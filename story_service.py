"""Persistent story jobs and a local Operit worker; all game writes use RoundStore."""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from flask import Response, abort, jsonify, request, stream_with_context
from werkzeug.exceptions import HTTPException
import round_runtime as rr
import save_store
import relationship_query as rq
import story_reading as sr
import interaction_runtime as ir
import story_progression as sp

STORY_PROTOCOL = 3
LEASE_SECONDS = 120
ACTIVE = {'preparing', 'queued', 'generating', 'validating', 'refund_pending'}
RULES = ('txt文件/一键注入指南.txt', 'txt文件/全局执行法典.md',
         'txt文件/提示词.md', 'txt文件/故事检索索引.md',
         'txt文件/知识库/世界观类.json', 'txt文件/知识库/角色类.json',
         'txt文件/知识库/叙事判断.json', 'txt文件/知识库/系统标签类.json', 'txt文件/事件注册表.json',
         rq.SOURCE, rq.VIEW, rq.RESOLVER, 'story_reading.py')

READ_TOOLS = {'read_file', 'read_file_full', 'read_file_part'}
READONLY_TOOLS = READ_TOOLS | {'list_files', 'find_files', 'grep_code', 'file_info', 'file_exists'}
REQUIRED_READS = (rr.FILES[0], RULES[0], RULES[1], RULES[2], RULES[3], 'data.json')
REQUIRED_BROWSE = ('txt文件', 'txt文件/知识库', '存档')


class _EventHub:
    """In-memory pub/sub for instant worker Long-Polling and browser SSE notifications."""

    def __init__(self, max_events=96):
        self._cond = threading.Condition()
        self._max_events = max_events
        self.seq = 0
        self.worker_seq = 0
        self._events = []

    def publish(self, event_type, payload=None, wake_worker=False):
        with self._cond:
            self.seq += 1
            if wake_worker:
                self.worker_seq += 1
            self._events.append((self.seq, event_type, payload if payload is not None else {}))
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]
            self._cond.notify_all()
            return self.seq

    def wait_worker(self, since_seq, timeout=25.0):
        deadline = time.monotonic() + max(0.2, min(float(timeout), 25.0))
        with self._cond:
            while self.worker_seq <= since_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            return self.worker_seq

    def wait_client(self, since_seq, timeout=15.0):
        deadline = time.monotonic() + max(0.2, min(float(timeout), 20.0))
        with self._cond:
            while self.seq <= since_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            missed = [item for item in self._events if item[0] > since_seq]
            return missed, self.seq


class StoryService:
    def __init__(self, root, *, tts_prewarmer=None):
        self.store = rr.RoundStore(root)
        self.root = self.store.root
        self.directory = self.store._path('.round-runtime/story')
        self.start_lock = threading.Lock()
        self.started = False
        self.service_epoch = secrets.token_hex(16)
        self.hub = _EventHub()
        self._stream_lock = threading.Lock()
        self._stream_preview = {}
        self._tts_prewarmer = tts_prewarmer
        self._prewarmed_keys = set()

    def _trigger_tts_prewarm(self, messages, *, dedup_prefix=''):
        fn = self._tts_prewarmer
        if not callable(fn) or not messages:
            return
        try:
            voice_cfg_rev = str((self.root / 'voice_config.json').stat().st_mtime_ns)
        except OSError:
            voice_cfg_rev = '0'
        candidates = []
        for idx, m in enumerate(messages):
            if not isinstance(m, dict):
                continue
            kind = m.get('kind')
            speaker = m.get('speaker', '')
            text = (m.get('text') or '').strip()
            if not text:
                continue
            if kind == 'narration':
                voice_who = '旁白'
            elif kind == 'dialogue' and speaker in ('沈知韫', '苏婉青', '徐念薇'):
                voice_who = speaker
            elif kind == 'action' and speaker in ('沈知韫', '苏婉青', '徐念薇'):
                voice_who = '旁白'
            else:
                continue
            sig = f'{dedup_prefix}:{voice_cfg_rev}:{voice_who}:{hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]}'
            with self._stream_lock:
                if sig in self._prewarmed_keys:
                    continue
                if len(self._prewarmed_keys) > 256:
                    self._prewarmed_keys.clear()
                self._prewarmed_keys.add(sig)
            candidates.append({'speaker': voice_who, 'text': text})
            if len(candidates) >= 3:
                break
        if candidates:
            try:
                fn(candidates)
            except Exception:
                pass

    def _clear_preview(self, key=None):
        with self._stream_lock:
            if key is None:
                self._stream_preview.clear()
            else:
                self._stream_preview.pop(key, None)

    def _path(self, name):
        return self.store._path('.round-runtime/story/' + name)

    def _read(self):
        path = self._path('tasks.json')
        if not path.exists():
            return {'version': 1, 'latest': None, 'jobs': {}, 'bridge_seen': 0}
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=rr._pairs)
        if value.get('version') != 1 or not isinstance(value.get('jobs'), dict):
            raise rr.RecoveryError('故事任务记录损坏，已停止任务写入')
        return value

    def _write(self, value):
        rr._atomic(self._path('tasks.json'), rr._json(value))

    def _blob(self, request_id, suffix):
        return self._path(hashlib.sha256(request_id.encode()).hexdigest() + suffix)

    def _expire(self, state):
        changed = False
        for job in state['jobs'].values():
            if job.get('reservation') and job['status']=='generating' and job.get('lease_until',0)<time.time():
                sp.refund(self,state,job,'interrupted','生成超时，预扣已全额返还，可原编号重试。')
                changed = True
                continue
            if job['status'] == 'generating' and job.get('lease_until', 0) < time.time():
                job.update(status='interrupted', error='生成连接已中断。原行动已保留，可重试。', lease=None)
                changed = True
        if changed:
            self._write(state)

    def _reset_guard(self):
        if self.store._path('.round-runtime/reset-journal.json').exists():
            raise rr.RecoveryError('新档清理尚未恢复，请停止服务并运行存档清理器.py --recover')

    def _save_epoch(self):
        path = self.store._path('.round-runtime/save-epoch.json')
        if not path.exists():
            return 'legacy'
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('version') != 1 or not re.fullmatch(r'[0-9a-f]{32}', value.get('epoch', '')):
                raise ValueError('invalid save epoch')
            return value['epoch']
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise rr.RecoveryError('新档标识无效，请检查清理器恢复记录') from exc

    def start(self):
        self._reset_guard()
        with self.start_lock:
            if self.started:
                return
            with self.store._locked():
                state = self._read()
                for job in state['jobs'].values():
                    if job.get('reservation') and job['status']=='preparing':
                        sp.refund(self,state,job,'interrupted','准备过程被中断，预扣已返还。')
                pending = [key for key, job in state['jobs'].items() if job['status'] == 'validating']
            for key in pending:
                self._finish(key)
            self.started = True

    def _public(self, job):
        if job is None:
            return None
        value = {key: val for key, val in job.items()
                if key not in {'lease', 'lease_until', 'before_panel', 'reservation', 'settlement', 'generation_model', 'created_at', 'claimed_at', 'returned_at', 'validation_started_at', 'committed_at', 'timing'}}
        timing = job.get('timing') or {}
        if isinstance(timing, dict):
            safe_timing = {key: timing[key] for key in ('queue_ms', 'generation_ms', 'settlement_ms', 'preflight_ms', 'acceptance_ms', 'generation_passes', 'settlement_passes', 'model_id', 'settlement_model_id') if key in timing}
            if safe_timing:
                value['timing'] = safe_timing
        if job.get('reservation'):
            value['reservation'] = {'status':job['reservation']['status'], 'quote':job['reservation']['quote']}
        return value

    def _expected_plugin_version(self):
        manifest_path = self.root / 'scene_chat_dev/local.story.operit_bridge/manifest.json'
        try:
            st = manifest_path.stat()
        except OSError:
            return ''
        cached = getattr(self, '_plugin_ver_cache', None)
        if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]
        try:
            ver = str(json.loads(manifest_path.read_text(encoding='utf-8')).get('version') or '').strip()
        except Exception:
            ver = ''
        self._plugin_ver_cache = (st.st_mtime_ns, st.st_size, ver)
        return ver

    def _bridge_view(self, state):
        now = time.time()
        monitor = state.get('bridge_monitor')
        expected_ver = self._expected_plugin_version()
        command = dict(state['bridge_control']) if state.get('bridge_control') else None
        if command and command['status'] == 'requested' and now - command['issued_at'] > 120:
            command['status'] = 'expired'
        if not monitor:
            connected = now - state.get('bridge_seen', 0) < 45
            return {'control_supported': True, 'present': connected, 'phase': 'legacy' if connected else 'offline',
                    'running': connected, 'busy': False, 'last_error': '',
                    'expected_plugin_version': expected_ver, 'control': command}
        present = now - monitor['received_at'] < 15
        extra = {}
        for opt_key in (
            'dual_stage', 'primary_model_mode', 'primary_function_type',
            'settlement_function_type', 'settlement_model', 'settlement_fallback',
            'settlement_thinking', 'settlement_thinking_mode', 'available_models', 'function_bindings',
        ):
            if opt_key in monitor:
                extra[opt_key] = monitor[opt_key]
        if 'settlement_thinking_mode' not in extra and 'settlement_thinking' in extra:
            extra['settlement_thinking_mode'] = 'on' if extra['settlement_thinking'] else 'off'
        return {'control_supported': True, 'present': present,
                **{key: monitor[key] for key in ('running', 'busy', 'last_error', 'plugin_version')},
                'expected_plugin_version': expected_ver,
                'session': monitor.get('session'), **extra,
                'phase': monitor['phase'] if present else 'offline', 'control': command}

    def bridge_control(self, body):
        self.start()
        allowed_keys = {
            'action', 'session_policy', 'dual_stage', 'settlement_function_type',
            'settlement_thinking', 'settlement_thinking_mode', 'primary_model_mode', 'primary_function_type',
            'primary_provider_id', 'primary_model_id',
            'slot', 'provider_id', 'model_id', 'use_as_settlement', 'max_turns',
        }
        rr._keys(body, allowed_keys, '桥接控制', {'action'})
        action = body['action']
        valid_actions = (
            'start', 'stop', 'reset_session', 'session_policy', 'dual_stage',
            'settlement_slot', 'settlement_thinking', 'primary_model',
            'bind_function_slot', 'max_turns',
        )
        if action not in valid_actions:
            raise rr.RoundError('桥接控制操作无效')
        payload = {}
        if action == 'session_policy':
            if body.get('session_policy') not in ('continuous', 'service_restart', 'per_action'):
                raise rr.RoundError('会话方式无效')
            payload['session_policy'] = body['session_policy']
        elif 'session_policy' in body:
            raise rr.RoundError('仅会话设置接收session_policy')

        if action == 'dual_stage':
            if type(body.get('dual_stage')) is not bool:
                raise rr.RoundError('双阶段模式开关须为布尔值')
            payload['dual_stage'] = body['dual_stage']
        elif 'dual_stage' in body:
            raise rr.RoundError('仅双阶段控制接收dual_stage')

        if action == 'settlement_slot':
            slot = body.get('settlement_function_type')
            if not isinstance(slot, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', slot):
                raise rr.RoundError('后台结算模型槽名称无效')
            payload['settlement_function_type'] = slot
            if 'settlement_thinking_mode' in body:
                mode_val = body['settlement_thinking_mode']
                if mode_val not in ('auto', 'off', 'on'):
                    raise rr.RoundError('副模型思考模式须为 auto/off/on')
                payload['settlement_thinking_mode'] = mode_val
                payload['settlement_thinking'] = (mode_val == 'on')
            elif 'settlement_thinking' in body:
                if type(body['settlement_thinking']) is not bool:
                    raise rr.RoundError('副模型思考开关须为布尔值')
                payload['settlement_thinking'] = body['settlement_thinking']
                payload['settlement_thinking_mode'] = 'on' if body['settlement_thinking'] else 'off'
        elif 'settlement_function_type' in body:
            raise rr.RoundError('仅结算槽设置接收settlement_function_type')

        if action == 'settlement_thinking':
            if 'settlement_thinking_mode' in body:
                mode_val = body['settlement_thinking_mode']
                if mode_val not in ('auto', 'off', 'on'):
                    raise rr.RoundError('副模型思考模式须为 auto/off/on')
                payload['settlement_thinking_mode'] = mode_val
                payload['settlement_thinking'] = (mode_val == 'on')
            else:
                if type(body.get('settlement_thinking')) is not bool:
                    raise rr.RoundError('副模型思考开关须为布尔值')
                payload['settlement_thinking'] = body['settlement_thinking']
                payload['settlement_thinking_mode'] = 'on' if body['settlement_thinking'] else 'off'
        elif action != 'settlement_slot' and ('settlement_thinking' in body or 'settlement_thinking_mode' in body):
            raise rr.RoundError('仅副模型设置接收settlement_thinking')

        if action == 'primary_model':
            mode = body.get('primary_model_mode')
            if mode not in ('slot', 'fixed'):
                raise rr.RoundError('主模型模式须为slot或fixed')
            payload['primary_model_mode'] = mode
            if mode == 'slot':
                slot = body.get('primary_function_type', 'CHAT')
                if not isinstance(slot, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', slot):
                    raise rr.RoundError('主模型功能槽名称无效')
                payload['primary_function_type'] = slot
            else:
                prov = body.get('primary_provider_id')
                mod = body.get('primary_model_id')
                if not isinstance(prov, str) or not prov.strip() or len(prov) > 256:
                    raise rr.RoundError('主模型服务商标识无效')
                if not isinstance(mod, str) or not mod.strip() or len(mod) > 256:
                    raise rr.RoundError('主模型标识无效')
                payload['primary_provider_id'] = prov.strip()
                payload['primary_model_id'] = mod.strip()
        elif any(k in body for k in ('primary_model_mode', 'primary_function_type', 'primary_provider_id', 'primary_model_id')):
            raise rr.RoundError('仅主模型设置接收主模型参数')

        if action == 'bind_function_slot':
            slot = body.get('slot')
            prov = body.get('provider_id')
            mod = body.get('model_id')
            if not isinstance(slot, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', slot):
                raise rr.RoundError('目标功能槽名称无效')
            if not isinstance(prov, str) or not prov.strip() or len(prov) > 256:
                raise rr.RoundError('目标服务商标识无效')
            if not isinstance(mod, str) or not mod.strip() or len(mod) > 256:
                raise rr.RoundError('目标模型标识无效')
            payload['slot'] = slot
            payload['provider_id'] = prov.strip()
            payload['model_id'] = mod.strip()
            if 'use_as_settlement' in body:
                if type(body['use_as_settlement']) is not bool:
                    raise rr.RoundError('use_as_settlement须为布尔值')
                payload['use_as_settlement'] = body['use_as_settlement']
        elif any(k in body for k in ('slot', 'provider_id', 'model_id', 'use_as_settlement')):
            raise rr.RoundError('仅功能槽绑定操作接收slot/provider_id/model_id')

        if action == 'max_turns':
            turns = body.get('max_turns')
            if type(turns) is not int or turns < 2 or turns > 30:
                raise rr.RoundError('自动切窗轮数须为2～30之间的整数')
            payload['max_turns'] = turns
        elif 'max_turns' in body:
            raise rr.RoundError('仅切窗设置接收max_turns')

        # Ensure no unexpected leftover keys for actions without extra fields.
        if set(body.keys()) - {'action', *payload.keys()}:
            raise rr.RoundError('桥接控制包含不支持的参数组合')

        idle_only_actions = (
            'reset_session', 'session_policy', 'dual_stage', 'settlement_slot',
            'settlement_thinking', 'primary_model', 'bind_function_slot', 'max_turns',
        )
        with self.store._locked():
            state = self._read()
            if action in idle_only_actions and any(
                    j['status'] in ACTIVE or j['status'] in ('preparing', 'refund_pending') for j in state['jobs'].values()):
                raise rr.ConflictError('请等待当前行动结束后调整会话或模型配置')
            previous = state.get('bridge_control')
            prev_payload = {k: v for k, v in previous.items() if k not in ('id', 'action', 'issued_at', 'status', 'completed_at', 'error')} if isinstance(previous, dict) else None
            same_cmd = (previous and previous['action'] == action
                        and prev_payload == payload
                        and previous['status'] == 'requested'
                        and time.time() - previous['issued_at'] <= 120)
            if not same_cmd:
                state['bridge_control'] = {
                    'id': secrets.token_hex(16), 'action': action,
                    'issued_at': time.time(), 'status': 'requested',
                    **payload,
                }
                self._write(state)
            result = self._status(state)
        self.hub.publish('bridge_control', {'action': action}, wake_worker=True)
        return result

    def worker_control(self, body):
        self.start()
        rr._keys(body, {'runtime', 'ack_id', 'ack_error'}, '桥接状态', {'runtime'})
        runtime = body['runtime']
        fields = {'phase', 'running', 'busy', 'last_error', 'plugin_version', 'model'}
        opt_fields = {
            'session', 'dual_stage', 'primary_model_mode', 'primary_function_type',
            'settlement_function_type', 'settlement_model', 'settlement_fallback',
            'settlement_thinking', 'settlement_thinking_mode', 'available_models', 'function_bindings',
        }
        rr._keys(runtime, fields | opt_fields, 'runtime', fields)
        if runtime.get('session') is not None:
            session = runtime['session']
            sf = {'policy', 'chat_id', 'generation', 'reset_reason'}
            sf_opt = {'turn_count', 'max_turns'}
            rr._keys(session, sf | sf_opt, 'session', sf)
            if session['policy'] not in ('continuous', 'service_restart', 'per_action') or type(session['generation']) is not int or session['generation'] < 0:
                raise rr.RoundError('桥接会话状态无效')
            if any(not isinstance(session[k], str) or len(session[k]) > 200 for k in ('chat_id', 'reset_reason')):
                raise rr.RoundError('桥接会话标识无效')
            for k in ('turn_count', 'max_turns'):
                if k in session and (type(session[k]) is not int or session[k] < 0):
                    raise rr.RoundError('桥接会话计数无效')
        if 'dual_stage' in runtime and type(runtime['dual_stage']) is not bool:
            raise rr.RoundError('双阶段状态须为布尔值')
        if 'settlement_fallback' in runtime and type(runtime['settlement_fallback']) is not bool:
            raise rr.RoundError('后台结算回退标记须为布尔值')
        if 'settlement_thinking' in runtime and type(runtime['settlement_thinking']) is not bool:
            raise rr.RoundError('副模型思考标记须为布尔值')
        if 'settlement_thinking_mode' in runtime and runtime['settlement_thinking_mode'] not in ('auto', 'off', 'on'):
            raise rr.RoundError('副模型思考模式无效')
        if 'primary_model_mode' in runtime and runtime['primary_model_mode'] not in ('slot', 'fixed'):
            raise rr.RoundError('主模型模式无效')
        if 'primary_function_type' in runtime:
            pft = runtime['primary_function_type']
            if not isinstance(pft, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', pft):
                raise rr.RoundError('主模型槽位标识无效')
        if 'settlement_function_type' in runtime:
            sft = runtime['settlement_function_type']
            if not isinstance(sft, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', sft):
                raise rr.RoundError('后台结算槽位标识无效')
        clean_available_models = None
        if 'available_models' in runtime:
            raw_models = runtime['available_models']
            if not isinstance(raw_models, list) or len(raw_models) > 120:
                raise rr.RoundError('可用模型列表无效')
            clean_available_models = []
            for item in raw_models:
                if not isinstance(item, dict):
                    raise rr.RoundError('可用模型项无效')
                rr._keys(item, {'provider_id', 'provider_name', 'model_id'}, '可用模型项', {'provider_id', 'provider_name', 'model_id'})
                if any(not isinstance(item[k], str) or not item[k] or len(item[k]) > 256 for k in ('provider_id', 'provider_name', 'model_id')):
                    raise rr.RoundError('可用模型字段无效')
                clean_available_models.append({k: item[k] for k in ('provider_id', 'provider_name', 'model_id')})
        clean_function_bindings = None
        if 'function_bindings' in runtime:
            raw_bindings = runtime['function_bindings']
            if not isinstance(raw_bindings, list) or len(raw_bindings) > 32:
                raise rr.RoundError('功能槽绑定列表无效')
            clean_function_bindings = []
            for item in raw_bindings:
                if not isinstance(item, dict):
                    raise rr.RoundError('功能槽绑定项无效')
                rr._keys(item, {'function_type', 'provider_id', 'provider_name', 'model_id'}, '功能槽绑定项', {'function_type', 'provider_id', 'provider_name', 'model_id'})
                if not isinstance(item['function_type'], str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', item['function_type']):
                    raise rr.RoundError('功能槽名称无效')
                if any(not isinstance(item[k], str) or len(item[k]) > 256 for k in ('provider_id', 'provider_name', 'model_id')):
                    raise rr.RoundError('功能槽模型字段无效')
                clean_function_bindings.append({k: item[k] for k in ('function_type', 'provider_id', 'provider_name', 'model_id')})
        if runtime['phase'] not in ('ready', 'paused', 'starting', 'generating', 'error'):
            raise rr.RoundError('桥接运行阶段无效')
        if type(runtime['running']) is not bool or type(runtime['busy']) is not bool:
            raise rr.RoundError('桥接运行状态须为布尔值')
        for key, limit in (('last_error', 500), ('plugin_version', 64)):
            if not isinstance(runtime[key], str) or len(runtime[key]) > limit:
                raise rr.RoundError('桥接' + key + '无效')
        if body.get('ack_id') is not None and (not isinstance(body['ack_id'], str)
                or not re.fullmatch('[0-9a-f]{32}', body['ack_id'])):
            raise rr.RoundError('桥接控制回执无效')
        if not isinstance(body.get('ack_error', ''), str) or len(body.get('ack_error', '')) > 500:
            raise rr.RoundError('桥接控制错误回执无效')
        model = self._model(runtime['model'])
        settlement_model = self._model(runtime.get('settlement_model')) if runtime.get('settlement_model') is not None else None
        changed = False
        with self.store._locked():
            state = self._read()
            prev = state.get('bridge_monitor') or {}
            clean_runtime = {**runtime, 'model': model}
            if 'settlement_model' in runtime:
                clean_runtime['settlement_model'] = settlement_model
            if clean_available_models is not None:
                clean_runtime['available_models'] = clean_available_models
            if clean_function_bindings is not None:
                clean_runtime['function_bindings'] = clean_function_bindings
            changed = any(prev.get(k) != clean_runtime.get(k) for k in (
                'phase', 'running', 'busy', 'last_error', 'plugin_version', 'model',
                'session', 'dual_stage', 'primary_model_mode', 'primary_function_type',
                'settlement_function_type', 'settlement_model', 'settlement_fallback',
                'settlement_thinking', 'settlement_thinking_mode', 'available_models', 'function_bindings',
            ))
            state['bridge_monitor'] = {**clean_runtime, 'received_at': time.time()}
            state['bridge_model'] = model
            command = state.get('bridge_control')
            if command and command['id'] == body.get('ack_id') and command['status'] == 'requested':
                command.update(status='failed' if body.get('ack_error') else 'applied', completed_at=time.time())
                if body.get('ack_error'):
                    command['error'] = body['ack_error']
                changed = True
            if runtime['running'] and runtime['phase'] in ('ready', 'generating') and not runtime['last_error']:
                state['bridge_seen'] = time.time()
            self._write(state)
            pending = self._bridge_view(state)['control']
            response = {'command': pending if pending and pending['status'] == 'requested' else None,
                        'story_protocol': STORY_PROTOCOL, 'service_epoch': self.service_epoch}
        if changed:
            self.hub.publish('bridge_state', {'phase': runtime['phase'], 'running': runtime['running']})
        return response

    def _status(self, state):
        bridge = self._bridge_view(state)
        connected = bridge['present'] and bridge['running'] and bridge['phase'] in ('ready', 'generating', 'legacy') and not bridge['last_error']
        return {'task': self._public(state['jobs'].get(state['latest'])),
                'bridge_connected': bool(connected), 'bridge': bridge,
                'reading_preflight': 1, 'live_reading_revision': 2, 'action_contract_revision':1,
                'material_delivery_revision': 1, 'material_delivery_v2': 1,
                'dual_stage_protocol': 1, 'worker_wait_supported': True, 'sse_supported': True,
                'service_epoch':self.service_epoch,
                'story_protocol': STORY_PROTOCOL, 'bridge_model': state.get('bridge_model'),
                'save_epoch': self._save_epoch(), 'interaction_protocol': 3 if sp.enabled(self.root) else 2}

    def status(self, request_id=None):
        self.start()
        with self.store._locked():
            state = self._read()
            self._expire(state)
            if request_id is not None:
                if request_id not in state['jobs']:
                    abort(404)
                return {'task': self._public(state['jobs'][request_id])}
            return self._status(state)

    def snapshot(self):
        self.start()
        with self.store._locked():
            files = self.store._files()
            state = self._read()
            self._expire(state)
            raw = files.get('data.json')
            if raw:
                data = json.loads(raw)
            else:
                st, _, _ = save_store.load_bundle(self.root, files)
                rt = st.get('runtime') or {}
                data = {
                    'round': rt.get('memory_round', 0),
                    'storyNodes': [],
                    'presence': st.get('presence', {}),
                    'sceneTitle': (st.get('presence', {}).get('徐志北') or {}).get('location', '徐家主宅'),
                    'story_runtime': {k: rt[k] for k in ('clock', 'memory_round', 'last_closed', 'phase', 'item_recovered', 'action_index', 'closed_by') if k in rt},
                    **({'prologue': rt['prologue']} if rt.get('prologue') else {}),
                }
            revision = rr._revision(files)
            job = state['jobs'].get(state['latest'])
            settlement = None
            if (job and job['status'] == 'committed' and job.get('before_panel') is not None
                    and (job.get('receipt') or {}).get('revision') == revision):
                settlement = {'revision': revision, 'round': data.get('round'),
                              'before_memory': job['before_panel']}
            return {'revision': revision, 'settlement': settlement,
                    'state_version': self.store._ledger()['sequence'],
                    'data': data,
                    'memory_text': (files[rr.FILES[0]] or b'').decode('utf-8'),
                    'items_text': (files[rr.FILES[1]] or b'').decode('utf-8'),
                    **self._status(state)}

    def new_game(self, body):
        self.start()
        rr._keys(body, {'request_id', 'save_epoch', 'confirm'}, 'new_game', {'request_id', 'save_epoch', 'confirm'})
        if body['confirm'] != 'new_game' or not isinstance(body['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', body['request_id']):
            raise rr.RoundError('新档确认信息无效')
        experimental = getattr(self, 'experimental', None)
        from contextlib import nullcontext
        exp_ctx = experimental.lock if experimental is not None else nullcontext()
        with exp_ctx:
            with self.store._locked():
                epoch = self._save_epoch()
                ep = self.store._path('.round-runtime/save-epoch.json')
                if ep.exists() and json.loads(ep.read_bytes()).get('request_id') == body['request_id']:
                    return {'status': 'reset', 'save_epoch': epoch, 'replayed': True}
                if epoch != body['save_epoch']:
                    raise rr.ConflictError('当前存档已改变，请刷新后重新确认新档')
                state = self._read()
                self._expire(state)
                if experimental is not None:
                    with experimental.db() as db:
                        experimental.expire(db)
                        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','generating')").fetchone():
                            raise rr.ConflictError('实验入口仍有请求在处理，请结束后再开新档')
                blocking_statuses = ACTIVE - {'refund_pending'}
                if any(j['status'] in blocking_statuses for j in state['jobs'].values()) or self._bridge_view(state).get('busy'):
                    raise rr.ConflictError('仍有行动在处理，请等待完成并暂停桥接后再开新档')
                import importlib.util
                spec = importlib.util.spec_from_file_location('_game_cleaner', self.root / '存档清理器.py')
                cleaner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cleaner)
                cleaner._reset_files(self.root, keep_backup=True, request_id=body['request_id'])
                data = json.loads(self.store._files()['data.json'] or b'{}')
                self._clear_preview()
                self._inquiries_path().unlink(missing_ok=True)
                result = {'status': 'reset', 'save_epoch': self._save_epoch(), 'replayed': False, 'prologue':data.get('prologue')}
        self.hub.publish('save_reset', {'save_epoch': result['save_epoch']})
        return result

    DEFAULT_LIVE_LIMIT = 10

    def _public_segment(self, value, current, progress):
        public = {k: v for k, v in value.items() if k not in ('audit', 'before_world', 'resolution')}
        if current and value['id'] == current['id'] and not progress['completed']:
            public['messages'] = public['messages'][:progress['revealed']]
            public['handoff'] = ''
            public.pop('decision', None)
            public.pop('settlement', None)
        return public

    def interaction_snapshot(self, before=None, limit=None):
        self.start()
        page_limit = self.DEFAULT_LIVE_LIMIT
        if limit is not None:
            try:
                page_limit = max(1, min(60, int(limit)))
            except (TypeError, ValueError) as exc:
                raise rr.RoundError('历史分页数量无效') from exc
        boundary = None
        if before is not None:
            try:
                boundary = int(before)
            except (TypeError, ValueError) as exc:
                raise rr.RoundError('历史游标无效') from exc
        with self.store._locked():
            state = self._read()
            self._expire(state)
            files = self.store._files()
            current = ir.segment(self.root, files)
            progress = ir.playback(self.root, current)
            selected, has_older = ir.recent_rows_page(self.store, files, before=boundary, limit=page_limit)
            history = [self._public_segment(value, current, progress) for _p, value in selected]
            world = current['before_world'] if (current and not progress['completed'] and current.get('before_world')) else ir.view(self.store, files)
            settlement = current.get('settlement') if current and progress['completed'] else None
            latest_job = state['jobs'].get(state['latest'])
            preview = None
            if latest_job and latest_job.get('status') in ('generating', 'validating'):
                with self._stream_lock:
                    raw_preview = self._stream_preview.get(latest_job['request_id'])
                    if raw_preview:
                        preview = dict(raw_preview)
            return {'world': world, 'settlement':settlement, 'playback': progress, 'history': history,
                    'has_older': has_older, 'stream_preview': preview,
                    'preferences': ir.load_story_prefs(self.root),
                    'revision': rr._revision(files), 'state_version': self.store._ledger()['sequence'],
                    **self._status(state)}

    def update_preferences(self, body):
        self.start()
        with self.store._locked():
            prefs = ir.save_story_prefs(self.root, body)
        self.hub.publish('preferences_updated', prefs)
        return {'preferences': prefs}

    def playback_progress(self, body):
        self.start()
        rr._keys(body, {'save_epoch', 'segment_id', 'revealed', 'completed', 'catchup', 'compact'}, 'playback',
                 {'save_epoch', 'segment_id', 'revealed', 'completed'})
        catchup = bool(body.get('catchup', False))
        compact = bool(body.get('compact', False))
        if 'catchup' in body and type(body['catchup']) is not bool:
            raise rr.RoundError('演播追平标记须为布尔值')
        if 'compact' in body and type(body['compact']) is not bool:
            raise rr.RoundError('演播精简标记须为布尔值')
        with self.store._locked():
            if body['save_epoch'] != self._save_epoch():
                raise rr.ConflictError('已切换新档，旧演播进度无效')
            files = self.store._files()
            row = ir.segment(self.root, files)
            if not row or row['id'] != body['segment_id']:
                raise rr.ConflictError('本段已更新，旧演播进度无效')
            progress = ir.update_playback(self.store, row, body['revealed'], body['completed'], allow_catchup=catchup)
            if compact:
                state = self._read()
                self._expire(state)
                public_seg = self._public_segment(row, row, progress)
                world = ir.view(self.store, files) if progress['completed'] else None
                settlement = row.get('settlement') if progress['completed'] else None
                return {
                    'compact': True,
                    'playback': progress,
                    'history': [public_seg],
                    'world': world,
                    'settlement': settlement,
                    'revision': rr._revision(files),
                    'state_version': self.store._ledger()['sequence'],
                    **self._status(state),
                }
        return self.interaction_snapshot()

    def _inquiries_path(self):
        return self._path('shop_inquiries.json')

    def _read_inquiries(self):
        path = self._inquiries_path()
        if not path.is_file():
            return {'version': 1, 'latest': None, 'items': {}}
        try:
            raw = json.loads(path.read_bytes())
        except Exception:
            return {'version': 1, 'latest': None, 'items': {}}
        if not isinstance(raw, dict) or not isinstance(raw.get('items'), dict):
            return {'version': 1, 'latest': None, 'items': {}}
        return raw

    def _write_inquiries(self, data):
        items = data.get('items') or {}
        if len(items) > 20:
            ordered = sorted(items.items(), key=lambda kv: float((kv[1] or {}).get('created_at') or 0))
            data['items'] = dict(ordered[-20:])
            if data.get('latest') not in data['items']:
                data['latest'] = ordered[-1][0] if ordered else None
        rr._atomic(self._inquiries_path(), rr._json(data))

    def _expire_inquiries(self, data, *, save_epoch=None):
        now = time.time()
        changed = False
        for iq in (data.get('items') or {}).values():
            if not isinstance(iq, dict):
                continue
            status = iq.get('status')
            if save_epoch and iq.get('save_epoch') and iq.get('save_epoch') != save_epoch and status in ('queued', 'claimed'):
                iq['status'] = 'cancelled'
                iq['error'] = '存档已切换，本次询货已取消'
                iq['completed_at'] = now
                changed = True
                continue
            if status == 'claimed' and (now - float(iq.get('claimed_at') or iq.get('created_at') or 0)) > LEASE_SECONDS:
                iq['status'] = 'failed'
                iq['error'] = 'AI 询货进货超时，请检查桥接状态后重试'
                iq['completed_at'] = now
                changed = True
            elif status == 'queued' and (now - float(iq.get('created_at') or 0)) > 180:
                iq['status'] = 'failed'
                iq['error'] = '桥接长时间未认领询货请求，请确认 Operit 桥接已开启'
                iq['completed_at'] = now
                changed = True
        return changed

    @staticmethod
    def _public_inquiry(iq):
        if not isinstance(iq, dict):
            return None
        return {
            'id': iq.get('id', ''),
            'query': iq.get('query', ''),
            'status': iq.get('status', ''),
            'save_epoch': iq.get('save_epoch', ''),
            'created_at': iq.get('created_at'),
            'completed_at': iq.get('completed_at'),
            'shopkeeper_reply': iq.get('shopkeeper_reply', ''),
            'added_items': list(iq.get('added_items') or []),
            'rejected_reasons': list(iq.get('rejected_reasons') or []),
            'error': iq.get('error', ''),
        }

    def shop_view(self):
        self.start()
        with self.store._locked():
            files = self.store._files()
            memory = (files[rr.FILES[0]] or b'').decode('utf-8')
            engine = rr._engine(self.root, self.root)
            points = engine._read_attr_value(memory, '系统宿主', '积分')
            shop_state = sp.parse_shop_echo_block(memory)
            catalog = sp.load_shop_catalog(self.root, optional=True)
            st, _, _ = save_store.load_bundle(self.root, files)
            dyn_items = list((st.get('shop') or {}).get('dynamic_catalog') or [])
            host_biz, heroine_affs = sp.read_shop_unlock_metrics(engine, memory)
            max_affection = max(heroine_affs.values()) if heroine_affs else 0
            row = ir.segment(self.root, files)
            prog = ir.playback(self.root, row)
            state = self._read()
            self._expire(state)
            busy = any(j['status'] in ACTIVE for j in state['jobs'].values())
            can_transact = (not busy) and (row is None or prog['completed'])
            cur_epoch = self._save_epoch()
            iq_store = self._read_inquiries()
            if self._expire_inquiries(iq_store, save_epoch=cur_epoch):
                self._write_inquiries(iq_store)
            latest_iq = iq_store['items'].get(iq_store.get('latest'))
            if latest_iq and latest_iq.get('save_epoch') != cur_epoch:
                latest_iq = None
            all_catalog_items = [
                *[{**it, 'source': 'static'} for it in catalog['items']],
                *[{**it, 'source': it.get('source') or 'ai_restock'} for it in dyn_items if isinstance(it, dict)],
            ]
            items = []
            for item in all_catalog_items:
                bought = shop_state['redeemed'].get(item['id'], 0)
                cap = item.get('max_per_save')
                remaining = None if cap is None else max(0, cap - bought)
                chk = sp.evaluate_unlock_req(item.get('unlock_req'), host_biz, heroine_affs)
                items.append({
                    **item,
                    'redeemed_count': bought,
                    'remaining': remaining,
                    'sold_out': cap is not None and bought >= cap,
                    'affordable': (points or 0) >= item['price'],
                    'unlocked': chk['unlocked'],
                    'unlock_reason': chk['reason'],
                    'unlock_hint': chk['hint'],
                })
            return {
                'version': catalog['version'],
                'tiers': catalog['tiers'],
                'categories': catalog.get('categories', {}),
                'items': items,
                'points': points if points is not None else 0,
                'host_biz': host_biz,
                'max_affection': max_affection,
                'dynamic_count': len(dyn_items),
                'dynamic_limit': sp.SHOP_DYNAMIC_LIMIT,
                'latest_inquiry': self._public_inquiry(latest_iq),
                'recent': shop_state['recent'],
                'can_transact': can_transact,
                'busy': busy,
                'revision': rr._revision(files),
                'save_epoch': cur_epoch,
            }

    def redeem_shop(self, body):
        result = sp.redeem_shop_item(self, body)
        self.hub.publish('committed', {'request_id': result['receipt']['request_id'], 'kind': 'shop_redeem'})
        return {**result, 'snapshot': self.interaction_snapshot()}

    def inquire_shop(self, body):
        self.start()
        rr._keys(body, {'query', 'save_epoch'}, '商城AI询货', {'query', 'save_epoch'})
        query = re.sub(r'\s+', ' ', str(body['query'] or '')).strip()
        if not query or len(query) > 120:
            raise rr.RoundError('询货描述须为 1～120 字的非空文本')
        with self.store._locked():
            cur_epoch = self._save_epoch()
            if body['save_epoch'] != cur_epoch:
                raise rr.ConflictError('当前存档已改变，请刷新后重试')
            state = self._read()
            self._expire(state)
            if any(j['status'] in ACTIVE for j in state['jobs'].values()):
                raise rr.ConflictError('当前有剧情行动正在处理，请待本段结算完成后再向商城询货')
            iq_store = self._read_inquiries()
            self._expire_inquiries(iq_store, save_epoch=cur_epoch)
            if any(it.get('status') in ('queued', 'claimed') for it in iq_store['items'].values()):
                raise rr.ConflictError('已有商城询货正在进货中，请稍候片刻')
            iq_id = 'siq-' + secrets.token_hex(8)
            iq = {
                'id': iq_id,
                'query': query,
                'status': 'queued',
                'save_epoch': cur_epoch,
                'lease': None,
                'created_at': time.time(),
                'claimed_at': None,
                'completed_at': None,
                'shopkeeper_reply': '',
                'added_items': [],
                'rejected_reasons': [],
                'error': '',
            }
            iq_store['items'][iq_id] = iq
            iq_store['latest'] = iq_id
            self._write_inquiries(iq_store)
            pub = {'inquiry': self._public_inquiry(iq)}
        self.hub.publish('shop_inquiry', {'id': iq_id, 'status': 'queued'}, wake_worker=True)
        return pub

    def shop_inquiry_status(self, iq_id):
        self.start()
        with self.store._locked():
            iq_store = self._read_inquiries()
            if self._expire_inquiries(iq_store, save_epoch=self._save_epoch()):
                self._write_inquiries(iq_store)
            iq = iq_store['items'].get(iq_id)
            if not iq:
                abort(404)
            return {'inquiry': self._public_inquiry(iq)}

    def claim_shop_inquiry(self, body=None):
        self.start()
        with self.store._locked():
            state = self._read()
            self._expire(state)
            if any(j['status'] in ACTIVE for j in state['jobs'].values()):
                return {'inquiry': None}
            cur_epoch = self._save_epoch()
            iq_store = self._read_inquiries()
            changed = self._expire_inquiries(iq_store, save_epoch=cur_epoch)
            queued = [
                it for it in iq_store['items'].values()
                if isinstance(it, dict) and it.get('status') == 'queued' and it.get('save_epoch') == cur_epoch
            ]
            if not queued:
                if changed:
                    self._write_inquiries(iq_store)
                return {'inquiry': None}
            queued.sort(key=lambda x: float(x.get('created_at') or 0))
            iq = queued[-1]
            iq['status'] = 'claimed'
            iq['lease'] = secrets.token_hex(16)
            iq['claimed_at'] = time.time()
            self._write_inquiries(iq_store)
            files = self.store._files()
            prompt_pack = sp.build_shop_inquiry_prompt(self.root, files, iq['query'])
            return {
                'inquiry': {
                    'id': iq['id'],
                    'lease': iq['lease'],
                    'query': iq['query'],
                    'save_epoch': iq['save_epoch'],
                    'system_prompt': prompt_pack['system_prompt'],
                    'user_prompt': prompt_pack['user_prompt'],
                }
            }

    def complete_shop_inquiry(self, iq_id, body):
        self.start()
        rr._keys(body, {'lease', 'text', 'payload', 'error'}, '商城询货提交', {'lease'})
        event_payload = None
        response = None
        with self.store._locked():
            iq_store = self._read_inquiries()
            iq = iq_store['items'].get(iq_id)
            if not iq:
                abort(404)
            if iq.get('status') in ('completed', 'failed', 'cancelled'):
                return {'inquiry': self._public_inquiry(iq)}
            lease = str(body.get('lease') or '')
            if iq.get('status') != 'claimed' or not iq.get('lease') or not hmac.compare_digest(lease, str(iq['lease'])):
                raise rr.ConflictError('商城询货租约无效或已过期')
            err_text = str(body.get('error') or '').strip()
            if err_text:
                iq['status'] = 'failed'
                iq['error'] = err_text[:400]
                iq['completed_at'] = time.time()
                self._write_inquiries(iq_store)
                event_payload = {'inquiry_id': iq_id, 'status': 'failed', 'error': iq['error']}
                response = {'inquiry': self._public_inquiry(iq)}
            else:
                raw_payload = body.get('payload') if body.get('payload') is not None else body.get('text')
                try:
                    res = sp.persist_dynamic_shop_items(
                        self,
                        raw_payload,
                        query=iq['query'],
                        expected_save_epoch=iq['save_epoch'],
                    )
                except rr.RoundError as exc:
                    iq['status'] = 'failed'
                    iq['error'] = str(exc)[:400]
                    iq['completed_at'] = time.time()
                    self._write_inquiries(iq_store)
                    event_payload = {'inquiry_id': iq_id, 'status': 'failed', 'error': iq['error']}
                    response = {'inquiry': self._public_inquiry(iq)}
                else:
                    iq['status'] = 'completed'
                    iq['completed_at'] = time.time()
                    iq['shopkeeper_reply'] = res['shopkeeper_reply']
                    iq['added_items'] = res['added_items']
                    iq['rejected_reasons'] = res['rejected_reasons']
                    iq['error'] = ''
                    self._write_inquiries(iq_store)
                    event_payload = {
                        'inquiry_id': iq_id,
                        'status': 'completed',
                        'added_count': len(res['added_items']),
                    }
                    response = {'inquiry': self._public_inquiry(iq), 'result': res}
        if event_payload is not None:
            self.hub.publish('shop_updated', event_payload)
        return response

    def delete_dynamic_shop_item(self, item_id, body=None):
        self.start()
        save_epoch = (body or {}).get('save_epoch') if isinstance(body, dict) else None
        res = sp.delete_dynamic_shop_item(self, item_id, save_epoch=save_epoch)
        self.hub.publish('shop_updated', {'removed_id': item_id})
        return {**res, 'snapshot': self.interaction_snapshot()}

    def claim_task_reward(self, body):
        result = sp.claim_task_reward(self, body)
        self.hub.publish('committed', {'request_id': result['receipt']['request_id'], 'kind': 'task_claim'})
        return {**result, 'snapshot': self.interaction_snapshot()}

    def upgrade_passive(self, body):
        result = sp.upgrade_passive_skill(self, body)
        self.hub.publish('committed', {'request_id': result['receipt']['request_id'], 'kind': 'passive_upgrade'})
        return {**result, 'snapshot': self.interaction_snapshot()}

    def acquire_intel(self, body):
        result = sp.acquire_intel(self, body)
        self.hub.publish('committed', {'request_id': result['receipt']['request_id'], 'kind': 'intel_acquire'})
        return {**result, 'snapshot': self.interaction_snapshot()}

    def toggle_leverage(self, body):
        result = sp.toggle_business_leverage(self, body)
        self.hub.publish('committed', {'request_id': result['receipt']['request_id'], 'kind': 'business_leverage'})
        return {**result, 'snapshot': self.interaction_snapshot()}

    def _context(self, prepared, request_id, action, previous_error="", entry_mode=None, command=None, selected=None):
        if entry_mode == ir.MODE:
            return ir.packet(self, prepared, request_id, action, command, previous_error, selected)
        audit = {}
        for name in (*RULES, *rr.FILES):
            path = self.store._path(name)
            if not path.is_file():
                continue
            raw = path.read_bytes()
            audit[name] = hashlib.sha256(raw).hexdigest()
        try:
            relationship_rows = rq.RelationshipRegistry(self.root).verify_view()
        except (ValueError, OSError) as exc:
            raise rr.RoundError('关系查询资料不可用: ' + str(exc)) from exc
        try:
            bundle = sr.build_bundle(self.root, request_id)
        except (ValueError, OSError) as exc:
            raise rr.RoundError('正文提取失败: ' + str(exc)) from exc
        required = []
        for name in REQUIRED_READS:
            projected_key = 'contract.inject' if name == RULES[0] else 'rule.prompt' if name == RULES[2] else None
            if projected_key:
                entry = bundle['entries'][projected_key]
                required.append({'key': projected_key, 'path': entry['path'], 'through_line': entry['through_line'],
                                 'source_alternative': entry['sources'][0]})
            else:
                required.append({'path': name, 'through_line': len(self.store._path(name).read_text(encoding='utf-8').splitlines())})
        for entry in bundle['entries'].values():
            audit[entry['path']] = entry['sha256']
        identity = {'schema_version': 1, 'request_id': request_id,
                    'base_revision': prepared['base_revision'], 'current_round': prepared['current_round']}
        guide = (self.root / RULES[0]).read_text(encoding='utf-8')
        match = rr.re.search(r'【节点键白名单开始】\s*(.*?)\s*【节点键白名单结束】', guide, rr.re.S)
        if not match:
            raise rr.RoundError('注入指南缺少桥接节点键白名单，请更新指南后重试')
        node_keys = rr.load_request(match.group(1))
        engine = rr._engine(self.root, self.root)
        known = set(engine.DEFAULT_PRESENCE) | {'徐承邺'}
        output_contract = {
            'fixed_fields': identity,
            'required_top_keys': sorted(rr.REQUIRED | {'system_log', 'options_text'}),
            'optional_defaults': {key: value for key, value in rr.OPTIONAL.items()
                                  if key not in {'system_log', 'options_text'}},
            'node_keys': node_keys, 'registered_speakers': sorted(known),
            'event_registry': {'path': 'txt文件/事件注册表.json', 'version': 1,
                               'sha256': audit['txt文件/事件注册表.json'],
                               'rule': '指南与sys条目的事件参数表由此源生成；仅按本回已发生事实选标签。'},
            'relationship_registry': {'path': rq.SOURCE, 'sha256': audit[rq.SOURCE],
                'view': {'path': rq.VIEW, 'sha256': audit[rq.VIEW]},
                'resolver': {'path': rq.RESOLVER, 'sha256': audit[rq.RESOLVER]},
                'occasions': list(rq.OCCASIONS), 'header_line': 1,
                'rule': '按索引读取实际方向/知情行，不自动读取全表；不得互借秘密，称谓可省略。'},
            'node_examples': [{'type': 'header', 'text': '[外出] 7月21日, 周二, 工作室, 08:43'},
                              {'type': 'narration', 'text': '你把材料清单放在桌边，纸页轻轻擦过指腹。'},
                              {'type': 'dialogue', 'speaker': '徐志北', 'text': '材料清单我带来了。'}],
            'rule': '示例仅演示字段，内容不可照抄。节点每个键只能出现一次，严格按node_keys选键；只有dialogue含speaker。上下文data.json为已提交的展示快照，含系统追加节点，不是本次请求模板。',
            'optional_top_fields': {key: {'type': 'null_or_object' if value is None else
                 'object' if isinstance(value, dict) else 'array'} for key, value in rr.OPTIONAL.items()
                 if key not in {'system_log', 'options_text'}},
             'memory_delta_keys': sorted(rr.MEMORY_DELTA_FIELDS),
             'field_layout': 'story_nodes、memory_deltas、options_text、model_audit与optional_top_fields中各字段均为顶层同级；'
                 '事件、NPC、道具、任务、微状态及计数器不要嵌入memory_deltas。无变化的可选字段直接省略。',
             'memory': '按指南的summary_sources触发条件提供增量；memory_deltas.round_conditions必填，报告已发生的烈度、推进与应激事实，累计数由程序结算；options_text不预先计分。',
            'round_conditions': {'location': 'memory_deltas.round_conditions',
                'required_fields': sorted(rr.ROUND_CONDITION_FIELDS),
                'intensity': ['A', 'B', 'C'], 'npc': [*rr.ROUND_NPCS, None],
                'rule': 'effective_progress/action_changed为布尔，scene为地点，stress_signals为本回次数，breakout_triggered仅列已发生事件对应计数键；语义由模型判断。'},
        }
        _, layers, _ = rr._memory_state(engine, {name: (value.encode('utf-8') if value is not None else None)
                                                     for name, value in prepared['snapshot'].items()})
        memory = prepared['snapshot'][rr.FILES[0]] or ''
        current_panel = memory.split('▶ 上回合历史快照', 1)[0]
        presence = re.search(r'【人物所在】\s*\n(.*?)(?=\n\s*【|\Z)', current_panel, re.S)
        assembly_memory = {'layers': {label: {'count': len(items),
                           'ranges': [list(engine._memory_item_range(item)) for item in items]}
                           for label, items in layers.items()},
                           'presence': presence.group(1).strip() if presence else ''}
        audit_contract = {
            'required': ['intent', 'scene', 'required_keys', 'evidence', 'v1', 'task', 'breakout'],
            'optional': {'notes': '最多三行的字符串数组'},
            'required_keys': '数组：本轮额外必需key；最小三键由程序加入。按实际意图与人物判断，不漏必需资料。',
            'evidence': '对象：最终必需key到本轮实际具体依据的单行字符串；不写已读取或同上。',
            'v1': {label: {'status': '通过', 'reason': '本轮具体语义依据；程序不代填'}
                   for label in ('V1-A', 'V1-B', 'V1-C', 'V1-D')},
            'task': '已读任务状态及本轮提议，未结算不能宣称完成',
            'breakout': '实际评估依据；无触发也须说明本轮为何不触发',
        }
        output_contract.update(
            result_format='story_semantics_v1',
            required_top_keys=['story_nodes', 'memory_deltas', 'options_text', 'model_audit'],
            optional_defaults={key: value for key, value in rr.OPTIONAL.items()
                               if key not in {'system_log', 'options_text'}},
            server_fields=['schema_version', 'request_id', 'base_revision', 'current_round',
                           'panel_changes', 'system_log'],
            model_audit=audit_contract,
            audit_rule='程序从本次正式会话审计组装读取事实、记忆层数、身份及事件清单；模型只交语义依据，不输出system_log。'
                       '可省略固定身份和空容器；若携带固定字段必须与round_identity完全一致。完整旧JSON仍兼容，但须正确身份及完整system_log，不能与model_audit混用。')
        policy = {'required_reads': required, 'required_browse': list(REQUIRED_BROWSE),
                   'version': sr.VERSION, 'required_keys': sorted(key for key, item in bundle['entries'].items() if item.get('always_required')), 'first_read_order': [item['path'] for item in required[:3]],
                  'canonical_roots': ['txt文件', '存档'],
                  'excluded_roots': ['开发者说明', '开发者功能', '.backup', '.operit', '.round-runtime',
                                     'Operit世界书导出', '日志', '__pycache__', 'vosi', '语音仓库'],
                  'relationship_queries': {'path': rq.VIEW, 'header_line': 1,
                       'key_lines': {row['key']: line for line, row in enumerate(relationship_rows[1:], 2)},
                       'coverage': '本目录仅定位，不算已读。用read_file_part读取第1行及所需key_lines行；'
                           'lore.称谓/lore.知情只有实际取得对应方向/人物正文才算已读，不包含未读取行。'}}
        for field in ('fixed_fields', 'optional_defaults', 'node_examples'):
            output_contract.pop(field, None)
        envelope = {'entry_mode': 'story_bridge', 'retrieval_mode': 'operit_session',
                    'host_action': action, 'round_identity': identity,
                    'summary_sources': prepared['summary_sources'],
                    'audit_origin': 'operit_tool_loop',
                    'reading_directory': {'nonce': bundle['nonce'], 'entries': {key: {'path': value['path'], 'through_line': value['through_line']}
                        for key, value in bundle['entries'].items()}},
                    'reading_policy': policy, 'output_contract': output_contract,
                    'previous_validation_error': previous_error or None}
        system = ('你是网页故事回合生成器。entry_mode=story_bridge、retrieval_mode=operit_session。'
                  '按reading_policy依次完整读取记忆库、contract.inject提取文件、法典，再主提示提取文件、索引、data.json；'
                  '前三份完成前不读取其他正文，每轮浏览required_browse目录。'
                  'reading_directory按key指向本任务原文提取件：首行是来源证明，后续是正文，必须全部实际读取；'
                  'read_file截断时用read_file_part补完，失败或正文缺失则阻断，不从历史补回。'
                  '按索引、在场人物与触发项读取相关key并沿指针继续；7条常驻key仍须取得，主角色对白须读其char。'
                  '可读原源兼容，但提取只覆盖对应key/片段，不等于读完整原库。'
                   '关系/知情按reading_policy.relationship_queries.key_lines定位，再实际读取第1行及所需行；目录不算正文，知情不互借。'
                  '只允许现有文件只读工具；禁止命令、写文件、外部服务、开发日志与非本任务缓存。'
                  '按output_contract交story_semantics_v1裸JSON：正文、记忆、选项、model_audit语义依据；'
                  '事件/道具/任务等可选字段与memory_deltas同级，依field_layout输出；空可选字段省略。'
                   '不输出system_log、读取次数、指纹或程序记忆统计；固定身份与空容器由程序补齐。'
                  '提交前逐一对照model_audit.required_keys与本轮真实工具记录，evidence引用的每个key都先取得完整正文；遗漏先补读并重评，不用历史或删key掩盖。V1必须有真实依据，未满足先修正，仍失败则说明阻塞，不能伪造通过。')
        turns = [{'kind': 'system', 'content': system},
                 {'kind': 'user', 'content': json.dumps(envelope, ensure_ascii=False)}]
        return {'protocol': STORY_PROTOCOL, 'turns': turns, 'audit': audit, 'reading_policy': policy,
                'assembly_memory': assembly_memory, 'reading_bundle': bundle}

    def _audit_path(self, raw, workspace):
        if not isinstance(raw, str) or not raw:
            raise rr.RoundError('工具审计缺少path')
        raw = raw.replace('\\', '/')
        for prefix in (workspace, str(self.root)):
            if isinstance(prefix, str) and prefix and (raw == prefix or raw.startswith(prefix.rstrip('/') + '/')):
                raw = raw[len(prefix.rstrip('/')):].lstrip('/') or '.'
                break
        path = Path(raw)
        if path.is_absolute() or ':' in raw or '..' in path.parts:
            raise rr.RoundError('工具读取越出项目工作区')
        relative = path.as_posix()
        first = path.parts[0] if path.parts else ''
        if (first in {'开发者说明', '开发者功能', '.backup', '.operit', '.round-runtime', 'Operit世界书导出',
                      '日志', '__pycache__', 'vosi', '语音仓库'}
                or any('.into-backup-' in part for part in path.parts)):
            raise rr.RoundError('工具读取了非运行数据源: ' + relative)
        self.store._path(relative)
        return relative

    def _verify_audit(self, key, proof):
        context = json.loads(self._blob(key, '.context.json').read_bytes())
        if context.get('entry_mode') == ir.MODE:
            return ir.verify(self, key, proof)
        if context.get('protocol') != STORY_PROTOCOL or context.get('reading_policy', {}).get('version') != sr.VERSION:
            raise rr.RoundError('旧读取任务需显式重试以刷新正文提取契约')
        if not isinstance(proof, dict) or proof.get('api') != 'Tools.Chat.sendMessageStreaming':
            raise rr.RoundError('缺少Operit正式会话工具审计，未提交')
        outcome = proof.get('outcome', {})
        if not isinstance(outcome, dict):
            raise rr.RoundError('正式会话回执无效')
        assistant = outcome.get('assistant', {})
        if (outcome.get('type') != 'committed' or outcome.get('status') != 'completed'
                or not isinstance(assistant, dict) or type(assistant.get('messageTimestamp')) is not int
                or proof.get('snapshot_message_timestamp') != assistant.get('messageTimestamp')
                or not isinstance(proof.get('chat_id'), str) or not proof['chat_id']
                or not isinstance(proof.get('participant_id'), str) or not proof['participant_id']):
            raise rr.RoundError('正式会话未完成或消息快照不匹配')
        tools = proof.get('tools')
        if not isinstance(tools, list) or not 1 <= len(tools) <= 128:
            raise rr.RoundError('文件工具调用数须为1至128')
        passes = proof.get('read_passes')
        repair_keys = proof.get('repair_keys', [])
        if (not isinstance(repair_keys, list) or len(repair_keys) > 64
                or not all(isinstance(item, str) for item in repair_keys)
                or len(set(repair_keys)) != len(repair_keys)):
            raise rr.RoundError('补读必需key清单无效')
        if passes is not None:
            if not isinstance(passes, list) or not 1 <= len(passes) <= 2:
                raise rr.RoundError('正式会话补读阶段须为1至2次')
            cursor, timestamps = 0, set()
            for stage in passes:
                if not isinstance(stage, dict):
                    raise rr.RoundError('正式会话补读回执无效')
                receipt = stage.get('outcome', {})
                timestamp = stage.get('snapshot_message_timestamp')
                count = stage.get('tool_count')
                if (not isinstance(receipt, dict) or receipt.get('type') != 'committed'
                        or receipt.get('status') != 'completed'
                        or not isinstance(receipt.get('assistant'), dict)
                        or type(timestamp) is not int or timestamp in timestamps
                        or receipt['assistant'].get('messageTimestamp') != timestamp
                        or type(stage.get('tool_start')) is not int or stage['tool_start'] != cursor
                        or type(count) is not int or count < 1):
                    raise rr.RoundError('正式会话补读回执或工具范围不符')
                timestamps.add(timestamp)
                cursor += count
            if (cursor != len(tools) or passes[-1]['outcome'] != outcome
                    or passes[-1]['snapshot_message_timestamp'] != proof['snapshot_message_timestamp']):
                raise rr.RoundError('补读累计工具或最终快照不符')
            if repair_keys and len(passes) != 2:
                raise rr.RoundError('补读必需key缺少第二次完成回执')
        elif repair_keys:
            raise rr.RoundError('补读必需key缺少分阶段回执')

        bundle = context['reading_bundle']
        allowed_projections = {item['path'] for item in bundle['entries'].values()}
        records, browse = [], set()
        for call in tools:
            if not isinstance(call, dict) or call.get('name') not in READONLY_TOOLS:
                raise rr.RoundError('会话调用了白名单之外的工具')
            name, params = call['name'], call.get('parameters')
            if not isinstance(params, dict):
                raise rr.RoundError('工具审计参数无效')
            relative = self._audit_path(params.get('path'), proof.get('workspace'))
            if relative == sr.CACHE or relative.startswith(sr.CACHE + '/'):
                current_directory = sr.CACHE + '/' + bundle['nonce']
                if relative not in allowed_projections and not (name == 'list_files' and relative == current_directory):
                    raise rr.RoundError('读取了非本次任务提取件')
            text = call.get('result_text')
            if not isinstance(text, str) or len(text.encode('utf-8')) > 1024 * 1024:
                raise rr.RoundError('工具结果审计文本无效')
            record = {'name': name, 'path': relative, 'status': call.get('status'),
                      'part_id': call.get('part_id'), 'result_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
            if call.get('status') == 'success' and name in READ_TOOLS:
                source = self.store._path(relative)
                if not source.is_file():
                    raise rr.ConflictError('读取过的资料已删除，请重新生成: ' + relative)
                raw = source.read_bytes()
                begin, end = 1, len(raw.decode('utf-8').splitlines())
                if name == 'read_file_part':
                    try:
                        begin = int(params.get('start_line', 1))
                        end = int(params.get('end_line', begin + 99))
                    except (TypeError, ValueError):
                        raise rr.RoundError('分段读取行号无效')
                try:
                    line_numbers = sr.verified_lines(raw, text, begin, end)
                except (ValueError, OSError) as exc:
                    raise rr.RoundError('实际读取正文未核验: ' + str(exc)) from exc
                record.update(verified_lines=line_numbers, source_sha256_at_result=hashlib.sha256(raw).hexdigest())
            if call.get('status') == 'success' and name == 'list_files':
                browse.add(relative)
            records.append(record)
        try:
            sr.check_required(context['reading_policy'], records)
            sr.verify_bundle(self.root, bundle)
        except (ValueError, OSError) as exc:
            raise rr.RoundError('正文读取校验未通过: ' + str(exc)) from exc
        if not set(context['reading_policy']['required_browse']) <= browse:
            raise rr.RoundError('本轮未重新浏览规则、知识库及存档目录')
        self._source_check(context)
        return {**{k: proof.get(k) for k in ('api', 'chat_id', 'participant_id', 'workspace', 'outcome',
                                           'snapshot_message_timestamp', 'started_at', 'completed_at')},
                'verified_tools': records, 'tool_count': len(records), 'required_reads_verified': True,
                'read_passes': passes, 'repair_keys': repair_keys}

    def _source_check(self, context):
        for relative, expected in context['audit'].items():
            source = self.store._path(relative)
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise rr.ConflictError('生成期间规则或存档已改变，请显式重试: ' + relative)

    @staticmethod
    def _read_coverage(records):
        ranges = {}
        for record in records:
            if record['status'] == 'success' and record['name'] in READ_TOOLS:
                ranges.setdefault(record['path'], set()).update(record.get('verified_lines', []))
        result = {}
        for path, lines in ranges.items():
            reached = 0
            while reached + 1 in lines:
                reached += 1
            result[path] = reached
        return result

    def _relationship_facts(self, records):
        spans = []
        for record in records:
            if record['path'] != rq.VIEW or record['status'] != 'success' or record['name'] not in READ_TOOLS:
                continue
            spans.extend((line, line) for line in record.get('verified_lines', []))
        if not spans:
            return {}
        if not any(begin <= 1 <= end for begin, end in spans):
            raise rr.RoundError('关系查询缺少第1行元数据读取')
        try:
            registry = rq.RelationshipRegistry(self.root)
            rows = registry.verify_view()
        except (ValueError, OSError) as exc:
            raise rr.RoundError('关系查询来源或视图无效: ' + str(exc)) from exc
        digest = hashlib.sha256(self.store._path(rq.VIEW).read_bytes()).hexdigest()
        result = {}
        for line, row in enumerate(rows[1:], 2):
            if any(begin <= line <= end for begin, end in spans):
                result[row['key']] = {'path': rq.VIEW, 'sha256': digest, 'covered_lines': [1, line],
                                      'source': registry.source, 'scope': 'query_row'}
        for prefix in ('lore.称谓', 'lore.知情'):
            keys = [key for key in result if key.startswith(prefix + '.')]
            if keys:
                result[prefix] = {'path': rq.VIEW, 'sha256': digest, 'scope': 'query_rows',
                                  'keys': keys, 'covered_lines': sorted({1} | {result[k]['covered_lines'][1] for k in keys}),
                                  'source': registry.source}
        return result

    def _bridge_facts(self, context, audit, enforce_required=True):
        if audit.get('required_reads_verified') is not True:
            raise rr.RoundError('缺少已核验的正式会话审计')
        self._source_check(context)
        records = audit['verified_tools']
        coverage = self._read_coverage(records)
        available, fingerprints = {}, {}
        mapped = {rr.FILES[0]: 'state.memory', RULES[0]: 'contract.inject',
                  RULES[1]: 'gate.V1', rr.FILES[1]: 'item.catalog',
                  'txt文件/事件注册表.json': 'contract.events'}
        for relative, reached in coverage.items():
            path = self.store._path(relative)
            raw = path.read_bytes()
            text = raw.decode('utf-8')
            through = len(text.splitlines())
            if relative == RULES[0]:
                through = len(text.split('【手动Python入口开始】', 1)[0].splitlines())
            if reached < through:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            fingerprints[relative] = digest
            keys = []
            if relative in mapped:
                keys.append(mapped[relative])
            elif relative.startswith('txt文件/知识库/') and path.suffix == '.json':
                obj = rr.load_request(text)
                items = obj.get('data', {}).get('entries', []) or obj.get('entries', [])
                for entry in items:
                    match = re.search(r'※索引key※\s*([\w.]+)', entry.get('content', ''))
                    name = entry.get('name', '').split('（', 1)[0]
                    key = match.group(1) if match else name
                    if re.fullmatch(r'(char|lore|narrative|sys)\.[\w]+', key):
                        keys.append(key)
            for key in keys:
                if key in available:
                    raise rr.RoundError('读取来源包含重复key: ' + key)
                available[key] = {'path': relative, 'sha256': digest, 'through_line': through}
        try:
            projected = sr.projection_facts(self.root, context['reading_bundle'], records)
        except (ValueError, OSError) as exc:
            raise rr.RoundError('提取来源不可核验: ' + str(exc)) from exc
        available.update(projected)
        for required in context['reading_policy']['required_reads']:
            alternative = required.get('source_alternative')
            if alternative and required['key'] not in available:
                spans = [(n,n) for record in records if record['path'] == alternative['path']
                         for n in record.get('verified_lines', [])]
                if all(sr._covers(spans, a, b) for a, b in alternative['ranges']):
                    available[required['key']] = {'path': alternative['path'], 'sha256': alternative['sha256'],
                        'scope': 'selected_source_ranges', 'covered_ranges': alternative['ranges']}
                    fingerprints[alternative['path']] = alternative['sha256']
        for item in projected.values():
            for source in item['sources']:
                fingerprints[source['path']] = source['sha256']
        relationship_facts = self._relationship_facts(records)
        available.update(relationship_facts)
        if relationship_facts:
            fingerprints[rq.VIEW] = hashlib.sha256(self.store._path(rq.VIEW).read_bytes()).hexdigest()
            fingerprints[rq.SOURCE] = hashlib.sha256(self.store._path(rq.SOURCE).read_bytes()).hexdigest()
        required_keys = sorted({key for key, item in context['reading_bundle']['entries'].items() if item.get('always_required')}
                               | set(audit.get('repair_keys', [])))
        if enforce_required and not set(required_keys) <= available.keys():
            raise rr.RoundError('本轮缺必需正文: ' + ', '.join(sorted(set(required_keys) - available.keys())))
        return {'required_reads_verified': True, 'available_keys': available, 'enforced_keys': required_keys,
                'source_fingerprints': fingerprints, 'memory': context['assembly_memory'],
                'read_call_count': sum(record['name'] in READ_TOOLS for record in records)}

    def _assemble_result(self, key, job):
        text = self._blob(key, '.result.txt').read_text(encoding='utf-8')
        result = rr.load_request(text)
        if not isinstance(result, dict):
            raise rr.RoundError('模型结果必须为JSON对象')
        context_path = self._blob(key, '.context.json')
        context = json.loads(context_path.read_bytes())
        if context.get('reading_policy', {}).get('version') != sr.VERSION:
            raise rr.RoundError('任务使用旧读取契约，请显式重试以刷新正文提取目录')
        assembly = self._blob(key, '.assembled.json')
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        context_digest = hashlib.sha256(context_path.read_bytes()).hexdigest()
        if context.get('entry_mode') == ir.MODE:
            if assembly.is_file():
                saved = rr.load_request(assembly.read_text(encoding='utf-8'))
                if saved.get('result_sha256') != digest or saved.get('context_sha256') != context_digest:
                    raise rr.ConflictError('保存的互动结果与本次任务不符')
                return saved['payload']
            audit = rr.load_request(self._blob(key, '.read-audit.json').read_text(encoding='utf-8'))
            payload = ir.assemble(self, key, job, result, context, audit)
            rr._atomic(assembly, rr._json({'result_sha256': digest, 'context_sha256': context_digest, 'payload': payload}))
            return payload
        if assembly.is_file():
            saved = rr.load_request(assembly.read_text(encoding='utf-8'))
            if saved.get('result_sha256') != digest or saved.get('context_sha256') != context_digest:
                raise rr.ConflictError('保存的组装结果与本次任务不符')
            payload = saved['payload']
        else:
            if 'model_audit' in result:
                audit = rr.load_request(self._blob(key, '.read-audit.json').read_text(encoding='utf-8'))
                identity = {'schema_version': 1, **{field: job[field] for field in
                            ('request_id', 'base_revision', 'current_round')}}
                payload = rr._assemble_bridge_result(self.root, result, identity, self._bridge_facts(context, audit))
            else:
                payload = result
            for field, value in {'schema_version': 1, **{field: job[field] for field in
                                 ('request_id', 'base_revision', 'current_round')}}.items():
                if field not in payload or rr._json(payload[field]) != rr._json(value):
                    raise rr.RoundError('模型结果的' + field + '与任务不符')
            rr._atomic(assembly, rr._json({'result_sha256': digest, 'context_sha256': context_digest,
                                        'payload': payload}))
        with self.store._locked():
            if key not in self.store._ledger()['receipts']:
                self._source_check(context)
        return payload

    @staticmethod
    def _model(value):
        if value is None:
            return None
        fields = ('key', 'function_type', 'provider_id', 'provider_name', 'model_id')
        if (not isinstance(value, dict) or any(not isinstance(value.get(k), str)
                or not value[k] or len(value[k]) > 512 for k in fields)
                or not isinstance(value.get('pricing_configured'), bool)):
            raise rr.RoundError('桥接模型信息无效')
        expected = json.dumps([value['function_type'], value['provider_id'], value['model_id']],
                              ensure_ascii=False, separators=(',', ':'))
        if value['key'] != expected:
            raise rr.RoundError('桥接模型标识不一致')
        return {k: value[k] for k in (*fields, 'pricing_configured')}

    @staticmethod
    def _model_key(body):
        value = body.get('model_key')
        if value is not None and (not isinstance(value, str) or not value or len(value) > 512):
            raise rr.RoundError('确认的模型标识无效')
        return value

    def create(self, body):
        if isinstance(body,dict) and body.get('entry_mode')==ir.MODE and sp.enabled(self.root):
            res = sp.create(self,body)
            task = (res or {}).get('task') or {}
            status = task.get('status')
            self.hub.publish('committed' if status == 'committed' else 'task_state',
                             {'request_id': task.get('request_id'), 'status': status},
                             wake_worker=(status == 'queued'))
            return res
        self.start()
        if (not isinstance(body, dict) or not {'request_id', 'base_revision', 'action'} <= set(body)
                or set(body) - {'request_id', 'base_revision', 'action', 'model_key', 'entry_mode', 'operation', 'save_epoch', 'selection'}):
            raise rr.RoundError('提交须包含request_id、base_revision和action，可附确认的model_key')
        model_key = self._model_key(body)
        mode, command = body.get('entry_mode'), body.get('operation')
        selected = body.get('selection')
        if mode not in (None, ir.MODE) or ((command is not None or selected is not None) and mode != ir.MODE):
            raise rr.RoundError('请求入口与操作不符')
        key, revision, action = body['request_id'], body['base_revision'], body['action']
        epoch = body.get('save_epoch')
        if mode == ir.MODE and (epoch != self._save_epoch() or not isinstance(action, str) or len(action) > 2000):
            raise rr.ConflictError('新档标识或输入长度无效，请恢复当前存档再提交')
        if not isinstance(key, str) or not rr.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', key):
            raise rr.RoundError('请求标识无效')
        if not isinstance(action, str) or not action.strip() or len(action) > 4000:
            raise rr.RoundError('行动须为1至4000字')
        with self.store._locked():
            state = self._read()
            if key in state['jobs']:
                job = state['jobs'][key]
                if job['action'] != action or job['base_revision'] != revision or job.get('model_key') != model_key or job.get('entry_mode') != mode or job.get('operation') != command or job.get('selection') != selected or (mode == ir.MODE and job.get('save_epoch') != epoch):
                    raise rr.ConflictError('同一请求标识不能提交不同行动')
                return {'task': self._public(job)}
        prepared = self.store.prepare()
        if prepared['base_revision'] != revision:
            raise rr.ConflictError('场景已更新，请重新载入后提交；原行动已保留')
        if mode == ir.MODE:
            ir.selection(self.root, self.store._files(), selected, action, command)
        context = self._context(prepared, key, action, entry_mode=mode, command=command, selected=selected)
        with self.store._locked():
            state = self._read()
            self._expire(state)
            if key in state['jobs']:
                job = state['jobs'][key]
                if job['action'] != action or job['base_revision'] != revision or job.get('model_key') != model_key or job.get('entry_mode') != mode or job.get('operation') != command or job.get('selection') != selected or (mode == ir.MODE and job.get('save_epoch') != epoch):
                    raise rr.ConflictError('请求标识已用于不同行动')
                return {'task': self._public(job)}
            latest = state['jobs'].get(state['latest'])
            if latest and latest['status'] in ACTIVE:
                raise rr.ConflictError('已有行动正在处理，请等待完成')
            if rr._revision(self.store._files()) != revision or (mode == ir.MODE and self._save_epoch() != epoch):
                raise rr.ConflictError('准备期间场景或新档标识已改变，请重新载入')
            if mode == ir.MODE:
                ir.selection(self.root, self.store._files(), selected, action, command)
            job = {'request_id': key, 'base_revision': revision, 'action': action,
                   'current_round': prepared['current_round'], 'status': 'queued',
                   'attempt': 0, 'created_at': time.time(), 'error': '', 'lease': None,
                   'timing': {}, 'model_key': model_key, 'entry_mode': mode, 'operation': command, 'save_epoch': epoch, 'selection': selected,
                    'cost_preview': context.get('cost_preview'),
                   'before_panel': '\n'.join(line for line in
                       (prepared['snapshot'][rr.FILES[0]] or '').split('▶ 上回合历史快照', 1)[0].splitlines()
                       if line.lstrip().startswith(('[系统宿主]', '[沈知韫]', '[徐念薇]', '[苏婉青]')))}
            rr._atomic(self._blob(key, '.context.json'), rr._json(context))
            state['jobs'][key] = job
            state['latest'] = key
            self._write(state)
            pub = {'task': self._public(job)}
        self.hub.publish('task_state', {'request_id': key, 'status': 'queued'}, wake_worker=True)
        return pub

    def retry(self, key, body=None):
        self.start()
        with self.store._locked():
            existing=self._read()['jobs'].get(key)
        if existing and existing.get('reservation'):
            res = sp.retry(self,key,body or {})
            task = (res or {}).get('task') or {}
            self.hub.publish('task_state', {'request_id': task.get('request_id'), 'status': task.get('status')},
                             wake_worker=(task.get('status') == 'queued'))
            return res
        model_key = self._model_key(body or {})
        with self.store._locked():
            state = self._read()
            self._expire(state)
            job = state['jobs'].get(key)
            if job is None:
                abort(404)
            latest = state['jobs'].get(state['latest'])
            if latest and latest['request_id'] != key and latest['status'] in ACTIVE:
                raise rr.ConflictError('另一行动正在处理')
            if job['status'] in ACTIVE or job['status'] == 'committed':
                return {'task': self._public(job)}
            original = dict(job)
        prepared = self.store.prepare()
        if prepared['base_revision'] != original['base_revision']:
            raise rr.ConflictError('该行动基于旧场景，请重新载入后重新提交')
        context = self._context(prepared, key, original['action'], original.get('error', ''),
                                entry_mode=original.get('entry_mode'), command=original.get('operation'), selected=original.get('selection'))
        with self.store._locked():
            state = self._read()
            self._expire(state)
            job = state['jobs'][key]
            if job['status'] in ACTIVE or job['status'] == 'committed':
                return {'task': self._public(job)}
            latest = state['jobs'].get(state['latest'])
            if latest and latest['request_id'] != key and latest['status'] in ACTIVE:
                raise rr.ConflictError('准备期间另一行动已开始')
            if (job != original or rr._revision(self.store._files()) != original['base_revision']):
                raise rr.ConflictError('准备期间任务或场景已更新，请检查最新状态')
            if job.get('before_panel') is None:
                memory = prepared['snapshot'][rr.FILES[0]] or ''
                job['before_panel'] = '\n'.join(line for line in
                    memory.split('▶ 上回合历史快照', 1)[0].splitlines()
                    if line.lstrip().startswith(('[系统宿主]', '[沈知韫]', '[徐念薇]', '[苏婉青]')))
            job['model_key'] = model_key
            # A retry keeps action and base identity, but reads current rules and feedback.
            rr._atomic(self._blob(key, '.context.json'), rr._json(context))
            self._blob(key, '.assembled.json').unlink(missing_ok=True)
            job.pop('generation_model', None)
            job.update(status='queued', error='', lease=None, cost_preview=context.get('cost_preview'))
            state['latest'] = key
            self._write(state)
            pub = {'task': self._public(job)}
        self.hub.publish('task_state', {'request_id': key, 'status': 'queued'}, wake_worker=True)
        return pub

    def bridge_info(self):
        with self.store._locked():
            path = self._path('bridge-key.json')
            if not path.exists():
                rr._atomic(path, rr._json({'token': secrets.token_urlsafe(32)}))
            return json.loads(path.read_bytes())

    def authorize(self, token):
        path = self._path('bridge-key.json')
        if not path.is_file() or not token:
            abort(403)
        if not hmac.compare_digest(str(token), str(json.loads(path.read_bytes())['token'])):
            abort(403)

    def _pending_flags(self):
        has_task = False
        has_control = False
        with self.store._locked():
            state = self._read()
            self._expire(state)
            job = state['jobs'].get(state['latest'])
            if job and job.get('status') == 'queued':
                has_task = True
            if not has_task and not any(j['status'] in ACTIVE for j in state['jobs'].values()):
                cur_epoch = self._save_epoch()
                iq_store = self._read_inquiries()
                if any(isinstance(it, dict) and it.get('status') == 'queued' and it.get('save_epoch') == cur_epoch
                       for it in (iq_store.get('items') or {}).values()):
                    has_task = True
            cmd = self._bridge_view(state).get('control')
            if cmd and cmd.get('status') == 'requested':
                has_control = True
        if not has_task:
            experimental = getattr(self, 'experimental', None)
            if experimental is not None:
                with experimental.lock, experimental.db() as db:
                    experimental.expire(db)
                    if db.execute("SELECT 1 FROM jobs WHERE status='queued' LIMIT 1").fetchone():
                        has_task = True
        return has_task, has_control

    def worker_wait(self, since_seq=0, timeout=25.0):
        self.start()
        has_task, has_control = self._pending_flags()
        if has_task or has_control:
            seq = self.hub.worker_seq
            reason = 'task' if has_task else 'control'
            return {'wake': True, 'reason': reason, 'seq': seq, 'worker_seq': seq,
                    'has_task': has_task, 'has_control': has_control, 'service_epoch': self.service_epoch}
        seq = self.hub.wait_worker(since_seq, timeout=timeout)
        has_task, has_control = self._pending_flags()
        wake = has_task or has_control or seq > since_seq
        reason = 'task' if has_task else ('control' if has_control else ('event' if seq > since_seq else 'timeout'))
        return {'wake': wake, 'reason': reason, 'seq': seq, 'worker_seq': seq,
                'has_task': has_task, 'has_control': has_control, 'service_epoch': self.service_epoch}

    def claim(self, body=None):
        self.start()
        model = self._model((body or {}).get('model'))
        with self.store._locked():
            state = self._read()
            self._expire(state)
            state['bridge_seen'] = time.time()
            state['bridge_model'] = model
            job = state['jobs'].get(state['latest'])
            if not job or job['status'] != 'queued':
                self._write(state)
                return {'task': None}
            if (rr._revision(self.store._files()) != job.get('working_revision',job['base_revision'])
                    or (job.get('entry_mode') == ir.MODE and job.get('save_epoch') != self._save_epoch())):
                if job.get('reservation'):
                    sp.refund(self,state,job,'conflict','场景版本已改变，旧行动未生成。')
                else: job.update(status='conflict', error='场景版本已改变，未生成或写入旧行动')
                self._write(state)
                return {'task': None}
            # Submission model hints do not constrain a queued task.
            job['generation_model'] = model
            timing = dict(job.get('timing') or {})
            timing['queue_ms'] = max(0, round((time.time() - job.get('created_at', time.time())) * 1000))
            timing['model_id'] = model['model_id'] if model else ''
            job['timing'] = timing
            job['claimed_at'] = time.time()
            context = json.loads(self._blob(job['request_id'], '.context.json').read_text(encoding='utf-8'))
            if (context.get('protocol') != STORY_PROTOCOL or context.get('reading_policy', {}).get('version') != sr.VERSION
                    or (context.get('entry_mode') == ir.MODE and context.get('interaction_protocol') != (3 if sp.enabled(self.root) else 2))):
                if job.get('reservation'):
                    sp.refund(self,state,job,'failed','任务来自旧入口，预扣已返还，请重试。')
                else: job.update(status='failed', lease=None, error='任务来自旧入口，请显式重试以刷新读取契约')
                self._write(state)
                return {'task': None}
            job.update(status='generating', lease=secrets.token_urlsafe(24),
                       lease_until=time.time() + LEASE_SECONDS, attempt=job['attempt'] + 1)
            self._write(state)
            self._clear_preview(job['request_id'])
            claimed = {'task': {'request_id': job['request_id'], 'lease': job['lease'],
                             'turns': context['turns'], 'model_key': model['key'] if model else None,
                              'previous_validation_error':context.get('previous_validation_error',''),
                              'service_epoch':self.service_epoch,'attempt':job['attempt'],'live_reading_revision':2,'action_contract_revision':1,
                              'material_delivery_revision': 1 if job.get('entry_mode') == ir.MODE else 0,
                              'material_delivery_v2': 1 if job.get('entry_mode') == ir.MODE else 0,
                              'dual_stage_protocol': 1 if job.get('entry_mode') == ir.MODE else 0,
                              'resume_stage2': bool(job.get('resume_stage2')),
                              'entry_mode': job.get('entry_mode'), 'save_epoch': self._save_epoch(),
                              'interaction_scope': context.get('interaction_scope'),
                              'packet_bytes': self.store._path(context['packet']['path']).stat().st_size if context.get('packet') else 0,
                              'story_protocol': STORY_PROTOCOL, 'reading_preflight': 1,
                              'round_identity': {'schema_version': 1, **{field: job[field] for field in
                                  ('request_id', 'base_revision', 'current_round')}}}}
        self.hub.publish('task_state', {'request_id': job['request_id'], 'status': 'generating'})
        return claimed

    def _leased(self, state, key, lease):
        job = state['jobs'].get(key)
        if (not job or not isinstance(lease, str) or not job.get('lease') or
                not hmac.compare_digest(job['lease'], lease)):
            raise rr.ConflictError('结果属于已失效任务，未写入')
        if job['status'] == 'generating' and job['lease_until'] < time.time():
            if job.get('reservation'):
                sp.refund(self,state,job,'interrupted','生成租约已过期，预扣已返还。')
            else: job.update(status='interrupted', lease=None, error='生成连接已过期，可重试')
            self._write(state)
            self._clear_preview(key)
            raise rr.ConflictError('生成租约已过期，结果未写入')
        return job

    def material(self, key, body):
        self.start()
        # continuity_hook: 桥接在重建会话时携带的续接钩子；本版只放行不参与资料生成，
        # 缺了它会让 material 交付整批 400，进而每次发言都失败。
        opt_keys = {'delivery_version', 'protocol_mode', 'synced_zone0_sha256',
                    'synced_zone1_sha256', 'last_committed_sequence', 'is_fresh_session',
                    'continuity_hook'}
        rr._keys(body, {'lease', 'chat_id', 'participant_id'} | opt_keys, '程序资料交付',
                 {'lease', 'chat_id', 'participant_id'})
        for field in ('chat_id', 'participant_id'):
            if not isinstance(body[field], str) or not 1 <= len(body[field]) <= 200:
                raise rr.RoundError('资料交付会话身份无效')
        with self.store._locked():
            state = self._read()
            job = self._leased(state, key, body['lease'])
            if job['status'] != 'generating' or job.get('entry_mode') != ir.MODE:
                raise rr.ConflictError('仅生成中的正式任务可领取资料')
            if body.get('delivery_version') == 2:
                return ir.material_delivery_v2(self, key, job, body['chat_id'], body['participant_id'], options=body)
            return ir.material_delivery(self, key, job, body['chat_id'], body['participant_id'])

    def stream_chunk(self, key, body):
        """Accept transient in-memory streaming preview nodes; never persists to RoundStore."""
        self.start()
        rr._keys(body, {'lease', 'stage', 'messages', 'revision'}, '流式预览', {'lease', 'stage'})
        stage = body['stage']
        if stage not in ('thinking', 'streaming', 'settling', 'settling_retry'):
            raise rr.RoundError('流式阶段无效')
        revision = body.get('revision', 0)
        if type(revision) is not int or revision < 0:
            raise rr.RoundError('流式版本号无效')
        raw_msgs = body.get('messages', [])
        if not isinstance(raw_msgs, list) or len(raw_msgs) > 1000:
            raise rr.RoundError('流式消息列表无效')
        with self.store._locked():
            state = self._read()
            job = self._leased(state, key, body['lease'])
            if job['status'] != 'generating' or job.get('entry_mode') != ir.MODE:
                raise rr.ConflictError('仅生成中的正式任务可推送流式预览')
            context = json.loads(self._blob(key, '.context.json').read_bytes())
            allowed_cast = set(context.get('cast', []))
            allow_player_dlg = ir.load_story_prefs(self.root)['protagonist_style'] == 'faithful'
        clean_msgs = []
        player_dlg_seen = 0
        for m in raw_msgs:
            if not isinstance(m, dict):
                continue
            kind, speaker, text = m.get('kind'), m.get('speaker', ''), m.get('text', '')
            if kind not in ('dialogue', 'action', 'narration') or not isinstance(speaker, str) or not isinstance(text, str):
                continue
            text = ir.sc.strip_preview_decision_leak(text.strip())
            if not text or len(text) > 4000:
                continue
            if kind == 'narration':
                speaker = ''
            elif kind == 'dialogue':
                if speaker == '徐志北':
                    if not allow_player_dlg or player_dlg_seen >= ir.sc.MAX_PLAYER_DIALOGUE_PER_TURN:
                        continue
                    player_dlg_seen += 1
                elif speaker not in allowed_cast:
                    continue
            elif kind == 'action' and speaker not in (allowed_cast | {'徐志北'}):
                continue
            clean_msgs.append({'kind': kind, 'speaker': speaker, 'text': text})
        preview = {'request_id': key, 'stage': stage, 'messages': clean_msgs,
                   'revision': revision, 'updated_at': time.time()}
        with self._stream_lock:
            old = self._stream_preview.get(key)
            if old and revision < old.get('revision', 0):
                return {'ok': True, 'ignored': True}
            self._stream_preview[key] = preview
        self.hub.publish('story_stream', preview)
        if clean_msgs and stage in ('streaming', 'settling'):
            self._trigger_tts_prewarm(clean_msgs[:5], dedup_prefix=key)
        return {'ok': True, 'count': len(clean_msgs)}

    def heartbeat(self, key, lease):
        with self.store._locked():
            state = self._read()
            job = self._leased(state, key, lease)
            if job['status'] == 'generating':
                job['lease_until'] = time.time() + LEASE_SECONDS
            state['bridge_seen'] = time.time()
            self._write(state)
            return {'status': job['status']}

    def preflight(self, key, body):
        """Validate real read receipts before commit; only return missing read locations."""
        self.start()
        rr._keys(body, {'lease', 'text', 'conversation_audit'}, '读取预检',
                 {'lease', 'text', 'conversation_audit'})
        with self.store._locked():
            state = self._read()
            job = self._leased(state, key, body.get('lease'))
            if job['status'] != 'generating':
                raise rr.ConflictError('仅生成中的任务可预检，原结果未替换')
        text = body['text']
        if not isinstance(text, str) or len(text.encode('utf-8')) > 4 * 1024 * 1024:
            raise rr.RoundError('模型结果须为4MiB内的JSON文本')
        result = rr.load_request(text)
        if not isinstance(result, dict):
            raise rr.RoundError('模型结果必须为JSON对象')
        context = json.loads(self._blob(key, '.context.json').read_bytes())
        if context.get('entry_mode') == ir.MODE:
            audit=ir.verify(self,key,body['conversation_audit'],allow_missing=True)
            if not audit['required_reads_verified']:
                return {'ready':False,'missing_keys':audit['missing_keys'],'read_targets':audit['read_targets']}
        else:audit = self._verify_audit(key, body['conversation_audit'])
        if context.get('entry_mode') == ir.MODE:
            payload = ir.assemble(self, key, job, result, context, audit)
            with self.store._locked():
                ir.validate(self.root, payload, self.store._files())
            return {'ready': True, 'missing_keys': [], 'read_targets': []}
        facts = self._bridge_facts(context, audit, enforce_required=False)
        if 'model_audit' not in result:
            return {'ready': True, 'missing_keys': [], 'read_targets': []}
        model_audit = result['model_audit']
        fields = {'intent', 'scene', 'required_keys', 'evidence', 'v1', 'task', 'breakout'}
        rr._keys(model_audit, fields | {'notes'}, 'model_audit', fields)
        requested = model_audit['required_keys']
        if (not isinstance(requested, list) or len(requested) > 64
                or not all(isinstance(item, str) for item in requested)
                or len(set(requested)) != len(requested)):
            raise rr.RoundError('required_keys须为不重复的key数组')
        evidence = model_audit['evidence']
        if not isinstance(evidence, dict):
            raise rr.RoundError('model_audit.evidence须为对象')
        nodes = result.get('story_nodes')
        if not isinstance(nodes, list):
            raise rr.RoundError('story_nodes须为数组')
        speakers = {'char.' + node['speaker'] for node in nodes
                    if isinstance(node, dict) and node.get('type') == 'dialogue'
                    and node.get('speaker') in {'徐志北', '沈知韫', '徐念薇', '苏婉青', '徐承邺'}}
        required = ({'state.memory', 'contract.inject', 'gate.V1'} | set(requested)
                    | set(facts['enforced_keys']) | speakers | set(evidence))
        missing = sorted(required - facts['available_keys'].keys())
        locations = []
        bundle = context['reading_bundle']['entries']
        queries = context['reading_policy']['relationship_queries']
        originals = {'state.memory': rr.FILES[0], 'gate.V1': RULES[1],
                     'item.catalog': rr.FILES[1],
                     'contract.events': 'txt文件/事件注册表.json'}
        for item in missing:
            if item in bundle:
                entry = bundle[item]
                reads = [{'path': entry['path'], 'start_line': 1, 'end_line': entry['through_line']}]
            elif item in queries['key_lines']:
                reads = [{'path': queries['path'], 'start_line': line, 'end_line': line}
                         for line in (queries['header_line'], queries['key_lines'][item])]
            elif item in originals:
                path = originals[item]
                reads = [{'path': path, 'start_line': 1,
                          'end_line': len(self.store._path(path).read_text(encoding='utf-8').splitlines())}]
            else:
                raise rr.RoundError('未找到必需key的读取位置，请按当前索引核对具体key: ' + item)
            locations.append({'key': item, 'reads': reads})
        return {'ready': not missing, 'missing_keys': missing, 'read_targets': locations}



    def result(self, key, body):
        self.start()
        timing_update = body.get('timing', {})
        int_timing = {'generation_ms', 'settlement_ms', 'preflight_ms', 'generation_passes', 'settlement_passes'}
        str_timing = {'settlement_model_id'}
        allowed_timing = int_timing | str_timing
        if (not isinstance(timing_update, dict) or set(timing_update) - allowed_timing
                or any(type(timing_update.get(k)) is not int or not 0 <= timing_update[k] <= 3600000
                       for k in int_timing if k in timing_update)
                or ('generation_passes' in timing_update and not 0 <= timing_update['generation_passes'] <= 2)
                or ('settlement_passes' in timing_update and not 1 <= timing_update['settlement_passes'] <= 4)
                or any(not isinstance(timing_update.get(k), str) or len(timing_update[k]) > 256
                       for k in str_timing if k in timing_update)):
            raise rr.RoundError('耗时统计字段无效')
        allow_settlement_retry = bool(body.get('allow_settlement_retry'))
        stage1_fallback = None
        with self.store._locked():
            state = self._read()
            job = self._leased(state, key, body.get('lease'))
            if job['status'] == 'committed':
                return {'task': self._public(job)}
            if job['status'] not in {'generating', 'validating'}:
                raise rr.ConflictError('任务已结束，结果未写入')
            if body.get('error') and job['status'] == 'validating':
                raise rr.ConflictError('已有待提交结果，不能替换为错误')
            if body.get('error'):
                saved_cp = False
                if job.get('entry_mode') == ir.MODE and isinstance(body.get('stage1_checkpoint'), dict):
                    try:
                        context = json.loads(self._blob(key, '.context.json').read_bytes())
                        saved_cp = ir.save_stage1_checkpoint(self, key, job, context, body['stage1_checkpoint'])
                    except Exception:
                        saved_cp = False
                if not saved_cp:
                    ir.clear_stage1_checkpoint(self, key)
                job['has_stage1_checkpoint'] = bool(saved_cp)
                job['resume_stage2'] = False
                if job.get('reservation'):
                    sp.refund(self,state,job,'failed','模型生成失败，预扣已返还：'+str(body['error'])[:500])
                else: job.update(status='failed', error='模型生成失败：' + str(body['error'])[:500], lease=None)
                self._write(state)
                self._clear_preview(key)
                pub = {'task': self._public(job)}
                self.hub.publish('task_state', {'request_id': key, 'status': job['status']})
                return pub
            text = body.get('text')
            if not isinstance(text, str) or len(text.encode('utf-8')) > 4 * 1024 * 1024:
                raise rr.RoundError('模型结果须为4MiB内的JSON文本')
            if timing_update:
                job['timing'].update(timing_update)
                job['returned_at'] = time.time()
                job['validation_started_at'] = job['returned_at']
            if job['status'] == 'validating':
                if self._blob(key, '.result.txt').read_text(encoding='utf-8') != text:
                    raise rr.ConflictError('同一任务已有待提交结果，不得更换')
            else:
                try:
                    audit = self._verify_audit(key, body.get('conversation_audit'))
                except rr.RoundError as exc:
                    ir.clear_stage1_checkpoint(self, key)
                    job['has_stage1_checkpoint'] = False
                    job['resume_stage2'] = False
                    if job.get('reservation'):
                        sp.refund(self,state,job,'conflict' if isinstance(exc,rr.ConflictError) else 'failed','读取校验未通过，预扣已返还：'+str(exc))
                    else: job.update(status='conflict' if isinstance(exc, rr.ConflictError) else 'failed',
                               error='读取校验未通过：' + str(exc), lease=None)
                    self._write(state)
                    self._clear_preview(key)
                    pub = {'task': self._public(job)}
                    self.hub.publish('task_state', {'request_id': key, 'status': job['status']})
                    return pub
                parsed_dual = None
                if job.get('entry_mode') == ir.MODE:
                    try:
                        maybe_parsed = rr.load_request(text)
                        if isinstance(maybe_parsed, dict) and maybe_parsed.get('dual_stage_version') == 1:
                            parsed_dual = maybe_parsed
                    except rr.RoundError:
                        parsed_dual = None
                if allow_settlement_retry and job.get('entry_mode') == ir.MODE:
                    context = json.loads(self._blob(key, '.context.json').read_bytes())
                    try:
                        parsed = parsed_dual if parsed_dual is not None else rr.load_request(text)
                        if isinstance(parsed, dict) and parsed.get('dual_stage_version') == 1:
                            payload = ir.assemble(self, key, job, parsed, context, audit)
                            ir.validate(self.root, payload, self.store._files())
                    except rr.ConflictError:
                        raise
                    except rr.RoundError as exc:
                        msg = str(exc)
                        # Settlement-layer errors (or foreground missing ONLY the decision block after
                        # passing prose & redline guardrails) are safely retryable without re-running foreground.
                        if ir.is_settlement_retryable_error(msg):
                            return {'retryable_settlement': True, 'error': msg, 'task': self._public(job)}
                if parsed_dual is not None and isinstance(body.get('conversation_audit'), dict):
                    stage1_fallback = {
                        'foreground_text': parsed_dual.get('foreground_text', ''),
                        'generation_ms': timing_update.get('generation_ms', 0) if isinstance(timing_update, dict) else 0,
                        'base_audit': body.get('conversation_audit'),
                    }
                rr._atomic(self._blob(key, '.read-audit.json'), rr._json(audit))
                rr._atomic(self._blob(key, '.result.txt'), text.encode('utf-8'))
                job.update(status='validating', error='')
                self._write(state)
        return self._finish(key, stage1_fallback=stage1_fallback)

    def _finish(self, key, stage1_fallback=None):
        with self.store._locked():
            existing=self._read()['jobs'][key]
        if existing.get('reservation'):
            sp.finish(self,key)
            committed_msgs = []
            with self.store._locked():
                state = self._read()
                current = state['jobs'][key]
                if current['status'] == 'committed':
                    ir.clear_stage1_checkpoint(self, key)
                    current['has_stage1_checkpoint'] = False
                    current['resume_stage2'] = False
                    if current.get('returned_at'):
                        current.setdefault('timing', {})['acceptance_ms'] = max(0, round((time.time() - current['returned_at']) * 1000))
                        current['committed_at'] = time.time()
                    self._write(state)
                    try:
                        seg = ir.segment(self.root, self.store._files())
                        if seg and seg.get('messages'):
                            committed_msgs = seg['messages'][:5]
                    except Exception:
                        committed_msgs = []
                elif current['status'] == 'failed':
                    saved_cp = False
                    if stage1_fallback and ir.is_settlement_retryable_error(current.get('error', '')):
                        try:
                            context = json.loads(self._blob(key, '.context.json').read_bytes())
                            saved_cp = ir.save_stage1_checkpoint(self, key, current, context, stage1_fallback)
                        except Exception:
                            saved_cp = False
                    if not saved_cp:
                        ir.clear_stage1_checkpoint(self, key)
                    current['has_stage1_checkpoint'] = bool(saved_cp)
                    current['resume_stage2'] = False
                    self._write(state)
                elif current['status'] == 'conflict':
                    ir.clear_stage1_checkpoint(self, key)
                    current['has_stage1_checkpoint'] = False
                    current['resume_stage2'] = False
                    self._write(state)
                pub = {'task': self._public(current)}
            self._clear_preview(key)
            if committed_msgs:
                self._trigger_tts_prewarm(committed_msgs, dedup_prefix=key)
            self.hub.publish('committed' if current['status'] == 'committed' else 'task_state',
                             {'request_id': key, 'status': current['status']})
            return pub
        with self.store._locked():
            state = self._read()
            job = dict(state['jobs'][key])
        if job['status'] != 'validating':
            return {'task': self._public(job)}
        try:
            payload = self._assemble_result(key, job)
            context = json.loads(self._blob(key, '.context.json').read_bytes())
            read_audit = json.loads(self._blob(key, '.read-audit.json').read_bytes())
            baseline = dict(context['audit'])
            baseline.update({record['path']: record['source_sha256_at_result']
                             for record in read_audit['verified_tools'] if 'source_sha256_at_result' in record})
            receipt = self.store.submit(payload, _source_baseline=baseline)
            status, error = 'committed', ''
        except rr.ConflictError as exc:
            receipt, status, error = None, 'conflict', str(exc)
        except rr.RoundError as exc:
            receipt, status, error = None, 'failed', '回合校验未通过：' + str(exc)
        # Storage failures leave the saved result in validating for replay after recovery.
        committed_msgs = []
        with self.store._locked():
            state = self._read()
            current = state['jobs'][key]
            if current['status'] == 'validating':
                current.update(status=status, error=error, receipt=receipt)
                if current.get('returned_at'):
                    current.setdefault('timing', {})['acceptance_ms'] = max(0, round((time.time() - current['returned_at']) * 1000))
                    current['committed_at'] = time.time()
                self._write(state)
            if current['status'] == 'committed':
                try:
                    seg = ir.segment(self.root, self.store._files())
                    if seg and seg.get('messages'):
                        committed_msgs = seg['messages'][:5]
                except Exception:
                    committed_msgs = []
            pub = {'task': self._public(current)}
        self._clear_preview(key)
        if committed_msgs:
            self._trigger_tts_prewarm(committed_msgs, dedup_prefix=key)
        self.hub.publish('committed' if current['status'] == 'committed' else 'task_state',
                         {'request_id': key, 'status': current['status']})
        return pub


def register_story_routes(app, root, *, tts_prewarmer=None):
    service = StoryService(root, tts_prewarmer=tts_prewarmer)
    app.extensions['story_service'] = service

    @app.before_request
    def story_request_boundary():
        if not request.path.startswith('/api/story/'):
            return None
        service._reset_guard()
        if urlsplit('http://' + request.host).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            abort(403)
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            abort(403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            abort(403)
        if '/worker/' in request.path:
            service.authorize(request.headers.get('X-Story-Bridge'))
        elif request.method != 'GET' and request.headers.get('X-Story-Client') != '1':
            abort(403)
        if request.method not in ('GET', 'DELETE') and not request.is_json:
            abort(415)

    @app.after_request
    def story_no_cache(response):
        if request.path.startswith('/api/story/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(HTTPException)
    def story_http_error(exc):
        if not request.path.startswith('/api/story/'):
            return exc
        response = exc.get_response()
        messages = {403: '故事服务拒绝请求，请检查本地连接后重试。',
                    404: '任务或接口不存在，原行动已保留。请检查最新场景后重试。',
                    405: '故事接口不支持此请求方式。',
                    415: '故事请求须使用JSON格式。'}
        payload = jsonify(error=messages.get(exc.code, '故事服务请求失败，请稍后重试。'),
                          status=exc.code)
        response.set_data(payload.get_data())
        response.content_type = 'application/json'
        return response

    @app.errorhandler(rr.RoundError)
    def story_error(exc):
        return jsonify(error=str(exc)), 409 if isinstance(exc, rr.ConflictError) else 400

    @app.errorhandler(500)
    def story_internal_error(exc):
        if not request.path.startswith('/api/story/'):
            return exc
        return jsonify(error='本地故事服务内部异常，请检查日志后重试。', status=500), 500

    def body():
        value = rr.load_request(request.get_data(as_text=True))
        if not isinstance(value, dict):
            raise rr.RoundError('请求必须是JSON对象')
        return value

    @app.get('/api/story/snapshot')
    def snapshot():
        return jsonify(service.snapshot())

    @app.post('/api/story/preferences')
    def story_preferences():
        return jsonify(service.update_preferences(body()))

    @app.post('/api/story/new-game')
    def new_game():
        return jsonify(service.new_game(body()))

    @app.get('/api/story/live')
    def interaction_snapshot():
        return jsonify(service.interaction_snapshot(request.args.get('before'), request.args.get('limit')))

    @app.get('/api/story/stream')
    def story_sse_stream():
        try:
            start_seq = int(request.args.get('since', service.hub.seq))
        except (TypeError, ValueError):
            start_seq = service.hub.seq

        @stream_with_context
        def generate():
            seq = start_seq
            yield f'event: ready\ndata: {json.dumps({"seq": seq}, ensure_ascii=False)}\n\n'
            try:
                while True:
                    missed, seq = service.hub.wait_client(seq, timeout=15.0)
                    if not missed:
                        yield ': keepalive\n\n'
                        continue
                    for item_seq, event_type, payload in missed:
                        data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                        yield f'id: {item_seq}\nevent: {event_type}\ndata: {data}\n\n'
            except GeneratorExit:
                return

        headers = {'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'}
        return Response(generate(), mimetype='text/event-stream', headers=headers)

    @app.post('/api/story/live/progress')
    def playback_progress():
        return jsonify(service.playback_progress(body()))

    @app.get('/api/story/tasks')
    def tasks():
        return jsonify(service.status())

    @app.get('/api/story/tasks/<key>')
    def task(key):
        return jsonify(service.status(key))

    @app.post('/api/story/tasks')
    def submit():
        return jsonify(service.create(body()))

    @app.post('/api/story/tasks/<key>/cancel')
    def cancel_task(key):
        res = sp.cancel(service, key)
        service._clear_preview(key)
        service.hub.publish('task_state', {'request_id': key, 'status': 'cancelled'})
        return jsonify(res)

    @app.post('/api/story/tasks/<key>/retry')
    def retry(key):
        return jsonify(service.retry(key, body()))

    @app.get('/api/story/shop')
    def shop():
        return jsonify(service.shop_view())

    @app.post('/api/story/shop/redeem')
    def shop_redeem():
        return jsonify(service.redeem_shop(body()))

    @app.post('/api/story/shop/inquire')
    def shop_inquire():
        return jsonify(service.inquire_shop(body()))

    @app.get('/api/story/shop/inquire/<iq_id>')
    def shop_inquiry_status(iq_id):
        return jsonify(service.shop_inquiry_status(iq_id))

    @app.delete('/api/story/shop/dynamic/<item_id>')
    def shop_dynamic_delete(item_id):
        payload = request.get_json(silent=True) if request.is_json else None
        if not isinstance(payload, dict):
            payload = {}
        if 'save_epoch' not in payload and request.args.get('save_epoch'):
            payload['save_epoch'] = request.args.get('save_epoch')
        return jsonify(service.delete_dynamic_shop_item(item_id, payload))

    @app.post('/api/story/task/claim')
    def task_claim():
        return jsonify(service.claim_task_reward(body()))

    @app.post('/api/story/passive/upgrade')
    def passive_upgrade():
        return jsonify(service.upgrade_passive(body()))

    @app.post('/api/story/intel/acquire')
    def intel_acquire():
        return jsonify(service.acquire_intel(body()))

    @app.post('/api/story/intel/leverage')
    def intel_leverage():
        return jsonify(service.toggle_leverage(body()))

    @app.get('/api/story/bridge-info')
    def bridge_info():
        return jsonify(service.bridge_info())

    @app.post('/api/story/bridge/control')
    def bridge_control():
        return jsonify(service.bridge_control(body()))

    @app.post('/api/story/worker/control')
    def worker_control():
        return jsonify(service.worker_control(body()))

    @app.get('/api/story/worker/wait')
    def worker_wait():
        try:
            since = int(request.args.get('since', 0))
        except (TypeError, ValueError):
            since = 0
        try:
            timeout = float(request.args.get('timeout', 25.0))
        except (TypeError, ValueError):
            timeout = 25.0
        return jsonify(service.worker_wait(since_seq=since, timeout=timeout))

    @app.post('/api/story/worker/claim')
    def claim():
        return jsonify(service.claim(body()))

    @app.post('/api/story/worker/shop-inquiry/claim')
    def worker_claim_shop_inquiry():
        payload = body() if request.get_data() else {}
        return jsonify(service.claim_shop_inquiry(payload))

    @app.post('/api/story/worker/shop-inquiry/<iq_id>/complete')
    def worker_complete_shop_inquiry(iq_id):
        return jsonify(service.complete_shop_inquiry(iq_id, body()))

    @app.post('/api/story/worker/<key>/material')
    def material(key):
        return jsonify(service.material(key, body()))

    @app.post('/api/story/worker/<key>/stream')
    def stream_chunk(key):
        return jsonify(service.stream_chunk(key, body()))

    @app.post('/api/story/worker/<key>/heartbeat')
    def heartbeat(key):
        return jsonify(service.heartbeat(key, body().get('lease')))

    @app.post('/api/story/worker/<key>/preflight')
    def preflight(key):
        return jsonify(service.preflight(key, body()))

    @app.post('/api/story/worker/<key>/result')
    def result(key):
        return jsonify(service.result(key, body()))

    from scene_chat import register_scene_routes
    service.experimental = register_scene_routes(app, root, service)

    return service
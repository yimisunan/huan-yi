"""Regression test suite covering P0 & P1 fixes from the full health audit."""
from pathlib import Path
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
import interaction_runtime as ir
import round_runtime as rr
import save_store
import story_compiler as sc
import story_progression as sp
import story_service as ss
from test_dual_stage_runtime import _make_workspace, _fg_script, _settlement_payload


def _load_cleaner_module():
    spec = importlib.util.spec_from_file_location('save_cleaner_mod', str(ROOT / '存档清理器.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _action_conditions(category='A', npc='沈知韫', scene='室内'):
    return {
        'intensity': category,
        'effective_progress': True,
        'scene': scene,
        'npc': npc,
        'action_changed': True,
        'stress_signals': 0,
        'breakout_triggered': [],
    }


class _Harness:
    def __init__(self, td: str, scenario_id: str | None = None):
        self.root = Path(td)
        _make_workspace(self.root)
        for extra in ('存档清理器.py', '存档开局随机盲盒.py'):
            if (ROOT / extra).is_file():
                shutil.copy2(ROOT / extra, self.root / extra)
        self.app = Flask(__name__)
        self.svc = ss.register_story_routes(self.app, self.root)
        self.client = self.app.test_client()
        self.token = self.client.get('/api/story/bridge-info').get_json()['token']
        self.cli_headers = {'X-Story-Client': '1'}
        self.wrk_headers = {'X-Story-Bridge': self.token}
        if scenario_id:
            live = self.client.get('/api/story/live').get_json()
            r = self.client.post('/api/story/new-game', headers=self.cli_headers, json={
                'request_id': 'init-' + scenario_id.replace('_', '-'),
                'save_epoch': live['save_epoch'],
                'confirm': 'new_game',
                'scenario_id': scenario_id,
            })
            assert r.status_code == 200, r.get_data(as_text=True)

    def complete_latest_playback(self):
        live = self.client.get('/api/story/live').get_json()
        if not live['history']:
            return live
        seg = live['history'][-1]
        pb = live.get('playback') or {}
        total = int(pb.get('total') or len(seg['messages']))
        if total > 0:
            r1 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
                'save_epoch': live['save_epoch'],
                'segment_id': seg['id'],
                'revealed': total,
                'completed': False,
                'catchup': True,
            })
            assert r1.status_code == 200, r1.get_data(as_text=True)
        r = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
            'save_epoch': live['save_epoch'],
            'segment_id': seg['id'],
            'revealed': total,
            'completed': True,
            'catchup': True,
        })
        assert r.status_code == 200, r.get_data(as_text=True)
        return self.client.get('/api/story/live').get_json()

    def create_action(self, request_id: str, option_id: str, text: str):
        live = self.client.get('/api/story/live').get_json()
        seg = live['history'][-1] if live['history'] else {}
        seg_id = seg.get('id', '')
        use_opt = 'CUSTOM'
        use_text = text
        if option_id in ('A', 'B', 'C') and not text:
            opt = next((o for o in (seg.get('decision', {}).get('options') or []) if o.get('id') == option_id), None)
            if opt:
                use_opt = option_id
                use_text = opt.get('text', '')
        r = self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': request_id,
            'base_revision': live['revision'],
            'save_epoch': live['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': use_text,
            'selection': {'segment_id': seg_id, 'option_id': use_opt},
        })
        assert r.status_code == 200, r.get_data(as_text=True)
        return r.get_json()['task']

    def claim(self, worker_id='w1'):
        r = self.client.post('/api/story/worker/claim', headers=self.wrk_headers, json={'worker_id': worker_id})
        assert r.status_code == 200, r.get_data(as_text=True)
        return r.get_json()['task']

    def material(self, task, *, is_fresh=True, synced_z0='', synced_z1='', synced_flags=None):
        r = self.client.post(f"/api/story/worker/{task['request_id']}/material", headers=self.wrk_headers, json={
            'lease': task['lease'],
            'chat_id': 'chat-rem-1',
            'participant_id': 'model:chat',
            'delivery_version': 2,
            'protocol_mode': 'dual_stream_v2',
            'is_fresh_session': is_fresh,
            'synced_zone0_sha256': synced_z0,
            'synced_zone1_sha256': synced_z1,
            'synced_zone1_flags': synced_flags or {},
            'last_committed_sequence': 0,
        })
        assert r.status_code == 200, r.get_data(as_text=True)
        return r.get_json()

    def audit(self, delivery, stamp=400):
        outcome = {
            'type': 'committed',
            'status': 'completed',
            'userMessageTimestamp': stamp,
            'assistant': {'messageTimestamp': stamp + 10},
        }
        return {
            'api': 'Tools.Chat.sendMessageStreaming',
            'chat_id': 'chat-rem-1',
            'participant_id': 'model:chat',
            'workspace': str(self.root),
            'outcome': outcome,
            'snapshot_message_timestamp': stamp + 10,
            'started_at': 1000,
            'completed_at': 2000,
            'read_passes': [{
                'outcome': outcome,
                'snapshot_message_timestamp': stamp + 10,
                'tool_start': 0,
                'tool_count': 0,
                'started_at': 1000,
                'completed_at': 2000,
            }],
            'repair_keys': [],
            'tools': [],
            'delivery': {**delivery['delivery'], 'user_message_timestamp': stamp},
            'settlement_audit': {
                'function_type': 'SUMMARY',
                'model_id': 'gemini-flash',
                'fallback': False,
                'attempts': 1,
                'duration_ms': 240,
            },
        }

    def submit_result(self, task, mat, fg_text: str, settle_obj: dict, stamp=400):
        r = self.client.post(f"/api/story/worker/{task['request_id']}/result", headers=self.wrk_headers, json={
            'lease': task['lease'],
            'text': json.dumps({
                'dual_stage_version': 1,
                'foreground_text': fg_text,
                'settlement': settle_obj,
            }, ensure_ascii=False),
            'conversation_audit': self.audit(mat, stamp=stamp),
            'timing': {
                'generation_ms': 800, 'settlement_ms': 240, 'preflight_ms': 0,
                'generation_passes': 1, 'settlement_passes': 1, 'settlement_model_id': 'gemini-flash',
            },
        })
        assert r.status_code == 200, r.get_data(as_text=True)
        return r.get_json()


class HealthRemediationTests(unittest.TestCase):

    def test_p0_1_sleep_start_accepts_hhmm_string_and_clock_dict(self):
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='zhiyun_late_office')
            st, ly, _ = save_store.load_bundle(h.root)
            st['runtime']['clock'] = {'day': 1, 'time': '23:10'}
            save_store.save_bundle(h.root, st, ly)
            files = {name: (h.root / name).read_bytes() for name in rr.FILES if (h.root / name).is_file()}
            for start_val in ('23:15', {'day': 1, 'time': '23:15'}):
                body = {
                    'selection': {'segment_id': '', 'option_id': 'REST'},
                    'audit': {'reservation': {'status': 'held', 'quote': {'kind': 'rest', 'total': 0}}},
                    'messages': [{'kind': 'narration', 'speaker': '', 'text': '夜深沉沉睡去直到天亮。'}],
                    'resolution': {
                        'category': 'SYSTEM',
                        'basis': '安稳整夜休息',
                        'clock': {'day': 2, 'time': '07:30', 'basis': '清晨醒来'},
                        'events': [],
                        'memory': {'fact': '', 'compact': '', 'transfers': {}},
                        'conditions': None,
                        'sleep': {'kind': 'overnight', 'start': start_val, 'evidence': '沉沉睡去直到天亮'},
                        'task': None,
                        'items': [],
                    },
                }
                res = sp.resolution(h.root, files, body)
                self.assertEqual(res['sleep']['start'], {'day': 1, 'time': '23:15'})

    def test_p0_2_p1_2_p1_9_prompts_and_kb_alignment(self):
        # P0-2: Stage 2 system prompt uses 堕落_私密自渎, never bare 私密自渎; includes unlock_secrets & "HH:MM"
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='zhiyun_late_office')
            h.complete_latest_playback()
            t = h.create_action('prompt-check-1', 'A', '问候她')
            t = h.claim()
            mat = h.material(t)
            s2 = mat['settlement_spec']['system_prompt']
            self.assertIn('堕落_私密自渎', s2)
            self.assertIn('unlock_secrets', s2)
            self.assertIn('"HH:MM"', s2)
            for seg in s2.split('堕落_私密自渎'):
                self.assertNotIn('私密自渎', seg.replace('意外撞破_私密自渎', ''))

        # P1-9: Zone 0 includes <stress> in both faithful & silent; single_prefix_v2 includes scene_state
        z0_f = sc.build_zone0_global(ROOT, mode='dual_stream_v2', protagonist_style='faithful')
        z0_s = sc.build_zone0_global(ROOT, mode='dual_stream_v2', protagonist_style='silent')
        z0_single = sc.build_zone0_global(ROOT, mode='single_prefix_v2', protagonist_style='faithful')
        self.assertIn('<stress>', z0_f)
        self.assertIn('<stress>', z0_s)
        self.assertIn('scene_state', z0_single)
        self.assertIn('unlock_secrets', z0_single)

        # P1-2: lore.命名锁 aligned with 1/2/3 intimate continuation costs (no 5/7/10)
        wb_world = json.loads((ROOT / 'txt文件/知识库/世界观类.json').read_text(encoding='utf-8'))
        naming = [e['content'] for e in wb_world['data']['entries'] if 'lore.命名锁' in e.get('content', '')][0]
        self.assertIn('1/2/3', naming)
        self.assertNotIn('5/7/10', naming)

        # P2-1: sys.runtime_data updated to P3 memory_store.json & 16 幕
        wb_sys = json.loads((ROOT / 'txt文件/知识库/系统标签类.json').read_text(encoding='utf-8'))
        rt = [e['content'] for e in wb_sys['data']['entries'] if 'sys.runtime_data' in e.get('content', '')][0]
        self.assertIn('memory_store.json', rt)
        self.assertIn('16', rt)

    def test_p0_4_p1_4_stream_parser_hardening(self):
        raw = (
            '好的，以下是本段剧情：\n'
            '```text\n'
            '［N］ [sigh] 窗外雨声细密。\n'
            '［A：沈知韫］ <whisper>她指尖拂过茶杯边缘。</whisper>\n'
            '［D：沈知韫］\n'
            '<stress>志北</stress>，<madeup attr="1">坐下</madeup>说话。\n'
            '[D:沈知韫] 她轻笑一声：“别总站着。”\n'
            '[D:徐志北] [轻笑] <whisper>好。</whisper>\n'
            '```\n'
            '以上为正文。\n'
            '---DECISION---\n'
            'PROMPT: 你接下来打算怎么回应？\n'
            'A: 坐下陪她喝茶。\n'
            'B: 顺手替她添茶。\n'
            'C: ［MOVE：公司］ 直接动身去公司。\n'
        )
        parsed = sc.parse_stream_story(raw, ['沈知韫'], allow_player_dialogue=True)
        msgs = parsed['messages']
        self.assertEqual(len(msgs), 6)
        self.assertEqual(msgs[0]['kind'], 'narration')
        self.assertNotIn('[sigh]', msgs[0]['text'])
        self.assertEqual(msgs[1]['kind'], 'action')
        self.assertNotIn('<whisper>', msgs[1]['text'])
        self.assertEqual(msgs[2]['kind'], 'dialogue')
        self.assertEqual(msgs[2]['speaker'], '沈知韫')
        self.assertIn('<stress>志北</stress>', msgs[2]['text'])
        self.assertNotIn('<madeup', msgs[2]['text'])
        self.assertEqual(msgs[3]['kind'], 'action')
        self.assertEqual(msgs[4]['kind'], 'dialogue')
        self.assertEqual(msgs[4]['text'], '别总站着。')
        self.assertEqual(msgs[5]['speaker'], '徐志北')
        self.assertNotIn('[轻笑]', msgs[5]['text'])
        self.assertNotIn('<whisper>', msgs[5]['text'])
        self.assertEqual(
            parsed['decision']['options'][2].get('operation'),
            {'code': 'move_player', 'destination': '公司'},
        )

    def test_p0_3_intel_persistence_and_s03_dual_channel_unlock(self):
        # Part A: INTEL-003 (target 沈知韫) persists into mechanics.secrets_unlocked via registry-driven check
        with tempfile.TemporaryDirectory() as td_intel:
            hi = _Harness(td_intel, scenario_id='zhiyun_late_office')
            hi.complete_latest_playback()
            sti, lyi, _ = save_store.load_bundle(hi.root)
            sti['panels']['系统宿主']['商业嗅觉'] = 80
            sti['intel']['held'] = ['INTEL-001', 'INTEL-003']
            save_store.save_bundle(hi.root, sti, lyi)

            ti = hi.create_action('rem-intel-3', 'C', '把徐承邺收购盲区的核查材料放在沈知韫面前')
            ti = hi.claim()
            mati = hi.material(ti)
            fgi = _fg_script(speaker='沈知韫', line='这份收购盲区的核查材料，你从哪里弄来的？')
            settlei = _settlement_payload(
                evidence_line='这份收购盲区的核查材料，你从哪里弄来的？',
                category='C',
                conditions=_action_conditions('C', '沈知韫', '公司'),
                clock_time='19:45',
            )
            settlei['resolution']['intel_used'] = {'id': 'INTEL-003', 'target': '沈知韫', 'evidence': '这份收购盲区的核查材料'}
            resi = hi.submit_result(ti, mati, fgi, settlei, stamp=450)
            self.assertEqual(resi['task']['status'], 'committed', resi)
            sti_after, _, _ = save_store.load_bundle(hi.root)
            self.assertIn('INTEL-003', sti_after['mechanics']['secrets_unlocked'],
                          'INTEL-003 must persist into secrets_unlocked')

        # Part B: S03_XU_PAINTING (SECRET-XNW-PAINTING) dual-channel unlock + forged INTEL rejection
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='nianwei_rain_studio')
            h.complete_latest_playback()

            st, ly, _ = save_store.load_bundle(h.root)
            st['panels']['徐念薇']['好感'] = 75
            save_store.save_bundle(h.root, st, ly)

            # Channel B: gated scene_state.unlock_secrets (accepts SECRET-XNW-PAINTING, rejects forged INTEL-002)
            t1 = h.create_action('rem-s03-b', 'C', '揭开画室里被白布盖住的旧画')
            t1 = h.claim()
            mat1 = h.material(t1)
            fg1 = (
                '[N] 雨点打在玻璃上。\n'
                '[A:徐志北] 伸手掀开画架上的白布，露出那幅落灰的旧画。\n'
                '[D:徐念薇] 别看那幅画……那是关于那年选拔展和抄袭的旧画稿。\n'
                '---DECISION---\n'
                'PROMPT: 接下来？\n'
                'A: 轻声安慰她。\n'
                'B: 扶住她的肩。\n'
                'C: 追问当年的真相。\n'
            )
            settle1 = _settlement_payload(
                evidence_line='别看那幅画……那是关于那年选拔展和抄袭的旧画稿。',
                category='C',
                conditions=_action_conditions('C', '徐念薇', '工作室'),
                clock_time='20:45',
            )
            settle1['resolution']['scene_state'] = {
                'present_actors': ['徐志北', '徐念薇'],
                'unlock_secrets': ['SECRET-XNW-PAINTING', 'INTEL-002'],
            }
            res1 = h.submit_result(t1, mat1, fg1, settle1, stamp=500)
            self.assertEqual(res1['task']['status'], 'committed', res1)

            st_after, ly_after, _ = save_store.load_bundle(h.root)
            unlocked = st_after['mechanics']['secrets_unlocked']
            self.assertIn('SECRET-XNW-PAINTING', unlocked, 'S03_XU_PAINTING must unlock via gated Channel B')
            self.assertNotIn('INTEL-002', unlocked, 'Forged INTEL-002 in scene_state.unlock_secrets must be rejected')

            # Channel A: deterministic unlock via BEAT-T2-STUDIO-PAINTING-QUESTION
            st_after['mechanics']['secrets_unlocked'] = []
            save_store.save_bundle(h.root, st_after, ly_after)
            h.complete_latest_playback()
            with patch.object(sp, 'roll_director_beat', return_value={
                'triggered': True,
                'beat_id': 'BEAT-T2-STUDIO-PAINTING-QUESTION',
                'tier': 'T2',
                'hint': '画廊电话问起旧画',
                'probability': 1.0,
                'scene_turns_in_place': 2,
            }):
                t2 = h.create_action('rem-beat-1', 'A', '顺着画廊来电继续和她聊画作')
            t2 = h.claim()
            mat2 = h.material(t2)
            fg2 = _fg_script(speaker='徐念薇', line='画廊刚才又来问那幅旧画的事了。')
            settle2 = _settlement_payload(
                evidence_line='画廊刚才又来问那幅旧画的事了。',
                category='A',
                conditions=_action_conditions('A', '徐念薇', '工作室'),
                clock_time='21:00',
            )
            res2 = h.submit_result(t2, mat2, fg2, settle2, stamp=600)
            self.assertEqual(res2['task']['status'], 'committed', res2)
            st_after2, _, _ = save_store.load_bundle(h.root)
            self.assertIn('SECRET-XNW-PAINTING', st_after2['mechanics']['secrets_unlocked'],
                          'Channel A director beat must deterministically unlock SECRET-XNW-PAINTING')

    def test_p1_3_zone1_unlocked_secrets_scope_rollover_and_mid_session_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='nianwei_rain_studio')
            h.complete_latest_playback()

            t1 = h.create_action('z1-turn-1', 'A', '顺口提起沈知韫和苏婉青今天在忙什么')
            t1 = h.claim()
            scope_before = t1['interaction_scope']
            mat1 = h.material(t1, is_fresh=True)
            z0_1, z1_1 = mat1['zone0_sha256'], mat1['zone1_sha256']
            self.assertNotIn('【已解锁暗线态势】', mat1['zone1_scene'])
            synced_flags = (mat1.get('session_meta') or {}).get('zone1_flags') or {}

            # Cancel t1 cleanly, then mutate stats + unlock secret in save_state
            rc = h.client.post(f"/api/story/tasks/{t1['request_id']}/cancel", headers=h.cli_headers, json={})
            self.assertEqual(rc.status_code, 200)
            st, ly, _ = save_store.load_bundle(h.root)
            st['panels']['徐念薇']['好感'] = 68
            st['panels']['徐念薇']['欲望'] = 55
            st['mechanics']['secrets_unlocked'] = ['SECRET-XNW-PAINTING']
            save_store.save_bundle(h.root, st, ly)

            # New action after secret unlock -> interaction_scope changes cleanly to trigger rollover
            t2 = h.create_action('z1-turn-2', 'A', '继续聊那幅画')
            t2 = h.claim()
            self.assertNotEqual(t2['interaction_scope'], scope_before,
                                'Unlocking an active cast secret must change interaction_scope for clean rollover')
            # Defense-in-depth: if bridge stayed mid-session (is_fresh=False) with synced_zone1_flags, Zone 1 stays byte-identical!
            mat_mid = h.material(
                t2, is_fresh=False,
                synced_z0=z0_1, synced_z1=z1_1, synced_flags=synced_flags,
            )
            self.assertEqual(mat_mid['zone0_sha256'], z0_1, 'Zone 0 must stay zero-drift')
            self.assertEqual(mat_mid['zone1_sha256'], z1_1, 'Mid-session Zone 1 must freeze unlocked_secrets for zero-drift')

            # Fresh session after rollover naturally injects 【已解锁暗线态势】 in Zone 1!
            rc2 = h.client.post(f"/api/story/tasks/{t2['request_id']}/cancel", headers=h.cli_headers, json={})
            self.assertEqual(rc2.status_code, 200)
            t3 = h.create_action('z1-turn-3', 'A', '继续聊那幅画')
            t3 = h.claim()
            mat3 = h.material(t3, is_fresh=True)
            self.assertIn('【已解锁暗线态势】', mat3['zone1_scene'])

    def test_p1_7_k01_subtext_whitelist_and_decision_non_retryable(self):
        msgs_safe = [{
            'kind': 'dialogue',
            'speaker': '沈知韫',
            'text': '｛公司账目都按规矩走，你别多想。｜老爷子遗嘱真正留给徐志北的秘密绝不能现在说破｝',
        }]
        res_safe = sc.guardrail_check(ROOT, '徐家主宅', ['沈知韫'], msgs_safe, secrets_unlocked=())
        self.assertEqual([w for w in res_safe if 'K01' in str(w)], [])

        msgs_leak = [{
            'kind': 'dialogue',
            'speaker': '沈知韫',
            'text': '老爷子的遗嘱里写着你才是唯一合法继承人。',
        }]
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(ROOT, '徐家主宅', ['沈知韫'], msgs_leak, secrets_unlocked=())

        self.assertFalse(ir.is_settlement_retryable_error(rr.RoundError('bad', 'decision.prompt过长')))
        self.assertFalse(ir.is_settlement_retryable_error(rr.RoundError('bad', 'decision.option.text超出长度')))

    def test_p1_8_present_actors_empty_safeguard(self):
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='zhiyun_late_office')
            h.complete_latest_playback()
            t1 = h.create_action('pa-guard-1', 'A', '和沈知韫核对报表')
            t1 = h.claim()
            mat = h.material(t1)
            fg = _fg_script(speaker='沈知韫', line='这份季报先放桌上吧。')
            settle = _settlement_payload(
                evidence_line='这份季报先放桌上吧。',
                category='A',
                conditions=_action_conditions('A', '沈知韫', '公司'),
                clock_time='19:40',
            )
            settle['resolution']['scene_state'] = {'present_actors': ['徐志北']}
            res = h.submit_result(t1, mat, fg, settle, stamp=700)
            self.assertEqual(res['task']['status'], 'committed')
            st, _, _ = save_store.load_bundle(h.root)
            self.assertIn('沈知韫', st['intimate']['present_actors'])

    def test_p0_5_sse_resync_on_stale_seq_and_epoch_mismatch(self):
        hub = ss._EventHub()
        hub.publish('committed', {'id': '1'})
        events, seq = hub.wait_client(since_seq=42, timeout=0.1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1], 'resync')
        self.assertEqual(seq, hub.seq)

        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td)
            resp = h.client.get('/api/story/stream?since=42&epoch=stale-epoch-xyz')
            self.assertEqual(resp.status_code, 200)
            chunks = []
            for part in resp.response:
                chunks.append(part.decode('utf-8'))
                if len(chunks) >= 2:
                    break
            resp.close()
            joined = ''.join(chunks)
            self.assertIn('event: ready', joined)
            self.assertIn('service_epoch', joined)
            self.assertIn('event: resync', joined)

    def test_p1_5_paid_tts_tier_triggers_committed_prewarm(self):
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='zhiyun_late_office')
            h.complete_latest_playback()
            captured = []
            orig_prewarm = h.svc._trigger_tts_prewarm

            def spy_prewarm(messages, *args, **kwargs):
                captured.append((kwargs.get('stage', 'streaming'), len(messages or [])))
                return orig_prewarm(messages, *args, **kwargs)

            with patch.object(h.svc, '_trigger_tts_prewarm', side_effect=spy_prewarm):
                t1 = h.create_action('tts-paid-1', 'A', '问她要不要喝热茶')
                t1 = h.claim()
                mat = h.material(t1)
                fg = _fg_script(speaker='沈知韫', line='先放着吧，等会儿喝。')
                settle = _settlement_payload(
                    evidence_line='先放着吧，等会儿喝。',
                    category='A',
                    conditions=_action_conditions('A', '沈知韫', '公司'),
                    clock_time='19:45',
                )
                res = h.submit_result(t1, mat, fg, settle, stamp=800)
                self.assertEqual(res['task']['status'], 'committed')
            self.assertTrue(any(st == 'committed' for st, _ in captured),
                            f'Expected stage="committed" TTS prewarm call, got {captured}')

    def test_p1_6_partial_json_corruption_preserves_intact_half(self):
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='zhiyun_late_office')
            st, ly, _ = save_store.load_bundle(h.root)
            st['mechanics']['secrets_unlocked'] = ['INTEL-001', 'SECRET-XNW-PAINTING']
            st['npc_mind']['沈知韫']['resentment'] = 33
            save_store.save_bundle(h.root, st, ly)
            (h.root / save_store.MEMORY_LAYERS_PATH).write_text('{corrupted json!!!', encoding='utf-8')
            st_reloaded, ly_reloaded, _ = save_store.load_bundle(h.root)
            self.assertEqual(st_reloaded['mechanics']['secrets_unlocked'], ['INTEL-001', 'SECRET-XNW-PAINTING'])
            self.assertEqual(st_reloaded['npc_mind']['沈知韫']['resentment'], 33)
            self.assertIsInstance(ly_reloaded, dict)

    def test_p0_6_legacy_roundstore_preserves_l1_l4_memory_txt(self):
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td)
            store = rr.RoundStore(h.root)
            prep = store.prepare()
            req = {
                'schema_version': 1,
                'request_id': 'legacy-round-p0-6',
                'base_revision': prep['base_revision'],
                'current_round': prep['current_round'],
                'story_nodes': [
                    {'type': 'header', 'text': '8月5日,周三,徐家主宅,10:00'},
                    {'type': 'narration', 'text': '清晨日光落在窗台。'},
                    {'type': 'dialogue', 'speaker': '沈知韫', 'text': '今天把账目理清。'},
                ],
                'memory_deltas': {'l1_new_round': '与沈知韫在书房核对季度账目，约定晚间复盘。'},
                'panel_changes': {},
                'npc_entries': [],
                'item_entries': [],
                'system_log': (
                    f"【SYSTEM_LOG】\nROUND: {prep['current_round']}\nINTENT: 回归验证\nSCENE: 客厅|徐志北,沈知韫\n"
                    "【应查】\nmust_keys: state.memory, contract.inject, gate.V1\n"
                    "【实查】\nquery_keys: state.memory, contract.inject, gate.V1\n"
                    "【豁免】\nskip: 无\n"
                    "【V1验收】\nV1-A: 通过 — 合成验收\nV1-B: 通过 — 无括号\nV1-C: 通过 — 合成验收\nV1-D: 通过 — 合成验收\n"
                    "【事件打标】\nHOST: 无\n【记忆/所在】\nL1: 已写\npresence: {}\n"
                ),
                'options_text': '[A. 日常互动]：继续核对账目\n[B. 社交接触]：递上热茶问候\n[C. 主动行为]：询问并购细节',
            }
            receipt = store.submit(req)
            self.assertEqual(receipt['status'], 'committed')
            mem_txt = (h.root / '存档/全局记忆库.txt').read_text(encoding='utf-8')
            self.assertIn('与沈知韫在书房核对季度账目', mem_txt)

    def test_p0_7_restore_save_slot_aborts_on_backup_failure_and_uses_wal(self):
        cleaner = _load_cleaner_module()
        with tempfile.TemporaryDirectory() as td:
            h = _Harness(td, scenario_id='zhiyun_late_office')
            slot = cleaner.create_save_slot(h.root, label='pre-test')
            slot_id = slot['id']

            st, ly, _ = save_store.load_bundle(h.root)
            st['panels']['系统宿主']['积分'] = 999
            save_store.save_bundle(h.root, st, ly)

            with patch.object(cleaner, 'create_save_slot', side_effect=OSError('disk full')):
                with self.assertRaises(RuntimeError):
                    cleaner.restore_save_slot(h.root, slot_id, auto_backup_current=True)
            st_check, _, _ = save_store.load_bundle(h.root)
            self.assertEqual(st_check['panels']['系统宿主']['积分'], 999, 'Aborted restore must not overwrite current save')

            out = cleaner.restore_save_slot(h.root, slot_id, auto_backup_current=True)
            self.assertEqual(out.get('status'), 'restored')
            self.assertFalse((h.root / '.round-runtime/reset-journal.json').exists())
            st_restored, _, _ = save_store.load_bundle(h.root)
            self.assertNotEqual(st_restored['panels']['系统宿主']['积分'], 999)


if __name__ == '__main__':
    unittest.main()

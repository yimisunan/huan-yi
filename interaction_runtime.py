"""Formal continuous interactions. Persistence is owned exclusively by RoundStore."""
import copy
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.parse
import round_runtime as rr
import save_store
import story_reading as sr
import story_progression as sp
import story_compiler as sc

_DIGEST_LOCK = threading.Lock()
_DIGEST_CACHE = {}


def _cached_digest(path):
    """Return SHA-256 hex digest cached by (abs_path, mtime_ns, size) for fast audit manifest building."""
    p = Path(path)
    st = p.stat()
    key = str(p)
    sig = (st.st_mtime_ns, st.st_size)
    with _DIGEST_LOCK:
        hit = _DIGEST_CACHE.get(key)
        if hit is not None and hit[0] == sig:
            return hit[1]
    digest = rr._digest(p.read_bytes())
    with _DIGEST_LOCK:
        if len(_DIGEST_CACHE) > 256:
            _DIGEST_CACHE.clear()
        _DIGEST_CACHE[key] = (sig, digest)
    return digest

MODE = 'live_interaction'
CONFIG = 'txt文件/互动运行配置.json'
ARCHIVE = '.round-runtime/interaction'
RULE = 'txt文件/场景交流规范.md'
PEOPLE = ('沈知韫', '苏婉青', '徐念薇')
PLAYBACK = ARCHIVE + '/playback.json'
LIVE_READ_TOOLS = ('read_file', 'read_file_full', 'read_file_part', 'file_info', 'grep_code')
OPTION_NAMES = {'A': '日常互动', 'B': '社交接触', 'C': '主动行为'}


def decision(value, valid_locations=None):
    rr._keys(value, {'prompt', 'options'}, 'decision', {'prompt', 'options'})
    rr._text(value['prompt'], 'decision.prompt', 300)
    options = value['options']
    if not isinstance(options, list) or len(options) != 3:
        raise rr.RoundError('decision.options须恰含A/B/C三个选项')
    for item, letter in zip(options, OPTION_NAMES):
        rr._keys(item, {'id', 'text', 'operation'}, 'decision.option', {'id', 'text'})
        if item['id'] != letter:
            raise rr.RoundError('选项必须按A/B/C排列且不重复')
        rr._text(item['text'], 'decision.option.text', 500)
        op = item.get('operation')
        if op is not None:
            rr._keys(op, {'code', 'destination'}, 'decision.option.operation', {'code', 'destination'})
            if op['code'] != 'move_player' or not isinstance(op['destination'], str) or not op['destination'].strip():
                raise rr.RoundError('选项转场操作仅支持有效目的地的move_player')
            if valid_locations is not None and op['destination'] not in valid_locations:
                raise rr.RoundError('选项转场目的地未开放: ' + str(op['destination']))
    if len({item['text'].strip() for item in options}) != 3:
        raise rr.RoundError('三个选项须为不同的可行动作')
    return copy.deepcopy(value)


def segment(root, files):
    raw_data = files.get('data.json')
    data = json.loads(raw_data) if raw_data else {}
    state = data.get('interaction', {}) if isinstance(data, dict) else {}
    seg_id = state.get('segment_id') or ''
    sequence = state.get('last_sequence')
    recent = None
    if not seg_id and raw_data is None:
        st, _, recent = save_store.load_bundle(root, files)
        seg_id = (st.get('runtime') or {}).get('last_segment_id') or ''
        sequence = (st.get('runtime') or {}).get('last_sequence') or 0
    if not seg_id:
        return None
    if type(sequence) is not int or sequence < 1:
        raise rr.RecoveryError('剧情段索引无效')
    archive_path = Path(root) / ARCHIVE / f'{sequence:012d}.json'
    if archive_path.is_file():
        row = rr.load_request(archive_path.read_text(encoding='utf-8'))
        if row.get('id') != seg_id or row.get('version') != 2:
            raise rr.RecoveryError('剧情段与当前存档不一致')
        return row
    if recent is None:
        _, _, recent = save_store.load_bundle(root, files)
    for item in reversed(recent.get('segments') or []):
        if isinstance(item, dict) and item.get('id') == seg_id and item.get('version') == 2:
            return copy.deepcopy(item)
    return None


def playback(root, row):
    if row is None:
        return {'segment_id': '', 'revealed': 0, 'total': 0, 'completed': True, 'bootstrap': True}
    path = Path(root) / PLAYBACK
    total = len(row['messages'])
    if path.is_file():
        value = rr.load_request(path.read_text(encoding='utf-8'))
    else:
        recent_path = Path(root) / save_store.RECENT_PLAYBACK_PATH
        value = None
        if recent_path.is_file():
            try:
                recent = json.loads(recent_path.read_text(encoding='utf-8'))
                pb = recent.get('playback') if isinstance(recent, dict) else None
                if isinstance(pb, dict) and pb.get('segment_id') == row['id']:
                    value = pb
            except ValueError:
                value = None
        if value is None:
            return {'version': 1, 'segment_id': row['id'], 'revealed': total, 'completed': True,
                    'total': total, 'bootstrap': False}
    if value.get('segment_id') != row['id']:
        raise rr.RecoveryError('剧情演播进度与当前段落不一致')
    if (value.get('version') != 1 or type(value.get('revealed')) is not int
            or not 0 <= value['revealed'] <= total or type(value.get('completed')) is not bool
            or (value['completed'] and value['revealed'] != total)):
        raise rr.RecoveryError('剧情演播进度无效')
    return {**value, 'total': total, 'bootstrap': False}


def selection(root, files, proposed, text, command=None, *, allow_handoff_drop=False):
    row = segment(root, files)
    state = playback(root, row)
    if proposed is None:
        if row is not None:
            raise rr.ConflictError('本段演播完成后须按当前抉择提交，旧输入不可绕过')
        return None  # Compatibility for pre-playback callers; the page uses BEGIN.
    rr._keys(proposed, {'segment_id', 'option_id'}, 'selection', {'segment_id', 'option_id'})
    if sp.enabled(root) and row is not None:
        runtime = sp.state(root, files)
        resting = runtime['phase'] == 'resting' or sp.stamina(root, files) < 5
        if resting:
            if (not state['completed'] or proposed != {'segment_id':row['id'], 'option_id':'REST'} or text != '继续休息' or command):
                raise rr.ConflictError('本段读完后须进入免费强制休息')
            return copy.deepcopy(proposed)
    if row is None:
        if proposed != {'segment_id': '', 'option_id': 'BEGIN'} or text != '继续当前剧情' or command:
            raise rr.ConflictError('当前没有可消费的抉择，请从继续剧情开始')
    else:
        if not state['completed']:
            raise rr.ConflictError('本段剧情尚未演播完成')
        if proposed['segment_id'] != row['id'] or proposed['option_id'] not in (*OPTION_NAMES, 'CUSTOM'):
            raise rr.ConflictError('抉择已过期，请恢复当前段落')
        if proposed['option_id'] != 'CUSTOM':
            item = next(item for item in row['decision']['options'] if item['id'] == proposed['option_id'])
            expected_op = item.get('operation')
            op_ok = (command == expected_op) or (allow_handoff_drop and expected_op is not None and command is None)
            if item['text'] != text or not op_ok:
                raise rr.ConflictError('选项内容或转场操作与本段不一致，不允许替换原行动')
    return copy.deepcopy(proposed)


STORY_PREFS_PATH = '.round-runtime/story/prefs.json'
PERSONA_CORRECTION_PATH = '.round-runtime/story/persona-correction.json'


def load_story_prefs(root):
    """Load runtime story preferences (defaults: faithful protagonist, standard director pacing, balanced anchor history, ask on drift, custom rules off)."""
    defaults = {
        'protagonist_style': 'faithful',
        'director_pacing': 'standard',
        'anchor_history_mode': 'balanced',
        'drift_review_mode': 'ask',
        'voice_playback_enabled': True,
        'custom_rules_enabled': False,
        'custom_rules_position': 'append',
        'custom_rules_text': '',
        'settlement_custom_rules_enabled': False,
        'settlement_custom_rules_position': 'append',
        'settlement_custom_rules_text': '',
    }
    p = Path(root) / STORY_PREFS_PATH
    if not p.is_file():
        return dict(defaults)
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            return dict(defaults)
        return {
            'protagonist_style': sc.normalize_protagonist_style(raw.get('protagonist_style', 'faithful')),
            'director_pacing': sp.normalize_director_pacing(raw.get('director_pacing', 'standard')),
            'anchor_history_mode': sc.normalize_anchor_history_mode(raw.get('anchor_history_mode', 'balanced')),
            'drift_review_mode': sc.normalize_drift_review_mode(raw.get('drift_review_mode', 'ask')),
            'voice_playback_enabled': bool(raw.get('voice_playback_enabled', True)),
            'custom_rules_enabled': bool(raw.get('custom_rules_enabled', False)),
            'custom_rules_position': sc.normalize_custom_rules_position(raw.get('custom_rules_position', 'append')),
            'custom_rules_text': sc.normalize_custom_rules_text(raw.get('custom_rules_text', '')),
            'settlement_custom_rules_enabled': bool(raw.get('settlement_custom_rules_enabled', False)),
            'settlement_custom_rules_position': sc.normalize_custom_rules_position(raw.get('settlement_custom_rules_position', 'append')),
            'settlement_custom_rules_text': sc.normalize_custom_rules_text(raw.get('settlement_custom_rules_text', '')),
        }
    except Exception:
        return dict(defaults)


def save_story_prefs(root, updates):
    """Persist validated runtime story preferences atomically."""
    if not isinstance(updates, dict):
        raise rr.RoundError('偏好设置须为对象')
    allowed_keys = {
        'protagonist_style', 'director_pacing', 'anchor_history_mode', 'drift_review_mode', 'voice_playback_enabled',
        'custom_rules_enabled', 'custom_rules_position', 'custom_rules_text',
        'settlement_custom_rules_enabled', 'settlement_custom_rules_position', 'settlement_custom_rules_text',
    }
    rr._keys(updates, allowed_keys, '偏好设置')
    cur = load_story_prefs(root)
    if 'protagonist_style' in updates:
        val = updates['protagonist_style']
        if val not in ('faithful', 'silent'):
            raise rr.RoundError('主角戏份风格须为 faithful 或 silent')
        cur['protagonist_style'] = val
    if 'director_pacing' in updates:
        val = updates['director_pacing']
        if val not in sp.DIRECTOR_PACING_MODES:
            raise rr.RoundError('女主意外节奏须为 slow、standard 或 frequent')
        cur['director_pacing'] = val
    if 'anchor_history_mode' in updates:
        val = updates['anchor_history_mode']
        if val not in sc.ANCHOR_HISTORY_MODES:
            raise rr.RoundError('开窗回溯模式须为 balanced 或 full')
        cur['anchor_history_mode'] = val
    if 'drift_review_mode' in updates:
        val = updates['drift_review_mode']
        if val not in sc.DRIFT_REVIEW_MODES:
            raise rr.RoundError('人设与暗线偏离处理须为 ask、auto_regen 或 soft_only')
        cur['drift_review_mode'] = val
    if 'voice_playback_enabled' in updates:
        val = updates['voice_playback_enabled']
        if type(val) is not bool:
            raise rr.RoundError('语音播放开关须为布尔值')
        cur['voice_playback_enabled'] = val
    for prefix, label in (
        ('custom_rules', '主模型自定义系统提示词'),
        ('settlement_custom_rules', '副模型自定义系统提示词'),
    ):
        en_key = prefix + '_enabled'
        pos_key = prefix + '_position'
        txt_key = prefix + '_text'
        if en_key in updates:
            val = updates[en_key]
            if type(val) is not bool:
                raise rr.RoundError(f'{label}开关须为布尔值')
            cur[en_key] = val
        if pos_key in updates:
            val = updates[pos_key]
            if val not in sc.CUSTOM_RULES_POSITIONS:
                raise rr.RoundError(f'{label}注入位置须为 append 或 prepend')
            cur[pos_key] = val
        if txt_key in updates:
            val = updates[txt_key]
            if not isinstance(val, str):
                raise rr.RoundError(f'{label}正文须为字符串')
            cur[txt_key] = sc.normalize_custom_rules_text(val)
    target = Path(root) / STORY_PREFS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    rr._atomic(target, rr._json(cur))
    return cur


def load_persona_correction(root, *, save_epoch=None):
    """Load pending one-shot soft persona correction matching save_epoch, or None."""
    p = Path(root) / PERSONA_CORRECTION_PATH
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            return None
        hint = str(raw.get('hint') or '').strip()
        if not hint:
            return None
        if save_epoch is not None and str(raw.get('save_epoch') or '') != str(save_epoch):
            return None
        return raw
    except Exception:
        return None


def save_persona_correction(root, *, save_epoch, hint, source_request_id=''):
    """Atomically store a one-shot next-turn Zone 2 persona/secret soft correction."""
    clean_hint = re.sub(r'[\r\n]+', ' ', str(hint or '')).strip()[:160]
    if not clean_hint:
        return None
    payload = {
        'save_epoch': str(save_epoch or ''),
        'hint': clean_hint,
        'source_request_id': str(source_request_id or ''),
        'created_at': time.time(),
    }
    target = Path(root) / PERSONA_CORRECTION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    rr._atomic(target, rr._json(payload))
    return payload


def clear_persona_correction(root):
    """Remove any pending one-shot soft persona correction."""
    p = Path(root) / PERSONA_CORRECTION_PATH
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def update_playback(store, row, revealed, completed, *, allow_catchup=False):
    state = playback(store.root, row)
    rr._integer(revealed, 'revealed')
    if type(completed) is not bool or row is None:
        raise rr.RoundError('演播完成标记或段落无效')
    if revealed > state['total'] or (not allow_catchup and revealed > state['revealed'] + 1):
        raise rr.ConflictError('演播须逐节点推进，请先恢复当前进度')
    if completed and (revealed != state['total'] or state['revealed'] != state['total']):
        raise rr.ConflictError('最后节点尚未演播，不可提前完成')
    new = {'version': 1, 'segment_id': row['id'], 'revealed': max(revealed, state['revealed']),
           'completed': state['completed'] or completed}
    if any(new[key] != state.get(key) for key in new):
        store._write_playback(new)
    return playback(store.root, row)


def policy(root):
    value = rr.load_request((Path(root) / CONFIG).read_text(encoding='utf-8'))
    resource = value.get('resource', {})
    if resource.get('scheme') == 'fixed_tiers':
        return sp.config(root)
    if value.get('version') != 1 or resource.get('status') not in ('pending', 'active'):
        raise rr.RoundError('互动运行配置版本或资源政策无效')
    if not isinstance(value.get('locations'), list) or not all(isinstance(n, str) and n for n in value['locations']):
        raise rr.RoundError('登记地点配置无效')
    if resource['status'] == 'pending':
        if resource.get('base_cost') is not None or resource.get('action_costs') is not None:
            raise rr.RoundError('待定资源政策不得携带隐式默认成本')
    else:
        rr._keys(resource, {'status', 'version', 'attribute', 'base_cost', 'action_costs', 'recovery', 'limits'},
                 'resource', {'status', 'version', 'attribute', 'base_cost', 'action_costs'})
        rr._integer(resource['version'], 'resource.version', 1)
        if resource.get('recovery') is not None or resource.get('limits') is not None:
            raise rr.RoundError('恢复与上限规则尚未实现，不能静默启用')
        if resource['attribute'] not in ('体力', '积分'):
            raise rr.RoundError('资源属性仅支持宿主已登记的体力或积分')
        rr._integer(resource['base_cost'], 'base_cost', 1)
        rr._keys(resource['action_costs'], {'move_player', 'transfer_item'}, 'action_costs', {'move_player', 'transfer_item'})
        for name, cost in resource['action_costs'].items():
            rr._integer(cost, 'action_costs.' + name)
    return value


def quote(root, files, op):
    resource = policy(root)['resource']
    if resource['status'] == 'pending':
        return {'status': 'pending', 'total': None, 'policy_version': None}
    total = resource['base_cost'] + (resource['action_costs'][op['code']] if op else 0)
    engine = rr._engine(root, root)
    current = engine._read_attr_value(files[rr.FILES[0]].decode('utf-8'), '系统宿主', resource['attribute'])
    if current is None:
        raise rr.RoundError('正式存档缺少指定资源')
    if current < total:
        raise rr.RoundError('资源不足；本次交流和操作均未接受')
    return {'status': 'active', 'attribute': resource['attribute'], 'total': total,
            'before': current, 'after': current - total, 'policy_version': resource['version']}


def records(store):
    folder = store._path(ARCHIVE)
    return sorted(p for p in folder.glob('*.json') if re.fullmatch(r'\d{12}\.json', p.name))


def recent_rows_page(store, files=None, *, before=None, limit=10):
    """Lazily read only the exact paginated slice of history segments (O(limit) disk reads, not O(total))."""
    limit = max(1, int(limit or 10))
    recent_map = {}
    _, _, recent = save_store.load_bundle(store.root, files)
    for item in recent.get('segments') or []:
        if isinstance(item, dict) and isinstance(item.get('sequence'), int) and item['sequence'] >= 1:
            recent_map[item['sequence']] = item
    disk_map = {}
    for p in records(store):
        try:
            disk_map[int(p.stem)] = p
        except ValueError:
            continue
    all_seqs = sorted(set(recent_map.keys()) | set(disk_map.keys()))
    if before is not None:
        all_seqs = [seq for seq in all_seqs if seq < before]
    has_older = len(all_seqs) > limit
    page_seqs = all_seqs[-limit:]
    rows = []
    for seq in page_seqs:
        p = disk_map.get(seq)
        if p is not None:
            try:
                row = rr.load_request(p.read_text(encoding='utf-8'))
                rows.append((p, row))
                continue
            except Exception:
                pass
        if seq in recent_map:
            rows.append((None, copy.deepcopy(recent_map[seq])))
    return rows, has_older


def recent_rows_tail(store, files=None, *, limit=24):
    """O(1) tail reader for packet assembly: reads only the latest `limit` segments while keeping omitted older paths."""
    limit = max(1, int(limit or 24))
    recent_map = {}
    _, _, recent = save_store.load_bundle(store.root, files)
    for item in recent.get('segments') or []:
        if isinstance(item, dict) and isinstance(item.get('sequence'), int) and item['sequence'] >= 1:
            recent_map[item['sequence']] = item
    disk_map = {}
    for p in records(store):
        try:
            disk_map[int(p.stem)] = p
        except ValueError:
            continue
    all_seqs = sorted(set(recent_map.keys()) | set(disk_map.keys()))
    older_seqs = all_seqs[:-limit] if len(all_seqs) > limit else []
    tail_seqs = all_seqs[-limit:]
    older_paths = [disk_map[seq] for seq in older_seqs if seq in disk_map]
    rows = []
    for seq in tail_seqs:
        p = disk_map.get(seq)
        if p is not None:
            try:
                row = rr.load_request(p.read_text(encoding='utf-8'))
                rows.append((p, row))
                continue
            except Exception:
                pass
        if seq in recent_map:
            rows.append((None, copy.deepcopy(recent_map[seq])))
    return rows, older_paths


def parse_public_vigilance(memory_text, save_state=None):
    """Parse 【监视状态】 for frontend display: exposes position, vigilance, discovery, reason, stage & sensitivity; STRICTLY hides 发现几率."""
    pos_m = re.search(r'^徐承邺位置：([^\n]+)', memory_text or '', re.M)
    position = pos_m.group(1).strip() if pos_m else '外地'
    su_defected = False
    if isinstance(save_state, dict):
        consumed = set((save_state.get('intel') or {}).get('consumed') or [])
        su_p = (save_state.get('panels') or {}).get('苏婉青') or {}
        if 'INTEL-002' in consumed and int(su_p.get('好感', 0) or 0) >= 70 and int(su_p.get('羞耻', 100) or 100) <= 50:
            su_defected = True
    role_meta = {
        '苏婉青': ('妻子 · 反水掩护' if su_defected else '妻子 · 极敏', 1.5),
        '沈知韫': ('母亲 · 伦理盲区', 2.0),
        '徐念薇': ('妹妹 · 易掩护', 3.0),
        '徐志北': ('养弟 · 连带汇聚', 2.0),
    }
    targets = []
    for m in re.finditer(
        r'^徐承邺_([^\n：:]+)[：:]\s*警惕\s*(\d+)\s*\|\s*发现\s*(\d+)(?:\s*\|\s*发现几率\s*\d+)?(?:\s*\|\s*动因[：:]\s*([^\n|]+))?',
        memory_text or '', re.M,
    ):
        who = m.group(1).strip()
        v = int(m.group(2))
        d = int(m.group(3))
        reason = (m.group(4) or '').strip()[:48]
        if d >= 3:
            stage, stage_label = 4, ('目击锁定' if d == 3 else '证据实锤')
        elif v >= 85:
            stage, stage_label = 4, '摊牌'
        elif v >= 65:
            stage, stage_label = 3, '紧盯'
        elif v >= 40:
            stage, stage_label = 2, '查岗'
        elif v >= 20:
            stage, stage_label = 1, '起疑'
        else:
            stage, stage_label = 0, '无察'
        r_label, decay_h = role_meta.get(who, ('受监视目标', 2.0))
        targets.append({
            'name': who,
            'vigilance': v,
            'discovery': d,
            'reason': '' if (v == 0 and d == 0) else reason,
            'stage': stage,
            'stage_label': stage_label,
            'role_label': r_label,
            'decay_per_hour': decay_h,
        })
    return {'position': position, 'targets': targets}


def scene_cast(presence, memory_text, location):
    """Authoritative on-stage speaker list; dynamically includes 徐承邺 when rolled into 徐家主宅 or 市中心顶层公寓."""
    cast = [n for n in PEOPLE if presence.get(n, {}).get('location') == location]
    if location == '徐家主宅' and re.search(r'^徐承邺位置：\s*(?:徐家主宅|徐家住宅)\b', memory_text or '', re.M):
        cast.append('徐承邺')
    elif location == '市中心顶层公寓' and re.search(r'^徐承邺位置：\s*市中心顶层公寓\b', memory_text or '', re.M):
        cast.append('徐承邺')
    return cast


_VISUAL_EXT_PRIORITY = {'.webp': 7, '.avif': 6, '.jpg': 5, '.jpeg': 4, '.png': 3, '.gif': 2, '.svg': 1}
_SCENE_TIME_SLOTS = frozenset({'day', 'night', 'dawn', 'dusk'})
_VISUAL_ASSETS_CACHE = {}


def parse_micro_states(memory_text):
    """Read-only parser for 【当前激活微状态】 safe against legacy/partial files."""
    try:
        return rr._current_micro(memory_text or '')
    except Exception:
        return {name: {k: False for k in rr.MICRO_STATES} for name in rr.ROUND_NPCS}


def _visual_dir_sig(image_root):
    try:
        sig = [image_root.stat().st_mtime_ns]
        for entry in sorted(image_root.iterdir(), key=lambda p: p.name):
            if entry.name.startswith(('.', '_')) or not entry.is_dir():
                continue
            sig.append((entry.name, entry.stat().st_mtime_ns))
        return tuple(sig)
    except OSError:
        return None


def scan_visual_assets(root):
    """Auto-discover scenes/ and character visual assets under txt文件/image/ (newest mtime wins across extensions)."""
    image_root = (Path(root) / 'txt文件' / 'image').resolve()
    scenes = {}
    characters = {}
    if not image_root.is_dir():
        return {'scenes': scenes, 'characters': characters}
    dir_sig = _visual_dir_sig(image_root)
    cache_key = str(image_root)
    cached = _VISUAL_ASSETS_CACHE.get(cache_key)
    if dir_sig is not None and cached and cached[0] == dir_sig:
        return copy.deepcopy(cached[1])

    def _pick(bucket, key, path, rel_parts):
        ext = path.suffix.lower()
        prio = _VISUAL_EXT_PRIORITY.get(ext, 0)
        if not prio:
            return
        try:
            st = path.stat()
        except OSError:
            return
        rank = (st.st_mtime_ns, prio)
        prev = bucket.get(key)
        if prev is None or rank > prev[0]:
            url = '/txt文件/image/' + '/'.join(urllib.parse.quote(p, safe='') for p in rel_parts) + f'?v={int(st.st_mtime)}'
            bucket[key] = (rank, url)

    scenes_dir = image_root / 'scenes'
    if scenes_dir.is_dir():
        scene_buckets = {}
        for f in sorted(scenes_dir.iterdir(), key=lambda p: p.name):
            if f.name.startswith(('.', '_')) or not f.is_file():
                continue
            stem = f.stem
            if '_' in stem:
                place, suffix = stem.rsplit('_', 1)
                slot = suffix.lower() if suffix.lower() in _SCENE_TIME_SLOTS else 'default'
                if slot == 'default':
                    place = stem
            else:
                place, slot = stem, 'default'
            place = place.strip()
            if not place:
                continue
            _pick(scene_buckets.setdefault(place, {}), slot, f, ('scenes', f.name))
        scenes = {place: {slot: pair[1] for slot, pair in slots.items()} for place, slots in scene_buckets.items()}

    for entry in sorted(image_root.iterdir(), key=lambda p: p.name):
        if entry.name.startswith(('.', '_')) or entry.name == 'scenes' or not entry.is_dir():
            continue
        char_bucket = {}
        for f in sorted(entry.iterdir(), key=lambda p: p.name):
            if f.name.startswith(('.', '_')) or not f.is_file():
                continue
            slot = f.stem.strip()
            if not slot:
                continue
            _pick(char_bucket, slot, f, (entry.name, f.name))
        if char_bucket:
            characters[entry.name] = {slot: pair[1] for slot, pair in char_bucket.items()}

    result = {'scenes': scenes, 'characters': characters}
    if dir_sig is not None:
        if len(_VISUAL_ASSETS_CACHE) >= 16:
            _VISUAL_ASSETS_CACHE.clear()
        _VISUAL_ASSETS_CACHE[cache_key] = (dir_sig, copy.deepcopy(result))
    return result


def view(store, files=None):
    files = files or store._files()
    engine = rr._engine(store.root, store.root)
    memory = (files[rr.FILES[0]] or b'').decode('utf-8')
    bundle_state, _, _ = save_store.load_bundle(store.root, files)
    presence = engine.parse_presence_from_memory(memory)
    location = presence['徐志北']['location']
    cast = scene_cast(presence, memory, location)
    timers = engine.parse_item_timers(memory)
    catalog = (files[rr.FILES[1]] or b'').decode('utf-8')
    active_by_id = {it['id']: it for it in bundle_state['items'].get('active', []) if isinstance(it, dict) and it.get('id')}
    items = []
    for m in engine._ITEM_BLOCK_RE.finditer(engine._active_item_zone(catalog)):
        fields = engine._parse_item_block(m.group(0))
        if not re.fullmatch(r'ITEM-\d+', fields['道具ID']):
            continue
        iid = fields['道具ID']
        t_info = timers.get(iid)
        rec = active_by_id.get(iid) or {}
        giftable = rec.get('giftable', fields.get('可赠予', '是') != '否')
        usage_mode = rec.get('usage_mode') or save_store.infer_usage_mode(
            fields.get('系统效果', ''), bool(giftable), fields.get('使用模式', '')
        )
        items.append({'id': iid, 'name': m.group('name').strip(),
                      'quantity': engine._int_of(fields['数量'], 1),
                      'remaining_turns': t_info['turns'] if t_info else None,
                      'giftable': bool(giftable),
                      'usage_mode': usage_mode,
                      'category': rec.get('category', ''),
                      'fields': fields})
    deployed_items = [
        {
            'id': it['id'],
            'name': it['name'],
            'quantity': it.get('quantity', 1),
            'usage_mode': it.get('usage_mode', 'deployable_device'),
            'category': it.get('category', 'covert'),
            'location': it.get('location', ''),
            'spot': it.get('spot', '隐蔽角落'),
            'hidden': bool(it.get('hidden', True)),
            'installed_clock': it.get('installed_clock', ''),
            'detected_risk': int(it.get('detected_risk', 0) or 0),
            'desc': it.get('desc', ''),
            'system_effect': it.get('system_effect', ''),
            'usage_record': it.get('usage_record', ''),
            'status': it.get('status', '已部署'),
        }
        for it in bundle_state['items'].get('deployed', [])
        if isinstance(it, dict) and it.get('id')
    ]
    delivered_items = [
        {
            'id': it['id'],
            'name': it['name'],
            'quantity': it['quantity'],
            'target': it.get('target', ''),
            'type': it.get('type', '永久性'),
            'desc': it.get('desc', ''),
            'note': it.get('note') or it.get('remark', ''),
            'remark': it.get('remark') or it.get('note', ''),
            'status': it.get('status', '已交付'),
        }
        for it in bundle_state['items'].get('delivered', [])
        if isinstance(it, dict) and it.get('id')
    ]
    panel = memory.split('▶ 上回合历史快照', 1)[0]
    panels = [line for line in panel.splitlines() if line.startswith('[')]
    data = json.loads(files.get('data.json') or b'{}')
    runtime = sp.state(store.root, files) if sp.enabled(store.root) else None
    weekday = sp.derive_weekday(data, memory, (runtime or {}).get('clock'), save_state=bundle_state)
    intl_snap = copy.deepcopy(bundle_state.get('intimate') or save_store.default_intimate())
    tier_costs = sp.active_costs(store.root, files) if runtime is not None else dict(sp.COSTS)
    guard_info = sp.stamina_guard_info(store.root, files) if runtime is not None else {'active': False, 'floor': 10, 'vigor': 100, 'min_vigor': 15}
    intl_snap['active_costs'] = tier_costs
    intl_snap['stamina_guard'] = guard_info
    progression = {'runtime': runtime, 'stamina': sp.stamina(store.root, files),
                   'costs': tier_costs, 'base_costs': sp.COSTS,
                   'intimate_mode': bool(intl_snap.get('scene_active')),
                   'stamina_guard': guard_info,
                   'item_budget': 20 - runtime['item_recovered']} if runtime is not None else None
    intel_cat = sp.load_intel_catalog(store.root, optional=True)
    intel_state = sp.parse_intel_block(memory)
    interaction_meta = data.get('interaction')
    if not isinstance(interaction_meta, dict):
        rt_meta = bundle_state.get('runtime') or {}
        interaction_meta = {'count': 0, 'actions': 0}
        if rt_meta.get('last_sequence'):
            interaction_meta['last_sequence'] = rt_meta['last_sequence']
        if rt_meta.get('last_segment_id'):
            interaction_meta['segment_id'] = rt_meta['last_segment_id']
    parsed_buffs = engine.parse_persistent_buffs(memory)
    cur_day = int(((runtime or {}).get('clock') or {}).get('day') or ((bundle_state.get('runtime') or {}).get('clock') or {}).get('day') or 1)
    mech = bundle_state.get('mechanics') or {}
    latent_map = mech.get('pregnancy_latent_until') or {}
    trace_map = mech.get('masturbation_trace') or {}
    counters_map = bundle_state.get('counters') or {}
    panels_dict = bundle_state.get('panels') or {}
    host_charm_val = int(((panels_dict.get('系统宿主') or {}).get('魅力', 70)) or 70)
    host_charm_tier = engine.charm_tier_info(host_charm_val)
    physiology = {}
    for hname in save_store.HEROINES:
        hpanel = panels_dict.get(hname) or {}
        is_preg = bool(hpanel.get('怀孕'))
        lat_until = int(latent_map.get(hname, 0) or 0)
        lat_left = max(0, lat_until - cur_day) if (not is_preg and lat_until > cur_day) else 0
        c_phase = engine.determine_cycle_phase(hname, cur_day)
        fl_turns = 0
        for bitem in (parsed_buffs.get(hname) or []):
            if isinstance(bitem, dict) and '持续_体液锁定' in str(bitem.get('name', '')):
                fl_turns = int(bitem.get('turns', 0) or 0)
                break
        physiology[hname] = {
            'cycle_phase': '孕期停经' if is_preg else c_phase,
            'pregnancy_stage': 'confirmed' if is_preg else ('latent' if lat_left > 0 else 'none'),
            'latent_days_left': lat_left,
            'creampie_count': int(hpanel.get('内射', 0) or 0),
            'unrelieved_streak': int(counters_map.get(f'空耗_连续未纾解_{hname}', 0) or 0),
            'masturbation_trace': int(trace_map.get(hname, 0) or 0),
            'fluid_lock_turns': fl_turns,
            'fluid_lock_floor': engine.fluid_lock_floor_for_turns(fl_turns, creampie_count=int(hpanel.get('内射', 0) or 0)),
        }
    delivered_intimate_gifts = {}
    for hname in save_store.HEROINES:
        glist = list(((intl_snap.get('attire') or {}).get(hname) or {}).get('gifted_items') or [])
        if glist:
            delivered_intimate_gifts[hname] = glist
    return {'progression': progression, 'weekday': weekday, 'location': location, 'cast': cast,
            'presence': presence, 'panels': panels, 'items': items,
            'deployed_items': deployed_items,
            'delivered_items': delivered_items,
            'delivered_intimate_gifts': delivered_intimate_gifts,
            'intimate': intl_snap,
            'host_charm_tier': host_charm_tier,
            'body_zone_meta': {
                'zones': list(save_store.BODY_ZONES),
                'labels': dict(save_store.BODY_ZONE_LABELS),
                'signatures': dict(save_store.HEROINE_SIGNATURE_ZONES),
                'level_labels': [engine.BODY_DEV_LEVEL_LABELS[i] for i in range(4)],
            },
            'keepsake_meta': {
                'kinds': dict(save_store.KEEPSAKE_KIND_LABELS),
                'methods': dict(save_store.KEEPSAKE_METHOD_LABELS),
                'conditions': dict(save_store.KEEPSAKE_CONDITION_LABELS),
                'actions': dict(save_store.KEEPSAKE_ACTION_LABELS),
            },
            'buffs': parsed_buffs,
            'micro_states': parse_micro_states(memory),
            'physiology': physiology,
            'visual_assets': scan_visual_assets(store.root),
            'vigilance': parse_public_vigilance(memory, save_state=bundle_state),
            'passive_tiers': [dict(x) for x in sp.passive_levels(store.root)],
            'secrets_unlocked': list(mech.get('secrets_unlocked', [])),
            'intel': {
                **intel_state,
                'leverage_min_biz': intel_cat.get('leverage_min_biz', 60),
                'catalog': intel_cat.get('items', []),
            },
            'tasks': engine._parse_task_block(memory),
            'shop_state': sp.parse_shop_echo_block(memory),
            'interaction': interaction_meta,
            'policy': policy(store.root)}


def location_aliases(root):
    configured=policy(root);aliases=configured.get('location_aliases',{})
    if (not isinstance(aliases,dict) or any(not isinstance(k,str) or not k.strip() or len(k)>40
            or not isinstance(v,str) or v not in configured['locations']
            or k in configured['locations'] and k!=v for k,v in aliases.items())):
        raise rr.RoundError('地点别名配置无效')
    return aliases


def travel_intent(root, text):
    """Resolve only a direct present player command, using registered aliases."""
    names={name:name for name in policy(root)['locations']};names.update(location_aliases(root))
    options='|'.join(re.escape(n) for n in sorted(names,key=len,reverse=True))
    lead=r'(?:(?:我)?(?:起身|站起身|收起[^\n，,。！？?]{0,6}|放下[^\n，,。！？?]{0,6}|喝完[^\n，,。！？?]{0,4}|告别|告辞|道别|出门|下楼|拿上[^\n，,。！？?]{0,6}|换好[^\n，,。！？?]{0,6})(?:[，,、\s]|告辞|出门|道别)*)?'
    verbs=r'(?:回到|返回|前往|走到|出发去|赶去|打车去|打车回|开车去|开车回|坐车去|坐车回|乘车去|乘车回|动身去|动身回|回|去)'
    match=re.fullmatch(r'\s*'+lead+r'(?:我)?(?:现在|这就|马上|直接|先)?(?:要)?\s*('+verbs+r')\s*('
                       +options+r')(?=$|[\s，,。！!；;、]|看看|查看|看|找|问|探望|确认|一趟|一下|吧)(.*)',text,re.S)
    if not match:return None
    tail=match[3]
    if re.search(r'还是|或者|要不要|是否前往|[？?]|(?:明天|后天|下午|晚上|稍后|以后|待会|等会|如果|假如|到时候)',tail):return None
    if re.search(verbs+r'\s*(?:'+options+r')',tail):return None
    return {'operation':{'code':'move_player','destination':names[match[2]]},
            'matched_text':match[1]+match[2],'destination_text':match[2],'input':text}


_RECIPIENT_ALIASES = {
    '沈知韫': ('沈知韫', '知韫', '妈', '妈妈', '母亲', '伯母'),
    '苏婉青': ('苏婉青', '婉青', '嫂子', '大嫂'),
    '徐念薇': ('徐念薇', '念薇', '念薇姐', '姐姐', '姐'),
    '徐承邺': ('徐承邺', '承邺', '大哥', '哥'),
}
humanize_item_effect = sc.humanize_item_effect
match_item_in_text = sc.match_item_in_text
find_mentioned_items = sc.find_mentioned_items


def _recipient_mentioned_in_text(text, who, cast_here):
    txt = str(text or '')
    if not txt or not who:
        return False
    if who in txt:
        return True
    aliases = _RECIPIENT_ALIASES.get(who, (who,))
    if any(a in txt for a in aliases):
        # Verify no other in-scene person shares this alias
        other_hits = [
            c for c in (cast_here or ())
            if c != who and any(a in txt for a in _RECIPIENT_ALIASES.get(c, (c,)))
        ]
        if not other_hits:
            return True
    if len(cast_here or ()) == 1 and cast_here[0] == who and re.search(r'送她|递给她|给她|交给她|赠予她|递过去', txt):
        return True
    return False


def operation(root, files, proposed, text='', explicit=False):
    """Validate player travel, transfer, item usage, device deployment, retrieval, inspection, and keepsake actions."""
    if proposed is None:
        return None
    rr._keys(
        proposed,
        {'code', 'destination', 'item_id', 'recipient', 'quantity', 'target', 'spot', 'hidden', 'keepsake_id', 'action_type'},
        'operation',
        {'code'},
    )
    if proposed['code'] == 'use_recovery_item' and sp.enabled(root):
        rr._keys(proposed, {'code', 'item_id'}, 'use_recovery_item', {'code', 'item_id'})
        match = sp.PURE_ITEM.fullmatch(text)
        if not match or match[1] != proposed['item_id']:
            raise rr.RoundError('道具操作必须是明确ID的纯使用恢复指令')
        sp.item_quote(root, files, proposed['item_id'])
        return copy.deepcopy(proposed)
    engine = rr._engine(root, root)
    mem_text = files[rr.FILES[0]].decode('utf-8')
    presence = engine.parse_presence_from_memory(mem_text)
    player_place = presence['徐志北']['location']
    cast_here = scene_cast(presence, mem_text, player_place)
    code = proposed['code']
    if code == 'move_player':
        rr._keys(proposed, {'code', 'destination'}, 'move_player', {'code', 'destination'})
        target = proposed['destination']
        if target not in policy(root)['locations'] or target == player_place:
            raise rr.RoundError('目的地未开放或已经位于该地点')
        intent = travel_intent(root, text) if not explicit else None
        if not explicit and (not intent or intent['operation']['destination'] != target):
            raise rr.RoundError('移动缺少玩家明确目的地与行动依据')
        return copy.deepcopy(proposed)
    if code == 'transfer_item':
        rr._keys(proposed, {'code', 'item_id', 'recipient', 'quantity'}, 'transfer_item', {'code', 'item_id', 'recipient'})
        who = proposed['recipient']
        if who not in cast_here:
            raise rr.RoundError('接收人必须实际在场')
        catalog = (files[rr.FILES[1]] or b'').decode('utf-8')
        if not isinstance(proposed['item_id'], str) or not re.fullmatch(r'ITEM-\d+', proposed['item_id']):
            raise rr.RoundError('道具编号无效')
        found = engine._find_item_block(catalog, item_id=proposed['item_id'])
        if not found:
            raise rr.RoundError('没有该活跃道具')
        fields = engine._parse_item_block(found['block'])
        if fields['当前状态'] != '仓库中' or fields['使用对象'] not in ('', '无', '未使用', '徐志北'):
            raise rr.RoundError('该道具不属于玩家可交付库存')
        item_name = re.search(r'【道具名称】：([^\n]+)', found['block']).group(1).strip()
        bundle_state, _, _ = save_store.load_bundle(root, files)
        active_list = bundle_state['items'].get('active', [])
        rec = next((it for it in active_list if it.get('id') == proposed['item_id']), None)
        non_giftable = (fields.get('可赠予') == '否') or (isinstance(rec, dict) and rec.get('giftable') is False)
        if not non_giftable:
            shop_cat = sp.load_shop_catalog(root, optional=True)
            for shop_it in shop_cat.get('items', []):
                if shop_it.get('name') == item_name and shop_it.get('giftable') is False:
                    non_giftable = True
                    break
        if non_giftable:
            raise rr.RoundError('该道具为宿主专用不可赠予物品')
        qty = engine._int_of(fields.get('数量', '1'), 1)
        if 'quantity' in proposed and proposed['quantity'] is not None:
            rr._integer(proposed['quantity'], 'transfer_item.quantity', 1)
            if proposed['quantity'] > qty:
                raise rr.RoundError('交付数量超过当前库存')
        item_stub = rec if isinstance(rec, dict) else {'id': proposed['item_id'], 'name': item_name}
        if not explicit and (not _recipient_mentioned_in_text(text, who, cast_here)
                             or not re.search(r'交给|送给|递给|赠给|赠予|送出|递过去|送她|给她', text)
                             or not match_item_in_text(text, item_stub, active_list)
                             or (qty > 1 and proposed.get('quantity') is None and not re.search(r'整组|全部|所有', text))):
            raise rr.RoundError('交付缺少玩家明确接收人依据')
        return copy.deepcopy(proposed)
    if code == 'use_item':
        rr._keys(proposed, {'code', 'item_id', 'target'}, 'use_item', {'code', 'item_id'})
        if not isinstance(proposed['item_id'], str) or not re.fullmatch(r'ITEM-\d+', proposed['item_id']):
            raise rr.RoundError('道具编号无效')
        bundle_state, _, _ = save_store.load_bundle(root, files)
        active_list = bundle_state['items'].get('active', [])
        rec = next((it for it in active_list if it.get('id') == proposed['item_id']), None)
        if rec is None or rec.get('status') != '仓库中' or int(rec.get('quantity', 0)) < 1:
            raise rr.RoundError('该活跃道具不存在或不可使用')
        if rec.get('usage_mode') == 'consumable_host' or str(rec.get('system_effect', '')).startswith('host_stamina:'):
            raise rr.RoundError('宿主体力恢复道具请通过免费恢复入口使用')
        target = str(proposed.get('target') or '').strip()
        if target and target not in ('室内', '室内氛围', '当前场景', '全员') and target not in cast_here:
            raise rr.RoundError('道具作用目标必须实际在场')
        if not explicit and not match_item_in_text(text, rec, active_list):
            raise rr.RoundError('使用道具缺少玩家原文依据')
        out = {'code': 'use_item', 'item_id': proposed['item_id']}
        if target:
            out['target'] = target
        return out
    if code == 'deploy_item':
        rr._keys(proposed, {'code', 'item_id', 'spot', 'hidden'}, 'deploy_item', {'code', 'item_id'})
        if not isinstance(proposed['item_id'], str) or not re.fullmatch(r'ITEM-\d+', proposed['item_id']):
            raise rr.RoundError('装置编号无效')
        bundle_state, _, _ = save_store.load_bundle(root, files)
        active_list = bundle_state['items'].get('active', [])
        rec = next((it for it in active_list if it.get('id') == proposed['item_id']), None)
        if rec is None or rec.get('status') != '仓库中' or int(rec.get('quantity', 0)) < 1:
            raise rr.RoundError('待部署装置不存在或不可用')
        if rec.get('usage_mode') != 'deployable_device' and not str(rec.get('system_effect', '')).startswith('deploy_device:'):
            raise rr.RoundError('该道具不是可部署的场景装置')
        spot = str(proposed.get('spot') or '隐蔽角落').strip() or '隐蔽角落'
        if len(spot) > 40 or '\n' in spot or '\r' in spot:
            raise rr.RoundError('安装点位须为40字内单行文本')
        hidden = proposed.get('hidden', True)
        if type(hidden) is not bool:
            raise rr.RoundError('隐蔽部署标记须为布尔值')
        if not explicit and not match_item_in_text(text, rec, active_list):
            raise rr.RoundError('部署装置缺少玩家原文依据')
        return {'code': 'deploy_item', 'item_id': proposed['item_id'], 'spot': spot, 'hidden': hidden}
    if code == 'retrieve_item':
        rr._keys(proposed, {'code', 'item_id'}, 'retrieve_item', {'code', 'item_id'})
        if not isinstance(proposed['item_id'], str) or not re.fullmatch(r'ITEM-\d+', proposed['item_id']):
            raise rr.RoundError('已部署装置编号无效')
        bundle_state, _, _ = save_store.load_bundle(root, files)
        deployed_list = bundle_state['items'].get('deployed', [])
        dev = next((it for it in deployed_list if it.get('id') == proposed['item_id']), None)
        if dev is None:
            raise rr.RoundError('未找到该已部署装置')
        if dev.get('location') != player_place:
            raise rr.RoundError(f"须先回到装置所在地点（{dev.get('location')}）才能拆除回收")
        if not explicit:
            local_devs = [d for d in deployed_list if d.get('location') == player_place]
            has_verb = bool(re.search(r'拆除|回收|拆下|拆掉|收回来|取回|拿回|摘下|取下', text or ''))
            if not match_item_in_text(text, dev, local_devs) and not (has_verb and len(local_devs) == 1):
                raise rr.RoundError('回收装置缺少玩家原文依据')
        return {'code': 'retrieve_item', 'item_id': proposed['item_id']}
    if code == 'inspect_deployed':
        rr._keys(proposed, {'code', 'item_id'}, 'inspect_deployed', {'code', 'item_id'})
        if not isinstance(proposed['item_id'], str) or not re.fullmatch(r'ITEM-\d+', proposed['item_id']):
            raise rr.RoundError('已部署装置编号无效')
        bundle_state, _, _ = save_store.load_bundle(root, files)
        deployed_list = bundle_state['items'].get('deployed', [])
        dev = next((it for it in deployed_list if it.get('id') == proposed['item_id']), None)
        if dev is None:
            raise rr.RoundError('未找到可远程查看的已部署装置')
        if not explicit:
            has_inspect = bool(re.search(r'远程|监控|画面|针孔|摄像头|录音|监听|窃听|回看|回听|查看.*装置|看一眼.*画面', text or ''))
            if not match_item_in_text(text, dev, deployed_list) and not (has_inspect and len(deployed_list) == 1):
                raise rr.RoundError('远程查看装置缺少玩家原文依据')
        return {'code': 'inspect_deployed', 'item_id': proposed['item_id']}
    if code == 'keepsake_action':
        rr._keys(proposed, {'code', 'keepsake_id', 'action_type'}, 'keepsake_action', {'code', 'keepsake_id', 'action_type'})
        ks_id = str(proposed.get('keepsake_id') or '').strip()
        act_type = str(proposed.get('action_type') or '').strip()
        if not re.fullmatch(r'KS-\d+', ks_id):
            raise rr.RoundError('私密珍藏编号无效')
        if act_type not in save_store.KEEPSAKE_ACTIONS:
            raise rr.RoundError('不支持的私密珍藏互动方式')
        bundle_state, _, _ = save_store.load_bundle(root, files)
        ks_list = (bundle_state.get('intimate') or {}).get('keepsakes') or []
        ks = next((it for it in ks_list if isinstance(it, dict) and it.get('id') == ks_id), None)
        if ks is None:
            raise rr.RoundError('该私密珍藏物品不存在或已归还')
        owner = ks.get('owner', '')
        if act_type in ('confront', 'use_intimate') and owner not in cast_here:
            raise rr.RoundError(f'当面出示或亲密复用须与失主 {owner} 身处同一场景')
        if act_type == 'return_secret':
            owner_loc = (presence.get(owner) or {}).get('location', '')
            home_ok = (owner in ('沈知韫', '徐念薇') and player_place == '徐家主宅') or (owner == '苏婉青' and player_place == '市中心顶层公寓')
            if not (owner in cast_here or player_place == ks.get('location') or player_place == owner_loc or home_ok):
                raise rr.RoundError(f"悄悄放回须在 {owner} 居所或原藏匿处（{ks.get('location') or '失主住处'}）")
        return {'code': 'keepsake_action', 'keepsake_id': ks_id, 'action_type': act_type}
    raise rr.RoundError('未登记的正式行动；请先明确可执行范围')


def validate(root, request, files):
    required = {'schema_version', 'entry_mode', 'request_id', 'base_revision', 'input', 'messages', 'operation', 'handoff', 'audit'}
    modern = request.get('schema_version') in (2, 3)
    charged = request.get('schema_version') == 3
    if sp.enabled(root) and not charged:
        raise rr.RoundError('现役收费入口须使用schema3及正式预扣')
    if charged:
        required.add('resolution')
    if modern:
        required |= {'decision', 'selection'}
    rr._keys(request, required, 'continuous_request', required)
    if type(request['schema_version']) is not int or request['schema_version'] not in (1, 2, 3) or request['entry_mode'] != MODE:
        raise rr.RoundError('正式互动协议无效')
    if not isinstance(request['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', request['request_id']):
        raise rr.RoundError('请求编号无效')
    if request['base_revision'] != rr._revision(files):
        raise rr.ConflictError('正式存档已改变，请恢复最新状态')
    rr._text(request['input'], 'input', 2000)
    checked_files = dict(files)
    if charged:
        import base64
        reservation = request.get('audit', {}).get('reservation', {})
        try: checked_files[rr.FILES[0]] = base64.b64decode(reservation['before_memory'], validate=True)
        except (ValueError, KeyError, TypeError) as exc: raise rr.RoundError('预扣原文缺失') from exc
    audit_obj = request.get('audit') if isinstance(request.get('audit'), dict) else {}
    req_op = audit_obj.get('requested_operation') if 'requested_operation' in audit_obj else request.get('operation')
    selection(root, checked_files, request.get('selection'), request['input'],
              command=req_op, allow_handoff_drop=bool(request.get('handoff')))
    if modern:
        decision(request['decision'], valid_locations=policy(root)['locations'])
    audit = request['audit']
    if not isinstance(audit, dict) or audit.get('required_reads_verified') is not True:
        raise rr.RoundError('缺少正式接受依据')
    proposed = operation(root, checked_files, request['operation'], request['input'], audit.get('origin') == 'player_action')
    mem_text = files[rr.FILES[0]].decode('utf-8')
    presence = rr._engine(root, root).parse_presence_from_memory(mem_text)
    location = presence['徐志北']['location']
    eff_loc = proposed['destination'] if (proposed and proposed['code'] == 'move_player') else location
    allowed = set(scene_cast(presence, mem_text, eff_loc))
    messages = request['messages']
    if not isinstance(messages, list) or not 1 <= len(messages) <= (1000 if modern else 12):
        raise rr.RoundError('剧情须为非空节点数组，传输最多1000节点；不作为正文篇幅预算')
    allow_player_dlg = modern and load_story_prefs(root)['protagonist_style'] == 'faithful'
    player_dlg_count = 0
    for m in messages:
        rr._keys(m, {'kind', 'speaker', 'text'}, 'message', {'kind', 'speaker', 'text'})
        rr._text(m['text'], 'message.text', 4000)
        if m['kind'] not in ('dialogue', 'action', 'narration'):
            raise rr.RoundError('消息类型无效')
        if m['kind'] == 'narration':
            if m['speaker'] != '':
                raise rr.RoundError('旁白不带说话人')
        elif not isinstance(m['speaker'], str):
            raise rr.RoundError('角色不在场或模型代写玩家台词：'+m['kind']+' / '+str(m['speaker']))
        elif m['speaker'] in allowed:
            pass
        elif modern and m['kind'] == 'action' and m['speaker'] == '徐志北':
            pass
        elif allow_player_dlg and m['kind'] == 'dialogue' and m['speaker'] == '徐志北':
            player_dlg_count += 1
            if player_dlg_count > sc.MAX_PLAYER_DIALOGUE_PER_TURN:
                raise rr.RoundError(
                    f'主角代写台词过多（单幕上限 {sc.MAX_PLAYER_DIALOGUE_PER_TURN} 句），请精简至贴合玩家意图的 1～2 句简短发言'
                )
        else:
            raise rr.RoundError('角色不在场或模型代写玩家台词：'+m['kind']+' / '+str(m['speaker']))
    if not isinstance(request['handoff'], str) or len(request['handoff']) > 300:
        raise rr.RoundError('待处理说明无效')
    if proposed and request['handoff']:
        raise rr.RoundError('待处理行动不得同时宣称执行')
    if charged:
        sp.resolution(root, files, request)
    else:
        quote(root, files, proposed)
    return copy.deepcopy(request)


def settle(store, body, files, sequence, request_id):
    """No legacy round timers, random rolls, auto tasks, or L1 rotation per message."""
    import shutil
    import tempfile
    stage = Path(tempfile.mkdtemp(prefix='work-', dir=store.runtime))
    try:
        for name, raw in files.items():
            if raw is not None:
                rr._atomic(stage / name, raw)
        engine = rr._engine(store.root, stage)
        before_mem = files[rr.FILES[0]].decode('utf-8')
        before_presence = engine.parse_presence_from_memory(before_mem)
        display_files = dict(files)
        if body['schema_version'] == 3:
            import base64
            display_files[rr.FILES[0]] = base64.b64decode(body['audit']['reservation']['before_memory'],validate=True)
        before_world = view(store, display_files)
        op = body['operation']
        charged = body['schema_version'] == 3
        settlement = None; runtime = None; scene_known_by = None
        if charged:
            parsed = sp.resolution(store.root, files, body)
            cost = parsed['cost']
            runtime, settlement = sp.apply_staged(store, engine, stage, body, files, parsed)
            if isinstance(settlement, dict) and '_scene_known_by' in settlement:
                scene_known_by = settlement.pop('_scene_known_by')
        else: cost = quote(store.root, files, op)
        if not charged and cost['status'] == 'active':
            memory_path = stage / rr.FILES[0]
            memory = memory_path.read_text(encoding='utf-8')
            memory = engine._simulate_panel(memory, {'系统宿主': {cost['attribute']: cost['after']}})
            rr._atomic(memory_path, memory.encode('utf-8'))
        if op and not charged:
            rr._engine_call(engine.apply_interaction_operation, op)
        after = {name: (stage / name).read_bytes() if (stage / name).is_file() else None for name in rr.FILES}
        after_mem = after[rr.FILES[0]].decode('utf-8')
        presence = engine.parse_presence_from_memory(after_mem)
        data = json.loads(after['data.json'] or b'{}')
        count = data.get('interaction', {}).get('count', 0) + 1
        actions = data.get('interaction', {}).get('actions', 0) + bool(op)
        data.update(presence=presence, state_version=sequence, request_id=request_id,
                    interaction={'count': count, 'actions': int(actions), 'last_sequence': sequence},
                    sceneTitle=presence['徐志北']['location'], options_text='')
        modern = body['schema_version'] in (2, 3)
        if charged:
            data.update(story_runtime=runtime, last_settlement=settlement, round=runtime['memory_round'])
        if modern:
            data['interaction']['segment_id'] = request_id
        data['storyNodes'] = [{'type': 'dialogue' if m['kind'] == 'dialogue' else 'narration',
                               **({'speaker': m['speaker']} if m['kind'] == 'dialogue' else {}), 'text': m['text']}
                              for m in body['messages']]
        after['data.json'] = rr._json(data)
        # Keep P3 save_state.json / memory_store.json runtime & hashes synced atomically.
        # For non-charged pure chat without state mutation, keep legacy .txt byte-identical.
        mutated_world = bool(charged or op or cost.get('status') == 'active')
        st_bundle, layers_bundle, _ = save_store.load_bundle(stage, after, sync_txt_drift=bool(op and not charged))
        st_bundle['runtime']['last_sequence'] = sequence
        if modern:
            st_bundle['runtime']['last_segment_id'] = request_id
        if charged and isinstance(runtime, dict):
            for k in ('clock', 'memory_round', 'last_closed', 'phase', 'item_recovered', 'action_index', 'closed_by'):
                if k in runtime:
                    st_bundle['runtime'][k] = copy.deepcopy(runtime[k])
        if isinstance(data.get('prologue'), dict):
            st_bundle['runtime']['prologue'] = copy.deepcopy(data['prologue'])
            live_mem = after[rr.FILES[0]].decode('utf-8') if after.get(rr.FILES[0]) else ''
            live_wd = sp.derive_weekday(data, live_mem, st_bundle['runtime'].get('clock'), save_state=st_bundle)
            if live_wd:
                st_bundle['runtime']['weekday'] = live_wd
        if mutated_world:
            rendered = save_store.render_bundle_bytes(st_bundle, layers_bundle, data_dict=data)
            for rel, raw_b in rendered.items():
                if rel in after:
                    after[rel] = raw_b
        else:
            st_bundle = save_store.normalize_state(st_bundle)
            st_bundle['rendered_sha256'] = {
                'memory_txt': save_store._sha256_bytes(after[rr.FILES[0]]),
                'items_txt': save_store._sha256_bytes(after[rr.FILES[1]]),
                'data_runtime': save_store._runtime_sig(data),
            }
            after[save_store.SAVE_STATE_PATH] = save_store._json_bytes(st_bundle)
            after[save_store.MEMORY_STORE_PATH] = save_store._json_bytes(save_store.normalize_memory_store(layers_bundle))
        listeners = ['徐志北', *scene_cast(before_presence, before_mem, before_presence['徐志北']['location'])]
        reply_listeners = ['徐志北', *scene_cast(presence, after_mem, presence['徐志北']['location'])]
        if charged and cost['kind']=='item':
            listeners = reply_listeners = ['徐志北']
        elif scene_known_by is not None:
            reply_listeners = list(scene_known_by)
        slim_audit = copy.deepcopy(body['audit'])
        if isinstance(slim_audit, dict) and isinstance(slim_audit.get('reservation'), dict):
            slim_audit['reservation'].pop('before_memory', None)
            slim_audit['reservation'].pop('before_save_state', None)
        accepted = {'version': 1, 'id': request_id, 'sequence': sequence, 'count': count,
                    'input': body['input'], 'input_kind': 'action' if op else 'dialogue',
                    'messages': body['messages'], 'handoff': body['handoff'], 'operation': op,
                    'known_by': sorted(set(listeners) & set(reply_listeners)),
                    'input_known_by': listeners, 'messages_known_by': reply_listeners,
                    'location': before_presence['徐志北']['location'],
                    'after_location': presence['徐志北']['location'],
                    'created_at': time.time(), 'cost': cost, 'audit': slim_audit}
        pb_obj = None
        if modern:
            accepted.update(version=2, decision=body['decision'], selection=body['selection'], before_world=before_world)
            if charged:
                accepted.update(settlement=settlement, resolution=body['resolution'])
            pb_obj = {'version': 1, 'segment_id': request_id, 'revealed': 0, 'completed': False}
            after[PLAYBACK] = rr._json(pb_obj)
        after[ARCHIVE + '/' + f'{sequence:012d}.json'] = rr._json(accepted)
        # Dual-write rolling recent 12 segments + playback into self-contained 存档/近期演播.json.
        recent_path = store._path(rr.RECENT_PLAYBACK)
        existing_recent = save_store.default_recent()
        if recent_path.is_file():
            try:
                existing_recent = json.loads(recent_path.read_text(encoding='utf-8'))
            except ValueError:
                existing_recent = save_store.default_recent()
        updated_recent = save_store.append_recent_segment(existing_recent, accepted, playback_state=pb_obj)
        after[rr.RECENT_PLAYBACK] = rr._json(updated_recent)
        return after
    finally:
        shutil.rmtree(stage)


def _source_ref(memory, entry, offset, layer):
    begin = memory.index(entry,offset)
    return {'layer':layer, 'range':entry.split('】',1)[0]+'】', 'path':rr.FILES[0],
            'start_line':memory.count('\n',0,begin)+1,
            'end_line':memory.count('\n',0,begin+len(entry))+1, 'characters':len(entry)}


def _relevance(text, query):
    chunks = re.findall(r'[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}',query)
    terms = {term for chunk in chunks for term in ([chunk] if chunk.isascii() else [chunk[i:i+2] for i in range(len(chunk)-1)])}
    terms -= {'继续','今天','怎么','一下','这里','当前','剧情','自己','安排'}
    return sum(term in text for term in terms)


def _project_memory_header(header, *, cast=None, is_single=True):
    """Strip redundant snapshot and bulky machine blocks from pre-L1 projection to stay permanently below context_chars//2."""
    if not header:
        return ''
    text = re.sub(r'^#[^\n]*\n+', '', header)
    text = re.sub(r'\n*【当前激活微状态】[\s\S]*?(?=\n={5,}|\n▶ 上回合历史快照|\n【|\Z)', '', text)
    text = re.sub(r'\n*▶ 上回合历史快照[\s\S]*?(?=\n={5,}\n【当前持久化状态与BUFF】|\n【当前持久化状态与BUFF】|\Z)', '', text)
    for anchor in ('【回合计数器】', '【商城与回响状态】', '【商业情报与杠杆状态】', '【世界导演状态】', '【回合生命周期】'):
        text = re.sub(rf'\n*{re.escape(anchor)}[\s\S]*?(?=\n【|\Z)', '', text)
    if not is_single:
        text = re.sub(r'\n*【情欲与空间态势】[\s\S]*?(?=\n【|\Z)', '', text)
        # Foreground writer sanitization: hide raw 发现几率, offstage NPC coordinates, and host points/EXP.
        text = re.sub(r'\s*\|\s*发现几率\s*\d+%?', '', text)
        if cast is not None:
            visible_who = set(cast) | {'徐志北'}
            def _filter_presence(match):
                kept = []
                for line in match.group(1).splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    who = stripped.split('：', 1)[0].strip()
                    if who in visible_who:
                        kept.append(line)
                return '【人物所在】\n' + '\n'.join(kept) + ('\n' if kept else '')
            text = re.sub(r'【人物所在】\n([\s\S]*?)(?=\n【|\n={5,}|\Z)', _filter_presence, text)
        def _strip_host_points(match):
            parts = [seg.strip() for seg in match.group(1).split('|') if not re.match(r'^(?:积分|经验值)\s+', seg.strip())]
            return '[系统宿主] ' + ' | '.join(parts)
        text = re.sub(r'^\[系统宿主\]\s*(.*)$', _strip_host_points, text, flags=re.M)
    text = re.sub(r'(?:\n={5,}\s*){2,}', '\n==================================================\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


_LAYER_PRIORITY = {'L1': 4, 'L2': 3, 'L3': 2, 'L4': 1}


def memory_context(root, memory, query, runtime, *, cast=None, location='', is_single=True):
    """Select complete source entries; omitted entries remain addressable by exact ranges."""
    engine=rr._engine(Path(root),Path(root));layers=engine._parse_memory_layer_items(memory)
    limits=sp.memory_policy(root);budget=limits['context_chars']
    entries=[];cursor=memory.index('▲ 第一层：')
    for layer,items in layers.items():
        for intra_idx, item in enumerate(items):
            ref=_source_ref(memory,item,cursor,layer)
            cursor=memory.index(item,cursor)+len(item)
            entries.append((item,ref,intra_idx))
    raw_header=memory[:memory.index('▲ 第一层：')].strip()
    header=_project_memory_header(raw_header, cast=cast, is_single=is_single)
    chosen=[];used=0
    # Compact projected machine state stays far below budget//2; only a pathological header falls back to explicit read.
    head=header if len(header)<=budget//2 else ''
    used=len(head)
    enriched_query = ' '.join(s for s in (query or '', location or '', ' '.join(cast or ())) if s)
    l4_indices = [i for i, (item, ref, _) in enumerate(entries) if ref['layer'] == 'L4' and len(item) <= 240]
    pinned_l4 = set(l4_indices[-2:])
    rel_scores = [_relevance(item, enriched_query) for item, _, _ in entries]
    raw_query_scores = [_relevance(item, query or '') for item, _, _ in entries]
    ranked=sorted(
        enumerate(entries),
        key=lambda pair:(
            pair[1][1]['layer']=='L1',
            pair[0] in pinned_l4,
            rel_scores[pair[0]],
            _LAYER_PRIORITY.get(pair[1][1]['layer'],0),
            pair[1][2],
        ),
        reverse=True,
    )
    for index,(item,ref,_intra) in ranked:
        if used+len(item)+1<=budget:
            chosen.append(index);used+=len(item)+1
    selected=set(chosen)
    projected='\n'.join(([head] if head else [])+[entries[i][0] for i in sorted(selected)])
    omitted=[ref for i,(_,ref,_intra) in enumerate(entries) if i not in selected]
    index_refs=[entries[i][1] for i,_ in ranked if i not in selected][:limits['index_entries']]
    recalled_old=[
        {'layer': entries[i][1]['layer'], 'range': entries[i][1]['range'], 'body': entries[i][0]}
        for i, _ in ranked
        if i in selected and entries[i][1]['layer'] != 'L1' and raw_query_scores[i] > 0
    ][:3]
    number=runtime['last_closed'] if runtime['phase']=='resting' and runtime['last_closed'] else runtime['memory_round']
    current=next(((item,ref) for item,ref,_intra in entries if ref['layer']=='L1' and item.startswith('【'+str(number)+'】')),None)
    required=[];allowed=list(index_refs)
    def demand(ref):
        if ref not in allowed:allowed.append(ref)
        if ref not in required:required.append(ref)
    if not head and raw_header:
        demand({'path':rr.FILES[0],'start_line':1,'end_line':memory[:memory.index('▲ 第一层：')].count('\n'),'characters':len(raw_header),'layer':'state'})
    current_ref=None
    if current:
        item,current_ref=current
        if current_ref not in [entries[i][1] for i in selected]:demand(current_ref)
    transfer_sources={}
    is_v2_mem_store = (Path(root) / save_store.MEMORY_STORE_PATH).is_file()
    if (not is_v2_mem_store) and current is None and len(layers['L1'])==3:
        for key,layer,source in [('l1_to_l2_condensed','L1',layers['L1'][:1]),
                                  ('l2_to_l3_summary','L2',layers['L2'] if len(layers['L2'])==10 else []),
                                  ('l3_to_l4_summary','L3',layers['L3'] if len(layers['L2'])==10 and len(layers['L3'])==10 else [])]:
            if source:
                refs=[ref for item,ref,_intra in entries if ref['layer']==layer and item in source]
                transfer_sources[key]=refs
                for ref in refs:
                    if ref not in [entries[i][1] for i in selected]:demand(ref)
    return {'text':projected,'selected':[entries[i][1] for i in sorted(selected)],
            'all_entries':[{'source':ref,'preview':item[:80]} for item,ref,_intra in entries],
            'all_refs':[ref for _,ref,_intra in entries],
            'recalled_old_entries': recalled_old,
            'omitted_count':len(omitted),'index':index_refs,'allowed':allowed,'required':required,
            'current':current_ref,'transfers':transfer_sources,'limits':limits}


def bounded_history(candidates, limits):
    chosen=[];used=2
    for path,safe in reversed(candidates):
        size=len(json.dumps(safe,ensure_ascii=False,separators=(',',':')))+1
        if len(chosen)>=limits['history_turns'] or used+size>limits['history_chars']:
            break
        chosen.append((path,safe));used+=size
    return list(reversed(chosen))


def encode_live_packet(data):
    """Lossless physical line breaks between JSON tokens, including nested objects."""
    raw=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    out=[];quoted=False;escaped=False
    for char in raw:
        out.append(char)
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '{[,':out.append('\n')
        elif char in '}]':out.append('\n')
    return (''.join(out).rstrip('\n')+'\n').encode('utf-8')


def packet_read_ranges(raw):
    """Bound returned source text rather than counting many short JSON syntax lines."""
    lines=raw.decode('utf-8').splitlines();ranges=[];begin=1;chars=0;byte_count=0
    for number,line in enumerate(lines,1):
        cost=len(line)+len(str(number))+4
        encoded=len(line.encode('utf-8'))+len(str(number))+4
        if number>begin and (chars+cost>9000 or byte_count+encoded>24000):
            ranges.append({'start_line':begin,'end_line':number-1})
            begin=number;chars=0;byte_count=0
        chars+=cost;byte_count+=encoded
    if lines:ranges.append({'start_line':begin,'end_line':len(lines)})
    return ranges


def _describe_operation_context(resolved, state, bundle_state, mem_text):
    """Build rich deterministic context for explicit item/device operations so Stage 1 narrates accurate physical facts."""
    if not isinstance(resolved, dict):
        return None
    code = resolved.get('code')
    active_list = (bundle_state.get('items') or {}).get('active') or []
    deployed_list = (bundle_state.get('items') or {}).get('deployed') or []
    if code == 'inspect_deployed':
        dev = next((it for it in deployed_list if it.get('id') == resolved.get('item_id')), None)
        if not dev:
            return None
        dev_loc = dev.get('location', '')
        remote_cast = scene_cast(state.get('presence') or {}, mem_text, dev_loc)
        eff = str(dev.get('system_effect') or '')
        feed_kind = '远程监听实时录音' if 'audio' in eff else ('远程感知室内状态' if 'aroma' in eff else '加密手机端远程查看针孔实时画面')
        return {
            'kind': 'inspect_deployed',
            'device': {
                'id': dev['id'], 'name': dev['name'], 'location': dev_loc,
                'spot': dev.get('spot') or '隐蔽角落', 'hidden': bool(dev.get('hidden', True)),
                'installed_clock': dev.get('installed_clock', ''), 'desc': dev.get('desc', ''),
            },
            'remote_location': dev_loc,
            'remote_cast': remote_cast,
            'instruction': (
                f"玩家正通过{feed_kind}，目标装置「{dev['name']}」暗藏于【{dev_loc} · {dev.get('spot') or '隐蔽角落'}】。"
                f"此刻该地点真实在场人物为：{('、'.join(remote_cast) if remote_cast else '空无一人')}。"
                "请用 [N] 旁白与 [A:徐志北] 细腻描写主角透过屏幕/耳机窥见的该处实时私密画面或听到的真实动静（遵循信息差，严禁把远程人物写成 [D:远程人物] 台词行，远处人声一律在 [N] 中用引号自然呈现）。"
            ),
        }
    if code == 'deploy_item':
        item = next((it for it in active_list if it.get('id') == resolved.get('item_id')), None)
        if not item:
            return None
        spot = resolved.get('spot') or '隐蔽角落'
        hidden = bool(resolved.get('hidden', True))
        return {
            'kind': 'deploy_item',
            'item': {'id': item['id'], 'name': item['name'], 'desc': item.get('desc', ''), 'system_effect': item.get('system_effect', '')},
            'location': state.get('location', ''),
            'spot': spot,
            'hidden': hidden,
            'instruction': (
                f"玩家将「{item['name']}」{'暗中隐蔽' if hidden else '公开'}安装于【{state.get('location', '')} · {spot}】。"
                + ("当前室内有他人在场，须描写主角借动作掩护悄然落位的紧张感与被瞥见风险，不直接戳破。" if (hidden and state.get('cast')) else "可自然描写安装固定与调试成功的触感细节。")
            ),
        }
    if code == 'retrieve_item':
        dev = next((it for it in deployed_list if it.get('id') == resolved.get('item_id')), None)
        if not dev:
            return None
        desc_short = str(dev.get('desc') or '').strip()[:80]
        return {
            'kind': 'retrieve_item',
            'device': {
                'id': dev['id'], 'name': dev['name'], 'location': dev.get('location', ''),
                'spot': dev.get('spot', ''), 'desc': desc_short,
            },
            'instruction': (
                f"玩家在【{dev.get('location', '')} · {dev.get('spot') or '原位'}】将先前部署的「{dev['name']}」"
                + (f"（{desc_short}）" if desc_short else "")
                + "悄然拆除收回随身。"
            ),
        }
    if code == 'use_recovery_item':
        item = next((it for it in active_list if it.get('id') == resolved.get('item_id')), None)
        if not item:
            return None
        cur_qty = max(1, int(item.get('quantity', 1) or 1))
        after_qty = max(0, cur_qty - 1)
        qty_note = '最后1份用尽' if after_qty == 0 else f'消耗1份，用后余{after_qty}份'
        desc_txt = str(item.get('desc') or '').strip()[:120]
        return {
            'kind': 'use_recovery_item',
            'item': {'id': item['id'], 'name': item['name'], 'desc': desc_txt},
            'quantity_after': after_qty,
            'instruction': (
                f"玩家原地顺手服用/使用了随身提神物品「{item['name']}」（{desc_txt}；{qty_note}）以缓和疲惫、提振精神。"
                "请以1～2句简短日常感官动作（口感、清凉/苦香、呼吸微定）自然带过；"
                "严禁推进游戏时间、严禁凭空推进新剧情或触发数值跳步。"
            ),
        }
    if code == 'use_item':
        item = next((it for it in active_list if it.get('id') == resolved.get('item_id')), None)
        if not item:
            return None
        target = resolved.get('target') or '当前场景'
        eff = str(item.get('system_effect') or '')
        eff_human = humanize_item_effect(eff)
        umode = str(item.get('usage_mode') or '')
        is_reusable = (umode == 'reusable_tool')
        cur_qty = max(1, int(item.get('quantity', 1) or 1))
        if is_reusable:
            use_boundary = '随身永久工具，用后保留'
        elif cur_qty <= 1:
            use_boundary = '消耗品，本次最后1份用尽'
        else:
            use_boundary = f'消耗品，消耗1份，用后余{cur_qty - 1}份'
        desc_txt = str(item.get('desc') or '').strip()[:140]
        return {
            'kind': 'use_item',
            'item': {
                'id': item['id'], 'name': item['name'], 'usage_mode': umode,
                'desc': desc_txt, 'effect': eff_human, 'consumption': use_boundary,
            },
            'target': target,
            'instruction': (
                f"玩家在本轮行动中正式动用随身道具「{item['name']}」（目标：{target}；{use_boundary}；质感与用法：{desc_txt}）。"
                + (f"该道具触发【{eff_human}】，请将触感、气味、温热/潮红与神态松动自然融入本幕互动（禁直呼机制或数值词）。" if eff_human else "请将道具实物触感与用法自然融入本幕互动。")
            ),
        }
    if code == 'transfer_item':
        item = next((it for it in active_list if it.get('id') == resolved.get('item_id')), None)
        if not item:
            return None
        qty = resolved.get('quantity') or item.get('quantity', 1)
        return {
            'kind': 'transfer_item',
            'item': {'id': item['id'], 'name': item['name'], 'desc': item.get('desc', '')},
            'recipient': resolved.get('recipient', ''),
            'quantity': qty,
            'instruction': f"玩家将「{item['name']}」×{qty} 亲手赠予在场的 {resolved.get('recipient', '')}（{item.get('desc', '')[:80]}）；请具体描写递交时的手部接触、拆看反应与角色性格回应。",
        }
    if code == 'keepsake_action':
        ks_list = (bundle_state.get('intimate') or {}).get('keepsakes') or []
        ks = next((it for it in ks_list if isinstance(it, dict) and it.get('id') == resolved.get('keepsake_id')), None)
        if not ks:
            return None
        owner = ks.get('owner', '')
        kname = ks.get('name', '')
        act_type = resolved.get('action_type', '')
        cond_lbl = save_store.KEEPSAKE_CONDITION_LABELS.get(ks.get('condition', ''), '尚带余香')
        method_lbl = save_store.KEEPSAKE_METHOD_LABELS.get(ks.get('method', ''), '私密留存')
        aware_str = '失主此前已知晓' if ks.get('owner_aware') else '失主此前浑然未觉'
        reaction_spine = {
            '沈知韫': '端庄克制骤裂、耳根与锁骨泛起潮红、声音压低发颤，羞愤与隐秘悸动交织',
            '苏婉青': '先是一瞬微怔随即唇角挑起危险魅惑的弧度，反客为主试探质问或顺势挑逗',
            '徐念薇': '清冷疏离外壳骤然绷紧、耳尖发烫、眼神冷厉闪躲并强装镇定低声斥责',
        }.get(owner, '神色微妙变化')
        if act_type == 'sniff_play':
            inst = (
                f"玩家取出私密珍藏「{owner}的{kname}」（来源：{method_lbl}；状态：{cond_lbl}；{aware_str}）私下嗅闻把玩。"
                + ("当前室内仍有他人在场，须刻画背身/掩饰的禁忌紧张感与随时被瞥见的窒息节奏；" if state.get('cast') else "独处时刻画布料质感、残留体温/体香与主角欲望急剧上涌的感官细节；")
                + "严禁代打高潮或擅自射精，仅呈现欲望翻涌与把玩张力。"
            )
        elif act_type == 'confront':
            inst = (
                f"玩家当着在场的 {owner} 面亮出私密珍藏「{kname}」（来源：{method_lbl}；状态：{cond_lbl}；{aware_str}）以试探其反应。"
                f"请紧扣 {owner} 性格呈现即时反应（{reaction_spine}），并依据当前堕落/羞耻/好感深度推进羞耻破防或拉扯博弈。"
            )
        elif act_type == 'use_intimate':
            inst = (
                f"玩家在亲密互动中拿出「{owner}的{kname}」（状态：{cond_lbl}；{aware_str}），让 {owner} 重新穿戴、套弄或作为缠绕/擦拭的贴身情趣道具复用。"
                f"请落实布料拉扯、温热贴肤、湿润水痕与 {owner} 羞耻又顺从/挣扎的声息反应（{reaction_spine}）。"
            )
        else:
            inst = (
                f"玩家将此前收存的「{owner}的{kname}」（状态：{cond_lbl}；{aware_str}）悄然放回原处或留置在 {owner} 容易发现的隐蔽位置。"
                f"请细腻刻画归还时的潜行动作与布料折痕/微潮痕迹留下的后续悬念。"
            )
        return {
            'kind': 'keepsake_action',
            'keepsake': {
                'id': ks['id'], 'owner': owner, 'name': kname,
                'kind': ks.get('kind', ''), 'method': ks.get('method', ''),
                'condition': ks.get('condition', ''), 'owner_aware': bool(ks.get('owner_aware')),
                'desc': ks.get('desc', ''),
            },
            'action_type': act_type,
            'instruction': inst,
        }
    return None


def packet(story, prepared, key, text, command=None, previous_error='', selected=None, reservation=None, *, lazy_live_txt=False):
    """Deterministic source extracts, scoped knowledge and original accepted messages."""
    from scene_chat import SceneService, encode_packet
    helper = SceneService(story.root, story)
    files = {n: v.encode('utf-8') if v is not None else None for n, v in prepared['snapshot'].items()}
    state = view(story.store, files)
    bundle_state, _, _ = save_store.load_bundle(story.root, files)
    mem_text = (files[rr.FILES[0]] or b'').decode('utf-8')
    intent=travel_intent(story.root,text)
    if command is None and intent and intent['operation']['destination']!=state['location']:
        command=copy.deepcopy(intent['operation'])
    resolved = operation(story.root, files, command, text, explicit=True) if command else None
    op_detail = _describe_operation_context(resolved, state, bundle_state, mem_text)
    charged = sp.enabled(story.root)
    preview_cost = reservation['quote'] if charged and reservation else quote(story.root, files, resolved)
    effective = copy.deepcopy(state)
    if resolved and resolved['code'] == 'move_player':
        effective['location'] = resolved['destination']
        effective['cast'] = scene_cast(state['presence'], mem_text, resolved['destination'])
        effective['intimate'] = {
            **(effective.get('intimate') or save_store.default_intimate()),
            'scene_active': False, 'session_beats': 0, 'privacy': 'open_public',
            'sub_location': '', 'present_actors': [], 'noise_risk': 0,
        }
    eff_intl = effective.get('intimate') or {}
    eff_present = [a for a in (eff_intl.get('present_actors') or []) if a in effective['cast']]
    history_audience = eff_present if eff_present else effective['cast']
    remote_vitals_targets = list(op_detail.get('remote_cast') or []) if (op_detail and op_detail.get('kind') == 'inspect_deployed') else []
    effective['remote_vitals_targets'] = remote_vitals_targets
    limits=sp.memory_policy(story.root)
    all_rows, older_disk_paths = recent_rows_tail(story.store, files, limit=24)
    visible_rows = []
    visible_archive_paths = list(older_disk_paths)
    for pair in all_rows:
        path, turn = pair
        input_visible = all(n in turn.get('input_known_by', turn.get('known_by', [])) for n in history_audience)
        reply_visible = all(n in turn.get('messages_known_by', turn.get('known_by', [])) for n in history_audience)
        if not (input_visible or reply_visible):
            continue
        if path is not None:
            visible_archive_paths.append(path)
        visible_rows.append((pair, input_visible, reply_visible))
    candidates = []
    for (path, turn), input_visible, reply_visible in visible_rows[-limits['history_turns']:]:
        safe = {k: turn[k] for k in ('id', 'input', 'input_kind', 'messages', 'handoff', 'operation', 'location', 'known_by')}
        safe.update(input_known_by=turn.get('input_known_by', turn.get('known_by', [])),
                    messages_known_by=turn.get('messages_known_by', turn.get('known_by', [])))
        if not input_visible:
            safe['input'] = ''
        if not reply_visible:
            safe.update(messages=[], handoff='', operation=None)
        seq_num = int(turn.get('sequence', 0)) if isinstance(turn.get('sequence'), int) else (int(path.stem) if path is not None else 0)
        candidates.append(((path, seq_num), safe))
    recent = bounded_history(candidates, limits)
    history = [safe for _, safe in recent]
    # Build epistemic-safe continuity bridge when the immediately preceding turn happened in the same
    # location with a subset of current room actors (e.g. a newcomer just walked in, filtering last turn out of history).
    recent_room_continuity = None
    if all_rows:
        last_turn = all_rows[-1][1]
        last_id = last_turn.get('id')
        last_loc = last_turn.get('after_location') or last_turn.get('location') or ''
        last_kb = [w for w in (last_turn.get('messages_known_by') or last_turn.get('known_by') or []) if w != '徐志北']
        if last_id and not any(h.get('id') == last_id for h in history) and last_loc == effective['location']:
            shared_here = [a for a in history_audience if a in last_kb]
            unseen_here = [a for a in history_audience if a not in last_kb]
            if shared_here and unseen_here:
                tail_bits = []
                for m in (last_turn.get('messages') or [])[-2:]:
                    if isinstance(m, dict) and m.get('text'):
                        t_clean = re.sub(r'\s+', ' ', str(m['text'])).strip()[:90]
                        if m.get('kind') == 'dialogue' and m.get('speaker'):
                            tail_bits.append(f"{m['speaker']}：「{t_clean}」")
                        elif m.get('kind') == 'action' and m.get('speaker'):
                            tail_bits.append(f"{m['speaker']}：{t_clean}")
                        else:
                            tail_bits.append(t_clean)
                if tail_bits:
                    recent_room_continuity = {
                        'only_known_by': ['徐志北', *shared_here],
                        'unseen_by': unseen_here,
                        'tail': ' | '.join(tail_bits)[:220],
                        'rule': f"上一幕紧接此前发生于同地，仅 {'、'.join(shared_here)} 与徐志北亲历；{'、'.join(unseen_here)} 刚入场毫不知情，严禁当众说破或让其凭空知晓。",
                    }
    included = {meta[0] for meta, _ in recent if meta[0] is not None}
    omitted_archive = [str(p.relative_to(story.root)) for p in visible_archive_paths if p not in included]
    last_cand_path = candidates[-1][0][0] if candidates else None
    required_history = [str(last_cand_path.relative_to(story.root))] if (last_cand_path is not None and last_cand_path not in included) else []
    refs = helper.references(text, history)
    if op_detail and op_detail.get('kind') == 'inspect_deployed':
        for rc_name in (op_detail.get('remote_cast') or []):
            if not any(r['name'] == rc_name for r in refs):
                refs.append({'name': rc_name, 'matched_aliases': [], 'basis': 'remote_device_feed'})
    if not any(r['name'] == '徐志北' for r in refs):
        refs.append({'name': '徐志北', 'matched_aliases': [], 'basis': 'host_sovereignty'})
    if lazy_live_txt:
        sources, characters, relationships = {}, [], []
    else:
        sources, characters, relationships = helper.sources(effective['cast'], refs)
    from relationship_query import RelationshipRegistry
    RelationshipRegistry(story.root).verify_view()
    shop_cat_rel = sp.shop_catalog_path(story.root)
    intel_cat_rel = sp.intel_catalog_path(story.root)
    director_cat_rel = str(sp.director_config(story.root).get('catalog') or sp.DIRECTOR_CATALOG_DEFAULT).strip()
    names = [RULE, CONFIG, 'txt文件/提示词.md', 'txt文件/一键注入指南.txt', 'txt文件/全局执行法典.md',
             'txt文件/故事检索索引.md', 'txt文件/知识库/世界观类.json', 'txt文件/知识库/叙事判断.json',
             'txt文件/知识库/系统标签类.json', 'txt文件/知识库/角色类.json', 'txt文件/关系称谓库.json',
             'interaction_runtime.py', 'round_runtime.py', 'injection_core.py',
             'relationship_query.py', *(['story_compiler.py'] if story.store._path('story_compiler.py').is_file() else []),
             *([shop_cat_rel] if story.store._path(shop_cat_rel).is_file() else []),
             *([intel_cat_rel] if story.store._path(intel_cat_rel).is_file() else []),
             *([director_cat_rel] if story.store._path(director_cat_rel).is_file() else []),
             *(['story_progression.py','txt文件/事件注册表.json'] if sp.enabled(story.root) else []), *rr.FILES]
    for n in names:
        p_obj = story.store._path(n)
        if p_obj.is_file():
            sources[n] = _cached_digest(p_obj)
    for (p, _seq), _ in recent:
        if p is not None and p.is_file():
            sources[str(p.relative_to(story.root))] = _cached_digest(p)
    for path in required_history:
        sources[path] = _cached_digest(story.store._path(path))
    memory = prepared['snapshot'][rr.FILES[0]]
    runtime=sp.state(story.root,files) if charged else {'memory_round':1,'last_closed':0,'phase':'ready'}
    projection=memory_context(story.root,memory,text,runtime,cast=effective['cast'],location=effective['location'])
    is_action_turn = (not charged or preview_cost.get('kind') == 'action')
    pending_echoes = sp.parse_shop_echo_block(memory)['echoes'] if is_action_turn else []
    delivered_echo_ids = [e['id'] for e in pending_echoes]
    prior_roll = None
    try:
        ctx_blob = story._blob(key, '.context.json')
        if ctx_blob.is_file():
            old_ctx = json.loads(ctx_blob.read_bytes())
            if isinstance(old_ctx, dict) and isinstance(old_ctx.get('director_roll'), dict):
                prior_roll = old_ctx['director_roll']
    except Exception:
        prior_roll = None
    if prior_roll is not None:
        director_roll = prior_roll
    elif is_action_turn:
        director_roll = sp.roll_director_beat(
            story.root, effective, memory, runtime, state.get('weekday', ''),
            pacing_mode=load_story_prefs(story.root)['director_pacing'],
        )
    else:
        dstate = sp.parse_director_block(memory)
        st_cnt = (dstate['scene_turns'] + 1) if dstate['scene_location'] == effective['location'] else 1
        director_roll = {'triggered': False, 'probability': 0.0, 'scene_turns_in_place': st_cnt}
    cache=sr.CACHE+'/'+hashlib.sha256(key.encode()).hexdigest()[:32]
    archive_index=cache+'/history-index.json'
    rr._atomic(story.store._path(archive_index),rr._json({'paths':omitted_archive}))
    sources[archive_index]=rr._digest(story.store._path(archive_index).read_bytes())
    memory_index=cache+'/memory-index.json'
    rr._atomic(story.store._path(memory_index),rr._json({'entries':projection['all_entries']}))
    sources[memory_index]=rr._digest(story.store._path(memory_index).read_bytes())
    scenario_meta = {'location': effective['location'], 'cast': effective['cast'],
                     'present_actors': history_audience, 'presence': state['presence'],
                     'remote_vitals_targets': remote_vitals_targets}
    op_meta = {'requested': resolved, 'input_evidence': intent, 'source_location': state['location'],
               **({'detail': op_detail} if op_detail else {})}
    v2_packet_meta = {
        'scenario': scenario_meta,
        'operation': op_meta,
        'accepted_history': history,
        'input': text,
        'selection': selected,
        'cost_preview': preview_cost,
        'previous_validation_error': previous_error,
        'accounting': {'runtime': runtime} if charged else None,
    }
    relative = cache + '/live.txt'
    if lazy_live_txt:
        packet_env = {'path': relative, 'lazy': True, 'through_line': 0, 'read_ranges': []}
        packet_sha = ''
    else:
        relevant = []
        for filename in ('世界观类', '叙事判断', '系统标签类'):
            for entry in sc._load_kb_entries(story.root, filename):
                content = entry['content']
                if charged or filename != '系统标签类' or any(k in content for k in ('※索引key※ sys.runtime_data', '※索引key※ sys.task', '※索引key※ sys.breakout')):
                    relevant.append({'source': 'txt文件/知识库/' + filename + '.json', 'body': content})
        # Legacy memories lack machine-readable knowledge scopes; preserve as player-only continuity.
        data = {'entry_mode': MODE, 'request_id': key, 'source_manifest': sources,
                'rules': (story.root / RULE).read_text(encoding='utf-8'),
                'sovereignty': (story.root / 'txt文件/全局执行法典.md').read_text(encoding='utf-8'),
                'characters': characters, 'relationships': relationships, 'knowledge_rules': relevant,
                'scenario': scenario_meta,
                'operation_policy': {'locations': state['policy']['locations'],'location_aliases':location_aliases(story.root),
                    'templates': [
                        {'code': 'move_player', 'destination': '登记地点'},
                        {'code': 'transfer_item', 'item_id': 'ITEM-编号', 'recipient': '在场人物'},
                        {'code': 'use_item', 'item_id': 'ITEM-编号', 'target': '在场人物或室内'},
                        {'code': 'deploy_item', 'item_id': 'ITEM-编号', 'spot': '安装点位', 'hidden': True},
                        {'code': 'retrieve_item', 'item_id': 'ITEM-编号'},
                        {'code': 'inspect_deployed', 'item_id': 'ITEM-编号'},
                        {'code': 'keepsake_action', 'keepsake_id': 'KS-编号', 'action_type': 'sniff_play|confront|use_intimate|return_secret'},
                    ]},
                'player_private_state': {'memory': projection['text'], 'items': state['items'],
                    'deployed_items': state.get('deployed_items', []), 'tasks': state['tasks'],
                    'memory_context':{'selected':projection['selected'],'omitted_count':projection['omitted_count'],
                        'index':projection['index'],'full_index':memory_index,'required_reads':projection['required'],'limits':limits,
                        'rule':'仅含完整源条目的预算内视图，不代表其余事实消失；旧记忆为玩家私有，不能传播NPC未知秘密。需旧事实时据精确行号补读。'}},
                **({'milestone_echo': {'events': [{'kind': e['kind'], 'summary': e['summary']} for e in pending_echoes],
                    'rule': '一次性特定时刻微回响：仅允许在自然间隙或收束处用1句氛围/感官/内心轻顿带过，禁直呼任务/委托/商城/积分/系统词，禁扭转玩家意图，禁泄露给NPC。'}} if pending_echoes else {}),
                **({'surprise_directive': sp.format_surprise_directive(director_roll)} if sp.format_surprise_directive(director_roll) else {}),
                'accepted_history': history, 'input': text, 'selection': selected,
                 'accounting': ({'reservation': {k:v for k,v in reservation.items() if k not in ('before_memory','before_save_state')},
                      'runtime':runtime,'instruction':'面板体力已预扣，原体力见quote.before；不据暂扣判断力竭。按resolution交实际事件与时间；程序决定最终不足5及强制休息。',
                      'event_registry':rr._engine(story.root,story.root)._load_event_registry(),
                      'memory_transfer_sources':{}} if charged else None),
                  'story_pacing': '依据当前人物、既有事务、矛盾及玩家意图推进连贯剧情，在真实抉择处交还；偶尔可短答，不固定一两句，不等整场结束，不按字数填充。',
                'operation': {**op_meta,
                    'rule': '玩家明确操作已预检；仅确认执行后的现场反应，不改参数。自由输入最多提议一个有原文依据的登记操作。'},
                'resource_policy': state['policy']['resource'], 'cost_preview': preview_cost,
                'history_archive': {'paths': omitted_archive[-limits['index_entries']:], 'omitted_count':len(omitted_archive),
                    'index':archive_index,'required_reads':required_history,
                    'rule': '需要旧记录时补读指定原文；更早路径从index取得。按input_known_by/messages_known_by分别核查，禁止扩散未知秘密。'},
                'previous_validation_error': previous_error}
        if charged:
            data['accounting']['memory_transfer_sources'] = {
                'current_round':runtime['last_closed'] if runtime['phase']=='resting' and runtime['last_closed'] else runtime['memory_round'],
                'current_entry':projection['current'],'transfers':projection['transfers'],
                'required_reads':projection['required'],
                'rule':'仅记录有长期因果价值的新fact，重要承诺/关系转折用anchor_ops原子维护；仅在待归档情景批到达时提交chronicle_digest。'}
        raw = encode_live_packet(data)
        rr._atomic(story.store._path(relative), raw)
        packet_env = {'path': relative, 'through_line': len(raw.decode().splitlines()), 'read_ranges': packet_read_ranges(raw)}
        packet_sha = rr._digest(raw)
    contract = {'messages': [{'kind': 'dialogue|action|narration', 'speaker': '在场人物或旁白空串', 'text': '本段剧情'}],
                 'decision': {'prompt': '本段真实抉择', 'options': [{'id': k, 'text': '当前可行的下一步行为'} for k in OPTION_NAMES]},
                'operation': 'null或一个合法move_player/transfer_item/use_item/deploy_item/retrieve_item/inspect_deployed/keepsake_action对象；不填成本或任意状态patch',
                'handoff': '无待处理时空字符串',
                'checks': {'intent': '具体依据', 'knowledge': '本场信息边界', 'action': '操作与正文一致或无动作', 'pace': '本段推进及此处交还控制权的依据'}}
    intimate_mode_now = bool(eff_intl.get('scene_active'))
    if charged:
        contract['resolution'] = sp.contract(story.root,preview_cost['kind'], (selected or {}).get('option_id'), intimate_mode=intimate_mode_now)
    envelope = {'entry_mode': MODE, 'packet': packet_env,
                'reading_tools':list(LIVE_READ_TOOLS),'previous_validation_error':previous_error,
                'continuity':{'source':'正式存档与accepted_history','rule':'本次资料包含当前正式记忆、已接受原文及原行动；旧会话未提交草稿不属于事实。重试承接同一冻结点，不跳到下一行动。'},
                'required_memory_reads':projection['required'],'required_history_reads':required_history,
                'operation_context':{**op_meta, 'location_aliases':location_aliases(story.root)},
                **({'resolution_policy':sp.resolution_policy(preview_cost['kind'], (selected or {}).get('option_id'), intimate_mode=intimate_mode_now)} if charged else {}),
                'output_contract': contract, 'instruction': '先执行读取阶段：逐一照用packet.path和packet.read_ranges中的start_line/end_line调用read_file_part，读完每一段；header显示请求范围不代表正文已齐，核对实际返回的末行。需要时补齐截断正文，文件末尾空白不作为未读正文。再读required_memory_reads与required_history_reads，最后生成完整JSON；只允许reading_tools和本任务文件路径，grep_code只定位不计正文覆盖，禁止list_files/find_files或读取许可外文件；其余旧事实按本任务精确行号或归档索引补读。返回单个裸JSON，生成连贯剧情及decision中的A/B/C；无需演完一场戏，不写旧完整回合、L1或SYSTEM_LOG。'}
    if charged:
        envelope['instruction'] += ' 必须同时返回resolution并逐项遵循resolution_policy：普通付费action即使只澄清或未发生移动也必须交完整conditions对象，字段名称不改；SYSTEM才允许无条件。已预检的operation_context.requested直接对应玩家原文与登记别名，不再猜地点。只分类和提供依据，不计算成本/最终面板；免费休息为SYSTEM且实际休息推进，睡眠有正文起止，不以短休冒充整夜。判档/事件/事实/时间只按当前资料；不能把人物系统数值或玩家私有记忆写成NPC知情。'
    last_seq = int(all_rows[-1][1].get('sequence', 0)) if all_rows else 0
    recent_seqs = [meta[1] for meta, _ in recent]
    bundle_state_scope, _, _ = save_store.load_bundle(story.root, files)
    all_unlocked_scope = [str(x).strip() for x in ((bundle_state_scope.get('mechanics') or {}).get('secrets_unlocked') or ()) if str(x).strip()]
    sec_reg_scope = sc.load_secret_guard_registry(story.root)
    cast_set_scope = set(effective['cast'])
    active_unlocked_scope = sorted({
        str(sec.get('unlock_key') or '').strip()
        for sec in (sec_reg_scope.get('secrets') or {}).values()
        if isinstance(sec, dict)
        and str(sec.get('unlock_key') or '').strip() in all_unlocked_scope
        and (sec.get('owner') in cast_set_scope or bool(set(sec.get('co_holders') or ()) & cast_set_scope))
    })
    return {'protocol': 3, 'interaction_protocol': 3 if charged else 2, 'entry_mode': MODE, 'audit': sources,
            'packet': {**envelope['packet'], 'sha256': packet_sha},
            'v2_packet_meta': v2_packet_meta,
            'allowed_archive': [*omitted_archive,archive_index,memory_index],
            'allowed_memory_reads':projection['all_refs']+projection['allowed'], 'required_memory_reads':projection['required'],
            'required_history_reads':required_history,
            'command': resolved, 'cast': effective['cast'], 'location': effective['location'],
            'references': refs, 'last_committed_sequence': last_seq, 'recent_sequences': recent_seqs,
            'archive_index': archive_index, 'memory_index': memory_index, 'omitted_archive': omitted_archive,
            'selection': selected, 'previous_validation_error':previous_error,
            'interaction_scope': rr._digest(rr._json([effective['location'], effective['cast'], active_unlocked_scope])),
            'cost_preview': preview_cost,
            'delivered_echo_ids': delivered_echo_ids,
            'director_roll': director_roll,
            **({'recent_room_continuity': recent_room_continuity} if recent_room_continuity else {}),
            'reading_policy': {'version': sr.VERSION},
            'turns': [{'kind': 'user', 'content': json.dumps(envelope, ensure_ascii=False)}]}


def required_source_lines(raw, through=None):
    lines=raw.decode('utf-8').splitlines()
    end=min(through if through is not None else len(lines),len(lines))
    while end and not lines[end-1].strip():end-=1
    return set(range(1,end+1))


def missing_read_target(key, path, raw, missing):
    pages=packet_read_ranges(raw);reads=[]
    for page in pages:
        begin=None
        for number in range(page['start_line'],page['end_line']+2):
            if number<=page['end_line'] and number in missing:
                if begin is None:begin=number
            elif begin is not None:
                reads.append({'path':path,'start_line':begin,'end_line':number-1});begin=None
    return {'key':key,'reads':reads}


def material_delivery(story, key, job, chat_id, participant_id):
    """Read and freeze this task's source material for one direct session input."""
    context = json.loads(story._blob(key, '.context.json').read_bytes())
    if context.get('entry_mode') != MODE:
        raise rr.RoundError('资料直送只用于正式互动')
    story._source_check(context)
    wanted = context['packet']
    if wanted.get('lazy') and not story.store._path(wanted['path']).is_file():
        raise rr.ConflictError('本次任务为精简v2上下文，请升级v2桥接或重试任务')
    raw = story.store._path(wanted['path']).read_bytes()
    if rr._digest(raw) != wanted['sha256']:
        raise rr.ConflictError('本次资料包已经改变')
    sources = [{'path': wanted['path'], 'source_sha256_at_result': rr._digest(raw),
                'verified_lines': sorted(required_source_lines(raw, wanted['through_line']))}]
    supplements = []
    refs = list(context.get('required_memory_reads', []))
    refs.extend({'path': path, 'start_line': 1,
                 'end_line': len(story.store._path(path).read_bytes().decode().splitlines())}
                for path in context.get('required_history_reads', []))
    seen = set()
    for ref in refs:
        path, begin, end = ref['path'], ref['start_line'], ref['end_line']
        if (path, begin, end) in seen:
            continue
        seen.add((path, begin, end))
        source = story.store._path(path).read_bytes()
        if context['audit'].get(path) != rr._digest(source):
            raise rr.ConflictError('必要补读源未冻结或已经改变: ' + path)
        lines = source.decode().splitlines()
        if not 1 <= begin <= end <= len(lines):
            raise rr.RoundError('必要补读源行号无效')
        supplements.append({'path': path, 'start_line': begin, 'end_line': end,
                            'body': '\n'.join(lines[begin-1:end])})
        sources.append({'path': path, 'source_sha256_at_result': rr._digest(source),
                        'verified_lines': list(range(begin, end+1))})
    envelope = json.loads(context['turns'][0]['content'])
    envelope.pop('instruction', None)
    envelope['output_contract']['operation'] = ''
    envelope['output_contract']['handoff'] = ''
    resolution = envelope['output_contract'].get('resolution')
    if resolution:
        resolution['task'] = ''
        resolution['sleep']['start'] = ''
        if isinstance(resolution.get('conditions'), dict):
            resolution['conditions']['npc'] = ''
    v1_protag_style = load_story_prefs(story.root)['protagonist_style']
    v1_player_dlg_rule = (
        'dialogue.speaker只能取material.scenario.cast中的实际在场人物（忠实演绎模式下另允许≤3句贴合玩家原意图的简短徐志北dialogue，单句≤40字、禁标签、不代做新决定或升级）'
        if v1_protag_style == 'faithful'
        else 'dialogue.speaker只能取material.scenario.cast中的实际在场人物，严禁写徐志北或场外人物，不代写玩家台词'
    )
    payload = {'entry_mode': MODE, 'material_delivery': 'program_inline_v1',
               'request_id': key, 'envelope': envelope, 'material': json.loads(raw),
               'required_sources': supplements,
               'instruction': f'本次material及required_sources是程序从当前冻结源完整读取后直接交付的正文，须完整理解，不为证明读取而再次逐段读packet；不虚构模型工具读取。旧会话、失败草稿均不替代本次正式存档。确需更早原文时，只按本任务索引和许可路径补查，保留实际听众与知情边界。messages按序排列：{v1_player_dlg_rule}；action.speaker为在场人物或徐志北；narration.speaker为空字符串。依据人物设定、世界规则、当前状态和玩家意图推演连贯剧情，保留完整回应与必要后果，在需要新决定处停下。不代替玩家决定，不将私有资料当共同知识。最终仅交envelope.output_contract要求的单个裸JSON，decision含A/B/C；按envelope.resolution_policy.category_policy执行：fixed_option的resolution.category只能为required_category，禁止重新判档；只有custom按实际行为分类，system为SYSTEM。conditions.intensity按现有契约与category一致，不因档位升级行为或虚构事件。按resolution_policy交完整conditions，只给事件原文依据、实际游戏时间和必要记忆，程序结算费用和数值。operation无操作、task无任务、sleep.start无起点、conditions.npc无对象时明确写空字符串，不能省略值。SYSTEM才允许无conditions；host_events对象固定为系统宿主。不执行命令、不写文件、不写旧整回合或SYSTEM_LOG。'}
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(content.encode('utf-8')) > 2 * 1024 * 1024:
        raise rr.RoundError('资料直送超过2MiB，停止生成，不截断正文')
    record = {'version': 1, 'id': secrets.token_hex(24), 'request_id': key,
              'lease_sha256': rr._digest(job['lease'].encode()),
              'context_sha256': rr._digest(story._blob(key, '.context.json').read_bytes()),
              'input_sha256': rr._digest(content.encode('utf-8')),
              'chat_id': chat_id, 'participant_id': participant_id, 'sources': sources}
    existing = story._blob(key, '.delivery.json')
    if existing.is_file():
        old = json.loads(existing.read_bytes())
        if old.get('lease_sha256') == record['lease_sha256']:
            if any(old.get(field) != record[field] for field in
                   ('version', 'request_id', 'context_sha256', 'input_sha256', 'chat_id', 'participant_id', 'sources')):
                raise rr.ConflictError('同一租约的资料或会话已经改变')
            record = old
    rr._atomic(existing, rr._json(record))
    return {'input_text': content, 'delivery': {k: record[k] for k in ('id', 'input_sha256')}}


def material_delivery_v2(story, key, job, chat_id, participant_id, options=None):
    """Freeze Zone 0/1 static prefixes and issue compact per-turn delta + optional settlement spec."""
    opts = options if isinstance(options, dict) else {}
    protocol_mode = opts.get('protocol_mode', 'dual_stream_v2')
    if protocol_mode not in ('dual_stream_v2', 'single_prefix_v2'):
        raise rr.RoundError('不支持的资料交付模式: ' + str(protocol_mode))
    context = json.loads(story._blob(key, '.context.json').read_bytes())
    if context.get('entry_mode') != MODE:
        raise rr.RoundError('资料直送只用于正式互动')
    story._source_check(context)
    wanted = context['packet']
    if wanted.get('lazy') and isinstance(context.get('v2_packet_meta'), dict):
        packet_data = context['v2_packet_meta']
        sources = []
        for src_rel in (rr.FILES[0], CONFIG):
            src_path = story.store._path(src_rel)
            if src_path.is_file():
                sources.append({'path': src_rel, 'source_sha256_at_result': rr._digest(src_path.read_bytes()),
                                'verified_lines': []})
    else:
        raw = story.store._path(wanted['path']).read_bytes()
        if rr._digest(raw) != wanted['sha256']:
            raise rr.ConflictError('本次资料包已经改变')
        packet_data = context['v2_packet_meta'] if isinstance(context.get('v2_packet_meta'), dict) else json.loads(raw)
        sources = [{'path': wanted['path'], 'source_sha256_at_result': rr._digest(raw),
                    'verified_lines': sorted(required_source_lines(raw, wanted['through_line']))}]
    supplements = []
    refs = list(context.get('required_memory_reads', []))
    refs.extend({'path': path, 'start_line': 1,
                 'end_line': len(story.store._path(path).read_bytes().decode().splitlines())}
                for path in context.get('required_history_reads', []))
    seen = set()
    for ref in refs:
        path, begin, end = ref['path'], ref['start_line'], ref['end_line']
        if (path, begin, end) in seen:
            continue
        seen.add((path, begin, end))
        source = story.store._path(path).read_bytes()
        if context['audit'].get(path) != rr._digest(source):
            raise rr.ConflictError('必要补读源未冻结或已经改变: ' + path)
        lines = source.decode().splitlines()
        if not 1 <= begin <= end <= len(lines):
            raise rr.RoundError('必要补读源行号无效')
        supplements.append({'path': path, 'start_line': begin, 'end_line': end,
                            'body': '\n'.join(lines[begin-1:end])})
        sources.append({'path': path, 'source_sha256_at_result': rr._digest(source),
                        'verified_lines': list(range(begin, end+1))})

    envelope = json.loads(context['turns'][0]['content'])
    envelope.pop('instruction', None)
    envelope['output_contract']['operation'] = ''
    envelope['output_contract']['handoff'] = ''
    resolution = envelope['output_contract'].get('resolution')
    if resolution:
        resolution['task'] = ''
        resolution['sleep']['start'] = ''
        if isinstance(resolution.get('conditions'), dict):
            resolution['conditions']['npc'] = ''

    files = story.store._files()
    prompt_files = dict(files)
    res_obj = (job or {}).get('reservation') if isinstance(job, dict) else None
    if isinstance(res_obj, dict) and res_obj.get('status') == 'held' and res_obj.get('before_memory'):
        import base64
        try:
            prompt_files[rr.FILES[0]] = base64.b64decode(res_obj['before_memory'], validate=True)
            if res_obj.get('before_save_state') is not None:
                prompt_files[save_store.SAVE_STATE_PATH] = base64.b64decode(res_obj['before_save_state'], validate=True)
        except Exception:
            prompt_files = dict(files)
    memory_text = (prompt_files[rr.FILES[0]] or b'').decode('utf-8')
    live_state = view(story.store, prompt_files)
    bundle_state, layers_bundle, _ = save_store.load_bundle(story.root, prompt_files)
    scenario = packet_data.get('scenario', {})
    req_op_v2 = (packet_data.get('operation') or {}).get('requested')
    eff_intl_v2 = copy.deepcopy(live_state.get('intimate') or save_store.default_intimate())
    if isinstance(req_op_v2, dict) and req_op_v2.get('code') == 'move_player':
        eff_intl_v2.update({
            'scene_active': False, 'session_beats': 0, 'privacy': 'open_public',
            'sub_location': '', 'present_actors': [], 'noise_risk': 0,
        })
    effective_state = {
        **live_state,
        'location': scenario.get('location', live_state['location']),
        'cast': scenario.get('cast', live_state['cast']),
        'intimate': eff_intl_v2,
        'remote_vitals_targets': list(scenario.get('remote_vitals_targets') or []),
        'mechanics': copy.deepcopy(bundle_state.get('mechanics') or {}),
        'npc_mind': copy.deepcopy(bundle_state.get('npc_mind') or save_store.default_npc_mind()),
        'prologue_active': bool((layers_bundle or {}).get('prologue_active', False)),
    }
    cast = effective_state['cast']
    references = context.get('references', [])
    text_input = packet_data.get('input', '')
    story_prefs = load_story_prefs(story.root)
    protagonist_style = story_prefs['protagonist_style']

    synced_z0 = str(opts.get('synced_zone0_sha256') or '')
    synced_z1 = str(opts.get('synced_zone1_sha256') or '')
    is_fresh = bool(opts.get('is_fresh_session', True))
    last_seen_seq = opts.get('last_committed_sequence', 0)
    if type(last_seen_seq) is not int or last_seen_seq < 0:
        last_seen_seq = 0
    raw_synced_flags = opts.get('synced_zone1_flags')
    pflags_now = sc.compute_zone1_persona_flags(effective_state, memory_text)
    if (not is_fresh) and isinstance(raw_synced_flags, dict) and 'vig' in raw_synced_flags and 'intl' in raw_synced_flags:
        synced_stage = raw_synced_flags.get('char_stage')
        synced_sec = raw_synced_flags.get('unlocked_secrets')
        zone1_flags = {
            'vig': bool(raw_synced_flags.get('vig')),
            'intl': bool(raw_synced_flags.get('intl')),
            'char_stage': dict(synced_stage) if isinstance(synced_stage, dict) else pflags_now['char_stage'],
            'unlocked_secrets': [str(x).strip() for x in synced_sec if str(x).strip()] if isinstance(synced_sec, list) else list(pflags_now['unlocked_secrets']),
        }
    else:
        zone1_flags = {
            'vig': sc._needs_vigilance_rules(effective_state, memory_text),
            'intl': sc._needs_intimate_zone1(effective_state, memory_text),
            'char_stage': pflags_now['char_stage'],
            'unlocked_secrets': list(pflags_now['unlocked_secrets']),
        }
    injected_refs = [x for x in (opts.get('injected_refs') or ()) if isinstance(x, str) and x] if not is_fresh else []
    injected_guides = [x for x in (opts.get('injected_guides') or ()) if isinstance(x, str) and x] if not is_fresh else []
    injected_memory_fps = [x for x in (opts.get('injected_memory_fps') or ()) if isinstance(x, str) and x] if not is_fresh else []
    prev_state_hashes = opts.get('prev_state_hashes') if (not is_fresh and isinstance(opts.get('prev_state_hashes'), dict)) else None
    anchor_history_mode = story_prefs.get('anchor_history_mode', 'balanced')

    zone0_global = sc.build_zone0_global(
        story.root, mode=protocol_mode, protagonist_style=protagonist_style,
        custom_rules=story_prefs,
    )
    # Zone 1 strictly excludes transient offstage references and freezes vig/intl/char_stage flags per session
    # so same-scene KV prefix cache stays 100% byte-identical across turns; offstage profiles/address locks
    # and mid-session craft guides are delivered losslessly once per session in Zone 2.
    zone1_scene = sc.build_zone1_scene(
        story.root, effective_state, cast, (),
        memory_text=memory_text, extra_text='', mode=protocol_mode,
        protagonist_style=protagonist_style, frozen_flags=zone1_flags,
    )
    zone0_sha = rr._digest(zone0_global.encode('utf-8'))
    zone1_sha = rr._digest(zone1_scene.encode('utf-8'))

    include_full_anchor = (
        is_fresh or last_seen_seq <= 0
        or (bool(synced_z0) and synced_z0 != zone0_sha)
        or (bool(synced_z1) and synced_z1 != zone1_sha)
    )

    history = packet_data.get('accepted_history', [])
    recent_seqs = context.get('recent_sequences', [])
    new_history_only = [
        item for item, seq in zip(history, recent_seqs) if seq > last_seen_seq
    ] if (not include_full_anchor and len(history) == len(recent_seqs)) else []

    charged = sp.enabled(story.root)
    runtime = (packet_data.get('accounting') or {}).get('runtime') or (
        sp.state(story.root, prompt_files) if charged else {'memory_round': 1, 'last_closed': 0, 'phase': 'ready'}
    )
    projection = memory_context(
        story.root, memory_text, text_input, runtime,
        cast=cast, location=effective_state['location'], is_single=(protocol_mode == 'single_prefix_v2'),
    )
    room_actors_v2 = [a for a in (eff_intl_v2.get('present_actors') or []) if a in cast] or list(cast)
    mem_view = save_store.retrieve_memory_view(
        layers_bundle,
        query=text_input,
        cast=cast,
        present_actors=room_actors_v2,
        location=effective_state['location'],
        max_chars=3600 if include_full_anchor else 1400,
        incremental=not include_full_anchor,
        exclude_fingerprints=injected_memory_fps if not include_full_anchor else None,
    )
    raw_chook = opts.get('continuity_hook')
    continuity_hook = (
        sc.strip_dialogue_subtext(re.sub(r'[\r\n]+', ' ', str(raw_chook)).strip())[:280]
        if isinstance(raw_chook, str) and raw_chook.strip() else ''
    )
    is_action_turn = (not charged or (packet_data.get('cost_preview') or {}).get('kind') == 'action')
    pending_echoes = sp.parse_shop_echo_block(memory_text)['echoes'] if is_action_turn else []
    breakout_hint = sc.compile_breakout_hint(memory_text) if is_action_turn else None
    intel_catalog = sp.load_intel_catalog(story.root, optional=True)
    stage1_supplements = () if protocol_mode == 'dual_stream_v2' else supplements
    persona_correction = ''
    if is_action_turn:
        retry_guidance = str((job or {}).get('drift_retry_guidance') or '').strip() if isinstance(job, dict) else ''
        if retry_guidance:
            persona_correction = retry_guidance
        else:
            cur_epoch = (job or {}).get('save_epoch') if isinstance(job, dict) else None
            if not cur_epoch and hasattr(story, '_save_epoch'):
                cur_epoch = story._save_epoch()
            pending_corr = load_persona_correction(story.root, save_epoch=cur_epoch)
            if isinstance(pending_corr, dict) and pending_corr.get('hint'):
                persona_correction = str(pending_corr['hint'])
    session_delta = {}
    user_delta = sc.build_user_delta(
        story.root, effective_state, projection, history, new_history_only,
        text_input, packet_data.get('selection'), context.get('command'),
        (packet_data.get('operation') or {}).get('input_evidence'),
        packet_data.get('cost_preview'), runtime, memory_text,
        previous_error=packet_data.get('previous_validation_error', ''),
        include_full_anchor=include_full_anchor, mode=protocol_mode,
        omitted_archive=context.get('omitted_archive', []),
        archive_index=context.get('archive_index', ''),
        memory_index=context.get('memory_index', ''),
        required_sources=stage1_supplements,
        output_contract=envelope['output_contract'],
        resolution_policy=envelope.get('resolution_policy'),
        operation_context=envelope.get('operation_context'),
        pending_echoes=pending_echoes,
        weekday=live_state.get('weekday', ''),
        breakout_hint=breakout_hint,
        intel_catalog=intel_catalog,
        director_roll=context.get('director_roll'),
        protagonist_style=protagonist_style,
        memory_view=mem_view,
        continuity_hook=continuity_hook,
        recent_room_continuity=context.get('recent_room_continuity'),
        references=references,
        injected_refs=injected_refs,
        zone1_flags=zone1_flags,
        injected_guides=injected_guides,
        session_delta_out=session_delta,
        prev_state_hashes=prev_state_hashes if not include_full_anchor else None,
        anchor_history_mode=anchor_history_mode,
        persona_correction=persona_correction,
    )
    total_bytes = len(zone0_global.encode('utf-8')) + len(zone1_scene.encode('utf-8')) + len(user_delta.encode('utf-8'))
    if total_bytes > 2 * 1024 * 1024:
        raise rr.RoundError('资料直送超过2MiB，停止生成，不截断正文')

    settlement_spec = None
    if protocol_mode == 'dual_stream_v2':
        settlement_spec = sc.build_settlement_spec(
            story.root, effective_state, projection, text_input, packet_data.get('selection'),
            context.get('command'), (packet_data.get('operation') or {}).get('input_evidence'),
            packet_data.get('cost_preview'), runtime, memory_text,
            envelope.get('resolution_policy'), envelope['output_contract'],
            envelope.get('operation_context'), required_sources=(),
            intel_catalog=intel_catalog, director_roll=context.get('director_roll'),
            settlement_custom_rules=story_prefs,
            memory_view=mem_view,
            history=history,
        )

    record = {
        'version': 2, 'kind': 'program_prefix_v2', 'protocol_mode': protocol_mode,
        'id': secrets.token_hex(24), 'request_id': key,
        'lease_sha256': rr._digest(job['lease'].encode()),
        'context_sha256': rr._digest(story._blob(key, '.context.json').read_bytes()),
        'zone0_sha256': zone0_sha, 'zone1_sha256': zone1_sha,
        'input_sha256': rr._digest(user_delta.encode('utf-8')),
        'settlement_system_sha256': settlement_spec['system_sha256'] if settlement_spec else '',
        'chat_id': chat_id, 'participant_id': participant_id, 'sources': sources,
    }
    existing = story._blob(key, '.delivery.json')
    if existing.is_file():
        old = json.loads(existing.read_bytes())
        if old.get('lease_sha256') == record['lease_sha256']:
            if any(old.get(field) != record[field] for field in
                   ('version', 'protocol_mode', 'request_id', 'context_sha256',
                    'zone0_sha256', 'zone1_sha256', 'input_sha256', 'chat_id', 'participant_id', 'sources')):
                raise rr.ConflictError('同一租约的资料或会话已经改变')
            record = old
    rr._atomic(existing, rr._json(record))
    merged_injected_refs = sorted(set(injected_refs) | set(session_delta.get('newly_injected_refs') or ()))
    merged_injected_guides = sorted(set(injected_guides) | set(session_delta.get('newly_injected_guides') or ()))
    merged_memory_fps = sorted(set(injected_memory_fps) | set(mem_view.get('selected_fingerprints') or ()))[-256:]
    res_payload = {
        'delivery_version': 2,
        'protocol_mode': protocol_mode,
        'protagonist_style': protagonist_style,
        'zone0_global': zone0_global,
        'zone0_sha256': zone0_sha,
        'zone1_scene': zone1_scene,
        'zone1_sha256': zone1_sha,
        'input_text': user_delta,
        'include_full_anchor': include_full_anchor,
        'allowed_speakers': cast,
        'last_committed_sequence': context.get('last_committed_sequence', 0),
        'envelope': envelope,
        'settlement_spec': settlement_spec,
        'session_meta': {
            'zone1_flags': zone1_flags,
            'injected_refs': merged_injected_refs,
            'injected_guides': merged_injected_guides,
            'memory_fps': merged_memory_fps,
            'state_hashes': session_delta.get('state_hashes') or {},
        },
        'delivery': {
            'id': record['id'],
            'input_sha256': record['input_sha256'],
            'zone0_sha256': zone0_sha,
            'zone1_sha256': zone1_sha,
        },
    }
    if protocol_mode == 'dual_stream_v2' and isinstance(job, dict) and job.get('resume_stage2'):
        cp = load_stage1_checkpoint(story, key, job)
        if cp is not None:
            res_payload['stage1_checkpoint'] = {
                'foreground_text': cp['foreground_text'],
                'foreground_messages': cp['foreground_messages'],
                'generation_ms': cp['generation_ms'],
                'base_audit': cp['base_audit'],
            }
    return res_payload


def verify_delivery(story, key, context, proof):
    delivered = proof.get('delivery')
    if delivered is None:
        return None
    path = story._blob(key, '.delivery.json')
    if not isinstance(delivered, dict) or not path.is_file():
        raise rr.RoundError('缺少本次程序交付记录')
    record = json.loads(path.read_bytes())
    version = record.get('version')
    job = story._read()['jobs'].get(key, {})
    if (context.get('entry_mode') != MODE or version not in (1, 2) or record.get('request_id') != key
            or job.get('status') not in ('generating', 'validating')
            or (job.get('status') == 'generating' and job.get('lease_until', 0) < time.time())
            or not job.get('lease')
            or record.get('lease_sha256') != rr._digest(job['lease'].encode())
            or record.get('context_sha256') != rr._digest(story._blob(key, '.context.json').read_bytes())):
        raise rr.ConflictError('资料交付属于过期任务或租约')
    expected_keys = {'id', 'input_sha256', 'user_message_timestamp'}
    if version == 2:
        expected_keys |= {'zone0_sha256', 'zone1_sha256'}
    if (set(delivered) != expected_keys
            or delivered.get('id') != record.get('id')
            or delivered.get('input_sha256') != record.get('input_sha256')
            or (version == 2 and (delivered.get('zone0_sha256') != record.get('zone0_sha256')
                                  or delivered.get('zone1_sha256') != record.get('zone1_sha256')))
            or proof.get('chat_id') != record.get('chat_id')
            or proof.get('participant_id') != record.get('participant_id')):
        raise rr.RoundError('程序交付身份、内容或会话不符')
    passes = proof.get('read_passes')
    if passes is not None and (not isinstance(passes, list) or not passes or not isinstance(passes[0], dict)):
        raise rr.RoundError('资料交付阶段回执无效')
    first = passes[0].get('outcome', {}) if passes else proof['outcome']
    if not isinstance(first, dict) or not isinstance(first.get('assistant'), dict):
        raise rr.RoundError('资料交付阶段回执无效')
    stamp = delivered.get('user_message_timestamp')
    if (type(stamp) is not int or stamp <= 0 or first.get('userMessageTimestamp') != stamp
            or stamp > first.get('assistant', {}).get('messageTimestamp', 0)
            or stamp > proof['snapshot_message_timestamp']):
        raise rr.RoundError('程序交付缺少本次用户消息回执')
    for source in record['sources']:
        current = story.store._path(source['path']).read_bytes()
        if rr._digest(current) != source['source_sha256_at_result']:
            raise rr.ConflictError('已交付资料源已经改变')
    return record


def verify(story, key, proof, allow_missing=False):
    context = json.loads(story._blob(key, '.context.json').read_bytes())
    story._source_check(context)
    if not isinstance(proof, dict) or proof.get('api') != 'Tools.Chat.sendMessageStreaming':
        raise rr.RoundError('缺少Operit正式只读会话审计')
    outcome = proof.get('outcome', {})
    if not isinstance(outcome, dict) or not isinstance(outcome.get('assistant'), dict):
        raise rr.RoundError('会话完成回执结构无效')
    stamp = outcome['assistant'].get('messageTimestamp')
    if (outcome.get('type') != 'committed' or outcome.get('status') != 'completed'
            or type(stamp) is not int or proof.get('snapshot_message_timestamp') != stamp
            or not proof.get('chat_id') or not proof.get('participant_id')):
        raise rr.RoundError('正式会话尚未完成或快照不符')
    delivered = verify_delivery(story, key, context, proof)
    tools = proof.get('tools')
    if not isinstance(tools, list) or not (0 if delivered else 1) <= len(tools) <= 128:
        raise rr.RoundError('读取工具审计无效')
    passes=proof.get('read_passes')
    if passes is not None:
        if not isinstance(passes,list) or not 1<=len(passes)<=2:raise rr.RoundError('正式互动只允许一次提交前补读')
        cursor=0;stamps=set()
        for stage in passes:
            if not isinstance(stage,dict):raise rr.RoundError('补读阶段无效')
            receipt=stage.get('outcome',{});timestamp=stage.get('snapshot_message_timestamp');count=stage.get('tool_count')
            if (not isinstance(receipt,dict) or receipt.get('type')!='committed' or receipt.get('status')!='completed'
                    or not isinstance(receipt.get('assistant'),dict) or type(timestamp) is not int or timestamp in stamps
                    or receipt['assistant'].get('messageTimestamp')!=timestamp or stage.get('tool_start')!=cursor
                    or type(count) is not int or count < (0 if delivered else 1)):
                raise rr.RoundError('补读回执身份或工具范围不符')
            stamps.add(timestamp);cursor+=count
        if cursor!=len(tools) or passes[-1]['outcome']!=outcome or passes[-1]['snapshot_message_timestamp']!=stamp:
            raise rr.RoundError('补读累计工具或最终快照不符')
    wanted = context['packet']; covered = set(); verified = []
    is_lazy_v2 = bool(wanted.get('lazy') and delivered and delivered.get('version') == 2)
    memory_refs=context.get('allowed_memory_reads',[])
    required_memory=context.get('required_memory_reads',[])
    memory_covered=set();history_covered={}
    allowed = ({*context.get('allowed_archive', []), *[ref['path'] for ref in memory_refs]}
               if is_lazy_v2
               else {wanted['path'], *context.get('allowed_archive', []), *[ref['path'] for ref in memory_refs]})
    raw = None
    if not is_lazy_v2:
        raw = story.store._path(wanted['path']).read_bytes()
        if rr._digest(raw) != wanted['sha256']:
            raise rr.ConflictError('本次资料包已经改变')
    if delivered:
        for source in delivered['sources']:
            lines = source['verified_lines']
            path = source['path']
            if path == wanted['path']:
                covered.update(lines)
            if path == rr.FILES[0]:
                memory_covered.update(lines)
            if path in context.get('required_history_reads', []):
                history_covered.setdefault(path, set()).update(lines)
    for call in tools:
        if not isinstance(call, dict) or call.get('name') not in LIVE_READ_TOOLS:
            raise rr.RoundError('正式互动工具未许可：'+str(call.get('name') if isinstance(call,dict) else type(call).__name__)+'；允许 '+','.join(LIVE_READ_TOOLS))
        params = call.get('parameters', {})
        if not isinstance(params, dict) or not isinstance(params.get('path'), str):
            raise rr.RoundError('读取工具参数无效')
        path = params['path'].replace('\\', '/')
        for prefix in (proof.get('workspace'), str(story.root)):
            if isinstance(prefix, str) and prefix:
                norm_pref = prefix.replace('\\', '/').rstrip('/')
                if path.startswith(norm_pref + '/'):
                    path = path[len(norm_pref) + 1:]
                    break
        while path.startswith('./'):
            path = path[2:]
        if path not in allowed:
            raise rr.RoundError('读取了非本任务资料：'+path)
        if path==rr.FILES[0]:
            begin,end=params.get('start_line'),params.get('end_line')
            try:
                if isinstance(begin,bool) or isinstance(end,bool) or not re.fullmatch(r'[0-9]+',str(begin)) or not re.fullmatch(r'[0-9]+',str(end)):raise ValueError()
                begin,end=int(begin),int(end)
            except (ValueError,TypeError):raise rr.RoundError('记忆补读行号须为整数')
            if (call['name']!='read_file_part'
                    or not any(ref['start_line']<=begin<=end<=ref['end_line'] for ref in memory_refs)):
                raise rr.RoundError('记忆补读须使用本任务指定的精确行号，不得整库重读')
        entry = {'name': call['name'], 'path': path, 'status': call.get('status')}
        if call.get('status') == 'success' and call['name'] in ('read_file','read_file_full','read_file_part'):
            source = story.store._path(path).read_bytes()
            total_lines = len(source.decode().splitlines())
            raw_b, raw_e = params.get('start_line'), params.get('end_line')
            begin = 1 if raw_b in (None, '') else raw_b
            end = total_lines if raw_e in (None, '') else raw_e
            try:
                lines = sr.verified_lines(source, call.get('result_text', ''), int(begin), int(end))
            except (ValueError, TypeError) as exc:
                raise rr.RoundError('读取内容未核验: ' + str(exc)) from exc
            entry.update(verified_lines=lines, source_sha256_at_result=rr._digest(source))
            if path == wanted['path']:
                covered.update(lines)
            if path==rr.FILES[0]:memory_covered.update(lines)
            if path in context.get('required_history_reads',[]):history_covered.setdefault(path,set()).update(lines)
        verified.append(entry)
    targets=[];messages=[]
    if not is_lazy_v2:
        missing=required_source_lines(raw,wanted['through_line'])-covered
        if missing:
            targets.append(missing_read_target('packet',wanted['path'],raw,missing))
            messages.append('正式互动资料包未完整读取；缺少行 '+','.join(str(x) for x in sorted(missing)[:12])+'；截断须补完')
    for index,ref in enumerate(required_memory):
        missing=set(range(ref['start_line'],ref['end_line']+1))-memory_covered
        if missing:
            source=story.store._path(ref['path']).read_bytes()
            targets.append(missing_read_target('memory.'+str(index),ref['path'],source,missing))
            messages.append('必要记忆源未完整补读，不能用截断视图合并或转移')
    for index,path in enumerate(context.get('required_history_reads',[])):
        source=story.store._path(path).read_bytes();missing=required_source_lines(source)-history_covered.get(path,set())
        if missing:
            targets.append(missing_read_target('history.'+str(index),path,source,missing))
            messages.append('最近剧情原文超过自动预算，须完整补读后再续写')
    if targets and not allow_missing:raise rr.RoundError('；'.join(messages))
    delivery_audit = None
    if delivered:
        delivery_audit = {
            'kind': delivered.get('kind', 'program_inline_v1'),
            'id': delivered['id'],
            'input_sha256': delivered['input_sha256'],
            'user_message_timestamp': proof['delivery']['user_message_timestamp'],
            'sources': delivered['sources'],
        }
        if delivered.get('version') == 2:
            delivery_audit.update(
                protocol_mode=delivered.get('protocol_mode'),
                zone0_sha256=delivered.get('zone0_sha256'),
                zone1_sha256=delivered.get('zone1_sha256'),
            )
    settlement_audit = proof.get('settlement_audit')
    return {'required_reads_verified': not targets, 'origin': 'operit_session', 'chat_id': proof['chat_id'],
            'verified_tools': verified, 'source_manifest': context['audit'],
            **({'material_delivery': delivery_audit} if delivery_audit else {}),
            **({'settlement_audit': settlement_audit} if isinstance(settlement_audit, dict) else {}),
            'snapshot_message_timestamp': stamp, 'packet_sha256': wanted['sha256'],
            'missing_keys':[item['key'] for item in targets],'read_targets':targets}


def _normalize_fallback_decision(raw_fb, valid_locations, current_location, aliases=None):
    if not isinstance(raw_fb, dict):
        raise rr.RoundError('fallback_decision 必须是包含 prompt 与 options 的对象')
    raw_prompt = raw_fb.get('prompt')
    prompt_text = raw_prompt.strip() if isinstance(raw_prompt, str) and raw_prompt.strip() else sc._DEFAULT_DECISION_PROMPT
    cleaned = {'prompt': prompt_text, 'options': []}
    raw_opts = raw_fb.get('options')
    if not isinstance(raw_opts, list):
        raise rr.RoundError('fallback_decision.options 必须是包含 A/B/C 的数组')
    for item in raw_opts:
        if not isinstance(item, dict):
            raise rr.RoundError('fallback_decision.options 每项必须是对象')
        raw_id = item.get('id')
        norm_item = {
            'id': raw_id.strip().upper() if isinstance(raw_id, str) else raw_id,
            'text': item.get('text').strip() if isinstance(item.get('text'), str) else item.get('text'),
        }
        op = item.get('operation')
        if op not in (None, ''):
            if isinstance(op, dict) and op.get('code') == 'move_player' and isinstance(op.get('destination'), str):
                resolved_op = sc._resolve_option_move(op.get('destination'), valid_locations, aliases, current_location)
                if resolved_op:
                    norm_item['operation'] = resolved_op
            else:
                norm_item['operation'] = op
        cleaned['options'].append(norm_item)
    return decision(cleaned, valid_locations=valid_locations)


_AUDIT_PLACEHOLDERS = frozenset({'同上', '见前文', '已读取', '通过', '无'})


def _clean_single_line(value):
    if not isinstance(value, str):
        return ''
    return re.sub(r'[\r\n]+', ' ', value).strip()


def _autofill_settlement_audit_lines(settlement, context):
    """Fill missing/placeholder non-core narrative audit strings in dual-stage Stage 2 output.
    Never modifies gameplay-affecting fields (category, clock day/time, events, memory, conditions, etc.)."""
    autofilled = []
    sel = (context or {}).get('selection') or {}
    opt_id = str(sel.get('option_id') or '').strip()

    checks = settlement.get('checks')
    if isinstance(checks, dict):
        defaults = {
            'intent': '按本幕玩家输入与所选意图核验推进。',
            'knowledge': '已按在场人物与知情边界核验本幕正文。',
            'action': '已按前台实际正文动作与对白完成结构化提取。',
            'pace': '已按本幕自然节奏收束并承接段末抉择。',
        }
        for key, fallback in defaults.items():
            cleaned = _clean_single_line(checks.get(key))
            if not cleaned or cleaned in _AUDIT_PLACEHOLDERS:
                checks[key] = fallback
                autofilled.append(f'checks.{key}')
            elif cleaned != checks.get(key):
                checks[key] = cleaned

    res = settlement.get('resolution')
    if isinstance(res, dict):
        cat = str(res.get('category') or '').strip()
        raw_basis = _clean_single_line(res.get('basis'))
        if not raw_basis or raw_basis in _AUDIT_PLACEHOLDERS:
            if cat == 'SYSTEM':
                res['basis'] = '按本幕系统免费操作事实结算。'
            elif opt_id in ('A', 'B', 'C'):
                res['basis'] = f'按玩家选定的固定{opt_id}档选项实际互动结算。'
            elif cat in ('A', 'B', 'C'):
                res['basis'] = f'按本幕玩家实际行为判定{cat}档结算。'
            else:
                res['basis'] = '按本幕前台实际互动事实结算。'
            autofilled.append('resolution.basis')
        elif raw_basis != res.get('basis'):
            res['basis'] = raw_basis

        clk = res.get('clock')
        if isinstance(clk, dict):
            raw_clk_basis = _clean_single_line(clk.get('basis'))
            if not raw_clk_basis or raw_clk_basis in _AUDIT_PLACEHOLDERS:
                day = clk.get('day')
                tm = clk.get('time') or ''
                clk['basis'] = f'本幕互动自然推进至第{day}天 {tm}'.strip()
                autofilled.append('resolution.clock.basis')
            elif raw_clk_basis != clk.get('basis'):
                clk['basis'] = raw_clk_basis
    return autofilled


_FOREGROUND_NON_RETRYABLE_TAGS = (
    '前台演播',
    '红线拦截',
    '角色不在场或代写玩家台词',
    '角色不在场或模型代写玩家台词',
    '主角代写台词过多',
    '动作角色不在场',
    '旁白不能携带说话人',
    '旁白不带说话人',
    'message.text',
    'decision.prompt',
    'decision.option.text',
    '消息类型无效',
    '剧情须为非空节点数组',
)


def _effective_guardrail_secrets(bundle_state, settlement_or_result=None, context=None):
    """Merge persisted secrets_unlocked with same-turn intel reveal, personal secret unlock, or director beat."""
    base = [str(x).strip() for x in ((bundle_state.get('mechanics') or {}).get('secrets_unlocked') or ()) if str(x).strip()]
    extra = []
    res_obj = None
    if isinstance(settlement_or_result, dict):
        res_obj = settlement_or_result.get('resolution') if isinstance(settlement_or_result.get('resolution'), dict) else None
    if isinstance(res_obj, dict):
        iu = res_obj.get('intel_used')
        if isinstance(iu, dict) and str(iu.get('id') or '').strip():
            extra.append(str(iu.get('id')).strip())
        ss_obj = res_obj.get('scene_state')
        if isinstance(ss_obj, dict) and isinstance(ss_obj.get('unlock_secrets'), list):
            for x in ss_obj['unlock_secrets']:
                if isinstance(x, str) and x.strip() and not x.strip().startswith('INTEL-'):
                    extra.append(x.strip())
    droll = (context or {}).get('director_roll') if isinstance(context, dict) else None
    if isinstance(droll, dict):
        bid = str(droll.get('beat_id') or ((droll.get('beat') or {}).get('id') if isinstance(droll.get('beat'), dict) else '') or '').strip()
        if bid in ('BEAT-T2-STUDIO-PAINTING-QUESTION', 'BEAT-T2-EXHIBITION-CALL'):
            extra.append('SECRET-XNW-PAINTING')
    return list(dict.fromkeys([*base, *extra]))


def is_settlement_retryable_error(msg):
    """Return True if a dual-stage validation error belongs to Stage 2 settlement (or decision-only fallback),
    meaning Stage 1 foreground prose is valid and does not need to be regenerated."""
    text = str(msg or '')
    if not text:
        return False
    if '可补充 fallback_decision' in text:
        return True
    return not any(tag in text for tag in _FOREGROUND_NON_RETRYABLE_TAGS)


def stage1_checkpoint_path(story, key):
    return story._blob(key, '.stage1.json')


def clear_stage1_checkpoint(story, key):
    try:
        stage1_checkpoint_path(story, key).unlink(missing_ok=True)
    except OSError:
        pass


def load_stage1_checkpoint(story, key, job):
    """Return validated Stage 1 checkpoint matching (key, base_revision, save_epoch) or None."""
    path = stage1_checkpoint_path(story, key)
    if not path.is_file() or not isinstance(job, dict):
        return None
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get('version') != 1:
        return None
    if data.get('request_id') != key:
        return None
    if data.get('base_revision') != job.get('base_revision'):
        return None
    if str(data.get('save_epoch') or '') != str(job.get('save_epoch') or ''):
        return None
    fg_text = data.get('foreground_text')
    base_audit = data.get('base_audit')
    if not isinstance(fg_text, str) or not fg_text.strip() or not isinstance(base_audit, dict):
        return None
    return data


def save_stage1_checkpoint(story, key, job, context, checkpoint):
    """Validate foreground prose + Stage 1 receipt and persist checkpoint for Stage-2-only retry."""
    if not isinstance(job, dict) or not isinstance(checkpoint, dict):
        return False
    fg_text = checkpoint.get('foreground_text')
    base_audit = checkpoint.get('base_audit')
    if not isinstance(fg_text, str) or not fg_text.strip() or len(fg_text.encode('utf-8')) > 2 * 1024 * 1024:
        return False
    if not isinstance(base_audit, dict) or base_audit.get('api') != 'Tools.Chat.sendMessageStreaming':
        return False
    outcome = base_audit.get('outcome')
    if (not isinstance(outcome, dict) or outcome.get('type') != 'committed'
            or outcome.get('status') != 'completed' or not isinstance(outcome.get('assistant'), dict)):
        return False
    stamp = outcome['assistant'].get('messageTimestamp')
    user_ts = outcome.get('userMessageTimestamp')
    if type(stamp) is not int or base_audit.get('snapshot_message_timestamp') != stamp:
        return False
    if type(user_ts) is not int or user_ts <= 0:
        return False

    try:
        files = story.store._files()
        mem_text = (files[rr.FILES[0]] or b'').decode('utf-8')
        presence = rr._engine(story.root, story.root).parse_presence_from_memory(mem_text)
        valid_locations = policy(story.root)['locations']
        cur_loc = presence['徐志北']['location']
        cmd = (context or {}).get('command')
        candidate_locs = [cur_loc]
        if isinstance(cmd, dict) and cmd.get('code') == 'move_player' and cmd.get('destination') in valid_locations:
            dest = cmd['destination']
            if dest not in candidate_locs:
                candidate_locs.insert(0, dest)
        protagonist_style = load_story_prefs(story.root)['protagonist_style']
        bundle_state, _, _ = save_store.load_bundle(story.root, files)
        held_intel_ids = list((sp.parse_intel_block(mem_text) or {}).get('held') or ())
        secrets_unlocked = list(dict.fromkeys([
            *_effective_guardrail_secrets(bundle_state, checkpoint.get('settlement'), context),
            *held_intel_ids,
        ]))
        parsed_fg = None
        for loc in candidate_locs:
            allowed_cast = scene_cast(presence, mem_text, loc)
            try:
                fg = sc.parse_stream_story(
                    fg_text,
                    allowed_speakers=allowed_cast,
                    partial=False,
                    valid_destinations=valid_locations,
                    location_aliases=location_aliases(story.root),
                    current_location=loc,
                    allow_missing_decision=True,
                    allow_player_dialogue=(protagonist_style == 'faithful'),
                )
                sc.guardrail_check(
                    story.root, loc, allowed_cast, fg['messages'],
                    memory_text=mem_text, secrets_unlocked=secrets_unlocked,
                    allow_player_dialogue=(protagonist_style == 'faithful'),
                )
                parsed_fg = fg
                break
            except rr.RoundError:
                continue
        if parsed_fg is None:
            return False
    except Exception:
        return False

    raw_msgs = checkpoint.get('foreground_messages')
    fg_msgs = raw_msgs if isinstance(raw_msgs, list) and raw_msgs else parsed_fg['messages']
    gen_ms = checkpoint.get('generation_ms', 0)
    if type(gen_ms) is not int or gen_ms < 0:
        gen_ms = 0
    sanitized_audit = copy.deepcopy(base_audit)
    sanitized_audit.pop('settlement_audit', None)
    record = {
        'version': 1,
        'request_id': key,
        'base_revision': job.get('base_revision', ''),
        'save_epoch': job.get('save_epoch', ''),
        'foreground_text': fg_text,
        'foreground_messages': fg_msgs,
        'generation_ms': gen_ms,
        'base_audit': sanitized_audit,
        'saved_at': time.time(),
    }
    rr._atomic(stage1_checkpoint_path(story, key), rr._json(record))
    return True


def _sanitize_settlement_mechanical_noise(settlement, context, files, root):
    """Deterministically clean strictly unambiguous mechanical/schema noise in Stage 2 settlement JSON.
    Never fabricates evidence, never alters gameplay tags/category, and never guesses semantic truth."""
    cleaned = []
    if not isinstance(settlement, dict):
        return cleaned
    if settlement.get('operation') == '':
        settlement['operation'] = None
        cleaned.append('operation(empty_to_none)')

    fb = settlement.get('fallback_decision')
    if isinstance(fb, dict) and isinstance(fb.get('options'), list):
        for idx, opt in enumerate(fb['options']):
            if isinstance(opt, dict) and opt.get('operation') in ('', None) and 'operation' in opt:
                del opt['operation']
                cleaned.append(f'fallback_decision.options[{idx}].operation(dropped_empty)')

    res = settlement.get('resolution')
    if not isinstance(res, dict):
        return cleaned

    for opt_field in ('task', 'intel_used', 'director_echo', 'scene_state'):
        if res.get(opt_field) == '':
            res[opt_field] = None
            cleaned.append(f'resolution.{opt_field}(empty_to_none)')
    if res.get('conditions') == '':
        res['conditions'] = None
        cleaned.append('resolution.conditions(empty_to_none)')
    elif isinstance(res.get('conditions'), dict) and res['conditions'].get('npc') == '':
        res['conditions']['npc'] = None
        cleaned.append('resolution.conditions.npc(empty_to_none)')
    if isinstance(res.get('sleep'), dict) and res['sleep'].get('start') == '':
        res['sleep']['start'] = None
        cleaned.append('resolution.sleep.start(empty_to_none)')
    if isinstance(res.get('memory'), dict) and res['memory'].get('chronicle_digest') == '':
        res['memory']['chronicle_digest'] = None
        cleaned.append('resolution.memory.chronicle_digest(empty_to_none)')

    # Rule 10: disallow new task when free SYSTEM or an active unfinished task already exists.
    if res.get('task') is not None:
        cat = str(res.get('category') or '').strip()
        has_active_task = False
        try:
            bundle_st, _, _ = save_store.load_bundle(root, files)
            cur_t = ((bundle_st.get('tasks') or {}).get('current'))
            has_active_task = isinstance(cur_t, dict) and cur_t.get('status') != '已完成'
        except Exception:
            has_active_task = False
        if cat == 'SYSTEM' or has_active_task:
            res['task'] = None
            cleaned.append('resolution.task(cleared_disallowed)')

    # Drop strictly no-op monitor-target noise: vigilance_events(target='徐承邺', tags=['无异常回合']).
    # Non-noop vigilance tags on '徐承邺' are intentionally preserved so strict validation rejects & retries them!
    events = res.get('events')
    if isinstance(events, list):
        kept = []
        for ev in events:
            if (isinstance(ev, dict) and ev.get('group') == 'vigilance_events'
                    and ev.get('target') == '徐承邺'
                    and isinstance(ev.get('tags'), list)
                    and ev['tags']
                    and set(ev['tags']) <= {'无异常回合'}):
                cleaned.append('resolution.events.vigilance(dropped_noop_monitor_target)')
                continue
            kept.append(ev)
        if len(kept) != len(events):
            res['events'] = kept

    return cleaned


def normalize_dual_stage(story, context, result):
    """Merge dual-stage foreground script + background SUMMARY settlement into canonical result."""
    if not isinstance(result, dict) or result.get('dual_stage_version') != 1:
        return result, {}
    rr._keys(result, {'dual_stage_version', 'foreground_text', 'settlement'}, '双阶段结果',
             {'dual_stage_version', 'foreground_text', 'settlement'})
    settlement = copy.deepcopy(result['settlement'])
    if not isinstance(settlement, dict):
        raise rr.RoundError('后台结算结果须为JSON对象')
    charged = sp.enabled(story.root)
    allowed_settle = {'operation', 'handoff', 'checks', 'quality_flags', 'fallback_decision'} | ({'resolution'} if charged else set())
    req_settle = {'operation', 'handoff', 'checks'} | ({'resolution'} if charged else set())
    rr._keys(settlement, allowed_settle, '后台结算结果', req_settle)
    files = story.store._files()
    sanitized_notes = _sanitize_settlement_mechanical_noise(settlement, context, files, story.root)
    autofilled_audit = _autofill_settlement_audit_lines(settlement, context)
    if context.get('command') and settlement.get('operation') != context['command']:
        if settlement.get('operation') is not None or not isinstance(settlement.get('handoff'), str) or not settlement.get('handoff').strip():
            raise rr.RoundError('后台结算未保留玩家明确操作；不能执行时须明确待处理且不提交操作')
    mem_text = files[rr.FILES[0]].decode('utf-8')
    presence = rr._engine(story.root, story.root).parse_presence_from_memory(mem_text)
    op = settlement.get('operation')
    valid_locations = policy(story.root)['locations']
    location = presence['徐志北']['location']
    if isinstance(op, dict) and op.get('code') == 'move_player' and op.get('destination') in valid_locations:
        location = op['destination']
    allowed_cast = scene_cast(presence, mem_text, location)
    protagonist_style = load_story_prefs(story.root)['protagonist_style']
    fg = sc.parse_stream_story(
        result['foreground_text'],
        allowed_speakers=allowed_cast,
        partial=False,
        valid_destinations=valid_locations,
        location_aliases=location_aliases(story.root),
        current_location=location,
        allow_missing_decision=True,
        allow_player_dialogue=(protagonist_style == 'faithful'),
    )
    resolved_decision = fg['decision']
    used_fallback_decision = False
    if resolved_decision is None:
        # Enforce redline guardrails on foreground prose BEFORE allowing any fallback_decision recovery.
        bundle_state, _, _ = save_store.load_bundle(story.root, files)
        secrets_unlocked = _effective_guardrail_secrets(bundle_state, settlement, context)
        sc.guardrail_check(
            story.root, location, allowed_cast, fg['messages'],
            memory_text=mem_text, secrets_unlocked=secrets_unlocked,
            allow_player_dialogue=(protagonist_style == 'faithful'),
        )
        raw_fb = settlement.get('fallback_decision')
        if raw_fb in (None, ''):
            reason = fg.get('decision_missing_reason') or '未检测到完整抉择'
            raise rr.RoundError(
                f'前台演播缺少完整的 ---DECISION--- 与 A/B/C 三项抉择（{reason}），'
                '后台结算可补充 fallback_decision 字段以完成本幕提交'
            )
        resolved_decision = _normalize_fallback_decision(
            raw_fb, valid_locations, location, aliases=location_aliases(story.root)
        )
        used_fallback_decision = True
    merged = {
        'messages': fg['messages'],
        'decision': resolved_decision,
        'operation': settlement['operation'],
        'handoff': settlement['handoff'],
        'checks': settlement['checks'],
    }
    if charged:
        merged['resolution'] = settlement['resolution']
    extra = {'dual_stage': True}
    if used_fallback_decision:
        extra['decision_fallback'] = True
    if autofilled_audit:
        extra['audit_lines_autofilled'] = autofilled_audit
    if sanitized_notes:
        extra['settlement_sanitized'] = sanitized_notes
    if 'quality_flags' in settlement:
        qf = settlement['quality_flags']
        if not isinstance(qf, list) or len(qf) > 16 or not all(isinstance(x, str) and len(x) <= 200 for x in qf):
            raise rr.RoundError('quality_flags须为字符串数组')
        extra['quality_flags'] = qf
    return merged, extra


def assemble(story, key, job, result, context, audit):
    result, extra_audit = normalize_dual_stage(story, context, result)
    charged = sp.enabled(story.root)
    fields = {'messages','decision','operation','handoff','checks'} | ({'resolution'} if charged else set())
    rr._keys(result, fields, '互动结果', fields)
    decision(result['decision'], valid_locations=policy(story.root)['locations'])
    rr._keys(result['checks'], {'intent', 'knowledge', 'action', 'pace'}, 'checks', {'intent', 'knowledge', 'action', 'pace'})
    for name, value in result['checks'].items():
        rr._audit_line(value, 'checks.' + name, reason=True)
    if context['command'] and result['operation'] != context['command']:
        if result['operation'] is not None or not isinstance(result['handoff'], str) or not result['handoff'].strip():
            raise rr.RoundError('模型不能变更玩家明确操作；不能执行时须明确待处理且不提交操作')
    # Deterministic zero-cost red-line guardrail check (speaker sovereignty, info-gap secrets, residence lock).
    files = story.store._files()
    mem_text = files[rr.FILES[0]].decode('utf-8')
    presence = rr._engine(story.root, story.root).parse_presence_from_memory(mem_text)
    op = result.get('operation')
    eff_loc = presence['徐志北']['location']
    if isinstance(op, dict) and op.get('code') == 'move_player' and op.get('destination') in policy(story.root)['locations']:
        eff_loc = op['destination']
    eff_cast = scene_cast(presence, mem_text, eff_loc)
    bundle_state, _, _ = save_store.load_bundle(story.root, files)
    effective_unlocked = _effective_guardrail_secrets(bundle_state, result, context)
    protagonist_style = load_story_prefs(story.root)['protagonist_style']
    intimate_active = bool((bundle_state.get('intimate') or {}).get('scene_active'))
    guard = sc.guardrail_check(
        story.root, eff_loc, eff_cast, result['messages'],
        memory_text=mem_text, secrets_unlocked=effective_unlocked,
        allow_player_dialogue=(protagonist_style == 'faithful'),
        panels=bundle_state.get('panels'),
        intimate_active=intimate_active,
    )
    accepted_audit = {**audit, **extra_audit, 'checks': result['checks']}
    if context.get('delivered_echo_ids'):
        accepted_audit['delivered_echo_ids'] = list(context['delivered_echo_ids'])
    if isinstance(context.get('director_roll'), dict):
        accepted_audit['director_roll'] = copy.deepcopy(context['director_roll'])
    if guard.get('warnings'):
        accepted_audit['guardrail_warnings'] = guard['warnings']
    guard_signals = list(guard.get('review_signals') or ())
    s2_signals = sc.extract_settlement_review_signals(
        story.root, extra_audit.get('quality_flags') or (),
        secrets_unlocked=effective_unlocked,
    )
    all_review_signals = guard_signals + s2_signals
    if all_review_signals:
        accepted_audit['review_signals'] = all_review_signals
    if charged:
        if not job.get('reservation') or job['reservation']['status']!='held':raise rr.ConflictError('预扣已结束，拒绝旧结果')
        accepted_audit['reservation'] = copy.deepcopy(job['reservation'])
    accepted_audit['requested_operation'] = copy.deepcopy(context['command'])
    if context['command']:
        accepted_audit['origin'] = 'player_action'
    return {'schema_version': 3 if charged else 2, 'entry_mode': MODE, 'request_id': key,
            **({'resolution':result['resolution']} if charged else {}),
            'base_revision': job.get('working_revision', job['base_revision']), 'input': job['action'],
            **{k: result[k] for k in ('messages', 'decision', 'operation', 'handoff')},
            'selection': job.get('selection'), 'audit': accepted_audit}
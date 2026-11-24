"""Unified P2 save storage: JSON single-source-of-truth + deterministic one-way .txt views.

Authoritative files inside 存档/:
  - 存档/save_state.json   : all structured machine state (panels, presence, micro, buffs,
                             counters, mechanics, vigilance, tasks, items, shop, intel,
                             director, lifecycle, runtime).
  - 存档/四层记忆.json      : structured L1-L4 memory layers with prologue_active & known_by.
  - 存档/近期演播.json      : rolling latest N accepted interaction segments + playback state.

One-way rendered read-only views (kept synchronized on every commit for human inspection,
manual Operit chats, and legacy line-addressed archive reads):
  - 存档/全局记忆库.txt
  - 存档/徐志北道具图鉴.txt
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

SAVE_STATE_PATH = '存档/save_state.json'
MEMORY_LAYERS_PATH = '存档/四层记忆.json'
RECENT_PLAYBACK_PATH = '存档/近期演播.json'
RENDERED_MEMORY_PATH = '存档/全局记忆库.txt'
RENDERED_ITEMS_PATH = '存档/徐志北道具图鉴.txt'

MAX_RECENT_SEGMENTS = 12
PROLOGUE_MARKER = '【系统隐藏标记：以上为新游戏序幕锚点，剧情从此刻正式开始计算】'

HEROINES = ('沈知韫', '苏婉青', '徐念薇')
PRESENCE_ORDER = ('沈知韫', '徐念薇', '苏婉青', '徐志北')
PANEL_ORDER = ('系统宿主', '沈知韫', '徐念薇', '苏婉青', '徐承邺')
VIGILANCE_TARGETS = ('沈知韫', '苏婉青', '徐念薇', '徐志北')
MICRO_STATES = ('momentary_ease', 'residual_tension', 'confusion_debt')
DEFAULT_PRESENCE = {
    '沈知韫': ('徐家主宅', '常住'),
    '徐念薇': ('大学', '工作日在大学'),
    '苏婉青': ('市中心顶层公寓', '常住'),
    '徐志北': ('徐家主宅', '常住'),
}
MEMORY_LAYER_HEADERS = (
    ('L1', '▲ 第一层：【即时运存区】'),
    ('L2', '▲ 第二层：【回想运存区】'),
    ('L3', '▲ 第三层：【近期事实缓存区】'),
    ('L4', '▲ 第四层：【深渊纪元浓缩区】'),
)
_EMPTY_MARKERS = frozenset({'', '（空）', '(空)', '无', '（无）', '(无)'})
_LABEL_RE = re.compile(r'^【(\d+)(?:-(\d+))?】')
_PROLOGUE_LINE_RE = re.compile(r'(?m)^\s*【系统隐藏标记：[^\n]*】\s*$')


def _sha256_bytes(data):
    if data is None:
        return ''
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.ss-tmp-' + uuid.uuid4().hex)
    try:
        with tmp.open('xb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def default_director():
    return {
        'calm_streak': 0,
        'global_cooldown': 0,
        'turns_since_beat': 99,
        'scene_location': '',
        'scene_turns': 0,
        'clock_tick_acc': 0,
        'sensual_drought': 0,
        'last_time_slot': '',
        'event_cooldowns': {},
        'consumed_once': [],
        'pending_seeds': [],
        'active_threads': [],
        'next_thread_seq': 1,
        'offstage_clocks': {},
        'recent_channels': [],
    }


PRIVACY_LEVELS = ('open_public', 'semi_open', 'thin_wall', 'under_cover', 'locked_private')
PRIVACY_LABELS = {
    'open_public': '公共开放',
    'semi_open': '虚掩半开放',
    'thin_wall': '隔墙有人',
    'under_cover': '同席暗触',
    'locked_private': '反锁私密',
}
ATTIRE_STATES = ('neat', 'disheveled', 'half_undressed', 'wet', 'torn')
ATTIRE_LABELS = {
    'neat': '整洁',
    'disheveled': '凌乱滑落',
    'half_undressed': '半褪暴露',
    'wet': '潮湿贴肤',
    'torn': '破损撕裂',
}
INTER_HEROINE_PAIRS = (
    '沈知韫->苏婉青', '沈知韫->徐念薇',
    '苏婉青->沈知韫', '苏婉青->徐念薇',
    '徐念薇->沈知韫', '徐念薇->苏婉青',
)
INTER_HEROINE_LABELS = {
    0: '无觉察',
    1: '疑心端倪',
    2: '撞破掌握',
    3: '默契共谋',
}


def default_intimate():
    return {
        'scene_active': False,
        'session_beats': 0,
        'session_orgasms': {name: 0 for name in HEROINES},
        'privacy': 'open_public',
        'sub_location': '',
        'present_actors': [],
        'noise_risk': 0,
        'attire': {
            name: {'outfit': 'default', 'state': 'neat', 'gifted_items': []}
            for name in HEROINES
        },
        'traces': {name: [] for name in HEROINES},
        'inter_heroine': {pair: 0 for pair in INTER_HEROINE_PAIRS},
    }


def default_mechanics():
    return {
        'su_affection_85_unlocked': False,
        'secrets_unlocked': [],
        'nap_last_day': {name: 0 for name in HEROINES},
        'insomnia_applied': {name: False for name in HEROINES},
        'first_triggers': {name: [] for name in HEROINES},
        'c_streak': {name: {'tier': '', 'count': 0} for name in HEROINES},
        'depravity_unlocked_caps': {name: 30 for name in HEROINES},
        'pregnancy_latent_until': {name: 0 for name in HEROINES},
        'masturbation_trace': {name: 0 for name in HEROINES},
        'charm_scene_used': False,
    }


def default_state():
    return {
        'version': 2,
        'panels': {
            '系统宿主': {'积分': 0, '经验值': 0, '体力': 100, '魅力': 70, '商业嗅觉': 0},
            '沈知韫': {'好感': 95, '堕落': 0, '欲望': 0, '羞耻': 100, '体力': 100, '高潮': 0, '内射': 0, '怀孕': False, '被动': 0},
            '徐念薇': {'好感': 30, '堕落': 0, '欲望': 0, '羞耻': 99, '体力': 100, '高潮': 0, '内射': 0, '怀孕': False, '被动': 0},
            '苏婉青': {'好感': 40, '堕落': 0, '欲望': 0, '羞耻': 99, '体力': 100, '高潮': 0, '内射': 0, '怀孕': False, '被动': 0},
            '徐承邺': {'堕落': 0},
        },
        'presence': {
            name: {'location': loc, 'reason': reason}
            for name, (loc, reason) in DEFAULT_PRESENCE.items()
        },
        'micro_states': {
            name: {k: False for k in MICRO_STATES}
            for name in HEROINES
        },
        'buffs': {name: [] for name in HEROINES},
        'counters': {
            '破局_日常冗余': 0,
            '破局_模式重复': 0,
            '破局_社交淤积': 0,
            '破局_张力淤积': 0,
            '空耗_连续未纾解_沈知韫': 0,
            '空耗_连续未纾解_苏婉青': 0,
            '空耗_连续未纾解_徐念薇': 0,
            '连续守护回合': 0,
        },
        'mechanics': default_mechanics(),
        'intimate': default_intimate(),
        'vigilance': {
            '位置': '外地',
            '目标': {
                name: {'警惕': 0, '发现': 0, '发现几率': 0}
                for name in VIGILANCE_TARGETS
            },
        },
        'tasks': {
            'current': None,
            'history': [],
            'pending_items': [],
        },
        'items': {
            'next_seq': 1,
            'active': [],
            'deployed': [],
            'delivered': [],
            'history': [],
        },
        'shop': {
            'redeemed': {},
            'recent': [],
            'echoes': [],
            'dynamic_catalog': [],
            'next_dyn_seq': 1,
        },
        'intel': {
            'held': [],
            'consumed': [],
            'su_ab_contacts': 0,
            'leverage_armed': '',
        },
        'director': default_director(),
        'lifecycle': {
            'version': 1,
            'round': 0,
            'micro': {},
            'ab_streak': 0,
            'scopes': {},
            'legacy_counters': {},
        },
        'runtime': {
            'clock': None,
            'weekday': '',
            'prologue': None,
            'memory_round': 1,
            'last_closed': 0,
            'phase': 'ready',
            'item_recovered': 0,
            'action_index': 0,
            'closed_by': '',
            'last_sequence': 0,
            'last_segment_id': '',
        },
        'rendered_sha256': {
            'memory_txt': '',
            'items_txt': '',
            'data_runtime': '',
        },
    }


def default_layers(prologue_text='周二上午，徐家主宅。新的一天刚刚开始。', *, prologue_active=True, known_by=None):
    clean = strip_prologue_marker(prologue_text)
    clean = _LABEL_RE.sub('', clean).strip()
    entries = []
    if clean:
        entries.append({
            'start_round': 1,
            'end_round': 1,
            'label': '【1】',
            'text': clean,
            'known_by': list(known_by) if isinstance(known_by, list) else None,
        })
    return {
        'version': 1,
        'prologue_active': bool(prologue_active),
        'layers': {
            'L1': entries,
            'L2': [],
            'L3': [],
            'L4': [],
        },
    }


def default_recent():
    return {
        'version': 1,
        'playback': None,
        'segments': [],
    }


def strip_prologue_marker(text):
    if not text:
        return ''
    cleaned = _PROLOGUE_LINE_RE.sub('', str(text))
    cleaned = cleaned.replace(PROLOGUE_MARKER, '')
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()


def _parse_int(value, default=0):
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    m = re.search(r'-?\d+', str(value or ''))
    return int(m.group(0)) if m else default


def _parse_entry_string(raw, *, known_by=None):
    cleaned = strip_prologue_marker(raw)
    m = _LABEL_RE.match(cleaned)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2) or start)
    label = f'【{start}】' if start == end else f'【{start}-{end}】'
    body = cleaned[m.end():].strip()
    return {
        'start_round': start,
        'end_round': end,
        'label': label,
        'text': body,
        'known_by': list(known_by) if isinstance(known_by, list) else None,
    }


def entry_to_string(entry):
    label = entry.get('label')
    if not label:
        s = int(entry.get('start_round', 1))
        e = int(entry.get('end_round', s))
        label = f'【{s}】' if s == e else f'【{s}-{e}】'
    body = strip_prologue_marker(entry.get('text', ''))
    return f'{label}{body}'


def layer_strings(mem_layers):
    layers = (mem_layers or {}).get('layers') or {}
    return {
        key: [entry_to_string(item) for item in (layers.get(key) or [])]
        for key in ('L1', 'L2', 'L3', 'L4')
    }


def set_layer_strings(mem_layers, str_layers, *, prologue_active=None):
    out = copy.deepcopy(mem_layers) if isinstance(mem_layers, dict) else default_layers('', prologue_active=False)
    old_layers = out.get('layers') or {}
    new_layers = {}
    for key in ('L1', 'L2', 'L3', 'L4'):
        old_known = {
            entry_to_string(e): e.get('known_by')
            for e in (old_layers.get(key) or [])
            if isinstance(e, dict)
        }
        items = []
        for raw in (str_layers.get(key) or []):
            parsed = _parse_entry_string(raw, known_by=old_known.get(strip_prologue_marker(raw)))
            if parsed is not None:
                items.append(parsed)
        new_layers[key] = items
    out['layers'] = new_layers
    if prologue_active is not None:
        out['prologue_active'] = bool(prologue_active)
    return out


def normalize_state(raw):
    base = default_state()
    if not isinstance(raw, dict):
        return base
    # Panels
    raw_panels = raw.get('panels') if isinstance(raw.get('panels'), dict) else {}
    for name, defaults in base['panels'].items():
        rp = raw_panels.get(name) if isinstance(raw_panels.get(name), dict) else {}
        for k, dv in defaults.items():
            if k in rp:
                if isinstance(dv, bool):
                    base['panels'][name][k] = bool(rp[k])
                else:
                    base['panels'][name][k] = _parse_int(rp[k], dv)
    # Presence
    raw_pres = raw.get('presence') if isinstance(raw.get('presence'), dict) else {}
    for name in PRESENCE_ORDER:
        rp = raw_pres.get(name)
        if isinstance(rp, dict) and rp.get('location'):
            base['presence'][name] = {
                'location': str(rp['location']).strip(),
                'reason': str(rp.get('reason') or DEFAULT_PRESENCE[name][1]).strip(),
            }
    # Micro states
    raw_micro = raw.get('micro_states') if isinstance(raw.get('micro_states'), dict) else {}
    for name in HEROINES:
        rm = raw_micro.get(name) if isinstance(raw_micro.get(name), dict) else {}
        for k in MICRO_STATES:
            if k in rm:
                base['micro_states'][name][k] = bool(rm[k])
    # Buffs
    raw_buffs = raw.get('buffs') if isinstance(raw.get('buffs'), dict) else {}
    for name in HEROINES:
        lst = raw_buffs.get(name)
        if isinstance(lst, list):
            cleaned = []
            for item in lst:
                if isinstance(item, dict) and item.get('name'):
                    turns = _parse_int(item.get('turns'), 0)
                    if turns > 0:
                        cleaned.append({
                            'name': str(item['name']).strip(),
                            'turns': turns,
                            'effect': str(item.get('effect') or '').strip(),
                        })
            base['buffs'][name] = cleaned
    # Counters
    raw_counters = raw.get('counters') if isinstance(raw.get('counters'), dict) else {}
    if raw_counters:
        merged_counters = dict(base['counters'])
        for k, v in raw_counters.items():
            if isinstance(k, str) and k:
                merged_counters[k] = max(0, _parse_int(v, 0))
        # Drop deprecated global 空耗_连续未纾解 if zero
        if merged_counters.get('空耗_连续未纾解') == 0:
            merged_counters.pop('空耗_连续未纾解', None)
        base['counters'] = merged_counters
    # Mechanics
    raw_mech = raw.get('mechanics') if isinstance(raw.get('mechanics'), dict) else {}
    mech = base['mechanics']
    mech['su_affection_85_unlocked'] = bool(
        raw_mech.get('su_affection_85_unlocked', False)
        or base['panels']['苏婉青']['好感'] > 85
    )
    if isinstance(raw_mech.get('secrets_unlocked'), list):
        mech['secrets_unlocked'] = list(dict.fromkeys(
            str(x).strip() for x in raw_mech['secrets_unlocked'] if isinstance(x, str) and x.strip()
        ))
    raw_nap = raw_mech.get('nap_last_day') if isinstance(raw_mech.get('nap_last_day'), dict) else {}
    for name in HEROINES:
        mech['nap_last_day'][name] = max(0, _parse_int(raw_nap.get(name), 0))
    raw_ins = raw_mech.get('insomnia_applied') if isinstance(raw_mech.get('insomnia_applied'), dict) else {}
    for name in HEROINES:
        mech['insomnia_applied'][name] = bool(raw_ins.get(name, False))
    raw_first = raw_mech.get('first_triggers') if isinstance(raw_mech.get('first_triggers'), dict) else {}
    for name in HEROINES:
        vals = raw_first.get(name)
        if isinstance(vals, list):
            mech['first_triggers'][name] = list(dict.fromkeys(
                str(x).strip() for x in vals if isinstance(x, str) and x.strip()
            ))
    raw_streak = raw_mech.get('c_streak') if isinstance(raw_mech.get('c_streak'), dict) else {}
    for name in HEROINES:
        st = raw_streak.get(name)
        if isinstance(st, dict):
            mech['c_streak'][name] = {
                'tier': str(st.get('tier') or '').strip(),
                'count': max(0, _parse_int(st.get('count'), 0)),
            }
    raw_dep_caps = raw_mech.get('depravity_unlocked_caps') if isinstance(raw_mech.get('depravity_unlocked_caps'), dict) else {}
    for name in HEROINES:
        cur_dep_val = _parse_int((base.get('panels', {}).get(name) or {}).get('堕落'), 0)
        implied_cap = 100 if cur_dep_val > 90 else (90 if cur_dep_val > 60 else (60 if cur_dep_val > 30 else 30))
        saved_cap = _parse_int(raw_dep_caps.get(name), 30)
        merged_cap = max(implied_cap, saved_cap)
        mech['depravity_unlocked_caps'][name] = 100 if merged_cap >= 100 else (90 if merged_cap >= 90 else (60 if merged_cap >= 60 else 30))
    raw_latent = raw_mech.get('pregnancy_latent_until') if isinstance(raw_mech.get('pregnancy_latent_until'), dict) else {}
    raw_mast = raw_mech.get('masturbation_trace') if isinstance(raw_mech.get('masturbation_trace'), dict) else {}
    for name in HEROINES:
        if base['panels'].get(name, {}).get('怀孕') is True:
            mech['pregnancy_latent_until'][name] = 0
        else:
            mech['pregnancy_latent_until'][name] = max(0, _parse_int(raw_latent.get(name), 0))
        mech['masturbation_trace'][name] = max(0, _parse_int(raw_mast.get(name), 0))
    mech['charm_scene_used'] = bool(raw_mech.get('charm_scene_used', False))
    # Intimate / Privacy / Attire / Traces / Inter-Heroine
    raw_int = raw.get('intimate') if isinstance(raw.get('intimate'), dict) else {}
    intl = base['intimate']
    intl['scene_active'] = bool(raw_int.get('scene_active', False))
    intl['session_beats'] = max(0, _parse_int(raw_int.get('session_beats'), 0)) if intl['scene_active'] else 0
    raw_sorg = raw_int.get('session_orgasms') if isinstance(raw_int.get('session_orgasms'), dict) else {}
    for name in HEROINES:
        intl['session_orgasms'][name] = max(0, _parse_int(raw_sorg.get(name), 0)) if intl['scene_active'] else 0
    priv = str(raw_int.get('privacy') or 'open_public').strip()
    intl['privacy'] = priv if priv in PRIVACY_LEVELS else 'open_public'
    intl['sub_location'] = str(raw_int.get('sub_location') or '').strip()[:48]
    raw_actors = raw_int.get('present_actors')
    if isinstance(raw_actors, list):
        valid_actors = set(HEROINES) | {'徐承邺'}
        intl['present_actors'] = list(dict.fromkeys(
            str(a).strip() for a in raw_actors if isinstance(a, str) and str(a).strip() in valid_actors
        ))
    intl['noise_risk'] = max(0, min(100, _parse_int(raw_int.get('noise_risk'), 0)))
    raw_attire = raw_int.get('attire') if isinstance(raw_int.get('attire'), dict) else {}
    for name in HEROINES:
        ra = raw_attire.get(name) if isinstance(raw_attire.get(name), dict) else {}
        outfit = str(ra.get('outfit') or 'default').strip()[:64] or 'default'
        astate = str(ra.get('state') or 'neat').strip()
        if astate not in ATTIRE_STATES:
            astate = 'neat'
        gifted = ra.get('gifted_items')
        clean_gifted = list(dict.fromkeys(
            str(g).strip()[:64] for g in (gifted or []) if isinstance(g, str) and str(g).strip()
        ))[:12] if isinstance(gifted, list) else []
        intl['attire'][name] = {'outfit': outfit, 'state': astate, 'gifted_items': clean_gifted}
    raw_traces = raw_int.get('traces') if isinstance(raw_int.get('traces'), dict) else {}
    for name in HEROINES:
        tlist = raw_traces.get(name)
        clean_traces = []
        if isinstance(tlist, list):
            for tr in tlist:
                if not isinstance(tr, dict):
                    continue
                kind = str(tr.get('kind') or '').strip()[:24]
                desc = str(tr.get('desc') or kind).strip()[:80]
                turns = _parse_int(tr.get('turns'), 0)
                if kind and turns > 0:
                    clean_traces.append({
                        'kind': kind,
                        'desc': desc,
                        'turns': min(24, turns),
                        'visible': bool(tr.get('visible', True)),
                    })
        intl['traces'][name] = clean_traces[-6:]
    raw_ih = raw_int.get('inter_heroine') if isinstance(raw_int.get('inter_heroine'), dict) else {}
    for pair in INTER_HEROINE_PAIRS:
        intl['inter_heroine'][pair] = max(0, min(3, _parse_int(raw_ih.get(pair), 0)))
    # Vigilance
    raw_vig = raw.get('vigilance') if isinstance(raw.get('vigilance'), dict) else {}
    if raw_vig.get('位置'):
        base['vigilance']['位置'] = str(raw_vig['位置']).strip()
    raw_vt = raw_vig.get('目标') if isinstance(raw_vig.get('目标'), dict) else {}
    for name in VIGILANCE_TARGETS:
        t = raw_vt.get(name)
        if isinstance(t, dict):
            base['vigilance']['目标'][name] = {
                '警惕': max(0, _parse_int(t.get('警惕'), 0)),
                '发现': max(0, _parse_int(t.get('发现'), 0)),
                '发现几率': max(0, min(100, _parse_int(t.get('发现几率'), 0))),
            }
    # Tasks
    raw_tasks = raw.get('tasks') if isinstance(raw.get('tasks'), dict) else {}
    if isinstance(raw_tasks.get('current'), dict):
        base['tasks']['current'] = copy.deepcopy(raw_tasks['current'])
    if isinstance(raw_tasks.get('history'), list):
        base['tasks']['history'] = [str(x).strip() for x in raw_tasks['history'] if str(x).strip()][:3]
    pending = []
    if isinstance(raw_tasks.get('pending_items'), list):
        pending = [str(x).strip() for x in raw_tasks['pending_items'] if str(x).strip()]
    elif raw_tasks.get('pending_item'):
        pending = [str(raw_tasks['pending_item']).strip()]
    base['tasks']['pending_items'] = list(dict.fromkeys(pending))
    # Items
    raw_items = raw.get('items') if isinstance(raw.get('items'), dict) else {}
    max_seq = 0
    for bucket in ('active', 'deployed', 'delivered', 'history'):
        arr = raw_items.get(bucket)
        if isinstance(arr, list):
            clean_arr = []
            for it in arr:
                if not isinstance(it, dict) or not it.get('name'):
                    continue
                item = normalize_item_dict(it)
                m = re.fullmatch(r'ITEM-(\d+)', str(item.get('id') or ''))
                if m:
                    max_seq = max(max_seq, int(m.group(1)))
                clean_arr.append(item)
            base['items'][bucket] = clean_arr
    base['items']['next_seq'] = max(_parse_int(raw_items.get('next_seq'), 1), max_seq + 1)
    # Shop / Intel / Director / Lifecycle / Runtime
    if isinstance(raw.get('shop'), dict):
        rs = raw['shop']
        base['shop']['redeemed'] = {str(k): _parse_int(v, 0) for k, v in (rs.get('redeemed') or {}).items() if _parse_int(v, 0) > 0}
        base['shop']['recent'] = [str(x).strip() for x in (rs.get('recent') or []) if str(x).strip()][:8]
        base['shop']['echoes'] = [copy.deepcopy(e) for e in (rs.get('echoes') or []) if isinstance(e, dict) and e.get('id')][-4:]
        dyn_raw = rs.get('dynamic_catalog')
        dyn_clean = []
        max_dyn_seq = 0
        seen_dyn = set()
        if isinstance(dyn_raw, list):
            for entry in dyn_raw:
                if not isinstance(entry, dict):
                    continue
                did = str(entry.get('id') or '').strip()
                dm = re.fullmatch(r'DYN-(\d+)', did)
                if not dm or did in seen_dyn:
                    continue
                seen_dyn.add(did)
                max_dyn_seq = max(max_dyn_seq, int(dm.group(1)))
                dyn_clean.append(copy.deepcopy(entry))
        base['shop']['dynamic_catalog'] = dyn_clean[-30:]
        base['shop']['next_dyn_seq'] = max(_parse_int(rs.get('next_dyn_seq'), 1), max_dyn_seq + 1)
    if isinstance(raw.get('intel'), dict):
        ri = raw['intel']
        base['intel']['held'] = list(dict.fromkeys(str(x) for x in (ri.get('held') or []) if str(x)))
        base['intel']['consumed'] = list(dict.fromkeys(str(x) for x in (ri.get('consumed') or []) if str(x) and str(x) not in base['intel']['held']))
        base['intel']['su_ab_contacts'] = max(0, _parse_int(ri.get('su_ab_contacts'), 0))
        armed = str(ri.get('leverage_armed') or '')
        base['intel']['leverage_armed'] = armed if armed in base['intel']['held'] else ''
    if isinstance(raw.get('director'), dict):
        base['director'].update(copy.deepcopy(raw['director']))
    if isinstance(raw.get('lifecycle'), dict):
        base['lifecycle'].update(copy.deepcopy(raw['lifecycle']))
    if isinstance(raw.get('runtime'), dict):
        rrt = raw['runtime']
        for k in base['runtime']:
            if k in rrt:
                base['runtime'][k] = copy.deepcopy(rrt[k])
    if isinstance(raw.get('rendered_sha256'), dict):
        for k in base['rendered_sha256']:
            if isinstance(raw['rendered_sha256'].get(k), str):
                base['rendered_sha256'][k] = raw['rendered_sha256'][k]
    return base


VALID_USAGE_MODES = ('gift', 'consumable_host', 'consumable_target', 'reusable_tool', 'deployable_device')


def infer_usage_mode(sys_eff='', giftable=True, explicit_mode=''):
    mode = str(explicit_mode or '').strip()
    if mode in VALID_USAGE_MODES:
        return mode
    eff = str(sys_eff or '').strip()
    if eff.startswith('host_stamina:'):
        return 'consumable_host'
    if eff.startswith('buff:'):
        return 'consumable_target'
    if eff.startswith('deploy_device:'):
        return 'deployable_device'
    return 'gift' if giftable else 'reusable_tool'


def normalize_item_dict(it):
    dur = str(it.get('duration') if it.get('duration') is not None else '无').strip() or '无'
    rem_turns = it.get('remaining_turns')
    if rem_turns is None:
        rem_str = str(it.get('remaining') or '').strip()
        m = re.match(r'^(\d+)\s*回合$', rem_str)
        if m:
            rem_turns = int(m.group(1))
        elif '临时' in str(it.get('type') or '') and re.fullmatch(r'\d+', dur):
            rem_turns = int(dur)
    if rem_turns is not None:
        rem_turns = max(0, _parse_int(rem_turns, 0))
    remaining_str = f'{rem_turns}回合' if rem_turns is not None else (str(it.get('remaining') or '无').strip() or '无')
    sys_eff = str(it.get('system_effect') or '').strip()
    giftable = it.get('giftable')
    if type(giftable) is not bool:
        if isinstance(giftable, str):
            giftable = giftable.strip() not in ('否', 'false', 'False', '0', '不可赠予')
        else:
            giftable = not bool(sys_eff)
    usage_mode = infer_usage_mode(sys_eff, giftable, it.get('usage_mode'))
    hidden_raw = it.get('hidden')
    if type(hidden_raw) is bool:
        hidden = hidden_raw
    elif isinstance(hidden_raw, str) and hidden_raw.strip():
        hidden = hidden_raw.strip() not in ('否', 'false', 'False', '0')
    else:
        hidden = True
    return {
        'id': str(it.get('id') or '').strip(),
        'name': str(it.get('name') or '未命名道具').strip(),
        'type': str(it.get('type') or '永久性').strip(),
        'category': str(it.get('category') or '').strip(),
        'usage_mode': usage_mode,
        'desc': str(it.get('desc') or '未填写').strip(),
        'quantity': max(1, _parse_int(it.get('quantity'), 1)),
        'obtain_round': str(it.get('obtain_round') if it.get('obtain_round') is not None else '').strip(),
        'status': str(it.get('status') or '仓库中').strip(),
        'location': str(it.get('location') or '无').strip(),
        'spot': str(it.get('spot') or '').strip(),
        'hidden': hidden,
        'installed_clock': str(it.get('installed_clock') or '').strip(),
        'detected_risk': max(0, min(100, _parse_int(it.get('detected_risk'), 0))),
        'target': str(it.get('target') or '未使用').strip(),
        'duration': dur,
        'remaining': remaining_str,
        'remaining_turns': rem_turns,
        'expire_rule': str(it.get('expire_rule') or '无').strip(),
        'usage_record': str(it.get('usage_record') or '无').strip(),
        'remark': str(it.get('remark') or it.get('note') or '无').strip() or '无',
        'system_effect': sys_eff,
        'giftable': giftable,
    }


def _parse_legacy_items(item_text):
    items_out = {'next_seq': 1, 'active': [], 'deployed': [], 'delivered': [], 'history': []}
    if not item_text:
        return items_out
    max_seq = 0
    for m in re.finditer(r'【道具ID】：ITEM-(\d+)', item_text):
        max_seq = max(max_seq, int(m.group(1)))

    def _extract_zone(zone_text):
        found = []
        pat = re.compile(r'(?m)^【道具名称】：([^\n]+)\n[\s\S]*?(?=\n\n【道具名称】|\n={5,}|\n▼|\Z)')
        for match in pat.finditer(zone_text or ''):
            block = match.group(0).strip()
            fields = dict(re.findall(r'^【([^】]+)】：([^\n]*)$', block, re.M))
            name = (fields.get('道具名称') or match.group(1)).strip()
            item_id = (fields.get('道具ID') or '').strip()
            if not item_id or not re.fullmatch(r'ITEM-\d+', item_id):
                continue
            rem_str = (fields.get('剩余时效') or '').strip()
            rm = re.match(r'^(\d+)\s*回合$', rem_str)
            gift_raw = fields.get('可赠予')
            sys_eff = (fields.get('系统效果') or '').strip()
            if gift_raw is not None and gift_raw.strip():
                giftable = gift_raw.strip() not in ('否', 'false', 'False', '0', '不可赠予')
            else:
                giftable = not bool(sys_eff)
            found.append(normalize_item_dict({
                'id': item_id,
                'name': name,
                'type': fields.get('类型', '永久性'),
                'category': fields.get('分类', ''),
                'usage_mode': fields.get('使用模式', ''),
                'desc': fields.get('描述', '未填写'),
                'quantity': _parse_int(fields.get('数量'), 1),
                'obtain_round': fields.get('获得回合', ''),
                'status': fields.get('当前状态', '仓库中'),
                'location': fields.get('位置', '无'),
                'spot': fields.get('安装点位', ''),
                'hidden': fields.get('隐蔽部署', '是'),
                'installed_clock': fields.get('部署时间', ''),
                'detected_risk': _parse_int(fields.get('暴露风险'), 0),
                'target': fields.get('使用对象', '未使用'),
                'duration': fields.get('时效', '无'),
                'remaining': rem_str or '无',
                'remaining_turns': int(rm.group(1)) if rm else None,
                'expire_rule': fields.get('过期规则', '无'),
                'usage_record': fields.get('使用记录', '无'),
                'remark': fields.get('备注', '无'),
                'system_effect': sys_eff,
                'giftable': giftable,
            }))
        return found

    act_idx = item_text.find('▼ 活跃道具区 ▼')
    dep_idx = item_text.find('▼ 已部署装置区 ▼')
    deliv_idx = item_text.find('▼ 已交付道具区 ▼')
    hist_idx = item_text.find('▼ 已过期/已消耗道具历史区 ▼')
    tpl_idx = item_text.find('▼ 格式模板区 ▼')

    def _next_stop(start_pos, *candidates):
        stops = [c for c in candidates if c != -1 and c > start_pos]
        return min(stops) if stops else len(item_text)

    if act_idx != -1:
        end_act = _next_stop(act_idx, dep_idx, deliv_idx, hist_idx, tpl_idx)
        for it in _extract_zone(item_text[act_idx:end_act]):
            if it['status'] == '已交付':
                items_out['delivered'].append(it)
            elif it['status'] == '已部署':
                items_out['deployed'].append(it)
            else:
                items_out['active'].append(it)
    if dep_idx != -1:
        end_dep = _next_stop(dep_idx, deliv_idx, hist_idx, tpl_idx)
        items_out['deployed'].extend(_extract_zone(item_text[dep_idx:end_dep]))
    if deliv_idx != -1:
        end_del = _next_stop(deliv_idx, hist_idx, tpl_idx)
        items_out['delivered'].extend(_extract_zone(item_text[deliv_idx:end_del]))
    if hist_idx != -1:
        end_hist = _next_stop(hist_idx, tpl_idx)
        items_out['history'].extend(_extract_zone(item_text[hist_idx:end_hist]))

    items_out['next_seq'] = max(1, max_seq + 1)
    return items_out


def migrate_from_legacy_texts(memory_text='', items_text='', data_dict=None, base_state=None):
    """Parse legacy 全局记忆库.txt + 徐志北道具图鉴.txt + data.json into P2 (state, layers)."""
    state = normalize_state(base_state) if base_state else default_state()
    layers = default_layers('', prologue_active=False)

    mem = memory_text or ''
    if mem:
        pre = mem.split('▲ 第一层：', 1)[0]
        cur_part = pre.split('▶ 上回合历史快照', 1)[0]

        # 1. Panels
        m_host = re.search(r'^\[系统宿主\]([^\n]+)', cur_part, re.M)
        if m_host:
            for attr in ('积分', '经验值', '体力', '魅力', '商业嗅觉'):
                am = re.search(rf'{re.escape(attr)}\s*(-?\d+)', m_host.group(1))
                if am:
                    state['panels']['系统宿主'][attr] = int(am.group(1))
        for name in ('沈知韫', '徐念薇', '苏婉青'):
            m_char = re.search(rf'^\[{re.escape(name)}\]([^\n]+)', cur_part, re.M)
            if m_char:
                line = m_char.group(1)
                for attr in ('好感', '堕落', '欲望', '羞耻', '体力'):
                    am = re.search(rf'{re.escape(attr)}\s*(-?\d+)', line)
                    if am:
                        state['panels'][name][attr] = int(am.group(1))
                om = re.search(r'高潮\s*(\d+)%?', line)
                if om:
                    state['panels'][name]['高潮'] = int(om.group(1))
                cm = re.search(r'内射\s*(\d+)次?', line)
                if cm:
                    state['panels'][name]['内射'] = int(cm.group(1))
                pm = re.search(r'怀孕\s*(True|False)', line)
                if pm:
                    state['panels'][name]['怀孕'] = (pm.group(1) == 'True')
                lm = re.search(r'被动\s*Lv\.?(\d+)', line)
                if lm:
                    state['panels'][name]['被动'] = int(lm.group(1))
        m_xcy = re.search(r'^\[徐承邺\][^\n]*堕落\s*(-?\d+)', cur_part, re.M)
        if m_xcy:
            state['panels']['徐承邺']['堕落'] = int(m_xcy.group(1))
        if state['panels']['苏婉青']['好感'] > 85:
            state['mechanics']['su_affection_85_unlocked'] = True

        # 2. Presence
        pm = re.search(r'【人物所在】[^\n]*\n(.*?)(?=\n【|\n▶|\n={5,}|\Z)', cur_part, re.S)
        if pm:
            for raw_ln in pm.group(1).splitlines():
                ln = raw_ln.strip()
                if not ln:
                    continue
                rm = re.match(r'^([^：:|]+)[：:]\s*([^|｜]+?)(?:\s*[|｜]\s*事由[：:]\s*(.+))?$', ln)
                if rm and rm.group(1).strip() in PRESENCE_ORDER:
                    who = rm.group(1).strip()
                    state['presence'][who] = {
                        'location': rm.group(2).strip(),
                        'reason': (rm.group(3) or DEFAULT_PRESENCE[who][1]).strip(),
                    }

        # 3. Micro states
        mm = re.search(r'^【当前激活微状态】[ \t]*\n(.*?)(?=^={5,}|^【|^▶\s*上回合|\Z)', cur_part, re.M | re.S)
        if mm:
            for part in re.finditer(r'^▶[ \t]*([^\r\n]+)\n(.*?)(?=^▶|\Z)', mm.group(1), re.M | re.S):
                who = part.group(1).strip()
                if who in HEROINES:
                    for key, val in re.findall(r'\b(momentary_ease|residual_tension|confusion_debt):[ \t]*(true|false)\b', part.group(2)):
                        state['micro_states'][who][key] = (val == 'true')

        # 4. Buffs
        bm = re.search(r'【当前持久化状态与BUFF】([\s\S]*?)(?=\n={5,}|\n【|\Z)', pre)
        if bm:
            cur_who = None
            for raw_ln in bm.group(1).splitlines():
                ln = raw_ln.strip()
                if not ln:
                    continue
                if ln.startswith('▶'):
                    cur_who = ln.lstrip('▶').strip()
                    if cur_who in HEROINES:
                        state['buffs'][cur_who] = []
                elif cur_who in HEROINES and ln.startswith('-'):
                    im = re.match(r'^-\s*\[([^\]]+)\]\s*剩余时效:\s*(\d+)回合\s*\((.*)\)\s*$', ln)
                    if im:
                        state['buffs'][cur_who].append({
                            'name': im.group(1).strip(),
                            'turns': int(im.group(2)),
                            'effect': im.group(3).strip(),
                        })

        # 5. Counters
        cm = re.search(r'^【回合计数器】[ \t]*\n(.*?)(?=^【|^▲|^={5,}|\Z)', pre, re.M | re.S)
        if cm:
            parsed_counts = {}
            for raw_ln in cm.group(1).splitlines():
                ln = raw_ln.strip()
                if not ln:
                    continue
                km = re.fullmatch(r'(\w{1,64}):[ \t]*(\d+)', ln)
                if km:
                    parsed_counts[km.group(1)] = int(km.group(2))
            if parsed_counts:
                merged = dict(state['counters'])
                merged.update(parsed_counts)
                if merged.get('空耗_连续未纾解') == 0:
                    merged.pop('空耗_连续未纾解', None)
                state['counters'] = merged

        # 6. Vigilance
        vm = re.search(r'(?m)(【监视状态】.*?)(?=\n【|\n▲ 第一层：|\Z)', pre, re.S)
        if vm:
            vblock = vm.group(1)
            pos_m = re.search(r'徐承邺位置：([^\n]+)', vblock)
            if pos_m:
                state['vigilance']['位置'] = pos_m.group(1).strip()
            for who in VIGILANCE_TARGETS:
                tm = re.search(rf'徐承邺_{re.escape(who)}：警惕\s*(\d+)\s*\|\s*发现\s*(\d+)\s*\|\s*发现几率\s*(\d+)', vblock)
                if tm:
                    state['vigilance']['目标'][who] = {
                        '警惕': int(tm.group(1)),
                        '发现': int(tm.group(2)),
                        '发现几率': int(tm.group(3)),
                    }

        # 7. Tasks
        tkm = re.search(r'(?m)(【任务状态】.*?)(?=\n【|\n▲ 第一层：|\Z)', pre, re.S)
        if tkm:
            tblock = tkm.group(1)
            state['tasks'] = {'current': None, 'history': [], 'pending_items': []}
            cur_m = re.search(
                r'当前任务：TASK-(\d+) \| ([^|]+) \| ([^|·]+)·([^|·]+)·(\d+) \| (\w+) \| ([^|]+) \| (\S+) \|发布回合(\d+)(?: \|完成回合(\d+))?',
                tblock,
            )
            if cur_m:
                state['tasks']['current'] = {
                    'id': f'TASK-{int(cur_m.group(1)):03d}',
                    'title': cur_m.group(2).strip(),
                    'target': cur_m.group(3).strip(),
                    'attr': cur_m.group(4).strip(),
                    'value': int(cur_m.group(5)),
                    'tier': cur_m.group(6).strip(),
                    'item_desc': cur_m.group(7).strip(),
                    'status': cur_m.group(8).strip(),
                    'issue_round': int(cur_m.group(9)),
                    'complete_round': int(cur_m.group(10)) if cur_m.group(10) else None,
                }
            hm = re.search(r'最近完成：\n((?: TASK-\d+ \| [^\n]+\n?)*)', tblock)
            if hm and hm.group(1).strip():
                state['tasks']['history'] = [ln.strip() for ln in hm.group(1).strip().splitlines() if ln.strip()][:3]
            pending_hits = re.findall(r'(?:待发道具：|\n )TASK-(\d+) \| ([^|\n]+) \|完成回合(\d+)', tblock)
            state['tasks']['pending_items'] = list(dict.fromkeys(
                f'TASK-{int(tid):03d} | {desc.strip()} |完成回合{int(rnd)}'
                for tid, desc, rnd in pending_hits
            ))

        # 8. Shop & echoes
        sm = re.search(r'(?m)(【商城与回响状态】.*?)(?=\n【|\n▲ 第一层：|\Z)', pre, re.S)
        if sm:
            sblock = sm.group(1)
            shop = {
                'redeemed': {},
                'recent': [],
                'echoes': [],
                'dynamic_catalog': copy.deepcopy(state['shop'].get('dynamic_catalog') or []),
                'next_dyn_seq': int(state['shop'].get('next_dyn_seq') or 1),
            }
            rm = re.search(r'^已兑统计：([^\n]+)', sblock, re.M)
            if rm and rm.group(1).strip() not in _EMPTY_MARKERS:
                for seg in rm.group(1).split('|'):
                    pm2 = re.fullmatch(r'\s*((?:SHOP|DYN)-\d+)[×x*](\d+)\s*', seg)
                    if pm2:
                        shop['redeemed'][pm2.group(1)] = int(pm2.group(2))
            recm = re.search(r'^最近兑换：\n((?: [^\n]+\n?)*)', sblock, re.M)
            if recm and recm.group(1).strip():
                shop['recent'] = [ln.strip() for ln in recm.group(1).splitlines() if ln.strip()][:8]
            em = re.search(r'^待播回响：\n((?: [^\n]+\n?)*)', sblock, re.M)
            if em and em.group(1).strip():
                for ln in em.group(1).splitlines():
                    raw_e = ln.strip()
                    parts = [p.strip() for p in raw_e.split('|', 2)]
                    if len(parts) == 3 and all(parts):
                        shop['echoes'].append({
                            'id': f'{parts[0]}:{parts[1]}',
                            'kind': parts[0],
                            'ref': parts[1],
                            'summary': parts[2],
                        })
            state['shop'] = shop

        # 9. Intel
        im_blk = re.search(r'(?m)(【商业情报与杠杆状态】.*?)(?=\n【|\n▲ 第一层：|\Z)', pre, re.S)
        if im_blk:
            ib = im_blk.group(1)
            intel = {'held': [], 'consumed': [], 'su_ab_contacts': 0, 'leverage_armed': ''}
            hm2 = re.search(r'^持有情报：([^\n]+)', ib, re.M)
            if hm2 and hm2.group(1).strip() not in _EMPTY_MARKERS:
                intel['held'] = list(dict.fromkeys(re.findall(r'INTEL-\d+', hm2.group(1))))
            cm2 = re.search(r'^已耗情报：([^\n]+)', ib, re.M)
            if cm2 and cm2.group(1).strip() not in _EMPTY_MARKERS:
                intel['consumed'] = list(dict.fromkeys(re.findall(r'INTEL-\d+', cm2.group(1))))
            sm2 = re.search(r'^苏婉青AB接触：\s*(\d+)', ib, re.M)
            if sm2:
                intel['su_ab_contacts'] = int(sm2.group(1))
            lm2 = re.search(r'^商业杠杆预备：([^\n]+)', ib, re.M)
            if lm2:
                aid = re.search(r'INTEL-\d+', lm2.group(1))
                if aid and aid.group(0) in intel['held']:
                    intel['leverage_armed'] = aid.group(0)
            state['intel'] = intel

        # 10. Director
        dm = re.search(r'(?m)^【世界导演状态】[ \t]*\n([^\n]+)', pre)
        if dm:
            try:
                raw_d = json.loads(dm.group(1).strip())
                if isinstance(raw_d, dict):
                    d_clean = default_director()
                    d_clean.update(raw_d)
                    state['director'] = d_clean
            except ValueError:
                pass

        # 11. Lifecycle
        lm_blk = re.search(r'(?m)^【回合生命周期】[ \t]*\n([^\n]+)', pre)
        if lm_blk:
            try:
                raw_l = json.loads(lm_blk.group(1).strip())
                if isinstance(raw_l, dict):
                    state['lifecycle'].update(raw_l)
            except ValueError:
                pass

        # 12. Four-layer memory
        had_prologue_marker = PROLOGUE_MARKER in mem
        positions = []
        for label, header in MEMORY_LAYER_HEADERS:
            idx = mem.find(header)
            if idx != -1:
                positions.append((label, header, idx))
        parsed_str_layers = {'L1': [], 'L2': [], 'L3': [], 'L4': []}
        for i, (label, header, start) in enumerate(positions):
            body_start = start + len(header)
            body_end = positions[i + 1][2] if i + 1 < len(positions) else len(mem)
            body = mem[body_start:body_end].strip()
            if body in _EMPTY_MARKERS:
                continue
            chunks = re.findall(r'(?m)^【\d+(?:-\d+)?】[\s\S]*?(?=^【\d+(?:-\d+)?】|\Z)', body)
            for ch in chunks:
                cleaned = strip_prologue_marker(ch)
                if cleaned and 'xxxxxxxxx' not in cleaned.casefold():
                    parsed_str_layers[label].append(cleaned)
        is_prologue_only = bool(
            had_prologue_marker
            and len(parsed_str_layers['L1']) == 1
            and not any(parsed_str_layers[k] for k in ('L2', 'L3', 'L4'))
            and parsed_str_layers['L1'][0].startswith('【1】')
        )
        layers = set_layer_strings(default_layers('', prologue_active=is_prologue_only), parsed_str_layers, prologue_active=is_prologue_only)

        # Sync item timers from 【道具倒计时】 into parsed items
        timer_map = {}
        tm_blk = re.search(r'(?m)【道具倒计时】(.*?)(?=\n【|\n▲ 第一层：|\Z)', pre, re.S)
        if tm_blk:
            for ln in tm_blk.group(1).splitlines():
                tm = re.match(r'^\s*(ITEM-\d+)：(\d+)回合', ln)
                if tm:
                    timer_map[tm.group(1)] = int(tm.group(2))
    else:
        timer_map = {}

    # Items
    if items_text:
        parsed_items = _parse_legacy_items(items_text)
        for it in parsed_items['active']:
            if it['id'] in timer_map:
                it['remaining_turns'] = timer_map[it['id']]
                it['remaining'] = f"{timer_map[it['id']]}回合"
        state['items'] = parsed_items

    # Runtime from data.json
    if isinstance(data_dict, dict):
        sr = data_dict.get('story_runtime')
        if isinstance(sr, dict):
            for k in ('clock', 'memory_round', 'last_closed', 'phase', 'item_recovered', 'action_index', 'closed_by'):
                if k in sr:
                    state['runtime'][k] = copy.deepcopy(sr[k])
        pro = data_dict.get('prologue')
        if isinstance(pro, dict):
            state['runtime']['prologue'] = copy.deepcopy(pro)
            if isinstance(pro.get('weekday'), str) and pro['weekday']:
                weekdays = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
                base_wd = pro['weekday']
                clk = state['runtime'].get('clock')
                day = int(clk['day']) if isinstance(clk, dict) and isinstance(clk.get('day'), int) else 1
                if base_wd in weekdays:
                    state['runtime']['weekday'] = weekdays[(weekdays.index(base_wd) + max(0, day - 1)) % 7]
                else:
                    state['runtime']['weekday'] = base_wd
        inter = data_dict.get('interaction')
        if isinstance(inter, dict):
            if type(inter.get('last_sequence')) is int:
                state['runtime']['last_sequence'] = max(state['runtime']['last_sequence'], inter['last_sequence'])
            if isinstance(inter.get('segment_id'), str) and inter['segment_id']:
                state['runtime']['last_segment_id'] = inter['segment_id']
        if type(data_dict.get('state_version')) is int:
            state['runtime']['last_sequence'] = max(state['runtime']['last_sequence'], data_dict['state_version'])

    return normalize_state(state), layers


def render_memory_txt(state, mem_layers):
    """Deterministically render 存档/全局记忆库.txt (read-only projection of JSON truth)."""
    state = normalize_state(state)
    panels = state['panels']
    host = panels['系统宿主']
    lines = [
        '===========================================',
        '               ⚠️ 板块三⚠️全局记忆库',
        '==========================================',
        '（只读视图：由 save_store 从 save_state.json + 四层记忆.json 单向自动渲染，机器真相以 JSON 为准）',
        '【实时面板快照】',
        '▶ 当前最新数值',
        f"[系统宿主] 积分 {host['积分']} | 经验值 {host['经验值']} | 体力 {host['体力']} | 魅力 {host['魅力']} | 商业嗅觉 {host['商业嗅觉']}",
    ]
    for name in ('沈知韫', '徐念薇', '苏婉青'):
        p = panels[name]
        lines.append(
            f"[{name}] 好感 {p['好感']} | 堕落 {p['堕落']} | 欲望 {p['欲望']} | 羞耻 {p['羞耻']} "
            f"| 体力 {p['体力']} | 高潮 {p['高潮']}% | 内射 {p['内射']}次 | 怀孕 {p['怀孕']} | 被动 Lv.{p['被动']}"
        )
    lines.append(f"[徐承邺] 堕落 {panels['徐承邺']['堕落']}")
    lines.append('')

    lines.append('【人物所在】')
    for name in PRESENCE_ORDER:
        info = state['presence'].get(name) or {'location': DEFAULT_PRESENCE[name][0], 'reason': DEFAULT_PRESENCE[name][1]}
        lines.append(f"{name}：{info['location']} | 事由：{info['reason']}")
    lines.append('')

    lines.append('【当前激活微状态】')
    for name in HEROINES:
        ms = state['micro_states'][name]
        row = ' | '.join(f"{k}: {str(bool(ms.get(k, False))).lower()}" for k in MICRO_STATES)
        lines.append(f'▶ {name}')
        lines.append(f'  {row}')
    lines.append('')
    lines.append('==================================================')

    lines.append('【当前持久化状态与BUFF】')
    for name in ('沈知韫', '苏婉青', '徐念薇'):
        lines.append(f'▶ {name}')
        blist = state['buffs'].get(name) or []
        if not blist:
            lines.append('  - 无')
        else:
            for b in blist:
                lines.append(f"  - [{b['name']}] 剩余时效: {b['turns']}回合 ({b['effect']})")
    lines.append('')
    lines.append('==================================================')

    lines.append('【回合计数器】')
    for k, v in state['counters'].items():
        lines.append(f'  {k}: {v}')
    lines.append('')

    vig = state['vigilance']
    lines.append('【监视状态】')
    lines.append(f"徐承邺位置：{vig['位置']}")
    for name in VIGILANCE_TARGETS:
        t = vig['目标'][name]
        lines.append(f"徐承邺_{name}：警惕 {t['警惕']} | 发现 {t['发现']} | 发现几率 {t['发现几率']}")
    lines.append('')

    tasks = state['tasks']
    lines.append('【任务状态】')
    cur = tasks.get('current')
    if cur:
        tline = (
            f"当前任务：{cur['id']} | {cur['title']} | {cur['target']}·{cur['attr']}·{cur['value']} "
            f"| {cur['tier']} | {cur['item_desc']} | {cur['status']} |发布回合{cur['issue_round']}"
        )
        if cur.get('complete_round'):
            tline += f" |完成回合{cur['complete_round']}"
        lines.append(tline)
    else:
        lines.append('当前任务：（无）')
    if tasks.get('history'):
        lines.append('最近完成：')
        for h in tasks['history']:
            lines.append(' ' + h)
    else:
        lines.append('最近完成：（空）')
    pending = tasks.get('pending_items') or []
    if not pending:
        lines.append('待发道具：（无）')
    elif len(pending) == 1:
        lines.append('待发道具：' + pending[0])
    else:
        lines.append('待发道具：')
        for pitem in pending:
            lines.append(' ' + pitem)
    lines.append('')

    lines.append('【道具倒计时】')
    timers = [
        it for it in state['items']['active']
        if it.get('remaining_turns') is not None
    ]
    if not timers:
        lines.append('（空）')
    else:
        for it in timers:
            lines.append(f"{it['id']}：{it['remaining_turns']}回合 | 名称：{it['name']} | 状态：进行中")
    lines.append('')

    shop = state['shop']
    lines.append('【商城与回响状态】')
    redeemed = shop.get('redeemed') or {}
    if redeemed:
        parts = [f'{k}×{int(v)}' for k, v in sorted(redeemed.items()) if int(v) > 0]
        lines.append('已兑统计：' + (' | '.join(parts) if parts else '（无）'))
    else:
        lines.append('已兑统计：（无）')
    if shop.get('recent'):
        lines.append('最近兑换：')
        for row in shop['recent']:
            lines.append(' ' + str(row).replace('\n', ' ').strip())
    else:
        lines.append('最近兑换：（无）')
    if shop.get('echoes'):
        lines.append('待播回响：')
        for e in shop['echoes']:
            lines.append(f" {e['kind']} | {e['ref']} | {e['summary']}")
    else:
        lines.append('待播回响：（无）')
    lines.append('')

    intel = state['intel']
    lines.append('【商业情报与杠杆状态】')
    lines.append('持有情报：' + (' | '.join(intel['held']) if intel['held'] else '（无）'))
    lines.append('已耗情报：' + (' | '.join(intel['consumed']) if intel['consumed'] else '（无）'))
    lines.append(f"苏婉青AB接触：{intel['su_ab_contacts']}")
    lines.append(f"商业杠杆预备：已预备({intel['leverage_armed']})" if intel['leverage_armed'] else '商业杠杆预备：未启用')
    lines.append('')

    intl = state.get('intimate') or default_intimate()
    has_intimate_notes = (
        intl.get('scene_active')
        or intl.get('privacy', 'open_public') != 'open_public'
        or bool(intl.get('sub_location'))
        or int(intl.get('noise_risk') or 0) > 0
        or any(
            (intl.get('attire', {}).get(h) or {}).get('state', 'neat') != 'neat'
            or (intl.get('attire', {}).get(h) or {}).get('outfit', 'default') != 'default'
            or bool((intl.get('attire', {}).get(h) or {}).get('gifted_items'))
            or bool(intl.get('traces', {}).get(h))
            for h in HEROINES
        )
        or any(int(v or 0) > 0 for v in (intl.get('inter_heroine') or {}).values())
    )
    if has_intimate_notes:
        lines.append('【情欲与空间态势】')
        priv_lbl = PRIVACY_LABELS.get(intl.get('privacy', 'open_public'), '公共开放')
        sub_loc = intl.get('sub_location') or '主区'
        mode_lbl = f"亲密进行中(第{intl.get('session_beats', 0)}拍)" if intl.get('scene_active') else '常规态'
        actors_lbl = '、'.join(intl.get('present_actors') or []) or '按地点常规在场'
        lines.append(f"场景：{sub_loc} | 隐私：{priv_lbl} | 状态：{mode_lbl} | 声响风险：{int(intl.get('noise_risk') or 0)} | 同室：{actors_lbl}")
        for h in HEROINES:
            att = (intl.get('attire') or {}).get(h) or {}
            trs = (intl.get('traces') or {}).get(h) or []
            bits = []
            if att.get('outfit', 'default') != 'default' or att.get('state', 'neat') != 'neat':
                bits.append(f"衣着={att.get('outfit', 'default')}({ATTIRE_LABELS.get(att.get('state', 'neat'), '整洁')})")
            if att.get('gifted_items'):
                bits.append('已获赠=' + '、'.join(att['gifted_items']))
            if trs:
                bits.append('痕迹=' + '、'.join(f"{t['kind']}({t['turns']}轮)" for t in trs))
            if bits:
                lines.append(f"  {h}：" + '；'.join(bits))
        ih_active = [f"{k}:{INTER_HEROINE_LABELS.get(int(v), str(v))}" for k, v in (intl.get('inter_heroine') or {}).items() if int(v or 0) > 0]
        if ih_active:
            lines.append('  女主暗流：' + ' | '.join(ih_active))
        lines.append('')

    lines.append('【世界导演状态】')
    lines.append(json.dumps(state['director'], ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    lines.append('')

    lines.append('【回合生命周期】')
    lines.append(json.dumps(state['lifecycle'], ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    lines.append('')

    str_layers = layer_strings(mem_layers)
    for key, header in MEMORY_LAYER_HEADERS:
        lines.append(header)
        entries = str_layers[key]
        if not entries:
            lines.append('（空）')
        else:
            lines.append('\n\n'.join(entries))
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def _format_item_record(it):
    it = normalize_item_dict(it)
    lines = [
        f"【道具名称】：{it['name']}",
        f"【道具ID】：{it['id']}",
        f"【类型】：{it['type']}",
    ]
    if it.get('category'):
        lines.append(f"【分类】：{it['category']}")
    lines.extend([
        f"【使用模式】：{it['usage_mode']}",
        f"【描述】：{it['desc']}",
        f"【数量】：{it['quantity']}",
        f"【获得回合】：{it['obtain_round']}",
        f"【当前状态】：{it['status']}",
        f"【位置】：{it['location']}",
    ])
    if it.get('spot') or it.get('status') == '已部署':
        lines.append(f"【安装点位】：{it.get('spot') or '隐蔽角落'}")
        lines.append(f"【隐蔽部署】：{'是' if it.get('hidden', True) else '否'}")
        if it.get('installed_clock'):
            lines.append(f"【部署时间】：{it['installed_clock']}")
        if int(it.get('detected_risk') or 0) > 0:
            lines.append(f"【暴露风险】：{int(it['detected_risk'])}")
    lines.extend([
        f"【使用对象】：{it['target']}",
        f"【时效】：{it['duration']}",
        f"【剩余时效】：{it['remaining']}",
        f"【过期规则】：{it['expire_rule']}",
        f"【使用记录】：{it['usage_record']}",
        f"【备注】：{it['remark']}",
        f"【系统效果】：{it['system_effect']}",
        f"【可赠予】：{'是' if it['giftable'] else '否'}",
    ])
    return '\n'.join(lines)


def render_items_txt(state):
    """Deterministically render 存档/徐志北道具图鉴.txt (active / deployed / delivered / history / template)."""
    state = normalize_state(state)
    items = state['items']

    def _section(arr, empty_label):
        if not arr:
            return empty_label
        return '\n\n'.join(_format_item_record(it) for it in arr)

    return (
        '===========================================\n'
        '          ⚠️ 板块五⚠️徐志北道具图鉴 V3.0\n'
        '===========================================\n\n'
        '【AI读取规则】\n'
        '1. 本文件由 save_store 从 存档/save_state.json 单向自动渲染，供人工与只读查阅；机器真相以 JSON 为准。\n'
        '2. 仅读取 ▼活跃道具区▼ 内的条目作为徐志北当前实际持有的有效道具。\n'
        '3. ▼已部署装置区▼ 记录已暗中安装于各场景的设备，可远程查看或回原址拆除回收。\n'
        '4. ▼已交付道具区▼ 记录已赠予/交付他人的道具，不计入徐志北当前库存，也不会被商城重购覆盖。\n'
        '5. 禁止把 ▼格式模板区▼ 和 ▼已过期/已消耗道具历史区▼ 里的内容当作可用道具。\n'
        '6. 临时道具剩余回合数由引擎统一维护在 save_state.json，归零自动移入历史区。\n\n'
        '==================================================\n'
        '▼ 活跃道具区 ▼（以下为当前实际持有的全部道具）\n'
        '==================================================\n\n'
        + _section(items['active'], '（新游戏初始仓库为空，兑换道具后由注入逻辑写入此区域）')
        + '\n\n==================================================\n'
        '▼ 已部署装置区 ▼（已暗中安装于各场景的设备记录，可远程查看或回原址拆除回收）\n'
        '==================================================\n\n'
        + _section(items.get('deployed', []), '（当前为空）')
        + '\n\n==================================================\n'
        '▼ 已交付道具区 ▼（已赠予或交付给其他角色的道具记录）\n'
        '==================================================\n\n'
        + _section(items['delivered'], '（当前为空）')
        + '\n\n==================================================\n'
        '▼ 已过期/已消耗道具历史区 ▼（仅供回溯，禁止当作可用道具）\n'
        '==================================================\n\n'
        + _section(items['history'], '（当前为空）')
        + '\n\n==================================================\n'
        '▼ 格式模板区 ▼（由 save_store 维护，只读说明）\n'
        '==================================================\n\n'
        '字段顺序：道具名称 / 道具ID / 类型 / 分类 / 使用模式 / 描述 / 数量 / 获得回合 / 当前状态 / 位置 / 安装点位 / 隐蔽部署 / 部署时间 / 暴露风险 / 使用对象 / 时效 / 剩余时效 / 过期规则 / 使用记录 / 备注 / 系统效果 / 可赠予。\n'
        '使用模式：gift / consumable_host / consumable_target / reusable_tool / deployable_device。\n'
        '系统效果：host_stamina:正整数 / buff:名称:回合:效果 / deploy_device:camera|audio|aroma。\n'
    )


def _runtime_sig(data_dict):
    if not isinstance(data_dict, dict):
        return ''
    subset = {
        'story_runtime': data_dict.get('story_runtime'),
        'prologue': data_dict.get('prologue'),
    }
    return _sha256_bytes(_json_bytes(subset))


def load_bundle(root, files=None):
    """Load (state, layers, recent) from files dict or disk, auto-migrating legacy saves or external .txt edits."""
    root = Path(root)

    def _read_bytes(rel):
        if files is not None and rel in files:
            return files[rel]
        p = root / rel
        return p.read_bytes() if p.is_file() else None

    raw_state = _read_bytes(SAVE_STATE_PATH)
    raw_layers = _read_bytes(MEMORY_LAYERS_PATH)
    raw_recent = _read_bytes(RECENT_PLAYBACK_PATH)
    raw_mem = _read_bytes(RENDERED_MEMORY_PATH)
    raw_items = _read_bytes(RENDERED_ITEMS_PATH)
    raw_data = _read_bytes('data.json')

    data_dict = None
    if raw_data:
        try:
            data_dict = json.loads(raw_data.decode('utf-8'))
        except ValueError:
            data_dict = None

    recent = default_recent()
    if raw_recent:
        try:
            parsed_recent = json.loads(raw_recent.decode('utf-8'))
            if isinstance(parsed_recent, dict):
                recent['playback'] = copy.deepcopy(parsed_recent.get('playback'))
                segs = parsed_recent.get('segments')
                if isinstance(segs, list):
                    recent['segments'] = [copy.deepcopy(s) for s in segs if isinstance(s, dict)][-MAX_RECENT_SEGMENTS:]
        except ValueError:
            pass

    if raw_state and raw_layers:
        try:
            state = normalize_state(json.loads(raw_state.decode('utf-8')))
            layers_raw = json.loads(raw_layers.decode('utf-8'))
            if isinstance(layers_raw, dict) and isinstance(layers_raw.get('layers'), dict):
                layers = layers_raw
            else:
                layers = default_layers('', prologue_active=False)

            # Detect external direct edits to rendered .txt or data.json story_runtime (e.g. legacy tools / tests).
            sha = state.get('rendered_sha256') or {}
            mem_drifted = bool(raw_mem and sha.get('memory_txt') and _sha256_bytes(raw_mem) != sha['memory_txt'])
            items_drifted = bool(raw_items and sha.get('items_txt') and _sha256_bytes(raw_items) != sha['items_txt'])
            rt_sig = _runtime_sig(data_dict)
            data_rt_drifted = bool(data_dict and sha.get('data_runtime') and rt_sig != sha['data_runtime'])

            if mem_drifted or items_drifted:
                migrated_state, migrated_layers = migrate_from_legacy_texts(
                    raw_mem.decode('utf-8') if (mem_drifted and raw_mem) else '',
                    raw_items.decode('utf-8') if (items_drifted and raw_items) else '',
                    data_dict if data_rt_drifted else None,
                    base_state=state,
                )
                if mem_drifted:
                    # Preserve JSON-only mechanics/runtime/dynamic_catalog and layer metadata (prologue_active / known_by) across .txt syncs.
                    migrated_state['mechanics'] = copy.deepcopy(state['mechanics'])
                    migrated_state['shop']['dynamic_catalog'] = copy.deepcopy(state['shop'].get('dynamic_catalog') or [])
                    migrated_state['shop']['next_dyn_seq'] = int(state['shop'].get('next_dyn_seq') or 1)
                    if not data_rt_drifted:
                        migrated_state['runtime'] = copy.deepcopy(state['runtime'])
                    if not items_drifted:
                        migrated_state['items'] = copy.deepcopy(state['items'])
                    old_known = {}
                    for lk, litems in (layers.get('layers') or {}).items():
                        for entry in (litems or []):
                            if isinstance(entry, dict) and entry.get('known_by') is not None:
                                old_known[(lk, entry.get('label', ''), entry.get('text', ''))] = copy.deepcopy(entry['known_by'])
                    for lk, litems in (migrated_layers.get('layers') or {}).items():
                        for entry in (litems or []):
                            if isinstance(entry, dict) and entry.get('known_by') is None:
                                saved_kb = old_known.get((lk, entry.get('label', ''), entry.get('text', '')))
                                if saved_kb is not None:
                                    entry['known_by'] = saved_kb
                    if layers.get('prologue_active') and not migrated_layers.get('prologue_active'):
                        l1 = (migrated_layers.get('layers') or {}).get('L1') or []
                        if len(l1) == 1 and l1[0].get('start_round') == 1 and l1[0].get('end_round') == 1:
                            migrated_layers['prologue_active'] = True
                    state = normalize_state(migrated_state)
                    layers = migrated_layers
                elif items_drifted:
                    state['items'] = migrated_state['items']
            if data_rt_drifted and isinstance(data_dict, dict):
                sr = data_dict.get('story_runtime')
                if isinstance(sr, dict):
                    for k in ('clock', 'memory_round', 'last_closed', 'phase', 'item_recovered', 'action_index', 'closed_by'):
                        if k in sr:
                            state['runtime'][k] = copy.deepcopy(sr[k])
                pro = data_dict.get('prologue')
                if isinstance(pro, dict):
                    state['runtime']['prologue'] = copy.deepcopy(pro)
                    base_wd = pro.get('weekday')
                    weekdays = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
                    if isinstance(base_wd, str) and base_wd in weekdays:
                        clk = state['runtime'].get('clock')
                        day = clk.get('day', 1) if isinstance(clk, dict) and isinstance(clk.get('day'), int) else 1
                        state['runtime']['weekday'] = weekdays[(weekdays.index(base_wd) + max(0, day - 1)) % 7]
            return state, layers, recent
        except ValueError:
            pass

    # Fallback: migrate legacy .txt + data.json save cleanly
    state, layers = migrate_from_legacy_texts(
        raw_mem.decode('utf-8') if raw_mem else '',
        raw_items.decode('utf-8') if raw_items else '',
        data_dict,
    )
    return state, layers, recent


def render_bundle_bytes(state, layers, recent=None, *, data_dict=None):
    """Build byte payloads for all 5 存档/ files so RoundStore can commit them atomically."""
    state = normalize_state(state)
    mem_txt = render_memory_txt(state, layers).encode('utf-8')
    items_txt = render_items_txt(state).encode('utf-8')
    state['rendered_sha256'] = {
        'memory_txt': _sha256_bytes(mem_txt),
        'items_txt': _sha256_bytes(items_txt),
        'data_runtime': _runtime_sig(data_dict) if data_dict is not None else state['rendered_sha256'].get('data_runtime', ''),
    }
    out = {
        RENDERED_MEMORY_PATH: mem_txt,
        RENDERED_ITEMS_PATH: items_txt,
        SAVE_STATE_PATH: _json_bytes(state),
        MEMORY_LAYERS_PATH: _json_bytes(layers),
    }
    if recent is not None:
        clean_recent = {
            'version': 1,
            'playback': copy.deepcopy(recent.get('playback')),
            'segments': [copy.deepcopy(s) for s in (recent.get('segments') or []) if isinstance(s, dict)][-MAX_RECENT_SEGMENTS:],
        }
        out[RECENT_PLAYBACK_PATH] = _json_bytes(clean_recent)
    return out


def save_bundle(stage_root, state, layers, recent=None, *, data_dict=None):
    """Write structured JSON state + layers + one-way rendered .txt views atomically into stage_root."""
    stage_root = Path(stage_root)
    payloads = render_bundle_bytes(state, layers, recent, data_dict=data_dict)
    for rel, raw in payloads.items():
        _atomic_write(stage_root / rel, raw)
    return payloads


def append_recent_segment(recent, segment_row, playback_state=None):
    out = copy.deepcopy(recent) if isinstance(recent, dict) else default_recent()
    segs = [s for s in (out.get('segments') or []) if isinstance(s, dict) and s.get('id') != segment_row.get('id')]
    # Keep full segment payload needed for history, known_by, decision, playback & settlement recovery; strip heavy/unused blobs.
    compact = {k: copy.deepcopy(v) for k, v in segment_row.items() if k not in ('audit', 'before_world', 'after_location', 'resolution')}
    segs.append(compact)
    segs.sort(key=lambda s: int(s.get('sequence', 0)))
    out['segments'] = segs[-MAX_RECENT_SEGMENTS:]
    if playback_state is not None:
        out['playback'] = copy.deepcopy(playback_state)
    return out


def update_recent_playback(recent, playback_state):
    out = copy.deepcopy(recent) if isinstance(recent, dict) else default_recent()
    out['playback'] = copy.deepcopy(playback_state)
    return out

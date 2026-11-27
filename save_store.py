"""Unified P3 save storage: pure JSON single-source-of-truth + deterministic one-way .txt views.

Authoritative files inside 存档/:
  - 存档/save_state.json   : all structured machine state (panels, presence, micro, buffs,
                             counters, mechanics, intimate, vigilance, tasks, items, shop,
                             intel, director, npc_mind, lifecycle, runtime).
  - 存档/memory_store.json : v2 three-track structured memory store (permanent anchors,
                             scene-scoped rolling episodes with authoritative known_by,
                             bounded epoch chronicle, and pending turn buffer).
  - 存档/近期演播.json      : rolling latest N accepted interaction segments + playback state.

One-way rendered read-only views (kept synchronized on every commit for human inspection
and manual Operit chats; never reverse-parsed during formal live_interaction):
  - 存档/全局记忆库.txt
  - 存档/徐志北道具图鉴.txt
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

SAVE_STATE_PATH = '存档/save_state.json'
MEMORY_STORE_PATH = '存档/memory_store.json'
MEMORY_LAYERS_PATH = MEMORY_STORE_PATH
LEGACY_MEMORY_LAYERS_PATH = '存档/四层记忆.json'
RECENT_PLAYBACK_PATH = '存档/近期演播.json'
RENDERED_MEMORY_PATH = '存档/全局记忆库.txt'
RENDERED_ITEMS_PATH = '存档/徐志北道具图鉴.txt'

MAX_RECENT_SEGMENTS = 16
MAX_DELIVERED_ITEMS = 40
MAX_HISTORY_ITEMS = 50
MAX_ACTIVE_ANCHORS = 60
MAX_RESOLVED_ANCHORS = 40
MAX_HOT_EPISODES = 24
ARCHIVE_BATCH_EPISODES = 8
HARD_MAX_EPISODES = 32
MAX_CHRONICLE_CHAPTERS = 16
PENDING_FLUSH_MAX_FACTS = 4
PENDING_FLUSH_MAX_CHARS = 360
ANCHOR_KINDS = ('promise', 'milestone', 'secret', 'clue', 'relationship')
PROLOGUE_MARKER = '【系统隐藏标记：以上为新游戏序幕锚点，剧情从此刻正式开始计算】'
_K01_SECRET_RE = re.compile(r'遗嘱|唯一合法继承人|唯一继承人|千亿家产(?:唯一|全归|归志北)|徐家继承权全归')

HEROINES = ('沈知韫', '苏婉青', '徐念薇')
PRESENCE_ORDER = ('沈知韫', '徐念薇', '苏婉青', '徐志北')
PANEL_ORDER = ('系统宿主', '沈知韫', '徐念薇', '苏婉青')
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
_ENTITY_ALIAS_MAP = {
    '沈知韫': ('沈知韫', '知韫', '母亲', '妈妈', '妈', '夫人', '董事长', '沈总', '婆婆'),
    '徐念薇': ('徐念薇', '念薇', '二姐', '姐姐', '姐', '画室', '画展', '美院'),
    '苏婉青': ('苏婉青', '婉青', '嫂子', '大嫂', '少奶奶', '公寓'),
    '徐承邺': ('徐承邺', '承邺', '大哥', '哥哥', '长兄', '外地', '查岗', '监视'),
    '徐志北': ('徐志北', '志北', '小叔', '小少爷'),
}


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
        'heroine_cd': 0,
        'last_time_slot': '',
        'event_cooldowns': {},
        'consumed_once': [],
        'pending_seeds': [],
        'active_threads': [],
        'next_thread_seq': 1,
        'offstage_clocks': {},
        'recent_channels': [],
    }


NPC_MIND_TARGETS = ('沈知韫', '苏婉青', '徐念薇', '徐承邺')


def default_npc_mind():
    return {
        '沈知韫': {
            'mood': '',
            'mood_ttl': 0,
            'preoccupation': '留意深圳分部近期对账风波，顺便掂量志北近来有没有进公司看看的心思',
            'impressions': [],
            'aff_delta_last': 0,
        },
        '苏婉青': {
            'mood': '',
            'mood_ttl': 0,
            'preoccupation': '留意主宅近况好应付丈夫晚间来电，同时在婆婆面前拿捏周全分寸',
            'impressions': [],
            'aff_delta_last': 0,
        },
        '徐念薇': {
            'mood': '',
            'mood_ttl': 0,
            'preoccupation': '青年画展二稿配色一直卡着，不想被家里催着掺和徐家事务',
            'impressions': [],
            'aff_delta_last': 0,
        },
        '徐承邺': {
            'mood': '',
            'mood_ttl': 0,
            'preoccupation': '外地并购谈判拉锯中，急着在母亲面前做出亮眼实绩',
            'impressions': [],
            'aff_delta_last': 0,
        },
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
BODY_ZONES = ('oral', 'hand', 'chest', 'foot', 'core')
BODY_ZONE_LABELS = {
    'oral': '口舌',
    'hand': '纤手',
    'chest': '胸乳',
    'foot': '玉足',
    'core': '深处',
}
HEROINE_SIGNATURE_ZONES = {
    '沈知韫': 'foot',
    '苏婉青': 'chest',
    '徐念薇': 'hand',
}
KEEPSAKE_KINDS = ('panties', 'stockings', 'bra', 'nightwear', 'accessory')
KEEPSAKE_KIND_LABELS = {
    'panties': '贴身内裤',
    'stockings': '丝袜长袜',
    'bra': '贴身内衣',
    'nightwear': '睡裙家居',
    'accessory': '私密贴物',
}
KEEPSAKE_METHODS = ('stolen', 'taken_intimate', 'gifted')
KEEPSAKE_METHOD_LABELS = {
    'stolen': '暗中偷藏',
    'taken_intimate': '亲密留存',
    'gifted': '亲手交出',
}
KEEPSAKE_CONDITIONS = ('fresh_warm', 'stained_damp', 'faded')
KEEPSAKE_CONDITION_LABELS = {
    'fresh_warm': '尚带体温余香',
    'stained_damp': '沾有微潮水痕',
    'faded': '余香渐淡',
}
KEEPSAKE_ACTIONS = ('sniff_play', 'confront', 'use_intimate', 'return_secret')
KEEPSAKE_ACTION_LABELS = {
    'sniff_play': '私下嗅闻把玩',
    'confront': '当面出示试探',
    'use_intimate': '亲密穿戴复用',
    'return_secret': '悄悄放回原处',
}


def default_host_phys():
    return {
        'desire': 0,
        'vigor': 100,
        'release_count': 0,
        'edging_streak': 0,
        'fetishes': [],
    }


def default_body_dev():
    return {
        name: {z: 0 for z in BODY_ZONES}
        for name in HEROINES
    }


def normalize_keepsake_dict(raw, fallback_id='KS-001'):
    if not isinstance(raw, dict):
        return None
    owner = str(raw.get('owner') or '').strip()
    name = str(raw.get('name') or '').strip()[:32]
    if owner not in HEROINES or not name:
        return None
    ks_id = str(raw.get('id') or '').strip()
    if not re.fullmatch(r'KS-\d+', ks_id):
        ks_id = fallback_id
    kind = str(raw.get('kind') or 'panties').strip()
    if kind not in KEEPSAKE_KINDS:
        if re.search(r'丝袜|黑丝|肉丝|过膝袜|长袜|袜', name):
            kind = 'stockings'
        elif re.search(r'文胸|胸罩|内衣|抹胸', name):
            kind = 'bra'
        elif re.search(r'睡裙|睡衣|吊带', name):
            kind = 'nightwear'
        elif re.search(r'内裤|底裤|胖次|蕾丝裤', name):
            kind = 'panties'
        else:
            kind = 'accessory'
    method = str(raw.get('method') or 'stolen').strip()
    if method == 'kept_after':
        method = 'taken_intimate'
    if method not in KEEPSAKE_METHODS:
        method = 'stolen'
    cond = str(raw.get('condition') or 'fresh_warm').strip()
    if cond not in KEEPSAKE_CONDITIONS:
        cond = 'fresh_warm'
    return {
        'id': ks_id,
        'owner': owner,
        'name': name,
        'kind': kind,
        'method': method,
        'condition': cond,
        'location': str(raw.get('location') or '').strip()[:24],
        'clock': str(raw.get('clock') or '').strip()[:24],
        'owner_aware': bool(raw.get('owner_aware', method == 'gifted')),
        'desc': str(raw.get('desc') or '').strip()[:80],
        'interactions': max(0, _parse_int(raw.get('interactions'), 0)),
    }


def default_intimate():
    return {
        'scene_active': False,
        'session_beats': 0,
        'session_orgasms': {name: 0 for name in HEROINES},
        'session_charm_gained': False,
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
        'host_phys': default_host_phys(),
        'body_dev': default_body_dev(),
        'keepsakes': [],
        'next_keepsake_seq': 1,
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
            '沈知韫': {'好感': 82, '堕落': 0, '欲望': 0, '羞耻': 100, '体力': 100, '高潮': 0, '内射': 0, '怀孕': False, '被动': 0},
            '徐念薇': {'好感': 30, '堕落': 0, '欲望': 0, '羞耻': 96, '体力': 100, '高潮': 0, '内射': 0, '怀孕': False, '被动': 0},
            '苏婉青': {'好感': 40, '堕落': 0, '欲望': 0, '羞耻': 92, '体力': 100, '高潮': 0, '内射': 0, '怀孕': False, '被动': 0},
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
                name: {'警惕': 0, '发现': 0, '发现几率': 0, '动因': ''}
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
            'leverage_charges': 0,
        },
        'director': default_director(),
        'npc_mind': default_npc_mind(),
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


_VALID_MEMORY_ACTORS = frozenset({'徐志北', '沈知韫', '苏婉青', '徐念薇', '徐承邺'})
_STOP_BIGRAMS = frozenset({'继续', '今天', '怎么', '一下', '这里', '当前', '剧情', '自己', '安排', '然后', '那个', '这个', '什么', '没有', '已经', '一个', '一些', '刚刚', '此刻'})


def _clean_mem_line(text, limit=400):
    s = re.sub(r'[\r\n\x00]+', ' ', str(text or '')).strip()
    s = re.sub(r'\s{2,}', ' ', s)
    return s[:limit]


def _clean_known_by(raw, *, default_actors=None):
    if isinstance(raw, (list, tuple, set)):
        cleaned = list(dict.fromkeys(
            str(x).strip() for x in raw if isinstance(x, str) and str(x).strip() in _VALID_MEMORY_ACTORS
        ))
        if cleaned:
            if '徐志北' not in cleaned:
                cleaned.insert(0, '徐志北')
            return cleaned
    if isinstance(default_actors, (list, tuple, set)):
        cleaned = list(dict.fromkeys(
            str(x).strip() for x in default_actors if isinstance(x, str) and str(x).strip() in _VALID_MEMORY_ACTORS
        ))
        if cleaned:
            if '徐志北' not in cleaned:
                cleaned.insert(0, '徐志北')
            return cleaned
    return ['徐志北']


def _extract_entities_from_text(text, extra=()):
    found = []
    seen = set()
    for item in (extra or ()):
        name = str(item or '').strip()
        if name in _VALID_MEMORY_ACTORS and name not in seen:
            seen.add(name)
            found.append(name)
    blob = str(text or '')
    for canonical, aliases in _ENTITY_ALIAS_MAP.items():
        if canonical in seen:
            continue
        if any(alias in blob for alias in aliases):
            seen.add(canonical)
            found.append(canonical)
    return found


def _extract_tokens(text):
    chunks = re.findall(r'[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}', str(text or ''))
    tokens = set()
    for ch in chunks:
        if ch.isascii():
            tokens.add(ch.lower())
        else:
            for i in range(len(ch) - 1):
                bg = ch[i:i + 2]
                if bg not in _STOP_BIGRAMS:
                    tokens.add(bg)
    return tokens


def _text_similar(a, b):
    ta = _extract_tokens(a)
    tb = _extract_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter / max(1, min(len(ta), len(tb))) >= 0.65


def _guard_k01_known_by(text, known_by, secrets_unlocked=()):
    if 'K01' in set(secrets_unlocked or ()):
        return list(known_by)
    if _K01_SECRET_RE.search(str(text or '')):
        return [w for w in known_by if w in ('沈知韫',)] or ['沈知韫']
    return list(known_by)


def _default_pending_buffer():
    return {
        'day': 1,
        'location': '',
        'sub_location': '',
        'start_time': '',
        'last_time': '',
        'known_by': [],
        'entities': [],
        'tags': [],
        'turns': 0,
        'facts': [],
    }


def default_memory_store(prologue_text='周二上午，徐家主宅。新的一天刚刚开始。', *,
                         prologue_active=True, known_by=None, location='徐家主宅',
                         sub_location='', day=1, time_str='12:00'):
    clean = strip_prologue_marker(prologue_text)
    clean = _LABEL_RE.sub('', clean).strip()
    kb = _clean_known_by(known_by, default_actors=['徐志北'])
    episodes = []
    next_ep_seq = 1
    if clean:
        episodes.append({
            'id': 'EP-001',
            'day': max(1, _parse_int(day, 1)),
            'time_range': str(time_str or '12:00').strip()[:16],
            'location': str(location or '徐家主宅').strip()[:32],
            'sub_location': str(sub_location or '').strip()[:32],
            'entities': _extract_entities_from_text(clean, kb),
            'known_by': kb,
            'tags': ['开局序幕'] if prologue_active else [],
            'summary': _clean_mem_line(clean, 480),
            'is_prologue': bool(prologue_active),
        })
        next_ep_seq = 2
    return {
        'version': 2,
        'prologue_active': bool(prologue_active and bool(clean)),
        'next_anchor_seq': 1,
        'next_episode_seq': next_ep_seq,
        'next_chronicle_seq': 1,
        'anchors': [],
        'resolved_anchors': [],
        'episodes': episodes,
        'chronicle': [],
        'pending_buffer': _default_pending_buffer(),
    }


def default_layers(prologue_text='周二上午，徐家主宅。新的一天刚刚开始。', *,
                   prologue_active=True, known_by=None, location='徐家主宅',
                   sub_location='', day=1, time_str='12:00'):
    """Compatibility wrapper returning the v2 three-track memory store."""
    return default_memory_store(
        prologue_text,
        prologue_active=prologue_active,
        known_by=known_by,
        location=location,
        sub_location=sub_location,
        day=day,
        time_str=time_str,
    )


def _upgrade_v1_layers_to_v2(raw):
    """Upgrade legacy v1 {'version': 1, 'layers': {L1..L4}} dict into v2 memory_store."""
    store = default_memory_store('', prologue_active=False)
    layers = raw.get('layers') if isinstance(raw.get('layers'), dict) else {}
    pro_active = bool(raw.get('prologue_active', False))
    ep_seq = 1
    ch_seq = 1
    for item in (layers.get('L4') or []):
        if not isinstance(item, dict):
            continue
        txt = _clean_mem_line(item.get('text') or '', 420)
        if not txt:
            continue
        sr = max(1, _parse_int(item.get('start_round'), 1))
        er = max(sr, _parse_int(item.get('end_round'), sr))
        store['chronicle'].append({
            'id': f'CH-{ch_seq:02d}',
            'day_range': [sr, er],
            'episode_range': [f'R{sr}', f'R{er}'],
            'entities': _extract_entities_from_text(txt),
            'public': txt[:260],
            'views': {},
        })
        ch_seq += 1
    for item in (layers.get('L3') or []):
        if not isinstance(item, dict):
            continue
        txt = _clean_mem_line(item.get('text') or '', 360)
        if not txt:
            continue
        sr = max(1, _parse_int(item.get('start_round'), 1))
        er = max(sr, _parse_int(item.get('end_round'), sr))
        store['chronicle'].append({
            'id': f'CH-{ch_seq:02d}',
            'day_range': [sr, er],
            'episode_range': [f'R{sr}', f'R{er}'],
            'entities': _extract_entities_from_text(txt),
            'public': txt[:260],
            'views': {},
        })
        ch_seq += 1
    for lkey in ('L2', 'L1'):
        for item in (layers.get(lkey) or []):
            if not isinstance(item, dict):
                continue
            txt = _clean_mem_line(strip_prologue_marker(item.get('text') or ''), 480)
            if not txt:
                continue
            sr = max(1, _parse_int(item.get('start_round'), 1))
            kb = _clean_known_by(item.get('known_by'), default_actors=['徐志北'])
            is_pro = bool(pro_active and lkey == 'L1' and sr == 1 and len(layers.get('L1') or []) == 1 and not layers.get('L2'))
            store['episodes'].append({
                'id': f'EP-{ep_seq:03d}',
                'day': sr,
                'time_range': '',
                'location': '',
                'sub_location': '',
                'entities': _extract_entities_from_text(txt, kb),
                'known_by': kb,
                'tags': ['开局序幕'] if is_pro else [],
                'summary': txt,
                'is_prologue': is_pro,
            })
            ep_seq += 1
    store['chronicle'] = store['chronicle'][-MAX_CHRONICLE_CHAPTERS:]
    store['episodes'] = store['episodes'][-HARD_MAX_EPISODES:]
    store['next_episode_seq'] = max(1, ep_seq)
    store['next_chronicle_seq'] = max(1, ch_seq)
    store['prologue_active'] = bool(pro_active and any(ep.get('is_prologue') for ep in store['episodes']))
    return store


def normalize_memory_store(raw):
    if not isinstance(raw, dict):
        return default_memory_store('', prologue_active=False)
    if 'layers' in raw and raw.get('version', 1) != 2 and 'episodes' not in raw:
        raw = _upgrade_v1_layers_to_v2(raw)

    out = default_memory_store('', prologue_active=False)
    out['prologue_active'] = bool(raw.get('prologue_active', False))

    max_a = 0
    seen_a = set()
    for bucket, dst_key, cap in (('anchors', 'anchors', MAX_ACTIVE_ANCHORS), ('resolved_anchors', 'resolved_anchors', MAX_RESOLVED_ANCHORS)):
        cleaned = []
        for item in (raw.get(bucket) or []):
            if not isinstance(item, dict):
                continue
            txt = _clean_mem_line(item.get('text') or '', 120)
            if not txt:
                continue
            aid = str(item.get('id') or '').strip()
            m = re.fullmatch(r'A-(\d+)', aid)
            if not m or aid in seen_a:
                max_a += 1
                aid = f'A-{max_a:03d}'
            else:
                max_a = max(max_a, int(m.group(1)))
            seen_a.add(aid)
            kind = str(item.get('kind') or 'milestone').strip()
            if kind not in ANCHOR_KINDS:
                kind = 'milestone'
            kb = _clean_known_by(item.get('known_by'), default_actors=['徐志北'])
            rec = {
                'id': aid,
                'kind': kind,
                'day': max(1, _parse_int(item.get('day'), 1)),
                'entities': _extract_entities_from_text(txt, item.get('entities') or kb),
                'known_by': kb,
                'status': 'resolved' if dst_key == 'resolved_anchors' else 'active',
                'importance': max(1, min(5, _parse_int(item.get('importance'), 3))),
                'text': txt,
            }
            if item.get('note'):
                rec['note'] = _clean_mem_line(item.get('note'), 60)
            cleaned.append(rec)
        out[dst_key] = cleaned[-cap:]
    out['next_anchor_seq'] = max(_parse_int(raw.get('next_anchor_seq'), 1), max_a + 1)

    max_ep = 0
    seen_ep = set()
    clean_eps = []
    for item in (raw.get('episodes') or []):
        if not isinstance(item, dict):
            continue
        summary = _clean_mem_line(strip_prologue_marker(item.get('summary') or ''), 480)
        if not summary:
            continue
        eid = str(item.get('id') or '').strip()
        m = re.fullmatch(r'EP-(\d+)', eid)
        if not m or eid in seen_ep:
            max_ep += 1
            eid = f'EP-{max_ep:03d}'
        else:
            max_ep = max(max_ep, int(m.group(1)))
        seen_ep.add(eid)
        kb = _clean_known_by(item.get('known_by'), default_actors=['徐志北'])
        raw_tags = item.get('tags') if isinstance(item.get('tags'), list) else []
        clean_tags = list(dict.fromkeys(_clean_mem_line(t, 16) for t in raw_tags if _clean_mem_line(t, 16)))[:6]
        clean_eps.append({
            'id': eid,
            'day': max(1, _parse_int(item.get('day'), 1)),
            'time_range': _clean_mem_line(item.get('time_range') or '', 20),
            'location': _clean_mem_line(item.get('location') or '', 32),
            'sub_location': _clean_mem_line(item.get('sub_location') or '', 32),
            'entities': _extract_entities_from_text(summary, item.get('entities') or kb),
            'known_by': kb,
            'tags': clean_tags,
            'summary': summary,
            'is_prologue': bool(item.get('is_prologue', False)),
        })
    out['episodes'] = clean_eps[-HARD_MAX_EPISODES:]
    out['next_episode_seq'] = max(_parse_int(raw.get('next_episode_seq'), 1), max_ep + 1)

    max_ch = 0
    seen_ch = set()
    clean_ch = []
    for item in (raw.get('chronicle') or []):
        if not isinstance(item, dict):
            continue
        pub = _clean_mem_line(item.get('public') or '', 300)
        raw_views = item.get('views') if isinstance(item.get('views'), dict) else {}
        views = {}
        for wk, wv in raw_views.items():
            wname = str(wk or '').strip()
            wtxt = _clean_mem_line(wv, 160)
            if wname in _VALID_MEMORY_ACTORS and wtxt:
                views[wname] = wtxt
        if not pub and not views:
            continue
        cid = str(item.get('id') or '').strip()
        m = re.fullmatch(r'CH-(\d+)', cid)
        if not m or cid in seen_ch:
            max_ch += 1
            cid = f'CH-{max_ch:02d}'
        else:
            max_ch = max(max_ch, int(m.group(1)))
        seen_ch.add(cid)
        dr = item.get('day_range')
        if isinstance(dr, list) and len(dr) == 2:
            d0 = max(1, _parse_int(dr[0], 1))
            d1 = max(d0, _parse_int(dr[1], d0))
        else:
            d0, d1 = 1, 1
        er = item.get('episode_range')
        ep_rng = [str(er[0])[:16], str(er[1])[:16]] if isinstance(er, list) and len(er) == 2 else ['', '']
        clean_ch.append({
            'id': cid,
            'day_range': [d0, d1],
            'episode_range': ep_rng,
            'entities': _extract_entities_from_text(pub + ' ' + ' '.join(views.values()), item.get('entities') or ()),
            'public': pub,
            'views': views,
        })
    out['chronicle'] = clean_ch[-MAX_CHRONICLE_CHAPTERS:]
    out['next_chronicle_seq'] = max(_parse_int(raw.get('next_chronicle_seq'), 1), max_ch + 1)

    pb = raw.get('pending_buffer') if isinstance(raw.get('pending_buffer'), dict) else {}
    clean_facts = [_clean_mem_line(f, 180) for f in (pb.get('facts') or []) if _clean_mem_line(f, 180)]
    if clean_facts:
        pb_kb = _clean_known_by(pb.get('known_by'), default_actors=['徐志北'])
        out['pending_buffer'] = {
            'day': max(1, _parse_int(pb.get('day'), 1)),
            'location': _clean_mem_line(pb.get('location') or '', 32),
            'sub_location': _clean_mem_line(pb.get('sub_location') or '', 32),
            'start_time': _clean_mem_line(pb.get('start_time') or '', 12),
            'last_time': _clean_mem_line(pb.get('last_time') or '', 12),
            'known_by': pb_kb,
            'entities': _extract_entities_from_text(' '.join(clean_facts), pb.get('entities') or pb_kb),
            'tags': list(dict.fromkeys(_clean_mem_line(t, 16) for t in (pb.get('tags') or []) if _clean_mem_line(t, 16)))[:6],
            'turns': max(len(clean_facts), _parse_int(pb.get('turns'), len(clean_facts))),
            'facts': clean_facts[-PENDING_FLUSH_MAX_FACTS:],
        }
    return out


def needs_chronicle_archive(mem_store):
    ms = normalize_memory_store(mem_store)
    non_prologue = [ep for ep in ms['episodes'] if not ep.get('is_prologue')]
    return len(non_prologue) >= MAX_HOT_EPISODES


def chronicle_archive_batch(mem_store):
    ms = normalize_memory_store(mem_store)
    non_prologue = [ep for ep in ms['episodes'] if not ep.get('is_prologue')]
    if len(non_prologue) < MAX_HOT_EPISODES:
        return []
    return copy.deepcopy(non_prologue[:ARCHIVE_BATCH_EPISODES])


def _seal_pending_buffer(ms, secrets_unlocked=()):
    pb = ms.get('pending_buffer') or _default_pending_buffer()
    facts = [f for f in (pb.get('facts') or []) if f]
    if not facts:
        ms['pending_buffer'] = _default_pending_buffer()
        return None
    summary = '；'.join(facts)[:460]
    t0 = pb.get('start_time') or ''
    t1 = pb.get('last_time') or ''
    trange = t0 if (not t1 or t0 == t1) else f'{t0}-{t1}'
    kb = _guard_k01_known_by(summary, _clean_known_by(pb.get('known_by')), secrets_unlocked)
    ep_id = f"EP-{ms['next_episode_seq']:03d}"
    ms['next_episode_seq'] += 1
    ep = {
        'id': ep_id,
        'day': max(1, _parse_int(pb.get('day'), 1)),
        'time_range': trange,
        'location': pb.get('location') or '',
        'sub_location': pb.get('sub_location') or '',
        'entities': _extract_entities_from_text(summary, list(pb.get('entities') or ()) + kb),
        'known_by': kb,
        'tags': list(pb.get('tags') or ())[:6],
        'summary': summary,
        'is_prologue': False,
    }
    ms['episodes'].append(ep)
    ms['pending_buffer'] = _default_pending_buffer()
    return ep


def _append_chronicle_chapter(ms, batch, *, public_text='', views=None, secrets_unlocked=()):
    if not batch:
        return None
    days = [max(1, _parse_int(ep.get('day'), 1)) for ep in batch]
    d0, d1 = min(days), max(days)
    ep_rng = [batch[0]['id'], batch[-1]['id']]
    all_ents = []
    for ep in batch:
        for e in (ep.get('entities') or ()):
            if e not in all_ents:
                all_ents.append(e)
    pub = _clean_mem_line(public_text, 280)
    if 'K01' not in set(secrets_unlocked or ()) and _K01_SECRET_RE.search(pub):
        pub = _K01_SECRET_RE.sub('家族事务', pub)
    clean_views = {}
    if isinstance(views, dict):
        for wk, wv in views.items():
            wname = str(wk or '').strip()
            wtxt = _clean_mem_line(wv, 140)
            if wname not in _VALID_MEMORY_ACTORS or not wtxt:
                continue
            if 'K01' not in set(secrets_unlocked or ()) and wname != '沈知韫' and _K01_SECRET_RE.search(wtxt):
                continue
            clean_views[wname] = wtxt
    if not pub and not clean_views:
        # Deterministic fallback digest grouped by public vs private actor witnesses
        pub_bits = []
        priv_bits = {}
        for ep in batch:
            kb = ep.get('known_by') or ['徐志北']
            snippet = _clean_mem_line(ep.get('summary') or '', 42)
            if not snippet:
                continue
            if len(kb) >= 3:
                pub_bits.append(f"D{ep['day']}:{snippet}")
            else:
                others = [w for w in kb if w != '徐志北']
                key = others[0] if len(others) == 1 else '徐志北'
                priv_bits.setdefault(key, []).append(f"D{ep['day']}:{snippet}")
        pub = ('；'.join(pub_bits))[:260] or f"第{d0}-{d1}天阶段经历归档（共{len(batch)}幕）。"
        for k, arr in priv_bits.items():
            clean_views[k] = ('；'.join(arr))[:140]

    ch_id = f"CH-{ms['next_chronicle_seq']:02d}"
    ms['next_chronicle_seq'] += 1
    chapter = {
        'id': ch_id,
        'day_range': [d0, d1],
        'episode_range': ep_rng,
        'entities': all_ents,
        'public': pub,
        'views': clean_views,
    }
    ms['chronicle'].append(chapter)
    consumed_ids = {ep['id'] for ep in batch}
    ms['episodes'] = [ep for ep in ms['episodes'] if ep['id'] not in consumed_ids]

    # Enforce MAX_CHRONICLE_CHAPTERS by deterministically folding the 2 oldest chapters if cap exceeded
    while len(ms['chronicle']) > MAX_CHRONICLE_CHAPTERS:
        c0 = ms['chronicle'].pop(0)
        c1 = ms['chronicle'][0]
        merged_pub = _clean_mem_line(f"{c0.get('public', '')[:125]}；{c1.get('public', '')[:125]}", 260)
        merged_views = {}
        for wk in set((c0.get('views') or {}).keys()) | set((c1.get('views') or {}).keys()):
            v0 = (c0.get('views') or {}).get(wk, '')
            v1 = (c1.get('views') or {}).get(wk, '')
            merged_views[wk] = _clean_mem_line('；'.join(x for x in (v0[:65], v1[:65]) if x), 140)
        c1['day_range'] = [min(c0['day_range'][0], c1['day_range'][0]), max(c0['day_range'][1], c1['day_range'][1])]
        c1['episode_range'] = [c0['episode_range'][0], c1['episode_range'][1]]
        c1['entities'] = list(dict.fromkeys((c0.get('entities') or []) + (c1.get('entities') or [])))
        c1['public'] = merged_pub
        c1['views'] = merged_views
    return chapter


def record_memory_turn(mem_store, *, fact='', anchor_ops=None, chronicle_digest=None,
                       day=1, time_str='', location='', sub_location='',
                       known_by=None, entities=None, tags=None,
                       day_crossed=False, overnight=False, secrets_unlocked=()):
    """Atomically record one committed turn into the v2 three-track memory store."""
    ms = normalize_memory_store(mem_store)
    cur_day = max(1, _parse_int(day, 1))
    cur_time = _clean_mem_line(time_str or '', 12)
    cur_loc = _clean_mem_line(location or '', 32)
    cur_sub = _clean_mem_line(sub_location or '', 32)
    cur_kb = _clean_known_by(known_by, default_actors=['徐志北'])
    clean_fact = _clean_mem_line(strip_prologue_marker(fact or ''), 180)
    ops = [op for op in (anchor_ops or ()) if isinstance(op, dict)]

    # Clear literary prologue marker cleanly once the first real story memory arrives
    if ms.get('prologue_active') and (clean_fact or ops):
        ms['prologue_active'] = False
        ms['episodes'] = [ep for ep in ms['episodes'] if not ep.get('is_prologue')]

    # 1. Seal pending_buffer if scene/day/witness boundary changed or capacity reached
    pb = ms['pending_buffer']
    if pb.get('facts'):
        pb_kb_set = set(pb.get('known_by') or ())
        cur_kb_set = set(cur_kb)
        projected_chars = sum(len(f) for f in pb['facts']) + len(clean_fact)
        boundary_crossed = bool(
            day_crossed
            or overnight
            or (pb.get('day') and pb['day'] != cur_day)
            or (pb.get('location') and cur_loc and pb['location'] != cur_loc)
            or (pb_kb_set and cur_kb_set and pb_kb_set != cur_kb_set)
            or (clean_fact and (len(pb['facts']) >= PENDING_FLUSH_MAX_FACTS or projected_chars > PENDING_FLUSH_MAX_CHARS))
        )
        if boundary_crossed:
            _seal_pending_buffer(ms, secrets_unlocked=secrets_unlocked)
            pb = ms['pending_buffer']

    # 2. Append new turn fact into pending_buffer (deduped)
    if clean_fact:
        fact_kb = _guard_k01_known_by(clean_fact, cur_kb, secrets_unlocked)
        if pb.get('facts') and set(pb.get('known_by') or ()) != set(fact_kb):
            _seal_pending_buffer(ms, secrets_unlocked=secrets_unlocked)
            pb = ms['pending_buffer']
        norm_new = re.sub(r'\s+', '', clean_fact)
        if not any(norm_new in re.sub(r'\s+', '', old) for old in pb['facts']):
            if not pb['facts']:
                pb['day'] = cur_day
                pb['location'] = cur_loc
                pb['sub_location'] = cur_sub
                pb['start_time'] = cur_time
                pb['known_by'] = fact_kb
            pb['last_time'] = cur_time or pb.get('last_time') or ''
            pb['facts'].append(clean_fact)
            pb['turns'] = int(pb.get('turns') or 0) + 1
            pb['entities'] = _extract_entities_from_text(
                clean_fact, list(pb.get('entities') or ()) + list(entities or ()) + fact_kb
            )
            pb['tags'] = list(dict.fromkeys(list(pb.get('tags') or ()) + [_clean_mem_line(t, 16) for t in (tags or ()) if _clean_mem_line(t, 16)]))[:6]
        if overnight or day_crossed:
            _seal_pending_buffer(ms, secrets_unlocked=secrets_unlocked)

    # 3. Apply atomic anchor_ops (ADD / UPDATE / RESOLVE) — permanent facts never lost to summarization
    for op in ops[:3]:
        act = str(op.get('op') or '').strip().lower()
        if act == 'add':
            atxt = _clean_mem_line(op.get('text') or '', 110)
            if not atxt:
                continue
            kind = str(op.get('kind') or 'milestone').strip()
            if kind not in ANCHOR_KINDS:
                kind = 'milestone'
            imp = max(1, min(5, _parse_int(op.get('importance'), 3)))
            if op.get('private_host') is True or (kind in ('secret', 'clue') and op.get('known_by') == ['徐志北']):
                akb = ['徐志北']
            elif isinstance(op.get('known_by'), list) and op['known_by']:
                # Restrict to actual witnesses in scene_known_by (never invent offstage witnesses)
                allowed_kb = set(cur_kb)
                scoped = [w for w in op['known_by'] if w in allowed_kb]
                akb = _clean_known_by(scoped or cur_kb)
            else:
                akb = list(cur_kb)
            akb = _guard_k01_known_by(atxt, akb, secrets_unlocked)
            ents = _extract_entities_from_text(atxt, list(op.get('entities') or ()) + akb)
            # Semantic dedup: update similar existing active anchor instead of cloning
            dup = next((a for a in ms['anchors'] if a['kind'] == kind and _text_similar(a['text'], atxt)), None)
            if dup is not None:
                dup['text'] = atxt
                dup['day'] = cur_day
                dup['importance'] = max(dup['importance'], imp)
                dup['known_by'] = _guard_k01_known_by(atxt, _clean_known_by(list(dup['known_by']) + akb), secrets_unlocked)
                dup['entities'] = list(dict.fromkeys(dup['entities'] + ents))
            else:
                aid = f"A-{ms['next_anchor_seq']:03d}"
                ms['next_anchor_seq'] += 1
                ms['anchors'].append({
                    'id': aid,
                    'kind': kind,
                    'day': cur_day,
                    'entities': ents,
                    'known_by': akb,
                    'status': 'active',
                    'importance': imp,
                    'text': atxt,
                })
        elif act == 'update':
            aid = str(op.get('id') or '').strip()
            target = next((a for a in ms['anchors'] if a['id'] == aid), None)
            if target is not None:
                atxt = _clean_mem_line(op.get('text') or '', 110)
                if atxt:
                    target['text'] = atxt
                    target['day'] = cur_day
                    if 'importance' in op:
                        target['importance'] = max(1, min(5, _parse_int(op.get('importance'), target['importance'])))
                    target['known_by'] = _guard_k01_known_by(target['text'], target['known_by'], secrets_unlocked)
                    target['entities'] = _extract_entities_from_text(target['text'], target['entities'])
        elif act == 'resolve':
            aid = str(op.get('id') or '').strip()
            idx = next((i for i, a in enumerate(ms['anchors']) if a['id'] == aid), None)
            if idx is not None:
                resolved = ms['anchors'].pop(idx)
                resolved['status'] = 'resolved'
                note = _clean_mem_line(op.get('note') or '', 60)
                if note:
                    resolved['note'] = note
                ms['resolved_anchors'].append(resolved)
                ms['resolved_anchors'] = ms['resolved_anchors'][-MAX_RESOLVED_ANCHORS:]

    # Enforce MAX_ACTIVE_ANCHORS cap (archive lowest-importance oldest anchor if exceeded)
    while len(ms['anchors']) > MAX_ACTIVE_ANCHORS:
        victim_idx = min(range(len(ms['anchors'])), key=lambda i: (ms['anchors'][i]['importance'], ms['anchors'][i]['day'], i))
        victim = ms['anchors'].pop(victim_idx)
        victim['status'] = 'resolved'
        ms['resolved_anchors'].append(victim)
        ms['resolved_anchors'] = ms['resolved_anchors'][-MAX_RESOLVED_ANCHORS:]

    # 4. Low-frequency chronicle archival (when Stage 2 provided chronicle_digest OR safety valve > HARD_MAX_EPISODES)
    if isinstance(chronicle_digest, dict) and (chronicle_digest.get('public') or chronicle_digest.get('views')):
        non_pro = [ep for ep in ms['episodes'] if not ep.get('is_prologue')]
        if len(non_pro) >= ARCHIVE_BATCH_EPISODES:
            batch = non_pro[:ARCHIVE_BATCH_EPISODES]
            _append_chronicle_chapter(
                ms, batch,
                public_text=chronicle_digest.get('public') or '',
                views=chronicle_digest.get('views'),
                secrets_unlocked=secrets_unlocked,
            )
    non_pro_after = [ep for ep in ms['episodes'] if not ep.get('is_prologue')]
    while len(non_pro_after) > HARD_MAX_EPISODES:
        batch = non_pro_after[:ARCHIVE_BATCH_EPISODES]
        _append_chronicle_chapter(ms, batch, secrets_unlocked=secrets_unlocked)
        non_pro_after = [ep for ep in ms['episodes'] if not ep.get('is_prologue')]

    return ms


def retrieve_memory_view(mem_store, *, query='', cast=(), present_actors=None,
                         location='', max_chars=2400, incremental=False,
                         exclude_fingerprints=None):
    """Multi-factor zero-dependency retriever with deterministic epistemic partitioning by known_by."""
    ms = normalize_memory_store(mem_store)
    cast_list = [c for c in (cast or ()) if c in _VALID_MEMORY_ACTORS]
    room_actors = [a for a in (present_actors if present_actors is not None else cast_list) if a in _VALID_MEMORY_ACTORS and a != '徐志北']
    room_set = set(room_actors)
    query_ents = set(_extract_entities_from_text(query, list(room_actors) + list(cast_list)))
    query_tokens = _extract_tokens(f"{query or ''} {location or ''}")
    max_day = max(
        [1]
        + [ep['day'] for ep in ms['episodes']]
        + [a['day'] for a in ms['anchors']]
        + [int((ms['pending_buffer'] or {}).get('day') or 1)]
    )

    def _score(text, entities, tags, item_loc, item_day, importance=3, is_anchor=False, is_pending=False):
        if is_pending:
            return 100.0
        ent_set = set(entities or ())
        # 1. Entity relevance (0.40)
        ent_hits = len((ent_set - {'徐志北'}) & (query_ents - {'徐志北'}))
        room_hits = len((ent_set - {'徐志北'}) & room_set)
        ent_score = min(1.0, (room_hits * 0.65 + ent_hits * 0.45)) if (room_set or query_ents) else 0.2
        # 2. Lexical / tag / location match (0.30)
        item_tokens = _extract_tokens(text + ' ' + ' '.join(tags or ()))
        lex_hits = len(query_tokens & item_tokens)
        lex_score = min(1.0, (lex_hits / max(1.0, min(6.0, float(len(query_tokens))))) if query_tokens else 0.0)
        if location and item_loc and location == item_loc:
            lex_score = min(1.0, lex_score + 0.35)
        # 3. Importance (0.20)
        imp_score = (max(1, min(5, int(importance))) / 5.0) * (1.15 if is_anchor else 0.85)
        # 4. Recency decay (0.10)
        age = max(0, max_day - max(1, int(item_day)))
        rec_score = 1.0 / (1.0 + 0.18 * age)
        return round(0.40 * ent_score + 0.30 * lex_score + 0.20 * imp_score + 0.10 * rec_score, 4)

    def _partition_bucket(known_by):
        kb_set = set(known_by or ('徐志北',))
        if not room_set:
            return ('host_private', '')
        if room_set.issubset(kb_set):
            return ('shared', '')
        present_knowers = [a for a in room_actors if a in kb_set]
        if present_knowers:
            return ('actor_private', '、'.join(present_knowers))
        return ('host_private', '')

    candidates = []
    # Pending buffer (always top priority current working memory)
    pb = ms['pending_buffer']
    if pb.get('facts'):
        pb_txt = f"[第{pb['day']}天 {pb.get('start_time') or ''} {pb.get('location') or ''}] " + '；'.join(pb['facts'])
        candidates.append({
            'source': 'pending', 'id': 'NOW', 'score': 100.0, 'pinned': True,
            'known_by': pb.get('known_by') or ['徐志北'], 'text': pb_txt.strip(),
        })

    # Active anchors (durable facts/promises/milestones)
    for a in ms['anchors']:
        sc = _score(a['text'], a['entities'], [a['kind']], '', a['day'], importance=a['importance'], is_anchor=True)
        tag_lbl = {'promise': '约定', 'milestone': '节点', 'secret': '秘密', 'clue': '线索', 'relationship': '关系'}.get(a['kind'], '锚点')
        candidates.append({
            'source': 'anchor', 'id': a['id'], 'score': sc, 'pinned': (not incremental and a['importance'] >= 4 and bool(set(a['entities']) & room_set)),
            'known_by': a['known_by'], 'text': f"[{a['id']}·{tag_lbl}·D{a['day']}] {a['text']}",
        })

    # Hot episodes
    eps = ms['episodes']
    recent_ep_ids = {ep['id'] for ep in eps[-3:]}
    for ep in eps:
        sc = _score(ep['summary'], ep['entities'], ep.get('tags'), ep.get('location'), ep['day'], importance=3, is_anchor=False)
        loc_part = f" {ep['location']}" if ep.get('location') else ''
        tm_part = f" {ep['time_range']}" if ep.get('time_range') else ''
        candidates.append({
            'source': 'episode', 'id': ep['id'], 'score': sc + (0.25 if ep['id'] in recent_ep_ids else 0.0),
            'pinned': (not incremental and ep['id'] in recent_ep_ids),
            'known_by': ep['known_by'],
            'text': f"[{ep['id']}·D{ep['day']}{tm_part}{loc_part}] {ep['summary']}",
        })

    # Chronicle chapters (split by public vs private actor view so private views never leak!)
    for ch in ms['chronicle']:
        dr = ch.get('day_range') or [1, 1]
        if ch.get('public'):
            sc = _score(ch['public'], ch.get('entities'), [], '', dr[1], importance=3, is_anchor=False)
            candidates.append({
                'source': 'chronicle', 'id': ch['id'], 'score': sc * 0.9, 'pinned': (not incremental and ch == ms['chronicle'][-1]),
                'known_by': list(_VALID_MEMORY_ACTORS),
                'text': f"[{ch['id']}·D{dr[0]}-{dr[1]}编年] {ch['public']}",
            })
        for wname, wtxt in (ch.get('views') or {}).items():
            sc = _score(wtxt, [wname, '徐志北'], [], '', dr[1], importance=3, is_anchor=False)
            candidates.append({
                'source': 'chronicle_view', 'id': f"{ch['id']}:{wname}", 'score': sc * 0.95, 'pinned': False,
                'known_by': ['徐志北', wname] if wname != '徐志北' else ['徐志北'],
                'text': f"[{ch['id']}·D{dr[0]}-{dr[1]}·{wname}线] {wtxt}",
            })

    candidates.sort(key=lambda c: (c['pinned'], c['score']), reverse=True)
    budget = max(400, int(max_chars or 2400))
    if incremental:
        # On turns 2..N inside an active session, focus on pending + highest-relevance non-trivial recalls
        candidates = [c for c in candidates if c['source'] == 'pending' or c['score'] >= 0.42]
        budget = min(budget, 1400)

    excl_fps = {str(x) for x in exclude_fingerprints if isinstance(x, str) and x} if (incremental and exclude_fingerprints) else set()
    shared = []
    actor_private = {}
    host_private = []
    used = 0
    selected_ids = []
    selected_fps = []
    ep_selected = 0
    ch_selected = 0
    max_eps = 4 if incremental else 8
    max_ch = 2 if incremental else 4
    for item in candidates:
        src = item['source']
        fp = ''
        if src != 'pending':
            fp = f"{item['id']}:{hashlib.sha1(item['text'].encode('utf-8')).hexdigest()[:8]}"
            if excl_fps and fp in excl_fps:
                continue
        if src == 'episode' and ep_selected >= max_eps:
            continue
        if src in ('chronicle', 'chronicle_view') and ch_selected >= max_ch:
            continue
        cost = len(item['text']) + 8
        if used + cost > budget and selected_ids:
            continue
        bucket, owner_lbl = _partition_bucket(item['known_by'])
        if bucket == 'shared':
            shared.append(item['text'])
        elif bucket == 'actor_private':
            actor_private.setdefault(owner_lbl, []).append(item['text'])
        else:
            host_private.append(item['text'])
        used += cost
        selected_ids.append(item['id'])
        if fp:
            selected_fps.append(fp)
        if src == 'episode':
            ep_selected += 1
        elif src in ('chronicle', 'chronicle_view'):
            ch_selected += 1

    # Lossless active anchor index for Stage 2 UPDATE/RESOLVE reference (preserves all high-importance & room anchors)
    anchors_for_stage2 = [
        {'id': a['id'], 'kind': a['kind'], 'day': a['day'], 'importance': a['importance'], 'text': a['text']}
        for a in sorted(
            ms['anchors'],
            key=lambda x: (x['importance'] >= 4 or bool(set(x['entities']) & room_set), bool(set(x['entities']) & room_set), x['importance'], x['day']),
            reverse=True,
        )[:MAX_ACTIVE_ANCHORS]
    ]
    return {
        'shared_scene_memory': shared,
        'actor_private_memory': actor_private,
        'host_private_memory': host_private,
        'selected_ids': selected_ids,
        'selected_fingerprints': selected_fps,
        'used_chars': used,
        'pending_facts': list(pb.get('facts') or []),
        'active_anchors_index': anchors_for_stage2,
        'chronicle_archive_batch': chronicle_archive_batch(ms),
        'stats': {
            'anchors': len(ms['anchors']),
            'resolved_anchors': len(ms['resolved_anchors']),
            'episodes': len(ms['episodes']),
            'chronicle': len(ms['chronicle']),
            'pending_facts': len(pb.get('facts') or []),
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


def layer_strings(mem_store):
    """Project v2 memory_store (or legacy v1 layers) into L1-L4 display strings for one-way .txt view."""
    if isinstance(mem_store, dict) and 'layers' in mem_store and 'episodes' not in mem_store:
        layers = mem_store.get('layers') or {}
        return {
            key: [entry_to_string(item) for item in (layers.get(key) or [])]
            for key in ('L1', 'L2', 'L3', 'L4')
        }
    ms = normalize_memory_store(mem_store)
    l1, l2, l3, l4 = [], [], [], []
    eps = list(ms['episodes'])
    pb = ms['pending_buffer']
    # L1: latest up to 2 sealed episodes + current pending buffer (total <= 3, valid monotonic 【n】 headers)
    hot_eps = eps[-2:] if pb.get('facts') else eps[-3:]
    older_eps = eps[:-len(hot_eps)] if hot_eps else []
    idx_counter = 1
    for ch in ms['chronicle']:
        dr = ch.get('day_range') or [1, 1]
        views_txt = ' | '.join(f"{k}:{v}" for k, v in (ch.get('views') or {}).items())
        body = f"[{ch['id']}] {ch.get('public', '')}" + (f"（暗线：{views_txt}）" if views_txt else '')
        l4.append(f"【{dr[0]}-{dr[1]}】{body}")
    for a in ms['anchors']:
        tag_lbl = {'promise': '约定', 'milestone': '节点', 'secret': '秘密', 'clue': '线索', 'relationship': '关系'}.get(a['kind'], '锚点')
        kb_lbl = '、'.join(a.get('known_by') or ['徐志北'])
        l3.append(f"【{a['day']}】[{a['id']}·{tag_lbl}·知情:{kb_lbl}] {a['text']}")
    for ep in older_eps:
        l2.append(f"【{ep['day']}】{ep['summary']}")
    for ep in hot_eps:
        l1.append(f"【{ep['day']}】{ep['summary']}")
        idx_counter += 1
    if pb.get('facts'):
        kb_lbl = '、'.join(pb.get('known_by') or ['徐志北'])
        loc_lbl = f"{pb['location']} " if pb.get('location') else ''
        tm_lbl = f"{pb.get('start_time') or ''} " if pb.get('start_time') else ''
        l1.append(f"【{pb['day']}】[本幕暂存·{loc_lbl}{tm_lbl}知情:{kb_lbl}] " + '；'.join(pb['facts']))
    return {'L1': l1, 'L2': l2, 'L3': l3, 'L4': l4}


def set_layer_strings(mem_layers, str_layers, *, prologue_active=None):
    """Legacy helper kept for injection_core direct manual CLI compatibility."""
    if isinstance(mem_layers, dict) and 'episodes' in mem_layers:
        out = normalize_memory_store(mem_layers)
        if prologue_active is not None:
            out['prologue_active'] = bool(prologue_active)
        return out
    out = copy.deepcopy(mem_layers) if isinstance(mem_layers, dict) else {'version': 1, 'prologue_active': False, 'layers': {'L1': [], 'L2': [], 'L3': [], 'L4': []}}
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
    return normalize_memory_store(out)


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
    intl['session_charm_gained'] = bool(raw_int.get('session_charm_gained', False)) if intl['scene_active'] else False
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
    # Host Physiology (Desire / Vigor / Release / Fetishes)
    raw_hp = raw_int.get('host_phys') if isinstance(raw_int.get('host_phys'), dict) else {}
    hp = intl['host_phys']
    hp['desire'] = max(0, min(100, _parse_int(raw_hp.get('desire'), 0)))
    hp['vigor'] = max(0, min(100, _parse_int(raw_hp.get('vigor'), 100)))
    hp['release_count'] = max(0, _parse_int(raw_hp.get('release_count'), 0))
    hp['edging_streak'] = max(0, min(20, _parse_int(raw_hp.get('edging_streak'), 0)))
    raw_fet = raw_hp.get('fetishes')
    if isinstance(raw_fet, list):
        hp['fetishes'] = list(dict.fromkeys(
            str(x).strip()[:24] for x in raw_fet if isinstance(x, str) and str(x).strip()
        ))[:8]
    # Heroine Body Development (5 zones: oral / hand / chest / foot / core)
    raw_bd = raw_int.get('body_dev') if isinstance(raw_int.get('body_dev'), dict) else {}
    for name in HEROINES:
        rb = raw_bd.get(name) if isinstance(raw_bd.get(name), dict) else {}
        for z in BODY_ZONES:
            intl['body_dev'][name][z] = max(0, min(100, _parse_int(rb.get(z), 0)))
    # Intimate Keepsakes (Trophy / Panties / Stockings Collection)
    raw_ks = raw_int.get('keepsakes')
    max_ks_seq = 0
    clean_ks = []
    if isinstance(raw_ks, list):
        seen_ids = set()
        for idx_ks, item in enumerate(raw_ks):
            norm_k = normalize_keepsake_dict(item, fallback_id=f'KS-{idx_ks + 1:03d}')
            if not norm_k:
                continue
            while norm_k['id'] in seen_ids:
                max_ks_seq += 1
                norm_k['id'] = f'KS-{max_ks_seq:03d}'
            seen_ids.add(norm_k['id'])
            m_ks = re.fullmatch(r'KS-(\d+)', norm_k['id'])
            if m_ks:
                max_ks_seq = max(max_ks_seq, int(m_ks.group(1)))
            clean_ks.append(norm_k)
    intl['keepsakes'] = clean_ks[:24]
    intl['next_keepsake_seq'] = max(_parse_int(raw_int.get('next_keepsake_seq'), 1), max_ks_seq + 1)
    # Vigilance
    raw_vig = raw.get('vigilance') if isinstance(raw.get('vigilance'), dict) else {}
    if raw_vig.get('位置'):
        base['vigilance']['位置'] = str(raw_vig['位置']).strip()
    raw_vt = raw_vig.get('目标') if isinstance(raw_vig.get('目标'), dict) else {}
    for name in VIGILANCE_TARGETS:
        t = raw_vt.get(name)
        if isinstance(t, dict):
            v_val = max(0, min(100, _parse_int(t.get('警惕'), 0)))
            d_val = max(0, _parse_int(t.get('发现'), 0))
            raw_reason = str(t.get('动因') or t.get('reason') or '').replace('|', ' ').replace('\n', ' ').replace('\r', ' ').strip()[:48]
            if v_val == 0 and d_val == 0:
                raw_reason = ''
            base['vigilance']['目标'][name] = {
                '警惕': v_val,
                '发现': d_val,
                '发现几率': max(0, min(100, _parse_int(t.get('发现几率'), 0))),
                '动因': raw_reason,
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
            if bucket == 'delivered':
                clean_arr = clean_arr[-MAX_DELIVERED_ITEMS:]
            elif bucket == 'history':
                clean_arr = clean_arr[-MAX_HISTORY_ITEMS:]
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
        base['intel']['leverage_charges'] = max(0, min(3, _parse_int(ri.get('leverage_charges'), 0)))
    if isinstance(raw.get('director'), dict):
        base['director'].update(copy.deepcopy(raw['director']))
    raw_mind = raw.get('npc_mind') if isinstance(raw.get('npc_mind'), dict) else {}
    for name in NPC_MIND_TARGETS:
        rm = raw_mind.get(name)
        if not isinstance(rm, dict):
            continue
        mood_txt = re.sub(r'[\r\n|]+', ' ', str(rm.get('mood') or '')).strip()[:40]
        mood_ttl = max(0, min(4, _parse_int(rm.get('mood_ttl'), 0)))
        if not mood_txt or mood_ttl <= 0:
            mood_txt = ''
            mood_ttl = 0
        preocc = re.sub(r'[\r\n|]+', ' ', str(rm.get('preoccupation') or '')).strip()[:48]
        if not preocc and 'preoccupation' not in rm:
            preocc = base['npc_mind'][name]['preoccupation']
        clean_imps = []
        raw_imps = rm.get('impressions')
        if isinstance(raw_imps, list):
            for item in raw_imps:
                if isinstance(item, dict):
                    itxt = re.sub(r'[\r\n|]+', ' ', str(item.get('text') or '')).strip()[:48]
                    ittl = max(0, min(8, _parse_int(item.get('ttl'), 4)))
                    if itxt and ittl > 0:
                        clean_imps.append({'text': itxt, 'ttl': ittl})
                elif isinstance(item, str) and item.strip():
                    itxt = re.sub(r'[\r\n|]+', ' ', item).strip()[:48]
                    if itxt:
                        clean_imps.append({'text': itxt, 'ttl': 4})
        aff_delta = max(-20, min(20, _parse_int(rm.get('aff_delta_last'), 0)))
        base['npc_mind'][name] = {
            'mood': mood_txt,
            'mood_ttl': mood_ttl,
            'preoccupation': preocc,
            'impressions': clean_imps[-2:],
            'aff_delta_last': aff_delta,
        }
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
                tm = re.search(
                    rf'徐承邺_{re.escape(who)}：警惕\s*(\d+)\s*\|\s*发现\s*(\d+)\s*\|\s*发现几率\s*(\d+)(?:\s*\|\s*动因[：:]\s*([^\n|]+))?',
                    vblock,
                )
                if tm:
                    reason_str = (tm.group(4) or '').strip()[:48]
                    v_num = max(0, min(100, int(tm.group(1))))
                    d_num = max(0, int(tm.group(2)))
                    state['vigilance']['目标'][who] = {
                        '警惕': v_num,
                        '发现': d_num,
                        '发现几率': int(tm.group(3)),
                        '动因': '' if (v_num == 0 and d_num == 0) else reason_str,
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
            intel = {'held': [], 'consumed': [], 'su_ab_contacts': 0, 'leverage_armed': '', 'leverage_charges': 0}
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
            lcm2 = re.search(r'^商业杠杆护盾：[^\n]*?(\d+)', ib, re.M)
            if lcm2:
                intel['leverage_charges'] = max(0, min(3, int(lcm2.group(1))))
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
        v1_shell = {'version': 1, 'prologue_active': is_prologue_only, 'layers': {'L1': [], 'L2': [], 'L3': [], 'L4': []}}
        layers = set_layer_strings(v1_shell, parsed_str_layers, prologue_active=is_prologue_only)

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
        '（只读视图：由 save_store 从 save_state.json + memory_store.json 单向自动渲染，正式互动以 JSON 为唯一真相）',
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
        reason = str(t.get('动因') or '').replace('|', ' ').replace('\n', ' ').strip()[:48]
        suffix = f" | 动因：{reason}" if reason and (t.get('警惕', 0) > 0 or t.get('发现', 0) > 0) else ''
        lines.append(f"徐承邺_{name}：警惕 {t['警惕']} | 发现 {t['发现']} | 发现几率 {t['发现几率']}{suffix}")
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
    if int(intel.get('leverage_charges', 0) or 0) > 0:
        lines.append(f"商业杠杆护盾：剩余 {int(intel['leverage_charges'])} 次")
    lines.append('')

    intl = state.get('intimate') or default_intimate()
    hp = intl.get('host_phys') or default_host_phys()
    bd = intl.get('body_dev') or default_body_dev()
    ks_list = [k for k in (intl.get('keepsakes') or []) if isinstance(k, dict) and k.get('name')]
    has_host_phys = (
        int(hp.get('desire', 0) or 0) > 0
        or int(hp.get('vigor', 100) if hp.get('vigor') is not None else 100) < 100
        or int(hp.get('release_count', 0) or 0) > 0
        or bool(hp.get('fetishes'))
    )
    has_body_dev = any(
        int((bd.get(h) or {}).get(z, 0) or 0) > 0
        for h in HEROINES for z in BODY_ZONES
    )
    has_intimate_notes = (
        intl.get('scene_active')
        or intl.get('privacy', 'open_public') != 'open_public'
        or bool(intl.get('sub_location'))
        or int(intl.get('noise_risk') or 0) > 0
        or has_host_phys
        or has_body_dev
        or bool(ks_list)
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
        if has_host_phys:
            fet_txt = (' | 癖好：' + '、'.join(hp.get('fetishes') or [])) if hp.get('fetishes') else ''
            lines.append(
                f"  宿主生理：欲望 {int(hp.get('desire', 0) or 0)}/100 | 亲密耐力 {int(hp.get('vigor', 100) if hp.get('vigor') is not None else 100)}/100"
                f" | 累计释放 {int(hp.get('release_count', 0) or 0)}次{fet_txt}"
            )
        for h in HEROINES:
            att = (intl.get('attire') or {}).get(h) or {}
            trs = (intl.get('traces') or {}).get(h) or []
            h_bd = bd.get(h) or {}
            sig_z = HEROINE_SIGNATURE_ZONES.get(h, '')
            dev_bits = [
                f"{BODY_ZONE_LABELS.get(z, z)}{'★' if z == sig_z else ''}{int(h_bd.get(z, 0) or 0)}"
                for z in BODY_ZONES if int(h_bd.get(z, 0) or 0) > 0
            ]
            bits = []
            if att.get('outfit', 'default') != 'default' or att.get('state', 'neat') != 'neat':
                bits.append(f"衣着={att.get('outfit', 'default')}({ATTIRE_LABELS.get(att.get('state', 'neat'), '整洁')})")
            if att.get('gifted_items'):
                bits.append('已获赠=' + '、'.join(att['gifted_items']))
            if trs:
                bits.append('痕迹=' + '、'.join(f"{t['kind']}({t['turns']}轮)" for t in trs))
            if dev_bits:
                bits.append('身体开发=' + '/'.join(dev_bits))
            if bits:
                lines.append(f"  {h}：" + '；'.join(bits))
        ih_active = [f"{k}:{INTER_HEROINE_LABELS.get(int(v), str(v))}" for k, v in (intl.get('inter_heroine') or {}).items() if int(v or 0) > 0]
        if ih_active:
            lines.append('  女主暗流：' + ' | '.join(ih_active))
        if ks_list:
            ks_rows = [
                f"{k['id']}·{k['owner']}的{k['name']}({KEEPSAKE_METHOD_LABELS.get(k.get('method', ''), '留存')}/{KEEPSAKE_CONDITION_LABELS.get(k.get('condition', ''), '余香')}/{'失主已知' if k.get('owner_aware') else '失主未觉'})"
                for k in ks_list[:12]
            ]
            lines.append('  私密贴身珍藏：' + '；'.join(ks_rows))
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


def harvest_engine_txt_mutations(base_state, memory_text='', items_text=''):
    """Narrow sandbox boundary helper: harvest ONLY machine fields mutated by legacy injection_core stage calls
    into pure JSON save_state without ever touching memory_store.json or JSON-native subsystems."""
    state = normalize_state(base_state)
    migrated, _ = migrate_from_legacy_texts(
        memory_text or '',
        items_text or '',
        None,
        base_state=state,
    )
    out = copy.deepcopy(state)
    if memory_text:
        for key in ('panels', 'presence', 'micro_states', 'buffs', 'counters',
                    'vigilance', 'tasks', 'intel', 'director', 'lifecycle'):
            out[key] = copy.deepcopy(migrated[key])
        if (migrated.get('mechanics') or {}).get('su_affection_85_unlocked'):
            out.setdefault('mechanics', {})['su_affection_85_unlocked'] = True
        # Preserve dynamic_catalog & next_dyn_seq (JSON-only) while harvesting redeemed/recent/echoes
        out['shop']['redeemed'] = copy.deepcopy(migrated['shop']['redeemed'])
        out['shop']['recent'] = copy.deepcopy(migrated['shop']['recent'])
        out['shop']['echoes'] = copy.deepcopy(migrated['shop']['echoes'])
    if items_text:
        out['items'] = copy.deepcopy(migrated['items'])
    return normalize_state(out)


def load_bundle(root, files=None, *, sync_txt_drift=True):
    """Load (state, memory_store, recent) from JSON truth; when sync_txt_drift is True, a fast SHA-256 check
    triggers zero-parse bypass on normal live reads and narrow non-memory harvest ONLY if legacy injection_core mutated .txt."""
    root = Path(root)

    def _read_bytes(rel):
        if files is not None and rel in files:
            return files[rel]
        p = root / rel
        return p.read_bytes() if p.is_file() else None

    raw_state = _read_bytes(SAVE_STATE_PATH)
    raw_mem_store = _read_bytes(MEMORY_STORE_PATH)
    if raw_mem_store is None:
        raw_mem_store = _read_bytes(LEGACY_MEMORY_LAYERS_PATH)
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

    if raw_state and raw_mem_store:
        try:
            state = normalize_state(json.loads(raw_state.decode('utf-8')))
            mem_store = normalize_memory_store(json.loads(raw_mem_store.decode('utf-8')))

            if sync_txt_drift:
                sha = state.get('rendered_sha256') or {}
                mem_drifted = bool(raw_mem and sha.get('memory_txt') and _sha256_bytes(raw_mem) != sha['memory_txt'])
                items_drifted = bool(raw_items and sha.get('items_txt') and _sha256_bytes(raw_items) != sha['items_txt'])
                if mem_drifted or items_drifted:
                    state = harvest_engine_txt_mutations(
                        state,
                        raw_mem.decode('utf-8') if (mem_drifted and raw_mem) else '',
                        raw_items.decode('utf-8') if (items_drifted and raw_items) else '',
                    )
            return state, mem_store, recent
        except ValueError:
            pass

    # Cold bootstrap only when JSON files do not exist yet
    state, legacy_layers = migrate_from_legacy_texts(
        raw_mem.decode('utf-8') if raw_mem else '',
        raw_items.decode('utf-8') if raw_items else '',
        data_dict,
    )
    return state, normalize_memory_store(legacy_layers), recent


def render_bundle_bytes(state, mem_store, recent=None, *, data_dict=None):
    """Build byte payloads for all 存档/ files so RoundStore can commit them atomically."""
    state = normalize_state(state)
    mem_store = normalize_memory_store(mem_store)
    mem_txt = render_memory_txt(state, mem_store).encode('utf-8')
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
        MEMORY_STORE_PATH: _json_bytes(mem_store),
    }
    if recent is not None:
        clean_recent = {
            'version': 1,
            'playback': copy.deepcopy(recent.get('playback')),
            'segments': [copy.deepcopy(s) for s in (recent.get('segments') or []) if isinstance(s, dict)][-MAX_RECENT_SEGMENTS:],
        }
        out[RECENT_PLAYBACK_PATH] = _json_bytes(clean_recent)
    return out


def save_bundle(stage_root, state, mem_store, recent=None, *, data_dict=None):
    """Write structured JSON state + memory_store + one-way rendered .txt views atomically into stage_root."""
    stage_root = Path(stage_root)
    payloads = render_bundle_bytes(state, mem_store, recent, data_dict=data_dict)
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

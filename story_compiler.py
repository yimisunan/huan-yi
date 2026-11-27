"""Deterministic source compiler, prefix freezer, stream parser, and zero-cost guardrails.

Reads canonical rule/lore/character/relationship/event sources without duplicating or mutating them,
producing cache-friendly frozen prefixes (Zone 0 + Zone 1), minimal per-turn deltas (Zone 2),
background settlement prompts, and deterministic red-line checks.
"""
import hashlib
import json
from pathlib import Path
import re
import threading

import injection_core as ic
import round_runtime as rr
import save_store
import story_progression as sp
from relationship_query import RelationshipRegistry

_SC_CACHE_LOCK = threading.RLock()
_SC_CACHE = {}
_SC_CACHE_MAX = 96


def _stat_sig(path):
    p = Path(path).resolve()
    try:
        st = p.stat()
        return (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(p), 0, -1)


def _sc_cache_get(key):
    with _SC_CACHE_LOCK:
        return _SC_CACHE.get(key)


def _sc_cache_set(key, val):
    with _SC_CACHE_LOCK:
        if len(_SC_CACHE) >= _SC_CACHE_MAX:
            _SC_CACHE.pop(next(iter(_SC_CACHE)), None)
        _SC_CACHE[key] = val
    return val

PEOPLE = ('沈知韫', '苏婉青', '徐念薇')
OPTION_NAMES = {'A': '日常互动', 'B': '社交接触', 'C': '主动行为'}
STREAM_PROTOCOL_VERSION = 1

_GEN_TABLE_RE = re.compile(r'【注册表生成表开始】.*?【注册表生成表结束】', re.S)
_LIVE_FOOTER_RE = re.compile(r'\n*【正式互动入口适用边界】[^\n]*')
_CHAR_LIVE_FOOTER_RE = re.compile(r'\n*【正式连续互动】[^\n]*')
_PARAM_HEADER_RE = re.compile(r'\n*【事件参数】[^\n]*')
_INDEX_KEY_RE = re.compile(r'\s*※索引key※\s*(?:char|lore|narrative|sys)\.\S+')
_CROSS_MODULE_PTR_RE = re.compile(r'\n*【跨模块指针】[^\n]*')
_KINSHIP_DEADLINE_RE = re.compile(r'\n*【亲属关系·身份死线】[^\n]*')
_LEGACY_ONLY_LABEL_RE = re.compile(r'\n*【唯一合法表述】[^\n]*')
_MULTI_NL_RE = re.compile(r'\n{3,}')

_LINE_TAG_RE = re.compile(
    r'^\s*(?:[-*•>]\s*)*(?:\*\*)?(?:(?:旁白|叙述|人物动作|动作|角色对白|对白|台词)\s*[:：]\s*)?'
    r'\[(N|A|D)(?:[:：]([^\]]+))?\](?:\*\*)?\s*(.*)$'
)
_BARE_NARRATION_RE = re.compile(
    r'^\s*(?:[-*•>]\s*)*(?:\*\*)?(?:(?:旁白|叙述)\s*[:：]|\[(?:旁白|叙述)\])(?:\*\*)?\s*(.+)$'
)
_INLINE_TAG_SPLIT_RE = re.compile(
    r'(?:\s+|(?<=[。！？!?；;”"」』）)]))\s*(?=(?:\*\*)?(?:(?:旁白|叙述|人物动作|动作|角色对白|对白|台词)\s*[:：]\s*)?\[(?:N|(?:A|D)[:：][^\]]+)\])'
)
_DECISION_SEP_RE = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:\*\*)?'
    r'(?:[-—–=]{2,}\s*(?:DECISION|段末抉择|抉择)\s*[-—–=]*'
    r'|(?:DECISION|段末抉择|抉择)\s*[-—–=]{2,}'
    r'|【\s*(?:DECISION|段末抉择|抉择)\s*】'
    r'|#{1,6}\s*(?:DECISION|段末抉择|抉择)'
    r'|(?:DECISION|段末抉择))'
    r'(?:\*\*)?(?:\s*[（(][^)\n）]{0,20}[)）])?\s*[:：]?\s*$',
    re.I,
)
_DECISION_BLOCK_SPLIT_RE = re.compile(
    r'(?:^|\r?\n)\s*(?:#{1,6}\s*)?(?:\*\*)?'
    r'(?:'
    r'[-—–=]{2,}\s*\r?\n(?:\s*\r?\n)?\s*(?:#{1,6}\s*)?(?:\*\*)?(?:DECISION|段末抉择|抉择)\s*[-—–=]*(?:\*\*)?(?:\s*\r?\n\s*[-—–=]{2,})?'
    r'|[-—–=]{2,}\s*(?:DECISION|段末抉择|抉择)\s*[-—–=]*(?:\*\*)?(?:\s*\r?\n\s*[-—–=]{2,})?'
    r'|(?:DECISION|段末抉择|抉择)\s*[-—–=]{2,}(?:\*\*)?'
    r'|【\s*(?:DECISION|段末抉择|抉择)\s*】(?:\*\*)?'
    r'|#{1,6}\s*(?:\*\*)?(?:DECISION|段末抉择|抉择)(?:\*\*)?'
    r'|(?:DECISION|段末抉择)(?:\*\*)?'
    r')'
    r'(?:\s*[（(][^)\n）]{0,20}[)）])?\s*[:：]?\s*(?=\r?\n|$)',
    re.I,
)
_INLINE_DECISION_SEP_RE = re.compile(
    r'\s*(?:\*\*)?(?:[-—–=]{3,}\s*DECISION\s*[-—–=]{3,}|[-—–=]{2,}\s*DECISION\s*[-—–=]{2,})(?:\*\*)?\s*',
    re.I,
)
_BARE_DIVIDER_RE = re.compile(r'^\s*[-—–=*_]{3,}\s*$')
_PROMPT_LINE_RE = re.compile(
    r'^\s*(?:[-*•>]\s*)*(?:#{1,6}\s*)?(?:\*\*)?'
    r'(?:PROMPT|提示|抉择提示|段末提示|当前局面|局面提示|抉择)'
    r'(?:\*\*)?\s*[:：]\s*(?:\*\*)?(.*)$',
    re.I,
)
_OPT_TIER_LABEL = r'(?:日常互动|社交接触|主动行为|日常|社交|主动|\d+\s*(?:体力|⚡))'
_OPT_LINE_RE = re.compile(
    r'^\s*(?:[-*•>]\s*)*(?:#{1,6}\s*)?(?:\*\*)?'
    r'(?:'
    r'(?:选项\s*)?([ABC])(?:\*\*)?(?:\s*\[(?i:MOVE)[:：]\s*([^\]]+?)\s*\])?(?:\*\*)?'
    r'(?:\s*(?:[·•\-—]\s*' + _OPT_TIER_LABEL + r'(?:\s*[（(][^）)\n]{1,16}[)）])?'
    r'|[（(\[]\s*' + _OPT_TIER_LABEL + r'[^）)\]\n]{0,16}[)）\]])(?:\s*\[(?i:MOVE)[:：]\s*([^\]]+?)\s*\])?(?:\*\*)?)?'
    r'\s*[:：.、)）]\s*'
    r'|[\[【(（]\s*([ABC])\s*[\]】)）](?:\*\*)?(?:\s*\[(?i:MOVE)[:：]\s*([^\]]+?)\s*\])?(?:\*\*)?'
    r'(?:\s*(?:[·•\-—]\s*' + _OPT_TIER_LABEL + r'(?:\s*[（(][^）)\n]{1,16}[)）])?'
    r'|[（(\[]\s*' + _OPT_TIER_LABEL + r'[^）)\]\n]{0,16}[)）\]])(?:\s*\[(?i:MOVE)[:：]\s*([^\]]+?)\s*\])?(?:\*\*)?)?'
    r'\s*(?:[:：.、)）]\s*|\s+(?=\S))'
    r')'
    r'(?:\*\*)?(.*)$',
    re.I,
)
_OPT_INLINE_MOVE_RE = re.compile(r'^\s*\[(?i:MOVE)[:：]\s*([^\]]+?)\s*\]\s*')
_OPT_TRAILING_MOVE_RE = re.compile(r'\s*\[(?i:MOVE)[:：]\s*([^\]]+?)\s*\]\s*[。.]?\s*$')
_DEFAULT_DECISION_PROMPT = '此刻，你准备怎么回应？'
_INTIMATE_TURN_RE = re.compile(
    r'强吻|亲吻|舌吻|拥吻|轻吻|热吻|吻(?:上|住|下|向|过|了|进|着|落|她|在)|抚摸|爱抚|轻揉|揉捏|按摩|按揉|摩挲|轻抚|抚过|贴近|凑近|抱紧|搂住|揽住|贴住|靠在怀里|压倒|推倒|扑倒|抱上床|抱进卧室|上床|'
    r'脱衣|脱掉|褪下|掀起裙|解开衣|解开扣|扯开|撕破|撩起|衣领|领口|肩带|睡裙|睡衣|内衣|内裤|底裤|丝袜|黑丝|偷藏|私藏|嗅闻|脚踝|玉足|美足|足背|足弓|脚尖|脚趾|手腕|指尖|锁骨|后颈|腰线|胸线|36D|大腿内侧|腿间|乳房|乳尖|酥胸|丰臀|私处|下身|小穴|穴口|'
    r'体香|沐浴露|耳垂|耳畔|耳边|精油|催情|桃露|香薰|眼罩|滚轮|润滑|束缚|项圈|丝带|摄像头|针孔|偷拍|监听|'
    r'足交|乳交|手交|素股|胸推|口交|颜射|射精|潮吹|舔|吮|咬|啃|捏|掐|揉|磨|蹭|跨坐|压在身下|按在墙上|把玩|掰开|'
    r'挺入|抽插|顶入|撞击|调教|侍奉|跪下含|含住|指奸|后入|骑乘|内射|外射|吞精|自慰|自渎|换衣|洗澡|沐浴|走光|湿身|高潮|性爱|做爱|情欲|亲密接触'
)

_WILL_SECRET_RE = re.compile(
    r'唯一合法继承人|唯一继承人|亲生子继承|继承真相|千亿家产唯一'
    r'|遗嘱[^\n。！？]{0,12}(?:指定|写着|留给|归|给了|继承|家产|份额)'
    r'|(?:志北|亲生子|继承权)[^\n。！？]{0,10}遗嘱'
)
_SU_RESIDENCE_CONFLICT_RE = re.compile(
    r'苏婉青[^。\n]{0,16}(?:常住(?:在)?(?:徐家)?主宅|(?:一直|就)?住在(?:徐家)?主宅|回(?:到)?自己(?:在主宅)?的卧室)'
)
_LIVE_FORBIDDEN_HOST_IDS = frozenset({
    'HOST_07', 'HOST_12', 'HOST_13', 'HOST_14', 'HOST_15',
    'DS_11', 'SHAME_15', 'SHAME_16', 'SHAME_17', 'SHAME_18',
})
_LEGACY_STAMINA_COMP_RE = re.compile(r'\n*【动态体力代偿※填入HOST_EVENTS※】[^\n]*')
_SETTLE_DROP_SECTIONS_RE = re.compile(
    r'\n*【(?:适用边界|意外白名单|插入时机|身体反应与阶段判断|耻感反弹|解离空洞|与其他系统硬耦合|'
    r'AI操作清单|撤离压力|引擎被动规则|持续_体液锁定 BUFF|越界联动掉分与完好防线修正|'
    r'警惕值阶梯后果|全角色联动·被发现事件|系统商城|商业嗅觉子系统[^】]*|一次性情报库[^】]*|'
    r'单体定向被动技能[^】]*|机制与加权|五阶与发现|魅力阶梯与增减平衡|奖励档位[^】]*|'
    r'定位|职责分工|条件校验|最高红线·任务只读不驱动|操作清单)】[^\n]*(?:\n(?!【)[^\n]*)*'
)
_SETTLE_DIRECTOR_PROSE_RE = re.compile(r'\n*正式互动（live_interaction）同时启用后端活体世界导演 2\.0[^\n]*')
_SETTLE_BACKEND_MATH_RES = (
    # Pure Python arithmetic in sys.ds (modulation soft cap 1.50x, overnight auto-masturbation & +5 rest recovery math)
    re.compile(r'高潮累积受欲望、堕落、宿主魅力[^。]*。'),
    re.compile(r'（若跨夜入睡时[^）]*上限88）'),
    re.compile(r'；纯A级平和照料回合若目标体力≤25且无消耗标签，后端自动轻缓回神\+5（至多回至30）'),
    # Pure Python RNG math in sys.pregnancy (preserving 内射/外射/潜伏期/确诊怀孕 trigger rules 100%)
    re.compile(r'\(安全期×0\.25[^)]*不进受孕暗骰\)'),
    re.compile(r'，并自动挂载24回合【持续_体液锁定】BUFF（[^）]*）'),
    # Backend counter persistence implementation details in sys.breakout (preserving all 4 breakout & effective_progress rules)
    re.compile(r'并在 breakout_triggered 非空时真实落盘冷却计数[^。]*。'),
)
_SETTLE_LEGACY_KEY_REPLACEMENTS = (
    ('SHAME_EVENTS', 'shame_events'),
    ('DEPRAVITY_EVENTS', 'depravity_events'),
    ('DS_EVENTS', 'ds_events'),
    ('AFFECTION_EVENTS', 'affection_events'),
    ('VIGILANCE_EVENTS', 'vigilance_events'),
    ('HOST_EVENTS', 'host_events'),
    ('round_conditions', 'resolution.conditions'),
    ('TASK_ISSUE', 'resolution.task'),
    ('ITEM_ENTRIES', 'resolution.items'),
)


def _digest_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _clean_text(text):
    return _MULTI_NL_RE.sub('\n\n', text).strip()


def _strip_kb_noise(content, keep_event_hint=False, mode='foreground',
                    protagonist_style='faithful', protocol_mode='dual_stream_v2'):
    text = _GEN_TABLE_RE.sub('', content)
    text = _LIVE_FOOTER_RE.sub('', text)
    text = _INDEX_KEY_RE.sub('', text)
    text = _CROSS_MODULE_PTR_RE.sub('', text)
    if not keep_event_hint:
        text = _PARAM_HEADER_RE.sub('', text)
    if mode == 'foreground':
        text = _KINSHIP_DEADLINE_RE.sub('', text)
        if protocol_mode == 'dual_stream_v2':
            text = _LEGACY_ONLY_LABEL_RE.sub('', text)
        if normalize_protagonist_style(protagonist_style) == 'silent':
            text = text.replace(
                '[D:徐志北] 所以妈是不打算把南城那块地交给他？',
                '[A:徐志北] 他把茶杯往桌内推了半寸，抬头问起南城那块地是不是不打算交给大哥。',
            )
    elif mode == 'settlement':
        text = _LEGACY_STAMINA_COMP_RE.sub('', text)
        text = _SETTLE_DROP_SECTIONS_RE.sub('', text)
        text = _SETTLE_DIRECTOR_PROSE_RE.sub('', text)
        for rx in _SETTLE_BACKEND_MATH_RES:
            text = rx.sub('', text)
        for old_k, new_k in _SETTLE_LEGACY_KEY_REPLACEMENTS:
            text = text.replace(old_k, new_k)
    return _clean_text(text)


def _load_kb_entries(root, name):
    path = Path(root) / 'txt文件/知识库' / (name + '.json')
    key = ('kb', _stat_sig(path))
    cached = _sc_cache_get(key)
    if cached is not None:
        return cached
    data = json.loads(path.read_text(encoding='utf-8'))
    entries = data.get('data', {}).get('entries', []) or data.get('entries', [])
    return _sc_cache_set(key, entries)


def _entry_key(entry):
    content = entry.get('content', '')
    match = re.search(r'※索引key※\s*((?:char|lore|narrative|sys)\.[\w]+)', content)
    if match:
        return match.group(1)
    return entry.get('name', '').split('（', 1)[0]


def compile_relationships(root, cast, references=()):
    """Losslessly compile scoped relationship facts, secret boundaries, beliefs, and address forms."""
    root = Path(root)
    reg = RelationshipRegistry(root)
    rows = reg.verify_view()[1:]
    data = reg.data
    ref_names = [r['name'] if isinstance(r, dict) else str(r) for r in references]
    participants = sorted(set(cast) | {'徐志北'})
    participant_set = set(participants)
    related = participant_set | set(ref_names)

    shared = [
        fact['text'] for fact in data['facts'].values()
        if fact['known_by'] == '*'
        and (fact['subject'] in related or fact['object'] in related)
    ]

    known_by = {}
    for person in participants:
        secrets = [
            fact['text'] for fact in data['facts'].values()
            if isinstance(fact['known_by'], list) and person in fact['known_by']
        ]
        if secrets:
            known_by[person] = secrets

    unknown_by_present = [p for p in participants if p not in known_by]

    beliefs = {}
    for person in participants:
        items = [b['text'] for b in data['beliefs'].values() if b['holder'] == person]
        if items:
            beliefs[person] = items

    forms = {}
    for row in rows:
        speaker, listener = row.get('speaker'), row.get('listener')
        if speaker not in participant_set or listener not in related:
            continue
        forms[f'{speaker}->{listener}'] = _compact_relationship_occasions(row)

    return {
        'shared': shared,
        'secret_boundaries': {
            'known_only_by': known_by,
            'unknown_by_present': unknown_by_present,
        },
        'beliefs': beliefs,
        'forms': forms,
        'rule': '称谓为合法候选（f正式/r放松/b商务/i私密亲密，未单列场合沿用f或r；s自称/a称呼），承接上下文可用我/你或省略；常规/公开场对母亲/姐姐/嫂子/大哥严禁直呼名字，i私密称谓仅对独处或失守的对应特定对象单独生效、禁扩散至同场旁观亲属；绝密仅限known_only_by本人，严禁向unknown_by_present泄露或碰巧知晓。',
    }


def _compact_relationship_occasions(row):
    occasions = {}
    for occ, odata in row.get('occasions', {}).items():
        selfs = [c['text'] for c in odata.get('self_candidates', []) if c['text'] not in ('', '我')]
        addrs = [
            c['text']
            for target in odata.get('targets', [])
            for c in target.get('address_candidates', [])
            if c['text'] not in ('', '你')
        ]
        slot = {}
        if selfs:
            slot['s'] = selfs
        if addrs:
            slot['a'] = addrs
        occasions[occ[0]] = slot
    base_f = occasions.get('f', {})
    compact_occ = {'f': base_f}
    if 'r' in occasions and occasions['r'] != base_f:
        compact_occ['r'] = occasions['r']
    if 'b' in occasions and occasions['b'] != base_f and occasions['b'] != compact_occ.get('r'):
        compact_occ['b'] = occasions['b']
    i_slot = occasions.get('i')
    if i_slot and i_slot != base_f and i_slot != occasions.get('r') and i_slot != occasions.get('b'):
        compact_occ['i'] = i_slot
    return base_f if len(compact_occ) == 1 else compact_occ


def compile_relationships_delta(root, cast, new_refs):
    """Losslessly compile directional address forms & public facts for newly mentioned offstage characters."""
    root = Path(root)
    ref_names = [r['name'] if isinstance(r, dict) else str(r) for r in (new_refs or ())]
    ref_set = {n for n in ref_names if n and n != '徐志北'} - set(cast or ())
    if not ref_set:
        return {'shared': [], 'forms': {}}
    reg = RelationshipRegistry(root)
    rows = reg.verify_view()[1:]
    data = reg.data
    participants = sorted(set(cast or ()) | {'徐志北'})
    participant_set = set(participants)

    shared_delta = [
        fact['text'] for fact in data['facts'].values()
        if fact['known_by'] == '*'
        and (fact['subject'] in ref_set or fact['object'] in ref_set)
        and not (fact['subject'] in participant_set or fact['object'] in participant_set)
    ]

    forms_delta = {}
    for row in rows:
        speaker, listener = row.get('speaker'), row.get('listener')
        if speaker in participant_set and listener in ref_set:
            forms_delta[f'{speaker}->{listener}'] = _compact_relationship_occasions(row)

    return {
        'shared': shared_delta,
        'forms': forms_delta,
        'offstage_guard': (
            '以上场外人物仅背景提及(不在场)，严禁写成[D:...]台词或当场动作；'
            '称谓须严守上述候选(常规/公开场对母亲/姐姐/嫂子/大哥严禁直呼名字)；'
            '其私密知情与未解锁绝密严禁向在场不知情人物泄露。'
        ),
    }


def compile_event_catalog(root, active_groups=None, live_mode=False):
    """Strip internal numeric calculation parameters; emit only valid tag whitelist & patterns."""
    reg_path = Path(root) / 'txt文件/事件注册表.json'
    key = ('event_catalog', _stat_sig(reg_path), tuple(active_groups) if active_groups is not None else None, bool(live_mode))
    cached = _sc_cache_get(key)
    if cached is not None:
        return cached
    raw = json.loads(reg_path.read_text(encoding='utf-8'))
    groups = raw.get('groups', {})
    selected = active_groups if active_groups is not None else tuple(groups.keys())
    catalog = {}
    for group in selected:
        items = groups.get(group, [])
        tags = []
        for item in items:
            if live_mode and item.get('id') in _LIVE_FORBIDDEN_HOST_IDS:
                continue
            tag = item.get('tag', '')
            pattern = item.get('pattern')
            tags.append(f'{tag} (正则:{pattern})' if pattern else tag)
        catalog[group] = tags
    return _sc_cache_set(key, catalog)


def _parse_vigilance_state(memory_text):
    pos_match = re.search(r'^徐承邺位置：([^\n]+)', memory_text or '', re.M)
    position = pos_match.group(1).strip() if pos_match else '外地'
    max_vig = 0
    max_disc = 0
    max_prob = 0
    details = []
    high_risk = []
    targets = {}
    for m in re.finditer(
        r'^徐承邺_([^\n：:]+)[：:]\s*警惕\s*(\d+)\s*\|\s*发现\s*(\d+)(?:\s*\|\s*发现几率\s*(\d+))?(?:\s*\|\s*动因[：:]\s*([^\n|]+))?',
        memory_text or '', re.M,
    ):
        who = m.group(1).strip()
        v, d = int(m.group(2)), int(m.group(3))
        p = int(m.group(4)) if m.group(4) is not None else 0
        reason = (m.group(5) or '').strip()[:48]
        max_vig = max(max_vig, v)
        max_disc = max(max_disc, d)
        max_prob = max(max_prob, p)
        targets[who] = {'vigilance': v, 'discovery': d, 'prob': p, 'reason': reason}
        if v >= 20 or d > 0:
            r_part = f'/{reason}' if reason else ''
            details.append(f'{who}(警惕{v}/发现{d}{r_part})')
        if p >= 70:
            high_risk.append(f'{who}(发现几率高危)')
    return {
        'position': position,
        'max_vigilance': max_vig,
        'max_discovery': max_disc,
        'max_prob': max_prob,
        'hot': details,
        'high_risk': high_risk,
        'targets': targets,
    }


def _mentions_vigilance(extra_text=''):
    return any(k in (extra_text or '') for k in ('徐承邺', '大哥', '哥哥', '查岗', '眼线', '监视', '被发现', '撞见'))


def _needs_vigilance_rules(state, memory_text='', extra_text=''):
    """Stable persistent-state gating for Zone 1 (protects Gemini 4 implicit KV cache from minor 0->5 jitter)."""
    vig = _parse_vigilance_state(memory_text)
    if vig['position'] != '外地' or vig['max_vigilance'] >= 20 or vig['max_discovery'] > 0:
        return True
    location = (state or {}).get('location', '')
    cast = (state or {}).get('cast', [])
    if location in ('徐家主宅', '市中心顶层公寓') and '徐承邺' in cast:
        return True
    if location == '徐家主宅' and '苏婉青' in cast:
        return True
    return False


def _needs_intimate_zone1(state, memory_text=''):
    """Session-stable persistent gating for narrative.intimate in Zone 1 (protects Gemini 4 implicit KV cache;
    transient single-turn arousal spikes inject intimate_craft_guide in Zone 2 without busting Zone 1)."""
    if bool(((state or {}).get('intimate') or {}).get('scene_active')):
        return True
    cast = (state or {}).get('cast', [])
    if not cast:
        return False
    panel_map = _parse_panel_map((state or {}).get('panels', []))
    buff_map = _parse_buffs_inline(memory_text)
    for name in cast:
        stats = panel_map.get(name, {})
        des_m = re.match(r'-?\d+', str(stats.get('欲望', '0')))
        dep_m = re.match(r'-?\d+', str(stats.get('堕落', '0')))
        shame_m = re.match(r'-?\d+', str(stats.get('羞耻', '100')))
        des = int(des_m.group(0)) if des_m else 0
        dep = int(dep_m.group(0)) if dep_m else 0
        shame = int(shame_m.group(0)) if shame_m else 100
        if des >= 60 or dep >= 15 or shame <= 80:
            return True
        if any('体液锁定' in (b.get('name', '') + b.get('effect', '')) for b in buff_map.get(name, [])):
            return True
    return False


def _needs_intimate_turn(text='', selected=None, operation_context=None, state=None):
    """Transient per-turn check for loading narrative.intimate in Zone 2 delta without touching Zone 1."""
    if bool(((state or {}).get('intimate') or {}).get('scene_active')):
        return True
    sel_text = selected.get('text', '') if isinstance(selected, dict) else ''
    op_blob = ''
    if isinstance(operation_context, dict):
        det = operation_context.get('detail')
        if isinstance(det, dict):
            kind = det.get('kind')
            if kind in ('inspect_deployed', 'keepsake_action'):
                return True
            if kind in ('use_item', 'transfer_item'):
                it = det.get('item') or {}
                op_blob = f"{it.get('name', '')} {it.get('desc', '')} {it.get('system_effect', '')}"
                if str(it.get('system_effect', '')).startswith('buff:'):
                    return True
    return bool(_INTIMATE_TURN_RE.search((text or '') + '\n' + (sel_text or '') + '\n' + op_blob))


def _load_intimate_body(root):
    for entry in _load_kb_entries(Path(root), '叙事判断'):
        if entry.get('enabled', True) is not True:
            continue
        if _entry_key(entry) == 'narrative.intimate':
            return _strip_kb_noise(entry['content'], mode='foreground')
    return ''


def _load_vigilance_body(root, *, protocol_mode='dual_stream_v2'):
    for entry in _load_kb_entries(Path(root), '叙事判断'):
        if entry.get('enabled', True) is not True:
            continue
        if _entry_key(entry) == 'narrative.vigilance':
            return _strip_kb_noise(entry['content'], mode='foreground', protocol_mode=protocol_mode)
    return ''


def _needs_pregnancy_rules(state, memory_text='', extra_text=''):
    panel_text = '\n'.join((state or {}).get('panels', []))
    if re.search(r'怀孕\s+True|内射\s+[1-9]\d*次|持续_体液锁定', (memory_text or '') + '\n' + panel_text):
        return True
    if re.search(r'内射|外射|精液|怀孕|受孕|危险期|体液锁定', extra_text or ''):
        return True
    return False


def compile_knowledge_rules(root, state, memory_text='', extra_text='', mode='foreground',
                            *, protagonist_style='faithful', protocol_mode='dual_stream_v2'):
    """Compile slimmed, state-gated knowledge rules from authoritative JSON sources."""
    root = Path(root)
    vig_active = _needs_vigilance_rules(state, memory_text)
    intimate_active = _needs_intimate_zone1(state, memory_text)
    preg_active = _needs_pregnancy_rules(state, memory_text, extra_text)
    blocks = []

    if mode in ('foreground', 'single'):
        for name in ('世界观类', '叙事判断'):
            for entry in _load_kb_entries(root, name):
                if entry.get('enabled', True) is not True:
                    continue
                key = _entry_key(entry)
                if key == 'narrative.vigilance' and not vig_active:
                    continue
                if key == 'narrative.intimate' and not intimate_active:
                    continue
                blocks.append({
                    'key': key,
                    'body': _strip_kb_noise(
                        entry['content'],
                        mode='foreground',
                        protagonist_style=protagonist_style,
                        protocol_mode=protocol_mode,
                    ),
                })

    if mode in ('settlement', 'single'):
        for entry in _load_kb_entries(root, '系统标签类'):
            if entry.get('enabled', True) is not True:
                continue
            key = _entry_key(entry)
            if key == 'sys.runtime_data':
                continue
            # In dual-stage settlement, keep sys.pregnancy & sys.vigilance always available so Stage 1
            # autonomous developments never hit a missing settlement rule and Stage 2 prompt cache stays stable.
            if mode == 'single':
                if key == 'sys.pregnancy' and not preg_active:
                    continue
                if key == 'sys.vigilance' and not vig_active:
                    continue
            blocks.append({
                'key': key,
                'body': _strip_kb_noise(entry['content'], mode='settlement', protocol_mode=protocol_mode),
            })

    return blocks


def compile_codex_runtime(root):
    """Deterministically slice runtime red-lines (Vol.0 §0~§3 & §5) from 全局执行法典.md."""
    codex_path = Path(root) / 'txt文件/全局执行法典.md'
    key = ('codex', _stat_sig(codex_path))
    cached = _sc_cache_get(key)
    if cached is not None:
        return cached
    raw = codex_path.read_text(encoding='utf-8')
    start = raw.find('# 【卷零：宿主主权宣言】')
    body = raw[start:] if start >= 0 else raw
    # Strip §4 old round V1 checklist, §6 abolished legacy rules, and bottom non-codex table.
    cut_v1 = body.find('### 4. 每回合硬验收')
    cut_backlash = body.find('### 5. 反噬条款')
    cut_old = body.find('### 6. 旧条废止声明')
    if cut_v1 >= 0 and cut_backlash > cut_v1:
        end_part = body[cut_backlash:cut_old] if cut_old > cut_backlash else body[cut_backlash:]
        body = body[:cut_v1].rstrip() + '\n\n' + end_part.strip()
    elif cut_old >= 0:
        body = body[:cut_old].rstrip()
    body = body.replace('禁止只写在 craft_note / SYSTEM_LOG。', '禁止省略或仅作后台概括。')
    body = re.sub(r'\n-\s*craft_note\s*可标注[^\n]*', '', body)
    body = re.sub(r'\n*正式连续入口entry_mode=live_interaction[^\n]*\n*', '\n\n', body)
    body = re.sub(r'### 0\. 卷零专用术语[\s\S]*?(?=### 1\. 轨 A)', '', body)
    body = re.sub(r'\n+---\n+', '\n\n', body)
    return _sc_cache_set(key, _clean_text(body))


def compile_characters(root, cast, references=(), *, include_host=True):
    """Preserve 100% of character persona/appearance/speech/Fish tags, stripping repeated meta markers."""
    entries = _load_kb_entries(root, '角色类')
    ref_names = [r['name'] if isinstance(r, dict) else str(r) for r in references]
    base = [*cast, *ref_names, '徐志北'] if include_host else [*cast, *ref_names]
    ordered = list(dict.fromkeys(base))
    cast_set = set(cast)
    result = []
    for name in ordered:
        found = [e['content'] for e in entries if '※索引key※ char.' + name in e.get('content', '')]
        if len(found) != 1:
            raise rr.RoundError('角色原文缺失或不唯一: ' + name)
        cleaned = _CHAR_LIVE_FOOTER_RE.sub('', found[0])
        cleaned = _INDEX_KEY_RE.sub('', cleaned)
        cleaned = _KINSHIP_DEADLINE_RE.sub('', cleaned)
        cleaned = _CROSS_MODULE_PTR_RE.sub('', cleaned)
        cleaned = _clean_text(cleaned)
        scope = 'present' if name in cast_set else ('host' if name == '徐志北' else 'referenced_background_offstage')
        result.append({'key': 'char.' + name, 'name': name, 'scope': scope, 'body': cleaned})
    return result


_TASK_WHITELIST_MAP = {
    '系统宿主': ('积分', '经验值', '商业嗅觉', '体力'),
    '沈知韫': ('好感',),
    '徐念薇': ('好感',),
    '苏婉青': ('好感',),
}


def _parse_panel_map(panels):
    panel_map = {}
    for line in panels or ():
        m = re.match(r'^\[([^\]]+)\]\s*(.*)$', line.strip())
        if not m:
            continue
        who = m.group(1).strip()
        stats = {}
        for seg in m.group(2).split('|'):
            seg = seg.strip()
            sm = re.match(r'^(\S+)\s+(.+)$', seg)
            if sm:
                stats[sm.group(1)] = sm.group(2).strip()
        panel_map[who] = stats
    return panel_map


def _extract_task_whitelist_values(panels):
    """Extract authoritative current numeric values for task whitelist attributes."""
    panel_map = _parse_panel_map(panels)
    result = {}
    for who, attrs in _TASK_WHITELIST_MAP.items():
        stats = panel_map.get(who, {})
        row = {}
        for attr in attrs:
            raw = stats.get(attr, '')
            m = re.match(r'^-?\d+', raw)
            if m:
                row[attr] = int(m.group(0))
        if row:
            result[who] = row
    return result


def _strip_active_task_from_memory(memory_text):
    """Strip 【任务状态】, 【商城与回响状态】, and 【商业情报与杠杆状态】 from dual_stream_v2 foreground projection."""
    if not memory_text:
        return memory_text
    cleaned = re.sub(r'\n*【任务状态】[\s\S]*?(?=\n【|\n▲ 第一层：|\Z)', '', memory_text)
    cleaned = re.sub(r'\n*【商城与回响状态】[\s\S]*?(?=\n【|\n▲ 第一层：|\Z)', '', cleaned)
    cleaned = re.sub(r'\n*【商业情报与杠杆状态】[\s\S]*?(?=\n【|\n▲ 第一层：|\Z)', '', cleaned)
    return cleaned.strip()


def _biz_sense_desc(biz):
    if biz >= 100:
        return '继承者视野(沈知韫叙事层完全信任，主动分享战略级情报)'
    if biz >= 60:
        return '成为变量(徐承邺视宿主为威胁；可动用商业杠杆)'
    if biz >= 30:
        return '被看见(沈知韫主动讨论非机密决策；苏婉青不再刻意隐瞒承邺动向)'
    if biz >= 10:
        return '商业入门(沈知韫商业对话不再视宿主为外行)'
    return '商业外行(初阶观察阶段)'


def compile_breakout_hint(memory_text):
    """Return a concise gated breakout hint ONLY when a counter hits threshold and is not cooling down."""
    if not memory_text:
        return None
    counters = rr._counters(memory_text)
    if counters.get('冷却_破局全局', 0) > 0:
        return None
    reason_labels = {
        '破局_日常冗余': '连续多轮停留在低起伏日常寒暄',
        '破局_模式重复': '同场景同角色互动模式重复',
        '破局_社交淤积': '高羞耻阶段社交试探出现淤积',
        '破局_张力淤积': 'B级张力多次积压尚未自然落点',
    }
    triggered = []
    for key, limit in rr.BREAKOUT_LIMITS.items():
        val = int(counters.get(key, 0))
        if val >= limit and int(counters.get('冷却_' + key, 0)) <= 0:
            triggered.append(f'{key}({val}/{limit}：{reason_labels.get(key, "节奏滞涩")})')
    if not triggered:
        return None
    return {
        'triggered_reasons': triggered,
        'allowed_accidents': [
            '家人来电或工作消息切入',
            '突发日常家务/送物打断',
            '门铃或宅内动静带来的短暂停顿',
            '物品意外滑落/泼洒等轻量物理意外',
            '天气/灯光/设备突发变化',
            '时间节点或行程提醒',
        ],
        'rule': '当前节奏已达到自然破局窗口：可在不违背玩家本轮意图与宿主主权的前提下，顺势引入1个克制的日常意外或外部切入打破停滞；严禁强行狗血、严禁擅自推进越界或凭空制造无依据目击。',
    }


def _parse_buffs_inline(memory_text):
    result = {}
    if not memory_text or '【当前持久化状态与BUFF】' not in memory_text:
        return result
    m = re.search(r'【当前持久化状态与BUFF】([\s\S]*?)(?=\n={10,}|\n【|\n▲ 第一层：|\Z)', memory_text)
    if not m:
        return result
    cur = None
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('▶'):
            cur = line.lstrip('▶').strip()
            result.setdefault(cur, [])
        elif cur and line.startswith('-'):
            bm = re.match(r'^-\s*\[([^\]]+)\]\s*剩余时效:\s*(\d+)回合\s*\(([^)]*)\)', line)
            if bm:
                result[cur].append({'name': bm.group(1).strip(), 'turns': int(bm.group(2)), 'effect': bm.group(3).strip()})
    return result


def _heroine_affection_desc(name, aff):
    if name == '沈知韫':
        if aff >= 95:
            return '对你几乎毫无保留地纵容与牵挂，心里把你摆在极重的位置'
        if aff >= 88:
            return '对你已生极深依赖与偏爱，话里行间藏着舍不得拒绝的软意，常先顺着你退半步'
        if aff >= 80:
            return '对你天然偏护信任、日常容错率极高（偶有冒失多半先替你找台阶或柔声包容），私下愿卸下几分董事长架子'
        if aff >= 70:
            return '对你亲近信任、日常容错率高，偶有小别扭多半轻声包容'
        if aff >= 55:
            return '对你温和关照、愿多聊几句近况，但长辈底线分明'
        if aff >= 40:
            return '对你礼貌照拂却留着明显分寸，谈话多停在面上'
        return '对你客套疏离、心存戒备，言行保持长辈威严与距离'
    if name == '徐念薇':
        if aff >= 90:
            return '卸下大部分尖刺与防备，对你极度坦诚且带着不肯明说的执拗偏爱'
        if aff >= 78:
            return '对你产生明显依赖与偏心，清冷外壳下藏着怕被敷衍的敏感与占有欲'
        if aff >= 65:
            return '私下已把你当自己人看待，虽仍嘴硬冷面，真有事会主动替你说话或分享画室近况'
        if aff >= 50:
            return '嘴上仍爱挑刺短答，但戒心已松，嫌弃之余会顺手留门或照料细节'
        if aff >= 35:
            return '对你维持礼貌距离、懒得客套，未熟稔前拒绝敷衍应酬'
        return '对你表面冷淡客套、耐性很低，话不投机便会冷言呛回或直接晾着你'
    if name == '苏婉青':
        if aff >= 86:
            return '心防与顾忌已彻底向你倾斜，甘愿站在你这边甚至暗中替你周全'
        if aff >= 78:
            return '对你心生强烈眷恋与信任，只在名分与婚姻处境上仍留着最后一层迟疑'
        if aff >= 65:
            return '对你颇为亲近依赖，常在不经意间卸下大房少奶奶的拘谨向你倾诉'
        if aff >= 50:
            return '对你已熟稔不少、偶露轻快俏皮，独处时会悄悄希望你多坐一会儿'
        if aff >= 35:
            return '对你礼貌周全中带着审慎试探与距离感，待人柔和却分寸极清'
        return '对你客气周全却藏着明显拘谨与防备，言谈事事留后路'
    return '态度平和自然'


def _heroine_shame_desc(shame):
    if shame >= 90:
        return '礼法与体面防线完好，任何越矩试探都会立刻触及她的自持与警觉'
    if shame >= 75:
        return '体面防线仍在，但近距试探时偶会出现一瞬迟疑或耳根发烫'
    if shame >= 55:
        return '端庄外壳已现松动，嘴硬掩饰与心虚破绽并存'
    if shame >= 35:
        return '羞赧防线大幅瓦解，理智克制与本能顺从剧烈拉扯'
    return '原有羞耻防线大半溃散，面对压迫极易顺从或失守'


def _heroine_depravity_desc(dep):
    if dep >= 60:
        return '深陷沉沦与私密依附，主动迎合与独占欲渐浓'
    if dep >= 30:
        return '陷入较深沉沦泥潭，理智克制已很难压住对你的身体记忆'
    if dep >= 10:
        return '已有轻微沉沦惯性，身体偶会先于理智放软'
    return ''


def _heroine_passive_desc(lv_num, *, remote=False):
    if lv_num <= 0:
        return ''
    if lv_num == 1:
        return '' if remote else '洞察之瞳生效(你极易捕捉她眼神躲闪、呼吸停顿与言不由衷的微妙破绽)'
    if lv_num == 2:
        eye = '；你亦能捕捉她细微的心虚破绽' if not remote else ''
        return f'认知欺诈滤镜生效(她潜意识会优先替你的反常靠近找合理解释{eye})'
    if lv_num == 3:
        eye = '且你能敏锐洞察她的防线裂口' if not remote else ''
        return f'疲劳诱导生效(焦灼、劳作或抗拒会令她心神更快倦怠松懈，潜意识仍易替你合理化{eye})'
    return '防线支配生效(你几乎一眼看穿她的虚实，高压之下她防线极易动摇溃散)'


def compile_state_qualitative_brief(state, memory_text='', include_tasks=False, include_points=False, intel_catalog=None):
    """Translate raw panel stats into human psychological director guidance without RPG number leakage."""
    panels = (state or {}).get('panels', [])
    panel_map = _parse_panel_map(panels)
    buff_map = _parse_buffs_inline(memory_text)
    micro_map = rr._current_micro(memory_text) if (memory_text and '【当前激活微状态】' in memory_text) else {}
    counters_map = rr._counters(memory_text) if memory_text else {}
    intel_state = sp.parse_intel_block(memory_text)
    intl = (state or {}).get('intimate') if isinstance((state or {}).get('intimate'), dict) else {}
    mech = (state or {}).get('mechanics') if isinstance((state or {}).get('mechanics'), dict) else {}
    mind_map = (state or {}).get('npc_mind') if isinstance((state or {}).get('npc_mind'), dict) else {}

    notes = []
    host = panel_map.get('系统宿主', {})
    if host:
        st = int(re.match(r'-?\d+', host.get('体力', '100')).group(0)) if re.match(r'-?\d+', host.get('体力', '100')) else 100
        st_desc = '精力偏低(注意耗神)' if st < 20 else ('精力尚可' if st < 55 else '精力充沛')
        biz = int(re.match(r'-?\d+', host.get('商业嗅觉', '0')).group(0)) if re.match(r'-?\d+', host.get('商业嗅觉', '0')) else 0
        charm = int(re.match(r'-?\d+', host.get('魅力', '70')).group(0)) if re.match(r'-?\d+', host.get('魅力', '70')) else 70
        ctier = ic.charm_tier_info(charm)
        charm_part = f'，个人气场：{ctier["name"]}（{ctier["brief"]}）' if charm >= 75 and ctier.get('brief') else ''
        hp = intl.get('host_phys') if isinstance(intl.get('host_phys'), dict) else {}
        h_des = int(hp.get('desire', 0) or 0)
        h_vig = int(hp.get('vigor', 100) if hp.get('vigor') is not None else 100)
        h_edge = int(hp.get('edging_streak', 0) or 0)
        h_fets = [f for f in (hp.get('fetishes') or []) if isinstance(f, str) and f.strip()]
        phys_parts = []
        if h_des >= 85 and h_edge >= 3:
            phys_parts.append(f'宿主极限控场(已连蓄{h_edge}轮，侵略张力极强且耐力承压，严禁代打擅自射精)')
        elif h_des >= 85:
            phys_parts.append('宿主欲望蓄满临界(边缘控场，严禁代打擅自射精，须由玩家自主决断克制或释放)')
        elif h_des >= 60:
            phys_parts.append('宿主欲火灼烫(呼吸沉热、侵略感抬升)')
        elif h_des >= 30:
            phys_parts.append('宿主情欲渐起')
        if intl.get('scene_active') or h_vig < 80:
            if h_vig < 15:
                phys_parts.append('亲密耐力见底(体能透支动作略沉，宜稍作缓冲或温存收束)')
            elif h_vig < 45:
                phys_parts.append('亲密耐力偏低(体能消耗明显)')
            else:
                phys_parts.append('亲密耐力充沛(护航中，日间体力锁底不中断)')
        if h_fets:
            phys_parts.append('显露癖好：' + '、'.join(h_fets[:4]))
        phys_clause = ('；' + '；'.join(phys_parts)) if phys_parts else ''
        extra = f'，积分{host.get("积分", "0")}，经验值{host.get("经验值", "0")}' if include_points else ''
        biz_note = f'{_biz_sense_desc(biz)}·深局棋手' if biz >= 80 else _biz_sense_desc(biz)
        notes.append(f'宿主状态：{st_desc}{charm_part}，商战眼界[{biz_note}]{extra}{phys_clause}。')

    if intel_state['held'] or int(intel_state.get('leverage_charges', 0) or 0) > 0:
        name_map = {it['id']: it['name'] for it in (intel_catalog or {}).get('items', [])}
        held_labels = [name_map.get(iid, iid) for iid in intel_state['held']]
        lev_parts = []
        if intel_state.get('leverage_armed'):
            lev_name = name_map.get(intel_state['leverage_armed'], intel_state['leverage_armed'])
            lev_parts.append(f'已暗中备妥筹码「{lev_name}」作商业牵制（仅自然落于压迫感或底气，禁直呼机制词）')
        if int(intel_state.get('leverage_charges', 0) or 0) > 0:
            lev_parts.append(f'已展开商业牵制底气（余{int(intel_state["leverage_charges"])}次压迫护航）')
        lev_note = ('；' + '；'.join(lev_parts)) if lev_parts else ''
        if held_labels:
            notes.append(f'宿主私下掌握的未动用商业线索：{"、".join(held_labels)}（仅宿主知晓，玩家未亮牌前NPC不可知晓{lev_note}）。')
        elif lev_parts:
            notes.append(f'宿主商业牵制态势：{"；".join(lev_parts)}（仅自然化入气场，禁直呼机制词）。')

    def _int_stat(raw_val, default=0):
        m = re.match(r'-?\d+', str(raw_val or ''))
        return int(m.group(0)) if m else default

    su_unlocked = bool(mech.get('su_affection_85_unlocked'))
    dep_caps = mech.get('depravity_unlocked_caps') if isinstance(mech.get('depravity_unlocked_caps'), dict) else {}
    attire_map = intl.get('attire') if isinstance(intl.get('attire'), dict) else {}
    traces_map = intl.get('traces') if isinstance(intl.get('traces'), dict) else {}
    sess_orgasms = intl.get('session_orgasms') if isinstance(intl.get('session_orgasms'), dict) else {}
    cast = (state or {}).get('cast', [])
    location = (state or {}).get('location', '')

    def _compile_heroine_line(name, *, remote=False):
        stats = panel_map.get(name, {})
        if not stats:
            return ''
        aff = _int_stat(stats.get('好感', '0'), 0)
        shame = _int_stat(stats.get('羞耻', '100'), 100)
        dep = _int_stat(stats.get('堕落', '0'), 0)
        desire = _int_stat(stats.get('欲望', '0'), 0)
        orgasm = _int_stat(stats.get('高潮', '0'), 0)
        npc_st = _int_stat(stats.get('体力', '100'), 100)
        passive = stats.get('被动', 'Lv.0')
        lv_m = re.search(r'Lv\.(\d+)', passive)
        lv_num = int(lv_m.group(1)) if lv_m else 0

        core_parts = [_heroine_affection_desc(name, aff), _heroine_shame_desc(shame)]
        dep_desc = _heroine_depravity_desc(dep)
        if dep_desc:
            core_parts.append(dep_desc)
        aff_trend = int(((mind_map.get(name) or {}).get('aff_delta_last') or 0))
        if aff_trend >= 3:
            core_parts.append('近来对你态度比先前明显松动热络了些')
        elif aff_trend >= 1:
            core_parts.append('近来对你态度比先前略微缓和了半分')
        elif aff_trend <= -3:
            core_parts.append('刚因越界或摩擦心生芥蒂，态度明显收冷')
        elif aff_trend <= -1:
            core_parts.append('刚才略有不快，语气比平日收紧了些')

        flags = []
        pas_desc = _heroine_passive_desc(lv_num, remote=remote)
        if pas_desc:
            flags.append(pas_desc)

        char_buffs = buff_map.get(name, [])
        if char_buffs:
            b_desc = '、'.join(f'{b["name"]}(剩{b["turns"]}轮:{b["effect"]})' for b in char_buffs)
            flags.append('生效持久化状态：' + b_desc)

        if desire >= 85:
            flags.append('欲望处于高位滞留(呼吸与克制极难维持)')
        elif desire >= 80:
            flags.append('欲望触及高位瓶颈(需更高心理压迫或诱因方能突破)')
        elif desire >= 70:
            flags.append('欲望明显躁动(情绪易失衡空耗)')
        elif desire >= 40:
            flags.append('情欲已起微澜(肢体与声息敏锐度抬升)')
        if orgasm >= 70:
            flags.append(f'临近生理峰值(高潮累积{orgasm}%)')
        elif orgasm >= 35:
            flags.append(f'生理快感持续累积中(高潮进度{orgasm}%)')
        s_org = int(sess_orgasms.get(name, 0) or 0)
        if s_org >= 1:
            flags.append(f'本场已达高潮{s_org}次(余韵敏锐且耐受下降)')

        if npc_st <= 15:
            flags.append('身心透支进入生理断电期(未获玩家括号强行授权前严禁继续深/重度推进，须转入照料、低声安抚或余韵收束)')
        elif npc_st < 40:
            flags.append('神态略显疲倦，支撑克制更耗心力')

        cap_val = int(dep_caps.get(name, 30) or 30)
        if dep >= cap_val - 3 and cap_val < 100 and dep > 0:
            flags.append('心理沉沦触及阶段瓶颈(须清醒主动顺从或重大心理破口方能更进一步)')
        c_streak_raw = (mech.get('c_streak') or {}).get(name) if isinstance(mech.get('c_streak'), dict) else None
        c_streak = int((c_streak_raw or {}).get('count', 0) or 0) if isinstance(c_streak_raw, dict) else int(c_streak_raw or 0)
        if c_streak >= 1 and not remote:
            flags.append(f'近轮连续高压接触({c_streak}轮，重复同套路易钝化，宜换节奏/换区/言语心理变奏)')

        att = attire_map.get(name) if isinstance(attire_map.get(name), dict) else {}
        att_state = str(att.get('state') or 'neat')
        att_outfit = str(att.get('outfit') or 'default')
        att_gifts = list(att.get('gifted_items') or [])
        if att_state != 'neat' or att_outfit != 'default':
            st_lbl = save_store.ATTIRE_LABELS.get(att_state, att_state)
            outfit_part = f'穿搭={att_outfit}，' if att_outfit != 'default' else ''
            flags.append(f'当前衣着：{outfit_part}{st_lbl}')
        if att_gifts:
            flags.append(f'已获赠私密穿戴礼盒：{"、".join(att_gifts)}（居家/私密情境可自然换穿或作为试探引子）')

        tr_list = traces_map.get(name) if isinstance(traces_map.get(name), list) else []
        if tr_list:
            tr_txt = '、'.join(
                f"{t.get('kind', '')}[{'显性' if t.get('visible') else '隐性'}]({t.get('desc', '')})"
                for t in tr_list[:4] if isinstance(t, dict) and t.get('kind')
            )
            if tr_txt:
                flags.append('身体留痕/余韵：' + tr_txt)

        bd_all = intl.get('body_dev') if isinstance(intl.get('body_dev'), dict) else {}
        h_bd = bd_all.get(name) if isinstance(bd_all.get(name), dict) else {}
        sig_z = save_store.HEROINE_SIGNATURE_ZONES.get(name)
        dev_items = []
        for z in save_store.BODY_ZONES:
            sc = int(h_bd.get(z, 0) or 0)
            if sc >= 20:
                lv = ic.body_dev_level(sc)
                star = '★' if z == sig_z else ''
                dev_items.append(f"{save_store.BODY_ZONE_LABELS.get(z, z)}{star}({ic.BODY_DEV_LEVEL_LABELS.get(lv, '')})")
        if dev_items:
            sig_lbl = save_store.BODY_ZONE_LABELS.get(sig_z, '')
            flags.append(f'身体熟悉度(招牌敏感带={sig_lbl})：' + '、'.join(dev_items))
        elif intl.get('scene_active') and sig_z:
            sig_lbl = save_store.BODY_ZONE_LABELS.get(sig_z, '')
            flags.append(f'招牌敏感带={sig_lbl}(针对触碰更易破防升温)')

        if not remote:
            ms = micro_map.get(name) or {}
            if ms.get('momentary_ease'):
                flags.append('刚经历短暂缓和，神色戒备略松但底线仍在')
            if ms.get('confusion_debt'):
                flags.append('心底留有未说破的局促与自我辩解余波')
            if ms.get('residual_tension'):
                flags.append('刚经历高压接触，呼吸与肢体仍留余韵张力')

        if name == '苏婉青':
            if not (su_unlocked or aff > 85) and aff >= 75:
                flags.append('心底仍对大房名分与徐承邺留着最后一层顾忌，尚未彻底交底')
            su_exposed = 'INTEL-002' in (mech.get('secrets_unlocked') or ())
            if su_exposed:
                flags.append('眼线身份已被宿主当面揭穿(心虚受制，不再主动替徐承邺盯梢，开启私下周旋/妥协线)')
            elif not remote and location == '徐家主宅' and (aff < 70 or shame > 80):
                flags.append('心底仍把丈夫立场摆在前头，回宅见闻事后多半会顺口告知徐承邺')
        phys = ((state or {}).get('physiology') or {}).get(name) or {}
        cp_cnt = int(phys.get('creampie_count', _int_stat(stats.get('内射', '0'), 0)) or 0)
        if cp_cnt == 1:
            flags.append('生涯首次内射印记已刻下(对亲密失控怀有深刻余悸与身体记忆)')
        elif cp_cnt >= 2:
            flags.append(f'已有多次亲密失守经历(身体对宿主气息形成隐秘惯性)')
        if stats.get('怀孕') == 'True' or phys.get('pregnancy_stage') == 'confirmed':
            flags.append('已确诊怀孕(孕期易倦、体态敏感与伦理身份反差并存)')
        elif phys.get('pregnancy_stage') == 'latent':
            flags.append('早孕潜伏微兆(尚未知情确诊，偶现嗜睡/晨起微恶心/小腹微胀)')
        elif intl.get('scene_active') or desire >= 45 or shame <= 75 or dep >= 15:
            c_phase = phys.get('cycle_phase')
            if not c_phase:
                cur_day = int(((((state or {}).get('progression') or {}).get('runtime') or {}).get('clock') or {}).get('day') or 1)
                c_phase = ic.determine_cycle_phase(name, cur_day)
            if c_phase == '危险期':
                flags.append('生理周期正值敏感危险期')
            elif c_phase == '安全期' and (desire >= 55 or shame < 80):
                flags.append('生理周期处于安全期')
        if int(phys.get('masturbation_trace', 0) or 0) > 0:
            flags.append('自渎余韵(近期曾暗中自慰泄欲，面对宿主易心虚闪躲或腿根发软)')
        if int(phys.get('unrelieved_streak', 0) or 0) >= 1:
            flags.append('高欲久未纾解，气息与心神暗藏燥意')
        prefix = f'【远程监控对象态势】{name}' if remote else f'{name}当下心理与边界'
        core_txt = '；'.join(core_parts)
        if flags:
            return f'{prefix}：{core_txt}（{"；".join(flags)}）。'
        return f'{prefix}：{core_txt}。'

    vig_pub = (state or {}).get('vigilance') if isinstance((state or {}).get('vigilance'), dict) else {}
    vig_targets_pub = vig_pub.get('targets') if isinstance(vig_pub.get('targets'), dict) else {}
    for name in cast:
        if name == '徐承邺':
            place_label = location or '徐家主宅'
            top_v = 0
            top_stage_lbl = '无察'
            top_reason = ''
            for _tinfo in vig_targets_pub.values():
                if isinstance(_tinfo, dict):
                    _tv = int(_tinfo.get('vigilance', 0) or 0)
                    if _tv >= top_v:
                        top_v = _tv
                        top_stage_lbl = str(_tinfo.get('stage_label') or top_stage_lbl)
                        if _tinfo.get('reason'):
                            top_reason = str(_tinfo['reason'])
            if top_v >= 65:
                x_mood = f'审视紧绷({top_stage_lbl}期，礼貌掌控欲下暗藏逼问锋芒)'
            elif top_v >= 40:
                x_mood = f'旁敲侧击({top_stage_lbl}期，不动声色试探动向与口风)'
            elif top_v >= 20:
                x_mood = f'略起疑云({top_stage_lbl}期，偶有若无其事的追问)'
            else:
                x_mood = '情绪沉稳克制，维持长兄与掌权者礼貌掌控欲'
            if top_reason:
                x_mood += f'；近期心结：{top_reason}'
            notes.append(f'徐承邺当轮态势：已抵达{place_label}且真实在场（{x_mood}；可合法对白与动作；按监视态势、礼貌掌控欲与信息差边界推演，严禁直呼数值）。')
            continue
        line = _compile_heroine_line(name, remote=False)
        if line:
            notes.append(line)

    # 空间隐私、房间级同席与女主间暗流态势
    priv = str(intl.get('privacy') or 'open_public')
    sub_loc = str(intl.get('sub_location') or '').strip()
    p_actors = [a for a in (intl.get('present_actors') or []) if a in cast]
    noise = int(intl.get('noise_risk') or 0)
    ih_map = intl.get('inter_heroine') if isinstance(intl.get('inter_heroine'), dict) else {}
    ih_hot = [
        f'{pair}={save_store.INTER_HEROINE_LABELS.get(int(lv), str(lv))}'
        for pair, lv in ih_map.items() if int(lv or 0) > 0
    ]
    if intl.get('scene_active') or priv != 'open_public' or sub_loc or noise > 0 or (p_actors and set(p_actors) != set(cast)) or ih_hot:
        sp_parts = [f'隐私={save_store.PRIVACY_LABELS.get(priv, priv)}']
        if sub_loc:
            sp_parts.append(f'当前子区={sub_loc}')
        if p_actors and set(p_actors) != set(cast):
            offroom = [c for c in cast if c not in p_actors]
            sp_parts.append(f'本房间在场={"、".join(p_actors)}（同栋楼门外/另室：{"、".join(offroom)}，须守信息差与隔墙听觉张力）')
        if intl.get('scene_active'):
            sp_parts.append(f'亲密进行态(第{int(intl.get("session_beats", 0) or 0) + 1}拍，按慢燃节奏连贯推进)')
        if noise > 0:
            risk_tag = '【高危：随时可能被门外/同席察觉】' if noise >= 60 else '须压低呼吸与动静'
            sp_parts.append(f'声响暴露压迫={noise}%({risk_tag})')
        if ih_hot:
            sp_parts.append('女主间暗流：' + '、'.join(ih_hot))
        notes.append('空间与私密态势：' + '；'.join(sp_parts) + '。')

    # 私密贴身收藏态势（仅持有时注入，守知情隔离）
    ks_list = [k for k in (intl.get('keepsakes') or []) if isinstance(k, dict) and k.get('name')]
    if ks_list:
        here_ks = [k for k in ks_list if k.get('owner') in cast] or ks_list[:3]
        ks_txt = '、'.join(
            f"{k.get('id', '')}·{k.get('owner', '')}的{k.get('name', '')}"
            f"[{save_store.KEEPSAKE_CONDITION_LABELS.get(k.get('condition', ''), '余香')}/{'失主已知' if k.get('owner_aware') else '失主未觉'}]"
            for k in here_ks[:4]
        )
        notes.append(f'宿主私密珍藏（随身暗藏，未主动出示前严禁失主凭空撞破；若偷藏且失主在场可自然流露一丝丢件微惑）：{ks_txt}。')

    # 远程监控对象态势（inspect_deployed 激活时透传远程地点女主真实生理/余韵/衣着）
    remote_targets = [r for r in ((state or {}).get('remote_vitals_targets') or []) if r in save_store.HEROINES and r not in cast]
    for rname in remote_targets:
        rline = _compile_heroine_line(rname, remote=True)
        if rline:
            notes.append(rline)

    vig = _parse_vigilance_state(memory_text)
    if vig['position'] != '外地' or vig['max_vigilance'] >= 20 or vig['max_discovery'] > 0 or vig['max_prob'] >= 70:
        detail = '、'.join(vig['hot']) if vig['hot'] else '低警惕'
        risk_clause = ''
        if vig['max_prob'] >= 70:
            risk_targets = '、'.join(vig['high_risk']) if vig['high_risk'] else '在场目标'
            risk_clause = f'；【高危暴露压迫】{risk_targets}发现几率达高危线，本轮须按将被发现/逼近查岗推进，不得写侥幸蒙混'
        szy_v = (vig['targets'].get('沈知韫') or {}).get('vigilance', 0)
        szy_d = (vig['targets'].get('沈知韫') or {}).get('discovery', 0)
        blind_clause = ''
        if 0 < szy_v < 45 and szy_d < 3:
            blind_clause = '；徐承邺对母亲存在伦理盲区（警惕<45只疑志北讨好母亲争家业，不疑母子私情）'
        notes.append(f'监视态势：徐承邺位置={vig["position"]}，关注={detail}{risk_clause}{blind_clause}（未实际目击/来电/第三方外传前不凭数值凭空造实锤）。')
    else:
        notes.append('监视态势：徐承邺在外地，警惕平静。')

    if include_tasks:
        tasks = (state or {}).get('tasks') or {}
        if tasks.get('current'):
            notes.append(f'当前委托（只读不驱动剧情，严禁围着任务编造桥段）：{tasks["current"]}')
        if tasks.get('pending_item'):
            notes.append(f'待领奖励道具（前端支持零体力一键领取）：{tasks["pending_item"]}')
    return '\n'.join(notes)


MAX_PLAYER_DIALOGUE_PER_TURN = 3


CUSTOM_RULES_POSITIONS = ('append', 'prepend')


def normalize_protagonist_style(value):
    return 'silent' if str(value or '').strip().lower() == 'silent' else 'faithful'


def normalize_custom_rules_position(value):
    return 'prepend' if str(value or '').strip().lower() == 'prepend' else 'append'


def normalize_custom_rules_text(value):
    if not isinstance(value, str):
        return ''
    return value.replace('\r\n', '\n').replace('\r', '\n')


def _apply_custom_rules_section(base_text, cfg, *, enabled_key, position_key, text_key, header, footer):
    if not isinstance(cfg, dict):
        return base_text
    if enabled_key in cfg or text_key in cfg or position_key in cfg:
        enabled = bool(cfg.get(enabled_key, False))
        position = normalize_custom_rules_position(cfg.get(position_key, 'append'))
        body = normalize_custom_rules_text(cfg.get(text_key, '')).strip()
    else:
        enabled = bool(cfg.get('enabled', False))
        position = normalize_custom_rules_position(cfg.get('position', 'append'))
        body = normalize_custom_rules_text(cfg.get('text', '')).strip()
    if not enabled or not body:
        return base_text
    block = f'{header}\n{body}\n{footer}'
    if position == 'prepend':
        return _clean_text(f'{block}\n\n{base_text}')
    return _clean_text(f'{base_text}\n\n{block}')


def build_zone0_global(root, mode='dual_stream_v2', protagonist_style='faithful', custom_rules=None):
    """Build globally frozen Zone 0 system prompt (injected via Operit native system prompt hook)."""
    style = normalize_protagonist_style(protagonist_style)
    root_p = Path(root)
    base_cache_key = (
        'zone0_base',
        mode,
        style,
        _stat_sig(root_p / 'txt文件/全局执行法典.md'),
        _stat_sig(root_p / 'txt文件/知识库/世界观类.json'),
        _stat_sig(root_p / 'txt文件/知识库/叙事判断.json'),
        _stat_sig(root_p / 'txt文件/知识库/角色类.json'),
    )
    base_zone0 = _sc_cache_get(base_cache_key)
    if base_zone0 is None:
        codex = compile_codex_runtime(root)
        world_rules = compile_knowledge_rules(
            root, {}, '', '', mode='foreground', protagonist_style=style, protocol_mode=mode,
        )
        # Only include constant/global world & narrative rules in Zone 0 (vigilance & intimate are gated on demand).
        global_kb = '\n\n'.join(
            item['body'] for item in world_rules
            if item['key'] not in ('narrative.vigilance', 'narrative.intimate')
        )
        host_chars = compile_characters(root, [], [], include_host=True)
        host_section = (
            '【主角全局锚点（跨场景冻结）】\n'
            + f'<<< {host_chars[0]["key"]} ({host_chars[0]["scope"]}) >>>\n{host_chars[0]["body"]}'
            if host_chars else ''
        )

        if mode == 'dual_stream_v2':
            if style == 'faithful':
                protagonist_rule = (
                    '   - 主角具身在场（忠实演绎）：用 [A:徐志北] / [N] 自然承接玩家本轮行动，允许输出 1～3 句贴合原意图的简短 [D:徐志北] 口语（建议≤40字、默认静音可在语音设置开启主角配音，正文禁任何声学/XML标签）；'
                    '称呼人物须严格沿用玩家本轮原输入称谓（不把母亲/姐姐/嫂子擅自改叫名字），括号内无声/眼神示意不擅自改写为喊话；若玩家输入已有直接引语则保留原意，不代增新决定、新承诺、烈度升级或未授权反派滤镜。\n'
                )
                action_line_rule = (
                    '   [A:角色姓名] 归属明确的具体动作（在场人物或徐志北；禁任何声学/XML标签；高羞耻身体露馅时可用 ｛表面端庄｜本能破绽｝）\n'
                )
                dialogue_line_rule = (
                    '   [D:角色姓名] 纯开口台词（仅限在场cast或≤3句忠实 [D:徐志北]；禁场外对白、禁外层引号“...”及第三人称动作旁白；三女主可按 narrative.dialogue_tts 使用中文/英文导演提示 [...]、句内呼吸 [break]/[sigh] 与词级标签 <whisper>/<soft>/<emphasis>/<slow>/<forceful>，及必要 ｛表层｜潜台词｝）\n'
                )
            else:
                protagonist_rule = (
                    '   - 主角具身在场（仅动作感官）：严禁输出 [D:徐志北]，以 [A:徐志北] / [N] 自然呈现动作、间接追问与体感，不把主角写成隐身摄像机。\n'
                )
                action_line_rule = (
                    '   [A:角色姓名] 归属明确的具体动作（在场人物或徐志北；玩家提问亦用 [A:徐志北]/[N] 间接表达，严禁 [D:徐志北]；禁任何声学/XML标签；高羞耻身体露馅可用 ｛表面端庄｜本能破绽｝）\n'
                )
                dialogue_line_rule = (
                    '   [D:角色姓名] 纯开口台词（严格限在场cast，严禁 [D:徐志北] 或场外对白；禁外层引号“...”及第三人称动作旁白；三女主可按 narrative.dialogue_tts 使用导演提示 [...]、句内停顿与词级标签 <whisper>/<soft>/<emphasis>/<slow>/<forceful>，及必要 ｛表层｜潜台词｝）\n'
                )
            protocol = (
                '【前台演播协议 · 文字沉浸流式剧场（dual_stream_v2）】\n'
                '你是深渊天平前台叙事演播者，专注真实活人对话、人物主体性、自然节奏、信息差与 Drama 3 导演声演；'
                '数值与结算交由后台完成，正文禁输出 JSON、面板数值、事件标签、SYSTEM_LOG 或审计表。\n'
                '1. 创作与流转：\n'
                '   - 篇幅由戏核自然呼吸决定（单行防呆上限4000字）：重场写透，日常快节奏亦可干脆短答；一幕一位移（变完回不去），打破礼貌寒暄循环；动作与对白自由穿插，快节奏交锋可连续多行 [D] 零动作直抛，不必机械一动一言。\n'
                + protagonist_rule +
                '   - 外部变数（仅当 delta 携带 surprise_directive 时生效）：将其化作真实客观动静织入并触发反应；thread_spark 顺着锚点融合双词意象；offstage_clock 且 owner_in_scene=false 时禁瞬移现身或输出 [D:姓名]，只经物件/转述浮现；若携带 choice_hook_guide（女主突发意外/微距契机），须在需要主角伸手或表态的临界半拍定格，段末 PROMPT 与 B/C 必须直接锚定该意外作为切入点（B 合法近身协助解围、C 借势压近试探，禁跳回无关寒暄）；避开 banned_channels，禁提机制词，不代作应对决定。\n'
                '   - 特定时刻微回响（仅当 delta 携带 milestone_echo 时生效）：自然间隙用 1 句克制氛围或内心轻顿带过，禁提系统/任务/商城/积分词，不扭转玩家意图。\n'
                '2. 逐行流式格式（禁 JSON/代码块/列表符/中文前缀“旁白：/对白：”，每行直接以英文方括号标签起头）：\n'
                '   [N] 旁白叙述（单行≤4000字，禁任何声学或 XML 标签）\n'
                + action_line_rule
                + dialogue_line_rule +
                '   格式示意（仅示语法，禁照抄内容）：\n'
                '   [A:沈知韫] 她把对账单往桌角一推，纸边撞到茶碟轻轻一响。\n'
                '   [D:沈知韫] [低声克制，语速微缓] 这么晚还没睡？<soft>手怎么这么凉。</soft>\n'
                '   段末三轴抉择块（正文结束另起完整单行 ---DECISION---，三条选项须实质互异）：\n'
                '   ---DECISION---\n'
                '   PROMPT: 点明本幕刚浮现的具体变数或两难（≤300字，禁空话）\n'
                '   A: 或 A[MOVE:登记地点]: 日常互动（5体力，中性无接触）— 信息撬动/暗线换轨或自然离场转场（≤500字）\n'
                '   B: 或 B[MOVE:登记地点]: 社交接触（10体力，礼仪接触）— 破冰试探或借突发意外合法近身解围（≤500字）\n'
                '   C: 或 C[MOVE:登记地点]: 主动行为（15体力）— 破局亮牌/正面戳破/借意外或成熟氛围主动压近推进（≤500字）\n'
                '   转场标记：选项实质包含离开当前地点前往 delta.available_destinations 中另一开放地点时，须在字母后标 [MOVE:登记地点]（禁填当前或未开放地点）。\n'
                '3. 只读工具边界：精编设定与状态已由程序冻结交付，勿重读规则文件；仅当玩家追问极早旧史时按 delta 许可路径行号调用 read_file_part 补查。不写文件、不执行命令。'
            )
        else:
            single_player_rule = (
                'messages中每幕须含徐志北具身动作与五感承接，忠实演绎模式下允许最多3句严格贴合玩家原意图的简短dialogue(speaker=="徐志北"，建议≤40字、禁任何声学/XML标签、称呼沿用玩家原输入且禁将无声眼神示意改写喊话、禁新增决定或烈度升级)，'
                if style == 'faithful'
                else 'messages中严禁出现kind=="dialogue"且speaker=="徐志北"（玩家追问用kind=="action",speaker=="徐志北"或narration间接动作表达，每幕至少2处主角具身动作），'
            )
            protocol = (
                '【单阶段精简协议（single_prefix_v2）】\n'
                '你是深渊天平正式互动生成者。系统提示词已由程序完整冻结交付全局规则、当前在场人物设定与关系知情边界；'
                '每轮user消息仅提供最新增量状态、记忆与玩家行动。不要重读已交付设定，仅确需极早旧史时按许可精确行号补查。\n'
                '最终只输出单个合法裸JSON对象，键恰为当前delta.output_contract所列（messages/decision/operation/handoff/checks/resolution）。'
                + single_player_rule +
                'dialogue.text只写纯台词禁混入第三人称动作旁白或外层引号。'
                '无操作operation、无待处理handoff、无任务resolution.task、无睡眠起点resolution.sleep.start及无对象conditions.npc明确写空字符串""（decision.options内无转场时省略operation键，切勿写operation:""），不得省略顶层值。'
                '普通付费action必须交完整7字段conditions；固定A/B/C不得重新判档（日常态固定A/B禁C烈度_*；亲密进行态A禁C烈度_*、B允许C烈度_轻度/中度）；host_events对象固定为“系统宿主”；vigilance_events.target只能填被徐承邺监视的人（沈知韫/苏婉青/徐念薇/徐志北），严禁填徐承邺本人；「首次/同质化免疫_回合2/3/小憩限次/空耗惩罚/生理周期」由后端确定性派生拦截；不写文件、不执行命令。\n'
                'memory 填 {"fact":"<=160字新因果事实或空串","anchor_ops":[],"chronicle_digest":""}：长期重要承诺/关系转折用 anchor_ops(add/update/resolve) 原子维护；仅当 delta 携带 chronicle_archive_request 时交 chronicle_digest。\n'
                '进行中任务严禁驱动剧情；仅当delta携带milestone_echo时允许1句低侵入氛围轻顿且禁提系统词。'
                '若cost_preview.kind=="action"且tasks.current为空或status=="已完成"，结合task_whitelist_current按task_schema六键续接新任务（value严格大于当前值）；进行中或SYSTEM时resolution.task写""。'
                '仅当玩家在正文中明确亮牌动用 delta.held_intel 中某条情报时才填 resolution.intel_used；action回合可选填 resolution.director_echo 维护未完线头、暗钟与角色心绪印象(mind_updates)，严禁编造。'
            )

        parts = [protocol, codex, global_kb]
        if host_section:
            parts.append(host_section)
        base_zone0 = _sc_cache_set(base_cache_key, _clean_text('\n\n'.join(parts)))
    return _apply_custom_rules_section(
        base_zone0,
        custom_rules,
        enabled_key='custom_rules_enabled',
        position_key='custom_rules_position',
        text_key='custom_rules_text',
        header='【玩家自定义系统级规则（主模型前景演播最高偏好覆写；严禁违背底层输出格式标签、在场发言白名单与未解锁知情红线）】',
        footer='【自定义系统级规则结束】',
    )


def build_zone1_scene(root, state, cast, references=(), memory_text='', extra_text='',
                      mode='dual_stream_v2', protagonist_style='faithful', *, frozen_flags=None):
    """Build scene-scoped semi-static Zone 1 system prompt (byte-invariant across turns in same scene/session)."""
    style = normalize_protagonist_style(protagonist_style)
    chars = compile_characters(root, cast, references, include_host=False)
    rels = compile_relationships(root, cast, references)
    location = (state or {}).get('location', '')
    offstage = [c['name'] for c in chars if c['scope'] == 'referenced_background_offstage']
    if style == 'faithful' and cast:
        speaker_line = (
            f'实际在场可发言白名单(dialogue.speaker)：{json.dumps(cast, ensure_ascii=False)}'
            '（忠实演绎模式下另允许 ≤3 句贴合玩家原意图的简短 [D:徐志北]）'
        )
    else:
        speaker_line = (
            f'实际在场可发言白名单(dialogue.speaker 仅限此列表，严禁 [D:徐志北])：{json.dumps(cast, ensure_ascii=False)}'
        )

    sections = [
        '【当前场景冻结锚点（同地同阵容不变）】\n'
        f'当前地点：{location}\n'
        f'{speaker_line}\n'
        f'仅背景提及(不在场，严禁写成dialogue或当场动作)：{json.dumps(offstage, ensure_ascii=False)}',
    ]
    if chars:
        sections.append(
            '【在场及关联人物完整设定】\n' + '\n\n'.join(
                f'<<< {c["key"]} ({c["scope"]}) >>>\n{c["body"]}' for c in chars
            )
        )
    sections.append(
        '【关系、知情隔离与称谓编译表】\n' + json.dumps(rels, ensure_ascii=False, separators=(',', ':'))
    )

    # Zone 1 gating relies ONLY on session-frozen flags (or persistent state when no frozen_flags provided)
    # so KV prefix cache stays 100% byte-identical across turns in the same scene session.
    if isinstance(frozen_flags, dict):
        vig_on = bool(frozen_flags.get('vig'))
        intl_on = bool(frozen_flags.get('intl'))
    else:
        vig_on = _needs_vigilance_rules(state, memory_text)
        intl_on = _needs_intimate_zone1(state, memory_text)

    if vig_on:
        vig_body = _load_vigilance_body(root, protocol_mode=mode)
        if vig_body:
            sections.append('【本场激活监视叙事裁决】\n' + vig_body)

    if intl_on:
        intimate_body = _load_intimate_body(root)
        if intimate_body:
            sections.append('【本场激活亲密与高压肢体描写技法】\n' + intimate_body)

    if mode == 'single_prefix_v2':
        sys_rules = compile_knowledge_rules(root, state, memory_text, extra_text, mode='settlement', protocol_mode=mode)
        catalog = compile_event_catalog(root, live_mode=True)
        sections.append('【系统机制与事件标签白名单（仅用于resolution打标，严禁口算分或写进台词）】\n'
                        + '合法事件标签：' + json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + '\n\n'
                        + '\n\n'.join(item['body'] for item in sys_rules))

    return _clean_text('\n\n'.join(sections))


def _build_available_destinations(root, current_location, weekday, clock):
    """Build compact public-knowledge destination hints (strictly no private/secret coordinate leaks)."""
    cfg_path = Path(root) / 'txt文件/互动运行配置.json'
    locations = ['徐家主宅', '公司', '大学', '市中心顶层公寓', '工作室']
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding='utf-8'))
            if isinstance(raw.get('locations'), list) and raw['locations']:
                locations = raw['locations']
        except Exception:
            pass
    is_workday = weekday in ('周一', '周二', '周三', '周四', '周五')
    hour = None
    if isinstance(clock, dict) and isinstance(clock.get('time'), str) and ':' in clock['time']:
        try:
            hour = int(clock['time'].split(':', 1)[0])
        except ValueError:
            hour = None
    hints = {
        '徐家主宅': '母子常住/徐念薇夜间周末回宅',
        '公司': '沈知韫工作日08-15:59' if is_workday else '周末多空',
        '大学': '徐念薇工作日08-16:59' if (is_workday and (hour is None or 8 <= hour < 17)) else '美院',
        '工作室': '徐念薇校外画室' + ('/工作日17:00-21:59' if is_workday else ''),
        '市中心顶层公寓': '苏婉青常住',
    }
    return [f'{loc}({hints[loc]})' if loc in hints else loc for loc in locations if loc != current_location]


_CLICHE_MOTIF_PATTERNS = (
    ('喉结滚动', re.compile(r'喉结')),
    ('端杯/放杯', re.compile(r'(?:端起|搁下|放下|摩挲|握着)[^。\n]{0,6}(?:杯|盏)')),
    ('顿了半秒/指尖微顿', re.compile(r'顿了半秒|指尖(?:微微)?一顿|指尖微顿')),
    ('合上文件', re.compile(r'合上文件|推远半寸')),
    ('垂下眼/垂眸', re.compile(r'垂下眼|垂眸|眼帘微垂')),
    ('锁骨特写', re.compile(r'锁骨')),
    ('沐浴露/洗发水香', re.compile(r'沐浴露|洗发水')),
    ('嘴角/唇角微动', re.compile(r'嘴角|唇角')),
)


def _extract_recent_cliche_motifs(history):
    """Scan the last 2 committed turns for repeated stage/body clichés; return a concise list when overused."""
    if not isinstance(history, (list, tuple)) or not history:
        return []
    recent_turns = [t for t in history if isinstance(t, dict)][-2:]
    turn_hits = []
    for turn in recent_turns:
        texts = []
        for m in turn.get('messages') or ():
            if isinstance(m, dict) and isinstance(m.get('text'), str):
                texts.append(m['text'])
        blob = '\n'.join(texts)
        hits = {label for label, rx in _CLICHE_MOTIF_PATTERNS if rx.search(blob)}
        turn_hits.append(hits)
    if not turn_hits:
        return []
    repeated_across_turns = turn_hits[0] & turn_hits[1] if len(turn_hits) >= 2 else set()
    union_hits = set().union(*turn_hits)
    if repeated_across_turns:
        ordered = [label for label, _ in _CLICHE_MOTIF_PATTERNS if label in repeated_across_turns or label in union_hits]
        return ordered[:4]
    if len(union_hits) >= 3:
        ordered = [label for label, _ in _CLICHE_MOTIF_PATTERNS if label in union_hits]
        return ordered[:4]
    return []


ANCHOR_HISTORY_MODES = ('balanced', 'full')
_ARCHIVE_RECALL_RE = re.compile(r'之前|上次|那天|记得|旧账|当初|最早|以前|查一下|回忆|前几天|说过|答应过|忘了')


def normalize_anchor_history_mode(value):
    return 'full' if str(value or '').strip().lower() == 'full' else 'balanced'


def _short_hash(obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:12]


def _apply_anchor_history_mode(history, mode='balanced', soft_budget=6000):
    """Apply cross-window history anchor mode: 'balanced' keeps last 2 turns 100% verbatim + up to 2 prior turns within soft_budget."""
    rows = list(history or ())
    if normalize_anchor_history_mode(mode) == 'full' or len(rows) <= 2:
        return rows
    tail = rows[-2:]
    used = len(json.dumps(tail, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
    head_keep = []
    for item in reversed(rows[-4:-2]):
        cost = len(json.dumps(item, ensure_ascii=False, separators=(',', ':'), allow_nan=False)) + 1
        if used + cost > soft_budget:
            break
        head_keep.append(item)
        used += cost
    head_keep.reverse()
    return head_keep + tail


def build_user_delta(root, state, projection, history, new_history_only, text, selected,
                     resolved_op, intent_evidence, preview_cost, runtime, memory_text,
                     previous_error='', include_full_anchor=True, mode='dual_stream_v2',
                     omitted_archive=(), archive_index='', memory_index='',
                     required_sources=(), output_contract=None, resolution_policy=None,
                     operation_context=None, pending_echoes=(), weekday='',
                     breakout_hint=None, intel_catalog=None, director_roll=None,
                     protagonist_style='faithful', memory_view=None,
                     continuity_hook='', recent_room_continuity=None,
                     references=(), injected_refs=(), zone1_flags=None,
                     injected_guides=(), session_delta_out=None,
                     prev_state_hashes=None, anchor_history_mode='balanced'):
    """Build compact per-turn user message (tiny diff-only delta on turns 2..N, bounded anchor on turn 1)."""
    style = normalize_protagonist_style(protagonist_style)
    is_single = (mode == 'single_prefix_v2')
    cat = intel_catalog if intel_catalog is not None else sp.load_intel_catalog(root, optional=True)
    brief = compile_state_qualitative_brief(
        state, memory_text, include_tasks=is_single, include_points=is_single, intel_catalog=cat,
    )
    cast = (state or {}).get('cast', [])
    location = (state or {}).get('location', '')
    cur_weekday = weekday or (state or {}).get('weekday', '')
    clock = (runtime or {}).get('clock')

    dcfg = sp.director_config(root)
    if isinstance(director_roll, dict) and isinstance(director_roll.get('scene_turns_in_place'), int):
        scene_turns = director_roll['scene_turns_in_place']
    else:
        dstate = sp.parse_director_block(memory_text)
        scene_turns = (dstate['scene_turns'] + 1) if dstate['scene_location'] == location else 1
    exit_threshold = int(dcfg.get('scene_exit_threshold', 3))

    intl_now = (state or {}).get('intimate') if isinstance((state or {}).get('intimate'), dict) else {}
    intimate_active_now = bool(intl_now.get('scene_active'))
    avail_dests = _build_available_destinations(root, location, cur_weekday, clock)
    can_diff_blocks = (not include_full_anchor) and (mode == 'dual_stream_v2') and isinstance(prev_state_hashes, dict)
    unchanged_blocks = []

    delta = {
        'mode': mode,
        'anchor': 'full_scene_start' if include_full_anchor else 'incremental_delta',
        'clock': clock,
        'weekday': cur_weekday,
        'stamina_before': (preview_cost or {}).get('before'),
        'location': location,
        'cast': cast,
        'scene_turns_in_place': scene_turns,
    }
    dests_hash = _short_hash(avail_dests)
    if can_diff_blocks and prev_state_hashes.get('dests') == dests_hash:
        unchanged_blocks.append('available_destinations')
    else:
        delta['available_destinations'] = avail_dests

    qual_hash = _short_hash(brief)
    if can_diff_blocks and prev_state_hashes.get('qual') == qual_hash:
        unchanged_blocks.append('qualitative_state')
    else:
        delta['qualitative_state'] = brief

    delta['selection'] = selected
    delta['player_input'] = text
    delta['operation_context'] = operation_context

    raw_mind = (state or {}).get('npc_mind') if isinstance((state or {}).get('npc_mind'), dict) else {}
    cast_mind_view = {}
    for cname in cast:
        cm = raw_mind.get(cname)
        if not isinstance(cm, dict):
            continue
        entry = {}
        if cm.get('mood') and int(cm.get('mood_ttl') or 0) > 0:
            entry['余绪'] = cm['mood']
        if cm.get('preoccupation'):
            entry['手头牵挂'] = cm['preoccupation']
        imps = [it['text'] for it in (cm.get('impressions') or []) if isinstance(it, dict) and it.get('text')]
        if imps:
            entry['对志北的暗自印象'] = imps[-2:]
        if entry:
            cast_mind_view[cname] = entry
    mind_hash = _short_hash(cast_mind_view)
    if cast_mind_view:
        if can_diff_blocks and prev_state_hashes.get('mind') == mind_hash:
            unchanged_blocks.append('cast_mind')
        else:
            mind_block = {'people': cast_mind_view}
            if include_full_anchor:
                mind_block['rule'] = '在场人物此刻的未散余绪、手头牵挂与暗自记账：作为内在驱动自然流露、借题发挥或隔幕提起，严禁生硬复读原文，更禁开上帝视角读主角括号内心。'
            delta['cast_mind'] = mind_block
    prologue_active_now = bool((state or {}).get('prologue_active', False))
    is_move_op = (
        (isinstance(resolved_op, dict) and resolved_op.get('code') == 'move_player')
        or (isinstance(operation_context, dict) and isinstance(operation_context.get('detail'), dict)
            and operation_context['detail'].get('kind') == 'move_player')
    )
    if scene_turns <= 1 and cast and not intimate_active_now and (not prologue_active_now or is_move_op):
        dstate_entry = sp.parse_director_block(memory_text) if memory_text else {}
        entry_res = sp.build_scene_entry_snapshot(
            root, location, cast, weekday=cur_weekday, clock=clock,
            director_state=dstate_entry, npc_mind=raw_mind,
            present_actors=intl_now.get('present_actors') if not is_move_op else None,
        )
        if entry_res:
            delta['scene_entry_residue'] = {
                'moments': entry_res,
                'rule': '进场即中途：切入本幕前一刻屋里人物正忙到半途的生活余温，可择一二自然织入开场，不必人人报流水账。',
            }
    if intimate_active_now:
        delta['intimate_mode'] = True
        delta['active_costs'] = intl_now.get('active_costs') or sp.COSTS
    if scene_turns >= exit_threshold and not intimate_active_now:
        if is_single:
            delta['scene_exit_hint'] = f'已在{location}连续停驻{scene_turns}幕：至少1个选项须提供推进时段或附带"operation":{{"code":"move_player","destination":"合法开放地点"}}的转场出口。'
        else:
            delta['scene_exit_hint'] = f'已在{location}连续停驻{scene_turns}幕：至少1个选项须提供推进时段或[MOVE:地点]转场出口。'
    if previous_error:
        delta['previous_validation_error'] = previous_error
    if not cast:
        delta['solo_scene_rule'] = '当前地点无其他在场角色：严禁输出任何 [D:...] 台词行；若出现来电或消息，请在 [N] 旁白中转述或用引号呈现。'

    # Lossless offstage reference delivery in Zone 2 (keeps Zone 1 strictly byte-frozen for KV cache)
    newly_injected_refs = []
    newly_injected_guides = []
    cast_set_local = set(cast or ())
    seen_refs_set = {r for r in (injected_refs or ()) if isinstance(r, str) and r}
    seen_guides_set = {g for g in (injected_guides or ()) if isinstance(g, str) and g}
    if mode in ('dual_stream_v2', 'single_prefix_v2') and references:
        ref_names_ordered = list(dict.fromkeys(
            (r['name'] if isinstance(r, dict) else str(r))
            for r in references
            if (r.get('name') if isinstance(r, dict) else str(r))
        ))
        offstage_names = [n for n in ref_names_ordered if n not in cast_set_local and n != '徐志北']
        new_ref_names = [n for n in offstage_names if n not in seen_refs_set]
        seen_active_refs = [n for n in offstage_names if n in seen_refs_set]
        if new_ref_names:
            ref_chars = compile_characters(root, [], new_ref_names, include_host=False)
            ref_rels = compile_relationships_delta(root, cast, new_ref_names)
            delta['referenced_offstage'] = {
                'characters': [{'key': c['key'], 'name': c['name'], 'body': c['body']} for c in ref_chars],
                'relationships_delta': ref_rels,
            }
            newly_injected_refs.extend(new_ref_names)
        if seen_active_refs:
            delta['referenced_offstage_active'] = {
                'names': seen_active_refs,
                'rule': '以上人物仍不在场(完整人设与称谓锁已于本会话前文交付)，严禁写成[D:...]台词或当场动作。',
            }

    z1_vig = bool(zone1_flags.get('vig')) if isinstance(zone1_flags, dict) else _needs_vigilance_rules(state, memory_text)
    z1_intl = bool(zone1_flags.get('intl')) if isinstance(zone1_flags, dict) else _needs_intimate_zone1(state, memory_text)
    need_vig_now = _needs_vigilance_rules(state, memory_text)
    if mode in ('dual_stream_v2', 'single_prefix_v2') and need_vig_now and not z1_vig and 'vigilance' not in seen_guides_set:
        vig_body = _load_vigilance_body(root, protocol_mode=mode)
        if vig_body:
            delta['vigilance_craft_guide'] = vig_body
            newly_injected_guides.append('vigilance')
    elif _mentions_vigilance(text) and not z1_vig and not need_vig_now and 'vigilance' not in seen_guides_set:
        delta['vigilance_turn_note'] = '本轮玩家提及徐承邺或监视相关词：遵循信息差与真实证据原则，未实际目击或来电前不凭空制造撞见或实锤。'

    sd = sp.format_surprise_directive(director_roll)
    if sd:
        delta['surprise_directive'] = sd
    if breakout_hint:
        delta['breakout_hint'] = breakout_hint
    is_erotic_roll = isinstance(director_roll, dict) and (
        director_roll.get('category') in ('erotic_accident', 'sensual_hook')
        or director_roll.get('sub_mode') == 'heroine_spark'
        or str(director_roll.get('event_id') or director_roll.get('beat_id') or '').startswith(
            ('BEAT-T0-SENSUAL-', 'BEAT-T1-EROTIC-', 'BEAT-T2-EROTIC-', 'BEAT-T3-EROTIC-', 'BEAT-T4-EROTIC-')
        )
    )
    need_intl_now = (
        _needs_intimate_zone1(state, memory_text)
        or _needs_intimate_turn(text, selected, operation_context=operation_context, state=state)
        or is_erotic_roll
    )
    if mode in ('dual_stream_v2', 'single_prefix_v2') and need_intl_now and not z1_intl and 'intimate' not in seen_guides_set:
        intimate_body = _load_intimate_body(root)
        if intimate_body:
            delta['intimate_craft_guide'] = intimate_body
            newly_injected_guides.append('intimate')
    recent_cliches = _extract_recent_cliche_motifs(history or new_history_only)
    if recent_cliches:
        delta['fresh_detail_hint'] = (
            f'近两幕已用过[{" / ".join(recent_cliches)}]，本幕请换用全新的日常动作或生活杂务细节，勿重复同一小动作。'
        )

    held_compact = [{
        'id': i['id'],
        'name': i['name'],
        'qty': i['quantity'],
        'usage_mode': i.get('usage_mode', ''),
        'status': (i.get('fields') or {}).get('当前状态', ''),
        'remaining_turns': i.get('remaining_turns'),
        'desc': ((i.get('fields') or {}).get('描述', '') or '')[:64],
        'effect': ((i.get('fields') or {}).get('系统效果', '') or '')[:60],
        'source': ((i.get('fields') or {}).get('备注', '') or '')[:60],
    } for i in (state.get('items') or [])]
    deployed_all = state.get('deployed_items') or []
    deployed_here = [{
        'id': d['id'], 'name': d['name'], 'spot': d.get('spot') or '隐蔽角落',
        'hidden': bool(d.get('hidden', True)), 'effect': d.get('system_effect', ''),
    } for d in deployed_all if d.get('location') == location]
    deployed_remote = [{
        'id': d['id'], 'name': d['name'], 'location': d.get('location', ''),
        'spot': d.get('spot') or '隐蔽角落', 'effect': d.get('system_effect', ''),
    } for d in deployed_all if d.get('location') and d.get('location') != location]
    cast_set = set(cast or [])
    delivered_to_cast = [
        {'name': d['name'], 'recipient': d.get('recipient', '')}
        for d in (state.get('delivered_items') or [])
        if isinstance(d, dict) and d.get('name') and d.get('recipient') in cast_set
    ][-6:]
    items_hash = _short_hash(held_compact)
    dep_here_hash = _short_hash(deployed_here)
    dep_remote_hash = _short_hash(deployed_remote)
    gifts_hash = _short_hash(delivered_to_cast)
    cur_state_hashes = {
        'dests': dests_hash,
        'qual': qual_hash,
        'mind': mind_hash,
        'items': items_hash,
        'dep_here': dep_here_hash,
        'dep_remote': dep_remote_hash,
        'gifts': gifts_hash,
    }
    if isinstance(session_delta_out, dict):
        session_delta_out['newly_injected_refs'] = newly_injected_refs
        session_delta_out['newly_injected_guides'] = newly_injected_guides
        session_delta_out['state_hashes'] = cur_state_hashes

    if delivered_to_cast:
        if can_diff_blocks and prev_state_hashes.get('gifts') == gifts_hash:
            unchanged_blocks.append('delivered_gifts_to_cast')
        else:
            delta['delivered_gifts_to_cast'] = delivered_to_cast

    if isinstance(memory_view, dict):
        scoped_block = {}
        if memory_view.get('shared_scene_memory'):
            scoped_block['shared_with_cast'] = memory_view['shared_scene_memory']
        if memory_view.get('actor_private_memory'):
            scoped_block['actor_private_with_host'] = memory_view['actor_private_memory']
        if memory_view.get('host_private_memory'):
            scoped_block['host_private_only'] = memory_view['host_private_memory']
        if scoped_block:
            if include_full_anchor or mode != 'dual_stream_v2':
                scoped_block['rule'] = (
                    '严格按知情分区引用：shared_with_cast可自然提及；'
                    'actor_private_with_host仅该角色与徐志北私下共知（禁当众对其他人说破）；'
                    'host_private_only仅徐志北私下知晓（在场NPC严禁察觉）。'
                )
            delta['scoped_memory'] = scoped_block

    if include_full_anchor:
        if continuity_hook:
            delta['continuity_hook'] = continuity_hook
        if not isinstance(memory_view, dict):
            raw_mem = projection['text']
            delta['player_private_memory'] = raw_mem if is_single else _strip_active_task_from_memory(raw_mem)
        delta['items'] = state.get('items', [])
        if deployed_here:
            delta['deployed_items_here'] = deployed_here
        if deployed_remote:
            delta['deployed_items_remote'] = deployed_remote
        if is_single:
            delta['tasks'] = state.get('tasks')
        delta['accepted_history'] = (
            _apply_anchor_history_mode(history, anchor_history_mode)
            if mode == 'dual_stream_v2' else history
        )
    else:
        if not isinstance(memory_view, dict):
            current_ref = projection.get('current')
            current_l1 = ''
            if current_ref:
                lines = (memory_text or '').splitlines()
                current_l1 = '\n'.join(lines[current_ref['start_line'] - 1:current_ref['end_line']])
            delta['current_l1_memory'] = current_l1
            recalled_entries = []
            recalled_budget = 900
            for item in (projection.get('recalled_old_entries') or ())[:3]:
                if not isinstance(item, dict):
                    continue
                body = str(item.get('body') or item.get('text') or '').strip()
                if not body:
                    continue
                if len(body) > recalled_budget:
                    if recalled_budget < 80:
                        break
                    body = body[:recalled_budget].rstrip() + '…'
                recalled_entries.append({
                    'layer': item.get('layer', ''),
                    'range': item.get('range') or item.get('header') or '',
                    'body': body,
                })
                recalled_budget -= len(body)
                if recalled_budget <= 0:
                    break
            if recalled_entries:
                delta['recalled_memories'] = recalled_entries
        delta['items_count'] = len(state.get('items', []))
        if held_compact:
            if can_diff_blocks and prev_state_hashes.get('items') == items_hash:
                unchanged_blocks.append('held_items')
            else:
                delta['held_items'] = held_compact
        if deployed_here:
            if can_diff_blocks and prev_state_hashes.get('dep_here') == dep_here_hash:
                unchanged_blocks.append('deployed_items_here')
            else:
                delta['deployed_items_here'] = deployed_here
        if deployed_remote:
            if can_diff_blocks and prev_state_hashes.get('dep_remote') == dep_remote_hash:
                unchanged_blocks.append('deployed_items_remote')
            else:
                delta['deployed_items_remote'] = deployed_remote
        if is_single:
            delta['tasks'] = state.get('tasks')
        if new_history_only:
            delta['new_accepted_history'] = new_history_only

    if unchanged_blocks:
        delta['unchanged_from_prev_turn'] = unchanged_blocks

    if isinstance(recent_room_continuity, dict) and recent_room_continuity.get('tail'):
        delta['recent_room_continuity'] = recent_room_continuity

    if pending_echoes:
        delta['milestone_echo'] = {
            'events': [{'kind': e['kind'], 'summary': e['summary']} for e in pending_echoes],
            'rule': '一次性特定时刻微回响：仅允许在自然间隙或收束处用1句氛围/感官/内心轻顿带过，禁直呼任务/委托/商城/积分/系统词，禁扭转玩家意图，禁泄露给NPC。',
        }

    shop_custom_query = sp.detect_shop_custom_request(text) if (preview_cost or {}).get('kind') == 'action' else None
    if shop_custom_query:
        shop_cat = sp.load_shop_catalog(root, optional=True)
        existing_shop_names = [it['name'] for it in shop_cat.get('items', [])]
        try:
            st_shop, _, _ = save_store.load_bundle(root)
            existing_shop_names.extend(
                it.get('name', '') for it in ((st_shop.get('shop') or {}).get('dynamic_catalog') or [])
                if isinstance(it, dict) and it.get('name')
            )
            panels_shop = st_shop.get('panels') or {}
            hp_shop = panels_shop.get('系统宿主') or {}
            host_pts_shop = int(hp_shop.get('积分', 0) or 0)
            host_biz_shop = int(hp_shop.get('商业嗅觉', 0) or 0)
            host_charm_shop = int(hp_shop.get('魅力', 70) or 70)
            max_dep_shop = max((int((panels_shop.get(h) or {}).get('堕落', 0) or 0) for h in save_store.HEROINES), default=0)
        except Exception:
            host_pts_shop, host_biz_shop, host_charm_shop, max_dep_shop = 0, 0, 70, 0
        cur_grade = sp.host_unlocked_shop_grade(host_biz_shop, max_dep_shop, host_charm_shop)
        delta['shop_custom_directive'] = {
            'query': shop_custom_query,
            'host_points': host_pts_shop,
            'host_biz': host_biz_shop,
            'host_charm': host_charm_shop,
            'max_depravity': max_dep_shop,
            'unlocked_grade': cur_grade,
            'existing_names': existing_shop_names[-30:],
            'rule': (
                f'玩家本轮以【商城定制】显式向深渊天平系统商城请求定制进货（当前已解锁最高阶：{cur_grade}）。'
                '此过程仅在徐志北脑海私密闪现，在场NPC绝对听不见、看不见且绝不察觉，现实动作与对话照常流畅衔接。'
                '请穿插1～2句简短[N]私密内心系统提示，紧密贴合当前局面、人物与玩家诉求（策略/社交/官能/私密穿搭/隐秘装备均不设限），'
                '推出1～3件不与existing_names重名的新道具，明确标出【品级T1~T4】、【道具名】、具体用途与参考积分：'
                'T1寻常小物(10~30分,开局即用)、T2进阶利器(32~60分,轻中度官能/公关/工具)、T3稀缺重器(65~120分,监控/深控/核心筹码)、T4深渊禁品(150~260分,高危强催化/终阶筹码)；'
                '建议优先含1件当前可买实用款，若玩家索要超阶/强效道具也照常上架但标T3/T4由程序锁门待后期解锁；仅作上架展示，本幕不得直接凭空塞进主角手里，且任何道具只做筹码助力不一键跳过剧情。'
            ),
        }

    want_archive_lookup = (
        include_full_anchor
        or mode != 'dual_stream_v2'
        or bool(_ARCHIVE_RECALL_RE.search(text or ''))
    )
    if want_archive_lookup and (projection.get('index') or omitted_archive):
        delta['optional_archive_lookup'] = {
            'memory_index_path': memory_index,
            'memory_refs': projection.get('index', [])[:8],
            'history_index_path': archive_index,
            'recent_omitted_history': list(omitted_archive)[-8:],
            'rule': '仅玩家主动追问极早旧事时按精确行号/路径调用read_file_part补查，否则无需读文件。',
        }
    if required_sources and mode != 'dual_stream_v2':
        delta['required_sources'] = required_sources

    if is_single:
        istate = sp.parse_intel_block(memory_text)
        held_intel = [
            {'id': it['id'], 'name': it['name'], 'targets': sorted(it['effects'].keys())}
            for it in cat.get('items', []) if it['id'] in istate['held']
        ]
        delta['cost_preview'] = preview_cost
        delta['resolution_policy'] = resolution_policy
        delta['output_contract'] = output_contract
        delta['held_intel'] = held_intel
        delta['director_context'] = sp.build_director_settlement_context(root, memory_text, director_roll=director_roll)
        delta['task_whitelist_current'] = _extract_task_whitelist_values((state or {}).get('panels', []))
        delta['task_schema'] = {
            'title': '简短中文标题',
            'target': '系统宿主|沈知韫|徐念薇|苏婉青',
            'attr': '系统宿主限积分/经验值/商业嗅觉/体力，三女主仅好感',
            'value': '严格大于当前值的正整数',
            'tier': 'small|medium|large',
            'item_desc': '非空小物描述',
        }
        if isinstance(memory_view, dict):
            delta['memory_store_context'] = {
                'active_anchors': memory_view.get('active_anchors_index', []),
                'pending_facts': memory_view.get('pending_facts', []),
            }
            if memory_view.get('chronicle_archive_batch'):
                delta['chronicle_archive_request'] = {
                    'episodes': memory_view['chronicle_archive_batch'],
                    'rule': '请将以上最旧8幕浓缩写入 resolution.memory.chronicle_digest={"public":"<=260字公共纪要","views":{"角色名":"<=140字该角色私密线(可选)"}}，严禁混写私密事件至public。',
                }
        else:
            delta['memory_transfer_sources'] = {
                'current_round': runtime['last_closed'] if runtime.get('phase') == 'resting' and runtime.get('last_closed') else runtime.get('memory_round', 1),
                'current_entry': projection.get('current'),
                'transfers': projection.get('transfers', {}),
                'source_bodies': _extract_transfer_source_bodies(memory_text, projection.get('transfers', {})),
                'limits': projection.get('limits'),
            }

    elif mode == 'dual_stream_v2':
        heroines_here = [c for c in cast if c in save_store.HEROINES]
        lateral_hint = (
            '同场多位人物之间须自然留出至少1拍彼此直接接话、眼神暗递、替对方圆场或轻声拆台，切忌排队只朝徐志北发言。'
            if len(cast) >= 2 else ''
        )
        multi_hint = (
            '当前同地有两位以上女主在场，可按当前关系与防线自然提供暗触试探、避开视线、醋意周旋或高堕落共谋的选项（严守宿主主权，绝不强推）。'
            if len(heroines_here) >= 2 else ''
        )
        acting_anchor = (
            '演法锚点：先让在场人物活出各自手头事、未散余绪与彼此间的真实空气，允许斜向回应、合理误判与分寸摩擦，再自然承接主角行动。'
            if cast else ''
        )
        if intimate_active_now:
            tier_c = intl_now.get('active_costs') or sp.COSTS
            decision_clause = (
                f'文末完整单行---DECISION---后接PROMPT:与亲密节奏三档A:/B:/C:（当前处于亲密进行态，严禁强切回无关日常客套）：'
                f'A=缓拍温存/耳语挑逗/喘息照料({tier_c["A"]}体力)；'
                f'B=肢体加深/换姿换区/动用情趣道具({tier_c["B"]}体力)；'
                f'C=强势压制/破防升级/高烈度冲刺({tier_c["C"]}体力)。{multi_hint}'
            )
        else:
            decision_clause = f'文末完整单行---DECISION---后接PROMPT:与A:/B:/C:三项互异抉择。{multi_hint}'
        if include_full_anchor:
            if style == 'faithful':
                delta['output_format'] = (
                    '逐行以[N]/[A:名]/[D:在场角色名]起头：动作与对白自由穿插（快节奏可连发[D]，不必每句硬配动作）；'
                    '允许≤3句贴合原意图的简短[D:徐志北]（单句≤40字、零标签）；[D:名]只写纯台词（禁动作旁白或外层引号），三女主按需用导演[...]与词级标签。'
                    + lateral_hint + acting_anchor + decision_clause
                )
            else:
                delta['output_format'] = (
                    '逐行以[N]/[A:名]/[D:在场角色名]起头（严禁[D:徐志北]，以[A:徐志北]/[N]呈现主角动作与提问；[D:名]只写纯台词禁动作旁白或外层引号，快节奏可连发[D]）。'
                    + lateral_hint + acting_anchor + decision_clause
                )
        else:
            # Zone 0 already freezes line-tag syntax; Turn 2+ only carries compact speaker lock + active dynamic cues.
            protag_cue = '允≤3句简短[D:徐志北](零标签)；' if style == 'faithful' else '禁[D:徐志北]；'
            dyn_format = (protag_cue + lateral_hint + decision_clause).strip()
            if dyn_format:
                delta['output_format'] = dyn_format

    return json.dumps(delta, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _extract_transfer_source_bodies(memory_text, transfers):
    """Unconditionally extract full source bodies for all memory entries scheduled for tier transfer."""
    if not transfers or not memory_text:
        return {}
    lines = memory_text.splitlines()
    bodies = {}
    for tkey, refs in transfers.items():
        chunks = []
        for ref in refs or ():
            try:
                start = int(ref['start_line'])
                end = int(ref['end_line'])
                if 1 <= start <= end <= len(lines):
                    chunks.append('\n'.join(lines[start - 1:end]))
            except (KeyError, TypeError, ValueError):
                continue
        if chunks:
            bodies[tkey] = chunks
    return bodies


def _compact_intimate_for_settlement(intl, cast):
    """Strip pure backend numeric matrices (body_dev/host_phys/session_orgasms/inter_heroine) Stage 2 never reads,
    while preserving 100% of scene_active, privacy, sub_location, present_actors, attire, traces, and keepsakes."""
    if not isinstance(intl, dict):
        return intl
    scene_active = bool(intl.get('scene_active'))
    cast_set = set(cast or ())
    raw_attire = intl.get('attire') if isinstance(intl.get('attire'), dict) else {}
    attire_out = {}
    for who, att in raw_attire.items():
        if not isinstance(att, dict):
            continue
        is_non_default = (
            str(att.get('state') or 'neat') != 'neat'
            or str(att.get('outfit') or 'default') != 'default'
            or bool(att.get('gifted_items'))
        )
        if is_non_default or (scene_active and who in cast_set):
            attire_out[who] = att
    raw_traces = intl.get('traces') if isinstance(intl.get('traces'), dict) else {}
    traces_out = {who: tr for who, tr in raw_traces.items() if tr}
    keepsakes_out = [
        {k: ks[k] for k in ('id', 'owner', 'name', 'kind', 'condition', 'owner_aware') if k in ks}
        for ks in (intl.get('keepsakes') or ())
        if isinstance(ks, dict)
    ]
    out = {
        'scene_active': scene_active,
        'privacy': intl.get('privacy', 'open_public'),
        'sub_location': intl.get('sub_location', ''),
        'present_actors': list(intl.get('present_actors') or ()),
    }
    if attire_out:
        out['attire'] = attire_out
    if traces_out:
        out['traces'] = traces_out
    if keepsakes_out:
        out['keepsakes'] = keepsakes_out
    return out


def _compact_items_for_settlement(items, text, operation_context):
    """Keep full item fields for items referenced in player input/op; emit compact 5-key refs for untouched inventory."""
    if not items:
        return []
    op_blob = json.dumps(operation_context or {}, ensure_ascii=False) if operation_context else ''
    haystack = f'{text or ""}\n{op_blob}'
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get('id') or '')
        iname = str(it.get('name') or '')
        if (iname and iname in haystack) or (iid and iid in haystack):
            out.append(it)
        else:
            out.append({
                'id': iid,
                'name': iname,
                'qty': it.get('quantity', 1),
                'usage_mode': it.get('usage_mode', ''),
                'status': (it.get('fields') or {}).get('当前状态', ''),
            })
    return out


def _format_anchors_compact_lossless(anchors):
    """Encode active anchors as lossless single-line records (0 text truncation, ~30% less JSON key overhead)."""
    out = []
    for a in anchors or ():
        if isinstance(a, dict):
            out.append(f"{a.get('id', '')}|{a.get('kind', '')}|D{a.get('day', 1)}|★{a.get('importance', 3)}|{a.get('text', '')}")
        elif isinstance(a, str) and a:
            out.append(a)
    return out


def build_settlement_spec(root, state, projection, text, selected, resolved_op, intent_evidence,
                          preview_cost, runtime, memory_text, resolution_policy, output_contract,
                          operation_context, required_sources=(), intel_catalog=None, director_roll=None,
                          settlement_custom_rules=None, memory_view=None):
    """Build static-system + compact-user specification for background SUMMARY Tools.Chat.call."""
    root_p = Path(root)
    dir_ctx_full = sp.build_director_settlement_context(root, memory_text, director_roll=director_roll)
    channels_enum = list(dir_ctx_full.get('channels_enum') or sp.DIRECTOR_DEFAULT_CHANNELS.keys())
    channels_enum_json = json.dumps(channels_enum, ensure_ascii=False, separators=(',', ':'))

    sys_cache_key = (
        'settlement_sys_base',
        channels_enum_json,
        _stat_sig(root_p / 'txt文件/事件注册表.json'),
        _stat_sig(root_p / 'txt文件/知识库/系统标签类.json'),
    )
    base_sys_prompt = _sc_cache_get(sys_cache_key)
    if base_sys_prompt is None:
        catalog = compile_event_catalog(root, live_mode=True)
        sys_rules = compile_knowledge_rules(root, {}, '', '', mode='settlement')
        base_sys_prompt = _sc_cache_set(sys_cache_key, _clean_text(
            '你是深渊天平后台结构化结算器（非作家，不改写剧情）。根据玩家行动、前台已生成的完整微幕正文与选项，'
            '严格提取事实并输出单个合法裸JSON对象，严禁代码围栏或前后解释。\n'
            '输出骨架（严禁多余顶层键；仅 foreground_decision_missing==true 时附带 fallback_decision）：\n'
            '{"operation":""或合法操作对象,"handoff":""或原因,"checks":{"intent":"单行依据","knowledge":"信息边界","action":"操作核对","pace":"节奏依据"},'
            '"resolution":{"category":"A|B|C|SYSTEM","basis":"判档依据","clock":{"day":正整数,"time":"HH:MM","basis":"时间推进依据"},'
            '"events":[{"group":"事件组","target":"角色名或系统宿主","tags":["白名单原标签"],"evidence":"正文逐字子串"}],'
            '"memory":{"fact":"<=160字新因果或空串","anchor_ops":[],"chronicle_digest":""},'
            '"conditions":{"intensity":"A|B|C","effective_progress":true/false,"scene":"地点","npc":"角色或空串","action_changed":true/false,"stress_signals":非负整数,"breakout_triggered":[]}或""(仅SYSTEM),'
            '"sleep":{"kind":"none|collapse|interrupted|overnight","start":"HH:MM或空串","evidence":"正文子串或空串"},"task":""或6键对象,"items":[]},'
            '"quality_flags":[]}\n'
            '硬性规则：\n'
            '1. 传输空值约定：无操作operation、无待处理handoff、无任务resolution.task、无睡眠起点resolution.sleep.start、'
            '免费SYSTEM的resolution.conditions、无NPC时的conditions.npc 均明确写空字符串""，不得省略键或留空。\n'
            '2. 分类与费用：遵循context.resolution_policy；fixed_option必须原样返回required_category禁止重新判档：'
            '日常态(intimate_mode=false)下A/B档严禁出现任何C烈度_*标签；亲密进行态(intimate_mode=true)下A档仍禁C烈度_*，B档允许按实际正文触碰记录C烈度_轻度或C烈度_中度（深度/重度仍须走C档）。'
            'custom按实际成立行为判A/B/C不得免费；system固定为SYSTEM。严禁口算最终数值。\n'
            '3. 事件与依据：events每项含group/target/tags/evidence；只用下列合法标签原名；'
            'evidence必须是foreground_messages中某条text的逐字原样子串（若正文含｛表层｜潜台词｝，可引用原串或表层子串，严禁改字或引用decision选项）；'
            'host_events的target固定为"系统宿主"（优雅掌控_魅力精进：每场景限1次，仅宿主展现游刃有余的魅力掌控时打入）；'
            '⚠️【监视目标防错铁律】vigilance_events的target必须是【被徐承邺监视的对象】（仅限"沈知韫"/"苏婉青"/"徐念薇"/"徐志北"四选一），严禁填监视者"徐承邺"本人！若正文仅口头提及徐承邺的交代或行程而无实质警惕增减，请直接省略该条事件；'
            'shame_events/depravity_events/ds_events/affection_events 严禁填徐承邺（死亡查岗_沉沦期target填在场女主）；当operation_context.detail.kind=="inspect_deployed"时，允许对detail.remote_cast中的远程目标据正文结算自慰_暗中纾解/私密自渎/意外撞破_私密自渎，其余事件组target必须严格属于本场实际在场角色姓名。目标体力<=15且无玩家括号强行授权时严禁施加C烈度_深度/重度。免费SYSTEM不得附带事件/任务/物品。'
            '「首次」「深度操控_首次」「内射_首次核爆」「同质化免疫_回合2/3」「小憩单日限次」「失眠防叠加」「状态_空耗惩罚」「生理_危险期」均由后端据持久化记录自动派生与拦截，模型只需如实标注本幕发生的基础事件。'
            '多档标签判准速查（严禁自造白名单外标签）：'
            'C烈度_轻度(越界言语挑逗/近距离施压/非敏感部位试探)、C烈度_中度(亲吻/隔衣贴合/轻度敏感部位触碰)、C烈度_深度(褪衣暴露/直接敏感带抚弄/口交侍奉，仅限C档)、C烈度_重度(实质性交/强行突破/高危越界结合，仅限C档)；'
            '高潮_轻度累积(初段爱抚/边缘挑弄)、高潮_中度累积(持续密集快感/深入刺激)、高潮_重度累积(临近绝顶/强烈痉挛)、触发高潮_绝顶清算(明确达到高潮绝顶)；'
            '刺激_视觉(近距凝视/暴露羞耻)、刺激_嗅觉(贴颈呼吸/体香气息)、刺激_听觉(耳语喘息/羞耻指令)、刺激_物理(实质肢体爱抚/器官接触)；'
            '消耗_轻微焦虑(短暂心虚/轻微防备)、消耗_日常劳作(常规奔波家务办公消耗)、消耗_剧烈抗拒(剧烈挣扎/高强度体力与心理拉扯)；'
            'VIGILANCE（外地密室无来电/旁人外传严禁打目击确认或异常行迹）：目击确认(徐在场撞见)、证据实锤(物证影像)、异常行迹(本人察觉/来电查岗露馅/旁人看见外传)、眼线汇报(苏或旁人向徐汇报)、'
            '降警惕_轻度(缓疑)、降警惕_中度(圆场)、降警惕_深度(消痕)、合理解释(解释)、转移注意(引开)、无异常回合(平静)。\n'
            '4. conditions：普通付费action必须交完整7字段对象(intensity/effective_progress/scene/npc/action_changed/stress_signals/breakout_triggered)，'
            'intensity须与category一致，无NPC仅npc写""；effective_progress仅当本幕产生了新信息/线索、态度或防备真实改变、明确约定、场景转移或有效事件时判true，纯礼貌寒暄/重复关怀/原地客套必须判false；免费SYSTEM的conditions写""。\n'
            '5. clock：按剧情实际经过单调向前，首次从第1天初始化；sleep.kind为overnight须连续>=6小时跨夜至05:00~12:59且evidence为正文子串。\n'
            '6. memory：输出 {"fact":"<=160字新因果或空串","anchor_ops":[],"chronicle_digest":""}。'
            'fact仅记本幕有长期因果价值的新事实（禁换行，不复述pending_facts，无价值写""）；'
            'anchor_ops（最多3条，对照格式为"A-号|类型|D天|★权重|完整正文"的active_anchors维护永久承诺/转折/线索/藏物，无变化交[]）：'
            '{"op":"add","kind":"promise|milestone|secret|clue|relationship","importance":1到5,"text":"<=100字","private_host":false} / '
            '{"op":"update","id":"A-号","text":"<=100字"} / {"op":"resolve","id":"A-号","note":"<=40字"}；'
            'chronicle_digest通常写""；仅当context含chronicle_archive_request时，将所列8幕浓缩为{"public":"<=260字公共纪要","views":{"角色名":"<=140字私密线"}}（禁将私密混入public或泄K01绝密）。\n'
            '7. operation：若context.operation_context.requested非空且现场未拒绝，原样返回该对象；若现场拒绝或未满足条件，operation写""并在handoff说明原因。\n'
            '8. checks：intent/knowledge/action/pace 四条具体单行事实依据，禁用“已读取/通过/同上”。\n'
            '9. quality_flags：字符串数组，无问题写[]；若发现正文违背玩家括号显形、擅加反派滤镜、越界代打、泄露未解锁秘密，或段末A/B/C三选项高度同质化/原地打转（记录"option_stagnation"），简要列出。\n'
            '10. 任务续接与道具增量：仅当 context.cost_preview.kind=="action" 且 (context.tasks.current 为空或 context.tasks.current.status=="已完成") 时，'
            '参考 context.task_whitelist_current 续接1个温和且自然可达的新任务，填入 resolution.task 六键对象：'
            '{"title":"简短中文标题","target":"系统宿主|沈知韫|徐念薇|苏婉青","attr":"系统宿主限积分/经验值/商业嗅觉/体力，三女主仅好感","value":严格大于当前值的正整数,"tier":"small|medium|large","item_desc":"非空小物描述"}（例：积分+6~20，好感+2~5）。'
            '若已有进行中任务或为免费SYSTEM，resolution.task 必须写 ""。严禁为凑任务目标编造未发生事件。'
            '系统商城兑换与委托奖励领取已由前端确定性通道处理，无兑换或任务待发资格时严禁填 action=="add"，无正文逐字依据时 resolution.items 写 []；'
            '确有正文依据时每项为 {"entry":{"name":"道具名","action":"add|consume|archive",...},"evidence":"正文原样子串"}。\n'
            '11. 商业情报亮牌：情报整理入库与商业杠杆预备已由前端确定性通道处理；仅当玩家在正文中明确亮牌动用 context.held_intel 中某条一次性情报时，才可选填 resolution.intel_used={"id":"INTEL-00X","target":"合法对象","evidence":"正文原样子串"}，否则省略或写 ""。\n'
            '12. 活体世界回响（可选）：仅当 context.cost_preview.kind=="action" 时，可选填 resolution.director_echo 对象（无变化省略或写""，严禁编造）：'
            '{"new_thread":{"who":["角色名"],"topic":"<=28字具体未完线头/承诺/破绽/藏物","tension":"soft|hard"}或"","close_thread":"本幕已了结的active_threads编号或""","clock_nudges":{"CLK_XXX":1或-1}或{},"used_channel":"真实变故填下列媒介之一否则\\"\\"","mind_updates":{"在场角色名":{"mood":"<=32字未散余绪","preoccupation":"<=36字新牵挂","impression":"<=36字对志北新主观印象或心结"}}}；'
            f'合法媒介 channels_enum={channels_enum_json}；'
            'mind_updates仅在正文确有情绪余波/新牵挂/记账印象时摘录（无变化省略），严禁泄露未解锁绝密。\n'
            '13. 段末抉择兜底（仅缺省触发）：foreground_decision_missing为false时省略fallback_decision；'
            '为true时补fallback_decision={"prompt":"<=300字","options":[{"id":"A","text":"日常(<=500字)"},{"id":"B","text":"社交(<=500字)"},{"id":"C","text":"主动(<=500字)"}]}'
            '（三项互异；转场项可附"operation":{"code":"move_player","destination":"合法地点"}）。\n'
            '14. 空间隐私与亲密态势增量 resolution.scene_state（可选，无变化直接省略或写""）：仅当本幕真实发生了房门反锁/隔墙偷欢/同席桌下暗触/子区切换/衣着凌乱褪衣换装/新增吻痕潮红痕迹/女主间疑心或共谋变化/身体部位开发互动/主角明确释放/偷藏或收下贴身衣物/剧情【商城定制】新推道具，或正式进入/收束亲密状态时填写：'
            '{"intimate_active":true或false,"privacy":"open_public|semi_open|thin_wall|under_cover|locked_private","sub_location":"<=48字子区名","present_actors":["当前房内实际同席角色"],"attire_updates":{"女主名":{"outfit":"穿搭名或default","state":"neat|disheveled|half_undressed|wet|torn"}},"trace_adds":{"女主名":[{"kind":"吻痕|指印|潮红|发丝凌乱","desc":"<=60字","turns":4,"visible":true}]},"inter_heroine_deltas":{"A->B":1或-1},"body_acts":{"女主名":["oral|hand|chest|foot|core"]},"host_release":true,"keepsake_adds":[{"owner":"女主名","name":"衣物名","kind":"panties|stockings|bra|nightwear|accessory","method":"stolen|taken_intimate|gifted","condition":"fresh_warm|stained_damp|faded","desc":"<=60字"}],"keepsake_updates":[{"id":"KS-编号","owner_aware":true,"condition":"stained_damp"}],"shop_adds":[{"name":"道具名","grade":"T1|T2|T3|T4","category":"sensual|covert|daily","usage_mode":"gift|consumable_target|reusable_tool|deployable_device","price":10到260,"pack_qty":1到3,"desc":"用途说明","system_effect":""或"buff:名:1-3:效"或"deploy_device:camera|audio|aroma","max_per_save":1到3}]}'
            '（所有子键均可选；贴身偷藏衣物只走keepsake_adds；shop_adds仅在context.shop_custom_requested==true时按正文新推道具摘录，严禁塞入resolution.items或虚构）。\n\n'
            '【合法事件标签白名单】\n'
            + json.dumps(catalog, ensure_ascii=False, separators=(',', ':'))
            + '\n\n【事件触发判定精简规则】\n'
            + '\n\n'.join(item['body'] for item in sys_rules)
        ))
    system_prompt = _apply_custom_rules_section(
        base_sys_prompt,
        settlement_custom_rules,
        enabled_key='settlement_custom_rules_enabled',
        position_key='settlement_custom_rules_position',
        text_key='settlement_custom_rules_text',
        header='【玩家自定义后台结算规则（副模型结算补充偏好；严禁违背裸JSON输出格式、合法标签白名单与原文evidence逐字引用铁律）】',
        footer='【自定义后台结算规则结束】',
    )

    panels = (state or {}).get('panels', [])
    icat = intel_catalog if intel_catalog is not None else sp.load_intel_catalog(root, optional=True)
    istate = sp.parse_intel_block(memory_text)
    held_intel = [
        {'id': it['id'], 'name': it['name'], 'targets': sorted(it['effects'].keys())}
        for it in icat.get('items', []) if it['id'] in istate['held']
    ]
    raw_mind_s2 = (state or {}).get('npc_mind') if isinstance((state or {}).get('npc_mind'), dict) else {}
    cast_mind_s2 = {
        cname: {
            'mood': (raw_mind_s2.get(cname) or {}).get('mood', ''),
            'preoccupation': (raw_mind_s2.get(cname) or {}).get('preoccupation', ''),
            'impressions': [it.get('text', '') for it in ((raw_mind_s2.get(cname) or {}).get('impressions') or []) if isinstance(it, dict) and it.get('text')],
        }
        for cname in ((state or {}).get('cast') or ())
        if cname in raw_mind_s2
    }
    if isinstance(memory_view, dict):
        mem_store_ctx = {
            'active_anchors': _format_anchors_compact_lossless(memory_view.get('active_anchors_index', [])),
            'pending_facts': memory_view.get('pending_facts', []),
        }
        archive_batch = memory_view.get('chronicle_archive_batch') or []
    else:
        mem_store_ctx = {'active_anchors': [], 'pending_facts': []}
        archive_batch = []

    raw_cp = (resolution_policy or {}).get('category_policy')
    compact_cp = (
        {'mode': raw_cp.get('mode', 'custom'), 'required_category': raw_cp.get('required_category')}
        if isinstance(raw_cp, dict) else raw_cp
    )
    compact_policy = {
        'kind': (resolution_policy or {}).get('kind', (preview_cost or {}).get('kind', 'action')),
        'conditions_required': bool((resolution_policy or {}).get('conditions_required', True)),
        'intimate_mode': bool((resolution_policy or {}).get('intimate_mode', False)),
        'category_policy': compact_cp,
    }
    dir_ctx_dynamic = {k: v for k, v in dir_ctx_full.items() if k != 'channels_enum'}
    tasks_obj = (state or {}).get('tasks')
    cur_task = tasks_obj.get('current') if isinstance(tasks_obj, dict) else None
    can_issue_task = (
        (preview_cost or {}).get('kind') == 'action'
        and (not isinstance(cur_task, dict) or cur_task.get('status') == '已完成')
    )
    compact_items = _compact_items_for_settlement((state or {}).get('items', []), text, operation_context)
    deployed_items = (state or {}).get('deployed_items', [])

    user_context = {
        'location': (state or {}).get('location'),
        'cast': (state or {}).get('cast', []),
        'presence': (state or {}).get('presence', {}),
        'intimate': _compact_intimate_for_settlement((state or {}).get('intimate'), (state or {}).get('cast', [])),
        **({'cast_mind': cast_mind_s2} if cast_mind_s2 else {}),
        'panels': panels,
        **({'task_whitelist_current': _extract_task_whitelist_values(panels)} if can_issue_task else {}),
        **({'held_intel': held_intel} if held_intel else {}),
        'director_context': dir_ctx_dynamic,
        'player_input': text,
        'selection': selected,
        'operation_context': operation_context,
        'cost_preview': preview_cost,
        'runtime': runtime,
        'resolution_policy': compact_policy,
        'items': compact_items,
        **({'deployed_items': deployed_items} if deployed_items else {}),
        'tasks': tasks_obj,
        'memory_store_context': mem_store_ctx,
        **({'chronicle_archive_request': {
            'episodes': archive_batch,
            'rule': '请将以上最旧8幕浓缩写入 resolution.memory.chronicle_digest={"public":"<=260字公共纪要","views":{"角色名":"<=140字私密线(可选)"}}，严禁混写二人私密事件至public。',
        }} if archive_batch else {}),
    }
    shop_custom_query = sp.detect_shop_custom_request(text) if (preview_cost or {}).get('kind') == 'action' else None
    if shop_custom_query:
        user_context['shop_custom_requested'] = True
        user_context['shop_custom_query'] = shop_custom_query
    return {
        'system_prompt': system_prompt,
        'system_sha256': _digest_text(system_prompt),
        'user_context': user_context,
    }


def _resolve_option_move(raw_dest, valid_destinations, location_aliases, current_location):
    dest = (raw_dest or '').strip().strip('「」『』"\' ')
    if not dest:
        return None
    aliases = location_aliases if isinstance(location_aliases, dict) else {}
    if valid_destinations is not None:
        lookup = {d: d for d in valid_destinations}
        lookup.update(aliases)
        resolved = lookup.get(dest)
    else:
        resolved = aliases.get(dest, dest)
    if not resolved or resolved == current_location:
        return None
    return {'code': 'move_player', 'destination': resolved}


def _clean_decision_field(text):
    value = (text or '').strip()
    if value.endswith('**') and value.count('**') % 2 == 1:
        value = value[:-2].strip()
    if value.startswith('**') and value.count('**') % 2 == 1:
        value = value[2:].strip()
    return value


def _split_decision_text(text):
    """Split raw foreground text into (body_text, decision_text, has_explicit_sep)."""
    m = _DECISION_BLOCK_SPLIT_RE.search(text)
    if m:
        return text[:m.start()], text[m.end():], True
    m2 = _INLINE_DECISION_SEP_RE.search(text)
    if m2:
        return text[:m2.start()], text[m2.end():], True
    return text, '', False


def _detect_unmarked_decision_tail(lines):
    """If the model omitted ---DECISION--- but ended with a clean A/B/C block after the last story node, split it."""
    last_story_idx = -1
    for idx, raw_line in enumerate(lines):
        trimmed = raw_line.strip()
        if not trimmed:
            continue
        if _LINE_TAG_RE.match(trimmed) or _BARE_NARRATION_RE.match(trimmed):
            last_story_idx = idx
    tail_start = last_story_idx + 1
    if tail_start >= len(lines):
        return None
    opt_positions = {}
    first_prompt_idx = None
    for idx in range(tail_start, len(lines)):
        trimmed = lines[idx].strip()
        if not trimmed or trimmed == '```' or _BARE_DIVIDER_RE.match(trimmed):
            continue
        if first_prompt_idx is None and not opt_positions and _PROMPT_LINE_RE.match(trimmed):
            first_prompt_idx = idx
            continue
        om = _OPT_LINE_RE.match(trimmed)
        if om:
            letter = (om.group(1) or om.group(4) or '').upper()
            if letter in ('A', 'B', 'C') and letter not in opt_positions:
                opt_positions[letter] = idx
    if set(opt_positions) != {'A', 'B', 'C'}:
        return None
    if not (opt_positions['A'] < opt_positions['B'] < opt_positions['C']):
        return None
    split_idx = first_prompt_idx if first_prompt_idx is not None else opt_positions['A']
    while split_idx > tail_start:
        prev = lines[split_idx - 1].strip()
        if not prev or _BARE_DIVIDER_RE.match(prev):
            split_idx -= 1
        else:
            break
    return split_idx


def strip_preview_decision_leak(text):
    """Strip any leaked decision separator or trailing prompt/option lines from a streaming preview node."""
    if not isinstance(text, str) or not text:
        return ''
    body, _, _ = _split_decision_text(text)
    lines = body.splitlines()
    cut = len(lines)
    for idx in range(1, len(lines)):
        trimmed = lines[idx].strip()
        if _PROMPT_LINE_RE.match(trimmed) or _DECISION_SEP_RE.match(trimmed):
            cut = idx
            break
        om = _OPT_LINE_RE.match(trimmed)
        if om and (om.group(1) or om.group(4) or '').upper() == 'A':
            if any(
                (m2 := _OPT_LINE_RE.match(lines[j].strip())) and (m2.group(1) or m2.group(4) or '').upper() == 'B'
                for j in range(idx + 1, len(lines))
            ):
                cut = idx
                break
    lines = lines[:cut]
    while lines and (not lines[-1].strip() or _BARE_DIVIDER_RE.match(lines[-1].strip())):
        lines.pop()
    return '\n'.join(lines).strip()


_OPT_STOP_CONT_RE = re.compile(r'^\s*(?:#{1,6}\s|【|[（(]?\s*(?:注|说明|备注)\s*[:：]|```)')
_LEADING_ASCII_FISH_RE = re.compile(r'^\s*(?:\[[a-zA-Z0-9_,\s-]{1,80}\]\s*)+')
_LEADING_VOICE_TAGS_RE = re.compile(r'^((?:\[[^\]\r\n]{1,80}\]\s*)*)(.*)$', re.S)
_ANY_VOICE_BRACKET_RE = re.compile(r'\[[^\]\r\n]{1,80}\]\s*')
_DRAMA3_XML_STRIP_RE = re.compile(
    r'</?(?:whisper|emphasis|soft|fast|slow|stress|forceful|chinese|english|japanese|korean|cantonese|french|german|spanish)>',
    re.I,
)
_OUTER_QUOTES_ONLY_RE = re.compile(
    r'^(?:“([^“”]+)”|"([^"]+)"|「([^「」]+)」|『([^『』]+)』)\s*$',
    re.S,
)
_MIXED_ACTION_DIALOGUE_RE = re.compile(
    r'^(?P<act>[^“"「『\r\n]{2,180}?)'
    r'(?P<verb>[，,、；;\s]*(?:(?:低声|轻声|冷声|沉声|柔声|淡淡|缓声|随口|开口|抬眼|垂眸|侧头|转头)?'
    r'(?:说道|问道|答道|应道|反问|叮嘱|交代|开口|道|说|问|答))?\s*[：:，,])\s*'
    r'(?:“(?P<q1>[^”]+)”|"(?P<q2>[^"]+)"|「(?P<q3>[^」]+)」|『(?P<q4>[^』]+)』)\s*$',
    re.S,
)


def _normalize_stream_node(kind, who, body):
    text = (body or '').strip()
    if not text:
        return []
    if kind == 'narration':
        cleaned = _DRAMA3_XML_STRIP_RE.sub('', _ANY_VOICE_BRACKET_RE.sub('', text)).strip() or text
        return [{'kind': 'narration', 'speaker': '', 'text': cleaned}]
    if kind == 'action':
        cleaned = _DRAMA3_XML_STRIP_RE.sub('', _ANY_VOICE_BRACKET_RE.sub('', text)).strip() or text
        return [{'kind': 'action', 'speaker': who, 'text': cleaned}]
    # kind == 'dialogue'
    if who == '徐志北':
        # Protagonist dialogue stays clean & tag-free (default muted, optional clean voice); strip any stray bracket/XML tags.
        text = _DRAMA3_XML_STRIP_RE.sub('', _ANY_VOICE_BRACKET_RE.sub('', text)).strip() or text
    tm = _LEADING_VOICE_TAGS_RE.match(text)
    leading_tags = (tm.group(1) or '').strip() if tm else ''
    rest = (tm.group(2) or '').strip() if tm else text

    qm = _OUTER_QUOTES_ONLY_RE.match(rest)
    if qm:
        inner = (qm.group(1) or qm.group(2) or qm.group(3) or qm.group(4) or '').strip()
        if inner:
            final_text = f'{leading_tags} {inner}'.strip() if leading_tags else inner
            return [{'kind': 'dialogue', 'speaker': who, 'text': final_text}]

    mm = _MIXED_ACTION_DIALOGUE_RE.match(rest)
    if mm:
        act_raw = (mm.group('act') or '').strip()
        verb_raw = (mm.group('verb') or '').strip()
        speech_raw = (mm.group('q1') or mm.group('q2') or mm.group('q3') or mm.group('q4') or '').strip()
        has_colon_or_verb = ('：' in verb_raw or ':' in verb_raw or bool(re.search(r'道|说|问|答|开口|反问|叮嘱|交代', verb_raw)))
        is_third_person_lead = (
            act_raw.startswith(('她', '他'))
            or (bool(who) and act_raw.startswith(who))
            or has_colon_or_verb
        )
        starts_first_second = bool(re.match(r'^(?:我|你|您|咱们|我们|你们)(?:们|[，,。、\s]|$)', act_raw))
        if speech_raw and is_third_person_lead and not starts_first_second and not act_raw.startswith(('｛', '{', '[')):
            act_clean = act_raw.rstrip('，,、；;：: ')
            if act_clean and act_clean[-1] not in '。！？!?…':
                act_clean += '。'
            inner_qm = _OUTER_QUOTES_ONLY_RE.match(speech_raw)
            if inner_qm:
                speech_raw = (inner_qm.group(1) or inner_qm.group(2) or inner_qm.group(3) or inner_qm.group(4) or speech_raw).strip()
            final_speech = f'{leading_tags} {speech_raw}'.strip() if leading_tags else speech_raw
            out = []
            if act_clean:
                out.append({'kind': 'action', 'speaker': who, 'text': act_clean})
            if final_speech:
                out.append({'kind': 'dialogue', 'speaker': who, 'text': final_speech})
            if out:
                return out

    return [{'kind': 'dialogue', 'speaker': who, 'text': text}]


def _parse_decision_lines(decision_lines, valid_destinations=None, location_aliases=None, current_location=''):
    prompt = ''
    opts = {}
    opt_ops = {}
    active_field = None
    for raw_line in decision_lines:
        line = raw_line.strip()
        if not line or line == '```' or _BARE_DIVIDER_RE.match(line) or _DECISION_SEP_RE.match(line):
            continue
        pm = _PROMPT_LINE_RE.match(line)
        if pm:
            prompt = _clean_decision_field(pm.group(1))
            active_field = 'prompt'
            continue
        om = _OPT_LINE_RE.match(line)
        if om:
            letter = (om.group(1) or om.group(4) or '').upper()
            raw_move = om.group(2) or om.group(3) or om.group(5) or om.group(6)
            opt_text = _clean_decision_field(om.group(7))
            if not raw_move:
                im = _OPT_INLINE_MOVE_RE.match(opt_text)
                if im:
                    raw_move = im.group(1)
                    opt_text = _clean_decision_field(opt_text[im.end():])
                else:
                    tm = _OPT_TRAILING_MOVE_RE.search(opt_text)
                    if tm:
                        raw_move = tm.group(1)
                        opt_text = _clean_decision_field(opt_text[:tm.start()])
            opts[letter] = opt_text
            op = _resolve_option_move(raw_move, valid_destinations, location_aliases, current_location)
            if op:
                opt_ops[letter] = op
            else:
                opt_ops.pop(letter, None)
            active_field = letter
            continue
        if _OPT_STOP_CONT_RE.match(line):
            active_field = None
            continue
        if active_field in ('A', 'B', 'C') and active_field in opts:
            merged_opt = _clean_decision_field((opts[active_field] + ' ' + line).strip())
            if active_field not in opt_ops:
                tm = _OPT_TRAILING_MOVE_RE.search(merged_opt)
                if tm:
                    op = _resolve_option_move(tm.group(1), valid_destinations, location_aliases, current_location)
                    if op:
                        opt_ops[active_field] = op
                    merged_opt = _clean_decision_field(merged_opt[:tm.start()])
            opts[active_field] = merged_opt
        elif active_field == 'prompt':
            prompt = _clean_decision_field((prompt + ' ' + line).strip())
        elif not opts:
            prompt = _clean_decision_field((prompt + ' ' + line).strip())
            active_field = 'prompt'
    return prompt, opts, opt_ops


def parse_stream_story(raw_text, allowed_speakers=None, partial=False,
                       valid_destinations=None, location_aliases=None, current_location='',
                       allow_missing_decision=False, allow_player_dialogue=False,
                       max_player_dialogue=MAX_PLAYER_DIALOGUE_PER_TURN):
    """Parse lightweight line-streaming script format into canonical {messages, decision}."""
    if not isinstance(raw_text, str):
        raise rr.RoundError('前台演播正文缺失')
    text = raw_text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```[a-zA-Z0-9_-]*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)

    body_text, decision_text, in_decision = _split_decision_text(text)
    body_lines = body_text.splitlines()
    decision_lines = decision_text.splitlines() if in_decision else []

    if partial and not in_decision and raw_text and not raw_text.endswith('\n'):
        # Drop potentially incomplete trailing line while streaming.
        body_lines = body_lines[:-1]
    elif not in_decision and not partial:
        split_idx = _detect_unmarked_decision_tail(body_lines)
        if split_idx is not None:
            decision_lines = body_lines[split_idx:]
            body_lines = body_lines[:split_idx]
            in_decision = True

    raw_messages = []
    allowed = set(allowed_speakers) if allowed_speakers is not None else None
    dialogue_allowed = (allowed | {'徐志北'}) if (allowed is not None and allow_player_dialogue) else allowed

    for idx_line, raw_line in enumerate(body_lines):
        trimmed = raw_line.strip()
        if not trimmed or trimmed == '```' or _BARE_DIVIDER_RE.match(trimmed):
            continue
        if _DECISION_SEP_RE.match(trimmed):
            in_decision = True
            decision_lines = body_lines[idx_line + 1:] + decision_lines
            break
        for seg in _INLINE_TAG_SPLIT_RE.split(trimmed):
            line = seg.strip()
            if not line or _BARE_DIVIDER_RE.match(line):
                continue
            m = _LINE_TAG_RE.match(line)
            if m:
                code, who, body = m.group(1), (m.group(2) or '').strip(), m.group(3).strip()
                if not body:
                    continue
                if code == 'N':
                    raw_messages.append({'kind': 'narration', 'speaker': '', 'text': body})
                elif code == 'A':
                    raw_messages.append({'kind': 'action', 'speaker': who, 'text': body})
                elif code == 'D':
                    raw_messages.append({'kind': 'dialogue', 'speaker': who, 'text': body})
                continue
            bm = _BARE_NARRATION_RE.match(line)
            if bm:
                body = bm.group(1).strip()
                if body:
                    raw_messages.append({'kind': 'narration', 'speaker': '', 'text': body})
                continue
            if raw_messages:
                # Continuation line attaches to the active node safely.
                raw_messages[-1]['text'] = (raw_messages[-1]['text'] + '\n' + line).strip()
            elif not partial:
                # Tolerate untagged opening narration only if non-empty and not stray markup.
                if not line.startswith('{') and not line.startswith('---'):
                    raw_messages.append({'kind': 'narration', 'speaker': '', 'text': line})

    messages = []
    for rm in raw_messages:
        messages.extend(_normalize_stream_node(rm['kind'], rm['speaker'], rm['text']))

    if partial:
        safe = []
        player_dialogue_seen = 0
        for m in messages:
            if not m['text'] or len(m['text']) > 4000:
                continue
            if m['kind'] == 'dialogue':
                if dialogue_allowed is not None and m['speaker'] not in dialogue_allowed:
                    continue
                if m['speaker'] == '徐志北':
                    if not allow_player_dialogue or player_dialogue_seen >= max_player_dialogue:
                        continue
                    player_dialogue_seen += 1
            if m['kind'] == 'action' and allowed is not None and m['speaker'] not in (allowed | {'徐志北'}):
                continue
            safe.append(m)
        return {'messages': safe, 'has_decision': in_decision}

    if not 1 <= len(messages) <= 1000:
        raise rr.RoundError('前台演播缺少有效剧情节点')
    player_dialogue_count = 0
    for m in messages:
        rr._text(m['text'], 'message.text', 4000)
        if m['kind'] == 'narration':
            if m['speaker'] != '':
                raise rr.RoundError('旁白不能携带说话人')
        elif m['kind'] == 'dialogue':
            if dialogue_allowed is not None and m['speaker'] not in dialogue_allowed:
                raise rr.RoundError('角色不在场或代写玩家台词：dialogue / ' + str(m['speaker']))
            if m['speaker'] == '徐志北':
                if not allow_player_dialogue:
                    raise rr.RoundError('角色不在场或代写玩家台词：dialogue / 徐志北')
                player_dialogue_count += 1
                if player_dialogue_count > max_player_dialogue:
                    raise rr.RoundError(f'主角代写台词过多（单幕上限 {max_player_dialogue} 句），请精简至贴合玩家意图的 1～2 句简短发言')
        elif m['kind'] == 'action':
            if allowed is not None and m['speaker'] not in (allowed | {'徐志北'}):
                raise rr.RoundError('动作角色不在场：action / ' + str(m['speaker']))

    prompt, opts, opt_ops = _parse_decision_lines(
        decision_lines,
        valid_destinations=valid_destinations,
        location_aliases=location_aliases,
        current_location=current_location,
    ) if in_decision else ('', {}, {})
    valid_letters = {k for k in ('A', 'B', 'C') if (opts.get(k) or '').strip()}

    if not in_decision or valid_letters != {'A', 'B', 'C'}:
        if not in_decision and not valid_letters:
            reason = '未检测到 ---DECISION--- 与 A/B/C 选项'
        else:
            missing = [k for k in ('A', 'B', 'C') if k not in valid_letters]
            reason = '缺少选项 ' + '/'.join(missing)
        if allow_missing_decision:
            return {'messages': messages, 'decision': None, 'decision_missing_reason': reason}
        raise rr.RoundError(f'前台演播缺少完整的 ---DECISION--- 与 A/B/C 三项抉择（{reason}）')

    if not prompt:
        prompt = _DEFAULT_DECISION_PROMPT

    option_items = []
    for letter in ('A', 'B', 'C'):
        item = {'id': letter, 'text': opts[letter]}
        if letter in opt_ops:
            item['operation'] = opt_ops[letter]
        option_items.append(item)
    decision = {
        'prompt': prompt,
        'options': option_items,
    }
    rr._text(decision['prompt'], 'decision.prompt', 300)
    for item in decision['options']:
        rr._text(item['text'], 'decision.option.text', 500)
    if len({item['text'].strip() for item in decision['options']}) != 3:
        raise rr.RoundError('前台演播三个选项须互不相同')
    return {'messages': messages, 'decision': decision}


_DISCLOSURE_ACTION_RE = re.compile(
    r'亮出|拿出|递给|出示|摊开|说破|告诉|告知|坦白|抖出|宣称|提起|提及|透露|说出|挑明|道出'
)
_NARRATION_REVEAL_RE = re.compile(
    r'说出|说破|脱口|挑明|告知|告诉|坦白|透露|道出|宣称|亮出|出示|递给|听见|听到|得知|知晓|知道|明白|震惊|脸色大变|追问|质问'
)
_HOST_INNER_RE = re.compile(
    r'心里|心中|暗自|暗忖|暗想|心底|脑海|念头|不动声色|没有说破|未曾说破|不能说破|只字未提'
)


def guardrail_check(root, location, cast, messages, memory_text='', *,
                    secrets_unlocked=(), allow_player_dialogue=False,
                    max_player_dialogue=MAX_PLAYER_DIALOGUE_PER_TURN):
    """Zero-cost deterministic checks protecting speaker sovereignty, info-gap secrets, and residence locks."""
    root = Path(root)
    warnings = []
    cast_set = set(cast or [])
    unlocked = {str(x).strip() for x in (secrets_unlocked or ()) if str(x).strip()}

    # 1. Speaker sovereignty & presence lock (defense-in-depth).
    player_dlg_count = 0
    for m in messages:
        if m['kind'] == 'dialogue':
            if m['speaker'] in cast_set:
                pass
            elif allow_player_dialogue and m['speaker'] == '徐志北':
                player_dlg_count += 1
                if player_dlg_count > max_player_dialogue:
                    raise rr.RoundError(
                        f'红线拦截：主角代写台词过多（单幕上限 {max_player_dialogue} 句）'
                    )
            else:
                raise rr.RoundError('红线拦截：角色不在场或代写玩家台词 (' + str(m['speaker']) + ')')
        if m['kind'] == 'action' and m['speaker'] not in (cast_set | {'徐志北'}):
            raise rr.RoundError('红线拦截：场外角色动作 (' + str(m['speaker']) + ')')

    # 2. Information-gap secret boundary from authoritative 关系称谓库.json (per-speaker + action/narration check).
    reg = RelationshipRegistry(root)
    secret_holders = set()
    for fact in reg.data['facts'].values():
        if isinstance(fact['known_by'], list):
            secret_holders.update(fact['known_by'])
    all_present = cast_set | {'徐志北'}
    non_holders_present = [p for p in all_present if p not in secret_holders]
    if secret_holders and 'K01' not in unlocked:
        for m in messages:
            kind = m.get('kind')
            speaker = m.get('speaker', '')
            text = m.get('text', '')
            hit = _WILL_SECRET_RE.search(text)
            if not hit:
                continue
            if kind == 'dialogue':
                if speaker not in secret_holders:
                    raise rr.RoundError(
                        f'信息差红线拦截：未解锁角色 {speaker} 的对白出现敏感继承/遗嘱真相词“{hit.group(0)}”'
                    )
                if non_holders_present:
                    raise rr.RoundError(
                        f'信息差红线拦截：知情角色 {speaker} 禁止在未解锁听众面前主动说出继承/遗嘱真相词“{hit.group(0)}”'
                    )
            if kind == 'action':
                if speaker == '徐志北':
                    if non_holders_present and _DISCLOSURE_ACTION_RE.search(text) and not _HOST_INNER_RE.search(text):
                        raise rr.RoundError(
                            f'信息差红线拦截：主角动作向未解锁在场角色泄露了继承/遗嘱真相词“{hit.group(0)}”'
                        )
                elif speaker not in secret_holders:
                    raise rr.RoundError(
                        f'信息差红线拦截：未解锁角色 {speaker} 的动作出现敏感继承/遗嘱真相词“{hit.group(0)}”'
                    )
                elif non_holders_present and _DISCLOSURE_ACTION_RE.search(text):
                    raise rr.RoundError(
                        f'信息差红线拦截：知情角色 {speaker} 的动作向未解锁角色泄露了继承/遗嘱真相词“{hit.group(0)}”'
                    )
            if kind == 'narration' and non_holders_present:
                mentions_non_holder = any(p in text for p in non_holders_present)
                if (mentions_non_holder or _NARRATION_REVEAL_RE.search(text)) and not _HOST_INNER_RE.search(text):
                    raise rr.RoundError(
                        f'信息差红线拦截：旁白向未解锁在场角色泄露了继承/遗嘱真相词“{hit.group(0)}”'
                    )

    # 3. Su Wanqing residence lock warning when at main manor (on-stage or mentioned).
    if location == '徐家主宅':
        joined = '\n'.join(m['text'] for m in messages)
        if _SU_RESIDENCE_CONFLICT_RE.search(joined):
            warnings.append('驻地红线提示：检测到苏婉青主宅居住表述冲突，请核对是否误写成常住主宅。')

    return {'ok': True, 'warnings': warnings}

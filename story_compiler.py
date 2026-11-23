"""Deterministic source compiler, prefix freezer, stream parser, and zero-cost guardrails.

Reads canonical rule/lore/character/relationship/event sources without duplicating or mutating them,
producing cache-friendly frozen prefixes (Zone 0 + Zone 1), minimal per-turn deltas (Zone 2),
background settlement prompts, and deterministic red-line checks.
"""
import hashlib
import json
from pathlib import Path
import re

import injection_core as ic
import round_runtime as rr
import story_progression as sp
from relationship_query import RelationshipRegistry

PEOPLE = ('沈知韫', '苏婉青', '徐念薇')
OPTION_NAMES = {'A': '日常互动', 'B': '社交接触', 'C': '主动行为'}
STREAM_PROTOCOL_VERSION = 1

_GEN_TABLE_RE = re.compile(r'【注册表生成表开始】.*?【注册表生成表结束】', re.S)
_LIVE_FOOTER_RE = re.compile(r'\n*【正式互动入口适用边界】[^\n]*')
_CHAR_LIVE_FOOTER_RE = re.compile(r'\n*【正式连续互动】[^\n]*')
_LEGACY_PACE_RE = re.compile(r'\n*【完整回合兼容节奏】[^\n]*')
_LEGACY_V1_RE = re.compile(r'\n*【V1验收】[^\n]*')
_PARAM_HEADER_RE = re.compile(r'\n*【事件参数】[^\n]*')
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
    r'强吻|亲吻|舌吻|拥吻|轻吻|热吻|吻(?:上|住|下|向|过|了|进|着|落|她|在)|抚摸|爱抚|轻揉|揉捏|压倒|推倒|扑倒|抱上床|抱进卧室|上床|'
    r'脱衣|脱掉|褪下|掀起裙|解开衣|解开扣|大腿内侧|腿间|乳房|乳尖|酥胸|丰臀|私处|下身|小穴|穴口|'
    r'挺入|抽插|顶入|撞击|调教|侍奉|跪下含|含住|口交|指奸|后入|骑乘|内射|外射|吞精|自慰|自渎|换衣|洗澡|沐浴|走光|湿身|高潮|性爱|做爱|情欲|亲密接触'
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
_LEGACY_CRAFT_SENT_RE = re.compile(r'；?craft_note\s*默认不生成[^。]*。')
_LEGACY_SYSLOG_NOTE_RE = re.compile(r'（须在SYSTEM_LOG写明事由）|\(须在SYSTEM_LOG写明事由\)')
_LEGACY_120_NODE_RE = re.compile(r'\n*【节点长度与段落边界】[^\n]*(?:\n[^\n【]*120字[^\n]*)*')


def _digest_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _clean_text(text):
    return _MULTI_NL_RE.sub('\n\n', text).strip()


def _strip_kb_noise(content, keep_event_hint=False, mode='foreground'):
    text = _GEN_TABLE_RE.sub('', content)
    text = _LIVE_FOOTER_RE.sub('', text)
    if not keep_event_hint:
        text = _PARAM_HEADER_RE.sub('', text)
    text = _LEGACY_PACE_RE.sub('', text)
    text = _LEGACY_V1_RE.sub('', text)
    if mode == 'foreground':
        text = _LEGACY_120_NODE_RE.sub('', text)
        text = _LEGACY_CRAFT_SENT_RE.sub('。', text)
        text = text.replace('技法分析(归craft_note)', '技法分析')
        text = _LEGACY_SYSLOG_NOTE_RE.sub('', text)
        text = text.replace('每回合有效正文应推进意图包并完成一场戏', '每段有效正文应承接玩家意图并推进完整连贯微幕')
    elif mode == 'settlement':
        text = _LEGACY_STAMINA_COMP_RE.sub('', text)
    return _clean_text(text)


def _load_kb_entries(root, name):
    path = Path(root) / 'txt文件/知识库' / (name + '.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    return data.get('data', {}).get('entries', []) or data.get('entries', [])


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
    reg.verify_view()
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

    rows = [
        json.loads(line)
        for line in (root / 'txt文件/关系称谓查询.jsonl').read_text(encoding='utf-8').splitlines()
    ][1:]
    forms = {}
    for row in rows:
        speaker, listener = row.get('speaker'), row.get('listener')
        if speaker not in participant_set or listener not in related:
            continue
        occasions = {}
        for occ, odata in row.get('occasions', {}).items():
            selfs = [c['text'] for c in odata.get('self_candidates', []) if c['text'] not in ('', '我')]
            addrs = [
                c['text']
                for target in odata.get('targets', [])
                for c in target.get('address_candidates', [])
                if c['text'] not in ('', '你')
            ]
            occasions[occ[0]] = {'s': selfs, 'a': addrs}
        if occasions.get('f') == occasions.get('r') == occasions.get('b'):
            forms[f'{speaker}->{listener}'] = occasions['f']
        else:
            forms[f'{speaker}->{listener}'] = occasions

    return {
        'shared': shared,
        'secret_boundaries': {
            'known_only_by': known_by,
            'unknown_by_present': unknown_by_present,
        },
        'beliefs': beliefs,
        'forms': forms,
        'rule': '称谓为合法候选（f正式/r放松/b商务，s自称/a称呼），承接上下文可用我/你或省略；绝密仅限known_only_by本人，严禁向unknown_by_present泄露或碰巧知晓。',
    }


def compile_event_catalog(root, active_groups=None, live_mode=False):
    """Strip internal numeric calculation parameters; emit only valid tag whitelist & patterns."""
    raw = json.loads((Path(root) / 'txt文件/事件注册表.json').read_text(encoding='utf-8'))
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
    return catalog


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
        r'^徐承邺_([^\n：:]+)[：:]\s*警惕\s*(\d+)\s*\|\s*发现\s*(\d+)(?:\s*\|\s*发现几率\s*(\d+))?',
        memory_text or '', re.M,
    ):
        who = m.group(1).strip()
        v, d = int(m.group(2)), int(m.group(3))
        p = int(m.group(4)) if m.group(4) is not None else 0
        max_vig = max(max_vig, v)
        max_disc = max(max_disc, d)
        max_prob = max(max_prob, p)
        targets[who] = {'vigilance': v, 'discovery': d, 'prob': p}
        if v >= 20 or d > 0:
            details.append(f'{who}(警惕{v}/发现{d})')
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
    """Stable persistent-state gating for Zone 1 (never flips on transient per-turn text)."""
    vig = _parse_vigilance_state(memory_text)
    if vig['position'] != '外地' or vig['max_vigilance'] > 0 or vig['max_discovery'] > 0:
        return True
    location = (state or {}).get('location', '')
    cast = (state or {}).get('cast', [])
    if location in ('徐家主宅', '市中心顶层公寓') and '徐承邺' in cast:
        return True
    if location == '徐家主宅' and '苏婉青' in cast:
        return True
    return False


def _needs_intimate_zone1(state, memory_text=''):
    """Stable persistent-state gating for narrative.intimate in Zone 1 (protects KV cache)."""
    cast = (state or {}).get('cast', [])
    if not cast:
        return False
    panel_map = _parse_panel_map((state or {}).get('panels', []))
    buff_map = _parse_buffs_inline(memory_text)
    for name in cast:
        stats = panel_map.get(name, {})
        desire_m = re.match(r'-?\d+', str(stats.get('欲望', '0')))
        dep_m = re.match(r'-?\d+', str(stats.get('堕落', '0')))
        desire = int(desire_m.group(0)) if desire_m else 0
        dep = int(dep_m.group(0)) if dep_m else 0
        if desire >= 60 or dep >= 30:
            return True
        if any('体液锁定' in (b.get('name', '') + b.get('effect', '')) for b in buff_map.get(name, [])):
            return True
    return False


def _needs_intimate_turn(text='', selected=None):
    """Transient per-turn check for loading narrative.intimate in Zone 2 delta without touching Zone 1."""
    sel_text = selected.get('text', '') if isinstance(selected, dict) else ''
    return bool(_INTIMATE_TURN_RE.search((text or '') + '\n' + (sel_text or '')))


def _load_intimate_body(root):
    for entry in _load_kb_entries(Path(root), '叙事判断'):
        if entry.get('enabled', True) is not True:
            continue
        if _entry_key(entry) == 'narrative.intimate':
            return _strip_kb_noise(entry['content'], mode='foreground')
    return ''


def _needs_pregnancy_rules(state, memory_text='', extra_text=''):
    panel_text = '\n'.join((state or {}).get('panels', []))
    if re.search(r'怀孕\s+True|内射\s+[1-9]\d*次|持续_体液锁定', (memory_text or '') + '\n' + panel_text):
        return True
    if re.search(r'内射|外射|精液|怀孕|受孕|危险期|体液锁定', extra_text or ''):
        return True
    return False


def compile_knowledge_rules(root, state, memory_text='', extra_text='', mode='foreground'):
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
                blocks.append({'key': key, 'body': _strip_kb_noise(entry['content'], mode='foreground')})

    if mode in ('settlement', 'single'):
        for entry in _load_kb_entries(root, '系统标签类'):
            if entry.get('enabled', True) is not True:
                continue
            key = _entry_key(entry)
            # In dual-stage settlement, keep sys.pregnancy & sys.vigilance always available so Stage 1
            # autonomous developments never hit a missing settlement rule and Stage 2 prompt cache stays stable.
            if mode == 'single':
                if key == 'sys.pregnancy' and not preg_active:
                    continue
                if key == 'sys.vigilance' and not vig_active:
                    continue
            blocks.append({'key': key, 'body': _strip_kb_noise(entry['content'], mode='settlement')})

    return blocks


def compile_codex_runtime(root):
    """Deterministically slice runtime red-lines (Vol.0 §0~§3 & §5) from 全局执行法典.md."""
    raw = (Path(root) / 'txt文件/全局执行法典.md').read_text(encoding='utf-8')
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
    return _clean_text(body)


def compile_characters(root, cast, references=()):
    """Preserve 100% of character persona/appearance/speech/Fish tags, stripping repeated footer."""
    entries = _load_kb_entries(root, '角色类')
    ref_names = [r['name'] if isinstance(r, dict) else str(r) for r in references]
    ordered = list(dict.fromkeys([*cast, *ref_names, '徐志北']))
    cast_set = set(cast)
    result = []
    for name in ordered:
        found = [e['content'] for e in entries if '※索引key※ char.' + name in e.get('content', '')]
        if len(found) != 1:
            raise rr.RoundError('角色原文缺失或不唯一: ' + name)
        cleaned = _clean_text(_CHAR_LIVE_FOOTER_RE.sub('', found[0]))
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


def compile_state_qualitative_brief(state, memory_text='', include_tasks=False, include_points=False, intel_catalog=None):
    """Translate raw panel stats into rich qualitative narrative constraints without exposing formulas."""
    panels = (state or {}).get('panels', [])
    panel_map = _parse_panel_map(panels)
    buff_map = _parse_buffs_inline(memory_text)
    micro_map = rr._current_micro(memory_text) if (memory_text and '【当前激活微状态】' in memory_text) else {}
    intel_state = sp.parse_intel_block(memory_text)

    notes = []
    host = panel_map.get('系统宿主', {})
    if host:
        st = int(re.match(r'-?\d+', host.get('体力', '100')).group(0)) if re.match(r'-?\d+', host.get('体力', '100')) else 100
        st_desc = '偏低（注意体力消耗）' if st < 20 else ('中等' if st < 50 else '充沛')
        biz = int(re.match(r'-?\d+', host.get('商业嗅觉', '0')).group(0)) if re.match(r'-?\d+', host.get('商业嗅觉', '0')) else 0
        charm = int(re.match(r'-?\d+', host.get('魅力', '70')).group(0)) if re.match(r'-?\d+', host.get('魅力', '70')) else 70
        extra = f'，积分{host.get("积分", "0")}，经验值{host.get("经验值", "0")}' if include_points else ''
        notes.append(f'宿主状态：体力{st}({st_desc})，魅力{charm}，商业嗅觉{biz}[{_biz_sense_desc(biz)}]{extra}。')

    if intel_state['held']:
        name_map = {it['id']: it['name'] for it in (intel_catalog or {}).get('items', [])}
        held_labels = [name_map.get(iid, iid) for iid in intel_state['held']]
        lev_note = ''
        if intel_state.get('leverage_armed'):
            lev_name = name_map.get(intel_state['leverage_armed'], intel_state['leverage_armed'])
            lev_note = f'；已暗中备妥筹码「{lev_name}」作商业牵制（仅自然落于压迫感或底气，禁直呼机制词）'
        notes.append(f'宿主私下掌握的未动用商业线索：{"、".join(held_labels)}（仅宿主知晓，玩家未亮牌前NPC不可知晓{lev_note}）。')

    def _int_stat(raw_val, default=0):
        m = re.match(r'-?\d+', str(raw_val or ''))
        return int(m.group(0)) if m else default

    su_unlocked = bool(((state or {}).get('mechanics') or {}).get('su_affection_85_unlocked'))
    cast = (state or {}).get('cast', [])
    location = (state or {}).get('location', '')
    for name in cast:
        if name == '徐承邺':
            place_label = location or '徐家主宅'
            notes.append(f'徐承邺当轮态势：已抵达{place_label}且真实在场（可合法对白与动作；按监视态势、礼貌掌控欲与信息差边界推演，严禁直呼数值）。')
            continue
        stats = panel_map.get(name, {})
        if not stats:
            continue
        aff = _int_stat(stats.get('好感', '0'), 0)
        shame = _int_stat(stats.get('羞耻', '100'), 100)
        dep = _int_stat(stats.get('堕落', '0'), 0)
        desire = _int_stat(stats.get('欲望', '0'), 0)
        orgasm = _int_stat(stats.get('高潮', '0'), 0)
        npc_st = _int_stat(stats.get('体力', '100'), 100)
        passive = stats.get('被动', 'Lv.0')
        lv_m = re.search(r'Lv\.(\d+)', passive)
        lv_info = sp.passive_level_info(int(lv_m.group(1)) if lv_m else 0)
        flags = [f'对宿主被动{lv_info["tag"]}({lv_info["name"]}：{lv_info["effect"]})']

        char_buffs = buff_map.get(name, [])
        if char_buffs:
            b_desc = '、'.join(f'{b["name"]}(剩{b["turns"]}轮:{b["effect"]})' for b in char_buffs)
            flags.append('生效持久化状态：' + b_desc)

        if desire >= 85:
            flags.append('欲望处于高位滞留(≥85，呼吸与克制极难维持)')
        elif desire >= 80:
            flags.append('欲望触及80瓶颈(需更高心理压迫或诱因方能突破)')
        elif desire >= 70:
            flags.append('欲望明显躁动(≥70，情绪易失衡空耗)')
        if orgasm >= 70:
            flags.append(f'临近生理峰值(高潮累积{orgasm}%)')

        if npc_st < 15:
            flags.append('体力跌破15(断电余韵，需照顾与低声/气音收束)')
        elif npc_st < 40:
            flags.append('体力偏低(神态略显疲倦，支撑克制更耗心力)')

        ms = micro_map.get(name) or {}
        if ms.get('momentary_ease'):
            flags.append('短期微状态：刚经历短暂缓和，神色戒备略松但底线仍在')
        if ms.get('confusion_debt'):
            flags.append('短期微状态：心底留有未说破的局促与自我辩解余波')
        if ms.get('residual_tension'):
            flags.append('短期微状态：刚经历高压接触，呼吸与肢体仍留余韵张力')

        if name == '苏婉青':
            if su_unlocked or aff > 85:
                flags.append('好感天花板85已解锁(上限95)')
            else:
                flags.append('好感天花板85未解锁')
            if location == '徐家主宅' and (aff < 70 or shame > 80):
                flags.append('主宅探访见闻事后会向丈夫徐承邺汇报(眼线条件激活)')
        phys = ((state or {}).get('physiology') or {}).get(name) or {}
        if stats.get('怀孕') == 'True' or phys.get('pregnancy_stage') == 'confirmed':
            flags.append('已确诊怀孕(羞耻上限锁≤35，身体具孕期敏感与身份反差)')
        elif phys.get('pregnancy_stage') == 'latent':
            flags.append('早孕潜伏微兆(尚未知情确诊，偶现嗜睡/晨起微恶心/小腹微胀)')
        else:
            c_phase = phys.get('cycle_phase')
            if not c_phase:
                cur_day = int(((((state or {}).get('progression') or {}).get('runtime') or {}).get('clock') or {}).get('day') or 1)
                c_phase = ic.determine_cycle_phase(name, cur_day)
            if c_phase == '危险期':
                flags.append('生理周期：危险期')
            elif c_phase == '安全期' and (desire >= 55 or shame < 80):
                flags.append('生理周期：安全期')
        if int(phys.get('masturbation_trace', 0) or 0) > 0:
            flags.append('自渎余韵(近期曾暗中自慰泄欲，面对宿主易心虚闪躲或腿根发软)')
        if int(phys.get('unrelieved_streak', 0) or 0) >= 1:
            flags.append(f'欲求未平(连续{phys["unrelieved_streak"]}轮高欲未纾解)')
        notes.append(f'{name}当轮态势：好感{aff}/羞耻{shame}/堕落{dep}（{"；".join(flags)}；严禁在台词中直呼数值）。')

    vig = _parse_vigilance_state(memory_text)
    if vig['position'] != '外地' or vig['max_vigilance'] >= 30 or vig['max_discovery'] > 0 or vig['max_prob'] >= 70:
        detail = '、'.join(vig['hot']) if vig['hot'] else '低警惕'
        risk_clause = ''
        if vig['max_prob'] >= 70:
            risk_targets = '、'.join(vig['high_risk']) if vig['high_risk'] else '在场目标'
            risk_clause = f'；【高危暴露压迫】{risk_targets}发现几率达高危线，本轮须按将被发现/逼近查岗推进，不得写侥幸蒙混'
        notes.append(f'监视态势：徐承邺位置={vig["position"]}，关注={detail}{risk_clause}（未实际目击/来电前不凭数值凭空造实锤）。')
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


def normalize_protagonist_style(value):
    return 'silent' if str(value or '').strip().lower() == 'silent' else 'faithful'


def build_zone0_global(root, mode='dual_stream_v2', protagonist_style='faithful'):
    """Build globally frozen Zone 0 system prompt (goes into Operit card characterSetting)."""
    style = normalize_protagonist_style(protagonist_style)
    codex = compile_codex_runtime(root)
    world_rules = compile_knowledge_rules(root, {}, '', '', mode='foreground')
    # Only include constant/global world & narrative rules in Zone 0 (vigilance & intimate are gated on demand).
    global_kb = '\n\n'.join(
        item['body'] for item in world_rules
        if item['key'] not in ('narrative.vigilance', 'narrative.intimate')
    )

    if mode == 'dual_stream_v2':
        if style == 'faithful':
            protagonist_rule = (
                '   - 主角具身在场与忠实演绎（杜绝摄像机感）：每幕开头必须先用 1～2 句 [A:徐志北] 或 [N] 将玩家本轮抉择真实落位（写出动作细节、具体五感与克制心绪），'
                '中段互动中穿插 1～2 处 [A:徐志北] 自然微反应（抬眼、停手、放杯、承接视线）；'
                '当玩家点选概括性选项或未逐字写台词时，允许输出 1～2 句简短克制、100% 忠实于本轮玩家意图的 [D:徐志北] 发言（每句≤40字、单幕硬上限3句，前端静音不发声），形成有来有往的真实交锋；'
                '若玩家输入已自带直接引语，则保持原意仅补动作神态。严禁替徐志北新增超出原意的新决定、新承诺、烈度升级或未授权反派滤镜。\n'
            )
            action_line_rule = (
                '   [A:角色姓名] 归属明确的具体动作（角色姓名须为在场人物或徐志北；徐志北动作须紧扣本轮意图与同意图微动作，展现主角在场存在感与五感反馈；'
                '严禁在 [A:...] 中混入Fish英文标签；当女性角色处于高羞耻强装镇定而身体泄漏本能反应时，允许在关键动作词使用全角大括号 ｛表面端庄动作｜生理失控破绽｝ 标注反差）\n'
            )
            dialogue_line_rule = (
                '   [D:角色姓名] 角色台词（角色姓名须属于当前在场cast白名单；忠实演绎模式下允许最多3句严格贴合玩家本轮意图的简短 [D:徐志北] 发言且禁带Fish标签；'
                '严禁输出场外人物对白；只放纯开口台词、在场角色合法Fish英文方括号声学标签及可选 ｛表层违心台词｜真实潜台词｝，严禁在 [D:角色姓名] 内混入第三人称动作/神态旁白如“她端起来抿了一口，没抬眼：”且严禁加外层双引号“...”，任何动作必须拆分为独立的 [A:角色姓名] 行）\n'
            )
        else:
            protagonist_rule = (
                '   - 主角具身在场（仅动作感官模式）：严禁输出 [D:徐志北]，但每幕必须包含至少 2 处 [A:徐志北] 具身动作、间接口吻概括与具体五感描写，绝不把主角写成隐身摄像机。\n'
            )
            action_line_rule = (
                '   [A:角色姓名] 归属明确的具体动作（角色姓名须为在场人物或徐志北；徐志北动作仅限原输入授权及同意图微动作；即使玩家选项含“追问/只问/顺口问起/开口询问”，也严禁写 [D:徐志北]，只能用 [A:徐志北] 或 [N] 以间接动作概括，如“[A:徐志北] 他顺着话头只问了画展哪天开幕、评审换成了谁。”，再由在场角色 [D:角色姓名] 直接回答；严禁在 [A:...] 中混入Fish英文标签；当女性角色处于高羞耻强装镇定而身体泄漏本能反应时，允许在关键动作词使用全角大括号 ｛表面端庄动作｜生理失控破绽｝ 标注反差）\n'
            )
            dialogue_line_rule = (
                '   [D:角色姓名] 角色台词（角色姓名必须严格属于当前在场cast白名单；严禁写 [D:徐志北] 或场外人物对白；只放纯开口台词、合法Fish英文方括号声学标签及可选 ｛表层违心台词｜真实潜台词｝，严禁在 [D:角色姓名] 内混入第三人称动作/神态旁白如“她端起来抿了一口，没抬眼：”且严禁加外层双引号“...”，任何动作必须拆分为独立的 [A:角色姓名] 行）\n'
            )
        protocol = (
            '【前台演播协议 · 文字沉浸流式剧场（dual_stream_v2）】\n'
            '你是深渊天平正式互动的前台叙事演播者。本通道只专注剧情深度、人物主体性、语言指纹、感官血肉、信息差与Fish声学标签；'
            '数值结算、事件打标、时钟推进与记忆归档由后台结算通道独立完成，严禁在正文输出JSON、面板数值、事件标签、SYSTEM_LOG或审计长表。\n'
            '1. 文字沉浸篇幅与微幕戏核：\n'
            '   - 篇幅与节点数由当前戏核与文学呼吸自然决定（单行传输防呆上限4000字，不再以旧字数配额限制创作）：重要冲突、心理交锋、人物展露与亲密场可充分写透，日常快节奏亦可利落短答；唯一红线是严禁注水复读、严禁静态景物灌水、严禁替玩家代打关键行动或越权篡改玩家意图。\n'
            + protagonist_rule +
            '   - 一幕一位移（变完回不去）：每幕须产生信息增量、防备/关系变化、局势介入或具体约定中至少一项真实位移，坚决打破「礼貌问候—温和回应—继续问候」的乒乓客套循环。\n'
            '   - 隐性议程与合法破绽：在场角色须带着自己的处境、顾虑与正在处理的事行动，留出可被玩家接住的真实破绽或悬念钩子；每幕换开场直接进动作或对话，禁连续静态扫景；零出现AI套词（极其/骤然/不禁/不由得/眼眸/唇角/闪过一丝/勾起嘴角），模糊词（似乎/仿佛/好像）单幕至多1处。\n'
            '   - 客观外部变数：仅当本轮 delta 携带 surprise_directive 时，将其作为真实世界中自然发生的客观动静织入剧情并触发人物反应；若为 thread_spark（活体火花）须顺着锚点线头融合双词意象与软/硬动作；若为 offstage_clock（场外暗钟）且 owner_in_scene=false，严禁让该角色瞬移现身或输出 [D:姓名]，只可经物件/转述/旁白间接浮现；严禁使用 banned_channels 所列近期媒介套路，严禁提及「系统/随机/概率/导演/暗钟/触发」等机制词，严禁替主角代作应对决定。\n'
            '2. 逐行流式输出格式（严禁使用JSON、Markdown代码块、列表符号或额外前后解释；每行必须直接以英文方括号标签开头，严禁在方括号前加“旁白：/动作：/对白：/人物动作：/角色对白：”等中文前缀）：\n'
            '   [N] 旁白叙述正文（单行传输防呆≤4000字，不带说话人；行首直接写 [N]，严禁写成“旁白：[N]”，严禁含Fish标签）\n'
            + action_line_rule
            + dialogue_line_rule +
            '   格式示例（仅示意行首标签，严禁照抄示例内容）：\n'
            '   [N] 书房的冷气偏低，台灯光落在纸页边缘。\n'
            '   [A:沈知韫] 她合上文件夹，抬眼看向门边。\n'
            '   [D:沈知韫] [low restrained voice] 这么晚还没睡？\n'
            '   段末三轴推进抉择块（正文结束后必须另起一行，完整单行写 ---DECISION--- 切勿把横线与DECISION拆成两行；三条选项须指向三种实质不同走向，严禁写成同场景三种不同客套话）：\n'
            '   ---DECISION---\n'
            '   PROMPT: 点明本幕刚浮现的具体变数、信息缺口或两难（≤300字，禁「接下来怎么做」式空话）\n'
            '   A: 或 A[MOVE:登记地点]: 日常互动（5体力，中性无肢体接触）— 信息撬动/暗线换轨，或当本场戏眼已尽时提供收束离场/转场出口（≤500字）\n'
            '   B: 或 B[MOVE:登记地点]: 社交接触（10体力，礼仪范围内接触）— 具身破冰/试探微目标/顺势自然过渡（≤500字）\n'
            '   C: 或 C[MOVE:登记地点]: 主动行为（15体力）— 高能动性破局/正面戳破/亮牌博弈/语境成熟时的亲密推进（≤500字，不强塞越界或保证成功）\n'
            '   显式转场标记：当某选项实质包含离开当前地点前往 delta.available_destinations 中另一处开放地点时，必须在该选项字母后标注 [MOVE:登记地点]（例如 A[MOVE:公司]: 收起手机告别出门，直接去公司找沈知韫），严禁填当前所在地点或未开放地点。\n'
            '3. 只读文件工具边界：本轮已由程序交付完整精编设定与状态；不要为证明读取而重读任何packet或规则文件。'
            '仅当玩家明确追问超出当前窗口的极早旧史或需核对被省略归档时，才按delta中给出的精确许可路径与行号调用read_file_part补查。不写文件、不执行命令。\n'
            '4. 特定时刻微回响（防偏航红线）：仅当本轮输入携带 milestone_echo 字段时，允许在自然间隙或收束处用1句克制的氛围、感官或内心轻顿带过（如想起新入囊的小物或心头掠过一阵阶段落定的轻快）；'
            '严禁直呼「任务/委托/商城/积分/系统/数值」等机制词，严禁因此扭转玩家当前行动意图，严禁让NPC凭空知晓主角私有道具或系统信息。无 milestone_echo 时不得主动编造任务或商城提示。'
        )
    else:
        single_player_rule = (
            'messages中每幕须含徐志北具身动作与五感承接，忠实演绎模式下允许最多3句严格贴合玩家原意图的简短dialogue(speaker=="徐志北"，单句≤40字、禁Fish标签、禁新增决定或烈度升级)，'
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
            '普通付费action必须交完整7字段conditions；固定A/B/C不得重新判档（且A/B档严禁打任何C烈度_*标签）；host_events对象固定为“系统宿主”；vigilance_events.target只能填被徐承邺监视的人（沈知韫/苏婉青/徐念薇/徐志北），严禁填徐承邺本人；「首次/同质化免疫_回合2/3/小憩限次/空耗惩罚/生理周期」由后端确定性派生拦截；不写文件、不执行命令。\n'
            '若 memory.fact == "" 则 memory.transfers 必须交 {}；memory.compact 严禁带【数字】前缀或换行；需转移时严格依据 memory_transfer_sources.source_bodies 原文浓缩。\n'
            '进行中任务严禁驱动剧情；仅当delta携带milestone_echo时允许1句低侵入氛围轻顿且禁提系统词。'
            '若cost_preview.kind=="action"且tasks.current为空或status=="已完成"，结合task_whitelist_current按task_schema六键续接新任务（value严格大于当前值）；进行中或SYSTEM时resolution.task写""。'
            '仅当玩家在正文中明确亮牌动用 delta.held_intel 中某条情报时才填 resolution.intel_used；action回合可选填 resolution.director_echo 维护未完线头与暗钟，严禁编造。'
        )

    return _clean_text(f'{protocol}\n\n{codex}\n\n{global_kb}')


def build_zone1_scene(root, state, cast, references=(), memory_text='', extra_text='', mode='dual_stream_v2'):
    """Build scene-scoped semi-static Zone 1 system prompt (goes into Operit card otherContentChat)."""
    chars = compile_characters(root, cast, references)
    rels = compile_relationships(root, cast, references)
    location = (state or {}).get('location', '')
    offstage = [c['name'] for c in chars if c['scope'] == 'referenced_background_offstage']

    sections = [
        '【当前场景冻结锚点（同地同阵容不变）】\n'
        f'当前地点：{location}\n'
        f'实际在场可发言白名单(dialogue.speaker 仅限此列表)：{json.dumps(cast, ensure_ascii=False)}\n'
        f'仅背景提及(不在场，严禁写成dialogue或当场动作)：{json.dumps(offstage, ensure_ascii=False)}',
        '【在场及关联人物完整设定】\n' + '\n\n'.join(
            f'<<< {c["key"]} ({c["scope"]}) >>>\n{c["body"]}' for c in chars
        ),
        '【关系、知情隔离与称谓编译表】\n' + json.dumps(rels, ensure_ascii=False, separators=(',', ':')),
    ]

    # Zone 1 gating relies ONLY on persistent state (never transient extra_text) to preserve KV cache.
    if _needs_vigilance_rules(state, memory_text):
        vig_rules = [b for b in compile_knowledge_rules(root, state, memory_text, '', mode='foreground')
                     if b['key'] == 'narrative.vigilance']
        if vig_rules:
            sections.append('【本场激活监视叙事裁决】\n' + vig_rules[0]['body'])

    if _needs_intimate_zone1(state, memory_text):
        intimate_body = _load_intimate_body(root)
        if intimate_body:
            sections.append('【本场激活亲密与高压肢体描写技法】\n' + intimate_body)

    if mode == 'single_prefix_v2':
        sys_rules = compile_knowledge_rules(root, state, memory_text, extra_text, mode='settlement')
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


def build_user_delta(root, state, projection, history, new_history_only, text, selected,
                     resolved_op, intent_evidence, preview_cost, runtime, memory_text,
                     previous_error='', include_full_anchor=True, mode='dual_stream_v2',
                     omitted_archive=(), archive_index='', memory_index='',
                     required_sources=(), output_contract=None, resolution_policy=None,
                     operation_context=None, pending_echoes=(), weekday='',
                     breakout_hint=None, intel_catalog=None, director_roll=None,
                     protagonist_style='faithful'):
    """Build compact per-turn user message (tiny delta on turns 2..N, bounded anchor on turn 1)."""
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

    delta = {
        'mode': mode,
        'anchor': 'full_scene_start' if include_full_anchor else 'incremental_delta',
        'clock': clock,
        'weekday': cur_weekday,
        'stamina_before': (preview_cost or {}).get('before'),
        'location': location,
        'cast': cast,
        'scene_turns_in_place': scene_turns,
        'available_destinations': _build_available_destinations(root, location, cur_weekday, clock),
        'qualitative_state': brief,
        'selection': selected,
        'player_input': text,
        'operation_context': operation_context,
    }
    if scene_turns >= exit_threshold:
        if is_single:
            delta['scene_exit_hint'] = f'已在{location}连续停驻{scene_turns}幕：至少1个选项须提供推进时段或附带"operation":{{"code":"move_player","destination":"合法开放地点"}}的转场出口。'
        else:
            delta['scene_exit_hint'] = f'已在{location}连续停驻{scene_turns}幕：至少1个选项须提供推进时段或[MOVE:地点]转场出口。'
    if previous_error:
        delta['previous_validation_error'] = previous_error
    if not cast:
        delta['solo_scene_rule'] = '当前地点无其他在场角色：严禁输出任何 [D:...] 台词行；若出现来电或消息，请在 [N] 旁白中转述或用引号呈现。'
    if _mentions_vigilance(text) and not _needs_vigilance_rules(state, memory_text):
        delta['vigilance_turn_note'] = '本轮玩家提及徐承邺或监视相关词：遵循信息差与真实证据原则，未实际目击或来电前不凭空制造撞见或实锤。'
    sd = sp.format_surprise_directive(director_roll)
    if sd:
        delta['surprise_directive'] = sd
    if breakout_hint:
        delta['breakout_hint'] = breakout_hint
    is_erotic_roll = isinstance(director_roll, dict) and (
        director_roll.get('category') == 'erotic_accident'
        or str(director_roll.get('beat_id') or '').startswith(('BEAT-T1-EROTIC-', 'BEAT-T2-EROTIC-', 'BEAT-T3-EROTIC-', 'BEAT-T4-EROTIC-'))
    )
    if mode in ('dual_stream_v2', 'single_prefix_v2') and (_needs_intimate_turn(text, selected) or is_erotic_roll) and not _needs_intimate_zone1(state, memory_text):
        intimate_body = _load_intimate_body(root)
        if intimate_body:
            delta['intimate_craft_guide'] = intimate_body

    if include_full_anchor:
        raw_mem = projection['text']
        delta['player_private_memory'] = raw_mem if is_single else _strip_active_task_from_memory(raw_mem)
        delta['items'] = state.get('items', [])
        if is_single:
            delta['tasks'] = state.get('tasks')
        delta['accepted_history'] = history
    else:
        # Session already holds prior scene turns; only transmit current L1 + newly committed turns + inventory delta.
        current_ref = projection.get('current')
        current_l1 = ''
        if current_ref:
            lines = (memory_text or '').splitlines()
            current_l1 = '\n'.join(lines[current_ref['start_line'] - 1:current_ref['end_line']])
        delta['current_l1_memory'] = current_l1
        delta['items_count'] = len(state.get('items', []))
        if state.get('items'):
            delta['held_items'] = [{
                'id': i['id'], 'name': i['name'], 'qty': i['quantity'],
                'status': i['fields'].get('当前状态', ''),
                'remaining_turns': i.get('remaining_turns'),
                'desc': (i['fields'].get('描述', '') or '')[:60],
                'source': (i['fields'].get('备注', '') or '')[:48],
            } for i in state['items']]
        if is_single:
            delta['tasks'] = state.get('tasks')
        if new_history_only:
            delta['new_accepted_history'] = new_history_only

    if pending_echoes:
        delta['milestone_echo'] = {
            'events': [{'kind': e['kind'], 'summary': e['summary']} for e in pending_echoes],
            'rule': '一次性特定时刻微回响：仅允许在自然间隙或收束处用1句氛围/感官/内心轻顿带过，禁直呼任务/委托/商城/积分/系统词，禁扭转玩家意图，禁泄露给NPC。',
        }

    if projection.get('index') or omitted_archive:
        delta['optional_archive_lookup'] = {
            'memory_index_path': memory_index,
            'memory_refs': projection.get('index', [])[:8],
            'history_index_path': archive_index,
            'recent_omitted_history': list(omitted_archive)[-8:],
            'rule': '仅玩家主动追问极早旧事时按精确行号/路径调用read_file_part补查，否则无需读文件。',
        }
    if required_sources:
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
        delta['memory_transfer_sources'] = {
            'current_round': runtime['last_closed'] if runtime.get('phase') == 'resting' and runtime.get('last_closed') else runtime.get('memory_round', 1),
            'current_entry': projection.get('current'),
            'transfers': projection.get('transfers', {}),
            'source_bodies': _extract_transfer_source_bodies(memory_text, projection.get('transfers', {})),
            'limits': projection.get('limits'),
        }

    elif mode == 'dual_stream_v2':
        if style == 'faithful':
            delta['output_format'] = (
                '正文逐行以[N]/[A:名]/[D:在场角色名]开头：开场先用1～2句[A:徐志北]/[N]具身落位本轮抉择与五感，'
                '中段保留主角自然微反应，且允许最多2～3句严格贴合玩家原意图的简短[D:徐志北]发言（单句≤40字、禁Fish标签、禁越权新决定）；'
                '[D:名]只写纯台词，严禁混入“她端起杯子：”等第三人称动作旁白或外层引号；'
                '末尾另起一行完整单行写---DECISION---（切勿拆行），紧接PROMPT:与A:/B:/C:三项互异抉择。'
            )
        else:
            delta['output_format'] = (
                '正文逐行以[N]/[A:名]/[D:在场角色名]开头（严禁输出[D:徐志北]，但每幕须至少含2处[A:徐志北]具身动作与五感描写，玩家提问用[A:徐志北]或[N]间接动作概括；'
                '[D:名]只写纯台词，严禁混入“她端起杯子：”等第三人称动作旁白或外层引号）；'
                '末尾另起一行完整单行写---DECISION---（切勿拆行），紧接PROMPT:与A:/B:/C:三项互异抉择。'
            )

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


def build_settlement_spec(root, state, projection, text, selected, resolved_op, intent_evidence,
                          preview_cost, runtime, memory_text, resolution_policy, output_contract,
                          operation_context, required_sources=(), intel_catalog=None, director_roll=None):
    """Build static-system + compact-user specification for background SUMMARY Tools.Chat.call."""
    catalog = compile_event_catalog(root, live_mode=True)
    sys_rules = compile_knowledge_rules(root, state, memory_text, '', mode='settlement')
    system_prompt = _clean_text(
        '你是深渊天平后台结构化结算器（非作家，不改写剧情）。根据玩家行动、前台已生成的完整微幕正文与选项，'
        '严格提取事实并输出单个合法裸JSON对象，严禁代码围栏或前后解释。\n'
        '输出键必须恰为：operation、handoff、checks、resolution、quality_flags（仅当前台漏写或截断段末抉择时额外附带 fallback_decision）。\n'
        '硬性规则：\n'
        '1. 传输空值约定：无操作operation、无待处理handoff、无任务resolution.task、无睡眠起点resolution.sleep.start、'
        '免费SYSTEM的resolution.conditions、无NPC时的conditions.npc 均明确写空字符串""，不得省略键或留空。\n'
        '2. 分类与费用：遵循context.resolution_policy.category_policy；fixed_option必须原样返回required_category禁止重新判档（且当required_category为A或B时，events中严禁出现任何C烈度_轻度/中度/深度/重度标签，否则直接校验失败）；'
        'custom按实际成立行为判A/B/C不得免费；system固定为SYSTEM。严禁口算最终数值。\n'
        '3. 事件与依据：events每项含group/target/tags/evidence；只用下列合法标签原名；'
        'evidence必须是foreground_messages中某条text的逐字原样子串（若正文含｛表层｜潜台词｝，可引用原串或表层子串，严禁改字或引用decision选项）；'
        'host_events的target固定为"系统宿主"；'
        '⚠️【监视目标防错铁律】vigilance_events的target必须是【被徐承邺监视的对象】（仅限"沈知韫"/"苏婉青"/"徐念薇"/"徐志北"四选一），严禁填监视者"徐承邺"本人！若正文仅口头提及徐承邺的交代或行程而无实质警惕增减，请直接省略该条事件；'
        'depravity_events仅死亡查岗_沉沦期可填徐承邺（shame_events/ds_events/affection_events严禁填徐承邺），其余事件组target必须严格属于本场实际在场角色姓名。免费SYSTEM不得附带事件/任务/物品。'
        '「首次」「深度操控_首次」「内射_首次核爆」「同质化免疫_回合2/3」「小憩单日限次」「失眠防叠加」「状态_空耗惩罚」「生理_危险期」均由后端据持久化记录自动派生与拦截，模型只需如实标注本幕发生的基础事件。'
        '多档标签判准速查（严禁自造白名单外标签）：'
        'C烈度_轻度(越界言语挑逗/近距离施压/非敏感部位试探，仅限C档)、C烈度_中度(亲吻/隔衣贴合/轻度敏感部位触碰，仅限C档)、C烈度_深度(褪衣暴露/直接敏感带抚弄/口交侍奉，仅限C档)、C烈度_重度(实质性交/强行突破/高危越界结合，仅限C档)；'
        '高潮_轻度累积(初段爱抚/边缘挑弄)、高潮_中度累积(持续密集快感/深入刺激)、高潮_重度累积(临近绝顶/强烈痉挛)、触发高潮_绝顶清算(明确达到高潮绝顶)；'
        '刺激_视觉(近距凝视/暴露羞耻)、刺激_嗅觉(贴颈呼吸/体香气息)、刺激_听觉(耳语喘息/羞耻指令)、刺激_物理(实质肢体爱抚/器官接触)；'
        '消耗_轻微焦虑(短暂心虚/轻微防备)、消耗_日常劳作(常规奔波家务办公消耗)、消耗_剧烈抗拒(剧烈挣扎/高强度体力与心理拉扯)；'
        'VIGILANCE：目击确认(徐承邺亲眼撞见亲密越界)、证据实锤(掌握明确物证/影像/录音实锤)、异常行迹(衣冠凌乱/气息残留/深夜共处等反常迹象)、眼线汇报(苏婉青或旁人向徐承邺汇报异常)、'
        '降警惕_轻度(日常自然得体缓解疑心)、降警惕_中度(主动圆场打消明显疑虑)、降警惕_深度(彻底消痕或建立稳固信任屏障)、合理解释(对反常行迹给出无懈可击的理由)、转移注意(成功引开查岗焦点)、无异常回合(风平浪静且无新异常)。\n'
        '4. conditions：普通付费action必须交完整7字段对象(intensity/effective_progress/scene/npc/action_changed/stress_signals/breakout_triggered)，'
        'intensity须与category一致，无NPC仅npc写""；effective_progress仅当本幕产生了新信息/线索、态度或防备真实改变、明确约定、场景转移或有效事件时判true，纯礼貌寒暄/重复关怀/原地客套必须判false；免费SYSTEM的conditions写""。\n'
        '5. clock：按剧情实际经过单调向前，首次从第1天初始化；sleep.kind为overnight须连续>=6小时跨夜至05:00~12:59且evidence为正文子串。\n'
        '6. memory：fact仅记有长期因果价值的新事实（单行<=160字，严禁换行，无价值写""，不复述琐事/时间地点）；'
        '若叠加当前L1会超round_chars或当前L1已超限，交完整合并摘要memory.compact（单行<=600字，严禁带【1】等回合号前缀、严禁换行，取代追加且保留约定/待办/知情边界）；'
        '若 memory.fact == ""，则 memory.transfers 必须交 {}；'
        'transfers仅在context.memory_transfer_sources.transfers非空且本幕有新事实写入时，严格依据 context.memory_transfer_sources.source_bodies 原文浓缩提供。\n'
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
        '12. 活体世界回响（可选）：仅当 context.cost_preview.kind=="action" 时，可选填 resolution.director_echo 对象（无新线头或无变化直接省略或写""，严禁编造）：'
        '{"new_thread":{"who":["角色名"],"topic":"<=28字具体未完线头/承诺/破绽/藏物","tension":"soft|hard"}或"","close_thread":"本幕已实质了结的director_context.active_threads编号或""","clock_nudges":{"CLK_XXX":1或-1}或{},"used_channel":"若本幕真实出现外部变故，填director_context.channels_enum之一，否则"""}；'
        '只摘取正文已发生且具后续拉扯价值的具体钩子（纯寒暄不建线头），严禁泄露未解锁绝密。\n'
        '13. 段末抉择兜底补全（仅缺省时触发）：若 foreground_script 末尾已含完整 ---DECISION--- 与 A/B/C 三项抉择，请省略 fallback_decision；'
        '仅当 foreground_script 正文有效但漏写或截断了 ---DECISION--- / A/B/C 抉择时，补充 fallback_decision={"prompt":"点明当前局面的简短提示(<=300字)","options":[{"id":"A","text":"日常互动(<=500字)"},{"id":"B","text":"社交接触(<=500字)"},{"id":"C","text":"主动行为(<=500字)"}]}'
        '（三项须互不相同且承接本幕末尾局面；含跨地点转场时可给该项附带 "operation":{"code":"move_player","destination":"合法开放地点"}，无转场勿填 operation）。\n\n'
        '【合法事件标签白名单】\n'
        + json.dumps(catalog, ensure_ascii=False, separators=(',', ':'))
        + '\n\n【事件触发判定精简规则】\n'
        + '\n\n'.join(item['body'] for item in sys_rules)
    )

    current_l1 = ''
    current_ref = projection.get('current')
    if current_ref:
        lines = (memory_text or '').splitlines()
        current_l1 = '\n'.join(lines[current_ref['start_line'] - 1:current_ref['end_line']])

    settle_contract = {
        'operation': '',
        'handoff': '',
        'checks': output_contract['checks'],
        'quality_flags': [],
    }
    if output_contract.get('resolution') is not None:
        settle_contract['resolution'] = output_contract['resolution']
    panels = (state or {}).get('panels', [])
    icat = intel_catalog if intel_catalog is not None else sp.load_intel_catalog(root, optional=True)
    istate = sp.parse_intel_block(memory_text)
    held_intel = [
        {'id': it['id'], 'name': it['name'], 'targets': sorted(it['effects'].keys())}
        for it in icat.get('items', []) if it['id'] in istate['held']
    ]
    user_context = {
        'location': (state or {}).get('location'),
        'cast': (state or {}).get('cast', []),
        'presence': (state or {}).get('presence', {}),
        'panels': panels,
        'task_whitelist_current': _extract_task_whitelist_values(panels),
        'held_intel': held_intel,
        'director_context': sp.build_director_settlement_context(root, memory_text, director_roll=director_roll),
        'player_input': text,
        'selection': selected,
        'operation_context': operation_context,
        'cost_preview': preview_cost,
        'runtime': runtime,
        'resolution_policy': resolution_policy,
        'items': (state or {}).get('items', []),
        'tasks': (state or {}).get('tasks'),
        'current_l1_entry': current_l1,
        'memory_transfer_sources': {
            'current_round': runtime['last_closed'] if runtime.get('phase') == 'resting' and runtime.get('last_closed') else runtime.get('memory_round', 1),
            'current_entry': current_ref,
            'transfers': projection.get('transfers', {}),
            'source_bodies': _extract_transfer_source_bodies(memory_text, projection.get('transfers', {})),
            'limits': projection.get('limits'),
        },
        'required_sources': list(required_sources),
        'output_contract': settle_contract,
    }
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
        return [{'kind': 'narration', 'speaker': '', 'text': text}]
    if kind == 'action':
        cleaned = _LEADING_ASCII_FISH_RE.sub('', text).strip() or text
        return [{'kind': 'action', 'speaker': who, 'text': cleaned}]
    # kind == 'dialogue'
    if who == '徐志北':
        # Player is permanently muted; strip any stray acoustic Fish tags cleanly.
        text = _LEADING_ASCII_FISH_RE.sub('', text).strip() or text
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
                    if not _HOST_INNER_RE.search(text):
                        raise rr.RoundError(
                            f'信息差红线拦截：未解锁角色 {speaker} 的动作出现敏感继承/遗嘱真相词“{hit.group(0)}”'
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

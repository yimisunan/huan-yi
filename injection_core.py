# injection_core.py
# 一键注入系统永久核心（模块化后只维护此文件）
# 【纯本地注入架构升级版】接管日志物理写入与前端选项原生挂载
# 迭代历史见开发者功能/修订日志/

import copy
import os
import sys
import json
import re
import time
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
import save_store

DATA_DIR = os.path.join(BASE_DIR, "存档")
MEMORY_FILE = os.path.join(DATA_DIR, "全局记忆库.txt")
NPC_ROSTER_FILE = os.path.join(DATA_DIR, "次要NPC名册.txt")  # 已移除，保留常量避免外部导入报错
ITEM_FILE = os.path.join(DATA_DIR, "徐志北道具图鉴.txt")
DATA_JSON_FILE = os.path.join(BASE_DIR, "data.json")


EVENT_REGISTRY_PATH = globals().get('_EVENT_REGISTRY_SOURCE', os.path.join(BASE_DIR, 'txt文件', '事件注册表.json'))
_EVENT_REGISTRY_DATA = None
_EVENT_INDEX = None


def _event_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('事件注册表含重复键: ' + key)
        result[key] = value
    return result


def _load_event_registry():
    """Read one immutable registry snapshot per isolated engine instance."""
    global _EVENT_REGISTRY_DATA, _EVENT_INDEX
    if _EVENT_REGISTRY_DATA is not None:
        return _EVENT_REGISTRY_DATA
    with open(EVENT_REGISTRY_PATH, 'r', encoding='utf-8') as handle:
        raw = handle.read()
    def bad_number(value):
        raise ValueError('事件注册表不接受非有限数字: ' + value)
    data = json.loads(raw, object_pairs_hook=_event_pairs, parse_constant=bad_number)
    groups = ('shame_events', 'depravity_events', 'ds_events', 'affection_events', 'host_events', 'vigilance_events')
    if (not isinstance(data, dict) or set(data) != {'version', 'groups'}
            or type(data['version']) is not int or data['version'] != 1
            or not isinstance(data['groups'], dict) or set(data['groups']) != set(groups)):
        raise ValueError('事件注册表结构或版本非法')
    index = {}
    for group in groups:
        entries = data['groups'][group]
        if not isinstance(entries, list) or not entries:
            raise ValueError('事件组须为非空数组: ' + group)
        tags = set()
        for entry in entries:
            fields = {'id', 'tag', 'parameters', 'parameter_usage', 'description', 'pattern', 'shared_parameters'}
            if not isinstance(entry, dict) or set(entry) != fields:
                raise ValueError('事件定义字段非法: ' + group)
            ident, tag = entry['id'], entry['tag']
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Z]+_[0-9]{2}', ident) or ident in index:
                raise ValueError('事件内部ID重复或非法')
            if not isinstance(tag, str) or not tag.strip() or any(c in tag for c in '\r\n') or tag in tags:
                raise ValueError('事件标签重复或非法: ' + group)
            params, usage = entry['parameters'], entry['parameter_usage']
            if not isinstance(params, dict) or not isinstance(usage, dict) or set(params) != set(usage):
                raise ValueError('事件参数与用途不对应: ' + ident)
            for key, value in params.items():
                if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or type(value) not in (int, float):
                    raise ValueError('事件参数须为具名数值: ' + ident)
                if isinstance(value, float) and (value != value or abs(value) == float('inf')):
                    raise ValueError('事件参数不可为非有限数字')
                if not isinstance(usage[key], str) or not usage[key].strip():
                    raise ValueError('事件参数缺少用途')
            if not isinstance(entry['description'], str) or not entry['description'].strip():
                raise ValueError('事件缺少说明: ' + ident)
            pattern = entry['pattern']
            if tag.endswith('_X') and pattern is None:
                raise ValueError('模板事件缺少实际提交模式')
            if pattern is not None:
                if (group != 'host_events' or not tag.endswith('_X')
                        or pattern != re.escape(tag[:-1]) + r'[1-9]\d{0,8}'):
                    raise ValueError('事件模板模式非法: ' + ident)
                re.compile(pattern)
            tags.add(tag)
            index[ident] = entry
    for entry in index.values():
        shared = entry['shared_parameters']
        if (not isinstance(shared, list) or not all(isinstance(key, str) and key in index and key != entry['id'] for key in shared)
                or len(shared) != len(set(shared))):
            raise ValueError('共享参数引用非法')
        if any(index[key]['shared_parameters'] for key in shared):
            raise ValueError('共享参数不得循环或多级转引')
    _EVENT_REGISTRY_DATA, _EVENT_INDEX = data, index
    return data


def _event_tag(ident):
    _load_event_registry()
    return _EVENT_INDEX[ident]['tag']


def _event_param(ident, key):
    _load_event_registry()
    return _EVENT_INDEX[ident]['parameters'][key]


def _event_accepts(group, tag):
    for entry in _load_event_registry()['groups'][group]:
        if entry['pattern'] is not None:
            if re.fullmatch(entry['pattern'], tag):
                return True
        elif tag == entry['tag']:
            return True
    return False


def _event_is_template(group, tag):
    return any(e['pattern'] is not None and tag == e['tag'] for e in _load_event_registry()['groups'][group])


def _render_event_table(group, include_parameters=True):
    """Generate model-visible spelling and numeric display from the loaded registry."""
    entries = _load_event_registry()['groups'][group]
    lines = ['【' + group.upper() + '】' + ' / '.join(e['tag'] for e in entries)]
    if include_parameters:
        for entry in entries:
            items = [key + '=' + str(value) + '（' + entry['parameter_usage'][key] + '）'
                     for key, value in entry['parameters'].items()]
            for ident in entry['shared_parameters']:
                shared = _EVENT_INDEX[ident]
                items.append('共享' + shared['tag'] + '的参数（同源引用）')
            details = '；'.join(items) if items else '条件/修饰标签；按既有通用规则处理'
            if entry['pattern']:
                details += '；实际提交模式=' + entry['pattern']
            lines.append('- ' + entry['tag'] + '：' + details)
    return '\n'.join(lines)


_SENSUAL_BUFF_RE = re.compile(
    r'温热精油|暖香微醺|微醺燥热|感官放大|精油|香薰|催情|微醺|燥热|酥麻|情趣|暖香|迷情'
)


def _has_sensual_buff(char_buffs):
    """True when any active persistent buff on the heroine is a sensual/arousal amplifier (static SHOP or AI-restocked DYN-*)."""
    if not isinstance(char_buffs, list):
        return False
    for b in char_buffs:
        if not isinstance(b, dict):
            continue
        blob = f"{b.get('name', '')} {b.get('effect', '')}"
        if _SENSUAL_BUFF_RE.search(blob):
            return True
    return False


CHARM_TIERS = (
    {
        'tier': 0, 'min': 0, 'max': 67, 'name': '气场受挫', 'next_at': 68,
        'aff_bonus': 0, 'violation_mitigation': 0.0, 'deep_mitigation': 0.0,
        'shame_extra_drop': 0, 'orgasm_mult_bonus': 0.0, 'shop_discount': 1.0,
        'release_vigor_cost': 14, 'bt_floor': 75, 'brief': '近期失态令从容气度略显动摇',
        'summary': '气场偏弱（释放耐力-14 · 魅力突破门限75；重整至 68 恢复常态，75 起解锁高阶增益）',
    },
    {
        'tier': 1, 'min': 68, 'max': 74, 'name': '清俊克制', 'next_at': 75,
        'aff_bonus': 0, 'violation_mitigation': 0.0, 'deep_mitigation': 0.0,
        'shame_extra_drop': 0, 'orgasm_mult_bonus': 0.0, 'shop_discount': 1.0,
        'release_vigor_cost': 12, 'bt_floor': 70, 'brief': '气度沉稳克制',
        'summary': '稳健起步（升至 75 阶解锁破冰好感+1、轻中越界减罚25%、商城9折）',
    },
    {
        'tier': 2, 'min': 75, 'max': 84, 'name': '锋芒初显', 'next_at': 85,
        'aff_bonus': 1, 'violation_mitigation': 0.25, 'deep_mitigation': 0.0,
        'shame_extra_drop': 0, 'orgasm_mult_bonus': 0.0, 'shop_discount': 0.90,
        'release_vigor_cost': 11, 'bt_floor': 60, 'brief': '高魅力压场：临近压迫与目光停留具显著磁吸感，正面破冰更易松动防备',
        'summary': '正面好感+1 · 轻中越界减罚25% · 魅力突破门限60(+2欲) · 商城9折 · 释放耐力-11',
    },
    {
        'tier': 3, 'min': 85, 'max': 94, 'name': '磁吸掌控', 'next_at': 95,
        'aff_bonus': 1, 'violation_mitigation': 0.40, 'deep_mitigation': 0.0,
        'shame_extra_drop': 1, 'orgasm_mult_bonus': 0.08, 'shop_discount': 0.85,
        'release_vigor_cost': 9, 'bt_floor': 60, 'brief': '极强磁吸掌控：贴近半步即可令对方呼吸失拍，亲密节奏拿捏游刃有余',
        'summary': '正面好感+1 · 轻中越界减罚40% · C档破防额外-1羞耻 · 高潮+8% · 商城85折 · 释放耐力-9',
    },
    {
        'tier': 4, 'min': 95, 'max': 100, 'name': '深渊魅影', 'next_at': None,
        'aff_bonus': 2, 'violation_mitigation': 0.50, 'deep_mitigation': 0.20,
        'shame_extra_drop': 2, 'orgasm_mult_bonus': 0.15, 'shop_discount': 0.85,
        'release_vigor_cost': 8, 'bt_floor': 60, 'brief': '深渊魅影气场：极具压倒性荷尔蒙引力，高羞耻防线亦会在凝视与低语下先一步发软',
        'summary': '正面好感+2 · 轻中越界减罚50%/重度20% · C档额外-2羞耻 · 高潮+15% · 商城85折 · 释放耐力-8',
    },
)

BODY_DEV_LEVEL_LABELS = {0: '生涩防备', 1: '敏感初开', 2: '熟稔沉溺', 3: '彻底开发'}
MAX_BODY_ACTS_PER_TURN = 2

_BODY_ACT_PATTERNS = {
    'oral': re.compile(
        r'口交|深喉|吞精|含住[^\n。！？]{0,8}(?:舔|吮|吞|弄|鸡巴|肉棒|龟头|阳具|乳头|奶头)|'
        r'(?:舔|吮|吸|吃|含)[^\n。！？]{0,8}(?:鸡巴|肉棒|龟头|阴蒂|小穴|骚逼|嫩逼)|'
        r'唇舌[^\n。！？]{0,8}(?:侍奉|包裹|舔)|舌尖[^\n。！？]{0,6}(?:绕|舔|勾)'
    ),
    'hand': re.compile(
        r'手交|套弄|撸动|纤手[^\n。！？]{0,8}(?:握|抚|揉|侍奉)|握住[^\n。！？]{0,8}(?:上下|缓缓|揉搓|鸡巴|肉棒)|'
        r'(?:撸|套弄|揉搓|把玩)[^\n。！？]{0,8}(?:鸡巴|肉棒|龟头)|十指相扣[^\n。！？]{0,10}(?:磨|压|吻)'
    ),
    'chest': re.compile(
        r'乳交|胸推|夹住[^\n。！？]{0,8}(?:磨|蹭|耸|鸡巴|肉棒)|'
        r'(?:揉捏|揉|捏|摸|抓|掐|搓|托|捧|吮吸|含住|舔|吮|轻咬|咬)[^\n。！？]{0,8}(?:胸|胸部|乳|乳房|双乳|奶子|大奶|奶头|乳头|乳晕|峰|尖)|'
        r'(?:奶子|大奶|乳房|双乳|胸部|乳头|奶头)[^\n。！？]{0,8}(?:被揉|被捏|被摸|被抓|被掐|被吮|被舔|变形|挤出|贴|压|晃)|'
        r'锁骨[^\n。！？]{0,8}(?:舔|吮|吻痕)'
    ),
    'foot': re.compile(r'足交|黑丝[^\n。！？]{0,8}(?:踩|蹭|勾|抚|脱)|(?:玉足|足弓|足心|脚背|脚踝|脚趾)[^\n。！？]{0,10}(?:吻|舔|吮|揉|握|踩|蹭)'),
    'core': re.compile(
        r'内射|外射|素股|抽插|顶弄|指尖探入|深处撞击|整根(?:没入|进出|顶|插|操)|'
        r'(?:插入|进入|插进|顶进|捅进|操进|肏进|干进|抠进)[^\n。！？]{0,8}(?:体内|深处|花|湿热|小穴|穴口|骚逼|嫩逼|逼)|'
        r'(?:操|肏|干|插|捅|顶|抠|撞)[^\n。！？]{0,8}(?:小穴|骚逼|嫩逼|穴口|穴肉|阴蒂|逼)|'
        r'(?:鸡巴|肉棒|龟头)[^\n。！？]{0,10}(?:顶进|插进|操进|捅进|没入|抵住|进出|抽插|埋进|撞|操|肏|磨蹭)'
    ),
}


def charm_tier_info(charm):
    val = max(0, min(100, int(charm or 0)))
    for row in CHARM_TIERS:
        if row['min'] <= val <= row['max']:
            return dict(row, charm=val)
    return dict(CHARM_TIERS[0], charm=val)


def body_dev_level(score):
    val = max(0, min(100, int(score or 0)))
    if val >= 80:
        return 3
    if val >= 50:
        return 2
    if val >= 20:
        return 1
    return 0


def _prioritize_body_zones(heroine, zones, limit=MAX_BODY_ACTS_PER_TURN):
    clean = list(dict.fromkeys(z for z in (zones or ()) if z in save_store.BODY_ZONES))
    if len(clean) <= limit:
        return clean
    sig = save_store.HEROINE_SIGNATURE_ZONES.get(heroine)
    def _rank(z):
        if z == sig:
            return 0
        if z == 'core':
            return 1
        return 2
    return sorted(clean, key=_rank)[:limit]


def infer_body_acts_from_prose(prose_text, events, explicit_acts=None):
    """Merge Stage 2 body_acts with deterministic prose fallback (capped to 2 focus zones per heroine)."""
    out = {}
    if isinstance(explicit_acts, dict):
        for who, zones in explicit_acts.items():
            if who in save_store.HEROINES and isinstance(zones, list):
                clean = list(dict.fromkeys(z for z in zones if z in save_store.BODY_ZONES))[:MAX_BODY_ACTS_PER_TURN]
                if clean:
                    out[who] = clean
    text = str(prose_text or '')
    if not text:
        return out
    shame_ev = (events or {}).get('shame_events') or {}
    ds_ev = (events or {}).get('ds_events') or {}
    intimate_s = {
        _event_tag('SHAME_01'), _event_tag('SHAME_02'), _event_tag('SHAME_03'),
        _event_tag('SHAME_04'), _event_tag('SHAME_05'), _event_tag('SHAME_06'),
        _event_tag('SHAME_07'), _event_tag('SHAME_08'), _event_tag('SHAME_09'),
    }
    intimate_d = {_event_tag('DS_04'), _event_tag('DS_14'), _event_tag('DS_15'), _event_tag('DS_16'), _event_tag('DS_17')}
    engaged = [
        h for h in save_store.HEROINES
        if (set(shame_ev.get(h) or ()) & intimate_s) or (set(ds_ev.get(h) or ()) & intimate_d)
    ]
    if not engaged:
        return out
    detected = [z for z, pat in _BODY_ACT_PATTERNS.items() if pat.search(text)]
    if not detected:
        return out
    for h in engaged:
        if h not in out:
            if len(engaged) == 1 or h in text:
                out[h] = _prioritize_body_zones(h, detected, limit=MAX_BODY_ACTS_PER_TURN)
    return out


def derive_host_fetishes(body_dev, keepsakes):
    """Deterministically derive readable kink/fetish imprints from sustained development & trophy collection."""
    bd = body_dev if isinstance(body_dev, dict) else {}
    ks = keepsakes if isinstance(keepsakes, list) else []
    marks = []
    foot_max = max((int((bd.get(h) or {}).get('foot', 0) or 0) for h in save_store.HEROINES), default=0)
    chest_max = max((int((bd.get(h) or {}).get('chest', 0) or 0) for h in save_store.HEROINES), default=0)
    hand_max = max((int((bd.get(h) or {}).get('hand', 0) or 0) for h in save_store.HEROINES), default=0)
    oral_max = max((int((bd.get(h) or {}).get('oral', 0) or 0) for h in save_store.HEROINES), default=0)
    core_max = max((int((bd.get(h) or {}).get('core', 0) or 0) for h in save_store.HEROINES), default=0)
    if int((bd.get('沈知韫') or {}).get('foot', 0) or 0) >= 20 or foot_max >= 25 or any(k.get('kind') == 'stockings' for k in ks if isinstance(k, dict)):
        marks.append('足踝黑丝控')
    if int((bd.get('苏婉青') or {}).get('chest', 0) or 0) >= 20 or chest_max >= 25 or any(k.get('kind') == 'bra' for k in ks if isinstance(k, dict)):
        marks.append('胸乳沉溺')
    if int((bd.get('徐念薇') or {}).get('hand', 0) or 0) >= 20 or hand_max >= 25:
        marks.append('纤手执念')
    if oral_max >= 30:
        marks.append('口舌侍奉控')
    if len(ks) >= 2 or any(isinstance(k, dict) and k.get('method') == 'stolen' and int(k.get('interactions') or 0) >= 1 for k in ks):
        marks.append('贴身私藏癖')
    if core_max >= 45:
        marks.append('深处支配欲')
    return marks[:6]


ACTION_ECONOMY_FLOOR = {"A": (2, 2), "B": (3, 2), "C": (4, 3)}
BODY_DEV_ECON_REWARDS = {1: (6, 5), 2: (10, 8), 3: (15, 12)}
SYNCED_CLIMAX_ECON_REWARD = (10, 8)
KEEPSAKE_NEW_ECON_REWARD = (6, 4)


def process_host_system(host_events, shame_events, memory_file, *, action_floor=None):
    """
    宿主核心引擎：三轨主次协同结算、连续守护独立入账、有效行动保底、动态体力代偿与魅力精进
    """
    if not host_events and not shame_events and not action_floor:
        return {}
    if not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    match_host = re.search(r"\[系统宿主\].*?积分\s*(-?\d+).*?经验值\s*(-?\d+).*?体力\s*(-?\d+).*?商业嗅觉\s*(-?\d+)", content)
    if not match_host:
        return {}
    match_charm = re.search(r"\[系统宿主\].*?魅力\s*(-?\d+)", content)
        
    cur_pts = int(match_host.group(1))
    cur_exp = int(match_host.group(2))
    cur_sta = int(match_host.group(3))
    cur_biz = int(match_host.group(4))
    cur_charm = int(match_charm.group(1)) if match_charm else 70
    
    # 1. 三轨主次协同结算 + HOST_07 连续守护独立里程碑（同经济标签单轮去重防刷）
    track1 = {"pts": 0, "exp": 0, "biz": 0, "name": "堕落侵蚀"}
    track2 = {"pts": 0, "exp": 0, "biz": 0, "name": "日常温馨"}
    track3 = {"pts": 0, "exp": 0, "biz": 0, "name": "商业权力"}
    guard_bonus = {"pts": 0, "exp": 0}
    seen_econ_tags = set()
    
    if host_events:
        for tag in host_events:
            if tag in seen_econ_tags:
                continue
            if tag == _event_tag('HOST_01'):
                seen_econ_tags.add(tag)
                track1["pts"] += _event_param('HOST_01', 'track1_pts_01'); track1["exp"] += _event_param('HOST_01', 'track1_exp_02')
            elif tag == _event_tag('HOST_02'):
                seen_econ_tags.add(tag)
                track1["pts"] += _event_param('HOST_02', 'track1_pts_01'); track1["exp"] += _event_param('HOST_02', 'track1_exp_02')
            elif tag == _event_tag('HOST_03'):
                seen_econ_tags.add(tag)
                track1["pts"] += _event_param('HOST_03', 'track1_pts_01'); track1["exp"] += _event_param('HOST_03', 'track1_exp_02')
            elif tag == _event_tag('HOST_04'):
                seen_econ_tags.add(tag)
                track1["pts"] += _event_param('HOST_04', 'track1_pts_01'); track1["exp"] += _event_param('HOST_04', 'track1_exp_02')
            elif tag == _event_tag('HOST_05'):
                seen_econ_tags.add(tag)
                track2["pts"] += _event_param('HOST_05', 'track2_pts_01'); track2["exp"] += _event_param('HOST_05', 'track2_exp_02')
            elif tag == _event_tag('HOST_06'):
                seen_econ_tags.add(tag)
                track2["pts"] += _event_param('HOST_06', 'track2_pts_01'); track2["exp"] += _event_param('HOST_06', 'track2_exp_02')
            elif tag == _event_tag('HOST_07'):
                seen_econ_tags.add(tag)
                guard_bonus["pts"] += _event_param('HOST_07', 'track2_pts_01'); guard_bonus["exp"] += _event_param('HOST_07', 'track2_exp_02')
            elif tag == _event_tag('HOST_08'):
                seen_econ_tags.add(tag)
                track2["pts"] += _event_param('HOST_08', 'track2_pts_01'); track2["exp"] += _event_param('HOST_08', 'track2_exp_02')
            elif tag == _event_tag('HOST_09'):
                seen_econ_tags.add(tag)
                track3["pts"] += _event_param('HOST_09', 'track3_pts_01'); track3["exp"] += _event_param('HOST_09', 'track3_exp_02'); track3["biz"] += _event_param('HOST_09', 'track3_biz_03')
            elif tag == _event_tag('HOST_10'):
                seen_econ_tags.add(tag)
                track3["pts"] += _event_param('HOST_10', 'track3_pts_01'); track3["exp"] += _event_param('HOST_10', 'track3_exp_02'); track3["biz"] += _event_param('HOST_10', 'track3_biz_03')
            elif tag == _event_tag('HOST_11'):
                seen_econ_tags.add(tag)
                track3["pts"] += _event_param('HOST_11', 'track3_pts_01'); track3["exp"] += _event_param('HOST_11', 'track3_exp_02'); track3["biz"] += _event_param('HOST_11', 'track3_biz_03')

    tracks = sorted([track1, track2, track3], key=lambda t: (t["pts"], t["exp"]), reverse=True)
    best_track = tracks[0]
    strategist_bonus = (cur_biz >= 80)

    pts_gain = best_track["pts"]
    exp_gain = best_track["exp"]
    synergy_names = []
    for sec in tracks[1:]:
        if sec["pts"] > 0 or sec["exp"] > 0:
            pts_gain += int(round(sec["pts"] * 0.5))
            exp_gain += int(round(sec["exp"] * 0.5))
            synergy_names.append(sec["name"])

    if (pts_gain > 0 or exp_gain > 0) and strategist_bonus:
        if pts_gain > 0:
            pts_gain += max(1, int(round(pts_gain * 0.15)))
        if exp_gain > 0:
            exp_gain += max(1, int(round(exp_gain * 0.15)))

    floor_applied = False
    if action_floor:
        f_pts = max(0, int(action_floor[0] or 0))
        f_exp = max(0, int(action_floor[1] or 0))
        if f_pts > pts_gain or f_exp > exp_gain:
            pts_gain = max(pts_gain, f_pts)
            exp_gain = max(exp_gain, f_exp)
            floor_applied = True

    total_pts_gain = pts_gain + guard_bonus["pts"]
    total_exp_gain = exp_gain + guard_bonus["exp"]
    if total_pts_gain > 0 or total_exp_gain > 0:
        cur_pts += total_pts_gain
        cur_exp += total_exp_gain
        parts = []
        if best_track["pts"] > 0 or best_track["exp"] > 0:
            syn_note = f"+{'/'.join(synergy_names)}×50%" if synergy_names else ""
            bonus_note = "（深局棋手+15%）" if strategist_bonus else ""
            parts.append(f"【{best_track['name']}】主轨{syn_note}{bonus_note}")
        if floor_applied:
            parts.append("有效推进保底")
        if guard_bonus["pts"] > 0 or guard_bonus["exp"] > 0:
            parts.append(f"连续守护独立+{guard_bonus['pts']}分/+{guard_bonus['exp']}经")
        print(f" 🏆 [宿主引擎] 经济结算（{' / '.join(parts)}）：积分+{total_pts_gain} 经验+{total_exp_gain}")

    # 商业嗅觉独立入账（不再被更高积分的情感/侵蚀轨道吞没，单轮上限 +20）
    biz_gain = min(20, max(0, int(track3["biz"])))
    if biz_gain > 0:
        cur_biz += biz_gain
        print(f" 📈 [宿主引擎] 商业嗅觉独立结算 +{biz_gain}")

    # 2. 商城动态扣费、体力与魅力结算
    charm_boosted = False
    if host_events:
        for tag in host_events:
            if tag.startswith(_event_tag('HOST_12')[:-1]):
                try:
                    cost = int(tag.split("_")[1])
                    cur_pts -= cost
                    print(f" 🛒 [宿主引擎] 商城兑换，扣除 {cost} 积分。")
                except (ValueError, TypeError):
                    pass
            elif tag == _event_tag('HOST_13'): cur_sta -= _event_param('HOST_13', 'cur_sta_01')
            elif tag == _event_tag('HOST_14'): cur_sta -= _event_param('HOST_14', 'cur_sta_01')
            elif tag == _event_tag('HOST_15'): cur_sta = _event_param('HOST_15', 'cur_sta_01')
            elif tag == _event_tag('HOST_16') and not charm_boosted:
                cur_charm += _event_param('HOST_16', 'cur_charm_01')
                charm_boosted = True
                print(f" ✨ [宿主引擎] 触发【优雅掌控_魅力精进】，宿主魅力 +{ _event_param('HOST_16', 'cur_charm_01') } -> {min(100, cur_charm)}")
            
    # 3. 跨模块肾上腺素监控
    adrenaline = False
    if host_events and (_event_tag('HOST_03') in host_events or _event_tag('HOST_04') in host_events):
        adrenaline = True
    if shame_events:
        for tags in shame_events.values():
            if _event_tag('SHAME_07') in tags:
                adrenaline = True
                
    if adrenaline:
        cur_sta += 30
        print(f" 🩸 [宿主引擎] 目标防线崩塌！宿主获得肾上腺素奖励：体力 +30")
        
    cur_sta = min(100, max(0, cur_sta))
    cur_biz = min(100, max(0, cur_biz))
    cur_charm = min(100, max(0, cur_charm))
    
    return {
        "积分": cur_pts,
        "经验值": cur_exp,
        "体力": cur_sta,
        "魅力": cur_charm,
        "商业嗅觉": cur_biz
    }

def process_shame_system(shame_events, memory_file, *, privacy='open_public', host_charm=70, body_acts=None):
    """
    语义化规则包：羞耻系统后台自动化物理计算引擎
    将 AI 前端的打标（如 'C烈度_轻度', '首次', '内射_首次核爆' 等）转换为绝对数值计算，
    支持堕落乘数、被动 Lv.3 疲倦破防、被动 Lv.4 防线支配、高魅力破防、招牌敏感带穿透、隐私潜行压迫加成、首杀附加、同质化免疫与堕落侵蚀上限夹紧。
    """
    if not shame_events or not os.path.exists(memory_file):
        return {}
    
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    computed_shame_changes = {}
    is_stealth_taboo = privacy in ('thin_wall', 'under_cover')
    charm_info = charm_tier_info(host_charm)
    acts_map = body_acts if isinstance(body_acts, dict) else {}
    
    for char_name, tags in shame_events.items() if shame_events else []:
        if not tags or not isinstance(tags, list):
            continue
        
        # 从当前记忆库中正则读取该角色当前的 羞耻、堕落、体力、怀孕 与 被动等级
        shame_match = re.search(rf"\[{re.escape(char_name)}\].*?羞耻\s*(-?\d+)", content)
        depravity_match = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(-?\d+)", content)
        sta_match = re.search(rf"\[{re.escape(char_name)}\].*?体力\s*(-?\d+)", content)
        preg_match = re.search(rf"\[{re.escape(char_name)}\].*?怀孕\s*(True|False)", content)
        pas_match = re.search(rf"\[{re.escape(char_name)}\].*?被动\s*Lv\.?(\d+)", content)
        
        if not shame_match:
            continue
        
        current_shame = int(shame_match.group(1))
        current_depravity = int(depravity_match.group(1)) if depravity_match else 0
        current_sta = int(sta_match.group(1)) if sta_match else 100
        is_pregnant = bool(preg_match and preg_match.group(1) == "True")
        cur_passive = int(pas_match.group(1)) if pas_match else 0
        erosion_coeff = 0.7 if cur_passive >= 4 else 0.6
        shame_cap = max(0, 100 - int(current_depravity * erosion_coeff))
        if is_pregnant or _event_tag('SHAME_10') in tags:
            shame_cap = min(shame_cap, _event_param('SHAME_10', 'shame_cap_02'))
        
        # 1. 状态锁与极值判定
        if _event_tag('SHAME_11') in tags or _event_tag('SHAME_12') in tags or _event_tag('SHAME_13') in tags:
            print(f" [羞耻引擎] {char_name} 处于冻结/死寂/解离锁状态，当回合羞耻停止下降。")
            continue
            
        if _event_tag('SHAME_14') in tags:
            rebound_val = current_shame + _event_param('SHAME_14', 'rebound_val_01')
            rebound_val = min(shame_cap, _event_param('SHAME_14', 'rebound_val_02'), max(_event_param('SHAME_14', 'rebound_val_03'), rebound_val))
            computed_shame_changes[char_name] = rebound_val
            print(f" [羞耻引擎] {char_name} 触发【耻感反弹_苏醒】，羞耻度回升至 {rebound_val} (堕落侵蚀上限 {shame_cap})。")
            continue
            
        # 2. 基础衰减分值计算（拆分 C 烈度与特殊事件，防同质化免疫误伤内射/查岗/怀孕/自渎撞破）
        c_delta = 0
        special_delta = 0
        is_first = _event_tag('SHAME_17') in tags
        
        for tag in tags:
            # A/B烈度零羞耻（日常态）；亲密进行态允许 B 档携带轻/中度亲密推进
            if tag == _event_tag('SHAME_01'): c_delta -= _event_param('SHAME_01', 'base_delta_01')
            elif tag == _event_tag('SHAME_02'): c_delta -= (_event_param('SHAME_02', 'base_delta_01') if is_first else _event_param('SHAME_02', 'base_delta_02'))
            elif tag == _event_tag('SHAME_03'): c_delta -= (_event_param('SHAME_03', 'base_delta_01') if is_first else _event_param('SHAME_03', 'base_delta_02'))
            elif tag == _event_tag('SHAME_04'): c_delta -= (_event_param('SHAME_04', 'base_delta_01') if is_first else _event_param('SHAME_04', 'base_delta_02'))
            elif tag == _event_tag('SHAME_19'):
                if current_shame > _event_param('SHAME_19', 'cur_shame_01'):
                    special_delta -= _event_param('SHAME_19', 'base_delta_02')
            elif tag == _event_tag('SHAME_05'): special_delta -= _event_param('SHAME_05', 'base_delta_01')
            elif tag == _event_tag('SHAME_06'): special_delta -= _event_param('SHAME_06', 'base_delta_01')
            elif tag == _event_tag('SHAME_07'): special_delta -= _event_param('SHAME_07', 'base_delta_01')
            elif tag == _event_tag('SHAME_08'): special_delta -= _event_param('SHAME_08', 'base_delta_01')
            elif tag == _event_tag('SHAME_09'): special_delta -= _event_param('SHAME_09', 'base_delta_01')
            elif tag == _event_tag('SHAME_10'): special_delta -= _event_param('SHAME_10', 'base_delta_01')
            elif tag == _event_tag('SHAME_20'): special_delta -= _event_param('SHAME_20', 'base_delta_01')
            
        if c_delta == 0 and special_delta == 0 and _event_tag('SHAME_10') not in tags:
            continue

        # 2.5 被动 Lv.3 疲倦破防、Lv.4 防线支配、高魅力破防、招牌敏感带命中与空间隐私潜行压迫
        if cur_passive >= 3 and current_sta < 60 and c_delta < 0:
            c_delta -= 1
            print(f" [羞耻引擎] 😮‍💨 {char_name} 触发【被动 Lv.3 疲劳诱导·体倦动摇】(体力{current_sta}<60)，羞耻额外 -1。")
        if cur_passive >= 4 and c_delta < 0:
            c_delta -= 2
            print(f" [羞耻引擎] 👑 {char_name} 触发【被动 Lv.4 防线支配】：精准命中防线弱点，羞耻额外 -2。")
        if charm_info['shame_extra_drop'] > 0 and c_delta < 0:
            c_delta -= charm_info['shame_extra_drop']
            print(f" [羞耻引擎] ✨ 宿主魅力({charm_info['charm']}·{charm_info['name']})压场：羞耻防线额外 -{charm_info['shame_extra_drop']}。")
        sig_zone = save_store.HEROINE_SIGNATURE_ZONES.get(char_name)
        char_acts = acts_map.get(char_name) or ()
        if sig_zone and sig_zone in char_acts and c_delta < 0:
            c_delta -= 1
            print(f" [羞耻引擎] 🔥 命中 {char_name} 招牌敏感带【{save_store.BODY_ZONE_LABELS.get(sig_zone, sig_zone)}】，防线额外穿透 -1。")
        if is_stealth_taboo and c_delta < 0:
            c_delta = -max(abs(c_delta) + 1, int(round(abs(c_delta) * 1.25)))
            print(f" [羞耻引擎] 🤫 {char_name} 处于【{privacy} 禁忌潜行压迫】，羞耻降幅 ×1.25 -> {c_delta}。")
            
        # 3. 堕落乘数 (堕落>60时，降幅 × 1.5) 与常规 C 烈度单轮软顶 (-10 防后期雪崩归零)
        if current_depravity > 60:
            if c_delta < 0:
                c_delta = int(round(c_delta * 1.5))
            if special_delta < 0:
                special_delta = int(round(special_delta * 1.5))
        if c_delta < -10:
            print(f" [羞耻引擎] 🛡️ {char_name} 常规 C 烈度破防触发单轮软顶：{c_delta} -> -10。")
            c_delta = -10
            
        # 4. 同质化免疫折扣（仅作用于重复 C 烈度；Lv.4 二轮保留 75% 穿透率）
        if _event_tag('SHAME_15') in tags:
            imm2_mult = 0.75 if cur_passive >= 4 else _event_param('SHAME_15', 'base_delta_01')
            c_delta = int(round(c_delta * imm2_mult))
        elif _event_tag('SHAME_16') in tags:
            c_delta = _event_param('SHAME_16', 'base_delta_01')
            
        base_delta = c_delta + special_delta
        # 5. 计算最终羞耻并安全夹紧 (Clamping 0-shame_cap)
        new_shame = current_shame + base_delta
        new_shame = min(shame_cap, max(0, new_shame))
        computed_shame_changes[char_name] = new_shame
        print(f" [羞耻引擎] {char_name} 语义标签 {tags} 自动演算：羞耻 {current_shame} -> {new_shame} (净变动: {base_delta}, 上限: {shame_cap})")
        
    return computed_shame_changes


def process_depravity_system(depravity_events, memory_file, *, unlocked_caps=None, caps_out=None):
    """
    语义化规则包：堕落系统后台自动化物理计算引擎
    处理堕落值的常规增加，并严格执行 30/60/90 阶梯锁死机制与持久化解锁上限。
    只有接收到特定的主动破锁标签，才能跨越极值屏障。
    """
    if not depravity_events or not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()

    stage_root = os.path.dirname(os.path.dirname(os.path.abspath(memory_file)))
    persisted_caps = {}
    if unlocked_caps is None:
        try:
            st_obj, _, _ = save_store.load_bundle(stage_root)
            raw_caps = (st_obj.get("mechanics") or {}).get("depravity_unlocked_caps")
            if isinstance(raw_caps, dict):
                persisted_caps = {k: int(v) for k, v in raw_caps.items() if isinstance(v, (int, float, str))}
        except Exception:
            persisted_caps = {}
    elif isinstance(unlocked_caps, dict):
        persisted_caps = {k: int(v) for k, v in unlocked_caps.items() if isinstance(v, (int, float, str))}
        
    computed_changes = {}
    
    for char_name, tags in depravity_events.items() if depravity_events else []:
        if not tags or not isinstance(tags, list) or char_name == "徐承邺":
            continue
            
        match = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(\d+)", content)
        if not match:
            continue
            
        current_dep = int(match.group(1))
        base_delta = 0
        unlocked_thresholds = []
        
        for tag in tags:
            if tag == _event_tag('DEPRAVITY_01'): base_delta += _event_param('DEPRAVITY_01', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_02'): base_delta += _event_param('DEPRAVITY_02', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_03'): base_delta += _event_param('DEPRAVITY_03', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_07'): base_delta += _event_param('DEPRAVITY_07', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_08'): base_delta += _event_param('DEPRAVITY_08', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_09'): base_delta += _event_param('DEPRAVITY_09', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_10'): base_delta += _event_param('DEPRAVITY_10', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_04'):
                base_delta += _event_param('DEPRAVITY_04', 'base_delta_01')
                unlocked_thresholds.append(_event_param('DEPRAVITY_04', 'unlocked_threshold_02'))
            elif tag == _event_tag('DEPRAVITY_05'):
                base_delta += _event_param('DEPRAVITY_05', 'base_delta_01')
                unlocked_thresholds.append(_event_param('DEPRAVITY_05', 'unlocked_threshold_02'))
            elif tag == _event_tag('DEPRAVITY_06'):
                base_delta += _event_param('DEPRAVITY_06', 'base_delta_01')
                unlocked_thresholds.append(_event_param('DEPRAVITY_06', 'unlocked_threshold_02'))
                
        if base_delta == 0 and not unlocked_thresholds:
            continue
            
        new_dep = current_dep + base_delta
        
        # 阶梯死锁核心逻辑：结合持久化解锁档位与当前值，当 current_dep >= 目标档位 或 new_dep >= 目标档位 时允许破锁升档并持久化
        saved_cap = int(persisted_caps.get(char_name, 30) or 30)
        if current_dep > 90: base_cap = 100
        elif current_dep > 60: base_cap = max(saved_cap, 90)
        elif current_dep > 30: base_cap = max(saved_cap, 60)
        else: base_cap = max(saved_cap, 30)

        cap = base_cap
        for th in unlocked_thresholds:
            if th == 30 and (current_dep >= 30 or new_dep >= 30): cap = max(cap, 60)
            elif th == 60 and (current_dep >= 60 or new_dep >= 60): cap = max(cap, 90)
            elif th == 90 and (current_dep >= 90 or new_dep >= 90): cap = 100

        if cap > saved_cap:
            persisted_caps[char_name] = cap
            if isinstance(caps_out, dict):
                caps_out[char_name] = cap
            try:
                st_obj, ly_obj, _ = save_store.load_bundle(stage_root)
                st_obj['mechanics'].setdefault('depravity_unlocked_caps', {})[char_name] = cap
                save_store.save_bundle(stage_root, st_obj, ly_obj)
            except Exception:
                pass
            print(f" [堕落引擎] 🔓 {char_name} 触发阶梯破锁，堕落上限永久解锁至 {cap}！")
            
        if new_dep > cap:
            new_dep = cap
            print(f" [堕落引擎] {char_name} 触及 {cap} 阶梯死锁阈值（未满足破锁条件），数值已被强制拦截。")
            
        new_dep = min(100, max(0, new_dep))
        computed_changes[char_name] = new_dep
        print(f" [堕落引擎] {char_name} 语义标签 {tags} 自动演算：堕落 {current_dep} -> {new_dep}")
        
    return computed_changes


CYCLE_OFFSETS = {"沈知韫": 0, "苏婉青": 3, "徐念薇": 6}


def determine_cycle_phase(char_name, current_day=None):
    """基于游戏相对天数(10日浓缩周期+角色错位偏移)确定性推导生理周期阶段。"""
    if current_day is None or int(current_day or 0) <= 0:
        return "常规期"
    offset = CYCLE_OFFSETS.get(char_name, 0)
    pos = (int(current_day) + offset) % 10
    if pos in (0, 1):
        return "安全期"
    if pos in (6, 7):
        return "危险期"
    return "常规期"


def fluid_lock_floor_for_turns(turns, creampie_count=0):
    """三阶体液锁定欲望底线：17~24回合锁>=85，9~16回合锁>=72，1~8回合锁>=58（累计内射>=3次末段升至62）。"""
    t = int(turns or 0)
    if t >= 17:
        return 85
    if t >= 9:
        return 72
    if t >= 1:
        return 62 if int(creampie_count or 0) >= 3 else 58
    return 0


def _compute_orgasm_mult(
    eff_des,
    cur_dep,
    *,
    host_charm=70,
    body_dev=None,
    char_name='',
    body_acts=None,
    host_desire=0,
    edging_streak=0,
    host_vigor=100,
    creampie_count=0,
    raw_org_add=0,
):
    """Single-source orgasm accumulation multiplier shared by DS engine and pregnancy RNG."""
    des_clamped = min(100, max(0, int(eff_des or 0)))
    dep_clamped = min(100, max(0, int(cur_dep or 0)))
    charm_info = charm_tier_info(host_charm)
    bd_map = body_dev if isinstance(body_dev, dict) else {}
    char_bd = bd_map.get(char_name) if isinstance(bd_map.get(char_name), dict) else {}
    char_acts = list(body_acts or ())
    zone_candidates = char_acts if char_acts else (['core'] if int(raw_org_add or 0) >= 30 else [])
    max_z_lv = max((body_dev_level(char_bd.get(z, 0)) for z in zone_candidates), default=0)
    dev_bonus = {0: 0.0, 1: 0.05, 2: 0.12, 3: 0.22}.get(max_z_lv, 0.0)
    h_des = int(host_desire or 0)
    h_edge = int(edging_streak or 0)
    edge_bonus = 0.15 if (h_des >= 85 and h_edge >= 3) else (0.10 if h_des >= 85 else 0.0)
    h_vig = 100 if host_vigor is None else int(host_vigor)
    vigor_penalty = -0.15 if h_vig < 15 else 0.0
    creampie_bonus = 0.05 if int(creampie_count or 0) >= 3 else 0.0
    raw_mult = (
        0.6 + 0.4 * (des_clamped / 100.0) + 0.3 * (dep_clamped / 100.0)
        + charm_info['orgasm_mult_bonus'] + dev_bonus + edge_bonus + vigor_penalty + creampie_bonus
    )
    clamped = max(0.45, min(1.50, raw_mult))
    return clamped, {
        'charm_bonus': charm_info['orgasm_mult_bonus'],
        'dev_bonus': dev_bonus,
        'edge_bonus': edge_bonus,
        'vigor_penalty': vigor_penalty,
        'creampie_bonus': creampie_bonus,
        'raw_mult': raw_mult,
    }


def process_desire_stamina_system(
    ds_events,
    memory_file,
    *,
    creampie_chars=None,
    active_cast=None,
    host_charm=70,
    privacy='open_public',
    climax_out=None,
    body_dev=None,
    body_acts=None,
    host_desire=0,
    host_vigor=100,
    edging_streak=0,
    coy_chars=None,
):
    """
    语义化规则包：生理体力与欲望高潮后台计算引擎
    接管欲望自然渗漏、复合感官刺激、招牌敏感带协同、欲拒还迎禁忌拉扯悸动、刺激上限(80)、临界突破(100，含体液锁定期与魅力协同)、
    隐私潜行肾上腺素、同源高潮增速调制(含1.50x软顶/耐力见底阻尼/极限控场/内射惯性)、场景切换回落、被动Lv.3双倍消耗、
    体力消耗、三阶体液锁定、自慰暗中纾解与自动高潮清算。
    """
    if (not ds_events and not creampie_chars and not active_cast and not coy_chars) or not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    computed_changes = {}
    parsed_buffs = parse_persistent_buffs(content)
    is_stealth_taboo = privacy in ('thin_wall', 'under_cover')
    charm_info = charm_tier_info(host_charm)
    bd_map = body_dev if isinstance(body_dev, dict) else {}
    acts_map = body_acts if isinstance(body_acts, dict) else {}
    coy_set = set(coy_chars or ())
    iter_items = list((ds_events or {}).items())
    seen_chars = {c for c, _ in iter_items}
    for c_extra in (creampie_chars or ()):
        if c_extra not in seen_chars:
            iter_items.append((c_extra, []))
            seen_chars.add(c_extra)
    for c_coy in coy_set:
        if c_coy not in seen_chars:
            iter_items.append((c_coy, []))
            seen_chars.add(c_coy)
    passive_only_chars = set()
    for c_cast in (active_cast or ()):
        if c_cast in save_store.HEROINES and c_cast not in seen_chars:
            iter_items.append((c_cast, []))
            seen_chars.add(c_cast)
            passive_only_chars.add(c_cast)
    
    for char_name, tags in iter_items:
        if not isinstance(tags, list):
            continue
            
        match_aff = re.search(rf"\[{re.escape(char_name)}\].*?好感\s*(-?\d+)", content)
        match_shame = re.search(rf"\[{re.escape(char_name)}\].*?羞耻\s*(-?\d+)", content)
        match_dep = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(-?\d+)", content)
        match_des = re.search(rf"\[{re.escape(char_name)}\].*?欲望\s*(-?\d+)", content)
        match_sta = re.search(rf"\[{re.escape(char_name)}\].*?体力\s*(-?\d+)", content)
        match_org = re.search(rf"\[{re.escape(char_name)}\].*?高潮\s*(\d+)", content)
        match_cp = re.search(rf"\[{re.escape(char_name)}\].*?内射\s*(\d+)次", content)
        match_pas = re.search(rf"\[{re.escape(char_name)}\].*?被动\s*Lv\.?(\d+)", content)
        
        if not (match_aff and match_shame and match_des and match_sta):
            continue
            
        cur_aff = int(match_aff.group(1))
        cur_shame = int(match_shame.group(1))
        cur_dep = int(match_dep.group(1)) if match_dep else 0
        cur_des = int(match_des.group(1))
        cur_sta = int(match_sta.group(1))
        cur_org = int(match_org.group(1)) if match_org else 0
        cur_cp = int(match_cp.group(1)) if match_cp else 0
        cur_passive = int(match_pas.group(1)) if match_pas else 0
        drain_mult = 2 if cur_passive >= 3 else 1
        char_acts = list(acts_map.get(char_name) or ())
        sig_zone = save_store.HEROINE_SIGNATURE_ZONES.get(char_name)
        sig_hit = bool(sig_zone and sig_zone in char_acts)
        is_coy = char_name in coy_set
        
        seepage_gain = 3 if (cur_shame < 40 and cur_aff > 75) else (2 if (cur_shame < 55 and cur_aff > 70) else 0)
        seepage_eligible = seepage_gain > 0
        if char_name in passive_only_chars and not seepage_eligible and not sig_hit and not is_coy:
            continue

        new_des = cur_des
        new_sta = cur_sta
        new_org = cur_org
        
        # 1. 引擎底层被动：好感渗漏机制（全回合自动生效；中段<55且好感>70给+2，深段<40且好感>75给+3）
        if seepage_eligible:
            new_des += seepage_gain
            print(f" [欲望引擎] {char_name} 触发【好感渗漏】，欲望底层暗流自动 +{seepage_gain}。")
            
        # 2. 标签解析（被动 Lv.3 疲劳诱导：焦虑/劳作 ×2，剧烈抗拒 ×1.5 防两回合瞬间断电）
        sensory_visual = 0
        sensory_smell = 0
        sensory_audio = 0
        raw_org_add = 0
        has_scene_decay = False
        has_sleep_reset = False
        has_self_relief = False
        has_active_arousal = False
        
        for tag in tags:
            # 欲望
            if tag == _event_tag('DS_01'): sensory_visual = _event_param('DS_01', 'sensory_visual_01'); has_active_arousal = True
            elif tag == _event_tag('DS_02'): sensory_smell = _event_param('DS_02', 'sensory_smell_01'); has_active_arousal = True
            elif tag == _event_tag('DS_03'): sensory_audio = _event_param('DS_03', 'sensory_audio_01'); has_active_arousal = True
            elif tag == _event_tag('DS_04'): new_des += _event_param('DS_04', 'new_des_01'); has_active_arousal = True
            elif tag == _event_tag('DS_05'):
                new_des -= _event_param('DS_05', 'new_des_01')
                has_scene_decay = True
            # 体力
            elif tag == _event_tag('DS_08'): new_sta -= _event_param('DS_08', 'new_sta_01') * drain_mult
            elif tag == _event_tag('DS_09'): new_sta -= _event_param('DS_09', 'new_sta_01') * drain_mult
            elif tag == _event_tag('DS_10'):
                resist_base = _event_param('DS_10', 'new_sta_01')
                new_sta -= int(round(resist_base * 1.5)) if cur_passive >= 3 else resist_base
            elif tag == _event_tag('DS_11'): new_sta -= _event_param('DS_11', 'new_sta_01')
            elif tag == _event_tag('DS_12'): new_sta += _event_param('DS_12', 'new_sta_01')
            elif tag == _event_tag('DS_13'):
                new_sta += _event_param('DS_13', 'new_sta_01')
                has_sleep_reset = True
            # 高潮与自慰暗中纾解
            elif tag == _event_tag('DS_14'): raw_org_add += _event_param('DS_14', 'new_org_01'); has_active_arousal = True
            elif tag == _event_tag('DS_15'): raw_org_add += _event_param('DS_15', 'new_org_01'); has_active_arousal = True
            elif tag == _event_tag('DS_16'): raw_org_add += _event_param('DS_16', 'new_org_01'); has_active_arousal = True
            elif tag == _event_tag('DS_18'): has_self_relief = True
            
        # 3. 多通道复合感官刺激（主通道全额 + 次通道 50% 协同，单回合上限 +5；羞耻 > 80 时视觉保留 +2 底线，欲拒还迎或官能 Buff 全额放行）
        char_buffs = parsed_buffs.get(char_name) or []
        if cur_shame > 80 and sensory_visual > 0:
            if not _has_sensual_buff(char_buffs) and not is_coy:
                sensory_visual = min(sensory_visual, 2)
        s_vals = sorted([sensory_visual, sensory_smell, sensory_audio], reverse=True)
        sensory_add = min(5, int(round(s_vals[0] + 0.5 * (s_vals[1] + s_vals[2]))))
        new_des += sensory_add

        # 3.5 欲拒还迎禁忌拉扯悸动 (+3)、空间隐私潜行肾上腺素 (+2)、招牌敏感带命中 (+3) 与高魅力压迫协同 (+2)
        if is_coy:
            coy_des_add = _event_param('AFFECTION_12', 'desire_bonus_02')
            new_des += coy_des_add
            has_active_arousal = True
            print(f" [欲望引擎] 💓 {char_name} 触发【欲拒还迎·禁忌拉扯悸动】，欲望额外 +{coy_des_add}。")
        if sig_hit:
            new_des += 3
            has_active_arousal = True
            print(f" [欲望引擎] 🔥 命中 {char_name} 招牌敏感带【{save_store.BODY_ZONE_LABELS.get(sig_zone, sig_zone)}】，欲望额外 +3。")
        if is_stealth_taboo and has_active_arousal:
            new_des += 2
            print(f" [欲望引擎] 🤫 {char_name} 处于【{privacy} 偷欢潜行态】，禁忌肾上腺素驱动欲望额外 +2。")
        has_charm_bt = _event_tag('DS_06') in tags
        has_breakthrough = (has_charm_bt or _event_tag('DS_07') in tags)
        if has_charm_bt and int(host_charm or 70) >= 75:
            new_des += 2
            print(f" [欲望引擎] ✨ 宿主魅力({host_charm})≥75，【临界突破_魅力压迫】额外附带 +2 压迫增幅。")
        
        # 4. 物理刺激上限拦截 (80) 与 临界突破 (100；魅力<68门限75、常规70、魅力>=75门限60)
        bt_floor = int(charm_info.get('bt_floor', 70)) if has_charm_bt else 70
        if has_breakthrough and (cur_des >= bt_floor or new_des >= bt_floor):
            new_des = _event_param('DS_06', 'new_des_01')
            print(f" [欲望引擎] {char_name} 触发【临界突破】，欲望强行贯穿阈值直达 100！")
        elif new_des > 80 and cur_des <= 80:
            new_des = 80
            print(f" [欲望引擎] {char_name} 欲望被拦截在 80（物理刺激上限，需特定临界突破）。")
                
        # 5. 特殊状态锁判定 (结合当回合内射与记忆库持久化BUFF三阶底线：17~24轮>=85，9~16轮>=72，1~8轮>=58/内射>=3次>=62)
        lock_m = re.search(rf"▶\s*{re.escape(char_name)}\s*\n(?:(?!▶).)*?\[持续_体液锁定\]\s*剩余时效:\s*(\d+)回合", content, re.DOTALL)
        lock_turns = int(lock_m.group(1)) if lock_m else 0
        if bool(creampie_chars and char_name in creampie_chars):
            lock_turns = max(lock_turns, 24)
        elif lock_turns == 0 and bool(re.search(rf"▶\s*{re.escape(char_name)}\s*\n(?:(?!▶).)*?\[持续_体液锁定\]", content, re.DOTALL)):
            lock_turns = 24
        semen_floor = fluid_lock_floor_for_turns(lock_turns, creampie_count=cur_cp)
        semen_locked = semen_floor > 0
        if semen_locked:
            new_des = max(semen_floor, new_des)
            print(f" [欲望引擎] 🔒 {char_name} 处于/触发【体液锁定({lock_turns}回合)】，欲望被强制钳制在不低于 {semen_floor}。")

        # 5.5 共享同源高潮增速调制（含 1.50x 软顶、耐力<15 阻尼、连控>=3 加成与累计内射惯性）
        if raw_org_add > 0:
            eff_des = min(100, max(0, new_des))
            org_mult, org_det = _compute_orgasm_mult(
                eff_des,
                cur_dep,
                host_charm=host_charm,
                body_dev=bd_map,
                char_name=char_name,
                body_acts=char_acts,
                host_desire=host_desire,
                edging_streak=edging_streak,
                host_vigor=host_vigor,
                creampie_count=cur_cp,
                raw_org_add=raw_org_add,
            )
            mod_org_add = int(round(raw_org_add * org_mult))
            new_org += mod_org_add
            print(
                f" [生理引擎] {char_name} 高潮累积耦合调制：原始+{raw_org_add} × {org_mult:.2f} "
                f"(欲望{eff_des}/堕落{cur_dep}/魅力+{org_det['charm_bonus']:.2f}/开发+{org_det['dev_bonus']:.2f}"
                f"/控场+{org_det['edge_bonus']:.2f}/耐力{org_det['vigor_penalty']:+.2f}/内射+{org_det['creampie_bonus']:.2f}) -> +{mod_org_add}"
            )
        elif has_scene_decay and new_org > 0:
            new_org = max(0, new_org - _event_param('DS_05', 'new_org_02'))
            print(f" [生理引擎] {char_name} 场景切换未继续刺激，高潮余波回落至 {new_org}。")
        if has_sleep_reset and new_org > 0 and raw_org_add == 0:
            new_org = 0
            print(f" [生理引擎] {char_name} 安稳睡眠恢复，残余高潮值清零。")
            
        # 6. 高潮核爆清算 或 自慰暗中纾解（体液锁定生效期间欲望受当前分阶底线钳制）
        if _event_tag('DS_17') in tags or new_org >= _event_param('DS_17', 'new_org_01'):
            if isinstance(climax_out, set):
                climax_out.add(char_name)
            new_org = _event_param('DS_17', 'new_org_02')
            new_des = _event_param('DS_17', 'new_des_03')
            new_sta -= _event_param('DS_17', 'new_sta_04')  # 扣除NPC绝顶痉挛体力消耗 15
            if semen_locked:
                new_des = max(semen_floor, new_des)
            print(f" [生理引擎] 💥 {char_name} 触发【高潮清算】，高潮归零，欲望回落 {new_des}，体力扣除 15 -> {new_sta}。")
        elif has_self_relief:
            new_org = _event_param('DS_18', 'new_org_01')
            new_des = _event_param('DS_18', 'new_des_02')
            new_sta -= _event_param('DS_18', 'new_sta_03')
            if semen_locked:
                new_des = max(semen_floor, new_des)
            print(f" [生理引擎] 🌙 {char_name} 触发【自慰_暗中纾解】，高潮释放归零，欲望回落 {new_des}，体力扣除 8 -> {new_sta}。")
            
        # 7. 极限夹紧
        new_des = min(100, max(0, new_des))
        new_sta = min(100, max(0, new_sta))
        new_org = min(100, max(0, new_org))
        
        # 8. 生理性断电监控
        if new_sta <= 15 and cur_sta > 15:
            print(f" ⚠️ [生理警告] {char_name} 体力跌破 15！触发【生理性断电】，神经传导已失效！")
            
        computed_changes[char_name] = {
            "欲望": new_des,
            "体力": new_sta,
            "高潮": new_org
        }
        
    return computed_changes


COY_AFF_FLOORS = {
    "沈知韫": 65,
    "苏婉青": 45,
    "徐念薇": 42,
}


def compute_tension_profile(
    char_name,
    *,
    cur_aff=50,
    cur_shame=100,
    cur_des=0,
    cur_dep=0,
    cur_passive=0,
    privacy='open_public',
    has_buff=False,
    resentment=0,
):
    """Dual-Control (SES Approach vs SIS Inhibition) tension synthesis shared by backend settlement and foreground brief."""
    aff = max(0, min(100, int(cur_aff or 0)))
    shame = max(0, min(100, int(cur_shame if cur_shame is not None else 100)))
    des = max(0, min(100, int(cur_des or 0)))
    dep = max(0, min(100, int(cur_dep or 0)))
    pas = max(0, int(cur_passive or 0))
    res = max(0, min(100, int(resentment or 0)))
    aff_floor = COY_AFF_FLOORS.get(char_name, 60)

    approach = min(
        100,
        max(0, int(round(0.45 * aff + 0.35 * des + 0.20 * dep + (10 if has_buff else 0) + (5 if pas >= 2 else 0)))),
    )
    priv_mod = 12 if privacy == 'open_public' else (-8 if privacy == 'locked_private' else 0)
    inhibition = min(100, max(0, int(round(shame + priv_mod))))
    tension = min(approach, inhibition)
    res_block = int(_event_param('AFFECTION_12', 'resentment_block_03'))

    if res >= res_block:
        quadrant = 'resentful'
    elif aff < aff_floor and des < 30 and dep < 10 and not has_buff:
        quadrant = 'true_reject'
    elif (approach >= 45 or (aff >= aff_floor and des >= 30)) and inhibition >= 60 and tension >= 38:
        quadrant = 'coy_tension'
    elif approach >= 55 and inhibition < 60:
        quadrant = 'yielding'
    else:
        quadrant = 'neutral'

    return {
        'approach': approach,
        'inhibition': inhibition,
        'tension': tension,
        'quadrant': quadrant,
        'resentment': res,
        'aff_floor': aff_floor,
    }


def process_affection_system(
    affection_events,
    shame_events,
    memory_file,
    *,
    business_leverage=False,
    leverage_meta=None,
    su_85_unlocked=None,
    unlock_out=None,
    host_charm=None,
    resentment_map=None,
    privacy='open_public',
    active_cast=None,
    ds_events=None,
    coy_out=None,
):
    """
    语义化规则包：好感度畸变与阻滞计算引擎
    监听 SHAME_EVENTS 中的越界行为，结合当前面板实现自动掉分、高羞耻完好防线修正、合理化闭环、
    五重安全闸欲拒还迎表里翻正、意外撞破自渎把柄折半、高魅力破冰加成与越界缓和及被动 Lv.2 减半。
    处理苏婉青的 85 分背德天花板持久化锁死，以及商业杠杆（C烈度越界好感惩罚减半，可与被动 Lv.2 叠加）。
    """
    if not affection_events and not shame_events:
        return {}
    if not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()

    if host_charm is None:
        m_hc = re.search(r"\[系统宿主\].*?魅力\s*(-?\d+)", content)
        eff_host_charm = int(m_hc.group(1)) if m_hc else 70
    else:
        eff_host_charm = int(host_charm)
    charm_info = charm_tier_info(eff_host_charm)

    stage_root = os.path.dirname(os.path.dirname(os.path.abspath(memory_file)))
    persisted_su_unlocked = False
    if su_85_unlocked is None:
        try:
            st_obj, _, _ = save_store.load_bundle(stage_root)
            persisted_su_unlocked = bool((st_obj.get("mechanics") or {}).get("su_affection_85_unlocked", False))
        except Exception:
            persisted_su_unlocked = False
    else:
        persisted_su_unlocked = bool(su_85_unlocked)
        
    computed_changes = {}
    parsed_buffs_all = parse_persistent_buffs(content)
    res_map = resentment_map if isinstance(resentment_map, dict) else {}
    cast_list = list(active_cast or ())
    ds_map = ds_events if isinstance(ds_events, dict) else {}
    coy_tag = _event_tag('AFFECTION_12')
    coy_res_block = int(_event_param('AFFECTION_12', 'resentment_block_03'))
    
    # 只要在好感字典或羞耻字典里出现的角色，统统拉出来接受结算
    all_chars = set(affection_events.keys() if affection_events else []).union(
                set(shame_events.keys() if shame_events else []))
                
    for char_name in all_chars:
        match_aff = re.search(rf"\[{re.escape(char_name)}\].*?好感\s*(-?\d+)", content)
        match_shame = re.search(rf"\[{re.escape(char_name)}\].*?羞耻\s*(-?\d+)", content)
        match_dep = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(-?\d+)", content)
        match_des = re.search(rf"\[{re.escape(char_name)}\].*?欲望\s*(-?\d+)", content)
        match_sta = re.search(rf"\[{re.escape(char_name)}\].*?体力\s*(-?\d+)", content)
        match_pas = re.search(rf"\[{re.escape(char_name)}\].*?被动\s*Lv\.?(\d+)", content)
        
        if not (match_aff and match_shame):
            continue
            
        cur_aff = int(match_aff.group(1))
        cur_shame = int(match_shame.group(1))
        cur_dep = int(match_dep.group(1)) if match_dep else 0
        cur_des = int(match_des.group(1)) if match_des else 0
        cur_sta = int(match_sta.group(1)) if match_sta else 100
        cur_passive = int(match_pas.group(1)) if match_pas else 0
        cur_res = max(0, min(100, int(res_map.get(char_name, 0) or 0)))
        new_aff = cur_aff
        
        a_tags = affection_events.get(char_name, []) if affection_events else []
        s_tags = shame_events.get(char_name, []) if shame_events else []
        d_tags = ds_map.get(char_name, []) if ds_map else []
        if not isinstance(a_tags, list): a_tags = []
        if not isinstance(s_tags, list): s_tags = []
        if not isinstance(d_tags, list): d_tags = []
        char_buffs = parsed_buffs_all.get(char_name) or []
        has_sensual = _has_sensual_buff(char_buffs)

        # 0. 五重确定性安全硬闸：评估「欲拒还迎_嘴硬心软」是否真正满足表里翻正资格
        coy_qualified = False
        if coy_tag in a_tags:
            has_deep_heavy = (_event_tag('SHAME_03') in s_tags or _event_tag('SHAME_04') in s_tags)
            has_mid_c = (_event_tag('SHAME_02') in s_tags)
            coercive_aff = {_event_tag('AFFECTION_01'), _event_tag('AFFECTION_02')}
            coercive_shame = {_event_tag('SHAME_11'), _event_tag('SHAME_12'), _event_tag('SHAME_13')}
            aff_floor = COY_AFF_FLOORS.get(char_name, 60)
            is_crowded_public = (privacy == 'open_public') and (len(cast_list) >= 2 or '徐承邺' in cast_list)

            block_reason = ''
            if cur_res >= coy_res_block:
                block_reason = f'真实反感裂痕({cur_res}≥{coy_res_block})锁死'
            elif not (cur_aff >= aff_floor or cur_des >= 30 or cur_dep >= 10 or has_sensual):
                block_reason = f'感情与生理未达准入(好感{cur_aff}<{aff_floor}且欲望{cur_des}<30)'
            elif (has_deep_heavy and cur_shame >= 55) or (has_mid_c and cur_shame >= 88 and cur_des < 30 and not has_sensual):
                block_reason = f'高羞耻({cur_shame})越界烈度超窗'
            elif (set(a_tags) & coercive_aff) or (set(s_tags) & coercive_shame) or (_event_tag('DS_10') in d_tags) or cur_sta <= 15:
                block_reason = '存在强迫/剧烈抗拒/解离或生理断电'
            elif is_crowded_public and (has_mid_c or has_deep_heavy):
                block_reason = '公开多人场禁中深度欲拒还迎翻正'

            if not block_reason:
                coy_qualified = True
                if isinstance(coy_out, set):
                    coy_out.add(char_name)
                print(f" [好感引擎] 💞 {char_name} 通过五重安全闸，触发【欲拒还迎·表里翻正】：免除本轮轻中越界扣分并转为正向心动。")
            else:
                print(f" [好感引擎] 🚫 {char_name} 未通过【欲拒还迎】安全闸（{block_reason}），驳回翻正并按真实防线结算。")
        
        # 1. 越界联动下降机制 (跨模块监听 SHAME_EVENTS；当羞耻>=90且堕落<10且未达被动Lv.4时防线完好，高好感仍享>60档轻判但不触发0掉分闭环)
        intact_defense = (cur_shame >= 90 and cur_dep < 10 and cur_passive < 4)
        violation_drop = 0
        hit_c_tier = ''
        if not coy_qualified:
            if _event_tag('SHAME_04') in s_tags:
                hit_c_tier = 'SHAME_04'
                if cur_aff > _event_param('SHAME_04', 'cur_aff_03'):
                    violation_drop -= (_event_param('SHAME_04', 'violation_drop_05') if (cur_shame < _event_param('SHAME_04', 'cur_shame_04') and not intact_defense) else _event_param('SHAME_04', 'violation_drop_06'))
                elif cur_aff >= _event_param('SHAME_04', 'cur_aff_07'): violation_drop -= _event_param('SHAME_04', 'violation_drop_08')
                else: violation_drop -= _event_param('SHAME_04', 'violation_drop_09')
            elif _event_tag('SHAME_03') in s_tags:
                hit_c_tier = 'SHAME_03'
                if cur_aff > _event_param('SHAME_03', 'cur_aff_03'):
                    violation_drop -= (_event_param('SHAME_03', 'violation_drop_05') if (cur_shame < _event_param('SHAME_03', 'cur_shame_04') and not intact_defense) else _event_param('SHAME_03', 'violation_drop_06'))
                elif cur_aff >= _event_param('SHAME_03', 'cur_aff_07'): violation_drop -= _event_param('SHAME_03', 'violation_drop_08')
                else: violation_drop -= _event_param('SHAME_03', 'violation_drop_09')
            elif _event_tag('SHAME_02') in s_tags:
                hit_c_tier = 'SHAME_02'
                if cur_aff > _event_param('SHAME_02', 'cur_aff_03'):
                    violation_drop -= (_event_param('SHAME_02', 'violation_drop_05') if (cur_shame < _event_param('SHAME_02', 'cur_shame_04') and not intact_defense) else _event_param('SHAME_02', 'violation_drop_06'))
                elif cur_aff >= _event_param('SHAME_02', 'cur_aff_07'): violation_drop -= _event_param('SHAME_02', 'violation_drop_08')
                else: violation_drop -= _event_param('SHAME_02', 'violation_drop_09')
            elif _event_tag('SHAME_01') in s_tags:
                hit_c_tier = 'SHAME_01'
                if cur_aff > _event_param('SHAME_01', 'cur_aff_02'):
                    violation_drop -= (_event_param('SHAME_01', 'violation_drop_04') if (cur_shame < _event_param('SHAME_01', 'cur_shame_03') and not intact_defense) else _event_param('SHAME_01', 'violation_drop_05'))
                elif cur_aff >= _event_param('SHAME_01', 'cur_aff_06'): violation_drop -= _event_param('SHAME_01', 'violation_drop_07')
                else: violation_drop -= _event_param('SHAME_01', 'violation_drop_08')

        raw_violation_drop = violation_drop
        if (not coy_qualified) and violation_drop == _event_param('SHAME_04', 'violation_drop_10') and bool(hit_c_tier):
            print(f" [好感引擎] 💖 {char_name} 触发【合理化闭环】！好感与羞耻达标，潜意识自我保护启动，未造成好感下降。")

        # 意外撞破_私密自渎（把柄在握+身体诚实情动）：当轮C烈度越界好感惩罚自动减半
        if _event_tag('SHAME_20') in s_tags and violation_drop < 0:
            halved_caught = int(violation_drop / 2)
            print(f" [好感引擎] 🔥 {char_name} 触发【意外撞破_私密自渎·身体诚实闭环】：越界好感惩罚减半 {violation_drop} -> {halved_caught}")
            violation_drop = halved_caught

        # 官能辅助道具 BUFF（含静态 SHOP、AI 动态进货 DYN-* 与眼罩滚轮）：轻/中度越界（SHAME_01/02）好感惩罚减半
        if violation_drop < 0 and (_event_tag('SHAME_01') in s_tags or _event_tag('SHAME_02') in s_tags):
            if has_sensual:
                halved_buff = int(violation_drop / 2)
                print(f" [好感引擎] 🕯️ {char_name} 触发【官能辅助 BUFF 缓和】：轻中度越界好感惩罚减半 {violation_drop} -> {halved_buff}")
                violation_drop = halved_buff

        # 高魅力越界缓和（75+轻中度减罚 25%/40%/50%；95+深重度减罚 20%）
        if violation_drop < 0:
            is_deep_heavy = (_event_tag('SHAME_03') in s_tags or _event_tag('SHAME_04') in s_tags)
            mit_ratio = charm_info['deep_mitigation'] if is_deep_heavy else charm_info['violation_mitigation']
            if mit_ratio > 0:
                mitigated = int(round(violation_drop * (1.0 - mit_ratio)))
                print(f" [好感引擎] ✨ 宿主魅力({charm_info['charm']}·{charm_info['name']})缓和：越界好感惩罚减免 {int(mit_ratio * 100)}% ({violation_drop} -> {mitigated})")
                violation_drop = mitigated

        # 被动 Lv.2（认知欺诈滤镜）：C烈度越界好感惩罚减半，与商业杠杆独立叠加
        if cur_passive >= 2 and violation_drop < 0:
            halved_passive = int(violation_drop / 2)
            print(f" [好感引擎] 👁️ {char_name} 触发【被动 Lv.2 认知欺诈滤镜】：越界好感惩罚减半 {violation_drop} -> {halved_passive}")
            violation_drop = halved_passive

        if business_leverage and violation_drop < 0:
            halved = int(violation_drop / 2)
            if leverage_meta is not None:
                leverage_meta['applied'] = True
                leverage_meta.setdefault('targets', []).append({
                    'target': char_name,
                    'before_drop': violation_drop,
                    'after_drop': halved,
                })
            print(f" [好感引擎] ⚖️ {char_name} 触发【商业杠杆】：越界好感惩罚减半 {violation_drop} -> {halved}")
            violation_drop = halved

        # 多重减免硬护栏：轻度越界(SHAME_01)经道具/被动/魅力/杠杆准备后允许真正免罚归 0；中/深/重度保留 75% 减免上限且保底至少 -1
        if raw_violation_drop < 0 and hit_c_tier != 'SHAME_01':
            min_penalty = -max(1, int(round(abs(raw_violation_drop) * 0.25)))
            if violation_drop > min_penalty:
                print(f" [好感引擎] 🛡️ {char_name} 触发【减免上限护栏(75%/保底-1)】：{violation_drop} -> {min_penalty}（原始 {raw_violation_drop}）")
                violation_drop = min_penalty

        # 合并「越界自动扣分 + 阻止侵犯_成功/暴力下流_雪崩」防同回合双重叠扣
        aff01_tag = _event_tag('AFFECTION_01')
        aff02_tag = _event_tag('AFFECTION_02')
        explicit_neg_merged = False
        if aff02_tag in a_tags:
            aff02_drop = -_event_param('AFFECTION_02', 'new_aff_01')
            violation_drop = min(violation_drop, aff02_drop)
            explicit_neg_merged = True
        elif aff01_tag in a_tags:
            aff01_drop = -_event_param('AFFECTION_01', 'new_aff_01')
            if violation_drop < 0:
                merged_drop = min(violation_drop, aff01_drop) - 1
                print(f" [好感引擎] ⚖️ {char_name} 越界({violation_drop})与阻止侵犯({aff01_drop})合并防重扣 -> {merged_drop}")
                violation_drop = merged_drop
            else:
                violation_drop = aff01_drop
            explicit_neg_merged = True

        new_aff += violation_drop
        
        # 2. 手动标签结算（高魅力 75+ 正面互动额外破冰加成）
        positive_gain = 0
        for tag in a_tags:
            if tag == aff01_tag:
                if not explicit_neg_merged:
                    new_aff -= _event_param('AFFECTION_01', 'new_aff_01')
            elif tag == aff02_tag:
                if not explicit_neg_merged:
                    new_aff -= _event_param('AFFECTION_02', 'new_aff_01')
            elif tag == _event_tag('AFFECTION_03'):
                g = (_event_param('AFFECTION_03', 'new_aff_02') if cur_aff < _event_param('AFFECTION_03', 'cur_aff_01') else _event_param('AFFECTION_03', 'new_aff_03'))
                new_aff += g; positive_gain += g
            elif tag == _event_tag('AFFECTION_04'):
                g = (_event_param('AFFECTION_04', 'new_aff_02') if cur_shame <= _event_param('AFFECTION_04', 'cur_shame_01') else _event_param('AFFECTION_04', 'new_aff_03'))
                new_aff += g; positive_gain += g
            elif tag == _event_tag('AFFECTION_05'):
                g = _event_param('AFFECTION_05', 'new_aff_01')
                new_aff += g; positive_gain += g
            elif tag == _event_tag('AFFECTION_06'):
                g = (_event_param('AFFECTION_06', 'new_aff_02') if cur_aff < _event_param('AFFECTION_06', 'cur_aff_01') else _event_param('AFFECTION_06', 'new_aff_03'))
                new_aff += g; positive_gain += g
            elif tag == _event_tag('AFFECTION_07'):
                g = _event_param('AFFECTION_07', 'new_aff_01')
                new_aff += g; positive_gain += g
            elif tag == _event_tag('AFFECTION_10'):
                g = (_event_param('AFFECTION_10', 'new_aff_02') if cur_aff < _event_param('AFFECTION_10', 'cur_aff_01') else _event_param('AFFECTION_10', 'new_aff_03'))
                new_aff += g; positive_gain += g
            elif tag == _event_tag('AFFECTION_11'):
                g = _event_param('AFFECTION_11', 'new_aff_01')
                new_aff += g; positive_gain += g
            elif tag == coy_tag and coy_qualified:
                g = _event_param('AFFECTION_12', 'new_aff_01')
                new_aff += g; positive_gain += g
        if positive_gain > 0 and charm_info['aff_bonus'] > 0:
            new_aff += charm_info['aff_bonus']
            print(f" [好感引擎] ✨ 宿主魅力({charm_info['charm']}·{charm_info['name']})破冰加成：正面好感额外 +{charm_info['aff_bonus']}。")
            
        # 3. 专属阻力锁：苏婉青的背德天花板（触发 AFFECTION_08/09 即永久持久化解锁至 95）
        cap = 100
        if char_name == "苏婉青":
            cap = 85
            triggered_unlock = (_event_tag('AFFECTION_08') in a_tags or _event_tag('AFFECTION_09') in a_tags)
            if triggered_unlock or persisted_su_unlocked or cur_aff > _event_param('AFFECTION_08', 'cur_aff_01'):
                cap = _event_param('AFFECTION_08', 'cap_02')
                if triggered_unlock:
                    persisted_su_unlocked = True
                    if unlock_out is not None:
                        unlock_out['su_affection_85_unlocked'] = True
                    try:
                        st_obj, ly_obj, _ = save_store.load_bundle(stage_root)
                        if not st_obj['mechanics'].get('su_affection_85_unlocked'):
                            st_obj['mechanics']['su_affection_85_unlocked'] = True
                            save_store.save_bundle(stage_root, st_obj, ly_obj)
                    except Exception:
                        pass
                    print(f" [好感引擎] 🔓 苏婉青触发【背德天花板解锁】，好感上限永久突破至 95！")
                    
        if new_aff > cap:
            new_aff = cap
            print(f" [好感引擎] {char_name} 触及好感天花板 ({cap})，数值已被拦截。")
            
        new_aff = min(100, max(0, new_aff))
        
        if new_aff != cur_aff:
            computed_changes[char_name] = new_aff
            print(f" [好感引擎] {char_name} 自动演算：好感 {cur_aff} -> {new_aff}")
            
    return computed_changes


def _estimate_turn_orgasm(
    char_name,
    cur_org,
    cur_des,
    cur_dep,
    ds_events,
    *,
    host_charm=70,
    body_dev=None,
    body_acts=None,
    host_desire=0,
    edging_streak=0,
    host_vigor=100,
    creampie_count=0,
):
    """估算本轮包含 ds_events 后的真实高潮峰值（与 process_desire_stamina_system 共享 _compute_orgasm_mult）。"""
    ds_tags = (ds_events or {}).get(char_name) if isinstance(ds_events, dict) else None
    if not isinstance(ds_tags, list) or not ds_tags:
        return cur_org
    if _event_tag('DS_17') in ds_tags:
        return 100
    raw_add = 0
    eff_des = cur_des
    for tag in ds_tags:
        if tag == _event_tag('DS_04'):
            eff_des += _event_param('DS_04', 'new_des_01')
        elif tag in (_event_tag('DS_06'), _event_tag('DS_07')):
            eff_des = _event_param('DS_06', 'new_des_01')
        elif tag == _event_tag('DS_14'):
            raw_add += _event_param('DS_14', 'new_org_01')
        elif tag == _event_tag('DS_15'):
            raw_add += _event_param('DS_15', 'new_org_01')
        elif tag == _event_tag('DS_16'):
            raw_add += _event_param('DS_16', 'new_org_01')
    if raw_add <= 0:
        return cur_org
    eff_des = min(100, max(0, eff_des))
    char_acts = list((body_acts or {}).get(char_name) or ()) if isinstance(body_acts, dict) else list(body_acts or ())
    org_mult, _ = _compute_orgasm_mult(
        eff_des,
        cur_dep,
        host_charm=host_charm,
        body_dev=body_dev,
        char_name=char_name,
        body_acts=char_acts,
        host_desire=host_desire,
        edging_streak=edging_streak,
        host_vigor=host_vigor,
        creampie_count=creampie_count,
        raw_org_add=raw_add,
    )
    return min(100, cur_org + int(round(raw_add * org_mult)))


def process_pregnancy_rng(
    shame_events,
    memory_file,
    *,
    ds_events=None,
    current_day=None,
    latent_map=None,
    latent_out=None,
    host_charm=70,
    body_dev=None,
    body_acts=None,
    host_desire=0,
    edging_streak=0,
    host_vigor=100,
):
    """
    命运引擎：真·随机数受孕判定 + 10日生理周期日历 + 受孕潜伏期
    接管内射后的受孕概率结算，同源复用 _compute_orgasm_mult 判定本轮高潮清算40%加成，支持受孕潜伏期与确诊怀孕落地。
    """
    if not shame_events or not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    computed_preg = {}
    
    for char_name, tags in shame_events.items() if shame_events else []:
        if not tags or not isinstance(tags, list): continue
        match_preg = re.search(rf"\[{re.escape(char_name)}\].*?怀孕\s*(True|False)", content)
        if match_preg and match_preg.group(1) == "True":
            continue # 已确诊怀孕，无需再投骰子

        existing_latent = int((latent_map or {}).get(char_name, 0) or 0) if isinstance(latent_map, dict) else 0
        if _event_tag('SHAME_10') in tags:
            if existing_latent > 0 or (match_preg and match_preg.group(1) == "True"):
                computed_preg[char_name] = "True"
                if isinstance(latent_out, dict):
                    latent_out[char_name] = 0
                continue
            if _event_tag('SHAME_06') not in tags and _event_tag('SHAME_07') not in tags:
                continue

        if _event_tag('SHAME_06') not in tags and _event_tag('SHAME_07') not in tags:
            continue
            
        match_dep = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(\d+)", content)
        match_org = re.search(rf"\[{re.escape(char_name)}\].*?高潮\s*(\d+)", content)
        match_des = re.search(rf"\[{re.escape(char_name)}\].*?欲望\s*(-?\d+)", content)
        match_cp = re.search(rf"\[{re.escape(char_name)}\].*?内射\s*(\d+)次", content)
        
        cur_dep = int(match_dep.group(1)) if match_dep else 0
        cur_org = int(match_org.group(1)) if match_org else 0
        cur_des = int(match_des.group(1)) if match_des else 0
        cur_cp = int(match_cp.group(1)) if match_cp else 0
        effective_org = _estimate_turn_orgasm(
            char_name,
            cur_org,
            cur_des,
            cur_dep,
            ds_events,
            host_charm=host_charm,
            body_dev=body_dev,
            body_acts=body_acts,
            host_desire=host_desire,
            edging_streak=edging_streak,
            host_vigor=host_vigor,
            creampie_count=cur_cp,
        )
        
        # 计算动态概率（含当轮高潮清算/峰值>=100加成）
        prob = 10
        if cur_dep > 80 or effective_org >= 100:
            prob = 40
            
        cycle_phase = determine_cycle_phase(char_name, current_day)
        if cycle_phase == "危险期" or (current_day is None and _event_tag('SHAME_18') in tags):
            prob *= _event_param('SHAME_18', 'prob_01')
        elif cycle_phase == "安全期" and current_day is not None:
            prob = max(2, int(round(prob * 0.25)))
            
        prob = min(100, prob)
        roll = random.randint(1, 100)
        
        print(f" 🎲 [命运引擎] {char_name} 触发内射！周期:{cycle_phase} 高潮峰值:{effective_org}% 堕落:{cur_dep} | 受孕概率: {prob}% | 命运暗骰: {roll}")
        
        if roll <= prob:
            if isinstance(latent_out, dict) and current_day is not None and int(current_day) > 0:
                if existing_latent > 0 and int(current_day) >= existing_latent:
                    computed_preg[char_name] = "True"
                    latent_out[char_name] = 0
                    print(f" 🚨🚨 [命运引擎] 潜伏期满并再次命中！{char_name} 正式确诊怀孕！🚨🚨")
                else:
                    target_day = existing_latent if existing_latent > 0 else (int(current_day) + 2)
                    latent_out[char_name] = target_day
                    print(f" 🌱 [命运引擎] 暗骰命中！{char_name} 已成功受孕并进入【受孕潜伏期】（预计第 {target_day} 天显露确诊）！")
            else:
                print(f" 🚨🚨 [命运引擎] 致命命中！{char_name} 确诊受孕！🚨🚨")
                computed_preg[char_name] = "True"
        else:
            print(f" 💨 [命运引擎] 未命中。{char_name} 逃过一劫。")
            
    return computed_preg



def update_persistent_buffs(memory_file, shame_events, new_buffs_dict=None):
    """
    后台持久化状态与BUFF管理器
    处理全局倒计时扣减、内射自动体液锁定（完整24回合）以及前台AI手动挂载新BUFF请求。
    先递减旧有BUFF，再挂载本轮新增BUFF，避免新挂载当轮立少1回合。
    """
    if new_buffs_dict is None: new_buffs_dict = {}
    if not os.path.exists(memory_file):
        return
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()

    if "【当前持久化状态与BUFF】" not in content:
        return

    # 1. 拆分出持久化区块
    parts = re.split(r"(【当前持久化状态与BUFF】[\s\S]*?)(?=\n={10,}|\n▲ 第一层|$)", content, maxsplit=1)
    if len(parts) < 2:
        return
    
    buff_block = parts[1]

    # 2. 先遍历所有既有带“剩余时效: X回合”的BUFF进行倒计时 -1（归零移除）
    def decrement_timer(match):
        buff_name = match.group(1)
        turns = int(match.group(2)) - 1
        effect = match.group(3)
        if turns <= 0:
            print(f" ⌛ [持久化引擎] BUFF [{buff_name}] 时效已尽，后台自动移除！")
            return "" # 归零移除
        if buff_name == "持续_体液锁定":
            fl_floor = fluid_lock_floor_for_turns(turns)
            effect = f"效果: 欲望死锁不低于{fl_floor}"
        return f"- [{buff_name}] 剩余时效: {turns}回合 ({effect})"

    buff_block = re.sub(r"-\s*\[([^\]]+)\]\s*剩余时效:\s*(\d+)回合\s*\((.*)\)(?=[ \t]*$)", decrement_timer, buff_block, flags=re.M)

    # 3. 再挂载本轮前台 AI 手动请求的新 BUFF（道具或特殊剧情触发；同名刷新不重复堆叠）
    if new_buffs_dict:
        for char, buff_str in new_buffs_dict.items():
            if buff_str:
                char_pattern = rf"(▶\s*{re.escape(char)}\s*\n)(.*?)(?=\n▶|\n$|\Z)"
                match_char = re.search(char_pattern, buff_block, re.DOTALL)
                if match_char:
                    old_buffs = match_char.group(2).strip()
                    name_m = re.match(r"^\[([^\]]+)\]", str(buff_str).strip())
                    bname = name_m.group(1) if name_m else ""
                    if "无" in old_buffs or not old_buffs:
                        new_buffs = f"  - {buff_str}"
                    elif bname and f"[{bname}]" in old_buffs:
                        new_buffs = re.sub(
                            rf"-\s*\[{re.escape(bname)}\][^\n]*",
                            f"- {buff_str}",
                            old_buffs,
                            count=1,
                        )
                    else:
                        new_buffs = old_buffs + "\n" + f"  - {buff_str}"
                    buff_block = re.sub(char_pattern, rf"\g<1>{new_buffs}\n", buff_block, flags=re.DOTALL)
                    print(f" 💉 [持久化引擎] 收到前台请求，已为 {char} 挂载新 BUFF：{buff_str}")

    # 4. 如果当回合发生内射，后台自动为其追加/重置完整 24回合 的体液锁定 BUFF
    if shame_events:
        for char, tags in shame_events.items():
            if _event_tag('SHAME_06') in tags or _event_tag('SHAME_07') in tags:
                semen_str = "  - [持续_体液锁定] 剩余时效: 24回合 (效果: 欲望死锁不低于85)"
                char_pattern = rf"(▶\s*{re.escape(char)}\s*\n)(.*?)(?=\n▶|\n$|\Z)"
                match_char = re.search(char_pattern, buff_block, re.DOTALL)
                if match_char:
                    old_buffs = match_char.group(2).strip()
                    if "无" in old_buffs or not old_buffs:
                        new_buffs = semen_str
                    elif "[持续_体液锁定]" in old_buffs:
                        new_buffs = re.sub(
                            r"\[持续_体液锁定\]\s*剩余时效:\s*\d+回合(?:\s*\([^\n)]*\))?",
                            "[持续_体液锁定] 剩余时效: 24回合 (效果: 欲望死锁不低于85)",
                            old_buffs,
                        )
                    else:
                        new_buffs = old_buffs + "\n" + semen_str
                    buff_block = re.sub(char_pattern, rf"\g<1>{new_buffs}\n", buff_block, flags=re.DOTALL)
                    print(f" 💉 [持久化引擎] 监听到内射事件，已自动为 {char} 挂载 [持续_体液锁定: 24回合] BUFF！")

    # 5. 清理空行并确保没有BUFF的角色显示“- 无”
    lines = buff_block.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        if line.strip().startswith("▶"):
            has_buff = False
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("▶") and not lines[j].strip().startswith("="):
                if lines[j].strip().startswith("-") and "剩余时效" in lines[j]:
                    has_buff = True
                    break
                j += 1
            if not has_buff:
                new_lines.append("  - 无")
        i += 1
    
    # 重新组装过滤多余的“无”或空行
    current_char = None
    char_buffs = {}
    for line in new_lines:
        if line.strip().startswith("▶"):
            current_char = line.strip()
            char_buffs[current_char] = []
        elif current_char and line.strip().startswith("-"):
            val = line.strip()
            if val != "- 无" and val:
                char_buffs[current_char].append(val)
                
    res_block = "【当前持久化状态与BUFF】\n"
    for char, b_list in char_buffs.items():
        res_block += f"{char}\n"
        if not b_list:
            res_block += "  - 无\n"
        else:
            for b in b_list:
                res_block += f"  {b}\n"
                
    full_content = parts[0] + res_block + parts[2]
    with open(memory_file, "w", encoding="utf-8") as f:
        f.write(full_content)
    print(" [持久化引擎] BUFF 倒计时结算与存档更新完毕！")


def parse_persistent_buffs(content):
    """只读解析【当前持久化状态与BUFF】→ {角色名: [{'name', 'turns', 'effect'}]}"""
    result = {}
    if not content or "【当前持久化状态与BUFF】" not in content:
        return result
    m = re.search(r"【当前持久化状态与BUFF】([\s\S]*?)(?=\n={10,}|\n【|\n▲ 第一层：|\Z)", content)
    if not m:
        return result
    current_char = None
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("▶"):
            current_char = line.lstrip("▶").strip()
            result.setdefault(current_char, [])
            continue
        if current_char and line.startswith("-"):
            bm = re.match(r"^-\s*\[([^\]]+)\]\s*剩余时效:\s*(\d+)回合\s*\(([^)]*)\)", line)
            if bm:
                result[current_char].append({
                    "name": bm.group(1).strip(),
                    "turns": int(bm.group(2)),
                    "effect": bm.group(3).strip(),
                })
    return result


def parse_item_timers(content):
    """只读解析【道具倒计时】→ {ITEM-NNN: {'turns': int, 'name': str, 'status': str}}"""
    result = {}
    if not content or "【道具倒计时】" not in content:
        return result
    m = re.search(r"(?m)【道具倒计时】(.*?)(?=\n【|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return result
    for raw in m.group(1).splitlines():
        ln = raw.strip()
        if not ln or ln == "（空）":
            continue
        tm = re.match(r"^(ITEM-\d+)：(\d+)回合\s*\|\s*名称：(.+?)(?:\s*\|\s*状态：(.+))?$", ln)
        if tm:
            result[tm.group(1)] = {
                "turns": int(tm.group(2)),
                "name": tm.group(3).strip(),
                "status": (tm.group(4) or "进行中").strip(),
            }
    return result


def update_micro_states(micro_state_changes):
    """更新全局记忆库中的【当前激活微状态】区块"""
    if not micro_state_changes:
        return
    if not os.path.exists(MEMORY_FILE):
        return

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    for char_name, states in micro_state_changes.items() if micro_state_changes else []:
        for state_name, state_value in states.items() if states else []:
            pattern = rf"(▶\s*{re.escape(char_name)}\s*\n.*?{re.escape(state_name)}:\s*)(true|false)"
            replacement = rf"\g<1>{str(state_value).lower()}"
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f" [√] 微状态已更新：{list(micro_state_changes.keys())}")


def update_counters(counter_updates):
    """
    回合计数器区块：维护跨回合计数器（破局触发计数/空耗连续回合/连续守护回合等）。
    格式：【回合计数器】块位于 ▲第一层 之前（pre-L1 区，不受记忆引擎尾部重建影响）。
    counter_updates 形如 {"破局_日常冗余": 2, "空耗_连续未纾解": 1}：
      - 键已存在 → 覆写数值；键不存在 → 追加到块尾；未点名的键原样保留。
    归零/重置：显式写入 0 即可清除计数。
    """
    if not counter_updates or not isinstance(counter_updates, dict):
        return
    if not os.path.exists(MEMORY_FILE):
        return

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    anchor = "【回合计数器】"
    l1_idx = content.find("▲ 第一层：")
    if l1_idx == -1:
        return

    if anchor not in content:
        block = anchor + "\n" + "".join(f"  {k}: {v}\n" for k, v in counter_updates.items())
        content = content[:l1_idx] + block + "\n" + content[l1_idx:]
    else:
        for k, v in counter_updates.items():
            pat = re.compile(rf"(?m)^(\s*{re.escape(k)}:\s*)(-?\d+)")
            if pat.search(content):
                content = pat.sub(rf"\g<1>{v}", content, count=1)
            else:
                m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【监视状态】|\n【任务状态】|\n【道具倒计时】|\n▲ 第一层：|\Z)", content, re.DOTALL)
                if m:
                    block = m.group(1).rstrip() + f"\n  {k}: {v}\n"
                    content = content[:m.start(1)] + block + content[m.end(1):]

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f" [√] 回合计数器已更新：{list(counter_updates.keys())}")


# ============ 徐承邺监视矩阵（分渠道·分人物·五阶警惕值机制） ============
VIGILANCE_TARGETS = ("沈知韫", "苏婉青", "徐念薇", "徐志北")
VIGILANCE_LOCKED_FLOOR = 50  # 目击锁定后警惕下限
VIGILANCE_EXPOSURE_TAGS = ("内射", "外射", "高潮", "C烈度", "私密自渎", "自慰_暗中纾解")  # 暴露加分触发
VIGILANCE_SPILLOVER_RATIO = 0.30  # 女主异常行迹/眼线/目击引发同场徐志北连带警惕比例
VIGILANCE_TRACE_BONUS = 3  # 合法外传异常行迹时，若目标身上仍留未清理痕迹的额外兑现增幅

VIGILANCE_PROFILE = {
    "苏婉青": {
        "role_label": "妻子 · 极敏",
        "defected_role_label": "妻子 · 反水掩护",
        "gain_mult": 1.4,       # 异常行迹 +14 / 眼线 +7
        "defected_mult": 1.0,   # 揭穿眼线(INTEL-002)且好感>=70/羞耻<=50后反水降敏
        "witness_gain": 20,     # 亲眼目击 +20
        "decay_per_hour": 1.5,  # 最慢衰减（1h:-1, 2h:-3, 3h:-4, 4h:-6）
        "home_thresholds": ((85, 0.65), (65, 0.40), (40, 0.15)),
    },
    "沈知韫": {
        "role_label": "母亲 · 伦理盲区",
        "gain_mult": 1.0,       # 异常行迹 +10 / 眼线 +5
        "witness_gain": 15,
        "decay_per_hour": 2.0,
        "home_thresholds": ((85, 0.65), (65, 0.30), (50, 0.10)),
        "ethical_blindspot_below": 45,  # <45 时先入为主疑「争家业/偏心」，不疑母子私情
    },
    "徐念薇": {
        "role_label": "妹妹 · 易掩护",
        "gain_mult": 0.65,      # 异常行迹 +6 / 眼线 +3
        "witness_gain": 15,     # 目击/实锤绕过日常折扣按满额结算
        "decay_per_hour": 3.0,  # 最快衰减
        "home_thresholds": ((85, 0.65), (65, 0.30), (50, 0.10)),
    },
    "徐志北": {
        "role_label": "养弟 · 连带汇聚",
        "gain_mult": 1.0,
        "witness_gain": 15,
        "decay_per_hour": 2.0,
        "home_thresholds": ((85, 0.65), (65, 0.30), (50, 0.10)),
    },
}

_VIGILANCE_CHANNEL_RE = re.compile(
    r"电话|来电|视频|语音|微信|消息|短信|查岗|回拨|接听|未接|铃声|屏幕亮|"
    r"管家|保姆|阿姨|佣人|物业|保安|门禁|司机|助理|秘书|眼线|打听|汇报|传话|通风报信|"
    r"照片|拍照|监控|摄像头|录音|账单|刷卡|快递|记录|撞见|看见|推门|敲门|门外|走廊|大厅|旁人|路人|同事|会议室|徐承邺"
)


def vigilance_stage_info(vigilance, discovery=0):
    """Return (stage_0_to_4, stage_label) for the 5-tier vigilance model."""
    v = int(vigilance or 0)
    d = int(discovery or 0)
    if d >= 3:
        return 4, "目击锁定" if d == 3 else "证据实锤"
    if v >= 85:
        return 4, "摊牌"
    if v >= 65:
        return 3, "紧盯"
    if v >= 40:
        return 2, "查岗"
    if v >= 20:
        return 1, "起疑"
    return 0, "无察"


def _vigilance_return_prob(target, vigilance):
    prof = VIGILANCE_PROFILE.get(target) or VIGILANCE_PROFILE["徐志北"]
    v = int(vigilance or 0)
    for th, p in prof.get("home_thresholds", ((85, 0.65), (65, 0.30), (50, 0.10))):
        if v >= th:
            return float(p)
    return 0.0


def _compact_vigilance_reason(text, fallback=""):
    raw = str(text or "").replace("|", " ").replace("\n", " ").replace("\r", " ")
    raw = re.sub(r"\{([^|｜{}]+)[|｜][^{}]+\}", r"\1", raw)
    raw = re.sub(r"\[[^\]]{1,24}\]", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" ，。；：、\"'“”‘’")
    if not raw:
        return str(fallback or "")[:40]
    return (raw[:34] + "…") if len(raw) > 36 else raw


def _has_external_vigilance_channel(evidence="", scene_prose="", scene_privacy=""):
    """Check whether an out-of-town vigilance increase has an observable real-world transmission channel."""
    ev = str(evidence or "")
    if _VIGILANCE_CHANNEL_RE.search(ev):
        return True
    if scene_privacy == "open_public" and _VIGILANCE_CHANNEL_RE.search(str(scene_prose or "")):
        return True
    return False


def _is_su_defected(intel_state=None, su_stats=None):
    """Return True if INTEL-002 (苏婉青眼线身份) has been exposed/consumed AND Su Wanqing has high affection & low shame."""
    consumed = set((intel_state or {}).get("consumed") or [])
    if "INTEL-002" not in consumed:
        return False
    if not isinstance(su_stats, dict):
        return False
    aff = int(su_stats.get("好感", 0) or 0)
    shame = int(su_stats.get("羞耻", 100) or 100)
    return aff >= 70 and shame <= 50

# ============ 任务系统（AI生成属性型任务 · 后端判定 · 串行单任务） ============
TASK_WHITELIST = {
    "系统宿主": ["积分", "经验值", "商业嗅觉", "体力"],
    "沈知韫": ["好感"],
    "徐念薇": ["好感"],
    "苏婉青": ["好感"],
}  # 严格白名单：堕落/欲望/羞耻/高潮/怀孕/内射/被动Lv 硬禁（任务化会诱导越界剧情）
TASK_REWARDS = {"small": (20, 12), "medium": (45, 30), "large": (80, 50)}  # (积分, 经验) 固定档位
TASK_HISTORY_LIMIT = 3  # 最近完成保留条数
TASK_BLOCK_ANCHOR = "【任务状态】"


def _parse_vigilance_block(content):
    """解析【监视状态】块 → {'位置':..., '目标':{名:{警惕,发现,发现几率,动因}}}"""
    anchor = "【监视状态】"
    if anchor not in content:
        return None
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【任务状态】|\n【道具倒计时】|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    pos_m = re.search(r"徐承邺位置：(.+)", block)
    pos = pos_m.group(1).strip() if pos_m else "外地"
    targets = {}
    for name in VIGILANCE_TARGETS:
        tm = re.search(
            rf"徐承邺_{re.escape(name)}：警惕\s*(\d+)\s*\|\s*发现\s*(\d+)\s*\|\s*发现几率\s*(\d+)(?:\s*\|\s*动因[：:]\s*([^\n|]+))?",
            block)
        if tm:
            targets[name] = {
                "警惕": int(tm.group(1)),
                "发现": int(tm.group(2)),
                "发现几率": int(tm.group(3)),
                "动因": (tm.group(4) or "").strip()[:48],
            }
    return {"位置": pos, "目标": targets}


def _is_exposed(target, shame_events, ds_events=None):
    """目标本回合是否有越界/私密暴露（覆盖 SHAME 与 DS 合法暴露标签）"""
    tags = []
    if isinstance(shame_events, dict) and isinstance(shame_events.get(target), list):
        tags.extend(shame_events[target])
    if isinstance(ds_events, dict) and isinstance(ds_events.get(target), list):
        tags.extend(ds_events[target])
    if not tags:
        return False
    return any(any(k in t for k in VIGILANCE_EXPOSURE_TAGS) for t in tags if isinstance(t, str))


def _apply_vigilance_tags(
    vig,
    events,
    *,
    active_cast=None,
    event_evidences=None,
    scene_prose="",
    scene_privacy="",
    traces=None,
    intel_state=None,
    su_stats=None,
    enforce_channel_gate=False,
    host_biz=0,
    leverage_active=False,
):
    """按语义标签、人物敏感度、感知渠道门禁与商战反制结算警惕/发现程度；目击(发现>=3)后警惕下限锁定、降警惕标签无效。"""
    xcy_abroad = vig.get("位置", "外地") in ("", "外地") and ("徐承邺" not in (active_cast or ()))
    su_defected = _is_su_defected(intel_state=intel_state, su_stats=su_stats)
    ev_map = event_evidences if isinstance(event_evidences, dict) else {}
    traces_map = traces if isinstance(traces, dict) else {}
    counter_intel = int(host_biz or 0) >= 80
    lev_suppress_budget = 10 if leverage_active else 0
    direct_gains = {}
    heroine_spill_sources = []

    for target, tags in (events or {}).items():
        if target not in vig["目标"] or not isinstance(tags, list):
            continue
        t = vig["目标"][target]
        locked = t["发现"] >= 3
        prof = VIGILANCE_PROFILE.get(target) or VIGILANCE_PROFILE["徐志北"]
        mult = prof["defected_mult"] if (target == "苏婉青" and su_defected) else prof["gain_mult"]
        ev_text = str(ev_map.get(target) or "")
        before_v = t["警惕"]
        turn_pos_gain = 0
        pos_reason_fallback = ""

        for tag in tags:
            if tag == _event_tag('VIGILANCE_01'):
                if enforce_channel_gate and xcy_abroad:
                    print(f" 🔒 [监视矩阵·感知门禁] 徐承邺在外地，拦截 {target} 的「目击确认」标签。")
                    continue
                add = int(prof.get("witness_gain", _event_param('VIGILANCE_01', 't_01')))
                t["警惕"] += add
                t["发现"] = max(t["发现"], _event_param('VIGILANCE_01', 't_02'))
                turn_pos_gain += add
                pos_reason_fallback = "亲眼目击异常"
            elif tag == _event_tag('VIGILANCE_02'):
                t["发现"] = max(t["发现"], _event_param('VIGILANCE_02', 't_01'))
                pos_reason_fallback = pos_reason_fallback or "掌握实锤物证"
            elif tag == _event_tag('VIGILANCE_03'):
                if enforce_channel_gate and xcy_abroad and not _has_external_vigilance_channel(ev_text, scene_prose, scene_privacy):
                    print(f" 🔒 [监视矩阵·感知门禁] 徐承邺在外地且无外部传导渠道，拦截 {target} 密室「异常行迹」（不涨警惕）。")
                    continue
                base = _event_param('VIGILANCE_03', 't_01')
                add = max(1, int(round(base * mult)))
                if isinstance(traces_map.get(target), list) and len(traces_map[target]) > 0:
                    add += VIGILANCE_TRACE_BONUS
                    print(f" 🔎 [监视矩阵] {target} 身上/现场仍有未清理痕迹，异常行迹额外兑现 +{VIGILANCE_TRACE_BONUS} 警惕。")
                if counter_intel and add > 1:
                    ci_cut = max(1, int(round(add * 0.15)))
                    add = max(1, add - ci_cut)
                    print(f" ♟️ [监视矩阵] 商业嗅觉≥80（深局棋手信息反制），{target} 异常行迹警惕减缓 -{ci_cut} -> +{add}。")
                if lev_suppress_budget > 0 and add > 0:
                    cut = min(add, lev_suppress_budget)
                    add -= cut
                    lev_suppress_budget -= cut
                    print(f" ⚖️ [监视矩阵] 商业杠杆压制当轮非目击警惕 -{cut} -> +{add}。")
                if add > 0:
                    t["警惕"] += add
                    t["发现"] = max(t["发现"], min(t["发现"] + _event_param('VIGILANCE_03', 't_02'), _event_param('VIGILANCE_03', 't_03')))
                    turn_pos_gain += add
                    pos_reason_fallback = pos_reason_fallback or "察觉异常行迹"
            elif tag == _event_tag('VIGILANCE_04'):
                if su_defected and target != "苏婉青" and "苏婉青" in ev_text and not re.search(r"管家|保姆|物业|司机|助理|保安", ev_text):
                    print(f" 🕶️ [监视矩阵] 苏婉青已反水掩护，拦截其作为眼线对 {target} 的汇报。")
                    continue
                base = _event_param('VIGILANCE_04', 't_01')
                add = max(1, int(round(base * mult)))
                if counter_intel and add > 1:
                    ci_cut = max(1, int(round(add * 0.15)))
                    add = max(1, add - ci_cut)
                    print(f" ♟️ [监视矩阵] 商业嗅觉≥80（深局棋手信息反制），{target} 眼线汇报警惕减缓 -{ci_cut} -> +{add}。")
                if lev_suppress_budget > 0 and add > 0:
                    cut = min(add, lev_suppress_budget)
                    add -= cut
                    lev_suppress_budget -= cut
                    print(f" ⚖️ [监视矩阵] 商业杠杆压制当轮眼线警惕 -{cut} -> +{add}。")
                if add > 0:
                    t["警惕"] += add
                    t["发现"] = max(t["发现"], min(t["发现"] + _event_param('VIGILANCE_04', 't_02'), _event_param('VIGILANCE_04', 't_03')))
                    turn_pos_gain += add
                    pos_reason_fallback = pos_reason_fallback or "收到眼线汇报"
            elif tag == _event_tag('VIGILANCE_05'):
                if not locked:
                    t["警惕"] -= _event_param('VIGILANCE_05', 't_01')
            elif tag == _event_tag('VIGILANCE_06'):
                if not locked:
                    t["警惕"] -= _event_param('VIGILANCE_06', 't_01')
            elif tag == _event_tag('VIGILANCE_07'):
                if not locked:
                    t["警惕"] -= _event_param('VIGILANCE_07', 't_01')
            elif tag in (_event_tag('VIGILANCE_08'), _event_tag('VIGILANCE_09')):
                if not locked:
                    t["警惕"] -= _event_param('VIGILANCE_08', 't_01')
            elif tag == _event_tag('VIGILANCE_10'):
                pass  # 时间衰减由后端每回合统一执行

        if t["发现"] >= 3 and t["警惕"] < VIGILANCE_LOCKED_FLOOR:
            t["警惕"] = VIGILANCE_LOCKED_FLOOR
        t["警惕"] = min(100, max(0, t["警惕"]))
        if turn_pos_gain > 0 or pos_reason_fallback:
            t["动因"] = _compact_vigilance_reason(ev_text, fallback=pos_reason_fallback)
        actual_gain = max(0, t["警惕"] - before_v)
        if actual_gain > 0:
            direct_gains[target] = actual_gain
            if target in ("沈知韫", "苏婉青", "徐念薇") and (active_cast is None or target in active_cast):
                heroine_spill_sources.append((target, actual_gain))

    # 30% 跨目标连带汇聚：同场女主因异常/眼线/目击涨警惕时，徐志北同步分担 30% 联动警惕
    if heroine_spill_sources and "徐志北" in vig["目标"]:
        spill_total = min(10, sum(max(1, int(round(g * VIGILANCE_SPILLOVER_RATIO))) for _, g in heroine_spill_sources))
        direct_host = direct_gains.get("徐志北", 0)
        extra_host = max(0, spill_total - direct_host)
        if extra_host > 0:
            ht = vig["目标"]["徐志北"]
            ht["警惕"] = min(100, max(0, ht["警惕"] + extra_host))
            if ht["发现"] == 0 and ht["警惕"] >= 20:
                ht["发现"] = 1
            src_names = "、".join(n for n, _ in heroine_spill_sources)
            if not ht.get("动因"):
                ht["动因"] = f"受{src_names}异常动向连带波及"
            print(f" 🔗 [监视矩阵] 养弟连带汇聚：{src_names} 引发警惕外溢，徐志北警惕 +{extra_host}（当前 {ht['警惕']}）。")


def _write_vigilance_block(vig, memory_file=None):
    """将结算后的监视状态写回【监视状态】块（锚点维护，与 update_counters 同模式）"""
    target_file = memory_file or MEMORY_FILE
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = "【监视状态】"
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【任务状态】|\n【道具倒计时】|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return
    lines = [anchor, f"徐承邺位置：{vig['位置']}"]
    for name in VIGILANCE_TARGETS:
        t = vig["目标"][name]
        reason = str(t.get("动因") or "").replace("|", " ").replace("\n", " ").strip()[:48]
        suffix = f" | 动因：{reason}" if reason and (t["警惕"] > 0 or t["发现"] > 0) else ""
        lines.append(f"徐承邺_{name}：警惕 {t['警惕']} | 发现 {t['发现']} | 发现几率 {t['发现几率']}{suffix}")
    block = "\n".join(lines) + "\n"
    content = content[:m.start(1)] + block + content[m.end(1):]
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(" [√] 监视状态块已更新")


def process_vigilance_system(
    vigilance_events,
    shame_events,
    memory_file,
    *,
    elapsed_hours=None,
    roll_home=True,
    active_cast=None,
    ds_events=None,
    event_evidences=None,
    scene_prose="",
    scene_privacy="",
    traces=None,
    intel_state=None,
    su_stats=None,
    enforce_channel_gate=False,
    host_biz=0,
    leverage_active=False,
):
    """
    徐承邺监视矩阵全自动结算：
    感知渠道门禁 / 分人物敏感度与伦理盲区 / 商战反制与杠杆压制 / 30% 养弟连带 / 分人物时间衰减 /
    五阶分人物回返掷骰（苏婉青40起15%·沈/徐50起10%·65起30~40%·85起65%）/ 发现几率。
    每回合常驻执行（即使 AI 未打标签也走时间衰减与回返判定）。
    """
    if not os.path.exists(memory_file):
        return {}
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    vig = _parse_vigilance_block(content)
    if not vig:
        return {}

    _apply_vigilance_tags(
        vig,
        vigilance_events or {},
        active_cast=active_cast,
        event_evidences=event_evidences,
        scene_prose=scene_prose,
        scene_privacy=scene_privacy,
        traces=traces,
        intel_state=intel_state,
        su_stats=su_stats,
        enforce_channel_gate=enforce_channel_gate,
        host_biz=host_biz,
        leverage_active=leverage_active,
    )

    # 死亡查岗衔接：查岗未抓实锤 → 该次越界目标警惕 -10（虚惊回落）
    for target, tags in (shame_events or {}).items():
        if target in vig["目标"] and isinstance(tags, list) and _event_tag('SHAME_08') in tags:
            if vig["目标"][target]["发现"] < _event_param('SHAME_08', 'vig_target_02'):
                vig["目标"][target]["警惕"] = max(_event_param('SHAME_08', 'vig_target_03'), vig["目标"][target]["警惕"] - _event_param('SHAME_08', 'vig_target_04'))

    # 分人物时间衰减：苏婉青 -1.5/h、沈知韫/徐志北 -2/h、徐念薇 -3/h；目击锁定目标不衰减
    hours = 1 if elapsed_hours is None else max(0, int(elapsed_hours))
    for name, t in vig["目标"].items():
        if t["发现"] < 3 and hours > 0 and t["警惕"] > 0:
            rate = float((VIGILANCE_PROFILE.get(name) or {}).get("decay_per_hour", 2.0))
            decay = max(1, int(rate * hours))
            t["警惕"] = max(0, t["警惕"] - decay)
        if t["警惕"] == 0 and t["发现"] < 3:
            t["发现"] = 0
            t["动因"] = ""

    # 在场集合：读取各角色真实所在
    presence = parse_presence_from_memory(content)
    at_home = {name for name, info in presence.items() if "徐家主宅" in info.get("location", "")}
    at_apt = {name for name, info in presence.items() if "市中心顶层公寓" in info.get("location", "")}

    # 五阶分人物回返掷骰：若徐承邺本段正同场对峙则保持当前在场位置，禁止中途随机瞬移回外地
    target_probs = {name: _vigilance_return_prob(name, t["警惕"]) for name, t in vig["目标"].items()}
    prob = max(target_probs.values(), default=0.0)
    on_stage_confronting = bool(active_cast and '徐承邺' in active_cast and vig.get("位置") not in ("", "外地"))
    if roll_home and not on_stage_confronting:
        if prob > 0.0 and random.random() < prob:
            su_prob = target_probs.get("苏婉青", 0.0)
            su_vig = vig["目标"].get("苏婉青", {}).get("警惕", 0)
            home_prio = max(
                ((target_probs.get(n, 0.0), vig["目标"][n]["警惕"]) for n in at_home if n in vig["目标"]),
                default=(0.0, 0),
            )
            if "苏婉青" in at_apt and su_prob > 0.0 and (su_prob, su_vig) >= home_prio:
                vig["位置"] = "市中心顶层公寓"
            else:
                vig["位置"] = "徐家主宅"
        else:
            vig["位置"] = "外地"

    # 发现几率：徐承邺在场且目标同地才可能发现（兼容历史存档「徐家住宅」）
    vig_loc = "徐家主宅" if vig["位置"] == "徐家住宅" else vig["位置"]
    co_present = at_home if vig_loc == "徐家主宅" else (at_apt if vig_loc == "市中心顶层公寓" else set())
    for name, t in vig["目标"].items():
        if vig_loc in ("徐家主宅", "市中心顶层公寓") and name in co_present:
            expo = 30 if _is_exposed(name, shame_events, ds_events=ds_events) else 0
            t["发现几率"] = min(100, 20 + t["警惕"] // 2 + expo)
        else:
            t["发现几率"] = 0

    _write_vigilance_block(vig, memory_file=memory_file)
    summary = {"徐承邺位置": vig["位置"]}
    for name, t in vig["目标"].items():
        summary[f"徐承邺_{name}"] = f"警惕 {t['警惕']} | 发现 {t['发现']} | 发现几率 {t['发现几率']}"
    print(f" [监视矩阵] 徐承邺回返判定：概率 {prob:.0%} → 位置 {vig['位置']} · {summary}")
    return summary


# ============ 任务系统：AI生成属性型任务 · 后端判定 · 串行单任务 ============

def _parse_task_block(content):
    """解析【任务状态】块 → {'current':..., 'history':[...], 'pending_item':..., 'pending_items':[...]}；无块返回 None"""
    anchor = TASK_BLOCK_ANCHOR
    if anchor not in content:
        return None
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    state = {"current": None, "history": [], "pending_item": None, "pending_items": []}

    # 当前任务：TASK-003 | 标题 | 目标·属性·值 | 档位 | 道具描述 | 状态 | 发布回合N [| 完成回合M]
    cm = re.search(
        r"当前任务：TASK-(\d+) \| ([^|]+) \| ([^|·]+)·([^|·]+)·(\d+) \| (\w+) \| ([^|]+) \| (\S+) \|发布回合(\d+)(?: \|完成回合(\d+))?",
        block,
    )
    if cm:
        state["current"] = {
            "id": f"TASK-{int(cm.group(1)):03d}",
            "title": cm.group(2).strip(),
            "target": cm.group(3).strip(),
            "attr": cm.group(4).strip(),
            "value": int(cm.group(5)),
            "tier": cm.group(6).strip(),
            "item_desc": cm.group(7).strip(),
            "status": cm.group(8).strip(),
            "issue_round": int(cm.group(9)),
            "complete_round": int(cm.group(10)) if cm.group(10) else None,
        }

    # 最近完成：空格缩进行（TASK-NNN | 标题 | 描述 | 完成于回合N | 奖励...）
    hm = re.search(r"最近完成：\n((?: TASK-\d+ \| [^\n]+\n?)*)", block)
    if hm and hm.group(1).strip():
        state["history"] = [ln.strip() for ln in hm.group(1).strip().splitlines() if ln.strip()]

    # 待发道具：兼容单行「待发道具：TASK-NNN | ...」与多行队列「待发道具：\n TASK-NNN | ...」
    pending_hits = re.findall(r"(?:待发道具：|\n )TASK-(\d+) \| ([^|\n]+) \|完成回合(\d+)", block)
    pending_items = list(dict.fromkeys(
        f"TASK-{int(tid):03d} | {desc.strip()} |完成回合{int(rnd)}"
        for tid, desc, rnd in pending_hits
    ))
    state["pending_items"] = pending_items
    state["pending_item"] = pending_items[0] if pending_items else None
    return state


def _write_task_block(state):
    """将结算后的任务状态写回【任务状态】块（支持待发道具队列，防未领取奖励被覆写）"""
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = TASK_BLOCK_ANCHOR
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return
    lines = [anchor]
    cur = state.get("current")
    if cur:
        line = (f"当前任务：{cur['id']} | {cur['title']} | {cur['target']}·{cur['attr']}·{cur['value']} "
                f"| {cur['tier']} | {cur['item_desc']} | {cur['status']} |发布回合{cur['issue_round']}")
        if cur.get("complete_round"):
            line += f" |完成回合{cur['complete_round']}"
        lines.append(line)
    else:
        lines.append("当前任务：（无）")
    if state.get("history"):
        lines.append("最近完成：")
        for h in state["history"]:
            lines.append(" " + h)
    else:
        lines.append("最近完成：（空）")
    if "pending_items" in state and isinstance(state["pending_items"], list):
        pending_items = [str(x).strip() for x in state["pending_items"] if str(x).strip()]
        # 兼容旧调用方仅通过 state["pending_item"] = None 弹出队首的行为
        if state.get("pending_item") is None and len(pending_items) == 1:
            pending_items = []
        elif state.get("pending_item") and state["pending_item"] not in pending_items:
            pending_items.insert(0, str(state["pending_item"]).strip())
    else:
        pending_items = [str(state["pending_item"]).strip()] if state.get("pending_item") else []
    pending_items = list(dict.fromkeys(pending_items))
    state["pending_items"] = pending_items
    state["pending_item"] = pending_items[0] if pending_items else None
    if not pending_items:
        lines.append("待发道具：（无）")
    elif len(pending_items) == 1:
        lines.append("待发道具：" + pending_items[0])
    else:
        lines.append("待发道具：")
        for pitem in pending_items:
            lines.append(" " + pitem)
    block = "\n".join(lines) + "\n"
    content = content[:m.start(1)] + block + content[m.end(1):]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(" [√] 任务状态块已更新")


def _read_attr_value(content, target, attr):
    """读面板最新区目标属性当前值；读不到返回 None"""
    if target == "系统宿主":
        m = re.search(rf"\[系统宿主\].*?{re.escape(attr)}\s*(-?\d+)", content)
    else:
        m = re.search(rf"\[{re.escape(target)}\].*?{re.escape(attr)}\s*(-?\d+)", content)
    return int(m.group(1)) if m else None


def _read_host_panel(memory_file):
    """读宿主面板绝对值 → {'积分','经验值','体力','商业嗅觉'}；读不到返回 None"""
    if not os.path.exists(memory_file):
        return None
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"\[系统宿主\].*?积分\s*(-?\d+).*?经验值\s*(-?\d+).*?体力\s*(-?\d+).*?商业嗅觉\s*(-?\d+)", content)
    if not m:
        return None
    return {
        "积分": int(m.group(1)),
        "经验值": int(m.group(2)),
        "体力": int(m.group(3)),
        "商业嗅觉": int(m.group(4)),
    }


def _simulate_panel(content, panel_changes):
    """用本回合 panel_changes 在内存中模拟面板最新值（不写文件），供任务判定使用。
    使任务判定基准 = 面板最终显示值（本回合结算后），而非上回合持久化旧值。"""
    if not panel_changes or not isinstance(panel_changes, dict):
        return content
    for char, changes in panel_changes.items():
        if not isinstance(changes, dict):
            continue
        for key, value in changes.items():
            pattern = rf"(\[{re.escape(char)}\].*?{re.escape(key)}\s*)(-?\d+|False|True|Lv\.\d+|\d+%)"
            content = re.sub(pattern, rf"\g<1>{value}", content, count=1)
    return content


def _validate_task(task_issue, content, *, baseline_content=None):
    """校验新任务：白名单 / 目标>当前 / tier合法 / title与item_desc非空。返回 (ok, err)"""
    if not isinstance(task_issue, dict):
        return False, "task_issue 非字典"
    title = str(task_issue.get("title") or "").strip()
    target = str(task_issue.get("target") or "").strip()
    attr = str(task_issue.get("attr") or "").strip()
    tier = str(task_issue.get("tier") or "").strip()
    item_desc = str(task_issue.get("item_desc") or "").strip()
    if not title:
        return False, "title 为空"
    if target not in TASK_WHITELIST:
        return False, f"目标 {target} 不在白名单"
    if attr not in TASK_WHITELIST[target]:
        return False, f"属性 {attr} 不在 {target} 白名单"
    if tier not in TASK_REWARDS:
        return False, f"档位 {tier} 非法（small/medium/large）"
    if not item_desc:
        return False, "item_desc 为空"
    try:
        value = int(task_issue.get("value"))
    except (TypeError, ValueError):
        return False, "value 非整数"
    if value <= 0:
        return False, "value 必须为正整数"
    ref_content = baseline_content if baseline_content is not None else content
    cur_val = _read_attr_value(ref_content, target, attr)
    if cur_val is None:
        return False, f"读取不到 {target} 的 {attr} 当前值"
    if value <= cur_val:
        return False, f"目标值 {value} 必须大于当前值 {cur_val}"
    return True, None


def _next_task_id(state):
    """生成下一个 TASK-ID（当前 + 历史 + 待领队列最大值 +1）"""
    nums = []
    if state.get("current"):
        m = re.search(r"TASK-(\d+)", state["current"]["id"])
        if m:
            nums.append(int(m.group(1)))
    for h in state.get("history") or []:
        m = re.search(r"TASK-(\d+)", h)
        if m:
            nums.append(int(m.group(1)))
    for p in state.get("pending_items") or []:
        m = re.search(r"TASK-(\d+)", p)
        if m:
            nums.append(int(m.group(1)))
    return f"TASK-{max(nums) + 1 if nums else 1:03d}"


def process_task_system(task_issue, current_round, memory_file, sim_content=None, *, pre_event_content=None):
    """
    任务系统：每回合常驻结算（参照监视矩阵）。
    1) 当前任务进行中 → 读面板目标属性（sim_content 为本回合结算后的模拟面板，缺省读文件持久化值）
       → 达标则标记已完成、结算积分/经验（返回增量）、写最近完成并追加至待发道具队列。
    2) 无进行中任务且 task_issue 非空 → 校验（白名单/目标>基线当前/单任务互斥）→ 挂载新任务，
       严格保留尚未领取的 pending_items 队列（绝不清空未领奖励）。
    返回积分/经验增量 dict（无结算返回 {}）。
    """
    if not os.path.exists(memory_file):
        return {}
    if sim_content is not None:
        content = sim_content
    else:
        with open(memory_file, "r", encoding="utf-8") as f:
            content = f.read()
    state = _parse_task_block(content)
    if state is None:
        return {}
    delta = {}

    # 1. 当前任务判定（常驻，与是否提交 task_issue 无关）
    cur = state.get("current")
    has_active = bool(cur and cur.get("status") == "进行中")
    if has_active:
        cur_val = _read_attr_value(content, cur["target"], cur["attr"])
        if cur_val is not None and cur_val >= cur["value"]:
            points, exp = TASK_REWARDS.get(cur["tier"], TASK_REWARDS["small"])
            cur["status"] = "已完成"
            cur["complete_round"] = current_round
            hist = (f"{cur['id']} | {cur['title']} | {cur['target']}{cur['attr']}达到{cur['value']}"
                    f" |完成于回合{current_round} |奖励积分+{points}经验+{exp}道具×1")
            state["history"].insert(0, hist)
            state["history"] = state["history"][:TASK_HISTORY_LIMIT]
            pending_line = f"{cur['id']} | {cur['item_desc']} |完成回合{current_round}"
            if pending_line not in state["pending_items"]:
                state["pending_items"].append(pending_line)
            state["pending_item"] = state["pending_items"][0]
            delta = {"积分": points, "经验值": exp}
            print(f" 🎯 [任务系统] {cur['id']}「{cur['title']}」完成！积分+{points} 经验+{exp}，待发道具已入队")

    # 2. 新任务挂载（无进行中任务且 AI 提交 task_issue；已完成任务可被替换，且绝不清空未领 pending_items）
    if has_active and task_issue:
        raise ValueError("已有进行中任务，不能覆盖")
    if not has_active and task_issue:
        ok, err = _validate_task(task_issue, content, baseline_content=pre_event_content)
        if ok:
            state["current"] = {
                "id": _next_task_id(state),
                "title": str(task_issue["title"]).strip(),
                "target": str(task_issue["target"]).strip(),
                "attr": str(task_issue["attr"]).strip(),
                "value": int(task_issue["value"]),
                "tier": str(task_issue["tier"]).strip(),
                "item_desc": str(task_issue["item_desc"]).strip(),
                "status": "进行中",
                "issue_round": current_round,
                "complete_round": None,
            }
            # 若挂接目标按 pre_event 合法但本幕事件已正好超过，顺带直接判定完成
            post_val = _read_attr_value(content, state["current"]["target"], state["current"]["attr"])
            if pre_event_content is not None and post_val is not None and post_val >= state["current"]["value"]:
                c2 = state["current"]
                points, exp = TASK_REWARDS.get(c2["tier"], TASK_REWARDS["small"])
                c2["status"] = "已完成"
                c2["complete_round"] = current_round
                hist = (f"{c2['id']} | {c2['title']} | {c2['target']}{c2['attr']}达到{c2['value']}"
                        f" |完成于回合{current_round} |奖励积分+{points}经验+{exp}道具×1")
                state["history"].insert(0, hist)
                state["history"] = state["history"][:TASK_HISTORY_LIMIT]
                pending_line = f"{c2['id']} | {c2['item_desc']} |完成回合{current_round}"
                if pending_line not in state["pending_items"]:
                    state["pending_items"].append(pending_line)
                state["pending_item"] = state["pending_items"][0]
                delta = {"积分": delta.get("积分", 0) + points, "经验值": delta.get("经验值", 0) + exp}
            t = state["current"]
            print(f" 📌 [任务系统] 新任务挂载：{t['id']}「{t['title']}」（{t['target']}·{t['attr']}≥{t['value']}）")
        else:
            raise ValueError(f"任务生成被拒绝：{err}")

    _write_task_block(state)
    return delta


# 人物所在默认锚点（防闪现；与法典卷三驻地表一致）
DEFAULT_PRESENCE = {
    "沈知韫": ("徐家主宅", "常住"),
    "徐念薇": ("大学", "工作日在大学"),
    "苏婉青": ("市中心顶层公寓", "常住"),
    "徐志北": ("徐家主宅", "常住"),
}


def _format_presence_block(presence_map):
    """presence_map: {角色名: (地点, 事由)} — 仅事实行，不写教学文案"""
    lines = ["【人物所在】"]
    for name in ("沈知韫", "徐念薇", "苏婉青", "徐志北"):
        loc, reason = presence_map.get(name, DEFAULT_PRESENCE[name])
        lines.append(f"{name}：{loc} | 事由：{reason}")
    return "\n".join(lines) + "\n"


def parse_presence_from_memory(content=None):
    """读取记忆库【人物所在】，返回 {角色: {location, reason}}。缺块则用默认。"""
    result = {
        n: {"location": loc, "reason": reason}
        for n, (loc, reason) in DEFAULT_PRESENCE.items()
    }
    if content is None:
        if not os.path.exists(MEMORY_FILE):
            return result
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    m = re.search(
        r"【人物所在】[^\n]*\n(.*?)(?=\n【当前激活微状态】|\n▶ 上回合历史快照|\n={5,}|\n【当前持久化)",
        content,
        re.DOTALL,
    )
    if not m:
        return result
    block = m.group(1)
    for name in result.keys():
        lm = re.search(
            rf"{re.escape(name)}：\s*([^|\n]+?)\s*\|\s*事由：\s*([^\n]+)",
            block,
        )
        if lm:
            result[name] = {
                "location": lm.group(1).strip(),
                "reason": lm.group(2).strip(),
            }
    return result


def ensure_presence_block(content):
    """若记忆库缺少【人物所在】区块，插入到【当前激活微状态】之前。"""
    if "【人物所在】" in content:
        return content
    block = _format_presence_block(dict(DEFAULT_PRESENCE))
    anchor = "【当前激活微状态】"
    if anchor in content:
        return content.replace(anchor, block + "\n" + anchor, 1)
    # 兜底：插在最新数值块后
    m = re.search(r"(▶ 当前最新数值\n.*?\n)(\n+)", content, re.DOTALL)
    if m:
        return content[: m.end(1)] + "\n" + block + "\n" + content[m.end(1) :]
    return block + "\n" + content


def update_presence(presence_changes):
    """
    更新【人物所在】。
    presence_changes 支持：
      {"苏婉青": {"location": "徐家主宅", "reason": "周五请安"}}
      {"苏婉青": "市中心顶层公寓|回公寓"}
      {"苏婉青": "市中心顶层公寓"}
    未点名的角色原样继承。空 dict 时仅确保区块存在。
    """
    if not os.path.exists(MEMORY_FILE):
        return

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    content = ensure_presence_block(content)
    current = parse_presence_from_memory(content)
    presence_map = {
        n: (current[n]["location"], current[n]["reason"]) for n in DEFAULT_PRESENCE
    }

    if presence_changes and isinstance(presence_changes, dict):
        for name, val in presence_changes.items():
            if name not in DEFAULT_PRESENCE:
                # 允许扩展角色，但不强制进默认四人表
                continue
            if isinstance(val, dict):
                loc = str(val.get("location") or val.get("loc") or presence_map[name][0]).strip()
                reason = str(val.get("reason") or val.get("事由") or "剧情移动").strip()
            else:
                s = str(val).strip()
                if "|" in s:
                    loc, reason = [x.strip() for x in s.split("|", 1)]
                elif "｜" in s:
                    loc, reason = [x.strip() for x in s.split("｜", 1)]
                else:
                    loc, reason = s, "剧情移动"
            if not loc:
                continue
            presence_map[name] = (loc, reason or "剧情移动")
            print(f" [所在] {name} → {loc}（{reason}）")

    new_block = _format_presence_block(presence_map)
    # 整段替换【人物所在】…到下一主区块之前
    pattern = re.compile(
        r"【人物所在】[^\n]*\n.*?(?=\n【当前激活微状态】|\n▶ 上回合历史快照|\n={5,}|\n【当前持久化)",
        re.DOTALL,
    )
    if pattern.search(content):
        content = pattern.sub(new_block.rstrip() + "\n", content, count=1)
    else:
        content = ensure_presence_block(content)

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(" [√] 人物所在锚点已同步")


class MemoryTransitionValidationError(ValueError):
    """记忆层转移前置校验失败，禁止继续执行注入。"""
    pass


_MEMORY_LAYER_PREFIXES = (
    ("L1", "▲ 第一层：", 3),
    ("L2", "▲ 第二层：", 10),
    ("L3", "▲ 第三层：", 10),
    ("L4", "▲ 第四层：", None),
)
_MEMORY_ITEM_RE = re.compile(
    r"(【\d+(?:-\d+)?】[^\r\n]*(?:\r?\n(?!(?:【\d|▲)).*)*)"
)
_MEMORY_LABEL_RE = re.compile(r"^\s*【(\d+)(?:-(\d+))?】")
_MEMORY_EMPTY_MARKERS = frozenset({
    "", "（空）", "(空)", "（当前为空）", "(当前为空)",
    "...", "…", "无", "none", "None",
})
_MEMORY_EMPTY_MARKERS_CASEFOLD = frozenset(
    marker.casefold() for marker in _MEMORY_EMPTY_MARKERS
)


def _memory_transition_error(message):
    raise MemoryTransitionValidationError(
        "[记忆层校验失败] " + str(message)
    )


def _parse_memory_layer_items(content):
    """只读解析 L1-L4，返回 {L1: [...], ...}；结构异常时抛错。"""
    if not isinstance(content, str):
        _memory_transition_error("记忆库内容不是文本。")

    matches_by_layer = {}
    for label, prefix, _cap in _MEMORY_LAYER_PREFIXES:
        matches = list(re.finditer(
            rf"(?m)^[ \t]*{re.escape(prefix)}[^\r\n]*$",
            content,
        ))
        if len(matches) != 1:
            _memory_transition_error(
                f"{label}锚点数量异常：应为1，实际为{len(matches)}。"
            )
        matches_by_layer[label] = matches[0]

    ordered = [
        matches_by_layer[label].start()
        for label, _prefix, _cap in _MEMORY_LAYER_PREFIXES
    ]
    if any(left >= right for left, right in zip(ordered, ordered[1:])):
        _memory_transition_error("L1-L4锚点顺序异常。")

    layers = {}
    for index, (label, _prefix, _cap) in enumerate(_MEMORY_LAYER_PREFIXES):
        start = matches_by_layer[label].end()
        if index + 1 < len(_MEMORY_LAYER_PREFIXES):
            end = matches_by_layer[
                _MEMORY_LAYER_PREFIXES[index + 1][0]
            ].start()
        else:
            end = len(content)

        body = content[start:end]
        item_matches = list(_MEMORY_ITEM_RE.finditer(body))
        residual = _MEMORY_ITEM_RE.sub("", body).strip()
        if residual and residual.casefold() not in _MEMORY_EMPTY_MARKERS_CASEFOLD:
            _memory_transition_error(
                f"{label}包含无法识别的非条目内容：{residual[:80]}"
            )

        items = []
        for item_match in item_matches:
            item = item_match.group(1).strip()
            label_match = _MEMORY_LABEL_RE.match(item)
            if not label_match:
                _memory_transition_error(
                    f"{label}存在非法条目标记：{item[:80]}"
                )
            start_round = int(label_match.group(1))
            end_round = int(label_match.group(2) or start_round)
            if start_round > end_round:
                _memory_transition_error(
                    f"{label}存在逆序回合范围：{item[:80]}"
                )
            items.append(item)
        layers[label] = items

    return layers


def _memory_item_range(item):
    """返回条目首部的 (起始回合, 结束回合)。"""
    match = _MEMORY_LABEL_RE.match(str(item or ""))
    if not match:
        _memory_transition_error(
            f"无法读取记忆条目回合范围：{str(item)[:80]}"
        )
    return int(match.group(1)), int(match.group(2) or match.group(1))


def _memory_layer_range(items, layer_label):
    if not items:
        _memory_transition_error(
            f"{layer_label}为空，无法校验待转移摘要来源范围。"
        )
    first_start, _first_end = _memory_item_range(items[0])
    _last_start, last_end = _memory_item_range(items[-1])
    return first_start, last_end


def _validate_memory_summary(summary, source_items, source_label):
    """校验摘要非空、非占位；若带首部范围则必须匹配源层。"""
    value = str(summary or "").strip()
    value_casefold = value.casefold()
    if not value or value_casefold in _MEMORY_EMPTY_MARKERS_CASEFOLD:
        _memory_transition_error(
            f"{source_label}转移摘要为空或为占位值。"
        )
    if "xxxxxxxxx" in value_casefold:
        _memory_transition_error(
            f"{source_label}转移摘要包含占位内容。"
        )

    expected = _memory_layer_range(source_items, source_label)
    explicit = _MEMORY_LABEL_RE.match(value)
    if value.startswith("【") and explicit is None:
        _memory_transition_error(
            f"{source_label}转移摘要的显式回合范围格式非法。"
        )
    summary_body = value[explicit.end():].strip() if explicit else value
    summary_body_casefold = summary_body.casefold()
    if not summary_body or summary_body_casefold in _MEMORY_EMPTY_MARKERS_CASEFOLD:
        _memory_transition_error(
            f"{source_label}转移摘要为空或为占位值。"
        )
    if "xxxxxxxxx" in summary_body_casefold:
        _memory_transition_error(
            f"{source_label}转移摘要包含占位内容。"
        )
    if explicit:
        actual = (
            int(explicit.group(1)),
            int(explicit.group(2) or explicit.group(1)),
        )
        if actual != expected:
            _memory_transition_error(
                f"{source_label}转移摘要范围 "
                f"{actual[0]}-{actual[1]} 与源条目范围 "
                f"{expected[0]}-{expected[1]} 不一致。"
            )
    return value


def _memory_delta_text(memory_deltas, field_name):
    value = memory_deltas.get(field_name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        _memory_transition_error(
            f"{field_name}必须是字符串，实际为{type(value).__name__}。"
        )
    return value.strip()


def validate_memory_transition_preflight(
    current_round, memory_deltas, memory_file=None
):
    """
    只读校验本回合记忆层转移，成功返回诊断信息，失败抛异常。
    不写入记忆库，不修改 memory_deltas，也不触发其他引擎。
    """
    if memory_file is None:
        memory_file = MEMORY_FILE
    if not os.path.exists(memory_file):
        _memory_transition_error(
            f"找不到记忆库文件：{memory_file}"
        )
    if memory_deltas is None:
        memory_deltas = {}
    if not isinstance(memory_deltas, dict):
        _memory_transition_error(
            f"memory_deltas必须是字典，实际为{type(memory_deltas).__name__}。"
        )

    with open(memory_file, "r", encoding="utf-8") as handle:
        content = handle.read()
    layers = _parse_memory_layer_items(content)

    for label, _prefix, cap in _MEMORY_LAYER_PREFIXES:
        if cap is not None and len(layers[label]) > cap:
            _memory_transition_error(
                f"{label}已有{len(layers[label])}条，超过容量{cap}。"
            )

    primary_round = _memory_delta_text(memory_deltas, "l1_new_round")
    legacy_round = _memory_delta_text(memory_deltas, "new_round_detail")
    if primary_round and legacy_round and primary_round != legacy_round:
        _memory_transition_error(
            "l1_new_round与new_round_detail同时存在且内容冲突。"
        )
    new_round = primary_round or legacy_round

    l1_summary = _memory_delta_text(
        memory_deltas, "l1_to_l2_condensed"
    )
    l2_summary = _memory_delta_text(
        memory_deltas, "l2_to_l3_summary"
    )
    l3_summary = _memory_delta_text(
        memory_deltas, "l3_to_l4_summary"
    )

    l1_items = layers["L1"]
    l2_items = layers["L2"]
    l3_items = layers["L3"]
    round_prefix = f"【{current_round}】"
    same_round_indices = [
        index for index, item in enumerate(l1_items)
        if item.startswith(round_prefix)
    ]
    if len(same_round_indices) > 1:
        _memory_transition_error(
            f"L1存在重复的当前回合条目：{round_prefix}。"
        )
    same_round_index = (
        same_round_indices[0] if same_round_indices else None
    )
    adds_l1 = bool(new_round) and same_round_index is None

    l1_transfer = bool(l1_summary)
    if l1_transfer:
        if not adds_l1 or len(l1_items) != 3:
            _memory_transition_error(
                "提交L1→L2摘要时，本回合没有产生合法的L1新增转移。"
            )
        l1_summary = _validate_memory_summary(
            l1_summary, l1_items[:1], "L1"
        )
    elif adds_l1 and len(l1_items) == 3:
        _memory_transition_error(
            "本回合新增L1将使第一层超过3条，但缺少l1_to_l2_condensed。"
        )

    l2_transfer = bool(l2_summary)
    if l2_transfer:
        if len(l2_items) != 10:
            _memory_transition_error(
                f"提交L2→L3摘要时，L2有{len(l2_items)}条，必须为10条。"
            )
        l2_summary = _validate_memory_summary(
            l2_summary, l2_items, "L2"
        )

    l3_transfer = bool(l3_summary)
    if l3_transfer:
        if len(l3_items) != 10:
            _memory_transition_error(
                f"提交L3→L4摘要时，L3有{len(l3_items)}条，必须为10条。"
            )
        l3_summary = _validate_memory_summary(
            l3_summary, l3_items, "L3"
        )

    staged_l1 = list(l1_items)
    staged_l2 = list(l2_items)
    staged_l3 = list(l3_items)

    if l3_transfer:
        staged_l3 = []
    if l2_transfer:
        staged_l2 = []
        staged_l3.append(l2_summary)
    if l1_transfer:
        staged_l1.pop(0)
        staged_l2.append(l1_summary)

    if l1_transfer and len(staged_l2) > 10:
        _memory_transition_error(
            f"模拟L1→L2后第二层将有{len(staged_l2)}条，"
            "但缺少l2_to_l3_summary。"
        )
    if l2_transfer and len(staged_l3) > 10:
        _memory_transition_error(
            f"模拟L2→L3后第三层将有{len(staged_l3)}条，"
            "但缺少l3_to_l4_summary。"
        )

    if new_round:
        if same_round_index is None:
            staged_l1.append(f"【{current_round}】{new_round}")
        else:
            staged_l1[same_round_index] = (
                f"【{current_round}】{new_round}"
            )

    if len(staged_l1) > 3:
        _memory_transition_error(
            f"模拟写入后L1将有{len(staged_l1)}条，未完成合法转移。"
        )
    if len(staged_l2) > 10:
        _memory_transition_error(
            f"模拟写入后L2将有{len(staged_l2)}条，未完成合法转移。"
        )
    if len(staged_l3) > 10:
        _memory_transition_error(
            f"模拟写入后L3将有{len(staged_l3)}条，未完成合法转移。"
        )

    return {
        "l1_count": len(l1_items),
        "l2_count": len(l2_items),
        "l3_count": len(l3_items),
        "l4_count": len(layers["L4"]),
        "adds_l1": adds_l1,
        "same_round_overwrite": (
            same_round_index is not None and bool(new_round)
        ),
        "l1_transfer": l1_transfer,
        "l2_transfer": l2_transfer,
        "l3_transfer": l3_transfer,
        "staged_l1_count": len(staged_l1),
        "staged_l2_count": len(staged_l2),
        "staged_l3_count": len(staged_l3),
    }
def update_global_memory(current_round, memory_deltas, panel_changes):
    """
    混合异步记忆引擎
    接管了所有的物理切片与移动，彻底解放AI前台的重复复读。
    """
    validate_memory_transition_preflight(current_round, memory_deltas)

    if not os.path.exists(MEMORY_FILE):
        return


    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 更新面板数值 (历史快照备份)
    if panel_changes:
        # Step 1: Extract latest stats and update them
        match = re.search(r"(▶ 当前最新数值\n)(.*?)(\n+(?:【当前激活微状态】|={10,}))", content, re.DOTALL)
        if match:
            latest_stats = match.group(2)
            new_latest_stats = latest_stats
            for char, changes in panel_changes.items():
                for key, value in changes.items():
                    pattern = rf"(\[{re.escape(char)}\].*?{re.escape(key)}\s*)(-?\d+|False|True|Lv\.\d+|\d+%)"
                    new_latest_stats = re.sub(pattern, rf"\g<1>{value}", new_latest_stats)
            
            # Update the latest stats block
            content = content[:match.start(2)] + new_latest_stats + content[match.end(2):]
            
            # Step 2: Push the old latest stats down to history snapshot EXACTLY ONCE
            # Find the history block and overwrite ONLY the stats part
            hist_match = re.search(r"(▶ 上回合历史快照[^\n]*\n)(.*?)(\n+(?:={10,}|【当前持久化状态与BUFF】))", content, re.DOTALL)
            if hist_match:
                content = content[:hist_match.start(2)] + latest_stats + content[hist_match.end(2):]

    # 2. 混合异步记忆引擎处理
    if not memory_deltas:
        memory_deltas = {}
        
    l1_start = content.find("▲ 第一层：")
    l2_start = content.find("▲ 第二层：")
    l3_start = content.find("▲ 第三层：")
    l4_start = content.find("▲ 第四层：")
    
    l1_text = content[l1_start:l2_start] if l1_start != -1 and l2_start != -1 else ""
    l2_text = content[l2_start:l3_start] if l2_start != -1 and l3_start != -1 else ""
    l3_text = content[l3_start:l4_start] if l3_start != -1 and l4_start != -1 else ""
    l4_text = content[l4_start:] if l4_start != -1 else ""

    def extract_items(layer_text):
        items = re.findall(r"(【\d+(?:-\d+)?】[^\n]*(?:\n(?!(?:【\d|▲)).*)*)", layer_text)
        # 过滤掉模板中的范例内容
        return [item.strip() for item in items if "xxxxxxxxx" not in item]
        
    l1_items = extract_items(l1_text)
    l2_items = extract_items(l2_text)
    l3_items = extract_items(l3_text)
    l4_items = extract_items(l4_text)

    # A. 触发式宏观总结打包
    l3_summary = memory_deltas.get("l3_to_l4_summary", "").strip()
    if l3_summary:
        if l3_items and not l3_summary.startswith("【"):
            match_start = re.search(r"【(\d+)", l3_items[0])
            match_end = re.search(r"-(\d+)】", l3_items[-1])
            if not match_end:
                match_end = re.search(r"【(\d+)】", l3_items[-1])
            if match_start and match_end:
                l3_summary = f"【{match_start.group(1)}-{match_end.group(1)}】{l3_summary}"
        l3_items = [] # 清空
        l4_items.append(l3_summary)
        print(" 📦 [记忆引擎] 触发【深渊纪元浓缩】，已清空第三层，推入第四层！")
        
    l2_summary = memory_deltas.get("l2_to_l3_summary", "").strip()
    if l2_summary:
        if l2_items and not l2_summary.startswith("【"):
            match_start = re.search(r"【(\d+)】", l2_items[0])
            match_end = re.search(r"【(\d+)】", l2_items[-1])
            if match_start and match_end:
                l2_summary = f"【{match_start.group(1)}-{match_end.group(1)}】{l2_summary}"
        l2_items = [] # 清空
        l3_items.append(l2_summary)
        print(" 📦 [记忆引擎] 触发【近期事实打包】，已清空第二层，推入第三层！")

    # B. L1 -> L2 手动降维 (由AI判断并提供精简文本)
    l1_to_l2 = memory_deltas.get("l1_to_l2_condensed", "").strip()
    if l1_to_l2:
        if len(l1_items) != 3:
            _memory_transition_error(
                f"L1转移前条目数异常：应为3，实际为{len(l1_items)}。"
            )
        prefix = ""
        match = re.search(r"^(【\d+】)", l1_items[0])
        if match:
            prefix = match.group(1)
        l1_items.pop(0) # 合法L1->L2转移，摘要已通过预检

        if prefix and not l1_to_l2.startswith("【"):
            l1_to_l2 = f"{prefix}{l1_to_l2}"

        l2_items.append(l1_to_l2)
        print(" 🔪 [记忆引擎] L1->L2 切片触发，已将AI提取的精简记录推入第二层！")

    # C. 增量写入第一层（自动剥离历史遗留的序幕隐藏标记，绝不滞留 L1）
    new_round = save_store.strip_prologue_marker(memory_deltas.get("l1_new_round", "").strip())
    if not new_round:
        new_round = save_store.strip_prologue_marker(memory_deltas.get("new_round_detail", "").strip()) # 兼容旧版Key
        
    is_overwrite = False
    if new_round:
        round_prefix = f"【{current_round}】"
        replaced = False
        for i in range(len(l1_items)):
            if l1_items[i].startswith(round_prefix):
                l1_items[i] = f"{round_prefix}{new_round}"
                replaced = True
                is_overwrite = True
                print(f" ⚠️ [防重叠机制] 检测到【第 {current_round} 回合】的存档已存在！已为您执行同回合覆盖更新。")
                break
        
        if not replaced:
            l1_items.append(f"{round_prefix}{new_round}")

    # 构造前硬检查：任何未合法转移的超容量都必须报错。
    for layer_name, items, capacity in (
        ("L1", l1_items, 3),
        ("L2", l2_items, 10),
        ("L3", l3_items, 10),
    ):
        if len(items) > capacity:
            _memory_transition_error(
                f"构造前{layer_name}有{len(items)}条，超过容量{capacity}。"
            )

    def build_layer(header, items, empty_msg="（空）"):
        res = header + "\n"
        if not items:
            res += empty_msg + "\n\n"
        else:
            res += "\n\n".join(items) + "\n\n"
        return res

    new_l1 = build_layer("▲ 第一层：【即时运存区】", l1_items)
    new_l2 = build_layer("▲ 第二层：【回想运存区】", l2_items)
    new_l3 = build_layer("▲ 第三层：【近期事实缓存区】", l3_items)
    new_l4 = build_layer("▲ 第四层：【深渊纪元浓缩区】", l4_items)

    new_tail = new_l1 + new_l2 + new_l3 + new_l4
    content = content[:l1_start] + new_tail
    
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    # 若 P3 记忆存储已存在，同步更新 memory_store.json（清除 prologue_active），同时保留本轮写入的 L1-L4 文本
    if os.path.exists(os.path.join(BASE_DIR, save_store.MEMORY_LAYERS_PATH)):
        try:
            st_obj, ly_obj, _ = save_store.load_bundle(BASE_DIR)
            ly_obj = save_store.set_layer_strings(
                ly_obj,
                {"L1": l1_items, "L2": l2_items, "L3": l3_items, "L4": l4_items},
                prologue_active=False if new_round else ly_obj.get("prologue_active", False),
            )
            if new_round and isinstance(ly_obj, dict) and 'episodes' in ly_obj:
                ly_obj = save_store.record_memory_turn(
                    ly_obj,
                    fact=new_round,
                    day=max(1, int(current_round or 1)),
                    location=str((st_obj.get('presence') or {}).get('徐志北', {}).get('location') or ''),
                    day_crossed=True,
                )
            st_obj['runtime']['last_closed'] = max(int(st_obj['runtime'].get('last_closed') or 0), int(current_round or 0))
            save_store.save_bundle(BASE_DIR, st_obj, ly_obj)
            # Only preserve legacy L1-L4 MEMORY_FILE verbatim when L2/L3/L4 legacy layers are populated
            if l2_items or l3_items or l4_items:
                with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                    f.write(content)
                st_obj.setdefault('rendered_sha256', {})['memory_txt'] = save_store._sha256_bytes(content.encode('utf-8'))
                save_store._atomic_write_bytes(os.path.join(BASE_DIR, save_store.SAVE_STATE_PATH), save_store._json_bytes(st_obj))
        except Exception:
            pass
        
    if is_overwrite:
        print(f" [√] 存档/全局记忆库.txt 异步引擎更新完成（回合 {current_round} - 本次为同回合覆盖更新）")
    else:
        print(f" [√] 存档/全局记忆库.txt 异步引擎更新完成（回合 {current_round}）")


# ============ 道具图鉴引擎（V3.0：save_store 单一真相 / 活跃·已部署·已交付·历史四区分离 / giftable） ============
ITEM_ANCHOR_DEPLOYED = "▼ 已部署装置区 ▼"
ITEM_ANCHOR_DELIVERED = "▼ 已交付道具区 ▼"
ITEM_ANCHOR_HISTORY = "▼ 已过期/已消耗道具历史区 ▼"
_ITEM_BLOCK_RE = re.compile(r"【道具名称】：(?P<name>[^\n]+)\n(?P<body>[\s\S]*?)(?=\n\n【道具名称】|\n\n(?:=+|▼)|\Z)")


def _active_item_zone(content):
    """活跃道具区 = 文件头部到已部署/已交付/历史区锚点之间（不含已部署、已交付与历史区）。"""
    stops = [
        idx for idx in (
            content.find(ITEM_ANCHOR_DEPLOYED),
            content.find(ITEM_ANCHOR_DELIVERED),
            content.find(ITEM_ANCHOR_HISTORY),
        ) if idx != -1
    ]
    return content[:min(stops)] if stops else content


def _find_item_block(content, name=None, item_id=None):
    """在活跃区按名称或 ID 定位条目块，返回 {start, end, block} 或 None。"""
    zone = _active_item_zone(content)
    for m in _ITEM_BLOCK_RE.finditer(zone):
        if name is not None and m.group("name").strip() == name:
            return {"start": m.start(), "end": m.end(), "block": m.group(0)}
        if item_id is not None:
            idm = re.search(r"【道具ID】：(ITEM-\d+)", m.group("body"))
            if idm and idm.group(1) == item_id:
                return {"start": m.start(), "end": m.end(), "block": m.group(0)}
    return None


def _parse_item_block(block):
    """解析单条道具记录 → {字段: 值}。"""
    item = {}
    for key in ("道具ID", "类型", "使用模式", "描述", "数量", "获得回合", "当前状态", "位置",
                "安装点位", "隐蔽部署", "部署时间", "使用对象", "时效", "剩余时效", "过期规则",
                "使用记录", "备注", "系统效果", "可赠予"):
        m = re.search(rf"【{key}】：([^\n]*)", block)
        item[key] = m.group(1).strip() if m else ""
    return item


def _int_of(raw, default=1):
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _next_item_id(content):
    ids = re.findall(r"【道具ID】：ITEM-(\d+)", content)
    nums = [int(x) for x in ids]
    return f"ITEM-{max(nums) + 1 if nums else 1:03d}"


def _normalize_item(item, current_round):
    """将传入条目规整为完整记录字段；desc/remark 空行归一；remaining 缺省取时效。"""
    item_name = str(item.get('name', '未命名道具')).strip() or '未命名道具'
    duration_raw = str(item.get('duration', '无')).strip()
    turns = _int_of(duration_raw, 0)
    has_timer = "临时性" in str(item.get('type', '')) and turns > 0
    remaining = str(item.get('remaining', '')).strip()
    if not remaining or remaining in ("无", "后台接管", "交由记忆库后台接管倒计时"):
        remaining = str(turns) + "回合" if has_timer else "无"

    def flat(v):
        return str(v).replace("\n", " ").replace("\r", " ").strip()

    sys_eff = flat(item.get('system_effect', ''))
    gift_raw = item.get('giftable')
    if type(gift_raw) is bool:
        giftable = gift_raw
    elif isinstance(gift_raw, str) and gift_raw.strip():
        giftable = gift_raw.strip() not in ('否', 'false', 'False', '0', '不可赠予')
    else:
        giftable = not bool(sys_eff)
    usage_mode = save_store.infer_usage_mode(sys_eff, giftable, item.get('usage_mode', ''))

    return {
        "id": str(item.get('id', '')).strip(),
        "name": item_name,
        "type": str(item.get('type', '临时性（消耗品）')).strip() or '临时性（消耗品）',
        "category": flat(item.get('category', '')),
        "usage_mode": usage_mode,
        "desc": flat(item.get('desc', '')),
        "quantity": max(1, _int_of(item.get('quantity', 1), 1)),
        "obtain_round": str(item.get('obtain_round', current_round)).strip(),
        "status": str(item.get('status', '仓库中')).strip() or '仓库中',
        "location": flat(item.get('location', '无')) or '无',
        "spot": flat(item.get('spot', '')),
        "hidden": bool(item.get('hidden', True)),
        "installed_clock": flat(item.get('installed_clock', '')),
        "target": flat(item.get('target', '未使用')) or '未使用',
        "duration": duration_raw or '无',
        "remaining": remaining,
        "remaining_turns": turns if has_timer else None,
        "expire_rule": flat(item.get('expire_rule', '时效归零后立即完全失效')) or '时效归零后立即完全失效',
        "usage_record": flat(item.get('usage_record', f'回合{current_round} - 已记录')) or f'回合{current_round} - 已记录',
        "remark": flat(item.get('remark', '')),
        "system_effect": sys_eff,
        "giftable": giftable,
        "_timer": has_timer,
        "_turns": turns if has_timer else 0,
    }


def _item_from_parsed(old, name=""):
    """将 _parse_item_block 的中文键解析结果映射为 _record_text 所需英文键。"""
    sys_eff = old.get("系统效果", "")
    gift_raw = old.get("可赠予", "")
    giftable = (gift_raw not in ("否", "false", "False", "0")) if gift_raw else (not bool(sys_eff))
    rem_str = old.get("剩余时效", "")
    rm = re.match(r"^(\d+)\s*回合$", rem_str)
    return {
        "name": name or old.get("道具名称", "") or "",
        "id": old.get("道具ID", ""),
        "type": old.get("类型", ""),
        "usage_mode": save_store.infer_usage_mode(sys_eff, giftable, old.get("使用模式", "")),
        "desc": old.get("描述", ""),
        "quantity": _int_of(old.get("数量"), 1),
        "obtain_round": old.get("获得回合", ""),
        "status": old.get("当前状态", ""),
        "location": old.get("位置", ""),
        "spot": old.get("安装点位", ""),
        "hidden": old.get("隐蔽部署", "是") not in ("否", "false", "False", "0"),
        "installed_clock": old.get("部署时间", ""),
        "target": old.get("使用对象", ""),
        "duration": old.get("时效", ""),
        "remaining": rem_str,
        "remaining_turns": int(rm.group(1)) if rm else None,
        "expire_rule": old.get("过期规则", ""),
        "usage_record": old.get("使用记录", ""),
        "remark": old.get("备注", ""),
        "system_effect": sys_eff,
        "giftable": giftable,
    }


def _record_text(item):
    giftable = item.get("giftable")
    if type(giftable) is not bool:
        giftable = not bool(item.get("system_effect", ""))
    usage_mode = save_store.infer_usage_mode(item.get("system_effect", ""), giftable, item.get("usage_mode", ""))
    record = f"""【道具名称】：{item['name']}
【道具ID】：{item['id']}
【类型】：{item['type']}
【使用模式】：{usage_mode}
【描述】：{item['desc']}
【数量】：{item['quantity']}
【获得回合】：{item['obtain_round']}
【当前状态】：{item['status']}
【位置】：{item['location']}
【使用对象】：{item['target']}
【时效】：{item['duration']}
【剩余时效】：{item['remaining']}
【过期规则】：{item['expire_rule']}
【使用记录】：{item['usage_record']}
【备注】：{item['remark']}
【系统效果】：{item.get('system_effect', '')}
【可赠予】：{'是' if giftable else '否'}"""
    return record.strip()


def _archive_item(content, target, item, new_status, usage_record, current_round):
    """兼容旧调用：从活跃区移除条目，写入历史区。"""
    old = _parse_item_block(target["block"])
    merged = old.get("使用记录", "")
    if merged and usage_record not in merged:
        merged = f"{merged} / {usage_record}"
    elif not merged:
        merged = usage_record
    item["status"] = new_status
    item["usage_record"] = merged
    item["obtain_round"] = old.get("获得回合") or item.get("obtain_round", current_round)
    record = _record_text(item)
    content = content[:target["start"]] + content[target["end"]:]
    m = re.search(r"(▼\s*已过期/已消耗道具历史区[^\n]*\n=+\n)([\s\S]*?)(?=\n=+\n▼\s*格式模板区|\Z)", content)
    if not m:
        raise RuntimeError("道具引擎：找不到历史区内容锚点！归档失败（已中止注入）。")
    head, body = m.group(1), m.group(2)
    cleaned = body.strip().replace("（当前为空）", "").strip()
    new_body = record + "\n\n" + (cleaned + "\n\n" if cleaned else "")
    return content[:m.start()] + head + "\n" + new_body + content[m.end():]


def _sync_item_timers(memory_file, pending_add, pending_remove):
    """同步记忆库【道具倒计时】区块（P2 下由 save_store 渲染统一维护；保留兼容直接调用）。"""
    if not pending_add and not pending_remove:
        return
    if not os.path.exists(memory_file):
        return
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = "【道具倒计时】"
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        insert_pos = next((content.find(k) for k in ("【商城与回响状态】", "【商业情报与杠杆状态】", "【世界导演状态】", "【回合生命周期】", "▲ 第一层：") if content.find(k) != -1), -1)
        if insert_pos == -1:
            return
        content = content[:insert_pos] + anchor + "\n（空）\n\n" + content[insert_pos:]
        m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【|\n▲ 第一层：|\Z)", content, re.DOTALL)
        if not m:
            return
    block = m.group(1)
    lines = [ln.strip() for ln in block.split("\n")[1:] if ln.strip() and ln.strip() != "（空）"]
    keep = []
    for ln in lines:
        idm = re.match(r"^(ITEM-\d+)：", ln)
        if idm and idm.group(1) in pending_remove:
            continue
        keep.append(ln)
    exist_ids = {re.match(r"^(ITEM-\d+)：", ln).group(1) for ln in keep if re.match(r"^(ITEM-\d+)：", ln)}
    for item_id, turns, name in pending_add:
        if item_id and item_id not in exist_ids:
            keep.append(f"{item_id}：{turns}回合 | 名称：{name} | 状态：进行中")
    if not keep:
        keep = ["（空）"]
    new_block = anchor + "\n" + "\n".join(keep) + "\n"
    content = content[:m.start(1)] + new_block + content[m.end(1):]
    with open(memory_file, "w", encoding="utf-8") as f:
        f.write(content)


def _merge_usage(old_usage, addition):
    old_u = str(old_usage or "").strip()
    if not old_u or old_u == "无":
        return addition
    if addition in old_u:
        return old_u
    return f"{old_u} / {addition}"


def update_item_catalog(current_round, new_item_entries):
    """
    道具图鉴引擎（V3.0）：以 save_store 为唯一真相，严格隔离活跃区/已部署区/已交付区/历史区；
    - add 仅堆叠活跃区「仓库中」同名条目，绝不覆盖已交付赠礼或已部署装置；
    - update 局部合并，严格保留未传的描述/备注/系统效果/使用记录/可赠予/使用模式字段；
    - 同步单向渲染徐志北道具图鉴.txt 与全局记忆库.txt【道具倒计时】。
    """
    if not new_item_entries:
        return {}
    if not os.path.exists(ITEM_FILE) and not os.path.exists(os.path.join(BASE_DIR, save_store.SAVE_STATE_PATH)):
        return {}
    if os.path.exists(ITEM_FILE):
        with open(ITEM_FILE, "r", encoding="utf-8") as f:
            raw_item_txt = f.read()
        if ITEM_ANCHOR_HISTORY not in raw_item_txt:
            raise RuntimeError("道具引擎：找不到历史区锚点！写入失败（已中止注入并触发全局回滚）。")

    state, layers, _ = save_store.load_bundle(BASE_DIR)
    items_box = state["items"]
    active = items_box["active"]
    history = items_box["history"]
    summary = {"added": [], "updated": [], "consumed": [], "archived": []}

    def _find_active_idx(item_name=None, item_id="", *, only_in_storage=False):
        if item_id:
            for idx, it in enumerate(active):
                if it.get("id") == item_id:
                    return idx
            return None
        for idx, it in enumerate(active):
            if it.get("name") == item_name:
                if only_in_storage and it.get("status") != "仓库中":
                    continue
                return idx
        return None

    def _alloc_id(explicit_id):
        if explicit_id and re.fullmatch(r"ITEM-\d+", explicit_id):
            num = int(explicit_id.split("-")[1])
            items_box["next_seq"] = max(int(items_box.get("next_seq", 1)), num + 1)
            return explicit_id
        seq = int(items_box.get("next_seq", 1))
        existing_nums = [
            int(it["id"].split("-")[1])
            for bucket in (
                items_box["active"],
                items_box.get("deployed", []),
                items_box["delivered"],
                items_box["history"],
            )
            for it in bucket
            if re.fullmatch(r"ITEM-\d+", str(it.get("id") or ""))
        ]
        seq = max(seq, (max(existing_nums) + 1) if existing_nums else 1)
        items_box["next_seq"] = seq + 1
        return f"ITEM-{seq:03d}"

    for item in new_item_entries:
        item_name = str(item.get("name", "未命名道具")).strip() or "未命名道具"
        action = str(item.get("action", "add")).strip() or "add"
        item_id = str(item.get("id", "")).strip()
        norm = _normalize_item(item, current_round)

        if action == "consume":
            idx = _find_active_idx(item_name=item_name, item_id=item_id)
            if idx is None:
                print(f" [道具引擎] 消耗失败：活跃区找不到道具「{item_name}」（ID：{item_id or '无'}）")
                continue
            cur = active[idx]
            new_q = int(cur.get("quantity", 1)) - norm["quantity"]
            if new_q <= 0:
                cur = copy.deepcopy(active.pop(idx))
                cur["status"] = "已消耗"
                cur["remaining_turns"] = None
                cur["remaining"] = "无"
                cur["usage_record"] = _merge_usage(cur.get("usage_record"), f"回合{current_round} - 消耗")
                history.insert(0, cur)
                summary["consumed"].append(item_name)
            else:
                cur["quantity"] = new_q
                cur["usage_record"] = _merge_usage(cur.get("usage_record"), f"回合{current_round} - 消耗{norm['quantity']}份")
                summary["updated"].append(item_name)
            continue

        if action == "archive":
            idx = _find_active_idx(item_name=item_name, item_id=item_id)
            if idx is None:
                print(f" [道具引擎] 归档失败：活跃区找不到道具「{item_name}」（ID：{item_id or '无'}）")
                continue
            cur = copy.deepcopy(active.pop(idx))
            cur["status"] = "已归档"
            cur["remaining_turns"] = None
            cur["remaining"] = "无"
            cur["usage_record"] = _merge_usage(cur.get("usage_record"), f"回合{current_round} - 手动归档")
            history.insert(0, cur)
            summary["archived"].append(item_name)
            continue

        if action == "update":
            idx = _find_active_idx(item_name=item_name, item_id=item_id)
            if idx is not None:
                cur = active[idx]
                # 局部合并：仅覆盖调用方显式传入的字段，绝不抹除原有描述/备注/系统效果/使用记录
                explicit_map = {
                    "type": "type", "desc": "desc", "status": "status", "location": "location",
                    "target": "target", "duration": "duration", "remaining": "remaining",
                    "expire_rule": "expire_rule", "usage_record": "usage_record",
                    "remark": "remark", "system_effect": "system_effect", "giftable": "giftable",
                }
                for raw_k, dst_k in explicit_map.items():
                    if raw_k in item and item[raw_k] not in (None, ""):
                        cur[dst_k] = norm[dst_k]
                if "quantity" in item and item["quantity"] is not None:
                    cur["quantity"] = norm["quantity"]
                if "duration" in item and norm["_timer"]:
                    cur["remaining_turns"] = norm["_turns"]
                    cur["remaining"] = f"{norm['_turns']}回合"
                active[idx] = save_store.normalize_item_dict(cur)
                summary["updated"].append(item_name)
                print(f" 🎒 [道具引擎] 已局部更新道具：{item_name}（{cur['id']}）")
                continue

        # action == 'add'（或 update 未命中时退化新增）：仅堆叠活跃区「仓库中」同名条目，绝不覆盖已交付道具
        idx = _find_active_idx(item_name=item_name, item_id=item_id, only_in_storage=(action == "add" and not item_id))
        if idx is not None:
            cur = active[idx]
            cur["quantity"] = int(cur.get("quantity", 1)) + norm["quantity"]
            if norm["_timer"] and cur.get("remaining_turns") is None:
                cur["remaining_turns"] = norm["_turns"]
                cur["remaining"] = f"{norm['_turns']}回合"
            active[idx] = save_store.normalize_item_dict(cur)
            summary["updated"].append(item_name)
            print(f" 🎒 [道具引擎] 已堆叠仓库道具：{item_name}（{cur['id']}，数量 {cur['quantity']}）")
        else:
            new_id = _alloc_id(item_id)
            rec = save_store.normalize_item_dict({
                **{k: v for k, v in norm.items() if not k.startswith("_")},
                "id": new_id,
                "remaining_turns": norm["_turns"] if norm["_timer"] else None,
            })
            active.append(rec)
            summary["added"].append(item_name)
            print(f" 🎁 [道具引擎] 已新增道具条目：{item_name}（{new_id}，数量 {rec['quantity']}）")

    save_store.save_bundle(BASE_DIR, state, layers)
    return summary


def process_item_timers(memory_file, item_file, current_round):
    """
    道具倒计时结算（V3.0）：统一从 save_store.items.active 递减 remaining_turns；
    归零道具自动移入 items.history（status='已过期'），并同步渲染两份可读视图。
    """
    if not os.path.exists(memory_file) and not os.path.exists(item_file):
        return {}
    stage_root = os.path.dirname(os.path.dirname(os.path.abspath(memory_file)))
    state, layers, _ = save_store.load_bundle(stage_root)
    active = state["items"]["active"]
    history = state["items"]["history"]
    expired = []
    kept = []
    changed = False
    for it in active:
        rem = it.get("remaining_turns")
        if rem is None:
            kept.append(it)
            continue
        changed = True
        rem = int(rem) - 1
        if rem <= 0:
            expired_item = copy.deepcopy(it)
            expired_item["status"] = "已过期"
            expired_item["remaining_turns"] = None
            expired_item["remaining"] = "无"
            expired_item["usage_record"] = _merge_usage(
                expired_item.get("usage_record"),
                f"回合{current_round} - 时效耗尽自动归档",
            )
            history.insert(0, expired_item)
            expired.append(it["name"])
            print(f" ⌛ [道具引擎] {it['name']}（{it['id']}）时效归零，自动失效归档。")
        else:
            it["remaining_turns"] = rem
            it["remaining"] = f"{rem}回合"
            kept.append(it)
    state["items"]["active"] = kept
    if changed:
        save_store.save_bundle(stage_root, state, layers)
    return {"expired": expired}


def update_npc_roster(current_round, new_npc_entries):
    """兼容保留空操作：次要NPC名册已移除，配角线头统一由四层记忆与活体世界导演承载。"""
    return None


# 【ENI 改造：绝对路径日志生成器】
# SYSTEM_LOG 方案A：强制模板节名（与常驻主规则一致）
_SYSLOG_REQUIRED_HEADERS = (
    "【SYSTEM_LOG】",
    "【应查】",
    "【实查】",
    "【豁免】",
    "【V1验收】",
    "【事件打标】",
    "【记忆/所在】",
)

# 最小键集适配世界书迁移——narrative.pace 已迁世界书，最小从四键降为三键
# 每回 must_keys 不可豁免、且必须出现在 must 与 query 中
_SYSLOG_MIN_MUST_KEYS = frozenset({
    "state.memory",
    "contract.inject",
    "gate.V1",
})

# 禁止写入 skip 的 key（红线）
_SYSLOG_NO_SKIP_KEYS = _SYSLOG_MIN_MUST_KEYS


def _parse_syslog_key_line(system_log, field_name):
    """
    从 SYSTEM_LOG 中解析 must_keys: / query_keys: 行。
    支持半角/全角冒号；值为逗号或中文逗号/空白分隔的 key 列表。
    """
    if not system_log:
        return None
    # 匹配 field_name: k1, k2 或 field_name：k1，k2
    pat = re.compile(
        rf"(?m)^\s*{re.escape(field_name)}\s*[:：]\s*(.*?)\s*$"
    )
    m = pat.search(system_log)
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw or raw in ("...", "…", "无", "none", "None"):
        return set()
    # 去掉可能的括号包裹
    raw = raw.strip("[]（）()")
    parts = re.split(r"[,，;；\s]+", raw)
    keys = set()
    for p in parts:
        k = p.strip().strip("`\"'")
        # 去除世界书 [世] 后缀，确保 must_keys ⊆ query_keys 字符串比较一致
        if k.endswith("[世]") or k.endswith("[世"):
            k = k[:-3] if k.endswith("[世]") else k.rstrip("[世")
        if k:
            keys.add(k)
    return keys


def _parse_syslog_skip_keys(system_log):
    """
    解析【豁免】节中的 skip 行。
    合法：skip: 无
    或：skip: key=理由, key2=理由
    返回被声明豁免的 key 集合（不含「无」）。
    """
    if not system_log:
        return set()
    m = re.search(r"(?m)^\s*skip\s*[:：]\s*(.+?)\s*$", system_log)
    if not m:
        return set()
    raw = m.group(1).strip()
    if raw in ("无", "none", "None", "...", "…", ""):
        return set()
    skipped = set()
    for part in re.split(r"[,，;；]+", raw):
        part = part.strip()
        if not part:
            continue
        # key=理由 或 仅 key
        if "=" in part:
            k = part.split("=", 1)[0].strip()
        elif "：" in part:
            k = part.split("：", 1)[0].strip()
        elif ":" in part:
            k = part.split(":", 1)[0].strip()
        else:
            k = part
        k = k.strip().strip("`\"'")
        if k and k not in ("无",):
            skipped.add(k)
    return skipped


class SystemLogValidationError(ValueError):
    """SYSTEM_LOG 方案A校验失败，应中止注入且不污染存档。"""
    pass


def validate_system_log_scheme_a(system_log):
    """
    方案A：校验常驻主规则强制 SYSTEM_LOG 模板。
    - 必要标题节存在
    - must_keys / query_keys 可解析且 query 非空
    - 最小三键 ⊆ must_keys ⊆ query_keys
    - 最小三键不得出现在 skip 豁免中
    成功返回 {"must_keys": set, "query_keys": set}
    失败 raise SystemLogValidationError
    """
    errors = []
    text = system_log if isinstance(system_log, str) else ""

    if not text.strip():
        raise SystemLogValidationError(
            "[SYSTEM_LOG] FAIL: system_log 为空（强制模板缺失）"
        )

    for h in _SYSLOG_REQUIRED_HEADERS:
        if h not in text:
            errors.append(f"缺节 {h}")

    must_keys = _parse_syslog_key_line(text, "must_keys")
    query_keys = _parse_syslog_key_line(text, "query_keys")

    if must_keys is None:
        errors.append("无法解析 must_keys: 行（【应查】）")
        must_keys = set()
    if query_keys is None:
        errors.append("无法解析 query_keys: 行（【实查】）")
        query_keys = set()

    if not query_keys:
        errors.append("query_keys 为空（禁止空实查）")

    missing_min_in_must = _SYSLOG_MIN_MUST_KEYS - must_keys
    if missing_min_in_must:
        errors.append(
            "must_keys 缺少最小三键: " + ", ".join(sorted(missing_min_in_must))
        )

    missing_in_query = must_keys - query_keys
    if missing_in_query:
        errors.append(
            "query_keys 未覆盖 must_keys: " + ", ".join(sorted(missing_in_query))
        )

    skipped = _parse_syslog_skip_keys(text)
    bad_skip = skipped & _SYSLOG_NO_SKIP_KEYS
    if bad_skip:
        errors.append(
            "禁止豁免红线 key: " + ", ".join(sorted(bad_skip))
        )

    # 仅校验明确、唯一的通过声明；语义是否正确仍需独立复核。
    for label in ("V1-A", "V1-B", "V1-C", "V1-D"):
        rows = re.findall(rf"(?m)^\s*{label}\s*[:：]\s*(.*)$", text)
        if len(rows) != 1 or not re.fullmatch(r"通过\s*[—–-]\s*\S.*", rows[0]):
            errors.append(f"【V1验收】{label}须唯一且为通过 — 具体依据")

    if errors:
        msg = "[SYSTEM_LOG] FAIL: " + " | ".join(errors)
        raise SystemLogValidationError(msg)

    print(
        f" [√] SYSTEM_LOG 方案A通过：must={len(must_keys)} query={len(query_keys)} "
        f"keys={', '.join(sorted(query_keys)[:12])}"
        + ("…" if len(query_keys) > 12 else "")
    )
    return {"must_keys": must_keys, "query_keys": query_keys}


def write_system_log(current_round, system_log):
    if not system_log: return
        
    log_dir = os.path.join(BASE_DIR, "日志")
        
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_filename = f"Round_{current_round}_推演日志_{timestamp}.txt"
    log_path = os.path.join(log_dir, log_filename)
    
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            f.write(f"【深渊天平引擎 - 回合 {current_round} 推演快照】\n")
            f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(system_log)
        print(f" [√] 战术推演日志已隐秘写入绝对路径: {log_path}")
    except Exception as e:
        raise OSError(f"日志写入失败: {e}") from e


_SCENE_STAMP_RE = re.compile(
    r"^\s*\[([^\[\]]+)\]\s*(.*)$",
    re.DOTALL,
)


_SCENE_OUTFIT_RE = re.compile(r"^\s*[\[【]\s*(居家|外出)\s*[\]】]\s*(.*)$", re.DOTALL)


def _split_scene_outfit_marker(text: str):
    """拆出 header 前缀服饰标记：[居家]/[外出]，返回 (marker, clean_text)。"""
    raw = (text or "").strip()
    m = _SCENE_OUTFIT_RE.match(raw)
    if not m:
        return "", raw
    return m.group(1).strip(), (m.group(2) or "").strip()


def _looks_like_scene_stamp(stamp: str) -> bool:
    """判断方括号内容是否为场景时间戳（而非普通中括号备注）。"""
    if not stamp:
        return False
    _marker, s = _split_scene_outfit_marker(stamp)
    s = s.strip()
    if re.search(r"月|日|周|星期|\d{1,2}\s*[:：点时]", s):
        return True
    if re.search(r"楼|室|厅|房|宅|园|公寓|别墅|画室|书房|餐厅|玄关|卧室|客厅|厨房|浴室", s):
        return True
    if ("," in s or "，" in s) and len(s) <= 40:
        return True
    return False


def _parse_scene_title_from_stamp(stamp: str) -> str:
    """从场景戳提炼顶栏短标题：地点 · 时间。"""
    _marker, clean_stamp = _split_scene_outfit_marker(stamp)
    core = (clean_stamp or "").strip().strip("[]")
    parts = [p.strip() for p in re.split(r"[,，、|/]", core) if p.strip()]
    place = ""
    time_bit = ""
    for p in parts:
        if re.search(r"[楼房厅室宅园廊厨卧浴车]|主宅|公寓|别墅|书房|餐厅|玄关|花园|客厅|卧室|画室", p):
            place = p
        if re.search(r"\d{1,2}\s*[:：点时]\s*\d{0,2}|清晨|黎明|上午|中午|午后|傍晚|黄昏|深夜|午夜|凌晨|夜晚|早上|晚上", p):
            time_bit = p.replace("：", ":")
    if not place and len(parts) >= 3:
        place = parts[-2]
    if not place:
        place = "徐宅"
    if not time_bit:
        for p in parts:
            if re.search(r"周|星期", p):
                time_bit = p
                break
    return f"{place} · {time_bit}" if time_bit else f"{place} · 此刻"


def _normalize_story_headers(story_nodes):
    """
    场景戳规范化：
    1) 已有 type=header → 保留（text 仅保留戳本体，去掉外层[]亦可）
    2) 旧格式 narration「[日期,周几,地点,时间] 正文」→ 拆成 header + narration
    3) 返回 (nodes, scene_title)
    """
    processed = []
    scene_title = "徐宅 · 此刻"
    for node in story_nodes or []:
        ntype = node.get("type")
        text = node.get("text") or ""

        if ntype == "header":
            stamp = text.strip()
            marker, marker_body = _split_scene_outfit_marker(stamp)
            body_for_match = marker_body if marker else stamp
            m = _SCENE_STAMP_RE.match(body_for_match)
            if m and _looks_like_scene_stamp(m.group(1)):
                clean_stamp = m.group(1).strip()
            else:
                clean_stamp = body_for_match.strip("[]").strip()
            stamp = f"[{marker}] {clean_stamp}" if marker else clean_stamp
            processed.append({"type": "header", "text": stamp})
            scene_title = _parse_scene_title_from_stamp(clean_stamp)
            continue

        if ntype == "narration":
            marker, marker_body = _split_scene_outfit_marker(text)
            text_for_match = marker_body if marker else text
            m = _SCENE_STAMP_RE.match(text_for_match)
            if m and _looks_like_scene_stamp(m.group(1)):
                clean_stamp = m.group(1).strip()
                stamp = f"[{marker}] {clean_stamp}" if marker else clean_stamp
                body = (m.group(2) or "").strip()
                processed.append({"type": "header", "text": stamp})
                scene_title = _parse_scene_title_from_stamp(clean_stamp)
                if body:
                    # 保留原节点其它键（一般没有），正文独立成旁白
                    body_node = {k: v for k, v in node.items() if k != "text"}
                    body_node["type"] = "narration"
                    body_node["text"] = body
                    processed.append(body_node)
                continue

        processed.append(node)
    return processed, scene_title


def _split_long_narrations(story_nodes, max_length=120):
    """仅拆「过载墙」。主旁白 80–110 应原样保留；默认硬拆线 120。"""
    processed_nodes = []
    for node in story_nodes:
        if node.get("type") == "narration" and len(node.get("text", "")) > max_length:
            text = node.get("text")
            if "【系统" in text or "深渊天平" in text:
                processed_nodes.append(node)
                continue
            sentences = re.split(r'(?<=[。！？…])', text)
            current_chunk = ""
            for sentence in sentences:
                if not sentence.strip(): continue
                if len(current_chunk) + len(sentence) > max_length and current_chunk:
                    processed_nodes.append({"type": "narration", "text": current_chunk.strip()})
                    current_chunk = sentence
                else:
                    current_chunk += sentence
            if current_chunk.strip():
                processed_nodes.append({"type": "narration", "text": current_chunk.strip()})
        else:
            processed_nodes.append(node)
    return processed_nodes


# 【ENI 改造：JSON 生成器升级，支持注入选项】
def generate_data_json(current_round, story_nodes, options_text="", presence=None):
    # 先规范化 header，再挂选项，保证场景戳不被长句切分打散
    story_nodes, scene_title = _normalize_story_headers(list(story_nodes or []))

    if options_text:
        # 【ENI补丁】剥离模板注释行（# 开头），防止「[X. badge]」示例被前端 regex 当成选项渲染成幽灵卡
        _clean_options = "\n".join(
            ln for ln in str(options_text).splitlines()
            if not ln.strip().startswith("#")
        ).strip()
        options_node = {
            "type": "narration",
            "text": f"【系统推演：当前可选行动】\n{_clean_options}"
        }
        story_nodes.append(options_node)

    if presence is None:
        presence = parse_presence_from_memory()

    game_state = {
        "round": current_round,
        "sceneTitle": scene_title,
        "storyNodes": story_nodes,
        "presence": presence,
    }
    output_path = DATA_JSON_FILE
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(game_state, f, ensure_ascii=False, indent=2)
    print(f" [√] data.json 已生成（场景标题: {scene_title} · 含人物所在）")


def _normalize_deterministic_events(state, events, *, current_day=None, active_cast=None, insomnia_targets=None):
    """后端确定性派生跨回合规则（小憩限次/失眠不叠加/首次首杀/同质化免疫），防止跨新窗失忆或重复刷奖。"""
    norm = copy.deepcopy(events) if isinstance(events, dict) else {}
    for g in ('shame_events', 'depravity_events', 'ds_events', 'affection_events', 'vigilance_events'):
        norm.setdefault(g, {})
    norm.setdefault('host_events', [])
    mech = state.setdefault('mechanics', save_store.default_mechanics())
    notes = []

    tag_c1 = _event_tag('SHAME_01')
    tag_c2 = _event_tag('SHAME_02')
    tag_c3 = _event_tag('SHAME_03')
    tag_c4 = _event_tag('SHAME_04')
    tag_cp_reg = _event_tag('SHAME_06')
    tag_cp_first = _event_tag('SHAME_07')
    tag_imm2 = _event_tag('SHAME_15')
    tag_imm3 = _event_tag('SHAME_16')
    tag_first = _event_tag('SHAME_17')
    tag_dep_first = _event_tag('DEPRAVITY_03')
    tag_host_first = _event_tag('HOST_04')
    tag_aff_first = _event_tag('AFFECTION_04')
    tag_aff_rep = _event_tag('AFFECTION_05')
    tag_ds_labor = _event_tag('DS_09')
    tag_ds_nap = _event_tag('DS_12')

    insomnia_set = set(insomnia_targets or ())
    cast_set = set(active_cast) if active_cast is not None else None
    any_first_creampie = False
    any_repeat_creampie = False

    def _dedup(seq):
        return list(dict.fromkeys(seq))

    for char in save_store.HEROINES:
        firsts = set(mech['first_triggers'].get(char) or [])
        s_tags = list(norm['shame_events'].get(char) or [])
        d_tags = list(norm['depravity_events'].get(char) or [])
        a_tags = list(norm['affection_events'].get(char) or [])
        ds_tags = list(norm['ds_events'].get(char) or [])

        # 1. 小憩单日最多1次
        if current_day and tag_ds_nap in ds_tags:
            if int(mech['nap_last_day'].get(char, 0) or 0) == int(current_day):
                ds_tags = [t for t in ds_tags if t != tag_ds_nap]
                notes.append(f'{char}:同日小憩上限拦截')
            else:
                mech['nap_last_day'][char] = int(current_day)

        # 2. 失眠不可叠加（同一夜只扣一次消耗_日常劳作）
        if char in insomnia_set and tag_ds_labor in ds_tags:
            if mech['insomnia_applied'].get(char, False):
                ds_tags = [t for t in ds_tags if t != tag_ds_labor]
                notes.append(f'{char}:同夜失眠不叠加拦截')
            else:
                mech['insomnia_applied'][char] = True

        # 3. 内射首次核爆 vs 常规（严格 per-save 一次性；首次自动派生 SHAME_07 + DEPRAVITY_03 + HOST_04）
        has_cp = (tag_cp_reg in s_tags) or (tag_cp_first in s_tags) or (tag_dep_first in d_tags)
        if has_cp:
            if '内射' not in firsts:
                s_tags = [tag_cp_first if t == tag_cp_reg else t for t in s_tags]
                if tag_cp_first not in s_tags:
                    s_tags.append(tag_cp_first)
                if tag_dep_first not in d_tags:
                    d_tags.append(tag_dep_first)
                firsts.add('内射')
                any_first_creampie = True
                notes.append(f'{char}:首次内射自动派生内射_首次核爆(羞耻+堕落+宿主)')
            else:
                any_repeat_creampie = True
                if tag_cp_first in s_tags:
                    s_tags = [tag_cp_reg if t == tag_cp_first else t for t in s_tags]
                    notes.append(f'{char}:已触发过内射首次核爆，降级为内射_常规')
                if tag_dep_first in d_tags:
                    d_tags = [t for t in d_tags if t != tag_dep_first]

        # 4. 深度操控首次 vs 重复
        if tag_aff_first in a_tags or tag_aff_rep in a_tags:
            if '深度操控' not in firsts:
                a_tags = [tag_aff_first if t == tag_aff_rep else t for t in a_tags]
                firsts.add('深度操控')
            else:
                if tag_aff_first in a_tags:
                    a_tags = [tag_aff_rep if t == tag_aff_first else t for t in a_tags]
                    notes.append(f'{char}:深度操控已非首次，自动转为深度操控_重复')

        # 5. C烈度首次修饰 + 同质化免疫（回合2 ×0.5 / 回合3 ×0）完全由后端自动派生
        s_tags = [t for t in s_tags if t not in (tag_first, tag_imm2, tag_imm3)]
        c_hit_first = False
        for ctag, ckey in ((tag_c2, 'C_中度'), (tag_c3, 'C_深度'), (tag_c4, 'C_重度')):
            if ctag in s_tags and ckey not in firsts:
                firsts.add(ckey)
                c_hit_first = True
        if c_hit_first:
            s_tags.append(tag_first)

        primary_tier = ''
        for ctag, ckey in ((tag_c4, 'C_重度'), (tag_c3, 'C_深度'), (tag_c2, 'C_中度'), (tag_c1, 'C_轻度')):
            if ctag in s_tags:
                primary_tier = ckey
                break
        streak = mech['c_streak'].setdefault(char, {'tier': '', 'count': 0})
        if primary_tier:
            if streak.get('tier') == primary_tier:
                streak['count'] = int(streak.get('count', 0)) + 1
            else:
                streak['tier'] = primary_tier
                streak['count'] = 1
            if streak['count'] == 2:
                s_tags.append(tag_imm2)
                notes.append(f'{char}:{primary_tier}连续第2轮自动触发同质化免疫×0.5')
            elif streak['count'] >= 3:
                s_tags.append(tag_imm3)
                notes.append(f'{char}:{primary_tier}连续第{streak["count"]}轮自动触发同质化免疫×0')
        elif cast_set is None or char in cast_set:
            streak['tier'] = ''
            streak['count'] = 0

        mech['first_triggers'][char] = sorted(firsts)
        if s_tags:
            norm['shame_events'][char] = _dedup(s_tags)
        elif char in norm['shame_events']:
            del norm['shame_events'][char]
        if d_tags:
            norm['depravity_events'][char] = _dedup(d_tags)
        elif char in norm['depravity_events']:
            del norm['depravity_events'][char]
        if a_tags:
            norm['affection_events'][char] = _dedup(a_tags)
        elif char in norm['affection_events']:
            del norm['affection_events'][char]
        if ds_tags:
            norm['ds_events'][char] = _dedup(ds_tags)
        elif char in norm['ds_events']:
            del norm['ds_events'][char]

    if any_first_creampie and tag_host_first not in norm['host_events']:
        norm['host_events'].append(tag_host_first)
    elif any_repeat_creampie and not any_first_creampie and tag_host_first in norm['host_events']:
        norm['host_events'] = [t for t in norm['host_events'] if t != tag_host_first]
        notes.append('系统宿主:已非首次内射，拦截重复侵蚀_首次核爆')

    return norm, notes


# 【ENI 改造：终极执行函数，接管 log 与 options】
def _execute_injection_internal(current_round, story_nodes, memory_deltas, panel_changes,
                      npc_entries=None, item_entries=None,
                      system_log="", options_text="", micro_state_changes=None,
                      shame_events=None, depravity_events=None, ds_events=None,
                      affection_events=None, host_events=None, presence_changes=None,
                  counter_updates=None, vigilance_events=None, task_issue=None):
    if npc_entries is None: npc_entries = []
    if item_entries is None: item_entries = []
    if micro_state_changes is None: micro_state_changes = {}
    if shame_events is None: shame_events = {}
    if depravity_events is None: depravity_events = {}
    if ds_events is None: ds_events = {}
    if affection_events is None: affection_events = {}
    if host_events is None: host_events = []
    if presence_changes is None: presence_changes = {}
    if counter_updates is None: counter_updates = {}
    if vigilance_events is None: vigilance_events = {}

    print("=" * 70)
    print(f" [引擎] 开始执行全本地一键注入（回合 {current_round}）")
    print("=" * 70)

    # 方案A：SYSTEM_LOG 强制模板校验（失败则整单中止，由外层回滚）
    validate_system_log_scheme_a(system_log)

    # 致命拦截：检查回合数是否重复
    # 例外：L1 仅有序幕锚点【1】（prologue_active 或旧隐藏标记）时，允许正式第1回合覆盖写入
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            check_content = f.read()
        l1_start = check_content.find("▲ 第一层：")
        l2_start = check_content.find("▲ 第二层：")
        l1_text = check_content[l1_start:l2_start] if l1_start != -1 and l2_start != -1 else ""
        l1_real_items = re.findall(r"【\d+】[^\n]*", l1_text)
        l1_real_items = [item for item in l1_real_items if "xxxxxxxxx" not in item and "范例" not in item]
        hit = [item for item in l1_real_items if item.startswith(f"【{current_round}】")]
        if hit:
            prologue_mark = "【系统隐藏标记：以上为新游戏序幕锚点，剧情从此刻正式开始计算】"
            _, ly_chk, _ = save_store.load_bundle(BASE_DIR)
            is_prologue_only = (
                current_round == 1
                and len(l1_real_items) == 1
                and (bool(ly_chk.get("prologue_active")) or prologue_mark in l1_text)
            )
            if is_prologue_only:
                print(" ⚠️ [序幕覆盖] 检测到仅有序幕锚点【1】，允许正式第1回合覆盖写入。")
            else:
                print(f"\n 🛑 [致命拦截] 引擎检测到【第 {current_round} 回合】的存档已存在！")
                raise ValueError("当前回合已存在，禁止重复结算")

    write_system_log(current_round, system_log)

    # 语义化规则包：后台引擎自动物理计算与覆写（内存流水线：堕落 -> 羞耻 -> 好感 -> 欲望体力高潮 -> 宿主）
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        _orig_mem_content = f.read()

    def _sync_pipeline_mem():
        if panel_changes:
            with open(MEMORY_FILE, "w", encoding="utf-8") as _wf:
                _wf.write(_simulate_panel(_orig_mem_content, panel_changes))

    _creampie_chars = set()
    if depravity_events:
        computed_dep = process_depravity_system(depravity_events, MEMORY_FILE)
        for char, new_val in computed_dep.items():
            panel_changes.setdefault(char, {})["堕落"] = new_val
        _sync_pipeline_mem()

    if shame_events:
        computed_pregnancy = process_pregnancy_rng(shame_events, MEMORY_FILE, ds_events=ds_events)
        for char, is_preg in computed_pregnancy.items():
            panel_changes.setdefault(char, {})["怀孕"] = is_preg
        # 补齐旧入口内射次数累加（与 apply_story_events 保持一致）
        creampie_tags = {_event_tag('SHAME_06'), _event_tag('SHAME_07')}
        for char, tags in shame_events.items():
            inc = sum(1 for t in (tags or []) if t in creampie_tags)
            if inc > 0:
                _creampie_chars.add(char)
                m_cnt = re.search(rf"\[{re.escape(char)}\].*?内射\s*(\d+)次", _orig_mem_content)
                cur_cnt = int(m_cnt.group(1)) if m_cnt else 0
                panel_changes.setdefault(char, {})["内射"] = cur_cnt + inc
        computed_shame = process_shame_system(shame_events, MEMORY_FILE)
        for char, new_val in computed_shame.items():
            panel_changes.setdefault(char, {})["羞耻"] = new_val
        _sync_pipeline_mem()

    if affection_events or shame_events:
        computed_aff = process_affection_system(affection_events, shame_events, MEMORY_FILE)
        for char, new_val in computed_aff.items():
            panel_changes.setdefault(char, {})["好感"] = new_val
        _sync_pipeline_mem()

    if ds_events:
        computed_ds = process_desire_stamina_system(ds_events, MEMORY_FILE, creampie_chars=_creampie_chars)
        for char, stats in computed_ds.items():
            panel_changes.setdefault(char, {})["欲望"] = stats["欲望"]
            panel_changes[char]["体力"] = stats["体力"]
            panel_changes[char]["高潮"] = stats["高潮"]
        _sync_pipeline_mem()

    # 宿主核心引擎：三轨竞标结算 + 商城扣费 + 体力代偿 + 肾上腺素
    _has_shame_adrenaline = bool(
        shame_events and any(
            _event_tag('SHAME_07') in (tags or ())
            for tags in shame_events.values()
            if isinstance(tags, (list, tuple, set))
        )
    )
    if host_events or _has_shame_adrenaline:
        host_result = process_host_system(host_events, shame_events, MEMORY_FILE)
        if host_result:
            panel_changes["系统宿主"] = host_result
            _sync_pipeline_mem()

    # 还原流水线前的 MEMORY_FILE 供 update_global_memory 推送真实「上回合历史快照」
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(_orig_mem_content)

    # 任务系统：判定完成 + 生成新任务（判定基准 = 本回合结算后的模拟面板，与面板显示一致；奖励独立叠加）
    sim_content = None
    if panel_changes:
        sim_content = _simulate_panel(_orig_mem_content, panel_changes)
    task_delta = process_task_system(task_issue, current_round, MEMORY_FILE, sim_content=sim_content)
    if task_delta:
        base = panel_changes.get("系统宿主")
        if not base:
            base = _read_host_panel(MEMORY_FILE) or {"积分": 0, "经验值": 0, "体力": 100, "商业嗅觉": 0}
        base["积分"] = base.get("积分", 0) + task_delta.get("积分", 0)
        base["经验值"] = base.get("经验值", 0) + task_delta.get("经验值", 0)
        panel_changes["系统宿主"] = base
        print(f" 📊 [任务系统] 宿主面板已并入任务奖励：积分+{task_delta.get('积分', 0)} 经验+{task_delta.get('经验值', 0)}")

    update_global_memory(current_round, memory_deltas, panel_changes)
    new_buffs_dict = memory_deltas.get("new_buffs", {}) if isinstance(memory_deltas, dict) else {}
    update_persistent_buffs(MEMORY_FILE, shame_events, new_buffs_dict)
    update_micro_states(micro_state_changes)
    update_counters(counter_updates)
    process_vigilance_system(vigilance_events, shame_events, MEMORY_FILE, ds_events=ds_events)
    if not presence_changes and isinstance(memory_deltas, dict):
        presence_changes = memory_deltas.get("presence") or memory_deltas.get("presence_changes") or {}
    update_presence(presence_changes if isinstance(presence_changes, dict) else {})
    update_item_catalog(current_round, item_entries)
    process_item_timers(MEMORY_FILE, ITEM_FILE, current_round)
    update_npc_roster(current_round, npc_entries)
    
    # 拆场景戳为 header；不再执行过时的 120 字硬切分（契约上限已为 4000 字）
    normalized_nodes, _scene_title = _normalize_story_headers(list(story_nodes or []))
    presence_snapshot = parse_presence_from_memory()
    generate_data_json(current_round, normalized_nodes, options_text, presence=presence_snapshot)

    print("=" * 70)
    print(" [完成] 本回合存档已全部更新，可以直接游玩！")
    print("=" * 70)


def apply_story_events(events, task_issue, memory_round, *, business_leverage=False,
                       current_day=None, active_cast=None, pre_event_content=None,
                       insomnia_targets=None, defer_task=False, privacy=None, body_acts=None,
                       action_category=None, effective_progress=False):
    """Settle accepted event tags with deterministic cross-window mechanics persistence (in-memory pipeline: depravity -> shame -> affection -> ds -> host)."""
    state, layers, _ = save_store.load_bundle(BASE_DIR)
    intl_now = state.get('intimate') or {}
    eff_privacy = str(privacy or intl_now.get('privacy') or 'open_public')
    host_charm = int(((state.get('panels') or {}).get('系统宿主') or {}).get('魅力', 70) or 70)
    body_dev_now = intl_now.get('body_dev') if isinstance(intl_now.get('body_dev'), dict) else {}
    hp_now = intl_now.get('host_phys') if isinstance(intl_now.get('host_phys'), dict) else {}
    host_desire_now = int(hp_now.get('desire', 0) or 0)
    host_vigor_now = int(hp_now.get('vigor', 100) if hp_now.get('vigor') is not None else 100)
    edging_streak_now = int(hp_now.get('edging_streak', 0) or 0)
    norm_events, mech_notes = _normalize_deterministic_events(
        state, events, current_day=current_day, active_cast=active_cast, insomnia_targets=insomnia_targets,
    )
    save_store.save_bundle(BASE_DIR, state, layers)

    with open(MEMORY_FILE, encoding='utf-8') as handle:
        content = handle.read()
    pre_baseline = pre_event_content if pre_event_content is not None else content
    panels = {}
    leverage_meta = {'applied': False, 'targets': []}
    unlock_out = {}
    dep_caps_out = {}
    latent_out = {}
    masturbation_out = {}
    creampie_chars = set()

    def _flush_sim():
        nonlocal content
        content = _simulate_panel(content, panels)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as _h:
            _h.write(content)

    # 0. 检查已到期的受孕潜伏期（跨入或超过确诊目标日自动转为可确诊/面板怀孕=True，并同步羞耻崩解与<=35封顶）
    existing_latent_map = dict((state.get('mechanics') or {}).get('pregnancy_latent_until') or {})
    if current_day is not None and int(current_day) > 0:
        for hname, lday in existing_latent_map.items():
            if int(lday or 0) > 0 and int(current_day) >= int(lday):
                if not state['panels'].get(hname, {}).get('怀孕'):
                    panels.setdefault(hname, {})['怀孕'] = 'True'
                    if _event_tag('SHAME_10') not in ((norm_events.get('shame_events') or {}).get(hname) or ()):
                        cur_shame = _read_attr_value(content, hname, '羞耻')
                        if cur_shame is not None:
                            panels.setdefault(hname, {})['羞耻'] = min(35, max(0, cur_shame - 30))
                latent_out[hname] = 0
        if panels:
            _flush_sim()

    if norm_events['depravity_events']:
        dep_updates = process_depravity_system(
            norm_events['depravity_events'], MEMORY_FILE,
            unlocked_caps=state['mechanics'].get('depravity_unlocked_caps'),
            caps_out=dep_caps_out,
        )
        for who, val in dep_updates.items():
            panels.setdefault(who, {})['堕落'] = val
            # 堕落抬升后即使本轮无羞耻事件，亦立即夹紧羞耻至最新堕落侵蚀上限
            cur_sh = _read_attr_value(content, who, '羞耻')
            pas_m = re.search(rf"\[{re.escape(who)}\].*?被动\s*Lv\.?(\d+)", content)
            preg_m = re.search(rf"\[{re.escape(who)}\].*?怀孕\s*(True|False)", content)
            cur_pas = int(pas_m.group(1)) if pas_m else 0
            is_preg = bool((preg_m and preg_m.group(1) == 'True') or panels.get(who, {}).get('怀孕') == 'True')
            erosion_c = 0.7 if cur_pas >= 4 else 0.6
            new_cap = min(35 if is_preg else 100, max(0, 100 - int(val * erosion_c)))
            if cur_sh is not None and cur_sh > new_cap:
                panels.setdefault(who, {})['羞耻'] = new_cap
        for who, dtags in norm_events['depravity_events'].items():
            if _event_tag('DEPRAVITY_10') in (dtags or ()):
                masturbation_out[who] = 2
        _flush_sim()

    shame = norm_events['shame_events']
    if shame:
        creampie_tags = {_event_tag('SHAME_06'), _event_tag('SHAME_07')}
        shame10_tag = _event_tag('SHAME_10')
        for who in list(shame.keys()):
            wtags = list(shame.get(who) or [])
            if shame10_tag in wtags:
                has_preg_basis = (
                    bool(state['panels'].get(who, {}).get('怀孕'))
                    or panels.get(who, {}).get('怀孕') == 'True'
                    or int(existing_latent_map.get(who, 0) or 0) > 0
                    or bool(creampie_tags & set(wtags))
                )
                if not has_preg_basis:
                    wtags = [t for t in wtags if t != shame10_tag]
                    if wtags:
                        shame[who] = wtags
                    else:
                        shame.pop(who, None)
        for who, val in process_pregnancy_rng(
            shame, MEMORY_FILE, ds_events=norm_events['ds_events'],
            current_day=current_day, latent_map=existing_latent_map, latent_out=latent_out,
            host_charm=host_charm, body_dev=body_dev_now, body_acts=body_acts,
            host_desire=host_desire_now, edging_streak=edging_streak_now, host_vigor=host_vigor_now,
        ).items():
            panels.setdefault(who, {})['怀孕'] = val
        for who, tags in shame.items():
            inc = sum(1 for t in (tags or []) if t in creampie_tags)
            if inc > 0:
                creampie_chars.add(who)
                m_cnt = re.search(rf"\[{re.escape(who)}\].*?内射\s*(\d+)次", content)
                cur_cnt = int(m_cnt.group(1)) if m_cnt else 0
                panels.setdefault(who, {})['内射'] = cur_cnt + inc
            if _event_tag('SHAME_20') in (tags or ()):
                masturbation_out[who] = 2
        for who, val in process_shame_system(
            shame, MEMORY_FILE, privacy=eff_privacy, host_charm=host_charm, body_acts=body_acts,
        ).items():
            panels.setdefault(who, {})['羞耻'] = val
        _flush_sim()

    resentment_map = {
        h: int(((state.get('npc_mind') or {}).get(h) or {}).get('resentment', 0) or 0)
        for h in save_store.HEROINES
    }
    coy_chars = set()
    if shame or norm_events['affection_events']:
        for who, val in process_affection_system(
            norm_events['affection_events'], shame, MEMORY_FILE,
            business_leverage=business_leverage, leverage_meta=leverage_meta,
            su_85_unlocked=bool(state['mechanics'].get('su_affection_85_unlocked')),
            unlock_out=unlock_out, host_charm=host_charm,
            resentment_map=resentment_map, privacy=eff_privacy,
            active_cast=active_cast, ds_events=norm_events['ds_events'],
            coy_out=coy_chars,
        ).items():
            panels.setdefault(who, {})['好感'] = val
        _flush_sim()

    heroine_cast = [c for c in (active_cast or ()) if c in save_store.HEROINES]
    # 温暖日常好感补底：A/B 档无越界与负面事件、副模型记了日常_信任建立/情感共振却漏标正面好感时，为单在场女主补 +1（限 <90 且守住苏婉青天花板）
    if (
        str(action_category or '').upper() in ('A', 'B')
        and not shame
        and len(heroine_cast) == 1
    ):
        who_warm = heroine_cast[0]
        host_ev_now = norm_events.get('host_events') or []
        has_warm_host_now = (_event_tag('HOST_05') in host_ev_now) or (_event_tag('HOST_06') in host_ev_now)
        who_aff_tags = (norm_events.get('affection_events') or {}).get(who_warm) or []
        who_ds_tags = (norm_events.get('ds_events') or {}).get(who_warm) or []
        neg_aff_set = {_event_tag('AFFECTION_01'), _event_tag('AFFECTION_02')}
        if (
            has_warm_host_now
            and not who_aff_tags
            and not (set(who_aff_tags) & neg_aff_set)
            and (_event_tag('DS_10') not in who_ds_tags)
            and '好感' not in (panels.get(who_warm) or {})
        ):
            cur_aff_w = _read_attr_value(content, who_warm, '好感')
            if cur_aff_w is not None and cur_aff_w < 90:
                su_unlk = bool(state['mechanics'].get('su_affection_85_unlocked')) or bool(unlock_out.get('su_affection_85_unlocked')) or cur_aff_w > 85
                cap_w = (95 if su_unlk else 85) if who_warm == '苏婉青' else 100
                next_aff_w = min(cap_w, cur_aff_w + 1)
                if next_aff_w > cur_aff_w:
                    panels.setdefault(who_warm, {})['好感'] = next_aff_w
                    _flush_sim()
                    print(f" 💗 [好感引擎] {who_warm} 触发【温暖日常补底】（{action_category}档无越界+日常信任/共振）：好感 {cur_aff_w} -> {next_aff_w}")
    auto_climax = set()
    if norm_events['ds_events'] or creampie_chars or heroine_cast or coy_chars:
        for who, values in process_desire_stamina_system(
            norm_events['ds_events'], MEMORY_FILE, creampie_chars=creampie_chars,
            active_cast=heroine_cast, host_charm=host_charm, privacy=eff_privacy,
            climax_out=auto_climax, body_dev=body_dev_now, body_acts=body_acts,
            host_desire=host_desire_now, host_vigor=host_vigor_now, edging_streak=edging_streak_now,
            coy_chars=coy_chars,
        ).items():
            panels.setdefault(who, {}).update({k: values[k] for k in ('欲望', '体力', '高潮')})
        climax_tag = _event_tag('DS_17')
        for who in auto_climax:
            dlist = norm_events['ds_events'].setdefault(who, [])
            if climax_tag not in dlist:
                dlist.append(climax_tag)
        for who, dstags in (norm_events['ds_events'] or {}).items():
            if _event_tag('DS_18') in (dstags or ()):
                masturbation_out[who] = 2
        _flush_sim()

    # 生理断电/虚脱温和照料回体：非越界 A 档且本轮无任何羞耻/消耗标签时，对体力<=25的在场女主温和回体+5（上限30）
    if action_category == 'A' and heroine_cast:
        drain_ds_tags = {
            _event_tag('DS_08'), _event_tag('DS_09'), _event_tag('DS_10'),
            _event_tag('DS_11'), _event_tag('DS_17'), _event_tag('DS_18'),
        }
        care_changed = False
        for who in heroine_cast:
            if shame.get(who):
                continue
            if set((norm_events.get('ds_events') or {}).get(who) or ()) & drain_ds_tags:
                continue
            cur_sta_val = _read_attr_value(content, who, '体力')
            if cur_sta_val is not None and cur_sta_val <= 25:
                next_sta = min(30, cur_sta_val + 5)
                if next_sta > cur_sta_val:
                    panels.setdefault(who, {})['体力'] = next_sta
                    care_changed = True
                    print(f" 🍵 [生理引擎] {who} 处于虚脱期(体力{cur_sta_val}≤25)，温和照料缓气回体 -> {next_sta}。")
        if care_changed:
            _flush_sim()

    # 欲拒还迎（AFFECTION_12）自动联动轨道 1 初阶（侵蚀_认知撕裂），避免嘴硬心软试探回合白打
    if coy_chars:
        track1_tags = {
            _event_tag('HOST_01'), _event_tag('HOST_02'),
            _event_tag('HOST_03'), _event_tag('HOST_04'),
        }
        if not any(t in track1_tags for t in norm_events['host_events']):
            norm_events['host_events'].append(_event_tag('HOST_01'))

    has_non_host_event = bool(
        norm_events['depravity_events']
        or shame
        or norm_events['affection_events']
        or norm_events['ds_events']
        or norm_events.get('vigilance_events')
    )
    action_floor = (
        ACTION_ECONOMY_FLOOR.get(str(action_category or '').upper())
        if (effective_progress or has_non_host_event)
        else None
    )

    if norm_events['host_events'] or shame or action_floor:
        host = process_host_system(
            norm_events['host_events'], shame, MEMORY_FILE,
            action_floor=action_floor,
        )
        if host:
            panels.setdefault('系统宿主', {}).update(host)
            _flush_sim()

    # 维护自慰痕迹自然递减与新增覆盖
    prev_mast = dict((state.get('mechanics') or {}).get('masturbation_trace') or {})
    new_mast = {}
    for hname in save_store.HEROINES:
        if hname in masturbation_out:
            new_mast[hname] = masturbation_out[hname]
        else:
            new_mast[hname] = max(0, int(prev_mast.get(hname, 0) or 0) - 1)
    mast_changed = (new_mast != prev_mast)

    if unlock_out.get('su_affection_85_unlocked') or dep_caps_out or latent_out or mast_changed:
        st2, ly2, _ = save_store.load_bundle(BASE_DIR)
        if unlock_out.get('su_affection_85_unlocked'):
            st2['mechanics']['su_affection_85_unlocked'] = True
        if dep_caps_out:
            st2['mechanics'].setdefault('depravity_unlocked_caps', {}).update(dep_caps_out)
        if latent_out:
            st2['mechanics'].setdefault('pregnancy_latent_until', {}).update(latent_out)
        if mast_changed:
            st2['mechanics']['masturbation_trace'] = new_mast
        save_store.save_bundle(BASE_DIR, st2, ly2)
    if not defer_task:
        reward = process_task_system(
            task_issue, memory_round, MEMORY_FILE, sim_content=content, pre_event_content=pre_baseline,
        )
        if reward:
            with open(MEMORY_FILE, encoding='utf-8') as handle: content = handle.read()
            host = _read_host_panel(MEMORY_FILE)
            for key, val in reward.items(): host[key] += val
            with open(MEMORY_FILE, 'w', encoding='utf-8') as handle:
                handle.write(_simulate_panel(content, {'系统宿主': host}))
    return {
        'leverage_meta': leverage_meta,
        'normalized_events': norm_events,
        'mechanics_notes': mech_notes,
        'auto_climax': sorted(auto_climax),
        'coy_chars': sorted(coy_chars),
    }


def consume_story_recovery_item(item_id, recovery, memory_round):
    """Consume precisely one held registered item via save_store; append usage even for a remaining stack and replenish vigor."""
    state, layers, _ = save_store.load_bundle(BASE_DIR)
    active = state['items']['active']
    idx = next((i for i, it in enumerate(active) if it.get('id') == item_id), None)
    if idx is None:
        raise ValueError('恢复道具已不存在')
    item = active[idx]
    if item.get('status') != '仓库中' or int(item.get('quantity', 0)) < 1:
        raise ValueError('恢复道具库存不合法')
    cur_sta = int(state['panels']['系统宿主']['体力'])
    if recovery <= 0 or cur_sta + recovery > 100:
        raise ValueError('实际恢复量无效')
    vigor_gain = 15 if recovery <= 10 else 25
    usage = '游戏回合' + str(memory_round) + ' - 使用1份，宿主体力恢复' + str(recovery) + '（亲密耐力+' + str(vigor_gain) + '）'
    if int(item['quantity']) == 1:
        done = copy.deepcopy(active.pop(idx))
        done['status'] = '已消耗'
        done['remaining_turns'] = None
        done['remaining'] = '无'
        done['usage_record'] = _merge_usage(done.get('usage_record'), usage)
        state['items']['history'].insert(0, done)
    else:
        item['quantity'] = int(item['quantity']) - 1
        item['usage_record'] = _merge_usage(item.get('usage_record'), usage)
    state['panels']['系统宿主']['体力'] = cur_sta + recovery
    hp = state.setdefault('intimate', save_store.default_intimate()).setdefault('host_phys', save_store.default_host_phys())
    hp['vigor'] = min(100, int(hp.get('vigor', 100) or 0) + vigor_gain)
    save_store.save_bundle(BASE_DIR, state, layers)


def _alloc_state_item_id(items_box):
    seq = int(items_box.get('next_seq', 1))
    existing_nums = [
        int(it['id'].split('-')[1])
        for bucket in (
            items_box.get('active', []),
            items_box.get('deployed', []),
            items_box.get('delivered', []),
            items_box.get('history', []),
        )
        for it in bucket
        if re.fullmatch(r'ITEM-\d+', str(it.get('id') or ''))
    ]
    seq = max(seq, (max(existing_nums) + 1) if existing_nums else 1)
    items_box['next_seq'] = seq + 1
    return f'ITEM-{seq:03d}'


def apply_interaction_operation(operation, *, clock_str=''):
    """Apply a prevalidated operation inside a RoundStore staging directory. Returns optional metadata dict."""
    code = operation['code']
    stamp = (clock_str.strip() + ' - ') if isinstance(clock_str, str) and clock_str.strip() else ''
    if code == 'move_player':
        update_presence({'徐志北': {'location': operation['destination'], 'reason': '玩家明确前往'}})
        return {'code': code, 'destination': operation['destination']}
    if code == 'transfer_item':
        state, layers, _ = save_store.load_bundle(BASE_DIR)
        active = state['items']['active']
        idx = next((i for i, it in enumerate(active) if it.get('id') == operation['item_id']), None)
        if idx is None:
            raise ValueError('交付道具已不存在')
        item = active[idx]
        if item.get('giftable') is False:
            raise ValueError('该道具为个人消耗/不可转赠物品，不能交付给他人')
        cur_qty = max(1, int(item.get('quantity', 1)))
        req_qty = operation.get('quantity')
        give_qty = cur_qty if (req_qty is None or int(req_qty) >= cur_qty) else max(1, int(req_qty))
        place = state['presence']['徐志北']['location']
        if give_qty < cur_qty:
            item['quantity'] = cur_qty - give_qty
            item['usage_record'] = _merge_usage(item.get('usage_record'), f"{stamp}赠予{operation['recipient']}×{give_qty}")
            delivered = copy.deepcopy(item)
            delivered['id'] = _alloc_state_item_id(state['items'])
            delivered['quantity'] = give_qty
        else:
            delivered = copy.deepcopy(active.pop(idx))
        delivered['status'] = '已交付'
        delivered['target'] = operation['recipient']
        delivered['location'] = place
        delivered['remaining_turns'] = None
        delivered['remaining'] = '无'
        note_str = f"{stamp}已交付给{operation['recipient']}（×{give_qty}）" if req_qty is not None else f"{stamp}已整组交付给{operation['recipient']}"
        delivered['usage_record'] = _merge_usage(delivered.get('usage_record'), note_str)
        norm_deliv = save_store.normalize_item_dict(delivered)
        state['items']['delivered'].insert(0, norm_deliv)
        # 赠予情趣可穿戴礼盒（如丝袜/真丝睡裙）同步登记至该女主衣着衣橱，供后续场景自然穿戴
        rec_name = operation['recipient']
        if rec_name in save_store.HEROINES and (
            norm_deliv.get('category') == 'sensual'
            or re.search(r'丝袜|睡裙|内衣|情趣|吊带|蕾丝', str(norm_deliv.get('name', '')))
        ):
            intl_blk = state.setdefault('intimate', save_store.default_intimate())
            att_map = intl_blk.setdefault('attire', {}).setdefault(rec_name, {'outfit': 'default', 'state': 'neat', 'gifted_items': []})
            glist = att_map.setdefault('gifted_items', [])
            if norm_deliv['name'] not in glist:
                glist.append(norm_deliv['name'])
        save_store.save_bundle(BASE_DIR, state, layers)
        return {'code': code, 'item_id': operation['item_id'], 'item_name': delivered['name'], 'quantity': give_qty, 'recipient': operation['recipient']}
    if code == 'use_item':
        state, layers, _ = save_store.load_bundle(BASE_DIR)
        active = state['items']['active']
        idx = next((i for i, it in enumerate(active) if it.get('id') == operation['item_id']), None)
        if idx is None:
            raise ValueError('待使用道具已不存在')
        item = save_store.normalize_item_dict(active[idx])
        if item.get('status') != '仓库中' or int(item.get('quantity', 0)) < 1:
            raise ValueError('该道具当前不可使用')
        mode = item.get('usage_mode', 'gift')
        target = str(operation.get('target') or '').strip()
        target_label = target or '当前场景'
        is_consumable = (mode == 'consumable_target') or (mode == 'consumable_host') or ('消耗品' in str(item.get('type', '')) and mode != 'reusable_tool')
        usage_note = f"{stamp}对{target_label}使用1份" if is_consumable else f"{stamp}在行动中使用（对象：{target_label}）"
        if is_consumable:
            cur_qty = int(item.get('quantity', 1))
            if cur_qty <= 1:
                done = copy.deepcopy(active.pop(idx))
                done['status'] = '已消耗'
                done['target'] = target or done.get('target', '未使用')
                done['remaining_turns'] = None
                done['remaining'] = '无'
                done['usage_record'] = _merge_usage(done.get('usage_record'), usage_note)
                state['items']['history'].insert(0, save_store.normalize_item_dict(done))
            else:
                item['quantity'] = cur_qty - 1
                item['usage_record'] = _merge_usage(item.get('usage_record'), usage_note)
                active[idx] = item
        else:
            item['usage_record'] = _merge_usage(item.get('usage_record'), usage_note)
            active[idx] = item
        save_store.save_bundle(BASE_DIR, state, layers)
        return {
            'code': code,
            'item_id': item['id'],
            'item_name': item['name'],
            'usage_mode': mode,
            'target': target,
            'system_effect': item.get('system_effect', ''),
        }
    if code == 'deploy_item':
        state, layers, _ = save_store.load_bundle(BASE_DIR)
        active = state['items']['active']
        deployed = state['items'].setdefault('deployed', [])
        idx = next((i for i, it in enumerate(active) if it.get('id') == operation['item_id']), None)
        if idx is None:
            raise ValueError('待部署装置已不存在')
        item = save_store.normalize_item_dict(active[idx])
        if item.get('usage_mode') != 'deployable_device' and not str(item.get('system_effect', '')).startswith('deploy_device:'):
            raise ValueError('该道具不是可部署的场景装置')
        place = state['presence']['徐志北']['location']
        spot = str(operation.get('spot') or '隐蔽角落').strip() or '隐蔽角落'
        hidden = bool(operation.get('hidden', True))
        cur_qty = int(item.get('quantity', 1))
        if cur_qty > 1:
            item['quantity'] = cur_qty - 1
            item['usage_record'] = _merge_usage(item.get('usage_record'), f"{stamp}分出1台部署于{place}·{spot}")
            active[idx] = item
            dev = copy.deepcopy(item)
            dev['id'] = _alloc_state_item_id(state['items'])
            dev['quantity'] = 1
        else:
            dev = copy.deepcopy(active.pop(idx))
            dev['quantity'] = 1
        witnesses_here = [
            n for n, info in (state.get('presence') or {}).items()
            if n != '徐志北' and (info or {}).get('location') == place
        ]
        dev['status'] = '已部署'
        dev['location'] = place
        dev['spot'] = spot
        dev['hidden'] = hidden
        dev['installed_clock'] = clock_str.strip() if isinstance(clock_str, str) else ''
        dev['detected_risk'] = 12 if (hidden and witnesses_here) else 0
        dev['usage_record'] = _merge_usage(dev.get('usage_record'), f"{stamp}{'暗中' if hidden else '公开'}部署于{place}·{spot}")
        deployed.insert(0, save_store.normalize_item_dict(dev))
        save_store.save_bundle(BASE_DIR, state, layers)
        return {'code': code, 'item_id': dev['id'], 'item_name': dev['name'], 'location': place, 'spot': spot, 'hidden': hidden, 'detected_risk': dev['detected_risk']}
    if code == 'retrieve_item':
        state, layers, _ = save_store.load_bundle(BASE_DIR)
        deployed = state['items'].setdefault('deployed', [])
        idx = next((i for i, it in enumerate(deployed) if it.get('id') == operation['item_id']), None)
        if idx is None:
            raise ValueError('已部署装置不存在或已被回收')
        dev = save_store.normalize_item_dict(deployed[idx])
        place = state['presence']['徐志北']['location']
        if dev.get('location') != place:
            raise ValueError(f"须身处装置所在地（{dev.get('location')}）才能拆除回收")
        rec = copy.deepcopy(deployed.pop(idx))
        old_spot = rec.get('spot') or '原位'
        rec['status'] = '仓库中'
        rec['location'] = '随身'
        rec['spot'] = ''
        rec['installed_clock'] = ''
        rec['detected_risk'] = 0
        rec['usage_record'] = _merge_usage(rec.get('usage_record'), f"{stamp}从{place}·{old_spot}拆除回收")
        state['items']['active'].append(save_store.normalize_item_dict(rec))
        save_store.save_bundle(BASE_DIR, state, layers)
        return {'code': code, 'item_id': rec['id'], 'item_name': rec['name'], 'location': place}
    if code == 'inspect_deployed':
        state, layers, _ = save_store.load_bundle(BASE_DIR)
        deployed = state['items'].setdefault('deployed', [])
        idx = next((i for i, it in enumerate(deployed) if it.get('id') == operation['item_id']), None)
        if idx is None:
            raise ValueError('要查看的已部署装置不存在')
        dev = save_store.normalize_item_dict(deployed[idx])
        if dev.get('hidden', True):
            dev['detected_risk'] = min(100, int(dev.get('detected_risk') or 0) + 5)
        dev['usage_record'] = _merge_usage(dev.get('usage_record'), f"{stamp}远程回看({dev.get('location')}·{dev.get('spot') or '隐蔽处'})")
        deployed[idx] = dev
        save_store.save_bundle(BASE_DIR, state, layers)
        return {'code': code, 'item_id': dev['id'], 'item_name': dev['name'], 'location': dev.get('location', ''), 'spot': dev.get('spot', ''), 'detected_risk': dev['detected_risk']}
    if code == 'keepsake_action':
        state, layers, _ = save_store.load_bundle(BASE_DIR)
        intl = state.setdefault('intimate', save_store.default_intimate())
        ks_list = intl.setdefault('keepsakes', [])
        ks_id = str(operation.get('keepsake_id') or '').strip()
        act_type = str(operation.get('action_type') or '').strip()
        idx = next((i for i, it in enumerate(ks_list) if isinstance(it, dict) and it.get('id') == ks_id), None)
        if idx is None:
            raise ValueError('该私密珍藏物品不存在或已归还')
        if act_type not in save_store.KEEPSAKE_ACTIONS:
            raise ValueError('不支持的私密珍藏互动方式')
        ks = copy.deepcopy(ks_list[idx])
        hp = intl.setdefault('host_phys', save_store.default_host_phys())
        if act_type == 'return_secret':
            ks_list.pop(idx)
        else:
            ks['interactions'] = int(ks.get('interactions') or 0) + 1
            if act_type == 'sniff_play':
                hp['desire'] = min(100, int(hp.get('desire', 0) or 0) + 18)
            elif act_type == 'confront':
                ks['owner_aware'] = True
            elif act_type == 'use_intimate':
                ks['owner_aware'] = True
                if ks.get('condition') == 'faded':
                    ks['condition'] = 'stained_damp'
            ks_list[idx] = ks
        hp['fetishes'] = derive_host_fetishes(intl.get('body_dev'), ks_list)
        save_store.save_bundle(BASE_DIR, state, layers)
        return {
            'code': code,
            'keepsake_id': ks_id,
            'action_type': act_type,
            'owner': ks.get('owner', ''),
            'name': ks.get('name', ''),
            'owner_aware': bool(ks.get('owner_aware')),
        }
    raise ValueError('不支持的正式互动操作')


_WASH_OFF_TRACE_KINDS = frozenset({'潮红', '腿软潮红', '汗息', '衣领凌乱', '极敏余韵', '体液残留', '水痕', '香气混杂'})


def _alloc_keepsake_id(intl):
    seq = int(intl.get('next_keepsake_seq', 1) or 1)
    existing = [
        int(it['id'].split('-')[1])
        for it in (intl.get('keepsakes') or [])
        if isinstance(it, dict) and re.fullmatch(r'KS-\d+', str(it.get('id') or ''))
    ]
    seq = max(seq, (max(existing) + 1) if existing else 1)
    intl['next_keepsake_seq'] = seq + 1
    return f'KS-{seq:03d}'


def advance_intimate_state(state, events, *, scene_state=None, active_cast=None, building_cast=None,
                           sleep_kind='none', location_changed=False, category='A', host_charm=None,
                           prose_text='', clock_str='', location='', elapsed_hours=0,
                           operation=None, vigor_costs=None, body_acts=None,
                           charm_gained_this_turn=False):
    """Deterministically advance save_state['intimate'] (privacy/stealth/attire/traces/inter_heroine/host_phys/body_dev/keepsakes/session beats & device risk)."""
    intl = state.setdefault('intimate', save_store.default_intimate())
    hp = intl.setdefault('host_phys', save_store.default_host_phys())
    bd = intl.setdefault('body_dev', save_store.default_body_dev())
    ks_list = intl.setdefault('keepsakes', [])
    for hname in save_store.HEROINES:
        bd.setdefault(hname, {z: 0 for z in save_store.BODY_ZONES})
        for z in save_store.BODY_ZONES:
            bd[hname].setdefault(z, 0)

    shame_ev = (events or {}).get('shame_events') or {}
    ds_ev = (events or {}).get('ds_events') or {}
    host_ev = (events or {}).get('host_events') or []
    eff_charm = int(host_charm if host_charm is not None else (((state.get('panels') or {}).get('系统宿主') or {}).get('魅力', 70) or 70))
    charm_info = charm_tier_info(eff_charm)
    was_scene_active = bool(intl.get('scene_active'))

    def _upsert_trace(hname, kind, desc, turns, visible=True):
        arr = intl.setdefault('traces', {}).setdefault(hname, [])
        for existing in arr:
            if existing.get('kind') == kind:
                existing['desc'] = desc[:80]
                existing['turns'] = max(int(existing.get('turns') or 0), int(turns))
                existing['visible'] = bool(visible)
                return
        arr.append({'kind': kind[:24], 'desc': desc[:80], 'turns': int(turns), 'visible': bool(visible)})
        intl['traces'][hname] = arr[-6:]

    # 1. 自然递减旧痕迹
    for hname in save_store.HEROINES:
        kept = []
        for tr in (intl.get('traces') or {}).get(hname) or []:
            rem = int(tr.get('turns') or 0) - 1
            if sleep_kind == 'overnight':
                if tr.get('kind') in _WASH_OFF_TRACE_KINDS:
                    rem = 0
                else:
                    rem = max(0, rem - 2)
            if rem > 0:
                kept.append({**tr, 'turns': rem})
        intl.setdefault('traces', {})[hname] = kept

    # 2. 跨地点或整夜睡眠重置场内亲密会话与隐私（痕迹、衣着与贴身珍藏气味按规则演变）
    if sleep_kind == 'overnight':
        intl['scene_active'] = False
        intl['session_beats'] = 0
        intl['session_orgasms'] = {h: 0 for h in save_store.HEROINES}
        intl['session_charm_gained'] = False
        intl['session_econ_climax_paid'] = False
        intl['noise_risk'] = 0
        intl['privacy'] = 'open_public'
        intl['sub_location'] = ''
        intl['present_actors'] = []
        for hname in save_store.HEROINES:
            att = intl.setdefault('attire', {}).setdefault(hname, {'outfit': 'default', 'state': 'neat', 'gifted_items': []})
            att['state'] = 'neat'
        for dev in (state.get('items', {}).get('deployed') or []):
            if isinstance(dev, dict) and int(dev.get('detected_risk') or 0) > 0:
                dev['detected_risk'] = max(0, int(dev['detected_risk']) - 3)
        for ks in ks_list:
            if isinstance(ks, dict) and ks.get('condition') == 'fresh_warm':
                ks['condition'] = 'faded'
    elif location_changed:
        intl['scene_active'] = False
        intl['session_beats'] = 0
        intl['session_orgasms'] = {h: 0 for h in save_store.HEROINES}
        intl['session_charm_gained'] = False
        intl['session_econ_climax_paid'] = False
        intl['noise_risk'] = 0
        intl['privacy'] = 'open_public'
        intl['sub_location'] = ''
        intl['present_actors'] = []

    # 3. 依据本轮事件判定亲密进行态、宿主释放、肾上腺素与自动身体余韵痕迹
    intimate_shame_tags = {_event_tag('SHAME_02'), _event_tag('SHAME_03'), _event_tag('SHAME_04'), _event_tag('SHAME_06'), _event_tag('SHAME_07')}
    intimate_ds_tags = {_event_tag('DS_04'), _event_tag('DS_06'), _event_tag('DS_07'), _event_tag('DS_14'), _event_tag('DS_15'), _event_tag('DS_16'), _event_tag('DS_17')}
    climax_tag = _event_tag('DS_17')
    creampie_tags = {_event_tag('SHAME_06'), _event_tag('SHAME_07')}
    release_shame_tags = {_event_tag('SHAME_05'), _event_tag('SHAME_06'), _event_tag('SHAME_07')}
    charm_backlash_shame_tags = {_event_tag('SHAME_09'), _event_tag('SHAME_14')}
    charm_caught_vig_tags = {_event_tag('VIGILANCE_01'), _event_tag('VIGILANCE_02')}
    vig_ev = (events or {}).get('vigilance_events') or {}
    high_noise_shame = {_event_tag('SHAME_03'), _event_tag('SHAME_04')}
    sensory_ds_tags = {_event_tag('DS_01'), _event_tag('DS_02'), _event_tag('DS_03')}

    triggered_intimate = False
    climax_hit = False
    host_released = False
    shame_backlash_hit = False
    vig_caught_hit = any(
        bool(set(vtags or ()) & charm_caught_vig_tags)
        for vtags in vig_ev.values()
        if isinstance(vtags, list)
    )
    adrenaline_vigor = bool(_event_tag('HOST_03') in host_ev or _event_tag('HOST_04') in host_ev)
    max_shame_noise = 0
    max_desire_c_gain = 0
    sensory_hit = False
    heroine_c_intensity = {}
    for hname in save_store.HEROINES:
        stags = set(shame_ev.get(hname) or ())
        dtags = set(ds_ev.get(hname) or ())
        if (stags & intimate_shame_tags) or (dtags & intimate_ds_tags):
            triggered_intimate = True
        if stags & release_shame_tags:
            host_released = True
        if stags & charm_backlash_shame_tags:
            shame_backlash_hit = True
        if _event_tag('SHAME_07') in stags:
            adrenaline_vigor = True
        if (dtags & sensory_ds_tags) or (_event_tag('SHAME_20') in stags):
            sensory_hit = True
        if _event_tag('SHAME_04') in stags or (stags & creampie_tags):
            max_desire_c_gain = max(max_desire_c_gain, 28)
            heroine_c_intensity[hname] = 'heavy'
        elif _event_tag('SHAME_03') in stags:
            max_desire_c_gain = max(max_desire_c_gain, 22)
            heroine_c_intensity[hname] = 'deep'
        elif _event_tag('SHAME_02') in stags:
            max_desire_c_gain = max(max_desire_c_gain, 14)
            heroine_c_intensity[hname] = 'mid'
        elif _event_tag('SHAME_01') in stags or _event_tag('DS_04') in dtags:
            max_desire_c_gain = max(max_desire_c_gain, 8)
            heroine_c_intensity[hname] = 'light'
        if stags & high_noise_shame:
            max_shame_noise = max(max_shame_noise, 20)
        elif _event_tag('SHAME_02') in stags:
            max_shame_noise = max(max_shame_noise, 10)
        if climax_tag in dtags:
            climax_hit = True
            intl.setdefault('session_orgasms', {})[hname] = int(intl.get('session_orgasms', {}).get(hname, 0) or 0) + 1
            _upsert_trace(hname, '极敏余韵', '绝顶后神经仍处于高敏酥麻状态，轻触易再失守', 3, visible=False)
            _upsert_trace(hname, '腿软潮红', '眼尾与锁骨尚留潮红，呼吸微促步履发软', 3, visible=True)
        if stags & creampie_tags:
            _upsert_trace(hname, '体液残留', '体内温热未散，起身走动时偶有湿滑失守感', 6, visible=False)

    # 4. 合并 Stage 2 校验后的 scene_state 增量
    ss = scene_state if isinstance(scene_state, dict) else {}
    if ss.get('host_release') is True:
        host_released = True
    if ss.get('privacy') in save_store.PRIVACY_LEVELS:
        intl['privacy'] = ss['privacy']
    if isinstance(ss.get('sub_location'), str) and ss['sub_location'].strip():
        intl['sub_location'] = ss['sub_location'].strip()[:48]
    if isinstance(ss.get('present_actors'), list):
        valid_pool = set(active_cast or ()) | set(building_cast or ())
        cleaned_pa = [a for a in ss['present_actors'] if isinstance(a, str) and (not valid_pool or a in valid_pool)]
        if cleaned_pa or not valid_pool:
            intl['present_actors'] = list(dict.fromkeys(cleaned_pa))
    if isinstance(ss.get('attire_updates'), dict):
        for hname, patch in ss['attire_updates'].items():
            if hname not in save_store.HEROINES or not isinstance(patch, dict):
                continue
            att = intl.setdefault('attire', {}).setdefault(hname, {'outfit': 'default', 'state': 'neat', 'gifted_items': []})
            if isinstance(patch.get('outfit'), str) and patch['outfit'].strip():
                att['outfit'] = patch['outfit'].strip()[:64]
            if patch.get('state') in save_store.ATTIRE_STATES:
                att['state'] = patch['state']
    if isinstance(ss.get('trace_adds'), dict):
        for hname, items in ss['trace_adds'].items():
            if hname not in save_store.HEROINES or not isinstance(items, list):
                continue
            for tr in items[:2]:
                if isinstance(tr, dict) and str(tr.get('kind') or '').strip():
                    _upsert_trace(
                        hname,
                        str(tr['kind']).strip(),
                        str(tr.get('desc') or tr['kind']).strip(),
                        max(1, min(12, int(tr.get('turns') or 4))),
                        visible=bool(tr.get('visible', True)),
                    )
    if isinstance(ss.get('inter_heroine_deltas'), dict):
        ih = intl.setdefault('inter_heroine', {p: 0 for p in save_store.INTER_HEROINE_PAIRS})
        for pair, delta in ss['inter_heroine_deltas'].items():
            if pair in save_store.INTER_HEROINE_PAIRS and isinstance(delta, int):
                step = max(-1, min(1, delta))
                ih[pair] = max(0, min(3, int(ih.get(pair, 0) or 0) + step))

    # 4.5 身体开发度与招牌敏感带成长（轻中 +4 / 深重 +8，招牌 ×1.35 -> +5/+11，单轮至多结算 2 个重点部位）
    resolved_body_acts = body_acts if isinstance(body_acts, dict) else infer_body_acts_from_prose(
        prose_text, events, explicit_acts=ss.get('body_acts')
    )
    dev_milestones = []
    dev_econ_milestones = []
    service_desire_bonus = 0
    for hname, zones in resolved_body_acts.items():
        if hname not in save_store.HEROINES or not isinstance(zones, list):
            continue
        tier_hit = heroine_c_intensity.get(hname, 'light')
        base_gain = 8 if tier_hit in ('deep', 'heavy') else 4
        sig_zone = save_store.HEROINE_SIGNATURE_ZONES.get(hname)
        focus_zones = list(dict.fromkeys(z for z in zones if z in save_store.BODY_ZONES))[:MAX_BODY_ACTS_PER_TURN]
        for z in focus_zones:
            old_val = int(bd[hname].get(z, 0) or 0)
            old_lv = body_dev_level(old_val)
            gain = int(round(base_gain * (1.35 if z == sig_zone else 1.0)))
            new_val = min(100, old_val + gain)
            bd[hname][z] = new_val
            new_lv = body_dev_level(new_val)
            if new_lv > old_lv:
                z_label = save_store.BODY_ZONE_LABELS.get(z, z)
                for crossed_lv in range(old_lv + 1, new_lv + 1):
                    if crossed_lv in BODY_DEV_ECON_REWARDS:
                        dev_econ_milestones.append({'heroine': hname, 'zone': z, 'label': z_label, 'level': crossed_lv})
                if new_lv >= 2:
                    dev_milestones.append({'heroine': hname, 'zone': z, 'label': z_label, 'level': new_lv})
            if z in ('oral', 'hand', 'chest', 'foot'):
                service_desire_bonus = max(service_desire_bonus, 4 + new_lv * 2)

    # 4.6 私密贴身收藏登记与更新（keepsake_adds / keepsake_updates）
    keepsakes_added = []
    new_keepsakes_created = []
    if isinstance(ss.get('keepsake_adds'), list):
        for raw_ks in ss['keepsake_adds'][:3]:
            if not isinstance(raw_ks, dict):
                continue
            owner = str(raw_ks.get('owner') or '').strip()
            kname = str(raw_ks.get('name') or '').strip()[:32]
            if owner not in save_store.HEROINES or not kname:
                continue
            existing = next(
                (k for k in ks_list if isinstance(k, dict) and k.get('owner') == owner and k.get('name') == kname),
                None,
            )
            if existing is not None:
                if raw_ks.get('condition') in save_store.KEEPSAKE_CONDITIONS:
                    existing['condition'] = raw_ks['condition']
                m_raw = 'taken_intimate' if raw_ks.get('method') == 'kept_after' else raw_ks.get('method')
                if m_raw in save_store.KEEPSAKE_METHODS:
                    existing['method'] = m_raw
                if isinstance(raw_ks.get('desc'), str) and raw_ks['desc'].strip():
                    existing['desc'] = raw_ks['desc'].strip()[:80]
                if clock_str:
                    existing['clock'] = str(clock_str).strip()[:24]
                keepsakes_added.append(copy.deepcopy(existing))
            else:
                new_id = _alloc_keepsake_id(intl)
                merged = dict(raw_ks)
                merged['id'] = new_id
                if not merged.get('location') and location:
                    merged['location'] = str(location).strip()[:24]
                if not merged.get('clock') and clock_str:
                    merged['clock'] = str(clock_str).strip()[:24]
                norm_k = save_store.normalize_keepsake_dict(merged, fallback_id=new_id)
                if norm_k:
                    ks_list.insert(0, norm_k)
                    if len(ks_list) > 24:
                        del ks_list[24:]
                    keepsakes_added.append(copy.deepcopy(norm_k))
                    new_keepsakes_created.append(copy.deepcopy(norm_k))
    if isinstance(ss.get('keepsake_updates'), list):
        for upd in ss['keepsake_updates'][:4]:
            if not isinstance(upd, dict):
                continue
            kid = str(upd.get('id') or '').strip()
            target_k = next((k for k in ks_list if isinstance(k, dict) and k.get('id') == kid), None)
            if target_k is None:
                continue
            if 'owner_aware' in upd and type(upd['owner_aware']) is bool:
                target_k['owner_aware'] = upd['owner_aware']
            if upd.get('condition') in save_store.KEEPSAKE_CONDITIONS:
                target_k['condition'] = upd['condition']

    # 5. 更新亲密进行态与慢燃拍数
    if sleep_kind != 'overnight' and not location_changed:
        explicit_active = ss.get('intimate_active') if 'intimate_active' in ss and type(ss.get('intimate_active')) is bool else None
        if triggered_intimate or explicit_active is True:
            intl['scene_active'] = True
            intl['session_beats'] = int(intl.get('session_beats', 0) or 0) + 1
        elif explicit_active is False:
            intl['scene_active'] = False
            intl['session_beats'] = 0
            intl['session_orgasms'] = {h: 0 for h in save_store.HEROINES}
            intl['session_charm_gained'] = False
            intl['session_econ_climax_paid'] = False
            intl['noise_risk'] = max(0, int(intl.get('noise_risk', 0) or 0) - 25)
        elif intl.get('scene_active'):
            # 维持亲密中进行（如 A 档喘息/调情缓拍）
            intl['session_beats'] = int(intl.get('session_beats', 0) or 0) + 1

    # 5.5 宿主欲望（Desire）与亲密耐力（Vigor）双池推进、同频共振与魅力增减平衡
    cur_h_des = max(0, min(100, int(hp.get('desire', 0) or 0)))
    cur_h_vig = max(0, min(100, int(hp.get('vigor', 100) or 0)))
    vc = vigor_costs if isinstance(vigor_costs, dict) else {'A': 2, 'B': 4, 'C': 7, 'release': 12}
    op_code = (operation or {}).get('code') if isinstance(operation, dict) else ''
    synced_climax = False
    if sleep_kind == 'overnight':
        hp['vigor'] = 100
        hp['desire'] = 25 if cur_h_des >= 70 else 0
        hp['edging_streak'] = 0
    else:
        des_gain = max_desire_c_gain + (5 if sensory_hit else 0) + service_desire_bonus
        if keepsakes_added and any(k.get('method') == 'stolen' for k in keepsakes_added):
            des_gain += 10
        if des_gain > 0:
            cur_h_des = min(100, cur_h_des + des_gain)
        elif location_changed and not intl.get('scene_active'):
            cur_h_des = max(0, cur_h_des - 15)
        elif not intl.get('scene_active') and op_code != 'keepsake_action':
            if int(elapsed_hours or 0) >= 2:
                cur_h_des = max(0, cur_h_des - min(30, int(elapsed_hours) * 5))
            elif category == 'A':
                cur_h_des = max(0, cur_h_des - 6)

        # 亲密进行态按档位温和消耗独立耐力（与日间体力彻底解耦）
        if intl.get('scene_active') or was_scene_active or triggered_intimate:
            tier_v_drain = int(vc.get(str(category or 'A'), 2) or 2)
            cur_h_vig = max(0, cur_h_vig - tier_v_drain)
        elif int(elapsed_hours or 0) > 0:
            cur_h_vig = min(100, cur_h_vig + int(elapsed_hours) * 8)

        if adrenaline_vigor:
            cur_h_vig = min(100, cur_h_vig + 25)

        if host_released:
            if cur_h_des >= 85 and climax_hit:
                synced_climax = True
            rel_cost = int(charm_info.get('release_vigor_cost', vc.get('release', 12)))
            cur_h_vig = max(0, cur_h_vig - rel_cost)
            cur_h_des = 20 if intl.get('scene_active') else 10
            hp['release_count'] = int(hp.get('release_count', 0) or 0) + 1
            hp['edging_streak'] = 0
        elif cur_h_des >= 85:
            next_edge = min(20, int(hp.get('edging_streak', 0) or 0) + 1)
            hp['edging_streak'] = next_edge
            # 极限控场（连续 >=3 轮蓄满边缘）：强控压迫伴随耐力焦灼，每轮额外 -2 耐力
            if next_edge >= 3:
                cur_h_vig = max(0, cur_h_vig - 2)
        else:
            hp['edging_streak'] = 0

        hp['desire'] = max(0, min(100, cur_h_des))
        hp['vigor'] = max(0, min(100, cur_h_vig))

    hp['fetishes'] = derive_host_fetishes(bd, ks_list)

    # 5.6 魅力增减平衡结算：
    # - 增长防刷：部位首破 Lv.2/3（不可重复里程碑）或 同频共振绝顶（每场亲密会话限 1 次），与 HOST_16 合并单轮严格 <= +1，上限 100；
    # - 合理消减（保底 60、单轮封顶 -2）：被徐承邺当场目击/实锤(-2)、女主严重耻感反弹/苏醒反噬(-1)、力竭累倒(-1)、
    #   或对高羞耻低堕落女主过早亮出偷藏贴身物遭反感(-1)。
    charm_milestone_gain = 0
    already_gained_charm = bool(charm_gained_this_turn or (_event_tag('HOST_16') in host_ev))
    sync_charm_eligible = bool(synced_climax and not intl.get('session_charm_gained'))
    if (dev_milestones or sync_charm_eligible) and eff_charm < 100 and not already_gained_charm:
        charm_milestone_gain = 1
        if sync_charm_eligible:
            intl['session_charm_gained'] = True

    charm_penalty = 0
    charm_penalty_reasons = []
    if vig_caught_hit:
        charm_penalty += 2
        charm_penalty_reasons.append('目击实锤失态')
    if shame_backlash_hit:
        charm_penalty += 1
        charm_penalty_reasons.append('防线反噬失控')
    if sleep_kind == 'collapse':
        charm_penalty += 1
        charm_penalty_reasons.append('体能透支累倒')
    if op_code == 'keepsake_action' and (operation or {}).get('action_type') == 'confront':
        ks_id = str((operation or {}).get('keepsake_id') or '').strip()
        ks_obj = next((k for k in ks_list if isinstance(k, dict) and k.get('id') == ks_id), None)
        owner = (ks_obj or {}).get('owner', '')
        owner_p = (state.get('panels') or {}).get(owner) or {}
        if owner in save_store.HEROINES and int(owner_p.get('羞耻', 100) or 0) >= 75 and int(owner_p.get('堕落', 0) or 0) < 15:
            charm_penalty += 1
            charm_penalty_reasons.append('过早亮出私藏遭反感')
    charm_penalty = min(2, charm_penalty)

    host_panel = state.setdefault('panels', {}).setdefault('系统宿主', {})
    cur_charm_panel = int(host_panel.get('魅力', eff_charm) or eff_charm)
    net_charm_delta = charm_milestone_gain - charm_penalty
    if net_charm_delta > 0:
        host_panel['魅力'] = min(100, cur_charm_panel + net_charm_delta)
    elif net_charm_delta < 0:
        floor_c = min(cur_charm_panel, 60)
        host_panel['魅力'] = max(floor_c, cur_charm_panel + net_charm_delta)

    # 5.7 高光互动里程碑经济红利（部位首破 Lv.1/2/3、同频绝顶每场限1次、全新贴身珍藏单轮限1件）
    econ_pts_bonus = 0
    econ_exp_bonus = 0
    economy_notes = []
    for dm in dev_econ_milestones:
        rew = BODY_DEV_ECON_REWARDS.get(int(dm.get('level') or 0))
        if rew:
            p_add, e_add = rew
            econ_pts_bonus += p_add
            econ_exp_bonus += e_add
            economy_notes.append(
                f"{dm['heroine']} {dm['label']}首破 Lv.{dm['level']}（积分+{p_add}、经验+{e_add}）"
            )
    if synced_climax and not intl.get('session_econ_climax_paid'):
        intl['session_econ_climax_paid'] = True
        p_add, e_add = SYNCED_CLIMAX_ECON_REWARD
        econ_pts_bonus += p_add
        econ_exp_bonus += e_add
        economy_notes.append(f"达成同频绝顶（积分+{p_add}、经验+{e_add}）")
    if new_keepsakes_created:
        ks0 = new_keepsakes_created[0]
        p_add, e_add = KEEPSAKE_NEW_ECON_REWARD
        econ_pts_bonus += p_add
        econ_exp_bonus += e_add
        owner_p = f"{ks0.get('owner', '')} · " if ks0.get('owner') else ''
        economy_notes.append(f"首次珍藏 {owner_p}「{ks0.get('name', '')}」（积分+{p_add}、经验+{e_add}）")
    if econ_pts_bonus > 0 or econ_exp_bonus > 0:
        host_panel['积分'] = int(host_panel.get('积分', 0) or 0) + econ_pts_bonus
        host_panel['经验值'] = int(host_panel.get('经验值', 0) or 0) + econ_exp_bonus

    # 6. 隔墙/同席潜行声响暴露风险与同栋楼女主疑心联动
    stealth_alert = False
    if intl.get('privacy') in ('thin_wall', 'under_cover'):
        noise_add = (35 if climax_hit else 0) + max_shame_noise
        if noise_add > 0:
            intl['noise_risk'] = min(100, int(intl.get('noise_risk', 0) or 0) + noise_add)
        else:
            intl['noise_risk'] = max(0, int(intl.get('noise_risk', 0) or 0) - 10)
        if intl['noise_risk'] >= 60:
            stealth_alert = True
            present_set = set(intl.get('present_actors') or (active_cast or ()))
            offroom_heroines = [h for h in (building_cast or ()) if h in save_store.HEROINES and h not in present_set]
            inroom_heroines = [h for h in present_set if h in save_store.HEROINES]
            ih = intl.setdefault('inter_heroine', {p: 0 for p in save_store.INTER_HEROINE_PAIRS})
            for listener in offroom_heroines:
                for target in inroom_heroines:
                    pair = f'{listener}->{target}'
                    if pair in ih and ih[pair] < 2:
                        ih[pair] = min(2, ih[pair] + 1)
    else:
        intl['noise_risk'] = max(0, int(intl.get('noise_risk', 0) or 0) - 15)

    high_risk_devices = [
        {'id': d.get('id'), 'name': d.get('name'), 'location': d.get('location'), 'spot': d.get('spot'), 'detected_risk': int(d.get('detected_risk') or 0)}
        for d in (state.get('items', {}).get('deployed') or [])
        if isinstance(d, dict) and int(d.get('detected_risk') or 0) >= 60
    ]
    return {
        'stealth_alert': stealth_alert,
        'high_risk_devices': high_risk_devices,
        'dev_milestones': dev_milestones,
        'synced_climax': synced_climax,
        'charm_milestone_gain': charm_milestone_gain,
        'charm_penalty': charm_penalty,
        'charm_penalty_reasons': charm_penalty_reasons,
        'keepsakes_added': keepsakes_added,
        'body_acts_used': resolved_body_acts,
        'economy_notes': economy_notes,
        'economy_bonus': {'pts': econ_pts_bonus, 'exp': econ_exp_bonus},
    }


def execute_injection(current_round, story_nodes, memory_deltas, panel_changes,
                      npc_entries=None, item_entries=None,
                      system_log="", options_text="", micro_state_changes=None,
                      shame_events=None, depravity_events=None, ds_events=None,
                      affection_events=None, host_events=None, presence_changes=None,
                      counter_updates=None, vigilance_events=None, task_issue=None,
                      *, request_id=None, base_revision=None, allow_panel_override=False):
    """兼容原Python入口，统一交由固定执行器校验、去重和可恢复提交。"""
    from round_runtime import submit_legacy
    body = {
        "current_round": current_round, "story_nodes": story_nodes,
        "memory_deltas": memory_deltas, "panel_changes": panel_changes,
        "npc_entries": [] if npc_entries is None else npc_entries,
        "item_entries": [] if item_entries is None else item_entries,
        "system_log": system_log, "options_text": options_text,
        "micro_state_changes": {} if micro_state_changes is None else micro_state_changes,
        "shame_events": {} if shame_events is None else shame_events,
        "depravity_events": {} if depravity_events is None else depravity_events,
        "ds_events": {} if ds_events is None else ds_events,
        "affection_events": {} if affection_events is None else affection_events,
        "host_events": [] if host_events is None else host_events,
        "presence_changes": {} if presence_changes is None else presence_changes,
        "counter_updates": {} if counter_updates is None else counter_updates,
        "vigilance_events": {} if vigilance_events is None else vigilance_events,
        "task_issue": task_issue,
    }
    receipt = submit_legacy(BASE_DIR, body, request_id=request_id,
                            base_revision=base_revision,
                            allow_panel_override=allow_panel_override)
    status = "已提交，重复请求未再结算" if receipt["replayed"] else "提交完成"
    print(f" [回合 {current_round}] {status}；状态版本 {receipt['state_version']}")
    return receipt

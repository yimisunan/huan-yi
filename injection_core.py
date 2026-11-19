# injection_core.py
# 一键注入系统永久核心（模块化后只维护此文件）
# 【纯本地注入架构升级版】接管日志物理写入与前端选项原生挂载
# 迭代历史见开发者功能/修订日志/

import os
import json
import re
import time
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "存档")
MEMORY_FILE = os.path.join(DATA_DIR, "全局记忆库.txt")
NPC_ROSTER_FILE = os.path.join(DATA_DIR, "次要NPC名册.txt")
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


def process_host_system(host_events, shame_events, memory_file):
    """
    宿主核心引擎：三轨竞标结算与动态体力代偿
    """
    if not host_events and not shame_events:
        return {}
    if not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    match_host = re.search(r"\[系统宿主\].*?积分\s*(-?\d+).*?经验值\s*(-?\d+).*?体力\s*(-?\d+).*?商业嗅觉\s*(-?\d+)", content)
    if not match_host:
        return {}
        
    cur_pts = int(match_host.group(1))
    cur_exp = int(match_host.group(2))
    cur_sta = int(match_host.group(3))
    cur_biz = int(match_host.group(4))
    
    # 1. 三轨竞标计算
    track1 = {"pts": 0, "exp": 0, "biz": 0, "name": "堕落侵蚀"}
    track2 = {"pts": 0, "exp": 0, "biz": 0, "name": "日常温馨"}
    track3 = {"pts": 0, "exp": 0, "biz": 0, "name": "商业权力"}
    
    if host_events:
        for tag in host_events:
            if tag == _event_tag('HOST_01'): track1["pts"] += _event_param('HOST_01', 'track1_pts_01'); track1["exp"] += _event_param('HOST_01', 'track1_exp_02')
            elif tag == _event_tag('HOST_02'): track1["pts"] += _event_param('HOST_02', 'track1_pts_01'); track1["exp"] += _event_param('HOST_02', 'track1_exp_02')
            elif tag == _event_tag('HOST_03'): track1["pts"] += _event_param('HOST_03', 'track1_pts_01'); track1["exp"] += _event_param('HOST_03', 'track1_exp_02')
            elif tag == _event_tag('HOST_04'): track1["pts"] += _event_param('HOST_04', 'track1_pts_01'); track1["exp"] += _event_param('HOST_04', 'track1_exp_02')
            elif tag == _event_tag('HOST_05'): track2["pts"] += _event_param('HOST_05', 'track2_pts_01'); track2["exp"] += _event_param('HOST_05', 'track2_exp_02')
            elif tag == _event_tag('HOST_06'): track2["pts"] += _event_param('HOST_06', 'track2_pts_01'); track2["exp"] += _event_param('HOST_06', 'track2_exp_02')
            elif tag == _event_tag('HOST_07'): track2["pts"] += _event_param('HOST_07', 'track2_pts_01'); track2["exp"] += _event_param('HOST_07', 'track2_exp_02')
            elif tag == _event_tag('HOST_08'): track2["pts"] += _event_param('HOST_08', 'track2_pts_01')
            elif tag == _event_tag('HOST_09'): track3["pts"] += _event_param('HOST_09', 'track3_pts_01'); track3["exp"] += _event_param('HOST_09', 'track3_exp_02'); track3["biz"] += _event_param('HOST_09', 'track3_biz_03')
            elif tag == _event_tag('HOST_10'): track3["pts"] += _event_param('HOST_10', 'track3_pts_01'); track3["exp"] += _event_param('HOST_10', 'track3_exp_02'); track3["biz"] += _event_param('HOST_10', 'track3_biz_03')
            elif tag == _event_tag('HOST_11'): track3["pts"] += _event_param('HOST_11', 'track3_pts_01'); track3["exp"] += _event_param('HOST_11', 'track3_exp_02'); track3["biz"] += _event_param('HOST_11', 'track3_biz_03')

    tracks = [track1, track2, track3]
    best_track = max(tracks, key=lambda t: t["pts"])
    
    if best_track["pts"] > 0:
        cur_pts += best_track["pts"]
        cur_exp += best_track["exp"]
        cur_biz += best_track["biz"]
        print(f" 🏆 [宿主引擎] 三轨结算：【{best_track['name']}】路线胜出！积分+{best_track['pts']} 经验+{best_track['exp']}")
        if best_track["biz"] > 0:
            print(f" 📈 [宿主引擎] 商业嗅觉同步提升 +{best_track['biz']}")

    # 2. 商城动态扣费与宿主体力结算
    if host_events:
        for tag in host_events:
            if tag.startswith(_event_tag('HOST_12')[:-1]):
                try:
                    cost = int(tag.split("_")[1])
                    cur_pts -= cost
                    print(f" 🛒 [宿主引擎] 商城兑换，扣除 {cost} 积分。")
                except:
                    pass
            elif tag == _event_tag('HOST_13'): cur_sta -= _event_param('HOST_13', 'cur_sta_01')
            elif tag == _event_tag('HOST_14'): cur_sta -= _event_param('HOST_14', 'cur_sta_01')
            elif tag == _event_tag('HOST_15'): cur_sta = _event_param('HOST_15', 'cur_sta_01')
            
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
    
    return {
        "积分": cur_pts,
        "经验值": cur_exp,
        "体力": cur_sta,
        "商业嗅觉": cur_biz
    }

def process_shame_system(shame_events, memory_file):
    """
    语义化规则包：羞耻系统后台自动化物理计算引擎
    将 AI 前端的打标（如 'C烈度_轻度', '首次', '内射_首次核爆' 等）转换为绝对数值计算，
    支持堕落乘数、首杀附加、同质化免疫与极限夹紧，直接返回算完的最新面板数值。
    """
    if not shame_events or not os.path.exists(memory_file):
        return {}
    
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    computed_shame_changes = {}
    
    for char_name, tags in shame_events.items() if shame_events else []:
        if not tags or not isinstance(tags, list):
            continue
        
        # 从当前记忆库中正则读取该角色当前的 羞耻 与 堕落 数值
        shame_match = re.search(rf"\[{re.escape(char_name)}\].*?羞耻\s*(-?\d+)", content)
        depravity_match = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(-?\d+)", content)
        
        if not shame_match:
            continue
        
        current_shame = int(shame_match.group(1))
        current_depravity = int(depravity_match.group(1)) if depravity_match else 0
        
        # 1. 状态锁与极值判定
        if _event_tag('SHAME_10') in tags:
            computed_shame_changes[char_name] = _event_param('SHAME_10', 'computed_shame_changes_char_name_01')
            print(f" [羞耻引擎] {char_name} 触发【确诊怀孕】，羞耻度强制清零。")
            continue
            
        if _event_tag('SHAME_11') in tags or _event_tag('SHAME_12') in tags or _event_tag('SHAME_13') in tags:
            print(f" [羞耻引擎] {char_name} 处于冻结/死寂/解离锁状态，当回合羞耻停止下降。")
            continue
            
        if _event_tag('SHAME_14') in tags:
            rebound_val = current_shame + _event_param('SHAME_14', 'rebound_val_01')
            rebound_val = min(_event_param('SHAME_14', 'rebound_val_02'), max(_event_param('SHAME_14', 'rebound_val_03'), rebound_val))
            computed_shame_changes[char_name] = rebound_val
            print(f" [羞耻引擎] {char_name} 触发【耻感反弹_苏醒】，羞耻度回升至 {rebound_val}。")
            continue
            
        # 2. 基础衰减分值计算
        base_delta = 0
        is_first = _event_tag('SHAME_17') in tags
        
        for tag in tags:
            # A/B烈度零羞耻：日常/礼仪接触(孝心按摩、握手、扶肩等)不触发羞耻判定；
            # 羞耻只由越界/性意味接触(C烈度及以上)与特殊事件触发，按意图与语境而非接触部位判定。
            if tag == _event_tag('SHAME_01'): base_delta -= _event_param('SHAME_01', 'base_delta_01')
            elif tag == _event_tag('SHAME_02'): base_delta -= (_event_param('SHAME_02', 'base_delta_01') if is_first else _event_param('SHAME_02', 'base_delta_02'))
            elif tag == _event_tag('SHAME_03'): base_delta -= (_event_param('SHAME_03', 'base_delta_01') if is_first else _event_param('SHAME_03', 'base_delta_02'))
            elif tag == _event_tag('SHAME_04'): base_delta -= (_event_param('SHAME_04', 'base_delta_01') if is_first else _event_param('SHAME_04', 'base_delta_02'))
            elif tag == _event_tag('SHAME_05'): base_delta -= _event_param('SHAME_05', 'base_delta_01')
            elif tag == _event_tag('SHAME_06'): base_delta -= _event_param('SHAME_06', 'base_delta_01')
            elif tag == _event_tag('SHAME_07'): base_delta -= _event_param('SHAME_07', 'base_delta_01')
            elif tag == _event_tag('SHAME_08'): base_delta -= _event_param('SHAME_08', 'base_delta_01')
            elif tag == _event_tag('SHAME_09'): base_delta -= _event_param('SHAME_09', 'base_delta_01')
            
        if base_delta == 0:
            continue
            
        # 3. 堕落乘数 (堕落>60时，降幅 × 1.5)
        if current_depravity > 60 and base_delta < 0:
            base_delta = int(round(base_delta * 1.5))
            
        # 4. 同质化免疫折扣
        if _event_tag('SHAME_15') in tags:
            base_delta = int(round(base_delta * _event_param('SHAME_15', 'base_delta_01')))
        elif _event_tag('SHAME_16') in tags:
            base_delta = _event_param('SHAME_16', 'base_delta_01')
            
        # 5. 计算最终羞耻并安全夹紧 (Clamping 0-100)
        new_shame = current_shame + base_delta
        new_shame = min(100, max(0, new_shame))
        computed_shame_changes[char_name] = new_shame
        print(f" [羞耻引擎] {char_name} 语义标签 {tags} 自动演算：羞耻 {current_shame} -> {new_shame} (净负动: {base_delta})")
        
    return computed_shame_changes


def process_depravity_system(depravity_events, memory_file):
    """
    语义化规则包：堕落系统后台自动化物理计算引擎
    处理堕落值的常规增加，并严格执行 30/60/90 阶梯锁死机制。
    只有接收到特定的主动破锁标签，才能跨越极值屏障。
    """
    if not depravity_events or not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    computed_changes = {}
    
    for char_name, tags in depravity_events.items() if depravity_events else []:
        if not tags or not isinstance(tags, list):
            continue
            
        match = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(\d+)", content)
        if not match:
            continue
            
        current_dep = int(match.group(1))
        base_delta = 0
        unlocked_threshold = None
        
        for tag in tags:
            if tag == _event_tag('DEPRAVITY_01'): base_delta += _event_param('DEPRAVITY_01', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_02'): base_delta += _event_param('DEPRAVITY_02', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_03'): base_delta += _event_param('DEPRAVITY_03', 'base_delta_01')
            elif tag == _event_tag('DEPRAVITY_04'):
                base_delta += _event_param('DEPRAVITY_04', 'base_delta_01')
                unlocked_threshold = _event_param('DEPRAVITY_04', 'unlocked_threshold_02')
            elif tag == _event_tag('DEPRAVITY_05'):
                base_delta += _event_param('DEPRAVITY_05', 'base_delta_01')
                unlocked_threshold = _event_param('DEPRAVITY_05', 'unlocked_threshold_02')
            elif tag == _event_tag('DEPRAVITY_06'):
                base_delta += _event_param('DEPRAVITY_06', 'base_delta_01')
                unlocked_threshold = _event_param('DEPRAVITY_06', 'unlocked_threshold_02')
                
        if base_delta == 0:
            continue
            
        new_dep = current_dep + base_delta
        
        # 阶梯死锁核心逻辑 (Clamping thresholds)
        cap = 100
        if unlocked_threshold == 30: cap = 60
        elif unlocked_threshold == 60: cap = 90
        elif unlocked_threshold == 90: cap = 100
        else:
            if current_dep < 30: cap = 30
            elif current_dep == 30: cap = 30
            elif current_dep < 60: cap = 60
            elif current_dep == 60: cap = 60
            elif current_dep < 90: cap = 90
            elif current_dep == 90: cap = 90
            
        if new_dep > cap:
            new_dep = cap
            print(f" [堕落引擎] {char_name} 触及 {cap} 阶梯死锁阈值（未检测到破锁标签），数值已被强制拦截。")
            
        new_dep = min(100, max(0, new_dep))
        computed_changes[char_name] = new_dep
        print(f" [堕落引擎] {char_name} 语义标签 {tags} 自动演算：堕落 {current_dep} -> {new_dep}")
        
    return computed_changes


def process_desire_stamina_system(ds_events, memory_file):
    """
    语义化规则包：生理体力与欲望高潮后台计算引擎
    接管欲望自然渗漏、刺激上限(80)、临界突破(100)、体力消耗与自动高潮清算。
    """
    if not ds_events or not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    computed_changes = {}
    
    for char_name, tags in ds_events.items() if ds_events else []:
        if not isinstance(tags, list):
            continue
            
        match_aff = re.search(rf"\[{re.escape(char_name)}\].*?好感\s*(-?\d+)", content)
        match_shame = re.search(rf"\[{re.escape(char_name)}\].*?羞耻\s*(-?\d+)", content)
        match_des = re.search(rf"\[{re.escape(char_name)}\].*?欲望\s*(-?\d+)", content)
        match_sta = re.search(rf"\[{re.escape(char_name)}\].*?体力\s*(-?\d+)", content)
        match_org = re.search(rf"\[{re.escape(char_name)}\].*?高潮\s*(\d+)", content)
        
        if not (match_aff and match_shame and match_des and match_sta):
            continue
            
        cur_aff = int(match_aff.group(1))
        cur_shame = int(match_shame.group(1))
        cur_des = int(match_des.group(1))
        cur_sta = int(match_sta.group(1))
        cur_org = int(match_org.group(1)) if match_org else 0
        
        new_des = cur_des
        new_sta = cur_sta
        new_org = cur_org
        
        # 1. 引擎底层被动：好感渗漏机制
        if cur_shame < 40 and cur_aff > 75:
            new_des += 3
            print(f" [欲望引擎] {char_name} 触发【好感渗漏】，欲望底层暗流自动 +3。")
            
        # 2. 标签解析
        sensory_visual = 0
        sensory_smell = 0
        sensory_audio = 0
        
        for tag in tags:
            # 欲望
            if tag == _event_tag('DS_01'): sensory_visual = _event_param('DS_01', 'sensory_visual_01')
            elif tag == _event_tag('DS_02'): sensory_smell = _event_param('DS_02', 'sensory_smell_01')
            elif tag == _event_tag('DS_03'): sensory_audio = _event_param('DS_03', 'sensory_audio_01')
            elif tag == _event_tag('DS_04'): new_des += _event_param('DS_04', 'new_des_01')
            elif tag == _event_tag('DS_05'): new_des -= _event_param('DS_05', 'new_des_01')
            # 体力
            elif tag == _event_tag('DS_08'): new_sta -= _event_param('DS_08', 'new_sta_01')
            elif tag == _event_tag('DS_09'): new_sta -= _event_param('DS_09', 'new_sta_01')
            elif tag == _event_tag('DS_10'): new_sta -= _event_param('DS_10', 'new_sta_01')
            elif tag == _event_tag('DS_11'): new_sta -= _event_param('DS_11', 'new_sta_01')
            elif tag == _event_tag('DS_12'): new_sta += _event_param('DS_12', 'new_sta_01')
            elif tag == _event_tag('DS_13'): new_sta += _event_param('DS_13', 'new_sta_01')
            # 高潮
            elif tag == _event_tag('DS_14'): new_org += _event_param('DS_14', 'new_org_01')
            elif tag == _event_tag('DS_15'): new_org += _event_param('DS_15', 'new_org_01')
            elif tag == _event_tag('DS_16'): new_org += _event_param('DS_16', 'new_org_01')
            
        # 3. 感官刺激取最高值（交感神经冲突时视觉屏蔽）
        if cur_shame > 80:
            sensory_visual = 0
        sensory_add = max(sensory_visual, sensory_smell, sensory_audio)
        new_des += sensory_add
        
        # 4. 物理刺激上限拦截 (80) 与 临界突破 (100)
        if new_des > 80 and cur_des <= 80:
            if _event_tag('DS_06') in tags or _event_tag('DS_07') in tags:
                new_des = _event_param('DS_06', 'new_des_01')
                print(f" [欲望引擎] {char_name} 触发【临界突破】，欲望强行贯穿 80 阈值直达 100！")
            else:
                new_des = 80
                print(f" [欲望引擎] {char_name} 欲望被拦截在 80（物理刺激上限，需特定临界突破）。")
                
        # 5. 特殊状态锁 (结合前端标签与记忆库持久化BUFF自动判定)
        has_semen_lock = bool(re.search(rf"▶\s*{re.escape(char_name)}\s*\n(?:(?!▶).)*?\[持续_体液锁定\]", content, re.DOTALL))
        if "持续_体液锁定" in tags or has_semen_lock:
            new_des = max(85, new_des)
            print(f" [欲望引擎] 🔒 {char_name} 处于/触发【体液锁定】，欲望被强制钳制在不低于 85。")
            
        # 6. 高潮核爆清算
        if _event_tag('DS_17') in tags or new_org >= _event_param('DS_17', 'new_org_01'):
            new_org = _event_param('DS_17', 'new_org_02')
            new_des = _event_param('DS_17', 'new_des_03')
            new_sta += _event_param('DS_17', 'new_sta_04')  # 扣除15消耗，叠加30肾上腺素奖励的净值
            print(f" [生理引擎] 💥 {char_name} 触发【高潮清算】，高潮归零，欲望回落 35，结算肾上腺素。")
            
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


def process_affection_system(affection_events, shame_events, memory_file):
    """
    语义化规则包：好感度畸变与阻滞计算引擎
    监听 SHAME_EVENTS 中的越界行为，结合当前面板实现自动掉分与合理化闭环。
    处理苏婉青的 85 分背德天花板锁死。
    """
    if not affection_events and not shame_events:
        return {}
    if not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    computed_changes = {}
    
    # 只要在好感字典或羞耻字典里出现的角色，统统拉出来接受结算
    all_chars = set(affection_events.keys() if affection_events else []).union(
                set(shame_events.keys() if shame_events else []))
                
    for char_name in all_chars:
        match_aff = re.search(rf"\[{re.escape(char_name)}\].*?好感\s*(-?\d+)", content)
        match_shame = re.search(rf"\[{re.escape(char_name)}\].*?羞耻\s*(-?\d+)", content)
        
        if not (match_aff and match_shame):
            continue
            
        cur_aff = int(match_aff.group(1))
        cur_shame = int(match_shame.group(1))
        new_aff = cur_aff
        
        a_tags = affection_events.get(char_name, []) if affection_events else []
        s_tags = shame_events.get(char_name, []) if shame_events else []
        if not isinstance(a_tags, list): a_tags = []
        if not isinstance(s_tags, list): s_tags = []
        
        # 1. 越界联动下降机制 (跨模块监听 SHAME_EVENTS)
        violation_drop = 0
        if _event_tag('SHAME_04') in s_tags:
            if cur_aff > _event_param('SHAME_04', 'cur_aff_03'): violation_drop -= _event_param('SHAME_04', 'violation_drop_05') if cur_shame < _event_param('SHAME_04', 'cur_shame_04') else _event_param('SHAME_04', 'violation_drop_06')
            elif cur_aff >= _event_param('SHAME_04', 'cur_aff_07'): violation_drop -= _event_param('SHAME_04', 'violation_drop_08')
            else: violation_drop -= _event_param('SHAME_04', 'violation_drop_09')
        elif _event_tag('SHAME_02') in s_tags:
            if cur_aff > _event_param('SHAME_02', 'cur_aff_03'): violation_drop -= _event_param('SHAME_02', 'violation_drop_05') if cur_shame < _event_param('SHAME_02', 'cur_shame_04') else _event_param('SHAME_02', 'violation_drop_06')
            elif cur_aff >= _event_param('SHAME_02', 'cur_aff_07'): violation_drop -= _event_param('SHAME_02', 'violation_drop_08')
            else: violation_drop -= _event_param('SHAME_02', 'violation_drop_09')
        elif _event_tag('SHAME_01') in s_tags:
            if cur_aff > _event_param('SHAME_01', 'cur_aff_02'): violation_drop -= _event_param('SHAME_01', 'violation_drop_04') if cur_shame < _event_param('SHAME_01', 'cur_shame_03') else _event_param('SHAME_01', 'violation_drop_05')
            elif cur_aff >= _event_param('SHAME_01', 'cur_aff_06'): violation_drop -= _event_param('SHAME_01', 'violation_drop_07')
            else: violation_drop -= _event_param('SHAME_01', 'violation_drop_08')
            
        if violation_drop == _event_param('SHAME_04', 'violation_drop_10') and (_event_tag('SHAME_04') in s_tags or _event_tag('SHAME_02') in s_tags or _event_tag('SHAME_01') in s_tags):
            print(f" [好感引擎] 💖 {char_name} 触发【合理化闭环】！好感与羞耻达标，潜意识自我保护启动，未造成好感下降。")
            
        new_aff += violation_drop
        
        # 2. 手动标签结算
        for tag in a_tags:
            if tag == _event_tag('AFFECTION_01'): new_aff -= _event_param('AFFECTION_01', 'new_aff_01')
            elif tag == _event_tag('AFFECTION_02'): new_aff -= _event_param('AFFECTION_02', 'new_aff_01')
            elif tag == _event_tag('AFFECTION_03'): new_aff += (_event_param('AFFECTION_03', 'new_aff_02') if cur_aff < _event_param('AFFECTION_03', 'cur_aff_01') else _event_param('AFFECTION_03', 'new_aff_03'))
            elif tag == _event_tag('AFFECTION_04'): new_aff += (_event_param('AFFECTION_04', 'new_aff_02') if cur_shame <= _event_param('AFFECTION_04', 'cur_shame_01') else _event_param('AFFECTION_04', 'new_aff_03'))
            elif tag == _event_tag('AFFECTION_05'): new_aff += _event_param('AFFECTION_05', 'new_aff_01')
            elif tag == _event_tag('AFFECTION_06'): new_aff += (_event_param('AFFECTION_06', 'new_aff_02') if cur_aff < _event_param('AFFECTION_06', 'cur_aff_01') else _event_param('AFFECTION_06', 'new_aff_03'))
            elif tag == _event_tag('AFFECTION_07'): new_aff += _event_param('AFFECTION_07', 'new_aff_01')
            
        # 3. 专属阻力锁：苏婉青的背德天花板
        cap = 100
        if char_name == "苏婉青":
            cap = 85
            if _event_tag('AFFECTION_08') in a_tags or _event_tag('AFFECTION_09') in a_tags or cur_aff > _event_param('AFFECTION_08', 'cur_aff_01'):
                cap = _event_param('AFFECTION_08', 'cap_02')
                if _event_tag('AFFECTION_08') in a_tags or _event_tag('AFFECTION_09') in a_tags:
                    print(f" [好感引擎] 🔓 苏婉青触发【背德天花板解锁】，好感上限突破至 95！")
                    
        if new_aff > cap:
            new_aff = cap
            print(f" [好感引擎] {char_name} 触及好感天花板 ({cap})，数值已被拦截。")
            
        new_aff = min(100, max(0, new_aff))
        
        if new_aff != cur_aff:
            computed_changes[char_name] = new_aff
            print(f" [好感引擎] {char_name} 自动演算：好感 {cur_aff} -> {new_aff}")
            
    return computed_changes



def process_pregnancy_rng(shame_events, memory_file):
    """
    命运引擎：真·随机数受孕判定
    接管内射后的受孕概率结算，绝对冷血，杜绝AI前台剧透。
    """
    if not shame_events or not os.path.exists(memory_file):
        return {}
        
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    computed_preg = {}
    
    for char_name, tags in shame_events.items() if shame_events else []:
        if not tags or not isinstance(tags, list): continue
        if _event_tag('SHAME_06') not in tags and _event_tag('SHAME_07') not in tags:
            continue
            
        match_preg = re.search(rf"\[{re.escape(char_name)}\].*?怀孕\s*(True|False)", content)
        if match_preg and match_preg.group(1) == "True":
            continue # 已孕，无需再投骰子
            
        match_dep = re.search(rf"\[{re.escape(char_name)}\].*?堕落\s*(\d+)", content)
        match_org = re.search(rf"\[{re.escape(char_name)}\].*?高潮\s*(\d+)", content)
        
        cur_dep = int(match_dep.group(1)) if match_dep else 0
        cur_org = int(match_org.group(1)) if match_org else 0
        
        # 计算动态概率
        prob = 10
        if cur_dep > 80 or cur_org >= 100:
            prob = 40
            
        if _event_tag('SHAME_18') in tags:
            prob *= _event_param('SHAME_18', 'prob_01')
            
        prob = min(100, prob)
        roll = random.randint(1, 100)
        
        print(f" 🎲 [命运引擎] {char_name} 触发内射！高潮:{cur_org}% 堕落:{cur_dep} | 受孕概率: {prob}% | 命运暗骰: {roll}")
        
        if roll <= prob:
            print(f" 🚨🚨 [命运引擎] 致命命中！{char_name} 确诊受孕！抵抗意志即将被彻底抹杀！🚨🚨")
            computed_preg[char_name] = "True"
        else:
            print(f" 💨 [命运引擎] 未命中。{char_name} 逃过一劫。")
            
    return computed_preg



def update_persistent_buffs(memory_file, shame_events, new_buffs_dict=None):
    """
    后台持久化状态与BUFF管理器
    处理内射自动体液锁定、前台AI手动挂载新BUFF请求，以及全局倒计时扣减。
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
    
    # 1.5 前台 AI 手动挂载的新 BUFF（道具或特殊剧情触发）
    if new_buffs_dict:
        for char, buff_str in new_buffs_dict.items():
            if buff_str:
                char_pattern = rf"(▶\s*{re.escape(char)}\s*\n)(.*?)(?=\n▶|\n$)"
                match_char = re.search(char_pattern, buff_block, re.DOTALL)
                if match_char:
                    old_buffs = match_char.group(2).strip()
                    if "无" in old_buffs or not old_buffs:
                        new_buffs = f"  - {buff_str}"
                    else:
                        new_buffs = old_buffs + "\n" + f"  - {buff_str}"
                    buff_block = re.sub(char_pattern, rf"\g<1>{new_buffs}\n", buff_block, flags=re.DOTALL)
                    print(f" 💉 [持久化引擎] 收到前台请求，已为 {char} 挂载新 BUFF：{buff_str}")

    # 2. 如果当回合发生内射，后台自动为其追加 24回合 的体液锁定 BUFF
    if shame_events:
        for char, tags in shame_events.items():
            if _event_tag('SHAME_06') in tags or _event_tag('SHAME_07') in tags:
                semen_str = "  - [持续_体液锁定] 剩余时效: 24回合 (效果: 欲望死锁不低于85)"
                char_pattern = rf"(▶\s*{re.escape(char)}\s*\n)(.*?)(?=\n▶|\n$)"
                match_char = re.search(char_pattern, buff_block, re.DOTALL)
                if match_char:
                    old_buffs = match_char.group(2).strip()
                    if "无" in old_buffs or not old_buffs:
                        new_buffs = semen_str
                    elif "[持续_体液锁定]" in old_buffs:
                        # 已有则重置时间为 24回合
                        new_buffs = re.sub(r"\[持续_体液锁定\] 剩余时效:\s*\d+回合", "[持续_体液锁定] 剩余时效: 24回合", old_buffs)
                    else:
                        new_buffs = old_buffs + "\n" + semen_str
                    buff_block = re.sub(char_pattern, rf"\g<1>{new_buffs}\n", buff_block, flags=re.DOTALL)
                    print(f" 💉 [持久化引擎] 监听到内射事件，已自动为 {char} 挂载 [持续_体液锁定: 24回合] BUFF！")

    # 3. 遍历所有带“剩余时效: X回合”的BUFF进行倒计时 -1
    def decrement_timer(match):
        buff_name = match.group(1)
        turns = int(match.group(2)) - 1
        effect = match.group(3)
        if turns <= 0:
            print(f" ⌛ [持久化引擎] BUFF [{buff_name}] 时效已尽，后台自动移除！")
            return "" # 归零移除
        return f"- [{buff_name}] 剩余时效: {turns}回合 ({effect})"

    buff_block = re.sub(r"-\s*\[(.*?)\]\s*剩余时效:\s*(\d+)回合\s*\((.*?)\)", decrement_timer, buff_block)

    # 4. 清理空行并确保没有BUFF的角色显示“- 无”
    lines = buff_block.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        if line.strip().startswith("▶"):
            # 检查下一行是否是有效BUFF
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
    final_buff_block = ""
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


# ============ 徐承邺监视矩阵（警惕值机制） ============
VIGILANCE_TARGETS = ("沈知韫", "苏婉青", "徐念薇", "徐志北")
VIGILANCE_LOCKED_FLOOR = 50  # 目击锁定后警惕下限
VIGILANCE_EXPOSURE_TAGS = ("内射", "高潮", "C烈度", "边缘", "深吻", "亲密")  # 暴露加分触发

# ============ 任务系统（AI生成属性型任务 · 后端判定 · 串行单任务） ============
TASK_WHITELIST = {
    "系统宿主": ["积分", "经验值", "商业嗅觉", "体力"],
    "沈知韫": ["好感"],
    "徐念薇": ["好感"],
    "苏婉青": ["好感"],
}  # 严格白名单：堕落/欲望/羞耻/高潮/怀孕/内射/被动Lv 硬禁（任务化会诱导越界剧情）
TASK_REWARDS = {"small": (15, 8), "medium": (40, 25), "large": (80, 50)}  # (积分, 经验) 固定档位
TASK_HISTORY_LIMIT = 3  # 最近完成保留条数
TASK_BLOCK_ANCHOR = "【任务状态】"


def _parse_vigilance_block(content):
    """解析【监视状态】块 → {'位置':..., '目标':{名:{警惕,发现,发现几率}}}"""
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
            rf"徐承邺_{re.escape(name)}：警惕\s*(\d+)\s*\|\s*发现\s*(\d+)\s*\|\s*发现几率\s*(\d+)",
            block)
        if tm:
            targets[name] = {
                "警惕": int(tm.group(1)),
                "发现": int(tm.group(2)),
                "发现几率": int(tm.group(3)),
            }
    return {"位置": pos, "目标": targets}


def _is_exposed(target, shame_events):
    """目标本回合是否有越界暴露（C烈度/内射/高潮/边缘等 SHAME 标签）"""
    tags = shame_events.get(target) if isinstance(shame_events, dict) else None
    if not tags or not isinstance(tags, list):
        return False
    return any(any(k in t for k in VIGILANCE_EXPOSURE_TAGS) for t in tags)


def _apply_vigilance_tags(vig, events):
    """按语义标签结算警惕/发现程度；目击(发现>=3)后警惕下限锁定、降警惕标签无效"""
    for target, tags in events.items():
        if target not in vig["目标"] or not isinstance(tags, list):
            continue
        t = vig["目标"][target]
        locked = t["发现"] >= 3
        for tag in tags:
            if tag == _event_tag('VIGILANCE_01'):
                t["警惕"] += _event_param('VIGILANCE_01', 't_01')
                t["发现"] = max(t["发现"], _event_param('VIGILANCE_01', 't_02'))
            elif tag == _event_tag('VIGILANCE_02'):
                t["发现"] = max(t["发现"], _event_param('VIGILANCE_02', 't_01'))
            elif tag == _event_tag('VIGILANCE_03'):
                t["警惕"] += _event_param('VIGILANCE_03', 't_01')
                t["发现"] = min(t["发现"] + _event_param('VIGILANCE_03', 't_02'), _event_param('VIGILANCE_03', 't_03'))
            elif tag == _event_tag('VIGILANCE_04'):
                t["警惕"] += _event_param('VIGILANCE_04', 't_01')
                t["发现"] = min(t["发现"] + _event_param('VIGILANCE_04', 't_02'), _event_param('VIGILANCE_04', 't_03'))
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
        t["警惕"] = max(0, t["警惕"])


def _write_vigilance_block(vig):
    """将结算后的监视状态写回【监视状态】块（锚点维护，与 update_counters 同模式）"""
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = "【监视状态】"
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【任务状态】|\n【道具倒计时】|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return
    lines = [anchor, f"徐承邺位置：{vig['位置']}"]
    for name in VIGILANCE_TARGETS:
        t = vig["目标"][name]
        lines.append(f"徐承邺_{name}：警惕 {t['警惕']} | 发现 {t['发现']} | 发现几率 {t['发现几率']}")
    block = "\n".join(lines) + "\n"
    content = content[:m.start(1)] + block + content[m.end(1):]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(" [√] 监视状态块已更新")


def process_vigilance_system(vigilance_events, shame_events, memory_file, *, elapsed_hours=None, roll_home=True):
    """
    徐承邺监视矩阵全自动结算：
    警惕增减 / 发现程度（目击不可逆）/ 回宅掷骰（警惕50档低概率·70档明显提升）/
    发现几率（在场×暴露+警惕加权）。
    每回合常驻执行（即使 AI 未打标签也走时间衰减与回宅判定）。
    """
    if not os.path.exists(memory_file):
        return {}
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    vig = _parse_vigilance_block(content)
    if not vig:
        return {}

    _apply_vigilance_tags(vig, vigilance_events or {})

    # 死亡查岗衔接：查岗未抓实锤 → 该次越界目标警惕 -10（虚惊回落）
    for target, tags in (shame_events or {}).items():
        if target in vig["目标"] and isinstance(tags, list) and _event_tag('SHAME_08') in tags:
            if vig["目标"][target]["发现"] < _event_param('SHAME_08', 'vig_target_02'):
                vig["目标"][target]["警惕"] = max(_event_param('SHAME_08', 'vig_target_03'), vig["目标"][target]["警惕"] - _event_param('SHAME_08', 'vig_target_04'))

    # 时间衰减：每回合 -2，目击锁定目标不衰减
    for t in vig["目标"].values():
        if t["发现"] < 3:
            t["警惕"] = max(0, t["警惕"] - 2 * (1 if elapsed_hours is None else elapsed_hours))

    # 回宅掷骰：取所有目标最高警惕
    max_vig = max((t["警惕"] for t in vig["目标"].values()), default=0)
    if max_vig >= 70:
        prob = 0.35
    elif max_vig >= 50:
        prob = 0.10
    else:
        prob = 0.0
    if roll_home:
        vig["位置"] = "徐家住宅" if random.random() < prob else "外地"

    # 在场集合：目标位置含【徐家主宅】
    presence = parse_presence_from_memory(content)
    at_home = {name for name, info in presence.items() if "徐家主宅" in info.get("location", "")}

    # 发现几率：徐承邺在场且目标在场才可能发现
    for name, t in vig["目标"].items():
        if vig["位置"] == "徐家住宅" and name in at_home:
            expo = 30 if _is_exposed(name, shame_events) else 0
            t["发现几率"] = min(100, 20 + t["警惕"] // 2 + expo)
        else:
            t["发现几率"] = 0

    _write_vigilance_block(vig)
    summary = {"徐承邺位置": vig["位置"]}
    for name, t in vig["目标"].items():
        summary[f"徐承邺_{name}"] = f"警惕 {t['警惕']} | 发现 {t['发现']} | 发现几率 {t['发现几率']}"
    print(f" [监视矩阵] 徐承邺回宅判定：概率 {prob:.0%} → 位置 {vig['位置']} · {summary}")
    return summary


# ============ 任务系统：AI生成属性型任务 · 后端判定 · 串行单任务 ============

def _parse_task_block(content):
    """解析【任务状态】块 → {'current':..., 'history':[...], 'pending_item':...}；无块返回 None"""
    anchor = TASK_BLOCK_ANCHOR
    if anchor not in content:
        return None
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【道具倒计时】|\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    state = {"current": None, "history": [], "pending_item": None}

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

    # 待发道具：TASK-NNN | 道具描述 | 完成回合N
    pm = re.search(r"待发道具：TASK-(\d+) \| ([^|]+) \|完成回合(\d+)", block)
    if pm:
        state["pending_item"] = f"TASK-{int(pm.group(1)):03d} | {pm.group(2).strip()} |完成回合{int(pm.group(3))}"
    return state


def _write_task_block(state):
    """将结算后的任务状态写回【任务状态】块（锚点维护，与 _write_vigilance_block 同模式）"""
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = TASK_BLOCK_ANCHOR
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n【道具倒计时】|\n▲ 第一层：|\Z)", content, re.DOTALL)
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
    if state.get("pending_item"):
        lines.append("待发道具：" + state["pending_item"])
    else:
        lines.append("待发道具：（无）")
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


def _validate_task(task_issue, content):
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
    cur_val = _read_attr_value(content, target, attr)
    if cur_val is None:
        return False, f"读取不到 {target} 的 {attr} 当前值"
    if value <= cur_val:
        return False, f"目标值 {value} 必须大于当前值 {cur_val}"
    return True, None


def _next_task_id(state):
    """生成下一个 TASK-ID（当前 + 历史最大值 +1）"""
    nums = []
    if state.get("current"):
        m = re.search(r"TASK-(\d+)", state["current"]["id"])
        if m:
            nums.append(int(m.group(1)))
    for h in state.get("history") or []:
        m = re.search(r"TASK-(\d+)", h)
        if m:
            nums.append(int(m.group(1)))
    return f"TASK-{max(nums) + 1 if nums else 1:03d}"


def process_task_system(task_issue, current_round, memory_file, sim_content=None):
    """
    任务系统：每回合常驻结算（参照监视矩阵）。
    1) 当前任务进行中 → 读面板目标属性（sim_content 为本回合结算后的模拟面板，缺省读文件持久化值）
       → 达标则标记已完成、结算积分/经验（返回增量）、写最近完成+待发道具。
    2) 无进行中任务且 task_issue 非空 → 校验（白名单/目标>当前/单任务互斥）→ 挂载新任务、清待发道具行。
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
            state["pending_item"] = f"{cur['id']} | {cur['item_desc']} |完成回合{current_round}"
            delta = {"积分": points, "经验值": exp}
            print(f" 🎯 [任务系统] {cur['id']}「{cur['title']}」完成！积分+{points} 经验+{exp}，待发道具已记录")

    # 2. 新任务挂载（无进行中任务且 AI 提交 task_issue；已完成任务可被替换）
    if has_active and task_issue:
        raise ValueError("已有进行中任务，不能覆盖")
    if not has_active and task_issue:
        ok, err = _validate_task(task_issue, content)
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
            state["pending_item"] = None  # 新任务 = 旧任务已完结处理，清待发道具行
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

    # C. 增量写入第一层
    new_round = memory_deltas.get("l1_new_round", "").strip()
    if not new_round:
        new_round = memory_deltas.get("new_round_detail", "").strip() # 兼容旧版Key
        
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
        
    if is_overwrite:
        print(f" [√] 存档/全局记忆库.txt 异步引擎更新完成（回合 {current_round} - 本次为同回合覆盖更新）")
    else:
        print(f" [√] 存档/全局记忆库.txt 异步引擎更新完成（回合 {current_round}）")


# ============ 道具图鉴引擎（V2.1：唯一ID / 数量堆叠 / 动作通道 / 倒计时区块） ============
ITEM_ANCHOR_HISTORY = "▼ 已过期/已消耗道具历史区 ▼"
_ITEM_BLOCK_RE = re.compile(r"【道具名称】：(?P<name>[^\n]+)\n(?P<body>[\s\S]*?)(?=\n\n【道具名称】|\n\n(?:=+|▼)|\Z)")


def _active_item_zone(content):
    """活跃道具区 = 文件头部到历史区锚点之间。"""
    idx = content.find(ITEM_ANCHOR_HISTORY)
    return content[:idx] if idx != -1 else content


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
    for key in ("道具ID", "类型", "描述", "数量", "获得回合", "当前状态", "位置",
                "使用对象", "时效", "剩余时效", "过期规则", "使用记录", "备注", "系统效果"):
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
    """将 AI 传入条目规整为完整记录字段；desc/remark 空行归一；remaining 缺省取时效。"""
    item_name = str(item.get('name', '未命名道具')).strip() or '未命名道具'
    duration_raw = str(item.get('duration', '无')).strip()
    turns = _int_of(duration_raw, 0)
    has_timer = "临时性" in str(item.get('type', '')) and turns > 0
    remaining = str(item.get('remaining', '')).strip()
    if not remaining or remaining in ("无", "后台接管", "交由记忆库后台接管倒计时"):
        remaining = str(turns) + "回合" if has_timer else "无"

    def flat(v):
        return str(v).replace("\n", " ").replace("\r", " ").strip()

    return {
        "id": str(item.get('id', '')).strip(),
        "name": item_name,
        "type": str(item.get('type', '临时性（消耗品）')).strip() or '临时性（消耗品）',
        "desc": flat(item.get('desc', '')),
        "quantity": max(1, _int_of(item.get('quantity', 1), 1)),
        "obtain_round": str(item.get('obtain_round', current_round)).strip(),
        "status": str(item.get('status', '仓库中')).strip() or '仓库中',
        "location": flat(item.get('location', '无')) or '无',
        "target": flat(item.get('target', '无')) or '无',
        "duration": duration_raw or '无',
        "remaining": remaining,
        "expire_rule": flat(item.get('expire_rule', '时效归零后立即完全失效')) or '时效归零后立即完全失效',
        "usage_record": flat(item.get('usage_record', f'回合{current_round} - 已记录')) or f'回合{current_round} - 已记录',
        "remark": flat(item.get('remark', '')),
        "system_effect": flat(item.get('system_effect', '')),
        "_timer": has_timer,
        "_turns": turns if has_timer else 0,
    }


def _item_from_parsed(old, name=""):
    """将 _parse_item_block 的中文键解析结果映射为 _record_text 所需英文键。
    name 显式传入（块首【道具名称】行不在 body 内，_parse_item_block 解析不到）。"""
    return {
        "name": name or old.get("道具名称", "") or "",
        "id": old.get("道具ID", ""),
        "type": old.get("类型", ""),
        "desc": old.get("描述", ""),
        "quantity": _int_of(old.get("数量"), 1),
        "obtain_round": old.get("获得回合", ""),
        "status": old.get("当前状态", ""),
        "location": old.get("位置", ""),
        "target": old.get("使用对象", ""),
        "duration": old.get("时效", ""),
        "remaining": old.get("剩余时效", ""),
        "expire_rule": old.get("过期规则", ""),
        "usage_record": old.get("使用记录", ""),
        "remark": old.get("备注", ""),
        "system_effect": old.get("系统效果", ""),
    }


def _record_text(item):
    record = f"""【道具名称】：{item['name']}
【道具ID】：{item['id']}
【类型】：{item['type']}
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
【系统效果】：{item.get('system_effect', '')}"""
    return record.strip()


def _archive_item(content, target, item, new_status, usage_record, current_round):
    """从活跃区移除条目，写入历史区（状态/使用记录覆写）。返回新 content。"""
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
    # 活跃区移除
    content = content[:target["start"]] + content[target["end"]:]
    # 历史区插入：标题下分隔线之后
    m = re.search(r"(▼\s*已过期/已消耗道具历史区[^\n]*\n=+\n)([\s\S]*?)(?=\n=+\n▼\s*格式模板区|\Z)", content)
    if not m:
        raise RuntimeError("道具引擎：找不到历史区内容锚点！归档失败（已中止注入）。")
    head, body = m.group(1), m.group(2)
    cleaned = body.strip().replace("（当前为空）", "").strip()
    new_body = record + "\n\n" + (cleaned + "\n\n" if cleaned else "")
    return content[:m.start()] + head + "\n" + new_body + content[m.end():]


def _sync_item_timers(memory_file, pending_add, pending_remove):
    """同步记忆库【道具倒计时】区块：追加新行 / 移除行。无区块则自动补建。"""
    if not pending_add and not pending_remove:
        return
    if not os.path.exists(memory_file):
        return
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = "【道具倒计时】"
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        l1_idx = content.find("▲ 第一层：")
        if l1_idx == -1:
            return
        content = content[:l1_idx] + anchor + "\n（空）\n" + content[l1_idx:]
        m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n▲ 第一层：|\Z)", content, re.DOTALL)
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
    exist_ids = set()
    for ln in keep:
        idm = re.match(r"^(ITEM-\d+)：", ln)
        if idm:
            exist_ids.add(idm.group(1))
    for item_id, turns, name in pending_add:
        if item_id and item_id not in exist_ids:
            keep.append(f"{item_id}：{turns}回合 | 名称：{name} | 状态：进行中")
    if not keep:
        keep = ["（空）"]
    new_block = anchor + "\n" + "\n".join(keep) + "\n"
    content = content[:m.start(1)] + new_block + content[m.end(1):]
    with open(memory_file, "w", encoding="utf-8") as f:
        f.write(content)


def update_item_catalog(current_round, new_item_entries):
    """
    道具图鉴引擎（V2.1）：唯一ID / 数量堆叠 / 动作通道（add·update·consume·archive）/
    历史区归档 / 记忆库【道具倒计时】区块同步。
    锚点缺失 → raise，由 execute_injection 全局回滚兜底。
    """
    if not new_item_entries:
        return {}
    if not os.path.exists(ITEM_FILE):
        return {}

    with open(ITEM_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if ITEM_ANCHOR_HISTORY not in content:
        raise RuntimeError("道具引擎：找不到历史区锚点！写入失败（已中止注入并触发全局回滚）。")

    summary = {"added": [], "updated": [], "consumed": [], "archived": []}
    pending_add = []  # (item_id, turns, name)
    pending_remove = []  # [item_id, ...]

    for item in new_item_entries:
        item_name = str(item.get('name', '未命名道具')).strip() or '未命名道具'
        action = str(item.get('action', 'add')).strip() or 'add'
        item_id = str(item.get('id', '')).strip()
        norm = _normalize_item(item, current_round)

        if action == 'consume':
            target = _find_item_block(content, name=item_name, item_id=item_id)
            if target is None:
                print(f" [道具引擎] 消耗失败：活跃区找不到道具「{item_name}」（ID：{item_id or '无'}）")
                continue
            old = _parse_item_block(target["block"])
            old_id = old.get("道具ID") or item_id
            cur_q = _int_of(old.get("数量"), 1)
            new_q = cur_q - norm["quantity"]
            if new_q <= 0:
                content = _archive_item(content, target, {**_item_from_parsed(old, item_name), "id": old_id, "quantity": cur_q},
                                        "已消耗", f"回合{current_round} - 消耗", current_round)
                summary["consumed"].append(item_name)
                if old_id:
                    pending_remove.append(old_id)
            else:
                new_rec = _record_text({**_item_from_parsed(old, item_name), "id": old_id, "quantity": new_q,
                                        "status": old.get("当前状态") or "仓库中"})
                content = content[:target["start"]] + new_rec + content[target["end"]:]
                summary["updated"].append(item_name)
            continue

        if action == 'archive':
            target = _find_item_block(content, name=item_name, item_id=item_id)
            if target is None:
                print(f" [道具引擎] 归档失败：活跃区找不到道具「{item_name}」（ID：{item_id or '无'}）")
                continue
            old = _parse_item_block(target["block"])
            old_id = old.get("道具ID") or item_id
            content = _archive_item(content, target, {**_item_from_parsed(old, item_name), "id": old_id},
                                    "已归档", f"回合{current_round} - 手动归档", current_round)
            summary["archived"].append(item_name)
            if old_id:
                pending_remove.append(old_id)
            continue

        # add / update：定位（id 优先，其次 name）
        target = _find_item_block(content, item_id=item_id) if item_id else None
        if target is None and not item_id:
            target = _find_item_block(content, name=item_name)

        if target is not None:
            old = _parse_item_block(target["block"])
            old_id = old.get("道具ID") or item_id
            new_q = (_int_of(old.get("数量"), 1) + norm["quantity"]) if action == 'add' else norm["quantity"]
            new_rec = _record_text({**norm, "id": old_id, "quantity": new_q,
                                    "obtain_round": old.get("获得回合") or norm["obtain_round"]})
            content = content[:target["start"]] + new_rec + content[target["end"]:]
            summary["updated"].append(item_name)
            if norm["_timer"] and old_id and old_id not in pending_remove:
                pending_add.append((old_id, norm["_turns"], item_name))
            print(f" 🎒 [道具引擎] 已更新图鉴库道具：{item_name}（{old_id}，数量 {new_q}）")
        else:
            new_id = item_id if re.fullmatch(r"ITEM-\d+", item_id) else _next_item_id(content)
            new_rec = _record_text({**norm, "id": new_id})
            content = content.replace(ITEM_ANCHOR_HISTORY, new_rec + "\n\n" + ITEM_ANCHOR_HISTORY, 1)
            summary["added"].append(item_name)
            if norm["_timer"]:
                pending_add.append((new_id, norm["_turns"], item_name))
            print(f" 🎁 [道具引擎] 盲盒商城兑换，已新增条目：{item_name}（{new_id}，数量 {norm['quantity']}）")

    with open(ITEM_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    if pending_add or pending_remove:
        _sync_item_timers(MEMORY_FILE, pending_add, pending_remove)
    return summary


def process_item_timers(memory_file, item_file, current_round):
    """
    道具倒计时结算：记忆库【道具倒计时】区块每回合 -1；
    归零道具自动失效归档（活跃区移除 → 历史区 status「已过期」）。
    无区块时自动补建空块。
    """
    if not os.path.exists(memory_file) or not os.path.exists(item_file):
        return {}
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    anchor = "【道具倒计时】"
    m = re.search(rf"(?m)({re.escape(anchor)}.*?)(?=\n▲ 第一层：|\Z)", content, re.DOTALL)
    if not m:
        l1_idx = content.find("▲ 第一层：")
        if l1_idx == -1:
            return {}
        block = anchor + "\n（空）\n"
        content = content[:l1_idx] + block + content[l1_idx:]
        with open(memory_file, "w", encoding="utf-8") as f:
            f.write(content)
        return {}
    block = m.group(1)
    expired = []
    keep = []
    remaining_updates = {}  # item_id -> 剩余回合数（同步覆写图鉴【剩余时效】）
    had_lines = any(ln.strip() and ln.strip() != "（空）" for ln in block.split("\n")[1:])
    if not had_lines:
        # 区块为空：无计时道具，无需写回
        return {"expired": []}
    for ln in block.split("\n")[1:]:
        ln = ln.strip()
        if not ln or ln == "（空）":
            continue
        tm = re.match(r"^(ITEM-\d+)：(\d+)回合\s*\|\s*名称：(.+?)(?:\s*\|\s*状态：.+)?$", ln)
        if not tm:
            continue
        item_id, turns, name = tm.group(1), int(tm.group(2)), tm.group(3).strip()
        turns -= 1
        if turns <= 0:
            expired.append((item_id, name))
            print(f" ⌛ [道具引擎] {name}（{item_id}）时效归零，自动失效归档。")
        else:
            keep.append(f"{item_id}：{turns}回合 | 名称：{name} | 状态：进行中")
            remaining_updates[item_id] = turns
    if not keep:
        keep = ["（空）"]
    new_block = anchor + "\n" + "\n".join(keep) + "\n"
    content = content[:m.start(1)] + new_block + content[m.end(1):]
    with open(memory_file, "w", encoding="utf-8") as f:
        f.write(content)

    # 归档过期道具 + 同步图鉴【剩余时效】真实值
    if expired or remaining_updates:
        with open(item_file, "r", encoding="utf-8") as f:
            icontent = f.read()
        for item_id, turns in remaining_updates.items():
            target = _find_item_block(icontent, item_id=item_id)
            if target is None:
                continue
            new_block = re.sub(r"(【剩余时效】：)[^\n]*", rf"\g<1>{turns}回合", target["block"], count=1)
            icontent = icontent[:target["start"]] + new_block + icontent[target["end"]:]
        for item_id, name in expired:
            target = _find_item_block(icontent, item_id=item_id)
            if target is None:
                continue
            old = _parse_item_block(target["block"])
            icontent = _archive_item(icontent, target,
                                     {**_item_from_parsed(old, name), "id": item_id},
                                     "已过期", f"回合{current_round} - 时效耗尽自动归档", current_round)
        with open(item_file, "w", encoding="utf-8") as f:
            f.write(icontent)
    return {"expired": [name for _, name in expired]}

def update_npc_roster(current_round, new_npc_entries):
    """
    次要NPC极简静态图鉴更新
    剥离动态状态追踪，仅用于首次登场的静态设定建档。
    """
    if not new_npc_entries: return
    if not os.path.exists(NPC_ROSTER_FILE): return

    with open(NPC_ROSTER_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    for npc in new_npc_entries:
        npc_name = npc.get('name', '未命名')
        record = f"""【NPC名称】：{npc_name}
【身份/角色】：{npc.get('identity', '')}
【出场设定/性格】：{npc.get('setting', '')}
【初始阵营/归属】：{npc.get('faction', '')}"""
        
        pattern = rf"【NPC名称】：{re.escape(npc_name)}\n[\s\S]*?(?=\n\n【NPC名称】|$)"
        if re.search(pattern, content):
            content = re.sub(pattern, record.strip(), content)
            print(f" 👥 [NPC图鉴] 极低频更新：已更新现有静态角色 {npc_name}")
        else:
            content = content + "\n\n" + record.strip()
            print(f" 👥 [NPC图鉴] 极低频更新：已建档新角色 {npc_name}")

    with open(NPC_ROSTER_FILE, "w", encoding="utf-8") as f:
        f.write(content)


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
    # 例外：L1 仅有序幕锚点【1】+ 隐藏标记时，允许正式第1回合覆盖写入
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            check_content = f.read()
        l1_start = check_content.find("▲ 第一层：")
        l2_start = check_content.find("▲ 第二层：")
        l1_text = check_content[l1_start:l2_start] if l1_start != -1 and l2_start != -1 else ""
        # 必须过滤掉模板范例中的虚假条目（含xxxxxxxxx的占位行）
        l1_real_items = re.findall(r"【\d+】[^\n]*", l1_text)
        l1_real_items = [item for item in l1_real_items if "xxxxxxxxx" not in item and "范例" not in item]
        hit = [item for item in l1_real_items if item.startswith(f"【{current_round}】")]
        if hit:
            prologue_mark = "【系统隐藏标记：以上为新游戏序幕锚点，剧情从此刻正式开始计算】"
            is_prologue_only = (
                current_round == 1
                and len(l1_real_items) == 1
                and prologue_mark in l1_text
            )
            if is_prologue_only:
                print(" ⚠️ [序幕覆盖] 检测到仅有序幕锚点【1】，允许正式第1回合覆盖写入。")
            else:
                print(f"\n 🛑 [致命拦截] 引擎检测到【第 {current_round} 回合】的存档已存在！")
                raise ValueError("当前回合已存在，禁止重复结算")

    write_system_log(current_round, system_log)

    # 语义化规则包：后台引擎自动物理计算与覆写
    if shame_events:
        computed_pregnancy = process_pregnancy_rng(shame_events, MEMORY_FILE)
        for char, is_preg in computed_pregnancy.items():
            if char not in panel_changes:
                panel_changes[char] = {}
            panel_changes[char]["怀孕"] = is_preg

    if affection_events or shame_events:
        computed_aff = process_affection_system(affection_events, shame_events, MEMORY_FILE)
        for char, new_val in computed_aff.items():
            if char not in panel_changes:
                panel_changes[char] = {}
            panel_changes[char]["好感"] = new_val

    if shame_events:
        computed_shame = process_shame_system(shame_events, MEMORY_FILE)
        for char, new_val in computed_shame.items():
            if char not in panel_changes:
                panel_changes[char] = {}
            panel_changes[char]["羞耻"] = new_val
            
    if depravity_events:
        computed_dep = process_depravity_system(depravity_events, MEMORY_FILE)
        for char, new_val in computed_dep.items():
            if char not in panel_changes:
                panel_changes[char] = {}
            panel_changes[char]["堕落"] = new_val

    if ds_events:
        computed_ds = process_desire_stamina_system(ds_events, MEMORY_FILE)
        for char, stats in computed_ds.items():
            if char not in panel_changes:
                panel_changes[char] = {}
            panel_changes[char]["欲望"] = stats["欲望"]
            panel_changes[char]["体力"] = stats["体力"]
            panel_changes[char]["高潮"] = stats["高潮"]

    # 宿主核心引擎：三轨竞标结算 + 商城扣费 + 体力代偿 + 肾上腺素
    if host_events:
        host_result = process_host_system(host_events, shame_events, MEMORY_FILE)
        if host_result:
            panel_changes["系统宿主"] = host_result

    # 任务系统：判定完成 + 生成新任务（判定基准 = 本回合结算后的模拟面板，与面板显示一致；奖励独立叠加）
    sim_content = None
    if panel_changes:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            _base_c = f.read()
        sim_content = _simulate_panel(_base_c, panel_changes)
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
    # 提取前台AI发来的新BUFF挂载请求
    new_buffs_dict = memory_deltas.get("new_buffs", {}) if isinstance(memory_deltas, dict) else {}
    update_persistent_buffs(MEMORY_FILE, shame_events, new_buffs_dict)
    update_micro_states(micro_state_changes)
    update_counters(counter_updates)
    # 徐承邺监视矩阵：每回合常驻结算（警惕增减/发现/回宅/发现几率）
    process_vigilance_system(vigilance_events, shame_events, MEMORY_FILE)
    # 人物所在：MEMORY_DELTAS.presence 或独立 presence_changes 参数
    if not presence_changes and isinstance(memory_deltas, dict):
        presence_changes = memory_deltas.get("presence") or memory_deltas.get("presence_changes") or {}
    update_presence(presence_changes if isinstance(presence_changes, dict) else {})
    update_item_catalog(current_round, item_entries)
    process_item_timers(MEMORY_FILE, ITEM_FILE, current_round)
    update_npc_roster(current_round, npc_entries)
    
    # 先拆场景戳为 header，再仅对过载墙切分（主旁白 80–110 保留，硬拆线 120）
    normalized_nodes, _scene_title = _normalize_story_headers(list(story_nodes or []))
    safe_nodes = _split_long_narrations(normalized_nodes, max_length=120)
    presence_snapshot = parse_presence_from_memory()
    generate_data_json(current_round, safe_nodes, options_text, presence=presence_snapshot)

    print("=" * 70)
    print(" [完成] 本回合存档已全部更新，可以直接游玩！")
    print("=" * 70)

def apply_story_events(events, task_issue, memory_round):
    """Settle accepted event tags without the legacy full-round lifecycle."""
    with open(MEMORY_FILE, encoding='utf-8') as handle:
        content = handle.read()
    panels = {}
    shame = events['shame_events']
    if shame:
        for who, val in process_pregnancy_rng(shame, MEMORY_FILE).items():
            panels.setdefault(who, {})['怀孕'] = val
    if shame or events['affection_events']:
        for who, val in process_affection_system(events['affection_events'], shame, MEMORY_FILE).items():
            panels.setdefault(who, {})['好感'] = val
    for field, function, attr in (('shame_events', process_shame_system, '羞耻'),
                                   ('depravity_events', process_depravity_system, '堕落')):
        if events[field]:
            for who, val in function(events[field], MEMORY_FILE).items():
                panels.setdefault(who, {})[attr] = val
    if events['ds_events']:
        for who, values in process_desire_stamina_system(events['ds_events'], MEMORY_FILE).items():
            panels.setdefault(who, {}).update({k: values[k] for k in ('欲望', '体力', '高潮')})
    if events['host_events'] or shame:
        host = process_host_system(events['host_events'], shame, MEMORY_FILE)
        if host: panels['系统宿主'] = host
    content = _simulate_panel(content, panels)
    with open(MEMORY_FILE, 'w', encoding='utf-8') as handle: handle.write(content)
    reward = process_task_system(task_issue, memory_round, MEMORY_FILE, sim_content=content)
    if reward:
        with open(MEMORY_FILE, encoding='utf-8') as handle: content = handle.read()
        host = _read_host_panel(MEMORY_FILE)
        for key, val in reward.items(): host[key] += val
        with open(MEMORY_FILE, 'w', encoding='utf-8') as handle:
            handle.write(_simulate_panel(content, {'系统宿主': host}))


def consume_story_recovery_item(item_id, recovery, memory_round):
    """Consume precisely one held registered item; append usage even for a remaining stack."""
    with open(ITEM_FILE, encoding='utf-8') as handle: text = handle.read()
    target = _find_item_block(text, item_id=item_id)
    if target is None: raise ValueError('恢复道具已不存在')
    old = _parse_item_block(target['block'])
    name = re.search(r'【道具名称】：([^\n]+)', target['block'])[1].strip()
    if old['当前状态'] != '仓库中' or _int_of(old['数量'], 0) < 1:
        raise ValueError('恢复道具库存不合法')
    quantity = _int_of(old['数量'], 0)
    record = _item_from_parsed(old, name)
    usage = '游戏回合' + str(memory_round) + ' - 使用1份，宿主体力恢复' + str(recovery)
    if quantity == 1:
        text = _archive_item(text, target, record, '已消耗', usage, memory_round)
        _sync_item_timers(MEMORY_FILE, [], [item_id])
    else:
        record.update(quantity=quantity-1, usage_record=(record['usage_record']+' / '+usage).strip(' /'))
        text = text[:target['start']] + _record_text(record) + text[target['end']:]
    with open(ITEM_FILE, 'w', encoding='utf-8') as handle: handle.write(text)
    with open(MEMORY_FILE, encoding='utf-8') as handle: memory = handle.read()
    current = _read_attr_value(memory, '系统宿主', '体力')
    if current is None or recovery <= 0 or current + recovery > 100: raise ValueError('实际恢复量无效')
    with open(MEMORY_FILE, 'w', encoding='utf-8') as handle:
        handle.write(_simulate_panel(memory, {'系统宿主': {'体力': current+recovery}}))


def apply_interaction_operation(operation):
    """Apply a prevalidated operation inside a RoundStore staging directory."""
    code = operation['code']
    if code == 'move_player':
        update_presence({'徐志北': {'location': operation['destination'], 'reason': '玩家明确前往'}})
        return
    if code == 'transfer_item':
        with open(ITEM_FILE, encoding='utf-8') as handle:
            content = handle.read()
        target = _find_item_block(content, item_id=operation['item_id'])
        if target is None:
            raise ValueError('交付道具已不存在')
        old = _parse_item_block(target['block'])
        item = _item_from_parsed(old, re.search(r'【道具名称】：([^\n]+)', target['block']).group(1).strip())
        place = parse_presence_from_memory()['徐志北']['location']
        item.update(status='已交付', target=operation['recipient'], location=place,
                    usage_record=(item.get('usage_record', '') + ' / 已整组交付给' + operation['recipient']).strip(' /'))
        content = content[:target['start']] + _record_text(item) + content[target['end']:]
        with open(ITEM_FILE, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return
    raise ValueError('不支持的正式互动操作')


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

"""Deterministic story accounting. Only RoundStore publishes its staged output."""
import base64
import copy
import json
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import time
import round_runtime as rr
import save_store

COSTS = {'A': 5, 'B': 10, 'C': 15}
TASKS = '.round-runtime/story/tasks.json'
PURE_ITEM = re.compile(r'\s*使用恢复道具\s*[：:]?\s*(ITEM-\d+)\s*[。！!]?\s*')
SHOP_ANCHOR = '【商城与回响状态】'
SHOP_CATALOG_DEFAULT = 'txt文件/系统商城目录.json'
SHOP_RECENT_LIMIT = 8
SHOP_ECHO_LIMIT = 4
SHOP_TIER_RANGES = {'low': (1, 10), 'mid': (11, 50), 'high': (60, 999999)}
SHOP_DYNAMIC_LIMIT = 30
SHOP_GRADES = ('T1', 'T2', 'T3', 'T4')
SHOP_GRADE_ORDER = {'T1': 1, 'T2': 2, 'T3': 3, 'T4': 4}
SHOP_GRADE_META = {
    'T1': {'label': 'T1 · 寻常小物', 'short': 'T1 寻常', 'min_price': 10, 'max_price': 30, 'max_per_save': 3},
    'T2': {'label': 'T2 · 进阶利器', 'short': 'T2 进阶', 'min_price': 32, 'max_price': 60, 'max_per_save': 3},
    'T3': {'label': 'T3 · 稀缺重器', 'short': 'T3 稀缺', 'min_price': 65, 'max_price': 120, 'max_per_save': 2},
    'T4': {'label': 'T4 · 深渊禁品', 'short': 'T4 深渊禁品', 'min_price': 150, 'max_price': 260, 'max_per_save': 1},
}
SHOP_GRADE_T4_RE = re.compile(
    r'催情|迷情|媚药|发情|失神|遥控|无线震动|跳蛋|项圈|贞操|调教套|奴役|深渊禁|扭转全局|彻底压制|一举定局|绝杀筹码|核心把柄|致命黑料|顶级秘药|强效催化|绝对顺从|强制服从'
)
SHOP_GRADE_T3_RE = re.compile(
    r'针孔|窃听|偷拍|监听|追踪器|隐蔽监控|微型摄像|拘束|手铐|束缚带|捆绑|情趣器具|高阶|稀缺|核心人脉|商业筹码|重磅筹码|催化滴剂|暗中调查|破防'
)
SHOP_GRADE_T2_RE = re.compile(
    r'精油|香薰|香氛|丝袜|睡裙|蕾丝|情趣|眼罩|冰玉|公关礼盒|厚礼|定制礼|微醺|桃露'
)
VALID_SYSTEM_EFFECT_RE = re.compile(
    r'^(?:host_stamina:[1-9]\d{0,3}|buff:[^:\r\n|]{2,12}:[1-4]:[^:\r\n|]{4,60}|deploy_device:(?:camera|audio|aroma))$'
)
SHOP_FORBIDDEN_DURATION_RE = re.compile(
    r'(?:延长|冻结|缩短|设定|暂停|修改|刷新|重置|清除).{0,6}(?:持续时间|状态时间|时效|倒计时|冷却|体液锁定|BUFF)'
)
_STAT_ATTR_PAT = (
    r'(?:属性|面板|数值|好感(?:度)?|羞耻(?:度)?|堕落(?:度)?|欲望(?:值)?|高潮(?:值|进度)?'
    r'|体力|精力|耐力|魅力|商业嗅觉|嗅觉|积分|经验(?:值)?|警惕(?:值|度)?)'
)
SHOP_FORBIDDEN_DYN_RE = re.compile(
    r'extend_duration|host_stamina'
    + r'|永久修改' + _STAT_ATTR_PAT
    + r'|(?:直接|立即|立刻|瞬间|一键|自动|必定|强制|无条件|永久|凭空|固定)\s*'
      r'(?:增加|提升|提高|加|涨|拉高|降低|减少|扣减|扣除|削减|清零|归零|拉满|加满|回满|回复|恢复|锁死|修改|改写|覆写|抹除|消除|刷取|暴涨).{0,6}' + _STAT_ATTR_PAT
    + r'|(?:清零|归零|拉满|加满|回满|回复|恢复|锁死|覆写|抹除|刷取|暴涨).{0,4}' + _STAT_ATTR_PAT
    + r'|(?:使用|服用|佩戴|携带|赠予|送出|饮用|涂抹|触发)后.{0,6}(?:即可|便可|就会|立刻|立即|直接)?(?:增加|提升|提高|涨|降低|减少|扣减|回复|恢复|清零|拉满|修改).{0,6}' + _STAT_ATTR_PAT
    + r'|' + _STAT_ATTR_PAT + r'\s*(?:直接|立即|立刻|瞬间|固定|自动|额外)?\s*[+＋\-－]\s*\d+'
    + r'|[+＋\-－]\s*\d+\s*(?:点|分|%)?' + _STAT_ATTR_PAT
    + r'|(?:增加|提升|提高|加|涨|拉高|降低|减少|扣减|扣除|回复|恢复|刷|送)\s*\d+\s*(?:点|分|%)?' + _STAT_ATTR_PAT
    + r'|' + _STAT_ATTR_PAT + r'(?:药水|神丹|丹药|药丸|修改器|增幅器|清零器|直充|加点卡)'
)
SHOP_CUSTOM_TAG_RE = re.compile(
    r'[【\[]\s*(?:商城定制|定制道具|商城进货|SHOP_CUSTOM|SHOP)\s*(?:[：:]([^】\]]*))?[】\]]',
    re.I,
)
_SHOP_BRACKET_SPAN_RE = re.compile(r'[（(]([^）)]*)[）)]')


def detect_shop_custom_request(text):
    """Detect explicit in-story custom shop restock tag (e.g. 【商城定制】) and return trimmed query or None."""
    if not isinstance(text, str) or not text.strip():
        return None
    m = SHOP_CUSTOM_TAG_RE.search(text)
    if not m:
        return None
    # Prefer enclosing parenthesis containing the tag so surrounding dialogue isn't lost or noisy.
    for bm in _SHOP_BRACKET_SPAN_RE.finditer(text):
        if bm.start() <= m.start() and m.end() <= bm.end():
            inner = SHOP_CUSTOM_TAG_RE.sub(lambda mm: (mm.group(1) or '').strip(), bm.group(1)).strip(' ：:，,。！？!')
            if inner:
                return re.sub(r'\s+', ' ', inner)[:180]
    inline = (m.group(1) or '').strip()
    after = text[m.end():].strip()
    merged = ' '.join(p for p in (inline, after) if p).strip() or text.strip()
    merged = SHOP_CUSTOM_TAG_RE.sub('', merged).strip(' ：:，,。！？!')
    return re.sub(r'\s+', ' ', merged)[:180] or '定制贴合当前局面的道具'
INTEL_ANCHOR = '【商业情报与杠杆状态】'
INTEL_CATALOG_DEFAULT = 'txt文件/商业情报目录.json'
DIRECTOR_ANCHOR = '【世界导演状态】'
DIRECTOR_CATALOG_DEFAULT = 'txt文件/世界变故库.json'
DIRECTOR_SEED_LIMIT = 3
DIRECTOR_PACING_MODES = ('slow', 'standard', 'frequent')


def normalize_director_pacing(val):
    s = str(val or '').strip().lower()
    return s if s in DIRECTOR_PACING_MODES else 'standard'


DIRECTOR_DEFAULTS = {
    'status': 'active',
    'catalog': DIRECTOR_CATALOG_DEFAULT,
    'base_prob': 0.08,
    'max_prob': 0.85,
    'stagnation_curve': [0.0, 0.07, 0.16, 0.28, 0.44, 0.62],
    'global_cooldown': 1,
    'soft_cooldown_penalty': 0.25,
    'tier_weights': {'tier1': 50, 'tier2': 38, 'tier3': 12, 'tier4': 22},
    'scene_exit_threshold': 3,
    'track_weights': {'thread_spark': 45, 'offstage_clock': 30, 'preset_beat': 25},
    'max_active_threads': 5,
    'max_thread_age': 12,
    'channel_cooldown_window': 4,
    'clock_tick_interval': 3,
    'heroine_pity_turns': 4,
    'heroine_beat_cooldown': 1,
    'erotic_category_cooldown': 2,
    'pacing_presets': {
        'slow': {'heroine_pity_turns': 6, 'heroine_beat_cooldown': 2, 'erotic_category_cooldown': 3, 'heroine_prob_mult': 0.75},
        'standard': {'heroine_pity_turns': 4, 'heroine_beat_cooldown': 1, 'erotic_category_cooldown': 2, 'heroine_prob_mult': 1.0},
        'frequent': {'heroine_pity_turns': 3, 'heroine_beat_cooldown': 1, 'erotic_category_cooldown': 1, 'heroine_prob_mult': 1.35},
    },
}
DIRECTOR_VALID_PEOPLE = ('沈知韫', '徐念薇', '苏婉青', '徐承邺', '徐志北')
DIRECTOR_DEFAULT_CHANNELS = {
    'phone_msg': '手机来电/微信/推送消息',
    'door_visit': '敲门/突然来访/门外闯入',
    'object_trace': '物件遗落/票据/衣着痕迹/随身小物',
    'sensory_slip': '气味/余温/声响/神态走神',
    'third_party': '管家/同事/邻里/第三方转述',
    'schedule_clash': '行程变卦/时间压缩/设备故障/天气突变',
    'conversation_twist': '口误/旧话重提/试探反问/话题转折',
    'offstage_ripple': '跨城信物/场外暗流余波',
}
WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
PASSIVE_TARGETS = ('沈知韫', '苏婉青', '徐念薇')
PASSIVE_LEVELS = (
    {'level': 0, 'tag': 'Lv.0', 'name': '凡人体质', 'cost': 0, 'effect': '无被动增益；越界面临正常防御或反击'},
    {'level': 1, 'tag': 'Lv.1', 'name': '洞察之瞳', 'cost': 20, 'effect': '精准捕捉目标生理伪装、心虚停顿与微小动摇'},
    {'level': 2, 'tag': 'Lv.2', 'name': '认知欺诈滤镜', 'cost': 50, 'effect': 'C烈度越界好感惩罚减半（叠加封顶75%且保底-1）；目标潜意识优先合理化宿主行为'},
    {'level': 3, 'tag': 'Lv.3', 'name': '疲劳诱导', 'cost': 110, 'effect': '目标焦虑/劳作/剧烈抗拒体力消耗翻倍；且目标体力<60时活跃C羞耻额外-1'},
    {'level': 4, 'tag': 'Lv.4', 'name': '防线支配', 'cost': 220, 'effect': '全景测绘；羞耻侵蚀加深(×0.7)、活跃C额外降防-2、高羞耻完好防线豁免与同质化穿透'},
)


def passive_levels(root):
    """Load passive upgrade EXP costs dynamically from txt文件/互动运行配置.json."""
    levels = [dict(x) for x in PASSIVE_LEVELS]
    cfg_path = Path(root) / 'txt文件/互动运行配置.json'
    if cfg_path.is_file():
        try:
            raw = rr.load_request(cfg_path.read_text(encoding='utf-8'))
            costs = (raw.get('passive') or {}).get('costs') or {}
            if isinstance(costs, dict):
                for item in levels:
                    key = str(item['level'])
                    if key in costs and isinstance(costs[key], int) and costs[key] >= 0:
                        item['cost'] = costs[key]
        except Exception:
            pass
    return levels
_FISH_TAG_RE = re.compile(r"\[[^\]\r\n]{1,80}\]")
_DRAMA3_EVIDENCE_RE = re.compile(
    r"</?(?:whisper|emphasis|soft|fast|slow|stress|forceful|chinese|english|japanese|korean|cantonese|french|german|spanish)>",
    flags=re.I,
)
_PHONEME_EVIDENCE_RE = re.compile(r"<\|phoneme_start\|>[^<\r\n]{1,40}<\|phoneme_end\|>|<\|[^|\r\n]{1,40}\|>")
_SUBTEXT_RUBY_RE = re.compile(r"[｛{]([^｜|}\r\n]+)[｜|]([^｝}\r\n]+)[｝}]")
ACTIVE_JOB_STATUSES = {'preparing', 'queued', 'generating', 'validating', 'refund_pending'}


MEMORY_DEFAULTS = {'fact_chars':160, 'round_chars':600, 'l2_chars':240, 'l3_chars':600,
                   'l4_chars':900, 'context_chars':6000, 'history_turns':6,
                   'history_chars':12000, 'index_entries':24}


def _clean_single_line(text):
    return re.sub(r'[\r\n|]+', ' ', str(text or '')).strip()


def _norm_evidence_text(text, subtext_mode=None):
    raw = str(text or '')
    if subtext_mode == 'surface':
        raw = _SUBTEXT_RUBY_RE.sub(r'\1', raw)
    elif subtext_mode == 'subtext':
        raw = _SUBTEXT_RUBY_RE.sub(r'\2', raw)
    stripped = _FISH_TAG_RE.sub('', raw)
    stripped = _DRAMA3_EVIDENCE_RE.sub('', stripped)
    stripped = _PHONEME_EVIDENCE_RE.sub('', stripped)
    return re.sub(r'\s+', ' ', stripped).strip()


def _evidence_matches(evidence, texts):
    if not isinstance(evidence, str) or not evidence.strip():
        return False
    if evidence in texts:
        return True
    for mode in (None, 'surface', 'subtext'):
        ne = _norm_evidence_text(evidence, mode)
        if len(ne) >= 2 and (
            ne in _norm_evidence_text(texts, mode)
            or ne in _norm_evidence_text(texts, 'surface')
            or ne in _norm_evidence_text(texts, 'subtext')
        ):
            return True
    return False


def parse_shop_echo_block(content):
    """Parse 【商城与回响状态】 from 全局记忆库.txt; missing block defaults cleanly to empty."""
    state_out = {'redeemed': {}, 'recent': [], 'echoes': []}
    if not content or SHOP_ANCHOR not in content:
        return state_out
    m = re.search(rf'(?m)({re.escape(SHOP_ANCHOR)}.*?)(?=\n【|\n▲ 第一层：|\Z)', content, re.S)
    if not m:
        return state_out
    block = m.group(1)
    rm = re.search(r'^已兑统计：([^\n]+)', block, re.M)
    if rm and rm.group(1).strip() not in ('（无）', '(无)', '无', ''):
        for seg in rm.group(1).split('|'):
            pm = re.fullmatch(r'\s*((?:SHOP|DYN)-\d+)[×x*](\d+)\s*', seg)
            if pm:
                state_out['redeemed'][pm.group(1)] = int(pm.group(2))
    rec_m = re.search(r'^最近兑换：\n((?: [^\n]+\n?)*)', block, re.M)
    if rec_m and rec_m.group(1).strip():
        state_out['recent'] = [ln.strip() for ln in rec_m.group(1).splitlines() if ln.strip()][:SHOP_RECENT_LIMIT]
    echo_m = re.search(r'^待播回响：\n((?: [^\n]+\n?)*)', block, re.M)
    if echo_m and echo_m.group(1).strip():
        for ln in echo_m.group(1).splitlines():
            raw = ln.strip()
            if not raw:
                continue
            parts = [p.strip() for p in raw.split('|', 2)]
            if len(parts) == 3 and parts[0] and parts[1] and parts[2]:
                state_out['echoes'].append({
                    'id': f'{parts[0]}:{parts[1]}',
                    'kind': parts[0],
                    'ref': parts[1],
                    'summary': parts[2],
                })
    state_out['echoes'] = state_out['echoes'][-SHOP_ECHO_LIMIT:]
    return state_out


def write_shop_echo_block(content, shop_state):
    """Write 【商城与回响状态】 cleanly into pre-L1 region without disturbing adjacent blocks."""
    redeemed = shop_state.get('redeemed') or {}
    recent = [ln.strip() for ln in (shop_state.get('recent') or []) if str(ln).strip()][:SHOP_RECENT_LIMIT]
    echoes = list(shop_state.get('echoes') or [])[-SHOP_ECHO_LIMIT:]
    lines = [SHOP_ANCHOR]
    if redeemed:
        parts = [f'{k}×{int(v)}' for k, v in sorted(redeemed.items()) if int(v) > 0]
        lines.append('已兑统计：' + (' | '.join(parts) if parts else '（无）'))
    else:
        lines.append('已兑统计：（无）')
    if recent:
        lines.append('最近兑换：')
        for row in recent:
            lines.append(' ' + row.replace('\n', ' ').strip())
    else:
        lines.append('最近兑换：（无）')
    if echoes:
        lines.append('待播回响：')
        for item in echoes:
            kind = _clean_single_line(item.get('kind'))
            ref = _clean_single_line(item.get('ref'))
            summary = _clean_single_line(item.get('summary'))
            if kind and ref and summary:
                lines.append(f' {kind} | {ref} | {summary}')
    else:
        lines.append('待播回响：（无）')
    block = '\n'.join(lines) + '\n'
    m = re.search(rf'(?m)({re.escape(SHOP_ANCHOR)}.*?)(?=\n【|\n▲ 第一层：|\Z)', content, re.S)
    if m:
        return content[:m.start(1)] + block + content[m.end(1):]
    for anchor in ('【回合生命周期】', '▲ 第一层：'):
        idx = content.find(anchor)
        if idx != -1:
            prefix = content[:idx]
            sep = '' if prefix.endswith('\n\n') else ('\n' if prefix.endswith('\n') else '\n\n')
            return prefix + sep + block + '\n' + content[idx:]
    return content.rstrip('\n') + '\n\n' + block


def append_echo(content, kind, ref, summary):
    shop_state = parse_shop_echo_block(content)
    k = _clean_single_line(kind)
    r = _clean_single_line(ref)
    s = _clean_single_line(summary)
    if not k or not r or not s:
        return content
    eid = f'{k}:{r}'
    echoes = [e for e in shop_state['echoes'] if e['id'] != eid]
    echoes.append({'id': eid, 'kind': k, 'ref': r, 'summary': s})
    shop_state['echoes'] = echoes[-SHOP_ECHO_LIMIT:]
    return write_shop_echo_block(content, shop_state)


def consume_echoes(content, consumed_ids):
    if not consumed_ids:
        return content
    wanted = set(consumed_ids)
    shop_state = parse_shop_echo_block(content)
    kept = [e for e in shop_state['echoes'] if e['id'] not in wanted]
    if len(kept) == len(shop_state['echoes']):
        return content
    shop_state['echoes'] = kept
    return write_shop_echo_block(content, shop_state)


def shop_catalog_path(root):
    cfg_path = Path(root) / 'txt文件/互动运行配置.json'
    if cfg_path.is_file():
        cfg = rr.load_request(cfg_path.read_text(encoding='utf-8'))
        shop_cfg = cfg.get('shop')
        if isinstance(shop_cfg, dict) and isinstance(shop_cfg.get('catalog'), str) and shop_cfg['catalog'].strip():
            return shop_cfg['catalog'].strip()
    return SHOP_CATALOG_DEFAULT


def _normalize_unlock_req(raw_req):
    if raw_req is None:
        return None
    if not isinstance(raw_req, dict):
        raise rr.RoundError('商城商品 unlock_req 须为对象或 null')
    rr._keys(raw_req, {'min_biz', 'min_any_affection', 'min_max_depravity', 'min_charm', 'mode'}, 'shop.unlock_req')
    out = {}
    for key in ('min_biz', 'min_any_affection', 'min_max_depravity', 'min_charm'):
        if key in raw_req and raw_req[key] is not None:
            rr._integer(raw_req[key], f'unlock_req.{key}', 0)
            if raw_req[key] > 0:
                out[key] = min(100, int(raw_req[key]))
    if not out:
        return None
    mode = str(raw_req.get('mode') or 'all').strip().lower()
    if mode not in ('all', 'any'):
        raise rr.RoundError('shop.unlock_req.mode 须为 all 或 any')
    if len(out) > 1:
        out['mode'] = mode
    return out


def read_shop_unlock_metrics(engine, memory_text):
    biz = engine._read_attr_value(memory_text, '系统宿主', '商业嗅觉')
    host_biz = max(0, int(biz)) if biz is not None else 0
    affs = {}
    for hname in save_store.HEROINES:
        val = engine._read_attr_value(memory_text, hname, '好感')
        affs[hname] = max(0, int(val)) if val is not None else 0
    return host_biz, affs


def read_shop_unlock_metrics_full(engine, memory_text):
    """Read all 4 progression axes used for shop unlock gating."""
    host_biz, affs = read_shop_unlock_metrics(engine, memory_text)
    charm_val = engine._read_attr_value(memory_text, '系统宿主', '魅力')
    host_charm = max(0, int(charm_val)) if charm_val is not None else 70
    deps = {}
    for hname in save_store.HEROINES:
        dval = engine._read_attr_value(memory_text, hname, '堕落')
        deps[hname] = max(0, int(dval)) if dval is not None else 0
    return {
        'host_biz': host_biz,
        'heroine_affs': affs,
        'heroine_deps': deps,
        'max_affection': max(affs.values()) if affs else 0,
        'max_depravity': max(deps.values()) if deps else 0,
        'host_charm': host_charm,
    }


def host_unlocked_shop_grade(host_biz, max_depravity=0, host_charm=70):
    """Determine the highest custom-shop grade tier the player currently qualifies to unlock."""
    biz = int(host_biz or 0)
    dep = int(max_depravity or 0)
    charm = int(host_charm or 70)
    if biz >= 55 or (dep >= 60 and charm >= 85):
        return 'T4'
    if biz >= 30 or (dep >= 30 and charm >= 78):
        return 'T3'
    if biz >= 15 or dep >= 10 or charm >= 75:
        return 'T2'
    return 'T1'


def evaluate_unlock_req(unlock_req, host_biz, heroine_affs, *, max_depravity=0, host_charm=70):
    if not unlock_req or not isinstance(unlock_req, dict):
        return {'unlocked': True, 'reason': '', 'hint': ''}
    min_biz = int(unlock_req.get('min_biz') or 0)
    min_aff = int(unlock_req.get('min_any_affection') or 0)
    min_dep = int(unlock_req.get('min_max_depravity') or 0)
    min_charm = int(unlock_req.get('min_charm') or 0)
    max_aff = max(heroine_affs.values()) if isinstance(heroine_affs, dict) and heroine_affs else 0
    cur_dep = max(0, int(max_depravity or 0))
    cur_charm = max(0, int(host_charm if host_charm is not None else 70))
    mode = str(unlock_req.get('mode') or 'all').strip().lower()
    checks = []
    parts = []
    if min_biz > 0:
        checks.append(host_biz >= min_biz)
        parts.append(f'商业嗅觉 ≥ {min_biz}（当前 {host_biz}）')
    if min_aff > 0:
        checks.append(max_aff >= min_aff)
        parts.append(f'任一女主好感 ≥ {min_aff}（最高 {max_aff}）')
    if min_dep > 0:
        checks.append(cur_dep >= min_dep)
        parts.append(f'最高堕落 ≥ {min_dep}（当前 {cur_dep}）')
    if min_charm > 0:
        checks.append(cur_charm >= min_charm)
        parts.append(f'宿主魅力 ≥ {min_charm}（当前 {cur_charm}）')
    if not checks:
        return {'unlocked': True, 'reason': '', 'hint': ''}
    unlocked = any(checks) if mode == 'any' else all(checks)
    joiner = ' 或 ' if mode == 'any' else ' 且 '
    hint = '需' + joiner.join(parts)
    return {
        'unlocked': unlocked,
        'reason': '' if unlocked else f'尚未满足解锁门槛：{hint}',
        'hint': hint,
    }


def load_shop_catalog(root, optional=False):
    """Load and strictly validate the authoritative deterministic shop catalog."""
    rel = shop_catalog_path(root)
    path = Path(root) / rel
    if not path.is_file():
        if optional:
            return {'version': 1, 'tiers': {}, 'categories': {}, 'items': [], 'source': rel}
        raise rr.RoundError('缺少权威系统商城目录：' + rel)
    raw = rr.load_request(path.read_text(encoding='utf-8'))
    rr._keys(raw, {'version', 'tiers', 'categories', 'items'}, '系统商城目录', {'version', 'items'})
    if raw.get('version') != 1 or not isinstance(raw.get('items'), list):
        raise rr.RoundError('系统商城目录版本或结构无效')
    seen_ids = set()
    seen_names = set()
    required_item = {'id', 'name', 'tier', 'price', 'type', 'desc', 'duration', 'expire_rule', 'system_effect', 'giftable', 'max_per_save'}
    optional_item = {'category', 'usage_mode', 'pack_qty', 'unlock_req'}
    normalized = []
    for entry in raw['items']:
        rr._keys(entry, required_item | optional_item, '商城商品', required_item)
        sid = entry['id']
        if not isinstance(sid, str) or not re.fullmatch(r'SHOP-\d+', sid) or sid in seen_ids:
            raise rr.RoundError('商城商品ID无效或重复: ' + str(sid))
        seen_ids.add(sid)
        name = rr._text(entry['name'], 'shop.name', 60).strip()
        if name in seen_names:
            raise rr.RoundError('商城商品名称重复: ' + name)
        seen_names.add(name)
        tier = entry['tier']
        if tier not in SHOP_TIER_RANGES:
            raise rr.RoundError('商城商品档位非法: ' + str(tier))
        price = entry['price']
        rr._integer(price, 'shop.price', 1)
        lo, hi = SHOP_TIER_RANGES[tier]
        if not lo <= price <= hi:
            raise rr.RoundError(f'商城商品 {sid} 价格 {price} 与档位 {tier}({lo}~{hi}) 不符')
        item_type = rr._text(entry['type'], 'shop.type', 40).strip()
        desc = rr._text(entry['desc'], 'shop.desc', 240).strip()
        duration = rr._text(entry['duration'], 'shop.duration', 20).strip()
        expire_rule = rr._text(entry['expire_rule'], 'shop.expire_rule', 80).strip()
        eff = entry['system_effect']
        if not isinstance(eff, str) or (eff and not VALID_SYSTEM_EFFECT_RE.fullmatch(eff)):
            raise rr.RoundError('商城商品系统效果未登记: ' + str(eff))
        if type(entry['giftable']) is not bool:
            raise rr.RoundError('商城商品giftable须为布尔值')
        cap = entry['max_per_save']
        if cap is not None:
            rr._integer(cap, 'shop.max_per_save', 1)
        pack_qty = entry.get('pack_qty', 1)
        rr._integer(pack_qty, 'shop.pack_qty', 1)
        if pack_qty > 10:
            raise rr.RoundError('商城商品单次兑换份数上限为10: ' + sid)
        category = str(entry.get('category') or 'daily').strip() or 'daily'
        if category not in ('daily', 'sensual', 'covert'):
            raise rr.RoundError('商城商品分类非法: ' + category)
        usage_mode = save_store.infer_usage_mode(eff, entry['giftable'], entry.get('usage_mode', ''))
        if entry.get('usage_mode') and entry['usage_mode'] not in save_store.VALID_USAGE_MODES:
            raise rr.RoundError('商城商品使用模式非法: ' + str(entry['usage_mode']))
        unlock_req = _normalize_unlock_req(entry.get('unlock_req'))
        for field_text in (name, desc, expire_rule):
            if SHOP_FORBIDDEN_DURATION_RE.search(field_text):
                raise rr.RoundError('商城商品违反红线（禁止修改状态持续时间）: ' + sid)
        normalized.append({
            'id': sid, 'name': name, 'tier': tier, 'category': category,
            'usage_mode': usage_mode, 'pack_qty': pack_qty, 'price': price,
            'type': item_type, 'desc': desc, 'duration': duration,
            'expire_rule': expire_rule, 'system_effect': eff,
            'giftable': entry['giftable'], 'max_per_save': cap,
            'unlock_req': unlock_req, 'source': 'static',
        })
    tiers = raw.get('tiers') if isinstance(raw.get('tiers'), dict) else {}
    categories = raw.get('categories') if isinstance(raw.get('categories'), dict) else {}
    return {'version': 1, 'tiers': copy.deepcopy(tiers), 'categories': copy.deepcopy(categories), 'items': normalized, 'source': rel}


def _extract_json_object_text(raw_text):
    if isinstance(raw_text, dict):
        return raw_text
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise rr.RoundError('AI进货返回为空')
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', raw_text, flags=re.I).strip()
    candidates = []
    for fm in re.finditer(r'```(?:json)?\s*([\s\S]*?)```', cleaned, flags=re.I):
        if fm.group(1).strip():
            candidates.append(fm.group(1).strip())
    candidates.append(cleaned)
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(cleaned[first_brace:last_brace + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    raise rr.RoundError('AI进货返回不是合法 JSON 对象')


def apply_scene_shop_adds(st, root, shop_adds, *, query=''):
    """Validate and append in-story custom shop items (from scene_state.shop_adds) into st['shop']['dynamic_catalog']."""
    if not isinstance(shop_adds, list) or not shop_adds:
        return {'added': [], 'rejected': []}
    catalog = load_shop_catalog(root, optional=True)
    shop_obj = st.setdefault('shop', {'redeemed': {}, 'recent': [], 'echoes': [], 'dynamic_catalog': [], 'next_dyn_seq': 1})
    existing_dyn = list(shop_obj.get('dynamic_catalog') or [])
    existing_names = [it['name'] for it in catalog.get('items', [])] + [
        it.get('name', '') for it in existing_dyn if isinstance(it, dict) and it.get('name')
    ]
    next_seq = max(
        int(shop_obj.get('next_dyn_seq') or 1),
        max((int(m.group(1)) for it in existing_dyn if isinstance(it, dict)
             for m in (re.fullmatch(r'DYN-(\d+)', str(it.get('id') or '')),) if m), default=0) + 1,
    )
    try:
        validated = validate_dynamic_shop_items(
            {'shopkeeper_reply': '', 'items': shop_adds},
            existing_names,
            next_seq,
            query=query,
        )
    except rr.RoundError as exc:
        return {'added': [], 'rejected': [str(exc)]}
    merged_dyn = (existing_dyn + validated['items'])[-SHOP_DYNAMIC_LIMIT:]
    shop_obj['dynamic_catalog'] = merged_dyn
    shop_obj['next_dyn_seq'] = validated['next_dyn_seq']
    return {'added': validated['items'], 'rejected': validated['rejected_reasons']}


def validate_dynamic_shop_items(raw_payload, existing_names, next_seq, *, query=''):
    """Deterministically validate, sanitize, price-clamp, and anti-cheat-filter custom shop items."""
    obj = _extract_json_object_text(raw_payload)
    reply = _clean_single_line(obj.get('shopkeeper_reply') or '')[:120]
    raw_items = obj.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        raise rr.RoundError('定制进货未返回任何有效商品条目')
    seen_names = {str(n).strip().casefold() for n in (existing_names or ()) if str(n).strip()}
    seq = max(1, int(next_seq or 1))
    clean_items = []
    rejected = []

    for entry in raw_items[:4]:
        if not isinstance(entry, dict):
            rejected.append('条目非对象')
            continue
        name = _clean_single_line(entry.get('name') or '')[:32]
        desc = _clean_single_line(entry.get('desc') or '')[:180]
        if len(name) < 2 or len(desc) < 6:
            rejected.append(f'{name or "空名"}:名称或描述过短')
            continue
        if name.casefold() in seen_names:
            rejected.append(f'{name}:与现有货架重名')
            continue
        raw_eff = _clean_single_line(entry.get('system_effect') or '')
        combined_text = f'{name} {desc} {raw_eff}'
        if SHOP_FORBIDDEN_DURATION_RE.search(combined_text) or SHOP_FORBIDDEN_DYN_RE.search(combined_text):
            rejected.append(f'{name}:触碰防崩与非修改器底线（自定义道具仅可间接辅助，严禁直接增减属性数值或篡改时效）')
            continue
        usage_mode = str(entry.get('usage_mode') or '').strip()
        if usage_mode not in ('gift', 'consumable_target', 'reusable_tool', 'deployable_device'):
            if raw_eff.startswith('deploy_device:'):
                usage_mode = 'deployable_device'
            elif raw_eff.startswith('buff:'):
                usage_mode = 'consumable_target'
            else:
                usage_mode = 'gift'
        category = str(entry.get('category') or '').strip()
        if category not in ('sensual', 'covert', 'daily'):
            category = 'covert' if usage_mode == 'deployable_device' else 'sensual'
        # Validate and sanitize system_effect (never allow host_stamina on AI restocked items)
        eff = ''
        if raw_eff.startswith('host_stamina:'):
            eff = ''
        elif raw_eff and VALID_SYSTEM_EFFECT_RE.fullmatch(raw_eff):
            if raw_eff.startswith('buff:'):
                parts = raw_eff.split(':', 3)
                bname = parts[1].strip()[:12]
                bturns = max(1, min(3, int(parts[2])))
                bdesc = parts[3].strip()[:55]
                eff = f'buff:{bname}:{bturns}:{bdesc}'
            elif raw_eff.startswith('deploy_device:'):
                eff = raw_eff
        if usage_mode == 'deployable_device' and not eff.startswith('deploy_device:'):
            eff = 'deploy_device:audio' if re.search(r'录音|拾音|窃听|麦克风', combined_text) else (
                'deploy_device:aroma' if re.search(r'扩香|香薰机|香氛机', combined_text) else 'deploy_device:camera'
            )
        if usage_mode != 'deployable_device' and eff.startswith('deploy_device:'):
            usage_mode = 'deployable_device'
            category = 'covert'
        # Infer deterministic T1-T4 custom item grade (prevents Turn-1 OP item / low-price cheese)
        try:
            raw_price = int(entry.get('price'))
        except (TypeError, ValueError):
            raw_price = 24
        ai_grade = str(entry.get('grade') or '').strip().upper()
        if ai_grade not in SHOP_GRADE_ORDER:
            ai_grade = 'T1'
        bturns_now = int(eff.split(':', 3)[2]) if eff.startswith('buff:') else 0
        min_grade = 'T1'
        if SHOP_GRADE_T4_RE.search(combined_text) or raw_price >= 150:
            min_grade = 'T4'
        elif (
            usage_mode == 'deployable_device'
            or eff.startswith('deploy_device:')
            or bturns_now >= 3
            or SHOP_GRADE_T3_RE.search(combined_text)
            or raw_price >= 65
        ):
            min_grade = 'T3'
        elif (
            category in ('sensual', 'covert')
            or eff.startswith('buff:')
            or usage_mode == 'consumable_target'
            or SHOP_GRADE_T2_RE.search(combined_text)
            or raw_price >= 32
        ):
            min_grade = 'T2'
        grade = ai_grade if SHOP_GRADE_ORDER[ai_grade] >= SHOP_GRADE_ORDER[min_grade] else min_grade
        gmeta = SHOP_GRADE_META[grade]

        # Enforce grade-specific system_effect bounds
        if grade == 'T1':
            if eff.startswith('deploy_device:'):
                grade = 'T3'
                gmeta = SHOP_GRADE_META[grade]
            elif eff.startswith('buff:'):
                parts = eff.split(':', 3)
                eff = f'buff:{parts[1]}:1:{parts[3]}'
        elif grade == 'T2' and eff.startswith('buff:') and bturns_now > 2:
            parts = eff.split(':', 3)
            eff = f'buff:{parts[1]}:2:{parts[3]}'

        # Deterministic price clamping + tier alignment per grade (avoiding 51..59 gap)
        price = max(gmeta['min_price'], min(gmeta['max_price'], raw_price))
        if 51 <= price <= 59:
            price = 60
        tier = 'low' if price <= 10 else ('mid' if price <= 50 else 'high')

        try:
            pack_qty = int(entry.get('pack_qty') or 1)
        except (TypeError, ValueError):
            pack_qty = 1
        pack_qty = max(1, min(3, pack_qty)) if usage_mode == 'consumable_target' else 1
        try:
            max_cap = int(entry.get('max_per_save') or gmeta['max_per_save'])
        except (TypeError, ValueError):
            max_cap = gmeta['max_per_save']
        max_cap = max(1, min(gmeta['max_per_save'], max_cap))

        # Sanitize & floor-enforce 4-axis unlock_req per grade (prevents Turn-1 95-affection bypass)
        req_in = entry.get('unlock_req') if isinstance(entry.get('unlock_req'), dict) else {}
        def _clamp_req(k, hi=100):
            try:
                return max(0, min(hi, int(req_in.get(k) or 0)))
            except (TypeError, ValueError):
                return 0
        min_biz = _clamp_req('min_biz', 100)
        min_aff = _clamp_req('min_any_affection', 100)
        min_dep = _clamp_req('min_max_depravity', 100)
        min_charm = _clamp_req('min_charm', 100)
        mode_req = str(req_in.get('mode') or 'all').strip().lower()
        if mode_req not in ('all', 'any'):
            mode_req = 'all'

        is_strategic_or_covert = (category in ('covert', 'daily') or usage_mode == 'deployable_device')
        if grade == 'T2':
            # Reachable via any one of biz/depravity/charm progression axes
            if min_biz < 15 and min_dep < 10 and min_charm < 75:
                min_biz = max(min_biz, 15)
                min_dep = max(min_dep, 10)
                min_charm = max(min_charm, 75)
                min_aff = 0
                mode_req = 'any'
        elif grade == 'T3':
            min_aff = 0
            mode_req = 'all'
            if is_strategic_or_covert:
                min_biz = max(min_biz, 30)
            else:
                min_dep = max(min_dep, 30)
                min_charm = max(min_charm, 78)
        elif grade == 'T4':
            min_aff = 0
            mode_req = 'all'
            if is_strategic_or_covert:
                min_biz = max(min_biz, 55)
            else:
                min_dep = max(min_dep, 60)
                min_charm = max(min_charm, 85)

        unlock_req = None
        if min_biz > 0 or min_aff > 0 or min_dep > 0 or min_charm > 0:
            unlock_req = {}
            if min_biz > 0:
                unlock_req['min_biz'] = min_biz
            if min_aff > 0:
                unlock_req['min_any_affection'] = min_aff
            if min_dep > 0:
                unlock_req['min_max_depravity'] = min_dep
            if min_charm > 0:
                unlock_req['min_charm'] = min_charm
            if len(unlock_req) > 1:
                unlock_req['mode'] = mode_req
        did = f'DYN-{seq:03d}'
        seq += 1
        seen_names.add(name.casefold())
        is_cons = (usage_mode == 'consumable_target')
        clean_items.append({
            'id': did,
            'name': name,
            'grade': grade,
            'grade_label': gmeta['short'],
            'tier': tier,
            'category': category,
            'usage_mode': usage_mode,
            'pack_qty': pack_qty,
            'price': price,
            'type': '临时性（消耗品）' if is_cons else '永久性',
            'desc': desc,
            'duration': '无',
            'expire_rule': '消耗归零后归档' if is_cons else '无',
            'system_effect': eff,
            'giftable': (usage_mode == 'gift'),
            'max_per_save': max_cap,
            'unlock_req': unlock_req,
            'source': 'ai_restock',
            'query': _clean_single_line(query)[:80],
        })
        if len(clean_items) >= 3:
            break

    if not clean_items:
        detail = '；'.join(rejected[:3]) if rejected else '无符合规范的条目'
        raise rr.RoundError('本次定制商品均未通过防崩与平衡校验：' + detail)
    if not reply:
        reply = f"已为你调货上架 {len(clean_items)} 件新品：{'、'.join(it['name'] for it in clean_items)}。"
    return {
        'shopkeeper_reply': reply,
        'items': clean_items,
        'next_dyn_seq': seq,
        'rejected_reasons': rejected,
    }


def intel_catalog_path(root):
    cfg_path = Path(root) / 'txt文件/互动运行配置.json'
    if cfg_path.is_file():
        cfg = rr.load_request(cfg_path.read_text(encoding='utf-8'))
        intel_cfg = cfg.get('intel')
        if isinstance(intel_cfg, dict) and isinstance(intel_cfg.get('catalog'), str) and intel_cfg['catalog'].strip():
            return intel_cfg['catalog'].strip()
    return INTEL_CATALOG_DEFAULT


def load_intel_catalog(root, optional=False):
    """Load and validate authoritative commercial intel catalog."""
    rel = intel_catalog_path(root)
    path = Path(root) / rel
    if not path.is_file():
        if optional:
            return {'version': 1, 'leverage_min_biz': 60, 'items': [], 'source': rel}
        raise rr.RoundError('缺少权威商业情报目录：' + rel)
    raw = rr.load_request(path.read_text(encoding='utf-8'))
    rr._keys(raw, {'version', 'leverage_min_biz', 'items'}, '商业情报目录', {'version', 'items'})
    if raw.get('version') != 1 or not isinstance(raw.get('items'), list):
        raise rr.RoundError('商业情报目录版本或结构无效')
    leverage_min = int(raw.get('leverage_min_biz', 60))
    seen_ids = set()
    items = []
    req = {'id', 'name', 'min_biz', 'min_su_ab_contacts', 'desc', 'effect_summary', 'effects'}
    for entry in raw['items']:
        rr._keys(entry, req, '商业情报条目', req)
        iid = entry['id']
        if not isinstance(iid, str) or not re.fullmatch(r'INTEL-\d+', iid) or iid in seen_ids:
            raise rr.RoundError('商业情报ID无效或重复: ' + str(iid))
        seen_ids.add(iid)
        items.append({
            'id': iid,
            'name': rr._text(entry['name'], 'intel.name', 60).strip(),
            'min_biz': int(entry['min_biz']),
            'min_su_ab_contacts': int(entry['min_su_ab_contacts']),
            'desc': rr._text(entry['desc'], 'intel.desc', 240).strip(),
            'effect_summary': rr._text(entry['effect_summary'], 'intel.effect_summary', 240).strip(),
            'effects': copy.deepcopy(entry['effects']),
        })
    return {'version': 1, 'leverage_min_biz': leverage_min, 'items': items, 'source': rel}


def parse_intel_block(content):
    """Parse 【商业情报与杠杆状态】 from 全局记忆库.txt; missing block defaults cleanly."""
    out = {'held': [], 'consumed': [], 'su_ab_contacts': 0, 'leverage_armed': '', 'leverage_charges': 0}
    if not content or INTEL_ANCHOR not in content:
        return out
    m = re.search(rf'(?m)({re.escape(INTEL_ANCHOR)}.*?)(?=\n【|\n▲ 第一层：|\Z)', content, re.S)
    if not m:
        return out
    block = m.group(1)
    hm = re.search(r'^持有情报：([^\n]+)', block, re.M)
    if hm and hm.group(1).strip() not in ('（无）', '(无)', '无', ''):
        out['held'] = list(dict.fromkeys(re.findall(r'INTEL-\d+', hm.group(1))))
    cm = re.search(r'^已耗情报：([^\n]+)', block, re.M)
    if cm and cm.group(1).strip() not in ('（无）', '(无)', '无', ''):
        out['consumed'] = list(dict.fromkeys(re.findall(r'INTEL-\d+', cm.group(1))))
    sm = re.search(r'^苏婉青AB接触：\s*(\d+)', block, re.M)
    if sm:
        out['su_ab_contacts'] = int(sm.group(1))
    lm = re.search(r'^商业杠杆预备：([^\n]+)', block, re.M)
    if lm:
        im = re.search(r'INTEL-\d+', lm.group(1))
        if im and im.group(0) in out['held']:
            out['leverage_armed'] = im.group(0)
    lcm = re.search(r'^商业杠杆护盾：[^\n]*?(\d+)', block, re.M)
    if lcm:
        out['leverage_charges'] = max(0, min(3, int(lcm.group(1))))
    return out


def write_intel_block(content, intel_state, catalog=None):
    """Write 【商业情报与杠杆状态】 cleanly into pre-L1 region after 【商城与回响状态】."""
    name_map = {it['id']: it['name'] for it in (catalog or {}).get('items', [])}
    held = list(dict.fromkeys(intel_state.get('held') or []))
    consumed = list(dict.fromkeys(x for x in (intel_state.get('consumed') or []) if x not in held))
    su_ab = max(0, int(intel_state.get('su_ab_contacts') or 0))
    armed = str(intel_state.get('leverage_armed') or '')
    if armed not in held:
        armed = ''
    charges = max(0, min(3, int(intel_state.get('leverage_charges', 0) or 0)))
    def fmt_id(iid):
        return f'{iid}({name_map[iid]})' if iid in name_map else iid
    lines = [
        INTEL_ANCHOR,
        '持有情报：' + (' | '.join(fmt_id(i) for i in held) if held else '（无）'),
        '已耗情报：' + (' | '.join(fmt_id(i) for i in consumed) if consumed else '（无）'),
        f'苏婉青AB接触：{su_ab}',
        f'商业杠杆预备：已预备({fmt_id(armed)})' if armed else '商业杠杆预备：未启用',
    ]
    if charges > 0:
        lines.append(f'商业杠杆护盾：剩余 {charges} 次')
    block = '\n'.join(lines) + '\n'
    m = re.search(rf'(?m)({re.escape(INTEL_ANCHOR)}.*?)(?=\n【|\n▲ 第一层：|\Z)', content, re.S)
    if m:
        return content[:m.start(1)] + block + content[m.end(1):]
    for anchor in ('【回合生命周期】', '▲ 第一层：'):
        idx = content.find(anchor)
        if idx != -1:
            prefix = content[:idx]
            sep = '' if prefix.endswith('\n\n') else ('\n' if prefix.endswith('\n') else '\n\n')
            return prefix + sep + block + '\n' + content[idx:]
    return content.rstrip('\n') + '\n\n' + block


def director_config(root):
    cfg = copy.deepcopy(DIRECTOR_DEFAULTS)
    cfg_path = Path(root) / 'txt文件/互动运行配置.json'
    if cfg_path.is_file():
        raw = rr.load_request(cfg_path.read_text(encoding='utf-8'))
        d = raw.get('director')
        if isinstance(d, dict):
            for k, v in d.items():
                if k in cfg:
                    cfg[k] = copy.deepcopy(v)
    return cfg


def load_world_beats(root, optional=True):
    cfg = director_config(root)
    rel = str(cfg.get('catalog') or DIRECTOR_CATALOG_DEFAULT).strip()
    path = Path(root) / rel
    if not path.is_file():
        if optional:
            return {
                'version': 1, 'beats': [], 'channels': dict(DIRECTOR_DEFAULT_CHANNELS),
                'spark_matrix': {}, 'sensual_spark_matrix': {}, 'offstage_clocks': {}, 'source': rel,
            }
        raise rr.RoundError('缺少世界变故库：' + rel)
    raw = rr.load_request(path.read_text(encoding='utf-8'))
    beats = raw.get('beats')
    if not isinstance(beats, list):
        raise rr.RoundError('世界变故库结构无效')
    channels = raw.get('channels') if isinstance(raw.get('channels'), dict) else dict(DIRECTOR_DEFAULT_CHANNELS)
    spark_matrix = raw.get('spark_matrix') if isinstance(raw.get('spark_matrix'), dict) else {}
    sensual_spark_matrix = raw.get('sensual_spark_matrix') if isinstance(raw.get('sensual_spark_matrix'), dict) else {}
    offstage_clocks = raw.get('offstage_clocks') if isinstance(raw.get('offstage_clocks'), dict) else {}
    return {
        'version': int(raw.get('version', 1)),
        'beats': beats,
        'channels': channels,
        'spark_matrix': spark_matrix,
        'sensual_spark_matrix': sensual_spark_matrix,
        'offstage_clocks': offstage_clocks,
        'source': rel,
    }


def _default_director_state():
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


def parse_director_block(content):
    """Parse 【世界导演状态】 compact JSON from 全局记忆库.txt; missing block or legacy v1 fields default cleanly."""
    out = _default_director_state()
    if not content or DIRECTOR_ANCHOR not in content:
        return out
    m = re.search(rf'(?m)^{re.escape(DIRECTOR_ANCHOR)}[ \t]*\n([^\n]+)', content)
    if not m:
        return out
    try:
        raw = json.loads(m.group(1).strip())
    except ValueError:
        return out
    if not isinstance(raw, dict):
        return out
    for int_k in ('calm_streak', 'global_cooldown', 'turns_since_beat', 'scene_turns', 'clock_tick_acc', 'sensual_drought', 'heroine_cd'):
        val = raw.get(int_k)
        if type(val) is int and val >= 0:
            out[int_k] = val
    if isinstance(raw.get('scene_location'), str):
        out['scene_location'] = raw['scene_location']
    if raw.get('last_time_slot') in ('', 'morning', 'afternoon', 'evening', 'night'):
        out['last_time_slot'] = raw['last_time_slot']
    if isinstance(raw.get('event_cooldowns'), dict):
        out['event_cooldowns'] = {
            str(k): int(v) for k, v in raw['event_cooldowns'].items()
            if isinstance(k, str) and type(v) is int and v > 0
        }
    if isinstance(raw.get('consumed_once'), list):
        out['consumed_once'] = list(dict.fromkeys(str(x) for x in raw['consumed_once'] if isinstance(x, str) and x))
    if isinstance(raw.get('pending_seeds'), list):
        seeds = []
        for s in raw['pending_seeds']:
            if isinstance(s, dict) and isinstance(s.get('seed_id'), str) and s['seed_id']:
                seeds.append({
                    'seed_id': s['seed_id'],
                    'summary': str(s.get('summary') or '')[:120],
                    'age': int(s.get('age') or 0) if type(s.get('age', 0)) is int else 0,
                })
        out['pending_seeds'] = seeds[-DIRECTOR_SEED_LIMIT:]
    max_seq = 0
    if isinstance(raw.get('active_threads'), list):
        threads = []
        seen_ids = set()
        for t in raw['active_threads']:
            if not isinstance(t, dict):
                continue
            tid = str(t.get('id') or '').strip()
            topic = _clean_single_line(t.get('topic') or '')[:60]
            if not tid or not topic or tid in seen_ids:
                continue
            seen_ids.add(tid)
            who_raw = t.get('who') if isinstance(t.get('who'), list) else []
            who = [str(w).strip() for w in who_raw if isinstance(w, str) and str(w).strip() in DIRECTOR_VALID_PEOPLE]
            tension = 'hard' if t.get('tension') == 'hard' else 'soft'
            age = t.get('age') if type(t.get('age')) is int and t.get('age') >= 0 else 0
            touches = t.get('touches') if type(t.get('touches')) is int and t.get('touches') >= 0 else 0
            threads.append({
                'id': tid, 'who': who, 'topic': topic,
                'tension': tension, 'age': age, 'touches': touches,
            })
            tm = re.fullmatch(r'TH-(\d+)', tid)
            if tm:
                max_seq = max(max_seq, int(tm.group(1)))
        out['active_threads'] = threads[-8:]
    seq_val = raw.get('next_thread_seq')
    if type(seq_val) is int and seq_val >= 1:
        out['next_thread_seq'] = max(seq_val, max_seq + 1)
    else:
        out['next_thread_seq'] = max(1, max_seq + 1)
    if isinstance(raw.get('offstage_clocks'), dict):
        clocks = {}
        for cid, cst in raw['offstage_clocks'].items():
            if not isinstance(cid, str) or not cid or not isinstance(cst, dict):
                continue
            p_val = cst.get('p') if type(cst.get('p')) is int and cst.get('p') >= 0 else 0
            ph_val = cst.get('ph') if type(cst.get('ph')) is int and cst.get('ph') >= 0 else 0
            so_val = bool(cst.get('so'))
            cd_val = cst.get('cd') if type(cst.get('cd')) is int and cst.get('cd') >= 0 else 0
            clocks[cid] = {'p': p_val, 'ph': ph_val, 'so': so_val, 'cd': cd_val}
        out['offstage_clocks'] = clocks
    if isinstance(raw.get('recent_channels'), list):
        out['recent_channels'] = [str(c).strip() for c in raw['recent_channels'] if isinstance(c, str) and c.strip()][-8:]
    return out


def write_director_block(content, dstate):
    """Write 【世界导演状态】 cleanly into pre-L1 region before 【回合生命周期】 or ▲ 第一层：."""
    clean = _default_director_state()
    clean.update({
        'calm_streak': max(0, int(dstate.get('calm_streak', 0))),
        'global_cooldown': max(0, int(dstate.get('global_cooldown', 0))),
        'turns_since_beat': max(0, int(dstate.get('turns_since_beat', 99))),
        'scene_location': str(dstate.get('scene_location') or ''),
        'scene_turns': max(0, int(dstate.get('scene_turns', 0))),
        'clock_tick_acc': max(0, int(dstate.get('clock_tick_acc', 0))),
        'sensual_drought': max(0, int(dstate.get('sensual_drought', 0))),
        'heroine_cd': max(0, int(dstate.get('heroine_cd', 0))),
        'last_time_slot': str(dstate.get('last_time_slot') or '') if dstate.get('last_time_slot') in ('', 'morning', 'afternoon', 'evening', 'night') else '',
        'event_cooldowns': {k: int(v) for k, v in (dstate.get('event_cooldowns') or {}).items() if int(v) > 0},
        'consumed_once': list(dict.fromkeys(str(x) for x in (dstate.get('consumed_once') or []) if x)),
        'pending_seeds': list(dstate.get('pending_seeds') or [])[-DIRECTOR_SEED_LIMIT:],
        'active_threads': list(dstate.get('active_threads') or [])[-8:],
        'next_thread_seq': max(1, int(dstate.get('next_thread_seq', 1))),
        'offstage_clocks': {
            str(k): {
                'p': max(0, int(v.get('p', 0))),
                'ph': max(0, int(v.get('ph', 0))),
                'so': bool(v.get('so', False)),
                'cd': max(0, int(v.get('cd', 0))),
            }
            for k, v in (dstate.get('offstage_clocks') or {}).items()
            if isinstance(k, str) and k and isinstance(v, dict)
        },
        'recent_channels': [str(c) for c in (dstate.get('recent_channels') or []) if isinstance(c, str) and c][-8:],
    })
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    block = DIRECTOR_ANCHOR + '\n' + encoded + '\n'
    m = re.search(rf'(?m)({re.escape(DIRECTOR_ANCHOR)}[ \t]*\n[^\n]*\n?)', content)
    if m:
        return content[:m.start(1)] + block + content[m.end(1):]
    for anchor in ('【回合生命周期】', '▲ 第一层：'):
        idx = content.find(anchor)
        if idx != -1:
            prefix = content[:idx]
            sep = '' if prefix.endswith('\n\n') else ('\n' if prefix.endswith('\n') else '\n\n')
            return prefix + sep + block + '\n' + content[idx:]
    return content.rstrip('\n') + '\n\n' + block


def _clock_time_slot(clock):
    if not isinstance(clock, dict) or not isinstance(clock.get('time'), str) or ':' not in clock['time']:
        return 'morning'
    try:
        hour = int(clock['time'].split(':', 1)[0])
    except ValueError:
        return 'morning'
    if 6 <= hour < 12:
        return 'morning'
    if 12 <= hour < 18:
        return 'afternoon'
    if 18 <= hour < 23:
        return 'evening'
    return 'night'


def _is_boundary_window(clock, weekday):
    if not isinstance(clock, dict) or not isinstance(clock.get('time'), str) or ':' not in clock['time']:
        return False
    try:
        h, m = map(int, clock['time'].split(':', 1))
    except ValueError:
        return False
    hhmm = h * 60 + m
    is_workday = weekday in ('周一', '周二', '周三', '周四', '周五')
    if is_workday and (945 <= hhmm <= 980 or 1005 <= hhmm <= 1040):
        return True  # 沈知韫下班交界 / 徐念薇转工作室交界
    if (weekday in ('周二', '周五') and 930 <= hhmm <= 1110) or (weekday == '周日' and 600 <= hhmm <= 900):
        return True  # 苏婉青请安窗
    if hhmm >= 1380 or hhmm < 120:
        return True  # 深夜 23:00-02:00
    return False


def _weighted_choice(weighted_items, gen):
    total = sum(max(0.0, float(w)) for _, w in weighted_items)
    if total <= 0.0:
        return weighted_items[0][0]
    pick = gen.random() * total
    acc = 0.0
    for item, w in weighted_items:
        acc += max(0.0, float(w))
        if pick <= acc:
            return item
    return weighted_items[-1][0]


def _extract_latest_l1_snippet(memory_text):
    if not memory_text or '▲ 第一层：' not in memory_text:
        return ''
    body = memory_text.split('▲ 第一层：', 1)[1].split('▲ 第二层：', 1)[0]
    lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith('【即时运存区】')]
    for ln in reversed(lines):
        if ln in ('（空）', '无', '- 无') or ln.startswith('【系统隐藏标记：'):
            continue
        cleaned = save_store.strip_prologue_marker(ln)
        cleaned = re.sub(r'^[•\-\*]+\s*', '', cleaned)
        cleaned = re.sub(r'^【\d+】(?:[^｜|]*[｜|]\s*)?', '', cleaned).strip()
        if len(cleaned) >= 6:
            return cleaned[:46]
    return ''


def _thread_topic_similar(a, b):
    sa = re.sub(r'[\s，。！？、：；“”"\'（）()\[\]]+', '', str(a or ''))
    sb = re.sub(r'[\s，。！？、：；“”"\'（）()\[\]]+', '', str(b or ''))
    if not sa or not sb:
        return False
    if sa in sb or sb in sa:
        return True
    if len(sa) < 3 or len(sb) < 3:
        return sa == sb
    ga = {sa[i:i + 2] for i in range(len(sa) - 1)}
    gb = {sb[i:i + 2] for i in range(len(sb) - 1)}
    inter = len(ga & gb)
    union = len(ga | gb)
    return bool(union and (inter / union) >= 0.55)


_ECHO_WILL_SECRET_RE = re.compile(
    r'唯一合法继承人|唯一继承人|亲生子继承|继承真相|千亿家产唯一'
    r'|遗嘱[^\n。！？]{0,12}(?:指定|写着|留给|归|给了|继承|家产|份额)'
    r'|(?:志北|亲生子|继承权)[^\n。！？]{0,10}遗嘱'
)


def _sanitize_director_echo(raw, catalog, dstate, is_action, *, secrets_unlocked=()):
    """Fault-tolerant whitelist sanitizer for optional resolution.director_echo; never raises RoundError."""
    if not is_action or raw in (None, '') or not isinstance(raw, dict):
        return None
    out = {}
    channels_map = (catalog or {}).get('channels') or DIRECTOR_DEFAULT_CHANNELS
    clocks_cfg = (catalog or {}).get('offstage_clocks') or {}
    active_ids = {t['id'] for t in (dstate or {}).get('active_threads', []) if isinstance(t, dict) and t.get('id')}
    k01_open = 'K01' in set(secrets_unlocked or ())

    nt = raw.get('new_thread')
    if isinstance(nt, dict):
        topic = _clean_single_line(nt.get('topic') or '')[:48]
        if len(topic) >= 4 and topic not in ('无', '暂无', '（空）', '空', 'none', 'null'):
            who_raw = nt.get('who')
            if isinstance(who_raw, str):
                who_raw = [who_raw]
            who = []
            if isinstance(who_raw, list):
                for w in who_raw:
                    ws = str(w).strip()
                    if ws in DIRECTOR_VALID_PEOPLE and ws not in who:
                        who.append(ws)
            k01_leak = (not k01_open) and bool(_ECHO_WILL_SECRET_RE.search(topic)) and (not who or any(w != '沈知韫' for w in who))
            if not k01_leak:
                tension = 'hard' if nt.get('tension') == 'hard' else 'soft'
                out['new_thread'] = {'who': who, 'topic': topic, 'tension': tension}

    ct = raw.get('close_thread')
    closed = []
    if isinstance(ct, str) and ct.strip() in active_ids:
        closed.append(ct.strip())
    elif isinstance(ct, list):
        for item in ct:
            if isinstance(item, str) and item.strip() in active_ids and item.strip() not in closed:
                closed.append(item.strip())
    if closed:
        out['close_thread'] = closed

    cn = raw.get('clock_nudges')
    if isinstance(cn, dict):
        nudges = {}
        for cid, delta in cn.items():
            if cid in clocks_cfg and type(delta) is int and delta != 0:
                nudges[cid] = 1 if delta > 0 else -1
        if nudges:
            out['clock_nudges'] = nudges

    uc = raw.get('used_channel')
    if isinstance(uc, str) and uc.strip() in channels_map:
        out['used_channel'] = uc.strip()

    mu = raw.get('mind_updates')
    if isinstance(mu, dict):
        clean_mu = {}
        invalid_tokens = {'无', '暂无', '（空）', '空', 'none', 'null', '无变化'}
        for who, patch in mu.items():
            wname = str(who).strip()
            if wname not in save_store.NPC_MIND_TARGETS or not isinstance(patch, dict):
                continue
            entry = {}
            for field, limit in (('mood', 40), ('preoccupation', 48), ('impression', 48)):
                val = patch.get(field)
                if isinstance(val, str):
                    txt = _clean_single_line(val)[:limit]
                    if len(txt) >= 3 and txt.lower() not in invalid_tokens:
                        if (not k01_open) and wname != '沈知韫' and _ECHO_WILL_SECRET_RE.search(txt):
                            continue
                        entry[field] = txt
            if entry:
                clean_mu[wname] = entry
        if clean_mu:
            out['mind_updates'] = clean_mu

    return out or None


def advance_npc_mind(
    st_final,
    mind_updates=None,
    *,
    active_cast=(),
    overnight=False,
    day_crossed=False,
    aff_deltas=None,
    events=None,
    coy_chars=(),
    action_category='',
    pre_values=None,
    engine=None,
):
    """Decay transient moods/impressions, maintain dark-box resentment/shift kind, and apply Stage 2 mind_updates."""
    if not isinstance(st_final, dict):
        return
    mind_map = st_final.setdefault('npc_mind', save_store.default_npc_mind())
    cast_set = set(active_cast or ())
    updates = mind_updates if isinstance(mind_updates, dict) else {}
    aff_map = aff_deltas if isinstance(aff_deltas, dict) else {}
    coy_set = set(coy_chars or ())
    ev_map = events if isinstance(events, dict) else {}
    shame_ev = ev_map.get('shame_events') or {}
    aff_ev = ev_map.get('affection_events') or {}
    ds_ev = ev_map.get('ds_events') or {}
    host_ev = ev_map.get('host_events') or []
    pre_map = pre_values if isinstance(pre_values, dict) else {}

    def _etag(ident, fallback=''):
        if engine is not None and hasattr(engine, '_event_tag'):
            try:
                return engine._event_tag(ident)
            except Exception:
                return fallback
        return fallback

    t_aff01 = _etag('AFFECTION_01', '阻止侵犯_成功')
    t_aff02 = _etag('AFFECTION_02', '暴力下流_雪崩')
    t_ds10 = _etag('DS_10', '消耗_剧烈抗拒')
    t_sh03 = _etag('SHAME_03', 'C烈度_深度')
    t_sh04 = _etag('SHAME_04', 'C烈度_重度')
    t_sh09 = _etag('SHAME_09', '无意识被侵_苏醒发现')
    t_sh14 = _etag('SHAME_14', '耻感反弹_苏醒')
    deep_warm_aff = {_etag('AFFECTION_10', '情感共振_深度交心'), _etag('AFFECTION_11', '危机并肩_实质破局')}
    mild_warm_aff = {
        _etag('AFFECTION_03', '基础安抚'),
        _etag('AFFECTION_06', '社交微幅回馈'),
        _etag('AFFECTION_07', '暴跌回升_恢复中'),
    }
    warm_host_tags = {
        _etag('HOST_05', '日常_信任建立'),
        _etag('HOST_06', '日常_情感共振'),
        _etag('HOST_08', '日常_温和累进'),
    }
    has_warm_host = any(t in warm_host_tags for t in host_ev)

    for name in save_store.NPC_MIND_TARGETS:
        slot = mind_map.get(name)
        if not isinstance(slot, dict):
            slot = copy.deepcopy(save_store.default_npc_mind()[name])
            mind_map[name] = slot
        # 1. Mood inertia decay (overnight or day boundary cools lingering temper)
        if overnight or day_crossed:
            slot['mood'] = ''
            slot['mood_ttl'] = 0
        else:
            cur_ttl = max(0, int(slot.get('mood_ttl') or 0))
            if cur_ttl > 0:
                cur_ttl -= 1
                slot['mood_ttl'] = cur_ttl
                if cur_ttl <= 0:
                    slot['mood'] = ''
        # 2. Subjective impressions decay (only for active cast or on day cross)
        old_imps = slot.get('impressions') if isinstance(slot.get('impressions'), list) else []
        next_imps = []
        for item in old_imps:
            if not isinstance(item, dict) or not item.get('text'):
                continue
            ittl = max(0, int(item.get('ttl') or 0))
            if day_crossed or name in cast_set:
                ittl -= 1
            if ittl > 0:
                next_imps.append({'text': str(item['text'])[:48], 'ttl': ittl})
        slot['impressions'] = next_imps[-2:]
        # 3. Apply Stage 2 mind_updates (zero-cost piggyback on director_echo)
        patch = updates.get(name)
        if isinstance(patch, dict):
            if patch.get('mood'):
                slot['mood'] = _clean_single_line(patch['mood'])[:40]
                slot['mood_ttl'] = 2
            if patch.get('preoccupation'):
                slot['preoccupation'] = _clean_single_line(patch['preoccupation'])[:48]
            if patch.get('impression'):
                new_imp = _clean_single_line(patch['impression'])[:48]
                replaced = False
                for existing in slot['impressions']:
                    if _thread_topic_similar(existing['text'], new_imp):
                        existing['text'] = new_imp
                        existing['ttl'] = 6
                        replaced = True
                        break
                if not replaced:
                    slot['impressions'].append({'text': new_imp, 'ttl': 6})
                slot['impressions'] = slot['impressions'][-2:]
        # 4. Track affection trend, dark-box resentment (0..100), and shift kind for qualitative brief
        if name in save_store.HEROINES:
            dval = int(aff_map.get(name, 0) or 0)
            s_tags = shame_ev.get(name) or []
            a_tags = aff_ev.get(name) or []
            d_tags = ds_ev.get(name) or []
            is_coy = name in coy_set
            cur_res = max(0, min(100, int(slot.get('resentment') or 0)))

            # 4a. Resentment accumulation on genuine offense / coercion / blackout push
            res_gain = 0
            if t_aff02 in a_tags:
                res_gain += 35
            if t_aff01 in a_tags:
                res_gain += 18
            if t_ds10 in d_tags:
                res_gain += 12
            if (t_sh09 in s_tags) or (t_sh14 in s_tags):
                res_gain += 15
            pre_sta = pre_map.get((name, '体力'))
            pre_shame = pre_map.get((name, '羞耻'))
            if pre_sta is not None and int(pre_sta) <= 15 and ((t_sh03 in s_tags) or (t_sh04 in s_tags)):
                res_gain += 20
            if (not is_coy) and dval <= -4:
                res_gain += 10
            elif (not is_coy) and -3 <= dval <= -2 and (pre_shame is None or int(pre_shame) >= 85):
                res_gain += 6

            # 4b. Resentment healing on sincere respectful interaction & time cooling
            res_heal = 0
            if res_gain == 0:
                if action_category in ('A', 'B') and name in cast_set and not s_tags and (t_aff01 not in a_tags) and (t_aff02 not in a_tags) and (t_ds10 not in d_tags):
                    if any(t in deep_warm_aff for t in a_tags):
                        res_heal += 15
                    elif any(t in mild_warm_aff for t in a_tags) or has_warm_host:
                        res_heal += 10
                    else:
                        res_heal += 5
                if overnight or day_crossed:
                    res_heal += 8
            slot['resentment'] = max(0, min(100, cur_res + res_gain - res_heal))

            # 4c. Affection trend & semantic shift classification (prevents coy_fluster from poisoning next turn as annoyance)
            if dval != 0:
                slot['aff_delta_last'] = max(-20, min(20, dval))
            elif overnight or day_crossed:
                slot['aff_delta_last'] = 0
            else:
                prev_d = int(slot.get('aff_delta_last') or 0)
                slot['aff_delta_last'] = int(prev_d / 2) if abs(prev_d) > 1 else 0

            if is_coy:
                slot['last_shift_kind'] = 'coy_fluster'
            elif res_gain > 0 or (dval <= -1 and not is_coy):
                slot['last_shift_kind'] = 'true_friction'
            elif dval >= 1:
                slot['last_shift_kind'] = 'warm_gain'
            elif overnight or day_crossed or int(slot.get('aff_delta_last') or 0) == 0:
                slot['last_shift_kind'] = ''


_SCENE_RESIDUE_TABLE = {
    ('沈知韫', '徐家主宅', 'morning'): '刚核完几封早间工作邮件，手机扣在餐桌边，杯里黑咖啡凉了一截',
    ('沈知韫', '徐家主宅', 'afternoon'): '刚结束一通工作确认把手机按暗，平板屏还停在集团月度简报页',
    ('沈知韫', '徐家主宅', 'evening'): '刚卸下外出耳饰换回居家开衫，手里还捏着一份没看完的对账折页',
    ('沈知韫', '徐家主宅', 'night'): '书房台灯只开了一盏，脚尖半挂着拖鞋，正揉着发酸的眉心收尾批注',
    ('沈知韫', '公司', 'morning'): '刚散完早会回办公室，桌角叠着两份待签字的文件，语音条还没点完',
    ('沈知韫', '公司', 'afternoon'): '正站在落地窗边接完一通供应商电话，保温杯里的花茶已经放温',
    ('沈知韫', '公司', 'evening'): '办公楼外已渐暗，正把最后一份风控复核单收进文件夹准备收工',
    ('沈知韫', '公司', 'night'): '整层楼只剩董事长室亮着灯，高跟鞋脱在桌下，正低头划掉报表里的疑点',
    ('苏婉青', '徐家主宅', 'morning'): '刚把带来的老字号点心盒放上餐边柜，顺手理平针织裙下摆',
    ('苏婉青', '徐家主宅', 'afternoon'): '刚帮婆婆添过半盏温水，手机屏幕在手包边悄悄亮了一下又被按暗',
    ('苏婉青', '徐家主宅', 'evening'): '刚把随身小包挪到手边整理好，正盘算着晚点怎么回承邺的消息',
    ('苏婉青', '市中心顶层公寓', 'morning'): '刚给阳台绿植喷完水，茶几上摆着切了一半的橙子和没来得及收的快递盒',
    ('苏婉青', '市中心顶层公寓', 'afternoon'): '窝在落地窗边翻家居杂志，屋里静得能听见挂钟轻响，电视开着静音',
    ('苏婉青', '市中心顶层公寓', 'evening'): '刚热好一人份晚汤却没动几口，正把冷掉的手机搁回沙发扶手边',
    ('苏婉青', '市中心顶层公寓', 'night'): '洗完澡只留了客厅一盏暖色落地灯，赤脚踩在地毯上正准备拉拢窗帘',
    ('徐念薇', '徐家主宅', 'morning'): '半靠在窗边回导师语音，指缝还沾着一点没搓净的颜料边',
    ('徐念薇', '徐家主宅', 'afternoon'): '戴着单边蓝牙耳机翻画册参考，脚尖轻轻点着椅子横档',
    ('徐念薇', '徐家主宅', 'evening'): '刚从外头回宅把帆布画袋往玄关一放，手腕上还绕着一根沾灰的发圈',
    ('徐念薇', '徐家主宅', 'night'): '捧着杯温水在客厅角落刷展览投稿进度，发梢还带着刚洗过的微潮',
    ('徐念薇', '大学', 'morning'): '刚下完素描评图课，怀里抱着速写本正准备避开熟人找安静角落',
    ('徐念薇', '大学', 'afternoon'): '正坐在系楼长廊边修改草图构图，铅笔屑落在帆布裙摆上还没拍掉',
    ('徐念薇', '工作室', 'morning'): '正把几幅半成品油画靠墙重新排光，空气里浮着淡淡松节油味',
    ('徐念薇', '工作室', 'afternoon'): '踩着矮凳给新画框绷麻布，嘴里咬着发圈，地上散着两张废稿',
    ('徐念薇', '工作室', 'evening'): '拿画刀刮掉调色盘边干硬的颜料，画室顶灯在画布边沿投下一道冷光',
    ('徐念薇', '工作室', 'night'): '画室只留了一盏冷白工作灯，围裙下摆蹭了道灰蓝，正盯着二稿出神',
    ('徐承邺', '徐家主宅', 'morning'): '西装袖扣刚扣好一半，正站在客厅边听助理语音边扫过餐桌',
    ('徐承邺', '徐家主宅', 'afternoon'): '靠在真皮沙发里划着项目报表，手边放着新捎回来的高价茶叶礼盒',
    ('徐承邺', '徐家主宅', 'evening'): '刚应酬完进门松了半截领带，身上带着一点应酬后的酒气与浓烈古龙水味',
    ('徐承邺', '市中心顶层公寓', 'evening'): '正把公文包随手放上玄关柜，顺口问起这两天主宅那边的动静',
    ('徐承邺', '市中心顶层公寓', 'night'): '松开衬衫最上面两颗扣子靠在书房椅背上，还在翻手机里的并购群消息',
}

_SCENE_RESIDUE_GENERIC_BY_CHAR = {
    '沈知韫': '刚把手机屏按灭收进手包，神色沉稳，眉心仍留着一丝刚处理完事务的余韵',
    '苏婉青': '刚理平袖口褶皱，手包搁在身侧，指尖轻轻按着静音的手机边沿',
    '徐念薇': '正把单边耳机摘下来绕进掌心，目光淡淡扫过四周，手里还拿着手机',
    '徐承邺': '刚把一条语音听完按灭屏幕，抬手整了整衬衫领口',
}


def build_scene_entry_snapshot(root, location, cast, weekday='', clock=None, director_state=None, npc_mind=None, *, present_actors=None):
    """Deterministic zero-cost 'in medias res' activity residue when entering a scene (scene_turns <= 1)."""
    if not cast:
        return {}
    room_set = {a for a in (present_actors or ()) if a in cast}
    target_cast = [c for c in cast if (not room_set or c in room_set)]
    if not target_cast:
        return {}
    slot = _clock_time_slot(clock)
    dstate = director_state if isinstance(director_state, dict) else {}
    clocks = dstate.get('offstage_clocks') if isinstance(dstate.get('offstage_clocks'), dict) else {}
    catalog = load_world_beats(root, optional=True)
    clocks_cfg = catalog.get('offstage_clocks') or {}
    # Find hot offstage clocks (progress >= 2) owned by in-scene characters
    hot_clock_by_owner = {}
    for cid, meta in clocks_cfg.items():
        owner = meta.get('owner')
        cst = clocks.get(cid) or {}
        if owner in target_cast and int(cst.get('p') or 0) >= 2:
            phases = meta.get('phases') or []
            if phases:
                ph = phases[int(cst.get('ph') or 0) % len(phases)]
                lbl = str(ph.get('label') or '').strip()
                if lbl:
                    hot_clock_by_owner[owner] = lbl
    out = {}
    for name in target_cast:
        if name not in save_store.NPC_MIND_TARGETS:
            continue
        base = _SCENE_RESIDUE_TABLE.get((name, location, slot)) or _SCENE_RESIDUE_GENERIC_BY_CHAR.get(name)
        if not base:
            continue
        if name in hot_clock_by_owner:
            base = f'{base}（心头正压着「{hot_clock_by_owner[name]}」的余波）'
        out[name] = base
    return out


def build_director_settlement_context(root, memory_text, director_roll=None):
    """Build compact read-only Living Director snapshot for Stage 2 SUMMARY user_context."""
    catalog = load_world_beats(root, optional=True)
    dstate = parse_director_block(memory_text)
    channels_map = catalog.get('channels') or DIRECTOR_DEFAULT_CHANNELS
    clocks_cfg = catalog.get('offstage_clocks') or {}
    clocks_view = {}
    for cid, meta in clocks_cfg.items():
        st = dstate['offstage_clocks'].get(cid) or {'p': 0, 'ph': 0, 'so': False, 'cd': 0}
        phases = meta.get('phases') or []
        label = phases[st['ph'] % len(phases)]['label'] if phases else cid
        clocks_view[cid] = {
            'owner': meta.get('owner', ''),
            'label': label,
            'p': st['p'],
            'max': int(meta.get('max_segments', 4)),
        }
    return {
        'active_threads': [
            {'id': t['id'], 'who': t['who'], 'topic': t['topic']}
            for t in dstate['active_threads']
        ],
        'offstage_clocks': clocks_view,
        'channels_enum': list(channels_map.keys()),
        'triggered_this_turn': bool(isinstance(director_roll, dict) and director_roll.get('triggered')),
    }


def format_surprise_directive(director_roll, catalog=None):
    """Unified Stage 1 Zone 2 / packet formatter for all three Living Director v2 modes + legacy v1 rolls."""
    if not isinstance(director_roll, dict) or not director_roll.get('triggered'):
        return None
    mode = director_roll.get('mode') or 'preset_beat'
    banned = [str(x) for x in (director_roll.get('banned_channels') or []) if isinstance(x, str) and x]
    if mode == 'thread_spark':
        is_heroine_spark = director_roll.get('sub_mode') == 'heroine_spark'
        sd = {
            'mode': 'thread_spark',
            'tier': director_roll.get('tier', 'tier1'),
            'move_style': f"{'硬动作' if director_roll.get('move_kind') == 'hard' else '软动作'}·{director_roll.get('move_name', '')}",
            'move_guide': director_roll.get('move_guide', ''),
            'anchor': director_roll.get('anchor', ''),
            'spark_pair': director_roll.get('spark_pair', ''),
            'rule': (
                '本幕围绕在场女主的暗流破绽与暧昧微距火花：将锚点与双词意象自然融合成真实近距细节或失守瞬间，在需要主角表态/接茬的半拍停住；严禁使用banned_channels所列近期媒介套路，禁提系统/随机/概率/导演词，禁替主角做决定，禁让场外人物瞬移发言，严守K01知情边界。'
                if is_heroine_spark else
                '将锚点与双词意象火花自然融合成真实生活细节或局部变故（软动作留出试探博弈余地，硬动作令既有压力落地）；严禁使用banned_channels所列近期媒介套路，禁提系统/随机/概率/导演词，禁替主角做决定，禁让场外人物瞬移发言，严守K01知情边界。'
            ),
        }
        if is_heroine_spark:
            sd['sub_mode'] = 'heroine_spark'
            sd['choice_hook_guide'] = (
                '段末---DECISION---须围绕此刻女主露出的微距破绽展开：A 绅士稳住或顺势带过；B 合法近身照料/顺手解围拉近距离；C 借势压近或主动试探推进。'
            )
        if banned:
            sd['banned_channels'] = banned
        return sd
    if mode == 'offstage_clock':
        in_scene = bool(director_roll.get('owner_in_scene'))
        sd = {
            'mode': 'offstage_clock',
            'tier': director_roll.get('tier', 'tier2'),
            'clock_stage': f"{'硬落地' if director_roll.get('clock_stage') == 'hard' else '软预兆'}({director_roll.get('clock_progress_label', '')})",
            'clock_owner': director_roll.get('clock_owner', ''),
            'owner_in_scene': in_scene,
            'clock_theme': director_roll.get('clock_phase_label', ''),
            'clock_event': director_roll.get('clock_event', ''),
            'rule': (
                '场外暗流蓄力后的自然浮现：'
                + ('' if in_scene else '该角色当前不在场，严禁让其现身或输出[D:姓名]台词，只能经由物件/旁人转述/旁白间接呈现；')
                + '严禁使用banned_channels所列近期媒介套路，禁提系统/暗钟/导演词，禁替主角做决定；'
                + str(director_roll.get('k01_guard') or '严守K01知情边界。')
            ),
        }
        if banned:
            sd['banned_channels'] = banned
        return sd
    # Default: Track 3 curated preset_beat (also 100% compatible with legacy v1 frozen rolls)
    cat = director_roll.get('category') or ''
    is_erotic = cat == 'erotic_accident'
    is_sensual = cat == 'sensual_hook'
    is_subtext_leak = cat == 'subtext_leak'
    sd = {
        'mode': 'preset_beat',
        'tier': director_roll.get('tier', 'tier1'),
        'objective_event': director_roll.get('objective_event', ''),
        'rule': (
            '本幕真实突发的女主贴身/香艳意外：细腻刻画视觉、气味、体温与女主在当前羞耻值下的真实慌乱、掩饰或生理失控反应，必须在需要徐志北立刻伸手/接茬/决定进退的临界半拍戛然而止，把主动权交给段末decision；禁提系统/随机/概率/导演词，禁替主角做决定，严守K01知情边界。'
            if is_erotic else (
                '本幕真实发生的日常魅力微距契机：自然织入在场女主的标志性形体细节（美足/美手/36D）、近距气味与徐志北的生理克制反应，在呼吸交错或视线撞上的半拍停住并把拉近距离/顺势试探的选择权交给段末decision；禁提系统/随机/概率/导演词，禁替主角做决定，严守K01知情边界。'
                if is_sensual else (
                    '本幕真实发生的客观微兆：只露出客观物件/声响微兆，当事人若被察觉必须按人设本能用无害日常敷衍遮掩，严禁借此主动坦白或交底；禁提系统/随机/概率/导演词，禁替主角做决定，严守K01知情边界。'
                    if is_subtext_leak else
                    '本幕真实发生的客观外部变数：自然织入剧情并触发人物反应；禁提系统/随机/概率/导演词，禁替主角做决定，严守K01知情边界。'
                )
            )
        ),
    }
    if is_erotic or is_sensual:
        sd['category'] = cat
        sd['choice_hook_guide'] = (
            '段末---DECISION---的PROMPT与B/C选项须直接锚定本次突发意外作为切入点（禁跳回无关日常寒暄）：'
            'A（5体力）绅士避嫌或替她保住体面解围；'
            'B（10体力）借本次意外合法近身协助（如递巾帮拭、扶稳肩臂、代解缠绕、帮遮破绽——严守日常B礼仪边界，却实质拉近距离松动防线）；'
            'C（15体力）趁着失衡/窘境借势压近、贴耳低语或顺水推舟越界试探。'
            if is_erotic else
            '段末---DECISION---的PROMPT与B/C选项须直接承接此刻微距契机（禁跳回平淡家常）：'
            'A（5体力）不动声色收回视线稳住对话；'
            'B（10体力）借递物/照料顺势靠近半步轻声点破或试探反应；'
            'C（15体力）主动压近距离或直球撩拨借势推进。'
        )
    if director_roll.get('linked_seed'):
        sd['linked_foreshadowing'] = director_roll['linked_seed']
    if banned:
        sd['banned_channels'] = banned
    return sd


def _parse_director_heroine_stats(memory_text, counters):
    stats = {}
    mem_str = memory_text or ''
    for name in ('沈知韫', '苏婉青', '徐念薇'):
        m = re.search(r'^\[' + re.escape(name) + r'\]([^\n]*)', mem_str, re.M)
        line = m.group(1) if m else ''
        def _val(attr, default):
            am = re.search(rf'{attr}\s*(-?\d+)', line)
            return int(am.group(1)) if am else default
        lock_m = re.search(
            rf'▶\s*{re.escape(name)}\s*\n(?:(?!▶).)*?\[持续_体液锁定\](?:\s*剩余时效:\s*(\d+)回合)?',
            mem_str,
            re.DOTALL,
        )
        has_fluid_lock = ('[持续_体液锁定]' in line) or bool(
            lock_m and (lock_m.group(1) is None or int(lock_m.group(1)) > 0)
        )
        stats[name] = {
            'aff': _val('好感', 50),
            'sha': _val('羞耻', 95),
            'des': _val('欲望', 0),
            'dep': _val('堕落', 0),
            'sta': _val('体力', 80),
            'fluid_lock': has_fluid_lock,
            'unrelieved': int((counters or {}).get(f'空耗_连续未纾解_{name}', 0)),
        }
    return stats


def _resolve_director_pacing(cfg, pacing_mode='standard'):
    key = normalize_director_pacing(pacing_mode)
    presets = cfg.get('pacing_presets') if isinstance(cfg.get('pacing_presets'), dict) else {}
    raw = presets.get(key) if isinstance(presets.get(key), dict) else {}
    fb = DIRECTOR_DEFAULTS['pacing_presets'].get(key, DIRECTOR_DEFAULTS['pacing_presets']['standard'])
    return {
        'mode': key,
        'heroine_pity_turns': max(2, int(raw.get('heroine_pity_turns', cfg.get('heroine_pity_turns', fb['heroine_pity_turns'])))),
        'heroine_beat_cooldown': max(1, int(raw.get('heroine_beat_cooldown', cfg.get('heroine_beat_cooldown', fb['heroine_beat_cooldown'])))),
        'erotic_category_cooldown': max(1, int(raw.get('erotic_category_cooldown', cfg.get('erotic_category_cooldown', fb['erotic_category_cooldown'])))),
        'heroine_prob_mult': max(0.3, min(2.0, float(raw.get('heroine_prob_mult', fb['heroine_prob_mult'])))),
    }


def roll_director_beat(root, state, memory_text, runtime, weekday, *, rng=None, pacing_mode='standard'):
    """Run one Living Director v2.1 Dual-Track (Heroine Pity + Routine Entropy RNG) roll. Freeze once per request_id."""
    cfg = director_config(root)
    pacing = _resolve_director_pacing(cfg, pacing_mode)
    dstate = parse_director_block(memory_text)
    location = (state or {}).get('location', '')
    cast = list((state or {}).get('cast', []))
    scene_turns = (dstate['scene_turns'] + 1) if dstate['scene_location'] == location else 1
    if cfg.get('status') != 'active':
        return {'triggered': False, 'probability': 0.0, 'scene_turns_in_place': scene_turns}

    catalog = load_world_beats(root, optional=True)
    channels_map = catalog.get('channels') or DIRECTOR_DEFAULT_CHANNELS
    clocks_cfg = catalog.get('offstage_clocks') or {}
    spark_cfg = catalog.get('spark_matrix') or {}

    try:
        counters = rr._counters(memory_text or '')
    except Exception:
        counters = {}
    char_stats = _parse_director_heroine_stats(memory_text, counters)
    cooldowns = dstate['event_cooldowns']
    erotic_cd = int(cooldowns.get('__EROTIC_CATEGORY__', 0))
    sensual_drought = max(0, int(dstate.get('sensual_drought', 0)))
    heroine_cd = max(0, int(dstate.get('heroine_cd', 0)))

    max_vig = 0
    for vm in re.finditer(r'^徐承邺_[^\n：:]+[：:]\s*警惕\s*(\d+)', memory_text or '', re.M):
        max_vig = max(max_vig, int(vm.group(1)))
    try:
        micro_map = rr._current_micro(memory_text or '')
    except Exception:
        micro_map = {}
    host_biz = 0
    bm = re.search(r'\[系统宿主\][^\n]*?商业嗅觉\s*(-?\d+)', memory_text or '')
    if bm:
        host_biz = int(bm.group(1))

    intl_state = (state or {}).get('intimate') if isinstance((state or {}).get('intimate'), dict) else {}
    intimate_active = bool(intl_state.get('scene_active'))
    present_actors = [a for a in (intl_state.get('present_actors') or []) if a in cast]
    eff_present = set(present_actors) if present_actors else set(cast)
    cur_privacy = str(intl_state.get('privacy') or 'open_public')
    attire_map = intl_state.get('attire') if isinstance(intl_state.get('attire'), dict) else {}
    deployed_items = [d for d in ((state or {}).get('deployed_items') or []) if isinstance(d, dict)]
    high_risk_devs_here = [
        d for d in deployed_items
        if d.get('location') == location and int(d.get('detected_risk') or 0) >= 60
    ]

    clock = (runtime or {}).get('clock')
    slot = _clock_time_slot(clock)
    seeds = dstate['pending_seeds']
    mature_seed_ids = {s['seed_id'] for s in seeds if s.get('age', 0) >= 2}
    all_seed_ids = {s['seed_id'] for s in seeds}
    consumed = set(dstate['consumed_once'])
    thread_people = {w for t in dstate['active_threads'] for w in t.get('who', [])}
    chan_win = max(1, int(cfg.get('channel_cooldown_window', 4)))
    recent_channels = list(dstate['recent_channels'][-chan_win:])
    recent_channel_set = set(recent_channels)
    banned_labels = [channels_map[c] for c in recent_channels if c in channels_map]
    tier_weights = cfg.get('tier_weights') or {'tier1': 50, 'tier2': 38, 'tier3': 12}

    has_heroine_here = any(c in char_stats for c in cast) and location in ('徐家主宅', '市中心顶层公寓', '工作室', '公司')
    pity_turns = pacing['heroine_pity_turns']
    pity_ready = bool(has_heroine_here and not intimate_active and heroine_cd <= 0 and sensual_drought >= pity_turns)
    drought_boost = 1.0 + min(0.90, max(0, sensual_drought - 1) * 0.25)

    # Pre-filter all preset beats into decoupled heroine vs routine pools in one pass
    heroine_candidates = []
    heroine_pity_fallback = []
    routine_preset_candidates = []
    has_mature_seed_beat = False
    has_device_risk_beat = False
    for beat in catalog.get('beats', []):
        bid = beat.get('id', '')
        if not bid or bid in consumed or cooldowns.get(bid, 0) > 0:
            continue
        bcat = beat.get('category', '')
        is_erotic_beat = bcat == 'erotic_accident'
        is_sensual_beat = bcat == 'sensual_hook'
        is_heroine_beat = is_erotic_beat or is_sensual_beat
        locs = beat.get('locations') or []
        if locs and location not in locs:
            continue
        req_cast = beat.get('required_cast') or []
        if any(c not in cast for c in req_cast):
            continue
        if 'requires_door_catch' in beat:
            is_door_catch = bool(beat.get('requires_door_catch'))
        else:
            is_door_catch = bid.startswith(('BEAT-T2-EROTIC-', 'BEAT-T3-EROTIC-', 'BEAT-T4-EROTIC-'))
        if is_door_catch and scene_turns >= 2:
            if req_cast and all(c in eff_present for c in req_cast):
                continue
        req_priv = beat.get('requires_privacy') or []
        if req_priv and cur_privacy not in req_priv:
            continue
        if beat.get('requires_gifted_outfit'):
            if not req_cast or not any((attire_map.get(c) or {}).get('gifted_items') for c in req_cast):
                continue
        if beat.get('requires_high_risk_device'):
            if not high_risk_devs_here:
                continue
        slots = beat.get('time_slots') or ['any']
        if 'any' not in slots and slot not in slots:
            continue
        if max_vig < int(beat.get('min_vigilance', 0)) or host_biz < int(beat.get('min_biz', 0)):
            continue
        min_aff = int(beat.get('min_affection', 0))
        max_sha = int(beat.get('max_shame', 100))
        min_des = int(beat.get('min_desire', 0))
        min_dep = int(beat.get('min_depravity', 0))
        req_unrel = bool(beat.get('requires_unrelieved', False))
        gate_target_names = [c for c in req_cast if c in char_stats]
        if (min_aff > 0 or max_sha < 100 or min_des > 0 or min_dep > 0 or req_unrel):
            if not gate_target_names:
                continue
            gate_ok = True
            for cname in gate_target_names:
                cst = char_stats[cname]
                if cst['aff'] < min_aff or cst['sha'] > max_sha or cst['des'] < min_des or cst['dep'] < min_dep:
                    gate_ok = False
                    break
                if req_unrel and not (cst['unrelieved'] >= 1 or cst['fluid_lock'] or cst['des'] >= 80):
                    gate_ok = False
                    break
            if not gate_ok:
                continue
        req_seed = beat.get('requires_seed')
        if req_seed and req_seed not in all_seed_ids:
            continue
        add_seed = beat.get('seed_to_add')
        if isinstance(add_seed, dict) and add_seed.get('seed_id') in all_seed_ids:
            continue

        btier = beat.get('tier', 'tier1')
        tw = float(tier_weights.get(btier, 22.0 if btier == 'tier4' else 20.0))
        w = max(1.0, float(beat.get('weight', 10))) * (tw / 30.0)
        if len(locs) == 1:
            w *= 1.45
        elif len(locs) == 2:
            w *= 1.15
        elif len(locs) >= 4:
            w *= 0.80
        if req_cast:
            w *= 1.35
        if 'any' not in slots:
            w *= 1.20
        if req_cast and any(c in thread_people for c in req_cast):
            w *= 1.40
        beat_chan = str(beat.get('channel') or '').strip()
        if beat_chan and beat_chan in recent_channel_set:
            w *= (0.45 if is_heroine_beat else 0.15)
        if req_seed and req_seed in mature_seed_ids:
            w *= 3.0
            has_mature_seed_beat = True
        elif req_seed:
            w *= 1.5
        if beat.get('requires_high_risk_device'):
            has_device_risk_beat = True
            w *= 2.80

        if is_heroine_beat:
            if is_erotic_beat:
                w *= (1.95 if req_unrel else 1.70) * drought_boost
                if erotic_cd > 0:
                    heroine_pity_fallback.append((beat, w, True))
                else:
                    heroine_candidates.append((beat, w, True))
            else:
                w *= 1.15 * drought_boost
                heroine_candidates.append((beat, w, False))
        else:
            routine_preset_candidates.append((beat, w))

    gen = rng if rng is not None else secrets.SystemRandom()

    # 1. Decoupled Heroine Opportunity Track (independent of routine global_cooldown & soft_cooldown_penalty)
    track_cfg = cfg.get('track_weights') or {'thread_spark': 45, 'offstage_clock': 30, 'preset_beat': 25}
    w_t3_base = float(track_cfg.get('preset_beat', 25))
    active_heroine_pool = heroine_candidates or (heroine_pity_fallback if pity_ready else [])
    if w_t3_base > 0 and has_heroine_here and not intimate_active and heroine_cd <= 0 and active_heroine_pool:
        heroine_curve = (0.06, 0.14, 0.26, 0.42, 0.58)
        if pity_ready:
            p_heroine = 1.0
        else:
            base_h = heroine_curve[min(sensual_drought, len(heroine_curve) - 1)]
            p_heroine = max(0.0, min(0.85, base_h * pacing['heroine_prob_mult']))
        if pity_ready or gen.random() < p_heroine:
            weighted_h = [
                (b, w * ((2.2 if pity_ready else 1.55) if is_er else 1.0))
                for b, w, is_er in active_heroine_pool
            ]
            chosen = _weighted_choice(weighted_h, gen)
            linked_summary = ''
            if chosen.get('requires_seed'):
                for s in seeds:
                    if s['seed_id'] == chosen['requires_seed']:
                        linked_summary = s.get('summary', '')
                        break
            return {
                'triggered': True,
                'mode': 'preset_beat',
                'track': 'heroine_opportunity',
                'pacing_mode': pacing['mode'],
                'pity_triggered': pity_ready,
                'probability': round(p_heroine, 4),
                'scene_turns_in_place': scene_turns,
                'tier': chosen.get('tier', 'tier1'),
                'event_id': chosen['id'],
                'category': chosen.get('category', ''),
                'channel_hint': str(chosen.get('channel') or ''),
                'banned_channels': banned_labels,
                'objective_event': chosen['objective_event'],
                'linked_seed': linked_summary,
                'seed_to_add': chosen.get('seed_to_add'),
                'seed_consumed': chosen.get('requires_seed'),
                'cooldown': int(chosen.get('cooldown', 7)),
                'once': bool(chosen.get('once', False)),
            }

    # 2. Routine World Director Track (Entropy curve + tension + context + mature seeds + ready clocks)
    base = float(cfg.get('base_prob', 0.08))
    curve = cfg.get('stagnation_curve') or [0.0, 0.07, 0.16, 0.28, 0.44, 0.62]
    k = min(max(0, int(dstate['calm_streak'])), len(curve) - 1)
    p_stag = float(curve[k])
    if any(int(counters.get(bk, 0)) >= lim for bk, lim in rr.BREAKOUT_LIMITS.items()):
        p_stag += 0.25

    p_tension = 0.0
    p_tension += min(0.24, (max_vig // 20) * 0.06)
    if any((micro_map.get(n) or {}).get('residual_tension') or (micro_map.get(n) or {}).get('confusion_debt') for n in cast):
        p_tension += 0.08
    if location == '徐家主宅' and '苏婉青' in cast:
        su_st = char_stats.get('苏婉青') or {'aff': 40, 'sha': 99}
        if su_st['aff'] < 70 or su_st['sha'] > 80:
            p_tension += 0.10
    if host_biz >= 10:
        istate = parse_intel_block(memory_text or '')
        icat = load_intel_catalog(root, optional=True)
        if any(it['id'] not in istate['held'] and it['id'] not in istate['consumed'] and host_biz >= it['min_biz']
               for it in icat.get('items', [])):
            p_tension += 0.08
    if high_risk_devs_here:
        p_tension += 0.12
    p_tension = min(0.35, p_tension)

    p_context = 0.10 if _is_boundary_window(clock, weekday) else 0.0
    p_seed = 0.12 if mature_seed_ids else 0.0

    # Inspect ready offstage clocks (3/4 soft omen or 4/4 hard landing)
    ready_clocks = []
    has_hard_clock = False
    for cid, meta in clocks_cfg.items():
        cst = dstate['offstage_clocks'].get(cid) or {'p': 0, 'ph': 0, 'so': False, 'cd': 0}
        if cst['cd'] > 0:
            continue
        max_seg = max(2, int(meta.get('max_segments', 4)))
        soft_at = max(1, min(max_seg - 1, int(meta.get('soft_at', max_seg - 1))))
        if cst['p'] >= max_seg:
            has_hard_clock = True
            ready_clocks.append((cid, meta, cst, 'hard', 3.0))
        elif cst['p'] >= soft_at and not cst['so']:
            ready_clocks.append((cid, meta, cst, 'soft', 1.2))
    p_clock = 0.10 if has_hard_clock else (0.06 if ready_clocks else 0.0)

    if dstate['global_cooldown'] > 0:
        prob = 0.0
    else:
        penalty = float(cfg.get('soft_cooldown_penalty', 0.25)) if dstate['turns_since_beat'] <= 2 else 0.0
        prob = max(0.0, min(float(cfg.get('max_prob', 0.85)),
                            base + p_stag + p_tension + p_context + p_seed + p_clock - penalty))

    if prob <= 0.0 or gen.random() >= prob:
        return {'triggered': False, 'probability': round(prob, 4), 'scene_turns_in_place': scene_turns}

    track_cfg = cfg.get('track_weights') or {'thread_spark': 45, 'offstage_clock': 30, 'preset_beat': 25}
    track_pool = []

    # --- Track 1: Living Threads × Combinatorial Spark Matrix (Mythic GME + PbtA) ---
    sensual_spark_cfg = catalog.get('sensual_spark_matrix') if isinstance(catalog.get('sensual_spark_matrix'), dict) else {}
    use_sensual_spark = bool(
        sensual_spark_cfg
        and has_heroine_here
        and (intimate_active or sensual_drought >= 2)
    )
    actions = list(spark_cfg.get('actions') or [])
    textures = list(spark_cfg.get('textures') or [])
    if use_sensual_spark:
        if sensual_spark_cfg.get('actions'):
            actions = list(sensual_spark_cfg['actions']) + actions
        if sensual_spark_cfg.get('textures'):
            textures = list(sensual_spark_cfg['textures']) + textures
    moves_cfg = spark_cfg.get('moves') or {}
    soft_moves = moves_cfg.get('soft') or []
    hard_moves = moves_cfg.get('hard') or []
    w_t1_base = float(track_cfg.get('thread_spark', 45))
    if w_t1_base > 0 and actions and textures and (soft_moves or hard_moves):
        threads = dstate['active_threads']
        if threads:
            t_weight = w_t1_base
            if any(any(w in cast for w in t['who']) for t in threads):
                t_weight *= 1.25
            track_pool.append(('thread_spark', t_weight))
        else:
            track_pool.append(('thread_spark', min(w_t1_base, 20.0)))

    # --- Track 2: Offstage Character Progress Clocks (Blades in the Dark) ---
    w_t2_base = float(track_cfg.get('offstage_clock', 30))
    if w_t2_base > 0 and ready_clocks:
        t2_mult = 2.4 if has_hard_clock else 1.6
        track_pool.append(('offstage_clock', w_t2_base * t2_mult))

    # --- Track 3: Curated Routine Preset Pivotal Storylets ---
    if high_risk_devs_here and not has_device_risk_beat:
        top_dev = max(high_risk_devs_here, key=lambda d: int(d.get('detected_risk') or 0))
        spot_txt = top_dev.get('spot') or '隐蔽角落'
        dev_name = top_dev.get('name') or '隐蔽装置'
        synth_beat = {
            'id': f"BEAT-DYN-DEVICE-RISK-{top_dev.get('id', 'DEV')}",
            'tier': 'tier2',
            'category': 'covert_risk',
            'channel': 'object_trace',
            'cooldown': 4,
            'once': False,
            'objective_event': (
                f"室内光线扫过{spot_txt}，暗藏的「{dev_name}」在微弱反光或整理擦拭间隙险些被在场人注意，空气骤然收紧，需决定借动作遮掩、转移视线还是顺势拆除。"
            ),
        }
        routine_preset_candidates.append((synth_beat, 42.0))
        has_device_risk_beat = True

    w_t3_base = float(track_cfg.get('preset_beat', 25))
    if w_t3_base > 0 and routine_preset_candidates:
        t3_mult = 1.8 if (has_mature_seed_beat or has_device_risk_beat) else 1.0
        track_pool.append(('preset_beat', w_t3_base * t3_mult))

    if not track_pool:
        return {'triggered': False, 'probability': round(prob, 4), 'scene_turns_in_place': scene_turns}

    chosen_track = _weighted_choice(track_pool, gen)

    if chosen_track == 'thread_spark':
        threads = dstate['active_threads']
        chosen_thread = None
        heroines_here = [c for c in cast if c in char_stats]
        is_heroine_spark = bool(use_sensual_spark and heroines_here)
        if is_heroine_spark and (not threads or gen.random() < 0.6):
            thread_id = ''
            target_h = heroines_here[int(gen.random() * len(heroines_here))]
            anchor_text = f'围绕{location}中与{target_h}此刻近距相处中的微妙暗流与失守破绽'
            s_acts = list(sensual_spark_cfg.get('actions') or actions)
            s_texs = [tx for tx in (sensual_spark_cfg.get('textures') or textures) if isinstance(tx, dict)]
            actions = s_acts
            textures = s_texs
        elif threads:
            weighted_threads = []
            for t in threads:
                tw_score = 1.5 if any(w in cast for w in t['who']) else 1.0
                if t['tension'] == 'hard':
                    tw_score += 0.35
                tw_score += min(0.4, t['age'] * 0.05)
                weighted_threads.append((t, tw_score))
            chosen_thread = _weighted_choice(weighted_threads, gen)
            who_tag = '、'.join(chosen_thread['who']) if chosen_thread['who'] else '当前局势'
            anchor_text = f"承接活体线头[{chosen_thread['id']}]（{who_tag}）：{chosen_thread['topic']}"
            thread_id = chosen_thread['id']
            is_heroine_spark = bool(is_heroine_spark and any(w in heroines_here for w in chosen_thread.get('who', [])))
        else:
            thread_id = ''
            l1_snip = _extract_latest_l1_snippet(memory_text)
            held_items = [i.get('name') for i in ((state or {}).get('items') or []) if isinstance(i, dict) and i.get('name')]
            if l1_snip:
                anchor_text = f'顺着近期余波自然延展：{l1_snip}'
            elif held_items:
                anchor_text = f'围绕随身物件「{held_items[0]}」与{location}当下相处细节'
            elif cast:
                anchor_text = f'围绕{location}中与{"、".join(cast)}此刻的微妙氛围与暗流'
            else:
                anchor_text = f'围绕{location}此刻独处环境中的细微反常'

        rolled_tier = _weighted_choice(
            [('tier1', tier_weights.get('tier1', 50)), ('tier2', tier_weights.get('tier2', 38))],
            gen,
        )
        use_hard = bool(
            hard_moves and (
                (chosen_thread and (chosen_thread['touches'] >= 1 or chosen_thread['age'] >= 4 or chosen_thread['tension'] == 'hard'))
                or (rolled_tier == 'tier2' and not soft_moves)
            )
        )
        if use_hard and hard_moves:
            move_kind = 'hard'
            move_obj = _weighted_choice([(mv, 1.0) for mv in hard_moves], gen)
            final_tier = 'tier2'
        else:
            move_kind = 'soft'
            move_obj = _weighted_choice([(mv, 1.0) for mv in (soft_moves or hard_moves)], gen)
            final_tier = 'tier1'

        allowed_textures = [tx for tx in textures if isinstance(tx, dict) and tx.get('channel') not in recent_channel_set]
        if not allowed_textures:
            allowed_textures = [tx for tx in textures if isinstance(tx, dict)]
        chosen_action = _weighted_choice([(act, 1.0) for act in actions], gen)
        chosen_tex = _weighted_choice([(tx, 1.0) for tx in allowed_textures], gen)
        tex_label = str(chosen_tex.get('label') or '')
        chan_hint = str(chosen_tex.get('channel') or '')
        spark_pair = f'{chosen_action} × {tex_label}'
        out_spark = {
            'triggered': True,
            'mode': 'thread_spark',
            'probability': round(prob, 4),
            'scene_turns_in_place': scene_turns,
            'tier': final_tier,
            'event_id': f"SPARK-{thread_id or ('HEROINE' if is_heroine_spark else 'AMBIENT')}",
            'category': 'living_spark',
            'thread_id': thread_id,
            'anchor': anchor_text,
            'move_kind': move_kind,
            'move_name': str(move_obj.get('name') or ''),
            'move_guide': str(move_obj.get('guide') or ''),
            'spark_action': str(chosen_action),
            'spark_texture': tex_label,
            'spark_pair': spark_pair,
            'channel_hint': chan_hint,
            'banned_channels': banned_labels,
            'objective_event': f"{anchor_text}｜{move_obj.get('name', '')}｜火花：{spark_pair}",
            'linked_seed': '',
            'seed_to_add': None,
            'seed_consumed': None,
            'cooldown': 0,
            'once': False,
        }
        if is_heroine_spark:
            out_spark['sub_mode'] = 'heroine_spark'
        return out_spark

    if chosen_track == 'offstage_clock':
        picked = _weighted_choice([(entry, entry[4]) for entry in ready_clocks], gen)
        cid, meta, cst, stage_kind, _ = picked
        max_seg = max(2, int(meta.get('max_segments', 4)))
        phases = meta.get('phases') or []
        phase = phases[cst['ph'] % len(phases)] if phases else {
            'label': cid, 'soft_omen': '', 'hard_landing': '', 'channel_hint': 'offstage_ripple',
        }
        owner = str(meta.get('owner') or '')
        owner_in_scene = owner in cast
        clock_event = str(phase.get('hard_landing' if stage_kind == 'hard' else 'soft_omen') or '')
        chan_hint = str(phase.get('channel_hint') or 'offstage_ripple')
        progress_label = f"{min(cst['p'], max_seg)}/{max_seg}"
        return {
            'triggered': True,
            'mode': 'offstage_clock',
            'probability': round(prob, 4),
            'scene_turns_in_place': scene_turns,
            'tier': 'tier2' if stage_kind == 'soft' else 'tier3',
            'event_id': f"{cid}-{stage_kind.upper()}",
            'category': 'offstage_clock',
            'clock_id': cid,
            'clock_owner': owner,
            'owner_in_scene': owner_in_scene,
            'clock_stage': stage_kind,
            'clock_progress_label': progress_label,
            'clock_phase_label': str(phase.get('label') or ''),
            'clock_event': clock_event,
            'k01_guard': str(meta.get('k01_guard') or '严守K01知情边界。'),
            'channel_hint': chan_hint,
            'banned_channels': banned_labels,
            'objective_event': f"[{owner}·{phase.get('label', '')} {progress_label}] {clock_event}",
            'linked_seed': '',
            'seed_to_add': None,
            'seed_consumed': None,
            'cooldown': 0,
            'once': False,
        }

    # Track 3: Curated Routine preset_beat
    chosen = _weighted_choice(routine_preset_candidates, gen)
    linked_summary = ''
    if chosen.get('requires_seed'):
        for s in seeds:
            if s['seed_id'] == chosen['requires_seed']:
                linked_summary = s.get('summary', '')
                break

    return {
        'triggered': True,
        'mode': 'preset_beat',
        'probability': round(prob, 4),
        'scene_turns_in_place': scene_turns,
        'tier': chosen.get('tier', 'tier1'),
        'event_id': chosen['id'],
        'category': chosen.get('category', ''),
        'channel_hint': str(chosen.get('channel') or ''),
        'banned_channels': banned_labels,
        'objective_event': chosen['objective_event'],
        'linked_seed': linked_summary,
        'seed_to_add': chosen.get('seed_to_add'),
        'seed_consumed': chosen.get('requires_seed'),
        'cooldown': int(chosen.get('cooldown', 8)),
        'once': bool(chosen.get('once', False)),
    }


def advance_director_state(root, memory_text, *, location, director_roll, effective_progress, had_events, memory_fact,
                           director_echo=None, active_cast=(), new_clock=None, day_crossed=False, pacing_mode='standard'):
    """Atomically advance 【世界导演状态】 (threads, clocks, channels, seeds, dual-track cooldowns & entropy) on committed paid action."""
    cfg = director_config(root)
    roll = director_roll if isinstance(director_roll, dict) else {}
    eff_pacing_mode = roll.get('pacing_mode') or pacing_mode
    pacing = _resolve_director_pacing(cfg, eff_pacing_mode)
    catalog = load_world_beats(root, optional=True)
    channels_map = catalog.get('channels') or DIRECTOR_DEFAULT_CHANNELS
    clocks_cfg = catalog.get('offstage_clocks') or {}
    dstate = parse_director_block(memory_text)

    loc_changed = bool(dstate['scene_location'] and dstate['scene_location'] != location)
    dstate['scene_turns'] = (dstate['scene_turns'] + 1) if dstate['scene_location'] == location else 1
    dstate['scene_location'] = location
    dstate['global_cooldown'] = max(0, dstate['global_cooldown'] - 1)
    dstate['heroine_cd'] = max(0, int(dstate.get('heroine_cd', 0)) - 1)
    dstate['turns_since_beat'] = min(999, dstate['turns_since_beat'] + 1)
    dstate['event_cooldowns'] = {k: v - 1 for k, v in dstate['event_cooldowns'].items() if v > 1}
    for s in dstate['pending_seeds']:
        s['age'] = int(s.get('age', 0)) + 1

    # 1. Advance active_threads (age, close, touch escalation, deduped creation, cap)
    max_threads = max(1, int(cfg.get('max_active_threads', 5)))
    max_thread_age = max(2, int(cfg.get('max_thread_age', 12)))
    echo = director_echo if isinstance(director_echo, dict) else {}
    closed_ids = set(echo.get('close_thread') or [])
    touched_tid = roll.get('thread_id') if (roll.get('triggered') and roll.get('mode') == 'thread_spark') else ''

    next_threads = []
    for t in dstate['active_threads']:
        if t['id'] in closed_ids:
            continue
        t['age'] = int(t.get('age', 0)) + 1
        if t['id'] == touched_tid:
            t['touches'] = int(t.get('touches', 0)) + 1
            if t.get('tension') == 'soft':
                t['tension'] = 'hard'
        if t['age'] <= max_thread_age:
            next_threads.append(t)

    new_t = echo.get('new_thread')
    if isinstance(new_t, dict) and new_t.get('topic'):
        duplicate = next((t for t in next_threads if _thread_topic_similar(t['topic'], new_t['topic'])), None)
        if duplicate is not None:
            duplicate['age'] = 0
            if new_t.get('tension') == 'hard':
                duplicate['tension'] = 'hard'
            for w in new_t.get('who') or []:
                if w not in duplicate['who']:
                    duplicate['who'].append(w)
        else:
            tid = f"TH-{dstate['next_thread_seq']}"
            dstate['next_thread_seq'] += 1
            next_threads.append({
                'id': tid,
                'who': list(new_t.get('who') or []),
                'topic': new_t['topic'],
                'tension': 'hard' if new_t.get('tension') == 'hard' else 'soft',
                'age': 0,
                'touches': 0,
            })
            if len(next_threads) > max_threads:
                soft_idx = next((i for i, item in enumerate(next_threads[:-1]) if item['tension'] == 'soft'), 0)
                next_threads.pop(soft_idx)
    dstate['active_threads'] = next_threads[-max_threads:]

    # 2. Advance offstage_clocks (cooldown decay, landing/omen commit, Stage 2 nudges, deterministic offstage tick)
    if clocks_cfg:
        for cid in clocks_cfg:
            dstate['offstage_clocks'].setdefault(cid, {'p': 0, 'ph': 0, 'so': False, 'cd': 0})
        for cid, cst in dstate['offstage_clocks'].items():
            cst['cd'] = max(0, int(cst.get('cd', 0)) - 1)

        if roll.get('triggered') and roll.get('mode') == 'offstage_clock':
            rcid = roll.get('clock_id')
            if rcid in dstate['offstage_clocks'] and rcid in clocks_cfg:
                cst = dstate['offstage_clocks'][rcid]
                phases = clocks_cfg[rcid].get('phases') or []
                if roll.get('clock_stage') == 'hard':
                    cst['p'] = 0
                    cst['so'] = False
                    if phases:
                        cst['ph'] = (int(cst.get('ph', 0)) + 1) % len(phases)
                    cst['cd'] = 6
                else:
                    cst['so'] = True
                    cst['cd'] = max(int(cst.get('cd', 0)), 2)

        for cid, delta in (echo.get('clock_nudges') or {}).items():
            if cid in dstate['offstage_clocks'] and cid in clocks_cfg and type(delta) is int:
                max_seg = max(2, int(clocks_cfg[cid].get('max_segments', 4)))
                soft_at = max(1, min(max_seg - 1, int(clocks_cfg[cid].get('soft_at', max_seg - 1))))
                cst = dstate['offstage_clocks'][cid]
                cst['p'] = max(0, min(max_seg, int(cst.get('p', 0)) + delta))
                if cst['p'] < soft_at:
                    cst['so'] = False

        new_slot = _clock_time_slot(new_clock) if isinstance(new_clock, dict) else ''
        slot_changed = bool(new_slot and dstate['last_time_slot'] and new_slot != dstate['last_time_slot'])
        tick_interval = max(1, int(cfg.get('clock_tick_interval', 3)))
        dstate['clock_tick_acc'] = int(dstate.get('clock_tick_acc', 0)) + 1
        if day_crossed or slot_changed or dstate['clock_tick_acc'] >= tick_interval:
            dstate['clock_tick_acc'] = 0
            cast_set = set(active_cast or ())
            clock_ids = list(clocks_cfg.keys())
            rot = (dstate['scene_turns'] + dstate['turns_since_beat']) % len(clock_ids)
            rotated = clock_ids[rot:] + clock_ids[:rot]
            eligible = []
            for idx_pos, cid in enumerate(rotated):
                meta = clocks_cfg[cid]
                cst = dstate['offstage_clocks'][cid]
                max_seg = max(2, int(meta.get('max_segments', 4)))
                if meta.get('owner') in cast_set or cst['cd'] > 0 or cst['p'] >= max_seg:
                    continue
                eligible.append((cst['p'], idx_pos, cid, max_seg))
            if eligible:
                eligible.sort(key=lambda x: (x[0], x[1]))
                _, _, pick_cid, max_seg = eligible[0]
                dstate['offstage_clocks'][pick_cid]['p'] = min(max_seg, dstate['offstage_clocks'][pick_cid]['p'] + 1)
        if new_slot:
            dstate['last_time_slot'] = new_slot

    # 3. Record anti-cliché media channel sliding window
    chan_win = max(1, int(cfg.get('channel_cooldown_window', 4)))
    used_chan = echo.get('used_channel') or (roll.get('channel_hint') if roll.get('triggered') else '')
    if isinstance(used_chan, str) and used_chan in channels_map:
        dstate['recent_channels'].append(used_chan)
        dstate['recent_channels'] = dstate['recent_channels'][-chan_win:]

    # 4. Advance decoupled cooldowns, seeds & entropy calm_streak
    is_heroine_beat = bool(roll.get('triggered') and roll.get('category') in ('sensual_hook', 'erotic_accident'))
    if roll.get('triggered'):
        mode = roll.get('mode') or 'preset_beat'
        if mode == 'preset_beat':
            eid = roll.get('event_id')
            if eid:
                cd = max(1, int(roll.get('cooldown', 8)))
                dstate['event_cooldowns'][eid] = cd
                if roll.get('once') and eid not in dstate['consumed_once']:
                    dstate['consumed_once'].append(eid)
            if roll.get('category') == 'erotic_accident':
                dstate['event_cooldowns']['__EROTIC_CATEGORY__'] = pacing['erotic_category_cooldown']
            consumed_seed = roll.get('seed_consumed')
            if consumed_seed:
                dstate['pending_seeds'] = [s for s in dstate['pending_seeds'] if s['seed_id'] != consumed_seed]
            add_seed = roll.get('seed_to_add')
            if isinstance(add_seed, dict) and add_seed.get('seed_id'):
                sid = add_seed['seed_id']
                dstate['pending_seeds'] = [s for s in dstate['pending_seeds'] if s['seed_id'] != sid]
                dstate['pending_seeds'].append({
                    'seed_id': sid,
                    'summary': str(add_seed.get('summary') or '')[:120],
                    'age': 0,
                })
                dstate['pending_seeds'] = dstate['pending_seeds'][-DIRECTOR_SEED_LIMIT:]
        if is_heroine_beat:
            dstate['heroine_cd'] = pacing['heroine_beat_cooldown']
            dstate['calm_streak'] = 0
        elif roll.get('tier') in ('tier2', 'tier3', 'tier4'):
            dstate['global_cooldown'] = max(1, int(cfg.get('global_cooldown', 1)))
            dstate['turns_since_beat'] = 0
            dstate['calm_streak'] = 0
        else:
            dstate['calm_streak'] = max(0, dstate['calm_streak'] - 1)
    else:
        meaningful = bool(effective_progress or had_events or loc_changed)
        dstate['calm_streak'] = 0 if meaningful else (dstate['calm_streak'] + 1)

    if is_heroine_beat:
        dstate['sensual_drought'] = 0
    else:
        dstate['sensual_drought'] = min(12, int(dstate.get('sensual_drought', 0)) + 1)

    return write_director_block(memory_text, dstate)


def derive_weekday(data, memory_text, clock, save_state=None):
    """Deterministically derive current Chinese weekday from save_state/prologue base weekday + clock.day."""
    base = ''
    if isinstance(save_state, dict):
        rt = save_state.get('runtime')
        if isinstance(rt, dict):
            pro_s = rt.get('prologue')
            if isinstance(pro_s, dict) and pro_s.get('weekday') in WEEKDAYS:
                base = pro_s['weekday']
            elif rt.get('weekday') in WEEKDAYS:
                # runtime.weekday already reflects current day when prologue base is unavailable
                return rt['weekday']
    if not base and isinstance(data, dict):
        pro = data.get('prologue')
        if isinstance(pro, dict) and pro.get('weekday') in WEEKDAYS:
            base = pro['weekday']
    if not base and memory_text:
        m = re.search(r'【1】\s*(周[一二三四五六日])', memory_text)
        if m and m.group(1) in WEEKDAYS:
            base = m.group(1)
    if not base:
        base = '周二'
    day = int((clock or {}).get('day') or 1)
    idx = (WEEKDAYS.index(base) + max(0, day - 1)) % 7
    return WEEKDAYS[idx]


def reconcile_offstage_presence(engine, memory_path, new_clock, weekday, player_location, *, overnight=False, day_crossed=False, player_moved=False):
    """Deterministically reconcile OFFSTAGE NPC locations per lore.驻地; never teleports co-present NPCs."""
    if not new_clock or not weekday or weekday not in WEEKDAYS:
        return []
    content = Path(memory_path).read_text(encoding='utf-8')
    presence = engine.parse_presence_from_memory(content)
    if not presence:
        return []
    hour, part = map(int, new_clock['time'].split(':'))
    hhmm = hour * 60 + part
    is_workday = weekday in ('周一', '周二', '周三', '周四', '周五')
    updates = {}
    moves = []

    def plan_move(name, target_loc, target_reason):
        info = presence.get(name)
        if not info or info.get('location') == player_location:
            return  # Never move an NPC currently in the same scene as the player.
        if target_loc == player_location and not (player_moved or overnight or day_crossed):
            return  # Never silently pop an offstage NPC into an ongoing same-scene conversation.
        if info.get('location') != target_loc:
            updates[name] = {'location': target_loc, 'reason': target_reason}
            moves.append({'name': name, 'from': info.get('location'), 'to': target_loc, 'reason': target_reason})

    # 沈知韫：工作日 08:00-15:59 在公司，其余时段/周末在徐家主宅（临时加班事由在跨夜前不强行迁离）
    shen_info = presence.get('沈知韫') or {}
    shen_reason = str(shen_info.get('reason') or '')
    shen_overtime = (
        shen_info.get('location') == '公司'
        and not overnight
        and not day_crossed
        and any(k in shen_reason for k in ('加班', '复核', '并购', '临时工作'))
    )
    if is_workday and 480 <= hhmm < 960:
        plan_move('沈知韫', '公司', '工作日上班中')
    elif not shen_overtime:
        plan_move('沈知韫', '徐家主宅', '常住')

    # 徐念薇：工作日 08:00-16:59 在大学，17:00-21:59 在校外画室（工作室），22:00后及周末在徐家主宅
    if is_workday and 480 <= hhmm < 1020:
        plan_move('徐念薇', '大学', '工作日在大学')
    elif is_workday and 1020 <= hhmm < 1320:
        plan_move('徐念薇', '工作室', '校外画室作画')
    else:
        plan_move('徐念薇', '徐家主宅', '周末在家' if not is_workday else '晚间回宅')

    # 苏婉青：常住市中心顶层公寓；周二/五 15:30-18:30 到访、最晚留至 20:30，周日 10:00-15:00 请安午餐；若宿主显式留住/过夜则不强行驱回公寓
    su_info = presence.get('苏婉青')
    if su_info:
        in_arrival_window = (
            (weekday in ('周二', '周五') and 930 <= hhmm <= 1110)
            or (weekday == '周日' and 600 <= hhmm <= 900)
        )
        in_stay_window = (
            (weekday in ('周二', '周五') and 930 <= hhmm <= 1230)
            or (weekday == '周日' and 600 <= hhmm <= 900)
        )
        su_reason = str(su_info.get('reason') or '')
        explicit_stay = any(k in su_reason for k in ('留住', '过夜', '宿', '留下'))
        if su_info.get('location') == '徐家主宅':
            if overnight or day_crossed or (not in_stay_window and not explicit_stay):
                plan_move('苏婉青', '市中心顶层公寓', '常住')
        elif su_info.get('location') == '市中心顶层公寓':
            if in_arrival_window and not overnight:
                plan_move('苏婉青', '徐家主宅', '回主宅请安看望')

    if updates:
        rr._engine_call(engine.update_presence, updates)
    return moves


def derive_micro_state_changes(engine, events, conditions, cast, before_memory):
    """Deterministically derive momentary_ease / confusion_debt / residual_tension from settled action events."""
    changes = {}
    intensity = (conditions or {}).get('intensity', 'A')
    shame_ev = (events or {}).get('shame_events') or {}
    dep_ev = (events or {}).get('depravity_events') or {}
    aff_ev = (events or {}).get('affection_events') or {}
    ds_ev = (events or {}).get('ds_events') or {}
    host_ev = (events or {}).get('host_events') or []

    warm_aff_tags = {engine._event_tag(f'AFFECTION_0{i}') for i in (3, 4, 5, 6, 7)} | {
        engine._event_tag('AFFECTION_10'),
        engine._event_tag('AFFECTION_11'),
    }
    warm_host_tags = {engine._event_tag('HOST_05'), engine._event_tag('HOST_06'), engine._event_tag('HOST_08')}
    heavy_shame_tags = {
        engine._event_tag('SHAME_04'),
        engine._event_tag('SHAME_05'),
        engine._event_tag('SHAME_06'),
        engine._event_tag('SHAME_07'),
        engine._event_tag('SHAME_20'),
    }
    heavy_dep_tags = {engine._event_tag('DEPRAVITY_01'), engine._event_tag('DEPRAVITY_10')}
    probe_shame_tags = {engine._event_tag('SHAME_01'), engine._event_tag('SHAME_02'), engine._event_tag('SHAME_19')}
    climax_tags = {engine._event_tag('DS_17'), engine._event_tag('DS_18')}
    cog_tear_tag = engine._event_tag('HOST_01')
    coy_tag = engine._event_tag('AFFECTION_12')

    has_warm_host = any(t in warm_host_tags for t in host_ev)
    has_cog_tear = cog_tear_tag in host_ev

    for name in cast:
        if name not in PASSIVE_TARGETS:
            continue
        s_tags = shame_ev.get(name) or []
        p_tags = dep_ev.get(name) or []
        a_tags = aff_ev.get(name) or []
        d_tags = ds_ev.get(name) or []
        cur_shame = engine._read_attr_value(before_memory, name, '羞耻')
        cur_shame = 100 if cur_shame is None else cur_shame
        delta = {}
        if (
            intensity == 'C'
            or any(t in heavy_shame_tags for t in s_tags)
            or any(t in heavy_dep_tags for t in p_tags)
            or any(t in climax_tags for t in d_tags)
        ):
            delta['residual_tension'] = True
        if has_cog_tear or (coy_tag in a_tags) or (cur_shame > 75 and any(t in probe_shame_tags for t in s_tags)):
            delta['confusion_debt'] = True
        if intensity in ('A', 'B') and (has_warm_host or any(t in warm_aff_tags for t in a_tags)) and not delta.get('residual_tension'):
            delta['momentary_ease'] = True
        if delta:
            changes[name] = delta
    return changes


def passive_level_info(level_int):
    idx = max(0, min(len(PASSIVE_LEVELS) - 1, int(level_int)))
    return PASSIVE_LEVELS[idx]


def read_passive_level(content, target):
    m = re.search(rf'\[{re.escape(target)}\][^\n]*?被动\s*Lv\.(\d+)', content or '')
    return int(m.group(1)) if m else 0


def memory_policy(root):
    policy = rr.load_request((Path(root)/'txt文件/互动运行配置.json').read_text(encoding='utf-8')).get('memory', MEMORY_DEFAULTS)
    if (not isinstance(policy, dict) or set(policy) != set(MEMORY_DEFAULTS)
            or any(type(v) is not int or v < 1 or v > 100000 for v in policy.values())):
        raise rr.RoundError('记忆预算配置无效')
    return policy


def memory_text(value, label, limit, empty=False):
    if (not isinstance(value, str) or len(value) > limit or any(c in value for c in ('\n','\r','\x00','▲','【回合生命周期】'))
            or re.match(r'^\s*【\d',value) and label != 'memory.transfer'):
        raise rr.RoundError(label+'须为预算内的单段文本，不得注入结构锚点')
    if not empty and not value.strip():
        raise rr.RoundError(label+'不得为空')
    return value.strip()


def memory_merge(root, layers, number, clock, value, system=False, *, prologue_active=False):
    """Model supplies semantic compaction; never silently truncate accepted facts. Replaces literary prologue on Round 1."""
    raw_prior = next((entry.split('】',1)[1] for entry in layers['L1'] if entry.startswith('【'+str(number)+'】')), '')
    prior = save_store.strip_prologue_marker(raw_prior)
    if system:
        return None
    limit = memory_policy(root)['round_chars']
    fact = value['fact'].strip()
    compact = value.get('compact','').strip()
    if compact:
        if not prior:
            raise rr.RoundError('同回合合并摘要缺少原条目')
        return save_store.strip_prologue_marker(compact)
    if prologue_active and number == 1 and fact:
        return '第'+str(clock['day'])+'天 '+clock['time']+' '+fact
    if fact and re.sub(r'\s','',fact) in re.sub(r'\s','',prior):
        fact = ''
    stamped = '第'+str(clock['day'])+'天 '+clock['time']+' '+fact if fact else ''
    merged = '\n'.join(s for s in (prior,stamped) if s).strip()
    if len(merged) > limit:
        raise rr.RoundError('本回合记忆超过预算，须据原文交memory.compact保留重要事实、待办和知情边界；未截断旧事实')
    return merged if merged and merged != prior else None


def enabled(root):
    path = Path(root)/'txt文件/互动运行配置.json'
    return path.is_file() and json.loads(path.read_text(encoding='utf-8'))['resource'].get('scheme') == 'fixed_tiers'


def config(root):
    value = rr.load_request((Path(root)/'txt文件/互动运行配置.json').read_text(encoding='utf-8'))
    r = value['resource']
    if (value['version'] != 2 or r.get('status') != 'active' or r.get('scheme') != 'fixed_tiers'
            or r.get('costs') != COSTS or r.get('custom_reserve') != 15
            or r.get('attribute') != '体力' or r.get('maximum') != 100
            or r.get('item_recovery_percent') != 20 or r.get('minimum_action') != 5):
        raise rr.RoundError('固定三档配置非法，禁止隐式降级或重复旧基础费')
    return value


def stamina(root, files):
    engine = rr._engine(Path(root), Path(root))
    value = engine._read_attr_value(files[rr.FILES[0]].decode(), '系统宿主', '体力')
    if type(value) is not int or not 0 <= value <= config(root)['resource']['maximum']:
        raise rr.RoundError('正式宿主体力缺失或超出范围')
    return value


def state(root, files):
    data = json.loads(files.get('data.json') or b'{}')
    value = data.get('story_runtime')
    if value is None:
        # 优先从 存档/save_state.json 的 runtime 恢复（即使 data.json 丢失或被旧入口覆盖也不丢时钟与休息态）
        if files.get(save_store.SAVE_STATE_PATH):
            try:
                st_obj, _, _ = save_store.load_bundle(root, files)
                rt = st_obj.get('runtime') or {}
                if rt.get('clock') is not None or int(rt.get('action_index') or 0) > 0 or int(rt.get('last_closed') or 0) > 0:
                    value = {
                        'version': 1,
                        'clock': copy.deepcopy(rt.get('clock')),
                        'memory_round': max(1, int(rt.get('memory_round') or 1)),
                        'last_closed': max(0, int(rt.get('last_closed') or 0)),
                        'phase': rt.get('phase') if rt.get('phase') in ('ready', 'resting') else 'ready',
                        'item_recovered': max(0, int(rt.get('item_recovered') or 0)),
                        'action_index': max(0, int(rt.get('action_index') or 0)),
                        'closed_by': str(rt.get('closed_by') or ''),
                    }
            except Exception:
                value = None
    if value is None:
        engine = rr._engine(Path(root), Path(root))
        _, _, previous = rr._memory_state(engine, files)
        content = files[rr.FILES[0]].decode()
        old = re.search(r'^【回合生命周期】\s*\n([^\n]+)', content, re.M)
        action_index = json.loads(old[1]).get('round', 0) if old else 0
        return {'version': 1, 'clock': None, 'memory_round': previous+1,
                'last_closed': previous, 'phase': 'ready', 'item_recovered': 0,
                'action_index': action_index, 'closed_by': ''}
    required = {'version','clock','memory_round','last_closed','phase','item_recovered','action_index','closed_by'}
    rr._keys(value, required, 'story_runtime', required)
    if value['version'] != 1 or value['phase'] not in ('ready','resting'):
        raise rr.RecoveryError('互动时间状态无效')
    for key in ('memory_round','last_closed','item_recovered','action_index'):
        rr._integer(value[key], key, 1 if key == 'memory_round' else 0)
    if value['last_closed'] != value['memory_round']-1 or value['item_recovered'] > 20:
        raise rr.RecoveryError('互动回合或道具额度不一致')
    if value['clock'] is not None:
        minute(value['clock'])
    return copy.deepcopy(value)


def minute(clock):
    rr._keys(clock, {'day','time'}, 'clock', {'day','time'})
    rr._integer(clock['day'], 'clock.day', 1)
    if not isinstance(clock['time'], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock['time']):
        raise rr.RoundError('游戏时刻须为HH:MM')
    hour, part = map(int, clock['time'].split(':'))
    return (clock['day']-1)*1440+hour*60+part


def item_quote(root, files, item_id):
    if not isinstance(item_id,str) or not re.fullmatch(r'ITEM-\d+',item_id):
        raise rr.RoundError('恢复道具ID无效')
    engine=rr._engine(Path(root),Path(root))
    text=(files[rr.FILES[1]] or b'').decode()
    found=engine._find_item_block(text,item_id=item_id)
    if not found:
        raise rr.RoundError('没有该活跃库存，未消耗道具')
    fields=engine._parse_item_block(found['block'])
    if (fields['当前状态']!='仓库中' or fields['使用对象'] not in ('','无','未使用','徐志北')
            or not fields['数量'].isdigit() or int(fields['数量']) < 1
            or re.fullmatch(r'0\s*(?:回合|次|分钟)?',fields['剩余时效'])):
        raise rr.RoundError('该道具未持有或已过期，未消耗')
    effect=re.fullmatch(r'host_stamina:([1-9]\d{0,3})',fields.get('系统效果',''))
    if not effect:
        raise rr.RoundError('该道具未登记宿主体力恢复效果，不能猜测数值')
    if '临时性' in fields['类型'] and fields['时效'].isdigit() and int(fields['时效']) > 0:
        timer=re.search(r'^'+re.escape(item_id)+r'：(\d+)回合\s*\|',files[rr.FILES[0]].decode(),re.M)
        if not timer or int(timer[1]) < 1:
            raise rr.RoundError('道具有效时效未核实，未消耗')
    runtime=state(root,files)
    gain=min(int(effect[1]),20-runtime['item_recovered'],100-stamina(root,files))
    if gain <= 0:
        raise rr.RoundError('体力已满或两次整夜间恢复额度已用完，未消耗道具')
    return {'item_id':item_id,'name':re.search(r'【道具名称】：([^\n]+)',found['block'])[1].strip(),
            'effect':int(effect[1]),'recovery':gain,'quantity':1,'remaining_budget':20-runtime['item_recovered']-gain}


def active_costs(root, files=None):
    """Return active A/B/C stamina costs (applies slow-burn intimate continuation discount when in an active intimate session)."""
    cfg = config(root)
    res = cfg.get('resource') or {}
    base = dict(COSTS)
    if files is None:
        return base
    try:
        st_obj, _, _ = save_store.load_bundle(Path(root), files)
        intl = (st_obj.get('intimate') or {})
        min_beats = int(res.get('intimate_min_beats_for_discount', 1))
        if intl.get('scene_active') and int(intl.get('session_beats', 0) or 0) >= min_beats:
            disc = res.get('intimate_continuation_costs') or {}
            return {
                'A': int(disc.get('A', base['A'])),
                'B': int(disc.get('B', base['B'])),
                'C': int(disc.get('C', base['C'])),
            }
    except Exception:
        pass
    return base


def stamina_guard_info(root, files=None):
    """Return intimate stamina floor guard state: during active sex with vigor >= 15, daily stamina never drops below floor (10)."""
    cfg = config(root)
    res = cfg.get('resource') or {}
    floor = max(5, int(res.get('intimate_stamina_floor', 10) or 10))
    min_vigor = max(0, int(res.get('vigor_min_floor_guard', 15) or 15))
    if files is None:
        return {'active': False, 'floor': floor, 'vigor': 100, 'min_vigor': min_vigor}
    try:
        st_obj, _, _ = save_store.load_bundle(Path(root), files)
        intl = st_obj.get('intimate') or {}
        hp = intl.get('host_phys') or {}
        vigor = max(0, min(100, int(hp.get('vigor', 100) if hp.get('vigor') is not None else 100)))
        active = bool(intl.get('scene_active') and vigor >= min_vigor)
        return {'active': active, 'floor': floor, 'vigor': vigor, 'min_vigor': min_vigor}
    except Exception:
        return {'active': False, 'floor': floor, 'vigor': 100, 'min_vigor': min_vigor}


def apply_stamina_floor(current_stamina, raw_cost, guard):
    """Apply intimate stamina floor guard: when active and current <= floor, stamina cost is 0 (vigor absorbs effort)."""
    cost = max(0, int(raw_cost or 0))
    if not (isinstance(guard, dict) and guard.get('active')):
        return cost
    floor = max(5, int(guard.get('floor', 10) or 10))
    if current_stamina <= floor:
        return 0
    return min(cost, max(0, current_stamina - floor))


def quote(root, files, selected, text, command=None):
    config(root)
    if selected is None:
        raise rr.ConflictError('收费入口须绑定当前抉择，旧格式不可绕过')
    option=selected['option_id']
    runtime=state(root,files)
    current=stamina(root,files)
    match=PURE_ITEM.fullmatch(text) if option=='CUSTOM' else None
    item=command if command and command.get('code')=='use_recovery_item' else None
    if item:
        rr._keys(item,{'code','item_id'},'use_recovery_item',{'code','item_id'})
        if option!='CUSTOM' or not match or match[1]!=item['item_id']:
            raise rr.RoundError('免费道具只能提交纯使用命令，不可混入额外行动')
    if match:
        item={'code':'use_recovery_item','item_id':match[1]}
    if runtime['phase']=='resting' or current < 5:
        if option not in ('REST','BEGIN') or item:
            raise rr.RoundError('体力不足或正在强制休息，普通行动暂停')
        kind='rest'
    elif option=='REST':
        raise rr.ConflictError('当前没有待完成的强制休息')
    elif option=='BEGIN':kind='begin'
    elif item:kind='item'
    else:kind='action'
    tier_costs = active_costs(root, files)
    guard = stamina_guard_info(root, files)
    raw_amount = tier_costs.get(option, tier_costs['C']) if kind=='action' else 0
    amount = apply_stamina_floor(current, raw_amount, guard) if kind=='action' else 0
    if current < amount:
        raise rr.RoundError('体力不足以预扣本档费用，请选择可用档位或提前使用恢复道具')
    value={'status':'active','scheme':'fixed_tiers','kind':kind,'attribute':'体力','total':amount,
           'before':current,'after':current-amount,'policy_version':2,'option_id':option,
           'intimate_discount': tier_costs != COSTS,
           'stamina_guard': guard['active'], 'stamina_floor': guard['floor'], 'vigor_before': guard['vigor']}
    if kind=='item':value['item']=item_quote(root,files,item['item_id'])
    return value


def change_stamina(root, files, value):
    result=dict(files)
    engine=rr._engine(Path(root),Path(root))
    old_mem=files[rr.FILES[0]]
    new_mem=engine._simulate_panel(old_mem.decode(),{'系统宿主':{'体力':value}}).encode()
    result[rr.FILES[0]]=new_mem
    if result.get(save_store.SAVE_STATE_PATH):
        try:
            st_obj=json.loads(result[save_store.SAVE_STATE_PATH].decode('utf-8'))
            if isinstance(st_obj,dict) and isinstance(st_obj.get('panels'),dict) and isinstance(st_obj['panels'].get('系统宿主'),dict):
                sha=st_obj.get('rendered_sha256') or {}
                prior_drifted=bool(sha.get('memory_txt') and save_store._sha256_bytes(old_mem)!=sha['memory_txt'])
                if not prior_drifted:
                    st_obj['panels']['系统宿主']['体力']=value
                    st_obj.setdefault('rendered_sha256',{})['memory_txt']=save_store._sha256_bytes(new_mem)
                    result[save_store.SAVE_STATE_PATH]=save_store._json_bytes(st_obj)
        except Exception:
            pass
    return result


MAX_TERMINAL_JOBS = 20


def prune_tasks_state(tasks, *, keep_terminal=MAX_TERMINAL_JOBS):
    """Strip heavy Base64 snapshots from all non-held reservations and cap terminal jobs in tasks.json."""
    if not isinstance(tasks, dict) or not isinstance(tasks.get('jobs'), dict):
        return tasks
    jobs = tasks['jobs']
    latest_id = tasks.get('latest')
    active_ids = set()
    terminal_rows = []
    for jid, job in list(jobs.items()):
        if not isinstance(job, dict):
            jobs.pop(jid, None)
            continue
        status = str(job.get('status') or '')
        res = job.get('reservation')
        is_held = isinstance(res, dict) and res.get('status') == 'held'
        if not is_held and isinstance(res, dict):
            res.pop('before_memory', None)
            res.pop('before_save_state', None)
        if status in ACTIVE_JOB_STATUSES or status == 'refund_pending' or is_held or jid == latest_id:
            active_ids.add(jid)
        else:
            ts = float(job.get('committed_at') or job.get('returned_at') or job.get('created_at') or 0)
            terminal_rows.append((ts, jid))
    if len(terminal_rows) > keep_terminal:
        terminal_rows.sort(key=lambda pair: (pair[0], pair[1]))
        for _, stale_jid in terminal_rows[:-keep_terminal]:
            if stale_jid not in active_ids:
                jobs.pop(stale_jid, None)
    return tasks


def commit_tasks(store, files, tasks):
    prune_tasks_state(tasks)
    after=dict(files)
    after[rr.META]=rr._json(store._ledger())
    after[TASKS]=rr._json(tasks)
    store._commit_files(after)


def reserve(service, tasks, job, files, cost):
    held=change_stamina(service.root,files,cost['after'])
    job['reservation']={
        'status':'held','quote':cost,
        'before_memory':base64.b64encode(files[rr.FILES[0]]).decode(),
        'before_save_state':base64.b64encode(files[save_store.SAVE_STATE_PATH]).decode() if files.get(save_store.SAVE_STATE_PATH) else None,
        'original_revision':rr._revision(files),'held_revision':rr._revision(held),
    }
    job['working_revision']=rr._revision(held)
    job['status']='preparing'
    tasks['jobs'][job['request_id']]=job;tasks['latest']=job['request_id']
    commit_tasks(service.store,held,tasks)
    return held


def refund(service,tasks,job,status,error):
    reservation=job.get('reservation')
    committed=service.store._ledger()['receipts'].get(job['request_id'])
    if committed:
        job.update(status='committed',error='',receipt=committed['receipt'],lease=None)
        if reservation:
            reservation['status']='settled'
            reservation.pop('before_memory', None)
            reservation.pop('before_save_state', None)
        commit_tasks(service.store,service.store._files(),tasks)
        return
    if reservation and reservation['status']=='held':
        files=service.store._files()
        if rr._revision(files)!=reservation['held_revision']:
            job.update(status='refund_pending',lease=None,error='存档被外部改动，退款待恢复；未覆盖他方更改。')
            commit_tasks(service.store,files,tasks)
            raise rr.RecoveryError(job['error'])
        files[rr.FILES[0]]=base64.b64decode(reservation['before_memory'],validate=True)
        if reservation.get('before_save_state') is not None:
            files[save_store.SAVE_STATE_PATH]=base64.b64decode(reservation['before_save_state'],validate=True)
        if rr._revision(files)!=reservation['original_revision']:
            raise rr.RecoveryError('预扣原始指纹不一致，拒绝猜测退款')
        reservation['status']='refunded'
        reservation.pop('before_memory', None)
        reservation.pop('before_save_state', None)
        job['refund']={'amount':reservation['quote']['total'],'status':'refunded','reason':error}
        job.update(status=status,error=error,lease=None)
        commit_tasks(service.store,files,tasks)
    else:
        job.update(status=status,error=error,lease=None)
        commit_tasks(service.store,service.store._files(),tasks)


def resolution(root,files,body):
    value=body['resolution']
    required={'category','basis','clock','events','memory','conditions','sleep','task','items'}
    rr._keys(value,required | {'intel_used','director_echo','scene_state'},'resolution',required)
    selected=body['selection'];reservation=body['audit'].get('reservation')
    if not isinstance(reservation,dict) or reservation.get('status')!='held':
        raise rr.RoundError('缺少由正式任务写入器登记的预扣')
    cost=reservation['quote'];kind=cost['kind']
    if value['category'] not in (*COSTS,'SYSTEM'):
        raise rr.RoundError('分类只能为A/B/C或免费系统SYSTEM')
    if kind=='action':
        rr._audit_line(value['basis'],'resolution.basis',reason=True)
        if selected['option_id'] in COSTS and value['category']!=selected['option_id']:
            raise rr.RoundError('固定选项不允许模型重新定价')
        if value['category'] not in COSTS:
            raise rr.RoundError('普通自定义须判A/B/C，不得免费')
    elif value['category']!='SYSTEM':
        raise rr.RoundError('启动/道具/休息须为SYSTEM')
    rr._keys(value['clock'],{'day','time','basis'},'resolution.clock',{'day','time','basis'})
    clock={k:value['clock'][k] for k in ('day','time')};end=minute(clock)
    rr._audit_line(value['clock']['basis'],'clock.basis',reason=True)
    runtime=state(root,files);start=minute(runtime['clock']) if runtime['clock'] else None
    if start is None and clock['day']!=1 and cost['kind']!='rest':
        raise rr.RoundError('首次时钟从游戏第1天初始化，不能借初始化关闭空回合')
    if start is not None and (end<start or end-start>7*1440):
        raise rr.RoundError('游戏时间须连续向前，单次不得跳过七天')
    texts='\n'.join(m['text'] for m in body['messages'])
    sleep=value['sleep']
    rr._keys(sleep,{'kind','start','evidence'},'sleep',{'kind','start','evidence'})
    if sleep['kind'] not in ('none','interrupted','overnight','collapse'):
        raise rr.RoundError('睡眠状态非法')
    if sleep['kind']!='none':
        rr._text(sleep['evidence'],'sleep.evidence',500)
        if not _evidence_matches(sleep['evidence'],texts):
            raise rr.RoundError('休息依据必须引用本段实际正文')
    elif sleep['start'] is not None or sleep['evidence']!='':
        raise rr.RoundError('无睡眠不应携带伪起点或依据')
    if sleep['kind']=='overnight':
        begun=minute(sleep['start'])
        if ((start is not None and begun<start) or begun>=end or end-begun<360
                or (begun//1440>=end//1440 and int(sleep['start']['time'][:2])>=6)
                or not 5<=int(clock['time'][:2])<=12):
            raise rr.RoundError('安稳一晚须有至少六小时、跨夜至清晨的连续起止时间；短休不满恢复')
    if kind=='rest' and (sleep['kind'] not in ('interrupted','overnight') or (start is not None and end<=start)):
        raise rr.RoundError('免费休息须实际推进休息过渡；中断保持休息')
    if kind=='begin' and sleep['kind']!='none':
        raise rr.RoundError('启动段不得凭空结算睡眠')
    limits=memory_policy(root)
    mem_raw_obj=value['memory']
    rr._keys(mem_raw_obj,{'fact','anchor_ops','chronicle_digest','tags','transfers','compact'},'memory',{'fact'})
    clean_fact=memory_text(mem_raw_obj['fact'],'memory.fact',limits['fact_chars'],empty=True)
    raw_anchor_ops=mem_raw_obj.get('anchor_ops')
    parsed_anchor_ops=[]
    if raw_anchor_ops not in (None,''):
        if not isinstance(raw_anchor_ops,list) or len(raw_anchor_ops)>3:
            raise rr.RoundError('memory.anchor_ops须为最多3条的数组')
        for idx_op, aop in enumerate(raw_anchor_ops):
            if not isinstance(aop,dict):
                raise rr.RoundError(f'memory.anchor_ops[{idx_op}]须为对象')
            act=str(aop.get('op') or '').strip().lower()
            if act not in ('add','update','resolve'):
                raise rr.RoundError(f'memory.anchor_ops[{idx_op}].op须为add/update/resolve')
            if act=='add':
                atxt=memory_text(aop.get('text',''),f'memory.anchor_ops[{idx_op}].text',110,empty=False)
                akind=str(aop.get('kind') or 'milestone').strip()
                if akind not in save_store.ANCHOR_KINDS:
                    akind='milestone'
                aimp=aop.get('importance',3)
                if type(aimp) is not int or not 1<=aimp<=5:
                    aimp=3
                parsed_anchor_ops.append({
                    'op':'add','kind':akind,'text':atxt,'importance':aimp,
                    **({'entities':[str(x).strip() for x in aop['entities'] if isinstance(x,str) and x.strip()]} if isinstance(aop.get('entities'),list) else {}),
                    **({'known_by':[str(x).strip() for x in aop['known_by'] if isinstance(x,str) and x.strip()]} if isinstance(aop.get('known_by'),list) else {}),
                    **({'private_host':True} if aop.get('private_host') is True else {}),
                })
            elif act=='update':
                aid=str(aop.get('id') or '').strip()
                if not re.fullmatch(r'A-\d+',aid):
                    raise rr.RoundError(f'memory.anchor_ops[{idx_op}].id须为A-编号')
                atxt=memory_text(aop.get('text',''),f'memory.anchor_ops[{idx_op}].text',110,empty=False)
                upd={'op':'update','id':aid,'text':atxt}
                if type(aop.get('importance')) is int and 1<=aop['importance']<=5:
                    upd['importance']=aop['importance']
                parsed_anchor_ops.append(upd)
            else:
                aid=str(aop.get('id') or '').strip()
                if not re.fullmatch(r'A-\d+',aid):
                    raise rr.RoundError(f'memory.anchor_ops[{idx_op}].id须为A-编号')
                anote=memory_text(aop.get('note','') or '',f'memory.anchor_ops[{idx_op}].note',60,empty=True)
                parsed_anchor_ops.append({'op':'resolve','id':aid,**({'note':anote} if anote else {})})
    raw_cd=mem_raw_obj.get('chronicle_digest')
    parsed_chronicle_digest=None
    if raw_cd not in (None,''):
        if not isinstance(raw_cd,dict):
            raise rr.RoundError('memory.chronicle_digest须为对象或空字符串')
        rr._keys(raw_cd,{'public','views'},'memory.chronicle_digest')
        pub_txt=memory_text(raw_cd.get('public','') or '','memory.chronicle_digest.public',280,empty=True)
        views_raw=raw_cd.get('views')
        clean_views={}
        if views_raw not in (None,''):
            if not isinstance(views_raw,dict):
                raise rr.RoundError('memory.chronicle_digest.views须为对象')
            for vk,vv in views_raw.items():
                if vk in save_store._VALID_MEMORY_ACTORS and isinstance(vv,str) and vv.strip():
                    clean_views[vk]=memory_text(vv,f'memory.chronicle_digest.views.{vk}',140,empty=False)
        if pub_txt or clean_views:
            parsed_chronicle_digest={'public':pub_txt,'views':clean_views}
    parsed_mem_tags=[str(t).strip()[:16] for t in (mem_raw_obj.get('tags') or []) if isinstance(t,str) and t.strip()][:6] if isinstance(mem_raw_obj.get('tags'),list) else []
    parsed_memory_payload={'fact':clean_fact,'anchor_ops':parsed_anchor_ops,'chronicle_digest':parsed_chronicle_digest,'tags':parsed_mem_tags}
    engine=rr._engine(Path(root),Path(root))
    memory_raw=files[rr.FILES[0]].decode('utf-8')
    bundle_st, _, _ = save_store.load_bundle(Path(root), files)
    intl_now = bundle_st.get('intimate') or save_store.default_intimate()
    intimate_mode = bool(intl_now.get('scene_active'))
    presence=engine.parse_presence_from_memory(memory_raw)
    place=body['operation'].get('destination') if body.get('operation') and body['operation']['code']=='move_player' else presence['徐志北']['location']
    active_cast={n for n,info in presence.items() if n!='徐志北' and info['location']==place}
    if ((place=='徐家主宅' and re.search(r'^徐承邺位置：\s*(?:徐家主宅|徐家住宅)\b',memory_raw,re.M))
            or (place=='市中心顶层公寓' and re.search(r'^徐承邺位置：\s*市中心顶层公寓\b',memory_raw,re.M))):
        active_cast.add('徐承邺')
    remote_cast = set()
    op_body = body.get('operation')
    if isinstance(op_body, dict) and op_body.get('code') == 'inspect_deployed':
        dev_id = op_body.get('item_id')
        dev_obj = next((d for d in (bundle_st.get('items', {}).get('deployed') or []) if d.get('id') == dev_id), None)
        if dev_obj and dev_obj.get('location'):
            dloc = dev_obj['location']
            remote_cast = {n for n, info in presence.items() if n != '徐志北' and info['location'] == dloc}
    remote_allowed_tags = {
        'ds_events': {engine._event_tag('DS_18')},
        'depravity_events': {engine._event_tag('DEPRAVITY_10')},
        'shame_events': {engine._event_tag('SHAME_20')},
    }
    grouped={key:[] if key=='host_events' else {} for key in engine._load_event_registry()['groups']}
    if not isinstance(value['events'],list) or len(value['events'])>40:
        raise rr.RoundError('事件须为最多40组的数组')
    dep02_tag=engine._event_tag('DEPRAVITY_02')
    ds09_tag=engine._event_tag('DS_09')
    insomnia_targets=set()
    for event in value['events']:
        rr._keys(event,{'group','target','tags','evidence'},'event',{'group','target','tags','evidence'})
        group=event['group'];target=event['target'];tags=event['tags']
        if not isinstance(tags,list) or not tags or not all(isinstance(t,str) for t in tags):raise rr.RoundError('事件标签须为非空文本数组')
        if group not in grouped or (group=='host_events' and target!='系统宿主'):
            raise rr.RoundError('事件组或宿主目标无效')
        if group=='vigilance_events':
            if target not in engine.VIGILANCE_TARGETS:
                valid_vig = '/'.join(engine.VIGILANCE_TARGETS)
                raise rr.RoundError(
                    f'监视事件目标无效：{target}（vigilance_events.target 只能填被徐承邺监视的对象：{valid_vig}，严禁填监视者徐承邺本人；若正文仅口头提及徐承邺且无实质警惕增减，请直接删除该条事件）'
                )
        elif group=='depravity_events' and target=='徐承邺':
            raise rr.RoundError('徐承邺为男性对手，无堕落面板；死亡查岗_沉沦期的 target 须填在场女主姓名（沈知韫/苏婉青/徐念薇），若本幕无女主沉沦请删除该条事件')
        elif target!='系统宿主' and target not in active_cast:
            if target in remote_cast and group in remote_allowed_tags and set(tags) <= remote_allowed_tags[group]:
                pass
            else:
                valid_cast = '、'.join(sorted(active_cast)) or '无'
                raise rr.RoundError(f'事件对象不在本段实际场内：{target}（当前合法在场角色：{valid_cast}；请核对target或删除场外人物事件）')
        rr._text(event['evidence'],'event.evidence',1200)
        if not _evidence_matches(event['evidence'],texts):
            raise rr.RoundError('事件必须引用本段实际正文，不以选项或计划作已发生依据（请从 foreground_messages 的 text 中原样逐字截取子串作为 evidence）')
        if group=='ds_events' and ds09_tag in tags and re.search(r'失眠|彻夜未眠|一夜未睡|没合眼|睡不着|通宵未眠', event['evidence']):
            insomnia_targets.add(target)
        if group=='host_events':grouped[group].extend(tags)
        else:grouped[group].setdefault(target,[]).extend(tags)
    rr._validate_event_fields(Path(root),engine,grouped)
    if kind == 'action':
        player_in_txt = str(body.get('input') or body.get('action') or '')
        force_blackout_auth = bool(re.search(r'[（(][^）)]*(?:强行|强制|继续|不管断电|趁虚)[^）)]*[）)]', player_in_txt))
        if not force_blackout_auth:
            deep_heavy_tags = {engine._event_tag('SHAME_03'), engine._event_tag('SHAME_04')}
            for who, stags in grouped['shame_events'].items():
                if who in save_store.HEROINES and (set(stags) & deep_heavy_tags):
                    cur_npc_sta = int(((bundle_st.get('panels') or {}).get(who) or {}).get('体力', 100) or 0)
                    if cur_npc_sta <= 15:
                        raise rr.RoundError(f'{who}当前处于生理断电期（体力{cur_npc_sta}≤15），未获玩家括号强行授权前禁止继续施加深度/重度越界，请改为照料、低语余韵或收束场景')
    scene_state = rr._validate_scene_state(value.get('scene_state'), active_cast, building_cast=active_cast) if kind == 'action' else None
    intel_used_raw=value.get('intel_used')
    intel_used=None
    if intel_used_raw not in (None,''):
        if kind!='action':
            raise rr.RoundError('免费系统操作不可消耗商业情报')
        if not isinstance(intel_used_raw,dict):
            raise rr.RoundError('intel_used须为对象或空值')
        rr._keys(intel_used_raw,{'id','target','evidence'},'intel_used',{'id','target','evidence'})
        iid=intel_used_raw['id'];itarget=intel_used_raw['target']
        rr._text(intel_used_raw['evidence'],'intel_used.evidence',500)
        if not _evidence_matches(intel_used_raw['evidence'],texts):
            raise rr.RoundError('情报使用必须引用本段实际正文依据')
        catalog=load_intel_catalog(root,optional=False)
        item_cfg=next((x for x in catalog['items'] if x['id']==iid),None)
        if item_cfg is None:
            raise rr.RoundError('商业情报ID未登记：'+str(iid))
        istate=parse_intel_block(memory_raw)
        if iid not in istate['held']:
            raise rr.RoundError('宿主当前未持有该商业情报：'+str(iid))
        if itarget not in item_cfg['effects']:
            raise rr.RoundError(f'情报 {iid} 不支持作用于目标 {itarget}')
        if itarget!='徐承邺' and itarget not in active_cast:
            raise rr.RoundError('情报作用对象不在本段实际场内：'+str(itarget))
        intel_used={'id':iid,'target':itarget,'evidence':intel_used_raw['evidence'],'item':item_cfg}
    if kind=='item' and (runtime['clock'] is None or clock!=runtime['clock'] or sleep['kind']!='none'):
        raise rr.RoundError('道具系统不推进游戏时间或睡眠')
    if kind!='action' and (value['events'] or value['task'] is not None or value['items'] or intel_used is not None):
        raise rr.RoundError('免费系统操作不可附带额外数值事件、任务、情报消耗或物品奖励')
    if engine._event_tag('HOST_15') in grouped['host_events'] and sleep['kind']!='overnight':
        raise rr.RoundError('整夜恢复事件缺少实际整夜睡眠')
    forbidden={engine._event_tag('HOST_12'),engine._event_tag('HOST_13'),engine._event_tag('HOST_14'),engine._event_tag('HOST_15'),engine._event_tag('HOST_07')}
    grouped['host_events']=[tag for tag in grouped['host_events'] if tag not in forbidden]
    if kind=='action':
        if not isinstance(value['conditions'],dict):
            raise rr.RoundError('普通付费行动的resolution.conditions必须是完整对象，即使只作澄清或未移动；字段为intensity/effective_progress/scene/npc/action_changed/stress_signals/breakout_triggered，无NPC仅npc为null')
        try:rr._round_conditions(value['conditions'],grouped,intimate_mode=intimate_mode)
        except rr.RoundError as exc:raise rr.RoundError('resolution.conditions字段不符：'+str(exc)) from exc
        if value['conditions']['intensity']!=value['category']:
            raise rr.RoundError('有效行动烈度须与本次实际判档一致')
    elif value['conditions'] is not None:
        raise rr.RoundError('免费操作不推进有效行动计数')
    if not isinstance(value['items'],list) or len(value['items'])>8:
        raise rr.RoundError('道具增量须为数组')
    # 前置校验任务与道具，使格式/业务校验错误可由 allow_settlement_retry 自动纠正而非落入 apply_staged 崩溃
    if value['task'] is not None:
        task=value['task'];rr._keys(task,{'title','target','attr','value','tier','item_desc'},'task',{'title','target','attr','value','tier','item_desc'})
        rr._integer(task['value'],'task.value',1)
        for key in ('title','target','attr','tier','item_desc'):
            rr._text(task[key],'task.'+key,300)
            if '|' in task[key]:
                raise rr.RoundError(f'任务字段 task.{key} 不能包含竖线分隔符 |')
        task_baseline_mem = memory_raw
        if isinstance(reservation, dict) and reservation.get('before_memory'):
            try:
                task_baseline_mem = base64.b64decode(reservation['before_memory'], validate=True).decode('utf-8')
            except Exception:
                task_baseline_mem = memory_raw
        task_before=engine._parse_task_block(task_baseline_mem)
        if task_before and task_before.get('current') and task_before['current'].get('status')=='进行中':
            raise rr.RoundError('已有进行中任务，不能覆盖')
        ok_t,err_t=engine._validate_task(task,task_baseline_mem)
        if not ok_t:
            raise rr.RoundError(f'任务生成被拒绝：{err_t}')
    if kind=='action' and any(t.startswith('兑换道具_') for t in grouped['host_events']):
        points_now=engine._read_attr_value(memory_raw,'系统宿主','积分') or 0
        if sum(int(t.split('_')[1]) for t in grouped['host_events'] if t.startswith('兑换道具_'))>points_now:
            raise rr.RoundError('兑换积分不足，未接受道具或扣费')
    items_raw=(files.get(rr.FILES[1]) or b'').decode('utf-8')
    for item in value['items']:
        rr._keys(item,{'entry','evidence'},'item',{'entry','evidence'})
        rr._text(item['evidence'],'item.evidence',500)
        if not _evidence_matches(item['evidence'],texts):raise rr.RoundError('道具变更缺正文依据')
        entry=item['entry'];rr._keys(entry,{'id','name','type','desc','quantity','status','location','target','duration','expire_rule','usage_record','remark','action','system_effect','giftable'},'item.entry',{'name','action'})
        for field,text in entry.items():
            if field=='quantity':rr._integer(text,'item.quantity',1)
            elif field=='giftable':
                if not isinstance(text,(bool,str)):raise rr.RoundError('道具giftable须为布尔或文本')
            elif not isinstance(text,str) or '\n' in text or '\r' in text:raise rr.RoundError('道具字段须为单行文本')
        if entry['action'] not in ('add','consume','update','archive'):raise rr.RoundError('道具动作无效')
        if entry.get('system_effect') and not VALID_SYSTEM_EFFECT_RE.fullmatch(entry['system_effect']):raise rr.RoundError('道具系统效果未登记')
        if entry['action']=='update':
            raise rr.RoundError('当前正式入口不允许任意覆写已有道具字段')
        if entry['action']=='add':
            if entry.get('id'):raise rr.RoundError('新增道具ID由执行器生成，不能覆盖已有编号')
            if engine._find_item_block(items_raw,name=entry['name']):raise rr.RoundError('同名道具增发须保留已有登记字段，当前不自动改写')
        else:
            original=engine._find_item_block(items_raw,item_id=entry.get('id',''))
            if original is None:raise rr.RoundError('道具增量未指向真实活跃ID')
            original_fields=engine._parse_item_block(original['block'])
            original_name=re.search(r'【道具名称】：([^\n]+)',original['block'])[1].strip()
            if entry['name']!=original_name:raise rr.RoundError('道具名称与真实ID不一致')
            if entry['action']=='consume' and entry.get('quantity',1)>engine._int_of(original_fields['数量'],0):raise rr.RoundError('道具消耗量超过库存')
            if entry.get('system_effect') and entry['system_effect']!=original_fields.get('系统效果',''):raise rr.RoundError('不能为已有物品臆造恢复效果')
    if kind=='action' and value['items']:
        additions_pre=sum(item['entry']['action']=='add' for item in value['items'])
        if additions_pre>0:
            purchases_pre=sum(t.startswith('兑换道具_') for t in grouped['host_events'])
            tb_pre=engine._parse_task_block(memory_raw)
            had_pend_pre=bool(tb_pre and (tb_pre.get('pending_items') or tb_pre.get('pending_item')))
            was_act_pre=bool(tb_pre and tb_pre.get('current') and tb_pre['current'].get('status')=='进行中')
            could_pend_pre=had_pend_pre or was_act_pre or (value['task'] is not None)
            if not purchases_pre and not could_pend_pre:
                raise rr.RoundError('新增道具缺已接受兑换或任务待发资格')
            if additions_pre>purchases_pre+int(could_pend_pre):
                raise rr.RoundError('新增道具组数超过实际兑换或任务待发资格')
    raw_ss_pre=files.get(save_store.SAVE_STATE_PATH)
    secrets_pre=()
    if raw_ss_pre:
        try:
            secrets_pre=tuple(((json.loads(raw_ss_pre.decode('utf-8')).get('mechanics') or {}).get('secrets_unlocked')) or ())
        except Exception:
            secrets_pre=()
    director_echo=_sanitize_director_echo(
        value.get('director_echo'),
        load_world_beats(root,optional=True),
        parse_director_block(memory_raw),
        is_action=(kind=='action'),
        secrets_unlocked=secrets_pre,
    )
    tier_costs=active_costs(root,files)
    guard=stamina_guard_info(root,files)
    final_cost=apply_stamina_floor(cost['before'],tier_costs[value['category']],guard) if kind=='action' else 0
    return {'runtime':runtime,'cost':cost,'refund':max(0,cost['total']-final_cost),'net':final_cost,
            'events':grouped,'clock':clock,'elapsed':0 if start is None else end-start,'sleep':sleep,
            'intel_used':intel_used,'director_echo':director_echo,'active_cast':sorted(active_cast),
            'insomnia_targets':sorted(insomnia_targets),'scene_state':scene_state,
            'intimate_mode':intimate_mode,'remote_cast':sorted(remote_cast),
            'stamina_guard':guard,'memory_payload':parsed_memory_payload}


def panel_values(engine,text):
    current=text.split('▶ 上回合历史快照',1)[0]
    result={}
    for name in ('系统宿主','沈知韫','徐念薇','苏婉青','徐承邺'):
        match=re.search(r'^\['+re.escape(name)+r'\]([^\n]+)',current,re.M)
        if not match:continue
        for pair in re.finditer(r'(积分|经验值|体力|魅力|商业嗅觉|好感|堕落|欲望|羞耻|高潮|内射)\s+(-?\d+)',match[1]):result[(name,pair[1])]=int(pair[2])
        preg_m=re.search(r'怀孕\s+(True|False)',match[1])
        if preg_m:result[(name,'怀孕')]=(preg_m[1]=='True')
    return result


def _inject_buff_no_tick(memory_text, target_buffs):
    """Mount item BUFFs onto memory_text without decrementing existing BUFF timers."""
    if not target_buffs or '【当前持久化状态与BUFF】' not in memory_text:
        return memory_text
    parts = re.split(r'(【当前持久化状态与BUFF】[\s\S]*?)(?=\n={10,}|\n▲ 第一层|$)', memory_text, maxsplit=1)
    if len(parts) < 2:
        return memory_text
    block = parts[1]
    for char, buff_str in target_buffs.items():
        if not buff_str:
            continue
        char_pattern = rf'(▶\s*{re.escape(char)}\s*\n)(.*?)(?=\n▶|\n$|\Z)'
        m = re.search(char_pattern, block, re.DOTALL)
        if not m:
            continue
        old_buffs = m.group(2).strip()
        name_m = re.match(r'^\[([^\]]+)\]', str(buff_str).strip())
        bname = name_m.group(1) if name_m else ''
        if '无' in old_buffs or not old_buffs:
            new_buffs = f'  - {buff_str}'
        elif bname and f'[{bname}]' in old_buffs:
            new_buffs = re.sub(rf'-\s*\[{re.escape(bname)}\][^\n]*', f'- {buff_str}', old_buffs, count=1)
        else:
            new_buffs = old_buffs + '\n' + f'  - {buff_str}'
        block = re.sub(char_pattern, rf'\g<1>{new_buffs}\n', block, flags=re.DOTALL)
    parts[1] = block
    return ''.join(parts)


def apply_staged(store,engine,stage,body,files,parsed):
    runtime=copy.deepcopy(parsed['runtime']);value=body['resolution'];kind=parsed['cost']['kind']
    memory_path=stage/rr.FILES[0]
    before=base64.b64decode(body['audit']['reservation']['before_memory'],validate=True).decode()
    content=memory_path.read_text(encoding='utf-8');current=engine._read_attr_value(content,'系统宿主','体力')
    rr._atomic(memory_path,engine._simulate_panel(content,{'系统宿主':{'体力':current+parsed['refund']}}).encode())
    events=parsed['events'];lifecycle=None;states=None;counts=None
    task_completed=False;task_issued=False;completed_task_info=None
    leverage_triggered=None;intel_consumed=None;schedule_moves=[]
    charm_gained_now=False;coy_chars=[]
    active_cast=parsed.get('active_cast') or []
    st_pre,ly_pre,_=save_store.load_bundle(stage)
    prologue_active_pre=bool(ly_pre.get('prologue_active'))
    intl_pre=st_pre.get('intimate') or save_store.default_intimate()
    scene_state=parsed.get('scene_state')
    op_now_all=body.get('operation')
    moved_now=bool(isinstance(op_now_all,dict) and op_now_all.get('code')=='move_player')
    if isinstance(scene_state,dict) and 'present_actors' in scene_state and isinstance(scene_state['present_actors'],list):
        present_actors=[a for a in scene_state['present_actors'] if a in active_cast]
    elif (not moved_now) and intl_pre.get('present_actors'):
        present_actors=[a for a in intl_pre['present_actors'] if a in active_cast]
        if not present_actors and active_cast:
            present_actors=list(active_cast)
    else:
        present_actors=list(active_cast)
    eff_privacy=(
        (scene_state.get('privacy') if isinstance(scene_state,dict) and scene_state.get('privacy') in save_store.PRIVACY_LEVELS else None)
        or ('open_public' if moved_now else intl_pre.get('privacy'))
        or 'open_public'
    )
    # 记录本幕实际发生时的房间级同席知情者（隔离同栋楼未入室角色，防止私密戏泄密）
    scene_known_by=['徐志北',*present_actors] if kind!='item' else ['徐志北']
    prose_joined='\n'.join(str(m.get('text') or '') for m in (body.get('messages') or []) if isinstance(m,dict))
    resolved_body_acts={}
    if kind=='action':
        # 0. 若本轮玩家通过 use_item 启用带 buff: 效果的道具，先预挂 (turns+1) 回合使本轮结算即刻享受缓冲，随后 update_persistent_buffs 统一 -1 落定为满额 turns
        op_now=body.get('operation')
        if isinstance(op_now,dict) and op_now.get('code')=='use_item':
            st_op,_,_=save_store.load_bundle(stage)
            op_item=next((it for it in (st_op.get('items',{}).get('active') or []) if it.get('id')==op_now.get('item_id')),None)
            eff_str=str((op_item or {}).get('system_effect') or '')
            if eff_str.startswith('buff:'):
                bparts=eff_str.split(':',3)
                if len(bparts)==4 and bparts[2].isdigit():
                    bname,bturns,bdesc=bparts[1].strip(),max(1,int(bparts[2])),bparts[3].strip()
                    op_target=str(op_now.get('target') or '').strip()
                    recipients=[op_target] if op_target in save_store.HEROINES else [c for c in present_actors if c in save_store.HEROINES]
                    if recipients:
                        pre_buff_map={who:f'[{bname}] 剩余时效: {bturns + 1}回合 (效果: {bdesc})' for who in recipients}
                        rr._atomic(memory_path,_inject_buff_no_tick(memory_path.read_text(encoding='utf-8'),pre_buff_map).encode('utf-8'))
        # Lifecycle units are accepted paid actions, independently of memory rounds.
        action=runtime['action_index']+1
        pre_mem=memory_path.read_text(encoding='utf-8')
        auto_micro=derive_micro_state_changes(engine,events,value['conditions'],present_actors,pre_mem)
        lifecycle_body={'current_round':action,'memory_deltas':{'round_conditions':value['conditions']},
                        'micro_state_changes':auto_micro,'counter_updates':{},'system_log':'',**copy.deepcopy(events)}
        derived,lifecycle,states,counts=rr._derive_lifecycle(engine,lifecycle_body,pre_mem,active_cast=present_actors)
        events={k:derived[k] for k in events};runtime['action_index']=action
        # 魅力精进(HOST_16)严格防刷冷却：每场景最多触发 1 次（切换地点或跨夜后重置）
        host16_tag=engine._event_tag('HOST_16')
        if host16_tag and host16_tag in events.get('host_events',[]):
            if bool((st_pre.get('mechanics') or {}).get('charm_scene_used')) and not moved_now:
                events['host_events']=[t for t in events['host_events'] if t!=host16_tag]
            else:
                seen_h16=False
                dedup_h=[]
                for t in events['host_events']:
                    if t==host16_tag:
                        if seen_h16: continue
                        seen_h16=True;charm_gained_now=True
                    dedup_h.append(t)
                events['host_events']=dedup_h
        if any(t.startswith('兑换道具_') for t in events['host_events']):
            points=engine._read_attr_value(memory_path.read_text(encoding='utf-8'),'系统宿主','积分')
            if sum(int(t.split('_')[1]) for t in events['host_events'] if t.startswith('兑换道具_'))>points:raise rr.RoundError('兑换积分不足，未接受道具或扣费')
        task_before=engine._parse_task_block(memory_path.read_text(encoding='utf-8'))
        had_pending_item=bool(task_before and (task_before.get('pending_items') or task_before.get('pending_item')))
        was_active_task=bool(task_before and task_before.get('current') and task_before['current'].get('status')=='进行中')
        intel_catalog=load_intel_catalog(store.root,optional=True)
        intel_state=parse_intel_block(memory_path.read_text(encoding='utf-8'))
        intel_dirty=False
        existing_charges=max(0,int(intel_state.get('leverage_charges',0) or 0))
        leverage_armed=intel_state['leverage_armed'] if intel_state['leverage_armed'] in intel_state['held'] else ''
        use_leverage=(existing_charges>0) or (bool(leverage_armed) and (not parsed.get('intel_used') or parsed['intel_used']['id']!=leverage_armed))
        resolved_body_acts=engine.infer_body_acts_from_prose(
            prose_joined, events, explicit_acts=(scene_state or {}).get('body_acts') if isinstance(scene_state,dict) else None,
        )
        # 1. 先结算常规事件（延迟任务结算，待 intel_used 数值生效后统一判任务完成）
        ev_meta=rr._engine_call(
            engine.apply_story_events,events,value['task'],runtime['memory_round'],
            business_leverage=use_leverage,current_day=parsed['clock']['day'],
            active_cast=present_actors,pre_event_content=pre_mem,
            insomnia_targets=parsed.get('insomnia_targets'),defer_task=True,
            privacy=eff_privacy,body_acts=resolved_body_acts,
            action_category=value.get('category'),
        )
        if isinstance(ev_meta,dict) and isinstance(ev_meta.get('normalized_events'),dict):
            events=ev_meta['normalized_events']
        coy_chars = (ev_meta or {}).get('coy_chars') or []
        auto_climax = (ev_meta or {}).get('auto_climax') or []
        if auto_climax and isinstance(states, dict) and isinstance(lifecycle, dict):
            lmicro = lifecycle.setdefault('micro', {})
            for hname in auto_climax:
                if hname in states:
                    states[hname]['residual_tension'] = True
                    lmicro.setdefault(hname, {})['residual_tension'] = {'observed_round': action, 'origin': 'activated'}
        lev_meta=(ev_meta or {}).get('leverage_meta') or {}
        if use_leverage and lev_meta.get('applied'):
            if existing_charges>0:
                rem_charges=max(0,existing_charges-1)
                intel_state['leverage_charges']=rem_charges
                intel_dirty=True
                leverage_triggered={'intel_id':'SHIELD','intel_name':'商业杠杆护盾','targets':lev_meta.get('targets',[]),'remaining_charges':rem_charges}
            else:
                intel_state['held']=[x for x in intel_state['held'] if x!=leverage_armed]
                if leverage_armed not in intel_state['consumed']:
                    intel_state['consumed'].append(leverage_armed)
                intel_state['leverage_armed']=''
                intel_state['leverage_charges']=2
                intel_dirty=True
                iname=next((it['name'] for it in intel_catalog['items'] if it['id']==leverage_armed),leverage_armed)
                leverage_triggered={'intel_id':leverage_armed,'intel_name':iname,'targets':lev_meta.get('targets',[]),'remaining_charges':2}
        su_targeted = (
            (value.get('conditions') or {}).get('npc') == '苏婉青'
            or any(m.get('kind') == 'dialogue' and m.get('speaker') == '苏婉青' for m in body.get('messages', []))
        )
        if '苏婉青' in active_cast and value['category'] in ('A','B') and su_targeted:
            intel_state['su_ab_contacts']+=1
            intel_dirty=True
        # 2. 结算一次性商业情报亮牌（先于任务完成判定，消除任务迟 1 轮完成问题）
        if parsed.get('intel_used'):
            iu=parsed['intel_used'];iid=iu['id'];itarget=iu['target'];icfg=iu['item']
            eff=icfg['effects'][itarget]
            cur_mem=memory_path.read_text(encoding='utf-8')
            st_chk,_,_=save_store.load_bundle(stage)
            su_unlocked=bool((st_chk.get('mechanics') or {}).get('su_affection_85_unlocked'))
            patch={}
            if 'attr' in eff and 'delta' in eff:
                attr=eff['attr'];old_v=engine._read_attr_value(cur_mem,itarget,attr)
                if old_v is not None:
                    cap=(95 if su_unlocked or old_v>85 else 85) if (itarget=='苏婉青' and attr=='好感') else 100
                    new_v=min(cap,max(0,old_v+int(eff['delta'])))
                    patch.setdefault(itarget,{})[attr]=new_v
            if 'host_bonus' in eff:
                host_now=engine._read_host_panel(cur_mem) or {'积分':0,'经验值':0,'体力':100,'商业嗅觉':0}
                for hk,hv in eff['host_bonus'].items():
                    nv=host_now.get(hk,0)+int(hv)
                    if hk=='商业嗅觉': nv=min(100,max(0,nv))
                    host_now[hk]=nv
                patch['系统宿主']=host_now
            if patch:
                rr._atomic(memory_path,engine._simulate_panel(cur_mem,patch).encode('utf-8'))
            intel_state['held']=[x for x in intel_state['held'] if x!=iid]
            if iid not in intel_state['consumed']:
                intel_state['consumed'].append(iid)
            if intel_state['leverage_armed']==iid:
                intel_state['leverage_armed']=''
            intel_dirty=True
            # 亮牌揭穿苏婉青眼线身份（INTEL-002）同步写入本档 secrets_unlocked
            if iid=='INTEL-002':
                st_s,ly_s,_=save_store.load_bundle(stage,sync_txt_drift=True)
                if iid not in st_s['mechanics']['secrets_unlocked']:
                    st_s['mechanics']['secrets_unlocked'].append(iid)
                    save_store.save_bundle(stage,st_s,ly_s)
            intel_consumed={'id':iid,'name':icfg['name'],'target':itarget,'effect_summary':icfg['effect_summary']}
        # 3. 统一结算任务完成与新任务挂载（保留未领 pending_items 队列）
        post_ev_mem=memory_path.read_text(encoding='utf-8')
        task_reward=rr._engine_call(
            engine.process_task_system,value['task'],runtime['memory_round'],str(memory_path),
            sim_content=post_ev_mem,pre_event_content=pre_mem,
        )
        if task_reward:
            tmem=memory_path.read_text(encoding='utf-8')
            thost=engine._read_host_panel(str(memory_path)) or {'积分':0,'经验值':0,'体力':100,'商业嗅觉':0}
            for rk,rv in task_reward.items():
                thost[rk]=thost.get(rk,0)+rv
            rr._atomic(memory_path,engine._simulate_panel(tmem,{'系统宿主':thost}).encode('utf-8'))
        task_after_events=engine._parse_task_block(memory_path.read_text(encoding='utf-8'))
        if (was_active_task and task_after_events and task_after_events.get('current')
                and task_after_events['current'].get('status')=='已完成'):
            task_completed=True
            completed_task_info=copy.deepcopy(task_after_events['current'])
        if (value['task'] is not None and task_after_events and task_after_events.get('current')
                and task_after_events['current'].get('status') in ('进行中','已完成')):
            task_issued=True
            if task_after_events['current'].get('status')=='已完成' and not was_active_task:
                task_completed=True
                completed_task_info=copy.deepcopy(task_after_events['current'])
        rr._engine_call(engine.update_persistent_buffs,str(memory_path),events['shame_events'],{})
        rr._engine_call(engine.process_item_timers,str(memory_path),str(stage/rr.FILES[1]),action)
        memory=rr._write_lifecycle(rr._write_counters(rr._write_micro(memory_path.read_text(encoding='utf-8'),states),counts),lifecycle)
        if intel_dirty:
            memory=write_intel_block(memory,intel_state,intel_catalog)
        rr._atomic(memory_path,memory.encode('utf-8'))
        if value['items']:
            host=events['host_events'];task=engine._parse_task_block(memory)
            additions=sum(item['entry']['action']=='add' for item in value['items'])
            purchases=sum(t.startswith('兑换道具_') for t in host)
            pending_eligible=had_pending_item or bool(task and (task.get('pending_items') or task.get('pending_item')))
            if additions>purchases+int(pending_eligible):raise rr.RoundError('新增道具组数超过实际兑换或任务待发资格')
            for item in value['items']:
                entry=item['entry']
                if entry['action']=='add' and not purchases and not pending_eligible:
                    raise rr.RoundError('新增道具缺已接受兑换或任务待发资格')
                stage_items_text=(stage/rr.FILES[1]).read_text(encoding='utf-8') if (stage/rr.FILES[1]).is_file() else ''
                if entry['action']=='add':
                    if entry.get('id'):raise rr.RoundError('新增道具ID由执行器生成，不能覆盖已有编号')
                    if engine._find_item_block(stage_items_text,name=entry['name']):raise rr.RoundError('同名道具增发须保留已有登记字段，当前不自动改写')
                if entry['action']!='add':
                    original=engine._find_item_block(stage_items_text,item_id=entry.get('id',''))
                    if original is None:raise rr.RoundError('道具增量未指向真实活跃ID')
                    original_fields=engine._parse_item_block(original['block'])
                    original_name=re.search(r'【道具名称】：([^\n]+)',original['block'])[1].strip()
                    if entry['name']!=original_name:raise rr.RoundError('道具名称与真实ID不一致')
                    if entry['action']=='update':raise rr.RoundError('当前正式入口不允许任意覆写已有道具字段')
                    if entry['action']=='consume' and entry.get('quantity',1)>engine._int_of(original_fields['数量'],0):raise rr.RoundError('道具消耗量超过库存')
                    if entry.get('system_effect') and entry['system_effect']!=original_fields.get('系统效果',''):raise rr.RoundError('不能为已有物品臆造恢复效果')
                rr._engine_call(engine.update_item_catalog,runtime['memory_round'],[entry])
            if task and (task.get('pending_items') or task.get('pending_item')) and additions > purchases:
                plist=list(task.get('pending_items') or ([task['pending_item']] if task.get('pending_item') else []))
                if plist: plist.pop(0)
                task['pending_items']=plist
                task['pending_item']=plist[0] if plist else None
                rr._engine_call(engine._write_task_block,task)
        delivered_echo_ids=body.get('audit',{}).get('delivered_echo_ids') or []
        memory_text_now=memory_path.read_text(encoding='utf-8')
        updated_memory_text=consume_echoes(memory_text_now,delivered_echo_ids)
        if task_completed and completed_task_info:
            pts,exp=engine.TASK_REWARDS.get(completed_task_info.get('tier','small'),engine.TASK_REWARDS['small'])
            summary=f"「{completed_task_info['title']}」已达成（积分+{pts}，经验+{exp}；待领奖励：{completed_task_info['item_desc']}）"
            updated_memory_text=append_echo(updated_memory_text,'task_completed',completed_task_info['id'],summary)
        if updated_memory_text!=memory_text_now:
            rr._atomic(memory_path,updated_memory_text.encode('utf-8'))
    if body['operation'] and kind!='item':
        op_clock=_clock_label({'clock':parsed['clock']})
        rr._engine_call(engine.apply_interaction_operation,body['operation'],clock_str=op_clock)
    item_receipt=None
    if kind=='item':
        item_receipt=parsed['cost']['item']
        rr._engine_call(engine.consume_story_recovery_item,item_receipt['item_id'],item_receipt['recovery'],runtime['memory_round'])
        runtime['item_recovered']+=item_receipt['recovery']
    data_before=json.loads((files.get('data.json') or b'{}').decode('utf-8'))
    crossed=parsed['runtime']['clock'] is not None and parsed['clock']['day']>parsed['runtime']['clock']['day']
    weekday=derive_weekday(data_before,memory_path.read_text(encoding='utf-8'),parsed['clock'],save_state=st_pre)
    if kind!='item':
        old_clock=runtime['clock'];new_clock=parsed['clock']
        hours=max(0,(minute(new_clock)-minute(old_clock))//60) if old_clock else 0
        runtime['clock']=new_clock
        cur_presence=engine.parse_presence_from_memory(memory_path.read_text(encoding='utf-8'))
        player_loc_now=cur_presence['徐志北']['location']
        # 4. 先同步离场作息日程，再结算徐承邺监视矩阵（保证 co_present 与发现几率基于最新坐标）
        schedule_moves=reconcile_offstage_presence(
            engine,memory_path,new_clock,weekday,player_loc_now,
            overnight=(parsed['sleep']['kind']=='overnight'),day_crossed=crossed,
            player_moved=bool(body.get('operation') and body['operation'].get('code')=='move_player'),
        )
        if kind=='action' or hours:
            vig_evidences={}
            for ev_item in (value.get('events') or []):
                if isinstance(ev_item,dict) and ev_item.get('group')=='vigilance_events':
                    ev_t=str(ev_item.get('target') or '')
                    ev_s=str(ev_item.get('evidence') or '').strip()
                    if ev_t and ev_s:
                        vig_evidences[ev_t]=(vig_evidences.get(ev_t,'')+' '+ev_s).strip()
            scene_prose_all=' '.join(str(m.get('text') or '') for m in (body.get('messages') or []) if isinstance(m,dict))
            st_vig_now,_,_=save_store.load_bundle(stage,sync_txt_drift=True)
            intl_vig=st_vig_now.get('intimate') or {}
            host_biz_now=int(((st_vig_now.get('panels') or {}).get('系统宿主') or {}).get('商业嗅觉',0) or 0)
            rr._engine_call(
                engine.process_vigilance_system,
                events['vigilance_events'],
                events['shame_events'],
                str(memory_path),
                elapsed_hours=hours,
                roll_home=kind=='action',
                active_cast=active_cast,
                ds_events=events.get('ds_events'),
                event_evidences=vig_evidences,
                scene_prose=scene_prose_all,
                scene_privacy=str(intl_vig.get('privacy') or ''),
                traces=intl_vig.get('traces') or {},
                intel_state=st_vig_now.get('intel') or {},
                su_stats=(st_vig_now.get('panels') or {}).get('苏婉青') or {},
                enforce_channel_gate=True,
                host_biz=host_biz_now,
                leverage_active=bool(leverage_triggered),
            )
        if kind=='action':
            dir_mem=memory_path.read_text(encoding='utf-8')
            dir_updated=advance_director_state(
                store.root,dir_mem,location=player_loc_now,
                director_roll=body.get('audit',{}).get('director_roll'),
                effective_progress=bool((value.get('conditions') or {}).get('effective_progress')),
                had_events=bool(any(events[g] for g in events)),
                memory_fact=(value.get('memory') or {}).get('fact',''),
                director_echo=parsed.get('director_echo'),
                active_cast=active_cast,
                new_clock=new_clock,
                day_crossed=crossed,
            )
            if dir_updated!=dir_mem:
                rr._atomic(memory_path,dir_updated.encode('utf-8'))
    if crossed or parsed['sleep']['kind']=='overnight':
        st_day,ly_day,_=save_store.load_bundle(stage,sync_txt_drift=True)
        cur_day_num=int((parsed.get('clock') or {}).get('day') or 1)
        lat_map=st_day['mechanics'].setdefault('pregnancy_latent_until',{h:0 for h in save_store.HEROINES})
        day_dirty=False
        for hname in save_store.HEROINES:
            due_day=int(lat_map.get(hname,0) or 0)
            if due_day>0 and cur_day_num>=due_day:
                was_preg=bool(st_day['panels'][hname].get('怀孕'))
                st_day['panels'][hname]['怀孕']=True
                if not was_preg:
                    cur_shame=int(st_day['panels'][hname].get('羞耻',100))
                    st_day['panels'][hname]['羞耻']=min(35,max(0,cur_shame-30))
                lat_map[hname]=0
                day_dirty=True
        if day_dirty:
            save_store.save_bundle(stage,st_day,ly_day)
    if parsed['sleep']['kind']=='overnight':
        # 跨夜安稳睡眠：宿主恢复 100；体液锁定跨夜衰减6回合；高欲求/空耗女主触发夜间暗中自渎纾解；未失眠女主恢复体力(孕期上限88)、残余高潮清零、堕落<30且欲望<15时羞耻防线微幅回弹+1，并即时夹紧羞耻上限
        st_ov,ly_ov,_=save_store.load_bundle(stage,sync_txt_drift=True)
        ins_map=st_ov['mechanics'].get('insomnia_applied') or {}
        unlocked_caps=st_ov['mechanics'].setdefault('depravity_unlocked_caps',{h:30 for h in save_store.HEROINES})
        m_trace=st_ov['mechanics'].setdefault('masturbation_trace',{h:0 for h in save_store.HEROINES})
        ov_patch={'系统宿主':{'体力':100}}
        for hname in save_store.HEROINES:
            ov_patch[hname]={'高潮':0}
            cur_h_sta=int(st_ov['panels'][hname]['体力'])
            cur_h_shame=int(st_ov['panels'][hname].get('羞耻',100))
            cur_h_dep=int(st_ov['panels'][hname].get('堕落',0))
            cur_h_des=int(st_ov['panels'][hname].get('欲望',0))
            cur_h_pas=int(st_ov['panels'][hname].get('被动',0))
            cur_h_cp=int(st_ov['panels'][hname].get('内射',0))
            is_h_preg=bool(st_ov['panels'][hname].get('怀孕'))
            # 1. 跨夜衰减 [持续_体液锁定] 6 回合
            rem_lock_turns=0
            next_buffs=[]
            for bitem in (st_ov.get('buffs',{}).get(hname) or []):
                if isinstance(bitem, dict) and bitem.get('name')=='持续_体液锁定':
                    old_rem=int(bitem.get('turns') or 0)
                    new_rem=max(0,old_rem-6)
                    if new_rem>0:
                        rem_lock_turns=new_rem
                        fl_floor=engine.fluid_lock_floor_for_turns(new_rem,creampie_count=cur_h_cp)
                        next_buffs.append({
                            'name':'持续_体液锁定',
                            'turns':new_rem,
                            'effect':f'效果: 体内精液残留与激素共振，欲望锁底>={fl_floor}',
                        })
                elif isinstance(bitem, str) and '[持续_体液锁定]' in bitem:
                    m_rem=re.search(r'剩余时效:\s*(\d+)回合',bitem)
                    old_rem=int(m_rem.group(1)) if m_rem else 0
                    new_rem=max(0,old_rem-6)
                    if new_rem>0:
                        rem_lock_turns=new_rem
                        fl_floor=engine.fluid_lock_floor_for_turns(new_rem,creampie_count=cur_h_cp)
                        next_buffs.append({
                            'name':'持续_体液锁定',
                            'turns':new_rem,
                            'effect':f'效果: 体内精液残留与激素共振，欲望锁底>={fl_floor}',
                        })
                else:
                    next_buffs.append(bitem)
            st_ov.setdefault('buffs',{})[hname]=next_buffs
            lock_floor=engine.fluid_lock_floor_for_turns(rem_lock_turns,creampie_count=cur_h_cp)
            # 2. 夜间私密自渎自动纾解判定
            unrel_key=f'空耗_连续未纾解_{hname}'
            cur_unrel=int(st_ov.get('counters',{}).get(unrel_key,0))
            secret_relief=bool((cur_h_des>=75 or rem_lock_turns>0) and (cur_h_dep>=15 or cur_unrel>=1))
            if secret_relief:
                ov_patch[hname]['欲望']=max(45,lock_floor)
                cap_val=int(unlocked_caps.get(hname,30))
                if cur_h_dep<cap_val:
                    cur_h_dep=min(cap_val,cur_h_dep+2)
                    ov_patch[hname]['堕落']=cur_h_dep
                st_ov.setdefault('counters',{})[unrel_key]=0
                m_trace[hname]=2
            elif rem_lock_turns>0 and cur_h_des<lock_floor:
                ov_patch[hname]['欲望']=lock_floor
            dep_coef=0.7 if cur_h_pas>=4 else 0.6
            shame_cap=min(35 if is_h_preg else 100,max(0,100-int(cur_h_dep*dep_coef)))
            if not ins_map.get(hname,False):
                sta_gain=32 if secret_relief else 40
                sta_cap=88 if is_h_preg else 100
                ov_patch[hname]['体力']=min(sta_cap,cur_h_sta+sta_gain) if cur_h_sta<sta_cap else cur_h_sta
                if cur_h_dep<30 and not secret_relief and cur_h_des<15:
                    ov_patch[hname]['羞耻']=min(shame_cap,cur_h_shame+1)
            # 堕落抬升或孕期后确保羞耻立即夹紧至 shame_cap
            if '羞耻' not in ov_patch[hname] and cur_h_shame>shame_cap:
                ov_patch[hname]['羞耻']=shame_cap
            st_ov['mechanics']['insomnia_applied'][hname]=False
        for ch,ch_vals in ov_patch.items():
            for ak,av in ch_vals.items():
                st_ov['panels'][ch][ak]=av
        save_store.save_bundle(stage,st_ov,ly_ov)
        runtime['item_recovered']=0
    final=engine._read_attr_value(memory_path.read_text(encoding='utf-8'),'系统宿主','体力')
    guard_pre=parsed.get('stamina_guard') if isinstance(parsed.get('stamina_guard'),dict) else stamina_guard_info(store.root,files)
    low=(final<5 and not (guard_pre.get('active') and final>=5)) or parsed['sleep']['kind']=='collapse'
    was_resting=runtime['phase']=='resting'
    closed=False
    if not was_resting and (crossed or low):
        runtime['last_closed']=runtime['memory_round'];runtime['memory_round']+=1;runtime['closed_by']=body['request_id'];closed=True
    if kind=='rest' or low:
        if not closed and not was_resting and kind=='rest':
            runtime['last_closed']=runtime['memory_round'];runtime['memory_round']+=1;runtime['closed_by']=body['request_id'];closed=True
        runtime['phase']='ready' if parsed['sleep']['kind']=='overnight' and final>=5 else 'resting'
    else:runtime['phase']='ready'
    # 最终统一同步 P3 纯 JSON 真相（save_state.json + memory_store.json）与单向可读视图
    st_final,ms_final,_=save_store.load_bundle(stage,sync_txt_drift=True)
    st_final['runtime'].update({
        'clock':copy.deepcopy(runtime['clock']),
        'weekday':weekday,
        'memory_round':runtime['memory_round'],
        'last_closed':runtime['last_closed'],
        'phase':runtime['phase'],
        'item_recovered':runtime['item_recovered'],
        'action_index':runtime['action_index'],
        'closed_by':runtime['closed_by'],
    })
    intimate_meta={'stealth_alert':False,'high_risk_devices':[]}
    if kind!='item':
        res_cfg=(config(store.root).get('resource') or {})
        intimate_meta=engine.advance_intimate_state(
            st_final,
            events,
            scene_state=scene_state,
            active_cast=present_actors,
            building_cast=active_cast,
            sleep_kind=parsed['sleep']['kind'],
            location_changed=moved_now,
            category=value.get('category','A'),
            prose_text=prose_joined,
            clock_str=_clock_label({'clock':parsed['clock']}),
            location=player_loc_now,
            elapsed_hours=hours,
            operation=op_now_all,
            vigor_costs=res_cfg.get('vigor_costs'),
            body_acts=resolved_body_acts,
            charm_gained_this_turn=charm_gained_now,
        )
        if parsed['sleep']['kind']=='overnight' or moved_now:
            st_final.setdefault('mechanics',{})['charm_scene_used']=False
        elif charm_gained_now:
            st_final.setdefault('mechanics',{})['charm_scene_used']=True
    shop_added=[]
    shop_rejected=[]
    if kind=='action' and isinstance(scene_state,dict) and scene_state.get('shop_adds'):
        shop_q=detect_shop_custom_request(str(body.get('input') or body.get('action') or ''))
        if shop_q:
            sa_res=apply_scene_shop_adds(st_final,store.root,scene_state['shop_adds'],query=shop_q)
            shop_added=[{
                'id':it['id'],'name':it['name'],'price':it['price'],'category':it['category'],
                'grade':it.get('grade','T1'),'grade_label':it.get('grade_label','T1 寻常'),
            } for it in sa_res['added']]
            shop_rejected=list(sa_res['rejected'])
    before_values=panel_values(engine,before)
    if kind!='item':
        aff_deltas={
            h: int((st_final.get('panels',{}).get(h) or {}).get('好感',0)) - int(before_values.get((h,'好感'), (st_final.get('panels',{}).get(h) or {}).get('好感',0)))
            for h in save_store.HEROINES
            if h in (st_final.get('panels') or {})
        }
        de_obj=parsed.get('director_echo') if isinstance(parsed.get('director_echo'),dict) else {}
        advance_npc_mind(
            st_final,
            mind_updates=de_obj.get('mind_updates') if kind=='action' else None,
            active_cast=present_actors if kind=='action' else active_cast,
            overnight=(parsed['sleep']['kind']=='overnight'),
            day_crossed=crossed,
            aff_deltas=aff_deltas,
            events=events if kind=='action' else None,
            coy_chars=coy_chars,
            action_category=value.get('category','A') if kind=='action' else '',
            pre_values=before_values,
            engine=engine,
        )
        # 纯 JSON 三轨结构化记忆落盘（携带后端权威房间级 scene_known_by 与 K01 硬守卫）
        mem_payload=parsed.get('memory_payload') or {'fact':str((value.get('memory') or {}).get('fact') or ''),'anchor_ops':[],'chronicle_digest':None,'tags':[]}
        cur_sub_loc=str(((st_final.get('intimate') or {}).get('sub_location')) or '')
        cur_secrets=tuple(((st_final.get('mechanics') or {}).get('secrets_unlocked')) or ())
        ms_final=save_store.record_memory_turn(
            ms_final,
            fact=mem_payload.get('fact',''),
            anchor_ops=mem_payload.get('anchor_ops'),
            chronicle_digest=mem_payload.get('chronicle_digest'),
            day=int((parsed.get('clock') or {}).get('day') or 1),
            time_str=str((parsed.get('clock') or {}).get('time') or ''),
            location=player_loc_now,
            sub_location=cur_sub_loc,
            known_by=scene_known_by,
            entities=scene_known_by,
            tags=mem_payload.get('tags'),
            day_crossed=crossed,
            overnight=(parsed['sleep']['kind']=='overnight'),
            secrets_unlocked=cur_secrets,
        )
    save_store.save_bundle(stage,st_final,ms_final)
    after_memory=memory_path.read_text(encoding='utf-8');after_values=panel_values(engine,after_memory)
    changes=[{'target':name,'attribute':attr,'before':old,'after':after_values[key],
              'delta':(1 if after_values[key] else -1) if isinstance(old,bool) else after_values[key]-old}
             for key,old in before_values.items() for name,attr in (key,) if key in after_values and after_values[key]!=old]
    receipt={'request_id':body['request_id'],'kind':kind,'reserved':parsed['cost']['total'],'refunded':parsed['refund'],
             'items_changed':(files[rr.FILES[1]] or b'')!=(stage/rr.FILES[1]).read_bytes(),
             'task_after':engine._parse_task_block(after_memory),
             'task_completed':task_completed,'task_issued':task_issued,
             'net_cost':parsed['net'],'stamina_before':parsed['cost']['before'],'stamina_after':final,'changes':changes,
             'events':events,'item':item_receipt,'clock':runtime['clock'],'weekday':weekday,
             'schedule_moves':schedule_moves,'leverage_triggered':leverage_triggered,'intel_consumed':intel_consumed,
             'memory_round':runtime['memory_round'],
             'closed_round':runtime['last_closed'] if closed else None,'phase':runtime['phase'],'item_budget':20-runtime['item_recovered'],
             'sleep_completed':parsed['sleep']['kind']=='overnight','_scene_known_by':scene_known_by,
             'intimate_meta':intimate_meta,'shop_added':shop_added,'shop_rejected':shop_rejected}
    return runtime,receipt


def category_policy(kind, option_id=None, *, intimate_mode=False):
    if kind != 'action':
        return {'mode':'system', 'required_category':'SYSTEM',
                'instruction':'本次为免费系统过渡，resolution.category只能为SYSTEM。'}
    if option_id in COSTS:
        extra = ' 当前处于亲密进行态：固定B档允许依据正文实际触碰记录 C烈度_轻度 或 C烈度_中度（深度/重度仍须走C档），A档仍禁C烈度_*。' if intimate_mode else ''
        return {'mode':'fixed_option', 'required_category':option_id,
                'instruction':f'本次玩家已选固定{option_id}选项，resolution.category必须原样返回{option_id}，不能按正文重新判档或降价。按已授权原行动生成，不因档位提高接触、情绪或剧情烈度，不保证成功。conditions.intensity按现有契约与category一致，不据此虚构事件。{extra}'}
    return {'mode':'custom', 'required_category':None,
            'instruction':'本次为自定义行动，resolution.category按实际成立行为判A/B/C并给出依据，不得使用SYSTEM；费用由程序计算。'}


def resolution_policy(kind, option_id=None, *, intimate_mode=False):
    return {'kind':kind,'conditions_required':kind=='action','intimate_mode':bool(intimate_mode),
            'category_policy':category_policy(kind, option_id, intimate_mode=intimate_mode),
            'conditions_fields':['intensity','effective_progress','scene','npc','action_changed','stress_signals','breakout_triggered'],
            'instruction':'普通付费行动必须提交七字段conditions对象；澄清/未移动也填，按事实用false，不改字段名；无NPC仅npc为空。免费SYSTEM的conditions为空。'}


def contract(root=None,kind='action',option_id=None,*,intimate_mode=False):
    limits=memory_policy(root) if root is not None else MEMORY_DEFAULTS
    category = category_policy(kind, option_id, intimate_mode=intimate_mode)
    return {'category':category['required_category'] or 'A|B|C','basis':category['instruction'],
            'clock':{'day':1,'time':'HH:MM','basis':'实际经过的行为与时间依据，首次从剧情初始化'},
            'events':[{'group':'登记事件组','target':'本场对象或系统宿主','tags':['登记原标签'],'evidence':'本段原文子串'}],
            'memory':{'fact':f"无长期新增价值时空串；否则<={limits['fact_chars']}字符单行，仅记新因果/承诺/变化",
                      'anchor_ops':[],
                      'chronicle_digest':''},
            'conditions':{'intensity':'A|B|C','effective_progress':True,'scene':'现场地点','npc':None,'action_changed':True,'stress_signals':0,'breakout_triggered':[]} if kind=='action' else None,
            'sleep':{'kind':'none|collapse|interrupted|overnight','start':None,'evidence':''},'task':None,'items':[]}


def _is_v2_bridge_active(tasks):
    """Return True when a recent v2.x bridge plugin heartbeat is recorded, enabling lazy live.txt skipping."""
    mon = (tasks or {}).get('bridge_monitor')
    if not isinstance(mon, dict):
        return False
    ver = str(mon.get('plugin_version') or '').strip()
    if not ver.startswith('2.'):
        return False
    rec_at = mon.get('received_at')
    if not isinstance(rec_at, (int, float)):
        return False
    return (time.time() - float(rec_at)) < 600


def create(service,body,retry_key=None,resume_stage2=False):
    service.start()
    rr._keys(body,{'request_id','base_revision','action','model_key','entry_mode','operation','save_epoch','selection'},'提交',{'request_id','base_revision','action','entry_mode','save_epoch','selection'})
    key=body['request_id'];action=body['action'];revision=body['base_revision']
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',key):raise rr.RoundError('请求编号无效')
    rr._text(action,'action',2000)
    model_key=service._model_key(body);selected=body['selection'];command=body.get('operation')
    import interaction_runtime as ir
    lazy_live_txt = False
    with service.store._locked():
        tasks=service._read();service._expire(tasks)
        lazy_live_txt = bool(getattr(service, '_v2_lazy_packet', False) or _is_v2_bridge_active(tasks))
        existing=tasks['jobs'].get(key)
        if existing and retry_key is None:
            if any(existing.get(k)!=body.get(k) for k in ('base_revision','action','entry_mode','save_epoch','selection','operation','model_key')):
                raise rr.ConflictError('同编号不得改动原选择')
            return {'task':service._public(existing)}
        if any(j['status'] in {'preparing','queued','generating','validating','awaiting_review','refund_pending'} for j in tasks['jobs'].values()):raise rr.ConflictError('已有行动正在处理或等待退款恢复')
        files=service.store._files()
        if service._save_epoch()!=body['save_epoch'] or rr._revision(files)!=revision:raise rr.ConflictError('存档或选择已更新，请恢复当前段落')
        ir.selection(service.root,files,selected,action,command)
        cost=quote(service.root,files,selected,action,command)
        if cost['kind']=='item':command={'code':'use_recovery_item','item_id':cost['item']['item_id']}
        if command:ir.operation(service.root,files,command,action,True)
        use_stage2_resume = bool(retry_key is not None and resume_stage2 and cost['kind'] != 'item')
        if use_stage2_resume:
            if ir.load_stage1_checkpoint(service, key, existing) is None:
                raise rr.RoundError('未找到可复用的前台剧情断点，请使用完整重推')
        else:
            ir.clear_stage1_checkpoint(service, key)
        previous_error=(existing or {}).get('error','') if retry_key is not None else ''
        job={**(existing or {}),'request_id':key,'base_revision':revision,'action':action,'entry_mode':ir.MODE,
             'model_key':model_key,'operation':body.get('operation'),'save_epoch':body['save_epoch'],'selection':selected,
             'current_round':state(service.root,files)['memory_round'],'status':'preparing','attempt':(existing or {}).get('attempt',0),
             'created_at':__import__('time').time(),'error':'','lease':None,'cost_preview':cost,
             'resume_stage2':use_stage2_resume,'has_stage1_checkpoint':use_stage2_resume}
        job.pop('refund',None);job.pop('receipt',None);job.pop('generation_model',None);job.pop('review',None)
        service._blob(key,'.assembled.json').unlink(missing_ok=True)
        reserve(service,tasks,job,files,cost)
    try:
        prepared={'base_revision':job['working_revision'],'current_round':job['current_round'],
                  'snapshot':{n:data.decode() if data is not None else None for n,data in held_files(service,job).items()}}
        if cost['kind']=='item':
            context={'protocol':3,'interaction_protocol':3,'entry_mode':ir.MODE,'audit':{n:rr._digest(service.store._path(n).read_bytes()) for n in ('story_progression.py','injection_core.py','txt文件/互动运行配置.json','txt文件/事件注册表.json')},'system_item':True,'command':command,'selection':selected}
        else:
            context=ir.packet(service,prepared,key,action,command,previous_error=previous_error,selected=selected,reservation=job['reservation'],lazy_live_txt=lazy_live_txt)
        with service.store._locked():
            tasks=service._read();current=tasks['jobs'][key]
            if current['status']!='preparing' or current['reservation']!=job['reservation']:raise rr.ConflictError('任务已取消')
            rr._atomic(service._blob(key,'.context.json'),rr._json(context))
            if cost['kind']=='item':
                runtime=state(service.root,service.store._files())
                clock=runtime['clock'] or {'day':1,'time':'12:00'}
                text='使用'+cost['item']['name']+'后，体力恢复了'+str(cost['item']['recovery'])+'点。'
                row=ir.segment(service.root,service.store._files())
                decision=copy.deepcopy(row['decision'])
                result={'messages':[{'kind':'narration','speaker':'','text':text}],'decision':decision,'operation':command,'handoff':'',
                        'checks':{'intent':'玩家只使用已登记恢复道具。','knowledge':'恢复信息仅供玩家。','action':'使用明确ID的实际道具。','pace':'系统恢复结束，仍由玩家选择下一步。'},
                        'resolution':{'category':'SYSTEM','basis':'纯道具系统操作','clock':{**clock,'basis':'纯道具使用不推进剧情时间'},
                                      'events':[],'memory':{'fact':'','transfers':{}},'conditions':None,'sleep':{'kind':'none','start':None,'evidence':''},'task':None,'items':[]}}
                audit={'required_reads_verified':True,'origin':'player_action','reservation':current['reservation'],'checks':result['checks']}
                payload={'schema_version':3,'entry_mode':ir.MODE,'request_id':key,'base_revision':current['working_revision'],'input':action,
                         'selection':selected,'audit':audit,**{k:result[k] for k in ('messages','decision','operation','handoff','resolution')}}
                rr._atomic(service._blob(key,'.assembled.json'),rr._json(payload))
                current.update(status='validating')
            else:current.update(status='queued')
            commit_tasks(service.store,service.store._files(),tasks)
        return finish(service,key) if cost['kind']=='item' else {'task':service._public(current)}
    except (ValueError,OSError):
        with service.store._locked():
            tasks=service._read();current=tasks['jobs'][key]
            if current['status'] in ('preparing','queued','validating'):refund(service,tasks,current,'failed','准备或系统结算未完成，已返还预扣。')
        raise


def held_files(service,job):
    with service.store._locked():
        files=service.store._files()
        if rr._revision(files)!=job['working_revision']:raise rr.ConflictError('预扣后存档被外部修改')
        return files


def retry(service,key,body):
    body = body if isinstance(body, dict) else {}
    with service.store._locked():
        tasks=service._read();service._expire(tasks);job=tasks['jobs'].get(key)
        if not job:raise rr.RoundError('任务不存在')
        if job['status'] in ('queued','generating','validating','committed','preparing'):return {'task':service._public(job)}
        if job.get('reservation',{}).get('status')=='held':refund(service,tasks,job,'failed','重试前返还原预扣')
        request={k:job.get(k) for k in ('request_id','base_revision','action','entry_mode','operation','save_epoch','selection','model_key')}
        request['model_key']=service._model_key(body)
        wants_resume = bool(body.get('resume_stage2'))
    return create(service,request,retry_key=key,resume_stage2=wants_resume)


def finish(service,key):
    with service.store._locked():
        job=copy.deepcopy(service._read()['jobs'][key])
    if job['status']!='validating':return {'task':service._public(job)}
    try:
        context=rr.load_request(service._blob(key,'.context.json').read_text(encoding='utf-8'))
        payload=rr.load_request(service._blob(key,'.assembled.json').read_text(encoding='utf-8')) if context.get('system_item') else service._assemble_result(key,job)
        baseline=dict(context.get('audit',{}))
        if not context.get('system_item'):
            proof=rr.load_request(service._blob(key,'.read-audit.json').read_text(encoding='utf-8'))
            baseline.update({item['path']:item['source_sha256_at_result'] for item in proof['verified_tools'] if 'source_sha256_at_result' in item})
        receipt=service.store.submit(payload,_source_baseline=baseline)
        with service.store._locked():return {'task':service._public(service._read()['jobs'][key])}
    except rr.RoundError as error:
        with service.store._locked():
            tasks=service._read();current=tasks['jobs'][key]
            if current['status']=='validating':refund(service,tasks,current,'conflict' if isinstance(error,rr.ConflictError) else 'failed','结算未通过：'+str(error))
            return {'task':service._public(current)}


def cancel(service,key):
    service.start()
    import interaction_runtime as ir
    with service.store._locked():
        tasks=service._read();job=tasks['jobs'].get(key)
        if not job:raise rr.RoundError('任务不存在')
        ir.clear_stage1_checkpoint(service, key)
        job['has_stage1_checkpoint'] = False
        job['resume_stage2'] = False
        job.pop('review', None)
        job.pop('drift_retry_guidance', None)
        if job.get('status')=='refund_pending':
            res=job.get('reservation')
            if isinstance(res,dict): res['status']='abandoned'
            job.update(status='cancelled',lease=None,error='已强制解除退款待恢复锁死（未覆盖外部存档改动）。')
            service._write(tasks)
        elif job.get('reservation'):
            refund(service,tasks,job,'cancelled','已取消，预扣全额返还。')
        elif job['status']!='committed':
            job.update(status='cancelled',lease=None,error='已取消原请求。');service._write(tasks)
        return {'task':service._public(job)}


def _clock_label(runtime):
    clock=(runtime or {}).get('clock')
    if isinstance(clock,dict) and clock.get('day') and clock.get('time'):
        return f"第{clock['day']}天 {clock['time']}"
    return '当前'


def _guard_deterministic_tx(service,body,required_keys,op_label):
    service.start()
    rr._keys(body,required_keys,op_label,required_keys)
    key=body['request_id']
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',key):
        raise rr.RoundError('请求编号无效')
    payload_hash=rr._digest(rr._json({k:v for k,v in body.items() if k!='request_id'}))
    ledger=service.store._ledger()
    previous=ledger['receipts'].get(key)
    if previous is not None:
        if previous['payload_hash']!=payload_hash:
            raise rr.ConflictError('request_id已用于不同内容，请勿复用')
        return {'replayed':True,'receipt':dict(previous['receipt'],replayed=True)}
    if body['save_epoch']!=service._save_epoch():
        raise rr.ConflictError('存档已切换，请刷新后再试')
    tasks=service._read();service._expire(tasks)
    if any(j['status'] in ACTIVE_JOB_STATUSES for j in tasks['jobs'].values()):
        raise rr.ConflictError('当前有剧情行动正在处理，请待本段结算完成后再操作')
    files=service.store._files()
    if rr._revision(files)!=body['base_revision']:
        raise rr.ConflictError('存档或积分已更新，请刷新后重试')
    import interaction_runtime as ir
    row=ir.segment(service.root,files)
    prog=ir.playback(service.root,row)
    if row is not None and not prog['completed']:
        raise rr.ConflictError('请先演播完本段剧情后再操作')
    return {'replayed':False,'key':key,'payload_hash':payload_hash,'ledger':ledger,'files':files}


def _publish_deterministic_stage(service,guard,stage,extra_receipt):
    files=guard['files'];ledger=guard['ledger'];key=guard['key']
    sequence=ledger['sequence']+1
    after={name:(stage/name).read_bytes() if (stage/name).is_file() else None for name in rr.FILES}
    data=json.loads(after['data.json'] or b'{}')
    data['state_version']=sequence
    after['data.json']=rr._json(data)
    # 原子同步 P3 save_state.json + memory_store.json + 单向渲染视图
    st_obj,ly_obj,_=save_store.load_bundle(stage,after,sync_txt_drift=True)
    st_obj['runtime']['last_sequence']=max(int(st_obj['runtime'].get('last_sequence') or 0),sequence)
    after.update(save_store.render_bundle_bytes(st_obj,ly_obj,data_dict=data))
    revision=rr._revision(after)
    receipt={'request_id':key,'revision':revision,'state_version':sequence,'status':'committed','replayed':False,**extra_receipt}
    ledger['sequence']=sequence
    ledger['receipts'][key]={'payload_hash':guard['payload_hash'],'receipt':receipt}
    if len(ledger['receipts']) > rr.MAX_LEDGER_RECEIPTS:
        ordered_ids = sorted(
            ledger['receipts'].keys(),
            key=lambda rid: (int(((ledger['receipts'][rid].get('receipt') or {}).get('state_version')) or 0), rid),
        )
        for stale_id in ordered_ids[:-rr.MAX_LEDGER_RECEIPTS]:
            ledger['receipts'].pop(stale_id, None)
    after[rr.META]=rr._json(ledger)
    current_disk=service.store._files()
    if any(current_disk[name]!=files[name] for name in rr.FILES):
        raise rr.ConflictError('提交期间存档被其他工具改动，未写入')
    service.store._commit_files(after)
    return receipt


def redeem_shop_item(service,body):
    """Deterministic zero-stamina, zero-LLM shop redemption via single RoundStore WAL transaction."""
    with service.store._locked():
        guard=_guard_deterministic_tx(service,body,{'request_id','base_revision','save_epoch','item_id'},'商城兑换')
        if guard['replayed']:
            return {'status':'committed','receipt':guard['receipt'],'replayed':True}
        item_id=body['item_id']
        if not isinstance(item_id,str) or not re.fullmatch(r'(?:SHOP|DYN)-\d+',item_id):
            raise rr.RoundError('商城商品ID无效')
        catalog=load_shop_catalog(service.root,optional=False)
        files=guard['files']
        st_cur,_,_=save_store.load_bundle(service.root,files)
        dyn_items=list((st_cur.get('shop') or {}).get('dynamic_catalog') or [])
        all_products=[*catalog['items'],*dyn_items]
        product=next((x for x in all_products if x.get('id')==item_id),None)
        if product is None:
            raise rr.RoundError('系统商城中未找到该商品：'+item_id)
        stage=Path(tempfile.mkdtemp(prefix='work-',dir=service.store.runtime))
        try:
            for name,raw in files.items():
                if raw is not None:
                    rr._atomic(stage/name,raw)
            engine=rr._engine(service.root,stage)
            memory_path=stage/rr.FILES[0]
            memory=memory_path.read_text(encoding='utf-8')
            um=read_shop_unlock_metrics_full(engine,memory)
            unlock_chk=evaluate_unlock_req(
                product.get('unlock_req'),um['host_biz'],um['heroine_affs'],
                max_depravity=um['max_depravity'],host_charm=um['host_charm'],
            )
            if not unlock_chk['unlocked']:
                raise rr.RoundError(unlock_chk['reason'])
            shop_state=parse_shop_echo_block(memory)
            bought=shop_state['redeemed'].get(product['id'],0)
            if product.get('max_per_save') is not None and bought>=product['max_per_save']:
                raise rr.RoundError(f"「{product['name']}」已达本档限购上限（{product['max_per_save']}次）")
            points=engine._read_attr_value(memory,'系统宿主','积分')
            if points is None:
                raise rr.RoundError('正式存档缺少宿主积分字段')
            host_charm=engine._read_attr_value(memory,'系统宿主','魅力')
            charm_info=engine.charm_tier_info(70 if host_charm is None else host_charm)
            charm_disc=float(charm_info.get('shop_discount',1.0))
            base_price=int(product['price'])
            eff_price=max(1,int(round(base_price*charm_disc))) if charm_disc<1.0 else base_price
            if points<eff_price:
                raise rr.RoundError(f"当前积分不足（需要 {eff_price}，现有 {points}）")
            points_after=points-eff_price
            memory=engine._simulate_panel(memory,{'系统宿主':{'积分':points_after}})
            rr._atomic(memory_path,memory.encode('utf-8'))
            runtime=state(service.root,files) if enabled(service.root) else {'memory_round':1,'clock':None}
            memory_round=max(1,int(runtime.get('memory_round') or 1))
            clock_str=_clock_label(runtime)
            pack_qty=max(1,int(product.get('pack_qty') or 1))
            usage_mode=save_store.infer_usage_mode(product.get('system_effect',''),bool(product.get('giftable',True)),product.get('usage_mode',''))
            location='无' if ('临时性' in product['type'] and usage_mode=='consumable_host') else '随身'
            disc_note=f"（魅力折扣 {int(round(charm_disc*100))}%）" if charm_disc<1.0 else ""
            entry={
                'name':product['name'],
                'type':product['type'],
                'category':product.get('category','daily'),
                'usage_mode':usage_mode,
                'desc':product['desc'],
                'quantity':pack_qty,
                'status':'仓库中',
                'location':location,
                'target':'未使用',
                'duration':product.get('duration','无'),
                'expire_rule':product.get('expire_rule','无'),
                'usage_record':f'{clock_str} - 系统商城兑换入囊（×{pack_qty}）' if pack_qty>1 else f'{clock_str} - 系统商城兑换入囊',
                'remark':f"系统商城兑换（{product['id']}）· 消耗{eff_price}积分{disc_note} · {clock_str}",
                'system_effect':product.get('system_effect',''),
                'giftable':bool(product.get('giftable',False)),
                'action':'add',
            }
            rr._engine_call(engine.update_item_catalog,memory_round,[entry])
            catalog_text=(stage/rr.FILES[1]).read_text(encoding='utf-8')
            found=engine._find_item_block(catalog_text,name=product['name'])
            catalog_item_id=engine._parse_item_block(found['block']).get('道具ID','ITEM-001') if found else 'ITEM-001'
            memory=memory_path.read_text(encoding='utf-8')
            shop_state=parse_shop_echo_block(memory)
            shop_state['redeemed'][product['id']]=bought+1
            seq_tag=guard['ledger']['sequence']+1
            shop_state['recent'].insert(0,f"{clock_str} | {product['id']} | {product['name']}×{pack_qty} | -{eff_price}积分 | {catalog_item_id}")
            shop_state['recent']=shop_state['recent'][:SHOP_RECENT_LIMIT]
            memory=write_shop_echo_block(memory,shop_state)
            memory=append_echo(
                memory,'shop_redeemed',f"{product['id']}@{seq_tag}",
                f"商城兑换「{product['name']}」×{pack_qty}（-{eff_price}积分{disc_note}，{catalog_item_id}）",
            )
            rr._atomic(memory_path,memory.encode('utf-8'))
            receipt=_publish_deterministic_stage(service,guard,stage,{
                'kind':'shop_redeem',
                'shop_id':product['id'],
                'item_id':catalog_item_id,
                'item_name':product['name'],
                'quantity':pack_qty,
                'price':eff_price,
                'base_price':base_price,
                'charm_discount':charm_disc,
                'points_before':points,
                'points_after':points_after,
            })
            return {'status':'committed','receipt':receipt,'replayed':False}
        finally:
            shutil.rmtree(stage)


def persist_dynamic_shop_items(service, raw_payload, *, query='', expected_save_epoch=None):
    """Validate AI restock output and atomically append DYN-* items to save_state.json via RoundStore WAL."""
    with service.store._locked():
        if expected_save_epoch and expected_save_epoch != service._save_epoch():
            raise rr.ConflictError('存档已切换，本次AI进货已作废')
        tasks = service._read()
        service._expire(tasks)
        if any(j['status'] in ACTIVE_JOB_STATUSES for j in tasks['jobs'].values()):
            raise rr.ConflictError('当前有剧情行动正在处理，请待本段结算完成后再重新询货')
        files = service.store._files()
        catalog = load_shop_catalog(service.root, optional=True)
        st, ly, _ = save_store.load_bundle(service.root, files)
        existing_dyn = list((st.get('shop') or {}).get('dynamic_catalog') or [])
        existing_names = [it['name'] for it in catalog.get('items', [])] + [
            it.get('name', '') for it in existing_dyn if isinstance(it, dict) and it.get('name')
        ]
        next_seq = int((st.get('shop') or {}).get('next_dyn_seq') or 1)
        validated = validate_dynamic_shop_items(raw_payload, existing_names, next_seq, query=query)
        merged_dyn = (existing_dyn + validated['items'])[-SHOP_DYNAMIC_LIMIT:]
        st['shop']['dynamic_catalog'] = merged_dyn
        st['shop']['next_dyn_seq'] = validated['next_dyn_seq']
        ledger = service.store._ledger()
        sequence = ledger['sequence'] + 1
        after = dict(files)
        data = json.loads(after.get('data.json') or b'{}')
        data['state_version'] = sequence
        after['data.json'] = rr._json(data)
        st['runtime']['last_sequence'] = max(int(st['runtime'].get('last_sequence') or 0), sequence)
        after.update(save_store.render_bundle_bytes(st, ly, data_dict=data))
        revision = rr._revision(after)
        ledger['sequence'] = sequence
        after[rr.META] = rr._json(ledger)
        service.store._commit_files(after)
        return {
            'shopkeeper_reply': validated['shopkeeper_reply'],
            'added_items': validated['items'],
            'rejected_reasons': validated['rejected_reasons'],
            'revision': revision,
            'state_version': sequence,
        }


def delete_dynamic_shop_item(service, item_id, *, save_epoch=None):
    """Atomically remove an AI-restocked DYN-* item from save_state.json via RoundStore WAL."""
    if not isinstance(item_id, str) or not re.fullmatch(r'DYN-\d+', item_id):
        raise rr.RoundError('仅支持移除动态进货商品（DYN-编号）')
    with service.store._locked():
        if save_epoch and save_epoch != service._save_epoch():
            raise rr.ConflictError('存档已切换，请刷新后再试')
        tasks = service._read()
        service._expire(tasks)
        if any(j['status'] in ACTIVE_JOB_STATUSES for j in tasks['jobs'].values()):
            raise rr.ConflictError('当前有剧情行动正在处理，请待本段结算完成后再操作')
        files = service.store._files()
        st, ly, _ = save_store.load_bundle(service.root, files)
        dyn = list((st.get('shop') or {}).get('dynamic_catalog') or [])
        kept = [it for it in dyn if it.get('id') != item_id]
        if len(kept) == len(dyn):
            raise rr.RoundError('动态货架中未找到该商品：' + item_id)
        st['shop']['dynamic_catalog'] = kept
        ledger = service.store._ledger()
        sequence = ledger['sequence'] + 1
        after = dict(files)
        data = json.loads(after.get('data.json') or b'{}')
        data['state_version'] = sequence
        after['data.json'] = rr._json(data)
        st['runtime']['last_sequence'] = max(int(st['runtime'].get('last_sequence') or 0), sequence)
        after.update(save_store.render_bundle_bytes(st, ly, data_dict=data))
        revision = rr._revision(after)
        ledger['sequence'] = sequence
        after[rr.META] = rr._json(ledger)
        service.store._commit_files(after)
        return {'removed_id': item_id, 'remaining_count': len(kept), 'revision': revision, 'state_version': sequence}


def claim_task_reward(service,body):
    """Deterministic zero-stamina, zero-LLM claim of the head completed task reward from pending_items queue."""
    with service.store._locked():
        guard=_guard_deterministic_tx(service,body,{'request_id','base_revision','save_epoch'},'领取委托奖励')
        if guard['replayed']:
            return {'status':'committed','receipt':guard['receipt'],'replayed':True}
        files=guard['files']
        stage=Path(tempfile.mkdtemp(prefix='work-',dir=service.store.runtime))
        try:
            for name,raw in files.items():
                if raw is not None:
                    rr._atomic(stage/name,raw)
            engine=rr._engine(service.root,stage)
            memory_path=stage/rr.FILES[0]
            memory=memory_path.read_text(encoding='utf-8')
            task_state=engine._parse_task_block(memory)
            pending_list=list((task_state or {}).get('pending_items') or ([] if not (task_state and task_state.get('pending_item')) else [task_state['pending_item']]))
            pending=pending_list[0] if pending_list else None
            if not pending:
                raise rr.RoundError('当前没有待领取的委托奖励道具')
            pm=re.fullmatch(r'(TASK-\d+)\s*\|\s*([^|]+?)\s*\|完成回合(\d+)',pending.strip())
            if not pm:
                raise rr.RoundError('待发道具记录格式无法解析：'+str(pending))
            task_id,item_desc=pm.group(1),pm.group(2).strip()
            item_name=_clean_single_line(item_desc)[:40] or f'{task_id}纪念小物'
            runtime=state(service.root,files) if enabled(service.root) else {'memory_round':1,'clock':None}
            memory_round=max(1,int(runtime.get('memory_round') or 1))
            clock_str=_clock_label(runtime)
            entry={
                'name':item_name,
                'type':'永久性',
                'desc':f'完成悬赏委托（{task_id}）所获奖励小物：{item_desc}。',
                'quantity':1,
                'status':'仓库中',
                'location':'随身',
                'target':'未使用',
                'duration':'无',
                'expire_rule':'无',
                'usage_record':f'{clock_str} - 委托奖励领取入囊',
                'remark':f'委托奖励（{task_id}）· {clock_str}',
                'system_effect':'',
                'giftable':True,
                'action':'add',
            }
            rr._engine_call(engine.update_item_catalog,memory_round,[entry])
            pending_list.pop(0)
            task_state['pending_items']=pending_list
            task_state['pending_item']=pending_list[0] if pending_list else None
            rr._engine_call(engine._write_task_block,task_state)
            catalog_text=(stage/rr.FILES[1]).read_text(encoding='utf-8')
            found=engine._find_item_block(catalog_text,name=item_name)
            catalog_item_id=engine._parse_item_block(found['block']).get('道具ID','ITEM-001') if found else 'ITEM-001'
            memory=memory_path.read_text(encoding='utf-8')
            memory=append_echo(
                memory,'task_reward_claimed',task_id,
                f"领取委托 {task_id} 奖励「{item_name}」（{catalog_item_id}）",
            )
            rr._atomic(memory_path,memory.encode('utf-8'))
            receipt=_publish_deterministic_stage(service,guard,stage,{
                'kind':'task_claim',
                'task_id':task_id,
                'item_id':catalog_item_id,
                'item_name':item_name,
                'remaining_pending_count':len(pending_list),
            })
            return {'status':'committed','receipt':receipt,'replayed':False}
        finally:
            shutil.rmtree(stage)


def upgrade_passive_skill(service,body):
    """Deterministic zero-stamina, zero-LLM passive Lv.0->Lv.4 EXP unlock for one heroine."""
    with service.store._locked():
        guard=_guard_deterministic_tx(service,body,{'request_id','base_revision','save_epoch','target'},'定向被动解锁')
        if guard['replayed']:
            return {'status':'committed','receipt':guard['receipt'],'replayed':True}
        target=body['target']
        if target not in PASSIVE_TARGETS:
            raise rr.RoundError('定向被动目标非法：'+str(target))
        files=guard['files']
        stage=Path(tempfile.mkdtemp(prefix='work-',dir=service.store.runtime))
        try:
            for name,raw in files.items():
                if raw is not None:
                    rr._atomic(stage/name,raw)
            engine=rr._engine(service.root,stage)
            memory_path=stage/rr.FILES[0]
            memory=memory_path.read_text(encoding='utf-8')
            cur_lv=read_passive_level(memory,target)
            levels=passive_levels(service.root)
            if cur_lv>=len(levels)-1:
                raise rr.RoundError(f'{target} 定向被动已达最高级 Lv.{cur_lv}')
            next_info=levels[cur_lv+1]
            cost_exp=next_info['cost']
            exp_before=engine._read_attr_value(memory,'系统宿主','经验值')
            if exp_before is None:
                raise rr.RoundError('正式存档缺少宿主经验值字段')
            if exp_before<cost_exp:
                raise rr.RoundError(f"当前经验值不足（解锁 {next_info['tag']} {next_info['name']} 需 {cost_exp}，现有 {exp_before}）")
            exp_after=exp_before-cost_exp
            charm_before=engine._read_attr_value(memory,'系统宿主','魅力')
            host_patch={'经验值':exp_after}
            charm_gain=0
            if charm_before is not None and charm_before<100:
                host_patch['魅力']=min(100,charm_before+1)
                charm_gain=host_patch['魅力']-charm_before
            memory=engine._simulate_panel(memory,{
                '系统宿主':host_patch,
                target:{'被动':next_info['tag']},
            })
            charm_note=f"，魅力+{charm_gain}" if charm_gain else ""
            memory=append_echo(
                memory,'passive_upgraded',f"{target}@{next_info['tag']}",
                f"对{target}解锁「{next_info['name']}」（{next_info['tag']}，-{cost_exp}经验{charm_note}）",
            )
            rr._atomic(memory_path,memory.encode('utf-8'))
            receipt=_publish_deterministic_stage(service,guard,stage,{
                'kind':'passive_upgrade',
                'target':target,
                'level_before':f'Lv.{cur_lv}',
                'level_after':next_info['tag'],
                'skill_name':next_info['name'],
                'cost_exp':cost_exp,
                'exp_before':exp_before,
                'exp_after':exp_after,
                'charm_gain':charm_gain,
            })
            return {'status':'committed','receipt':receipt,'replayed':False}
        finally:
            shutil.rmtree(stage)


def acquire_intel(service,body):
    """Deterministic zero-stamina acquisition of an unlocked one-time commercial intel item."""
    with service.store._locked():
        guard=_guard_deterministic_tx(service,body,{'request_id','base_revision','save_epoch','intel_id'},'商业情报入库')
        if guard['replayed']:
            return {'status':'committed','receipt':guard['receipt'],'replayed':True}
        intel_id=body['intel_id']
        if not isinstance(intel_id,str) or not re.fullmatch(r'INTEL-\d+',intel_id):
            raise rr.RoundError('商业情报ID无效')
        catalog=load_intel_catalog(service.root,optional=False)
        item=next((x for x in catalog['items'] if x['id']==intel_id),None)
        if item is None:
            raise rr.RoundError('商业情报目录中未找到：'+intel_id)
        files=guard['files']
        stage=Path(tempfile.mkdtemp(prefix='work-',dir=service.store.runtime))
        try:
            for name,raw in files.items():
                if raw is not None:
                    rr._atomic(stage/name,raw)
            engine=rr._engine(service.root,stage)
            memory_path=stage/rr.FILES[0]
            memory=memory_path.read_text(encoding='utf-8')
            istate=parse_intel_block(memory)
            if intel_id in istate['held']:
                raise rr.RoundError(f"已持有情报「{item['name']}」")
            if intel_id in istate['consumed']:
                raise rr.RoundError(f"一次性情报「{item['name']}」已消耗作废，不可重复获取")
            biz=engine._read_attr_value(memory,'系统宿主','商业嗅觉')
            biz=0 if biz is None else biz
            if biz<item['min_biz']:
                raise rr.RoundError(f"商业嗅觉不足（需 ≥ {item['min_biz']}，当前 {biz}）")
            if istate['su_ab_contacts']<item['min_su_ab_contacts']:
                raise rr.RoundError(f"与苏婉青的A/B级接触次数不足（需 ≥ {item['min_su_ab_contacts']}，当前 {istate['su_ab_contacts']}）")
            istate['held'].append(intel_id)
            memory=write_intel_block(memory,istate,catalog)
            memory=append_echo(
                memory,'intel_acquired',intel_id,
                f"整理掌握商业情报「{item['name']}」（一次性筹码）",
            )
            rr._atomic(memory_path,memory.encode('utf-8'))
            receipt=_publish_deterministic_stage(service,guard,stage,{
                'kind':'intel_acquire',
                'intel_id':intel_id,
                'intel_name':item['name'],
                'biz':biz,
            })
            return {'status':'committed','receipt':receipt,'replayed':False}
        finally:
            shutil.rmtree(stage)


def toggle_business_leverage(service,body):
    """Deterministic zero-stamina arm/disarm of Business Leverage (requires 商业嗅觉>=60 + held intel)."""
    with service.store._locked():
        guard=_guard_deterministic_tx(service,body,{'request_id','base_revision','save_epoch','action','intel_id'},'商业杠杆切换')
        if guard['replayed']:
            return {'status':'committed','receipt':guard['receipt'],'replayed':True}
        action=body['action'];intel_id=body['intel_id']
        if action not in ('arm','disarm'):
            raise rr.RoundError('商业杠杆操作须为 arm 或 disarm')
        catalog=load_intel_catalog(service.root,optional=False)
        files=guard['files']
        stage=Path(tempfile.mkdtemp(prefix='work-',dir=service.store.runtime))
        try:
            for name,raw in files.items():
                if raw is not None:
                    rr._atomic(stage/name,raw)
            engine=rr._engine(service.root,stage)
            memory_path=stage/rr.FILES[0]
            memory=memory_path.read_text(encoding='utf-8')
            istate=parse_intel_block(memory)
            biz=engine._read_attr_value(memory,'系统宿主','商业嗅觉')
            biz=0 if biz is None else biz
            if action=='arm':
                min_biz=int(catalog.get('leverage_min_biz',60))
                if biz<min_biz:
                    raise rr.RoundError(f'启用商业杠杆需要商业嗅觉 ≥ {min_biz}（当前 {biz}）')
                if not isinstance(intel_id,str) or intel_id not in istate['held']:
                    raise rr.RoundError('所选商业情报未持有，无法预备商业杠杆')
                istate['leverage_armed']=intel_id
            else:
                istate['leverage_armed']=''
            memory=write_intel_block(memory,istate,catalog)
            rr._atomic(memory_path,memory.encode('utf-8'))
            iname=next((it['name'] for it in catalog['items'] if it['id']==istate['leverage_armed']),'')
            receipt=_publish_deterministic_stage(service,guard,stage,{
                'kind':'business_leverage',
                'action':action,
                'leverage_armed':istate['leverage_armed'],
                'intel_name':iname,
            })
            return {'status':'committed','receipt':receipt,'replayed':False}
        finally:
            shutil.rmtree(stage)

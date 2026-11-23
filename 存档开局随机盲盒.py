# -*- coding: utf-8 -*-
"""
存档开局随机盲盒（P2 自包含存档版）

职责：
  - 为空白新档随机抽取一条合规「序幕锚点」，通过 save_store 与 RoundStore 原子写入
    存档/save_state.json、存档/四层记忆.json、存档/近期演播.json 与单向渲染视图及 data.json
  - 绝不覆盖已有进度档（如需重开，请先运行 存档清理器.py 或在网页端使用「重开新档」）

使用：在项目根目录运行
  python3 存档开局随机盲盒.py
"""

from __future__ import annotations

import os
import random
import re

# 项目根 / 记忆库路径（与 injection_core、清理器一致）
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_DIR = os.getcwd()

DATA_DIR = os.path.join(BASE_DIR, "存档")
MEMORY_FILE = os.path.join(DATA_DIR, "全局记忆库.txt")

# 序幕隐藏标记（常驻主规则「开始故事」可识别，避免误重置）
PROLOGUE_MARK = "【系统隐藏标记：以上为新游戏序幕锚点，剧情从此刻正式开始计算】"

# =============================================================================
# 剧本池
# 每条必须自洽：weekday / time / 主场景 与 presence 对齐法典
# presence: {角色: (地点, 事由)}  四人齐全
# l1_body: 单段话序幕锚点（勿自带【1】、勿分栏标题）；只供「开始故事」继承此刻，不是每回合填写模板
# =============================================================================
SCENARIOS = [
    {
        "id": "zhiyun_friday_study",
        "title": "周五深夜 · 主宅书房 · 母亲",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "晚间在家休息"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周五深夜十一时，徐家主宅二楼书房。冷气开得偏低，实木书桌上摊着压了红签的并购简报。"
            "沈知韫穿着淡紫色细肩带缎面上衣与同色薄纱开衫，米白提花短裤配露趾拖鞋，正伏案翻阅文件。"
            "房门半掩，徐志北端着温水站在门边，扑面而来的是空调冷风与纸墨微苦的气息。"
        ),
    },
    {
        "id": "nianwei_saturday_studio",
        "title": "周六凌晨 · 主宅北窗 · 姐姐",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周六凌晨一时，徐家主宅二楼北窗画架旁。落地灯压出一方冷白光圈，窗缝漏进夜风和淡淡炭笔灰味。"
            "徐念薇穿着浅蓝色方领抽绳长泡泡袖居家裙、脚踩银色蝴蝶结凉拖，坐在高脚凳上整理周末带回的速写本，"
            "脚边斜倚着装满画稿的牛皮纸袋；徐志北停在门廊边，脚底木板微凉，能闻到纸页间散出的松节油残味。"
        ),
    },
    {
        "id": "wanqing_apartment_night",
        "title": "周中夜 · 顶层公寓 · 嫂子",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("工作室", "工作日傍晚在画室"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("市中心顶层公寓", "到访"),
        },
        "l1_body": (
            "周三晚九时，市中心顶层公寓客厅。落地窗外车河静流，暖灯映着茶几上一杯未动过的温水和滑出一角的便签纸。"
            "苏婉青穿着浅黄色碎花吊带睡裙与白色蝴蝶结平底凉拖，坐在沙发外侧；玄关门已从内侧带上，"
            "徐志北刚在近旁落步，空气里浮着淡淡的沐浴露甜香与高楼室内的安静。"
        ),
    },
    {
        "id": "wanqing_friday_visit",
        "title": "周五傍晚 · 主宅请安 · 嫂子",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("工作室", "工作日傍晚在画室"),
            "苏婉青": ("徐家主宅", "周五请安窗"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周五傍晚五时，徐家主宅一楼玄关至起居室。苏婉青穿着浅黄色细肩带修身短裙外搭白色宽松长袖开衫与米白细跟鞋，"
            "按请安惯例拎着点心礼袋到访，未作过夜打算；提袋刚搁上边几，徐志北从楼梯转角走下，撞见她微红的手腕和带进门的一缕晚风。"
        ),
    },
    {
        "id": "zhiyun_sunday_noon",
        "title": "周日午间 · 主宅餐厅 · 家庭",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("徐家主宅", "周日家庭午餐窗"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周日十一时五十分，徐家主宅餐厅。家庭午餐尚未开席，长桌上茶具温热。"
            "沈知韫着淡紫色缎面薄纱居家服居中，徐念薇着浅蓝色泡泡袖居家裙坐在较远一侧，"
            "苏婉青一身浅黄短裙配白开衫外出装依周日惯例到宅，手边放着伴手礼；徐志北站在桌旁，席间礼貌与暗流并存。"
        ),
    },
    {
        "id": "zhiyun_rain_balcony",
        "title": "工作日雨后 · 主宅阳台 · 母亲",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周四十六时三十分，雷阵雨刚歇，潮湿土腥顺着廊沿漫上二楼阳台内侧。"
            "沈知韫提前从公司回到徐家主宅，已换上淡紫色细肩带缎面居家服与薄纱开衫，背对玻璃门望向积水庭院，手机还攥在指间。"
            "徐志北走近玻璃门，冷湿水汽沾上袖口，能听见檐角滴水的轻响。"
        ),
    },
    {
        "id": "nianwei_sunday_evening_studio",
        "title": "周日傍晚 · 主宅露台侧厅 · 姐姐",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周日傍晚六时，徐家主宅二楼露台侧厅。天光转冷，长桌上摊着未收完的水彩草稿与洗笔瓷筒。"
            "徐念薇穿着浅蓝色方领抽绳长泡泡袖居家裙，肩头搭着一条薄毯，正慢条斯理擦净画笔；"
            "侧厅门虚开一掌宽，徐志北推门入内，晚风带着颜料的微苦气味掠过指尖。"
        ),
    },
    {
        "id": "wanqing_apartment_morning",
        "title": "工作日上午 · 公寓 · 嫂子",
        "presence": {
            "沈知韫": ("公司", "工作日上班中"),
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("市中心顶层公寓", "到访"),
        },
        "l1_body": (
            "周二上午九时，市中心顶层公寓开放式餐厨。意式咖啡机轻响，落地窗外是工作日密集车流。"
            "苏婉青穿着浅黄色碎花吊带睡裙、踩着白色蝴蝶结凉拖，正在岛台边准备早餐，台面上的手机屏幕刚暗下去；"
            "徐志北靠在岛台外侧，现磨咖啡焦香混着清晨阳光落进手边。"
        ),
    },
]


def _validate_scenario(sc: dict) -> None:
    p = sc["presence"]
    for name in ("沈知韫", "徐念薇", "苏婉青", "徐志北"):
        if name not in p:
            raise ValueError(f"剧本 {sc['id']} 缺少 presence: {name}")
    # 轻量合规：苏婉青在主宅必须事由像看望/午餐/请安
    loc, reason = p["苏婉青"]
    if re.search(r"主宅|别墅|徐家", loc) and not re.search(
        r"请安|午餐|周日|周五|看望|家宴|叫来|指令", reason
    ):
        raise ValueError(f"剧本 {sc['id']} 苏婉青在主宅但事由不像看望窗: {reason}")


def randomize_start(seed: int | None = None) -> None:
    """Initialize an empty save with the shared writer; never overwrite an existing story."""
    from pathlib import Path
    import round_runtime as rr
    request_id = 'manual-opening-' + (str(seed) if seed is not None else __import__('uuid').uuid4().hex)
    store = rr.RoundStore(Path(BASE_DIR))
    try:
        with store._locked():
            result = initialize_prologue(store.root, request_id)
        print('序幕已准备：', result['scenario_id'])
        print('打开首页点按开始演播，读完后选择；已有档不会被覆盖。')
    except rr.ConflictError as exc:
        print('提示：', str(exc))
        print('如需重新随机开局，请先运行 `python3 存档清理器.py` 或在网页端使用「重开新档」。')


import copy
import hashlib

# Explicit game-time anchors for the existing pool; no wall-clock date is used.
OPENING_TIMES = {
    'zhiyun_friday_study': ('周五', '23:00'),
    'nianwei_saturday_studio': ('周六', '01:00'),
    'wanqing_apartment_night': ('周三', '21:00'),
    'wanqing_friday_visit': ('周五', '17:00'),
    'zhiyun_sunday_noon': ('周日', '11:50'),
    'zhiyun_rain_balcony': ('周四', '16:30'),
    'nianwei_sunday_evening_studio': ('周日', '18:00'),
    'wanqing_apartment_morning': ('周二', '09:00'),
}
OPENING_LINES = {
    'zhiyun_friday_study': (
        '沈知韫',
        '她把并购简报的一角压回文件夹下，摘下无框眼镜轻按了半秒眉心，才抬眼望向门边。',
        '[low restrained voice] 这么晚还没睡？外头冷气大，顺手把门带上，过来坐会儿。',
    ),
    'nianwei_saturday_studio': (
        '徐念薇',
        '她停下翻检速写本的手，合拢封面压住边角，侧眼瞥向门廊，顺手把脚边的牛皮纸袋往椅下收了半寸。',
        '[cool restrained voice] 还没睡？别踩到地上的画稿，有事直接说。',
    ),
    'wanqing_apartment_night': (
        '苏婉青',
        '她把茶几上那杯没动过的温水朝徐志北这边轻推了一寸，指尖撤回时顺手把露出一角的便签压回杂志底下。',
        '[soft timid voice] 这么晚还跑一趟，先坐吧。承邺这周在外地忙，屋里怪冷清的……要换杯热茶吗？',
    ),
    'wanqing_friday_visit': (
        '苏婉青',
        '她把带给主宅的点心礼袋搁上玄关边几，听见脚步声便回过身，下意识理了理白色开衫的袖口，笑意客气又带着几分拘谨。',
        '[polite, careful] 志北，今天也在家呀。我按规矩过来看看妈，顺便带了些她爱吃的点心。',
    ),
    'zhiyun_sunday_noon': (
        '沈知韫',
        '她扫过一圈餐桌，目光在苏婉青手边的伴手礼和念薇略远一格的座椅间掠过，自己拉开主位座椅。',
        '[warm but guarded] 都到齐了，先落座吧。厨房那边还要一会儿，志北坐妈手边。',
    ),
    'zhiyun_rain_balcony': (
        '沈知韫',
        '听见身后脚步声，她没有立刻回头，只微微侧脸，把玻璃门内侧避风的位置让开半步。',
        '[controlled breath] 雨刚歇，风里还带着潮气。怎么这个点上来找我？',
    ),
    'nianwei_sunday_evening_studio': (
        '徐念薇',
        '她把最后两支画笔插进瓷筒，指尖蹭掉一点干掉的蓝灰颜料，拢紧肩上薄毯，隔着长桌看了过来。',
        '[quiet detached tone] 门没锁，进来就行。晚饭前我还要收完这些习作。',
    ),
    'wanqing_apartment_morning': (
        '苏婉青',
        '她按停嗡嗡作响的咖啡机，把温热的骨瓷杯挪到岛台边，眼角余光扫过亮了一瞬又暗下的手机屏幕。',
        '[gentle breathy voice] 早餐再等几分钟就好。你难得上午过来，先喝杯黑咖啡，还是兑点牛奶？',
    ),
}
OPENING_CHOICES = {
    'zhiyun_friday_study': (
        '顺口问起桌上那份压了红签的并购简报，试探公司近况',
        '把温水搁到她手边，俯身替她把滑落的薄纱衣角搭回肩头',
        '走近书桌站定，直问她深夜还在为大哥外地那单项目兜底吗',
    ),
    'nianwei_saturday_studio': (
        '靠在门框边，问起她刚才匆忙合上的那本速写里画的是什么',
        '蹲身替她把脚边歪斜的牛皮纸袋扶正，顺手递过滚到地毯边的炭笔',
        '拉开一旁高脚凳坐近半步，直问她美院青年画展那边是不是出了变故',
    ),
    'wanqing_apartment_night': (
        '接过水杯落座，顺着话头打听大哥在外地最近到底在忙什么项目',
        '递回滑落在沙发边的小披肩，指尖轻擦过她手背，留心她一瞬停顿',
        '目光落在杂志下露出的一角便签上，笑问她平时记着主宅琐事累不累',
    ),
    'wanqing_friday_visit': (
        '迎上前寒暄两句，随口问起她每周五来主宅是不是大哥特意交代的',
        '伸手接过她手里沉甸甸的礼盒，顺势托稳她被提袋勒红的手腕',
        '压低声音留住正要往餐厅走的嫂子，问她今天除了请安还带了什么口信',
    ),
    'zhiyun_sunday_noon': (
        '顺势在母亲身旁落座，聊起大哥外地项目风声，暗中观察三人的神色',
        '先替母亲与二姐斟好热茶，转手把温热茶盏递给略显拘谨的苏婉青',
        '趁开席前的空当，当众挑起主宅与公司近期的安排，试探各自的口风',
    ),
    'zhiyun_rain_balcony': (
        '走到她身侧半步处，轻声问她今天提前回来是不是公司遇到了棘手事',
        '伸手替她把被湿风吹散的薄纱衣角拢稳，顺带试探她微凉的指尖温度',
        '合上身后的玻璃门隔开走廊，直问她刚才电话里压着火气是在替谁善后',
    ),
    'nianwei_sunday_evening_studio': (
        '停在长桌对面扫过摊开的习作，问她周末宁可在主宅赶稿也不去画室的缘由',
        '顺手递过桌边干净的擦手巾，替她把滑到肩下的薄毯往上拉稳',
        '拿起桌角一张未干透的冷调草稿细看，直问画里那把空椅子是不是主宅长桌',
    ),
    'wanqing_apartment_morning': (
        '靠在岛台边要了杯黑咖啡，漫不经心问起刚才手机是不是大哥又在催问家里',
        '上前接过她刚倒满的烫手骨瓷杯，自然托住杯底，留意她泛红的耳尖',
        '绕到岛台内侧挡住她要收手机的动作，轻声问她独守这间空公寓到底图什么',
    ),
}


OPENING_TASKS = {
    'zhiyun_friday_study': {
        'title': '深夜灯下',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '素银云纹书签',
    },
    'nianwei_saturday_studio': {
        'title': '北窗微光',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '便携炭笔素描本',
    },
    'wanqing_apartment_night': {
        'title': '夜色初叙',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '手作安神香囊',
    },
    'wanqing_friday_visit': {
        'title': '主宅请安',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '釉白瓷小茶匙',
    },
    'zhiyun_sunday_noon': {
        'title': '同席家宴',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '银杏叶金属餐巾扣',
    },
    'zhiyun_rain_balcony': {
        'title': '雨歇微凉',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '细棉格子手帕',
    },
    'nianwei_sunday_evening_studio': {
        'title': '暮色收笔',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '亚麻画稿收纳袋',
    },
    'wanqing_apartment_morning': {
        'title': '晨间破冰',
        'target': '系统宿主',
        'attr': '积分',
        'value': 4,
        'tier': 'small',
        'item_desc': '手冲咖啡滤纸礼盒',
    },
}


def choose_opening(request_id, scenario_id=None):
    """Return a deterministic projection of the original pool, without writing files."""
    if not isinstance(request_id, str) or not request_id:
        raise ValueError('序幕须有稳定新档编号')
    pool = list(SCENARIOS)
    for scenario in pool:
        _validate_scenario(scenario)
    if scenario_id is not None:
        chosen = next((s for s in pool if s['id'] == scenario_id), None)
        if chosen is None: raise ValueError('序幕场景未登记')
    else:
        chosen = random.Random(int(hashlib.sha256(request_id.encode()).hexdigest(), 16)).choice(pool)
    chosen = copy.deepcopy(chosen)
    weekday, clock = OPENING_TIMES[chosen['id']]
    speaker, action, line = OPENING_LINES[chosen['id']]
    starter_task = copy.deepcopy(OPENING_TASKS[chosen['id']])
    chosen.update(clock={'day': 1, 'time': clock}, weekday=weekday, starter_task=starter_task,
                  messages=[{'kind': 'narration', 'speaker': '', 'text': chosen['l1_body']},
                            {'kind': 'action', 'speaker': speaker, 'text': action},
                            {'kind': 'dialogue', 'speaker': speaker, 'text': line}],
                  decision={'prompt': '此刻，你准备怎么回应？', 'options': [
                      {'id': k, 'text': text} for k, text in zip(('A', 'B', 'C'), OPENING_CHOICES[chosen['id']])]})
    return chosen


def initialize_prologue(root, request_id, scenario_id=None):
    """Caller holds the shared RoundStore lock, inside a new-game reset transaction."""
    import json
    from pathlib import Path
    import round_runtime as rr
    import interaction_runtime as ir
    import save_store
    root = Path(root).resolve()
    store = rr.RoundStore(root)
    files = store._files()
    data = json.loads(files['data.json'] or b'{}')
    saved = data.get('prologue', {})
    if saved.get('request_id') == request_id:
        return {'scenario_id': saved['scenario_id'], 'replayed': True}
    if data.get('storyNodes') or data.get('interaction', {}).get('count') or store._ledger()['receipts']:
        raise rr.ConflictError('已有剧情，序幕不能覆盖；请经新档确认入口初始化')
    chosen = choose_opening(request_id, scenario_id)
    policy = ir.policy(root)
    if any(place not in policy['locations'] for place, reason in chosen['presence'].values()):
        raise rr.RoundError('序幕中的地点未登记')
    engine = rr._engine(root, root)
    st, layers, _ = save_store.load_bundle(root, files)
    if any((layers.get('layers') or {}).get(k) for k in ('L1', 'L2', 'L3', 'L4')):
        raise rr.ConflictError('已有记忆，不能另抽序幕覆盖')
    st['presence'] = {
        name: {'location': loc, 'reason': reason}
        for name, (loc, reason) in chosen['presence'].items()
    }
    import story_progression as sp
    st['director']['scene_location'] = st['presence']['徐志北']['location']
    st['director']['last_time_slot'] = sp._clock_time_slot(chosen['clock'])
    l1_clean = re.sub(r'^【\d+】\s*', '', chosen['l1_body'].strip())
    l1_clean = re.sub(r'\s{2,}', ' ', re.sub(r'\s*\n\s*', '', l1_clean)).strip()
    layers = save_store.default_layers(l1_clean, prologue_active=True)
    starter = chosen.get('starter_task')
    if starter:
        preview_mem = save_store.render_memory_txt(st, layers)
        ok, err = engine._validate_task(starter, preview_mem)
        if not ok:
            raise rr.RoundError('开局首环委托校验失败: ' + str(err))
        st['tasks'] = {
            'current': {
                'id': 'TASK-001',
                'title': str(starter['title']).strip(),
                'target': str(starter['target']).strip(),
                'attr': str(starter['attr']).strip(),
                'value': int(starter['value']),
                'tier': str(starter['tier']).strip(),
                'item_desc': str(starter['item_desc']).strip(),
                'status': '进行中',
                'issue_round': 1,
                'complete_round': None,
            },
            'history': [],
            'pending_items': [],
        }
    presence = copy.deepcopy(st['presence'])
    ident = 'prologue-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
    runtime = {'version': 1, 'clock': chosen['clock'], 'memory_round': 1,
               'last_closed': 0, 'phase': 'ready', 'item_recovered': 0, 'action_index': 0, 'closed_by': ''}
    prologue_meta = {'request_id': request_id, 'scenario_id': chosen['id'], 'weekday': chosen['weekday'], 'title': chosen['title']}
    st['runtime'].update({
        'clock': copy.deepcopy(chosen['clock']),
        'weekday': chosen['weekday'],
        'prologue': copy.deepcopy(prologue_meta),
        'memory_round': 1,
        'last_closed': 0,
        'phase': 'ready',
        'item_recovered': 0,
        'action_index': 0,
        'closed_by': '',
        'last_sequence': 1,
        'last_segment_id': ident,
    })
    data.update(round=1, sceneTitle=presence['徐志北']['location'], presence=presence,
                request_id=ident, state_version=1, options_text='', story_runtime=runtime,
                prologue=prologue_meta,
                interaction={'count': 1, 'actions': 0, 'last_sequence': 1, 'segment_id': ident},
                storyNodes=[{'type': 'dialogue' if m['kind'] == 'dialogue' else 'narration', 'text': m['text'],
                            **({'speaker': m['speaker']} if m['kind'] == 'dialogue' else {})} for m in chosen['messages']])
    rendered_files = save_store.render_bundle_bytes(st, layers, data_dict=data)
    for rel, raw_b in rendered_files.items():
        files[rel] = raw_b
    # before_world has the same initial location/time, with no unseen numerical reward.
    temporary = dict(files); temporary['data.json'] = rr._json(data)
    world = ir.view(store, temporary)
    listeners = ['徐志北', *world['cast']]
    if (layers.get('layers') or {}).get('L1'):
        layers['layers']['L1'][0]['known_by'] = list(listeners)
        rendered_files = save_store.render_bundle_bytes(st, layers, data_dict=data)
        for rel, raw_b in rendered_files.items():
            files[rel] = raw_b
    row = {'version': 2, 'id': ident, 'sequence': 1, 'count': 1, 'input': '', 'input_kind': 'system',
           'selection': {'segment_id': '', 'option_id': 'BEGIN'}, 'messages': chosen['messages'],
           'decision': chosen['decision'], 'operation': None, 'handoff': '',
           'known_by': listeners, 'input_known_by': ['徐志北'], 'messages_known_by': listeners,
           'location': world['location'], 'after_location': world['location'], 'created_at': 0,
           'cost': {'status': 'active', 'kind': 'prologue', 'total': 0},
           'audit': {'origin': 'registered_prologue', 'scenario_id': chosen['id']}, 'before_world': world}
    pb_obj = {'version': 1, 'segment_id': ident, 'revealed': 0, 'completed': False}
    files['data.json'] = rr._json(data)
    files[ir.ARCHIVE+'/000000000001.json'] = rr._json(row)
    files[ir.PLAYBACK] = rr._json(pb_obj)
    files[rr.RECENT_PLAYBACK] = rr._json(save_store.append_recent_segment(save_store.default_recent(), row, playback_state=pb_obj))
    revision = rr._revision(files)
    receipt = {'request_id': ident, 'revision': revision, 'round': 1, 'state_version': 1, 'status': 'committed', 'replayed': False}
    files[rr.META] = rr._json({'version': 1, 'sequence': 1, 'receipts': {ident: {'payload_hash': rr._digest(rr._json(chosen)), 'receipt': receipt}}})
    store._commit_files(files)
    return {'scenario_id': chosen['id'], 'replayed': False}


if __name__ == "__main__":
    print("=======================================")
    print(" 初始锚点随机盲盒（P2 自包含存档版）")
    print(" 驻地合规 · 人物所在 · L1 序幕")
    print("=======================================")
    randomize_start()
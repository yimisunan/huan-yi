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
            "温水杯壁贴着掌心发烫，周五深夜十一点的书房冷气开得偏低，门一推开，纸墨味混着沈知韫身上那缕冷调幽兰香扑面落进呼吸里。"
            "实木书桌下，她那双脚踝纤细、线条匀称的白皙秀足正半勾着露趾拖鞋舒展足弓，米白与淡紫交叉带垂在足背将落未落，淡粉趾甲在暖灯下泛着润泽微光；"
            "上身淡紫细肩带缎面贴着腰线微收，薄纱开衫随伏案翻看红签简报的动作滑下半寸。徐志北脚步顿在门边，喉结不受控地滚了一下，呼吸硬压慢了半拍。"
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
            "脚底木板透着周六凌晨一点的微凉，松节油与极淡皂香顺着北窗冷风漫过门廊。冷白落地灯照着高脚凳上的徐念薇——"
            "她穿着浅蓝方领抽绳泡泡袖居家裙，低头整理速写本时，蓬松高丸子头散下几缕碎发贴在冷白后颈；"
            "那双修长清冷、指节分明的秀手正压着画纸边角，薄白手背下的浅青血管与淡粉圆润指甲清晰入眼。徐志北指节不自觉收紧，视线在她细白的腕骨上多停了两秒才压下胸口那丝发闷的躁动。"
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
            "玄关门在身后轻合，周三夜九点的顶层公寓安静得只听见空调低鸣，刚洗完澡的沐浴露甜香裹着暖意扑了满怀。"
            "苏婉青坐在沙发外侧，浅黄碎花吊带睡裙的细肩带在冷白肩头压出浅浅印痕，胸前抽褶被丰盈的 36D 撑出饱满惊人的弧度，微微一俯身领口便松出一寸深邃雪白阴影；"
            "茶几上温水渐凉，杂志角露出半张手写便签。徐志北站在半步外，掌心莫名发烫，吞咽声在寂静客厅里显得格外清晰。"
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
            "周五傍晚五点的晚风裹着甜暖淡香水扑进主宅玄关，苏婉青刚把沉甸甸的点心礼袋搁上边几，被提绳勒红的细腕还微微发抖。"
            "她一身浅黄细肩带修身短裙外搭宽松白开衫，微弯腰放袋的刹那，开衫领口向两侧滑开，蕾丝抽褶下 36D 的饱满起伏与纤细腰线形成极勾眼的胸腰差，白皙锁骨率先漫开薄红；"
            "徐志北从楼梯转角步下，迎面撞进那股温软馨香里，脚步微滞，下意识放轻了呼吸。"
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
            "瓷壶倾出热茶的清响散在周日午间餐厅里，茶雾混着三道截然不同的气息——沈知韫的冷调幽兰香、徐念薇指间的淡皂香，还有苏婉青走近时拂过的暖甜香水。"
            "桌沿下，穿淡紫缎面居家服的沈知韫脚尖轻搭拖鞋露出白皙足背；较远一侧徐念薇修长冷白的手指扣着骨瓷杯耳，腕骨清瘦；"
            "依周日惯例赴宅的苏婉青俯身搁下伴手礼，浅黄短裙领口被 36D 撑得微紧。徐志北端杯的手指被杯壁烫得微麻，目光掠过三人，胸口暗涌起一层压不住的灼热。"
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
            "周四下午四点半，雷阵雨刚歇的湿凉水汽漫上二楼阳台，袖口沾了一层细潮，檐角滴水声清脆。"
            "提前回宅换上淡紫细肩带缎面居家服的沈知韫背对玻璃门站着，盘发下露出一截细腻白皙的后颈与耳后肌肤，薄纱开衫贴着湿风勾出柔韧腰线；"
            "往下看去，她露趾拖鞋里的脚踝纤细微白，脚趾因地面微凉轻轻蜷起，手机仍紧攥在指间。徐志北贴近门沿，呼吸不自觉变浅，指腹发烫。"
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
            "周日傍晚六点的暮风卷着水彩与松节油微苦气味掠过指尖，侧厅门推开一掌宽，天光暗冷下来。"
            "徐念薇肩头松松搭着薄毯，浅蓝方领长裙露出清瘦锁骨，那双白皙修长的秀手正慢条斯理用棉布拭净画笔，一抹淡蓝颜料蹭在细瘦腕骨边，衬得皮肤越发薄透清冷；"
            "长桌上摊着未干的冷调习作。徐志北靠在门边，目光黏在她指节灵活转动的白皙十指上，嗓子莫名发干。"
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
            "周二上午九点，意式咖啡机嗡鸣渐歇，现磨焦香混着清晨沐浴后的甜润馨香绕在顶层公寓岛台边。"
            "苏婉青只穿一袭浅黄碎花吊带睡裙、脚踩白色蝴蝶结凉拖，微倾身倒咖啡时，细肩带险些滑下圆润肩头，36D 的饱满曲线在晨光里把胸前蕾丝抽褶撑得呼之欲出，起身晃动时起伏比动作慢了半拍；"
            "台面上的手机屏幕刚暗下去。徐志北撑在岛台外侧，掌心贴着冰凉大理石，小腹却隐隐绷紧，话在喉头顿了一瞬。"
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
        '她合上红签简报，摘下无框眼镜轻按眉心，桌下半挂在脚尖的露趾拖鞋轻轻滑落在地毯边，白皙脚背与纤细脚踝彻底露在暖光里。',
        '[低声] 这么晚还没睡？外头冷气大，顺手把门带上，过来陪妈坐会儿。',
    ),
    'nianwei_saturday_studio': (
        '徐念薇',
        '她停下翻检速写本的手，修长冷白的指节合拢封面压住边角，腕骨微微一转把脚边画稿袋往椅下收了半寸，指尖沾着一点未擦净的炭灰。',
        '[克制] 还没睡？别踩到地上的画稿，手怎么那么凉，有事直接说。',
    ),
    'wanqing_apartment_night': (
        '苏婉青',
        '她俯身把茶几上那杯温水往徐志北手边轻推一寸，浅黄吊带领口随动作垂开一道诱人雪白缝隙，指尖撤回时顺手把露出一角的便签按回杂志底下，耳根微微泛红。',
        '[轻声] 这么晚还跑一趟，先坐吧。承邺这周在外地忙，屋里怪冷清的……要我替你换杯热茶吗？',
    ),
    'wanqing_friday_visit': (
        '苏婉青',
        '听见脚步声她回过身，下意识抬起偏凉微汗的手指理了理滑落的白开衫肩线，领口下被 36D 撑开的抽褶随呼吸轻颤，笑意客气又藏着几分局促。',
        '[轻声] 志北，今天也在家呀。我按规矩过来看看妈，顺便带了些她爱吃的点心。',
    ),
    'zhiyun_sunday_noon': (
        '沈知韫',
        '她扫过一圈餐桌，目光在苏婉青手边的伴手礼和念薇修长握杯的手指间掠过，自己拉开主位座椅，脚下露趾拖鞋轻蹭过地毯边沿。',
        '[平静] 都到齐了，先落座吧。厨房那边还要一会儿，志北坐妈手边。',
    ),
    'zhiyun_rain_balcony': (
        '沈知韫',
        '听见身后脚步声，她没有立刻回头，只微微侧脸让开玻璃门内侧避风的位置，晚风吹起薄纱衣摆贴合腰线，盘发下白皙后颈与赤着半截的秀足脚踝格外显眼。',
        '[低声] 雨刚歇，风里还带着潮气。怎么这个点上来找我？',
    ),
    'nianwei_sunday_evening_studio': (
        '徐念薇',
        '她把最后两支画笔插进瓷筒，修长白皙的指腹蹭掉腕骨旁一星蓝灰颜料，拢紧肩头薄毯，隔着长桌冷淡却专注地望了过来。',
        '[克制] 门没锁，进来就行。晚饭前我还要收完这些习作，帮我递一下纸巾？',
    ),
    'wanqing_apartment_morning': (
        '苏婉青',
        '她按停嗡嗡作响的咖啡机，微微俯身把滚烫的骨瓷杯挪到岛台边，碎花睡裙胸前饱满弧度近在咫尺，余光偷瞄了一眼暗下的手机屏幕，锁骨透出浅粉。',
        '[轻声] 早餐再等几分钟就好。你难得上午过来，先喝杯黑咖啡，还是我给你兑点热牛奶？',
    ),
}
OPENING_CHOICES = {
    'zhiyun_friday_study': (
        '顺口问起桌上那份压了红签的并购简报，试探公司与大哥外地项目的近况',
        '搁下温水后蹲身替她拾起滑落的露趾拖鞋，顺势握住她微凉的脚踝替她按揉解乏',
        '反手合上书房门锁隔绝门外，俯身贴近她耳侧低声说她穿这身熬夜实在太让人分神',
    ),
    'nianwei_saturday_studio': (
        '靠在门框边，问起她刚才匆忙合上的速写本与美院青年画展的近况',
        '走近抽了张干纸巾，轻轻握住她偏凉纤细的手腕，替她一点点擦去指节上的炭灰',
        '拉开高脚凳紧挨她坐下，双掌包住她冰凉修长的双手替她暖手，直视她泛红的耳廓',
    ),
    'wanqing_apartment_night': (
        '接过水杯落座，顺着话头打听大哥在外地忙什么，留意杂志下那角便签',
        '伸手替她把滑到臂弯的吊带边沿与薄披肩轻拢稳，指尖擦过她温热微红的锁骨',
        '借着接杯坐到她身侧极近处，嗅着她发间沐浴露甜香，低声笑问她独守空房是不是也寂寞',
    ),
    'wanqing_friday_visit': (
        '迎上前寒暄两句，随口问起她每周五来主宅是不是大哥特意交代的任务',
        '上前接过沉甸甸的礼盒，顺势托稳她被勒红的细腕轻揉两下，贴近帮她理正滑落的开衫肩头',
        '趁大厅无人压低嗓音留住她，贴近她泛红耳畔低语今天怎么穿得这样勾眼，试探她的反应',
    ),
    'zhiyun_sunday_noon': (
        '顺势在母亲身旁落座，聊起大哥外地项目风声，暗中观察三人的细微神色',
        '替母亲斟茶时顺手替她把桌下歪斜的拖鞋拨正，转而递茶给苏婉青时指尖轻擦她微凉手背',
        '借着拿茶点挨近母亲与嫂子之间，先夸母亲气色温润，再含笑压低声线打趣嫂子今日裙子格外合身',
    ),
    'zhiyun_rain_balcony': (
        '走到她身侧半步处，轻声问她今天提前回来是不是公司或并购案出了棘手事',
        '替她把被湿风吹散的薄纱衣角拢稳，蹲下身拿干毛巾替她擦去脚踝与足背沾上的细潮水汽',
        '反手带紧身后的玻璃门隔开走廊，贴近她身后闻着幽兰冷香，低声问她累成这样为什么总硬撑',
    ),
    'nianwei_sunday_evening_studio': (
        '停在长桌对面扫过摊开的冷调习作，问她周末宁可在主宅赶稿也不去画室的缘由',
        '递过擦手巾并顺势托起她细白冰凉的右手，用指腹仔细替她揩净腕骨边那抹蓝灰颜料',
        '反手掩上侧厅门走到她椅后俯身看画，呼吸拂过她散落碎发的后颈，顺手握住她握笔的手',
    ),
    'wanqing_apartment_morning': (
        '靠在岛台边要了杯黑咖啡，漫不经心问起刚才手机是不是大哥又在催问主宅动静',
        '绕过岛台接过滚烫的骨瓷杯，指腹擦过她微汗指尖，顺手替她把快滑落的睡裙细肩带扶回肩头',
        '贴到岛台内侧堵住她收手机的动作，垂眼扫过她晨光下起伏的胸线，低声笑问她平时独居都穿这么清凉吗',
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
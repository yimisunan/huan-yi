# -*- coding: utf-8 -*-
"""
存档开局随机盲盒 V4.6

职责：
  - 随机抽一条「序幕锚点」，只作开局继承，不是每回合填写范本
  - 写入 存档/全局记忆库.txt：
      1) 【人物所在】四行当前坐标（事实）
      2) 第一层【1】单段叙述（时间地点+在场谁+物理现状，一段话写完）
  - 禁止 L1 使用「时间地点：/在场：/事实：」分栏，以免 AI 当成固定输出格式

使用：在项目根目录运行
  python 存档开局随机盲盒.py
"""

from __future__ import annotations

import os
import random
import re
import shutil
from datetime import datetime

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
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周五深夜，徐家主宅二楼书房。冷气过足，并购文件摊在实木桌上。"
            "沈知韫穿着角色设定中的居家服，正在翻阅文件，门半掩，徐志北在场。"
        ),
    },
    {
        "id": "nianwei_saturday_studio",
        "title": "周六凌晨 · 主宅画室 · 姐姐",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周六凌晨，徐家主宅三楼私人画室。只开着冷白补光灯，松节油混着穿堂风。"
            "徐念薇穿着角色设定中的居家服，坐在高脚凳上整理画板，徐志北在场。"
        ),
    },
    {
        "id": "wanqing_apartment_night",
        "title": "周中夜 · 顶层公寓 · 嫂子",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("市中心顶层公寓", "到访"),
        },
        "l1_body": (
            "周三夜里，市中心顶层公寓客厅。落地窗外是夜景，茶几上一杯未动的水。"
            "苏婉青穿着角色设定中的居家服，门已从内侧带上，徐志北在场。"
        ),
    },
    {
        "id": "wanqing_friday_visit",
        "title": "周五傍晚 · 主宅请安 · 嫂子",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("徐家主宅", "周五请安窗"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周五傍晚，徐家主宅一楼起居室。苏婉青穿着角色设定中的外出服，按请安习惯到访，"
            "提袋搁在玄关边几，未作过夜打算，徐志北在场。"
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
            "周日近午，徐家主宅餐厅。家庭午餐尚未开席，沈知韫、徐念薇、苏婉青与徐志北同在。"
            "苏婉青属周日露面到宅，念薇坐在较远一侧，席间礼貌未散。"
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
            "周四16:30，沈知韫下班回到徐家主宅，换好居家服后走到二楼阳台内侧。雷阵雨刚歇，潮气带着泥土腥。"
            "沈知韫穿着角色设定中的居家服，背对玻璃门望向庭院，徐志北在场。"
        ),
    },
    {
        "id": "nianwei_sunday_evening_studio",
        "title": "周日傍晚 · 画室 · 姐姐",
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周日傍晚，徐家主宅三楼画室。天光转冷，画布未完成。"
            "徐念薇擦着笔，薄毯搭在肩上，门开一掌宽，徐志北在场。"
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
            "周二上午，市中心顶层公寓餐厨相连处。咖啡机轻响，窗外是工作日车流。"
            "苏婉青穿着角色设定中的居家服，正在准备早餐，徐志北在场。"
        ),
    },
]


def _resolve_memory_path() -> str | None:
    if os.path.exists(MEMORY_FILE):
        return MEMORY_FILE
    # 兼容旧布局：曾经放在 txt文件/ 或根目录
    for alt in (
        os.path.join(BASE_DIR, "txt文件", "全局记忆库.txt"),
        os.path.join(BASE_DIR, "全局记忆库.txt"),
    ):
        if os.path.exists(alt):
            return alt
    return None


def _format_presence_block(presence: dict) -> str:
    """仅事实行，与 injection_core._format_presence_block 同形。"""
    order = ("沈知韫", "徐念薇", "苏婉青", "徐志北")
    lines = ["【人物所在】"]
    for name in order:
        loc, reason = presence.get(name, ("未知", "未标注"))
        lines.append(f"{name}：{loc} | 事由：{reason}")
    return "\n".join(lines) + "\n"


def _patch_presence(content: str, presence: dict) -> str:
    block = _format_presence_block(presence)
    pattern = re.compile(
        r"【人物所在】[^\n]*\n.*?(?=\n【当前激活微状态】|\n▶ 上回合历史快照|\n={5,}|\n【当前持久化)",
        re.DOTALL,
    )
    if pattern.search(content):
        return pattern.sub(block.rstrip() + "\n", content, count=1)
    # 无区块则插在微状态前
    anchor = "【当前激活微状态】"
    if anchor in content:
        return content.replace(anchor, block + "\n" + anchor, 1)
    return block + "\n" + content


def _patch_layer1(content: str, l1_body: str) -> str:
    """重写第一层为序幕【1】+ 隐藏标记，保留二层及以后。"""
    l1_start = content.find("▲ 第一层：")
    l2_start = content.find("▲ 第二层：")
    if l1_start == -1:
        raise ValueError("未找到 ▲ 第一层：标记")

    body = l1_body.strip()
    # 去掉误带的回合戳
    body = re.sub(r"^【\d+】\s*", "", body)

    # 压成单行段落，去掉误用的分栏换行
    body = re.sub(r"\s*\n\s*", "", body)
    body = re.sub(r"\s{2,}", " ", body).strip()

    new_l1 = (
        "▲ 第一层：【即时运存区】\n"
        f"【1】{body}\n"
        f"{PROLOGUE_MARK}\n\n"
    )

    if l2_start == -1:
        return content[:l1_start] + new_l1
    return content[:l1_start] + new_l1 + content[l2_start:]


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
    with store._locked():
        result = initialize_prologue(store.root, request_id)
    print('序幕已准备：', result['scenario_id'])
    print('打开首页点按开始演播，读完后选择；已有档不会被覆盖。')


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
    'zhiyun_friday_study': ('沈知韫', '她把正在看的文件拢到一旁，抬眼看向门边。', '还没睡？过来坐一会儿。'),
    'nianwei_saturday_studio': ('徐念薇', '她停下整理画板的手，把脚边的一张凳子向外推了推。', '这么晚还没睡。进来吧，小心地上的颜料。'),
    'wanqing_apartment_night': ('苏婉青', '她把茶几上的水杯朝他这边移了些，转身让出沙发旁的位置。', '先坐吧，要不要喝点水？'),
    'wanqing_friday_visit': ('苏婉青', '她放好提袋，听见玄关的动静便回过身来。', '志北，你也在家。今天没出去？'),
    'zhiyun_sunday_noon': ('沈知韫', '她看了一眼餐厅里的人，把手边的座椅拉开。', '都来了，先坐。饭还要等一会儿。'),
    'zhiyun_rain_balcony': ('沈知韫', '她听到身后的脚步声，侧过脸，把靠近玻璃门的位置让开。', '雨停了，外面还有点凉。你找我？'),
    'nianwei_sunday_evening_studio': ('徐念薇', '她把擦过的画笔放回罐里，抬手揉了一下肩。', '进来吧，门没关。我刚准备歇一会儿。'),
    'wanqing_apartment_morning': ('苏婉青', '她关小咖啡机的声音，把台面上一只空杯拿到手边。', '早餐还要一会儿。你想喝什么？'),
}
OPENING_CHOICES = {
    'zhiyun_friday_study': ('问她今晚忙得怎么样', '询问她是否需要搭一把手，再扶稳她递来的文件夹', '主动提出帮她核对一项文件'),
    'nianwei_saturday_studio': ('问她正在整理哪幅画', '问她是否需要扶稳画板', '请她指导自己画一笔基础线条'),
    'wanqing_apartment_night': ('聊起她今天的安排', '征得回应后礼貌地握手致意', '主动提出一起整理茶几'),
    'wanqing_friday_visit': ('问候她并聊起今天的来访', '询问后帮她提好玄关的袋子', '主动提议一起准备晚饭前的茶点'),
    'zhiyun_sunday_noon': ('问问大家最近过得怎么样', '询问后帮家人扶稳餐椅', '主动提出帮忙摆放餐具'),
    'zhiyun_rain_balcony': ('问她今天工作是否顺利', '询问后替她拉好身旁的薄帘', '提出陪她谈谈正在烦心的具体事务'),
    'nianwei_sunday_evening_studio': ('问她画里的景色来自哪里', '询问后帮她扶稳靠墙的画架', '提出请她安排一项入门绘画练习'),
    'wanqing_apartment_morning': ('问问她今天有什么安排', '征得回应后礼貌地握手致意', '主动提出一起准备早餐'),
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
    chosen.update(clock={'day': 1, 'time': clock}, weekday=weekday,
                  messages=[{'kind': 'narration', 'speaker': '', 'text': chosen['l1_body'].replace('穿着角色设定中的居家服', '已经换过居家衣服').replace('穿着角色设定中的外出服', '还穿着出门时的衣服')},
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
    memory = files[rr.FILES[0]].decode()
    if any(engine._parse_memory_layer_items(memory)[k] for k in ('L1', 'L2', 'L3', 'L4')):
        raise rr.ConflictError('已有记忆，不能另抽序幕覆盖')
    memory = _patch_layer1(_patch_presence(memory, chosen['presence']), chosen['l1_body'])
    files[rr.FILES[0]] = memory.encode()
    presence = engine.parse_presence_from_memory(memory)
    ident = 'prologue-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
    runtime = {'version': 1, 'clock': chosen['clock'], 'memory_round': 1,
               'last_closed': 0, 'phase': 'ready', 'item_recovered': 0, 'action_index': 0, 'closed_by': ''}
    data.update(round=1, sceneTitle=presence['徐志北']['location'], presence=presence,
                request_id=ident, state_version=1, options_text='', story_runtime=runtime,
                prologue={'request_id': request_id, 'scenario_id': chosen['id'], 'weekday': chosen['weekday'], 'title': chosen['title']},
                interaction={'count': 1, 'actions': 0, 'last_sequence': 1, 'segment_id': ident},
                storyNodes=[{'type': 'dialogue' if m['kind'] == 'dialogue' else 'narration', 'text': m['text'],
                            **({'speaker': m['speaker']} if m['kind'] == 'dialogue' else {})} for m in chosen['messages']])
    # before_world has the same initial location/time, with no unseen numerical reward.
    temporary = dict(files); temporary['data.json'] = rr._json(data)
    world = ir.view(store, temporary)
    listeners = ['徐志北', *world['cast']]
    row = {'version': 2, 'id': ident, 'sequence': 1, 'count': 1, 'input': '', 'input_kind': 'system',
           'selection': {'segment_id': '', 'option_id': 'BEGIN'}, 'messages': chosen['messages'],
           'decision': chosen['decision'], 'operation': None, 'handoff': '',
           'known_by': listeners, 'input_known_by': ['徐志北'], 'messages_known_by': listeners,
           'location': world['location'], 'after_location': world['location'], 'created_at': 0,
           'cost': {'status': 'active', 'kind': 'prologue', 'total': 0},
           'audit': {'origin': 'registered_prologue', 'scenario_id': chosen['id']}, 'before_world': world}
    files['data.json'] = rr._json(data)
    files[ir.ARCHIVE+'/000000000001.json'] = rr._json(row)
    files[ir.PLAYBACK] = rr._json({'version': 1, 'segment_id': ident, 'revealed': 0, 'completed': False})
    revision = rr._revision(files)
    receipt = {'request_id': ident, 'revision': revision, 'round': 1, 'state_version': 1, 'status': 'committed', 'replayed': False}
    files[rr.META] = rr._json({'version': 1, 'sequence': 1, 'receipts': {ident: {'payload_hash': rr._digest(rr._json(chosen)), 'receipt': receipt}}})
    store._commit_files(files)
    return {'scenario_id': chosen['id'], 'replayed': False}


if __name__ == "__main__":
    print("=======================================")
    print(" 初始锚点随机盲盒 V4.6")
    print(" 驻地合规 · 人物所在 · L1 序幕")
    print("=======================================")
    randomize_start()
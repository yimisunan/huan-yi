# -*- coding: utf-8 -*-
"""
存档开局随机盲盒（P2 自包含存档版 · 10 幕池）

职责：
  - 为空白新档随机抽取或按指定 ID 写入一条合规「序幕锚点」，经 save_store 与 RoundStore 原子落盘
    存档/save_state.json、存档/四层记忆.json、存档/近期演播.json 与单向渲染视图及 data.json
  - 按房间级 present_actors 精确隔离 known_by，杜绝同栋楼门外目击泄密
  - 绝不覆盖已有进度档（如需重开，请运行 存档清理器.py 或在网页端「档案室」操作）

使用：在项目根目录运行
  python3 存档开局随机盲盒.py --list
  python3 存档开局随机盲盒.py --scenario nianwei_rain_studio
  python3 存档开局随机盲盒.py --reroll
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import uuid

try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path(os.getcwd()).resolve()

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# =============================================================================
# 10 幕序幕剧本池（8 幕精修去套词 + 2 幕校外画室/顶层办公室主场）
# 每条自洽：weekday / time / presence / present_actors / sub_location / privacy 全线对齐法典
# =============================================================================
SCENARIOS = [
    {
        "id": "zhiyun_friday_study",
        "title": "周五深夜 · 主宅书房 · 母亲",
        "heroine": "沈知韫",
        "summary": "十一点的书房冷气偏低，桌案堆着深圳对账红签简报，她在暖灯下卸了鞋松着脚踝。",
        "sub_location": "主宅二楼书房",
        "privacy": "semi_open",
        "present_actors": ["沈知韫"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "晚间在家休息"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周五夜里十一点，书房的冷气比走廊低了两度，门推开时纸墨味混着一缕冷调幽兰香扑面落进领口。"
            "暖黄台灯只照着红签简报的一角，实木桌下，沈知韫那只脚踝纤细的白皙秀足正半勾着露趾拖鞋晃了一下，米白交叉带斜垂在足背将落未落；"
            "她身上那件淡紫细肩带缎面居家上衣贴着腰线微收，薄纱开衫随翻页滑下半寸。徐志北端着温水停在门边，指节抵着温热杯壁，呼吸比刚才放慢了半拍。"
        ),
    },
    {
        "id": "nianwei_saturday_studio",
        "title": "周六凌晨 · 主宅北窗 · 姐姐",
        "heroine": "徐念薇",
        "summary": "凌晨一点的二楼北窗下，她在冷白落地灯前整理未收妥的速写本与炭灰画稿。",
        "sub_location": "主宅二楼北窗门廊",
        "privacy": "thin_wall",
        "present_actors": ["徐念薇"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周六凌晨一点，二楼木地板透着凉意，北窗缝里溜进来的风裹着松节油与极淡皂香。"
            "冷白落地灯落在高脚凳上，徐念薇穿着浅蓝方领抽绳居家裙，高丸子头散下几缕碎发贴在冷白后颈；"
            "她那双修长、指节分明的秀手正压着速写本边角，薄白手背下的浅青血管在光里看得一清二楚。徐志北脚步顿在门廊阴影里，视线在她纤瘦腕骨上多停了一瞬。"
        ),
    },
    {
        "id": "wanqing_apartment_night",
        "title": "周中夜 · 顶层公寓 · 嫂子",
        "heroine": "苏婉青",
        "summary": "周三夜九点的顶层公寓安静空旷，刚沐浴完的她独守沙发，杂志下压着半角便签。",
        "sub_location": "公寓客厅沙发",
        "privacy": "semi_open",
        "present_actors": ["苏婉青"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("工作室", "工作日傍晚在画室"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("市中心顶层公寓", "到访"),
        },
        "l1_body": (
            "玄关门在身后扣合，周三夜里九点的顶层公寓安静得只剩空调出风口的轻响，刚沐浴过的暖甜沐浴露香气迎面漫过来。"
            "苏婉青靠在沙发外侧，浅黄碎花吊带睡裙的细肩带在冷白肩头勒出浅痕，胸前抽褶被丰盈的 36D 撑开柔和弧度，一俯身领口便松出一寸微暗的雪白阴影；"
            "茶几上温水渐凉，杂志角下露出半截折着的手写便签。徐志北站在半步外，心跳撞得耳膜发沉，脚步一时没有再往前挪。"
        ),
    },
    {
        "id": "wanqing_friday_visit",
        "title": "周五傍晚 · 主宅请安 · 嫂子",
        "heroine": "苏婉青",
        "summary": "周五请安窗傍晚五点，她拎着点心礼袋立在主宅玄关，开衫微松、面带几分拘谨。",
        "sub_location": "主宅玄关侧厅",
        "privacy": "thin_wall",
        "present_actors": ["苏婉青"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("工作室", "工作日傍晚在画室"),
            "苏婉青": ("徐家主宅", "周五请安窗"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周五傍晚五点，院门外晚风顺着玄关卷进来，带着一缕暖甜淡香水气味。苏婉青刚把沉甸甸的点心礼袋搁上边几，被提绳勒红的细腕还微微收着劲。"
            "她一身浅黄细肩带修身短裙外搭宽松白开衫，弯腰落袋的刹那，开衫领口顺着肩线滑开半寸，蕾丝抽褶下 36D 的饱满起伏与纤细腰线收得很利落，冷白锁骨先泛起一层薄红；"
            "徐志北从楼梯转角步下，恰好与她打了个照面，下意识放轻了脚步。"
        ),
    },
    {
        "id": "zhiyun_sunday_noon",
        "title": "周日午间 · 主宅餐厅 · 家庭",
        "heroine": "全员家宴",
        "summary": "周日家庭午餐窗三美同席，茶雾交织三缕不同香气，闲谈之下各自藏着心事。",
        "sub_location": "主宅餐厅",
        "privacy": "open_public",
        "present_actors": ["沈知韫", "徐念薇", "苏婉青"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("徐家主宅", "周日家庭午餐窗"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "瓷壶倾出热茶的轻响散在周日午间餐厅里，茶雾混着三道截然不同的气息——沈知韫的冷调幽兰、徐念薇指间的淡皂香，以及苏婉青落座时拂过的柔顺甜香。"
            "桌布边沿下，穿淡紫缎面居家服的沈知韫脚尖轻搭拖鞋露出一截白皙足背；另一侧徐念薇修长冷白的手指扣着骨瓷杯耳，腕骨清瘦；"
            "依周日惯例赴宅的苏婉青俯身搁下伴手礼，浅黄短裙领口被 36D 撑得微紧。徐志北指腹被热茶杯壁烫了一下，目光在三人神色间掠过。"
        ),
    },
    {
        "id": "zhiyun_rain_balcony",
        "title": "周四雨后 · 主宅阳台 · 母亲",
        "heroine": "沈知韫",
        "summary": "周四下午四点半，她刚下班回宅换好居家服，独自站在雨后湿凉的二楼阳台握着手机。",
        "sub_location": "主宅二楼阳台",
        "privacy": "semi_open",
        "present_actors": ["沈知韫"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周四下午四点半，急雨刚歇的湿凉水汽漫上二楼阳台，檐角滴水敲在栏杆上清脆有声。"
            "刚从公司下班回宅、换上淡紫细肩带缎面居家服的沈知韫背对玻璃门站着，盘发下露出一截白皙后颈与耳后肌肤，湿风把薄纱开衫贴在腰线上；"
            "她露趾拖鞋里的纤细脚踝微白，脚趾因地砖微凉轻轻蜷起，手机仍攥在指间没有锁屏。徐志北推开半扇玻璃门，袖口沾上细潮，呼吸一时放轻。"
        ),
    },
    {
        "id": "nianwei_sunday_evening_studio",
        "title": "周日傍晚 · 主宅露台侧厅 · 姐姐",
        "heroine": "徐念薇",
        "summary": "周日傍晚六点暮光渐沉，她在侧厅赶收冷调水彩习作，腕骨边蹭着一星蓝灰颜料。",
        "sub_location": "主宅露台侧厅",
        "privacy": "semi_open",
        "present_actors": ["徐念薇"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("徐家主宅", "周末在家"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("徐家主宅", "常住"),
        },
        "l1_body": (
            "周日傍晚六点，暮风卷着水彩与松节油微苦的气味掠过侧厅半掩的木门，窗外天光一点点沉成冷灰。"
            "徐念薇肩头松松搭着薄毯，浅蓝方领长裙露出清瘦锁骨，那双白皙修长的秀手正慢条斯理拿棉布拭净画笔，一抹淡蓝颜料蹭在细瘦腕骨边，衬得皮肤格外薄透；"
            "长桌上摊着未干的冷调习作。徐志北靠在门沿，听见画笔轻碰瓷筒的细响，目光落在她灵活转动的冷白指节上。"
        ),
    },
    {
        "id": "wanqing_apartment_morning",
        "title": "工作日上午 · 顶层公寓 · 嫂子",
        "heroine": "苏婉青",
        "summary": "周二上午九点，咖啡香漫过公寓岛台，只穿碎花吊带睡裙的她刚按暗屏幕上的来讯。",
        "sub_location": "公寓开放式岛台",
        "privacy": "semi_open",
        "present_actors": ["苏婉青"],
        "presence": {
            "沈知韫": ("公司", "工作日上班中"),
            "徐念薇": ("大学", "工作日在大学"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("市中心顶层公寓", "到访"),
        },
        "l1_body": (
            "周二上午九点，意式咖啡机低鸣渐歇，现磨焦香混着清晨沐浴露的暖甜气息散在顶层公寓岛台边。"
            "苏婉青只穿一袭浅黄碎花吊带睡裙、脚踩白色蝴蝶结凉拖，微倾身倒咖啡时细肩带滑到圆润肩沿，36D 的饱满曲线在晨光里撑开胸前蕾丝抽褶；"
            "大理石台面上的手机屏幕恰好暗下去。徐志北单手撑在冰凉台沿，话在嘴边顿了一瞬才压下心头那股发紧的躁意。"
        ),
    },
    {
        "id": "nianwei_rain_studio",
        "title": "周四雨夜 · 校外画室 · 姐姐",
        "heroine": "徐念薇",
        "summary": "周四晚八点半暴雨敲窗，校外画室只亮一盏暖黄射灯，角落藏着蒙布的旧画框。",
        "sub_location": "校外私人画室",
        "privacy": "semi_open",
        "present_actors": ["徐念薇"],
        "presence": {
            "沈知韫": ("徐家主宅", "常住"),
            "徐念薇": ("工作室", "工作日傍晚在画室备展"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("工作室", "雨夜来送伞看望"),
        },
        "l1_body": (
            "周四晚八点半，暴雨把老街巷口敲出一片白雾，推开校外画室的木门，浓冽的松节油混着雨腥味立刻涌上来。"
            "头顶只有一盏暖黄射灯罩着画架，徐念薇穿浅蓝高领复古长裙、外系沾了群青颜料的棉麻围裙，高丸子头散落两缕湿发贴在冷白后颈，正用修长指节拧开画颜料管；"
            "墙角立着一幅蒙了旧亚麻布的大号画框。徐志北收起滴水的雨伞靠在门边，指尖蹭着微凉伞柄，屋里只剩雨声和画刀刮过木板的轻响。"
        ),
    },
    {
        "id": "zhiyun_late_office",
        "title": "周三晚间 · 顶层办公室 · 母亲",
        "heroine": "沈知韫",
        "summary": "周三晚七点半总部整层清场，玻璃幕墙映着夜色，她卸下细跟鞋独自复核并购风控件。",
        "sub_location": "顶层董事长办公室",
        "privacy": "locked_private",
        "present_actors": ["沈知韫"],
        "presence": {
            "沈知韫": ("公司", "周三晚间加班复核并购案"),
            "徐念薇": ("工作室", "工作日傍晚在画室"),
            "苏婉青": ("市中心顶层公寓", "常住"),
            "徐志北": ("公司", "晚间送夜宵探班"),
        },
        "l1_body": (
            "周三晚七点半，集团总部顶层早已清场，走廊灯暗了一半，只有董事长办公室的落地玻璃幕墙映着城央灯火。"
            "沈知韫仍穿着收腰白衬衫与黑色高腰包臀短裙，宽大办公桌下，那双被超薄黑丝包裹的纤细脚踝刚从黑色尖头细跟后空鞋里褪出半截，足背绷着舒缓一天的酸胀；"
            "案头摊着标有风控红签的并购文件夹。徐志北提着温热的汤盅轻推开门，反手带上门扉的咔哒声在静谧空间里格外清晰。"
        ),
    },
]


# Explicit game-time anchors for all 10 scenarios; no wall-clock date is used.
OPENING_TIMES = {
    'zhiyun_friday_study': ('周五', '23:00'),
    'nianwei_saturday_studio': ('周六', '01:00'),
    'wanqing_apartment_night': ('周三', '21:00'),
    'wanqing_friday_visit': ('周五', '17:00'),
    'zhiyun_sunday_noon': ('周日', '11:50'),
    'zhiyun_rain_balcony': ('周四', '16:30'),
    'nianwei_sunday_evening_studio': ('周日', '18:00'),
    'wanqing_apartment_morning': ('周二', '09:00'),
    'nianwei_rain_studio': ('周四', '20:30'),
    'zhiyun_late_office': ('周三', '19:30'),
}

OPENING_LINES = {
    'zhiyun_friday_study': (
        '沈知韫',
        '她合上红签简报，摘下无框眼镜轻按眉心，桌下半挂在脚尖的露趾拖鞋滑落在地毯边，白皙脚背与纤细脚踝露在暖灯下。',
        '[低声克制，带着点倦意] 这么晚还没睡？外头冷气大，顺手把门带上，过来陪妈坐会儿。',
    ),
    'nianwei_saturday_studio': (
        '徐念薇',
        '她停下翻检速写本的手，冷白指节合拢封面压住边角，顺手把脚边画稿袋往椅下收了半寸，指尖沾着一点未擦净的炭灰。',
        '[清冷平淡，声音压轻] 还没睡？别踩到地上的画稿，这么晚下来有事直说。',
    ),
    'wanqing_apartment_night': (
        '苏婉青',
        '她俯身把茶几上那杯温水往徐志北手边轻推一寸，浅黄吊带领口随动作微微垂松，指尖撤回时顺手把露出一角的便签按回杂志底下，耳根透出一抹浅粉。',
        '[声音轻柔，略微拘谨] 这么晚还跑一趟，先坐吧。承邺这周在外地忙，屋里怪冷清的……<soft>要我替你换杯热茶吗？</soft>',
    ),
    'wanqing_friday_visit': (
        '苏婉青',
        '听见脚步声她回过身，下意识抬起偏凉的手指理了理滑落的白开衫肩线，领口下被 36D 撑开的抽褶随呼吸轻动，笑意客气又藏着几分局促。',
        '[声音轻柔，带点客套分寸] 志北，今天也在家呀。我按规矩过来看看妈，顺便带了些她爱吃的点心。',
    ),
    'zhiyun_sunday_noon': (
        '沈知韫',
        '她扫过一圈餐桌，目光在苏婉青手边的伴手礼和念薇握杯的手指间掠过，自己拉开主位座椅，脚下露趾拖鞋轻蹭过地毯边沿。',
        '[沉稳从容] 都到齐了，先落座吧。厨房那边还要一会儿，志北坐妈手边。',
    ),
    'zhiyun_rain_balcony': (
        '沈知韫',
        '听见身后脚步声，她没有立刻回头，只微微侧身让开玻璃门内侧避风的位置，晚风吹起薄纱衣摆贴合腰线，盘发下白皙后颈映着灰蓝雨天光影。',
        '[低声克制，语速微缓] 雨刚歇，风里还带着潮气。怎么这个点上来找我？',
    ),
    'nianwei_sunday_evening_studio': (
        '徐念薇',
        '她把最后两支画笔插进瓷筒，冷白指腹蹭掉腕骨旁一星蓝灰颜料，拢紧肩头薄毯，隔着长桌淡淡望了过来。',
        '[清冷克制，字句干净] 门没锁，进来就行。晚饭前我还要收完这些习作，帮我递一下纸巾？',
    ),
    'wanqing_apartment_morning': (
        '苏婉青',
        '她按停低鸣的咖啡机，微微俯身把滚烫的骨瓷杯挪到岛台边，碎花睡裙胸前饱满弧度近在咫尺，余光扫了一眼暗下的手机屏幕。',
        '[声音轻柔，带着几分试探] 早餐再等几分钟就好。你难得上午过来，先喝杯黑咖啡，还是我给你兑点热牛奶？',
    ),
    'nianwei_rain_studio': (
        '徐念薇',
        '她拧紧颜料盖搁进木盘，偏头看了一眼徐志北滴水的雨伞，转身把墙角蒙布滑开一角的大画框重新扯平压实。',
        '[声音平淡，带着一丝意外] 下这么大雨怎么跑这儿来了？<soft>伞搁门后那只铁桶里，别把颜料弄湿了。</soft>',
    ),
    'zhiyun_late_office': (
        '沈知韫',
        '她合上并购风控红签夹，把桌上冷掉的咖啡往旁边一推，桌下黑丝脚尖顺势重新勾回细跟后空鞋，抬眼时掌权者的冷锐柔和了半分。',
        '[低声克制，带着难得的松弛] 这层早就没人了，怎么还专程跑一趟？<soft>先搁茶几上，坐下歇口气。</soft>',
    ),
}

# 全部 10 幕 Option B 严格遵守日常态 lore.命名锁（礼仪/照料/递物/协作接触，零越界擦边）；Option C 承载高张力与成人试探
OPENING_CHOICES = {
    'zhiyun_friday_study': (
        '顺口问起桌上那份压了红签的并购简报，试探公司与大哥外地项目的近况',
        '把温水放到她右手边，顺手帮她把披在椅背上的薄针织披肩搭稳肩头并递过热毛巾',
        '反手带上书房门锁隔绝门外，蹲身替她拾起滑落的拖鞋时指腹故意缓停在她微凉足背上',
    ),
    'nianwei_saturday_studio': (
        '靠在门框边，问起她刚才匆忙合上的速写本与美院青年画展的近况',
        '抽两张干纸巾递到她手里，顺手帮她把脚边散落的画稿袋提稳放回桌角',
        '拉开高脚凳紧挨她坐下，直接扣住她偏凉纤细的手腕擦净指节炭灰，迫使她抬头对视',
    ),
    'wanqing_apartment_night': (
        '接过水杯落座，顺着话头打听大哥在外地忙什么，留意杂志下那角便签',
        '接过温水时礼貌道谢，顺手把沙发边折好的羊绒披肩递给她挡一挡空调冷风',
        '借着接杯坐到她身侧极近处，指尖擦过她温热锁骨帮她拢吊带，低声笑问她独守空房是不是寂寞',
    ),
    'wanqing_friday_visit': (
        '迎上前寒暄两句，随口问起她每周五来主宅是不是大哥特意交代的任务',
        '上前替她接过沉甸甸的点心礼袋提进客厅，顺手递过一张纸巾让她擦擦微汗指尖',
        '趁侧厅无人压低嗓音留住她，贴近她泛红耳畔低语今天裙子太勾眼，顺势揽住她纤细手腕试探',
    ),
    'zhiyun_sunday_noon': (
        '顺势在母亲身旁落座，聊起大哥外地项目风声，暗中观察三人的细微神色',
        '接过茶壶依次替母亲、姐姐和嫂子斟好热茶，顺手替母亲把餐巾铺整到桌沿',
        '落座在母亲与嫂子之间，先笑赞母亲气色温润，桌下却借挪椅微蹭过她丝滑脚踝边沿试探反应',
    ),
    'zhiyun_rain_balcony': (
        '走到她身侧半步处，轻声问她今天在公司是不是又遇到棘手的账目或并购分歧',
        '从室内取来一条干毛巾与薄披肩递过去，顺手帮她把阳台玻璃门掩小挡住穿堂湿风',
        '反手扣紧身后的玻璃门隔开走廊，贴近她白皙后颈嗅着幽兰冷香，低声问她为什么总在人前硬撑',
    ),
    'nianwei_sunday_evening_studio': (
        '停在长桌对面扫过摊开的冷调习作，问她周末宁可在主宅赶稿也不去画室的缘由',
        '抽出几张干纸巾递给她，顺手帮她扶稳桌上险些滑落的调色瓷碟与画笔筒',
        '反手掩上侧厅门走到她椅后俯身看画，呼吸拂过她散落碎发的后颈，直接握住她沾着颜料的冷白手腕',
    ),
    'wanqing_apartment_morning': (
        '靠在岛台边要了杯黑咖啡，漫不经心问起刚才手机是不是大哥又在催问主宅动静',
        '绕到岛台侧边接过滚烫的骨瓷杯，顺手帮她端起一旁的吐司碟与牛奶壶摆上餐垫',
        '贴到岛台内侧挡住她收手机的退路，垂眼扫过晨光下起伏的胸线，指尖轻勾她滑落的吊带笑问独居日常',
    ),
    'nianwei_rain_studio': (
        '把雨伞立在门边，目光转向墙角那幅蒙着旧亚麻布的大画框，问她青年画展近况',
        '递过随手带的热姜茶纸杯与干毛巾，帮她把窗边被雨气打湿的素描纸挪到干燥木桌上',
        '顺手拨上画室木门的暗闩隔绝外面雨声，贴近画架握住她微凉修长的十指低声追问旧画里藏了谁',
    ),
    'zhiyun_late_office': (
        '拉开办公桌对面的椅子坐下，把夜宵推过去，借机探问桌上那份并购风控红签的症结',
        '打开保温汤盅替她盛出一碗热汤递到手边，顺手把凉透的咖啡端开腾出桌面',
        '反手按下办公室电动百叶与门锁开关，绕到宽大办公桌后方低身贴近她耳侧，夸她深夜穿黑丝加班太惹眼',
    ),
}

# 差异化首环委托：按 10 幕主题自然分配 积分 / 商业嗅觉 / 对应女主好感（均严格高于初始面板值）
OPENING_TASKS = {
    'zhiyun_friday_study': {
        'title': '深夜灯下',
        'target': '系统宿主',
        'attr': '商业嗅觉',
        'value': 4,
        'tier': 'small',
        'item_desc': '素银云纹书签',
    },
    'nianwei_saturday_studio': {
        'title': '北窗微光',
        'target': '徐念薇',
        'attr': '好感',
        'value': 87,
        'tier': 'small',
        'item_desc': '便携炭笔素描本',
    },
    'wanqing_apartment_night': {
        'title': '夜色初叙',
        'target': '苏婉青',
        'attr': '好感',
        'value': 43,
        'tier': 'small',
        'item_desc': '手作安神香囊',
    },
    'wanqing_friday_visit': {
        'title': '主宅请安',
        'target': '苏婉青',
        'attr': '好感',
        'value': 42,
        'tier': 'small',
        'item_desc': '釉白瓷小茶匙',
    },
    'zhiyun_sunday_noon': {
        'title': '同席家宴',
        'target': '系统宿主',
        'attr': '积分',
        'value': 6,
        'tier': 'small',
        'item_desc': '银杏叶金属餐巾扣',
    },
    'zhiyun_rain_balcony': {
        'title': '雨歇微凉',
        'target': '沈知韫',
        'attr': '好感',
        'value': 97,
        'tier': 'small',
        'item_desc': '细棉格子手帕',
    },
    'nianwei_sunday_evening_studio': {
        'title': '暮色收笔',
        'target': '徐念薇',
        'attr': '好感',
        'value': 87,
        'tier': 'small',
        'item_desc': '亚麻画稿收纳袋',
    },
    'wanqing_apartment_morning': {
        'title': '晨间破冰',
        'target': '系统宿主',
        'attr': '积分',
        'value': 5,
        'tier': 'small',
        'item_desc': '手冲咖啡滤纸礼盒',
    },
    'nianwei_rain_studio': {
        'title': '雨夜画室',
        'target': '徐念薇',
        'attr': '好感',
        'value': 87,
        'tier': 'small',
        'item_desc': '黄铜调色画刀套组',
    },
    'zhiyun_late_office': {
        'title': '顶层夜灯',
        'target': '系统宿主',
        'attr': '商业嗅觉',
        'value': 6,
        'tier': 'small',
        'item_desc': '磨砂金属名片夹',
    },
}


def _validate_scenario(sc: dict) -> None:
    p = sc["presence"]
    for name in ("沈知韫", "徐念薇", "苏婉青", "徐志北"):
        if name not in p:
            raise ValueError(f"剧本 {sc['id']} 缺少 presence: {name}")
    loc, reason = p["苏婉青"]
    if re.search(r"主宅|别墅|徐家", loc) and not re.search(
        r"请安|午餐|周日|周五|看望|家宴|叫来|指令", reason
    ):
        raise ValueError(f"剧本 {sc['id']} 苏婉青在主宅但事由不像看望窗: {reason}")
    player_loc = p["徐志北"][0]
    for actor in sc.get("present_actors") or []:
        if actor not in p or p[actor][0] != player_loc:
            raise ValueError(f"剧本 {sc['id']} present_actors({actor}) 与主角地点({player_loc})不符")


def list_scenarios() -> list[dict]:
    """Return frontend/CLI-friendly metadata cards for all 10 opening scenarios."""
    cards = []
    for sc in SCENARIOS:
        _validate_scenario(sc)
        weekday, clock_time = OPENING_TIMES[sc['id']]
        cards.append({
            'id': sc['id'],
            'title': sc['title'],
            'heroine': sc.get('heroine', ''),
            'location': sc['presence']['徐志北'][0],
            'sub_location': sc.get('sub_location', ''),
            'weekday': weekday,
            'time': clock_time,
            'summary': sc.get('summary', ''),
            'privacy': sc.get('privacy', 'open_public'),
            'present_actors': list(sc.get('present_actors') or []),
        })
    return cards


def choose_opening(request_id, scenario_id=None):
    """Return a deterministic projection of the scenario pool, without writing files."""
    if not isinstance(request_id, str) or not request_id:
        raise ValueError('序幕须有稳定新档编号')
    pool = list(SCENARIOS)
    for scenario in pool:
        _validate_scenario(scenario)
    if scenario_id is not None and scenario_id != 'random':
        chosen = next((s for s in pool if s['id'] == scenario_id), None)
        if chosen is None:
            raise ValueError('序幕场景未登记：' + str(scenario_id))
    else:
        chosen = random.Random(int(hashlib.sha256(request_id.encode()).hexdigest(), 16)).choice(pool)
    chosen = copy.deepcopy(chosen)
    weekday, clock = OPENING_TIMES[chosen['id']]
    speaker, action, line = OPENING_LINES[chosen['id']]
    starter_task = copy.deepcopy(OPENING_TASKS[chosen['id']])
    chosen.update(
        clock={'day': 1, 'time': clock},
        weekday=weekday,
        starter_task=starter_task,
        messages=[
            {'kind': 'narration', 'speaker': '', 'text': chosen['l1_body']},
            {'kind': 'action', 'speaker': speaker, 'text': action},
            {'kind': 'dialogue', 'speaker': speaker, 'text': line},
        ],
        decision={
            'prompt': '此刻，你准备怎么回应？',
            'options': [{'id': k, 'text': text} for k, text in zip(('A', 'B', 'C'), OPENING_CHOICES[chosen['id']])],
        },
    )
    return chosen


def initialize_prologue(root, request_id, scenario_id=None):
    """Caller holds the shared RoundStore lock, inside a new-game reset transaction."""
    import interaction_runtime as ir
    import round_runtime as rr
    import save_store
    import story_progression as sp

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
    st['director']['scene_location'] = st['presence']['徐志北']['location']
    st['director']['last_time_slot'] = sp._clock_time_slot(chosen['clock'])
    # 房间级在场人与隐私隔离：避免同栋楼门外未入室角色混入 known_by
    present_actors = list(chosen.get('present_actors') or [])
    intl = st.setdefault('intimate', save_store.default_intimate())
    intl['privacy'] = chosen.get('privacy', 'open_public')
    intl['sub_location'] = chosen.get('sub_location', '')
    intl['present_actors'] = list(present_actors)
    intl['scene_active'] = False
    intl['session_beats'] = 0
    intl['noise_risk'] = 0

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
    runtime = {
        'version': 1, 'clock': chosen['clock'], 'memory_round': 1,
        'last_closed': 0, 'phase': 'ready', 'item_recovered': 0, 'action_index': 0, 'closed_by': '',
    }
    prologue_meta = {
        'request_id': request_id,
        'scenario_id': chosen['id'],
        'weekday': chosen['weekday'],
        'title': chosen['title'],
        'heroine': chosen.get('heroine', ''),
        'sub_location': chosen.get('sub_location', ''),
        'privacy': chosen.get('privacy', 'open_public'),
    }
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
    data.update(
        round=1,
        sceneTitle=presence['徐志北']['location'],
        presence=presence,
        request_id=ident,
        state_version=1,
        options_text='',
        story_runtime=runtime,
        prologue=prologue_meta,
        interaction={'count': 1, 'actions': 0, 'last_sequence': 1, 'segment_id': ident},
        storyNodes=[
            {'type': 'dialogue' if m['kind'] == 'dialogue' else 'narration', 'text': m['text'],
             **({'speaker': m['speaker']} if m['kind'] == 'dialogue' else {})}
            for m in chosen['messages']
        ],
    )
    building_cast = [
        name for name in ('沈知韫', '苏婉青', '徐念薇')
        if presence.get(name, {}).get('location') == presence['徐志北']['location']
    ]
    room_cast = [a for a in present_actors if a in building_cast] or building_cast
    listeners = ['徐志北', *room_cast]
    if (layers.get('layers') or {}).get('L1'):
        layers['layers']['L1'][0]['known_by'] = list(listeners)
    rendered_files = save_store.render_bundle_bytes(st, layers, data_dict=data)
    for rel, raw_b in rendered_files.items():
        files[rel] = raw_b
    temporary = dict(files)
    temporary['data.json'] = rr._json(data)
    world = ir.view(store, temporary)
    row = {
        'version': 2, 'id': ident, 'sequence': 1, 'count': 1, 'input': '', 'input_kind': 'system',
        'selection': {'segment_id': '', 'option_id': 'BEGIN'}, 'messages': chosen['messages'],
        'decision': chosen['decision'], 'operation': None, 'handoff': '',
        'known_by': listeners, 'input_known_by': ['徐志北'], 'messages_known_by': listeners,
        'location': world['location'], 'after_location': world['location'], 'created_at': 0,
        'cost': {'status': 'active', 'kind': 'prologue', 'total': 0},
        'audit': {'origin': 'registered_prologue', 'scenario_id': chosen['id']},
        'before_world': world,
    }
    pb_obj = {'version': 1, 'segment_id': ident, 'revealed': 0, 'completed': False}
    files['data.json'] = rr._json(data)
    files[ir.ARCHIVE + '/000000000001.json'] = rr._json(row)
    files[ir.PLAYBACK] = rr._json(pb_obj)
    files[rr.RECENT_PLAYBACK] = rr._json(save_store.append_recent_segment(save_store.default_recent(), row, playback_state=pb_obj))
    revision = rr._revision(files)
    receipt = {'request_id': ident, 'revision': revision, 'round': 1, 'state_version': 1, 'status': 'committed', 'replayed': False}
    files[rr.META] = rr._json({'version': 1, 'sequence': 1, 'receipts': {ident: {'payload_hash': rr._digest(rr._json(chosen)), 'receipt': receipt}}})
    store._commit_files(files)
    return {'scenario_id': chosen['id'], 'replayed': False}


def randomize_start(seed: int | None = None, *, scenario_id: str | None = None, reroll: bool = False, port: int | None = None) -> int:
    """Initialize an empty save (or reroll a 0-action prologue) safely; never overwrite an active playthrough."""
    import importlib.util
    import round_runtime as rr

    spec = importlib.util.spec_from_file_location('_cleaner_helper', BASE_DIR / '存档清理器.py')
    cleaner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cleaner)
    if cleaner.server_running(port=port):
        print('❌ 本地服务正在运行，请先停止服务或在网页端「档案室」中操作。')
        return 1

    request_id = 'manual-opening-' + (str(seed) if seed is not None else uuid.uuid4().hex)
    store = rr.RoundStore(BASE_DIR)
    try:
        with store._locked():
            if reroll:
                files = store._files()
                data = json.loads(files.get('data.json') or b'{}')
                actions = int((data.get('interaction') or {}).get('actions') or 0)
                if actions > 0:
                    raise rr.ConflictError(f'当前存档已有 {actions} 次正式行动，禁止直接重摇；请使用 存档清理器.py 重开')
                cleaner._reset_files(BASE_DIR, keep_backup=False, request_id=request_id, scenario_id=scenario_id)
                new_data = json.loads(store._files().get('data.json') or b'{}')
                sid = (new_data.get('prologue') or {}).get('scenario_id')
                print('✅ 已免费重摇序幕：', sid)
                return 0
            result = initialize_prologue(store.root, request_id, scenario_id=scenario_id)
        print('✅ 序幕已准备：', result['scenario_id'])
        print('打开首页点按开始演播，读完后选择；已有档不会被覆盖。')
        return 0
    except (rr.ConflictError, ValueError, RuntimeError) as exc:
        print('提示：', str(exc))
        print('如需重新开局，请运行 `python3 存档清理器.py` 或在网页端打开「档案室」。')
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='深渊天平 · 10幕序幕盲盒/自选初始化工具（P2 自包含存档版）')
    parser.add_argument('--list', action='store_true', help='列出全部 10 个开局场景卡片')
    parser.add_argument('--scenario', default=None, help='指定开局场景 ID（不传或 random 为盲盒随机）')
    parser.add_argument('--seed', type=int, default=None, help='指定确定性随机种子')
    parser.add_argument('--reroll', action='store_true', help='仅在当前尚未产生正式行动（actions==0）时免费重摇/切换序幕')
    parser.add_argument('--port', type=int, default=None, help='本地服务检测端口（默认 STORY_PORT 或 5000）')
    args = parser.parse_args(argv)
    if args.list:
        cards = list_scenarios()
        print(f'【深渊天平 · 序幕剧本池（共 {len(cards)} 幕）】')
        for idx, c in enumerate(cards, 1):
            print(f"  {idx:02d}. {c['id']:30s} | {c['title']} ({c['location']} · {c['weekday']} {c['time']})")
            print(f"      {c['summary']}")
        return 0
    print('=======================================')
    print(' 初始锚点开局工具（P2 自包含存档 · 10 幕池）')
    print('=======================================')
    return randomize_start(seed=args.seed, scenario_id=args.scenario, reroll=args.reroll, port=args.port)


if __name__ == "__main__":
    sys.exit(main())
【步骤编号】step_14
【上游依赖】logs/step_13.md，SHA256 91a8c678377515991609201785a2cc8a0961470d4993ca2d890c51bbeb10d75e；用户确认“可行流畅”后批准旧存档只读隔离导入、B状态接入与一致性/恢复验证。
【做了什么】完成旧存档不可变隔离版本、来源原文/指纹与待确认项，B页查看状态并按存档同地人物开启交流，资料包按知情范围接入旧记忆及对应状态。
【产物】scene_world.py；scene_chat.py；src/legacy_visibility.json；src/scene_live/{index.html,live.js,live.css,README.md}；tests/test_world.py；txt文件/场景交流规范.md；src/旧存档隔离接入说明.md；接入计划、开发者说明书及本月修订日志；logs/step_14_baseline.json与step_14_checks.json。运行导入位于.scene-chat/world/state.sqlite3，已排除自动同步。
【验收证据】
V1 改前基线：现场pwd=/storage/emulated/0/互动对话项目/Gemini网页版，realpath=/sdcard/互动对话项目/Gemini网页版。step_14_baseline.json记录8份已有文件大小、mtime/SHA256及唯一父版最终路径，另记录4份旧源指纹。父版字节校验后归档，不复制多份。
V2 改后结果：
- 当前真实旧源只读导入world_id=1e5c3510c3acc14384277ca474564a8d8f71eb4c8733769611dce715f8c10462，world_revision=1、旧round=1。人物所在4份、面板5份、记忆1条；道具/任务/真实NPC为空，待确认0。“林秘书”范例未导入登记。四源与V1逐字节SHA256一致。
- 同源重复导入返回同ID/同版本；全新Python进程重开恢复同ID/版本/记忆。所有四源、实体登记与知情映射原文存BLOB，payload、manifest及原文指纹读取时校验；同SQLite事务保存，无旧源写入。
- PYTHONPATH=scene_chat_dev/tmp/tmp_flask_deps python scene_chat_dev/tests/test_world.py：Ran 12 tests in 6.085s / OK / exitCode=0。覆盖实际字段及来源、相同导入/新进程恢复、未知知情不传播、旧源变化/位置冲突/回合错位拒绝、未恢复旧事务不代恢复、损坏原文拒绝、道具旧单位/NPC范例边界、未识别条目保留、世界绑定包/重复结果只入一次、API同源约束。
- python scene_chat_dev/tests/test_read_truncation.py：Ran 9 tests in 0.537s / OK / exitCode=0。修复新模块提前依赖旧引擎的问题，旧实验不必加载旧源。test_live.py与test_transactions.py在首次定向执行已PASS：typed_messages/8例非法拒绝、覆盖、幂等、恢复、查询、路由、租约、源变化/5例非法拒绝。未对这两份已通过检查无依据重跑。Python AST和最终node --check live.js通过。
- 浏览器使用临时副本/临时Flask服务及实际候选静态文件，端口由系统分配40681；375×812、812×375同源iframe通过状态/原文展示、按存档与沈知韫在徐家主宅建立revision0场景、刷新恢复同场景、源变化禁发保留历史、显式重导入版本2。按钮最小高度44px，状态弹窗无横向溢出。顶层viewport=[0,0]，证据只代表iframe，未检验真机键盘。无模型请求。
- 最新只读5000连接仍scene_protocol=3、桥接1.5.0，无world_state_protocol，现役尚未加载本轮新接口；需要Pydroid重启。用户苏婉青原实验场景已revision=5，本次仅只读核对ID/计数/任务状态，没有读取新剧情或写交流库，也未把实验记录导入世界。
- 8份父版与13份交付重读/指纹验证通过；运行目录复用既有同步排除，限额未改。真实模型与TTS调用0。
V3 反向可行：8份父版在开发者功能/归档/项目清理/历史修改备份内，逐一SHA256与V1一致。下列单命令可恢复覆盖文件，未为演练覆盖当前通过实现。
【故障与预算】首轮UI定位空白不符中止后恢复HTML，后续浏览器发现部分绑定未插入，已改唯一锚点；维护终端无Flask/pip，使用PyPI官方文件SHA256核验后临时解压到排除同步的tmp；首版模块即时加载旧引擎导致1项既有回归失败，按需加载后9项全通过；临时固定端口占用后改系统分配。源码组检查超过默认两组预算，理由为真实失败修正、用户要求的实际导入/新进程/浏览器恢复验证；未扩至全仓库测试或收费探针。完整结构化结果在step_14_checks.json。
【清理】临时服务会话415bf0df-3c78-4a8d-9c19-2411a93ce198及失败启动会话545fb2a4-0017-478e-88ab-e719d96a37ae已关闭；浏览器返回5000入口。收尾删除本步tmp_脚本、Flask依赖与浏览器副本，只保留预先存在fix_wire.py。保留实际隔离世界账本。根目录仅新增授权scene_world.py；敏感主窗口、旧引擎、启动器与语音配置未改。
【发现未处理】旧全局记忆没有通用知情标签，后续条目需逐条审定/新账本证据，不能靠姓名匹配自动共享；长期会话增长、资源具体数值与第一项行动模板仍未定。历史plan/step_4.md缺失已由前步登记，不补造。本步plan/logs_14成对。
【回滚方式】R1，项目根执行：
```bash
python -c 'from pathlib import Path; import json, shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_14_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b.items() if not k.startswith("_") and v.get("backup")]'
```
重启Pydroid加载恢复源码；新增模块/测试/说明为R0可删除，隔离账本保留不回写旧源。不要删除用户现有.scene-chat/state.sqlite3或旧存档。
【下一步】在Pydroid停止并重新运行语音运行.py，进入http://127.0.0.1:5000/scene-live → 存档状态，核对人物及记忆，点击“在徐家主宅与沈知韫继续”，由用户发送一句正常接话检验实际承接。旧苏婉青记录可从场景管理恢复。行动、消耗、秘密披露和正式主窗口切换保持未启用。
【当前】B旧存档隔离接入 / 导入、定向回归、恢复及浏览器状态入口通过 / 等待现役重启后的用户真实交流验收。
【产物指纹】
```json
{
  "scene_world.py": {
    "bytes": 21767,
    "sha256": "92105b01ba6a1ad5ca79921e5c53981afd4ca2090d5524884bc118b2c8ec78b3"
  },
  "scene_chat.py": {
    "bytes": 26674,
    "sha256": "3178981c9a7049ff67d2300b205b1593297e4b0af21de9ca51bf29f67dc0b522"
  },
  "txt文件/场景交流规范.md": {
    "bytes": 3738,
    "sha256": "f11c76e85ac056dc1c76ded52833fce22f492b716ec4809421edc5bc03cbb90f"
  },
  "scene_chat_dev/src/legacy_visibility.json": {
    "bytes": 496,
    "sha256": "5e14b386372725d01af82ca5d396cd8d388783ea0cd743c376153f3f74701b1e"
  },
  "scene_chat_dev/src/scene_live/index.html": {
    "bytes": 5256,
    "sha256": "3e4896a4e547c143d752aaf66ddd238eddccce6237c8ee93807159f899234df1"
  },
  "scene_chat_dev/src/scene_live/live.js": {
    "bytes": 22393,
    "sha256": "ff9452d34bf92e5d7a544de28f0ed05f887a06b2d49cb8d1afeea07c2d0164f2"
  },
  "scene_chat_dev/src/scene_live/live.css": {
    "bytes": 11597,
    "sha256": "233804423390ed318244ca7ff4cb2e2c3436735c19e1238cc30242afc9a04b54"
  },
  "scene_chat_dev/src/scene_live/README.md": {
    "bytes": 3206,
    "sha256": "84023d35f7453c6e903f95033a12e2e94069be93728c9a9873dde29c0660a429"
  },
  "scene_chat_dev/tests/test_world.py": {
    "bytes": 14253,
    "sha256": "4a7b92f93a0958bef260decd5affd88ad3affe59ad193c51b56a98d92331f940"
  },
  "scene_chat_dev/主窗口接入调整计划.md": {
    "bytes": 8117,
    "sha256": "d73e7b3f4744b9cf96900c947f744ab663879b5c05d0cfea77e49188218b858e"
  },
  "scene_chat_dev/src/旧存档隔离接入说明.md": {
    "bytes": 4580,
    "sha256": "f7676e6c4fc9c96efecef1c8e2ad70fe49943a1c87c09bb7dfd53aee64c96714"
  },
  "开发者功能/开发者说明书/开发者说明书.md": {
    "bytes": 27879,
    "sha256": "606e02f7081c844eef458e13452a9881331b8b548bd72e488faeeccf6d1aa7f3"
  },
  "开发者功能/修订日志/2026.11/B旧存档隔离状态接入.md": {
    "bytes": 977,
    "sha256": "6d37e8b24c6464b16b449dc009631d41ed87fb87547a406c52709897f20d7a80"
  }
}
```

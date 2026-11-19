【步骤编号】step_13
【上游依赖】logs/step_12.md，SHA256 f91237b2b8dd9d65ec907b8c3a0baa4c7f6bac4bdb293e8579f159b8197e725e；用户反馈首条成功、第二条失败重试后成功，授权核查记录，沿用B联调及修复范围。
【做了什么】从正式任务账本、指定Operit会话原始工具部件查清末行截断误拒，修复公共读取回执校验，完成定向回归和真实回执离线重放。
【产物】story_reading.py；tests/test_read_truncation.py；src/场景读取截断核查.md；主窗口接入调整计划、scene_live/README、开发者说明书与修订日志；logs/step_13_checks.json与step_13_baseline.json。
【验收证据】
V1 改前基线：step_13_baseline.json记录4个已有文件的字节数/SHA256及归档父版；父版均逐字节或SHA256核验，现位于开发者功能/归档/项目清理/历史修改备份，清单指向最终位置。story_reading.py改前12455字节，SHA256 530ad4129327c57cea5739256c644b040142a4ce10d1678fb68d5b97ec504611。
V2 改后结果：
- 现场pwd=/storage/emulated/0/互动对话项目/Gemini网页版；声明的Operit storage paths给出runtime root，指定chat由正式chat show --json确认，再对该会话选定3个AI时间戳只读查询message_parts，未读取其他会话正文，未写用户数据库。
- 场景96216918e8e96cb5e0f633ad：首条scene-04667938-a58d-4e28-9638-0fc3b6b2abef与第二条scene-daa30c42-77d8-47bf-8a54-534145646259都committed，revision=2，第二条在history仅出现一次。失败执行没有提前加入正式history。
- 首条AI timestamp=1795062702538：read_file完整1～22行，修前/修后均通过；第二条首试=1795062765314：首read_file末尾明确(file content truncated)，第20行3192字符只显示1156字符严格前缀，后续read_file_part 20～28完整；旧校验先因半行抛读取回执正文或行号与当前文件不符，未进入联合覆盖判定。最终JSON本身合法。
- 第二条重试=1795062822407：同一请求和同一会话，读取1～10、11～19、20～28，完整通过并接受。
- 修后真实原回执重放：首读只计1～19，20行半行不计；补读计20～28；并集完整28行。第二条原包35674字节，SHA256 6d44f7304cc4f8960e497a17dd21bba83631c292b80a615aacef3eb594424a3f，与任务保存指纹一致。详细结构化结果step_13_checks.json。
- python scene_chat_dev/tests/test_read_truncation.py：Ran 9 tests in 0.443s / OK，exitCode=0。覆盖完整编号/原文适配、明确截断半行排除、补读完整后通过、缺读拒绝、无标记/改字/错行/重复/乱序/非末尾标记拒绝；隔离SceneService预检未补齐拒绝、补齐后接受、重复结果只增一次revision且保存原审计。无Flask依赖、无模型/TTS、无现役任务写入。
- Python AST story_reading.py和新回归脚本通过；4份归档备份及7份产物重读通过；现役只读GET连接信息仍协议3/桥接1.5.0。未对现役发生成或重试请求，不宣称运行进程已加载新校验；需要Pydroid重启。
- 验证调用3组：回归、真实回执重放、最终语法/备份/状态重读；按服务修改与文档两组物理事务计，在定向预算内。临时补丁脚本产生转义SyntaxWarning但生产文件解析通过；一条终端内联查询被工具层转义损坏，改用临时脚本后取得真实记录；无正式文件受该错误影响。
V3 反向可行：4份父版存在、SHA256与V1一致；下面一条命令可恢复，未为演练覆盖当前通过代码。
【清理】本步临时查询、过滤回执、补丁、重放和文档脚本全部删除；tmp保留本来已有fix_wire.py。临时复制的角色全文随过滤回执清理，交付只留必要范围/摘要/指纹。未改main_template.html、语音运行.py、scene数据库、存档或平台配置；图片直接看已附内容，没有调用文件工具重读附件。
【发现未处理】失败执行仍留在复用的桥接场景会话历史、累计输入量偏高，属后续上下文管理；本次不清聊天或变更模型/会话策略。历史plan/step_4.md缺失沿用step_12登记，不补造；本步plan/logs_13成对。
【回滚方式】R1，在项目根执行：
```bash
python -c 'from pathlib import Path; import json, shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_13_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b.items()]'
```
恢复后需重启Pydroid生效。新增回归和核查报告为R0，可删除，不涉及正式记录回退。
【下一步】在Pydroid停止并重新运行语音运行.py，恢复现有场景继续正常交流；已成功的第二条无需重发。当前保存2次已确认；新校验真实新请求效果仍待后续使用观察。
【当前】B真实交流读取截断 / 根因确认、源码修复、9项回归及真实回执重放通过 / 等待现役服务重启加载。
【产物指纹】
```json
{
  "story_reading.py": {
    "bytes": 13209,
    "sha256": "f0001a8a641170af4bba8e7889af44c81be33e6e56154fe48dff4e0db2689b13"
  },
  "scene_chat_dev/tests/test_read_truncation.py": {
    "bytes": 6690,
    "sha256": "b84bea255a0cfe4e83fbd8a101aeca886714fd670b824518e3bbd2fea66e1e56"
  },
  "scene_chat_dev/src/场景读取截断核查.md": {
    "bytes": 3065,
    "sha256": "e684890224bca588e60229bbfac438b7fd78a819e4a80b95c9ce2aa045ff25ee"
  },
  "scene_chat_dev/主窗口接入调整计划.md": {
    "bytes": 6992,
    "sha256": "86675de33674be434bd8643577d07d60bc21137a59809e6d84677263f49bc054"
  },
  "scene_chat_dev/src/scene_live/README.md": {
    "bytes": 2560,
    "sha256": "1e41e0d59835096783c8fb36026278e0b826f881c59741bb143a912523922825"
  },
  "开发者功能/开发者说明书/开发者说明书.md": {
    "bytes": 27124,
    "sha256": "db8df1ac4a3853d800d018384dccf0015267cbe00c7e01a1a4ed37ec4b288a42"
  },
  "开发者功能/修订日志/2026.11/B场景读取截断补读修复.md": {
    "bytes": 866,
    "sha256": "c1f148021c80742672d97b210995b248aa64d9b0b90e6b4fc7ba57246c0afca0"
  }
}
```

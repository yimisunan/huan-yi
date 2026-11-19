【步骤编号】step_25
【上游依赖】logs/step_24.md；远端main基线0f76ab554c3f727422d4d6829d26929a513a00f1。
【做了什么】定位真实缺值JSON，修复可空字段传输、具体报错和资料包截断补读提示；保留电脑端新UI。
【产物】桥接main/manifest及1.8.1成品、build、interaction_runtime、场景规范、直接测试、开发说明/修订与本步plan/baseline/checks/log。
【验收证据】
- V1：实际根/sdcard/互动对话项目/Gemini网页版；本机3个UI及2个.agent源与origin/main逐字一致，未覆盖；仅HEAD/index对齐已下载remote基线后建立fix/live-null-wire分支。真实失败sleep.start/task缺值已从chat show --runtime确认，失败行动退款且未产生正式事实。
- V2：node --check通过；bridge_interaction与bridge_contract全部断言通过，新增task/start/npc/conditions路径空串、对象/null/旧协议、重复键与缺值拒绝。Python3个packet词法等价/长行拆分/真实分读覆盖用例0.008s全过；包zip构建核验通过。未改固定执行器及预扣退款。1.8.1原ID原位安装，原模型/工作区保持并恢复启用运行。初次导入使用Host路径映射错误，改用实际VFS路径后成功。Python服务未重启、未真实模型重试/TTS，不把隔离结果当实测可用。
- V3：7父版逐字节核验后归开发者功能/归档/项目清理/历史修改备份/step_25；13保护源含界面/实际存档/data/voice不变。旧1.8.0成品保留。回退命令可执行但未覆盖式演练。
【回滚方式】暂停服务后在项目根：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_25_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
插件如需回退，原ID导入scene_chat_dev/artifacts/故事桥接-continuous-1.8.0.toolpkg并复查状态。不覆盖运行事实，不强推。
【清理与提交】本步临时脚本删除，既有fix_wire.py保留；代码/文档/包仅按本步清单提交，功能分支快进合并main并推送。其他.nomedia/已存在trash文件不提交、不清理。推送SHA在最终工具结果，未上传凭据或运行事实。
【下一步】Pydroid3停止重跑语音运行.py，刷新正式首页后手动“重试本次推演”，使新packet与1.8.1一起生效；无需清档。该动作会进行真实生成，维护端未代按。
【当前】深渊天平正式互动项目 / 空值及资料读取修复已安装并定向通过 / 待Python重启和用户原行动真实重试。

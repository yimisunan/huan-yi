【步骤编号】step_19
【上游依赖】logs/step_18.md SHA256 087bf7b42bff41403a0343a10f3ca19e417d916e4f010272fe724a83d490d397；用户补齐零点、不足5休息、道具20%和整夜满恢复规则。
【做了什么】更新现行计划与开发摘要，将已定边界和具体恢复口径落盘，保持M1优先；本步仅文档。
【产物】主窗口接入调整计划.md、开发者说明书、零点与体力休息规则.md；plan/step_19.md、logs/step_19_baseline.json及本交接。
【验收证据】
- V1：真实pwd为/storage/emulated/0/互动对话项目/Gemini网页版，realpath为/sdcard/互动对话项目/Gemini网页版。两份既有文档的大小/mtime_ns/SHA256及父版见baseline，33份源码/规则/存档保护源指纹记录；写前一次并发内容复核。真实库存有效区为空，现役体力上限100、旧HOST_15加50均为只读核对。
- V2：受控脚本逐文件原子替换3份文档并逐字节重读一致；零点、不足5、整夜至上限、道具累计20、免费受限使用、最终而非暂扣判断等定向条款检查通过，旧待裁决条款已移除；33份保护源及本步契约不变。无源码/运行配置/存档修改，无模型/TTS或平台操作；仅文档，不写软件测试。本步配对与临时清理见同次脚本输出。既有step_4未配对缺口只登记，不补造历史。
- V3：两份父版逐字节核验后归入既有历史修改备份目录，baseline保存实际恢复路径。以下命令恢复文档及删除新增修订日志，不影响运行数据，未做覆盖式回滚演练。
【回滚方式】R1既有文档，R0新增修订日志：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_19_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
【清理】仅删除tmp/tmp_step19_finalize.py，保留其他既有临时物；无根目录新增物、依赖或服务器。
【调用计量】本回合1个文档事务，预检/读取/技能16次，写入3次（契约/临时脚本/脚本执行）；执行内完成一次定向验证，0次独立验证工具调用。
【下一步】step_20的M1正式剧情段/抉择契约、点按演播及自动语音；M2/M3采用已定边界同步费用、恢复、事件源和执行器。当前运行仍是step_17短交流能力。
【当前】深渊天平正式互动项目 / 零点、低体力与恢复规则已记录并验真 / 下一批M1演播与抉择。

【步骤编号】step_18
【上游依赖】logs/step_17.md SHA256 39724a666de8da287d32dfd91fdd2b39be05f138cc24b5a503d197f01ce76299；用户确认连通并提出七点玩法，授权先记录规划、分点完成。
【做了什么】完成七点需求记录与五批实施规划，更新总计划和开发文档，明确既定规则、实现建议、启用依赖与两组待定玩法；本步仅文档。
【产物】scene_chat_dev/主窗口接入调整计划.md、开发者说明书摘要、剧情演播与三档结算规划.md；plan/step_18.md、logs/step_18_baseline.json及本交接。
【验收证据】
- V1 改前基线：真实pwd为/storage/emulated/0/互动对话项目/Gemini网页版，realpath为/sdcard/互动对话项目/Gemini网页版。两份既有文档大小/mtime_ns/SHA256、33份保护源与契约指纹见step_18_baseline.json。两份父版写后逐字节核验，所有目标一次并发内容复核后才替换。终端rg不可用，精确检索改用grep_code，未重试安装。
- V2 改后结果：受控临时脚本逐文件原子替换3份文档；逐字节重读一致，七点/五批/固定费用/退款/回合解耦/序幕/语音/SVG及待定条款断言通过；33份源码/规则/配置/存档/桥接保护源SHA256不变，契约不变。收费现役启用与M3低体力出口联动，避免不完整中间玩法。本步不写软件测试、不启动服务，不执行脚本/清档，不调用故事模型或TTS。初次整体配对检查遇历史step_4缺少交接日志，导致本次文档自动恢复；仅修正为本步配对必过、既存缺口如实登记后重验一次，未补造或修改历史step_4。最后配对与清理结果见同次脚本输出。
- V3 反向可行：两份父版已收至现有历史修改备份目录，各自字节及指纹与V1一致，baseline保存实际恢复路径；以下命令仅恢复两份文档并删除本步新增修订日志，不触碰运行数据或平台插件。未执行覆盖式回滚演练。
【回滚方式】R1既有文档父版恢复，新增修订日志R0；命令：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_18_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
【清理】收尾仅删除tmp/tmp_step18_plan.md、tmp/tmp_step18_finish.py与tmp/tmp_step18_correct.py，保留既有fix_wire.py，无根目录新增物、依赖、服务器或安装包。
【调用计量】本次续接：预检/技能/读取/定位22次，写入阶段4次（临时脚本和局部纠错脚本各落盘/执行），执行内初次验证失败并完成一次定向重验（0次独立验证工具调用），1个文档事务；不把摘要前的调用冒充已完整计数。
【下一步】继续step_19的M1正式剧情段/抉择契约、点按演播与语音；无需重复确认开工。凌晨界点与低体力继续方式集中待用户明确，不阻塞M1。当前现役仍为step_17短交流能力。
【当前】深渊天平主项目互动改造 / 七点需求和五批计划已落盘，尚未实现新玩法 / 下一批M1剧情演播与抉择。

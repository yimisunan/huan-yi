【步骤编号】step_21
【上游依赖】logs/step_20.md SHA256 d074e94585e8f5655b4fd35dd66cbc6364cac8d82374e2193e4ecae602e1c1d0；持续授权七点玩法及零点/低体力/20%/满恢复规则。
【做了什么】交付M2/M3固定收费、预扣退款与真实事件回执、游戏时钟与同回合记忆、强制免费休息及实际道具/整夜恢复；原ID桥接1.8.0安装并恢复启用运行。
【产物】story_progression.py、原执行器/服务/前端、配置与事件原源及正式规则/KB/22条派生、tests/test_progression.py和必要旧测试适配、1.8.0包、开发说明/现行计划/修订日志、baseline/checks和本交接。
【验收证据】
- V1：实际根/sdcard/互动对话项目/Gemini网页版；一次33目标清单及12保护源基线，实际改动既有源每份一父版；写前并发指纹核验，逐文件原子替换并重读。未修改真实存档、data、语音配置、角色与关系、开局/清理脚本。
- V2：16项结算用例最终通过（首轮11通过、1项依赖元数据问题后重验通过、后补4项通过），25项旧交互/演播兼容全部通过；最终2项回执/道具复验通过，Python语法及Node/桥接严格空值线通过。原错误与真实命令/退出码保留checks；未运行全项目测试。隔离浏览器验证体力10时A/B可选而C/普通自定义禁用、免费道具恢复与库存/额度、演完才揭示结算、8扣5剩3强制休息、免费整夜3→100及额度重置；模拟503语音不锁。浏览器报告视口0，不能声称手机小屏/键盘大字或实听通过。
- 部署：包15613字节/SHA256 42070135bdff9221ab202043252eccaddcb8f4f50504a4b47270d93e6e8e7d08，与源及manifest一致；plugin import/show和status核实1.8.0、原模型gpt-6.1-sol/工作区保持、enabled/running=true、busy=false/inFlight=null/outbox无。现役Python互动协议1，Pydroid3需停止重跑语音运行.py后刷新加载协议3。无真实模型/TTS/清档调用。
- V3：27份已有源父版SHA核验并归档，12保护源不变，31写入源指纹一致；新文件中间副本误留的父版已清除，不冒充原始父版。未执行覆盖式回滚演练；保留旧1.7.0包。
【回滚方式】R1既有源/R0新增。先停止桥接和Python服务，执行：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_21_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items() if v["exists"] and "backup" in v]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
平台另导入原ID旧1.7.0包并核验；源码回退不等于插件回退。若已产生真实收费行动，先保留最新存档，不能用源码父版覆盖运行事实。
【清理】隔离8773服务已关闭、浏览器about:blank；本步tmp_step21_*脚本/夹具/依赖收尾删除，保留fix_wire.py。本步plan/log配对，历史step_4缺plan仅登记。
【预算与计量】一次L2范围按依赖分组，复用基线/父版；超默认调用预算用于多模块接口和直接持久恢复/浏览器验收，初次依赖缺失及旧文案断言各定向修正一次。文本替换缩进不符在写前停止并局部校正；无全量环境安装。未维护完整跨段工具总数，不补造。
【下一步】step_22接M4原8场景池的统一初始化事务/可播序幕，同新档ID只抽一次；step_23完成M5 SVG及总体验。真实清档须玩家确认；现役Python仍待用户重启加载。
【当前】深渊天平正式互动项目 / M1～M3源码、规则、桥接1.8.0交付并隔离验证 / 正在接M4序幕与新档。

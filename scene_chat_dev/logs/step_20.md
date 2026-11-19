【步骤编号】step_20
【上游依赖】logs/step_19.md SHA256 53e6e6c6e5f889a1b88a91998ecef241a33ff6c2cec3bd0bb4392169860c0f2a；七点改造持续授权，用户已补齐零点与恢复边界。
【做了什么】交付M1正式剧情段/段末decision、逐节点演播门、当前抉择选择、刷新恢复及自动语音，原ID安装桥接1.7.0。费用/时钟/休息等后续批次尚未实现。
【产物】后端3源、正式HTML/JS/CSS、桥接main/manifest/build及1.7.0包、正式规则与两个KB原条目/22条导出及路由说明、2份适配测试与新增9项演播测试、开发文档；baseline/checks及本交接。
【验收证据】
- V1：真实pwd /storage/emulated/0/互动对话项目/Gemini网页版，realpath /sdcard/互动对话项目/Gemini网页版。完整目标基线见baseline，每个实际覆盖源只一份父版；按依赖分组应用前核验来源未并发改变。已读同步排除覆盖tmp依赖/夹具，未改同步配置。
- V2：27份写入源指纹最终一致，14份实际存档/data/voice/关系/事件参数/初始脚本/配置保护源字节不变；没有真实故事模型/TTS或清档。语法/Node桥接契约/严格空操作线与派生22条核对通过；原16项功能用例15通过及1项更新新显示语义后重验通过，新增9项全通过，后补协议保护后读取接受定向检查再次通过。完整命令输出与初次缺Flask、pip环境限制保留于checks，临时依赖未写系统。
- 浏览器：逐节点、未读隐藏、刷新游标、无自动出声、503语音失败继续、末尾ABC/自定义及选择排队/原编号恢复均实际观测。发现字段顺序比较误判后按值修正并定向重验一次通过。工具不支持resize，不声称手机视口/大字体/真实听感通过；UI搜索脚本VFS路径在Host不可见，使用已读规范作为通用参考，不编造搜索命中。
- 部署：桥接1.7.0包15742字节，SHA256 fa53f12298b8e48398c51491fc7b487a9779767684b9903ee2d3fa89c416ebde，zip/manifest/main与源码一致；原ID导入与plugin show/status确认，模型gpt-6.1-sol/工作区/原running启用状态保留，busy=false，无inFlight/outbox/error。现役Python仍protocol=1，需在Pydroid3停止并重跑语音运行.py、刷新后加载演播协议2；新增桥接保护不领取旧协议正式任务。
- V3：24份父版已逐字节校验并移至现有历史修改备份目录，baseline记实际路径；保留旧1.6.1安装包。下述只恢复源码；平台插件回退须另按原ID导入旧包并核验。未执行覆盖式回滚演练。
【回滚方式】R1既有源，R0新增产物。先暂停桥接、停止Pydroid服务，再执行：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_20_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items() if "backup" in v]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
平台回退：operit2 plugin import /virtual/android/documents/230ffdc0fe524442bfde22083d61c969/scene_chat_dev/artifacts/故事桥接-continuous-1.6.1.toolpkg。随后重启Python并核验；不得仅回源码就声称插件也回退。
【清理】隔离8772服务器已关闭，浏览器离开测试页；本步临时脚本、依赖和夹具收尾删除，保留fix_wire.py，无根目录新增物。step_20 plan/log配对检查，本项目既有step_4缺口只记录。
【预算与计量】范围为L2多模块事务，按依赖分组写入并复用一次父版。验证超过4次，原因是Flask环境缺失、一次旧断言适配、浏览器发现字段顺序误判及部署协议保护后定向复验；无全目录扫描或全项目测试。调用覆盖多段执行，未维护完整逐类计数，不补造总数；真实命令和结果保留checks及工具回执。
【下一步】用户重启Pydroid本地服务后刷新，现有档先点“继续当前剧情”，无需清档。step_21按M2/M3联动实现固定三档、真实事件回执、零点/记忆回合、不足5休息、道具累计20%与整夜满恢复；后续M4序幕/M5 SVG。
【当前】深渊天平正式互动项目 / M1源码、规则与桥接1.7.0已交付并隔离验证，现役Python待重启 / 下一批M2/M3结算与休息恢复。

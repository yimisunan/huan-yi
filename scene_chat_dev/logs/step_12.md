【步骤编号】step_12
【上游依赖】logs/step_11.md，SHA256 9c3f6b3be287c9fa989adf99fc99741536fcac81a3b20ed3f21fc6263938322a；用户已敲定B并授权开始真实交流候选页。
【做了什么】完成B真实交流候选源码、三类消息正式契约与服务端恢复接口；真实模型请求留由用户在页面发送触发。
【产物】
- scene_chat.py：协议3，messages允许dialogue/action/narration；action/dialogue必须在场，narration空speaker；新增场景列表、按request_id查询与/scene-live白名单资源。
- txt文件/场景交流规范.md：三类按需混排，不强制凑齐，action只作现场描写；scene_chat.html兼容动作和旁白标签。
- src/scene_live/{index.html,live.css,live.js,README.md}：延续B视觉、人物原图查看、常驻输入、接受后显示、耐久恢复、场景管理、未知送达先查询、同ID显式重发、失败显式重试、历史和连接信息入口。浏览器仅保存sceneId/draft/pending，SQLite为接受记录来源。
- tests/test_live.py：定向离线事务和HTTP验收；主窗口接入调整计划、连续交互结构稿、开发者说明书与修订日志同步当前进度。
【验收证据】
V1 改前基线：logs/step_12_baseline.json记录6个已有文件的bytes/SHA256/备份；所有备份逐字节或SHA256验证，现已按项目规则移入开发者功能/归档/项目清理/历史修改备份，清单路径已更新。新增文件为R0。
V2 改后结果：
- 终端现场pwd=/storage/emulated/0/互动对话项目/Gemini网页版，realpath=/sdcard/互动对话项目/Gemini网页版；未套用客户端另报Linux路径。rg不可用，改用文件工具及受限Python读取，不安装rg。
- Python AST scene_chat.py PASS；node --check src/scene_live/live.js返回exitCode=0。
- 通过已排除同步的tmp/flask-deps运行test_live.py：{"typed_messages":"PASS","invalid_speakers_and_kinds_rejected":8,"read_coverage":"PASS","same_request_commit_once":"PASS","restart_restore":"PASS","request_lookup":"PASS","candidate_routes":"PASS","same_origin_boundary":"PASS"}。
- test_transactions.py：transactions/idempotent_commit/durable_restore/expired_lease/source_change/packet_coverage/route_boundary全PASS，invalid_cases_rejected=5，packet_bytes=19868。
- 首次test_live完成时文件响应终结出现OSError Errno 5，定位为测试响应未显式关闭；改为with client.get后单次重验exitCode=0，无终结异常。没有因此修改生产事务。
- 复用浏览器留存的14项隔离检查：初始无已接受记录；queued不伪装已回复；接受后4个消息节点含玩家/旁白/动作/对白；刷新仍4；失败可显式retry后8；刷新未知送达查到原任务仍queued；未登记请求显示按原编号重发和放回草稿；同编号接受后16且pending为空；历史计数匹配。
- 场景管理证据：2个场景，选择历史场景后dialogClosed=true、restoredCount=20、restoredTitle=离线验收客厅。全是隔离fixture，不是正式模型生成。
- 375×812、390×844、844×390、1440×900四组检查overflow=false/inputOverlap=false；动作正文宽依次约293/308/465/630px、背景透明。补充历史触控区44px后375组定向检查仍无溢出/输入覆盖。
- 最后复核：connectionLink=PASS，protocol=3，historyClose=PASS，historyCount=16，pollKeepsScroll=PASS。辅助脚本曾因旧DOM缺入口及统计隐藏历史节点出现失败；重新加载并限定#messages后通过，没有把这些辅助错误记为产品通过。
- 浏览器宿主顶层viewport=0，尺寸证据来自同源固定尺寸iframe；未宣称真机软键盘、动态大字、屏幕阅读器或真实断网验收。
- 当前5000只读连接探测：scene_protocol=2，bridge.present/running=true、phase=ready、plugin_version=1.5.0。现役Pydroid进程尚未重启，不声称已加载新路由或新契约。桥接源码核对优先采用下发output_contract，无额外action白名单，无需升级插件、无切模型。
- 当前可见续作部分执行2组定向终端验收（初次事务/语法、关闭响应后重验）、最后2项界面功能复核及1次文档/备份重读；早前上下文省略调用数不可恢复。超into默认预算理由为跨服务协议/耐久恢复/UI验收以及有新失败需定向复核，不以流程堆叠充当验收。
V3 反向可行：6份归档父版均存在且与V1 SHA256一致，可运行下方一条命令恢复；只核验凭据，不实际覆盖当前通过源码。恢复后需Pydroid重启生效，新增候选页可保留但无恢复后旧服务路由。
【清理】隔离8768 fixture PID13343经cmdline匹配后SIGTERM；本步tmp测试源码、依赖、日志和数据库目录已删除。tmp仅保留预先存在的fix_wire.py；原8766三版服务继续保留，浏览器已返回compare.html#b。未改Operit根或交付位，未全盘扫描；原主窗口/存档/data.json/voice_config.json/原图未写入；未发真实模型/TTS。
【回滚方式】R1：在项目根执行：
```bash
python -c 'from pathlib import Path; import json, shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_12_baseline.json").read_text()); [shutil.copyfile(r/v["backup"], r/k) for k,v in b.items()]'
```
R0：新增候选页与test_live.py可删除，正式存档和桥接安装不在本次回退范围。
【下一步】用户在Pydroid停止并重新运行语音运行.py，打开http://127.0.0.1:5000/scene-live；从场景管理恢复或新建1～2人场景，发送一句真实输入验收。若提示协议旧或404，先重启并查看连接信息。正式主窗口替换、存档迁移、世界行动与资源结算仍未实施。
【当前】B真实交流候选窗口 / 源码、离线事务与浏览器恢复通过 / 等待现役服务重启及用户真实交流验收。
【产物指纹】
```json
{
  "scene_chat.py": {
    "bytes": 24772,
    "sha256": "be82cb087e5267f1357e0964040f49061f6597d9dba319aab9bb25a6833866e9"
  },
  "scene_chat.html": {
    "bytes": 11033,
    "sha256": "ba2b7a66e1dfa2ea595b2ac49778fef3293331c32f8420c337e924e9eb7e11a5"
  },
  "txt文件/场景交流规范.md": {
    "bytes": 2958,
    "sha256": "3fdfcd5f6082ba232c6c6e2906df3586829ef68f189b3ba92cb3edfc0da32e10"
  },
  "scene_chat_dev/src/scene_live/index.html": {
    "bytes": 4608,
    "sha256": "085a2e6eb610d8f25727753db62e485f7fbe8fd8fe2531edd7c3363918096327"
  },
  "scene_chat_dev/src/scene_live/live.css": {
    "bytes": 10431,
    "sha256": "863d0e7e982ca5a9253dd15c471f78c150346312b13681238348059ee3a098d6"
  },
  "scene_chat_dev/src/scene_live/live.js": {
    "bytes": 15449,
    "sha256": "f9318dacf751fa2cd7f199d803772e2c01cddbdce2f73de19cad99babd1a5ef4"
  },
  "scene_chat_dev/src/scene_live/README.md": {
    "bytes": 2299,
    "sha256": "0973d84378dbce2522fb6ad1db6de6079918817c39d638b8a4a824a25915074e"
  },
  "scene_chat_dev/tests/test_live.py": {
    "bytes": 5825,
    "sha256": "30173dec62a0ade84379310671a002a6fd72293c2080de4231f388aef6797f5b"
  },
  "scene_chat_dev/主窗口接入调整计划.md": {
    "bytes": 6530,
    "sha256": "dec9bc8c05add20c0c0d92fe60d19f8a720a11ed8ccff606c766488e9ec94323"
  },
  "scene_chat_dev/主窗口连续交互结构稿.md": {
    "bytes": 2909,
    "sha256": "11d0a113788fd4705c07337cd6ab030f0cba51dfe8506a61b7809f3e13d0f1ec"
  },
  "开发者功能/开发者说明书/开发者说明书.md": {
    "bytes": 26631,
    "sha256": "1dc56b2fb69cdcf6a9522d4df76ffd842ec2bd884c41661733ab3c4af0941346"
  },
  "开发者功能/修订日志/2026.11/B同席真实交流候选页.md": {
    "bytes": 1290,
    "sha256": "d3609712568b114c22c3a77d6bbb2adbd9d6559225e625bbc195485180c8bc1e"
  }
}
```

【配对自检】本步plan/step_12.md与logs/step_12.md齐全；所有现有plan均有同名log。发现历史logs/step_4.md缺少plan/step_4.md，本次只登记，不补造历史计划、不删除历史日志。收尾的全量配对断言因这一既有缺口失败，已核实不是本轮交付缺失。

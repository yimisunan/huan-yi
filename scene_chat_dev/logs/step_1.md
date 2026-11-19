# 场景交流实验交付

当前：scene_chat / 代码落地、离线事务与插件路由验证通过、插件1.4.0已安装 / 等待现役Python服务重启与真实交流验收。

入口：重启手机上原有的 `语音运行.py` 后访问 http://127.0.0.1:5000/scene-chat 。若返回404，说明仍在运行旧进程。工具终端与手机现役Python环境不同，本轮没有擅自结束其进程。

已完成：scene_chat.py独立SQLite账本与来源包；story_service.py注册路由并复用本地请求边界；scene_chat.html连续记录、草稿、原请求确认与显式重试、仅点击播放才合成Fish语音；桥接按入口分发心跳/预检/结果；场景专用角色与会话；场景/来源/模型变化或观察体量阈值120000时保留旧聊天并新建会话。AGENTS.md与提示词.md增加场景入口作用域。

首版限制：1～2位角色、24次交流、包≤160000字节；保留已接受历史原文，不伪称压缩；facts_delta/needs为空。移动、物品、任务、秘密解锁、数值结算通过handoff标识，尚无自动完整回合转交按钮。独立实验不继承全部原游戏动态事实；原存档指纹变化则拒绝继续。

验证证据：Python编译和页面/桥接JavaScript解析通过；tests/test_transactions.py输出transactions、idempotent_commit、durable_restore、expired_lease、source_change、packet_coverage、route_boundary均PASS，拒绝5个非法用例，单人物样例包28503字节；tests/bridge_contract.js输出PASS。手机iframe宽386px、scrollWidth386px，接受记录与草稿显示正常。未执行真实模型生成、TTS请求或全流程浏览器服务测试。工具终端无Flask/pip，通过临时纯Python依赖完成离线验证，收尾删除。

插件：同ID local.story.operit_bridge，1.3.0→1.4.0；通过VFS项目路径package import成功，storedPath仍为 /operitapp/data/extensions/device/packages/故事桥接.toolpkg。status返回version=1.4.0、busy=false、inFlight=null，CHAT/工作区/chatId/participantId保留。导入后首次status显示running=false、enabled=true；未调用start/stop，真实运行状态需重启本地服务后查看。package list不列该ToolPkg子包，不能据此判断其禁用；status可实际执行。

包源现状：原包只有CommonJS JavaScript与manifest，无TypeScript原工程；本次维护可读JS源码，复制当前API types，未安装编译器或宣称完成TS构建。

回滚：原包 scene_bridge_original.toolpkg；使用 operit_editor package import 其项目VFS绝对路径可回退。既有源文件备份清单与指纹见 logs/baseline.json，逐项复制backup回原路径。新增实验账本.scene-chat不写原data.json、存档、语音配置与立绘；本轮未修改这些文件。

下一步：用户在Pydroid停止旧服务并重新运行语音运行.py，打开入口；确认测试模型和少量普通交流范围后才开展真实模型验收。待验：宿主额外注入的世界书/规则、实际读取回执、会话重建、手机软键盘、断网恢复、人设与知识隔离。未证明实际token或费用下降。

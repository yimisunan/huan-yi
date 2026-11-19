【步骤编号】step_25
【对象】深渊天平正式互动 / 电脑界面更新后生成失败
【上游】logs/step_24.md；远端基线0f76ab554c3f727422d4d6829d26929a513a00f1，本机界面与远端逐字相同，已仅对齐Git HEAD/index，原工作文件保留。
【原因】真实失败会话明确sleep.start与task冒号后缺值；资料包54行、最长19027字符，整读与重复1-54分读均截断，出现许可外补读。未接受正文，15预扣已退。
【目标】桥接1.8.1对可空字段采用合法空串传输、只在整份合法解析后按精确路径归一为null；缺值与重复键仍拒绝。改善字段级诊断、任务提醒/事件对象，并将正式packet等价分行以可补读。
【写入】scene_chat_dev/local.story.operit_bridge/main.js、scene_chat_dev/local.story.operit_bridge/manifest.json、scene_chat_dev/build.py、interaction_runtime.py、txt文件/场景交流规范.md、scene_chat_dev/tests/bridge_interaction.js、开发者功能/开发者说明书/开发者说明书.md；新增scene_chat_dev/tests/test_live_packet_format.py、开发者功能/修订日志/2026.11/正式互动空值与资料截断修复.md、scene_chat_dev/artifacts/故事桥接-continuous-1.8.1.toolpkg；plan/baseline/checks/log与临时脚本。
【不变量】新界面字节不变、收费/退款/听众/唯一事务不改、原存档/音色/模型保留。不修补残缺JSON，不自动付费重试。不运行真实故事模型/TTS。安装同ID桥接修复属当前修复授权，保持配置。
【验收】Node直接桥接/空值/缺值/重复键/旧协议；JSON等价/长包分读；新包构建/安装版本与启用状态；真实四源与界面指纹不变；按main规则仅提交本步源与产物，快进合并推送，不强推。
【回滚】已变更源一份父版，旧1.8.0成品可原ID导回；代码回退不撤销运行事实。恢复命令记交接。

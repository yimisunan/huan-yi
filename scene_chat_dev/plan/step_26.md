【步骤编号】step_26
【上游】logs/step_25.md；真实失败ddc06518通过grep_code检索本任务live.txt，角色允许而服务verify拒绝，导致再次退款。另有未完成全覆盖风险。
【目标】统一live专用角色和服务只读工具（read_file/read_file_full/read_file_part/file_info/grep_code），grep只可检索指定文件且不计正文覆盖；未授权路径/目录/写工具继续拒绝。生成前给出按实际字节/字符分组的完整read_ranges与必需补读，避免2364行按20行需119次接近128工具上限；不扩大正文/秘密资格。
【写入】interaction_runtime.py、scene_chat_dev/local.story.operit_bridge/main.js、scene_chat_dev/local.story.operit_bridge/manifest.json、scene_chat_dev/build.py、txt文件/场景交流规范.md、scene_chat_dev/tests/bridge_interaction.js、开发者功能/开发者说明书/开发者说明书.md；新增scene_chat_dev/tests/test_live_read_audit.py、开发者功能/修订日志/2026.11/正式读取工具与范围一致性修复.md、scene_chat_dev/artifacts/故事桥接-continuous-1.8.2.toolpkg；plan/baseline/checks/log与tmp。
【验收】直接执行生产verify函数的隔离回执：允许文件grep＋完整读通过、grep-only/缺页/伪回执/许可外路径/目录及写工具失败；记忆行号字符串可解析且严守范围，覆盖所有规划页、上限及桥接角色工具一致。新1.8.2构建/原ID安装和状态；main提交/推送。
【不变量】收费/退款/真实存档/界面/语音模型配置不改；不代用户执行真实付费生成，不以跳过审计放行。
【回滚】每个现有源一份父版，原1.8.1包保留；源码/插件回退不覆盖运行事实。授权沿用户报告故障的修复范围。

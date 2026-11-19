# step_7 交接单

- 【步骤编号】step_7
- 【上游依赖】logs/step_6.md，SHA-256=89be945532e4b2619f5b5218d6fc1021c6418bec82b5f46441446364315a186f；plan/step_7.md；用户「好的，不错，开始」已授权生成入口迁移。
- 【做了什么】把网页生成迁移到绑定工作区的正式Operit只读会话，更新读取契约和工具审计，保留原硬校验与写入通道；安装1.1.0并完成一次真实隔离回合提交。
- 【产物】11个正式文件及父版详见src/安装清单_7.json（SHA-256=c2c7844a5768c254daf241be5fc42905feafa251ef93498a00eb973fe0ba6167）；src/会话接入说明.md；src/会话接入实测证据_7.json（SHA-256=6279d9127c0743c0c9e30daecd94b3e123ce97c7cb8b27024c57d42112836c9c）；最终结果、原始消息、HTTP与Node验收文本同存src。tmp收尾清空。
- 【验收证据】
  - V1 改前基线：11个目标与20个受保护文件SHA-256/大小/mtime保存于安装清单；桥接原1.0.3且enabled/running，暂停时busy=false/pendingResult=false；原模型gpt-6.1-sol，当前聊天8455b45a-26a3-4c59-b836-cbf0f18b5f06。原3张角色卡未修改。
  - V2 改后结果：HTTP原样“Ran 19 tests in 33.273s”“OK”；Node10组PASS。真实隔离任务session-integration-7，attempt=1、23次工具调用全部成功、耗时509.564秒；正式会话committed/completed，原始消息最终JSON与回传文本逐字节一致，副本第1回合回执committed/state_version=1。原项目剧情第4回合，20个保护指纹不变。安装原样“SOURCE_INSTALLED 11 BACKUPS_VERIFIED 11 PROTECTED_UNCHANGED 20”；宿主Version:1.1.0、Enabled:true；安装包读回与源码包一致。当前桥接running/enabled=true、busy=false、pendingResult=false、inFlight=null，工作区和端口恢复正式项目。旧Python进程story_protocol=2，lastError明确要求重启；未领取真实剧情任务。
  - V3 反向可行：11份父版SHA均与改前匹配；安装清单rollback_command经shlex解析与Python编译通过，未实际回滚。父版包含1.0.3包。恢复仅本次文件，正式存档无需恢复。
- 【实现边界】消息执行会切换当前聊天，完成后条件恢复；正式聊天在下一排队行动时自动新建，当前chatId为空。专用角色f3c542bc-5c3c-413f-a4c9-375c526f0e76保留，8项只读工具，未激活为用户默认角色。只验证本地KB，世界书/Skill与长期语义一致性未验收。原生JS项目继续维护原生源码，未添加TS编译链。
- 【清理】测试聊天839b32dc-7754-4272-b7ee-ff1c155e86a2及其角色绑定已由configure resetSession移除；额外空聊天已删除；检查插件local.story.session_inspect已删除。隔离5013服务关闭，端口确认不再监听。保留证据后删除本步tmp资料/依赖/脚本，根目录仅允许本次必要同目录父版新增，plan/logs按step文件名配对。
- 【成本与异常】T1候选实现与验证、T2安装与真实集成两事务。验证与调用数超过into/iter-revise普通改动预算，已在执行中说明：本次跨Python服务、插件正式会话、宿主安装和真实隔离提交。实际付费故事生成仅1次，无自动再生成；L1无需压缩。终端多行转义出错后改为落盘脚本。proot缺Flask/pip，通过官方PyPI包下载到已排除同步的tmp；首解压缺metadata补齐后继续，候选漏常量修正后19项通过。以上失败均未触及正式源码，依赖最终清除。安装使用同ID原地import成功，无卸载旧包。价格未配置，金额未知。
- 【回滚方式】R1：停止桥接，在项目根执行src/安装清单_7.json中的rollback_command，再导入恢复后的开发者功能/Operit故事桥接/故事桥接.toolpkg，核验版本/配置并重启Pydroid3；桥接专用新增角色/聊天按绑定解除后删除。R0文档与证据可删。
- 【下一步】在Pydroid3停止旧进程并重新运行语音运行.py，刷新网页；协议3出现后由用户提交下一条真实行动。源文件迁移与隔离验收已完成，实际Pydroid3加载等待此操作。

# step_5 交接单

- 【步骤编号】step_5
- 【上游依赖】logs/step_4.md，SHA-256=934644c92edb7442c26b92198b140d885989c2db1f07ebac345a037a2d08e28a；用户关于规则契约、游戏化结算和弱化状态入口的三项要求；plan/step_5.md。
- 【做了什么】统一桥接裸JSON与手动Python入口、服务端读取审计和节点键白名单；显式重试重读当前规则并传入上一错误；结算改为带SVG浮入/微光/淡出的行动回响，状态入口缩为小点与模型名；安装故事桥接1.0.3。
- 【产物】14个正式文件详见src/安装清单_5.json；说明保留src/契约与回响说明.md；14份同目录父版为R1凭据；候选、临时依赖、预览及脚本全部在本步tmp，收尾清空。
- 【验收证据】
  - V1 改前基线：14个既有目标改前SHA-256/大小/mtime已于预检记录，安装前重核SHA及mtime；8个受保护文件含存档三文件、data.json、voice_config.json、round_runtime.py、injection_core.py、语音运行.py。清单保留改前/改后及受保护指纹。同步规则的tmp、运行目录、备份排除与限额沿用。
  - V2 改后结果：Python2项/JS4项语法及契约定向检查通过；HTTP原样输出“Ran 16 tests in 21.795s”“OK”，新增覆盖重试重读规则/原行动、节点白名单和重复键拒绝；Node9组PASS含桥接、页面、reward SVG/延迟/去重/回看/取消、阅读恢复、L1与模型检查。375×812与812×375同源隔离iframe均horizontal_overflow=false、open_dialogs=0；回响在视口内，SVG数3，动画story-reward-arrive；入口与回看高度44px。安装原样“REPACK_VERIFIED_1.0.3 6394”“BACKUPS_VERIFIED 14”“INSTALLED_MATCH 14 BACKUP_MATCH 14 PROTECTED_UNCHANGED 8”。宿主读回Version:1.0.3、Enabled:true，status为enabled=true/running=true/busy=false/pendingResult=false，实际模型仍gpt-6.1-sol / 665535GPT。
  - V3 反向可行：14份父版均与改前SHA匹配，清单rollback_command经shlex解析及Python编译通过，未实际回滚；父桥接包1.0.2在对应备份，可重导入。恢复范围只覆盖本次14个文件。
- 【安装状态】仅替换local.story.operit_bridge；因import拒绝同名，先停止空闲桥接并移除旧注册，重导入1.0.3后恢复启用与运行，未切换模型配置。实际GET任务仍failed、attempt=1，错误仍node[1]多余speaker；未发起真实生成/重试。当前服务协议2不能区分本次实现是否已载入，须在Pydroid3重启加载修改后的story_service.py。
- 【成本与异常】T1/T2两事务。复用已通过HTTP/Node结果，未重跑。浏览器外层视口调整不可用，续用同源iframe。浏览器异步evaluate未返回有效数据后，改同步读取完成布局验收。安装打包时修正候选未复制但内容未变的tools.js来源；此前一次heredoc传输引号损坏后改用落盘脚本。安装前预检发现toolpkg仍为旧候选，重打包核对后再替换正式文件。调用数超过into默认验证预算的原因为已约定的横竖屏验收、打包/安装和宿主状态核对；无额外真实模型调用。
- 【清理】隔离5013预览已停止，浏览器tab已关闭；tmp在交接完成后清空；根目录除本次4份必要同目录备份外零新增；plan/logs按step文件名配对。
- 【回滚方式】R1：在项目根执行src/安装清单_5.json中的rollback_command，随后停止桥接并重导入恢复后的开发者功能/Operit故事桥接/故事桥接.toolpkg，恢复运行；重启Pydroid3并刷新故事页。新增说明与清单为R0，但恢复前应保留清单。存档、任务、语音配置不在恢复范围。
- 【未覆盖】真实模型按新规则的生成表现、TTS、Android最大系统字号与系统减少动态效果开关；模型元数据预检不能锁定另一处同步切换。规则更清楚但不能保证模型零格式错误，硬校验保留。
- 【下一步】在Pydroid3停止当前进程并重新运行语音运行.py，刷新故事页，再由用户点击“重试原行动”；这将重读新规则并携带previous_validation_error。

# step_2 交接单

- 【步骤编号】step_2
- 【上游依赖】logs/step_1.md；第一阶段执行器契约与验收结论复用。目标与不变量由plan/step_2.md锁定，当前逐文件指纹见src/安装清单_2.json。
- 【做了什么】落实故事页面行动提交、持久任务、Operit 2桥接生成适配、一致快照及阅读恢复；最终写入统一调用RoundStore.submit。
- 【产物】story_service.py、story_client.js、story_client.css、修改后的语音运行.py/main_template.html/开发者说明书、开发者工具/故事页面验收.py与故事桥接验收.mjs、开发者功能/Operit故事桥接/四文件、src/页面对接说明.md与src/安装清单_2.json。临时依赖、候选项目和合成数据全部在tmp内，交段清空。
- 【验收证据】
  - V1 改前基线：plan/step_2.md内10个基线；正式安装前原样输出“PREINSTALL_BASELINES_UNCHANGED 10”。3个旧源文件各留一份同目录备份，后缀.into-backup-20261116_172101，指纹见安装清单。
  - V2 改后结果：Python3文件及JavaScript4单元语法通过；Flask隔离验收原样“Ran 10 tests in 11.961s”“OK”，退出码0。Node最终运行原样三行：“PASS bridge: single consumer, durable output, delivery retry, stop”“PASS page: progress, exact retry, busy controls, failed action retained”“PASS reading restore: late previous snapshot cannot resume or clear newer state”，退出码0。最终核对原样“FINAL_MATCH 12 BACKUP_MATCH 3 UNCHANGED 7”“NO_GAME_RUNTIME_CREATED True”，退出码0。浏览器确认合成任务的表单提交、等待禁用态、失败保留行动和进度缓存。实际宿主包导入、4工具注册、启动/停止与HTTP空任务连接通过，“HOST_BRIDGE_CONNECTED True”；最后status返回busy=false、enabled=false、pendingResult=false、running=false、lastError为空。
  - V3 反向可行：3个备份SHA-256与基线相符，src/页面对接说明.md提供一条恢复命令。未执行正式代码回滚，以免撤销交付；安装脚本遇故障可恢复已覆盖文件。新增包可在插件管理禁用或删除local.story.operit_bridge。
- 【成本与异常】2个关联事务组；标准工具预算明显超出，主要花费为Operit 2适配和测试依赖，不扩大功能范围。可核实验证计数：HTTP一次因缺Flask未启动，补隔离依赖后一次有效运行10项通过；Node桥接/页面共4轮（3次候选、1次最终），另1次单独阅读竞态验收；语言语法2批（首次全批、最终只复查修改的页面）。宿主实际测试暴露3个兼容问题并逐项修正：源码export需CommonJS、IPC须加载时注册、网络请求须省略undefined字段。两次内联长命令遭终端传输转义破坏后改用已落盘短命令执行；文档重复表头断言在写入前阻断，限定当前月份后安装。测试缺pip，使用PyPI发布包解压到已排除同步的tmp，不改系统Python。未保存不完整工具总计，避免补造预检/写入总次数。预算扩展已中途说明。
- 【回滚方式】R1恢复3个既有文件，R0删除9个新增文件；一条执行命令见src/页面对接说明.md。代码回滚不更改存档、voice_config.json与.round-runtime/；事务未恢复前不删运行记录。宿主桥接包交付时已停止，包启用状态保留。
- 【未覆盖】真实模型调用与生成质量、Pydroid3解释器、手机长期后台冻结、375px/横屏/大字布局。浏览器工具视口0×0且resize不支持，因此只报告交互结构验收，不报告视觉布局通过。每任务发送全量权威规则，输入成本较高；任务历史暂不自动清理；清档工具仍无会话重置协议。硬校验不等于叙事语义正确。
- 【下一步】实机体验：Pydroid3运行语音运行.py；Operit调用story_bridge:start并保持可见小窗；故事页提交一个行动。真实模型会产生调用成本并在校验通过时推进存档，本次开发验收未执行。

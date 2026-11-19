# 回合执行基础契约
对象: Gemini网页版
授权: 用户在调研后明确回复“好的，开始授权”。
目标: 结构化回合契约、固定校验/提交入口、状态版本、请求去重、持久恢复；保留旧Python入口。
范围: round_runtime.py（新增）；injection_core.py；txt文件/一键注入指南.txt；开发者功能/开发者工具/回合执行验收.py（新增）；开发者说明书及本目录记录；.operit/sync.json。
不变量: 不改真实存档、data.json、voice_config.json、前端、角色知识库或Operit配置；不发起模型调用；不操作系统分区。
风险: L2，引擎入口变更；分为运行时/引擎和契约/归档两个关联文件组。
验收: 语法；隔离目录内正常提交、重复/旧版本/坏格式、记忆容量边界、异常不污染、进程中断恢复、竞争提交及旧入口兼容。
回滚: R1，每个已修改源文件保留同目录时间戳副本；新增文件R0。
限制: 旧网页直接读取多文件的并发快照问题留待页面接入；本阶段提供受锁保护的一致快照接口。
基线:
- injection_core.py: bytes=111221; mtime_ns=1794311346881000000; sha256=dc4e4b5c568624899c12585c069316d7cc067a97594bc0136a2b2d84aa352dfe
- txt文件/一键注入指南.txt: bytes=39566; mtime_ns=1787722154000000000; sha256=f28aeb7970dc57adeb70a25018875ebc6e4c5eb16199cb633383fa870efb509b
- 开发者功能/开发者说明书/开发者说明书.md: bytes=10421; mtime_ns=1794521563143175204; sha256=aa42a23af7512dd470a9365b1745ba9aa32c42a4dbf519bcbcd85642e1e03e2d
- data.json: bytes=3873; mtime_ns=1794311192781000000; sha256=4357a34a95e4af4cd4c1aa29ddc784283f5b56c8f9918b7ab3aebc884a5075a0
- 存档/全局记忆库.txt: bytes=5049; mtime_ns=1787816076000000000; sha256=e3ed74fcc356f487e4dbdf52673e25726ea8adeeab1cfe0a48591627304a1377
- 存档/徐志北道具图鉴.txt: bytes=2437; mtime_ns=1787726754000000000; sha256=5ec84007c18ad3f9937717453e37238869ff610af5bc23ae33af2da1fc51224c
- 存档/次要NPC名册.txt: bytes=1124; mtime_ns=1787726754000000000; sha256=7c6c74b8790273b8d71294c1e9ebe700cf97ff5dfb14b10ac213c9d83c836f0f
- voice_config.json: bytes=2618; mtime_ns=1794292912340000000; sha256=6bbd1ad3f537b8a52ad3a1aec684d52358f9c0b3aaf9cbbeace994715573cec0

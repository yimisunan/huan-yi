# step_3 桥接记忆超长修复

上游：logs/step_2.md；用户提交首次实机错误截图，L1去空白298字，上限280。失败任务无回执，base_revision仍为当前快照；本次修复不推进回合。

目标：在桥接层明确150～220字生成目标和Python一致的计数口径；检测L1超280时最多一次模型压缩，只替换该JSON字符串的原始字节区间，禁止改正文/事件/身份与数值。压缩仍失败则保留失败态，禁止截断或绕过执行器。重试时带回上次校验失败原因。

范围：修改Operit故事桥接/main.js、manifest.json、故事桥接.toolpkg、开发者工具/故事桥接验收.mjs、开发者说明书索引。新增src/安装清单_3.json、src/记忆字数修复说明.md、logs/step_3.md。本地Flask服务和执行器不改，无需Pydroid3重启。

不变量：不修改存档/data.json/voice_config；280硬顶不变；全量规则仍来自任务上下文；失败结果不执行为代码。追加压缩最多1次模型调用；传输重试复用已保存结果，不触发新模型。压缩调用前持久化原结果，宿主中断后不自动重复压缩。

事务T1，L2：候选和定向Node测试在tmp。语法和计数/单字段替换/单次修正/重传不重复/重试反馈验收后，备份5个既有文件并原子安装。宿主包停止、删除本次开发包并导入新版、启用并恢复监听；正式故事任务不代为重试。

回滚：R1按安装清单恢复5个源文件并重新导入旧包；源码备份不覆盖之前阶段备份。新增说明与清单为R0。

基线：

{
  "开发者功能/Operit故事桥接/main.js": {
    "sha256": "b851d632554772a1bc6e4e7d977ae72ea39094c2f66dcf092a23a0b9b377ace0",
    "bytes": 6053
  },
  "开发者功能/Operit故事桥接/manifest.json": {
    "sha256": "04ccb1a96b897caf7cffae2fdebd16e09e4f198d4f09330bcebc5260db5d7930",
    "bytes": 551
  },
  "开发者功能/Operit故事桥接/故事桥接.toolpkg": {
    "sha256": "2a7172dc578b0563416ba3aa49de033921caef633ce4decad79fff155a11089f",
    "bytes": 3353
  },
  "开发者功能/开发者工具/故事桥接验收.mjs": {
    "sha256": "cf703f130b4ff7fcbd5ce2883bdc1f85b8425a28d0ad8b6c777576cd65f4e080",
    "bytes": 8126
  },
  "开发者功能/开发者说明书/开发者说明书.md": {
    "sha256": "0254a9ec3c29ddf9f54f1cba7807739a39e9d4e64f63b02b2dca238132e9931f",
    "bytes": 11511
  },
  "data.json": {
    "sha256": "079e1f37473701a36dfaabd350cb36fba9bda8584fee5f304935de8ba54f0f44",
    "bytes": 3803
  },
  "存档/全局记忆库.txt": {
    "sha256": "6149947df23b2c99dee6d6f6965611551213c28c56db31e76dc25585e1da786e",
    "bytes": 5182
  },
  "存档/徐志北道具图鉴.txt": {
    "sha256": "5ec84007c18ad3f9937717453e37238869ff610af5bc23ae33af2da1fc51224c",
    "bytes": 2437
  },
  "存档/次要NPC名册.txt": {
    "sha256": "7c6c74b8790273b8d71294c1e9ebe700cf97ff5dfb14b10ac213c9d83c836f0f",
    "bytes": 1124
  },
  "voice_config.json": {
    "sha256": "6bbd1ad3f537b8a52ad3a1aec684d52358f9c0b3aaf9cbbeace994715573cec0",
    "bytes": 2618
  },
  "round_runtime.py": {
    "sha256": "1747af3593f006e7fe878984ebfecd7a5fd3d15683f484b4f69e1a6055dda80a",
    "bytes": 31591
  },
  "injection_core.py": {
    "sha256": "b665b9ccf7fc1205a5baf726fc248556e20eeb9650b0fc4754695d0258af8752",
    "bytes": 111118
  },
  "story_service.py": {
    "sha256": "c4a7aafa42f7497b036bc741765d213f026da70dd1325e6787862841d4faca0b",
    "bytes": 17907
  }
}

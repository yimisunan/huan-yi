# step_2 故事页面与 Operit 2 对接

目标：故事页选择行动或输入自定义行动，生成任务持久化，Operit 2 专用桥接包领取任务并调用 CHAT 功能模型，结果只经 RoundStore.submit；成功载入一致快照，刷新恢复阅读和任务。

授权：用户「好的，开始授权」「好的，继续」。本阶段不重复逐项确认。

修改清单：语音运行.py（注册故事服务和静态白名单）、main_template.html（选项提交与快照/阅读钩子）、开发者说明书（索引）。新增 story_service.py、story_client.js、story_client.css、开发者工具/故事页面验收.py、开发者工具/故事桥接验收.mjs、开发者功能/Operit故事桥接/{main.js,tools.js,manifest.json,故事桥接.toolpkg}。续写本项目 src/页面对接说明.md、src/安装清单_2.json、logs/step_2.md。

事务：T1 服务/前端/桥接包，L2（新增接口与并发恢复）；T2 文档归档，L1。先候选实现，使用合成存档验收，再校验原件基线、每个既有文件一份备份、逐文件原子安装。桥接包可导入宿主以核验注册，不执行真实模型或真实回合。

不变量：存档、data.json、voice_config.json 不写；沿用固定执行器；不调用代码执行模型输出；同 request_id 重试幂等；不同任务/过期租约回调不得覆盖；失败保留行动；成功仅显示最新快照。

生成上下文：每任务独立组装权威规则和知识库，不依赖当前聊天或世界书隐式挂载。Tools.Chat.call 不持久化聊天；适配器只改变返回封装为回合 JSON。

验收：语法解析；Flask 本地测试客户端覆盖任务提交/重复/并发/版本冲突/失败/租约/重启/一致快照；Node 覆盖桥接单消费者、先留存结果后重传、客户端请求保留和恢复；浏览器可达时数值检查窄屏表单。测试不调用外部模型/语音。

回滚：R1 既有文件同目录时间戳备份；R0 新增文件可删。交付说明提供一条恢复命令。后台长期运行与 Pydroid3 实机保留未验证标记。

V1 基线：

{
  "语音运行.py": {
    "sha256": "a2e17621f8e465310aaa3464feb37eeed492e5b9fa5b835ae0b33201dcdc7472",
    "bytes": 39756,
    "mtime_ns": 1794311352508000000
  },
  "main_template.html": {
    "sha256": "b71e002115a240127f3a4fa9bbfa33f8dcf80b5e4d4624016b081d3eb1f2b56d",
    "bytes": 272725,
    "mtime_ns": 1794394473468827642
  },
  "开发者功能/开发者说明书/开发者说明书.md": {
    "sha256": "78970d2c26d885a15785a093e04468542e3428f5af3e813b75c1f1ecbcb67010",
    "bytes": 10852,
    "mtime_ns": 1794846792428274207
  },
  "data.json": {
    "sha256": "4357a34a95e4af4cd4c1aa29ddc784283f5b56c8f9918b7ab3aebc884a5075a0",
    "bytes": 3873,
    "mtime_ns": 1794311192781000000
  },
  "存档/全局记忆库.txt": {
    "sha256": "e3ed74fcc356f487e4dbdf52673e25726ea8adeeab1cfe0a48591627304a1377",
    "bytes": 5049,
    "mtime_ns": 1787816076000000000
  },
  "存档/徐志北道具图鉴.txt": {
    "sha256": "5ec84007c18ad3f9937717453e37238869ff610af5bc23ae33af2da1fc51224c",
    "bytes": 2437,
    "mtime_ns": 1787726754000000000
  },
  "存档/次要NPC名册.txt": {
    "sha256": "7c6c74b8790273b8d71294c1e9ebe700cf97ff5dfb14b10ac213c9d83c836f0f",
    "bytes": 1124,
    "mtime_ns": 1787726754000000000
  },
  "voice_config.json": {
    "sha256": "6bbd1ad3f537b8a52ad3a1aec684d52358f9c0b3aaf9cbbeace994715573cec0",
    "bytes": 2618,
    "mtime_ns": 1794292912340000000
  },
  "injection_core.py": {
    "sha256": "b665b9ccf7fc1205a5baf726fc248556e20eeb9650b0fc4754695d0258af8752",
    "bytes": 111118,
    "mtime_ns": 1794846792408274207
  },
  "round_runtime.py": {
    "sha256": "1747af3593f006e7fe878984ebfecd7a5fd3d15683f484b4f69e1a6055dda80a",
    "bytes": 31591,
    "mtime_ns": 1794846792400274207
  }
}

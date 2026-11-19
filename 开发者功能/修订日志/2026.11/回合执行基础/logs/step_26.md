- 【步骤编号】step_26
- 【上游依赖】logs/step_25.md；src/排查与疑似.txt的逐项决定和最终授权；本轮用户对最终简写回复“准确”。
- 【做了什么】仅替换两个角色的5个已批准段落；徐念薇20岁在校校花、保留绘画天赋，外貌去标签并补匀称修长体态；苏婉青恢复天生妩媚与娇柔内向反差；三套衣服按确认文字写入。
- 【产物】角色类.json、由现有convert_to_operit.py的FILES/to_operit生成的本地世界书导出、说明书单行索引；本计划/交接。没有执行转换器main，避免其额外.prev副本；未导入平台。
- 【验收证据】
  - V1 改前基线：三个覆盖目标的大小、SHA-256及唯一父版见下方清单；五角色原文和导出在内存保留作结构比较。全部备份逐字节校验。
  - V2 改后结果：系统python3执行完成；JSON解析与重读、5个批准段落逆替换后等于原对象、源JSON仅两个content改变；导出22条且无重名，屏蔽两个批准content后与原导出完全一致。五个角色的所有元数据、其他角色正文及两角色非目标段落不变；关键词清单已读且路由一致，无需改写；常驻数量不变。采用原文件序列化字符串定点替换，未重新格式化源JSON。定向验证1批。
  - V3 反向可行：三份父版已移入既有归档，重新读字节与原文一致；恢复命令如下，未实际覆盖演练。
- 【回滚方式】R1，在工作区根执行：
```bash
python3 -c "from pathlib import Path; import shutil; shutil.copyfile('开发者功能/归档/项目清理/历史修改备份/txt文件/知识库/角色类.json.into-backup-20261118_134836', 'txt文件/知识库/角色类.json'); shutil.copyfile('开发者功能/归档/项目清理/历史修改备份/Operit世界书导出/operit_worldbook_深渊天平.json.into-backup-20261118_134836', 'Operit世界书导出/operit_worldbook_深渊天平.json'); shutil.copyfile('开发者功能/归档/项目清理/历史修改备份/开发者功能/开发者说明书/开发者说明书.md.into-backup-20261118_134836', '开发者功能/开发者说明书/开发者说明书.md')"
```
- 【文件基线及结果】
```json
[
  {
    "path": "txt文件/知识库/角色类.json",
    "backup": "开发者功能/归档/项目清理/历史修改备份/txt文件/知识库/角色类.json.into-backup-20261118_134836",
    "before_bytes": 25701,
    "after_bytes": 24923,
    "before_sha256": "20a66c1eb9b59f474029c24715950658abab50b2f6aae8b657007e1dcf6610ec",
    "after_sha256": "d89b4df2ab32614c10dd87f395aae09cb1179584039cc408c873db70ee4b4bf9"
  },
  {
    "path": "Operit世界书导出/operit_worldbook_深渊天平.json",
    "backup": "开发者功能/归档/项目清理/历史修改备份/Operit世界书导出/operit_worldbook_深渊天平.json.into-backup-20261118_134836",
    "before_bytes": 85198,
    "after_bytes": 84421,
    "before_sha256": "cc1985b298367a0949bc8fb7dcd4a6846dc9cde0643f13e045637036d5564c8d",
    "after_sha256": "cba62db21d0fdd0cd5a0e3ccd1455deb621b1a1d47ff0b2479dc0750a3a3bd25"
  },
  {
    "path": "开发者功能/开发者说明书/开发者说明书.md",
    "backup": "开发者功能/归档/项目清理/历史修改备份/开发者功能/开发者说明书/开发者说明书.md.into-backup-20261118_134836",
    "before_bytes": 20183,
    "after_bytes": 20426,
    "before_sha256": "3970a1f7d7676042f59dfd9afacd01f3e03e477efba1e248003a3178f83d64b9",
    "after_sha256": "78d0a305585884248bdb9eb75f33a1afdd81e7d2b544aeae4d714571ad3eae9c"
  }
]
```
- 【验证范围与限制】没有运行真实模型/故事模拟、服务重启或网页/TTS，未改动态存档与任何声学段落；本轮仅验证本地角色库及导出的一致性。
- 【下一步】本轮角色修正完成；step_24真实模型补读与网页/TTS端到端、P5—P7语音试听仍待后续测试。
- 当前：深渊天平引擎 · 互动叙事 / 角色修正已落地且定向验证通过 / 本轮收尾完成。

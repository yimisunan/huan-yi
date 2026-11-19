- 【步骤编号】step_28
- 【上游依赖】logs/step_27.md；用户确认工作日默认大学、镜头以玩家为主，不模拟镜头外换位。
- 【做了什么】世界观驻地规则与三份Python源中的8处徐念薇默认位置/事由统一为大学；周末主宅不变，明确实际位置优先、必要时再移动及到达后更新。
- 【产物】计划所列5个既有文件与本交接；无临时文件残留。
- 【验收证据】
  - V1：下列改前指纹与唯一父版均已核验字节一致。
  - V2：JSON解析及非目标对象一致PASS；三个Python AST解析及指定字符串替换外结构一致PASS；索引提取30个key PASS；当前记忆库与世界书导出字节不变PASS。未执行引擎、清理器、盲盒、真实故事或TTS。
  - V3：父版收至既有归档并逐字节重读PASS；实际恢复未演练。
- 【回滚方式】R1，项目根执行：
```bash
python3 -c 'import shutil; shutil.copyfile('"'"'开发者功能/归档/项目清理/历史修改备份/txt文件/知识库/世界观类.json.into-backup-20261118_153215'"'"','"'"'txt文件/知识库/世界观类.json'"'"'); shutil.copyfile('"'"'开发者功能/归档/项目清理/历史修改备份/injection_core.py.into-backup-20261118_153215'"'"','"'"'injection_core.py'"'"'); shutil.copyfile('"'"'开发者功能/归档/项目清理/历史修改备份/存档清理器.py.into-backup-20261118_153215'"'"','"'"'存档清理器.py'"'"'); shutil.copyfile('"'"'开发者功能/归档/项目清理/历史修改备份/存档开局随机盲盒.py.into-backup-20261118_153215'"'"','"'"'存档开局随机盲盒.py'"'"'); shutil.copyfile('"'"'开发者功能/归档/项目清理/历史修改备份/开发者功能/开发者说明书/开发者说明书.md.into-backup-20261118_153215'"'"','"'"'开发者功能/开发者说明书/开发者说明书.md'"'"')'
```
- 【清单】
```json
[
  {
    "path": "txt文件/知识库/世界观类.json",
    "backup": "开发者功能/归档/项目清理/历史修改备份/txt文件/知识库/世界观类.json.into-backup-20261118_153215",
    "before_sha256": "3a0f9916f7c5a4ab7979882dfa2000adcc171eca48535cfbda734c8dc6f2f5bf",
    "after_sha256": "1c4d85a099c57246f248e2785f29bf6e5efbd165c18880f1926360fc180db50d"
  },
  {
    "path": "injection_core.py",
    "backup": "开发者功能/归档/项目清理/历史修改备份/injection_core.py.into-backup-20261118_153215",
    "before_sha256": "a0f8f08eac00041ff5e85e337fdd210c17d83155125bcef839136db2be984968",
    "after_sha256": "17157355cdffeb13c79b4248a79fbd6516e9eb3d094175c7c24b72f9db40c64e"
  },
  {
    "path": "存档清理器.py",
    "backup": "开发者功能/归档/项目清理/历史修改备份/存档清理器.py.into-backup-20261118_153215",
    "before_sha256": "0646b0ec0a7fe7b2fb9640ed2f57a94dfccdcbea79ac1f97ab6e3691767e7913",
    "after_sha256": "7712376e68669253a31c94a0d5a9080484496785e59230591f772c06ed94d06a"
  },
  {
    "path": "存档开局随机盲盒.py",
    "backup": "开发者功能/归档/项目清理/历史修改备份/存档开局随机盲盒.py.into-backup-20261118_153215",
    "before_sha256": "b36479cba7dc53d4f6977ec4d0493ca20ea4e11f339c0b7c42c45ef6e059b5b5",
    "after_sha256": "c2862f229c92bfe70622e109c2596d9359d45f4c645fad418540a23fe05183eb"
  },
  {
    "path": "开发者功能/开发者说明书/开发者说明书.md",
    "backup": "开发者功能/归档/项目清理/历史修改备份/开发者功能/开发者说明书/开发者说明书.md.into-backup-20261118_153215",
    "before_sha256": "cb66b924c4e25df67ba79e49c964545a5afa4434fa4ab7440e1b917db9cbb12c",
    "after_sha256": "1e00e65831babd11f87ee5db8e00d1d601a91160f8e9f02523139adecce2d158"
  }
]
```
- 【下一步】本轮整改完成；当前存档仍保留原工作室位置，不视作自动迁移；后续实际移动经正常presence记录。用户手动运行convert_to_operit.py更新导出；Python默认值需服务重启才加载。
- 当前：深渊天平引擎 · 互动叙事 / 大学默认驻地已统一并验证 / 收尾完成。

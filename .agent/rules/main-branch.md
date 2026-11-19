# 分支规则：修改完成必须落到 main 分支

- 每次修改完成并通过验证后，必须将变更合并并推送到 `main` 分支（`origin/main`），不得仅停留在功能分支。
- 流程：功能分支提交 → 切换 `main` → `git pull --ff-only` → 合并功能分支 → `git push origin main`。
- 仅提交本次任务涉及的文件；`data.json`、`存档/*`、`voice_config.json` 等运行时数据不得顺带提交。
- 推送前先完成该任务对应的语法/契约检查；推送失败时如实说明，不得强推（禁止 `--force`）。

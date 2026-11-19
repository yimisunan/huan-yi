【步骤编号】step_24
【对象】深渊天平正式互动项目 / 首次推送私有GitHub仓库
【上游依赖】logs/step_23.md SHA256 91feb3a9172f6858109f2a2129f277cb6db437ee2e0e65fa7a525aff1bdb9103
【授权】用户要求将当前项目推送至 https://github.com/yimisunan/geni-eni-cra.git；已有GitHub认证和push权限，仓库private=true且无分支。该指令已授权提交与推送，无需重复确认。
【目标】建立本地main，将当前项目首次提交并非强制推送至该仓库，核验远端main与本地提交一致。
【写入】新增.gitignore、README.md、.git元数据及本步plan/log/checks；临时执行脚本仅scene_chat_dev/tmp。
【范围】当前源码/规则/人物图/存档/音色配置/桥接产物和开发记录。排除凭据、缓存、音频运行物、旧备份与历史图集；GitHub普通Git不接受单文件超过100MiB，历史图集zip约153MB，保留本地。
【密钥处理】语音运行.py有硬编码FISH_API_KEY；仅暂存副本将赋值改为os.environ.get，原文件与原设备功能保持。扫描暂存对象不得出现该密钥，不打印其内容；原工作区预计仅该文件有本地差异。
【验收】仓库私有及push权限，remote空基线、已提交文件数/体量及秘密扫描、git fsck、远端SHA与main相等；不重复功能测试、不调用模型/TTS、不清档。
【恢复】新增本地.git/README/.gitignore可移除以撤销本地接入；已推送远端不自动删除或强推。如需撤销远端提交另按用户明确要求处理。

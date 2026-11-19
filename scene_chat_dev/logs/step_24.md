【步骤编号】step_24
【上游依赖】logs/step_23.md；用户明确授权推送至yimisunan/geni-eni-cra私有仓库。
【做了什么】建立main和origin，准备项目首个版本；GitHub账号yimisunan认证有效且仓库private/push=true，无额外授权需求。
【产物】.gitignore、README.md、本步plan/log/checks及本地Git元数据。
【验收证据】V1远端无分支，当前425个候选文件117957023字节，最大11977432字节；扫描候选blob无已知硬编码语音密钥或常见token/私钥。语音运行.py仅Git暂存副本读取FISH_API_KEY环境变量，本机原文件指纹不变。当前源码、规则、存档/音色、角色图片、桥接产物和开发记录收录；凭据/缓存/音频运行物/旧备份/历史图集排除。历史图集ZIP约153MB超过普通Git限制，原件本地保留。
【兼容处理】Android共享存储使用core.createObject=rename，命令仅对当前根设置safe.directory，不设全局通配信任；未改变业务文件或全局Git身份。
【V2】暂存扫描通过；本提交建立后执行非强制push，再通过远端SHA复核。最终推送结果后续据实际结果补齐。
【V3与回滚】新增本地Git接入可移除.git、.gitignore和README.md；不撤销已有业务文件，远端无自动删除/强推回滚。不输出或提交密钥，不自动重启Python服务。
【下一步】git push -u origin main，核验远端main等于本地HEAD并记录结果。

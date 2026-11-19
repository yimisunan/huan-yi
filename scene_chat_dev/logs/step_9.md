【步骤编号】step_9
【上游依赖】logs/step_8.md；用户审阅后授权独立可体验原型。
【做了什么】同场立绘层与小说式连续记录、三人接话、调查确认/取消、守密分支、预写自由输入、失败重试/刷新恢复、历史小结与纯阅读模式。
【产物】scene_chat_dev/src/continuous-stage/ 五份文件。独立8766服务已启动，终端sessionId 602833c9-d6df-4ab1-9701-fa84bc545377。
【验收证据】
V1：新目录原先不存在；六张fullbody/into原图只读定位；说明书备份字节校验一致：开发者功能/开发者说明书/开发者说明书.md.bak-20261118-213256。
V2：node --check通过；Python AST解析通过；HTTP三个页面资源200、data.json拒绝404；六原图在浏览器naturalWidth>0。真实DOM交互：三次接受后额度9，行动确认6→4；模拟失败保留pending且quota9，刷新显示原消息重试，接受后quota8；小结归档保留第一段事项。最终375×812、844×390、1440×900同源iframe检查均overflow=false、inputOverlap=false。Workspace Browser宿主视口为0且resize不支持，未做真实截图、真机键盘或屏幕阅读器验收。浏览器调用超过into默认预算，原因是可点击UI必要专项验收及一次缩放高度修正后复核；未执行全量测试。
V3：原型纯新增R0，关闭独立服务并删除新增目录可撤回；说明书R1备份可恢复。
【回滚方式】说明书：cp "开发者功能/开发者说明书/开发者说明书.md.bak-20261118-213256" "开发者功能/开发者说明书/开发者说明书.md"。原型免回滚（删新增物）；不影响现役5000。
【下一步】用户打开http://127.0.0.1:8766审阅视觉、手机键盘与节奏。未接正式主窗口、未迁移存档、未调用模型/TTS。数字全部演示。
【产物指纹】
{
  "index.html": {
    "bytes": 4886,
    "sha256": "177afe63fd50b3827ab0fc1d065ab615641d87512117edd1296a5616d1ef61fa"
  },
  "stage.css": {
    "bytes": 12138,
    "sha256": "564882caddce3dca01ae9e6d70943699dba4ec25ceca51d2abbf519c2615c152"
  },
  "stage.js": {
    "bytes": 14730,
    "sha256": "542ec56cd792a80615013a27b5b6693b2441d926491348467819815fb95d118c"
  },
  "serve.py": {
    "bytes": 1875,
    "sha256": "366e33bfb04d49e1fc011b75785f34271e26ac6800e7b0c1989dab06cf624f06"
  },
  "README.md": {
    "bytes": 1706,
    "sha256": "697d851ac93447b79e1f8c2c800b4266b842ab983cde3a6b9f091b0fb8e1e5da"
  }
}
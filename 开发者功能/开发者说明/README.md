# 深渊天平引擎 · 开发者说明（架构与工程手册）

> **文档性质**：本项目完整工程架构、协议契约、内部实现与维护开发参考手册。
> **非数据源硬声明**：本目录（`开发者功能/开发者说明/`）仅供人类开发者与工程维护代理阅读，**严禁作为 AI 剧情运行时提示词、世界书条目、知识库或上下文注入**。
> **适用版本基线**：协议 v3 / 资料交付 v2（`dual_stream_v2` + `single_prefix_v2`） / P3 纯 JSON 三轨自包含存档（`save_store.py`） / Operit 2 故事桥接插件 **v2.3.2**（API `2.0.0`，零角色卡依赖原生自托管 + 零漂移 KV 前缀锁定 + 人设稳态与暗线隔离 + Drama 3 声学全链路解禁）
> **面向玩家的日常使用手册**：见根目录 [`游玩指南.md`](../../游玩指南.md)；历史版本演进归档见 [`开发者功能/修订日志/README.md`](../修订日志/README.md)。

---

## 1. 项目一句话定位

**深渊天平引擎（Abyss Scale Engine）** 是一套运行在 **Android（Pydroid 3 + 浏览器）与 Operit 2 宿主生态** 上的本地互动叙事软件栈。它采用 **「前后端分离 + 确定性规则编译 + 双阶段流式演播/结算 + P3 纯 JSON 三轨自包含存档 + 单一原子事务账本」** 的工程架构：

- **AI 负责叙事与结构化语义提取**：前台主模型通过零漂移冻结前缀（Zone 0 规则 + 按会话冻结阶段桶切片与未解锁暗线物理脱敏的 Zone 1）与真差分增量（Zone 2 指纹去重 + `delta_patch` + 剥离未出口 `｜潜台词` 的历史上下文）实现高 KV 缓存命中与逐句微幕流式演播（默认全局激活成人感官沉浸基线，同时保持卷零轨 A 宿主主权；玩家显式标注 `【商城定制】` 时按需私密推演定制商品）；后台副模型（默认 Operit 2 `SUMMARY` 智能自适应思考槽）依托独立缓存静态结算 Schema（`stage2_system`）无状态提取事件标签、时间推进、操作、记忆摘要、`scene_state.shop_adds` 定制货品及 `persona_ooc`/`secret_premature_leak` 质量信号。
- **确定性 Python 引擎负责全部规则裁决与状态落盘**：所有数值计算、体力预扣与差额退款、游戏时钟、P3 三轨结构化记忆（永久锚点 / 情景幕 + 缓冲 / 分视角编年史）与知情隔离门禁、跨回合确定性机制（小憩/失眠/被动 Lv.2–3/首次与同质化免疫/秘密解锁）、两级红线与暗线/OOC 沉浸裁决门禁（`awaiting_review`）及崩溃恢复，均由本地 Python 经 `RoundStore` + `save_store` 唯一原子事务完成；模型从不直接写存档或口算数值。

---

## 2. 文档目录与按需阅读路径

本手册拆分为 **8 篇专题文档**，按「宏观架构 → 核心内核 → 规则数值 → 网络协议 → 前端与语音 → 桥接插件 → 数据规范 → 维护开发」由上至下逐层展开：

| 序号 | 文档 | 核心内容 | 建议阅读对象 |
|---|---|---|---|
| **01** | [`01_系统总架构与模块依赖.md`](01_系统总架构与模块依赖.md) | 系统四端拓扑、分层架构、全仓模块依赖图（含 `save_store.py` 与 `.round-runtime/story/prefs.json` 偏好持久化）、五大入口模式矩阵、一次互动的端到端时序图、运行环境与安全边界 | **所有人必读（入门首篇）** |
| **02** | [`02_核心引擎与事务存储层.md`](02_核心引擎与事务存储层.md) | `save_store.py` P3 纯 JSON 三轨自包含存档（`save_state.json` + `memory_store.json` + `近期演播.json`；含 `intimate` 隐私/衣着/痕迹/3×3 暗流矩阵 + v4 `host_phys`/`body_dev`/`keepsakes`、`deployed` 装置区、`shop.dynamic_catalog` 动态货架与纯暗箱 `npc_mind.resentment`/`last_shift_kind`）与轻量单向渲染、`RoundStore` 单一写者锁与双阶段 WAL 崩溃恢复、`story_compiler.py` **零漂移三区精编、全员暗线隔离、主模型道具可见性与三女主表里拉扯导演**（Zone 0 冻结规则 + 主/副模型独立自定义 Rule；Zone 1 剥离场外角色、按 `char_stage` 冻结桶切片心理脊梁并在实际松动 `羞耻<90` × 高好感高欲无裂痕时放行 `stage2`、按 `unlocked_secrets` 物理脱敏未解锁暗线；Zone 2 指纹去重、`_heroine_tension_directive()` 三女主专属 `【表里拉扯】` 与 `【真实裂痕】` 锚点及 `last_shift_kind` 防毒化、自然语言化 `held_items`/`deployed_items_*`/`delivered_gifts_to_cast` 清空显式 `[]` 与增量按需 `mentioned_items` 精确召回、对白 `｜潜台词` 清洗、一次性 `persona_drift_correction`、场外人物简报 `referenced_offstage`、按需 `sensory_lens`/`【商城定制】`、`anchor_history_mode` 与防复读滑窗；Stage 2 静态 `stage2_system` 缓存分离 `11,892 < 12,000`、动态 `free_text_item_hint`/`shop_custom_rule`、`persona_anchors` 与 `persona_ooc`/`secret_premature_leak` 检测；两级 `guardrail_check()` 守卫）、`interaction_runtime.py` `O(limit)` 倒序分页/v2 桥接懒跳过 `live.txt`/自动 GC 与 `室内氛围`/`use_recovery_item`/自由文本实证补发、`story_reading.py` 与 `relationship_query.py`（JSON/JSONL 进程内 `mtime` 缓存） | 后端 / 引擎 / 事务维护者 |
| **03** | [`03_数值结算与规则推进体系.md`](03_数值结算与规则推进体系.md) | `story_progression.py` 双态三档体力（日常 `5/10/15` / 亲密续演 **`1/2/3`** + `intimate_stamina_floor=10` + `vigor` 精力双池保底 + B 档放行 `C烈度_轻度/中度`）、`体力<=15` 断电硬锁、8 类登记操作（含 `室内氛围`、`inspect_deployed` 与 `keepsake_action`）、独立确定性系统商城（16 件分类商品含对齐后的 `SHOP-014` + 魅力折扣 + 剧情内 `【商城定制】` `T1～T4` 分阶、4 轴解锁与「道具非修改器」硬护栏）、活体导演 **75 拍**（2.1 双轨解耦 + `heroine_cd` 硬保底 + `subtext_leak` 日常遮掩铁律）、暗箱 `resentment` 裂痕累积与真诚照料/跨夜治愈、`injection_core.py` 全量数值闭环（**86 项事件**、双轴 SES/SIS 张力合成 `compute_tension_profile()`、五重安全闸 `AFFECTION_12` 欲拒还迎翻正与欲望 `+3` 悸动联动、v4 主角欲火/控欲、三女主 5 区身体开发与特色部位、5 阶魅力收支平衡、私密珍藏盒与 `advance_intimate_state`） | 游戏机制 / 规则 / 数值开发者 |
| **04** | [`04_后端服务与HTTP_SSE协议参考.md`](04_后端服务与HTTP_SSE协议参考.md) | Flask 引导与 `/api/story/*` + `/api/*` 双同源/CSRF 边界、`_EventHub` + Long-Polling + SSE、`DEFAULT_LIVE_LIMIT=10` 懒加载、`compact: true`、`_thumbs/` 缩略图、**35 个 `/api/story/*` 路由**（含 `POST /api/story/tasks/<key>/review-decision` 沉浸偏离裁决、`POST /api/story/preferences` 主/副模型自定义系统提示词、`anchor_history_mode`、`drift_review_mode`、`v2.3.2` 状态心跳 `prefs_epoch` 与 commit-only `session_meta`、一体化档案室 5 路由）与 **17 个语音路由（含 `POST /api/voice_design`、`retake`/`context_hint`/`voice_script`/`raw_params`）**、`scene_chat` SQLite 隔离 | API / 前后端联调 / 桥接联调开发者 |
| **05** | [`05_前端剧场与语音引擎架构.md`](05_前端剧场与语音引擎架构.md) | `main_template.html` + `story_client.js` + `story_client.css` 剧场前端（顶部锚定聚焦输入浮层 `#composerSheet`、无弹窗方案 A+B 落笔确认、`#stageCurtain.is-review` 双模式沉浸偏离裁决卡片、一体化双页签「档案室」、四档合理化闭环徽标、非遮挡双条 Disco 横幅、亲密 `1/2/3` 动态按钮与 `#sceneAtmospherePills`、**现值直显结算卡（`+delta → after`、无 6 项截断全属性与里程碑/预警胶囊、`state_notes` 与 `intel_consumed`/`shop_rejected` 明细）**、主/副模型自定义 Rule 编辑器、主角 8 项与名册 13 项全属性点按式沉浸释义手记、`sharp`/`playful`/`flustered` 情绪胶囊与三女主 `.msg-retake-btn` 单句重录）、**Drama 3 表现力全链路解禁（`DRAMA3_ROLE_PROFILES`、潜台词自动导演 `hiding:`、无标签 `context_hint` 兜底、`quality-guard` 戏剧释放、付费 TTS 预热门禁与 S2 反义词安全降级）**、`voice_manager.html`（A/B 盲测对照 + `✦ 母带工坊`） | 前端 / UI / 语音引擎开发者 |
| **06** | [`06_Operit2桥接插件架构.md`](06_Operit2桥接插件架构.md) | **Operit 2 官方知识库与宿主机制** + `local.story.operit_bridge` **v2.3.2** 零角色卡原生自托管架构（`model:chat` + `Tools.Chat.writeExtension/readExtension` + 5 个原生 Prompt/Tool/Worldbook 钩子）、`sanitizeOperitCorePrompt()` 宿主 `AGENTS.md`/工作区样板净化、`buildTailHook()` 清洗对白 `｜潜台词` 与 180 字导演词、`applyCommittedSessionMeta()` 透传 `char_stage`/`unlocked_secrets`、`awaiting_review` 静默 `markLiveDirty`、`prefs_epoch` 感知重卷、`getBridgeToken()` 内存缓存与 6s/30s 动态退避、侧边栏内嵌 `ComposeDslWebView` 剧场（`ui/theater.ui.js`）、工作区 UUID 绑定适配、双端 `CHAT` 槽改绑与三档副模型结算思考自适应（`auto/off/on`）及 `build.py` 静态门禁自动清旧打包 | Operit 2 插件 / 桥接协议开发者 |
| **07** | [`07_数据模型_SSOT与文件格式规范.md`](07_数据模型_SSOT与文件格式规范.md) | 单一事实来源（SSOT）依赖总图与派生视图同步规则、`txt文件/` 全量 JSON Schema（**86 项**事件注册表含 `AFFECTION_12`、`隐秘守卫注册表.json` 4 条暗线与话量基准、75 拍变故库 + `sensual_spark_matrix`、16 件商城、`intimate` 关系称谓库、8 项 `operations` 与 `vigor` 参数）、**P3 纯 JSON 三轨自包含存档（`save_state.json` 含暗箱 `npc_mind.resentment`/`last_shift_kind`、`memory_store.json`、`近期演播.json`）**与 `.round-runtime/save-slots/` 精简存档槽格式 | 设定维护 / 数据结构 / 存档工具开发者 |
| **08** | [`08_开发维护_测试排障与二次开发指南.md`](08_开发维护_测试排障与二次开发指南.md) | Pydroid 3 与 proot Alpine/Linux 双环境配置、改动与图片热替换生效路径、**45 项**全量测试清册（**41 个核心套件：Python 32 + Node 9**，含新增 `test_settlement_receipt_ui.py` 与 `test_stat_tension_and_subtext.py` + 4 项离线工具验收全绿）、常见二次开发清单、升级版 `存档清理器.py` 与 10 幕 `存档开局随机盲盒.py` CLI、崩溃恢复与 Git 交付流 | 接手维护 / QA / 二次开发工程师 |
| **附** | [`世界书关键字配置.txt`](世界书关键字配置.txt) | 24 条知识库世界书正则关键字与常驻配置全量对齐参考表（含按需条目 `narrative.intimate`，仅供参考、非数据源） | 设定维护 / 手动世界书维护者 |

### 快捷阅读路径

- **刚接手项目、快速建立全景认知**：`01` → `07` → `08`
- **排查「提交后卡住 / 校验失败 / 体力退款 / 断网恢复」**：`02` → `04` → `06`
- **调整数值平衡、新增事件标签、改体力/记忆/休息机制**：`03` → `07` → `08`
- **修改剧场界面、流式预览、语音朗读或调音台**：`05` → `04`
- **开发 Operit 2 桥接功能、新增设置项或更换模型调度策略**：`06` → `04` → `02`

### 上游宿主平台与官方知识库（Operit 2）

本项目桥接插件（`local.story.operit_bridge`，**v2.3.2**，API `2.0.0`）与手动世界书导出均面向 **Operit 2** 生态。涉及 Operit 2 宿主 API、ToolPkg 规范、Compose DSL 或原生钩子机制时，请参阅官方权威源（详见 [`06_Operit2桥接插件架构.md`](06_Operit2桥接插件架构.md) §1）：

- **Operit 2 官方下载页**：https://operit.app/#/v2/download
- **Operit 2 官方 GitHub 仓库**：https://github.com/AAswordman/Operit2 （`https://github.com/AAswordman/Operit2.git`）
- **Operit 2 官方知识库源码（GitHub）**：https://github.com/luojiaping/Operit2-wiki
- **Operit 2 官方在线知识库（Wiki）**：https://luojiaping.github.io/Operit2-wiki
- **本地离线 SDK 类型声明**：[`scene_chat_dev/types/`](../../scene_chat_dev/types/)（30 份官方 `.d.ts`）

---

## 3. 全仓目录与代码规模总览

项目核心运行时代码约 **3.7 万行**（纯标准库 + Flask + Requests + 原生 HTML/CSS/JS + Operit 2 QuickJS/Compose DSL，无前端打包器与重型框架依赖，适配移动端 Pydroid 3 零编译部署）。

```text
huan-yi/                                    # 项目根目录（Android: /storage/emulated/0/互动对话项目/Gemini网页版）
├── 语音运行.py                              # 唯一服务端启动入口：Flask 托管 + ?thumb=avatar|plate 缩略图 + Fish/Edge TTS（Drama 3 分角色参数解禁/潜台词自动导演/context_hint/retake 重录/S2 反义词安全降级/POST /api/voice_design 代理）+ CSRF + 静态白名单
├── save_store.py                           # P3 纯 JSON 三轨自包含存档存储层：save_state.json + memory_store.json + 近期演播.json 读写、懒/轻量单向 .txt 渲染与旧档迁移
├── story_service.py                        # 正式互动 HTTP/SSE/Long-Polling 服务（35 路由：含 awaiting_review 偏离裁决 /review-decision、DEFAULT_LIVE_LIMIT=10、compact 演播进度、prefs_epoch 心跳、张力韵律与相邻动作 context_hint 预热）
├── story_compiler.py                       # 只读确定性精编器：Zone 0 冻结规则 + 零漂移脱敏切片 Zone 1 + Zone 2 统一自然语言化道具/按需召回/指纹去重/潜台词清洗/一次性软纠偏 + Stage 2 独立缓存 stage2_system、自由文本道具提示与两级 guardrail_check
├── interaction_runtime.py                  # 正式连续互动协议：O(limit) 倒序分页、房间级 present_actors 历史可见性、v2 桥接跳过 170 KB live.txt 懒生成与自动 GC（保近 3 任务）、一次性 persona-correction.json 与 8 类登记操作（含 室内氛围 / use_recovery_item / 自由文本实证守卫）
├── story_progression.py                    # 确定性资源与推进：双态三档体力(日常5/10/15·亲密1/2/3 + floor 10 + vigor双池)、断电<=15硬锁、活体导演(75拍+subtext_leak遮掩铁律)、16件商城+剧情内【商城定制】T1~T4分阶锁门与非修改器硬护栏
├── round_runtime.py                        # RoundStore 单一写者事务引擎：可重入 POSIX 锁、_ENGINE_CODE_CACHE、2PC WAL、亲密态 B 档放行与 scene_state 校验
├── injection_core.py                       # 底层数值与存档引擎：9 大数值系统 + v4 成人深度机制（主角欲火控欲/5区身体开发与特色部位/5阶魅力收支平衡/私密珍藏盒/advance_intimate_state）
├── story_reading.py                        # 任务级原文提取投影、过期缓存清理与行级读回执认证器
├── relationship_query.py                   # 方向性亲属称谓查询（含 intimate 私密层）、进程内 mtime JSON/JSONL 缓存与 known_by 秘密隔离视图生成器
├── scene_chat.py                           # 隔离实验场景聊天服务（.scene-chat/ SQLite）
├── scene_world.py                          # 旧存档只读隔离导入器（兼容 P2/P3 存档结构）
│
├── main_template.html                      # 正式剧场首页（顶部聚焦浮层 #composerSheet、收墨撤回坞 #inkCommitDock、#stageCurtain 含 .is-review 沉浸偏离裁决、一体化档案室 #newGameDialog、#sceneAtmospherePills、六大档案中心）
├── story_client.js                         # 正式剧场前端主逻辑（#stageCurtain.is-review 裁决交互、一体化档案室、方案A+B无弹窗确认、Drama 3 潜台词透传/相邻动作兜底/三女主 .msg-retake-btn 重录/180字导演词隐藏与新情绪胶囊、付费 TTS 预热门禁与 v4 面板）
├── story_client.css                        # 剧场设计系统（.stage-curtain.is-review 琥珀金审校态、.msg-retake-btn 重录按钮与 sharp/playful/flustered 情绪胶囊、一体化档案室、5区开发条与珍藏盒卡片、noir/ivory 双主题）
├── voice_client.js                         # 共享语音传输库（支持 context_hint/voice_script/retake/raw_params 与 designVoice()）
├── voice_manager.html                      # /admin 声学工坊（音色与 A/B 盲测 / ★ 收藏夹 / 参数微调 / ✦ 母带工坊 4 页签）
├── scene_chat.html                         # /scene-chat 极简独立实验页
│
├── 存档开局随机盲盒.py                      # P3 10 幕精修去剧透序幕池（高反差英文导演词开场白、日常 Option B 校准、房内 present_actors 隔离、差异化首环任务、CLI argparse）
├── 存档清理器.py                            # 2PC P3 新档初始化 + .round-runtime/save-slots/ 精简可回档存档槽管理（CLI --list-backups/--restore/--scenario）
├── 一键同步GitHub.py                        # 手机端纯标准库增量同步工具
│
├── txt文件/                                # 权威设定、规则、配置与现用资源（SSOT）
│   ├── 互动运行配置.json                    # 唯一运行参数源（locations、aliases、intimate_continuation_costs 1/2/3 + floor 10 + vigor_*、8 项 operations、director 双轨保底与三档节奏预设）
│   ├── 隐秘守卫注册表.json                  # 全员暗线秘密与话量基准唯一 SSOT（S01～S04 surface_cover/unlocked_branch/leak_patterns/裁决文案 + 4 人 voice_budgets）
│   ├── 世界变故库.json                      # 活体世界导演 2.1 统一数据源（75 拍：含脱敏 T1 手机亮屏、T2 min_biz 门控、12 条 sensual_hook、31 条 erotic_accident、sensual_spark_matrix）
│   ├── 系统商城目录.json                    # 16 件分类商品目录（含可复用 SHOP-013、已对齐引擎的 SHOP-014、pack_qty 与 unlock_req）
│   ├── 商业情报目录.json                    # 商业嗅觉一次性情报唯一目录
│   ├── 事件注册表.json                      # 6 组 85 个事件标签与算分参数唯一原源（含 HOST_16 魅力精进与 SHAME_02 校准）
│   ├── 关系称谓库.json & 查询.jsonl         # 血缘/社会/法理事实、秘密知情名单与四场合（含 intimate）称谓查询
│   ├── 场景交流规范.md / 全局执行法典.md / 一键注入指南.txt / 提示词.md / 故事检索索引.md
│   ├── character_phoneme_map.json          # 角色易错多音人名音素映射表（沈知韫/知韫/徐承邺/承邺，语音运行.py 自动加载）
│   ├── 知识库/{世界观类,叙事判断,系统标签类,角色类}.json   # 4 个 ST-v1 格式权威知识库（含三层解耦角色档案、英文优先高反差四象限声演与可切片三阶心理脊梁）
│   └── image/                              # 现用视觉素材（含 _thumbs/ 36 张 WebP 预生缩略图与 .nomedia）
│
├── 存档/                                   # P3 纯 JSON 三轨自包含累积事实层（save_state.json + memory_store.json + 近期演播.json 与单向渲染只读 .txt）
├── data.json & voice_config.json           # 派生运行时快照与角色语音配置
├── Operit世界书导出/                       # 手动入口世界书派生产物（24 条同步）
├── scene_chat_dev/                         # Operit 2 桥接源码（v2.3.2）、成品包与核心回归测试
│   ├── local.story.operit_bridge/          # 插件 v2.3.2 源码（零角色卡原生自托管 + sanitizeOperitCorePrompt 样板净化 + 潜台词与180字导演词清洗/char_stage透传/awaiting_review洁净切窗 + ui/theater.ui.js 内嵌剧场）
│   ├── build.py                            # 打包脚本（含零依赖与 JS 语法门禁）→ artifacts/故事桥接-continuous-2.3.2.toolpkg
│   ├── src/scene_live/ & legacy_visibility.json
│   └── tests/ & run_tests.sh               # 30 个 Python 单测 + 9 个 Node 桥接测试套件（另加 开发者工具 4 项验收，共 43 项全绿）
│
└── 开发者功能/                             # 统一开发文档、变更归档与离线工具（非 AI 数据源，不散落根目录）
    ├── 开发者说明/                          # 【本目录】完整工程开发者说明书体系（含 世界书关键字配置.txt 与 语音引擎升级方案/）
    ├── 修订日志/                            # 压缩归档日志
    └── 开发者工具/                          # 世界书编辑器.html、音频截取工具.html、voice_design_generator.py 与独立验收脚本
```

### 运行时自动生成目录（均在 `.gitignore` 中排除）

| 目录/文件 | 归属模块 | 职责 | 能否清空？ |
|---|---|---|---|
| `.cache/fish_api_key.json` | `语音运行.py` | 玩家通过首页系统设定或 `/admin` 保存的本地 Fish API Key 缓存（`0600` 原子写入，受 `.gitignore` 与 `一键同步GitHub.py` 保护） | **用户私有密钥缓存**（可在网页清除，切勿提交到仓库） |
| `.round-runtime/` | `round_runtime.py` / `story_service.py` / `interaction_runtime.py` | `lock`、`state.json` 幂等账本、`journal.json`、`reset-journal.json`、`save-epoch.json`、`interaction/` 全量演播归档与进度、`story/` 任务队列、交付/审计凭证与 `prefs.json`（含主/副模型无上限自定义系统级 Rule、`context_budget` 与 `tts_prewarm_paid` 偏好） | **日常切勿手清**（含超出近 16 幕的历史归档与在途事务）；`存档清理器.py` 重置新档自动保留 `prefs.json`；若仅拷贝 `存档/` 到新设备缺失此目录，服务可零 500 自动从 `存档/近期演播.json` 与 `save_state.json` 冷启恢复并单调续号 |
| `.scene-chat/` | `scene_chat.py` / `scene_world.py` | 独立实验场景 SQLite（`state.sqlite3`、`world/state.sqlite3`）与任务资料包 | 与正式存档隔离；新档重置时一并清理 |
| `txt文件/.story-reading/` | `story_reading.py` / `interaction_runtime.py` | 任务级原文提取与 `live.txt` / 索引缓存（v2 桥接模式自动跳过 ~170 KB `live.txt` 落盘，并由自动 GC 仅保留近 3 个任务目录） | 新档重置时自动清理 |
| `语音仓库/` | `语音运行.py` | `voice_repo.json` 用户长期收藏音色库（按需懒创建） | **用户资产，不可清空** |
| `日志/` | `injection_core.py` / `round_runtime.py` / `story_service.py` | 旧完整回合推演日志 `Round_<N>_<hash>.txt` 与 `story_error.log` | 历史/排障记录 |
| `vosi/` | `语音运行.py` | Edge-TTS 临时 mp3（合成后即时删除，启动时清 6h 以上残留） | 纯临时目录 |
| `.sync-backup/` | `一键同步GitHub.py` | 最近 5 次 GitHub 同步前备份（用于 `--rollback`） | 同步回滚备份 |

---

## 4. 五大核心工程设计原则

理解本代码库前，务必先掌握贯穿全部模块的五条架构铁律：

1. **单一事实来源（SSOT）与派生校验**：所有规则、事件参数、关系称谓、知识库条目、运行配置均有唯一权威源；任何派生视图（`关系称谓查询.jsonl`、指南中的 `【注册表生成表】`、`operit_worldbook_深渊天平.json`、运行时 Zone 0/1 编译结果）要么在运行期校验字节/SHA-256 一致，要么由确定性脚本单向生成，**绝不允许手工双源维护**。
2. **模型输出永远是数据，永非可执行代码或信任事实**：桥接插件把模型回复作为纯文本/JSON 数据回传服务端；服务端按白名单、长度硬顶、SHA-256 来源指纹、听众隔离和红线守卫逐项校验。流式预览只驻留服务端 RAM，在最终事务落盘前绝不成为正式事实。
3. **单一原子写者（Single-Writer + 2PC WAL）**：所有对正式存档（`存档/`、`data.json`、`tasks.json`、`interaction/*`）的变更必须通过 `RoundStore._locked()`（进程内 `RLock` + 跨进程 `fcntl.LOCK_EX`）与 `journal.json` 双阶段提交完成；`data.json` 永远最后发布，崩溃重启自动依据 `phase` 执行 Redo 或 Rollback。
4. **预扣托管（Escrow）与零白扣承诺**：提交行动先原子预扣体力并保存扣前记忆库 Base64 快照及指纹；取消、超时、校验失败或启动中断时原子退款；若存档在期间被外部篡改，则进入 `refund_pending` 拒绝猜测覆写。
5. **模型无关的零漂移前缀冻结与真差分传输（KV Cache 友好）**：v2.3 架构严格贯彻「动静分离」——Zone 0 冻结规则（含可选主模型自定义 Rule）与 Zone 1 仅保留当前在场核心人设及静态关系称谓（彻底剥离场外角色、会逐轮漂移的时钟/线索/动态称谓锁），并由桥接插件在 `registerSystemPromptComposeHook` 中先剥离 Operit 宿主自动塞入的 `AGENTS.md` 与工作区样板（同时保留必要工具声明），使同场景连续多轮的 `system` 前缀 SHA-256 保持 100% 恒定；所有动态状态（含 `offstage_references` 场外简报）均在 Zone 2 经指纹去重与 `delta_patch` 真差分发送；Stage 2 后台结算同步拆出独立缓存的静态 `stage2_system` Schema 与瘦身载荷，面向所有主流模型通用降低前缀重算与 Token 开销。

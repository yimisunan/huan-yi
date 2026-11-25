# 04 · 后端服务与 HTTP / SSE / Long-Polling 协议参考

> **非数据源声明**：本文件为开发者架构参考文档，严禁作为 AI 剧情运行时提示词或世界书注入。
> **覆盖模块**：[`语音运行.py`](../../语音运行.py)、[`story_service.py`](../../story_service.py)、[`scene_chat.py`](../../scene_chat.py)、[`scene_world.py`](../../scene_world.py)。

---

## 1. 服务启动与路由装配架构

整个后端以单个 Flask 实例运行（无 Blueprint，按函数注册到同一 `app`）：

1. **入口 [`语音运行.py`](../../语音运行.py)**：
   - `app = Flask(__name__, static_folder=None)`（关闭默认静态目录，改用白名单路由），`MAX_CONTENT_LENGTH = 5 MiB`。
   - 调用 `register_story_routes(app, BASE_DIR)`（挂载正式互动路由与全局 `/api/story/*` 安全中间件，实例存 `app.extensions['story_service']`）。
   - `register_story_routes` 内部自动调用 `register_scene_routes(app, root, service)`（挂载实验场景路由，实例存 `app.extensions['scene_chat']`）。
   - 启动时顺序执行：`_initialize_config()` → `_cleanup_temp_audio()`（清 `vosi/` 中超过 6h 的临时 mp3）→ 1.5s 后异步唤起浏览器打开 `http://127.0.0.1:5000` → `app.run(host='127.0.0.1', port=5000, threaded=True)`。

### 1.1 `/api/story/*` 统一安全边界与错误映射（[`story_service.py:1539-1585`](../../story_service.py#L1539-L1585)）

对**全部 `/api/story/*`（含 `/api/story/scene/*`）**生效的 `@app.before_request` / `@app.after_request` / `@app.errorhandler`：

| 检查项 | 规则 | 失败状态码 |
|---|---|---|
| 重置熔断 `_reset_guard()` | `.round-runtime/reset-journal.json` 存在则拒绝所有请求 | `400` (`RecoveryError`) |
| Loopback 主机限制 | `request.host` 主机名必在 `{'127.0.0.1', 'localhost', '::1'}` | `403` |
| 同源防 CSRF | 若含 `Origin` 头必须等于 `request.host_url.rstrip('/')`；拒绝 `Sec-Fetch-Site: cross-site` | `403` |
| Worker 鉴权（路径含 `/worker/`） | 请求头 `X-Story-Bridge` 经 `hmac.compare_digest` 匹配 `.round-runtime/story/bridge-key.json` | `403` |
| 浏览器写接口（非 GET 且非 Worker） | 必须带 `X-Story-Client: 1`（`403`）且 `Content-Type: application/json`（`415`） | `403` / `415` |
| 缓存禁止（`after_request`） | 全部响应附带 `Cache-Control: no-store` | — |
| 统一异常映射 | `rr.ConflictError` → `409 {"error": ...}`；其他 `rr.RoundError` / `RecoveryError` → `400 {"error": ...}`；`HTTPException` → 对应状态码 JSON；未捕获服务端异常由 `@app.errorhandler(500)` 兜底返 JSON `500`（生产环境绝不泄漏 HTML 堆栈页） | `400` / `409` / `4xx` / `500` |

### 1.2 语音与配置 `/api/*` 安全边界（[`语音运行.py`](../../语音运行.py)）

对非 `/api/story/*` 的语音与配置路由（`/api/fish_key`、`/api/voice_tier`、`/api/config`、`/api/voice_repo`、`/api/tts`、`/api/voices`、`/api/edge_voices`、`/api/fish_wallet`）统一施加 `@app.before_request` 防护：

| 检查项 | 规则 | 失败状态码 |
|---|---|---|
| Loopback 主机限制 | `request.host` 主机名必在 `{'127.0.0.1', 'localhost', '::1'}` | `403` |
| 同源防 CSRF | 若含 `Origin` 或 `Referer` 头必须匹配 `request.host_url.rstrip('/')`；拒绝 `Sec-Fetch-Site ∈ {'cross-site', 'same-site'}` | `403` |
| 写接口显式客户端头 | 非 `GET`/`HEAD`/`OPTIONS` 的变更接口（`POST/DELETE /api/fish_key`、`POST /api/voice_tier`、`POST /api/config`、`POST/PATCH/DELETE /api/voice_repo`、`POST /api/tts/prefetch`）强制要求 `X-Voice-Client: 1` | `403` |
| 密钥绝不回显与脱敏日志 | `/api/fish_key` 仅返回掩码指纹与来源（`cache`/`env`/`none`）；上游报错日志自动脱敏所有 `sk-` / Bearer 令牌；`/api/tts` 入口统一剥离 `｛表层台词｜真实潜台词｝` 仅朗读表层台词 | — |

---

## 2. 实时通信机制：`_EventHub`、Long-Polling、SSE 与内存预览

### 2.1 `_EventHub` 进程内发布/订阅（[`story_service.py:35-75`](../../story_service.py#L35-L75)）
- 基于 `threading.Condition()` 与环形事件缓冲 `_events`（最多保留最近 **96** 条），维护两条单调递增序号：
  - `seq`：全部客户端可见事件序号（`bridge_control`, `bridge_state`, `save_reset`, `task_state`, `committed`, `story_stream`）。
  - `worker_seq`：仅当 `publish(..., wake_worker=True)` 时递增（新任务入队 `queued`、实验场景入队/重试或网页下发 `bridge_control` 指令）。

### 2.2 Worker Long-Polling（`GET /api/story/worker/wait`, `L1158-1192, 1670-1680`）
- 取代传统 3 秒轮询，实现秒级领单与零空转功耗：
  1. 进接口立即检查 `_pending_flags()`（是否有正式 `queued` 任务、120s 内未确认的 `bridge_control` 指令，或 `scene_chat` SQLite 中的 `queued` 任务）。
  2. 有待办立即返回 `{wake: true, reason: "task"|"control", seq, worker_seq, has_task, has_control}`。
  3. 否则阻塞在 `hub.wait_worker(since_seq, timeout)`（`timeout` 钳位 `[0.2, 25.0]` 秒），被事件唤醒或超时后复查 `_pending_flags()` 返回。
  - `scene_chat.py` 在提交实验消息与重试时均同步调用 `story.hub.publish('scene_task', ..., wake_worker=True)`，实现实验任务秒级唤醒。

### 2.3 浏览器 SSE 推送流（`GET /api/story/stream`, `L1605-1629`）
- 查询参数 `?since=<seq>`（缺省取当前最新 `hub.seq`）；响应头 `Content-Type: text/event-stream`、`Cache-Control: no-store`、`X-Accel-Buffering: no`。
- 连接建立立刻发送 `event: ready\ndata: {"seq": N}\n\n`；此后每轮最长等 15s，超时发 `: keepalive\n\n`，有事件则推 `id: <seq>\nevent: <type>\ndata: <json>\n\n`。
- 推送事件类型：`story_stream`（流式预览帧）、`committed`（事务落盘完成）、`task_state`（任务状态变更）、`bridge_state`（桥接运行态/模型/配置变化）、`save_reset`（新档重置完成）。

### 2.4 纯内存 `_stream_preview` 与 `allow_settlement_retry` 协议
- **纯内存预览（[`stream_chunk()`](../../story_service.py#L1280-L1325)）**：
  - 仅在任务为 `live_interaction` 且处于 `generating`、持有合法租约时接受 `POST /api/story/worker/<key>/stream`。
  - 要求单调 `revision >= 0`（旧帧忽略）、`stage ∈ {'thinking', 'streaming', 'settling'}`，并按 `context['cast']` 过滤非法说话人与超长句（≤4000 字传输防呆）。
  - 数据仅存 `self._stream_preview` 内存字典，**绝不写入 `tasks.json` 或 `RoundStore`**；在 `new_game`、`claim`、租约超时、失败、取消或 `_finish()` 结束时立即 `_clear_preview()`。
- **后台结算原地重试协议（[`result()`](../../story_service.py#L1411-L1485)）**：
  - 双阶段第 1、2 次提交携带 `allow_settlement_retry: true` 与 `dual_stage_version: 1`；服务端在写入 `.result.txt` 切 `validating` 之前，先试运行 `ir.assemble()` 与 `ir.validate()`。
  - 若抛 `RoundError`（非 `ConflictError`）且错误原因**不含** Stage 1 前台/红线不可重试关键字（`'前台演播'` / `'红线拦截'` / `'角色不在场或代写玩家台词'` / `'动作角色不在场'` / `'旁白不能携带说话人'` / `'message.text'` / `'消息类型无效'` / `'剧情须为非空节点数组'`），判定为可重试的后台结算字段错（例外：错误含 `可补充 fallback_decision` 时，因前台正文与红线已通过，同样判定可重试，仅要求 Stage 2 补 `fallback_decision`）：**保留 `generating` 状态、租约与预扣不退**，返回 HTTP `200 {"retryable_settlement": true, "error": "...", "task": ...}`，供桥接原地重跑 `SUMMARY`（不重跑前台剧情）；若命中 Stage 1 不可重试错则立刻结束不烧 Stage 2 额度。

---

## 3. 全量 HTTP API 路由参考（共 68 个路由装饰器）

### 3.1 入口页面、静态白名单与语音路由（`语音运行.py`，16 装饰器 / 14 路径）

| 方法 | 路径 | 处理器 | 请求参数 / Body | 响应与说明 |
|---|---|---|---|---|
| `GET` | `/` | `index` | — | 返回 `main_template.html`（`Cache-Control: no-cache`） |
| `GET` | `/admin` | `admin` | — | 返回 `voice_manager.html` 声学工坊（`no-cache`） |
| `GET` | `/<path:filename>` | `public_file` | 路径参数 | 严格白名单：放行 8 个根/存档文件（页面/脚本/样式/`data.json` 返回 `no-cache`）、`txt文件/image/` 下合法图片及 `txt文件/audio/` 下合法音频（`Cache-Control: public, max-age=86400`）；拒绝 `..` 与隐藏路径（`404`） |
| `GET` | `/api/audio_assets` | `audio_assets_api` | — | 零配置扫描 `txt文件/audio/ambient/`，返回可用本地背景音景映射 |
| `GET`/`POST`/`DELETE` | `/api/fish_key` | `fish_key_api` | `POST`: `{api_key}`（须 `X-Voice-Client: 1`） | 查询/保存/清空受保护本地 Fish API Key 缓存 `.cache/fish_api_key.json`（`0600` 原子写入）；仅返 `{configured, source, masked}`，绝不回显明文 |
| `POST` | `/api/voice_tier` | `set_voice_tier` | `{tier: "free"|"pro"|"drama"}`（须 `X-Voice-Client: 1`） | 一键切换三女主音质分档（`free → s2.1-pro-free` / `pro → s2.1-pro` / `drama → drama-3`），`FREE_DEFAULT_ROLES`（`旁白/动作/徐志北`）保持免费档，原子写回 `voice_config.json` |
| `POST` | `/api/voice_routing` | `set_voice_routing` | `{protagonist_voice_enabled?, action_voice_mode?, action_voice_scope?}`（须 `X-Voice-Client: 1`） | 原子更新 `__settings__` 中的主角语音开关（默认 `false`）及旁白/动作分声道路由（`follow_narrator`/`separate`/`muted`、`all`/`heroines`） |
| `GET` | `/api/config` | `get_config` | — | 返回规范化后的 `voice_config.json`；文件损坏返 `503` |
| `POST` | `/api/config` | `save_config` | JSON 配置对象（须 `X-Voice-Client: 1`） | 校验、清空 `emotion`、原子覆写 `voice_config.json`；现有文件损坏返 `409` |
| `GET` | `/api/voices` | `get_voices` | `?search=` / `?title=` (≤80字) | 拉取 Fish 私有+公开音色列表（私有优先去重）与可用 `tts_models` |
| `GET` | `/api/edge_voices` | `get_edge_voices` | — | 动态枚举 Edge 中文音色（8s 超时降级静态列表）与不可用提示 |
| `GET` | `/api/fish_wallet` | `get_fish_wallet` | — | 查询 Fish 账户套餐与 API Credit 余额（6s 超时） |
| `GET` | `/api/voice_repo` | `get_voice_repo` | — | 读取 `语音仓库/voice_repo.json` 收藏音色列表 `{items, count}` |
| `POST` | `/api/voice_repo` | `add_voice_repo` | `{id, name?, note?}`（须 `X-Voice-Client: 1`） | 规范化并新增收藏音色（重复返 `409`） |
| `PATCH` | `/api/voice_repo` | `update_voice_repo` | `{id, name?, note?}`（须 `X-Voice-Client: 1`） | 更新指定收藏音色的名称与备注（未找到返 `404`） |
| `DELETE` | `/api/voice_repo` | `delete_voice_repo` | `?id=...`（须 `X-Voice-Client: 1`） | 删除指定收藏音色 |
| `GET`/`POST` | `/api/tts` | `tts_api` | `text`(1–12000), `voice`, `speaker?`, `emotion?`, `tts_model?`, `speed_scale?`, `expressive_boost?`, `stream?` | 剥离 `【】*`；仅 Fish 注入音素，非 `drama-3` 智能降级 XML 标签并抽取中文导演句英文控制词，支持生理韵律微调；Singleflight + 内存/磁盘 LRU + 4 并发槽 |
| `POST` | `/api/tts/prefetch` | `tts_prefetch_api` | `{items: [{text, voice, speaker?, speed_scale?, expressive_boost?}]}`（须 `X-Voice-Client: 1`） | 批量向后预热接下来 3 句台词，闲置槽位并发 2，100ms 快速超时放弃 |

### 3.2 正式互动、档案室、确定性交易、任务、流式推送与桥接路由（`story_service.py`，34 个路由）

> **统一行动与确定性交易分界**：地图移动、道具部分/整组赠予（`transfer_item`）、主动道具使用（`use_item`）、隐蔽装置部署/回收/远程查看（`deploy_item` / `retrieve_item` / `inspect_deployed`）、私密珍藏互动（`keepsake_action`）、剧情内 `【商城定制】` 进货、免费恢复道具与强制休息统一经 `POST /api/story/tasks` 进入 `story_progression.create()`；**档案室存档槽快照/回档/删除、系统商城兑换、动态进货下架、委托奖励领取、经验被动升级、商业情报获取与商业杠杆切换**为 0 体力、0 模型调用的纯确定性事务，经独立路由共用 `RoundStore` WAL 原子落盘并广播 SSE `committed` / `save_reset` / `shop_updated`。

| # | 方法 | 路径 | 鉴权 | 关键参数 / Body | 核心行为与返回 |
|---|---|---|---|---|---|
| 1 | `GET` | `/api/story/live` | 同源 | `?before=<seq>&limit=<1..60>` | 正式剧场快照（`DEFAULT_LIVE_LIMIT = 10` 倒序懒加载）：`world`（含 `weekday`、`buffs`、`vigilance`、`passive_tiers`、`secrets_unlocked`、`intel`、`shop_state`、`micro_states`、`physiology`、`intimate`、`active_costs`、`stamina_guard`、`host_charm_tier`、`body_zone_meta`、`keepsake_meta`、`items`、独立 `deployed_items`、`delivered_items`、`visual_assets`）、`settlement`、`playback`、`history`、`has_older`、`stream_preview`、`revision`、`bridge`、`save_epoch`、`interaction_protocol` |
| 2 | `GET` | `/api/story/stream` | 同源 | `?since=<seq>` | SSE 实时推送流（`ready` / `story_stream` / `committed` / `task_state` / `bridge_state` / `save_reset` / `shop_updated`） |
| 3 | `POST` | `/api/story/live/progress` | Client | `{save_epoch, segment_id, revealed, completed, catchup?}` | 单调步进演播进度并仅写入 `playback.json` 与 `存档/近期演播.json`，默认返回 `compact: true` 单幕轻量增量降低长局刷新开销 |
| 4 | `POST` | `/api/story/new-game` | Client | `{request_id, save_epoch, confirm:"new_game", scenario_id?, reroll_only?}` | 统一按 `experimental.lock → store._locked()` 锁序防 AB-BA 死锁；支持指定 10 序幕之一或随机抽取、`reroll_only` 仅在 `actions==0` 时零备份原地重抽序幕，否则自动保存轻量化 `auto` 存档槽后重建新档，发 `save_reset` 事件 |
| 5 | `GET` | `/api/story/prologues` | 同源 | — | 返回全部 10 组开局剧本元数据（`id/title/heroine/summary/sub_location/privacy/present_actors`）、当前开局 `current`、`actions`、`can_reroll` 与 `save_epoch` |
| 6 | `GET` | `/api/story/saves` | 同源 | — | 返回当前存档摘要 `current`（天数/时刻/地点/行动数/魅力/珍藏/剧本标题）、全部轻量化档槽 `slots[]` 与 `save_epoch` |
| 7 | `POST` | `/api/story/saves/snapshot` | Client | `{save_epoch, label?}`（备注 ≤60 字） | 零体力原子创建手工存档槽（`.round-runtime/save-slots/<slot_id>/`）并返回新档槽元数据 |
| 8 | `POST` | `/api/story/saves/restore` | Client | `{save_epoch, slot_id, confirm:"restore_save", request_id?}` | 按 `experimental.lock → store._locked()` 锁序先自动留存当前档 `pre_restore` 快照，再通过 2PC 回档至指定档槽、刷新 `save_epoch` 并广播 SSE `save_reset` |
| 9 | `DELETE` | `/api/story/saves/<slot_id>` | Client | `?save_epoch=...` 或 JSON `{save_epoch}` | 校验空闲与 `save_epoch` 后原子删除指定档槽目录 |
| 10 | `GET` | `/api/story/snapshot` | 同源 | — | 旧完整回合页面快照 |
| 11 | `GET` | `/api/story/tasks` | 同源 | — | 返回最新任务状态、桥接在线/配置视图、协议标志与 `save_epoch`/`service_epoch` |
| 12 | `GET` | `/api/story/tasks/<key>` | 同源 | Path `<key>` | 查询单个任务公开状态（`404` 表示不存在，供前端 `pending` 幂等恢复核查） |
| 13 | `POST` | `/api/story/tasks` | Client | `{request_id, base_revision, action, entry_mode, selection, operation?, save_epoch?, model_key?}` | 提交行动；支持 8 类登记操作及剧情内 `【商城定制】` 标签触发 |
| 14 | `POST` | `/api/story/tasks/<key>/cancel` | Client | `{}` | 取消任务，清预览并调用 `sp.refund()` 全额退还预扣体力 |
| 15 | `POST` | `/api/story/tasks/<key>/retry` | Client | `{model_key?}` | 沿用原 `request_id` 与输入重试失败/中断/冲突任务 |
| 16 | `GET` | `/api/story/shop` | 同源 | — | 合并静态 16 件商品与 `save_state.json["shop"]["dynamic_catalog"]` 动态货架，附带 4 轴 `unlock_req`（嗅觉/好感/最高堕落/魅力）、`unlocked_grade`（`T1～T4`）、魅力折扣、`points` 与 `can_transact` |
| 17 | `POST` | `/api/story/shop/redeem` | Client | `{request_id, base_revision, save_epoch, item_id}` | 确定性 0 体力兑换静态 `SHOP-*` 或动态 `DYN-*` 商品入囊（强制校验 4 轴 `unlock_req`、魅力折扣与 `pack_qty`），广播 SSE `committed` |
| 18 | `DELETE` | `/api/story/shop/dynamic/<item_id>` | Client | `?save_epoch=...` 或 JSON `{save_epoch?}` | 确定性下架并移除 `save_state.json["shop"]["dynamic_catalog"]` 中指定 `DYN-*` 商品，广播 SSE `shop_updated` |
| 19 | `POST` | `/api/story/task/claim` | Client | `{request_id, base_revision, save_epoch}` | 确定性 0 体力按 FIFO 顺序领取 `tasks.pending_items` 队列队首待发奖励入囊 |
| 20 | `POST` | `/api/story/passive/upgrade` | Client | `{request_id, base_revision, save_epoch, target}` | 确定性 0 体力将目标女主被动升阶 `Lv.N→Lv.(N+1)` |
| 21 | `POST` | `/api/story/intel/acquire` | Client | `{request_id, base_revision, save_epoch, intel_id}` | 确定性 0 体力获取一次性商业情报 |
| 22 | `POST` | `/api/story/intel/leverage` | Client | `{request_id, base_revision, save_epoch, armed, intel_id?}` | 确定性 0 体力武装/解除商业杠杆 |
| 23 | `GET` | `/api/story/bridge-info` | 同源 | — | 读取或懒生成 `.round-runtime/story/bridge-key.json` 返回 `{token}` |
| 24 | `POST` | `/api/story/bridge/control` | Client | `{action, ...}` | 下发桥接控制指令并 `wake_worker=True` |
| 25 | `POST` | `/api/story/worker/control` | Bridge | `{runtime, ack_id?, ack_error?}` | 插件每 6s 上报运行态与确认指令结果 |
| 26 | `GET` | `/api/story/worker/wait` | Bridge | `?since=<int>&timeout=<float>` | Long-Polling 等待剧情任务或控制指令 |
| 27 | `POST` | `/api/story/worker/claim` | Bridge | `{model?}` | 领取队首 `queued` 剧情任务，签发 120s `lease` |
| 28 | `POST` | `/api/story/worker/shop-inquiry/claim` | Bridge | `{}` | 兼容 `v2.1.8` 桥接插件的静默空返回路由（恒返 `{"inquiry": null}`，免重装 `.toolpkg`） |
| 29 | `POST` | `/api/story/worker/<key>/material` | Bridge | `{lease, chat_id, participant_id, ...}` | 颁发 v1 / v2 冻结资料与 `settlement_spec` |
| 30 | `POST` | `/api/story/worker/<key>/stream` | Bridge | `{lease, stage, messages?, revision?}` | 上报瞬时流式预览节点并广播 SSE `story_stream` |
| 31 | `POST` | `/api/story/worker/<key>/heartbeat` | Bridge | `{lease}` | 续期 `lease_until = now + 120` |
| 32 | `POST` | `/api/story/worker/<key>/preflight` | Bridge | `{lease, text, conversation_audit}` | v1 / 旧回合提交前读审计预检 |
| 33 | `POST` | `/api/story/worker/<key>/result` | Bridge | `{lease, text?, error?, conversation_audit?, timing?, allow_settlement_retry?}` | 提交最终结果或报错；通过审计/双阶段重试/装配后经 `RoundStore` 原子落盘 |
| 34 | `POST` | `/api/story/preferences` | Client | `{protagonist_style?, director_pacing?}` | 保存并广播玩家演播偏好（主角戏份风格与女主意外节奏 `slow/standard/frequent`）至 `.round-runtime/story/prefs.json` |

### 3.3 隔离实验场景与只读旧档导入路由（`scene_chat.py`，15 个路由）

| 方法 | 路径 | 处理器 | 职责说明 |
|---|---|---|---|
| `GET` | `/scene-live` | `scene_live_page` | 托管 `scene_chat_dev/src/scene_live/index.html`（同席交流候选页） |
| `GET` | `/scene-live/assets/<name>` | `scene_live_asset` | 仅放行 `live.css` / `live.js` |
| `GET` | `/scene-chat` | `scene_page` | 托管根目录 `scene_chat.html`（极简实验页） |
| `GET` | `/api/story/scene/connection` | `scene_connection` | 协议握手：`scene_protocol: 3`, `world_state_protocol: 1`, `world_mode: "isolated_read_only"` |
| `GET` | `/api/story/scene/world` | `scene_world` | `?id=` 查询隔离旧档快照及其相对当前正式存档的新鲜度（`source_current`） |
| `POST` | `/api/story/scene/world/import` | `scene_world_import` | 在实验空闲时调用 `LegacyWorld.import_latest()` 只读导入最新正式存档 |
| `GET` | `/api/story/scene/list` | `scene_list` | 列出 `.scene-chat/state.sqlite3` 中所有实验场景 |
| `GET` | `/api/story/scene` | `scene_snapshot` | `?id=` 获取指定（或最新）实验场景与最新任务 |
| `POST` | `/api/story/scene` | `scene_create` | 创建实验场景（1–2 位角色；绑定 `world_id` 时强制同地校验） |
| `POST` | `/api/story/scene/messages` | `scene_submit` | 提交实验发言（`request_id` 须以 `scene-` 开头；上限 24 轮 / 160 KB 包） |
| `GET` | `/api/story/scene/request/<key>` | `scene_request` | 按请求 ID 查单条实验任务 |
| `POST` | `/api/story/scene/retry/<key>` | `scene_retry` | 校验源指纹与存档基线未变后重试失败/中断的实验任务 |
| `GET` | `/api/story/scene/audit/<key>` | `scene_audit` | 查看已接受实验任务的完整文件工具覆盖审计 |
| `POST` | `/api/story/scene/worker/claim` | `scene_claim` | Worker 领取实验任务（租约 **660s**） |
| `POST` | `/api/story/scene/worker/<key>/<action>` | `scene_worker` | `heartbeat`(+660s) / `preflight` / `result`（核验包全行覆盖并提交到 `.scene-chat/state.sqlite3`） |

---

## 4. 实验隔离层：`scene_world.py`、`legacy_visibility.json` 与 `unresolved_source`

[`scene_world.py`](../../scene_world.py) 实现了**严格防污染、零臆测（Fail-Closed）**的只读存档导入器：

1. **共享锁零写副作用（[`read_lock()`](../../scene_world.py#L38-L64)）**：
   - 借用 `RoundStore.thread_lock` 与 `.round-runtime/lock` 的**共享读锁（`LOCK_SH`）**，**绝不**触发 `RoundStore._recover()` 或写入正式目录；若检测到 `journal.json` 或 `reset-journal.json` 直接抛 `RecoveryError`。
2. **内容寻址 SQLite 隔离库（`.scene-chat/world/state.sqlite3`）**：
   - `WAL + synchronous=FULL`；表 `imports` 与 `sources` 保存所有源文件（`存档/*.txt`, `存档/四层记忆.json`, `data.json`, `关系称谓库.json`, `legacy_visibility.json`）原始字节与 SHA-256，每次读取 `snapshot()` 均二次防篡改校验。
   - 一旦正式存档有任何变更，`assert_current()` 抛 `409 ConflictError`，旧实验场景自动锁定只读。
3. **`存档/四层记忆.json`（P2 嵌套 `layers.L1..L4`）与 `legacy_visibility.json` 精确指纹知情门禁（[`parse()`](../../scene_world.py#L206-L231)）**：
   - 优先无损读取 P2 `存档/四层记忆.json` 嵌套结构 `layers.L1..L4[].known_by`（兼容老式扁平顶层结构）；无 P2 `known_by` 时回落校验 `scene_chat_dev/src/legacy_visibility.json`（**运行时强依赖，不可删除**）中对应 SHA-256 的人工核定 `known_by` 与 `basis`；均未命中时 `known_by` 保持 `None`，并生成 `memory_visibility` 类型的 `unresolved_source`，绝不把未经审核的旧记忆泄露给 NPC。
4. **`unresolved_source` 零编造语义**：
   - 解析面板、位置、任务、记忆、道具时，遇到缺失区块、非法格式、未识别残留文本或边界不清，绝不猜测默认值或静默丢弃，而是原样记录 `{kind: "unresolved_source", domain, reason, origin: {path, sha256, start_line, end_line, raw}}`，交由 `/scene-live` 界面呈现给人类核查。

# Fish Audio 语音引擎深度升级方案（2026 官方文档核查版）

> 核查日期：2026-11-19  
> 官方权威文档来源：`https://docs.fish.audio/`（API Reference `/v1/tts`、Drama 3、Models Overview、Migrate from S1、Fine-grained Control、Realtime Streaming、Text to Speech Stream with Timestamps、Voice Design、Pricing & Rate Limits）

本文件夹汇总了针对 **「深渊天平」安卓本地互动叙事引擎** 的 Fish Audio 官方最新能力调研、参数勘误与可落地进阶方案。

## 已直接落地至当前主程序与调音台的升级

以下零侵入、向后兼容的新参数已同步接入根目录 [`语音运行.py`](../语音运行.py)、[`voice_client.js`](../voice_client.js) 与 [`voice_manager.html`](../voice_manager.html)（旧版 `voice_config.json` 无需手工迁移即可直接运行）：

1. **新增官方旗舰模型选择**：在 `s2.1-pro` / `s2.1-pro-free` 基础上新增 **`drama-3`**（可自然语言导演、支持局部词语标签）与 `s2-pro`。
2. **关键勘误标注**：官方 `Migrate from S1` 明确声明 `repetition_penalty` **仅对已弃用的 S1 生效，在 `s2.1-pro` / `s2.1-pro-free` 上已被忽略**；调音台已显式提醒，避免继续浪费时间微调无效参数。
3. **动态响度控制 `prosody.normalize_loudness`**：此前后端硬编码 `True`，导致 `[whispers]` / 轻声喘息被自动拉平回大音量；现已开放每角色独立开关，关闭后可真实保留贴耳低语与气声动态范围。
4. **音频编码、码率与采样率 (`format` / `mp3_bitrate` / `opus_bitrate` / `sample_rate`)**：支持 `mp3`（64/128/192 kbps）、`opus`（48 kHz 高效省流）、`wav`（无损母带）。
5. **文本规范化与语言 (`normalize` / `language`)**：支持显式指定 `zh-CN` 防止短中文数字/日期（如 `15:30`、`第1天`）误判规范化规则。
6. **进阶控制与质量守卫 (`max_new_tokens` / `early_stop_threshold` / `features: ["quality-guard"]` / `pronunciation_dictionary`)**：防止长情绪戏被截断、可选开启质量守卫、支持挂载云端发音词典。
7. **调音台快捷导演测试栏**：内置 S2.1 `[bracket]`、Drama 3 `<whisper>`/`<emphasis>`/`<slow>` 与中文音素 `<|phoneme_start|>yun4<|phoneme_end|>` 一键插入试听。

---

## 本目录进阶方案索引

| 文件 | 适用场景 | 实施优先级 | 成本影响 |
|---|---|---|---|
| [`01_参数与模型全景指南.md`](01_参数与模型全景指南.md) | 查清 2026 `/v1/tts` 全量参数、避开无效参数陷阱、按人设选型调参 | ★★★★★ 立即可用 | 零增费（合理混用 `s2.1-pro-free` 可降本） |
| [`02_Drama3导演语法与中文注音方案.md`](02_Drama3导演语法与中文注音方案.md) | 升级情感表演粒度（局部耳语/重音/停顿）+ 根治「沈知韫 / 徐承邺」等生僻字多音字误读 | ★★★★★ 强烈推荐 | 音素注音 $0；Drama 3 促销 $10/M 字节（原价 $50） |
| [`03_流式低延迟与时间戳字幕同步方案.md`](03_流式低延迟与时间戳字幕同步方案.md) | 消灭点按后等待黑窗（MSE 流式 + 下一节点预取 + SSE 时间戳卡拉 OK 高亮 + 多角色合批） | ★★★★☆ 体验飞跃 | 零增费（同单价） |
| [`04_VoiceDesign角色定制音色方案.md`](04_VoiceDesign角色定制音色方案.md) | 用自然语言直接定制四位主角专属高质量音色，无需四处找公开撞声 | ★★★★☆ 强烈推荐 | 极低（$0.01 / 次，每次可出 2~4 候选） |
| [`voice_design_generator.py`](voice_design_generator.py) | 一键调用 `/v1/voice-design` 批量试生成角色音色样本的独立工具脚本 | 按需手动运行 | 按次计费（需 `FISH_API_KEY`） |
| [`character_phoneme_map.json`](character_phoneme_map.json) | 面向本作角色名与常见多音字的中文带声调拼音注音映射表 | 可直接接入预处理 | $0 |

---

## 推荐组合策略（针对本项目最优性价比）

- **日常演播（高性价比）**：
  - **旁白**：`s2.1-pro-free`（$0 免费）+ `latency: "balanced"` + `language: "zh-CN"` + `mp3 128k`
  - **沈知韫 / 徐念薇**：`s2.1-pro`（或 `s2.1-pro-free`）+ `normalize_loudness: true` + `temperature: 0.58~0.64`
  - **苏婉青 / 亲密低语场景**：`s2.1-pro` + **`normalize_loudness: false`**（关键！）+ `speed: 0.92`
- **关键冲突 / 高压情感高光戏**：
  - 临时或专项切至 **`drama-3`**，利用 `<whisper>…</whisper>`、`<slow>…</slow>`、`[sigh]` 与中文/英文自然语言执导，表演细腻度远超传统句首情绪标签。
- **安卓端播放响应优化**：
  - 启用 `story_client.js` 内的 HTTP MSE 流式播放与下一节点有限预取（详见 `03_流式低延迟与时间戳字幕同步方案.md`），可将首字出声延迟压至 ~300–500ms。

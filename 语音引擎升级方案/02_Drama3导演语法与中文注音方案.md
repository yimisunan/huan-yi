# 02 · Drama 3 导演语法、中文音素注音与发音词典方案

## 一、Drama 3 独有表演控制能力（极度契合互动剧情）

`drama-3` 是 Fish Audio 2026 年 11 月全新推出的「可导演式 TTS 模型」，直接沿用现有 `POST /v1/tts`，只需将请求头 `model` 设为 `drama-3`（已在调音台模型下拉菜单内置）。

### 1. 自然语言导演指令（支持中文或英文）
与 S2.1 相比，Drama 3 可以直接理解「写给配音演员的戏前提示」，且指令语言不必与台词语言一致：

```text
[低声克制，像强压着情绪的集团董事长，语速略缓] 这件事先不要声张，等我核对完账目再说。
[soft, slightly hesitant, glancing away] 下午……我还是照原安排去看婆婆。
```

### 2. 句内声音与自然停顿
直接把呼吸、叹息、轻笑、停顿放在发生位置：
- `[sigh]` / `[sighing]` 轻叹
- `[gasp]` 抽气
- `[chuckle]` 轻哂
- `[breath]` 换气声
- `[break]` / `[long-break]` 短/长停顿

### 3. 局部词语成对标签（Drama 3 独家杀手锏）
以往 `[whispering]` 会把整句话都变成耳语；Drama 3 支持**仅对某几个字词变调**，精准还原潜台词与心理偏角：

支持的 7 种成对标签：
- `<whisper>…</whisper>`：仅这几个字贴耳低语
- `<soft>…</soft>`：柔和轻声带过
- `<emphasis>…</emphasis>`：意味深长地重读
- `<stress>…</stress>`：强重音落点
- `<slow>…</slow>`：刻意放慢语速
- `<fast>…</fast>`：紧张/急促加快
- `<forceful>…</forceful>`：施压、坚定发声

**本作实景示例**：
```text
沈知韫：集团的事你不用操心，先把<soft>早饭吃了</soft>。[break] 至于承邺那边，<slow><emphasis>我会处理</emphasis></slow>。
苏婉青：早饭已经盛好了。[sigh] 只是下午回主宅……<whisper>你别跟婆婆提我昨晚失眠的事</whisper>，好不好？
徐念薇：画还没干。<forceful>退半步。</forceful>[break] <soft>……沾到袖口洗不掉。</soft>
```

> **前端显示兼容提示**：若未来正式剧情台词引入 Drama 3 成对标签，只需在 `story_client.js` 显示渲染时过滤 `</?(?:whisper|emphasis|soft|fast|slow|stress|forceful)>`（同时保留完整原文送往 `/api/tts`），前端文字依然纯净无标签，耳中却能听到逐词级表演起伏。本轮已在 `story_client.js` 提前兼容该清洗规则！

---

## 二、中文生僻字与多音字精准注音（零成本根治读错名）

本作多位主角姓名与剧情词汇包含中文 TTS 高频误读字：
- **沈知韫**：「韫」正确读 **`yùn` (`yun4`)**，TTS 常误读为 `wēn`。
- **徐承邺**：「邺」正确读 **`yè` (`ye4`)**，偶发误读为 `yě` 或 `yí`。
- **高频多音字**：「重（`chóng` / `zhòng`）」、「行（`xíng` / `háng`，如银行/投行）」、「长（`zhǎng` 董事长 / `cháng`）」、「藏（`cáng` / `zàng`）」。

### 方案 A：行内中文音素标签（S2.1 与 Drama 3 均支持）
官方规则：使用带数字声调的汉语拼音（1=阴平、2=阳平、3=上声、4=去声、5=轻声），每字一个 `<|phoneme_start|>拼音<|phoneme_end|>` 标签，标点留在标签外：

```text
沈知<|phoneme_start|>yun4<|phoneme_end|>正在书房处理并购案。
徐承<|phoneme_start|>ye4<|phoneme_end|>打来了电话。
```

### 方案 B：Fish 平台云端发音词典（`pronunciation_dictionary` · 推荐长期使用）
1. 登录 `fish.audio` 网页端 → **Pronunciation Dictionaries** → 创建本作专属词典（如 `abyss_scales_zh`）。
2. 录入固定替换规则（可参考本目录 [`character_phoneme_map.json`](character_phoneme_map.json)）：
   - `沈知韫` → `沈知<|phoneme_start|>yun4<|phoneme_end|>`
   - `知韫` → `知<|phoneme_start|>yun4<|phoneme_end|>`
   - `徐承邺` → `徐承<|phoneme_start|>ye4<|phoneme_end|>`
   - `承邺` → `承<|phoneme_start|>ye4<|phoneme_end|>`
   - `董事长` → `董事<|phoneme_start|>zhang3<|phoneme_end|>`
3. 在平台发布词典后，将返回的 **Dictionary ID** 与 **Version** 直接填入本项目的「声学工坊」→「4. 高级推理、质量守卫与发音词典」，后端即会自动在每次 `/v1/tts` 请求时挂载 `pronunciation_dictionary`！

### 方案 C：后端轻量本地注音预处理（无需建云端词典）
若想完全在本地零配置生效，可在 `语音运行.py` 发送 Fish `/v1/tts` 前读取 [`character_phoneme_map.json`](character_phoneme_map.json)，仅对明确不会歧义的专属词（`沈知韫`、`知韫`、`徐承邺`、`承邺`）做自动替换，同时不影响页面上显示的汉字原文。

---

## 三、Audio Infill（局部重录修音 · 面向精品剧情收藏）

Fish Audio 新增了 **`POST /v1/audio/infill`** 接口（搭配 Drama 3）：当某一段精彩长语音里仅有一两个字念错或语气不对时，无需整段重新生成，只需传入原音频、修改后的完整文本及需替换片段，即可只重绘该区间并无缝拼接原声线。适合未来做「经典桥段音声收藏馆」功能。

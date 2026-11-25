# 04 · Fish Audio Voice Design 角色专属音色定制方案

## 一、为什么推荐 Voice Design？

Fish Audio 官方现已开放 **`POST /v1/voice-design`**（模型 `voice-design-1`）：
- **价格极低**：**`$0.01 / 次成功请求`**，且单次请求可直接生成 `n = 1 ~ 4` 个候选音色样本，只收一次 `$0.01`（约 7 分人民币！）。
- **零撞声 / 高度贴合人设**：无需在公开库大海捞针翻找可能随时下架或风格跑偏的社区音色，直接用精确的声学描述生成贴合本作四位核心人物的定制音色；挑中满意的样本后，上传至 Fish 平台 **Create Voice**（`POST /model`）即可获得永久私有 `reference_id`，随后一键填入调音台的「全局语音仓库」。

---

## 二、官方接口参数速览

- 端点：`POST https://api.fish.audio/v1/voice-design`（仅接受 `application/json`）
- 鉴权：`Authorization: Bearer $FISH_API_KEY`
- 核心字段：
  - `instruction`（必填，1~2000 字符）：声学与性格描述提示词
  - `reference_text`（可选，≤300 字符）：试听样句文本
  - `language`（可选）：`"zh"`
  - `n`（1~4，默认 2）：一次生成的候选音色数量
  - `speed`（`>0 ~ 3.0`，默认 `1.0`）：语速基准
  - `num_step`（1~128，默认 `32`）：扩散步数，推荐 `32 ~ 48`
  - `guidance_scale`（默认 `2.0`）：提示词遵循度，推荐 `2.0 ~ 2.6`
  - `seed`（可选整数）：复现实验用随机种子

---

## 三、贴合本作《角色类.json》的四套精调设计提示词

以下提示词严格依据 `txt文件/知识库/角色类.json` 中的【Fish声学覆盖】与人物气质编写：

### 1. 沈知韫（38 岁千亿集团董事长 · 沉稳温润的守密者）
- **声学目标**：成熟、低饱和、稳定呼吸、温柔却带掌权者分寸，禁甜腻撒娇、禁尖锐播音腔。
- **instruction**：
  > Mature refined Chinese woman in her mid-30s, corporate chairwoman. Warm low-mid register, velvety and restrained timbre, steady unhurried breathing, articulate Mandarin with gentle poise and quiet authority. Calm, composed, never shrill or overly sweet, intimate natural close-mic studio recording.
- **reference_text**：
  > 这件事先不急着定论。坐下来把热茶喝了，外面下着雨，剩下的交给我来处理。

### 2. 苏婉青（25 岁顶层公寓少奶奶 · 外柔内敛、轻气声反差）
- **声学目标**：天生妩媚底色与娇柔内敛克制共存，气息轻软温婉，自然口语，禁幼态卖萌。
- **instruction**：
  > Soft-spoken graceful Chinese woman in her mid-20s. Delicate breathy warm voice, naturally alluring yet shy and restrained delivery, gentle pacing with soft pauses and subtle vulnerability. Polite, feminine, intimate modern Mandarin, never childish or cartoonish, clean close-mic studio quality.
- **reference_text**：
  > 那就留下来呀。有人陪着吃早饭，我也高兴。先坐吧，咖啡还是温水？

### 3. 徐念薇（20 岁艺术学院校花 · 清冷干净、情绪内收）
- **声学目标**：清冷克制、字句干脆、略带微凉骨感与书卷气，熟悉时语调可缓和。
- **instruction**：
  > Cool, poised young Chinese woman around 20 years old, fine arts university student. Clear, crisp, understated timbre with restrained emotion and clean diction, slightly cool and calm resonance, unhurried dry elegance. Natural conversational Mandarin, never hyper or sugary, clean studio recording.
- **reference_text**：
  > 画布还没干，别靠太近。桌上那杯茶还是温的，有话直接说就好。

### 4. 旁白（黑金胶片叙事 · 低沉克制、电影质感）
- **声学目标**：略慢略沉的近场叙述男声/中性声，像深夜胶片电影画外音，不抢戏、无播音腔夸张起伏。
- **instruction**：
  > Calm, understated Chinese male narrator in his early 30s for literary cinema drama. Warm low-mid baritone, measured unhurried pacing, clean neutral Mandarin without news-anchor exaggeration or dramatic overacting. Subtle close-mic intimacy, steady breath, quiet room tone.
- **reference_text**：
  > 窗外细雨未停，落地灯在木质桌面投下一圈暖光。她把餐巾放在桌边，抬眼等你的意思。

---

## 四、使用方式

工具目录已附带可直接运行的独立脚本 [`开发者功能/开发者工具/voice_design_generator.py`](../../开发者工具/voice_design_generator.py)：

```bash
# 先设置环境变量 FISH_API_KEY
export FISH_API_KEY="你的密钥"

# 仅生成某一位角色（每次仅 $0.01，默认生成 3 个候选试听音频）
python3 开发者功能/开发者工具/voice_design_generator.py --role 苏婉青 --candidates 3

# 列出内置的全部角色配方
python3 开发者功能/开发者工具/voice_design_generator.py --list
```

试听满意后，打开 `https://fish.audio` → **Create Voice** 上传生成的候选样本即可拿到专属 `reference_id`，再粘入本项目的 **声学工坊 (`/admin`) → 全局语音仓库**。

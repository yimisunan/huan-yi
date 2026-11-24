# 05 · Fish Audio Plus 网页积分永久素材制作教程

> **配套说明**：本教程对应主程序 [`语音运行.py`](../语音运行.py)（本地音景/拟音静态服务、`GET /api/audio_assets`、序幕离线母带 `local-master` 秒播、非 Drama 3 声学智能降级、动态生理韵律调制）与 [`story_client.js`](../story_client.js)（双轨交叉淡入淡出音景、TTS 自动 Audio Ducking、事件拟音、角色原声试听）。
> **目录保护**：[`一键同步GitHub.py`](../一键同步GitHub.py) 与 `.gitignore` 已将 `txt文件/audio/` 设为本地专属目录，同步或 `--prune` 绝不覆盖删除你的本地素材。

---

## 目录结构（启动 `语音运行.py` 自动创建，含防安卓音乐扫描 `.nomedia`）

```text
txt文件/audio/
├── .nomedia                # 阻止安卓系统音乐 App 扫描游戏拟音
├── ambient/                # 5 首循环氛围底噪：calm_home / rain_night / tension_stealth / intimate_warm / aftermath_quiet
├── sfx/                    # 10 条电影拟音：scale_chime / page_turn / door_lock / footsteps / phone_vibrate / teacup_clink / silk_rustle / heartbeat_low / climax_swell / unlock_chime
├── samples/                # 4 条角色干声备份兼原声试听：沈知韫.mp3 / 苏婉青.mp3 / 徐念薇.mp3 / 旁白.mp3
└── prologues/              # （可选）10 套开局序幕 Drama 3 离线母带：<scenario_id>_{dialogue|narration|action}.mp3
```

---

## 第一步：5 首循环氛围底噪（`txt文件/audio/ambient/`，每首 60～90 秒）

登录 `https://fish.audio/app` → **Music**（务必关闭人声/选 Instrumental）或 **Sound Effects**：

| 文件名 | 自动触发情境 | 推荐复制 Prompt |
|---|---|---|
| `calm_home.mp3` | 白天日常（主宅/公寓/公司） | `Minimalist warm ambient piano and soft low cello pad, slow unhurried nocturnal luxury apartment mood, subtle room reverb, very gentle and sparse, no drums, no vocals, seamless calm background loop` |
| `rain_night.mp3` | 夜晚/黄昏/雨夜画室/阳台 | `Gentle steady night rain tapping softly against tall floor-to-ceiling glass window indoors, very faint warm room air ambience, cozy quiet luxury study at midnight, no thunder, seamless loop` |
| `tension_stealth.mp3` | 徐承邺在场/警惕≥50/潜行 | `Dark minimalist thriller suspense underscore, very subtle low sub-bass pulse, distant soft mechanical watch ticking, restrained cold tension, cinematic noir atmosphere, no loud hits, no vocals, seamless loop` |
| `intimate_warm.mp3` | 亲密升温/高欲/体液锁定 | `Sensual velvet dark ambient drone, warm breathy analog synth pad with sparse muted Rhodes chords, slow intimate midnight bedroom atmosphere, hushed and deeply atmospheric, no percussion, no vocals, seamless loop` |
| `aftermath_quiet.mp3` | 高潮余韵/生理断电（体力≤15） | `Ultra-soft late night aftermath ambient, delicate fading warm electric piano harmonics, hushed quiet bedroom stillness, tender melancholic calm, very low density, no drums, no vocals, seamless loop` |

---

## 第二步：10 条电影拟音 SFX（`txt文件/audio/sfx/`，每条 1～4 秒）

`https://fish.audio/app` → **Sound Effects**：

| 文件名 | 自动触发时机 | 时长 | 推荐复制 Prompt |
|---|---|---|---|
| `scale_chime.mp3` | 确认行动 / 抉择落印 | 1～2s | `Soft delicate brass balance scale weight settling gently with a subtle muted metallic chime, refined dark luxury UI sound, clean short decay` |
| `page_turn.mp3` | 点击推进下一句 | 1s | `Very soft crisp heavy linen paper page turning gently in a quiet room, subtle realistic foley, low volume` |
| `door_lock.mp3` | 剧情出现反锁/落锁/暗闩 | 1～2s | `Quiet wooden bedroom door closing softly followed by a crisp solid brass deadbolt lock click indoors, intimate quiet house foley` |
| `footsteps.mp3` | 剧情出现门外/走廊脚步声 | 2～3s | `Soft muffled footsteps walking slowly along a wooden hallway outside a closed door, quiet house at night, subtle tension` |
| `phone_vibrate.mp3` | 剧情出现手机震动/来电 | 2s | `Short muted smartphone vibration buzz twice on a solid wooden desk in a quiet room, realistic close foley` |
| `teacup_clink.mp3` | 剧情出现茶杯/瓷杯轻碰 | 1～2s | `Delicate porcelain teacup gently placed onto a ceramic saucer, crisp subtle clink in a quiet dining room` |
| `silk_rustle.mp3` | 剧情出现丝袜/真丝/衣摆滑落 | 1～2s | `Soft delicate silk fabric and sheer satin rustling gently close to microphone, quiet intimate bedroom foley` |
| `heartbeat_low.mp3` | 防线失守 / 生理断电脉冲 | 3～4s | `Deep muted low-frequency human heartbeat thumping slowly three times, close warm cinematic tension, soft sub-bass` |
| `climax_swell.mp3` | 绝顶清算 / 内射 / 确诊怀孕脉冲 | 3～4s | `Warm emotional cinematic low swell with soft shimmering airy shimmer fading gently into hush, intimate dramatic highlight, not loud` |
| `unlock_chime.mp3` | 堕落蚀刻 / 阶梯破锁脉冲 | 2～3s | `Dark resonant subtle glass-and-bronze harmonic chime unlocking softly with warm dark reverb, refined noir cinema sting` |

---

## 第三步：Voice Design 定制 4 位角色音色 + 留底干声（`txt文件/audio/samples/`）

> **提示**：不要浪费时间做 PVC（仅网页可用、不支持 API）。请直接使用 **Voices → Create Voice → Voice Design**（详见同目录 [`04_VoiceDesign角色定制音色方案.md`](04_VoiceDesign角色定制音色方案.md)），定型后复制 `reference_id` 填入 `/admin`，并在网页端 **Text to Speech (Drama 3)** 用下方三语态稿各导出一条干声存至 `txt文件/audio/samples/<角色名>.mp3`（兼作人物羁绊页 $0 原声试听与到期后无损重建备份）：

1. **`txt文件/audio/samples/沈知韫.mp3`**：
   - Voice Design：`Mature refined Chinese woman in her mid-30s, corporate chairwoman. Warm low-mid register, velvety and restrained timbre, steady unhurried breathing, articulate Mandarin with gentle poise and quiet authority. Calm, composed, never shrill or overly sweet, intimate natural close-mic studio recording.`
   - 干声稿：`[沉稳从容，语速平缓] 这件事先不急着定论。坐下来把热茶喝了，外面雨还没停，剩下的交给我来处理就好。[短停顿] [低声克制，带着一丝倦意] 这么晚还没睡，怎么又跑来书房站着？顺手把门带上，别让走廊的冷气吹进来。[短停顿] [声音压得很低，克制中透出一点失守的微颤] <whisper>……别靠这么近，这儿还在主宅里，让人看见像什么样子。</whisper>`

2. **`txt文件/audio/samples/苏婉青.mp3`**：
   - Voice Design：`Soft-spoken graceful Chinese woman in her mid-20s. Delicate breathy warm voice, naturally alluring yet shy and restrained delivery, gentle pacing with soft pauses and subtle vulnerability. Polite, feminine, intimate modern Mandarin, never childish or cartoonish, clean close-mic studio quality.`
   - 干声稿：`[声音轻柔，客气温婉] 那就留下来呀。承邺这周都在外地忙，屋里怪冷清的，有人陪着吃顿早饭我也高兴。[短停顿] [轻声试探，带着几分拘谨] 先坐吧，咖啡还是温水？刚烧好的，小心烫着手。[短停顿] [气息变软，带着羞怯与轻颤] <whisper>志北……你手怎么这么凉，先松开一点，等会儿电话要是打过来……</whisper>`

3. **`txt文件/audio/samples/徐念薇.mp3`**：
   - Voice Design：`Cool, poised young Chinese woman around 20 years old, fine arts university student. Clear, crisp, understated timbre with restrained emotion and clean diction, slightly cool and calm resonance, unhurried dry elegance. Natural conversational Mandarin, never hyper or sugary, clean studio recording.`
   - 干声稿：`[清冷克制，字句干净] 画布还没干，别靠太近。桌上那杯茶还是温的，有话直接说就好，别踩到地上的炭笔稿。[短停顿] [声音放轻，略带别扭的缓和] 外面下这么大雨，伞搁门后那只铁桶里就行，头发湿了也不擦一下。[短停顿] [气息微紧，嘴硬却藏着轻微发抖] <soft>……放手，颜料蹭到你袖口上了。我又没说让你走。</soft>`

4. **`txt文件/audio/samples/旁白.mp3`**：
   - Voice Design：`Calm, understated Chinese male narrator in his early 30s for literary cinema drama. Warm low-mid baritone, measured unhurried pacing, clean neutral Mandarin without news-anchor exaggeration or dramatic overacting. Subtle close-mic intimacy, steady breath, quiet room tone.`
   - 干声稿：`[平静低沉，电影画外音] 窗外细雨未停，暖黄落地灯在实木桌面投下一圈克制的光晕。空气里飘着淡淡茶香与微凉水汽，她合上文件夹，指尖在桌沿停了半拍，抬眼静静等你开口。`

---

## 第四步（可选）：10 套开局序幕 Drama 3 离线母带（`txt文件/audio/prologues/`）

优先制作 10 条女主开场对白（放进目录即自动命中，0ms 秒播、$0 API 费；如需补全旁白/动作，使用同前缀 `_narration.mp3` / `_action.mp3`）：

- `zhiyun_friday_study_dialogue.mp3`（沈知韫）：`[低声克制，带着点倦意] 这么晚还没睡？外头冷气大，顺手把门带上，过来陪妈坐会儿。`
- `nianwei_saturday_studio_dialogue.mp3`（徐念薇）：`[清冷平淡，声音压轻] 还没睡？别踩到地上的画稿，这么晚下来有事直说。`
- `wanqing_apartment_night_dialogue.mp3`（苏婉青）：`[声音轻柔，略微拘谨] 这么晚还跑一趟，先坐吧。承邺这周在外地忙，屋里怪冷清的……<soft>要我替你换杯热茶吗？</soft>`
- `wanqing_friday_visit_dialogue.mp3`（苏婉青）：`[声音轻柔，带点客套分寸] 志北，今天也在家呀。我按规矩过来看看妈，顺便带了些她爱吃的点心。`
- `zhiyun_sunday_noon_dialogue.mp3`（沈知韫）：`[沉稳从容] 都到齐了，先落座吧。厨房那边还要一会儿，志北坐妈手边。`
- `zhiyun_rain_balcony_dialogue.mp3`（沈知韫）：`[低声克制，语速微缓] 雨刚歇，风里还带着潮气。怎么这个点上来找我？`
- `nianwei_sunday_evening_studio_dialogue.mp3`（徐念薇）：`[清冷克制，字句干净] 门没锁，进来就行。晚饭前我还要收完这些习作，帮我递一下纸巾？`
- `wanqing_apartment_morning_dialogue.mp3`（苏婉青）：`[声音轻柔，带着几分试探] 早餐再等几分钟就好。你难得上午过来，先喝杯黑咖啡，还是我给你兑点热牛奶？`
- `nianwei_rain_studio_dialogue.mp3`（徐念薇）：`[声音平淡，带着一丝意外] 下这么大雨怎么跑这儿来了？<soft>伞搁门后那只铁桶里，别把颜料弄湿了。</soft>`
- `zhiyun_late_office_dialogue.mp3`（沈知韫）：`[低声克制，带着难得的松弛] 这层早就没人了，怎么还专程跑一趟？<soft>先搁茶几上，坐下歇口气。</soft>`

---

## 第五步：验证生效

1. 启动 `语音运行.py`，确认已自动生成 `txt文件/audio/` 四子目录与 `.nomedia`；
2. 将音频放入对应目录后，打开网页「档案 → 系统 → 本地音景与离线母带」点击 **刷新检测**；
3. 轻触舞台任意处解锁移动端音频即可听到氛围音景 + 人声 Audio Ducking + 拟音与离线序幕秒播。

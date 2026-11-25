#!/usr/bin/env python3
"""独立工具：调用 Fish Audio Voice Design API (/v1/voice-design) 为本作角色生成定制候选音色。

仅在用户手动执行时调用外部网络；不修改项目存档或 voice_config.json。
运行前请设置环境变量 FISH_API_KEY。
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path
import requests

API_URL = "https://api.fish.audio/v1/voice-design"

CHARACTER_RECIPES = {
    "沈知韫": {
        "instruction": (
            "Mature refined Chinese woman in her mid-30s, corporate chairwoman. "
            "Warm low-mid register, velvety and restrained timbre, steady unhurried breathing, "
            "articulate Mandarin with gentle poise and quiet authority. Calm, composed, "
            "never shrill or overly sweet, clean intimate close-mic studio recording."
        ),
        "reference_text": "这件事先不急着定论。坐下来把热茶喝了，外面下着雨，剩下的交给我来处理。",
        "speed": 0.96,
    },
    "苏婉青": {
        "instruction": (
            "Soft-spoken graceful Chinese woman in her mid-20s. Delicate breathy warm voice, "
            "naturally alluring yet shy and restrained delivery, gentle pacing with soft pauses "
            "and subtle vulnerability. Polite, feminine, intimate modern Mandarin, "
            "never childish or cartoonish, clean close-mic studio quality."
        ),
        "reference_text": "那就留下来呀。有人陪着吃早饭，我也高兴。先坐吧，咖啡还是温水？",
        "speed": 0.94,
    },
    "徐念薇": {
        "instruction": (
            "Cool, poised young Chinese woman around 20 years old, fine arts university student. "
            "Clear, crisp, understated timbre with restrained emotion and clean diction, "
            "slightly cool and calm resonance, unhurried dry elegance. Natural conversational Mandarin, "
            "never hyper or sugary, clean studio recording."
        ),
        "reference_text": "画布还没干，别靠太近。桌上那杯茶还是温的，有话直接说就好。",
        "speed": 0.97,
    },
    "旁白": {
        "instruction": (
            "Calm, understated Chinese male narrator in his early 30s for literary cinema drama. "
            "Warm low-mid baritone, measured unhurried pacing, clean neutral Mandarin without "
            "news-anchor exaggeration or melodrama. Subtle close-mic intimacy, steady breath."
        ),
        "reference_text": "窗外细雨未停，落地灯在木质桌面投下一圈暖光。她把餐巾放在桌边，抬眼等你的意思。",
        "speed": 0.94,
    },
    "徐承邺": {
        "instruction": (
            "Confident, expressive young Chinese man around 27 years old from a wealthy family. "
            "Bright mid-range masculine voice, slightly brash and eager to impress, lively natural Mandarin "
            "conversational cadence with clear projection, clean studio recording."
        ),
        "reference_text": "妈，外地这边的渠道我已经谈得差不多了，等我回来再跟您细说。",
        "speed": 1.02,
    },
}


def save_candidates(role: str, data: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = data.get("candidates") or data.get("audios") or data.get("samples") or data.get("items") or []
    saved = 0
    for idx, item in enumerate(candidates, 1):
        b64 = None
        ext = "wav"
        if isinstance(item, str):
            b64 = item
        elif isinstance(item, dict):
            b64 = item.get("audio_base64") or item.get("audio") or item.get("data")
            fmt = str(item.get("format") or "wav").lower()
            if fmt in {"mp3", "wav", "opus"}:
                ext = fmt
        if not b64:
            continue
        raw = base64.b64decode(b64)
        path = out_dir / f"{role}_candidate_{idx}.{ext}"
        path.write_bytes(raw)
        print(f"  ✓ 已保存样本: {path} ({len(raw) // 1024} KB)")
        saved += 1
    meta_path = out_dir / f"{role}_response_meta.json"
    meta = {k: v for k, v in data.items() if k not in {"candidates", "audios", "samples"}}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def main():
    parser = argparse.ArgumentParser(description="Fish Audio Voice Design 角色定制音色生成器")
    parser.add_argument("--list", action="store_true", help="列出全部内置角色声学配方")
    parser.add_argument("--role", choices=list(CHARACTER_RECIPES.keys()), help="指定生成角色")
    parser.add_argument("--candidates", type=int, default=3, help="候选数量 (1~4，默认 3)")
    parser.add_argument("--steps", type=int, default=36, help="扩散步数 num_step (1~128，默认 36)")
    parser.add_argument("--guidance", type=float, default=2.2, help="提示词遵循度 guidance_scale (默认 2.2)")
    parser.add_argument("--seed", type=int, default=None, help="可选随机种子")
    parser.add_argument("--out", default="开发者功能/开发者工具/voice_design_samples", help="样本输出目录")
    args = parser.parse_args()

    if args.list:
        for name, cfg in CHARACTER_RECIPES.items():
            print(f"- {name}: speed={cfg['speed']} | sample={cfg['reference_text']}")
        return

    if not args.role:
        parser.error("请使用 --role 指定角色，或使用 --list 查看内置角色。")

    api_key = os.environ.get("FISH_API_KEY", "").strip()
    if not api_key:
        print("错误：请先在环境变量中设置 FISH_API_KEY。", file=sys.stderr)
        sys.exit(1)

    recipe = CHARACTER_RECIPES[args.role]
    payload = {
        "instruction": recipe["instruction"],
        "reference_text": recipe["reference_text"],
        "language": "zh",
        "n": max(1, min(4, args.candidates)),
        "speed": recipe["speed"],
        "num_step": max(1, min(128, args.steps)),
        "guidance_scale": max(0.0, args.guidance),
    }
    if args.seed is not None:
        payload["seed"] = args.seed

    print(f"正在调用 Fish Audio Voice Design 为「{args.role}」生成 {payload['n']} 个候选音色…")
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(10, 90),
    )
    if resp.status_code != 200:
        print(f"请求失败 HTTP {resp.status_code}: {resp.text[:400]}", file=sys.stderr)
        sys.exit(2)

    data = resp.json()
    count = save_candidates(args.role, data, Path(args.out))
    if count == 0:
        raw_out = Path(args.out) / f"{args.role}_raw.json"
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"接口已返回，但未匹配到默认音频字段，原始响应已保存至 {raw_out}")
    else:
        print(f"完成：共导出 {count} 份样本，试听后可上传至 fish.audio 创建私有音色并写入调音台。")


if __name__ == "__main__":
    main()

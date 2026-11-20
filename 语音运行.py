import os
import json
import re
import time
import uuid
import threading
from pathlib import Path
import requests
import copy
import hashlib
import io
import queue
from collections import OrderedDict
import webbrowser
from threading import Timer
from flask import Flask, request, send_file, jsonify, abort, Response


try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_DIR = os.getcwd()
CONFIG_FILE = os.path.join(BASE_DIR, 'voice_config.json')
TTS_MAX_TEXT_LENGTH = 12000
TEMP_AUDIO_MAX_AGE_SECONDS = 6 * 60 * 60
FILE_WRITE_LOCK = threading.RLock()
FISH_HTTP_TIMEOUT = (8, 45)
TTS_WAIT_SECONDS = 60
TTS_CACHE_MAX_BYTES = 32 * 1024 * 1024
TTS_CACHE_MAX_ENTRIES = 64
TTS_STATE_LOCK = threading.Lock()
TTS_SLOTS = threading.BoundedSemaphore(2)
TTS_CACHE = OrderedDict()
TTS_INFLIGHT = {}
TTS_CACHE_BYTES = 0

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

from story_service import register_story_routes
register_story_routes(app, BASE_DIR)

# ==========================================
# Fish Audio API 配置（单人本地使用：密钥内置后端，不走额外 .env）
# ==========================================
FISH_API_KEY = os.environ.get("FISH_API_KEY", "sk-fish-ZIt5QhP-mrAPI1xXHSjRvG15Bvo5cFKMDN92S0S33Zg")
FISH_BASE_URL = "https://api.fish.audio"
FISH_TTS_MODEL = "s2.1-pro"  # 默认付费模型；实际请求可由 voice_config.json 的 __settings__.fish_tts_model 覆盖
FISH_TTS_MODELS = [
    {"id": "s2.1-pro", "name": "S2.1 Pro（官方生产主力 · 高质稳定）"},
    {"id": "s2.1-pro-free", "name": "S2.1 Pro Free（同质免费开发档）"},
    {"id": "drama-3", "name": "Drama 3（自然语言导演 / 局部标签旗舰）"},
    {"id": "s2-pro", "name": "S2 Pro（上一代开源 S2）"},
]
FISH_FREE_TTS_MODEL = "s2.1-pro-free"
FISH_DEFAULT_VOICE_ID = ""
FISH_AUDIO_FORMATS = {
    "mp3": {"mime": "audio/mpeg", "ext": "mp3", "default_rate": 44100, "rates": (32000, 44100)},
    "opus": {"mime": "audio/ogg", "ext": "opus", "default_rate": 48000, "rates": (48000,)},
    "wav": {"mime": "audio/wav", "ext": "wav", "default_rate": 44100, "rates": (8000, 16000, 24000, 32000, 44100)},
}
FISH_DEFAULT_STYLE = {
    "speed": 1.0,
    "volume": 0,
    "normalize_loudness": True,
    "temperature": 0.72,
    "top_p": 0.75,
    "latency": "normal",
    "chunk_length": 220,
    "min_chunk_length": 40,
    "repetition_penalty": 1.18,
    "condition_on_previous_chunks": True,
    "normalize": True,
    "language": "",
    "format": "mp3",
    "mp3_bitrate": 128,
    "opus_bitrate": -1000,
    "sample_rate": 44100,
    "max_new_tokens": 1024,
    "early_stop_threshold": 1.0,
    "quality_guard": False,
    "pronunciation_dictionary_id": "",
    "pronunciation_dictionary_version": "",
}


# Edge 免费链路里稳定可用的中文旁白默认（云泽/晓甄多数环境不在免费列表）
EDGE_DEFAULT_VOICE = "zh-CN-YunyangNeural"
EDGE_FALLBACK_VOICES = [
    "zh-CN-YunyangNeural",  # 播音中性 · 旁白首选
    "zh-CN-YunjianNeural",   # 稳重男声
    "zh-CN-YunxiNeural",     # 阳光男声
    "zh-CN-XiaoyiNeural",    # 温柔女声
    "zh-CN-XiaoxiaoNeural",  # 最通用兜底
]

# 静态展示名（动态列表拿不到时用）
EDGE_VOICE_LABELS = {
    "zh-CN-YunyangNeural": "云扬 (专业播音男声 · 旁白首选)",
    "zh-CN-YunjianNeural": "云健 (成熟稳重男声)",
    "zh-CN-YunxiNeural": "云希 (阳光磁性男声)",
    "zh-CN-XiaoyiNeural": "晓伊 (温柔亲切女声)",
    "zh-CN-XiaoxiaoNeural": "晓晓 (通用女声 · 起伏略大)",
    "zh-CN-liaoning-XiaobeiNeural": "晓北 (东北女声)",
    "zh-CN-shaanxi-XiaoniNeural": "晓妮 (陕西女声)",
    "zh-TW-HsiaoChenNeural": "晓臻 (台湾女声)",
    "zh-TW-HsiaoYuNeural": "晓雨 (台湾女声)",
    "zh-TW-YunJheNeural": "云哲 (台湾男声)",
    "zh-HK-HiuMaanNeural": "晓曼 (粤语女声)",
    "zh-HK-HiuGaaiNeural": "晓佳 (粤语女声)",
    "zh-HK-WanLungNeural": "云龙 (粤语男声)",
}

# 明确标记：这些名字常被误当成 Edge 免费音色，实际多数环境不可用
EDGE_UNAVAILABLE_HINTS = {
    "zh-CN-YunzeNeural": "云泽不在 Edge 免费音色列表（多为 Azure 专属）",
    "zh-CN-XiaozhenNeural": "晓甄不在 Edge 免费音色列表（多为 Azure 专属）",
}

default_config = {
    "__settings__": {
        "fish_tts_model": FISH_TTS_MODEL
    },
    "沈知韫": {
        "voice": "fish:",
        "voice_ids": [],
        **FISH_DEFAULT_STYLE,
        "emotion": ""
    },
    "徐念薇": {
        "voice": "fish:",
        "voice_ids": [],
        **FISH_DEFAULT_STYLE,
        "emotion": ""
    },
    "苏婉青": {
        "voice": "fish:",
        "voice_ids": [],
        **FISH_DEFAULT_STYLE,
        "emotion": ""
    },
    "旁白": {
        "voice": "fish:",
        "voice_ids": [],
        "tts_model": FISH_FREE_TTS_MODEL,
        **FISH_DEFAULT_STYLE,
        "speed": 0.94,
        "temperature": 0.58,
        "top_p": 0.66,
        "latency": "balanced",
        "chunk_length": 260,
        "min_chunk_length": 55,
        "repetition_penalty": 1.25,
        "emotion": ""
    },
    "default": {
        "voice": "fish:",
        "voice_ids": [],
        **FISH_DEFAULT_STYLE,
        "emotion": ""
    }
}


def _is_fish_voice(voice_str):
    return isinstance(voice_str, str) and voice_str.startswith("fish:")


def _is_edge_voice(voice_str):
    return isinstance(voice_str, str) and voice_str.startswith("edge:")


def _normalize_edge_param(value, kind):
    """统一 Edge rate/pitch/volume 格式，避免空串或错误符号导致无音频。"""
    # 电影旁白默认：略慢略沉，避免播音加速腔
    default_rate = default_config.get("旁白", {}).get("rate", "-8%")
    default_pitch = default_config.get("旁白", {}).get("pitch", "-4Hz")
    if value is None:
        value = ""
    s = str(value).strip()
    if kind == "rate":
        if not s:
            return default_rate
        if not s.endswith("%"):
            # 允许传 5 / +5
            try:
                n = int(float(s.replace("%", "")))
                return f"{n:+d}%"
            except Exception:
                return default_rate
        # 保证有正负号
        num = s[:-1]
        try:
            n = int(float(num))
            return f"{n:+d}%"
        except Exception:
            return default_rate
    if kind == "pitch":
        if not s:
            return default_pitch
        s = s.replace("hz", "Hz").replace("HZ", "Hz")
        if not s.lower().endswith("hz"):
            try:
                n = int(float(s))
                return f"{n:+d}Hz"
            except Exception:
                return default_pitch
        num = s[:-2]
        try:
            n = int(float(num))
            return f"{n:+d}Hz"
        except Exception:
            return default_pitch
    if kind == "volume":
        if not s:
            return "+0%"
        if not s.endswith("%"):
            try:
                n = int(float(s.replace("%", "")))
                return f"{n:+d}%"
            except Exception:
                return "+0%"
        num = s[:-1]
        try:
            n = int(float(num))
            return f"{n:+d}%"
        except Exception:
            return "+0%"
    return s


def _clamp_float(value, default, lo, hi):
    try:
        n = float(value)
        if n != n:
            return default
        return max(lo, min(hi, n))
    except Exception:
        return default


def _clamp_int(value, default, lo, hi):
    try:
        n = int(float(value))
        return max(lo, min(hi, n))
    except Exception:
        return default


def _normalize_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


def _clean_token(value, pattern, max_len=64):
    s = str(value or "").strip()
    if not s or len(s) > max_len:
        return ""
    return s if re.fullmatch(pattern, s) else ""


def _normalize_fish_cfg(cfg):
    cfg = cfg or {}
    latency = str(cfg.get("latency", FISH_DEFAULT_STYLE["latency"]) or FISH_DEFAULT_STYLE["latency"]).strip()
    if latency not in {"low", "normal", "balanced"}:
        latency = FISH_DEFAULT_STYLE["latency"]
    chunk_length = _clamp_int(cfg.get("chunk_length"), FISH_DEFAULT_STYLE["chunk_length"], 100, 300)
    min_chunk_length = min(_clamp_int(cfg.get("min_chunk_length"), FISH_DEFAULT_STYLE["min_chunk_length"], 0, 100), chunk_length)
    fmt = str(cfg.get("format", FISH_DEFAULT_STYLE["format"]) or "mp3").strip().lower()
    if fmt not in FISH_AUDIO_FORMATS:
        fmt = "mp3"
    fmt_meta = FISH_AUDIO_FORMATS[fmt]
    mp3_bitrate = _clamp_int(cfg.get("mp3_bitrate"), FISH_DEFAULT_STYLE["mp3_bitrate"], 64, 192)
    if mp3_bitrate not in (64, 128, 192):
        mp3_bitrate = 128
    try:
        opus_bitrate = int(float(cfg.get("opus_bitrate", FISH_DEFAULT_STYLE["opus_bitrate"])))
    except Exception:
        opus_bitrate = -1000
    if opus_bitrate not in (-1000, 24000, 32000, 48000, 64000):
        opus_bitrate = -1000
    try:
        sample_rate = int(float(cfg.get("sample_rate", fmt_meta["default_rate"])))
    except Exception:
        sample_rate = fmt_meta["default_rate"]
    if sample_rate not in fmt_meta["rates"]:
        sample_rate = fmt_meta["default_rate"]
    return {
        "speed": round(_clamp_float(cfg.get("speed"), FISH_DEFAULT_STYLE["speed"], 0.5, 2.0), 2),
        "volume": round(_clamp_float(cfg.get("volume"), FISH_DEFAULT_STYLE["volume"], -20, 20), 1),
        "normalize_loudness": _normalize_bool(cfg.get("normalize_loudness"), FISH_DEFAULT_STYLE["normalize_loudness"]),
        "temperature": round(_clamp_float(cfg.get("temperature"), FISH_DEFAULT_STYLE["temperature"], 0, 1), 2),
        "top_p": round(_clamp_float(cfg.get("top_p"), FISH_DEFAULT_STYLE["top_p"], 0, 1), 2),
        "latency": latency,
        "chunk_length": chunk_length,
        "min_chunk_length": min_chunk_length,
        "repetition_penalty": round(_clamp_float(cfg.get("repetition_penalty"), FISH_DEFAULT_STYLE["repetition_penalty"], 1.0, 2.0), 2),
        "condition_on_previous_chunks": _normalize_bool(cfg.get("condition_on_previous_chunks"), FISH_DEFAULT_STYLE["condition_on_previous_chunks"]),
        "normalize": _normalize_bool(cfg.get("normalize"), FISH_DEFAULT_STYLE["normalize"]),
        "language": _clean_token(cfg.get("language"), r"[A-Za-z0-9_-]{1,35}", 35),
        "format": fmt,
        "mp3_bitrate": mp3_bitrate,
        "opus_bitrate": opus_bitrate,
        "sample_rate": sample_rate,
        "max_new_tokens": _clamp_int(cfg.get("max_new_tokens"), FISH_DEFAULT_STYLE["max_new_tokens"], 128, 4096),
        "early_stop_threshold": round(_clamp_float(cfg.get("early_stop_threshold"), FISH_DEFAULT_STYLE["early_stop_threshold"], 0.0, 1.0), 2),
        "quality_guard": _normalize_bool(cfg.get("quality_guard"), FISH_DEFAULT_STYLE["quality_guard"]),
        "pronunciation_dictionary_id": _clean_token(cfg.get("pronunciation_dictionary_id"), r"[A-Za-z0-9._:-]{1,128}", 128),
        "pronunciation_dictionary_version": _clean_token(cfg.get("pronunciation_dictionary_version"), r"[A-Za-z0-9._:-]{1,64}", 64),
    }


def _normalize_fish_tts_model(value, default=None):
    model = str(value or default or FISH_TTS_MODEL).strip()
    allowed = {m["id"] for m in FISH_TTS_MODELS}
    fallback = default or FISH_TTS_MODEL
    return model if model in allowed else fallback


def _normalize_voice_ids(cfg, voice):
    """从配置或 voice 解析音色候选 ID 列表（去空、去重、去 fish: 前缀）。"""
    raw = cfg.get("voice_ids") if isinstance(cfg, dict) else None
    ids = []
    if isinstance(raw, list):
        for item in raw:
            ids.extend(re.split(r"[,;\n ]+", str(item)))
    elif isinstance(raw, str) and raw.strip():
        ids = re.split(r"[,;\n ]+", raw)
    if not ids:
        single = str(voice or "").strip()
        if ":" in single:
            single = single.split(":", 1)[1]
        if single.strip():
            ids = [single.strip()]
    out = []
    seen = set()
    for item in ids:
        s = str(item).strip()
        if s.startswith("fish:"):
            s = s[5:].strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _normalize_config(data):
    """按引擎清洗字段：Edge 只保留 rate/pitch/volume；Fish 只保留人物 TTS 参数。"""
    if not isinstance(data, dict):
        return copy.deepcopy(default_config)

    cleaned = {}
    settings = data.get("__settings__", {}) if isinstance(data.get("__settings__", {}), dict) else {}
    allowed_fish_models = {m["id"] for m in FISH_TTS_MODELS}
    fish_tts_model = str(settings.get("fish_tts_model") or FISH_TTS_MODEL).strip()
    if fish_tts_model not in allowed_fish_models:
        fish_tts_model = FISH_TTS_MODEL
    cleaned["__settings__"] = {**settings, "fish_tts_model": fish_tts_model}

    for name, cfg in data.items():
        if name == "__settings__":
            continue
        if not isinstance(cfg, dict):
            cleaned[name] = copy.deepcopy(cfg)
            continue
        voice = cfg.get("voice", "")
        extras = copy.deepcopy(cfg)
        for key in ('voice', 'voice_ids', 'tts_model', 'rate', 'pitch', 'volume', 'emotion',
                    *FISH_DEFAULT_STYLE, 'stability', 'similarity_boost', 'style',
                    'use_speaker_boost', 'use_custom_settings'):
            extras.pop(key, None)
        if _is_edge_voice(voice):
            # 把已知不可用的云泽/晓甄自动替换成稳定默认
            edge_id = voice.split(":", 1)[1] if ":" in voice else EDGE_DEFAULT_VOICE
            if edge_id in EDGE_UNAVAILABLE_HINTS:
                print(f"[配置清洗] {name}: {edge_id} 不可用 → {EDGE_DEFAULT_VOICE}（{EDGE_UNAVAILABLE_HINTS[edge_id]}）")
                edge_id = EDGE_DEFAULT_VOICE
                voice = f"edge:{edge_id}"
            cleaned[name] = {
                **extras,
                "voice": voice,
                "rate": _normalize_edge_param(cfg.get("rate", default_config["旁白"].get("rate", "-8%")), "rate"),
                "pitch": _normalize_edge_param(cfg.get("pitch", default_config["旁白"].get("pitch", "-4Hz")), "pitch"),
                "volume": _normalize_edge_param(cfg.get("volume", "+0%"), "volume"),
                "emotion": ""
            }
        else:
            # 长期配置禁止绑定 emotion。
            # 旧版调试时可能把 whispers/angry/laughs 写进 json，加载/保存时一律清空。
            # 正式推演情绪只认台词内标签（由 main_template 把原文送入 TTS）。
            # 调音台「试听情感」仅通过 /api/tts?emotion= 临时注入，不落盘。
            cleaned[name] = {
                **extras,
                "voice": voice if _is_fish_voice(voice) else default_config["default"]["voice"],
                "voice_ids": _normalize_voice_ids(cfg, voice),
                "tts_model": _normalize_fish_tts_model(
                    cfg.get("tts_model"),
                    FISH_FREE_TTS_MODEL if name == "旁白" else fish_tts_model
                ),
                **_normalize_fish_cfg(cfg),
                "emotion": ""
            }
    for k, v in default_config.items():
        if k not in cleaned:
            cleaned[k] = copy.deepcopy(v)
    return cleaned


class ConfigError(Exception):
    pass


def _load_config():
    """读取失败必须显式报错；读取操作不创建或修复磁盘文件。"""
    if not os.path.exists(CONFIG_FILE):
        return copy.deepcopy(default_config)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if not isinstance(raw, dict) or not raw or any(
            name in raw and not isinstance(raw[name], dict) for name in default_config
        ):
            raise ValueError('配置结构不完整')
        return _normalize_config(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise ConfigError('语音配置读取失败，原文件已保留。请检查 voice_config.json 后重试。') from exc


def _atomic_json_write(path, data):
    tmp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with FILE_WRITE_LOCK:
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def _save_config(data):
    if not isinstance(data, dict) or not data or not any(
        name != '__settings__' and isinstance(cfg, dict) and isinstance(cfg.get('voice'), str)
        for name, cfg in data.items()
    ):
        raise ValueError('未收到有效的角色音色配置，已取消保存。')
    if any(name in data and not isinstance(data[name], dict) for name in default_config):
        raise ValueError('角色配置格式不正确，已取消保存。')
    with FILE_WRITE_LOCK:
        if os.path.exists(CONFIG_FILE):
            _load_config()
        cleaned = _normalize_config(data)
        _atomic_json_write(CONFIG_FILE, cleaned)
    return cleaned


def _initialize_config():
    with FILE_WRITE_LOCK:
        if not os.path.exists(CONFIG_FILE):
            _atomic_json_write(CONFIG_FILE, copy.deepcopy(default_config))
        else:
            _load_config()

# ==========================================
# 语音仓库（全局长期音色池 · 独立于角色 voice_ids 收藏）
# 落盘：语音仓库/voice_repo.json
# ==========================================
VOICE_REPO_DIR = os.path.join(BASE_DIR, '语音仓库')
VOICE_REPO_FILE = os.path.join(VOICE_REPO_DIR, 'voice_repo.json')


def _load_voice_repo():
    """读取语音仓库；文件缺失或损坏时返回空列表。"""
    if not os.path.exists(VOICE_REPO_FILE):
        return []
    try:
        with open(VOICE_REPO_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        out = []
        seen = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            vid = str(item.get('id') or '').strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append({
                'id': vid,
                'name': str(item.get('name') or '').strip(),
                'note': str(item.get('note') or '').strip(),
                'created_at': str(item.get('created_at') or '')
            })
        return out
    except Exception:
        return []


def _normalize_voice_repo_id(value):
    vid = str(value or '').strip()
    vid = re.sub(r'^(?:(?:fish:|reference_id\s*[:=]\s*)\s*)+', '', vid, flags=re.I).strip().strip('\"\'')
    if not vid or len(vid) > 160 or any(ord(ch) < 32 for ch in vid):
        return ''
    return vid


def _save_voice_repo(items):
    """写入语音仓库（先确保目录存在）。"""
    if not os.path.exists(VOICE_REPO_DIR):
        os.makedirs(VOICE_REPO_DIR)
    _atomic_json_write(VOICE_REPO_FILE, items)
    return items


@app.route('/api/voice_repo', methods=['GET'])
def get_voice_repo():
    items = _load_voice_repo()
    return jsonify({'items': items, 'count': len(items)})


@app.route('/api/voice_repo', methods=['POST'])
def add_voice_repo():
    data = request.json or {}
    vid = _normalize_voice_repo_id(data.get('id'))
    if not vid:
        return jsonify({'status': 'error', 'msg': '缺少音色 ID'}), 400
    items = _load_voice_repo()
    if any(x['id'] == vid for x in items):
        return jsonify({'status': 'error', 'msg': '该音色已在语音库中', 'items': items, 'count': len(items)}), 409
    items.append({
        'id': vid,
        'name': str(data.get('name') or '').strip(),
        'note': str(data.get('note') or '').strip(),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
    })
    _save_voice_repo(items)
    return jsonify({'status': 'success', 'msg': '已加入语音库', 'items': items, 'count': len(items)})


@app.route('/api/voice_repo', methods=['DELETE'])
def delete_voice_repo():
    vid = (request.args.get('id') or '').strip()
    if not vid:
        return jsonify({'status': 'error', 'msg': '缺少音色 ID'}), 400
    items = _load_voice_repo()
    before = len(items)
    items = [x for x in items if x['id'] != vid]
    _save_voice_repo(items)
    return jsonify({'status': 'success', 'msg': '已从语音库删除', 'removed': before - len(items), 'items': items, 'count': len(items)})


def _list_edge_voices_sync():
    """从 edge-tts 拉真实可用中文音色；失败则返回静态白名单。"""
    try:
        import asyncio
        import edge_tts

        async def _fetch():
            voices = await edge_tts.list_voices()
            zh = []
            for v in voices:
                short = v.get("ShortName") or ""
                locale = v.get("Locale") or ""
                if not (short.startswith("zh-") or locale.startswith("zh-")):
                    continue
                gender = v.get("Gender") or ""
                label = EDGE_VOICE_LABELS.get(short)
                if not label:
                    # FriendlyName 形如 Microsoft Yunyang Online (Natural) - Chinese (Mainland)
                    friendly = v.get("FriendlyName") or short
                    label = f"{short} ({gender})" if gender else f"{short} · {friendly}"
                zh.append({
                    "id": short,
                    "name": label,
                    "gender": gender,
                    "locale": locale
                })
            # 去重并稳定排序：男声叙事优先
            seen = set()
            uniq = []
            for item in zh:
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                uniq.append(item)

            def sort_key(x):
                prefer = {vid: i for i, vid in enumerate(EDGE_FALLBACK_VOICES)}
                return (prefer.get(x["id"], 100), x["id"])

            uniq.sort(key=sort_key)
            return uniq

        return asyncio.run(asyncio.wait_for(_fetch(), timeout=8))
    except Exception as e:
        print(f"⚠️ 拉取 Edge 音色列表失败，使用静态白名单: {e}")
        return [
            {"id": vid, "name": EDGE_VOICE_LABELS.get(vid, vid), "gender": "", "locale": "zh-CN"}
            for vid in EDGE_FALLBACK_VOICES
        ]


def _run_edge_tts(text, voice_id, rate, pitch, volume, output_file):
    import asyncio
    import edge_tts

    async def synthesize():
        last_error = 'Edge TTS 无音频返回'
        for candidate in dict.fromkeys([voice_id, *EDGE_FALLBACK_VOICES]):
            try:
                if os.path.exists(output_file):
                    os.remove(output_file)
                await edge_tts.Communicate(
                    text, candidate, rate=rate, pitch=pitch, volume=volume
                ).save(output_file)
                if not os.path.isfile(output_file) or os.path.getsize(output_file) == 0:
                    raise ValueError('音频为空')
                return candidate, None
            except Exception as exc:
                last_error = str(exc)
        return None, last_error

    try:
        return asyncio.run(asyncio.wait_for(synthesize(), timeout=45))
    except Exception as exc:
        return None, str(exc) or 'Edge TTS 等待超时'

def _get_current_fish_tts_model():
    try:
        cfg = _load_config()
        model = str(cfg.get("__settings__", {}).get("fish_tts_model") or FISH_TTS_MODEL).strip()
    except Exception:
        model = FISH_TTS_MODEL
    allowed = {m["id"] for m in FISH_TTS_MODELS}
    return model if model in allowed else FISH_TTS_MODEL


def _fish_headers(tts_model=None, audio_format='mp3'):
    if not FISH_API_KEY:
        return None
    model = str(tts_model or _get_current_fish_tts_model() or FISH_TTS_MODEL).strip()
    allowed = {m["id"] for m in FISH_TTS_MODELS}
    if model not in allowed:
        model = FISH_TTS_MODEL
    fmt_meta = FISH_AUDIO_FORMATS.get(str(audio_format or 'mp3').lower(), FISH_AUDIO_FORMATS['mp3'])
    return {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
        "Accept": fmt_meta["mime"],
        "model": model
    }


def _fish_request_json(url, params=None, timeout=6, retries=0):
    if not FISH_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {FISH_API_KEY}"}
    last_err = None
    for attempt in range(max(1, int(retries) + 1)):
        try:
            res = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
            if res.status_code == 200:
                return res.json()
            last_err = f"Fish Audio 接口报错 {res.status_code}: {res.text[:300]}"
        except Exception as e:
            last_err = str(e)
            if attempt < max(1, int(retries)):
                time.sleep(0.8 * (attempt + 1))
    if last_err:
        print(f"⚠️ Fish Audio 请求失败（已重试）: {last_err}")
    return None


def _extract_fish_models(data):
    """兼容 Fish /model 返回的多种包装格式。"""
    if not data:
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('items') or data.get('models') or data.get('data') or data.get('results') or []
    else:
        items = []
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = str(m.get('_id') or m.get('id') or m.get('model_id') or m.get('reference_id') or '').strip()
        if not mid:
            continue
        title = m.get('title') or m.get('name') or m.get('nickname') or m.get('description') or mid
        lang = m.get('language') or m.get('locale') or ''
        visibility = m.get('visibility') or m.get('type') or ''
        label = str(title)
        extras = ' · '.join([str(x) for x in [lang, visibility] if x])
        if extras:
            label = f"{label} ({extras})"
        out.append({"id": mid, "name": label})
    # 去重
    seen, uniq = set(), []
    for item in out:
        if item['id'] in seen:
            continue
        seen.add(item['id'])
        uniq.append(item)
    return uniq


def _fish_reference_id(voice_id):
    voice_id = (voice_id or '').strip()
    if voice_id:
        return voice_id
    return FISH_DEFAULT_VOICE_ID


def _build_fish_payload(text, voice_id, cfg=None):
    """Fish Audio /v1/tts：构建完整官方 v1 参数载荷（兼容 s2.1-pro / s2.1-pro-free / drama-3 / s2-pro）。"""
    fish_cfg = _normalize_fish_cfg(cfg or {})
    fmt = fish_cfg["format"]
    payload = {
        "text": text,
        "format": fmt,
        "sample_rate": fish_cfg["sample_rate"],
        "latency": fish_cfg["latency"],
        "normalize": fish_cfg["normalize"],
        "temperature": fish_cfg["temperature"],
        "top_p": fish_cfg["top_p"],
        "chunk_length": fish_cfg["chunk_length"],
        "min_chunk_length": fish_cfg["min_chunk_length"],
        "repetition_penalty": fish_cfg["repetition_penalty"],
        "condition_on_previous_chunks": fish_cfg["condition_on_previous_chunks"],
        "max_new_tokens": fish_cfg["max_new_tokens"],
        "early_stop_threshold": fish_cfg["early_stop_threshold"],
    }
    if fmt == "mp3":
        payload["mp3_bitrate"] = fish_cfg["mp3_bitrate"]
    elif fmt == "opus":
        payload["opus_bitrate"] = fish_cfg["opus_bitrate"]
    if fish_cfg["language"]:
        payload["language"] = fish_cfg["language"]
    if fish_cfg["quality_guard"]:
        payload["features"] = ["quality-guard"]
    if fish_cfg["pronunciation_dictionary_id"]:
        dict_ref = {"id": fish_cfg["pronunciation_dictionary_id"]}
        if fish_cfg["pronunciation_dictionary_version"]:
            dict_ref["version"] = fish_cfg["pronunciation_dictionary_version"]
        payload["pronunciation_dictionary"] = [dict_ref]
    ref_id = _fish_reference_id(voice_id)
    if ref_id:
        payload["reference_id"] = ref_id
    payload["prosody"] = {
        "speed": fish_cfg["speed"],
        "volume": fish_cfg["volume"],
        "normalize_loudness": fish_cfg["normalize_loudness"]
    }
    return payload


PUBLIC_FILES = {
    'main_template.html', 'voice_manager.html', 'voice_client.js', 'data.json',
    'story_client.js', 'story_client.css',
    '存档/全局记忆库.txt', '存档/徐志北道具图鉴.txt',
}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif'}


def _serve_public_file(filename):
    root = Path(BASE_DIR).resolve()
    target = (root / filename).resolve()
    image_root = (root / 'txt文件' / 'image').resolve()
    image_allowed = target.is_relative_to(image_root) and target.suffix.lower() in IMAGE_EXTENSIONS
    if (not target.is_relative_to(root) or not target.is_file() or
            any(part.startswith('.') for part in Path(filename).parts) or
            not (filename in PUBLIC_FILES or image_allowed)):
        abort(404)
    response = send_file(target)
    if filename in {'main_template.html', 'voice_manager.html', 'voice_client.js', 'story_client.js', 'story_client.css', 'data.json'}:
        response.headers['Cache-Control'] = 'no-cache'
    return response


@app.route('/<path:filename>')
def public_file(filename):
    return _serve_public_file(filename)


@app.route('/')
def index():
    return _serve_public_file('main_template.html')


@app.route('/admin')
def admin():
    return _serve_public_file('voice_manager.html')


@app.route('/api/voices', methods=['GET'])
def get_voices():
    """返回 Fish Audio 可选音色模型。"""
    if not FISH_API_KEY:
        return jsonify({"voices": [], "error": "missing FISH_API_KEY"}), 200

    search = (request.args.get("search") or request.args.get("title") or "").strip()
    own_data = None if search else _fish_request_json(f"{FISH_BASE_URL}/model", params={"page_size": 100, "self": "true"})
    public_params = {"page_size": 100}
    if search:
        public_params["title"] = search[:80]
    else:
        public_params["sort_by"] = "task_count"
    public_data = _fish_request_json(f"{FISH_BASE_URL}/model", params=public_params)
    voice_list = _extract_fish_models(own_data) + _extract_fish_models(public_data)

    # 去重：自己的私有/克隆模型优先，其次公开模型。
    seen, deduped = set(), []
    for item in voice_list:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)
    voice_list = deduped

    # 若后端常量指定了默认音色，但公开/私有列表没返回，也补进下拉框。
    if not search and FISH_DEFAULT_VOICE_ID and not any(v["id"] == FISH_DEFAULT_VOICE_ID for v in voice_list):
        voice_list.insert(0, {"id": FISH_DEFAULT_VOICE_ID, "name": "默认 Fish 音色（来自 FISH_DEFAULT_VOICE_ID）"})

    return jsonify({
        "voices": voice_list,
        "provider": "fish",
        "search": search,
        "count": len(voice_list),
        "mode": "search" if search else "default",
        "tts_model": _get_current_fish_tts_model(),
        "tts_models": FISH_TTS_MODELS
    })


@app.route('/api/edge_voices', methods=['GET'])
def get_edge_voices():
    """返回当前环境真正可用的 Edge 中文音色（动态）。"""
    voices = _list_edge_voices_sync()
    return jsonify({
        "voices": voices,
        "default": EDGE_DEFAULT_VOICE,
        "unavailable_hints": EDGE_UNAVAILABLE_HINTS
    })


@app.route('/api/fish_wallet', methods=['GET'])
def get_fish_wallet():
    """返回 Fish Audio 套餐与 API Credit，用于调音台快速查看余额。"""
    if not FISH_API_KEY:
        return jsonify({"ok": False, "error": "missing FISH_API_KEY"}), 200

    package = _fish_request_json(f"{FISH_BASE_URL}/wallet/self/package", timeout=6, retries=0)
    credit = _fish_request_json(
        f"{FISH_BASE_URL}/wallet/self/api-credit",
        params={"check_free_credit": "true"},
        timeout=6,
        retries=0
    )
    warnings = []
    if package is None:
        warnings.append("套餐查询失败（网络或限流），不影响 TTS 生成")
    if credit is None:
        warnings.append("API Credit 查询失败（网络或限流），不影响 TTS 生成")
    return jsonify({
        "ok": not warnings,
        "package": package,
        "api_credit": credit,
        "warnings": warnings
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    try:
        return jsonify(_load_config())
    except ConfigError as exc:
        return jsonify({'error': str(exc)}), 503


@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        cleaned = _save_config(request.get_json(silent=True))
        return jsonify({'status': 'success', 'msg': '配置已保存', 'config': cleaned})
    except ConfigError as exc:
        return jsonify({'error': str(exc)}), 409
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except OSError:
        return jsonify({'error': '保存失败，原配置已保留，请检查存储空间或权限。'}), 503


def _find_cfg_by_voice(raw_voice_param):
    all_cfg = _load_config()
    for k, v in all_cfg.items():
        if isinstance(v, dict) and v.get('voice') == raw_voice_param:
            return v
    if raw_voice_param.startswith('edge:'):
        return all_cfg.get('旁白', default_config['旁白'])
    return {}


def _cleanup_temp_audio():
    vosi_dir = os.path.join(BASE_DIR, 'vosi')
    if not os.path.isdir(vosi_dir):
        return
    cutoff = time.time() - TEMP_AUDIO_MAX_AGE_SECONDS
    for item in Path(vosi_dir).glob('temp_audio_*.mp3'):
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:
            pass


def _request_tts_data():
    payload = request.get_json(silent=True) if request.method == 'POST' else None
    return payload if isinstance(payload, dict) else request.args.to_dict(flat=True)


class TtsError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _cached_tts(key, producer):
    """相同文本、模型和参数共用生成任务；只缓存成功音频，容量有限。"""
    global TTS_CACHE_BYTES
    with TTS_STATE_LOCK:
        now = time.monotonic()
        for old_key, (created, audio) in list(TTS_CACHE.items()):
            if now - created > TEMP_AUDIO_MAX_AGE_SECONDS:
                TTS_CACHE_BYTES -= len(audio)
                del TTS_CACHE[old_key]
        if key in TTS_CACHE:
            created, audio = TTS_CACHE.pop(key)
            TTS_CACHE[key] = (created, audio)
            return audio
        job = TTS_INFLIGHT.get(key)
        owner = job is None
        if owner:
            job = {'event': threading.Event(), 'audio': None, 'error': None}
            TTS_INFLIGHT[key] = job
    if not owner:
        if not job['event'].wait(TTS_WAIT_SECONDS):
            raise TtsError('语音仍在生成，请稍后重试。', 504)
        if job['error']:
            raise job['error']
        return job['audio']
    acquired = False
    try:
        acquired = TTS_SLOTS.acquire(timeout=1)
        if not acquired:
            raise TtsError('正在处理其他语音，请稍后重试。', 429)
        audio = producer()
        if not audio:
            raise TtsError('语音服务没有返回音频，请重试。')
        job['audio'] = audio
        with TTS_STATE_LOCK:
            if len(audio) <= TTS_CACHE_MAX_BYTES:
                TTS_CACHE[key] = (time.monotonic(), audio)
                TTS_CACHE_BYTES += len(audio)
                while TTS_CACHE and (len(TTS_CACHE) > TTS_CACHE_MAX_ENTRIES or TTS_CACHE_BYTES > TTS_CACHE_MAX_BYTES):
                    _, (_, old_audio) = TTS_CACHE.popitem(last=False)
                    TTS_CACHE_BYTES -= len(old_audio)
        return audio
    except Exception as exc:
        job['error'] = exc if isinstance(exc, TtsError) else TtsError('语音生成失败，请检查网络后重试。')
        raise job['error'] from exc
    finally:
        if acquired:
            TTS_SLOTS.release()
        with TTS_STATE_LOCK:
            job['event'].set()
            TTS_INFLIGHT.pop(key, None)


def _edge_audio(text, voice_id, rate, pitch, volume):
    vosi_dir = os.path.join(BASE_DIR, 'vosi')
    os.makedirs(vosi_dir, exist_ok=True)
    output_file = os.path.join(vosi_dir, f'temp_audio_{uuid.uuid4().hex}.mp3')
    try:
        used_voice, error = _run_edge_tts(text, voice_id, rate, pitch, volume, output_file)
        if not used_voice:
            raise TtsError('Edge 语音生成失败，请检查网络或切换音色。')
        with open(output_file, 'rb') as audio_file:
            return audio_file.read()
    finally:
        if os.path.exists(output_file):
            os.remove(output_file)


def _fish_audio(payload, tts_model, on_chunk=None):
    fmt = str((payload or {}).get('format') or 'mp3').lower()
    try:
        response = requests.post(
            f'{FISH_BASE_URL}/v1/tts', json=payload,
            headers=_fish_headers(tts_model, fmt), timeout=FISH_HTTP_TIMEOUT, stream=True
        )
        try:
            if response.status_code != 200:
                status = response.status_code
                message = '语音服务暂时不可用，请稍后重试。'
                if status in (401, 403):
                    message = '语音服务授权失败，请检查密钥或音色权限。'
                elif status in (402, 429):
                    message = '语音服务额度不足或请求过于频繁，请稍后重试。'
                raise TtsError(message, 429 if status == 429 else 502)
            content_type = response.headers.get('Content-Type', '').lower()
            if content_type and not (content_type.startswith('audio/') or 'octet-stream' in content_type):
                raise TtsError('语音服务返回了非音频内容，请重试。')
            parts = []
            size = 0
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                size += len(chunk)
                if size > TTS_CACHE_MAX_BYTES:
                    raise TtsError('音频超过传输容量限制。', 413)
                parts.append(chunk)
                if on_chunk is not None:
                    on_chunk(chunk)
            return b''.join(parts)
        finally:
            response.close()
    except requests.Timeout as exc:
        raise TtsError('语音生成等待超时，请稍后重试。', 504) from exc
    except requests.RequestException as exc:
        raise TtsError('语音服务连接失败，请检查网络后重试。', 502) from exc


def _stream_cached_tts(key, factory, mimetype='audio/mpeg'):
    """复用现有缓存及请求去重；仅请求拥有者逐块转发。"""
    messages = queue.Queue(maxsize=8)
    stopped = threading.Event()

    def emit(kind, value):
        while not stopped.is_set():
            try:
                messages.put((kind, value), timeout=0.2)
                return
            except queue.Full:
                continue
        raise TtsError('语音传输已取消。', 499)

    def worker():
        sent = False
        def chunk(data):
            nonlocal sent
            emit('audio', data)
            sent = True
        try:
            audio = _cached_tts(key, lambda: factory(chunk))
            if not sent:
                emit('audio', audio)
            emit('done', None)
        except Exception as exc:
            if not stopped.is_set():
                try:
                    emit('error', exc)
                except TtsError:
                    pass

    threading.Thread(target=worker, daemon=True).start()
    try:
        kind, first = messages.get(timeout=TTS_WAIT_SECONDS)
    except queue.Empty:
        stopped.set()
        raise TtsError('语音生成等待超时。', 504)
    if kind == 'error':
        stopped.set()
        raise first
    if kind != 'audio':
        stopped.set()
        raise TtsError('语音服务没有返回音频。')

    def body():
        try:
            yield first
            while True:
                try:
                    kind, value = messages.get(timeout=TTS_WAIT_SECONDS)
                except queue.Empty:
                    raise TtsError('音频传输等待超时。', 504)
                if kind == 'done':
                    return
                if kind == 'error':
                    raise value
                yield value
        finally:
            stopped.set()
    response = Response(body(), mimetype=mimetype)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Accel-Buffering'] = 'no'
    response.call_on_close(stopped.set)
    return response


@app.route('/api/tts', methods=['GET', 'POST'])
def tts_api():
    data = _request_tts_data()
    text = str(data.get('text') or '').strip().replace('【', '').replace('】', '').replace('*', '')
    if len(text) > TTS_MAX_TEXT_LENGTH:
        return jsonify({'error': f'文本超过 {TTS_MAX_TEXT_LENGTH} 字符上限'}), 413
    if not text:
        return jsonify({'error': '请提供需要朗读的文本。'}), 400
    voice = str(data.get('voice') or 'fish:')
    model_name, _, voice_id = voice.partition(':')
    if not voice_id and ':' not in voice:
        voice_id = voice
    try:
        matched = _find_cfg_by_voice(voice)
        audio_mime = 'audio/mpeg'
        audio_ext = 'mp3'
        if model_name == 'edge':
            if voice_id in EDGE_UNAVAILABLE_HINTS or not voice_id:
                voice_id = EDGE_DEFAULT_VOICE
            text = re.sub(r'\[[^\]]{1,60}\]\s*', '', text)
            text = re.sub(r'<\|[^|]{1,40}\|>', '', text)
            text = re.sub(r'</?(?:whisper|emphasis|soft|fast|slow|stress|forceful)>', '', text, flags=re.I).strip()
            if not text:
                return jsonify({'error': '没有可朗读的文本。'}), 400
            rate = _normalize_edge_param(data.get('rate') or matched.get('rate') or '-8%', 'rate')
            pitch = _normalize_edge_param(data.get('pitch') or matched.get('pitch') or '-4Hz', 'pitch')
            volume = _normalize_edge_param(data.get('volume') or matched.get('volume') or '+0%', 'volume')
            key_data = ['edge', text, voice_id, rate, pitch, volume]
            producer = lambda: _edge_audio(text, voice_id, rate, pitch, volume)
        else:
            if not FISH_API_KEY:
                return jsonify({'error': '尚未设置 Fish Audio 密钥。'}), 503
            emotion = str(data.get('emotion') or '').strip()
            if emotion and len(emotion) <= 48 and re.fullmatch(r'[A-Za-z0-9 ,_-]+', emotion):
                text = f'[{emotion}] {text}'
            runtime_cfg = dict(matched)
            for name in FISH_DEFAULT_STYLE:
                if data.get(name) is not None:
                    runtime_cfg[name] = data[name]
            tts_model = _normalize_fish_tts_model(
                data.get('tts_model') or matched.get('tts_model') or _get_current_fish_tts_model()
            )
            payload = _build_fish_payload(text, voice_id, runtime_cfg)
            fmt_meta = FISH_AUDIO_FORMATS.get(payload.get('format', 'mp3'), FISH_AUDIO_FORMATS['mp3'])
            audio_mime = fmt_meta['mime']
            audio_ext = fmt_meta['ext']
            key_data = ['fish', tts_model, payload]
            producer = lambda: _fish_audio(payload, tts_model)
        key = hashlib.sha256(json.dumps(key_data, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
        if model_name != 'edge' and data.get('stream') is True:
            return _stream_cached_tts(key, lambda emit: _fish_audio(payload, tts_model, on_chunk=emit), mimetype=audio_mime)
        audio = _cached_tts(key, producer)
        response = send_file(io.BytesIO(audio), mimetype=audio_mime, download_name=f'tts.{audio_ext}')
        response.headers['Cache-Control'] = 'no-store'
        return response
    except ConfigError as exc:
        return jsonify({'error': str(exc)}), 503
    except TtsError as exc:
        return jsonify({'error': str(exc)}), exc.status



PREFERRED_BROWSER = "yujianc"  # 默认浏览器：雨见c (com.yjllq.chrome.beta)


def open_browser():
    import os
    import sys
    url = 'http://127.0.0.1:5000'
    try:
        if sys.platform == 'win32' or os.name == 'nt' or not os.path.exists('/system/bin/am'):
            webbrowser.open(url)
            return

        if PREFERRED_BROWSER == "default":
            webbrowser.open(url)
        else:
            pkg_map = {
                "chrome": "com.android.chrome",
                "edge": "com.microsoft.emmx",
                "via": "mark.via",
                "firefox": "org.mozilla.firefox",
                "alook": "alook.browser",
                "yujianc": "com.yjllq.chrome.beta"  # 雨见c
            }

            if PREFERRED_BROWSER == "chooser":
                os.system(f'am start -a android.intent.action.VIEW -d "{url}" --activity-clear-task')
            else:
                pkg = pkg_map.get(PREFERRED_BROWSER.lower())
                if pkg:
                    print(f"\n[系统] 正在底层强制唤醒外部浏览器: {PREFERRED_BROWSER}...")
                    res = os.system(f'am start -a android.intent.action.VIEW -d "{url}" -p {pkg}')
                    if res != 0:
                        print(f"\n[!] 唤醒指令可能受限 (返回码: {res})。但已剥离内置浏览器兜底！")
                else:
                    webbrowser.open(url)
    except Exception as e:
        print(f"⚠️ 自动打开浏览器发生异常: {e}")


if __name__ == '__main__':
    try:
        _initialize_config()
    except (ConfigError, OSError) as exc:
        print(f'配置加载异常，原文件已保留：{exc}')
    _cleanup_temp_audio()
    print("=======================================")
    print("🚀 双引擎语音中控已启动（Fish Audio旁白/人物，Edge可选回退）")
    print(f"🎙️ Fish 免费旁白模型: {FISH_FREE_TTS_MODEL}")
    print("👉 游戏端访问: http://127.0.0.1:5000")
    print("⚙️ 管理端访问: http://127.0.0.1:5000/admin?v=pro")
    print("=======================================")

    Timer(1.5, open_browser).start()
    app.run(host='127.0.0.1', port=5000, threaded=True)
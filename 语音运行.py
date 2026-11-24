import os
import json
import re
import time
import uuid
import threading
from pathlib import Path
from urllib.parse import urlsplit
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
FISH_KEY_CACHE_FILE = os.path.join(BASE_DIR, '.cache', 'fish_api_key.json')
PHONEME_MAP_FILE = os.path.join(BASE_DIR, '语音引擎升级方案', 'character_phoneme_map.json')
TTS_MAX_TEXT_LENGTH = 12000
TEMP_AUDIO_MAX_AGE_SECONDS = 6 * 60 * 60
FILE_WRITE_LOCK = threading.RLock()
FISH_HTTP_TIMEOUT = (8, 45)
TTS_WAIT_SECONDS = 60
TTS_CACHE_MAX_BYTES = 32 * 1024 * 1024
TTS_CACHE_MAX_ENTRIES = 64
TTS_DISK_CACHE_DIR = os.path.join(BASE_DIR, '.cache', 'tts_audio')
TTS_DISK_CACHE_MAX_BYTES = 40 * 1024 * 1024
TTS_DISK_CACHE_LOCK = threading.Lock()
TTS_STATE_LOCK = threading.Lock()
TTS_SLOTS = threading.BoundedSemaphore(4)
TTS_PREFETCH_SLOTS = threading.BoundedSemaphore(2)
TTS_CACHE = OrderedDict()
TTS_INFLIGHT = {}
TTS_CACHE_BYTES = 0
_HEX64_RE = re.compile(r'^[0-9a-f]{64}$')

_ORIG_REQUESTS_POST = requests.post
_ORIG_REQUESTS_GET = requests.get
_FISH_HTTP_SESSION = requests.Session()
_fish_http_adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=6)
_FISH_HTTP_SESSION.mount('https://', _fish_http_adapter)
_FISH_HTTP_SESSION.mount('http://', _fish_http_adapter)

_FISH_RATE_LOCK = threading.Lock()
_FISH_429_COOLDOWN_UNTIL = 0.0
_FISH_429_STREAK = 0


def _fish_http_post(*args, **kwargs):
    if requests.post is not _ORIG_REQUESTS_POST:
        return requests.post(*args, **kwargs)
    return _FISH_HTTP_SESSION.post(*args, **kwargs)


def _fish_http_get(*args, **kwargs):
    if requests.get is not _ORIG_REQUESTS_GET:
        return requests.get(*args, **kwargs)
    return _FISH_HTTP_SESSION.get(*args, **kwargs)


def _record_fish_429():
    global _FISH_429_COOLDOWN_UNTIL, _FISH_429_STREAK
    with _FISH_RATE_LOCK:
        _FISH_429_STREAK = min(_FISH_429_STREAK + 1, 5)
        wait_sec = min(24.0, 3.0 * (2 ** (_FISH_429_STREAK - 1)))
        _FISH_429_COOLDOWN_UNTIL = time.monotonic() + wait_sec
        return wait_sec


def _record_fish_ok():
    global _FISH_429_COOLDOWN_UNTIL, _FISH_429_STREAK
    with _FISH_RATE_LOCK:
        _FISH_429_STREAK = 0
        _FISH_429_COOLDOWN_UNTIL = 0.0


def _in_fish_429_cooldown():
    with _FISH_RATE_LOCK:
        return time.monotonic() < _FISH_429_COOLDOWN_UNTIL

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

from story_service import register_story_routes
register_story_routes(app, BASE_DIR, tts_prewarmer=lambda items: prewarm_tts_items(items))

# ==========================================
# Fish Audio API 配置（零硬编码：优先读受保护本地缓存 .cache/fish_api_key.json，其次环境变量）
# ==========================================
FISH_API_KEY = os.environ.get("FISH_API_KEY", "").strip()
FISH_BASE_URL = "https://api.fish.audio"
FISH_TTS_MODEL = "s2.1-pro-free"  # 默认零成本主力（与 s2.1-pro 同权重同音质，按需可切分档）
FISH_TTS_MODELS = [
    {"id": "s2.1-pro-free", "name": "S2.1 Pro Free（同质零费用主力 · 推荐）"},
    {"id": "s2.1-pro", "name": "S2.1 Pro（付费稳定生产档 · $15/M字节）"},
    {"id": "drama-3", "name": "Drama 3（高消费旗舰导演 · 原价$50/M字节）"},
    {"id": "s2-pro", "name": "S2 Pro（上一代开源 S2）"},
]
FISH_FREE_TTS_MODEL = "s2.1-pro-free"
VOICED_HEROINES = ("沈知韫", "苏婉青", "徐念薇")
VOICE_TIERS = {
    "free": {
        "heroine_model": "s2.1-pro-free",
        "narrator_model": "s2.1-pro-free",
        "label": "标准免费档（推荐 · $0）",
    },
    "pro": {
        "heroine_model": "s2.1-pro",
        "narrator_model": "s2.1-pro-free",
        "label": "稳定生产档（三女主 $15/M字节 · 旁白免费）",
    },
    "drama": {
        "heroine_model": "drama-3",
        "narrator_model": "s2.1-pro-free",
        "label": "旗舰导演档（三女主 Drama 3 高消费 · 旁白免费）",
    },
}
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
    "temperature": 0.68,
    "top_p": 0.75,
    "latency": "balanced",
    "chunk_length": 180,
    "min_chunk_length": 40,
    "repetition_penalty": 1.18,
    "condition_on_previous_chunks": True,
    "normalize": True,
    "language": "zh-CN",
    "format": "mp3",
    "mp3_bitrate": 128,
    "opus_bitrate": -1000,
    "sample_rate": 44100,
    "max_new_tokens": 1024,
    "early_stop_threshold": 1.0,
    "quality_guard": True,
    "pronunciation_dictionary_id": "",
    "pronunciation_dictionary_version": "",
}

_VOICE_MUTATING_PATHS = frozenset({
    '/api/fish_key',
    '/api/config',
    '/api/voice_tier',
    '/api/voice_repo',
    '/api/tts/prefetch',
})
_DRAMA3_XML_RE = re.compile(
    r'</?(?:whisper|emphasis|soft|fast|slow|stress|forceful|chinese|english|japanese|korean|cantonese|french|german|spanish)>',
    flags=re.I,
)
_PHONEME_SPAN_RE = re.compile(r'<\|phoneme_start\|>[^<]{1,40}<\|phoneme_end\|>')
_PHONEME_TOKEN_RE = re.compile(r'<\|[^|]{1,40}\|>')
_PHONEME_SPLIT_RE = re.compile(r'(\[[^\]\r\n]{1,80}\]|<\|phoneme_start\|>[^<]{1,40}<\|phoneme_end\|>|<[^>]{1,40}>)')
_PHONEME_CACHE = {'mtime': None, 'pattern': None, 'mapping': {}}


_SUBTEXT_RUBY_RE = re.compile(r'[｛{]([^｜|}\r\n]+)[｜|][^｝}\r\n]+[｝}]')


@app.before_request
def _voice_request_boundary():
    """为所有非 /api/story/ 的本地语音与配置接口补齐同源与 CSRF 防护。"""
    if not request.path.startswith('/api/') or request.path.startswith('/api/story/'):
        return None
    if urlsplit('http://' + request.host).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        abort(403)
    host_prefix = request.host_url.rstrip('/')
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != host_prefix:
        abort(403)
    referer = request.headers.get('Referer')
    if referer and not (referer == host_prefix or referer.startswith(host_prefix + '/')):
        abort(403)
    if request.headers.get('Sec-Fetch-Site') in {'cross-site', 'same-site'}:
        abort(403)
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.path in _VOICE_MUTATING_PATHS:
        if request.headers.get('X-Voice-Client') != '1':
            abort(403)
    return None


def _mask_fish_key(key):
    s = str(key or '').strip()
    if not s:
        return ''
    if len(s) <= 10:
        return s[:2] + '****' + s[-2:] if len(s) > 4 else '****'
    return s[:8] + '****' + s[-4:]


def _validate_fish_key_format(key):
    s = str(key or '').strip()
    if not s or len(s) < 8 or len(s) > 256 or any(ord(ch) <= 32 or ord(ch) == 127 for ch in s):
        return ''
    return s


def _load_cached_fish_key():
    """读取玩家本机受保护缓存 .cache/fish_api_key.json（受 .gitignore、一键同步与新档重置保护）。"""
    if not os.path.isfile(FISH_KEY_CACHE_FILE):
        return ''
    try:
        with open(FISH_KEY_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return _validate_fish_key_format(data.get('api_key', ''))
    except Exception:
        return ''
    return ''


def _save_cached_fish_key(raw_key):
    cleaned = _validate_fish_key_format(raw_key)
    if not cleaned:
        raise ValueError('密钥格式无效：请粘贴完整的 Fish Audio API Key（不含空格或换行）。')
    cache_dir = os.path.dirname(FISH_KEY_CACHE_FILE)
    os.makedirs(cache_dir, exist_ok=True)
    tmp_path = f"{FISH_KEY_CACHE_FILE}.{uuid.uuid4().hex}.tmp"
    with FILE_WRITE_LOCK:
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump({'api_key': cleaned, 'updated_at': int(time.time())}, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, FISH_KEY_CACHE_FILE)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    return cleaned


def _clear_cached_fish_key():
    with FILE_WRITE_LOCK:
        if os.path.exists(FISH_KEY_CACHE_FILE):
            os.remove(FISH_KEY_CACHE_FILE)


def _resolve_fish_api_key(override_key=None):
    """动态解析 Fish API Key：显式参数/请求头 > 本地受保护缓存 > 环境变量。"""
    if override_key is not None:
        cleaned = _validate_fish_key_format(override_key)
        if cleaned:
            return cleaned, 'request'
    try:
        hdr = request.headers.get('X-Fish-Api-Key', '')
        cleaned_hdr = _validate_fish_key_format(hdr)
        if cleaned_hdr:
            return cleaned_hdr, 'header'
    except RuntimeError:
        pass
    cached = _load_cached_fish_key()
    if cached:
        return cached, 'local_cache'
    env_key = _validate_fish_key_format(os.environ.get('FISH_API_KEY', '') or FISH_API_KEY)
    if env_key:
        return env_key, 'env'
    return '', 'none'


def _load_phoneme_map():
    """加载专有名词/多音字服务端注音映射（仅对 Fish Audio 请求生效，不污染剧情原文）。"""
    try:
        st = os.stat(PHONEME_MAP_FILE)
        mtime = st.st_mtime
    except OSError:
        return None, {}
    if _PHONEME_CACHE['mtime'] == mtime and _PHONEME_CACHE['pattern'] is not None:
        return _PHONEME_CACHE['pattern'], _PHONEME_CACHE['mapping']
    try:
        with open(PHONEME_MAP_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        mapping = {
            str(k): str(v)
            for k, v in (raw.get('safe_auto_replace') or {}).items()
            if isinstance(k, str) and k and isinstance(v, str) and v
        }
        if not mapping:
            return None, {}
        ordered = sorted(mapping.keys(), key=len, reverse=True)
        pattern = re.compile('|'.join(re.escape(k) for k in ordered))
        _PHONEME_CACHE.update({'mtime': mtime, 'pattern': pattern, 'mapping': mapping})
        return pattern, mapping
    except Exception:
        return None, {}


def _apply_fish_phonemes(text):
    pattern, mapping = _load_phoneme_map()
    if not pattern or not text:
        return text
    parts = _PHONEME_SPLIT_RE.split(text)
    for i in range(0, len(parts), 2):
        if parts[i]:
            parts[i] = pattern.sub(lambda m: mapping[m.group(0)], parts[i])
    return ''.join(parts)


def _strip_edge_voice_markup(text):
    """Edge 链路彻底剥离方括号标签、完整音素注音区间与 Drama 3 词级/语言标签。"""
    cleaned = re.sub(r'\[[^\]]{1,80}\]\s*', '', text)
    cleaned = _PHONEME_SPAN_RE.sub('', cleaned)
    cleaned = _PHONEME_TOKEN_RE.sub('', cleaned)
    cleaned = _DRAMA3_XML_RE.sub('', cleaned)
    return cleaned.strip()


def _strip_drama3_markup(text):
    """非 drama-3 模型剥离 Drama 3 专属配对 XML / 语言标签，防止 S2.1 直接念出标签词。"""
    return _DRAMA3_XML_RE.sub('', text).strip()


def _infer_voice_tier(cfg):
    if not isinstance(cfg, dict):
        return 'free'
    heroine_models = {
        str((cfg.get(name) or {}).get('tts_model') or FISH_TTS_MODEL).strip()
        for name in VOICED_HEROINES
    }
    narrator_cfg = cfg.get('旁白') or {}
    narrator_is_free_fish = (
        not str(narrator_cfg.get('voice') or '').startswith('edge:')
        and str(narrator_cfg.get('tts_model') or FISH_FREE_TTS_MODEL).strip() == FISH_FREE_TTS_MODEL
    )
    if len(heroine_models) == 1 and narrator_is_free_fish:
        hm = next(iter(heroine_models))
        for tier_id, spec in VOICE_TIERS.items():
            if spec['heroine_model'] == hm:
                return tier_id
    return 'custom'


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
        "language": (
            FISH_DEFAULT_STYLE["language"]
            if cfg.get("language") is None
            else _clean_token(cfg.get("language"), r"[A-Za-z0-9_-]{1,35}", 35)
        ),
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
    cleaned["__settings__"]["voice_tier"] = _infer_voice_tier(cleaned)
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


def _fish_headers(tts_model=None, audio_format='mp3', api_key=None):
    key = api_key or _resolve_fish_api_key()[0]
    if not key:
        return None
    model = str(tts_model or _get_current_fish_tts_model() or FISH_TTS_MODEL).strip()
    allowed = {m["id"] for m in FISH_TTS_MODELS}
    if model not in allowed:
        model = FISH_TTS_MODEL
    fmt_meta = FISH_AUDIO_FORMATS.get(str(audio_format or 'mp3').lower(), FISH_AUDIO_FORMATS['mp3'])
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": fmt_meta["mime"],
        "model": model
    }


def _fish_request_json(url, params=None, timeout=6, retries=0, api_key=None):
    key = api_key or _resolve_fish_api_key()[0]
    if not key:
        return None
    headers = {"Authorization": f"Bearer {key}"}
    last_err = None
    for attempt in range(max(1, int(retries) + 1)):
        try:
            res = _fish_http_get(url, headers=headers, params=params or {}, timeout=timeout)
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


def _build_fish_payload(text, voice_id, cfg=None, tts_model=None):
    """Fish Audio /v1/tts：构建完整官方 v1 参数载荷（兼容 s2.1-pro / s2.1-pro-free / drama-3 / s2-pro）。"""
    fish_cfg = _normalize_fish_cfg(cfg or {})
    fmt = fish_cfg["format"]
    model = str(tts_model or (cfg or {}).get("tts_model") or FISH_TTS_MODEL).strip()
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
        "condition_on_previous_chunks": fish_cfg["condition_on_previous_chunks"],
        "max_new_tokens": fish_cfg["max_new_tokens"],
        "early_stop_threshold": fish_cfg["early_stop_threshold"],
    }
    if model not in ("s2.1-pro", "s2.1-pro-free"):
        payload["repetition_penalty"] = fish_cfg["repetition_penalty"]
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


_THUMB_SPECS = {'avatar': (160, 82), 'plate': (720, 84)}


def _resolve_image_thumb(root, image_root, target, thumb_mode):
    if thumb_mode not in _THUMB_SPECS:
        return target
    try:
        rel = target.relative_to(image_root)
    except ValueError:
        return target
    if any(part.startswith(('.', '_')) for part in rel.parts):
        return target
    src_mtime = target.stat().st_mtime_ns
    pre = image_root / '_thumbs' / rel.parent / f'{rel.stem}.{thumb_mode}.webp'
    if pre.is_file():
        try:
            if pre.stat().st_mtime_ns >= src_mtime:
                return pre
        except OSError:
            pass
    try:
        from PIL import Image
    except Exception:
        return pre if pre.is_file() else target
    cache_dir = root / '.round-runtime' / 'thumbs'
    cache_key = hashlib.sha1(f'{rel.as_posix()}:{src_mtime}:{thumb_mode}'.encode('utf-8')).hexdigest()[:20]
    cached = cache_dir / f'{cache_key}.{thumb_mode}.webp'
    if cached.is_file():
        return cached
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        max_w, quality = _THUMB_SPECS[thumb_mode]
        with Image.open(target) as im:
            conv = im.convert('RGBA') if im.mode in ('RGBA', 'LA', 'P') else im.convert('RGB')
            w, h = conv.size
            if w > max_w:
                conv = conv.resize((max_w, max(1, int(round(h * (max_w / w))))), Image.Resampling.LANCZOS)
            tmp = cached.with_suffix('.tmp.webp')
            conv.save(tmp, format='WEBP', quality=quality, method=4)
            os.replace(tmp, cached)
        return cached
    except Exception:
        return pre if pre.is_file() else target


def _serve_public_file(filename):
    root = Path(BASE_DIR).resolve()
    target = (root / filename).resolve()
    image_root = (root / 'txt文件' / 'image').resolve()
    image_allowed = target.is_relative_to(image_root) and target.suffix.lower() in IMAGE_EXTENSIONS
    if (not target.is_relative_to(root) or not target.is_file() or
            any(part.startswith('.') for part in Path(filename).parts) or
            not (filename in PUBLIC_FILES or image_allowed)):
        abort(404)
    serve_path = target
    if image_allowed:
        thumb_mode = (request.args.get('thumb') or '').strip().lower()
        if thumb_mode in _THUMB_SPECS:
            serve_path = _resolve_image_thumb(root, image_root, target, thumb_mode)
    response = send_file(serve_path)
    if filename in {'main_template.html', 'voice_manager.html', 'voice_client.js', 'story_client.js', 'story_client.css', 'data.json'}:
        response.headers['Cache-Control'] = 'no-cache'
    elif image_allowed:
        response.headers['Cache-Control'] = 'public, max-age=86400'
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


@app.route('/api/fish_key', methods=['GET', 'POST', 'DELETE'])
def fish_key_api():
    """管理本机受保护的 Fish Audio API Key 缓存（.cache/fish_api_key.json），永不回显明文。"""
    if request.method == 'GET':
        key, source = _resolve_fish_api_key()
        return jsonify({
            'configured': bool(key),
            'masked': _mask_fish_key(key) if key else '',
            'source': source,
            'cache_path': '.cache/fish_api_key.json',
        })
    if request.method == 'DELETE':
        try:
            _clear_cached_fish_key()
            key, source = _resolve_fish_api_key()
            return jsonify({
                'status': 'success',
                'msg': '已清除本地缓存密钥' + ('（当前仍检测到环境变量回退）' if key else '。'),
                'configured': bool(key),
                'masked': _mask_fish_key(key) if key else '',
                'source': source,
            })
        except OSError:
            return jsonify({'error': '清除本地密钥缓存失败，请检查文件权限。'}), 503

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({'error': '请求体必须是 JSON 对象。'}), 400
    raw_key = payload.get('api_key', '')
    verify = bool(payload.get('verify', False))
    try:
        saved = _save_cached_fish_key(raw_key)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except OSError:
        return jsonify({'error': '写入本地密钥缓存失败，请检查存储空间或权限。'}), 503

    verify_ok = None
    verify_msg = ''
    if verify:
        credit = _fish_request_json(
            f"{FISH_BASE_URL}/wallet/self/api-credit",
            params={"check_free_credit": "true"},
            timeout=6,
            retries=0,
            api_key=saved,
        )
        verify_ok = credit is not None
        verify_msg = '密钥已保存且连通正常。' if verify_ok else '密钥已保存，但余额探针未通过（请核对密钥或网络）。'
    return jsonify({
        'status': 'success',
        'msg': verify_msg or '密钥已保存至本机受保护缓存（.cache/fish_api_key.json）。',
        'configured': True,
        'masked': _mask_fish_key(saved),
        'source': 'local_cache',
        'verified': verify_ok,
    })


@app.route('/api/voice_tier', methods=['POST'])
def voice_tier_api():
    """一键切换三档语音品质：free(全免费推荐) / pro(三女主S2.1 Pro) / drama(三女主Drama 3高消费)。"""
    payload = request.get_json(silent=True) or {}
    tier = str(payload.get('tier') or '').strip().lower() if isinstance(payload, dict) else ''
    if tier not in VOICE_TIERS:
        return jsonify({'error': '不支持的语音档位，仅允许 free / pro / drama。'}), 400
    spec = VOICE_TIERS[tier]
    try:
        cfg = _load_config()
        cfg.setdefault('__settings__', {})
        cfg['__settings__']['fish_tts_model'] = spec['heroine_model']
        cfg['__settings__']['voice_tier'] = tier
        for heroine in VOICED_HEROINES:
            if isinstance(cfg.get(heroine), dict) and not _is_edge_voice(cfg[heroine].get('voice', '')):
                cfg[heroine]['tts_model'] = spec['heroine_model']
        if isinstance(cfg.get('旁白'), dict) and not _is_edge_voice(cfg['旁白'].get('voice', '')):
            cfg['旁白']['tts_model'] = spec['narrator_model']
        if isinstance(cfg.get('default'), dict) and not _is_edge_voice(cfg['default'].get('voice', '')):
            cfg['default']['tts_model'] = FISH_FREE_TTS_MODEL
        cleaned = _save_config(cfg)
        return jsonify({
            'status': 'success',
            'tier': tier,
            'msg': f'已切换至 {spec["label"]}',
            'config': cleaned,
        })
    except ConfigError as exc:
        return jsonify({'error': str(exc)}), 409
    except (ValueError, OSError) as exc:
        return jsonify({'error': f'档位切换失败：{exc}'}), 503


@app.route('/api/voices', methods=['GET'])
def get_voices():
    """返回 Fish Audio 可选音色模型。"""
    key, _ = _resolve_fish_api_key()
    if not key:
        return jsonify({"voices": [], "error": "missing FISH_API_KEY", "tts_models": FISH_TTS_MODELS}), 200

    search = (request.args.get("search") or request.args.get("title") or "").strip()
    own_data = None if search else _fish_request_json(f"{FISH_BASE_URL}/model", params={"page_size": 100, "self": "true"}, api_key=key)
    public_params = {"page_size": 100}
    if search:
        public_params["title"] = search[:80]
    else:
        public_params["sort_by"] = "task_count"
    public_data = _fish_request_json(f"{FISH_BASE_URL}/model", params=public_params, api_key=key)
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
    key, _ = _resolve_fish_api_key()
    if not key:
        return jsonify({"ok": False, "error": "missing FISH_API_KEY"}), 200

    package = _fish_request_json(f"{FISH_BASE_URL}/wallet/self/package", timeout=6, retries=0, api_key=key)
    credit = _fish_request_json(
        f"{FISH_BASE_URL}/wallet/self/api-credit",
        params={"check_free_credit": "true"},
        timeout=6,
        retries=0,
        api_key=key,
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


def _find_cfg_by_voice(raw_voice_param, speaker=''):
    all_cfg = _load_config()
    sp_name = str(speaker or '').strip()
    if sp_name and sp_name != '__settings__' and isinstance(all_cfg.get(sp_name), dict):
        return all_cfg[sp_name]
    for k, v in all_cfg.items():
        if k == '__settings__':
            continue
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


def _disk_cache_path(key):
    s = str(key or '').strip()
    if not TTS_DISK_CACHE_DIR or not _HEX64_RE.fullmatch(s):
        return ''
    return os.path.join(TTS_DISK_CACHE_DIR, f'{s}.bin')


def _read_disk_tts_cache(key):
    path = _disk_cache_path(key)
    if not path or not os.path.isfile(path):
        return None
    try:
        st = os.stat(path)
        if st.st_size <= 0 or st.st_size > TTS_CACHE_MAX_BYTES:
            return None
        with open(path, 'rb') as f:
            data = f.read()
        if not data:
            return None
        try:
            os.utime(path, None)
        except OSError:
            pass
        return data
    except OSError:
        return None


def _write_disk_tts_cache(key, audio):
    path = _disk_cache_path(key)
    if not path or not audio or len(audio) > TTS_DISK_CACHE_MAX_BYTES:
        return
    with TTS_DISK_CACHE_LOCK:
        try:
            os.makedirs(TTS_DISK_CACHE_DIR, exist_ok=True)
            tmp_path = f'{path}.{uuid.uuid4().hex}.tmp'
            with open(tmp_path, 'wb') as f:
                f.write(audio)
            os.replace(tmp_path, path)
            entries = []
            total = 0
            for item in Path(TTS_DISK_CACHE_DIR).glob('*.bin'):
                try:
                    st = item.stat()
                    entries.append((st.st_mtime, st.st_size, item))
                    total += st.st_size
                except OSError:
                    continue
            if total > TTS_DISK_CACHE_MAX_BYTES:
                entries.sort(key=lambda row: row[0])
                keep_name = os.path.basename(path)
                for _mtime, sz, item in entries:
                    if total <= TTS_DISK_CACHE_MAX_BYTES:
                        break
                    if item.name == keep_name:
                        continue
                    try:
                        item.unlink()
                        total -= sz
                    except OSError:
                        continue
        except OSError:
            pass


def _is_tts_cached(key):
    with TTS_STATE_LOCK:
        if key in TTS_CACHE or key in TTS_INFLIGHT:
            return True
    path = _disk_cache_path(key)
    return bool(path and os.path.isfile(path))


def _cached_tts(key, producer, *, slot_timeout=4):
    """相同文本、模型和参数共用生成任务；内存 + 磁盘双层 LRU 缓存，只缓存成功音频。"""
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
        disk_audio = _read_disk_tts_cache(key)
        if disk_audio:
            job['audio'] = disk_audio
            with TTS_STATE_LOCK:
                if len(disk_audio) <= TTS_CACHE_MAX_BYTES:
                    TTS_CACHE[key] = (time.monotonic(), disk_audio)
                    TTS_CACHE_BYTES += len(disk_audio)
                    while TTS_CACHE and (len(TTS_CACHE) > TTS_CACHE_MAX_ENTRIES or TTS_CACHE_BYTES > TTS_CACHE_MAX_BYTES):
                        _, (_, old_audio) = TTS_CACHE.popitem(last=False)
                        TTS_CACHE_BYTES -= len(old_audio)
            return disk_audio
        acquired = TTS_SLOTS.acquire(timeout=slot_timeout)
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
        _write_disk_tts_cache(key, audio)
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


def _fish_audio(payload, tts_model, on_chunk=None, api_key=None):
    fmt = str((payload or {}).get('format') or 'mp3').lower()
    headers = _fish_headers(tts_model, fmt, api_key=api_key)
    if not headers:
        raise TtsError('尚未配置 Fish Audio 密钥，请在主页「系统 → 语音与密钥」或「声学工坊」填入保存。', 503)
    try:
        response = _fish_http_post(
            f'{FISH_BASE_URL}/v1/tts', json=payload,
            headers=headers, timeout=FISH_HTTP_TIMEOUT, stream=True
        )
        try:
            if response.status_code != 200:
                status = response.status_code
                if status == 429:
                    _record_fish_429()
                try:
                    err_snippet = (response.text or '')[:300].replace('\n', ' ')
                except Exception:
                    err_snippet = ''
                print(f"⚠️ Fish /v1/tts 请求失败 [{status}] model={tts_model}: {err_snippet}")
                message = '语音服务暂时不可用，请稍后重试。'
                if status in (401, 403):
                    message = '语音服务授权失败，请检查 Fish Audio 密钥或音色权限。'
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
            _record_fish_ok()
            return b''.join(parts)
        finally:
            response.close()
    except requests.Timeout as exc:
        raise TtsError('语音生成等待超时，请稍后重试。', 504) from exc
    except requests.RequestException as exc:
        raise TtsError('语音服务连接失败，请检查网络后重试。', 502) from exc


def _stream_cached_tts(key, factory, mimetype='audio/mpeg'):
    """复用现有缓存及请求去重；单客户端提前取消不再毒化同 key 的并发等待者与缓存。"""
    messages = queue.Queue(maxsize=8)
    stopped = threading.Event()

    def emit(kind, value):
        while not stopped.is_set():
            try:
                messages.put((kind, value), timeout=0.2)
                return
            except queue.Full:
                continue

    def worker():
        sent = False
        def chunk(data):
            nonlocal sent
            if not stopped.is_set():
                emit('audio', data)
                sent = True
        try:
            audio = _cached_tts(key, lambda: factory(chunk))
            if not sent and not stopped.is_set():
                emit('audio', audio)
            if not stopped.is_set():
                emit('done', None)
        except Exception as exc:
            if not stopped.is_set():
                emit('error', exc)

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


def _prepare_tts_job(data):
    """统一构建 /api/tts 与后台预热任务的规范化载荷与 SHA-256 缓存键，确保 100% 命中。"""
    raw_text = _SUBTEXT_RUBY_RE.sub(r'\1', str((data or {}).get('text') or ''))
    text = raw_text.strip().replace('【', '').replace('】', '').replace('*', '')
    if len(text) > TTS_MAX_TEXT_LENGTH:
        raise TtsError(f'文本超过 {TTS_MAX_TEXT_LENGTH} 字符上限', 413)
    if not text:
        raise TtsError('请提供需要朗读的文本。', 400)
    speaker = str((data or {}).get('speaker') or '').strip()
    raw_voice = str((data or {}).get('voice') or '').strip()
    matched = _find_cfg_by_voice(raw_voice, speaker=speaker)
    voice = raw_voice or str(matched.get('voice') or 'fish:')
    model_name, _, voice_id = voice.partition(':')
    if not voice_id and ':' not in voice:
        voice_id = voice
    audio_mime = 'audio/mpeg'
    audio_ext = 'mp3'
    stream_factory = None
    if model_name == 'edge':
        if voice_id in EDGE_UNAVAILABLE_HINTS or not voice_id:
            voice_id = EDGE_DEFAULT_VOICE
        text = _strip_edge_voice_markup(text)
        if not text:
            raise TtsError('没有可朗读的文本。', 400)
        rate = _normalize_edge_param((data or {}).get('rate') or matched.get('rate') or '-8%', 'rate')
        pitch = _normalize_edge_param((data or {}).get('pitch') or matched.get('pitch') or '-4Hz', 'pitch')
        volume = _normalize_edge_param((data or {}).get('volume') or matched.get('volume') or '+0%', 'volume')
        key_data = ['edge', text, voice_id, rate, pitch, volume]
        producer = lambda: _edge_audio(text, voice_id, rate, pitch, volume)
    else:
        api_key, _ = _resolve_fish_api_key()
        if not api_key:
            raise TtsError('尚未配置 Fish Audio 密钥，请在主页「系统 → 语音与密钥」或「声学工坊」填入保存。', 503)
        runtime_cfg = dict(matched)
        for name in FISH_DEFAULT_STYLE:
            if (data or {}).get(name) is not None:
                runtime_cfg[name] = data[name]
        tts_model = _normalize_fish_tts_model(
            (data or {}).get('tts_model') or matched.get('tts_model') or _get_current_fish_tts_model()
        )
        if tts_model != 'drama-3':
            text = _strip_drama3_markup(text)
        emotion = str((data or {}).get('emotion') or '').strip()
        existing_tags = len(re.findall(r'\[[^\]\r\n]{1,80}\]', text))
        if emotion and len(emotion) <= 48 and existing_tags < 2:
            allow_emotion = (
                bool(re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9 ，,、_-]+', emotion))
                if tts_model == 'drama-3'
                else bool(re.fullmatch(r'[A-Za-z0-9 ,_-]+', emotion))
            )
            if allow_emotion:
                text = f'[{emotion}] {text}'
        text = _apply_fish_phonemes(text)
        if not text.strip():
            raise TtsError('没有可朗读的文本。', 400)
        payload = _build_fish_payload(text, voice_id, runtime_cfg, tts_model=tts_model)
        fmt_meta = FISH_AUDIO_FORMATS.get(payload.get('format', 'mp3'), FISH_AUDIO_FORMATS['mp3'])
        audio_mime = fmt_meta['mime']
        audio_ext = fmt_meta['ext']
        key_data = ['fish', tts_model, payload]
        producer = lambda: _fish_audio(payload, tts_model, api_key=api_key)
        stream_factory = lambda emit: _fish_audio(payload, tts_model, on_chunk=emit, api_key=api_key)
    key = hashlib.sha256(json.dumps(key_data, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    return {
        'key': key,
        'model_name': model_name,
        'audio_mime': audio_mime,
        'audio_ext': audio_ext,
        'producer': producer,
        'stream_factory': stream_factory,
    }


def prewarm_tts_items(items):
    """低优先级后台预合成最多 6 句语音；严格受限于 2 并发与 429 冷却，绝不抢占实时播放。"""
    if not isinstance(items, (list, tuple)) or not items:
        return 0
    if _in_fish_429_cooldown():
        return 0
    jobs = []
    seen_keys = set()
    for raw in items[:6]:
        if not isinstance(raw, dict):
            continue
        try:
            job = _prepare_tts_job(raw)
        except (TtsError, ConfigError):
            continue
        key = job['key']
        if key in seen_keys or _is_tts_cached(key):
            continue
        seen_keys.add(key)
        jobs.append(job)
    if not jobs:
        return 0

    def _run_batch():
        for job in jobs:
            if _in_fish_429_cooldown():
                break
            if _is_tts_cached(job['key']):
                continue
            if not TTS_PREFETCH_SLOTS.acquire(timeout=0.5):
                continue
            try:
                _cached_tts(job['key'], job['producer'], slot_timeout=0.1)
            except Exception:
                pass
            finally:
                TTS_PREFETCH_SLOTS.release()

    threading.Thread(target=_run_batch, daemon=True).start()
    return len(jobs)


@app.route('/api/tts/prefetch', methods=['POST'])
def tts_prefetch_api():
    """接收前端即将播放的 1~6 句语音列表，异步预热到内存+磁盘缓存。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
        return jsonify({'error': 'items 必须为列表。'}), 400
    scheduled = prewarm_tts_items(payload['items'])
    return jsonify({
        'status': 'accepted',
        'scheduled': scheduled,
        'cooldown': _in_fish_429_cooldown(),
    }), 202


@app.route('/api/tts', methods=['GET', 'POST'])
def tts_api():
    data = _request_tts_data()
    try:
        job = _prepare_tts_job(data)
        if job['model_name'] != 'edge' and data.get('stream') is True and job['stream_factory'] is not None:
            return _stream_cached_tts(job['key'], job['stream_factory'], mimetype=job['audio_mime'])
        audio = _cached_tts(job['key'], job['producer'])
        response = send_file(io.BytesIO(audio), mimetype=job['audio_mime'], download_name=f"tts.{job['audio_ext']}")
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
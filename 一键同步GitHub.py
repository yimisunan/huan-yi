#!/usr/bin/env python3
"""深渊天平 · 安卓/Pydroid3 一键同步 GitHub 脚本（纯标准库，无需安装 git）。

核心特性：
  1. 默认启用「智能增量同步」：仅请求 1 次 GitHub 文件树（~35 KB）按 Git Blob SHA-1
     对比本地差异，**只下载真正新增或改动的文件**（跳过 90 MB 未改动立绘，通常 1～3 秒完成）；
     若遇 API 限流或指定 --full-zip / --zip，自动平滑回退到整包 ZIP 模式；
  2. 完整支持 GitHub 的「新增 / 修改 / 删除」三类同步，并校验每个下载文件的 SHA-1 指纹；
  3. 硬保护根目录 .git/（Git 仓库）及本地存档与运行数据（data.json、存档/*、
     voice_config.json、.cache/fish_api_key.json、.round-runtime/、.scene-chat/、语音仓库/、.env 等），绝不覆盖或删除；
  4. 覆盖或删除前自动备份到 .sync-backup/<时间戳>/（保留最近 5 份），支持 --rollback 一键撤销。

Pydroid 3 用法：
  先停止「语音运行.py」，直接打开本文件点运行（▶）按提示确认即可。
常用参数：
  python 一键同步GitHub.py                # 交互确认增量同步（首次运行可一键清理本地多余旧文件）
  python 一键同步GitHub.py --dry-run      # 仅预览差异（约 35 KB 流量），不修改任何文件
  python 一键同步GitHub.py --yes          # 免确认执行新增/修改/已跟踪删除
  python 一键同步GitHub.py --yes --prune  # 免确认并完全对齐 GitHub（本地多余旧文件移入备份）
  python 一键同步GitHub.py --rollback     # 一键回滚到最近一次同步前的状态
  python 一键同步GitHub.py --full-zip     # 强制使用整包 ZIP 模式（不受 API 每小时 60 次限制）
  python 一键同步GitHub.py --zip 包路径   # 使用浏览器手动下载的 GitHub ZIP 离线同步
  python 一键同步GitHub.py --mirror URL   # 可选代理/镜像前缀（也可设环境变量 GITHUB_MIRROR）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

DEFAULT_REPO = 'yimisunan/huan-yi'
DEFAULT_BRANCH = 'main'
SYNC_STATE_FILE = '.sync-state.json'
SYNC_BACKUP_DIR = '.sync-backup'
TOKEN_FILE = '.github_sync_token'
MAX_BACKUPS = 5
SERVICE_PORT = 5000
USER_AGENT = 'huan-yi-android-sync/2.0'

# 本地专属目录：绝不覆盖、绝不删除、不纳入同步管理（根目录 .git/ 另有独立硬保护防火墙）。
LOCAL_ONLY_TOP_DIRS = frozenset({
    '.git', '.operit', '.backup', '.into-backup', '.round-runtime',
    '.scene-chat', '.sync-backup', '语音仓库', '日志', 'vosi',
    'node_modules', '.venv', 'venv', '.cache', '.pytest_cache', '.mypy_cache',
    'build', 'dist',
})
LOCAL_ONLY_NESTED_DIRS = frozenset({
    'scene_chat_dev/tmp',
    'txt文件/.story-reading',
})
LOCAL_ONLY_FILES = frozenset({
    SYNC_STATE_FILE,
    TOKEN_FILE,
    '.fish_api_key',
    '.cache/fish_api_key.json',
    '.env',
    '.env.local',
})
LOCAL_ONLY_SUFFIXES = (
    '.bak', '.log', '.tmp', '.pyc', '.pyo', '.orig', '.rej', '.prev',
    '.pem', '.key', '.p12', '.pfx', '~',
)
LOCAL_ONLY_MARKERS = ('.bak-', '.into-backup-', '.round-tmp-', '.sync-tmp-', '.ss-tmp-')

# 初始模板保护：
# - SEED_ONLY_FILES：单文件本地缺失时从 GitHub 补齐，本地存在即绝对保护（不覆盖、不删除）；
# - SEED_ONLY_DIRS：整目录原子判定——仅当本地目录不存在或为空（全新安装）时整套补齐初始模板；
#   只要本地已有任意真实存档文件，远端该目录下所有文件（含 P2 新增空档 JSON 模板）一律跳过，
#   防止往玩家既有旧存档里误塞空模板，格式演进完全交由 save_store 自动无损迁移。
SEED_ONLY_FILES = frozenset({'data.json', 'voice_config.json'})
SEED_ONLY_DIRS = ('存档/',)


def is_git_metadata_path(rel_posix: str) -> bool:
    """Return True if path targets root .git/ or any nested .git entry (case-insensitive)."""
    normalized = rel_posix.replace('\\', '/').strip('/')
    if not normalized:
        return False
    return any(part.lower() == '.git' for part in normalized.split('/'))


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def is_local_only(rel_posix: str) -> bool:
    """Return True if path belongs strictly to local VCS (.git)/runtime/secrets/backups."""
    rel = rel_posix.replace('\\', '/').strip('/')
    if not rel:
        return True
    if is_git_metadata_path(rel):
        return True
    parts = rel.split('/')
    if parts[0] in LOCAL_ONLY_TOP_DIRS or '__pycache__' in parts:
        return True
    for nested in LOCAL_ONLY_NESTED_DIRS:
        if rel == nested or rel.startswith(nested + '/'):
            return True
    name = parts[-1]
    if rel in LOCAL_ONLY_FILES or name in LOCAL_ONLY_FILES:
        return True
    if name.startswith('.env.') and name != '.env.example':
        return True
    if name.startswith('.trashed-'):
        return True
    if name.endswith(LOCAL_ONLY_SUFFIXES) or any(m in name for m in LOCAL_ONLY_MARKERS):
        return True
    return False


def _assert_not_protected_target(root: Path, rel_posix: str) -> None:
    """Final hard-protection firewall blocking any write/delete to .git/ or local-only paths."""
    norm = rel_posix.replace('\\', '/').strip('/')
    parts = [p for p in norm.split('/') if p]
    if not parts or rel_posix.startswith('/') or '..' in parts:
        raise RuntimeError(f'硬保护拦截：非法相对路径：{rel_posix}')
    if is_git_metadata_path(norm) or is_local_only(norm):
        raise RuntimeError(f'硬保护拦截：禁止修改或删除受保护路径：{rel_posix}')
    root_res = root.resolve()
    target_res = (root / Path(*parts)).resolve()
    if target_res == root_res or not _is_within(target_res, root_res):
        raise RuntimeError(f'硬保护拦截：目标路径越界项目根目录：{rel_posix}')
    git_dir_logical = root_res / '.git'
    if target_res == git_dir_logical or _is_within(target_res, git_dir_logical):
        raise RuntimeError(f'硬保护拦截：严禁修改或删除根目录 .git/：{rel_posix}')
    git_dir_raw = root / '.git'
    if git_dir_raw.exists():
        git_dir_res = git_dir_raw.resolve()
        if target_res == git_dir_res or _is_within(target_res, git_dir_res):
            raise RuntimeError(f'硬保护拦截：严禁修改或删除根目录 .git/：{rel_posix}')


def _seed_dir_prefix(rel_posix: str) -> str:
    """Return matching SEED_ONLY_DIRS prefix (e.g. '存档/') if rel_posix lies inside one."""
    rel = rel_posix.replace('\\', '/').strip('/')
    for prefix in SEED_ONLY_DIRS:
        if rel.startswith(prefix):
            return prefix
    return ''


def _seed_dir_has_existing_data(root: Path, prefix: str) -> bool:
    """Return True if a seed-only directory (e.g. 存档/) already holds any real local file."""
    base = root / prefix.rstrip('/')
    if not base.is_dir():
        return False
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '__pycache__']
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for fname in filenames:
            if fname.startswith('.'):
                continue
            rel = f'{rel_dir}/{fname}'
            if is_local_only(rel):
                continue
            full = Path(dirpath) / fname
            if not full.is_symlink() and full.is_file():
                return True
    return False


def is_seed_only(rel_posix: str) -> bool:
    """Return True if file is a player save/config template protected once present locally."""
    rel = rel_posix.replace('\\', '/').strip('/')
    if rel in SEED_ONLY_FILES:
        return True
    return bool(_seed_dir_prefix(rel))


def is_nomedia_marker(rel_posix: str) -> bool:
    """Return True if path is an Android .nomedia gallery-shield marker (presence-only)."""
    return Path(rel_posix.replace('\\', '/')).name == '.nomedia'


def git_blob_sha1_bytes(data: bytes) -> str:
    """Compute exact Git blob SHA-1 matching GitHub Git Trees API."""
    h = hashlib.sha1()
    h.update(f'blob {len(data)}\0'.encode('ascii'))
    h.update(data)
    return h.hexdigest()


def git_blob_sha1_file(path: Path) -> str:
    size = path.stat().st_size
    h = hashlib.sha1()
    h.update(f'blob {size}\0'.encode('ascii'))
    with path.open('rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _touch_mtime(path: Path) -> None:
    """Explicitly refresh mtime on the visible target path so Android FUSE/MediaStore updates date_modified."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def _sync_temp_path(dest: Path) -> Path:
    # Always use a non-dot temp filename (still matched by LOCAL_ONLY_MARKERS '.sync-tmp-')
    # so Android 11+ MediaProvider FUSE does not skip indexing the renamed file.
    safe_base = dest.name.lstrip('.') or 'file'
    return dest.parent / f'{safe_base}.sync-tmp-{os.getpid()}'


def atomic_write_bytes(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _sync_temp_path(dest)
    try:
        with tmp.open('wb') as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, dest)
        _touch_mtime(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def atomic_copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _sync_temp_path(dest)
    try:
        with src.open('rb') as sf, tmp.open('wb') as df:
            shutil.copyfileobj(sf, df, 65536)
            df.flush()
            try:
                os.fsync(df.fileno())
            except OSError:
                pass
        os.replace(tmp, dest)
        _touch_mtime(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def is_local_service_running(port: int = SERVICE_PORT) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.4):
            return True
    except OSError:
        return False


def load_token(root: Path, cli_token: str = '') -> str:
    if cli_token.strip():
        return cli_token.strip()
    env_tok = os.environ.get('GITHUB_TOKEN', '').strip()
    if env_tok:
        return env_tok
    tok_path = root / TOKEN_FILE
    if tok_path.is_file():
        return tok_path.read_text(encoding='utf-8').strip()
    return ''


def _apply_mirror(url: str, mirror: str) -> str:
    m = mirror.strip()
    if not m:
        return url
    prefix = m if m.endswith('/') else m + '/'
    return prefix + url


_OFFICIAL_GITHUB_HOSTS = frozenset({
    'github.com',
    'api.github.com',
    'raw.githubusercontent.com',
    'codeload.github.com',
})


def _is_official_github_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or '').lower()
        return host in _OFFICIAL_GITHUB_HOSTS
    except ValueError:
        return False


def _headers_for_url(url: str, token: str = '', accept_json: bool = False) -> dict[str, str]:
    headers = {'User-Agent': USER_AGENT}
    if accept_json:
        headers['Accept'] = 'application/vnd.github+json'
    if token and _is_official_github_url(url):
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _http_get_bytes(url: str, headers: dict[str, str], timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def fetch_github_tree(repo: str, branch: str, token: str = '', timeout: int = 20) -> tuple[str, dict[str, dict]]:
    """Fetch commit SHA and full recursive blob tree via GitHub API (~35 KB JSON).

    Returns (commit_sha, {rel_posix: {'sha': blob_sha1, 'size': int}}).
    """
    # Resolve branch head commit SHA so subsequent raw downloads stay pinned to one atomic commit.
    commit_url = f'https://api.github.com/repos/{repo}/commits/{urllib.parse.quote(branch, safe="")}'
    headers = _headers_for_url(commit_url, token=token, accept_json=True)
    commit_data = json.loads(_http_get_bytes(commit_url, headers, timeout=timeout).decode('utf-8'))
    commit_sha = commit_data['sha']
    tree_sha = commit_data['commit']['tree']['sha']

    tree_url = f'https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1'
    tree_data = json.loads(_http_get_bytes(tree_url, headers, timeout=timeout).decode('utf-8'))
    if tree_data.get('truncated'):
        raise RuntimeError('GitHub 文件树返回截断，将自动回退至整包 ZIP 模式')
    entries: dict[str, dict] = {}
    for item in tree_data.get('tree', []):
        if item.get('type') != 'blob':
            continue
        rel = item.get('path', '').strip('/')
        if not rel or is_local_only(rel):
            continue
        entries[rel] = {'sha': item['sha'], 'size': int(item.get('size') or 0)}
    return commit_sha, entries


def download_incremental_files(
    repo: str,
    commit_sha: str,
    rel_paths: list[str],
    expected_shas: dict[str, str],
    dest_dir: Path,
    *,
    token: str = '',
    mirror: str = '',
    timeout: int = 35,
) -> dict[str, Path]:
    """Download ONLY changed/added files pinned to commit_sha, verifying every Git blob SHA-1."""
    downloaded: dict[str, Path] = {}
    total_count = len(rel_paths)
    total_bytes = 0
    dest_res = dest_dir.resolve()
    for idx, rel in enumerate(rel_paths, 1):
        norm = rel.replace('\\', '/').strip('/')
        parts = [p for p in norm.split('/') if p]
        if not parts or rel.startswith('/') or '..' in parts:
            raise RuntimeError(f'硬保护拦截：非法相对路径：{rel}')
        if is_git_metadata_path(rel) or is_local_only(rel):
            raise RuntimeError(f'硬保护拦截：禁止下载写入受保护路径：{rel}')
        out_path = (dest_dir / Path(*parts)).resolve()
        if out_path == dest_res or not _is_within(out_path, dest_res):
            raise RuntimeError(f'硬保护拦截：下载目标越界临时目录：{rel}')
        quoted = urllib.parse.quote(rel, safe='/')
        raw_url = f'https://raw.githubusercontent.com/{repo}/{commit_sha}/{quoted}'
        urls = [_apply_mirror(raw_url, mirror), raw_url] if mirror.strip() else [raw_url]
        data = None
        last_err = None
        for u in urls:
            try:
                data = _http_get_bytes(u, _headers_for_url(u, token=token), timeout=timeout)
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                last_err = exc
        if data is None:
            raise RuntimeError(f'下载文件失败（{rel}）：{last_err}')
        actual_sha = git_blob_sha1_bytes(data)
        want_sha = expected_shas.get(rel)
        if want_sha and actual_sha != want_sha:
            raise ValueError(f'文件校验不通过（{rel}）：期望 {want_sha[:10]}，实际 {actual_sha[:10]}')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        downloaded[rel] = out_path
        total_bytes += len(data)
        print(f'  增量下载 [{idx}/{total_count}] {rel} ({len(data) / 1024:.1f} KB)')
    print(f'  增量下载完成：{total_count} 个文件，共 {total_bytes / 1024:.1f} KB（全部 SHA-1 校验通过）')
    return downloaded


def build_zip_urls(repo: str, branch: str, token: str = '', mirror: str = '') -> list[str]:
    if token:
        urls = [f'https://api.github.com/repos/{repo}/zipball/{branch}']
    else:
        urls = [
            f'https://codeload.github.com/{repo}/zip/refs/heads/{branch}',
            f'https://github.com/{repo}/archive/refs/heads/{branch}.zip',
        ]
    if mirror.strip():
        mirror_sources = [
            f'https://codeload.github.com/{repo}/zip/refs/heads/{branch}',
            f'https://github.com/{repo}/archive/refs/heads/{branch}.zip',
        ]
        urls = [_apply_mirror(u, mirror) for u in mirror_sources] + urls
    return urls


def download_zip(urls: list[str], dest_zip: Path, token: str = '', timeout: int = 45) -> str:
    """Download full GitHub archive ZIP to dest_zip; returns the URL that succeeded."""
    ctx = ssl.create_default_context()
    last_error = None
    for url in urls:
        print(f'正在下载整包：{url}')
        headers = _headers_for_url(url, token=token, accept_json=_is_official_github_url(url) and bool(token))
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                total = int(resp.headers.get('Content-Length') or 0)
                downloaded = 0
                last_print = 0.0
                with dest_zip.open('wb') as out:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - last_print >= 0.4:
                            mb = downloaded / (1024 * 1024)
                            if total > 0:
                                pct = downloaded * 100.0 / total
                                print(f'  已下载 {mb:.2f} MB ({pct:.0f}%)', end='\r', flush=True)
                            else:
                                print(f'  已下载 {mb:.2f} MB...', end='\r', flush=True)
                            last_print = now
                print(f'  下载完成：{downloaded / (1024 * 1024):.2f} MB' + ' ' * 16)
                return url
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_error = exc
            print(f'  尝试失败：{exc}')
    raise RuntimeError(f'无法从 GitHub 下载最新快照：{last_error}')


def extract_github_zip(zip_path: Path, extract_dir: Path) -> tuple[Path, str]:
    """Verify and safely extract a GitHub archive ZIP (skipping any .git entries); return (tree_root, inferred_ref)."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f'下载的 ZIP 压缩包损坏（文件：{bad}）')
        members = zf.infolist()
        if not members:
            raise ValueError('下载的 ZIP 压缩包为空')
        top_dirs = set()
        for info in members:
            name = info.filename
            if name.startswith('/') or '\\' in name or '..' in Path(name).parts:
                raise ValueError(f'检测到不安全的压缩包路径：{name}')
            first = name.split('/', 1)[0]
            if first:
                top_dirs.add(first)
        if len(top_dirs) != 1:
            raise ValueError(f'压缩包顶层目录结构异常：{sorted(top_dirs)}')
        top_name = next(iter(top_dirs))
        skipped_git = 0
        for info in members:
            rel_after_top = info.filename[len(top_name):].lstrip('/')
            if rel_after_top and is_git_metadata_path(rel_after_top):
                skipped_git += 1
                continue
            zf.extract(info, extract_dir)
        if skipped_git:
            print(f'  （安全保护：已忽略压缩包内 {skipped_git} 个 .git 项，本地 .git/ 不受任何影响）')
        tree_root = extract_dir / top_name
        tree_root.mkdir(parents=True, exist_ok=True)
        if not tree_root.is_dir():
            raise ValueError('解压后未找到有效项目根目录')
        return tree_root, top_name


def scan_files(base_dir: Path) -> dict[str, Path]:
    """Scan all regular files under base_dir returning {posix_rel_path: absolute_path}."""
    found: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(base_dir):
        rel_dir = Path(dirpath).relative_to(base_dir)
        rel_dir_posix = '' if rel_dir == Path('.') else rel_dir.as_posix()
        pruned = []
        for d in dirnames:
            child_rel = f'{rel_dir_posix}/{d}' if rel_dir_posix else d
            if d.lower() == '.git':
                continue
            if d in LOCAL_ONLY_TOP_DIRS and not rel_dir_posix:
                continue
            if d == '__pycache__' or child_rel in LOCAL_ONLY_NESTED_DIRS:
                continue
            pruned.append(d)
        dirnames[:] = pruned
        for fname in filenames:
            if fname.lower() == '.git':
                continue
            rel_posix = f'{rel_dir_posix}/{fname}' if rel_dir_posix else fname
            full = Path(dirpath) / fname
            if full.is_symlink() or not full.is_file():
                continue
            found[rel_posix] = full
    return found


def load_sync_state(root: Path) -> dict:
    path = root / SYNC_STATE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def compute_sync_plan_from_manifest(
    root: Path,
    remote_entries: dict[str, dict],
    *,
    remote_files: dict[str, Path] | None = None,
    state: dict | None = None,
) -> dict:
    """Compute sync plan from {rel_posix: {'sha': git_blob_sha1, 'size': int}}."""
    state = load_sync_state(root) if state is None else state
    prev_managed = state.get('managed_files') if isinstance(state.get('managed_files'), dict) else {}
    local_all = scan_files(root)

    remote_hashes = {k: v['sha'] for k, v in remote_entries.items() if not is_local_only(k)}
    remote_sizes = {k: int(v.get('size') or 0) for k, v in remote_entries.items() if not is_local_only(k)}

    to_add: list[str] = []
    to_update: list[str] = []
    protected_skipped: list[str] = []
    unchanged: list[str] = []
    populated_seed_dirs = {
        prefix for prefix in SEED_ONLY_DIRS
        if _seed_dir_has_existing_data(root, prefix)
    }

    for rel in sorted(remote_hashes):
        seed_dir = _seed_dir_prefix(rel)
        if seed_dir and seed_dir in populated_seed_dirs:
            protected_skipped.append(rel)
            continue
        local_path = root / rel
        if not local_path.is_file():
            if local_path.exists():
                protected_skipped.append(rel)
            else:
                to_add.append(rel)
            continue
        if is_seed_only(rel):
            protected_skipped.append(rel)
            continue
        # Android 11+ MediaProvider writes internal directory metadata into .nomedia files;
        # .nomedia is a presence-only gallery shield, so once present locally never force-overwrite it.
        if is_nomedia_marker(rel):
            unchanged.append(rel)
            continue
        if git_blob_sha1_file(local_path) != remote_hashes[rel]:
            to_update.append(rel)
        else:
            unchanged.append(rel)

    to_delete_tracked: list[str] = []
    extra_untracked: list[str] = []

    for rel in sorted(local_all):
        if rel in remote_hashes:
            continue
        if is_local_only(rel) or is_seed_only(rel):
            continue
        # Never auto-delete user's custom .nomedia shields.
        if is_nomedia_marker(rel):
            continue
        if rel in prev_managed:
            to_delete_tracked.append(rel)
        else:
            extra_untracked.append(rel)

    download_bytes = sum(remote_sizes.get(rel, 0) for rel in (to_add + to_update))
    return {
        'remote_files': dict(remote_files) if remote_files else {},
        'remote_hashes': remote_hashes,
        'remote_sizes': remote_sizes,
        'download_bytes': download_bytes,
        'to_add': to_add,
        'to_update': to_update,
        'to_delete_tracked': to_delete_tracked,
        'extra_untracked': extra_untracked,
        'protected_skipped': protected_skipped,
        'unchanged': unchanged,
        'has_previous_state': bool(prev_managed),
    }


def compute_sync_plan(root: Path, remote_root: Path, state: dict | None = None) -> dict:
    """Compute sync plan directly from an extracted local directory (ZIP mode)."""
    remote_all = scan_files(remote_root)
    remote_files = {k: v for k, v in remote_all.items() if not is_local_only(k)}
    remote_entries = {
        k: {'sha': git_blob_sha1_file(v), 'size': v.stat().st_size}
        for k, v in remote_files.items()
    }
    return compute_sync_plan_from_manifest(root, remote_entries, remote_files=remote_files, state=state)


def _cleanup_empty_parents(root: Path, rel_paths: list[str]) -> None:
    dirs = set()
    for rel in rel_paths:
        p = (root / rel).parent
        while p != root and root in p.parents:
            dirs.add(p)
            p = p.parent
    for d in sorted(dirs, key=lambda x: len(x.parts), reverse=True):
        rel_posix = d.relative_to(root).as_posix()
        if is_git_metadata_path(rel_posix) or is_local_only(rel_posix) or is_seed_only(rel_posix + '/'):
            continue
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def _prune_old_backups(root: Path, keep: int = MAX_BACKUPS) -> None:
    bdir = root / SYNC_BACKUP_DIR
    if not bdir.is_dir():
        return
    entries = sorted([p for p in bdir.iterdir() if p.is_dir()], key=lambda p: p.name)
    for stale in entries[:-keep]:
        shutil.rmtree(stale, ignore_errors=True)


def apply_sync_plan(
    root: Path,
    plan: dict,
    *,
    prune_extra: bool = False,
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    source_ref: str = '',
    staged_files: dict[str, Path] | None = None,
) -> dict:
    """Apply sync plan atomically with full reversible backup in .sync-backup/<ts>/."""
    file_sources: dict[str, Path] = {**plan.get('remote_files', {}), **(staged_files or {})}
    remote_hashes: dict[str, str] = plan['remote_hashes']
    to_add: list[str] = list(plan['to_add'])
    to_update: list[str] = list(plan['to_update'])
    to_delete: list[str] = list(plan['to_delete_tracked']) + (list(plan['extra_untracked']) if prune_extra else [])

    for rel in to_add + to_update + to_delete:
        _assert_not_protected_target(root, rel)

    for rel in to_add + to_update:
        if rel not in file_sources or not file_sources[rel].is_file():
            raise RuntimeError(f'缺少待写入源文件：{rel}')

    timestamp = time.strftime('%Y%m%d-%H%M%S')
    backup_dir = root / SYNC_BACKUP_DIR / timestamp
    if backup_dir.exists():
        backup_dir = root / SYNC_BACKUP_DIR / f'{timestamp}-{int((time.time() % 1) * 1000):03d}'
    backup_files_dir = backup_dir / 'files'
    has_changes = bool(to_add or to_update or to_delete)

    if has_changes:
        backup_files_dir.mkdir(parents=True, exist_ok=True)
        prev_state_file = root / SYNC_STATE_FILE
        if prev_state_file.is_file():
            shutil.copy2(prev_state_file, backup_dir / 'prev_sync_state.json')
        for rel in to_update + to_delete:
            src = root / rel
            if src.is_file():
                dst = backup_files_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        backup_manifest = {
            'created_at': timestamp,
            'repo': repo,
            'branch': branch,
            'source_ref': source_ref,
            'added': to_add,
            'updated': to_update,
            'deleted': to_delete,
        }
        atomic_write_bytes(
            backup_dir / 'manifest.json',
            json.dumps(backup_manifest, ensure_ascii=False, indent=2).encode('utf-8'),
        )

    write_targets = list(to_add + to_update)
    if '一键同步GitHub.py' in write_targets:
        write_targets.remove('一键同步GitHub.py')
        write_targets.insert(0, '一键同步GitHub.py')

    for rel in write_targets:
        dest_path = root / rel
        if is_nomedia_marker(rel):
            if not dest_path.is_file():
                atomic_copy_file(file_sources[rel], dest_path)
            if not dest_path.is_file():
                raise RuntimeError(f'落盘校验失败：{rel}（防图库标记未成功创建）')
            continue
        atomic_copy_file(file_sources[rel], dest_path)
        expected_sha = remote_hashes.get(rel)
        if expected_sha:
            written_sha = git_blob_sha1_file(dest_path)
            if written_sha != expected_sha:
                raise RuntimeError(
                    f'落盘校验失败：{rel}（期望 {expected_sha[:10]}，磁盘实际 {written_sha[:10]}）'
                )

    for rel in to_delete:
        target = root / rel
        if target.is_file():
            target.unlink()
    if to_delete:
        _cleanup_empty_parents(root, to_delete)

    managed = {
        rel: digest
        for rel, digest in remote_hashes.items()
        if not is_seed_only(rel)
    }
    state_payload = {
        'version': 2,
        'repo': repo,
        'branch': branch,
        'source_ref': source_ref,
        'synced_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'managed_files': managed,
    }
    atomic_write_bytes(
        root / SYNC_STATE_FILE,
        json.dumps(state_payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
    )

    if has_changes:
        _prune_old_backups(root)

    changed_toolpkgs = [
        rel for rel in (to_add + to_update)
        if rel.startswith('scene_chat_dev/artifacts/') and rel.endswith('.toolpkg')
    ]
    changed_toolpkg_details = []
    for rel in changed_toolpkgs:
        pkg_path = root / rel
        st = pkg_path.stat()
        pkg_ver = ''
        try:
            with zipfile.ZipFile(pkg_path, 'r') as zf:
                pkg_ver = str(json.loads(zf.read('manifest.json').decode('utf-8')).get('version') or '').strip()
        except Exception:
            pkg_ver = ''
        changed_toolpkg_details.append({
            'rel': rel,
            'version': pkg_ver,
            'size': st.st_size,
            'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
            'sha1': git_blob_sha1_file(pkg_path)[:10],
        })
    artifacts_dir = root / 'scene_chat_dev/artifacts'
    stale_toolpkgs = []
    if artifacts_dir.is_dir():
        for existing in sorted(artifacts_dir.glob('*.toolpkg')):
            rel_existing = existing.relative_to(root).as_posix()
            if rel_existing not in remote_hashes:
                stale_toolpkgs.append(rel_existing)

    added_nomedia = [rel for rel in to_add if Path(rel).name == '.nomedia']
    self_updated = '一键同步GitHub.py' in (to_add + to_update)
    legacy_save_pending_migration = (
        (root / '存档/全局记忆库.txt').is_file()
        and not (root / '存档/save_state.json').is_file()
    )

    return {
        'added': len(to_add),
        'updated': len(to_update),
        'deleted': len(to_delete),
        'protected': len(plan['protected_skipped']),
        'unchanged': len(plan['unchanged']),
        'backup_dir': str(backup_dir) if has_changes else '',
        'changed_toolpkgs': changed_toolpkgs,
        'changed_toolpkg_details': changed_toolpkg_details,
        'stale_toolpkgs': stale_toolpkgs,
        'added_nomedia': added_nomedia,
        'self_updated': self_updated,
        'legacy_save_pending_migration': legacy_save_pending_migration,
    }


def rollback_latest(root: Path) -> dict:
    """Restore the most recent .sync-backup/<timestamp>/ snapshot."""
    bdir = root / SYNC_BACKUP_DIR
    if not bdir.is_dir():
        raise FileNotFoundError('未找到 .sync-backup/ 备份目录，无法回滚。')
    candidates = sorted(
        [p for p in bdir.iterdir() if p.is_dir() and (p / 'manifest.json').is_file()],
        key=lambda p: p.name,
    )
    if not candidates:
        raise FileNotFoundError('没有可用的同步备份记录。')
    latest = candidates[-1]
    manifest = json.loads((latest / 'manifest.json').read_text(encoding='utf-8'))
    files_dir = latest / 'files'

    restored = 0
    for rel in manifest.get('updated', []) + manifest.get('deleted', []):
        if is_git_metadata_path(rel) or is_local_only(rel):
            continue
        _assert_not_protected_target(root, rel)
        src = files_dir / rel
        if src.is_file():
            atomic_copy_file(src, root / rel)
            restored += 1

    removed_added = 0
    added_list = manifest.get('added', [])
    for rel in added_list:
        if is_seed_only(rel) or is_git_metadata_path(rel) or is_local_only(rel):
            continue
        _assert_not_protected_target(root, rel)
        target = root / rel
        if target.is_file():
            target.unlink()
            removed_added += 1
    if added_list:
        _cleanup_empty_parents(root, added_list)

    prev_state = latest / 'prev_sync_state.json'
    if prev_state.is_file():
        atomic_copy_file(prev_state, root / SYNC_STATE_FILE)

    shutil.rmtree(latest, ignore_errors=True)
    return {'backup_name': latest.name, 'restored': restored, 'removed_added': removed_added}


def _print_list(title: str, items: list[str], limit: int = 25) -> None:
    if not items:
        return
    print(f'\n【{title}】共 {len(items)} 项：')
    for rel in items[:limit]:
        print(f'  - {rel}')
    if len(items) > limit:
        print(f'  ... 以及其余 {len(items) - limit} 项')


def _detect_protected_local_items(root: Path | None) -> list[str]:
    if root is None:
        return []
    detected: list[str] = []
    candidates = [
        ('.git', '.git/（根目录 Git 仓库）'),
        ('.round-runtime', '.round-runtime/'),
        ('.scene-chat', '.scene-chat/'),
        ('语音仓库', '语音仓库/'),
        ('.env', '.env'),
    ]
    for name, label in candidates:
        if (root / name).exists():
            detected.append(label)
    return detected


def _print_summary(plan: dict, mode_label: str, root: Path | None = None) -> None:
    dl_kb = plan.get('download_bytes', 0) / 1024
    dl_str = f'{dl_kb / 1024:.2f} MB' if dl_kb >= 1024 else f'{dl_kb:.1f} KB'
    protected_local = _detect_protected_local_items(root)
    print(f'\n================ 同步差异预览（{mode_label}）================')
    print(f'  新增文件：{len(plan["to_add"])}')
    print(f'  更新文件：{len(plan["to_update"])}')
    print(f'  预计下载体量：{dl_str}（未改动的大立绘等全部跳过）')
    print(f'  GitHub 已删除（自动清理）：{len(plan["to_delete_tracked"])}')
    print(f'  本地多余旧文件（未在 GitHub）：{len(plan["extra_untracked"])}')
    print(f'  已保护存档/配置（绝不覆盖）：{len(plan["protected_skipped"])}')
    if protected_local:
        print(f'  硬保护本地目录/文件（绝不改动）：{", ".join(protected_local)}')
    print(f'  一致无需变动：{len(plan["unchanged"])}')
    _print_list('将新增', plan['to_add'])
    _print_list('将更新', plan['to_update'])
    _print_list('GitHub 已删除，将移入备份清理', plan['to_delete_tracked'])
    _print_list('本地多余旧文件（可选移入备份清理）', plan['extra_untracked'])
    protected_display = list(protected_local) + list(plan['protected_skipped'])
    if protected_display:
        print(f'\n【已自动保护，绝不改动】{", ".join(protected_display[:10])}'
              + (' ...' if len(protected_display) > 10 else ''))
    print('============================================================')


def detect_pending_runtime_journal(root: Path) -> tuple[str, str] | None:
    """Return (rel_path, recovery_hint) if an unfinished runtime/reset journal blocks safe syncing."""
    if (root / '.round-runtime/reset-journal.json').exists():
        return (
            '.round-runtime/reset-journal.json',
            '检测到未完成的新档清理日志（.round-runtime/reset-journal.json），已暂停同步。\n'
            '请先运行 `python 存档清理器.py --recover` 恢复或完成新档操作后再运行同步。',
        )
    if (root / '.round-runtime/journal.json').exists():
        return (
            '.round-runtime/journal.json',
            '检测到未恢复的回合事务日志（.round-runtime/journal.json），已暂停同步。\n'
            '请先运行 `python round_runtime.py recover` 或启动「语音运行.py」自动恢复后再运行同步。',
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='深渊天平 · 一键从 GitHub 增量同步项目文件（自动保护 .git 与存档）')
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPO', DEFAULT_REPO), help='GitHub 仓库 owner/repo')
    parser.add_argument('--branch', default=os.environ.get('GITHUB_BRANCH', DEFAULT_BRANCH), help='分支名（默认 main）')
    parser.add_argument('--mirror', default=os.environ.get('GITHUB_MIRROR', ''), help='可选下载镜像前缀')
    parser.add_argument('--token', default='', help='私有仓库或免限流可选 GitHub Token（默认读 GITHUB_TOKEN 或 .github_sync_token）')
    parser.add_argument('--full-zip', action='store_true', help='强制使用整包 ZIP 模式（跳过 GitHub Trees API）')
    parser.add_argument('--zip', dest='local_zip', default='', help='离线模式：指定已手动下载的 GitHub ZIP 路径')
    parser.add_argument('--dry-run', action='store_true', help='仅预览差异，不修改本地文件')
    parser.add_argument('--yes', '-y', action='store_true', help='跳过交互确认直接执行')
    parser.add_argument('--prune', action='store_true', help='同时清理本地多余旧文件（全部先备份到 .sync-backup/）')
    parser.add_argument('--rollback', action='store_true', help='回滚到最近一次同步前的备份')
    parser.add_argument('--force-while-running', action='store_true', help='忽略本地 5000 端口服务运行检测')
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    print(f'项目根目录：{root}')
    if (root / '.git').exists():
        print('已检测到根目录 .git/：已启用硬保护（绝不扫描、覆写、删除或回滚 Git 仓库目录）')

    if not (root / '语音运行.py').is_file() and not (root / 'story_service.py').is_file():
        print('错误：当前脚本不在深渊天平项目根目录，已停止。')
        return 1

    if not args.dry_run and not args.force_while_running and is_local_service_running():
        print('\n⚠️  检测到本地故事服务（127.0.0.1:5000）正在运行！')
        print('请先在 Pydroid 3 停止「语音运行.py」，再重新运行本同步脚本，防止文件冲突。')
        return 2

    pending_journal = detect_pending_runtime_journal(root)
    if pending_journal is not None:
        print(f'\n⚠️  {pending_journal[1]}')
        return 2

    if args.rollback:
        try:
            res = rollback_latest(root)
            print(f'回滚完成（备份 {res["backup_name"]}）：恢复 {res["restored"]} 个文件，移除 {res["removed_added"]} 个新增文件。')
            return 0
        except Exception as exc:
            print(f'回滚失败：{exc}')
            return 1

    token = load_token(root, args.token)

    with tempfile.TemporaryDirectory(prefix='huan_yi_sync_') as tmp:
        tmp_dir = Path(tmp)
        use_incremental = not args.local_zip and not args.full_zip
        commit_sha = ''
        source_ref = ''
        mode_label = ''
        plan = None

        if use_incremental:
            print(f'正在获取 GitHub 文件树（{args.repo}@{args.branch}，仅 ~35 KB）...')
            try:
                commit_sha, remote_entries = fetch_github_tree(args.repo, args.branch, token=token)
                source_ref = commit_sha[:12]
                mode_label = f'智能增量 · 提交 {source_ref}'
                plan = compute_sync_plan_from_manifest(root, remote_entries)
            except Exception as exc:
                print(f'增量文件树获取失败（{exc}），自动切换整包 ZIP 模式...')
                use_incremental = False

        if not use_incremental:
            zip_path = tmp_dir / 'repo.zip'
            if args.local_zip:
                src_zip = Path(args.local_zip).expanduser().resolve()
                if not src_zip.is_file():
                    print(f'错误：找不到指定的 ZIP 文件：{src_zip}')
                    return 1
                zip_path = src_zip
                mode_label = '本地离线 ZIP'
                print(f'使用本地离线包：{zip_path}')
            else:
                urls = build_zip_urls(args.repo, args.branch, token=token, mirror=args.mirror)
                try:
                    download_zip(urls, zip_path, token=token)
                except RuntimeError as exc:
                    print(f'\n下载失败：{exc}')
                    print('提示：如果手机直连 GitHub 较慢，可开启代理后重试，或使用 --mirror <镜像前缀>，')
                    print('      也可在浏览器下载 main 分支 ZIP 后运行：python 一键同步GitHub.py --zip /路径/huan-yi-main.zip')
                    return 1
                mode_label = '整包 ZIP'
            print('正在校验压缩包并计算文件差异...')
            try:
                remote_root, source_ref = extract_github_zip(zip_path, tmp_dir / 'extracted')
            except Exception as exc:
                print(f'压缩包校验失败：{exc}')
                return 1
            plan = compute_sync_plan(root, remote_root)

        assert plan is not None
        _print_summary(plan, mode_label, root=root)

        if args.dry_run:
            print('\n（--dry-run 预览结束，未改动任何本地文件。）')
            return 0

        has_core_changes = bool(plan['to_add'] or plan['to_update'] or plan['to_delete_tracked'])
        has_extra = bool(plan['extra_untracked'])

        if not has_core_changes and not has_extra:
            apply_sync_plan(root, plan, prune_extra=False, repo=args.repo, branch=args.branch, source_ref=source_ref)
            print('\n✅ 本地文件已与 GitHub 完全一致，无需更新！')
            return 0

        prune_extra = args.prune
        if not args.yes:
            if has_extra:
                print('\n请选择同步方式（.git/、存档、data.json、音色与 .round-runtime 均已硬保护，绝不改动）：')
                print('  [1] 完全对齐 GitHub（推荐）：执行新增/修改，并把本地多余旧文件移入 .sync-backup/ 清理')
                print('  [2] 仅同步新增与修改（保留本地多余旧文件）')
                print('  [0] 取消退出')
                choice = input('请输入选项 [1/2/0]（默认 1）：').strip() or '1'
                if choice == '0':
                    print('已取消同步，未改动任何文件。')
                    return 0
                if choice == '1':
                    prune_extra = True
                elif choice == '2':
                    prune_extra = False
                else:
                    print('输入无效，已取消同步。')
                    return 0
            else:
                ans = input('\n确认开始同步以上变更？(所有覆盖/删除都会先自动备份) [Y/n]：').strip().lower()
                if ans in ('n', 'no'):
                    print('已取消同步，未改动任何文件。')
                    return 0

        staged_files: dict[str, Path] = {}
        need_download = plan['to_add'] + plan['to_update']
        if use_incremental and need_download:
            print(f'\n开始增量下载 {len(need_download)} 个变更文件...')
            try:
                staged_files = download_incremental_files(
                    args.repo, commit_sha, need_download, plan['remote_hashes'],
                    tmp_dir / 'delta', token=token, mirror=args.mirror,
                )
            except Exception as exc:
                print(f'增量下载失败：{exc}')
                print('提示：可改用代理 / --mirror <镜像前缀> 或加 --full-zip 重试。')
                return 1

        summary = apply_sync_plan(
            root, plan, prune_extra=prune_extra,
            repo=args.repo, branch=args.branch, source_ref=source_ref,
            staged_files=staged_files,
        )

    print('\n================ 同步完成 ================')
    print(f'  新增：{summary["added"]}  更新：{summary["updated"]}  清理：{summary["deleted"]}  已保护跳过：{summary["protected"]}')
    if summary['backup_dir']:
        print(f'  本次备份目录：{summary["backup_dir"]}')
        print('  （如发现任何异常，运行 `python 一键同步GitHub.py --rollback` 即可一键撤销）')
    if summary['changed_toolpkgs']:
        print('\n🔔 检测到新版 Operit 2 插件包已同步（已通过落盘 SHA-1 校验）：')
        details = summary.get('changed_toolpkg_details') or []
        if details:
            for item in details:
                ver_part = f'v{item["version"]} | ' if item.get('version') else ''
                print(
                    f'   → {item["rel"]}\n'
                    f'     ({ver_part}{item["size"]:,} B | 写入时间 {item["mtime"]} | SHA1 {item["sha1"]})'
                )
        else:
            for pkg in summary['changed_toolpkgs']:
                print(f'   → {pkg}')
        print('   请在 Operit 2 中同 ID 覆盖导入该插件包（同步脚本只更新项目目录文件，Operit 已安装副本需导入后才会升级版本号）。')
    if summary.get('stale_toolpkgs'):
        print('\n⚠️  检测到旧版遗留插件包仍在 scene_chat_dev/artifacts/（未自动清理）：')
        for old_pkg in summary['stale_toolpkgs']:
            print(f'   - {old_pkg}')
        print('   请避免误导入旧包，或运行 `python 一键同步GitHub.py --prune` 将旧包移入备份清理。')
    if summary['added_nomedia']:
        print('\n🖼️ 已写入防图库扫描标记（.nomedia）：')
        print('   若手机相册此前已扫出旧 .d.ts 伪视频或立绘，重启手机或清理「媒体存储」缓存即可消失。')
    if summary.get('self_updated'):
        print('\n🔄 「一键同步GitHub.py」脚本自身已更新，下次运行将自动使用新逻辑。')
    if summary.get('legacy_save_pending_migration'):
        print('\n💾 已完整保护本地旧版存档（未写入仓库里的空档 P2 JSON 模板）：')
        print('   重启「语音运行.py」加载或提交新回合时，引擎将从现有存档自动无损迁移至 P2 结构。')
    print('\n📌 下一步：在 Pydroid 3 重新运行「语音运行.py」，并刷新浏览器页面即可生效。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""停止本地服务后初始化新档与管理精简存档槽；--preview只读，默认留档槽，--list-backups/--restore回档，--recover恢复中断。"""

import argparse
from contextlib import contextmanager
from datetime import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import uuid

DEFAULT_ROOT = Path(__file__).resolve().parent
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))
import save_store

TX = '.round-runtime/reset-journal.json'
EPOCH = '.round-runtime/save-epoch.json'
BACKUPS = '.round-runtime/reset-backups'
SAVE_SLOTS = '.round-runtime/save-slots'
MAX_RESET_BACKUPS = 10
LEGACY_RETIRED_ROSTER = '存档/次要NPC名册.txt'
LEGACY_MEMORY_LAYERS = save_store.LEGACY_MEMORY_LAYERS_PATH

SLIM_SLOT_FILES = (
    save_store.SAVE_STATE_PATH,
    save_store.MEMORY_LAYERS_PATH,
    save_store.RECENT_PLAYBACK_PATH,
    save_store.RENDERED_MEMORY_PATH,
    save_store.RENDERED_ITEMS_PATH,
    'data.json',
    '.round-runtime/state.json',
)
SLIM_SLOT_DIRS = (
    '.round-runtime/interaction',
)
_STORY_BLOB_RE = re.compile(
    r'[0-9a-f]{64}\.(?:context\.json|result\.txt|read-audit\.json|assembled\.json|delivery\.json|stage1\.json)'
)
_STORY_TMP_RE = re.compile(r'\.round-tmp-[^\s/]+')
_SS_TMP_RE = re.compile(r'\.ss-tmp-[^\s/]+')
_SLOT_ID_RE = re.compile(r'[A-Za-z0-9_-]{4,80}')


def _initial_data_dict():
    return {
        'round': 0,
        'sceneTitle': '徐家主宅',
        'storyNodes': [],
        'presence': {
            '沈知韫': {'location': '徐家主宅', 'reason': '常住'},
            '徐念薇': {'location': '大学', 'reason': '工作日在大学'},
            '苏婉青': {'location': '市中心顶层公寓', 'reason': '常住'},
            '徐志北': {'location': '徐家主宅', 'reason': '常住'},
        },
        'state_version': 0,
    }


def _initial_templates():
    init_data = _initial_data_dict()
    state = save_store.default_state()
    layers = save_store.default_layers('', prologue_active=False)
    recent = save_store.default_recent()
    raw_map = save_store.render_bundle_bytes(state, layers, recent, data_dict=init_data)
    return {k: v.decode('utf-8') for k, v in raw_map.items()}


TEMPLATES = _initial_templates()
INITIAL_GLOBAL_MEMORY = TEMPLATES[save_store.RENDERED_MEMORY_PATH]
INITIAL_ITEM_CATALOG = TEMPLATES[save_store.RENDERED_ITEMS_PATH]


def project_root(root):
    path = Path(root)
    if path.is_symlink():
        raise RuntimeError('项目目录不能是软链接')
    path = path.resolve()
    if not all((path / name).is_file() for name in ('injection_core.py', 'round_runtime.py')):
        raise RuntimeError('目标不是项目根目录，已停止')
    return path


def safe(root, relative):
    path = root / relative
    path.resolve().relative_to(root)
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise RuntimeError('拒绝软链接路径：' + relative)
    return path


def inventory(root, relative):
    path = safe(root, relative)
    if not path.exists():
        return None
    if path.is_file():
        return {'kind': 'file', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if not path.is_dir():
        raise RuntimeError('不支持的文件类型：' + relative)
    digest = hashlib.sha256()
    for parent, dirs, files in os.walk(path, followlinks=False):
        dirs.sort()
        files.sort()
        for name in sorted(dirs + files):
            child = Path(parent) / name
            safe(root, str(child.relative_to(root)))
            if not child.is_file() and not child.is_dir():
                raise RuntimeError('目录含特殊文件：' + relative)
            digest.update(str(child.relative_to(path)).encode('utf-8') + b'\0')
            digest.update(b'D' if child.is_dir() else b'F' + child.read_bytes())
    return {'kind': 'dir', 'sha256': digest.hexdigest()}


def plan_reset(root):
    root = project_root(root)
    paths = list(TEMPLATES) + ['data.json', '.round-runtime/state.json', '.round-runtime/journal.json', EPOCH]
    for retired in (LEGACY_RETIRED_ROSTER, LEGACY_MEMORY_LAYERS):
        if safe(root, retired).exists():
            paths.append(retired)
    save_dir = safe(root, '存档')
    if save_dir.is_dir():
        for child in sorted(save_dir.iterdir()):
            if _SS_TMP_RE.fullmatch(child.name):
                paths.append(str(child.relative_to(root)))
    story = safe(root, '.round-runtime/story')
    if story.exists():
        for child in sorted(story.iterdir()):
            if (
                child.name in ('tasks.json', 'shop_inquiries.json')
                or _STORY_BLOB_RE.fullmatch(child.name)
                or _STORY_TMP_RE.fullmatch(child.name)
            ):
                paths.append(str(child.relative_to(root)))
    runtime = safe(root, '.round-runtime')
    if runtime.exists():
        for child in sorted(runtime.glob('work-*')):
            if child.is_symlink() or child.is_dir():
                paths.append(str(child.relative_to(root)))
    paths.extend(['txt文件/.story-reading', '.round-runtime/interaction', '.scene-chat'])
    return [{'path': path, 'before': inventory(root, path),
             'action': '初始化' if path in TEMPLATES or path == 'data.json' else '新档标识' if path == EPOCH else '清理'} for path in paths]


def _effective_port(port=None):
    if port is not None:
        return int(port)
    env_p = os.environ.get('STORY_PORT', '').strip()
    if env_p.isdigit():
        return int(env_p)
    return 5000


def server_running(port=None):
    target_port = _effective_port(port)
    try:
        with socket.create_connection(('127.0.0.1', target_port), timeout=0.4):
            return True
    except (ConnectionRefusedError, TimeoutError):
        return False
    except OSError as exc:
        raise RuntimeError(f'无法确认本地服务已停止，请检查端口{target_port}') from exc


@contextmanager
def reset_lock(root, *, port=None):
    if server_running(port=port):
        raise RuntimeError('请先停止Pydroid3本地服务及Operit故事桥接，再运行清理器')
    import round_runtime as rr
    runtime = safe(root, '.round-runtime')
    runtime.mkdir(exist_ok=True)
    try:
        with rr.acquire_process_lock(root, timeout=0.0, conflict_message='回合正在提交，未清理任何存档'):
            if server_running(port=port):
                raise RuntimeError('本地服务仍在运行，未清理任何存档')
            yield
    except rr.ConflictError as exc:
        raise RuntimeError(str(exc)) from exc


def sync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF, errno.EACCES}:
            raise


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.round-tmp-reset-' + uuid.uuid4().hex)
    try:
        with temp.open('xb') as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        sync_dir(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def write_json(path, data):
    atomic(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def remove(path):
    if path.is_symlink():
        raise RuntimeError('拒绝删除软链接：' + str(path))
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    sync_dir(path.parent)


def _fsync_file(path):
    try:
        with Path(path).open('rb') as handle:
            os.fsync(handle.fileno())
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF, errno.EACCES}:
            raise


def copy_saved(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
        for parent, _, files in os.walk(target):
            for name in files:
                _fsync_file(Path(parent) / name)
            sync_dir(parent)
    else:
        shutil.copy2(source, target)
        _fsync_file(target)
    sync_dir(target.parent)


def _dir_size_bytes(path):
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for parent, _, files in os.walk(path, followlinks=False):
        for fn in files:
            try:
                total += (Path(parent) / fn).stat().st_size
            except OSError:
                pass
    return total


def _summarize_save_state(st_obj, data_obj):
    rt = (st_obj.get('runtime') or {}) if isinstance(st_obj, dict) else {}
    clock = rt.get('clock') or ((data_obj.get('story_runtime') or {}).get('clock') if isinstance(data_obj, dict) else None) or {}
    presence = (st_obj.get('presence') or {}) if isinstance(st_obj, dict) else {}
    loc = (presence.get('徐志北') or {}).get('location') or (data_obj.get('sceneTitle') if isinstance(data_obj, dict) else '') or '徐家主宅'
    prologue = rt.get('prologue') or (data_obj.get('prologue') if isinstance(data_obj, dict) else None) or {}
    inter = (data_obj.get('interaction') or {}) if isinstance(data_obj, dict) else {}
    actions = int(inter.get('actions') if inter.get('actions') is not None else (rt.get('action_index') or 0))
    round_num = int(rt.get('memory_round') or (data_obj.get('round') if isinstance(data_obj, dict) else 0) or 1)
    panels = (st_obj.get('panels') or {}) if isinstance(st_obj, dict) else {}
    host_p = panels.get('系统宿主') or {}
    intl_p = (st_obj.get('intimate') or {}) if isinstance(st_obj, dict) else {}
    host_phys = intl_p.get('host_phys') if isinstance(intl_p.get('host_phys'), dict) else {}
    vig_obj = (st_obj.get('vigilance') or {}) if isinstance(st_obj, dict) else {}
    vig_targets = vig_obj.get('目标') if isinstance(vig_obj.get('目标'), dict) else {}
    max_vig = max((int((t or {}).get('警惕', 0) or 0) for t in vig_targets.values() if isinstance(t, dict)), default=0)
    panel_summary = {
        'host': {
            '体力': int(host_p.get('体力', 100) or 0),
            '亲密耐力': int(host_phys.get('vigor', 100) if host_phys.get('vigor') is not None else 100),
            '积分': int(host_p.get('积分', 0) or 0),
            '魅力': int(host_p.get('魅力', 70) or 70),
            '商业嗅觉': int(host_p.get('商业嗅觉', 0) or 0),
            '私密珍藏': len(intl_p.get('keepsakes') or []),
        },
        'heroines': {
            h: {
                '好感': int((panels.get(h) or {}).get('好感', 0) or 0),
                '羞耻': int((panels.get(h) or {}).get('羞耻', 100) or 0),
                '堕落': int((panels.get(h) or {}).get('堕落', 0) or 0),
            }
            for h in save_store.HEROINES
        },
        'vigilance': {
            '位置': str(vig_obj.get('位置') or '外地'),
            '最高警惕': max_vig,
        },
    }
    return {
        'round': round_num,
        'day': int(clock.get('day') or 1),
        'time': str(clock.get('time') or ''),
        'weekday': str(rt.get('weekday') or prologue.get('weekday') or ''),
        'location': str(loc),
        'prologue_title': str(prologue.get('title') or ''),
        'scenario_id': str(prologue.get('scenario_id') or ''),
        'actions': actions,
        'panel_summary': panel_summary,
    }


def current_save_summary(root):
    root = project_root(root)
    st_obj = {}
    data_obj = {}
    try:
        st_obj, _, _ = save_store.load_bundle(root)
    except Exception:
        st_obj = {}
    data_path = safe(root, 'data.json')
    if data_path.is_file():
        try:
            data_obj = json.loads(data_path.read_text(encoding='utf-8'))
        except Exception:
            data_obj = {}
    return _summarize_save_state(st_obj, data_obj)


def _prune_auto_slots(root, keep=MAX_RESET_BACKUPS):
    slots_dir = safe(root, SAVE_SLOTS)
    if not slots_dir.is_dir():
        return
    auto_dirs = []
    for p in sorted(slots_dir.iterdir(), key=lambda item: item.name):
        if not p.is_dir() or p.is_symlink():
            continue
        meta_path = p / 'slot_meta.json'
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if meta.get('kind') != 'manual':
            auto_dirs.append(p)
    if len(auto_dirs) <= keep:
        return
    for old in auto_dirs[:-keep]:
        try:
            shutil.rmtree(old)
        except OSError:
            pass
    sync_dir(slots_dir)


def create_save_slot(root, label='', kind='manual'):
    """Create a slim restorable save slot under .round-runtime/save-slots/<slot_id>/ (excludes bulky caches)."""
    root = project_root(root)
    if kind not in ('manual', 'auto_before_reset', 'auto_before_restore'):
        raise ValueError('存档槽类型无效')
    clean_label = re.sub(r'[\r\n]+', ' ', str(label or '')).strip()[:60]
    if not clean_label:
        clean_label = {
            'manual': '手动存档',
            'auto_before_reset': '重开新档前自动备份',
            'auto_before_restore': '回档前自动备份',
        }[kind]
    slot_id = datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8]
    slot_dir = safe(root, SAVE_SLOTS + '/' + slot_id)
    files_root = slot_dir / 'files'
    files_root.mkdir(parents=True, exist_ok=False)
    manifest = {}
    try:
        for rel in (*SLIM_SLOT_FILES, *SLIM_SLOT_DIRS):
            src = safe(root, rel)
            if not src.exists():
                continue
            inv = inventory(root, rel)
            dst = files_root / rel
            copy_saved(src, dst)
            manifest[rel] = inv
        summary = current_save_summary(root)
        meta = {
            'version': 2,
            'id': slot_id,
            'label': clean_label,
            'kind': kind,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'size_bytes': _dir_size_bytes(files_root),
            'files_manifest': manifest,
            **summary,
        }
        write_json(slot_dir / 'slot_meta.json', meta)
    except BaseException:
        shutil.rmtree(slot_dir, ignore_errors=True)
        raise
    if kind != 'manual':
        _prune_auto_slots(root)
    return {k: v for k, v in meta.items() if k != 'files_manifest'}


def _inspect_legacy_backup(root, backup_dir):
    manifest_path = backup_dir / 'manifest.json'
    if not manifest_path.is_file():
        return None
    try:
        rec = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    entries = rec.get('entries') or []
    st_obj = {}
    data_obj = {}
    for idx, item in enumerate(entries):
        if not isinstance(item, dict) or item.get('before') is None:
            continue
        p = item.get('path')
        saved = backup_dir / f'slot-{idx}'
        if not saved.is_file():
            continue
        if p == save_store.SAVE_STATE_PATH:
            try:
                st_obj = json.loads(saved.read_text(encoding='utf-8'))
            except Exception:
                pass
        elif p == 'data.json':
            try:
                data_obj = json.loads(saved.read_text(encoding='utf-8'))
            except Exception:
                pass
    summary = _summarize_save_state(st_obj, data_obj)
    ts_part = backup_dir.name[:15]
    try:
        created_at = datetime.strptime(ts_part, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        created_at = ts_part
    return {
        'version': 1,
        'id': backup_dir.name,
        'label': '历史重开备份（旧版）',
        'kind': 'auto_before_reset',
        'created_at': created_at,
        'size_bytes': _dir_size_bytes(backup_dir),
        'legacy': True,
        **summary,
    }


def list_save_slots(root):
    """List slim save slots (.round-runtime/save-slots) plus backward-compatible legacy reset-backups."""
    root = project_root(root)
    results = []
    seen = set()
    slots_dir = safe(root, SAVE_SLOTS)
    if slots_dir.is_dir():
        for child in sorted(slots_dir.iterdir(), key=lambda p: p.name, reverse=True):
            if not child.is_dir() or child.is_symlink():
                continue
            meta_path = child / 'slot_meta.json'
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
            except Exception:
                continue
            item = {k: v for k, v in meta.items() if k != 'files_manifest'}
            item['legacy'] = False
            results.append(item)
            seen.add(child.name)
    legacy_dir = safe(root, BACKUPS)
    if legacy_dir.is_dir():
        for child in sorted(legacy_dir.iterdir(), key=lambda p: p.name, reverse=True):
            if child.name in seen or not child.is_dir() or child.is_symlink():
                continue
            if not re.fullmatch(r'\d{8}_\d{6}_[0-9a-f]{32}', child.name):
                continue
            legacy_meta = _inspect_legacy_backup(root, child)
            if legacy_meta is not None:
                results.append(legacy_meta)
    results.sort(key=lambda item: (str(item.get('created_at') or ''), str(item.get('id') or '')), reverse=True)
    return results


def _resolve_slot_location(root, slot_id):
    if not isinstance(slot_id, str) or not _SLOT_ID_RE.fullmatch(slot_id):
        raise ValueError('存档槽编号无效')
    slim_dir = safe(root, SAVE_SLOTS + '/' + slot_id)
    if slim_dir.is_dir() and (slim_dir / 'slot_meta.json').is_file():
        return 'slim', slim_dir
    legacy_dir = safe(root, BACKUPS + '/' + slot_id)
    if legacy_dir.is_dir() and (legacy_dir / 'manifest.json').is_file():
        return 'legacy', legacy_dir
    raise ValueError('未找到指定存档槽：' + slot_id)


def delete_save_slot(root, slot_id):
    root = project_root(root)
    _kind, slot_dir = _resolve_slot_location(root, slot_id)
    remove(slot_dir)
    return {'status': 'deleted', 'slot_id': slot_id}


def restore_save_slot(root, slot_id, *, auto_backup_current=True, request_id=None):
    """Atomically restore a slim save slot (or legacy backup) and rotate save_epoch."""
    root = project_root(root)
    if safe(root, TX).exists():
        raise RuntimeError('存在未完成清理，请先运行 --recover')
    slot_kind, slot_dir = _resolve_slot_location(root, slot_id)

    restore_sources = {}
    if slot_kind == 'slim':
        meta = json.loads((slot_dir / 'slot_meta.json').read_text(encoding='utf-8'))
        manifest = meta.get('files_manifest') or {}
        files_root = slot_dir / 'files'
        for rel, expected_inv in manifest.items():
            if rel not in (*SLIM_SLOT_FILES, *SLIM_SLOT_DIRS):
                raise RuntimeError('存档槽含非法路径：' + rel)
            src = files_root / rel
            if not src.exists():
                raise RuntimeError('存档槽缺失文件：' + rel)
            rel_inside = str(src.relative_to(root))
            if expected_inv is not None and inventory(root, rel_inside) != expected_inv:
                raise RuntimeError('存档槽校验和失败：' + rel)
            restore_sources[rel] = src
        if save_store.SAVE_STATE_PATH not in restore_sources and save_store.RENDERED_MEMORY_PATH not in restore_sources:
            raise RuntimeError('存档槽缺少核心存档文件')
    else:
        rec = json.loads((slot_dir / 'manifest.json').read_text(encoding='utf-8'))
        for idx, item in enumerate(rec.get('entries') or []):
            rel = item.get('path')
            if rel not in (*SLIM_SLOT_FILES, *SLIM_SLOT_DIRS) or item.get('before') is None:
                continue
            saved = slot_dir / f'slot-{idx}'
            if not saved.exists():
                raise RuntimeError('旧版备份缺少文件：' + rel)
            if inventory(root, str(saved.relative_to(root))) != item['before']:
                raise RuntimeError('旧版备份校验和失败：' + rel)
            restore_sources[rel] = saved
        if save_store.SAVE_STATE_PATH not in restore_sources and save_store.RENDERED_MEMORY_PATH not in restore_sources:
            raise RuntimeError('旧版备份缺少核心存档文件')

    auto_backup = None
    if auto_backup_current:
        try:
            auto_backup = create_save_slot(root, label='回档前自动备份', kind='auto_before_restore')
        except Exception:
            auto_backup = None

    # 清理全部运行时临时与过时缓存，避免旧任务/旧预览污染回档后的存档
    for item in plan_reset(root):
        rel = item['path']
        if rel in restore_sources or rel == EPOCH:
            continue
        target = safe(root, rel)
        if target.exists():
            remove(target)

    # 写回存档槽内全部核心文件与目录
    for rel, src in restore_sources.items():
        dst = safe(root, rel)
        if src.is_file():
            if dst.is_dir():
                remove(dst)
            atomic(dst, src.read_bytes())
        else:
            if dst.exists():
                remove(dst)
            copy_saved(src, dst)

    # 若存档槽仅含 P2 JSON（或需同步单向渲染），确认 bundle 一致并补全缺失的 .txt / data.json
    st, ly, rc = save_store.load_bundle(root)
    save_store.save_bundle(root, st, ly, rc)

    new_epoch = uuid.uuid4().hex
    write_json(safe(root, EPOCH), {'version': 1, 'epoch': new_epoch, 'request_id': request_id or f'restore-{slot_id}'})
    return {
        'status': 'restored',
        'slot_id': slot_id,
        'save_epoch': new_epoch,
        'auto_backup': auto_backup,
        'summary': current_save_summary(root),
    }


def read_record(root):
    record = json.loads(safe(root, TX).read_text(encoding='utf-8'))
    if not isinstance(record, dict) or record.get('version') != 1 or record.get('phase') not in ('prepared', 'committed'):
        raise RuntimeError('清理恢复记录无效，已保留现场')
    if not re.fullmatch(r'\d{8}_\d{6}_[0-9a-f]{32}', record.get('id', '')):
        raise RuntimeError('清理恢复目录无效')
    entries = record.get('entries')
    if (not isinstance(entries, list) or not entries
            or any(not isinstance(item, dict) or not isinstance(item.get('path'), str)
                   or 'before' not in item for item in entries)
            or len({item['path'] for item in entries}) != len(entries)
            or type(record.get('keep_backup')) is not bool):
        raise RuntimeError('清理恢复清单无效')
    for index, item in enumerate(entries):
        rel = item['path']
        allowed = rel in (
            *TEMPLATES, LEGACY_RETIRED_ROSTER, LEGACY_MEMORY_LAYERS, 'data.json',
            '.round-runtime/state.json', '.round-runtime/journal.json', EPOCH,
            '.round-runtime/story/tasks.json', '.round-runtime/story/shop_inquiries.json',
            'txt文件/.story-reading', '.round-runtime/interaction', '.scene-chat',
        )
        allowed = allowed or bool(re.fullmatch(r'\.round-runtime/story/' + _STORY_BLOB_RE.pattern, rel))
        allowed = allowed or bool(re.fullmatch(r'\.round-runtime/story/' + _STORY_TMP_RE.pattern, rel))
        allowed = allowed or bool(re.fullmatch(r'存档/' + _SS_TMP_RE.pattern, rel))
        allowed = allowed or bool(re.fullmatch(r'\.round-runtime/work-[^/]+', rel))
        if not allowed:
            raise RuntimeError('恢复清单越出允许范围')
        safe(root, rel)
        if item['before'] is not None:
            saved = BACKUPS + '/' + record['id'] + '/slot-' + str(index)
            if inventory(root, saved) != item['before']:
                raise RuntimeError('恢复副本校验失败：' + rel)
    return record


def prune_backups(root, keep=MAX_RESET_BACKUPS):
    backups_dir = safe(root, BACKUPS)
    if not backups_dir.is_dir():
        return
    dirs = sorted(
        (p for p in backups_dir.iterdir() if p.is_dir() and not p.is_symlink()
         and re.fullmatch(r'\d{8}_\d{6}_[0-9a-f]{32}', p.name)),
        key=lambda p: p.name,
    )
    if len(dirs) <= keep:
        return
    for old in dirs[:-keep]:
        try:
            shutil.rmtree(old)
        except OSError:
            pass
    sync_dir(backups_dir)


def finish_record(root, record):
    backup = safe(root, BACKUPS + '/' + record['id'])
    safe(root, TX).unlink()
    sync_dir(root / '.round-runtime')
    # 无论是否 keep_backup，均清理笨重的事务回滚工作副本（长期保留交由精简存档槽承载）
    if backup.exists():
        try:
            shutil.rmtree(backup)
        except OSError:
            print('清理已完成，但临时工作副本未能删除：' + str(backup))
    slot_path = record.get('slim_slot_path')
    if slot_path:
        return str(slot_path)
    return None


def restore_record(root, record):
    if record['phase'] == 'prepared':
        for index, item in enumerate(record['entries']):
            path = safe(root, item['path'])
            if item['before'] is None:
                if path.exists():
                    inventory(root, item['path'])
                    remove(path)
            else:
                saved = safe(root, BACKUPS + '/' + record['id'] + '/slot-' + str(index))
                if saved.is_file():
                    if path.is_dir():
                        inventory(root, item['path'])
                        remove(path)
                    atomic(path, saved.read_bytes())
                else:
                    if path.exists():
                        inventory(root, item['path'])
                        remove(path)
                    copy_saved(saved, path)
            if inventory(root, item['path']) != item['before']:
                raise RuntimeError('恢复结果核对失败：' + item['path'])
    return finish_record(root, record)


def recover(root=DEFAULT_ROOT, *, port=None):
    root = project_root(root)
    with reset_lock(root, port=port):
        if not safe(root, TX).exists():
            return {'status': 'nothing_to_recover'}
        record = read_record(root)
        backup = restore_record(root, record)
        return {'status': 'restored' if record['phase'] == 'prepared' else 'committed', 'backup': backup}


def reset(root=DEFAULT_ROOT, keep_backup=True, *, scenario_id=None, no_prologue=False, port=None):
    root = project_root(root)
    with reset_lock(root, port=port):
        return _reset_files(root, keep_backup=keep_backup, scenario_id=scenario_id, no_prologue=no_prologue)


def _reset_files(root, keep_backup=True, request_id=None, scenario_id=None, no_prologue=False):
    """Caller must hold the same RoundStore lock; CLI additionally requires stopped service."""
    if safe(root, TX).exists():
        raise RuntimeError('存在未完成清理，请先运行 --recover，再决定是否重置')
    slim_slot = None
    if keep_backup:
        try:
            slim_slot = create_save_slot(root, label='重开新档前自动备份', kind='auto_before_reset')
        except Exception:
            slim_slot = None
    entries = plan_reset(root)
    ident = datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex
    backup = safe(root, BACKUPS + '/' + ident)
    backup.mkdir(parents=True)
    record = {
        'version': 1,
        'id': ident,
        'phase': 'prepared',
        'keep_backup': bool(keep_backup),
        'slim_slot_path': str(safe(root, SAVE_SLOTS + '/' + slim_slot['id'])) if slim_slot else None,
        'entries': entries,
    }
    try:
        for index, item in enumerate(entries):
            if item['before'] is not None:
                saved_rel = BACKUPS + '/' + ident + '/slot-' + str(index)
                copy_saved(safe(root, item['path']), safe(root, saved_rel))
                if inventory(root, saved_rel) != item['before']:
                    raise RuntimeError('备份不完整，未开始清理')
        for item in entries:
            if inventory(root, item['path']) != item['before']:
                raise RuntimeError('备份期间文件已变化，未开始清理')
        write_json(backup / 'manifest.json', record)
        write_json(safe(root, TX), record)
    except BaseException:
        if not safe(root, TX).exists():
            shutil.rmtree(backup, ignore_errors=True)
        raise
    templates = _initial_templates()
    try:
        for item in entries:
            path = safe(root, item['path'])
            if item['path'] in templates:
                atomic(path, templates[item['path']].encode('utf-8'))
            elif item['path'] == 'data.json':
                write_json(path, _initial_data_dict())
            elif item['path'] == EPOCH:
                write_json(path, {'version': 1, 'epoch': uuid.uuid4().hex, 'request_id': request_id})
            elif path.exists():
                remove(path)
        for relative, content in templates.items():
            if safe(root, relative).read_text(encoding='utf-8') != content:
                raise RuntimeError('初始化内容核对失败')
        for item in entries:
            if item['path'] not in templates and item['path'] not in ('data.json', EPOCH) and safe(root, item['path']).exists():
                raise RuntimeError('旧档残留核对失败：' + item['path'])
        initial_data = json.loads(safe(root, 'data.json').read_text(encoding='utf-8'))
        if initial_data.get('round') != 0 or initial_data.get('storyNodes') != []:
            raise RuntimeError('新档起始快照无效')
        configuration = safe(root, 'txt文件/互动运行配置.json')
        if (not no_prologue) and configuration.is_file() and json.loads(configuration.read_text(encoding='utf-8')).get('resource', {}).get('scheme') == 'fixed_tiers':
            import importlib.util
            spec = importlib.util.spec_from_file_location('_registered_opening', root / '存档开局随机盲盒.py')
            opening = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(opening)
            chosen_sid = None if (not scenario_id or scenario_id == 'random') else scenario_id
            opening.initialize_prologue(root, request_id or 'reset-' + ident, scenario_id=chosen_sid)
            data = json.loads(safe(root, 'data.json').read_text(encoding='utf-8'))
            if not data.get('prologue') or not data.get('interaction', {}).get('segment_id'):
                raise RuntimeError('新档序幕未完整写入')
        record['phase'] = 'committed'
        write_json(safe(root, TX), record)
    except BaseException:
        try:
            restore_record(root, read_record(root))
        except Exception as exc:
            raise RuntimeError('清理中断，恢复副本已保留；停止服务后运行 --recover') from exc
        raise
    retained = finish_record(root, record)
    return {'status': 'reset', 'backup': retained, 'slot': slim_slot, 'entries': len(entries)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='初始化新档、管理精简存档槽并清理旧回合恢复记录；先停止本地服务和故事桥接')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preview', action='store_true', help='仅列出清理范围，不写文件')
    mode.add_argument('--recover', action='store_true', help='恢复未完成的清理事务')
    mode.add_argument('--list-backups', action='store_true', help='列出全部可回档存档槽与旧版备份')
    mode.add_argument('--restore', metavar='SLOT_ID', help='从指定存档槽原子回档（自动先留当前档备份）')
    backup_group = parser.add_mutually_exclusive_group()
    backup_group.add_argument('--backup', dest='backup', action='store_true', default=True, help='重开前自动留存精简存档槽（默认开启）')
    backup_group.add_argument('--no-backup', dest='backup', action='store_false', help='重开前不留旧档备份')
    parser.add_argument('--scenario', default=None, help='指定序幕场景ID（不传或 random 为盲盒随机）')
    parser.add_argument('--no-prologue', action='store_true', help='仅清空为空白初始档，不写入序幕')
    parser.add_argument('--port', type=int, default=None, help='本地服务检测端口（默认读取 STORY_PORT 或 5000）')
    parser.add_argument('-y', '--yes', action='store_true', help='跳过交互确认直接执行')
    args = parser.parse_args(argv)
    try:
        root = project_root(DEFAULT_ROOT)
        if args.list_backups:
            slots = list_save_slots(root)
            if not slots:
                print('当前暂无已保存的存档槽或历史备份。')
                return 0
            print(f'【深渊天平 · 可回档存档槽（共 {len(slots)} 个）】')
            for s in slots:
                tag = '手动' if s.get('kind') == 'manual' else ('旧版' if s.get('legacy') else '自动')
                kb = max(1, int(s.get('size_bytes') or 0) // 1024)
                print(
                    f"  {s['id']}  [{tag}] {s.get('label','')} | "
                    f"第{s.get('day',1)}天 {s.get('weekday','')} {s.get('time','')} · {s.get('location','')} "
                    f"(行动{s.get('actions',0)}次, {kb}KB)"
                )
            return 0
        if args.recover:
            print('恢复结果：', recover(root, port=args.port))
            return 0
        if args.restore:
            with reset_lock(root, port=args.port):
                res = restore_save_slot(root, args.restore, auto_backup_current=args.backup)
            print(f"✅ 已回档至存档槽：{res['slot_id']}（新档标识 {res['save_epoch'][:10]}…）")
            if res.get('auto_backup'):
                print(f"回档前自动备份：{res['auto_backup']['id']}")
            return 0
        print('【深渊天平 · 新档初始化】\n项目：' + str(root))
        for item in plan_reset(root):
            print('  ' + item['action'] + '：' + item['path'] + ('（不存在）' if item['before'] is None else ''))
        print('保留桥接密钥、语音配置、素材、规则、已有存档槽和历史日志。请先停止本地服务和故事桥接。')
        if args.preview:
            print('仅预览，未修改文件。')
            return 0
        print('本次' + ('自动留存精简存档槽（可随时回档）。' if args.backup else '不留旧档备份（--no-backup）。'))
        if not args.yes and input('确认初始化新档？输入 y 继续，其余取消 > ').strip().lower() != 'y':
            print('已取消，未清理存档。')
            return 0
        result = reset(root, args.backup, scenario_id=args.scenario, no_prologue=args.no_prologue, port=args.port)
        print('✅ 新档初始化完成。重新启动本地服务和故事桥接，再刷新网页；无需手动删除data.json。')
        if result.get('slot'):
            print('旧档已存为精简存档槽：' + result['slot']['id'] + '（可用 --restore 回档）')
        return 0
    except (OSError, ValueError, RuntimeError, EOFError, KeyboardInterrupt) as exc:
        print('❌ 未完成：' + str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""停止本地服务后初始化新档；--preview只读，--backup留旧档，--recover恢复中断。"""

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import errno
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
MAX_RESET_BACKUPS = 10
LEGACY_RETIRED_ROSTER = '存档/次要NPC名册.txt'


def _initial_templates():
    init_data = {
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
    if safe(root, LEGACY_RETIRED_ROSTER).exists():
        paths.append(LEGACY_RETIRED_ROSTER)
    story = safe(root, '.round-runtime/story')
    if story.exists():
        for child in sorted(story.iterdir()):
            if child.name == 'tasks.json' or re.fullmatch(
                r'[0-9a-f]{64}\.(?:context\.json|result\.txt|read-audit\.json|assembled\.json|delivery\.json)',
                child.name,
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


def server_running():
    try:
        with socket.create_connection(('127.0.0.1', 5000), timeout=0.4):
            return True
    except (ConnectionRefusedError, TimeoutError):
        return False
    except OSError as exc:
        raise RuntimeError('无法确认本地服务已停止，请检查端口5000') from exc


@contextmanager
def reset_lock(root):
    if server_running():
        raise RuntimeError('请先停止Pydroid3本地服务及Operit故事桥接，再运行清理器')
    import fcntl
    runtime = safe(root, '.round-runtime')
    runtime.mkdir(exist_ok=True)
    lock = safe(root, '.round-runtime/lock')
    with lock.open('a+b') as handle:
        try:
            fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('回合正在提交，未清理任何存档') from exc
        try:
            if server_running():
                raise RuntimeError('本地服务仍在运行，未清理任何存档')
            yield
        finally:
            fcntl.lockf(handle, fcntl.LOCK_UN)


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
        allowed = rel in (*TEMPLATES, LEGACY_RETIRED_ROSTER, 'data.json', '.round-runtime/state.json', '.round-runtime/journal.json', EPOCH,
                          '.round-runtime/story/tasks.json', 'txt文件/.story-reading', '.round-runtime/interaction', '.scene-chat')
        allowed = allowed or bool(re.fullmatch(r'\.round-runtime/story/[0-9a-f]{64}\.(?:context\.json|result\.txt|read-audit\.json|assembled\.json|delivery\.json)', rel))
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
    sync_dir(root/'.round-runtime')
    if not record['keep_backup']:
        try:
            shutil.rmtree(backup)
        except OSError:
            print('清理已完成，但工作副本未能删除：' + str(backup))
            return str(backup)
    else:
        prune_backups(root)
    return str(backup) if record['keep_backup'] else None


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


def recover(root=DEFAULT_ROOT):
    root = project_root(root)
    with reset_lock(root):
        if not safe(root, TX).exists():
            return {'status': 'nothing_to_recover'}
        record = read_record(root)
        backup = restore_record(root, record)
        return {'status': 'restored' if record['phase'] == 'prepared' else 'committed', 'backup': backup}


def reset(root=DEFAULT_ROOT, keep_backup=False):
    root = project_root(root)
    with reset_lock(root):
        return _reset_files(root, keep_backup)


def _reset_files(root, keep_backup=False, request_id=None):
    """Caller must hold the same RoundStore lock; CLI additionally requires stopped service."""
    if safe(root, TX).exists():
        raise RuntimeError('存在未完成清理，请先运行 --recover，再决定是否重置')
    entries = plan_reset(root)
    ident = datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex
    backup = safe(root, BACKUPS + '/' + ident)
    backup.mkdir(parents=True)
    record = {'version': 1, 'id': ident, 'phase': 'prepared', 'keep_backup': bool(keep_backup), 'entries': entries}
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
        write_json(backup/'manifest.json', record)
        write_json(safe(root, TX), record)
    except BaseException:
        if not safe(root, TX).exists():
            shutil.rmtree(backup, ignore_errors=True)
        raise
    try:
        for item in entries:
            path = safe(root, item['path'])
            if item['path'] in TEMPLATES:
                atomic(path, TEMPLATES[item['path']].encode('utf-8'))
            elif item['path'] == 'data.json':
                write_json(path, {'round': 0, 'sceneTitle': '徐家主宅',
                                  'storyNodes': [],
                                  'presence': {
                                      '沈知韫': {'location': '徐家主宅', 'reason': '常住'},
                                      '徐念薇': {'location': '大学', 'reason': '工作日在大学'},
                                      '苏婉青': {'location': '市中心顶层公寓', 'reason': '常住'},
                                      '徐志北': {'location': '徐家主宅', 'reason': '常住'},
                                  },
                                  'state_version': 0})
            elif item['path'] == EPOCH:
                write_json(path, {'version': 1, 'epoch': uuid.uuid4().hex, 'request_id': request_id})
            elif path.exists():
                remove(path)
        for relative, content in TEMPLATES.items():
            if safe(root, relative).read_text(encoding='utf-8') != content:
                raise RuntimeError('初始化内容核对失败')
        for item in entries:
            if item['path'] not in TEMPLATES and item['path'] not in ('data.json', EPOCH) and safe(root, item['path']).exists():
                raise RuntimeError('旧档残留核对失败：' + item['path'])
        initial_data = json.loads(safe(root, 'data.json').read_text(encoding='utf-8'))
        if initial_data.get('round') != 0 or initial_data.get('storyNodes') != []:
            raise RuntimeError('新档起始快照无效')
        configuration = safe(root,'txt文件/互动运行配置.json')
        if configuration.is_file() and json.loads(configuration.read_text(encoding='utf-8')).get('resource',{}).get('scheme')=='fixed_tiers':
            import importlib.util
            spec = importlib.util.spec_from_file_location('_registered_opening', root/'存档开局随机盲盒.py')
            opening = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(opening)
            opening.initialize_prologue(root, request_id or 'reset-'+ident)
            data = json.loads(safe(root,'data.json').read_text(encoding='utf-8'))
            if not data.get('prologue') or not data.get('interaction',{}).get('segment_id'):
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
    return {'status': 'reset', 'backup': retained, 'entries': len(entries)}



def main(argv=None):
    parser = argparse.ArgumentParser(description='初始化新档并清理旧回合恢复记录；先停止本地服务和故事桥接')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preview', action='store_true', help='仅列出范围，不写文件')
    mode.add_argument('--recover', action='store_true', help='恢复未完成的清理事务')
    parser.add_argument('--backup', action='store_true', help='成功后保留本次旧档副本')
    args = parser.parse_args(argv)
    try:
        root = project_root(DEFAULT_ROOT)
        if args.recover:
            print('恢复结果：', recover(root))
            return 0
        print('【深渊天平 · 新档初始化】\n项目：' + str(root))
        for item in plan_reset(root):
            print('  ' + item['action'] + '：' + item['path'] + ('（不存在）' if item['before'] is None else ''))
        print('保留桥接密钥、语音配置、素材、规则和历史日志。请先停止本地服务和故事桥接。')
        if args.preview:
            print('仅预览，未修改文件。')
            return 0
        print('本次' + ('保留旧档备份。' if args.backup else '成功后不保留旧档；需要留档可加 --backup。'))
        if input('确认初始化新档？输入 y 继续，其余取消 > ').strip().lower() != 'y':
            print('已取消，未清理存档。')
            return 0
        result = reset(root, args.backup)
        print('✅ 新档初始化完成。重新启动本地服务和故事桥接，再刷新网页；无需手动删除data.json。')
        if result['backup']:
            print('旧档副本：' + result['backup'])
        return 0
    except (OSError, ValueError, RuntimeError, EOFError, KeyboardInterrupt) as exc:
        print('❌ 未完成：' + str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())

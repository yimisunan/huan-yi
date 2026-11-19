"""Isolated new-save reset acceptance; run from project root, optionally --installed.
Uses standard-library Python and Node; never resets the live project.
"""
from pathlib import Path
from contextlib import redirect_stdout
import argparse
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument('--installed', action='store_true')
parser.add_argument('--symlink-only', action='store_true')
args = parser.parse_args()
root = Path.cwd().resolve()
base = root/'开发者功能/修订日志/2026.11/回合执行基础'
manifest = json.loads((base/'src/安装清单_21.json').read_text())
changes = {c['path']: c for c in manifest['changes']}
sys.path.insert(0, str(root))
import round_runtime as rr
import relationship_query as rq
import story_reading as sr


def source(path):
    return root/path if args.installed or path not in changes else root/changes[path]['staged']


work = Path(tempfile.mkdtemp(prefix='tmp_reset21_test_', dir=base/'tmp'))
results = []
symlink_observation = {}


def test(name, function):
    try:
        function()
        results.append({'name': name, 'status': 'PASS'})
    except Exception:
        results.append({'name': name, 'status': 'FAIL', 'error': traceback.format_exc()})


def expect(condition, detail='assertion failed'):
    assert condition, detail


def load_cleaner():
    spec = importlib.util.spec_from_file_location('_reset21_cleaner', source('存档清理器.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleaner_output = io.StringIO()
with redirect_stdout(cleaner_output):
    cleaner = load_cleaner()
service_tree = ast.parse(source('story_service.py').read_text())
service_nodes = [node for node in service_tree.body if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
ns = {'rr': rr, 'rq': rq, 'sr': sr, 'Path': Path}
exec('import hashlib,hmac,json,re,secrets,threading,time', ns)
exec(compile(ast.Module(body=service_nodes, type_ignores=[]), 'story_service.py', 'exec'), ns)
Service = ns['StoryService']
seed = work/'seed'
seed.mkdir()
for relative in dict.fromkeys(['injection_core.py', 'round_runtime.py', *ns['RULES']]):
    target = seed/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root/relative, target)


def fixture():
    fixture.count += 1
    project = work/('case_'+str(fixture.count))
    shutil.copytree(seed, project)
    values = {
        '存档/全局记忆库.txt': b'old-memory-fixture',
        '存档/次要NPC名册.txt': b'old-npc-fixture',
        '存档/徐志北道具图鉴.txt': b'old-item-fixture',
        'data.json': json.dumps({'round': 9, 'storyNodes': [{'type': 'narration', 'text': 'isolated old scene'}]}).encode(),
        '.round-runtime/state.json': b'{"version":1,"sequence":9,"receipts":{"old":{}}}',
        '.round-runtime/journal.json': b'old journal must never replay into new save',
        '.round-runtime/story/tasks.json': b'{"version":1,"jobs":{"old":{"status":"generating"}},"latest":"old"}',
        '.round-runtime/story/bridge-key.json': b'{"token":"isolated-not-a-real-token"}',
        '.round-runtime/story/'+'a'*64+'.context.json': b'old-context',
        '.round-runtime/story/'+'a'*64+'.result.txt': b'old-result',
        '.round-runtime/story/'+'a'*64+'.read-audit.json': b'old-audit',
        '.round-runtime/story/'+'a'*64+'.assembled.json': b'old-assembly',
        '.round-runtime/story/notes.txt': b'keep-unknown',
        '.round-runtime/keep.txt': b'keep-unknown-runtime',
        '.round-runtime/lock': b'keep-same-lock-inode',
        '.round-runtime/work-isolated/temp.txt': b'old-settlement',
        'txt文件/.story-reading/oldnonce/entry.txt': b'old-cache',
        'voice_config.json': b'isolated-voice-settings',
        '.backup/keep.txt': b'keep-engine-backup',
        '日志/keep.txt': b'keep-history',
    }
    for relative, raw in values.items():
        p=project/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    return project


fixture.count = 0
original_server_running = cleaner.server_running
cleaner.server_running = lambda: False  # Test adapter: never stop or bind the production port.


def managed(project):
    return {item['path']: cleaner.inventory(project, item['path']) for item in cleaner.plan_reset(project)}


def rejects(function, exception=Exception):
    try:
        function()
    except exception:
        return
    raise AssertionError('operation was not rejected')


def immutable(project):
    paths=['.round-runtime/story/bridge-key.json', '.round-runtime/story/notes.txt', '.round-runtime/keep.txt',
           '.round-runtime/lock', 'voice_config.json', '.backup/keep.txt', '日志/keep.txt', 'injection_core.py',
           'round_runtime.py', 'txt文件/事件注册表.json']
    return {p:(project/p).read_bytes() for p in paths}


def test_syntax():
    for path in ('存档清理器.py', 'story_service.py'):
        compile(source(path).read_bytes(), path, 'exec')
    subprocess.run(['node', '--check', str(source('story_client.js'))], check=True, capture_output=True)
    expect(cleaner_output.getvalue() == '')
    old_tree=ast.parse((root/changes['存档清理器.py']['path']).read_text() if not args.installed else (root/changes['存档清理器.py']['backup']).read_text())
    old={n.targets[0].id:ast.literal_eval(n.value) for n in old_tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id.startswith('INITIAL_')}
    expect(len(old)==3 and all(getattr(cleaner,k)==v for k,v in old.items()))


def test_complete():
    p=fixture(); keep=immutable(p);inode=(p/'.round-runtime/lock').stat().st_ino
    result=cleaner.reset(p)
    expect(result['status']=='reset' and result['backup'] is None)
    for relative,template in cleaner.TEMPLATES.items():expect((p/relative).read_text()==template)
    data=json.loads((p/'data.json').read_text());expect(data['round']==0 and data['storyNodes']==[])
    for path in ('.round-runtime/state.json','.round-runtime/journal.json','.round-runtime/story/tasks.json','txt文件/.story-reading','.round-runtime/work-isolated'):
        expect(not (p/path).exists(),path)
    expect(immutable(p)==keep)
    expect((p/'.round-runtime/lock').stat().st_ino==inode)
    expect(not (p/cleaner.TX).exists())
    expect(not list((p/cleaner.BACKUPS).iterdir()))
    expect(re.fullmatch('[0-9a-f]{32}',json.loads((p/cleaner.EPOCH).read_text())['epoch']) is not None)


def test_missing_and_repeat():
    p=fixture();(p/'data.json').unlink();cleaner.reset(p)
    first=json.loads((p/cleaner.EPOCH).read_text())['epoch'];cleaner.reset(p)
    expect(json.loads((p/cleaner.EPOCH).read_text())['epoch']!=first)
    expect(json.loads((p/'data.json').read_text())['round']==0)


def test_backup():
    p=fixture();before=managed(p);result=cleaner.reset(p,keep_backup=True)
    archive=Path(result['backup']);record=json.loads((archive/'manifest.json').read_text())
    for index,item in enumerate(record['entries']):
        if item['before'] is not None:
            expect(cleaner.inventory(p,str((archive/('slot-'+str(index))).relative_to(p)))==before[item['path']])
    expect(not (p/cleaner.TX).exists())


def test_preview_cancel():
    p=fixture();before=managed(p);old_root=cleaner.DEFAULT_ROOT
    cleaner.DEFAULT_ROOT=p
    import builtins
    original_input=builtins.input
    try:
        with redirect_stdout(io.StringIO()):
            expect(cleaner.main(['--preview'])==0)
            builtins.input=lambda _: 'n'
            expect(cleaner.main([])==0)
    finally:
        cleaner.DEFAULT_ROOT=old_root;builtins.input=original_input
    expect(managed(p)==before)
    expect(not (p/cleaner.BACKUPS).exists())


def test_service_refusal():
    p=fixture();before=managed(p);cleaner.server_running=lambda: True
    try:rejects(lambda:cleaner.reset(p),RuntimeError)
    finally:cleaner.server_running=lambda:False
    expect(managed(p)==before and not (p/cleaner.BACKUPS).exists())


def test_lock_refusal():
    p=fixture();before=managed(p)
    script="import fcntl,sys; f=open(sys.argv[1],'a+b'); fcntl.lockf(f,fcntl.LOCK_EX); print('ready',flush=True); sys.stdin.readline()"
    child=subprocess.Popen([sys.executable,'-c',script,str(p/'.round-runtime/lock')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        expect(child.stdout.readline().strip()=='ready')
        rejects(lambda:cleaner.reset(p),RuntimeError)
    finally:
        child.stdin.write('\n');child.stdin.flush();child.wait(timeout=5)
    expect(managed(p)==before)


def test_symlink():
    p=fixture();target=p/'data.json';target.unlink();outside=work/'outside';outside.write_bytes(b'keep')
    try:
        target.symlink_to(outside)
    except PermissionError:
        # Android shared storage cannot create native symlinks. Exercise the guard explicitly.
        from unittest.mock import patch
        original=Path.is_symlink
        def pretend_link(path):
            return path==target or original(path)
        with patch.object(Path,'is_symlink',pretend_link):
            rejects(lambda:cleaner.reset(p),RuntimeError)
        rejects(lambda:cleaner.safe(p,'../outside'),ValueError)
        symlink_observation.update(native_symlink_supported=False,guard_adapter_tested=True,path_escape_tested=True)
    else:
        rejects(lambda:cleaner.reset(p))
        q=fixture();nested=q/'txt文件/.story-reading/oldnonce/link';nested.symlink_to(outside)
        rejects(lambda:cleaner.reset(q))
        expect(not (q/cleaner.BACKUPS).exists())
        symlink_observation.update(native_symlink_supported=True,guard_adapter_tested=False,path_escape_tested=True)
    expect(outside.read_bytes()==b'keep' and not (p/cleaner.BACKUPS).exists())


def test_write_failure():
    p=fixture();before=managed(p);atomic=cleaner.atomic;failed=[False]
    def fail(path,raw):
        if path==p/'存档/次要NPC名册.txt' and not failed[0]:
            failed[0]=True;raise OSError('isolated single write failure')
        return atomic(path,raw)
    cleaner.atomic=fail
    try:rejects(lambda:cleaner.reset(p),OSError)
    finally:cleaner.atomic=atomic
    expect(failed[0] and managed(p)==before)
    expect(not (p/cleaner.TX).exists())


def test_crash_recovery():
    p=fixture();before=managed(p)
    script="""from pathlib import Path
import importlib.util,os,sys
spec=importlib.util.spec_from_file_location('reset_test',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.server_running=lambda:False
atomic=m.atomic
root=Path(sys.argv[2])
def crash(path,raw):
 atomic(path,raw)
 if path==root/'存档/全局记忆库.txt':os._exit(77)
m.atomic=crash
m.reset(root)
"""
    child=subprocess.run([sys.executable,'-c',script,str(source('存档清理器.py')),str(p)],capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    expect(child.returncode==77,child.stderr.decode())
    expect((p/cleaner.TX).exists())
    rejects(lambda:cleaner.reset(p),RuntimeError)
    result=cleaner.recover(p)
    expect(result['status']=='restored' and managed(p)==before)


def test_recovery_tamper():
    p=fixture();(p/cleaner.TX).write_text('{"version":1,"phase":"prepared","id":"bad","entries":[]}')
    before=(p/'存档/全局记忆库.txt').read_bytes()
    rejects(lambda:cleaner.recover(p),RuntimeError)
    expect((p/cleaner.TX).exists() and (p/'存档/全局记忆库.txt').read_bytes()==before)


def test_round1_context():
    p=fixture();cleaner.reset(p)
    store=rr.RoundStore(p);prepared=store.prepare()
    expect(prepared['current_round']==1)
    service=Service(p)
    snapshot=service.snapshot();epoch=json.loads((p/cleaner.EPOCH).read_text())['epoch']
    expect(snapshot['save_epoch']==epoch and snapshot['data']['round']==0)
    context=service._context(prepared,'isolated-new-game','开始序章')
    expect(context['reading_policy']['version']==sr.VERSION)
    expect((p/'data.json').is_file())
    expect(service.status()['save_epoch']==epoch and service.status()['task'] is None)


def test_guard_and_legacy():
    p=fixture();service=Service(p);expect(service._save_epoch()=='legacy')
    (p/cleaner.TX).write_text('{}')
    before=(p/'.round-runtime/journal.json').read_bytes()
    rejects(service.start,rr.RecoveryError)
    expect((p/'.round-runtime/journal.json').read_bytes()==before)
    (p/cleaner.TX).unlink();(p/cleaner.EPOCH).write_text('[]')
    rejects(service._save_epoch,rr.RecoveryError)


try:
    for name,function in [
        ('syntax_import_and_templates',test_syntax),('complete_reset_preserves_settings_and_lock',test_complete),
        ('missing_snapshot_and_repeat',test_missing_and_repeat),('optional_backup_verified',test_backup),
        ('preview_and_cancel_are_readonly',test_preview_cancel),('running_service_refused',test_service_refusal),
        ('other_process_lock_refused',test_lock_refusal),('symlinks_refused',test_symlink),
        ('write_failure_restores_old_save',test_write_failure),('hard_exit_then_recover',test_crash_recovery),
        ('invalid_recovery_record_refused',test_recovery_tamper),('real_roundstore_round1_and_context',test_round1_context),
        ('service_guard_and_legacy_epoch',test_guard_and_legacy)]:
        if not args.symlink_only or name=='symlinks_refused':test(name,function)
    for script,prefix in [('新档清理前端验收_21.js','epoch.'),('任务响应前端验收_20.js','response20.')] if not args.symlink_only else []:
        run=subprocess.run(['node',str(base/'src'/script),str(source('story_client.js'))],capture_output=True,text=True)
        try:
            data=json.loads(run.stdout)
            results.extend({'name':prefix+c['name'],**{k:v for k,v in c.items() if k!='name'}} for c in data['cases'])
        except Exception:
            results.append({'name':prefix+'runner','status':'FAIL','error':run.stderr or run.stdout})
finally:
    cleaner.server_running=original_server_running
    shutil.rmtree(work)

initial=None
if args.symlink_only:
    initial=json.loads((base/'src/新档清理验收结果_21.json').read_text())
    corrected={r['name']:r for r in results}
    results=[corrected.get(r['name'],r) for r in initial['cases']]
output={'stage':'new_save_reset_21','cases':results,'passed':sum(r['status']=='PASS' for r in results),
        'failed':sum(r['status']!='PASS' for r in results),'installed':args.installed,
        'real_roundstore':True,'real_story_service_class':True,'flask_routes_executed':False,
        'actual_isolated_reset_and_recovery':True,'real_frontend_script':True,'real_browser':False,
        'production_reset_executed':False,'model_called':False,'tts_called':False,
        'symlink_observation':symlink_observation}
if initial:
    output['initial_acceptance']=initial
    output['targeted_retry']={'cases':list(corrected.values()),'scope':'symlinks_refused_only','live_code_changed':False}
(base/'src/新档清理验收结果_21.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('RESET21_ISOLATION_'+('PASS' if output['failed']==0 else 'FAIL')+' cases='+str(len(results))+' passed='+str(output['passed'])+' failed='+str(output['failed'])+' live_reset=false')
if output['failed']:
    print(json.dumps([r for r in results if r['status']!='PASS'],ensure_ascii=False))
    raise SystemExit(1)
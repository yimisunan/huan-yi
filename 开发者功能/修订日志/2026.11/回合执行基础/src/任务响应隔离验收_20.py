"""Run from project root: python3 this_file --deps <Flask dir> [--installed].
Only disposable tmp projects are served by the real Flask test client.
Node runs the real story client against an isolated DOM/HTTP adapter.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import traceback

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument('--deps')
parser.add_argument('--installed', action='store_true')
args = parser.parse_args()
root = Path.cwd().resolve()
base = root/'开发者功能/修订日志/2026.11/回合执行基础'
sys.path.insert(0, str(root))
if args.deps:
    sys.path.insert(0, str(Path(args.deps).resolve()))
manifest = json.loads((base/'src/安装清单_20.json').read_text())
changes = {c['path']: c for c in manifest['changes']}
results = []


def source(path):
    return root/path if args.installed or path not in changes else root/changes[path]['staged']


def check(name, function):
    try:
        function()
        results.append({'name': name, 'status': 'PASS'})
    except Exception:
        results.append({'name': name, 'status': 'FAIL', 'error': traceback.format_exc()})


def expect(condition, detail='assertion failed'):
    assert condition, detail


compile(source('story_service.py').read_bytes(), 'story_service.py', 'exec')
subprocess.run(['node', '--check', str(source('story_client.js'))], check=True, capture_output=True, text=True)
results.append({'name': 'python_and_javascript_syntax', 'status': 'PASS'})
from flask import Flask, abort
import round_runtime as rr
spec = importlib.util.spec_from_file_location('_response20_service', source('story_service.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
work = Path(tempfile.mkdtemp(prefix='tmp_response20_test_', dir=base/'tmp'))
try:
    (work/'injection_core.py').write_bytes((root/'injection_core.py').read_bytes())
    app = Flask('_response20_isolated', static_folder=None)
    app.testing = True
    app.logger.disabled = True
    service = module.register_story_routes(app, work)
    state = {'version': 1, 'latest': 'known', 'bridge_seen': 0, 'jobs': {
        'known': {'request_id': 'known', 'status': 'failed', 'action': '隔离测试行动', 'attempt': 1, 'error': '隔离测试'}}}
    (work/'.round-runtime/story').mkdir(parents=True)
    (work/'.round-runtime/story/tasks.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    @app.get('/api/story/isolation-http-error')
    def http_error():
        abort(500)
    @app.get('/api/story/isolation-conflict')
    def conflict():
        raise rr.ConflictError('隔离版本冲突')
    @app.get('/api/story/isolation-round-error')
    def round_error():
        raise rr.RoundError('隔离契约错误')
    @app.get('/api/story/isolation-exception')
    def exception():
        raise RuntimeError('isolated exception detail must not leak')
    @app.get('/outside/denied')
    def denied():
        abort(403)
    client = app.test_client()

    def story_error(response, code):
        expect(response.status_code == code, response.status_code)
        expect(response.mimetype == 'application/json', response.content_type)
        data = response.get_json()
        expect(isinstance(data.get('error'), str) and bool(data['error']))
        expect(data.get('status') == code)
        expect(response.headers.get('Cache-Control') == 'no-store')
        expect(b'<!doctype' not in response.data)
        return data

    check('missing_task_get_json404', lambda: story_error(client.get('/api/story/tasks/missing'), 404))
    check('missing_task_retry_json404', lambda: story_error(client.post('/api/story/tasks/missing/retry', json={}, headers={'X-Story-Client': '1'}), 404))
    check('unknown_story_route_json404', lambda: story_error(client.get('/api/story/missing'), 404))
    def method():
        response = client.put('/api/story/tasks', json={}, headers={'X-Story-Client': '1'})
        story_error(response, 405)
        expect('GET' in response.headers['Allow'] and 'POST' in response.headers['Allow'])
    check('json405_retains_allow_header', method)
    check('client_header_guard_json403', lambda: story_error(client.post('/api/story/tasks', json={}), 403))
    check('non_json_body_guard_json415', lambda: story_error(client.post('/api/story/tasks', data='x', headers={'X-Story-Client': '1'}), 415))
    check('worker_auth_guard_json403', lambda: story_error(client.post('/api/story/worker/claim', json={}), 403))
    check('cross_origin_guard_json403', lambda: story_error(client.get('/api/story/tasks', headers={'Origin': 'https://invalid.example'}), 403))
    check('explicit_http500_is_json', lambda: story_error(client.get('/api/story/isolation-http-error'), 500))
    def real_exception():
        app.config['PROPAGATE_EXCEPTIONS'] = False
        data = story_error(client.get('/api/story/isolation-exception'), 500)
        expect('isolated exception detail' not in data['error'])
    check('unhandled_exception_json500_no_details', real_exception)
    def existing_error(path, code, message):
        response = client.get(path)
        expect(response.status_code == code)
        expect(response.get_json() == {'error': message})
        expect(response.headers.get('Cache-Control') == 'no-store')
    check('round_error_keeps_json400', lambda: existing_error('/api/story/isolation-round-error', 400, '隔离契约错误'))
    check('conflict_keeps_json409', lambda: existing_error('/api/story/isolation-conflict', 409, '隔离版本冲突'))
    def outside(path, code):
        response = client.get(path)
        expect(response.status_code == code and response.mimetype == 'text/html')
        expect(response.headers.get('Cache-Control') != 'no-store')
    check('outside404_keeps_html', lambda: outside('/outside/missing', 404))
    check('outside403_keeps_html', lambda: outside('/outside/denied', 403))
    def existing_task():
        response = client.get('/api/story/tasks/known')
        expect(response.status_code == 200)
        expect(response.get_json()['task'] == state['jobs']['known'])
        expect(response.headers.get('Cache-Control') == 'no-store')
    check('existing_task_json_unchanged', existing_task)
    def list_task():
        response = client.get('/api/story/tasks')
        expect(response.status_code == 200)
        expect(response.get_json()['task']['request_id'] == 'known')
    check('task_list_remains_usable', list_task)
    def no_job_mutation():
        expect(json.loads((work/'.round-runtime/story/tasks.json').read_text()) == state)
    check('error_requests_do_not_mutate_jobs', no_job_mutation)
    node = subprocess.run(['node', str(base/'src/任务响应前端验收_20.js'), str(source('story_client.js'))], capture_output=True, text=True)
    try:
        frontend = json.loads(node.stdout)
        results.extend({'name': 'frontend.' + case['name'], **{k:v for k,v in case.items() if k != 'name'}} for case in frontend['cases'])
    except Exception:
        results.append({'name': 'frontend.runner', 'status': 'FAIL', 'error': node.stderr or node.stdout})
    if node.returncode and not any(r['status'] == 'FAIL' and r['name'].startswith('frontend.') for r in results):
        results.append({'name': 'frontend.exit_code', 'status': 'FAIL', 'error': str(node.returncode)})
finally:
    shutil.rmtree(work)

output = {'stage': 'task_response_20', 'cases': results, 'passed': sum(r['status'] == 'PASS' for r in results),
          'failed': sum(r['status'] != 'PASS' for r in results), 'installed': args.installed,
          'real_flask_test_client': True, 'real_story_service': True, 'real_frontend_script': True,
          'dom_adapter': True, 'real_browser': False, 'live_http_mutations': False,
          'live_story_submissions': False, 'real_model_called': False, 'tts_called': False,
          'system_dependencies_installed': False}
(base/'src/任务响应验收结果_20.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('RESPONSE20_ISOLATION_' + ('PASS' if output['failed'] == 0 else 'FAIL') + ' cases=' + str(len(results)) + ' passed=' + str(output['passed']) + ' failed=' + str(output['failed']) + ' real_flask=true real_frontend=true live_submissions=false')
if output['failed']:
    print(json.dumps([r for r in results if r['status'] != 'PASS'], ensure_ascii=False))
    raise SystemExit(1)
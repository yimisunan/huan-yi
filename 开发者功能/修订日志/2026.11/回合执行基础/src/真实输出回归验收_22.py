"""Focused bridge regression using a frozen real failure and disposable projects.
Run from project root: python3 this_file [--installed]. No model or live save writes.
Flask routes are unchanged; the existing AST loader executes the original service class.
"""
from pathlib import Path
import ast
import copy
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import traceback
import types

sys.dont_write_bytecode = True
ROOT = Path.cwd().resolve()
BASE = ROOT / '开发者功能/修订日志/2026.11/回合执行基础'
manifest = json.loads((BASE / 'src/安装清单_22.json').read_bytes())
changes = {c['path']: c for c in manifest['changes']}
installed = '--installed' in sys.argv
frozen = json.loads((BASE / 'src/真实失败样本_22.json').read_bytes())
sha = lambda raw: hashlib.sha256(raw).hexdigest()
results, details = [], {}
work = Path(tempfile.mkdtemp(prefix='tmp_compat22_tests_', dir=BASE / 'tmp'))


def source(rel, old=False):
    c = changes.get(rel)
    if not c:
        return (ROOT / rel).read_bytes()
    if old:
        return (ROOT / (c['backup'] if installed else rel)).read_bytes()
    return (ROOT / (rel if installed else c['staged'])).read_bytes()


def module(name, rel, old=False):
    m = types.ModuleType(name)
    m.__file__ = str(ROOT / rel)
    sys.modules[name] = m
    exec(compile(source(rel, old), m.__file__, 'exec'), m.__dict__)
    return m


rr = module('round_runtime', 'round_runtime.py')
rq = module('relationship_query', 'relationship_query.py')
sr = module('story_reading', 'story_reading.py')
oldrr = module('_compat22_previous_runtime', 'round_runtime.py', old=True)
service_tree = ast.parse(source('story_service.py'))
service_tree.body = [n for n in service_tree.body if isinstance(n, (ast.Assign, ast.ClassDef))]
env = dict(rr=rr, rq=rq, sr=sr, Path=Path, json=json, re=re, hashlib=hashlib,
           threading=threading, time=time, secrets=secrets, hmac=hmac)
exec(compile(service_tree, 'story_service.py', 'exec'), env)
Service = env['StoryService']
seed = work / 'seed'
seed.mkdir()
for rel in set(env['RULES']) | set(rr.FILES) | {'injection_core.py'}:
    dest = seed / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source(rel))
for rel, text in frozen['facts'].items():
    (seed / rel).write_text(text, encoding='utf-8')
ctx = frozen['context']
for key, spec in sr.specifications(seed).items():
    entry = ctx['reading_bundle']['entries'][key]
    raw = sr._document(spec, ctx['reading_bundle']['task_id'], ctx['reading_bundle']['nonce'])
    assert sha(raw) == entry['sha256'], key
    dest = seed / entry['path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
svc = Service(seed)
facts = svc._bridge_facts(ctx, frozen['audit'])
identity = {'schema_version': 1, **{k: frozen['job'][k] for k in ('request_id', 'base_revision', 'current_round')}}
raw_result = rr.load_request(frozen['result_text'])
canonical = copy.deepcopy(raw_result)
misplaced = ('shame_events', 'depravity_events', 'ds_events', 'affection_events',
             'host_events', 'vigilance_events', 'item_entries', 'task_issue')
for field in misplaced:
    canonical[field] = canonical['memory_deltas'].pop(field)
engine = rr._engine(seed, seed)


def require(value, reason='assertion failed'):
    if not value:
        raise AssertionError(reason)


def rejects(fn, fragment):
    try:
        fn()
    except (ValueError, OSError) as exc:
        require(fragment in str(exc), str(exc))
        return str(exc)
    raise AssertionError('Expected rejection: ' + fragment)


def case(name, fn):
    if '--failed-only' in sys.argv and name not in {'new_task_claim_actual_read_audit_result_and_commit', 'live_save_runtime_and_31_protected_sources_unchanged'}:
        previous = json.loads((BASE / 'src/真实输出回归首轮_22.json').read_bytes())
        record = next(r for r in previous['cases'] if r['name'] == name)
        require(record['status'] == 'PASS', name)
        results.append(dict(record, reused_from='真实输出回归首轮_22.json'))
        return
    try:
        fn()
        results.append({'name': name, 'status': 'PASS'})
    except Exception as exc:
        results.append({'name': name, 'status': 'FAIL', 'error': str(exc), 'traceback': traceback.format_exc()})
    print(results[-1]['status'], name, flush=True)


def assemble(value, reading_facts=facts):
    return rr._assemble_bridge_result(seed, value, identity, reading_facts)


def project(name):
    dest = work / name
    shutil.copytree(seed, dest)
    return dest, Service(dest)


def reading_proof(service, context):
    tools = []
    def read(rel, begin=1, end=None):
        lines = (service.root / rel).read_text(encoding='utf-8').splitlines()
        end = len(lines) if end is None else end
        text = '\n'.join(str(i) + '| ' + lines[i-1] for i in range(begin, end+1))
        tools.append({'name': 'read_file_part', 'parameters': {'path': rel, 'start_line': begin, 'end_line': end},
                      'status': 'success', 'part_id': 'synthetic-' + str(len(tools)), 'result_text': text})
    for entry in context['reading_policy']['required_reads']:
        read(entry['path'])
    for rel in context['reading_policy']['required_browse']:
        tools.append({'name': 'list_files', 'parameters': {'path': rel}, 'status': 'success',
                      'part_id': 'synthetic-' + str(len(tools)), 'result_text': 'synthetic directory receipt'})
    selected = set(canonical['model_audit']['required_keys']) | set(context['reading_policy']['required_keys'])
    for key in sorted(selected):
        entry = context['reading_bundle']['entries'].get(key)
        if entry:
            read(entry['path'])
    for record in frozen['audit']['verified_tools']:
        if record['path'] == rq.VIEW and record.get('verified_lines'):
            for line in record['verified_lines']:
                read(rq.VIEW, line, line)
    return {'api': 'Tools.Chat.sendMessageStreaming', 'chat_id': 'synthetic-isolated-22',
            'participant_id': 'synthetic-reader', 'workspace': str(service.root),
            'outcome': {'type': 'committed', 'status': 'completed', 'assistant': {'messageTimestamp': 22}},
            'snapshot_message_timestamp': 22, 'tools': tools}


def structure():
    for rel in ('round_runtime.py', 'story_service.py'):
        compile(source(rel), rel, 'exec')
    # Routes and the public submission implementation must be byte-for-byte identical ASTs.
    before = ast.parse(source('story_service.py', old=True))
    after = ast.parse(source('story_service.py'))
    select = lambda tree, name: next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    require(ast.dump(select(before, 'register_story_routes')) == ast.dump(select(after, 'register_story_routes')))
    oldtree, newtree = ast.parse(source('round_runtime.py', old=True)), ast.parse(source('round_runtime.py'))
    oldclass = next(n for n in oldtree.body if isinstance(n, ast.ClassDef) and n.name == 'RoundStore')
    newclass = next(n for n in newtree.body if isinstance(n, ast.ClassDef) and n.name == 'RoundStore')
    require(ast.dump(oldclass) == ast.dump(newclass))
case('python_syntax_routes_and_public_submit_unchanged', structure)


def real_replay():
    before = copy.deepcopy(raw_result)
    error = rejects(lambda: oldrr._assemble_bridge_result(seed, raw_result, identity, facts), 'memory_deltas: 未知键=')
    body = assemble(raw_result)
    require(raw_result == before, 'caller input mutated')
    for field in misplaced:
        require(field not in body['memory_deltas'] and body[field] == before['memory_deltas'][field])
    require('【字段归位】' in body['system_log'])
    for key in ('story_nodes', 'options_text'):
        require(body[key] == raw_result[key], key)
    rr._validate(seed, body, svc.store._files(), False)
    details['real_failure'] = {'old_error': error, 'replayed_result_sha256': sha(frozen['result_text'].encode()),
                               'relocated_fields': list(misplaced), 'nodes_preserved': len(body['story_nodes'])}
case('exact_real_failure_replay_and_complete_validation', real_replay)


def previous_missing_reads():
    missing = copy.deepcopy(facts)
    missing['available_keys'] = {k: v for k, v in facts['available_keys'].items()
                                 if not k.startswith(('lore.称谓', 'lore.知情'))}
    message = rejects(lambda: assemble(raw_result, missing), '必需key未完整读取: lore.知情, lore.称谓')
    details['previous_failure'] = {'stored_error': json.loads(ctx['turns'][1]['content'])['previous_validation_error'],
                                   'reconstructed_missing_read_rejection': message,
                                   'original_attempt1_audit_available': False}
case('previous_missing_relationship_reads_still_rejected', previous_missing_reads)


def canonical_result():
    body = assemble(canonical)
    require('【字段归位】' not in body['system_log'])
    require(body['memory_deltas'] == canonical['memory_deltas'])
    rr._validate(seed, body, svc.store._files(), False)
case('canonical_top_level_format_still_valid', canonical_result)


def nonempty_fields():
    registry = engine._load_event_registry()['groups']
    values = {}
    for field, rows in registry.items():
        tag = next(row['tag'] for row in rows if not row['tag'].startswith('C烈度_') and 'X' not in row['tag'])
        target = sorted(engine.VIGILANCE_TARGETS)[0] if field == 'vigilance_events' else '沈知韫'
        values[field] = [tag] if field == 'host_events' else {target: [tag]}
    target = next(iter(engine.TASK_WHITELIST))
    attr = next(iter(engine.TASK_WHITELIST[target]))
    values.update(npc_entries=[{'name': '隔离验收助手', 'identity': '资料核验人员'}],
                  item_entries=[{'name': '隔离便签', 'quantity': 1, 'desc': '仅供隔离验证'}],
                  task_issue={'title': '隔离核验', 'target': target, 'attr': attr, 'value': 1,
                              'tier': next(iter(engine.TASK_REWARDS)), 'item_desc': '隔离测试奖励'},
                  micro_state_changes={'沈知韫': {'momentary_ease': True}}, counter_updates={'验收计数': 1})
    for field, value in values.items():
        sample = copy.deepcopy(canonical)
        sample.pop(field, None)
        sample['memory_deltas'][field] = value
        body = assemble(sample)
        require(body[field] == value and field not in body['memory_deltas'], field)
        rr._validate(seed, body, svc.store._files(), False)
    details['nonempty_fields_validated'] = sorted(values)
case('nonempty_events_npc_items_tasks_states_and_counters_relocate', nonempty_fields)


def duplicate_same():
    sample = copy.deepcopy(canonical)
    tags = ['日常_温和累进']
    sample['host_events'] = tags
    sample['memory_deltas']['host_events'] = list(tags)
    require(assemble(sample)['host_events'] == tags)
case('identical_duplicate_values_apply_once', duplicate_same)


def default_top():
    sample = copy.deepcopy(canonical)
    sample['memory_deltas']['host_events'] = ['日常_温和累进']
    require(assemble(sample)['host_events'] == ['日常_温和累进'])
case('empty_top_level_preserves_nonempty_nested_events', default_top)


def default_nested():
    sample = copy.deepcopy(canonical)
    sample['host_events'] = ['日常_温和累进']
    sample['memory_deltas']['host_events'] = []
    require(assemble(sample)['host_events'] == ['日常_温和累进'])
case('empty_nested_preserves_nonempty_top_level_events', default_nested)


def conflicting():
    sample = copy.deepcopy(canonical)
    sample['host_events'] = ['日常_温和累进']
    sample['memory_deltas']['host_events'] = ['意外_小收获']
    before = copy.deepcopy(sample)
    rejects(lambda: assemble(sample), '桥接字段位置冲突')
    require(sample == before)
case('conflicting_nonempty_values_rejected_without_merging', conflicting)


def bad_field():
    sample = copy.deepcopy(canonical)
    sample['memory_deltas']['eventz'] = {}
    rejects(lambda: assemble(sample), "未知键=['eventz']")
case('unknown_nested_key_rejected', bad_field)


def server_injection():
    for key in ('system_log', 'request_id', 'options_text', 'panel_changes'):
        sample = copy.deepcopy(canonical)
        sample['memory_deltas'][key] = 'forged'
        rejects(lambda: assemble(sample), '未知键=')
case('server_fields_and_required_text_cannot_be_relocated', server_injection)


def bad_tags():
    sample = copy.deepcopy(canonical)
    sample.pop('host_events')
    sample['memory_deltas']['host_events'] = ['不存在的事件']
    rejects(lambda: assemble(sample), '含未知标签')
    sample['memory_deltas']['host_events'] = ['日常_温和累进', '日常_温和累进']
    rejects(lambda: assemble(sample), '含重复标签')
case('relocated_unknown_and_duplicate_tags_rejected', bad_tags)


def bad_type():
    sample = copy.deepcopy(canonical)
    sample.pop('host_events')
    sample['memory_deltas']['host_events'] = {}
    rejects(lambda: assemble(sample), '标签必须是文本数组')
    sample['memory_deltas'].pop('host_events')
    sample.pop('item_entries')
    sample['memory_deltas']['item_entries'] = {}
    body = assemble(sample)
    rejects(lambda: rr._validate(seed, body, svc.store._files(), False), 'item_entries必须是数组')
case('relocated_wrong_types_keep_existing_validation', bad_type)


def strict_public():
    body = assemble(canonical)
    body['memory_deltas']['host_events'] = []
    rejects(lambda: rr._validate(seed, body, svc.store._files(), False), 'memory_deltas: 未知键=')
case('public_complete_json_remains_strict', strict_public)


def semantic_gate():
    sample = copy.deepcopy(canonical)
    sample['model_audit']['v1']['V1-A']['status'] = '未通过'
    rejects(lambda: assemble(sample), '未明确通过')
    sample = copy.deepcopy(canonical)
    sample['model_audit']['evidence']['state.memory'] = '已读取'
    rejects(lambda: assemble(sample), '须为单行具体依据')
case('v1_and_concrete_evidence_still_required', semantic_gate)


def context_directory():
    global new_context
    prepared = svc.store.prepare()
    new_context = svc._context(prepared, 'synthetic-22', frozen['job']['action'])
    envelope = json.loads(new_context['turns'][1]['content'])
    contract = envelope['output_contract']
    require(contract['optional_top_fields']['host_events']['type'] == 'array')
    require(contract['optional_top_fields']['shame_events']['type'] == 'object')
    require(contract['optional_top_fields']['task_issue']['type'] == 'null_or_object')
    require(set(contract['memory_delta_keys']) == rr.MEMORY_DELTA_FIELDS)
    require('顶层同级' in contract['field_layout'] and 'optional_defaults' not in contract)
    queries = envelope['reading_policy']['relationship_queries']
    rows = rq.RelationshipRegistry(seed).verify_view()
    require(queries['key_lines'] == {row['key']: line for line, row in enumerate(rows[1:], 2)})
    require('不算已读' in queries['coverage'])
    require('lore.称谓' not in queries['key_lines'])
    require(queries['key_lines']['lore.称谓.沈知韫.徐志北'] == 5)
    details['relationship_directory_rows'] = len(queries['key_lines'])
case('new_field_shapes_and_41_precise_relationship_rows', context_directory)


def no_metadata_reads():
    record = {'path': rq.VIEW, 'name': 'read_file_part', 'status': 'success', 'verified_lines': [1]}
    require(svc._relationship_facts([record]) == {})
    record = dict(record, verified_lines=[], start_line=1, end_line=42)
    require(svc._relationship_facts([record]) == {})
    no_reads = copy.deepcopy(facts)
    no_reads['available_keys'] = {k: v for k, v in facts['available_keys'].items() if not k.startswith('lore.称谓')}
    no_reads['relationship_queries'] = new_context['reading_policy']['relationship_queries']
    rejects(lambda: assemble(canonical, no_reads), '必需key未完整读取: lore.称谓')
case('directory_header_and_requested_ranges_never_count_as_body', no_metadata_reads)


def per_direction():
    records = [{'path': rq.VIEW, 'name': 'read_file_part', 'status': 'success', 'verified_lines': [1, 5, 38]}]
    related = svc._relationship_facts(records)
    require('lore.称谓.沈知韫.徐志北' in related and 'lore.知情.沈知韫' in related)
    require('lore.称谓.徐志北.沈知韫' not in related and 'lore.知情.徐志北' not in related)
    require(related['lore.称谓']['covered_lines'] == [1, 5])
    require(related['lore.知情']['covered_lines'] == [1, 38])
case('direction_and_knowledge_coverage_remains_person_specific', per_direction)


def no_header():
    rejects(lambda: svc._relationship_facts([{'path': rq.VIEW, 'name': 'read_file_part',
        'status': 'success', 'verified_lines': [5]}]), '缺少第1行元数据读取')
case('relationship_rows_without_metadata_rejected', no_header)


def forged_text():
    raw = (seed / rq.VIEW).read_bytes()
    rejects(lambda: sr.verified_lines(raw, '5| forged relationship', 5, 5), '正文或行号与当前文件不符')
case('forged_relationship_receipt_text_rejected', forged_text)


def frozen_full_commit():
    dest, service = project('exact-frozen-task')
    key = frozen['request_id']
    job = dict(frozen['job'], status='validating')
    service._write({'version': 1, 'latest': key, 'jobs': {key: job}, 'bridge_seen': 0})
    rr._atomic(service._blob(key, '.context.json'), rr._json(ctx))
    rr._atomic(service._blob(key, '.read-audit.json'), rr._json(frozen['audit']))
    rr._atomic(service._blob(key, '.result.txt'), frozen['result_text'].encode('utf-8'))
    result = service._finish(key)['task']
    require(result['status'] == 'committed', result.get('error'))
    receipt = result['receipt']
    require(receipt['round'] == 1 and receipt['state_version'] == 1)
    assembled = rr.load_request(service._blob(key, '.assembled.json').read_text())['payload']
    require(assembled['story_nodes'] == raw_result['story_nodes'])
    require(service._blob(key, '.result.txt').read_text() == frozen['result_text'])
    replay = service.store.submit(assembled)
    require(replay['replayed'] and service.store._ledger()['sequence'] == 1)
    require(service._finish(key)['task']['status'] == 'committed')
    require(json.loads((dest / 'data.json').read_bytes())['round'] == 1)
    require(len(list((dest / '日志').glob('Round_*.txt'))) == 1)
    details['frozen_isolated_commit'] = {'round': 1, 'state_version': 1, 'replayed': True, 'live': False}
case('exact_saved_task_finish_commit_and_idempotent_replay', frozen_full_commit)


def new_service_flow():
    dest, service = project('new-service-flow')
    prepared = service.store.prepare()
    key = 'page-isolated-compat22'
    service.create({'request_id': key, 'base_revision': prepared['base_revision'], 'action': frozen['job']['action']})
    task = service.claim()['task']
    require(task['request_id'] == key)
    context = json.loads(service._blob(key, '.context.json').read_bytes())
    proof = reading_proof(service, context)
    response = service.result(key, {'lease': task['lease'], 'text': frozen['result_text'], 'conversation_audit': proof})['task']
    require(response['status'] == 'committed', response.get('error'))
    require(service.store._ledger()['sequence'] == 1)
    audit = json.loads(service._blob(key, '.read-audit.json').read_bytes())
    require(audit['required_reads_verified'])
    details['new_isolated_service_flow'] = {'round': response['receipt']['round'], 'tool_count': audit['tool_count'],
                                           'real_model': False, 'flask_routes': False}
case('new_task_claim_actual_read_audit_result_and_commit', new_service_flow)


def live_guard():
    for rel, value in manifest['dynamic_before'].items():
        if rel == '.round-runtime/story/tasks.json':
            continue
        p = ROOT / rel
        require((sha(p.read_bytes()) if p.exists() else None) == (value['sha256'] if value else None), rel)
    state = json.loads((ROOT / '.round-runtime/story/tasks.json').read_bytes())
    require(state['latest'] == frozen['request_id'] and set(state['jobs']) == {frozen['request_id']})
    current = state['jobs'][frozen['request_id']]
    require(all(current.get(k) == v for k, v in frozen['job'].items()), 'live job changed')
    details['external_runtime_change'] = {'tasks_sha256_changed': True, 'job_fields_unchanged': True,
                                           'bridge_seen': state.get('bridge_seen')}
    for rel, value in manifest['protected'].items():
        require(sha((ROOT / rel).read_bytes()) == value['sha256'], rel)
case('live_save_runtime_and_31_protected_sources_unchanged', live_guard)

if '--failed-only' in sys.argv:
    reused_details = json.loads((BASE / 'src/真实输出回归首轮_22.json').read_bytes())['details']
    reused_details.update(details)
    details = reused_details
output = {'passed': sum(r['status'] == 'PASS' for r in results), 'failed': sum(r['status'] == 'FAIL' for r in results),
          'cases': results, 'details': details, 'reused_passes': sum('reused_from' in r for r in results), 'live_submissions': False, 'models_called': 0,
          'real_roundstore': True, 'real_story_service_class': True, 'flask_routes_executed': False,
          'fixture_sha256': sha((BASE / 'src/真实失败样本_22.json').read_bytes()),
          'tested_sources': {rel: sha(source(rel)) for rel in changes}}
(BASE / 'src/真实输出回归结果_22.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if output['failed'] == 0:
    shutil.rmtree(work)
else:
    output['failure_workdir'] = str(work.relative_to(ROOT))
    (BASE / 'src/真实输出回归结果_22.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('COMPAT22_REGRESSION_' + ('PASS' if output['failed'] == 0 else 'FAIL') + ' cases=' + str(len(results))
      + ' passed=' + str(output['passed']) + ' failed=' + str(output['failed']) + ' live_submissions=false models=0')
raise SystemExit(0 if output['failed'] == 0 else 1)

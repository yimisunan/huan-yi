"""Exercise the story HTTP API against disposable synthetic projects only."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from flask import Flask

sys.dont_write_bytecode = True
PROJECT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').is_file())
SOURCE = Path(os.environ.get('STORY_TEST_SOURCE', PROJECT)).resolve()
sys.path.insert(0, str(SOURCE))
import story_service as ss
import round_runtime as rr

spec = importlib.util.spec_from_file_location('round_fixtures', PROJECT / '开发者功能/开发者工具/回合执行验收.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
TMP = PROJECT / '开发者功能/修订日志/2026.11/回合执行基础/tmp'
TMP.mkdir(parents=True, exist_ok=True)


class StoryChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='story-test-', dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('save_store.py', 'injection_core.py', 'round_runtime.py', *ss.RULES):
            source = (SOURCE / name) if (SOURCE / name).is_file() else PROJECT / name
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (self.root / '存档').mkdir()
        (self.root / rr.FILES[0]).write_text(fixture.memory(), encoding='utf-8')
        (self.root / rr.FILES[1]).write_text('▼ 活跃道具区 ▼\n\n（空）\n\n▼ 已过期/已消耗道具历史区 ▼\n\n（当前为空）\n', encoding='utf-8')
        (self.root / 'data.json').write_text('{"round":0,"storyNodes":[]}', encoding='utf-8')
        self.app = Flask(__name__)
        self.app.testing = True
        self.service = ss.register_story_routes(self.app, self.root)
        self.client = self.app.test_client()
        self.token = self.client.get('/api/story/bridge-info').json['token']
        self.revision = self.client.get('/api/story/snapshot').json['revision']

    def page(self, path, body):
        return self.client.post('/api/story/' + path, json=body, headers={'X-Story-Client': '1'})

    def worker(self, path, body):
        return self.client.post('/api/story/worker/' + path, json=body, headers={'X-Story-Bridge': self.token})

    def create(self, key='page-test'):
        return self.page('tasks', {'request_id': key, 'base_revision': self.revision, 'action': '把杯子放在桌上。'})

    def claim(self):
        return self.worker('claim', {}).json['task']

    def payload(self, key='page-test'):
        # Reuse the independent phase-one fixture, not a copy of service behavior.
        holder = object.__new__(fixture.RoundTests)
        holder.store = self.service.store
        return fixture.RoundTests.request(holder, key)

    def complete(self, claim, payload=None):
        return self.worker(claim['request_id'] + '/result', {'lease': claim['lease'],
            'text': json.dumps(payload or self.payload(claim['request_id']), ensure_ascii=False),
            'conversation_audit': self.audit(claim)})

    def audit(self, claim):
        context = json.loads(self.service._blob(claim['request_id'], '.context.json').read_bytes())
        tools = [{'name': 'read_file', 'parameters': {'path': item['path']}, 'part_id': 'part-' + str(i),
                  'status': 'success', 'result_text': (self.root / item['path']).read_text()}
                 for i, item in enumerate(context['reading_policy']['required_reads'])]
        tools += [{'name': 'list_files', 'parameters': {'path': name}, 'part_id': 'list-' + str(i),
                   'status': 'success', 'result_text': 'isolated tool event fixture'}
                  for i, name in enumerate(ss.REQUIRED_BROWSE)]
        return {'api': 'Tools.Chat.sendMessageStreaming', 'chat_id': 'test-chat', 'participant_id': 'test-role',
                'workspace': str(self.root), 'outcome': {'type': 'committed', 'status': 'completed',
                  'assistant': {'messageTimestamp': 123, 'variantIndex': 0}},
                'snapshot_message_timestamp': 123, 'tools': tools}

    def files(self):
        return {name: (self.root / name).read_bytes() if (self.root / name).is_file() else None for name in rr.FILES}

    def model(self, name='model-a'):
        return {'key': json.dumps(['CHAT', 'provider', name], separators=(',', ':')),
                'function_type': 'CHAT', 'provider_id': 'provider', 'provider_name': 'Test',
                'model_id': name, 'pricing_configured': False, 'apiKey': 'never-public'}

    def test_model_disclosure_and_change_requires_explicit_retry(self):
        model = self.model()
        self.assertIsNone(self.worker('claim', {'model': model}).json['task'])
        public = self.client.get('/api/story/tasks').json
        self.assertEqual(3, public['story_protocol'])
        self.assertNotIn('apiKey', public['bridge_model'])
        body = {'request_id': 'priced', 'base_revision': self.revision,
                'action': '把杯子放下。', 'model_key': model['key']}
        self.assertEqual(200, self.page('tasks', body).status_code)
        other = self.model('model-b')
        claim = self.worker('claim', {'model': other}).json['task']
        self.assertEqual('priced', claim['request_id'])
        self.assertEqual('model-b', self.service.status()['bridge_model']['model_id'])
        self.assertEqual(200, self.page('tasks', body).status_code)
        self.assertEqual(409, self.page('tasks', {**body, 'model_key': other['key']}).status_code)

    def test_settlement_uses_exact_action_baseline_and_survives_restart(self):
        self.create()
        claim = self.claim()
        before = (self.root / rr.FILES[0]).read_text()
        with contextlib.redirect_stdout(io.StringIO()):
            result = self.complete(claim)
        self.assertEqual('committed', result.json['task']['status'])
        snapshot = self.client.get('/api/story/snapshot').json
        baseline = snapshot['settlement']['before_memory']
        self.assertEqual(snapshot['revision'], snapshot['settlement']['revision'])
        self.assertIn('[系统宿主]', baseline)
        self.assertTrue(all(line in before for line in baseline.splitlines()))
        self.assertNotIn('before_panel', result.json['task'])
        self.assertEqual(snapshot['settlement'], ss.StoryService(self.root).snapshot()['settlement'])
        (self.root / 'data.json').write_text('{"round":1,"storyNodes":[],"unrelated":true}')
        self.assertIsNone(self.service.snapshot()['settlement'])

    def test_legacy_failed_task_gets_panel_at_explicit_retry(self):
        self.create()
        claim = self.claim()
        self.worker('page-test/result', {'lease': claim['lease'], 'error': 'failed'})
        with self.service.store._locked():
            state = self.service._read()
            del state['jobs']['page-test']['before_panel']
            self.service._write(state)
        self.page('tasks/page-test/retry', {})
        with self.service.store._locked():
            self.assertIn('[系统宿主]', self.service._read()['jobs']['page-test']['before_panel'])

    def test_bridge_contract_and_manual_projection(self):
        self.create()
        claimed = self.claim()
        envelope = json.loads(claimed['turns'][-1]['content'])
        contract = envelope['output_contract']
        self.assertEqual('story_bridge', envelope['entry_mode'])
        self.assertEqual('operit_tool_loop', envelope['audit_origin'])
        self.assertEqual('operit_session', envelope['retrieval_mode'])
        self.assertNotIn('model_file_tool_calls', envelope)
        self.assertEqual(['type', 'text'], contract['node_keys']['narration'])
        self.assertEqual(['type', 'speaker', 'text'], contract['node_keys']['dialogue'])
        self.assertEqual('array', contract['optional_top_fields']['host_events']['type'])
        self.assertEqual('object', contract['optional_top_fields']['affection_events']['type'])
        self.assertIn('徐志北', contract['registered_speakers'])
        self.assertEqual(self.revision, envelope['round_identity']['base_revision'])
        self.assertNotIn('from injection_core import execute_injection', claimed['turns'][1]['content'])
        self.assertEqual(2, len(claimed['turns']))
        self.assertIn('reading_policy', envelope)
        self.assertNotIn('===== ', claimed['turns'][1]['content'])

    def test_explicit_retry_rebuilds_rules_preserving_original_action(self):
        self.create()
        claimed = self.claim()
        ctx_before = json.loads(self.service._blob('page-test', '.context.json').read_bytes())
        self.worker('page-test/result', {'lease': claimed['lease'], 'error': 'node[1] unknown speaker'})
        rule = self.root / 'txt文件/提示词.md'
        rule.write_text(rule.read_text() + '\nNEW_RULE_SENTINEL\n')
        original = self.files()
        self.page('tasks/page-test/retry', {})
        retried = self.claim()
        ctx_after = json.loads(self.service._blob('page-test', '.context.json').read_bytes())
        envelope = json.loads(retried['turns'][-1]['content'])
        self.assertNotIn('NEW_RULE_SENTINEL', retried['turns'][1]['content'])
        self.assertNotEqual(ctx_before['audit'][str(rule.relative_to(self.root))], ctx_after['audit'][str(rule.relative_to(self.root))])
        self.assertEqual('把杯子放在桌上。', envelope['host_action'])
        self.assertEqual('page-test', envelope['round_identity']['request_id'])
        self.assertEqual(self.revision, envelope['round_identity']['base_revision'])
        self.assertIn('unknown speaker', envelope['previous_validation_error'])
        self.assertEqual(original, self.files())
        self.assertEqual(2, self.service.status()['task']['attempt'])

    def test_bad_node_and_duplicate_keys_still_rejected_without_file_changes(self):
        self.create()
        claimed = self.claim()
        payload = self.payload()
        node = next(x for x in payload['story_nodes'] if x['type'] == 'narration')
        node['speaker'] = '徐志北'
        before = self.files()
        response = self.complete(claimed, payload)
        self.assertEqual('failed', response.json['task']['status'])
        self.assertIn("未知键=['speaker']", response.json['task']['error'])
        self.assertEqual(before, self.files())
        self.page('tasks/page-test/retry', {})
        claimed = self.claim()
        raw = json.dumps(self.payload(), ensure_ascii=False)
        raw = raw.replace('"type": "header"', '"type": "header", "type": "header"', 1)
        response = self.worker('page-test/result', {'lease': claimed['lease'], 'text': raw, 'conversation_audit': self.audit(claimed)})
        self.assertIn('重复键', response.json['task']['error'])
        self.assertEqual(before, self.files())

    def test_snapshot_and_origin_boundary(self):
        response = self.client.get('/api/story/snapshot')
        self.assertEqual('no-store', response.headers['Cache-Control'])
        self.assertEqual(0, response.json['data']['round'])
        self.assertEqual(403, self.client.get('/api/story/snapshot', headers={'Origin': 'https://example.org'}).status_code)
        self.assertEqual(403, self.client.get('/api/story/bridge-info', headers={'Host': 'evil.example'}).status_code)
        self.assertEqual(403, self.client.post('/api/story/worker/claim', json={}).status_code)
        self.assertEqual(403, self.client.post('/api/story/tasks', json={}).status_code)

    def test_create_replay_and_context(self):
        before = self.files()
        first = self.create()
        self.assertEqual(200, first.status_code)
        self.assertEqual('queued', first.json['task']['status'])
        self.assertEqual(first.json, self.create().json)
        claim = self.claim()
        self.assertEqual('page-test', claim['request_id'])
        self.assertIsNone(self.claim())
        context = json.loads(self.service._blob(claim['request_id'], '.context.json').read_bytes())
        for path in ss.RULES:
            self.assertIn(path, context['audit'])
        self.assertNotIn('沈知韫 —', claim['turns'][1]['content'])
        self.assertEqual(before, self.files())

    def test_id_reuse_and_competing_task(self):
        self.create()
        response = self.page('tasks', {'request_id': 'page-test', 'base_revision': self.revision, 'action': '别的行动'})
        self.assertEqual(409, response.status_code)
        self.assertEqual(409, self.create('other-task').status_code)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.service.claim(), range(2)))
        self.assertEqual(1, sum(result['task'] is not None for result in results))

    def test_commit_duplicate_callback_and_consistent_snapshot(self):
        self.create()
        claim = self.claim()
        payload = self.payload()
        with contextlib.redirect_stdout(io.StringIO()):
            first = self.complete(claim, payload)
            second = self.complete(claim, payload)
        self.assertEqual('committed', first.json['task']['status'], first.json)
        self.assertEqual(first.json['task']['receipt'], second.json['task']['receipt'])
        snapshot = self.client.get('/api/story/snapshot').json
        self.assertEqual(1, snapshot['data']['round'])
        self.assertEqual(snapshot['revision'], first.json['task']['receipt']['revision'])
        self.assertEqual(1, self.service.store._ledger()['sequence'])

    def test_invalid_output_keeps_files_and_action_then_retry(self):
        self.create()
        claim = self.claim()
        before = self.files()
        result = self.worker('page-test/result', {'lease': claim['lease'], 'text': 'print("not json")'})
        self.assertEqual('failed', result.json['task']['status'])
        self.assertEqual(before, self.files())
        self.assertEqual('把杯子放在桌上。', result.json['task']['action'])
        self.assertEqual('queued', self.page('tasks/page-test/retry', {}).json['task']['status'])
        current = self.claim()
        self.assertNotEqual(current['lease'], claim['lease'])
        self.assertEqual(409, self.complete(claim).status_code)

    def test_timeout_does_not_automatically_regenerate(self):
        self.create()
        claim = self.claim()
        with self.service.store._locked():
            state = self.service._read()
            state['jobs']['page-test']['lease_until'] = 1
            self.service._write(state)
        self.assertIsNone(self.claim())
        self.assertEqual('interrupted', self.service.status()['task']['status'])
        self.assertEqual(409, self.complete(claim).status_code)
        self.assertEqual('queued', self.page('tasks/page-test/retry', {}).json['task']['status'])

    def test_stale_base_and_late_result(self):
        self.create()
        claim = self.claim()
        payload = self.payload()
        path = self.root / 'data.json'
        path.write_text('{"round":0,"storyNodes":[],"manual_test":true}')
        result = self.complete(claim, payload)
        self.assertEqual('conflict', result.json['task']['status'])
        self.assertEqual(409, self.page('tasks/page-test/retry', {}).status_code)
        self.assertTrue(json.loads(path.read_text())['manual_test'])

    def test_restart_replays_saved_validation_result(self):
        self.create()
        claim = self.claim()
        payload = self.payload()
        with patch.object(self.service, '_finish', side_effect=OSError('simulated restart')):
            with self.assertRaises(OSError):
                self.complete(claim, payload)
        restarted = ss.StoryService(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual('committed', restarted.snapshot()['task']['status'])
        self.assertEqual(1, restarted.store._ledger()['sequence'])

    def test_restart_after_engine_commit_reuses_receipt(self):
        self.create()
        claim = self.claim()
        payload = self.payload()
        with patch.object(self.service, '_finish', side_effect=OSError('simulated restart')):
            with self.assertRaises(OSError):
                self.complete(claim, payload)
        with contextlib.redirect_stdout(io.StringIO()):
            self.service.store.submit(payload)
            restarted = ss.StoryService(self.root)
            result = restarted.snapshot()
        self.assertEqual('committed', result['task']['status'])
        self.assertTrue(result['task']['receipt']['replayed'])
        self.assertEqual(1, restarted.store._ledger()['sequence'])

    def test_saved_result_cannot_be_replaced_by_error(self):
        self.create()
        claim = self.claim()
        with patch.object(self.service, '_finish', side_effect=OSError('pending')):
            with self.assertRaises(OSError):
                self.complete(claim)
        self.assertEqual(409, self.worker('page-test/result', {'lease': claim['lease'], 'error': 'late'}).status_code)
        self.assertEqual('validating', self.service.status()['task']['status'])

    def test_missing_or_incomplete_file_audit_cannot_commit(self):
        self.create()
        claimed = self.claim()
        before = self.files()
        raw = json.dumps(self.payload(), ensure_ascii=False)
        result = self.worker('page-test/result', {'lease': claimed['lease'], 'text': raw})
        self.assertEqual('failed', result.json['task']['status'])
        self.assertIn('审计', result.json['task']['error'])
        self.assertEqual(before, self.files())
        self.page('tasks/page-test/retry', {})
        claimed = self.claim()
        audit = self.audit(claimed)
        first_two_lines = '\n'.join((self.root / rr.FILES[0]).read_text().splitlines()[:2])
        audit['tools'][0] = dict(audit['tools'][0], name='read_file_part', parameters={
            'path': rr.FILES[0], 'start_line': '1', 'end_line': '2'}, result_text=first_two_lines)
        result = self.worker('page-test/result', {'lease': claimed['lease'], 'text': raw, 'conversation_audit': audit})
        self.assertEqual('failed', result.json['task']['status'])
        self.assertIn('未完整取得', result.json['task']['error'])
        self.assertEqual(before, self.files())

    def test_rules_changed_during_generation_blocks_result(self):
        self.create()
        claimed = self.claim()
        audit = self.audit(claimed)
        before = self.files()
        rule = self.root / 'txt文件/提示词.md'
        rule.write_text(rule.read_text() + '\nchanged after prepare\n')
        result = self.worker('page-test/result', {'lease': claimed['lease'],
            'text': json.dumps(self.payload(), ensure_ascii=False), 'conversation_audit': audit})
        self.assertIn(result.json['task']['status'], ('conflict', 'failed'))
        self.assertEqual(before, self.files())

    def test_cancelled_or_wrong_snapshot_and_nondata_reads_block(self):
        self.create()
        claimed = self.claim()
        before = self.files()
        for mutation in ('cancelled', 'snapshot', 'nondata'):
            audit = self.audit(claimed)
            if mutation == 'cancelled':
                audit['outcome']['status'] = 'cancelled'
            elif mutation == 'snapshot':
                audit['snapshot_message_timestamp'] = 456
            else:
                audit['tools'].append({'name': 'read_file', 'parameters': {'path': '开发者功能/log.txt'},
                    'status': 'success', 'part_id': 'invalid', 'result_text': 'invalid source'})
            result = self.worker('page-test/result', {'lease': claimed['lease'],
                'text': json.dumps(self.payload(), ensure_ascii=False), 'conversation_audit': audit})
            self.assertEqual('failed', result.json['task']['status'])
            self.assertEqual(before, self.files())
            self.page('tasks/page-test/retry', {})
            claimed = self.claim()



if __name__ == '__main__':
    unittest.main(verbosity=2)

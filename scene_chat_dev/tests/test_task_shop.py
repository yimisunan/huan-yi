"""End-to-end tests for deterministic System Shop, cold-start/claimable Tasks,
anti-hijack foreground isolation, cross-window TXT persistence, and echo lifecycle."""
from pathlib import Path
import copy
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
import interaction_runtime as ir
import round_runtime as rr
import scene_world as sw
import story_compiler as sc
import story_progression as sp
from story_service import StoryService, register_story_routes
from test_interaction import fixture

_opening_spec = importlib.util.spec_from_file_location('opening_box', ROOT / '存档开局随机盲盒.py')
opening = importlib.util.module_from_spec(_opening_spec)
_opening_spec.loader.exec_module(opening)

DECISION = {
    'prompt': '接下来如何回应？',
    'options': [
        {'id': 'A', 'text': '继续聊起今天的安排'},
        {'id': 'B', 'text': '礼貌地握手告别'},
        {'id': 'C', 'text': '主动提出自己的建议'},
    ],
}


class TaskAndShopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmp_task_shop-', dir=ROOT / 'scene_chat_dev/tmp')
        self.root = fixture(self.temp.name, progression=True)
        self.service = StoryService(self.root)
        self.store = self.service.store
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def _set_host_attr(self, attr, value):
        engine = rr._engine(self.root, self.root)
        path = self.root / rr.FILES[0]
        content = path.read_text(encoding='utf-8')
        updated = engine._simulate_panel(content, {'系统宿主': {attr: value}})
        path.write_text(updated, encoding='utf-8')

    def _read_host_attr(self, attr):
        engine = rr._engine(self.root, self.root)
        return engine._read_attr_value((self.root / rr.FILES[0]).read_text(encoding='utf-8'), '系统宿主', attr)

    def _play_all(self):
        snap = self.service.interaction_snapshot()
        p = snap['playback']
        if not p['segment_id'] or p['completed']:
            return snap
        for step in range(p['revealed'] + 1, p['total'] + 1):
            snap = self.service.playback_progress({
                'save_epoch': snap['save_epoch'],
                'segment_id': p['segment_id'],
                'revealed': step,
                'completed': False,
            })
        return self.service.playback_progress({
            'save_epoch': snap['save_epoch'],
            'segment_id': p['segment_id'],
            'revealed': p['total'],
            'completed': True,
        })

    def _make_req(self, option='BEGIN', text=None, key=None):
        snap = self.service.interaction_snapshot()
        row = ir.segment(self.root, self.store._files())
        if text is None:
            if option == 'BEGIN':
                text = '继续当前剧情'
            elif option == 'REST':
                text = '继续休息'
            else:
                text = next(x['text'] for x in row['decision']['options'] if x['id'] == option)
        self.counter += 1
        return {
            'request_id': key or f'ts-req-{self.counter}',
            'base_revision': snap['revision'],
            'entry_mode': ir.MODE,
            'save_epoch': snap['save_epoch'],
            'action': text,
            'selection': {
                'segment_id': snap['playback']['segment_id'] if option != 'BEGIN' else '',
                'option_id': option,
            },
        }

    def _make_response(
        self, task, *, category='SYSTEM', day=1, time='09:10',
        text='窗外光线安静，对话顺势推进了一步。', events=None,
        task_issue=None, items=None,
    ):
        key = task['request_id']
        context = json.loads(self.service._blob(key, '.context.json').read_text(encoding='utf-8'))
        packet = context['packet']
        lines = (self.root / packet['path']).read_text(encoding='utf-8').splitlines()
        proof = {
            'api': 'Tools.Chat.sendMessageStreaming',
            'chat_id': 'offline-chat',
            'participant_id': 'offline-user',
            'workspace': str(self.root),
            'outcome': {'type': 'committed', 'status': 'completed', 'assistant': {'messageTimestamp': 10}},
            'snapshot_message_timestamp': 10,
            'tools': [{
                'name': 'read_file',
                'parameters': {'path': packet['path']},
                'status': 'success',
                'result_text': '\n'.join(f'{i}| {line}' for i, line in enumerate(lines, 1)),
            }],
        }
        result = {
            'messages': [{'kind': 'narration', 'speaker': '', 'text': text}],
            'decision': DECISION,
            'operation': None,
            'handoff': '',
            'checks': {
                'intent': '承接玩家行动。',
                'knowledge': '仅使用当前在场已知信息。',
                'action': '未擅自替玩家追加行动。',
                'pace': '本段自然停在新的抉择处。',
            },
            'resolution': {
                'category': category,
                'basis': '按实际行为判档。',
                'clock': {'day': day, 'time': time, 'basis': '对应本段经过时间。'},
                'events': events or [],
                'memory': {'fact': text, 'transfers': {}},
                'conditions': None if category == 'SYSTEM' else {
                    'intensity': category,
                    'effective_progress': True,
                    'scene': ir.view(self.store)['location'],
                    'npc': (ir.view(self.store)['cast'] or [None])[0],
                    'action_changed': True,
                    'stress_signals': 0,
                    'breakout_triggered': [],
                },
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
                'task': task_issue,
                'items': items or [],
            },
        }
        return {'lease': task['lease'], 'text': json.dumps(result, ensure_ascii=False), 'conversation_audit': proof}

    def _begin(self, time='09:00'):
        self.service.create(self._make_req('BEGIN'))
        task = self.service.claim()['task']
        res = self.service.result(task['request_id'], self._make_response(task, category='SYSTEM', time=time))
        self.assertEqual(res['task']['status'], 'committed', res)
        self._play_all()

    def _accept_paid(self, option='A', category='A', **kw):
        self.service.create(self._make_req(option))
        task = self.service.claim()['task']
        res = self.service.result(task['request_id'], self._make_response(task, category=category, **kw))
        self.assertEqual(res['task']['status'], 'committed', res)
        return res

    # 1. Shop catalog schema & red-line validation
    def test_shop_catalog_valid_and_rejects_redline_violations(self):
        catalog = sp.load_shop_catalog(self.root, optional=False)
        self.assertEqual(len(catalog['items']), 8)
        self.assertEqual({it['tier'] for it in catalog['items']}, {'low', 'mid', 'high'})

        base = json.loads((self.root / 'txt文件/系统商城目录.json').read_text(encoding='utf-8'))
        catalog_path = self.root / 'txt文件/系统商城目录.json'

        # Invalid tier price band
        bad_price = copy.deepcopy(base)
        bad_price['items'][0]['price'] = 25  # low must be 1..10
        catalog_path.write_text(json.dumps(bad_price, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(rr.RoundError):
            sp.load_shop_catalog(self.root, optional=False)

        # Duplicate SHOP ID
        bad_dup = copy.deepcopy(base)
        bad_dup['items'][1]['id'] = bad_dup['items'][0]['id']
        catalog_path.write_text(json.dumps(bad_dup, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(rr.RoundError):
            sp.load_shop_catalog(self.root, optional=False)

        # Invalid system_effect
        bad_eff = copy.deepcopy(base)
        bad_eff['items'][0]['system_effect'] = 'extend_duration:2'
        catalog_path.write_text(json.dumps(bad_eff, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(rr.RoundError):
            sp.load_shop_catalog(self.root, optional=False)

        # Forbidden duration-manipulation text in desc
        bad_dur = copy.deepcopy(base)
        bad_dur['items'][2]['desc'] = '使用后可延长穿戴时效并冻结倒计时。'
        catalog_path.write_text(json.dumps(bad_dur, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(rr.RoundError):
            sp.load_shop_catalog(self.root, optional=False)

    # 2. Deterministic zero-stamina shop redeem, idempotency, caps, guards, WAL rollback
    def test_shop_redeem_zero_stamina_persistence_guards_and_rollback(self):
        self._begin()
        self._set_host_attr('积分', 35)
        self._set_host_attr('体力', 50)
        before_interaction = json.loads((self.root / 'data.json').read_text(encoding='utf-8')).get('interaction')

        snap = self.service.interaction_snapshot()
        req = {
            'request_id': 'shop-redeem-1',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'item_id': 'SHOP-001',
        }
        res = self.service.redeem_shop(req)
        self.assertEqual(res['status'], 'committed')
        self.assertFalse(res['replayed'])
        self.assertEqual(res['receipt']['points_before'], 35)
        self.assertEqual(res['receipt']['points_after'], 27)
        self.assertEqual(self._read_host_attr('积分'), 27)
        self.assertEqual(self._read_host_attr('体力'), 50)  # zero stamina spent!
        after_interaction = json.loads((self.root / 'data.json').read_text(encoding='utf-8')).get('interaction')
        self.assertEqual(after_interaction, before_interaction)

        # Item persisted with system_effect & source remark
        catalog_txt = (self.root / rr.FILES[1]).read_text(encoding='utf-8')
        self.assertIn('ITEM-001', catalog_txt)
        self.assertIn('host_stamina:10', catalog_txt)
        self.assertIn('系统商城兑换（SHOP-001）', catalog_txt)

        # 【商城与回响状态】 persisted in 全局记忆库.txt
        mem_txt = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        parsed_shop = sp.parse_shop_echo_block(mem_txt)
        self.assertEqual(parsed_shop['redeemed'].get('SHOP-001'), 1)
        self.assertEqual(len(parsed_shop['recent']), 1)
        self.assertTrue(any(e['kind'] == 'shop_redeemed' for e in parsed_shop['echoes']))

        # Idempotent replay with same request_id
        again = self.service.redeem_shop(req)
        self.assertTrue(again['replayed'])
        self.assertEqual(self._read_host_attr('积分'), 27)

        # Reusing same request_id with different item_id raises ConflictError
        with self.assertRaises(rr.ConflictError):
            self.service.redeem_shop({**req, 'item_id': 'SHOP-002'})

        # Insufficient points rejected cleanly (SHOP-007 = 100 pts)
        snap2 = self.service.interaction_snapshot()
        with self.assertRaises(rr.RoundError):
            self.service.redeem_shop({
                'request_id': 'shop-too-poor',
                'base_revision': snap2['revision'],
                'save_epoch': snap2['save_epoch'],
                'item_id': 'SHOP-007',
            })
        self.assertEqual(self._read_host_attr('积分'), 27)

        # Purchase cap enforcement: SHOP-005 (price 30, max_per_save 1)
        self._set_host_attr('积分', 70)
        snap3 = self.service.interaction_snapshot()
        r_cap = self.service.redeem_shop({
            'request_id': 'shop-cap-1',
            'base_revision': snap3['revision'],
            'save_epoch': snap3['save_epoch'],
            'item_id': 'SHOP-005',
        })
        self.assertEqual(r_cap['status'], 'committed')
        snap4 = self.service.interaction_snapshot()
        with self.assertRaises(rr.RoundError):
            self.service.redeem_shop({
                'request_id': 'shop-cap-2',
                'base_revision': snap4['revision'],
                'save_epoch': snap4['save_epoch'],
                'item_id': 'SHOP-005',
            })

        # Active job blocks deterministic shop redeem
        self.service.create(self._make_req('A'))
        snap5 = self.service.interaction_snapshot()
        with self.assertRaises(rr.ConflictError):
            self.service.redeem_shop({
                'request_id': 'shop-while-busy',
                'base_revision': snap5['revision'],
                'save_epoch': snap5['save_epoch'],
                'item_id': 'SHOP-001',
            })
        sp.cancel(self.service, snap5['task']['request_id'])

        # WAL rollback on partial publish failure
        before_files = self.store._files()
        snap6 = self.service.interaction_snapshot()
        original_publish = self.store._publish
        calls = 0

        def fail_once(values):
            nonlocal calls
            calls += 1
            if calls == 1:
                rr._atomic(self.root / rr.FILES[0], values[rr.FILES[0]])
                raise OSError('injected shop publish interruption')
            return original_publish(values)

        with patch.object(self.store, '_publish', side_effect=fail_once):
            with self.assertRaises(OSError):
                self.service.redeem_shop({
                    'request_id': 'shop-wal-rollback',
                    'base_revision': snap6['revision'],
                    'save_epoch': snap6['save_epoch'],
                    'item_id': 'SHOP-002',
                })
        self.store.recover()
        self.assertEqual(self.store._files(), before_files)

    # 3. Chain SHOP-001 redemption -> free use_recovery_item stamina restore
    def test_shop_redeem_chains_into_free_recovery_item(self):
        self._begin()
        self._set_host_attr('积分', 20)
        self._set_host_attr('体力', 45)
        snap = self.service.interaction_snapshot()
        res = self.service.redeem_shop({
            'request_id': 'shop-buy-tonic',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'item_id': 'SHOP-001',
        })
        item_id = res['receipt']['item_id']
        self.assertEqual(self._read_host_attr('体力'), 45)
        use_req = self._make_req('CUSTOM', f'使用恢复道具 {item_id}')
        use_req['operation'] = {'code': 'use_recovery_item', 'item_id': item_id}
        use_res = self.service.create(use_req)
        self.assertEqual(use_res['task']['status'], 'committed', use_res)
        self.assertEqual(self._read_host_attr('体力'), 55)
        self.assertEqual(sp.state(self.root, self.store._files())['item_recovered'], 10)

    # 4. All 8 opening prologues deterministically mount starter TASK-001
    def test_all_eight_prologues_mount_starter_task_001(self):
        self.assertEqual(len(opening.SCENARIOS), 8)
        for scenario in opening.SCENARIOS:
            with tempfile.TemporaryDirectory(prefix='tmp_open_task-', dir=ROOT / 'scene_chat_dev/tmp') as td:
                r = fixture(td, progression=True)
                st = rr.RoundStore(r)
                with st._locked():
                    opening.initialize_prologue(r, 'starter-test-' + scenario['id'], scenario['id'])
                mem = (r / rr.FILES[0]).read_text(encoding='utf-8')
                engine = rr._engine(r, r)
                tblock = engine._parse_task_block(mem)
                self.assertIsNotNone(tblock['current'], scenario['id'])
                self.assertEqual(tblock['current']['id'], 'TASK-001')
                self.assertEqual(tblock['current']['target'], '系统宿主')
                self.assertEqual(tblock['current']['attr'], '积分')
                self.assertEqual(tblock['current']['value'], 4)
                self.assertEqual(tblock['current']['tier'], 'small')
                self.assertEqual(tblock['current']['status'], '进行中')
                # Ensure 【商城与回响状态】 still intact right next to 【任务状态】
                self.assertIn('【商城与回响状态】', mem)

        # Unfinished prologue playback blocks deterministic shop redeem
        with self.store._locked():
            opening.initialize_prologue(self.root, 'prologue-guard', opening.SCENARIOS[0]['id'])
        snap = self.service.interaction_snapshot()
        self.assertFalse(snap['playback']['completed'])
        with self.assertRaises(rr.ConflictError):
            self.service.redeem_shop({
                'request_id': 'shop-during-unplayed-prologue',
                'base_revision': snap['revision'],
                'save_epoch': snap['save_epoch'],
                'item_id': 'SHOP-001',
            })

    # 5. Task completion -> echo -> one-click claim + same-turn pending_item + new task regression
    def test_task_completion_echo_claim_and_same_turn_chain(self):
        with self.store._locked():
            opening.initialize_prologue(self.root, 'quest-flow', opening.SCENARIOS[0]['id'])
        self._play_all()
        self._set_host_attr('积分', 2)

        # Trigger host_events (+2 points) to cross TASK-001 target (4)
        ev_text = '她安静听完你的安排，微微颔首。'
        self._accept_paid(
            time='23:15',
            text=ev_text,
            events=[{'group': 'host_events', 'target': '系统宿主', 'tags': ['日常_信任建立'], 'evidence': ev_text}],
        )
        snap = self._play_all()
        self.assertTrue(snap['settlement']['task_completed'])
        self.assertEqual(self._read_host_attr('积分'), 19)  # 2 + 2 + 15
        self.assertTrue(snap['world']['tasks']['pending_item'].startswith('TASK-001'))
        mem_after_complete = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        echoes = sp.parse_shop_echo_block(mem_after_complete)['echoes']
        self.assertTrue(any(e['kind'] == 'task_completed' and e['ref'] == 'TASK-001' for e in echoes))

        # One-click zero-stamina claim
        stamina_before_claim = self._read_host_attr('体力')
        claim_req = {
            'request_id': 'claim-task-001',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
        }
        claimed = self.service.claim_task_reward(claim_req)
        self.assertEqual(claimed['status'], 'committed')
        self.assertEqual(claimed['receipt']['task_id'], 'TASK-001')
        self.assertEqual(self._read_host_attr('体力'), stamina_before_claim)
        self.assertIsNone(claimed['snapshot']['world']['tasks']['pending_item'])
        self.assertIn('委托奖励（TASK-001）', (self.root / rr.FILES[1]).read_text(encoding='utf-8'))
        mem_after_claim = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        echoes2 = sp.parse_shop_echo_block(mem_after_claim)['echoes']
        self.assertTrue(any(e['kind'] == 'task_reward_claimed' and e['ref'] == 'TASK-001' for e in echoes2))

        # Idempotent replay & duplicate claim rejection
        self.assertTrue(self.service.claim_task_reward(claim_req)['replayed'])
        snap_after = self.service.interaction_snapshot()
        with self.assertRaises(rr.RoundError):
            self.service.claim_task_reward({
                'request_id': 'claim-task-001-again',
                'base_revision': snap_after['revision'],
                'save_epoch': snap_after['save_epoch'],
            })

        # Regression: same-turn Stage 2 pending_item handover + new TASK-002 issuance
        engine = rr._engine(self.root, self.root)
        tstate = engine._parse_task_block((self.root / rr.FILES[0]).read_text(encoding='utf-8'))
        tstate['pending_item'] = 'TASK-001 | 紫檀木书签 |完成回合1'
        engine._write_task_block(tstate)
        cur_points = self._read_host_attr('积分')
        next_task = {
            'title': '再进一步',
            'target': '系统宿主',
            'attr': '积分',
            'value': cur_points + 10,
            'tier': 'small',
            'item_desc': '旧怀表钥匙扣',
        }
        add_item = [{
            'evidence': '你将紫檀木书签仔细收进了随身口袋。',
            'entry': {
                'action': 'add',
                'name': '紫檀木书签',
                'type': '永久性',
                'desc': '完成委托后留下的精致紫檀木书签。',
                'quantity': 1,
                'status': '仓库中',
                'location': '随身',
                'target': '未使用',
                'duration': '无',
                'expire_rule': '无',
            },
        }]
        self._accept_paid(
            time='23:25',
            text='你将紫檀木书签仔细收进了随身口袋。',
            task_issue=next_task,
            items=add_item,
        )
        snap_chain = self._play_all()
        self.assertTrue(snap_chain['settlement']['task_issued'])
        self.assertEqual(snap_chain['world']['tasks']['current']['id'], 'TASK-002')
        self.assertEqual(snap_chain['world']['tasks']['current']['status'], '进行中')
        self.assertIsNone(snap_chain['world']['tasks']['pending_item'])

    # 6. Cross-window (is_fresh_session=True) anti-hijack isolation, Stage 2 settlement spec, & echo lifecycle
    def test_cross_window_anti_hijack_isolation_and_echo_lifecycle(self):
        with self.store._locked():
            opening.initialize_prologue(self.root, 'anti-hijack', opening.SCENARIOS[0]['id'])
        self._play_all()
        self._set_host_attr('积分', 10)  # 10 - 8 = 2 (< 4), keeping TASK-001 in-progress during echo test
        snap = self.service.interaction_snapshot()
        self.service.redeem_shop({
            'request_id': 'shop-for-cross-window',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'item_id': 'SHOP-001',
        })

        # Simulate brand-new window / fresh StoryService instance
        fresh_service = StoryService(self.root)
        self.service = fresh_service
        self.store = fresh_service.store

        self.service.create(self._make_req('A'))
        task = self.service.claim()['task']
        mat = self.service.material(task['request_id'], {
            'lease': task['lease'],
            'chat_id': 'fresh-window-chat',
            'participant_id': 'fresh-window-user',
            'delivery_version': 2,
            'protocol_mode': 'dual_stream_v2',
            'is_fresh_session': True,
        })

        delta = json.loads(mat['input_text'])
        # Foreground isolation: active task MUST NOT appear in dual_stream_v2 input_text
        self.assertNotIn('tasks', delta)
        self.assertNotIn('TASK-001', delta.get('player_private_memory', ''))
        self.assertNotIn('【任务状态】', delta.get('player_private_memory', ''))
        self.assertNotIn('【商城与回响状态】', delta.get('player_private_memory', ''))
        self.assertNotIn('当前委托', delta.get('qualitative_state', ''))
        self.assertIn('milestone_echo', mat['zone0_global'])

        # Cross-window continuity: fresh-session items keep full desc & source remark; milestone_echo delivered
        self.assertTrue(delta['items'])
        self.assertTrue(delta['items'][0]['fields'].get('描述'))
        self.assertIn('系统商城兑换（SHOP-001）', delta['items'][0]['fields'].get('备注', ''))
        self.assertIn('milestone_echo', delta)
        self.assertTrue(any(e['kind'] == 'shop_redeemed' for e in delta['milestone_echo']['events']))

        # Stage 2 settlement_spec has real panels, task_whitelist_current, and Rule 10
        sspec = mat['settlement_spec']
        self.assertIsNotNone(sspec)
        self.assertIn('panels', sspec['user_context'])
        self.assertTrue(any('[系统宿主]' in line for line in sspec['user_context']['panels']))
        self.assertIn('task_whitelist_current', sspec['user_context'])
        self.assertIn('系统宿主', sspec['user_context']['task_whitelist_current'])
        self.assertIn('10. 任务续接与道具增量：', sspec['system_prompt'])

        # Retry safety: failing this turn MUST NOT consume the pending echo
        self.service.result(task['request_id'], {'lease': task['lease'], 'error': 'simulated model error'})
        mem_after_fail = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        self.assertTrue(any(e['kind'] == 'shop_redeemed' for e in sp.parse_shop_echo_block(mem_after_fail)['echoes']))

        # Retry and commit -> consumes delivered echo once
        self.service.retry(task['request_id'], {})
        task2 = self.service.claim()['task']
        res = self.service.result(task2['request_id'], self._make_response(task2, category='A', time='23:15'))
        self.assertEqual(res['task']['status'], 'committed', res)
        self._play_all()
        mem_after_commit = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        self.assertEqual(sp.parse_shop_echo_block(mem_after_commit)['echoes'], [])

        # Next turn (incremental delta): NO milestone_echo, and held_items keeps compact desc & source
        self.service.create(self._make_req('A'))
        task3 = self.service.claim()['task']
        mat2 = self.service.material(task3['request_id'], {
            'lease': task3['lease'],
            'chat_id': 'fresh-window-chat-2',
            'participant_id': 'fresh-window-user',
            'delivery_version': 2,
            'protocol_mode': 'dual_stream_v2',
            'is_fresh_session': False,
            'synced_zone0_sha256': mat['zone0_sha256'],
            'synced_zone1_sha256': mat['zone1_sha256'],
            'last_committed_sequence': mat['last_committed_sequence'] + 1,
        })
        delta2 = json.loads(mat2['input_text'])
        self.assertNotIn('milestone_echo', delta2)
        self.assertEqual(delta2['anchor'], 'incremental_delta')
        self.assertTrue(delta2.get('held_items'))
        self.assertTrue(delta2['held_items'][0].get('desc'))
        self.assertIn('系统商城兑换（SHOP-001）', delta2['held_items'][0].get('source', ''))

    # 7. HTTP route & security header boundaries
    def test_http_shop_and_claim_routes_enforce_client_header_and_origin(self):
        self._begin()
        self._set_host_attr('积分', 20)
        app = Flask('task-shop-http')
        register_story_routes(app, self.root)
        client = app.test_client()

        r_get = client.get('/api/story/shop')
        self.assertEqual(r_get.status_code, 200)
        data = r_get.get_json()
        self.assertEqual(data['points'], 20)
        self.assertEqual(len(data['items']), 8)
        self.assertTrue(data['can_transact'])

        # Missing X-Story-Client header -> 403
        self.assertEqual(client.post('/api/story/shop/redeem', json={}).status_code, 403)
        self.assertEqual(client.post('/api/story/task/claim', json={}).status_code, 403)
        # Foreign origin -> 403
        self.assertEqual(
            client.get('/api/story/shop', headers={'Origin': 'https://foreign.example'}).status_code,
            403,
        )

        # Valid POST /api/story/shop/redeem (SHOP-001 = 8 pts -> 12 pts)
        r_buy = client.post(
            '/api/story/shop/redeem',
            headers={'X-Story-Client': '1'},
            json={
                'request_id': 'http-shop-1',
                'base_revision': data['revision'],
                'save_epoch': data['save_epoch'],
                'item_id': 'SHOP-001',
            },
        )
        self.assertEqual(r_buy.status_code, 200, r_buy.get_json())
        buy_body = r_buy.get_json()
        self.assertEqual(buy_body['receipt']['points_after'], 12)
        self.assertIn('snapshot', buy_body)

        # Seed pending_item and test POST /api/story/task/claim
        engine = rr._engine(self.root, self.root)
        tstate = engine._parse_task_block((self.root / rr.FILES[0]).read_text(encoding='utf-8'))
        tstate['pending_item'] = 'TASK-001 | 银色书签 |完成回合1'
        engine._write_task_block(tstate)
        live = client.get('/api/story/live').get_json()
        r_claim = client.post(
            '/api/story/task/claim',
            headers={'X-Story-Client': '1'},
            json={
                'request_id': 'http-claim-1',
                'base_revision': live['revision'],
                'save_epoch': live['save_epoch'],
            },
        )
        self.assertEqual(r_claim.status_code, 200, r_claim.get_json())
        self.assertEqual(r_claim.get_json()['receipt']['item_name'], '银色书签')

    # 8. scene_world.py & injection_core.py backward compatibility with 【商城与回响状态】
    def test_scene_world_and_injection_core_block_boundary_compatibility(self):
        import shutil
        vis_dst = self.root / sw.VISIBILITY
        vis_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / sw.VISIBILITY, vis_dst)

        # Sync data.json presence with 全局记忆库.txt so LegacyWorld consistency guard passes
        mem_path = self.root / rr.FILES[0]
        engine = rr._engine(self.root, self.root)
        data_path = self.root / 'data.json'
        data_obj = json.loads(data_path.read_text(encoding='utf-8'))
        data_obj['presence'] = engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))
        data_path.write_text(json.dumps(data_obj, ensure_ascii=False), encoding='utf-8')

        # 8a. With 【商城与回响状态】 present
        mem_with = sp.write_shop_echo_block(mem_path.read_text(encoding='utf-8'), {
            'redeemed': {'SHOP-001': 2},
            'recent': ['第1天 09:00 | SHOP-001 | 清神薄荷糖×1 | -8积分 | ITEM-001'],
            'echoes': [{'kind': 'shop_redeemed', 'ref': 'SHOP-001@1', 'summary': '测试回响'}],
        })
        mem_path.write_text(mem_with, encoding='utf-8')
        w_with = sw.LegacyWorld(self.root).import_latest()
        self.assertFalse(any(u.get('domain') == '【商城与回响状态】' for u in w_with['unresolved_source']))
        self.assertIn('【商城与回响状态】', w_with['state_sections'])

        # 8b. Legacy save WITHOUT 【商城与回响状态】 does not log unresolved_source
        mem_legacy = re.sub(r'\n*【商城与回响状态】[\s\S]*?(?=\n【|\n▲ 第一层：|\Z)', '', mem_with)
        self.assertNotIn('【商城与回响状态】', mem_legacy)
        mem_path.write_text(mem_legacy, encoding='utf-8')
        w_legacy = sw.LegacyWorld(self.root).import_latest()
        self.assertFalse(any(u.get('domain') == '【商城与回响状态】' for u in w_legacy['unresolved_source']))
        self.assertNotIn('【商城与回响状态】', w_legacy['state_sections'])

        # 8c. injection_core._write_task_block and process_item_timers preserve 【商城与回响状态】 intact
        mem_path.write_text(mem_with, encoding='utf-8')
        tstate = engine._parse_task_block(mem_with)
        tstate['pending_item'] = 'TASK-001 | 测试小物 |完成回合1'
        engine._write_task_block(tstate)
        engine.process_item_timers(str(mem_path), str(self.root / rr.FILES[1]), 1)
        after_mem = mem_path.read_text(encoding='utf-8')
        parsed_after = sp.parse_shop_echo_block(after_mem)
        self.assertEqual(parsed_after['redeemed'], {'SHOP-001': 2})
        self.assertEqual(len(parsed_after['recent']), 1)
        self.assertEqual(len(parsed_after['echoes']), 1)


if __name__ == '__main__':
    unittest.main()

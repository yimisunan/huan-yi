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
        task_issue=None, items=None, operation=None, messages=None,
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
            'messages': messages or [{'kind': 'narration', 'speaker': '', 'text': text}],
            'decision': DECISION,
            'operation': operation,
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
        self.assertEqual(len(catalog['items']), 16)
        self.assertEqual({it['tier'] for it in catalog['items']}, {'low', 'mid', 'high'})
        self.assertEqual({it['category'] for it in catalog['items']}, {'daily', 'sensual', 'covert'})
        by_id = {it['id']: it for it in catalog['items']}
        self.assertEqual(by_id['SHOP-009']['usage_mode'], 'consumable_target')
        self.assertEqual(by_id['SHOP-009']['pack_qty'], 3)
        self.assertEqual(by_id['SHOP-013']['usage_mode'], 'reusable_tool')
        self.assertEqual(by_id['SHOP-015']['usage_mode'], 'deployable_device')
        self.assertEqual(by_id['SHOP-015']['unlock_req']['min_biz'], 25)

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

    # 4. All 10 opening prologues deterministically mount diversified starter TASK-001
    def test_all_eight_prologues_mount_starter_task_001(self):
        self.assertEqual(len(opening.SCENARIOS), 10)
        seen_attrs = set()
        for scenario in opening.SCENARIOS:
            with tempfile.TemporaryDirectory(prefix='tmp_open_task-', dir=ROOT / 'scene_chat_dev/tmp') as td:
                r = fixture(td, progression=True)
                st = rr.RoundStore(r)
                with st._locked():
                    opening.initialize_prologue(r, 'starter-test-' + scenario['id'], scenario['id'])
                mem = (r / rr.FILES[0]).read_text(encoding='utf-8')
                engine = rr._engine(r, r)
                tblock = engine._parse_task_block(mem)
                exp = opening.OPENING_TASKS[scenario['id']]
                self.assertIsNotNone(tblock['current'], scenario['id'])
                self.assertEqual(tblock['current']['id'], 'TASK-001')
                self.assertEqual(tblock['current']['target'], exp['target'])
                self.assertEqual(tblock['current']['attr'], exp['attr'])
                self.assertEqual(tblock['current']['value'], exp['value'])
                self.assertEqual(tblock['current']['tier'], 'small')
                self.assertEqual(tblock['current']['status'], '进行中')
                seen_attrs.add(exp['attr'])
                # Ensure 【商城与回响状态】 still intact right next to 【任务状态】
                self.assertIn('【商城与回响状态】', mem)
        self.assertTrue({'积分', '商业嗅觉', '好感'}.issubset(seen_attrs))

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
            opening.initialize_prologue(self.root, 'quest-flow', 'zhiyun_sunday_noon')
        self._play_all()
        self._set_host_attr('积分', 4)

        # Trigger host_events (+2 points) to cross TASK-001 target (6 for zhiyun_sunday_noon)
        ev_text = '她安静听完你的安排，微微颔首。'
        self._accept_paid(
            time='12:05',
            text=ev_text,
            events=[{'group': 'host_events', 'target': '系统宿主', 'tags': ['日常_信任建立'], 'evidence': ev_text}],
        )
        snap = self._play_all()
        self.assertTrue(snap['settlement']['task_completed'])
        self.assertEqual(self._read_host_attr('积分'), 21)  # 4 + 2 + 15
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
        self.assertEqual(len(data['items']), 16)
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

    # 9. Stacked points + 商业嗅觉 / 好感 unlock_req enforcement
    def test_shop_unlock_req_enforcement(self):
        self._begin()
        self._set_host_attr('积分', 200)
        self._set_host_attr('商业嗅觉', 10)

        # SHOP-015 requires min_biz >= 25
        sv = self.service.shop_view()
        cam = next(x for x in sv['items'] if x['id'] == 'SHOP-015')
        self.assertFalse(cam['unlocked'])
        self.assertIn('商业嗅觉', cam['unlock_hint'])
        snap = self.service.interaction_snapshot()
        with self.assertRaises(rr.RoundError):
            self.service.redeem_shop({
                'request_id': 'unlock-fail-1',
                'base_revision': snap['revision'],
                'save_epoch': snap['save_epoch'],
                'item_id': 'SHOP-015',
            })

        # Raise 商业嗅觉 to 25 -> SHOP-015 unlocks & redeems cleanly
        self._set_host_attr('商业嗅觉', 25)
        sv2 = self.service.shop_view()
        cam2 = next(x for x in sv2['items'] if x['id'] == 'SHOP-015')
        self.assertTrue(cam2['unlocked'])
        snap2 = self.service.interaction_snapshot()
        r_cam = self.service.redeem_shop({
            'request_id': 'unlock-ok-1',
            'base_revision': snap2['revision'],
            'save_epoch': snap2['save_epoch'],
            'item_id': 'SHOP-015',
        })
        self.assertEqual(r_cam['status'], 'committed')

        # SHOP-014 requires BOTH min_biz >= 15 AND min_any_affection >= 55
        engine = rr._engine(self.root, self.root)
        mem_path = self.root / rr.FILES[0]
        mem_low = engine._simulate_panel(
            mem_path.read_text(encoding='utf-8'),
            {'沈知韫': {'好感': 30}, '苏婉青': {'好感': 30}, '徐念薇': {'好感': 30}},
        )
        mem_path.write_text(mem_low, encoding='utf-8')
        snap3 = self.service.interaction_snapshot()
        with self.assertRaises(rr.RoundError):
            self.service.redeem_shop({
                'request_id': 'unlock-fail-2',
                'base_revision': snap3['revision'],
                'save_epoch': snap3['save_epoch'],
                'item_id': 'SHOP-014',
            })
        mem_hi = engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {'沈知韫': {'好感': 60}})
        mem_path.write_text(mem_hi, encoding='utf-8')
        snap4 = self.service.interaction_snapshot()
        r_drop = self.service.redeem_shop({
            'request_id': 'unlock-ok-2',
            'base_revision': snap4['revision'],
            'save_epoch': snap4['save_epoch'],
            'item_id': 'SHOP-014',
        })
        self.assertEqual(r_drop['receipt']['quantity'], 2)

    # 10. In-Story 【商城定制】 Tag E2E: Zone 2 directive -> Stage 2 scene_state.shop_adds -> anti-cheat filter -> DYN-* -> redeem -> delete + v2.1.8 claim compat
    def test_in_story_shop_custom_tag_e2e(self):
        self._begin()
        self._set_host_attr('积分', 120)
        self._set_host_attr('商业嗅觉', 30)

        # Tag detection: untagged turns return None; tagged turns extract clean query
        self.assertIsNone(sp.detect_shop_custom_request('（绕到母亲身后揉太阳穴）妈，这么晚了别操心了。'))
        q_extracted = sp.detect_shop_custom_request(
            '（绕到母亲身后揉太阳穴）妈，别担心了。（【商城定制】有没有能化解大姑妈这次来访挑刺，顺便带点深夜氛围的道具？）'
        )
        self.assertIn('大姑妈', q_extracted)

        # Untagged turn: Zone 2 and Stage 2 context carry ZERO shop_custom overhead
        req_plain = self._make_req('CUSTOM', text='我给沈知韫倒了杯温水。')
        self.service.create(req_plain)
        task_plain = self.service.claim()['task']
        mat_plain = self.service.material(task_plain['request_id'], {
            'lease': task_plain['lease'], 'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
            'chat_id': 'c-plain', 'participant_id': 'p-plain',
        })
        self.assertNotIn('shop_custom_directive', mat_plain['input_text'])
        self.assertNotIn('shop_custom_requested', mat_plain['settlement_spec']['user_context'])
        sp.cancel(self.service, task_plain['request_id'])

        # Tagged turn: Zone 2 injects shop_custom_directive & Stage 2 injects shop_custom_requested
        tagged_text = '（给母亲揉太阳穴）妈别急。（【商城定制】定制应对大姑妈刁难的礼数策略夹与深夜真丝按摩礼盒）'
        req = self._make_req('CUSTOM', text=tagged_text)
        self.service.create(req)
        task = self.service.claim()['task']
        mat = self.service.material(task['request_id'], {
            'lease': task['lease'], 'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
            'chat_id': 'c-shop', 'participant_id': 'p-shop',
        })
        self.assertIn('shop_custom_directive', mat['input_text'])
        self.assertTrue(mat['settlement_spec']['user_context'].get('shop_custom_requested'))

        # Commit turn with scene_state.shop_adds: 2 valid (strategy + sensual) + 1 anti-cheat timer hack (filtered without failing turn!)
        resp = self._make_response(
            task, category='A', time='09:20',
            text='沈知韫微阖着眼，脑海中悄然浮现「大姑妈家宴礼数应对备忘」与「夜玫瑰真丝披肩礼盒」两项上架提示。',
        )
        payload = json.loads(resp['text'])
        payload['resolution']['scene_state'] = {
            'shop_adds': [
                {
                    'name': '大姑妈家宴礼数应对备忘',
                    'category': 'daily',
                    'usage_mode': 'reusable_tool',
                    'price': 18,
                    'pack_qty': 1,
                    'desc': '整理了大姑妈历年挑刺习惯与化解话术的私密策略备忘，替苏婉青提前避坑。',
                    'system_effect': '',
                    'max_per_save': 1,
                },
                {
                    'name': '夜玫瑰真丝披肩礼盒',
                    'category': 'sensual',
                    'usage_mode': 'consumable_target',
                    'price': 36,
                    'pack_qty': 2,
                    'desc': '带着冷冽玫瑰淡香的温感真丝披肩与按摩油组合。',
                    'system_effect': 'buff:温热精油:2:亲密互动更松弛',
                    'max_per_save': 3,
                },
                {
                    'name': '时效冻结沙漏',
                    'category': 'daily',
                    'usage_mode': 'reusable_tool',
                    'price': 20,
                    'pack_qty': 1,
                    'desc': '延长穿戴时效并冻结倒计时。',
                    'system_effect': 'extend_duration:9',
                    'max_per_save': 1,
                },
            ],
        }
        resp['text'] = json.dumps(payload, ensure_ascii=False)
        committed = self.service.result(task['request_id'], resp)
        self.assertEqual(committed['task']['status'], 'committed', committed)
        self._play_all()
        snap_after = self.service.interaction_snapshot()
        shop_added = (snap_after.get('settlement') or {}).get('shop_added') or []
        self.assertEqual(len(shop_added), 2, snap_after.get('settlement'))
        self.assertEqual([x['id'] for x in shop_added], ['DYN-001', 'DYN-002'])
        self.assertEqual([x['grade'] for x in shop_added], ['T1', 'T2'])

        app = Flask(__name__)
        svc = register_story_routes(app, self.root)
        client = app.test_client()
        token = svc.bridge_info()['token']

        # Legacy v2.1.8 bridge worker/shop-inquiry/claim remains a clean 200 no-op
        r_claim = client.post(
            '/api/story/worker/shop-inquiry/claim',
            headers={'X-Story-Bridge': token},
            json={},
        )
        self.assertEqual(r_claim.status_code, 200)
        self.assertIsNone(r_claim.get_json()['inquiry'])

        # Removed /api/story/shop/inquire no longer exists (404)
        self.assertEqual(
            client.post('/api/story/shop/inquire', headers={'X-Story-Client': '1'}, json={}).status_code,
            404,
        )

        # Shop now serves DYN-001 (T1 strategy) and DYN-002 (T2 sensual), while timer-hack item was filtered
        shop1 = client.get('/api/story/shop').get_json()
        dyn_items = [x for x in shop1['items'] if x['source'] == 'ai_restock']
        self.assertEqual([x['id'] for x in dyn_items], ['DYN-001', 'DYN-002'])
        self.assertEqual(dyn_items[0]['grade'], 'T1')
        self.assertEqual(dyn_items[1]['grade'], 'T2')
        self.assertFalse(any(x['name'] == '时效冻结沙漏' for x in shop1['items']))

        # Redeem DYN-002 (pack_qty=2, T2 unlocked because host_biz=30 >= 15)
        r_buy = client.post(
            '/api/story/shop/redeem',
            headers={'X-Story-Client': '1'},
            json={
                'request_id': 'buy-dyn-2',
                'base_revision': shop1['revision'],
                'save_epoch': shop1['save_epoch'],
                'item_id': 'DYN-002',
            },
        )
        self.assertEqual(r_buy.status_code, 200, r_buy.get_json())
        self.assertEqual(r_buy.get_json()['receipt']['quantity'], 2)

        # Delete DYN-001 via DELETE route
        r_del = client.delete(
            '/api/story/shop/dynamic/DYN-001',
            headers={'X-Story-Client': '1'},
            json={'save_epoch': shop1['save_epoch']},
        )
        self.assertEqual(r_del.status_code, 200, r_del.get_json())
        shop2 = client.get('/api/story/shop').get_json()
        self.assertFalse(any(x['id'] == 'DYN-001' for x in shop2['items']))
        self.assertTrue(any(x['id'] == 'DYN-002' for x in shop2['items']))

    # 10b. T1-T4 Custom Shop Grading & Anti-Cheese: Turn-1 OP item auto-escalated to T4 & locked despite Shen Zhiyun 95 affection
    def test_custom_shop_t1_to_t4_grading_and_anti_cheese_gates(self):
        self._begin()
        # Simulate Turn-1 host: high points (300) so points aren't the blocker, biz=0, charm=70, max_depravity=0, Shen Zhiyun aff=95
        self._set_host_attr('积分', 300)
        self._set_host_attr('商业嗅觉', 0)
        self._set_host_attr('魅力', 70)
        engine = rr._engine(self.root, self.root)
        mem_path = self.root / rr.FILES[0]
        mem_path.write_text(
            engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {'沈知韫': {'好感': 95, '堕落': 0}}),
            encoding='utf-8',
        )

        # Player tries to cheese an OP item at T1 / 10 points + a covert camera at T1 / 15 points + a normal T1 note
        req = self._make_req('CUSTOM', text='（【商城定制】给我10分买个强效催情遥控跳蛋，再加个15分针孔摄像头和礼数备忘）')
        self.service.create(req)
        task = self.service.claim()['task']
        mat = self.service.material(task['request_id'], {
            'lease': task['lease'], 'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
            'chat_id': 'c-tier', 'participant_id': 'p-tier',
        })
        self.assertIn('"unlocked_grade":"T1"', mat['input_text'])

        resp = self._make_response(task, category='A', time='09:30', text='脑海浮现三件不同品级的定制商品提示。')
        payload = json.loads(resp['text'])
        payload['resolution']['scene_state'] = {
            'shop_adds': [
                {
                    'name': '家宴礼数速查备忘',
                    'grade': 'T1',
                    'category': 'daily',
                    'usage_mode': 'reusable_tool',
                    'price': 15,
                    'desc': '梳理长辈来访话题雷区的实用小卡片。',
                    'system_effect': '',
                },
                {
                    'name': '书架隐蔽针孔摄像头',
                    'grade': 'T1',
                    'category': 'covert',
                    'usage_mode': 'deployable_device',
                    'price': 15,
                    'desc': '伪装成书挡螺丝的隐蔽监控装置。',
                    'system_effect': 'deploy_device:camera',
                },
                {
                    'name': '无线遥控强效催情跳蛋',
                    'grade': 'T1',
                    'category': 'sensual',
                    'usage_mode': 'reusable_tool',
                    'price': 10,
                    'desc': '远程无线震动调控与强效催化器具。',
                    'system_effect': 'buff:极乐遥控:3:持续高强度感官催化',
                    'max_per_save': 3,
                },
            ],
        }
        resp['text'] = json.dumps(payload, ensure_ascii=False)
        committed = self.service.result(task['request_id'], resp)
        self.assertEqual(committed['task']['status'], 'committed', committed)
        self._play_all()

        app = Flask(__name__)
        register_story_routes(app, self.root)
        client = app.test_client()
        shop = client.get('/api/story/shop').get_json()
        self.assertEqual(shop['unlocked_grade'], 'T1')
        by_id = {x['id']: x for x in shop['items'] if x['source'] == 'ai_restock'}

        # DYN-001: genuine T1 daily memo -> 15 pts, unlocked on Turn 1
        self.assertEqual(by_id['DYN-001']['grade'], 'T1')
        self.assertEqual(by_id['DYN-001']['price'], 15)
        self.assertTrue(by_id['DYN-001']['unlocked'])

        # DYN-002: covert camera auto-escalated to T3 -> >=65 pts, locked by min_biz>=30
        self.assertEqual(by_id['DYN-002']['grade'], 'T3')
        self.assertGreaterEqual(by_id['DYN-002']['price'], 65)
        self.assertLessEqual(by_id['DYN-002']['max_per_save'], 2)
        self.assertFalse(by_id['DYN-002']['unlocked'])
        self.assertEqual(by_id['DYN-002']['unlock_req'].get('min_biz'), 30)

        # DYN-003: OP sensual toy auto-escalated to T4 -> >=150 pts, max_per_save=1, LOCKED even with Shen Zhiyun aff=95!
        self.assertEqual(by_id['DYN-003']['grade'], 'T4')
        self.assertGreaterEqual(by_id['DYN-003']['price'], 150)
        self.assertEqual(by_id['DYN-003']['max_per_save'], 1)
        self.assertFalse(by_id['DYN-003']['unlocked'])
        self.assertEqual(by_id['DYN-003']['unlock_req'].get('min_max_depravity'), 60)
        self.assertEqual(by_id['DYN-003']['unlock_req'].get('min_charm'), 85)

        # Attempting to redeem locked T4 on Turn 1 is deterministically rejected
        r_blocked = client.post(
            '/api/story/shop/redeem',
            headers={'X-Story-Client': '1'},
            json={
                'request_id': 'cheese-t4-fail',
                'base_revision': shop['revision'],
                'save_epoch': shop['save_epoch'],
                'item_id': 'DYN-003',
            },
        )
        self.assertEqual(r_blocked.status_code, 400)
        self.assertIn('最高堕落', r_blocked.get_json()['error'])

        # Once player genuinely progresses to max_depravity=65 and host_charm=86, T4 unlocks & redeems cleanly (with 85折!)
        self._set_host_attr('魅力', 86)
        mem_path.write_text(
            engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {'沈知韫': {'堕落': 65}}),
            encoding='utf-8',
        )
        shop_late = client.get('/api/story/shop').get_json()
        self.assertEqual(shop_late['unlocked_grade'], 'T4')
        d3_late = next(x for x in shop_late['items'] if x['id'] == 'DYN-003')
        self.assertTrue(d3_late['unlocked'])
        r_ok = client.post(
            '/api/story/shop/redeem',
            headers={'X-Story-Client': '1'},
            json={
                'request_id': 'unlock-t4-ok',
                'base_revision': shop_late['revision'],
                'save_epoch': shop_late['save_epoch'],
                'item_id': 'DYN-003',
            },
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.get_json())

    # 11. use_item: consumable buff active in same turn (halves SHAME_01 drop) + reusable_tool stays unconsumed
    def test_use_item_consumable_buff_and_reusable_tool(self):
        self._begin()
        self._set_host_attr('积分', 150)
        self._set_host_attr('商业嗅觉', 30)
        engine = rr._engine(self.root, self.root)
        mem_path = self.root / rr.FILES[0]
        mem_path.write_text(
            engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {'沈知韫': {'好感': 50, '羞耻': 50}}),
            encoding='utf-8',
        )

        # Redeem SHOP-009 (热感足部按摩精油, pack_qty=3, buff:温热精油:3) and SHOP-013 (reusable_tool)
        snap = self.service.interaction_snapshot()
        r_oil = self.service.redeem_shop({
            'request_id': 'buy-oil-1',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'item_id': 'SHOP-009',
        })
        oil_id = r_oil['receipt']['item_id']
        snap2 = self.service.interaction_snapshot()
        r_tool = self.service.redeem_shop({
            'request_id': 'buy-tool-1',
            'base_revision': snap2['revision'],
            'save_epoch': snap2['save_epoch'],
            'item_id': 'SHOP-013',
        })
        tool_id = r_tool['receipt']['item_id']

        # Turn 1: use_item on oil + SHAME_02 (violation_drop_08=-4 at aff=50, halved to -2 by 温热精油 buff active in same turn!)
        req1 = self._make_req('CUSTOM', text='拿出热感足部按摩精油，帮沈知韫舒缓脚踝。')
        req1['operation'] = {'code': 'use_item', 'item_id': oil_id, 'target': '沈知韫'}
        self.service.create(req1)
        task1 = self.service.claim()['task']
        ev_text = '温热精油在沈知韫脚踝散开，她耳尖微红地轻颤了一下。'
        res1 = self.service.result(task1['request_id'], self._make_response(
            task1,
            category='C',
            time='09:30',
            text=ev_text,
            operation={'code': 'use_item', 'item_id': oil_id, 'target': '沈知韫'},
            events=[{'group': 'shame_events', 'target': '沈知韫', 'tags': ['C烈度_中度'], 'evidence': ev_text}],
        ))
        self.assertEqual(res1['task']['status'], 'committed', res1)
        self._play_all()

        # Verify: oil qty decremented 3 -> 2, buff 温热精油 persisted at 2回合, SHAME_02 penalty halved!
        world1 = ir.view(self.store)
        oil_after = next(it for it in world1['items'] if it['id'] == oil_id)
        self.assertEqual(oil_after['quantity'], 2)
        mem_after = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        self.assertIn('[温热精油] 剩余时效: 2回合', mem_after)
        aff_after = engine._read_attr_value(mem_after, '沈知韫', '好感')
        self.assertEqual(aff_after, 48)  # 50 - 2 (halved from -4!)

        # Turn 2: use_item on reusable_tool (SHOP-013) -> quantity remains 1
        req2 = self._make_req('CUSTOM', text='取出真丝蒙眼带与玉石滚轮，轻轻试探她的反应。')
        req2['operation'] = {'code': 'use_item', 'item_id': tool_id, 'target': '沈知韫'}
        self.service.create(req2)
        task2 = self.service.claim()['task']
        res2 = self.service.result(task2['request_id'], self._make_response(
            task2,
            category='B',
            time='09:50',
            text='丝滑冰凉的滚轮掠过她的耳际，她屏住呼吸。',
            operation={'code': 'use_item', 'item_id': tool_id, 'target': '沈知韫'},
        ))
        self.assertEqual(res2['task']['status'], 'committed', res2)
        self._play_all()
        world2 = ir.view(self.store)
        tool_after = next(it for it in world2['items'] if it['id'] == tool_id)
        self.assertEqual(tool_after['quantity'], 1)

    # 12. deploy_item -> move_player -> remote inspect_deployed (+ Turn 2 delta) -> retrieve_item lifecycle
    def test_deploy_inspect_and_retrieve_device_lifecycle(self):
        self._begin()
        self._set_host_attr('积分', 150)
        self._set_host_attr('商业嗅觉', 35)

        snap = self.service.interaction_snapshot()
        r_cam = self.service.redeem_shop({
            'request_id': 'buy-cam-dev',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'item_id': 'SHOP-015',
        })
        cam_id = r_cam['receipt']['item_id']

        # Turn 1: deploy_item at 徐家主宅
        dep_op = {'code': 'deploy_item', 'item_id': cam_id, 'spot': '床头暗槽', 'hidden': True}
        req1 = self._make_req('CUSTOM', text='趁无人留意把针孔摄像头藏进床头暗槽。')
        req1['operation'] = dep_op
        self.service.create(req1)
        task1 = self.service.claim()['task']
        res1 = self.service.result(task1['request_id'], self._make_response(
            task1, category='B', time='09:20', text='微小的镜头悄无声息嵌进床头木缝。', operation=dep_op,
        ))
        self.assertEqual(res1['task']['status'], 'committed', res1)
        self._play_all()

        world1 = ir.view(self.store)
        self.assertFalse(any(it['id'] == cam_id for it in world1['items']))
        self.assertEqual(len(world1['deployed_items']), 1)
        self.assertEqual(world1['deployed_items'][0]['location'], '徐家主宅')
        self.assertEqual(world1['deployed_items'][0]['spot'], '床头暗槽')
        items_txt = (self.root / rr.FILES[1]).read_text(encoding='utf-8')
        self.assertIn('▼ 已部署装置区 ▼', items_txt)
        self.assertIn('【安装点位】：床头暗槽', items_txt)

        # Turn 2: move_player to 市中心顶层公寓
        mv_op = {'code': 'move_player', 'destination': '市中心顶层公寓'}
        req2 = self._make_req('CUSTOM', text='前往市中心顶层公寓')
        req2['operation'] = mv_op
        self.service.create(req2)
        task2 = self.service.claim()['task']
        res2 = self.service.result(task2['request_id'], self._make_response(
            task2, category='A', time='09:50', text='车子停在公寓楼下，乘电梯上了顶层。', operation=mv_op,
        ))
        self.assertEqual(res2['task']['status'], 'committed', res2)
        self._play_all()

        # Verify retrieve_item from wrong location fails
        bad_ret = self._make_req('CUSTOM', text='回收摄像头')
        bad_ret['operation'] = {'code': 'retrieve_item', 'item_id': cam_id}
        with self.assertRaises(rr.RoundError):
            self.service.create(bad_ret)

        # Turn 3: inspect_deployed from 市中心顶层公寓 succeeds and injects remote_cast + deployed_items_remote
        insp_op = {'code': 'inspect_deployed', 'item_id': cam_id}
        req3 = self._make_req('CUSTOM', text='打开加密监控端查看徐家主宅的实时画面。')
        req3['operation'] = insp_op
        self.service.create(req3)
        task3 = self.service.claim()['task']
        ctx3 = json.loads(self.service._blob(task3['request_id'], '.context.json').read_text(encoding='utf-8'))
        env3 = json.loads(ctx3['turns'][0]['content'])
        op_detail = (env3.get('operation_context') or {}).get('detail') or {}
        self.assertEqual(op_detail.get('kind'), 'inspect_deployed')
        self.assertEqual((op_detail.get('device') or {}).get('location'), '徐家主宅')
        self.assertIsInstance(op_detail.get('remote_cast'), list)

        # Verify Turn 2..N compiled user_delta emits deployed_items_remote via real StoryService.material()
        mat3 = self.service.material(task3['request_id'], {
            'lease': task3['lease'],
            'chat_id': 'c-dev',
            'participant_id': 'p-dev',
            'delivery_version': 2,
            'protocol_mode': 'dual_stream_v2',
            'is_fresh_session': False,
        })
        delta_t2 = mat3['input_text']
        self.assertIn('deployed_items_remote', delta_t2)
        self.assertIn('床头暗槽', delta_t2)

        res3 = self.service.result(task3['request_id'], self._make_response(
            task3, category='B', time='10:10',
            text='手机屏幕亮起，主宅卧室里暖灯微亮，隐约能看见沈知韫站在镜前整理披肩。',
            operation=insp_op,
        ))
        self.assertEqual(res3['task']['status'], 'committed', res3)
        self._play_all()

        # Turn 4: move back to 徐家主宅 and retrieve_item -> restored to active items
        mv_back = {'code': 'move_player', 'destination': '徐家主宅'}
        req4 = self._make_req('CUSTOM', text='回到徐家主宅')
        req4['operation'] = mv_back
        self.service.create(req4)
        task4 = self.service.claim()['task']
        self.service.result(task4['request_id'], self._make_response(
            task4, category='A', time='10:40', text='推门回到徐家主宅。', operation=mv_back,
        ))
        self._play_all()

        ret_op = {'code': 'retrieve_item', 'item_id': cam_id}
        req5 = self._make_req('CUSTOM', text='趁无人注意从床头暗槽取回针孔摄像头。')
        req5['operation'] = ret_op
        self.service.create(req5)
        task5 = self.service.claim()['task']
        res5 = self.service.result(task5['request_id'], self._make_response(
            task5, category='A', time='10:50', text='指尖探入床头木缝，将装置收回随身口袋。', operation=ret_op,
        ))
        self.assertEqual(res5['task']['status'], 'committed', res5)
        self._play_all()

        world_end = ir.view(self.store)
        self.assertEqual(len(world_end['deployed_items']), 0)
        self.assertTrue(any(it['id'] == cam_id and it['quantity'] == 1 for it in world_end['items']))


if __name__ == '__main__':
    unittest.main()

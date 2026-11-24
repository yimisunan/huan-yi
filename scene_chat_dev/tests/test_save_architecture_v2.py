"""Comprehensive regression suite for P0 + P1 + P2 Save Architecture Overhaul.

Covers all 9 verification pillars from implementation_plan.md:
  1. Legacy .txt auto-migration -> P2 JSON + one-way .txt roundtrip + external edit drift detection
  2. Cold-boot recovery after deleting .round-runtime/ and data.json (zero HTTP 500 + monotonic sequence)
  3. memory_context() 6000-char budget strict priority (L1 > L2 > L3 > L4, newer L2 preferred)
  4. dual_stream_v2 & single_prefix_v2 unconditional memory_transfer_sources.source_bodies + empty fact safety
  5. PROLOGUE cleanliness, LegacyWorld fresh prologue import, and blindbox schedule consistency across all 8 scenarios
  6. Task completion + immediate TASK-002 issuance preserving tasks.pending_items queue for sequential claiming
  7. Su Wanqing 85-cap persistent unlock (su_affection_85_unlocked) + bidirectional visiting window
  8. Delivered items isolation (shop re-buy never overwrites), giftable=false guard, SHAME_06 full 24-turn buff
  9. Decision 2 deterministic backend mechanics (nap/insomnia/overnight +40, Passive Lv.2/Lv.3 & dynamic EXP,
     first-trigger & homogeneity immunity c_streak, secrets_unlocked INTEL-002 + extended guardrail_check)
"""
import copy
import importlib.util
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

from flask import Flask

sys.dont_write_bytecode = True
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import injection_core as ic
import interaction_runtime as ir
import round_runtime as rr
import save_store
import story_compiler as sc
import story_progression as sp
from scene_world import LegacyWorld, ENTITIES, VISIBILITY
from story_service import StoryService, register_story_routes
from test_phase_ab_linkage import (
    complete_current_playback,
    make_isolated_workspace,
    reset_clean_save,
    run_action_turn,
)

_opening_spec = importlib.util.spec_from_file_location('opening_box_v2', REPO / '存档开局随机盲盒.py')
opening = importlib.util.module_from_spec(_opening_spec)
_opening_spec.loader.exec_module(opening)


class SaveArchitectureV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_isolated_workspace()
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 1. Legacy .txt auto-migration -> P2 JSON roundtrip + external edit drift detection
    def test_01_legacy_txt_auto_migration_roundtrip_and_drift_detection(self):
        # Remove P2 JSONs to simulate an old legacy .txt-only save
        for rel in (save_store.SAVE_STATE_PATH, save_store.MEMORY_LAYERS_PATH, save_store.RECENT_PLAYBACK_PATH):
            p = self.tmp / rel
            if p.exists():
                p.unlink()

        legacy_mem = (
            '【实时面板快照】\n'
            '▶ 当前最新数值\n'
            '[系统宿主] 积分 12 | 经验值 8 | 体力 85 | 魅力 72 | 商业嗅觉 25\n'
            '[沈知韫] 好感 95 | 堕落 5 | 欲望 10 | 羞耻 92 | 体力 90 | 高潮 0% | 内射 1次 | 怀孕 False | 被动 Lv.1\n'
            '[徐念薇] 好感 35 | 堕落 0 | 欲望 0 | 羞耻 99 | 体力 65 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.0\n'
            '[苏婉青] 好感 86 | 堕落 12 | 欲望 20 | 羞耻 80 | 体力 95 | 高潮 10% | 内射 0次 | 怀孕 False | 被动 Lv.2\n'
            '[徐承邺] 堕落 0\n\n'
            '【人物所在】\n'
            '沈知韫：徐家主宅 | 事由：常住\n'
            '徐念薇：大学 | 事由：工作日在大学\n'
            '苏婉青：市中心顶层公寓 | 事由：常住\n'
            '徐志北：徐家主宅 | 事由：常住\n\n'
            '【当前激活微状态】\n'
            '▶ 沈知韫\n'
            'residual_tension: true | confusion_debt: false | momentary_ease: false\n'
            '▶ 苏婉青\n'
            'momentary_ease: true | residual_tension: false | confusion_debt: false\n'
            '▶ 徐念薇\n'
            'momentary_ease: false | residual_tension: false | confusion_debt: false\n\n'
            '==================================================\n'
            '▶ 上回合历史快照\n'
            '[系统宿主] 积分 0 | 经验值 0 | 体力 100 | 魅力 70 | 商业嗅觉 0\n\n'
            '==================================================\n'
            '【当前持久化状态与BUFF】\n'
            '▶ 沈知韫\n'
            '  - [体液锁定] 剩余时效: 20回合 (示例效果)\n'
            '▶ 苏婉青\n'
            '  - 无\n'
            '▶ 徐念薇\n'
            '  - 无\n'
            '==================================================\n'
            '【回合计数器】\n'
            '  连续守护回合: 2\n\n'
            '【监视状态】\n'
            '徐承邺位置：外地\n'
            '徐承邺_沈知韫：警惕 10 | 发现 0 | 发现几率 5\n'
            '徐承邺_苏婉青：警惕 0 | 发现 0 | 发现几率 0\n'
            '徐承邺_徐念薇：警惕 0 | 发现 0 | 发现几率 0\n'
            '徐承邺_徐志北：警惕 5 | 发现 0 | 发现几率 0\n\n'
            '【任务状态】\n'
            '当前任务：TASK-001 | 试探 | 系统宿主·积分·20 | small | 银扣 | 进行中 |发布回合1\n'
            '最近完成：（空）\n'
            '待发道具：（无）\n\n'
            '【道具倒计时】\n'
            '（空）\n\n'
            '▲ 第一层：【即时运存区】\n'
            f'【1】深夜书房的旧序幕。\n{save_store.PROLOGUE_MARKER}\n\n'
            '▲ 第二层：【回想运存区】\n（空）\n\n'
            '▲ 第三层：【近期事实缓存区】\n（空）\n\n'
            '▲ 第四层：【深渊纪元浓缩区】\n（空）\n'
        )
        legacy_items = (
            '▼ 活跃道具区 ▼\n\n'
            '【道具名称】：丝绸发带\n【道具ID】：ITEM-001\n【类型】：永久性\n【描述】：柔和丝带\n'
            '【数量】：1\n【获得回合】：1\n【当前状态】：已交付\n【位置】：随身\n【使用对象】：沈知韫\n'
            '【时效】：无\n【剩余时效】：无\n【过期规则】：无\n【使用记录】：无\n【备注】：无\n\n'
            '【道具名称】：清凉薄荷糖\n【道具ID】：ITEM-002\n【类型】：临时性（消耗品）\n【描述】：提神\n'
            '【数量】：2\n【获得回合】：1\n【当前状态】：仓库中\n【位置】：无\n【使用对象】：未使用\n'
            '【时效】：无\n【剩余时效】：无\n【过期规则】：无\n【使用记录】：无\n【备注】：无\n'
            '【系统效果】：host_stamina:10\n\n'
            '▼ 已过期/已消耗道具历史区 ▼\n\n（当前为空）\n'
        )
        (self.tmp / save_store.RENDERED_MEMORY_PATH).write_text(legacy_mem, encoding='utf-8')
        (self.tmp / save_store.RENDERED_ITEMS_PATH).write_text(legacy_items, encoding='utf-8')

        st, ly, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st['panels']['系统宿主']['积分'], 12)
        self.assertEqual(st['panels']['沈知韫']['内射'], 1)
        self.assertTrue(st['mechanics']['su_affection_85_unlocked'])
        self.assertTrue(ly['prologue_active'])
        self.assertNotIn('系统隐藏标记', ly['layers']['L1'][0]['text'])
        self.assertEqual(len(st['items']['active']), 1)
        self.assertEqual(st['items']['active'][0]['id'], 'ITEM-002')
        self.assertEqual(len(st['items']['delivered']), 1)
        self.assertEqual(st['items']['delivered'][0]['id'], 'ITEM-001')

        # Persist P2 JSON + one-way views
        st['mechanics']['secrets_unlocked'].append('INTEL-002')
        save_store.save_bundle(self.tmp, st, ly)
        rendered_mem = (self.tmp / save_store.RENDERED_MEMORY_PATH).read_text(encoding='utf-8')
        rendered_items = (self.tmp / save_store.RENDERED_ITEMS_PATH).read_text(encoding='utf-8')
        self.assertNotIn('上回合历史快照', rendered_mem)
        self.assertNotIn('系统隐藏标记', rendered_mem)
        self.assertIn('▼ 已交付道具区 ▼', rendered_items)
        self.assertIn('【可赠予】', rendered_items)

        # Simulate external direct .txt edit -> drift detection imports panel edit while preserving JSON-only mechanics
        engine = rr._engine(self.tmp, self.tmp)
        edited = engine._simulate_panel(rendered_mem, {'系统宿主': {'积分': 44, '商业嗅觉': 55}})
        (self.tmp / save_store.RENDERED_MEMORY_PATH).write_text(edited, encoding='utf-8')
        st_drifted, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_drifted['panels']['系统宿主']['积分'], 44)
        self.assertEqual(st_drifted['panels']['系统宿主']['商业嗅觉'], 55)
        self.assertIn('INTEL-002', st_drifted['mechanics']['secrets_unlocked'])
        self.assertTrue(st_drifted['mechanics']['su_affection_85_unlocked'])

    # 2. Cold-boot recovery without .round-runtime/ and data.json
    def test_02_cold_boot_recovery_without_runtime_dir_or_data_json(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'cold-boot-init', opening.SCENARIOS[0]['id'])
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store

        run_action_turn(
            self.svc, text='轻轻倒了一杯热茶递过去', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '这么晚了，喝点热茶也好。'}],
            clock={'day': 1, 'time': '23:15'},
            req_id='cold-turn-1',
        )
        run_action_turn(
            self.svc, text='坐到她身旁翻看文件', option_id='B', category='B',
            messages=[{'kind': 'narration', 'speaker': '', 'text': '纸页在台灯下轻轻翻动，室内格外安静。'}],
            clock={'day': 1, 'time': '23:30'},
            req_id='cold-turn-2',
        )
        complete_current_playback(self.svc)
        seq_before = self.store._ledger()['sequence']
        self.assertGreaterEqual(seq_before, 2)

        # Wipe .round-runtime/ AND data.json completely (simulating pure 存档/ copy to a new machine/window)
        shutil.rmtree(self.tmp / '.round-runtime')
        (self.tmp / 'data.json').unlink()

        fresh_svc = StoryService(self.tmp)
        app = Flask('cold-boot-check')
        register_story_routes(app, self.tmp)
        client = app.test_client()

        r_live = client.get('/api/story/live')
        self.assertEqual(r_live.status_code, 200)
        live_data = r_live.get_json()
        self.assertGreaterEqual(len(live_data['history']), 2)
        self.assertEqual(live_data['world']['progression']['runtime']['clock'], {'day': 1, 'time': '23:30'})
        self.assertTrue(live_data['history'][-1]['decision']['options'])

        r_snap = client.get('/api/story/snapshot')
        self.assertEqual(r_snap.status_code, 200)

        # Commit next turn on cold-booted service -> sequence must advance monotonically beyond seq_before
        run_action_turn(
            fresh_svc, text='继续确认明天行程', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '明天上午有个早会。'}],
            clock={'day': 1, 'time': '23:45'},
            req_id='cold-turn-3',
        )
        seq_after = fresh_svc.store._ledger()['sequence']
        self.assertGreater(seq_after, seq_before)
        self.assertFalse((self.tmp / '.round-runtime/interaction/000000000001.json').exists())

    # 3. memory_context() 6000-char budget strict priority: L1 > L2 > L3 > L4 & newer L2 first
    def test_03_memory_context_budget_priority_and_recency(self):
        st, ly, _ = save_store.load_bundle(self.tmp)
        ly['prologue_active'] = False
        ly['layers'] = {
            'L1': [
                {'label': '【14】', 'text': '最新即时运存14。' + '甲' * 120},
                {'label': '【15】', 'text': '最新即时运存15。' + '乙' * 120},
                {'label': '【16】', 'text': '最新即时运存16。' + '丙' * 120},
            ],
            'L2': [
                {'label': f'【{n}】', 'text': f'回想层条目{n}。' + ('丁' * 720)}
                for n in range(4, 14)  # 10 entries * ~730 chars = ~7300 chars (> 6000 budget)
            ],
            'L3': [
                {'label': '【2-3】', 'text': '近期事实缓存L3。' + ('戊' * 500)},
            ],
            'L4': [
                {'label': '【1】', 'text': '远古纪元浓缩L4。' + ('己' * 500)},
            ],
        }
        save_store.save_bundle(self.tmp, st, ly)
        mem_txt = (self.tmp / save_store.RENDERED_MEMORY_PATH).read_text(encoding='utf-8')
        ctx = ir.memory_context(self.tmp, mem_txt, '继续聊起近况', {'memory_round': 17, 'phase': 'ready', 'last_closed': 16})
        self.assertLessEqual(len(ctx['text']), 6000)
        # All L1 entries must be kept
        for tag in ('【14】', '【15】', '【16】'):
            self.assertIn(tag, ctx['text'])
        # Newer L2 entries (13, 12, 11) must be selected over oldest L2 (4) and L3/L4
        self.assertIn('【13】', ctx['text'])
        self.assertIn('【12】', ctx['text'])
        self.assertNotIn('回想层条目4', ctx['text'])
        self.assertNotIn('远古纪元浓缩L4', ctx['text'])

    # 4. dual_stream_v2 & single_prefix_v2 unconditional transfer source_bodies + empty fact safety
    def test_04_transfer_source_bodies_unconditional_and_empty_fact_safe(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'transfer-init', opening.SCENARIOS[0]['id'])
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store
        complete_current_playback(self.svc)

        st, ly, _ = save_store.load_bundle(self.tmp)
        ly['prologue_active'] = False
        ly['layers'] = {
            'L1': [{'label': f'【{n}】', 'text': f'实时层源文本{n}'} for n in (21, 22, 23)],
            'L2': [{'label': f'【{n}】', 'text': f'回想层源文本{n}'} for n in range(11, 21)],
            'L3': [{'label': f'【{n}】', 'text': f'缓存层源文本{n}'} for n in range(1, 11)],
            'L4': [],
        }
        st['runtime']['memory_round'] = 24
        st['runtime']['last_closed'] = 23
        st['intel']['held'] = ['INTEL-001']
        save_store.save_bundle(self.tmp, st, ly)
        data_p = self.tmp / 'data.json'
        data_obj = json.loads(data_p.read_text(encoding='utf-8'))
        data_obj['story_runtime'] = {**data_obj.get('story_runtime', {}), 'memory_round': 24, 'last_closed': 23}
        data_p.write_text(json.dumps(data_obj, ensure_ascii=False), encoding='utf-8')

        snap = self.svc.interaction_snapshot()
        row = ir.segment(self.tmp, self.store._files())
        opt_a_text = next(o['text'] for o in row['decision']['options'] if o['id'] == 'A')
        self.svc.create({
            'request_id': 'xfer-req-1',
            'base_revision': snap['revision'],
            'entry_mode': ir.MODE,
            'save_epoch': snap['save_epoch'],
            'action': opt_a_text,
            'selection': {'segment_id': row['id'], 'option_id': 'A'},
        })
        task = self.svc.claim()['task']

        # Verify single_prefix_v2 real material delivery unconditionally carries source_bodies + held_intel
        mat_single = self.svc.material('xfer-req-1', {
            'lease': task['lease'],
            'chat_id': 'chat-single',
            'participant_id': 'card-1',
            'delivery_version': 2,
            'protocol_mode': 'single_prefix_v2',
            'is_fresh_session': True,
        })
        delta_single = mat_single['input_text']
        self.assertIn('实时层源文本21', delta_single)
        self.assertIn('回想层源文本11', delta_single)
        self.assertIn('缓存层源文本1', delta_single)
        self.assertIn('INTEL-001', delta_single)

        # Cancel xfer-req-1, create xfer-req-2, and verify dual_stream_v2 material delivery unconditionally carries source_bodies
        sp.cancel(self.svc, 'xfer-req-1')
        snap_d = self.svc.interaction_snapshot()
        self.svc.create({
            'request_id': 'xfer-req-2',
            'base_revision': snap_d['revision'],
            'entry_mode': ir.MODE,
            'save_epoch': snap_d['save_epoch'],
            'action': opt_a_text,
            'selection': {'segment_id': row['id'], 'option_id': 'A'},
        })
        task2 = self.svc.claim()['task']
        mat_dual = self.svc.material('xfer-req-2', {
            'lease': task2['lease'],
            'chat_id': 'chat-dual',
            'participant_id': 'card-1',
            'delivery_version': 2,
            'protocol_mode': 'dual_stream_v2',
            'is_fresh_session': True,
        })
        spec_text = json.dumps(mat_dual['settlement_spec'], ensure_ascii=False)
        self.assertIn('实时层源文本21', spec_text)
        self.assertIn('回想层源文本11', spec_text)
        self.assertIn('缓存层源文本1', spec_text)

        # Cancel xfer-req-2 and verify empty fact + non-empty transfers does NOT crash
        sp.cancel(self.svc, 'xfer-req-2')
        snap2 = self.svc.interaction_snapshot()
        sp.create(self.svc, {
            'request_id': 'empty-fact-xfer',
            'base_revision': snap2['revision'],
            'save_epoch': snap2['save_epoch'],
            'action': opt_a_text,
            'entry_mode': ir.MODE,
            'operation': None,
            'selection': {'segment_id': row['id'], 'option_id': 'A'},
            'model_key': None,
        })
        tasks_data = self.svc._read()
        job = tasks_data['jobs']['empty-fact-xfer']
        job['status'] = 'validating'
        self.svc._write(tasks_data)
        payload = {
            'schema_version': 3,
            'entry_mode': ir.MODE,
            'request_id': 'empty-fact-xfer',
            'base_revision': job['working_revision'],
            'input': opt_a_text,
            'messages': [{'kind': 'narration', 'speaker': '', 'text': '你点点头，没再多说。'}],
            'decision': {
                'prompt': '下一步？',
                'options': [
                    {'id': 'A', 'text': '继续聊'},
                    {'id': 'B', 'text': '喝口茶'},
                    {'id': 'C', 'text': '走近一步'},
                ],
            },
            'selection': {'segment_id': row['id'], 'option_id': 'A'},
            'operation': None,
            'handoff': '',
            'resolution': {
                'category': 'A',
                'basis': '常规交谈',
                'clock': {'day': 1, 'time': '23:15', 'basis': '几分钟后'},
                'events': [],
                'memory': {'fact': '', 'transfers': {'l1_to_l2_condensed': '多余的转移文本'}},
                'conditions': {
                    'intensity': 'A',
                    'effective_progress': False,
                    'scene': '徐家主宅',
                    'npc': '沈知韫',
                    'action_changed': False,
                    'stress_signals': 0,
                    'breakout_triggered': [],
                },
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
                'task': None,
                'items': [],
            },
            'audit': {
                'required_reads_verified': True,
                'origin': 'operit_session',
                'reservation': job['reservation'],
                'checks': {'intent': '承接', 'knowledge': '在场', 'action': '未代打', 'pace': '停在抉择'},
            },
        }
        res = self.store.submit(payload)
        self.assertEqual(res['status'], 'committed')

    # 5. PROLOGUE cleanliness, LegacyWorld import on fresh prologue, & all 8 blindbox schedule consistency
    def test_05_prologue_cleanliness_legacy_world_import_and_blindbox_schedules(self):
        expected_xnw = {
            'zhiyun_friday_study': '徐家主宅',
            'wanqing_apartment_night': '工作室',
            'wanqing_friday_visit': '工作室',
        }
        for rel in (ENTITIES, VISIBILITY):
            src = REPO / rel
            dst = self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        self.assertEqual(len(opening.SCENARIOS), 10)
        for scenario in opening.SCENARIOS:
            sid = scenario['id']
            with self.subTest(scenario=sid):
                reset_clean_save(self.tmp)
                st_store = rr.RoundStore(self.tmp)
                with st_store._locked():
                    opening.initialize_prologue(self.tmp, 'pro-' + sid, sid)
                mem_txt = (self.tmp / save_store.RENDERED_MEMORY_PATH).read_text(encoding='utf-8')
                self.assertNotIn(save_store.PROLOGUE_MARKER, mem_txt)
                self.assertNotIn('系统隐藏标记', mem_txt)
                _, ly, _ = save_store.load_bundle(self.tmp)
                self.assertTrue(ly['prologue_active'])
                snippet = sp._extract_latest_l1_snippet(mem_txt)
                self.assertNotIn('系统隐藏标记', snippet)
                if sid in expected_xnw:
                    st_now, _, _ = save_store.load_bundle(self.tmp)
                    self.assertEqual(st_now['presence']['徐念薇']['location'], expected_xnw[sid])
                # LegacyWorld must import fresh prologue (round=0 or 1) without ConflictError
                world_res = LegacyWorld(self.tmp).import_latest()
                self.assertEqual(len(world_res['memories']), 1)

    # 6. Task pending_items queue preserved across immediate TASK-002 issuance + sequential claiming
    def test_06_task_pending_items_queue_preserved_across_new_task_issuance(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'task-queue', 'zhiyun_sunday_noon')
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store
        complete_current_playback(self.svc)

        # Give host 4 points so +2 completes TASK-001 (target 6 for zhiyun_sunday_noon)
        st, ly, _ = save_store.load_bundle(self.tmp)
        st['panels']['系统宿主']['积分'] = 4
        save_store.save_bundle(self.tmp, st, ly)

        ev_text = '她安静听完你的安排，微微颔首。'
        run_action_turn(
            self.svc, text=ev_text, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ev_text}],
            clock={'day': 1, 'time': '12:05'},
            events=[{'group': 'host_events', 'target': '系统宿主', 'tags': ['日常_信任建立'], 'evidence': ev_text}],
            req_id='tq-1',
        )
        complete_current_playback(self.svc)
        st1, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st1['tasks']['current']['status'], '已完成')
        self.assertEqual(len(st1['tasks']['pending_items']), 1)
        self.assertTrue(st1['tasks']['pending_items'][0].startswith('TASK-001'))

        # Issue TASK-002 WITHOUT claiming TASK-001 reward first!
        cur_pts = st1['panels']['系统宿主']['积分']
        engine = rr._engine(self.tmp, self.tmp)
        engine.process_task_system(
            {'title': '连环跟进', 'target': '系统宿主', 'attr': '积分', 'value': cur_pts + 2, 'tier': 'small', 'item_desc': '红木镇纸'},
            2, str(self.tmp / rr.FILES[0]),
        )
        st2, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st2['tasks']['current']['id'], 'TASK-002')
        self.assertEqual(len(st2['tasks']['pending_items']), 1)
        self.assertTrue(st2['tasks']['pending_items'][0].startswith('TASK-001'))

        # Complete TASK-002 -> pending_items queue now holds BOTH TASK-001 and TASK-002
        ev_text2 = '她对你今天的统筹十分满意。'
        run_action_turn(
            self.svc, text=ev_text2, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ev_text2}],
            clock={'day': 1, 'time': '23:30'},
            events=[{'group': 'host_events', 'target': '系统宿主', 'tags': ['日常_信任建立'], 'evidence': ev_text2}],
            req_id='tq-2',
        )
        complete_current_playback(self.svc)
        st3, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(len(st3['tasks']['pending_items']), 2)
        self.assertTrue(st3['tasks']['pending_items'][0].startswith('TASK-001'))
        self.assertTrue(st3['tasks']['pending_items'][1].startswith('TASK-002'))

        # Claim both sequentially via deterministic API
        snap_a = self.svc.interaction_snapshot()
        c1 = self.svc.claim_task_reward({'request_id': 'claim-q1', 'base_revision': snap_a['revision'], 'save_epoch': snap_a['save_epoch']})
        self.assertEqual(c1['receipt']['task_id'], 'TASK-001')
        snap_b = self.svc.interaction_snapshot()
        c2 = self.svc.claim_task_reward({'request_id': 'claim-q2', 'base_revision': snap_b['revision'], 'save_epoch': snap_b['save_epoch']})
        self.assertEqual(c2['receipt']['task_id'], 'TASK-002')
        st4, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st4['tasks']['pending_items'], [])
        self.assertEqual(len(st4['items']['active']), 2)

    # 7. Su Wanqing 85-cap persistent unlock + bidirectional visiting window
    def test_07_su_wanqing_85_cap_persistence_and_visiting_window(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'su-cap', scenario_id='wanqing_apartment_morning')
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store
        complete_current_playback(self.svc)

        # Unlock via 苏婉青_真相揭露 while affection is still 40 (<= 85)
        ev = '你点破了她一直藏在心底的真相，她眼眶微红。'
        run_action_turn(
            self.svc, text=ev, option_id='B', category='B',
            messages=[{'kind': 'dialogue', 'speaker': '苏婉青', 'text': ev}],
            clock={'day': 1, 'time': '09:30'},
            events=[{'group': 'affection_events', 'target': '苏婉青', 'tags': ['苏婉青_真相揭露'], 'evidence': ev}],
            req_id='su-unlock-1',
        )
        complete_current_playback(self.svc)
        st1, ly1, _ = save_store.load_bundle(self.tmp)
        self.assertLessEqual(st1['panels']['苏婉青']['好感'], 85)
        self.assertTrue(st1['mechanics']['su_affection_85_unlocked'])

        # Simulate crossing 85 later from a fresh StoryService instance using 深度操控_首次 (+3 when shame>60)
        st1['panels']['苏婉青']['好感'] = 84
        save_store.save_bundle(self.tmp, st1, ly1)
        fresh_svc = StoryService(self.tmp)
        ev2 = '她靠在肩头轻轻吐了口气，彻底放下了戒心。'
        run_action_turn(
            fresh_svc, text=ev2, option_id='B', category='B',
            messages=[{'kind': 'dialogue', 'speaker': '苏婉青', 'text': ev2}],
            clock={'day': 1, 'time': '09:50'},
            events=[{'group': 'affection_events', 'target': '苏婉青', 'tags': ['深度操控_首次'], 'evidence': ev2}],
            req_id='su-unlock-2',
        )
        st2, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st2['panels']['苏婉青']['好感'], 87)  # 84 + 3 crossed 85 because persisted flag!

        # Bidirectional visiting window check (player offstage at 公司)
        mem_path = self.tmp / rr.FILES[0]
        engine = rr._engine(self.tmp, self.tmp)
        st2['presence']['徐志北']['location'] = '公司'
        st2['presence']['苏婉青']['location'] = '市中心顶层公寓'
        save_store.save_bundle(self.tmp, st2, ly1)

        # Tue 16:00 -> visits 徐家主宅
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '16:00'}, '周二', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['苏婉青']['location'], '徐家主宅')
        # Tue 21:00 -> returns to 市中心顶层公寓
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '21:00'}, '周二', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['苏婉青']['location'], '市中心顶层公寓')
        # Sun 11:30 -> visits 徐家主宅
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 6, 'time': '11:30'}, '周日', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['苏婉青']['location'], '徐家主宅')
        # Sun 15:30 -> returns to 市中心顶层公寓
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 6, 'time': '15:30'}, '周日', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['苏婉青']['location'], '市中心顶层公寓')

    # 8. Delivered items isolated, giftable=false guard, SHAME_06 full 24-turn mount
    def test_08_delivered_items_isolated_giftable_guard_and_shame06_full_24_turns(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'item-iso', opening.SCENARIOS[0]['id'])
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store
        complete_current_playback(self.svc)

        # Give points & redeem SHOP-002 (giftable item: 手工茉莉冷萃茶包)
        st, ly, _ = save_store.load_bundle(self.tmp)
        st['panels']['系统宿主']['积分'] = 50
        save_store.save_bundle(self.tmp, st, ly)
        snap = self.svc.interaction_snapshot()
        r1 = self.svc.redeem_shop({'request_id': 'buy-1', 'base_revision': snap['revision'], 'save_epoch': snap['save_epoch'], 'item_id': 'SHOP-002'})
        item1_id = r1['receipt']['item_id']

        # Deliver item1 to present 沈知韫 (transfer_item uses option_id='CUSTOM')
        run_action_turn(
            self.svc, text='把礼物递给她', option_id='CUSTOM', category='B',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '谢谢你，我收下了。'}],
            clock={'day': 1, 'time': '23:15'},
            operation={'code': 'transfer_item', 'item_id': item1_id, 'recipient': '沈知韫'},
            req_id='deliver-1',
        )
        complete_current_playback(self.svc)
        st_del, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_del['items']['active'], [])
        self.assertEqual(len(st_del['items']['delivered']), 1)
        self.assertEqual(st_del['items']['delivered'][0]['id'], item1_id)

        # Re-buy the SAME shop item -> delivered record MUST NOT be overwritten!
        snap2 = self.svc.interaction_snapshot()
        r2 = self.svc.redeem_shop({'request_id': 'buy-2', 'base_revision': snap2['revision'], 'save_epoch': snap2['save_epoch'], 'item_id': 'SHOP-002'})
        self.assertNotEqual(r2['receipt']['item_id'], item1_id)
        st_rebuy, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(len(st_rebuy['items']['active']), 1)
        self.assertEqual(len(st_rebuy['items']['delivered']), 1)
        self.assertEqual(st_rebuy['items']['delivered'][0]['id'], item1_id)

        # Non-giftable shop item SHOP-001 (giftable: false) rejected by transfer_item
        snap3 = self.svc.interaction_snapshot()
        r_ng = self.svc.redeem_shop({'request_id': 'buy-ng', 'base_revision': snap3['revision'], 'save_epoch': snap3['save_epoch'], 'item_id': 'SHOP-001'})
        ng_id = r_ng['receipt']['item_id']
        st_ng, _, _ = save_store.load_bundle(self.tmp)
        ng_item = next(x for x in st_ng['items']['active'] if x['id'] == ng_id)
        self.assertFalse(ng_item['giftable'])
        with self.assertRaises(rr.RoundError):
            ir.operation(self.tmp, self.store._files(), {'code': 'transfer_item', 'item_id': ng_id, 'recipient': '沈知韫'}, '送出薄荷糖')

        # SHAME_06 mounts buff at FULL 24 turns, then decrements to 23 on next turn
        ev_cp = '剧烈喘息之后，温度久久未散。'
        run_action_turn(
            self.svc, text=ev_cp, option_id='C', category='C',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ev_cp}],
            clock={'day': 1, 'time': '23:30'},
            events=[{'group': 'shame_events', 'target': '沈知韫', 'tags': ['内射_常规'], 'evidence': ev_cp}],
            req_id='shame06-mount',
        )
        complete_current_playback(self.svc)
        st_b1, _, _ = save_store.load_bundle(self.tmp)
        buffs1 = st_b1['buffs']['沈知韫']
        self.assertTrue(buffs1, 'SHAME_06/07 must mount a 24-turn persistent buff')
        self.assertEqual(buffs1[0]['turns'], 24)

        run_action_turn(
            self.svc, text='给她盖好薄被', option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': '你拉过薄被盖在她肩头。'}],
            clock={'day': 1, 'time': '23:45'},
            req_id='shame06-tick',
        )
        st_b2, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_b2['buffs']['沈知韫'][0]['turns'], 23)

    # 9. Decision 2 four rule groups deterministic backend enforcement
    def test_09_deterministic_four_rule_groups_mechanics(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'mech-4', opening.SCENARIOS[0]['id'])
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store
        complete_current_playback(self.svc)

        # (9a) Dynamic EXP costs from 互动运行配置.json
        tiers = sp.passive_levels(self.tmp)
        self.assertEqual([t['cost'] for t in tiers], [0, 20, 50, 200, 800])

        # (9b) Nap max once per day (+10) + Insomnia non-stacking (-5) + Overnight +40 stamina for non-insomniac heroines
        st, ly, _ = save_store.load_bundle(self.tmp)
        st['panels']['沈知韫']['体力'] = 50
        st['panels']['苏婉青']['体力'] = 50
        st['panels']['徐念薇']['体力'] = 50
        save_store.save_bundle(self.tmp, st, ly)

        nap_txt = '沈知韫靠在沙发上小憩了一会儿。'
        run_action_turn(
            self.svc, text=nap_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': nap_txt}],
            clock={'day': 1, 'time': '23:10'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['恢复_小憩'], 'evidence': nap_txt}],
            req_id='nap-1',
        )
        complete_current_playback(self.svc)
        st_n1, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_n1['panels']['沈知韫']['体力'], 60)  # +10

        # Second nap same day -> blocked (stays 60!)
        run_action_turn(
            self.svc, text=nap_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': nap_txt}],
            clock={'day': 1, 'time': '23:20'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['恢复_小憩'], 'evidence': nap_txt}],
            req_id='nap-2-blocked',
        )
        complete_current_playback(self.svc)
        st_n2, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_n2['panels']['沈知韫']['体力'], 60)

        # Insomnia twice same night -> only first applies (-5: 60 -> 55), second blocked (stays 55)
        ins_txt = '夜深了，沈知韫辗转反侧难以入睡，整夜失眠。'
        run_action_turn(
            self.svc, text=ins_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ins_txt}],
            clock={'day': 1, 'time': '23:30'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['消耗_日常劳作'], 'evidence': ins_txt}],
            req_id='ins-1',
        )
        complete_current_playback(self.svc)
        st_i1, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_i1['panels']['沈知韫']['体力'], 55)
        self.assertTrue(st_i1['mechanics']['insomnia_applied']['沈知韫'])

        run_action_turn(
            self.svc, text=ins_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ins_txt}],
            clock={'day': 1, 'time': '23:40'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['消耗_日常劳作'], 'evidence': ins_txt}],
            req_id='ins-2-blocked',
        )
        complete_current_playback(self.svc)
        st_i2, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_i2['panels']['沈知韫']['体力'], 55)

        # Overnight sleep -> host=100, non-insomniac 苏婉青/徐念薇 get +40 (50->90), insomniac 沈知韫 stays 55, insomnia_applied reset!
        ov_txt = '夜色沉去，他在卧室安稳睡了一整晚，次日七点醒来。'
        run_action_turn(
            self.svc, text=ov_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ov_txt}],
            clock={'day': 2, 'time': '07:00'},
            sleep={'kind': 'overnight', 'start': {'day': 1, 'time': '23:40'}, 'evidence': ov_txt},
            req_id='overnight-1',
        )
        complete_current_playback(self.svc)
        st_ov, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_ov['panels']['系统宿主']['体力'], 100)
        self.assertEqual(st_ov['panels']['沈知韫']['体力'], 55)
        self.assertEqual(st_ov['panels']['苏婉青']['体力'], 90)
        self.assertEqual(st_ov['panels']['徐念薇']['体力'], 90)
        self.assertFalse(st_ov['mechanics']['insomnia_applied']['沈知韫'])

        # Day 2 nap now succeeds again (55 -> 65)
        run_action_turn(
            self.svc, text=nap_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': nap_txt}],
            clock={'day': 2, 'time': '13:00'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['恢复_小憩'], 'evidence': nap_txt}],
            req_id='nap-day2-ok',
        )
        complete_current_playback(self.svc)
        st_n3, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_n3['panels']['沈知韫']['体力'], 65)

        # (9c) Passive Lv.2 halves C-intensity violation drop (-10 -> -5, stacked with leverage -> -2) & Lv.3 doubles NPC stamina drain
        st_p, ly_p, _ = save_store.load_bundle(self.tmp)
        st_p['panels']['沈知韫']['被动'] = 2
        st_p['panels']['沈知韫']['好感'] = 80
        st_p['panels']['沈知韫']['羞耻'] = 90
        st_p['panels']['沈知韫']['体力'] = 80
        save_store.save_bundle(self.tmp, st_p, ly_p)
        engine = rr._engine(self.tmp, self.tmp)
        aff_lv2 = engine.process_affection_system({}, {'沈知韫': ['C烈度_重度']}, str(self.tmp / rr.FILES[0]))
        self.assertEqual(aff_lv2['沈知韫'], 75)  # -10 * 0.5 = -5
        aff_lv2_lev = engine.process_affection_system(
            {}, {'沈知韫': ['C烈度_重度']}, str(self.tmp / rr.FILES[0]),
            business_leverage=True,
        )
        self.assertEqual(aff_lv2_lev['沈知韫'], 78)  # int(-5 / 2) = -2

        st_p['panels']['沈知韫']['被动'] = 3
        save_store.save_bundle(self.tmp, st_p, ly_p)
        ds_lv3 = engine.process_desire_stamina_system({'沈知韫': ['消耗_剧烈抗拒']}, str(self.tmp / rr.FILES[0]))
        self.assertEqual(ds_lv3['沈知韫']['体力'], 50)  # 80 - (15 * 2) = 50

        # (9d) Deterministic first triggers & homogeneity immunity c_streak across fresh windows
        ev_c1 = '沈知韫被逼到书桌边，呼吸骤乱，这是第一次如此失控。'
        run_action_turn(
            self.svc, text=ev_c1, option_id='C', category='C',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ev_c1}],
            clock={'day': 2, 'time': '13:20'},
            events=[
                {'group': 'shame_events', 'target': '沈知韫', 'tags': ['C烈度_中度', '内射_首次核爆'], 'evidence': ev_c1},
                {'group': 'affection_events', 'target': '沈知韫', 'tags': ['深度操控_首次'], 'evidence': ev_c1},
            ],
            req_id='first-1',
        )
        complete_current_playback(self.svc)
        st_f1, _, _ = save_store.load_bundle(self.tmp)
        self.assertIn('内射', st_f1['mechanics']['first_triggers']['沈知韫'])
        self.assertIn('深度操控', st_f1['mechanics']['first_triggers']['沈知韫'])
        self.assertEqual(st_f1['mechanics']['c_streak']['沈知韫']['count'], 1)

        # Fresh StoryService simulates new Operit window attempting to re-farm first triggers & ignore immunity!
        fresh_svc2 = StoryService(self.tmp)
        ev_c2 = '书房内再度陷入同烈度的压迫与纠缠。'
        run_action_turn(
            fresh_svc2, text=ev_c2, option_id='C', category='C',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ev_c2}],
            clock={'day': 2, 'time': '13:40'},
            events=[
                {'group': 'shame_events', 'target': '沈知韫', 'tags': ['C烈度_中度', '内射_首次核爆'], 'evidence': ev_c2},
                {'group': 'affection_events', 'target': '沈知韫', 'tags': ['深度操控_首次'], 'evidence': ev_c2},
            ],
            req_id='first-2-downgraded',
        )
        complete_current_playback(fresh_svc2)
        snap_f2 = fresh_svc2.interaction_snapshot()
        ev_set2 = snap_f2['settlement']['events']
        self.assertIn('内射_常规', ev_set2['shame_events']['沈知韫'])
        self.assertNotIn('内射_首次核爆', ev_set2['shame_events']['沈知韫'])
        self.assertIn('同质化免疫_回合2', ev_set2['shame_events']['沈知韫'])
        self.assertIn('深度操控_重复', ev_set2['affection_events']['沈知韫'])
        self.assertNotIn('深度操控_首次', ev_set2['affection_events']['沈知韫'])

        # Turn 3 same tier -> auto-appends 同质化免疫_回合3
        run_action_turn(
            fresh_svc2, text=ev_c2, option_id='C', category='C',
            messages=[{'kind': 'narration', 'speaker': '', 'text': ev_c2}],
            clock={'day': 2, 'time': '14:00'},
            events=[{'group': 'shame_events', 'target': '沈知韫', 'tags': ['C烈度_中度'], 'evidence': ev_c2}],
            req_id='first-3-imm3',
        )
        complete_current_playback(fresh_svc2)
        snap_f3 = fresh_svc2.interaction_snapshot()
        self.assertIn('同质化免疫_回合3', snap_f3['settlement']['events']['shame_events']['沈知韫'])

        # (9e) secrets_unlocked auto-adds INTEL-002 + extended guardrail_check on dialogue/action/narration
        st_sec, ly_sec, _ = save_store.load_bundle(self.tmp)
        st_sec['intel']['held'] = ['INTEL-002']
        st_sec['presence']['徐志北']['location'] = '市中心顶层公寓'
        st_sec['presence']['苏婉青']['location'] = '市中心顶层公寓'
        save_store.save_bundle(self.tmp, st_sec, ly_sec)
        ev_i2 = '你拿出对账单与通话记录，平静地挑明了她替徐承邺盯梢的底细。'
        run_action_turn(
            fresh_svc2, text=ev_i2, option_id='B', category='B',
            messages=[{'kind': 'dialogue', 'speaker': '苏婉青', 'text': ev_i2}],
            clock={'day': 2, 'time': '14:30'},
            intel_used={'id': 'INTEL-002', 'target': '苏婉青', 'evidence': ev_i2},
            req_id='intel-002-unlock',
        )
        st_sec2, _, _ = save_store.load_bundle(self.tmp)
        self.assertIn('INTEL-002', st_sec2['mechanics']['secrets_unlocked'])

        # guardrail_check blocks K01 in dialogue, action, and non-inner-thought narration
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], [{'kind': 'dialogue', 'speaker': '苏婉青', 'text': '遗嘱其实把继承权留给了徐志北。'}])
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], [{'kind': 'action', 'speaker': '苏婉青', 'text': '苏婉青盯着遗嘱副本，终于明白真正继承人是徐志北。'}])
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], [{'kind': 'narration', 'speaker': '', 'text': '苏婉青早已知晓遗嘱将公司继承权留给徐志北的真相。'}])
        # Host inner thought narration is allowed (must not raise)
        sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], [{'kind': 'narration', 'speaker': '', 'text': '你心底清楚亡夫遗嘱与继承权的真相，却没有表露分毫。'}])
        # Once 'K01' is in secrets_unlocked, K01 is allowed (must not raise)
        sc.guardrail_check(
            self.tmp, '市中心顶层公寓', ['苏婉青'],
            [{'kind': 'dialogue', 'speaker': '苏婉青', 'text': '遗嘱其实把继承权留给了徐志北。'}],
            secrets_unlocked=['K01'],
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)

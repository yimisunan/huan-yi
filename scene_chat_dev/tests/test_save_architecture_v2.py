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
        self.assertNotIn('系统隐藏标记', ly['episodes'][0]['summary'])
        self.assertEqual(len(st['items']['active']), 1)
        self.assertEqual(st['items']['active'][0]['id'], 'ITEM-002')
        self.assertEqual(len(st['items']['delivered']), 1)
        self.assertEqual(st['items']['delivered'][0]['id'], 'ITEM-001')

        # Persist P3 JSON + one-way views
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

    # 3. v2 three-track memory retrieval: bounded budget, recency & relevance priority, and epistemic partitioning
    def test_03_memory_context_budget_priority_and_recency(self):
        st, ms, _ = save_store.load_bundle(self.tmp)
        ms = save_store.default_memory_store('', prologue_active=False)
        for day_i in range(1, 17):
            ms = save_store.record_memory_turn(
                ms,
                fact=f'第{day_i}天回想层条目{day_i}：主宅书房常规谈话。' + ('丁' * 80),
                day=day_i,
                time_str='20:00',
                location='徐家主宅',
                known_by=['徐志北', '沈知韫'],
                overnight=True,
            )
        ms = save_store.record_memory_turn(
            ms,
            fact='徐志北与沈知韫约定周五晚核对蓝色档案袋。',
            anchor_ops=[{'op': 'add', 'kind': 'promise', 'importance': 5, 'text': '周五晚与沈知韫核对蓝色档案袋', 'private_host': False}],
            day=17,
            time_str='21:00',
            location='徐家主宅',
            known_by=['徐志北', '沈知韫'],
            overnight=True,
        )
        save_store.save_bundle(self.tmp, st, ms)
        view = save_store.retrieve_memory_view(
            ms, cast=['沈知韫'], location='徐家主宅', query='蓝色档案袋核对了吗',
        )
        shared_blob = '\n'.join(view['shared_scene_memory'])
        self.assertLessEqual(len(shared_blob), 2400)
        self.assertIn('蓝色档案袋', shared_blob)
        self.assertIn('条目16', shared_blob)
        self.assertNotIn('条目1：', shared_blob)
        # Epistemic isolation: Su Wanqing was NOT present for Shen Zhiyun's study episodes
        view_su = save_store.retrieve_memory_view(
            ms, cast=['苏婉青'], location='市中心顶层公寓', query='蓝色档案袋',
        )
        self.assertNotIn('蓝色档案袋', '\n'.join(view_su['shared_scene_memory']))
        self.assertIn('蓝色档案袋', '\n'.join(view_su['host_private_memory']))

    # 4. dual_stream_v2 & single_prefix_v2 unconditional chronicle_archive_request + held_intel + zero Stage 1 required_sources
    def test_04_transfer_source_bodies_unconditional_and_empty_fact_safe(self):
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'transfer-init', opening.SCENARIOS[0]['id'])
        self.svc = StoryService(self.tmp)
        self.store = self.svc.store
        complete_current_playback(self.svc)

        st, ms, _ = save_store.load_bundle(self.tmp)
        ms = save_store.default_memory_store('', prologue_active=False)
        for idx in range(1, 26):
            ms = save_store.record_memory_turn(
                ms,
                fact=f'第{idx}幕关键事件：书房对账节点{idx}。',
                day=idx,
                time_str='20:00',
                location='徐家主宅',
                known_by=['徐志北', '沈知韫'],
                overnight=True,
            )
        st['runtime']['memory_round'] = 26
        st['runtime']['last_closed'] = 25
        st['intel']['held'] = ['INTEL-001']
        save_store.save_bundle(self.tmp, st, ms)
        data_p = self.tmp / 'data.json'
        data_obj = json.loads(data_p.read_text(encoding='utf-8'))
        data_obj['story_runtime'] = {**data_obj.get('story_runtime', {}), 'memory_round': 26, 'last_closed': 25}
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

        # Verify single_prefix_v2 real material delivery carries chronicle_archive_request (oldest 8 episodes) + held_intel
        mat_single = self.svc.material('xfer-req-1', {
            'lease': task['lease'],
            'chat_id': 'chat-single',
            'participant_id': 'card-1',
            'delivery_version': 2,
            'protocol_mode': 'single_prefix_v2',
            'is_fresh_session': True,
        })
        delta_single = mat_single['input_text']
        self.assertIn('chronicle_archive_request', delta_single)
        self.assertIn('书房对账节点1', delta_single)
        self.assertIn('书房对账节点8', delta_single)
        self.assertIn('INTEL-001', delta_single)

        # Cancel xfer-req-1, create xfer-req-2, and verify dual_stream_v2 puts chronicle_archive_request in Stage 2 ONLY & zero required_sources
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
        self.assertNotIn('required_sources', mat_dual['input_text'])
        self.assertNotIn('chronicle_archive_request', mat_dual['input_text'])
        spec_text = json.dumps(mat_dual['settlement_spec'], ensure_ascii=False)
        self.assertIn('chronicle_archive_request', spec_text)
        self.assertIn('书房对账节点1', spec_text)
        self.assertIn('书房对账节点8', spec_text)
        self.assertNotIn('required_sources', spec_text)

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
        self.assertEqual([t['cost'] for t in tiers], [0, 20, 50, 110, 220])

        # (9b) Nap max once per day (+15) + Insomnia non-stacking (-5) + Overnight +40 stamina for non-insomniac heroines
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
        self.assertEqual(st_n1['panels']['沈知韫']['体力'], 65)  # +15

        # Second nap same day -> blocked (stays 65!)
        run_action_turn(
            self.svc, text=nap_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': nap_txt}],
            clock={'day': 1, 'time': '23:20'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['恢复_小憩'], 'evidence': nap_txt}],
            req_id='nap-2-blocked',
        )
        complete_current_playback(self.svc)
        st_n2, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_n2['panels']['沈知韫']['体力'], 65)

        # Insomnia twice same night -> only first applies (-5: 65 -> 60), second blocked (stays 60)
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
        self.assertEqual(st_i1['panels']['沈知韫']['体力'], 60)
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
        self.assertEqual(st_i2['panels']['沈知韫']['体力'], 60)

        # Overnight sleep -> host=100, non-insomniac 苏婉青/徐念薇 get +40 (50->90), insomniac 沈知韫 stays 60, insomnia_applied reset!
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
        self.assertEqual(st_ov['panels']['沈知韫']['体力'], 60)
        self.assertEqual(st_ov['panels']['苏婉青']['体力'], 90)
        self.assertEqual(st_ov['panels']['徐念薇']['体力'], 90)
        self.assertFalse(st_ov['mechanics']['insomnia_applied']['沈知韫'])

        # Day 2 nap now succeeds again (60 -> 75)
        run_action_turn(
            self.svc, text=nap_txt, option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': nap_txt}],
            clock={'day': 2, 'time': '13:00'},
            events=[{'group': 'ds_events', 'target': '沈知韫', 'tags': ['恢复_小憩'], 'evidence': nap_txt}],
            req_id='nap-day2-ok',
        )
        complete_current_playback(self.svc)
        st_n3, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_n3['panels']['沈知韫']['体力'], 75)

        # (9c) Passive Lv.2 halves C-intensity violation drop (intact_defense stays active until Lv.4; 75% mitigation cap), Lv.4 exempts intact_defense, Lv.3 doubles NPC stamina drain
        st_p, ly_p, _ = save_store.load_bundle(self.tmp)
        st_p['panels']['沈知韫']['被动'] = 2
        st_p['panels']['沈知韫']['好感'] = 80
        st_p['panels']['沈知韫']['羞耻'] = 90
        st_p['panels']['沈知韫']['堕落'] = 0
        st_p['panels']['沈知韫']['体力'] = 80
        save_store.save_bundle(self.tmp, st_p, ly_p)
        engine = rr._engine(self.tmp, self.tmp)
        aff_lv2 = engine.process_affection_system({}, {'沈知韫': ['C烈度_重度']}, str(self.tmp / rr.FILES[0]))
        self.assertEqual(aff_lv2['沈知韫'], 73)  # intact_defense -> raw -15, Lv.2 *0.5 -> -7
        aff_lv2_lev = engine.process_affection_system(
            {}, {'沈知韫': ['C烈度_重度']}, str(self.tmp / rr.FILES[0]),
            business_leverage=True,
        )
        self.assertEqual(aff_lv2_lev['沈知韫'], 76)  # stacked Lv.2 + leverage capped at 75% mitigation -> -4
        st_p['panels']['沈知韫']['被动'] = 4
        save_store.save_bundle(self.tmp, st_p, ly_p)
        aff_lv4 = engine.process_affection_system({}, {'沈知韫': ['C烈度_重度']}, str(self.tmp / rr.FILES[0]))
        self.assertEqual(aff_lv4['沈知韫'], 75)  # Lv.4 exempts intact_defense -> raw -10, Lv.2+ *0.5 -> -5

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

    def test_10_workstream_2b_and_3_regressions(self):
        # 1. mechanics.charm_scene_used persists across save_store.normalize_state & save_bundle round-trip
        st, ly, _ = save_store.load_bundle(self.tmp)
        st['mechanics']['charm_scene_used'] = True
        save_store.save_bundle(self.tmp, st, ly)
        st2, _, _ = save_store.load_bundle(self.tmp)
        self.assertIs(st2['mechanics'].get('charm_scene_used'), True)

        # 2. Xu Nianwei default stamina is 100 in default_state()
        self.assertEqual(save_store.default_state()['panels']['徐念薇']['体力'], 100)

        # 3. Round 1 memory_merge replaces literary prologue when prologue_active=True
        merged = sp.memory_merge(
            self.tmp,
            {'L1': ['【1】周日午间阳光漫过主宅长桌的文学序幕。'], 'L2': [], 'L3': [], 'L4': []},
            1, {'day': 1, 'time': '12:15'},
            {'fact': '沈知韫递来深圳分部对账底稿并约明早七点餐桌核对。', 'compact': ''},
            prologue_active=True,
        )
        self.assertEqual(merged, '第1天 12:15 沈知韫递来深圳分部对账底稿并约明早七点餐桌核对。')

        # 4. derive_weekday reads save_state runtime prologue weekday even when data.json is empty
        st_day = save_store.default_state()
        st_day['runtime']['prologue'] = {'weekday': '周日'}
        self.assertEqual(sp.derive_weekday({}, '', {'day': 1, 'time': '12:00'}, save_state=st_day), '周日')
        self.assertEqual(sp.derive_weekday({}, '', {'day': 2, 'time': '09:00'}, save_state=st_day), '周一')

        # 5. Shen Zhiyun overtime exemption preserves 公司 location after 16:00 when reason notes 加班
        st_ot, ly_ot, _ = save_store.load_bundle(self.tmp)
        st_ot['presence']['徐志北'] = {'location': '市中心顶层公寓', 'reason': '探望'}
        st_ot['presence']['沈知韫'] = {'location': '公司', 'reason': '留公司加班复核并购条款'}
        save_store.save_bundle(self.tmp, st_ot, ly_ot)
        mem_path = self.tmp / save_store.RENDERED_MEMORY_PATH
        from unittest import mock
        with mock.patch.object(ic, 'MEMORY_FILE', str(mem_path)):
            moves_ot = sp.reconcile_offstage_presence(
                ic, mem_path, {'day': 1, 'time': '18:30'}, '周二', '市中心顶层公寓', player_moved=True,
            )
            self.assertFalse(any(m['name'] == '沈知韫' for m in moves_ot))
            moves_overnight = sp.reconcile_offstage_presence(
                ic, mem_path, {'day': 2, 'time': '07:00'}, '周三', '市中心顶层公寓', overnight=True, day_crossed=True,
            )
            self.assertTrue(any(m['name'] == '沈知韫' and m['to'] == '徐家主宅' for m in moves_overnight))

        # 6. VIGILANCE_EXPOSURE_TAGS covers 外射/私密自渎 + ds_events 高潮/自慰
        self.assertTrue(ic._is_exposed('苏婉青', {'苏婉青': ['外射_体表面部']}, None))
        self.assertTrue(ic._is_exposed('苏婉青', {'苏婉青': ['意外撞破_私密自渎']}, None))
        self.assertTrue(ic._is_exposed('苏婉青', None, {'苏婉青': ['触发高潮_绝顶清算']}))
        self.assertTrue(ic._is_exposed('苏婉青', None, {'苏婉青': ['自慰_暗中纾解']}))
        self.assertFalse(ic._is_exposed('苏婉青', {'苏婉青': ['心理破冰_暧昧试探']}, None))

        # 7. Auto-climax (new_org >= 100 without explicit DS_17) reports auto_climax via climax_out
        climax_set = set()
        org_path = self.tmp / '_test_org_mem.txt'
        org_path.write_text(
            '[沈知韫] 好感 80 | 堕落 20 | 欲望 80 | 羞耻 40 | 体力 90 | 高潮 85% | 内射 0次 | 怀孕 False | 被动 Lv.0\n',
            encoding='utf-8',
        )
        ic.process_desire_stamina_system(
            {'沈知韫': ['高潮_中度累积']}, str(org_path), climax_out=climax_set,
        )
        self.assertIn('沈知韫', climax_set)

        # 8. Opening box fixes: zhiyun_sunday_noon starts at 12:00 & Xu Nianwei opening task targets <= 35
        self.assertEqual(opening.OPENING_TIMES['zhiyun_sunday_noon'], ('周日', '12:00'))
        for sid, task_def in opening.OPENING_TASKS.items():
            if task_def.get('target') == '徐念薇' and task_def.get('attr') == '好感':
                self.assertLessEqual(task_def['value'], 35, f'{sid} Xu Nianwei task value too high: {task_def}')

    # 11. P3 three-track memory_store 500-turn stress, epistemic/K01 hard isolation, O(1) GC, and Gemini 4 cache lock
    def test_11_v3_three_track_500_turn_stress_and_gemini4_cache_lock(self):
        # A. 500-turn three-track simulation
        ms = save_store.default_memory_store('', prologue_active=False)
        # Turn 1a: permanent high-importance promise anchor (known ONLY by host + Shen Zhiyun)
        ms = save_store.record_memory_turn(
            ms,
            fact='徐志北与沈知韫在书房约定：下周五一起核对旧账并保密。',
            anchor_ops=[
                {'op': 'add', 'kind': 'promise', 'importance': 5, 'text': '下周五与沈知韫核对深圳旧账并保密', 'private_host': False},
            ],
            day=1,
            time_str='21:00',
            location='徐家主宅',
            sub_location='二楼书房',
            known_by=['徐志北', '沈知韫'],
            secrets_unlocked=(),
        )
        # Turn 1b: K01 secret guard check (even if 苏婉青/徐志北 are passed in known_by, K01 lock strips them)
        ms = save_store.record_memory_turn(
            ms,
            fact='',
            anchor_ops=[
                {'op': 'add', 'kind': 'secret', 'importance': 5, 'text': '老宅真遗嘱与亲生血缘绝密线索', 'private_host': False},
            ],
            day=1,
            time_str='21:05',
            location='徐家主宅',
            sub_location='二楼书房',
            known_by=['徐志北', '沈知韫', '苏婉青'],
            secrets_unlocked=(),
        )
        # K01 secret guard must strip unauthorized witnesses (苏婉青 / 徐志北) when K01 is locked
        k01_anchor = next(a for a in ms['anchors'] if '遗嘱' in a['text'])
        self.assertEqual(k01_anchor['known_by'], ['沈知韫'])

        # Simulate 500 turns across rotating days/locations/casts, piggybacking chronicle_digest whenever >= 24 episodes
        locs = [
            ('徐家主宅', ['徐志北', '沈知韫']),
            ('市中心顶层公寓', ['徐志北', '苏婉青']),
            ('工作室', ['徐志北', '徐念薇']),
        ]
        for turn in range(2, 502):
            day_i = 1 + (turn // 5)
            loc_name, witnesses = locs[turn % 3]
            digest = None
            if save_store.needs_chronicle_archive(ms):
                digest = {
                    'public': f'第{day_i}日前多幕纪要：徐志北往返主宅、公寓与画室推进关系与账目调查。',
                    'views': {'沈知韫': f'书房私密进展至第{turn}轮。', '苏婉青': f'公寓私下照料至第{turn}轮。'},
                }
            a_ops = []
            if turn % 20 == 0:
                a_ops.append({'op': 'add', 'kind': 'clue', 'importance': 3, 'text': f'第{turn}轮阶段线索记录', 'private_host': False})
            ms = save_store.record_memory_turn(
                ms,
                fact=f'第{turn}轮因果变化：在{loc_name}推进具体对话与安排。',
                anchor_ops=a_ops,
                chronicle_digest=digest,
                day=day_i,
                time_str=f'{(8 + (turn % 14)):02d}:{(turn * 7) % 60:02d}',
                location=loc_name,
                known_by=witnesses,
                overnight=(turn % 5 == 0),
                secrets_unlocked=(),
            )

        # Verify bounded size & permanent anchor survival after 500 turns
        self.assertLessEqual(len(ms['anchors']), save_store.MAX_ACTIVE_ANCHORS)
        self.assertLessEqual(len(ms['resolved_anchors']), save_store.MAX_RESOLVED_ANCHORS)
        self.assertLessEqual(len(ms['episodes']), save_store.HARD_MAX_EPISODES)
        self.assertLessEqual(len(ms['chronicle']), save_store.MAX_CHRONICLE_CHAPTERS)
        raw_bytes = save_store._json_bytes(ms)
        self.assertLess(len(raw_bytes), 45000, f'memory_store.json bloated after 500 turns: {len(raw_bytes)}B')
        self.assertTrue(any('核对深圳旧账并保密' in a['text'] for a in ms['anchors']), 'Turn-1 permanent anchor lost!')

        # Verify epistemic partitioning & bounded injection at Turn 500
        view_szy = save_store.retrieve_memory_view(
            ms, cast=['沈知韫'], location='徐家主宅', query='深圳旧账核对',
        )
        view_swq = save_store.retrieve_memory_view(
            ms, cast=['苏婉青'], location='市中心顶层公寓', query='深圳旧账核对',
        )
        self.assertIn('核对深圳旧账并保密', '\n'.join(view_szy['shared_scene_memory']))
        self.assertNotIn('核对深圳旧账并保密', '\n'.join(view_swq['shared_scene_memory']))
        self.assertIn('核对深圳旧账并保密', '\n'.join(view_swq['host_private_memory']))
        total_view_chars = (
            sum(len(x) for x in view_szy['shared_scene_memory'])
            + sum(len(x) for x in view_szy['host_private_memory'])
            + sum(sum(len(y) for y in v) for v in view_szy['actor_private_memory'].values())
        )
        self.assertLessEqual(total_view_chars, 3200)

        # B. O(1) tasks.json pruning & runtime blob GC
        fake_tasks = {
            'version': 1,
            'latest': 'req-499',
            'bridge_seen': 0,
            'jobs': {
                f'req-{i}': {
                    'request_id': f'req-{i}',
                    'status': 'committed' if i < 499 else 'running',
                    'created': float(i),
                    'reservation': {
                        'status': 'settled' if i < 499 else 'held',
                        'before_memory': 'X' * 10000,
                        'before_save_state': 'Y' * 10000,
                        'quote': {'total': 5},
                    },
                }
                for i in range(500)
            },
        }
        sp.prune_tasks_state(fake_tasks)
        self.assertLessEqual(len(fake_tasks['jobs']), sp.MAX_TERMINAL_JOBS + 1)
        self.assertIn('req-499', fake_tasks['jobs'])
        self.assertIn('before_memory', fake_tasks['jobs']['req-499']['reservation'])
        for jid, job in fake_tasks['jobs'].items():
            if jid != 'req-499':
                self.assertNotIn('before_memory', job['reservation'])
                self.assertNotIn('before_save_state', job['reservation'])
        self.assertLess(len(json.dumps(fake_tasks, ensure_ascii=False)), 35000)

        # Orphan cache GC keeps <= 3 recent requests
        with self.store._locked():
            opening.initialize_prologue(self.tmp, 'gc-init', opening.SCENARIOS[0]['id'])
        svc = StoryService(self.tmp)
        reading_root = self.tmp / 'txt文件/.story-reading'
        story_root = self.tmp / '.round-runtime/story'
        reading_root.mkdir(parents=True, exist_ok=True)
        story_root.mkdir(parents=True, exist_ok=True)
        for idx in range(10):
            (reading_root / f'{idx:032x}').mkdir(exist_ok=True)
            (reading_root / f'{idx:032x}' / 'probe.txt').write_text('x', encoding='utf-8')
            (story_root / f'{idx:064x}.context.json').write_text('{}', encoding='utf-8')
        svc._gc_runtime_artifacts({'jobs': {}}, keep_recent=3)
        self.assertLessEqual(len([p for p in reading_root.iterdir() if p.is_dir()]), 3)
        self.assertLessEqual(len(list(story_root.glob('*.context.json'))), 3)

        # C. Gemini 4 implicit KV cache stability lock: mid-scene calm desire (0->50) & vigilance (0->15) keep Zone 0 + Zone 1 byte-identical
        st0, ly0, _ = save_store.load_bundle(self.tmp)
        mem0 = save_store.render_memory_txt(st0, ly0)
        view0 = ir.view(svc.store)
        z0_a = sc.build_zone0_global(self.tmp, mode='dual_stream_v2')
        z1_a = sc.build_zone1_scene(self.tmp, view0, view0['cast'], (), memory_text=mem0, mode='dual_stream_v2')

        st1 = copy.deepcopy(st0)
        st1['panels']['沈知韫']['欲望'] = 50
        st1['vigilance']['目标']['沈知韫']['警惕'] = 15
        mem1 = save_store.render_memory_txt(st1, ly0)
        view1 = dict(view0)
        view1['panels'] = [
            re.sub(r'欲望\s+\d+', '欲望 50', p) if p.startswith('[沈知韫]') else p
            for p in view0['panels']
        ]
        z0_b = sc.build_zone0_global(self.tmp, mode='dual_stream_v2')
        z1_b = sc.build_zone1_scene(self.tmp, view1, view1['cast'], (), memory_text=mem1, mode='dual_stream_v2')
        self.assertEqual(z0_a, z0_b)
        self.assertEqual(z1_a, z1_b, 'Zone 1 prefix drifted during calm mid-scene desire(0->50)/vigilance(0->15) change!')
        self.assertLess(len(z0_a), 9200)
        self.assertLess(len(z1_a), 6800)


if __name__ == '__main__':
    unittest.main(verbosity=2)

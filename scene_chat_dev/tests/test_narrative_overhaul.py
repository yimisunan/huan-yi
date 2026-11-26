"""Comprehensive automated tests for the Narrative System Overhaul (T1-T7).
Runs strictly inside isolated temporary copies; never modifies live save files.
"""
import json
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import injection_core as ic
import interaction_runtime as ir
import round_runtime as rr
import story_compiler as sc
import story_progression as sp
import story_service as ss
from test_phase_ab_linkage import (
    complete_current_playback,
    make_isolated_workspace,
    reset_clean_save,
    run_action_turn,
)


class FixedRng:
    def __init__(self, values):
        self._vals = list(values)
        self._idx = 0

    def random(self):
        v = self._vals[self._idx % len(self._vals)]
        self._idx += 1
        return v


class NarrativeOverhaulTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_isolated_workspace()
        self.svc = ss.StoryService(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _begin_game(self, *, time_str='09:30', decision=None):
        snap = self.svc.interaction_snapshot()
        sp.create(self.svc, {
            'request_id': 'begin-0',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'action': '继续当前剧情',
            'entry_mode': ir.MODE,
            'operation': None,
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
            'model_key': None,
        })
        tasks = self.svc._read()
        job = tasks['jobs']['begin-0']
        job['status'] = 'validating'
        self.svc._write(tasks)
        dec = decision or {
            'prompt': '客厅里安静下来，你准备如何继续？',
            'options': [
                {'id': 'A', 'text': '问问今天家里的安排'},
                {'id': 'B', 'text': '顺手帮她递过茶杯'},
                {'id': 'C', 'text': '直接试探她的真实想法'},
            ],
        }
        payload = {
            'schema_version': 3,
            'entry_mode': ir.MODE,
            'request_id': 'begin-0',
            'base_revision': job['working_revision'],
            'input': '继续当前剧情',
            'messages': [{'kind': 'narration', 'speaker': '', 'text': '清晨阳光照进客厅，茶杯边腾起细薄水汽。'}],
            'decision': dec,
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
            'operation': None,
            'handoff': '',
            'resolution': {
                'category': 'SYSTEM',
                'basis': '开场推进',
                'clock': {'day': 1, 'time': time_str, 'basis': '初始化时刻'},
                'events': [],
                'memory': {'fact': '', 'transfers': {}, 'compact': ''},
                'conditions': None,
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
                'task': None,
                'items': [],
            },
            'audit': {
                'required_reads_verified': True,
                'origin': 'model',
                'reservation': job['reservation'],
            },
        }
        return self.svc.store.submit(payload)

    def test_T1_zone0_cleanliness_and_lifted_length_limits(self):
        z0 = sc.build_zone0_global(self.tmp, mode='dual_stream_v2')
        for forbidden in (
            '120字硬顶',
            '只有完整回合兼容入口才在其末尾呈现选项',
            '约6～12个节点',
            '350～650字',
            '体液来处去处',
        ):
            self.assertNotIn(forbidden, z0)
        for required in ('一幕一位移', '[MOVE:', 'surprise_directive', '4000字'):
            self.assertIn(required, z0)

        # Verify SKILL.md was removed from repository root after integration.
        self.assertFalse((REPO / 'SKILL.md').exists(), 'Root SKILL.md should be deleted after integration')

        # 1500-char narration and dialogue pass parse_stream_story (partial + full)
        long_n = '书桌上的灯影微微晃动，' * 140  # 1540 chars
        long_d = '我今天确实还有几份对账单没看完，' * 95  # 1520 chars
        self.assertGreater(len(long_n), 1500)
        self.assertGreater(len(long_d), 1500)
        raw = (
            f'[N] {long_n}\n'
            f'[D:沈知韫] {long_d}\n'
            '---DECISION---\n'
            'PROMPT: 书桌上的账单还摊开着，你决定怎么接话？\n'
            'A: 顺着账单询问深圳分部近况\n'
            'B: 替她续上一杯温水并靠近桌沿\n'
            'C: 直接翻看桌角露出一半的回执\n'
        )
        part = sc.parse_stream_story(raw, allowed_speakers=['沈知韫'], partial=True)
        self.assertEqual(len(part['messages']), 2)
        full = sc.parse_stream_story(raw, allowed_speakers=['沈知韫'], partial=False)
        self.assertEqual(len(full['messages']), 2)
        self.assertEqual(len(full['messages'][0]['text']), len(long_n))

        # Verify full RoundStore / interaction_runtime.validate accepts 1500-char messages
        self._begin_game()
        run_action_turn(
            self.svc, text='问问今天家里的安排', option_id='A', category='A',
            messages=full['messages'], clock={'day': 1, 'time': '09:45'}, req_id='long-node-1',
        )

        # Verify Operit bridge JS parseStreamMessages also accepts 1500-char messages without dropping them
        js_code = (
            "const fs = require('fs');"
            "const src = fs.readFileSync('scene_chat_dev/local.story.operit_bridge/main.js', 'utf8');"
            "const start = src.indexOf('const STREAM_TAG_RE');"
            "const end = src.indexOf('function normalizeSettlementJson');"
            "const fn = new Function(src.slice(start, end) + '; return parseStreamMessages;')();"
            "const longN = '书桌上的灯影微微晃动，'.repeat(140);"
            "const longD = '我今天确实还有几份对账单没看完，'.repeat(95);"
            "const out = fn('[N] ' + longN + '\\n[D:沈知韫] ' + longD + '\\n---DECISION---\\n', ['沈知韫'], true);"
            "console.log(JSON.stringify({count: out.length, len0: out[0]?.text.length || 0, len1: out[1]?.text.length || 0}));"
        )
        proc = subprocess.run(['node', '-e', js_code], cwd=str(REPO), capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res['count'], 2)
        self.assertEqual(res['len0'], len(long_n))
        self.assertEqual(res['len1'], len(long_d))

    def test_T2_intimate_dual_channel_gating(self):
        mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        state = ir.view(self.svc.store)
        runtime = sp.state(self.svc.store.root, self.svc.store._files())
        proj = ir.memory_context(self.tmp, mem, '聊几句天气', runtime)

        z0 = sc.build_zone0_global(self.tmp, mode='dual_stream_v2')
        z1_calm = sc.build_zone1_scene(self.tmp, state, state['cast'], (), memory_text=mem, mode='dual_stream_v2')
        self.assertNotIn('narrative.intimate', z0)
        self.assertNotIn('本场激活亲密', z1_calm)

        # Calm A turn incremental delta: no intimate guide, and strictly < 3000 chars
        delta_a_str = sc.build_user_delta(
            self.tmp, state, proj, [], [], '聊几句今天天气',
            {'segment_id': 's1', 'option_id': 'A'}, None, None,
            {'before': 100, 'kind': 'action'}, runtime, mem,
            include_full_anchor=False, mode='dual_stream_v2',
        )
        delta_a = json.loads(delta_a_str)
        self.assertNotIn('intimate_craft_guide', delta_a)
        self.assertLess(len(delta_a_str), 3000)

        # C turn in calm state: Zone 1 SHA-256 unchanged, Zone 2 delta injects intimate_craft_guide
        z1_after_c = sc.build_zone1_scene(self.tmp, state, state['cast'], (), memory_text=mem, mode='dual_stream_v2')
        self.assertEqual(sc._digest_text(z1_calm), sc._digest_text(z1_after_c))
        delta_c_str = sc.build_user_delta(
            self.tmp, state, proj, [], [], '伸手揽住她的腰吻下去',
            {'segment_id': 's1', 'option_id': 'C'}, None, None,
            {'before': 100, 'kind': 'action'}, runtime, mem,
            include_full_anchor=False, mode='dual_stream_v2',
        )
        delta_c = json.loads(delta_c_str)
        self.assertIn('intimate_craft_guide', delta_c)
        self.assertIn('体液', delta_c['intimate_craft_guide'])

        # Persistent high desire (>= 60): enters Zone 1 and is NOT duplicated in Zone 2 delta
        hot_panels = [
            re.sub(r'欲望\s+\d+', '欲望 68', p) if p.startswith('[沈知韫]') else p
            for p in state['panels']
        ]
        hot_state = {**state, 'panels': hot_panels}
        z1_hot = sc.build_zone1_scene(self.tmp, hot_state, hot_state['cast'], (), memory_text=mem, mode='dual_stream_v2')
        self.assertIn('本场激活亲密', z1_hot)
        delta_hot = json.loads(sc.build_user_delta(
            self.tmp, hot_state, proj, [], [], '进一步试探',
            {'segment_id': 's1', 'option_id': 'C'}, None, None,
            {'before': 100, 'kind': 'action'}, runtime, mem,
            include_full_anchor=False, mode='dual_stream_v2',
        ))
        self.assertNotIn('intimate_craft_guide', delta_hot)

    def test_T3_shame03_and_xu_chengye_fixes(self):
        engine = rr._engine(self.tmp, self.tmp)
        mem_path = self.tmp / rr.FILES[0]
        base_mem = mem_path.read_text(encoding='utf-8')

        def run_shame03(aff, shame, leverage=False):
            m = engine._simulate_panel(base_mem, {'沈知韫': {'好感': aff, '羞耻': shame}})
            mem_path.write_text(m, encoding='utf-8')
            meta = {}
            d = engine.process_affection_system(
                {}, {'沈知韫': ['C烈度_深度']}, str(mem_path),
                business_leverage=leverage, leverage_meta=meta,
            )
            val = d.get('沈知韫', aff)
            new_aff = val.get('好感', aff) if isinstance(val, dict) else int(val)
            return new_aff - aff, meta

        # High aff (70) + low shame (30) -> rationalization loop (0 drop)
        delta_rat, _ = run_shame03(70, 30)
        self.assertEqual(delta_rat, 0)
        # High aff (70) + high shame (60) -> -7
        self.assertEqual(run_shame03(70, 60)[0], -7)
        # Mid aff (40) -> -9
        self.assertEqual(run_shame03(40, 60)[0], -9)
        # Low aff (25 < 30) -> -16; with commercial leverage -> halved (-8)
        self.assertEqual(run_shame03(25, 60)[0], -16)
        delta_lev, lev_meta = run_shame03(25, 60, leverage=True)
        self.assertEqual(delta_lev, -8)
        self.assertTrue(lev_meta.get('applied'))

        # Restore clean memory before full service transaction test
        mem_path.write_text(base_mem, encoding='utf-8')

        # Xu Chengye in conditions.npc and transfer_item when present at 徐家主宅
        self._begin_game()
        mem = mem_path.read_text(encoding='utf-8').replace('徐承邺位置：外地', '徐承邺位置：徐家主宅')
        mem_path.write_text(mem, encoding='utf-8')
        self.assertIn('徐承邺', ir.view(self.svc.store)['cast'])

        # Add a transferable item to active catalog via engine
        rr._engine_call(engine.update_item_catalog, 0, [{
            'name': '温润茶礼', 'type': '永久性', 'quantity': 1, 'target': '未使用', 'location': '徐志北',
        }])
        files_now = self.svc.store._files()
        op_xfer = {'code': 'transfer_item', 'item_id': 'ITEM-001', 'recipient': '徐承邺'}
        self.assertEqual(ir.operation(self.tmp, files_now, op_xfer, '把整组温润茶礼交给徐承邺', explicit=True), op_xfer)

        run_action_turn(
            self.svc, text='和徐承邺寒暄两句', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '徐承邺', 'text': '难得今天都在家，坐吧。'}],
            clock={'day': 1, 'time': '09:50'},
            conditions={'intensity': 'A', 'effective_progress': True, 'scene': '徐家主宅', 'npc': '徐承邺',
                        'action_changed': True, 'stress_signals': 0, 'breakout_triggered': []},
            req_id='xcy-npc-1',
        )

        # Apartment vigilance roll: high vigilance on 苏婉青 at 市中心顶层公寓
        mem_apt = re.sub(r'徐承邺_苏婉青[：:]\s*警惕\s*\d+\s*\|\s*发现\s*\d+(?:\s*\|\s*发现几率\s*\d+)?',
                         '徐承邺_苏婉青：警惕 60 | 发现 0 | 发现几率 0', base_mem)
        mem_path.write_text(mem_apt, encoding='utf-8')
        orig_random = engine.random.random
        try:
            engine.random.random = lambda: 0.01  # always triggers return & apartment check
            summary = engine.process_vigilance_system({}, {}, str(mem_path), elapsed_hours=0, roll_home=True)
        finally:
            engine.random.random = orig_random
        self.assertEqual(summary.get('徐承邺位置'), '市中心顶层公寓')
        mem_after = mem_path.read_text(encoding='utf-8')
        self.assertIn('徐承邺位置：市中心顶层公寓', mem_after)
        pres = engine.parse_presence_from_memory(mem_after)
        self.assertIn('徐承邺', ir.scene_cast(pres, mem_after, '市中心顶层公寓'))
        prob_m = re.search(r'徐承邺_苏婉青[：:]\s*警惕\s*\d+\s*\|\s*发现\s*\d+\s*\|\s*发现几率\s*(\d+)', mem_after)
        self.assertIsNotNone(prob_m)
        self.assertGreater(int(prob_m.group(1)), 0)

    def test_T4_studio_schedule_and_aliases(self):
        aliases = ir.location_aliases(self.tmp)
        self.assertEqual(aliases.get('画室'), '工作室')
        self.assertEqual(aliases.get('校外画室'), '工作室')
        self.assertEqual(aliases.get('念薇画室'), '工作室')

        engine = rr._engine(self.tmp, self.tmp)
        mem_path = self.tmp / rr.FILES[0]
        base_mem = mem_path.read_text(encoding='utf-8')
        # Player at 公司 (offstage from 徐念薇)
        p_mem = re.sub(r'(徐志北：)[^\n]+', r'\1公司（处理事务）', base_mem)
        mem_path.write_text(p_mem, encoding='utf-8')

        # Workday 14:00 -> 大学
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '14:00'}, '周三', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '大学')

        # Workday 18:30 & 21:00 -> 工作室
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '18:30'}, '周三', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '工作室')
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '21:00'}, '周五', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '工作室')

        # Workday 22:30 & Saturday 10:00 -> 徐家主宅
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '22:30'}, '周五', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '徐家主宅')

        # Move back to studio at 18:30, then Saturday 10:00 -> 徐家主宅
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '18:30'}, '周五', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '工作室')
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 2, 'time': '10:00'}, '周六', '公司')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '徐家主宅')

        # Co-present at 工作室 at 22:30 -> NEVER teleported away!
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '18:30'}, '周三', '公司')
        co_mem = re.sub(r'(徐志北：)[^\n]+', r'\1工作室（看画）', mem_path.read_text(encoding='utf-8'))
        mem_path.write_text(co_mem, encoding='utf-8')
        sp.reconcile_offstage_presence(engine, mem_path, {'day': 1, 'time': '22:30'}, '周三', '工作室')
        self.assertEqual(engine.parse_presence_from_memory(mem_path.read_text(encoding='utf-8'))['徐念薇']['location'], '工作室')

    def test_T5_entropy_rng_director_two_beat_and_idempotency(self):
        base_mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        state = {'location': '市中心顶层公寓', 'cast': ['苏婉青']}
        runtime = {'clock': {'day': 1, 'time': '14:00'}}

        # Monotonic stagnation curve and hard cap at 0.85
        probs = []
        for streak in range(6):
            m = sp.write_director_block(base_mem, {'calm_streak': streak, 'scene_location': '市中心顶层公寓', 'scene_turns': 1})
            r = sp.roll_director_beat(self.tmp, state, m, runtime, '周三', rng=FixedRng([0.99]))
            probs.append(r['probability'])
        self.assertEqual(probs, sorted(probs))
        self.assertGreater(probs[-1], probs[0])
        self.assertLessEqual(probs[-1], 0.85)

        # Both world global_cooldown and decoupled heroine_cd on cooldown -> prob = 0.0
        m_cd = sp.write_director_block(base_mem, {'calm_streak': 5, 'global_cooldown': 1, 'heroine_cd': 1})
        r_cd = sp.roll_director_beat(self.tmp, state, m_cd, runtime, '周三', rng=FixedRng([0.0]))
        self.assertFalse(r_cd['triggered'])
        self.assertEqual(r_cd['probability'], 0.0)

        # Two-beat seed planting -> aging -> detonation & consumption
        m_seed = sp.advance_director_state(
            self.tmp, base_mem, location='市中心顶层公寓',
            director_roll={
                'triggered': True, 'tier': 'tier1', 'event_id': 'BEAT-APT-01',
                'seed_to_add': {'seed_id': 'SEED-APT-GIFT', 'summary': '玄关放着徐承邺秘书错寄的礼盒'},
                'seed_consumed': None, 'cooldown': 8, 'once': False,
            },
            effective_progress=False, had_events=False, memory_fact='',
        )
        self.assertEqual(len(sp.parse_director_block(m_seed)['pending_seeds']), 1)
        # Age seed 2 turns
        for _ in range(2):
            m_seed = sp.advance_director_state(
                self.tmp, m_seed, location='市中心顶层公寓', director_roll={'triggered': False},
                effective_progress=False, had_events=False, memory_fact='',
            )
        ds = sp.parse_director_block(m_seed)
        self.assertEqual(ds['pending_seeds'][0]['age'], 2)

        # Trigger detonation consuming SEED-APT-GIFT
        m_det = sp.advance_director_state(
            self.tmp, m_seed, location='市中心顶层公寓',
            director_roll={
                'triggered': True, 'tier': 'tier2', 'event_id': 'BEAT-APT-03',
                'seed_to_add': None, 'seed_consumed': 'SEED-APT-GIFT', 'cooldown': 8, 'once': False,
            },
            effective_progress=True, had_events=False, memory_fact='徐承邺发来语音追问礼盒去向。',
        )
        ds_after = sp.parse_director_block(m_det)
        self.assertEqual(ds_after['pending_seeds'], [])
        self.assertEqual(ds_after['global_cooldown'], 1)
        self.assertEqual(ds_after['calm_streak'], 0)

        # _project_memory_header strips 【世界导演状态】 and keeps header compact (< 1400 chars)
        raw_header = m_det.split('▲ 第一层：', 1)[0]
        projected_header = ir._project_memory_header(raw_header)
        self.assertNotIn('【世界导演状态】', projected_header)
        self.assertLess(len(projected_header), 1400)

        # Retry idempotency: frozen director_roll in .context.json survives retry, and cancel never pollutes memory
        self._begin_game()
        complete_current_playback(self.svc)
        snap = self.svc.interaction_snapshot()
        row = ir.segment(self.svc.store.root, self.svc.store._files())
        mem_before = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        sp.create(self.svc, {
            'request_id': 'idemp-roll-1',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'action': row['decision']['options'][0]['text'],
            'entry_mode': ir.MODE,
            'operation': None,
            'selection': {'segment_id': row['id'], 'option_id': 'A'},
            'model_key': None,
        })
        ctx1 = json.loads(self.svc._blob('idemp-roll-1', '.context.json').read_text(encoding='utf-8'))
        # Inject a sentinel roll into .context.json to verify retry strictly reuses it without re-rolling!
        sentinel = {'triggered': True, 'probability': 0.42, 'scene_turns_in_place': 2, 'tier': 'tier1',
                    'event_id': 'BEAT-SENTINEL', 'objective_event': '测试冻结变数'}
        ctx1['director_roll'] = sentinel
        rr._atomic(self.svc._blob('idemp-roll-1', '.context.json'), rr._json(ctx1))
        # Fail job, refund, and retry
        with self.svc.store._locked():
            tasks = self.svc._read()
            sp.refund(self.svc, tasks, tasks['jobs']['idemp-roll-1'], 'failed', '模拟失败重试')
        sp.retry(self.svc, 'idemp-roll-1', {'model_key': None})
        ctx2 = json.loads(self.svc._blob('idemp-roll-1', '.context.json').read_text(encoding='utf-8'))
        self.assertEqual(ctx2['director_roll'], sentinel)
        # Cancel/refund does not pollute 【世界导演状态】 in memory
        with self.svc.store._locked():
            tasks = self.svc._read()
            sp.refund(self.svc, tasks, tasks['jobs']['idemp-roll-1'], 'cancelled', '玩家取消')
        self.assertEqual((self.tmp / rr.FILES[0]).read_text(encoding='utf-8'), mem_before)

    def test_T6_option_2b_move_syntax_and_tamper_protection(self):
        locs = ir.policy(self.tmp)['locations']
        aliases = ir.location_aliases(self.tmp)
        raw = (
            '[N] 客厅里的茶已经微凉，手机在桌面上闪了一下。\n'
            '---DECISION---\n'
            'PROMPT: 手机提示集团有新邮件，你怎么安排下一步？\n'
            'A[MOVE:公司]: 起身告别，直接去公司找沈知韫\n'
            'B[MOVE:画室]: 顺路去念薇的校外画室看看她的参展画稿\n'
            'C[MOVE:火星]: 原地把话挑明，不再绕弯子\n'
        )
        parsed = sc.parse_stream_story(
            raw, allowed_speakers=[], partial=False,
            valid_destinations=locs, location_aliases=aliases, current_location='徐家主宅',
        )
        opts = {o['id']: o for o in parsed['decision']['options']}
        self.assertEqual(opts['A']['operation'], {'code': 'move_player', 'destination': '公司'})
        self.assertEqual(opts['A']['text'], '起身告别，直接去公司找沈知韫')
        self.assertEqual(opts['B']['operation'], {'code': 'move_player', 'destination': '工作室'})
        self.assertNotIn('operation', opts['C'])  # Invalid destination gracefully dropped!
        self.assertEqual(opts['C']['text'], '原地把话挑明，不再绕弯子')

        # Same-location [MOVE] is also gracefully stripped
        raw_same = (
            '[N] 你站在客厅里。\n'
            '---DECISION---\n'
            'PROMPT: 怎么走？\n'
            'A[MOVE:徐家主宅]: 留在客厅继续看文件\n'
            'B: 倒杯温水递给她\n'
            'C: 直接开口询问\n'
        )
        p_same = sc.parse_stream_story(
            raw_same, allowed_speakers=[], partial=False,
            valid_destinations=locs, location_aliases=aliases, current_location='徐家主宅',
        )
        self.assertNotIn('operation', p_same['decision']['options'][0])

        # Begin game with Option A carrying move_player -> 公司, Option C carrying no operation
        self._begin_game(decision=parsed['decision'])
        complete_current_playback(self.svc)
        files = self.svc.store._files()
        row = ir.segment(self.tmp, files)
        sel_a = {'segment_id': row['id'], 'option_id': 'A'}
        sel_c = {'segment_id': row['id'], 'option_id': 'C'}
        op_company = {'code': 'move_player', 'destination': '公司'}
        op_univ = {'code': 'move_player', 'destination': '大学'}

        # Tamper protection checks
        ir.selection(self.tmp, files, sel_a, opts['A']['text'], op_company)  # exact match passes
        with self.assertRaises(rr.ConflictError):
            ir.selection(self.tmp, files, sel_a, opts['A']['text'], None)  # dropping op rejected
        with self.assertRaises(rr.ConflictError):
            ir.selection(self.tmp, files, sel_a, opts['A']['text'], op_univ)  # swapped destination rejected
        with self.assertRaises(rr.ConflictError):
            ir.selection(self.tmp, files, sel_c, opts['C']['text'], op_company)  # injecting op rejected

        # End-to-end execution of Option A [MOVE:公司] transitions location to 公司
        run_action_turn(
            self.svc, text=opts['A']['text'], option_id='A', category='A',
            operation=op_company,
            messages=[{'kind': 'narration', 'speaker': '', 'text': '徐志北乘车来到公司楼下，前台领着他走向总裁办公室。'}],
            clock={'day': 1, 'time': '10:00'},
            conditions={'intensity': 'A', 'effective_progress': True, 'scene': '公司', 'npc': None,
                        'action_changed': True, 'stress_signals': 0, 'breakout_triggered': []},
            req_id='move-opt-a-1',
        )
        self.assertEqual(ir.view(self.svc.store)['location'], '公司')

        # Refused-move handoff compatibility: option carries [MOVE:工作室], site refuses -> operation=None + handoff
        complete_current_playback(self.svc)
        # Seed next turn with move option to 工作室
        snap2 = self.svc.interaction_snapshot()
        row2 = ir.segment(self.tmp, self.svc.store._files())
        # Commit a turn that outputs B[MOVE:工作室]
        dec_refuse = {
            'prompt': '准备去工作室吗？',
            'options': [
                {'id': 'A', 'text': '先在公司看报表'},
                {'id': 'B', 'text': '立刻出发去工作室找念薇', 'operation': {'code': 'move_player', 'destination': '工作室'}},
                {'id': 'C', 'text': '直接推门进会议室'},
            ],
        }
        sp.create(self.svc, {
            'request_id': 'prep-refuse', 'base_revision': snap2['revision'], 'save_epoch': snap2['save_epoch'],
            'action': row2['decision']['options'][0]['text'], 'entry_mode': ir.MODE, 'operation': None,
            'selection': {'segment_id': row2['id'], 'option_id': 'A'}, 'model_key': None,
        })
        tasks = self.svc._read()
        job = tasks['jobs']['prep-refuse']; job['status'] = 'validating'; self.svc._write(tasks)
        self.svc.store.submit({
            'schema_version': 3, 'entry_mode': ir.MODE, 'request_id': 'prep-refuse',
            'base_revision': job['working_revision'], 'input': row2['decision']['options'][0]['text'],
            'messages': [{'kind': 'narration', 'speaker': '', 'text': '会议室走廊里传来脚步声。'}],
            'decision': dec_refuse, 'selection': {'segment_id': row2['id'], 'option_id': 'A'},
            'operation': None, 'handoff': '',
            'resolution': {
                'category': 'A', 'basis': 'A档', 'clock': {'day': 1, 'time': '10:15', 'basis': '推进'},
                'events': [], 'memory': {'fact': '', 'transfers': {}, 'compact': ''},
                'conditions': {'intensity': 'A', 'effective_progress': True, 'scene': '公司', 'npc': None,
                               'action_changed': True, 'stress_signals': 0, 'breakout_triggered': []},
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''}, 'task': None, 'items': [],
            },
            'audit': {'required_reads_verified': True, 'origin': 'model', 'reservation': job['reservation']},
        })
        complete_current_playback(self.svc)
        snap3 = self.svc.interaction_snapshot()
        row3 = ir.segment(self.tmp, self.svc.store._files())
        op_studio = {'code': 'move_player', 'destination': '工作室'}
        sp.create(self.svc, {
            'request_id': 'refuse-move-1', 'base_revision': snap3['revision'], 'save_epoch': snap3['save_epoch'],
            'action': '立刻出发去工作室找念薇', 'entry_mode': ir.MODE, 'operation': op_studio,
            'selection': {'segment_id': row3['id'], 'option_id': 'B'}, 'model_key': None,
        })
        tasks = self.svc._read()
        job3 = tasks['jobs']['refuse-move-1']; job3['status'] = 'validating'; self.svc._write(tasks)
        self.svc.store.submit({
            'schema_version': 3, 'entry_mode': ir.MODE, 'request_id': 'refuse-move-1',
            'base_revision': job3['working_revision'], 'input': '立刻出发去工作室找念薇',
            'messages': [{'kind': 'narration', 'speaker': '', 'text': '刚走到电梯口，秘书拦住他递来一份紧急签收单。'}],
            'decision': dec_refuse, 'selection': {'segment_id': row3['id'], 'option_id': 'B'},
            'operation': None, 'handoff': '电梯口被紧急签收单拦住，暂未出发前往工作室',
            'resolution': {
                'category': 'B', 'basis': 'B档', 'clock': {'day': 1, 'time': '10:25', 'basis': '拦住'},
                'events': [], 'memory': {'fact': '', 'transfers': {}, 'compact': ''},
                'conditions': {'intensity': 'B', 'effective_progress': True, 'scene': '公司', 'npc': None,
                               'action_changed': False, 'stress_signals': 0, 'breakout_triggered': []},
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''}, 'task': None, 'items': [],
            },
            'audit': {
                'required_reads_verified': True, 'origin': 'player_action',
                'requested_operation': op_studio, 'reservation': job3['reservation'],
            },
        })
        self.assertEqual(ir.view(self.svc.store)['location'], '公司')

        # Natural transition travel_intent + all 11 negative cases remain None
        for pos, dest in [
            ('起身告辞，去公司', '公司'),
            ('喝完茶回主宅', '徐家主宅'),
            ('告别出门，去画室看看', '工作室'),
        ]:
            with self.subTest(pos=pos):
                res = ir.travel_intent(self.tmp, pos)
                self.assertIsNotNone(res)
                self.assertEqual(res['operation']['destination'], dest)
        for neg in [
            '不回家', '先不回家', '明天回家', '等会回家', '如果妈妈在家就回家',
            '问她要不要回家', '回家还是去大学', '回家，随后去公司', '回家？',
            '回家里屋', '回家，下午再去公司',
        ]:
            with self.subTest(neg=neg):
                self.assertIsNone(ir.travel_intent(self.tmp, neg))

    def test_T7_breakout_cooldown_persistence(self):
        self._begin_game()
        # Trigger breakout_triggered=['破局_日常冗余']
        run_action_turn(
            self.svc, text='问问今天家里的安排', option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': '客厅电话忽然响了两声，打破了冗长的寒暄。'}],
            clock={'day': 1, 'time': '10:00'},
            conditions={'intensity': 'A', 'effective_progress': True, 'scene': '徐家主宅', 'npc': '沈知韫',
                        'action_changed': True, 'stress_signals': 0, 'breakout_triggered': ['破局_日常冗余']},
            req_id='bk-1',
        )
        mem1 = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        c1 = rr._counters(mem1)
        self.assertEqual(c1.get('冷却_破局全局'), 2)
        self.assertEqual(c1.get('冷却_破局_日常冗余'), 8)
        # Even if counter were pushed above threshold, compile_breakout_hint stays None during cooldown!
        mem_high = re.sub(r'破局_日常冗余\s*:\s*\d+', '破局_日常冗余: 6', mem1)
        self.assertIsNone(sc.compile_breakout_hint(mem_high))

        # Next turn decrements cooldowns cleanly (2 -> 1, 8 -> 7)
        run_action_turn(
            self.svc, text='聊些日常近况', option_id='A', category='A',
            messages=[{'kind': 'narration', 'speaker': '', 'text': '她放下话筒，重新端起茶杯。'}],
            clock={'day': 1, 'time': '10:15'},
            req_id='bk-2',
        )
        c2 = rr._counters((self.tmp / rr.FILES[0]).read_text(encoding='utf-8'))
        self.assertEqual(c2.get('冷却_破局全局'), 1)
        self.assertEqual(c2.get('冷却_破局_日常冗余'), 7)

    def test_T8_pregnancy_cycle_latency_fluid_lock_and_masturbation_mechanics(self):
        import save_store
        engine = rr._engine(self.tmp, self.tmp)
        mem_path = self.tmp / rr.FILES[0]

        # 1. Deterministic 10-day cycle calendar:
        # Shen Zhiyun offset=0 -> pos 0,1 安全期; pos 6,7 危险期; others 常规期
        self.assertEqual(engine.determine_cycle_phase('沈知韫', 1), '安全期')
        self.assertEqual(engine.determine_cycle_phase('沈知韫', 4), '常规期')
        self.assertEqual(engine.determine_cycle_phase('沈知韫', 7), '危险期')

        # 2. Climax + Creampie conception rate fix & 2-day conception latency (pregnancy_latent_until):
        # On Day 5 (常规期 x1.0), climax (DS_17 -> 40% base) with rng=0.30 (< 0.40, whereas old broken 0.15 would have failed!)
        st, ly, _ = save_store.load_bundle(self.tmp)
        st['runtime']['clock'] = {'day': 5, 'time': '22:00'}
        save_store.save_bundle(self.tmp, st, ly)
        orig_randint = engine.random.randint
        try:
            engine.random.randint = lambda a, b: 30
            engine.apply_story_events(
                {
                    'shame_events': {'沈知韫': ['内射_常规']},
                    'ds_events': {'沈知韫': ['触发高潮_绝顶清算']},
                    'depravity_events': {},
                    'affection_events': {},
                    'host_events': [],
                },
                None,
                1,
                current_day=5,
                active_cast=['沈知韫'],
            )
        finally:
            engine.random.randint = orig_randint

        st_after, _, _ = save_store.load_bundle(self.tmp)
        # During 2-day latency (until Day 7), panel 怀孕 is still False, but pregnancy_latent_until == 7!
        self.assertFalse(st_after['panels']['沈知韫']['怀孕'])
        self.assertEqual(st_after['mechanics']['pregnancy_latent_until']['沈知韫'], 7)
        self.assertEqual(st_after['panels']['沈知韫']['内射'], 1)
        # Fluid lock mounted at 24 turns -> floor >= 85
        self.assertEqual(st_after['panels']['沈知韫']['欲望'], 85)

        # 3. 3-tier fluid lock floor (17~24 -> 85, 9~16 -> 72, 1~8 -> 58)
        self.assertEqual(engine.fluid_lock_floor_for_turns(20), 85)
        self.assertEqual(engine.fluid_lock_floor_for_turns(12), 72)
        self.assertEqual(engine.fluid_lock_floor_for_turns(4), 58)
        self.assertEqual(engine.fluid_lock_floor_for_turns(0), 0)

        # 4. Advance clock to Day 7 -> latent pregnancy auto-promotes to confirmed 怀孕=True;
        # then 确诊怀孕 (SHAME_10) deducts 30 and caps shame at <= 35 (not 0!)
        st_day7, ly_day7, _ = save_store.load_bundle(self.tmp)
        st_day7['runtime']['clock'] = {'day': 7, 'time': '09:00'}
        st_day7['panels']['沈知韫']['羞耻'] = 60
        save_store.save_bundle(self.tmp, st_day7, ly_day7)
        engine.apply_story_events(
            {
                'shame_events': {'沈知韫': ['确诊怀孕']},
                'ds_events': {},
                'depravity_events': {},
                'affection_events': {},
                'host_events': [],
            },
            None,
            2,
            current_day=7,
            active_cast=['沈知韫'],
        )
        st_preg, _, _ = save_store.load_bundle(self.tmp)
        self.assertTrue(st_preg['panels']['沈知韫']['怀孕'])
        self.assertEqual(st_preg['mechanics']['pregnancy_latent_until']['沈知韫'], 0)
        self.assertEqual(st_preg['panels']['沈知韫']['羞耻'], 30)

        # Even if shame started at 90 before 确诊怀孕, shame is capped at <= 35
        st_preg['panels']['沈知韫']['羞耻'] = 90
        save_store.save_bundle(self.tmp, st_preg, ly_day7)
        engine.apply_story_events(
            {
                'shame_events': {'沈知韫': ['确诊怀孕']},
                'ds_events': {},
                'depravity_events': {},
                'affection_events': {},
                'host_events': [],
            },
            None,
            3,
            current_day=7,
            active_cast=['沈知韫'],
        )
        st_capped, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_capped['panels']['沈知韫']['羞耻'], 35)

        # 5. Masturbation tags (SHAME_20, DEPRAVITY_10, DS_18) & off-stage exhaustion freeze
        st_m, ly_m, _ = save_store.load_bundle(self.tmp)
        st_m['panels']['苏婉青']['羞耻'] = 70
        st_m['panels']['苏婉青']['好感'] = 50
        st_m['panels']['苏婉青']['欲望'] = 80
        st_m['panels']['苏婉青']['高潮'] = 65
        st_m['panels']['苏婉青']['体力'] = 80
        st_m['panels']['徐念薇']['欲望'] = 80
        st_m['counters']['空耗_连续未纾解_苏婉青'] = 1
        st_m['counters']['空耗_连续未纾解_徐念薇'] = 1
        save_store.save_bundle(self.tmp, st_m, ly_m)

        # Derive lifecycle with active_cast=['苏婉青'] (徐念薇 is off-stage -> her streak must stay frozen at 1!)
        body_m = {
            'current_round': 1,
            'memory_deltas': {
                'round_conditions': {
                    'intensity': 'C', 'effective_progress': True, 'scene': '市中心顶层公寓',
                    'npc': '苏婉青', 'action_changed': True, 'stress_signals': 1, 'breakout_triggered': [],
                },
            },
            'micro_state_changes': {},
            'counter_updates': {},
            'host_events': [],
            'shame_events': {'苏婉青': ['意外撞破_私密自渎', 'C烈度_中度']},
            'depravity_events': {'苏婉青': ['堕落_私密自渎']},
            'ds_events': {'苏婉青': ['自慰_暗中纾解']},
            'affection_events': {},
            'vigilance_events': {},
            'system_log': '',
        }
        settled_m, _, _, counters_m = rr._derive_lifecycle(
            engine, body_m, mem_path.read_text(encoding='utf-8'), active_cast=['苏婉青'],
        )
        # Su Wanqing relieved via DS_18 -> streak reset to 0; Xu Nianwei off-stage -> frozen at 1 without penalty
        self.assertEqual(counters_m['空耗_连续未纾解_苏婉青'], 0)
        self.assertEqual(counters_m['空耗_连续未纾解_徐念薇'], 1)
        self.assertNotIn('状态_空耗惩罚', settled_m['ds_events'].get('徐念薇', []))

        engine.apply_story_events(
            {
                'shame_events': settled_m['shame_events'],
                'depravity_events': settled_m['depravity_events'],
                'ds_events': settled_m['ds_events'],
                'affection_events': {},
                'host_events': [],
            },
            None,
            4,
            current_day=7,
            active_cast=['苏婉青'],
        )
        st_m_after, _, _ = save_store.load_bundle(self.tmp)
        self.assertEqual(st_m_after['panels']['苏婉青']['高潮'], 0)
        self.assertEqual(st_m_after['panels']['苏婉青']['欲望'], 40)
        self.assertEqual(st_m_after['panels']['苏婉青']['体力'], 72)
        self.assertEqual(st_m_after['mechanics']['masturbation_trace']['苏婉青'], 2)
        # C烈度_中度 at aff=50 normally drops -4, halved to -2 by 意外撞破_私密自渎
        self.assertEqual(st_m_after['panels']['苏婉青']['好感'], 48)


if __name__ == '__main__':
    unittest.main()

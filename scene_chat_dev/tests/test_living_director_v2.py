"""Comprehensive automated tests for Living World Director 2.0 (Plan A).
Runs strictly inside isolated temporary copies; never modifies live save files.
"""
import copy
import json
import pathlib
import random
import shutil
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

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


class LivingDirectorV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_isolated_workspace()
        self.svc = ss.StoryService(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _set_track_weights(self, weights):
        cfg_path = self.tmp / 'txt文件/互动运行配置.json'
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        cfg['director']['track_weights'] = dict(weights)
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def _begin_game(self, *, time_str='09:30'):
        snap = self.svc.interaction_snapshot()
        sp.create(self.svc, {
            'request_id': 'ld2-begin',
            'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'],
            'action': '继续当前剧情',
            'entry_mode': ir.MODE,
            'operation': None,
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
            'model_key': None,
        })
        tasks = self.svc._read()
        job = tasks['jobs']['ld2-begin']
        job['status'] = 'validating'
        self.svc._write(tasks)
        payload = {
            'schema_version': 3,
            'entry_mode': ir.MODE,
            'request_id': 'ld2-begin',
            'base_revision': job['working_revision'],
            'input': '继续当前剧情',
            'messages': [{'kind': 'narration', 'speaker': '', 'text': '清晨阳光照进主宅客厅，茶盏冒着微热白气。'}],
            'decision': {
                'prompt': '客厅里安静下来，你准备如何继续？',
                'options': [
                    {'id': 'A', 'text': '问问今天家里的安排'},
                    {'id': 'B', 'text': '顺手帮她递过茶杯'},
                    {'id': 'C', 'text': '直接试探她的真实想法'},
                ],
            },
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

    def test_01_v2_catalog_integrity_and_safety(self):
        cat = sp.load_world_beats(self.tmp, optional=False)
        self.assertEqual(cat['version'], 2)
        channels = cat['channels']
        self.assertEqual(len(channels), 8)
        for req_ch in ('phone_msg', 'door_visit', 'object_trace', 'sensory_slip',
                       'third_party', 'schedule_clash', 'conversation_twist', 'offstage_ripple'):
            self.assertIn(req_ch, channels)

        spark = cat['spark_matrix']
        self.assertEqual(len(spark['actions']), 25)
        self.assertEqual(len(spark['textures']), 25)
        for tx in spark['textures']:
            self.assertIn(tx['channel'], channels)
            self.assertTrue(tx['label'])
        self.assertEqual(len(spark['moves']['soft']), 6)
        self.assertEqual(len(spark['moves']['hard']), 5)

        clocks = cat['offstage_clocks']
        self.assertEqual(set(clocks.keys()), {'CLK_XCY', 'CLK_SZY', 'CLK_XNW', 'CLK_SWQ'})
        for cid, meta in clocks.items():
            self.assertIn(meta['owner'], sp.DIRECTOR_VALID_PEOPLE)
            self.assertEqual(meta['max_segments'], 4)
            self.assertEqual(meta['soft_at'], 3)
            self.assertEqual(len(meta['phases']), 2)
            self.assertTrue(meta['k01_guard'])
            for ph in meta['phases']:
                self.assertIn(ph['channel_hint'], channels)
                self.assertTrue(ph['soft_omen'] and ph['hard_landing'])

        beats = cat['beats']
        self.assertEqual(len(beats), 61)
        erotic_beats = [b for b in beats if b.get('category') == 'erotic_accident']
        self.assertEqual(len(erotic_beats), 17)
        self.assertIn('sensual_spark_matrix', cat)
        for b in beats:
            self.assertIn(b.get('channel'), channels, f"beat {b.get('id')} missing valid channel")
            self.assertNotIn('系统提示', b.get('objective_event', ''))

        cfg = sp.director_config(self.tmp)
        self.assertEqual(cfg['track_weights'], {'thread_spark': 45, 'offstage_clock': 30, 'preset_beat': 25})
        self.assertEqual(cfg['max_active_threads'], 5)
        self.assertEqual(cfg['channel_cooldown_window'], 4)

    def test_02_persistence_legacy_compat_and_header_strip(self):
        base_mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        # Legacy v1 block lacking all v2 keys
        v1_json = json.dumps({
            'calm_streak': 3, 'global_cooldown': 0, 'turns_since_beat': 5,
            'scene_location': '徐家主宅', 'scene_turns': 2,
            'event_cooldowns': {'BEAT-T1-MANOR-COURIER': 4},
            'consumed_once': [], 'pending_seeds': [],
        }, ensure_ascii=False, separators=(',', ':'))
        base_no_dir = sp.re.sub(r'(?m)^【世界导演状态】[ \t]*\n[^\n]*\n*', '', base_mem)
        legacy_mem = base_no_dir.replace('▲ 第一层：', f'{sp.DIRECTOR_ANCHOR}\n{v1_json}\n\n▲ 第一层：', 1)
        parsed_v1 = sp.parse_director_block(legacy_mem)
        self.assertEqual(parsed_v1['calm_streak'], 3)
        self.assertEqual(parsed_v1['active_threads'], [])
        self.assertEqual(parsed_v1['offstage_clocks'], {})
        self.assertEqual(parsed_v1['recent_channels'], [])
        self.assertEqual(parsed_v1['next_thread_seq'], 1)

        # Full v2 round-trip + compact single-line + _project_memory_header stripping
        v2_state = {
            **parsed_v1,
            'active_threads': [
                {'id': 'TH-3', 'who': ['徐念薇'], 'topic': '画室藏画与方才眼神躲闪', 'tension': 'soft', 'age': 2, 'touches': 0},
            ],
            'next_thread_seq': 4,
            'offstage_clocks': {'CLK_XCY': {'p': 3, 'ph': 1, 'so': False, 'cd': 0}},
            'recent_channels': ['phone_msg', 'door_visit'],
            'clock_tick_acc': 2,
            'last_time_slot': 'evening',
        }
        written = sp.write_director_block(base_mem, v2_state)
        roundtrip = sp.parse_director_block(written)
        self.assertEqual(roundtrip['active_threads'][0]['id'], 'TH-3')
        self.assertEqual(roundtrip['next_thread_seq'], 4)
        self.assertEqual(roundtrip['offstage_clocks']['CLK_XCY'], {'p': 3, 'ph': 1, 'so': False, 'cd': 0})
        self.assertEqual(roundtrip['recent_channels'], ['phone_msg', 'door_visit'])
        self.assertEqual(roundtrip['clock_tick_acc'], 2)
        self.assertEqual(roundtrip['last_time_slot'], 'evening')

        raw_header = written.split('▲ 第一层：', 1)[0]
        projected = ir._project_memory_header(raw_header)
        self.assertNotIn(sp.DIRECTOR_ANCHOR, projected)
        self.assertNotIn('CLK_XCY', projected)
        self.assertNotIn('TH-3', projected)

    def test_03_track1_thread_spark_salience_escalation_and_channel_ban(self):
        self._set_track_weights({'thread_spark': 100, 'offstage_clock': 0, 'preset_beat': 0})
        base_mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        state = {'location': '工作室', 'cast': ['徐念薇'], 'items': []}
        runtime = {'clock': {'day': 2, 'time': '19:30'}}

        # 1) On-stage thread outscores off-stage thread + banned channels excluded from texture
        banned = ['phone_msg', 'door_visit', 'object_trace']
        m = sp.write_director_block(base_mem, {
            'calm_streak': 5,
            'active_threads': [
                {'id': 'TH-1', 'who': ['徐念薇'], 'topic': '画室未干的藏画与临时遮盖布', 'tension': 'soft', 'age': 1, 'touches': 0},
                {'id': 'TH-2', 'who': ['苏婉青'], 'topic': '公寓茶几压着的备忘便签', 'tension': 'soft', 'age': 1, 'touches': 0},
            ],
            'next_thread_seq': 3,
            'recent_channels': banned,
        })
        rng = random.Random(2026)
        hits = {'TH-1': 0, 'TH-2': 0}
        for _ in range(300):
            r = sp.roll_director_beat(self.tmp, state, m, runtime, '周三', rng=rng)
            if not r['triggered']:
                continue
            self.assertEqual(r['mode'], 'thread_spark')
            self.assertNotIn(r['channel_hint'], banned)
            self.assertEqual(r['move_kind'], 'soft')
            hits[r['thread_id']] += 1
        self.assertGreater(hits['TH-1'], hits['TH-2'])

        # 2) Touching TH-1 escalates tension soft -> hard and next roll emits hard move
        r_soft = sp.roll_director_beat(self.tmp, state, m, runtime, '周三', rng=FixedRng([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
        self.assertEqual(r_soft['thread_id'], 'TH-1')
        self.assertEqual(r_soft['move_kind'], 'soft')
        m_after = sp.advance_director_state(
            self.tmp, m, location='工作室', director_roll=r_soft,
            effective_progress=True, had_events=False, memory_fact='',
            active_cast=['徐念薇'], new_clock={'day': 2, 'time': '19:45'},
        )
        ds_after = sp.parse_director_block(m_after)
        th1 = next(t for t in ds_after['active_threads'] if t['id'] == 'TH-1')
        self.assertEqual(th1['touches'], 1)
        self.assertEqual(th1['tension'], 'hard')
        # Clear global cooldown if any and roll again -> must escalate to hard move!
        ds_after['global_cooldown'] = 0
        ds_after['calm_streak'] = 5
        m_next = sp.write_director_block(m_after, ds_after)
        r_hard = sp.roll_director_beat(self.tmp, state, m_next, runtime, '周三', rng=FixedRng([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
        self.assertEqual(r_hard['mode'], 'thread_spark')
        self.assertEqual(r_hard['thread_id'], 'TH-1')
        self.assertEqual(r_hard['move_kind'], 'hard')
        self.assertEqual(r_hard['tier'], 'tier2')

        # 3) Empty active_threads gracefully falls back to L1 snippet
        m_l1 = base_mem.replace('▲ 第一层：【即时运存区】\n（空）', '▲ 第一层：【即时运存区】\n【1】周二 10:00｜沈知韫在书房临时收起一份深圳对账单。')
        m_l1 = sp.write_director_block(m_l1, {'calm_streak': 5, 'active_threads': []})
        r_fb = sp.roll_director_beat(self.tmp, state, m_l1, runtime, '周三', rng=FixedRng([0.0]))
        self.assertTrue(r_fb['triggered'])
        self.assertEqual(r_fb['mode'], 'thread_spark')
        self.assertEqual(r_fb['thread_id'], '')
        self.assertIn('深圳对账单', r_fb['anchor'])

    def test_04_track2_offstage_clock_lifecycle_and_no_teleport(self):
        self._set_track_weights({'thread_spark': 0, 'offstage_clock': 100, 'preset_beat': 0})
        base_mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        state = {'location': '徐家主宅', 'cast': ['沈知韫'], 'items': []}
        runtime = {'clock': {'day': 2, 'time': '20:00'}}

        # 1) Clocks below 3/4 NEVER fire Track 2
        m_low = sp.write_director_block(base_mem, {
            'calm_streak': 5,
            'offstage_clocks': {'CLK_XCY': {'p': 2, 'ph': 0, 'so': False, 'cd': 0}},
        })
        r_low = sp.roll_director_beat(self.tmp, state, m_low, runtime, '周三', rng=FixedRng([0.0]))
        self.assertFalse(r_low['triggered'])

        # 2) Deterministic ticking: slot change ticks an OFFSTAGE clock (never on-stage 沈知韫)
        m_tick = sp.write_director_block(base_mem, {'last_time_slot': 'morning'})
        m_tick = sp.advance_director_state(
            self.tmp, m_tick, location='徐家主宅', director_roll={'triggered': False},
            effective_progress=True, had_events=False, memory_fact='',
            active_cast=['沈知韫'], new_clock={'day': 1, 'time': '14:00'}, day_crossed=False,
        )
        clocks_after_tick = sp.parse_director_block(m_tick)['offstage_clocks']
        self.assertEqual(clocks_after_tick['CLK_SZY']['p'], 0, 'On-stage character clock must not tick')
        self.assertEqual(sum(v['p'] for k, v in clocks_after_tick.items() if k != 'CLK_SZY'), 1)

        # 3) Clock at 3/4 triggers Soft Omen + sets so=True & cd=2 + forbids teleporting offstage 徐承邺
        m_soft = sp.write_director_block(base_mem, {
            'calm_streak': 5,
            'offstage_clocks': {'CLK_XCY': {'p': 3, 'ph': 0, 'so': False, 'cd': 0}},
            'recent_channels': ['phone_msg'],
        })
        r_soft = sp.roll_director_beat(self.tmp, state, m_soft, runtime, '周三', rng=FixedRng([0.0]))
        self.assertTrue(r_soft['triggered'])
        self.assertEqual(r_soft['mode'], 'offstage_clock')
        self.assertEqual(r_soft['clock_id'], 'CLK_XCY')
        self.assertEqual(r_soft['clock_stage'], 'soft')
        self.assertFalse(r_soft['owner_in_scene'])
        sd_soft = sp.format_surprise_directive(r_soft)
        self.assertIn('严禁让其现身或输出[D:姓名]', sd_soft['rule'])
        self.assertIn('手机来电/微信/推送消息', sd_soft['banned_channels'])

        m_after_soft = sp.advance_director_state(
            self.tmp, m_soft, location='徐家主宅', director_roll=r_soft,
            effective_progress=True, had_events=False, memory_fact='',
            active_cast=['沈知韫'], new_clock={'day': 2, 'time': '20:15'},
        )
        xcy_soft = sp.parse_director_block(m_after_soft)['offstage_clocks']['CLK_XCY']
        self.assertTrue(xcy_soft['so'])
        self.assertEqual(xcy_soft['cd'], 2)

        # 4) Clock at 4/4 triggers Hard Landing -> resets p=0, so=False, rotates phase 0->1, cd=6
        m_hard = sp.write_director_block(base_mem, {
            'calm_streak': 5,
            'offstage_clocks': {'CLK_XCY': {'p': 4, 'ph': 0, 'so': True, 'cd': 0}},
        })
        r_hard = sp.roll_director_beat(self.tmp, state, m_hard, runtime, '周三', rng=FixedRng([0.0]))
        self.assertTrue(r_hard['triggered'])
        self.assertEqual(r_hard['clock_stage'], 'hard')
        self.assertEqual(r_hard['tier'], 'tier3')
        m_after_hard = sp.advance_director_state(
            self.tmp, m_hard, location='徐家主宅', director_roll=r_hard,
            effective_progress=True, had_events=False, memory_fact='',
            active_cast=['沈知韫'], new_clock={'day': 2, 'time': '20:30'},
        )
        xcy_hard = sp.parse_director_block(m_after_hard)['offstage_clocks']['CLK_XCY']
        self.assertEqual(xcy_hard['p'], 0)
        self.assertFalse(xcy_hard['so'])
        self.assertEqual(xcy_hard['ph'], 1)
        self.assertEqual(xcy_hard['cd'], 6)

    def test_05_track3_salience_specificity_and_channel_demotion(self):
        self._set_track_weights({'thread_spark': 0, 'offstage_clock': 0, 'preset_beat': 100})
        base_mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        state = {'location': '市中心顶层公寓', 'cast': ['苏婉青'], 'items': []}
        runtime = {'clock': {'day': 2, 'time': '15:00'}}

        # Compare phone_msg share with vs without phone_msg in recent_channels
        m_plain = sp.write_director_block(base_mem, {'calm_streak': 5, 'recent_channels': []})
        m_ban_phone = sp.write_director_block(base_mem, {'calm_streak': 5, 'recent_channels': ['phone_msg']})
        rng1 = random.Random(101)
        rng2 = random.Random(101)
        plain_phone, plain_weather, plain_specific = 0, 0, 0
        ban_phone = 0
        for _ in range(400):
            r1 = sp.roll_director_beat(self.tmp, state, m_plain, runtime, '周三', rng=rng1)
            if r1['triggered']:
                if r1['channel_hint'] == 'phone_msg':
                    plain_phone += 1
                if r1['event_id'] == 'BEAT-T1-WEATHER-CLOUD':
                    plain_weather += 1
                elif r1['event_id'] in ('BEAT-T1-APT-WRONG-GIFT', 'BEAT-T1-APT-MEMO-NOTE', 'BEAT-T1-APT-PHONE-GLOW'):
                    plain_specific += 1
            r2 = sp.roll_director_beat(self.tmp, state, m_ban_phone, runtime, '周三', rng=rng2)
            if r2['triggered'] and r2['channel_hint'] == 'phone_msg':
                ban_phone += 1
        # Specific apartment+Su Wanqing beats dominate universal 5-location weather beat
        self.assertGreater(plain_specific, plain_weather * 3)
        # Channel cooldown sharply suppresses phone_msg preset beats
        self.assertGreater(plain_phone, ban_phone * 3)

    def test_06_director_echo_fault_tolerant_sanitization_and_thread_lifecycle(self):
        base_mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        cat = sp.load_world_beats(self.tmp, optional=False)
        dstate = sp.parse_director_block(base_mem)
        dstate['active_threads'] = [
            {'id': 'TH-1', 'who': ['徐念薇'], 'topic': '画室藏画未干', 'tension': 'soft', 'age': 2, 'touches': 0},
        ]

        # Malformed payloads never raise and clamp valid nudges
        self.assertIsNone(sp._sanitize_director_echo('bad-string', cat, dstate, True))
        self.assertIsNone(sp._sanitize_director_echo(12345, cat, dstate, True))
        self.assertIsNone(sp._sanitize_director_echo({'used_channel': 'phone_msg'}, cat, dstate, False))
        cleaned = sp._sanitize_director_echo({
            'new_thread': {'who': ['徐念薇', '不存在路人'], 'topic': '周末去校外画室看未完成作品', 'tension': 'unknown'},
            'close_thread': ['TH-1', 'TH-999'],
            'clock_nudges': {'CLK_XCY': 99, 'CLK_FAKE': 1, 'CLK_SZY': -5, 'CLK_XNW': True},
            'used_channel': 'sensory_slip',
        }, cat, dstate, True)
        self.assertEqual(cleaned['new_thread'], {'who': ['徐念薇'], 'topic': '周末去校外画室看未完成作品', 'tension': 'soft'})
        self.assertEqual(cleaned['close_thread'], ['TH-1'])
        self.assertEqual(cleaned['clock_nudges'], {'CLK_XCY': 1, 'CLK_SZY': -1})
        self.assertEqual(cleaned['used_channel'], 'sensory_slip')

        # Thread dedupe, max cap (5), and expiration (>12)
        m = base_mem
        topics = [
            '沈知韫藏起顾律师名片',
            '苏婉青公寓玄关错寄礼盒',
            '徐念薇画室蒙布下的画框',
            '公司茶水间议论外地并购估值',
            '主宅管家提及林秘书来电问家宴',
            '书房抽屉深处带日期的加密函件',
        ]
        for idx, tp in enumerate(topics):
            m = sp.advance_director_state(
                self.tmp, m, location='徐家主宅', director_roll={'triggered': False},
                effective_progress=True, had_events=False, memory_fact='',
                director_echo={'new_thread': {'who': ['沈知韫'], 'topic': tp, 'tension': 'hard' if idx == 0 else 'soft'}},
                active_cast=['沈知韫'], new_clock={'day': 1, 'time': f'1{idx}:00'},
            )
        ds = sp.parse_director_block(m)
        self.assertEqual(len(ds['active_threads']), 5)
        # Hard thread TH-1 should be retained while oldest soft thread TH-2 was evicted
        ids = [t['id'] for t in ds['active_threads']]
        self.assertIn('TH-1', ids)
        self.assertNotIn('TH-2', ids)

        # Duplicate topic refreshes instead of adding a new ID
        seq_before = ds['next_thread_seq']
        m_dup = sp.advance_director_state(
            self.tmp, m, location='徐家主宅', director_roll={'triggered': False},
            effective_progress=True, had_events=False, memory_fact='',
            director_echo={'new_thread': {'who': ['沈知韫'], 'topic': '书房抽屉深处带日期的加密函件', 'tension': 'hard'}},
            active_cast=['沈知韫'], new_clock={'day': 1, 'time': '16:30'},
        )
        ds_dup = sp.parse_director_block(m_dup)
        self.assertEqual(ds_dup['next_thread_seq'], seq_before)

    def test_07_e2e_dual_stream_v2_kv_cache_invariance_and_bridge_passthrough(self):
        self._begin_game()
        complete_current_playback(self.svc)

        # Turn 1: compile dual_stream_v2 material and verify Rule 12 + director_context
        snap1 = self.svc.interaction_snapshot()
        row1 = ir.segment(self.svc.store.root, self.svc.store._files())
        sp.create(self.svc, {
            'request_id': 'ld2-turn-1',
            'base_revision': snap1['revision'],
            'save_epoch': snap1['save_epoch'],
            'action': row1['decision']['options'][0]['text'],
            'entry_mode': ir.MODE,
            'operation': None,
            'selection': {'segment_id': row1['id'], 'option_id': 'A'},
            'model_key': None,
        })
        tasks = self.svc._read()
        job1 = tasks['jobs']['ld2-turn-1']
        job1['status'] = 'generating'
        job1['lease'] = 'lease-ld2-1'
        self.svc._write(tasks)
        mat1 = ir.material_delivery_v2(
            self.svc, 'ld2-turn-1', job1, 'chat-ld2', 'part-1',
            options={'protocol_mode': 'dual_stream_v2', 'is_fresh_session': True},
        )
        spec1 = mat1['settlement_spec']
        self.assertIn('director_echo', spec1['system_prompt'])
        self.assertIn('director_context', spec1['user_context'])
        self.assertEqual(len(spec1['user_context']['director_context']['channels_enum']), 8)
        z0_sha_1 = mat1['zone0_sha256']
        z1_sha_1 = mat1['zone1_sha256']

        # Submit full dual_stream_v2 payload carrying resolution.director_echo
        fg_text = (
            '[N] 客厅里的茶水泛起细微涟漪，沈知韫指尖在文件夹边缘略停了一下。\n'
            '[D:沈知韫] [calm] 深圳那边最近账目对不上，你先别声张。\n'
            '---DECISION---\n'
            'PROMPT: 她罕见漏出一句深圳账目，你打算怎么接？\n'
            'A: 顺着问清具体是哪笔款项出岔子\n'
            'B: 替她续上半杯温茶并顺势坐近些\n'
            'C[MOVE:公司]: 提议等会儿顺路去公司替她翻一遍旧卷宗\n'
        )
        settlement_payload = {
            'operation': None,
            'handoff': '',
            'checks': {
                'intent': '承接玩家询问家里安排的意图',
                'knowledge': '仅涉及在场人物沈知韫与公开对话内容',
                'action': '无地点移动或道具转移操作',
                'pace': '抛出深圳账目悬念并在三轴分歧处交还玩家',
            },
            'quality_flags': [],
            'resolution': {
                'category': 'A',
                'basis': '固定A选项日常对话询问',
                'clock': {'day': 1, 'time': '09:50', 'basis': '客厅交谈约二十分钟'},
                'events': [],
                'memory': {'fact': '沈知韫私下透露深圳分部账目近期对不上，嘱咐先别声张。', 'transfers': {}, 'compact': ''},
                'conditions': {
                    'intensity': 'A', 'effective_progress': True, 'scene': '徐家主宅',
                    'npc': '沈知韫', 'action_changed': True, 'stress_signals': 0, 'breakout_triggered': [],
                },
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
                'task': None,
                'items': [],
                'director_echo': {
                    'new_thread': {'who': ['沈知韫'], 'topic': '深圳分部账目异常且暂不声张', 'tension': 'soft'},
                    'close_thread': '',
                    'clock_nudges': {'CLK_XCY': 1},
                    'used_channel': 'conversation_twist',
                },
            },
        }
        ctx1 = json.loads(self.svc._blob('ld2-turn-1', '.context.json').read_text(encoding='utf-8'))
        assembled = ir.assemble(
            self.svc, 'ld2-turn-1', job1,
            {'dual_stage_version': 1, 'foreground_text': fg_text, 'settlement': settlement_payload},
            ctx1, {'required_reads_verified': True, 'origin': 'model'},
        )
        tasks = self.svc._read()
        tasks['jobs']['ld2-turn-1']['status'] = 'validating'
        self.svc._write(tasks)
        self.svc.store.submit(assembled)
        complete_current_playback(self.svc)

        # Verify 【世界导演状态】 persisted thread + clock nudge + recent_channel atomically
        mem_after_1 = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        ds1 = sp.parse_director_block(mem_after_1)
        self.assertEqual(len(ds1['active_threads']), 1)
        self.assertEqual(ds1['active_threads'][0]['id'], 'TH-1')
        self.assertIn('深圳分部账目', ds1['active_threads'][0]['topic'])
        self.assertEqual(ds1['offstage_clocks']['CLK_XCY']['p'], 1)
        self.assertIn('conversation_twist', ds1['recent_channels'])

        # Turn 2: material_delivery_v2 MUST preserve Zone 0 & Zone 1 SHA-256 unchanged (100% KV cache hit!)
        snap2 = self.svc.interaction_snapshot()
        row2 = ir.segment(self.svc.store.root, self.svc.store._files())
        sp.create(self.svc, {
            'request_id': 'ld2-turn-2',
            'base_revision': snap2['revision'],
            'save_epoch': snap2['save_epoch'],
            'action': row2['decision']['options'][0]['text'],
            'entry_mode': ir.MODE,
            'operation': None,
            'selection': {'segment_id': row2['id'], 'option_id': 'A'},
            'model_key': None,
        })
        tasks2 = self.svc._read()
        job2 = tasks2['jobs']['ld2-turn-2']
        job2['status'] = 'generating'
        job2['lease'] = 'lease-ld2-2'
        self.svc._write(tasks2)
        mat2 = ir.material_delivery_v2(
            self.svc, 'ld2-turn-2', job2, 'chat-ld2', 'part-1',
            options={
                'protocol_mode': 'dual_stream_v2',
                'synced_zone0_sha256': z0_sha_1,
                'synced_zone1_sha256': z1_sha_1,
                'last_committed_sequence': mat1['last_committed_sequence'] + 1,
                'is_fresh_session': False,
            },
        )
        self.assertEqual(mat2['zone0_sha256'], z0_sha_1)
        self.assertEqual(mat2['zone1_sha256'], z1_sha_1)
        dc2 = mat2['settlement_spec']['user_context']['director_context']
        self.assertEqual(dc2['active_threads'][0]['id'], 'TH-1')

        # Verify Operit bridge JS normalizeSettlementJson passes resolution.director_echo untouched
        js_code = (
            "const fs = require('fs');"
            "const src = fs.readFileSync('scene_chat_dev/local.story.operit_bridge/main.js', 'utf8');"
            "const jStart = src.indexOf('function jsonMemberSpan');"
            "const jEnd = src.indexOf('function oversizedMemory');"
            "const nStart = src.indexOf('function extractBalancedJsonObjects');"
            "const nEnd = src.indexOf('function extractRawForeground');"
            "const fn = new Function(src.slice(jStart, jEnd) + '\\n' + src.slice(nStart, nEnd) + '; return normalizeSettlementJson;')();"
            "const sample = JSON.stringify({operation:'',handoff:'',checks:{intent:'a',knowledge:'b',action:'c',pace:'d'},"
            "quality_flags:[],resolution:{category:'A',basis:'x',clock:{day:1,time:'10:00',basis:'b'},events:[],"
            "memory:{fact:'',transfers:{},compact:''},conditions:{intensity:'A',effective_progress:true,scene:'徐家主宅',"
            "npc:'',action_changed:true,stress_signals:0,breakout_triggered:[]},sleep:{kind:'none',start:'',evidence:''},"
            "task:'',items:[],director_echo:{new_thread:{who:['沈知韫'],topic:'深圳账目核对',tension:'soft'},"
            "close_thread:'',clock_nudges:{CLK_XCY:1},used_channel:'object_trace'}}});"
            "const out = fn(sample);"
            "console.log(JSON.stringify({op: out.operation, echo: out.resolution.director_echo}));"
        )
        proc = subprocess.run(['node', '-e', js_code], cwd=str(REPO), capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())
        self.assertIsNone(res['op'])
        self.assertEqual(res['echo']['used_channel'], 'object_trace')
        self.assertEqual(res['echo']['clock_nudges']['CLK_XCY'], 1)

    def test_08_reset_cleans_all_living_director_v2_state(self):
        mem_path = self.tmp / rr.FILES[0]
        dirty = sp.write_director_block(mem_path.read_text(encoding='utf-8'), {
            'calm_streak': 4,
            'active_threads': [{'id': 'TH-9', 'who': ['徐念薇'], 'topic': '残留旧线头', 'tension': 'hard', 'age': 5, 'touches': 2}],
            'next_thread_seq': 10,
            'offstage_clocks': {'CLK_XCY': {'p': 4, 'ph': 1, 'so': True, 'cd': 3}},
            'recent_channels': ['phone_msg', 'door_visit', 'object_trace'],
        })
        mem_path.write_text(dirty, encoding='utf-8')
        reset_clean_save(self.tmp)
        fresh = sp.parse_director_block((self.tmp / rr.FILES[0]).read_text(encoding='utf-8'))
        self.assertEqual(fresh['active_threads'], [])
        self.assertEqual(fresh['offstage_clocks'], {})
        self.assertEqual(fresh['recent_channels'], [])
        self.assertEqual(fresh['calm_streak'], 0)
        self.assertEqual(fresh['next_thread_seq'], 1)

    def test_09_four_tier_erotic_accidents_gating_and_category_cooldown(self):
        mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        # 1. At initial high shame (100), erotic accidents are gated out
        state_view = {'location': '徐家主宅', 'cast': ['沈知韫'], 'items': []}
        runtime_night = {'clock': {'day': 2, 'time': '22:30'}}
        roll_guarded = sp.roll_director_beat(
            self.tmp, state_view, mem, runtime_night, '周二',
            rng=FixedRng([0.01, 0.99, 0.01]),
        )
        self.assertTrue(roll_guarded['triggered'])
        self.assertNotEqual(roll_guarded.get('category'), 'erotic_accident')

        # 2. Lower shame to 50, raise desire to 80, depravity to 22, and unrelieved streak to 1 -> Tier 1..4 erotic accidents unlock
        high_tension_mem = sp.re.sub(
            r'(\[沈知韫\][^\n]*?好感\s*)\d+([^\n]*?堕落\s*)\d+([^\n]*?欲望\s*)\d+([^\n]*?羞耻\s*)\d+',
            r'\g<1>85\g<2>22\g<3>80\g<4>50',
            mem,
        )
        high_tension_mem = high_tension_mem.replace(
            '【回合计数器】\n',
            '【回合计数器】\n空耗_连续未纾解_沈知韫: 1\n',
            1,
        )
        roll_erotic = sp.roll_director_beat(
            self.tmp, state_view, high_tension_mem, runtime_night, '周二',
            rng=FixedRng([0.01, 0.99, 0.99]),
        )
        self.assertTrue(roll_erotic['triggered'])
        self.assertEqual(roll_erotic['mode'], 'preset_beat')
        self.assertEqual(roll_erotic['category'], 'erotic_accident')
        self.assertEqual(roll_erotic['event_id'], 'BEAT-T4-EROTIC-SHEN-MASTURBATION')
        sd = sp.format_surprise_directive(roll_erotic)
        self.assertEqual(sd.get('category'), 'erotic_accident')
        self.assertIn('香艳/私密意外', sd['rule'])

        # 3. Advancing director state sets 3-turn __EROTIC_CATEGORY__ cooldown, preventing immediate back-to-back erotic spam
        after_mem = sp.advance_director_state(
            self.tmp, high_tension_mem, location='徐家主宅',
            director_roll=roll_erotic, effective_progress=True, had_events=True,
            memory_fact='撞见私密自渎现场', active_cast=['沈知韫'],
            new_clock={'day': 2, 'time': '22:45'}, day_crossed=False,
        )
        dstate = sp.parse_director_block(after_mem)
        self.assertEqual(dstate['event_cooldowns'].get('__EROTIC_CATEGORY__'), 3)
        # Clear global_cooldown & soft_cooldown_penalty to test category cooldown directly
        dstate['global_cooldown'] = 0
        dstate['turns_since_beat'] = 3
        cooled_mem = sp.write_director_block(high_tension_mem, dstate)
        roll_cooled = sp.roll_director_beat(
            self.tmp, state_view, cooled_mem, runtime_night, '周二',
            rng=FixedRng([0.01, 0.99, 0.99]),
        )
        self.assertTrue(roll_cooled['triggered'])
        self.assertNotEqual(roll_cooled.get('category'), 'erotic_accident')

    def test_10_tier0_sensual_hooks_and_drought_boost(self):
        cat = sp.load_world_beats(self.tmp)
        sensual = [b for b in cat['beats'] if b.get('category') == 'sensual_hook']
        self.assertEqual(len(sensual), 12)
        mem = (self.tmp / rr.FILES[0]).read_text(encoding='utf-8')
        self._set_track_weights({'thread_spark': 0, 'offstage_clock': 0, 'preset_beat': 100})
        state_view = {'location': '徐家主宅', 'cast': ['沈知韫'], 'items': []}
        runtime_eve = {'clock': {'day': 1, 'time': '21:30'}}
        # Opening shame=100 still permits Tier 0 sensual_hook
        roll_hook = sp.roll_director_beat(
            self.tmp, state_view, mem, runtime_eve, '周二',
            rng=FixedRng([0.01, 0.99, 0.99]),
        )
        self.assertTrue(roll_hook['triggered'])
        self.assertEqual(roll_hook['category'], 'sensual_hook')
        self.assertEqual(roll_hook['event_id'], 'BEAT-T0-SENSUAL-SHEN-FOOT-HOME')
        sd = sp.format_surprise_directive(roll_hook)
        self.assertEqual(sd.get('category'), 'sensual_hook')
        self.assertIn('魅力微距契机', sd['rule'])
        # Drought counter boosts probability and resets to 0 when sensual_hook triggers
        m0 = sp.write_director_block(mem, {'sensual_drought': 0})
        m5 = sp.write_director_block(mem, {'sensual_drought': 5})
        p0 = sp.roll_director_beat(self.tmp, state_view, m0, runtime_eve, '周二', rng=FixedRng([0.99]))['probability']
        p5 = sp.roll_director_beat(self.tmp, state_view, m5, runtime_eve, '周二', rng=FixedRng([0.99]))['probability']
        self.assertGreater(p5, p0)
        after_hook = sp.advance_director_state(
            self.tmp, m5, location='徐家主宅', director_roll=roll_hook,
            effective_progress=True, had_events=False, memory_fact='她拖鞋滑落',
            active_cast=['沈知韫'], new_clock={'day': 1, 'time': '21:45'}, day_crossed=False,
        )
        self.assertEqual(sp.parse_director_block(after_hook)['sensual_drought'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)

"""End-to-end automated verification suite for Phase A + Phase B linkage overhaul.
Runs entirely inside an isolated temporary copy of the repository; never mutates live save files.
"""
import base64
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import injection_core as ic
import interaction_runtime as ir
import round_runtime as rr
import story_compiler as sc
import story_progression as sp
import story_service as ss
import 存档清理器 as cleaner
import 存档开局随机盲盒 as blindbox


def reset_clean_save(tmp):
    for rel in ('存档/save_state.json', '存档/四层记忆.json', '存档/近期演播.json', '存档/次要NPC名册.txt'):
        p = tmp / rel
        if p.exists():
            p.unlink()
    for rel, content in cleaner.TEMPLATES.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
    (tmp / 'data.json').write_text('{}', encoding='utf-8')
    rt = tmp / '.round-runtime'
    if rt.exists():
        shutil.rmtree(rt)


def make_isolated_workspace():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='phase-ab-test-'))
    for rel in (
        'save_store.py',
        'injection_core.py',
        'round_runtime.py',
        'interaction_runtime.py',
        'story_progression.py',
        'story_compiler.py',
        'story_service.py',
        'scene_chat.py',
        'relationship_query.py',
        '存档清理器.py',
        '存档开局随机盲盒.py',
    ):
        src = REPO / rel
        if src.is_file():
            shutil.copy2(src, tmp / rel)
    shutil.copytree(REPO / 'txt文件', tmp / 'txt文件')
    (tmp / '存档').mkdir(parents=True, exist_ok=True)
    reset_clean_save(tmp)
    return tmp


def complete_current_playback(svc):
    files = svc.store._files()
    row = ir.segment(svc.root, files)
    if row is not None:
        prog = ir.playback(svc.root, row)
        total = len(row.get('messages') or [])
        for step in range(prog['revealed'] + 1, total + 1):
            ir.update_playback(svc.store, row, step, False)
        if not prog['completed']:
            ir.update_playback(svc.store, row, total, True)


def run_action_turn(svc, *, text, option_id='A', category='A', messages, clock,
                    events=None, sleep=None, operation=None, intel_used=None,
                    conditions=None, req_id='act-1'):
    """Submit a full schema_version=3 action turn through real sp.create reservation + RoundStore.submit."""
    complete_current_playback(svc)
    snap = svc.interaction_snapshot()
    files = svc.store._files()
    row = ir.segment(svc.root, files)
    selection = {'segment_id': row['id'] if row else '', 'option_id': option_id}
    action_text = text
    if row and option_id in ('A', 'B', 'C'):
        for opt in (row.get('decision') or {}).get('options', []):
            if opt['id'] == option_id:
                action_text = opt['text']
    sp.create(svc, {
        'request_id': req_id,
        'base_revision': snap['revision'],
        'save_epoch': snap['save_epoch'],
        'action': action_text,
        'entry_mode': ir.MODE,
        'operation': operation,
        'selection': selection,
        'model_key': None,
    })
    tasks_data = svc._read()
    job = tasks_data['jobs'][req_id]
    job['status'] = 'validating'
    svc._write(tasks_data)
    reservation = job['reservation']
    working_rev = job['working_revision']
    working_files = svc.store._files()

    if conditions is None:
        cast_now = ir.view(svc.store, working_files)['cast']
        conditions = {
            'intensity': category,
            'effective_progress': True,
            'scene': ir.view(svc.store, working_files)['location'],
            'npc': cast_now[0] if cast_now else None,
            'action_changed': True,
            'stress_signals': 0,
            'breakout_triggered': [],
        }
    res_obj = {
        'category': category,
        'basis': '测试确定性结算依据',
        'clock': {'day': clock['day'], 'time': clock['time'], 'basis': '剧情自然推进'},
        'events': events or [],
        'memory': {'fact': '', 'transfers': {}, 'compact': ''},
        'conditions': conditions,
        'sleep': sleep or {'kind': 'none', 'start': None, 'evidence': ''},
        'task': None,
        'items': [],
    }
    if intel_used is not None:
        res_obj['intel_used'] = intel_used

    payload = {
        'schema_version': 3,
        'entry_mode': ir.MODE,
        'request_id': req_id,
        'base_revision': working_rev,
        'input': action_text,
        'messages': messages,
        'decision': {
            'prompt': '下一步怎么处理？',
            'options': [
                {'id': 'A', 'text': '聊些日常近况'},
                {'id': 'B', 'text': '顺手递过温水'},
                {'id': 'C', 'text': '进一步试探底线'},
            ],
        },
        'selection': selection,
        'operation': operation,
        'handoff': '',
        'resolution': res_obj,
        'audit': {
            'required_reads_verified': True,
            'origin': 'player_action' if operation else 'model',
            'reservation': reservation,
        },
    }
    return svc.store.submit(payload)


class PhaseABLinkageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_isolated_workspace()
        blindbox.initialize_prologue(self.tmp, 'init-test-1', scenario_id='zhiyun_friday_study')
        self.svc = ss.StoryService(self.tmp)
        self.svc.start()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T01_pre_l1_header_projection_avoids_3000_char_cliff(self):
        mem_path = self.tmp / rr.FILES[0]
        mem = mem_path.read_text(encoding='utf-8')
        # Inflate shop recent + echoes + intel + lifecycle so raw pre-L1 > 3600 chars
        shop_state = {
            'redeemed': {f'SHOP-00{i}': i for i in range(1, 9)},
            'recent': [f'第1天 23:0{i} | SHOP-00{i} | 精品礼盒测试商品名称很长很长{i}×1 | -10积分 | ITEM-00{i}' for i in range(1, 9)],
            'echoes': [{'id': f'shop_redeemed:SHOP-00{i}@{i}', 'kind': 'shop_redeemed', 'ref': f'SHOP-00{i}@{i}',
                        'summary': f'商城兑换「超长测试回响商品描述文本占位确保撑大原始头部{i}」×1（-10积分）'} for i in range(1, 5)],
        }
        mem = sp.write_shop_echo_block(mem, shop_state)
        mem = sp.write_intel_block(mem, {'held': ['INTEL-001', 'INTEL-002'], 'consumed': ['INTEL-003'], 'su_ab_contacts': 5, 'leverage_armed': 'INTEL-001'})
        big_lc = {'version': 1, 'round': 12, 'micro': {'沈知韫': {'momentary_ease': {'observed_round': 12, 'origin': 'activated'}}},
                  'ab_streak': 4, 'scopes': {k: '徐家主宅|沈知韫|B' for k in rr.BREAKOUT_LIMITS}, 'legacy_counters': {}}
        mem = rr._write_lifecycle(mem, big_lc)
        mem_path.write_text(mem, encoding='utf-8')
        raw_pre = mem[:mem.index('▲ 第一层：')].strip()
        self.assertGreater(len(raw_pre), 2600)
        proj = ir.memory_context(self.tmp, mem, '书房', sp.state(self.tmp, self.svc.store._files()))
        proj_head = proj['text'].split('【1】', 1)[0]
        self.assertLess(len(proj_head), 1400)
        self.assertEqual(proj['required'], [])

    def test_T02_creampie_counter_increments_on_shame_06_and_07(self):
        mem_path = self.tmp / rr.FILES[0]
        engine = rr._engine(self.tmp, self.tmp)
        empty = {'shame_events': {}, 'depravity_events': {}, 'ds_events': {}, 'affection_events': {}, 'host_events': [], 'vigilance_events': {}}
        ev1 = {**empty, 'shame_events': {'沈知韫': ['内射_首次核爆']}}
        rr._engine_call(engine.apply_story_events, ev1, None, 1)
        m1 = mem_path.read_text(encoding='utf-8')
        self.assertIn('内射 1次', m1.split('[沈知韫]', 1)[1].splitlines()[0])
        ev2 = {**empty, 'shame_events': {'沈知韫': ['内射_常规']}}
        rr._engine_call(engine.apply_story_events, ev2, None, 1)
        m2 = mem_path.read_text(encoding='utf-8')
        self.assertIn('内射 2次', m2.split('[沈知韫]', 1)[1].splitlines()[0])

    def test_T03_fish_tag_evidence_matching(self):
        texts = '[low restrained voice] 这么晚了，怎么还不回房间休息？\n[near whisper, trembling] 别靠这么近。'
        self.assertTrue(sp._evidence_matches('这么晚了，怎么还不回房间休息？', texts))
        self.assertTrue(sp._evidence_matches('别靠这么近。', texts))
        self.assertTrue(sp._evidence_matches('[low restrained voice] 这么晚了', texts))
        self.assertFalse(sp._evidence_matches('我根本没说过这句话', texts))
        self.assertFalse(sp._evidence_matches(' ', texts))

    def test_T04_guardrail_check_per_speaker_and_r02_safe(self):
        # Co-present with 沈知韫: 徐念薇 revealing K01 MUST still be blocked!
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(self.tmp, '徐家主宅', ['沈知韫', '徐念薇'], [
                {'kind': 'dialogue', 'speaker': '徐念薇', 'text': '我听说你才是千亿家产唯一合法继承人。'}
            ])
        # 沈知韫 herself saying it is allowed (she is in secret_holders)
        res_ok = sc.guardrail_check(self.tmp, '徐家主宅', ['沈知韫', '徐念薇'], [
            {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '这份遗嘱的事，你不必多问。'}
        ])
        self.assertTrue(res_ok['ok'])
        # Public fact R02 (mentioning 遗嘱 generically without K01 secret) when 沈知韫 is absent MUST NOT false-positive!
        res_r02 = sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], [
            {'kind': 'dialogue', 'speaker': '苏婉青', 'text': '公公当年立遗嘱那阵子，家里气氛就一直很紧绷。'}
        ])
        self.assertTrue(res_r02['ok'])
        # Compound K01 phrasing by 苏婉青 MUST still be blocked!
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], [
                {'kind': 'dialogue', 'speaker': '苏婉青', 'text': '其实遗嘱里写着家产留给志北一个人。'}
            ])

    def test_T05_zone1_sha_stable_and_stage2_rules_and_catalog_clean(self):
        files = self.svc.store._files()
        mem = files[rr.FILES[0]].decode('utf-8')
        state = ir.view(self.svc.store, files)
        z1_a = sc.build_zone1_scene(self.tmp, state, state['cast'], [], memory_text=mem, extra_text='今天天气不错', mode='dual_stream_v2')
        z1_b = sc.build_zone1_scene(self.tmp, state, state['cast'], [], memory_text=mem, extra_text='大哥最近查岗吗', mode='dual_stream_v2')
        self.assertEqual(sc._digest_text(z1_a), sc._digest_text(z1_b))

        z0 = sc.build_zone0_global(self.tmp, mode='dual_stream_v2')
        self.assertNotIn('craft_note', z0)
        self.assertNotIn('须在SYSTEM_LOG写明事由', z0)

        cat = sc.compile_event_catalog(self.tmp, live_mode=True)
        host_tags = ' '.join(cat['host_events'])
        for banned in ('体力_日常消耗', '体力_激烈交欢', '体力_次日休息', '兑换道具_X', '连续守护5回合'):
            self.assertNotIn(banned, host_tags)

        sys_rules = sc.compile_knowledge_rules(self.tmp, state, mem, '', mode='settlement')
        keys = {b['key'] for b in sys_rules}
        self.assertIn('sys.pregnancy', keys)
        self.assertIn('sys.vigilance', keys)

    def test_T06_qualitative_brief_full_and_frontend_hides_discovery_prob(self):
        mem_path = self.tmp / rr.FILES[0]
        mem = mem_path.read_text(encoding='utf-8')
        engine = rr._engine(self.tmp, self.tmp)
        mem = engine._simulate_panel(mem, {
            '系统宿主': {'商业嗅觉': 65},
            '沈知韫': {'欲望': 86, '高潮': 75, '体力': 32, '被动': 'Lv.2'},
        })
        mem = re.sub(r'▶ 沈知韫\n  - 无', '▶ 沈知韫\n  - [持续_体液锁定] 剩余时效: 20回合 (效果: 欲望死锁不低于85)', mem, count=1)
        mem = re.sub(r'徐承邺位置：外地', '徐承邺位置：徐家住宅', mem, count=1)
        mem = re.sub(r'徐承邺_沈知韫：警惕 0 \| 发现 0 \| 发现几率 0', '徐承邺_沈知韫：警惕 75 | 发现 1 | 发现几率 82', mem, count=1)
        mem = sp.write_intel_block(mem, {'held': ['INTEL-001'], 'consumed': [], 'su_ab_contacts': 0, 'leverage_armed': 'INTEL-001'})
        mem_path.write_text(mem, encoding='utf-8')

        files = self.svc.store._files()
        state = ir.view(self.svc.store, files)
        # Frontend view() exposes vigilance position/targets WITHOUT 发现几率
        self.assertEqual(state['vigilance']['position'], '徐家住宅')
        self.assertNotIn('prob', json.dumps(state['vigilance']))
        self.assertNotIn('发现几率', json.dumps(state['vigilance'], ensure_ascii=False))
        self.assertEqual(state['buffs']['沈知韫'][0]['name'], '持续_体液锁定')

        brief = sc.compile_state_qualitative_brief(state, mem, intel_catalog=sp.load_intel_catalog(self.tmp))
        for expected in ('成为变量', '深圳账目异常', '认知欺诈滤镜', '持续_体液锁定', '欲望处于高位滞留', '高潮累积75%', '高危暴露压迫'):
            self.assertIn(expected, brief)

    def test_T07_weekday_and_offstage_schedule_reconciliation(self):
        # Start in wanqing_friday_visit: Friday 17:00, player & 苏婉青 & 沈知韫 at 徐家主宅
        reset_clean_save(self.tmp)
        blindbox.initialize_prologue(self.tmp, 'init-fri-visit', scenario_id='wanqing_friday_visit')
        svc = ss.StoryService(self.tmp)
        svc.start()
        w0 = ir.view(svc.store)
        self.assertEqual(w0['weekday'], '周五')
        self.assertEqual(w0['presence']['苏婉青']['location'], '徐家主宅')

        # Turn 1: Move player to 市中心顶层公寓 at Friday 21:00 (past 20:30 visit window)
        # 苏婉青 is now OFFSTAGE (at 徐家主宅 while player moved to 公寓), so she MUST return to 市中心顶层公寓!
        run_action_turn(
            svc, text='前往市中心顶层公寓', option_id='CUSTOM', category='A',
            operation={'code': 'move_player', 'destination': '市中心顶层公寓'},
            messages=[{'kind': 'narration', 'speaker': '', 'text': '徐志北乘车来到市中心顶层公寓，夜色已经沉了下来。'}],
            clock={'day': 1, 'time': '21:00'},
            conditions={'intensity': 'A', 'effective_progress': True, 'scene': '市中心顶层公寓', 'npc': None,
                        'action_changed': True, 'stress_signals': 0, 'breakout_triggered': []},
            req_id='move-apt-1',
        )
        w1 = ir.view(svc.store)
        self.assertEqual(w1['presence']['苏婉青']['location'], '市中心顶层公寓')
        self.assertEqual(w1['presence']['徐念薇']['location'], '工作室')  # Friday 17:00-21:59 at off-campus studio

        # Turn 1b: Friday 22:30 -> offstage 徐念薇 returns to 徐家主宅 for the night
        run_action_turn(
            svc, text='和嫂子聊两句晚间安排', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '苏婉青', 'text': '时间不早了，你也早点休息。'}],
            clock={'day': 1, 'time': '22:30'},
            req_id='fri-late-1b',
        )
        w1b = ir.view(svc.store)
        self.assertEqual(w1b['presence']['徐念薇']['location'], '徐家主宅')

        # Turn 2: Cross to Saturday (day 2, 10:00) while player is at 市中心顶层公寓 with 苏婉青
        # 徐念薇 (offstage) stays at 徐家主宅 (weekend!), while co-present 苏婉青 stays put!
        run_action_turn(
            svc, text='和嫂子吃早餐', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '苏婉青', 'text': '周六早上难得清静，先喝杯热咖啡吧。'}],
            clock={'day': 2, 'time': '10:00'},
            req_id='sat-morn-2',
        )
        w2 = ir.view(svc.store)
        self.assertEqual(w2['weekday'], '周六')
        self.assertEqual(w2['presence']['徐念薇']['location'], '徐家主宅')
        self.assertEqual(w2['presence']['苏婉青']['location'], '市中心顶层公寓')

    def test_T08_xu_chengye_home_cast_and_offstage_vigilance_depravity_events(self):
        mem_path = self.tmp / rr.FILES[0]
        mem = mem_path.read_text(encoding='utf-8')
        mem = re.sub(r'徐承邺位置：外地', '徐承邺位置：徐家住宅', mem, count=1)
        mem_path.write_text(mem, encoding='utf-8')

        # 徐承邺 now appears in scene_cast at 徐家主宅 and can speak legally!
        w = ir.view(self.svc.store)
        self.assertIn('徐承邺', w['cast'])

        # Submit action with [D:徐承邺], offstage VIGILANCE_04 targeting 苏婉青, and DEPRAVITY_02 targeting on-stage heroine 沈知韫
        receipt = run_action_turn(
            self.svc, text='在书房应付大哥试探', option_id='B', category='B',
            messages=[
                {'kind': 'dialogue', 'speaker': '徐承邺', 'text': '[low restrained voice] 这么晚了，志北还在母亲书房里谈什么？'},
                {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '不过是核对几份旧账，刚巧婉青下午也打过电话提了一嘴。'},
            ],
            clock={'day': 1, 'time': '23:15'},
            events=[
                {'group': 'vigilance_events', 'target': '苏婉青', 'tags': ['眼线汇报'], 'evidence': '刚巧婉青下午也打过电话提了一嘴。'},
                {'group': 'depravity_events', 'target': '沈知韫', 'tags': ['死亡查岗_沉沦期'], 'evidence': '这么晚了，志北还在母亲书房里谈什么？'},
            ],
            req_id='xu-home-1',
        )
        self.assertEqual(receipt['status'], 'committed')
        after_mem = mem_path.read_text(encoding='utf-8')
        self.assertGreater(rr._engine(self.tmp, self.tmp)._read_attr_value(after_mem, '沈知韫', '堕落'), 0)
        self.assertNotIn('[徐承邺] 堕落', after_mem)

    def test_T09_breakout_hint_gating_and_micro_state_auto_derivation(self):
        mem_path = self.tmp / rr.FILES[0]
        mem = mem_path.read_text(encoding='utf-8')
        self.assertIsNone(sc.compile_breakout_hint(mem))
        mem_hi = re.sub(r'破局_日常冗余:\s*0', '破局_日常冗余: 5', mem)
        hint = sc.compile_breakout_hint(mem_hi)
        self.assertIsNotNone(hint)
        self.assertTrue(any('破局_日常冗余' in r for r in hint['triggered_reasons']))

        # Warm A turn activates momentary_ease automatically
        run_action_turn(
            self.svc, text='给母亲倒热茶', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '谢谢你，茶温刚刚好。'}],
            clock={'day': 1, 'time': '23:10'},
            events=[{'group': 'host_events', 'target': '系统宿主', 'tags': ['日常_信任建立'], 'evidence': '谢谢你，茶温刚刚好。'}],
            req_id='micro-warm-1',
        )
        micro = rr._current_micro(mem_path.read_text(encoding='utf-8'))
        self.assertTrue(micro['沈知韫']['momentary_ease'])

    def test_T10_passive_skill_deterministic_exp_upgrade(self):
        complete_current_playback(self.svc)
        mem_path = self.tmp / rr.FILES[0]
        engine = rr._engine(self.tmp, self.tmp)
        # Give host 80 EXP
        mem_path.write_text(engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {'系统宿主': {'经验值': 80}}), encoding='utf-8')
        snap = self.svc.interaction_snapshot()
        # Upgrade Lv.0 -> Lv.1 (costs 20 EXP)
        r1 = self.svc.upgrade_passive({
            'request_id': 'pas-1', 'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'], 'target': '沈知韫',
        })
        self.assertEqual(r1['receipt']['level_after'], 'Lv.1')
        self.assertEqual(r1['receipt']['exp_after'], 60)
        # Idempotent replay
        r1_rep = self.svc.upgrade_passive({
            'request_id': 'pas-1', 'base_revision': snap['revision'],
            'save_epoch': snap['save_epoch'], 'target': '沈知韫',
        })
        self.assertTrue(r1_rep['replayed'])
        # Upgrade Lv.1 -> Lv.2 (costs 50 EXP, leaving 10 EXP)
        r2 = self.svc.upgrade_passive({
            'request_id': 'pas-2', 'base_revision': r1['snapshot']['revision'],
            'save_epoch': r1['snapshot']['save_epoch'], 'target': '沈知韫',
        })
        self.assertEqual(r2['receipt']['level_after'], 'Lv.2')
        self.assertEqual(r2['receipt']['exp_after'], 10)
        # Echo persisted in TXT
        echoes = sp.parse_shop_echo_block(mem_path.read_text(encoding='utf-8'))['echoes']
        self.assertTrue(any(e['kind'] == 'passive_upgraded' for e in echoes))
        # Insufficient EXP for Lv.3 (110 EXP) fails cleanly
        with self.assertRaises(rr.RoundError):
            self.svc.upgrade_passive({
                'request_id': 'pas-3', 'base_revision': r2['snapshot']['revision'],
                'save_epoch': r2['snapshot']['save_epoch'], 'target': '沈知韫',
            })

    def test_T11_commercial_intel_and_business_leverage_end_to_end(self):
        complete_current_playback(self.svc)
        mem_path = self.tmp / rr.FILES[0]
        engine = rr._engine(self.tmp, self.tmp)
        # Set host 商业嗅觉=65, 沈知韫 好感=50 羞耻=90 (so SHAME_04 triggers violation_drop < 0)
        mem = engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {
            '系统宿主': {'商业嗅觉': 65},
            '沈知韫': {'好感': 50, '羞耻': 90},
        })
        mem_path.write_text(mem, encoding='utf-8')
        snap = self.svc.interaction_snapshot()

        # 1. Acquire INTEL-001 (min_biz=10) & INTEL-003 (min_biz=60)
        r_a1 = self.svc.acquire_intel({'request_id': 'int-1', 'base_revision': snap['revision'], 'save_epoch': snap['save_epoch'], 'intel_id': 'INTEL-001'})
        r_a3 = self.svc.acquire_intel({'request_id': 'int-3', 'base_revision': r_a1['snapshot']['revision'], 'save_epoch': r_a1['snapshot']['save_epoch'], 'intel_id': 'INTEL-003'})
        self.assertEqual(set(r_a3['snapshot']['world']['intel']['held']), {'INTEL-001', 'INTEL-003'})

        # 2. INTEL-002 blocked before 3 Su Wanqing A/B contacts
        with self.assertRaises(rr.RoundError):
            self.svc.acquire_intel({'request_id': 'int-2-fail', 'base_revision': r_a3['snapshot']['revision'], 'save_epoch': r_a3['snapshot']['save_epoch'], 'intel_id': 'INTEL-002'})

        # 3. Arm business leverage with INTEL-001
        r_arm = self.svc.toggle_leverage({'request_id': 'lev-1', 'base_revision': r_a3['snapshot']['revision'], 'save_epoch': r_a3['snapshot']['save_epoch'], 'action': 'arm', 'intel_id': 'INTEL-001'})
        self.assertEqual(r_arm['snapshot']['world']['intel']['leverage_armed'], 'INTEL-001')

        # 4. Run a gentle A turn -> leverage MUST NOT be wasted!
        run_action_turn(
            self.svc, text='聊几句项目进度', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '下周二再看这份报表。'}],
            clock={'day': 1, 'time': '23:10'},
            req_id='gentle-no-waste',
        )
        istate_after_a = sp.parse_intel_block(mem_path.read_text(encoding='utf-8'))
        self.assertEqual(istate_after_a['leverage_armed'], 'INTEL-001')
        self.assertIn('INTEL-001', istate_after_a['held'])

        # 5. Run C turn with SHAME_04 (C烈度_重度): baseline drop at aff=50 is -10 -> halved to -5 (aff 50 -> 45), INTEL-001 consumed and 2 shield charges remain!
        aff_before = engine._read_attr_value(mem_path.read_text(encoding='utf-8'), '沈知韫', '好感')
        run_action_turn(
            self.svc, text='强势逼近试探', option_id='C', category='C',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '[voice breaking] 你放手，别越界！'}],
            clock={'day': 1, 'time': '23:25'},
            events=[{'group': 'shame_events', 'target': '沈知韫', 'tags': ['C烈度_重度'], 'evidence': '你放手，别越界！'}],
            req_id='c-leverage-fire',
        )
        aff_after = engine._read_attr_value(mem_path.read_text(encoding='utf-8'), '沈知韫', '好感')
        # Normal SHAME_04 drop at aff=50 is -10 (would be 40); halved to -5 -> 45!
        self.assertEqual(aff_after, aff_before - 5)
        istate_after_c = sp.parse_intel_block(mem_path.read_text(encoding='utf-8'))
        self.assertEqual(istate_after_c['leverage_armed'], '')
        self.assertEqual(istate_after_c['leverage_charges'], 2)
        self.assertNotIn('INTEL-001', istate_after_c['held'])
        self.assertIn('INTEL-001', istate_after_c['consumed'])

        # 6. Direct card play with INTEL-003 targeting 沈知韫 -> +5 affection & INTEL-003 consumed!
        aff_pre3 = engine._read_attr_value(mem_path.read_text(encoding='utf-8'), '沈知韫', '好感')
        run_action_turn(
            self.svc, text='亮出徐承邺收购盲区线索', option_id='A', category='A',
            messages=[{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '你连并购估值盲区都查到了？这份材料帮了大忙。'}],
            clock={'day': 1, 'time': '23:40'},
            intel_used={'id': 'INTEL-003', 'target': '沈知韫', 'evidence': '你连并购估值盲区都查到了？这份材料帮了大忙。'},
            req_id='intel-direct-3',
        )
        aff_post3 = engine._read_attr_value(mem_path.read_text(encoding='utf-8'), '沈知韫', '好感')
        self.assertEqual(aff_post3, aff_pre3 + 5)
        istate_final = sp.parse_intel_block(mem_path.read_text(encoding='utf-8'))
        self.assertIn('INTEL-003', istate_final['consumed'])
        self.assertNotIn('INTEL-003', istate_final['held'])

    def test_T12_su_ab_contacts_accumulate_and_unlock_intel_002(self):
        reset_clean_save(self.tmp)
        blindbox.initialize_prologue(self.tmp, 'init-su-ab', scenario_id='wanqing_apartment_morning')
        svc = ss.StoryService(self.tmp)
        svc.start()
        mem_path = self.tmp / rr.FILES[0]
        engine = rr._engine(self.tmp, self.tmp)
        mem_path.write_text(engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {'系统宿主': {'商业嗅觉': 35}}), encoding='utf-8')
        for idx in range(1, 4):
            run_action_turn(
                svc, text=f'和嫂子闲聊第{idx}次', option_id='A', category='A',
                messages=[{'kind': 'dialogue', 'speaker': '苏婉青', 'text': f'慢慢吃，别急（第{idx}段）。'}],
                clock={'day': 1, 'time': f'09:{10*idx:02d}'},
                req_id=f'su-ab-{idx}',
            )
        complete_current_playback(svc)
        snap = svc.interaction_snapshot()
        self.assertEqual(snap['world']['intel']['su_ab_contacts'], 3)
        res = svc.acquire_intel({'request_id': 'int-2-ok', 'base_revision': snap['revision'], 'save_epoch': snap['save_epoch'], 'intel_id': 'INTEL-002'})
        self.assertIn('INTEL-002', res['snapshot']['world']['intel']['held'])

    def test_T13_flask_http_routes_end_to_end(self):
        from flask import Flask
        complete_current_playback(self.svc)
        mem_path = self.tmp / rr.FILES[0]
        engine = rr._engine(self.tmp, self.tmp)
        mem_path.write_text(engine._simulate_panel(mem_path.read_text(encoding='utf-8'), {
            '系统宿主': {'经验值': 30, '商业嗅觉': 65, '积分': 10},
        }), encoding='utf-8')
        app = Flask(__name__)
        ss.register_story_routes(app, self.tmp)
        client = app.test_client()

        live = client.get('/api/story/live')
        self.assertEqual(live.status_code, 200)
        d0 = live.get_json()
        self.assertEqual(d0['world']['weekday'], '周五')
        self.assertIn('vigilance', d0['world'])
        self.assertIn('intel', d0['world'])
        self.assertIn('passive_tiers', d0['world'])

        hdrs = {'X-Story-Client': '1'}
        # 1. HTTP passive upgrade
        r1 = client.post('/api/story/passive/upgrade', headers=hdrs, json={
            'request_id': 'http-pas-1', 'base_revision': d0['revision'],
            'save_epoch': d0['save_epoch'], 'target': '沈知韫',
        })
        self.assertEqual(r1.status_code, 200)
        j1 = r1.get_json()
        self.assertEqual(j1['receipt']['level_after'], 'Lv.1')

        # 2. HTTP intel acquire
        r2 = client.post('/api/story/intel/acquire', headers=hdrs, json={
            'request_id': 'http-int-1', 'base_revision': j1['snapshot']['revision'],
            'save_epoch': j1['snapshot']['save_epoch'], 'intel_id': 'INTEL-001',
        })
        self.assertEqual(r2.status_code, 200)
        j2 = r2.get_json()
        self.assertIn('INTEL-001', j2['snapshot']['world']['intel']['held'])

        # 3. HTTP business leverage arm & disarm
        r3 = client.post('/api/story/intel/leverage', headers=hdrs, json={
            'request_id': 'http-lev-1', 'base_revision': j2['snapshot']['revision'],
            'save_epoch': j2['snapshot']['save_epoch'], 'action': 'arm', 'intel_id': 'INTEL-001',
        })
        self.assertEqual(r3.status_code, 200)
        j3 = r3.get_json()
        self.assertEqual(j3['snapshot']['world']['intel']['leverage_armed'], 'INTEL-001')

        r4 = client.post('/api/story/intel/leverage', headers=hdrs, json={
            'request_id': 'http-lev-2', 'base_revision': j3['snapshot']['revision'],
            'save_epoch': j3['snapshot']['save_epoch'], 'action': 'disarm', 'intel_id': '',
        })
        self.assertEqual(r4.status_code, 200)
        self.assertEqual(r4.get_json()['snapshot']['world']['intel']['leverage_armed'], '')


if __name__ == '__main__':
    unittest.main(verbosity=2)

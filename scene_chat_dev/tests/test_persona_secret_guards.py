"""Comprehensive regression suite for persona stability (anti-OOC), hidden-secret isolation,
subtext history sanitization, two-tier guardrails, awaiting_review state machine, and Batch 2 calibration."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import interaction_runtime as ir
import round_runtime as rr
import story_compiler as sc
import story_progression as sp
import story_service as ss
from test_phase_ab_linkage import complete_current_playback, reset_clean_save

_opening_spec = importlib.util.spec_from_file_location('opening_box_guards', ROOT / '存档开局随机盲盒.py')
opening = importlib.util.module_from_spec(_opening_spec)
_opening_spec.loader.exec_module(opening)


def _copy_project(dst: Path):
    for rel in (
        'txt文件',
        '存档',
        'injection_core.py',
        'interaction_runtime.py',
        'relationship_query.py',
        'round_runtime.py',
        'save_store.py',
        'story_compiler.py',
        'story_progression.py',
        'story_reading.py',
        'scene_chat.py',
        'story_service.py',
    ):
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, dst / rel, ignore=shutil.ignore_patterns('.story-reading', '__pycache__'))
        elif src.is_file():
            shutil.copy2(src, dst / rel)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class PersonaAndSecretGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='persona_guard_'))
        _copy_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. Zone 1 physical desensitization, stage slicing & KV invariance
    # ------------------------------------------------------------------
    def test_01_zone1_physical_desensitization_unlock_and_stage_slicing(self):
        state_su = {
            'location': '市中心顶层公寓',
            'cast': ['苏婉青'],
            'panels': ['[苏婉青] 好感 50 | 羞耻 96 | 堕落 0 | 欲望 0 | 体力 100'],
            'mechanics': {'secrets_unlocked': []},
        }
        z1_su_locked = sc.build_zone1_scene(self.tmp, state_su, ['苏婉青'], [], '', mode='dual_stream_v2')
        for forbidden in ('眼线', '盯梢', '倒戈', '被揭穿', '尤物', '高堕落深水区', '打听妈见了谁'):
            self.assertNotIn(forbidden, z1_su_locked, f'Locked Su Wanqing Zone 1 must not contain {forbidden!r}')
        self.assertIn('【台面与回避边界】', z1_su_locked)
        self.assertIn('【当前阶段亲密心理边界】', z1_su_locked)
        self.assertIn('【表达节奏与行为边界】', z1_su_locked)
        self.assertNotIn('沉溺于被真心凝视', z1_su_locked, 'Stage 1 must not include Stage 3 deep-fall spine')

        # Unlock INTEL-002 -> seamlessly switches to unlocked branch
        state_su_unlocked = dict(state_su, mechanics={'secrets_unlocked': ['INTEL-002']})
        z1_su_unlocked = sc.build_zone1_scene(self.tmp, state_su_unlocked, ['苏婉青'], [], '', mode='dual_stream_v2')
        self.assertIn('【已解锁暗线态势】', z1_su_unlocked)
        self.assertIn('眼线身份已被宿主当面揭穿', z1_su_unlocked)

        # Stage 3 spine slicing
        state_su_s3 = dict(state_su, panels=['[苏婉青] 好感 88 | 羞耻 30 | 堕落 45 | 欲望 60 | 体力 80'])
        z1_su_s3 = sc.build_zone1_scene(self.tmp, state_su_s3, ['苏婉青'], [], '', mode='dual_stream_v2')
        self.assertIn('沉溺于被真心凝视', z1_su_s3)
        self.assertNotIn('既怕背叛婚姻又不敢得罪小叔子', z1_su_s3)

        # Shen Zhiyun locked Zone 1 check
        state_shen = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'panels': ['[沈知韫] 好感 82 | 羞耻 98 | 堕落 0 | 欲望 0 | 体力 100'],
            'mechanics': {'secrets_unlocked': []},
        }
        z1_shen = sc.build_zone1_scene(self.tmp, state_shen, ['沈知韫'], [], '', mode='dual_stream_v2')
        for forbidden in ('绝望的守密者', '卸下董事长铠甲', '遗嘱秘密', '深圳分部'):
            self.assertNotIn(forbidden, z1_shen, f'Locked Shen Zhiyun Zone 1 must not contain {forbidden!r}')

        # Xu Nianwei locked Zone 1 check
        state_xu = {
            'location': '工作室',
            'cast': ['徐念薇'],
            'panels': ['[徐念薇] 好感 48 | 羞耻 99 | 堕落 0 | 欲望 0 | 体力 100'],
            'mechanics': {'secrets_unlocked': []},
        }
        z1_xu = sc.build_zone1_scene(self.tmp, state_xu, ['徐念薇'], [], '', mode='dual_stream_v2')
        for forbidden in ('坠落的艺术神明', '孤傲倾泻成带刺', '赞助暗箱', '被人动了手脚'):
            self.assertNotIn(forbidden, z1_xu, f'Locked Xu Nianwei Zone 1 must not contain {forbidden!r}')

    def test_02_zone1_kv_cache_invariance_within_stage_bucket(self):
        st_t1 = {
            'location': '市中心顶层公寓',
            'cast': ['苏婉青'],
            'panels': ['[苏婉青] 好感 50 | 羞耻 96 | 堕落 0 | 欲望 0 | 体力 100'],
            'mechanics': {'secrets_unlocked': []},
        }
        st_t2 = {
            'location': '市中心顶层公寓',
            'cast': ['苏婉青'],
            'panels': ['[苏婉青] 好感 55 | 羞耻 90 | 堕落 5 | 欲望 12 | 体力 94'],
            'mechanics': {'secrets_unlocked': []},
        }
        z1_t1 = sc.build_zone1_scene(self.tmp, st_t1, ['苏婉青'], [], '', mode='dual_stream_v2')
        z1_t2 = sc.build_zone1_scene(self.tmp, st_t2, ['苏婉青'], [], '', mode='dual_stream_v2')
        self.assertEqual(_sha(z1_t1), _sha(z1_t2), 'Zone 1 SHA-256 must stay 100% byte-identical within same stage bucket')

        # Budgets remain strictly respected
        z0 = sc.build_zone0_global(self.tmp, mode='dual_stream_v2', protagonist_style='faithful')
        self.assertLess(len(z0), 9200)
        st3 = {
            'location': '徐家主宅',
            'cast': ['沈知韫', '苏婉青', '徐念薇'],
            'panels': [
                '[沈知韫] 好感 82 | 羞耻 98 | 堕落 0 | 欲望 0 | 体力 100',
                '[苏婉青] 好感 50 | 羞耻 96 | 堕落 0 | 欲望 0 | 体力 100',
                '[徐念薇] 好感 48 | 羞耻 99 | 堕落 0 | 欲望 0 | 体力 100',
            ],
            'mechanics': {'secrets_unlocked': []},
        }
        z1_3 = sc.build_zone1_scene(self.tmp, st3, st3['cast'], [], '', mode='dual_stream_v2')
        self.assertLess(len(z1_3), 6800)

    # ------------------------------------------------------------------
    # 2. Subtext history sanitization
    # ------------------------------------------------------------------
    def test_03_subtext_sanitized_from_history_and_continuity_while_action_kept(self):
        raw_hist = [{
            'round': 1,
            'input': '问她手机响了什么',
            'messages': [
                {'kind': 'action', 'speaker': '苏婉青', 'text': '她｛表面端庄微笑｜指尖却悄悄攥紧手机边缘｝。'},
                {'kind': 'dialogue', 'speaker': '苏婉青', 'text': '｛没什么，就快递短信。｜还好没被发现我替承邺盯着主宅｝'},
            ],
        }]
        state = {
            'location': '市中心顶层公寓',
            'cast': ['苏婉青'],
            'panels': ['[苏婉青] 好感 50 | 羞耻 96 | 堕落 0 | 欲望 0 | 体力 100'],
            'presence': {'徐志北': {'location': '市中心顶层公寓'}, '苏婉青': {'location': '市中心顶层公寓'}},
            'mechanics': {'secrets_unlocked': []},
        }
        proj = {'text': '【L1】测试', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        delta_str = sc.build_user_delta(
            self.tmp, state, proj, raw_hist, raw_hist,
            '继续聊天', None, None, None, {'before': 100, 'reserved': 5},
            {'clock': {'day': 1, 'time': '21:10'}, 'memory_round': 1, 'phase': 'ready'},
            '', include_full_anchor=True, mode='dual_stream_v2',
            recent_room_continuity=raw_hist,
            persona_correction='苏婉青须保持含蓄短答。',
        )
        self.assertNotIn('还好没被发现我替承邺盯着主宅', delta_str, 'Right-hand dialogue subtext MUST be stripped from Zone 2 history')
        self.assertIn('没什么，就快递短信。', delta_str, 'Spoken left-hand surface dialogue MUST be preserved')
        self.assertIn('指尖却悄悄攥紧手机边缘', delta_str, 'Visible action micro-slip MUST be preserved')
        parsed_delta = json.loads(delta_str)
        self.assertEqual(parsed_delta.get('persona_drift_correction'), '苏婉青须保持含蓄短答。')

    # ------------------------------------------------------------------
    # 3. Two-tier guardrails & Stage 2 signal extraction
    # ------------------------------------------------------------------
    def test_04_two_tier_guardrails_and_settlement_signal_extraction(self):
        # Tier 1: K01 will-secret still hard-rejects
        with self.assertRaises(rr.RoundError):
            sc.guardrail_check(
                self.tmp, '徐家主宅', ['沈知韫', '苏婉青'],
                [{'kind': 'dialogue', 'speaker': '沈知韫', 'text': '其实遗嘱指定了志北是唯一合法继承人。'}],
                secrets_unlocked=(),
            )

        # Tier 2: Su Wanqing spy leak returns review_signals (does NOT raise RoundError)
        leaky_msgs = [
            {'kind': 'action', 'speaker': '苏婉青', 'text': '她低声凑近了半步。'},
            {'kind': 'dialogue', 'speaker': '苏婉青', 'text': '你哥盯得很紧，需要你告诉我一些情报好应付他。'},
        ]
        g_locked = sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], leaky_msgs, secrets_unlocked=())
        self.assertTrue(g_locked['ok'])
        self.assertIn('review_signals', g_locked)
        self.assertEqual(g_locked['review_signals'][0]['code'], 'S01_SU_SPY')
        self.assertEqual(g_locked['review_signals'][0]['kind'], 'secret_leak')

        # Valid airtight surface + private right-hand subtext must NOT false-positive Tier 2
        safe_subtext_msgs = [
            {'kind': 'dialogue', 'speaker': '苏婉青', 'text': '｛没事，快递短信。｜还好没让他知道我替承邺盯着家里｝'},
        ]
        g_safe = sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], safe_subtext_msgs, secrets_unlocked=())
        self.assertEqual(g_safe, {'ok': True, 'warnings': []})

        # After INTEL-002 unlock, the same line produces 0 Tier-2 alerts
        g_unlocked = sc.guardrail_check(self.tmp, '市中心顶层公寓', ['苏婉青'], leaky_msgs, secrets_unlocked=('INTEL-002',))
        self.assertEqual(g_unlocked, {'ok': True, 'warnings': []})

        # Stage 2 quality_flags extraction
        s2_sigs = sc.extract_settlement_review_signals(
            self.tmp,
            [
                'option_stagnation',
                'persona_ooc:苏婉青:内敛少奶奶变直白话痨大段倾诉',
                'secret_premature_leak:徐念薇:主动点破画室旧画画中人',
            ],
            secrets_unlocked=(),
        )
        self.assertEqual(len(s2_sigs), 2)
        kinds = {s['kind'] for s in s2_sigs}
        self.assertEqual(kinds, {'persona_ooc', 'secret_leak'})

        # Suppressed when secret already unlocked
        s2_suppressed = sc.extract_settlement_review_signals(
            self.tmp, ['secret_premature_leak:苏婉青:提及替丈夫留意主宅'], secrets_unlocked=('INTEL-002',),
        )
        self.assertEqual(s2_suppressed, [])

        # Payload builder cleans Drama 3 tags & subtext in excerpt
        payload = sc.build_review_payload(
            g_locked['review_signals'] + s2_sigs,
            [{'kind': 'dialogue', 'speaker': '苏婉青', 'text': '[声音轻柔] <soft>需要你告诉我一些情报。</soft>'}],
            regen_count=1,
        )
        self.assertEqual(payload['title'], '暗线险些走漏，待你裁夺')
        self.assertEqual(payload['regen_count'], 1)
        self.assertTrue(payload['excerpt'])
        self.assertNotIn('<soft>', payload['excerpt'][0])
        self.assertNotIn('[声音轻柔]', payload['excerpt'][0])

    # ------------------------------------------------------------------
    # 4. Full awaiting_review state machine & stamina/escrow safety
    # ------------------------------------------------------------------
    def _init_wanqing_service(self):
        reset_clean_save(self.tmp)
        svc = ss.StoryService(self.tmp)
        with svc.store._locked():
            opening.initialize_prologue(self.tmp, 'guard-init', 'wanqing_apartment_night')
        complete_current_playback(svc)
        model_obj = {
            'key': '["CHAT","p","m"]', 'function_type': 'CHAT',
            'provider_id': 'p', 'provider_name': 'P', 'model_id': 'm',
            'pricing_configured': True,
        }
        svc.worker_control({
            'runtime': {
                'phase': 'ready', 'running': True, 'busy': False, 'last_error': '',
                'plugin_version': '2.3.1', 'model': model_obj,
                'session': {'policy': 'continuous', 'chat_id': 'c1', 'generation': 1, 'reset_reason': 'init'},
            },
            'ack_id': None, 'ack_error': '',
        })
        return svc, model_obj

    def _run_turn_submit(self, svc, model_obj, req_id, fg_text, quality_flags=None, *,
                         create_new=True, clock_time='21:10'):
        if create_new:
            snap = svc.interaction_snapshot()
            seg = ir.segment(svc.root, svc.store._files())
            opt_a = seg['decision']['options'][0]['text']
            svc.create({
                'request_id': req_id, 'base_revision': snap['revision'],
                'save_epoch': snap['save_epoch'], 'entry_mode': ir.MODE,
                'action': opt_a, 'selection': {'segment_id': seg['id'], 'option_id': 'A'},
            })
        task = svc.claim({'model': model_obj})['task']
        mat = svc.material(req_id, {
            'lease': task['lease'], 'chat_id': 'c1', 'participant_id': 'model:chat',
            'delivery_version': 2, 'protocol_mode': 'dual_stream_v2', 'is_fresh_session': True,
        })
        settle_obj = {
            'operation': None, 'handoff': '',
            'checks': {'intent': '日常交谈', 'knowledge': '在场信息', 'action': '无操作', 'pace': '交还抉择'},
            'resolution': {
                'category': 'A', 'basis': '日常公寓对话',
                'clock': {'day': 1, 'time': clock_time, 'basis': '交谈约十分钟'},
                'events': [],
                'memory': {'fact': '', 'anchor_ops': [], 'chronicle_digest': ''},
                'conditions': {
                    'intensity': 'A', 'effective_progress': True,
                    'scene': '市中心顶层公寓', 'npc': '苏婉青',
                    'action_changed': True, 'stress_signals': 0, 'breakout_triggered': [],
                },
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
                'task': None, 'items': [],
            },
            'quality_flags': list(quality_flags or []),
        }
        proof = {
            'api': 'Tools.Chat.sendMessageStreaming', 'chat_id': 'c1', 'participant_id': 'model:chat',
            'workspace': str(self.tmp),
            'outcome': {'type': 'committed', 'status': 'completed', 'userMessageTimestamp': 100, 'assistant': {'messageTimestamp': 101}},
            'snapshot_message_timestamp': 101,
            'tools': [],
            'delivery': {**mat['delivery'], 'user_message_timestamp': 100},
        }
        res = svc.result(req_id, {
            'lease': task['lease'],
            'text': json.dumps({'dual_stage_version': 1, 'foreground_text': fg_text, 'settlement': settle_obj}, ensure_ascii=False),
            'conversation_audit': proof,
        })
        return res, mat

    def test_05_awaiting_review_ask_accept_with_correction_and_oneshot_consume(self):
        svc, model_obj = self._init_wanqing_service()
        before_seq = svc.store._ledger()['sequence']
        leaky_fg = (
            '[A:苏婉青] 她咬了咬唇，把手机扣回茶几。\n'
            '[D:苏婉青] 你哥盯得很紧，需要你告诉我一些情报好应付他。\n'
            '---DECISION---\nPROMPT: 客厅一时安静。\nA: 岔开话题聊茶点\nB: 递过温水安抚\nC: 逼近追问细节'
        )
        res, _ = self._run_turn_submit(svc, model_obj, 'req-rev-ask-1', leaky_fg)
        self.assertEqual(res['task']['status'], 'awaiting_review')
        self.assertIn('review', res['task'])
        self.assertEqual(res['task']['review']['title'], '暗线险些走漏，待你裁夺')
        self.assertEqual(res['task']['reservation']['status'], 'held')
        # Zero dirty save write while awaiting review
        self.assertEqual(svc.store._ledger()['sequence'], before_seq)

        # _expire() must NOT expire awaiting_review
        with svc.store._locked():
            st = svc._read()
            st['jobs']['req-rev-ask-1']['lease_until'] = 0
            svc._expire(st)
            self.assertEqual(svc._read()['jobs']['req-rev-ask-1']['status'], 'awaiting_review')

        # Concurrent action creation must be blocked while awaiting_review
        snap = svc.interaction_snapshot()
        seg = ir.segment(svc.root, svc.store._files())
        with self.assertRaises(rr.ConflictError):
            svc.create({
                'request_id': 'req-concurrent', 'base_revision': snap['revision'],
                'save_epoch': snap['save_epoch'], 'entry_mode': ir.MODE,
                'action': seg['decision']['options'][0]['text'],
                'selection': {'segment_id': seg['id'], 'option_id': 'A'},
            })

        # Player chooses accept_with_correction -> 0 LLM calls commit + one-shot correction file written
        dec = svc.review_decision('req-rev-ask-1', {'decision': 'accept_with_correction'})
        self.assertEqual(dec['task']['status'], 'committed')
        self.assertEqual(svc.store._ledger()['sequence'], before_seq + 1)
        corr = ir.load_persona_correction(self.tmp, save_epoch=snap['save_epoch'])
        self.assertIsNotNone(corr)
        self.assertIn('苏婉青', corr['hint'])

        # Next turn Zone 2 receives persona_drift_correction, and committing clears it (one-shot)
        complete_current_playback(svc)
        clean_fg = (
            '[A:苏婉青] 她垂下眼理了理衣角，端起茶壶添了半杯热水。\n'
            '[D:苏婉青] 没事，就是快递短信。水凉了，我去换杯热的？\n'
            '---DECISION---\nPROMPT: 她轻声问你。\nA: 顺着聊点心\nB: 帮她接过茶壶\nC: 拉住她手腕'
        )
        res2, mat2 = self._run_turn_submit(svc, model_obj, 'req-rev-ask-2', clean_fg, clock_time='21:20')
        delta2 = json.loads(mat2['input_text'])
        self.assertIn('persona_drift_correction', delta2)
        self.assertIn('苏婉青', delta2['persona_drift_correction'])
        self.assertEqual(res2['task']['status'], 'committed')
        self.assertIsNone(ir.load_persona_correction(self.tmp), 'One-shot correction MUST be cleared after next commit')

    def test_06_awaiting_review_regenerate_and_cancel_stamina_safety(self):
        svc, model_obj = self._init_wanqing_service()
        stamina_initial = sp.stamina(self.tmp, svc.store._files())
        leaky_fg = (
            '[A:苏婉青] 她攥紧手机。\n'
            '[D:苏婉青] 其实我一直是替他盯着主宅的。\n'
            '---DECISION---\nPROMPT: 她看着你。\nA: 聊点心\nB: 递水\nC: 靠近'
        )
        res, _ = self._run_turn_submit(svc, model_obj, 'req-rev-regen', leaky_fg)
        self.assertEqual(res['task']['status'], 'awaiting_review')

        # Player picks regenerate -> refunds old escrow, re-reserves cleanly, requeues with guidance
        reg_res = svc.review_decision('req-rev-regen', {'decision': 'regenerate'})
        self.assertEqual(reg_res['task']['status'], 'queued')
        self.assertEqual(reg_res['task'].get('review_regen_count'), 1)

        # Claiming regenerated job injects targeted persona_drift_correction into Zone 2
        clean_fg = (
            '[A:苏婉青] 她耳根微微泛红，顺手把手机扣进沙发缝里。\n'
            '[D:苏婉青] 没什么，就快递到了。你喝冰的还是常温？\n'
            '---DECISION---\nPROMPT: 空气缓和下来。\nA: 要一杯常温水\nB: 递过披肩\nC: 贴近低声笑问'
        )
        res2, mat2 = self._run_turn_submit(svc, model_obj, 'req-rev-regen', clean_fg, create_new=False)
        delta2 = json.loads(mat2['input_text'])
        self.assertIn('persona_drift_correction', delta2)
        self.assertEqual(res2['task']['status'], 'committed')

        # Now test cancel from awaiting_review -> full stamina refund
        complete_current_playback(svc)
        stamina_before_cancel = sp.stamina(self.tmp, svc.store._files())
        res3, _ = self._run_turn_submit(svc, model_obj, 'req-rev-cancel', leaky_fg, clock_time='21:25')
        self.assertEqual(res3['task']['status'], 'awaiting_review')
        self.assertLess(sp.stamina(self.tmp, svc.store._files()), stamina_before_cancel)

        can_res = svc.review_decision('req-rev-cancel', {'decision': 'cancel'})
        self.assertEqual(can_res['task']['status'], 'cancelled')
        self.assertEqual(sp.stamina(self.tmp, svc.store._files()), stamina_before_cancel)
        self.assertEqual(stamina_initial - 5, stamina_before_cancel)

    def test_07_auto_regen_caps_at_one_and_soft_only_commits_directly(self):
        svc, model_obj = self._init_wanqing_service()
        # Mode: auto_regen
        ir.save_story_prefs(self.tmp, {'drift_review_mode': 'auto_regen'})
        ooc_fg = (
            '[A:苏婉青] 她忽然敞开心扉侃侃而谈。\n'
            '[D:苏婉青] 我心里其实一直特别委屈，今天非要把所有想法都直白告诉你不可。\n'
            '---DECISION---\nPROMPT: 客厅安静。\nA: 点头回应\nB: 倒杯热水\nC: 坐近安抚'
        )
        # First drift -> auto requeues (queued, review_regen_count=1)
        r1, _ = self._run_turn_submit(
            svc, model_obj, 'req-auto-1', ooc_fg,
            quality_flags=['persona_ooc:苏婉青:内敛角色变直白话痨长篇剖析'],
        )
        self.assertEqual(r1['task']['status'], 'queued')
        self.assertEqual(r1['task'].get('review_regen_count'), 1)

        # Second consecutive drift -> MUST NOT infinite-loop; falls back cleanly to awaiting_review!
        r2, _ = self._run_turn_submit(
            svc, model_obj, 'req-auto-1', ooc_fg,
            quality_flags=['persona_ooc:苏婉青:依然过于直白外化'],
            create_new=False,
        )
        self.assertEqual(r2['task']['status'], 'awaiting_review')
        self.assertEqual(r2['task']['review']['regen_count'], 1)
        svc.review_decision('req-auto-1', {'decision': 'cancel'})

        # Mode: soft_only -> commits immediately & writes one-shot persona-correction.json
        ir.save_story_prefs(self.tmp, {'drift_review_mode': 'soft_only'})
        r3, _ = self._run_turn_submit(
            svc, model_obj, 'req-soft-1', ooc_fg,
            quality_flags=['persona_ooc:苏婉青:台词偏直白'],
        )
        self.assertEqual(r3['task']['status'], 'committed')
        corr = ir.load_persona_correction(self.tmp)
        self.assertIsNotNone(corr)
        self.assertEqual(corr['source_request_id'], 'req-soft-1')

    # ------------------------------------------------------------------
    # 5. Batch 2 opening pool, world beats & scene residue health
    # ------------------------------------------------------------------
    def test_08_batch2_openings_world_beats_and_residue_health(self):
        # Openings: zero spoiler phrases
        all_choice_txt = '\n'.join(
            '\n'.join(opts) for opts in opening.OPENING_CHOICES.values()
        )
        for bad in ('特意交代的任务', '催问主宅动静', '追问旧画里藏了谁'):
            self.assertNotIn(bad, all_choice_txt)

        # World beats: BEAT-T1-APT-PHONE-GLOW desensitized, BEAT-T2-CHENGYE-MSG-PRESSURE min_biz >= 10
        beats_data = json.loads((self.tmp / 'txt文件/世界变故库.json').read_text(encoding='utf-8'))
        beats_by_id = {b['id']: b for b in beats_data.get('beats', [])}
        self.assertNotIn('妈这周有没有提南边', beats_by_id['BEAT-T1-APT-PHONE-GLOW']['objective_event'])
        self.assertGreaterEqual(int(beats_by_id['BEAT-T2-CHENGYE-MSG-PRESSURE'].get('min_biz', 0)), 10)

        # format_surprise_directive subtext_leak ironclad cover rule
        sd = sp.format_surprise_directive({
            'triggered': True, 'mode': 'preset_beat', 'tier': 'tier1',
            'category': 'subtext_leak', 'objective_event': '手机屏幕闪了一下。',
        })
        self.assertIn('无害日常敷衍遮掩', sd['rule'])
        self.assertIn('严禁借此主动坦白或交底', sd['rule'])

        # Scene residue table strictly obeys no-smoking lore rule
        for key, desc in sp._SCENE_RESIDUE_TABLE.items():
            self.assertNotIn('烟草', desc, f'Residue {key} violates no-smoking lore')
            self.assertNotIn('吸烟', desc, f'Residue {key} violates no-smoking lore')


if __name__ == '__main__':
    unittest.main()

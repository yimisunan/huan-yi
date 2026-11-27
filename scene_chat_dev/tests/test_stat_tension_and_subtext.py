"""Unit and end-to-end tests for Dual-Axis Tension (SES/SIS), five-gate coy-yield
(`欲拒还迎_嘴硬心软`), dark-box resentment persistence & healing, character-specific
foreground cues, Zone 1 stage2 unlock alignment, and Stage 2 12K budget compliance."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
import injection_core as ic
import interaction_runtime as ir
import round_runtime as rr
import save_store
import story_compiler as sc
import story_progression as sp
import story_service as ss
from test_dual_stage_runtime import _make_workspace, _fg_script, _settlement_payload


def _audit_for(root: Path, delivery: dict, chat_id='chat-tension-1', card_id='card-tension-1', stamp=300):
    outcome = {
        'type': 'committed',
        'status': 'completed',
        'userMessageTimestamp': stamp,
        'assistant': {'messageTimestamp': stamp + 10},
    }
    return {
        'api': 'Tools.Chat.sendMessageStreaming',
        'chat_id': chat_id,
        'participant_id': card_id,
        'workspace': str(root),
        'outcome': outcome,
        'snapshot_message_timestamp': stamp + 10,
        'started_at': 1000,
        'completed_at': 2000,
        'read_passes': [{
            'outcome': outcome,
            'snapshot_message_timestamp': stamp + 10,
            'tool_start': 0,
            'tool_count': 0,
            'started_at': 1000,
            'completed_at': 2000,
        }],
        'repair_keys': [],
        'tools': [],
        'delivery': {**delivery['delivery'], 'user_message_timestamp': stamp},
        'settlement_audit': {
            'function_type': 'SUMMARY',
            'model_id': 'gemini-flash',
            'fallback': False,
            'attempts': 1,
            'duration_ms': 280,
        },
    }


class StatTensionAndSubtextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_workspace(self.root)
        app = Flask(__name__)
        self.service = ss.register_story_routes(app, self.root)
        self.store = self.service.store
        self.client = app.test_client()
        self.token = self.client.get('/api/story/bridge-info').get_json()['token']
        self.cli_headers = {'X-Story-Client': '1'}
        self.wrk_headers = {'X-Story-Bridge': self.token}
        self.model = {
            'key': '["CHAT","prov","gemini-4"]',
            'function_type': 'CHAT',
            'provider_id': 'prov',
            'model_id': 'gemini-4',
            'provider_name': 'Prov',
            'pricing_configured': True,
        }
        self._stamp = 100

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_save_panels(self, panel_patches, *, mind_patches=None, intimate_patch=None, presence_patch=None):
        st, ms, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        for char_name, attrs in (panel_patches or {}).items():
            st.setdefault('panels', {}).setdefault(char_name, {}).update(attrs)
        if mind_patches:
            for char_name, mvals in mind_patches.items():
                st.setdefault('npc_mind', save_store.default_npc_mind()).setdefault(char_name, {}).update(mvals)
        if intimate_patch:
            st.setdefault('intimate', save_store.default_intimate()).update(intimate_patch)
        if presence_patch:
            for char_name, pvals in presence_patch.items():
                st.setdefault('presence', {}).setdefault(char_name, {}).update(pvals)
        save_store.save_bundle(self.root, st, ms)
        return (self.root / rr.FILES[0]).read_text(encoding='utf-8')

    def _run_dual_turn(self, action_text, fg_text, settlement_obj, *, option_id='CUSTOM',
                       chat_id='chat-e2e-1', synced_z0='', synced_z1='', last_seq=0,
                       is_fresh=False, prev_hashes=None):
        live = self.client.get('/api/story/live').get_json()
        self._stamp += 20
        req_id = f'req-tension-{self._stamp}'
        hist = live.get('history') or []
        if option_id == 'BEGIN' or not hist:
            selection = {'segment_id': '', 'option_id': 'BEGIN'}
            action_send = '继续当前剧情'
        else:
            seg_id_now = hist[-1].get('segment_id') or (live.get('playback') or {}).get('segment_id') or ''
            selection = {'segment_id': seg_id_now, 'option_id': option_id}
            action_send = action_text
        payload = {
            'request_id': req_id,
            'base_revision': live['revision'],
            'save_epoch': live['save_epoch'],
            'action': action_send,
            'entry_mode': 'live_interaction',
            'selection': selection,
        }
        created = self.client.post('/api/story/tasks', headers=self.cli_headers, json=payload)
        self.assertEqual(created.status_code, 200, created.get_json())
        claimed = self.client.post(
            '/api/story/worker/claim', headers=self.wrk_headers, json={'model': self.model}
        ).get_json()['task']
        mat_req = {
            'lease': claimed['lease'],
            'chat_id': chat_id,
            'participant_id': 'card-e2e-1',
            'delivery_version': 2,
            'protocol_mode': 'dual_stream_v2',
            'synced_zone0_sha256': synced_z0,
            'synced_zone1_sha256': synced_z1,
            'last_committed_sequence': last_seq,
            'is_fresh_session': is_fresh,
        }
        if prev_hashes is not None:
            mat_req['prev_state_hashes'] = prev_hashes
        mat = self.client.post(
            f"/api/story/worker/{claimed['request_id']}/material",
            headers=self.wrk_headers,
            json=mat_req,
        ).get_json()
        res = self.client.post(
            f"/api/story/worker/{claimed['request_id']}/result",
            headers=self.wrk_headers,
            json={
                'lease': claimed['lease'],
                'text': json.dumps({
                    'dual_stage_version': 1,
                    'foreground_text': fg_text,
                    'settlement': settlement_obj,
                }, ensure_ascii=False),
                'conversation_audit': _audit_for(self.root, mat, chat_id=chat_id, card_id='card-e2e-1', stamp=self._stamp),
                'timing': {
                    'generation_ms': 900, 'settlement_ms': 350, 'preflight_ms': 0,
                    'generation_passes': 1, 'settlement_passes': 1, 'settlement_model_id': 'gemini-flash',
                },
                'allow_settlement_retry': False,
            },
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        live_after = self.client.get('/api/story/live').get_json()
        pb = live_after.get('playback') or {}
        if pb and not pb.get('completed'):
            seg_id = pb['segment_id']
            total = int(pb.get('total') or 0)
            for r_idx in range(int(pb.get('revealed') or 0) + 1, total + 1):
                live_after = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
                    'save_epoch': live_after['save_epoch'], 'segment_id': seg_id, 'revealed': r_idx, 'completed': False,
                }).get_json()
            self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
                'save_epoch': live_after['save_epoch'], 'segment_id': seg_id, 'revealed': total, 'completed': True,
            })
        return mat, res.get_json()

    def test_coy_yield_passes_five_gates_and_flips_affection_positive(self):
        """Scenario 1: Shen Zhiyun (aff=85, shame=88, desire=48, dep=6) passes all 5 gates under C烈度_轻度 + 欲拒还迎_嘴硬心软."""
        self._patch_save_panels({
            '系统宿主': {'魅力': 70},
            '沈知韫': {'好感': 85, '羞耻': 88, '欲望': 48, '堕落': 6, '体力': 90, '被动': 0},
        })
        mem_file = str(self.root / rr.FILES[0])
        coy_tag = ic._event_tag('AFFECTION_12')
        c_light = ic._event_tag('SHAME_01')

        # Baseline (charm 70): aff 85 -> 86 (+1), desire gets +3 flutter
        coy_out = set()
        aff_res = ic.process_affection_system(
            {'沈知韫': [coy_tag]},
            {'沈知韫': [c_light]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='semi_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_out,
        )
        self.assertIn('沈知韫', coy_out)
        self.assertEqual(aff_res['沈知韫'], 86)

        ds_res = ic.process_desire_stamina_system(
            {'沈知韫': [ic._event_tag('DS_01')]},
            mem_file,
            coy_chars=coy_out,
        )
        # Visual base under shame>80 relaxed to +2 + coy_desire_bonus +3 = +5 -> 48 -> 53
        self.assertEqual(ds_res['沈知韫']['欲望'], 53)

        # High charm (85): aff 85 -> 87 (+1 base +1 charm synergy)
        self._patch_save_panels({'系统宿主': {'魅力': 85}})
        coy_out_hi = set()
        aff_res_hi = ic.process_affection_system(
            {'沈知韫': [coy_tag]},
            {'沈知韫': [c_light]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_out_hi,
        )
        self.assertIn('沈知韫', coy_out_hi)
        self.assertEqual(aff_res_hi['沈知韫'], 87)

        # Full apply_story_events + advance_npc_mind check inside isolated temp workspace
        engine = rr._engine(self.root, self.root)
        ev_meta = rr._engine_call(
            engine.apply_story_events,
            {
                'shame_events': {'沈知韫': [c_light]},
                'affection_events': {'沈知韫': [coy_tag]},
                'ds_events': {},
                'depravity_events': {},
                'host_events': [],
                'vigilance_events': {},
            },
            None,
            1,
            active_cast=['沈知韫'],
            privacy='locked_private',
            action_category='C',
        )
        self.assertEqual(ev_meta['coy_chars'], ['沈知韫'])
        st, _, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        self.assertEqual(st['panels']['沈知韫']['好感'], 87)
        self.assertLess(st['panels']['沈知韫']['羞耻'], 88)
        self.assertGreaterEqual(st['panels']['沈知韫']['欲望'], 51)
        sp.advance_npc_mind(
            st,
            active_cast=['沈知韫'],
            aff_deltas={'沈知韫': 2},
            events={'shame_events': {'沈知韫': [c_light]}, 'affection_events': {'沈知韫': [coy_tag]}, 'ds_events': {}, 'host_events': []},
            coy_chars=ev_meta['coy_chars'],
            action_category='C',
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['last_shift_kind'], 'coy_fluster')
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 0)

    def test_coy_yield_blocked_by_low_affection_and_low_desire(self):
        """Scenario 2: Low affection (40), low desire (10), low dep (0) is hard-blocked by Gate 2."""
        self._patch_save_panels({
            '沈知韫': {'好感': 40, '羞耻': 95, '欲望': 10, '堕落': 0, '体力': 90, '被动': 0},
        })
        mem_file = str(self.root / rr.FILES[0])
        coy_out = set()
        aff_res = ic.process_affection_system(
            {'沈知韫': [ic._event_tag('AFFECTION_12')]},
            {'沈知韫': [ic._event_tag('SHAME_01')]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_out,
        )
        self.assertEqual(coy_out, set())
        self.assertLess(aff_res['沈知韫'], 40)

    def test_coy_yield_blocked_by_heavy_coercion_and_blackout(self):
        """Scenario 3: Heavy coercion (C烈度_深度/重度), true rejection/violence/violent struggle, or stamina<=15 blocked by Gates 3 & 4."""
        coy_tag = ic._event_tag('AFFECTION_12')
        self._patch_save_panels({
            '沈知韫': {'好感': 88, '羞耻': 82, '欲望': 60, '堕落': 10, '体力': 85, '被动': 0},
        })
        mem_file = str(self.root / rr.FILES[0])
        # 3a: C烈度_深度 at high shame >= 55 -> blocked by Gate 3
        coy_deep = set()
        res_deep = ic.process_affection_system(
            {'沈知韫': [coy_tag]},
            {'沈知韫': [ic._event_tag('SHAME_03')]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_deep,
        )
        self.assertEqual(coy_deep, set())
        self.assertLess(res_deep['沈知韫'], 88)

        # 3b: Conflict with 阻止侵犯_成功 -> blocked by Gate 4
        coy_rej = set()
        res_rej = ic.process_affection_system(
            {'沈知韫': [coy_tag, ic._event_tag('AFFECTION_01')]},
            {'沈知韫': [ic._event_tag('SHAME_01')]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_rej,
        )
        self.assertEqual(coy_rej, set())
        self.assertLess(res_rej['沈知韫'], 88)

        # 3c: Conflict with 消耗_剧烈抗拒 -> blocked by Gate 4
        coy_str = set()
        res_str = ic.process_affection_system(
            {'沈知韫': [coy_tag]},
            {'沈知韫': [ic._event_tag('SHAME_01')]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={'沈知韫': [ic._event_tag('DS_10')]},
            coy_out=coy_str,
        )
        self.assertEqual(coy_str, set())
        self.assertLess(res_str['沈知韫'], 88)

        # 3d: Physiological blackout stamina <= 15 -> blocked by Gate 4
        self._patch_save_panels({'沈知韫': {'体力': 12}})
        coy_sta = set()
        res_sta = ic.process_affection_system(
            {'沈知韫': [coy_tag]},
            {'沈知韫': [ic._event_tag('SHAME_01')]},
            mem_file,
            resentment_map={'沈知韫': 0},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_sta,
        )
        self.assertEqual(coy_sta, set())
        self.assertLess(res_sta['沈知韫'], 88)

    def test_coy_yield_blocked_in_open_public_multi_cast(self):
        """Scenario 4: Moderate C-tier in open_public with multiple cast blocked by Gate 5, allowed in locked_private."""
        coy_tag = ic._event_tag('AFFECTION_12')
        c_mid = ic._event_tag('SHAME_02')
        self._patch_save_panels({
            '苏婉青': {'好感': 75, '羞耻': 76, '欲望': 50, '堕落': 10, '体力': 90, '被动': 0},
        })
        mem_file = str(self.root / rr.FILES[0])
        coy_pub = set()
        res_pub = ic.process_affection_system(
            {'苏婉青': [coy_tag]},
            {'苏婉青': [c_mid]},
            mem_file,
            resentment_map={'苏婉青': 0},
            privacy='open_public',
            active_cast=['苏婉青', '沈知韫'],
            ds_events={},
            coy_out=coy_pub,
        )
        self.assertEqual(coy_pub, set())
        self.assertLess(res_pub['苏婉青'], 75)

        coy_priv = set()
        res_priv = ic.process_affection_system(
            {'苏婉青': [coy_tag]},
            {'苏婉青': [c_mid]},
            mem_file,
            resentment_map={'苏婉青': 0},
            privacy='locked_private',
            active_cast=['苏婉青'],
            ds_events={},
            coy_out=coy_priv,
        )
        self.assertIn('苏婉青', coy_priv)
        self.assertGreater(res_priv['苏婉青'], 75)

    def test_resentment_locks_coy_yield_across_turns_and_heals_with_care(self):
        """Scenario 5: Genuine rejection raises resentment >= 25 blocking coy yield; sincere care + overnight cools < 25 and unlocks."""
        self._patch_save_panels({
            '沈知韫': {'好感': 85, '羞耻': 86, '欲望': 50, '堕落': 8, '体力': 88, '被动': 0},
        })
        mem_file = str(self.root / rr.FILES[0])
        st, _, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        # Turn A: Genuine rejection + violent struggle -> resentment +18 + 12 + 10 = 40
        sp.advance_npc_mind(
            st,
            active_cast=['沈知韫'],
            aff_deltas={'沈知韫': -7},
            events={
                'shame_events': {'沈知韫': [ic._event_tag('SHAME_02')]},
                'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_01')]},
                'ds_events': {'沈知韫': [ic._event_tag('DS_10')]},
                'host_events': [],
            },
            coy_chars=[],
            action_category='C',
            pre_values={('沈知韫', '体力'): 88, ('沈知韫', '羞耻'): 86},
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 40)
        self.assertEqual(st['npc_mind']['沈知韫']['last_shift_kind'], 'true_friction')

        # Gate 1 hard-blocks coy yield while resentment == 40 >= 25
        coy_blocked = set()
        res_blocked = ic.process_affection_system(
            {'沈知韫': [ic._event_tag('AFFECTION_12')]},
            {'沈知韫': [ic._event_tag('SHAME_01')]},
            mem_file,
            resentment_map={'沈知韫': st['npc_mind']['沈知韫']['resentment']},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_blocked,
        )
        self.assertEqual(coy_blocked, set())
        self.assertLess(res_blocked['沈知韫'], 85)

        # Turn B: Sincere deep heart-to-heart A-tier care (-15 -> 25)
        sp.advance_npc_mind(
            st,
            active_cast=['沈知韫'],
            aff_deltas={'沈知韫': 1},
            events={
                'shame_events': {},
                'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_10')]},
                'ds_events': {},
                'host_events': [ic._event_tag('HOST_06')],
            },
            coy_chars=[],
            action_category='A',
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 25)

        # Turn C: Overnight cooling (-8 -> 17 < 25)
        sp.advance_npc_mind(
            st,
            active_cast=[],
            overnight=True,
            day_crossed=True,
            aff_deltas={'沈知韫': 0},
            events=None,
            coy_chars=[],
            action_category='',
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 17)

        # Now Gate 1 passes again!
        coy_unlocked = set()
        res_unlocked = ic.process_affection_system(
            {'沈知韫': [ic._event_tag('AFFECTION_12')]},
            {'沈知韫': [ic._event_tag('SHAME_01')]},
            mem_file,
            resentment_map={'沈知韫': st['npc_mind']['沈知韫']['resentment']},
            privacy='locked_private',
            active_cast=['沈知韫'],
            ds_events={},
            coy_out=coy_unlocked,
        )
        self.assertIn('沈知韫', coy_unlocked)
        self.assertGreater(res_unlocked['沈知韫'], 85)

    def test_qualitative_brief_character_specific_coy_and_no_poisoning(self):
        """Scenario 6: All 3 heroines get unique 【表里拉扯】 directives, zero negative poisoning under coy_fluster, and real rift cues under resentment."""
        mem = self._patch_save_panels({
            '沈知韫': {'好感': 85, '羞耻': 86, '欲望': 48, '堕落': 6, '体力': 90, '被动': 0},
            '苏婉青': {'好感': 72, '羞耻': 82, '欲望': 46, '堕落': 8, '体力': 90, '被动': 0},
            '徐念薇': {'好感': 68, '羞耻': 84, '欲望': 45, '堕落': 4, '体力': 90, '被动': 0},
        })
        base_state = {
            'location': '徐家主宅',
            'cast': ['沈知韫', '苏婉青', '徐念薇'],
            'panels': [
                '[系统宿主] 体力 90 | 商业嗅觉 30 | 魅力 75',
                '[沈知韫] 好感 85 | 羞耻 86 | 欲望 48 | 堕落 6 | 高潮 0 | 体力 90 | 被动 Lv.0',
                '[苏婉青] 好感 72 | 羞耻 82 | 欲望 46 | 堕落 8 | 高潮 0 | 体力 90 | 被动 Lv.0',
                '[徐念薇] 好感 68 | 羞耻 84 | 欲望 45 | 堕落 4 | 高潮 0 | 体力 90 | 被动 Lv.0',
            ],
            'npc_mind': {
                '沈知韫': {'aff_delta_last': 1, 'resentment': 0, 'last_shift_kind': 'coy_fluster'},
                '苏婉青': {'aff_delta_last': -1, 'resentment': 0, 'last_shift_kind': 'coy_fluster'},
                '徐念薇': {'aff_delta_last': 0, 'resentment': 0, 'last_shift_kind': ''},
            },
            'intimate': {'privacy': 'semi_private', 'scene_active': False},
        }
        brief = sc.compile_state_qualitative_brief(base_state, mem)
        self.assertIn('【表里拉扯】嘴上端着长辈体面低声轻斥或借正事岔开', brief)
        self.assertIn('【表里拉扯】台面仍挂得体礼数与浅笑周旋', brief)
        self.assertIn('【表里拉扯】嘴硬嫌弃或拿兄妹规矩轻哼挡驾', brief)
        self.assertIn('刚经历嘴硬心软的近距试探，余热与窘迫交织未散', brief)
        self.assertNotIn('刚才略有不快，语气比平日收紧了些', brief)

        # Now verify resentment >= 25 and >= 50 override coy cues completely
        rift_state = copy.deepcopy(base_state)
        rift_state['npc_mind'] = {
            '沈知韫': {'aff_delta_last': -2, 'resentment': 30, 'last_shift_kind': 'true_friction'},
            '苏婉青': {'aff_delta_last': -6, 'resentment': 55, 'last_shift_kind': 'true_friction'},
            '徐念薇': {'aff_delta_last': 0, 'resentment': 0, 'last_shift_kind': ''},
        }
        rift_brief = sc.compile_state_qualitative_brief(rift_state, mem)
        self.assertIn('【真实裂痕·委屈戒备】', rift_brief)
        self.assertIn('【真实裂痕·严正冷淡】', rift_brief)
        self.assertIn('刚才略有不快，语气比平日收紧了些', rift_brief)
        self.assertIn('刚因越界或摩擦心生芥蒂，态度明显收冷', rift_brief)
        self.assertNotIn('【表里拉扯】嘴上端着长辈体面', rift_brief)
        self.assertNotIn('【表里拉扯】台面仍挂得体礼数', rift_brief)

    def test_zone1_stage2_unlock_on_high_aff_desire_and_kv_stability(self):
        """Scenario 7: High aff + high desire + low resentment unlocks stage2; high resentment stays stage1; frozen Zone 1 SHA-256 never drifts."""
        state_coy = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'panels': [
                '[沈知韫] 好感 85 | 羞耻 88 | 欲望 46 | 堕落 5 | 高潮 0 | 体力 95 | 被动 Lv.0',
            ],
            'npc_mind': {'沈知韫': {'resentment': 0, 'last_shift_kind': ''}},
            'mechanics': {'secrets_unlocked': []},
        }
        flags_coy = sc.compute_zone1_persona_flags(state_coy)
        self.assertEqual(flags_coy['char_stage']['沈知韫'], 'stage2')

        state_rift = copy.deepcopy(state_coy)
        state_rift['npc_mind']['沈知韫']['resentment'] = 30
        flags_rift = sc.compute_zone1_persona_flags(state_rift)
        self.assertEqual(flags_rift['char_stage']['沈知韫'], 'stage1')

        # Frozen session check: passing frozen_flags keeps Zone 1 text/SHA-256 100% identical across state shifts
        z1_a = sc.build_zone1_scene(self.root, state_coy, ['沈知韫'], frozen_flags=flags_coy)
        z1_b = sc.build_zone1_scene(self.root, state_rift, ['沈知韫'], frozen_flags=flags_coy)
        self.assertEqual(z1_a, z1_b)

    def test_dark_box_isolation_and_save_store_roundtrip(self):
        """Scenario 8: resentment & last_shift_kind persist/normalize cleanly in save_store and NEVER leak into ir.view()."""
        st, ms, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        # Simulate dirty/legacy values
        st['npc_mind']['沈知韫']['resentment'] = 142
        st['npc_mind']['沈知韫']['last_shift_kind'] = 'coy_fluster'
        st['npc_mind']['苏婉青']['resentment'] = -9
        st['npc_mind']['苏婉青']['last_shift_kind'] = 'bogus_enum'
        del st['npc_mind']['徐念薇']['resentment']
        del st['npc_mind']['徐念薇']['last_shift_kind']
        save_store.save_bundle(self.root, st, ms)

        st2, _, _ = save_store.load_bundle(self.root, sync_txt_drift=False)
        self.assertEqual(st2['npc_mind']['沈知韫']['resentment'], 100)
        self.assertEqual(st2['npc_mind']['沈知韫']['last_shift_kind'], 'coy_fluster')
        self.assertEqual(st2['npc_mind']['苏婉青']['resentment'], 0)
        self.assertEqual(st2['npc_mind']['苏婉青']['last_shift_kind'], '')
        self.assertEqual(st2['npc_mind']['徐念薇']['resentment'], 0)
        self.assertEqual(st2['npc_mind']['徐念薇']['last_shift_kind'], '')

        # Pure dark-box verification: frontend ir.view() & /api/story/live MUST NOT leak npc_mind/resentment/last_shift_kind
        live_snap = self.client.get('/api/story/live').get_json()
        live_json = json.dumps(live_snap, ensure_ascii=False)
        self.assertNotIn('resentment', live_json)
        self.assertNotIn('last_shift_kind', live_json)
        self.assertNotIn('npc_mind', live_json)

    def test_full_dual_stage_e2e_coy_yield_and_true_rejection(self):
        """Scenario 9: Full StoryService dual_stream_v2 E2E: Turn 1 coy yield flips aff up + cues next turn; Turn 2 true reject raises resentment + cues rift."""
        # Prepare private scene with Shen Zhiyun in golden coy-tension window
        self._patch_save_panels(
            {
                '系统宿主': {'魅力': 70, '体力': 100},
                '沈知韫': {'好感': 85, '羞耻': 88, '欲望': 48, '堕落': 6, '体力': 92, '被动': 0},
            },
            intimate_patch={'privacy': 'locked_private', 'present_actors': ['沈知韫']},
            presence_patch={
                '徐志北': {'location': '徐家主宅', 'state': '与沈知韫独处'},
                '沈知韫': {'location': '徐家主宅', 'state': '书房独处'},
                '苏婉青': {'location': '盛华广场公寓', 'state': '居家'},
                '徐念薇': {'location': '江城大学', 'state': '上课'},
                '徐承邺': {'location': '外地', 'state': '出差'},
            },
        )
        # Bootstrap opening BEGIN turn
        fg0 = _fg_script(speaker='沈知韫', line='志北，把门带上再坐过来。')
        s0 = _settlement_payload(category='SYSTEM', conditions=None, clock_time='20:10')
        mat0, _ = self._run_dual_turn('继续当前剧情', fg0, s0, option_id='BEGIN', is_fresh=True)
        z0_sha = mat0['zone0_sha256']
        z1_sha = mat0['zone1_sha256']
        seq = 1
        hashes = mat0.get('session_state_hashes') or {}

        # Turn 1: Coy yield (C烈度_轻度 + 欲拒还迎_嘴硬心软)
        fg1 = (
            '[N] 书房灯光暖黄，茶香混着她颈侧淡淡的沉水香。\n'
            '[A:徐志北] 你顺势倾身替她拢了拢滑落的披肩，指背若有似无擦过她滚烫的耳垂。\n'
            '[A:沈知韫] 沈知韫肩头轻轻一颤，耳尖瞬间泛红，呼吸发软却没有真的推开你的手。\n'
            '[D:沈知韫] 没大没小的……多大人了还这么毛躁，茶都要凉了。\n'
            '---DECISION---\n'
            'PROMPT: 她耳尖透红却未退开，你打算怎么做？\n'
            'A: 退开半步帮她添茶，顺着话头聊正事。\n'
            'B: 放低声音哄她两句，指尖轻抚她腕侧。\n'
            'C: 顺势贴得更近，低声在她耳边再试探一句。\n'
        )
        s1 = _settlement_payload(
            category='C',
            conditions={
                'intensity': 'C', 'effective_progress': True, 'scene': '徐家主宅',
                'npc': '沈知韫', 'action_changed': True, 'stress_signals': 1, 'breakout_triggered': [],
            },
            clock_time='20:20',
        )
        s1['resolution']['basis'] = '书房独处时贴近耳垂轻触引发暧昧越界试探。'
        s1['resolution']['events'] = [
            {'group': 'shame_events', 'target': '沈知韫', 'tags': [ic._event_tag('SHAME_01')], 'evidence': '指背若有似无擦过她滚烫的耳垂'},
            {'group': 'affection_events', 'target': '沈知韫', 'tags': [ic._event_tag('AFFECTION_12')], 'evidence': '耳尖瞬间泛红，呼吸发软却没有真的推开你的手'},
        ]
        s1['resolution']['memory'] = {'fact': '书房独处时贴近试探，沈知韫嘴上轻斥却未真推开。', 'anchor_ops': [], 'chronicle_digest': ''}
        _, r1 = self._run_dual_turn(
            '俯身替她拢披肩并轻擦她耳垂低声试探', fg1, s1,
            synced_z0=z0_sha, synced_z1=z1_sha, last_seq=seq, prev_hashes=hashes,
        )
        self.assertEqual(r1['task']['status'], 'committed')
        st1, _, _ = save_store.load_bundle(self.root, sync_txt_drift=False)
        self.assertEqual(st1['panels']['沈知韫']['好感'], 86)
        self.assertEqual(st1['panels']['沈知韫']['欲望'], 51)
        self.assertEqual(st1['npc_mind']['沈知韫']['last_shift_kind'], 'coy_fluster')
        self.assertEqual(st1['npc_mind']['沈知韫']['resentment'], 0)

        # Turn 2: Verify Turn 2 foreground material receives coy tension directive without negative poisoning, then submit true rejection!
        fg2 = (
            '[N] 空气蓦地冷了下来。\n'
            '[A:沈知韫] 沈知韫脸色一沉，果断抬手用力推开你，整个人往后撤了两步拉开距离，眼中满是冷硬与失望。\n'
            '[D:沈知韫] 志北，够了！别越矩，今天到此为止。\n'
            '---DECISION---\n'
            'PROMPT: 她已明显动怒拉远距离，你打算如何处理？\n'
            'A: 立刻退回安全距离，诚恳低头道歉。\n'
            'B: 沉默片刻，轻声解释并把空间还给她。\n'
            'C: 继续上前试图强行拉住她的手腕。\n'
        )
        s2 = _settlement_payload(
            category='C',
            conditions={
                'intensity': 'C', 'effective_progress': True, 'scene': '徐家主宅',
                'npc': '沈知韫', 'action_changed': True, 'stress_signals': 2, 'breakout_triggered': [],
            },
            clock_time='20:28',
        )
        s2['resolution']['basis'] = '强行加重越界遭到沈知韫果断推开与严词拒绝。'
        s2['resolution']['events'] = [
            {'group': 'shame_events', 'target': '沈知韫', 'tags': [ic._event_tag('SHAME_02')], 'evidence': '果断抬手用力推开你'},
            {'group': 'affection_events', 'target': '沈知韫', 'tags': [ic._event_tag('AFFECTION_01')], 'evidence': '沈知韫脸色一沉，果断抬手用力推开你'},
            {'group': 'ds_events', 'target': '沈知韫', 'tags': [ic._event_tag('DS_10')], 'evidence': '果断抬手用力推开你'},
        ]
        s2['resolution']['memory'] = {'fact': '强行加重越界遭沈知韫严词推开，心生真实裂痕。', 'anchor_ops': [], 'chronicle_digest': ''}
        mat2, r2 = self._run_dual_turn(
            '不顾她犹豫强行扣住肩头加重试探', fg2, s2,
            synced_z0=z0_sha, synced_z1=z1_sha, last_seq=seq + 1,
        )
        self.assertEqual(r2['task']['status'], 'committed')
        # Check Turn 2 foreground delta had the coy-fluster cues from Turn 1 and ZERO false annoyance!
        self.assertIn('【表里拉扯】嘴上端着长辈体面低声轻斥或借正事岔开', mat2['input_text'])
        self.assertIn('刚经历嘴硬心软的近距试探，余热与窘迫交织未散', mat2['input_text'])
        self.assertNotIn('刚才略有不快，语气比平日收紧了些', mat2['input_text'])

        st2, _, _ = save_store.load_bundle(self.root, sync_txt_drift=False)
        self.assertGreaterEqual(st2['npc_mind']['沈知韫']['resentment'], 25)
        self.assertEqual(st2['npc_mind']['沈知韫']['last_shift_kind'], 'true_friction')

        # Check Turn 3 material now surfaces real resentment directive & blocks coy directive!
        live3 = self.client.get('/api/story/live').get_json()
        self._stamp += 20
        req3 = f'req-tension-{self._stamp}'
        seg3_id = (live3.get('playback') or {}).get('segment_id') or live3['history'][-1].get('id', '')
        r3_task = self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': req3, 'base_revision': live3['revision'], 'save_epoch': live3['save_epoch'],
            'action': '低声向她道歉并退开半步', 'entry_mode': 'live_interaction',
            'selection': {'segment_id': seg3_id, 'option_id': 'CUSTOM'},
        })
        self.assertEqual(r3_task.status_code, 200, r3_task.get_json())
        c3 = self.client.post('/api/story/worker/claim', headers=self.wrk_headers, json={'model': self.model}).get_json()['task']
        mat3 = self.client.post(f"/api/story/worker/{c3['request_id']}/material", headers=self.wrk_headers, json={
            'lease': c3['lease'], 'chat_id': 'chat-e2e-1', 'participant_id': 'card-e2e-1',
            'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
            'synced_zone0_sha256': z0_sha, 'synced_zone1_sha256': z1_sha,
            'last_committed_sequence': seq + 2, 'is_fresh_session': False,
        }).get_json()
        self.assertIn('【真实裂痕·', mat3['input_text'])
        self.assertNotIn('【表里拉扯】嘴上端着长辈体面', mat3['input_text'])

    def test_registry_sync_worldbook_and_stage2_12k_budget(self):
        """Scenario 10: Registry, guide table, sys.affection, worldbook export are 100% synced and Stage 2 prompt stays < 12,000 chars."""
        raw_reg = json.loads((ROOT / 'txt文件/事件注册表.json').read_text(encoding='utf-8'))
        aff_list = raw_reg['groups']['affection_events']
        aff12 = next((x for x in aff_list if x.get('id') == 'AFFECTION_12'), None)
        self.assertIsNotNone(aff12)
        self.assertEqual(aff12['tag'], '欲拒还迎_嘴硬心软')
        self.assertEqual(aff12['parameters']['resentment_block_03'], 25)

        grouped_reg = rr._event_registry(ROOT, ic)
        self.assertIn('欲拒还迎_嘴硬心软', grouped_reg['affection_events'])

        guide = (ROOT / 'txt文件/一键注入指南.txt').read_text(encoding='utf-8')
        table_block = '【注册表生成表开始】\n' + ic._render_event_table('affection_events') + '\n【注册表生成表结束】'
        self.assertEqual(guide.count(table_block), 1)

        wb = json.loads((ROOT / 'Operit世界书导出/operit_worldbook_深渊天平.json').read_text(encoding='utf-8'))
        wb_text = json.dumps(wb, ensure_ascii=False)
        self.assertIn('欲拒还迎_嘴硬心软', wb_text)

        state = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'panels': [
                '[系统宿主] 体力 100 | 商业嗅觉 30 | 魅力 75',
                '[沈知韫] 好感 85 | 羞耻 88 | 欲望 48 | 堕落 6 | 高潮 0 | 体力 95 | 被动 Lv.0',
            ],
        }
        mem_txt = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        spec = sc.build_settlement_spec(
            ROOT,
            state,
            {'text': '', 'current': None, 'index': [], 'transfers': {}, 'limits': {}},
            '低声试探',
            {'segment_id': '', 'option_id': 'CUSTOM'},
            None,
            '',
            {'kind': 'action', 'total': 15},
            {'clock': {'day': 1, 'time': '20:00'}, 'memory_round': 1, 'phase': 'ready'},
            mem_txt,
            sp.resolution_policy('action'),
            sp.contract(ROOT, 'action'),
            {'allowed_codes': []},
        )
        sys_prompt = spec['system_prompt']
        self.assertLess(len(sys_prompt), 12000, f'Stage 2 static prompt exceeded 12K budget: {len(sys_prompt)}')
        self.assertIn('欲拒还迎_嘴硬心软', sys_prompt)
        self.assertIn('阻止侵犯_成功', sys_prompt)
        for marker in ('羞耻>75', '主动破锁_30阶梯', '苏婉青_真相揭露', '触发高潮_绝顶清算',
                       '自慰_暗中纾解', '解离保护', '外地', '内射', 'effective_progress',
                       '优雅掌控_魅力精进', '确诊怀孕', '体力 ≤ 15'):
            self.assertIn(marker, sys_prompt, f'Missing Stage 2 trigger marker: {marker}')

        # Zone 0 determinism check
        z0_a = sc.build_zone0_global(ROOT)
        z0_b = sc.build_zone0_global(ROOT)
        self.assertEqual(z0_a, z0_b)
        self.assertNotIn('欲拒还迎_嘴硬心软', z0_a)


if __name__ == '__main__':
    unittest.main()

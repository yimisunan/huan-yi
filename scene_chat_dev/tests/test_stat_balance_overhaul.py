"""Focused tests for the 5-module stat balance overhaul (Affection, Resentment, Shame, Desire, Charm/Stamina)."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import injection_core as ic
import round_runtime as rr
import save_store
import story_compiler as sc
import story_progression as sp


class StatBalanceOverhaulTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmp_statbal-', dir=ROOT / 'scene_chat_dev/tmp')
        self.root = Path(self.temp.name)
        self.prev_paths = (ic.BASE_DIR, ic.DATA_DIR, ic.MEMORY_FILE, ic.ITEM_FILE, ic.DATA_JSON_FILE)
        ic.BASE_DIR = str(self.root)
        ic.DATA_DIR = str(self.root / '存档')
        ic.MEMORY_FILE = str(self.root / '存档' / '全局记忆库.txt')
        ic.ITEM_FILE = str(self.root / '存档' / '徐志北道具图鉴.txt')
        ic.DATA_JSON_FILE = str(self.root / 'data.json')

    def tearDown(self):
        ic.BASE_DIR, ic.DATA_DIR, ic.MEMORY_FILE, ic.ITEM_FILE, ic.DATA_JSON_FILE = self.prev_paths
        self.temp.cleanup()

    def _init_save(self, host_patch=None, heroine_patch=None, buffs=None):
        st = save_store.default_state()
        if host_patch:
            st['panels']['系统宿主'].update(host_patch)
        if heroine_patch:
            for name, patch in heroine_patch.items():
                st['panels'][name].update(patch)
        if buffs:
            st['buffs'].update(buffs)
        ly = save_store.default_layers()
        save_store.save_bundle(self.root, st, ly)
        return st, ly

    def test_01_affection_rebalance_intact_defense_and_shame01_mitigation(self):
        # 1. Shen Zhiyun (aff 82, shame 100, dep 0): intact_defense blocks 0-drop closure but keeps >60 tier (-1 for SHAME_01, -2 for SHAME_02)
        self._init_save(heroine_patch={'沈知韫': {'好感': 82, '羞耻': 100, '堕落': 0}})
        res1 = ic.process_affection_system({}, {'沈知韫': [ic._event_tag('SHAME_01')]}, ic.MEMORY_FILE)
        self.assertEqual(res1['沈知韫'], 81)  # -1 (not -2)
        res2 = ic.process_affection_system({}, {'沈知韫': [ic._event_tag('SHAME_02')]}, ic.MEMORY_FILE)
        self.assertEqual(res2['沈知韫'], 80)  # -2 (not -5)

        # 2. SHAME_01 with sensual buff / Lv.2 passive genuinely mitigates to 0 drop (rewards preparation)
        self._init_save(
            heroine_patch={'沈知韫': {'好感': 82, '羞耻': 100, '堕落': 0, '被动': 2}},
        )
        res_zero = ic.process_affection_system({}, {'沈知韫': [ic._event_tag('SHAME_01')]}, ic.MEMORY_FILE)
        self.assertEqual(res_zero, {})  # 0 drop!

        # 3. Double penalty merge: SHAME_02 (-2) + AFFECTION_01 (-5) -> min(-2,-5)-1 = -6 (not -7/-10)
        self._init_save(heroine_patch={'沈知韫': {'好感': 82, '羞耻': 100, '堕落': 0}})
        res_merge = ic.process_affection_system(
            {'沈知韫': [ic._event_tag('AFFECTION_01')]},
            {'沈知韫': [ic._event_tag('SHAME_02')]},
            ic.MEMORY_FILE,
        )
        self.assertEqual(res_merge['沈知韫'], 76)  # 82 - 6

        # 4. AFFECTION_02 (-20) + SHAME_04 merges to -20 (not -26/-35)
        res_avalanche = ic.process_affection_system(
            {'沈知韫': [ic._event_tag('AFFECTION_02')]},
            {'沈知韫': [ic._event_tag('SHAME_04')]},
            ic.MEMORY_FILE,
        )
        self.assertEqual(res_avalanche['沈知韫'], 62)  # 82 - 20

    def test_02_positive_affection_channels_and_warm_daily_fallback(self):
        # High affection (>=60) still gets +1 from AFFECTION_03 (基础安抚) and +1 from AFFECTION_06 (<80)
        self._init_save(heroine_patch={'沈知韫': {'好感': 82}, '苏婉青': {'好感': 65}})
        res = ic.process_affection_system(
            {'沈知韫': [ic._event_tag('AFFECTION_03')], '苏婉青': [ic._event_tag('AFFECTION_06')]},
            {}, ic.MEMORY_FILE,
        )
        self.assertEqual(res['沈知韫'], 83)  # +1 even at 82
        self.assertEqual(res['苏婉青'], 66)  # +1 at 65 (<80)

        # Warm daily fallback: A/B turn with HOST_05, no shame/aff events, single heroine < 90 -> +1
        self._init_save(heroine_patch={'沈知韫': {'好感': 82}})
        ic.apply_story_events(
            {'shame_events': {}, 'depravity_events': {}, 'ds_events': {},
             'affection_events': {}, 'host_events': [ic._event_tag('HOST_05')], 'vigilance_events': {}},
            None, 1, active_cast=['沈知韫'], action_category='A', effective_progress=True,
        )
        st_after, _, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        self.assertEqual(st_after['panels']['沈知韫']['好感'], 83)

        # Warm daily fallback must NOT stack when explicit positive affection already fired
        self._init_save(heroine_patch={'沈知韫': {'好感': 82}})
        ic.apply_story_events(
            {'shame_events': {}, 'depravity_events': {}, 'ds_events': {},
             'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_03')]},
             'host_events': [ic._event_tag('HOST_05')], 'vigilance_events': {}},
            None, 1, active_cast=['沈知韫'], action_category='A', effective_progress=True,
        )
        st_no_stack, _, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        self.assertEqual(st_no_stack['panels']['沈知韫']['好感'], 83)  # only +1 from AFFECTION_03

    def test_03_coy_gates_and_resentment_anti_death_spiral(self):
        # Su Wanqing at aff=46 passes Gate 2 (new floor 45); Shen Zhiyun at shame=85, des=10 passes Gate 3 mid-C (new limit 88)
        self._init_save(heroine_patch={
            '苏婉青': {'好感': 46, '羞耻': 85, '堕落': 0, '欲望': 10},
            '沈知韫': {'好感': 82, '羞耻': 85, '堕落': 0, '欲望': 10},
        })
        coy_out = set()
        res = ic.process_affection_system(
            {'苏婉青': [ic._event_tag('AFFECTION_12')], '沈知韫': [ic._event_tag('AFFECTION_12')]},
            {'苏婉青': [ic._event_tag('SHAME_01')], '沈知韫': [ic._event_tag('SHAME_02')]},
            ic.MEMORY_FILE, coy_out=coy_out,
        )
        self.assertEqual(coy_out, {'苏婉青', '沈知韫'})
        self.assertEqual(res['苏婉青'], 47)
        self.assertEqual(res['沈知韫'], 83)

        # Single rejection + struggle caps resentment gain at <= 15 (does NOT one-shot lock >= 30)
        st = save_store.default_state()
        sp.advance_npc_mind(
            st, active_cast=['沈知韫'], action_category='C',
            aff_deltas={'沈知韫': -6},
            events={
                'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_01')]},
                'ds_events': {'沈知韫': [ic._event_tag('DS_10')]},
                'shame_events': {'沈知韫': [ic._event_tag('SHAME_02')]},
            },
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 15)

        # Second coercive push crosses 30 -> locks coy yield; deep care (-20) + overnight (-12) cools back to 0
        sp.advance_npc_mind(
            st, active_cast=['沈知韫'], action_category='C',
            aff_deltas={'沈知韫': -6},
            events={
                'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_01')]},
                'ds_events': {'沈知韫': [ic._event_tag('DS_10')]},
                'shame_events': {'沈知韫': [ic._event_tag('SHAME_02')]},
            },
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 30)
        sp.advance_npc_mind(
            st, active_cast=['沈知韫'], action_category='A', overnight=True,
            aff_deltas={'沈知韫': 3},
            events={'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_10')]}},
            engine=ic,
        )
        self.assertEqual(st['npc_mind']['沈知韫']['resentment'], 0)

    def test_04_shame_soft_cap_shame19_immunity_and_ds_balance(self):
        # 1. SHAME_19 (>70) is NOT zeroed out by SHAME_16 (同质化免疫_回合3)
        self._init_save(heroine_patch={'沈知韫': {'羞耻': 74, '堕落': 0}})
        sh19 = ic.process_shame_system(
            {'沈知韫': [ic._event_tag('SHAME_19'), ic._event_tag('SHAME_16')]},
            ic.MEMORY_FILE,
        )
        self.assertEqual(sh19['沈知韫'], 71)  # -3 preserved despite SHAME_16

        # 2. Late-game multiplier avalanche is clamped by -10 soft cap on regular c_delta
        self._init_save(
            host_patch={'魅力': 95},
            heroine_patch={'沈知韫': {'羞耻': 50, '堕落': 70, '被动': 4, '体力': 40}},
        )
        sh_cap = ic.process_shame_system(
            {'沈知韫': [ic._event_tag('SHAME_04'), ic._event_tag('SHAME_17')]},
            ic.MEMORY_FILE, privacy='thin_wall', host_charm=95, body_acts={'沈知韫': ['foot']},
        )
        self.assertEqual(sh_cap['沈知韫'], 40)  # clamped to -10 (not -20+)

        # 3. DS mid-band seepage (+2 at shame<55 & aff>70), visual floor +2 at shame>80, and Lv.3 DS_10 = -22 (not -30)
        self._init_save(heroine_patch={
            '沈知韫': {'好感': 75, '羞耻': 50, '欲望': 10, '体力': 80, '被动': 3},
            '苏婉青': {'好感': 50, '羞耻': 90, '欲望': 0, '体力': 100, '被动': 0},
        })
        ds_res = ic.process_desire_stamina_system(
            {'沈知韫': [ic._event_tag('DS_10')], '苏婉青': [ic._event_tag('DS_01')]},
            ic.MEMORY_FILE, active_cast=['沈知韫', '苏婉青'],
        )
        self.assertEqual(ds_res['沈知韫']['欲望'], 12)  # +2 mid-band seepage
        self.assertEqual(ds_res['沈知韫']['体力'], 58)  # 80 - round(15*1.5)=22
        self.assertEqual(ds_res['苏婉青']['欲望'], 2)   # +2 visual floor at shame>80

    def test_05_registry_sync_and_prompt_budgets(self):
        reg = rr._event_registry(ROOT, ic)
        self.assertEqual(len(reg), 6)
        z0 = sc.build_zone0_global(ROOT, mode='dual_stream_v2')
        self.assertLess(len(z0), 9000, f'Zone 0 over budget: {len(z0)}')
        st = save_store.default_state()
        mem_txt = save_store.render_memory_txt(st, save_store.default_layers())
        hot = {'location': '徐家主宅', 'cast': ['沈知韫'], 'clock': {'day': 1, 'time': '20:00'}, 'intimate': st['intimate'], 'panels': st['panels']}
        s2 = sc.build_settlement_spec(
            ROOT, hot, {'text': '', 'omitted_count': 0}, '继续交谈',
            {'option_id': 'B', 'text': '继续交谈'}, None, None, {'kind': 'action', 'total': 10},
            {'clock': {'day': 1, 'time': '20:05'}, 'memory_round': 5, 'phase': 'ready'},
            mem_txt, {'category_policy': 'fixed_option', 'required_category': 'B'},
            {'operation': '', 'handoff': '', 'checks': {}, 'resolution': {'category': 'B', 'events': [], 'memory': {}}},
            {},
        )['system_prompt']
        self.assertIn('心理破冰_暧昧试探', s2)
        self.assertLess(len(s2), 12000, f'Stage 2 over budget: {len(s2)}')


if __name__ == '__main__':
    unittest.main()

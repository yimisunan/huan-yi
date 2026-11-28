"""Focused tests for the 4-pillar Points/EXP economy pacing overhaul."""
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


class EconomyPacingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmp_econ_test-', dir=ROOT / 'scene_chat_dev/tmp')
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

    def _init_save(self, host_patch=None, heroine_patch=None):
        st = save_store.default_state()
        if host_patch:
            st['panels']['系统宿主'].update(host_patch)
        if heroine_patch:
            for name, patch in heroine_patch.items():
                st['panels'][name].update(patch)
        ly = save_store.default_layers()
        save_store.save_bundle(self.root, st, ly)
        return st, ly

    def test_01_registry_sync_and_host08_grants_exp(self):
        reg = rr._event_registry(ROOT, ic)
        self.assertIn('host_events', reg)
        self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 0})
        res = ic.process_host_system([ic._event_tag('HOST_08')], {}, ic.MEMORY_FILE)
        self.assertEqual(res['积分'], 3)
        self.assertEqual(res['经验值'], 2)

    def test_02_three_track_synergy_dedup_and_guard_independent(self):
        # 1. Primary 100% + Secondary 50% + biz>=80 (+15%) + independent biz
        self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 80})
        res = ic.process_host_system(
            [ic._event_tag('HOST_03'), ic._event_tag('HOST_09')],
            {}, ic.MEMORY_FILE,
        )
        # track1=(32,22), track3=(6,5,4) -> synergy=(32+3=35, 22+2=24) -> *1.15 => (40, 28)
        self.assertEqual(res['积分'], 40)
        self.assertEqual(res['经验值'], 28)
        self.assertEqual(res['商业嗅觉'], 84)

        # 2. Same-turn duplicate econ tags deduplicated
        self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 0})
        res_dup = ic.process_host_system(
            [ic._event_tag('HOST_05')] * 3,
            {}, ic.MEMORY_FILE,
        )
        self.assertEqual(res_dup['积分'], 5)
        self.assertEqual(res_dup['经验值'], 3)

        # 3. HOST_07 (连续守护5回合) paid independently on top of higher track (never swallowed)
        self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 0})
        res_guard = ic.process_host_system(
            [ic._event_tag('HOST_02'), ic._event_tag('HOST_07')],
            {}, ic.MEMORY_FILE,
        )
        # HOST_02 (12, 8) + independent HOST_07 (10, 8) = (22, 16)
        self.assertEqual(res_guard['积分'], 22)
        self.assertEqual(res_guard['经验值'], 16)

    def test_03_action_floor_anti_farming_and_non_stacking(self):
        # Effective progress with no host_events yields deterministic tier floor
        for cat, (exp_pts, exp_exp) in ic.ACTION_ECONOMY_FLOOR.items():
            self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 0})
            ic.apply_story_events(
                {'shame_events': {}, 'depravity_events': {}, 'ds_events': {},
                 'affection_events': {}, 'host_events': [], 'vigilance_events': {}},
                None, 1, action_category=cat, effective_progress=True,
            )
            host = ic._read_host_panel(ic.MEMORY_FILE)
            self.assertEqual((host['积分'], host['经验值']), (exp_pts, exp_exp), f'cat={cat}')

        # Idle turn (effective_progress=False and no events) gets strictly 0/0
        self._init_save({'积分': 10, '经验值': 5, '商业嗅觉': 0})
        ic.apply_story_events(
            {'shame_events': {}, 'depravity_events': {}, 'ds_events': {},
             'affection_events': {}, 'host_events': [], 'vigilance_events': {}},
            None, 1, action_category='A', effective_progress=False,
        )
        host_idle = ic._read_host_panel(ic.MEMORY_FILE)
        self.assertEqual((host_idle['积分'], host_idle['经验值']), (10, 5))

        # High-yield event uses max(earned, floor), never stacks floor on top
        self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 0})
        ic.apply_story_events(
            {'shame_events': {}, 'depravity_events': {}, 'ds_events': {},
             'affection_events': {}, 'host_events': [ic._event_tag('HOST_03')], 'vigilance_events': {}},
            None, 1, action_category='C', effective_progress=True,
        )
        host_big = ic._read_host_panel(ic.MEMORY_FILE)
        self.assertEqual((host_big['积分'], host_big['经验值']), (32, 22))

        # HOST_07 stacks independently on top of action floor
        self._init_save({'积分': 0, '经验值': 0, '商业嗅觉': 0})
        ic.apply_story_events(
            {'shame_events': {}, 'depravity_events': {}, 'ds_events': {},
             'affection_events': {}, 'host_events': [ic._event_tag('HOST_07')], 'vigilance_events': {}},
            None, 1, action_category='A', effective_progress=True,
        )
        host_g = ic._read_host_panel(ic.MEMORY_FILE)
        self.assertEqual((host_g['积分'], host_g['经验值']), (12, 10))

    def test_04_coy_yield_auto_derives_host01(self):
        # Setup heroine meeting AFFECTION_12 5-gate (aff >= 70 or desire >= 40, shame >= 55, no heavy shame, resentment < 40)
        self._init_save(
            host_patch={'积分': 0, '经验值': 0, '商业嗅觉': 0},
            heroine_patch={'沈知韫': {'好感': 75, '羞耻': 80, '堕落': 10}},
        )
        ev_meta = ic.apply_story_events(
            {
                'shame_events': {'沈知韫': [ic._event_tag('SHAME_01')]},
                'depravity_events': {},
                'ds_events': {},
                'affection_events': {'沈知韫': [ic._event_tag('AFFECTION_12')]},
                'host_events': [],
                'vigilance_events': {},
            },
            None, 1, active_cast=['沈知韫'], action_category='B', effective_progress=True,
        )
        self.assertIn('沈知韫', ev_meta['coy_chars'])
        self.assertIn(ic._event_tag('HOST_01'), ev_meta['normalized_events']['host_events'])
        host = ic._read_host_panel(ic.MEMORY_FILE)
        self.assertEqual((host['积分'], host['经验值']), (5, 3))

    def test_05_adult_milestones_economy_payoff_and_anti_farming(self):
        import copy
        st, _ = self._init_save({'积分': 0, '经验值': 0, '魅力': 72})
        st_before = copy.deepcopy(st)
        # 1. body_dev crossing Lv.1 (threshold=20; foot signature: 17 -> 17+5=22 >= 20) pays +6/+5 without triggering Charm dev_milestones
        st['intimate']['body_dev']['沈知韫']['foot'] = 17
        m1 = ic.advance_intimate_state(
            st, events={'shame_events': {'沈知韫': [ic._event_tag('SHAME_02')]}, 'ds_events': {}, 'host_events': []},
            scene_state={'intimate_active': True, 'body_acts': {'沈知韫': ['foot']}},
            category='B', active_cast=['沈知韫'],
        )
        self.assertEqual(m1['dev_milestones'], [])
        self.assertEqual(m1['economy_bonus'], {'pts': 6, 'exp': 5})
        self.assertEqual((st['panels']['系统宿主']['积分'], st['panels']['系统宿主']['经验值']), (6, 5))
        self.assertTrue(any('Lv.1' in x for x in m1['economy_notes']))

        # 2. Crossing Lv.2 (threshold=50; 45 -> 45+11=56) + synced_climax + brand-new keepsake (2 submitted -> capped at 1 paid)
        st['intimate']['body_dev']['沈知韫']['foot'] = 45
        st['intimate']['host_phys']['desire'] = 90
        m2 = ic.advance_intimate_state(
            st,
            events={'shame_events': {'沈知韫': [ic._event_tag('SHAME_04'), ic._event_tag('SHAME_05')]}, 'ds_events': {'沈知韫': [ic._event_tag('DS_17')]}, 'host_events': []},
            scene_state={
                'intimate_active': True,
                'body_acts': {'沈知韫': ['foot']},
                'keepsake_adds': [
                    {'owner': '沈知韫', 'name': '黑色蕾丝丝袜', 'method': 'taken_intimate', 'condition': 'fresh_warm'},
                    {'owner': '沈知韫', 'name': '珍珠耳钉', 'method': 'gifted', 'condition': 'clean'},
                ],
            },
            category='C', active_cast=['沈知韫'],
        )
        # Lv.2 (10, 8) + synced_climax (10, 8) + 1 new keepsake (6, 4) = (26, 20)
        self.assertTrue(m2['synced_climax'])
        self.assertTrue(st['intimate']['session_econ_climax_paid'])
        self.assertEqual(m2['economy_bonus'], {'pts': 26, 'exp': 20})
        self.assertEqual((st['panels']['系统宿主']['积分'], st['panels']['系统宿主']['经验值']), (32, 25))

        # 3. Same-session second synced_climax + updating existing keepsake pays 0/0 (anti-farming)
        st['intimate']['host_phys']['desire'] = 95
        m3 = ic.advance_intimate_state(
            st,
            events={'shame_events': {'沈知韫': [ic._event_tag('SHAME_05')]}, 'ds_events': {'沈知韫': [ic._event_tag('DS_17')]}, 'host_events': []},
            scene_state={
                'intimate_active': True,
                'keepsake_adds': [
                    {'owner': '沈知韫', 'name': '黑色蕾丝丝袜', 'method': 'taken_intimate', 'condition': 'faded'},
                ],
            },
            category='C', active_cast=['沈知韫'],
        )
        self.assertTrue(m3['synced_climax'])
        self.assertEqual(m3['economy_bonus'], {'pts': 0, 'exp': 0})
        self.assertEqual((st['panels']['系统宿主']['积分'], st['panels']['系统宿主']['经验值']), (32, 25))

        # 4. collect_state_deltas surfaces economy_notes into receipt state_notes
        _, notes = sp.collect_state_deltas(st_before, st, intimate_meta=m2)
        econ_notes = [n for n in notes if n.get('kind') == 'economy_milestone']
        self.assertEqual(len(econ_notes), 3)

        # 5. Scene exit resets session_econ_climax_paid cleanly across save_store normalization
        ic.advance_intimate_state(
            st, events={}, scene_state={}, category='A', location_changed=True,
        )
        self.assertFalse(st['intimate']['session_econ_climax_paid'])
        norm_st = save_store.normalize_state(st)
        self.assertFalse(norm_st['intimate']['session_econ_climax_paid'])

    def test_06_task_rewards_and_prompt_budgets(self):
        self.assertEqual(ic.TASK_REWARDS, {'small': (20, 12), 'medium': (45, 30), 'large': (80, 50)})
        z0 = sc.build_zone0_global(ROOT, mode='dual_stream_v2')
        self.assertLess(len(z0), 9000, f"Zone 0 over budget: {len(z0)}")
        st = save_store.default_state()
        mem_txt = save_store.render_memory_txt(st, save_store.default_layers())
        hot_state = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'clock': {'day': 1, 'time': '20:00'},
            'intimate': st['intimate'],
            'panels': st['panels'],
        }
        spec = sc.build_settlement_spec(
            ROOT, hot_state, {'text': '', 'omitted_count': 0}, '继续交谈',
            {'option_id': 'B', 'text': '继续交谈'}, None, None, {'kind': 'action', 'total': 10},
            {'clock': {'day': 1, 'time': '20:05'}, 'memory_round': 5, 'phase': 'ready'},
            mem_txt, {'category_policy': 'fixed_option', 'required_category': 'B'},
            {'operation': '', 'handoff': '', 'checks': {}, 'resolution': {'category': 'B', 'events': [], 'memory': {}}},
            {},
        )
        self.assertLess(len(spec['system_prompt']), 12000, f"Stage 2 over budget: {len(spec['system_prompt'])}")


if __name__ == '__main__':
    unittest.main()

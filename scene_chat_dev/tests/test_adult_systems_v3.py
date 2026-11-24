"""Comprehensive verification suite for v3 adult mechanics, stealth/privacy, intimate slow-burn, remote monitoring, and Living Director fixes."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scene_chat_dev/tests'))

from test_interaction import fixture
import injection_core as ic
import relationship_query as rq
import round_runtime as rr
import save_store
import story_compiler as sc
import story_progression as sp


def _bind_engine(root: Path):
    prev = (ic.BASE_DIR, ic.DATA_DIR, ic.MEMORY_FILE, ic.ITEM_FILE, ic.DATA_JSON_FILE)
    ic.BASE_DIR = str(root)
    ic.DATA_DIR = str(root / '存档')
    ic.MEMORY_FILE = str(root / save_store.RENDERED_MEMORY_PATH)
    ic.ITEM_FILE = str(root / save_store.RENDERED_ITEMS_PATH)
    ic.DATA_JSON_FILE = str(root / 'data.json')
    return prev


def _restore_engine(prev):
    ic.BASE_DIR, ic.DATA_DIR, ic.MEMORY_FILE, ic.ITEM_FILE, ic.DATA_JSON_FILE = prev


def _files_snapshot(root: Path):
    files = {p: (root / p).read_bytes() for p in rr.FILES if (root / p).is_file()}
    for extra in ('data.json', save_store.SAVE_STATE_PATH, save_store.MEMORY_LAYERS_PATH, save_store.RECENT_PLAYBACK_PATH):
        fp = root / extra
        if fp.is_file():
            files[extra] = fp.read_bytes()
    return files


def _make_res_body(option_id, category, action, events_dict, *, operation=None, scene_state=None, day=1, time_str='21:30', npc='沈知韫'):
    cost_map = {'A': 5, 'B': 10, 'C': 15}
    ev_list = []
    for grp, payload in (events_dict or {}).items():
        if grp == 'host_events':
            if payload:
                ev_list.append({'group': grp, 'target': '系统宿主', 'tags': list(payload), 'evidence': action})
        else:
            for tgt, tags in (payload or {}).items():
                if tags:
                    ev_list.append({'group': grp, 'target': tgt, 'tags': list(tags), 'evidence': action})
    res_obj = {
        'category': category,
        'basis': '按玩家本轮明确指令结算',
        'clock': {'day': day, 'time': time_str, 'basis': '场景推进十五分钟'},
        'events': ev_list,
        'memory': {'fact': '测试场景推进', 'transfers': {}, 'compact': ''},
        'conditions': {
            'intensity': category,
            'effective_progress': True,
            'action_changed': False,
            'scene': '徐家主宅书房',
            'npc': npc,
            'stress_signals': 0,
            'breakout_triggered': [],
        },
        'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
        'task': None,
        'items': [],
    }
    if scene_state is not None:
        res_obj['scene_state'] = scene_state
    body = {
        'action': action,
        'input': action,
        'messages': [{'kind': 'narration', 'speaker': '', 'text': action}],
        'selection': {'segment_id': 'seg-0001', 'option_id': option_id},
        'audit': {
            'reservation': {
                'status': 'held',
                'quote': {
                    'status': 'active',
                    'scheme': 'fixed_tiers',
                    'kind': 'action',
                    'attribute': '体力',
                    'total': cost_map.get(category, 15),
                    'before': 100,
                    'after': 100 - cost_map.get(category, 15),
                    'policy_version': 2,
                    'option_id': option_id,
                },
            }
        },
        'resolution': res_obj,
    }
    if operation is not None:
        body['operation'] = operation
    return body


class AdultSystemsV3Tests(unittest.TestCase):
    def setUp(self):
        import shutil
        self.temp = tempfile.TemporaryDirectory(prefix='tmp_v3_adult-', dir=ROOT / 'scene_chat_dev/tmp')
        self.root = fixture(self.temp.name, progression=True)
        shutil.copyfile(ROOT / 'txt文件/世界变故库.json', self.root / 'txt文件/世界变故库.json')
        self.prev_engine = _bind_engine(self.root)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        _restore_engine(self.prev_engine)
        self.temp.cleanup()

    def _load(self):
        return save_store.load_bundle(self.root)

    def _save(self, st, ly, rc=None):
        save_store.save_bundle(self.root, st, ly, rc)

    def test_01_goodwill_seepage_fires_without_ds_events(self):
        st, ly, rc = self._load()
        st['panels']['沈知韫']['好感'] = 82
        st['panels']['沈知韫']['羞耻'] = 32
        st['panels']['沈知韫']['欲望'] = 10
        self._save(st, ly, rc)

        ic.apply_story_events({}, None, 2, active_cast=['沈知韫'])
        st2, _, _ = self._load()
        self.assertGreaterEqual(st2['panels']['沈知韫']['欲望'], 13)

    def test_02_critical_breakthrough_during_fluid_lock_and_charm_synergy(self):
        st, ly, rc = self._load()
        st['panels']['苏婉青']['羞耻'] = 35
        st['panels']['苏婉青']['欲望'] = 85
        st['panels']['苏婉青']['体力'] = 80
        st['buffs']['苏婉青'] = [
            {'name': '体液锁定', 'turns': 24, 'desc': '体内体液残留，欲望锁定在60~85'},
        ]
        self._save(st, ly, rc)

        # Breakthrough DS_06 penetrates fluid lock directly to 100
        res = ic.process_desire_stamina_system(
            {'苏婉青': [ic._event_tag('DS_06')]},
            ic.MEMORY_FILE,
            active_cast=['苏婉青'],
            host_charm=78,
        )
        self.assertEqual(res['苏婉青']['欲望'], 100)

        # Host charm >= 75 relaxes DS_06 threshold from 70 down to 60 and adds +2 synergy
        st, ly, rc = self._load()
        st['panels']['苏婉青']['欲望'] = 62
        st['buffs']['苏婉青'] = []
        self._save(st, ly, rc)
        res2 = ic.process_desire_stamina_system(
            {'苏婉青': [ic._event_tag('DS_06')]},
            ic.MEMORY_FILE,
            active_cast=['苏婉青'],
            host_charm=80,
        )
        self.assertEqual(res2['苏婉青']['欲望'], 100)

    def test_03_first_creampie_auto_derives_shame07_depravity03_host04_once(self):
        st, ly, rc = self._load()
        st['panels']['沈知韫']['羞耻'] = 50
        st['panels']['沈知韫']['堕落'] = 15
        st['panels']['系统宿主']['积分'] = 0
        st['panels']['系统宿主']['经验值'] = 0
        self._save(st, ly, rc)

        events = {'shame_events': {'沈知韫': [ic._event_tag('SHAME_06')]}, 'depravity_events': {}, 'host_events': []}
        ic.apply_story_events(events, None, 2, active_cast=['沈知韫'])
        st2, _, _ = self._load()
        self.assertIn('内射', st2['mechanics']['first_triggers']['沈知韫'])
        self.assertGreaterEqual(st2['panels']['沈知韫']['堕落'], 30)  # +15 from DEPRAVITY_03
        self.assertGreaterEqual(st2['panels']['系统宿主']['积分'], 50)  # +50 from HOST_04
        self.assertGreaterEqual(st2['panels']['系统宿主']['经验值'], 50)

        # Second creampie must NOT duplicate first-time DEPRAVITY_03 or HOST_04
        dep_before = st2['panels']['沈知韫']['堕落']
        pts_before = st2['panels']['系统宿主']['积分']
        events2 = {
            'shame_events': {'沈知韫': [ic._event_tag('SHAME_07')]},
            'depravity_events': {'沈知韫': [ic._event_tag('DEPRAVITY_03')]},
            'host_events': [ic._event_tag('HOST_04')],
        }
        ic.apply_story_events(events2, None, 3, active_cast=['沈知韫'])
        st3, _, _ = self._load()
        self.assertEqual(st3['panels']['沈知韫']['堕落'], dep_before)
        self.assertEqual(st3['panels']['系统宿主']['积分'], pts_before)

    def test_04_physiological_blackout_at_stamina_15_blocks_unconsented_deep_c(self):
        st, ly, rc = self._load()
        st['panels']['沈知韫']['体力'] = 15
        st['panels']['沈知韫']['羞耻'] = 30
        st['presence']['徐志北'] = {'location': '徐家主宅', 'reason': '主宅书房'}
        st['presence']['沈知韫'] = {'location': '徐家主宅', 'reason': '主宅书房'}
        self._save(st, ly, rc)
        files = _files_snapshot(self.root)

        events = {'shame_events': {'沈知韫': ['C烈度_深度']}}
        body_blocked = _make_res_body('C', 'C', '继续吻她并加深接触', events)
        with self.assertRaises(rr.RoundError) as ctx:
            sp.resolution(self.root, files, body_blocked)
        self.assertIn('生理断电', str(ctx.exception))

        # Explicit player bracket authorization overrides the guard cleanly
        body_auth = _make_res_body('C', 'C', '（强行继续，不顾她脱力）把她按回枕上', events)
        ok_res = sp.resolution(self.root, files, body_auth)
        self.assertIn('沈知韫', ok_res['active_cast'])

    def test_05_dynamic_sensual_buff_and_reusable_shop013_blindfold(self):
        # Test _has_sensual_buff with dynamic AI restock buff + SHOP-013 buff
        self.assertTrue(ic._has_sensual_buff([{'name': '催情玫瑰按摩油', 'desc': '温热发烫'}]))
        self.assertTrue(ic._has_sensual_buff([{'name': '感官放大', 'desc': '遮光与冰玉温差'}]))
        self.assertFalse(ic._has_sensual_buff([{'name': '普通精力恢复', 'desc': '喝了杯黑咖啡'}]))

        # Verify SHOP-013 catalog entry has reusable buff effect
        cat = json.loads((self.root / 'txt文件/系统商城目录.json').read_text(encoding='utf-8'))
        s013 = next(it for it in cat['items'] if it['id'] == 'SHOP-013')
        self.assertIn('buff:感官放大:2:', s013['system_effect'])

        # Visual shame bypass (DS_01 = 刺激_视觉) & halved affection penalty under dynamic sensual buff
        st, ly, rc = self._load()
        st['panels']['苏婉青']['羞耻'] = 75  # > 60 normally blocks visual shame
        st['panels']['苏婉青']['好感'] = 50
        st['panels']['苏婉青']['欲望'] = 10
        st['buffs']['苏婉青'] = [{'name': '感官放大', 'turns': 2, 'desc': '遮光与冰玉温差'}]
        self._save(st, ly, rc)

        ds_res = ic.process_desire_stamina_system(
            {'苏婉青': [ic._event_tag('DS_01')]},
            ic.MEMORY_FILE,
            active_cast=['苏婉青'],
        )
        self.assertGreater(ds_res['苏婉青']['欲望'], 10)

        # Affection penalty halving vs no buff
        aff_with_buff = ic.process_affection_system(
            {}, {'苏婉青': ['C烈度_中度']}, ic.MEMORY_FILE
        )['苏婉青']
        st['buffs']['苏婉青'] = []
        self._save(st, ly, rc)
        aff_without_buff = ic.process_affection_system(
            {}, {'苏婉青': ['C烈度_中度']}, ic.MEMORY_FILE
        )['苏婉青']
        self.assertGreater(aff_with_buff, aff_without_buff)

    def test_06_passive_lv4_erosion_intact_exemption_and_homogenization(self):
        # Compare Lv.0 (intact_defense active) vs Lv.4 (exempt + 0.7 erosion + -2 C bonus + 0.75 Turn-2)
        st, ly, rc = self._load()
        st['panels']['系统宿主']['魅力'] = 70
        st['panels']['沈知韫']['被动'] = 0
        st['panels']['沈知韫']['羞耻'] = 90
        st['panels']['沈知韫']['堕落'] = 10
        st['panels']['沈知韫']['好感'] = 78
        self._save(st, ly, rc)
        aff_lv0 = ic.process_affection_system({}, {'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE)['沈知韫']

        st['panels']['沈知韫']['被动'] = 4
        self._save(st, ly, rc)
        aff_lv4 = ic.process_affection_system({}, {'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE)['沈知韫']
        self.assertGreater(aff_lv4, aff_lv0)

        # Lv.4 applies 0.7 shame cap erosion & -2 bonus on active C (at dep=20: cap=86 vs Lv.0 cap=88)
        st['panels']['沈知韫']['堕落'] = 20
        st['panels']['沈知韫']['羞耻'] = 90
        st['panels']['沈知韫']['被动'] = 0
        self._save(st, ly, rc)
        shame_lv0 = ic.process_shame_system({'沈知韫': ['C烈度_轻度']}, ic.MEMORY_FILE)['沈知韫']
        st['panels']['沈知韫']['被动'] = 4
        self._save(st, ly, rc)
        shame_lv4 = ic.process_shame_system({'沈知韫': ['C烈度_轻度']}, ic.MEMORY_FILE)['沈知韫']
        self.assertLess(shame_lv4, shame_lv0)
        self.assertLessEqual(shame_lv4, 86)  # 0.7 * 20 = 14 -> cap 86

        # Lv.4 Turn-2 homogenization preserves 0.75 vs Lv.2 0.50
        st['panels']['沈知韫']['羞耻'] = 80
        st['panels']['沈知韫']['堕落'] = 0
        st['panels']['沈知韫']['被动'] = 2
        self._save(st, ly, rc)
        imm_lv2 = ic.process_shame_system({'沈知韫': ['C烈度_重度', ic._event_tag('SHAME_15')]}, ic.MEMORY_FILE)['沈知韫']
        st['panels']['沈知韫']['被动'] = 4
        self._save(st, ly, rc)
        imm_lv4 = ic.process_shame_system({'沈知韫': ['C烈度_重度', ic._event_tag('SHAME_15')]}, ic.MEMORY_FILE)['沈知韫']
        self.assertLess(imm_lv4, imm_lv2)

        # HOST_16 charm progression works and caps at 100
        host_res = ic.process_host_system([ic._event_tag('HOST_16')], {}, ic.MEMORY_FILE)
        self.assertEqual(host_res['魅力'], 71)

    def test_07_intimate_mode_option_b_decoupling_and_slowburn_costs(self):
        st, ly, rc = self._load()
        st['intimate']['scene_active'] = True
        st['intimate']['session_beats'] = 1
        self._save(st, ly, rc)
        files = _files_snapshot(self.root)

        # Discounted costs active at beat >= 1
        costs = sp.active_costs(self.root, files)
        self.assertEqual(costs, {'A': 5, 'B': 7, 'C': 10})

        def _cond(intensity):
            return {
                'intensity': intensity,
                'effective_progress': True,
                'action_changed': False,
                'scene': '徐家主宅书房',
                'npc': '沈知韫',
                'stress_signals': 0,
                'breakout_triggered': [],
            }

        # Intimate mode allows B with C烈度_轻度 / C烈度_中度
        rr._round_conditions(_cond('B'), {'shame_events': {'沈知韫': ['C烈度_中度']}}, intimate_mode=True)

        # Intimate mode still blocks B with C烈度_深度 / C烈度_重度
        with self.assertRaises(rr.RoundError):
            rr._round_conditions(_cond('B'), {'shame_events': {'沈知韫': ['C烈度_深度']}}, intimate_mode=True)

        # Intimate mode still blocks A with any C烈度_*
        with self.assertRaises(rr.RoundError):
            rr._round_conditions(_cond('A'), {'shame_events': {'沈知韫': ['C烈度_轻度']}}, intimate_mode=True)

        # Daily mode still blocks B with C烈度_轻度
        with self.assertRaises(rr.RoundError):
            rr._round_conditions(_cond('B'), {'shame_events': {'沈知韫': ['C烈度_轻度']}}, intimate_mode=False)

    def test_08_inspect_deployed_remote_monitoring_events_and_compiler_brief(self):
        import interaction_runtime as ir
        st, ly, rc = self._load()
        st['presence']['徐志北'] = {'location': '徐家主宅', 'reason': '主宅书房'}
        st['presence']['沈知韫'] = {'location': '徐家主宅', 'reason': '主宅书房'}
        st['presence']['苏婉青'] = {'location': '市中心顶层公寓', 'reason': '公寓主卧独处'}
        st['panels']['苏婉青']['欲望'] = 76
        st['panels']['苏婉青']['羞耻'] = 48
        st['items']['deployed'] = [{
            'id': 'ITEM-901',
            'name': '微型隐蔽摄像头',
            'quantity': 1,
            'usage_mode': 'deployable_device',
            'category': 'covert',
            'status': '已部署',
            'location': '市中心顶层公寓',
            'spot': '梳妆台背',
            'hidden': True,
            'detected_risk': 10,
        }]
        self._save(st, ly, rc)
        files = _files_snapshot(self.root)

        # resolution allows remote DS_18/DEPRAVITY_10/SHAME_20 on 苏婉青 during inspect_deployed
        op = {'code': 'inspect_deployed', 'item_id': 'ITEM-901'}
        events_ok = {
            'ds_events': {'苏婉青': [ic._event_tag('DS_18')]},
            'depravity_events': {'苏婉青': [ic._event_tag('DEPRAVITY_10')]},
            'shame_events': {'苏婉青': [ic._event_tag('SHAME_20')]},
        }
        body_ok = _make_res_body('CUSTOM', 'C', '远程查看梳妆台背摄像头画面', events_ok, operation=op)
        res = sp.resolution(self.root, files, body_ok)
        self.assertEqual(res['remote_cast'], ['苏婉青'])

        # Direct physical contact event against remote target must STILL be rejected!
        events_bad = {'shame_events': {'苏婉青': ['C烈度_深度']}}
        body_bad = _make_res_body('CUSTOM', 'C', '远程查看梳妆台背摄像头画面', events_bad, operation=op)
        with self.assertRaises(rr.RoundError):
            sp.resolution(self.root, files, body_bad)

        # Stage 1 qualitative brief includes 【远程监控对象态势】
        mem_txt = (self.root / save_store.RENDERED_MEMORY_PATH).read_text(encoding='utf-8')
        view_state = ir.view(rr.RoundStore(self.root), files)
        view_state['remote_vitals_targets'] = ['苏婉青']
        brief = sc.compile_state_qualitative_brief(view_state, mem_txt)
        self.assertIn('【远程监控对象态势】', brief)
        self.assertIn('苏婉青', brief)

        # apply_interaction_operation('inspect_deployed') increments detected_risk by +5
        op_out = ic.apply_interaction_operation({'code': 'inspect_deployed', 'item_id': 'ITEM-901'})
        self.assertEqual(op_out['detected_risk'], 15)

    def test_09_privacy_stealth_bonuses_noise_risk_and_inter_heroine_matrix(self):
        st, ly, rc = self._load()
        st['panels']['沈知韫']['羞耻'] = 80
        st['panels']['沈知韫']['欲望'] = 20
        st['intimate']['privacy'] = 'thin_wall'
        st['intimate']['present_actors'] = ['沈知韫']
        st['intimate']['noise_risk'] = 45
        self._save(st, ly, rc)

        # Privacy thin_wall gives x1.25 (at least -1 extra) shame penalty on C & +2 desire adrenaline
        shame_open = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, privacy='open_public')['沈知韫']
        self._save(st, ly, rc)
        shame_thin = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, privacy='thin_wall')['沈知韫']
        self.assertLess(shame_thin, shame_open)

        self._save(st, ly, rc)
        ds_thin = ic.process_desire_stamina_system({'沈知韫': [ic._event_tag('DS_04')]}, ic.MEMORY_FILE, active_cast=['沈知韫'], privacy='thin_wall')['沈知韫']['欲望']
        self._save(st, ly, rc)
        ds_open = ic.process_desire_stamina_system({'沈知韫': [ic._event_tag('DS_04')]}, ic.MEMORY_FILE, active_cast=['沈知韫'], privacy='open_public')['沈知韫']['欲望']
        self.assertGreater(ds_thin, ds_open)

        # Deep C under thin_wall pushes noise_risk >= 60 and bumps off-room housemate's inter_heroine suspicion
        st, ly, rc = self._load()
        st['intimate']['privacy'] = 'thin_wall'
        st['intimate']['present_actors'] = ['沈知韫']
        st['intimate']['noise_risk'] = 45
        out = ic.advance_intimate_state(
            st,
            {'shame_events': {'沈知韫': ['C烈度_深度']}, 'ds_events': {}},
            active_cast=['沈知韫'],
            building_cast=['沈知韫', '徐念薇'],
        )
        self.assertGreaterEqual(st['intimate']['noise_risk'], 60)
        self.assertTrue(out['stealth_alert'])
        self.assertEqual(st['intimate']['inter_heroine']['徐念薇->沈知韫'], 1)

    def test_10_attire_traces_persistence_intimate_occasion_and_door_catch_guard(self):
        # 1. Attire gifted_items + trace persistence & overnight wash-off preserving 吻痕
        st, ly, rc = self._load()
        st['intimate']['traces']['沈知韫'] = [
            {'kind': '潮红未退', 'desc': '耳后潮红', 'turns': 3, 'visible': True},
            {'kind': '吻痕', 'desc': '锁骨下方浅红吻痕', 'turns': 5, 'visible': True},
        ]
        st['intimate']['attire']['沈知韫']['state'] = 'disheveled'
        ic.advance_intimate_state(st, {}, active_cast=['沈知韫'], sleep_kind='overnight')
        kinds = [t['kind'] for t in st['intimate']['traces']['沈知韫']]
        self.assertNotIn('潮红未退', kinds)
        self.assertIn('吻痕', kinds)
        self.assertEqual(st['intimate']['attire']['沈知韫']['state'], 'neat')

        # 2. Relationship intimate occasion preserved in compile_relationships() & verified
        reg = rq.RelationshipRegistry(self.root)
        rows = reg.verify_view()
        self.assertGreaterEqual(len(rows), 41)
        compiled = sc.compile_relationships(self.root, ['沈知韫', '苏婉青'])
        self.assertIn('i', compiled['forms']['沈知韫->徐志北'])
        self.assertIn('知韫', compiled['forms']['沈知韫->徐志北']['i']['s'])

        # 3. Door-catch spatial precondition: when heroine is ALREADY in present_actors and scene_turns >= 1,
        #    door-catch T2/T3/T4 erotic beats must NOT fire (eliminates teleportation glitches!)
        cat = sp.load_world_beats(self.root)
        door_ids = {b['id'] for b in cat['beats'] if b.get('requires_door_catch')}
        self.assertGreaterEqual(len(door_ids), 9)
        st, ly, rc = self._load()
        st['panels']['沈知韫']['好感'] = 85
        st['panels']['沈知韫']['羞耻'] = 45
        st['panels']['沈知韫']['欲望'] = 80
        st['panels']['沈知韫']['堕落'] = 30
        st.setdefault('physiology', {}).setdefault('沈知韫', {})['unrelieved_streak'] = 3
        st['intimate']['present_actors'] = ['沈知韫']
        st['director']['scene_location'] = '徐家主宅'
        st['director']['scene_turns'] = 2
        st['director']['turns_since_beat'] = 5
        st['director']['global_cooldown'] = 0
        self._save(st, ly, rc)
        mem_txt = (self.root / save_store.RENDERED_MEMORY_PATH).read_text(encoding='utf-8')

        class _FixedRng:
            def __init__(self, vals):
                self._vals = list(vals)

            def random(self):
                return self._vals.pop(0) if self._vals else 0.01

            def choices(self, pop, weights=None, k=1):
                return [pop[0]] * k

        roll = sp.roll_director_beat(
            self.root,
            {'location': '徐家主宅', 'cast': ['沈知韫'], 'items': [], 'intimate': st['intimate']},
            mem_txt,
            {'clock': {'day': 2, 'time': '22:30'}},
            '周三',
            rng=_FixedRng([0.01, 0.99, 0.99]),
        )
        self.assertNotIn(roll.get('event_id'), door_ids)


if __name__ == '__main__':
    unittest.main()

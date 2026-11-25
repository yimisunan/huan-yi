"""Comprehensive verification suite for v4 adult mechanics (host desire/vigor/floor guard, 5-zone body dev & signature zones, 5-tier Charm rework, and Private Keepsakes vault)."""
import base64
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
import interaction_runtime as ir
import round_runtime as rr
import save_store
import story_compiler as sc
import story_progression as sp
import story_service as ss


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


class AdultSystemsV4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = fixture(Path(self.tmp.name), progression=True)
        self.prev = _bind_engine(self.root)

    def tearDown(self):
        _restore_engine(self.prev)
        self.tmp.cleanup()

    def _load(self):
        return save_store.load_bundle(self.root)

    def _save(self, st, ly, rc=None):
        save_store.save_bundle(self.root, st, ly, rc)

    def test_01_host_desire_edging_release_synced_climax_and_track_a_sovereignty(self):
        st, ly, rc = self._load()
        st['panels']['系统宿主']['魅力'] = 70
        st['intimate']['scene_active'] = True
        st['intimate']['host_phys'] = {'desire': 75, 'vigor': 90, 'release_count': 0, 'edging_streak': 0, 'fetishes': []}

        # High desire push without release -> reaches 100 edging state; NEVER auto-releases (Track A sovereignty)
        meta1 = ic.advance_intimate_state(
            st,
            {'shame_events': {'沈知韫': ['C烈度_重度']}, 'ds_events': {'沈知韫': ['刺激_物理']}},
            scene_state={'body_acts': {'沈知韫': ['foot']}},
            active_cast=['沈知韫'],
            category='C',
        )
        hp = st['intimate']['host_phys']
        self.assertEqual(hp['desire'], 100)
        self.assertEqual(hp['release_count'], 0)
        self.assertEqual(hp['edging_streak'], 1)
        self.assertFalse(meta1['synced_climax'])
        self.assertLess(hp['vigor'], 90)

        # Edging bonus (+0.10) feeds heroine orgasm multiplier
        st['panels']['沈知韫']['欲望'] = 80
        st['panels']['沈知韫']['堕落'] = 40
        st['panels']['沈知韫']['高潮'] = 0
        self._save(st, ly, rc)
        org_no_edge = ic.process_desire_stamina_system({'沈知韫': ['高潮_中度累积']}, ic.MEMORY_FILE, host_desire=30)['沈知韫']['高潮']
        org_with_edge = ic.process_desire_stamina_system({'沈知韫': ['高潮_中度累积']}, ic.MEMORY_FILE, host_desire=90)['沈知韫']['高潮']
        self.assertGreater(org_with_edge, org_no_edge)

        # Explicit host release + heroine climax -> synced_climax + milestone +1 Charm + reset desire to 20
        charm_before = st['panels']['系统宿主']['魅力']
        meta2 = ic.advance_intimate_state(
            st,
            {'shame_events': {'沈知韫': ['内射_常规']}, 'ds_events': {'沈知韫': ['触发高潮_绝顶清算']}},
            scene_state={'host_release': True, 'intimate_active': True},
            active_cast=['沈知韫'],
            category='C',
        )
        self.assertTrue(meta2['synced_climax'])
        self.assertEqual(meta2['charm_milestone_gain'], 1)
        self.assertEqual(st['panels']['系统宿主']['魅力'], charm_before + 1)
        self.assertEqual(st['intimate']['host_phys']['release_count'], 1)
        self.assertEqual(st['intimate']['host_phys']['desire'], 20)
        self.assertEqual(st['intimate']['host_phys']['edging_streak'], 0)

        # Overnight sleep restores vigor=100; high residual desire stays 25, low clears to 0
        st['intimate']['host_phys']['desire'] = 80
        st['intimate']['host_phys']['vigor'] = 22
        ic.advance_intimate_state(st, {}, sleep_kind='overnight')
        self.assertEqual(st['intimate']['host_phys']['vigor'], 100)
        self.assertEqual(st['intimate']['host_phys']['desire'], 25)
        ic.advance_intimate_state(st, {}, sleep_kind='overnight')
        self.assertEqual(st['intimate']['host_phys']['desire'], 0)

    def test_02_intimate_stamina_1_2_3_floor_guard_vigor_pool_and_no_midsex_rest(self):
        st, ly, rc = self._load()
        st['panels']['系统宿主']['体力'] = 10
        st['intimate']['scene_active'] = True
        st['intimate']['session_beats'] = 1
        st['intimate']['host_phys'] = {'desire': 50, 'vigor': 75, 'release_count': 0, 'edging_streak': 0, 'fetishes': []}
        self._save(st, ly, rc)
        files = _files_snapshot(self.root)

        # Active costs are 1/2/3 and stamina guard is active with floor=10
        self.assertEqual(sp.active_costs(self.root, files), {'A': 1, 'B': 2, 'C': 3})
        guard = sp.stamina_guard_info(self.root, files)
        self.assertTrue(guard['active'])
        self.assertEqual(guard['floor'], 10)

        # At stamina=10 with vigor=75, CUSTOM & C quote charge 0 stamina (vigor absorbs effort)
        q_c = sp.quote(self.root, files, {'segment_id': 'seg-0001', 'option_id': 'C'}, '继续深入')
        q_custom = sp.quote(self.root, files, {'segment_id': 'seg-0001', 'option_id': 'CUSTOM'}, '换个姿势贴紧')
        self.assertEqual(q_c['total'], 0)
        self.assertEqual(q_custom['total'], 0)
        self.assertEqual(q_custom['after'], 10)
        self.assertTrue(q_custom['stamina_guard'])

        # At stamina=12 with guard active, C raw=3 is capped to 2 (floor=10)
        st['panels']['系统宿主']['体力'] = 12
        self._save(st, ly, rc)
        files12 = _files_snapshot(self.root)
        q12 = sp.quote(self.root, files12, {'segment_id': 'seg-0001', 'option_id': 'C'}, '继续')
        self.assertEqual(q12['total'], 2)
        self.assertEqual(q12['after'], 10)

        # When vigor drops below 15, floor guard turns off
        st['intimate']['host_phys']['vigor'] = 10
        self._save(st, ly, rc)
        files_low_v = _files_snapshot(self.root)
        self.assertFalse(sp.stamina_guard_info(self.root, files_low_v)['active'])
        q_unguarded = sp.quote(self.root, files_low_v, {'segment_id': 'seg-0001', 'option_id': 'C'}, '继续')
        self.assertEqual(q_unguarded['total'], 3)

        # Recovery item also restores vigor (+15 / +25)
        st['panels']['系统宿主']['体力'] = 60
        st['intimate']['host_phys']['vigor'] = 40
        st['items']['active'] = [{
            'id': 'ITEM-777', 'name': '参茶补气膏', 'type': '临时性', 'category': 'daily',
            'usage_mode': 'consumable_host', 'desc': '温补体力与精力', 'quantity': 1,
            'status': '仓库中', 'location': '无', 'target': '未使用', 'duration': '无',
            'expire_rule': '无', 'usage_record': '无', 'remark': '测试',
            'system_effect': 'host_stamina:15', 'giftable': False,
        }]
        self._save(st, ly, rc)
        ic.consume_story_recovery_item('ITEM-777', 15, 1)
        st_after, _, _ = self._load()
        self.assertEqual(st_after['panels']['系统宿主']['体力'], 75)
        self.assertEqual(st_after['intimate']['host_phys']['vigor'], 65)

    def test_03_heroine_5_zone_body_development_signature_zones_and_prose_fallback(self):
        st, ly, rc = self._load()
        st['panels']['沈知韫']['羞耻'] = 70
        st['panels']['沈知韫']['欲望'] = 50
        st['panels']['沈知韫']['高潮'] = 0
        self._save(st, ly, rc)

        # Signature zone (沈知韫 -> foot) gives extra -1 shame drop & +3 desire
        shame_plain = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=70, body_acts={'沈知韫': ['hand']})['沈知韫']
        shame_sig = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=70, body_acts={'沈知韫': ['foot']})['沈知韫']
        self.assertEqual(shame_plain - shame_sig, 1)

        ds_plain = ic.process_desire_stamina_system({'沈知韫': ['刺激_物理']}, ic.MEMORY_FILE, body_acts={'沈知韫': ['hand']})['沈知韫']['欲望']
        ds_sig = ic.process_desire_stamina_system({'沈知韫': ['刺激_物理']}, ic.MEMORY_FILE, body_acts={'沈知韫': ['foot']})['沈知韫']['欲望']
        self.assertEqual(ds_sig - ds_plain, 3)

        # Prose fallback infers foot & chest when explicit body_acts omitted
        inferred = ic.infer_body_acts_from_prose(
            '她穿着黑丝的玉足轻轻踩在他掌心，脚踝微微绷直。',
            {'shame_events': {'沈知韫': ['C烈度_深度']}},
        )
        self.assertEqual(inferred, {'沈知韫': ['foot']})

        # Signature zone develops at 1.35x speed (deep base 12 -> 16 vs non-signature 12)
        ic.advance_intimate_state(
            st,
            {'shame_events': {'沈知韫': ['C烈度_深度']}},
            scene_state={'body_acts': {'沈知韫': ['foot', 'hand']}},
            active_cast=['沈知韫'],
            category='C',
        )
        self.assertEqual(st['intimate']['body_dev']['沈知韫']['foot'], 16)
        self.assertEqual(st['intimate']['body_dev']['沈知韫']['hand'], 12)

        # Crossing Lv.2 (>=50) triggers dev_milestones & +1 Charm
        st['intimate']['body_dev']['沈知韫']['foot'] = 44
        st['panels']['系统宿主']['魅力'] = 72
        meta_lv2 = ic.advance_intimate_state(
            st,
            {'shame_events': {'沈知韫': ['C烈度_深度']}},
            scene_state={'body_acts': {'沈知韫': ['foot']}},
            active_cast=['沈知韫'],
            category='C',
        )
        self.assertEqual(st['intimate']['body_dev']['沈知韫']['foot'], 60)
        self.assertEqual(len(meta_lv2['dev_milestones']), 1)
        self.assertEqual(meta_lv2['dev_milestones'][0]['level'], 2)
        self.assertEqual(st['panels']['系统宿主']['魅力'], 73)

        # Lv.3 body dev yields noticeably higher orgasm gain than Lv.0
        org_lv0 = ic.process_desire_stamina_system(
            {'沈知韫': ['高潮_中度累积']}, ic.MEMORY_FILE,
            body_dev={'沈知韫': {'foot': 0}}, body_acts={'沈知韫': ['foot']},
        )['沈知韫']['高潮']
        org_lv3 = ic.process_desire_stamina_system(
            {'沈知韫': ['高潮_中度累积']}, ic.MEMORY_FILE,
            body_dev={'沈知韫': {'foot': 90}}, body_acts={'沈知韫': ['foot']},
        )['沈知韫']['高潮']
        self.assertGreater(org_lv3, org_lv0)

    def test_04_five_tier_charm_affection_shame_orgasm_shop_discount_and_passive_growth(self):
        # Verify 5-tier ladder values
        self.assertEqual(ic.charm_tier_info(70)['shop_discount'], 1.0)
        self.assertEqual(ic.charm_tier_info(75)['shop_discount'], 0.90)
        self.assertEqual(ic.charm_tier_info(85)['shop_discount'], 0.85)
        self.assertEqual(ic.charm_tier_info(95)['aff_bonus'], 2)

        st, ly, rc = self._load()
        st['panels']['沈知韫']['好感'] = 40
        st['panels']['沈知韫']['羞耻'] = 75
        st['panels']['沈知韫']['欲望'] = 50
        st['panels']['沈知韫']['高潮'] = 0
        self._save(st, ly, rc)

        # Affection gain scales with Charm 70 -> 75 -> 95
        pos_aff_tag = ic._event_tag('AFFECTION_03')
        aff70 = ic.process_affection_system({'沈知韫': [pos_aff_tag]}, {}, ic.MEMORY_FILE, host_charm=70)['沈知韫']
        aff75 = ic.process_affection_system({'沈知韫': [pos_aff_tag]}, {}, ic.MEMORY_FILE, host_charm=75)['沈知韫']
        aff95 = ic.process_affection_system({'沈知韫': [pos_aff_tag]}, {}, ic.MEMORY_FILE, host_charm=95)['沈知韫']
        self.assertEqual(aff75 - aff70, 1)
        self.assertEqual(aff95 - aff70, 2)

        # Violation drop mitigated at Charm 75/95
        drop70 = ic.process_affection_system({}, {'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=70)['沈知韫']
        drop95 = ic.process_affection_system({}, {'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=95)['沈知韫']
        self.assertGreater(drop95, drop70)

        # Shame extra drop at Charm 85 (-1) / 95 (-2)
        sh70 = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=70)['沈知韫']
        sh85 = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=85)['沈知韫']
        sh95 = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, ic.MEMORY_FILE, host_charm=95)['沈知韫']
        self.assertEqual(sh70 - sh85, 1)
        self.assertEqual(sh70 - sh95, 2)

        # Shop discount at Charm 85 (85%) in shop_view() AND redeem_shop_item()
        st['panels']['系统宿主']['积分'] = 200
        st['panels']['系统宿主']['经验值'] = 100
        st['panels']['系统宿主']['魅力'] = 85
        self._save(st, ly, rc)
        svc = ss.StoryService(self.root)
        sview = svc.shop_view()
        self.assertEqual(sview['charm_discount'], 0.85)
        first_item = next(it for it in sview['items'] if it.get('unlocked') and it['base_price'] >= 10)
        self.assertEqual(first_item['effective_price'], max(1, int(round(first_item['base_price'] * 0.85))))

        rev = rr._revision(_files_snapshot(self.root))
        res_buy = sp.redeem_shop_item(svc, {
            'request_id': 'buy-charm-disc-1',
            'base_revision': rev,
            'save_epoch': svc._save_epoch(),
            'item_id': first_item['id'],
        })
        self.assertEqual(res_buy['receipt']['price'], first_item['effective_price'])
        self.assertEqual(res_buy['receipt']['points_after'], 200 - first_item['effective_price'])

        # Passive skill upgrade awards +1 Charm
        rev2 = rr._revision(_files_snapshot(self.root))
        res_pas = sp.upgrade_passive_skill(svc, {
            'request_id': 'pas-charm-up-1',
            'base_revision': rev2,
            'save_epoch': svc._save_epoch(),
            'target': '沈知韫',
        })
        self.assertEqual(res_pas['receipt']['charm_gain'], 1)
        st_post, _, _ = self._load()
        self.assertEqual(st_post['panels']['系统宿主']['魅力'], 86)

    def test_05_keepsakes_full_lifecycle_scene_state_actions_fetishes_and_view_compiler(self):
        st, ly, rc = self._load()
        st['presence']['徐志北'] = {'location': '徐家主宅', 'reason': '主宅二楼走廊'}
        st['presence']['沈知韫'] = {'location': '徐家主宅', 'reason': '主卧整理衣物'}
        st['presence']['苏婉青'] = {'location': '市中心顶层公寓', 'reason': '公寓休息'}
        self._save(st, ly, rc)

        # 1. Validate scene_state.keepsake_adds via round_runtime._validate_scene_state
        ss_valid = rr._validate_scene_state({
            'keepsake_adds': [
                {'owner': '沈知韫', 'name': '酒红蕾丝贴身内裤', 'kind': 'panties', 'method': 'stolen', 'condition': 'fresh_warm', 'desc': '刚换下尚带温热淡香'},
                {'owner': '沈知韫', 'name': '超薄黑丝连裤袜', 'kind': 'stockings', 'method': 'stolen', 'condition': 'fresh_warm', 'desc': '脚尖处微带暖意'},
            ],
            'body_acts': {'沈知韫': ['foot']},
        }, ['沈知韫'])
        self.assertEqual(len(ss_valid['keepsake_adds']), 2)
        self.assertEqual(ss_valid['body_acts'], {'沈知韫': ['foot']})

        # 2. Register keepsakes deterministically via advance_intimate_state -> bypasses shop/task item anti-cheat
        meta = ic.advance_intimate_state(
            st,
            {'shame_events': {'沈知韫': ['C烈度_轻度']}},
            scene_state=ss_valid,
            active_cast=['沈知韫'],
            clock_str='第1天 22:10',
            location='徐家主宅',
        )
        self.assertEqual(len(meta['keepsakes_added']), 2)
        ks1_id = st['intimate']['keepsakes'][0]['id']
        ks2_id = st['intimate']['keepsakes'][1]['id']
        self.assertTrue(ks1_id.startswith('KS-'))
        # 2 stolen/panties+stockings items automatically derive host fetish tags
        self.assertIn('足踝黑丝控', st['intimate']['host_phys']['fetishes'])
        self.assertIn('贴身私藏癖', st['intimate']['host_phys']['fetishes'])
        # Stolen keepsake bumps host desire (+10 on top of C light +8)
        self.assertGreaterEqual(st['intimate']['host_phys']['desire'], 18)
        self._save(st, ly, rc)

        # 3. Validate keepsake_action operations & preconditions
        files = _files_snapshot(self.root)
        op_sniff = ir.operation(self.root, files, {'code': 'keepsake_action', 'keepsake_id': ks1_id, 'action_type': 'sniff_play'}, explicit=True)
        self.assertEqual(op_sniff['action_type'], 'sniff_play')
        op_confront = ir.operation(self.root, files, {'code': 'keepsake_action', 'keepsake_id': ks1_id, 'action_type': 'confront'}, explicit=True)
        self.assertEqual(op_confront['action_type'], 'confront')

        # Confront fails when owner is NOT in current scene
        st['presence']['沈知韫']['location'] = '商业中心'
        self._save(st, ly, rc)
        with self.assertRaises(rr.RoundError):
            ir.operation(self.root, _files_snapshot(self.root), {'code': 'keepsake_action', 'keepsake_id': ks1_id, 'action_type': 'confront'}, explicit=True)
        st['presence']['沈知韫']['location'] = '徐家主宅'
        self._save(st, ly, rc)

        # 4. Execute sniff_play (+18 desire), confront (owner_aware=True), return_secret (removes item)
        des_before = st['intimate']['host_phys']['desire']
        ic.apply_interaction_operation({'code': 'keepsake_action', 'keepsake_id': ks1_id, 'action_type': 'sniff_play'})
        st_s, _, _ = self._load()
        self.assertEqual(st_s['intimate']['host_phys']['desire'], min(100, des_before + 18))

        ic.apply_interaction_operation({'code': 'keepsake_action', 'keepsake_id': ks1_id, 'action_type': 'confront'})
        st_c, _, _ = self._load()
        ks1_now = next(k for k in st_c['intimate']['keepsakes'] if k['id'] == ks1_id)
        self.assertTrue(ks1_now['owner_aware'])

        # 5. Check view() metadata & compiler qualitative brief include keepsakes, charm tier, body_zone_meta
        store = rr.RoundStore(self.root)
        v = ir.view(store, _files_snapshot(self.root))
        self.assertIn('host_charm_tier', v)
        self.assertIn('body_zone_meta', v)
        self.assertEqual(v['body_zone_meta']['level_labels'][0], '生涩防备')
        self.assertIn('keepsake_meta', v)
        self.assertTrue(len(v['intimate']['keepsakes']) == 2)

        mem_txt = (self.root / save_store.RENDERED_MEMORY_PATH).read_text(encoding='utf-8')
        brief = sc.compile_state_qualitative_brief(v, mem_txt)
        self.assertIn('宿主私密珍藏', brief)
        self.assertIn('失主已知', brief)
        self.assertIn('失主未觉', brief)

        # 6. return_secret removes ks2 from vault
        ic.apply_interaction_operation({'code': 'keepsake_action', 'keepsake_id': ks2_id, 'action_type': 'return_secret'})
        st_r, _, _ = self._load()
        self.assertEqual(len(st_r['intimate']['keepsakes']), 1)
        self.assertEqual(st_r['intimate']['keepsakes'][0]['id'], ks1_id)


if __name__ == '__main__':
    unittest.main()

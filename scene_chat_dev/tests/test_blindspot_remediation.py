import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import interaction_runtime as ir
import save_store as ss
import scene_chat
import story_compiler as sc
import story_progression as sp


def _make_state(**overrides):
    intl = ss.default_intimate()
    mind = ss.default_npc_mind()
    base = {
        'location': '徐家主宅',
        'cast': ['苏婉青'],
        'presence': {
            '沈知韫': {'location': '徐家主宅', 'reason': '在宅'},
            '苏婉青': {'location': '徐家主宅', 'reason': '来访'},
            '徐念薇': {'location': '徐家主宅', 'reason': '在宅'},
            '徐志北': {'location': '徐家主宅', 'reason': '在宅'},
        },
        'panels': [
            '[系统宿主] 积分 180 | 经验值 60 | 体力 85 | 魅力 75 | 商业嗅觉 35',
            '[沈知韫] 好感 58 | 堕落 25 | 欲望 35 | 羞耻 68 | 体力 70 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.3',
            '[苏婉青] 好感 72 | 堕落 28 | 欲望 45 | 羞耻 62 | 体力 75 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.2',
            '[徐念薇] 好感 46 | 堕落 14 | 欲望 20 | 羞耻 78 | 体力 80 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.1',
        ],
        'items': [],
        'deployed_items': [],
        'delivered_items': [],
        'tasks': {'current': None, 'history': []},
        'intimate': intl,
        'mechanics': {'secrets_unlocked': []},
        'npc_mind': mind,
        'remote_vitals_targets': [],
        'weekday': '周四',
        'prologue_active': False,
        'vigilance': {'position': '外地', 'targets': {}},
        'physiology': {},
    }
    base.update(overrides)
    return base


class BlindspotRemediationTests(unittest.TestCase):
    def test_p0_1_stage2_restored_rules_and_budget(self):
        state = _make_state()
        spec = sc.build_settlement_spec(
            ROOT, state, {}, '继续交流', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 3, 'last_closed': 2, 'phase': 'ready'},
            '', {'kind': 'action', 'conditions_required': True, 'intimate_mode': False, 'category_policy': {'mode': 'custom'}},
            {}, {'requested': None},
        )
        s2_sys = spec['system_prompt']
        self.assertLess(len(s2_sys), 12000, f'Stage 2 static prompt exceeded 12K budget: {len(s2_sys)}')
        parts = s2_sys.split('【事件触发判定精简规则】')
        header_part = parts[0].split('【合法事件标签白名单】')[0]
        prose_part = parts[1] if len(parts) > 1 else ''
        combined_non_whitelist = header_part + '\n' + prose_part
        for kw in (
            '临界突破_魅力压迫', '临界突破_心理羞辱', '场景切换_欲望回落', '外射_体表面部',
            '无意识被侵_苏醒发现', '耻感反弹_苏醒',
            '破局_日常冗余', '破局_模式重复', '破局_社交淤积', '破局_张力淤积',
            'K01', '亡夫遗嘱唯一合法继承人', 'INTEL-001', 'INTEL-002', 'INTEL-003', 'SECRET-XNW-PAINTING',
        ):
            self.assertIn(kw, combined_non_whitelist, f'Missing restored Stage 2 guidance: {kw}')

    def test_p0_2_studio_painting_unlock_hint_and_guardrail_harmony(self):
        state = _make_state(location='工作室', cast=['徐念薇'])
        delta_raw = sc.build_user_delta(
            ROOT, state, {'text': '', 'index': []}, [], [],
            '我走近角落画架，伸手掀开蒙着的那块白布看旧画。', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 3, 'last_closed': 2, 'phase': 'ready'},
            '', include_full_anchor=True, mode='dual_stream_v2',
        )
        delta = json.loads(delta_raw)
        self.assertIn('painting_unlock_hint', delta)

        # Already unlocked -> no hint needed
        state_unlocked = _make_state(location='工作室', cast=['徐念薇'], mechanics={'secrets_unlocked': ['SECRET-XNW-PAINTING']})
        delta_u = json.loads(sc.build_user_delta(
            ROOT, state_unlocked, {'text': '', 'index': []}, [], [],
            '我再看看那幅旧画。', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 4, 'last_closed': 3, 'phase': 'ready'},
            '', include_full_anchor=True, mode='dual_stream_v2',
        ))
        self.assertNotIn('painting_unlock_hint', delta_u)

        # When Stage 2 emits unlock_secrets=["SECRET-XNW-PAINTING"], _effective_guardrail_secrets prevents false leak
        eff = ir._effective_guardrail_secrets(
            {'mechanics': {'secrets_unlocked': []}},
            {'resolution': {'scene_state': {'unlock_secrets': ['SECRET-XNW-PAINTING']}}},
            {},
        )
        self.assertIn('SECRET-XNW-PAINTING', eff)
        msgs = [
            {'kind': 'action', 'speaker': '徐志北', 'text': '我掀开白布。'},
            {'kind': 'dialogue', 'speaker': '徐念薇', 'text': '别碰那幅画！画展被赞助商暗箱撤展的事不用你管！'},
        ]
        gr = sc.guardrail_check(ROOT, '工作室', ['徐念薇'], msgs, '', secrets_unlocked=eff)
        self.assertFalse(gr.get('review_signals'))

    def test_p0_3_su_wanqing_defection_parity(self):
        # Exposed INTEL-002 but aff=55, shame=70 -> backend _is_su_defected is False -> must NOT claim ceased spying
        st_partial = _make_state(
            cast=['苏婉青'],
            panels=[
                '[系统宿主] 积分 100 | 经验值 0 | 体力 100 | 魅力 60 | 商业嗅觉 30',
                '[苏婉青] 好感 55 | 堕落 10 | 欲望 20 | 羞耻 70 | 体力 90 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.0',
            ],
            mechanics={'secrets_unlocked': ['INTEL-002']},
        )
        brief_partial = sc.compile_state_qualitative_brief(st_partial, '')
        self.assertIn('尚未彻底倒戈', brief_partial)
        self.assertNotIn('不再主动替徐承邺盯梢', brief_partial)

        # Exposed INTEL-002 AND aff=75, shame=45 -> backend _is_su_defected is True
        st_full = _make_state(
            cast=['苏婉青'],
            panels=[
                '[系统宿主] 积分 100 | 经验值 0 | 体力 100 | 魅力 60 | 商业嗅觉 30',
                '[苏婉青] 好感 75 | 堕落 30 | 欲望 45 | 羞耻 45 | 体力 90 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.2',
            ],
            mechanics={'secrets_unlocked': ['INTEL-002']},
        )
        brief_full = sc.compile_state_qualitative_brief(st_full, '')
        self.assertIn('不再主动替徐承邺盯梢', brief_full)

    def test_p0_4_unified_person_aliases_and_npc_surface_scan(self):
        svc = scene_chat.SceneService(ROOT, None)
        refs = svc.references('趁我妈和嫂子不在，顺便提防我哥那边来电', [])
        self.assertEqual({r['name'] for r in refs}, {'沈知韫', '苏婉青', '徐承邺'})

        # Title aliases
        refs_titles = svc.references('沈总和少奶奶下午去哪了？徐总还没回？', [])
        self.assertEqual({r['name'] for r in refs_titles}, {'沈知韫', '苏婉青', '徐承邺'})

        # NPC surface line triggers follow-up pronoun resolution, but unspoken ｜subtext does NOT
        hist_surface = [{'input': '怎么了', 'messages': [{'speaker': '徐念薇', 'text': '大哥刚才来过电话'}]}]
        self.assertEqual({r['name'] for r in svc.references('他怎么说的？', hist_surface)}, {'徐承邺'})

        hist_subtext_only = [{'input': '怎么了', 'messages': [{'speaker': '徐念薇', 'text': '｛没事｜可不能让大哥知道｝'}]}]
        self.assertEqual(svc.references('好吧', hist_subtext_only), [])

        # Zero false positives on 小姐 / 大妈
        self.assertEqual(svc.references('路过的小姐和保姆大妈聊了两句', []), [])

    def test_p1_1_stage2_compact_handoff_context(self):
        state = _make_state(
            cast=['苏婉青', '沈知韫'],
            panels=[
                '[系统宿主] 积分 180 | 经验值 60 | 体力 85 | 魅力 75 | 商业嗅觉 35',
                '[沈知韫] 好感 60 | 堕落 10 | 欲望 20 | 羞耻 82 | 体力 80 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.1',
                '[苏婉青] 好感 80 | 堕落 45 | 欲望 65 | 羞耻 35 | 体力 75 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.3',
            ],
            intimate={
                **ss.default_intimate(),
                'scene_active': True,
                'privacy': 'thin_wall',
                'present_actors': ['苏婉青'],
                'inter_heroine': {'沈知韫->苏婉青': 2},
            },
            npc_mind={
                '苏婉青': {'mood': '余热未散', 'preoccupation': '留心门外', 'impressions': [{'text': '敏锐'}], 'resentment': 15, 'last_shift_kind': 'coy_fluster'},
            },
            vigilance={'position': '徐家主宅', 'targets': {'苏婉青': {'vigilance': 30, 'discovery': 1}}},
            physiology={'苏婉青': {'pregnancy_stage': 'latent'}},
        )
        droll = {'triggered': True, 'mode': 'thread_spark', 'anchor': '茶室备用钥匙', 'spark_pair': '眼神/茶香', 'banned_channels': ['电话']}
        hist = [{'input': '我端茶试探苏婉青', 'decision': {'options': [{'id': 'A', 'text': '顺势寒暄'}, {'id': 'B', 'text': '低声追问'}]}, 'messages': [{'speaker': '苏婉青', 'text': '怎么了'}]}]
        spec = sc.build_settlement_spec(
            ROOT, state, {}, '我继续靠近她', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 5, 'last_closed': 4, 'phase': 'ready'},
            '', {'kind': 'action', 'conditions_required': True, 'intimate_mode': True, 'category_policy': {'mode': 'custom'}},
            {}, {'requested': None}, director_roll=droll, history=hist,
        )
        uctx = spec['user_context']
        self.assertIn('stage3', uctx['persona_anchors']['苏婉青'])
        self.assertIn('stage1', uctx['persona_anchors']['沈知韫'])
        self.assertEqual(uctx['cast_mind']['苏婉青']['resentment'], 15)
        self.assertEqual(uctx['cast_mind']['苏婉青']['last_shift_kind'], 'coy_fluster')
        self.assertEqual(uctx['vigilance_brief']['xu_position'], '徐家主宅')
        self.assertEqual(uctx['pregnancy_latent'], ['苏婉青'])
        self.assertEqual(uctx['intimate']['inter_heroine'], {'沈知韫->苏婉青': 2})
        self.assertEqual(len(uctx['intimate']['inter_heroine_pairs']), 6)
        self.assertIn('prev_turn_brief', uctx)
        self.assertIn('茶室备用钥匙', uctx['director_context'].get('triggered_summary', ''))

    def test_p1_2_item_matching_collision_and_intel_summary(self):
        cat_items = [
            {'id': 'SHOP-003', 'name': '精品黑咖啡浓缩液', 'usage_mode': 'consumable_host', 'desc': '浓缩黑咖啡'},
            {'id': 'SHOP-014', 'name': '无色微醺桃露（催化滴剂）', 'usage_mode': 'consumable_target', 'desc': '无色滴剂'},
            {'id': 'SHOP-015', 'name': '纽扣式微型针孔摄像头', 'usage_mode': 'deployable_device', 'desc': '微摄'},
            {'id': 'SHOP-009', 'name': '热感幽兰按摩精油', 'usage_mode': 'consumable_target', 'desc': '幽兰精油'},
            {'id': 'DYN-001', 'name': '玫瑰温感按摩精油', 'usage_mode': 'consumable_target', 'desc': '玫瑰精油'},
        ]
        self.assertEqual([x['id'] for x in sc.find_mentioned_items('泡一杯黑咖啡提神', cat_items)], ['SHOP-003'])
        self.assertEqual([x['id'] for x in sc.find_mentioned_items('滴两滴催化滴剂', cat_items)], ['SHOP-014'])
        self.assertEqual([x['id'] for x in sc.find_mentioned_items('把针孔藏在书架上', cat_items)], ['SHOP-015'])
        # Collision fallback returns both colliding oils rather than []
        collided = [x['id'] for x in sc.find_mentioned_items('拿出精油涂在掌心', cat_items)]
        self.assertEqual(set(collided), {'SHOP-009', 'DYN-001'})

        # Untouched Stage 2 item stubs include giftable & short hint
        compact = sc._compact_items_for_settlement(cat_items, '随便聊聊', None)
        self.assertTrue(all('giftable' in x and 'hint' in x for x in compact))

        # Foreground single-device fallback when deployed_items_remote is diff-omitted
        dev_state = _make_state(
            deployed_items=[{'id': 'DEV-1', 'name': '纽扣式微型针孔摄像头', 'location': '市中心顶层公寓', 'spot': '梳妆台', 'system_effect': 'deploy_device:camera'}],
        )
        sdelta1 = {}
        sc.build_user_delta(
            ROOT, dev_state, {'text': '', 'index': []}, [], [], '闲聊', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 1, 'last_closed': 0, 'phase': 'ready'},
            '', include_full_anchor=True, mode='dual_stream_v2', session_delta_out=sdelta1,
        )
        delta2 = json.loads(sc.build_user_delta(
            ROOT, dev_state, {'text': '', 'index': []}, [], [], '趁没人打开手机看看远程监控画面', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 2, 'last_closed': 1, 'phase': 'ready'},
            '', include_full_anchor=False, mode='dual_stream_v2', prev_state_hashes=sdelta1['state_hashes'],
        ))
        self.assertIn('mentioned_items', delta2)
        self.assertEqual(delta2['mentioned_items'][0]['id'], 'DEV-1')

        # Dual-stage qualitative_state includes in-world intel desc & targets without RPG numbers
        mem_with_intel = f'{sp.INTEL_ANCHOR}\n持有情报：INTEL-001\n已耗情报：（无）\n'
        icat = sp.load_intel_catalog(ROOT, optional=True)
        brief_intel = sc.compile_state_qualitative_brief(_make_state(), mem_with_intel, intel_catalog=icat)
        self.assertIn('深圳账目异常', brief_intel)
        self.assertIn('徐承邺/沈知韫', brief_intel)
        self.assertIn('深圳分部', brief_intel)
        self.assertNotIn('扣3羞耻', brief_intel)

    def test_p1_3_mid_session_stage_patch_and_zero_zone1_drift(self):
        state_t1 = _make_state(
            cast=['徐念薇'],
            panels=[
                '[系统宿主] 积分 180 | 经验值 60 | 体力 85 | 魅力 75 | 商业嗅觉 35',
                '[徐念薇] 好感 35 | 堕落 5 | 欲望 10 | 羞耻 90 | 体力 80 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.0',
            ],
        )
        pflags1 = sc.compute_zone1_persona_flags(state_t1, '')
        z1_flags1 = {'vig': False, 'intl': False, **pflags1}
        z1_t1 = sc.build_zone1_scene(ROOT, state_t1, ['徐念薇'], (), '', mode='dual_stream_v2', frozen_flags=z1_flags1)

        state_t2 = copy.deepcopy(state_t1)
        state_t2['panels'][1] = '[徐念薇] 好感 78 | 堕落 48 | 欲望 65 | 羞耻 38 | 体力 70 | 高潮 20% | 内射 0次 | 怀孕 False | 被动 Lv.3'
        z1_t2 = sc.build_zone1_scene(ROOT, state_t2, ['徐念薇'], (), '', mode='dual_stream_v2', frozen_flags=z1_flags1)
        self.assertEqual(z1_t1, z1_t2, 'Zone 1 MUST remain 100% byte-identical for KV cache!')

        sdelta = {}
        delta_t2 = json.loads(sc.build_user_delta(
            ROOT, state_t2, {'text': '', 'index': []}, [], [], '我走到她身旁', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 2, 'last_closed': 1, 'phase': 'ready'},
            '', include_full_anchor=False, mode='dual_stream_v2',
            zone1_flags=z1_flags1, injected_guides=[], session_delta_out=sdelta,
        ))
        self.assertIn('persona_stage_updates', delta_t2)
        self.assertIn('徐念薇', delta_t2['persona_stage_updates']['characters'])
        self.assertIn('[stage3]', delta_t2['persona_stage_updates']['characters']['徐念薇'])
        self.assertIn('stage:徐念薇:stage3', sdelta['newly_injected_guides'])

        # Turn 3 with guide already injected does NOT repeat patch
        delta_t3 = json.loads(sc.build_user_delta(
            ROOT, state_t2, {'text': '', 'index': []}, [], [], '继续聊', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 3, 'last_closed': 2, 'phase': 'ready'},
            '', include_full_anchor=False, mode='dual_stream_v2',
            zone1_flags=z1_flags1, injected_guides=sdelta['newly_injected_guides'],
        ))
        self.assertNotIn('persona_stage_updates', delta_t3)

        # Offstage stage3 heroine uses real stage3 spine, not stage1
        delta_off = json.loads(sc.build_user_delta(
            ROOT, {**state_t2, 'cast': ['沈知韫']}, {'text': '', 'index': []}, [], [], '看看念薇', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 3, 'last_closed': 2, 'phase': 'ready'},
            '', include_full_anchor=True, mode='dual_stream_v2',
            references=[{'name': '徐念薇'}],
        ))
        off_body = delta_off['referenced_offstage']['characters'][0]['body']
        self.assertIn('偏执占有', off_body)

    def test_p1_4_intimate_vigilance_and_gate5_parity(self):
        for kw in ('搂腰', '抱住', '依偎', '腰侧', '胸口', '体温', '掌心', '反锁房门', '拉进怀里', '裙摆', '喘息'):
            self.assertIsNotNone(sc._INTIMATE_TURN_RE.search(kw), f'_INTIMATE_TURN_RE missed: {kw}')
        for vkw in ('我哥来电', '管家经过', '别穿帮', '门外脚步声'):
            self.assertTrue(sc._mentions_vigilance(vkw), f'_mentions_vigilance missed: {vkw}')

        # Gate 5 crowded public room suppresses coy-yield acting cue
        crowded_st = _make_state(
            cast=['苏婉青', '沈知韫'],
            panels=[
                '[系统宿主] 积分 180 | 经验值 60 | 体力 85 | 魅力 75 | 商业嗅觉 35',
                '[沈知韫] 好感 60 | 堕落 5 | 欲望 10 | 羞耻 90 | 体力 90 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.0',
                '[苏婉青] 好感 78 | 堕落 10 | 欲望 50 | 羞耻 70 | 体力 90 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.1',
            ],
            intimate={**ss.default_intimate(), 'privacy': 'open_public'},
        )
        brief_crowd = sc.compile_state_qualitative_brief(crowded_st, '')
        self.assertIn('公开顾忌', brief_crowd)
        self.assertNotIn('顺水留人', brief_crowd)

    def test_p2_1_memory_callback_penetration_and_anchor_scope(self):
        ms = ss.default_memory_store()
        ms['anchors'] = [
            {'id': 'A-01', 'kind': 'promise', 'day': 1, 'importance': 4, 'text': '苏婉青悄悄答应周五晚把主宅书房备用钥匙留给徐志北', 'entities': ['徐志北', '苏婉青'], 'known_by': ['徐志北', '苏婉青']},
            {'id': 'A-02', 'kind': 'secret', 'day': 1, 'importance': 3, 'text': '徐志北暗中记下暗红真丝丝巾内侧绣着的财务室缩写', 'entities': ['徐志北'], 'known_by': ['徐志北']},
        ]
        mv1 = ss.retrieve_memory_view(ms, query='茶室聊天', cast=['沈知韫'], present_actors=['沈知韫'], location='徐家主宅', max_chars=3600, incremental=False)
        self.assertIn('A-01', mv1['selected_ids'])
        # Normal chatter stays deduplicated
        mv2_chatter = ss.retrieve_memory_view(
            ms, query='今天天气不错', cast=['沈知韫'], present_actors=['沈知韫'], location='徐家主宅',
            max_chars=1400, incremental=True, exclude_fingerprints=mv1['selected_fingerprints'],
        )
        self.assertNotIn('A-01', mv2_chatter['selected_ids'])
        # Explicit strong lexical callback penetrates exclude_fingerprints!
        mv2_callback = ss.retrieve_memory_view(
            ms, query='周五晚主宅书房备用钥匙的事怎么安排？', cast=['沈知韫'], present_actors=['沈知韫'], location='徐家主宅',
            max_chars=1400, incremental=True, exclude_fingerprints=mv1['selected_fingerprints'],
        )
        self.assertIn('A-01', mv2_callback['selected_ids'])

        # Stage 2 anchor formatting preserves |私密 and |知情:苏婉青
        formatted = sc._format_anchors_compact_lossless(mv1['active_anchors_index'])
        self.assertTrue(any('|私密|' in x and 'A-02' in x for x in formatted))
        self.assertTrue(any('|知情:苏婉青|' in x and 'A-01' in x for x in formatted))

        # Archive recall regex catches 记不记得 / 昨晚 / 昨天
        for rkw in ('记不记得', '昨晚', '昨天', '前阵子', '那件事'):
            self.assertIsNotNone(sc._ARCHIVE_RECALL_RE.search(rkw))

    def test_p2_2_keepsake_offstage_mention_and_stage2_shop_existing(self):
        st_ks = _make_state(
            cast=['沈知韫'],
            intimate={
                **ss.default_intimate(),
                'keepsakes': [
                    {'id': 'KS-01', 'owner': '沈知韫', 'name': '真丝手帕', 'kind': 'accessory', 'method': 'gifted', 'condition': 'fresh_warm', 'owner_aware': True},
                    {'id': 'KS-02', 'owner': '苏婉青', 'name': '黑色蕾丝内裤', 'kind': 'panties', 'method': 'stolen', 'condition': 'fresh_warm', 'owner_aware': False},
                ],
            },
        )
        brief_plain = sc.compile_state_qualitative_brief(st_ks, '', text='和沈知韫喝茶')
        self.assertIn('KS-01', brief_plain)
        self.assertNotIn('KS-02', brief_plain)

        brief_mention = sc.compile_state_qualitative_brief(st_ks, '', text='我暗自摸了摸口袋里那条黑色蕾丝内裤')
        self.assertIn('KS-01', brief_mention)
        self.assertIn('KS-02', brief_mention)

        # Stage 2 includes shop_existing_names on 【商城定制】
        spec_shop = sc.build_settlement_spec(
            ROOT, _make_state(), {}, '【商城定制：助兴香薰】', None, None, None,
            {'kind': 'action', 'cost': 1}, {'memory_round': 3, 'last_closed': 2, 'phase': 'ready'},
            '', {'kind': 'action', 'conditions_required': True, 'intimate_mode': False, 'category_policy': {'mode': 'custom'}},
            {}, {'requested': None},
        )
        self.assertTrue(spec_shop['user_context'].get('shop_custom_requested'))
        self.assertTrue(len(spec_shop['user_context'].get('shop_existing_names') or []) > 0)

    def test_p2_3_stage1_boundary_and_vigor_latent_cues(self):
        st_low = _make_state(
            cast=['徐念薇'],
            panels=[
                '[系统宿主] 积分 0 | 经验值 0 | 体力 85 | 魅力 70 | 商业嗅觉 0',
                '[徐念薇] 好感 30 | 堕落 0 | 欲望 0 | 羞耻 74 | 体力 90 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.0',
            ],
            intimate={**ss.default_intimate(), 'scene_active': True, 'host_phys': {'desire': 35, 'vigor': 18, 'edging_streak': 0, 'fetishes': []}},
            physiology={'徐念薇': {'pregnancy_stage': 'latent'}},
        )
        pflags = sc.compute_zone1_persona_flags(st_low, '')
        self.assertEqual(pflags['char_stage']['徐念薇'], 'stage1')

        brief = sc.compile_state_qualitative_brief(st_low, '')
        self.assertIn('逼近断崖', brief)
        self.assertIn('2日观察期', brief)


if __name__ == '__main__':
    unittest.main()

"""End-to-end and unit tests for Main Model item visibility, frontend-backend item ops,
Stage 2 free-text item inference, and custom shop anti-modifier guardrails."""
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
import story_compiler as sc
import story_progression as sp
import story_service as ss
from test_dual_stage_runtime import _make_workspace, _fg_script, _settlement_payload


def _audit_for(root: Path, delivery: dict, chat_id='chat-item-1', card_id='card-item-1', stamp=200):
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
            'duration_ms': 310,
        },
    }


class ItemVisibilityAndOpsTests(unittest.TestCase):
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
        self.memory_text = (self.root / rr.FILES[0]).read_text(encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def _set_host_attr(self, attr: str, val: int):
        engine = rr._engine(self.root, self.root)
        path = self.root / rr.FILES[0]
        content = path.read_text(encoding='utf-8')
        updated = engine._simulate_panel(content, {'系统宿主': {attr: val}})
        path.write_text(updated, encoding='utf-8')

    def _set_host_points(self, pts: int):
        self._set_host_attr('积分', pts)

    def _redeem_shop(self, item_id: str):
        live = self.client.get('/api/story/live').get_json()
        self._stamp += 1
        r = self.client.post('/api/story/shop/redeem', headers=self.cli_headers, json={
            'request_id': f'redeem-{self._stamp}',
            'base_revision': live['revision'],
            'save_epoch': live['save_epoch'],
            'item_id': item_id,
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def _call_delta(self, state, text='聊聊近况', *, include_full_anchor=True, prev_state_hashes=None):
        session_out = {}
        raw = sc.build_user_delta(
            self.root,
            state,
            {'text': '', 'current': None, 'index': [], 'transfers': {}, 'limits': {}},
            [],
            [],
            text,
            {'segment_id': '', 'option_id': 'CUSTOM'},
            None,
            {'raw': text, 'brackets': []},
            {'kind': 'action', 'cost': 5},
            {'clock': {'day': 1, 'time': '09:10'}, 'memory_round': 1, 'phase': 'active'},
            self.memory_text,
            include_full_anchor=include_full_anchor,
            mode='dual_stream_v2',
            session_delta_out=session_out,
            prev_state_hashes=prev_state_hashes,
        )
        return json.loads(raw), session_out.get('state_hashes', {})

    def _play_all(self):
        snap = self.service.interaction_snapshot()
        p = snap['playback']
        if not p['segment_id'] or p['completed']:
            return snap
        for step in range(p['revealed'] + 1, p['total'] + 1):
            snap = self.service.playback_progress({
                'save_epoch': snap['save_epoch'],
                'segment_id': p['segment_id'],
                'revealed': step,
                'completed': False,
            })
        return self.service.playback_progress({
            'save_epoch': snap['save_epoch'],
            'segment_id': p['segment_id'],
            'revealed': p['total'],
            'completed': True,
        })

    def _run_dual_turn(self, *, option_id='BEGIN', action='继续当前剧情', operation=None,
                       fg_text=None, settlement_override=None, is_fresh=True,
                       synced_z0='', synced_z1='', last_seq=0):
        live = self.client.get('/api/story/live').get_json()
        seg_id = '' if option_id == 'BEGIN' else live['playback']['segment_id']
        self._stamp += 30
        req_id = f'item-req-{self._stamp}'
        payload = {
            'request_id': req_id,
            'base_revision': live['revision'],
            'save_epoch': live['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': action,
            'selection': {'segment_id': seg_id, 'option_id': option_id},
        }
        if operation is not None:
            payload['operation'] = operation
        cr = self.client.post('/api/story/tasks', headers=self.cli_headers, json=payload)
        self.assertEqual(cr.status_code, 200, cr.get_json())
        claimed = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                                   json={'model': self.model}).get_json()['task']
        mat_resp = self.client.post(f"/api/story/worker/{claimed['request_id']}/material",
                                    headers=self.wrk_headers, json={
                                        'lease': claimed['lease'],
                                        'chat_id': 'chat-item-1',
                                        'participant_id': 'card-item-1',
                                        'delivery_version': 2,
                                        'protocol_mode': 'dual_stream_v2',
                                        'synced_zone0_sha256': synced_z0,
                                        'synced_zone1_sha256': synced_z1,
                                        'last_committed_sequence': last_seq,
                                        'is_fresh_session': is_fresh,
                                    })
        self.assertEqual(mat_resp.status_code, 200, mat_resp.get_json())
        mat = mat_resp.get_json()
        fg = fg_text or _fg_script(speaker='沈知韫')
        cat = 'SYSTEM' if option_id == 'BEGIN' else (option_id if option_id in ('A', 'B', 'C') else 'A')
        settle = _settlement_payload(
            category=cat,
            conditions=None if cat == 'SYSTEM' else {
                'intensity': cat,
                'effective_progress': True,
                'scene': live['world']['location'],
                'npc': '沈知韫',
                'action_changed': True,
                'stress_signals': 0,
                'breakout_triggered': [],
            },
            clock_time='09:10' if option_id == 'BEGIN' else '09:25',
        )
        if settlement_override:
            for k, v in settlement_override.items():
                if k == 'resolution' and isinstance(v, dict):
                    settle['resolution'].update(v)
                else:
                    settle[k] = v
        res = self.client.post(f"/api/story/worker/{claimed['request_id']}/result",
                               headers=self.wrk_headers, json={
                                   'lease': claimed['lease'],
                                   'text': json.dumps({
                                       'dual_stage_version': 1,
                                       'foreground_text': fg,
                                       'settlement': settle,
                                   }, ensure_ascii=False),
                                   'conversation_audit': _audit_for(self.root, mat, stamp=self._stamp),
                                   'timing': {
                                       'generation_ms': 900,
                                       'settlement_ms': 350,
                                       'preflight_ms': 0,
                                       'generation_passes': 1,
                                       'settlement_passes': 1,
                                       'settlement_model_id': 'gemini-flash',
                                   },
                               }).get_json()
        return mat, res

    # 1. delivered_gifts_to_cast via real ir.view() + empty-transition diff emission
    def test_delivered_gifts_visible_via_real_view_and_clears_when_empty(self):
        self._set_host_points(80)
        catalog = sp.load_shop_catalog(self.root, optional=False)
        gift_item = next(it for it in catalog['items'] if it.get('usage_mode') == 'gift')
        gift_inv_id = self._redeem_shop(gift_item['id'])['receipt']['item_id']

        self._run_dual_turn(option_id='BEGIN')
        self._play_all()
        op_gift = {'code': 'transfer_item', 'item_id': gift_inv_id, 'recipient': '沈知韫'}
        _, res2 = self._run_dual_turn(
            option_id='CUSTOM',
            action=f"把{gift_item['name']}送给沈知韫",
            operation=op_gift,
            fg_text=(
                '[N] 客厅里的空调风微微发凉。\n'
                f"[A:徐志北] 他拆开礼盒，把{gift_item['name']}递到沈知韫面前。\n"
                '[D:沈知韫] 怎么突然买这个……倒是很合心意，谢谢你，志北。\n'
                '---DECISION---\n'
                'PROMPT: 沈知韫收下礼物，你打算怎么接话？\n'
                'A: 笑着说顺路看到觉得很衬她。\n'
                'B: 顺势坐到她身边聊起近况。\n'
                'C: 问她今晚想吃什么。\n'
            ),
            settlement_override={'operation': op_gift},
        )
        self.assertEqual(res2['task']['status'], 'committed', res2)
        self._play_all()

        # Real ir.view() emits 'target' -> build_user_delta() must map it to delivered_gifts_to_cast with recipient + desc
        view = ir.view(self.store)
        self.assertTrue(view.get('delivered_items'), 'real ir.view() should contain delivered_items')
        self.assertEqual(view['delivered_items'][0].get('target'), '沈知韫')

        delta1, hashes1 = self._call_delta(view, '聊聊近况', include_full_anchor=True)
        gifts = delta1.get('delivered_gifts_to_cast') or []
        self.assertEqual(len(gifts), 1, delta1)
        self.assertEqual(gifts[0]['name'], gift_item['name'])
        self.assertEqual(gifts[0]['recipient'], '沈知韫')
        self.assertTrue(gifts[0].get('desc'), 'delivered gift must carry short desc')

        # Transition delivered_items from non-empty -> empty must explicitly emit []
        empty_view = copy.deepcopy(view)
        empty_view['delivered_items'] = []
        delta2, _ = self._call_delta(
            empty_view, '聊聊近况', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        self.assertIn('delivered_gifts_to_cast', delta2)
        self.assertEqual(delta2['delivered_gifts_to_cast'], [])

    # 2. use_item with target='室内氛围' succeeds end-to-end and attaches buff to present heroine
    def test_use_item_indoor_atmosphere_target_e2e(self):
        self._set_host_points(80)
        catalog = sp.load_shop_catalog(self.root, optional=False)
        aroma_item = next(
            it for it in catalog['items']
            if it.get('usage_mode') == 'consumable_target'
            and ('香薰' in it.get('name', '') or '氛围' in it.get('system_effect', ''))
        )
        aroma_inv_id = self._redeem_shop(aroma_item['id'])['receipt']['item_id']

        self._run_dual_turn(option_id='BEGIN')
        self._play_all()

        op = {'code': 'use_item', 'item_id': aroma_inv_id, 'target': '室内氛围'}
        mat, res = self._run_dual_turn(
            option_id='CUSTOM',
            action=f"点起{aroma_item['name']}，让室内氛围松弛下来",
            operation=op,
            fg_text=(
                f"[N] 客厅一角点起了{aroma_item['name']}，淡雅的暖香很快漫开。\n"
                '[A:沈知韫] 沈知韫嗅到空气里柔和的香气，紧绷的肩线不自觉放松了些。\n'
                '[D:沈知韫] 这香闻着挺安神，你什么时候准备的？\n'
                '---DECISION---\n'
                'PROMPT: 香气在屋内弥漫，你打算如何回应？\n'
                'A: 说是顺路挑来助眠安神的。\n'
                'B: 坐到她身旁陪她喝口温茶。\n'
                'C: 问她今天在集团是不是累着了。\n'
            ),
            settlement_override={'operation': op},
        )
        self.assertEqual(res['task']['status'], 'committed', res)
        # Check op instruction humanized (no raw buff: syntax)
        user_msg_text = mat['delivery'].get('user_message') or ''
        self.assertNotIn('buff:', user_msg_text)
        # Verify buff attached to present heroine 沈知韫 and quantity deducted
        mem_after = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        buffs = sc._parse_buffs_inline(mem_after).get('沈知韫') or []
        self.assertTrue(buffs, f'Expected aroma buff attached to 沈知韫, got {sc._parse_buffs_inline(mem_after)}')
        view_after = ir.view(self.store)
        held = next((it for it in view_after.get('items', []) if it.get('id') == aroma_inv_id), None)
        if aroma_item.get('pack_qty', 1) > 1:
            self.assertIsNotNone(held)
            self.assertEqual(int(held['quantity']), int(aroma_item['pack_qty']) - 1)

    # 3. _describe_operation_context handles use_recovery_item explicitly
    def test_use_recovery_item_operation_detail(self):
        state = {'location': '徐家主宅', 'cast': ['沈知韫']}
        bundle_state = {
            'items': {
                'active': [{
                    'id': 'SHOP-009',
                    'name': '提神黑咖精华',
                    'quantity': 3,
                    'usage_mode': 'consumable_host',
                    'desc': '高浓缩便携黑咖安瓶，入口微苦回甘，迅速驱散倦意。',
                    'system_effect': 'host_stamina:35',
                }],
                'deployed': [],
            },
        }
        detail = ir._describe_operation_context(
            {'code': 'use_recovery_item', 'item_id': 'SHOP-009'},
            state,
            bundle_state,
            '',
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail['kind'], 'use_recovery_item')
        self.assertEqual(detail['item']['name'], '提神黑咖精华')
        self.assertIn('高浓缩便携黑咖安瓶', detail['item']['desc'])
        self.assertEqual(detail['quantity_after'], 2)
        self.assertIn('严禁推进游戏时间', detail['instruction'])
        self.assertNotIn('host_stamina:', json.dumps(detail, ensure_ascii=False))

    # 4. Unified held_items on Turn 1 & Turn 2+, no raw fields / points leakage, full 150-char DYN desc
    def test_unified_held_items_human_readable_and_no_dyn_truncation(self):
        long_dyn_desc = (
            '表面是一枚复古黄铜书签，背面刻有极细的微缩花纹，夹在财务文件夹中毫不起眼；'
            '实则内嵌温敏变色涂层与隐藏磁吸夹片，可用于在对方翻阅文件时确认是否被人暗中动过手脚，'
            '同时能作为自然搭话的精致小物件送出而不引人起疑。'
        )
        self.assertGreater(len(long_dyn_desc), 100)
        self.assertLessEqual(len(long_dyn_desc), 160)
        state = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'presence': {'沈知韫': {'location': '徐家主宅'}, '徐志北': {'location': '徐家主宅'}},
            'panels': [
                '[系统宿主] 体力 100 | 积分 50 | 经验值 0 | 魅力 50 | 商业嗅觉 50',
                '[沈知韫] 好感 50 | 羞耻 100 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
            ],
            'items': [
                {
                    'id': 'SHOP-013',
                    'name': '冰玉冷敷按摩棒',
                    'type': '感官工具',
                    'quantity': 1,
                    'usage_mode': 'reusable_tool',
                    'giftable': False,
                    'desc': '冰凉润泽的玉石冷敷按摩器具，适合帮人舒缓肩颈与眼周疲惫。',
                    'system_effect': 'buff:冰火刺激:2:冷热交替感官放大（轻中度越界好感惩罚减半）',
                    'source': '系统商城兑换(18积分)',
                    'fields': {'id': 'SHOP-013', '来源': '系统商城兑换(18积分)', '描述': '冰凉润泽的玉石冷敷按摩器具，适合帮人舒缓肩颈与眼周疲惫。', 'extra': 'a' * 180},
                },
                {
                    'id': 'SHOP-006',
                    'name': '薰衣草温感按摩精油',
                    'type': '消耗品',
                    'quantity': 2,
                    'usage_mode': 'consumable_target',
                    'giftable': False,
                    'desc': '涂抹后掌心发热并散发清淡薰衣草香，适合肩颈或足部放松按摩。',
                    'system_effect': 'buff:温热精油:2:肌肤温热顺滑，防备感缓和（轻中度越界好感惩罚减半）',
                    'source': '系统商城兑换(12积分)',
                    'fields': {'id': 'SHOP-006', '来源': '系统商城兑换(12积分)', 'extra': 'b' * 180},
                },
                {
                    'id': 'DYN-001',
                    'name': '复古黄铜温敏书签',
                    'type': '定制道具',
                    'quantity': 1,
                    'usage_mode': 'reusable_tool',
                    'giftable': True,
                    'desc': long_dyn_desc,
                    'system_effect': '',
                    'source': '系统商城兑换(15积分)',
                    'fields': {'id': 'DYN-001', '来源': '系统商城兑换(15积分)', 'extra': 'c' * 180},
                },
            ],
            'deployed_items': [],
            'delivered_items': [],
        }

        delta1, _ = self._call_delta(state, '聊聊近况', include_full_anchor=True)
        delta2, _ = self._call_delta(state, '聊聊近况', include_full_anchor=False, prev_state_hashes={})

        for label, d in (('turn1', delta1), ('turn2', delta2)):
            self.assertIn('held_items', d, f'{label} must emit unified held_items')
            self.assertNotIn('items', d, f'{label} must not emit legacy raw items')
            dumped = json.dumps(d['held_items'], ensure_ascii=False)
            self.assertNotIn('fields', dumped)
            self.assertNotIn('系统商城兑换', dumped)
            self.assertNotIn('积分', dumped)
            self.assertNotIn('buff:', dumped)
            self.assertNotIn('好感惩罚减半', dumped)

            by_id = {x['id']: x for x in d['held_items']}
            self.assertEqual(by_id['DYN-001']['desc'], long_dyn_desc)
            self.assertIn('可反复使用不消耗', by_id['SHOP-013']['use_way'])
            self.assertIn('消耗品', by_id['SHOP-006']['use_way'])
            self.assertIn('持续2轮「温热精油」', by_id['SHOP-006'].get('effect', ''))

        raw_size = len(json.dumps(state['items'], ensure_ascii=False, separators=(',', ':')))
        new_size = len(json.dumps(delta1['held_items'], ensure_ascii=False, separators=(',', ':')))
        self.assertLess(new_size, raw_size, 'Unified held_items should stay leaner than raw items+fields')

    # 5. Deployed items include desc, humanized capability, qualitative risk, and empty transition
    def test_deployed_items_include_desc_capability_risk_and_empty_transition(self):
        state = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'presence': {'沈知韫': {'location': '徐家主宅'}, '徐志北': {'location': '徐家主宅'}},
            'panels': [
                '[系统宿主] 体力 100 | 积分 50 | 经验值 0 | 魅力 50 | 商业嗅觉 50',
                '[沈知韫] 好感 50 | 羞耻 100 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
            ],
            'items': [],
            'deployed_items': [
                {
                    'id': 'SHOP-015',
                    'name': '伪装插座针孔镜头',
                    'location': '徐家主宅',
                    'spot': '书桌下方墙插',
                    'desc': '外观与普通五孔插座无异，通电即可广角回传室内画面。',
                    'system_effect': 'deploy_device:camera',
                    'detected_risk': 22,
                },
                {
                    'id': 'SHOP-016',
                    'name': '纽扣微距拾音器',
                    'location': '市中心顶层公寓',
                    'spot': '沙发缝隙',
                    'desc': '米粒大小低功耗声控拾音模块，人声触发自动回传。',
                    'system_effect': 'deploy_device:audio',
                    'detected_risk': 8,
                },
            ],
            'delivered_items': [],
        }

        delta1, hashes1 = self._call_delta(state, '先坐下喝茶', include_full_anchor=True)
        here = delta1.get('deployed_items_here') or []
        remote = delta1.get('deployed_items_remote') or []
        self.assertEqual(len(here), 1)
        self.assertEqual(len(remote), 1)
        self.assertEqual(here[0]['capability'], '隐蔽广角实时画面回传')
        self.assertIn('五孔插座', here[0]['desc'])
        self.assertEqual(here[0].get('risk'), '已有一定暴露隐患')
        self.assertEqual(remote[0]['capability'], '隐蔽声控实时拾音监听')
        self.assertIn('声控拾音', remote[0]['desc'])
        self.assertNotIn('risk', remote[0])
        self.assertNotIn('deploy_device:', json.dumps(delta1, ensure_ascii=False))

        # Remove local deployed item -> Turn 2 diff must explicitly emit []
        state2 = copy.deepcopy(state)
        state2['deployed_items'] = [state['deployed_items'][1]]
        delta2, _ = self._call_delta(
            state2, '先坐下喝茶', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        self.assertIn('deployed_items_here', delta2)
        self.assertEqual(delta2['deployed_items_here'], [])

    # 6. Incremental mention recall on-demand + ambiguity guard
    def test_incremental_mention_recall_on_demand(self):
        state = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'presence': {'沈知韫': {'location': '徐家主宅'}, '徐志北': {'location': '徐家主宅'}},
            'panels': [
                '[系统宿主] 体力 100 | 积分 50 | 经验值 0 | 魅力 50 | 商业嗅觉 50',
                '[沈知韫] 好感 50 | 羞耻 100 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
            ],
            'items': [
                {
                    'id': 'SHOP-006',
                    'name': '薰衣草温感按摩精油',
                    'quantity': 2,
                    'usage_mode': 'consumable_target',
                    'desc': '涂抹后温热舒缓肩颈。',
                    'system_effect': 'buff:温热精油:2:肌肤温热顺滑',
                },
                {
                    'id': 'DYN-002',
                    'name': '玫瑰护手精油',
                    'quantity': 1,
                    'usage_mode': 'consumable_target',
                    'desc': '淡雅玫瑰花香护手润肤。',
                    'system_effect': '',
                },
                {
                    'id': 'SHOP-013',
                    'name': '冰玉冷敷棒',
                    'quantity': 1,
                    'usage_mode': 'reusable_tool',
                    'desc': '玉石材质，冰凉贴肤，适合冷敷眼周与颈侧。',
                    'system_effect': 'buff:冰火刺激:2:冷热交替感官放大',
                },
            ],
            'deployed_items': [
                {
                    'id': 'SHOP-015',
                    'name': '伪装插座针孔镜头',
                    'location': '徐家主宅',
                    'spot': '墙角插座',
                    'desc': '广角回传室内画面。',
                    'system_effect': 'deploy_device:camera',
                    'detected_risk': 18,
                },
            ],
            'delivered_items': [],
        }

        _, hashes1 = self._call_delta(state, '先坐下聊天', include_full_anchor=True)

        # (a) Unmentioned turn -> held_items & deployed_items_here omitted, no mentioned_items
        d_plain, _ = self._call_delta(
            state, '聊聊今晚想吃什么', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        self.assertIn('held_items', d_plain.get('unchanged_from_prev_turn', []))
        self.assertIn('deployed_items_here', d_plain.get('unchanged_from_prev_turn', []))
        self.assertNotIn('mentioned_items', d_plain)

        # (b) Mentioning unique owned item -> recalled in mentioned_items with full desc
        d_held, _ = self._call_delta(
            state, '我拿出冷敷棒帮她冰敷额角', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        recalled_ids = [x['id'] for x in d_held.get('mentioned_items', [])]
        self.assertEqual(recalled_ids, ['SHOP-013'])
        self.assertEqual(d_held['mentioned_items'][0]['status'], '背包持有')
        self.assertIn('冷敷眼周', d_held['mentioned_items'][0]['desc'])

        # (c) Mentioning deployed item -> recalled with deployed status & capability
        d_dep, _ = self._call_delta(
            state, '顺便扫一眼墙角的针孔镜头有没有歪', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        self.assertEqual([x['id'] for x in d_dep.get('mentioned_items', [])], ['SHOP-015'])
        self.assertEqual(d_dep['mentioned_items'][0]['status'], '已部署(当前现场)')
        self.assertEqual(d_dep['mentioned_items'][0]['capability'], '隐蔽广角实时画面回传')

        # (d) Ambiguous noun ("精油" matches both SHOP-006 and DYN-002) -> surface both candidates for disambiguation instead of silent amnesia
        d_ambig, _ = self._call_delta(
            state, '我想用精油', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        self.assertEqual({x['id'] for x in d_ambig.get('mentioned_items', [])}, {'SHOP-006', 'DYN-002'})

        # (e) Disambiguated phrase ("按摩精油") -> locks uniquely onto SHOP-006
        d_disambig, _ = self._call_delta(
            state, '我拿出按摩精油帮她揉揉肩', include_full_anchor=False, prev_state_hashes=hashes1,
        )
        self.assertEqual([x['id'] for x in d_disambig.get('mentioned_items', [])], ['SHOP-006'])

    # 7. Stage 2 free-text item inference (CUSTOM + normal option B) & hallucination guard
    def test_stage2_free_text_item_op_inference_and_selection_compat(self):
        self._set_host_points(120)
        self._set_host_attr('商业嗅觉', 30)
        catalog = sp.load_shop_catalog(self.root, optional=False)
        oil_cat = next(
            it for it in catalog['items']
            if it.get('usage_mode') == 'consumable_target' and '精油' in it.get('name', '')
        )
        tool_cat = next(
            it for it in catalog['items']
            if it.get('usage_mode') == 'reusable_tool'
        )
        oil_inv_id = self._redeem_shop(oil_cat['id'])['receipt']['item_id']
        tool_inv_id = self._redeem_shop(tool_cat['id'])['receipt']['item_id']

        view0 = ir.view(self.store)
        oil = next(it for it in view0['items'] if it['id'] == oil_inv_id)
        tool = next(it for it in view0['items'] if it['id'] == tool_inv_id)
        oil_qty_before = int(oil['quantity'])

        # Turn 1 BEGIN — plant option B mentioning the owned reusable tool name
        self._run_dual_turn(
            option_id='BEGIN',
            fg_text=(
                '[N] 午后阳光落在客厅地毯上，沈知韫正揉着眉心。\n'
                '[A:沈知韫] 沈知韫合上文件，略带倦意地靠在沙发背上。\n'
                '[D:沈知韫] 志北，坐吧，刚才那份报表看得眼睛发酸。\n'
                '---DECISION---\n'
                'PROMPT: 见她有些疲惫，你打算怎么做？\n'
                'A: 顺手替她倒杯温茶聊聊天。\n'
                f"B: 拿出{tool['name']}帮沈知韫舒缓疲惫。\n"
                'C: 问她今天集团的会议顺不顺利。\n'
            ),
        )
        self._play_all()

        # (a) CUSTOM free text with NO UI operation -> Stage 2 receives free_text_item_hint & emits use_item
        mat_custom, res_custom = self._run_dual_turn(
            option_id='CUSTOM',
            action='我拿出精油帮沈知韫按按脚放松一下',
            operation=None,
            fg_text=(
                '[N] 温热的香气在客厅里缓缓散开。\n'
                f"[A:徐志北] 他取来{oil['name']}在掌心搓热，蹲在沙发边替沈知韫按揉微凉的脚踝。\n"
                '[D:沈知韫] 嗯……怎么突然弄这个，温温热热的倒是很舒服。\n'
                '---DECISION---\n'
                'PROMPT: 沈知韫呼吸放慢了些，你打算如何继续？\n'
                'A: 顺着小腿力道放轻再按一会儿。\n'
                f"B: 拿出{tool['name']}帮沈知韫舒缓酸胀。\n"
                'C: 收手去洗个手，陪她说说话。\n'
            ),
            settlement_override={
                'operation': {'code': 'use_item', 'item_id': oil_inv_id, 'target': '沈知韫'},
            },
        )
        self.assertEqual(res_custom['task']['status'], 'committed', res_custom)
        s2_ctx = mat_custom['settlement_spec']['user_context']
        hint = s2_ctx.get('free_text_item_hint') or {}
        self.assertIn(oil_inv_id, [x['id'] for x in hint.get('candidates', [])])

        view_after_custom = ir.view(self.store)
        oil_after = next((it for it in view_after_custom['items'] if it['id'] == oil_inv_id), None)
        if oil_qty_before > 1:
            self.assertIsNotNone(oil_after)
            self.assertEqual(int(oil_after['quantity']), oil_qty_before - 1)
        else:
            self.assertIsNone(oil_after)
        mem_after_custom = (self.root / rr.FILES[0]).read_text(encoding='utf-8')
        buff_entries = sc._parse_buffs_inline(mem_after_custom).get('沈知韫') or []
        self.assertTrue(buff_entries, f'Expected oil buff attached to 沈知韫, got {sc._parse_buffs_inline(mem_after_custom)}')
        self._play_all()

        # (b) Normal option B (non-CUSTOM, NO UI operation) mentioning owned tool -> selection() allows Stage 2 op!
        mat_optb, res_optb = self._run_dual_turn(
            option_id='B',
            action=f"拿出{tool['name']}帮沈知韫舒缓酸胀。",
            operation=None,
            fg_text=(
                '[N] 细腻的触感贴上她的肩颈。\n'
                f"[A:徐志北] 他拿起{tool['name']}替沈知韫细细放松紧绷的肩线。\n"
                '[D:沈知韫] 嗯，这样舒服多了。\n'
                '---DECISION---\n'
                'PROMPT: 沈知韫微微睁开眼看着你，接下来？\n'
                'A: 把工具收好陪她喝茶。\n'
                'B: 顺势问她晚饭想吃什么。\n'
                'C: 聊起公司近期的安排。\n'
            ),
            settlement_override={
                'operation': {'code': 'use_item', 'item_id': tool_inv_id, 'target': '沈知韫'},
            },
        )
        self.assertEqual(res_optb['task']['status'], 'committed', res_optb)
        self.assertIn(
            tool_inv_id,
            [x['id'] for x in (mat_optb['settlement_spec']['user_context'].get('free_text_item_hint') or {}).get('candidates', [])],
        )

        # (c) Hallucination guard (explicit=False): unmentioned use_item / retrieve_item / inspect_deployed rejected
        # Redeem and deploy a real device so retrieve_item / inspect_deployed reach text-evidence check
        self._play_all()
        dev_cat = next(it for it in catalog['items'] if it.get('usage_mode') == 'deployable_device')
        dev_inv_id = self._redeem_shop(dev_cat['id'])['receipt']['item_id']
        op_dep = {'code': 'deploy_item', 'item_id': dev_inv_id, 'spot': '书桌下', 'hidden': True}
        _, res_dep = self._run_dual_turn(
            option_id='CUSTOM',
            action=f"把{dev_cat['name']}悄悄装到书桌下",
            operation=op_dep,
            fg_text=(
                '[N] 书桌下方阴影刚好遮住接口。\n'
                f"[A:徐志北] 他借俯身捡笔的动作将{dev_cat['name']}嵌进书桌下的隐蔽插座。\n"
                '[D:沈知韫] 笔掉地上了？\n'
                '---DECISION---\n'
                'PROMPT: 装置已装好，接下来？\n'
                'A: 顺口应一声坐回沙发。\n'
                'B: 倒杯水递给她。\n'
                'C: 聊起明天安排。\n'
            ),
            settlement_override={'operation': op_dep},
        )
        self.assertEqual(res_dep['task']['status'], 'committed', res_dep)

        files_now = self.store._files()
        plain_text = '窗外阳光很好，我们只是喝了口白开水聊了聊天气。'
        with self.assertRaises(rr.RoundError):
            ir.operation(self.root, files_now,
                         {'code': 'use_item', 'item_id': tool_inv_id, 'target': '沈知韫'},
                         plain_text, explicit=False)
        with self.assertRaises(rr.RoundError):
            ir.operation(self.root, files_now,
                         {'code': 'retrieve_item', 'item_id': dev_inv_id},
                         plain_text, explicit=False)
        with self.assertRaises(rr.RoundError):
            ir.operation(self.root, files_now,
                         {'code': 'inspect_deployed', 'item_id': dev_inv_id},
                         plain_text, explicit=False)

    # 8. compile_state_qualitative_brief enriches keepsakes with method label and short desc
    def test_keepsake_qualitative_brief_includes_method_and_desc(self):
        state = {
            'location': '徐家主宅',
            'cast': ['沈知韫'],
            'panels': [
                '[系统宿主] 体力 100 | 积分 50 | 经验值 0 | 魅力 50 | 商业嗅觉 50',
                '[沈知韫] 好感 55 | 羞耻 95 | 体力 95 | 欲望 10 | 堕落 0 | 怀孕 False',
            ],
            'intimate': {
                'keepsakes': [
                    {'id': 'KS-1', 'owner': '沈知韫', 'name': '真丝手帕', 'method': 'stolen', 'condition': 'fresh_warm', 'desc': '沾着淡淡冷梅香的米白真丝方巾'},
                    {'id': 'KS-2', 'owner': '沈知韫', 'name': '珍珠发簪', 'method': 'taken_intimate', 'condition': 'stained_damp', 'desc': '温润圆珠银簪，昨夜遗落枕畔'},
                    {'id': 'KS-3', 'owner': '沈知韫', 'name': '袖扣礼盒', 'method': 'gifted', 'condition': 'faded', 'desc': '亲手挑选送出的深蓝珐琅袖扣'},
                ],
            },
        }
        brief = sc.compile_state_qualitative_brief(state)
        self.assertIn('真丝手帕[暗中偷藏/', brief)
        self.assertIn('冷梅香', brief)
        self.assertIn('珍珠发簪[亲密留存/', brief)
        self.assertIn('袖扣礼盒[亲手交出/', brief)

    # 9. SHOP-014 alignment + custom item anti-modifier guardrails
    def test_shop_014_alignment_and_custom_item_anti_modifier_guard(self):
        catalog = sp.load_shop_catalog(self.root, optional=False)
        shop_014 = next(it for it in catalog['items'] if it['id'] == 'SHOP-014')
        eff = shop_014.get('system_effect', '')
        self.assertIn('防备松动与越界缓和', eff)
        self.assertNotIn('羞耻防线松动', eff)
        # Ensure engine _SENSUAL_BUFF_RE still recognizes SHOP-014 buff name/effect
        parts = eff.split(':', 3)
        self.assertTrue(ic._SENSUAL_BUFF_RE.search(parts[1]) or ic._SENSUAL_BUFF_RE.search(parts[3]))

        # Direct stat-modifier custom items MUST be rejected
        forbidden_cases = [
            ('魅惑香囊', '佩戴后直接增加好感，让对方爱上你', ''),
            ('心动糖果', '吃下后好感+20，气氛立刻升温', ''),
            ('迷迭香滴露', '使用后降低羞耻，消除一切防备', ''),
            ('好感药水', '精致小瓶装饮品，喝下后让人亲近你', ''),
            ('气场胸针', '佩戴后魅力+5，举手投足更迷人', ''),
            ('黑金盲盒', '打开后获得积分+100用于商城消费', ''),
            ('失忆喷雾', '喷洒后清零警惕，让大哥彻底忘掉怀疑', ''),
            ('超级能量液', '一口回复精力，重新精神饱满', ''),
            ('暗影吊坠', '直接加堕落，催化目标彻底沉沦', ''),
        ]
        for name, desc, syseff in forbidden_cases:
            payload = json.dumps({
                'shopkeeper_reply': '测试上架',
                'items': [{
                    'name': name,
                    'category': 'daily',
                    'usage_mode': 'gift',
                    'desc': desc,
                    'system_effect': syseff,
                    'price': 20,
                    'grade': 'T1',
                }],
            }, ensure_ascii=False)
            with self.assertRaises(rr.RoundError, msg=f'Expected rejection for {name}: {desc}') as cm:
                sp.validate_dynamic_shop_items(payload, existing_names=[], next_seq=1, query=name)
            self.assertIn('非修改器', str(cm.exception))

        # Indirect / auxiliary creative items MUST be allowed
        allowed_cases = [
            ('桂花微醺果酒', 'sensual', 'consumable_target',
             '入口清甜微醺，有助于拉近距离制造独处契机，让对方防备松动与越界缓和。',
             'buff:微醺松弛:2:酒意微醺放松防备（轻中度越界好感惩罚减半）'),
            ('手写股市复盘备忘', 'daily', 'reusable_tool',
             '整理好的南城地皮与财报关键节点策略备忘，方便在饭桌上自然切入商业话题展示眼光。',
             ''),
            ('伪装书挡微距镜头', 'covert', 'deployable_device',
             '藏在胡桃木书挡内的隐蔽监控装置，摆在书房架上不易察觉，便于掌握室内动向。',
             'deploy_device:camera'),
        ]
        for idx, (name, cat, mode, desc, syseff) in enumerate(allowed_cases, start=1):
            payload = json.dumps({
                'shopkeeper_reply': '已为您调货',
                'items': [{
                    'name': name,
                    'category': cat,
                    'usage_mode': mode,
                    'desc': desc,
                    'system_effect': syseff,
                    'price': 36,
                    'grade': 'T2',
                }],
            }, ensure_ascii=False)
            res = sp.validate_dynamic_shop_items(payload, existing_names=[], next_seq=idx, query=name)
            self.assertEqual(len(res['items']), 1, f'Expected acceptance for {name}, got {res}')
            self.assertEqual(len(res['rejected_reasons']), 0)

    # 10. Zero KV prefix drift (Zone 0 deterministic) & Stage 2 < 12,000 char budget
    def test_zero_kv_prefix_drift_and_stage2_12k_budget(self):
        z0_a = sc.build_zone0_global(self.root, mode='dual_stream_v2')
        z0_b = sc.build_zone0_global(self.root, mode='dual_stream_v2')
        self.assertEqual(z0_a, z0_b)
        self.assertNotIn('free_text_item_hint', z0_a)

        view = ir.view(self.store)
        proj = {'text': '', 'current': None, 'index': [], 'transfers': {}, 'limits': {}}
        rt = {'clock': {'day': 1, 'time': '09:10'}, 'memory_round': 1, 'phase': 'active'}
        spec = sc.build_settlement_spec(
            self.root, view, proj, '聊聊今天的安排',
            {'segment_id': '', 'option_id': 'CUSTOM'}, None,
            {'raw': '聊聊今天的安排', 'brackets': []},
            {'kind': 'action', 'cost': 5}, rt, self.memory_text, {}, {}, None,
        )
        s2_sys = spec['system_prompt']
        self.assertLess(len(s2_sys), 12000, f'Stage 2 static system_prompt exceeded 12K budget: {len(s2_sys)}')
        # shop_custom_rule & free_text_item_hint must stay out of static system_prompt (dynamic user_context only)
        self.assertNotIn('道具不是修改器铁律', s2_sys)
        self.assertNotIn('shop_custom_rule', spec['user_context'])

        spec_custom = sc.build_settlement_spec(
            self.root, view, proj, '【商城定制】想买点好东西',
            {'segment_id': '', 'option_id': 'CUSTOM'}, None,
            {'raw': '【商城定制】想买点好东西', 'brackets': []},
            {'kind': 'action', 'cost': 5}, rt, self.memory_text, {}, {}, None,
        )
        self.assertIn('shop_custom_rule', spec_custom['user_context'])
        self.assertIn('道具非修改器', spec_custom['user_context']['shop_custom_rule'])


if __name__ == '__main__':
    unittest.main()

"""End-to-end tests for v2 material delivery, Long-Polling wait, streaming preview, and dual-stage settlement."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest

from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import round_runtime as rr
import story_service as ss

COPY_FILES = [
    'injection_core.py',
    'round_runtime.py',
    'save_store.py',
    'story_reading.py',
    'story_compiler.py',
    'relationship_query.py',
    'interaction_runtime.py',
    'story_progression.py',
    'story_service.py',
    'scene_chat.py',
    'data.json',
    '存档清理器.py',
]
COPY_DIRS = ['txt文件']


def _make_workspace(dst: Path):
    for name in COPY_FILES:
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dst / name)
    for dname in COPY_DIRS:
        shutil.copytree(ROOT / dname, dst / dname)
    # Remove any accidental runtime cache inside copied txt文件.
    cache_dir = dst / 'txt文件/.story-reading'
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    # Hermetically write clean blank P2 initial save templates (independent of developer's local 存档/).
    import 存档清理器 as cleaner
    for rel, text in cleaner._initial_templates().items():
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
    (dst / 'data.json').write_text(json.dumps({
        'round': 0,
        'sceneTitle': '徐家主宅',
        'storyNodes': [],
        'presence': {
            '沈知韫': {'location': '徐家主宅', 'reason': '常住'},
            '徐念薇': {'location': '大学', 'reason': '工作日在大学'},
            '苏婉青': {'location': '市中心顶层公寓', 'reason': '常住'},
            '徐志北': {'location': '徐家主宅', 'reason': '常住'},
        },
        'state_version': 0,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _fg_script(speaker='沈知韫', line='志北，先坐下喝口茶，有事慢慢说。'):
    return (
        '[N] 客厅里的茶香缓缓散开，窗外日光落在雕花桌沿。\n'
        f'[A:{speaker}] {speaker}将温热的白瓷杯轻轻推到你手边，神情柔和。\n'
        f'[D:{speaker}] {line}\n'
        '---DECISION---\n'
        'PROMPT: 茶刚沏好，你打算如何回应？\n'
        'A: 顺势接过茶杯道谢，聊聊今天在家的安排。\n'
        'B: 轻轻扶住她的手腕致意，问她昨晚休息得如何。\n'
        'C: 顺着话头提起公司最近的事务，试探她的态度。\n'
    )


def _settlement_payload(evidence_line='志北，先坐下喝口茶，有事慢慢说。', category='SYSTEM', conditions=None, clock_time='09:10'):
    return {
        'operation': None,
        'handoff': '',
        'checks': {
            'intent': '玩家启动首段剧情，承接现场氛围展开互动。',
            'knowledge': '仅使用当前在场人物与公开现场状态，未泄露私密档案或遗嘱。',
            'action': '仅在场角色倒茶招呼，未代写玩家台词或擅自移动。',
            'pace': '完成首轮微幕互动并给出三项可选方向，停在玩家回应处。',
        },
        'resolution': {
            'category': category,
            'basis': '系统启动免费进入当前现场。' if category == 'SYSTEM' else '日常言语互动，无肢体越界。',
            'clock': {'day': 1, 'time': clock_time, 'basis': '简短寒暄经过约十分钟。'},
            'events': [],
            'memory': {'fact': '', 'compact': '', 'transfers': {}},
            'conditions': conditions,
            'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
            'task': None,
            'items': [],
        },
        'quality_flags': [],
    }


class DualStageRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_workspace(self.root)
        # Ensure clean fresh save with known starting location/cast via 存档清理器.
        app = Flask(__name__)
        self.service = ss.register_story_routes(app, self.root)
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
        self.summary_model = {
            'key': '["SUMMARY","prov","gemini-flash"]',
            'function_type': 'SUMMARY',
            'provider_id': 'prov',
            'model_id': 'gemini-flash',
            'provider_name': 'Prov',
            'pricing_configured': True,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _audit(self, delivery, chat_id='chat-1', card_id='card-1', stamp=100):
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
            'workspace': str(self.root),
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
                'duration_ms': 420,
            },
        }

    def test_status_advertises_v2_and_bridge_control_dual_stage(self):
        st = self.client.get('/api/story/tasks').get_json()
        self.assertEqual(st['material_delivery_revision'], 1)
        self.assertEqual(st['material_delivery_v2'], 1)
        self.assertEqual(st['dual_stage_protocol'], 1)
        self.assertTrue(st['worker_wait_supported'])
        self.assertTrue(st['sse_supported'])

        # Worker reports v2.1 runtime metadata including model catalog, slot bindings, thinking & turn count.
        wc = self.client.post('/api/story/worker/control', headers=self.wrk_headers, json={
            'runtime': {
                'phase': 'ready', 'running': True, 'busy': False, 'last_error': '',
                'plugin_version': '2.1.0', 'model': self.model,
                'session': {'policy': 'continuous', 'chat_id': 'c1', 'generation': 1,
                            'reset_reason': '首次连接', 'turn_count': 3, 'max_turns': 10},
                'dual_stage': True, 'primary_model_mode': 'slot', 'primary_function_type': 'CHAT',
                'settlement_function_type': 'SUMMARY', 'settlement_thinking': False,
                'settlement_model': self.summary_model, 'settlement_fallback': False,
                'available_models': [
                    {'provider_id': 'prov', 'provider_name': 'Prov', 'model_id': 'gemini-4'},
                    {'provider_id': 'prov', 'provider_name': 'Prov', 'model_id': 'gemini-flash'},
                ],
                'function_bindings': [
                    {'function_type': 'CHAT', 'provider_id': 'prov', 'provider_name': 'Prov', 'model_id': 'gemini-4'},
                    {'function_type': 'SUMMARY', 'provider_id': 'prov', 'provider_name': 'Prov', 'model_id': 'gemini-flash'},
                ],
            },
            'ack_id': None, 'ack_error': '',
        })
        self.assertEqual(wc.status_code, 200)
        st2 = self.client.get('/api/story/tasks').get_json()
        self.assertTrue(st2['bridge']['dual_stage'])
        self.assertEqual(st2['bridge']['primary_model_mode'], 'slot')
        self.assertEqual(st2['bridge']['settlement_function_type'], 'SUMMARY')
        self.assertEqual(st2['bridge']['settlement_model']['model_id'], 'gemini-flash')
        self.assertEqual(st2['bridge']['settlement_thinking'], False)
        self.assertEqual(len(st2['bridge']['available_models']), 2)
        self.assertEqual(len(st2['bridge']['function_bindings']), 2)
        self.assertEqual(st2['bridge']['session']['turn_count'], 3)

        # Client issues dual_stage toggle, primary_model fixed override, bind_function_slot, settlement_thinking & max_turns.
        bc = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'dual_stage', 'dual_stage': False,
        })
        self.assertEqual(bc.status_code, 200)
        self.assertEqual(bc.get_json()['bridge']['control']['dual_stage'], False)

        pm = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'primary_model', 'primary_model_mode': 'fixed',
            'primary_provider_id': 'prov', 'primary_model_id': 'gemini-4',
        })
        self.assertEqual(pm.status_code, 200)
        self.assertEqual(pm.get_json()['bridge']['control']['primary_model_id'], 'gemini-4')

        bs = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'bind_function_slot', 'slot': 'TRANSLATION',
            'provider_id': 'prov', 'model_id': 'gemini-flash', 'use_as_settlement': True,
        })
        self.assertEqual(bs.status_code, 200)
        self.assertEqual(bs.get_json()['bridge']['control']['slot'], 'TRANSLATION')
        self.assertTrue(bs.get_json()['bridge']['control']['use_as_settlement'])

        st_th = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'settlement_thinking', 'settlement_thinking': True,
        })
        self.assertEqual(st_th.status_code, 200)
        self.assertTrue(st_th.get_json()['bridge']['control']['settlement_thinking'])

        mt = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'max_turns', 'max_turns': 15,
        })
        self.assertEqual(mt.status_code, 200)
        self.assertEqual(mt.get_json()['bridge']['control']['max_turns'], 15)

        bad_mt = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'max_turns', 'max_turns': 99,
        })
        self.assertEqual(bad_mt.status_code, 400)

    def test_worker_wait_long_poll_wakes_immediately_on_task_create(self):
        live = self.client.get('/api/story/live').get_json()
        base_seq = self.service.hub.worker_seq
        result_box = {}

        def waiter():
            t0 = time.monotonic()
            result_box['resp'] = self.service.worker_wait(since_seq=base_seq, timeout=5.0)
            result_box['elapsed'] = time.monotonic() - t0

        th = threading.Thread(target=waiter)
        th.start()
        time.sleep(0.06)
        r = self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-wait-1',
            'base_revision': live['revision'],
            'save_epoch': live['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': '继续当前剧情',
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
        })
        self.assertEqual(r.status_code, 200)
        th.join(timeout=2.0)
        self.assertFalse(th.is_alive())
        self.assertTrue(result_box['resp']['wake'])
        self.assertTrue(result_box['resp']['has_task'])
        self.assertLess(result_box['elapsed'], 1.0)

    def test_full_dual_stage_streaming_retry_commit_and_delta_turn2(self):
        live0 = self.client.get('/api/story/live').get_json()
        cast0 = live0['world']['cast']
        speaker = cast0[0] if cast0 else '沈知韫'

        # 1. Create BEGIN task & claim it.
        created = self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-dual-1',
            'base_revision': live0['revision'],
            'save_epoch': live0['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': '继续当前剧情',
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
        }).get_json()
        self.assertEqual(created['task']['status'], 'queued')

        claimed = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                                   json={'model': self.model}).get_json()['task']
        self.assertEqual(claimed['material_delivery_v2'], 1)
        self.assertEqual(claimed['dual_stage_protocol'], 1)

        # 2. Fetch v2 material (turn 1: full anchor).
        mat1 = self.client.post(f"/api/story/worker/{claimed['request_id']}/material",
                                headers=self.wrk_headers, json={
                                    'lease': claimed['lease'],
                                    'chat_id': 'chat-1',
                                    'participant_id': 'card-1',
                                    'delivery_version': 2,
                                    'protocol_mode': 'dual_stream_v2',
                                    'synced_zone0_sha256': '',
                                    'synced_zone1_sha256': '',
                                    'last_committed_sequence': 0,
                                    'is_fresh_session': True,
                                }).get_json()
        self.assertEqual(mat1['delivery_version'], 2)
        self.assertTrue(mat1['include_full_anchor'])
        self.assertIn('settlement_spec', mat1)

        # 3. Push streaming previews: faithful mode allows <=3 [D:徐志北] (never offstage) while silent mode filters [D:徐志北].
        p1 = self.client.post(f"/api/story/worker/{claimed['request_id']}/stream",
                              headers=self.wrk_headers, json={
                                  'lease': claimed['lease'], 'stage': 'streaming', 'revision': 2,
                                  'messages': [
                                      {'kind': 'narration', 'speaker': '', 'text': '客厅里的茶香缓缓散开。'},
                                      {'kind': 'dialogue', 'speaker': '徐志北', 'text': '我刚回来，喝口茶正好。'},
                                      {'kind': 'dialogue', 'speaker': '临时场外路人', 'text': '非法场外对白应被过滤'},
                                      {'kind': 'dialogue', 'speaker': speaker, 'text': '志北，先坐下喝口茶。'},
                                  ],
                              }).get_json()
        self.assertEqual(p1['count'], 3)
        # Switch to silent mode -> [D:徐志北] is filtered cleanly!
        pref_res = self.client.post('/api/story/preferences', headers=self.cli_headers, json={'protagonist_style': 'silent'})
        self.assertEqual(pref_res.status_code, 200)
        self.assertEqual(pref_res.get_json()['preferences']['protagonist_style'], 'silent')
        p_silent = self.client.post(f"/api/story/worker/{claimed['request_id']}/stream",
                                    headers=self.wrk_headers, json={
                                        'lease': claimed['lease'], 'stage': 'streaming', 'revision': 3,
                                        'messages': [
                                            {'kind': 'narration', 'speaker': '', 'text': '客厅里的茶香缓缓散开。'},
                                            {'kind': 'dialogue', 'speaker': '徐志北', 'text': '静音模式下应被过滤'},
                                            {'kind': 'dialogue', 'speaker': speaker, 'text': '志北，先坐下喝口茶。'},
                                        ],
                                    }).get_json()
        self.assertEqual(p_silent['count'], 2)
        # Restore faithful mode for remainder of test.
        self.client.post('/api/story/preferences', headers=self.cli_headers, json={'protagonist_style': 'faithful'})
        # Stale revision ignored.
        p_stale = self.client.post(f"/api/story/worker/{claimed['request_id']}/stream",
                                   headers=self.wrk_headers, json={
                                       'lease': claimed['lease'], 'stage': 'thinking', 'revision': 1, 'messages': [],
                                   }).get_json()
        self.assertTrue(p_stale.get('ignored'))
        snap_mid = self.client.get('/api/story/live').get_json()
        self.assertEqual(snap_mid['stream_preview']['stage'], 'streaming')
        self.assertEqual(len(snap_mid['stream_preview']['messages']), 2)
        self.assertEqual(snap_mid['world']['interaction']['count'], 0)

        # 4. Submit bad settlement with allow_settlement_retry=True -> retryable without refund!
        fg = _fg_script(speaker=speaker)
        bad_settle = _settlement_payload(category='A')  # BEGIN requires SYSTEM!
        retry_resp = self.client.post(f"/api/story/worker/{claimed['request_id']}/result",
                                      headers=self.wrk_headers, json={
                                          'lease': claimed['lease'],
                                          'text': json.dumps({'dual_stage_version': 1, 'foreground_text': fg, 'settlement': bad_settle}, ensure_ascii=False),
                                          'conversation_audit': self._audit(mat1),
                                          'timing': {'generation_ms': 1200, 'settlement_ms': 400, 'preflight_ms': 0,
                                                     'generation_passes': 1, 'settlement_passes': 1, 'settlement_model_id': 'gemini-flash'},
                                          'allow_settlement_retry': True,
                                      }).get_json()
        self.assertTrue(retry_resp.get('retryable_settlement'))
        self.assertEqual(retry_resp['task']['status'], 'generating')

        # 5. Retry with fixed settlement -> commits atomically and clears stream_preview!
        good_settle = _settlement_payload(category='SYSTEM', conditions=None, clock_time='09:10')
        ok_resp = self.client.post(f"/api/story/worker/{claimed['request_id']}/result",
                                   headers=self.wrk_headers, json={
                                       'lease': claimed['lease'],
                                       'text': json.dumps({'dual_stage_version': 1, 'foreground_text': fg, 'settlement': good_settle}, ensure_ascii=False),
                                       'conversation_audit': self._audit(mat1),
                                       'timing': {'generation_ms': 1200, 'settlement_ms': 750, 'preflight_ms': 0,
                                                  'generation_passes': 1, 'settlement_passes': 2, 'settlement_model_id': 'gemini-flash'},
                                       'allow_settlement_retry': True,
                                   }).get_json()
        self.assertEqual(ok_resp['task']['status'], 'committed')

        live1 = self.client.get('/api/story/live').get_json()
        self.assertIsNone(live1['stream_preview'])
        # Before playback completes, world stays on before_world (anti-spoiler invariant); playback holds new segment.
        self.assertFalse(live1['playback']['completed'])
        self.assertEqual(live1['playback']['total'], 3)
        seg_id = live1['playback']['segment_id']

        # Complete playback sequentially so post-segment world activates and we can issue Turn 2 (option A).
        total = live1['playback']['total']
        for r_idx in range(live1['playback']['revealed'] + 1, total + 1):
            live1 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
                'save_epoch': live1['save_epoch'], 'segment_id': seg_id, 'revealed': r_idx, 'completed': False,
            }).get_json()
        live1 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
            'save_epoch': live1['save_epoch'], 'segment_id': seg_id, 'revealed': total, 'completed': True,
        }).get_json()
        self.assertEqual(live1['world']['interaction']['count'], 1)

        # 6. Turn 2: verify incremental delta (include_full_anchor == False) & identical Zone 0/1 SHA!
        self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-dual-2',
            'base_revision': live1['revision'],
            'save_epoch': live1['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': live1['history'][-1]['decision']['options'][0]['text'],
            'selection': {'segment_id': seg_id, 'option_id': 'A'},
        })
        claimed2 = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                                    json={'model': self.model}).get_json()['task']
        mat2 = self.client.post(f"/api/story/worker/{claimed2['request_id']}/material",
                                headers=self.wrk_headers, json={
                                    'lease': claimed2['lease'],
                                    'chat_id': 'chat-1',
                                    'participant_id': 'card-1',
                                    'delivery_version': 2,
                                    'protocol_mode': 'dual_stream_v2',
                                    'synced_zone0_sha256': mat1['zone0_sha256'],
                                    'synced_zone1_sha256': mat1['zone1_sha256'],
                                    'last_committed_sequence': 1,
                                    'is_fresh_session': False,
                                }).get_json()
        self.assertEqual(mat2['zone0_sha256'], mat1['zone0_sha256'])
        self.assertEqual(mat2['zone1_sha256'], mat1['zone1_sha256'])
        self.assertFalse(mat2['include_full_anchor'])
        self.assertLess(len(mat2['input_text']), 3000)

        # Cancel turn 2 -> clears preview and refunds stamina cleanly.
        self.client.post(f"/api/story/worker/{claimed2['request_id']}/stream",
                         headers=self.wrk_headers, json={
                             'lease': claimed2['lease'], 'stage': 'thinking', 'revision': 1, 'messages': [],
                         })
        cancel_res = self.client.post(f"/api/story/tasks/{claimed2['request_id']}/cancel",
                                      headers=self.cli_headers, json={})
        self.assertEqual(cancel_res.status_code, 200)
        live_after_cancel = self.client.get('/api/story/live').get_json()
        self.assertIsNone(live_after_cancel['stream_preview'])
        self.assertEqual(live_after_cancel['world']['progression']['stamina'], 100)

    def test_dual_stage_missing_decision_fallback_retry_preview_sanitize_and_redline_guard(self):
        live0 = self.client.get('/api/story/live').get_json()
        cast0 = live0['world']['cast']
        speaker = cast0[0] if cast0 else '沈知韫'

        # 1. Start BEGIN task.
        self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-fb-1',
            'base_revision': live0['revision'],
            'save_epoch': live0['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': '继续当前剧情',
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
        })
        claimed = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                                   json={'model': self.model}).get_json()['task']
        mat = self.client.post(f"/api/story/worker/{claimed['request_id']}/material",
                               headers=self.wrk_headers, json={
                                   'lease': claimed['lease'], 'chat_id': 'chat-fb', 'participant_id': 'card-fb',
                                   'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                                   'synced_zone0_sha256': '', 'synced_zone1_sha256': '',
                                   'last_committed_sequence': 0, 'is_fresh_session': True,
                               }).get_json()

        # 2. Preview stream with leaked `---\nDECISION---` suffix (older plugin compat) must be sanitized cleanly.
        self.client.post(f"/api/story/worker/{claimed['request_id']}/stream",
                         headers=self.wrk_headers, json={
                             'lease': claimed['lease'], 'stage': 'streaming', 'revision': 1,
                             'messages': [{
                                 'kind': 'action', 'speaker': speaker,
                                 'text': '她合上文件夹，没有催。\n\n---\nDECISION---\nPROMPT: 局面\nA: 一\nB: 二\nC: 三',
                             }],
                         })
        snap = self.client.get('/api/story/live').get_json()
        self.assertEqual(snap['stream_preview']['messages'][0]['text'], '她合上文件夹，没有催。')

        # 3. Foreground has valid prose but completely omits ---DECISION---.
        prose_only = (
            '[N] 书房里的冷气偏低，台灯光落在纸页边缘。\n'
            f'[D:{speaker}] 志北，先坐下喝口茶，有事慢慢说。\n'
        )
        # Attempt 1: settlement without fallback_decision -> retryable_settlement=True (not failed/refunded!).
        settle_no_fb = _settlement_payload(category='SYSTEM', conditions=None, clock_time='09:10')
        r1 = self.client.post(f"/api/story/worker/{claimed['request_id']}/result",
                              headers=self.wrk_headers, json={
                                  'lease': claimed['lease'],
                                  'text': json.dumps({'dual_stage_version': 1, 'foreground_text': prose_only, 'settlement': settle_no_fb}, ensure_ascii=False),
                                  'conversation_audit': self._audit(mat, chat_id='chat-fb', card_id='card-fb'),
                                  'allow_settlement_retry': True,
                              }).get_json()
        self.assertTrue(r1.get('retryable_settlement'))
        self.assertIn('fallback_decision', r1.get('error', ''))
        self.assertEqual(r1['task']['status'], 'generating')

        # Attempt 2: settlement supplies valid fallback_decision -> commits seamlessly!
        settle_with_fb = dict(settle_no_fb, fallback_decision={
            'prompt': '她已把茶推到你手边，你准备怎么回应？',
            'options': [
                {'id': 'A', 'text': '端起茶杯道谢，顺着问她昨晚忙什么。'},
                {'id': 'B', 'text': '坐近半步扶稳桌角的文件，问要不要帮忙。'},
                {'id': 'C', 'text': '直接问她刚才翻扣手机是不是公司出了事。'},
            ],
        })
        r2 = self.client.post(f"/api/story/worker/{claimed['request_id']}/result",
                              headers=self.wrk_headers, json={
                                  'lease': claimed['lease'],
                                  'text': json.dumps({'dual_stage_version': 1, 'foreground_text': prose_only, 'settlement': settle_with_fb}, ensure_ascii=False),
                                  'conversation_audit': self._audit(mat, chat_id='chat-fb', card_id='card-fb'),
                                  'allow_settlement_retry': True,
                              }).get_json()
        self.assertEqual(r2['task']['status'], 'committed')

        # 4. Redline guard precedence: missing decision + K01 secret leak by non-knower must NEVER be retryable.
        # Move 徐念薇 to present check via direct normalize_dual_stage on a redline-violating scene.
        live1 = self.client.get('/api/story/live').get_json()
        seg_id = live1['playback']['segment_id']
        total1 = live1['playback']['total']
        for i in range(live1['playback']['revealed'] + 1, total1 + 1):
            live1 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
                'save_epoch': live1['save_epoch'], 'segment_id': seg_id, 'revealed': i, 'completed': False,
            }).get_json()
        live1 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
            'save_epoch': live1['save_epoch'], 'segment_id': seg_id, 'revealed': total1, 'completed': True,
        }).get_json()
        self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-fb-redline',
            'base_revision': live1['revision'],
            'save_epoch': live1['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': live1['history'][-1]['decision']['options'][0]['text'],
            'selection': {'segment_id': seg_id, 'option_id': 'A'},
        })
        claimed_rl = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                                      json={'model': self.model}).get_json()['task']
        mat_rl = self.client.post(f"/api/story/worker/{claimed_rl['request_id']}/material",
                                  headers=self.wrk_headers, json={
                                      'lease': claimed_rl['lease'], 'chat_id': 'chat-fb', 'participant_id': 'card-fb',
                                      'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                                      'synced_zone0_sha256': mat['zone0_sha256'], 'synced_zone1_sha256': mat['zone1_sha256'],
                                      'last_committed_sequence': 1, 'is_fresh_session': False,
                                  }).get_json()
        bad_prose_no_decision = f'[N] 客厅灯光下，{speaker}突然脱口说出遗嘱留给亲生子千亿家产唯一合法继承人的秘密。'
        bad_settle_a = _settlement_payload(category='A', conditions={
            'intensity': 'A', 'effective_progress': True, 'scene': live1['world']['location'],
            'npc': speaker, 'action_changed': False, 'stress_signals': [], 'breakout_triggered': False,
        }, clock_time='09:20')
        rl_resp = self.client.post(f"/api/story/worker/{claimed_rl['request_id']}/result",
                                   headers=self.wrk_headers, json={
                                       'lease': claimed_rl['lease'],
                                       'text': json.dumps({'dual_stage_version': 1, 'foreground_text': bad_prose_no_decision, 'settlement': bad_settle_a}, ensure_ascii=False),
                                       'conversation_audit': self._audit(mat_rl, chat_id='chat-fb', card_id='card-fb', stamp=200),
                                       'allow_settlement_retry': True,
                                   }).get_json()
        self.assertFalse(rl_resp.get('retryable_settlement'))
        self.assertEqual(rl_resp['task']['status'], 'failed')
        self.assertIn('红线拦截', rl_resp['task']['error'])

    def test_bridge_view_exposes_expected_plugin_version(self):
        manifest_dir = self.root / 'scene_chat_dev/local.story.operit_bridge'
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / 'manifest.json').write_text(json.dumps({'version': '2.1.3'}), encoding='utf-8')
        snap = self.client.get('/api/story/tasks').get_json()
        self.assertEqual(snap['bridge']['expected_plugin_version'], '2.1.3')
        # Also verify live monitor preserves expected_plugin_version alongside older plugin_version.
        hb = self.client.post('/api/story/worker/control', headers=self.wrk_headers, json={
            'runtime': {
                'running': True, 'busy': False, 'phase': 'ready',
                'plugin_version': '2.1.2', 'last_error': '', 'model': self.model,
            },
            'ack_id': None, 'ack_error': '',
        })
        self.assertEqual(hb.status_code, 200)
        snap2 = self.client.get('/api/story/tasks').get_json()
        self.assertEqual(snap2['bridge']['plugin_version'], '2.1.2')
        self.assertEqual(snap2['bridge']['expected_plugin_version'], '2.1.3')

    def test_vigilance_repair_hint_thinking_mode_and_tts_prewarmer(self):
        # 1. Verify bridge control accepts settlement_thinking_mode ('auto'|'off'|'on') and reports it.
        hb = self.client.post('/api/story/worker/control', headers=self.wrk_headers, json={
            'runtime': {
                'running': True, 'busy': False, 'phase': 'ready',
                'plugin_version': '2.1.4', 'last_error': '', 'model': self.model,
                'settlement_thinking': False, 'settlement_thinking_mode': 'auto',
            },
            'ack_id': None, 'ack_error': '',
        })
        self.assertEqual(hb.status_code, 200)
        ctrl = self.client.post('/api/story/bridge/control', headers=self.cli_headers, json={
            'action': 'settlement_thinking', 'settlement_thinking_mode': 'auto',
        })
        self.assertEqual(ctrl.status_code, 200)
        self.assertEqual(ctrl.get_json()['bridge']['settlement_thinking_mode'], 'auto')

        # 2. Verify TTS prewarmer receives voiced items (and never 徐志北) on /stream and commit.
        prewarmed = []
        self.service._tts_prewarmer = lambda items: prewarmed.extend(items)
        live0 = self.client.get('/api/story/live').get_json()
        speaker = live0['world']['cast'][0] if live0['world']['cast'] else '沈知韫'
        self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-prewarm-1',
            'base_revision': live0['revision'],
            'save_epoch': live0['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': '继续当前剧情',
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
        })
        claimed = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                                   json={'model': self.model}).get_json()['task']
        mat = self.client.post(f"/api/story/worker/{claimed['request_id']}/material",
                               headers=self.wrk_headers, json={
                                   'lease': claimed['lease'], 'chat_id': 'chat-pw', 'participant_id': 'card-pw',
                                   'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                                   'synced_zone0_sha256': '', 'synced_zone1_sha256': '',
                                   'last_committed_sequence': 0, 'is_fresh_session': True,
                               }).get_json()
        self.assertIn('监视目标防错铁律', mat['settlement_spec']['system_prompt'])
        self.client.post(f"/api/story/worker/{claimed['request_id']}/stream",
                         headers=self.wrk_headers, json={
                             'lease': claimed['lease'], 'stage': 'settling', 'revision': 1,
                             'messages': [
                                 {'kind': 'narration', 'speaker': '', 'text': '雨声拍打在窗沿。'},
                                 {'kind': 'dialogue', 'speaker': '徐志北', 'text': '我先坐下。'},
                                 {'kind': 'dialogue', 'speaker': speaker, 'text': '过来吧。'},
                             ],
                         })
        self.assertTrue(len(prewarmed) >= 2)
        self.assertFalse(any(it['speaker'] == '徐志北' for it in prewarmed))

        # 3. Verify vigilance_events with target="徐承邺" returns actionable repair guidance.
        import story_progression as sp
        bad_vig = _settlement_payload(category='A', conditions={
            'intensity': 'A', 'effective_progress': True, 'scene': live0['world']['location'],
            'npc': speaker, 'action_changed': False, 'stress_signals': 0, 'breakout_triggered': [],
        }, clock_time='09:10')
        bad_vig['resolution']['events'] = [{
            'group': 'vigilance_events', 'target': '徐承邺',
            'tags': ['无异常回合'], 'evidence': '客厅里的茶香缓缓散开。',
        }]
        res_body = {
            'messages': [{'kind': 'narration', 'speaker': '', 'text': '客厅里的茶香缓缓散开。'}],
            'selection': {'segment_id': '', 'option_id': 'A'},
            'operation': None,
            'audit': {'reservation': {'status': 'held', 'quote': {'kind': 'action', 'total': 5, 'before': 100}}},
            'resolution': bad_vig['resolution'],
        }
        with self.assertRaises(rr.RoundError) as vctx:
            sp.resolution(self.root, self.service.store._files(), res_body)
        self.assertIn('严禁填监视者徐承邺本人', str(vctx.exception))

    def test_stage2_audit_autofill_and_stage1_checkpoint_resume(self):
        # 1. Stage 1 completes, Stage 2 fails with error + stage1_checkpoint -> checkpoint persisted!
        live0 = self.client.get('/api/story/live').get_json()
        speaker = live0['world']['cast'][0] if live0['world']['cast'] else '沈知韫'
        fg_text = (
            f'[N] 客厅里的微风轻轻掠过窗纱。\n'
            f'[A:徐志北] 徐志北随手关上廊门，走到桌边落座。\n'
            f'[D:徐志北] 刚才外面风有点大，先喝口热茶吧。\n'
            f'[D:{speaker}] 坐下喝口茶吧。\n'
            '---DECISION---\n'
            'PROMPT: 你准备怎么回应？\n'
            'A: 接过茶杯轻声致谢。\n'
            'B: 顺势询问家里近况。\n'
            'C: 靠近几步低声试探。\n'
        )
        self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-cp-1',
            'base_revision': live0['revision'],
            'save_epoch': live0['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': '继续当前剧情',
            'selection': {'segment_id': '', 'option_id': 'BEGIN'},
        })
        c1 = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                              json={'model': self.model}).get_json()['task']
        m1 = self.client.post(f"/api/story/worker/{c1['request_id']}/material",
                              headers=self.wrk_headers, json={
                                  'lease': c1['lease'], 'chat_id': 'chat-cp-1', 'participant_id': 'card-cp-1',
                                  'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                                  'synced_zone0_sha256': '', 'synced_zone1_sha256': '',
                                  'last_committed_sequence': 0, 'is_fresh_session': True,
                              }).get_json()
        audit1 = self._audit(m1, chat_id='chat-cp-1', card_id='card-cp-1', stamp=1710000100)
        r_err = self.client.post(f"/api/story/worker/{c1['request_id']}/result",
                                 headers=self.wrk_headers, json={
                                     'lease': c1['lease'],
                                     'error': '后台结算(SUMMARY)失败：后台结算回复不是合法JSON对象',
                                     'stage1_checkpoint': {
                                         'foreground_text': fg_text,
                                         'foreground_messages': [
                                             {'kind': 'narration', 'speaker': '', 'text': '客厅里的微风轻轻掠过窗纱。'},
                                             {'kind': 'dialogue', 'speaker': speaker, 'text': '坐下喝口茶吧。'},
                                         ],
                                         'generation_ms': 1234,
                                         'base_audit': audit1,
                                     },
                                 }).get_json()
        self.assertEqual(r_err['task']['status'], 'failed')
        self.assertTrue(r_err['task'].get('has_stage1_checkpoint'))

        # 2. Retry with resume_stage2=True -> delivers stage1_checkpoint in /material & commits with generation_passes=0
        #    AND tests dual-stage audit-line autofill (empty resolution.basis, empty clock.basis, placeholder checks)!
        r_retry = self.client.post(f"/api/story/tasks/{c1['request_id']}/retry",
                                   headers=self.cli_headers, json={'resume_stage2': True}).get_json()
        self.assertEqual(r_retry['task']['status'], 'queued')
        self.assertTrue(r_retry['task'].get('resume_stage2'))

        c2 = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                              json={'model': self.model}).get_json()['task']
        self.assertTrue(c2.get('resume_stage2'))
        m2 = self.client.post(f"/api/story/worker/{c2['request_id']}/material",
                              headers=self.wrk_headers, json={
                                  'lease': c2['lease'], 'chat_id': 'chat-cp-1', 'participant_id': 'card-cp-1',
                                  'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                                  'synced_zone0_sha256': '', 'synced_zone1_sha256': '',
                                  'last_committed_sequence': 0, 'is_fresh_session': False,
                              }).get_json()
        self.assertIn('stage1_checkpoint', m2)
        self.assertEqual(m2['stage1_checkpoint']['foreground_text'], fg_text)

        # Rebind audit delivery to m2 (mirrors bridge main.js resume behavior).
        rebound_audit = dict(m2['stage1_checkpoint']['base_audit'])
        rebound_audit['delivery'] = {**m2['delivery'], 'user_message_timestamp': 1710000100}
        settle = _settlement_payload(category='SYSTEM', conditions=None, clock_time='09:05')
        settle['resolution']['basis'] = ''
        settle['resolution']['clock']['basis'] = '通过'
        settle['checks'] = {'intent': '', 'knowledge': '通过', 'action': '同上', 'pace': '无'}
        dual_text = json.dumps({'dual_stage_version': 1, 'foreground_text': fg_text, 'settlement': settle}, ensure_ascii=False)
        r_ok = self.client.post(f"/api/story/worker/{c2['request_id']}/result",
                                headers=self.wrk_headers, json={
                                    'lease': c2['lease'],
                                    'text': dual_text,
                                    'conversation_audit': rebound_audit,
                                    'timing': {
                                        'generation_ms': 1234, 'settlement_ms': 400, 'preflight_ms': 0,
                                        'generation_passes': 0, 'settlement_passes': 1, 'settlement_model_id': 'summary-m',
                                    },
                                }).get_json()
        self.assertEqual(r_ok['task']['status'], 'committed')
        self.assertFalse(r_ok['task'].get('has_stage1_checkpoint'))
        self.assertFalse(r_ok['task'].get('resume_stage2'))

        # 3. Case B: final Stage 2 submission fails validation (non-foreground error) -> checkpoint saved;
        #    full retry (resume_stage2=False) clears checkpoint!
        live1 = self.client.get('/api/story/live').get_json()
        seg1 = live1['playback']['segment_id']
        total1 = live1['playback']['total']
        prog1 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
            'save_epoch': live1['save_epoch'], 'segment_id': seg1, 'revealed': total1, 'completed': False, 'catchup': True,
        })
        self.assertEqual(prog1.status_code, 200, prog1.get_json())
        prog2 = self.client.post('/api/story/live/progress', headers=self.cli_headers, json={
            'save_epoch': live1['save_epoch'], 'segment_id': seg1, 'revealed': total1, 'completed': True,
        })
        self.assertEqual(prog2.status_code, 200, prog2.get_json())
        live2 = self.client.get('/api/story/live').get_json()
        t3_res = self.client.post('/api/story/tasks', headers=self.cli_headers, json={
            'request_id': 'req-cp-2',
            'base_revision': live2['revision'],
            'save_epoch': live2['save_epoch'],
            'entry_mode': 'live_interaction',
            'action': '接过茶杯轻声致谢。',
            'selection': {'segment_id': seg1, 'option_id': 'A'},
        })
        self.assertEqual(t3_res.status_code, 200, t3_res.get_json())
        c3 = self.client.post('/api/story/worker/claim', headers=self.wrk_headers,
                              json={'model': self.model}).get_json()['task']
        self.assertIsNotNone(c3)
        m3 = self.client.post(f"/api/story/worker/{c3['request_id']}/material",
                              headers=self.wrk_headers, json={
                                  'lease': c3['lease'], 'chat_id': 'chat-cp-1', 'participant_id': 'card-cp-1',
                                  'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                                  'synced_zone0_sha256': '', 'synced_zone1_sha256': '',
                                  'last_committed_sequence': 1, 'is_fresh_session': False,
                              }).get_json()
        audit3 = self._audit(m3, chat_id='chat-cp-1', card_id='card-cp-1', stamp=1710000200)
        bad_settle = _settlement_payload(category='C', conditions={
            'intensity': 'C', 'effective_progress': True, 'scene': live2['world']['location'],
            'npc': speaker, 'action_changed': False, 'stress_signals': 0, 'breakout_triggered': [],
        }, clock_time='09:15')  # Wrong category C for fixed option A -> Stage 2 settlement error!
        r_fail = self.client.post(f"/api/story/worker/{c3['request_id']}/result",
                                  headers=self.wrk_headers, json={
                                      'lease': c3['lease'],
                                      'text': json.dumps({'dual_stage_version': 1, 'foreground_text': fg_text, 'settlement': bad_settle}, ensure_ascii=False),
                                      'conversation_audit': audit3,
                                  }).get_json()
        self.assertEqual(r_fail['task']['status'], 'failed')
        self.assertTrue(r_fail['task'].get('has_stage1_checkpoint'))

        r_full = self.client.post(f"/api/story/tasks/{c3['request_id']}/retry",
                                  headers=self.cli_headers, json={'resume_stage2': False}).get_json()
        self.assertEqual(r_full['task']['status'], 'queued')
        self.assertFalse(r_full['task'].get('resume_stage2'))
        self.assertFalse(r_full['task'].get('has_stage1_checkpoint'))


if __name__ == '__main__':
    unittest.main()

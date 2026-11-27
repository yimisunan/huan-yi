"""Regression tests for v2.3.0 Batch 3 runtime efficiency & Paid TTS prewarm safeguard."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import interaction_runtime as ir
import relationship_query as rq
import round_runtime as rr
import scene_chat
import story_compiler as sc
import story_service as ss

_opening_spec = importlib.util.spec_from_file_location('opening_box_eff', ROOT / '存档开局随机盲盒.py')
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


class RuntimeEfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='runtime_eff_'))
        _copy_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_mtime_size_cache_hits_and_instant_invalidation(self):
        """(mtime_ns, size) caches in story_compiler, relationship_query, and scene_chat hit & immediately invalidate on edit."""
        # 1) story_compiler Zone 0 cache + invalidation on KB edit
        z0_a = sc.build_zone0_global(self.tmp, mode='dual_stream_v2', protagonist_style='faithful')
        z0_b = sc.build_zone0_global(self.tmp, mode='dual_stream_v2', protagonist_style='faithful')
        self.assertEqual(z0_a, z0_b)

        kb_path = self.tmp / 'txt文件/知识库/世界观类.json'
        kb_data = json.loads(kb_path.read_text(encoding='utf-8'))
        kb_data['data']['entries'][0]['content'] += '\n【缓存即时失效探针-v230】'
        kb_path.write_text(json.dumps(kb_data, ensure_ascii=False, indent=2), encoding='utf-8')
        z0_c = sc.build_zone0_global(self.tmp, mode='dual_stream_v2', protagonist_style='faithful')
        self.assertIn('【缓存即时失效探针-v230】', z0_c)

        # 2) relationship_query verify_view cache + instant invalidation on jsonl tamper
        reg1 = rq.RelationshipRegistry(self.tmp)
        rows1 = reg1.verify_view()
        reg2 = rq.RelationshipRegistry(self.tmp)
        rows2 = reg2.verify_view()
        self.assertEqual(len(rows1), len(rows2))
        self.assertEqual(rows1[0], rows2[0])

        view_path = self.tmp / 'txt文件/关系称谓查询.jsonl'
        orig_view = view_path.read_text(encoding='utf-8')
        view_path.write_text(orig_view + '\n{"tamper": true}\n', encoding='utf-8')
        with self.assertRaises(rq.RelationshipError):
            rq.RelationshipRegistry(self.tmp).verify_view()
        view_path.write_text(orig_view, encoding='utf-8')

        # 3) scene_chat reference alias cache + invalidation on 角色类.json edit
        svc = ss.StoryService(self.tmp)
        helper = scene_chat.SceneService(self.tmp, svc)
        refs_a = helper.references('我想问问徐承邺什么时候回老宅', [])
        self.assertTrue(any(r['name'] == '徐承邺' for r in refs_a))
        refs_b = helper.references('我想问问徐承邺什么时候回老宅', [])
        self.assertEqual(refs_a, refs_b)

    def test_02_lazy_v2_skips_live_txt_and_preserves_tamper_detection(self):
        """With v2 bridge active, create -> claim -> material(v2) -> result -> commit skips writing 200KB live.txt
        while still catching external save/config tampering via verify_delivery / source_check."""
        sys.path.insert(0, str(Path(__file__).parent))
        from test_phase_ab_linkage import complete_current_playback, reset_clean_save
        reset_clean_save(self.tmp)
        svc = ss.StoryService(self.tmp)
        with svc.store._locked():
            opening.initialize_prologue(self.tmp, 'lazy-init', opening.SCENARIOS[0]['id'])
        complete_current_playback(svc)
        model_obj = {
            'key': '["CHAT","p","m"]', 'function_type': 'CHAT',
            'provider_id': 'p', 'provider_name': 'P', 'model_id': 'm',
            'pricing_configured': True,
        }
        # Record a v2.3.0 bridge heartbeat so _is_v2_bridge_active(tasks) == True
        svc.worker_control({
            'runtime': {
                'phase': 'ready', 'running': True, 'busy': False, 'last_error': '',
                'plugin_version': '2.3.0',
                'model': model_obj,
                'session': {'policy': 'continuous', 'chat_id': 'c1', 'generation': 1, 'reset_reason': 'init'},
            },
            'ack_id': None, 'ack_error': '',
        })

        snap2 = svc.interaction_snapshot()
        seg1 = ir.segment(svc.root, svc.store._files())
        opt_a1 = seg1['decision']['options'][0]['text']
        req_id = 'req-lazy-v2-1'
        svc.create({
            'request_id': req_id, 'base_revision': snap2['revision'],
            'save_epoch': snap2['save_epoch'], 'entry_mode': ir.MODE,
            'action': opt_a1, 'selection': {'segment_id': seg1['id'], 'option_id': 'A'},
        })
        ctx = json.loads(svc._blob(req_id, '.context.json').read_bytes())
        self.assertTrue(ctx['packet'].get('lazy'), 'v2 bridge must activate lazy_live_txt')
        live_txt_path = svc.store._path(ctx['packet']['path'])
        self.assertFalse(live_txt_path.exists(), 'lazy_live_txt MUST NOT write 200KB live.txt to disk')

        task = svc.claim({'model': model_obj})['task']
        self.assertEqual(task['packet_bytes'], 0)

        mat = svc.material(req_id, {
            'lease': task['lease'], 'chat_id': 'c1', 'participant_id': 'model:chat',
            'delivery_version': 2, 'protocol_mode': 'dual_stream_v2', 'is_fresh_session': True,
        })
        self.assertEqual(mat['delivery_version'], 2)
        self.assertIn('zone0_global', mat)
        self.assertIn('zone1_scene', mat)
        self.assertFalse(live_txt_path.exists())

        # Full commit with lazy v2 delivery succeeds cleanly
        fg_text = '[A:沈知韫] 她抬眼接过水杯，指尖在杯壁停了一瞬。\n[D:沈知韫] 放这儿吧，正好有点口渴。\n---DECISION---\nPROMPT: 她看着你。\nA: 问她刚才的报表\nB: 顺手替她披件披肩\nC: 说先回房间休息'
        settle_obj = {
            'operation': None, 'handoff': '',
            'checks': {'intent': '递水', 'knowledge': '仅在场', 'action': '无登记操作', 'pace': '交还'},
            'resolution': {
                'category': 'A', 'basis': '日常递水互动',
                'clock': {'day': 1, 'time': '23:10', 'basis': '递水闲谈约5分钟'},
                'events': [],
                'memory': {'fact': '', 'anchor_ops': [], 'chronicle_digest': ''},
                'conditions': {'intensity': 'A', 'effective_progress': True, 'scene': '徐家主宅', 'npc': None, 'action_changed': True, 'stress_signals': 0, 'breakout_triggered': []},
                'sleep': {'kind': 'none', 'start': None, 'evidence': ''},
                'task': None, 'items': [],
            },
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
        self.assertEqual(res['task']['status'], 'committed')

        # Now start a second lazy v2 turn and tamper with 互动运行配置.json BEFORE verify -> MUST raise ConflictError!
        complete_current_playback(svc)
        snap4 = svc.interaction_snapshot()
        seg2 = ir.segment(svc.root, svc.store._files())
        opt_a2 = seg2['decision']['options'][0]['text']
        req2 = 'req-lazy-tamper'
        svc.create({
            'request_id': req2, 'base_revision': snap4['revision'],
            'save_epoch': snap4['save_epoch'], 'entry_mode': ir.MODE,
            'action': opt_a2, 'selection': {'segment_id': seg2['id'], 'option_id': 'A'},
        })
        task2 = svc.claim({'model': model_obj})['task']
        mat2 = svc.material(req2, {
            'lease': task2['lease'], 'chat_id': 'c1', 'participant_id': 'model:chat',
            'delivery_version': 2, 'protocol_mode': 'dual_stream_v2', 'is_fresh_session': False,
        })
        cfg_path = self.tmp / ir.CONFIG
        cfg_path.write_text(cfg_path.read_text(encoding='utf-8') + '\n ', encoding='utf-8')
        proof2 = {
            'api': 'Tools.Chat.sendMessageStreaming', 'chat_id': 'c1', 'participant_id': 'model:chat',
            'workspace': str(self.tmp),
            'outcome': {'type': 'committed', 'status': 'completed', 'userMessageTimestamp': 200, 'assistant': {'messageTimestamp': 201}},
            'snapshot_message_timestamp': 201,
            'tools': [],
            'delivery': {**mat2['delivery'], 'user_message_timestamp': 200},
        }
        with self.assertRaises(rr.ConflictError):
            ir.verify(svc, req2, proof2)

    def test_03_paid_tts_guard_leaves_free_tier_untouched(self):
        """Free TTS tier stays 100% unchanged; paid tiers respect voice mute, skip streaming stage, and cap to 2 lines."""
        prewarm_batches = []
        svc = ss.StoryService(self.tmp, tts_prewarmer=lambda items: prewarm_batches.append(list(items)))
        sample_msgs = [
            {'kind': 'narration', 'speaker': '', 'text': '第一句旁白测试。'},
            {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '第二句沈知韫台词。'},
            {'kind': 'dialogue', 'speaker': '苏婉青', 'text': '第三句苏婉青台词。'},
            {'kind': 'dialogue', 'speaker': '徐念薇', 'text': '第四句徐念薇台词。'},
        ]
        vcfg_path = self.tmp / 'voice_config.json'

        # 1) Free tier: even when muted and stage='streaming', STILL prewarms 3 lines (100% unchanged!)
        vcfg_path.write_text(json.dumps({'__settings__': {'voice_tier': 'free'}}, ensure_ascii=False), encoding='utf-8')
        ir.save_story_prefs(self.tmp, {'voice_playback_enabled': False})
        svc._trigger_tts_prewarm(sample_msgs, dedup_prefix='free-1', stage='streaming')
        self.assertEqual(len(prewarm_batches), 1)
        self.assertEqual(len(prewarm_batches[0]), 3, 'free tier must remain 100% untouched (3 lines on streaming)')

        # 2) Paid tier + muted: 0 prewarm calls!
        prewarm_batches.clear()
        vcfg_path.write_text(json.dumps({'__settings__': {'voice_tier': 'vip'}}, ensure_ascii=False), encoding='utf-8')
        ir.save_story_prefs(self.tmp, {'voice_playback_enabled': False})
        svc._trigger_tts_prewarm(sample_msgs, dedup_prefix='paid-muted', stage='settling')
        self.assertEqual(len(prewarm_batches), 0, 'paid tier must NOT prewarm while muted')

        # 3) Paid tier + unmuted + stage='streaming': 0 prewarm calls (wait for settling)!
        ir.save_story_prefs(self.tmp, {'voice_playback_enabled': True})
        svc._trigger_tts_prewarm(sample_msgs, dedup_prefix='paid-stream', stage='streaming')
        self.assertEqual(len(prewarm_batches), 0, 'paid tier must skip streaming stage prewarm')

        # 4) Paid tier + unmuted + stage='settling': prewarms cleanly, capped at 2 lines!
        svc._trigger_tts_prewarm(sample_msgs, dedup_prefix='paid-settle', stage='settling')
        self.assertEqual(len(prewarm_batches), 1)
        self.assertEqual(len(prewarm_batches[0]), 2, 'paid tier prewarm must cap at 2 lines')


if __name__ == '__main__':
    unittest.main()

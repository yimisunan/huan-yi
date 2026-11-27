"""Drama 3 & S2.1 voice expressivity overhaul unit tests (stdlib unittest, zero live network calls)."""
import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE = ROOT / '语音运行.py'
voice_mod = types.ModuleType('voice_runtime_drama3_test')
voice_mod.__file__ = str(SOURCE)
exec(compile(SOURCE.read_text(encoding='utf-8'), str(SOURCE), 'exec'), voice_mod.__dict__)
voice_mod.FISH_API_KEY = 'test-key-placeholder'

import story_service as ss
import 存档开局随机盲盒 as blind_box


class TestDrama3VoicePipeline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='drama3-unit-')
        self.tmpdir = Path(self.temp.name)
        self.old_cfg = voice_mod.CONFIG_FILE
        self.old_disk = voice_mod.TTS_DISK_CACHE_DIR
        voice_mod.CONFIG_FILE = str(self.tmpdir / 'voice_config.json')
        voice_mod.TTS_DISK_CACHE_DIR = str(self.tmpdir / 'tts_audio')
        self.cfg = copy.deepcopy(voice_mod.default_config)
        for hero, vid in (('沈知韫', 'fish:shen-id'), ('苏婉青', 'fish:su-id'), ('徐念薇', 'fish:wei-id')):
            self.cfg[hero]['voice'] = vid
        Path(voice_mod.CONFIG_FILE).write_text(json.dumps(self.cfg, ensure_ascii=False), encoding='utf-8')
        with voice_mod.TTS_STATE_LOCK:
            voice_mod.TTS_CACHE.clear()
            voice_mod.TTS_INFLIGHT.clear()
            voice_mod.TTS_CACHE_BYTES = 0
        voice_mod._record_fish_ok()
        self.client = voice_mod.app.test_client()
        self.net_guard = patch.object(voice_mod.requests, 'post', side_effect=AssertionError('禁止真实网络请求'))
        self.net_guard.start()

    def tearDown(self):
        self.net_guard.stop()
        voice_mod.CONFIG_FILE = self.old_cfg
        voice_mod.TTS_DISK_CACHE_DIR = self.old_disk
        voice_mod._record_fish_ok()
        self.temp.cleanup()

    def test_drama3_vs_s2_payload_liberation_for_all_three_heroines(self):
        # Switch tier to drama -> verify per-role Drama 3 profiles & clean payload without no-op fields
        r_tier = self.client.post('/api/voice_tier', headers={'X-Voice-Client': '1'}, json={'tier': 'drama'})
        self.assertEqual(r_tier.status_code, 200)
        captured = []

        def fake_fish(payload, tts_model, **_kwargs):
            captured.append((tts_model, dict(payload)))
            return b'ID3-drama3'

        with patch.object(voice_mod, '_fish_audio', side_effect=fake_fish):
            for hero, exp_temp, exp_top_p, exp_speed in (
                ('沈知韫', 0.94, 0.90, 1.00),
                ('苏婉青', 0.98, 0.93, 1.00),
                ('徐念薇', 0.92, 0.88, 1.02),
            ):
                res = self.client.post('/api/tts', json={'text': '[dry amusement] 你先坐。', 'speaker': hero})
                self.assertEqual(res.status_code, 200)
                model, payload = captured[-1]
                self.assertEqual(model, 'drama-3')
                self.assertEqual(payload['temperature'], exp_temp)
                self.assertEqual(payload['top_p'], exp_top_p)
                self.assertEqual(payload['prosody']['speed'], exp_speed)
                self.assertEqual(payload['prosody']['volume'], 0.0)
                self.assertFalse(payload['prosody']['normalize_loudness'])
                self.assertEqual(payload['latency'], 'normal')
                for forbidden in (
                    'chunk_length', 'min_chunk_length', 'condition_on_previous_chunks',
                    'early_stop_threshold', 'repetition_penalty', 'features',
                ):
                    self.assertNotIn(forbidden, payload, f'{hero} drama-3 must omit {forbidden}')

        # Switch back to free -> verify S2_ROLE_PROFILES & quality-guard restored for S2.1
        r_free = self.client.post('/api/voice_tier', headers={'X-Voice-Client': '1'}, json={'tier': 'free'})
        self.assertEqual(r_free.status_code, 200)
        with patch.object(voice_mod, '_fish_audio', side_effect=fake_fish):
            res = self.client.post('/api/tts', json={'text': '[warm teasing] 喝口茶。', 'speaker': '苏婉青'})
            self.assertEqual(res.status_code, 200)
            model, payload = captured[-1]
            self.assertEqual(model, 's2.1-pro-free')
            self.assertEqual(payload['temperature'], 0.84)
            self.assertEqual(payload['top_p'], 0.87)
            self.assertEqual(payload['prosody']['speed'], 0.99)
            self.assertEqual(payload.get('features'), ['quality-guard'])
            self.assertIn('chunk_length', payload)

    def test_subtext_directing_context_hint_and_phase2_voice_script_hook(self):
        captured = []

        def fake_fish(payload, tts_model, **_kwargs):
            captured.append((tts_model, dict(payload)))
            return b'ID3-subtext'

        with patch.object(voice_mod, '_fish_audio', side_effect=fake_fish):
            # 1. Drama 3 merges right-hand subtext into leading cue or prepends [hiding: ...]
            raw = '[soft, flustered] ｛哥，你别误会｜其实怕他看出手抖｝，我先回屋了。'
            res_d3 = self.client.post('/api/tts', json={'text': raw, 'voice': 'fish:su-id', 'tts_model': 'drama-3'})
            self.assertEqual(res_d3.status_code, 200)
            p_d3 = captured[-1][1]['text']
            self.assertIn('[soft, flustered; hiding: 其实怕他看出手抖]', p_d3)
            self.assertIn('哥，你别误会，我先回屋了。', p_d3)
            self.assertNotIn('｛', p_d3)
            self.assertNotIn('｜', p_d3)

            res_d3_bare = self.client.post('/api/tts', json={
                'text': '｛真没事｜怕他多想｝，先喝茶。',
                'voice': 'fish:su-id',
                'tts_model': 'drama-3',
            })
            self.assertEqual(res_d3_bare.status_code, 200)
            self.assertIn('[hiding: 怕他多想]', captured[-1][1]['text'])

            # 2. S2.1 speaks surface text only (never leaks subtext into spoken audio)
            res_s2 = self.client.post('/api/tts', json={'text': raw, 'voice': 'fish:su-id', 'tts_model': 's2.1-pro-free'})
            self.assertEqual(res_s2.status_code, 200)
            p_s2 = captured[-1][1]['text']
            self.assertNotIn('其实怕他看出手抖', p_s2)
            self.assertIn('哥，你别误会', p_s2)

            # 3. Phase 2 voice_script takes precedence over display text when supplied
            res_vs = self.client.post('/api/tts', json={
                'text': '画面显示用的干净台词。',
                'voice_script': '[sharp, biting] 专门给声优的独立剧本。[pause] 听懂了？',
                'voice': 'fish:wei-id',
                'tts_model': 'drama-3',
            })
            self.assertEqual(res_vs.status_code, 200)
            self.assertIn('专门给声优的独立剧本', captured[-1][1]['text'])
            self.assertNotIn('画面显示用的干净台词', captured[-1][1]['text'])

            # 4. context_hint fallback only fires on untagged Drama 3 lines
            res_hint = self.client.post('/api/tts', json={
                'text': '别站门口吹风。',
                'context_hint': '她侧身让开半步，指尖摩挲着茶杯',
                'voice': 'fish:shen-id',
                'tts_model': 'drama-3',
            })
            self.assertEqual(res_hint.status_code, 200)
            self.assertTrue(captured[-1][1]['text'].startswith('[acting cue: 她侧身让开半步，指尖摩挲着茶杯] '))

        # Edge also strips subtext cleanly
        with patch.object(voice_mod, '_edge_audio', return_value=b'edge-clean') as mock_edge:
            res_edge = self.client.post('/api/tts', json={'text': raw, 'voice': 'edge:zh-CN-XiaoxiaoNeural'})
            self.assertEqual(res_edge.status_code, 200)
            self.assertEqual(mock_edge.call_args.args[0], '哥，你别误会，我先回屋了。')

    def test_retake_bypasses_and_overwrites_memory_and_disk_cache(self):
        takes = iter([b'ID3-take-one', b'ID3-take-two'])

        def fake_fish(_payload, _model, **_kwargs):
            return next(takes)

        req = {'text': '[cool irony] 重录验证。', 'voice': 'fish:shen-id', 'tts_model': 'drama-3'}
        with patch.object(voice_mod, '_fish_audio', side_effect=fake_fish):
            r1 = self.client.post('/api/tts', json=req)
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r1.data, b'ID3-take-one')
            # Second normal call hits cache
            r1_hit = self.client.post('/api/tts', json=req)
            self.assertEqual(r1_hit.data, b'ID3-take-one')
            # Retake forces fresh synthesis & overwrites cache
            r2 = self.client.post('/api/tts', json={**req, 'retake': True})
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r2.headers.get('X-TTS-Retake'), '1')
            self.assertEqual(r2.data, b'ID3-take-two')
            # Subsequent normal call gets take-two from memory
            r2_mem = self.client.post('/api/tts', json=req)
            self.assertEqual(r2_mem.data, b'ID3-take-two')
            # Clear memory -> disk cache must also hold take-two
            with voice_mod.TTS_STATE_LOCK:
                voice_mod.TTS_CACHE.clear()
                voice_mod.TTS_CACHE_BYTES = 0
            r2_disk = self.client.post('/api/tts', json=req)
            self.assertEqual(r2_disk.data, b'ID3-take-two')

    def test_s2_degradation_and_chinese_antonym_safety(self):
        # [pause] -> [break], [long pause] -> [long-break], <forceful> -> [firm tone]
        degraded = voice_mod._degrade_drama3_for_s2(
            '[sharp, amused] 话说到这份上。[pause] <forceful>够了。</forceful>[long pause] 滚吧。'
        )
        self.assertIn('[break]', degraded)
        self.assertIn('[long-break]', degraded)
        self.assertIn('[firm tone] 够了。', degraded)
        self.assertNotIn('[pause]', degraded)

        # Pure English passes untouched; mixed & negation phrases never collide with low restrained voice
        norm_en = voice_mod._normalize_s2_chinese_aliases('[warm teasing, small laugh] 别躲了。')
        self.assertEqual(norm_en, '[warm teasing, small laugh] 别躲了。')

        norm_antonym = voice_mod._normalize_s2_chinese_aliases('[声音发涩破音，克制不住抖了一下] 别逼我。')
        self.assertNotIn('low restrained voice', norm_antonym)
        self.assertIn('voice cracking', norm_antonym)

        norm_mixed = voice_mod._normalize_s2_chinese_aliases('[icy authority, 压低声音] 过来。')
        self.assertIn('icy authority', norm_mixed)
        self.assertIn('hushed low voice', norm_mixed)

    def test_voice_design_endpoint_csrf_validation_and_proxy(self):
        self.assertEqual(
            self.client.post('/api/voice_design', json={'description': 'Warm alto', 'text': '你好，请进。'}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post('/api/voice_design', headers={'X-Voice-Client': '1'}, json={'description': '短', 'text': '短'}).status_code,
            400,
        )
        seen = []

        class FakeResp:
            status_code = 200
            def json(self):
                return {'candidates': [
                    {'id': 'cand-a', 'index': 0, 'audio_base64': 'UklGRAAA', 'sample_rate': 44100, 'duration_ms': 3800},
                ]}

        def fake_http_post(url, json=None, headers=None, timeout=None):
            seen.append((url, json, headers, timeout))
            return FakeResp()

        with patch.object(voice_mod, '_fish_http_post', side_effect=fake_http_post):
            res = self.client.post('/api/voice_design', headers={'X-Voice-Client': '1'}, json={
                'description': 'Crisp 24yo Chinese heiress voice, sharp wit with fragile tremor underneath',
                'text': '这事我管定了，你别插手。',
                'count': 4,
                'temperature': 0.92,
            })
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body['status'], 'success')
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['candidates'][0]['id'], 'cand-a')
        self.assertTrue(seen[0][0].endswith('/v1/voice-design'))
        self.assertEqual(seen[0][2]['model'], 'voice-design-1')
        self.assertEqual(seen[0][1]['count'], 4)

    def test_utf8_byte_efficiency_and_trimmed_phoneme_map(self):
        # Trimmed phoneme map must keep 沈知韫/徐承邺 but NOT inflate 董事长/徐家主宅
        phoneme_text = voice_mod._apply_fish_phonemes('董事长今天在徐家主宅见了沈知韫和徐承邺。')
        self.assertIn('沈知<|phoneme_start|>', phoneme_text)
        self.assertIn('徐承<|phoneme_start|>', phoneme_text)
        self.assertNotIn('董<|phoneme_start|>', phoneme_text)
        self.assertNotIn('主<|phoneme_start|>', phoneme_text)

        # Concise English cue costs fewer UTF-8 bytes than verbose Chinese director paragraph
        new_line = '[dry amusement] 董事长今天不在徐家主宅。[pause] 你找错人了。'
        old_line = '[强压着倦意，声音稳而微冷，带着上位者的克制] 董事长今天不在徐家主宅。[break] 你找错人了。'
        self.assertLess(
            len(voice_mod._apply_fish_phonemes(new_line).encode('utf-8')),
            len(old_line.encode('utf-8')),
        )

    def test_opening_blind_box_lines_clean_of_legacy_break_and_flat_tags(self):
        banned = ('[break]', '[低声克制]', '[清冷平淡]', '[声音轻柔]', '[沉稳从容]')
        self.assertGreaterEqual(len(blind_box.OPENING_LINES), 10)
        for key, line in blind_box.OPENING_LINES.items():
            for bad in banned:
                self.assertNotIn(bad, line, f'OPENING_LINES[{key}] must not contain legacy tag {bad}')

    def test_story_service_prewarm_prosody_and_adjacent_action_hint(self):
        svc = ss.StoryService.__new__(ss.StoryService)
        # 1. Peak desire/orgasm/tag boosts expressive_boost to 0.08 WITHOUT crushing speed
        self.assertEqual(
            svc._compute_prewarm_prosody('别再逼我了。', '苏婉青', {'panels': {'苏婉青': {'欲望': 90, '体力': 60}}}),
            {'expressive_boost': 0.08},
        )
        self.assertEqual(
            svc._compute_prewarm_prosody('[shaky breath] 停下来……', '徐念薇', {'panels': {'徐念薇': {'体力': 80}}}),
            {'expressive_boost': 0.08},
        )
        # 2. Moderate tension boosts expressive_boost to 0.04 WITHOUT speed_scale
        self.assertEqual(
            svc._compute_prewarm_prosody('[icy, sarcastic] 你倒是敢说。', '沈知韫', {'panels': {'沈知韫': {'体力': 90}}}),
            {'expressive_boost': 0.04},
        )
        # 3. Exhaustion (stam <= 15) is the only path applying speed_scale 0.95
        self.assertEqual(
            svc._compute_prewarm_prosody('好累。', '苏婉青', {'panels': {'苏婉青': {'体力': 15}}}),
            {'speed_scale': 0.95, 'expressive_boost': 0.08},
        )
        # 4. Adjacent same-speaker action yields cleaned context_hint; different speaker stops scan
        msgs = [
            {'kind': 'action', 'speaker': '沈知韫', 'text': '她把签字笔轻轻扣在文件夹上。'},
            {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '说完了？'},
            {'kind': 'action', 'speaker': '徐志北', 'text': '他往后退了半步。'},
            {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '站住。'},
        ]
        self.assertEqual(ss.StoryService._find_adjacent_action_hint(msgs, 1, '沈知韫'), '她把签字笔轻轻扣在文件夹上。')
        self.assertEqual(ss.StoryService._find_adjacent_action_hint(msgs, 3, '沈知韫'), '')


if __name__ == '__main__':
    unittest.main()

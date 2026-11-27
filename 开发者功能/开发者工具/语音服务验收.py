"""语音服务定向验收：使用工作区内临时目录与模拟接口，不调用外部语音服务。"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import copy
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT / '语音运行.py'
module = types.ModuleType('voice_service_verification')
module.__file__ = str(SOURCE)
exec(compile(SOURCE.read_text(encoding='utf-8'), str(SOURCE), 'exec'), module.__dict__)
module.FISH_API_KEY = 'test-placeholder'


class VoiceServiceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='voice-check-', dir=ROOT / '开发者功能' / '开发者工具')
        self.directory = Path(self.temp.name)
        self.old_config = module.CONFIG_FILE
        self.old_disk_cache = module.TTS_DISK_CACHE_DIR
        module.CONFIG_FILE = str(self.directory / 'voice_config.json')
        module.TTS_DISK_CACHE_DIR = str(self.directory / 'tts_audio')
        self.config = copy.deepcopy(module.default_config)
        Path(module.CONFIG_FILE).write_text(json.dumps(self.config, ensure_ascii=False), encoding='utf-8')
        with module.TTS_STATE_LOCK:
            module.TTS_CACHE.clear()
            module.TTS_INFLIGHT.clear()
            module.TTS_CACHE_BYTES = 0
        module._record_fish_ok()
        self.client = module.app.test_client()
        self.network = patch.object(module.requests, 'post', side_effect=AssertionError('禁止真实网络请求'))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        module.CONFIG_FILE = self.old_config
        module.TTS_DISK_CACHE_DIR = self.old_disk_cache
        module._record_fish_ok()
        self.temp.cleanup()

    def test_import_and_read_are_readonly(self):
        path = Path(module.CONFIG_FILE)
        original = path.read_bytes()
        module._initialize_config()
        module._load_config()
        self.assertEqual(path.read_bytes(), original)
        path.unlink()
        first = module._load_config()
        first['旁白']['voice_ids'].append('test')
        self.assertFalse(path.exists())
        self.assertEqual(module._load_config()['旁白']['voice_ids'], [])

    def test_damaged_config_is_never_overwritten(self):
        path = Path(module.CONFIG_FILE)
        for damaged in [b'{invalid', b'[]', b'{}', b'{"__settings__": 123}']:
            path.write_bytes(damaged)
            self.assertEqual(self.client.get('/api/config').status_code, 503)
            self.assertEqual(self.client.post('/api/config', json=self.config).status_code, 403)
            self.assertEqual(self.client.post('/api/config', json=self.config, headers={'X-Voice-Client': '1'}).status_code, 409)
            self.assertEqual(path.read_bytes(), damaged)

    def test_atomic_failure_preserves_original_and_cleans_temp(self):
        path = Path(module.CONFIG_FILE)
        original = path.read_bytes()
        with patch.object(module.os, 'replace', side_effect=OSError('simulated full storage')):
            result = self.client.post('/api/config', json=self.config, headers={'X-Voice-Client': '1'})
        self.assertEqual(result.status_code, 503)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.directory.glob('*.tmp')), [])

    def test_save_validates_and_preserves_future_fields(self):
        original = Path(module.CONFIG_FILE).read_bytes()
        for invalid in [None, {}, [], {'旁白': None}, {'__settings__': {}}]:
            self.assertEqual(self.client.post('/api/config', json=invalid, headers={'X-Voice-Client': '1'}).status_code, 400)
            self.assertEqual(Path(module.CONFIG_FILE).read_bytes(), original)
        self.config['__settings__']['future_setting'] = 'keep'
        self.config['旁白']['future_parameter'] = {'value': 4}
        self.config['旁白']['emotion'] = 'angry'
        result = self.client.post('/api/config', json=self.config, headers={'X-Voice-Client': '1'})
        self.assertEqual(result.status_code, 200)
        saved = json.loads(Path(module.CONFIG_FILE).read_text(encoding='utf-8'))
        self.assertEqual(saved['旁白']['emotion'], '')
        self.assertEqual(saved['旁白']['future_parameter'], {'value': 4})
        self.assertEqual(saved['__settings__']['future_setting'], 'keep')

    def test_public_files_allowlist(self):
        for path in ['/', '/admin', '/voice_client.js', '/data.json', '/存档/全局记忆库.txt', '/txt文件/image/徐志北/into.png']:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in ['/语音运行.py', '/voice_config.json', '/AGENTS.md', '/injection_core.py', '/txt文件/提示词.md', '/开发者功能/开发者工具/语音服务验收.py', '/.backup/data.json', '/../语音运行.py']:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_http_cache_reuses_only_matching_parameters(self):
        calls = []
        def fake_fish(payload, model, **_kwargs):
            calls.append((payload, model))
            return b'ID3-audio'
        request = {'text': '[whispers] 测试文字', 'voice': 'fish:test', 'tts_model': 's2.1-pro-free'}
        with patch.object(module, '_fish_audio', side_effect=fake_fish):
            for _ in range(2):
                result = self.client.post('/api/tts', json=request)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.data, b'ID3-audio')
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0]['text'], request['text'])
            self.assertEqual(calls[0][0]['latency'], 'balanced')
            self.assertEqual(calls[0][0]['chunk_length'], 180)
            self.client.post('/api/tts', json={**request, 'speed': 1.2})
            self.assertEqual(len(calls), 2)
            self.client.post('/api/tts', json={**request, 'tts_model': 's2.1-pro'})
            self.assertEqual(len(calls), 3)
        self.assertEqual(self.client.post('/api/tts', json={'text': ''}).status_code, 400)
        self.assertEqual(self.client.post('/api/tts', json={'text': '字' * 12001}).status_code, 413)

    def test_concurrent_identical_requests_share_one_generation(self):
        calls = []
        started, finish = threading.Event(), threading.Event()
        def produce():
            calls.append(True)
            started.set()
            self.assertTrue(finish.wait(2))
            return b'shared-audio'
        with ThreadPoolExecutor(max_workers=2) as workers:
            one = workers.submit(module._cached_tts, 'same-key', produce)
            self.assertTrue(started.wait(1))
            two = workers.submit(module._cached_tts, 'same-key', produce)
            finish.set()
            self.assertEqual(one.result(), b'shared-audio')
            self.assertEqual(two.result(), b'shared-audio')
        self.assertEqual(len(calls), 1)
        self.assertEqual(module.TTS_INFLIGHT, {})

    def test_failed_generation_can_retry_and_cache_is_bounded(self):
        def fail():
            raise module.TtsError('test failure')
        with self.assertRaises(module.TtsError):
            module._cached_tts('retry', fail)
        self.assertEqual(module._cached_tts('retry', lambda: b'ok'), b'ok')
        with patch.object(module, 'TTS_CACHE_MAX_BYTES', 8), patch.object(module, 'TTS_CACHE_MAX_ENTRIES', 2):
            for key in ['one', 'two', 'three']:
                module._cached_tts(key, lambda: b'1234')
            self.assertLessEqual(module.TTS_CACHE_BYTES, 8)
            self.assertLessEqual(len(module.TTS_CACHE), 2)

    def test_disk_cache_prefetch_and_429_cooldown(self):
        # 1. Disk cache hit survives full memory cache clear.
        calls = []
        done = threading.Event()
        def fake_fish(payload, model, **_kwargs):
            calls.append(payload['text'])
            done.set()
            return b'ID3-disk-cached'
        with patch.object(module, '_fish_audio', side_effect=fake_fish):
            r1 = self.client.post('/api/tts', json={'text': '磁盘缓存测试', 'speaker': '沈知韫'})
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(len(calls), 1)
            with module.TTS_STATE_LOCK:
                module.TTS_CACHE.clear()
                module.TTS_CACHE_BYTES = 0
            r2 = self.client.post('/api/tts', json={'text': '磁盘缓存测试', 'speaker': '沈知韫'})
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r2.data, b'ID3-disk-cached')
            self.assertEqual(len(calls), 1, 'Disk LRU cache must satisfy request without re-calling Fish')

            # 2. /api/tts/prefetch enforces X-Voice-Client CSRF and warms cache with identical key.
            self.assertEqual(self.client.post('/api/tts/prefetch', json={'items': []}).status_code, 403)
            done.clear()
            pf = self.client.post('/api/tts/prefetch', headers={'X-Voice-Client': '1'}, json={
                'items': [{'text': '预热这一句', 'speaker': '沈知韫'}]
            })
            self.assertEqual(pf.status_code, 202)
            self.assertEqual(pf.get_json()['scheduled'], 1)
            self.assertTrue(done.wait(2.0), 'Background prefetch thread should synthesize item')
            time.sleep(0.05)
            r3 = self.client.post('/api/tts', json={'text': '预热这一句', 'speaker': '沈知韫'})
            self.assertEqual(r3.status_code, 200)
            self.assertEqual(len(calls), 2, 'Live /api/tts must hit exact prewarmed cache key')

            # 3. 429 cooldown pauses background prewarm cleanly.
            module._record_fish_429()
            self.assertTrue(module._in_fish_429_cooldown())
            pf_cool = self.client.post('/api/tts/prefetch', headers={'X-Voice-Client': '1'}, json={
                'items': [{'text': '冷却期间不预热', 'speaker': '沈知韫'}]
            })
            self.assertEqual(pf_cool.status_code, 202)
            self.assertEqual(pf_cool.get_json()['scheduled'], 0)
            self.assertTrue(pf_cool.get_json()['cooldown'])

    def test_edge_tags_and_fish_failures(self):
        with patch.object(module, '_edge_audio', return_value=b'edge-audio') as edge:
            result = self.client.post('/api/tts', json={'text': '[低声] 测试', 'voice': 'edge:test'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(edge.call_args.args[0], '测试')
        class FakeResponse:
            status_code = 200
            content = b'{"error":"not audio"}'
            headers = {'Content-Type': 'application/json'}
            def close(self):
                pass
        with patch.object(module.requests, 'post', return_value=FakeResponse()):
            with self.assertRaises(module.TtsError):
                module._fish_audio({'text': 'test'}, 's2.1-pro')
        with patch.object(module.requests, 'post', side_effect=module.requests.Timeout()):
            result = self.client.post('/api/tts', json={'text': 'timeout test', 'voice': 'fish:test'})
            self.assertEqual(result.status_code, 504)

    def test_drama3_directing_params_header_and_s2_alias_mapping(self):
        captured = []
        def fake_fish_audio(payload, tts_model, on_chunk=None, api_key=None):
            captured.append((tts_model, dict(payload)))
            return b'fake-mp3-audio'

        with patch.object(module, '_fish_audio', side_effect=fake_fish_audio):
            # 1. Drama 3 keeps director brief + paired XML tags, omits S2-only/no-op params
            #    (chunk_length, min_chunk_length, condition_on_previous_chunks, early_stop_threshold, repetition_penalty),
            #    defaults quality-guard OFF, lifts legacy <0.80/<0.82 to >=0.92/>=0.88, and returns X-Fish-Model header.
            r_d3 = self.client.post('/api/tts', json={
                'text': '[icy authority, restrained] 账得<slow>先算清楚</slow>。[pause] <whisper>别声张。</whisper>',
                'voice': 'fish:test',
                'tts_model': 'drama-3',
                'temperature': 0.58,
                'top_p': 0.68,
                'chunk_length': 180,
                'latency': 'balanced',
            })
            self.assertEqual(r_d3.status_code, 200)
            self.assertEqual(r_d3.headers.get('X-Fish-Model'), 'drama-3')
            m_d3, p_d3 = captured[-1]
            self.assertEqual(m_d3, 'drama-3')
            self.assertIn('[icy authority, restrained]', p_d3['text'])
            self.assertIn('<slow>先算清楚</slow>', p_d3['text'])
            self.assertIn('<whisper>别声张。</whisper>', p_d3['text'])
            for omitted in ('chunk_length', 'min_chunk_length', 'condition_on_previous_chunks',
                            'early_stop_threshold', 'repetition_penalty', 'features'):
                self.assertNotIn(omitted, p_d3)
            self.assertEqual(p_d3['latency'], 'normal')
            self.assertGreaterEqual(p_d3['temperature'], 0.92)
            self.assertGreaterEqual(p_d3['top_p'], 0.88)

            # 1b. raw_params=True preserves legacy low temperature/top_p for A/B blind testing.
            r_raw = self.client.post('/api/tts', json={
                'text': '[低声克制] 旧参数对照组。',
                'voice': 'fish:test',
                'tts_model': 'drama-3',
                'temperature': 0.68,
                'top_p': 0.75,
                'quality_guard': True,
                'raw_params': True,
            })
            self.assertEqual(r_raw.status_code, 200)
            _, p_raw = captured[-1]
            self.assertEqual(p_raw['temperature'], 0.68)
            self.assertEqual(p_raw['top_p'], 0.75)
            self.assertEqual(p_raw.get('features'), ['quality-guard'])

            # 2. Non-Drama-3 (s2.1-pro-free) degrades [pause]->[break], XML->S2 tags, maps Chinese aliases,
            #    passes English cues through untouched, and prevents antonym collision on 克制不住.
            r_s2 = self.client.post('/api/tts', json={
                'text': '[低声, 微颤] 别再问了。[pause] <whisper>回房睡吧。</whisper>',
                'voice': 'fish:test',
                'tts_model': 's2.1-pro-free',
            })
            self.assertEqual(r_s2.status_code, 200)
            self.assertEqual(r_s2.headers.get('X-Fish-Model'), 's2.1-pro-free')
            m_s2, p_s2 = captured[-1]
            self.assertEqual(m_s2, 's2.1-pro-free')
            self.assertNotIn('<whisper>', p_s2['text'])
            self.assertNotIn('</whisper>', p_s2['text'])
            self.assertIn('[break]', p_s2['text'])
            self.assertIn('[low restrained voice, voice trembling]', p_s2['text'])
            self.assertIn('[whispering] 回房睡吧。', p_s2['text'])

            # 2b. English cue passthrough + antonym-safe Chinese mapping on S2.1.
            r_s2_antonym = self.client.post('/api/tts', json={
                'text': '[sharp, amused] 你觉得呢？[声音发涩破音，克制不住低下来] 别碰我！',
                'voice': 'fish:test',
                'tts_model': 's2.1-pro-free',
            })
            self.assertEqual(r_s2_antonym.status_code, 200)
            _, p_s2_ant = captured[-1]
            self.assertIn('[sharp, amused]', p_s2_ant['text'])
            self.assertNotIn('low restrained voice', p_s2_ant['text'])
            self.assertIn('voice cracking', p_s2_ant['text'])

            # 2c. Physiological prosody modulation adjusts temperature/top_p up to 1.00/0.95 without forcing slowdown.
            r_pros = self.client.post('/api/tts', json={
                'text': '慢一点，别这么急。',
                'voice': 'fish:test',
                'tts_model': 'drama-3',
                'speed': 1.0,
                'temperature': 0.94,
                'top_p': 0.90,
                'speed_scale': 0.95,
                'expressive_boost': 0.08,
            })
            self.assertEqual(r_pros.status_code, 200)
            _, p_pros = captured[-1]
            self.assertEqual(p_pros['prosody']['speed'], 0.95)
            self.assertEqual(p_pros['temperature'], 1.0)
            self.assertEqual(p_pros['top_p'], 0.95)

        # 3. VOICE_TIERS['drama'] routes all 3 heroines to drama-3 while keeping narrator free,
        #    and DRAMA3_ROLE_PROFILES / S2_ROLE_PROFILES differentiate all 3 heroines.
        self.assertEqual(module.VOICE_TIERS['drama']['heroine_model'], 'drama-3')
        self.assertEqual(module.VOICE_TIERS['drama']['narrator_model'], 's2.1-pro-free')
        self.assertEqual(set(module.VOICED_HEROINES), {'沈知韫', '苏婉青', '徐念薇'})
        self.assertEqual(module.DRAMA3_ROLE_PROFILES['苏婉青']['temperature'], 0.98)
        self.assertEqual(module.DRAMA3_ROLE_PROFILES['徐念薇']['speed'], 1.02)
        self.assertFalse(module.DRAMA3_ROLE_PROFILES['沈知韫']['quality_guard'])

    def test_drama3_subtext_context_hint_retake_and_voice_design(self):
        captured = []
        counter = {'n': 0}
        def fake_fish_audio(payload, tts_model, on_chunk=None, api_key=None):
            counter['n'] += 1
            captured.append((tts_model, dict(payload)))
            return f'ID3-take-{counter["n"]}'.encode('utf-8')

        with patch.object(module, '_fish_audio', side_effect=fake_fish_audio):
            # 1. Subtext auto-directing: Drama 3 merges '; hiding: ...' into existing leading tag or prepends [hiding: ...]; S2 speaks surface only.
            line_sub = '[composed] ｛没事，只是有点累｜手心都在发凉，怕他再追问｝。'
            r_d3 = self.client.post('/api/tts', json={'text': line_sub, 'voice': 'fish:test', 'tts_model': 'drama-3'})
            self.assertEqual(r_d3.status_code, 200)
            _, p_d3 = captured[-1]
            self.assertIn('[composed; hiding: 手心都在发凉，怕他再追问]', p_d3['text'])
            self.assertIn('没事，只是有点累', p_d3['text'])
            self.assertNotIn('｛', p_d3['text'])

            r_d3_bare = self.client.post('/api/tts', json={
                'text': '｛没事，不用担心｜其实紧张极了｝。',
                'voice': 'fish:test',
                'tts_model': 'drama-3',
            })
            self.assertEqual(r_d3_bare.status_code, 200)
            self.assertIn('[hiding: 其实紧张极了]', captured[-1][1]['text'])

            r_s2 = self.client.post('/api/tts', json={'text': line_sub, 'voice': 'fish:test', 'tts_model': 's2.1-pro-free'})
            self.assertEqual(r_s2.status_code, 200)
            _, p_s2 = captured[-1]
            self.assertNotIn('手心都在发凉', p_s2['text'])
            self.assertIn('没事，只是有点累', p_s2['text'])

            # 2. context_hint applies ONLY to untagged Drama 3 lines; ignored when line already has [...].
            r_ctx_plain = self.client.post('/api/tts', json={
                'text': '把文件放下。',
                'voice': 'fish:test',
                'tts_model': 'drama-3',
                'context_hint': '她指节发白，合上文件夹',
            })
            self.assertEqual(r_ctx_plain.status_code, 200)
            self.assertTrue(captured[-1][1]['text'].startswith('[acting cue: 她指节发白，合上文件夹] '))

            r_ctx_tagged = self.client.post('/api/tts', json={
                'text': '[cool irony] 把文件放下。',
                'voice': 'fish:test',
                'tts_model': 'drama-3',
                'context_hint': '她指节发白，合上文件夹',
            })
            self.assertEqual(r_ctx_tagged.status_code, 200)
            self.assertNotIn('acting cue:', captured[-1][1]['text'])

            # 3. retake=True bypasses & overwrites memory + disk cache cleanly with X-TTS-Retake header.
            req_take = {'text': '[warm teasing] 重录测试台词。', 'voice': 'fish:test', 'tts_model': 'drama-3'}
            t1 = self.client.post('/api/tts', json=req_take)
            t1_cached = self.client.post('/api/tts', json=req_take)
            self.assertEqual(t1.data, t1_cached.data)
            t2 = self.client.post('/api/tts', json={**req_take, 'retake': True})
            self.assertEqual(t2.status_code, 200)
            self.assertEqual(t2.headers.get('X-TTS-Retake'), '1')
            self.assertNotEqual(t2.data, t1.data)
            # Clear memory cache -> disk cache must return new take t2.data
            with module.TTS_STATE_LOCK:
                module.TTS_CACHE.clear()
                module.TTS_CACHE_BYTES = 0
            t2_disk = self.client.post('/api/tts', json=req_take)
            self.assertEqual(t2_disk.data, t2.data)

        # 4. POST /api/voice_design enforces X-Voice-Client CSRF, validates inputs, and proxies model=voice-design-1.
        self.assertEqual(
            self.client.post('/api/voice_design', json={'description': 'warm female', 'text': '你好世界试音'}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post('/api/voice_design', headers={'X-Voice-Client': '1'}, json={'description': 'a', 'text': 'b'}).status_code,
            400,
        )
        design_calls = []
        class FakeDesignResp:
            status_code = 200
            def json(self):
                return {'candidates': [
                    {'id': 'c0', 'index': 0, 'audio_base64': 'UklGRg==', 'sample_rate': 44100, 'duration_ms': 4200},
                    {'id': 'c1', 'index': 1, 'audio_base64': 'UklGRh==', 'sample_rate': 44100, 'duration_ms': 4500},
                ]}
        def fake_post(url, json=None, headers=None, timeout=None):
            design_calls.append((url, json, headers, timeout))
            return FakeDesignResp()
        with patch.object(module, '_fish_http_post', side_effect=fake_post):
            vd = self.client.post(
                '/api/voice_design',
                headers={'X-Voice-Client': '1'},
                json={'description': 'Composed 38yo Chinese female CEO with dry warmth', 'text': '把合同拿进来，放在桌上。', 'count': 3},
            )
        self.assertEqual(vd.status_code, 200)
        vd_body = vd.get_json()
        self.assertEqual(vd_body['count'], 2)
        self.assertTrue(design_calls[0][0].endswith('/v1/voice-design'))
        self.assertEqual(design_calls[0][2]['model'], 'voice-design-1')
        self.assertEqual(design_calls[0][1]['count'], 3)

    def test_local_ambient_audio_assets(self):
        # Isolate BASE_DIR to temp workspace with txt文件/audio/ambient/
        audio_base = self.directory / 'txt文件' / 'audio'
        (audio_base / 'ambient').mkdir(parents=True, exist_ok=True)
        (audio_base / 'ambient' / 'rain_night.ogg').write_bytes(b'OggS-RAIN-AMBIENT')
        (audio_base / 'ambient' / 'calm_home.mp3').write_bytes(b'ID3-CALM-AMBIENT')
        (audio_base / 'ambient' / 'secret.txt').write_text('blocked', encoding='utf-8')

        old_base = module.BASE_DIR
        module.BASE_DIR = str(self.directory)
        module._AUDIO_ASSETS_CACHE.clear()
        try:
            # 1. GET /api/audio_assets discovers ambient tracks only
            res = self.client.get('/api/audio_assets')
            self.assertEqual(res.status_code, 200)
            info = res.get_json()
            self.assertIn('rain_night', info['ambient'])
            self.assertIn('calm_home', info['ambient'])
            self.assertNotIn('sfx', info)
            self.assertNotIn('samples', info)
            self.assertNotIn('prologues_count', info)

            # 2. Static audio serving allows whitelisted audio extensions and blocks non-audio / traversal
            self.assertEqual(self.client.get('/txt文件/audio/ambient/rain_night.ogg').data, b'OggS-RAIN-AMBIENT')
            self.assertEqual(self.client.get('/txt文件/audio/ambient/calm_home.mp3').data, b'ID3-CALM-AMBIENT')
            self.assertEqual(self.client.get('/txt文件/audio/ambient/secret.txt').status_code, 404)
            self.assertEqual(self.client.get('/txt文件/audio/../voice_config.json').status_code, 404)
        finally:
            module.BASE_DIR = old_base
            module._AUDIO_ASSETS_CACHE.clear()

    def test_protagonist_and_action_voice_routing_and_inheritance(self):
        # 1. /api/voice_routing enforces X-Voice-Client and updates routing atomically
        self.assertEqual(self.client.post('/api/voice_routing', json={'protagonist_voice_enabled': True}).status_code, 403)
        self.assertEqual(
            self.client.post('/api/voice_routing', headers={'X-Voice-Client': '1'}, json={'action_voice_mode': 'bad'}).status_code,
            400,
        )
        res = self.client.post(
            '/api/voice_routing',
            headers={'X-Voice-Client': '1'},
            json={'protagonist_voice_enabled': True, 'action_voice_mode': 'separate', 'action_voice_scope': 'heroines'},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body['routing'], {
            'protagonist_voice_enabled': True,
            'action_voice_mode': 'separate',
            'action_voice_scope': 'heroines',
        })

        # 2. /api/voice_tier keeps 旁白 / 动作 / 徐志北 on s2.1-pro-free and applies DRAMA3_ROLE_PROFILES to 3 heroines
        tier_res = self.client.post('/api/voice_tier', headers={'X-Voice-Client': '1'}, json={'tier': 'drama'})
        self.assertEqual(tier_res.status_code, 200)
        tcfg = tier_res.get_json()['config']
        for h in ('沈知韫', '苏婉青', '徐念薇'):
            self.assertEqual(tcfg[h]['tts_model'], 'drama-3')
            self.assertEqual(tcfg[h]['temperature'], module.DRAMA3_ROLE_PROFILES[h]['temperature'])
            self.assertEqual(tcfg[h]['quality_guard'], False)
        for r in ('旁白', '动作', '徐志北'):
            self.assertEqual(tcfg[r]['tts_model'], 's2.1-pro-free')

        # 3. 动作 with empty voice inherits 旁白 Fish voice ID while keeping 动作 speed (1.03) and volume (-1.5)
        cfg = module._load_config()
        cfg['旁白']['voice'] = 'fish:narrator-id-123'
        cfg['动作']['voice'] = ''
        module._save_config(cfg)
        captured = []
        def fake_fish(payload, tts_model, **_kwargs):
            captured.append((tts_model, dict(payload)))
            return b'ID3-action-fish'
        with patch.object(module, '_fish_audio', side_effect=fake_fish):
            r_act = self.client.post('/api/tts', json={'text': '她把茶杯放回桌面。', 'speaker': '动作'})
            self.assertEqual(r_act.status_code, 200)
            self.assertEqual(captured[-1][0], 's2.1-pro-free')
            self.assertEqual(captured[-1][1]['reference_id'], 'narrator-id-123')
            self.assertEqual(captured[-1][1]['prosody']['speed'], 1.03)
            self.assertEqual(captured[-1][1]['prosody']['volume'], -1.5)

        # 4. 动作 inherits Edge voice when 旁白 uses edge: with distinct Edge prosody (+0% / -2Hz / -10%)
        cfg2 = module._load_config()
        cfg2['旁白'] = {'voice': 'edge:zh-CN-YunyangNeural', 'rate': '-8%', 'pitch': '-4Hz', 'volume': '+0%', 'emotion': ''}
        cfg2['动作']['voice'] = ''
        module._save_config(cfg2)
        with patch.object(module, '_edge_audio', return_value=b'ID3-action-edge') as mock_edge:
            r_edge = self.client.post('/api/tts', json={'text': '他合上文件。', 'speaker': '动作'})
            self.assertEqual(r_edge.status_code, 200)
            self.assertEqual(mock_edge.call_args.args[1], 'zh-CN-YunyangNeural')
            self.assertEqual(mock_edge.call_args.args[2], '+0%')
            self.assertEqual(mock_edge.call_args.args[4], '-10%')

        # 5. StoryService._trigger_tts_prewarm matches voice_config routing, tension expressive_boost (no speed crush), & context_hint
        import story_service as ss
        warmed = []
        svc = ss.StoryService.__new__(ss.StoryService)
        svc.root = self.directory
        svc._tts_prewarmer = lambda items: warmed.extend(items)
        svc._stream_lock = threading.Lock()
        svc._prewarmed_keys = set()
        vcfg_for_svc = {
            '__settings__': {
                'protagonist_voice_enabled': True,
                'action_voice_mode': 'separate',
                'action_voice_scope': 'all',
            },
            '旁白': {'voice': 'fish:narr123'},
            '动作': {'voice': ''},
            '徐志北': {'voice': 'fish:male123'},
            '沈知韫': {'voice': 'fish:shen123'},
        }
        (self.directory / 'voice_config.json').write_text(json.dumps(vcfg_for_svc, ensure_ascii=False), encoding='utf-8')
        svc._trigger_tts_prewarm([
            {'kind': 'action', 'speaker': '沈知韫', 'text': '她放下钢笔，指尖轻敲桌面。'},
            {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '<whisper>别声张。</whisper>'},
            {'kind': 'dialogue', 'speaker': '徐志北', 'text': '妈，趁热喝。'},
        ], dedup_prefix='test-warm')
        self.assertEqual(len(warmed), 3)
        self.assertEqual(warmed[0]['speaker'], '动作')
        self.assertEqual(warmed[1]['speaker'], '沈知韫')
        self.assertNotIn('speed_scale', warmed[1])
        self.assertEqual(warmed[1]['expressive_boost'], 0.08)
        self.assertEqual(warmed[1].get('context_hint'), '她放下钢笔，指尖轻敲桌面。')
        self.assertEqual(warmed[2]['speaker'], '徐志北')
        # Moderate tension cue gets 0.04 boost without speed_scale; exhaustion (stam <= 15) is the sole path lowering speed_scale to 0.95
        self.assertEqual(svc._compute_prewarm_prosody('[sharp, dry] 坐下。', '沈知韫', {}), {'expressive_boost': 0.04})
        exhausted = svc._compute_prewarm_prosody('别碰了。', '沈知韫', {'panels': {'沈知韫': {'体力': 12}}})
        self.assertEqual(exhausted, {'speed_scale': 0.95, 'expressive_boost': 0.08})


if __name__ == '__main__':
    protected = ['voice_config.json', 'data.json', '存档/全局记忆库.txt', 'injection_core.py']
    before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in protected}
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(VoiceServiceChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in protected}
    assert before == after, '受保护文件发生变化'
    print('受保护文件 SHA-256 一致；外部语音调用：0')
    raise SystemExit(0 if result.wasSuccessful() else 1)

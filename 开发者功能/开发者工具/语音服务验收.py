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
            # 1. Drama 3 keeps Chinese director brief + paired XML tags, omits repetition_penalty,
            #    raises chunk_length>=280 & normal latency & expressive temperature, and returns X-Fish-Model header.
            r_d3 = self.client.post('/api/tts', json={
                'text': '[强压着倦意，声音稳而微冷] 账得<slow>先算清楚</slow>。[break] <whisper>别声张。</whisper>',
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
            self.assertIn('[强压着倦意，声音稳而微冷]', p_d3['text'])
            self.assertIn('<slow>先算清楚</slow>', p_d3['text'])
            self.assertIn('<whisper>别声张。</whisper>', p_d3['text'])
            self.assertNotIn('repetition_penalty', p_d3)
            self.assertGreaterEqual(p_d3['chunk_length'], 280)
            self.assertEqual(p_d3['latency'], 'normal')
            self.assertGreaterEqual(p_d3['temperature'], 0.70)
            self.assertGreaterEqual(p_d3['top_p'], 0.76)

            # 2. Non-Drama-3 (s2.1-pro-free) strips XML paired tags and maps standard Chinese short aliases.
            r_s2 = self.client.post('/api/tts', json={
                'text': '[低声, 微颤] 别再问了，<whisper>回房睡吧。</whisper>',
                'voice': 'fish:test',
                'tts_model': 's2.1-pro-free',
            })
            self.assertEqual(r_s2.status_code, 200)
            self.assertEqual(r_s2.headers.get('X-Fish-Model'), 's2.1-pro-free')
            m_s2, p_s2 = captured[-1]
            self.assertEqual(m_s2, 's2.1-pro-free')
            self.assertNotIn('<whisper>', p_s2['text'])
            self.assertNotIn('</whisper>', p_s2['text'])
            self.assertIn('[low restrained voice, voice trembling]', p_s2['text'])

        # 3. VOICE_TIERS['drama'] routes all 3 heroines to drama-3 while keeping narrator free.
        self.assertEqual(module.VOICE_TIERS['drama']['heroine_model'], 'drama-3')
        self.assertEqual(module.VOICE_TIERS['drama']['narrator_model'], 's2.1-pro-free')
        self.assertEqual(set(module.VOICED_HEROINES), {'沈知韫', '苏婉青', '徐念薇'})


if __name__ == '__main__':
    protected = ['voice_config.json', 'data.json', '存档/全局记忆库.txt', 'injection_core.py']
    before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in protected}
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(VoiceServiceChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in protected}
    assert before == after, '受保护文件发生变化'
    print('受保护文件 SHA-256 一致；外部语音调用：0')
    raise SystemExit(0 if result.wasSuccessful() else 1)

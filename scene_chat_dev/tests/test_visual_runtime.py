"""Automated verification suite for Concept 4+ Text-First Editorial Cinema & Visual Runtime.
Verifies micro_states/minor_npcs parsing, visual asset auto-discovery & mtime replacement priority,
Flask static image cache headers & dotfile/traversal guards, and frontend DOM-ID/CSS integrity.
"""
import importlib.util
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import interaction_runtime as ir
import round_runtime as rr
import 存档清理器 as cleaner


def _load_voice_server():
    spec = importlib.util.spec_from_file_location('voice_server_test_mod', REPO / '语音运行.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VisualRuntimeTests(unittest.TestCase):
    def test_parse_micro_states_normal_and_malformed(self):
        base = ir.parse_micro_states(cleaner.INITIAL_GLOBAL_MEMORY)
        for name in ('沈知韫', '苏婉青', '徐念薇'):
            self.assertIn(name, base)
            self.assertIsInstance(base[name], dict)
            self.assertFalse(any(base[name].values()))

        custom_mem = (
            '【当前激活微状态】\n'
            '▶ 沈知韫\n'
            'residual_tension: true | confusion_debt: false | momentary_ease: false\n'
            '▶ 苏婉青\n'
            'residual_tension: false | confusion_debt: true | momentary_ease: false\n'
            '▶ 徐念薇\n'
            'residual_tension: false | confusion_debt: false | momentary_ease: true\n'
        )
        parsed = ir.parse_micro_states(custom_mem)
        self.assertTrue(parsed['沈知韫']['residual_tension'])
        self.assertFalse(parsed['沈知韫']['confusion_debt'])
        self.assertTrue(parsed['苏婉青']['confusion_debt'])
        self.assertTrue(parsed['徐念薇']['momentary_ease'])

        malformed = '【当前激活微状态】\n▶ 未知角色\nresidual_tension: true\n'
        fallback = ir.parse_micro_states(malformed)
        self.assertEqual(set(fallback.keys()), {'沈知韫', '苏婉青', '徐念薇'})
        self.assertFalse(any(any(v.values()) for v in fallback.values()))

    def test_scan_visual_assets_discovers_repo_scenes_and_characters(self):
        assets = ir.scan_visual_assets(REPO)
        scenes = assets['scenes']
        chars = assets['characters']

        expected_scenes = {
            '徐家主宅': {'night', 'day'},
            '市中心顶层公寓': {'night', 'day'},
            '公司': {'day'},
            '大学': {'day'},
            '工作室': {'night', 'day'},
        }
        for place, slots in expected_scenes.items():
            self.assertIn(place, scenes, f'Missing scene location: {place}')
            for slot in slots:
                self.assertIn(slot, scenes[place], f'Missing slot {slot} for {place}')
                url = scenes[place][slot]
                self.assertTrue(url.startswith('/txt文件/image/scenes/'))
                self.assertRegex(url, r'\?v=\d+$')
                self.assertNotIn('.nomedia', url)

        for hero in ('沈知韫', '苏婉青', '徐念薇'):
            self.assertIn(hero, chars)
            self.assertTrue({'into', 'fullbody', 'fullbody2'}.issubset(chars[hero].keys()))
        self.assertIn('徐志北', chars)
        self.assertIn('into', chars['徐志北'])
        self.assertNotIn('徐承邺', chars)

    def test_scan_visual_assets_prefers_newer_mtime_across_extensions(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix='visual-scan-test-'))
        try:
            scenes_dir = tmp / 'txt文件' / 'image' / 'scenes'
            scenes_dir.mkdir(parents=True)
            (scenes_dir / '.nomedia').write_text('', encoding='utf-8')

            old_webp = scenes_dir / '徐家主宅_night.webp'
            old_webp.write_bytes(b'RIFFxxxxWEBP')
            os.utime(old_webp, (1700000000, 1700000000))

            new_png = scenes_dir / '徐家主宅_night.png'
            new_png.write_bytes(b'\x89PNG\r\n\x1a\n')
            os.utime(new_png, (1700000500, 1700000500))

            # Equal mtime prefers higher extension priority (.webp > .png)
            eq_png = scenes_dir / '公司_day.png'
            eq_webp = scenes_dir / '公司_day.webp'
            eq_png.write_bytes(b'\x89PNG')
            eq_webp.write_bytes(b'RIFF')
            os.utime(eq_png, (1700000200, 1700000200))
            os.utime(eq_webp, (1700000200, 1700000200))

            # User adds optional mood portrait and custom NPC portrait
            shen_dir = tmp / 'txt文件' / 'image' / '沈知韫'
            shen_dir.mkdir(parents=True)
            (shen_dir / 'mood_blush.jpg').write_bytes(b'\xff\xd8\xff')
            xu_dir = tmp / 'txt文件' / 'image' / '徐承邺'
            xu_dir.mkdir(parents=True)
            (xu_dir / 'into.webp').write_bytes(b'RIFF')

            assets = ir.scan_visual_assets(tmp)
            night_url = assets['scenes']['徐家主宅']['night']
            self.assertIn(urllib.parse.quote('徐家主宅_night.png', safe=''), night_url)
            self.assertTrue(night_url.endswith('?v=1700000500'))

            day_url = assets['scenes']['公司']['day']
            self.assertIn(urllib.parse.quote('公司_day.webp', safe=''), day_url)

            self.assertIn('mood_blush', assets['characters']['沈知韫'])
            self.assertIn('into', assets['characters']['徐承邺'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_view_exposes_visual_runtime_fields(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix='visual-view-test-'))
        try:
            for rel in (
                'save_store.py',
                'injection_core.py',
                'round_runtime.py',
                'interaction_runtime.py',
                'story_progression.py',
                'story_compiler.py',
            ):
                shutil.copy2(REPO / rel, tmp / rel)
            shutil.copytree(REPO / 'txt文件', tmp / 'txt文件')
            for rel, content in cleaner.TEMPLATES.items():
                p = tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding='utf-8')
            (tmp / 'data.json').write_text('{}', encoding='utf-8')

            store = rr.RoundStore(tmp)
            v = ir.view(store)
            self.assertIn('micro_states', v)
            self.assertIn('delivered_items', v)
            self.assertIn('visual_assets', v)
            self.assertIn('徐家主宅', v['visual_assets']['scenes'])
            self.assertIn('沈知韫', v['visual_assets']['characters'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flask_image_cache_headers_and_security(self):
        mod = _load_voice_server()
        client = mod.app.test_client()

        with client.get('/txt文件/image/scenes/徐家主宅_night.webp') as resp_img:
            self.assertEqual(resp_img.status_code, 200)
            self.assertEqual(resp_img.headers.get('Cache-Control'), 'public, max-age=86400')
            self.assertTrue(resp_img.data.startswith(b'RIFF'))
            self.assertIn(b'WEBP', resp_img.data[:16])

        for path in ('/', '/story_client.js', '/story_client.css'):
            with client.get(path) as resp:
                self.assertEqual(resp.status_code, 200, path)
                self.assertEqual(resp.headers.get('Cache-Control'), 'no-cache', path)

        with client.get('/txt文件/image/scenes/.nomedia') as resp_hidden:
            self.assertEqual(resp_hidden.status_code, 404)

        with client.get('/txt文件/image/../../语音运行.py') as resp_trav:
            self.assertEqual(resp_trav.status_code, 404)

    def test_frontend_dom_ids_css_braces_and_contracts(self):
        html = (REPO / 'main_template.html').read_text(encoding='utf-8')
        css = (REPO / 'story_client.css').read_text(encoding='utf-8')
        js = (REPO / 'story_client.js').read_text(encoding='utf-8')

        self.assertEqual(css.count('{'), css.count('}'))

        html_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', html))
        js_ids = set(re.findall(r'(?<![A-Za-z0-9_])\$\(\s*[\'"]([A-Za-z0-9_-]+)[\'"]\s*\)', js))
        self.assertGreater(len(js_ids), 100)
        self.assertEqual(sorted(js_ids - html_ids), [])

        for required_token in (
            'cinemaPlates',
            'readingDof',
            'topPeekDrawer',
            'gazeLens',
            'sideFocusCard',
            'bracketChips',
            'no-avatar',
        ):
            self.assertIn(required_token, js, f'Missing Concept 4+ contract token: {required_token}')

        # User explicitly rejected redundant bubble-style dual switch
        self.assertNotIn('bubbleStyle', js)

    def test_frontend_runtime_renders_real_live_snapshot_without_error(self):
        import json
        import subprocess

        tmp = pathlib.Path(tempfile.mkdtemp(prefix='visual-js-e2e-'))
        try:
            for rel in (
                'save_store.py',
                'injection_core.py',
                'round_runtime.py',
                'interaction_runtime.py',
                'story_progression.py',
                'story_compiler.py',
            ):
                shutil.copy2(REPO / rel, tmp / rel)
            shutil.copytree(REPO / 'txt文件', tmp / 'txt文件')
            for rel, content in cleaner.TEMPLATES.items():
                p = tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding='utf-8')
            (tmp / 'data.json').write_text('{}', encoding='utf-8')

            world = ir.view(rr.RoundStore(tmp))
            self.assertIn('physiology', world)
            self.assertIn('沈知韫', world['physiology'])
            # Simulate active dict buffs (the exact Python shape that broke Array.some) + physiology state
            world['buffs']['沈知韫'] = [{'name': '体液锁定', 'turns': 18, 'effect': '测试效果'}]
            world['physiology']['沈知韫'].update({
                'cycle_phase': '危险期',
                'pregnancy_stage': 'latent',
                'latent_days_left': 2,
                'creampie_count': 1,
                'unrelieved_streak': 1,
                'masturbation_trace': 2,
                'fluid_lock_turns': 18,
                'fluid_lock_floor': 85,
            })
            world['cast'] = ['沈知韫']

            live_payload = {
                'revision': 'rev-1',
                'save_epoch': 'epoch-1',
                'world': world,
                'playback': {'segment_id': 'seg-1', 'revealed': 6, 'total': 6, 'completed': True, 'bootstrap': False},
                'history': [
                    {
                        'id': 'seg-1',
                        'location': '徐家主宅',
                        'input': '（轻轻合上书房门）晚上好。',
                        'input_kind': 'action',
                        'selection': {'segment_id': '', 'option_id': 'A'},
                        'messages': [
                            {'kind': 'narration', 'speaker': '', 'text': '壁灯映着雨夜长廊，滚烫的余温里她指尖轻颤。'},
                            {'kind': 'action', 'speaker': '沈知韫', 'text': '她｛表面端庄地合上账册｜腿根却因濡湿而暗暗绷紧｝。'},
                            {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '[whisper] 这么晚还没睡？'},
                            {'kind': 'dialogue', 'speaker': '徐承邺', 'text': '哥，书房的灯怎么还亮着。'},
                            {'kind': 'dialogue', 'speaker': '林秘书', 'text': '沈总，文件已经放桌上了。'},
                            {'kind': 'dialogue', 'speaker': '临时司机', 'text': '车已经停在正门外。'},
                        ],
                        'decision': {
                            'prompt': '此刻你打算？',
                            'options': [
                                {'id': 'A', 'text': '顺口寒暄几句'},
                                {'id': 'B', 'text': '走近沈知韫递茶'},
                                {'id': 'C', 'text': '直接扣住她的手腕'},
                            ],
                        },
                    }
                ],
                'has_older': False,
                'bridge_connected': False,
                'bridge': {},
                'task': None,
            }

            harness = r"""
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(process.argv[2], 'utf8');
const js = fs.readFileSync(process.argv[3], 'utf8');
const payload = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const voiceJs = fs.readFileSync(process.argv[5], 'utf8');

class ClassList {
  constructor(el) { this.el = el; this.set = new Set(); }
  add(...xs) { xs.forEach(x => x && this.set.add(x)); this._sync(); }
  remove(...xs) { xs.forEach(x => this.set.delete(x)); this._sync(); }
  toggle(x, force) {
    if (force === undefined) { if (this.set.has(x)) this.set.delete(x); else this.set.add(x); }
    else if (force) this.set.add(x);
    else this.set.delete(x);
    this._sync();
  }
  contains(x) { return this.set.has(x); }
  _sync() { this.el._className = [...this.set].join(' '); }
}

class Elem {
  constructor(tag, id = '') {
    this.tagName = String(tag || 'div').toUpperCase();
    this.id = id;
    this.dataset = {};
    this.style = { setProperty() {} };
    this.attributes = {};
    this.children = [];
    this.parentElement = null;
    this.classList = new ClassList(this);
    this.hidden = false;
    this.disabled = false;
    this.open = false;
    this.value = '';
    this.textContent = '';
    this.scrollTop = 0;
    this.scrollHeight = 400;
    this.clientHeight = 400;
    this.listeners = {};
  }
  get className() { return this._className || ''; }
  set className(v) {
    this.classList.set = new Set(String(v || '').split(/\s+/).filter(Boolean));
    this._className = [...this.classList.set].join(' ');
  }
  get childElementCount() { return this.children.length; }
  get options() { return this.children; }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'class') this.className = v; }
  getAttribute(k) { return this.attributes[k] ?? null; }
  removeAttribute(k) { delete this.attributes[k]; }
  pause() {}
  play() { return Promise.resolve(); }
  load() {}
  append(...nodes) {
    for (const n of nodes) {
      if (n && typeof n === 'object') { n.parentElement = this; this.children.push(n); }
    }
  }
  insertBefore(n, ref) {
    if (n && typeof n === 'object') { n.parentElement = this; this.children.unshift(n); }
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() {}
  focus() {}
  scrollTo() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  setSelectionRange() {}
  cloneNode() { return new Elem(this.tagName); }
  getBoundingClientRect() { return { top: 0, bottom: 100, height: 100, width: 300, left: 0, right: 300 }; }
  addEventListener(ev, fn) { (this.listeners[ev] ||= []).push(fn); }
  closest() { return this; }
  _walk(pred, out = []) {
    for (const c of this.children) {
      if (pred(c)) out.push(c);
      if (c._walk) c._walk(pred, out);
    }
    return out;
  }
  querySelectorAll(sel) {
    if (sel.startsWith('.')) {
      const cls = sel.slice(1);
      return this._walk(c => c.classList && c.classList.contains(cls));
    }
    if (sel === 'button') return this._walk(c => c.tagName === 'BUTTON');
    return [];
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

const byId = new Map();
for (const m of html.matchAll(/\bid=["']([^"']+)["']/g)) {
  if (!byId.has(m[1])) byId.set(m[1], new Elem('div', m[1]));
}
const docEl = new Elem('html');
const bodyEl = new Elem('body');
const storage = new Map();

const sandbox = {
  console, setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
  requestAnimationFrame: fn => fn(),
  cancelAnimationFrame: () => {},
  URL: { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} },
  Blob: class {},
  location: { origin: 'http://127.0.0.1:5000', href: 'http://127.0.0.1:5000/' },
  navigator: { vibrate: () => {} },
  innerHeight: 800,
  matchMedia: () => ({ matches: false }),
  addEventListener: () => {},
  removeEventListener: () => {},
  localStorage: {
    getItem: k => storage.has(k) ? storage.get(k) : null,
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: k => storage.delete(k),
  },
  document: {
    hidden: false,
    documentElement: docEl,
    body: bodyEl,
    getElementById: id => byId.get(id) || null,
    createElement: tag => new Elem(tag),
    createElementNS: (_ns, tag) => new Elem(tag),
    createTextNode: txt => ({ nodeType: 3, textContent: String(txt) }),
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: () => {},
  },
  fetch: async url => {
    if (String(url).startsWith('/api/story/live')) {
      return { ok: true, status: 200, json: async () => payload, text: async () => JSON.stringify(payload) };
    }
    return { ok: true, status: 200, json: async () => ({}), text: async () => '{}' };
  },
  EventSource: undefined,
  AbortController,
  Headers: typeof Headers !== 'undefined' ? Headers : class {},
  Response: typeof Response !== 'undefined' ? Response : class {},
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

const ctx = vm.createContext(sandbox);
vm.runInContext(voiceJs, ctx);
vm.runInContext(js, ctx);
setTimeout(() => {
  const statusEl = byId.get('status');
  const statusText = (statusEl && statusEl.textContent) || '';
  if (statusEl && statusEl.classList.contains('error')) {
    console.error('RUNTIME_ERROR_IN_STATUS:', statusText);
    process.exit(2);
  }
  const msgs = byId.get('messages').children;
  const plates = msgs.filter(c => c.classList.contains('cinema-plate'));
  const noAvatars = msgs.filter(c => c.classList.contains('no-avatar'));
  const avatarMsgs = msgs.filter(c => c.classList.contains('msg') && !c.classList.contains('no-avatar') && !c.classList.contains('narration'));
  const badImgs = byId.get('cast')._walk(c => c.tagName === 'IMG' && String(c.src || '').includes(encodeURIComponent('徐承邺')));
  if (plates.length < 2) { console.error('EXPECTED_PLATES>=2, got', plates.length); process.exit(3); }
  if (noAvatars.length !== 3) { console.error('EXPECTED_NO_AVATAR=3 (徐承邺/林秘书/临时司机), got', noAvatars.length); process.exit(4); }
  if (avatarMsgs.length < 2) { console.error('EXPECTED_AVATAR_MSGS>=2 (徐志北/沈知韫), got', avatarMsgs.length); process.exit(5); }
  if (badImgs.length !== 0) { console.error('UNEXPECTED_404_IMG_FOR_XUCHENGYE'); process.exit(6); }
  // Exercise Top Peek Drawer toggle & bracket chip insert
  const gazePill = byId.get('hudCast').querySelector('.hud-gaze-pill');
  if (!gazePill || !gazePill.onclick) { console.error('MISSING_HUD_GAZE_PILL'); process.exit(7); }
  gazePill.onclick();
  if (!byId.get('topPeekDrawer').classList.contains('is-open')) { console.error('PEEK_DRAWER_DID_NOT_OPEN'); process.exit(8); }
  gazePill.onclick();
  const chips = byId.get('bracketChips').querySelectorAll('button');
  if (chips.length < 2) { console.error('MISSING_BRACKET_CHIPS'); process.exit(9); }
  chips[0].onclick();
  if (!byId.get('input').value.includes('（）')) { console.error('BRACKET_CHIP_FAILED'); process.exit(10); }
  if (docEl.dataset.mood !== 'intimate') { console.error('EXPECTED_INTIMATE_MOOD_FROM_DICT_BUFF, got', docEl.dataset.mood); process.exit(11); }
  const dossierBtn = noAvatars[0].querySelector('.msg-micro-btn');
  if (dossierBtn && dossierBtn.listeners.click && dossierBtn.listeners.click[0]) {
    dossierBtn.listeners.click[0]({ stopPropagation() {} });
    if (!byId.get('gazeLens').classList.contains('is-open')) { console.error('GAZE_LENS_DID_NOT_OPEN_FOR_NPC'); process.exit(12); }
  }
  const fluidSpans = byId.get('messages')._walk(c => c.classList && c.classList.contains('fx-fluid'));
  const spasmSpans = byId.get('messages')._walk(c => c.classList && c.classList.contains('fx-spasm'));
  const rubyNodes = byId.get('messages')._walk(c => c.classList && c.classList.contains('subtext-ruby'));
  const latentChips = byId.get('messages')._walk(c => c.classList && c.classList.contains('is-latent'));
  if (fluidSpans.length < 1) { console.error('EXPECTED_FX_FLUID_SPAN'); process.exit(13); }
  if (spasmSpans.length < 1) { console.error('EXPECTED_FX_SPASM_SPAN'); process.exit(14); }
  if (rubyNodes.length < 1) { console.error('EXPECTED_ACTION_SUBTEXT_RUBY'); process.exit(15); }
  if (latentChips.length < 1) { console.error('EXPECTED_LATENT_PREGNANCY_CHIP'); process.exit(16); }
  // Action vs Dialogue visual separation: non-player .msg.action must NOT render large .avatar, must render .action-mini-avatar
  const npcActionMsgs = msgs.filter(c => c.classList.contains('msg') && c.classList.contains('action') && !c.classList.contains('player'));
  if (npcActionMsgs.length < 1) { console.error('EXPECTED_NPC_ACTION_MSG'); process.exit(17); }
  if (npcActionMsgs.some(m => m.querySelector('.avatar'))) { console.error('UNEXPECTED_LARGE_AVATAR_ON_ACTION'); process.exit(18); }
  if (!npcActionMsgs[0].querySelector('.action-mini-avatar')) { console.error('EXPECTED_ACTION_MINI_AVATAR'); process.exit(19); }
  if (!byId.get('stageCurtain')) { console.error('MISSING_STAGE_CURTAIN'); process.exit(20); }
  if (!byId.get('storySettlementThinkingMode')) { console.error('MISSING_SETTLEMENT_THINKING_MODE'); process.exit(21); }
  console.log('JS_E2E_OK', JSON.stringify({
    mood: docEl.dataset.mood,
    plates: plates.length,
    noAvatars: noAvatars.length,
    avatarMsgs: avatarMsgs.length,
    npcActionMsgs: npcActionMsgs.length,
    chips: chips.length,
    fluidSpans: fluidSpans.length,
    spasmSpans: spasmSpans.length,
    rubyNodes: rubyNodes.length,
  }));
}, 80);
"""
            payload_file = tmp / 'live.json'
            payload_file.write_text(json.dumps(live_payload, ensure_ascii=False), encoding='utf-8')
            harness_file = tmp / 'harness.js'
            harness_file.write_text(harness, encoding='utf-8')

            proc = subprocess.run(
                ['node', str(harness_file), str(REPO / 'main_template.html'), str(REPO / 'story_client.js'), str(payload_file), str(REPO / 'voice_client.js')],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(proc.returncode, 0, f'Node E2E failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}')
            self.assertIn('JS_E2E_OK', proc.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()

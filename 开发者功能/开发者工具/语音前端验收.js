/* 定向验收：模拟网络与音频资源，检查取消、超时、资源上限和管理页离线初始化。 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert').strict;
const root = path.resolve(__dirname, '..', '..');
const clientSource = fs.readFileSync(path.join(root, 'voice_client.js'), 'utf8');
const managerSource = fs.readFileSync(path.join(root, 'voice_manager.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}
function response(body, status = 200, type = 'application/json') {
    return { ok: status >= 200 && status < 300, status,
        headers: { get: () => type }, json: async () => body, blob: async () => new Blob([body], { type }) };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function makeContext(fetcher) {
    let sequence = 0;
    const revoked = [];
    const context = vm.createContext({ console, setTimeout, clearTimeout, AbortController, DOMException, Blob,
        URL: { createObjectURL: () => 'blob:test-' + (++sequence), revokeObjectURL: url => revoked.push(url) },
        fetch: fetcher, globalThis: null });
    context.globalThis = context;
    vm.runInContext(clientSource, context);
    return { context, client: context.VoiceClient, revoked };
}
async function run() {
    let pending = [];
    const { client, revoked, context } = makeContext((url, options) => new Promise((resolve, reject) => {
        pending.push({ resolve, reject, signal: options.signal });
        options.signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError')), { once: true });
    }));
    const body = client.buildPayload('[whispers] 测试', { voice: 'fish:test', temperature: 0, volume: 0, min_chunk_length: 0, tts_model: 's2.1-pro-free' });
    assert.equal(body.temperature, 0); assert.equal(body.volume, 0); assert.equal(body.min_chunk_length, 0);
    assert.equal(body.text, '[whispers] 测试'); assert.equal(body.tts_model, 's2.1-pro-free');
    const first = client.requestAudio(body, { channel: 'test' }).catch(error => error);
    const second = client.requestAudio(body, { channel: 'test' });
    assert.equal(pending[0].signal.aborted, true);
    pending[1].resolve(response('audio', 200, 'audio/mpeg'));
    assert.equal((await first).name, 'AbortError'); assert.equal((await second).size, 5);
    const timeout = await client.requestAudio(body, { channel: 'timeout', timeoutMs: 5 }).catch(error => error);
    assert.equal(timeout.name, 'TimeoutError');
    const failure = client.requestAudio(body, { channel: 'failure' }).catch(error => error);
    pending[pending.length - 1].resolve(response({ error: '配置读取失败，原文件已保留。' }, 503));
    assert.match((await failure).message, /原文件已保留/);
    const store = new client.AudioUrlStore(3, 12);
    const pinned = store.add(new Blob(['1234'])); store.pin(pinned);
    for (let i = 0; i < 20; i++) store.add(new Blob(['1234']));
    assert.ok(store.entries.size <= 3); assert.ok(store.bytes <= 12); assert.ok(store.has(pinned));
    assert.ok(revoked.length >= 18); store.clear(); assert.equal(store.entries.size, 0);
    console.log('PASS shared client: payload, cancellation, timeout, error feedback, bounded URL release');

    const remote = deferred();
    const saved = deferred();
    const elements = new Map();
    function element(id) {
        if (!elements.has(id)) elements.set(id, { textContent: '', disabled: false, classList: { toggle() {} }, replaceChildren() {}, append() {} });
        return elements.get(id);
    }
    const config = { __settings__: { fish_tts_model: 's2.1-pro' }, 旁白: { voice: 'fish:sample', tts_model: 's2.1-pro-free', temperature: 0.58 }, default: { voice: 'fish:' } };
    const manager = makeContext((url, options = {}) => {
        if (url === '/api/config' && options.method === 'POST') return saved.promise;
        if (url === '/api/config') return Promise.resolve(response(config));
        if (url === '/api/voices' || url === '/api/edge_voices') return remote.promise;
        return Promise.resolve(response({ items: [] }));
    }).context;
    manager.window = manager;
    manager.addEventListener = () => {};
    manager.document = { getElementById: element, querySelectorAll: () => [], querySelector: () => null, activeElement: null,
        createElement: () => ({ append() {}, classList: { toggle() {} } }) };
    manager.alert = () => {}; manager.confirm = () => false;
    vm.runInContext(managerSource, manager);
    vm.runInContext('var renders=0; renderEditor=()=>{renders++;updateSaveState();}; refreshEditorPreservingDraft=()=>{};', manager);
    await tick();
    assert.equal(vm.runInContext('configReady', manager), true);
    assert.equal(vm.runInContext('renders', manager), 1);
    assert.equal(element('save-all-button').disabled, false);
    remote.resolve(response({ voices: [] })); await tick();
    const saving = vm.runInContext('configData["旁白"].speed=0.9; saveAllConfig();', manager);
    saved.resolve(response({ error: '存储不可写' }, 503)); await saving;
    assert.equal(vm.runInContext('isDirty()', manager), true);
    assert.match(element('manager-status').textContent, /存储不可写/);
    console.log('PASS manager: local config renders while remote pending; failed save remains dirty');

    const sentHeaders = [];
    const csrfCtx = makeContext((url, options = {}) => {
        sentHeaders.push({ url, method: options.method || 'GET', headers: options.headers || {}, body: options.body || '' });
        if (url === '/api/fish_key' && options.method === 'POST') return Promise.resolve(response({ ok: true, configured: true, masked: 'sk-****1234' }));
        if (url === '/api/fish_key' && options.method === 'DELETE') return Promise.resolve(response({ ok: true, configured: false }));
        if (url === '/api/voice_tier' && options.method === 'POST') return Promise.resolve(response({ ok: true, voice_tier: 'pro' }));
        return Promise.resolve(response({ configured: false }));
    });
    const defaultPayload = csrfCtx.client.buildPayload('测试文本', { voice: 'fish:abc' }, {}, '', '沈知韫');
    assert.equal(defaultPayload.tts_model, 's2.1-pro-free');
    assert.equal(defaultPayload.speaker, '沈知韫');
    assert.equal(defaultPayload.language, 'zh-CN');
    assert.equal(defaultPayload.latency, 'balanced');
    assert.equal(defaultPayload.chunk_length, 180);
    assert.equal(defaultPayload.quality_guard, true);
    await csrfCtx.client.saveFishKey('test-key-12345678', false);
    await csrfCtx.client.setVoiceTier('pro');
    await csrfCtx.client.prefetchBatch([{ text: '预热测试', speaker: '沈知韫' }]);
    await csrfCtx.client.clearFishKey();
    assert.ok(sentHeaders.some(r => r.url === '/api/tts/prefetch' && r.headers['X-Voice-Client'] === '1'), 'prefetchBatch must hit /api/tts/prefetch with X-Voice-Client');
    assert.ok(sentHeaders.every(r => r.headers['X-Voice-Client'] === '1'), 'X-Voice-Client header required on all key/tier/prefetch calls');
    console.log('PASS voice_client: s2.1-pro-free + balanced/180 default, prefetchBatch, speaker passthrough, key/tier APIs & X-Voice-Client');

    const storySource = fs.readFileSync(path.join(root, 'story_client.js'), 'utf8');
    const stripFn = storySource.match(/function stripVoiceTags\([\s\S]*?\n  \}/)[0];
    const allowBlock = storySource.match(/const VOICED_SPEAKERS = [\s\S]*?function resolveVoiceSpeaker\([\s\S]*?\n  \}/)[0];
    const whisperFn = storySource.match(/function isWhisperLine\([\s\S]*?\n  \}/)[0];
    const storyCtx = vm.createContext({});
    vm.runInContext(stripFn + '\n' + allowBlock + '\n' + whisperFn, storyCtx);
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'narration', speaker: '', text: '雨停了。' }), '旁白');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '沈知韫', text: '过来。' }), '沈知韫');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '苏婉青', text: '先坐吧。' }), '苏婉青');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐念薇', text: '进来。' }), '徐念薇');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '沈知韫', text: '她放下笔。' }), '旁白');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐志北', text: '怎么了？' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐志北', text: '他走近一步。' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐承邺', text: '妈！' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐承邺', text: '他推开门。' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '顾律师', text: '沈董您好。' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '主宅管家', text: '他轻敲房门。' }), '');
    assert.equal(
        storyCtx.stripVoiceTags('沈知<|phoneme_start|>yun4<|phoneme_end|>韫[low restrained voice]<whisper>低声</whisper><chinese>问好</chinese>'),
        '沈知韫低声问好'
    );
    assert.equal(storyCtx.isWhisperLine('<whisper>别出声</whisper>'), true);
    assert.equal(storyCtx.isWhisperLine('[低声] 过来'), true);
    assert.equal(storyCtx.isWhisperLine('普通对话'), false);
    assert.match(storySource, /name === '苏婉青' && loc === '市中心顶层公寓'/);
    assert.match(storySource, /name === '沈知韫' \|\| name === '徐念薇'.*loc === '徐家主宅'/);
    assert.match(storySource, /3:\s*'目击锁定'.*4:\s*'实锤'/);
    assert.match(storySource, /=== '徐家主宅'/);
    const mainHtml = fs.readFileSync(path.join(root, 'main_template.html'), 'utf8');
    assert.equal((mainHtml.match(/<\/html>/gi) || []).length, 1, 'main_template.html should have exactly one closing </html>');
    console.log('PASS story_client & main_template: 4-speaker allowlist, stripVoiceTags, isHome lock, discLabels 0..4, HTML integrity');
    console.log('All frontend checks passed; external requests: 0');
}
run().catch(error => { console.error(error.stack); process.exitCode = 1; });

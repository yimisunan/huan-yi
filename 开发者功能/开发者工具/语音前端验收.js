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
    console.log('All frontend checks passed; external requests: 0');
}
run().catch(error => { console.error(error.stack); process.exitCode = 1; });

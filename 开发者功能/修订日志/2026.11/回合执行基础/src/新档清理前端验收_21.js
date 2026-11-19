/* Epoch changes run against the real story client with isolated DOM/storage/network. */
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const cases = [];
const model = { key: 'test-model', model_id: 'test', provider_name: 'isolated', pricing_configured: false };
const action = '旧档行动';
const pending = { request_id: 'page-old', action, base_revision: 'old', model_key: model.key };
const oldEpoch = 'a'.repeat(32), newEpoch = 'b'.repeat(32);
const state = epoch => ({ task: null, bridge_connected: true, bridge_model: model, story_protocol: 3,
    ...(epoch === undefined ? {} : { save_epoch: epoch }) });
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r)); };

function setup(cache) {
    const queue = [], calls = [], nodes = new Map(), intervals = [];
    let stored = JSON.stringify(cache);
    class Node {
        constructor() { this.children = []; this.events = {}; this.value = ''; this.dataset = {}; this.isConnected = true;
            this.classList = { toggle() {}, add() {}, remove() {} }; }
        set id(v) { this._id = v; nodes.set(v, this); }
        get id() { return this._id; }
        append(...items) { this.children.push(...items); }
        replaceChildren(...items) { this.children = items; }
        addEventListener(name, fn) { this.events[name] = fn; }
        setAttribute() {}
        focus() {}
        showModal() { this.open = true; }
        close() { this.open = false; }
    }
    const body = new Node();
    const document = { body, hidden: false, activeElement: body, createElement: () => new Node(),
        createElementNS: () => new Node(), getElementById: id => nodes.get(id) || null,
        querySelectorAll: () => [], addEventListener() {} };
    const context = { document, window: {}, localStorage: { getItem: () => stored, setItem: (_, value) => { stored = value; } },
        AbortController, crypto: { randomUUID: () => 'new-action' }, setTimeout: () => 1, clearTimeout() {},
        setInterval: fn => intervals.push(fn), fetch: async (url, options) => {
            const next = queue.shift(); assert.ok(next, url); assert.equal(url, '/api/story/' + next.path);
            calls.push({ path: next.path, method: options.method, body: options.body });
            return { ok: true, status: 200, json: async () => next.data };
        } };
    vm.createContext(context); vm.runInContext(source, context);
    const reply = (path, data) => queue.push({ path, data });
    const all = node => [node, ...node.children.flatMap(all)];
    return { calls, reply, cache: () => JSON.parse(stored), nodes,
        async start(epoch) { reply('snapshot', { ...state(epoch), revision: 'current' }); await context.window.StoryPage.start(async () => -1); },
        async send() { all(body).find(n => n.textContent === '重试原行动').events.click(); await flush(); },
        async poll() { intervals[0](); await flush(); } };
}

async function test(name, fn) {
    try { await fn(); cases.push({ name, status: 'PASS' }); }
    catch (error) { cases.push({ name, status: 'FAIL', error: error.stack }); }
}

(async () => {
    await test('new_epoch_clears_legacy_pending_and_progress', async () => {
        const h = setup({ pending, draft: action, progress: { revision: 'old', index: 2 }, settlement: { revision: 'old' },
            rewardSeen: 'old', errorShown: 'old', acceptedModel: model.key });
        await h.start(newEpoch);
        const cache = h.cache();
        assert.equal(cache.pending, undefined); assert.equal(cache.draft, undefined);
        assert.equal(cache.settlement, undefined); assert.equal(cache.rewardSeen, undefined); assert.equal(cache.errorShown, undefined);
        assert.equal(cache.progress.revision, 'current'); assert.equal(cache.acceptedModel, model.key);
        assert.equal(cache.saveEpoch, newEpoch); assert.equal(h.nodes.get('story-action-input').value, '');
    });
    await test('legacy_server_keeps_existing_pending', async () => {
        const h = setup({ pending, draft: action }); await h.start(undefined);
        assert.deepEqual(h.cache().pending, pending); assert.equal(h.cache().saveEpoch, 'legacy');
    });
    await test('same_epoch_preserves_draft_and_pending', async () => {
        const h = setup({ saveEpoch: oldEpoch, pending, draft: action }); await h.start(oldEpoch);
        assert.deepEqual(h.cache().pending, pending); assert.equal(h.cache().draft, action);
    });
    await test('epoch_change_during_send_never_posts_old_action', async () => {
        const h = setup({ saveEpoch: oldEpoch, pending, draft: action }); await h.start(oldEpoch);
        h.reply('tasks', state(newEpoch)); h.reply('snapshot', { ...state(newEpoch), revision: 'new' }); await h.send();
        assert.ok(h.calls.every(call => call.method === 'GET')); assert.equal(h.cache().pending, undefined);
        assert.equal(h.cache().progress.revision, 'new');
    });
    await test('epoch_change_in_poll_reloads_snapshot', async () => {
        const h = setup({ saveEpoch: oldEpoch, draft: action }); await h.start(oldEpoch);
        h.reply('tasks', state(newEpoch)); h.reply('snapshot', { ...state(newEpoch), revision: 'new' }); await h.poll();
        assert.equal(h.cache().saveEpoch, newEpoch); assert.equal(h.cache().draft, undefined);
        assert.equal(h.calls.at(-1).path, 'snapshot');
    });
    console.log(JSON.stringify({ cases, passed: cases.filter(c => c.status === 'PASS').length, failed: cases.filter(c => c.status !== 'PASS').length }));
    process.exitCode = cases.some(c => c.status !== 'PASS') ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
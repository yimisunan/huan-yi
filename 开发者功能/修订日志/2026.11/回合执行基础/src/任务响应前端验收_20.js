/* Run the real story client in an isolated DOM adapter; no production requests. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const results = [];
const model = { key: 'test-model', model_id: 'test', provider_name: 'isolated', pricing_configured: false };
const pending = { request_id: 'page-isolated-original', action: '核对桌上材料', base_revision: 'isolated-revision', model_key: model.key };
const status = task => ({ task, bridge_connected: true, bridge_model: model, story_protocol: 3 });
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise(resolve => setImmediate(resolve)); };

function harness(hasPending = true) {
    const nodes = new Map(), intervals = [], queue = [], calls = [];
    let stored = JSON.stringify({ ...(hasPending ? { pending: { ...pending } } : {}), draft: pending.action, acceptedModel: model.key });
    class Element {
        constructor(tag) {
            this.tagName = tag; this.children = []; this.events = {}; this.value = ''; this.open = false;
            this.hidden = false; this.disabled = false; this.dataset = {}; this.isConnected = true;
            this.classList = { toggle() {}, add() {}, remove() {} };
        }
        set id(value) { this._id = value; nodes.set(value, this); }
        get id() { return this._id; }
        append(...children) { this.children.push(...children); }
        replaceChildren(...children) { this.children = children; }
        setAttribute() {}
        addEventListener(name, fn) { this.events[name] = fn; }
        focus() {}
        showModal() { this.open = true; }
        close() { this.open = false; }
    }
    const body = new Element('body');
    const document = { body, hidden: false, activeElement: body, createElement: tag => new Element(tag),
        createElementNS: (_, tag) => new Element(tag), getElementById: id => nodes.get(id) || null,
        querySelectorAll: () => [], addEventListener() {} };
    const context = { document, window: {}, localStorage: { getItem: () => stored, setItem: (_, value) => { stored = value; } },
        AbortController, crypto: { randomUUID: () => 'isolated-new' }, console,
        setTimeout: () => 1, clearTimeout() {}, setInterval: fn => { intervals.push(fn); return 1; },
        fetch: async (url, options) => {
            const next = queue.shift();
            assert.ok(next, 'unexpected request: ' + url);
            assert.equal(url, '/api/story/' + next.path);
            calls.push({ path: next.path, method: options.method, body: options.body ? JSON.parse(options.body) : null });
            return { status: next.code, ok: next.code >= 200 && next.code < 300,
                json: async () => {
                    if (next.abort) { const error = new Error('aborted'); error.name = 'AbortError'; throw error; }
                    return JSON.parse(next.raw);
                } };
        } };
    vm.createContext(context);
    vm.runInContext(source, context, { filename: 'story_client.js' });
    const reply = (path, code, data, raw = false) => queue.push({ path, code, raw: raw ? data : JSON.stringify(data) });
    const descendants = node => [node, ...node.children.flatMap(child => descendants(child))];
    return { reply, queue, calls, nodes, cache: () => JSON.parse(stored),
        text: () => nodes.get('story-action-status').textContent,
        async start() { reply('snapshot', 200, { ...status(null), revision: 'isolated-revision' }); await context.window.StoryPage.start(async () => -1); },
        async poll() { intervals[0](); await flush(); },
        async retry() { descendants(body).find(n => n.textContent === '重试原行动').events.click(); await flush(); },
        async choose() { context.window.StoryPage.choose(pending.action); await flush(); } };
}

async function test(name, fn) {
    try { await fn(); results.push({ name, status: 'PASS' }); }
    catch (error) { results.push({ name, status: 'FAIL', error: error.stack }); }
}

(async () => {
    await test('html404_poll_continues_and_original_request_retries', async () => {
        const h = harness(); await h.start();
        h.reply('tasks/' + pending.request_id, 404, '<!doctype html><title>Not Found</title>', true);
        h.reply('tasks', 200, status(null)); await h.poll();
        assert.equal(h.calls.at(-1).path, 'tasks');
        assert.deepEqual(h.cache().pending, pending);
        assert.ok(!h.text().includes('Unexpected token'));
        h.reply('tasks', 200, status(null));
        h.reply('tasks', 200, { task: { ...pending, status: 'queued' } }); await h.retry();
        assert.deepEqual(h.calls.at(-1).body, pending);
        assert.equal(h.calls.at(-1).method, 'POST');
        assert.equal(h.cache().pending, undefined);
        assert.equal(h.cache().draft, pending.action);
    });
    await test('json404_poll_compatibility', async () => {
        const h = harness(); await h.start();
        h.reply('tasks/' + pending.request_id, 404, { error: 'missing', status: 404 });
        h.reply('tasks', 200, status(null)); await h.poll();
        assert.equal(h.calls.at(-1).path, 'tasks'); assert.deepEqual(h.cache().pending, pending);
    });
    for (const code of [403, 500]) await test('html' + code + '_keeps_status_and_pending', async () => {
        const h = harness(); await h.start();
        h.reply('tasks/' + pending.request_id, code, '<!doctype html><title>Error</title>', true); await h.poll();
        assert.ok(h.text().includes('HTTP ' + code)); assert.deepEqual(h.cache().pending, pending);
    });
    for (const raw of ['<!doctype html>', 'null', '[]']) await test('invalid_success_' + raw.slice(0, 8), async () => {
        const h = harness(); await h.start();
        h.reply('tasks/' + pending.request_id, 200, raw, true); await h.poll();
        assert.ok(h.text().includes('无效数据')); assert.deepEqual(h.cache().pending, pending);
    });
    await test('json409_error_message_preserved', async () => {
        const h = harness(); await h.start();
        h.reply('tasks/' + pending.request_id, 409, { error: '隔离版本冲突' }); await h.poll();
        assert.equal(h.text(), '隔离版本冲突'); assert.deepEqual(h.cache().pending, pending);
    });
    await test('response_body_abort_uses_timeout_message', async () => {
        const h = harness(); await h.start();
        h.queue.push({ path: 'tasks/' + pending.request_id, code: 200, abort: true }); await h.poll();
        assert.ok(h.text().includes('连接超时')); assert.deepEqual(h.cache().pending, pending);
    });
    await test('accepted_submission_preserves_payload_shape', async () => {
        const h = harness(false); await h.start();
        h.reply('tasks', 200, status(null));
        h.reply('tasks', 200, { task: { ...pending, request_id: 'page-isolated-new', status: 'queued' } }); await h.choose();
        const body = h.calls.at(-1).body;
        assert.equal(body.request_id, 'page-isolated-new'); assert.equal(body.action, pending.action);
        assert.equal(body.base_revision, pending.base_revision); assert.equal(body.model_key, model.key);
    });
    await test('post409_keeps_action_for_manual_retry', async () => {
        const h = harness(false); await h.start();
        h.reply('tasks', 200, status(null)); h.reply('tasks', 409, { error: '隔离冲突请重试' }); await h.choose();
        assert.equal(h.cache().pending, undefined); assert.equal(h.cache().draft, pending.action);
        assert.equal(h.text(), '隔离冲突请重试');
    });
    console.log(JSON.stringify({ cases: results, passed: results.filter(r => r.status === 'PASS').length,
        failed: results.filter(r => r.status !== 'PASS').length, real_browser: false, real_model: false }));
    process.exitCode = results.some(r => r.status !== 'PASS') ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });

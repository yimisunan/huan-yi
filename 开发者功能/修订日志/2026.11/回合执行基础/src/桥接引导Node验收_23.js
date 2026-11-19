'use strict';
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const root = process.cwd(), base = path.join(root, '开发者功能/修订日志/2026.11/回合执行基础');
const manifest = JSON.parse(fs.readFileSync(path.join(base, 'src/安装清单_23.json')));
const staged = Object.fromEntries(manifest.changes.map(c => [c.path, c.staged]));
const source = rel => fs.readFileSync(path.join(root, process.argv.includes('--installed') ? rel : staged[rel] || rel), 'utf8');
const model = { key: '["CHAT","test","model"]', function_type: 'CHAT', provider_id: 'test', model_id: 'model', provider_name: 'Test', pricing_configured: true };
const results = [];
const flush = async () => { for (let n = 0; n < 12; n++) await new Promise(resolve => setImmediate(resolve)); };
async function test(name, fn) { try { await fn(); results.push({ name, status: 'PASS' }); } catch (e) { results.push({ name, status: 'FAIL', error: e.stack }); } console.log(results.at(-1).status, name); }

function plugin(options = {}) {
    const state = { enabled: false, endpoint: 'http://127.0.0.1:5000', functionType: 'CHAT', outbox: null, inFlight: null,
        workspacePath: '/virtual/test', chatId: 'deleted', participantId: 'owned', ...options.state };
    const requests = [], events = [], intervals = new Map(); let serial = 1, creations = 0, generated = 0;
    let command = options.command || null, commandAcked = false;
    const card = { id: 'owned', marks: 'local.story.operit_bridge:readonly', chatModelBindingMode: 'FIXED_MODEL', chatProviderId: 'test', chatModelId: 'model', toolAccessConfig: {} };
    const Tools = { SoftwareSettings: { async exec(args) {
        events.push(['cli', args]);
        if (args[0] === 'model' && args[1] === 'function-show') return { providerId: 'test', modelId: 'model' };
        if (args[0] === 'model' && args[1] === 'show') return { providerId: 'test', modelId: 'model', providerName: 'Test', pricing: {} };
        if (args[0] === 'chat') return { chatId: 'return-chat' };
        return { success: true };
    } }, Chat: {
        async listChats(params) { events.push(['listChats', params]); if (options.listError) throw Error(options.listError); return { chats: options.exists ? [{ id: state.chatId }] : [] }; },
        async agentStatus(id) { events.push(['agentStatus', id]); return { isIdle: !options.chatBusy }; },
        async createNew(input) { creations++; events.push(['create', input]); return { chatId: 'new-owned-chat' }; },
        async updateTitle() {}, async cancel() {}, async switchTo() {}, async deleteChat() { throw Error('must not delete chats'); },
        async *sendMessageStreaming() { generated++; throw Error('model must not run'); }, async call() { generated++; throw Error('model must not run'); }
    }, Net: { async http(request) {
        const route = request.url.replace(state.endpoint, ''); const body = request.body && JSON.parse(request.body);
        requests.push({ route, body });
        if (options.networkError) throw Error('network unavailable');
        if (route === '/api/story/bridge-info') return { statusCode: 200, content: JSON.stringify({ token: 'isolated-token' }) };
        if (route === '/api/story/tasks') return { statusCode: 200, content: JSON.stringify({ story_protocol: 3, task: null }) };
        if (route === '/api/story/worker/control') {
            if (options.oldServer) return { statusCode: 404, content: JSON.stringify({ error: 'not found' }) };
            if (body.ack_id && command && body.ack_id === command.id) commandAcked = true;
            return { statusCode: 200, content: JSON.stringify({ command: commandAcked ? null : command, story_protocol: 3 }) };
        }
        if (route === '/api/story/worker/claim') return { statusCode: 200, content: '{"task":null}' };
        throw Error(route);
    } } };
    const registrations = { commands: [], hooks: [] };
    const ToolPkg = { ipc: { on() {} }, async callDependency(owner, action, params) {
        events.push(['dependency', action]);
        if (action === 'character.get') return card;
        if (action === 'character.update') { Object.assign(card, params.changes); return card; }
        if (action === 'chat.configuration.binding.read') return { selection: 'card:owned' };
        throw Error(action);
    }, registerCoreCommand(value) { registrations.commands.push(value); }, registerChatInputHook(value) { registrations.hooks.push(value); }, registerAppLifecycleHook() {} };
    const context = { exports: {}, Tools, ToolPkg, PluginConfig: { async use() { return state; }, async flush() {} },
        setInterval(fn) { const id = serial++; intervals.set(id, fn); return id; }, clearInterval(id) { intervals.delete(id); },
        setTimeout() { return serial++; }, clearTimeout() {}, console };
    vm.createContext(context); vm.runInContext(source('开发者功能/Operit故事桥接/main.js'), context);
    context.exports.registerToolPkg();
    return { state, requests, events, intervals, registrations, exports: context.exports,
        creations: () => creations, generated: () => generated, acked: () => commandAcked,
        async runTimers() { for (const fn of [...intervals.values()]) fn(); await flush(); } };
}

function page(initial = {}, options = {}) {
    const nodes = new Map(), requests = [], intervals = []; let stored = JSON.stringify(options.cache || {});
    const status = { revision: 'rev', save_epoch: 'legacy', bridge_connected: false, story_protocol: 3,
        bridge_model: model, task: null, bridge: { control_supported: true, present: false, phase: 'offline', running: false, busy: false, last_error: '', control: null }, ...initial };
    class Node {
        constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.value = ''; this.dataset = {}; this.isConnected = true; this.attrs = {}; this.hidden = false;
            this.classList = { toggle() {}, add() {}, remove() {} }; }
        set id(value) { this._id = value; nodes.set(value, this); } get id() { return this._id; }
        append(...children) { this.children.push(...children); } replaceChildren(...children) { this.children = children; }
        addEventListener(name, fn) { this.events[name] = fn; } setAttribute(k, v) { this.attrs[k] = v; }
        focus() { this.focused = true; } select() { this.selected = true; } showModal() { this.open = true; } close() { this.open = false; }
    }
    const body = new Node('body');
    const document = { body, hidden: false, activeElement: body, createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag),
        getElementById: id => nodes.get(id) || null, querySelectorAll: () => [], addEventListener() {} };
    let clipboard = null;
    const context = { document, window: {}, navigator: options.noClipboard ? {} : { clipboard: { async writeText(text) { clipboard = text; } } },
        localStorage: { getItem: () => stored, setItem: (_, s) => { stored = s; } }, AbortController, crypto: { randomUUID: () => 'isolated' },
        setTimeout: () => 1, clearTimeout() {}, setInterval: fn => intervals.push(fn), fetch: async (url, opts) => {
            const endpoint = url.replace('/api/story/', ''); requests.push({ endpoint, method: opts.method, body: opts.body });
            if (endpoint === 'bridge/control') {
                if (options.control404) return { status: 404, ok: false, json: async () => ({ error: 'Not found' }) };
                status.bridge.control = { id: 'a'.repeat(32), action: JSON.parse(opts.body).action, status: 'requested' };
            }
            return { status: 200, ok: true, json: async () => JSON.parse(JSON.stringify(status)) };
        } };
    vm.createContext(context); vm.runInContext(source('story_client.js'), context);
    const all = node => [node, ...node.children.flatMap(all)];
    return { nodes, body, requests, status, context, clipboard: () => clipboard, cache: () => JSON.parse(stored), all: () => all(body),
        async start() { await context.window.StoryPage.start(async () => -1); }, async click(id) { nodes.get(id).events.click(); await flush(); },
        async poll() { intervals[0](); await flush(); } };
}

(async () => {
    await test('registration_has_fixed_command_and_exported_control_hook', async () => {
        const h = plugin(); assert.equal(h.registrations.commands[0].name, 'storybridge');
        assert.equal(h.registrations.commands[0].function, h.exports.bridgeCommand); assert.equal(h.registrations.hooks[0].function, h.exports.bridgeInput);
    });
    await test('paused_monitor_never_claims_or_calls_model', async () => {
        const h = plugin(); await h.exports.receive({ action: 'status' }); await flush(); await h.runTimers();
        assert.ok(h.requests.some(r => r.route.endsWith('/control'))); assert.ok(!h.requests.some(r => r.route.endsWith('/claim'))); assert.equal(h.generated(), 0);
    });
    await test('deleted_owned_chat_rebuilt_before_claim_without_deletion', async () => {
        const h = plugin(); const value = await h.exports.receive({ action: 'start' }); await flush();
        assert.equal(value.running, true); assert.equal(h.creations(), 1); assert.equal(h.state.chatId, 'new-owned-chat');
        assert.ok(h.events.some(e => e[0] === 'create' && e[1].setAsCurrentChat === false));
        assert.equal(h.generated(), 0); await h.exports.receive({ action: 'stop' });
    });
    await test('query_failure_preserves_owned_chat_and_blocks_start', async () => {
        const h = plugin({ listError: 'permission unavailable' });
        await assert.rejects(() => h.exports.receive({ action: 'start' }), /permission unavailable/);
        assert.equal(h.state.chatId, 'deleted'); assert.equal(h.creations(), 0); assert.equal(h.state.enabled, false);
    });
    await test('existing_busy_chat_is_not_replaced', async () => {
        const h = plugin({ exists: true, chatBusy: true }); await assert.rejects(() => h.exports.receive({ action: 'start' }), /仍在运行|忙碌/); assert.equal(h.creations(), 0);
    });
    await test('page_start_command_acknowledged_once_and_monitor_survives_stop', async () => {
        const h = plugin({ command: { id: 'b'.repeat(32), action: 'start', status: 'requested' } });
        await h.exports.receive({ action: 'status' }); await flush(); await h.runTimers(); assert.equal(h.acked(), true); assert.equal(h.creations(), 1);
        await h.exports.receive({ action: 'stop' }); assert.ok(h.intervals.size >= 1); assert.equal((await h.exports.receive({ action: 'status' })).running, false); assert.equal(h.generated(), 0);
    });
    await test('old_server_reports_unsupported_without_claim_while_paused', async () => {
        const h = plugin({ oldServer: true }); await h.exports.receive({ action: 'status' }); await flush();
        assert.equal((await h.exports.receive({ action: 'status' })).controlSupported, false); assert.equal(h.generated(), 0);
    });
    await test('explicit_chinese_control_consumed_without_model', async () => {
        const h = plugin(); const value = await h.exports.bridgeInput({ eventName: 'submit_requested', eventPayload: { text: '启动故事桥接服务', attachments: [], replyToMessageTimestamp: null } });
        assert.equal(value.action, 'Consume'); assert.ok(value.message.includes('已启动')); assert.equal(h.generated(), 0); await h.exports.receive({ action: 'stop' });
    });
    await test('story_inputs_and_attached_requests_are_not_intercepted', async () => {
        const h = plugin(); for (const text of ['开始新故事', '启动', '请解释启动故事桥接的办法', '故事桥接服务开启后继续剧情']) {
            assert.equal((await h.exports.bridgeInput({ eventName: 'submit_requested', eventPayload: { text, attachments: [], replyToMessageTimestamp: null } })).action, 'Allow');
        }
        assert.equal((await h.exports.bridgeInput({ eventName: 'submit_requested', eventPayload: { text: '启动故事桥接', attachments: [{}] } })).action, 'Allow');
    });
    await test('fixed_status_command_uses_no_model_or_generation', async () => {
        const h = plugin(); const result = await h.exports.bridgeCommand({ eventPayload: { args: ['status'] } }); assert.ok(result.stdout.includes('暂停')); assert.equal(h.generated(), 0);
    });
    await test('page_offline_shows_three_steps_and_start_control', async () => {
        const h = page(); await h.start(); assert.equal(h.nodes.get('story-bridge-start').disabled, false);
        assert.equal(h.nodes.get('story-connection').children[1].children.length, 3);
        await h.click('story-bridge-start'); assert.equal(h.requests.at(-1).endpoint, 'bridge/control');
        assert.equal(JSON.parse(h.requests.at(-1).body).action, 'start'); assert.equal(h.nodes.get('story-bridge-start').disabled, true);
    });
    await test('page_online_has_pause_and_hides_bootstrap_command', async () => {
        const h = page({ bridge_connected: true, bridge: { control_supported: true, present: true, running: true, phase: 'ready', last_error: '' } }); await h.start();
        assert.equal(h.nodes.get('story-bridge-start').hidden, true); assert.equal(h.nodes.get('story-bridge-stop').hidden, false);
        await h.click('story-bridge-stop'); assert.equal(JSON.parse(h.requests.at(-1).body).action, 'stop');
    });
    await test('page_connection_fault_is_visible_without_losing_draft', async () => {
        const h = page({ bridge: { control_supported: true, present: true, running: true, phase: 'error', last_error: 'Chat does not exist' } }, { cache: { draft: '保留行动' } }); await h.start();
        assert.equal(h.nodes.get('story-connection').dataset.state, 'error'); assert.equal(h.nodes.get('story-action-input').value, '保留行动');
        assert.ok(h.nodes.get('story-connection').children[2].textContent.includes('Chat does not exist'));
    });
    await test('clipboard_command_and_manual_selection_fallback', async () => {
        const h = page(); await h.start(); await h.click('story-bridge-copy'); assert.equal(h.clipboard(), '/storybridge start');
        const fallback = page({}, { noClipboard: true }); await fallback.start(); await fallback.click('story-bridge-copy'); assert.equal(fallback.nodes.get('story-bridge-command').selected, true);
    });
    await test('legacy_backend_disables_page_control_with_restart_guidance', async () => {
        const h = page({ bridge: undefined }); await h.start(); assert.equal(h.nodes.get('story-bridge-start').disabled, true);
        assert.ok(h.nodes.get('story-connection').children[2].textContent.includes('重启'));
    });
    await test('control_404_produces_load_guidance_not_json_exception', async () => {
        const h = page({}, { control404: true }); await h.start(); await h.click('story-bridge-start');
        assert.ok(h.nodes.get('story-connection').children[2].textContent.includes('重启'));
    });
    await test('disconnected_submit_opens_connection_without_task_post', async () => {
        const h = page({}, { cache: { draft: '开始新故事' } }); await h.start();
        const form = h.all().find(n => n.tag === 'form'); form.events.submit({ preventDefault() {} }); await flush();
        assert.ok(h.nodes.get('story-action-dialog').open); assert.ok(!h.requests.some(r => r.endpoint === 'tasks' && r.method === 'POST'));
    });
    await test('page_connected_update_clears_old_copy_notice', async () => {
        const h = page(); await h.start(); await h.click('story-bridge-copy');
        Object.assign(h.status, { bridge_connected: true, bridge: { control_supported: true, present: true, running: true, phase: 'ready', last_error: '' } }); await h.poll();
        assert.ok(h.nodes.get('story-connection').children[2].textContent.includes('后续行动'));
    });
    const output = { cases: results, passed: results.filter(r => r.status === 'PASS').length, failed: results.filter(r => r.status === 'FAIL').length,
        real_plugin_source: true, host_api_adapters: true, real_dom_browser: false, real_model_called: false };
    fs.writeFileSync(path.join(base, 'src/桥接引导Node结果_23.json'), JSON.stringify(output, null, 2));
    console.log('BRIDGE23_NODE_' + (output.failed ? 'FAIL' : 'PASS') + ' passed=' + output.passed + ' failed=' + output.failed);
    process.exitCode = output.failed ? 1 : 0;
})();
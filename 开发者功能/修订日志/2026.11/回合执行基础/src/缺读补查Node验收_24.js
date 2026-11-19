'use strict';
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const root = process.cwd(), base = path.join(root, '开发者功能/修订日志/2026.11/回合执行基础');
const manifest = JSON.parse(fs.readFileSync(path.join(base, 'src/安装清单_24.json')));
const change = manifest.changes.find(c => c.path === '开发者功能/Operit故事桥接/main.js');
const source = fs.readFileSync(path.join(root, process.argv.includes('--installed') ? change.path : change.staged), 'utf8');
const model = { key: '["CHAT","test","model"]', function_type: 'CHAT', provider_id: 'test', model_id: 'model', provider_name: 'Test', pricing_configured: false };
const task = { request_id: 'isolated-read24', lease: 'lease24', turns: [{ kind: 'user', content: '{"host_action":"递材料"}' }], reading_preflight: 1,
    round_identity: { schema_version: 1, request_id: 'isolated-read24', base_revision: 'a'.repeat(64), current_round: 3 } };
const session = { chatId: 'owned', participantId: 'reader' };
const results = [];
async function test(name, fn) { try { await fn(); results.push({ name, status: 'PASS' }); } catch (e) { results.push({ name, status: 'FAIL', error: e.stack }); } console.log(results.at(-1).status, name); }
const drain = async () => { for (let n = 0; n < 15; n++) await new Promise(resolve => setImmediate(resolve)); };

function harness(options = {}) {
    const state = { enabled: false, endpoint: 'http://127.0.0.1:5000', functionType: 'CHAT', workspacePath: '/virtual/test', outbox: null, inFlight: null, chatId: 'owned', participantId: 'reader' };
    const sends = [], posts = [], cancelled = [], timers = new Map(), bindings = [], registered = []; let serial = 1, streams = 0, calls = 0;
    const parsed = { story_nodes: [], memory_deltas: {}, options_text: 'draft', model_audit: { required_keys: ['sys.shame'] } };
    const Tools = { SoftwareSettings: { async exec(args) {
        if (args[0] === 'chat') return { chatId: 'current-user-chat' };
        if (args[0] === 'model' && args[1] === 'function-show') return { providerId: 'test', modelId: options.modelChanged && streams ? 'changed' : 'model' };
        if (args[0] === 'model' && args[1] === 'show') return { providerId: args[2], modelId: args[3], providerName: 'Test' };
        bindings.push(args); return { success: true };
    } }, Chat: {
        async listChats() { return { chats: [{ id: 'owned' }] }; }, async agentStatus() { return { isIdle: true }; },
        async updateTitle() {}, async createNew() { throw Error('must not create an existing chat'); },
        async switchTo() { throw Error('unexpected current chat switch'); }, async cancel(id) { cancelled.push(id); },
        async call() { calls++; throw Error('memory compression must not run'); },
        async *sendMessageStreaming(request) {
            sends.push(request); streams++; const count = streams;
            if (options.restart) throw Error('interrupted by restart');
            const timestamp = 100 + count;
            const entries = count === 1 ? (options.toolOverflow ? 128 : 1) : 1;
            const parts = [];
            for (let i = 0; i < entries; i++) {
                parts.push({ kind: 'tool_call', toolName: options.writeTool ? 'write_file' : 'read_file_part', partId: 'call-' + i, toolCallId: 'call-' + i,
                    attributes: { path: count === 1 ? '存档/全局记忆库.txt' : 'txt文件/.story-reading/task/sys.shame.txt', start_line: 1, end_line: 44 } });
                parts.push({ kind: 'tool_result', toolName: options.writeTool ? 'write_file' : 'read_file_part', partId: 'result-' + i, toolCallId: 'call-' + i,
                    attributes: { status: 'success' }, content: '1| actual-' + count });
            }
            parts.push({ kind: 'markdown', content: JSON.stringify({ ...parsed, options_text: 'draft-' + count }) });
            if (!options.noTools) {
                // Only the latest revision should contribute tool receipts.
                yield { type: 'part', chatId: options.foreignChat ? 'foreign' : 'owned', messageTimestamp: timestamp, revision: 2, parts };
                yield { type: 'part', chatId: 'owned', messageTimestamp: timestamp, revision: 1, parts: [] };
            } else yield { type: 'part', chatId: 'owned', messageTimestamp: timestamp, revision: 1, parts: [parts.at(-1)] };
            if (options.timeout) for (const timer of timers.values()) if (timer.ms === 600000) timer.fn();
            if (!options.noReceipt) yield { type: 'completed', result: { chatId: 'owned', outcome: {
                type: options.cancelledReceipt ? 'cancelled' : 'committed', status: options.cancelledReceipt ? 'cancelled' : 'completed', assistant: { messageTimestamp: timestamp } } } };
        }
    }, Net: { async http(request) {
        const route = request.url.replace(state.endpoint, ''), body = request.body && JSON.parse(request.body); posts.push({ route, body, headers: request.headers });
        if (route === '/api/story/bridge-info') return { statusCode: 200, content: '{"token":"synthetic-test-token"}' };
        if (route === '/api/story/tasks') return { statusCode: 200, content: JSON.stringify({ story_protocol: 3, reading_preflight: options.oldServer ? undefined : 1, task: null }) };
        if (route === '/api/story/worker/control') return { statusCode: 200, content: '{"command":null}' };
        if (route === '/api/story/worker/claim') return { statusCode: 200, content: '{"task":null}' };
        if (route.endsWith('/preflight')) {
            if (options.preflightError) return { statusCode: 409, content: '{"error":"source changed"}' };
            if (options.badPreflight) return { statusCode: 200, content: '{"ready":false}' };
            const ready = options.alwaysReady || (!options.stillMissing && streams > 1);
            return { statusCode: 200, content: JSON.stringify({ ready, missing_keys: ready ? [] : ['sys.shame'],
                read_targets: ready ? [] : [{ key: 'sys.shame', reads: [{ path: 'txt文件/.story-reading/task/sys.shame.txt', start_line: 1, end_line: 44 }] }] }) };
        }
        throw Error('unexpected route: ' + route);
    } } };
    const card = { id: 'reader', marks: 'local.story.operit_bridge:readonly', chatModelBindingMode: 'FIXED_MODEL', chatProviderId: 'test', chatModelId: 'model' };
    const ToolPkg = { ipc: { on() {} }, registerCoreCommand() {}, registerChatInputHook() {}, registerAppLifecycleHook() {}, async callDependency(owner, action, input) {
        if (action === 'character.get') return card;
        if (action === 'character.update') { Object.assign(card, input.changes); return card; }
        if (action === 'chat.configuration.binding.read') return { selection: 'card:reader' };
        throw Error(action);
    } };
    const context = { exports: {}, Tools, ToolPkg, PluginConfig: { async use() { return state; }, async flush() {} }, console,
        setInterval(fn, ms) { const id = serial++; timers.set(id, { fn, ms }); return id; }, clearInterval(id) { timers.delete(id); },
        setTimeout(fn, ms) { const id = serial++; timers.set(id, { fn, ms }); return id; }, clearTimeout(id) { timers.delete(id); } };
    vm.createContext(context); vm.runInContext(source + '\nexports.testSession = executeSession; exports.testInterrupted = interruptedSession;', context);
    return { state, sends, posts, cancelled, timers, exports: context.exports, count: () => streams, calls: () => calls,
        run: (selectedTask = task) => context.exports.testSession(state, selectedTask, model, session) };
}

(async () => {
    await test('single_pass_preflight_adds_no_model_call', async () => {
        const h = harness({ alwaysReady: true }), result = await h.run(); assert.equal(h.count(), 1);
        assert.equal(result.conversation_audit.tools.length, 1); assert.equal(result.conversation_audit.read_passes.length, 1);
        assert.equal(JSON.parse(result.text).options_text, 'draft-1'); assert.equal(h.calls(), 0);
        assert.equal(h.posts.filter(x => x.route.endsWith('/preflight')).length, 1); assert.equal(h.timers.size, 0);
    });
    await test('missing_key_exactly_one_real_tool_repair_merges_both_receipts', async () => {
        const h = harness(), result = await h.run(), proof = result.conversation_audit;
        assert.equal(h.count(), 2); assert.equal(proof.tools.length, 2); assert.equal(proof.read_passes.length, 2);
        assert.deepEqual(JSON.parse(JSON.stringify(proof.repair_keys)), ['sys.shame']);
        assert.equal(proof.read_passes[1].tool_start, 1); assert.equal(proof.snapshot_message_timestamp, 102);
        assert.equal(JSON.parse(result.text).options_text, 'draft-2'); assert.equal(result.lease, task.lease);
        const repair = JSON.parse(h.sends[1].input.text); assert.deepEqual(repair.round_identity, task.round_identity);
        assert.equal(repair.read_repair.max_attempts, 1); assert.ok(repair.instruction.includes('不得删除必需key'));
        assert.equal(h.posts.filter(x => x.route.endsWith('/preflight')).length, 2);
        assert.ok(h.posts.filter(x => x.route.endsWith('/preflight')).every(x => x.headers['X-Story-Bridge'] === 'synthetic-test-token'));
    });
    await test('still_missing_after_one_repair_stops_without_third_call', async () => {
        const h = harness({ stillMissing: true }); await assert.rejects(() => h.run(), /补读后仍缺必需正文/);
        assert.equal(h.count(), 2); assert.deepEqual(h.cancelled, ['owned']); assert.equal(h.timers.size, 0);
    });
    await test('model_change_during_generation_blocks_repair_and_delivery', async () => {
        const h = harness({ modelChanged: true }); await assert.rejects(() => h.run(), /生成模型已变更/);
        assert.equal(h.count(), 1); assert.ok(!h.posts.some(x => x.route.endsWith('/preflight')));
    });
    await test('cancelled_missing_receipt_and_no_read_body_are_not_accepted', async () => {
        for (const flag of ['cancelledReceipt', 'noReceipt', 'noTools']) {
            const h = harness({ [flag]: true }); await assert.rejects(() => h.run()); assert.equal(h.count(), 1);
            assert.ok(!h.posts.some(x => x.route.endsWith('/preflight')));
        }
    });
    await test('total_timeout_covers_first_and_repair_stage', async () => {
        const h = harness({ timeout: true }); await assert.rejects(() => h.run(), /超过10分钟/);
        assert.equal(h.count(), 1); assert.equal(h.timers.size, 0);
    });
    await test('source_conflict_and_malformed_preflight_do_not_trigger_extra_model', async () => {
        for (const flag of ['preflightError', 'badPreflight']) {
            const h = harness({ [flag]: true }); await assert.rejects(() => h.run()); assert.equal(h.count(), 1);
        }
    });
    await test('foreign_chat_and_write_tool_streams_rejected', async () => {
        for (const flag of ['foreignChat', 'writeTool']) { const h = harness({ [flag]: true }); await assert.rejects(() => h.run()); assert.equal(h.count(), 1); }
    });
    await test('tool_limit_is_total_across_both_real_completions', async () => {
        const h = harness({ toolOverflow: true }); await assert.rejects(() => h.run(), /累计超过128次/); assert.equal(h.count(), 2);
    });
    await test('restart_during_repair_never_automatically_repeats_generation', async () => {
        const h = harness({ restart: true }); await assert.rejects(() => h.run(), /interrupted by restart/);
        assert.equal(h.state.inFlight.request_id, task.request_id); await h.exports.testInterrupted(h.state);
        assert.equal(h.state.inFlight, null); assert.ok(h.state.outbox.body.error.includes('未自动重复生成')); assert.equal(h.count(), 1);
    });
    await test('old_task_capability_blocks_before_first_model', async () => {
        const h = harness(); await assert.rejects(() => h.run({ ...task, reading_preflight: undefined }), /重启Pydroid3/); assert.equal(h.count(), 0);
    });
    await test('old_server_start_blocked_before_session_or_claim', async () => {
        const h = harness({ oldServer: true }); await assert.rejects(() => h.exports.receive({ action: 'start' }), /提交前读取校验/);
        await drain(); assert.equal(h.state.enabled, false); assert.ok(!h.posts.some(x => x.route.endsWith('/claim'))); assert.equal(h.count(), 0);
    });
    const out = { cases: results, passed: results.filter(x => x.status === 'PASS').length, failed: results.filter(x => x.status === 'FAIL').length,
        real_plugin_source: true, synthetic_host_streams: true, real_model_called: false };
    fs.writeFileSync(path.join(base, 'src/缺读补查Node结果_24.json'), JSON.stringify(out, null, 2) + '\n');
    console.log('READ24_NODE_' + (out.failed ? 'FAIL' : 'PASS') + ' passed=' + out.passed + ' failed=' + out.failed);
    process.exitCode = out.failed ? 1 : 0;
})();
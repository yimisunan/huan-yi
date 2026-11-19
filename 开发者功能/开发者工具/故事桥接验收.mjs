import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
let project = here;
while (!fs.existsSync(path.join(project, 'AGENTS.md'))) project = path.dirname(project);
const source = process.env.STORY_TEST_SOURCE || project;
const bridgePath = fs.existsSync(path.join(source, 'main.js')) ? path.join(source, 'main.js') : path.join(source, '开发者功能/Operit故事桥接/main.js');
const bridgeCode = fs.readFileSync(bridgePath, 'utf8').replace(/export /g, '');
const modelFixture = { functionType: 'CHAT', providerId: 'provider-test', modelId: 'model-test', providerName: 'Test Provider', pricing: null };
const modelKey = JSON.stringify(['CHAT', modelFixture.providerId, modelFixture.modelId]);
const modelPublic = { key: modelKey, function_type: 'CHAT', provider_id: modelFixture.providerId,
    provider_name: modelFixture.providerName, model_id: modelFixture.modelId, pricing_configured: false };
let currentChatId = 'original-chat';
const cli = { exec: async args => {
    if (args[0] === 'chat' && args[1] === 'current') return { chatId: currentChatId };
    if (args[0] === 'workspace') return { success: true, data: {} };
    return { success: true, data: JSON.stringify(args[1] === 'function-show'
        ? { functionType: 'CHAT', providerId: modelFixture.providerId, modelId: modelFixture.modelId }
        : { ...modelFixture, apiKey: 'must-not-leak' }) };
} };
const dependency = async (_pkg, method) => {
    if (method === 'character.get') return { id: 'test-role', marks: 'local.story.operit_bridge:readonly',
        chatModelBindingMode: 'FIXED_MODEL', chatProviderId: modelFixture.providerId, chatModelId: modelFixture.modelId,
        toolAccessConfig: { enabled: true, allowedBuiltinTools: ['list_files','find_files','grep_code','read_file','read_file_full','read_file_part','file_info','file_exists'],
            allowedPackages: [], allowedSkills: [], allowedMcpServers: [] } };
    if (method === 'character.update') return { id: 'test-role' };
    if (method === 'chat.configuration.binding.read') return { selection: 'card:test-role' };
    throw new Error('unexpected dependency ' + method);
};
function nativeResult(text, timestamp=123) {
    return { type: 'part', chatId: 'test-chat', messageTimestamp: timestamp, revision: 2,
        parts: [
            {kind:'markdown',content:'正在只读查证。',partId:'intro',sequence:0,attributes:{}},
            {kind:'tool_call',toolName:'read_file',toolCallId:'call-1',partId:'call-1',sequence:1,content:'',attributes:{path:'存档/全局记忆库.txt'}},
            {kind:'tool_result',toolName:'read_file',toolCallId:null,partId:'result-1',sequence:2,content:'文件内容',attributes:{status:'success'}},
            {kind:'markdown',content:text,partId:'final',sequence:3,attributes:{}}
        ] };
}
function nativeReceipt(timestamp=123) {
    return { type:'completed',result:{chatId:'test-chat',sentAt:1,receivedAt:2,
        outcome:{type:'committed',status:'completed',assistant:{messageTimestamp:timestamp,variantIndex:0},userMessageTimestamp:100}} };
}
const sessionConfig = { workspacePath: '/test-project', chatId: 'test-chat', participantId: 'test-role', inFlight: null };
const idleChat = { agentStatus: async () => ({ isIdle: true }), cancel: async () => ({}), switchTo: async id => { currentChatId = id; } };
const intervals = new Map();
let nextTimer = 0, claimed = 0, generated = 0, delivered = 0, failDelivery = true;
const config = { enabled: false, endpoint: 'http://127.0.0.1:5000', functionType: 'CHAT', outbox: null, ...sessionConfig };
let resolveModel;
const ctx = vm.createContext({ console, Set, Promise, JSON, Error, exports: {},
    PluginConfig: { use: async () => config, flush: async () => {} },
    ToolPkg: { ipc: { on() {} }, registerAppLifecycleHook() {}, callDependency: dependency },
    setInterval: (fn, ms) => { const id = ++nextTimer; intervals.set(id, { fn, ms }); return id; },
    clearInterval: id => intervals.delete(id), setTimeout: () => 0, clearTimeout() {},
    Tools: { SoftwareSettings: cli, Chat: { ...idleChat, sendMessageStreaming: async function* (options) {
        generated++; assert.equal(options.turn.kind, 'execute'); assert.equal(options.turn.participantId,'test-role');
        assert.ok(config.inFlight, 'in-flight persisted before paid call');
        currentChatId = 'test-chat';
        const output = await new Promise(resolve => { resolveModel = resolve; });
        yield nativeResult(output.text); yield nativeReceipt();
    } }, Net: { http: async options => {
        let content;
        if (options.url.endsWith('/bridge-info')) content = { token: 'local-test' };
        else if (options.url.endsWith('/api/story/tasks')) content = { task: {status:'queued'}, story_protocol: 3 };
        else if (options.url.endsWith('/claim')) {
            claimed++;
            content = { task: claimed === 1 ? { request_id: 'page-test', lease: 'lease-1', turns: [] } : null };
        } else if (options.url.endsWith('/heartbeat')) content = { status: 'generating' };
        else if (options.url.endsWith('/result')) {
            delivered++;
            assert.equal(JSON.parse(options.body).text, '{"test":true}');
            assert.ok(config.outbox, 'output saved before callback');
            if (failDelivery) throw new Error('transport dropped');
            content = { task: { status: 'committed' } };
        } else throw new Error('unexpected URL');
        return { statusCode: 200, content: JSON.stringify(content) };
    } } }
});
vm.runInContext(bridgeCode, ctx);
const call = code => vm.runInContext(code, ctx);
const settle = async () => { for (let i = 0; i < 120; i++) await Promise.resolve(); };
await call("receive({action:'start'})"); await settle();
assert.equal(generated, 1);
const loop = [...intervals.values()].find(value => value.ms === 3000).fn;
loop(); loop(); await settle();
assert.equal(generated, 1, 'one consumer while model is pending');
resolveModel({ text: '{"test":true}' }); await settle();
assert.ok(config.outbox, 'failed delivery retains exact result');
assert.equal(delivered, 1);
failDelivery = false; loop(); await settle();
assert.equal(delivered, 2); assert.equal(generated, 1); assert.equal(config.outbox, null);
assert.equal(currentChatId, 'original-chat');
await call("receive({action:'stop'})");
assert.equal(config.enabled, false); assert.equal(intervals.size, 0);
console.log('PASS bridge: single consumer, durable output, delivery retry, stop');

class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.value = ''; this.open = false; this.isConnected = true;
        this.classList = { toggle() {}, add() {}, remove() {} }; this.dataset = {}; this.disabled = false; this.textContent = ''; this.attrs = {}; this.modalCount = 0; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = [...nodes]; }
    setAttribute(name, value) { this.attrs[name] = value; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    focus() {}
    showModal() { this.open = true; this.modalCount++; }
    close() { this.open = false; this.listeners.close?.(); }
}
const storage = new Map();
const body = new Element('body');
const snapshots = [];
const rev = 'a'.repeat(64);
let pageTask = null, failSubmit = true;
const posted = [];
const callbacks = [];
const pageTimers = new Map(); let pageTimerId = 0;
const page = vm.createContext({ console, JSON, Set, Promise, Error, AbortController, globalThis: {},
    window: {}, localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    setTimeout: (fn, ms) => { const id = ++pageTimerId; pageTimers.set(id, {fn, ms}); return id; },
    clearTimeout: id => pageTimers.delete(id),
    setInterval: fn => { callbacks.push(fn); return 1; },
    document: { body, createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag), getElementById: () => null, activeElement: null, hidden: false, querySelectorAll: () => [], addEventListener() {} },
    fetch: async (url, options) => {
        let content, status = 200;
        if (url.endsWith('/snapshot')) content = { revision: rev, bridge_connected: true, story_protocol: 2, bridge_model: modelPublic, data: {}, task: pageTask };
        else if (url.endsWith('/tasks') && options.method === 'POST') {
            const request = JSON.parse(options.body); posted.push(request);
            if (failSubmit) throw new Error('network lost');
            pageTask = { ...request, status: 'queued' }; content = { task: pageTask };
        } else if (url.endsWith('/tasks')) content = { task: pageTask, bridge_connected: true, story_protocol: 2, bridge_model: modelPublic };
        else { status = 404; content = { error: 'missing' }; }
        return { ok: status === 200, status, json: async () => content };
    }
});
vm.runInContext(fs.readFileSync(path.join(source, 'story_client.js'), 'utf8'), page);
await page.window.StoryPage.start(async (snapshot, index) => { snapshots.push(index); return 2; });
page.window.StoryPage.read(3);
assert.equal(JSON.parse(storage.get('story-page-v1')).progress.index, 3);
page.window.StoryPage.choose('把杯子放在桌上。'); await settle();
const dialog = body.children[1], form = dialog.children[1], confirmation = body.children[2];
assert.equal(dialog.open, false, 'normal selection does not open modal');
assert.equal(posted.length, 0, 'first use waits for model acceptance');
assert.equal(confirmation.hidden, false);
confirmation.children[2].children[0].listeners.click(); await settle();
assert.ok(JSON.parse(storage.get('story-page-v1')).pending);
assert.equal(dialog.open, true, 'transport error opens dialog');
const buttons = form.children[4];
failSubmit = false;
buttons.children[1].listeners.click(); await settle();
assert.equal(posted.length, 2);
assert.deepEqual(posted[0], posted[1], 'uncertain submission reuses exact identity');
assert.equal(posted[0].model_key, modelKey);
assert.equal(JSON.parse(storage.get('story-page-v1')).pending, undefined);
assert.equal(form.children[1].disabled, true);
assert.equal(dialog.open, false, 'retry closes modal while generating');
const initialPosts = posted.length;
page.window.StoryPage.choose('重复点选'); await settle(); assert.equal(posted.length, initialPosts);
pageTask = { ...pageTask, status: 'failed', error: 'invalid model output', attempt: 1 };
callbacks[0](); await settle();
assert.equal(form.children[1].value, '把杯子放在桌上。');
assert.equal(form.children[1].disabled, false);
assert.equal(dialog.open, true);
const popups = dialog.modalCount; dialog.close(); callbacks[0](); await settle();
assert.equal(dialog.open, false); assert.equal(dialog.modalCount, popups, 'same failure never reopens');
page.window.StoryPage.settlement(rev, 6, [{role:'角色甲',attr:'好感',old:31,neu:34},{role:'角色乙',attr:'体力',old:90,neu:85}]);
const settlementParent = new Element('div'), reward = body.children[4];
assert.equal(reward.hidden, true, 'preparing settlement renders nothing');
page.window.StoryPage.showSettlement(settlementParent, true);
assert.equal(settlementParent.children[0].tag, 'button');
assert.equal(reward.hidden, false);
const rows = reward.children[0].children[1].children;
assert.equal(rows[0].children[1].children[1].textContent, '好感  31 → 34'); assert.equal(rows[0].children[2].textContent, '+3');
assert.equal(rows[1].children[2].textContent, '-5');
assert.equal(rows[0].children[0].children[0].tag, 'svg');
const timeout = [...pageTimers.values()].find(x => x.ms === 5600); assert.ok(timeout);
timeout.fn(); const exit = [...pageTimers.values()].find(x => x.ms === 220); exit.fn();
assert.equal(reward.hidden, true, 'auto dismissal is deterministic');
page.window.StoryPage.showSettlement(new Element('div'), true);
assert.equal(reward.hidden, true, 'same revision never repeats animation');
settlementParent.children[0].listeners.click({stopPropagation(){}});
assert.equal(reward.hidden, false, 'button replays all changes');
page.window.StoryPage.settlement(rev, 6, null);
assert.equal(JSON.parse(storage.get('story-page-v1')).settlement.changes.length, 2, 'same revision keeps settlement');
page.window.StoryPage.settlement('new-revision', 7, []);
assert.equal(reward.hidden, true, 'new revision cancels prior toast');
page.window.StoryPage.showSettlement(new Element('div'), true);
assert.equal(reward.children[0].children[1].children[0].textContent, '故事继续，数值如常');
assert.ok([...pageTimers.values()].find(x => x.ms === 2800));
page.window.StoryPage.leaveOptions(); assert.equal(reward.hidden, true);
page.window.StoryPage.settlement('missing-baseline', 8, null);
const empty = new Element('div'); page.window.StoryPage.showSettlement(empty, true);
assert.equal(reward.hidden, true, 'missing baseline has no reward animation');
empty.children[0].listeners.click({stopPropagation(){}});
assert.equal(reward.children[0].children[1].children[0].textContent, '这段往事暂无记录');
page.window.StoryPage.leaveOptions();
assert.equal(body.children[0].children[1].textContent, '!', 'error uses compact badge');
modelPublic.model_id = 'changed-model'; modelPublic.key = JSON.stringify(['CHAT', modelPublic.provider_id, modelPublic.model_id]);
page.window.StoryPage.choose('确认新模型后才提交'); await settle();
assert.equal(posted.length, initialPosts); assert.equal(confirmation.hidden, false);
assert.equal(dialog.open, false); assert.ok(confirmation.children[1].textContent.includes('changed-model'));
console.log('PASS page: model confirmation, silent choices, exact retry, one error popup, duplicate guard');
console.log('PASS reward: SVG +/-, delayed reveal, timed dismissal, one animation per revision, replay, cancellation');

{
const html = fs.readFileSync(path.join(source, 'main_template.html'), 'utf8');
const start = html.indexOf('async function applyStorySnapshot(');
const end = html.indexOf("window.addEventListener('load', initialize);", start);
let release;
const seen = [];
const noop = () => {};
const context = vm.createContext({
    storyGeneration: 0, isProcessingNode: false, isRestoringStory: false, storyNodes: [], memoryData: null,
    currentNodeIndex: -1, isVoiceEnabled: true,
    releaseStoryAudio: noop, parseMemoryText: () => ({}), renderItems: noop, parseItemText: () => [],
    renderContactsList: noop, updateMePanel: noop, updateAtmosphere: noop, _checkStatsChanges: noop,
    _hideStatDot: noop, _buildStatsSnapshot: () => ({}), _diffStats: () => [], StoryPage: { settlement: noop },
    resetVanityStage: noop, applySceneTitle: noop, syncVoiceButtons: noop, prepareDualModeForNode: noop,
    renderSceneHeaderCard: node => seen.push(node), renderCraftNoteNode: noop,
    handleDialogueNode: () => new Promise(resolve => { release = resolve; }),
    renderNodeImmediately: async node => seen.push(node.text), updateVanityProgressAfterNode: noop,
    showToast: noop, maybeShowFirstRunGuide: noop, advanceStory: async () => {},
    document: { getElementById: () => ({ replaceChildren: noop }) }
});
vm.runInContext(html.slice(start, end), context);
const old = context.applyStorySnapshot({ data: { storyNodes: [
    { type: 'dialogue', text: 'old pending' }, { type: 'narration', text: 'old must not render' }
] }, memory_text: '', items_text: '' }, 1);
const newer = context.applyStorySnapshot({ data: { storyNodes: [
    { type: 'narration', text: 'current snapshot' }
] }, memory_text: '', items_text: '' }, 0);
await newer;
release(); await old;
assert.deepEqual(seen, ['current snapshot']);
assert.equal(context.isRestoringStory, false);
assert.equal(context.storyNodes[0].text, 'current snapshot');
console.log('PASS reading restore: late previous snapshot cannot resume or clear newer state');
}

// Regression cases for L1 repair, without calling any external model.
{
const memoryContext = vm.createContext({ console, Set, Promise, JSON, Error, exports: {},
    ToolPkg: { ipc: { on() {} }, registerAppLifecycleHook() {} },
    PluginConfig: { use: async () => ({}), flush: async () => {} },
    Tools: { SoftwareSettings: cli, Chat: { call: async () => { throw new Error('model stub not set'); } } }
});
vm.runInContext(bridgeCode, memoryContext);
const length = value => memoryContext.memoryLength(value);
assert.equal(length('汉 A，\n\t😀\u0085\u001c\ufeff'), 5);
assert.equal(length('字'.repeat(280)), 280);
assert.equal(memoryContext.oversizedMemory(JSON.stringify({ memory_deltas: { l1_new_round: '字'.repeat(280) } })), null);
const original = '字'.repeat(298), short = '实'.repeat(180);
const raw = '{"story_nodes":[{"type":"narration","text":"原正文不变\\n含\\\"引号\\\"与括号{}"}],"memory_deltas":{"nested":[{},[1,2]],"l1_new_round":' + JSON.stringify(original) + ',"l2_to_l3_summary":""},"host_events":[],"counter_updates":{"big":9007199254740993},"same":1,"same":2}';
let calls = 0, persisted = false;
memoryContext.PluginConfig.flush = async config => { persisted = config.outbox.repairAttempted === true; };
memoryContext.Tools.Chat.call = async options => {
    calls++;
    assert.equal(persisted, true, 'repair marker saved before paid call');
    assert.equal(JSON.parse(options.turns[1].content).length, 298);
    return { text: JSON.stringify(short) };
};
const repairConfig = { functionType: 'CHAT', outbox: { request_id: 'repair-1', body: { lease: 'lease', text: raw } } };
await memoryContext.repairMemory(repairConfig);
await memoryContext.repairMemory(repairConfig);
assert.equal(calls, 1);
assert.equal(repairConfig.outbox.body.text, raw.replace(JSON.stringify(original), JSON.stringify(short)));
assert.ok(repairConfig.outbox.body.text.includes('9007199254740993'));
assert.ok(repairConfig.outbox.body.text.includes('"same":1,"same":2'));
assert.equal(repairConfig.outbox.body.lease, 'lease');
console.log('PASS L1: Python-compatible count, exact single-field replacement, one persisted repair');

for (const text of ['not json', JSON.stringify({ l1_new_round: '字'.repeat(300) }), JSON.stringify('短'), JSON.stringify('字'.repeat(281)), JSON.stringify('字'.repeat(180) + '\n')]) {
    memoryContext.Tools.Chat.call = async () => { calls++; return { text }; };
    const config = { functionType: 'CHAT', outbox: { request_id: 'bad', body: { text: raw } } };
    const before = calls;
    await memoryContext.repairMemory(config); await memoryContext.repairMemory(config);
    assert.equal(calls, before + 1);
    assert.equal(config.outbox.body.text, raw, 'invalid repair preserves original rejection');
}
const interrupted = { functionType: 'CHAT', outbox: { repairAttempted: true, body: { text: raw } } };
const before = calls; await memoryContext.repairMemory(interrupted); assert.equal(calls, before);
const duplicate = '{"memory_deltas":{"l1_new_round":' + JSON.stringify(original) + ',"l1_new_round":' + JSON.stringify(original) + '}}';
assert.equal(memoryContext.oversizedMemory(duplicate), null, 'duplicate-key input remains for server rejection');
console.log('PASS L1: bad compression rejected, restart bounded, duplicate keys untouched');

const turns = memoryContext.generationTurns({ turns: [{ kind: 'user', content: '原行动' }] }, 'L1超长');
assert.equal(turns[0].content, '原行动');
assert.equal(JSON.parse(turns[1].content).previous_validation_error, 'L1超长');
assert.ok(JSON.parse(turns[1].content).contract_reminder.includes('150～220'));
console.log('PASS L1: retry carries original action and validation feedback');
}

{
let calls = 0, claims = 0, deliveries = 0, offline = true;
const timers = [];
const original = '长'.repeat(298), replacement = '短'.repeat(190);
const generated = JSON.stringify({ request_id: 'single', story_nodes: [], memory_deltas: { l1_new_round: original } });
const config = { enabled: false, endpoint: 'http://127.0.0.1:5000', functionType: 'CHAT', outbox: null, lastRejection: null, ...sessionConfig };
const context = vm.createContext({ console, Set, Promise, JSON, Error, exports: {},
    ToolPkg: { ipc: { on() {} }, registerAppLifecycleHook() {}, callDependency: dependency },
    PluginConfig: { use: async () => config, flush: async () => {} },
    setInterval: (fn, ms) => { timers.push({ fn, ms }); return timers.length; }, clearInterval() {}, setTimeout: () => 0, clearTimeout() {},
    Tools: { SoftwareSettings: cli, Chat: { ...idleChat, sendMessageStreaming: async function* (options) {
        calls++;
        assert.ok(options.input.text.includes('上次L1超长'));
        yield nativeResult(generated); yield nativeReceipt();
    }, call: async options => {
        calls++;
        return {text:JSON.stringify(replacement)};
    } }, Net: { http: async options => {
        let value;
        if (options.url.endsWith('/bridge-info')) value = { token: 'test' };
        else if (options.url.endsWith('/api/story/tasks')) value = { story_protocol: 3, task: { request_id: 'single', status: 'queued', error: '上次L1超长' } };
        else if (options.url.endsWith('/claim')) { claims++; value = { task: { request_id: 'single', lease: 'lease', turns: [] } }; }
        else if (options.url.endsWith('/result')) {
            deliveries++;
            assert.equal(JSON.parse(JSON.parse(options.body).text).memory_deltas.l1_new_round, replacement);
            if (offline) throw new Error('lost response');
            value = { task: { status: 'committed' } };
        } else throw new Error('unexpected request');
        return { statusCode: 200, content: JSON.stringify(value) };
    } } }
});
vm.runInContext(bridgeCode, context);
await context.tick();
assert.equal(calls, 2); assert.equal(claims, 1); assert.equal(deliveries, 1); assert.ok(config.outbox);
offline = false;
await context.tick();
assert.equal(calls, 2); assert.equal(claims, 1); assert.equal(deliveries, 2); assert.equal(config.outbox, null);
console.log('PASS L1: generate + one repair, transport retry adds no model calls');
}

{
const resolved = await ctx.resolveModel(config);
assert.equal(resolved.model_id, 'model-test'); assert.equal(resolved.pricing_configured, false);
assert.equal(JSON.stringify(resolved).includes('must-not-leak'), false);
const oldId = modelFixture.modelId; modelFixture.modelId = 'other-model';
await assert.rejects(() => ctx.checkModel(config, resolved.key), /生成模型已变更/);
modelFixture.modelId = oldId;
assert.equal(JSON.parse(ctx.cliObject(JSON.stringify(JSON.stringify(modelFixture))).pricing ?? 'null'), null);
console.log('PASS model metadata: host query, safe allowlist, pre-call mismatch blocks generation');
}

// Native snapshots replace prior revisions; incomplete, cancelled or unrelated receipts never commit.
{
    const event = nativeResult('{"value":9007199254740993,"same":1,"same":2}');
    const receipts = nativeReceipt().result;
    const snapshots = new Map([[123,event]]);
    const result = ctx.finalMessage(receipts,snapshots);
    assert.equal(result.text,'{"value":9007199254740993,"same":1,"same":2}', 'keep original JSON bytes for server validation');
    assert.equal(result.tools.length,1);
    assert.throws(()=>ctx.finalMessage({...receipts,outcome:{type:'committed',status:'cancelled',assistant:{messageTimestamp:123}}},snapshots));
    assert.throws(()=>ctx.finalMessage({...receipts,outcome:{type:'committed',status:'completed',assistant:{messageTimestamp:456}}},snapshots));
    const bad = nativeResult('not json');
    assert.throws(()=>ctx.finalMessage(receipts,new Map([[123,bad]])));
    const forbidden = nativeResult('{}'); forbidden.parts[1].toolName='write_file';
    assert.throws(()=>ctx.finalMessage(receipts,new Map([[123,forbidden]])));
    const cancelled = { ...sessionConfig, inFlight:{chat_id:'test-chat',request_id:'pending',lease:'lease',model_key:modelKey,return_chat_id:'original-chat'}, outbox:null };
    await ctx.interruptedSession(cancelled);
    assert.equal(cancelled.inFlight,null); assert.ok(cancelled.outbox.body.error.includes('未自动重复生成'));
    console.log('PASS native session: exact receipt, strict final parts, tool allowlist, original JSON, restart bounded');
}

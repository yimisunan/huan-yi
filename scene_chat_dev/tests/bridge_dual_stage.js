'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '../local.story.operit_bridge/main.js'), 'utf8');

function createHarness(opts = {}) {
    const config = {
        workspacePath: '/fixture',
        endpoint: 'http://127.0.0.1:5000',
        functionType: 'CHAT',
        dualStageEnabled: opts.dualStageEnabled !== undefined ? opts.dualStageEnabled : true,
        settlementFunctionType: opts.settlementFunctionType || 'SUMMARY',
        maxTurnsPerSession: opts.maxTurnsPerSession || 10,
        liveSessionPolicy: 'continuous',
        chatId: '',
        participantId: '',
        inFlight: null,
        outbox: null,
        liveSession: opts.liveSession || null,
    };
    const state = {
        cardUpdates: [],
        streamPushes: [],
        sendCalls: [],
        chatCalls: [],
        resultPosts: [],
        createdChats: 0,
        summaryBound: opts.summaryBound !== undefined ? opts.summaryBound : true,
        retryableFirst: !!opts.retryableFirst,
        fgText: opts.fgText || '[N] 暖光漫过桌面。\n[D:沈知韫] 志北，过来坐。\n---DECISION---\nPROMPT: 下一步？\nA: 坐下喝茶。\nB: 轻握她的手。\nC: 谈公事。\n',
        settlementJson: opts.settlementJson || '{"operation":"","handoff":"","checks":{"intent":"i","knowledge":"k","action":"a","pace":"p"},"resolution":{"category":"SYSTEM","basis":"b","clock":{"day":1,"time":"09:10","basis":"c"},"events":[],"memory":{"fact":"","compact":"","transfers":{}},"conditions":"","sleep":{"kind":"none","start":"","evidence":""},"task":"","items":[]},"quality_flags":[]}',
        singleJson: opts.singleJson || '{"messages":[{"kind":"narration","speaker":"","text":"暖光漫过桌面。"}],"decision":{"prompt":"下一步？","options":[{"id":"A","text":"a"},{"id":"B","text":"b"},{"id":"C","text":"c"}]},"operation":"","handoff":"","checks":{"intent":"i","knowledge":"k","action":"a","pace":"p"},"resolution":{"category":"SYSTEM","basis":"b","clock":{"day":1,"time":"09:10","basis":"c"},"events":[],"memory":{"fact":"","compact":"","transfers":{}},"conditions":"","sleep":{"kind":"none","start":"","evidence":""},"task":"","items":[]}}',
    };

    const box = {
        exports: {},
        console,
        setTimeout,
        clearTimeout,
        setInterval,
        clearInterval,
        config,
        state,
        PluginConfig: { use: async () => config, flush: async () => {} },
        ToolPkg: {
            ipc: { on() {} },
            callDependency: async (dep, method, args) => {
                if (method === 'character.list') return [];
                if (method === 'character.create') return { ...args.values, id: 'card-v2' };
                if (method === 'character.get') return { id: 'card-v2', marks: 'local.story.operit_bridge:readonly', name: '同席互动·项目只读', characterSetting: '', otherContentChat: '', chatModelBindingMode: 'FIXED_MODEL', chatProviderId: 'prov', chatModelId: 'gemini-4', toolAccessConfig: { enabled: true, allowedBuiltinTools: ['read_file', 'read_file_full', 'read_file_part', 'file_info', 'grep_code'], allowedPackages: [], allowedSkills: [], allowedMcpServers: [] } };
                if (method === 'character.update') {
                    state.cardUpdates.push(args.changes);
                    return { id: args.id, ...args.changes };
                }
                if (method === 'chat.configuration.binding.read') return { selection: 'card:card-v2' };
                throw new Error('unexpected dep call: ' + method);
            },
        },
        Tools: {
            SoftwareSettings: {
                exec: async (argv) => {
                    if (argv[0] === 'chat' && argv[1] === 'current') return { chatId: 'return-chat' };
                    if (argv[0] === 'workspace' && argv[1] === 'bind') return { success: true };
                    if (argv[0] === 'model' && argv[1] === 'function-show') {
                        const slot = argv[2];
                        if (slot === 'CHAT') return { providerId: 'prov', modelId: 'gemini-4' };
                        if (slot === 'SUMMARY' && state.summaryBound) return { providerId: 'prov', modelId: 'gemini-flash' };
                        return { success: false, error: 'unbound' };
                    }
                    if (argv[0] === 'model' && argv[1] === 'show') {
                        return { providerId: argv[2], modelId: argv[3], providerName: 'Prov', pricing: { in: 1 } };
                    }
                    return { success: true };
                },
            },
            Chat: {
                listChats: async ({ chat_ids }) => ({ chats: chat_ids.map(id => ({ id })) }),
                createNew: async () => ({ chatId: 'live-chat-' + (++state.createdChats) }),
                updateTitle: async () => {},
                agentStatus: async () => ({ isIdle: true }),
                switchTo: async () => {},
                cancel: async () => {},
                getMessages: async (chatId) => ({
                    chatId,
                    messages: [{ sender: 'user', timestamp: 100, content: state.lastSubmittedText }],
                }),
                sendMessageStreaming: async function* (request) {
                    state.sendCalls.push(request);
                    state.lastSubmittedText = request.input.text;
                    const text = state.currentMode === 'dual_stream_v2' ? state.fgText : state.singleJson;
                    if (state.currentMode === 'dual_stream_v2') {
                        yield { type: 'part', chatId: request.chatId, messageTimestamp: 110, revision: 1, parts: [{ kind: 'thinking', content: '构思微幕...' }] };
                        yield { type: 'part', chatId: request.chatId, messageTimestamp: 110, revision: 2, parts: [{ kind: 'thinking', content: '构思微幕...' }, { kind: 'markdown', content: '[N] 暖光漫过桌面。\n[D:沈知韫] 志北，' }] };
                        yield { type: 'part', chatId: request.chatId, messageTimestamp: 110, revision: 3, parts: [{ kind: 'markdown', content: text }] };
                    } else {
                        yield { type: 'part', chatId: request.chatId, messageTimestamp: 110, revision: 1, parts: [{ kind: 'markdown', content: text }] };
                    }
                    yield {
                        type: 'completed',
                        result: {
                            chatId: request.chatId,
                            outcome: { type: 'committed', status: 'completed', userMessageTimestamp: 100, assistant: { messageTimestamp: 110 } },
                        },
                    };
                },
                call: async (req) => {
                    state.chatCalls.push(req);
                    return { text: state.settlementJson };
                },
            },
        },
    };

    vm.createContext(box);
    vm.runInContext(source, box);

    box.http = async (urlPath, body) => {
        if (urlPath === '/api/story/bridge-info') return { token: 'tok' };
        if (urlPath.endsWith('/material')) {
            state.currentMode = body.protocol_mode;
            const z0 = 'ZONE0_GLOBAL_' + body.protocol_mode;
            const z1 = 'ZONE1_SCENE_' + (opts.sceneTag || 'manor');
            const z0Sha = (body.protocol_mode === 'dual_stream_v2' ? 'a' : 'c').repeat(64);
            const z1Sha = (opts.sceneShaChar || 'b').repeat(64);
            const deltaText = JSON.stringify({
                mode: body.protocol_mode,
                anchor: body.is_fresh_session ? 'full_scene_start' : 'incremental_delta',
                player_input: '测试输入',
            });
            return {
                delivery_version: 2,
                protocol_mode: body.protocol_mode,
                zone0_global: z0,
                zone0_sha256: z0Sha,
                zone1_scene: z1,
                zone1_sha256: z1Sha,
                input_text: deltaText,
                include_full_anchor: body.is_fresh_session || body.synced_zone0_sha256 !== z0Sha || body.synced_zone1_sha256 !== z1Sha,
                allowed_speakers: ['沈知韫'],
                last_committed_sequence: body.last_committed_sequence || 0,
                envelope: { output_contract: {} },
                settlement_spec: body.protocol_mode === 'dual_stream_v2' ? {
                    system_prompt: 'STATIC_SETTLE_SYSTEM',
                    system_sha256: 'd'.repeat(64),
                    user_context: { location: '徐家主宅', cast: ['沈知韫'] },
                } : null,
                delivery: {
                    id: 'e'.repeat(48),
                    input_sha256: 'f'.repeat(64),
                    zone0_sha256: z0Sha,
                    zone1_sha256: z1Sha,
                },
                ...(opts.stage1Checkpoint ? { stage1_checkpoint: opts.stage1Checkpoint } : {}),
            };
        }
        if (urlPath.endsWith('/stream')) {
            state.streamPushes.push(body);
            return { ok: true };
        }
        if (urlPath.endsWith('/result')) {
            state.resultPosts.push(body);
            if (state.retryableFirst && state.resultPosts.length === 1) {
                return { retryable_settlement: true, error: 'evidence需为正文子串', task: { request_id: 'r1', status: 'generating' } };
            }
            return { task: { request_id: 'r1', status: 'committed' } };
        }
        if (urlPath.endsWith('/preflight')) {
            throw new Error('v2 must not call /preflight');
        }
        throw new Error('unexpected http: ' + urlPath);
    };
    vm.runInContext('http = box_http;', Object.assign(box, { box_http: box.http }));
    return box;
}

async function run() {
    const model = { key: '["CHAT","prov","gemini-4"]', function_type: 'CHAT', provider_id: 'prov', model_id: 'gemini-4', provider_name: 'Prov', pricing_configured: true };

    // 1. Dual-stage turn 1 + settlement retry + turn 2 prefix cache hit (zero card rewrite!)
    const h1 = createHarness({ retryableFirst: true });
    h1.model = model;
    h1.task = {
        request_id: 'r1', lease: 'L1', entry_mode: 'live_interaction', save_epoch: 'ep1',
        interaction_scope: '徐家主宅|沈知韫|', service_epoch: 'srv1',
        reading_preflight: 1, live_reading_revision: 2, action_contract_revision: 1,
        material_delivery_revision: 1, material_delivery_v2: 1, dual_stage_protocol: 1,
    };
    const sess1 = await vm.runInContext('liveSession(config, model, task)', h1);
    assert.equal(sess1.isFresh, true);
    h1.session = sess1;
    const out1 = await vm.runInContext('executeSession(config, task, model, session)', h1);
    assert.equal(out1.__alreadyDelivered, true);
    assert.equal(h1.state.cardUpdates.length, 1, 'Turn 1 must sync Zone 0 + Zone 1 into card once');
    assert.equal(h1.state.cardUpdates[0].characterSetting, 'ZONE0_GLOBAL_dual_stream_v2');
    assert.equal(h1.state.cardUpdates[0].otherContentChat, 'ZONE1_SCENE_manor');
    assert.equal(h1.state.sendCalls.length, 1, 'Foreground must run exactly once even when settlement retries');
    assert.equal(h1.state.chatCalls.length, 2, 'Settlement SUMMARY must retry once after retryable_settlement');
    assert.equal(h1.state.chatCalls[0].functionType, 'SUMMARY');
    assert.equal(h1.state.chatCalls[0].enableThinking, false, 'Auto mode attempt 1 must be non-thinking for speed');
    assert.equal(h1.state.chatCalls[1].enableThinking, true, 'Auto mode attempt 2 must auto-escalate enableThinking=true');
    assert(h1.state.chatCalls[1].turns[1].content.includes('evidence需为正文子串'));
    assert.deepEqual(h1.state.streamPushes.map(p => p.stage), ['thinking', 'streaming', 'settling', 'settling_retry']);
    assert.equal(h1.state.streamPushes[h1.state.streamPushes.length - 1].messages.length, 2);
    assert.equal(h1.config.liveSession.turnCount, 1);
    assert.equal(h1.config.liveSession.lastCommittedSeq, 1);
    assert.equal(h1.config.liveSession.dirty, false);

    // Turn 2 in same location/cast: same chatId, ZERO character.update calls!
    h1.task = { ...h1.task, request_id: 'r2', lease: 'L2' };
    h1.state.retryableFirst = false;
    const sess2 = await vm.runInContext('liveSession(config, model, task)', h1);
    assert.equal(sess2.chatId, sess1.chatId);
    assert.equal(sess2.isFresh, false);
    h1.session = sess2;
    await vm.runInContext('executeSession(config, task, model, session)', h1);
    assert.equal(h1.state.cardUpdates.length, 1, 'Turn 2 same scene must NOT rewrite card prefixes');
    assert.equal(h1.config.liveSession.turnCount, 2);
    console.log('PASS dual-stage turn1+retry+turn2: 1 card sync across 2 turns, adaptive thinking escalation on retry, streaming pushes ordered');

    // 2. Clean session rollover on scope change, maxTurns, and dirty flag.
    h1.task = { ...h1.task, request_id: 'r3', interaction_scope: '公司|沈知韫|' };
    const sessScope = await vm.runInContext('liveSession(config, model, task)', h1);
    assert.notEqual(sessScope.chatId, sess2.chatId, 'Scope change must cleanly roll over v2 session');
    assert.equal(sessScope.isFresh, true);

    h1.config.liveSession.turnCount = 10;
    h1.task = { ...h1.task, request_id: 'r4', interaction_scope: '公司|沈知韫|' };
    const sessMax = await vm.runInContext('liveSession(config, model, task)', h1);
    assert.notEqual(sessMax.chatId, sessScope.chatId, 'Hitting maxTurns must cleanly roll over v2 session');

    h1.config.liveSession.dirty = true;
    h1.task = { ...h1.task, request_id: 'r5', interaction_scope: '公司|沈知韫|' };
    const sessDirty = await vm.runInContext('liveSession(config, model, task)', h1);
    assert.notEqual(sessDirty.chatId, sessMax.chatId, 'Dirty session must roll over cleanly');
    console.log('PASS v2 clean rollover on scope change, maxTurns=10, and dirty error state');

    // 3. SUMMARY unbound -> graceful auto-fallback to CHAT with enableThinking: false.
    const hFallback = createHarness({ summaryBound: false });
    hFallback.model = model;
    hFallback.task = {
        request_id: 'rf1', lease: 'LF1', entry_mode: 'live_interaction', save_epoch: 'ep1',
        interaction_scope: '徐家主宅|沈知韫|', service_epoch: 'srv1',
        reading_preflight: 1, live_reading_revision: 2, action_contract_revision: 1,
        material_delivery_revision: 1, material_delivery_v2: 1, dual_stage_protocol: 1,
    };
    hFallback.session = await vm.runInContext('liveSession(config, model, task)', hFallback);
    await vm.runInContext('executeSession(config, task, model, session)', hFallback);
    assert.equal(hFallback.state.chatCalls[0].functionType, 'CHAT');
    assert.equal(hFallback.state.chatCalls[0].enableThinking, false);
    const report = vm.runInContext('runtimeReport(config)', hFallback);
    assert.equal(report.settlement_fallback, true);
    assert.equal(report.settlement_thinking_mode, 'auto');
    console.log('PASS SUMMARY unbound graceful auto-fallback to CHAT with auto thinking mode');

    // 3b. Verify parseStreamMessages allowPlayerDialogue caps at 3 and strips Fish tags on 徐志北.
    const faithfulSample = '[D:徐志北] [whisper] 第一句。\n[D:徐志北] 第二句。\n[D:徐志北] 第三句。\n[D:徐志北] 第四句超限。\n[D:苏婉青] 场外。\n[D:沈知韫] 明白。\n';
    const parsedFaithful = h1.parseStreamMessages(faithfulSample, ['沈知韫'], true, true);
    assert.equal(parsedFaithful.filter(m => m.speaker === '徐志北').length, 3);
    assert.equal(parsedFaithful[0].text, '第一句。', 'Fish tags on muted 徐志北 dialogue must be stripped');
    assert.equal(parsedFaithful.some(m => m.speaker === '苏婉青'), false);
    const parsedSilent = h1.parseStreamMessages(faithfulSample, ['沈知韫'], true, false);
    assert.equal(parsedSilent.filter(m => m.speaker === '徐志北').length, 0);

    // 4. Single-stage slim mode (dualStageEnabled=false): no /preflight, returns body with __meta.
    const hSingle = createHarness({ dualStageEnabled: false });
    hSingle.model = model;
    hSingle.task = {
        request_id: 'rs1', lease: 'LS1', entry_mode: 'live_interaction', save_epoch: 'ep1',
        interaction_scope: '徐家主宅|沈知韫|', service_epoch: 'srv1',
        reading_preflight: 1, live_reading_revision: 2, action_contract_revision: 1,
        material_delivery_revision: 1, material_delivery_v2: 1, dual_stage_protocol: 1,
    };
    hSingle.session = await vm.runInContext('liveSession(config, model, task)', hSingle);
    const singleOut = await vm.runInContext('executeSession(config, task, model, session)', hSingle);
    assert.equal(hSingle.state.chatCalls.length, 0, 'Single-stage mode must not invoke SUMMARY');
    assert.equal(singleOut.__meta.isV2, true);
    assert.equal(JSON.parse(singleOut.text).operation, null);
    console.log('PASS single_prefix_v2 mode skips /preflight and normalizes wire JSON cleanly');

    // 5. CLI commands /storybridge mode, settlement & thinking.
    h1.config.inFlight = null;
    vm.runInContext('startMonitor = () => {};', h1);
    const cmdSingle = await vm.runInContext('bridgeCommand({eventPayload:{args:["mode","single"]}})', h1);
    assert(cmdSingle.stdout.includes('单阶段精简'));
    assert.equal(h1.config.dualStageEnabled, false);
    const cmdDual = await vm.runInContext('bridgeCommand({eventPayload:{args:["mode","dual"]}})', h1);
    assert(cmdDual.stdout.includes('双阶段流式'));
    assert.equal(h1.config.dualStageEnabled, true);
    const cmdThinkOff = await vm.runInContext('bridgeCommand({eventPayload:{args:["thinking","off"]}})', h1);
    assert.equal(cmdThinkOff.json.settlementThinkingMode, 'off');
    const cmdThinkAuto = await vm.runInContext('bridgeCommand({eventPayload:{args:["thinking","auto"]}})', h1);
    assert.equal(cmdThinkAuto.json.settlementThinkingMode, 'auto');
    const cmdSlot = await vm.runInContext('bridgeCommand({eventPayload:{args:["settlement","MEMORY"]}})', h1);
    assert(cmdSlot.stdout.includes('MEMORY'));
    assert.equal(h1.config.settlementFunctionType, 'MEMORY');
    console.log('PASS /storybridge mode & settlement CLI commands');

    // 6. parseStreamMessages handles split `---\nDECISION---` and bare dividers cleanly without leaking options.
    const splitRaw = '[N] 冷气往下沉。\n[A:沈知韫] 她看着你手里的文件夹，没有催。\n\n---\nDECISION---\nPROMPT: 局面\nA: 一\nB: 二\nC: 三\n';
    const parsedComplete = h1.parseStreamMessages(splitRaw, ['沈知韫'], true);
    assert.equal(parsedComplete.length, 2);
    assert.equal(parsedComplete[1].text, '她看着你手里的文件夹，没有催。');
    const parsedStreamingDivider = h1.parseStreamMessages('[A:沈知韫] 她没有催。\n\n---\n', ['沈知韫'], false);
    assert.equal(parsedStreamingDivider.length, 1);
    assert.equal(parsedStreamingDivider[0].text, '她没有催。');
    console.log('PASS parseStreamMessages cleanly splits multi-line ---\\nDECISION--- and skips bare dividers');

    // 7. 101 regression: JS parseStreamMessages splits mixed [D:] action+quote, strips outer quotes & [A:] Fish tags, preserves opening narration.
    const raw101 = [
        '书房里冷气偏低，台灯只照亮桌沿。',
        '[A:沈知韫] [soft sigh] 她揉了揉眉心。',
        '[D:沈知韫] 她端起来抿了一口，没抬眼：“[calm low voice] 几点了，还端着水往书房跑。”',
        '[D:徐念薇] “下周三开幕，评审刚换成周教授。”',
        '---DECISION---',
        'PROMPT: 两人都看着你。',
        'A: 问画展日期。',
        'B: 替她理好画册。',
        'C: 出门去公司。',
    ].join('\n');
    const parsed101 = h1.parseStreamMessages(raw101, ['沈知韫', '徐念薇'], true);
    assert.equal(parsed101.length, 5, 'Expected opening narration + action + split(action+dialogue) + pure dialogue');
    assert.deepEqual(parsed101[0], { kind: 'narration', speaker: '', text: '书房里冷气偏低，台灯只照亮桌沿。' });
    assert.deepEqual(parsed101[1], { kind: 'action', speaker: '沈知韫', text: '她揉了揉眉心。' });
    assert.deepEqual(parsed101[2], { kind: 'action', speaker: '沈知韫', text: '她端起来抿了一口，没抬眼。' });
    assert.deepEqual(parsed101[3], { kind: 'dialogue', speaker: '沈知韫', text: '[calm low voice] 几点了，还端着水往书房跑。' });
    assert.deepEqual(parsed101[4], { kind: 'dialogue', speaker: '徐念薇', text: '下周三开幕，评审刚换成周教授。' });
    console.log('PASS 101 JS parseStreamMessages splits mixed [D:] action+quote and strips [A:] Fish tags');

    // 8. cancelWaitSleep immediately resolves pending waitSleep (prevents waitLoop deadlock).
    const sleepStart = Date.now();
    const sleepPromise = vm.runInContext('waitSleep(60000)', h1);
    vm.runInContext('cancelWaitSleep()', h1);
    await sleepPromise;
    assert(Date.now() - sleepStart < 1000, 'cancelWaitSleep must resolve waitSleep immediately without hanging');
    console.log('PASS cancelWaitSleep resolves pending waitSleep cleanly');

    // 9. http() checks HTTP statusCode before JSON.parse (HTML 500 keeps statusCode 500; 200 non-JSON throws clear error).
    const rawNetBox = {
        exports: {}, console, setTimeout, clearTimeout, setInterval, clearInterval,
        PluginConfig: { use: async () => ({ endpoint: 'http://127.0.0.1:5000' }), flush: async () => {} },
        ToolPkg: { ipc: { on() {} } },
        Tools: { Net: { http: async () => ({ statusCode: 500, content: '<html>500 Internal Server Error</html>' }) }, Chat: {} },
    };
    vm.runInNewContext(source, rawNetBox);
    await assert.rejects(
        () => vm.runInContext("http('/api/story/tasks')", rawNetBox),
        err => err && err.statusCode === 500 && /500/.test(err.message)
    );
    rawNetBox.Tools.Net.http = async () => ({ statusCode: 200, content: '<html>not json</html>' });
    await assert.rejects(
        () => vm.runInContext("http('/api/story/tasks')", rawNetBox),
        err => err && /非JSON/.test(err.message)
    );
    console.log('PASS http() prioritizes HTTP statusCode over JSON.parse and flags non-JSON 2xx responses');

    // 10. pulse() stops heartbeat AND invokes onLeaseLost callback on HTTP 409.
    let capturedCb = null, clearedId = null, leaseLostCount = 0;
    const rawPulseBox = {
        exports: {}, console, setTimeout, clearTimeout,
        setInterval: cb => { capturedCb = cb; return 42; },
        clearInterval: id => { clearedId = id; },
        PluginConfig: { use: async () => ({ endpoint: 'http://127.0.0.1:5000' }), flush: async () => {} },
        ToolPkg: { ipc: { on() {} } },
        Tools: { Net: { http: async () => ({ statusCode: 409, content: JSON.stringify({ error: 'lease expired' }) }) }, Chat: {} },
        onLost: () => { leaseLostCount += 1; },
    };
    vm.runInNewContext(source, rawPulseBox);
    vm.runInContext("pulse('req-409', 'L409', 'tok', 'live_interaction', onLost)", rawPulseBox);
    assert(typeof capturedCb === 'function');
    await capturedCb();
    assert.equal(clearedId, 42, 'pulse must clearInterval on 409');
    assert.equal(leaseLostCount, 1, 'pulse must invoke onLeaseLost callback on 409');
    console.log('PASS pulse() stops interval and triggers onLeaseLost cancellation on HTTP 409');

    // 11. normalizeSettlementJson strips <think> blocks and extracts balanced JSON from wrapped prose.
    const wrapped = '<think>分析中... {fake: 1}</think>\n```json\n{"operation":"","handoff":"","checks":{"intent":"i","knowledge":"k","action":"a","pace":"p"},"resolution":{"category":"SYSTEM","basis":"b","clock":{"day":1,"time":"09:10","basis":"c"},"events":[],"memory":{"fact":"","compact":"","transfers":{}},"conditions":"","sleep":{"kind":"none","start":"","evidence":""},"task":"","items":[]},"quality_flags":[]}\n```';
    const normObj = h1.normalizeSettlementJson(wrapped);
    assert.equal(normObj.operation, null);
    assert.equal(normObj.resolution.category, 'SYSTEM');
    // Also handles trailing commentary AFTER a leading '{' JSON object!
    const trailingProse = '{"operation":"","handoff":"","checks":{"intent":"i","knowledge":"k","action":"a","pace":"p"},"resolution":{"category":"SYSTEM","basis":"b","clock":{"day":1,"time":"09:10","basis":"c"},"events":[],"memory":{"fact":"","compact":"","transfers":{}},"conditions":"","sleep":{"kind":"none","start":"","evidence":""},"task":"","items":[]},"quality_flags":[]}\n以上为本轮结算（已核对{规则}）。';
    const normTrailing = h1.normalizeSettlementJson(trailingProse);
    assert.equal(normTrailing.operation, null);
    assert.equal(normTrailing.resolution.category, 'SYSTEM');
    // Unclosed <think> throws clear truncation error
    assert.throws(
        () => h1.normalizeSettlementJson('<think>还在思考中没有结束...'),
        /思考未结束或回复被截断/
    );
    console.log('PASS normalizeSettlementJson handles trailing prose after leading brace and unclosed <think>');

    // 12. Stage 2 failure attaches stage1Checkpoint to thrown error; Stage-2-only resume skips Stage 1 (0 main LLM calls).
    const hFail = createHarness({ settlementJson: '这不是JSON纯废话' });
    const failModel = { key: 'prov:gemini-4', provider_id: 'prov', model_id: 'gemini-4' };
    const failTask = {
        request_id: 'req-cp-bridge', lease: 'L-cp-1', entry_mode: 'live_interaction',
        save_epoch: 'ep-cp', service_epoch: 'svc-1', material_delivery_v2: 1,
        dual_stage_protocol: 1, interaction_scope: '徐家主宅|沈知韫',
    };
    const failSess = await hFail.liveSession(hFail.config, failModel, failTask);
    let capturedErr = null;
    try {
        await hFail.executeSessionV2(hFail.config, failTask, failModel, failSess);
    } catch (e) {
        capturedErr = e;
    }
    assert(capturedErr, 'Stage 2 non-JSON 3x must throw');
    assert(capturedErr.stage1Checkpoint, 'Stage 2 failure must attach stage1Checkpoint');
    assert(capturedErr.stage1Checkpoint.foreground_text.includes('暖光漫过桌面'));
    assert.equal(hFail.state.sendCalls.length, 1, 'Stage 1 ran once before Stage 2 failed');
    assert.equal(hFail.state.chatCalls.length, 3, 'Stage 2 retried 3 times');
    assert.equal(hFail.config.liveSession.dirty, true, 'Dirty flag stays true on failure for safety');

    // Now resume with stage1Checkpoint -> MUST skip Stage 1 (0 sendCalls), reuse same chat, commit with generation_passes=0!
    const hResume = createHarness({
        liveSession: { ...hFail.config.liveSession },
        stage1Checkpoint: capturedErr.stage1Checkpoint,
    });
    const resumeTask = { ...failTask, lease: 'L-cp-2', resume_stage2: true };
    const resumeSess = await hResume.liveSession(hResume.config, failModel, resumeTask);
    assert.equal(resumeSess.chatId, failSess.chatId, 'Resume must preserve same live chat session');
    const resumeRes = await hResume.executeSessionV2(hResume.config, resumeTask, failModel, resumeSess);
    assert.equal(resumeRes.__alreadyDelivered, true);
    assert.equal(hResume.state.sendCalls.length, 0, 'Stage-2-only resume MUST make 0 main LLM calls!');
    assert.equal(hResume.state.chatCalls.length, 1, 'Stage 2 ran once and succeeded');
    assert.equal(hResume.state.resultPosts[0].timing.generation_passes, 0);
    assert.equal(hResume.state.resultPosts[0].conversation_audit.settlement_audit.resumed_stage2, true);
    assert.equal(hResume.config.liveSession.dirty, false, 'Same-chat resume commit clears dirty flag');
    console.log('PASS Stage 1 checkpoint attached on Stage 2 failure and Stage-2-only resume skips main LLM (0 calls)');
}

run().catch(e => { console.error(e); process.exitCode = 1; });

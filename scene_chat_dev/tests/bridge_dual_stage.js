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
        prefixSyncs: [],
        extStore: new Map(),
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
            callDependency: async (dep, method) => {
                throw new Error('v2.2.0 must not call external dependency: ' + dep + ':' + method);
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
                writeExtension: async (target, value) => {
                    state.extStore.set(target.chatId, JSON.parse(JSON.stringify(value)));
                    if (value && value.zone0Sha) state.prefixSyncs.push(value);
                    return { extension: value };
                },
                readExtension: async (target) => ({
                    extension: state.extStore.get(target.chatId) || null,
                }),
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

    // 1. Dual-stage turn 1 + settlement retry + turn 2 prefix cache hit (zero redundant prefix sync!)
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
    assert.equal(sess1.participantId, 'model:chat');
    h1.session = sess1;
    const out1 = await vm.runInContext('executeSession(config, task, model, session)', h1);
    assert.equal(out1.__alreadyDelivered, true);
    assert.equal(h1.state.prefixSyncs.length, 1, 'Turn 1 must sync Zone 0 + Zone 1 into native chat extension once');
    assert.equal(h1.state.prefixSyncs[0].systemPrefix, 'ZONE0_GLOBAL_dual_stream_v2\n\nZONE1_SCENE_manor');
    assert.equal(h1.state.sendCalls.length, 1, 'Foreground must run exactly once even when settlement retries');
    assert.equal(h1.state.sendCalls[0].turn.participantId, 'model:chat');
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

    // Turn 2 in same location/cast: same chatId, ZERO redundant writeExtension prefix syncs!
    h1.task = { ...h1.task, request_id: 'r2', lease: 'L2' };
    h1.state.retryableFirst = false;
    const sess2 = await vm.runInContext('liveSession(config, model, task)', h1);
    assert.equal(sess2.chatId, sess1.chatId);
    assert.equal(sess2.isFresh, false);
    h1.session = sess2;
    await vm.runInContext('executeSession(config, task, model, session)', h1);
    assert.equal(h1.state.prefixSyncs.length, 1, 'Turn 2 same scene must NOT rewrite chat extension prefixes');
    assert.equal(h1.config.liveSession.turnCount, 2);
    console.log('PASS dual-stage turn1+retry+turn2: 1 native extension sync across 2 turns, adaptive thinking escalation on retry, streaming pushes ordered');

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
    // 13. v2.3.0: prefs_epoch triggers clean rollover, session_meta commits ONLY on committed, and monitor token cache + 6s/30s backoff work.
    const hMeta = createHarness({});
    const metaModel = { key: 'prov:gemini-4', provider_id: 'prov', model_id: 'gemini-4' };
    // Intercept box.http to return session_meta and capture outgoing material opts.
    const origHttp = hMeta.http;
    const matRequests = [];
    let forceCommitReject = false;
    hMeta.http = async (urlPath, body, token, timeout) => {
        if (urlPath.endsWith('/material')) {
            matRequests.push(JSON.parse(JSON.stringify(body)));
            const data = await origHttp(urlPath, body, token, timeout);
            data.session_meta = {
                zone1_flags: { vig: false, intl: false },
                injected_refs: ['徐承邺'],
                injected_guides: ['vig'],
                memory_fps: ['anc-1:abcd1234'],
                state_hashes: { panels: 'h1', intimacy: 'h2' },
            };
            return data;
        }
        if (urlPath.endsWith('/result') && forceCommitReject) {
            const err = new Error('模拟校验拒绝');
            err.statusCode = 400;
            throw err;
        }
        return origHttp(urlPath, body, token, timeout);
    };
    const tMeta1 = {
        request_id: 'req-meta-1', lease: 'L-meta-1', entry_mode: 'live_interaction',
        save_epoch: 'ep-m', prefs_epoch: 'pe-1', service_epoch: 'svc-1',
        material_delivery_v2: 1, dual_stage_protocol: 1, interaction_scope: '徐家主宅|沈知韫',
    };
    // First attempt rejected by server 400 -> session_meta MUST NOT be persisted!
    forceCommitReject = true;
    const sMeta1 = await hMeta.liveSession(hMeta.config, metaModel, tMeta1);
    let rejectCaught = false;
    try { await hMeta.executeSessionV2(hMeta.config, tMeta1, metaModel, sMeta1); } catch (_) { rejectCaught = true; }
    assert(rejectCaught, '400 rejection must throw');
    assert.deepEqual(hMeta.config.liveSession.injectedRefs || [], [], 'rejected turn MUST NOT persist injectedRefs');
    assert.deepEqual(hMeta.config.liveSession.injectedMemoryFps || [], [], 'rejected turn MUST NOT persist memory_fps');

    // Retry succeeds -> session_meta MUST be committed and forwarded on next turn!
    forceCommitReject = false;
    hMeta.config.liveSession.dirty = false;
    const sMeta2 = await hMeta.liveSession(hMeta.config, metaModel, { ...tMeta1, request_id: 'req-meta-2', lease: 'L-meta-2' });
    await hMeta.executeSessionV2(hMeta.config, { ...tMeta1, request_id: 'req-meta-2', lease: 'L-meta-2' }, metaModel, sMeta2);
    assert.deepEqual(hMeta.config.liveSession.injectedRefs, ['徐承邺']);
    assert.deepEqual(hMeta.config.liveSession.injectedGuides, ['vig']);
    assert.deepEqual(hMeta.config.liveSession.injectedMemoryFps, ['anc-1:abcd1234']);
    assert.deepEqual(hMeta.config.liveSession.stateHashes, { panels: 'h1', intimacy: 'h2' });

    // Next turn in same session forwards synced_zone1_flags, injected_refs, injected_guides, injected_memory_fps, prev_state_hashes!
    const sMeta3 = await hMeta.liveSession(hMeta.config, metaModel, { ...tMeta1, request_id: 'req-meta-3', lease: 'L-meta-3' });
    assert.equal(sMeta3.isFresh, false, 'same prefs_epoch & scope reuses session');
    await hMeta.executeSessionV2(hMeta.config, { ...tMeta1, request_id: 'req-meta-3', lease: 'L-meta-3' }, metaModel, sMeta3);
    const lastMat = matRequests[matRequests.length - 1];
    assert.deepEqual(lastMat.synced_zone1_flags, { vig: false, intl: false });
    assert.deepEqual(lastMat.injected_refs, ['徐承邺']);
    assert.deepEqual(lastMat.injected_guides, ['vig']);
    assert.deepEqual(lastMat.injected_memory_fps, ['anc-1:abcd1234']);
    assert.deepEqual(lastMat.prev_state_hashes, { panels: 'h1', intimacy: 'h2' });

    // Changing prefs_epoch triggers clean rollover!
    const sMetaRoll = await hMeta.liveSession(hMeta.config, metaModel, { ...tMeta1, request_id: 'req-meta-4', prefs_epoch: 'pe-2' });
    assert.equal(sMetaRoll.isFresh, true, 'changed prefs_epoch must roll over to fresh session');
    assert.notEqual(sMetaRoll.chatId, sMeta3.chatId);

    // Monitor token cache & 6s/30s adaptive backoff verification
    let bridgeInfoCalls = 0, controlCalls = 0, rejectFirstToken = false;
    const monBox = {
        exports: {}, console, setTimeout, clearTimeout, setInterval, clearInterval,
        PluginConfig: { use: async () => ({ endpoint: 'http://127.0.0.1:5000', workspacePath: '/w' }), flush: async () => {} },
        ToolPkg: { ipc: { on() {} } },
        Tools: {
            Net: {
                http: async (opts) => {
                    if (opts.url.endsWith('/api/story/bridge-info')) {
                        bridgeInfoCalls += 1;
                        return { statusCode: 200, content: JSON.stringify({ token: 'tok-' + bridgeInfoCalls }) };
                    }
                    if (opts.url.endsWith('/api/story/worker/control')) {
                        controlCalls += 1;
                        if (rejectFirstToken && opts.headers && opts.headers['X-Story-Bridge'] === 'tok-1') {
                            return { statusCode: 401, content: JSON.stringify({ error: 'stale token' }) };
                        }
                        return { statusCode: 200, content: JSON.stringify({ command: null, service_epoch: 'ep-1' }) };
                    }
                    return { statusCode: 200, content: '{}' };
                },
            },
            SoftwareSettings: {
                exec: async () => JSON.stringify({ success: true, data: { models: [], bindings: [] } }),
            },
            Chat: {},
        },
    };
    vm.runInNewContext(source, monBox);
    const now0 = 1_000_000;
    monBox.exports.markBridgeActivity(now0);
    assert.equal(monBox.exports.computeMonitorDelayMs(now0 + 10_000), 6000, 'active monitor runs every 6s');
    assert.equal(monBox.exports.computeMonitorDelayMs(now0 + 65_000), 30000, 'idle monitor (>60s) backs off to 30s');
    await monBox.exports.monitor();
    await monBox.exports.monitor();
    assert.equal(bridgeInfoCalls, 1, 'cached bridge token must avoid repeated /bridge-info calls');
    assert.equal(controlCalls, 2);
    // 401 automatically invalidates cached token and refreshes cleanly once!
    rejectFirstToken = true;
    await monBox.exports.monitor();
    assert.equal(bridgeInfoCalls, 2, '401 must invalidate cached token and re-fetch /bridge-info');
    console.log('PASS v2.3.0 prefs_epoch rollover, commit-only session_meta, and monitor token-cache + 6s/30s backoff');

    // 14. v2.3.1: buildTailHook strips unspoken dialogue ｜subtext & applyCommittedSessionMeta preserves char_stage/unlocked_secrets.
    const hook = monBox.exports.buildTailHook([
        { kind: 'action', speaker: '苏婉青', text: '她｛表面镇定｜指尖发颤｝放下杯子。' },
        { kind: 'dialogue', speaker: '苏婉青', text: '｛没事，快递短信。｜还好没被发现我替承邺盯着主宅｝' },
    ]);
    assert.ok(hook.includes('没事，快递短信。'), 'tailHook must keep spoken surface dialogue');
    assert.ok(!hook.includes('替承邺盯着主宅'), 'tailHook MUST strip unspoken dialogue ｜subtext');
    assert.ok(hook.includes('指尖发颤'), 'tailHook keeps visible action slip');
    const mergedMeta = monBox.exports.applyCommittedSessionMeta({}, {
        zone1_flags: { vig: false, intl: false, char_stage: { 苏婉青: 'stage1' }, unlocked_secrets: ['INTEL-002'] },
    });
    assert.deepEqual(mergedMeta.zone1Flags, {
        vig: false, intl: false, char_stage: { 苏婉青: 'stage1' }, unlocked_secrets: ['INTEL-002'],
    });
    console.log('PASS v2.3.1 subtext-stripped tailHook and char_stage/unlocked_secrets session_meta preservation');

    // 15. v2.3.3: actualSeq reads res.task.receipt.state_version AND parseStreamMessages matches Python hardening.
    const hSeq = createHarness({
        fgText: '好的，以下为本段演播：\n```text\n［N］ [sigh] 暖灯微暗。\n［A：沈知韫］ <whisper>她指尖轻叩桌面。</whisper>\n［D：沈知韫］\n<stress>志北</stress>，<hallucinated>过来</hallucinated>坐。\n[D:徐志北] [轻笑] <whisper>这就来。</whisper>\n```\n以上是本段内容。\n---DECISION---\nPROMPT: 下一步？\nA: 坐下喝茶。\nB: 轻握她的手。\nC: 谈公事。\n',
    });
    hSeq.model = model;
    hSeq.task = {
        request_id: 'rseq1', lease: 'LSEQ1', entry_mode: 'live_interaction', save_epoch: 'ep1',
        interaction_scope: '徐家主宅|沈知韫|', service_epoch: 'srv1',
        reading_preflight: 1, live_reading_revision: 2, action_contract_revision: 1,
        material_delivery_revision: 1, material_delivery_v2: 1, dual_stage_protocol: 1,
    };
    const origSeqHttp = hSeq.http;
    hSeq.http = async (urlPath, body) => {
        const resp = await origSeqHttp(urlPath, body);
        if (urlPath.endsWith('/result')) {
            return { task: { request_id: 'rseq1', status: 'committed', receipt: { state_version: 42 } } };
        }
        return resp;
    };
    vm.runInContext('http = box_http;', Object.assign(hSeq, { box_http: hSeq.http }));
    hSeq.session = await vm.runInContext('liveSession(config, model, task)', hSeq);
    await vm.runInContext('executeSession(config, task, model, session)', hSeq);
    assert.equal(hSeq.config.liveSession.lastCommittedSeq, 42, 'actualSeq must extract res.task.receipt.state_version');
    const parsedMsgs = hSeq.state.streamPushes[hSeq.state.streamPushes.length - 1].messages;
    assert.equal(parsedMsgs.length, 4, 'Must parse fenced full-width & newline-header stream lines into 4 messages');
    assert.equal(parsedMsgs[0].kind, 'narration');
    assert.ok(!parsedMsgs[0].text.includes('[sigh]'), '[N] must strip voice tags');
    assert.equal(parsedMsgs[1].kind, 'action');
    assert.ok(!parsedMsgs[1].text.includes('<whisper>'), '[A] must strip XML voice tags');
    assert.equal(parsedMsgs[2].kind, 'dialogue');
    assert.equal(parsedMsgs[2].speaker, '沈知韫');
    assert.ok(parsedMsgs[2].text.includes('<stress>志北</stress>'), 'Allowed Drama 3 XML <stress> must be preserved');
    assert.ok(!parsedMsgs[2].text.includes('<hallucinated>'), 'Unknown XML tags must be stripped');
    assert.equal(parsedMsgs[3].speaker, '徐志北');
    assert.ok(!parsedMsgs[3].text.includes('[轻笑]') && !parsedMsgs[3].text.includes('<whisper>'), '[D:徐志北] must strip all voice/XML tags');
    console.log('PASS v2.3.3 task.receipt.state_version actualSeq and Python-parity stream parser hardening');
}

run().catch(e => { console.error(e); process.exitCode = 1; });

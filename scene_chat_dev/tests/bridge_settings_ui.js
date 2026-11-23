'use strict';
/**
 * Tests v2.1.0 bridge native settings UI registration, model catalog,
 * fixed primary model override, direct Operit function-slot rebinding,
 * settlement thinking toggle, max-turns control, and Compose DSL UI rendering.
 */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');

const MAIN_PATH = path.join(__dirname, '../local.story.operit_bridge/main.js');
const UI_PATH = path.join(__dirname, '../local.story.operit_bridge/ui/settings.ui.js');
const mainSource = fs.readFileSync(MAIN_PATH, 'utf8');
const uiSource = fs.readFileSync(UI_PATH, 'utf8');

function createHarness() {
    const config = {
        enabled: false,
        endpoint: 'http://127.0.0.1:5000',
        functionType: 'CHAT',
        primaryModelMode: 'slot',
        primaryProviderId: '',
        primaryModelId: '',
        workspacePath: '/storage/emulated/0/互动对话项目/Gemini网页版',
        chatId: '',
        participantId: '',
        inFlight: null,
        outbox: null,
        liveSessionPolicy: 'continuous',
        dualStageEnabled: true,
        settlementFunctionType: 'SUMMARY',
        settlementThinking: false,
        maxTurnsPerSession: 10,
        liveSession: null,
    };

    const modelsList = [
        { providerId: 'google', providerName: 'Google', providerTypeId: 'gemini', endpoint: 'https://g', modelId: 'gemini-4', pricing: { inputPricePerMillion: 1 } },
        { providerId: 'google', providerName: 'Google', providerTypeId: 'gemini', endpoint: 'https://g', modelId: 'gemini-2.5-flash', pricing: { inputPricePerMillion: 0.1 } },
        { providerId: 'deepseek', providerName: 'DeepSeek', providerTypeId: 'openai', endpoint: 'https://ds', modelId: 'deepseek-4.1', pricing: { inputPricePerMillion: 0.5 } },
        { providerId: 'deepseek', providerName: 'DeepSeek', providerTypeId: 'openai', endpoint: 'https://ds', modelId: 'deepseek-v3.2', pricing: { inputPricePerMillion: 0.2 } },
    ];
    const bindings = {
        CHAT: { providerId: 'google', modelId: 'gemini-4' },
        SUMMARY: { providerId: 'google', modelId: 'gemini-2.5-flash' },
        TRANSLATION: { providerId: 'deepseek', modelId: 'deepseek-v3.2' },
    };

    const state = {
        registeredRoutes: [],
        registeredNav: [],
        registeredCommands: [],
        functionSetCalls: [],
        chatCalls: [],
        monitorPosts: [],
        ipcHandlers: {},
    };

    const box = {
        exports: {},
        console,
        setTimeout,
        clearTimeout,
        setInterval: () => 999,
        clearInterval: () => {},
        require: (modPath) => {
            if (modPath === './ui/settings.ui.js') {
                const fn = function placeholder() {};
                fn.__operit_toolpkg_module_path = 'ui/settings.ui.js';
                fn.__operit_toolpkg_export_name = 'default';
                return { default: fn };
            }
            throw new Error('Unexpected require: ' + modPath);
        },
        PluginConfig: { use: async () => config, flush: async () => {} },
        ToolPkg: {
            ipc: {
                on(ch, fn) { state.ipcHandlers[ch] = fn; },
                async call(ch, payload) { return await state.ipcHandlers[ch](payload); },
            },
            registerUiRoute(def) { state.registeredRoutes.push(def); },
            registerNavigationEntry(def) { state.registeredNav.push(def); },
            registerCoreCommand(def) { state.registeredCommands.push(def); },
            registerChatInputHook() {},
            registerAppLifecycleHook() {},
            callDependency: async (dep, method, args) => {
                if (method === 'character.list') return [];
                if (method === 'character.create') return { ...args.values, id: 'card-1' };
                if (method === 'character.get') return { id: 'card-1', marks: 'local.story.operit_bridge:readonly', name: '同席互动·项目只读', characterSetting: '', otherContentChat: '', chatModelBindingMode: 'FIXED_MODEL', chatProviderId: 'google', chatModelId: 'gemini-4', toolAccessConfig: {} };
                if (method === 'character.update') return { id: args.id, ...args.changes };
                if (method === 'chat.configuration.binding.read') return { selection: 'card:card-1' };
                throw new Error('unexpected dep: ' + method);
            },
        },
        Tools: {
            Models: {
                listSummaries: async () => ({ models: modelsList }),
            },
            SoftwareSettings: {
                exec: async (argv) => {
                    if (argv[0] === 'model' && argv[1] === 'function-list') {
                        return JSON.stringify({
                            bindings: Object.entries(bindings).map(([functionType, b]) => ({
                                functionType, providerId: b.providerId, modelId: b.modelId,
                            })),
                        });
                    }
                    if (argv[0] === 'model' && argv[1] === 'function-show') {
                        const b = bindings[argv[2]];
                        if (!b) return JSON.stringify({ success: false, error: 'unbound' });
                        return JSON.stringify({ functionType: argv[2], providerId: b.providerId, modelId: b.modelId });
                    }
                    if (argv[0] === 'model' && argv[1] === 'function-set') {
                        const [, , slot, prov, mod] = argv;
                        state.functionSetCalls.push({ slot, prov, mod });
                        bindings[slot] = { providerId: prov, modelId: mod };
                        return JSON.stringify({ functionType: slot, providerId: prov, modelId: mod, updated: true });
                    }
                    if (argv[0] === 'model' && argv[1] === 'show') {
                        const found = modelsList.find(m => m.providerId === argv[2] && m.modelId === argv[3]);
                        if (!found) return JSON.stringify({ success: false, error: 'not found' });
                        return JSON.stringify(found);
                    }
                    return JSON.stringify({ success: true });
                },
            },
            Chat: {
                call: async (req) => { state.chatCalls.push(req); return { text: '{}' }; },
                agentStatus: async () => ({ isIdle: true }),
            },
            Net: {
                http: async (opts) => {
                    if (opts.url.endsWith('/api/story/bridge-info')) {
                        return { statusCode: 200, content: JSON.stringify({ token: 'tok' }) };
                    }
                    if (opts.url.endsWith('/api/story/worker/control')) {
                        state.monitorPosts.push(JSON.parse(opts.body));
                        return { statusCode: 200, content: JSON.stringify({ command: null, story_protocol: 3 }) };
                    }
                    if (opts.url.endsWith('/api/story/tasks')) {
                        return { statusCode: 200, content: JSON.stringify({ story_protocol: 3, reading_preflight: 1 }) };
                    }
                    return { statusCode: 200, content: '{}' };
                },
            },
        },
    };

    vm.createContext(box);
    vm.runInContext(mainSource, box);
    return { box, config, state, bindings };
}

function makeMockComposeCtx(ipcCall) {
    const states = new Map();
    const refs = new Map();
    const toasts = [];
    const colorToken = (name) => ({ name, copy: () => ({ name }) });
    const makeMod = () => new Proxy({}, { get: () => () => makeMod() });
    const UI = new Proxy({}, {
        get: (_, type) => (props, children) => ({ type, props: props || {}, children }),
    });
    const ctx = {
        UI,
        Modifier: makeMod(),
        MaterialTheme: {
            colorScheme: new Proxy({}, { get: (_, k) => colorToken(String(k)) }),
        },
        useState(key, init) {
            if (!states.has(key)) states.set(key, init);
            return [states.get(key), (val) => states.set(key, val)];
        },
        useRef(key, init) {
            if (!refs.has(key)) refs.set(key, { current: init });
            return refs.get(key);
        },
        showToast(msg) { toasts.push(msg); },
    };
    const uiBox = {
        exports: {},
        console,
        ToolPkg: { ipc: { call: ipcCall } },
    };
    vm.createContext(uiBox);
    vm.runInContext(uiSource, uiBox);
    assert.strictEqual(typeof uiBox.exports.default, 'function', 'ui/settings.ui.js must export default screen');
    return { ctx, render: () => uiBox.exports.default(ctx), toasts };
}

function findNode(tree, predicate) {
    if (!tree) return null;
    if (Array.isArray(tree)) {
        for (const item of tree) {
            const hit = findNode(item, predicate);
            if (hit) return hit;
        }
        return null;
    }
    if (typeof tree !== 'object') return null;
    if (predicate(tree)) return tree;
    return findNode(tree.children, predicate) || findNode(tree.props && tree.props.content, predicate);
}

async function run() {
    // 1. Plugin registration registers native UI route + sidebar & toolbox navigation entries.
    {
        const { box, state } = createHarness();
        assert.strictEqual(box.exports.registerToolPkg(), true);
        assert.strictEqual(state.registeredRoutes.length, 1);
        assert.strictEqual(state.registeredRoutes[0].route, 'toolpkg:local.story.operit_bridge:ui:settings');
        assert.strictEqual(state.registeredRoutes[0].runtime, 'compose_dsl');
        assert.strictEqual(state.registeredRoutes[0].screen.__operit_toolpkg_module_path, 'ui/settings.ui.js');
        assert.deepStrictEqual(
            state.registeredNav.map(n => n.surface).sort(),
            ['main_sidebar_plugins', 'toolbox']
        );
        console.log('PASS 1: native settings UI route + sidebar/toolbox entries registered');
    }

    // 2. Backend IPC actions: ui_snapshot, fixed primary model, invalid model rollback, bind_function_slot, settlement_thinking, max_turns.
    {
        const { box, config, state, bindings } = createHarness();
        const snap = await box.exports.receive({ action: 'ui_snapshot' });
        const manifestVersion = JSON.parse(
            fs.readFileSync(path.join(__dirname, '../local.story.operit_bridge/manifest.json'), 'utf8')
        ).version;
        assert.strictEqual(snap.version, manifestVersion);
        // Verify JS streaming preview parser also cleanly handles 旁白：[N], bare 旁白：, and inline glued tags.
        const streamed = box.parseStreamMessages(
            '旁白：[N] 书房冷气偏低。\n[D:沈知韫] [low restrained voice] 还没睡？\n旁白：[N] 她抬手点了点文件。\n[D:沈知韫] 怎么看？ 旁白：[N] 她问得很平。\n旁白：冷气还在沉。\n',
            ['沈知韫'],
            true
        );
        assert.deepStrictEqual(Array.from(streamed, m => m.kind), ['narration', 'dialogue', 'narration', 'dialogue', 'narration', 'narration']);
        assert.strictEqual(streamed[0].text, '书房冷气偏低。');
        assert.strictEqual(streamed[1].text, '[low restrained voice] 还没睡？');
        assert.strictEqual(streamed[2].text, '她抬手点了点文件。');
        assert.strictEqual(streamed[3].text, '怎么看？');
        assert.strictEqual(streamed[4].text, '她问得很平。');
        assert.strictEqual(streamed[5].text, '冷气还在沉。');
        assert.strictEqual(snap.availableModels.length, 4);
        assert.strictEqual(snap.functionBindings.length, 3);
        assert.strictEqual(snap.primaryModelMode, 'slot');
        assert.strictEqual(snap.model.model_id, 'gemini-4');
        assert.strictEqual(snap.settlementModel.model_id, 'gemini-2.5-flash');

        // Switch primary model to fixed DeepSeek 4.1 -> CHAT slot remains untouched!
        const fixed = await box.exports.receive({
            action: 'primary_model',
            primaryModelMode: 'fixed',
            primaryProviderId: 'deepseek',
            primaryModelId: 'deepseek-4.1',
            includeCatalog: true,
        });
        assert.strictEqual(fixed.primaryModelMode, 'fixed');
        assert.strictEqual(fixed.model.function_type, 'FIXED');
        assert.strictEqual(fixed.model.model_id, 'deepseek-4.1');
        assert.strictEqual(bindings.CHAT.modelId, 'gemini-4', 'Fixed story primary must NOT touch global CHAT slot');

        // Invalid fixed model throws and preserves previous valid config.
        await assert.rejects(() => box.exports.receive({
            action: 'primary_model',
            primaryModelMode: 'fixed',
            primaryProviderId: 'ghost',
            primaryModelId: 'missing-model',
        }), /故事专属主模型未找到/);
        assert.strictEqual(config.primaryModelId, 'deepseek-4.1');

        // Directly rebind SUMMARY slot to deepseek-v3.2 via Operit model function-set!
        const rebound = await box.exports.receive({
            action: 'bind_function_slot',
            slot: 'SUMMARY',
            providerId: 'deepseek',
            modelId: 'deepseek-v3.2',
            useAsSettlement: true,
        });
        assert.strictEqual(state.functionSetCalls.length, 1);
        assert.deepStrictEqual(state.functionSetCalls[0], { slot: 'SUMMARY', prov: 'deepseek', mod: 'deepseek-v3.2' });
        assert.strictEqual(rebound.settlementModel.model_id, 'deepseek-v3.2');
        assert.strictEqual(rebound.settlementFallback, false);

        // Toggle settlementThinking + maxTurns + update_settings.
        const thinkOn = await box.exports.receive({ action: 'settlement_thinking', settlementThinking: true });
        assert.strictEqual(thinkOn.settlementThinking, true);
        const turns = await box.exports.receive({ action: 'max_turns', maxTurnsPerSession: 15 });
        assert.strictEqual(turns.maxTurnsPerSession, 15);
        assert.strictEqual(turns.liveSession.max_turns, 15);
        const adv = await box.exports.receive({
            action: 'update_settings',
            workspacePath: '/storage/emulated/0/custom/',
            endpoint: 'http://127.0.0.1:5055/',
        });
        assert.strictEqual(adv.workspacePath, '/storage/emulated/0/custom');
        assert.strictEqual(adv.endpoint, 'http://127.0.0.1:5055');
        console.log('PASS 2: primary fixed override, direct function-slot rebinding, thinking & max_turns IPC verified');
    }

    // 3. End-to-end Compose DSL settings.ui.js render + interactive clicks against real main.js IPC!
    {
        const { box, state } = createHarness();
        const { render, toasts } = makeMockComposeCtx((ch, payload) => state.ipcHandlers[ch](payload));

        // Initial render has onLoad hook -> triggers ui_snapshot.
        const initialTree = render();
        assert.strictEqual(typeof initialTree.props.onLoad, 'function');
        await initialTree.props.onLoad();

        // Re-render after load: verify all key interactive controls exist and work!
        let tree = render();
        const fixedChip = findNode(tree, n => n.props && n.props.key === 'primary-mode:fixed');
        assert(fixedChip, 'primary-mode:fixed FilterChip must render');
        fixedChip.props.onClick();
        await new Promise(r => setImmediate(r));
        await new Promise(r => setImmediate(r));

        tree = render();
        const fixedDropdown = findNode(tree, n => n.props && n.props.key === 'primary-fixed-model');
        assert(fixedDropdown, 'primary-fixed-model DropdownMenu must appear in fixed mode');
        // Index 0 in sorted availableModels is DeepSeek deepseek-4.1
        fixedDropdown.props.onClick(0);
        await new Promise(r => setImmediate(r));
        await new Promise(r => setImmediate(r));

        tree = render();
        const bindDropdown = findNode(tree, n => n.props && n.props.key === 'settlement-slot-bind-model');
        assert(bindDropdown, 'settlement-slot-bind-model DropdownMenu must render');
        // Pick deepseek-v3.2 (index 1 in sorted list: DeepSeek deepseek-4.1, DeepSeek deepseek-v3.2, Google ...)
        bindDropdown.props.onClick(1);
        tree = render();
        const bindBtn = findNode(tree, n => n.props && n.props.key === 'btn-bind-settlement-slot');
        assert(bindBtn, 'btn-bind-settlement-slot Button must render');
        bindBtn.props.onClick();
        await new Promise(r => setImmediate(r));
        await new Promise(r => setImmediate(r));
        assert.strictEqual(state.functionSetCalls.length, 1);
        assert.strictEqual(state.functionSetCalls[0].slot, 'SUMMARY');
        assert.strictEqual(state.functionSetCalls[0].mod, 'deepseek-v3.2');

        // Select settlement thinking mode chip ('on') + click +1 turn button.
        tree = render();
        const thinkAutoChip = findNode(tree, n => n.props && n.props.key === 'settlement-thinking-mode:auto');
        const thinkOnChip = findNode(tree, n => n.props && n.props.key === 'settlement-thinking-mode:on');
        assert(thinkAutoChip && thinkAutoChip.props.selected === true, 'settlement-thinking-mode:auto must default selected');
        assert(thinkOnChip, 'settlement-thinking-mode:on FilterChip must render');
        thinkOnChip.props.onClick();
        await new Promise(r => setImmediate(r));
        await new Promise(r => setImmediate(r));

        tree = render();
        const incBtn = findNode(tree, n => n.props && n.props.key === 'btn-turns-inc');
        assert(incBtn, 'btn-turns-inc button must render');
        incBtn.props.onClick();
        await new Promise(r => setImmediate(r));
        await new Promise(r => setImmediate(r));

        const finalSnap = await box.exports.receive({ action: 'status' });
        assert.strictEqual(finalSnap.primaryModelMode, 'fixed');
        assert.strictEqual(finalSnap.model.model_id, 'deepseek-4.1');
        assert.strictEqual(finalSnap.settlementModel.model_id, 'deepseek-v3.2');
        assert.strictEqual(finalSnap.settlementThinking, true);
        assert.strictEqual(finalSnap.settlementThinkingMode, 'on');
        assert.strictEqual(finalSnap.maxTurnsPerSession, 11);
        assert(toasts.length >= 4, 'UI should emit clear toast feedback');
        console.log('PASS 3: Compose DSL settings.ui.js end-to-end UI render & interaction tests passed');
    }
}

run().catch(err => {
    console.error('FAIL bridge_settings_ui:', err);
    process.exit(1);
});

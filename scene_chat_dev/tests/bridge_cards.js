'use strict';
/**
 * Verifies v2.2.0 native self-hosted session & hook architecture:
 * - Zero calls to com.operit.character_cards
 * - Defensive createNew input { 'com.operit.character_cards': { version: 1, selection: 'model:chat' } }
 * - Automatic migration of legacy v2.1.x card-bound sessions to native model:chat
 * - Tools.Chat.writeExtension persistence + cold-start Tools.Chat.readExtension hydration
 * - Native hooks: composeStorySystemPrompt, filterStoryTools, interceptStoryToolCall, finalizeStoryPrompt
 * - Zero interference on non-bridge user chats
 */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '../local.story.operit_bridge/main.js'), 'utf8');

function createBox(initialConfig = {}) {
    const config = {
        workspacePath: '/fixture',
        chatId: '',
        participantId: '',
        ...initialConfig,
    };
    const extStore = new Map();
    const calls = [];
    const createdInputs = [];
    let chatSeq = 0;

    const box = {
        exports: {},
        console,
        setTimeout,
        clearTimeout,
        setInterval,
        clearInterval,
        config,
        calls,
        extStore,
        createdInputs,
        PluginConfig: { flush: async () => {} },
        ToolPkg: {
            ipc: { on() {} },
            callDependency: async (dep, method) => {
                calls.push('dep:' + dep + ':' + method);
                throw new Error('v2.2.0 must NEVER call external plugin dependency: ' + dep + ':' + method);
            },
        },
        Tools: {
            Chat: {
                listChats: async ({ chat_ids }) => ({
                    chats: (chat_ids || []).filter(id => extStore.has(id) || id === 'legacy-card-chat').map(id => ({ id })),
                }),
                createNew: async (opts) => {
                    createdInputs.push(opts);
                    const id = 'native-chat-' + (++chatSeq);
                    return { chatId: id };
                },
                updateTitle: async () => {},
                agentStatus: async () => ({ isIdle: true }),
                writeExtension: async (target, value) => {
                    calls.push('writeExtension:' + target.chatId);
                    extStore.set(target.chatId, JSON.parse(JSON.stringify(value)));
                    return { extension: value };
                },
                readExtension: async (target) => {
                    calls.push('readExtension:' + target.chatId);
                    return { extension: extStore.has(target.chatId) ? extStore.get(target.chatId) : null };
                },
            },
            SoftwareSettings: {
                exec: async () => ({ success: true }),
            },
        },
    };
    vm.createContext(box);
    vm.runInContext(source, box);
    box.model = { key: '["CHAT","prov","gemini-4"]', provider_id: 'prov', model_id: 'gemini-4' };
    return box;
}

(async () => {
    // 1. Fresh native session creation: zero character_cards calls, defensive selection:'model:chat', writeExtension persisted.
    const b1 = createBox();
    const s1 = await vm.runInContext('ensureSession(config, model, "live")', b1);
    assert.strictEqual(s1.chatId, 'native-chat-1');
    assert.strictEqual(s1.participantId, 'model:chat');
    assert.strictEqual(b1.createdInputs.length, 1);
    assert.deepStrictEqual(JSON.parse(JSON.stringify(b1.createdInputs[0].input)), {
        'com.operit.character_cards': { version: 1, selection: 'model:chat' },
    });
    assert(!b1.calls.some(c => c.startsWith('dep:')), 'must not invoke any external plugin dependency');
    assert(b1.extStore.has('native-chat-1'), 'must persist bridge chat extension');
    assert.strictEqual(b1.extStore.get('native-chat-1').bridge, 'local.story.operit_bridge');
    assert.strictEqual(b1.extStore.get('native-chat-1').role, 'live');

    // 2. Legacy v2.1.x card-bound session auto-migrates to a clean native model:chat session.
    const bMig = createBox({ chatId: 'legacy-card-chat', participantId: 'old-card-uuid-123' });
    const sMig = await vm.runInContext('ensureSession(config, model, "live")', bMig);
    assert.strictEqual(sMig.chatId, 'native-chat-1', 'must open clean native chat instead of reusing card-bound chat');
    assert.strictEqual(sMig.participantId, 'model:chat');
    assert.strictEqual(bMig.config.participantId, 'model:chat');

    // 3. Cold-start hydration via readExtension + syncLivePrefixes.
    await vm.runInContext('syncLivePrefixes(config, model, { chatId: "native-chat-1", participantId: "model:chat" }, "ZONE0_TEXT", "ZONE1_TEXT", "sha0", "sha1")', b1);
    // Clear in-memory registry to simulate app restart!
    vm.runInContext('bridgeChatRegistry.clear(); nonBridgeChatCache.clear();', b1);
    const hydrated = await b1.exports.resolveBridgeChatState('native-chat-1');
    assert(hydrated && hydrated.systemPrefix === 'ZONE0_TEXT\n\nZONE1_TEXT', 'cold restart must hydrate frozen prefix via readExtension');
    assert.strictEqual(await b1.exports.resolveBridgeChatState('normal-user-chat'), null, 'non-bridge chat must resolve null');

    // 4. System prompt compose hook: prepends Zone 0/1, strips PACKAGE SYSTEM boilerplate, leaves non-bridge chats untouched.
    const composed = await b1.exports.composeStorySystemPrompt({
        eventPayload: {
            stage: 'compose_system_prompt_sections',
            chatId: 'native-chat-1',
            systemPrompt: '工作区指南\n\n包系统：\n- 使用 use_package 激活\n\n可用工具\nread_file_part',
        },
    });
    assert(composed && composed.systemPrompt.startsWith('ZONE0_TEXT\n\nZONE1_TEXT\n\n工作区指南'));
    assert(!composed.systemPrompt.includes('包系统：'), 'must strip package system boilerplate from bridge chat');
    assert(composed.systemPrompt.includes('可用工具'), 'must preserve workspace & readonly tool guidelines');
    assert.strictEqual(
        await b1.exports.composeStorySystemPrompt({
            eventPayload: { stage: 'compose_system_prompt_sections', chatId: 'normal-user-chat', systemPrompt: '原样' },
        }),
        null,
        'must not touch non-bridge chats'
    );

    // 5. Tool prompt filter & lifecycle intercept hooks: allow only 5 LIVE_READ_TOOLS, block write/terminal/package tools.
    const filtered = await b1.exports.filterStoryTools({
        eventPayload: {
            stage: 'filter_tool_call_tools',
            chatId: 'native-chat-1',
            availableTools: [
                { name: 'read_file_part' },
                { name: 'grep_code' },
                { name: 'write_file' },
                { name: 'use_package' },
                { name: 'mcp_pkg:tool', activationSource: 'mcp_pkg' },
            ],
        },
    });
    assert.deepStrictEqual(Array.from(filtered.availableTools, t => t.name), ['read_file_part', 'grep_code']);
    assert.strictEqual(
        await b1.exports.filterStoryTools({
            eventPayload: { stage: 'filter_tool_call_tools', chatId: 'normal-user-chat', availableTools: [{ name: 'write_file' }] },
        }),
        null
    );

    const allowRes = await b1.exports.interceptStoryToolCall({
        eventName: 'tool_call_intercept',
        eventPayload: { toolName: 'read_file_part', runtimeContext: { chatId: 'native-chat-1' } },
    });
    assert.deepStrictEqual(JSON.parse(JSON.stringify(allowRes)), { action: 'allow' });
    const blockRes = await b1.exports.interceptStoryToolCall({
        eventName: 'tool_call_intercept',
        eventPayload: { toolName: 'write_file', runtimeContext: { chatId: 'native-chat-1' } },
    });
    assert.strictEqual(blockRes.action, 'block');
    assert.strictEqual(
        await b1.exports.interceptStoryToolCall({
            eventName: 'tool_call_intercept',
            eventPayload: { toolName: 'write_file', runtimeContext: { chatId: 'normal-user-chat' } },
        }),
        undefined,
        'must not block tools on non-bridge chats'
    );

    // 6. Prompt finalize hook: strips external <worldbook> ONLY on bridge chats.
    const finalized = await b1.exports.finalizeStoryPrompt({
        eventPayload: {
            stage: 'before_finalize_prompt',
            chatId: 'native-chat-1',
            systemPrompt: 'ZONE0_TEXT\n\n<worldbook>\n外部世界书常驻词条\n</worldbook>\n\n可用工具',
        },
    });
    assert(finalized && !finalized.systemPrompt.includes('<worldbook>') && !finalized.systemPrompt.includes('外部世界书常驻词条'));
    assert(finalized.systemPrompt.includes('ZONE0_TEXT') && finalized.systemPrompt.includes('可用工具'));
    assert.strictEqual(
        await b1.exports.finalizeStoryPrompt({
            eventPayload: {
                stage: 'before_finalize_prompt',
                chatId: 'normal-user-chat',
                systemPrompt: '<worldbook>正常聊天保留世界书</worldbook>',
            },
        }),
        null
    );

    // 7. v2.3.0 Operit 2 zh/en AGENTS.md & host boilerplate sanitization (live-only, preserves tools, toggleable).
    const fakeAgents = '# AGENTS.md\n' + '规则正文。'.repeat(1800);
    const zhPrompt = [
        '你是 Operit，一个由人工智能驱动的全能助手，能够执行各种任务。',
        '',
        '工作区指南：当前工作区为 /fixture',
        '',
        '<workspace_rule_file name="AGENTS.md">\n' + fakeAgents + '\n</workspace_rule_file>',
        '',
        '包系统：\n- 使用 use_package 激活扩展包',
        '',
        '文件同步：\n- 自动同步本地文件变更到工作区',
        '',
        '附件：\n- 用户可上传图片或文档附件',
        '',
        '可用工具：\n- read_file_part: 按行号读取文件',
    ].join('\n');
    const zhComposed = await b1.exports.composeStorySystemPrompt({
        eventPayload: { stage: 'compose_system_prompt_sections', chatId: 'native-chat-1', systemPrompt: zhPrompt },
    });
    assert(zhComposed && zhComposed.systemPrompt.startsWith('ZONE0_TEXT\n\nZONE1_TEXT'));
    assert(!zhComposed.systemPrompt.includes('<workspace_rule_file'), 'must strip AGENTS.md workspace_rule_file on live chat');
    assert(!zhComposed.systemPrompt.includes('规则正文。'), 'must strip AGENTS.md body on live chat');
    assert(!zhComposed.systemPrompt.includes('包系统：'), 'must strip PACKAGE SYSTEM on live chat');
    assert(!zhComposed.systemPrompt.includes('文件同步：'), 'must strip FILE SYNC on live chat');
    assert(!zhComposed.systemPrompt.includes('附件：'), 'must strip ATTACHMENTS on live chat');
    assert(!zhComposed.systemPrompt.includes('你是 Operit'), 'must strip generic Operit intro on live chat');
    assert(zhComposed.systemPrompt.includes('工作区指南'), 'must preserve workspace guidance');
    assert(zhComposed.systemPrompt.includes('可用工具') && zhComposed.systemPrompt.includes('read_file_part'), 'must preserve readonly tools section');
    assert(zhComposed.systemPrompt.length < zhPrompt.length - 8000, 'must reclaim 8K+ chars of AGENTS.md overhead');

    const enPrompt = [
        'You are Operit, an all-purpose AI assistant capable of handling many tasks.',
        '',
        'Workspace Guidelines: /fixture',
        '',
        '<workspace_rule_file name="AGENTS.md">\n' + fakeAgents + '\n</workspace_rule_file>',
        '',
        'FILE SYNC:\n- Auto sync files',
        '',
        'ATTACHMENTS:\n- User attachments',
        '',
        'AVAILABLE TOOLS:\n- read_file_part: read lines',
    ].join('\n');
    const enSanitized = b1.exports.sanitizeOperitCorePrompt(enPrompt, true);
    assert(!enSanitized.includes('<workspace_rule_file') && !enSanitized.includes('FILE SYNC:') && !enSanitized.includes('ATTACHMENTS:') && !enSanitized.includes('You are Operit'));
    assert(enSanitized.includes('Workspace Guidelines') && enSanitized.includes('AVAILABLE TOOLS:') && enSanitized.includes('read_file_part'));

    // Scene chat (role !== 'live') must NOT strip AGENTS.md / boilerplate.
    const sScene = await vm.runInContext('ensureSession(config, model, "scene")', b1);
    const sceneComposed = await b1.exports.composeStorySystemPrompt({
        eventPayload: { stage: 'compose_system_prompt_sections', chatId: sScene.chatId, systemPrompt: zhPrompt },
    });
    assert(sceneComposed === null || sceneComposed.systemPrompt.includes('<workspace_rule_file'), 'non-live scene chat must not strip AGENTS.md');

    // Toggle sanitizeOperitBoilerplate=false falls back to preserving AGENTS.md while keeping package stripping.
    const bNoSan = createBox({ sanitizeOperitBoilerplate: false });
    await vm.runInContext('ensureSession(config, model, "live")', bNoSan);
    await vm.runInContext('syncLivePrefixes(config, model, { chatId: "native-chat-1", participantId: "model:chat" }, "ZONE0_TEXT", "ZONE1_TEXT", "sha0", "sha1")', bNoSan);
    const noSanComposed = await bNoSan.exports.composeStorySystemPrompt({
        eventPayload: { stage: 'compose_system_prompt_sections', chatId: 'native-chat-1', systemPrompt: zhPrompt },
    });
    assert(noSanComposed && noSanComposed.systemPrompt.includes('<workspace_rule_file'), 'sanitizeOperitBoilerplate=false must preserve AGENTS.md');
    assert(!noSanComposed.systemPrompt.includes('包系统：'), 'package system strip remains active even when boilerplate sanitize is off');

    console.log('BRIDGE_SELF_HOSTED_OK native model:chat, zero character_cards, write/readExtension hydration, system/tool/worldbook/AGENTS hooks & non-bridge isolation verified');
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
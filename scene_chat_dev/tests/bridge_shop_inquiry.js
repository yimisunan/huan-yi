'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '../local.story.operit_bridge/main.js'), 'utf8');

function createHarness(opts = {}) {
    const originalLive = {
        chatId: 'live-story-chat-keep',
        participantId: 'part-1',
        cardId: 'card-v2',
        saveEpoch: 'epoch-1',
        prefixHash: 'hash-keep',
        generation: 3,
        turnCount: 4,
        dirty: false,
    };
    const config = {
        workspacePath: '/fixture',
        endpoint: 'http://127.0.0.1:5000',
        functionType: 'CHAT',
        dualStageEnabled: true,
        settlementFunctionType: 'SUMMARY',
        maxTurnsPerSession: 10,
        liveSessionPolicy: 'continuous',
        chatId: '',
        participantId: '',
        inFlight: null,
        outbox: null,
        liveSession: { ...originalLive },
    };
    const state = {
        originalLive,
        chatCalls: [],
        sendCalls: [],
        createdChats: 0,
        switchCalls: 0,
        completePosts: [],
        claimCount: 0,
        claim404: !!opts.claim404,
        chatError: opts.chatError || '',
        chatReplyText: opts.chatReplyText || JSON.stringify({
            shopkeeper_reply: '按要求新进了温热精油礼盒。',
            items: [
                {
                    name: '白桃温热足部精油',
                    category: 'sensual',
                    usage_mode: 'consumable_target',
                    tier: 'mid',
                    price: 24,
                    pack_qty: 2,
                    type: '消耗品',
                    desc: '带着淡淡白桃香气的微热按摩精油。',
                    system_effect: 'buff:温热精油:3:亲密互动羞耻防线柔和',
                    giftable: true,
                    max_per_save: 3,
                    unlock_req: { min_biz: 0, min_any_affection: 35, mode: 'all' },
                },
            ],
        }),
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
            callDependency: async () => { throw new Error('must not touch character cards during shop inquiry'); },
        },
        Tools: {
            SoftwareSettings: {
                exec: async (argv) => {
                    if (argv[0] === 'model' && argv[1] === 'function-show') {
                        if (argv[2] === 'CHAT') return { providerId: 'prov', modelId: 'gemini-4' };
                        if (argv[2] === 'SUMMARY') return { providerId: 'prov', modelId: 'gemini-flash' };
                        return { success: false, error: 'unbound' };
                    }
                    if (argv[0] === 'model' && argv[1] === 'show') {
                        return { providerId: argv[2], modelId: argv[3], providerName: 'Prov', pricing: { in: 1 } };
                    }
                    throw new Error('must not switch chat or workspace during shop inquiry: ' + JSON.stringify(argv));
                },
            },
            Chat: {
                createNew: async () => { state.createdChats += 1; return { chatId: 'unexpected' }; },
                switchTo: async () => { state.switchCalls += 1; },
                sendMessageStreaming: async function* () { state.sendCalls.push('unexpected'); yield {}; },
                call: async (req) => {
                    state.chatCalls.push(req);
                    if (state.chatError) throw new Error(state.chatError);
                    return { text: state.chatReplyText };
                },
            },
        },
    };

    vm.createContext(box);
    vm.runInContext(source, box);

    box.http = async (urlPath, body) => {
        if (urlPath === '/api/story/bridge-info') return { token: 'tok-shop' };
        if (urlPath === '/api/story/tasks') {
            return {
                story_protocol: 3,
                reading_preflight: 1,
                interaction_protocol: 3,
                live_reading_revision: 2,
                action_contract_revision: 1,
                material_delivery_revision: 1,
                save_epoch: 'epoch-1',
                service_epoch: 'svc-1',
                task: null,
            };
        }
        if (urlPath === '/api/story/scene/worker/claim') {
            const err = new Error('not found');
            err.statusCode = 404;
            throw err;
        }
        if (urlPath === '/api/story/worker/claim') return { task: null };
        if (urlPath === '/api/story/worker/shop-inquiry/claim') {
            state.claimCount += 1;
            if (state.claim404) {
                const err = new Error('not found');
                err.statusCode = 404;
                throw err;
            }
            if (state.claimCount > 1) return { inquiry: null };
            return {
                inquiry: {
                    id: 'siq-test1234',
                    lease: 'lease-abc',
                    query: '有没有白桃香味的热感足部精油？',
                    save_epoch: 'epoch-1',
                    system_prompt: 'SYSTEM_SHOP_PROMPT',
                    user_prompt: 'USER_SHOP_QUERY',
                },
            };
        }
        if (urlPath === '/api/story/worker/shop-inquiry/siq-test1234/complete') {
            state.completePosts.push(body);
            return { inquiry: { id: 'siq-test1234', status: body.error ? 'failed' : 'completed' } };
        }
        throw new Error('unexpected http path: ' + urlPath);
    };
    return box;
}

(async () => {
    // 1. Happy path: stateless Tools.Chat.call runs on SUMMARY slot and leaves liveSession untouched
    {
        const box = createHarness();
        const didWork = await box.work();
        assert.strictEqual(didWork, true, 'work() should return true after completing shop inquiry');
        assert.strictEqual(box.state.chatCalls.length, 1);
        assert.strictEqual(box.state.chatCalls[0].functionType, 'SUMMARY');
        assert.strictEqual(box.state.chatCalls[0].enableThinking, false);
        assert.deepStrictEqual(JSON.parse(JSON.stringify(box.state.chatCalls[0].turns)), [
            { kind: 'system', content: 'SYSTEM_SHOP_PROMPT' },
            { kind: 'user', content: 'USER_SHOP_QUERY' },
        ]);
        assert.strictEqual(box.state.completePosts.length, 1);
        assert.strictEqual(box.state.completePosts[0].lease, 'lease-abc');
        assert.strictEqual(box.state.completePosts[0].text, box.state.chatReplyText);
        assert.strictEqual(box.state.sendCalls.length, 0);
        assert.strictEqual(box.state.createdChats, 0);
        assert.strictEqual(box.state.switchCalls, 0);
        assert.deepStrictEqual(box.config.liveSession, box.state.originalLive, 'liveSession must stay untouched');
    }

    // 2. Error reporting path: model failure posts { lease, error } cleanly to /complete
    {
        const box = createHarness({ chatError: '模拟副模型限流' });
        const didWork = await box.work();
        assert.strictEqual(didWork, true);
        assert.strictEqual(box.state.completePosts.length, 1);
        assert.strictEqual(box.state.completePosts[0].lease, 'lease-abc');
        assert.ok(String(box.state.completePosts[0].error || '').includes('模拟副模型限流'));
        assert.deepStrictEqual(box.config.liveSession, box.state.originalLive);
    }

    // 3. Backwards compatibility: 404 on shop-inquiry/claim gracefully returns false
    {
        const box = createHarness({ claim404: true });
        const didWork = await box.work();
        assert.strictEqual(didWork, false);
        assert.strictEqual(box.state.chatCalls.length, 0);
    }

    console.log('bridge_shop_inquiry.js OK');
})().catch(err => {
    console.error(err);
    process.exit(1);
});

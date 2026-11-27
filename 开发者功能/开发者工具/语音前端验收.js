/* 定向验收：模拟网络与音频资源，检查取消、超时、资源上限和管理页离线初始化。 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert').strict;
const root = path.resolve(__dirname, '..', '..');
const clientSource = fs.readFileSync(path.join(root, 'voice_client.js'), 'utf8');
const managerSource = fs.readFileSync(path.join(root, 'voice_manager.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}
function response(body, status = 200, type = 'application/json') {
    return { ok: status >= 200 && status < 300, status,
        headers: { get: () => type }, json: async () => body, blob: async () => new Blob([body], { type }) };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function makeContext(fetcher) {
    let sequence = 0;
    const revoked = [];
    const context = vm.createContext({ console, setTimeout, clearTimeout, AbortController, DOMException, Blob,
        URL: { createObjectURL: () => 'blob:test-' + (++sequence), revokeObjectURL: url => revoked.push(url) },
        fetch: fetcher, globalThis: null });
    context.globalThis = context;
    vm.runInContext(clientSource, context);
    return { context, client: context.VoiceClient, revoked };
}
async function run() {
    let pending = [];
    const { client, revoked, context } = makeContext((url, options) => new Promise((resolve, reject) => {
        pending.push({ resolve, reject, signal: options.signal });
        options.signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError')), { once: true });
    }));
    const body = client.buildPayload('[whispers] 测试', { voice: 'fish:test', temperature: 0, volume: 0, min_chunk_length: 0, tts_model: 's2.1-pro-free' });
    assert.equal(body.temperature, 0); assert.equal(body.volume, 0); assert.equal(body.min_chunk_length, 0);
    assert.equal(body.text, '[whispers] 测试'); assert.equal(body.tts_model, 's2.1-pro-free');
    const first = client.requestAudio(body, { channel: 'test' }).catch(error => error);
    const second = client.requestAudio(body, { channel: 'test' });
    assert.equal(pending[0].signal.aborted, true);
    pending[1].resolve(response('audio', 200, 'audio/mpeg'));
    assert.equal((await first).name, 'AbortError'); assert.equal((await second).size, 5);
    const timeout = await client.requestAudio(body, { channel: 'timeout', timeoutMs: 5 }).catch(error => error);
    assert.equal(timeout.name, 'TimeoutError');
    const failure = client.requestAudio(body, { channel: 'failure' }).catch(error => error);
    pending[pending.length - 1].resolve(response({ error: '配置读取失败，原文件已保留。' }, 503));
    assert.match((await failure).message, /原文件已保留/);
    const store = new client.AudioUrlStore(3, 12);
    const pinned = store.add(new Blob(['1234'])); store.pin(pinned);
    for (let i = 0; i < 20; i++) store.add(new Blob(['1234']));
    assert.ok(store.entries.size <= 3); assert.ok(store.bytes <= 12); assert.ok(store.has(pinned));
    assert.ok(revoked.length >= 18); store.clear(); assert.equal(store.entries.size, 0);
    console.log('PASS shared client: payload, cancellation, timeout, error feedback, bounded URL release');

    const remote = deferred();
    const saved = deferred();
    const elements = new Map();
    function element(id) {
        if (!elements.has(id)) elements.set(id, { textContent: '', disabled: false, classList: { toggle() {} }, replaceChildren() {}, append() {} });
        return elements.get(id);
    }
    const config = { __settings__: { fish_tts_model: 's2.1-pro' }, 旁白: { voice: 'fish:sample', tts_model: 's2.1-pro-free', temperature: 0.58 }, default: { voice: 'fish:' } };
    const manager = makeContext((url, options = {}) => {
        if (url === '/api/config' && options.method === 'POST') return saved.promise;
        if (url === '/api/config') return Promise.resolve(response(config));
        if (url === '/api/voices' || url === '/api/edge_voices') return remote.promise;
        return Promise.resolve(response({ items: [] }));
    }).context;
    manager.window = manager;
    manager.addEventListener = () => {};
    manager.document = { getElementById: element, querySelectorAll: () => [], querySelector: () => null, activeElement: null,
        createElement: () => ({ append() {}, classList: { toggle() {} } }) };
    manager.alert = () => {}; manager.confirm = () => false;
    vm.runInContext(managerSource, manager);
    vm.runInContext('var renders=0; renderEditor=()=>{renders++;updateSaveState();}; refreshEditorPreservingDraft=()=>{};', manager);
    await tick();
    assert.equal(vm.runInContext('configReady', manager), true);
    assert.equal(vm.runInContext('renders', manager), 1);
    assert.equal(element('save-all-button').disabled, false);
    remote.resolve(response({ voices: [] })); await tick();
    const saving = vm.runInContext('configData["旁白"].speed=0.9; saveAllConfig();', manager);
    saved.resolve(response({ error: '存储不可写' }, 503)); await saving;
    assert.equal(vm.runInContext('isDirty()', manager), true);
    assert.match(element('manager-status').textContent, /存储不可写/);
    console.log('PASS manager: local config renders while remote pending; failed save remains dirty');

    const sentHeaders = [];
    const csrfCtx = makeContext((url, options = {}) => {
        sentHeaders.push({ url, method: options.method || 'GET', headers: options.headers || {}, body: options.body || '' });
        if (url === '/api/fish_key' && options.method === 'POST') return Promise.resolve(response({ ok: true, configured: true, masked: 'sk-****1234' }));
        if (url === '/api/fish_key' && options.method === 'DELETE') return Promise.resolve(response({ ok: true, configured: false }));
        if (url === '/api/voice_tier' && options.method === 'POST') return Promise.resolve(response({ ok: true, voice_tier: 'pro' }));
        if (url === '/api/voice_routing' && options.method === 'POST') return Promise.resolve(response({ status: 'success', routing: { protagonist_voice_enabled: true, action_voice_mode: 'separate', action_voice_scope: 'all' } }));
        return Promise.resolve(response({ configured: false }));
    });
    const defaultPayload = csrfCtx.client.buildPayload('测试文本', { voice: 'fish:abc' }, {}, '', '沈知韫');
    assert.equal(defaultPayload.tts_model, 's2.1-pro-free');
    assert.equal(defaultPayload.speaker, '沈知韫');
    assert.equal(defaultPayload.language, 'zh-CN');
    assert.equal(defaultPayload.latency, 'balanced');
    assert.equal(defaultPayload.chunk_length, 180);
    assert.equal(defaultPayload.quality_guard, true);
    await csrfCtx.client.saveFishKey('test-key-12345678', false);
    await csrfCtx.client.setVoiceTier('pro');
    await csrfCtx.client.setVoiceRouting({ protagonist_voice_enabled: true, action_voice_mode: 'separate', action_voice_scope: 'all' });
    await csrfCtx.client.prefetchBatch([{ text: '预热测试', speaker: '沈知韫' }]);
    await csrfCtx.client.clearFishKey();
    assert.ok(sentHeaders.some(r => r.url === '/api/voice_routing' && r.headers['X-Voice-Client'] === '1'), 'setVoiceRouting must hit /api/voice_routing with X-Voice-Client');
    assert.ok(sentHeaders.some(r => r.url === '/api/tts/prefetch' && r.headers['X-Voice-Client'] === '1'), 'prefetchBatch must hit /api/tts/prefetch with X-Voice-Client');
    assert.ok(sentHeaders.every(r => r.headers['X-Voice-Client'] === '1'), 'X-Voice-Client header required on all key/tier/routing/prefetch calls');
    console.log('PASS voice_client: s2.1-pro-free + balanced/180 default, prefetchBatch, speaker passthrough, key/tier/routing APIs & X-Voice-Client');

    const storySource = fs.readFileSync(path.join(root, 'story_client.js'), 'utf8');
    const stripFn = storySource.match(/function stripVoiceTags\([\s\S]*?\n  \}/)[0];
    const allowBlock = storySource.match(/const VOICED_SPEAKERS = [\s\S]*?function resolveEffectiveVoiceCfg\([\s\S]*?\n  \}/)[0];
    const whisperFn = storySource.match(/function isWhisperLine\([\s\S]*?\n  \}/)[0];
    const storyCtx = vm.createContext({});
    vm.runInContext(stripFn + '\n' + allowBlock + '\n' + whisperFn, storyCtx);
    // Default (no voiceConfigCache): narration->旁白, heroines->speaker, action(heroines+徐志北)->旁白, 徐志北 dialogue->''
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'narration', speaker: '', text: '雨停了。' }), '旁白');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '沈知韫', text: '过来。' }), '沈知韫');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '苏婉青', text: '先坐吧。' }), '苏婉青');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐念薇', text: '进来。' }), '徐念薇');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '沈知韫', text: '她放下笔。' }), '旁白');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐志北', text: '怎么了？' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐志北', text: '他走近一步。' }), '旁白');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐承邺', text: '妈！' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐承邺', text: '他推开门。' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '顾律师', text: '沈董您好。' }), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '主宅管家', text: '他轻敲房门。' }), '');

    // Protagonist voice enabled + bound vs unbound vs isPlayerInput guard
    const cfgProtagBound = {
        __settings__: { protagonist_voice_enabled: true, action_voice_mode: 'separate', action_voice_scope: 'all' },
        旁白: { voice: 'fish:narr123', speed: 0.94 },
        动作: { voice: '', speed: 1.03, volume: -1.5 },
        徐志北: { voice: 'edge:zh-CN-YunxiNeural', rate: '-2%' }
    };
    const cfgProtagUnbound = {
        __settings__: { protagonist_voice_enabled: true, action_voice_mode: 'muted', action_voice_scope: 'heroines' },
        旁白: { voice: 'edge:zh-CN-YunyangNeural' },
        动作: { voice: '', speed: 1.03, volume: -1.5 },
        徐志北: { voice: 'fish:' }
    };
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐志北', text: '妈，我回来了。' }, cfgProtagBound), '徐志北');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐志北', text: '玩家输入气泡', isPlayerInput: true }, cfgProtagBound), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐志北', text: '玩家动作气泡', isPlayerInput: true }, cfgProtagBound), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '沈知韫', text: '她放下笔。' }, cfgProtagBound), '动作');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐志北', text: '你接过茶杯。' }, cfgProtagBound), '动作');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'dialogue', speaker: '徐志北', text: '未绑定音色不发声' }, cfgProtagUnbound), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '沈知韫', text: '动作静音模式' }, cfgProtagUnbound), '');
    assert.equal(storyCtx.resolveVoiceSpeaker({ kind: 'action', speaker: '徐志北', text: '仅三女主范围' }, { __settings__: { action_voice_mode: 'separate', action_voice_scope: 'heroines' } }), '');
    // Inherit narrator voice (Fish & Edge) for 动作 when voice is empty
    const effActionFish = storyCtx.resolveEffectiveVoiceCfg('动作', cfgProtagBound);
    assert.equal(effActionFish.voice, 'fish:narr123');
    assert.equal(effActionFish.speed, 1.03);
    assert.equal(effActionFish.volume, -1.5);
    const effActionEdge = storyCtx.resolveEffectiveVoiceCfg('动作', cfgProtagUnbound);
    assert.equal(effActionEdge.voice, 'edge:zh-CN-YunyangNeural');
    assert.equal(effActionEdge.rate, '+0%');
    assert.equal(effActionEdge.volume, '-10%');

    // Voice manager preserves voice_ids on Edge<->Fish toggle & sorts pages canonically
    const mgrTest = makeContext(() => Promise.resolve(response({}))).context;
    mgrTest.window = mgrTest; mgrTest.addEventListener = () => {};
    mgrTest.document = { getElementById: () => ({ textContent: '', disabled: false, classList: { toggle() {} }, replaceChildren() {}, append() {} }), querySelectorAll: () => [], querySelector: () => null, activeElement: null, createElement: () => ({ append() {}, classList: { toggle() {} } }) };
    mgrTest.alert = () => {}; mgrTest.confirm = () => false;
    vm.runInContext(managerSource, mgrTest);
    vm.runInContext('renderEditor = () => {}; updateSaveState = () => {};', mgrTest);
    vm.runInContext(`
        configData = {
            __settings__: { fish_tts_model: 's2.1-pro-free' },
            徐志北: { voice: 'fish:male111111111111111111111111', voice_ids: ['male111111111111111111111111'], tts_model: 's2.1-pro-free' },
            苏婉青: { voice: 'fish:su1' },
            动作: { voice: '', voice_ids: [], tts_model: 's2.1-pro-free' },
            沈知韫: { voice: 'fish:shen1' },
            旁白: { voice: 'fish:narr111111111111111111111111', voice_ids: ['narr111111111111111111111111'], tts_model: 's2.1-pro-free' },
            徐念薇: { voice: 'fish:wei1' },
            default: { voice: 'fish:' }
        };
    `, mgrTest);
    assert.deepEqual(Array.from(vm.runInContext('editablePageNames()', mgrTest)), ['旁白', '动作', '沈知韫', '苏婉青', '徐念薇', '徐志北']);
    vm.runInContext("switchRoleToEdge('徐志北'); switchRoleToFishFree('徐志北');", mgrTest);
    assert.deepEqual(Array.from(vm.runInContext("configData['徐志北'].voice_ids", mgrTest)), ['male111111111111111111111111']);
    assert.equal(vm.runInContext("sanitizeConfigForSave(configData)['动作'].voice", mgrTest), '');

    assert.equal(
        storyCtx.stripVoiceTags('沈知<|phoneme_start|>yun4<|phoneme_end|>韫[low restrained voice]<whisper>低声</whisper><chinese>问好</chinese>'),
        '沈知韫低声问好'
    );
    assert.equal(storyCtx.isWhisperLine('<whisper>别出声</whisper>'), true);
    assert.equal(storyCtx.isWhisperLine('[低声] 过来'), true);
    assert.equal(storyCtx.isWhisperLine('普通对话'), false);
    assert.match(storySource, /name === '苏婉青' && loc === '市中心顶层公寓'/);
    assert.match(storySource, /name === '沈知韫' \|\| name === '徐念薇'.*loc === '徐家主宅'/);
    assert.match(storySource, /3:\s*'目击锁定'.*4:\s*'实锤'/);
    assert.match(storySource, /=== '徐家主宅'/);
    const mainHtml = fs.readFileSync(path.join(root, 'main_template.html'), 'utf8');
    assert.equal((mainHtml.match(/<\/html>/gi) || []).length, 1, 'main_template.html should have exactly one closing </html>');
    assert.ok(!mainHtml.includes('id="commitDialog"'), 'legacy #commitDialog modal must be removed');
    assert.ok(mainHtml.includes('id="inkCommitDock"'), '#inkCommitDock container must exist inside #stream');

    // Verify free-form English & Chinese Drama 3 director cues (up to 180 chars) are hidden from dialogue display (zero screen leak)
    const classifyFn = storySource.match(/function classifyVoiceTag\([\s\S]*?\n  \}/)[0];
    const zhReBlock = storySource.match(/const ZH_VOICE_TAG_TOKEN_RE = [\s\S]*?function isFishBracketTag\([\s\S]*?\n  \}/)[0];
    vm.runInContext(classifyFn + '\n' + zhReBlock, storyCtx);
    assert.equal(storyCtx.isFishBracketTag('像在强忍眼泪，却努力笑着', 'dialogue'), true);
    assert.equal(storyCtx.isFishBracketTag('声音发沉，带着点冷淡的提醒', 'dialogue'), true);
    assert.equal(
        storyCtx.isFishBracketTag('icy boardroom control, clipped pacing, holding back a sharp sigh before dropping her voice into an intimate warning', 'dialogue'),
        true
    );
    assert.equal(storyCtx.isFishBracketTag('MOVE:公司', 'dialogue'), false);
    assert.equal(storyCtx.isFishBracketTag('ITEM-001', 'dialogue'), false);
    assert.equal(storyCtx.classifyVoiceTag('压着倦意，声音微冷')?.mood, 'exhausted');
    assert.equal(storyCtx.classifyVoiceTag('轻哂，语速放慢半拍')?.mood, 'restrained');
    assert.equal(storyCtx.classifyVoiceTag('sharp, biting sarcasm')?.mood, 'sharp');
    assert.equal(storyCtx.classifyVoiceTag('warm playful, light chuckle')?.mood, 'playful');
    assert.equal(storyCtx.classifyVoiceTag('flustered, stammering nervously')?.mood, 'flustered');

    // Verify audioCache model-keying + invalidation on tier switch + Scheme A/B confirmation hooks + Drama 3 retake & subtext forwarding
    assert.match(storySource, /function clearAudioCache\(\)[\s\S]*?audioCache\.clear\(\)/);
    assert.match(storySource, /function invalidateVoiceConfig\(\)[\s\S]*?clearAudioCache\(\)/);
    assert.match(storySource, /function audioCacheKey\(id,\s*who,\s*cfg,\s*settings,\s*prosodyMod\s*=\s*null,\s*contextHint\s*=\s*''\)/);
    assert.match(storySource, /function findAdjacentActionHint\(messages,\s*index,\s*speaker\)/);
    assert.match(storySource, /msg-retake-btn/);
    assert.match(storySource, /voice-d3-pill/);
    assert.match(storySource, /confirmMode:\s*'inline'/);
    assert.match(storySource, /function bindChoiceGesture\(b,\s*opt\)/);
    assert.match(storySource, /function stageInkCommit\(/);
    assert.match(storySource, /function recallInkCommit\(/);

    // Verify VoiceClient extras (context_hint, retake, raw_params, voice_script), designVoice API & voice_manager studio tools
    assert.equal(typeof csrfCtx.client.getAudioAssets, 'function', 'VoiceClient.getAudioAssets must be exported');
    assert.equal(typeof csrfCtx.client.designVoice, 'function', 'VoiceClient.designVoice must be exported');
    const prosPayload = csrfCtx.client.buildPayload(
        '测试', { voice: 'fish:abc', speed: 1.0 }, {}, '', '沈知韫',
        { speed_scale: 0.95, expressive_boost: 0.08 },
        { context_hint: '她轻轻合上文件', retake: true, raw_params: true, voice_script: '[sharp] 测试' }
    );
    assert.equal(prosPayload.speed_scale, 0.95);
    assert.equal(prosPayload.expressive_boost, 0.08);
    assert.equal(prosPayload.context_hint, '她轻轻合上文件');
    assert.equal(prosPayload.retake, true);
    assert.equal(prosPayload.raw_params, true);
    assert.equal(prosPayload.voice_script, '[sharp] 测试');
    const calmPayload = csrfCtx.client.buildPayload('测试', { voice: 'fish:abc', speed: 1.0 }, {}, '', '沈知韫', null);
    assert.equal(calmPayload.speed_scale, undefined);
    await csrfCtx.client.designVoice({ description: 'Warm female voice', text: '试音脚本测试', count: 3 });
    assert.ok(
        sentHeaders.some(r => r.url === '/api/voice_design' && r.method === 'POST' && r.headers['X-Voice-Client'] === '1'),
        'designVoice must POST /api/voice_design with X-Voice-Client header'
    );
    assert.match(managerSource, /AB_BENCHMARK_SCRIPTS/);
    assert.match(managerSource, /VOICE_DESIGN_TEMPLATES/);
    assert.match(managerSource, /function renderAbPanelHtml\(/);
    assert.match(managerSource, /function runAbCompare\(/);
    assert.match(managerSource, /function renderVoiceDesignPanelHtml\(/);
    assert.match(managerSource, /function runVoiceDesign\(/);
    assert.match(storySource, /ambientAudio:\s*true/);
    assert.match(storySource, /function syncAmbientSoundscape\(\)/);
    assert.match(storySource, /function duckAmbient\(speakingNow\)/);
    assert.doesNotMatch(storySource, /function playSfx\(/);
    assert.doesNotMatch(storySource, /function playVoiceSample\(/);
    assert.match(storySource, /function computeProsodyMod\(m,\s*who\)/);

    // Verify v3 Archive Center, tiered rationalization, multi-banner Disco checks, Lv.4 防线支配, <=15, save_epoch & CSS integrity
    const ratFn = storySource.match(/function rationalizationTier\([\s\S]*?\n  \}/)[0];
    vm.runInContext(ratFn, storyCtx);
    assert.equal(storyCtx.rationalizationTier({ affection: 75, shame: 25, depravity: 20, passiveLv: 2 })?.text, '合理化闭环 · 全档豁免');
    assert.equal(storyCtx.rationalizationTier({ affection: 75, shame: 35, depravity: 20, passiveLv: 2 })?.text, '合理化闭环 · 深度豁免');
    assert.equal(storyCtx.rationalizationTier({ affection: 75, shame: 45, depravity: 20, passiveLv: 2 })?.text, '合理化闭环 · 中度豁免');
    assert.equal(storyCtx.rationalizationTier({ affection: 75, shame: 65, depravity: 20, passiveLv: 2 })?.text, '合理化闭环 · 轻度豁免');
    assert.equal(storyCtx.rationalizationTier({ affection: 75, shame: 88, depravity: 5, passiveLv: 2 }), null);
    assert.equal(storyCtx.rationalizationTier({ affection: 55, shame: 35, depravity: 20, passiveLv: 2 }), null);

    assert.ok(!storySource.includes("'绝对掌控'"), 'Lv.4 passive name must be 防线支配, not 绝对掌控');
    assert.match(storySource, /'防线支配'/);
    assert.match(storySource, /if \(npcStam <= 15\)/);
    assert.match(storySource, /const physChecks = \[\];[\s\S]*?const passiveChecks = \[\];/);
    assert.match(storySource, /const prevEpoch = cache\.epoch;[\s\S]*?shopCatalog = null;[\s\S]*?clearAudioCache\(\);[\s\S]*?if \(intentionalEpochSwitch\)/);
    assert.match(storySource, /api\('prologues'\)/);
    assert.match(storySource, /api\('saves'\)/);
    assert.match(storySource, /api\('saves\/snapshot'/);
    assert.match(storySource, /api\('saves\/restore'/);

    for (const id of [
        'newGameDialog', 'archiveTabs', 'archiveTabNewGame', 'archiveTabSaves',
        'archiveRandomCard', 'archiveScenarioGrid', 'rerollPrologueBtn',
        'saveSlotLabelInput', 'saveSlotCreateBtn', 'archiveSlotList',
        'sceneAtmospherePills', 'archiveQuickBtn'
    ]) {
        assert.ok(mainHtml.includes(`id="${id}"`), `main_template.html missing #${id}`);
    }
    const cssSource = fs.readFileSync(path.join(root, 'story_client.css'), 'utf8');
    assert.equal((cssSource.match(/\{/g) || []).length, (cssSource.match(/\}/g) || []).length, 'story_client.css braces must be balanced');
    assert.match(cssSource, /\.msg\[data-defense="melted"\]/);
    assert.match(cssSource, /\.msg\[data-defense="guarded"\]/);
    assert.match(cssSource, /\.archive-dialog/);
    assert.match(cssSource, /\.audio-vol-slider/);

    console.log('PASS story_client & main_template: 4-speaker allowlist, Drama 3 director tag hiding, cache invalidation, ambient soundscape/ducking/prosody, Scheme A+B confirm & v3 Archive Center');
    console.log('All frontend checks passed; external requests: 0');
}
run().catch(error => { console.error(error.stack); process.exitCode = 1; });

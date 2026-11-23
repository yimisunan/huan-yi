"use strict";
/* Operit 2 main-runtime worker. Model output is data, never executable code. */
const CHANNEL = 'story.bridge.control';
let settingsPromise;
let running = false;
let timer = null;
let busy = null;
let lastError = '';
let monitorTimer = null, monitorBusy = false, starting = null;
let controlSupported = null, sessionReady = false;
const PLUGIN_VERSION = '2.1.6';
const SETTINGS_ROUTE = 'toolpkg:local.story.operit_bridge:ui:settings';
const DEFAULT_MAX_TURNS = 10;
const MAX_PLAYER_DIALOGUE_PER_TURN = 3;
const KNOWN_FUNCTION_SLOTS = ['CHAT', 'SUMMARY', 'TRANSLATION', 'TITLE_GENERATION', 'MEMORY', 'GREP', 'ROLE_RESPONSE_PLANNER'];

function effectiveSettlementThinkingMode(config) {
    const mode = config && config.settlementThinkingMode;
    if (mode === 'auto' || mode === 'off' || mode === 'on') return mode;
    if (config && config.settlementThinking === true) return 'on';
    return 'auto';
}
let heartbeats = new Set();
let waitLoopActive = false, workerSeq = 0, lastServiceEpoch = '', waitSleepTimer = null, waitSleepResolve = null;

function syncServiceEpoch(epoch) {
    if (typeof epoch !== 'string' || !epoch) return;
    if (lastServiceEpoch && lastServiceEpoch !== epoch) {
        workerSeq = 0;
    }
    lastServiceEpoch = epoch;
}
let verifiedCardCache = new Map();
let boundChatCache = new Map();
let settlementModelInfo = null, settlementCheckedAt = 0, settlementFallback = false;
let modelCatalogCache = { models: [], bindings: [] }, catalogCheckedAt = 0;
const FILE_TOOLS = ['list_files', 'find_files', 'grep_code', 'read_file', 'read_file_full', 'read_file_part', 'file_info', 'file_exists'];
const LIVE_READ_TOOLS = ['read_file','read_file_full','read_file_part','file_info','grep_code'];
const ROLE_MARK = 'local.story.operit_bridge:readonly';
const SESSION_TIMEOUT = 600000;

function cliData(raw) {
    for (let i = 0; i < 8; i++) {
        if (typeof raw === 'string') { raw = JSON.parse(raw); continue; }
        if (raw && typeof raw === 'object') {
            if (raw.success === false) throw new Error(raw.error || 'Operit操作失败');
            const value = raw.data ?? raw.result ?? raw.value;
            if (value !== undefined) { raw = value; continue; }
            return raw;
        }
        break;
    }
    throw new Error('Operit返回了无法解析的结果');
}

async function currentChat() {
    return cliData(await Tools.SoftwareSettings.exec(['chat', 'current', '--json'])).chatId;
}

async function restoreChat(chatId, returnChatId) {
    if (returnChatId && chatId !== returnChatId && await currentChat() === chatId) {
        await Tools.Chat.switchTo(returnChatId);
    }
}

function roleChanges(model, scene = false, customPrompts = null) {
    if (scene === 'live') {
        const base = { ...roleChanges(model, true),
            toolAccessConfig:{enabled:true,allowedBuiltinTools:LIVE_READ_TOOLS,allowedPackages:[],allowedSkills:[],allowedMcpServers:[]}, name: '同席互动·项目只读',
            characterSetting: '你是正式互动故事生成者。entry_mode=live_interaction时，material_delivery=program_inline_v1表示material与required_sources已由程序从冻结源完整读取并直接交付；完整理解正文，不为证明读取而逐段重读packet，也不声称执行了未发生的工具读取。没有该标记时按packet.read_ranges读取。确需旧史时，只补查本任务许可路径与精确范围。依据设定、正式存档和玩家意图推演连贯剧情，在需要玩家新决定处停下。只交本次output_contract要求的裸JSON；保留主权、知情边界和角色主体性；对白只归实际在场人物，玩家台词不得代写；费用与数值由程序结算。不写文件、不执行命令。',
            otherContentChat: '遵循本次output_contract；正式传输中operation无操作时明确写空字符串两个双引号，不省略值，桥接在合法解析后转换为内部null。resolution.task、resolution.sleep.start及conditions.npc无内容写空字符串，不得省略值；有任务/时间则写合法对象。conditions依本次resolution_policy：普通付费必须七字段完整对象，无NPC仅npc为空；免费SYSTEM才无条件。严格区分玩家私有状态与角色共同知情。正文与登记操作一致；未支持操作写待处理，不宣称完成。' };
        if (customPrompts && typeof customPrompts.characterSetting === 'string') {
            base.characterSetting = customPrompts.characterSetting;
            base.otherContentChat = typeof customPrompts.otherContentChat === 'string' ? customPrompts.otherContentChat : '';
        }
        return base;
    }
    return { name: scene ? '场景交流·项目只读' : '故事生成·项目只读', description: '网页故事桥接的专用只读生成参与者。',
        characterSetting: scene ? '你是隔离场景交流参与者。entry_mode=scene_chat时只真实读取指定packet，按其中交流规范回应；不执行完整回合读取链、字数、节拍、OPTIONS或结算。当前packet覆盖事实，不从旧会话引入其他场景。只输出裸JSON，不写文件、不执行命令。' : '你是项目故事回合生成器。按本次网页信封调用真实只读文件工具；当前文件是事实源，历史会话不能代替本轮读取。最终只返回契约JSON；禁止写文件、执行命令、外部服务或自行提交。',
        otherContentChat: scene ? '完整读取指定packet，截断则分段补全；只返回messages/facts_delta/needs/handoff。' : '工具读取可以分多步，最终回复只包含单个裸JSON。遵循当前reading_policy与output_contract；不能伪造读取、阅据或V1。',
        attachedTagIds: [], marks: ROLE_MARK, chatModelBindingMode: 'FIXED_MODEL',
        chatProviderId: model.provider_id, chatModelId: model.model_id,
        toolAccessConfig: { enabled: true, allowedBuiltinTools: FILE_TOOLS,
            allowedPackages: [], allowedSkills: [], allowedMcpServers: [] } };
}

async function ownedStoryCard(model, scene) {
    const expectedName = roleChanges(model, scene).name;
    const listed = await ToolPkg.callDependency('com.operit.character_cards', 'character.list', {}).catch(() => []);
    const items = Array.isArray(listed) ? listed : (listed && Array.isArray(listed.characters) ? listed.characters : []);
    for (const item of items) {
        if (!item || !item.id || (item.name && item.name !== expectedName)) continue;
        const card = await ToolPkg.callDependency('com.operit.character_cards', 'character.get', { id: item.id }).catch(() => null);
        if (card && card.marks === ROLE_MARK && card.name === expectedName) return { ...card, id: item.id };
    }
    return null;
}

async function ensureSession(config, model, scene = false, persist = () => PluginConfig.flush(config), skipPromptReset = false) {
    if (!config.workspacePath) throw new Error('故事会话尚未绑定项目工作区，请先配置workspacePath');
    const cachedBoundKey = config.chatId && config.participantId
        ? JSON.stringify([config.chatId, config.participantId, config.workspacePath, model.key, String(scene)])
        : '';
    if (cachedBoundKey && boundChatCache.get(config.chatId) === cachedBoundKey && verifiedCardCache.has(config.participantId)) {
        const existing = await Tools.Chat.listChats({ chat_ids: [config.chatId] });
        if (!Array.isArray(existing.chats)) throw new Error('无法核验故事专用会话');
        if (existing.chats.some(chat => chat.id === config.chatId)) {
            if (!(await Tools.Chat.agentStatus(config.chatId)).isIdle) throw new Error('故事专用会话忙碌，未重复提交');
            sessionReady = true;
            return { chatId: config.chatId, participantId: config.participantId };
        }
        boundChatCache.delete(config.chatId);
        config.chatId = '';
        sessionReady = false;
        await persist();
    }
    if (config.chatId) {
        const existing = await Tools.Chat.listChats({ chat_ids: [config.chatId] });
        if (!Array.isArray(existing.chats)) throw new Error('无法核验故事专用会话');
        if (!existing.chats.some(chat => chat.id === config.chatId)) {
            boundChatCache.delete(config.chatId);
            config.chatId = '';
            sessionReady = false;
            await persist();
        }
    }
    if (!config.participantId) {
        // Reuse this plugin's own card after a reinstall or cleared config; never delete user data.
        const found = await ownedStoryCard(model, scene);
        if (found) { config.participantId = found.id; await persist(); }
    }
    let card;
    if (config.participantId) {
        card = await ToolPkg.callDependency('com.operit.character_cards', 'character.get', { id: config.participantId });
        if (card.marks !== ROLE_MARK) throw new Error('专用角色标记不符，已停止自动修改');
        const expected = roleChanges(model, scene, skipPromptReset ? { characterSetting: card.characterSetting, otherContentChat: card.otherContentChat } : null);
        if (card.characterSetting !== expected.characterSetting || card.otherContentChat !== expected.otherContentChat || card.chatModelBindingMode !== 'FIXED_MODEL' || card.chatProviderId !== expected.chatProviderId || card.chatModelId !== expected.chatModelId ||
                JSON.stringify(card.toolAccessConfig) !== JSON.stringify(expected.toolAccessConfig)) {
            if (config.chatId && !(await Tools.Chat.agentStatus(config.chatId)).isIdle) throw new Error('专用会话仍在运行，不能更新模型或权限');
            card = await ToolPkg.callDependency('com.operit.character_cards', 'character.update', { id: config.participantId, changes: expected });
        }
        verifiedCardCache.set(config.participantId, model.key);
    } else {
        try {
            card = await ToolPkg.callDependency('com.operit.character_cards', 'character.create', { values: roleChanges(model, scene) });
        } catch (error) {
            if (!/已存在|exist/i.test(String(error.message || error))) throw error;
            card = await ownedStoryCard(model, scene);
            if (!card) throw new Error('同名角色卡已存在但不是本插件的专用卡，未自动删除或覆盖；请先确认该卡来源。');
        }
        if (!card || !card.id) throw new Error('未取得专用角色标识');
        config.participantId = card.id;
        verifiedCardCache.set(config.participantId, model.key);
        await persist();
    }
    if (!config.chatId) {
        const chat = await Tools.Chat.createNew({ setAsCurrentChat: false,
            input: { 'com.operit.character_cards': { version: 1, selection: 'card:' + config.participantId } } });
        if (!chat.chatId) throw new Error('未取得专用会话标识');
        config.chatId = chat.chatId;
        await persist();
        await Tools.Chat.updateTitle(chat.chatId, '故事生成 · 项目工作区');
    }
    const boundRaw = await Tools.SoftwareSettings.exec(['workspace', 'bind', config.chatId, config.workspacePath, '--json']);
    if (boundRaw !== undefined && boundRaw !== null) {
        const bound = typeof boundRaw === 'string' ? (() => { try { return JSON.parse(boundRaw); } catch (_) { return { raw: boundRaw }; } })() : boundRaw;
        if (bound && (bound.success === false || bound.ok === false)) throw new Error(bound.error || '工作区绑定失败');
    }
    const binding = await ToolPkg.callDependency('com.operit.character_cards', 'chat.configuration.binding.read', { chatId: config.chatId });
    if (binding.selection !== 'card:' + config.participantId) throw new Error('专用会话参与者绑定已改变');
    if (!(await Tools.Chat.agentStatus(config.chatId)).isIdle) throw new Error('故事专用会话忙碌，未重复提交');
    boundChatCache.set(config.chatId, JSON.stringify([config.chatId, config.participantId, config.workspacePath, model.key, String(scene)]));
    sessionReady = true;
    return { chatId: config.chatId, participantId: config.participantId };
}

async function syncCardPrefixes(config, model, session, zone0Global, zone1Scene, zone0Sha, zone1Sha) {
    const state = config.liveSession || {};
    const targetSig = JSON.stringify([session.participantId, model.key, zone0Sha, zone1Sha]);
    if (state.syncedCardSig === targetSig && verifiedCardCache.get(session.participantId + ':prefix') === targetSig) {
        return;
    }
    if (session.chatId && !(await Tools.Chat.agentStatus(session.chatId)).isIdle) {
        throw new Error('专用会话仍在运行，不能更新冻结前缀');
    }
    const changes = roleChanges(model, 'live', { characterSetting: zone0Global, otherContentChat: zone1Scene });
    await ToolPkg.callDependency('com.operit.character_cards', 'character.update', { id: session.participantId, changes });
    state.zone0Sha = zone0Sha;
    state.zone1Sha = zone1Sha;
    state.syncedCardSig = targetSig;
    verifiedCardCache.set(session.participantId + ':prefix', targetSig);
    config.liveSession = { ...state };
    await PluginConfig.flush(config);
}

function workerPath(task, action) {
    return (task.entry_mode === 'scene_chat' ? '/api/story/scene/worker/' : '/api/story/worker/') + task.request_id + '/' + action;
}

async function sceneSession(config, model, task) {
    const identity = JSON.stringify([task.scene_id, task.source_version, model.key, "handoff-empty-string-v1"]);
    let state = config.sceneSession;
    if (!state || state.identity !== identity || state.observedChars + task.packet_bytes > 120000) {
        state = { identity, chatId: '', participantId: state ? state.participantId : '', observedChars: 0 };
        config.sceneSession = state;
        await PluginConfig.flush(config);
    }
    const child = { workspacePath: config.workspacePath, chatId: state.chatId, participantId: state.participantId };
    const session = await ensureSession(child, model, true, async () => {
        state.chatId = child.chatId; state.participantId = child.participantId;
        config.sceneSession = { ...state };
        await PluginConfig.flush(config);
    });
    state.chatId = session.chatId; state.participantId = session.participantId;
    config.sceneSession = { ...state };
    await PluginConfig.flush(config);
    return session;
}

function liveSessionPolicy(config) {
    return ['continuous','service_restart','per_action'].includes(config.liveSessionPolicy) ? config.liveSessionPolicy : 'continuous';
}

function liveMaxTurns(config) {
    const n = Number(config && config.maxTurnsPerSession);
    return Number.isInteger(n) && n >= 2 && n <= 30 ? n : DEFAULT_MAX_TURNS;
}

function liveSessionView(config) {
    const state = config.liveSession || {};
    return { policy: liveSessionPolicy(config), chat_id: state.chatId || '', generation: state.generation || 0,
        reset_reason: state.resetReason || '', turn_count: state.turnCount || 0, max_turns: liveMaxTurns(config) };
}

async function resetLiveSession(config, reason) {
    const state = config.liveSession || {};
    if (config.inFlight || config.outbox || state.chatId && !(await Tools.Chat.agentStatus(state.chatId)).isIdle) throw new Error('请等待当前生成和提交结束后重建会话');
    if (state.chatId) boundChatCache.delete(state.chatId);
    config.liveSession = { ...state, chatId: '', observedChars: 0, turnCount: 0, lastCommittedSeq: 0,
        interactionScope: '', dirty: false, generation: (state.generation || 0) + 1, resetReason: reason };
    await PluginConfig.flush(config);
}

function buildTailHook(messages) {
    if (!Array.isArray(messages) || !messages.length) return '';
    const tail = messages.slice(-2).map(m => {
        if (!m || !m.text) return '';
        const txt = String(m.text).replace(/\s+/g, ' ').trim().slice(0, 110);
        if (!txt) return '';
        if (m.kind === 'dialogue' && m.speaker) return m.speaker + '：「' + txt + '」';
        if (m.kind === 'action' && m.speaker) return m.speaker + '（动作）：' + txt;
        return '旁白：' + txt;
    }).filter(Boolean);
    return tail.join(' | ').slice(0, 240);
}

async function liveSession(config, model, task) {
    const isV2 = task.material_delivery_v2 === 1;
    const protocolTag = isV2 ? (config.dualStageEnabled !== false ? 'live-dual-v2' : 'live-single-v2') : 'live-program-inline-v1';
    const identity = JSON.stringify([config.workspacePath, task.save_epoch, model.key, protocolTag]);
    const policy = liveSessionPolicy(config);
    const maxTurns = liveMaxTurns(config);
    let state = config.liveSession;
    const canResumeSameChat = Boolean(isV2 && task.resume_stage2 && state && state.chatId && state.lastRequestId === task.request_id);
    const reason = !state ? '首次连接'
        : state.identity !== identity ? '存档、工作区、模型或模式变更'
        : isV2 && state.dirty && !canResumeSameChat ? '上轮异常干净切窗'
        : isV2 && state.chatId && state.interactionScope && task.interaction_scope && state.interactionScope !== task.interaction_scope ? '场景或同席人物变化'
        : isV2 && state.chatId && (state.turnCount || 0) >= maxTurns && state.lastRequestId !== task.request_id ? '满' + maxTurns + '轮防摘要切窗'
        : policy === 'service_restart' && state.serviceEpoch !== task.service_epoch ? '本地故事服务已重启'
        : policy === 'per_action' && state.lastRequestId !== task.request_id ? '按行动新建' : '';
    let isFresh = !state || !state.chatId;
    if (reason) {
        if (state && state.chatId && !(await Tools.Chat.agentStatus(state.chatId)).isIdle) throw new Error('旧正式会话尚未结束，不能切换');
        if (state && state.chatId) boundChatCache.delete(state.chatId);
        const sameIdentity = Boolean(state && state.identity === identity);
        state = { identity, chatId: '', participantId: state ? state.participantId : '', observedChars: 0,
            turnCount: 0, lastCommittedSeq: 0, interactionScope: task.interaction_scope || '', dirty: false,
            zone0Sha: state ? state.zone0Sha || '' : '', zone1Sha: state ? state.zone1Sha || '' : '',
            syncedCardSig: state ? state.syncedCardSig || '' : '',
            lastTailHook: sameIdentity && state && state.lastTailHook ? state.lastTailHook : '',
            generation: ((state && state.generation) || 0) + 1, resetReason: reason };
        config.liveSession = state;
        await PluginConfig.flush(config);
        isFresh = true;
    }
    state.serviceEpoch = task.service_epoch;
    state.lastRequestId = task.request_id;
    if (task.interaction_scope) state.interactionScope = task.interaction_scope;
    const prevChatId = state.chatId || '';
    const child = { workspacePath: config.workspacePath, chatId: state.chatId, participantId: state.participantId };
    const persist = async () => { state.chatId = child.chatId; state.participantId = child.participantId; config.liveSession = { ...state }; await PluginConfig.flush(config); };
    const session = await ensureSession(child, model, 'live', persist, isV2);
    if (session.chatId !== prevChatId) {
        isFresh = true;
        state.lastCommittedSeq = 0;
        state.turnCount = 0;
        state.observedChars = 0;
        state.dirty = false;
        state.resetReason = reason || '外部窗口已重建';
    }
    await persist();
    return { ...session, isFresh };
}

function finalMessage(receipt, snapshots, mode = false, inline = false) {
    const outcome = receipt && receipt.outcome;
    if (!outcome || outcome.type !== 'committed' || outcome.status !== 'completed' || !outcome.assistant) {
        throw new Error('正式会话未正常完成，结果未提交');
    }
    const snapshot = snapshots.get(outcome.assistant.messageTimestamp);
    if (!snapshot) throw new Error('缺少完成回执对应的消息快照');
    const parts = snapshot.parts;
    let lastResult = -1;
    for (let i = 0; i < parts.length; i++) if (parts[i].kind === 'tool_result') lastResult = i;
    if (lastResult < 0 && !inline) throw new Error('正式会话没有实际文件工具结果');
    const start = lastResult < 0 ? 0 : lastResult + 1;
    let text = parts.slice(start).filter(part => part.kind === 'markdown' && part.content.trim())
        .map(part => part.content).join('').trim();
    let value;
    try { value = JSON.parse(text); } catch (_) {
        if (/"operation"\s*:\s*[,}]/.test(text)) throw new Error('模型输出JSON语法错误：operation缺少值；无操作必须明确写空字符串两个双引号，不能留空；回复未接受，请重试原消息。');
        if (/"handoff"\s*:\s*[,}]/.test(text)) throw new Error('模型输出JSON语法错误：handoff缺少值；无待处理说明须按本次传输契约明确填写，不能留空；回复未接受，请重试原消息。');
        const missing = text.match(/"(start|task|npc|conditions)"\s*:\s*[,}]/);
        if (missing) throw new Error('模型输出JSON语法错误：'+missing[1]+'缺少值；无内容请明确写空字符串两个双引号，不能留空；回复未接受，请重试原行动。');
        throw new Error('模型最终回复不是合法JSON，未接受；请检查专用会话原回复后手动重试。');
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('最终结果必须为JSON对象');
    // Explicit scene wire encoding: empty string means no handoff. Never repair malformed JSON.
    if ((mode === true || mode === 'scene_chat') && value.handoff === '') { value.handoff = null; text = JSON.stringify(value); }
    if (mode === 'live_interaction') {
        if (value.resolution && ['A','B','C'].includes(value.resolution.category)
                && (!value.resolution.conditions || typeof value.resolution.conditions!=='object' || Array.isArray(value.resolution.conditions))) {
            throw new Error('普通付费行动的resolution.conditions必须是完整对象；澄清或未移动也须填写，无NPC只将npc留空');
        }
        const paths = [['operation'], ['resolution','task'], ['resolution','conditions'],
            ['resolution','sleep','start'], ['resolution','conditions','npc']];
        const edits = [];
        for (const path of paths) {
            let current = value;
            for (const key of path) current = current && typeof current === 'object' ? current[key] : undefined;
            if (current !== '') continue;
            let offset = 0, span = null;
            for (const key of path) {
                span = jsonMemberSpan(text, offset, key);
                if (!span) throw new Error('正式互动'+path.join('.')+'字段重复或缺失，回复未接受');
                offset = span[0];
            }
            edits.push(span);
        }
        // Legal empty strings only. Preserve other bytes and duplicate keys for the server to reject.
        for (const span of edits.sort((a,b) => b[0]-a[0])) text = text.slice(0,span[0])+'null'+text.slice(span[1]);
    }
    const pending = [], tools = [];
    for (const part of parts) {
        if (part.kind === 'tool_call') {
            if (!FILE_TOOLS.includes(part.toolName)) throw new Error('会话调用了非只读工具');
            pending.push(part);
        } else if (part.kind === 'tool_result') {
            const index = pending.findIndex(call => call.toolName === part.toolName &&
                (!part.toolCallId || part.toolCallId === call.toolCallId || part.toolCallId === call.partId));
            if (index < 0) throw new Error('工具结果缺少对应调用');
            const call = pending.splice(index, 1)[0];
            tools.push({ name: call.toolName, parameters: call.attributes, part_id: part.partId,
                status: part.attributes.status, result_text: part.content });
        }
    }
    if (pending.length || tools.length > 128) throw new Error('工具调用未全部结束或超出128次上限');
    return { text, tools, timestamp: snapshot.messageTimestamp };
}

const STREAM_TAG_RE = /^(?:[-*•>]\s*)*(?:\*\*)?(?:(?:旁白|叙述|人物动作|动作|角色对白|对白|台词)\s*[:：]\s*)?\[(N|A|D)(?:[:：]([^\]]+))?\](?:\*\*)?\s*(.*)$/;
const STREAM_BARE_NARRATION_RE = /^(?:[-*•>]\s*)*(?:\*\*)?(?:(?:旁白|叙述)\s*[:：]|\[(?:旁白|叙述)\])(?:\*\*)?\s*(.+)$/;
const STREAM_INLINE_SPLIT_RE = /(?:\s+|(?<=[。！？!?；;”"」』）)]))\s*(?=(?:\*\*)?(?:(?:旁白|叙述|人物动作|动作|角色对白|对白|台词)\s*[:：]\s*)?\[(?:N|(?:A|D)[:：][^\]]+)\])/;
const STREAM_DECISION_SPLIT_RE = /(?:^|\r?\n)\s*(?:#{1,6}\s*)?(?:\*\*)?(?:[-—–=]{2,}\s*\r?\n(?:\s*\r?\n)?\s*(?:#{1,6}\s*)?(?:\*\*)?(?:DECISION|段末抉择|抉择)\s*[-—–=]*(?:\*\*)?|[-—–=]{2,}\s*(?:DECISION|段末抉择|抉择)\s*[-—–=]*(?:\*\*)?|(?:DECISION|段末抉择|抉择)\s*[-—–=]{2,}(?:\*\*)?|【\s*(?:DECISION|段末抉择|抉择)\s*】(?:\*\*)?|#{1,6}\s*(?:\*\*)?(?:DECISION|段末抉择|抉择)(?:\*\*)?|(?:DECISION|段末抉择)(?:\*\*)?)(?:\s*[（(][^)\n）]{0,20}[)）])?\s*[:：]?\s*(?=\r?\n|$)/i;
const STREAM_INLINE_DECISION_RE = /\s*(?:\*\*)?[-—–=]{2,}\s*DECISION\s*[-—–=]{2,}(?:\*\*)?\s*/i;
const STREAM_BARE_DIVIDER_RE = /^\s*[-—–=*_]{3,}\s*$/;
const STREAM_PROMPT_RE = /^\s*(?:[-*•>]\s*)*(?:#{1,6}\s*)?(?:\*\*)?(?:PROMPT|提示|抉择提示|段末提示|当前局面|局面提示|抉择)(?:\*\*)?\s*[:：]/i;
const STREAM_OPT_RE = /^\s*(?:[-*•>]\s*)*(?:#{1,6}\s*)?(?:\*\*)?(?:(?:选项\s*)?([ABC])|[\[【(（]\s*([ABC])\s*[\]】)）])(?:\*\*)?(?:\s*\[MOVE[:：][^\]]+\])?(?:\s*(?:[·•\-—（(\[][^\n:：.、)）]{1,24}))?\s*[:：.、)）\s]\s*\S/i;
const STREAM_LEADING_ASCII_FISH_RE = /^\s*(?:\[[a-zA-Z0-9_,\s-]{1,80}\]\s*)+/;
const STREAM_LEADING_VOICE_TAGS_RE = /^((?:\[[^\]\r\n]{1,80}\]\s*)*)([\s\S]*)$/;
const STREAM_OUTER_QUOTES_RE = /^(?:“([^“”]+)”|"([^"]+)"|「([^「」]+)」|『([^『』]+)』)\s*$/;
const STREAM_MIXED_ACTION_DIALOGUE_RE = /^([^“"「『\r\n]{2,180}?)([，,、；;\s]*(?:(?:低声|轻声|冷声|沉声|柔声|淡淡|缓声|随口|开口|抬眼|垂眸|侧头|转头)?(?:说道|问道|答道|应道|反问|叮嘱|交代|开口|道|说|问|答))?\s*[：:，,])\s*(?:“([^”]+)”|"([^"]+)"|「([^」]+)」|『([^』]+)』)\s*$/;

function normalizeStreamNodeJs(kind, speaker, rawBody) {
    let text = String(rawBody || '').trim();
    if (!text) return [];
    if (kind === 'narration') return [{ kind: 'narration', speaker: '', text }];
    if (kind === 'action') {
        const cleaned = text.replace(STREAM_LEADING_ASCII_FISH_RE, '').trim() || text;
        return [{ kind: 'action', speaker, text: cleaned }];
    }
    if (speaker === '徐志北') {
        text = text.replace(STREAM_LEADING_ASCII_FISH_RE, '').trim() || text;
    }
    const tm = text.match(STREAM_LEADING_VOICE_TAGS_RE);
    const leadingTags = tm && tm[1] ? tm[1].trim() : '';
    const rest = tm && tm[2] ? tm[2].trim() : text;
    const qm = rest.match(STREAM_OUTER_QUOTES_RE);
    if (qm) {
        const inner = (qm[1] || qm[2] || qm[3] || qm[4] || '').trim();
        if (inner) {
            return [{ kind: 'dialogue', speaker, text: leadingTags ? (leadingTags + ' ' + inner).trim() : inner }];
        }
    }
    const mm = rest.match(STREAM_MIXED_ACTION_DIALOGUE_RE);
    if (mm) {
        const actRaw = (mm[1] || '').trim();
        const verbRaw = (mm[2] || '').trim();
        let speechRaw = (mm[3] || mm[4] || mm[5] || mm[6] || '').trim();
        const hasColonOrVerb = /[：:]|道|说|问|答|开口|反问|叮嘱|交代/.test(verbRaw);
        const isThirdPerson = actRaw.startsWith('她') || actRaw.startsWith('他') || (speaker && actRaw.startsWith(speaker)) || hasColonOrVerb;
        const startsFirstSecond = /^(?:我|你|您|咱们|我们|你们)(?:们|[，,。、\s]|$)/.test(actRaw);
        if (speechRaw && isThirdPerson && !startsFirstSecond && !/^[｛{\[]/.test(actRaw)) {
            let actClean = actRaw.replace(/[，,、；;：:\s]+$/, '');
            if (actClean && !/[。！？!?…]$/.test(actClean)) actClean += '。';
            const iqm = speechRaw.match(STREAM_OUTER_QUOTES_RE);
            if (iqm) speechRaw = (iqm[1] || iqm[2] || iqm[3] || iqm[4] || speechRaw).trim();
            const finalSpeech = leadingTags ? (leadingTags + ' ' + speechRaw).trim() : speechRaw;
            const out = [];
            if (actClean) out.push({ kind: 'action', speaker, text: actClean });
            if (finalSpeech) out.push({ kind: 'dialogue', speaker, text: finalSpeech });
            if (out.length) return out;
        }
    }
    return [{ kind: 'dialogue', speaker, text }];
}

function detectUnmarkedDecisionTailJs(lines) {
    let lastStoryIdx = -1;
    for (let i = 0; i < lines.length; i++) {
        const t = lines[i].trim();
        if (t && (STREAM_TAG_RE.test(t) || STREAM_BARE_NARRATION_RE.test(t))) lastStoryIdx = i;
    }
    const tailStart = lastStoryIdx + 1;
    if (tailStart >= lines.length) return -1;
    const optPos = {};
    let firstPromptIdx = -1;
    for (let i = tailStart; i < lines.length; i++) {
        const t = lines[i].trim();
        if (!t || t === '```' || STREAM_BARE_DIVIDER_RE.test(t)) continue;
        if (firstPromptIdx < 0 && Object.keys(optPos).length === 0 && STREAM_PROMPT_RE.test(t)) {
            firstPromptIdx = i;
            continue;
        }
        const om = t.match(STREAM_OPT_RE);
        if (om) {
            const letter = (om[1] || om[2] || '').toUpperCase();
            if (['A', 'B', 'C'].includes(letter) && optPos[letter] === undefined) optPos[letter] = i;
        }
    }
    if (optPos.A === undefined || optPos.B === undefined || optPos.C === undefined) return -1;
    if (!(optPos.A < optPos.B && optPos.B < optPos.C)) return -1;
    let splitIdx = firstPromptIdx >= 0 ? firstPromptIdx : optPos.A;
    while (splitIdx > tailStart) {
        const prev = lines[splitIdx - 1].trim();
        if (!prev || STREAM_BARE_DIVIDER_RE.test(prev)) splitIdx--;
        else break;
    }
    return splitIdx;
}

function parseStreamMessages(rawText, allowedSpeakers = null, complete = false, allowPlayerDialogue = false) {
    if (typeof rawText !== 'string' || !rawText) return [];
    let src = rawText.replace(/^\s*```[a-zA-Z0-9_-]*\r?\n/, '').replace(/\r?\n?```\s*$/, '');
    let decIdx = src.search(STREAM_DECISION_SPLIT_RE);
    if (decIdx < 0) decIdx = src.search(STREAM_INLINE_DECISION_RE);
    let body = decIdx >= 0 ? src.slice(0, decIdx) : src;
    let lines = body.split(/\r?\n/);
    if (!complete && decIdx < 0 && !/\r?\n$/.test(body)) {
        lines.pop();
    } else if (decIdx < 0) {
        const tailIdx = detectUnmarkedDecisionTailJs(lines);
        if (tailIdx >= 0) lines = lines.slice(0, tailIdx);
    }
    const allow = Array.isArray(allowedSpeakers) ? new Set(allowedSpeakers) : null;
    const rawMessages = [];
    for (const rawLine of lines) {
        const trimmed = rawLine.trim();
        if (!trimmed || trimmed === '```' || STREAM_BARE_DIVIDER_RE.test(trimmed)) continue;
        if (!complete && rawMessages.length && STREAM_PROMPT_RE.test(trimmed)) break;
        const segments = trimmed.split(STREAM_INLINE_SPLIT_RE);
        for (const seg of segments) {
            const line = seg.trim();
            if (!line || STREAM_BARE_DIVIDER_RE.test(line)) continue;
            const m = line.match(STREAM_TAG_RE);
            if (m) {
                const code = m[1], speaker = (m[2] || '').trim(), text = m[3].trim();
                if (!text || text.length > 4000) continue;
                if (code === 'N') {
                    rawMessages.push({ kind: 'narration', speaker: '', text });
                } else if (code === 'A') {
                    rawMessages.push({ kind: 'action', speaker, text });
                } else if (code === 'D') {
                    rawMessages.push({ kind: 'dialogue', speaker, text });
                }
                continue;
            }
            const bm = line.match(STREAM_BARE_NARRATION_RE);
            if (bm) {
                const text = bm[1].trim();
                if (text && text.length <= 4000) rawMessages.push({ kind: 'narration', speaker: '', text });
                continue;
            }
            if (rawMessages.length) {
                const combined = (rawMessages[rawMessages.length - 1].text + '\n' + line).trim();
                if (combined.length <= 4000) rawMessages[rawMessages.length - 1].text = combined;
            } else if (complete && !line.startsWith('{') && !line.startsWith('---')) {
                rawMessages.push({ kind: 'narration', speaker: '', text: line });
            }
        }
    }
    const messages = [];
    let playerDialogueCount = 0;
    for (const rm of rawMessages) {
        for (const node of normalizeStreamNodeJs(rm.kind, rm.speaker, rm.text)) {
            if (!node.text || node.text.length > 4000) continue;
            if (node.kind === 'action') {
                if (node.speaker && (!allow || allow.has(node.speaker) || node.speaker === '徐志北')) {
                    messages.push(node);
                }
            } else if (node.kind === 'dialogue') {
                if (node.speaker === '徐志北') {
                    if (allowPlayerDialogue && playerDialogueCount < MAX_PLAYER_DIALOGUE_PER_TURN) {
                        playerDialogueCount += 1;
                        messages.push(node);
                    }
                } else if (node.speaker && (!allow || allow.has(node.speaker))) {
                    messages.push(node);
                }
            } else {
                messages.push(node);
            }
        }
    }
    return messages;
}

function extractBalancedJsonObjects(source) {
    const found = [];
    let i = 0;
    while (i < source.length) {
        const start = source.indexOf('{', i);
        if (start < 0) break;
        let depth = 0, inStr = false, esc = false, end = -1;
        for (let j = start; j < source.length; j++) {
            const ch = source[j];
            if (inStr) {
                if (esc) { esc = false; }
                else if (ch === '\\') { esc = true; }
                else if (ch === '"') { inStr = false; }
            } else {
                if (ch === '"') { inStr = true; }
                else if (ch === '{') { depth++; }
                else if (ch === '}') {
                    depth--;
                    if (depth === 0) { end = j + 1; break; }
                }
            }
        }
        if (end > start) {
            found.push(source.slice(start, end));
            i = end;
        } else {
            i = start + 1;
        }
    }
    return found;
}

function normalizeSettlementJson(rawText) {
    if (typeof rawText !== 'string' || !rawText.trim()) throw new Error('后台结算回复为空');
    const hadUnclosedThink = /<think>/i.test(rawText) && !/<\/think>/i.test(rawText);
    let cleaned = rawText.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
    if (!cleaned && hadUnclosedThink) {
        throw new Error('后台结算思考未结束或回复被截断');
    }
    const candidates = [];
    const fenceRe = /```(?:json)?\s*([\s\S]*?)```/gi;
    let fm;
    while ((fm = fenceRe.exec(cleaned)) !== null) {
        const inner = (fm[1] || '').trim();
        if (inner) candidates.push(inner);
    }
    const strippedFence = cleaned.startsWith('```')
        ? cleaned.replace(/^```[a-zA-Z0-9_-]*\r?\n?/, '').replace(/\r?\n?```\s*$/, '').trim()
        : cleaned;
    if (strippedFence) candidates.push(strippedFence);
    for (const block of extractBalancedJsonObjects(strippedFence)) {
        candidates.push(block);
    }
    let text = '';
    let value = null;
    const seen = new Set();
    for (const cand of candidates) {
        if (!cand || seen.has(cand)) continue;
        seen.add(cand);
        try {
            const parsed = JSON.parse(cand);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                const looksSettlement = ('resolution' in parsed) || ('checks' in parsed) || ('operation' in parsed);
                if (!value || looksSettlement) {
                    text = cand;
                    value = parsed;
                    if (looksSettlement) break;
                }
            }
        } catch (_) {}
    }
    if (!value) {
        if (hadUnclosedThink) {
            throw new Error('后台结算思考未结束或回复被截断');
        }
        const preview = cleaned.replace(/\s+/g, ' ').slice(0, 60);
        throw new Error('后台结算回复不是合法JSON对象' + (preview ? '（摘要：' + preview + '）' : ''));
    }
    if (value.resolution && ['A', 'B', 'C'].includes(value.resolution.category)
            && (!value.resolution.conditions || typeof value.resolution.conditions !== 'object' || Array.isArray(value.resolution.conditions))) {
        throw new Error('普通付费行动的resolution.conditions必须是完整对象；澄清或未移动也须填写，无NPC只将npc留空');
    }
    const paths = [['operation'], ['resolution', 'task'], ['resolution', 'conditions'],
        ['resolution', 'sleep', 'start'], ['resolution', 'conditions', 'npc']];
    const edits = [];
    for (const path of paths) {
        let current = value;
        for (const key of path) current = current && typeof current === 'object' ? current[key] : undefined;
        if (current !== '') continue;
        let offset = 0, span = null;
        for (const key of path) {
            span = jsonMemberSpan(text, offset, key);
            if (!span) throw new Error('后台结算' + path.join('.') + '字段重复或缺失');
            offset = span[0];
        }
        edits.push(span);
    }
    for (const span of edits.sort((a, b) => b[0] - a[0])) text = text.slice(0, span[0]) + 'null' + text.slice(span[1]);
    const parsedOut = JSON.parse(text);
    if (parsedOut.fallback_decision && Array.isArray(parsedOut.fallback_decision.options)) {
        for (const opt of parsedOut.fallback_decision.options) {
            if (opt && typeof opt === 'object' && (opt.operation === '' || opt.operation === null)) {
                delete opt.operation;
            }
        }
    }
    return parsedOut;
}

function extractRawForeground(receipt, snapshots) {
    const outcome = receipt && receipt.outcome;
    if (!outcome || outcome.type !== 'committed' || outcome.status !== 'completed' || !outcome.assistant) {
        throw new Error('正式会话未正常完成，结果未提交');
    }
    const snapshot = snapshots.get(outcome.assistant.messageTimestamp);
    if (!snapshot) throw new Error('缺少完成回执对应的消息快照');
    const parts = snapshot.parts || [];
    let lastResult = -1;
    for (let i = 0; i < parts.length; i++) if (parts[i].kind === 'tool_result') lastResult = i;
    const start = lastResult < 0 ? 0 : lastResult + 1;
    const text = parts.slice(start).filter(part => part.kind === 'markdown' && part.content && part.content.trim())
        .map(part => part.content).join('').trim();
    if (!text) throw new Error('前台演播正文为空');
    const pending = [], tools = [];
    for (const part of parts) {
        if (part.kind === 'tool_call') {
            if (!LIVE_READ_TOOLS.includes(part.toolName)) throw new Error('正式互动调用了非许可工具：' + part.toolName);
            pending.push(part);
        } else if (part.kind === 'tool_result') {
            const index = pending.findIndex(call => call.toolName === part.toolName &&
                (!part.toolCallId || part.toolCallId === call.toolCallId || part.toolCallId === call.partId));
            if (index < 0) throw new Error('工具结果缺少对应调用');
            const call = pending.splice(index, 1)[0];
            tools.push({ name: call.toolName, parameters: call.attributes, part_id: part.partId,
                status: part.attributes.status, result_text: part.content });
        }
    }
    if (pending.length || tools.length > 128) throw new Error('工具调用未全部结束或超出128次上限');
    return { text, tools, timestamp: snapshot.messageTimestamp };
}

function sessionText(task, previousError) {
    const turns = generationTurns(task, previousError);
    return turns.map(turn => turn.content).join('\n\n');
}

async function markLiveDirty(config) {
    if (config && config.liveSession) {
        config.liveSession = { ...config.liveSession, dirty: true };
        await PluginConfig.flush(config);
    }
}

async function executeSessionV2(config, task, model, session) {
    const returnChatId = await currentChat();
    const startedAt = Date.now();
    const dualStage = config.dualStageEnabled !== false && task.dual_stage_protocol === 1;
    const protocolMode = dualStage ? 'dual_stream_v2' : 'single_prefix_v2';
    config.inFlight = { request_id: task.request_id, lease: task.lease, model_key: model.key, entry_mode: task.entry_mode,
        is_v2: true, chat_id: session.chatId, return_chat_id: returnChatId, started_at: startedAt };
    await PluginConfig.flush(config);
    let expired = false;
    const timeout = setTimeout(() => { expired = true; void Tools.Chat.cancel(session.chatId).catch(error => { lastError = String(error.message || error); }); }, SESSION_TIMEOUT);
    const tools = [], passes = [];
    try {
        const { token } = await http('/api/story/bridge-info');
        const liveState = config.liveSession || {};
        const material = await http(workerPath(task, 'material'), {
            lease: task.lease, chat_id: session.chatId, participant_id: session.participantId,
            delivery_version: 2, protocol_mode: protocolMode,
            synced_zone0_sha256: liveState.zone0Sha || '', synced_zone1_sha256: liveState.zone1Sha || '',
            last_committed_sequence: liveState.lastCommittedSeq || 0, is_fresh_session: !!session.isFresh,
            ...(session.isFresh && liveState.lastTailHook ? { continuity_hook: liveState.lastTailHook } : {})
        }, token);
        if (!material || material.delivery_version !== 2 || typeof material.zone0_global !== 'string'
                || typeof material.zone1_scene !== 'string' || typeof material.input_text !== 'string'
                || !material.delivery || !/^[0-9a-f]{64}$/.test(material.delivery.input_sha256)
                || !/^[0-9a-f]{64}$/.test(material.delivery.zone0_sha256)
                || !/^[0-9a-f]{64}$/.test(material.delivery.zone1_sha256)
                || !/^[0-9a-f]{48}$/.test(material.delivery.id)) {
            throw new Error('v2程序交付资料不完整，未生成');
        }
        await syncCardPrefixes(config, model, session, material.zone0_global, material.zone1_scene,
            material.zone0_sha256, material.zone1_sha256);
        const delivered = { ...material.delivery };
        const nextCommittedSeq = (material.last_committed_sequence || 0) + 1;

        if (protocolMode === 'dual_stream_v2') {
            if (!material.settlement_spec || typeof material.settlement_spec.system_prompt !== 'string') {
                throw new Error('缺少双阶段后台结算规格');
            }
            const allowedSpeakers = Array.isArray(material.allowed_speakers) ? material.allowed_speakers : [];
            const allowPlayerDialogue = material.protagonist_style !== 'silent';
            let streamRev = 0, lastPushedCount = -1, lastPushAt = 0, thinkingSent = false;
            let pendingPreview = null, previewFlushPromise = null;
            const drainPreview = () => {
                if (previewFlushPromise) return previewFlushPromise;
                previewFlushPromise = (async () => {
                    while (pendingPreview) {
                        const next = pendingPreview;
                        pendingPreview = null;
                        try {
                            await http(workerPath(task, 'stream'), {
                                lease: task.lease, stage: next.stage, messages: next.messages, revision: next.revision
                            }, token, 8);
                        } catch (_) {}
                    }
                })().finally(() => { previewFlushPromise = null; });
                return previewFlushPromise;
            };
            const pushPreview = (stage, messages) => {
                pendingPreview = { stage, messages, revision: ++streamRev };
                return drainPreview();
            };
            const resumeCp = (material.stage1_checkpoint && typeof material.stage1_checkpoint === 'object'
                && typeof material.stage1_checkpoint.foreground_text === 'string'
                && material.stage1_checkpoint.foreground_text.trim()
                && material.stage1_checkpoint.base_audit && typeof material.stage1_checkpoint.base_audit === 'object')
                ? material.stage1_checkpoint
                : null;
            let fg;
            let genMs = 0;
            let genPasses = 1;
            let finalPreviewMsgs = [];
            let baseAudit;
            let resumedFromSameChat = true;
            if (resumeCp) {
                fg = { text: resumeCp.foreground_text };
                genMs = Number.isSafeInteger(resumeCp.generation_ms) && resumeCp.generation_ms >= 0 ? resumeCp.generation_ms : 0;
                genPasses = 0;
                finalPreviewMsgs = Array.isArray(resumeCp.foreground_messages) && resumeCp.foreground_messages.length
                    ? resumeCp.foreground_messages
                    : parseStreamMessages(fg.text, allowedSpeakers, true, allowPlayerDialogue);
                const prevAudit = resumeCp.base_audit;
                const prevUserTs = (prevAudit.delivery && Number.isSafeInteger(prevAudit.delivery.user_message_timestamp))
                    ? prevAudit.delivery.user_message_timestamp
                    : (prevAudit.outcome && prevAudit.outcome.userMessageTimestamp);
                delivered.user_message_timestamp = prevUserTs;
                resumedFromSameChat = Boolean(prevAudit.chat_id && prevAudit.chat_id === session.chatId);
                baseAudit = {
                    ...prevAudit,
                    chat_id: session.chatId,
                    participant_id: session.participantId,
                    workspace: config.workspacePath || prevAudit.workspace || '',
                    delivery: delivered,
                };
                await pushPreview('settling', finalPreviewMsgs);
            } else {
                const snapshots = new Map();
                let receipt = null;
                const passStarted = Date.now();
                const request = { kind: 'submit', chatId: session.chatId, runtime: 'main',
                    input: { text: material.input_text, attachments: [], replyToMessageTimestamp: null },
                    turn: { kind: 'execute', participantId: session.participantId }, notifyReply: false };
                for await (const event of Tools.Chat.sendMessageStreaming(request)) {
                    if (event.type === 'part') {
                        if (event.chatId !== session.chatId) throw new Error('会话事件身份不符');
                        const old = snapshots.get(event.messageTimestamp);
                        if (!old || event.revision >= old.revision) snapshots.set(event.messageTimestamp, event);
                        const parts = event.parts || [];
                        let lastRes = -1;
                        for (let i = 0; i < parts.length; i++) if (parts[i].kind === 'tool_result') lastRes = i;
                        const tail = parts.slice(lastRes + 1);
                        const md = tail.filter(p => p.kind === 'markdown' && p.content).map(p => p.content).join('');
                        const hasThinking = tail.some(p => p.kind === 'thinking' || p.kind === 'reasoning');
                        if (md) {
                            const parsed = parseStreamMessages(md, allowedSpeakers, false, allowPlayerDialogue);
                            const now = Date.now();
                            if (parsed.length > lastPushedCount || (parsed.length > 0 && now - lastPushAt >= 180)) {
                                lastPushedCount = parsed.length;
                                lastPushAt = now;
                                pushPreview('streaming', parsed);
                            }
                        } else if (hasThinking && !thinkingSent) {
                            thinkingSent = true;
                            pushPreview('thinking', []);
                        }
                    } else if (event.type === 'completed') receipt = event.result;
                }
                if (expired) { await markLiveDirty(config); throw new Error('正式会话超过10分钟，已取消；原行动保留，需显式重试'); }
                if (!receipt || receipt.chatId !== session.chatId) { await markLiveDirty(config); throw new Error('缺少当前正式会话的完成回执'); }
                const stamp = receipt.outcome && receipt.outcome.userMessageTimestamp;
                if (!Number.isSafeInteger(stamp) || stamp <= 0) { await markLiveDirty(config); throw new Error('缺少资料交付的用户消息回执'); }
                const saved = await Tools.Chat.getMessages(session.chatId, { order: 'desc', limit: 12 });
                const message = saved.messages && saved.messages.find(item => item.timestamp === stamp && item.sender === 'user');
                const suffix = message && typeof message.content === 'string' ? message.content.slice(material.input_text.length) : '';
                if (saved.chatId !== session.chatId || !message || typeof message.content !== 'string'
                        || !(message.content === material.input_text || (message.content.startsWith(material.input_text)
                        && /^\s*<workspace_attachment>[\s\S]*?<\/workspace_attachment>\s*$/.test(suffix)))) {
                    await markLiveDirty(config);
                    throw new Error('正式会话保存的资料不完整或已改变，未提交');
                }
                delivered.user_message_timestamp = stamp;
                try { fg = extractRawForeground(receipt, snapshots); }
                catch (err) { await markLiveDirty(config); throw err; }
                genMs = Math.max(0, Date.now() - passStarted);
                finalPreviewMsgs = parseStreamMessages(fg.text, allowedSpeakers, true, allowPlayerDialogue);
                await pushPreview('settling', finalPreviewMsgs);
                if (config.liveSession) {
                    config.liveSession.observedChars = (config.liveSession.observedChars || 0)
                        + material.input_text.length + fg.text.length + fg.tools.reduce((n, t) => n + t.result_text.length, 0);
                    await PluginConfig.flush(config);
                }
                tools.push(...fg.tools);
                passes.push({ outcome: receipt.outcome, snapshot_message_timestamp: fg.timestamp,
                    tool_start: 0, tool_count: fg.tools.length, started_at: passStarted, completed_at: Date.now() });
                baseAudit = { api: 'Tools.Chat.sendMessageStreaming', chat_id: session.chatId,
                    participant_id: session.participantId, workspace: config.workspacePath,
                    outcome: receipt.outcome, snapshot_message_timestamp: fg.timestamp,
                    started_at: startedAt, completed_at: Date.now(), read_passes: passes,
                    repair_keys: [], tools, delivery: delivered };
            }
            const stage1Checkpoint = {
                foreground_text: fg.text,
                foreground_messages: finalPreviewMsgs,
                generation_ms: genMs,
                base_audit: baseAudit,
            };

            const settleTarget = await resolveSettlementModel(config, model);
            const settleThinkMode = effectiveSettlementThinkingMode(config);
            const settleStarted = Date.now();
            let lastSettleError = '';
            for (let attempt = 1; attempt <= 3; attempt++) {
                if (expired) {
                    await markLiveDirty(config);
                    const expErr = new Error('正式会话超过10分钟，已取消；原行动保留，需显式重试');
                    expErr.stage1Checkpoint = stage1Checkpoint;
                    throw expErr;
                }
                const effectiveThinking = settleThinkMode === 'on' || (settleThinkMode === 'auto' && attempt > 1);
                if (attempt > 1) {
                    await pushPreview('settling_retry', finalPreviewMsgs);
                }
                const settleUser = JSON.stringify({
                    context: material.settlement_spec.user_context,
                    foreground_script: fg.text,
                    foreground_messages: finalPreviewMsgs,
                    ...(lastSettleError ? { previous_settlement_error: lastSettleError, retry_attempt: attempt } : {})
                });
                let settlementObj;
                let settleTimer = null;
                try {
                    const callPromise = Tools.Chat.call({
                        functionType: settleTarget.slot,
                        recordTokenUsage: true,
                        enableThinking: effectiveThinking,
                        turns: [
                            { kind: 'system', content: material.settlement_spec.system_prompt },
                            { kind: 'user', content: settleUser }
                        ]
                    });
                    const timeoutPromise = new Promise((_, reject) => {
                        settleTimer = setTimeout(() => reject(new Error('后台结算调用超时')), 120000);
                    });
                    const generated = await Promise.race([callPromise, timeoutPromise]);
                    if (settleTimer !== null) { clearTimeout(settleTimer); settleTimer = null; }
                    settlementObj = normalizeSettlementJson(generated && generated.text);
                } catch (err) {
                    if (settleTimer !== null) { clearTimeout(settleTimer); settleTimer = null; }
                    lastSettleError = String(err.message || err);
                    if (attempt < 3) continue;
                    await markLiveDirty(config);
                    const settleErr = new Error('后台结算(' + settleTarget.slot + ')失败：' + lastSettleError);
                    settleErr.stage1Checkpoint = stage1Checkpoint;
                    throw settleErr;
                }
                const settleMs = Math.max(0, Date.now() - settleStarted);
                const dualText = JSON.stringify({ dual_stage_version: 1, foreground_text: fg.text, settlement: settlementObj });
                const submitBody = {
                    lease: task.lease,
                    text: dualText,
                    conversation_audit: {
                        ...baseAudit,
                        completed_at: Date.now(),
                        settlement_audit: {
                            function_type: settleTarget.slot,
                            model_id: settleTarget.model ? settleTarget.model.model_id : '',
                            fallback: !!settleTarget.fallback,
                            attempts: attempt,
                            thinking_mode: settleThinkMode,
                            thinking_enabled: effectiveThinking,
                            duration_ms: settleMs,
                            resumed_stage2: !!resumeCp
                        }
                    },
                    timing: {
                        generation_ms: genMs,
                        settlement_ms: settleMs,
                        preflight_ms: 0,
                        generation_passes: genPasses,
                        settlement_passes: attempt,
                        settlement_model_id: settleTarget.model ? settleTarget.model.model_id : ''
                    }
                };
                try {
                    const res = await http(workerPath(task, 'result'),
                        attempt < 3 ? { ...submitBody, allow_settlement_retry: true } : submitBody, token);
                    if (res && res.retryable_settlement === true && attempt < 3) {
                        lastSettleError = res.error || '后台结算校验未通过';
                        continue;
                    }
                    await rememberRejection(config, res && res.task);
                    const tailHook = buildTailHook(finalPreviewMsgs);
                    if (res && res.task && res.task.status === 'committed') {
                        const actualSeq = (res.receipt && Number.isSafeInteger(res.receipt.state_version))
                            ? res.receipt.state_version
                            : ((res.task && Number.isSafeInteger(res.task.result_sequence)) ? res.task.result_sequence : nextCommittedSeq);
                        config.liveSession = { ...config.liveSession,
                            turnCount: ((config.liveSession && config.liveSession.turnCount) || 0) + 1,
                            lastCommittedSeq: actualSeq,
                            ...(tailHook ? { lastTailHook: tailHook } : {}),
                            dirty: Boolean(resumeCp && !resumedFromSameChat) };
                        await PluginConfig.flush(config);
                    } else {
                        await markLiveDirty(config);
                    }
                    return { __alreadyDelivered: true };
                } catch (err) {
                    if (!(err.statusCode >= 400 && err.statusCode < 500)) {
                        return { ...submitBody, __meta: { isV2: true, nextCommittedSeq, tailHook: buildTailHook(finalPreviewMsgs) } };
                    }
                    await markLiveDirty(config);
                    throw err;
                }
            }
            await markLiveDirty(config);
            const limitErr = new Error('后台结算重试超限：' + lastSettleError);
            limitErr.stage1Checkpoint = stage1Checkpoint;
            throw limitErr;
        }

        // single_prefix_v2: single-stage slim mode (no redundant /preflight, 1 JSON format-repair pass).
        let text = material.input_text;
        let formatRepair = false;
        for (let pass = 0; pass < 2; pass++) {
            if (expired) { await markLiveDirty(config); throw new Error('正式会话超过10分钟，已取消；原行动保留，需显式重试'); }
            const snapshots = new Map();
            let receipt = null;
            const passStarted = Date.now();
            const request = { kind: 'submit', chatId: session.chatId, runtime: 'main',
                input: { text, attachments: [], replyToMessageTimestamp: null },
                turn: { kind: 'execute', participantId: session.participantId }, notifyReply: false };
            for await (const event of Tools.Chat.sendMessageStreaming(request)) {
                if (event.type === 'part') {
                    if (event.chatId !== session.chatId) throw new Error('会话事件身份不符');
                    const old = snapshots.get(event.messageTimestamp);
                    if (!old || event.revision >= old.revision) snapshots.set(event.messageTimestamp, event);
                } else if (event.type === 'completed') receipt = event.result;
            }
            if (expired) { await markLiveDirty(config); throw new Error('正式会话超过10分钟，已取消；原行动保留，需显式重试'); }
            if (!receipt || receipt.chatId !== session.chatId) { await markLiveDirty(config); throw new Error('缺少当前正式会话的完成回执'); }
            if (pass === 0) {
                const stamp = receipt.outcome && receipt.outcome.userMessageTimestamp;
                if (!Number.isSafeInteger(stamp) || stamp <= 0) { await markLiveDirty(config); throw new Error('缺少资料交付的用户消息回执'); }
                const saved = await Tools.Chat.getMessages(session.chatId, { order: 'desc', limit: 12 });
                const message = saved.messages && saved.messages.find(item => item.timestamp === stamp && item.sender === 'user');
                const suffix = message && typeof message.content === 'string' ? message.content.slice(material.input_text.length) : '';
                if (saved.chatId !== session.chatId || !message || typeof message.content !== 'string'
                        || !(message.content === material.input_text || (message.content.startsWith(material.input_text)
                        && /^\s*<workspace_attachment>[\s\S]*?<\/workspace_attachment>\s*$/.test(suffix)))) {
                    await markLiveDirty(config);
                    throw new Error('正式会话保存的资料不完整或已改变，未提交');
                }
                delivered.user_message_timestamp = stamp;
            }
            let final;
            try {
                final = finalMessage(receipt, snapshots, 'live_interaction', true);
            } catch (error) {
                const detail = String(error.message || error);
                if (pass !== 0 || formatRepair || !/JSON|conditions|字段重复或缺失/.test(detail)) { await markLiveDirty(config); throw error; }
                const snapshot = snapshots.get(receipt.outcome && receipt.outcome.assistant && receipt.outcome.assistant.messageTimestamp);
                if (!snapshot || snapshot.parts.some(part => part.kind === 'tool_call')) {
                    await markLiveDirty(config);
                    throw new Error('格式纠正前的回复包含工具调用，未自动重发');
                }
                passes.push({ outcome: receipt.outcome, snapshot_message_timestamp: receipt.outcome.assistant.messageTimestamp,
                    tool_start: 0, tool_count: 0, started_at: passStarted, completed_at: Date.now() });
                formatRepair = true;
                text = JSON.stringify({ entry_mode: 'live_interaction', request_id: task.request_id,
                    format_repair: { attempt: 1, max_attempts: 1, error: detail },
                    task_envelope: material.envelope,
                    instruction: '同一任务的格式纠正，上一回复未接受，也不是剧情事实。不要改动已拟定的正文、事件、时间、记忆分类或操作；只把同一回复重新输出为一个完整合法JSON对象，键恰为task_envelope.output_contract所列。不得使用代码围栏、前后解释或省略字段；无操作operation、无任务task、无睡眠起点start及无对象npc明确写空字符串两个双引号。保持原行动、冻结点与知情边界。' });
                continue;
            }
            if (config.liveSession) {
                config.liveSession.observedChars = (config.liveSession.observedChars || 0)
                    + text.length + final.text.length + final.tools.reduce((n, t) => n + t.result_text.length, 0);
                await PluginConfig.flush(config);
            }
            const toolStart = tools.length;
            tools.push(...final.tools);
            if (tools.length > 128) throw new Error('本次任务文件工具累计超过128次上限');
            passes.push({ outcome: receipt.outcome, snapshot_message_timestamp: final.timestamp,
                tool_start: toolStart, tool_count: final.tools.length, started_at: passStarted, completed_at: Date.now() });
            const audit = { api: 'Tools.Chat.sendMessageStreaming', chat_id: session.chatId,
                participant_id: session.participantId, workspace: config.workspacePath,
                outcome: receipt.outcome, snapshot_message_timestamp: final.timestamp,
                started_at: startedAt, completed_at: Date.now(), read_passes: passes,
                repair_keys: [], tools, delivery: delivered };
            const timing = { generation_ms: passes.reduce((sum, item) => sum + Math.max(0, item.completed_at - item.started_at), 0),
                preflight_ms: 0, generation_passes: passes.length };
            return { lease: task.lease, text: final.text, conversation_audit: audit, timing,
                __meta: { isV2: true, nextCommittedSeq } };
        }
        throw new Error('单阶段v2流程未取得结果');
    } catch (error) {
        await Tools.Chat.cancel(session.chatId).catch(() => {});
        throw error;
    } finally {
        clearTimeout(timeout);
        try { await restoreChat(session.chatId, returnChatId); }
        catch (error) { lastError = '生成结束但恢复聊天失败：' + String(error.message || error); }
    }
}

async function executeSession(config, task, model, session) {
    if (task.reading_preflight !== 1 || task.entry_mode === 'live_interaction' &&
            (task.live_reading_revision !== 2 || task.action_contract_revision !== 1 || task.material_delivery_revision !== 1)) {
        throw new Error('请重启本地故事服务并重试原行动，以加载程序资料交付接口');
    }
    if (task.entry_mode === 'live_interaction' && task.material_delivery_v2 === 1) {
        return executeSessionV2(config, task, model, session);
    }
    const returnChatId = await currentChat();
    const startedAt = Date.now();
    config.inFlight = { request_id: task.request_id, lease: task.lease, model_key: model.key, entry_mode: task.entry_mode,
        chat_id: session.chatId, return_chat_id: returnChatId, started_at: startedAt };
    await PluginConfig.flush(config);
    let expired = false;
    const timeout = setTimeout(() => { expired = true; void Tools.Chat.cancel(session.chatId).catch(error => { lastError = String(error.message || error); }); }, SESSION_TIMEOUT);
    const tools = [], passes = [];
    let repairKeys = [];
    let formatRepair = false;
    try {
        const previous = task.previous_validation_error || (config.lastRejection && config.lastRejection.request_id === task.request_id ? config.lastRejection.error : '');
        const { token } = await http('/api/story/bridge-info');
        const inline = task.entry_mode === 'live_interaction';
        let delivered = null;
        let text;
        if (inline) {
            if (task.material_delivery_revision !== 1) throw new Error('请重启本地故事服务以加载程序资料交付接口');
            const material = await http(workerPath(task, 'material'), { lease: task.lease,
                chat_id: session.chatId, participant_id: session.participantId }, token);
            if (!material || typeof material.input_text !== 'string' || !material.delivery
                    || !/^[0-9a-f]{64}$/.test(material.delivery.input_sha256)
                    || !/^[0-9a-f]{48}$/.test(material.delivery.id)) throw new Error('程序交付资料不完整，未生成');
            text = material.input_text;
            delivered = { ...material.delivery };
        } else text = sessionText(task, previous);
        const inlineEnvelope = inline ? JSON.parse(text).envelope : null;
        for (let pass = 0; pass < (task.entry_mode === 'scene_chat' ? 1 : 2); pass++) {
            if (expired) throw new Error('正式会话超过10分钟，已取消；原行动保留，需显式重试');
            const snapshots = new Map();
            let receipt = null;
            const passStarted = Date.now();
            const textForCall = text;
            const request = { kind: 'submit', chatId: session.chatId, runtime: 'main',
                input: { text: textForCall, attachments: [], replyToMessageTimestamp: null },
                turn: { kind: 'execute', participantId: session.participantId }, notifyReply: false };
            for await (const event of Tools.Chat.sendMessageStreaming(request)) {
                if (event.type === 'part') {
                    if (event.chatId !== session.chatId) throw new Error('会话事件身份不符');
                    const old = snapshots.get(event.messageTimestamp);
                    if (!old || event.revision >= old.revision) snapshots.set(event.messageTimestamp, event);
                } else if (event.type === 'completed') receipt = event.result;
            }
            if (expired) throw new Error('正式会话超过10分钟，已取消；原行动保留，需显式重试');
            if (!receipt || receipt.chatId !== session.chatId) throw new Error('缺少当前正式会话的完成回执');
            if (inline && pass === 0) {
                const stamp = receipt.outcome && receipt.outcome.userMessageTimestamp;
                if (!Number.isSafeInteger(stamp) || stamp <= 0) throw new Error('缺少资料交付的用户消息回执');
                const saved = await Tools.Chat.getMessages(session.chatId, { order: 'desc', limit: 4 });
                const message = saved.messages && saved.messages.find(item => item.timestamp === stamp && item.sender === 'user');
                const suffix = message && typeof message.content === 'string' ? message.content.slice(text.length) : '';
                if (saved.chatId !== session.chatId || !message || typeof message.content !== 'string'
                        || !(message.content === text || (message.content.startsWith(text)
                        && /^\s*<workspace_attachment>[^<]*<\/workspace_attachment>\s*$/.test(suffix)))) {
                    throw new Error('正式会话保存的资料不完整或已改变，未提交');
                }
                delivered.user_message_timestamp = stamp;
            }
            let final;
            try {
                final = finalMessage(receipt, snapshots, task.entry_mode, inline);
            } catch (error) {
                const detail = String(error.message || error);
                if (!inline || pass !== 0 || formatRepair || !/JSON/.test(detail)) throw error;
                const snapshot = snapshots.get(receipt.outcome && receipt.outcome.assistant && receipt.outcome.assistant.messageTimestamp);
                if (!snapshot || snapshot.parts.some(part => part.kind === 'tool_call')) {
                    throw new Error('格式纠正前的回复包含工具调用，未自动重发');
                }
                const invalidStamp = receipt.outcome.assistant.messageTimestamp;
                passes.push({ outcome: receipt.outcome, snapshot_message_timestamp: invalidStamp,
                    tool_start: 0, tool_count: 0, started_at: passStarted, completed_at: Date.now(),
                    preflight_completed_at: Date.now() });
                formatRepair = true;
                text = JSON.stringify({ entry_mode: 'live_interaction', request_id: task.request_id,
                    format_repair: { attempt: 1, max_attempts: 1, error: detail },
                    task_envelope: inlineEnvelope,
                    instruction: '同一任务的格式纠正，上一回复未接受，也不是剧情事实。不要改动已拟定的正文、事件、时间、记忆分类或操作；只把同一回复重新输出为一个完整合法JSON对象，键恰为task_envelope.output_contract所列。不得使用代码围栏、前后解释或省略字段；无操作operation、无任务task、无睡眠起点start及无对象npc明确写空字符串两个双引号。保持原行动、冻结点与知情边界。' });
                continue;
            }
            if (task.entry_mode === 'scene_chat') {
                config.sceneSession.observedChars += text.length + final.text.length + final.tools.reduce((n, t) => n + t.result_text.length, 0);
                await PluginConfig.flush(config);
            }
            if (task.entry_mode === 'live_interaction') {
                config.liveSession.observedChars += text.length + final.text.length + final.tools.reduce((n,t) => n + t.result_text.length, 0);
                await PluginConfig.flush(config);
            }
            const toolStart = tools.length;
            tools.push(...final.tools);
            if (tools.length > 128) throw new Error('本次任务文件工具累计超过128次上限');
            passes.push({ outcome: receipt.outcome, snapshot_message_timestamp: final.timestamp,
                tool_start: toolStart, tool_count: final.tools.length, started_at: passStarted, completed_at: Date.now() });
            const audit = { api: 'Tools.Chat.sendMessageStreaming', chat_id: session.chatId,
                participant_id: session.participantId, workspace: config.workspacePath,
                outcome: receipt.outcome, snapshot_message_timestamp: final.timestamp,
                started_at: startedAt, completed_at: Date.now(), read_passes: passes,
                repair_keys: repairKeys, tools, ...(delivered ? {delivery: delivered} : {}) };
            const body = { lease: task.lease, text: final.text, conversation_audit: audit };
            let check;
            const preflightStarted = Date.now();
            check = await http(workerPath(task, 'preflight'), body, token);
            const preflightElapsed = Date.now() - preflightStarted;
            passes[passes.length - 1].preflight_completed_at = passes[passes.length - 1].completed_at + preflightElapsed;
            if (check.ready === true) {
                const timing = { generation_ms: passes.reduce((sum, item) => sum + Math.max(0, item.completed_at - item.started_at), 0),
                    preflight_ms: passes.reduce((sum, item) => sum + Math.max(0, item.preflight_completed_at - item.completed_at), 0),
                    generation_passes: passes.length };
                return { ...body, timing };
            }
            if (!Array.isArray(check.missing_keys) || !check.missing_keys.length || !Array.isArray(check.read_targets)) {
                throw new Error('读取预检返回无效结果，未提交');
            }
            if (pass === 1) throw new Error('同一任务的一次补救后仍缺必需正文：' + check.missing_keys.join(', ') + '；已停止自动补读，请重试原行动');
            repairKeys = check.missing_keys.slice();
            if (task.entry_mode === 'live_interaction') {
                text=JSON.stringify({entry_mode:'live_interaction',request_id:task.request_id,
                    read_repair:{attempt:1,max_attempts:1,missing_keys:check.missing_keys,read_targets:check.read_targets},
                    task_envelope:inline ? inlineEnvelope : JSON.parse(generationTurns(task,previous)[0].content),
                    instruction:'同一任务的提交前补读，上一草稿未接受。仅补读read_targets所列缺失正文；已核验部分继续有效，不重复整包。核对实际返回末行，缺失则继续取得；据新正文重新核对上一草稿并按task_envelope.output_contract返回整份JSON。保持原行动、冻结点及知情范围，不推进到下一行动。最多补读一次，仍不足则停止。'});
                continue;
            }
            text = JSON.stringify({ entry_mode: 'story_bridge', retrieval_mode: 'operit_session',
                round_identity: task.round_identity, read_repair: { attempt: 1, max_attempts: 1,
                    missing_keys: check.missing_keys, read_targets: check.read_targets },
                instruction: '这是同一任务的提交前补读，当前草稿未提交。先用真实只读文件工具完整读取read_targets所列本任务正文；start_line/end_line是需取得的范围，截断须补完，目录和元数据不算正文。前一阶段实际读取已由程序核验并保留，不必重读；不得从历史冒充本次缺失读取，不得删除必需key掩盖漏读。根据刚取得原文重新核对上一条草稿中的正文、事件、记忆、required_keys、evidence和V1，按同一output_contract返回完整裸JSON。保持原行动及身份，不推进到下一回合、不加新意图。若仍缺资料或V1失败，说明具体阻塞。' });
        }
        throw new Error('补读流程未取得结果');
    } catch (error) {
        await Tools.Chat.cancel(session.chatId).catch(() => {});
        throw error;
    } finally {
        clearTimeout(timeout);
        try { await restoreChat(session.chatId, returnChatId); }
        catch (error) { lastError = '生成结束但恢复聊天失败：' + String(error.message || error); }
    }
}

async function interruptedSession(config) {
    const flight = config.inFlight;
    if (!flight) return;
    await Tools.Chat.cancel(flight.chat_id).catch(() => {});
    const isV2 = Boolean(flight.is_v2 || (flight.entry_mode === 'live_interaction' && config.liveSession && config.liveSession.syncedCardSig && config.liveSession.chatId === flight.chat_id));
    if (!config.outbox) config.outbox = { request_id: flight.request_id, model_key: flight.model_key, entry_mode: flight.entry_mode,
        ...(isV2 ? { meta: { isV2: true } } : {}),
        body: { lease: flight.lease, error: 'Operit在正式会话执行中重启，未自动重复生成；原行动已保留，请显式重试。' } };
    if (isV2 && config.liveSession) {
        config.liveSession = { ...config.liveSession, dirty: true };
    }
    config.inFlight = null;
    await PluginConfig.flush(config);
    await restoreChat(flight.chat_id, flight.return_chat_id).catch(() => {});
}

let modelInfo = null, modelDetails = null, modelCheckedAt = 0;

function cliPayload(raw) {
    for (let i = 0; i < 6; i++) {
        if (typeof raw === 'string') {
            const trimmed = raw.trim();
            if (!trimmed) return null;
            raw = JSON.parse(trimmed);
            continue;
        }
        if (raw && typeof raw === 'object') {
            if (raw.success === false) throw new Error(raw.error || 'Operit命令执行失败');
            if (Array.isArray(raw) || raw.modelId || Array.isArray(raw.bindings) || Array.isArray(raw.models) || raw.updated === true) return raw;
            const nested = raw.data ?? raw.result ?? raw.content ?? raw.text ?? raw.value;
            if (nested !== undefined) { raw = nested; continue; }
            return raw;
        }
        break;
    }
    return raw;
}

function cliObject(raw) {
    for (let i = 0; i < 6; i++) {
        if (typeof raw === 'string') { raw = JSON.parse(raw); continue; }
        if (raw && typeof raw === 'object') {
            if (raw.modelId) return raw;
            if (raw.success === false) throw new Error(raw.error || '模型配置读取失败');
            const nested = raw.data ?? raw.result ?? raw.content ?? raw.text;
            if (nested !== undefined) { raw = nested; continue; }
        }
        break;
    }
    throw new Error('无法读取 Operit 功能模型，请检查模型绑定');
}

function normalizeCatalogModel(item) {
    if (!item || typeof item !== 'object') return null;
    const providerId = String(item.providerId || item.provider_id || '').trim();
    const modelId = String(item.modelId || item.model_id || '').trim();
    if (!providerId || !modelId || providerId.length > 256 || modelId.length > 256) return null;
    const providerName = String(item.providerName || item.provider_name || providerId).trim().slice(0, 256) || providerId;
    return {
        provider_id: providerId,
        provider_name: providerName,
        model_id: modelId,
        pricing_configured: item.pricing != null || item.pricing_configured === true
    };
}

async function fetchModelCatalog(force = false) {
    const fresh = !force && (Date.now() - catalogCheckedAt <= 30000)
        && (modelCatalogCache.models.length > 0 || modelCatalogCache.bindings.length > 0);
    if (fresh) return modelCatalogCache;

    const modelMap = new Map();
    const providerNames = new Map();
    try {
        let rawModels = [];
        if (typeof Tools !== 'undefined' && Tools.Models && typeof Tools.Models.listSummaries === 'function') {
            const res = await Tools.Models.listSummaries();
            rawModels = Array.isArray(res) ? res : (res && Array.isArray(res.models) ? res.models : []);
        }
        if (!rawModels.length && typeof Tools !== 'undefined' && Tools.SoftwareSettings && typeof Tools.SoftwareSettings.exec === 'function') {
            const res = cliPayload(await Tools.SoftwareSettings.exec(['model', 'list', '--json']));
            rawModels = Array.isArray(res) ? res : (res && Array.isArray(res.models) ? res.models : (res && Array.isArray(res.items) ? res.items : []));
        }
        for (const item of rawModels) {
            const norm = normalizeCatalogModel(item);
            if (!norm) continue;
            const key = norm.provider_id + '\0' + norm.model_id;
            if (!modelMap.has(key)) modelMap.set(key, norm);
            if (!providerNames.has(norm.provider_id)) providerNames.set(norm.provider_id, norm.provider_name);
        }
    } catch (_) {}

    const models = Array.from(modelMap.values())
        .sort((a, b) => a.provider_name.localeCompare(b.provider_name) || a.model_id.localeCompare(b.model_id))
        .slice(0, 120);

    const bindingMap = new Map();
    try {
        if (typeof Tools !== 'undefined' && Tools.SoftwareSettings && typeof Tools.SoftwareSettings.exec === 'function') {
            let rows = [];
            try {
                const res = cliPayload(await Tools.SoftwareSettings.exec(['model', 'function-list', '--json']));
                rows = Array.isArray(res) ? res : (res && Array.isArray(res.bindings) ? res.bindings : []);
            } catch (_) {
                rows = [];
            }
            if (!rows.length) {
                for (const slot of KNOWN_FUNCTION_SLOTS) {
                    try {
                        const one = cliObject(await Tools.SoftwareSettings.exec(['model', 'function-show', slot, '--json']));
                        rows.push({ functionType: slot, providerId: one.providerId, modelId: one.modelId });
                    } catch (_) {}
                }
            }
            for (const row of rows) {
                if (!row || typeof row !== 'object') continue;
                const slot = String(row.functionType || row.function_type || '').trim();
                const providerId = String(row.providerId || row.provider_id || '').trim();
                const modelId = String(row.modelId || row.model_id || '').trim();
                if (!/^[A-Z][A-Z0-9_]{0,63}$/.test(slot)) continue;
                bindingMap.set(slot, {
                    function_type: slot,
                    provider_id: providerId.slice(0, 256),
                    model_id: modelId.slice(0, 256),
                    provider_name: (providerNames.get(providerId) || providerId).slice(0, 256)
                });
            }
        }
    } catch (_) {}

    const slotOrder = new Map(KNOWN_FUNCTION_SLOTS.map((name, idx) => [name, idx]));
    const bindings = Array.from(bindingMap.values())
        .sort((a, b) => {
            const ai = slotOrder.has(a.function_type) ? slotOrder.get(a.function_type) : 999;
            const bi = slotOrder.has(b.function_type) ? slotOrder.get(b.function_type) : 999;
            return ai !== bi ? ai - bi : a.function_type.localeCompare(b.function_type);
        })
        .slice(0, 32);

    modelCatalogCache = { models, bindings };
    catalogCheckedAt = Date.now();
    return modelCatalogCache;
}

async function bindFunctionSlot(slot, providerId, modelId) {
    if (typeof slot !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(slot)) {
        throw new Error('功能槽位名称无效');
    }
    const prov = String(providerId || '').trim();
    const mod = String(modelId || '').trim();
    if (!prov || !mod || prov.length > 256 || mod.length > 256) {
        throw new Error('请选择有效的服务商与模型');
    }
    const raw = await Tools.SoftwareSettings.exec(['model', 'function-set', slot, prov, mod, '--json']);
    cliPayload(raw);
    modelInfo = null;
    modelDetails = null;
    modelCheckedAt = 0;
    settlementModelInfo = null;
    settlementCheckedAt = 0;
    catalogCheckedAt = 0;
    return { function_type: slot, provider_id: prov, model_id: mod };
}

async function resolveModel(config) {
    if (config && config.primaryModelMode === 'fixed' && config.primaryProviderId && config.primaryModelId) {
        const providerId = String(config.primaryProviderId).trim();
        const modelId = String(config.primaryModelId).trim();
        const key = JSON.stringify(['FIXED', providerId, modelId]);
        if (!modelInfo || modelInfo.key !== key || Date.now() - modelCheckedAt > 30000) {
            let details = null;
            try {
                details = cliObject(await Tools.SoftwareSettings.exec(['model', 'show', providerId, modelId, '--json']));
            } catch (_) {
                const catalog = await fetchModelCatalog(true);
                const found = catalog.models.find(m => m.provider_id === providerId && m.model_id === modelId);
                if (found) details = { providerId: found.provider_id, modelId: found.model_id, providerName: found.provider_name, pricing: found.pricing_configured ? {} : null };
            }
            if (!details || details.providerId !== providerId || details.modelId !== modelId) {
                throw new Error('故事专属主模型未找到或已删除（' + modelId + '），请在设置页重新选择主模型或切换回功能槽');
            }
            modelDetails = { provider_name: details.providerName || providerId, pricing_configured: details.pricing != null };
            modelCheckedAt = Date.now();
        }
        modelInfo = { key, function_type: 'FIXED', provider_id: providerId, model_id: modelId, ...modelDetails };
        return modelInfo;
    }
    const slot = (config && config.functionType) || 'CHAT';
    const binding = cliObject(await Tools.SoftwareSettings.exec(['model', 'function-show', slot, '--json']));
    if (!binding.providerId || !binding.modelId) throw new Error('故事功能未绑定模型');
    const key = JSON.stringify([slot, binding.providerId, binding.modelId]);
    if (!modelInfo || modelInfo.key !== key || Date.now() - modelCheckedAt > 30000) {
        const details = cliObject(await Tools.SoftwareSettings.exec(['model', 'show', binding.providerId, binding.modelId, '--json']));
        if (details.providerId !== binding.providerId || details.modelId !== binding.modelId) throw new Error('模型配置已改变，请稍后重试');
        modelDetails = { provider_name: details.providerName || binding.providerId,
            pricing_configured: details.pricing != null };
        modelCheckedAt = Date.now();
    }
    modelInfo = { key, function_type: slot, provider_id: binding.providerId,
        model_id: binding.modelId, ...modelDetails };
    return modelInfo;
}

async function checkModel(config, key) {
    if (key && (await resolveModel(config)).key !== key) throw new Error('生成模型已变更，请确认当前模型后重试。');
}

async function resolveSettlementModel(config, primaryModel) {
    const slot = (config && config.settlementFunctionType) || 'SUMMARY';
    const primarySlot = (config && config.functionType) || 'CHAT';
    const isFixedPrimary = config && config.primaryModelMode === 'fixed';
    const baseModel = primaryModel || modelInfo;
    if (!isFixedPrimary && slot === primarySlot && baseModel) {
        settlementModelInfo = baseModel;
        settlementFallback = false;
        settlementCheckedAt = Date.now();
        return { slot, model: baseModel, fallback: false };
    }
    const cacheFresh = settlementModelInfo && settlementModelInfo.function_type === slot && (Date.now() - settlementCheckedAt <= 30000);
    if (cacheFresh && !settlementFallback) {
        return { slot, model: settlementModelInfo, fallback: false };
    }
    try {
        const binding = cliObject(await Tools.SoftwareSettings.exec(['model', 'function-show', slot, '--json']));
        if (!binding.providerId || !binding.modelId) throw new Error('槽位未绑定模型');
        let providerName = binding.providerId, pricingConfigured = false;
        try {
            const details = cliObject(await Tools.SoftwareSettings.exec(['model', 'show', binding.providerId, binding.modelId, '--json']));
            providerName = details.providerName || binding.providerId;
            pricingConfigured = details.pricing != null;
        } catch (_) {}
        const key = JSON.stringify([slot, binding.providerId, binding.modelId]);
        settlementModelInfo = { key, function_type: slot, provider_id: binding.providerId,
            model_id: binding.modelId, provider_name: providerName, pricing_configured: pricingConfigured };
        settlementFallback = false;
        settlementCheckedAt = Date.now();
        return { slot, model: settlementModelInfo, fallback: false };
    } catch (_) {
        settlementFallback = true;
        let fallbackModel = !isFixedPrimary ? (baseModel || null) : null;
        if (!fallbackModel) {
            try {
                const fb = cliObject(await Tools.SoftwareSettings.exec(['model', 'function-show', primarySlot, '--json']));
                if (fb.providerId && fb.modelId) {
                    let providerName = fb.providerId, pricingConfigured = false;
                    try {
                        const details = cliObject(await Tools.SoftwareSettings.exec(['model', 'show', fb.providerId, fb.modelId, '--json']));
                        providerName = details.providerName || fb.providerId;
                        pricingConfigured = details.pricing != null;
                    } catch (_) {}
                    fallbackModel = {
                        key: JSON.stringify([primarySlot, fb.providerId, fb.modelId]),
                        function_type: primarySlot,
                        provider_id: fb.providerId,
                        model_id: fb.modelId,
                        provider_name: providerName,
                        pricing_configured: pricingConfigured
                    };
                }
            } catch (_) {}
        }
        settlementModelInfo = fallbackModel;
        settlementCheckedAt = Date.now();
        return { slot: primarySlot, model: fallbackModel, fallback: true };
    }
}

function settings() {
    if (!settingsPromise) settingsPromise = PluginConfig.use('story_bridge', {
        enabled: false, endpoint: 'http://127.0.0.1:5000', functionType: 'CHAT',
        primaryModelMode: 'slot', primaryProviderId: '', primaryModelId: '',
        outbox: null, lastRejection: null,
        workspacePath: '', chatId: '', participantId: '', inFlight: null, liveSessionPolicy:'continuous',
        dualStageEnabled: true, settlementFunctionType: 'SUMMARY', settlementThinking: false,
        settlementThinkingMode: 'auto',
        maxTurnsPerSession: DEFAULT_MAX_TURNS
    });
    return settingsPromise;
}

async function http(path, body, token, readTimeout = 45) {
    const config = await settings();
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (token) headers['X-Story-Bridge'] = token;
    const options = {
        url: config.endpoint + path, method: body === undefined ? 'GET' : 'POST',
        headers,
        connect_timeout: 8, read_timeout: readTimeout, responseType: 'text', validateStatus: false,
        follow_redirects: false
    };
    if (body !== undefined) options.body = JSON.stringify(body);
    const result = await Tools.Net.http(options);
    let data = null;
    let parseErr = null;
    if (typeof result.content === 'string') {
        try { data = JSON.parse(result.content); } catch (err) { parseErr = err; }
    } else {
        data = result.content;
    }
    if (result.statusCode < 200 || result.statusCode >= 300) {
        const error = new Error((data && data.error) || ('本地故事服务返回 ' + result.statusCode));
        error.statusCode = result.statusCode;
        throw error;
    }
    if (parseErr) {
        throw new Error('本地故事服务返回了非JSON响应');
    }
    return data;
}

function pulse(key, lease, token, entry_mode, onLeaseLost) {
    let pending = false;
    const id = setInterval(async () => {
        if (pending) return;
        pending = true;
        try { await http(workerPath({request_id: key, entry_mode}, 'heartbeat'), { lease }, token); }
        catch (error) {
            lastError = String(error.message || error);
            if (error && error.statusCode === 409) {
                clearInterval(id);
                heartbeats.delete(id);
                if (typeof onLeaseLost === 'function') {
                    try { onLeaseLost(); } catch (_) {}
                }
            }
        }
        finally { pending = false; }
    }, 20000);
    heartbeats.add(id);
    return () => { clearInterval(id); heartbeats.delete(id); };
}

// Match Python str.isspace() and count Unicode code points, including punctuation.
function memoryLength(text) {
    let count = 0;
    for (const char of text) {
        if (!/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(char)) count++;
    }
    return count;
}

function jsonMemberSpan(text, start, name) {
    const whitespace = index => { while (/\s/.test(text[index] || '') && index < text.length) index++; return index; };
    function stringEnd(index) {
        for (index++; index < text.length; index++) {
            if (text[index] === '\\') index++;
            else if (text[index] === '"') return index + 1;
        }
        throw new Error('JSON字符串未闭合');
    }
    function valueEnd(index) {
        if (text[index] === '"') return stringEnd(index);
        if (text[index] !== '{' && text[index] !== '[') {
            while (index < text.length && !/[\s,}\]]/.test(text[index])) index++;
            return index;
        }
        let depth = 0;
        for (; index < text.length; index++) {
            const char = text[index];
            if (char === '"') index = stringEnd(index) - 1;
            else if (char === '{' || char === '[') depth++;
            else if ((char === '}' || char === ']') && --depth === 0) return index + 1;
        }
        throw new Error('JSON对象未闭合');
    }
    let index = whitespace(start), found = null;
    if (text[index++] !== '{') return null;
    while ((index = whitespace(index)) < text.length && text[index] !== '}') {
        const keyEnd = stringEnd(index);
        const key = JSON.parse(text.slice(index, keyEnd));
        index = whitespace(keyEnd);
        if (text[index++] !== ':') return null;
        const begin = whitespace(index), end = valueEnd(begin);
        if (key === name) {
            if (found) return null; // Leave duplicate-key rejection to the fixed executor.
            found = [begin, end];
        }
        index = whitespace(end);
        if (text[index] === ',') index++;
        else break;
    }
    return found;
}

function oversizedMemory(text) {
    if (typeof text !== 'string') return null;
    try {
        const value = JSON.parse(text);
        const deltas = value && value.memory_deltas;
        if (!deltas || typeof deltas !== 'object' || Array.isArray(deltas)) return null;
        const field = deltas.l1_new_round ? 'l1_new_round' : 'new_round_detail';
        const original = deltas[field];
        if (typeof original !== 'string' || memoryLength(original) <= 280) return null;
        const object = jsonMemberSpan(text, 0, 'memory_deltas');
        const span = object && jsonMemberSpan(text, object[0], field);
        if (!span || text[span[0]] !== '"') return null;
        return { field, original, span, length: memoryLength(original) };
    } catch (_) { return null; }
}

function resolutionReminder(envelope) {
    const policy=envelope.resolution_policy;
    const paid=policy ? policy.conditions_required : envelope.output_contract.resolution && envelope.output_contract.resolution.category!=='SYSTEM';
    return paid
        ? '本次是普通付费行动：resolution.conditions必须是完整对象，恰含intensity/effective_progress/scene/npc/action_changed/stress_signals/breakout_triggered，不能为空或null。只作澄清、未移动、未接触也交对象；无推进/无变化按事实填false，无NPC仅npc写空字符串，stress_signals为0、breakout_triggered为数组。禁止progress/action_change/stress_count/breakout等别名。'
        : '本次是免费SYSTEM：resolution.category为SYSTEM，conditions写空字符串（传输后为null），不提交行动计数对象。';
}

function generationTurns(task, previousError) {
    if (task.entry_mode === 'live_interaction') {
        const turns = task.turns.map(turn => {
            const envelope = JSON.parse(turn.content);
            if (envelope.entry_mode !== 'live_interaction' || !envelope.output_contract) throw new Error('正式互动信封缺少输出契约');
            envelope.output_contract.operation = '';
            envelope.output_contract.handoff = '';
            const resolution = envelope.output_contract.resolution;
            if (resolution) {
                resolution.task = '';
                if (resolution.sleep) resolution.sleep.start = '';
                if (resolution.conditions && typeof resolution.conditions === 'object') resolution.conditions.npc = '';
            }
            envelope.instruction += ' '+resolutionReminder(envelope)+' 最终传输约定：无操作operation、无任务resolution.task、无睡眠起点resolution.sleep.start及无对象conditions.npc均写空字符串两个双引号；不要留空。有对象则交原合法对象。按packet.read_ranges依序读完全部范围；grep_code只定位不替代正文读取，不用list_files/find_files；截断缩小范围补齐，不读许可外文件。';
            return { ...turn, content: JSON.stringify(envelope) };
        });
        const envelope=JSON.parse(turns[0].content);
        const contract = { ...envelope.output_contract, operation:'', handoff:'' };
        return [...turns, {kind:'user',content:JSON.stringify({output_contract:contract,resolution_policy:envelope.resolution_policy,operation_context:envelope.operation_context,
            instruction:resolutionReminder(envelope)+' 已预检operation_context.requested须保持；地点别名以operation_context为准，不能再把已解析回家写成歧义。'+'最终仅交单个合法JSON，键恰为本次output_contract所列；不照抄结构说明。读取阶段逐项照用packet.path和packet.read_ranges中的start_line、end_line调用read_file_part，核对真实返回末行；完成全部范围及必需补读后才输出。文件尾空白不等于正文未读；grep_code只定位，不计正文覆盖；禁止list_files/find_files，遇截断缩小范围补齐未覆盖行，重试也重新读取本次更新后的资料包；上一失败草稿不是事实，承接正式存档与accepted_history。无操作operation、无待处理handoff、无任务resolution.task、无睡眠起点resolution.sleep.start和无对象conditions.npc均明确写空字符串两个双引号；例如sleep为{\"kind\":\"none\",\"start\":\"\",\"evidence\":\"\"}且task为空字符串。禁止冒号后直接接逗号，不修补残缺JSON。按设定/存档/意图推演连贯剧情及本段decision，不定长、不等整场结束。若契约要求resolution，完整提交分类/实际游戏时间/事件原文依据/本次记忆事实及必要源摘要、有效行动条件；程序算费用与实际结算。事件group=host_events时target必须是系统宿主，其他事件用实际场内登记姓名；固定ABC不能重新定价；自定义只判档，不填面板数值；预扣不代表疲劳，最终不足5由执行器判断。SYSTEM休息须实际过渡及睡眠起止，不伪造整夜；纯道具由执行器处理。严格保留角色知情，不以系统数值写NPC台词。',
            previous_validation_error:previousError||JSON.parse(turns[0].content).previous_validation_error||''})}];
    }
    if (task.entry_mode === 'scene_chat') return [...task.turns, {kind: 'user', content: JSON.stringify({
        output_contract: task.output_contract || {messages: [{kind: 'dialogue', speaker: '本场人物姓名', text: '回应本次输入'}], facts_delta: [], needs: [], handoff: ''},
        instruction: '上面是字段结构示例，不能照抄示例台词。最终仅输出一个合法JSON对象。按本任务output_contract的桥接传输约定：handoff没有转交说明时明确写空字符串（两个双引号），有转交则写说明字符串；程序解析后将空字符串转换为内部无转交值。不能省略值；facts_delta和needs首版必须为[]。每个冒号后必须有合法值，禁止尾逗号、代码围栏和解释。返回前核对JSON语法及本任务全部资料行已读完。'
    })}];
    const reminder = '输出单个JSON对象。memory_deltas.l1_new_round为单段150～220个去空白Unicode字符，标点、数字、字母均计数，280是拒绝上限，不是目标。保留时间地点、在场、实际动作和场景冻结点，删重复修饰，不复制正文。只写本回合记忆，不手写回合号。按末条output_contract逐一核对节点键集合与容器；每个键仅出现一次，不把data.json展示节点当请求模板。提交前核对required_keys与evidence引用key是否均在本轮真实工具结果中完整取得；缺失先补读并重评，不能从历史复用或删key掩盖。返回前在内部修正previous_validation_error，禁止照抄失败结构或伪造V1。保持原行动、request_id、base_revision与current_round。';
    return [...task.turns, { kind: 'user', content: JSON.stringify({
        contract_reminder: reminder, previous_validation_error: previousError || null
    }) }];
}

async function repairMemory(config) {
    const pending = config.outbox;
    if (!pending || ['scene_chat', 'live_interaction'].includes(pending.entry_mode) || pending.repairAttempted || !pending.body.text) return;
    const problem = oversizedMemory(pending.body.text);
    if (!problem) return;
    // Persist before the extra call: restarting must not repeat a paid repair indefinitely.
    config.outbox = { ...pending, repairAttempted: true };
    await PluginConfig.flush(config);
    try {
        await checkModel(config, pending.model_key);
        const generated = await Tools.Chat.call({ functionType: config.functionType, recordTokenUsage: true,
            turns: [
                { kind: 'system', content: '压缩一段故事事实记忆。只返回一个合法JSON字符串（用双引号包裹），不要返回对象、Markdown或说明。目标150～220个去空白Unicode字符，标点数字字母均计数。保留原文中的时间地点、人物、行动因果、不可逆事实和终点；只删冗词与重复内容，不新增、改变或推测事实，不替代宿主行动。不要生成正文、事件或数值，不手写回合号。' },
                { kind: 'user', content: JSON.stringify({ field: problem.field, length: problem.length,
                    target: '150～220', original: problem.original }) }
            ] });
        const replacement = JSON.parse(generated.text);
        if (typeof replacement !== 'string' || memoryLength(replacement) < 150 || memoryLength(replacement) > 220 ||
                /[\x00\r\n]/.test(replacement) || /^\s*【\d/.test(replacement)) {
            throw new Error('压缩结果须为150～220字的单段JSON字符串');
        }
        const [begin, end] = problem.span;
        const text = pending.body.text.slice(0, begin) + JSON.stringify(replacement) + pending.body.text.slice(end);
        // Preserve every byte outside the L1 string: large integers, duplicate keys and events are untouched.
        config.outbox = { ...config.outbox, body: { ...pending.body, text } };
        await PluginConfig.flush(config);
    } catch (error) {
        lastError = 'L1记忆压缩未完成：' + String(error.message || error);
        // The original stays in outbox; the server applies its normal rejection, never truncation.
    }
}

async function rememberRejection(config, task) {
    if (task && task.error && task.request_id &&
            (!config.lastRejection || config.lastRejection.request_id !== task.request_id || config.lastRejection.error !== task.error)) {
        config.lastRejection = { request_id: task.request_id, error: task.error };
        await PluginConfig.flush(config);
    }
}

async function deliver(config, token) {
    if (!config.outbox) return;
    const pending = config.outbox;
    await PluginConfig.flush(config);
    try {
        const result = await http(workerPath(pending, 'result'), pending.body, token);
        await rememberRejection(config, result.task);
        if (pending.entry_mode === 'live_interaction' && pending.meta && pending.meta.isV2) {
            if (result && result.task && result.task.status === 'committed') {
                config.liveSession = { ...config.liveSession,
                    turnCount: ((config.liveSession && config.liveSession.turnCount) || 0) + 1,
                    lastCommittedSeq: pending.meta.nextCommittedSeq || ((config.liveSession && config.liveSession.lastCommittedSeq) || 0) + 1,
                    lastTailHook: pending.meta.tailHook || (config.liveSession && config.liveSession.lastTailHook) || '',
                    dirty: false };
            } else if (config.liveSession) {
                config.liveSession = { ...config.liveSession, dirty: true };
            }
        }
    } catch (error) {
        // A 4xx response is authoritative rejection; transport/5xx keeps the exact saved output.
        if (!(error.statusCode >= 400 && error.statusCode < 500)) throw error;
        lastError = String(error.message || error);
        if (pending.entry_mode === 'live_interaction' && pending.meta && pending.meta.isV2 && config.liveSession) {
            config.liveSession = { ...config.liveSession, dirty: true };
        }
    }
    config.outbox = null;
    await PluginConfig.flush(config);
}

async function work() {
    const config = await settings();
    await interruptedSession(config);
    const { token } = await http('/api/story/bridge-info');
    if (config.outbox) {
        const pending = config.outbox;
        const stop = pulse(pending.request_id, pending.body.lease, token, pending.entry_mode);
        try { await repairMemory(config); await deliver(config, token); } finally { stop(); }
        return true;
    }
    const status = await http('/api/story/tasks');
    syncServiceEpoch(status && status.service_epoch);
    if (status.story_protocol !== 3 || status.reading_preflight !== 1) throw new Error('请先停止旧的本地故事服务并重新启动，以加载正式会话读取接口（协议3）。');
    if (status.task && status.task.status === 'queued' && status.task.entry_mode === 'live_interaction'
            && (status.interaction_protocol !== 3 || status.live_reading_revision !== 2
                || status.action_contract_revision !== 1 || status.material_delivery_revision !== 1)) {
        throw new Error('请先重启本地故事服务以加载程序资料交付接口；旧任务须显式重试后再生成。');
    }
    await rememberRejection(config, status.task);
    const model = await resolveModel(config);
    lastError = '';
    let session;
    let response;
    if (status.save_epoch && config.legacySaveEpoch && config.legacySaveEpoch !== status.save_epoch && config.chatId) {
        boundChatCache.delete(config.chatId);
        config.chatId = '';
        await PluginConfig.flush(config);
    }
    if (status.task && status.task.status === 'queued') {
        if (status.task.entry_mode !== 'live_interaction') {
            config.legacySaveEpoch = status.save_epoch || '';
            session = await ensureSession(config, model);
        }
        response = await http('/api/story/worker/claim', { model }, token);
    } else {
        try { response = await http('/api/story/scene/worker/claim', { model }, token); }
        catch (error) { if (error.statusCode === 404) return false; throw error; }
    }
    if (!response.task) {
        response = await http('/api/story/worker/claim', { model }, token);
        if (response.task && response.task.entry_mode !== 'live_interaction') {
            config.legacySaveEpoch = response.task.save_epoch || status.save_epoch || '';
            session = await ensureSession(config, model);
        }
    }
    if (!response.task) return false;
    const task = response.task;
    syncServiceEpoch(task.service_epoch);
    const stop = pulse(task.request_id, task.lease, token, task.entry_mode, () => {
        if (session && session.chatId) {
            void Tools.Chat.cancel(session.chatId).catch(() => {});
        }
    });
    try {
        let body;
        try {
            await checkModel(config, model.key);
            if (task.entry_mode === 'scene_chat') session = await sceneSession(config, model, task);
            if (task.entry_mode === 'live_interaction') session = await liveSession(config, model, task);
            if (!session) throw new Error('未准备正式会话，任务未生成');
            body = await executeSession(config, task, model, session);
        } catch (error) {
            if (task.entry_mode === 'live_interaction' && task.material_delivery_v2 === 1) {
                await markLiveDirty(config);
            }
            body = {
                lease: task.lease,
                error: String(error.message || error).slice(0, 500),
                ...(error && error.stage1Checkpoint ? { stage1_checkpoint: error.stage1Checkpoint } : {})
            };
        }
        if (body && body.__alreadyDelivered) {
            config.inFlight = null;
            await PluginConfig.flush(config);
            return true;
        }
        const meta = body && body.__meta ? body.__meta : null;
        if (body && '__meta' in body) { body = { ...body }; delete body.__meta; }
        config.outbox = { request_id: task.request_id, entry_mode: task.entry_mode, model_key: model.key, body, ...(meta ? { meta } : {}) };
        config.inFlight = null;
        await PluginConfig.flush(config);
        await repairMemory(config);
        await deliver(config, token);
        return true;
    } finally { stop(); }
}

let lastTickDidWork = false;
function tick() {
    if (busy) return busy;
    lastTickDidWork = false;
    busy = work().then(didWork => { lastTickDidWork = !!didWork; }, error => { lastError = String(error.message || error); })
        .finally(() => { busy = null; });
    return busy;
}

async function startBridge(config) {
    if (running) return;
    if (starting) return starting;
    starting = (async () => {
        const status = await http('/api/story/tasks');
        syncServiceEpoch(status && status.service_epoch);
        if (status.story_protocol !== 3 || status.reading_preflight !== 1) throw new Error('请重启本地故事服务以加载提交前读取校验，再启动桥接');
        const model = await resolveModel(config);
        await resolveSettlementModel(config, model).catch(() => {});
        if (!config.workspacePath) throw new Error('故事会话尚未绑定项目工作区');
        config.enabled = true;
        await PluginConfig.flush(config);
        lastError = '';
        arm();
    })().catch(error => { lastError = String(error.message || error); throw error; })
        .finally(() => { starting = null; });
    return starting;
}

function runtimeReport(config) {
    const models = Array.isArray(modelCatalogCache.models) ? modelCatalogCache.models : [];
    const bindings = Array.isArray(modelCatalogCache.bindings) ? modelCatalogCache.bindings : [];
    const settleThinkMode = effectiveSettlementThinkingMode(config);
    return { phase: lastError ? 'error' : starting ? 'starting' : config.inFlight ? 'generating' : running ? 'ready' : 'paused',
        running, busy: !!busy || !!starting, last_error: lastError.slice(0, 500),
        plugin_version: PLUGIN_VERSION, model: modelInfo, session: liveSessionView(config),
        dual_stage: config.dualStageEnabled !== false,
        primary_model_mode: config.primaryModelMode === 'fixed' ? 'fixed' : 'slot',
        primary_function_type: config.functionType || 'CHAT',
        settlement_function_type: config.settlementFunctionType || 'SUMMARY',
        settlement_model: settlementModelInfo,
        settlement_fallback: !!settlementFallback,
        settlement_thinking: settleThinkMode === 'on',
        settlement_thinking_mode: settleThinkMode,
        available_models: models.map(m => ({ provider_id: m.provider_id, provider_name: m.provider_name, model_id: m.model_id })),
        function_bindings: bindings.map(b => ({ function_type: b.function_type, provider_id: b.provider_id, provider_name: b.provider_name, model_id: b.model_id })) };
}

async function monitor() {
    if (monitorBusy) return;
    monitorBusy = true;
    try {
        const config = await settings();
        await fetchModelCatalog(false).catch(() => {});
        let model = null;
        try {
            model = await resolveModel(config);
            if (lastError && /^故事专属主模型|^无法读取 Operit 功能模型|^故事功能未绑定/.test(lastError)) lastError = '';
        } catch (err) {
            modelInfo = null;
            lastError = String(err.message || err).slice(0, 500);
        }
        await resolveSettlementModel(config, model).catch(() => {});
        const { token } = await http('/api/story/bridge-info');
        const response = await http('/api/story/worker/control', { runtime: runtimeReport(config),
            ack_id: config.controlAck || null, ack_error: config.controlError || '' }, token);
        syncServiceEpoch(response && response.service_epoch);
        controlSupported = true;
        if (response.command && response.command.id !== config.controlAck) {
            const command = response.command;
            let error = '';
            try {
                await receive({
                    action: command.action,
                    sessionPolicy: command.session_policy,
                    dualStage: command.dual_stage,
                    settlementFunctionType: command.settlement_function_type,
                    settlementThinking: command.settlement_thinking,
                    settlementThinkingMode: command.settlement_thinking_mode,
                    primaryModelMode: command.primary_model_mode,
                    functionType: command.primary_function_type,
                    primaryProviderId: command.primary_provider_id,
                    primaryModelId: command.primary_model_id,
                    slot: command.slot,
                    providerId: command.provider_id,
                    modelId: command.model_id,
                    useAsSettlement: command.use_as_settlement,
                    maxTurnsPerSession: command.max_turns,
                    _fromMonitor: true
                });
            } catch (failure) { error = String(failure.message || failure).slice(0, 500); lastError = error; }
            await fetchModelCatalog(false).catch(() => {});
            config.controlAck = command.id;
            config.controlError = error;
            await PluginConfig.flush(config);
            await http('/api/story/worker/control', { runtime: runtimeReport(config),
                ack_id: command.id, ack_error: error }, token);
        }
    } catch (error) {
        if (error.statusCode === 404) controlSupported = false;
        // A disconnected server is observed by heartbeat expiry; do not overwrite a useful session error.
    } finally { monitorBusy = false; }
}

function startMonitor() {
    if (monitorTimer !== null) return;
    monitorTimer = setInterval(() => { void monitor(); }, 6000);
    void monitor();
}

function cancelWaitSleep() {
    if (waitSleepTimer !== null) {
        clearTimeout(waitSleepTimer);
        waitSleepTimer = null;
    }
    if (waitSleepResolve !== null) {
        const fn = waitSleepResolve;
        waitSleepResolve = null;
        fn();
    }
}

function waitSleep(ms) {
    return new Promise(resolve => {
        cancelWaitSleep();
        waitSleepResolve = resolve;
        waitSleepTimer = setTimeout(() => {
            waitSleepTimer = null;
            waitSleepResolve = null;
            resolve();
        }, ms);
    });
}

async function waitLoop() {
    if (waitLoopActive) return;
    waitLoopActive = true;
    let cachedToken = '';
    let needTick = true;
    let spinCount = 0;
    try {
        while (running) {
            let hadTaskSignal = false;
            if (needTick) {
                await tick();
                if (lastError) {
                    spinCount = Math.min(8, spinCount + 1);
                } else if (lastTickDidWork) {
                    spinCount = 0;
                }
            }
            needTick = true;
            if (!running) break;
            if (spinCount > 0 && lastError) {
                await waitSleep(Math.min(2500, 300 * Math.pow(2, spinCount - 1)));
                if (!running) break;
            }
            try {
                if (!cachedToken) {
                    const info = await http('/api/story/bridge-info');
                    cachedToken = info && info.token || '';
                }
                const waited = await http('/api/story/worker/wait?since=' + workerSeq + '&timeout=25', undefined, cachedToken, 35);
                if (!running) break;
                if (waited && waited.service_epoch) syncServiceEpoch(waited.service_epoch);
                if (waited && Number.isSafeInteger(waited.seq)) workerSeq = waited.seq;
                if (waited && waited.has_control) {
                    await monitor();
                    if (!running) break;
                    if (!waited.has_task) { needTick = false; continue; }
                }
                if (waited && waited.has_task) {
                    hadTaskSignal = true;
                    if (!lastTickDidWork) {
                        spinCount = Math.min(8, spinCount + 1);
                        await waitSleep(Math.min(2500, 300 * Math.pow(2, spinCount - 1)));
                        if (!running) break;
                    }
                    continue;
                }
                if (!hadTaskSignal) spinCount = 0;
            } catch (_) {
                cachedToken = '';
                workerSeq = 0;
                if (!running) break;
                await waitSleep(2500);
            }
        }
    } finally {
        cancelWaitSleep();
        waitLoopActive = false;
    }
}

function arm() {
    if (running && waitLoopActive) return;
    running = true;
    void waitLoop();
}

function assertIdleForSettings(config, verb) {
    if (busy || starting || config.inFlight || config.outbox) {
        throw new Error('请等待当前行动结束后' + verb);
    }
}

async function receive(input = {}) {
    const config = await settings();
    startMonitor();
    const action = input.action || 'status';
    let mutated = false;
    let wantCatalog = !!input.includeCatalog || action === 'ui_snapshot' || action === 'bind_function_slot';
    let forceCatalog = !!input.forceRefresh || action === 'bind_function_slot';

    if (action === 'start') {
        await startBridge(config);
        mutated = true;
    } else if (action === 'stop') {
        config.enabled = false;
        await PluginConfig.flush(config);
        running = false;
        cancelWaitSleep();
        if (timer !== null) clearInterval(timer);
        timer = null;
        if (!busy) lastError = '';
        mutated = true;
        // An already claimed round completes once; stopping prevents another claim.
    } else if (action === 'reset_session') {
        if (busy || starting) throw new Error('请等待当前行动结束后重建会话');
        await resetLiveSession(config, '玩家手动重建');
        if (config.chatId) {
            boundChatCache.delete(config.chatId);
            config.chatId = '';
            await PluginConfig.flush(config);
        }
        mutated = true;
    } else if (action === 'session_policy') {
        assertIdleForSettings(config, '调整会话方式');
        if (!['continuous', 'service_restart', 'per_action'].includes(input.sessionPolicy)) throw new Error('会话方式无效');
        config.liveSessionPolicy = input.sessionPolicy;
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'dual_stage') {
        assertIdleForSettings(config, '切换生成模式');
        if (typeof input.dualStage !== 'boolean') throw new Error('双阶段开关须为布尔值');
        config.dualStageEnabled = input.dualStage;
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'settlement_slot') {
        assertIdleForSettings(config, '切换后台结算槽位');
        if (typeof input.settlementFunctionType !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(input.settlementFunctionType)) throw new Error('后台结算槽位名称无效');
        config.settlementFunctionType = input.settlementFunctionType;
        if (input.settlementThinkingMode !== undefined) {
            if (!['auto', 'off', 'on'].includes(input.settlementThinkingMode)) throw new Error('副模型思考模式仅支持auto/off/on');
            config.settlementThinkingMode = input.settlementThinkingMode;
            config.settlementThinking = input.settlementThinkingMode === 'on';
        } else if (typeof input.settlementThinking === 'boolean') {
            config.settlementThinking = input.settlementThinking;
            config.settlementThinkingMode = input.settlementThinking ? 'on' : 'off';
        }
        settlementCheckedAt = 0;
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'settlement_thinking') {
        assertIdleForSettings(config, '切换副模型思考模式');
        if (input.settlementThinkingMode !== undefined) {
            if (!['auto', 'off', 'on'].includes(input.settlementThinkingMode)) throw new Error('副模型思考模式仅支持auto/off/on');
            config.settlementThinkingMode = input.settlementThinkingMode;
            config.settlementThinking = input.settlementThinkingMode === 'on';
        } else if (typeof input.settlementThinking === 'boolean') {
            config.settlementThinking = input.settlementThinking;
            config.settlementThinkingMode = input.settlementThinking ? 'on' : 'off';
        } else {
            throw new Error('副模型思考模式须为auto/off/on或布尔值');
        }
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'primary_model') {
        assertIdleForSettings(config, '切换主模型');
        const mode = input.primaryModelMode === 'fixed' ? 'fixed' : 'slot';
        if (mode === 'fixed') {
            const prov = String(input.primaryProviderId || '').trim();
            const mod = String(input.primaryModelId || '').trim();
            if (!prov || !mod || prov.length > 256 || mod.length > 256) throw new Error('请选择有效的主模型服务商与模型');
            const prevMode = config.primaryModelMode, prevProv = config.primaryProviderId, prevMod = config.primaryModelId;
            config.primaryModelMode = 'fixed';
            config.primaryProviderId = prov;
            config.primaryModelId = mod;
            modelCheckedAt = 0;
            try {
                await resolveModel(config);
            } catch (err) {
                config.primaryModelMode = prevMode;
                config.primaryProviderId = prevProv;
                config.primaryModelId = prevMod;
                modelCheckedAt = 0;
                throw err;
            }
        } else {
            const slot = input.functionType !== undefined ? String(input.functionType).trim() : (config.functionType || 'CHAT');
            if (!/^[A-Z][A-Z0-9_]{0,63}$/.test(slot)) throw new Error('主模型功能槽名称无效');
            const prevMode = config.primaryModelMode, prevSlot = config.functionType;
            config.primaryModelMode = 'slot';
            config.functionType = slot;
            modelCheckedAt = 0;
            try {
                await resolveModel(config);
            } catch (err) {
                config.primaryModelMode = prevMode;
                config.functionType = prevSlot;
                modelCheckedAt = 0;
                throw err;
            }
        }
        lastError = '';
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'bind_function_slot') {
        assertIdleForSettings(config, '修改功能模型绑定');
        await bindFunctionSlot(input.slot, input.providerId, input.modelId);
        if (input.useAsSettlement === true) {
            config.settlementFunctionType = input.slot;
            await PluginConfig.flush(config);
        }
        lastError = '';
        mutated = true;
    } else if (action === 'max_turns') {
        assertIdleForSettings(config, '调整切窗轮数');
        const n = Number(input.maxTurnsPerSession);
        if (!Number.isInteger(n) || n < 2 || n > 30) throw new Error('自动切窗轮数须为2～30之间的整数');
        config.maxTurnsPerSession = n;
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'update_settings') {
        assertIdleForSettings(config, '更新高级连接配置');
        if (input.workspacePath !== undefined) {
            const wp = String(input.workspacePath).trim();
            if (!wp.startsWith('/')) throw new Error('工作区路径须为以 / 开头的绝对路径');
            config.workspacePath = wp.replace(/\/$/, '');
        }
        if (input.endpoint !== undefined) {
            const ep = String(input.endpoint).trim().replace(/\/$/, '');
            if (!/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(ep)) throw new Error('本地服务地址仅允许 http://127.0.0.1:<端口>');
            config.endpoint = ep;
        }
        if (input.maxTurnsPerSession !== undefined) {
            const n = Number(input.maxTurnsPerSession);
            if (!Number.isInteger(n) || n < 2 || n > 30) throw new Error('自动切窗轮数须为2～30之间的整数');
            config.maxTurnsPerSession = n;
        }
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action === 'configure') {
        if (running || busy || config.outbox || config.inFlight) throw new Error('请先停止桥接并等待当前任务结束');
        if (input.functionType !== undefined) {
            if (!/^[A-Z][A-Z0-9_]{0,63}$/.test(input.functionType)) throw new Error('功能模型名称无效');
            config.functionType = input.functionType;
            modelCheckedAt = 0;
        }
        if (input.primaryModelMode !== undefined) {
            if (!['slot', 'fixed'].includes(input.primaryModelMode)) throw new Error('primaryModelMode须为slot或fixed');
            config.primaryModelMode = input.primaryModelMode;
            modelCheckedAt = 0;
        }
        if (input.primaryProviderId !== undefined) {
            config.primaryProviderId = String(input.primaryProviderId || '').trim();
            modelCheckedAt = 0;
        }
        if (input.primaryModelId !== undefined) {
            config.primaryModelId = String(input.primaryModelId || '').trim();
            modelCheckedAt = 0;
        }
        if (input.workspacePath !== undefined) {
            if (typeof input.workspacePath !== 'string' || !input.workspacePath.startsWith('/')) throw new Error('workspacePath须为已确认的工作区VFS绝对路径');
            config.workspacePath = input.workspacePath.replace(/\/$/, '');
        }
        if (input.endpoint !== undefined) {
            if (!/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(input.endpoint)) throw new Error('endpoint只允许本机IPv4端口');
            config.endpoint = input.endpoint;
        }
        if (input.sessionPolicy !== undefined) {
            if (!['continuous', 'service_restart', 'per_action'].includes(input.sessionPolicy)) throw new Error('会话方式无效');
            config.liveSessionPolicy = input.sessionPolicy;
        }
        if (input.dualStage !== undefined) {
            if (typeof input.dualStage !== 'boolean') throw new Error('dualStage须为布尔值');
            config.dualStageEnabled = input.dualStage;
        }
        if (input.settlementFunctionType !== undefined) {
            if (typeof input.settlementFunctionType !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(input.settlementFunctionType)) throw new Error('后台结算槽位名称无效');
            config.settlementFunctionType = input.settlementFunctionType;
            settlementCheckedAt = 0;
        }
        if (input.settlementThinkingMode !== undefined) {
            if (!['auto', 'off', 'on'].includes(input.settlementThinkingMode)) throw new Error('settlementThinkingMode须为auto/off/on');
            config.settlementThinkingMode = input.settlementThinkingMode;
            config.settlementThinking = input.settlementThinkingMode === 'on';
        } else if (input.settlementThinking !== undefined) {
            if (typeof input.settlementThinking !== 'boolean') throw new Error('settlementThinking须为布尔值');
            config.settlementThinking = input.settlementThinking;
            config.settlementThinkingMode = input.settlementThinking ? 'on' : 'off';
        }
        if (input.maxTurnsPerSession !== undefined) {
            const n = Number(input.maxTurnsPerSession);
            if (!Number.isInteger(n) || n < 2 || n > 30) throw new Error('maxTurnsPerSession须为2～30之间的整数');
            config.maxTurnsPerSession = n;
        }
        if (input.resetSession === true) {
            await resetLiveSession(config, '玩家手动重建');
            config.chatId = ''; config.sceneSession = null;
        }
        await PluginConfig.flush(config);
        mutated = true;
    } else if (action !== 'status' && action !== 'ui_snapshot') {
        throw new Error('未知桥接操作');
    }

    if (wantCatalog) await fetchModelCatalog(forceCatalog).catch(() => {});
    try {
        const model = await resolveModel(config);
        await resolveSettlementModel(config, model).catch(() => {});
        if (mutated && lastError && /^故事专属主模型|^无法读取 Operit 功能模型|^故事功能未绑定/.test(lastError)) lastError = '';
    } catch (error) { lastError = String(error.message || error); }
    if (mutated && !input._fromMonitor) void monitor();

    const settleThinkMode = effectiveSettlementThinkingMode(config);
    return { running, enabled: config.enabled, busy: busy !== null, model: modelInfo,
        version: PLUGIN_VERSION, controlSupported, sessionReady,
        functionType: config.functionType || 'CHAT',
        primaryModelMode: config.primaryModelMode === 'fixed' ? 'fixed' : 'slot',
        primaryProviderId: config.primaryProviderId || '',
        primaryModelId: config.primaryModelId || '',
        dualStage: config.dualStageEnabled !== false,
        settlementFunctionType: config.settlementFunctionType || 'SUMMARY',
        settlementThinking: settleThinkMode === 'on',
        settlementThinkingMode: settleThinkMode,
        settlementModel: settlementModelInfo, settlementFallback: !!settlementFallback,
        maxTurnsPerSession: liveMaxTurns(config),
        pendingResult: config.outbox !== null, lastError,
        mode: 'operit_session', workspacePath: config.workspacePath, endpoint: config.endpoint,
        liveSession: liveSessionView(config),
        chatId: config.chatId, participantId: config.participantId,
        inFlight: config.inFlight && { request_id: config.inFlight.request_id },
        ...(wantCatalog ? { availableModels: modelCatalogCache.models, functionBindings: modelCatalogCache.bindings } : {}) };
}

async function restore() {
    startMonitor();
    if ((await settings()).enabled) arm();
}

function terminate() {
    if (monitorTimer !== null) clearInterval(monitorTimer);
    monitorTimer = null;
    running = false;
    cancelWaitSleep();
    if (timer !== null) clearInterval(timer);
    timer = null;
    for (const id of heartbeats) clearInterval(id);
    heartbeats.clear();
}

function controlMessage(value) {
    const state = value.lastError ? '桥接需要处理：' + value.lastError : value.running
        ? '故事桥接已启动。回故事页选择行动；请保持Operit小窗可见。'
        : '故事桥接已暂停，已领取的行动会完成一次。';
    const primarySource = value.primaryModelMode === 'fixed' ? '专属固定' : '功能槽 ' + (value.functionType || 'CHAT');
    const modeLine = '\n生成模式：' + (value.dualStage !== false ? '双阶段流式(v2)' : '单阶段精简(v2)');
    const thinkMode = ['auto', 'off', 'on'].includes(value.settlementThinkingMode)
        ? value.settlementThinkingMode : (value.settlementThinking ? 'on' : 'auto');
    const thinkLabel = thinkMode === 'auto' ? '·智能思考' : thinkMode === 'on' ? '·深度思考' : '·非思考';
    const settleLine = value.dualStage !== false
        ? '\n后台结算(' + (value.settlementFunctionType || 'SUMMARY') + thinkLabel + ')：'
            + (value.settlementModel ? value.settlementModel.model_id + ' · ' + value.settlementModel.provider_name : '未绑定')
            + (value.settlementFallback ? '（未绑定，自动回退主功能槽）' : '')
        : '';
    return (value.liveSession && !value.liveSession.chat_id ? '正式会话将在下次行动建立。\n' : '')
        + state
        + (value.model ? '\n主模型(' + primarySource + ')：' + value.model.model_id + ' · ' + value.model.provider_name : '')
        + modeLine + settleLine;
}

async function bridgeCommand(event) {
    const args = event.eventPayload.args || [];
    const action = args[0] || 'status';
    if (action === 'session') {
        if (args.length !== 2 || !['continuous', 'service_restart', 'per_action'].includes(args[1])) return { stdout: '用法：/storybridge session continuous | service_restart | per_action' };
        const state = await receive({ action: 'session_policy', sessionPolicy: args[1] }); return { stdout: '已更新会话方式，下一次行动生效。', json: state };
    }
    if (action === 'mode') {
        if (args.length !== 2 || !['dual', 'single'].includes(args[1])) return { stdout: '用法：/storybridge mode dual | single' };
        const state = await receive({ action: 'dual_stage', dualStage: args[1] === 'dual' });
        return { stdout: '已切换为' + (args[1] === 'dual' ? '双阶段流式(v2)' : '单阶段精简(v2)') + '，下一次行动生效。', json: state };
    }
    if (action === 'settlement') {
        if (args.length !== 2 || !/^[A-Z][A-Z0-9_]{0,63}$/.test(args[1])) return { stdout: '用法：/storybridge settlement SUMMARY（或其它Operit功能槽名）' };
        const state = await receive({ action: 'settlement_slot', settlementFunctionType: args[1] });
        return { stdout: '已将后台结算槽位设为 ' + args[1] + '。\n' + controlMessage(state), json: state };
    }
    if (action === 'thinking') {
        if (args.length !== 2 || !['auto', 'off', 'on'].includes(args[1])) return { stdout: '用法：/storybridge thinking auto | off | on' };
        const state = await receive({ action: 'settlement_thinking', settlementThinkingMode: args[1] });
        return { stdout: '已更新副模型思考模式为 ' + args[1] + '。\n' + controlMessage(state), json: state };
    }
    if (action === 'max-turns') {
        const n = Number(args[1]);
        if (args.length !== 2 || !Number.isInteger(n) || n < 2 || n > 30) return { stdout: '用法：/storybridge max-turns <2～30>' };
        const state = await receive({ action: 'max_turns', maxTurnsPerSession: n });
        return { stdout: '已将同场景防漂移切窗轮数设为 ' + n + ' 轮。', json: state };
    }
    if (args.length > 1 || !['start', 'stop', 'status', 'reset-session'].includes(action)) {
        return { stdout: '用法：/storybridge start | stop | status | reset-session | session <方式> | mode <dual|single> | settlement <槽位> | thinking <auto|off|on> | max-turns <2-30>' };
    }
    const state = await receive({ action: action === 'reset-session' ? 'reset_session' : action });
    return { stdout: controlMessage(state), json: state };
}

async function bridgeInput(event) {
    if (event.eventName !== 'submit_requested') return { action: 'Allow' };
    const input = event.eventPayload;
    if (input.attachments && input.attachments.length || input.replyToMessageTimestamp != null) return { action: 'Allow' };
    const text = String(input.text || '').trim().replace(/[。！!]+$/, '');
    const actions = { '启动故事桥接': 'start', '开启故事桥接': 'start', '启用故事桥接': 'start',
        '启动故事桥接服务': 'start', '开启故事桥接服务': 'start', '启用故事桥接服务': 'start',
        '故事桥接服务开启': 'start', '停止故事桥接': 'stop', '暂停故事桥接': 'stop',
        '查看故事桥接状态': 'status', '查询故事桥接状态': 'status', '重建故事会话': 'reset_session' };
    if (!Object.prototype.hasOwnProperty.call(actions, text)) return { action: 'Allow' };
    try {
        const state = await receive({ action: actions[text] });
        return { action: 'Consume', message: controlMessage(state), clearInput: true };
    } catch (error) {
        return { action: 'Block', message: '桥接未启动：' + String(error.message || error) + '。请检查本地服务与工作区配置。' };
    }
}

ToolPkg.ipc.on(CHANNEL, receive);

function registerToolPkg() {
    const settingsScreen = typeof require === 'function' ? require('./ui/settings.ui.js').default : 'ui/settings.ui.js';
    if (typeof ToolPkg.registerUiRoute === 'function') {
        ToolPkg.registerUiRoute({
            id: 'settings',
            route: SETTINGS_ROUTE,
            runtime: 'compose_dsl',
            screen: settingsScreen,
            keepAlive: true,
            title: { zh: '故事桥接设置', en: 'Story Bridge Settings' }
        });
    }
    if (typeof ToolPkg.registerNavigationEntry === 'function') {
        ToolPkg.registerNavigationEntry({
            id: 'story_bridge_sidebar',
            route: SETTINGS_ROUTE,
            surface: 'main_sidebar_plugins',
            title: { zh: '故事桥接', en: 'Story Bridge' },
            icon: 'Tune',
            order: 160
        });
        ToolPkg.registerNavigationEntry({
            id: 'story_bridge_toolbox',
            route: SETTINGS_ROUTE,
            surface: 'toolbox',
            title: { zh: '故事桥接设置', en: 'Story Bridge Settings' },
            icon: 'Tune',
            order: 160
        });
    }
    ToolPkg.registerCoreCommand({ id: 'story_bridge_control', name: 'storybridge', title: '故事桥接',
        description: '启动、暂停或检查故事桥接，不经过模型生成。',
        usage: '/storybridge start | stop | status | reset-session | session <continuous|service_restart|per_action> | mode <dual|single> | settlement <SUMMARY> | thinking <auto|off|on> | max-turns <2-30>', function: bridgeCommand });
    ToolPkg.registerChatInputHook({ id: 'story_bridge_control_input', function: bridgeInput });
    ToolPkg.registerAppLifecycleHook({ id: 'story_create', event: 'application_on_create', function: restore });
    ToolPkg.registerAppLifecycleHook({ id: 'story_foreground', event: 'application_on_foreground', function: restore });
    ToolPkg.registerAppLifecycleHook({ id: 'story_terminate', event: 'application_on_terminate', function: terminate });
    return true;
}
exports.bridgeCommand = bridgeCommand;
exports.bridgeInput = bridgeInput;
exports.receive = receive;
exports.restore = restore;
exports.terminate = terminate;
exports.registerToolPkg = registerToolPkg;
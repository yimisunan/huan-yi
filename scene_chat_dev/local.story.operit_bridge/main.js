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
const PLUGIN_VERSION = '1.9.5';
let heartbeats = new Set();
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

function roleChanges(model, scene = false) {
    if (scene === 'live') return { ...roleChanges(model, true),
        toolAccessConfig:{enabled:true,allowedBuiltinTools:LIVE_READ_TOOLS,allowedPackages:[],allowedSkills:[],allowedMcpServers:[]}, name: '同席互动·项目只读',
        characterSetting: '你是正式互动故事生成者。entry_mode=live_interaction时，material_delivery=program_inline_v1表示material与required_sources已由程序从冻结源完整读取并直接交付；完整理解正文，不为证明读取而逐段重读packet，也不声称执行了未发生的工具读取。没有该标记时按packet.read_ranges读取。确需旧史时，只补查本任务许可路径与精确范围。依据设定、正式存档和玩家意图推演连贯剧情，在需要玩家新决定处停下。只交本次output_contract要求的裸JSON；保留主权、知情边界和角色主体性；对白只归实际在场人物，玩家台词不得代写；费用与数值由程序结算。不写文件、不执行命令。',
        otherContentChat: '遵循本次output_contract；正式传输中operation无操作时明确写空字符串两个双引号，不省略值，桥接在合法解析后转换为内部null。resolution.task、resolution.sleep.start及conditions.npc无内容写空字符串，不得省略值；有任务/时间则写合法对象。conditions依本次resolution_policy：普通付费必须七字段完整对象，无NPC仅npc为空；免费SYSTEM才无条件。严格区分玩家私有状态与角色共同知情。正文与登记操作一致；未支持操作写待处理，不宣称完成。' };
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

async function ensureSession(config, model, scene = false, persist = () => PluginConfig.flush(config)) {
    if (!config.workspacePath) throw new Error('故事会话尚未绑定项目工作区，请先配置workspacePath');
    if (config.chatId) {
        const existing = await Tools.Chat.listChats({ chat_ids: [config.chatId] });
        if (!Array.isArray(existing.chats)) throw new Error('无法核验故事专用会话');
        if (!existing.chats.some(chat => chat.id === config.chatId)) {
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
        const expected = roleChanges(model, scene);
        if (card.characterSetting !== expected.characterSetting || card.otherContentChat !== expected.otherContentChat || card.chatModelBindingMode !== 'FIXED_MODEL' || card.chatProviderId !== expected.chatProviderId || card.chatModelId !== expected.chatModelId ||
                JSON.stringify(card.toolAccessConfig) !== JSON.stringify(expected.toolAccessConfig)) {
            if (config.chatId && !(await Tools.Chat.agentStatus(config.chatId)).isIdle) throw new Error('专用会话仍在运行，不能更新模型或权限');
            card = await ToolPkg.callDependency('com.operit.character_cards', 'character.update', { id: config.participantId, changes: expected });
        }
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
    const bound = await Tools.SoftwareSettings.exec(['workspace', 'bind', config.chatId, config.workspacePath]);
    if (bound && bound.success === false) throw new Error(bound.error || '工作区绑定失败');
    const binding = await ToolPkg.callDependency('com.operit.character_cards', 'chat.configuration.binding.read', { chatId: config.chatId });
    if (binding.selection !== 'card:' + config.participantId) throw new Error('专用会话参与者绑定已改变');
    if (!(await Tools.Chat.agentStatus(config.chatId)).isIdle) throw new Error('故事专用会话忙碌，未重复提交');
    sessionReady = true;
    return { chatId: config.chatId, participantId: config.participantId };
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

function liveSessionView(config) {
    const state=config.liveSession || {};
    return {policy:liveSessionPolicy(config),chat_id:state.chatId || '',generation:state.generation || 0,reset_reason:state.resetReason || ''};
}

async function resetLiveSession(config, reason) {
    const state=config.liveSession || {};
    if (config.inFlight || config.outbox || state.chatId && !(await Tools.Chat.agentStatus(state.chatId)).isIdle) throw new Error('请等待当前生成和提交结束后重建会话');
    config.liveSession={...state,chatId:'',observedChars:0,generation:(state.generation || 0)+1,resetReason:reason};
    await PluginConfig.flush(config);
}

async function liveSession(config, model, task) {
    const identity=JSON.stringify([config.workspacePath,task.save_epoch,model.key,'live-program-inline-v1']);
    const policy=liveSessionPolicy(config);let state=config.liveSession;
    const reason=!state ? '首次连接' : state.identity!==identity ? '存档、工作区或模型变更'
        : policy==='service_restart' && state.serviceEpoch!==task.service_epoch ? 'Python服务已重启'
        : policy==='per_action' && state.lastRequestId!==task.request_id ? '按行动新建' : '';
    if (reason) {
        if (state && state.chatId && !(await Tools.Chat.agentStatus(state.chatId)).isIdle) throw new Error('旧正式会话尚未结束，不能切换');
        state={identity,chatId:'',participantId:state ? state.participantId : '',observedChars:0,
            generation:((state && state.generation) || 0)+1,resetReason:reason};
        config.liveSession=state;await PluginConfig.flush(config);
    }
    state.serviceEpoch=task.service_epoch;state.lastRequestId=task.request_id;
    const child={workspacePath:config.workspacePath,chatId:state.chatId,participantId:state.participantId};
    const persist=async()=>{state.chatId=child.chatId;state.participantId=child.participantId;config.liveSession={...state};await PluginConfig.flush(config);};
    const session=await ensureSession(child,model,'live',persist);await persist();return session;
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

function sessionText(task, previousError) {
    const turns = generationTurns(task, previousError);
    return turns.map(turn => turn.content).join('\n\n');
}

async function executeSession(config, task, model, session) {
    if (task.reading_preflight !== 1 || task.entry_mode === 'live_interaction' &&
            (task.live_reading_revision !== 2 || task.action_contract_revision !== 1 || task.material_delivery_revision !== 1)) {
        throw new Error('请重启Pydroid3服务并重试原行动，以加载程序资料交付接口');
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
            if (task.material_delivery_revision !== 1) throw new Error('请重启Pydroid3服务以加载程序资料交付接口');
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
            const turns = inline
                ? [{kind: 'user', content: text}]
                : generationTurns(task, previous);
            const textForCall = turns.map(turn => turn.content).join('\n\n');
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
    if (!config.outbox) config.outbox = { request_id: flight.request_id, model_key: flight.model_key, entry_mode: flight.entry_mode,
        body: { lease: flight.lease, error: 'Operit在正式会话执行中重启，未自动重复生成；原行动已保留，请显式重试。' } };
    config.inFlight = null;
    await PluginConfig.flush(config);
    await restoreChat(flight.chat_id, flight.return_chat_id).catch(() => {});
}

let modelInfo = null, modelDetails = null, modelCheckedAt = 0;

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

async function resolveModel(config) {
    const binding = cliObject(await Tools.SoftwareSettings.exec(['model', 'function-show', config.functionType, '--json']));
    if (!binding.providerId || !binding.modelId) throw new Error('故事功能未绑定模型');
    const key = JSON.stringify([config.functionType, binding.providerId, binding.modelId]);
    if (!modelInfo || modelInfo.key !== key || Date.now() - modelCheckedAt > 30000) {
        const details = cliObject(await Tools.SoftwareSettings.exec(['model', 'show', binding.providerId, binding.modelId, '--json']));
        if (details.providerId !== binding.providerId || details.modelId !== binding.modelId) throw new Error('模型配置已改变，请稍后重试');
        modelDetails = { provider_name: details.providerName || binding.providerId,
            pricing_configured: details.pricing != null };
        modelCheckedAt = Date.now();
    }
    modelInfo = { key, function_type: config.functionType, provider_id: binding.providerId,
        model_id: binding.modelId, ...modelDetails };
    return modelInfo;
}

async function checkModel(config, key) {
    if (key && (await resolveModel(config)).key !== key) throw new Error('生成模型已变更，请确认当前模型后重试。');
}

function settings() {
    if (!settingsPromise) settingsPromise = PluginConfig.use('story_bridge', {
        enabled: false, endpoint: 'http://127.0.0.1:5000', functionType: 'CHAT', outbox: null, lastRejection: null,
        workspacePath: '', chatId: '', participantId: '', inFlight: null, liveSessionPolicy:'continuous'
    });
    return settingsPromise;
}

async function http(path, body, token) {
    const config = await settings();
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (token) headers['X-Story-Bridge'] = token;
    const options = {
        url: config.endpoint + path, method: body === undefined ? 'GET' : 'POST',
        headers,
        connect_timeout: 8, read_timeout: 45, responseType: 'text', validateStatus: false,
        follow_redirects: false
    };
    if (body !== undefined) options.body = JSON.stringify(body);
    const result = await Tools.Net.http(options);
    const data = typeof result.content === 'string' ? JSON.parse(result.content) : result.content;
    if (result.statusCode < 200 || result.statusCode >= 300) {
        const error = new Error(data && data.error || '本地故事服务返回 ' + result.statusCode);
        error.statusCode = result.statusCode;
        throw error;
    }
    return data;
}

function pulse(key, lease, token, entry_mode) {
    let pending = false;
    const id = setInterval(async () => {
        if (pending) return;
        pending = true;
        try { await http(workerPath({request_id: key, entry_mode}, 'heartbeat'), { lease }, token); }
        catch (error) { lastError = String(error.message || error); }
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
    } catch (error) {
        // A 4xx response is authoritative rejection; transport/5xx keeps the exact saved output.
        if (!(error.statusCode >= 400 && error.statusCode < 500)) throw error;
        lastError = String(error.message || error);
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
        return;
    }
    const status = await http('/api/story/tasks');
    if (status.story_protocol !== 3 || status.reading_preflight !== 1) throw new Error('请在 Pydroid3 停止旧服务并重新运行语音运行.py，以加载正式会话读取接口（协议3）。');
    if (status.task && status.task.status === 'queued' && status.task.entry_mode === 'live_interaction'
            && (status.interaction_protocol !== 3 || status.live_reading_revision !== 2
                || status.action_contract_revision !== 1 || status.material_delivery_revision !== 1)) {
        throw new Error('请先重启Pydroid3服务以加载程序资料交付接口；旧任务须显式重试后再生成。');
    }
    await rememberRejection(config, status.task);
    const model = await resolveModel(config);
    lastError = '';
    let session;
    let response;
    if (status.task && status.task.status === 'queued') {
        if (status.task.entry_mode !== 'live_interaction') session = await ensureSession(config, model);
        response = await http('/api/story/worker/claim', { model }, token);
    } else {
        try { response = await http('/api/story/scene/worker/claim', { model }, token); }
        catch (error) { if (error.statusCode === 404) return; throw error; }
    }
    if (!response.task) {
        response = await http('/api/story/worker/claim', { model }, token);
        if (response.task && response.task.entry_mode !== 'live_interaction') session = await ensureSession(config, model);
    }
    if (!response.task) return;
    const task = response.task;
    const stop = pulse(task.request_id, task.lease, token, task.entry_mode);
    try {
        let body;
        try {
            await checkModel(config, model.key);
            if (task.entry_mode === 'scene_chat') session = await sceneSession(config, model, task);
            if (task.entry_mode === 'live_interaction') session = await liveSession(config, model, task);
            if (!session) throw new Error('未准备正式会话，任务未生成');
            body = await executeSession(config, task, model, session);
        } catch (error) {
            body = { lease: task.lease, error: String(error.message || error).slice(0, 500) };
        }
        config.outbox = { request_id: task.request_id, entry_mode: task.entry_mode, model_key: model.key, body };
        config.inFlight = null;
        await PluginConfig.flush(config);
        await repairMemory(config);
        await deliver(config, token);
    } finally { stop(); }
}

function tick() {
    if (busy) return busy;
    busy = work().then(() => {}, error => { lastError = String(error.message || error); })
        .finally(() => { busy = null; });
    return busy;
}

async function startBridge(config) {
    if (running) return;
    if (starting) return starting;
    starting = (async () => {
        const status = await http('/api/story/tasks');
        if (status.story_protocol !== 3 || status.reading_preflight !== 1) throw new Error('请重启Pydroid3本地服务以加载提交前读取校验，再启动桥接');
        const model = await resolveModel(config);
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
    return { phase: lastError ? 'error' : starting ? 'starting' : config.inFlight ? 'generating' : running ? 'ready' : 'paused',
        running, busy: !!busy || !!starting, last_error: lastError.slice(0, 500),
        plugin_version: PLUGIN_VERSION, model: modelInfo, session:liveSessionView(config) };
}

async function monitor() {
    if (monitorBusy) return;
    monitorBusy = true;
    try {
        const config = await settings();
        await resolveModel(config);
        const { token } = await http('/api/story/bridge-info');
        const response = await http('/api/story/worker/control', { runtime: runtimeReport(config),
            ack_id: config.controlAck || null, ack_error: config.controlError || '' }, token);
        controlSupported = true;
        if (response.command && response.command.id !== config.controlAck) {
            const command = response.command;
            let error = '';
            try { await receive({ action: command.action, sessionPolicy:command.session_policy }); }
            catch (failure) { error = String(failure.message || failure).slice(0, 500); lastError = error; }
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
    monitorTimer = setInterval(() => { void monitor(); }, 3000);
    void monitor();
}

function arm() {
    if (timer !== null) return;
    running = true;
    timer = setInterval(() => { if (running) void tick(); }, 3000);
    void tick();
}

async function receive(input = {}) {
    const config = await settings();
    startMonitor();
    if (input.action === 'start') {
        await startBridge(config);
    } else if (input.action === 'stop') {
        config.enabled = false;
        await PluginConfig.flush(config);
        running = false;
        if (timer !== null) clearInterval(timer);
        timer = null;
        if (!busy) lastError = '';
        // An already claimed round completes once; stopping prevents another claim.
    } else if (input.action === 'reset_session') {
        if (busy || starting) throw new Error('请等待当前行动结束后重建会话');
        await resetLiveSession(config,'玩家手动重建');
    } else if (input.action === 'session_policy') {
        if (busy || starting || config.inFlight || config.outbox) throw new Error('请等待当前行动结束后调整会话方式');
        if (!['continuous','service_restart','per_action'].includes(input.sessionPolicy)) throw new Error('会话方式无效');
        config.liveSessionPolicy=input.sessionPolicy;await PluginConfig.flush(config);
    } else if (input.action === 'configure') {
        if (running || busy || config.outbox || config.inFlight) throw new Error('请先停止桥接并等待当前任务结束');
        if (input.functionType !== undefined) {
            if (!/^[A-Z][A-Z0-9_]{0,63}$/.test(input.functionType)) throw new Error('功能模型名称无效');
            config.functionType = input.functionType;
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
            if (!['continuous','service_restart','per_action'].includes(input.sessionPolicy)) throw new Error('会话方式无效');
            config.liveSessionPolicy=input.sessionPolicy;
        }
        if (input.resetSession === true) {
            await resetLiveSession(config,'玩家手动重建');
            config.chatId='';config.sceneSession=null;
        }
        await PluginConfig.flush(config);
    } else if (input.action !== 'status') {
        throw new Error('未知桥接操作');
    }
    try { await resolveModel(config); } catch (error) { lastError = String(error.message || error); }
    return { running, enabled: config.enabled, busy: busy !== null, model: modelInfo,
        version: PLUGIN_VERSION, controlSupported, sessionReady,
        functionType: config.functionType, pendingResult: config.outbox !== null, lastError,
        mode: 'operit_session', workspacePath: config.workspacePath, endpoint: config.endpoint,
        liveSession:liveSessionView(config),
        chatId: config.chatId, participantId: config.participantId, inFlight: config.inFlight && { request_id: config.inFlight.request_id } };
}

async function restore() {
    startMonitor();
    if ((await settings()).enabled) arm();
}

function terminate() {
    if (monitorTimer !== null) clearInterval(monitorTimer);
    monitorTimer = null;
    running = false;
    if (timer !== null) clearInterval(timer);
    timer = null;
    for (const id of heartbeats) clearInterval(id);
    heartbeats.clear();
}

function controlMessage(value) {
    const state = value.lastError ? '桥接需要处理：' + value.lastError : value.running
        ? '故事桥接已启动。回故事页选择行动；请保持Operit小窗可见。'
        : '故事桥接已暂停，已领取的行动会完成一次。';
    return (value.liveSession && !value.liveSession.chat_id ? '正式会话将在下次行动建立。\n' : '') + state + (value.model ? '\n生成模型：' + value.model.model_id + ' · ' + value.model.provider_name : '');
}

async function bridgeCommand(event) {
    const args = event.eventPayload.args || [];
    const action = args[0] || 'status';
    if (action==='session') {
        if (args.length!==2 || !['continuous','service_restart','per_action'].includes(args[1])) return {stdout:'用法：/storybridge session continuous | service_restart | per_action'};
        const state=await receive({action:'session_policy',sessionPolicy:args[1]});return {stdout:'已更新会话方式，下一次行动生效。',json:state};
    }
    if (args.length > 1 || !['start','stop','status','reset-session'].includes(action)) return {stdout:'用法：/storybridge start | stop | status | reset-session | session <方式>'};
    const state = await receive({ action:action==='reset-session' ? 'reset_session' : action });
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
        '查看故事桥接状态': 'status', '查询故事桥接状态': 'status', '重建故事会话':'reset_session' };
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
    ToolPkg.registerCoreCommand({ id: 'story_bridge_control', name: 'storybridge', title: '故事桥接',
        description: '启动、暂停或检查故事桥接，不经过模型生成。',
        usage: '/storybridge start | stop | status | reset-session | session <continuous|service_restart|per_action>', function: bridgeCommand });
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
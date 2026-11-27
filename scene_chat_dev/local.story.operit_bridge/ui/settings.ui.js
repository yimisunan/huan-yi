"use strict";

const CHANNEL = 'story.bridge.control';
const THEATER_ROUTE = 'toolpkg:local.story.operit_bridge:ui:theater';

const SLOT_LABELS = {
    CHAT: 'CHAT（主聊天）',
    SUMMARY: 'SUMMARY（摘要总结 · 推荐）',
    TRANSLATION: 'TRANSLATION（翻译 · 适合专供副模型）',
    TITLE_GENERATION: 'TITLE_GENERATION（标题生成 · 适合专供副模型）',
    MEMORY: 'MEMORY（记忆整理）',
    GREP: 'GREP（快速检索）',
    ROLE_RESPONSE_PLANNER: 'ROLE_RESPONSE_PLANNER（角色规划）',
};

const BASE_SLOTS = ['SUMMARY', 'TRANSLATION', 'TITLE_GENERATION', 'MEMORY', 'GREP', 'ROLE_RESPONSE_PLANNER', 'CHAT'];
const TURN_PRESETS = [6, 10, 15, 20];

function slotTitle(slot) {
    return SLOT_LABELS[slot] || slot;
}

function modelPairKey(providerId, modelId) {
    return providerId && modelId ? providerId + '::' + modelId : '';
}

function parsePairKey(key) {
    const idx = String(key || '').indexOf('::');
    if (idx <= 0) return null;
    return { providerId: key.slice(0, idx), modelId: key.slice(idx + 2) };
}

function formatModelLabel(m) {
    if (!m || !m.model_id) return '未选择';
    return m.model_id + ' · ' + (m.provider_name || m.provider_id || '');
}

function findBinding(bindings, slot) {
    if (!Array.isArray(bindings)) return null;
    return bindings.find(item => item && item.function_type === slot) || null;
}

function slotOptionLabel(slot, bindings) {
    const binding = findBinding(bindings, slot);
    const boundText = binding && binding.model_id
        ? binding.model_id + ' (' + (binding.provider_name || binding.provider_id) + ')'
        : '未绑定';
    return slotTitle(slot) + ' → ' + boundText;
}

async function ipcCall(payload) {
    return await ToolPkg.ipc.call(CHANNEL, payload, { targetRuntime: 'main' });
}

function StoryBridgeSettingsScreen(ctx) {
    const UI = ctx.UI;
    const M = ctx.Modifier;
    const colors = ctx.MaterialTheme.colorScheme;

    const [state, setState] = ctx.useState('story-bridge-settings-state', {
        snapshot: null,
        loading: true,
        busy: false,
        error: '',
        notice: '',
        showAdvanced: false,
        workspaceDraft: '',
        endpointDraft: 'http://127.0.0.1:5000',
        primaryBindDraft: '',
        settlementBindDraft: '',
        draftSyncedSlot: '',
        primaryDraftSyncedSlot: '',
    });
    const live = ctx.useRef('story-bridge-settings-live', state);
    live.current = state;

    function update(patch) {
        const next = { ...live.current, ...patch };
        live.current = next;
        setState(next);
    }

    function applySnapshot(snap, extraPatch) {
        const bindings = Array.isArray(snap && snap.functionBindings) ? snap.functionBindings : [];
        const settleSlot = (snap && snap.settlementFunctionType) || 'SUMMARY';
        const primarySlot = 'CHAT';
        const settleBinding = findBinding(bindings, settleSlot);
        const primaryBinding = findBinding(bindings, primarySlot);
        const cur = live.current;
        const nextSettleDraft = (cur.draftSyncedSlot !== settleSlot || !cur.settlementBindDraft)
            ? (settleBinding ? modelPairKey(settleBinding.provider_id, settleBinding.model_id) : '')
            : cur.settlementBindDraft;
        const nextPrimaryDraft = (cur.primaryDraftSyncedSlot !== primarySlot || !cur.primaryBindDraft)
            ? (primaryBinding ? modelPairKey(primaryBinding.provider_id, primaryBinding.model_id) : '')
            : cur.primaryBindDraft;
        const prevSnap = cur.snapshot || {};
        const nextWs = (snap && snap.workspacePath) || '';
        const nextEp = (snap && snap.endpoint) || 'http://127.0.0.1:5000';
        const wsUntouched = !cur.workspaceDraft || cur.workspaceDraft === (prevSnap.workspacePath || '');
        const epUntouched = !cur.endpointDraft || cur.endpointDraft === (prevSnap.endpoint || 'http://127.0.0.1:5000');
        update({
            snapshot: snap,
            loading: false,
            workspaceDraft: (cur.showAdvanced && !wsUntouched) ? cur.workspaceDraft : nextWs,
            endpointDraft: (cur.showAdvanced && !epUntouched) ? cur.endpointDraft : nextEp,
            settlementBindDraft: nextSettleDraft,
            draftSyncedSlot: settleSlot,
            primaryBindDraft: nextPrimaryDraft,
            primaryDraftSyncedSlot: primarySlot,
            ...(extraPatch || {}),
        });
    }

    async function runAction(payload, successToast, syncBindDrafts) {
        if (live.current.busy) return;
        update({ busy: true, error: '', notice: '' });
        try {
            const snap = await ipcCall({ includeCatalog: true, ...payload });
            const extra = { busy: false, notice: successToast || '' };
            if (syncBindDrafts) {
                extra.draftSyncedSlot = '';
                extra.primaryDraftSyncedSlot = '';
            }
            applySnapshot(snap, extra);
            if (successToast && typeof ctx.showToast === 'function') {
                void ctx.showToast(successToast);
            }
        } catch (err) {
            const msg = String(err && err.message ? err.message : err);
            update({ busy: false, loading: false, error: msg });
            if (typeof ctx.showToast === 'function') void ctx.showToast(msg);
        }
    }

    async function load() {
        await runAction({ action: 'ui_snapshot', forceRefresh: true }, '', true);
    }

    const enabled = !state.busy;
    const snap = state.snapshot;
    const models = Array.isArray(snap && snap.availableModels) ? snap.availableModels : [];
    const bindings = Array.isArray(snap && snap.functionBindings) ? snap.functionBindings : [];

    function badge(label, tone) {
        const fg = tone === 'ok' ? colors.primary
            : tone === 'warn' ? colors.error
            : colors.onSurfaceVariant;
        const shape = { cornerRadius: 6 };
        const mod = M.clip(shape).background(fg.copy({ alpha: 0.12 })).border(1, fg.copy({ alpha: 0.32 }), shape);
        return UI.Box({ height: 22, paddingHorizontal: 8, contentAlignment: 'center', modifier: mod },
            UI.Text({ text: label, fontSize: 11, fontWeight: '600', color: fg, maxLines: 1 }));
    }

    function section(key, title, iconName, headerActions, children) {
        const shape = { cornerRadius: 16 };
        const items = [];
        for (let i = 0; i < children.length; i++) {
            if (i > 0) items.push(UI.Spacer({ height: 10 }));
            items.push(children[i]);
        }
        return UI.Box({ key, fillMaxWidth: true, paddingBottom: 12 },
            UI.Surface({
                fillMaxWidth: true,
                color: colors.surfaceContainer.copy({ alpha: 0.72 }),
                shape,
                modifier: M.border(1, colors.outlineVariant.copy({ alpha: 0.38 }), shape),
            }, UI.Column({ fillMaxWidth: true, padding: 14, spacing: 0 }, [
                UI.Row({ fillMaxWidth: true, verticalAlignment: 'center', spacing: 8 }, [
                    UI.Icon({ name: iconName, size: 20, tint: colors.primary }),
                    UI.Text({ text: title, fontSize: 15, fontWeight: '700', color: colors.onSurface, weight: 1, maxLines: 1 }),
                    ...headerActions,
                ]),
                UI.Spacer({ height: 10 }),
                ...items,
            ])));
    }

    function muted(text, key) {
        return UI.Text({ key, text, fontSize: 12, color: colors.onSurfaceVariant });
    }

    function dropdown(key, label, selectedText, options, onSelect) {
        if (!options.length) {
            return muted('当前未检测到已配置选项，请先在 Operit 模型配置中添加服务商与模型后点「刷新」。', key + '-empty');
        }
        return UI.Box({ key: key + '-box', fillMaxWidth: true, paddingTop: 2, paddingBottom: 2 },
            UI.DropdownMenu({
                key,
                label,
                text: selectedText,
                enabled,
                fillMaxWidth: true,
                onClick: index => {
                    if (enabled && options[index] !== undefined) onSelect(options[index]);
                },
            }, options.map((opt, idx) => UI.Text({ key: key + '-opt-' + idx, text: opt.label, paddingVertical: 8 }))));
    }

    function chipRow(key, selectedValue, options, onSelect) {
        return UI.FlowRow({ key, fillMaxWidth: true, spacing: 6, runSpacing: 6 },
            options.map(opt => UI.FilterChip({
                key: key + ':' + String(opt.value),
                selected: selectedValue === opt.value,
                enabled,
                label: UI.Text({ text: opt.label, fontSize: 12.5 }),
                onClick: () => { if (enabled) onSelect(opt.value); },
            })));
    }

    function textInput(key, label, value, onChange) {
        return UI.Box({ key: key + '-box', fillMaxWidth: true, paddingTop: 4, paddingBottom: 4 },
            UI.TextField({
                key,
                label,
                value,
                readOnly: !enabled,
                singleLine: true,
                style: { fontSize: 13.5 },
                decoration: {
                    filled: false,
                    isDense: true,
                    cornerRadius: 8,
                    borderColor: colors.outline,
                    focusedBorderColor: colors.primary,
                    contentPadding: { horizontal: 12, vertical: 12 },
                },
                onValueChange: v => { if (enabled) onChange(v); },
                fillMaxWidth: true,
            }));
    }

    const cards = [];

    if (!snap) {
        cards.push(section('loading-card', '故事桥接设置', 'Tune', [
            UI.TextButton({ key: 'retry-load', height: 32, text: '重试', enabled, onClick: load }),
        ], [
            state.loading
                ? UI.Row({ spacing: 10, verticalAlignment: 'center' }, [
                    UI.CircularProgressIndicator({}),
                    muted('正在读取桥接状态与 Operit 模型列表…'),
                ])
                : muted(state.error || '未能读取桥接状态，请点击右上角重试。'),
        ]));
    } else {
        const isRunning = !!snap.running;
        const isBusy = !!snap.busy || !!snap.inFlight;
        const hasErr = !!(state.error || snap.lastError);
        const statusLabel = hasErr ? '需处理' : isBusy ? '生成中' : isRunning ? '运行中' : '已暂停';
        const statusTone = hasErr ? 'warn' : isRunning ? 'ok' : 'idle';

        const primarySlot = 'CHAT';
        const dualStage = snap.dualStage !== false;
        const settleSlot = snap.settlementFunctionType || 'SUMMARY';
        const settleThinkingMode = ['auto', 'off', 'on'].includes(snap.settlementThinkingMode)
            ? snap.settlementThinkingMode
            : (snap.settlementThinking ? 'on' : 'auto');
        const settleThinkLabel = settleThinkingMode === 'auto' ? '智能思考'
            : settleThinkingMode === 'on' ? '深度思考' : '极速非思考';
        const sessionPolicy = (snap.liveSession && snap.liveSession.policy) || 'continuous';
        const maxTurns = Number(snap.maxTurnsPerSession || (snap.liveSession && snap.liveSession.max_turns) || 10);

        const primaryDesc = snap.model
            ? formatModelLabel(snap.model) + '（CHAT 槽 · 原生自托管）'
            : '未解析到主模型（请绑定 CHAT 槽）';
        const settleDesc = !dualStage
            ? '单阶段精简模式（仅主模型）'
            : (snap.settlementModel ? formatModelLabel(snap.settlementModel) : '未绑定')
                + '（' + settleSlot + ' · ' + settleThinkLabel
                + (snap.settlementFallback ? ' · 已自动回退' : '') + '）';
        const sess = snap.liveSession || {};
        const sessionDesc = (sess.chat_id ? '当前会话 ' + sess.chat_id.slice(0, 8) : '下次行动建立新会话')
            + ' · ' + (sess.turn_count || 0) + '/' + maxTurns + ' 轮'
            + (snap.workspacePath ? '' : ' · 未配置工作区路径');

        // Card 0: Status & Quick Controls
        const statusChildren = [
            UI.Text({ text: '主模型：' + primaryDesc, fontSize: 13, color: colors.onSurface }),
            UI.Text({ text: '副模型：' + settleDesc, fontSize: 13, color: colors.onSurface }),
            muted('会话与环境：' + sessionDesc + ' · 零角色卡依赖'),
        ];
        if (state.error || snap.lastError) {
            statusChildren.push(UI.Surface({
                fillMaxWidth: true,
                color: colors.errorContainer,
                shape: { cornerRadius: 10 },
            }, UI.Text({
                text: '提示：' + (state.error || snap.lastError),
                fontSize: 12,
                color: colors.onErrorContainer,
                padding: 10,
            })));
        } else if (state.notice) {
            statusChildren.push(UI.Surface({
                fillMaxWidth: true,
                color: colors.primaryContainer.copy({ alpha: 0.55 }),
                shape: { cornerRadius: 10 },
            }, UI.Text({
                text: state.notice,
                fontSize: 12,
                color: colors.onPrimaryContainer,
                padding: 10,
            })));
        }
        statusChildren.push(UI.FlowRow({ key: 'quick-actions', fillMaxWidth: true, spacing: 8, runSpacing: 6 }, [
            isRunning
                ? UI.OutlinedButton({ key: 'btn-stop', height: 36, enabled, onClick: () => runAction({ action: 'stop' }, '已暂停故事桥接') },
                    UI.Text({ text: '暂停桥接', fontSize: 13 }))
                : UI.Button({ key: 'btn-start', height: 36, text: '启动桥接', enabled, onClick: () => runAction({ action: 'start' }, '故事桥接已启动') }),
            UI.Button({
                key: 'btn-open-theater',
                height: 36,
                text: '打开内嵌剧场',
                enabled,
                onClick: () => {
                    if (typeof ctx.navigate === 'function') {
                        void ctx.navigate((snap && snap.theaterRoute) || THEATER_ROUTE);
                    }
                },
            }),
            UI.OutlinedButton({ key: 'btn-reset-session', height: 36, enabled, onClick: () => runAction({ action: 'reset_session' }, '已安排下次行动新建干净会话') },
                UI.Text({ text: '新建干净会话', fontSize: 13 })),
            UI.TextButton({ key: 'btn-refresh', height: 36, text: '刷新模型列表', enabled, onClick: () => runAction({ action: 'ui_snapshot', forceRefresh: true }, '已刷新模型与状态', true) }),
        ]));
        cards.push(section('status-card', '故事桥接 · v' + (snap.version || '2.3.3'), 'Tune', [badge(statusLabel, statusTone)], statusChildren));

        // Build option lists from live catalog
        const modelOptions = models.map(m => ({
            value: modelPairKey(m.provider_id, m.model_id),
            providerId: m.provider_id,
            modelId: m.model_id,
            label: formatModelLabel(m),
        }));
        const allSlotNames = Array.from(new Set([...BASE_SLOTS, ...bindings.map(b => b.function_type)]));

        // Card 1: Primary Model (Foreground Storytelling via Operit native CHAT slot)
        const curPrimaryBind = findBinding(bindings, primarySlot);
        const selectedPrimaryBindKey = state.primaryBindDraft || (curPrimaryBind ? modelPairKey(curPrimaryBind.provider_id, curPrimaryBind.model_id) : '');
        const selectedPrimaryBindOpt = modelOptions.find(o => o.value === selectedPrimaryBindKey);
        const primaryBindChanged = !!(selectedPrimaryBindOpt && (!curPrimaryBind || modelPairKey(curPrimaryBind.provider_id, curPrimaryBind.model_id) !== selectedPrimaryBindKey));
        const primaryChildren = [
            muted('原生自托管模式已彻底剥离角色卡依赖，前景演播默认跟随 Operit 的「CHAT」功能槽（也可在故事会话输入框菜单临时切换单聊模型）。主/副模型自定义系统提示词可在内嵌剧场「设置 → 阅读与体验」中随时编辑。'),
            UI.Surface({
                fillMaxWidth: true,
                color: colors.surfaceContainerHighest.copy({ alpha: 0.45 }),
                shape: { cornerRadius: 12 },
            }, UI.Column({ fillMaxWidth: true, padding: 10, spacing: 6 }, [
                UI.Text({ text: '直接切换「CHAT」主模型槽', fontSize: 13, fontWeight: '600', color: colors.onSurface }),
                muted('保存后会直接更新 Operit 全局 CHAT 功能槽绑定的模型，下一次行动立即生效并同步网页端。'),
                dropdown(
                    'primary-slot-bind-model',
                    '为 CHAT 槽选择主模型',
                    selectedPrimaryBindOpt ? selectedPrimaryBindOpt.label : (snap.model ? formatModelLabel(snap.model) : '请选择目标模型'),
                    modelOptions,
                    opt => update({ primaryBindDraft: opt.value })
                ),
                UI.Row({ fillMaxWidth: true, horizontalArrangement: 'end' }, [
                    UI.Button({
                        key: 'btn-bind-primary-slot',
                        height: 34,
                        text: '绑定到 CHAT 槽',
                        enabled: enabled && !!selectedPrimaryBindOpt,
                        onClick: () => {
                            const parsed = parsePairKey(selectedPrimaryBindKey);
                            if (!parsed) return;
                            void runAction({
                                action: 'bind_function_slot',
                                slot: primarySlot,
                                providerId: parsed.providerId,
                                modelId: parsed.modelId,
                            }, '已将 CHAT 槽主模型绑定为 ' + parsed.modelId, true);
                        },
                    }),
                ]),
                ...(primaryBindChanged ? [muted('待保存：点击上方按钮即可写入 Operit 的 CHAT 功能槽。')] : []),
            ])),
        ];
        cards.push(section('primary-model-card', '主模型 · 前景剧情演播', 'AutoAwesome', [], primaryChildren));

        // Card 2: Secondary / Settlement Model (Background Settlement)
        const settleChildren = [
            UI.Row({ fillMaxWidth: true, verticalAlignment: 'center', spacing: 12 }, [
                UI.Column({ weight: 1, spacing: 2 }, [
                    UI.Text({ text: '启用双阶段流式演播（推荐）', fontSize: 13.5, fontWeight: '600', color: colors.onSurface }),
                    muted('主模型逐句流式写剧情，副模型在后台静默结算数值、记忆与选项。'),
                ]),
                UI.Switch({
                    key: 'switch-dual-stage',
                    checked: dualStage,
                    enabled,
                    onCheckedChange: val => {
                        void runAction({ action: 'dual_stage', dualStage: !!val }, val ? '已开启双阶段流式演播' : '已切换为单阶段精简模式');
                    },
                }),
            ]),
        ];

        if (dualStage) {
            const settleSlotOptions = allSlotNames.map(slot => ({
                value: slot,
                label: slotOptionLabel(slot, bindings),
            }));
            settleChildren.push(UI.HorizontalDivider({ thickness: 1, color: colors.outlineVariant.copy({ alpha: 0.35 }) }));
            settleChildren.push(dropdown(
                'settlement-slot-select',
                '副模型使用的 Operit 功能槽',
                slotOptionLabel(settleSlot, bindings),
                settleSlotOptions,
                opt => {
                    void runAction({
                        action: 'settlement_slot',
                        settlementFunctionType: opt.value,
                    }, '后台结算槽位已切换为 ' + opt.value, true);
                }
            ));

            const curSettleBind = findBinding(bindings, settleSlot);
            const selectedSettleBindKey = state.settlementBindDraft || (curSettleBind ? modelPairKey(curSettleBind.provider_id, curSettleBind.model_id) : '');
            const selectedSettleBindOpt = modelOptions.find(o => o.value === selectedSettleBindKey);
            const settleBindChanged = !!(selectedSettleBindOpt && (!curSettleBind || modelPairKey(curSettleBind.provider_id, curSettleBind.model_id) !== selectedSettleBindKey));

            settleChildren.push(UI.Surface({
                fillMaxWidth: true,
                color: colors.surfaceContainerHighest.copy({ alpha: 0.45 }),
                shape: { cornerRadius: 12 },
            }, UI.Column({ fillMaxWidth: true, padding: 10, spacing: 6 }, [
                UI.Text({ text: '直接修改「' + settleSlot + '」槽绑定的模型', fontSize: 13, fontWeight: '600', color: colors.onSurface }),
                muted('保存后会直接更新 Operit 全局的 ' + settleSlot + ' 功能模型。建议绑定低价快速模型（如 Gemini 2.5 Flash / DeepSeek-V3.2）；若不想动默认摘要，可先在上方改选 TRANSLATION 或 TITLE_GENERATION。'),
                dropdown(
                    'settlement-slot-bind-model',
                    '为 ' + settleSlot + ' 槽选择新模型',
                    selectedSettleBindOpt ? selectedSettleBindOpt.label : '请选择目标模型',
                    modelOptions,
                    opt => update({ settlementBindDraft: opt.value })
                ),
                UI.Row({ fillMaxWidth: true, horizontalArrangement: 'end' }, [
                    UI.Button({
                        key: 'btn-bind-settlement-slot',
                        height: 34,
                        text: '绑定到 ' + settleSlot + ' 槽',
                        enabled: enabled && !!selectedSettleBindOpt,
                        onClick: () => {
                            const parsed = parsePairKey(selectedSettleBindKey);
                            if (!parsed) return;
                            void runAction({
                                action: 'bind_function_slot',
                                slot: settleSlot,
                                providerId: parsed.providerId,
                                modelId: parsed.modelId,
                                useAsSettlement: true,
                            }, '已将 ' + settleSlot + ' 槽绑定为 ' + parsed.modelId, true);
                        },
                    }),
                ]),
                ...(settleBindChanged ? [muted('待保存：点击上方按钮即可写入 Operit 的 ' + settleSlot + ' 功能槽。')] : []),
            ])));

            settleChildren.push(UI.Column({ fillMaxWidth: true, spacing: 6 }, [
                UI.Text({ text: '副模型思考策略', fontSize: 13.5, fontWeight: '600', color: colors.onSurface }),
                muted('推荐「智能自适应」：首轮免思考保极速，校验重试（第2～3次）自动开启思考纠错。注：Operit 2 接口仅提供思考开关，若需细调思考深度请在 Operit 模型参数页配置。'),
                chipRow('settlement-thinking-mode', settleThinkingMode, [
                    { value: 'auto', label: '智能自适应（推荐）' },
                    { value: 'off', label: '常关（极速）' },
                    { value: 'on', label: '常开（深度）' },
                ], val => {
                    const msg = val === 'auto'
                        ? '已设为智能自适应思考（重试自动升档）'
                        : val === 'on' ? '已设为副模型常开深度思考' : '已设为副模型常关非思考（最快）';
                    void runAction({
                        action: 'settlement_thinking',
                        settlementThinkingMode: val,
                        settlementThinking: val === 'on',
                    }, msg);
                }),
            ]));
        }
        cards.push(section('settlement-model-card', '副模型 · 后台结构化结算', 'Psychology', [], settleChildren));

        // Card 3: Session & Anti-Drift
        const sessionChildren = [
            UI.Text({ text: '剧情会话沿用策略', fontSize: 13, fontWeight: '600', color: colors.onSurface }),
            chipRow('session-policy', sessionPolicy, [
                { value: 'continuous', label: '持续沿用（推荐）' },
                { value: 'service_restart', label: '重启服务后新建' },
                { value: 'per_action', label: '每次行动新建' },
            ], val => {
                void runAction({ action: 'session_policy', sessionPolicy: val }, '会话策略已更新');
            }),
            UI.HorizontalDivider({ thickness: 1, color: colors.outlineVariant.copy({ alpha: 0.35 }) }),
            UI.Row({ fillMaxWidth: true, verticalAlignment: 'center', spacing: 8 }, [
                UI.Column({ weight: 1, spacing: 2 }, [
                    UI.Text({ text: '同场景防漂移自动切窗：每 ' + maxTurns + ' 轮', fontSize: 13, fontWeight: '600', color: colors.onSurface }),
                    muted('满轮数或切换场景/人物时自动开启干净新会话（默认 10 轮兼顾通用稳定；长上下文强模型可调至 15～18 轮提升前缀缓存复用，弱模型建议保持 8～10 轮）。'),
                ]),
                UI.OutlinedButton({
                    key: 'btn-turns-dec',
                    height: 32,
                    enabled: enabled && maxTurns > 2,
                    contentPadding: { horizontal: 10, vertical: 2 },
                    onClick: () => runAction({ action: 'max_turns', maxTurnsPerSession: Math.max(2, maxTurns - 1) }, '自动切窗轮数已设为 ' + Math.max(2, maxTurns - 1) + ' 轮'),
                }, UI.Text({ text: '-1', fontSize: 12.5 })),
                UI.OutlinedButton({
                    key: 'btn-turns-inc',
                    height: 32,
                    enabled: enabled && maxTurns < 30,
                    contentPadding: { horizontal: 10, vertical: 2 },
                    onClick: () => runAction({ action: 'max_turns', maxTurnsPerSession: Math.min(30, maxTurns + 1) }, '自动切窗轮数已设为 ' + Math.min(30, maxTurns + 1) + ' 轮'),
                }, UI.Text({ text: '+1', fontSize: 12.5 })),
            ]),
            chipRow('max-turns-presets', maxTurns, TURN_PRESETS.map(n => ({ value: n, label: n + ' 轮' })), n => {
                void runAction({ action: 'max_turns', maxTurnsPerSession: n }, '自动切窗轮数已设为 ' + n + ' 轮');
            }),
        ];
        cards.push(section('session-card', '会话与防漂移控制', 'History', [], sessionChildren));

        // Card 4: Advanced Connection Settings (Collapsible)
        const workspaces = Array.isArray(snap && snap.availableWorkspaces) ? snap.availableWorkspaces : [];
        const matchedWs = workspaces.find(ws => ws && (ws.id === snap.workspacePath || (Array.isArray(ws.folders) && ws.folders.some(f => f && f.path === snap.workspacePath))));
        const wsSummaryLabel = matchedWs
            ? (matchedWs.name + ' (' + matchedWs.id.slice(0, 8) + '…)')
            : (snap.workspacePath || '未设置');
        const sanitizeBoilerplate = snap.sanitizeOperitBoilerplate !== false;
        const advChildren = [];
        if (state.showAdvanced) {
            advChildren.push(UI.Row({ fillMaxWidth: true, verticalAlignment: 'center', spacing: 12 }, [
                UI.Column({ weight: 1, spacing: 2 }, [
                    UI.Text({ text: '净化 Operit 宿主样板（推荐）', fontSize: 13, fontWeight: '600', color: colors.onSurface }),
                    muted('仅对正式剧情会话剔除 AGENTS.md、文件同步与附件样板，保留只读旧档查询工具，大幅省量且不影响普通聊天。'),
                ]),
                UI.Switch({
                    key: 'switch-sanitize-boilerplate',
                    checked: sanitizeBoilerplate,
                    enabled,
                    onCheckedChange: val => {
                        void runAction({ action: 'sanitize_boilerplate', sanitizeOperitBoilerplate: !!val }, val ? '已开启宿主样板净化' : '已关闭宿主样板净化（恢复原样）');
                    },
                }),
            ]));
            advChildren.push(UI.HorizontalDivider({ thickness: 1, color: colors.outlineVariant.copy({ alpha: 0.35 }) }));
            advChildren.push(muted('新版 Operit 2 需绑定已创建的工作区 ID；直接点选下方已有工作区，或填入工作区 ID / 目录路径（自动匹配已有工作区）。'));
            if (workspaces.length > 0) {
                advChildren.push(UI.Text({ text: '快速选择 Operit 已有工作区', fontSize: 13, fontWeight: '600', color: colors.onSurface }));
                const wsOptions = workspaces.slice(0, 12).map(ws => {
                    const primary = ws.primary_path || (ws.folders && ws.folders[0] && ws.folders[0].path) || '';
                    const shortPath = primary ? (' · ' + primary.split('/').filter(Boolean).slice(-1)[0]) : '';
                    const label = (ws.name || ws.id.slice(0, 8)) + (shortPath && shortPath !== (' · ' + ws.name) ? shortPath : '');
                    return { value: ws.id, label: label.slice(0, 28) };
                });
                advChildren.push(chipRow('workspace-presets', matchedWs ? matchedWs.id : (state.workspaceDraft || ''), wsOptions, wsId => {
                    update({ workspaceDraft: wsId });
                    void runAction({
                        action: 'update_settings',
                        workspacePath: wsId,
                        endpoint: state.endpointDraft,
                    }, '已绑定工作区');
                }));
            }
            advChildren.push(textInput('input-workspace', '工作区 ID 或目录路径 (workspacePath)', state.workspaceDraft, v => update({ workspaceDraft: v })));
            advChildren.push(textInput('input-endpoint', '本地服务地址 (endpoint)', state.endpointDraft, v => update({ endpointDraft: v })));
            advChildren.push(UI.Row({ fillMaxWidth: true, horizontalArrangement: 'end' }, [
                UI.Button({
                    key: 'btn-save-advanced',
                    height: 36,
                    text: '保存高级配置',
                    enabled,
                    onClick: () => runAction({
                        action: 'update_settings',
                        workspacePath: state.workspaceDraft,
                        endpoint: state.endpointDraft,
                    }, '高级连接配置已保存'),
                }),
            ]));
        } else {
            advChildren.push(muted('工作区：' + wsSummaryLabel + '\n本地地址：' + (snap.endpoint || 'http://127.0.0.1:5000') + '\n宿主样板净化：' + (sanitizeBoilerplate ? '已开启' : '已关闭')));
        }
        cards.push(section('advanced-card', '高级连接配置', 'Settings', [
            UI.TextButton({
                key: 'btn-toggle-advanced',
                height: 32,
                text: state.showAdvanced ? '收起' : '展开编辑',
                enabled,
                onClick: () => update({ showAdvanced: !state.showAdvanced }),
            }),
        ], advChildren));
    }

    return UI.Box({ key: 'story-bridge-settings-root', fillMaxSize: true, onLoad: load }, [
        UI.Column({ fillMaxSize: true }, [
            UI.LazyColumn({
                key: 'story-bridge-settings-list',
                weight: 1,
                fillMaxWidth: true,
                paddingHorizontal: 14,
                paddingTop: 12,
                paddingBottom: 24,
            }, cards),
        ]),
    ]);
}

exports.default = StoryBridgeSettingsScreen;

"use strict";

const CHANNEL = 'story.bridge.control';
const SETTINGS_ROUTE = 'toolpkg:local.story.operit_bridge:ui:settings';
const DEFAULT_ENDPOINT = 'http://127.0.0.1:5000';

function normalizeEndpoint(raw) {
    const text = String(raw || '').trim().replace(/\/+$/, '');
    return /^https?:\/\/.+/.test(text) ? text : DEFAULT_ENDPOINT;
}

function formatWebError(err) {
    if (!err) return '无法连接到本地剧场服务';
    if (typeof err === 'string') return err;
    const desc = err.description || err.message || '';
    const code = err.errorCode !== undefined ? (' (code ' + err.errorCode + ')') : '';
    return (desc ? String(desc) : '无法连接到本地剧场服务') + code;
}

async function ipcCall(payload) {
    return await ToolPkg.ipc.call(CHANNEL, payload, { targetRuntime: 'main' });
}

function StoryTheaterScreen(ctx) {
    const UI = ctx.UI;
    const M = ctx.Modifier;
    const colors = ctx.MaterialTheme.colorScheme;

    const [state, setState] = ctx.useState('story-theater-webview-state', {
        endpoint: DEFAULT_ENDPOINT,
        ready: false,
        loading: true,
        progress: 0,
        error: '',
        reloadNonce: 0,
    });
    const live = ctx.useRef('story-theater-webview-live', state);
    live.current = state;

    function update(patch) {
        const next = { ...live.current, ...patch };
        live.current = next;
        setState(next);
    }

    async function loadEndpoint() {
        try {
            const snap = await ipcCall({ action: 'ui_snapshot', includeCatalog: false });
            const ep = normalizeEndpoint(snap && snap.endpoint);
            update({ endpoint: ep, ready: true, error: '' });
        } catch (_) {
            update({ endpoint: DEFAULT_ENDPOINT, ready: true });
        }
    }

    function reload() {
        update({
            error: '',
            loading: true,
            progress: 0,
            reloadNonce: (live.current.reloadNonce || 0) + 1,
        });
    }

    function openSettings() {
        if (typeof ctx.navigate === 'function') {
            void ctx.navigate(SETTINGS_ROUTE);
        }
    }

    const layers = [];

    if (state.ready && !state.error) {
        layers.push(UI.WebView({
            key: 'story-theater-webview-' + state.reloadNonce,
            fillMaxSize: true,
            url: state.endpoint,
            javaScriptEnabled: true,
            domStorageEnabled: true,
            databaseEnabled: true,
            allowFileAccess: true,
            allowContentAccess: true,
            supportZoom: false,
            useWideViewPort: true,
            loadWithOverviewMode: true,
            onPageStarted: () => update({ loading: true, error: '' }),
            onProgressChanged: p => {
                const pct = Number(p);
                update({ progress: Number.isFinite(pct) ? pct : 0, loading: pct < 100 });
            },
            onPageFinished: () => update({ loading: false, progress: 100 }),
            onReceivedError: err => update({ loading: false, error: formatWebError(err) }),
        }));
    }

    if (!state.ready || (state.loading && !state.error && state.progress < 95)) {
        layers.push(UI.Box({
            key: 'story-theater-loading-overlay',
            fillMaxSize: true,
            contentAlignment: 'topCenter',
            paddingTop: 12,
            paddingHorizontal: 16,
        }, UI.Surface({
            color: colors.surfaceContainerHigh.copy({ alpha: 0.92 }),
            shape: { cornerRadius: 999 },
            modifier: M.border(1, colors.outlineVariant.copy({ alpha: 0.45 }), { cornerRadius: 999 }),
        }, UI.Row({
            verticalAlignment: 'center',
            spacing: 8,
            paddingHorizontal: 14,
            paddingVertical: 8,
        }, [
            UI.CircularProgressIndicator({ size: 16, strokeWidth: 2 }),
            UI.Text({
                text: state.ready
                    ? ('正在载入深渊天平剧场' + (state.progress > 0 ? (' · ' + state.progress + '%') : '…'))
                    : '正在读取剧场地址…',
                fontSize: 12.5,
                color: colors.onSurface,
                maxLines: 1,
            }),
        ]))));
    }

    if (state.error) {
        const cardShape = { cornerRadius: 16 };
        layers.push(UI.Box({
            key: 'story-theater-error-overlay',
            fillMaxSize: true,
            contentAlignment: 'center',
            paddingHorizontal: 20,
        }, UI.Surface({
            fillMaxWidth: true,
            color: colors.surfaceContainer,
            shape: cardShape,
            modifier: M.border(1, colors.outlineVariant.copy({ alpha: 0.45 }), cardShape),
        }, UI.Column({ fillMaxWidth: true, padding: 18, spacing: 10 }, [
            UI.Row({ verticalAlignment: 'center', spacing: 8 }, [
                UI.Icon({ name: 'CloudOff', size: 22, tint: colors.error }),
                UI.Text({ text: '未能连接到本地剧场服务', fontSize: 15.5, fontWeight: '700', color: colors.onSurface }),
            ]),
            UI.Text({
                text: '当前目标地址：' + state.endpoint + '\n错误详情：' + state.error,
                fontSize: 12.5,
                color: colors.onSurfaceVariant,
            }),
            UI.Text({
                text: '请先在 Pydroid 3 / Termux 中运行「语音运行.py」启动本地服务，确认端口一致后点击下方重试。',
                fontSize: 12.5,
                color: colors.onSurfaceVariant,
            }),
            UI.Row({ fillMaxWidth: true, spacing: 8, horizontalArrangement: 'end' }, [
                UI.OutlinedButton({
                    key: 'btn-theater-settings',
                    height: 36,
                    onClick: openSettings,
                }, UI.Text({ text: '桥接设置', fontSize: 13 })),
                UI.Button({
                    key: 'btn-theater-retry',
                    height: 36,
                    text: '重新连接',
                    onClick: reload,
                }),
            ]),
        ]))));
    }

    return UI.Box({
        key: 'story-theater-root',
        fillMaxSize: true,
        onLoad: loadEndpoint,
    }, layers);
}

exports.default = StoryTheaterScreen;

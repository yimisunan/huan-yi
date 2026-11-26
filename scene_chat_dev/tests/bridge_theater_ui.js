'use strict';
/**
 * Compose DSL smoke test for ui/theater.ui.js (Operit 2 ComposeDslWebView embedded theater).
 */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');

const UI_PATH = path.join(__dirname, '../local.story.operit_bridge/ui/theater.ui.js');
const uiSource = fs.readFileSync(UI_PATH, 'utf8');

function findNode(tree, pred) {
    if (!tree || typeof tree !== 'object') return null;
    if (pred(tree)) return tree;
    const kids = Array.isArray(tree.children) ? tree.children : (tree.children ? [tree.children] : []);
    for (const k of kids) {
        const hit = findNode(k, pred);
        if (hit) return hit;
    }
    return null;
}

function makeTheaterHarness(ipcImpl) {
    const stateStore = new Map();
    const refStore = new Map();
    const navCalls = [];
    const colorStub = () => ({ copy: () => colorStub() });
    const modStub = {
        clip: () => modStub,
        background: () => modStub,
        border: () => modStub,
    };
    const UI = new Proxy({}, {
        get(_, type) {
            return (props, children) => ({ type: String(type), props: props || {}, children: children || [] });
        },
    });
    const ctx = {
        UI,
        Modifier: modStub,
        MaterialTheme: {
            colorScheme: new Proxy({}, { get: () => colorStub() }),
        },
        useState(key, init) {
            if (!stateStore.has(key)) stateStore.set(key, init);
            return [stateStore.get(key), val => stateStore.set(key, val)];
        },
        useRef(key, init) {
            if (!refStore.has(key)) refStore.set(key, { current: init });
            return refStore.get(key);
        },
        navigate(route) {
            navCalls.push(route);
        },
    };
    const box = {
        exports: {},
        console,
        ToolPkg: {
            ipc: { call: ipcImpl },
        },
    };
    vm.createContext(box);
    vm.runInContext(uiSource, box);
    const Screen = box.exports.default;
    return {
        render: () => Screen(ctx),
        navCalls,
    };
}

(async () => {
    const { render, navCalls } = makeTheaterHarness(async () => ({ endpoint: 'http://127.0.0.1:5055/' }));

    // 1. Initial load fetches endpoint and renders WebView.
    let tree = render();
    assert.strictEqual(typeof tree.props.onLoad, 'function');
    assert(findNode(tree, n => n.props && n.props.key === 'story-theater-loading-overlay'));
    await tree.props.onLoad();

    tree = render();
    const wv = findNode(tree, n => n.type === 'WebView');
    assert(wv, 'UI.WebView must render once endpoint loads');
    assert.strictEqual(wv.props.url, 'http://127.0.0.1:5055');
    assert.strictEqual(wv.props.javaScriptEnabled, true);
    assert.strictEqual(wv.props.domStorageEnabled, true);

    // 2. Page finish hides loading overlay cleanly for 100% fullscreen immersion.
    wv.props.onPageFinished();
    tree = render();
    assert.strictEqual(findNode(tree, n => n.props && n.props.key === 'story-theater-loading-overlay'), null);
    assert.strictEqual(findNode(tree, n => n.props && n.props.key === 'story-theater-error-overlay'), null);

    // 3. Connection error shows friendly fallback card with Settings jump + Retry button.
    wv.props.onReceivedError({ description: 'ERR_CONNECTION_REFUSED', errorCode: -6 });
    tree = render();
    const errOverlay = findNode(tree, n => n.props && n.props.key === 'story-theater-error-overlay');
    assert(errOverlay, 'error overlay must appear on connection failure');
    const settingsBtn = findNode(tree, n => n.props && n.props.key === 'btn-theater-settings');
    assert(settingsBtn, 'settings button must exist on error overlay');
    settingsBtn.props.onClick();
    assert.deepStrictEqual(navCalls, ['toolpkg:local.story.operit_bridge:ui:settings']);

    const retryBtn = findNode(tree, n => n.props && n.props.key === 'btn-theater-retry');
    assert(retryBtn, 'retry button must exist on error overlay');
    retryBtn.props.onClick();
    tree = render();
    const wv2 = findNode(tree, n => n.type === 'WebView');
    assert(wv2 && wv2.props.key === 'story-theater-webview-1', 'retry must remount WebView with incremented key');

    console.log('BRIDGE_THEATER_UI_OK WebView render, fullscreen completion, error fallback, settings jump & retry verified');
})().catch(err => {
    console.error(err);
    process.exitCode = 1;
});

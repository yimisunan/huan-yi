'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const KEY = 'abyss_official_live_v1';
  const PREF_KEY = 'abyss_ui_prefs_v1';
  const PEOPLE = ['沈知韫', '苏婉青', '徐念薇'];
  const LABELS = { A: '日常互动', B: '社交接触', C: '主动行为' };
  const COSTS = { A: 5, B: 10, C: 15 };
  const HUD_RING_C = 2 * Math.PI * 14;
  const BIG_RING_C = 2 * Math.PI * 52;
  const INNER_RING_C = 2 * Math.PI * 41;

  const CHAR_META = {
    '徐志北': { role: '主角 · 系统宿主', accent: '#d6b278', hasPortrait: true, fullbody: false },
    '沈知韫': { role: '集团董事长', accent: '#e5c388', hasPortrait: true, fullbody: true },
    '苏婉青': { role: '顶层公寓女主人', accent: '#e49c8d', hasPortrait: true, fullbody: true },
    '徐念薇': { role: '艺术学院在读', accent: '#9bc0d6', hasPortrait: true, fullbody: true },
    '徐承邺': { role: '徐家长子', accent: '#aba396', hasPortrait: false, fullbody: false }
  };

  const QUEST_TIERS = {
    small: '日常委托',
    medium: '进阶契约',
    large: '核心委托'
  };

  const QUEST_REWARDS = {
    small: '积分+15 · 经验+8 · 小道具×1',
    medium: '积分+40 · 经验+25 · 小道具×1',
    large: '积分+80 · 经验+50 · 小道具×1'
  };

  const SHOP_TIER_LABELS = {
    low: '低阶小物（≤10 积分）',
    mid: '中阶好物（11～50 积分）',
    high: '高阶臻品（≥100 积分）'
  };

  const MAP_COORDS = {
    '徐家主宅':       { x: 180, y: 46,  short: '徐家主宅' },
    '市中心顶层公寓': { x: 86,  y: 112, short: '顶层公寓' },
    '公司':           { x: 274, y: 112, short: '集团公司' },
    '大学':           { x: 112, y: 176, short: '艺术大学' },
    '工作室':         { x: 248, y: 176, short: '画室工坊' }
  };

  const SVG_NS = 'http://www.w3.org/2000/svg';

  let cache = { epoch: '', draft: '', pending: null, voice: true };
  let prefs = { theme: 'noir', font: 'normal', haptics: true, backdrop: true, cinemaPlates: true, readingDof: true, displayMode: 'curtain' };
  let snapshot = null, online = false, posting = false, polling = false, progressing = false;
  let storageOK = true, error = '', missing = false, mismatch = false;
  let portraitName = '', signature = '', worldSignature = '', lastSpeaker = '', backdropTarget = '';
  let desktopFocusName = '', topPeekOpen = false, gazeLensLocked = false, parallaxRaf = 0;
  let gazeHoldActive = false, gazeHoldCleanup = null;
  let history = [], hasOlder = false, olderCursor = null, resetRequest = null;
  let audioSerial = 0, audioMessage = null, audioStatus = '', isSpeaking = false;
  let gesture = false, configPromise = null, lastTap = 0;
  let activeHubTab = 'host', selectedChar = '', selectedMapPlace = '', historyFilter = 'all';
  let settlementFolded = true, settlementDismissedId = '', deckCollapsed = false, customComposerExpanded = false, lastUiMode = '';
  let activeStream = null, speakingMessageId = '', lastVectorLocation = '';
  let streamPreview = null, earlyStreamPreview = null, handoffPreview = null, sse = null, sseOpen = false, sseRetryTimer = null;
  let lastSseSeq = 0, sseRetryAttempt = 0;
  let fishKeyStatusPromise = null, fishKeyConfigured = null, fishMissingToastShown = false;
  let restoreTimer = null, restoreQueued = false, prefetchTimer = null, catchingUp = false;
  let curtainTrackedReqId = '', curtainHideTimer = null, backendPrefBusy = false;
  let bridgePrimaryTargetSig = '', bridgeSettleSlotSig = '', bridgeBindModelSig = '', bridgeBindSyncedKey = '';
  let shopCatalog = null, shopBusy = false, shopLoading = false, shopError = '';

  const BRIDGE_SLOT_LABELS = {
    CHAT: 'CHAT（主聊天）',
    SUMMARY: 'SUMMARY（摘要总结）',
    TRANSLATION: 'TRANSLATION（翻译）',
    TITLE_GENERATION: 'TITLE_GENERATION（标题生成）',
    MEMORY: 'MEMORY（记忆整理）',
    GREP: 'GREP（快速检索）',
    ROLE_RESPONSE_PLANNER: 'ROLE_RESPONSE_PLANNER（角色规划）',
  };
  const BRIDGE_BASE_SLOTS = ['SUMMARY', 'TRANSLATION', 'TITLE_GENERATION', 'MEMORY', 'GREP', 'ROLE_RESPONSE_PLANNER', 'CHAT'];
  const BRIDGE_PRIMARY_SLOTS = ['CHAT', 'SUMMARY', 'TRANSLATION', 'TITLE_GENERATION', 'MEMORY', 'GREP', 'ROLE_RESPONSE_PLANNER'];

  const urls = new VoiceClient.AudioUrlStore(8, 16 * 1024 * 1024);
  const audioCache = new Map();

  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '{}');
    if (typeof v.epoch === 'string') cache.epoch = v.epoch;
    if (typeof v.draft === 'string') cache.draft = v.draft;
    if (typeof v.voice === 'boolean') cache.voice = v.voice;
    if (v.pending && typeof v.pending.request_id === 'string'
        && typeof v.pending.action === 'string'
        && typeof v.pending.base_revision === 'string') {
      cache.pending = v.pending;
    }
  } catch (_) {
    storageOK = false;
  }

  try {
    const p = JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
    if (p.theme === 'noir' || p.theme === 'ivory') prefs.theme = p.theme;
    if (p.font === 'normal' || p.font === 'large') prefs.font = p.font;
    if (typeof p.haptics === 'boolean') prefs.haptics = p.haptics;
    if (typeof p.backdrop === 'boolean') prefs.backdrop = p.backdrop;
    if (typeof p.cinemaPlates === 'boolean') prefs.cinemaPlates = p.cinemaPlates;
    if (typeof p.readingDof === 'boolean') prefs.readingDof = p.readingDof;
    if (p.displayMode === 'curtain' || p.displayMode === 'stream') prefs.displayMode = p.displayMode;
  } catch (_) {}

  function reducedMotion() {
    return matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function applyPrefs() {
    document.documentElement.dataset.theme = prefs.theme;
    document.documentElement.dataset.font = prefs.font;
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) metaTheme.setAttribute('content', prefs.theme === 'ivory' ? '#f4efe6' : '#0c0a09');
    updateBackdrop();
    applyReadingFocus();
  }

  function savePrefs() {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch (_) {}
    applyPrefs();
  }

  function haptic(ms = 10) {
    if (!prefs.haptics || reducedMotion()) return;
    try { if (navigator.vibrate) navigator.vibrate(ms); } catch (_) {}
  }

  function toast(message) {
    const host = $('toastHost');
    if (!host || !message) return;
    while (host.children.length >= 2) host.firstElementChild.remove();
    const item = node('div', 'toast-item');
    item.append(icon('sparkle', 'chip-svg'), node('span', '', message));
    host.append(item);
    setTimeout(() => item.remove(), 2200);
  }

  function node(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function svgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  }

  function stripSubtextForTts(text) {
    return String(text || '').replace(/[｛{]([^｜|}\r\n]+)[｜|][^｝}\r\n]+[｝}]/g, '$1');
  }

  function stripVoiceTags(text) {
    return String(text || '')
      .replace(/[｛{]([^｜|}\r\n]+)[｜|][^｝}\r\n]+[｝}]/g, '$1')
      .replace(/\[[^\]\r\n]+\]/g, '')
      .replace(/<\/?(?:whisper|emphasis|soft|fast|slow|stress|forceful|chinese|english|japanese|korean|cantonese|french|german|spanish)>/gi, '')
      .replace(/<\|phoneme_start\|>[^<\r\n]{1,40}<\|phoneme_end\|>/g, '')
      .replace(/<\|[^|\r\n]+\|>/g, '')
      .trim();
  }

  function icon(name, cls = 'game-icon') {
    const svg = svgEl('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true', focusable: 'false' });
    svg.classList.add(...cls.split(' ').filter(Boolean));
    const paths = {
      energy:  'M13 2 4 14h7l-1 8 10-13h-7l1-7Z',
      coin:    'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v10m3-8c-1-2-6-2-6 1 0 3 6 1 6 4 0 3-5 3-6 1',
      heart:   'M12 20 3.8 11.8C1.2 9.1 3 4.6 6.8 4.6c2.1 0 3.8 1.1 5.2 2.9 1.4-1.8 3.1-2.9 5.2-2.9 3.8 0 5.6 4.5 3 7.2L12 20Z',
      moon:    'M20 14.5A8 8 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z',
      sun:     'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0-4v2m0 14v2M3 12h2m14 0h2m-3.4-6.6-1.4 1.4M7.8 16.2l-1.4 1.4m0-12.2 1.4 1.4m8.4 8.4 1.4 1.4',
      dawn:    'M4 17h16M7 17a5 5 0 0 1 10 0M12 6v3m-6.4 1.6 1.8 1.8m11-1.8-1.8 1.8',
      dusk:    'M3 16h18M7 16a5 5 0 0 1 10 0M6 20h12M12 7v3',
      check:   'M4 12.5 9.2 17.5 20 6.5',
      bag:     'M5 7.5h14l1.6 12.5a1.5 1.5 0 0 1-1.5 1.5H4.9a1.5 1.5 0 0 1-1.5-1.5L5 7.5Zm3.5 0V6a3.5 3.5 0 0 1 7 0v1.5',
      refund:  'M8 4 3 9l5 5M3 9h11a6 6 0 0 1 0 12',
      clock:   'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5.5l3.8 2.2',
      sparkle: 'M12 3 14.2 9.8 21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2L12 3Z',
      flame:   'M12 3c2.5 3.4 6 6.2 6 10.2a6 6 0 1 1-12 0c0-2.4 1.3-4.6 2.8-6.4.1 1.7 1.1 2.9 2.2 3.2C10.8 7.5 11.4 5 12 3Z',
      shield:  'M12 3 5 6v5.5c0 4.6 3 8 7 9.5 4-1.5 7-4.9 7-9.5V6l-7-3Z',
      map:     'M12 21s6-5.6 6-10.5a6 6 0 1 0-12 0C6 15.4 12 21 12 21Z',
      scroll:  'M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a3 3 0 0 1-3-3V6a2 2 0 0 1 2-2Zm3 4h6m-6 4h6m-6 4h4',
      gift:    'M4 10h16v10H4V10Zm-1-3h18v3H3V7Zm9 0v13m0-13c-1.5-3-5-3-5-1s3.5 1 5 1Zm0 0c1.5-3 5-3 5-1s-3.5 1-5 1Z',
      volume:  'M11 5 6 9H3v6h3l5 4V5Zm4.5 3.5a5 5 0 0 1 0 7',
      close:   'M6 6 18 18M18 6 6 18',
      scales:  'M12 4v15M8 19h8M5 9h14M5 9 3.5 14h3L5 9Zm14 0-1.5 5h3L19 9Z',
      shop:    'M4 9.5 5.5 4h13L20 9.5M4 9.5h16M4 9.5v1.5a2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0V9.5M6 14v6h12v-6'
    };
    const path = svgEl('path', {
      d: paths[name] || paths.check,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': '1.65',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round'
    });
    svg.append(path);
    return svg;
  }

  function renderSceneVector(location) {
    const loc = String(location || '');
    document.documentElement.dataset.location = loc;
    const host = $('sceneVectorLayer');
    if (!host || lastVectorLocation === loc) return;
    lastVectorLocation = loc;

    const svg = svgEl('svg', {
      viewBox: '0 0 400 800',
      preserveAspectRatio: 'xMidYMid slice',
      class: 'scene-vector-svg',
      'aria-hidden': 'true',
      focusable: 'false'
    });
    const stroke = { fill: 'none', stroke: 'currentColor', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };

    if (loc.includes('公寓')) {
      // Penthouse floor-to-ceiling rain-kissed glass & skyline horizon
      svg.append(
        svgEl('path', { ...stroke, 'stroke-width': '0.9', 'stroke-opacity': '0.35', d: 'M36 0v800M152 0v800M248 0v800M364 0v800M0 175h400M0 545h400' }),
        svgEl('path', { ...stroke, 'stroke-width': '0.8', 'stroke-opacity': '0.26', d: 'M0 510h42v-48h28v24h34v-72h26v96h38v-34h24v-66h34v100h30v-58h36v32h30v-80h32v106h46' }),
        svgEl('line', { ...stroke, 'stroke-width': '1.05', 'stroke-opacity': '0.52', class: 'rain-streak', x1: 78, y1: 60, x2: 72, y2: 148 }),
        svgEl('line', { ...stroke, 'stroke-width': '0.9', 'stroke-opacity': '0.42', class: 'rain-streak r2', x1: 196, y1: 30, x2: 190, y2: 112 }),
        svgEl('line', { ...stroke, 'stroke-width': '1.0', 'stroke-opacity': '0.48', class: 'rain-streak r3', x1: 312, y1: 90, x2: 306, y2: 178 }),
        svgEl('line', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.38', class: 'rain-streak r4', x1: 128, y1: 220, x2: 122, y2: 298 }),
        svgEl('line', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.36', class: 'rain-streak r2', x1: 274, y1: 260, x2: 268, y2: 344 }),
        svgEl('circle', { ...stroke, 'stroke-width': '0.8', 'stroke-opacity': '0.32', class: 'arch-shimmer', cx: 200, cy: 112, r: 44 })
      );
    } else if (loc.includes('主宅')) {
      // Neo-classical manor grand arches & chandelier silhouette
      svg.append(
        svgEl('path', { ...stroke, 'stroke-width': '1', 'stroke-opacity': '0.34', d: 'M46 800V240a154 154 0 0 1 308 0v560' }),
        svgEl('path', { ...stroke, 'stroke-width': '0.8', 'stroke-opacity': '0.24', d: 'M82 800V256a118 118 0 0 1 236 0v544M200 0v98M146 130h108' }),
        svgEl('path', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.38', class: 'arch-shimmer', d: 'M200 98c-24 18-50 24-72 24m72-24c24 18 50 24 72 24M162 122v18m38-42v48m38-24v18' }),
        svgEl('path', { fill: 'currentColor', 'fill-opacity': '0.28', class: 'arch-shimmer', d: 'M200 144 205 154 200 164 195 154ZM162 138 165 144 162 150 159 144ZM238 138 241 144 238 150 235 144Z' })
      );
    } else if (loc.includes('公司')) {
      // Executive tower glass curtain wall & crisp diagonal light shaft
      svg.append(
        svgEl('path', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.3', d: 'M50 0v800M100 0v800M200 0v800M300 0v800M350 0v800M0 140h400M0 320h400M0 500h400' }),
        svgEl('path', { ...stroke, 'stroke-width': '1.05', 'stroke-opacity': '0.4', class: 'arch-shimmer', d: 'M400 40 120 440M400 110 180 420M360 0 60 420' })
      );
    } else if (loc.includes('大学')) {
      // Academy classical colonnade arches & gallery sunlight
      svg.append(
        svgEl('path', { ...stroke, 'stroke-width': '0.95', 'stroke-opacity': '0.34', d: 'M18 800V240a56 56 0 0 1 112 0v560M144 800V240a56 56 0 0 1 112 0v560M270 800V240a56 56 0 0 1 112 0v560' }),
        svgEl('path', { ...stroke, 'stroke-width': '0.8', 'stroke-opacity': '0.24', d: 'M0 154h400M0 172h400' }),
        svgEl('circle', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.36', class: 'arch-shimmer', cx: 200, cy: 110, r: 34 })
      );
    } else if (loc.includes('工作室')) {
      // Atelier pitched skylight rafters & canvas geometric frame
      svg.append(
        svgEl('path', { ...stroke, 'stroke-width': '0.95', 'stroke-opacity': '0.34', d: 'M0 170 200 32 400 170M60 128 200 32M340 128 200 32M200 32v96' }),
        svgEl('rect', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.26', x: 76, y: 210, width: 248, height: 340, rx: 4 }),
        svgEl('path', { ...stroke, 'stroke-width': '0.9', 'stroke-opacity': '0.38', class: 'arch-shimmer', d: 'M200 128 112 310M200 128 288 310' })
      );
    } else {
      // Default Abyss Scales meridian arcs
      svg.append(
        svgEl('circle', { ...stroke, 'stroke-width': '0.85', 'stroke-opacity': '0.28', cx: 200, cy: 230, r: 140, 'stroke-dasharray': '4 8' }),
        svgEl('circle', { ...stroke, 'stroke-width': '0.8', 'stroke-opacity': '0.22', class: 'arch-shimmer', cx: 200, cy: 230, r: 92 }),
        svgEl('path', { ...stroke, 'stroke-width': '0.8', 'stroke-opacity': '0.24', d: 'M200 40v380M50 230h300' })
      );
    }
    host.replaceChildren(svg);
  }

  function spawnTapRipple(x, y) {
    if (reducedMotion()) return;
    const layer = $('tapRippleLayer');
    if (!layer) return;
    const svg = svgEl('svg', { viewBox: '0 0 80 80', class: 'tap-ripple' });
    svg.style.left = x + 'px';
    svg.style.top = y + 'px';
    svg.append(
      svgEl('circle', { cx: 40, cy: 40, r: 22, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.4', 'stroke-opacity': '0.9' }),
      svgEl('circle', { cx: 40, cy: 40, r: 10, fill: 'none', stroke: 'currentColor', 'stroke-width': '1', 'stroke-opacity': '0.55' }),
      svgEl('path', { d: 'M40 24 43 37 56 40 43 43 40 56 37 43 24 40 37 37Z', fill: 'currentColor', 'fill-opacity': '0.32' })
    );
    layer.append(svg);
    setTimeout(() => svg.remove(), 620);
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(cache));
      storageOK = true;
    } catch (_) {
      storageOK = false;
    }
    $('saveHint').textContent = storageOK
      ? (progression() ? '阅读与存档进度自动保存 · 点按演播不耗体力' : '阅读与存档进度自动保存')
      : '浏览器存储不可用，提交已暂停';
    return storageOK;
  }

  async function api(path, body) {
    return VoiceClient.requestJson('/api/story/' + path, {
      cache: 'no-store',
      ...(body === undefined ? {} : {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Story-Client': '1' },
        body: JSON.stringify(body)
      })
    }, 12000);
  }

  function queuedBridgeIssue(state) {
    if (state?.task?.status !== 'queued') return '';
    const b = state.bridge;
    const controlError = b?.control?.status === 'failed' ? b.control.error : '';
    if (b?.last_error || controlError) return '行动尚未开始 · 桥接错误：' + (b.last_error || controlError);
    if (!b?.present) return '行动尚未开始 · Operit 桥接未连接，请在 Operit 开启故事桥接；可取消退还。';
    if (b.phase === 'starting') return '行动尚未开始 · Operit 桥接正在启动……';
    if (!b.running || b.phase === 'paused') return '行动尚未开始 · Operit 桥接未启动或已暂停；可取消退还。';
    if (b.phase === 'error') return '行动尚未开始 · Operit 桥接运行异常，请查看连接详情。';
    return '';
  }

  const isCurtainMode = () => prefs.displayMode !== 'stream';
  const active = () => ['preparing', 'queued', 'generating', 'validating', 'refund_pending'].includes(snapshot?.task?.status);
  const hasPreview = () => !!(streamPreview && active() && streamPreview.request_id === snapshot?.task?.request_id);
  const hasPreviewNodes = () => !isCurtainMode() && hasPreview() && Array.isArray(streamPreview.messages) && streamPreview.messages.length > 0;
  const baseBlocked = () => posting || polling || progressing || catchingUp || !online || !storageOK || ![2, 3].includes(snapshot?.interaction_protocol) || !!cache.pending || active();
  const canDecide = () => !!snapshot?.playback?.segment_id && snapshot.playback.completed;
  const blocked = () => baseBlocked() || !canDecide();
  const current = () => history.find(t => t.id === snapshot?.playback?.segment_id);
  const progression = () => snapshot?.world?.progression;
  const resting = () => !!progression() && (progression().runtime.phase === 'resting' || (snapshot?.task?.reservation?.status !== 'held' && progression().stamina < 5));
  const pureRecovery = () => /^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test($('input').value);
  const afford = n => !progression() || progression().stamina >= n;
  const ordinaryBlocked = () => blocked() || resting();
  const canTransactDeterministic = () => online && !posting && !polling && !progressing && !catchingUp
    && !active() && !shopBusy && !cache.pending && !!snapshot?.revision
    && (!snapshot?.playback?.segment_id || snapshot.playback.completed);

  function transactBlockReason() {
    if (!online) return '未连接本地服务';
    if (shopBusy) return '正在处理…';
    if (posting || progressing || catchingUp || active() || cache.pending) return '当前有行动处理中';
    if (snapshot?.playback?.segment_id && !snapshot.playback.completed) return '请先演播完本段';
    return '';
  }

  function makeReqId(prefix) {
    return prefix + '-' + (crypto.randomUUID
      ? crypto.randomUUID()
      : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2));
  }

  async function loadShop(force = false) {
    if (shopLoading) return;
    if (!force && shopCatalog && shopCatalog.revision === snapshot?.revision && shopCatalog.save_epoch === cache.epoch) return;
    shopLoading = true;
    shopError = '';
    if ($('worldDialog')?.open && activeHubTab === 'shop') renderWorld(true);
    try {
      shopCatalog = await api('shop');
    } catch (e) {
      shopError = e.message || '商城目录加载失败';
    } finally {
      shopLoading = false;
      if ($('worldDialog')?.open && activeHubTab === 'shop') renderWorld(true);
    }
  }

  async function redeemShopItem(item) {
    if (!item || !canTransactDeterministic()) return;
    haptic(14);
    shopBusy = true;
    renderWorld(true);
    try {
      const res = await api('shop/redeem', {
        request_id: makeReqId('shop'),
        base_revision: snapshot.revision,
        save_epoch: cache.epoch,
        item_id: item.id
      });
      if (res?.snapshot) absorb(res.snapshot);
      else await restore();
      toast('已兑换「' + (res?.receipt?.item_name || item.name) + '」入囊（-' + (res?.receipt?.price ?? item.price) + ' 积分）');
      await loadShop(true);
    } catch (e) {
      toast(e.message || '兑换未完成，已刷新状态');
      await restore();
      await loadShop(true);
    } finally {
      shopBusy = false;
      renderWorld(true);
    }
  }

  async function claimTaskReward() {
    if (!canTransactDeterministic()) return;
    haptic(14);
    shopBusy = true;
    renderWorld(true);
    try {
      const res = await api('task/claim', {
        request_id: makeReqId('claim'),
        base_revision: snapshot.revision,
        save_epoch: cache.epoch
      });
      if (res?.snapshot) absorb(res.snapshot);
      else await restore();
      toast('已领取委托奖励「' + (res?.receipt?.item_name || '纪念小物') + '」入囊');
    } catch (e) {
      toast(e.message || '领取未完成，已刷新状态');
      await restore();
    } finally {
      shopBusy = false;
      renderWorld(true);
    }
  }

  function formatGameClock(clock, weekday = '') {
    if (!clock || !clock.day || !clock.time) return '';
    return '第' + clock.day + '天 · ' + (weekday ? (weekday + ' ') : '') + clock.time;
  }

  async function upgradePassiveSkill(target) {
    if (!target || !canTransactDeterministic()) return;
    haptic(14);
    shopBusy = true;
    renderWorld(true);
    try {
      const res = await api('passive/upgrade', {
        request_id: makeReqId('passive'),
        base_revision: snapshot.revision,
        save_epoch: cache.epoch,
        target
      });
      if (res?.snapshot) absorb(res.snapshot);
      else await restore();
      const rc = res?.receipt || {};
      toast('已对 ' + target + ' 解锁 ' + (rc.level_after || '') + '「' + (rc.skill_name || '定向被动') + '」（-' + (rc.cost_exp ?? '') + ' 经验）');
    } catch (e) {
      toast(e.message || '被动解锁未完成，已刷新状态');
      await restore();
    } finally {
      shopBusy = false;
      renderWorld(true);
    }
  }

  async function acquireIntel(intelId) {
    if (!intelId || !canTransactDeterministic()) return;
    haptic(14);
    shopBusy = true;
    renderWorld(true);
    try {
      const res = await api('intel/acquire', {
        request_id: makeReqId('intel'),
        base_revision: snapshot.revision,
        save_epoch: cache.epoch,
        intel_id: intelId
      });
      if (res?.snapshot) absorb(res.snapshot);
      else await restore();
      toast('已整理掌握商业情报「' + (res?.receipt?.intel_name || intelId) + '」');
    } catch (e) {
      toast(e.message || '情报入库未完成，已刷新状态');
      await restore();
    } finally {
      shopBusy = false;
      renderWorld(true);
    }
  }

  async function toggleBusinessLeverage(action, intelId = '') {
    if (!canTransactDeterministic()) return;
    haptic(14);
    shopBusy = true;
    renderWorld(true);
    try {
      const res = await api('intel/leverage', {
        request_id: makeReqId('lev'),
        base_revision: snapshot.revision,
        save_epoch: cache.epoch,
        action,
        intel_id: intelId || ''
      });
      if (res?.snapshot) absorb(res.snapshot);
      else await restore();
      if (action === 'arm') {
        toast('已预备商业杠杆「' + (res?.receipt?.intel_name || intelId) + '」（下次 C 烈度好感惩罚减半）');
      } else {
        toast('已取消商业杠杆预备');
      }
    } catch (e) {
      toast(e.message || '商业杠杆切换未完成，已刷新状态');
      await restore();
    } finally {
      shopBusy = false;
      renderWorld(true);
    }
  }

  function parsePanels(lines = []) {
    const result = {};
    for (const raw of lines || []) {
      const m = /^\[([^\]]+)\]\s*(.*)$/.exec(String(raw).trim());
      if (!m) continue;
      const key = m[1].trim();
      const stats = {};
      const ordered = [];
      for (const seg of m[2].split('|')) {
        const s = seg.trim();
        if (!s) continue;
        const idx = s.search(/\s+/);
        if (idx < 0) continue;
        const k = s.slice(0, idx).trim();
        const vRaw = s.slice(idx).trim();
        const numMatch = /^-?\d+(?:\.\d+)?/.exec(vRaw);
        const entry = {
          key: k,
          raw: vRaw,
          num: numMatch ? Number(numMatch[0]) : null,
          bool: vRaw === 'True' ? true : vRaw === 'False' ? false : null,
          isPercent: vRaw.endsWith('%'),
          isCount: vRaw.endsWith('次'),
          isLevel: vRaw.startsWith('Lv.')
        };
        stats[k] = entry;
        ordered.push(entry);
      }
      result[key] = { key, raw, stats, ordered };
    }
    return result;
  }

  function timeOfDay(timeStr) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(timeStr || ''));
    if (!m) return { phase: 'day', icon: 'sun' };
    const h = Number(m[1]);
    if (h >= 5 && h < 9) return { phase: 'dawn', icon: 'dawn' };
    if (h >= 9 && h < 17) return { phase: 'day', icon: 'sun' };
    if (h >= 17 && h < 20) return { phase: 'dusk', icon: 'dusk' };
    return { phase: 'night', icon: 'moon' };
  }

  const VISUAL_SLOT_LABELS = {
    fullbody: '外出立绘',
    fullbody2: '居家立绘',
    into: '近景特写',
    mood_blush: '微醺羞怯',
    mood_desire: '高欲沉溺',
    mood_sleep: '深夜余韵',
    mood_cold: '冷艳审视'
  };

  const VISUAL_SLOT_ORDER = ['fullbody', 'fullbody2', 'into', 'mood_blush', 'mood_desire', 'mood_sleep', 'mood_cold'];

  function image(name, file = 'into.png') {
    const slot = String(file || 'into.png').replace(/\.[a-z0-9]+$/i, '');
    const charSlots = snapshot?.world?.visual_assets?.characters?.[name];
    if (charSlots?.[slot]) return charSlots[slot];
    if (charSlots) {
      const any = Object.values(charSlots)[0];
      if (any) return any;
    }
    return '/txt文件/image/' + encodeURIComponent(name) + '/' + file;
  }

  function getVisualAssets() {
    return snapshot?.world?.visual_assets || { scenes: {}, characters: {} };
  }

  function hasCharacterPortrait(name) {
    if (!name) return false;
    const va = snapshot?.world?.visual_assets;
    if (va && va.characters) {
      const slots = va.characters[name];
      return Boolean(slots && Object.keys(slots).length > 0);
    }
    return Boolean(CHAR_META[name]?.hasPortrait);
  }

  function getCharacterSlots(name) {
    const va = getVisualAssets().characters?.[name];
    if (va && Object.keys(va).length > 0) return va;
    const meta = CHAR_META[name];
    if (!meta?.hasPortrait) return {};
    if (meta.fullbody) {
      return {
        fullbody: '/txt文件/image/' + encodeURIComponent(name) + '/fullbody.png',
        fullbody2: '/txt文件/image/' + encodeURIComponent(name) + '/fullbody2.png',
        into: '/txt文件/image/' + encodeURIComponent(name) + '/into.png'
      };
    }
    return { into: '/txt文件/image/' + encodeURIComponent(name) + '/into.png' };
  }

  function resolveSceneStill(location, timeStr = null) {
    const loc = String(location || '').trim();
    if (!loc) return null;
    const slots = getVisualAssets().scenes?.[loc];
    if (!slots || !Object.keys(slots).length) return null;
    const tStr = timeStr || snapshot?.world?.progression?.runtime?.clock?.time || '';
    const phase = timeOfDay(tStr).phase;
    const order = (phase === 'night' || phase === 'dusk')
      ? ['night', 'dusk', 'default', 'day', 'dawn']
      : ['day', 'dawn', 'default', 'night', 'dusk'];
    for (const k of order) {
      if (slots[k]) return { url: slots[k], slot: k, phase };
    }
    const firstKey = Object.keys(slots)[0];
    return firstKey ? { url: slots[firstKey], slot: firstKey, phase } : null;
  }

  function characterBuffList(w, name) {
    const buffs = w?.buffs;
    if (!buffs) return [];
    if (Array.isArray(buffs)) return buffs;
    if (name) return Array.isArray(buffs[name]) ? buffs[name] : [];
    return Object.values(buffs).flat().filter(Boolean);
  }

  function resolveCharacterAsset(name, opts = {}) {
    if (!hasCharacterPortrait(name)) return null;
    const slots = getCharacterSlots(name);
    const w = snapshot?.world;
    const pick = (slotKey, tagText) => slots[slotKey]
      ? {
          url: slots[slotKey],
          slot: slotKey,
          label: tagText || VISUAL_SLOT_LABELS[slotKey] || slotKey,
          pos: slotKey === 'into' || slotKey.startsWith('mood_') ? '50% 22%' : '50% 16%'
        }
      : null;

    if (opts.slot) {
      const cleanSlot = String(opts.slot).replace(/\.[a-z0-9]+$/i, '');
      const exact = pick(cleanSlot, VISUAL_SLOT_LABELS[cleanSlot]);
      if (exact) return exact;
    }

    const loc = opts.location || w?.location || '';
    const tStr = opts.time || w?.progression?.runtime?.clock?.time || '';
    const tod = timeOfDay(tStr).phase;
    const isHome = (name === '苏婉青' && loc === '市中心顶层公寓')
      || ((name === '沈知韫' || name === '徐念薇') && loc === '徐家主宅');
    const isNight = tod === 'night' || tod === 'dusk' || tod === 'dawn';

    if (opts.preferMood !== false && w && PEOPLE.includes(name)) {
      const panels = parsePanels(w.panels || []);
      const st = panels[name]?.stats || {};
      const micro = w.micro_states?.[name] || {};
      const desire = st['欲望']?.num ?? 0;
      const shame = st['羞耻']?.num ?? 100;
      const npcStam = st['体力']?.num ?? 100;
      const hasFluidLock = characterBuffList(w, name).some(b => String(b?.name || '').includes('体液锁定'));
      const vigRow = (w.vigilance?.targets || []).find(t => t.name === name);
      const highVig = (vigRow?.vigilance || 0) >= 50;

      if (npcStam < 15) {
        const hit = pick('mood_sleep', '深夜余韵');
        if (hit) return hit;
      }
      if (desire >= 70 || hasFluidLock || micro.residual_tension) {
        const hit = pick('mood_desire', '高欲沉溺');
        if (hit) return hit;
      }
      if (micro.momentary_ease || micro.confusion_debt || (shame >= 30 && shame <= 65)) {
        const hit = pick('mood_blush', '微醺羞怯');
        if (hit) return hit;
      }
      if (highVig) {
        const hit = pick('mood_cold', '冷艳审视');
        if (hit) return hit;
      }
    }

    if (opts.whisper) {
      return pick('mood_blush', '微距耳语') || pick('into', '近景特写') || pick('fullbody2', '居家立绘') || pick('fullbody', '外出立绘');
    }

    if (isHome) {
      const tag = isNight ? '居家立绘 · 夜间匹配' : '居家立绘';
      return pick('fullbody2', tag) || pick('into', '近景特写') || pick('fullbody', '外出立绘');
    }
    return pick('fullbody', '外出立绘') || pick('into', '近景特写') || pick('fullbody2', '居家立绘');
  }

  function deriveAtmosphereMood(w) {
    if (!w) return 'calm';
    const cast = w.cast || [];
    if (cast.includes('徐承邺')) return 'vigilance';
    const maxVig = Math.max(0, ...(w.vigilance?.targets || []).map(t => Number(t.vigilance) || 0));
    if (maxVig >= 50) return 'vigilance';
    const panels = parsePanels(w.panels || []);
    for (const name of cast) {
      if (!PEOPLE.includes(name)) continue;
      const st = panels[name]?.stats || {};
      const micro = w.micro_states?.[name] || {};
      const hasFluidLock = characterBuffList(w, name).some(b => String(b?.name || '').includes('体液锁定'));
      if ((st['欲望']?.num ?? 0) >= 65 || hasFluidLock || micro.momentary_ease || micro.residual_tension || micro.confusion_debt) {
        return 'intimate';
      }
    }
    return 'calm';
  }

  function initAmbientRain() {
    const box = $('ambientRain');
    if (!box || box.childElementCount > 0) return;
    for (let i = 0; i < 16; i++) {
      const d = node('span', 'ambient-rain-drop');
      d.style.left = (4 + (i * 5.9) % 92) + '%';
      d.style.top = (-18 - (i * 17) % 65) + '%';
      d.style.animationDuration = (3.0 + (i % 5) * 0.55) + 's';
      d.style.animationDelay = (-i * 0.45) + 's';
      box.append(d);
    }
  }

  function updateBackdrop() {
    const img = $('stageBackdrop');
    const stage = $('ambientStage');
    const rain = $('ambientRain');
    if (!img) return;
    const w = snapshot?.world;
    document.documentElement.dataset.mood = deriveAtmosphereMood(w);
    const still = prefs.backdrop ? resolveSceneStill(w?.location) : null;

    if (rain) {
      const tod = timeOfDay(w?.progression?.runtime?.clock?.time || '').phase;
      const loc = w?.location || '';
      const shouldRain = Boolean(prefs.backdrop && !reducedMotion() && (tod === 'night' || tod === 'dusk') && (loc === '徐家主宅' || loc === '市中心顶层公寓'));
      rain.classList.toggle('is-raining', shouldRain);
    }

    if (!still) {
      img.classList.remove('is-ready');
      stage?.classList.remove('has-scene-still');
      backdropTarget = '';
      return;
    }
    if (backdropTarget === still.url) {
      if (img.complete && img.naturalWidth) {
        img.classList.add('is-ready');
        stage?.classList.add('has-scene-still');
      }
      return;
    }
    backdropTarget = still.url;
    img.classList.remove('is-ready');
    img.onload = () => {
      if (backdropTarget === still.url && prefs.backdrop) {
        img.classList.add('is-ready');
        stage?.classList.add('has-scene-still');
      }
    };
    img.onerror = () => {
      img.classList.remove('is-ready');
      stage?.classList.remove('has-scene-still');
    };
    img.src = still.url;
  }

  function buildNpcDossierData(name) {
    const w = snapshot?.world;
    const meta = CHAR_META[name];
    const isHere = (w?.cast || []).includes(name);
    const seal = (name || '客').slice(0, 1);

    if (name === '徐承邺') {
      const pos = w?.vigilance?.position || '外地';
      const maxVig = Math.max(0, ...(w?.vigilance?.targets || []).map(t => Number(t.vigilance) || 0));
      const maxDisc = Math.max(0, ...(w?.vigilance?.targets || []).map(t => Number(t.discovery) || 0));
      return {
        name,
        seal: '邺',
        role: '徐家长子 · 27岁',
        tags: [
          (pos === '徐家主宅' || pos === '徐家住宅') ? '此刻在主宅' : ('行踪：' + pos),
          '最高警惕 ' + maxVig,
          '发现阶段 ' + maxDisc
        ],
        summary: '徐家养子，被母亲娇惯长大却极度渴望证明接班能力。对家里暗流敏感多疑，回宅时气压沉了下来。'
      };
    }

    return {
      name,
      seal,
      role: meta?.role || '临场登场人物',
      tags: [isHere ? '此刻同场' : '剧情角色', '当前地点：' + (w?.location || '未知')],
      summary: '当前剧情中自然登场的角色，以统一文学排版与场景空镜自然承接，无需预制立绘。'
    };
  }

  function renderNpcDossierCard(dossier, sceneStill) {
    const card = node('div', 'npc-dossier-card');
    const hero = node('div', 'npc-dossier-hero');
    if (sceneStill?.url) {
      const bg = node('img');
      bg.src = sceneStill.url;
      bg.alt = '';
      bg.decoding = 'async';
      hero.append(bg);
    }
    hero.append(node('div', 'npc-dossier-scrim'));
    const head = node('div', 'npc-dossier-head');
    head.append(node('span', 'npc-dossier-seal', dossier.seal));
    const headTxt = node('div');
    headTxt.append(node('strong', '', dossier.name), node('span', '', dossier.role));
    head.append(headTxt);
    hero.append(head);

    const body = node('div', 'npc-dossier-body');
    const tags = node('div', 'npc-dossier-tags');
    for (const t of dossier.tags) tags.append(node('span', 'npc-dossier-tag', t));
    body.append(tags, node('p', 'npc-dossier-text', dossier.summary));
    card.append(hero, body);
    return card;
  }

  function getLiveCharStats(name) {
    const w = snapshot?.world;
    if (!w || !name || !PEOPLE.includes(name)) return null;
    const panels = parsePanels(w.panels || []);
    const st = panels[name]?.stats || {};
    const micro = w.micro_states?.[name] || {};
    const buffs = characterBuffList(w, name);
    const hasFluidLock = buffs.some(b => String(b?.name || '').includes('体液锁定'));
    const passiveRaw = st['被动']?.raw || 'Lv.0';
    const passiveMatch = /Lv\.(\d+)/i.exec(passiveRaw);
    const phys = w.physiology?.[name] || {};
    return {
      name,
      affection: st['好感']?.num ?? 0,
      shame: st['羞耻']?.num ?? 100,
      depravity: st['堕落']?.num ?? 0,
      desire: st['欲望']?.num ?? 0,
      stamina: st['体力']?.num ?? 100,
      orgasm: st['高潮']?.num ?? 0,
      creampie: st['内射']?.num ?? (phys.creampie_count || 0),
      passiveLv: passiveMatch ? Number(passiveMatch[1]) : 0,
      pregnant: st['怀孕']?.bool === true || phys.pregnancy_stage === 'confirmed',
      phys,
      micro,
      buffs,
      hasFluidLock
    };
  }

  function buildGazeVitalsHud(name) {
    const st = getLiveCharStats(name);
    if (!st) return null;
    const hud = node('div', 'gaze-vitals-hud');
    const tagsRow = node('div', 'gaze-vitals-tags');
    const passiveNames = ['无被动', '洞察之瞳', '认知欺诈滤镜', '疲劳诱导', '绝对掌控'];
    tagsRow.append(node('span', 'gaze-vital-chip is-passive', `被动 Lv.${st.passiveLv} · ${passiveNames[st.passiveLv] || '洞察'}`));
    tagsRow.append(node('span', 'gaze-vital-chip' + (st.stamina <= 15 ? ' is-alert' : ''), `体力 ${st.stamina}`));
    if (st.pregnant) {
      tagsRow.append(node('span', 'gaze-vital-chip is-pregnant', '已确诊怀孕'));
    } else if (st.phys?.pregnancy_stage === 'latent') {
      tagsRow.append(node('span', 'gaze-vital-chip is-latent', '早孕微兆'));
    } else if (st.phys?.cycle_phase === '危险期') {
      tagsRow.append(node('span', 'gaze-vital-chip is-danger', '危险期'));
    }
    if (st.depravity > 0) {
      tagsRow.append(node('span', 'gaze-vital-chip is-depravity', `堕落 ${st.depravity}`));
    }
    if (st.creampie > 0) {
      tagsRow.append(node('span', 'gaze-vital-chip is-desire', `内射 ${st.creampie}次`));
    }
    if (st.hasFluidLock) {
      const flFloor = st.phys?.fluid_lock_floor ? ` ≥${st.phys.fluid_lock_floor}` : '';
      tagsRow.append(node('span', 'gaze-vital-chip is-desire', `体液锁定${flFloor}`));
    }
    if (st.phys?.masturbation_trace > 0) {
      tagsRow.append(node('span', 'gaze-vital-chip is-tension', '自渎余韵'));
    } else if (st.phys?.unrelieved_streak >= 1) {
      tagsRow.append(node('span', 'gaze-vital-chip is-desire', '欲求未平'));
    }
    if (st.micro.residual_tension) {
      tagsRow.append(node('span', 'gaze-vital-chip is-tension', '余韵未平'));
    } else if (st.micro.confusion_debt) {
      tagsRow.append(node('span', 'gaze-vital-chip is-confusion', '心绪失守'));
    } else if (st.micro.momentary_ease) {
      tagsRow.append(node('span', 'gaze-vital-chip is-ease', '戒备微松'));
    }
    hud.append(tagsRow);

    const grid = node('div', 'gaze-vitals-grid');
    const metrics = [
      { label: '好感', val: st.affection, suffix: '', tone: 'affection' },
      { label: '羞耻', val: st.shame, suffix: '', tone: 'shame' },
      { label: '欲望', val: st.desire, suffix: '', tone: 'desire' },
      { label: '高潮', val: st.orgasm, suffix: '%', tone: 'orgasm' }
    ];
    for (const m of metrics) {
      const cell = node('div', 'gaze-vital-cell is-' + m.tone);
      const top = node('div', 'gaze-vital-head');
      top.append(node('span', '', m.label), node('strong', '', m.val + m.suffix));
      const track = node('div', 'gaze-vital-track');
      const fill = node('span', 'gaze-vital-fill');
      fill.style.width = Math.max(0, Math.min(100, m.val)) + '%';
      track.append(fill);
      cell.append(top, track);
      grid.append(cell);
    }
    hud.append(grid);
    return hud;
  }

  function closeGazeLens() {
    gazeLensLocked = false;
    gazeHoldActive = false;
    const lens = $('gazeLens');
    if (!lens) return;
    lens.classList.remove('is-open');
    lens.setAttribute('aria-hidden', 'true');
  }

  function openGazeLens(name, { isHold = false, whisper = false, slot = '' } = {}) {
    const lens = $('gazeLens');
    if (!lens) return;
    const w = snapshot?.world;
    const hasImg = hasCharacterPortrait(name);
    gazeLensLocked = !isHold;
    gazeHoldActive = isHold;

    $('gazeLensClose').hidden = isHold;
    const fullBtn = $('gazeLensFullBtn');
    const body = $('gazeLensBody');
    body.replaceChildren();

    if (hasImg) {
      const resolved = resolveCharacterAsset(name, { slot, whisper });
      $('gazeLensMode').textContent = isHold ? '按住凝视中 · 松手即回正文' : '同席凝视 · 电影剧照';
      $('gazeLensTitle').textContent = name + (CHAR_META[name]?.role ? (' · ' + CHAR_META[name].role) : '');
      const im = node('img', 'gaze-lens-portrait');
      im.src = resolved?.url || image(name, 'into.png');
      im.alt = name;
      im.decoding = 'async';
      body.append(im);
      const vitalsHud = buildGazeVitalsHud(name);
      if (vitalsHud) body.append(vitalsHud);
      $('gazeLensFoot').textContent = (w?.location ? w.location + ' · ' : '') + (resolved?.label || '剧照');
      if (fullBtn) {
        fullBtn.hidden = isHold;
        fullBtn.onclick = () => {
          closeGazeLens();
          showPortrait(name, resolved?.slot || '');
        };
      }
    } else {
      const dossier = buildNpcDossierData(name);
      const still = resolveSceneStill(w?.location);
      $('gazeLensMode').textContent = isHold ? '按住速览人物档案 · 松手即回正文' : '人物档案卡';
      $('gazeLensTitle').textContent = dossier.name;
      body.append(renderNpcDossierCard(dossier, still));
      $('gazeLensFoot').textContent = '以同场景电影空镜与暗金人物手记自然承接';
      if (fullBtn) fullBtn.hidden = true;
    }

    lens.classList.add('is-open');
    lens.setAttribute('aria-hidden', 'false');
  }

  function openSceneLens(location, timeStr = null) {
    const lens = $('gazeLens');
    if (!lens) return;
    const w = snapshot?.world;
    const loc = location || w?.location || '当前场景';
    const still = resolveSceneStill(loc, timeStr);
    gazeLensLocked = true;
    gazeHoldActive = false;
    $('gazeLensMode').textContent = '场景电影空镜';
    $('gazeLensTitle').textContent = loc;
    $('gazeLensClose').hidden = false;
    if ($('gazeLensFullBtn')) $('gazeLensFullBtn').hidden = true;
    const body = $('gazeLensBody');
    body.replaceChildren();
    if (still?.url) {
      const im = node('img', 'gaze-lens-portrait');
      im.src = still.url;
      im.alt = loc;
      im.decoding = 'async';
      body.append(im);
    } else {
      body.append(renderNpcDossierCard({
        name: loc,
        seal: loc.slice(0, 1),
        role: '当前空间坐标',
        tags: [(w?.cast?.length ? '同席：' + w.cast.join('、') : '此刻独处')],
        summary: '该地点尚未配置自定义空镜图，将自动以建筑线稿呈现氛围；放入 txt文件/image/scenes/' + loc + '_night.webp 后刷新即刻生效。'
      }, null));
    }
    const clockStr = w?.progression?.runtime?.clock ? formatGameClock(w.progression.runtime.clock, w?.weekday || '') : '';
    const castStr = w?.cast?.length ? ('同席：' + w.cast.join('、')) : '此刻独处';
    $('gazeLensFoot').textContent = [clockStr, castStr].filter(Boolean).join(' · ');
    lens.classList.add('is-open');
    lens.setAttribute('aria-hidden', 'false');
  }

  function bindHoldGaze(el, speaker, opts = {}) {
    let timer = null;
    let openedByHold = false;
    let suppressClick = false;
    let startX = 0;
    let startY = 0;
    const clearHold = () => {
      if (timer) { clearTimeout(timer); timer = null; }
      if (openedByHold) {
        openedByHold = false;
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 320);
        closeGazeLens();
      }
    };
    el.addEventListener('pointerdown', ev => {
      if (ev.button && ev.button !== 0) return;
      ev.stopPropagation();
      openedByHold = false;
      suppressClick = false;
      startX = ev.clientX || 0;
      startY = ev.clientY || 0;
      if (gazeHoldCleanup) gazeHoldCleanup();
      gazeHoldCleanup = clearHold;
      timer = setTimeout(() => {
        timer = null;
        openedByHold = true;
        haptic(8);
        openGazeLens(speaker, { isHold: true, whisper: !!opts.whisper, slot: opts.slot || '' });
      }, 190);
    });
    el.addEventListener('pointermove', ev => {
      if (!timer) return;
      if (Math.hypot((ev.clientX || 0) - startX, (ev.clientY || 0) - startY) > 10) {
        clearTimeout(timer);
        timer = null;
      }
    });
    el.addEventListener('click', ev => {
      ev.stopPropagation();
      if (timer) { clearTimeout(timer); timer = null; }
      if (openedByHold || suppressClick) {
        openedByHold = false;
        suppressClick = false;
        closeGazeLens();
        return;
      }
      haptic(8);
      if (hasCharacterPortrait(speaker)) showPortrait(speaker, opts.slot || '');
      else openGazeLens(speaker, { isHold: false });
    });
  }

  function primaryPortraitHero(w) {
    const cast = w?.cast || [];
    if (lastSpeaker && cast.includes(lastSpeaker) && hasCharacterPortrait(lastSpeaker)) return lastSpeaker;
    return cast.find(n => hasCharacterPortrait(n)) || '';
  }

  function renderTopPeekDrawer() {
    const drawer = $('topPeekDrawer');
    if (!drawer) return;
    const w = snapshot?.world;
    const hero = primaryPortraitHero(w);
    const still = resolveSceneStill(w?.location);

    const hudCast = $('hudCast');
    if (hudCast) {
      const labelText = topPeekOpen
        ? '收起 ▴'
        : (hero ? ('凝视 · ' + hero + ' ▾') : '环顾空镜 ▾');
      let btn = hudCast.querySelector('.hud-gaze-pill');
      if (!btn) {
        btn = node('button', 'hud-gaze-pill');
        btn.type = 'button';
        btn.onclick = () => {
          haptic(8);
          topPeekOpen = !topPeekOpen;
          renderTopPeekDrawer();
        };
        hudCast.replaceChildren(btn);
      }
      btn.textContent = labelText;
      btn.setAttribute('aria-expanded', String(topPeekOpen));
    }

    drawer.classList.toggle('is-open', topPeekOpen);
    drawer.setAttribute('aria-hidden', String(!topPeekOpen));
    if (!topPeekOpen) return;

    const img = $('topPeekImg');
    const expandBtn = $('topPeekExpand');
    if (hero) {
      const asset = resolveCharacterAsset(hero);
      img.src = asset?.url || image(hero, 'into.png');
      img.style.objectPosition = asset?.pos || '50% 16%';
      $('topPeekTitle').textContent = hero;
      $('topPeekSub').textContent = (w?.location ? w.location + ' · ' : '') + (asset?.label || '剧照');
      expandBtn.hidden = false;
      expandBtn.onclick = () => {
        haptic(8);
        topPeekOpen = false;
        renderTopPeekDrawer();
        showPortrait(hero, asset?.slot || '');
      };
    } else if (still) {
      img.src = still.url;
      img.style.objectPosition = '50% 50%';
      $('topPeekTitle').textContent = w?.location || '当前场景';
      $('topPeekSub').textContent = w?.cast?.length ? ('同席：' + w.cast.join('、')) : '此刻独处 · 电影空镜';
      expandBtn.hidden = false;
      expandBtn.onclick = () => {
        haptic(8);
        topPeekOpen = false;
        renderTopPeekDrawer();
        openSceneLens(w?.location);
      };
    } else {
      topPeekOpen = false;
      drawer.classList.remove('is-open');
      openSceneLens(w?.location);
    }
  }

  function renderDesktopSideFocus() {
    const box = $('sideFocusCard');
    if (!box) return;
    const w = snapshot?.world;
    if (!w) {
      box.replaceChildren();
      return;
    }
    const cast = w.cast || [];
    const focus = (desktopFocusName && cast.includes(desktopFocusName))
      ? desktopFocusName
      : (primaryPortraitHero(w) || cast[0] || '');

    const still = resolveSceneStill(w.location);
    box.replaceChildren();

    if (focus && hasCharacterPortrait(focus)) {
      const asset = resolveCharacterAsset(focus);
      const btn = node('button', 'side-focus-portrait');
      btn.type = 'button';
      const im = node('img');
      im.src = asset?.url || image(focus, 'into.png');
      im.alt = focus;
      im.style.objectPosition = asset?.pos || '50% 16%';
      im.decoding = 'async';
      const meta = node('div', 'side-focus-meta');
      meta.append(node('strong', '', focus), node('span', '', asset?.label || CHAR_META[focus]?.role || ''));
      btn.append(im, node('div', 'side-focus-scrim'), meta);
      btn.onclick = () => { haptic(8); showPortrait(focus, asset?.slot || ''); };
      box.append(btn);
      return;
    }

    // Flip seamlessly to Location Empty Still + Dossier Card for 徐承邺, AI NPCs, or Solo!
    const dossier = focus
      ? buildNpcDossierData(focus)
      : {
          name: w.location || '此刻独处',
          seal: (w.location || '静').slice(0, 1),
          role: w.progression?.runtime?.clock ? formatGameClock(w.progression.runtime.clock, w.weekday || '') : '当前场景',
          summary: '此刻四下安静，无人同席。可轻触查看场景空镜或移步前往他处。'
        };
    const btn = node('button', 'side-focus-dossier');
    btn.type = 'button';
    const head = node('div', 'side-focus-scene-head');
    if (still?.url) {
      const im = node('img');
      im.src = still.url;
      im.alt = w.location || '';
      im.decoding = 'async';
      head.append(im);
    }
    const meta = node('div', 'side-focus-meta');
    meta.append(node('strong', '', dossier.name), node('span', '', dossier.role));
    head.append(node('div', 'side-focus-scrim'), meta);
    btn.append(head, node('div', 'side-focus-dossier-body', dossier.summary));
    btn.onclick = () => {
      haptic(8);
      if (focus) openGazeLens(focus, { isHold: false });
      else openSceneLens(w.location);
    };
    box.append(btn);
  }

  function previewChoiceWeight(optId) {
    const beam = $('hudScalesBeam');
    const hold = $('hudStaminaHold');
    const fill = $('hudStaminaFill');
    const valEl = $('hudStaminaVal');
    const pg = progression();
    const tiltMap = { A: -5, B: 0, C: 9 };

    if (!optId) {
      if (beam) {
        beam.classList.remove('is-weighted');
        beam.style.transform = '';
      }
      updateHudVitals();
      return;
    }
    if (beam) {
      beam.classList.add('is-weighted');
      beam.style.transform = 'rotate(' + (tiltMap[optId] || 0) + 'deg)';
    }
    if (pg && fill && hold && valEl) {
      const st = Math.max(0, Math.min(100, pg.stamina));
      const cost = COSTS[optId] || 0;
      const after = Math.max(0, st - cost);
      hold.setAttribute('stroke-dashoffset', String(HUD_RING_C * (1 - st / 100)));
      fill.setAttribute('stroke-dashoffset', String(HUD_RING_C * (1 - after / 100)));
      valEl.textContent = String(after);
    }
  }

  function insertInputBracket(prefix = '') {
    const inp = $('input');
    if (!inp) return;
    haptic(6);
    const val = inp.value || '';
    const start = inp.selectionStart ?? val.length;
    const end = inp.selectionEnd ?? start;
    const selected = val.slice(start, end);
    const snippet = '（' + prefix + selected + '）';
    inp.value = val.slice(0, start) + snippet + val.slice(end);
    cache.draft = inp.value;
    save();
    inp.focus();
    const caret = start + 1 + prefix.length + selected.length;
    inp.setSelectionRange(caret, caret);
    controls();
    sizing();
  }

  function renderBracketChips(w) {
    const bar = $('bracketChips');
    if (!bar) return;
    const heldIds = w?.intel?.held || [];
    const catalog = w?.intel?.catalog || [];
    const sig = heldIds.join(',');
    if (bar.dataset.sig === sig && bar.childElementCount > 0) return;
    bar.dataset.sig = sig;
    bar.replaceChildren();

    const actChip = node('button', 'bracket-chip is-primary', '＋（）括号动作');
    actChip.type = 'button';
    actChip.onclick = () => insertInputBracket('');

    const thChip = node('button', 'bracket-chip', '＋（）内心想法');
    thChip.type = 'button';
    thChip.onclick = () => insertInputBracket('心底暗忖：');

    bar.append(actChip, thChip);

    for (const iid of heldIds) {
      const item = catalog.find(x => x.id === iid);
      const label = item?.name || iid;
      const chip = node('button', 'bracket-chip is-intel', '◆ 亮牌：' + label);
      chip.type = 'button';
      chip.onclick = () => {
        haptic(8);
        const inp = $('input');
        if (!inp) return;
        inp.value = '（我把暗中掌握的「' + label + '」线索摊在眼前）这件事，你打算怎么解释？';
        cache.draft = inp.value;
        save();
        inp.focus();
        controls();
        sizing();
      };
      bar.append(chip);
    }
  }

  function applyReadingFocus() {
    const msgBox = $('messages');
    const stream = $('stream');
    if (!msgBox || !stream) return;
    if (!prefs.readingDof) {
      msgBox.classList.remove('is-dof-on');
      return;
    }
    const items = Array.from(msgBox.children).filter(el => el.classList.contains('msg') || el.classList.contains('cinema-plate'));
    items.forEach(el => el.classList.remove('is-focus-beat'));
    const nearBottom = (stream.scrollHeight - stream.scrollTop - stream.clientHeight) < 88;
    const shouldDof = nearBottom && items.length > 1;
    msgBox.classList.toggle('is-dof-on', shouldDof);
    if (shouldDof) {
      items[items.length - 1].classList.add('is-focus-beat');
      // If the penultimate element is the character plate immediately introducing the last beat, keep it crisp too
      if (items.length >= 2 && items[items.length - 2].classList.contains('cinema-plate')) {
        items[items.length - 2].classList.add('is-focus-beat');
      }
    }
  }

  function updatePlateParallax() {
    parallaxRaf = 0;
    if (reducedMotion()) return;
    const stream = $('stream');
    if (!stream) return;
    const rect = stream.getBoundingClientRect();
    if (!rect.height) return;
    const center = rect.top + rect.height / 2;
    stream.querySelectorAll('.cinema-plate-img').forEach(img => {
      const r = img.parentElement.getBoundingClientRect();
      if (r.bottom < rect.top - 40 || r.top > rect.bottom + 40) return;
      const rel = ((r.top + r.height / 2) - center) / rect.height;
      const shift = Math.max(-12, Math.min(12, rel * 22));
      img.style.transform = 'scale(1.08) translateY(' + shift.toFixed(1) + 'px)';
    });
  }

  function schedulePlateParallax() {
    if (parallaxRaf || reducedMotion()) return;
    parallaxRaf = requestAnimationFrame(updatePlateParallax);
  }

  function updateHudVitals() {
    const pg = progression();
    const res = snapshot?.task?.reservation;
    const pill = $('staminaHud');
    const fill = $('hudStaminaFill');
    const hold = $('hudStaminaHold');
    const valEl = $('hudStaminaVal');
    const tagEl = $('hudStaminaTag');
    const clockText = $('clockText');
    const clockOrb = $('clockOrb');

    if (pg) {
      const st = Math.max(0, Math.min(100, pg.stamina));
      valEl.textContent = String(st);
      const heldBefore = res?.status === 'held' ? Math.max(st, Math.min(100, res.quote.before)) : st;
      tagEl.textContent = res?.status === 'held' ? ('-' + res.quote.total + ' 暂扣') : '体力';
      fill.setAttribute('stroke-dashoffset', String(HUD_RING_C * (1 - st / 100)));
      hold.setAttribute('stroke-dashoffset', String(HUD_RING_C * (1 - heldBefore / 100)));
      pill.classList.toggle('is-low', st < 20);
      pill.classList.toggle('is-mid', st >= 20 && st < 50);

      if (pg.runtime?.clock) {
        const { time } = pg.runtime.clock;
        clockText.textContent = formatGameClock(pg.runtime.clock, snapshot?.world?.weekday || '');
        const tod = timeOfDay(time);
        document.documentElement.dataset.timeOfDay = tod.phase;
        if (clockOrb.dataset.icon !== tod.icon) {
          clockOrb.dataset.icon = tod.icon;
          clockOrb.replaceChildren(icon(tod.icon, 'chip-svg'));
        }
      } else {
        clockText.textContent = '第' + (pg.runtime?.memory_round || 1) + '记忆回合';
      }
    } else {
      valEl.textContent = '--';
      tagEl.textContent = '体力';
      fill.setAttribute('stroke-dashoffset', String(HUD_RING_C * 0.2));
      hold.setAttribute('stroke-dashoffset', String(HUD_RING_C));
      pill.classList.remove('is-low', 'is-mid');
      clockText.textContent = snapshot?.world ? (snapshot.world.interaction.count + ' 段剧情') : '连接本地服务';
    }
  }

  function updatePlaybackPips(p) {
    const wrap = $('playbackPips');
    if (!wrap || !p?.segment_id) return;
    const total = Math.max(1, p.total || 1);
    const revealed = Math.max(0, Math.min(total, p.revealed || 0));
    if (total <= 12) {
      const key = total + ':' + revealed;
      if (wrap.dataset.key === key) return;
      wrap.dataset.key = key;
      wrap.replaceChildren();
      for (let i = 1; i <= total; i++) {
        const cls = 'pip' + (i < revealed ? ' is-read' : i === revealed ? ' is-current' : '');
        wrap.append(node('span', cls));
      }
    } else {
      const pct = Math.round((revealed / total) * 100);
      const key = 'bar:' + pct;
      if (wrap.dataset.key === key) return;
      wrap.dataset.key = key;
      const bar = node('div', 'stamina-meter');
      bar.style.width = '92px';
      const fill = node('span', 'stamina-fill');
      fill.style.setProperty('--balance', pct + '%');
      bar.append(fill);
      wrap.replaceChildren(bar);
    }
  }

  function updateStageCurtain() {
    const curtain = $('stageCurtain');
    if (!curtain) return;
    const isAct = active();
    const task = snapshot?.task;
    const useCurtain = isCurtainMode();
    const isSubmitting = posting && !!cache.pending;

    const showActive = useCurtain && (isAct || isSubmitting);
    const showError = useCurtain && !isAct && !isSubmitting && task
      && ['failed', 'interrupted'].includes(task.status)
      && !!curtainTrackedReqId && task.request_id === curtainTrackedReqId;

    if (!showActive && !showError) {
      if (!curtain.hidden && curtainHideTimer === null) {
        if (reducedMotion()) {
          curtain.hidden = true;
          curtain.classList.remove('is-hiding', 'is-error');
        } else {
          curtain.classList.add('is-hiding');
          curtainHideTimer = setTimeout(() => {
            curtainHideTimer = null;
            curtain.hidden = true;
            curtain.classList.remove('is-hiding', 'is-error');
          }, 340);
        }
      }
      if (!isAct && !isSubmitting && (!task || task.status === 'committed' || task.status === 'cancelled')) {
        curtainTrackedReqId = '';
      }
      return;
    }

    if (curtainHideTimer !== null) {
      clearTimeout(curtainHideTimer);
      curtainHideTimer = null;
    }
    curtain.classList.remove('is-hiding');
    curtain.hidden = false;

    const step1 = $('curtainStep1'), step2 = $('curtainStep2'), step3 = $('curtainStep3');
    const setSteps = (activeIdx, allDone = false) => {
      [step1, step2, step3].forEach((el, idx) => {
        if (!el) return;
        const n = idx + 1;
        el.classList.toggle('is-done', allDone || n < activeIdx);
        el.classList.toggle('is-active', !allDone && n === activeIdx);
      });
    };

    const actionText = (task?.action || cache.pending?.action || '').trim();
    const quoteEl = $('curtainActionQuote');
    if (quoteEl) {
      if (actionText && task?.selection?.option_id !== 'BEGIN') {
        quoteEl.textContent = actionText.length > 96 ? actionText.slice(0, 96) + '…' : actionText;
        quoteEl.hidden = false;
      } else {
        quoteEl.hidden = true;
      }
    }

    const cancelBtn = $('curtainCancelBtn');
    const retryBtn = $('curtainRetryBtn');
    const fullRetryBtn = $('curtainFullRetryBtn');
    const dismissBtn = $('curtainDismissBtn');
    const progEl = $('curtainProgress');

    if (showError) {
      curtain.classList.add('is-error');
      setSteps(3, false);
      const hasStage1Cp = Boolean(task && task.has_stage1_checkpoint);
      if (hasStage1Cp) {
        if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '主模型剧情已留存 · 已退还体力';
        if ($('curtainTitle')) $('curtainTitle').textContent = '仅后台结算未能通过';
        if ($('curtainSub')) $('curtainSub').textContent = (task.error || '后台结算未通过校验') + ' · 主模型已写完的剧情已保底留存，点击下方将只重跑副模型，不重复消耗主模型费用。';
        if (retryBtn) { retryBtn.textContent = '仅重试结算（免主模型费）'; retryBtn.hidden = false; retryBtn.disabled = baseBlocked(); }
        if (fullRetryBtn) { fullRetryBtn.hidden = false; fullRetryBtn.disabled = baseBlocked(); }
      } else {
        if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '天平归位 · 已退还体力';
        if ($('curtainTitle')) $('curtainTitle').textContent = '本次推演未能成幕';
        if ($('curtainSub')) $('curtainSub').textContent = (task.error || '后台结算未通过校验') + ' · 预扣体力已全额退还。';
        if (retryBtn) { retryBtn.textContent = '重试本次推演'; retryBtn.hidden = false; retryBtn.disabled = baseBlocked(); }
        if (fullRetryBtn) fullRetryBtn.hidden = true;
      }
      if (progEl) progEl.hidden = true;
      if (cancelBtn) cancelBtn.hidden = true;
      if (dismissBtn) dismissBtn.hidden = false;
      return;
    }

    curtain.classList.remove('is-error');
    const reqId = task?.request_id || cache.pending?.request_id || '';
    if (reqId) curtainTrackedReqId = reqId;

    const pvStage = hasPreview() ? streamPreview.stage : '';
    const pvCount = hasPreview() && Array.isArray(streamPreview.messages) ? streamPreview.messages.length : 0;
    const queueIssue = queuedBridgeIssue(snapshot);
    const isStage2Resume = Boolean(task && task.resume_stage2);

    if (pvStage === 'settling_retry') {
      setSteps(3);
      if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '二次核验 · 深度校准';
      if ($('curtainTitle')) $('curtainTitle').textContent = '细核因果 · 校准细节中……';
      if ($('curtainSub')) $('curtainSub').textContent = '副模型已自动开启思考核对事件与记忆，无需重跑剧情。';
      if (progEl) {
        progEl.textContent = pvCount ? ('已收束 ' + pvCount + ' 句 · 后台同步预热语音') : '后台深度校准中';
        progEl.hidden = false;
      }
    } else if (isStage2Resume) {
      setSteps(3);
      if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '断点续结 · 免主模型费';
      if ($('curtainTitle')) $('curtainTitle').textContent = queueIssue ? '等待桥接领单……' : '正在仅重跑后台结算……';
      if ($('curtainSub')) $('curtainSub').textContent = queueIssue
        || '已直接复用上次留存的前台剧情（跳过主模型），等待副模型结算入档后即刻揭幕。';
      if (progEl) {
        progEl.textContent = pvCount ? ('复用 ' + pvCount + ' 句剧情 · 仅结算入档中') : '仅重跑副模型结算';
        progEl.hidden = false;
      }
    } else if (pvStage === 'settling' || task?.status === 'validating') {
      setSteps(3);
      if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '落幕封存 · 声韵预热';
      if ($('curtainTitle')) $('curtainTitle').textContent = '校对因果 · 封存记忆中……';
      if ($('curtainSub')) $('curtainSub').textContent = '剧情已落笔，正在校验数值入档并预热首句语音，片刻后揭幕。';
      if (progEl) {
        progEl.textContent = pvCount ? ('共 ' + pvCount + ' 句 · 预热语音中') : '后台结算入档中';
        progEl.hidden = false;
      }
    } else if (pvStage === 'streaming' && pvCount > 0) {
      setSteps(2);
      if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '执笔生景 · 静候成幕';
      if ($('curtainTitle')) $('curtainTitle').textContent = '微幕渐成 · 同步预热声韵';
      if ($('curtainSub')) $('curtainSub').textContent = '正在延续你的抉择展开这一幕，待结算完毕后完整揭幕。';
      if (progEl) {
        progEl.textContent = '已落笔 ' + pvCount + ' 句 · 后台同步预热语音';
        progEl.hidden = false;
      }
    } else {
      setSteps(1);
      if ($('curtainEyebrow')) $('curtainEyebrow').textContent = '天平演算 · 幕帷静候';
      if ($('curtainTitle')) $('curtainTitle').textContent = queueIssue
        ? '等待桥接领单……'
        : pvStage === 'thinking' ? '沉思落子 · 构思微幕中' : '正在承接你的抉择……';
      if ($('curtainSub')) $('curtainSub').textContent = queueIssue
        || '主模型正在阅读记忆与现场细节，稍候即可揭幕听读。';
      if (progEl) progEl.hidden = true;
    }

    if (cancelBtn) {
      cancelBtn.hidden = !(isAct && task?.reservation);
      cancelBtn.disabled = posting || progressing;
    }
    if (retryBtn) retryBtn.hidden = true;
    if (fullRetryBtn) fullRetryBtn.hidden = true;
    if (dismissBtn) dismissBtn.hidden = true;
  }

  function controls() {
    const p = snapshot?.playback, ready = canDecide(), base = baseBlocked(), hasSegment = !!p?.segment_id;
    const rest = resting(), isAct = active(), task = snapshot?.task;
    const previewOn = hasPreviewNodes();
    const mode = previewOn ? 'playback' : !hasSegment ? 'empty' : !ready ? 'playback' : 'decision';

    document.body.classList.toggle('mode-empty', mode === 'empty');
    document.body.classList.toggle('mode-playback', mode === 'playback');
    document.body.classList.toggle('mode-decision', mode === 'decision');
    document.body.classList.toggle('is-thinking', isAct);
    $('statusSpinner').hidden = !isAct;

    const showDecisions = ready && !rest && !previewOn;
    const isCollapsed = showDecisions && deckCollapsed;
    const optCount = current()?.decision?.options?.length || 0;
    const hasChoices = showDecisions && optCount > 0;
    const hasDraft = Boolean(($('input')?.value || '').trim());
    const formCompact = hasChoices && !customComposerExpanded && !hasDraft && !document.body.classList.contains('kb-open');
    $('decisionPanel').hidden = !showDecisions || isCollapsed;
    $('form').hidden = !showDecisions || isCollapsed;
    $('form').classList.toggle('has-choices', hasChoices);
    $('form').classList.toggle('is-compact', formCompact);
    if ($('customFormToggle')) {
      const expanded = !formCompact;
      $('customFormToggle').setAttribute('aria-expanded', String(expanded));
      const hint = $('customFormToggle').querySelector('.custom-form-toggle-hint');
      if (hint) hint.textContent = expanded ? '收起 ▴' : '展开 ▾';
    }
    if ($('deckCollapsedBar')) {
      $('deckCollapsedBar').hidden = !isCollapsed;
      if (isCollapsed && $('deckCollapsedLabel')) {
        $('deckCollapsedLabel').textContent = '展开抉择 · ' + (optCount || 3) + ' 项可选 / 自由行动';
      }
    }
    if (lastUiMode !== mode) {
      const wasInitial = lastUiMode === '';
      const enteredDecision = mode === 'decision' && (lastUiMode === 'playback' || wasInitial);
      lastUiMode = mode;
      if (mode !== 'decision') customComposerExpanded = false;
      if (enteredDecision) {
        const snap = () => {
          sizing();
          latest(wasInitial);
        };
        requestAnimationFrame(snap);
        setTimeout(snap, 220);
      }
    }

    $('restCard').hidden = !ready || !rest || previewOn;
    $('rest').hidden = !ready || !rest || previewOn;
    $('rest').disabled = base;
    $('cancelTask').hidden = !isAct || !task?.reservation;
    $('cancelTask').disabled = posting || progressing;

    const pg = progression(), res = task?.reservation;
    $('resourceStatus').textContent = pg
      ? (res?.status === 'held'
          ? '已暂扣 ' + res.quote.total + ' · 原体力 ' + res.quote.before + ' · 结算后判断疲惫'
          : '体力 ' + pg.stamina + ' / 100 · 道具可恢复额度 ' + pg.item_budget)
        + (pg.runtime.clock ? ' · 第' + pg.runtime.clock.day + '天 ' + pg.runtime.clock.time : '')
      : '';
    $('resourceStatus').hidden = !pg;

    const hasUsableRecovery = $('recoveryItem').options.length > 1;
    $('recoveryWrap').hidden = !hasUsableRecovery;
    $('form').classList.toggle('is-low-stamina', !!(pg && pg.stamina <= 45));
    $('useRecovery').disabled = ordinaryBlocked() || !$('recoveryItem').value || !pg || pg.item_budget <= 0 || pg.stamina >= 100;

    const isPureRec = pureRecovery();
    $('sendCost').textContent = isPureRec ? '免费恢复' : (pg ? '-15⚡' : '提交');
    $('send').disabled = ordinaryBlocked() || (!isPureRec && !afford(15));
    $('input').disabled = !ready || posting || progressing || !online || !storageOK || !!cache.pending || isAct;

    $('actions').hidden = !ready || rest || previewOn;
    $('actions').disabled = ordinaryBlocked() || !afford(15);
    if ($('quickActionBtn')) $('quickActionBtn').disabled = ordinaryBlocked() || !afford(15);
    $('move').disabled = ordinaryBlocked() || !afford(15) || !$('destination').value;
    $('give').disabled = ordinaryBlocked() || !afford(15) || !$('item').value || !$('recipient').value;

    $('choices').querySelectorAll('button').forEach(b => {
      b.disabled = ordinaryBlocked() || !afford(COSTS[b.dataset.option]);
    });

    const advLabel = $('advanceLabel') || $('advance');
    if (previewOn) {
      const pvTotal = streamPreview.messages.length;
      const pvRev = Math.min(pvTotal, streamPreview.revealed || 0);
      $('playbackBar').hidden = false;
      $('advance').hidden = false;
      $('advance').disabled = pvRev >= pvTotal;
      advLabel.textContent = pvRev < pvTotal
        ? '轻触继续预览'
        : streamPreview.stage === 'settling_retry' ? '深度校准因果中…'
        : streamPreview.stage === 'settling' ? '后台结算入档中…' : '正在流式演播…';
      $('playbackCount').textContent = pvRev + ' / ' + pvTotal + (
        streamPreview.stage === 'settling_retry' ? ' · 校准中'
        : streamPreview.stage === 'settling' ? ' · 结算中' : ' · 流式'
      );
      updatePlaybackPips({ segment_id: 'preview:' + streamPreview.request_id, revealed: pvRev, total: pvTotal });
    } else {
      $('playbackBar').hidden = !hasSegment || ready;
      $('advance').hidden = !hasSegment || p.completed;
      $('advance').disabled = base;
      advLabel.textContent = progressing ? '正在保存进度…'
        : !p?.revealed ? '开始演播'
        : p.revealed < p.total ? '轻触继续剧情'
        : '读完本段 · 展开抉择';
      $('playbackCount').textContent = hasSegment
        ? (p.completed ? '本段已读完' : p.revealed + ' / ' + p.total)
        : '';
      if (hasSegment) updatePlaybackPips(p);
    }

    $('voiceToggle').setAttribute('aria-pressed', String(cache.voice));
    $('voiceToggle').setAttribute('aria-label', cache.voice ? '关闭语音' : '开启语音');
    $('voiceToggle').title = cache.voice ? '语音已开（点击静音）' : '已静音（点击开启）';
    $('hudVoiceBtn').setAttribute('aria-pressed', String(cache.voice));
    $('hudVoiceWave').classList.toggle('is-speaking', isSpeaking && cache.voice);

    const needsAudioUnlock = audioStatus.includes('启用');
    $('replayVoice').hidden = !audioMessage || !needsAudioUnlock;
    $('replayVoice').textContent = needsAudioUnlock ? '启用语音' : '重听';
    $('audioStatus').textContent = audioStatus;

    $('begin').hidden = hasSegment || previewOn;
    $('begin').disabled = base;
    if (!hasSegment) $('begin').textContent = rest ? '开始休息 · 免费' : '踏入此刻 · 继续剧情';

    $('refresh').disabled = posting || polling || progressing;
    const showRetry = ['failed', 'interrupted', 'cancelled'].includes(task?.status);
    $('retry').hidden = !showRetry;
    $('retry').disabled = base;
    $('retry').textContent = task?.has_stage1_checkpoint ? '仅重试结算（免主模型费）' : '重试';
    $('older').disabled = posting || polling || progressing;
    $('confirmNewGame').disabled = base;

    const showCheck = !!cache.pending;
    const showResend = !!cache.pending && missing && !mismatch;
    const showEdit = !!cache.pending && missing && !mismatch;
    $('checkPending').hidden = !showCheck;
    $('checkPending').disabled = posting || polling || progressing;
    $('resendPending').hidden = !showResend;
    $('resendPending').disabled = posting || polling || !online || isAct;
    $('editPending').hidden = !showEdit;
    $('editPending').disabled = posting || polling || !online;
    $('recoveryBox').hidden = !(showRetry || showCheck || showResend || showEdit);

    $('pending').textContent = cache.pending
      ? '待确认行动：' + cache.pending.action
      : task && ['queued', 'generating', 'validating', 'failed', 'interrupted'].includes(task.status)
        ? '当前行动：' + task.action
        : '';
    $('pending').hidden = !$('pending').textContent;

    const protoBad = online && ![2, 3].includes(snapshot?.interaction_protocol);
    const bridgeWarn = hasSegment && ready && online && !snapshot?.bridge_connected;
    const showStatusStrip = Boolean(
      isAct || !online || error || task?.error || cache.pending || protoBad || bridgeWarn || needsAudioUnlock
    );
    if ($('statusWrap')) $('statusWrap').hidden = !showStatusStrip;

    const queueIssue = queuedBridgeIssue(snapshot);
    $('status').classList.toggle('error', !!error || !!task?.error || !!queueIssue);
    const pvStage = hasPreview() ? streamPreview.stage : '';
    const activeStatusText = pvStage === 'thinking'
      ? '模型思考中 · 正在构思微幕剧情……'
      : pvStage === 'streaming'
        ? (isCurtainMode()
          ? '幕帷演播中 · 已落笔 ' + streamPreview.messages.length + ' 句（预热语音中）'
          : '流式演播中 · 已生成 ' + streamPreview.messages.length + ' 句（可先轻触阅读）')
      : pvStage === 'settling_retry'
        ? '副模型正在深度校对因果与记忆……'
      : pvStage === 'settling'
        ? '前台演播完毕 · 后台结算入档中……'
      : task?.status === 'generating'
        ? '天平演算中 · 正在承接你的抉择推演剧情……'
      : task?.status === 'validating'
        ? '正在校验剧情并写入记忆存档……'
      : queueIssue || '已入列 · 等待 Operit 领取，开始时使用最新选择的模型……';
    $('status').textContent = error || (
      !online ? '正在连接本地剧场服务，你的行动已安全保留……'
      : protoBad ? '请重启本地服务以加载最新剧情演播接口。'
      : cache.pending
        ? (mismatch ? '原编号与服务记录不符，请在系统设定查看连接详情。'
          : missing ? '原编号尚未登记，可点击下方按钮重发。'
          : '正在核对上一次行动状态…')
      : isAct ? activeStatusText
      : task?.error
      || (needsAudioUnlock ? '浏览器暂停了自动播放，轻触右侧“启用语音”继续听读。'
      : bridgeWarn ? '抉择已就绪 · Operit 桥接待连接。'
      : !hasSegment ? '幕布已备好，轻触下方按钮进入此刻现场。'
      : !p.completed ? '轻触屏幕继续阅读。'
      : rest ? '夜色已深，本段收束，请安稳休整后再启程。'
      : '此刻由你决定下一步。')
    );

    const bridge = snapshot?.bridge;
    const bridgeOnline = !!snapshot?.bridge_connected;
    const isOlderSemver = (cur, target) => {
      if (!cur || !target || cur === target) return false;
      const a = String(cur).split('.').map(n => parseInt(n, 10) || 0);
      const b = String(target).split('.').map(n => parseInt(n, 10) || 0);
      const len = Math.max(a.length, b.length);
      for (let i = 0; i < len; i++) {
        if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) < (b[i] || 0);
      }
      return false;
    };
    const pluginOutdated = !!(
      bridge?.plugin_version
      && bridge?.expected_plugin_version
      && isOlderSemver(bridge.plugin_version, bridge.expected_plugin_version)
    );
    $('bridgeDot')?.classList.toggle('is-online', bridgeOnline);
    $('bridgeInfo').textContent = (bridgeOnline ? '桥接已连接' : '桥接未连接')
      + (snapshot?.bridge_model ? ' · ' + snapshot.bridge_model.model_id : '')
      + (bridge?.plugin_version ? ' (v' + bridge.plugin_version + ')' : '')
      + (pluginOutdated ? ' · 有新版 v' + bridge.expected_plugin_version + ' 待在 Operit 导入' : '')
      + (bridge?.last_error ? ' · ' + bridge.last_error : '');
    const session = bridge?.session;
    const waiting = bridge?.control?.status === 'requested';
    const sessionBusy = posting || isAct || bridge?.busy || waiting || !bridge?.present || !session;
    const sessionPolicy = $('storySessionPolicy');
    if (sessionPolicy) {
      sessionPolicy.disabled = !!sessionBusy;
      sessionPolicy.value = session?.policy || 'continuous';
    }
    if ($('storySessionReset')) $('storySessionReset').disabled = !!sessionBusy;
    const maxTurnsSel = $('storyMaxTurns');
    const curMaxTurns = typeof session?.max_turns === 'number' && session.max_turns >= 2 ? session.max_turns : 10;
    if (maxTurnsSel) {
      const turnVal = String(curMaxTurns);
      if (!Array.from(maxTurnsSel.options).some(o => o.value === turnVal)) {
        const opt = document.createElement('option');
        opt.value = turnVal;
        opt.textContent = '每 ' + turnVal + ' 轮自动开干净新会话';
        maxTurnsSel.append(opt);
      }
      maxTurnsSel.disabled = !!sessionBusy;
      maxTurnsSel.value = turnVal;
    }
    const turnNote = typeof session?.turn_count === 'number'
      ? ' · 本会话 ' + session.turn_count + '/' + curMaxTurns + ' 轮'
      : '';
    const upgradeNote = pluginOutdated
      ? ' · 请导入 scene_chat_dev/artifacts/故事桥接-continuous-' + bridge.expected_plugin_version + '.toolpkg'
      : '';
    if ($('storySessionStatus')) $('storySessionStatus').textContent = bridge?.control?.status === 'failed' ? bridge.control.error
      : waiting ? '正在应用桥接设置…'
      : !session ? '会话控制需要新版桥接与 Python 服务。'
      : (session.chat_id ? '当前会话 ' + session.chat_id.slice(0, 8) : '下次行动建立新会话')
        + turnNote
        + (session.reset_reason ? ' · ' + session.reset_reason : '')
        + upgradeNote;

    const availModels = Array.isArray(bridge?.available_models) ? bridge.available_models : [];
    const funcBindings = Array.isArray(bridge?.function_bindings) ? bridge.function_bindings : [];
    const bindingBySlot = new Map(funcBindings.map(b => [b.function_type, b]));
    const slotOptionText = slot => {
      const b = bindingBySlot.get(slot);
      const label = BRIDGE_SLOT_LABELS[slot] || slot;
      return label + ' → ' + (b && b.model_id ? b.model_id + ' (' + (b.provider_name || b.provider_id) + ')' : '未绑定');
    };
    const pairKey = (p, m) => (p && m ? p + '::' + m : '');
    const syncSelectOptions = (el, opts, curSig, selectedVal) => {
      const sig = JSON.stringify(opts);
      if (sig !== curSig) {
        el.textContent = '';
        for (const item of opts) {
          const opt = document.createElement('option');
          opt.value = item.value;
          opt.textContent = item.label;
          el.append(opt);
        }
      }
      if (selectedVal && Array.from(el.options).some(o => o.value === selectedVal)) {
        el.value = selectedVal;
      }
      return sig;
    };

    const hasCatalogApi = typeof bridge?.primary_model_mode === 'string';
    const primaryMode = bridge?.primary_model_mode === 'fixed' ? 'fixed' : 'slot';
    const primarySlot = bridge?.primary_function_type || 'CHAT';
    const primaryModeSel = $('storyPrimaryMode');
    const primaryTargetSel = $('storyPrimaryTarget');
    if ($('storyPrimaryBadge')) $('storyPrimaryBadge').textContent = primaryMode === 'fixed' ? '专属固定' : primarySlot + ' 槽';
    if (primaryModeSel) {
      primaryModeSel.disabled = !!sessionBusy || !hasCatalogApi;
      primaryModeSel.value = primaryMode;
    }
    if (primaryTargetSel) {
      if ($('storyPrimaryTargetLabel')) {
        $('storyPrimaryTargetLabel').textContent = primaryMode === 'fixed' ? '故事专属主模型' : '主模型跟随的 Operit 功能槽';
      }
      const primaryOpts = primaryMode === 'fixed'
        ? availModels.map(m => ({ value: pairKey(m.provider_id, m.model_id), label: m.model_id + ' · ' + m.provider_name }))
        : Array.from(new Set([...BRIDGE_PRIMARY_SLOTS, ...funcBindings.map(b => b.function_type)]))
            .map(slot => ({ value: slot, label: slotOptionText(slot) }));
      const selectedPrimaryVal = primaryMode === 'fixed'
        ? pairKey(snapshot?.bridge_model?.provider_id, snapshot?.bridge_model?.model_id)
        : primarySlot;
      if (!primaryOpts.length) {
        primaryOpts.push({ value: '', label: hasCatalogApi ? '未检测到 Operit 已配置模型' : '升级 v2.1.0 桥接插件后可选' });
      }
      bridgePrimaryTargetSig = syncSelectOptions(primaryTargetSel, primaryOpts, bridgePrimaryTargetSig, selectedPrimaryVal);
      primaryTargetSel.disabled = !!sessionBusy || !hasCatalogApi || !primaryOpts[0].value;
    }
    if ($('storyPrimaryStatus')) {
      const bm = snapshot?.bridge_model;
      $('storyPrimaryStatus').textContent = !bridge?.present ? '桥接未连接，请在 Operit 开启故事桥接。'
        : !hasCatalogApi ? '导入 v2.1.0 故事桥接插件后，可在此与 Operit 插件设置页双端切换主/副模型。'
        : bm ? '当前主模型：' + bm.model_id + ' · ' + bm.provider_name + (primaryMode === 'fixed' ? '（仅故事生效，不改 Operit 主聊天）' : '（跟随 ' + primarySlot + ' 功能槽）')
        : '主模型未解析，请检查 Operit 模型配置。';
    }

    const dualSel = $('storyDualStage');
    const hasDualFlag = typeof bridge?.dual_stage === 'boolean';
    const isDual = bridge?.dual_stage !== false;
    if ($('storyDualBadge')) $('storyDualBadge').textContent = isDual ? '双阶段流式' : '单阶段精简';
    if (dualSel) {
      dualSel.disabled = !!sessionBusy || !hasDualFlag;
      dualSel.value = isDual ? 'dual' : 'single';
    }
    if ($('storySettlementControls')) $('storySettlementControls').hidden = !isDual;

    const settleSlot = bridge?.settlement_function_type || 'SUMMARY';
    const settleSlotSel = $('storySettlementSlot');
    if (settleSlotSel) {
      const slotOpts = Array.from(new Set([...BRIDGE_BASE_SLOTS, ...funcBindings.map(b => b.function_type)]))
        .map(slot => ({ value: slot, label: slotOptionText(slot) }));
      bridgeSettleSlotSig = syncSelectOptions(settleSlotSel, slotOpts, bridgeSettleSlotSig, settleSlot);
      settleSlotSel.disabled = !!sessionBusy || !hasDualFlag;
    }
    const bindModelSel = $('storyBindSlotModel');
    const bindBtn = $('storyBindSlotBtn');
    if ($('storyBindSlotLabel')) $('storyBindSlotLabel').textContent = '直接修改「' + settleSlot + '」槽绑定的模型';
    if (bindModelSel) {
      const modelOpts = availModels.length
        ? availModels.map(m => ({ value: pairKey(m.provider_id, m.model_id), label: m.model_id + ' · ' + m.provider_name }))
        : [{ value: '', label: hasCatalogApi ? '未检测到 Operit 已配置模型' : '升级 v2.1.0 桥接插件后可改绑' }];
      const curBinding = bindingBySlot.get(settleSlot);
      const curBindPair = curBinding ? pairKey(curBinding.provider_id, curBinding.model_id) : '';
      const syncMarker = settleSlot + '|' + curBindPair;
      const shouldResetVal = bridgeBindSyncedKey !== syncMarker;
      bridgeBindModelSig = syncSelectOptions(bindModelSel, modelOpts, bridgeBindModelSig, shouldResetVal ? curBindPair : '');
      if (shouldResetVal && curBindPair) bridgeBindSyncedKey = syncMarker;
      else if (shouldResetVal && !curBindPair) bridgeBindSyncedKey = syncMarker;
      bindModelSel.disabled = !!sessionBusy || !hasCatalogApi || !availModels.length;
      if (bindBtn) bindBtn.disabled = !!sessionBusy || !hasCatalogApi || !availModels.length || !bindModelSel.value;
    }
    const settleThinkMode = ['auto', 'off', 'on'].includes(bridge?.settlement_thinking_mode)
      ? bridge.settlement_thinking_mode
      : (bridge?.settlement_thinking ? 'on' : 'auto');
    const thinkSel = $('storySettlementThinkingMode');
    if (thinkSel) {
      thinkSel.value = settleThinkMode;
      thinkSel.disabled = !!sessionBusy || !hasCatalogApi;
    }

    const settleEl = $('storySettlementStatus');
    if (settleEl) {
      if (!bridge?.present) settleEl.textContent = '桥接未连接，请在 Operit 开启故事桥接。';
      else if (!hasDualFlag) settleEl.textContent = '导入 v2.1.4 故事桥接插件后可启用双阶段流式与副模型后台结算。';
      else if (!isDual) settleEl.textContent = '当前使用单阶段精简模式（v2 前缀缓存，单次返回完整 JSON）。';
      else {
        const sm = bridge.settlement_model;
        const thinkLabel = settleThinkMode === 'auto' ? '·智能思考' : settleThinkMode === 'on' ? '·深度思考' : '·非思考';
        settleEl.textContent = '当前副模型(' + settleSlot + thinkLabel + ')：'
          + (sm ? sm.model_id + ' · ' + sm.provider_name : '未绑定')
          + (bridge.settlement_fallback ? '（未单独绑定，已自动回退主功能槽）' : '');
      }
    }

    updateHudVitals();
    updateStageCurtain();
  }

  function showPortrait(name, file = '') {
    if (!hasCharacterPortrait(name)) {
      openGazeLens(name, { isHold: false });
      return;
    }
    const meta = CHAR_META[name] || { role: '' };
    const slots = getCharacterSlots(name);
    const requestedSlot = file ? String(file).replace(/\.[a-z0-9]+$/i, '') : '';
    const resolved = resolveCharacterAsset(name, requestedSlot ? { slot: requestedSlot } : {});
    const activeSlot = resolved?.slot || Object.keys(slots)[0] || 'into';
    const targetSrc = resolved?.url || slots[activeSlot] || image(name, 'into.png');

    portraitName = name;
    $('portraitName').textContent = name;
    $('portraitRole').textContent = [meta.role, resolved?.label].filter(Boolean).join(' · ');
    const img = $('portrait');
    const loader = $('portraitLoader');
    img.classList.remove('is-loaded');
    loader.classList.remove('is-done');
    img.onload = () => {
      img.classList.add('is-loaded');
      loader.classList.add('is-done');
    };
    img.onerror = () => {
      loader.classList.add('is-done');
    };
    img.src = targetSrc;
    img.alt = name + '立绘';
    if (img.complete && img.naturalWidth) {
      img.classList.add('is-loaded');
      loader.classList.add('is-done');
    }

    const outfitsEl = $('portraitOutfits');
    if (outfitsEl) {
      const ordered = VISUAL_SLOT_ORDER.filter(k => slots[k]);
      for (const k of Object.keys(slots)) {
        if (!ordered.includes(k)) ordered.push(k);
      }
      outfitsEl.replaceChildren(...ordered.map(slotKey => {
        const b = node('button', '', VISUAL_SLOT_LABELS[slotKey] || slotKey);
        b.type = 'button';
        b.dataset.file = slotKey;
        b.setAttribute('aria-pressed', String(slotKey === activeSlot));
        b.onclick = () => { haptic(8); showPortrait(name, slotKey); };
        return b;
      }));
    }
    if (!$('portraitDialog').open) $('portraitDialog').showModal();
  }

  function updateSpeakingUI() {
    document.querySelectorAll('#messages .msg.is-speaking').forEach(el => {
      el.classList.remove('is-speaking');
      el.querySelector('.speaking-wave')?.remove();
    });
    if (!isSpeaking || !speakingMessageId) return;
    const escaped = window.CSS && CSS.escape ? CSS.escape(speakingMessageId) : speakingMessageId.replace(/"/g, '\\"');
    const activeEl = $('messages')?.querySelector('.msg[data-message-id="' + escaped + '"]');
    if (!activeEl) return;
    activeEl.classList.add('is-speaking');
    const heading = activeEl.querySelector('.message-heading') || activeEl.querySelector('.narration-mark');
    if (heading && !heading.querySelector('.speaking-wave')) {
      const wave = node('span', 'speaking-wave');
      wave.setAttribute('aria-hidden', 'true');
      wave.append(node('i'), node('i'), node('i'));
      const anchor = heading.querySelector(':scope > .msg-head-actions') || heading.querySelector(':scope > .msg-replay-btn');
      if (anchor) heading.insertBefore(wave, anchor);
      else heading.append(wave);
    }
  }

  function cancelPrefetch() {
    if (prefetchTimer !== null) {
      clearTimeout(prefetchTimer);
      prefetchTimer = null;
    }
    VoiceClient.cancel('prefetch');
  }

  function stopVoice() {
    audioSerial++;
    isSpeaking = false;
    speakingMessageId = '';
    if (activeStream) {
      activeStream.dispose();
      activeStream = null;
    }
    VoiceClient.cancel('live');
    cancelPrefetch();
    $('audio').pause();
    $('audio').onended = null;
    audioStatus = '';
    updateSpeakingUI();
  }

  const VOICED_SPEAKERS = new Set(['沈知韫', '苏婉青', '徐念薇']);

  function resolveVoiceSpeaker(m) {
    if (!m || !String(m.text || '').trim()) return '';
    if (m.kind === 'narration') return '旁白';
    if (m.kind === 'dialogue') return VOICED_SPEAKERS.has(m.speaker) ? m.speaker : '';
    if (m.kind === 'action') return VOICED_SPEAKERS.has(m.speaker) ? '旁白' : '';
    return '';
  }

  function invalidateVoiceConfig() {
    configPromise = null;
    fishKeyStatusPromise = null;
    fishKeyConfigured = null;
  }

  function loadVoiceConfig() {
    configPromise = configPromise || VoiceClient.requestJson('/api/config?t=' + Date.now(), { cache: 'no-store' }).catch(e => {
      configPromise = null;
      throw e;
    });
    return configPromise;
  }

  async function ensureFishKeyReady() {
    if (typeof fishKeyConfigured === 'boolean') return fishKeyConfigured;
    fishKeyStatusPromise = fishKeyStatusPromise || VoiceClient.getFishKeyStatus()
      .then(st => {
        fishKeyConfigured = !!(st && st.configured);
        return fishKeyConfigured;
      })
      .catch(() => {
        fishKeyStatusPromise = null;
        return false;
      });
    return fishKeyStatusPromise;
  }

  function schedulePrefetch(m, id) {
    cancelPrefetch();
    if (!m || !id || !cache.voice || !gesture || document.hidden) return;
    const who = resolveVoiceSpeaker(m);
    if (!who) return;
    const existing = audioCache.get(id);
    if (existing && urls.has(existing)) return;
    const serial = audioSerial;
    prefetchTimer = setTimeout(async () => {
      prefetchTimer = null;
      if (serial !== audioSerial || !cache.voice || !gesture || document.hidden) return;
      try {
        const config = await loadVoiceConfig();
        if (serial !== audioSerial || !cache.voice || document.hidden) return;
        const cfg = config[who];
        if (!cfg || !cfg.voice) return;
        if (!String(cfg.voice).startsWith('edge:') && !(await ensureFishKeyReady())) return;
        const payload = VoiceClient.buildPayload(stripSubtextForTts(m.text), cfg, config.__settings__ || {}, '', who);
        const blob = await VoiceClient.requestAudio(payload, { channel: 'prefetch', maxBytes: 16 * 1024 * 1024 });
        if (!cache.voice || document.hidden) return;
        const blobUrl = urls.add(blob);
        audioCache.set(id, blobUrl);
        for (const [key, value] of audioCache) if (!urls.has(value)) audioCache.delete(key);
      } catch (_) {}
    }, 250);
  }

  function schedulePrefetchWindow(messages, idPrefix, startIndex = 0) {
    if (!Array.isArray(messages) || !messages.length || !cache.voice || document.hidden) return;
    if (fishKeyConfigured === false) return;
    const voiced = [];
    for (let i = Math.max(0, startIndex); i < messages.length && voiced.length < 3; i++) {
      const m = messages[i];
      const who = resolveVoiceSpeaker(m);
      if (who) voiced.push({ m, who, idx: i, id: idPrefix + ':' + i });
    }
    if (!voiced.length) return;
    void ensureFishKeyReady().then(ok => {
      if (!ok || !cache.voice || document.hidden) return;
      if (typeof VoiceClient.prefetchBatch === 'function') {
        void VoiceClient.prefetchBatch(voiced.map(v => ({
          text: stripSubtextForTts(v.m.text),
          speaker: v.who
        })));
      }
      if (gesture) {
        schedulePrefetch(voiced[0].m, voiced[0].id);
      }
    });
  }

  function unlock() {
    if (gesture) return;
    gesture = true;
    $('audio').src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    const result = $('audio').play();
    if (result?.catch) result.catch(() => {});
  }

  async function speak(m, id) {
    stopVoice();
    const who = resolveVoiceSpeaker(m);
    if (!who) {
      audioMessage = null;
      audioStatus = '';
      controls();
      return;
    }
    audioMessage = { m, id };
    if (!cache.voice || !gesture) {
      controls();
      return;
    }
    const serial = audioSerial;
    audioStatus = '合成语音中…';
    controls();
    const bindEnded = () => {
      $('audio').onended = () => {
        if (serial === audioSerial) {
          isSpeaking = false;
          speakingMessageId = '';
          audioStatus = '已播完';
          updateSpeakingUI();
          controls();
        }
      };
    };
    const playBuffered = async payload => {
      const blob = await VoiceClient.requestAudio(payload, { channel: 'live', maxBytes: 16 * 1024 * 1024 });
      if (serial !== audioSerial || !cache.voice || document.hidden) return;
      const blobUrl = urls.add(blob);
      audioCache.set(id, blobUrl);
      for (const [key, value] of audioCache) if (!urls.has(value)) audioCache.delete(key);
      urls.pin(blobUrl);
      $('audio').src = blobUrl;
      bindEnded();
      await $('audio').play();
      if (serial !== audioSerial) return;
      isSpeaking = true;
      speakingMessageId = id;
      audioStatus = '朗读中';
      updateSpeakingUI();
    };
    try {
      const cachedUrl = audioCache.get(id);
      if (cachedUrl && urls.has(cachedUrl)) {
        if (serial !== audioSerial || !cache.voice || document.hidden) return;
        urls.pin(cachedUrl);
        $('audio').src = cachedUrl;
        bindEnded();
        await $('audio').play();
        if (serial !== audioSerial) return;
        isSpeaking = true;
        speakingMessageId = id;
        audioStatus = '朗读中';
        updateSpeakingUI();
      } else {
        const config = await loadVoiceConfig();
        if (serial !== audioSerial || !cache.voice || document.hidden) return;
        const cfg = config[who];
        if (!cfg || !cfg.voice) {
          audioStatus = '';
          controls();
          return;
        }
        if (!String(cfg.voice).startsWith('edge:') && !(await ensureFishKeyReady())) {
          audioStatus = '未配置语音密钥';
          if (!fishMissingToastShown) {
            fishMissingToastShown = true;
            toast('尚未配置 Fish 语音密钥，当前静默演播');
          }
          controls();
          return;
        }
        const payload = VoiceClient.buildPayload(stripSubtextForTts(m.text), cfg, config.__settings__ || {}, '', who);
        let streamStarted = false;
        const stream = await VoiceClient.requestStream(payload, {
          channel: 'live',
          onReady: () => {
            if (serial !== audioSerial) return;
            streamStarted = true;
            isSpeaking = true;
            speakingMessageId = id;
            audioStatus = '流式朗读中';
            updateSpeakingUI();
            controls();
          }
        });
        if (stream) {
          if (serial !== audioSerial || !cache.voice || document.hidden) {
            stream.dispose();
            return;
          }
          activeStream = stream;
          $('audio').src = stream.url;
          bindEnded();
          try {
            await Promise.all([$('audio').play(), stream.done]);
            if (serial === audioSerial && !streamStarted && !$('audio').paused) {
              isSpeaking = true;
              speakingMessageId = id;
              audioStatus = '朗读中';
              updateSpeakingUI();
            }
          } catch (streamErr) {
            if (serial !== audioSerial) return;
            if (activeStream === stream) { stream.dispose(); activeStream = null; }
            const noRetryStatus = streamErr?.status >= 400 && streamErr?.status < 600;
            if (!streamStarted && !noRetryStatus && streamErr?.name !== 'AbortError' && streamErr?.name !== 'NotAllowedError') {
              await playBuffered(payload);
            } else {
              throw streamErr;
            }
          }
        } else {
          await playBuffered(payload);
        }
      }
    } catch (e) {
      isSpeaking = false;
      speakingMessageId = '';
      updateSpeakingUI();
      if (serial === audioSerial && e?.name !== 'AbortError') {
        audioStatus = e?.name === 'NotAllowedError' ? '点“启用语音”继续听读' : (e?.status === 503 ? '请在系统设置配置 Fish 密钥' : '语音暂不可用');
      }
    }
    controls();
  }

  function isWhisperLine(rawText) {
    const s = String(rawText || '');
    return /\[(?:[^\]]*(?:\b(?:whisper|softly|breathy|murmur|sigh|hushed|intimate|trembling)\b|低声|耳语|轻声|气音|压低声音)[^\]]*)\]/i.test(s)
      || /<(?:whisper|soft)>/i.test(s);
  }

  function classifyVoiceTag(rawTag) {
    const t = String(rawTag || '').toLowerCase();
    if (/trembl|shaky|quiver|voice\s+breaks|颤|抖/.test(t)) {
      return { cls: 'fx-tremble', label: '声线微颤', mood: 'tremble' };
    }
    if (/exhaust|sobbing|weak|faint|dazed|out\s+of\s+breath|失力|虚弱|余韵|泣|哽咽/.test(t)) {
      return { cls: 'fx-exhausted', label: '失力余韵', mood: 'exhausted' };
    }
    if (/catch|choke|gasp|inhale|pant|hold(?:ing)?\s+back|short\s+breath|屏息|抽气|急促|喘/.test(t)) {
      return { cls: 'fx-catch', label: '呼吸急顿', mood: 'catch' };
    }
    if (/whisper|breathy|softly|murmur|hushed|intimate|sigh|耳语|气音|低语|轻声|叹息/.test(t)) {
      return { cls: 'fx-whisper', label: '微距气音', mood: 'whisper' };
    }
    if (/calm|executive|cold|restrained|firm|low\s+voice|composed|克制|冷冽|沉稳|压低/.test(t)) {
      return { cls: 'fx-restrained', label: '冷冽克制', mood: 'restrained' };
    }
    return null;
  }

  const SENSORY_TOKEN_RE = /((?:嗯|啊|唔|哈啊|嘶|呜|唔嗯)[…~～。.、！!]+|湿透|濡湿|泥泞|蜜汁|爱液|滑腻|水声|粘腻|黏腻|滚烫|余温|痉挛|抽搐|战栗|轻颤|发软|蜷起|失焦|绷紧|耳根|耳垂|后颈|颈侧|锁骨|腰窝|腕骨|指节|脚踝|脊背|肩头|鼻息|体温|发梢|唇瓣|眼尾|指尖)/g;
  const MOAN_PREFIX_RE = /^(?:嗯|啊|唔|哈啊|嘶|呜|唔嗯)[…~～。.、！!]+$/;
  const FLUID_TOKEN_RE = /^(?:湿透|濡湿|泥泞|蜜汁|爱液|滑腻|水声|粘腻|黏腻|滚烫|余温)$/;
  const SPASM_TOKEN_RE = /^(?:痉挛|抽搐|战栗|轻颤|发软|蜷起|失焦|绷紧)$/;

  function appendEnrichedSegment(target, segText, kind, charStats, anchorState) {
    if (!segText) return;
    const highArousal = (charStats?.desire ?? 0) >= 65 || (charStats?.orgasm ?? 0) >= 50 || Boolean(charStats?.hasFluidLock);
    const parts = String(segText).split(SENSORY_TOKEN_RE);
    for (const part of parts) {
      if (!part) continue;
      if (MOAN_PREFIX_RE.test(part) && (highArousal || (kind === 'dialogue' && /[…~～]/.test(part)))) {
        target.append(node('span', 'fx-moan', part));
      } else if (FLUID_TOKEN_RE.test(part) && highArousal) {
        target.append(node('span', 'fx-fluid', part));
      } else if (SPASM_TOKEN_RE.test(part) && highArousal) {
        target.append(node('span', 'fx-spasm', part));
      } else if (SENSORY_TOKEN_RE.test(part) && !MOAN_PREFIX_RE.test(part) && anchorState.count < 3) {
        SENSORY_TOKEN_RE.lastIndex = 0;
        anchorState.count += 1;
        target.append(node('span', 'sensory-anchor', part));
      } else {
        SENSORY_TOKEN_RE.lastIndex = 0;
        target.append(document.createTextNode(part));
      }
      SENSORY_TOKEN_RE.lastIndex = 0;
    }
  }

  function appendNpcRichText(container, rawText, speaker, kind, charStats) {
    const raw = String(rawText || '');
    const tagMatches = [...raw.matchAll(/\[([^\]\r\n]+)\]/g)];
    const moods = [];
    const seenMoods = new Set();
    let primaryCls = '';

    for (const m of tagMatches) {
      const info = classifyVoiceTag(m[1]);
      if (info && !seenMoods.has(info.mood)) {
        seenMoods.add(info.mood);
        moods.push(info);
        if (!primaryCls) primaryCls = info.cls;
      }
    }

    if (moods.length > 0 && (kind === 'dialogue' || kind === 'action')) {
      const pillWrap = node('span', 'voice-mood-strip');
      for (const m of moods.slice(0, 2)) {
        const pill = node('span', 'voice-mood-tag', m.label);
        pill.dataset.mood = m.mood;
        pillWrap.append(pill);
      }
      container.append(pillWrap);
    }

    const cleaned = raw
      .replace(/\[[a-zA-Z][a-zA-Z0-9_,\s-]{0,79}\]/g, '')
      .replace(/<\/?(?:whisper|emphasis|soft|fast|slow|stress|forceful|chinese|english|japanese|korean|cantonese|french|german|spanish)>/gi, '')
      .replace(/<\|phoneme_start\|>[^<\r\n]{1,40}<\|phoneme_end\|>/g, '')
      .replace(/<\|[^|\r\n]+\|>/g, '')
      .trim();

    const bodySpan = node('span', 'npc-prose-body' + (primaryCls ? (' ' + primaryCls) : ''));
    const anchorState = { count: 0 };
    const subtextParts = cleaned.split(/([｛{][^｜|}\r\n]+[｜|][^｝}\r\n]+[｝}])/g);

    for (const chunk of subtextParts) {
      if (!chunk) continue;
      const subMatch = /^[｛{]([^｜|}\r\n]+)[｜|]([^｝}\r\n]+)[｝}]$/.exec(chunk);
      if (subMatch) {
        const ruby = node('ruby', 'subtext-ruby');
        ruby.append(
          node('span', 'subtext-surface', subMatch[1].trim()),
          node('rt', 'subtext-rt', subMatch[2].trim())
        );
        bodySpan.append(ruby);
      } else {
        appendEnrichedSegment(bodySpan, chunk, kind, charStats, anchorState);
      }
    }
    container.append(bodySpan);
  }

  function appendPlayerRichText(container, rawText) {
    const parts = String(rawText || '').split(/([（(][^）)]+[）)])/g);
    for (const part of parts) {
      if (!part) continue;
      if (/^[（(].+[）)]$/.test(part)) {
        container.append(node('span', 'player-bracket', part));
      } else {
        container.append(document.createTextNode(part));
      }
    }
  }

  function quoteLineToInput(speaker, rawText) {
    const clean = stripVoiceTags(rawText || '').trim().replace(/\s+/g, ' ');
    const snippet = clean.length > 22 ? (clean.slice(0, 22) + '…') : clean;
    const inp = $('input');
    if (!inp) return;
    haptic(8);
    if (deckCollapsed) {
      deckCollapsed = false;
      controls();
      sizing();
    }
    inp.value = '（我看向' + speaker + '）「' + snippet + '」——';
    cache.draft = inp.value;
    save();
    inp.focus();
    controls();
    sizing();
    toast('已引用' + speaker + '的台词至输入框');
  }

  function buildScenePlate(loc, still, clockStr, turnId) {
    const btn = node('button', 'cinema-plate is-scene');
    btn.type = 'button';
    btn.dataset.plateId = 'scene:' + turnId + ':' + loc;
    const frame = node('div', 'cinema-plate-frame');
    const im = node('img', 'cinema-plate-img');
    im.src = still.url;
    im.alt = loc + '场景空镜';
    im.decoding = 'async';
    const tag = node('span', 'cinema-plate-tag', '场景空镜');
    const cap = node('div', 'cinema-plate-caption');
    const titles = node('div', 'cinema-plate-titles');
    titles.append(node('strong', '', loc), node('span', '', clockStr || '当前空间坐标'));
    cap.append(titles, node('span', 'cinema-plate-hint', '空镜 ↗'));
    frame.append(im, node('div', 'cinema-plate-scrim'), tag, cap);
    btn.append(frame);
    btn.onclick = ev => {
      ev.stopPropagation();
      haptic(8);
      openSceneLens(loc);
    };
    return btn;
  }

  function buildCharPlate(speaker, asset, subText, turnId) {
    const btn = node('button', 'cinema-plate is-char');
    btn.type = 'button';
    btn.dataset.plateId = 'char:' + turnId + ':' + speaker + ':' + asset.slot;
    const frame = node('div', 'cinema-plate-frame');
    const im = node('img', 'cinema-plate-img');
    im.src = asset.url;
    im.alt = speaker + '剧照';
    im.style.objectPosition = asset.pos || '50% 18%';
    im.decoding = 'async';
    const tag = node('span', 'cinema-plate-tag', asset.label || '登场定格');
    const cap = node('div', 'cinema-plate-caption');
    const titles = node('div', 'cinema-plate-titles');
    titles.append(node('strong', '', speaker), node('span', '', subText || (CHAR_META[speaker]?.role || '同席聚焦')));
    cap.append(titles, node('span', 'cinema-plate-hint', '按住/轻触细赏'));
    frame.append(im, node('div', 'cinema-plate-scrim'), tag, cap);
    btn.append(frame);
    bindHoldGaze(btn, speaker, { slot: asset.slot });
    return btn;
  }

  function entry(kind, speaker, text, id, opts = {}) {
    const isPlayer = speaker === '徐志北';
    const isNpcAction = !isPlayer && kind === 'action';
    const whisper = !isPlayer && kind === 'dialogue' && isWhisperLine(text);
    const charHasImg = Boolean(speaker && (kind === 'dialogue' || kind === 'action') && hasCharacterPortrait(speaker));
    const noAvatarCls = (!isPlayer && (kind === 'dialogue' || kind === 'action') && !charHasImg) ? ' no-avatar' : '';
    const focusHero = (!isPlayer && kind === 'narration') ? primaryPortraitHero(snapshot?.world) : '';
    const isLiveTurn = !opts.inHistory && !opts.isHistoricTurn;
    const cStats = (isLiveTurn && !isPlayer && speaker && PEOPLE.includes(speaker))
      ? getLiveCharStats(speaker)
      : (isLiveTurn && focusHero ? getLiveCharStats(focusHero) : null);
    const el = node(
      'article',
      'msg ' + kind + (isPlayer ? ' player' : '') + noAvatarCls + (whisper ? ' is-whisper' : '') + (opts.isPreview ? ' is-preview' : '')
    );
    el.dataset.messageId = id;
    el.dataset.renderKey = 'msg:' + id;
    el.dataset.msgTextSig = kind + '|' + (speaker || '') + '|' + String(text || '').slice(0, 120) + '|' + String(text || '').length;
    if (speaker) el.dataset.speaker = speaker;
    if (cStats && isLiveTurn) {
      if (cStats.desire >= 85 || cStats.orgasm >= 75 || cStats.hasFluidLock) el.dataset.arousal = 'peak';
      else if (cStats.desire >= 70 || cStats.orgasm >= 50) el.dataset.arousal = 'high';
      if (cStats.stamina <= 15) el.dataset.defense = 'blackout';
      else if (cStats.shame < 40) el.dataset.defense = 'melted';
      else if (cStats.shame > 80) el.dataset.defense = 'guarded';
    }
    el.setAttribute('aria-label', kind === 'narration' ? '旁白' : speaker + (kind === 'action' ? '的动作' : '的对白'));

    if (kind === 'narration') {
      if (opts.showNarrationMark !== false || opts.previewTag) {
        const mark = node('div', 'narration-mark');
        const diamond = svgEl('svg', { viewBox: '0 0 12 12', class: 'narration-diamond', 'aria-hidden': 'true' });
        diamond.append(svgEl('path', { d: 'M6 1 11 6 6 11 1 6Z', fill: 'currentColor' }));
        mark.append(diamond, node('span', '', '旁白'), diamond.cloneNode(true));
        if (opts.previewTag) mark.append(node('span', 'stream-preview-tag', opts.previewTag));
        el.append(mark);
      }
    } else if (kind === 'handoff') {
      const h = node('div', 'message-heading');
      h.append(icon('scroll', 'chip-svg'), node('span', '', speaker));
      el.append(h);
    } else {
      if (charHasImg && !isNpcAction) {
        const im = node('img', 'avatar');
        const thumb = resolveCharacterAsset(speaker, { slot: 'into' });
        im.src = thumb?.url || image(speaker, 'into.png');
        im.alt = '';
        im.decoding = 'async';
        im.onerror = () => {
          im.remove();
          if (!isPlayer) el.classList.add('no-avatar');
        };
        if (!isPlayer) {
          im.style.cursor = 'pointer';
          bindHoldGaze(im, speaker, { whisper });
        }
        el.append(im);
      }
      const h = node('div', isNpcAction ? 'message-heading action-heading' : 'message-heading');
      if (isNpcAction) {
        if (charHasImg) {
          const mini = node('img', 'action-mini-avatar');
          const thumb = resolveCharacterAsset(speaker, { slot: 'into' });
          mini.src = thumb?.url || image(speaker, 'into.png');
          mini.alt = '';
          mini.decoding = 'async';
          mini.style.cursor = 'pointer';
          mini.onerror = () => mini.remove();
          if (!opts.inHistory) bindHoldGaze(mini, speaker, { whisper: false });
          h.append(mini);
        } else {
          h.append(node('span', 'action-dot'));
        }
      }
      const nameSpan = node('span', 'msg-speaker-name', speaker);
      if (!isPlayer && !opts.inHistory) {
        nameSpan.style.cursor = 'pointer';
        bindHoldGaze(nameSpan, speaker, { whisper });
      }
      h.append(nameSpan);
      if (kind === 'action') h.append(node('span', 'kind-label', '动作'));
      if (whisper) h.append(node('span', 'whisper-pill', '耳语'));
      if (cStats && !opts.inHistory) {
        if (cStats.pregnant) {
          h.append(node('span', 'micro-state-chip is-pregnant', '孕期敏感'));
        } else if (cStats.phys?.pregnancy_stage === 'latent') {
          h.append(node('span', 'micro-state-chip is-latent', '早孕微兆'));
        } else if (cStats.phys?.cycle_phase === '危险期' && (cStats.desire >= 45 || cStats.hasFluidLock)) {
          h.append(node('span', 'micro-state-chip is-danger', '危险期'));
        }
        if (cStats.stamina <= 15) {
          h.append(node('span', 'micro-state-chip is-alert', '生理断电'));
        } else if (cStats.hasFluidLock) {
          h.append(node('span', 'micro-state-chip is-desire', '体液锁定'));
        }
        if (cStats.orgasm >= 50) {
          h.append(node('span', 'micro-state-chip is-climax', `高潮 ${cStats.orgasm}%`));
        }
        if (cStats.phys?.masturbation_trace > 0) {
          h.append(node('span', 'micro-state-chip is-tension', '自渎余韵'));
        } else if (cStats.phys?.unrelieved_streak >= 1) {
          h.append(node('span', 'micro-state-chip is-desire', '欲求未平'));
        }
        if (cStats.micro.residual_tension) {
          h.append(node('span', 'micro-state-chip is-tension', '余韵未平'));
        } else if (cStats.micro.confusion_debt) {
          h.append(node('span', 'micro-state-chip is-confusion', '心绪失守'));
        } else if (cStats.micro.momentary_ease) {
          h.append(node('span', 'micro-state-chip is-ease', '戒备微松'));
        }
      }
      if (opts.previewTag) h.append(node('span', 'stream-preview-tag', opts.previewTag));
      if (!isPlayer && (kind === 'dialogue' || kind === 'action')) {
        const actions = node('span', 'msg-head-actions');
        if (resolveVoiceSpeaker({ kind, speaker, text })) {
          const replay = node('button', 'msg-replay-btn');
          replay.type = 'button';
          replay.setAttribute('aria-label', '重听本句语音');
          replay.title = '重听语音';
          replay.append(icon('volume', 'chip-svg'));
          replay.onclick = e => {
            e.stopPropagation();
            haptic(8);
            unlock();
            cache.voice = true;
            save();
            void speak({ kind, speaker, text }, id);
          };
          actions.append(replay);
        }

        if (kind === 'dialogue' && !opts.inHistory) {
          const quoteBtn = node('button', 'msg-micro-btn', '引用');
          quoteBtn.type = 'button';
          quoteBtn.title = '引用此句至输入框';
          quoteBtn.onclick = e => {
            e.stopPropagation();
            quoteLineToInput(speaker, text);
          };
          actions.append(quoteBtn);
        }

        if (kind === 'dialogue' && !opts.inHistory) {
          const gazeBtn = node('button', 'msg-micro-btn' + (charHasImg ? ' is-gaze' : ''), charHasImg ? '凝视 ◉' : '档案 ◈');
          gazeBtn.type = 'button';
          gazeBtn.title = charHasImg ? '按住凝视，轻触全幅细赏' : '按住或轻触查看人物档案';
          bindHoldGaze(gazeBtn, speaker, { whisper });
          actions.append(gazeBtn);
        }
        if (actions.childElementCount > 0) h.append(actions);
      }
      el.append(h);
    }

    const textEl = node('div', 'text');
    if (isPlayer) {
      appendPlayerRichText(textEl, text);
    } else {
      appendNpcRichText(textEl, text, speaker, kind, cStats);
    }
    el.append(textEl);
    return el;
  }

  function buildDiscoCheckBanners(turn, isLastTurn, w) {
    if (!turn || !isLastTurn || !w) return [];
    const cast = (w.cast || []).filter(n => PEOPLE.includes(n));
    if (!cast.length) return [];
    const speakersInTurn = new Set((turn.messages || []).map(m => m.speaker).filter(s => PEOPLE.includes(s)));
    const targets = speakersInTurn.size ? [...speakersInTurn] : cast.slice(0, 1);
    const changes = turn.settlement?.changes || [];
    const banners = [];

    for (const who of targets) {
      const st = getLiveCharStats(who);
      if (!st) continue;
      const charChanges = changes.filter(c => c.target === who);
      const hadShameDrop = charChanges.some(c => c.attribute === '羞耻' && c.delta < 0);
      const hadAffChange = charChanges.some(c => c.attribute === '好感');
      const hadStaDrop = charChanges.some(c => c.attribute === '体力' && c.delta < 0);

      if (st.passiveLv >= 1) {
        let insight = '';
        if (st.shame > 80) {
          insight = `${who}表面仍维持着矜持防线（羞耻 ${st.shame}），但微绷的肩线与视线停顿已被你的洞察之瞳捕捉。`;
        } else if (st.shame >= 40) {
          insight = `${who}的羞耻防线已现松动裂隙（羞耻 ${st.shame}），呼吸的细微凌乱比言辞更诚实。`;
        } else {
          insight = `${who}的心理防线近乎瓦解（羞耻 ${st.shame}），残存的客套只剩最后一层薄纱。`;
        }
        banners.push({
          tier: 'insight',
          badge: `洞察之瞳 Lv.${st.passiveLv} · 检定成功`,
          text: insight
        });
      }

      if (st.pregnant) {
        banners.push({
          tier: 'seep',
          badge: '孕期本能 · 防线坍缩',
          text: `${who}腹中已孕育着禁忌的骨血，孕期敏感与既成事实将羞耻上限压在低位（羞耻 ${st.shame} / 上限35）。`
        });
      } else if (st.phys?.pregnancy_stage === 'latent') {
        banners.push({
          tier: 'deception',
          badge: '生命微兆 · 潜伏着床',
          text: `${who}尚未知晓体内已悄然受孕，莫名的困倦与小腹微酸正悄然瓦解她的敏锐戒备。`
        });
      } else if (st.phys?.masturbation_trace > 0) {
        banners.push({
          tier: 'seep',
          badge: '暗中自渎 · 把柄余韵',
          text: `${who}独处时借你气息暗中泄欲的余韵尚未散尽，面对你的目光时耳根发烫、底气尽失。`
        });
      } else if (st.hasFluidLock) {
        banners.push({
          tier: 'seep',
          badge: '体液锁定 · 激素共振',
          text: `深处残留的滚烫体液正持续灼烧${who}的理智，欲望被强行锁在 ${st.phys?.fluid_lock_floor || 58} 底线之上（当前欲望 ${st.desire}）。`
        });
      } else if (st.passiveLv >= 2 && (hadShameDrop || (st.affection > 60 && st.shame < 65))) {
        const closedLoop = (st.affection > 60 && st.shame < 65 && !hadAffChange && hadShameDrop);
        banners.push({
          tier: 'deception',
          badge: closedLoop ? '认知欺诈 · 合理化闭环' : '认知欺诈滤镜 Lv.2 · 检定生效',
          text: closedLoop
            ? `${who}的潜意识自动启动自我保护合理化，越界未损分毫好感（好感 ${st.affection}）。`
            : `认知滤镜正在软化${who}的抵触情绪，越界带来的心理反扑被悄然折半。`
        });
      } else if (st.passiveLv >= 3 && (hadStaDrop || st.stamina <= 45)) {
        banners.push({
          tier: 'fatigue',
          badge: '疲劳诱导 Lv.3 · 躯体代偿',
          text: `交感神经高负荷紧绷正加倍抽空${who}的体力（当前体力 ${st.stamina} / 100）。`
        });
      } else if (st.shame < 40 && st.affection > 75) {
        banners.push({
          tier: 'seep',
          badge: '暗流渗漏 · 被动触发',
          text: `高好感（${st.affection}）穿透低羞耻防线，无声的情欲暗流正在${who}心底自动滋长（欲望 ${st.desire}）。`
        });
      }

      if (banners.length >= 2) break;
    }

    return banners.slice(0, 2).map(b => {
      const box = node('aside', 'disco-check-banner is-' + b.tier);
      const head = node('div', 'disco-check-head');
      head.append(icon('sparkle', 'chip-svg'), node('strong', '', '[' + b.badge + ']'));
      box.append(head, node('p', 'disco-check-text', b.text));
      return box;
    });
  }

  function timeline(filter = 'all', opts = {}) {
    const out = [];
    const includePlates = Boolean(opts.includePlates && filter === 'all' && prefs.cinemaPlates);
    const inHistory = Boolean(opts.inHistory);
    const w = snapshot?.world;
    let prevKind = '';
    let lastPlateLoc = '';
    const seenCharSlot = new Map();

    history.forEach((t, tIdx) => {
      const isLastTurn = tIdx === history.length - 1;
      const turnLoc = t.operation?.destination || t.location || (isLastTurn ? w?.location : '') || w?.location || '';
      const turnClock = t.settlement?.clock || (isLastTurn ? w?.progression?.runtime?.clock : null);
      const clockStr = turnClock ? formatGameClock(turnClock, isLastTurn ? (w?.weekday || '') : '') : '';

      if (includePlates && turnLoc && turnLoc !== lastPlateLoc) {
        const still = resolveSceneStill(turnLoc, turnClock?.time);
        if (still) {
          const sp = buildScenePlate(turnLoc, still, clockStr, t.id);
          sp.dataset.renderKey = 'splate:' + t.id + ':' + turnLoc;
          out.push(sp);
          prevKind = 'plate';
        }
        lastPlateLoc = turnLoc;
        seenCharSlot.clear();
      }

      if (filter === 'all' && t.selection?.option_id !== 'BEGIN') {
        out.push(entry(t.input_kind === 'action' ? 'action' : 'dialogue', '徐志北', t.input, t.id + ':input', { inHistory }));
        prevKind = 'player';
      }

      const turnMessages = (handoffPreview && handoffPreview.segmentId === t.id
        && handoffPreview.revealed > t.messages.length)
        ? handoffPreview.messages.slice(0, handoffPreview.revealed)
        : t.messages;
      const isHistoricTurn = inHistory || !isLastTurn;

      turnMessages.forEach((m, i) => {
        if (filter === 'settlement') return;
        if (filter === 'dialogue' && m.kind !== 'dialogue') return;

        if (includePlates && (m.kind === 'dialogue' || m.kind === 'action') && m.speaker && m.speaker !== '徐志北' && hasCharacterPortrait(m.speaker)) {
          const asset = resolveCharacterAsset(m.speaker, {
            location: turnLoc,
            time: turnClock?.time,
            whisper: m.kind === 'dialogue' && isWhisperLine(m.text),
            preferMood: isLastTurn
          });
          if (asset) {
            const prevSlot = seenCharSlot.get(m.speaker);
            const shouldInsert = !prevSlot || (isLastTurn && prevSlot !== asset.slot);
            if (shouldInsert) {
              const sub = [turnLoc, clockStr].filter(Boolean).join(' · ') || (CHAR_META[m.speaker]?.role || '');
              const cp = buildCharPlate(m.speaker, asset, sub, t.id + ':' + i);
              cp.dataset.renderKey = 'cplate:' + t.id + ':' + i + ':' + m.speaker + ':' + asset.slot;
              out.push(cp);
              seenCharSlot.set(m.speaker, asset.slot);
              prevKind = 'plate';
            }
          }
        }

        const showNarrationMark = m.kind !== 'narration' ? true : prevKind !== 'narration';
        out.push(entry(m.kind, m.speaker, m.text, t.id + ':' + i, { showNarrationMark, inHistory, isHistoricTurn }));
        prevKind = m.kind;
      });
      if (filter === 'all' && !inHistory && isLastTurn) {
        buildDiscoCheckBanners(t, isLastTurn, w).forEach((banner, bIdx) => {
          banner.dataset.renderKey = 'disco:' + t.id + ':' + bIdx;
          out.push(banner);
        });
      }
      if (filter === 'all' && t.handoff) {
        out.push(entry('handoff', '待处理', t.handoff, t.id + ':handoff', { inHistory }));
        prevKind = 'handoff';
      }
      if (t.settlement && (filter === 'settlement' || t.id !== snapshot?.playback?.segment_id)) {
        const sc = settlementCard(t.settlement, false);
        sc.dataset.renderKey = 'settle:' + t.id;
        out.push(sc);
        prevKind = 'settlement';
      }
    });

    if (filter === 'all' && hasPreviewNodes()) {
      const reqId = streamPreview.request_id;
      const task = snapshot?.task;
      if (task?.action && task.selection?.option_id !== 'BEGIN') {
        out.push(entry('action', '徐志北', task.action, 'preview:' + reqId + ':input', { isPreview: true, inHistory }));
        prevKind = 'player';
      }
      const visible = streamPreview.messages.slice(0, Math.max(1, streamPreview.revealed || 1));
      visible.forEach((m, i) => {
        const showNarrationMark = m.kind !== 'narration' ? true : prevKind !== 'narration';
        const isLast = i === visible.length - 1;
        const previewTag = isLast
          ? (streamPreview.stage === 'settling_retry' ? '校准中' : streamPreview.stage === 'settling' ? '结算中' : '流式预览')
          : '';
        out.push(entry(m.kind, m.speaker, m.text, 'preview:' + reqId + ':' + i, {
          showNarrationMark, isPreview: true, previewTag, inHistory
        }));
        prevKind = m.kind;
      });
    }
    return out;
  }

  function rewardIconFor(attr) {
    if (attr === '好感') return { icon: 'heart', cls: 'is-heart' };
    if (attr === '积分') return { icon: 'coin', cls: '' };
    if (attr === '经验值') return { icon: 'sparkle', cls: '' };
    if (attr === '体力') return { icon: 'energy', cls: '' };
    if (attr === '羞耻') return { icon: 'shield', cls: '' };
    if (attr === '欲望' || attr === '堕落') return { icon: 'flame', cls: 'is-heart' };
    return { icon: 'sparkle', cls: '' };
  }

  let svgGradUid = 0;

  function buildSettlementMeterSvg(before, after, refunded) {
    const b = Math.max(0, Math.min(100, Number(before) || 0));
    const a = Math.max(0, Math.min(100, Number(after) || 0));
    const ref = Math.max(0, Number(refunded) || 0);
    const gid = 'settleMeterGrad-' + (++svgGradUid);
    const svg = svgEl('svg', {
      viewBox: '0 0 240 14',
      class: 'settlement-svg-meter',
      role: 'meter',
      'aria-label': '结算后体力 ' + a + ' / 100',
      'aria-valuemin': '0',
      'aria-valuemax': '100',
      'aria-valuenow': String(a)
    });
    const defs = svgEl('defs');
    const grad = svgEl('linearGradient', { id: gid, x1: '0%', y1: '0%', x2: '100%', y2: '0%' });
    grad.append(
      svgEl('stop', { offset: '0%', 'stop-color': a < 20 ? '#d06161' : '#6db592' }),
      svgEl('stop', { offset: '100%', 'stop-color': a < 20 ? '#a83c3c' : '#f2daa9' })
    );
    defs.append(grad);
    svg.append(defs);

    const w = 236, ox = 2, y = 4, h = 6;
    svg.append(svgEl('rect', { x: ox, y, width: w, height: h, rx: 3, fill: 'var(--surface-3)' }));
    if (b > a) {
      svg.append(svgEl('rect', {
        x: ox, y, width: ((b / 100) * w).toFixed(1), height: h, rx: 3,
        fill: 'var(--gold)', 'fill-opacity': '0.2'
      }));
    }
    svg.append(svgEl('rect', {
      x: ox, y, width: Math.max(2, (a / 100) * w).toFixed(1), height: h, rx: 3,
      fill: 'url(#' + gid + ')'
    }));
    if (ref > 0 && a > 0) {
      const rw = Math.min(a, ref) / 100 * w;
      const rx = Math.max(ox, ox + (a / 100) * w - rw);
      svg.append(svgEl('rect', {
        x: rx.toFixed(1), y, width: rw.toFixed(1), height: h, rx: 3,
        fill: '#8be0b6', 'fill-opacity': '0.55'
      }));
    }
    for (const tick of [25, 50, 75]) {
      const tx = (ox + (tick / 100) * w).toFixed(1);
      svg.append(svgEl('line', { x1: tx, y1: y, x2: tx, y2: y + h, stroke: 'var(--bg)', 'stroke-width': '1', 'stroke-opacity': '0.55' }));
    }
    const markerX = (ox + (a / 100) * w).toFixed(1);
    svg.append(svgEl('circle', { cx: markerX, cy: y + h / 2, r: 3.4, fill: '#f6e2b8', stroke: 'var(--bg)', 'stroke-width': '1.2' }));
    return svg;
  }

  function settlementCard(s, foldable = false, dismissKey = '') {
    const isFolded = foldable && settlementFolded;
    const box = node('section', 'settlement-card game-settlement' + (s.phase === 'resting' ? ' resting' : s.sleep_completed ? ' rested' : '') + (isFolded ? '' : ' is-expanded'));
    const changes = s.changes || [];
    const rewards = changes.filter(c => c.target !== '系统宿主' || c.attribute !== '体力');

    const buildRewardPills = (cls, mini = false) => {
      const wrap = node('div', cls);
      rewards.slice(0, mini ? 3 : 6).forEach((c, idx) => {
        const meta = rewardIconFor(c.attribute);
        const tag = node('span', 'reward-pill ' + (mini ? 'is-mini ' : '') + (c.delta < 0 ? 'is-negative' : meta.cls));
        if (!mini) tag.style.animationDelay = (idx * 55) + 'ms';
        const who = c.target === '系统宿主' ? '' : c.target + ' ';
        tag.append(icon(meta.icon), node('span', '', who + c.attribute + ' ' + (c.delta > 0 ? '+' : '') + c.delta));
        wrap.append(tag);
      });
      return wrap;
    };

    const ribbon = node('div', 'settlement-ribbon');
    const left = node('div', 'settlement-ribbon-left');
    const mark = node('span', 'reward-mark');
    mark.append(icon(s.sleep_completed ? 'moon' : s.phase === 'resting' ? 'clock' : 'scales'));

    const shortTitle = s.sleep_completed ? '安稳醒来' : s.phase === 'resting' ? '体力已尽' : '已结算';
    const badgeText = s.kind === 'item' ? '道具恢复' : s.kind === 'rest' ? '免费休息' : '-' + s.net_cost + '⚡';
    left.append(mark, node('span', 'settlement-summary-title', shortTitle), node('span', 'settlement-badge', badgeText));

    const hasPendingReward = !!s.task_after?.pending_item;
    const makeTaskPills = (mini = false) => {
      const list = [];
      if (s.task_completed || hasPendingReward) {
        const btn = node('button', 'settlement-action-pill is-jade' + (mini ? ' is-mini' : ''));
        btn.type = 'button';
        btn.append(icon('gift'), node('span', '', s.task_completed ? '委托达成 · 领奖' : '待领委托奖励'));
        btn.onclick = () => openHub('bag');
        list.push(btn);
      }
      if (s.task_issued && s.task_after?.current) {
        const btn = node('button', 'settlement-action-pill' + (mini ? ' is-mini' : ''));
        btn.type = 'button';
        btn.append(icon('scroll'), node('span', '', '新委托：' + s.task_after.current.title));
        btn.onclick = () => openHub('bag');
        list.push(btn);
      }
      return list;
    };

    if (foldable && (rewards.length || s.task_completed || s.task_issued || hasPendingReward)) {
      const wrap = buildRewardPills('settlement-inline-pills', true);
      for (const pill of makeTaskPills(true)) wrap.append(pill);
      left.append(wrap);
    } else if (foldable) {
      const wrap = node('div', 'settlement-inline-pills');
      const stChip = node('span', 'reward-pill is-mini');
      stChip.append(icon('energy'), node('span', '', s.stamina_before + '→' + s.stamina_after));
      wrap.append(stChip);
      left.append(wrap);
    }

    const actions = node('div', 'settlement-actions');
    const body = node('div', 'settlement-body' + (isFolded ? ' is-folded' : ''));
    if (foldable) {
      const foldBtn = node('button', 'settlement-fold-btn', isFolded ? '明细 ▾' : '收起 ▴');
      foldBtn.type = 'button';
      foldBtn.onclick = () => {
        haptic(8);
        settlementFolded = !settlementFolded;
        body.classList.toggle('is-folded', settlementFolded);
        box.classList.toggle('is-expanded', !settlementFolded);
        foldBtn.textContent = settlementFolded ? '明细 ▾' : '收起 ▴';
        sizing();
      };
      const dismissBtn = node('button', 'settlement-dismiss-btn');
      dismissBtn.type = 'button';
      dismissBtn.setAttribute('aria-label', '关闭结算提示');
      dismissBtn.append(icon('close', 'chip-svg'));
      dismissBtn.onclick = () => {
        haptic(6);
        settlementDismissedId = dismissKey;
        $('settlement').hidden = true;
        sizing();
      };
      actions.append(foldBtn, dismissBtn);
    }
    ribbon.append(left, actions);
    box.append(ribbon);

    const balance = node('div', 'balance-line');
    const label = node('span', '');
    label.append(icon('energy', 'chip-svg'), node('span', '', '宿主体力'));
    balance.append(label, node('strong', '', s.stamina_before + ' → ' + s.stamina_after), node('span', 'balance-cap', '/ 100'));
    body.append(balance);

    body.append(buildSettlementMeterSvg(s.stamina_before, s.stamina_after, s.refunded));

    const fees = node('div', 'fee-line');
    for (const [key, value] of [['暂扣', s.reserved], ['返还', s.refunded], ['实耗', s.net_cost]]) {
      const part = node('span', '');
      part.append(node('small', '', key), node('b', '', String(value)));
      fees.append(part);
    }
    body.append(fees);

    const bodyTaskPills = makeTaskPills(false);
    if (rewards.length || bodyTaskPills.length) {
      const listEl = buildRewardPills('reward-list', false);
      for (const pill of bodyTaskPills) listEl.append(pill);
      body.append(listEl);
    }

    if (s.item) {
      const note = node('p', 'item-receipt');
      note.append(icon('bag', 'chip-svg'), node('span', '', s.item.name + ' × 1 · 恢复 ' + s.item.recovery + ' · 剩余额度 ' + s.item_budget));
      body.append(note);
    }
    if (s.closed_round) body.append(node('p', 'round-receipt', '记忆回合 ' + s.closed_round + ' 已收束入档'));
    if (s.phase === 'resting') body.append(node('p', 'round-receipt', '体力已低于阈值，请完成休整后再行动'));
    if (s.sleep_completed) body.append(node('p', 'round-receipt', '体力已恢复至满值 · 恢复道具额度已重置'));

    const detail = node('details', 'settlement-details');
    detail.append(node('summary', '', '展开本次明细 ▾'));
    for (const c of changes) {
      detail.append(node('p', '', c.target + ' · ' + c.attribute + ' ' + c.before + ' → ' + c.after + '（' + (c.delta > 0 ? '+' : '') + c.delta + '）'));
    }
    if (s.items_changed && !s.item) detail.append(node('p', '', '行囊库存已按实际增量更新'));
    if (s.task_after?.current) detail.append(node('p', '', '委托：' + s.task_after.current.title + ' · ' + s.task_after.current.status));
    if (s.task_after?.pending_item) detail.append(node('p', '', '待领奖励：' + s.task_after.pending_item));
    if (Array.isArray(s.schedule_moves) && s.schedule_moves.length) {
      for (const mv of s.schedule_moves) {
        const who = mv.target || mv.name || '';
        const loc = mv.to || mv.location || '';
        const rsn = mv.reason ? ('（' + mv.reason + '）') : '';
        if (who && loc) detail.append(node('p', '', '日程流转：' + who + ' → ' + loc + rsn));
      }
    }
    if (s.leverage_triggered) {
      const levName = typeof s.leverage_triggered === 'object' ? (s.leverage_triggered.intel_name || s.leverage_triggered.intel_id || '已生效') : String(s.leverage_triggered);
      detail.append(node('p', '', '商业杠杆触发：' + levName + '（好感惩罚减半）'));
    }
    if (Array.isArray(s.intel_consumed) && s.intel_consumed.length) {
      detail.append(node('p', '', '消耗情报：' + s.intel_consumed.join('、')));
    }
    if (s.clock) detail.append(node('p', '', '游戏时间：第' + s.clock.day + '天 ' + s.clock.time));
    if (s.events) {
      for (const value of Object.values(s.events)) {
        const tags = Array.isArray(value)
          ? value
          : Object.entries(value).flatMap(([who, values]) => values.map(tag => who + ' · ' + tag));
        if (tags.length) detail.append(node('p', 'muted', tags.join(' / ')));
      }
    }
    body.append(detail);
    box.append(body);
    return box;
  }

  function renderSettlement() {
    const box = $('settlement');
    const refund = snapshot?.task?.refund;
    const s = refund ? null : snapshot?.settlement;
    const key = s?.request_id || (refund ? snapshot.task.request_id + ':refund' : '');
    if (!key) {
      box.hidden = true;
      box.dataset.id = '';
      box.replaceChildren();
      return;
    }
    if (box.dataset.id === key) {
      box.hidden = settlementDismissedId === key;
      return;
    }
    box.dataset.id = key;
    settlementDismissedId = '';
    settlementFolded = true;
    box.hidden = false;
    box.replaceChildren();
    if (s) {
      box.append(settlementCard(s, true, key));
    } else if (refund) {
      const card = node('section', 'settlement-card game-settlement returned');
      const ribbon = node('div', 'settlement-ribbon');
      const left = node('div', 'settlement-ribbon-left');
      const mark = node('span', 'reward-mark');
      mark.append(icon('refund'));
      left.append(mark, node('span', 'settlement-summary-title', '预扣已返还'), node('span', 'settlement-badge', '+' + refund.amount + '⚡'));
      if (refund.reason) left.append(node('span', 'muted', refund.reason));
      const dismissBtn = node('button', 'settlement-dismiss-btn');
      dismissBtn.type = 'button';
      dismissBtn.setAttribute('aria-label', '关闭返还提示');
      dismissBtn.append(icon('close', 'chip-svg'));
      dismissBtn.onclick = () => {
        haptic(6);
        settlementDismissedId = key;
        box.hidden = true;
        sizing();
      };
      ribbon.append(left, dismissBtn);
      card.append(ribbon);
      box.append(card);
    }
  }

  /* ========================================================================
     Unified Game Hub Renderers (主角 / 人物 / 地图 / 行囊 / 系统)
     ======================================================================== */

  function buildStaminaDualRing(stamina, itemBudget) {
    const st = Math.max(0, Math.min(100, stamina));
    const bud = Math.max(0, Math.min(20, itemBudget));
    const wrap = node('div', 'gauge-ring-wrap');
    const svg = svgEl('svg', { viewBox: '0 0 124 124', class: 'gauge-ring-svg', 'aria-hidden': 'true' });

    const defs = svgEl('defs');
    const grad = svgEl('linearGradient', { id: 'hostStaminaGrad', x1: '0%', y1: '0%', x2: '100%', y2: '100%' });
    const c1 = st < 20 ? '#df7373' : st < 50 ? '#e6ba74' : '#7ecba4';
    const c2 = st < 20 ? '#a83c3c' : st < 50 ? '#b6833c' : '#d6b278';
    grad.append(
      svgEl('stop', { offset: '0%', 'stop-color': c1 }),
      svgEl('stop', { offset: '100%', 'stop-color': c2 })
    );
    defs.append(grad);
    svg.append(defs);

    // Outer Stamina Track & Value
    svg.append(
      svgEl('circle', { cx: 62, cy: 62, r: 52, fill: 'none', stroke: 'var(--surface-3)', 'stroke-width': 7 }),
      svgEl('circle', {
        cx: 62, cy: 62, r: 52, fill: 'none', stroke: 'url(#hostStaminaGrad)', 'stroke-width': 7,
        'stroke-linecap': 'round', 'stroke-dasharray': BIG_RING_C.toFixed(2),
        'stroke-dashoffset': (BIG_RING_C * (1 - st / 100)).toFixed(2)
      }),
      // Inner Recovery Budget Track & Value
      svgEl('circle', { cx: 62, cy: 62, r: 41, fill: 'none', stroke: 'var(--line)', 'stroke-width': 3.5 }),
      svgEl('circle', {
        cx: 62, cy: 62, r: 41, fill: 'none', stroke: 'var(--gold)', 'stroke-width': 3.5,
        'stroke-linecap': 'round', 'stroke-dasharray': INNER_RING_C.toFixed(2),
        'stroke-dashoffset': (INNER_RING_C * (1 - bud / 20)).toFixed(2),
        'stroke-opacity': '0.85'
      })
    );

    const center = node('div', 'gauge-center-label');
    center.append(node('strong', '', String(st)), node('span', '', '体力 / 100'));
    wrap.append(svg, center);
    return wrap;
  }

  function buildRadarSvg(stats, accent) {
    const axes = [
      { key: '好感', label: '好感' },
      { key: '羞耻', label: '羞耻' },
      { key: '体力', label: '体力' },
      { key: '欲望', label: '欲望' },
      { key: '堕落', label: '堕落' }
    ];
    const cx = 140, cy = 122, R = 74;
    const svg = svgEl('svg', { viewBox: '0 0 280 244', class: 'radar-svg', role: 'img', 'aria-label': '角色五维属性图' });

    const defs = svgEl('defs');
    const fillGrad = svgEl('radialGradient', { id: 'radarFillGrad', cx: '50%', cy: '50%', r: '55%' });
    fillGrad.append(
      svgEl('stop', { offset: '0%', 'stop-color': accent, 'stop-opacity': '0.46' }),
      svgEl('stop', { offset: '100%', 'stop-color': accent, 'stop-opacity': '0.14' })
    );
    defs.append(fillGrad);
    svg.append(defs);

    const pt = (i, ratio) => {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
      return [cx + Math.cos(a) * R * ratio, cy + Math.sin(a) * R * ratio];
    };

    for (const level of [0.25, 0.5, 0.75, 1]) {
      const pts = axes.map((_, i) => pt(i, level).map(n => n.toFixed(1)).join(',')).join(' ');
      svg.append(svgEl('polygon', { points: pts, class: 'radar-grid' }));
    }

    const polyPoints = [];
    const dots = [];
    axes.forEach((ax, i) => {
      const [ox, oy] = pt(i, 1);
      svg.append(svgEl('line', { x1: cx, y1: cy, x2: ox.toFixed(1), y2: oy.toFixed(1), class: 'radar-axis' }));
      const rawVal = stats[ax.key]?.num ?? 0;
      const ratio = Math.max(0.08, Math.min(1, rawVal / 100));
      const [vx, vy] = pt(i, ratio);
      polyPoints.push(vx.toFixed(1) + ',' + vy.toFixed(1));
      dots.push([vx, vy, rawVal]);

      const [lx, ly] = pt(i, 1.32);
      const anchor = Math.abs(lx - cx) < 12 ? 'middle' : lx > cx ? 'start' : 'end';
      const lbl = svgEl('text', { x: lx.toFixed(1), y: (ly - 3).toFixed(1), 'text-anchor': anchor, class: 'radar-label' });
      lbl.textContent = ax.label;
      const val = svgEl('text', { x: lx.toFixed(1), y: (ly + 12).toFixed(1), 'text-anchor': anchor, class: 'radar-val' });
      val.textContent = String(rawVal);
      svg.append(lbl, val);
    });

    svg.append(svgEl('polygon', {
      points: polyPoints.join(' '),
      fill: 'url(#radarFillGrad)',
      stroke: accent,
      'stroke-width': '2',
      'stroke-linejoin': 'round',
      class: 'radar-polygon'
    }));

    dots.forEach(([vx, vy]) => {
      svg.append(svgEl('circle', {
        cx: vx.toFixed(1), cy: vy.toFixed(1), r: 3.6,
        fill: '#171310', stroke: accent, 'stroke-width': 2
      }));
    });
    return svg;
  }

  function buildCityMapSvg(locations, presence, currentLoc, selectedLoc, onSelect) {
    const svg = svgEl('svg', { viewBox: '0 0 360 220', class: 'city-map-svg', role: 'img', 'aria-label': '城市地点分布图' });
    const coords = {};
    const extras = [];
    for (const loc of locations) {
      if (MAP_COORDS[loc]) coords[loc] = MAP_COORDS[loc];
      else extras.push(loc);
    }
    extras.forEach((loc, idx) => {
      const angle = (idx / Math.max(1, extras.length)) * Math.PI * 2;
      coords[loc] = { x: 180 + Math.cos(angle) * 120, y: 110 + Math.sin(angle) * 76, short: loc };
    });

    // Subtle decorative compass rings
    svg.append(
      svgEl('circle', { cx: 180, cy: 112, r: 84, fill: 'none', stroke: 'var(--line)', 'stroke-width': 0.8, 'stroke-dasharray': '2 6' }),
      svgEl('circle', { cx: 180, cy: 112, r: 42, fill: 'none', stroke: 'var(--line)', 'stroke-width': 0.7 })
    );

    // Connect architectural routes
    const pairs = [
      ['徐家主宅', '市中心顶层公寓'],
      ['徐家主宅', '公司'],
      ['市中心顶层公寓', '大学'],
      ['公司', '工作室'],
      ['大学', '工作室'],
      ['市中心顶层公寓', '公司']
    ];
    for (const [a, b] of pairs) {
      if (!coords[a] || !coords[b]) continue;
      const p1 = coords[a], p2 = coords[b];
      const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2 - 8;
      svg.append(svgEl('path', {
        d: `M${p1.x} ${p1.y} Q${mx} ${my} ${p2.x} ${p2.y}`,
        class: 'map-route'
      }));
    }

    // Active travel trajectory line from currentLoc -> selectedLoc
    if (selectedLoc && selectedLoc !== currentLoc && coords[currentLoc] && coords[selectedLoc]) {
      const p1 = coords[currentLoc], p2 = coords[selectedLoc];
      const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2 - 14;
      svg.append(svgEl('path', {
        d: `M${p1.x} ${p1.y} Q${mx} ${my} ${p2.x} ${p2.y}`,
        class: 'map-route is-active'
      }));
    }

    // Group people per location
    const occupants = {};
    for (const [who, info] of Object.entries(presence || {})) {
      if (!occupants[info.location]) occupants[info.location] = [];
      occupants[info.location].push(who);
    }

    const nodeGlyphPath = loc => {
      if (loc.includes('主宅')) return 'M-4.5 0 L0 -4.2 L4.5 0 M-3 0v3.8h6V0';
      if (loc.includes('公寓')) return 'M-3 4V-2.4L0 -5L3 -2.4V4M-1 1h2';
      if (loc.includes('公司')) return 'M-4.2 4V-3.6h3.2V4M1 4V-1.4h3.2V4';
      if (loc.includes('大学')) return 'M-4.5 -1.4L0 -4.5L4.5 -1.4M-3 -1.4v5M0 -1.4v5M3 -1.4v5M-4.5 3.6h9';
      if (loc.includes('工作室')) return 'M-3.4 -3.4h6.8v4.8h-6.8ZM-2 1.4L-3.4 4.4M2 1.4L3.4 4.4';
      return 'M0 -3.2L3.2 0L0 3.2L-3.2 0Z';
    };

    for (const loc of locations) {
      const pos = coords[loc];
      if (!pos) continue;
      const isHere = loc === currentLoc;
      const isSel = loc === selectedLoc;
      const g = svgEl('g', {
        class: 'map-node-group' + (isHere ? ' is-here' : '') + (isSel ? ' is-selected' : ''),
        tabindex: '0',
        role: 'button',
        'aria-label': loc + (isHere ? '（当前所在）' : '')
      });
      if (isHere) {
        const ring = svgEl('circle', { cx: pos.x, cy: pos.y, r: 12, class: 'map-beacon-ring', opacity: '0.65' });
        if (!reducedMotion()) {
          ring.append(
            svgEl('animate', { attributeName: 'r', values: '12;25', dur: '2.4s', repeatCount: 'indefinite' }),
            svgEl('animate', { attributeName: 'opacity', values: '0.85;0', dur: '2.4s', repeatCount: 'indefinite' })
          );
        }
        g.append(ring);
      }
      g.append(
        svgEl('circle', { cx: pos.x, cy: pos.y, r: 25, class: 'map-node-hit' }),
        svgEl('circle', { cx: pos.x, cy: pos.y, r: isHere || isSel ? 12 : 10.5, class: 'map-node-dot' }),
        svgEl('path', { d: nodeGlyphPath(loc), transform: `translate(${pos.x}, ${pos.y})`, class: 'map-node-glyph' })
      );
      const label = svgEl('text', { x: pos.x, y: pos.y + 25, class: 'map-node-label' });
      label.textContent = pos.short || loc;
      g.append(label);

      const whoList = (occupants[loc] || []).filter(n => n !== '徐志北');
      if (whoList.length) {
        const sub = svgEl('text', { x: pos.x, y: pos.y - 16, class: 'map-node-count' });
        sub.textContent = whoList.join(' · ');
        g.append(sub);
      }

      const activate = () => { haptic(8); onSelect(loc); };
      g.addEventListener('click', activate);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
      svg.append(g);
    }
    return svg;
  }

  function renderHostTab(w, panels) {
    const pane = node('div', 'hub-pane');
    const host = panels['系统宿主'] || { stats: {}, ordered: [] };
    const pg = w.progression;
    const staminaVal = pg ? pg.stamina : (host.stats['体力']?.num ?? 100);
    const budgetVal = pg ? pg.item_budget : 20;

    // 1. Hero Identity Card
    const hero = node('section', 'host-hero-card');
    const av = node('img', 'host-avatar');
    av.src = image('徐志北', 'into.png');
    av.alt = '徐志北';
    av.decoding = 'async';

    const idBox = node('div', 'host-identity');
    idBox.append(node('h3', '', '徐志北'), node('div', 'host-role-line', '系统宿主 · 执秤者'));
    const pills = node('div', 'host-meta-pills');
    const locChip = node('span', 'meta-chip');
    locChip.append(icon('map', 'chip-svg'), node('span', '', w.location || '未知地点'));
    pills.append(locChip);
    if (pg?.runtime?.clock) {
      const clk = node('span', 'meta-chip');
      clk.append(icon('clock', 'chip-svg'), node('span', '', formatGameClock(pg.runtime.clock, w.weekday || '')));
      pills.append(clk);
    }
    if (pg?.runtime?.memory_round) {
      pills.append(node('span', 'meta-chip', '第 ' + pg.runtime.memory_round + ' 记忆回合'));
    }
    idBox.append(pills);
    hero.append(av, idBox);
    pane.append(hero);

    // 2. Dual SVG Vitals Gauge Card
    const vitals = node('section', 'vitals-card');
    vitals.append(buildStaminaDualRing(staminaVal, budgetVal));
    const vDetails = node('div', 'vitals-details');

    const mkVitalRow = (label, valueText, pct, color) => {
      const row = node('div', 'vital-row');
      const top = node('div', 'vital-row-top');
      top.append(node('span', '', label), node('b', '', valueText));
      const track = node('div', 'stat-track');
      const bar = node('span', 'stat-bar');
      bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
      bar.style.background = color;
      track.append(bar);
      row.append(top, track);
      return row;
    };

    vDetails.append(
      mkVitalRow('当前体力', staminaVal + ' / 100', staminaVal, staminaVal < 20 ? 'var(--crimson)' : 'linear-gradient(90deg, var(--jade), var(--gold-bright))'),
      mkVitalRow('道具恢复额度', budgetVal + ' / 20', (budgetVal / 20) * 100, 'linear-gradient(90deg, var(--gold-deep), var(--gold-bright))')
    );
    const note = node('p', 'muted', 'A 5 · B 10 · C 15 体力；安稳整夜入眠恢复至满值并重置额度。');
    note.style.margin = '2px 0 0';
    vDetails.append(note);
    vitals.append(vDetails);
    pane.append(vitals);

    // 3. Structured Attribute Tiles
    const grid = node('section', 'attr-grid');
    const hostAttrs = host.ordered.filter(item => item.key !== '体力');
    const tileConfigs = {
      '积分': { icon: 'coin', color: 'var(--gold-bright)', max: null },
      '经验值': { icon: 'sparkle', color: 'var(--mist)', max: null },
      '魅力': { icon: 'heart', color: 'var(--rose)', max: 100 },
      '商业嗅觉': { icon: 'shield', color: 'var(--jade)', max: 100 }
    };
    for (const item of hostAttrs) {
      const cfg = tileConfigs[item.key] || { icon: 'sparkle', color: 'var(--gold)', max: null };
      const isPoints = item.key === '积分';
      const isExp = item.key === '经验值';
      const isClickable = isPoints || isExp;
      const tile = node(isClickable ? 'button' : 'div', 'attr-tile' + (isClickable ? ' is-clickable' : ''));
      if (isPoints) {
        tile.type = 'button';
        tile.onclick = () => openHub('shop');
      } else if (isExp) {
        tile.type = 'button';
        tile.onclick = () => openHub('roster');
      }
      const head = node('div', 'attr-tile-head');
      head.append(node('span', '', item.key), icon(cfg.icon, 'chip-svg'));
      const val = node('div', 'attr-tile-val', item.raw);
      tile.append(head, val);
      if (isPoints) {
        tile.append(node('div', 'attr-tile-link', '前往商城兑换 →'));
      } else if (isExp) {
        tile.append(node('div', 'attr-tile-link', '前往名册解锁被动 →'));
      } else if (cfg.max && item.num !== null) {
        const track = node('div', 'stat-track');
        const bar = node('span', 'stat-bar');
        bar.style.width = Math.max(0, Math.min(100, (item.num / cfg.max) * 100)) + '%';
        bar.style.background = cfg.color;
        track.append(bar);
        tile.append(track);
      }
      grid.append(tile);
    }
    if (hostAttrs.length) pane.append(grid);

    // 3b. Commercial Sense, One-Time Intel & Business Leverage Card
    const intel = w.intel;
    if (intel && Array.isArray(intel.catalog) && intel.catalog.length) {
      const bizVal = host.stats['商业嗅觉']?.num ?? 0;
      const levMin = intel.leverage_min_biz ?? 60;
      const heldSet = new Set(intel.held || []);
      const consumedSet = new Set(intel.consumed || []);
      const armedId = intel.leverage_armed || '';
      const suAb = intel.su_ab_contacts ?? 0;

      const iSec = node('section', 'intel-section');
      const iHead = node('div', 'intel-head');
      iHead.append(
        node('strong', '', '商业嗅觉与一次性情报'),
        node('span', 'quest-badge', '嗅觉 ' + bizVal + ' / 100')
      );
      iSec.append(iHead);

      const tierStrip = node('div', 'intel-tier-strip');
      for (const [th, lbl] of [[10, '10 入门'], [30, '30 被看见'], [60, '60 杠杆'], [100, '100 视野']]) {
        tierStrip.append(node('span', 'intel-tier-pill' + (bizVal >= th ? ' is-reached' : ''), lbl));
      }
      iSec.append(tierStrip);

      if (armedId) {
        const armedItem = intel.catalog.find(x => x.id === armedId);
        const banner = node('div', 'leverage-banner');
        banner.append(node('span', '', '商业杠杆已预备：「' + (armedItem ? armedItem.name : armedId) + '」（下次 C 烈度好感惩罚减半，非 C 烈度不浪费）'));
        const disarmBtn = node('button', 'btn-outline', '取消预备');
        disarmBtn.type = 'button';
        disarmBtn.disabled = !canTransactDeterministic();
        disarmBtn.onclick = () => void toggleBusinessLeverage('disarm', '');
        banner.append(disarmBtn);
        iSec.append(banner);
      }

      for (const it of intel.catalog) {
        const isHeld = heldSet.has(it.id);
        const isConsumed = consumedSet.has(it.id);
        const bizOk = bizVal >= (it.min_biz || 0);
        const abOk = suAb >= (it.min_su_ab_contacts || 0);
        const canAcquire = !isHeld && !isConsumed && bizOk && abOk;

        const ic = node('article', 'intel-card' + (isHeld ? ' is-held' : '') + (isConsumed ? ' is-consumed' : ''));
        const cTop = node('div', 'intel-head');
        const badgeText = isHeld ? (armedId === it.id ? '持有中 · 杠杆已预备' : '持有中')
          : isConsumed ? '已消耗作废'
          : canAcquire ? '可整理入库'
          : '未解锁';
        cTop.append(node('strong', '', it.name), node('span', 'item-tag' + (isHeld ? ' is-effect' : ''), badgeText));
        ic.append(cTop);

        const reqParts = ['嗅觉 ≥ ' + it.min_biz];
        if (it.min_su_ab_contacts > 0) reqParts.push('苏婉青A/B接触 ' + suAb + '/' + it.min_su_ab_contacts);
        ic.append(
          node('p', 'intel-desc', it.effect_summary),
          node('span', 'muted', '门槛：' + reqParts.join(' · '))
        );

        const acts = node('div', 'intel-actions');
        if (!isHeld && !isConsumed) {
          const acqBtn = node('button', 'btn-jade', canAcquire ? '整理入库 · 0体力' : '尚未达成门槛');
          acqBtn.type = 'button';
          acqBtn.disabled = !canAcquire || !canTransactDeterministic();
          acqBtn.onclick = () => void acquireIntel(it.id);
          acts.append(acqBtn);
        } else if (isHeld) {
          if (bizVal >= levMin) {
            const isThisArmed = armedId === it.id;
            const levBtn = node('button', isThisArmed ? 'btn-outline' : 'btn-jade', isThisArmed ? '取消商业杠杆' : '预备商业杠杆 · 0体力');
            levBtn.type = 'button';
            levBtn.disabled = !canTransactDeterministic();
            levBtn.onclick = () => void toggleBusinessLeverage(isThisArmed ? 'disarm' : 'arm', it.id);
            acts.append(levBtn);
          }
          const cueBtn = node('button', 'btn-outline', '带入对话亮牌');
          cueBtn.type = 'button';
          cueBtn.onclick = () => {
            haptic(10);
            $('worldDialog').close();
            if (deckCollapsed) {
              deckCollapsed = false;
              controls();
              sizing();
            }
            const inp = $('input');
            const cue = '（亮出私下掌握的情报「' + it.name + '」作为筹码）';
            inp.value = inp.value.trim() ? (inp.value.trim() + ' ' + cue) : cue;
            cache.draft = inp.value;
            save();
            controls();
            sizing();
            inp.focus();
            toast('已填入情报亮牌提示，确认补充行动后发送');
          };
          acts.append(cueBtn);
        }
        if (acts.children.length) ic.append(acts);
        iSec.append(ic);
      }
      pane.append(iSec);
    }

    // 4. Compact Chronicle Stats
    const summary = node('section', 'pref-group');
    summary.append(node('h3', '', '存档概览'));
    const row = node('div', 'pref-row');
    const lbl = node('div', 'pref-row-label');
    lbl.append(
      node('strong', '', w.interaction.count + ' 段已存剧情 · ' + w.interaction.actions + ' 次登记行动'),
      node('span', '', pg ? '跨零点或最终体力不足 5 时自动收束记忆回合' : '正式连续演播存档')
    );
    row.append(lbl);
    summary.append(row);
    pane.append(summary);

    return pane;
  }

  function renderRosterTab(w, panels) {
    const pane = node('div', 'hub-pane');
    const rosterNames = [
      ...PEOPLE,
      ...Object.keys(panels).filter(k => k !== '系统宿主' && !PEOPLE.includes(k))
    ];
    if (!rosterNames.includes(selectedChar)) {
      selectedChar = (w.cast && w.cast[0]) || rosterNames[0] || '沈知韫';
    }

    // Horizontal Character Selector Rail
    const rail = node('div', 'roster-rail');
    rail.setAttribute('role', 'tablist');
    for (const name of rosterNames) {
      const meta = CHAR_META[name] || { role: '角色', hasPortrait: false };
      const pInfo = panels[name]?.stats || {};
      const isHere = (w.cast || []).includes(name);
      const btn = node('button', 'roster-pill');
      btn.type = 'button';
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', String(name === selectedChar));

      const thumbWrap = node('span', 'roster-thumb-wrap');
      if (hasCharacterPortrait(name)) {
        const im = node('img', 'roster-thumb');
        im.src = image(name, 'into.png');
        im.alt = '';
        im.decoding = 'async';
        thumbWrap.append(im);
      } else {
        thumbWrap.append(node('span', 'roster-thumb-fallback', name.slice(0, 1)));
      }
      thumbWrap.append(node('i', 'presence-dot' + (isHere ? ' is-here' : '')));

      const info = node('span', 'roster-pill-info');
      info.append(
        node('strong', '', name),
        node('span', '', pInfo['好感'] ? ('好感 ' + pInfo['好感'].raw) : (w.presence?.[name]?.location || meta.role))
      );
      btn.append(thumbWrap, info);
      btn.onclick = () => {
        haptic(8);
        selectedChar = name;
        renderWorld(true);
      };
      rail.append(btn);
    }
    pane.append(rail);

    // Selected Character Feature Card
    const name = selectedChar;
    const meta = CHAR_META[name] || { role: '登场人物', accent: '#d6b278', hasPortrait: false, fullbody: false };
    const charPanel = panels[name] || { stats: {}, ordered: [] };
    const locObj = w.presence?.[name];
    const isHere = (w.cast || []).includes(name);

    const card = node('section', 'char-stage-card');

    if (hasCharacterPortrait(name)) {
      const slots = getCharacterSlots(name);
      const banner = node('div', 'char-banner');
      const img = node('img', 'char-banner-img');
      img.src = slots.into || Object.values(slots)[0] || image(name, 'into.png');
      img.alt = name;
      img.decoding = 'async';
      const scrim = node('div', 'char-banner-scrim');
      const overlay = node('div', 'char-banner-overlay');

      const titleBox = node('div', 'char-banner-title');
      titleBox.append(node('h3', '', name));
      const sub = node('div', 'char-banner-sub');
      sub.append(node('span', '', meta.role));
      if (locObj) {
        sub.append(node('span', 'presence-badge' + (isHere ? ' is-here' : ''), isHere ? '此刻在场' : locObj.location));
      }
      titleBox.append(sub);
      overlay.append(titleBox);

      if (Object.keys(slots).length > 0) {
        const openBtn = node('button', 'portrait-open-btn', '展开立绘');
        openBtn.type = 'button';
        openBtn.onclick = () => { haptic(10); showPortrait(name, slots.fullbody ? 'fullbody' : ''); };
        overlay.append(openBtn);
      }
      banner.append(img, scrim, overlay);
      card.append(banner);
    } else {
      const head = node('div', 'char-body');
      const row = node('div', 'pref-row');
      const lbl = node('div', 'pref-row-label');
      const vigPos = name === '徐承邺' && w.vigilance?.position ? w.vigilance.position : '';
      const isManorPos = p => p === '徐家主宅' || p === '徐家住宅';
      const subText = locObj
        ? (locObj.location + (locObj.reason ? ' · ' + locObj.reason : ''))
        : (vigPos ? (isManorPos(vigPos) ? '徐家主宅 · 此刻在主宅' : vigPos) : '当前行踪未记');
      lbl.append(node('strong', '', name + ' · ' + meta.role), node('span', '', subText));
      row.append(lbl);
      head.append(row);
      card.append(head);
    }

    const body = node('div', 'char-body');
    if (locObj && meta.hasPortrait) {
      const locNote = node('div', 'meta-chip');
      locNote.style.width = 'fit-content';
      locNote.append(icon('map', 'chip-svg'), node('span', '', locObj.location + (locObj.reason ? ' · ' + locObj.reason : '')));
      body.append(locNote);
    }

    // Check if character supports 5-axis SVG Radar Chart
    const radarKeys = ['好感', '羞耻', '体力', '欲望', '堕落'];
    const hasRadar = radarKeys.filter(k => charPanel.stats[k]?.num !== null && charPanel.stats[k]?.num !== undefined).length >= 3;
    if (hasRadar) {
      const radarWrap = node('div', 'radar-wrap');
      radarWrap.append(buildRadarSvg(charPanel.stats, meta.accent));
      body.append(radarWrap);
    }

    // Animated Stat Bars for Bounded Numeric Metrics
    const barMeta = {
      '好感': 'linear-gradient(90deg, #b86a5e, #e49c8d)',
      '羞耻': 'linear-gradient(90deg, #b99968, #f0d7a8)',
      '体力': 'linear-gradient(90deg, #4b8f6f, #7ecba4)',
      '欲望': 'linear-gradient(90deg, #9f4448, #df7278)',
      '堕落': 'linear-gradient(90deg, #7d4a69, #c484a7)'
    };
    const barItems = charPanel.ordered.filter(it => barMeta[it.key] && it.num !== null);
    if (barItems.length) {
      const grid = node('div', 'char-bars-grid');
      for (const it of barItems) {
        const bCard = node('div', 'char-bar-card');
        const top = node('div', 'char-bar-top');
        top.append(node('span', '', it.key), node('b', '', it.raw));
        const track = node('div', 'stat-track');
        const fill = node('span', 'stat-bar');
        fill.style.width = Math.max(0, Math.min(100, it.num)) + '%';
        fill.style.background = barMeta[it.key];
        track.append(fill);
        bCard.append(top, track);
        grid.append(bCard);
      }
      body.append(grid);
    }

    // Remaining Secondary Status Chips (高潮 / 内射 / 怀孕 / 被动 / etc.)
    const chipItems = charPanel.ordered.filter(it => !barMeta[it.key]);
    const phys = w.physiology?.[name];
    if (chipItems.length || phys) {
      const chips = node('div', 'status-chip-row');
      for (const it of chipItems) {
        const chip = node('span', 'status-chip');
        const display = it.bool === true ? '是' : it.bool === false ? '否' : it.raw;
        chip.append(node('span', '', it.key), node('b', '', display));
        chips.append(chip);
      }
      if (phys) {
        if (phys.cycle_phase) {
          const chip = node('span', 'status-chip');
          chip.append(node('span', '', '生理周期'), node('b', '', phys.cycle_phase));
          chips.append(chip);
        }
        if (phys.pregnancy_stage === 'latent') {
          const chip = node('span', 'status-chip');
          const daysTxt = Number.isFinite(Number(phys.latent_days_left)) ? ('（剩' + phys.latent_days_left + '天显影）') : '';
          chip.append(node('span', '', '孕育状态'), node('b', '', '潜伏着床' + daysTxt));
          chips.append(chip);
        }
        if (Number(phys.unrelieved_streak) > 0) {
          const chip = node('span', 'status-chip');
          chip.append(node('span', '', '欲求积压'), node('b', '', phys.unrelieved_streak + ' 段'));
          chips.append(chip);
        }
      }
      body.append(chips);
    }

    // Persistent BUFF Badges (e.g., 持续_体液锁定)
    const charBuffs = w.buffs?.[name] || [];
    if (charBuffs.length) {
      const bRow = node('div', 'buff-row');
      for (const b of charBuffs) {
        const badge = node('span', 'buff-badge');
        badge.append(node('b', '', b.name), node('span', '', '剩 ' + b.turns + ' 行动' + (b.effect ? ' · ' + b.effect : '')));
        bRow.append(badge);
      }
      body.append(bRow);
    }

    // Deterministic EXP Passive Skill Upgrade Card (Heroines only)
    if (PEOPLE.includes(name) && Array.isArray(w.passive_tiers) && w.passive_tiers.length) {
      const rawPassive = charPanel.stats['被动']?.raw || 'Lv.0';
      const lvM = /Lv\.(\d+)/.exec(rawPassive);
      const curLv = lvM ? Number(lvM[1]) : 0;
      const curTier = w.passive_tiers[curLv] || w.passive_tiers[0];
      const nextTier = w.passive_tiers[curLv + 1] || null;
      const hostExp = panels['系统宿主']?.stats?.['经验值']?.num ?? 0;

      const pCard = node('section', 'passive-card');
      const pHead = node('div', 'passive-head');
      pHead.append(
        node('strong', '', '定向被动 · ' + curTier.tag + ' ' + curTier.name),
        node('span', 'item-tag', '可用经验 ' + hostExp)
      );
      pCard.append(pHead, node('p', 'passive-effect', curTier.effect));

      if (nextTier) {
        const nextBox = node('div', 'passive-next-box');
        const nMeta = node('div', 'passive-next-meta');
        nMeta.append(
          node('span', '', '下一阶：' + nextTier.tag + ' ' + nextTier.name),
          node('b', '', '消耗 ' + nextTier.cost + ' 经验')
        );
        nextBox.append(nMeta, node('p', 'passive-effect', nextTier.effect));
        const pActs = node('div', 'passive-actions');
        const enoughExp = hostExp >= nextTier.cost;
        const upBtn = node('button', 'btn-jade', shopBusy ? '解锁中…' : ('解锁 ' + nextTier.tag + ' · ' + nextTier.cost + ' EXP · 0体力'));
        upBtn.type = 'button';
        upBtn.disabled = !enoughExp || !canTransactDeterministic();
        upBtn.onclick = () => void upgradePassiveSkill(name);
        pActs.append(upBtn);
        const blockReason = !enoughExp ? ('经验值尚差 ' + (nextTier.cost - hostExp)) : transactBlockReason();
        if (blockReason && upBtn.disabled) {
          pActs.append(node('span', 'shop-reason-hint', blockReason));
        }
        nextBox.append(pActs);
        pCard.append(nextBox);
      } else {
        pCard.append(node('span', 'item-tag is-effect', '已达最高阶防线支配'));
      }
      body.append(pCard);
    }

    // Dedicated Vigilance Monitor Panel for 徐承邺 (strictly hides 发现几率)
    if (name === '徐承邺' && w.vigilance) {
      const vCard = node('section', 'vigilance-card');
      const vHead = node('div', 'vigilance-head');
      const isHome = w.vigilance.position === '徐家主宅' || w.vigilance.position === '徐家住宅';
      vHead.append(
        node('strong', '', '徐承邺监视态势'),
        node('span', 'vigilance-pos-pill' + (isHome ? ' is-home' : ''), isHome ? '徐家主宅 · 正在主宅' : (w.vigilance.position || '外地'))
      );
      vCard.append(vHead);
      const discLabels = { 0: '未察觉', 1: '怀疑', 2: '线索', 3: '目击锁定', 4: '实锤' };
      const vList = node('div', 'vigilance-list');
      for (const t of (w.vigilance.targets || [])) {
        const vRow = node('div', 'vigilance-row');
        const vTop = node('div', 'vigilance-row-top');
        vTop.append(
          node('span', '', t.name + ' · ' + (discLabels[t.discovery] || ('发现 ' + t.discovery))),
          node('b', '', '警惕 ' + t.vigilance + ' / 100')
        );
        const track = node('div', 'stat-track');
        const fill = node('span', 'stat-bar');
        fill.style.width = Math.max(0, Math.min(100, t.vigilance)) + '%';
        fill.style.background = t.vigilance >= 70
          ? 'linear-gradient(90deg, #9f4448, #e07272)'
          : t.vigilance >= 30
            ? 'linear-gradient(90deg, #b99968, #f0d7a8)'
            : 'linear-gradient(90deg, #4b8f6f, #7ecba4)';
        track.append(fill);
        vRow.append(vTop, track);
        vList.append(vRow);
      }
      vCard.append(vList, node('span', 'muted', '每完整游戏小时警惕自然回落 2（目击锁定目标不衰减）；仅显示行踪、警惕与发现阶段。'));
      body.append(vCard);
    }

    if (!charPanel.ordered.length) {
      body.append(node('p', 'muted', '当前存档尚未记录该人物的数值面板。'));
    }

    card.append(body);
    pane.append(card);
    return pane;
  }

  function renderMapTab(w) {
    const pane = node('div', 'hub-pane');
    const locations = w.policy?.locations || Object.keys(MAP_COORDS);
    const currentLoc = w.location || locations[0];
    if (!selectedMapPlace || !locations.includes(selectedMapPlace)) {
      selectedMapPlace = locations.find(l => l !== currentLoc) || currentLoc;
    }

    const canvasCard = node('section', 'map-canvas-card');
    canvasCard.append(buildCityMapSvg(locations, w.presence, currentLoc, selectedMapPlace, loc => {
      selectedMapPlace = loc;
      renderWorld(true);
    }));
    pane.append(canvasCard);

    // Travel Action Bar for Selected Destination
    const travelBar = node('section', 'map-travel-bar');
    const info = node('div', 'map-travel-info');
    const isHere = selectedMapPlace === currentLoc;
    const travelAllowed = !isHere && !ordinaryBlocked() && afford(15);
    const reasonText = isHere ? '你此刻正身处此地'
      : !canDecide() ? '请先读完本段剧情后再启程'
      : resting() ? '当前需先完成休整'
      : !afford(15) ? '当前体力不足 15'
      : '将作为自定义行动提交 · 暂扣 15 体力';
    info.append(node('strong', '', selectedMapPlace), node('span', '', reasonText));
    const goBtn = node('button', 'cta-gold', isHere ? '当前位置' : '前往此地');
    goBtn.type = 'button';
    goBtn.disabled = !travelAllowed;
    goBtn.style.minHeight = '42px';
    goBtn.style.padding = '8px 16px';
    goBtn.onclick = async () => {
      if (goBtn.disabled) return;
      haptic(14);
      const dest = selectedMapPlace;
      $('worldDialog').close();
      await enqueue('前往' + dest, { code: 'move_player', destination: dest });
    };
    travelBar.append(info, goBtn);
    pane.append(travelBar);

    // Detailed Location Cards
    const list = node('section', 'location-list');
    for (const loc of locations) {
      const card = node('button', 'location-card' + (loc === currentLoc ? ' is-here' : '') + (loc === selectedMapPlace ? ' is-selected' : ''));
      card.type = 'button';
      const main = node('div', 'location-card-main');
      const title = node('strong', '', loc);
      if (loc === currentLoc) title.append(node('span', 'quest-badge', '当前所在'));
      main.append(title);

      const whoHere = Object.entries(w.presence || {}).filter(([, p]) => p.location === loc);
      const pplRow = node('div', 'location-card-people');
      if (whoHere.length) {
        for (const [who, p] of whoHere) {
          pplRow.append(node('span', 'mini-who-tag', who + (p.reason ? ' · ' + p.reason : '')));
        }
      } else {
        pplRow.append(node('span', 'mini-who-tag', '此刻无人停留'));
      }
      main.append(pplRow);
      card.append(main);
      card.onclick = () => {
        haptic(8);
        selectedMapPlace = loc;
        renderWorld(true);
      };
      list.append(card);
    }
    pane.append(list);

    return pane;
  }

  function renderBagTab(w, panels) {
    const pane = node('div', 'hub-pane');
    const hostPoints = panels['系统宿主']?.stats?.['积分']?.num ?? 0;

    // 1. Quest Contract Section
    const curTask = w.tasks?.current;
    if (curTask) {
      const qCard = node('section', 'quest-card');
      const head = node('div', 'quest-head');
      head.append(
        node('div', 'quest-title', curTask.title || '进行中委托'),
        node('span', 'quest-badge', (QUEST_TIERS[curTask.tier] || curTask.tier || '委托') + ' · ' + (curTask.status || '进行中'))
      );
      const metaText = '目标：' + (curTask.target || '系统宿主') + ' · ' + (curTask.attr || '') + ' ≥ ' + (curTask.value ?? '')
        + (curTask.item_desc ? '\n附赠小物：' + curTask.item_desc : '')
        + (curTask.issue_round ? '\n发布回合：第 ' + curTask.issue_round + ' 回合' : '');
      qCard.append(head, node('div', 'quest-meta', metaText));

      const rewardSummary = QUEST_REWARDS[curTask.tier];
      if (rewardSummary) {
        const rewardLine = node('div', 'quest-reward-line');
        rewardLine.append(icon('sparkle', 'chip-svg'), node('span', '', '达成奖励：' + rewardSummary));
        qCard.append(rewardLine);
      }

      const targetPanel = panels[curTask.target]?.stats?.[curTask.attr];
      if (targetPanel && targetPanel.num !== null && Number.isFinite(Number(curTask.value)) && Number(curTask.value) > 0) {
        const curV = targetPanel.num, reqV = Number(curTask.value);
        const pct = Math.max(0, Math.min(100, Math.round((curV / reqV) * 100)));
        const row = node('div', 'vital-row');
        const top = node('div', 'vital-row-top');
        top.append(node('span', '', '当前达成进度'), node('b', '', curV + ' / ' + reqV));
        const track = node('div', 'stat-track');
        const bar = node('span', 'stat-bar');
        bar.style.width = pct + '%';
        bar.style.background = 'linear-gradient(90deg, var(--gold-deep), var(--gold-bright))';
        track.append(bar);
        row.append(top, track);
        qCard.append(row);
      }
      pane.append(qCard);
    } else {
      const emptyQ = node('section', 'empty-card');
      emptyQ.append(icon('scroll'), node('p', '', '此刻暂无进行中委托，随剧情推进自动承接下一项'));
      pane.append(emptyQ);
    }

    // 1b. Pending Quest Reward One-Click Claim Card (supports pending_items queue)
    const pendingQueue = Array.isArray(w.tasks?.pending_items) && w.tasks.pending_items.length
      ? w.tasks.pending_items
      : (w.tasks?.pending_item ? [w.tasks.pending_item] : []);
    if (pendingQueue.length) {
      const rawPending = String(pendingQueue[0]).trim();
      const pm = /^(TASK-\d+)\s*\|\s*([^|]+?)\s*\|完成回合(\d+)$/.exec(rawPending);
      const claimCard = node('section', 'quest-claim-card');
      const cHead = node('div', 'quest-claim-head');
      const cTitle = node('strong', '');
      const qSuffix = pendingQueue.length > 1 ? ('（队列共 ' + pendingQueue.length + ' 项）') : '';
      cTitle.append(icon('gift', 'chip-svg'), node('span', '', (pm ? ('待领委托奖励 · ' + pm[1]) : '待领委托奖励') + qSuffix));
      cHead.append(cTitle, node('span', 'item-tag is-effect', '0 体力 · 即时入囊'));
      claimCard.append(cHead, node('p', 'quest-claim-desc', pm ? ('可领取奖励小物：「' + pm[2].trim() + '」（第 ' + pm[3] + ' 回合达成）') : rawPending));
      if (pendingQueue.length > 1) {
        const qList = node('p', 'muted', '后续待领：' + pendingQueue.slice(1).join('；'));
        claimCard.append(qList);
      }
      const cActs = node('div', 'quest-claim-actions');
      const claimBtn = node('button', 'btn-jade', shopBusy ? '领取中…' : '领取委托奖励 · 免费');
      claimBtn.type = 'button';
      claimBtn.disabled = !canTransactDeterministic();
      claimBtn.onclick = () => void claimTaskReward();
      cActs.append(claimBtn);
      const reason = transactBlockReason();
      if (reason && !canTransactDeterministic()) {
        cActs.append(node('span', 'shop-reason-hint', reason));
      }
      claimCard.append(cActs);
      pane.append(claimCard);
    }

    if (w.tasks?.history?.length) {
      const histBox = node('details', 'settlement-details');
      histBox.style.padding = '0 6px';
      histBox.append(node('summary', '', '查看已完成委托（' + w.tasks.history.length + '） ▾'));
      for (const h of w.tasks.history) histBox.append(node('p', 'muted', h));
      pane.append(histBox);
    }

    // 2. Quick Jump to System Shop
    const shopCta = node('button', 'bag-shop-cta');
    shopCta.type = 'button';
    const ctaLeft = node('span', 'bag-shop-cta-left');
    ctaLeft.append(icon('shop', 'chip-svg'), node('span', '', '前往系统商城兑换道具 →'));
    shopCta.append(ctaLeft, node('small', '', '现有 ' + hostPoints + ' 积分 · 0 体力'));
    shopCta.onclick = () => openHub('shop');
    pane.append(shopCta);

    // 3. Inventory Section (split into 随身持有 vs 已赠予纪念)
    const allItems = w.items || [];
    const heldItems = allItems.filter(it => (it.fields?.['当前状态'] || '仓库中') !== '已交付');
    const deliveredList = Array.isArray(w.delivered_items)
      ? w.delivered_items.map(it => ({
          id: it.id,
          name: it.name,
          quantity: it.quantity,
          remaining_turns: null,
          giftable: false,
          fields: {
            '当前状态': it.status || '已交付',
            '类型': it.type || '永久性',
            '使用对象': it.target || '',
            '描述': it.desc || '',
          }
        }))
      : [];
    const legacyGifted = allItems.filter(it => (it.fields?.['当前状态'] || '') === '已交付');
    const giftedItems = [...deliveredList, ...legacyGifted];

    const renderItemCard = item => {
      const pg = w.progression;
      const card = node('article', 'item-card');
      const top = node('div', 'item-card-top');
      top.append(node('span', 'item-card-name', item.name), node('span', 'item-qty-pill', '× ' + item.quantity));
      card.append(top);

      const tags = node('div', 'item-tags');
      const status = item.fields?.['当前状态'] || '持有';
      tags.append(node('span', 'item-tag', status));
      if (item.fields?.['类型']) tags.append(node('span', 'item-tag', item.fields['类型']));
      if (item.remaining_turns !== null && item.remaining_turns !== undefined) {
        tags.append(node('span', 'item-tag is-timer', '剩余 ' + item.remaining_turns + ' 行动'));
      } else if (item.fields?.['剩余时效'] && !['无', ''].includes(item.fields['剩余时效'])) {
        tags.append(node('span', 'item-tag is-timer', '剩余 ' + item.fields['剩余时效']));
      }
      if (item.fields?.['使用对象'] && !['', '无', '未使用'].includes(item.fields['使用对象'])) {
        tags.append(node('span', 'item-tag', '对象：' + item.fields['使用对象']));
      }
      const eff = item.fields?.['系统效果'] || '';
      const staminaMatch = /^host_stamina:([1-9]\d*)$/.exec(eff);
      if (staminaMatch) {
        tags.append(node('span', 'item-tag is-effect', '体力 +' + staminaMatch[1]));
      }
      card.append(tags);

      if (item.fields?.['描述']) {
        card.append(node('p', 'item-desc', item.fields['描述']));
      }

      const owned = status === '仓库中' && ['', '无', '未使用', '徐志北'].includes(item.fields?.['使用对象'] || '');
      const canGift = item.giftable !== false && item.fields?.['可赠予'] !== '否';
      if (owned) {
        const acts = node('div', 'item-card-actions');
        if (staminaMatch) {
          const useBtn = node('button', 'btn-jade', '使用恢复 · 免费');
          useBtn.type = 'button';
          useBtn.disabled = ordinaryBlocked() || !pg || pg.item_budget <= 0 || pg.stamina >= 100;
          useBtn.onclick = async () => {
            if (useBtn.disabled) return;
            haptic(14);
            $('worldDialog').close();
            await enqueue('使用恢复道具 ' + item.id, { code: 'use_recovery_item', item_id: item.id });
          };
          acts.append(useBtn);
        }
        if (w.cast?.length && canGift) {
          const giftBtn = node('button', 'btn-outline', '赠予在场人物');
          giftBtn.type = 'button';
          giftBtn.disabled = ordinaryBlocked() || !afford(15);
          giftBtn.onclick = () => {
            haptic(8);
            $('worldDialog').close();
            $('item').value = item.id;
            controls();
            $('actionStatus').textContent = '已选中「' + item.name + '」，请选择在场接收人。';
            $('actionDialog').showModal();
          };
          acts.append(giftBtn);
        }
        if (acts.children.length) card.append(acts);
      }
      return card;
    };

    if (!heldItems.length && !giftedItems.length) {
      const emptyBag = node('section', 'empty-card');
      emptyBag.append(icon('bag'), node('p', '', '行囊暂为空置，完成委托或前往系统商城兑换可获得道具'));
      pane.append(emptyBag);
    } else {
      if (heldItems.length) {
        pane.append(node('div', 'bag-section-title', '随身持有（' + heldItems.length + '）'));
        const grid = node('section', 'item-grid');
        for (const item of heldItems) grid.append(renderItemCard(item));
        pane.append(grid);
      } else {
        const emptyHeld = node('section', 'empty-card');
        emptyHeld.append(icon('bag'), node('p', '', '当前没有随身未赠予的道具'));
        pane.append(emptyHeld);
      }
      if (giftedItems.length) {
        const giftBox = node('details', 'settlement-details');
        giftBox.style.padding = '0 4px';
        giftBox.append(node('summary', '', '已赠予纪念（' + giftedItems.length + '） ▾'));
        const gGrid = node('section', 'item-grid');
        gGrid.style.marginTop = '8px';
        for (const item of giftedItems) gGrid.append(renderItemCard(item));
        giftBox.append(gGrid);
        pane.append(giftBox);
      }
    }

    return pane;
  }

  function renderShopTab(w, panels) {
    const pane = node('div', 'hub-pane');
    if (!shopCatalog && !shopLoading && !shopError) {
      void loadShop();
    }
    const hostPoints = panels['系统宿主']?.stats?.['积分']?.num ?? 0;
    const points = shopCatalog && shopCatalog.revision === snapshot?.revision ? shopCatalog.points : hostPoints;

    // 1. Balance Hero Card
    const balCard = node('section', 'shop-balance-card');
    const balMain = node('div', 'shop-balance-main');
    const balLabel = node('div', 'shop-balance-label');
    balLabel.append(icon('coin', 'chip-svg'), node('span', '', '当前可用系统积分'));
    balMain.append(
      balLabel,
      node('div', 'shop-balance-num', String(points)),
      node('div', 'shop-balance-sub', '0 体力 · 即时入囊 · 不打断当前剧情')
    );
    const bagBtn = node('button', 'btn-outline', '查看行囊');
    bagBtn.type = 'button';
    bagBtn.onclick = () => openHub('bag');
    balCard.append(balMain, bagBtn);
    pane.append(balCard);

    // 2. Loading / Error / Tiered Catalog
    if (shopLoading && !shopCatalog) {
      const loadingCard = node('section', 'empty-card');
      loadingCard.append(icon('shop'), node('p', '', '正在读取系统商城货架……'));
      pane.append(loadingCard);
    } else if (shopError && !shopCatalog) {
      const errCard = node('section', 'empty-card');
      errCard.append(icon('shop'), node('p', '', shopError));
      const retryBtn = node('button', 'btn-outline', '重新加载商城');
      retryBtn.type = 'button';
      retryBtn.onclick = () => void loadShop(true);
      errCard.append(retryBtn);
      pane.append(errCard);
    } else if (shopCatalog?.items?.length) {
      const redeemedMap = w.shop_state?.redeemed || {};
      const blockReason = transactBlockReason();
      for (const tierKey of ['low', 'mid', 'high']) {
        const tierItems = shopCatalog.items.filter(it => it.tier === tierKey);
        if (!tierItems.length) continue;
        const group = node('section', 'shop-tier-group');
        const tHead = node('div', 'shop-tier-head');
        tHead.append(
          node('h3', '', SHOP_TIER_LABELS[tierKey] || tierKey),
          node('span', '', tierItems.length + ' 件可兑')
        );
        group.append(tHead);

        for (const item of tierItems) {
          const bought = redeemedMap[item.id] ?? item.redeemed_count ?? 0;
          const cap = item.max_per_save;
          const soldOut = cap !== null && cap !== undefined && bought >= cap;
          const enough = points >= item.price;
          const canBuy = !soldOut && enough && canTransactDeterministic();

          const card = node('article', 'shop-item-card' + (soldOut ? ' is-soldout' : ''));
          const top = node('div', 'shop-item-top');
          const pricePill = node('span', 'shop-price-pill');
          pricePill.append(icon('coin', 'chip-svg'), node('span', '', item.price + ' 积分'));
          top.append(node('span', 'shop-item-name', item.name), pricePill);
          card.append(top);

          const tags = node('div', 'item-tags');
          tags.append(node('span', 'item-tag', item.type || '道具'));
          const effMatch = /^host_stamina:([1-9]\d*)$/.exec(item.system_effect || '');
          if (effMatch) tags.append(node('span', 'item-tag is-effect', '体力 +' + effMatch[1]));
          if (item.giftable) tags.append(node('span', 'item-tag', '可赠予在场人物'));
          if (cap !== null && cap !== undefined) {
            tags.append(node('span', 'item-tag' + (soldOut ? ' is-soldout' : ''), soldOut ? ('已售罄 ' + bought + '/' + cap) : ('限兑 ' + bought + '/' + cap)));
          }
          card.append(tags);

          if (item.desc) card.append(node('p', 'item-desc', item.desc));

          const footer = node('div', 'shop-item-footer');
          const buyBtn = node('button', 'btn-gold', soldOut ? '已售罄' : (shopBusy ? '兑换中…' : ('兑换 · ' + item.price + ' 积分')));
          buyBtn.type = 'button';
          buyBtn.disabled = !canBuy;
          buyBtn.onclick = () => void redeemShopItem(item);
          footer.append(buyBtn);

          let reason = '';
          if (soldOut) reason = '已达本档限购上限';
          else if (!enough) reason = '还差 ' + (item.price - points) + ' 积分';
          else if (blockReason) reason = blockReason;
          if (reason) footer.append(node('span', 'shop-reason-hint', reason));

          card.append(footer);
          group.append(card);
        }
        pane.append(group);
      }
    } else {
      const emptyShop = node('section', 'empty-card');
      emptyShop.append(icon('shop'), node('p', '', '商城货架暂未上架商品'));
      pane.append(emptyShop);
    }

    // 3. Recent Redemptions Ledger (persisted in 【商城与回响状态】)
    const recent = (w.shop_state?.recent?.length ? w.shop_state.recent : shopCatalog?.recent) || [];
    if (recent.length) {
      const recBox = node('details', 'settlement-details shop-recent-box');
      recBox.append(node('summary', '', '最近兑换记录（' + recent.length + '） ▾'));
      for (const line of recent) recBox.append(node('p', 'muted', line));
      pane.append(recBox);
    }

    return pane;
  }

  function renderSystemTab() {
    const pane = node('div', 'hub-pane');

    // 1. Display & Haptics Preferences
    const uiGroup = node('section', 'pref-group');
    uiGroup.append(node('h3', '', '剧场沉浸设置'));

    const mkSwitchRow = (title, desc, optionsList, currentVal, onChange) => {
      const row = node('div', 'pref-row');
      const lbl = node('div', 'pref-row-label');
      lbl.append(node('strong', '', title), node('span', '', desc));
      const sw = node('div', 'seg-switch');
      for (const [val, text] of optionsList) {
        const b = node('button', '', text);
        b.type = 'button';
        b.setAttribute('aria-pressed', String(currentVal === val));
        b.onclick = () => { haptic(8); onChange(val); renderWorld(true); };
        sw.append(b);
      }
      row.append(lbl, sw);
      return row;
    };

    const curProtagStyle = snapshot?.preferences?.protagonist_style === 'silent' ? 'silent' : 'faithful';
    uiGroup.append(
      mkSwitchRow('视觉主题', '暗夜黑金剧场 / 昼间暖纸护眼', [['noir', '黑金'], ['ivory', '暖纸']], prefs.theme, v => { prefs.theme = v; savePrefs(); }),
      mkSwitchRow('演播呈现方式', '沉浸幕布待结算完成揭幕，杜绝闪屏与半读回退；即时流式边写边看', [['curtain', '沉浸幕布'], ['stream', '即时流式']], prefs.displayMode, v => {
        prefs.displayMode = v;
        savePrefs();
        signature = '';
        render();
        controls();
      }),
      mkSwitchRow('主角戏份风格', '忠实演绎允许贴合原意的简短主角发言与具身反应（静音不配音）；仅动作感官禁主角台词', [['faithful', '忠实演绎'], ['silent', '仅动作感官']], curProtagStyle, async v => {
        if (backendPrefBusy) return;
        backendPrefBusy = true;
        try {
          const res = await api('preferences', { protagonist_style: v });
          if (snapshot && res?.preferences) snapshot.preferences = res.preferences;
          toast(v === 'faithful' ? '已设为忠实演绎（下幕生效）' : '已设为仅动作感官（下幕生效）');
          renderWorld(true);
        } catch (err) {
          toast('保存偏好失败：' + (err?.message || err));
        } finally {
          backendPrefBusy = false;
        }
      }),
      mkSwitchRow('正文字号', '适应移动端阅读舒适度', [['normal', '标准'], ['large', '大字']], prefs.font, v => { prefs.font = v; savePrefs(); }),
      mkSwitchRow('触感微振', '点按剧情与抉择时轻振反馈', [[true, '开启'], [false, '关闭']], prefs.haptics, v => { prefs.haptics = v; savePrefs(); }),
      mkSwitchRow('场景氛围光影', '随当前地点空镜与情绪变化柔和染光', [[true, '开启'], [false, '静默']], prefs.backdrop, v => { prefs.backdrop = v; savePrefs(); }),
      mkSwitchRow('电影插页', '切场空镜与角色入场横幅，零额外消耗', [[true, '开启'], [false, '纯文字']], prefs.cinemaPlates, v => { prefs.cinemaPlates = v; savePrefs(); signature = ''; render(); }),
      mkSwitchRow('焦点景深阅读', '最新一段全清晰，上文轻柔退远', [[true, '开启'], [false, '关闭']], prefs.readingDof, v => { prefs.readingDof = v; savePrefs(); applyReadingFocus(); })
    );
    pane.append(uiGroup);

    // 2. Fish Audio Key Cache & Voice Quality Tier
    const voiceGroup = node('section', 'pref-group');
    voiceGroup.append(node('h3', '', 'Fish Audio 密钥与语音品质'));

    const keyRow = node('div', 'pref-row');
    const keyLbl = node('div', 'pref-row-label');
    const keyTitle = node('strong', '', 'Fish Audio 密钥（本机受保护缓存）');
    const keyDesc = node('span', '', '正在检测本地受保护缓存 (.cache/fish_api_key.json)…');
    keyLbl.append(keyTitle, keyDesc);
    const keyBadge = node('span', 'cost-chip', '检测中');
    keyRow.append(keyLbl, keyBadge);
    voiceGroup.append(keyRow);

    const keyFormRow = node('div', 'action-row');
    keyFormRow.style.marginTop = '8px';
    const keyInput = node('input', '');
    keyInput.type = 'password';
    keyInput.autocomplete = 'off';
    keyInput.spellcheck = false;
    keyInput.placeholder = '粘贴你的 Fish Audio API Key（不上传 GitHub，一键同步与新档重置均受保护）';
    keyInput.style.cssText = 'flex:1;min-width:140px;padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink);font-size:13px;';
    const keySaveBtn = node('button', 'btn-outline', '保存');
    keySaveBtn.type = 'button';
    const keyTestBtn = node('button', 'btn-outline', '保存并测试');
    keyTestBtn.type = 'button';
    const keyClearBtn = node('button', 'btn-outline', '清除');
    keyClearBtn.type = 'button';
    keyFormRow.append(keyInput, keySaveBtn, keyTestBtn, keyClearBtn);
    voiceGroup.append(keyFormRow);

    const tierRow = node('div', 'pref-row');
    tierRow.style.marginTop = '12px';
    const tierLbl = node('div', 'pref-row-label');
    const tierDesc = node('span', '', '仅三大女主（沈知韫/苏婉青/徐念薇）与旁白启用配音；主角、徐承邺及次要NPC静默无声。旁白恒走零费用免费档。');
    tierLbl.append(node('strong', '', '语音品质分档（默认零费用）'), tierDesc);
    const tierSwitch = node('div', 'seg-switch');
    const tierDefs = [
      ['free', '标准免费 ($0)'],
      ['pro', '稳定付费'],
      ['drama', '旗舰 Drama3']
    ];
    const tierButtons = new Map();
    const markTierActive = activeTier => {
      for (const [tid, btn] of tierButtons) {
        btn.setAttribute('aria-pressed', String(tid === activeTier));
      }
    };
    const refreshVoiceKeyAndTier = async () => {
      try {
        const [st, cfg] = await Promise.all([
          VoiceClient.getFishKeyStatus().catch(() => null),
          loadVoiceConfig().catch(() => null)
        ]);
        if (st && st.configured) {
          keyBadge.textContent = '已配置';
          const srcName = st.source === 'local_cache' ? '本地受保护缓存 (.cache/fish_api_key.json)' : '环境变量';
          keyDesc.textContent = `当前密钥：${st.masked || '已隐藏'} · 来源：${srcName}（一键同步与新档重置均受保护）`;
        } else {
          keyBadge.textContent = '未配置';
          keyDesc.textContent = '尚未保存 Fish API Key；填入保存后主页与声学工坊共用，永不写入同步代码。';
        }
        const curTier = cfg?.__settings__?.voice_tier || 'free';
        markTierActive(curTier);
      } catch (_) {
        keyBadge.textContent = '待检测';
      }
    };
    const doSaveKey = async verify => {
      const val = keyInput.value.trim();
      if (!val) { toast('请先粘贴 Fish Audio API Key'); return; }
      keySaveBtn.disabled = keyTestBtn.disabled = true;
      try {
        const res = await VoiceClient.saveFishKey(val, verify);
        keyInput.value = '';
        invalidateVoiceConfig();
        toast(res.msg || '密钥已保存至本机受保护缓存');
        await refreshVoiceKeyAndTier();
      } catch (err) {
        toast(err.message || '保存密钥失败');
      } finally {
        keySaveBtn.disabled = keyTestBtn.disabled = false;
      }
    };
    keySaveBtn.onclick = () => { haptic(8); void doSaveKey(false); };
    keyTestBtn.onclick = () => { haptic(8); void doSaveKey(true); };
    keyClearBtn.onclick = async () => {
      haptic(8);
      try {
        const res = await VoiceClient.clearFishKey();
        invalidateVoiceConfig();
        toast(res.msg || '已清除本机缓存密钥');
        await refreshVoiceKeyAndTier();
      } catch (err) {
        toast(err.message || '清除失败');
      }
    };
    for (const [tid, label] of tierDefs) {
      const b = node('button', '', label);
      b.type = 'button';
      b.setAttribute('aria-pressed', 'false');
      b.onclick = async () => {
        haptic(8);
        if (tid === 'drama' && !window.confirm('旗舰导演档（Drama 3）按字节计费较高（促销后约 $50/百万字节，仅对三大女主启用，旁白仍免费）。确认切换？')) {
          return;
        }
        try {
          const res = await VoiceClient.setVoiceTier(tid);
          invalidateVoiceConfig();
          markTierActive(res.tier || tid);
          toast(res.msg || '语音品质档位已切换');
        } catch (err) {
          toast(err.message || '档位切换失败');
        }
      };
      tierButtons.set(tid, b);
      tierSwitch.append(b);
    }
    tierRow.append(tierLbl, tierSwitch);
    voiceGroup.append(tierRow);
    pane.append(voiceGroup);
    void refreshVoiceKeyAndTier();

    // 3. Audio & Bridge Operations
    const srvGroup = node('section', 'pref-group');
    srvGroup.append(node('h3', '', '语音与本地连接'));

    const bRow = node('div', 'pref-row');
    const bLbl = node('div', 'pref-row-label');
    bLbl.append(
      node('strong', '', snapshot?.bridge_connected ? 'Operit 桥接已就绪' : 'Operit 桥接未连接'),
      node('span', '', snapshot?.bridge_model ? ('当前模型：' + snapshot.bridge_model.model_id) : '请在 Operit 保持故事桥接开启')
    );
    const dot = node('span', 'status-beacon' + (snapshot?.bridge_connected ? ' is-online' : ''));
    bRow.append(bLbl, dot);
    srvGroup.append(bRow);

    const btnGrid = node('div', 'world-actions');
    btnGrid.style.padding = '0';

    const syncBtn = node('button', 'btn-outline', '同步最新存档');
    syncBtn.type = 'button';
    syncBtn.onclick = async () => { haptic(8); await restore(); toast('已同步最新进度'); };

    const diagBtn = node('button', 'btn-outline', '桥接控制与诊断');
    diagBtn.type = 'button';
    diagBtn.onclick = () => {
      haptic(8);
      $('worldDialog').close();
      openConnectionDialog();
    };

    const voiceLink = node('a', 'btn-outline', '打开语音工坊');
    voiceLink.href = '/admin';
    voiceLink.target = '_blank';
    voiceLink.rel = 'noopener';

    btnGrid.append(syncBtn, diagBtn, voiceLink);
    srvGroup.append(btnGrid);
    pane.append(srvGroup);

    return pane;
  }

  function worldSigFor(w) {
    return JSON.stringify({
      tab: activeHubTab,
      char: selectedChar,
      place: selectedMapPlace,
      prefs,
      canDecide: canDecide(),
      canTransact: canTransactDeterministic(),
      resting: resting(),
      shopBusy,
      shopLoading,
      shopError,
      shopRev: shopCatalog?.revision || '',
      shopCount: shopCatalog?.items?.length || 0,
      bridge: snapshot?.bridge_connected,
      model: snapshot?.bridge_model?.model_id,
      w: w ? {
        loc: w.location,
        weekday: w.weekday,
        cast: w.cast,
        presence: w.presence,
        panels: w.panels,
        items: w.items,
        delivered_items: w.delivered_items,
        buffs: w.buffs,
        vigilance: w.vigilance,
        intel: w.intel,
        tasks: w.tasks,
        shop_state: w.shop_state,
        interaction: w.interaction,
        prog: w.progression,
        micro_states: w.micro_states,
        physiology: w.physiology,
        visual_assets: w.visual_assets
      } : null
    });
  }

  function renderWorld(force = false) {
    const dlg = $('worldDialog');
    if (!force && !dlg.open) return;
    const w = snapshot?.world;
    const sig = worldSigFor(w);
    if (!force && sig === worldSignature) return;
    worldSignature = sig;

    const box = $('worldContent');
    const prevTab = box.dataset.renderedTab || '';
    const prevScroll = prevTab === activeHubTab ? box.scrollTop : 0;
    box.dataset.renderedTab = activeHubTab;

    document.querySelectorAll('#worldTabs .hub-tab').forEach(b => {
      b.setAttribute('aria-selected', String(b.dataset.tab === activeHubTab));
    });
    const tabTitles = { host: '主角档案', roster: '人物羁绊', map: '城市坐标', bag: '委托与行囊', shop: '系统商城', system: '系统设定' };
    $('worldHeading').textContent = tabTitles[activeHubTab] || '档案中心';
    $('worldDangerFooter').hidden = activeHubTab !== 'system';

    box.replaceChildren();
    if (!w) {
      box.append(node('p', 'muted', '正在读取当前存档数据……'));
      return;
    }

    const panels = parsePanels(w.panels);
    if (activeHubTab === 'host') box.append(renderHostTab(w, panels));
    else if (activeHubTab === 'roster') box.append(renderRosterTab(w, panels));
    else if (activeHubTab === 'map') box.append(renderMapTab(w));
    else if (activeHubTab === 'bag') box.append(renderBagTab(w, panels));
    else if (activeHubTab === 'shop') box.append(renderShopTab(w, panels));
    else box.append(renderSystemTab());

    box.scrollTop = prevTab === activeHubTab ? prevScroll : 0;
  }

  function openHub(tab = 'host', charName = '') {
    haptic(8);
    activeHubTab = tab;
    if (charName) selectedChar = charName;
    worldSignature = '';
    if (tab === 'shop') void loadShop();
    renderWorld(true);
    if (!$('worldDialog').open) $('worldDialog').showModal();
  }

  function openConnectionDialog() {
    $('connectionText').textContent = JSON.stringify({
      origin: location.origin,
      revision: snapshot?.revision,
      save_epoch: snapshot?.save_epoch,
      playback: snapshot?.playback,
      task: snapshot?.task,
      bridge: snapshot?.bridge,
      model: snapshot?.bridge_model
    }, null, 2);
    controls();
    $('connectionDialog').showModal();
  }

  function latest(instant = false) {
    const el = $('stream');
    el.scrollTo({ top: el.scrollHeight, behavior: (instant || reducedMotion()) ? 'instant' : 'smooth' });
    $('jump').hidden = true;
    requestAnimationFrame(() => {
      applyReadingFocus();
      schedulePlateParallax();
    });
  }

  function options(id, items) {
    const old = $(id).value;
    $(id).replaceChildren(...items.map(([v, l]) => {
      const o = node('option', '', l);
      o.value = v;
      return o;
    }));
    if (items.some(([v]) => v === old)) $(id).value = old;
  }

  function renderMoveChips(places) {
    const box = $('moveCards');
    if (!box) return;
    box.replaceChildren();
    const cur = $('destination').value;
    for (const place of places) {
      const btn = node('button', 'place-chip', place);
      btn.type = 'button';
      btn.setAttribute('aria-pressed', String(place === cur));
      btn.onclick = () => {
        haptic(8);
        $('destination').value = place;
        box.querySelectorAll('.place-chip').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
        controls();
      };
      box.append(btn);
    }
  }

  function renderHistoryDialog() {
    document.querySelectorAll('#historyFilters .filter-pill').forEach(b => {
      b.setAttribute('aria-pressed', String(b.dataset.filter === historyFilter));
    });
    const list = timeline(historyFilter, { includePlates: false, inHistory: true });
    if (list.length) {
      $('historyList').replaceChildren(...list);
    } else {
      const emp = node('div', 'empty-card');
      emp.append(icon('scroll'), node('p', '', '当前筛选条件下暂无剧情记录'));
      $('historyList').replaceChildren(emp);
    }
  }

  function syncPreviewChrome(existingEl, freshEl) {
    if (!existingEl || !freshEl || existingEl === freshEl) return;
    if (freshEl.dataset?.renderKey) existingEl.dataset.renderKey = freshEl.dataset.renderKey;
    if (freshEl.dataset?.messageId) existingEl.dataset.messageId = freshEl.dataset.messageId;
    if (freshEl.dataset?.msgTextSig) existingEl.dataset.msgTextSig = freshEl.dataset.msgTextSig;
    const wantPreview = !!(freshEl.classList && freshEl.classList.contains('is-preview'));
    if (existingEl.classList) existingEl.classList.toggle('is-preview', wantPreview);
    const oldTag = existingEl.querySelector ? existingEl.querySelector('.stream-preview-tag') : null;
    const newTag = freshEl.querySelector ? freshEl.querySelector('.stream-preview-tag') : null;
    if (oldTag && !newTag) {
      if (typeof oldTag.remove === 'function') oldTag.remove();
    } else if (oldTag && newTag) {
      if (oldTag.textContent !== newTag.textContent) oldTag.textContent = newTag.textContent;
    } else if (!oldTag && newTag) {
      const host = existingEl.querySelector
        ? (existingEl.querySelector('.message-heading') || existingEl.querySelector('.narration-mark'))
        : null;
      if (host && typeof host.append === 'function') host.append(newTag);
    }
  }

  function patchMessageTimeline(container, nextNodes) {
    if (!container) return;
    const oldChildren = Array.from(container.children || []);
    const oldLen = oldChildren.length;

    // Fast path: pure append onto unchanged prefix (zero detachment, zero reflow of existing nodes)
    if (oldLen > 0 && nextNodes.length >= oldLen) {
      let prefixMatches = true;
      for (let i = 0; i < oldLen; i++) {
        const ok = oldChildren[i]?.dataset?.renderKey;
        const nk = nextNodes[i]?.dataset?.renderKey;
        if (!ok || ok !== nk) { prefixMatches = false; break; }
      }
      if (prefixMatches) {
        syncPreviewChrome(oldChildren[oldLen - 1], nextNodes[oldLen - 1]);
        for (let i = oldLen; i < nextNodes.length; i++) {
          const item = nextNodes[i];
          if (item?.classList?.contains('msg')) item.classList.add('is-fresh-enter');
          container.append(item);
        }
        return;
      }
    }

    const wasEmpty = oldLen === 0;
    const byKey = new Map();
    const previewByText = new Map();
    for (const child of oldChildren) {
      const k = child?.dataset?.renderKey;
      if (k) byKey.set(k, child);
      if (child?.classList?.contains('is-preview') && child?.dataset?.msgTextSig && !previewByText.has(child.dataset.msgTextSig)) {
        previewByText.set(child.dataset.msgTextSig, child);
      }
    }

    const resolved = [];
    const kept = new Set();
    for (const cand of nextNodes) {
      const k = cand?.dataset?.renderKey || '';
      const sig = cand?.dataset?.msgTextSig || '';
      if (k && byKey.has(k)) {
        const existing = byKey.get(k);
        byKey.delete(k);
        syncPreviewChrome(existing, cand);
        kept.add(existing);
        resolved.push(existing);
      } else if (sig && !cand?.classList?.contains('is-preview') && previewByText.has(sig)) {
        const morphed = previewByText.get(sig);
        previewByText.delete(sig);
        if (morphed.dataset?.renderKey) byKey.delete(morphed.dataset.renderKey);
        syncPreviewChrome(morphed, cand);
        kept.add(morphed);
        resolved.push(morphed);
      } else {
        if (!wasEmpty && cand?.classList?.contains('msg')) cand.classList.add('is-fresh-enter');
        resolved.push(cand);
      }
    }

    if (typeof container.removeChild === 'function') {
      for (const old of oldChildren) {
        if (!kept.has(old)) container.removeChild(old);
      }
      for (let i = 0; i < resolved.length; i++) {
        const want = resolved[i];
        const cur = container.children[i] || null;
        if (cur !== want) container.insertBefore(want, cur);
      }
    } else {
      container.replaceChildren(...resolved);
    }
  }

  function render() {
    const w = snapshot?.world, p = snapshot?.playback;
    $('policyNote').textContent = progression() ? 'A 5 · B 10 · C 15 体力 · 自定义暂扣15退差' : '按设定与存档推进 · 本段读完后抉择';
    $('sceneTitle').textContent = w?.location || '正在回到现场';
    $('sceneMeta').textContent = w ? (w.cast.length ? w.cast.join(' · ') + ' 在场' : '此刻独处') : '读取存档中…';
    $('revision').textContent = w ? w.interaction.count + ' 段已存剧情' : '';
    renderSceneVector(w?.location || '');

    // Dock & Topbar notification dots
    const hasBagNotice = !!(w?.tasks?.current || w?.tasks?.pending_item || w?.items?.length > 0);
    if ($('dockRosterDot')) $('dockRosterDot').hidden = !(w?.cast?.length > 0);
    if ($('dockBagDot')) $('dockBagDot').hidden = !hasBagNotice;
    if ($('hudMenuDot')) $('hudMenuDot').hidden = !hasBagNotice;

    let pvSig = '';
    if (hasPreviewNodes()) {
      const pvVisCount = Math.min(streamPreview.messages.length, Math.max(1, streamPreview.revealed || 1));
      const pvLast = streamPreview.messages[pvVisCount - 1];
      const pvTagKey = streamPreview.stage === 'settling_retry' ? 'retry'
        : streamPreview.stage === 'settling' ? 'settle' : 'stream';
      pvSig = '|pv:' + streamPreview.request_id + ':' + pvTagKey + ':' + pvVisCount
        + ':' + (pvLast ? (pvLast.kind + ':' + (pvLast.speaker || '') + ':' + String(pvLast.text || '').length) : '');
    }
    const hpSig = handoffPreview
      ? '|hp:' + handoffPreview.segmentId + ':' + handoffPreview.revealed
      : '';
    const va = w?.visual_assets;
    const vaSig = va
      ? '|va:' + Object.keys(va.scenes || {}).sort().join(',') + '/' + Object.entries(va.characters || {}).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => k + ':' + Object.keys(v || {}).sort().join(',')).join(';')
      : '';
    const sig = cache.epoch + ':' + (prefs.cinemaPlates ? 'P1' : 'P0') + ':' + history.map(t => t.id + ':' + t.messages.length + ':' + (t.handoff || '') + ':' + !!t.settlement).join('|') + pvSig + hpSig + vaSig;
    if (sig !== signature) {
      const stream = $('stream');
      const near = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 140;
      const top = stream.scrollTop;
      signature = sig;
      const nodes = timeline('all', { includePlates: prefs.cinemaPlates, inHistory: false });
      patchMessageTimeline($('messages'), nodes);
      const msgTotal = nodes.filter(el => el.classList && el.classList.contains('msg')).length;
      $('messageCount').textContent = String(msgTotal);
      const pvVisible = hasPreviewNodes() ? streamPreview.messages.slice(0, Math.max(1, streamPreview.revealed || 1)) : [];
      const pvSpeaker = pvVisible.filter(m => m.speaker).at(-1)?.speaker || '';
      lastSpeaker = pvSpeaker || history.flatMap(t => t.messages).filter(m => m.speaker).at(-1)?.speaker || '';
      updateSpeakingUI();
      if (near) latest();
      else {
        stream.scrollTop = top;
        $('jump').hidden = false;
        applyReadingFocus();
        schedulePlateParallax();
      }
      if ($('historyDialog').open) renderHistoryDialog();
    }

    $('older').hidden = !hasOlder;
    $('empty').hidden = !!p?.segment_id || hasPreviewNodes();

    // Desktop Side Cast List (Zero-404: Portrait thumb or Editorial Seal Badge) + Flip Focus Card
    const names = w?.cast || [];
    const castEl = $('cast');
    const namesKey = names.map(n => n + ':' + (hasCharacterPortrait(n) ? '1' : '0')).join('|');
    if (castEl && castEl.dataset.names !== namesKey) {
      castEl.dataset.names = namesKey;
      castEl.replaceChildren(...names.map(name => {
        const hasPort = hasCharacterPortrait(name);
        const b = node('button', 'person-button');
        b.type = 'button';
        b.dataset.name = name;
        b.setAttribute('aria-label', hasPort ? ('聚焦' + name + '立绘与档案') : ('查看' + name + '档案卡'));

        if (hasPort) {
          const wrap = node('span', 'person-avatar-wrap');
          const im = node('img');
          im.src = image(name, 'into.png');
          im.alt = '';
          im.decoding = 'async';

          const orbit = svgEl('svg', { viewBox: '0 0 44 44', class: 'speaker-orbit', 'aria-hidden': 'true' });
          orbit.append(svgEl('circle', {
            cx: 22, cy: 22, r: 20, fill: 'none', stroke: 'currentColor',
            'stroke-width': '1.2', 'stroke-dasharray': '5 5'
          }));

          wrap.append(im, orbit);
          b.append(wrap, node('span', '', name));
        } else {
          b.append(
            node('span', 'person-seal-badge', name.slice(0, 1)),
            node('span', '', name),
            node('span', 'person-tag', '档案卡')
          );
        }

        b.onclick = () => {
          haptic(10);
          desktopFocusName = name;
          renderDesktopSideFocus();
          castEl.querySelectorAll('button').forEach(x => {
            x.setAttribute('aria-current', String(x.dataset.name === name));
          });
        };
        return b;
      }));
    }
    const activeDesktopFocus = (desktopFocusName && names.includes(desktopFocusName))
      ? desktopFocusName
      : (primaryPortraitHero(w) || names[0] || lastSpeaker);
    if (castEl) {
      castEl.querySelectorAll('button').forEach(b => {
        b.setAttribute('aria-current', String(b.dataset.name === activeDesktopFocus));
      });
    }
    renderDesktopSideFocus();

    // Mobile Topbar Gaze Pill & Top Peek Drawer
    renderTopPeekDrawer();

    updateBackdrop();

    // Decision Choice Cards with Abyssal Scale Weight Preview & Attribute Resonance Badges
    const turn = current(), decision = turn?.decision, decisionKey = p?.completed ? turn?.id : '';
    if ($('choices').dataset.key !== decisionKey) {
      $('choices').dataset.key = decisionKey || '';
      deckCollapsed = false;
      $('choices').replaceChildren();
      if (decision) {
        $('decisionPrompt').textContent = decision.prompt;
        for (const opt of decision.options) {
          const b = node('button', 'story-option');
          b.type = 'button';
          b.dataset.option = opt.id;

          const seal = node('span', 'option-seal', opt.id);
          const body = node('span', 'option-body');
          const moveDest = opt.operation && opt.operation.code === 'move_player' && opt.operation.destination
            ? opt.operation.destination : '';
          const resonance = deriveOptionResonance(opt.id, w);
          const head = node('span', 'option-head');
          head.append(node('span', 'option-label', LABELS[opt.id] || opt.id));
          if (moveDest) {
            head.append(node('span', 'option-move-badge', '前往 · ' + moveDest));
          }
          if (resonance) {
            head.append(node('span', 'option-resonance-badge is-' + resonance.tone, resonance.text));
          }
          body.append(head, node('span', 'option-text', opt.text));
          b.append(seal, body);

          if (progression()) {
            const cost = node('span', 'option-cost');
            cost.append(icon('energy', 'chip-svg'), node('span', '', String(COSTS[opt.id])));
            b.append(cost);
          }

          const tiltOn = () => previewChoiceWeight(opt.id);
          const tiltOff = () => previewChoiceWeight(null);
          b.addEventListener('mouseenter', tiltOn);
          b.addEventListener('focus', tiltOn);
          b.addEventListener('pointerdown', tiltOn);
          b.addEventListener('mouseleave', tiltOff);
          b.addEventListener('blur', tiltOff);
          b.addEventListener('pointercancel', tiltOff);

          b.onclick = () => {
            previewChoiceWeight(null);
            haptic(14);
            void enqueue(opt.text, opt.operation || null, opt.id);
          };
          $('choices').append(b);
        }
      }
    }

    if (w) {
      const otherPlaces = w.policy.locations.filter(place => place !== w.location);
      options('destination', otherPlaces.map(place => [place, place]));
      renderMoveChips(otherPlaces);
      options('recipient', w.cast.map(name => [name, name]));
      options('item', w.items
        .filter(i => i.fields['当前状态'] === '仓库中'
          && i.giftable !== false && i.fields['可赠予'] !== '否'
          && ['', '无', '未使用', '徐志北'].includes(i.fields['使用对象']))
        .map(i => [i.id, i.name + ' × ' + i.quantity]));
      options('recoveryItem', [
        ['', '请选择恢复道具'],
        ...w.items
          .filter(i => i.fields['当前状态'] === '仓库中'
            && /^host_stamina:[1-9]\d*$/.test(i.fields['系统效果'] || '')
            && ['', '无', '未使用', '徐志北'].includes(i.fields['使用对象']))
          .map(i => [i.id, i.name + ' × ' + i.quantity])
      ]);
      renderBracketChips(w);
    }

    renderSettlement();
    renderWorld(false);
    controls();
    sizing();
  }

  function deriveOptionResonance(optId, w) {
    if (!w) return null;
    const present = (w.cast || []).filter(n => PEOPLE.includes(n)).map(n => getLiveCharStats(n)).filter(Boolean);
    if (!present.length) return null;
    const primary = present[0];
    const maxVig = Math.max(0, ...(w.vigilance?.targets || []).map(t => Number(t.vigilance) || 0));

    if (optId === 'A') {
      if (present.some(s => s.stamina <= 15)) return { text: '断电照护 · 温和收束', tone: 'jade' };
      if (present.some(s => s.micro.momentary_ease)) return { text: '戒备已松 · 乘势定心', tone: 'jade' };
      if (maxVig >= 50) return { text: '稳妥周旋 · 避开耳目', tone: 'gold' };
      return null;
    }
    if (optId === 'B') {
      if (present.some(s => s.phys?.masturbation_trace > 0)) return { text: '自渎心虚 · 羞耻易溃', tone: 'rose' };
      if (present.some(s => s.phys?.pregnancy_stage === 'latent')) return { text: '早孕慵懒 · 防备松弛', tone: 'rose' };
      if (present.some(s => s.shame > 75)) return { text: '暧昧破冰 · 羞耻松动', tone: 'rose' };
      if (present.some(s => s.micro.confusion_debt)) return { text: '心绪未平 · 易触动摇', tone: 'rose' };
      if (primary.affection >= 60) return { text: '亲近默契 · 自然贴近', tone: 'gold' };
      return null;
    }
    if (optId === 'C') {
      if (present.some(s => s.stamina <= 15)) return { text: '体力透支 · 断电锁限制', tone: 'alert' };
      if (present.some(s => s.orgasm >= 70 || s.desire >= 80)) return { text: '临近峰值 · 易触发绝顶', tone: 'climax' };
      if (present.some(s => s.pregnant)) return { text: '孕期锁顶 · 羞耻上限35', tone: 'climax' };
      if (present.some(s => s.hasFluidLock)) return { text: '体液锁定 · 欲火难抑', tone: 'climax' };
      if (present.some(s => s.phys?.unrelieved_streak >= 1)) return { text: '欲求积压 · 渴望纾解', tone: 'rose' };
      if (present.some(s => s.phys?.cycle_phase === '危险期' && s.desire >= 50)) return { text: '危险期躁动 · 受孕高危', tone: 'climax' };
      if (present.some(s => s.affection > 60 && s.shame < 55)) return { text: '合理化闭环 · 豁免掉分', tone: 'rose' };
      if (present.some(s => s.passiveLv >= 2)) return { text: '认知滤镜 · 惩罚减半', tone: 'gold' };
      if (present.some(s => s.shame >= 85 && s.depravity < 15)) return { text: '防线完好 · 强推易掉好感', tone: 'alert' };
      return null;
    }
    return null;
  }

  let lastEffectSegmentId = '';

  function triggerStageEffect(kind, label) {
    if (reducedMotion()) return;
    const stage = $('ambientStage');
    if (stage) {
      stage.classList.remove('fx-stage-climax', 'fx-stage-unlock', 'fx-stage-meltdown');
      void stage.offsetWidth;
      stage.classList.add('fx-stage-' + kind);
      setTimeout(() => stage.classList.remove('fx-stage-' + kind), 1850);
    }
    haptic(kind === 'climax' ? 28 : 16);
    if (label) toast(label);
  }

  function checkTurnStageEffects(turn) {
    if (!turn || !turn.id || turn.id === lastEffectSegmentId) return;
    lastEffectSegmentId = turn.id;
    const changes = turn.settlement?.changes || [];
    if (!changes.length) return;

    for (const who of PEOPLE) {
      const charChanges = changes.filter(c => c.target === who);
      if (!charChanges.length) continue;
      const orgDelta = charChanges.find(c => c.attribute === '高潮');
      const depDelta = charChanges.find(c => c.attribute === '堕落');
      const shameDelta = charChanges.find(c => c.attribute === '羞耻');
      const staDelta = charChanges.find(c => c.attribute === '体力');
      const creampieDelta = charChanges.find(c => c.attribute === '内射');
      const pregDelta = charChanges.find(c => c.attribute === '怀孕');

      if (pregDelta && pregDelta.after === true) {
        triggerStageEffect('climax', `🌺 ${who} · 禁忌骨血着床 · 确诊怀孕`);
        return;
      }
      if (creampieDelta && creampieDelta.delta > 0) {
        triggerStageEffect('climax', `💦 ${who} · 滚烫内射注入 · 体液锁定激活`);
        return;
      }
      if (orgDelta && (orgDelta.after === 0 && orgDelta.before >= 40)) {
        triggerStageEffect('climax', `💥 ${who} · 绝顶清算 · 余韵震颤`);
        return;
      }
      if (depDelta && depDelta.delta > 0) {
        triggerStageEffect('unlock', `🔓 ${who} · 堕落蚀刻 +${depDelta.delta}（当前 ${depDelta.after}）`);
        return;
      }
      if ((shameDelta && shameDelta.delta <= -5) || (staDelta && staDelta.after <= 15)) {
        triggerStageEffect('meltdown', `⚡ ${who} · ${staDelta && staDelta.after <= 15 ? '生理性断电' : '羞耻防线失守'}`);
        return;
      }
    }
  }

  function canonical(value) {
    if (!value) return null;
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]]));
  }

  function same(task, p) {
    return task.request_id === p.request_id
      && task.action === p.action
      && task.base_revision === p.base_revision
      && JSON.stringify(canonical(task.operation)) === JSON.stringify(canonical(p.operation))
      && JSON.stringify(canonical(task.selection)) === JSON.stringify(canonical(p.selection))
      && task.entry_mode === p.entry_mode
      && task.save_epoch === p.save_epoch;
  }

  function applyStreamPreview(pv, fromSnapshot = false) {
    if (!pv || typeof pv !== 'object' || !pv.request_id) return;
    if (!fromSnapshot) {
      if (!active()) {
        earlyStreamPreview = pv;
        scheduleRestore(20);
        return;
      }
      if (snapshot?.task?.request_id && pv.request_id !== snapshot.task.request_id) return;
    }
    const msgs = Array.isArray(pv.messages) ? pv.messages : [];
    const rev = Number(pv.revision) || 0;
    const prev = streamPreview && streamPreview.request_id === pv.request_id ? streamPreview : null;
    if (prev && rev < prev.revision) return;
    const prevRevealed = prev ? prev.revealed : 0;
    const prevCount = prev ? prev.messages.length : 0;
    const revealed = prev ? Math.max(prevRevealed, msgs.length > 0 && prevRevealed === 0 ? 1 : 0) : (msgs.length > 0 ? 1 : 0);
    streamPreview = {
      request_id: pv.request_id,
      stage: pv.stage || 'streaming',
      messages: msgs,
      revision: rev,
      revealed: Math.min(msgs.length, revealed)
    };
    if (!fromSnapshot) {
      if (isCurtainMode()) {
        controls();
      } else {
        render();
        if (prevRevealed === 0 && streamPreview.revealed === 1 && msgs[0]) {
          void speak(msgs[0], 'preview:' + pv.request_id + ':0');
        }
        if (streamPreview.revealed > 0 && msgs.length > streamPreview.revealed && prevCount <= streamPreview.revealed) {
          schedulePrefetchWindow(msgs, 'preview:' + pv.request_id, streamPreview.revealed);
        }
      }
    }
  }

  async function catchUpPlayback(epoch, segmentId, fromRevealed, toRevealed) {
    if (catchingUp || toRevealed <= fromRevealed) return;
    catchingUp = true;
    try {
      let lastFresh = null;
      if (cache.epoch === epoch && snapshot?.playback?.segment_id === segmentId) {
        lastFresh = await api('live/progress', {
          save_epoch: epoch, segment_id: segmentId, revealed: toRevealed, completed: false, catchup: true
        });
      }
      handoffPreview = null;
      if (lastFresh) {
        absorb(lastFresh);
        const turn = current();
        if (turn?.messages) {
          schedulePrefetchWindow(turn.messages, turn.id, toRevealed);
        }
      } else {
        render();
      }
    } catch (_) {
      handoffPreview = null;
      render();
    } finally {
      catchingUp = false;
      controls();
    }
  }

  function absorb(fresh) {
    const prevSegmentId = snapshot?.playback?.segment_id;
    const prevWasActive = active();
    const prevPreview = streamPreview;
    const prevPreviewRevealed = prevPreview ? (prevPreview.revealed || 0) : 0;
    if (cache.epoch && cache.epoch !== fresh.save_epoch) {
      cache = { epoch: fresh.save_epoch, draft: '', pending: null, voice: cache.voice };
      $('input').value = '';
      history = [];
      signature = '';
      worldSignature = '';
      olderCursor = null;
      missing = false;
      mismatch = false;
      streamPreview = null;
      earlyStreamPreview = null;
      handoffPreview = null;
      curtainTrackedReqId = '';
      error = '已切换至新档，旧进度与行动已隔离。';
    }
    const freshActive = ['preparing', 'queued', 'generating', 'validating', 'refund_pending'].includes(fresh.task?.status);
    let seamlessVoiceHandoff = false;
    let catchUpTarget = 0;
    let shouldSpeakFirstPreview = false;

    if (freshActive) {
      const candidatePv = fresh.stream_preview
        || (earlyStreamPreview && earlyStreamPreview.request_id === fresh.task?.request_id ? earlyStreamPreview : null);
      if (earlyStreamPreview && earlyStreamPreview.request_id === fresh.task?.request_id) {
        earlyStreamPreview = null;
      }
      if (candidatePv) {
        const hadSameReq = prevPreview && prevPreview.request_id === candidatePv.request_id;
        const beforeRev = hadSameReq ? prevPreviewRevealed : 0;
        applyStreamPreview(candidatePv, true);
        if (!isCurtainMode() && beforeRev === 0 && streamPreview && streamPreview.revealed === 1 && streamPreview.messages[0]) {
          shouldSpeakFirstPreview = true;
        }
      }
    } else {
      earlyStreamPreview = null;
      if (!isCurtainMode() && prevPreview && fresh.playback?.segment_id && fresh.playback.segment_id !== prevSegmentId) {
        const segId = fresh.playback.segment_id;
        const prefix = 'preview:' + prevPreview.request_id + ':';
        for (const [k, v] of [...audioCache.entries()]) {
          if (k.startsWith(prefix)) {
            const idx = k.slice(prefix.length);
            audioCache.set(segId + ':' + idx, v);
          }
        }
        if (speakingMessageId && speakingMessageId.startsWith(prefix)) {
          const idx = speakingMessageId.slice(prefix.length);
          speakingMessageId = segId + ':' + idx;
          if (audioMessage && audioMessage.id.startsWith(prefix)) audioMessage.id = segId + ':' + idx;
          seamlessVoiceHandoff = true;
        }
        if (prevPreview.revealed >= 1 && fresh.playback.revealed < prevPreview.revealed && !fresh.playback.completed) {
          catchUpTarget = Math.min(prevPreview.revealed, fresh.playback.total || 1);
          handoffPreview = {
            segmentId: segId,
            request_id: prevPreview.request_id,
            messages: prevPreview.messages.slice(),
            revealed: catchUpTarget
          };
        }
      }
      streamPreview = null;
    }

    if (prevSegmentId !== fresh.playback?.segment_id && !seamlessVoiceHandoff) {
      stopVoice();
      audioMessage = null;
    }
    const prevEpoch = cache.epoch;
    cache.epoch = fresh.save_epoch;
    snapshot = fresh;
    if (prevEpoch && prevEpoch !== fresh.save_epoch) {
      shopCatalog = null;
      shopError = '';
    }
    if (!fresh.playback?.segment_id && Array.isArray(fresh.history) && fresh.history.length === 0) {
      history = [];
      signature = '';
      $('stream').scrollTop = 0;
    } else {
      const map = new Map(history.map(t => [t.id, t]));
      fresh.history.forEach(t => map.set(t.id, t));
      history = [...map.values()].sort((a, b) => a.sequence - b.sequence);
    }
    if (!audioMessage && fresh.playback?.revealed) {
      const turn = history.find(t => t.id === fresh.playback.segment_id);
      const i = fresh.playback.revealed - 1;
      if (turn?.messages[i]) audioMessage = { m: turn.messages[i], id: turn.id + ':' + i };
    }
    if (prevSegmentId && fresh.playback?.segment_id && fresh.playback.segment_id !== prevSegmentId) {
      const settledTurn = history.find(t => t.id === fresh.playback.segment_id);
      if (settledTurn) checkTurnStageEffects(settledTurn);
    } else if (!prevSegmentId && fresh.playback?.segment_id) {
      lastEffectSegmentId = fresh.playback.segment_id;
    }
    if (olderCursor === null) hasOlder = fresh.has_older;
    save();
    render();
    if (shouldSpeakFirstPreview && streamPreview?.messages?.[0]) {
      const firstId = 'preview:' + streamPreview.request_id + ':0';
      if (speakingMessageId !== firstId) {
        void speak(streamPreview.messages[0], firstId);
      }
      if (streamPreview.messages.length > 1) {
        schedulePrefetchWindow(streamPreview.messages, 'preview:' + streamPreview.request_id, 1);
      }
    } else if (!freshActive && prevWasActive && fresh.playback?.segment_id && fresh.playback.segment_id !== prevSegmentId && !seamlessVoiceHandoff) {
      const committedTurn = history.find(t => t.id === fresh.playback.segment_id);
      const revIdx = Math.max(0, (fresh.playback.revealed || 1) - 1);
      if (committedTurn?.messages?.[revIdx]) {
        void speak(committedTurn.messages[revIdx], committedTurn.id + ':' + revIdx);
        schedulePrefetchWindow(committedTurn.messages, committedTurn.id, revIdx + 1);
      }
    }
    if ($('worldDialog')?.open && activeHubTab === 'shop' && (!shopCatalog || shopCatalog.revision !== fresh.revision)) {
      void loadShop();
    }
    if (catchUpTarget > fresh.playback.revealed) {
      void catchUpPlayback(fresh.save_epoch, fresh.playback.segment_id, fresh.playback.revealed, catchUpTarget);
    }
  }

  function scheduleRestore(delayMs = 40) {
    if (posting || polling || progressing) {
      restoreQueued = true;
      return;
    }
    if (restoreTimer !== null) return;
    restoreTimer = setTimeout(() => {
      restoreTimer = null;
      void restore();
    }, delayMs);
  }

  async function restore({ preserveError = false } = {}) {
    if (posting || polling || progressing) {
      restoreQueued = true;
      return;
    }
    polling = true;
    restoreQueued = false;
    controls();
    try {
      const fresh = await api('live');
      online = true;
      if (!preserveError) error = '';
      if (cache.pending) {
        let task;
        try { task = (await api('tasks/' + encodeURIComponent(cache.pending.request_id))).task; }
        catch (e) { if (e.status !== 404) throw e; }
        missing = !task;
        mismatch = !!task && !same(task, cache.pending);
        if (task && !mismatch) {
          cache.pending = null;
          missing = false;
        }
      }
      absorb(fresh);
    } catch (e) {
      online = false;
      error = e.message;
    } finally {
      polling = false;
      controls();
      if (restoreQueued) {
        restoreQueued = false;
        scheduleRestore(30);
      }
    }
  }

  async function advance(tapCoords = null) {
    if (hasPreviewNodes()) {
      if (Date.now() - lastTap < 250) return;
      if (streamPreview.revealed < streamPreview.messages.length) {
        lastTap = Date.now();
        haptic(10);
        if (tapCoords) spawnTapRipple(tapCoords.x, tapCoords.y);
        unlock();
        stopVoice();
        streamPreview.revealed += 1;
        render();
        latest();
        const idx = streamPreview.revealed - 1;
        const m = streamPreview.messages[idx];
        if (m) void speak(m, 'preview:' + streamPreview.request_id + ':' + idx);
        schedulePrefetchWindow(streamPreview.messages, 'preview:' + streamPreview.request_id, idx + 1);
      }
      return;
    }
    if (baseBlocked() || !snapshot?.playback?.segment_id || snapshot.playback.completed || Date.now() - lastTap < 300) return;
    lastTap = Date.now();
    haptic(10);
    if (tapCoords) spawnTapRipple(tapCoords.x, tapCoords.y);
    unlock();
    stopVoice();
    progressing = true;
    error = '';
    controls();
    const p = snapshot.playback;
    const revealed = Math.min(p.total, p.revealed + 1);
    const completed = p.revealed === p.total;
    try {
      const fresh = await api('live/progress', { save_epoch: cache.epoch, segment_id: p.segment_id, revealed, completed });
      absorb(fresh);
      latest();
      if (!completed) {
        const turn = current(), m = turn?.messages[revealed - 1];
        if (m) void speak(m, turn.id + ':' + (revealed - 1));
        if (turn?.messages) schedulePrefetchWindow(turn.messages, turn.id, revealed);
      }
    } catch (e) {
      error = '演播进度待确认：' + e.message;
    } finally {
      progressing = false;
      controls();
    }
  }

  async function dispatch() {
    if (posting || polling || progressing || !cache.pending) return;
    posting = true;
    stopVoice();
    error = '';
    controls();
    try {
      await api('tasks', cache.pending);
    } catch (e) {
      error = '提交状态待确认：' + e.message;
    } finally {
      posting = false;
      await restore({ preserveError: true });
      controls();
    }
  }

  async function enqueue(text, op = null, optionId = 'CUSTOM') {
    if (baseBlocked() || !text.trim() || (optionId !== 'BEGIN' && !canDecide())) return;
    if (optionId !== 'REST' && optionId !== 'BEGIN' && (
      resting() || !afford(optionId === 'CUSTOM'
        ? (/^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test(text) ? 0 : 15)
        : COSTS[optionId])
    )) return;
    const selected = { segment_id: optionId === 'BEGIN' ? '' : snapshot.playback.segment_id, option_id: optionId };
    cache.pending = {
      request_id: 'live-' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2)),
      base_revision: snapshot.revision,
      save_epoch: cache.epoch,
      entry_mode: 'live_interaction',
      action: text,
      selection: selected,
      ...(op ? { operation: op } : {})
    };
    if (optionId === 'CUSTOM' && !op) cache.draft = '';
    missing = false;
    mismatch = false;
    if (!save()) {
      cache.pending = null;
      cache.draft = text;
      controls();
      return;
    }
    if (optionId === 'CUSTOM' && !op) {
      $('input').value = '';
      $('input').style.height = 'auto';
    }
    await dispatch();
  }

  function toggleVoice() {
    haptic(8);
    unlock();
    cache.voice = !cache.voice;
    save();
    if (!cache.voice) {
      stopVoice();
      toast('语音已静音');
    } else {
      toast('语音已开启');
      if (audioMessage) void speak(audioMessage.m, audioMessage.id);
    }
    controls();
  }

  // Wire HUD, Navigation Dock & Tabs
  $('sceneLocationBtn').onclick = () => openHub('map');
  $('staminaHud').onclick = () => openHub('host');
  $('hudVoiceBtn').onclick = toggleVoice;
  $('settingsBtn').onclick = () => openHub('system');
  $('world').onclick = () => openHub(activeHubTab || 'host');

  document.querySelectorAll('[data-hub-tab]').forEach(btn => {
    btn.onclick = () => openHub(btn.dataset.hubTab);
  });
  document.querySelectorAll('#worldTabs .hub-tab').forEach(btn => {
    btn.onclick = () => {
      haptic(8);
      activeHubTab = btn.dataset.tab;
      if (activeHubTab === 'shop') void loadShop();
      renderWorld(true);
    };
  });

  const openHistorySheet = () => { haptic(8); renderHistoryDialog(); $('historyDialog').showModal(); };
  $('dockHistoryBtn').onclick = openHistorySheet;
  $('history').onclick = openHistorySheet;
  if ($('playbackHistoryBtn')) $('playbackHistoryBtn').onclick = openHistorySheet;
  if ($('deckToggleBtn')) {
    $('deckToggleBtn').onclick = () => {
      haptic(8);
      deckCollapsed = true;
      controls();
      sizing();
    };
  }
  if ($('deckCollapsedBar')) {
    $('deckCollapsedBar').onclick = () => {
      haptic(8);
      deckCollapsed = false;
      controls();
      requestAnimationFrame(() => {
        sizing();
        latest();
      });
    };
  }
  if ($('customFormToggle')) {
    $('customFormToggle').onclick = () => {
      haptic(6);
      customComposerExpanded = !customComposerExpanded;
      controls();
      requestAnimationFrame(() => {
        sizing();
        if (customComposerExpanded) $('input')?.focus();
      });
    };
  }
  document.querySelectorAll('#historyFilters .filter-pill').forEach(btn => {
    btn.onclick = () => {
      haptic(6);
      historyFilter = btn.dataset.filter;
      renderHistoryDialog();
    };
  });

  $('portraitStatsBtn').onclick = () => {
    const target = portraitName;
    $('portraitDialog').close();
    openHub('roster', target);
  };

  // Wire Gameplay & Action Controls
  $('rest').onclick = () => { haptic(14); void enqueue('继续休息', null, 'REST'); };
  $('useRecovery').onclick = () => {
    if ($('useRecovery').disabled) return;
    haptic(14);
    void enqueue('使用恢复道具 ' + $('recoveryItem').value, { code: 'use_recovery_item', item_id: $('recoveryItem').value });
  };
  $('recoveryItem').onchange = controls;
  $('cancelTask').onclick = async () => {
    if (posting || !snapshot?.task) return;
    haptic(12);
    posting = true;
    controls();
    try { await api('tasks/' + encodeURIComponent(snapshot.task.request_id) + '/cancel', {}); toast('已取消并退还预扣'); }
    catch (e) { error = e.message; }
    finally { posting = false; await restore({ preserveError: true }); }
  };
  $('advance').onclick = () => void advance();
  $('begin').onclick = () => { haptic(14); void enqueue('继续当前剧情', null, 'BEGIN'); };
  $('voiceToggle').onclick = toggleVoice;
  $('replayVoice').onclick = () => {
    if (!audioMessage) return;
    haptic(8);
    unlock();
    cache.voice = true;
    save();
    void speak(audioMessage.m, audioMessage.id);
  };

  $('stream').addEventListener('click', e => {
    if (e.target.closest('button,a,input,textarea,select,summary,details') || getSelection()?.toString()) return;
    void advance({ x: e.clientX, y: e.clientY });
  });
  $('stream').addEventListener('keydown', e => {
    if (e.target === $('stream') && ['Enter', ' '].includes(e.key)) {
      e.preventDefault();
      void advance();
    }
  });

  $('form').onsubmit = e => {
    e.preventDefault();
    haptic(14);
    void enqueue($('input').value);
  };
  $('input').addEventListener('input', () => {
    cache.draft = $('input').value;
    save();
    controls();
    $('input').style.height = 'auto';
    $('input').style.height = Math.min($('input').scrollHeight, 92) + 'px';
    sizing();
  });
  $('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $('form').requestSubmit();
    }
  });

  $('refresh').onclick = async () => { haptic(8); await restore(); toast('已同步现场进度'); };
  $('checkPending').onclick = () => void restore();
  $('resendPending').onclick = dispatch;
  $('editPending').onclick = () => {
    if (!cache.pending || !missing || mismatch || posting || polling) return;
    cache.draft = [cache.pending.action, cache.draft].filter(Boolean).join('\n');
    cache.pending = null;
    $('input').value = cache.draft;
    save();
    controls();
  };
  async function runRetry(resumeStage2) {
    if (baseBlocked() || !snapshot?.task?.request_id) return;
    haptic(12);
    posting = true;
    controls();
    const payload = resumeStage2 ? { resume_stage2: true } : { resume_stage2: false };
    try { await api('tasks/' + encodeURIComponent(snapshot.task.request_id) + '/retry', payload); }
    catch (e) { error = e.message; }
    finally { posting = false; await restore({ preserveError: true }); }
  }
  $('retry').onclick = () => void runRetry(Boolean(snapshot?.task?.has_stage1_checkpoint));

  const openActionSheet = () => {
    if (blocked()) return;
    haptic(8);
    $('actionStatus').textContent = '出行与赠礼将作为本次自定义行动提交。';
    render();
    $('actionDialog').showModal();
  };
  $('actions').onclick = openActionSheet;
  if ($('quickActionBtn')) $('quickActionBtn').onclick = openActionSheet;

  $('moveForm').onsubmit = async e => {
    e.preventDefault();
    if ($('move').disabled) return;
    haptic(14);
    const dest = $('destination').value;
    $('actionDialog').close();
    await enqueue('前往' + dest, { code: 'move_player', destination: dest });
  };
  $('giveForm').onsubmit = async e => {
    e.preventDefault();
    if ($('give').disabled) return;
    haptic(14);
    const id = $('item').value, who = $('recipient').value;
    const item = snapshot.world.items.find(i => i.id === id);
    $('actionDialog').close();
    await enqueue('把' + item.name + '整组交给' + who, { code: 'transfer_item', item_id: id, recipient: who });
  };
  $('destination').onchange = () => {
    const val = $('destination').value;
    $('moveCards')?.querySelectorAll('.place-chip').forEach(b => b.setAttribute('aria-pressed', String(b.textContent === val)));
    controls();
  };
  $('item').onchange = controls;
  $('recipient').onchange = controls;

  $('newGame').onclick = () => {
    haptic(10);
    $('worldDialog').close();
    $('newGameStatus').textContent = '';
    resetRequest = null;
    $('newGameDialog').showModal();
    controls();
  };
  $('confirmNewGame').onclick = async () => {
    if (baseBlocked()) return;
    haptic(16);
    posting = true;
    controls();
    resetRequest = resetRequest || {
      request_id: 'reset-' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)),
      save_epoch: cache.epoch,
      confirm: 'new_game'
    };
    try {
      await api('new-game', resetRequest);
      $('newGameDialog').close();
      toast('已开启全新存档');
    } catch (e) {
      $('newGameStatus').textContent = e.message + '；可按原编号再次确认。';
    } finally {
      posting = false;
      await restore({ preserveError: true });
    }
  };

  $('older').onclick = async () => {
    if (posting || polling || progressing || !history.length) return;
    haptic(8);
    polling = true;
    controls();
    try {
      const fresh = await api('live?before=' + history[0].sequence);
      if (fresh.save_epoch !== cache.epoch) {
        polling = false;
        await restore();
        return;
      }
      const map = new Map(history.map(t => [t.id, t]));
      fresh.history.forEach(t => map.set(t.id, t));
      history = [...map.values()].sort((a, b) => a.sequence - b.sequence);
      hasOlder = fresh.has_older;
      olderCursor = history[0]?.sequence || 0;
      render();
    } catch (e) {
      error = e.message;
    } finally {
      polling = false;
      controls();
    }
  };

  $('connection').onclick = () => { haptic(8); openConnectionDialog(); };
  for (const [id, action] of [['bridgeStart', 'start'], ['bridgeStop', 'stop']]) {
    $(id).onclick = async () => {
      if (posting) return;
      haptic(10);
      posting = true;
      controls();
      try { await api('bridge/control', { action }); toast(action === 'start' ? '已请求启动桥接' : '已暂停桥接'); }
      catch (e) { error = e.message; }
      finally { posting = false; await restore({ preserveError: true }); }
    };
  }

  async function sendBridgeControl(payload, okMessage) {
    if (posting) return;
    posting = true; haptic(10); controls();
    try {
      await api('bridge/control', payload);
      if (okMessage) toast(okMessage);
    } catch (e) { error = e.message; }
    finally { posting = false; await restore({ preserveError: true }); }
  }
  function parseModelPair(val) {
    const idx = String(val || '').indexOf('::');
    if (idx <= 0) return null;
    return { provider_id: val.slice(0, idx), model_id: val.slice(idx + 2) };
  }

  $('storySessionPolicy').onchange = event => sendBridgeControl(
    { action: 'session_policy', session_policy: event.target.value }, '已请求更新会话方式'
  );
  $('storySessionReset').onclick = () => sendBridgeControl(
    { action: 'reset_session' }, '已请求下次行动新建会话，旧聊天保留'
  );
  if ($('storyMaxTurns')) {
    $('storyMaxTurns').onchange = event => {
      const n = Number(event.target.value);
      if (!Number.isInteger(n) || n < 2 || n > 30) return;
      void sendBridgeControl({ action: 'max_turns', max_turns: n }, '已请求将防漂移切窗设为每 ' + n + ' 轮');
    };
  }
  if ($('storyPrimaryMode')) {
    $('storyPrimaryMode').onchange = event => {
      const mode = event.target.value === 'fixed' ? 'fixed' : 'slot';
      const bridge = snapshot?.bridge;
      if (mode === 'slot') {
        const slot = bridge?.primary_function_type || 'CHAT';
        void sendBridgeControl({ action: 'primary_model', primary_model_mode: 'slot', primary_function_type: slot }, '主模型已切回跟随 ' + slot + ' 槽');
      } else {
        const avail = Array.isArray(bridge?.available_models) ? bridge.available_models : [];
        const bm = snapshot?.bridge_model;
        const pick = (bm && bm.provider_id && bm.model_id)
          ? { provider_id: bm.provider_id, model_id: bm.model_id }
          : avail[0];
        if (!pick) { error = '未检测到 Operit 已配置模型，请先在 Operit 添加模型。'; controls(); return; }
        void sendBridgeControl({
          action: 'primary_model',
          primary_model_mode: 'fixed',
          primary_provider_id: pick.provider_id,
          primary_model_id: pick.model_id,
        }, '主模型已设为故事专属：' + pick.model_id);
      }
    };
  }
  if ($('storyPrimaryTarget')) {
    $('storyPrimaryTarget').onchange = event => {
      const mode = $('storyPrimaryMode')?.value === 'fixed' ? 'fixed' : 'slot';
      const val = event.target.value;
      if (!val) return;
      if (mode === 'fixed') {
        const parsed = parseModelPair(val);
        if (!parsed) return;
        void sendBridgeControl({
          action: 'primary_model',
          primary_model_mode: 'fixed',
          primary_provider_id: parsed.provider_id,
          primary_model_id: parsed.model_id,
        }, '故事主模型已切换为 ' + parsed.model_id);
      } else {
        void sendBridgeControl({
          action: 'primary_model',
          primary_model_mode: 'slot',
          primary_function_type: val,
        }, '主模型功能槽已切换为 ' + val);
      }
    };
  }
  if ($('storyDualStage')) {
    $('storyDualStage').onchange = event => {
      const dual = event.target.value === 'dual';
      void sendBridgeControl({ action: 'dual_stage', dual_stage: dual }, dual ? '已切换为双阶段流式演播' : '已切换为单阶段精简模式');
    };
  }
  if ($('storySettlementSlot')) {
    $('storySettlementSlot').onchange = event => {
      const slot = event.target.value;
      if (!slot) return;
      bridgeBindSyncedKey = '';
      void sendBridgeControl({ action: 'settlement_slot', settlement_function_type: slot }, '后台结算槽位已切换为 ' + slot);
    };
  }
  if ($('storyBindSlotBtn')) {
    $('storyBindSlotBtn').onclick = () => {
      const slot = $('storySettlementSlot')?.value || snapshot?.bridge?.settlement_function_type || 'SUMMARY';
      const parsed = parseModelPair($('storyBindSlotModel')?.value);
      if (!parsed) { error = '请先选择要绑定的目标模型。'; controls(); return; }
      bridgeBindSyncedKey = '';
      void sendBridgeControl({
        action: 'bind_function_slot',
        slot,
        provider_id: parsed.provider_id,
        model_id: parsed.model_id,
        use_as_settlement: true,
      }, '已请求将 ' + slot + ' 槽绑定为 ' + parsed.model_id);
    };
  }
  if ($('storySettlementThinkingMode')) {
    $('storySettlementThinkingMode').onchange = event => {
      const mode = ['auto', 'off', 'on'].includes(event.target.value) ? event.target.value : 'auto';
      const msg = mode === 'auto'
        ? '已请求设为智能自适应思考（重试自动升档）'
        : mode === 'on' ? '已请求设为副模型常开深度思考' : '已请求设为副模型常关非思考（最快）';
      void sendBridgeControl({
        action: 'settlement_thinking',
        settlement_thinking_mode: mode,
        settlement_thinking: mode === 'on'
      }, msg);
    };
  }
  if ($('curtainCancelBtn')) {
    $('curtainCancelBtn').onclick = () => {
      if ($('cancelTask') && typeof $('cancelTask').onclick === 'function') {
        $('cancelTask').onclick();
      }
    };
  }
  if ($('curtainRetryBtn')) {
    $('curtainRetryBtn').onclick = () => {
      void runRetry(Boolean(snapshot?.task?.has_stage1_checkpoint));
    };
  }
  if ($('curtainFullRetryBtn')) {
    $('curtainFullRetryBtn').onclick = () => {
      void runRetry(false);
    };
  }
  if ($('curtainDismissBtn')) {
    $('curtainDismissBtn').onclick = () => {
      haptic(8);
      curtainTrackedReqId = '';
      updateStageCurtain();
    };
  }

  function closeSSE() {
    if (sseRetryTimer !== null) {
      clearTimeout(sseRetryTimer);
      sseRetryTimer = null;
    }
    if (sse) {
      try { sse.close(); } catch (_) {}
      sse = null;
    }
    sseOpen = false;
  }

  function trackSseEventSeq(event) {
    const idNum = Number(event?.lastEventId);
    if (Number.isInteger(idNum) && idNum > lastSseSeq) lastSseSeq = idNum;
  }

  function connectSSE() {
    if (typeof EventSource === 'undefined' || document.hidden) return;
    if (sse && sse.readyState !== 2) return;
    closeSSE();
    try {
      const qs = lastSseSeq > 0 ? '?since=' + encodeURIComponent(String(lastSseSeq)) : '';
      const es = new EventSource('/api/story/stream' + qs);
      sse = es;
      es.onopen = () => {
        if (sse !== es) return;
        sseOpen = true;
        sseRetryAttempt = 0;
        scheduleRestore(30);
      };
      es.addEventListener('ready', event => {
        try {
          const info = JSON.parse(event.data);
          if (Number.isInteger(info?.seq) && info.seq > lastSseSeq) lastSseSeq = info.seq;
        } catch (_) {}
      });
      es.addEventListener('story_stream', event => {
        trackSseEventSeq(event);
        try {
          const pv = JSON.parse(event.data);
          applyStreamPreview(pv, false);
        } catch (_) {}
      });
      es.addEventListener('committed', event => { trackSseEventSeq(event); scheduleRestore(20); });
      es.addEventListener('task_state', event => { trackSseEventSeq(event); scheduleRestore(40); });
      es.addEventListener('bridge_state', event => { trackSseEventSeq(event); scheduleRestore(80); });
      es.addEventListener('save_reset', event => { trackSseEventSeq(event); scheduleRestore(20); });
      es.onerror = () => {
        if (sse !== es) return;
        sseOpen = false;
        try { es.close(); } catch (_) {}
        sse = null;
        if (!document.hidden && sseRetryTimer === null) {
          const delays = [1500, 3000, 6000, 12000, 20000];
          const delay = delays[Math.min(sseRetryAttempt, delays.length - 1)];
          sseRetryAttempt += 1;
          sseRetryTimer = setTimeout(() => {
            sseRetryTimer = null;
            connectSSE();
          }, delay);
        }
      };
    } catch (_) {
      sseOpen = false;
    }
  }

  // Close Buttons & Backdrop Tap-to-Dismiss on Sheets
  document.querySelectorAll('[data-close]').forEach(b => {
    b.onclick = () => { haptic(6); b.closest('dialog').close(); };
  });
  document.querySelectorAll('dialog.sheet-dialog').forEach(dlg => {
    dlg.addEventListener('click', e => {
      if (e.target === dlg) { haptic(6); dlg.close(); }
    });
  });
  // Top Peek Drawer, Gaze Lens & Hold-to-Gaze Global Controls
  if ($('topPeekClose')) {
    $('topPeekClose').onclick = () => {
      haptic(6);
      topPeekOpen = false;
      renderTopPeekDrawer();
    };
  }
  if ($('gazeLensClose')) {
    $('gazeLensClose').onclick = () => {
      haptic(6);
      closeGazeLens();
    };
  }
  if ($('gazeLens')) {
    $('gazeLens').addEventListener('click', e => {
      if (e.target === $('gazeLens') && gazeLensLocked) {
        haptic(6);
        closeGazeLens();
      }
    });
  }
  const releaseHoldGaze = () => {
    if (gazeHoldCleanup) {
      const fn = gazeHoldCleanup;
      gazeHoldCleanup = null;
      fn();
    } else if (gazeHoldActive) {
      closeGazeLens();
    }
  };
  window.addEventListener('pointerup', releaseHoldGaze);
  window.addEventListener('pointercancel', releaseHoldGaze);
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if ($('gazeLens')?.classList.contains('is-open')) {
      closeGazeLens();
    } else if (topPeekOpen) {
      topPeekOpen = false;
      renderTopPeekDrawer();
    }
  });

  $('jump').onclick = () => { haptic(8); latest(); };
  $('stream').addEventListener('scroll', () => {
    if ($('stream').scrollHeight - $('stream').scrollTop - $('stream').clientHeight < 70) {
      $('jump').hidden = true;
    }
    applyReadingFocus();
    schedulePlateParallax();
  }, { passive: true });

  let lastComposerHeight = 0;
  function sizing() {
    const stream = $('stream');
    const wasNearBottom = stream
      ? (stream.scrollHeight - stream.scrollTop - stream.clientHeight < 96)
      : false;
    const compH = $('composer') ? Math.ceil($('composer').getBoundingClientRect().height) : 0;
    const setEl = $('settlement');
    const setH = setEl && !setEl.hidden ? Math.ceil(setEl.getBoundingClientRect().height) : 0;
    document.documentElement.style.setProperty('--bottom', (compH + setH) + 'px');
    if (compH > lastComposerHeight + 12 && wasNearBottom && stream) {
      requestAnimationFrame(() => {
        stream.scrollTop = stream.scrollHeight;
      });
    }
    lastComposerHeight = compH;
  }
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(sizing);
    ro.observe($('composer'));
    if ($('settlement')) ro.observe($('settlement'));
  }

  let baseViewportHeight = window.innerHeight || 0;
  let lastOrientationWidth = window.innerWidth || 0;
  function isEditableFocused() {
    const activeEl = document.activeElement;
    if (!activeEl) return false;
    const tag = activeEl.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || activeEl.isContentEditable;
  }
  function viewport() {
    const v = window.visualViewport;
    const curW = window.innerWidth || 0;
    const curH = window.innerHeight || 0;
    if (Math.abs(curW - lastOrientationWidth) > 80) {
      lastOrientationWidth = curW;
      baseViewportHeight = curH;
    } else if (!isEditableFocused() && curH > baseViewportHeight) {
      baseViewportHeight = curH;
    }
    const visualH = v ? v.height : curH;
    const visualOffset = v ? v.offsetTop : 0;
    // Only apply --keyboard offset when browser did NOT already shrink layout viewport (resizes-visual)
    const visualDelta = v ? Math.max(0, Math.round(curH - visualH - visualOffset)) : 0;
    const layoutShrink = Math.max(0, Math.round(baseViewportHeight - visualH));
    const kbOpen = isEditableFocused() && (layoutShrink > 120 || visualDelta > 120);
    document.documentElement.style.setProperty('--keyboard', (visualDelta > 20 ? visualDelta : 0) + 'px');
    document.body.classList.toggle('kb-open', kbOpen);
    if (kbOpen && topPeekOpen) {
      topPeekOpen = false;
      renderTopPeekDrawer();
    }
    sizing();
  }
  if (window.visualViewport) {
    visualViewport.addEventListener('resize', viewport);
    visualViewport.addEventListener('scroll', viewport);
  }
  window.addEventListener('resize', viewport);
  document.addEventListener('focusin', () => setTimeout(viewport, 60));
  document.addEventListener('focusout', () => setTimeout(viewport, 120));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopVoice();
      closeSSE();
    } else {
      invalidateVoiceConfig();
      sseRetryAttempt = 0;
      connectSSE();
      void restore();
    }
  });
  window.addEventListener('pagehide', () => {
    stopVoice();
    closeSSE();
    urls.clear();
  });

  initAmbientRain();
  applyPrefs();
  $('input').value = cache.draft;
  save();
  render();
  connectSSE();
  void restore();
  setInterval(() => { if (!document.hidden && !sseOpen) void restore(); }, 15000);
})();

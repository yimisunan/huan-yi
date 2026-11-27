'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const KEY = 'abyss_official_live_v1';
  const PREF_KEY = 'abyss_ui_prefs_v1';
  const PEOPLE = ['沈知韫', '苏婉青', '徐念薇'];
  const LABELS = { A: '日常互动', B: '社交接触', C: '主动行为' };
  const INTIMATE_LABELS = { A: '缓拍温存', B: '肢体加深', C: '强势冲刺' };
  const COSTS = { A: 5, B: 10, C: 15 };
  const PRIVACY_LABELS = {
    open_public: '',
    semi_open: '半私密',
    thin_wall: '隔墙潜行',
    under_cover: '同席暗触',
    locked_private: '反锁私密'
  };
  const ATTIRE_STATE_LABELS = {
    neat: '',
    disheveled: '衣着凌乱',
    half_undressed: '半褪轻敞',
    wet: '水渍濡湿',
    torn: '衣料破损'
  };
  const SENSUAL_ITEM_RE = /精油|香薰|眼罩|滚轮|黑丝|睡裙|丝袜|按摩|催情|润滑|束缚|情趣|温热/;
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
    high: '高阶臻品（≥60 积分）'
  };

  const SHOP_CATEGORY_ORDER = ['ai_restock', 'sensual', 'covert', 'daily'];
  const SHOP_CATEGORY_LABELS = {
    ai_restock: 'AI 定制进货',
    sensual: '官能与亲密辅助',
    covert: '隐秘探测装备',
    daily: '日用与礼赠'
  };
  const USAGE_MODE_LABELS = {
    gift: '可赠予',
    consumable_host: '体力恢复',
    consumable_target: '消耗生效',
    reusable_tool: '反复工具',
    deployable_device: '可部署装置'
  };
  const DEPLOY_SPOT_PRESETS = ['床头暗槽', '衣柜缝隙', '梳妆台背', '书架角落', '沙发侧缝'];

  const MAP_COORDS = {
    '徐家主宅':       { x: 180, y: 46,  short: '徐家主宅' },
    '市中心顶层公寓': { x: 86,  y: 112, short: '顶层公寓' },
    '公司':           { x: 274, y: 112, short: '集团公司' },
    '大学':           { x: 112, y: 176, short: '艺术大学' },
    '工作室':         { x: 248, y: 176, short: '画室工坊' }
  };

  const SVG_NS = 'http://www.w3.org/2000/svg';

  let cache = { epoch: '', draft: '', pending: null, voice: true };
  let prefs = { theme: 'noir', font: 'normal', haptics: true, backdrop: true, cinemaPlates: true, readingDof: true, displayMode: 'curtain', confirmMode: 'inline', ambientAudio: true, ambientVolume: 0.32 };
  let snapshot = null, online = false, posting = false, polling = false, progressing = false;
  let storageOK = true, error = '', missing = false, mismatch = false;
  let portraitName = '', signature = '', worldSignature = '', lastSpeaker = '', backdropTarget = '';
  let desktopFocusName = '', topPeekOpen = false, gazeLensLocked = false, parallaxRaf = 0;
  let gazeHoldActive = false, gazeHoldCleanup = null;
  let history = [], hasOlder = false, olderCursor = null, resetRequest = null;
  let intentionalEpochSwitch = false;
  let archiveTab = 'newgame', archivePrologues = null, archiveSaves = null;
  let archiveFilterHero = 'all', archiveSelectedScenario = 'random', archiveBusy = false;
  let archiveArmKey = '', archiveArmTimer = null;
  let audioSerial = 0, audioMessage = null, audioStatus = '', isSpeaking = false;
  let gesture = false, configPromise = null, voiceConfigCache = null, activeVoiceTier = 'free', lastTap = 0;
  let audioAssets = { ambient: {} };
  let audioAssetsLoaded = false, ambientTrackKey = '', ambientActiveIdx = 0;
  let ambientPlayers = null, ambientFadeRaf = 0, ambientDuckTimer = null, ambientDucked = false;
  let armedChoice = null, inkCommit = null;
  let activeHubTab = 'host', selectedChar = '', selectedMapPlace = '', historyFilter = 'all';
  let inspectedHostStat = '', inspectedCharStat = '';
  let activeBagSubTab = '', activeShopCat = 'all', activeSystemSubTab = 'display', activeActionTab = 'move';
  let settlementFolded = true, settlementDismissedId = '', deckCollapsed = false, customComposerExpanded = false, lastUiMode = '';
  let activeStream = null, speakingMessageId = '', lastVectorLocation = '';
  let streamPreview = null, earlyStreamPreview = null, handoffPreview = null, sse = null, sseOpen = false, sseRetryTimer = null;
  let lastSseSeq = 0, sseRetryAttempt = 0, initialSyncDone = false;
  let fishKeyStatusPromise = null, fishKeyConfigured = null, fishMissingToastShown = false;
  let restoreTimer = null, restoreQueued = false, prefetchTimer = null, catchingUp = false;
  let curtainTrackedReqId = '', curtainHideTimer = null, backendPrefBusy = false;
  let customRuleTab = 'primary', customRuleFoldOpen = false;
  let customRuleDrafts = { primary: null, settlement: null };
  let bridgePrimaryTargetSig = '', bridgePrimarySyncedKey = '', bridgeSettleSlotSig = '', bridgeBindModelSig = '', bridgeBindSyncedKey = '';
  let shopCatalog = null, shopBusy = false, shopLoading = false, shopError = '';

  function isIntimateActive(w = snapshot?.world) {
    return Boolean(w?.intimate?.scene_active || w?.progression?.intimate_mode);
  }

  function activeCosts(w = snapshot?.world) {
    const src = w?.intimate?.active_costs || w?.progression?.costs;
    if (src && typeof src === 'object') {
      return {
        A: Number.isFinite(Number(src.A)) ? Number(src.A) : COSTS.A,
        B: Number.isFinite(Number(src.B)) ? Number(src.B) : COSTS.B,
        C: Number.isFinite(Number(src.C)) ? Number(src.C) : COSTS.C
      };
    }
    return { ...COSTS };
  }

  function staminaGuard(w = snapshot?.world) {
    const g = w?.intimate?.stamina_guard || w?.progression?.stamina_guard;
    if (g && typeof g === 'object') {
      return {
        active: Boolean(g.active),
        floor: Number.isFinite(Number(g.floor)) ? Number(g.floor) : 10,
        vigor: Number.isFinite(Number(g.vigor)) ? Number(g.vigor) : 100,
        min_vigor: Number.isFinite(Number(g.min_vigor)) ? Number(g.min_vigor) : 15
      };
    }
    return { active: false, floor: 10, vigor: 100, min_vigor: 15 };
  }

  function applyStaminaFloorClient(rawCost, w = snapshot?.world) {
    const cost = Math.max(0, Number(rawCost) || 0);
    const g = staminaGuard(w);
    if (!g.active) return cost;
    const pg = w?.progression;
    const cur = Number.isFinite(Number(pg?.stamina)) ? Number(pg.stamina) : 100;
    if (cur <= g.floor) return 0;
    return Math.min(cost, Math.max(0, cur - g.floor));
  }

  function optionCost(optId, w = snapshot?.world) {
    const c = activeCosts(w);
    const raw = c[optId] ?? COSTS[optId] ?? 0;
    return applyStaminaFloorClient(raw, w);
  }

  function customReserveCost(w = snapshot?.world) {
    const c = activeCosts(w);
    return applyStaminaFloorClient(c.C, w);
  }

  function optionLabel(optId, w = snapshot?.world) {
    if (isIntimateActive(w) && INTIMATE_LABELS[optId]) return INTIMATE_LABELS[optId];
    return LABELS[optId] || optId;
  }

  function rationalizationTier(st) {
    if (!st) return null;
    const intactDefense = st.shame >= 85 && st.depravity < 15 && st.passiveLv < 4;
    if (intactDefense || st.affection <= 60) return null;
    if (st.shame < 30) return { level: 'all', text: '合理化闭环 · 全档豁免', tone: 'rose' };
    if (st.shame < 40) return { level: 'deep', text: '合理化闭环 · 深度豁免', tone: 'rose' };
    if (st.shame < 50) return { level: 'medium', text: '合理化闭环 · 中度豁免', tone: 'rose' };
    if (st.shame < 70) return { level: 'light', text: '合理化闭环 · 轻度豁免', tone: 'rose' };
    return null;
  }
  let bagPickerState = null;
  let panelsCacheSig = '', panelsCacheVal = null;
  let lastFocusedBeats = [];
  const visiblePlates = new Set();
  let plateObserver = null;
  const segmentDomCache = new Map();
  let segmentDomCacheEpoch = '', segmentDomCachePlates = null, segmentDomCacheVaSig = '';

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

  let legacyConfirmOff = false;
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '{}');
    if (typeof v.epoch === 'string') cache.epoch = v.epoch;
    if (typeof v.draft === 'string') cache.draft = v.draft;
    if (typeof v.voice === 'boolean') cache.voice = v.voice;
    if (v.confirmCommit === false) legacyConfirmOff = true;
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
    if (p.confirmMode === 'inline' || p.confirmMode === 'critical' || p.confirmMode === 'off') {
      prefs.confirmMode = p.confirmMode;
    } else if (legacyConfirmOff) {
      prefs.confirmMode = 'off';
    }
    if (typeof p.ambientAudio === 'boolean') prefs.ambientAudio = p.ambientAudio;
    if (Number.isFinite(Number(p.ambientVolume))) {
      prefs.ambientVolume = Math.max(0.05, Math.min(0.85, Number(p.ambientVolume)));
    }
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
    syncAmbientSoundscape();
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

  async function api(path, body, method = null) {
    const reqMethod = method || (body === undefined ? 'GET' : 'POST');
    const headers = reqMethod === 'GET' ? {} : { 'X-Story-Client': '1' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    return VoiceClient.requestJson('/api/story/' + path, {
      cache: 'no-store',
      ...(reqMethod === 'GET' ? {} : {
        method: reqMethod,
        headers,
        ...(body === undefined ? {} : { body: JSON.stringify(body) })
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
  const baseBlocked = () => posting || polling || progressing || catchingUp || !online || !storageOK || ![2, 3].includes(snapshot?.interaction_protocol) || !!cache.pending || !!inkCommit || active();
  const canDecide = () => !!snapshot?.playback?.segment_id && snapshot.playback.completed;
  const blocked = () => baseBlocked() || !canDecide();
  const current = () => history.find(t => t.id === snapshot?.playback?.segment_id);
  const progression = () => snapshot?.world?.progression;
  const resting = () => !!progression() && (progression().runtime.phase === 'resting' || (snapshot?.task?.reservation?.status !== 'held' && progression().stamina < 5));
  const pureRecovery = () => /^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test($('input').value);
  const afford = n => !progression() || progression().stamina >= n;
  const ordinaryBlocked = () => blocked() || resting();
  const canTransactDeterministic = () => online && !posting && !polling && !progressing && !catchingUp
    && !active() && !shopBusy && !cache.pending && !inkCommit && !!snapshot?.revision
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

  function describeSystemEffect(eff) {
    const s = String(eff || '').trim();
    if (!s) return '';
    let m = /^host_stamina:([1-9]\d*)$/.exec(s);
    if (m) return '体力 +' + m[1];
    m = /^buff:([^:]{1,20}):([1-9]\d*)(?::(.*))?$/.exec(s);
    if (m) return '增益：' + m[1] + '（' + m[2] + '回合）';
    m = /^(?:deploy_device|device):(camera|audio|aroma)$/.exec(s);
    if (m) return m[1] === 'camera' ? '远程隐蔽画面' : (m[1] === 'audio' ? '远程隐蔽拾音' : '定时扩香装置');
    m = /^costume:(.+)$/.exec(s);
    if (m) return '穿搭效果：' + m[1];
    return '';
  }

  function attachOperationToComposer({ operation, label, defaultAction }) {
    pendingItemAttachment = { operation, label, defaultAction: defaultAction || '' };
    bagPickerState = null;
    if (!($('input')?.value || '').trim() && defaultAction) {
      syncDraftInputs(defaultAction);
      save();
    }
    renderSheetAttachBar();
    if ($('worldDialog')?.open) $('worldDialog').close();
    openComposerSheet({ focus: true });
  }

  async function handleShopUpdatedEvent() {
    await loadShop(true);
    scheduleRestore(30);
  }

  async function deleteDynamicShopItem(item) {
    if (!item || !item.id || !canTransactDeterministic()) return;
    haptic(10);
    shopBusy = true;
    renderWorld(true);
    try {
      const res = await api('shop/dynamic/' + encodeURIComponent(item.id), { save_epoch: cache.epoch }, 'DELETE');
      if (res?.snapshot) absorb(res.snapshot);
      else await restore();
      toast('已下架动态商品「' + item.name + '」');
      await loadShop(true);
    } catch (e) {
      toast(e.message || '下架失败，已刷新商城');
      await loadShop(true);
    } finally {
      shopBusy = false;
      renderWorld(true);
    }
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
        toast('已预备商业杠杆「' + (res?.receipt?.intel_name || intelId) + '」（下次 C 烈度展开 3 次越界护盾并压制非目击警惕）');
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
    const arr = Array.isArray(lines) ? lines : [];
    const sig = arr.join('\n');
    if (panelsCacheVal && sig === panelsCacheSig) return panelsCacheVal;
    const result = {};
    for (const raw of arr) {
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
    panelsCacheSig = sig;
    panelsCacheVal = result;
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

  function withThumb(url, mode = 'avatar') {
    if (!url || !mode || !String(url).startsWith('/txt文件/image/')) return url || '';
    if (/[?&]thumb=/.test(url)) return url;
    return url + (url.includes('?') ? '&' : '?') + 'thumb=' + encodeURIComponent(mode);
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

      if (npcStam <= 15) {
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
    syncAmbientSoundscape();
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
    img.src = withThumb(still.url, 'plate');
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
      bg.src = withThumb(sceneStill.url, 'plate');
      bg.alt = '';
      bg.loading = 'lazy';
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
    const passiveNames = ['无被动', '洞察之瞳', '认知欺诈滤镜', '疲劳诱导', '防线支配'];
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
      img.src = withThumb(asset?.url || image(hero, 'into.png'), 'plate');
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
      img.src = withThumb(still.url, 'plate');
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
      im.src = withThumb(asset?.url || image(focus, 'into.png'), 'plate');
      im.alt = focus;
      im.style.objectPosition = asset?.pos || '50% 16%';
      im.loading = 'lazy';
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
      im.src = withThumb(still.url, 'plate');
      im.alt = w.location || '';
      im.loading = 'lazy';
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
      const cost = optionCost(optId) || 0;
      const after = Math.max(0, st - cost);
      hold.setAttribute('stroke-dashoffset', String(HUD_RING_C * (1 - st / 100)));
      fill.setAttribute('stroke-dashoffset', String(HUD_RING_C * (1 - after / 100)));
      valEl.textContent = String(after);
    }
  }

  let composerSheetOpen = false;
  let pendingItemAttachment = null; // Reserved for Phase 3 item attachment capsule

  function isMobileViewport() {
    if (typeof window.matchMedia === 'function') {
      return window.matchMedia('(max-width: 859px)').matches;
    }
    return (window.innerWidth || 1024) < 860;
  }

  function activeComposerInput() {
    if (composerSheetOpen && $('sheetInput')) return $('sheetInput');
    return $('input');
  }

  function syncInputHeight(el = $('input')) {
    if (!el || !el.style) return;
    el.style.height = 'auto';
    const cap = el === $('sheetInput') ? 210 : 180;
    const h = el.scrollHeight || 36;
    el.style.height = Math.min(h, cap) + 'px';
  }

  function syncDraftInputs(val, sourceEl = null) {
    const text = String(val ?? '');
    if ($('input') && sourceEl !== $('input')) $('input').value = text;
    if ($('sheetInput') && sourceEl !== $('sheetInput')) $('sheetInput').value = text;
    if ($('sheetCharCount')) $('sheetCharCount').textContent = text.length + ' / 2000';
    cache.draft = text;
  }

  function getLatestContextLine() {
    const turn = current();
    const msgs = turn?.messages || [];
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (!m || !m.text) continue;
      const prefix = m.speaker ? (m.speaker + '：') : '旁白：';
      const clean = String(m.text)
        .replace(/\[[^\]]{1,80}\]/g, '')
        .replace(/[｛{]([^｜|}\r\n]+)[｜|][^｝}\r\n]+[｝}]/g, '$1')
        .trim();
      if (clean) return prefix + clean;
    }
    return '';
  }

  function renderSheetContextPeek() {
    const peek = $('sheetContextPeek');
    if (!peek) return;
    const line = getLatestContextLine();
    if (!line) {
      peek.hidden = true;
      peek.textContent = '';
      return;
    }
    peek.hidden = false;
    peek.textContent = line;
    peek.classList.remove('is-expanded');
  }

  function renderSheetAttachBar() {
    const bar = $('sheetAttachBar');
    if (!bar) return;
    if (!pendingItemAttachment) {
      bar.hidden = true;
      bar.replaceChildren();
      return;
    }
    bar.hidden = false;
    bar.replaceChildren();
    const pill = node('span', 'sheet-attach-pill');
    pill.append(node('span', '', pendingItemAttachment.label || '已挂载道具'));
    const rm = node('button', '', '×');
    rm.type = 'button';
    rm.setAttribute('aria-label', '取消挂载道具');
    rm.onclick = () => {
      pendingItemAttachment = null;
      renderSheetAttachBar();
      controls();
    };
    pill.append(rm);
    bar.append(pill);
  }

  function openComposerSheet(opts = {}) {
    const sheet = $('composerSheet');
    const bd = $('composerSheetBackdrop');
    if (!sheet || !bd) return;
    composerSheetOpen = true;
    syncDraftInputs($('input')?.value ?? cache.draft ?? '');
    renderSheetContextPeek();
    renderSheetAttachBar();
    renderBracketChips(snapshot?.world, true);
    bd.hidden = false;
    sheet.hidden = false;
    document.body.classList.add('sheet-composer-open');
    controls();
    const target = $('sheetInput');
    if (target) {
      if (opts.insertBracket !== undefined) {
        insertInputBracket(opts.insertBracket, target);
      } else if (opts.focus !== false) {
        requestAnimationFrame(() => {
          target.focus();
          const len = (target.value || '').length;
          if (typeof target.setSelectionRange === 'function') target.setSelectionRange(len, len);
          syncInputHeight(target);
        });
      } else {
        syncInputHeight(target);
      }
    }
  }

  function closeComposerSheet() {
    if (!composerSheetOpen) return;
    composerSheetOpen = false;
    if ($('composerSheet')) $('composerSheet').hidden = true;
    if ($('composerSheetBackdrop')) $('composerSheetBackdrop').hidden = true;
    document.body.classList.remove('sheet-composer-open');
    $('sheetInput')?.blur?.();
    syncInputHeight($('input'));
    controls();
    sizing();
  }

  function insertInputBracket(prefix = '', targetOverride = null) {
    const inp = targetOverride || activeComposerInput();
    if (!inp) return;
    haptic(6);
    const val = inp.value || '';
    const start = inp.selectionStart ?? val.length;
    const end = inp.selectionEnd ?? start;
    const selected = val.slice(start, end);
    const snippet = '（' + prefix + selected + '）';
    const nextVal = val.slice(0, start) + snippet + val.slice(end);
    syncDraftInputs(nextVal);
    save();
    inp.focus();
    const caret = start + 1 + prefix.length + selected.length;
    if (typeof inp.setSelectionRange === 'function') inp.setSelectionRange(caret, caret);
    syncInputHeight(inp);
    controls();
    sizing();
  }

  function heldSensualItems(w) {
    const items = Array.isArray(w?.items) ? w.items : [];
    return items.filter(it => {
      if (!it || it.fields?.['当前状态'] !== '仓库中') return false;
      const cat = String(it.category || it.fields?.['分类'] || '').toLowerCase();
      if (cat === 'sensual') return true;
      const blob = `${it.name || ''} ${it.fields?.['系统效果'] || ''} ${it.fields?.['说明'] || ''}`;
      return SENSUAL_ITEM_RE.test(blob);
    }).slice(0, 4);
  }

  function insertChipSnippet(snippet, isSheetBar) {
    haptic(8);
    const cur = (activeComposerInput()?.value || '');
    const nextVal = cur ? (cur.trimEnd() + (cur.trimEnd().endsWith('）') ? '' : ' ') + snippet) : snippet;
    syncDraftInputs(nextVal);
    save();
    if (!isSheetBar && isMobileViewport() && !composerSheetOpen) {
      openComposerSheet({ focus: true });
    } else {
      const inp = isSheetBar ? $('sheetInput') : activeComposerInput();
      if (inp) {
        inp.focus();
        syncInputHeight(inp);
      }
      controls();
      sizing();
    }
  }

  function populateQuickChipsInto(bar, heldIds, catalog, sensualItems, isSheetBar, keepsakes = [], castHere = []) {
    if (!bar) return;
    const sIds = (sensualItems || []).map(x => x.id + ':' + x.name).join(',');
    const kIds = (keepsakes || []).slice(0, 2).map(k => (k.id || '') + ':' + (k.name || '') + ':' + (castHere.includes(k.owner) ? '1' : '0')).join(',');
    const sig = heldIds.join(',') + '|' + sIds + '|' + kIds + (isSheetBar ? ':s' : ':b');
    if (bar.dataset.sig === sig && bar.childElementCount > 0) return;
    bar.dataset.sig = sig;
    bar.replaceChildren();

    const actChip = node('button', 'bracket-chip is-primary', '＋（）括号动作');
    actChip.type = 'button';
    actChip.onclick = () => {
      if (!isSheetBar && isMobileViewport() && !composerSheetOpen) {
        openComposerSheet({ focus: true, insertBracket: '' });
      } else {
        insertInputBracket('', isSheetBar ? $('sheetInput') : null);
      }
    };

    const thChip = node('button', 'bracket-chip', '＋（）内心想法');
    thChip.type = 'button';
    thChip.onclick = () => {
      if (!isSheetBar && isMobileViewport() && !composerSheetOpen) {
        openComposerSheet({ focus: true, insertBracket: '心底暗忖：' });
      } else {
        insertInputBracket('心底暗忖：', isSheetBar ? $('sheetInput') : null);
      }
    };

    const shopCustomChip = node('button', 'bracket-chip is-intel', '✦ 商城定制');
    shopCustomChip.type = 'button';
    shopCustomChip.title = '在剧情内向系统商城私密定制贴合当前局面的新道具并自动上架';
    shopCustomChip.onclick = () => {
      if (!isSheetBar && isMobileViewport() && !composerSheetOpen) {
        openComposerSheet({ focus: true, insertBracket: '【商城定制】' });
      } else {
        insertInputBracket('【商城定制】', isSheetBar ? $('sheetInput') : null);
      }
    };

    const domChip = node('button', 'bracket-chip is-intimate', '＋（强势压迫授权）');
    domChip.type = 'button';
    domChip.onclick = () => insertChipSnippet('（强势压迫授权）', isSheetBar);

    bar.append(actChip, thChip, shopCustomChip, domChip);

    for (const item of (sensualItems || [])) {
      const chip = node('button', 'bracket-chip is-sensual', '✦ 道具：' + item.name);
      chip.type = 'button';
      chip.onclick = () => insertChipSnippet('（取用随身「' + item.name + '」）', isSheetBar);
      bar.append(chip);
    }

    for (const ks of (keepsakes || []).slice(0, 2)) {
      if (!ks || !ks.id || !ks.name) continue;
      const ownerHere = castHere.includes(ks.owner);
      const actType = ownerHere ? 'confront' : 'sniff_play';
      const chip = node('button', 'bracket-chip is-keepsake', '🎀 私藏：' + ks.owner + '·' + ks.name);
      chip.type = 'button';
      chip.onclick = () => {
        haptic(8);
        attachOperationToComposer({
          operation: { code: 'keepsake_action', keepsake_id: ks.id, action_type: actType },
          label: (ownerHere ? '👀 当面出示「' : '🫧 私下嗅闻「') + ks.owner + '的' + ks.name + '」',
          defaultAction: ownerHere
            ? ('（指尖勾出暗中藏着的那件「' + ks.name + '」，在' + ks.owner + '眼前轻轻一晃）')
            : ('（避开视线取出暗中收存的「' + ks.owner + '的' + ks.name + '」，指腹摩挲着布料凑近轻嗅）')
        });
      };
      bar.append(chip);
    }

    for (const iid of heldIds) {
      const item = catalog.find(x => x.id === iid);
      const label = item?.name || iid;
      const chip = node('button', 'bracket-chip is-intel', '◆ 亮牌：' + label);
      chip.type = 'button';
      chip.onclick = () => {
        haptic(8);
        const text = '（我把暗中掌握的「' + label + '」线索摊在眼前）这件事，你打算怎么解释？';
        syncDraftInputs(text);
        save();
        if (!isSheetBar && isMobileViewport() && !composerSheetOpen) {
          openComposerSheet({ focus: true });
        } else {
          const inp = isSheetBar ? $('sheetInput') : activeComposerInput();
          if (inp) {
            inp.focus();
            syncInputHeight(inp);
          }
          controls();
          sizing();
        }
      };
      bar.append(chip);
    }
  }

  function renderBracketChips(w, forceSheet = false) {
    const heldIds = w?.intel?.held || [];
    const catalog = w?.intel?.catalog || [];
    const sensual = heldSensualItems(w);
    const keepsakes = Array.isArray(w?.intimate?.keepsakes) ? w.intimate.keepsakes : [];
    const castHere = Array.isArray(w?.cast) ? w.cast : [];
    populateQuickChipsInto($('bracketChips'), heldIds, catalog, sensual, false, keepsakes, castHere);
    if (forceSheet || composerSheetOpen || $('sheetQuickChips')) {
      populateQuickChipsInto($('sheetQuickChips'), heldIds, catalog, sensual, true, keepsakes, castHere);
    }
  }

  function ensurePlateObserver() {
    if (plateObserver || typeof IntersectionObserver === 'undefined') return plateObserver;
    const stream = $('stream');
    if (!stream) return null;
    try {
      plateObserver = new IntersectionObserver(entries => {
        for (const ent of entries) {
          if (ent.isIntersecting) visiblePlates.add(ent.target);
          else visiblePlates.delete(ent.target);
        }
      }, { root: stream, rootMargin: '60px 0px' });
    } catch (_) {
      plateObserver = null;
    }
    return plateObserver;
  }

  function observePlateElement(el) {
    if (!el || typeof el.querySelector !== 'function') return;
    const obs = ensurePlateObserver();
    if (!obs) return;
    const img = el.classList?.contains('cinema-plate-img') ? el : el.querySelector('.cinema-plate-img');
    if (img && img.dataset?.plateObserved !== '1') {
      img.dataset.plateObserved = '1';
      try { obs.observe(img); } catch (_) {}
    }
  }

  function applyReadingFocus() {
    const msgBox = $('messages');
    const stream = $('stream');
    if (!msgBox || !stream) return;
    for (const prev of lastFocusedBeats) prev.classList?.remove('is-focus-beat');
    lastFocusedBeats = [];
    if (!prefs.readingDof) {
      msgBox.classList.remove('is-dof-on');
      return;
    }
    const children = msgBox.children || [];
    let lastBeat = null, prevBeat = null, beatCount = 0;
    for (let i = children.length - 1; i >= 0; i--) {
      const el = children[i];
      if (!el?.classList || (!el.classList.contains('msg') && !el.classList.contains('cinema-plate'))) continue;
      beatCount += 1;
      if (!lastBeat) lastBeat = el;
      else if (!prevBeat) { prevBeat = el; break; }
    }
    const nearBottom = (stream.scrollHeight - stream.scrollTop - stream.clientHeight) < 88;
    const shouldDof = nearBottom && beatCount > 1 && !!lastBeat;
    msgBox.classList.toggle('is-dof-on', shouldDof);
    if (shouldDof) {
      lastBeat.classList.add('is-focus-beat');
      lastFocusedBeats.push(lastBeat);
      if (prevBeat && prevBeat.classList.contains('cinema-plate')) {
        prevBeat.classList.add('is-focus-beat');
        lastFocusedBeats.push(prevBeat);
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
    const targets = plateObserver
      ? Array.from(visiblePlates)
      : Array.from(stream.querySelectorAll('.cinema-plate-img'));
    for (const img of targets) {
      if (!img || !img.parentElement || (img.isConnected === false)) {
        visiblePlates.delete(img);
        continue;
      }
      const r = img.parentElement.getBoundingClientRect();
      if (r.bottom < rect.top - 40 || r.top > rect.bottom + 40) continue;
      const rel = ((r.top + r.height / 2) - center) / rect.height;
      const shift = Math.max(-12, Math.min(12, rel * 22));
      img.style.transform = 'scale(1.08) translateY(' + shift.toFixed(1) + 'px)';
    }
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

    const pg = progression(), res = task?.reservation, sg = staminaGuard();
    const hpStatus = snapshot?.world?.intimate?.host_phys;
    const vigorTxt = (isIntimateActive() || (hpStatus && Number(hpStatus.vigor) < 100))
      ? (' · 耐力 ' + (hpStatus?.vigor ?? sg.vigor ?? 100) + (sg.active ? '(护航)' : ''))
      : '';
    $('resourceStatus').textContent = pg
      ? (res?.status === 'held'
          ? '已暂扣 ' + res.quote.total + ' · 原体力 ' + res.quote.before + ' · 结算后判断疲惫'
          : '体力 ' + pg.stamina + ' / 100' + vigorTxt + ' · 道具恢复额度 ' + pg.item_budget)
        + (pg.runtime.clock ? ' · 第' + pg.runtime.clock.day + '天 ' + pg.runtime.clock.time : '')
      : '';
    $('resourceStatus').hidden = !pg;

    const hasUsableRecovery = $('recoveryItem').options.length > 1;
    const hideMobileRecovery = isMobileViewport() && pg && pg.stamina > 30;
    $('recoveryWrap').hidden = !hasUsableRecovery || hideMobileRecovery;
    $('form').classList.toggle('is-low-stamina', !!(pg && pg.stamina <= 45 && !sg.active));
    $('useRecovery').disabled = ordinaryBlocked() || !$('recoveryItem').value || !pg || pg.item_budget <= 0 || pg.stamina >= 100;

    const custCost = customReserveCost();
    const isPureRec = !pendingItemAttachment && pureRecovery();
    const sendCostLabel = isPureRec ? '免费恢复' : (pg ? (custCost > 0 ? ('-' + custCost + '⚡') : '护航0⚡') : '提交');
    const inputDisabled = !ready || posting || progressing || !online || !storageOK || !!cache.pending || isAct;
    const draftStr = ($('input')?.value || '');
    const hasDraftOrAttach = Boolean(draftStr.trim() || pendingItemAttachment);
    const sendDisabled = ordinaryBlocked() || (!isPureRec && !afford(custCost));
    $('sendCost').textContent = sendCostLabel;
    $('send').disabled = sendDisabled;
    $('input').disabled = inputDisabled;
    if ($('expandComposerBtn')) $('expandComposerBtn').disabled = inputDisabled;
    if ($('sheetInput')) $('sheetInput').disabled = inputDisabled;
    if ($('sheetSendCost')) $('sheetSendCost').textContent = sendCostLabel;
    if ($('sheetSendBtn')) $('sheetSendBtn').disabled = sendDisabled || !hasDraftOrAttach;
    if ($('sheetCharCount')) $('sheetCharCount').textContent = draftStr.length + ' / 2000';
    if ($('sheetBagBtn')) $('sheetBagBtn').disabled = base;
    if ($('sheetMoveBtn')) $('sheetMoveBtn').disabled = ordinaryBlocked() || !afford(custCost);
    if (composerSheetOpen && (!showDecisions || inputDisabled)) closeComposerSheet();

    $('actions').hidden = !ready || rest || previewOn;
    $('actions').disabled = ordinaryBlocked() || !afford(custCost);
    if ($('quickActionBtn')) $('quickActionBtn').disabled = ordinaryBlocked() || !afford(custCost);
    $('move').disabled = ordinaryBlocked() || !afford(custCost) || !$('destination').value;
    $('give').disabled = ordinaryBlocked() || !afford(custCost) || !$('item').value || !$('recipient').value;

    $('choices').querySelectorAll('button').forEach(b => {
      b.disabled = ordinaryBlocked() || !afford(optionCost(b.dataset.option));
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
    if ($('confirmNewGame')) $('confirmNewGame').disabled = base || archiveBusy;
    if ($('rerollPrologueBtn')) $('rerollPrologueBtn').disabled = base || archiveBusy;
    if ($('saveSlotCreateBtn')) $('saveSlotCreateBtn').disabled = base || archiveBusy;

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
    const primaryTargetSel = $('storyPrimaryTarget');
    const primaryBindBtn = $('storyBindPrimaryBtn');
    if ($('storyPrimaryBadge')) $('storyPrimaryBadge').textContent = 'CHAT 槽';
    if (primaryTargetSel) {
      const primaryOpts = availModels.length
        ? availModels.map(m => ({ value: pairKey(m.provider_id, m.model_id), label: m.model_id + ' · ' + m.provider_name }))
        : [{ value: '', label: hasCatalogApi ? '未检测到 Operit 已配置模型' : '升级 v2.2.0 桥接插件后可改绑' }];
      const curChatBind = bindingBySlot.get('CHAT');
      const curChatPair = curChatBind
        ? pairKey(curChatBind.provider_id, curChatBind.model_id)
        : pairKey(snapshot?.bridge_model?.provider_id, snapshot?.bridge_model?.model_id);
      const shouldResetPrimary = bridgePrimarySyncedKey !== curChatPair;
      bridgePrimaryTargetSig = syncSelectOptions(primaryTargetSel, primaryOpts, bridgePrimaryTargetSig, shouldResetPrimary ? curChatPair : '');
      if (shouldResetPrimary) bridgePrimarySyncedKey = curChatPair;
      primaryTargetSel.disabled = !!sessionBusy || !hasCatalogApi || !availModels.length;
      if (primaryBindBtn) primaryBindBtn.disabled = !!sessionBusy || !hasCatalogApi || !availModels.length || !primaryTargetSel.value;
    }
    if ($('storyPrimaryStatus')) {
      const bm = snapshot?.bridge_model;
      $('storyPrimaryStatus').textContent = !bridge?.present ? '桥接未连接，请在 Operit 开启故事桥接。'
        : !hasCatalogApi ? '导入 v2.2.0 故事桥接插件后，可在此与 Operit 插件设置页双端切换主/副模型。'
        : bm ? '当前主模型：' + bm.model_id + ' · ' + bm.provider_name + '（CHAT 槽 · 原生自托管）'
        : '主模型未解析，请先在 Operit 绑定 CHAT 功能槽模型。';
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

  function ensureAmbientPlayers() {
    if (ambientPlayers) return ambientPlayers;
    const mk = () => {
      const a = new Audio();
      a.loop = true;
      a.preload = 'auto';
      a.volume = 0;
      return a;
    };
    ambientPlayers = [mk(), mk()];
    return ambientPlayers;
  }

  async function loadAudioAssets(force = false) {
    if (audioAssetsLoaded && !force) return audioAssets;
    if (typeof VoiceClient.getAudioAssets !== 'function') return audioAssets;
    try {
      const res = await VoiceClient.getAudioAssets();
      if (res && typeof res === 'object') {
        audioAssets = {
          ambient: res.ambient && typeof res.ambient === 'object' ? res.ambient : {}
        };
        audioAssetsLoaded = true;
        syncAmbientSoundscape();
      }
    } catch (_) {}
    return audioAssets;
  }

  function ambientTargetVolume() {
    const base = Math.max(0.05, Math.min(0.85, Number(prefs.ambientVolume) || 0.32));
    return ambientDucked ? +(base * 0.28).toFixed(3) : +base.toFixed(3);
  }

  function chooseAmbientTrackKey(w = snapshot?.world) {
    const avail = audioAssets?.ambient || {};
    const keys = Object.keys(avail);
    if (!keys.length) return '';
    const pick = list => list.find(k => Boolean(avail[k])) || keys[0];
    const mood = deriveAtmosphereMood(w);
    if (mood === 'vigilance') {
      return pick(['tension_stealth', 'rain_night', 'calm_home']);
    }
    if (mood === 'intimate') {
      const cast = w?.cast || [];
      const panels = parsePanels(w?.panels || []);
      const isAftermath = cast.some(name => {
        if (!PEOPLE.includes(name)) return false;
        const micro = w?.micro_states?.[name] || {};
        const stam = panels[name]?.stats?.['体力']?.num;
        return Boolean(micro.residual_tension) || (Number.isFinite(stam) && stam <= 15);
      });
      if (isAftermath) {
        return pick(['aftermath_quiet', 'intimate_warm', 'rain_night', 'calm_home']);
      }
      return pick(['intimate_warm', 'rain_night', 'calm_home']);
    }
    const tod = timeOfDay(w?.progression?.runtime?.clock?.time || '').phase;
    const isRainScene = /雨/.test(String(w?.prologue?.title || '') + String(w?.intimate?.sub_location || ''));
    if (tod === 'night' || tod === 'dusk' || isRainScene) {
      return pick(['rain_night', 'calm_home']);
    }
    return pick(['calm_home', 'rain_night']);
  }

  function rampAmbientVolumes(activeEl, inactiveEl, targetActive, durationMs = 900) {
    if (ambientFadeRaf) cancelAnimationFrame(ambientFadeRaf);
    const startActive = activeEl ? activeEl.volume : 0;
    const startInactive = inactiveEl ? inactiveEl.volume : 0;
    const t0 = performance.now();
    const step = now => {
      const p = durationMs <= 0 ? 1 : Math.min(1, (now - t0) / durationMs);
      if (activeEl) activeEl.volume = Math.max(0, Math.min(1, startActive + (targetActive - startActive) * p));
      if (inactiveEl) inactiveEl.volume = Math.max(0, Math.min(1, startInactive * (1 - p)));
      if (p < 1) {
        ambientFadeRaf = requestAnimationFrame(step);
      } else {
        ambientFadeRaf = 0;
        if (inactiveEl && inactiveEl.volume <= 0.005) {
          inactiveEl.pause();
          inactiveEl.volume = 0;
        }
      }
    };
    ambientFadeRaf = requestAnimationFrame(step);
  }

  function pauseAmbient() {
    if (ambientFadeRaf) { cancelAnimationFrame(ambientFadeRaf); ambientFadeRaf = 0; }
    if (ambientDuckTimer) { clearTimeout(ambientDuckTimer); ambientDuckTimer = null; }
    if (!ambientPlayers) return;
    for (const p of ambientPlayers) {
      try { p.pause(); } catch (_) {}
      p.volume = 0;
    }
  }

  function syncAmbientSoundscape() {
    if (!prefs.ambientAudio || document.hidden || !gesture) {
      pauseAmbient();
      return;
    }
    const desiredKey = chooseAmbientTrackKey(snapshot?.world);
    const desiredUrl = desiredKey ? audioAssets.ambient[desiredKey] : '';
    if (!desiredUrl) {
      pauseAmbient();
      return;
    }
    const players = ensureAmbientPlayers();
    const cur = players[ambientActiveIdx];
    const targetVol = ambientTargetVolume();
    if (ambientTrackKey === desiredKey && cur.dataset.trackKey === desiredKey) {
      if (cur.paused) {
        cur.volume = 0;
        const pr = cur.play();
        if (pr?.catch) pr.catch(() => {});
      }
      rampAmbientVolumes(cur, players[1 - ambientActiveIdx], targetVol, 420);
      return;
    }
    const nextIdx = 1 - ambientActiveIdx;
    const next = players[nextIdx];
    const prev = cur;
    ambientActiveIdx = nextIdx;
    ambientTrackKey = desiredKey;
    next.dataset.trackKey = desiredKey;
    next.src = desiredUrl;
    next.volume = 0;
    const pr = next.play();
    if (pr?.catch) pr.catch(() => {});
    rampAmbientVolumes(next, prev, targetVol, 1150);
  }

  function duckAmbient(speakingNow) {
    if (ambientDuckTimer) { clearTimeout(ambientDuckTimer); ambientDuckTimer = null; }
    if (!prefs.ambientAudio || !ambientPlayers || document.hidden || !gesture) return;
    const cur = ambientPlayers[ambientActiveIdx];
    if (!cur || cur.paused) return;
    if (speakingNow) {
      ambientDucked = true;
      rampAmbientVolumes(cur, ambientPlayers[1 - ambientActiveIdx], ambientTargetVolume(), 240);
    } else {
      ambientDuckTimer = setTimeout(() => {
        ambientDuckTimer = null;
        ambientDucked = false;
        if (!isSpeaking && prefs.ambientAudio && !document.hidden && ambientPlayers) {
          const active = ambientPlayers[ambientActiveIdx];
          if (active && !active.paused) {
            rampAmbientVolumes(active, ambientPlayers[1 - ambientActiveIdx], ambientTargetVolume(), 520);
          }
        }
      }, 420);
    }
  }

  function computeProsodyMod(m, who) {
    if (!m || m.kind !== 'dialogue' || !VOICED_SPEAKERS.has(who)) return null;
    const w = snapshot?.world;
    const panels = w ? parsePanels(w.panels || []) : {};
    const stats = panels[who]?.stats || {};
    const desire = stats['欲望']?.num ?? 0;
    const orgasm = stats['高潮']?.num ?? 0;
    const stam = stats['体力']?.num ?? 100;
    const intimateBeat = Number(w?.intimate?.session_beats || 0);
    const txt = String(m.text || '');
    const hasIntimateTag = /<whisper>|<soft>|\[(?:[^\]\r\n]*(?:耳语|气音|气声|喘|颤|沙哑|发紧|发虚|低哑|whisper|pant|breathless|trembl)[^\]\r\n]*)\]/i.test(txt);
    if (orgasm >= 70 || stam <= 15) {
      return { speed_scale: 0.90, expressive_boost: 0.06 };
    }
    if (desire >= 85 || hasIntimateTag) {
      return { speed_scale: 0.93, expressive_boost: 0.04 };
    }
    if (intimateBeat >= 1) {
      return { speed_scale: 0.95, expressive_boost: 0.02 };
    }
    return null;
  }

  function updateSpeakingUI() {
    duckAmbient(Boolean(isSpeaking));
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
  const FREE_DEFAULT_VOICE_ROLES = new Set(['旁白', '动作', '徐志北']);

  function hasUsableVoiceSlot(slotCfg) {
    const v = String(slotCfg?.voice || '').trim();
    if (v.startsWith('edge:')) return v.length > 5;
    if (v.startsWith('fish:')) return v.length > 5;
    return false;
  }

  function resolveVoiceSpeaker(m, cfgOverride) {
    if (!m || m.isPlayerInput || !String(m.text || '').trim()) return '';
    const cfg = cfgOverride || (typeof voiceConfigCache !== 'undefined' ? voiceConfigCache : null);
    const settings = cfg?.__settings__ || {};
    if (m.kind === 'narration') return '旁白';
    if (m.kind === 'dialogue') {
      if (VOICED_SPEAKERS.has(m.speaker)) return m.speaker;
      if (m.speaker === '徐志北') {
        return settings.protagonist_voice_enabled === true && hasUsableVoiceSlot(cfg?.['徐志北']) ? '徐志北' : '';
      }
      return '';
    }
    if (m.kind === 'action') {
      const mode = settings.action_voice_mode || 'follow_narrator';
      if (mode === 'muted') return '';
      const scope = settings.action_voice_scope || 'all';
      const actorOk = scope === 'all'
        ? (VOICED_SPEAKERS.has(m.speaker) || m.speaker === '徐志北')
        : VOICED_SPEAKERS.has(m.speaker);
      if (!actorOk) return '';
      return mode === 'separate' ? '动作' : '旁白';
    }
    return '';
  }

  function resolveEffectiveVoiceCfg(who, config) {
    const raw = config?.[who];
    if (!raw || typeof raw !== 'object') return null;
    const v = String(raw.voice || '').trim();
    if (who === '动作' && (!v || v === 'fish:')) {
      const narrator = config?.['旁白'] || {};
      const nv = String(narrator.voice || '').trim();
      if (!nv || nv === 'fish:') return null;
      if (nv.startsWith('edge:')) {
        return { voice: nv, rate: '+0%', pitch: '-2Hz', volume: '-10%', emotion: '' };
      }
      return { ...raw, voice: nv };
    }
    if (!v || v === 'fish:') return null;
    return raw;
  }

  function clearAudioCache() {
    cancelPrefetch();
    audioCache.clear();
    urls.clear();
  }

  function resolveVoiceModelKey(who, cfg, settings) {
    const voice = String(cfg?.voice || '');
    if (voice.startsWith('edge:')) return 'edge';
    return String(cfg?.tts_model || (FREE_DEFAULT_VOICE_ROLES.has(who) ? 's2.1-pro-free' : (settings?.fish_tts_model || 's2.1-pro-free'))).trim() || 's2.1-pro-free';
  }

  function audioCacheKey(id, who, cfg, settings, prosodyMod = null) {
    const voiceTag = String(cfg?.voice || '');
    let key = id + '|' + who + '|' + voiceTag + '|' + resolveVoiceModelKey(who, cfg, settings);
    if (prosodyMod && (prosodyMod.speed_scale || prosodyMod.expressive_boost)) {
      key += '|p:' + (prosodyMod.speed_scale || 1) + ':' + (prosodyMod.expressive_boost || 0);
    }
    return key;
  }

  function isDrama3Speaker(speaker) {
    const name = String(speaker || '').trim();
    if (!['沈知韫', '苏婉青', '徐念薇'].includes(name)) return false;
    if (voiceConfigCache && voiceConfigCache[name]) {
      return resolveVoiceModelKey(name, voiceConfigCache[name], voiceConfigCache.__settings__ || {}) === 'drama-3';
    }
    return activeVoiceTier === 'drama';
  }

  function voiceRoutingSig(cfg) {
    const s = cfg?.__settings__ || {};
    return [
      s.voice_tier || 'free',
      s.protagonist_voice_enabled === true ? '1' : '0',
      hasUsableVoiceSlot(cfg?.['徐志北']) ? '1' : '0',
      s.action_voice_mode || 'follow_narrator',
      s.action_voice_scope || 'all',
    ].join('|');
  }

  function invalidateVoiceConfig() {
    configPromise = null;
    voiceConfigCache = null;
    fishKeyStatusPromise = null;
    fishKeyConfigured = null;
    clearAudioCache();
  }

  function loadVoiceConfig() {
    configPromise = configPromise || VoiceClient.requestJson('/api/config?t=' + Date.now(), { cache: 'no-store' })
      .then(cfg => {
        const prevSig = voiceConfigCache ? voiceRoutingSig(voiceConfigCache) : '';
        const prevTier = activeVoiceTier;
        voiceConfigCache = cfg || null;
        activeVoiceTier = cfg?.__settings__?.voice_tier || 'free';
        const nextSig = voiceConfigCache ? voiceRoutingSig(voiceConfigCache) : '';
        if ((prevTier !== activeVoiceTier || prevSig !== nextSig) && history.length) {
          segmentDomCache.clear();
          signature = '';
          render();
        }
        return cfg;
      })
      .catch(e => {
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
    const serial = audioSerial;
    prefetchTimer = setTimeout(async () => {
      prefetchTimer = null;
      if (serial !== audioSerial || !cache.voice || !gesture || document.hidden) return;
      try {
        const config = await loadVoiceConfig();
        if (serial !== audioSerial || !cache.voice || document.hidden) return;
        const who = resolveVoiceSpeaker(m, config);
        if (!who) return;
        const cfg = resolveEffectiveVoiceCfg(who, config);
        if (!cfg) return;
        const prosodyMod = computeProsodyMod(m, who);
        const cacheKey = audioCacheKey(id, who, cfg, config.__settings__ || {}, prosodyMod);
        const existing = audioCache.get(cacheKey);
        if (existing && urls.has(existing)) return;
        if (!String(cfg.voice).startsWith('edge:') && !(await ensureFishKeyReady())) return;
        const payload = VoiceClient.buildPayload(stripSubtextForTts(m.text), cfg, config.__settings__ || {}, '', who, prosodyMod);
        const blob = await VoiceClient.requestAudio(payload, { channel: 'prefetch', maxBytes: 16 * 1024 * 1024 });
        if (!cache.voice || document.hidden) return;
        const blobUrl = urls.add(blob);
        audioCache.set(cacheKey, blobUrl);
        for (const [key, value] of audioCache) if (!urls.has(value)) audioCache.delete(key);
      } catch (_) {}
    }, 250);
  }

  function schedulePrefetchWindow(messages, idPrefix, startIndex = 0) {
    if (!Array.isArray(messages) || !messages.length || !cache.voice || document.hidden) return;
    void loadVoiceConfig().then(async config => {
      if (!config || !cache.voice || document.hidden) return;
      const voiced = [];
      let needsFish = false;
      for (let i = Math.max(0, startIndex); i < messages.length && voiced.length < 3; i++) {
        const m = messages[i];
        const who = resolveVoiceSpeaker(m, config);
        if (!who) continue;
        const effCfg = resolveEffectiveVoiceCfg(who, config);
        if (!effCfg) continue;
        const isEdge = String(effCfg.voice).startsWith('edge:');
        if (!isEdge) needsFish = true;
        voiced.push({ m, who, isEdge, idx: i, id: idPrefix + ':' + i, prosodyMod: computeProsodyMod(m, who) });
      }
      if (!voiced.length) return;
      const fishOk = needsFish ? await ensureFishKeyReady() : false;
      if (!cache.voice || document.hidden) return;
      const ready = voiced.filter(v => v.isEdge || fishOk);
      if (!ready.length) return;
      if (typeof VoiceClient.prefetchBatch === 'function') {
        void VoiceClient.prefetchBatch(ready.map(v => ({
          text: stripSubtextForTts(v.m.text),
          speaker: v.who,
          ...(v.prosodyMod || {})
        })));
      }
      if (gesture) {
        schedulePrefetch(ready[0].m, ready[0].id);
      }
    }).catch(() => {});
  }

  function unlock() {
    if (gesture) {
      syncAmbientSoundscape();
      return;
    }
    gesture = true;
    $('audio').src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    const result = $('audio').play();
    if (result?.catch) result.catch(() => {});
    syncAmbientSoundscape();
  }

  async function speak(m, id) {
    stopVoice();
    if (!m || m.isPlayerInput || !String(m.text || '').trim()) {
      audioMessage = null;
      audioStatus = '';
      controls();
      return;
    }
    const quickWho = voiceConfigCache ? resolveVoiceSpeaker(m, voiceConfigCache) : null;
    if (voiceConfigCache && !quickWho) {
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
    try {
      const config = await loadVoiceConfig();
      if (serial !== audioSerial || !cache.voice || document.hidden) return;
      const who = resolveVoiceSpeaker(m, config);
      if (!who) {
        audioMessage = null;
        audioStatus = '';
        controls();
        return;
      }
      const cfg = resolveEffectiveVoiceCfg(who, config);
      if (!cfg) {
        audioStatus = '';
        controls();
        return;
      }
      const modelKey = resolveVoiceModelKey(who, cfg, config.__settings__ || {});
      const isD3 = modelKey === 'drama-3';
      const prosodyMod = computeProsodyMod(m, who);
      const cacheKey = audioCacheKey(id, who, cfg, config.__settings__ || {}, prosodyMod);
      const playBuffered = async payload => {
        const blob = await VoiceClient.requestAudio(payload, { channel: 'live', maxBytes: 16 * 1024 * 1024 });
        if (serial !== audioSerial || !cache.voice || document.hidden) return;
        const blobUrl = urls.add(blob);
        audioCache.set(cacheKey, blobUrl);
        for (const [key, value] of audioCache) if (!urls.has(value)) audioCache.delete(key);
        urls.pin(blobUrl);
        $('audio').src = blobUrl;
        bindEnded();
        await $('audio').play();
        if (serial !== audioSerial) return;
        isSpeaking = true;
        speakingMessageId = id;
        audioStatus = isD3 ? 'D3 朗读中' : '朗读中';
        updateSpeakingUI();
      };
      const cachedUrl = audioCache.get(cacheKey);
      if (cachedUrl && urls.has(cachedUrl)) {
        if (serial !== audioSerial || !cache.voice || document.hidden) return;
        urls.pin(cachedUrl);
        $('audio').src = cachedUrl;
        bindEnded();
        await $('audio').play();
        if (serial !== audioSerial) return;
        isSpeaking = true;
        speakingMessageId = id;
        audioStatus = isD3 ? 'D3 朗读中' : '朗读中';
        updateSpeakingUI();
      } else {
        if (!String(cfg.voice).startsWith('edge:') && !(await ensureFishKeyReady())) {
          audioStatus = '未配置语音密钥';
          if (!fishMissingToastShown) {
            fishMissingToastShown = true;
            toast('尚未配置 Fish 语音密钥，当前静默演播');
          }
          controls();
          return;
        }
        const payload = VoiceClient.buildPayload(stripSubtextForTts(m.text), cfg, config.__settings__ || {}, '', who, prosodyMod);
        let streamStarted = false;
        const stream = await VoiceClient.requestStream(payload, {
          channel: 'live',
          onReady: () => {
            if (serial !== audioSerial) return;
            streamStarted = true;
            isSpeaking = true;
            speakingMessageId = id;
            audioStatus = isD3 ? 'D3 流式朗读中' : '流式朗读中';
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
              audioStatus = isD3 ? 'D3 朗读中' : '朗读中';
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
    return /\[(?:[^\]]*(?:\b(?:whisper|softly|breathy|murmur|sigh|hushed|intimate|trembling)\b|低声|耳语|轻声|气音|压低声音|声音放轻|贴耳)[^\]]*)\]/i.test(s)
      || /<(?:whisper|soft)>/i.test(s);
  }

  function classifyVoiceTag(rawTag) {
    const t = String(rawTag || '').toLowerCase();
    if (/trembl|shaky|quiver|voice\s+breaks|颤|抖|破音|发涩/.test(t)) {
      return { cls: 'fx-tremble', label: '声线微颤', mood: 'tremble' };
    }
    if (/exhaust|sobbing|weak|faint|dazed|out\s+of\s+breath|失力|虚弱|余韵|泣|哽咽|疲惫|倦意/.test(t)) {
      return { cls: 'fx-exhausted', label: '失力余韵', mood: 'exhausted' };
    }
    if (/catch|choke|gasp|inhale|pant|hold(?:ing)?\s+back|short\s+breath|屏息|抽气|急促|喘|发紧|发虚|发干/.test(t)) {
      return { cls: 'fx-catch', label: '呼吸急顿', mood: 'catch' };
    }
    if (/whisper|breathy|softly|murmur|hushed|intimate|sigh|耳语|气音|低语|轻声|轻柔|声音放轻|叹息|轻叹|轻哄/.test(t)) {
      return { cls: 'fx-whisper', label: '微距气音', mood: 'whisper' };
    }
    if (/calm|executive|cold|restrained|firm|low\s+voice|composed|克制|冷冽|沉稳|压低|微冷|冷硬|冷淡|轻哂|放慢|强忍|压着|发沉/.test(t)) {
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

  const ZH_VOICE_TAG_TOKEN_RE = /^(?:轻声|低声|耳语|气音|停顿|长停顿|短停顿|停顿半拍|微颤|颤抖|轻颤|声颤|克制|疲惫|倦怠|冷冽|冷淡|沉稳|平静|平淡|叹息|轻叹|低叹|叹气|抽气|倒吸一口气|屏息|急促|喘息|喘气|微喘|轻喘|喘|沙哑|微哑|柔声|低语|压低|压低声音|哽咽|泣声|哭腔|含泪|虚弱|失力|余韵|轻笑|冷笑|低笑|笑声|微笑|慌乱|紧张|窘迫|羞耻|羞涩|试探|挑眉|疑惑|缓声|放慢|语速放慢|迟疑|犹豫|沉默|顿了顿|顿了一下|温柔|冷笑一声|微怒|压抑|强忍|隐忍|娇喘|呢喃|喃喃|敷衍|轻哂|微冷|冷硬|发紧|发沉|发干|发虚|发涩|[a-zA-Z][a-zA-Z0-9_\s-]{0,36})$/;
  const NON_VOICE_BRACKET_RE = /^(?:N|[AD]\s*[:：].*|MOVE\s*[:：].*|ITEM-\d+|INTEL-\d+|CLK_[A-Z0-9_]+)$/i;

  function isFishBracketTag(inner, kind = '') {
    const trimmed = String(inner || '').trim();
    if (!trimmed || trimmed.length > 80 || /[\r\n\[\]]/.test(trimmed)) return false;
    if (NON_VOICE_BRACKET_RE.test(trimmed)) return false;
    if (kind === 'dialogue') return true;
    if (/^[a-zA-Z][a-zA-Z0-9_,\s-]{0,79}$/.test(trimmed)) return true;
    if (classifyVoiceTag(trimmed)) return true;
    const parts = trimmed.split(/[,，、;/\s]+/).map(s => s.trim()).filter(Boolean);
    return parts.length > 0 && parts.every(p => ZH_VOICE_TAG_TOKEN_RE.test(p));
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
      .replace(/\[([^\]\r\n]{1,80})\]/g, (full, inner) => (isFishBracketTag(inner, kind) ? '' : full))
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
    if (!$('input')) return;
    haptic(8);
    if (deckCollapsed) {
      deckCollapsed = false;
      controls();
      sizing();
    }
    const text = '（我看向' + speaker + '）「' + snippet + '」——';
    syncDraftInputs(text);
    save();
    if (isMobileViewport()) {
      openComposerSheet({ focus: true });
    } else {
      syncInputHeight($('input'));
      $('input').focus();
      controls();
      sizing();
    }
    toast('已引用' + speaker + '的台词至输入框');
  }

  function buildScenePlate(loc, still, clockStr, turnId) {
    const btn = node('button', 'cinema-plate is-scene');
    btn.type = 'button';
    btn.dataset.plateId = 'scene:' + turnId + ':' + loc;
    const frame = node('div', 'cinema-plate-frame');
    const im = node('img', 'cinema-plate-img');
    im.src = withThumb(still.url, 'plate');
    im.alt = loc + '场景空镜';
    im.loading = 'lazy';
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
    im.src = withThumb(asset.url, 'plate');
    im.alt = speaker + '剧照';
    im.style.objectPosition = asset.pos || '50% 18%';
    im.loading = 'lazy';
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
      'msg ' + kind + (isPlayer ? ' player' : '') + noAvatarCls + (whisper ? ' is-whisper' : '') + (opts.isPreview ? ' is-preview' : '') + (opts.isHistoricTurn ? ' is-historic' : '')
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
      const showFullMark = opts.showNarrationMark !== false || Boolean(opts.previewTag);
      const mark = node('div', showFullMark ? 'narration-mark' : 'narration-mark is-compact');
      if (showFullMark) {
        const diamond = svgEl('svg', { viewBox: '0 0 12 12', class: 'narration-diamond', 'aria-hidden': 'true' });
        diamond.append(svgEl('path', { d: 'M6 1 11 6 6 11 1 6Z', fill: 'currentColor' }));
        mark.append(diamond, node('span', '', '旁白'), diamond.cloneNode(true));
        if (opts.previewTag) mark.append(node('span', 'stream-preview-tag', opts.previewTag));
      }
      if (resolveVoiceSpeaker({ kind, speaker: '', text })) {
        const actions = node('span', 'msg-head-actions');
        const replay = node('button', 'msg-replay-btn');
        replay.type = 'button';
        replay.setAttribute('aria-label', '重听本段旁白');
        replay.title = '重听旁白';
        replay.append(icon('volume', 'chip-svg'));
        replay.onclick = e => {
          e.stopPropagation();
          haptic(8);
          unlock();
          const wasMuted = !cache.voice;
          cache.voice = true;
          save();
          if (wasMuted) syncVoicePlaybackPref(true);
          void speak({ kind, speaker: '', text }, id);
        };
        actions.append(replay);
        mark.append(actions);
      }
      el.append(mark);
    } else if (kind === 'handoff') {
      const h = node('div', 'message-heading');
      h.append(icon('scroll', 'chip-svg'), node('span', '', speaker));
      el.append(h);
    } else {
      if (charHasImg && !isNpcAction) {
        const im = node('img', 'avatar');
        const thumb = resolveCharacterAsset(speaker, { slot: 'into' });
        im.src = withThumb(thumb?.url || image(speaker, 'into.png'), 'avatar');
        im.alt = '';
        im.loading = 'lazy';
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
          mini.src = withThumb(thumb?.url || image(speaker, 'into.png'), 'avatar');
          mini.alt = '';
          mini.loading = 'lazy';
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
      if (kind === 'dialogue' && !opts.inHistory && isDrama3Speaker(speaker)) {
        const d3 = node('span', 'voice-d3-pill', 'D3');
        d3.title = 'Drama 3 导演声演';
        h.append(d3);
      }
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
      if (!opts.isPlayerInput && (kind === 'dialogue' || kind === 'action')) {
        const actions = node('span', 'msg-head-actions');
        if (resolveVoiceSpeaker({ kind, speaker, text, isPlayerInput: opts.isPlayerInput })) {
          const replay = node('button', 'msg-replay-btn');
          replay.type = 'button';
          replay.setAttribute('aria-label', '重听本句语音');
          replay.title = '重听语音';
          replay.append(icon('volume', 'chip-svg'));
          replay.onclick = e => {
            e.stopPropagation();
            haptic(8);
            unlock();
            const wasMuted = !cache.voice;
            cache.voice = true;
            save();
            if (wasMuted) syncVoicePlaybackPref(true);
            void speak({ kind, speaker, text }, id);
          };
          actions.append(replay);
        }

        if (!isPlayer && kind === 'dialogue' && !opts.inHistory) {
          const quoteBtn = node('button', 'msg-micro-btn', '引用');
          quoteBtn.type = 'button';
          quoteBtn.title = '引用此句至输入框';
          quoteBtn.onclick = e => {
            e.stopPropagation();
            quoteLineToInput(speaker, text);
          };
          actions.append(quoteBtn);
        }

        if (!isPlayer && kind === 'dialogue' && !opts.inHistory) {
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

      const physChecks = [];
      if (st.pregnant) {
        physChecks.push({
          tier: 'seep',
          badge: '孕期本能 · 防线坍缩',
          text: `${who}腹中已孕育着禁忌的骨血，孕期敏感与既成事实将羞耻上限压在低位（羞耻 ${st.shame} / 上限35）。`
        });
      } else if (st.phys?.pregnancy_stage === 'latent') {
        physChecks.push({
          tier: 'deception',
          badge: '生命微兆 · 潜伏着床',
          text: `${who}尚未知晓体内已悄然受孕，莫名的困倦与小腹微酸正悄然瓦解她的敏锐戒备。`
        });
      }
      if (st.phys?.masturbation_trace > 0) {
        physChecks.push({
          tier: 'seep',
          badge: '暗中自渎 · 把柄余韵',
          text: `${who}独处时借你气息暗中泄欲的余韵尚未散尽，面对你的目光时耳根发烫、底气尽失。`
        });
      }
      if (st.hasFluidLock) {
        physChecks.push({
          tier: 'seep',
          badge: '体液锁定 · 激素共振',
          text: `深处残留的滚烫体液正持续灼烧${who}的理智，欲望被强行锁在 ${st.phys?.fluid_lock_floor || 58} 底线之上（当前欲望 ${st.desire}）。`
        });
      }
      if (st.shame < 40 && st.affection > 75) {
        physChecks.push({
          tier: 'seep',
          badge: '暗流渗漏 · 被动触发',
          text: `高好感（${st.affection}）穿透低羞耻防线，无声的情欲暗流正在${who}心底自动滋长（欲望 ${st.desire}）。`
        });
      }

      const passiveChecks = [];
      const rat = rationalizationTier(st);
      if (st.passiveLv >= 4) {
        passiveChecks.push({
          tier: 'deception',
          badge: '防线支配 Lv.4 · 压迫生效',
          text: `${who}的防线侵蚀加深（0.7×上限），且完好防线好感截断已被支配压迫豁免（羞耻 ${st.shame}）。`
        });
      }
      if (st.passiveLv >= 2 && (hadShameDrop || rat)) {
        const closedLoop = Boolean(rat && !hadAffChange && hadShameDrop);
        passiveChecks.push({
          tier: 'deception',
          badge: closedLoop ? rat.text : '认知欺诈滤镜 Lv.2 · 检定生效',
          text: closedLoop
            ? `${who}的潜意识自动启动自我保护合理化，越界未损分毫好感（好感 ${st.affection}）。`
            : `认知滤镜正在软化${who}的抵触情绪，越界带来的心理反扑被悄然折半。`
        });
      }
      if (st.passiveLv >= 3 && (hadStaDrop || st.stamina <= 45)) {
        passiveChecks.push({
          tier: 'fatigue',
          badge: '疲劳诱导 Lv.3 · 躯体代偿',
          text: `交感神经高负荷紧绷正加倍抽空${who}的体力（当前体力 ${st.stamina} / 100）。`
        });
      }
      if (st.passiveLv >= 1) {
        let insight = '';
        if (st.shame > 80) {
          insight = `${who}表面仍维持着矜持防线（羞耻 ${st.shame}），但微绷的肩线与视线停顿已被你的洞察之瞳捕捉。`;
        } else if (st.shame >= 40) {
          insight = `${who}的羞耻防线已现松动裂隙（羞耻 ${st.shame}），呼吸的细微凌乱比言辞更诚实。`;
        } else {
          insight = `${who}的心理防线近乎瓦解（羞耻 ${st.shame}），残存的客套只剩最后一层薄纱。`;
        }
        passiveChecks.push({
          tier: 'insight',
          badge: `洞察之瞳 Lv.${st.passiveLv} · 检定成功`,
          text: insight
        });
      }

      // Pair top physiology cue + top passive cue so neither occludes the other (up to 2 total)
      if (physChecks.length) banners.push(physChecks[0]);
      if (passiveChecks.length) banners.push(passiveChecks[0]);
      if (banners.length < 2 && physChecks.length > 1) banners.push(physChecks[1]);
      if (banners.length < 2 && passiveChecks.length > 1) banners.push(passiveChecks[1]);
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
    const va = w?.visual_assets;
    const curVaSig = va
      ? Object.keys(va.scenes || {}).sort().join(',') + '/' + Object.entries(va.characters || {}).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => k + ':' + Object.keys(v || {}).sort().join(',')).join(';')
      : '';
    if (!inHistory && filter === 'all') {
      if (segmentDomCacheEpoch !== cache.epoch || segmentDomCachePlates !== includePlates || segmentDomCacheVaSig !== curVaSig) {
        segmentDomCache.clear();
        segmentDomCacheEpoch = cache.epoch;
        segmentDomCachePlates = includePlates;
        segmentDomCacheVaSig = curVaSig;
      }
    }
    let prevKind = '';
    let lastPlateLoc = '';
    const seenCharSlot = new Map();

    history.forEach((t, tIdx) => {
      const isLastTurn = tIdx === history.length - 1;
      const turnLoc = t.operation?.destination || t.location || (isLastTurn ? w?.location : '') || w?.location || '';
      const turnClock = t.settlement?.clock || (isLastTurn ? w?.progression?.runtime?.clock : null);
      const clockStr = turnClock ? formatGameClock(turnClock, isLastTurn ? (w?.weekday || '') : '') : '';
      const canCacheTurn = filter === 'all' && !inHistory && !isLastTurn
        && t.id !== snapshot?.playback?.segment_id
        && !(handoffPreview && handoffPreview.segmentId === t.id);

      let cacheKey = '';
      if (canCacheTurn) {
        const seenSig = Array.from(seenCharSlot.entries()).map(([k, v]) => k + '=' + v).join(',');
        cacheKey = t.id + '|' + t.messages.length + '|' + (t.handoff || '') + '|' + (t.settlement ? '1' : '0')
          + '|' + turnLoc + '|' + prevKind + '|' + lastPlateLoc + '|' + seenSig;
        const cached = segmentDomCache.get(cacheKey);
        if (cached) {
          for (const nd of cached.nodes) out.push(nd);
          prevKind = cached.endPrevKind;
          lastPlateLoc = cached.endPlateLoc;
          seenCharSlot.clear();
          for (const [k, v] of cached.endSeen) seenCharSlot.set(k, v);
          return;
        }
      }

      const turnNodes = [];
      const pushNode = el => {
        if (canCacheTurn) turnNodes.push(el);
        out.push(el);
      };

      if (includePlates && turnLoc && turnLoc !== lastPlateLoc) {
        const still = resolveSceneStill(turnLoc, turnClock?.time);
        if (still) {
          const sp = buildScenePlate(turnLoc, still, clockStr, t.id);
          sp.dataset.renderKey = 'splate:' + t.id + ':' + turnLoc;
          pushNode(sp);
          prevKind = 'plate';
        }
        lastPlateLoc = turnLoc;
        seenCharSlot.clear();
      }

      if (filter === 'all' && t.selection?.option_id !== 'BEGIN') {
        pushNode(entry(t.input_kind === 'action' ? 'action' : 'dialogue', '徐志北', t.input, t.id + ':input', { inHistory, isPlayerInput: true }));
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
              pushNode(cp);
              seenCharSlot.set(m.speaker, asset.slot);
              prevKind = 'plate';
            }
          }
        }

        const showNarrationMark = m.kind !== 'narration' ? true : prevKind !== 'narration';
        pushNode(entry(m.kind, m.speaker, m.text, t.id + ':' + i, { showNarrationMark, inHistory, isHistoricTurn }));
        prevKind = m.kind;
      });
      if (filter === 'all' && !inHistory && isLastTurn) {
        buildDiscoCheckBanners(t, isLastTurn, w).forEach((banner, bIdx) => {
          banner.dataset.renderKey = 'disco:' + t.id + ':' + bIdx;
          pushNode(banner);
        });
      }
      if (filter === 'all' && t.handoff) {
        pushNode(entry('handoff', '待处理', t.handoff, t.id + ':handoff', { inHistory }));
        prevKind = 'handoff';
      }
      if (t.settlement && (filter === 'settlement' || t.id !== snapshot?.playback?.segment_id)) {
        const sc = settlementCard(t.settlement, false);
        sc.dataset.renderKey = 'settle:' + t.id;
        pushNode(sc);
        prevKind = 'settlement';
      }
      if (canCacheTurn && cacheKey) {
        if (segmentDomCache.size > 60) {
          const firstKey = segmentDomCache.keys().next().value;
          if (firstKey !== undefined) segmentDomCache.delete(firstKey);
        }
        segmentDomCache.set(cacheKey, {
          nodes: turnNodes,
          endPrevKind: prevKind,
          endPlateLoc: lastPlateLoc,
          endSeen: Array.from(seenCharSlot.entries())
        });
      }
    });

    if (filter === 'all' && hasPreviewNodes()) {
      const reqId = streamPreview.request_id;
      const task = snapshot?.task;
      if (task?.action && task.selection?.option_id !== 'BEGIN') {
        out.push(entry('action', '徐志北', task.action, 'preview:' + reqId + ':input', { isPreview: true, inHistory, isPlayerInput: true }));
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
    const shopAdded = Array.isArray(s.shop_added) ? s.shop_added : [];
    const makeTaskPills = (mini = false) => {
      const list = [];
      if (shopAdded.length) {
        const btn = node('button', 'settlement-action-pill is-jade' + (mini ? ' is-mini' : ''));
        btn.type = 'button';
        btn.append(icon('shop'), node('span', '', '商城上架 +' + shopAdded.length + '件'));
        btn.onclick = () => {
          shopCatalog = null;
          openHub('shop');
        };
        list.push(btn);
      }
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

    if (foldable && (rewards.length || shopAdded.length || s.task_completed || s.task_issued || hasPendingReward)) {
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
    if (shopAdded.length) {
      detail.append(node('p', '', '商城定制上架：' + shopAdded.map(it => (it.grade ? ('[' + it.grade + '] ') : '') + '「' + it.name + '」(' + it.price + '分)').join('、')));
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
      const levObj = typeof s.leverage_triggered === 'object' ? s.leverage_triggered : null;
      const levName = levObj ? (levObj.intel_name || levObj.intel_id || '护盾生效') : String(s.leverage_triggered);
      const remRaw = levObj ? (levObj.remaining_charges ?? levObj.charges_remaining) : null;
      const rem = (remRaw !== null && remRaw !== undefined && Number.isFinite(Number(remRaw)) && !/（余\d+次）/.test(levName))
        ? ('，余 ' + Number(remRaw) + ' 次')
        : '';
      detail.append(node('p', '', '商业杠杆护盾：' + levName + '（越界掉好感减半 · 压制非目击警惕' + rem + '）'));
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

  const HOST_VITAL_GUIDE_KEYS = new Set(['体力', '亲密耐力', '宿主欲望', '道具恢复额度']);
  const CHAR_BAR_GUIDE_KEYS = new Set(['好感', '羞耻', '体力', '欲望', '堕落']);

  const STAT_GUIDE = {
    host: {
      '体力': {
        title: '当前体力',
        subtitle: '日常周旋与亲密拉扯的体能底盘',
        effect: '支撑每次行动消耗：日常轻 / 中 / 重度分别消耗 5 / 10 / 15；进入亲密纠缠第 2 拍起折减为 1 / 2 / 3，且只要亲密耐力 ≥ 15，体力最多锁底 10 不会中途断电。',
        gain: '安稳整夜入睡后满额恢复至 100；使用恢复类道具回补（受每日额度约束）；触发首次深层突破等强肾上腺素节点时可即时回涌 +30。',
        loss: '每次有效行动均按烈度扣减；若体力与耐力双双耗竭会触发力竭状态，并折损 1 点魅力。',
        live: ctx => {
          const parts = ['当前 ' + ctx.stamina + ' / 100'];
          if (ctx.sg?.active) parts.push('亲密护航生效中（锁底 ' + ctx.sg.floor + ' 不断电）');
          else if (ctx.stamina < 20) parts.push('体能偏低，建议补给或安稳休息');
          return parts.join(' · ');
        }
      },
      '亲密耐力': {
        title: '亲密耐力（精力）',
        subtitle: '深水纠缠中的持久续航与护航盾',
        effect: '决定亲密阶段的持久承压：耐力 ≥ 15 时可替当前体力托底（锁底 10 不断电）；魅力越高，每次释放消耗的耐力越少（<68 需 14，68–74 需 12，75 降为 11，85 降为 9，95 降为 8）。若耐力跌破 15，不仅失去锁底护航，且动作发沉令对方高潮推进倍率 -15%。',
        gain: '安稳整夜入睡后满额回满 100；非亲密跨小时自然回补（+8/小时）；使用体力 / 精力补给道具可同步回补 +15～+25；强肾上腺素突破可提振 +25。',
        loss: '亲密持续推进与临界释放会持续消耗耐力；连续 3 轮以上卡「极限控场」每轮额外消耗 -2；彻底力竭会折损 1 点魅力。',
        live: ctx => {
          const cost = ctx.charm >= 95 ? 8 : ctx.charm >= 85 ? 9 : ctx.charm >= 75 ? 11 : ctx.charm >= 68 ? 12 : 14;
          const guard = ctx.vigor >= 15 ? '护航就绪（≥15）' : '已跌破护航线（<15，高潮 -15%）';
          return '当前 ' + ctx.vigor + ' / 100 · ' + guard + ' · 当前释放耗耐约 ' + cost;
        }
      },
      '宿主欲望': {
        title: '宿主欲望（欲火）',
        subtitle: '蓄积的躁动张力与控欲临界火候',
        effect: '蓄满至 ≥ 85 会进入「控欲边缘」态，使对方高潮推进倍率额外 +10%；若连续 3 轮以上稳住不放则升入「极限控场」（对方高潮 +15%，但每轮额外消耗 2 点亲密耐力；引擎绝不代你失控）。',
        gain: '感官挑逗、近身肢体纠缠、亲密互动升温，以及独处时把玩私密珍藏（+18）都会推高欲火。',
        loss: '主动释放后大幅回落；更换地点（-15）、平静日常（-6）与长时间非亲密跨时（每小时 -5）会自然降温；整夜入睡后高欲留底 25，否则归零。',
        live: ctx => {
          const edge = Number(ctx.edgingStreak || 0);
          const tag = (ctx.desire >= 85 && edge >= 3) ? ('极限控场中（连蓄 ' + edge + ' 轮，高潮 +15% / 耐力 -2）')
            : ctx.desire >= 85 ? '已入控欲边缘（对方高潮 +10%）'
            : ctx.desire >= 60 ? '欲火灼烫，距控欲边缘还差 ' + (85 - ctx.desire) : '气息平稳';
          return '当前 ' + ctx.desire + ' / 100 · ' + tag;
        }
      },
      '道具恢复额度': {
        title: '道具恢复额度',
        subtitle: '单日借由补给品回血的安全上限',
        effect: '限制同一游戏日内通过随身补给品直接恢复体力的总量（每日上限 20 点），防止全靠药物透支身体。',
        gain: '每个新游戏日跨夜安稳入睡后自动重置回满至 20 / 20。',
        loss: '使用体力恢复类道具时按实际回复量扣减；额度耗尽后当日无法再借补给品强拉体力。',
        live: ctx => '今日剩余 ' + ctx.budget + ' / 20'
      },
      '积分': {
        title: '系统积分',
        subtitle: '深渊天平结算出的硬通货',
        effect: '用于在「系统商城」零体力兑换感官助兴器物、隐蔽布防装置、恢复补给及剧情定制稀缺品；魅力 ≥ 75 享 9 折，≥ 85 享 85 折。',
        gain: '每段有效互动按「情欲侵蚀 / 日常守护 / 商业权力」三轨择优结算（商业嗅觉 ≥ 80 时三轨收益额外 +15%），完成委托任务亦可一键领赏 +15～+80。',
        loss: '在系统商城兑换道具时按折后标价扣除。',
        live: ctx => {
          const disc = ctx.charm >= 85 ? '当前享 85 折' : ctx.charm >= 75 ? '当前享 9 折' : '魅力达 75 起解锁商城折扣';
          return '当前余额 ' + ctx.points + ' · ' + disc;
        },
        action: () => ({ label: '前往系统商城 →', run: () => openHub('shop') })
      },
      '经验值': {
        title: '掌控经验值',
        subtitle: '沉淀于心智博弈中的支配阅历',
        effect: '用于在「人物名册」为每位女主零体力解锁定向被动（Lv.1 需 20、Lv.2 需 50、Lv.3 需 110、Lv.4 需 220），每次成功升阶还会永久提升主角 +1 魅力。',
        gain: '与积分同源，随每轮互动三轨择优同步积累（商业嗅觉 ≥ 80 时额外 +15%），完成委托任务也可获赠 +8～+50。',
        loss: '在人物名册解锁女主定向被动阶梯时按门槛消耗。',
        live: ctx => {
          const ready = ctx.readyPassives || [];
          if (ready.length) return '当前 ' + ctx.exp + ' · 可立即为 ' + ready.join('、') + ' 升阶被动';
          return '当前 ' + ctx.exp + ' · 攒足门槛即可零体力解锁被动';
        },
        action: () => ({ label: '前往名册解锁被动 →', run: () => openHub('roster') })
      },
      '魅力': {
        title: '主角魅力',
        subtitle: '无声改写气场、容错与吸引力的个人磁力（底线 60）',
        effect: '五阶递进：<68（气场受挫：释放耐力增至 14、魅力突破门限升至 75）；68–74（清俊克制基准）；75（锋芒初显：正好感 +1、轻中越界减伤 25%、门限降 60、商城 9 折）；85（磁吸掌控：轻中减伤 40%、额外降羞 -1、高潮 +8%、商城 85 折）；95（深渊魅影：正好感 +2、轻中 50% / 深重 20% 减伤、额外降羞 -2、高潮 +15%）。',
        gain: '情欲温水攻心（同场限 1 次）、升级任意女主被动（+1）、女主身体任意部位首次突破 Lv.2 或 Lv.3（+1）、与女主达成同频绝顶（单场限 1 次）；单轮常规净增上限 +1。',
        loss: '单轮最多折损 -2 且不低于 60：遭徐承邺目击撞破（-2）、引发强烈羞耻反噬（-1）、自身彻底力竭（-1），或对高羞耻低堕落女主冒进亮出私密珍藏对峙（-1）。',
        live: ctx => {
          const ct = ctx.cTier;
          if (ct) {
            return '当前 ' + ct.charm + '（' + (ct.name || '清俊克制') + '）' + (ct.next_at ? (' · 距下一阶还差 ' + Math.max(0, ct.next_at - ct.charm) + ' 点') : ' · 已登顶阶');
          }
          return '当前 ' + ctx.charm + ' / 100';
        }
      },
      '商业嗅觉': {
        title: '商业嗅觉',
        subtitle: '看穿资本暗流与筹码结构的敏锐眼光（上限 100）',
        effect: '五阶递进：10（解锁初阶情报与隐秘货架）；30（跻身牌桌，解锁眼线情报与 T3 货架）；60（解锁「商业杠杆」，消耗 1 条情报展开 3 次越界护盾：每次 C 烈度掉分减半并压制当轮非目击警惕 -10）；80（深局棋手：三轨积分与经验收益 +15%，且信息反制减缓非目击警惕 15%）；100（全盘继承者视野）。',
        gain: '在涉及商业情报、资本布局、股权筹码与职场博弈的行动中按深度独立结算 +4 / +8 / +20（不再被更高积分的情感轨道吞没）。',
        loss: '一旦沉淀不会随时间自然衰减；武装「商业杠杆」仅消耗对应一次性情报，不扣嗅觉数值。',
        live: ctx => {
          const lv = ctx.biz >= 100 ? '全盘视野（+15%收益 · 反制警惕）'
            : ctx.biz >= 80 ? '深局棋手（三轨 +15% · 非目击警惕 -15%）'
            : ctx.biz >= 60 ? '可武装商业杠杆（距 80 阶深局棋手还差 ' + (80 - ctx.biz) + '）'
            : ctx.biz >= 30 ? '已跻身牌桌，距杠杆还差 ' + (60 - ctx.biz)
            : ctx.biz >= 10 ? '初探暗流，距 30 阶还差 ' + (30 - ctx.biz)
            : '尚未入门（距 10 阶还差 ' + (10 - ctx.biz) + '）';
          return '当前 ' + ctx.biz + ' / 100 · ' + lv;
        }
      }
    },
    char: {
      '好感': {
        title: '好感度',
        subtitle: '信任、偏爱与越界试探时的心理缓冲垫',
        effect: '决定她对你的亲近意愿与容错空间：好感 > 60 且羞耻已松动时，轻中度越界会转为自我合理化而不再掉分；但若高羞耻（≥85）且低堕落（<15）且被动不足 Lv.4，防线完好状态下亲情好感不会豁免越界惩罚。',
        gain: '日常安抚（<50）、自然社交回馈（<60）、深度交心共振（全段 +1～+2）、危机并肩破局（+3）、贴心赠礼与深层心理掌控均可稳步提升。',
        loss: '防线尚高时强行越界、遭抗拒硬闯或粗暴冒犯会明显掉分；高魅力、感官 Buff、被动 Lv.2、把柄与商业杠杆均可减伤，但多重叠加总减免封顶 75% 且未达合理化闭环时保底至少 -1。',
        live: ctx => {
          const notes = ['当前 ' + ctx.aff + ' / 100'];
          if (ctx.name === '苏婉青') {
            notes.push(ctx.aff >= 85 ? '已触及或突破 85 门槛（需真相揭露 / 温柔侵蚀放宽至 95）' : '默认封顶 85（可通过真相揭露或温柔侵蚀破限至 95）');
          } else if (ctx.shame >= 85 && ctx.dep < 15 && ctx.passiveLv < 4) {
            notes.push('当前防线完好：高好感暂不豁免越界掉分，宜先破冰降羞（<85）或升至被动 Lv.4');
          } else if (ctx.aff > 60) {
            notes.push('已入高好感缓冲段，配合降羞可大幅压低越界摩擦');
          }
          return notes.join(' · ');
        }
      },
      '羞耻': {
        title: '羞耻防线',
        subtitle: '矜持、伦理束缚与心理底线（越低越失守）',
        effect: '羞耻越高，对亲密越界的抵触越重；走低后逐步松开距离与言辞底线，且低于 40（配合好感 >75）会持续自然渗漏欲望。上限受当前堕落即时动态压制（100 − 堕落×0.6，Lv.4 为 ×0.7），确诊怀孕后永久锁顶 ≤ 35。',
        gain: '骤然清醒回神时的耻感反弹（+15），以及早中期低堕落（<30）安稳跨夜的小幅回稳（+1），均不会突破当前羞耻上限。',
        loss: '暧昧破冰（羞耻 >75 时 -3）、近身越界与亲密加深（-2～-6，偷情遮蔽态、堕落 >60、被动 Lv.3 疲倦破防或 Lv.4 均会放大）、撞破私密自渎（-6）、命中招牌部位及临界释放都会持续削弱；连续机械重复同烈度会触发同质化免疫。',
        live: ctx => {
          const cap = ctx.shameCap;
          return '当前 ' + ctx.shame + ' · 当前天花板 ' + cap + (ctx.isPreg ? '（孕期永久锁顶 ≤35）' : ('（受堕落 ' + ctx.dep + ' 压制）'));
        }
      },
      '欲望': {
        title: '情欲燥热',
        subtitle: '感官沉溺与理智融化的即时火候',
        effect: '直接放大高潮累积倍率并动摇羞耻防线；常规刺激最多推至 80，须凭主角魅力压迫（魅力 ≥ 75 门限 60、常规 70、<68 升至 75）或心理羞辱冲破 100 临界。',
        gain: '视 / 嗅 / 听多通道感官撩拨（单轮协同至多 +5）、直接肢体刺激（+10）、隔墙遮蔽偷情紧张感（+2）、感官类 Buff 协同、命中招牌部位（+3），以及低羞耻（<40）+ 高好感（>75）自动渗漏（+3）。',
        loss: '切换场景自然回落（-15）、绝顶清算回落至 35、暗中自渎回落至 40；若挂有「持续_体液锁定」则按浓烈 / 温热 / 余温三阶强制保底（85 / 72 / 58，累计内射 ≥3 次末段升至 62）。',
        live: ctx => {
          const tags = ['当前 ' + ctx.des + ' / 100'];
          if (ctx.hasFluidLock) tags.push('体液锁定保底生效中');
          else if (ctx.des >= 80) tags.push('已抵 80 临界，需魅力压迫或心理羞辱破百');
          if (ctx.shame < 40 && ctx.aff > 75) tags.push('已触发低羞高好感自动渗漏（+3/段）');
          return tags.join(' · ');
        }
      },
      '堕落': {
        title: '堕落刻痕',
        subtitle: '越界沉沦的不可逆印记与阶梯破锁',
        effect: '每 10 点堕落永久压低 6 点羞耻上限（Lv.4 为 7 点）并即时夹紧；超过 60 后一切降羞效果额外放大 1.5 倍，并同步加快高潮推进、解锁更私密的称谓与深水区主动迎合。',
        gain: '背德共谋（+2）、防线失守（+3）、绝顶蚀刻（+4）、私密自渎（+3）、深层屈从与首次突破（+5～+15）持续累积。设有 30 / 60 / 90 三道阶梯锁，触顶后须以关键主动破锁事件解开下一阶。',
        loss: '刻入认知与身体的习惯化印记，通常只增不退，不会因日常安抚或睡眠回退。',
        live: ctx => {
          const coef = ctx.passiveLv >= 4 ? 0.7 : 0.6;
          const stage = ctx.dep >= 90 ? '深渊沉溺（90+）' : ctx.dep >= 60 ? '沉沦加速（降羞 ×1.5）' : ctx.dep >= 30 ? '防线松动（30–59）' : '初生裂隙（0–29）';
          return '当前 ' + ctx.dep + ' / 100 · ' + stage + ' · 压低羞耻上限 ' + Math.floor(ctx.dep * coef);
        }
      },
      '体力': {
        title: '对方体力',
        subtitle: '精力余量与生理断电红线',
        effect: '衡量对方当前的承压与抗拒气力；跌至 ≤ 15 时会触发「生理断电」软倒余韵，无力再维持强硬防备（被动达 Lv.3 且体力 <60 时羞耻防线亦会额外动摇 -1）。',
        gain: '白日小憩恢复 +15（每人每日限 1 次）；虚脱期（体力 ≤25）选择温和日常照料可缓气回补 +5（至 30）；安稳整夜入睡恢复 +40（夜间自渎为 +32；确诊怀孕后整夜体力上限为 88）。',
        loss: '焦虑紧绷（-2）、日常劳作（-5）、剧烈抗拒（-15）、在场高欲空耗（-5）、暗中自渎（-8）与绝顶痉挛（-15）均会消耗；被动达 Lv.3 后焦虑 / 劳作 / 抗拒消耗翻倍。',
        live: ctx => {
          const tags = ['当前 ' + ctx.stamina + ' / 100'];
          if (ctx.stamina <= 15) tags.push('已触发低体力软倒红线（≤15），温和日常照料可缓气回体');
          else if (ctx.stamina < 60 && ctx.passiveLv >= 3) tags.push('体倦动摇（<60）：活跃 C 羞耻额外 -1');
          if (ctx.passiveLv >= 3) tags.push('被动 Lv.3 生效：劳作与抗拒消耗翻倍');
          return tags.join(' · ');
        }
      },
      '高潮': {
        title: '高潮累积',
        subtitle: '濒临失控的感官峰谷进度',
        effect: '蓄满 100 即触发绝顶清算：瞬间清空高潮、扣除对方 15 点体力、欲望回落至 35（受锁底保护），大幅击穿羞耻防线；若与主角同拍释放则达成同频绝顶，奖主角 +1 魅力。',
        gain: '亲密刺激按轻 / 中 / 重度基础推进 +15 / +30 / +50，并受欲望、堕落、身体部位开发阶梯、主角控欲边缘（+10%/+15%）、高阶魅力与累计内射惯性（≥3 次 +5%）多重调制（总倍率区间 0.45×～1.50×；主角耐力 <15 时 -15%）。',
        loss: '停止推进并切换场景时回落 -30；安稳睡眠或跨夜后残余高潮归零。'
      },
      '内射': {
        title: '深层内释次数',
        subtitle: '不可逆越界的累计刻印与受孕检定入口',
        effect: '每次触发都会递增计数、挂上 24 回合「持续_体液锁定」（三阶锁住高欲望底线），并自动触发一次受孕暗骰；累计达 3 次及以上时，身体惯性令体液锁定末段底线升至 62 且高潮倍率额外 +5%。',
        gain: '在亲密顶点选择深层内释时自动累加。',
        loss: '历史累计记录，不会减少。'
      },
      '怀孕': {
        title: '孕育状态',
        subtitle: '彻底改写关系走向的身份转折',
        effect: '确诊后立即扣减 30 点羞耻并将羞耻上限永久锁死在 ≤ 35，伴随孕期易倦体态（整夜体力恢复上限 88），深刻影响后续亲密互动、隐瞒博弈与家族暗线。',
        gain: '仅在未孕状态下发生深层内释时进行隐秘检定（常规 10%，高堕落 >80 或绝顶同拍达 40%；安全期 ×0.25、危险期 ×2）；命中后先经 2 天早孕潜伏期，跨日自动显影确诊。',
        loss: '一旦显影确诊为持久剧情状态，不会自行消退。'
      },
      '孕育状态': {
        title: '早孕潜伏期',
        subtitle: '尚未察觉却已在体内悄然生根的微兆',
        effect: '处于 2 天着床潜伏期内，表面尚无明显察觉；跨日到期后自动转正为确诊怀孕，并瞬间压低羞耻至 ≤ 35。',
        gain: '深层内释命中受孕暗骰后自动进入潜伏着床。',
        loss: '随游戏日历倒计时归零自动显影转正。'
      },
      '被动': {
        title: '定向支配被动',
        subtitle: '以主角经验值刻下的专属心理支配阶梯',
        effect: 'Lv.1 洞察之瞳（捕捉生理伪装与破绽）；Lv.2 认知欺诈滤镜（越界掉好感减半，叠加封顶 75% 且保底 -1）；Lv.3 疲劳诱导（焦虑 / 劳作 / 抗拒消耗翻倍，且目标体力 <60 时活跃 C 羞耻额外 -1）；Lv.4 防线支配（羞耻上限侵蚀 ×0.7、活跃 C 额外降羞 -2、高羞耻完好防线豁免与同质化穿透）。',
        gain: '消耗主角「经验值」在下方被动卡片零体力逐阶解锁（20 / 50 / 110 / 220），每次升阶同时永久奖主角 +1 魅力。',
        loss: '永久生效，不会降级。'
      },
      '生理周期': {
        title: '生理周期',
        subtitle: '十日一轮的自然节律相位',
        effect: '直接修正深层内释时的受孕检定倍率：安全期降为 0.25×（保底 2%），常规期为 1×，危险期翻倍至 2×（配合高堕落或绝顶极易受孕）。',
        gain: '随游戏日历按每位女主各自固定相位自然推进（每 10 天一轮）。',
        loss: '自然周期循环，不受单次互动直接改写。'
      },
      '欲求积压': {
        title: '欲求积压',
        subtitle: '在场高欲却迟迟未得纾解的焦灼段数',
        effect: '在场且高欲（>70）连续未得释放时积压；满 2 段会触发空耗疲惫扣除体力，并显著提高整夜独处时对方暗中自渎纾解的倾向。',
        gain: '女主在场且处于高欲状态，却未迎来绝顶或纾解时每段 +1。',
        loss: '绝顶清算、暗中自渎或触发一次空耗结算后清零；离场期间冻结不递增。'
      },
      '警惕': {
        title: '徐承邺监视态势',
        subtitle: '分渠道感知 · 分人物敏感度 · 五阶递进压迫',
        effect: '五阶推进：0–19 无察；20–39 起疑（远程消息/电话试探）；40–64 查岗（妻子苏婉青 40 起就有 15% 概率折返公寓，母妹 50 起 10% 回主宅）；65–84 紧盯（高频返城 30%–40%）；85+ 摊牌搜证（65% 在场）。母亲沈知韫在警惕 <45 时存在伦理盲区，徐承邺只会疑心争家业而不疑母子私情；发现 ≥3 目击锁定后警戒底线锁死 ≥50。',
        gain: '遵循「无现实渠道不涨警惕」铁律：徐承邺在外地且密室独处无来电/旁人时绝不凭空涨警惕；仅在当场察觉、来电/消息露馅或第三方外传时触发。按关系加权：妻子苏婉青 ×1.4（极敏，揭穿眼线且高好感低羞耻反水后降为 ×1.0）、母亲沈知韫 ×1.0、妹妹徐念薇 ×0.65（易掩护，但目击按满额）；身上留有未清理痕迹额外 +3，同场女主涨警惕时徐志北连带分担 30%。',
        loss: '未目击锁定前每完整游戏小时自然回落：苏婉青 -1.5/h（最慢）、沈知韫/徐志北 -2/h、徐念薇 -3/h（最快）；合理解释、转移注意、查岗化解（-5～-15）可主动压低，归零后清除疑点记录。一旦目击锁定，一切衰减与解释均失效。'
      }
    }
  };

  function buildStatGuidePanel(scope, statKey, ctx, onClose) {
    const entry = STAT_GUIDE[scope]?.[statKey];
    if (!entry) return null;
    const panel = node('section', 'stat-guide-panel');
    panel.setAttribute('role', 'region');
    panel.setAttribute('aria-label', entry.title + '说明');

    const head = node('div', 'stat-guide-head');
    const titleWrap = node('div', 'stat-guide-title');
    titleWrap.append(
      node('strong', '', entry.title),
      node('span', 'stat-guide-sub', entry.subtitle)
    );
    const closeBtn = node('button', 'stat-guide-close', '收起 ×');
    closeBtn.type = 'button';
    closeBtn.onclick = () => { haptic(6); onClose(); };
    head.append(titleWrap, closeBtn);
    panel.append(head);

    if (typeof entry.live === 'function') {
      const liveText = entry.live(ctx || {});
      if (liveText) {
        const liveBar = node('div', 'stat-guide-live');
        liveBar.append(node('span', 'stat-guide-live-dot', '✦'), node('span', '', liveText));
        panel.append(liveBar);
      }
    }

    const rows = node('div', 'stat-guide-rows');
    const mkRow = (tag, cls, text) => {
      const row = node('div', 'stat-guide-row');
      row.append(node('span', 'stat-guide-tag ' + cls, tag), node('p', 'stat-guide-text', text));
      return row;
    };
    rows.append(
      mkRow('作用', 'is-effect', entry.effect),
      mkRow('增长', 'is-gain', entry.gain),
      mkRow('减少', 'is-loss', entry.loss)
    );
    panel.append(rows);

    if (typeof entry.action === 'function') {
      const act = entry.action(ctx || {});
      if (act && act.label && typeof act.run === 'function') {
        const foot = node('div', 'stat-guide-foot');
        const btn = node('button', 'btn-outline stat-guide-action', act.label);
        btn.type = 'button';
        btn.onclick = () => { haptic(8); act.run(); };
        foot.append(btn);
        panel.append(foot);
      }
    }
    return panel;
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
    av.src = withThumb(image('徐志北', 'into.png'), 'avatar');
    av.alt = '徐志北';
    av.loading = 'lazy';
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
    const sg = staminaGuard(w);
    const hp = w?.intimate?.host_phys || {};
    const vigorVal = Number.isFinite(Number(hp.vigor)) ? Number(hp.vigor) : sg.vigor;
    const desireVal = Number.isFinite(Number(hp.desire)) ? Number(hp.desire) : 0;
    const desireTag = desireVal >= 85 ? ' · 临界蓄满' : (desireVal >= 60 ? ' · 欲火灼烫' : '');
    const vigorTag = sg.active ? (' · 护航锁底' + sg.floor) : (vigorVal <= 15 ? ' · 耐力见底' : '');
    const charmVal = host.stats['魅力']?.num ?? w.host_charm_tier?.charm ?? 70;
    const bizVal = host.stats['商业嗅觉']?.num ?? 0;
    const ptsVal = host.stats['积分']?.num ?? 0;
    const expVal = host.stats['经验值']?.num ?? 0;
    const readyPassives = [];
    if (Array.isArray(w.passive_tiers) && w.passive_tiers.length) {
      for (const hName of PEOPLE) {
        const rawP = panels[hName]?.stats?.['被动']?.raw || 'Lv.0';
        const lvM = /Lv\.(\d+)/.exec(rawP);
        const curLv = lvM ? Number(lvM[1]) : 0;
        const nextT = w.passive_tiers[curLv + 1];
        if (nextT && expVal >= nextT.cost) readyPassives.push(hName);
      }
    }
    const hostGuideCtx = {
      stamina: staminaVal,
      vigor: vigorVal,
      desire: desireVal,
      edgingStreak: Number(hp.edging_streak ?? 0),
      budget: budgetVal,
      charm: charmVal,
      biz: bizVal,
      points: ptsVal,
      exp: expVal,
      sg,
      cTier: w.host_charm_tier,
      readyPassives
    };
    const toggleHostInspect = key => {
      haptic(8);
      inspectedHostStat = inspectedHostStat === key ? '' : key;
      renderWorld(true);
    };

    const vitals = node('section', 'vitals-card');
    vitals.append(buildStaminaDualRing(staminaVal, budgetVal));
    const vDetails = node('div', 'vitals-details');

    const mkVitalRow = (statKey, label, valueText, pct, color) => {
      const isInsp = inspectedHostStat === statKey;
      const row = node('button', 'vital-row is-inspectable' + (isInsp ? ' is-inspected' : ''));
      row.type = 'button';
      row.setAttribute('aria-expanded', String(isInsp));
      row.onclick = () => toggleHostInspect(statKey);
      const top = node('div', 'vital-row-top');
      const lblWrap = node('span', 'vital-row-label');
      lblWrap.append(node('span', '', label), node('span', 'stat-info-dot', 'ⓘ'));
      top.append(lblWrap, node('b', '', valueText));
      const track = node('div', 'stat-track');
      const bar = node('span', 'stat-bar');
      bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
      bar.style.background = color;
      track.append(bar);
      row.append(top, track);
      return row;
    };

    vDetails.append(
      mkVitalRow('体力', '当前体力', staminaVal + ' / 100', staminaVal, staminaVal < 20 ? 'var(--crimson)' : 'linear-gradient(90deg, var(--jade), var(--gold-bright))'),
      mkVitalRow('亲密耐力', '亲密耐力（精力）', vigorVal + ' / 100' + vigorTag, vigorVal, vigorVal <= 15 ? 'var(--crimson)' : 'linear-gradient(90deg, #6e59a8, #b694f6)'),
      mkVitalRow('宿主欲望', '宿主欲望', desireVal + ' / 100' + desireTag, desireVal, desireVal >= 85 ? 'linear-gradient(90deg, #b83b5e, #ff7096)' : 'linear-gradient(90deg, #8e4658, #d87a8f)'),
      mkVitalRow('道具恢复额度', '道具恢复额度', budgetVal + ' / 20', (budgetVal / 20) * 100, 'linear-gradient(90deg, var(--gold-deep), var(--gold-bright))')
    );
    const note = node('p', 'muted', '轻点任一体能条或下方属性卡，查看沉浸作用与增减途径。');
    note.style.margin = '2px 0 0';
    vDetails.append(note);
    vitals.append(vDetails);
    pane.append(vitals);

    if (HOST_VITAL_GUIDE_KEYS.has(inspectedHostStat)) {
      const gPanel = buildStatGuidePanel('host', inspectedHostStat, hostGuideCtx, () => {
        inspectedHostStat = '';
        renderWorld(true);
      });
      if (gPanel) pane.append(gPanel);
    }

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
      const hasGuide = Boolean(STAT_GUIDE.host[item.key]);
      const isInsp = inspectedHostStat === item.key;
      const isClickable = isPoints || isExp || hasGuide;
      const tile = node(isClickable ? 'button' : 'div', 'attr-tile' + (isClickable ? ' is-clickable is-inspectable' : '') + (isInsp ? ' is-inspected' : ''));
      if (isClickable) {
        tile.type = 'button';
        tile.setAttribute('aria-expanded', String(isInsp));
        tile.onclick = () => {
          if (hasGuide) toggleHostInspect(item.key);
          else if (isPoints) openHub('shop');
          else if (isExp) openHub('roster');
        };
      }
      const head = node('div', 'attr-tile-head');
      const headTitle = node('span', 'attr-tile-name');
      headTitle.append(node('span', '', item.key));
      if (hasGuide) headTitle.append(node('span', 'stat-info-dot', 'ⓘ'));
      head.append(headTitle, icon(cfg.icon, 'chip-svg'));
      const val = node('div', 'attr-tile-val', item.raw);
      tile.append(head, val);
      if (isPoints) {
        tile.append(node('div', 'attr-tile-link', isInsp ? '下方可直达系统商城' : '释义 · 兑换商城'));
      } else if (isExp) {
        tile.append(node('div', 'attr-tile-link', isInsp ? '下方可直达人物名册' : '释义 · 解锁被动'));
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
    if (hostAttrs.length) {
      pane.append(grid);
      if (inspectedHostStat && !HOST_VITAL_GUIDE_KEYS.has(inspectedHostStat) && STAT_GUIDE.host[inspectedHostStat]) {
        const gPanel = buildStatGuidePanel('host', inspectedHostStat, hostGuideCtx, () => {
          inspectedHostStat = '';
          renderWorld(true);
        });
        if (gPanel) pane.append(gPanel);
      }
    }

    // 3a. Charm 5-Tier Perks & Host Fetish Card (Collapsible)
    const cTier = w.host_charm_tier;
    const fetishes = Array.isArray(hp.fetishes) ? hp.fetishes.filter(Boolean) : [];
    if (cTier || fetishes.length) {
      const cCard = node('details', 'hub-fold charm-tier-card');
      const cHead = node('summary', 'hub-fold-summary');
      const cTitleWrap = node('div', 'hub-fold-title');
      const cSubText = fetishes.length
        ? ('已显露 ' + fetishes.length + ' 项癖好' + (cTier?.summary ? ' · ' + cTier.summary : ''))
        : (cTier?.summary || '随魅力升阶解锁专属被动增益');
      cTitleWrap.append(
        node('strong', '', '魅力阶梯 · ' + (cTier?.name || '清俊克制')),
        node('span', 'muted', cSubText)
      );
      const cRight = node('span', 'fold-right');
      if (cTier) {
        cRight.append(node('span', 'quest-badge', cTier.next_at ? ('魅力 ' + cTier.charm + ' → ' + cTier.next_at) : ('魅力 ' + cTier.charm + ' · 最高阶')));
      }
      cRight.append(node('span', 'fold-caret', '▾'));
      cHead.append(cTitleWrap, cRight);
      cCard.append(cHead);

      const cBody = node('div', 'hub-fold-body');
      if (cTier) {
        const strip = node('div', 'intel-tier-strip');
        for (const [th, lbl] of [[68, '68 清俊'], [75, '75 锋芒'], [85, '85 磁吸'], [95, '95 魅影']]) {
          strip.append(node('span', 'intel-tier-pill' + ((cTier.charm ?? 70) >= th ? ' is-reached' : ''), lbl));
        }
        cBody.append(strip);
        if (cTier.summary) cBody.append(node('p', 'intel-desc', cTier.summary));
      }
      if (fetishes.length) {
        const fRow = node('div', 'fetish-chip-row');
        fRow.append(node('span', 'muted', '显露癖好：'));
        for (const f of fetishes) fRow.append(node('span', 'fetish-chip', '✦ ' + f));
        cBody.append(fRow);
      }
      cCard.append(cBody);
      pane.append(cCard);
    }

    // 3b. Commercial Sense, One-Time Intel & Business Leverage Card (Collapsible)
    const intel = w.intel;
    if (intel && Array.isArray(intel.catalog) && intel.catalog.length) {
      const bizVal = host.stats['商业嗅觉']?.num ?? 0;
      const levMin = intel.leverage_min_biz ?? 60;
      const heldSet = new Set(intel.held || []);
      const consumedSet = new Set(intel.consumed || []);
      const armedId = intel.leverage_armed || '';
      const levCharges = Math.max(0, Number(intel.leverage_charges || 0));
      const suAb = intel.su_ab_contacts ?? 0;
      const availCount = intel.catalog.filter(it => !heldSet.has(it.id) && !consumedSet.has(it.id) && bizVal >= (it.min_biz || 0) && suAb >= (it.min_su_ab_contacts || 0)).length;

      const iSec = node('details', 'hub-fold intel-section');
      if (armedId || levCharges > 0 || availCount > 0) iSec.open = true;
      const iHead = node('summary', 'hub-fold-summary');
      const iTitleWrap = node('div', 'hub-fold-title');
      iTitleWrap.append(
        node('strong', '', '商业嗅觉与一次性情报'),
        node('span', 'muted', '持有 ' + heldSet.size + (availCount ? (' · ' + availCount + ' 项可入库') : '') + (levCharges > 0 ? (' · 护盾余 ' + levCharges + ' 次') : '') + (armedId ? ' · 杠杆已预备' : ''))
      );
      const iRight = node('span', 'fold-right');
      iRight.append(node('span', 'quest-badge', '嗅觉 ' + bizVal + ' / 100'), node('span', 'fold-caret', '▾'));
      iHead.append(iTitleWrap, iRight);
      iSec.append(iHead);

      const iBody = node('div', 'hub-fold-body');
      const tierStrip = node('div', 'intel-tier-strip is-five');
      for (const [th, lbl] of [[10, '10 入门'], [30, '30 被看见'], [60, '60 杠杆'], [80, '80 深局'], [100, '100 视野']]) {
        tierStrip.append(node('span', 'intel-tier-pill' + (bizVal >= th ? ' is-reached' : ''), lbl));
      }
      iBody.append(tierStrip);

      if (levCharges > 0) {
        const shieldBanner = node('div', 'leverage-banner');
        shieldBanner.append(node('span', '', '商业杠杆护盾生效中：剩余 ' + levCharges + ' 次（后续 C 烈度自动减半越界掉好感并压制至多 10 点非目击警惕，非 C 烈度不消耗）'));
        iBody.append(shieldBanner);
      }

      if (armedId) {
        const armedItem = intel.catalog.find(x => x.id === armedId);
        const banner = node('div', 'leverage-banner');
        banner.append(node('span', '', '商业杠杆已预备：「' + (armedItem ? armedItem.name : armedId) + '」（下次 C 烈度展开 3 次越界护盾并压制非目击警惕，非 C 烈度不浪费）'));
        const disarmBtn = node('button', 'btn-outline', '取消预备');
        disarmBtn.type = 'button';
        disarmBtn.disabled = !canTransactDeterministic();
        disarmBtn.onclick = () => void toggleBusinessLeverage('disarm', '');
        banner.append(disarmBtn);
        iBody.append(banner);
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
            const cur = ($('input')?.value || cache.draft || '').trim();
            const cue = '（亮出私下掌握的情报「' + it.name + '」作为筹码）';
            const nextVal = cur ? (cur + ' ' + cue) : cue;
            syncDraftInputs(nextVal);
            save();
            if (isMobileViewport()) {
              openComposerSheet({ focus: true });
            } else {
              syncInputHeight($('input'));
              controls();
              sizing();
              $('input')?.focus();
            }
            toast('已填入情报亮牌提示，确认补充行动后发送');
          };
          acts.append(cueBtn);
        }
        if (acts.children.length) ic.append(acts);
        iBody.append(ic);
      }
      iSec.append(iBody);
      pane.append(iSec);
    }

    // 4. Compact Chronicle Stats Bar
    const summary = node('section', 'host-chronicle-strip');
    summary.append(
      node('strong', '', w.interaction.count + ' 段已存剧情 · ' + w.interaction.actions + ' 次行动'),
      node('span', 'muted', pg ? '跨零点或体力 < 5 自动收束回合' : '正式演播存档')
    );
    pane.append(summary);

    return pane;
  }

  function renderRosterTab(w, panels) {
    const pane = node('div', 'hub-pane');
    const rosterNames = [
      ...PEOPLE,
      ...Object.keys(panels).filter(k => k !== '系统宿主' && !PEOPLE.includes(k))
    ];
    if (w.vigilance && !rosterNames.includes('徐承邺')) {
      rosterNames.push('徐承邺');
    }
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
        im.src = withThumb(image(name, 'into.png'), 'avatar');
        im.alt = '';
        im.loading = 'lazy';
        im.decoding = 'async';
        thumbWrap.append(im);
      } else {
        thumbWrap.append(node('span', 'roster-thumb-fallback', name.slice(0, 1)));
      }
      thumbWrap.append(node('i', 'presence-dot' + (isHere ? ' is-here' : '')));

      const info = node('span', 'roster-pill-info');
      let pillSub = pInfo['好感'] ? ('好感 ' + pInfo['好感'].raw) : (w.presence?.[name]?.location || meta.role);
      if (name === '徐承邺' && w.vigilance) {
        const maxV = Math.max(0, ...(w.vigilance.targets || []).map(x => Number(x.vigilance) || 0));
        pillSub = (w.vigilance.position || '外地') + (maxV >= 20 ? (' · 警惕 ' + maxV) : '');
      }
      info.append(
        node('strong', '', name),
        node('span', '', pillSub)
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
      img.src = withThumb(slots.into || Object.values(slots)[0] || image(name, 'into.png'), 'plate');
      img.alt = name;
      img.loading = 'lazy';
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
    const charBuffs = w.buffs?.[name] || [];
    const rawPassiveForGuide = charPanel.stats['被动']?.raw || 'Lv.0';
    const passiveLvM = /Lv\.(\d+)/.exec(rawPassiveForGuide);
    const passiveLvNum = passiveLvM ? Number(passiveLvM[1]) : 0;
    const depNum = charPanel.stats['堕落']?.num ?? 0;
    const isPregBool = charPanel.stats['怀孕']?.bool === true;
    const baseShameCap = Math.max(0, 100 - Math.floor(depNum * 0.6));
    const charGuideCtx = {
      name,
      aff: charPanel.stats['好感']?.num ?? 0,
      shame: charPanel.stats['羞耻']?.num ?? 0,
      stamina: charPanel.stats['体力']?.num ?? 0,
      des: charPanel.stats['欲望']?.num ?? 0,
      dep: depNum,
      passiveLv: passiveLvNum,
      isPreg: isPregBool,
      shameCap: isPregBool ? Math.min(35, baseShameCap) : baseShameCap,
      hasFluidLock: charBuffs.some(b => String(b?.name || '').includes('体液锁定'))
    };
    const toggleCharInspect = key => {
      haptic(8);
      inspectedCharStat = inspectedCharStat === key ? '' : key;
      renderWorld(true);
    };

    const barItems = name === '徐承邺' ? [] : charPanel.ordered.filter(it => barMeta[it.key] && it.num !== null);
    if (barItems.length) {
      body.append(node('div', 'stat-inspect-hint', '轻点任意属性或状态标签，查看沉浸作用与增减途径'));
      const grid = node('div', 'char-bars-grid');
      for (const it of barItems) {
        const hasGuide = Boolean(STAT_GUIDE.char[it.key]);
        const isInsp = inspectedCharStat === it.key;
        const bCard = node(hasGuide ? 'button' : 'div', 'char-bar-card' + (hasGuide ? ' is-inspectable' : '') + (isInsp ? ' is-inspected' : ''));
        if (hasGuide) {
          bCard.type = 'button';
          bCard.setAttribute('aria-expanded', String(isInsp));
          bCard.onclick = () => toggleCharInspect(it.key);
        }
        const top = node('div', 'char-bar-top');
        const lblWrap = node('span', 'char-bar-label');
        lblWrap.append(node('span', '', it.key));
        if (hasGuide) lblWrap.append(node('span', 'stat-info-dot', 'ⓘ'));
        top.append(lblWrap, node('b', '', it.raw));
        const track = node('div', 'stat-track');
        const fill = node('span', 'stat-bar');
        fill.style.width = Math.max(0, Math.min(100, it.num)) + '%';
        fill.style.background = barMeta[it.key];
        track.append(fill);
        bCard.append(top, track);
        grid.append(bCard);
      }
      body.append(grid);
      if (CHAR_BAR_GUIDE_KEYS.has(inspectedCharStat) && barItems.some(it => it.key === inspectedCharStat)) {
        const gPanel = buildStatGuidePanel('char', inspectedCharStat, charGuideCtx, () => {
          inspectedCharStat = '';
          renderWorld(true);
        });
        if (gPanel) body.append(gPanel);
      }
    }

    // Remaining Secondary Status Chips (高潮 / 内射 / 怀孕 / 被动 / etc.)
    const chipItems = charPanel.ordered.filter(it => !barMeta[it.key]);
    const phys = w.physiology?.[name];
    const renderedChipKeys = new Set();
    const mkStatusChip = (chipKey, label, valueText) => {
      const hasGuide = Boolean(STAT_GUIDE.char[chipKey]);
      const isInsp = inspectedCharStat === chipKey;
      renderedChipKeys.add(chipKey);
      const chip = node(hasGuide ? 'button' : 'span', 'status-chip' + (hasGuide ? ' is-inspectable' : '') + (isInsp ? ' is-inspected' : ''));
      if (hasGuide) {
        chip.type = 'button';
        chip.setAttribute('aria-expanded', String(isInsp));
        chip.onclick = () => toggleCharInspect(chipKey);
      }
      chip.append(node('span', '', label), node('b', '', valueText));
      if (hasGuide) chip.append(node('span', 'stat-info-dot', 'ⓘ'));
      return chip;
    };
    if (chipItems.length || phys) {
      const chips = node('div', 'status-chip-row');
      for (const it of chipItems) {
        const display = it.bool === true ? '是' : it.bool === false ? '否' : it.raw;
        chips.append(mkStatusChip(it.key, it.key, display));
      }
      if (phys) {
        if (phys.cycle_phase) {
          chips.append(mkStatusChip('生理周期', '生理周期', phys.cycle_phase));
        }
        if (phys.pregnancy_stage === 'latent') {
          const daysTxt = Number.isFinite(Number(phys.latent_days_left)) ? ('（剩' + phys.latent_days_left + '天显影）') : '';
          chips.append(mkStatusChip('孕育状态', '孕育状态', '潜伏着床' + daysTxt));
        }
        if (Number(phys.unrelieved_streak) > 0) {
          chips.append(mkStatusChip('欲求积压', '欲求积压', phys.unrelieved_streak + ' 段'));
        }
      }
      body.append(chips);
      if (renderedChipKeys.has(inspectedCharStat) && STAT_GUIDE.char[inspectedCharStat]) {
        const gPanel = buildStatGuidePanel('char', inspectedCharStat, charGuideCtx, () => {
          inspectedCharStat = '';
          renderWorld(true);
        });
        if (gPanel) body.append(gPanel);
      }
    }

    // Persistent BUFF Badges (e.g., 持续_体液锁定)
    if (charBuffs.length) {
      const bRow = node('div', 'buff-row');
      for (const b of charBuffs) {
        const badge = node('span', 'buff-badge');
        badge.append(node('b', '', b.name), node('span', '', '剩 ' + b.turns + ' 行动' + (b.effect ? ' · ' + b.effect : '')));
        bRow.append(badge);
      }
      body.append(bRow);
    }

    // 5-Zone Body Development & Signature Sensitive Zone Card (Heroines only · Collapsible)
    if (PEOPLE.includes(name)) {
      const bzMeta = w.body_zone_meta || {};
      const zones = Array.isArray(bzMeta.zones) && bzMeta.zones.length ? bzMeta.zones : ['oral', 'hand', 'chest', 'foot', 'core'];
      const zLabels = bzMeta.labels || { oral: '口舌', hand: '纤手', chest: '胸乳', foot: '玉足', core: '深处' };
      const sigMap = bzMeta.signatures || { '沈知韫': 'foot', '苏婉青': 'chest', '徐念薇': 'hand' };
      const lvLabels = Array.isArray(bzMeta.level_labels) && bzMeta.level_labels.length >= 4
        ? bzMeta.level_labels : ['生涩防备', '敏感初开', '熟稔沉溺', '彻底开发'];
      const sigZone = sigMap[name] || '';
      const hDev = w.intimate?.body_dev?.[name] || {};
      const sigScore = sigZone ? Math.max(0, Math.min(100, Number(hDev[sigZone]) || 0)) : 0;
      const sigLv = sigScore >= 80 ? 3 : sigScore >= 50 ? 2 : sigScore >= 20 ? 1 : 0;
      const devCount = zones.filter(z => (Number(hDev[z]) || 0) >= 20).length;

      const bdCard = node('details', 'hub-fold body-dev-card');
      const bdHead = node('summary', 'hub-fold-summary');
      const bdTitle = node('div', 'hub-fold-title');
      bdTitle.append(
        node('strong', '', '身体开发 · 部位敏感度'),
        node('span', 'muted', (sigZone ? ('招牌 ' + (zLabels[sigZone] || sigZone) + ' Lv.' + sigLv + ' · ') : '') + '已开敏 ' + devCount + ' / ' + zones.length + ' 部位')
      );
      const bdRight = node('span', 'fold-right');
      bdRight.append(
        sigZone ? node('span', 'sig-zone-pill', '★ 招牌：' + (zLabels[sigZone] || sigZone)) : node('span', 'item-tag', '5 部位'),
        node('span', 'fold-caret', '▾')
      );
      bdHead.append(bdTitle, bdRight);
      bdCard.append(bdHead);

      const bdBody = node('div', 'hub-fold-body');
      const bdGrid = node('div', 'body-dev-grid');
      for (const z of zones) {
        const sc = Math.max(0, Math.min(100, Number(hDev[z]) || 0));
        const lv = sc >= 80 ? 3 : sc >= 50 ? 2 : sc >= 20 ? 1 : 0;
        const isSig = z === sigZone;
        const item = node('div', 'body-dev-item' + (isSig ? ' is-signature' : ''));
        const top = node('div', 'body-dev-top');
        top.append(
          node('span', 'body-dev-name', (zLabels[z] || z) + (isSig ? ' ★' : '')),
          node('b', '', 'Lv.' + lv + ' · ' + sc)
        );
        const track = node('div', 'stat-track');
        const fill = node('span', 'stat-bar');
        fill.style.width = sc + '%';
        fill.style.background = isSig
          ? 'linear-gradient(90deg, #b83b5e, #f2b483)'
          : 'linear-gradient(90deg, #7d4a69, #d48ba8)';
        track.append(fill);
        item.append(top, track, node('div', 'body-dev-lv', lvLabels[lv] || ''));
        bdGrid.append(item);
      }
      bdBody.append(
        bdGrid,
        node('p', 'stat-inline-note', '五区开发只增不退（Lv.0–3：0 / 20 / 50 / 80），单回至多聚焦 2 区（轻中 +4 / 深度 +8），随阶梯叠加 +5% / +12% / +22% 高潮推进；命中 ★ 招牌部位享 1.35× 成长与额外降羞，首破 Lv.2 / Lv.3 同步奖主角 +1 魅力（单回净涨封顶 +1）。')
      );
      bdCard.append(bdBody);
      body.append(bdCard);
    }

    // Deterministic EXP Passive Skill Upgrade Card (Heroines only · Collapsible)
    if (PEOPLE.includes(name) && Array.isArray(w.passive_tiers) && w.passive_tiers.length) {
      const rawPassive = charPanel.stats['被动']?.raw || 'Lv.0';
      const lvM = /Lv\.(\d+)/.exec(rawPassive);
      const curLv = lvM ? Number(lvM[1]) : 0;
      const curTier = w.passive_tiers[curLv] || w.passive_tiers[0];
      const nextTier = w.passive_tiers[curLv + 1] || null;
      const hostExp = panels['系统宿主']?.stats?.['经验值']?.num ?? 0;
      const canUnlockNow = Boolean(nextTier && hostExp >= nextTier.cost);

      const pCard = node('details', 'hub-fold passive-card');
      if (canUnlockNow) pCard.open = true;
      const pHead = node('summary', 'hub-fold-summary');
      const pTitle = node('div', 'hub-fold-title');
      pTitle.append(
        node('strong', '', '定向被动 · ' + curTier.tag + ' ' + curTier.name),
        node('span', 'muted', nextTier ? (canUnlockNow ? ('可解锁下一阶 ' + nextTier.tag) : ('下阶需 ' + nextTier.cost + ' 经验')) : '已达最高阶防线支配')
      );
      const pRight = node('span', 'fold-right');
      pRight.append(node('span', 'item-tag' + (canUnlockNow ? ' is-effect' : ''), '经验 ' + hostExp), node('span', 'fold-caret', '▾'));
      pHead.append(pTitle, pRight);
      pCard.append(pHead);

      const pBody = node('div', 'hub-fold-body');
      pBody.append(node('p', 'passive-effect', curTier.effect));

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
        pBody.append(nextBox);
      } else {
        pBody.append(node('span', 'item-tag is-effect', '已达最高阶防线支配'));
      }
      pCard.append(pBody);
      body.append(pCard);
    }

    // Dedicated Vigilance Monitor Panel for 徐承邺 (strictly hides 发现几率)
    if (name === '徐承邺' && w.vigilance) {
      const vCard = node('section', 'vigilance-card');
      const vHead = node('div', 'vigilance-head');
      const isHome = w.vigilance.position === '徐家主宅' || w.vigilance.position === '徐家住宅';
      const vTitleBtn = node('button', 'vigilance-guide-btn' + (inspectedCharStat === '警惕' ? ' is-inspected' : ''));
      vTitleBtn.type = 'button';
      vTitleBtn.setAttribute('aria-expanded', String(inspectedCharStat === '警惕'));
      vTitleBtn.append(node('strong', '', '徐承邺监视态势'), node('span', 'stat-info-dot', 'ⓘ'));
      vTitleBtn.onclick = () => toggleCharInspect('警惕');
      vHead.append(
        vTitleBtn,
        node('span', 'vigilance-pos-pill' + (isHome ? ' is-home' : ''), isHome ? '徐家主宅 · 正在主宅' : (w.vigilance.position || '外地'))
      );
      vCard.append(vHead);
      if (inspectedCharStat === '警惕') {
        const gPanel = buildStatGuidePanel('char', '警惕', charGuideCtx, () => {
          inspectedCharStat = '';
          renderWorld(true);
        });
        if (gPanel) vCard.append(gPanel);
      }
      const discLabels = { 0: '无察', 1: '怀疑', 2: '线索', 3: '目击锁定', 4: '实锤' };
      const fallbackRole = {
        '苏婉青': '妻子 · 极敏',
        '沈知韫': '母亲 · 伦理盲区',
        '徐念薇': '妹妹 · 易掩护',
        '徐志北': '养弟 · 连带汇聚'
      };
      const vList = node('div', 'vigilance-list');
      for (const t of (w.vigilance.targets || [])) {
        const vRow = node('div', 'vigilance-row');
        const vTop = node('div', 'vigilance-row-top');
        const stageNum = Number.isFinite(Number(t.stage))
          ? Number(t.stage)
          : (t.discovery >= 3 || t.vigilance >= 85 ? 4 : t.vigilance >= 65 ? 3 : t.vigilance >= 40 ? 2 : t.vigilance >= 20 ? 1 : 0);
        const stageLbl = t.stage_label || (t.discovery >= 3 ? (discLabels[t.discovery] || '目击锁定') : ['无察', '起疑', '查岗', '紧盯', '摊牌'][stageNum] || '无察');
        const roleLbl = t.role_label || fallbackRole[t.name] || '';
        const leftWrap = node('span', 'vigilance-row-left');
        leftWrap.append(node('span', '', t.name));
        if (roleLbl) leftWrap.append(node('span', 'vigilance-role-pill', roleLbl));
        leftWrap.append(node('span', 'vigilance-stage-pill is-tier-' + stageNum, stageLbl));
        vTop.append(
          leftWrap,
          node('b', '', '警惕 ' + t.vigilance + ' / 100')
        );
        const track = node('div', 'stat-track');
        const fill = node('span', 'stat-bar');
        fill.style.width = Math.max(0, Math.min(100, t.vigilance)) + '%';
        fill.style.background = stageNum >= 3
          ? 'linear-gradient(90deg, #9f4448, #e07272)'
          : stageNum === 2
            ? 'linear-gradient(90deg, #b87333, #f2b47c)'
            : stageNum === 1
              ? 'linear-gradient(90deg, #b99968, #f0d7a8)'
              : 'linear-gradient(90deg, #4b8f6f, #7ecba4)';
        track.append(fill);
        vRow.append(vTop, track);
        if (t.reason) {
          vRow.append(node('div', 'vigilance-reason', '疑点：' + t.reason));
        }
        vList.append(vRow);
      }
      vCard.append(vList, node('span', 'muted', '轻点标题查看分渠道、分人物敏感度与五阶回返机制；外地密室无外传渠道绝不凭空涨警惕。'));
      body.append(vCard);
    }

    if (!charPanel.ordered.length && !(name === '徐承邺' && w.vigilance)) {
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

    const devCountByLoc = {};
    for (const dev of (w.deployed_items || [])) {
      const dl = dev?.location || '';
      if (dl) devCountByLoc[dl] = (devCountByLoc[dl] || 0) + 1;
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
    const travelCost = customReserveCost(w);
    const travelAllowed = !isHere && !ordinaryBlocked() && afford(travelCost);
    const reasonText = isHere ? '你此刻正身处此地'
      : !canDecide() ? '请先读完本段剧情后再启程'
      : resting() ? '当前需先完成休整'
      : !afford(travelCost) ? ('当前体力不足 ' + travelCost)
      : (travelCost > 0 ? ('将作为自定义行动提交 · 暂扣 ' + travelCost + ' 体力') : '亲密护航中 · 将作为自定义行动提交');
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
      if (devCountByLoc[loc]) {
        title.append(node('span', 'map-device-badge', '📷 ' + devCountByLoc[loc] + ' 台装置'));
      }
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

    const curTask = w.tasks?.current;
    const pendingQueue = Array.isArray(w.tasks?.pending_items) && w.tasks.pending_items.length
      ? w.tasks.pending_items
      : (w.tasks?.pending_item ? [w.tasks.pending_item] : []);

    const allItems = w.items || [];
    const heldItems = allItems.filter(it => (it.fields?.['当前状态'] || '仓库中') !== '已交付');
    const deployedItems = Array.isArray(w.deployed_items) ? w.deployed_items : [];
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
    const castHere = Array.isArray(w.cast) ? w.cast : [];
    const custCost = customReserveCost(w);
    const custBadge = custCost > 0 ? (' (-' + custCost + '⚡)') : ' (护航0⚡)';
    const keepsakes = Array.isArray(w?.intimate?.keepsakes) ? w.intimate.keepsakes.filter(k => k && k.id && k.name) : [];

    // Smart default sub-tab: prioritize claimable quest rewards, else held items
    const subKey = activeBagSubTab || (pendingQueue.length ? 'quest' : 'held');
    const subBar = node('div', 'sub-pill-bar');
    subBar.setAttribute('role', 'tablist');
    const bagTabs = [
      ['held', '随身', heldItems.length, false],
      ['keepsakes', '珍藏', keepsakes.length, false],
      ['quest', '委托', (curTask ? 1 : 0) + pendingQueue.length, pendingQueue.length > 0],
      ['deployed', '已部署', deployedItems.length, false],
      ['gifted', '已赠予', giftedItems.length, false]
    ];
    for (const [k, label, cnt, alertDot] of bagTabs) {
      const btn = node('button', 'sub-pill-btn' + (subKey === k ? ' is-active' : ''));
      btn.type = 'button';
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', String(subKey === k));
      btn.append(node('span', '', label));
      if (cnt > 0) btn.append(node('em', 'sub-pill-cnt', String(cnt)));
      if (alertDot) btn.append(node('i', 'sub-pill-dot'));
      btn.onclick = () => {
        haptic(8);
        activeBagSubTab = k;
        renderWorld(true);
      };
      subBar.append(btn);
    }
    pane.append(subBar);

    if (subKey === 'quest') {
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
          claimCard.append(node('p', 'muted', '后续待领：' + pendingQueue.slice(1).join('；')));
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
      } else if (!pendingQueue.length) {
        const emptyQ = node('section', 'empty-card');
        emptyQ.append(icon('scroll'), node('p', '', '此刻暂无进行中委托，随剧情推进自动承接下一项'));
        pane.append(emptyQ);
      }

      if (w.tasks?.history?.length) {
        const histBox = node('details', 'settlement-details');
        histBox.style.padding = '0 6px';
        histBox.append(node('summary', '', '查看已完成委托（' + w.tasks.history.length + '） ▾'));
        for (const h of w.tasks.history) histBox.append(node('p', 'muted', h));
        pane.append(histBox);
      }
      return pane;
    }

    const renderInlinePicker = (item, usageMode) => {
      if (!bagPickerState || bagPickerState.itemId !== item.id) return null;
      const box = node('div', 'bag-inline-picker');

      if (bagPickerState.mode === 'use') {
        const targets = [...castHere, '室内氛围'];
        if (!targets.includes(bagPickerState.target)) bagPickerState.target = targets[0] || '室内氛围';
        box.append(node('div', 'bag-picker-title', '选择作用目标'));
        const chips = node('div', 'bag-picker-chips');
        for (const t of targets) {
          const b = node('button', 'bag-picker-chip' + (bagPickerState.target === t ? ' is-active' : ''), t);
          b.type = 'button';
          b.onclick = () => {
            bagPickerState = { ...bagPickerState, target: t };
            renderWorld(true);
          };
          chips.append(b);
        }
        box.append(chips);
        const foot = node('div', 'bag-picker-foot');
        const confirmBtn = node('button', 'btn-gold', '挂载并写行动' + custBadge);
        confirmBtn.type = 'button';
        confirmBtn.disabled = ordinaryBlocked() || !afford(custCost);
        confirmBtn.onclick = () => {
          const tgt = bagPickerState.target || '室内氛围';
          attachOperationToComposer({
            operation: { code: 'use_item', item_id: item.id, target: tgt },
            label: '🧴 使用「' + item.name + '」→ ' + tgt,
            defaultAction: tgt === '室内氛围'
              ? ('（拿出' + item.name + '，在屋内启用营造氛围）')
              : ('（拿出' + item.name + '，自然地对' + tgt + '使用）')
          });
        };
        const cancelBtn = node('button', 'btn-outline', '取消');
        cancelBtn.type = 'button';
        cancelBtn.onclick = () => { bagPickerState = null; renderWorld(true); };
        foot.append(confirmBtn, cancelBtn);
        box.append(foot);
      } else if (bagPickerState.mode === 'deploy') {
        box.append(node('div', 'bag-picker-title', '安装位置（当前：' + (w.location || '当前地点') + '）'));
        const chips = node('div', 'bag-picker-chips');
        for (const sp of DEPLOY_SPOT_PRESETS) {
          const b = node('button', 'bag-picker-chip' + (bagPickerState.spot === sp ? ' is-active' : ''), sp);
          b.type = 'button';
          b.onclick = () => {
            bagPickerState = { ...bagPickerState, spot: sp };
            renderWorld(true);
          };
          chips.append(b);
        }
        box.append(chips);
        const spotInput = node('input', 'bag-picker-input');
        spotInput.type = 'text';
        spotInput.maxLength = 40;
        spotInput.placeholder = '自定义安装点位（如：床头灯座后侧）';
        spotInput.value = bagPickerState.spot || '';
        spotInput.oninput = () => { bagPickerState.spot = spotInput.value; };
        box.append(spotInput);

        const hideLabel = node('label', 'bag-picker-check');
        const hideChk = node('input');
        hideChk.type = 'checkbox';
        hideChk.checked = bagPickerState.hidden !== false;
        hideChk.onchange = () => { bagPickerState.hidden = hideChk.checked; };
        hideLabel.append(hideChk, node('span', '', '隐蔽部署（尽量避免被在场人察觉）'));
        box.append(hideLabel);

        const foot = node('div', 'bag-picker-foot');
        const confirmBtn = node('button', 'btn-gold', '挂载部署行动' + custBadge);
        confirmBtn.type = 'button';
        confirmBtn.disabled = ordinaryBlocked() || !afford(custCost);
        confirmBtn.onclick = () => {
          const spot = String(spotInput.value || bagPickerState.spot || '隐蔽角落').trim() || '隐蔽角落';
          const hidden = hideChk.checked;
          attachOperationToComposer({
            operation: { code: 'deploy_item', item_id: item.id, spot, hidden },
            label: '📷 部署「' + item.name + '」@ ' + spot + (hidden ? '（隐蔽）' : ''),
            defaultAction: '（' + (hidden ? '趁人不备，悄悄把' : '把') + item.name + '安装在' + (w.location || '此处') + '的「' + spot + '」）'
          });
        };
        const cancelBtn = node('button', 'btn-outline', '取消');
        cancelBtn.type = 'button';
        cancelBtn.onclick = () => { bagPickerState = null; renderWorld(true); };
        foot.append(confirmBtn, cancelBtn);
        box.append(foot);
      } else if (bagPickerState.mode === 'gift') {
        if (!castHere.length) return null;
        if (!castHere.includes(bagPickerState.recipient)) bagPickerState.recipient = castHere[0];
        const maxQty = Math.max(1, Number(item.quantity) || 1);
        const curQty = Math.max(1, Math.min(maxQty, Number(bagPickerState.qty) || 1));
        bagPickerState.qty = curQty;
        box.append(node('div', 'bag-picker-title', '选择在场接收人'));
        const chips = node('div', 'bag-picker-chips');
        for (const who of castHere) {
          const b = node('button', 'bag-picker-chip' + (bagPickerState.recipient === who ? ' is-active' : ''), who);
          b.type = 'button';
          b.onclick = () => {
            bagPickerState = { ...bagPickerState, recipient: who };
            renderWorld(true);
          };
          chips.append(b);
        }
        box.append(chips);
        if (maxQty > 1) {
          const qtyRow = node('div', 'bag-picker-qty');
          qtyRow.append(node('span', '', '赠予数量：'));
          const minusBtn = node('button', 'bag-picker-chip', '−');
          minusBtn.type = 'button';
          minusBtn.disabled = curQty <= 1;
          minusBtn.onclick = () => { bagPickerState = { ...bagPickerState, qty: Math.max(1, curQty - 1) }; renderWorld(true); };
          const plusBtn = node('button', 'bag-picker-chip', '+');
          plusBtn.type = 'button';
          plusBtn.disabled = curQty >= maxQty;
          plusBtn.onclick = () => { bagPickerState = { ...bagPickerState, qty: Math.min(maxQty, curQty + 1) }; renderWorld(true); };
          qtyRow.append(minusBtn, node('strong', '', curQty + ' / ' + maxQty), plusBtn);
          box.append(qtyRow);
        }
        const foot = node('div', 'bag-picker-foot');
        const confirmBtn = node('button', 'btn-gold', '挂载赠予行动' + custBadge);
        confirmBtn.type = 'button';
        confirmBtn.disabled = ordinaryBlocked() || !afford(custCost);
        confirmBtn.onclick = () => {
          const who = bagPickerState.recipient || castHere[0];
          const qty = bagPickerState.qty || 1;
          attachOperationToComposer({
            operation: { code: 'transfer_item', item_id: item.id, recipient: who, quantity: qty },
            label: '🎁 赠予「' + item.name + (qty > 1 ? ('×' + qty) : '') + '」→ ' + who,
            defaultAction: '（把' + (qty > 1 ? (qty + '份') : '') + item.name + '递给' + who + '）'
          });
        };
        const cancelBtn = node('button', 'btn-outline', '取消');
        cancelBtn.type = 'button';
        cancelBtn.onclick = () => { bagPickerState = null; renderWorld(true); };
        foot.append(confirmBtn, cancelBtn);
        box.append(foot);
      }
      return box;
    };

    const renderItemCard = item => {
      const pg = w.progression;
      const card = node('article', 'item-card');
      const top = node('div', 'item-card-top');
      top.append(node('span', 'item-card-name', item.name), node('span', 'item-qty-pill', '× ' + item.quantity));
      card.append(top);

      const tags = node('div', 'item-tags');
      const status = item.fields?.['当前状态'] || '持有';
      const eff = item.fields?.['系统效果'] || '';
      const staminaMatch = /^host_stamina:([1-9]\d*)$/.exec(eff);
      const canGift = item.giftable !== false && item.fields?.['可赠予'] !== '否';
      const usageMode = item.usage_mode || item.fields?.['使用模式']
        || (staminaMatch ? 'consumable_host' : (/^(?:deploy_device|device):(camera|audio|aroma)$/.test(eff) ? 'deployable_device' : (canGift ? 'gift' : 'reusable_tool')));

      tags.append(node('span', 'item-tag', status));
      if (USAGE_MODE_LABELS[usageMode]) {
        tags.append(node('span', 'item-tag' + (usageMode === 'deployable_device' ? ' is-device' : ''), USAGE_MODE_LABELS[usageMode]));
      } else if (item.fields?.['类型']) {
        tags.append(node('span', 'item-tag', item.fields['类型']));
      }
      if (item.remaining_turns !== null && item.remaining_turns !== undefined) {
        tags.append(node('span', 'item-tag is-timer', '剩余 ' + item.remaining_turns + ' 行动'));
      } else if (item.fields?.['剩余时效'] && !['无', ''].includes(item.fields['剩余时效'])) {
        tags.append(node('span', 'item-tag is-timer', '剩余 ' + item.fields['剩余时效']));
      }
      if (item.fields?.['使用对象'] && !['', '无', '未使用'].includes(item.fields['使用对象'])) {
        tags.append(node('span', 'item-tag', '对象：' + item.fields['使用对象']));
      }
      const effLabel = describeSystemEffect(eff);
      if (effLabel) {
        tags.append(node('span', 'item-tag is-effect', effLabel));
      }
      card.append(tags);

      if (item.fields?.['描述']) {
        card.append(node('p', 'item-desc', item.fields['描述']));
      }

      const owned = status === '仓库中' && ['', '无', '未使用', '徐志北'].includes(item.fields?.['使用对象'] || '');
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
        if (usageMode === 'consumable_target' || usageMode === 'reusable_tool') {
          const isOpen = bagPickerState?.itemId === item.id && bagPickerState?.mode === 'use';
          const btn = node('button', isOpen ? 'btn-gold' : 'btn-outline', usageMode === 'consumable_target' ? '使用 / 作用目标' : '在行动中使用');
          btn.type = 'button';
          btn.disabled = ordinaryBlocked() || !afford(custCost);
          btn.onclick = () => {
            haptic(8);
            bagPickerState = isOpen ? null : { mode: 'use', itemId: item.id, target: castHere[0] || '室内氛围' };
            renderWorld(true);
          };
          acts.append(btn);
        }
        if (usageMode === 'deployable_device') {
          const isOpen = bagPickerState?.itemId === item.id && bagPickerState?.mode === 'deploy';
          const btn = node('button', isOpen ? 'btn-gold' : 'btn-outline', '安装到当前地点');
          btn.type = 'button';
          btn.disabled = ordinaryBlocked() || !afford(custCost);
          btn.onclick = () => {
            haptic(8);
            bagPickerState = isOpen ? null : { mode: 'deploy', itemId: item.id, spot: DEPLOY_SPOT_PRESETS[0], hidden: true };
            renderWorld(true);
          };
          acts.append(btn);
        }
        if (castHere.length && canGift && usageMode !== 'deployable_device') {
          const isOpen = bagPickerState?.itemId === item.id && bagPickerState?.mode === 'gift';
          const giftBtn = node('button', isOpen ? 'btn-gold' : 'btn-outline', '赠予在场人物');
          giftBtn.type = 'button';
          giftBtn.disabled = ordinaryBlocked() || !afford(custCost);
          giftBtn.onclick = () => {
            haptic(8);
            bagPickerState = isOpen ? null : { mode: 'gift', itemId: item.id, recipient: castHere[0], qty: 1 };
            renderWorld(true);
          };
          acts.append(giftBtn);
        }
        if (acts.children.length) card.append(acts);
        const pickerEl = renderInlinePicker(item, usageMode);
        if (pickerEl) card.append(pickerEl);
      }
      return card;
    };

    const renderDeployedCard = dev => {
      const card = node('article', 'item-card deployed-device-card');
      const top = node('div', 'item-card-top');
      top.append(
        node('span', 'item-card-name', dev.name),
        node('span', 'item-tag is-device', (dev.location || '未知地点') + ' · ' + (dev.spot || '隐蔽点位'))
      );
      card.append(top);

      const tags = node('div', 'item-tags');
      tags.append(node('span', 'item-tag', dev.hidden !== false ? '隐蔽部署' : '明面摆放'));
      if (dev.installed_clock) tags.append(node('span', 'item-tag', '部署于 ' + dev.installed_clock));
      const effLabel = describeSystemEffect(dev.system_effect);
      if (effLabel) tags.append(node('span', 'item-tag is-effect', effLabel));
      card.append(tags);

      if (dev.desc) card.append(node('p', 'item-desc', dev.desc));

      const acts = node('div', 'item-card-actions');
      const inspectBtn = node('button', 'btn-gold', '📱 远程查看画面');
      inspectBtn.type = 'button';
      inspectBtn.disabled = ordinaryBlocked() || !afford(custCost);
      inspectBtn.onclick = () => {
        haptic(10);
        attachOperationToComposer({
          operation: { code: 'inspect_deployed', item_id: dev.id },
          label: '📱 远程查看「' + dev.name + '」（' + (dev.location || '') + '）',
          defaultAction: '（拿出手机打开加密监控端，远程查看留在「' + (dev.location || '') + ' · ' + (dev.spot || '隐蔽点位') + '」的' + dev.name + '实时画面）'
        });
      };
      acts.append(inspectBtn);

      const sameLoc = dev.location === w.location;
      const retBtn = node('button', 'btn-outline', '拆除回收');
      retBtn.type = 'button';
      retBtn.disabled = !sameLoc || ordinaryBlocked() || !afford(custCost);
      if (!sameLoc) retBtn.title = '需先前往 ' + dev.location + ' 才可回收';
      retBtn.onclick = () => {
        haptic(10);
        attachOperationToComposer({
          operation: { code: 'retrieve_item', item_id: dev.id },
          label: '🔧 回收「' + dev.name + '」',
          defaultAction: '（趁无人注意，从「' + (dev.spot || '隐蔽点位') + '」取回' + dev.name + '收进随身口袋）'
        });
      };
      acts.append(retBtn);
      if (!sameLoc) {
        acts.append(node('span', 'shop-reason-hint', '回收需先前往 ' + dev.location));
      }
      card.append(acts);
      return card;
    };

    const ksMeta = w.keepsake_meta || {};
    const ksKinds = ksMeta.kinds || { panties: '贴身内裤', stockings: '丝袜长袜', bra: '贴身内衣', nightwear: '睡裙家居', accessory: '私密贴物' };
    const ksMethods = ksMeta.methods || { stolen: '暗中偷藏', taken_intimate: '亲密留存', gifted: '亲手交出' };
    const ksConds = ksMeta.conditions || { fresh_warm: '尚带体温余香', stained_damp: '沾有微潮水痕', faded: '余香渐淡' };

    const renderKeepsakeCard = ks => {
      const card = node('article', 'item-card keepsake-card');
      const top = node('div', 'item-card-top');
      top.append(
        node('span', 'item-card-name', ks.owner + ' · ' + ks.name),
        node('span', 'keepsake-owner-pill', ksKinds[ks.kind] || '贴身珍藏')
      );
      card.append(top);

      const tags = node('div', 'item-tags');
      tags.append(
        node('span', 'item-tag', ksMethods[ks.method] || '私密留存'),
        node('span', 'item-tag is-effect', ksConds[ks.condition] || '尚带余香'),
        node('span', 'item-tag' + (ks.owner_aware ? ' is-timer' : ''), ks.owner_aware ? '失主已知晓' : '失主未察觉')
      );
      if (ks.clock) tags.append(node('span', 'item-tag', ks.clock));
      card.append(tags);

      if (ks.desc) card.append(node('p', 'item-desc', ks.desc));

      const ownerHere = castHere.includes(ks.owner);
      const ownerLoc = w.presence?.[ks.owner]?.location || '';
      const homeOk = (['沈知韫', '徐念薇'].includes(ks.owner) && w.location === '徐家主宅')
        || (ks.owner === '苏婉青' && w.location === '市中心顶层公寓');
      const canReturn = ownerHere || w.location === ks.location || w.location === ownerLoc || homeOk;
      const canPay = !ordinaryBlocked() && afford(custCost);

      const acts = node('div', 'item-card-actions keepsake-actions');

      const sniffBtn = node('button', 'btn-outline', '🫧 私下嗅闻/把玩');
      sniffBtn.type = 'button';
      sniffBtn.disabled = !canPay;
      sniffBtn.onclick = () => {
        haptic(10);
        attachOperationToComposer({
          operation: { code: 'keepsake_action', keepsake_id: ks.id, action_type: 'sniff_play' },
          label: '🫧 嗅闻把玩「' + ks.owner + '的' + ks.name + '」',
          defaultAction: '（取出暗中收存的「' + ks.owner + '的' + ks.name + '」，指腹摩挲着轻薄布料凑近轻嗅）'
        });
      };
      acts.append(sniffBtn);

      const confBtn = node('button', ownerHere ? 'btn-gold' : 'btn-outline', '👀 当面出示试探');
      confBtn.type = 'button';
      confBtn.disabled = !canPay || !ownerHere;
      if (!ownerHere) confBtn.title = '需与 ' + ks.owner + ' 身处同一场景';
      confBtn.onclick = () => {
        haptic(10);
        attachOperationToComposer({
          operation: { code: 'keepsake_action', keepsake_id: ks.id, action_type: 'confront' },
          label: '👀 当面出示「' + ks.owner + '的' + ks.name + '」',
          defaultAction: '（指尖勾出暗中藏着的那件「' + ks.name + '」，在' + ks.owner + '眼前慢慢摊开）'
        });
      };
      acts.append(confBtn);

      const useIntBtn = node('button', 'btn-outline', '🎭 亲密穿戴复用');
      useIntBtn.type = 'button';
      useIntBtn.disabled = !canPay || !ownerHere;
      if (!ownerHere) useIntBtn.title = '需与 ' + ks.owner + ' 身处同一场景';
      useIntBtn.onclick = () => {
        haptic(10);
        attachOperationToComposer({
          operation: { code: 'keepsake_action', keepsake_id: ks.id, action_type: 'use_intimate' },
          label: '🎭 亲密复用「' + ks.owner + '的' + ks.name + '」',
          defaultAction: '（拿出收存的「' + ks.name + '」，贴着' + ks.owner + '低声让她重新换上或在亲密间复用）'
        });
      };
      acts.append(useIntBtn);

      const retKsBtn = node('button', 'btn-outline', '🤫 悄悄放回原处');
      retKsBtn.type = 'button';
      retKsBtn.disabled = !canPay || !canReturn;
      if (!canReturn) retKsBtn.title = '需回到 ' + ks.owner + ' 居所或原藏匿地点';
      retKsBtn.onclick = () => {
        haptic(10);
        attachOperationToComposer({
          operation: { code: 'keepsake_action', keepsake_id: ks.id, action_type: 'return_secret' },
          label: '🤫 悄悄放回「' + ks.owner + '的' + ks.name + '」',
          defaultAction: '（趁无人留意，把这件「' + ks.name + '」悄悄放回' + ks.owner + '的衣橱或原处）'
        });
      };
      acts.append(retKsBtn);

      card.append(acts);
      return card;
    };

    if (subKey === 'held') {
      if (heldItems.length) {
        const grid = node('section', 'item-grid');
        for (const item of heldItems) grid.append(renderItemCard(item));
        pane.append(grid);
      } else {
        const emptyHeld = node('section', 'empty-card');
        emptyHeld.append(icon('bag'), node('p', '', '当前没有随身道具，可在系统商城兑换或完成委托获取'));
        pane.append(emptyHeld);
      }
      const shopCta = node('button', 'bag-shop-cta');
      shopCta.type = 'button';
      const ctaLeft = node('span', 'bag-shop-cta-left');
      ctaLeft.append(icon('shop', 'chip-svg'), node('span', '', '前往系统商城兑换 / 定制进货 →'));
      shopCta.append(ctaLeft, node('small', '', '现有 ' + hostPoints + ' 积分 · 0 体力'));
      shopCta.onclick = () => openHub('shop');
      pane.append(shopCta);
    } else if (subKey === 'keepsakes') {
      if (keepsakes.length) {
        const kGrid = node('section', 'item-grid');
        for (const ks of keepsakes) kGrid.append(renderKeepsakeCard(ks));
        pane.append(kGrid);
      } else {
        const emptyKs = node('section', 'empty-card');
        emptyKs.append(icon('bag'), node('p', '', '尚未收录私密珍藏，在剧情中暗中留存或由对方交出的贴身物件会收录于此'));
        pane.append(emptyKs);
      }
    } else if (subKey === 'deployed') {
      if (deployedItems.length) {
        const dGrid = node('section', 'item-grid');
        for (const dev of deployedItems) dGrid.append(renderDeployedCard(dev));
        pane.append(dGrid);
      } else {
        const emptyDep = node('section', 'empty-card');
        emptyDep.append(icon('bag'), node('p', '', '尚未在任何场所部署隐秘装置'));
        pane.append(emptyDep);
      }
    } else if (subKey === 'gifted') {
      if (giftedItems.length) {
        const gGrid = node('section', 'item-grid');
        for (const item of giftedItems) gGrid.append(renderItemCard(item));
        pane.append(gGrid);
      } else {
        const emptyGift = node('section', 'empty-card');
        emptyGift.append(icon('gift'), node('p', '', '尚未赠予过纪念物品'));
        pane.append(emptyGift);
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
    const hostBiz = shopCatalog?.host_biz ?? (panels['系统宿主']?.stats?.['商业嗅觉']?.num ?? 0);
    const maxAff = shopCatalog?.max_affection ?? Math.max(0, ...PEOPLE.map(n => panels[n]?.stats?.['好感']?.num ?? 0));
    const points = shopCatalog && shopCatalog.revision === snapshot?.revision ? shopCatalog.points : hostPoints;
    const charmDisc = Number(shopCatalog?.charm_discount ?? w?.host_charm_tier?.shop_discount ?? 1);
    const discPct = Math.round(charmDisc * 100);
    const discLabel = charmDisc < 1 ? (' · 魅力优待 ' + (discPct % 10 === 0 ? (discPct / 10) : (discPct / 10).toFixed(1)) + '折') : '';

    // 1. Balance Hero Card
    const balCard = node('section', 'shop-balance-card');
    const balMain = node('div', 'shop-balance-main');
    const balLabel = node('div', 'shop-balance-label');
    balLabel.append(icon('coin', 'chip-svg'), node('span', '', '当前可用系统积分'));
    balMain.append(
      balLabel,
      node('div', 'shop-balance-num', String(points)),
      node('div', 'shop-balance-sub', '商业嗅觉 ' + hostBiz + ' · 最高好感 ' + maxAff + discLabel + ' · 0 体力即时入囊')
    );
    const bagBtn = node('button', 'btn-outline', '查看行囊');
    bagBtn.type = 'button';
    bagBtn.onclick = () => openHub('bag');
    balCard.append(balMain, bagBtn);
    pane.append(balCard);

    // 2. In-Story 【商城定制】 Guide Card (Collapsible, replaces removed stateless AI inquiry window)
    const iqCard = node('details', 'hub-fold shop-inquiry-card');
    const iqHead = node('summary', 'hub-fold-summary');
    const dynCount = shopCatalog?.dynamic_count ?? (shopCatalog?.items || []).filter(it => it.source === 'ai_restock').length;
    const dynLimit = shopCatalog?.dynamic_limit ?? 30;
    const unlockedGradeLabel = shopCatalog?.unlocked_grade_label || 'T1 · 寻常小物';
    const iqTitleWrap = node('div', 'hub-fold-title');
    iqTitleWrap.append(
      node('strong', '', '剧情内定制进货 · 【商城定制】'),
      node('span', 'muted', '已解锁 ' + unlockedGradeLabel + ' · 点此展开或直达输入')
    );
    const iqRight = node('span', 'fold-right');
    iqRight.append(node('span', 'item-tag is-effect', '动态 ' + dynCount + '/' + dynLimit), node('span', 'fold-caret', '▾'));
    iqHead.append(iqTitleWrap, iqRight);
    iqCard.append(iqHead);

    const iqBody = node('div', 'hub-fold-body');
    const jumpRow = node('div', 'shop-inquiry-form');
    const jumpBtn = node('button', 'btn-gold', '✦ 去剧情中输入【商城定制】');
    jumpBtn.type = 'button';
    jumpBtn.onclick = () => {
      haptic(10);
      $('worldDialog')?.close();
      if (isMobileViewport()) {
        openComposerSheet({ focus: true, insertBracket: '【商城定制】' });
      } else {
        insertInputBracket('【商城定制】');
      }
    };
    jumpRow.append(jumpBtn);
    iqBody.append(
      node('p', 'shop-inquiry-sub', '在剧情输入框点「✦ 商城定制」或写【商城定制】即可自由定制目录外道具。高阶道具按 T1～T4 分阶定价并由「商业嗅觉 / 最高堕落 / 魅力」自动锁门，超阶物品可提前上架作为后期目标。'),
      jumpRow
    );
    iqCard.append(iqBody);
    pane.append(iqCard);

    // 3. Loading / Error / Categorized Catalog Shelves
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
      const bucketOf = it => it.source === 'ai_restock'
        ? 'ai_restock'
        : (['sensual', 'covert', 'daily'].includes(it.category) ? it.category : 'daily');

      const presentCats = SHOP_CATEGORY_ORDER
        .map(k => ({
          key: k,
          label: (shopCatalog.categories && shopCatalog.categories[k]?.label) || SHOP_CATEGORY_LABELS[k] || k,
          items: shopCatalog.items.filter(it => bucketOf(it) === k)
        }))
        .filter(g => g.items.length > 0);

      if (activeShopCat !== 'all' && !presentCats.some(g => g.key === activeShopCat)) {
        activeShopCat = 'all';
      }

      if (presentCats.length > 1) {
        const catBar = node('div', 'sub-pill-bar');
        catBar.setAttribute('role', 'tablist');
        const allBtn = node('button', 'sub-pill-btn' + (activeShopCat === 'all' ? ' is-active' : ''));
        allBtn.type = 'button';
        allBtn.setAttribute('aria-selected', String(activeShopCat === 'all'));
        allBtn.append(node('span', '', '全部'), node('em', 'sub-pill-cnt', String(shopCatalog.items.length)));
        allBtn.onclick = () => { haptic(8); activeShopCat = 'all'; renderWorld(true); };
        catBar.append(allBtn);
        for (const g of presentCats) {
          const shortLabel = g.label.replace(/（.*?）/g, '').replace(/\s*·.*$/, '');
          const b = node('button', 'sub-pill-btn' + (activeShopCat === g.key ? ' is-active' : ''));
          b.type = 'button';
          b.setAttribute('aria-selected', String(activeShopCat === g.key));
          b.append(node('span', '', shortLabel), node('em', 'sub-pill-cnt', String(g.items.length)));
          b.onclick = () => { haptic(8); activeShopCat = g.key; renderWorld(true); };
          catBar.append(b);
        }
        pane.append(catBar);
      }

      const visibleCats = activeShopCat === 'all' ? presentCats : presentCats.filter(g => g.key === activeShopCat);
      for (const { key: catKey, label: catTitle, items: catItems } of visibleCats) {
        const group = node('section', 'shop-tier-group');
        const tHead = node('div', 'shop-tier-head');
        tHead.append(
          node('h3', '', catTitle),
          node('span', '', catItems.length + ' 件')
        );
        group.append(tHead);

        for (const item of catItems) {
          const bought = redeemedMap[item.id] ?? item.redeemed_count ?? 0;
          const cap = item.max_per_save;
          const soldOut = cap !== null && cap !== undefined && bought >= cap;
          const unlocked = item.unlocked !== false;
          const basePrice = Number(item.base_price ?? item.price);
          const effPrice = Number(item.effective_price ?? item.price);
          const hasDisc = effPrice < basePrice;
          const enough = points >= effPrice;
          const canBuy = !soldOut && unlocked && enough && canTransactDeterministic();
          const packQty = Number(item.pack_qty || 1);

          const card = node('article', 'shop-item-card' + (soldOut ? ' is-soldout' : '') + (!unlocked ? ' is-locked' : ''));
          const top = node('div', 'shop-item-top');
          const nameWrap = node('span', 'shop-item-name', item.name + (packQty > 1 ? (' ×' + packQty) : ''));
          const pricePill = node('span', 'shop-price-pill' + (hasDisc ? ' is-discounted' : ''));
          pricePill.append(icon('coin', 'chip-svg'));
          if (hasDisc) pricePill.append(node('s', 'shop-price-base', String(basePrice)));
          pricePill.append(node('span', '', effPrice + ' 积分'));
          top.append(nameWrap, pricePill);
          card.append(top);

          const tags = node('div', 'item-tags');
          if (item.source === 'ai_restock') {
            const gCode = String(item.grade || 'T1').toLowerCase();
            const gLabel = item.grade_label || (item.grade ? (item.grade + ' 定制') : '剧情定制');
            tags.append(node('span', 'item-tag is-grade-' + gCode, gLabel));
          }
          if (USAGE_MODE_LABELS[item.usage_mode]) {
            tags.append(node('span', 'item-tag' + (item.usage_mode === 'deployable_device' ? ' is-device' : ''), USAGE_MODE_LABELS[item.usage_mode]));
          } else {
            tags.append(node('span', 'item-tag', item.type || '道具'));
          }
          const effLabel = describeSystemEffect(item.system_effect);
          if (effLabel) tags.append(node('span', 'item-tag is-effect', effLabel));
          if (item.giftable && item.usage_mode !== 'gift') tags.append(node('span', 'item-tag', '可赠予'));
          if (cap !== null && cap !== undefined) {
            tags.append(node('span', 'item-tag' + (soldOut ? ' is-soldout' : ''), soldOut ? ('已售罄 ' + bought + '/' + cap) : ('限兑 ' + bought + '/' + cap)));
          }
          if (!unlocked && item.unlock_hint) {
            tags.append(node('span', 'item-tag is-locked', '🔒 ' + item.unlock_hint));
          }
          card.append(tags);

          if (item.desc) card.append(node('p', 'item-desc', item.desc));

          const footer = node('div', 'shop-item-footer');
          const buyLabel = soldOut ? '已售罄'
            : !unlocked ? '未解锁'
            : shopBusy ? '兑换中…'
            : ('兑换 · ' + effPrice + ' 积分');
          const buyBtn = node('button', 'btn-gold', buyLabel);
          buyBtn.type = 'button';
          buyBtn.disabled = !canBuy;
          buyBtn.onclick = () => void redeemShopItem(item);
          footer.append(buyBtn);

          if (item.source === 'ai_restock') {
            const delBtn = node('button', 'btn-outline is-tiny', '下架');
            delBtn.type = 'button';
            delBtn.disabled = !canTransactDeterministic();
            delBtn.onclick = () => void deleteDynamicShopItem(item);
            footer.append(delBtn);
          }

          let reason = '';
          if (soldOut) reason = '已达本档限购上限';
          else if (!unlocked) reason = item.unlock_reason || item.unlock_hint || '尚未满足解锁门槛';
          else if (!enough) reason = '还差 ' + (effPrice - points) + ' 积分';
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

    // 4. Recent Redemptions Ledger (persisted in 【商城与回响状态】)
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
    const subKey = ['display', 'voice', 'ambient', 'bridge'].includes(activeSystemSubTab) ? activeSystemSubTab : 'display';

    const subBar = node('div', 'sub-pill-bar');
    subBar.setAttribute('role', 'tablist');
    const sysTabs = [
      ['display', '剧场显示'],
      ['voice', '语音与密钥'],
      ['ambient', '背景音景'],
      ['bridge', '连接维护']
    ];
    for (const [k, label] of sysTabs) {
      const btn = node('button', 'sub-pill-btn' + (subKey === k ? ' is-active' : ''));
      btn.type = 'button';
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', String(subKey === k));
      btn.append(node('span', '', label));
      if (k === 'bridge') {
        const d = node('i', 'sub-pill-dot' + (snapshot?.bridge_connected ? ' is-online' : ''));
        btn.append(d);
      }
      btn.onclick = () => {
        haptic(8);
        activeSystemSubTab = k;
        renderWorld(true);
      };
      subBar.append(btn);
    }
    pane.append(subBar);

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
    const curDirectorPacing = ['slow', 'standard', 'frequent'].includes(snapshot?.preferences?.director_pacing)
      ? snapshot.preferences.director_pacing
      : 'standard';
    const curAnchorHistoryMode = snapshot?.preferences?.anchor_history_mode === 'full' ? 'full' : 'balanced';

    // Sub-tab 1: Display, Narrative & Haptics
    if (subKey === 'display') {
      const uiGroup = node('section', 'pref-group');
      uiGroup.append(node('h3', '', '核心阅读与演播'));
      uiGroup.append(
        mkSwitchRow('视觉主题', '暗夜黑金剧场 / 昼间暖纸护眼', [['noir', '黑金'], ['ivory', '暖纸']], prefs.theme, v => { prefs.theme = v; savePrefs(); }),
        mkSwitchRow('正文字号', '适应移动端阅读舒适度', [['normal', '标准'], ['large', '大字']], prefs.font, v => { prefs.font = v; savePrefs(); }),
        mkSwitchRow('演播呈现方式', '沉浸幕布待结算完成揭幕，杜绝闪屏；即时流式边写边看', [['curtain', '沉浸幕布'], ['stream', '即时流式']], prefs.displayMode, v => {
          prefs.displayMode = v;
          savePrefs();
          signature = '';
          render();
          controls();
        }),
        mkSwitchRow('主角戏份风格', '忠实演绎允许简短主角发言与具身反应；仅动作感官禁主角台词', [['faithful', '忠实演绎'], ['silent', '仅动作感官']], curProtagStyle, async v => {
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
        mkSwitchRow('女主意外节奏', '调节女主突发意外与推进契机的保底频次（慢热6轮 / 标准4轮 / 密集3轮）', [['slow', '慢热'], ['standard', '标准'], ['frequent', '密集']], curDirectorPacing, async v => {
          if (backendPrefBusy) return;
          backendPrefBusy = true;
          try {
            const res = await api('preferences', { director_pacing: v });
            if (snapshot && res?.preferences) snapshot.preferences = res.preferences;
            const labels = { slow: '慢热写实', standard: '标准节奏', frequent: '密集邂逅' };
            toast(`女主意外节奏已设为「${labels[v] || v}」（下幕生效）`);
            renderWorld(true);
          } catch (err) {
            toast('保存偏好失败：' + (err?.message || err));
          } finally {
            backendPrefBusy = false;
          }
        }),
        mkSwitchRow('开窗回溯模式', '均衡模式保留近2幕完整原文+三轨记忆（省量连贯）；完整模式保留近6幕全量原文', [['balanced', '均衡（推荐）'], ['full', '完整6幕']], curAnchorHistoryMode, async v => {
          if (backendPrefBusy) return;
          backendPrefBusy = true;
          try {
            const res = await api('preferences', { anchor_history_mode: v });
            if (snapshot && res?.preferences) snapshot.preferences = res.preferences;
            toast(v === 'balanced' ? '开窗回溯已设为「均衡模式」（下次开窗生效）' : '开窗回溯已设为「完整6幕」（下次开窗生效）');
            renderWorld(true);
          } catch (err) {
            toast('保存偏好失败：' + (err?.message || err));
          } finally {
            backendPrefBusy = false;
          }
        }),
        mkSwitchRow('落笔防误触', '原位称重落印与 1.8s 收墨撤回，无全屏弹窗', [['inline', '原位轻确认'], ['critical', '仅关键动作'], ['off', '直出']], prefs.confirmMode, v => { prefs.confirmMode = v; savePrefs(); disarmChoice(); })
      );
      pane.append(uiGroup);

      // Custom System-Level Rules (Primary Zone 0 + Secondary Stage 2, unlimited length)
      const bp = snapshot?.preferences || {};
      const ruleConfigs = {
        primary: {
          tabLabel: '主模型 · 前景演播',
          enKey: 'custom_rules_enabled',
          posKey: 'custom_rules_position',
          txtKey: 'custom_rules_text',
          enabled: !!bp.custom_rules_enabled,
          position: bp.custom_rules_position === 'prepend' ? 'prepend' : 'append',
          savedText: typeof bp.custom_rules_text === 'string' ? bp.custom_rules_text : '',
          posTitle: 'Zone 0 注入位置',
          posSub: '置底紧贴场景人设前权重高且保缓存；置顶置于协议最前方',
          placeholder: '填写主模型（前景演播 Zone 0）的自定义系统级规则，不限字数。\n例如：\n- 对话节奏偏电影质感，减少解释性内心独白\n- 描写更侧重环境声响、光影与肢体微反应',
          hint: '仅编译注入主模型前景演播（Zone 0），不污染后台数值结算；内容不变时 100% 命中 KV 前缀缓存，重置存档与同步 GitHub 均自动保留。',
        },
        settlement: {
          tabLabel: '副模型 · 后台结算',
          enKey: 'settlement_custom_rules_enabled',
          posKey: 'settlement_custom_rules_position',
          txtKey: 'settlement_custom_rules_text',
          enabled: !!bp.settlement_custom_rules_enabled,
          position: bp.settlement_custom_rules_position === 'prepend' ? 'prepend' : 'append',
          savedText: typeof bp.settlement_custom_rules_text === 'string' ? bp.settlement_custom_rules_text : '',
          posTitle: 'Stage 2 注入位置',
          posSub: '置底紧接事件判准后；置顶置于结算指令最前方',
          placeholder: '填写副模型（后台结构化结算 Stage 2 system_prompt）的自定义系统级规则，不限字数。\n例如：\n- 当正文出现明显口是心非时，在 quality_flags 额外留意记录\n- 严禁改变裸 JSON 结构与合法标签白名单',
          hint: '仅编译注入副模型后台结算（Stage 2 静态 system_prompt），与主模型互不干扰；跨回合静态保前缀缓存，重置存档与同步 GitHub 均自动保留。',
        },
      };
      const pLen = ruleConfigs.primary.savedText.trim().length;
      const sLen = ruleConfigs.settlement.savedText.trim().length;
      const summaryParts = [];
      if (ruleConfigs.primary.enabled) summaryParts.push('主模型已开' + (pLen ? `(${pLen}字)` : '(空)'));
      if (ruleConfigs.settlement.enabled) summaryParts.push('副模型已开' + (sLen ? `(${sLen}字)` : '(空)'));
      const ruleFold = node('details', 'hub-fold pref-fold custom-rule-fold');
      ruleFold.open = !!customRuleFoldOpen;
      ruleFold.ontoggle = () => { customRuleFoldOpen = !!ruleFold.open; };
      const rSum = node('summary', 'hub-fold-summary');
      const rTitle = node('div', 'hub-fold-title');
      rTitle.append(
        node('strong', '', '自定义系统级 Rule（主 / 副模型）'),
        node('span', 'muted', summaryParts.length ? summaryParts.join(' · ') : '未启用（不限字数，本地持久保存）')
      );
      rSum.append(rTitle, node('span', 'fold-caret', '▾'));
      ruleFold.append(rSum);

      const rBody = node('div', 'hub-fold-body');
      const tabBar = node('div', 'custom-rule-tabs');
      tabBar.setAttribute('role', 'tablist');
      for (const tabKey of ['primary', 'settlement']) {
        const cfg = ruleConfigs[tabKey];
        const tb = node('button', 'custom-rule-tab', cfg.tabLabel + (cfg.enabled ? ' · 开' : ''));
        tb.type = 'button';
        tb.setAttribute('role', 'tab');
        tb.setAttribute('aria-selected', String(customRuleTab === tabKey));
        tb.onclick = () => {
          if (customRuleTab === tabKey) return;
          haptic(6);
          customRuleTab = tabKey;
          customRuleFoldOpen = true;
          renderWorld(true);
        };
        tabBar.append(tb);
      }
      rBody.append(tabBar);

      const activeKey = customRuleTab === 'settlement' ? 'settlement' : 'primary';
      const activeCfg = ruleConfigs[activeKey];
      const existingDraft = customRuleDrafts[activeKey];
      const curDraftText = (existingDraft && existingDraft.dirty) ? existingDraft.text : activeCfg.savedText;

      const saveRulePatch = async (patch, successMsg, resetDraft = false) => {
        if (backendPrefBusy) return;
        backendPrefBusy = true;
        try {
          const res = await api('preferences', patch);
          if (snapshot && res?.preferences) snapshot.preferences = res.preferences;
          if (resetDraft) customRuleDrafts[activeKey] = null;
          toast(successMsg);
          customRuleFoldOpen = true;
          renderWorld(true);
        } catch (err) {
          toast('保存规则失败：' + (err?.message || err));
        } finally {
          backendPrefBusy = false;
        }
      };

      rBody.append(
        mkSwitchRow(
          activeKey === 'primary' ? '启用主模型自定义 Rule' : '启用副模型自定义 Rule',
          activeKey === 'primary' ? '开启后注入前景演播 Zone 0（下幕生效）' : '开启后注入后台结算 Stage 2 system_prompt（下幕生效）',
          [[true, '开启'], [false, '关闭']],
          activeCfg.enabled,
          v => {
            const payload = { [activeCfg.enKey]: !!v };
            if (existingDraft && existingDraft.dirty) payload[activeCfg.txtKey] = existingDraft.text;
            void saveRulePatch(
              payload,
              (activeKey === 'primary' ? '主模型' : '副模型') + '自定义 Rule 已' + (v ? '开启（下幕生效）' : '关闭（下幕生效）'),
              !!(existingDraft && existingDraft.dirty)
            );
          }
        ),
        mkSwitchRow(
          activeCfg.posTitle,
          activeCfg.posSub,
          [['append', '置底（推荐）'], ['prepend', '置顶']],
          activeCfg.position,
          v => {
            void saveRulePatch(
              { [activeCfg.posKey]: v },
              (activeKey === 'primary' ? '主模型' : '副模型') + '注入位置已设为' + (v === 'prepend' ? '置顶' : '置底') + '（下幕生效）'
            );
          }
        )
      );

      const editorWrap = node('div', 'custom-rule-editor');
      const ta = node('textarea', 'custom-rule-textarea');
      ta.rows = 7;
      ta.value = curDraftText;
      ta.placeholder = activeCfg.placeholder;
      ta.setAttribute('aria-label', activeCfg.tabLabel + ' 自定义系统级规则');

      const metaRow = node('div', 'custom-rule-meta');
      const countSpan = node('span', '', `当前 ${curDraftText.length} 字 · 不限字数`);
      const dirtySpan = node('span', 'custom-rule-dirty', curDraftText !== activeCfg.savedText ? '有未保存修改' : '');
      metaRow.append(countSpan, dirtySpan);

      ta.oninput = () => {
        const val = ta.value;
        const isDirty = val !== activeCfg.savedText;
        customRuleDrafts[activeKey] = isDirty ? { text: val, dirty: true } : null;
        countSpan.textContent = `当前 ${val.length} 字 · 不限字数`;
        dirtySpan.textContent = isDirty ? '有未保存修改' : '';
      };

      const actRow = node('div', 'custom-rule-actions');
      const clearBtn = node('button', 'btn-outline compact-btn', '清空');
      clearBtn.type = 'button';
      clearBtn.onclick = () => {
        haptic(8);
        ta.value = '';
        void saveRulePatch(
          { [activeCfg.txtKey]: '' },
          (activeKey === 'primary' ? '主模型' : '副模型') + '自定义 Rule 已清空',
          true
        );
      };
      const saveBtn = node('button', 'btn-gold compact-btn', '保存规则');
      saveBtn.type = 'button';
      saveBtn.onclick = () => {
        haptic(10);
        const val = ta.value;
        const label = activeKey === 'primary' ? '主模型' : '副模型';
        const suffix = activeCfg.enabled || !val.trim()
          ? '（下幕生效，前缀缓存自动刷新）'
          : '（请开启上方开关使其生效）';
        void saveRulePatch({ [activeCfg.txtKey]: val }, `${label}自定义 Rule 已保存${suffix}`, true);
      };
      actRow.append(clearBtn, saveBtn);

      editorWrap.append(ta, metaRow, actRow, node('p', 'custom-rule-hint', activeCfg.hint));
      rBody.append(editorWrap);
      ruleFold.append(rBody);
      pane.append(ruleFold);

      const visualFold = node('details', 'hub-fold pref-fold');
      const vSum = node('summary', 'hub-fold-summary');
      const vTitle = node('div', 'hub-fold-title');
      const onFlags = [
        prefs.cinemaPlates ? '插页' : '',
        prefs.backdrop ? '光影' : '',
        prefs.readingDof ? '景深' : '',
        prefs.haptics ? '微振' : ''
      ].filter(Boolean);
      vTitle.append(
        node('strong', '', '细节视觉与触感'),
        node('span', 'muted', onFlags.length ? ('已开启：' + onFlags.join(' · ')) : '已全部静默')
      );
      vSum.append(vTitle, node('span', 'fold-caret', '▾'));
      visualFold.append(vSum);
      const vBody = node('div', 'hub-fold-body');
      vBody.append(
        mkSwitchRow('电影插页', '切场空镜与角色入场横幅，零额外消耗', [[true, '开启'], [false, '纯文字']], prefs.cinemaPlates, v => { prefs.cinemaPlates = v; savePrefs(); signature = ''; render(); }),
        mkSwitchRow('场景氛围光影', '随当前地点空镜与情绪变化柔和染光', [[true, '开启'], [false, '静默']], prefs.backdrop, v => { prefs.backdrop = v; savePrefs(); }),
        mkSwitchRow('焦点景深阅读', '最新一段全清晰，上文轻柔退远', [[true, '开启'], [false, '关闭']], prefs.readingDof, v => { prefs.readingDof = v; savePrefs(); applyReadingFocus(); }),
        mkSwitchRow('触感微振', '点按剧情与抉择时轻振反馈', [[true, '开启'], [false, '关闭']], prefs.haptics, v => { prefs.haptics = v; savePrefs(); })
      );
      visualFold.append(vBody);
      pane.append(visualFold);
      return pane;
    }

    // Sub-tab 2: Voice Quality, Multi-channel Routing & Fish API Key
    if (subKey === 'voice') {
      const voiceGroup = node('section', 'pref-group');
      const vHeader = node('div', 'pref-group-head');
      const voiceStudioBtn = node('a', 'btn-outline is-tiny', '打开声学工坊 ↗');
      voiceStudioBtn.href = '/admin';
      voiceStudioBtn.target = '_blank';
      voiceStudioBtn.rel = 'noopener';
      vHeader.append(node('h3', '', '语音品质与声道路由'), voiceStudioBtn);
      voiceGroup.append(vHeader);

      const tierRow = node('div', 'pref-row');
      const tierLbl = node('div', 'pref-row-label');
      const tierDesc = node('span', '', '三女主随分档切换模型；旁白、动作与主角恒走免费档（$0）。');
      tierLbl.append(node('strong', '', '语音品质分档'), tierDesc);
      const tierSwitch = node('div', 'seg-switch');
      const tierDefs = [
        ['free', '免费 ($0)'],
        ['pro', '稳定付费'],
        ['drama', 'Drama3']
      ];
      const tierButtons = new Map();
      const markTierActive = activeTier => {
        for (const [tid, btn] of tierButtons) {
          btn.setAttribute('aria-pressed', String(tid === activeTier));
        }
      };

      const protagRow = node('div', 'pref-row');
      const protagLbl = node('div', 'pref-row-label');
      const protagDesc = node('span', '', '开启后朗读 AI 正文中的 [D:徐志北]（恒走免费档，需绑定男声音色）。');
      protagLbl.append(node('strong', '', '主角配音（徐志北）'), protagDesc);
      const protagSwitch = node('div', 'seg-switch');
      const protagButtons = new Map();

      const actModeRow = node('div', 'pref-row');
      const actModeLbl = node('div', 'pref-row-label');
      const actModeDesc = node('span', '', '区分旁白 [N] 与舞台动作 [A]：「独立动作」默认继承旁白并微调韵律。');
      actModeLbl.append(node('strong', '', '动作声线模式'), actModeDesc);
      const actModeSwitch = node('div', 'seg-switch');
      const actModeButtons = new Map();

      const actScopeRow = node('div', 'pref-row');
      const actScopeLbl = node('div', 'pref-row-label');
      const actScopeDesc = node('span', '', '控制动作配音覆盖范围：默认朗读全部 [A:*]，也可仅朗读三女主。');
      actScopeLbl.append(node('strong', '', '动作配音范围'), actScopeDesc);
      const actScopeSwitch = node('div', 'seg-switch');
      const actScopeButtons = new Map();

      const markRoutingUI = cfg => {
        const s = cfg?.__settings__ || {};
        const pOn = s.protagonist_voice_enabled === true;
        const aMode = s.action_voice_mode || 'follow_narrator';
        const aScope = s.action_voice_scope || 'all';
        for (const [val, btn] of protagButtons) btn.setAttribute('aria-pressed', String(val === pOn));
        for (const [val, btn] of actModeButtons) btn.setAttribute('aria-pressed', String(val === aMode));
        for (const [val, btn] of actScopeButtons) btn.setAttribute('aria-pressed', String(val === aScope));
        const hasProtagVoice = hasUsableVoiceSlot(cfg?.['徐志北']);
        const hints = [];
        if (curProtagStyle === 'silent') hints.push('当前为「仅动作感官」模式，切回「忠实演绎」后方有主角台词');
        if (pOn && !hasProtagVoice) hints.push('尚未在声学工坊为徐志北绑定音色');
        if (!hints.length) {
          hints.push(hasProtagVoice ? '已绑定徐志北音色；开启后朗读 AI [D:徐志北]（恒免费）' : '开启后朗读 AI [D:徐志北]；可在声学工坊选定男声音色');
        }
        protagDesc.textContent = hints.join('；');
        actScopeRow.style.opacity = aMode === 'muted' ? '0.55' : '';
      };

      const applyRoutingPatch = async (patch, okMsg) => {
        try {
          const res = await VoiceClient.setVoiceRouting(patch);
          invalidateVoiceConfig();
          if (res && res.config) voiceConfigCache = res.config;
          segmentDomCache.clear();
          signature = '';
          render();
          markRoutingUI(voiceConfigCache);
          void loadVoiceConfig().catch(() => null);
          toast(okMsg || res?.msg || '语音路由已更新');
        } catch (err) {
          toast('语音路由保存失败：' + (err?.message || err));
        }
      };

      for (const [val, label] of [[true, '开启'], [false, '关闭']]) {
        const b = node('button', '', label);
        b.type = 'button';
        b.setAttribute('aria-pressed', 'false');
        b.onclick = () => { haptic(8); void applyRoutingPatch({ protagonist_voice_enabled: val }, val ? '已开启主角配音（徐志北）' : '已关闭主角配音'); };
        protagButtons.set(val, b);
        protagSwitch.append(b);
      }
      protagRow.append(protagLbl, protagSwitch);

      for (const [val, label] of [['follow_narrator', '跟随旁白'], ['separate', '独立动作'], ['muted', '动作静音']]) {
        const b = node('button', '', label);
        b.type = 'button';
        b.setAttribute('aria-pressed', 'false');
        b.onclick = () => {
          haptic(8);
          const msg = val === 'separate' ? '已切至独立动作声线（可与旁白区分听感）' : (val === 'muted' ? '已将动作描写设为静音' : '已将动作声线设为跟随旁白');
          void applyRoutingPatch({ action_voice_mode: val }, msg);
        };
        actModeButtons.set(val, b);
        actModeSwitch.append(b);
      }
      actModeRow.append(actModeLbl, actModeSwitch);

      for (const [val, label] of [['all', '全部含主角'], ['heroines', '仅三女主']]) {
        const b = node('button', '', label);
        b.type = 'button';
        b.setAttribute('aria-pressed', 'false');
        b.onclick = () => { haptic(8); void applyRoutingPatch({ action_voice_scope: val }, val === 'all' ? '动作配音覆盖全部角色（含主角）' : '动作配音仅覆盖三女主'); };
        actScopeButtons.set(val, b);
        actScopeSwitch.append(b);
      }
      actScopeRow.append(actScopeLbl, actScopeSwitch);

      for (const [tid, label] of tierDefs) {
        const b = node('button', '', label);
        b.type = 'button';
        b.setAttribute('aria-pressed', 'false');
        b.onclick = async () => {
          haptic(8);
          if (tid === 'drama' && !window.confirm('旗舰导演档（Drama 3）将对三大女主全部台词启用导演声演，旁白、动作与主角仍免费。按字节计费较高（促销后约 $50/百万字节），确认切换？')) {
            return;
          }
          try {
            const res = await VoiceClient.setVoiceTier(tid);
            invalidateVoiceConfig();
            activeVoiceTier = res.tier || tid;
            if (res.config) voiceConfigCache = res.config;
            segmentDomCache.clear();
            signature = '';
            render();
            markTierActive(activeVoiceTier);
            markRoutingUI(voiceConfigCache);
            void loadVoiceConfig().catch(() => null);
            toast((res.msg || '语音品质档位已切换') + '（已刷新本幕音频缓存）');
          } catch (err) {
            toast(err.message || '档位切换失败');
          }
        };
        tierButtons.set(tid, b);
        tierSwitch.append(b);
      }
      tierRow.append(tierLbl, tierSwitch);
      voiceGroup.append(tierRow, protagRow, actModeRow, actScopeRow);
      pane.append(voiceGroup);

      // Collapsible Fish API Key Card (auto-opens only when unconfigured)
      const keyFold = node('details', 'hub-fold pref-fold');
      const keySum = node('summary', 'hub-fold-summary');
      const keyTitleWrap = node('div', 'hub-fold-title');
      const keyDesc = node('span', 'muted', '正在检测本地受保护缓存 (.cache/fish_api_key.json)…');
      keyTitleWrap.append(node('strong', '', 'Fish Audio API 密钥'), keyDesc);
      const keyRight = node('span', 'fold-right');
      const keyBadge = node('span', 'cost-chip', '检测中');
      keyRight.append(keyBadge, node('span', 'fold-caret', '▾'));
      keySum.append(keyTitleWrap, keyRight);
      keyFold.append(keySum);

      const keyBody = node('div', 'hub-fold-body');
      const keyFormRow = node('div', 'action-row');
      const keyInput = node('input', '');
      keyInput.type = 'password';
      keyInput.autocomplete = 'off';
      keyInput.spellcheck = false;
      keyInput.placeholder = '粘贴 Fish Audio API Key（仅存本机受保护缓存）';
      keyInput.style.cssText = 'flex:1;min-width:140px;padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink);font-size:13px;';
      const keySaveBtn = node('button', 'btn-outline', '保存');
      keySaveBtn.type = 'button';
      const keyTestBtn = node('button', 'btn-outline', '保存并测试');
      keyTestBtn.type = 'button';
      const keyClearBtn = node('button', 'btn-outline', '清除');
      keyClearBtn.type = 'button';
      keyFormRow.append(keyInput, keySaveBtn, keyTestBtn, keyClearBtn);
      keyBody.append(keyFormRow);
      keyFold.append(keyBody);
      pane.append(keyFold);

      const refreshVoiceKeyAndTier = async () => {
        try {
          const [st, cfg] = await Promise.all([
            VoiceClient.getFishKeyStatus().catch(() => null),
            loadVoiceConfig().catch(() => null)
          ]);
          if (st && st.configured) {
            keyBadge.textContent = '已配置';
            const srcName = st.source === 'local_cache' ? '本地缓存' : '环境变量';
            keyDesc.textContent = `${st.masked || '已隐藏'} · ${srcName}（点此更改/清除）`;
          } else {
            keyBadge.textContent = '未配置';
            keyDesc.textContent = '尚未保存 Fish API Key，展开填入后主页与工坊共用';
            keyFold.open = true;
          }
          const curTier = cfg?.__settings__?.voice_tier || 'free';
          markTierActive(curTier);
          markRoutingUI(cfg);
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
      void refreshVoiceKeyAndTier();
      return pane;
    }

    // Sub-tab 3: Local Offline Ambient Soundscape
    if (subKey === 'ambient') {
      const ambGroup = node('section', 'pref-group');
      ambGroup.append(node('h3', '', '本地背景音景'));
      ambGroup.append(
        mkSwitchRow(
          '环境背景音',
          '随昼夜/情绪自动淡入淡出循环，人声播报时自动压低背景音（Audio Ducking）',
          [[true, '开启'], [false, '静音']],
          prefs.ambientAudio,
          v => { prefs.ambientAudio = v; savePrefs(); }
        )
      );
      const volRow = node('div', 'pref-row');
      const volLbl = node('div', 'pref-row-label');
      const volPct = Math.round((Number(prefs.ambientVolume) || 0.32) * 100);
      const volValSpan = node('span', '', `当前背景音量：${volPct}%（播报人声时自动压低至约 28%）`);
      volLbl.append(node('strong', '', '氛围背景音量'), volValSpan);
      const volCtrl = node('div', 'audio-vol-wrap');
      const volSlider = node('input', 'audio-vol-slider');
      volSlider.type = 'range';
      volSlider.min = '5';
      volSlider.max = '85';
      volSlider.step = '5';
      volSlider.value = String(volPct);
      volSlider.oninput = () => {
        const pct = Math.max(5, Math.min(85, Number(volSlider.value) || 32));
        prefs.ambientVolume = +(pct / 100).toFixed(2);
        volValSpan.textContent = `当前背景音量：${pct}%（播报人声时自动压低至约 28%）`;
        savePrefs();
      };
      volCtrl.append(volSlider);
      volRow.append(volLbl, volCtrl);
      ambGroup.append(volRow);

      const ambKeys = Object.keys(audioAssets?.ambient || {});
      const ambCount = ambKeys.length;
      const assetRow = node('div', 'pref-row');
      const assetLbl = node('div', 'pref-row-label');
      assetLbl.append(
        node('strong', '', ambCount > 0 ? `已挂载本地背景音（${ambCount} 首）` : '等待放入本地背景音'),
        node(
          'span',
          '',
          ambCount > 0
            ? `已加载：${ambKeys.join(' / ')}（目录：txt文件/audio/ambient/）`
            : '将背景音（calm_home / rain_night / tension_stealth / intimate_warm / aftermath_quiet，支持 .mp3/.ogg/.wav）放入 txt文件/audio/ambient/ 后点刷新即刻生效。'
        )
      );
      const assetRefreshBtn = node('button', 'btn-outline', '刷新检测');
      assetRefreshBtn.type = 'button';
      assetRefreshBtn.onclick = async () => {
        haptic(8);
        assetRefreshBtn.disabled = true;
        try {
          await loadAudioAssets(true);
          const c = Object.keys(audioAssets.ambient || {}).length;
          toast(c > 0 ? `检测到 ${c} 首本地背景音景` : '暂未在 txt文件/audio/ambient/ 检测到背景音文件');
          renderWorld(true);
        } finally {
          assetRefreshBtn.disabled = false;
        }
      };
      assetRow.append(assetLbl, assetRefreshBtn);
      ambGroup.append(assetRow);
      pane.append(ambGroup);
      return pane;
    }

    // Sub-tab 4: Bridge & Maintenance
    const srvGroup = node('section', 'pref-group');
    srvGroup.append(node('h3', '', '本地服务与桥接'));

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

    const voiceLink = node('a', 'btn-outline', '打开声学工坊');
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
      bagSub: activeBagSubTab,
      shopCat: activeShopCat,
      sysSub: activeSystemSubTab,
      char: selectedChar,
      place: selectedMapPlace,
      prefs,
      canDecide: canDecide(),
      canTransact: canTransactDeterministic(),
      resting: resting(),
      shopBusy,
      shopLoading,
      shopError,
      bagPickerState,
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
        deployed_items: w.deployed_items,
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
        intimate: w.intimate,
        host_charm_tier: w.host_charm_tier,
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
          if (item?.classList?.contains('cinema-plate')) observePlateElement(item);
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
        if (want?.classList?.contains('cinema-plate')) observePlateElement(want);
      }
    } else {
      container.replaceChildren(...resolved);
      for (const want of resolved) {
        if (want?.classList?.contains('cinema-plate')) observePlateElement(want);
      }
    }
  }

  function renderSceneAtmospherePills(w) {
    const host = $('sceneAtmospherePills');
    if (!host) return;
    const im = w?.intimate;
    if (!im || typeof im !== 'object') {
      host.hidden = true;
      host.replaceChildren();
      return;
    }
    const pills = [];
    const privLabel = PRIVACY_LABELS[im.privacy] || '';
    if (privLabel) {
      const noise = Number(im.noise_risk) || 0;
      const noiseSuffix = (im.privacy === 'thin_wall' || im.privacy === 'under_cover') && noise >= 40
        ? ` · 声响 ${noise}%` : '';
      const subSuffix = im.sub_location ? ` · ${im.sub_location}` : '';
      pills.push({ cls: 'privacy-pill is-' + im.privacy, text: privLabel + subSuffix + noiseSuffix });
    }
    if (im.scene_active) {
      const beat = Math.max(1, Number(im.session_beats) || 1);
      const c = activeCosts(w);
      const sg = staminaGuard(w);
      const disc = (c.B < COSTS.B || c.C < COSTS.C) ? ` · 折减 ${c.A}/${c.B}/${c.C}⚡` : '';
      const guardTag = sg.active ? ` · 锁底${sg.floor}` : '';
      pills.push({ cls: 'privacy-pill is-intimate', text: `亲密慢燃 · 第${beat}拍${disc}${guardTag}` });
    }
    const hp = im.host_phys;
    if (hp && typeof hp === 'object') {
      const hDes = Number(hp.desire) || 0;
      const hVig = Number.isFinite(Number(hp.vigor)) ? Number(hp.vigor) : 100;
      if (im.scene_active || hDes >= 40) {
        const desTxt = hDes >= 85 ? `欲 ${hDes}·临界` : `欲 ${hDes}`;
        const vigTxt = im.scene_active ? ` · 耐力 ${hVig}` : '';
        pills.push({ cls: 'trace-chip ' + (hDes >= 85 ? 'is-desire-peak' : 'is-host-phys'), text: desTxt + vigTxt });
      }
    }
    const cast = (Array.isArray(im.present_actors) && im.present_actors.length) ? im.present_actors : (w.cast || []);
    const heroCast = cast.filter(n => PEOPLE.includes(n));
    for (const who of heroCast) {
      const att = im.attire?.[who];
      const attLabel = att ? (ATTIRE_STATE_LABELS[att.state] || '') : '';
      if (attLabel) {
        pills.push({ cls: 'trace-chip is-attire', text: `${who} · ${attLabel}` });
      }
      const traces = Array.isArray(im.traces?.[who]) ? im.traces[who] : [];
      for (const tr of traces.slice(0, 2)) {
        if (!tr || !tr.kind) continue;
        pills.push({ cls: 'trace-chip is-trace', text: `${who} · ${tr.kind}` });
      }
    }
    if (heroCast.length >= 2 && im.inter_heroine) {
      const stages = { 1: '暗生疑心', 2: '已察端倪', 3: '默契共谋' };
      let maxStage = 0;
      for (const [pair, lv] of Object.entries(im.inter_heroine)) {
        const [a, b] = pair.split('->');
        if (heroCast.includes(a) && heroCast.includes(b) && Number(lv) > maxStage) {
          maxStage = Number(lv);
        }
      }
      if (maxStage >= 1 && stages[maxStage]) {
        pills.push({ cls: 'trace-chip is-tension', text: `同场暗流 · ${stages[maxStage]}` });
      }
    }
    const sig = pills.map(x => x.cls + ':' + x.text).join('|');
    if (host.dataset.sig === sig) {
      host.hidden = pills.length === 0;
      return;
    }
    host.dataset.sig = sig;
    host.replaceChildren(...pills.slice(0, 6).map(x => node('span', x.cls, x.text)));
    host.hidden = pills.length === 0;
  }

  function render() {
    const w = snapshot?.world, p = snapshot?.playback;
    const c = activeCosts(w);
    const sg = staminaGuard(w);
    const custCost = customReserveCost(w);
    const intimateOn = isIntimateActive(w);
    $('policyNote').textContent = progression()
      ? (intimateOn
        ? `亲密护航 · A ${optionCost('A', w)} · B ${optionCost('B', w)} · C ${optionCost('C', w)} 体力${sg.active ? `（锁底${sg.floor} · 耐力${sg.vigor}）` : ''} · 自定义暂扣${custCost}退差`
        : `A ${c.A} · B ${c.B} · C ${c.C} 体力 · 自定义暂扣${custCost}退差`)
      : '按设定与存档推进 · 本段读完后抉择';
    $('sceneTitle').textContent = w?.location || '正在回到现场';
    $('sceneMeta').textContent = w ? (w.cast.length ? w.cast.join(' · ') + ' 在场' : '此刻独处') : '读取存档中…';
    $('revision').textContent = w ? w.interaction.count + ' 段已存剧情' : '';
    renderSceneVector(w?.location || '');
    renderSceneAtmospherePills(w);

    // Dock & Topbar notification dots
    const hasBagNotice = !!(w?.tasks?.current || w?.tasks?.pending_item || w?.items?.length > 0 || w?.intimate?.keepsakes?.length > 0);
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
    const sig = cache.epoch + ':' + (prefs.cinemaPlates ? 'P1' : 'P0') + ':' + activeVoiceTier + ':' + history.map(t => t.id + ':' + t.messages.length + ':' + (t.handoff || '') + ':' + !!t.settlement).join('|') + pvSig + hpSig + vaSig;
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
          im.src = withThumb(image(name, 'into.png'), 'avatar');
          im.alt = '';
          im.loading = 'lazy';
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
    const activeDesktopFocus = desktopFocusName && names.includes(desktopFocusName)
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

    // Decision Choice Cards with Abyssal Scale Weight Preview & Diegetic Inline Confirm (Scheme A)
    const turn = current(), decision = turn?.decision;
    const oppCue = p?.completed ? (turn?.opportunity_cue || '') : '';
    const ornEl = $('decisionOrnament');
    if (ornEl) {
      ornEl.classList.toggle('is-cue-subtle', oppCue === 'subtle');
      ornEl.classList.toggle('is-cue-accident', oppCue === 'accident');
    }
    const cueEl = $('decisionCue');
    if (cueEl) {
      cueEl.hidden = !oppCue;
      cueEl.classList.toggle('is-accident', oppCue === 'accident');
      cueEl.textContent = oppCue === 'accident' ? '· 契机' : (oppCue === 'subtle' ? '· 暗涌' : '');
    }
    const costSig = (intimateOn ? 'I1' : 'I0') + ':' + c.A + ',' + c.B + ',' + c.C;
    const decisionKey = p?.completed && turn?.id ? (turn.id + '|' + costSig + '|' + oppCue) : '';
    if ($('choices')) $('choices').classList.toggle('is-intimate-mode', intimateOn);
    if ($('choices').dataset.key !== decisionKey) {
      disarmChoice();
      $('choices').dataset.key = decisionKey || '';
      deckCollapsed = false;
      $('choices').replaceChildren();
      if (decision) {
        $('decisionPrompt').textContent = decision.prompt;
        for (const opt of decision.options) {
          const b = node('button', 'story-option' + (intimateOn ? ' is-intimate-opt' : ''));
          b.type = 'button';
          b.dataset.option = opt.id;

          const seal = node('span', 'option-seal', opt.id);
          const body = node('span', 'option-body');
          const moveDest = opt.operation && opt.operation.code === 'move_player' && opt.operation.destination
            ? opt.operation.destination : '';
          const resonance = deriveOptionResonance(opt.id, w);
          const head = node('span', 'option-head');
          head.append(node('span', 'option-label', optionLabel(opt.id, w)));
          if (moveDest) {
            head.append(node('span', 'option-move-badge', '前往 · ' + moveDest));
          }
          if (resonance) {
            head.append(node('span', 'option-resonance-badge is-' + resonance.tone, resonance.text));
          }
          body.append(head, node('span', 'option-text', opt.text));
          b.append(seal, body);

          if (progression()) {
            const costVal = optionCost(opt.id, w);
            const cost = node('span', 'option-cost' + (costVal < (COSTS[opt.id] || 0) ? ' is-discounted' : ''));
            cost.append(icon('energy', 'chip-svg'), node('span', '', String(costVal)));
            b.append(cost);
          }

          bindChoiceGesture(b, opt);
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
    const intimateOn = isIntimateActive(w);

    if (optId === 'A') {
      if (present.some(s => s.stamina <= 15)) return { text: '断电照护 · 温和收束', tone: 'jade' };
      if (intimateOn) return { text: '缓拍挑逗 · 喘息过渡', tone: 'gold' };
      if (present.some(s => s.micro.momentary_ease)) return { text: '戒备已松 · 乘势定心', tone: 'jade' };
      if (maxVig >= 50) return { text: '稳妥周旋 · 避开耳目', tone: 'gold' };
      return null;
    }
    if (optId === 'B') {
      if (intimateOn) return { text: '亲密加深 · 轻中度放行', tone: 'rose' };
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
      const bestRat = present.map(rationalizationTier).filter(Boolean).sort((a, b) => {
        const order = { all: 4, deep: 3, medium: 2, light: 1 };
        return (order[b.level] || 0) - (order[a.level] || 0);
      })[0];
      if (bestRat) return { text: bestRat.text, tone: bestRat.tone };
      if (present.some(s => s.passiveLv >= 4)) return { text: '防线支配 Lv.4 · 豁免完好截断', tone: 'gold' };
      if (present.some(s => s.passiveLv >= 2)) return { text: '认知滤镜 · 惩罚减半', tone: 'gold' };
      if (present.some(s => s.shame >= 85 && s.depravity < 15 && s.passiveLv < 4)) return { text: '防线完好 · 强推易掉好感', tone: 'alert' };
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
          save_epoch: epoch, segment_id: segmentId, revealed: toRevealed, completed: false, catchup: true, compact: true
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
    initialSyncDone = true;
    if (fresh && fresh.compact && snapshot && snapshot.save_epoch === fresh.save_epoch) {
      fresh = {
        ...snapshot,
        playback: fresh.playback || snapshot.playback,
        history: Array.isArray(fresh.history) ? fresh.history : [],
        world: (fresh.world !== undefined && fresh.world !== null) ? fresh.world : snapshot.world,
        settlement: fresh.settlement !== undefined ? fresh.settlement : snapshot.settlement,
        revision: fresh.revision ?? snapshot.revision,
        state_version: fresh.state_version ?? snapshot.state_version,
        save_epoch: fresh.save_epoch,
        has_older: snapshot.has_older
      };
    }
    const prevSegmentId = snapshot?.playback?.segment_id;
    const prevWasActive = active();
    const prevPreview = streamPreview;
    const prevPreviewRevealed = prevPreview ? (prevPreview.revealed || 0) : 0;
    const prevEpoch = cache.epoch;
    const epochChanged = Boolean(prevEpoch && prevEpoch !== fresh.save_epoch);
    if (epochChanged) {
      cache = { epoch: fresh.save_epoch, draft: '', pending: null, voice: cache.voice };
      syncDraftInputs('');
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
      lastEffectSegmentId = '';
      shopCatalog = null;
      shopError = '';
      stopVoice();
      clearAudioCache();
      audioMessage = null;
      if (intentionalEpochSwitch) {
        intentionalEpochSwitch = false;
        error = '';
      } else {
        error = '已切换至新档，旧进度与行动已隔离。';
      }
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
    cache.epoch = fresh.save_epoch;
    snapshot = fresh;
    if (!fresh.playback?.segment_id && Array.isArray(fresh.history) && fresh.history.length === 0) {
      history = [];
      signature = '';
      $('stream').scrollTop = 0;
    } else {
      const map = new Map(history.map(t => [t.id, t]));
      (fresh.history || []).forEach(t => map.set(t.id, t));
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
    if (olderCursor === null && typeof fresh.has_older === 'boolean') hasOlder = fresh.has_older;
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
      const fresh = await api('live/progress', { save_epoch: cache.epoch, segment_id: p.segment_id, revealed, completed, compact: true });
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

  // ── 沉浸式落笔确认：方案 A（选项原位称重/长按落印）+ 方案 B（自由输入 1.8s 收墨撤回） ──
  const CHOICE_HOLD_MS = 550;
  const CHOICE_ARM_MS = 3800;
  const CHOICE_MOVE_CANCEL_PX = 12;
  const INK_DRY_MS = 1800;

  function needsChoiceConfirm(opt) {
    if (prefs.confirmMode === 'off') return false;
    if (prefs.confirmMode === 'critical') {
      const isMove = !!(opt?.operation && opt.operation.code === 'move_player');
      return opt?.id === 'C' || isMove;
    }
    return true;
  }

  function disarmChoice() {
    if (!armedChoice) return;
    if (armedChoice.timer) clearTimeout(armedChoice.timer);
    if (armedChoice.btn) {
      armedChoice.btn.classList.remove('is-armed', 'is-holding');
      armedChoice.btn.querySelector('.option-arm-hint')?.remove();
    }
    $('choices')?.classList.remove('has-armed');
    armedChoice = null;
    previewChoiceWeight(null);
  }

  function armChoice(opt, btn) {
    disarmChoice();
    if (!btn || !opt) return;
    btn.classList.add('is-armed');
    $('choices')?.classList.add('has-armed');
    const head = btn.querySelector('.option-head');
    if (head && !head.querySelector('.option-arm-hint')) {
      head.append(node('span', 'option-arm-hint', '再点落印'));
    }
    previewChoiceWeight(opt.id);
    const timer = setTimeout(() => {
      if (armedChoice && armedChoice.btn === btn) disarmChoice();
    }, CHOICE_ARM_MS);
    armedChoice = { optId: opt.id, opt, btn, timer };
  }

  function bindChoiceGesture(b, opt) {
    let holdTimer = null;
    let holdFired = false;
    let startX = 0, startY = 0;

    const clearHold = () => {
      if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; }
      b.classList.remove('is-holding');
    };

    const tiltOn = () => { if (!armedChoice) previewChoiceWeight(opt.id); };
    const tiltOff = () => { if (!armedChoice) previewChoiceWeight(null); };

    b.addEventListener('mouseenter', tiltOn);
    b.addEventListener('focus', tiltOn);
    b.addEventListener('mouseleave', () => { clearHold(); tiltOff(); });
    b.addEventListener('blur', () => { clearHold(); tiltOff(); });

    b.addEventListener('pointerdown', e => {
      if (e.button > 0 || baseBlocked()) return;
      holdFired = false;
      startX = e.clientX;
      startY = e.clientY;
      previewChoiceWeight(opt.id);
      if (!needsChoiceConfirm(opt)) return;
      clearHold();
      b.classList.add('is-holding');
      holdTimer = setTimeout(() => {
        holdTimer = null;
        holdFired = true;
        b.classList.remove('is-holding');
        if (baseBlocked()) return;
        disarmChoice();
        haptic(10);
        setTimeout(() => haptic(22), 60);
        void enqueue(opt.text, opt.operation || null, opt.id);
      }, CHOICE_HOLD_MS);
    });

    b.addEventListener('pointermove', e => {
      if (!holdTimer) return;
      if (Math.hypot(e.clientX - startX, e.clientY - startY) > CHOICE_MOVE_CANCEL_PX) {
        clearHold();
      }
    });

    b.addEventListener('pointerup', () => clearHold());
    b.addEventListener('pointercancel', () => { clearHold(); tiltOff(); });

    b.onclick = () => {
      clearHold();
      if (holdFired) { holdFired = false; return; }
      if (baseBlocked()) return;
      if (!needsChoiceConfirm(opt)) {
        disarmChoice();
        haptic(14);
        void enqueue(opt.text, opt.operation || null, opt.id);
        return;
      }
      if (armedChoice && armedChoice.optId === opt.id && armedChoice.btn === b) {
        disarmChoice();
        haptic(18);
        void enqueue(opt.text, opt.operation || null, opt.id);
        return;
      }
      haptic(10);
      armChoice(opt, b);
    };
  }

  function clearInkCommit() {
    if (inkCommit?.timer) clearTimeout(inkCommit.timer);
    inkCommit = null;
    const dock = $('inkCommitDock');
    if (dock) {
      dock.replaceChildren();
      dock.hidden = true;
    }
  }

  function recallInkCommit() {
    if (!inkCommit) return;
    const saved = inkCommit;
    clearInkCommit();
    pendingItemAttachment = saved.attached || null;
    renderSheetAttachBar();
    const restoreText = saved.rawDraft != null ? saved.rawDraft : saved.text;
    cache.draft = restoreText;
    syncDraftInputs(restoreText);
    save();
    controls();
    sizing();
    if (saved.source === 'sheet') {
      openComposerSheet();
      $('sheetInput')?.focus();
    } else {
      $('input')?.focus();
    }
    haptic(10);
    toast('已收回，可继续修改');
  }

  function flushInkCommitNow() {
    if (!inkCommit) return;
    const ready = inkCommit;
    clearInkCommit();
    controls();
    haptic(16);
    void enqueue(ready.text, ready.op || null, ready.optionId || 'CUSTOM');
  }

  function stageInkCommit({ text, rawDraft, op = null, optionId = 'CUSTOM', source = 'inline', attached = null, cost = 15 }) {
    clearInkCommit();
    disarmChoice();
    const dock = $('inkCommitDock');
    if (!dock) {
      void enqueue(text, op, optionId);
      return;
    }
    const card = node('article', 'msg player is-ink-drying');
    card.title = '轻点立即落定，或点右侧收回';

    const head = node('div', 'ink-dry-head');
    const costLabel = cost ? ('-' + cost + '⚡ · ') : '';
    head.append(node('span', 'ink-dry-status', costLabel + '墨迹未干 · 轻点立即落定'));
    const recallBtn = node('button', 'ink-recall-btn', '收回');
    recallBtn.type = 'button';
    recallBtn.onclick = e => {
      e.stopPropagation();
      recallInkCommit();
    };
    head.append(recallBtn);

    const body = node('div', 'text');
    const parts = String(text || '').split(/([（(][^）)\r\n]+[）)])/g);
    for (const part of parts) {
      if (!part) continue;
      if (/^[（(][^）)\r\n]+[）)]$/.test(part)) body.append(node('span', 'player-bracket', part));
      else body.append(document.createTextNode(part));
    }
    body.append(node('span', 'ink-dry-bar'));

    card.append(head, body);
    card.onclick = () => flushInkCommitNow();

    dock.replaceChildren(card);
    dock.hidden = false;

    const timer = setTimeout(() => flushInkCommitNow(), INK_DRY_MS);
    inkCommit = { text, rawDraft, op, optionId, source, attached, cost, timer };
    controls();
    latest();
  }

  document.addEventListener('pointerdown', e => {
    if (armedChoice && !e.target.closest?.('#choices')) disarmChoice();
  }, { passive: true });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (inkCommit) { e.preventDefault(); recallInkCommit(); }
      else if (armedChoice) disarmChoice();
    }
  });

  async function enqueue(text, op = null, optionId = 'CUSTOM') {
    if (baseBlocked() || !text.trim() || (optionId !== 'BEGIN' && !canDecide())) return;
    if (optionId !== 'REST' && optionId !== 'BEGIN' && (
      resting() || !afford(optionId === 'CUSTOM'
        ? (/^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test(text) ? 0 : 15)
        : optionCost(optionId))
    )) return;
    const selected = { segment_id: optionId === 'BEGIN' ? '' : snapshot.playback.segment_id, option_id: optionId };
    unlock();
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
    if (optionId === 'CUSTOM') {
      syncDraftInputs('');
      if ($('input')) $('input').style.height = 'auto';
      if ($('sheetInput')) $('sheetInput').style.height = 'auto';
      if (composerSheetOpen) closeComposerSheet();
    }
    await dispatch();
  }

  function syncVoicePlaybackPref(enabled) {
    void api('preferences', { voice_playback_enabled: !!enabled }).then(res => {
      if (snapshot && res?.preferences) snapshot.preferences = res.preferences;
    }).catch(() => {});
  }

  function toggleVoice() {
    haptic(8);
    unlock();
    cache.voice = !cache.voice;
    save();
    syncVoicePlaybackPref(cache.voice);
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
      if (isMobileViewport()) {
        openComposerSheet({ focus: true });
        return;
      }
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
    const wasMuted = !cache.voice;
    cache.voice = true;
    save();
    if (wasMuted) syncVoicePlaybackPref(true);
    void speak(audioMessage.m, audioMessage.id);
  };

  $('stream').addEventListener('click', e => {
    if (e.target.closest('button,a,input,textarea,select,summary,details,.is-ink-drying') || getSelection()?.toString()) return;
    void advance({ x: e.clientX, y: e.clientY });
  });
  $('stream').addEventListener('keydown', e => {
    if (e.target === $('stream') && ['Enter', ' '].includes(e.key)) {
      e.preventDefault();
      void advance();
    }
  });

  async function submitDraftFromComposer(source = 'inline') {
    const rawDraft = source === 'sheet' ? ($('sheetInput')?.value || '') : ($('input')?.value || '');
    const attached = pendingItemAttachment;
    if (baseBlocked() || (!rawDraft.trim() && !attached)) return;
    haptic(14);
    const finalText = rawDraft.trim() || (attached?.defaultAction || '');
    const isPureRec = !attached && /^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test(finalText);
    const cost = isPureRec ? 0 : 15;
    const op = attached?.operation || null;

    if (composerSheetOpen) closeComposerSheet();
    pendingItemAttachment = null;
    renderSheetAttachBar();

    if (prefs.confirmMode === 'off') {
      void enqueue(finalText, op, 'CUSTOM');
      return;
    }
    cache.draft = '';
    syncDraftInputs('');
    if ($('input')) $('input').style.height = 'auto';
    if ($('sheetInput')) $('sheetInput').style.height = 'auto';
    save();
    stageInkCommit({ text: finalText, rawDraft, op, optionId: 'CUSTOM', source, attached, cost });
  }

  let draftSyncTimer = null;
  function scheduleDraftControlsSave() {
    if (draftSyncTimer !== null) clearTimeout(draftSyncTimer);
    draftSyncTimer = setTimeout(() => {
      draftSyncTimer = null;
      save();
      controls();
      sizing();
    }, 150);
  }

  $('form').onsubmit = async e => {
    e.preventDefault();
    await submitDraftFromComposer('inline');
  };
  $('input').addEventListener('focus', () => {
    if (isMobileViewport() && !composerSheetOpen && !$('input').disabled) {
      $('input').blur?.();
      openComposerSheet({ focus: true });
    }
  });
  $('input').addEventListener('input', () => {
    syncDraftInputs($('input').value, $('input'));
    syncInputHeight($('input'));
    scheduleDraftControlsSave();
  });
  $('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $('form').requestSubmit();
    }
  });

  if ($('expandComposerBtn')) {
    $('expandComposerBtn').onclick = () => {
      haptic(6);
      openComposerSheet({ focus: true });
    };
  }
  if ($('sheetCloseBtn')) {
    $('sheetCloseBtn').onclick = () => {
      haptic(6);
      closeComposerSheet();
    };
  }
  if ($('composerSheetBackdrop')) {
    $('composerSheetBackdrop').onclick = () => {
      haptic(6);
      closeComposerSheet();
    };
  }
  if ($('sheetContextPeek')) {
    $('sheetContextPeek').onclick = () => {
      haptic(4);
      $('sheetContextPeek').classList.toggle('is-expanded');
    };
  }
  if ($('sheetInput')) {
    $('sheetInput').addEventListener('input', () => {
      syncDraftInputs($('sheetInput').value, $('sheetInput'));
      syncInputHeight($('sheetInput'));
      const hasContent = Boolean($('sheetInput').value.trim() || pendingItemAttachment);
      if ($('sheetSendBtn')) {
        const isPureRec = !pendingItemAttachment && pureRecovery();
        $('sheetSendBtn').disabled = !hasContent || ordinaryBlocked() || (!isPureRec && !afford(customReserveCost()));
      }
      scheduleDraftControlsSave();
    });
    $('sheetInput').addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !e.isComposing) {
        e.preventDefault();
        void submitDraftFromComposer('sheet');
      }
    });
  }
  if ($('sheetSendBtn')) {
    $('sheetSendBtn').onclick = () => void submitDraftFromComposer('sheet');
  }

  $('refresh').onclick = async () => { haptic(8); await restore(); toast('已同步现场进度'); };
  $('checkPending').onclick = () => void restore();
  $('resendPending').onclick = dispatch;
  $('editPending').onclick = () => {
    if (!cache.pending || !missing || mismatch || posting || polling) return;
    const merged = [cache.pending.action, cache.draft].filter(Boolean).join('\n');
    cache.pending = null;
    syncDraftInputs(merged);
    syncInputHeight($('input'));
    save();
    controls();
    if (isMobileViewport()) openComposerSheet({ focus: true });
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

  const switchActionTab = tab => {
    activeActionTab = tab === 'give' ? 'give' : 'move';
    document.querySelectorAll('#actionTabs [data-action-tab]').forEach(b => {
      b.setAttribute('aria-selected', String(b.dataset.actionTab === activeActionTab));
    });
    if ($('moveForm')) $('moveForm').hidden = activeActionTab !== 'move';
    if ($('giveForm')) $('giveForm').hidden = activeActionTab !== 'give';
  };
  document.querySelectorAll('#actionTabs [data-action-tab]').forEach(b => {
    b.onclick = () => { haptic(8); switchActionTab(b.dataset.actionTab); };
  });

  const openActionSheet = (tab = '') => {
    if (blocked()) return;
    haptic(8);
    if (tab) switchActionTab(tab);
    else switchActionTab(activeActionTab);
    $('actionStatus').textContent = '出行与赠礼将作为本次自定义行动提交。';
    render();
    $('actionDialog').showModal();
  };
  $('actions').onclick = () => openActionSheet();
  if ($('quickActionBtn')) $('quickActionBtn').onclick = () => openActionSheet();
  if ($('sheetBagBtn')) {
    $('sheetBagBtn').onclick = () => {
      haptic(8);
      closeComposerSheet();
      openHub('bag');
    };
  }
  if ($('sheetMoveBtn')) {
    $('sheetMoveBtn').onclick = () => {
      haptic(8);
      closeComposerSheet();
      openActionSheet('move');
    };
  }

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

  function clearArchiveArm() {
    archiveArmKey = '';
    if (archiveArmTimer) {
      clearTimeout(archiveArmTimer);
      archiveArmTimer = null;
    }
  }

  function armArchiveAction(key) {
    clearArchiveArm();
    archiveArmKey = key;
    archiveArmTimer = setTimeout(() => {
      archiveArmKey = '';
      archiveArmTimer = null;
      renderArchiveDialog();
    }, 5000);
  }

  function formatArchiveBytes(n) {
    const num = Number(n) || 0;
    if (num < 1024) return num + ' B';
    if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB';
    return (num / (1024 * 1024)).toFixed(2) + ' MB';
  }

  function formatHeroinesCompact(panelSummary) {
    const hs = panelSummary?.heroines || {};
    return PEOPLE.map(name => {
      const row = hs[name] || {};
      const short = name.slice(-1);
      return `${short} 好${row['好感'] ?? 0}/羞${row['羞耻'] ?? 100}/堕${row['堕落'] ?? 0}`;
    }).join(' · ');
  }

  function switchArchiveTab(tab) {
    archiveTab = tab === 'saves' ? 'saves' : 'newgame';
    clearArchiveArm();
    $('archiveTabs')?.querySelectorAll('[data-archive-tab]').forEach(btn => {
      btn.setAttribute('aria-selected', String(btn.dataset.archiveTab === archiveTab));
    });
    if ($('archiveTabNewGame')) $('archiveTabNewGame').hidden = archiveTab !== 'newgame';
    if ($('archiveTabSaves')) $('archiveTabSaves').hidden = archiveTab !== 'saves';
    renderArchiveDialog();
  }

  function renderArchiveNewGame() {
    const data = archivePrologues;
    const scenarios = Array.isArray(data?.scenarios) ? data.scenarios : [];
    const actions = Number(data?.actions ?? snapshot?.world?.interaction?.actions ?? 0);
    const canReroll = Boolean(data?.can_reroll ?? (actions === 0));
    const curTitle = data?.current?.title || snapshot?.world?.prologue?.title || '未命名序幕';
    const curSid = data?.current?.scenario_id || '';

    const rerollRow = $('archiveRerollRow');
    if (rerollRow) {
      rerollRow.hidden = !canReroll;
      if ($('archiveCurrentBrief')) {
        $('archiveCurrentBrief').textContent = `当前序幕：${curTitle}（尚未行动）`;
      }
    }

    const randomCard = $('archiveRandomCard');
    if (randomCard) {
      const isRand = !archiveSelectedScenario || archiveSelectedScenario === 'random';
      randomCard.classList.toggle('is-selected', isRand);
      randomCard.setAttribute('aria-pressed', String(isRand));
    }

    $('archiveHeroFilter')?.querySelectorAll('[data-hero]').forEach(pill => {
      pill.classList.toggle('is-active', pill.dataset.hero === archiveFilterHero);
    });

    const grid = $('archiveScenarioGrid');
    if (grid) {
      grid.replaceChildren();
      const filtered = scenarios.filter(sc => archiveFilterHero === 'all' || sc.heroine === archiveFilterHero);
      if (!filtered.length) {
        grid.append(node('p', 'muted archive-empty', scenarios.length ? '该筛选下暂无开局。' : '正在读取 10 幕开局池…'));
      } else {
        for (const sc of filtered) {
          const btn = node('button', 'archive-scenario-card');
          btn.type = 'button';
          const selected = archiveSelectedScenario === sc.id;
          btn.classList.toggle('is-selected', selected);
          btn.setAttribute('aria-pressed', String(selected));
          const head = node('div', 'archive-sc-head');
          head.append(
            node('span', 'archive-sc-hero', sc.heroine || '主线'),
            node('span', 'archive-sc-meta', `${sc.weekday || ''} ${sc.time || ''} · ${sc.location || ''}`.trim())
          );
          const titleRow = node('div', 'archive-sc-title-row');
          titleRow.append(node('strong', 'archive-sc-title', sc.title || sc.id));
          if (sc.id === curSid) titleRow.append(node('span', 'archive-sc-now', '当前'));
          btn.append(head, titleRow);
          if (sc.summary) btn.append(node('p', 'archive-sc-summary', sc.summary));
          btn.onclick = () => {
            haptic(8);
            archiveSelectedScenario = sc.id;
            resetRequest = null;
            clearArchiveArm();
            renderArchiveNewGame();
          };
          grid.append(btn);
        }
      }
    }

    const confirmBtn = $('confirmNewGame');
    const noteEl = $('archiveNewGameNote');
    if (confirmBtn) {
      const picked = scenarios.find(s => s.id === archiveSelectedScenario);
      const isRand = !picked;
      const armed = archiveArmKey === 'newgame';
      confirmBtn.classList.toggle('is-armed', armed);
      if (canReroll) {
        confirmBtn.textContent = isRand ? '🎲 免费重摇随机序幕' : `免费切换至「${picked.title}」`;
        if (noteEl) noteEl.textContent = '当前尚未产生正式行动，切换或重摇序幕不会生成多余空档备份。';
      } else if (armed) {
        confirmBtn.textContent = isRand ? '再次轻触确认 · 开启随机新档' : `再次轻触确认 · 开启「${picked.title}」`;
        if (noteEl) noteEl.textContent = '旧档会自动保存至轻量存档槽，确认后立刻切换新局。';
      } else {
        confirmBtn.textContent = isRand ? '开启随机盲盒新档' : `开启「${picked.title}」新档`;
        if (noteEl) noteEl.textContent = '开启新档前，当前进度将自动存入精简存档槽，随时可在「存档槽」页签一键回档。';
      }
    }
  }

  function renderArchiveSaves() {
    const liveCard = $('archiveLiveCard');
    const cur = archiveSaves?.current;
    if (liveCard) {
      liveCard.replaceChildren();
      if (cur) {
        const title = node('div', 'archive-live-head');
        title.append(
          node('span', 'archive-slot-badge is-live', '当前进度'),
          node('strong', '', `第${cur.day || 1}天 ${cur.weekday || ''} ${cur.time || ''} · ${cur.location || '徐家主宅'}`.trim()),
          node('span', 'archive-slot-sub', `${cur.actions || 0} 次行动`)
        );
        liveCard.append(title, node('p', 'archive-slot-vitals', formatHeroinesCompact(cur.panel_summary)));
      } else {
        liveCard.append(node('p', 'muted', '正在读取当前存档摘要…'));
      }
    }

    const listEl = $('archiveSlotList');
    if (!listEl) return;
    listEl.replaceChildren();
    const slots = Array.isArray(archiveSaves?.slots) ? archiveSaves.slots : [];
    if (!slots.length) {
      listEl.append(node('p', 'muted archive-empty', '尚无存档槽。你可以在上方备注并点击「＋ 存为新档槽」，或在重开新档时自动留存一份快照。'));
      return;
    }

    const kindMeta = {
      manual: { label: '手动档槽', cls: 'is-manual' },
      auto_before_reset: { label: '重开前备份', cls: 'is-auto' },
      auto_before_restore: { label: '回档前备份', cls: 'is-auto' },
      legacy: { label: '旧版备份', cls: 'is-legacy' }
    };

    for (const slot of slots) {
      const card = node('article', 'archive-slot-card');
      const head = node('div', 'archive-slot-head');
      const km = kindMeta[slot.kind] || kindMeta.auto_before_reset;
      head.append(
        node('span', 'archive-slot-badge ' + km.cls, km.label),
        node('strong', 'archive-slot-label', slot.label || slot.id),
        node('span', 'archive-slot-time', slot.created_at || '')
      );
      const metaLine = node('p', 'archive-slot-meta',
        `第${slot.day || 1}天 ${slot.weekday || ''} ${slot.time || ''} · ${slot.location || ''} · ${slot.actions || 0}次行动 · ${formatArchiveBytes(slot.size_bytes)}`.replace(/\s+·\s+·/g, ' · ')
      );
      const vitalsLine = node('p', 'archive-slot-vitals', formatHeroinesCompact(slot.panel_summary));

      const actionsRow = node('div', 'archive-slot-actions');
      const restoreKey = 'restore:' + slot.id;
      const deleteKey = 'delete:' + slot.id;
      const restoreBtn = node('button', 'btn-outline archive-slot-btn' + (archiveArmKey === restoreKey ? ' is-armed' : ''),
        archiveArmKey === restoreKey ? '确认回档（自动留存现档）' : '一键回档');
      restoreBtn.type = 'button';
      restoreBtn.disabled = archiveBusy || baseBlocked();
      restoreBtn.onclick = async () => {
        if (archiveBusy || baseBlocked()) return;
        haptic(12);
        if (archiveArmKey !== restoreKey) {
          armArchiveAction(restoreKey);
          renderArchiveSaves();
          return;
        }
        clearArchiveArm();
        archiveBusy = true;
        posting = true;
        $('newGameStatus').textContent = '';
        controls();
        renderArchiveSaves();
        intentionalEpochSwitch = true;
        try {
          const reqId = 'restore-' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36));
          await api('saves/restore', {
            save_epoch: cache.epoch,
            slot_id: slot.id,
            confirm: 'restore_save',
            request_id: reqId
          });
          $('newGameDialog').close();
          toast('已回档至「' + (slot.label || slot.id) + '」');
        } catch (e) {
          intentionalEpochSwitch = false;
          $('newGameStatus').textContent = e.message;
        } finally {
          archiveBusy = false;
          posting = false;
          await restore({ preserveError: true });
          if ($('newGameDialog').open) await refreshArchiveData();
        }
      };

      const delBtn = node('button', 'btn-danger-outline archive-slot-btn is-del' + (archiveArmKey === deleteKey ? ' is-armed' : ''),
        archiveArmKey === deleteKey ? '确认删除？' : '删除');
      delBtn.type = 'button';
      delBtn.disabled = archiveBusy || baseBlocked();
      delBtn.onclick = async () => {
        if (archiveBusy || baseBlocked()) return;
        haptic(10);
        if (archiveArmKey !== deleteKey) {
          armArchiveAction(deleteKey);
          renderArchiveSaves();
          return;
        }
        clearArchiveArm();
        archiveBusy = true;
        $('newGameStatus').textContent = '';
        controls();
        renderArchiveSaves();
        try {
          const res = await api('saves/' + encodeURIComponent(slot.id), { save_epoch: cache.epoch }, 'DELETE');
          if (archiveSaves && Array.isArray(res?.slots)) archiveSaves.slots = res.slots;
          toast('已删除存档槽');
        } catch (e) {
          $('newGameStatus').textContent = e.message;
        } finally {
          archiveBusy = false;
          controls();
          renderArchiveSaves();
        }
      };

      actionsRow.append(restoreBtn, delBtn);
      card.append(head, metaLine, vitalsLine, actionsRow);
      listEl.append(card);
    }
  }

  function renderArchiveDialog() {
    renderArchiveNewGame();
    renderArchiveSaves();
  }

  async function refreshArchiveData() {
    try {
      const [pro, sav] = await Promise.all([api('prologues'), api('saves')]);
      archivePrologues = pro;
      archiveSaves = sav;
      renderArchiveDialog();
    } catch (e) {
      $('newGameStatus').textContent = '读取档案室失败：' + e.message;
    }
  }

  function openArchiveDialog(initialTab = 'newgame') {
    haptic(10);
    if ($('worldDialog')?.open) $('worldDialog').close();
    $('newGameStatus').textContent = '';
    resetRequest = null;
    archiveSelectedScenario = 'random';
    archiveFilterHero = 'all';
    clearArchiveArm();
    switchArchiveTab(initialTab);
    $('newGameDialog').showModal();
    controls();
    void refreshArchiveData();
  }

  $('newGame').onclick = () => openArchiveDialog('newgame');
  if ($('archiveQuickBtn')) $('archiveQuickBtn').onclick = () => openArchiveDialog('newgame');

  $('archiveTabs')?.querySelectorAll('[data-archive-tab]').forEach(btn => {
    btn.onclick = () => {
      haptic(6);
      switchArchiveTab(btn.dataset.archiveTab);
    };
  });

  if ($('archiveRandomCard')) {
    $('archiveRandomCard').onclick = () => {
      haptic(8);
      archiveSelectedScenario = 'random';
      resetRequest = null;
      clearArchiveArm();
      renderArchiveNewGame();
    };
  }

  $('archiveHeroFilter')?.querySelectorAll('[data-hero]').forEach(pill => {
    pill.onclick = () => {
      haptic(6);
      archiveFilterHero = pill.dataset.hero || 'all';
      renderArchiveNewGame();
    };
  });

  if ($('rerollPrologueBtn')) {
    $('rerollPrologueBtn').onclick = async () => {
      if (baseBlocked() || archiveBusy) return;
      haptic(12);
      archiveBusy = true;
      posting = true;
      $('newGameStatus').textContent = '';
      controls();
      intentionalEpochSwitch = true;
      try {
        const res = await api('new-game', {
          request_id: 'reroll-' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)),
          save_epoch: cache.epoch,
          confirm: 'new_game',
          reroll_only: true
        });
        $('newGameDialog').close();
        toast('已免费重摇序幕：' + (res?.prologue?.title || '新开局'));
      } catch (e) {
        intentionalEpochSwitch = false;
        $('newGameStatus').textContent = e.message;
      } finally {
        archiveBusy = false;
        posting = false;
        await restore({ preserveError: true });
      }
    };
  }

  if ($('saveSlotCreateBtn')) {
    $('saveSlotCreateBtn').onclick = async () => {
      if (baseBlocked() || archiveBusy) return;
      haptic(12);
      const inp = $('saveSlotLabelInput');
      const label = (inp?.value || '').trim();
      archiveBusy = true;
      $('newGameStatus').textContent = '';
      controls();
      try {
        const res = await api('saves/snapshot', { save_epoch: cache.epoch, label });
        if (inp) inp.value = '';
        if (archiveSaves && Array.isArray(res?.slots)) archiveSaves.slots = res.slots;
        else await refreshArchiveData();
        toast('已存为档槽：' + (res?.slot?.label || '手动存档'));
      } catch (e) {
        $('newGameStatus').textContent = e.message;
      } finally {
        archiveBusy = false;
        controls();
        renderArchiveSaves();
      }
    };
  }

  $('confirmNewGame').onclick = async () => {
    if (baseBlocked() || archiveBusy) return;
    const actions = Number(archivePrologues?.actions ?? snapshot?.world?.interaction?.actions ?? 0);
    const canReroll = Boolean(archivePrologues?.can_reroll ?? (actions === 0));
    if (!canReroll && archiveArmKey !== 'newgame') {
      haptic(10);
      armArchiveAction('newgame');
      renderArchiveNewGame();
      return;
    }
    clearArchiveArm();
    haptic(16);
    archiveBusy = true;
    posting = true;
    $('newGameStatus').textContent = '';
    controls();
    const chosen = archiveSelectedScenario && archiveSelectedScenario !== 'random' ? archiveSelectedScenario : 'random';
    resetRequest = resetRequest || {
      request_id: (canReroll ? 'reroll-' : 'reset-') + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)),
      save_epoch: cache.epoch,
      confirm: 'new_game',
      scenario_id: chosen,
      ...(canReroll ? { reroll_only: true } : {})
    };
    intentionalEpochSwitch = true;
    try {
      const res = await api('new-game', resetRequest);
      resetRequest = null;
      $('newGameDialog').close();
      toast((canReroll ? '已切换序幕：' : '已开启新档：') + (res?.prologue?.title || '随机盲盒'));
    } catch (e) {
      intentionalEpochSwitch = false;
      $('newGameStatus').textContent = e.message + '；可按原编号再次确认。';
    } finally {
      archiveBusy = false;
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
  if ($('storyBindPrimaryBtn')) {
    $('storyBindPrimaryBtn').onclick = () => {
      const parsed = parseModelPair($('storyPrimaryTarget')?.value);
      if (!parsed) { error = '请先选择要绑定到 CHAT 槽的主模型。'; controls(); return; }
      bridgePrimarySyncedKey = '';
      void sendBridgeControl({
        action: 'bind_function_slot',
        slot: 'CHAT',
        provider_id: parsed.provider_id,
        model_id: parsed.model_id,
      }, '已将 CHAT 槽主模型绑定为 ' + parsed.model_id);
    };
  }
  if ($('storyPrimaryTarget')) {
    $('storyPrimaryTarget').onchange = () => {
      if ($('storyBindPrimaryBtn')) $('storyBindPrimaryBtn').disabled = !$('storyPrimaryTarget').value;
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
        if (initialSyncDone) scheduleRestore(30);
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
      es.addEventListener('shop_updated', event => { trackSseEventSeq(event); void handleShopUpdatedEvent(event); });
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
    if (composerSheetOpen) {
      closeComposerSheet();
    } else if ($('gazeLens')?.classList.contains('is-open')) {
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
    // Accurate delta for resizes-visual viewports (avoid cancelling offsetTop)
    const visualDelta = v ? Math.max(0, Math.round(curH - visualH)) : 0;
    const layoutShrink = Math.max(0, Math.round(baseViewportHeight - visualH));
    const kbOpen = isEditableFocused() && (layoutShrink > 120 || visualDelta > 120);
    if (visualH > 0) {
      document.documentElement.style.setProperty('--vvh', Math.round(visualH) + 'px');
    }
    document.documentElement.style.setProperty('--vv-top', Math.max(0, Math.round(visualOffset)) + 'px');
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
  document.addEventListener('focusin', () => {
    setTimeout(viewport, 60);
    setTimeout(viewport, 180);
    setTimeout(viewport, 360);
  });
  document.addEventListener('focusout', () => setTimeout(viewport, 120));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopVoice();
      pauseAmbient();
      closeSSE();
    } else {
      invalidateVoiceConfig();
      void loadVoiceConfig().catch(() => null);
      void loadAudioAssets(true).catch(() => null);
      sseRetryAttempt = 0;
      connectSSE();
      void restore();
    }
  });
  window.addEventListener('pagehide', () => {
    if (inkCommit) {
      cache.draft = inkCommit.rawDraft != null ? inkCommit.rawDraft : inkCommit.text;
      save();
      clearInkCommit();
    }
    stopVoice();
    pauseAmbient();
    closeSSE();
    urls.clear();
  });

  initAmbientRain();
  applyPrefs();
  viewport();
  syncDraftInputs(cache.draft);
  syncInputHeight($('input'));
  save();
  render();
  void loadVoiceConfig().catch(() => null);
  void loadAudioAssets().catch(() => null);
  connectSSE();
  void restore();
  setInterval(() => { if (!document.hidden && !sseOpen) void restore(); }, 15000);
})();

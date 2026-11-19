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

  const MAP_COORDS = {
    '徐家主宅':       { x: 180, y: 46,  short: '徐家主宅' },
    '市中心顶层公寓': { x: 86,  y: 112, short: '顶层公寓' },
    '公司':           { x: 274, y: 112, short: '集团公司' },
    '大学':           { x: 112, y: 176, short: '艺术大学' },
    '工作室':         { x: 248, y: 176, short: '画室工坊' }
  };

  const SVG_NS = 'http://www.w3.org/2000/svg';

  let cache = { epoch: '', draft: '', pending: null, voice: true };
  let prefs = { theme: 'noir', font: 'normal', haptics: true, backdrop: true };
  let snapshot = null, online = false, posting = false, polling = false, progressing = false;
  let storageOK = true, error = '', missing = false, mismatch = false;
  let portraitName = '', signature = '', worldSignature = '', lastSpeaker = '', backdropTarget = '';
  let history = [], hasOlder = false, olderCursor = null, resetRequest = null;
  let audioSerial = 0, audioMessage = null, audioStatus = '', isSpeaking = false;
  let gesture = false, configPromise = null, lastTap = 0;
  let activeHubTab = 'host', selectedChar = '', selectedMapPlace = '', historyFilter = 'all';
  let settlementFolded = false;

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
  } catch (_) {}

  function reducedMotion() {
    return matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function applyPrefs() {
    document.documentElement.dataset.theme = prefs.theme;
    document.documentElement.dataset.font = prefs.font;
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) metaTheme.setAttribute('content', prefs.theme === 'ivory' ? '#f4efe6' : '#0f0d0b');
    updateBackdrop();
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
    const item = node('div', 'toast-item', message);
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
      gift:    'M4 10h16v10H4V10Zm-1-3h18v3H3V7Zm9 0v13m0-13c-1.5-3-5-3-5-1s3.5 1 5 1Zm0 0c1.5-3 5-3 5-1s-3.5 1-5 1Z'
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

  const active = () => ['preparing', 'queued', 'generating', 'validating', 'refund_pending'].includes(snapshot?.task?.status);
  const baseBlocked = () => posting || polling || progressing || !online || !storageOK || ![2, 3].includes(snapshot?.interaction_protocol) || !!cache.pending || active();
  const canDecide = () => !!snapshot?.playback?.segment_id && snapshot.playback.completed;
  const blocked = () => baseBlocked() || !canDecide();
  const current = () => history.find(t => t.id === snapshot?.playback?.segment_id);
  const progression = () => snapshot?.world?.progression;
  const resting = () => !!progression() && (progression().runtime.phase === 'resting' || (snapshot?.task?.reservation?.status !== 'held' && progression().stamina < 5));
  const pureRecovery = () => /^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test($('input').value);
  const afford = n => !progression() || progression().stamina >= n;
  const ordinaryBlocked = () => blocked() || resting();

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

  function image(name, file = 'into.png') {
    return '/txt文件/image/' + encodeURIComponent(name) + '/' + file;
  }

  function updateBackdrop() {
    const img = $('stageBackdrop');
    if (!img) return;
    const w = snapshot?.world;
    const candidate = PEOPLE.includes(lastSpeaker) ? lastSpeaker : (w?.cast?.[0] || '');
    if (!prefs.backdrop || !candidate) {
      img.classList.remove('is-ready');
      backdropTarget = '';
      return;
    }
    if (backdropTarget === candidate) {
      if (img.complete && img.naturalWidth) img.classList.add('is-ready');
      return;
    }
    backdropTarget = candidate;
    img.classList.remove('is-ready');
    const src = image(candidate, 'into.png');
    img.onload = () => { if (backdropTarget === candidate && prefs.backdrop) img.classList.add('is-ready'); };
    img.src = src;
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
        const { day, time } = pg.runtime.clock;
        clockText.textContent = '第' + day + '天 · ' + time;
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

  function controls() {
    const p = snapshot?.playback, ready = canDecide(), base = baseBlocked(), hasSegment = !!p?.segment_id;
    const rest = resting(), isAct = active();

    document.body.classList.toggle('is-thinking', isAct);
    $('statusSpinner').hidden = !isAct;

    $('decisionPanel').hidden = !ready || rest;
    $('form').hidden = !ready || rest;
    $('restCard').hidden = !ready || !rest;
    $('rest').hidden = !ready || !rest;
    $('rest').disabled = base;
    $('cancelTask').hidden = !isAct || !snapshot?.task?.reservation;
    $('cancelTask').disabled = posting || progressing;

    const pg = progression(), res = snapshot?.task?.reservation;
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

    $('actions').hidden = !ready || rest;
    $('actions').disabled = ordinaryBlocked() || !afford(15);
    if ($('quickActionBtn')) $('quickActionBtn').disabled = ordinaryBlocked() || !afford(15);
    $('move').disabled = ordinaryBlocked() || !afford(15) || !$('destination').value;
    $('give').disabled = ordinaryBlocked() || !afford(15) || !$('item').value || !$('recipient').value;

    $('choices').querySelectorAll('button').forEach(b => {
      b.disabled = ordinaryBlocked() || !afford(COSTS[b.dataset.option]);
    });

    $('playbackBar').hidden = !hasSegment || ready;
    $('advance').hidden = !hasSegment || p.completed;
    $('advance').disabled = base;
    const advLabel = $('advanceLabel') || $('advance');
    advLabel.textContent = progressing ? '正在保存进度…'
      : !p?.revealed ? '开始演播'
      : p.revealed < p.total ? '轻触继续剧情'
      : '读完本段 · 展开抉择';
    $('playbackCount').textContent = hasSegment
      ? (p.completed ? '本段已读完' : p.revealed + ' / ' + p.total)
      : '';
    if (hasSegment) updatePlaybackPips(p);

    $('voiceToggle').textContent = cache.voice ? '语音开' : '已静音';
    $('voiceToggle').setAttribute('aria-pressed', String(cache.voice));
    $('hudVoiceBtn').setAttribute('aria-pressed', String(cache.voice));
    $('hudVoiceWave').classList.toggle('is-speaking', isSpeaking && cache.voice);

    $('replayVoice').hidden = !audioMessage;
    $('replayVoice').textContent = audioStatus.includes('启用') ? '启用语音' : '重听';
    $('audioStatus').textContent = audioStatus;

    $('begin').hidden = hasSegment;
    $('begin').disabled = base;
    if (!hasSegment) $('begin').textContent = rest ? '开始休息 · 免费' : '踏入此刻 · 继续剧情';

    $('refresh').disabled = posting || polling || progressing;
    const showRetry = ['failed', 'interrupted', 'cancelled'].includes(snapshot?.task?.status);
    $('retry').hidden = !showRetry;
    $('retry').disabled = base;
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

    const task = snapshot?.task;
    $('pending').textContent = cache.pending
      ? '待确认行动：' + cache.pending.action
      : task && ['queued', 'generating', 'validating', 'failed', 'interrupted'].includes(task.status)
        ? '当前行动：' + task.action
        : '';
    $('pending').hidden = !$('pending').textContent;

    $('status').classList.toggle('error', !!error || !!task?.error);
    $('status').textContent = error || (
      !online ? '正在连接本地剧场服务，你的行动已安全保留……'
      : ![2, 3].includes(snapshot?.interaction_protocol) ? '请重启本地服务以加载最新剧情演播接口。'
      : cache.pending
        ? (mismatch ? '原编号与服务记录不符，请在系统设定查看连接详情。'
          : missing ? '原编号尚未登记，可点击下方按钮重发。'
          : '正在核对上一次行动状态…')
      : isAct
        ? (task.status === 'generating' ? '天平演算中 · 正在承接你的抉择推演剧情……'
          : task.status === 'validating' ? '正在校验剧情并写入记忆存档……'
          : '已入列 · 等待 Operit 桥接回应……')
      : task?.error || (
        !hasSegment ? '幕布已备好，轻触下方按钮进入此刻现场。'
        : !p.completed ? '轻触屏幕任意处继续阅读，读完本段后落下抉择。'
        : !snapshot.bridge_connected ? '抉择已就绪 · 桥接待连接。'
        : rest ? '夜色已深，本段收束，请安稳休整后再启程。'
        : '此刻由你决定下一步。'
      )
    );

    const bridgeOnline = !!snapshot?.bridge_connected;
    $('bridgeDot')?.classList.toggle('is-online', bridgeOnline);
    $('bridgeInfo').textContent = (bridgeOnline ? '桥接已连接' : '桥接未连接')
      + (snapshot?.bridge_model ? ' · ' + snapshot.bridge_model.model_id : '')
      + (snapshot?.bridge?.last_error ? ' · ' + snapshot.bridge.last_error : '');

    updateHudVitals();
  }

  function showPortrait(name, file = 'fullbody.png') {
    const meta = CHAR_META[name] || { role: '', fullbody: false };
    portraitName = name;
    if (!meta.fullbody) file = 'into.png';
    $('portraitName').textContent = name;
    $('portraitRole').textContent = meta.role || '';
    const img = $('portrait');
    const loader = $('portraitLoader');
    img.classList.remove('is-loaded');
    loader.classList.remove('is-done');
    const targetSrc = image(name, file);
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
    document.querySelectorAll('#portraitDialog [data-file]').forEach(b => {
      b.hidden = !meta.fullbody && b.dataset.file !== 'into.png';
      b.setAttribute('aria-pressed', String(b.dataset.file === file));
    });
    if (!$('portraitDialog').open) $('portraitDialog').showModal();
  }

  function stopVoice() {
    audioSerial++;
    isSpeaking = false;
    VoiceClient.cancel('live');
    $('audio').pause();
    $('audio').onended = null;
    audioStatus = '';
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
    audioMessage = { m, id };
    if (!cache.voice || !gesture) {
      controls();
      return;
    }
    const serial = audioSerial;
    audioStatus = '合成语音中…';
    controls();
    try {
      let url = audioCache.get(id);
      if (!url || !urls.has(url)) {
        configPromise = configPromise || VoiceClient.requestJson('/api/config', { cache: 'no-store' }).catch(e => { configPromise = null; throw e; });
        const config = await configPromise;
        if (serial !== audioSerial || document.hidden) return;
        const who = m.kind === 'dialogue' ? m.speaker : '旁白';
        const cfg = config[who] || config['旁白'] || {};
        const blob = await VoiceClient.requestAudio(VoiceClient.buildPayload(m.text, cfg, config.__settings__ || {}), { channel: 'live', maxBytes: 16 * 1024 * 1024 });
        if (serial !== audioSerial || document.hidden) return;
        url = urls.add(blob);
        audioCache.set(id, url);
        for (const [key, value] of audioCache) if (!urls.has(value)) audioCache.delete(key);
      }
      if (serial !== audioSerial || !cache.voice || document.hidden) return;
      urls.pin(url);
      $('audio').src = url;
      await $('audio').play();
      if (serial !== audioSerial) return;
      isSpeaking = true;
      audioStatus = '朗读中';
      $('audio').onended = () => {
        if (serial === audioSerial) {
          isSpeaking = false;
          audioStatus = '已播完';
          controls();
        }
      };
    } catch (e) {
      isSpeaking = false;
      if (serial === audioSerial) {
        audioStatus = e.name === 'NotAllowedError' ? '点“启用语音”继续听读' : '语音暂不可用';
      }
    }
    controls();
  }

  function entry(kind, speaker, text, id) {
    const isPlayer = speaker === '徐志北';
    const el = node('article', 'msg ' + kind + (isPlayer ? ' player' : ''));
    el.dataset.messageId = id;
    if (speaker) el.dataset.speaker = speaker;
    el.setAttribute('aria-label', kind === 'narration' ? '旁白' : speaker + (kind === 'action' ? '的动作' : '的对白'));

    if (kind === 'narration') {
      const mark = node('div', 'narration-mark');
      const diamond = svgEl('svg', { viewBox: '0 0 12 12', class: 'narration-diamond', 'aria-hidden': 'true' });
      diamond.append(svgEl('path', { d: 'M6 1 11 6 6 11 1 6Z', fill: 'currentColor' }));
      mark.append(diamond, node('span', '', '旁白'), diamond.cloneNode(true));
      el.append(mark);
    } else if (kind === 'handoff') {
      const h = node('div', 'message-heading');
      h.append(icon('scroll', 'chip-svg'), node('span', '', speaker));
      el.append(h);
    } else {
      if (PEOPLE.includes(speaker) || isPlayer) {
        const im = node('img', 'avatar');
        im.src = image(speaker, 'into.png');
        im.alt = '';
        im.decoding = 'async';
        if (PEOPLE.includes(speaker)) {
          im.style.cursor = 'pointer';
          im.onclick = e => { e.stopPropagation(); haptic(8); showPortrait(speaker); };
        }
        el.append(im);
      }
      const h = node('div', 'message-heading');
      h.append(node('span', '', speaker));
      if (kind === 'action') h.append(node('span', 'kind-label', '动作'));
      el.append(h);
    }
    el.append(node('div', 'text', isPlayer ? text : text.replace(/\[[^\]\r\n]+\]/g, '')));
    return el;
  }

  function timeline(filter = 'all') {
    const out = [];
    for (const t of history) {
      if (filter === 'all' && t.selection?.option_id !== 'BEGIN') {
        out.push(entry(t.input_kind === 'action' ? 'action' : 'dialogue', '徐志北', t.input, t.id + ':input'));
      }
      t.messages.forEach((m, i) => {
        if (filter === 'settlement') return;
        if (filter === 'dialogue' && m.kind !== 'dialogue') return;
        out.push(entry(m.kind, m.speaker, m.text, t.id + ':' + i));
      });
      if (filter === 'all' && t.handoff) {
        out.push(entry('handoff', '待处理', t.handoff, t.id + ':handoff'));
      }
      if (t.settlement && (filter === 'settlement' || t.id !== snapshot?.playback?.segment_id)) {
        out.push(settlementCard(t.settlement, false));
      }
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

  function settlementCard(s, foldable = false) {
    const isFolded = foldable && settlementFolded;
    const box = node('section', 'settlement-card game-settlement' + (s.phase === 'resting' ? ' resting' : s.sleep_completed ? ' rested' : '') + (isFolded ? '' : ' is-expanded'));
    const header = node('div', 'settlement-head');
    const title = node('div', 'settlement-title');
    const mark = node('span', 'reward-mark');
    mark.append(icon(s.sleep_completed ? 'moon' : s.phase === 'resting' ? 'clock' : 'check'));

    const titleStack = node('div', 'settlement-title-stack');
    titleStack.append(node('span', '', s.sleep_completed ? '安稳醒来 · 崭新晨光' : s.phase === 'resting' ? '本段收束 · 宜入眠休整' : '行动已结算'));
    if (foldable) {
      titleStack.append(node('span', 'settlement-quick-sub', '体力 ' + s.stamina_before + ' → ' + s.stamina_after + ' / 100'));
    }
    title.append(mark, titleStack);

    const right = node('div', 'settlement-head-right');
    right.append(node('span', 'settlement-badge', s.kind === 'item' ? '道具恢复' : s.kind === 'rest' ? '免费休息' : '-' + s.net_cost + ' 体力'));

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
      right.append(foldBtn);
    }

    header.append(title, right);
    box.append(header);

    const changes = s.changes || [];
    const rewards = changes.filter(c => c.target !== '系统宿主' || c.attribute !== '体力');
    const buildRewardPills = cls => {
      const wrap = node('div', cls);
      rewards.slice(0, 5).forEach((c, idx) => {
        const meta = rewardIconFor(c.attribute);
        const tag = node('span', 'reward-pill ' + (c.delta < 0 ? 'is-negative' : meta.cls));
        tag.style.animationDelay = (idx * 55) + 'ms';
        const who = c.target === '系统宿主' ? '' : c.target + ' ';
        tag.append(icon(meta.icon), node('span', '', who + c.attribute + ' ' + (c.delta > 0 ? '+' : '') + c.delta));
        wrap.append(tag);
      });
      return wrap;
    };

    if (foldable && rewards.length) {
      box.append(buildRewardPills('settlement-compact-rewards'));
    }

    const balance = node('div', 'balance-line');
    const label = node('span', '');
    label.append(icon('energy', 'chip-svg'), node('span', '', '宿主体力'));
    balance.append(label, node('strong', '', s.stamina_before + ' → ' + s.stamina_after), node('span', 'balance-cap', '/ 100'));
    body.append(balance);

    const meter = node('div', 'stamina-meter');
    meter.setAttribute('role', 'meter');
    meter.setAttribute('aria-label', '结算后体力');
    meter.setAttribute('aria-valuemin', '0');
    meter.setAttribute('aria-valuemax', '100');
    meter.setAttribute('aria-valuenow', String(s.stamina_after));
    const fill = node('span', 'stamina-fill');
    fill.style.setProperty('--balance', Math.max(0, Math.min(100, s.stamina_after)) + '%');
    meter.append(fill);
    body.append(meter);

    const fees = node('div', 'fee-line');
    for (const [key, value] of [['暂扣', s.reserved], ['返还', s.refunded], ['实耗', s.net_cost]]) {
      const part = node('span', '');
      part.append(node('small', '', key), node('b', '', String(value)));
      fees.append(part);
    }
    body.append(fees);

    if (rewards.length) {
      body.append(buildRewardPills('reward-list'));
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
    box.hidden = !s && !refund;
    const key = s?.request_id || (refund ? snapshot.task.request_id + ':refund' : '');
    if (box.dataset.id === key) return;
    box.dataset.id = key;
    settlementFolded = true;
    box.replaceChildren();
    if (s) {
      box.append(settlementCard(s, true));
    } else if (refund) {
      const card = node('section', 'settlement-card game-settlement returned');
      const title = node('div', 'settlement-title');
      const mark = node('span', 'reward-mark');
      mark.append(icon('refund'));
      title.append(mark, node('strong', '', '预扣体力已全额返还'));
      card.append(title, node('p', 'round-receipt', '已返还 +' + refund.amount + ' 体力'), node('p', 'muted', refund.reason));
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
        const ring = svgEl('circle', { cx: pos.x, cy: pos.y, r: 10, class: 'map-beacon-ring', opacity: '0.65' });
        if (!reducedMotion()) {
          ring.append(
            svgEl('animate', { attributeName: 'r', values: '9;22', dur: '2.4s', repeatCount: 'indefinite' }),
            svgEl('animate', { attributeName: 'opacity', values: '0.85;0', dur: '2.4s', repeatCount: 'indefinite' })
          );
        }
        g.append(ring);
      }
      g.append(
        svgEl('circle', { cx: pos.x, cy: pos.y, r: 24, class: 'map-node-hit' }),
        svgEl('circle', { cx: pos.x, cy: pos.y, r: isHere || isSel ? 9 : 7, class: 'map-node-dot' })
      );
      const label = svgEl('text', { x: pos.x, y: pos.y + 22, class: 'map-node-label' });
      label.textContent = pos.short || loc;
      g.append(label);

      const whoList = (occupants[loc] || []).filter(n => n !== '徐志北');
      if (whoList.length) {
        const sub = svgEl('text', { x: pos.x, y: pos.y - 14, class: 'map-node-count' });
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
      clk.append(icon('clock', 'chip-svg'), node('span', '', '第' + pg.runtime.clock.day + '天 ' + pg.runtime.clock.time));
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
      const tile = node('div', 'attr-tile');
      const head = node('div', 'attr-tile-head');
      head.append(node('span', '', item.key), icon(cfg.icon, 'chip-svg'));
      const val = node('div', 'attr-tile-val', item.raw);
      tile.append(head, val);
      if (cfg.max && item.num !== null) {
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
      if (meta.hasPortrait) {
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

    if (meta.hasPortrait) {
      const banner = node('div', 'char-banner');
      const img = node('img', 'char-banner-img');
      img.src = image(name, 'into.png');
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

      if (meta.fullbody) {
        const openBtn = node('button', 'portrait-open-btn', '展开全身立绘');
        openBtn.type = 'button';
        openBtn.onclick = () => { haptic(10); showPortrait(name, 'fullbody.png'); };
        overlay.append(openBtn);
      }
      banner.append(img, scrim, overlay);
      card.append(banner);
    } else {
      const head = node('div', 'char-body');
      const row = node('div', 'pref-row');
      const lbl = node('div', 'pref-row-label');
      lbl.append(node('strong', '', name + ' · ' + meta.role), node('span', '', locObj ? (locObj.location + (locObj.reason ? ' · ' + locObj.reason : '')) : '当前行踪未记'));
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
    if (chipItems.length) {
      const chips = node('div', 'status-chip-row');
      for (const it of chipItems) {
        const chip = node('span', 'status-chip');
        const display = it.bool === true ? '是' : it.bool === false ? '否' : it.raw;
        chip.append(node('span', '', it.key), node('b', '', display));
        chips.append(chip);
      }
      body.append(chips);
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
        + (curTask.item_desc ? '\n奖励：' + curTask.item_desc : '')
        + (curTask.issue_round ? '\n发布回合：第 ' + curTask.issue_round + ' 回合' : '');
      qCard.append(head, node('div', 'quest-meta', metaText));

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
      emptyQ.append(icon('scroll'), node('p', '', '此刻暂无悬赏委托，随剧情自然触发'));
      pane.append(emptyQ);
    }

    if (w.tasks?.history?.length) {
      const histBox = node('details', 'settlement-details');
      histBox.style.padding = '0 6px';
      histBox.append(node('summary', '', '查看已完成委托（' + w.tasks.history.length + '） ▾'));
      for (const h of w.tasks.history) histBox.append(node('p', 'muted', h));
      pane.append(histBox);
    }

    // 2. Inventory Section
    if (!w.items?.length) {
      const emptyBag = node('section', 'empty-card');
      emptyBag.append(icon('bag'), node('p', '', '行囊暂为空置，完成委托或触发剧情可获得道具'));
      pane.append(emptyBag);
    } else {
      const grid = node('section', 'item-grid');
      const pg = w.progression;
      for (const item of w.items) {
        const card = node('article', 'item-card');
        const top = node('div', 'item-card-top');
        top.append(node('span', 'item-card-name', item.name), node('span', 'item-qty-pill', '× ' + item.quantity));
        card.append(top);

        const tags = node('div', 'item-tags');
        const status = item.fields?.['当前状态'] || '持有';
        tags.append(node('span', 'item-tag', status));
        if (item.fields?.['类型']) tags.append(node('span', 'item-tag', item.fields['类型']));
        if (item.fields?.['剩余时效'] && !['无', ''].includes(item.fields['剩余时效'])) {
          tags.append(node('span', 'item-tag', '剩余 ' + item.fields['剩余时效']));
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
          if (w.cast?.length) {
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
        grid.append(card);
      }
      pane.append(grid);
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

    uiGroup.append(
      mkSwitchRow('视觉主题', '暗夜黑金剧场 / 昼间暖纸护眼', [['noir', '黑金'], ['ivory', '暖纸']], prefs.theme, v => { prefs.theme = v; savePrefs(); }),
      mkSwitchRow('正文字号', '适应移动端阅读舒适度', [['normal', '标准'], ['large', '大字']], prefs.font, v => { prefs.font = v; savePrefs(); }),
      mkSwitchRow('触感微振', '点按剧情与抉择时轻振反馈', [[true, '开启'], [false, '关闭']], prefs.haptics, v => { prefs.haptics = v; savePrefs(); }),
      mkSwitchRow('人物氛围光影', '随在场主角柔和变换幕后光影', [[true, '开启'], [false, '静默']], prefs.backdrop, v => { prefs.backdrop = v; savePrefs(); })
    );
    pane.append(uiGroup);

    // 2. Audio & Bridge Operations
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
      resting: resting(),
      bridge: snapshot?.bridge_connected,
      model: snapshot?.bridge_model?.model_id,
      w: w ? {
        loc: w.location,
        cast: w.cast,
        presence: w.presence,
        panels: w.panels,
        items: w.items,
        tasks: w.tasks,
        interaction: w.interaction,
        prog: w.progression
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
    const tabTitles = { host: '主角档案', roster: '人物羁绊', map: '城市坐标', bag: '行囊与委托', system: '系统设定' };
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
    else box.append(renderSystemTab());

    box.scrollTop = prevTab === activeHubTab ? prevScroll : 0;
  }

  function openHub(tab = 'host', charName = '') {
    haptic(8);
    activeHubTab = tab;
    if (charName) selectedChar = charName;
    worldSignature = '';
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

  function latest() {
    const el = $('stream');
    el.scrollTo({ top: el.scrollHeight, behavior: reducedMotion() ? 'instant' : 'smooth' });
    $('jump').hidden = true;
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
    const list = timeline(historyFilter);
    if (list.length) {
      $('historyList').replaceChildren(...list);
    } else {
      const emp = node('div', 'empty-card');
      emp.append(icon('scroll'), node('p', '', '当前筛选条件下暂无剧情记录'));
      $('historyList').replaceChildren(emp);
    }
  }

  function render() {
    const w = snapshot?.world, p = snapshot?.playback;
    $('policyNote').textContent = progression() ? 'A 5 · B 10 · C 15 体力 · 自定义暂扣15退差' : '按设定与存档推进 · 本段读完后抉择';
    $('sceneTitle').textContent = w?.location || '正在回到现场';
    $('sceneMeta').textContent = w ? (w.cast.length ? w.cast.join(' · ') + ' 在场' : '此刻独处') : '读取存档中…';
    $('revision').textContent = w ? w.interaction.count + ' 段已存剧情' : '';

    // Dock notification dots
    if ($('dockRosterDot')) $('dockRosterDot').hidden = !(w?.cast?.length > 0);
    if ($('dockBagDot')) $('dockBagDot').hidden = !(w?.tasks?.current || w?.items?.length > 0);

    const sig = cache.epoch + ':' + history.map(t => t.id + ':' + t.messages.length + ':' + (t.handoff || '') + ':' + !!t.settlement).join('|');
    if (sig !== signature) {
      const stream = $('stream');
      const near = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 140;
      const top = stream.scrollTop;
      signature = sig;
      const nodes = timeline('all');
      $('messages').replaceChildren(...nodes);
      $('messageCount').textContent = String(nodes.length);
      lastSpeaker = history.flatMap(t => t.messages).filter(m => m.speaker).at(-1)?.speaker || '';
      if (near) latest();
      else {
        stream.scrollTop = top;
        $('jump').hidden = false;
      }
      if ($('historyDialog').open) renderHistoryDialog();
    }

    $('older').hidden = !hasOlder;
    $('empty').hidden = !!p?.segment_id;

    // Cast Medallion Dock
    const names = w?.cast || [];
    if ($('cast').dataset.names !== names.join('|')) {
      $('cast').dataset.names = names.join('|');
      $('cast').replaceChildren(...names.map(name => {
        const b = node('button', 'person-button');
        b.type = 'button';
        b.dataset.name = name;
        b.setAttribute('aria-label', '查看' + name + '立绘与档案');

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
        b.onclick = () => { haptic(10); showPortrait(name); };
        return b;
      }));
    }
    $('cast').querySelectorAll('button').forEach(b => {
      b.setAttribute('aria-current', String(b.dataset.name === lastSpeaker));
    });

    updateBackdrop();

    // Decision Choice Cards
    const turn = current(), decision = turn?.decision, decisionKey = p?.completed ? turn?.id : '';
    if ($('choices').dataset.key !== decisionKey) {
      $('choices').dataset.key = decisionKey || '';
      $('choices').replaceChildren();
      if (decision) {
        $('decisionPrompt').textContent = decision.prompt;
        for (const opt of decision.options) {
          const b = node('button', 'story-option');
          b.type = 'button';
          b.dataset.option = opt.id;

          const seal = node('span', 'option-seal', opt.id);
          const body = node('span', 'option-body');
          body.append(node('span', 'option-label', LABELS[opt.id] || opt.id), node('span', 'option-text', opt.text));
          b.append(seal, body);

          if (progression()) {
            const cost = node('span', 'option-cost');
            cost.append(icon('energy', 'chip-svg'), node('span', '', String(COSTS[opt.id])));
            b.append(cost);
          }

          b.onclick = () => {
            haptic(14);
            void enqueue(opt.text, null, opt.id);
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
        .filter(i => i.fields['当前状态'] === '仓库中' && ['', '无', '未使用', '徐志北'].includes(i.fields['使用对象']))
        .map(i => [i.id, i.name + ' × ' + i.quantity]));
      options('recoveryItem', [
        ['', '请选择恢复道具'],
        ...w.items
          .filter(i => i.fields['当前状态'] === '仓库中'
            && /^host_stamina:[1-9]\d*$/.test(i.fields['系统效果'] || '')
            && ['', '无', '未使用', '徐志北'].includes(i.fields['使用对象']))
          .map(i => [i.id, i.name + ' × ' + i.quantity])
      ]);
    }

    renderSettlement();
    renderWorld(false);
    controls();
    sizing();
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

  function absorb(fresh) {
    if (cache.epoch && cache.epoch !== fresh.save_epoch) {
      cache = { epoch: fresh.save_epoch, draft: '', pending: null, voice: cache.voice };
      $('input').value = '';
      history = [];
      signature = '';
      worldSignature = '';
      olderCursor = null;
      missing = false;
      mismatch = false;
      error = '已切换至新档，旧进度与行动已隔离。';
    }
    if (snapshot?.playback?.segment_id !== fresh.playback?.segment_id) {
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
      fresh.history.forEach(t => map.set(t.id, t));
      history = [...map.values()].sort((a, b) => a.sequence - b.sequence);
    }
    if (!audioMessage && fresh.playback?.revealed) {
      const turn = history.find(t => t.id === fresh.playback.segment_id);
      const i = fresh.playback.revealed - 1;
      if (turn?.messages[i]) audioMessage = { m: turn.messages[i], id: turn.id + ':' + i };
    }
    if (olderCursor === null) hasOlder = fresh.has_older;
    save();
    render();
  }

  async function restore() {
    if (posting || polling || progressing) return;
    polling = true;
    controls();
    try {
      const fresh = await api('live');
      online = true;
      error = '';
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
    }
  }

  async function advance(tapCoords = null) {
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
      await restore();
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
      ...(snapshot.bridge_model ? { model_key: snapshot.bridge_model.key } : {}),
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
      renderWorld(true);
    };
  });

  $('dockHistoryBtn').onclick = () => { haptic(8); renderHistoryDialog(); $('historyDialog').showModal(); };
  $('history').onclick = () => { haptic(8); renderHistoryDialog(); $('historyDialog').showModal(); };
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
    finally { posting = false; await restore(); }
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
  $('checkPending').onclick = restore;
  $('resendPending').onclick = dispatch;
  $('editPending').onclick = () => {
    if (!cache.pending || !missing || mismatch || posting || polling) return;
    cache.draft = [cache.pending.action, cache.draft].filter(Boolean).join('\n');
    cache.pending = null;
    $('input').value = cache.draft;
    save();
    controls();
  };
  $('retry').onclick = async () => {
    if (baseBlocked()) return;
    haptic(12);
    posting = true;
    controls();
    try { await api('tasks/' + encodeURIComponent(snapshot.task.request_id) + '/retry', snapshot.bridge_model ? { model_key: snapshot.bridge_model.key } : {}); }
    catch (e) { error = e.message; }
    finally { posting = false; await restore(); }
  };

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
      await restore();
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
      finally { posting = false; await restore(); }
    };
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
  document.querySelectorAll('[data-file]').forEach(b => {
    b.onclick = () => { haptic(8); showPortrait(portraitName, b.dataset.file); };
  });

  $('jump').onclick = () => { haptic(8); latest(); };
  $('stream').addEventListener('scroll', () => {
    if ($('stream').scrollHeight - $('stream').scrollTop - $('stream').clientHeight < 70) {
      $('jump').hidden = true;
    }
  });

  function sizing() {
    document.documentElement.style.setProperty('--bottom', Math.ceil($('composer').getBoundingClientRect().height) + 'px');
  }
  if (window.ResizeObserver) new ResizeObserver(sizing).observe($('composer'));

  function viewport() {
    const v = window.visualViewport;
    const kb = Math.max(0, innerHeight - v.height - v.offsetTop);
    document.documentElement.style.setProperty('--keyboard', kb + 'px');
    document.body.classList.toggle('kb-open', kb > 120);
    sizing();
  }
  if (window.visualViewport) {
    visualViewport.addEventListener('resize', viewport);
    visualViewport.addEventListener('scroll', viewport);
  }
  window.addEventListener('resize', sizing);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopVoice();
    else void restore();
  });
  window.addEventListener('pagehide', () => {
    stopVoice();
    urls.clear();
  });

  applyPrefs();
  $('input').value = cache.draft;
  save();
  render();
  void restore();
  setInterval(() => { if (!document.hidden) void restore(); }, 2500);
})();

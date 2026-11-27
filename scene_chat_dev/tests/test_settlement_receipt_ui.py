"""Unit, E2E, and Node-VM frontend tests for upgraded settlement receipt:
- Visible resulting values (`+delta -> after`) on reward pills without silent 6-item cap
- Extended non-panel numeric deltas (`亲密耐力`, `宿主欲望`, 5-zone `body_dev`, `警惕`, `发现等级`)
- Auxiliary `state_notes` (buffs, latent pregnancy, keepsakes, dev milestones, stealth/device risk, attire, traces, inter-heroine, micro-states)
- Bugfixes for object-form `intel_consumed`, `shop_rejected`, boolean `怀孕`, and multi `pending_items`
- Strict dark-box exclusion (`npc_mind.resentment`, `last_shift_kind`, vigilance `发现几率`)
"""
from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
import injection_core as ic
import round_runtime as rr
import save_store
import story_progression as sp
import story_service as ss
from test_dual_stage_runtime import _make_workspace, _fg_script, _settlement_payload
from test_stat_tension_and_subtext import _audit_for


class SettlementReceiptUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_workspace(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_state_deltas_covers_all_non_panel_stats_and_excludes_dark_box(self):
        st_before, _, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        st_after = copy.deepcopy(st_before)

        # 1. Host intimate dual-pool
        st_after['intimate']['host_phys']['vigor'] = 88
        st_after['intimate']['host_phys']['desire'] = 42
        # 2. Heroine body_dev
        st_after['intimate']['body_dev']['苏婉青']['chest'] = 24
        st_after['intimate']['body_dev']['沈知韫']['foot'] = 12
        # 3. Vigilance (including hidden 发现几率 which MUST NOT appear!)
        st_after['vigilance']['目标']['苏婉青']['警惕'] = 24
        st_after['vigilance']['目标']['苏婉青']['发现'] = 2
        st_after['vigilance']['目标']['苏婉青']['发现几率'] = 65
        st_after['vigilance']['位置'] = '市中心顶层公寓'
        # 4. Buffs (new buff mounted)
        st_after['buffs']['苏婉青'] = [
            {'name': '持续_体液锁定', 'turns': 24, 'effect': '体内余温锁底>=85'},
        ]
        # 5. Latent pregnancy & masturbation trace
        st_after['mechanics']['pregnancy_latent_until']['苏婉青'] = 4
        st_after['mechanics']['masturbation_trace']['沈知韫'] = 2
        # 6. Attire, traces, inter_heroine, counters, micro_states
        st_after['intimate']['attire']['苏婉青']['state'] = 'disheveled'
        st_after['intimate']['traces']['苏婉青'] = [
            {'kind': '指痕潮红', 'desc': '腕侧留有浅红指印', 'turns': 3, 'visible': True},
        ]
        st_after['intimate']['inter_heroine']['沈知韫->苏婉青'] = 1
        st_after['counters']['空耗_连续未纾解_苏婉青'] = 1
        st_after['micro_states']['苏婉青']['confusion_debt'] = True
        # 7. Dark-box fields mutated -> MUST NEVER appear in extra_changes or state_notes!
        st_after['npc_mind']['苏婉青']['resentment'] = 45
        st_after['npc_mind']['苏婉青']['last_shift_kind'] = 'true_friction'

        im = {
            'dev_milestones': [{'heroine': '苏婉青', 'zone': 'chest', 'label': '胸乳', 'level': 2}],
            'synced_climax': True,
            'keepsakes_added': [{'id': 'KS-001', 'owner': '苏婉青', 'name': '蕾丝丝袜'}],
            'charm_penalty_reasons': ['体能透支累倒'],
            'stealth_alert': True,
            'high_risk_devices': [{'id': 'I-01', 'name': '微型窃听器', 'location': '市中心顶层公寓', 'spot': '灯座', 'detected_risk': 72}],
        }

        extra, notes = sp.collect_state_deltas(st_before, st_after, intimate_meta=im)
        by_key = {(c['target'], c['attribute']): c for c in extra}

        self.assertEqual(by_key[('系统宿主', '亲密耐力')]['after'], 88)
        self.assertEqual(by_key[('系统宿主', '亲密耐力')]['delta'], -12)
        self.assertEqual(by_key[('系统宿主', '宿主欲望')]['after'], 42)
        self.assertEqual(by_key[('苏婉青', '胸乳开发')]['after'], 24)
        self.assertEqual(by_key[('沈知韫', '玉足开发')]['after'], 12)
        self.assertEqual(by_key[('苏婉青', '警惕')]['after'], 24)
        self.assertEqual(by_key[('苏婉青', '发现等级')]['after'], 2)

        kinds = {n['kind'] for n in notes}
        for expected_kind in (
            'vigilance_pos', 'buff', 'pregnancy_latent', 'masturbation_trace',
            'dev_milestone', 'synced_climax', 'keepsake', 'charm_penalty',
            'stealth_alert', 'device_risk', 'attire', 'trace', 'inter_heroine',
            'unrelieved', 'micro_state',
        ):
            self.assertIn(expected_kind, kinds, f'Missing state_note kind: {expected_kind}')

        # Dark-box isolation checks
        dumped = json.dumps({'extra': extra, 'notes': notes}, ensure_ascii=False)
        self.assertNotIn('resentment', dumped)
        self.assertNotIn('last_shift_kind', dumped)
        self.assertNotIn('发现几率', dumped)
        self.assertNotIn('65', dumped)

    def test_e2e_apply_staged_emits_extended_changes_and_state_notes(self):
        app = Flask(__name__)
        ss.register_story_routes(app, self.root)
        client = app.test_client()
        token = client.get('/api/story/bridge-info').get_json()['token']
        cli_h = {'X-Story-Client': '1'}
        wrk_h = {'X-Story-Bridge': token}
        model = {
            'key': '["CHAT","prov","gemini-4"]',
            'function_type': 'CHAT', 'provider_id': 'prov', 'model_id': 'gemini-4',
            'provider_name': 'Prov', 'pricing_configured': True,
        }

        # Put host & Su Wanqing alone in apartment with intimate warm-up
        st, ms, _ = save_store.load_bundle(self.root, sync_txt_drift=True)
        st['presence']['徐志北'] = {'location': '市中心顶层公寓', 'state': '与苏婉青独处'}
        st['presence']['苏婉青'] = {'location': '市中心顶层公寓', 'state': '客卧'}
        st['presence']['沈知韫'] = {'location': '徐家主宅', 'state': '常住'}
        st['presence']['徐念薇'] = {'location': '江城大学', 'state': '上课'}
        st['panels']['苏婉青'].update({'好感': 72, '羞耻': 80, '欲望': 46, '堕落': 8, '体力': 90})
        st['intimate']['privacy'] = 'locked_private'
        st['intimate']['present_actors'] = ['苏婉青']
        save_store.save_bundle(self.root, st, ms)

        def run_turn(action_text, fg_text, settle_obj, opt_id='CUSTOM', is_fresh=False, seq=0, z0='', z1='', stamp=100):
            live = client.get('/api/story/live').get_json()
            hist = live.get('history') or []
            sel = {'segment_id': '', 'option_id': 'BEGIN'} if (opt_id == 'BEGIN' or not hist) else {
                'segment_id': (live.get('playback') or {}).get('segment_id') or hist[-1].get('id', ''),
                'option_id': opt_id,
            }
            r_t = client.post('/api/story/tasks', headers=cli_h, json={
                'request_id': f'req-ui-{stamp}',
                'base_revision': live['revision'], 'save_epoch': live['save_epoch'],
                'action': '继续当前剧情' if opt_id == 'BEGIN' else action_text,
                'entry_mode': 'live_interaction', 'selection': sel,
            })
            self.assertEqual(r_t.status_code, 200, r_t.get_json())
            c = client.post('/api/story/worker/claim', headers=wrk_h, json={'model': model}).get_json()['task']
            mat = client.post(f"/api/story/worker/{c['request_id']}/material", headers=wrk_h, json={
                'lease': c['lease'], 'chat_id': 'c-ui', 'participant_id': 'p-ui',
                'delivery_version': 2, 'protocol_mode': 'dual_stream_v2',
                'synced_zone0_sha256': z0, 'synced_zone1_sha256': z1,
                'last_committed_sequence': seq, 'is_fresh_session': is_fresh,
            }).get_json()
            r_res = client.post(f"/api/story/worker/{c['request_id']}/result", headers=wrk_h, json={
                'lease': c['lease'],
                'text': json.dumps({'dual_stage_version': 1, 'foreground_text': fg_text, 'settlement': settle_obj}, ensure_ascii=False),
                'conversation_audit': _audit_for(self.root, mat, chat_id='c-ui', card_id='p-ui', stamp=stamp),
                'timing': {'generation_ms': 500, 'settlement_ms': 250, 'preflight_ms': 0, 'generation_passes': 1, 'settlement_passes': 1, 'settlement_model_id': 'gemini-flash'},
                'allow_settlement_retry': False,
            })
            self.assertEqual(r_res.status_code, 200, r_res.get_json())
            self.assertEqual(r_res.get_json()['task']['status'], 'committed', r_res.get_json())
            live_a = client.get('/api/story/live').get_json()
            pb = live_a.get('playback') or {}
            if pb and not pb.get('completed'):
                sid, tot = pb['segment_id'], int(pb.get('total') or 0)
                for r_i in range(int(pb.get('revealed') or 0) + 1, tot + 1):
                    live_a = client.post('/api/story/live/progress', headers=cli_h, json={
                        'save_epoch': live_a['save_epoch'], 'segment_id': sid, 'revealed': r_i, 'completed': False,
                    }).get_json()
                live_a = client.post('/api/story/live/progress', headers=cli_h, json={
                    'save_epoch': live_a['save_epoch'], 'segment_id': sid, 'revealed': tot, 'completed': True,
                }).get_json()
            return mat, live_a

        fg0 = _fg_script(speaker='苏婉青', line='志北，客卧里有些闷，先坐会儿吧。')
        s0 = _settlement_payload(category='SYSTEM', conditions=None, clock_time='22:10')
        mat0, _ = run_turn('继续当前剧情', fg0, s0, opt_id='BEGIN', is_fresh=True, stamp=100)

        fg1 = (
            '[N] 药膏的微热顺着她指尖蔓延。\n'
            '[A:徐志北] 你顺势扶住她微凉的肩背，掌心贴着她轻颤的腰侧慢慢摩挲。\n'
            '[A:苏婉青] 苏婉青耳尖泛红，呼吸发软却没有真的推开，任由你的掌心停在腰间。\n'
            '[D:苏婉青] 别闹了……衣襟都要弄乱了。\n'
            '---DECISION---\n'
            'PROMPT: 她气息已乱，你打算怎么继续？\n'
            'A: 退开半步帮她整理衣领。\n'
            'B: 放轻动作低声安抚她的情绪。\n'
            'C: 顺势更贴近她颈侧试探。\n'
        )
        s1 = _settlement_payload(
            category='C',
            conditions={
                'intensity': 'C', 'effective_progress': True, 'scene': '市中心顶层公寓',
                'npc': '苏婉青', 'action_changed': True, 'stress_signals': 1, 'breakout_triggered': [],
            },
            clock_time='22:20',
        )
        s1['resolution']['basis'] = '客卧独处轻度暧昧接触并引发欲拒还迎与情绪升温。'
        s1['resolution']['events'] = [
            {'group': 'shame_events', 'target': '苏婉青', 'tags': [ic._event_tag('SHAME_01')], 'evidence': '掌心贴着她轻颤的腰侧慢慢摩挲'},
            {'group': 'affection_events', 'target': '苏婉青', 'tags': [ic._event_tag('AFFECTION_12')], 'evidence': '呼吸发软却没有真的推开'},
            {'group': 'ds_events', 'target': '苏婉青', 'tags': [ic._event_tag('DS_04')], 'evidence': '药膏的微热顺着她指尖蔓延'},
        ]
        s1['resolution']['scene_state'] = {
            'privacy': 'locked_private',
            'attire_updates': {'苏婉青': {'state': 'disheveled'}},
            'body_acts': {'苏婉青': ['chest']},
            'keepsake_adds': [{'owner': '苏婉青', 'name': '真丝发带', 'kind': 'accessory', 'method': 'taken_intimate'}],
        }
        s1['resolution']['memory'] = {'fact': '客卧独处暧昧试探，苏婉青未真推开。', 'anchor_ops': [], 'chronicle_digest': ''}
        _, live1 = run_turn(
            '俯身贴近并轻抚她腰侧试探', fg1, s1,
            seq=1, z0=mat0['zone0_sha256'], z1=mat0['zone1_sha256'], stamp=200,
        )
        settle = live1['settlement']
        self.assertIsNotNone(settle)
        ch_map = {(c['target'], c['attribute']): c for c in settle['changes']}
        self.assertIn(('苏婉青', '好感'), ch_map)
        self.assertEqual(ch_map[('苏婉青', '好感')]['after'], 73)
        self.assertIn(('苏婉青', '胸乳开发'), ch_map)
        self.assertGreater(ch_map[('苏婉青', '胸乳开发')]['after'], 0)
        self.assertIn(('系统宿主', '宿主欲望'), ch_map)
        self.assertGreater(ch_map[('系统宿主', '宿主欲望')]['after'], 0)
        self.assertIn('state_notes', settle)
        note_kinds = {n['kind'] for n in settle['state_notes']}
        self.assertIn('attire', note_kinds)
        self.assertIn('keepsake', note_kinds)
        self.assertIn('micro_state', note_kinds)
        # Ensure zero dark-box leak in live settlement
        settle_json = json.dumps(settle, ensure_ascii=False)
        self.assertNotIn('resentment', settle_json)
        self.assertNotIn('last_shift_kind', settle_json)
        self.assertNotIn('发现几率', settle_json)

    def test_frontend_settlement_card_renders_after_values_all_pills_and_fixes_bugs(self):
        js_probe = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const src = fs.readFileSync(process.argv[1], 'utf8');

// Extract needed functions from story_client.js IIFE cleanly by evaluating in a minimal mock DOM sandbox
function makeEl(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    className: '',
    textContent: '',
    attrs: {},
    style: {},
    dataset: {},
    children: [],
    hidden: false,
    classList: {
      toggle(c, force) { return !!force; },
      add(...cs) { el.className = (el.className + ' ' + cs.join(' ')).trim(); }
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    append(...items) {
      for (const it of items) {
        if (it !== null && it !== undefined) this.children.push(it);
      }
    },
    replaceChildren(...items) { this.children = []; this.append(...items); },
    allText() {
      let s = this.textContent || '';
      for (const c of this.children) s += typeof c === 'string' ? c : (c.allText ? c.allText() : '');
      return s;
    },
    findAll(pred, out = []) {
      if (pred(this)) out.push(this);
      for (const c of this.children) {
        if (c && typeof c === 'object' && c.findAll) c.findAll(pred, out);
      }
      return out;
    }
  };
  return el;
}

const iconStart = src.indexOf('  function icon(');
const iconEnd = src.indexOf('  function renderSceneVector(');
const settleStart = src.indexOf('  function rewardIconFor(');
const settleEnd = src.indexOf('  function renderSettlement(');
assert.ok(iconStart > 0 && iconEnd > iconStart, 'icon() bounds not found');
assert.ok(settleStart > 0 && settleEnd > settleStart, 'settlementCard() bounds not found');

const snippet = src.slice(iconStart, iconEnd) + '\n' + src.slice(settleStart, settleEnd) + '\nthis.settlementCard = settlementCard; this.rewardPillTone = rewardPillTone;';
const sandbox = {
  settlementFolded: false,
  settlementDismissedId: '',
  shopCatalog: null,
  haptic() {},
  sizing() {},
  openHub() {},
  $: () => makeEl('div'),
  node(tag, cls = '', text = '') {
    const el = makeEl(tag);
    el.className = cls;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  },
  svgEl(tag, attrs = {}) {
    const el = makeEl(tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  },
};
vm.runInNewContext(snippet, sandbox);

const richSettlement = {
  request_id: 'req-1',
  kind: 'action',
  reserved: 15,
  refunded: 5,
  net_cost: 10,
  stamina_before: 80,
  stamina_after: 70,
  phase: 'ready',
  changes: [
    { target: '系统宿主', attribute: '体力', before: 80, after: 70, delta: -10 },
    { target: '苏婉青', attribute: '好感', before: 41, after: 42, delta: 1 },
    { target: '苏婉青', attribute: '欲望', before: 50, after: 61, delta: 11 },
    { target: '苏婉青', attribute: '羞耻', before: 82, after: 79, delta: -3 },
    { target: '苏婉青', attribute: '胸乳开发', before: 20, after: 28, delta: 8 },
    { target: '苏婉青', attribute: '警惕', before: 10, after: 24, delta: 14 },
    { target: '沈知韫', attribute: '警惕', before: 12, after: 7, delta: -5 },
    { target: '苏婉青', attribute: '发现等级', before: 1, after: 2, delta: 1 },
    { target: '系统宿主', attribute: '亲密耐力', before: 100, after: 98, delta: -2 },
    { target: '系统宿主', attribute: '宿主欲望', before: 24, after: 38, delta: 14 },
    { target: '系统宿主', attribute: '魅力', before: 75, after: 76, delta: 1 },
    { target: '苏婉青', attribute: '怀孕', before: false, after: true, delta: 1 },
  ],
  state_notes: [
    { kind: 'buff', level: 'info', text: '苏婉青 生效状态：[持续_体液锁定]（剩 24 回合）' },
    { kind: 'pregnancy_latent', level: 'milestone', target: '沈知韫', text: '沈知韫 受孕暗骰命中：进入早孕着床潜伏期（预计第 4 天显影）' },
    { kind: 'vigilance_pos', level: 'warn', text: '徐承邺行踪变化：外地 → 市中心顶层公寓' },
  ],
  intimate_meta: {
    synced_climax: true,
    keepsakes_added: [{ id: 'KS-001', owner: '苏婉青', name: '黑丝长袜' }],
    dev_milestones: [{ heroine: '苏婉青', zone: 'chest', label: '胸乳', level: 2 }],
    stealth_alert: true,
  },
  intel_consumed: { id: 'INTEL-002', name: '眼线密报', target: '苏婉青', effect_summary: '揭穿眼线身份' },
  shop_rejected: [{ name: '好感药水', reason: '禁止直接增减属性' }],
  task_after: { pending_item: '真丝眼罩', pending_items: ['真丝眼罩', '精油礼盒'] },
  clock: { day: 1, time: '22:45' },
};

const card = sandbox.settlementCard(richSettlement, true, 'req-1');
const bodyList = card.findAll(el => el.className === 'reward-list')[0];
assert.ok(bodyList, 'reward-list missing');
const bodyPills = bodyList.findAll(el => (el.className || '').includes('reward-pill') || (el.className || '').includes('settlement-action-pill'));
const bodyPillTexts = bodyPills.map(p => p.allText());

// Verify recommended "+delta → after" format on expanded pills & zero 6-item silent truncation (all 11 non-host-stamina changes rendered!)
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 好感 +1') && t.includes('→ 42')), 'Missing 好感 +1 → 42: ' + JSON.stringify(bodyPillTexts));
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 欲望 +11') && t.includes('→ 61')), 'Missing 欲望 +11 → 61');
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 羞耻 -3') && t.includes('→ 79')), 'Missing 羞耻 -3 → 79');
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 胸乳开发 +8') && t.includes('→ 28')), 'Missing 胸乳开发 +8 → 28');
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 警惕 +14') && t.includes('→ 24')), 'Missing 警惕 +14 → 24');
assert.ok(bodyPillTexts.some(t => t.includes('亲密耐力 -2') && t.includes('→ 98')), 'Missing 亲密耐力 -2 → 98');
assert.ok(bodyPillTexts.some(t => t.includes('宿主欲望 +14') && t.includes('→ 38')), 'Missing 宿主欲望 +14 → 38');
assert.ok(bodyPillTexts.some(t => t.includes('魅力 +1') && t.includes('→ 76')), 'Missing 魅力 +1 → 76');
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 确诊怀孕')), 'Pregnancy should show 确诊怀孕 not +1');
assert.ok(!bodyPillTexts.some(t => t.includes('怀孕 +1')), 'Must not show 怀孕 +1');
assert.ok(bodyPillTexts.some(t => t.includes('同频绝顶')), 'Missing synced_climax pill');
assert.ok(bodyPillTexts.some(t => t.includes('新增珍藏 +1')), 'Missing keepsakes pill');
assert.ok(bodyPillTexts.some(t => t.includes('苏婉青 胸乳 Lv.2')), 'Missing dev_milestone pill');
assert.ok(bodyPillTexts.some(t => t.includes('沈知韫 早孕潜伏')), 'Missing latent pregnancy pill');
assert.ok(bodyPillTexts.some(t => t.includes('隔墙声响预警')), 'Missing stealth_alert pill');
assert.ok(bodyPillTexts.some(t => t.includes('待领委托奖励 ×2')), 'Missing multi pending rewards count');

// Verify semantic pill tones
const vigUp = bodyPills.find(p => p.allText().includes('苏婉青 警惕 +14'));
const vigDown = bodyPills.find(p => p.allText().includes('沈知韫 警惕 -5'));
const shameDown = bodyPills.find(p => p.allText().includes('苏婉青 羞耻 -3'));
assert.ok(vigUp.className.includes('is-negative'), 'Vigilance increase should be negative/danger');
assert.ok(vigDown.className.includes('is-jade'), 'Vigilance decrease should be jade/relief');
assert.ok(shameDown.className.includes('is-shield') && !shameDown.className.includes('is-negative'), 'Shame drop should be shield not negative');

// Verify folded mini ribbon shows compact +delta→after and +N项 overflow indicator
const inlineWrap = card.findAll(el => el.className === 'settlement-inline-pills')[0];
assert.ok(inlineWrap, 'settlement-inline-pills missing');
const inlineText = inlineWrap.allText();
assert.ok(inlineText.includes('+8项'), 'Folded ribbon should show +8项 overflow for 11 rewards: ' + inlineText);

// Verify details panel includes fixed intel_consumed object, shop_rejected, and state_notes
const detailsEl = card.findAll(el => el.tagName === 'DETAILS')[0];
const detailsText = detailsEl.allText();
assert.ok(detailsText.includes('消耗情报：「眼线密报」（对象：苏婉青） · 揭穿眼线身份'), 'Object intel_consumed must render: ' + detailsText);
assert.ok(detailsText.includes('商城定制拦截：好感药水：禁止直接增减属性'), 'shop_rejected must render');
assert.ok(detailsText.includes('生效状态：[持续_体液锁定]（剩 24 回合）'), 'buff state_note must render');
assert.ok(detailsText.includes('未孕 → 确诊怀孕'), 'Pregnancy detail should render human-readable transition');

// Legacy fallback check (receipt with intimate_meta but no state_notes field)
const legacy = {
  request_id: 'req-old', kind: 'action', reserved: 5, refunded: 0, net_cost: 5,
  stamina_before: 90, stamina_after: 85, phase: 'ready', changes: [],
  intimate_meta: { synced_climax: true, charm_penalty_reasons: ['目击实锤失态'] },
};
const legacyCard = sandbox.settlementCard(legacy, false, 'req-old');
const legacyDetail = legacyCard.findAll(el => el.tagName === 'DETAILS')[0].allText();
assert.ok(legacyDetail.includes('达成同频绝顶') && legacyDetail.includes('魅力折损原因：目击实锤失态'), 'Legacy intimate_meta fallback failed');

console.log('NODE_SETTLEMENT_UI_OK');
"""
        proc = subprocess.run(
            ['node', '-e', js_probe, str(ROOT / 'story_client.js')],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, f'STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}')
        self.assertIn('NODE_SETTLEMENT_UI_OK', proc.stdout)

    def test_css_settlement_classes_balanced_and_theme_safe(self):
        css = (ROOT / 'story_client.css').read_text(encoding='utf-8')
        self.assertEqual(css.count('{'), css.count('}'))
        for sel in (
            '.reward-pill .pill-after',
            '.reward-pill.is-jade',
            '.reward-pill.is-shield',
            '.reward-pill.is-charm',
            '.reward-pill.is-vigilance',
            '.reward-pill.is-more',
            '.settlement-details p.is-milestone',
            '.settlement-details p.is-warn',
        ):
            self.assertIn(sel, css, f'Missing CSS rule {sel}')


if __name__ == '__main__':
    unittest.main()

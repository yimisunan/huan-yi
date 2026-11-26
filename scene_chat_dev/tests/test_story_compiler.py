"""Unit tests for read-only deterministic context projection, streaming parser, and guardrails."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import round_runtime as rr
import story_compiler as sc


class StoryCompilerTests(unittest.TestCase):
    def setUp(self):
        self.memory_text = (ROOT / rr.FILES[0]).read_text(encoding='utf-8')
        self.state = {
            'location': '徐家主宅',
            'cast': ['沈知韫', '徐念薇'],
            'presence': {
                '徐志北': {'location': '徐家主宅', 'reason': '在家'},
                '沈知韫': {'location': '徐家主宅', 'reason': '在客厅'},
                '徐念薇': {'location': '徐家主宅', 'reason': '刚回来'},
                '苏婉青': {'location': '市中心顶层公寓', 'reason': '在顶层公寓'},
            },
            'panels': [
                '[系统宿主] 体力 100 | 积分 50 | 经验值 0 | 魅力 50 | 商业嗅觉 50',
                '[沈知韫] 好感 50 | 羞耻 100 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
                '[徐念薇] 好感 50 | 羞耻 100 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
            ],
            'items': [],
            'tasks': {'current': None, 'history': []},
        }

    def test_compile_relationships_lossless_and_compact(self):
        raw_rel = (ROOT / 'txt文件/关系称谓库.json').read_text(encoding='utf-8')
        compiled = sc.compile_relationships(ROOT, ['沈知韫', '徐念薇'], ['苏婉青'])
        compact = json.dumps(compiled, ensure_ascii=False, separators=(',', ':'))
        # Huge reduction compared to full relationship library / legacy bundle.
        self.assertLess(len(compact), 3500)
        self.assertLess(len(compact), len(raw_rel) * 0.2)
        # Critical secret knowledge boundaries must stay intact.
        self.assertIn('secret_boundaries', compiled)
        self.assertIn('known_only_by', compiled['secret_boundaries'])
        self.assertIn('unknown_by_present', compiled['secret_boundaries'])
        # Present cast forms and beliefs preserved.
        self.assertTrue(compiled['forms'])
        self.assertTrue(compiled['shared'])

        # Full-cast address & self-address boundary checks (no awkward given-name leaks in regular occasions).
        full = sc.compile_relationships(ROOT, ['沈知韫', '苏婉青', '徐念薇', '徐承邺', '次要NPC'])
        forms = full['forms']
        # Younger brother -> elder sister: regular occasions use 二姐/姐/姐姐 only; 念薇 only in intimate after 姐姐.
        zb_nw = forms['徐志北->徐念薇']
        self.assertNotIn('念薇', zb_nw['f'].get('a', []))
        self.assertIn('二姐', zb_nw['f'].get('a', []))
        self.assertNotIn('念薇', zb_nw['r'].get('a', []))
        self.assertIn('姐姐', zb_nw['r'].get('a', []))
        self.assertEqual(zb_nw['i'].get('a'), ['姐姐', '念薇'])
        # Brother-in-law -> sister-in-law & younger brother -> elder brother: kinship only in f/r.
        zb_wq = forms['徐志北->苏婉青']
        self.assertNotIn('婉青', zb_wq['f'].get('a', []))
        self.assertNotIn('婉青', zb_wq['r'].get('a', []))
        self.assertIn('嫂子', zb_wq['f'].get('a', []))
        self.assertEqual(zb_wq['i'].get('a'), ['嫂子', '婉青'])
        zb_cy = forms['徐志北->徐承邺']
        self.assertNotIn('承邺', zb_cy['f'].get('a', []))
        self.assertNotIn('承邺', zb_cy['r'].get('a', []))
        self.assertIn('大哥', zb_cy['f'].get('a', []))
        # Younger sister -> sister-in-law / elder brother: no given-name leak in regular occasions.
        self.assertNotIn('婉青', forms['徐念薇->苏婉青']['f'].get('a', []))
        self.assertNotIn('承邺', forms['徐念薇->徐承邺']['f'].get('a', []))
        # Regular self-address: seniors & peers do not self-refer by given name; intimate retains it.
        self.assertNotIn('念薇', forms['徐念薇->徐志北']['f'].get('s', []))
        self.assertNotIn('婉青', forms['苏婉青->徐志北']['f'].get('s', []))
        self.assertNotIn('知韫', forms['沈知韫->次要NPC'].get('s', []))
        self.assertIn('知韫', forms['沈知韫->徐志北']['i'].get('s', []))
        # Secondary NPCs use formal titles, never given names.
        self.assertNotIn('知韫', forms['次要NPC->沈知韫']['f'].get('a', []))
        self.assertIn('沈董', forms['次要NPC->沈知韫']['f'].get('a', []))
        self.assertNotIn('婉青', forms['次要NPC->苏婉青']['f'].get('a', []))
        self.assertIn('少奶奶', forms['次要NPC->苏婉青']['f'].get('a', []))
        self.assertNotIn('念薇', forms['次要NPC->徐念薇'].get('a', []))
        self.assertIn('徐小姐', forms['次要NPC->徐念薇'].get('a', []))
        # Elder -> junior and spouses still keep natural given-name address.
        self.assertIn('志北', forms['沈知韫->徐志北']['f'].get('a', []))
        self.assertIn('婉青', forms['徐承邺->苏婉青']['f'].get('a', []))
        self.assertIn('承邺', forms['苏婉青->徐承邺']['f'].get('a', []))

    def test_compile_event_catalog_preserves_regex_and_strips_scoring_params(self):
        raw_ev = (ROOT / 'txt文件/事件注册表.json').read_text(encoding='utf-8')
        catalog = sc.compile_event_catalog(ROOT)
        compact = json.dumps(catalog, ensure_ascii=False, separators=(',', ':'))
        self.assertLess(len(compact), len(raw_ev) * 0.15)
        self.assertIn('host_events', catalog)
        self.assertTrue(any('兑换道具_X' in tag for tag in catalog['host_events']))
        self.assertNotIn('base_delta_01', compact)
        self.assertNotIn('extra_delta', compact)

    def test_compile_characters_keeps_100_percent_persona_body(self):
        chars = sc.compile_characters(ROOT, ['沈知韫'], ['苏婉青'])
        self.assertEqual([c['name'] for c in chars], ['沈知韫', '苏婉青', '徐志北'])
        self.assertEqual(chars[0]['scope'], 'present')
        self.assertEqual(chars[1]['scope'], 'referenced_background_offstage')
        self.assertEqual(chars[2]['scope'], 'host')
        # Original persona content is untouched except the repeated boundary footer.
        raw_entries = sc._load_kb_entries(ROOT, '角色类')
        shen_raw = next(item['content'] for item in raw_entries if '※索引key※ char.沈知韫' in item.get('content', ''))
        self.assertGreater(len(chars[0]['body']), len(shen_raw) - 300)
        self.assertNotIn('【正式互动入口适用边界】', chars[0]['body'])

    def test_compile_knowledge_rules_strips_redundancy_and_gates_inactive_subsystems(self):
        fg_rules = sc.compile_knowledge_rules(ROOT, self.state, self.memory_text, '聊聊近况', mode='foreground')
        fg_keys = {b['key'] for b in fg_rules}
        self.assertNotIn('narrative.vigilance', fg_keys)
        self.assertNotIn('sys.pregnancy', fg_keys)
        joined_fg = '\n'.join(b['body'] for b in fg_rules)
        self.assertNotIn('【注册表生成表】', joined_fg)
        self.assertNotIn('【正式互动入口适用边界】', joined_fg)

        # Transient per-turn text does NOT flip Zone 1 vigilance (prevents KV cache thrashing);
        # persistent vigilance state activates narrative.vigilance reliably.
        fg_transient = sc.compile_knowledge_rules(ROOT, self.state, self.memory_text, '查看监视和警惕值', mode='foreground')
        self.assertNotIn('narrative.vigilance', {b['key'] for b in fg_transient})
        vig_mem = self.memory_text.replace('徐承邺位置：外地', '徐承邺位置：徐家住宅')
        fg_vig = sc.compile_knowledge_rules(ROOT, self.state, vig_mem, '聊聊近况', mode='foreground')
        self.assertIn('narrative.vigilance', {b['key'] for b in fg_vig})

        # Stage 2 settlement always keeps sys.pregnancy and sys.vigilance loaded so autonomous Stage 1 events never miss rules.
        st_rules = sc.compile_knowledge_rules(ROOT, self.state, self.memory_text, '闲聊', mode='settlement')
        st_keys = {b['key'] for b in st_rules}
        self.assertIn('sys.pregnancy', st_keys)
        self.assertIn('sys.vigilance', st_keys)

    def test_zone0_zone1_determinism_and_size_reduction(self):
        z0_a = sc.build_zone0_global(ROOT, mode='dual_stream_v2')
        z0_b = sc.build_zone0_global(ROOT, mode='dual_stream_v2')
        self.assertEqual(hashlib.sha256(z0_a.encode()).hexdigest(), hashlib.sha256(z0_b.encode()).hexdigest())

        z1_a = sc.build_zone1_scene(ROOT, self.state, ['沈知韫', '徐念薇'], [], self.memory_text, '打招呼', mode='dual_stream_v2')
        z1_b = sc.build_zone1_scene(ROOT, self.state, ['沈知韫', '徐念薇'], [], self.memory_text, '换一句日常问候', mode='dual_stream_v2')
        self.assertEqual(hashlib.sha256(z1_a.encode()).hexdigest(), hashlib.sha256(z1_b.encode()).hexdigest())

        # Total static system prefix for 2 NPCs stays compact (< 25K chars vs ~120K+ baseline).
        self.assertLess(len(z0_a) + len(z1_a), 26000)

    def test_incremental_user_delta_is_compact(self):
        projection = {'text': '【L1】当前回合核心记忆', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        delta = sc.build_user_delta(
            ROOT, self.state, projection, history=[], new_history_only=[],
            text='坐下来喝茶', selected={'segment_id': 's1', 'option_id': 'A'},
            resolved_op=None, intent_evidence=None, preview_cost={'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '09:10'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, include_full_anchor=False, mode='dual_stream_v2',
        )
        self.assertLess(len(delta), 3000)
        parsed = json.loads(delta)
        self.assertEqual(parsed['anchor'], 'incremental_delta')
        self.assertNotIn('accepted_history', parsed)
        self.assertNotIn('sensory_lens', parsed)
        # Expanded intimate turn regex covers warm/sensual/fetish/item phrases
        for sample in (
            '蹲下替她按揉酸胀的脚踝',
            '轻轻摩挲她修长偏凉的手指',
            '贴近嗅着她发间的沐浴露体香',
            '趁她转身往杯里滴入催情桃露',
            '掌心抹上热感精油轻抚她肩背',
            '替她把滑落的吊带肩带扶回肩头',
            '在主卧镜柜下沿暗中安装针孔摄像头',
        ):
            self.assertTrue(sc._needs_intimate_turn(sample), f'Expected intimate match for: {sample}')

    def test_parse_stream_story_complete_and_partial(self):
        script = (
            '[N] 客厅里的茶雾缓缓散开。\n'
            '[A:沈知韫] 沈知韫放下瓷杯，目光温和地落到你身上。\n'
            '[D:沈知韫] 志北，昨晚睡得怎么样？\n'
            '[D:徐念薇] 哥，你今天怎么起这么早呀？\n'
            '---DECISION---\n'
            'PROMPT: 客厅气氛轻松，你打算如何回应？\n'
            'A: 笑着说睡得不错，顺手替母亲续上半杯热茶。\n'
            'B: 轻轻拍了拍念薇的发顶，问她画展准备得如何。\n'
            'C: 顺势提起公司近期的动向，探听母亲的看法。\n'
        )
        parsed = sc.parse_stream_story(script, allowed_speakers=['沈知韫', '徐念薇'], partial=False)
        self.assertEqual(len(parsed['messages']), 4)
        self.assertEqual(parsed['messages'][0], {'kind': 'narration', 'speaker': '', 'text': '客厅里的茶雾缓缓散开。'})
        self.assertEqual(parsed['messages'][2]['speaker'], '沈知韫')
        self.assertEqual([o['id'] for o in parsed['decision']['options']], ['A', 'B', 'C'])

        # Partial streaming drops incomplete trailing line cleanly.
        partial_raw = '[N] 第一句完整旁白。\n[D:沈知韫] 这句还没打完'
        partial = sc.parse_stream_story(partial_raw, allowed_speakers=['沈知韫'], partial=True)
        self.assertEqual(len(partial['messages']), 1)

        # Player dialogue rejected when allow_player_dialogue=False (silent mode).
        bad_player = '[D:徐志北] 我自己说一句。\n---DECISION---\nPROMPT: p\nA: a\nB: b\nC: c'
        with self.assertRaises(rr.RoundError):
            sc.parse_stream_story(bad_player, allowed_speakers=['沈知韫'], partial=False)

        # Faithful mode allows up to 3 concise muted [D:徐志北] lines and strips any stray Fish tags.
        ok_player = (
            '[A:徐志北] 你接过热茶。\n'
            '[D:徐志北] [whisper] 谢谢，刚巧有些渴了。\n'
            '[D:沈知韫] 慢点喝。\n'
            '---DECISION---\nPROMPT: p\nA: a\nB: b\nC: c'
        )
        parsed_faithful = sc.parse_stream_story(ok_player, allowed_speakers=['沈知韫'], partial=False, allow_player_dialogue=True)
        self.assertEqual(parsed_faithful['messages'][1], {'kind': 'dialogue', 'speaker': '徐志北', 'text': '谢谢，刚巧有些渴了。'})

        too_many_player = (
            '[D:徐志北] 一。\n[D:徐志北] 二。\n[D:徐志北] 三。\n[D:徐志北] 四。\n'
            '---DECISION---\nPROMPT: p\nA: a\nB: b\nC: c'
        )
        with self.assertRaises(rr.RoundError) as ctx_many:
            sc.parse_stream_story(too_many_player, allowed_speakers=['沈知韫'], partial=False, allow_player_dialogue=True)
        self.assertIn('主角代写台词过多', str(ctx_many.exception))

        bad_offstage = '[D:苏婉青] 场外发言。\n---DECISION---\nPROMPT: p\nA: a\nB: b\nC: c'
        with self.assertRaises(rr.RoundError):
            sc.parse_stream_story(bad_offstage, allowed_speakers=['沈知韫'], partial=False, allow_player_dialogue=True)

    def test_parse_stream_story_strips_chinese_prefixes_and_never_glues_narration_into_dialogue(self):
        # Reproduces real deepseek-v4-flash output with `旁白：[N]`, bare `旁白：`, markdown bullets, and inline tags.
        raw = (
            '旁白：[N] 你的掌心落下去，覆在她手背上。\n'
            '人物动作：[A:沈知韫] 她抬眼看了你一眼。\n'
            '[D:沈知韫] [low restrained voice] 手这么凉，还说不困。\n'
            '角色对白：[D:沈知韫] 第三条，对价分两期。\n'
            '旁白：[N] 她抬手用笔帽点了点那一行字。\n'
            '[D:沈知韫] 换作你接手，会怎么压这一截尾款？ 旁白：[N] 她问得很平。\n'
            '- 旁白：冷气还在往下沉。\n'
            '---DECISION---\n'
            '**PROMPT:** 下一步怎么回应？\n'
            '- **A:** 顺着条款问她的想法。\n'
            '- **B:** 轻捏一下她的指尖让她别熬太晚。\n'
            '- **C:** 直接替她合上文件夹。\n'
        )
        parsed = sc.parse_stream_story(raw, allowed_speakers=['沈知韫'], partial=False)
        msgs = parsed['messages']
        self.assertEqual([m['kind'] for m in msgs], ['narration', 'action', 'dialogue', 'dialogue', 'narration', 'dialogue', 'narration', 'narration'])
        self.assertEqual(msgs[0]['text'], '你的掌心落下去，覆在她手背上。')
        self.assertEqual(msgs[2]['text'], '[low restrained voice] 手这么凉，还说不困。')
        self.assertEqual(msgs[3]['text'], '第三条，对价分两期。')
        self.assertEqual(msgs[4], {'kind': 'narration', 'speaker': '', 'text': '她抬手用笔帽点了点那一行字。'})
        self.assertEqual(msgs[5], {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '换作你接手，会怎么压这一截尾款？'})
        self.assertEqual(msgs[6], {'kind': 'narration', 'speaker': '', 'text': '她问得很平。'})
        self.assertEqual(msgs[7], {'kind': 'narration', 'speaker': '', 'text': '冷气还在往下沉。'})
        for m in msgs:
            self.assertNotIn('旁白：', m['text'])
            self.assertNotIn('[N]', m['text'])
        self.assertEqual(parsed['decision']['prompt'], '下一步怎么回应？')
        self.assertEqual(len(parsed['decision']['options']), 3)

    def test_guardrail_check_catches_info_gap_and_residence_conflicts(self):
        # Clean scene passes with zero warnings.
        ok = [{'kind': 'dialogue', 'speaker': '徐念薇', 'text': '哥，今天阳光很好，我们去花园走走吧。'}]
        self.assertEqual(sc.guardrail_check(ROOT, '徐家主宅', ['徐念薇'], ok), {'ok': True, 'warnings': []})

        # Dynamic known_by check: 徐念薇 does NOT know the inheritance/will secret -> hard block.
        leak = [{'kind': 'dialogue', 'speaker': '徐念薇', 'text': '哥，我听说遗嘱和继承权的事全交给大哥了？'}]
        with self.assertRaises(rr.RoundError) as ctx:
            sc.guardrail_check(ROOT, '徐家主宅', ['徐念薇'], leak)
        self.assertIn('信息差红线拦截', str(ctx.exception))

        # Residence boundary check: 苏婉青 must not be described as residing in 徐家主宅.
        res_bad = [{'kind': 'narration', 'speaker': '', 'text': '苏婉青就住在徐家主宅二楼，每天在主宅常住。'}]
        res_out = sc.guardrail_check(ROOT, '徐家主宅', ['沈知韫'], res_bad)
        self.assertTrue(res_out['warnings'], 'Expected Su Wanqing main-manor residence conflict warning')

    def test_parse_stream_story_handles_split_decision_separator_and_variants(self):
        # Exact real-world failure: model inserted a newline between `---` and `DECISION---`.
        real_output = (
            '[N] 冷气从天花出风口直往下沉，桌面上那叠纸的边缘被吹得一起一伏。你把那句“要不要搭把手”问进门缝里，声音不高，落在安静的书房里反倒清楚。\n\n'
            '[A:沈知韫] 她先把红笔帽扣上，才抬起头，视线在你脸上停了一瞬，像在掂量这句话里有几分客气、几分真心。随后她把摊开的并购文件往左边推开半尺，从下面抽出一只薄一些的硬纸文件夹。\n\n'
            '[D:沈知韫] [low restrained voice] 来得正好。你替我拿一下。\n\n'
            '[A:沈知韫] 她半侧过身，一手托着文件夹递过来，另一手还压在文件背脊上。\n\n'
            '[A:徐志北] 你探手过去接，掌心先贴住文件夹底部，把往下滑的几张散页一起兜稳。\n\n'
            '[N] 硬纸板边角在掌心硌出一道折痕，纸面带着空调吹久的干凉。\n\n'
            '[A:沈知韫] 她收回手，指尖在自己袖口边缘捻了一下，又松开。\n\n'
            '[D:沈知韫] 深圳分部递上来的东西。我看了半个晚上，总觉得里头有三处不对。\n\n'
            '[A:沈知韫] 说到“三处”时她抬手按了按眉心，很快又放下来。\n\n'
            '[D:沈知韫] 你从头翻，找三处出来。找错了也不要紧，我要的是你看见的东西。\n\n'
            '[N] 你把文件夹翻过来，里面夹的是对账底稿。\n\n'
            '[D:沈知韫] 明早七点，餐桌上说给我听。\n\n'
            '[A:沈知韫] 她往椅背上靠了一点，手掌搭在扶手上，眼睛看着你手里的文件夹，没有催。\n\n'
            '---\n'
            'DECISION---\n'
            'PROMPT: 她递来的是深圳分部的对账底稿，只说要你找“三处不对”，却没提她自己在哪一行停过笔；翻扣的手机压在文件堆边，屏幕刚才亮过。明早七点的餐桌，是她给这件事定的期限。\n'
            'A: 应下就翻，先从她铅笔圈过又擦掉的那几行问一句，把话题往具体账目上引。\n'
            'B: 把文件夹往桌心挪半尺，就着她的手边摊开，顺势凑近同看，探她为什么把这份东西交给你而不是交给分部。\n'
            'C: 合上文件夹放回桌面，直接点出她按眉心那一下和翻扣手机的动作，问她深圳那边究竟出了什么事。\n'
        )
        parsed = sc.parse_stream_story(real_output, allowed_speakers=['沈知韫'], partial=False)
        self.assertEqual(len(parsed['messages']), 13)
        self.assertEqual(parsed['messages'][-1]['text'], '她往椅背上靠了一点，手掌搭在扶手上，眼睛看着你手里的文件夹，没有催。')
        self.assertNotIn('DECISION', parsed['messages'][-1]['text'])
        self.assertNotIn('---', parsed['messages'][-1]['text'])
        self.assertIn('明早七点的餐桌', parsed['decision']['prompt'])
        self.assertEqual([o['id'] for o in parsed['decision']['options']], ['A', 'B', 'C'])

        # Variant 1: unmarked decision block (no ---DECISION--- at all) + Chinese punctuation + tier labels + bold MOVE.
        unmarked = (
            '[N] 客厅安静下来。\n'
            '[D:沈知韫] 你自己拿主意。\n\n'
            '提示：\n'
            '她在等你给个明确答复。\n'
            'A、先顺着她的话问清楚细节。\n'
            'B · 社交接触：递一杯温水过去，顺手轻触她的手背。\n'
            '**C[MOVE:公司]**：起身告辞，直接去公司查对账单。\n'
        )
        p_unmarked = sc.parse_stream_story(
            unmarked, allowed_speakers=['沈知韫'], partial=False,
            valid_destinations=['徐家主宅', '公司', '大学', '市中心顶层公寓', '工作室'],
            current_location='徐家主宅',
        )
        self.assertEqual(len(p_unmarked['messages']), 2)
        self.assertEqual(p_unmarked['decision']['prompt'], '她在等你给个明确答复。')
        self.assertEqual(p_unmarked['decision']['options'][0]['text'], '先顺着她的话问清楚细节。')
        self.assertEqual(p_unmarked['decision']['options'][1]['text'], '递一杯温水过去，顺手轻触她的手背。')
        self.assertEqual(p_unmarked['decision']['options'][2]['operation'], {'code': 'move_player', 'destination': '公司'})

        # Variant 2: inline separator + omitted PROMPT + bracketed/lowercase options.
        inline_no_prompt = (
            '[A:沈知韫] 她合上文件夹。---DECISION---\n'
            '[a] 问她今晚几点休息。\n'
            '【B】 帮她把桌角的文件理齐。\n'
            '(c) 直接问她刚才谁打的电话。\n'
        )
        p_inline = sc.parse_stream_story(inline_no_prompt, allowed_speakers=['沈知韫'], partial=False)
        self.assertEqual(p_inline['messages'][0]['text'], '她合上文件夹。')
        self.assertTrue(p_inline['decision']['prompt'])
        self.assertEqual([o['id'] for o in p_inline['decision']['options']], ['A', 'B', 'C'])

        # Variant 3: allow_missing_decision returns prose cleanly with reason.
        only_prose = '[N] 书房里只剩钟表轻响。\n[D:沈知韫] 明天再说吧。'
        p_missing = sc.parse_stream_story(only_prose, allowed_speakers=['沈知韫'], partial=False, allow_missing_decision=True)
        self.assertEqual(len(p_missing['messages']), 2)
        self.assertIsNone(p_missing['decision'])
        self.assertIn('未检测到', p_missing['decision_missing_reason'])

        # Preview leak sanitizer cleans legacy plugin leaked suffix without touching prose.
        leaked = '她往椅背上靠了一点，没有催。\n\n---\nDECISION---\nPROMPT: 局面\nA: 一\nB: 二\nC: 三'
        self.assertEqual(sc.strip_preview_decision_leak(leaked), '她往椅背上靠了一点，没有催。')
        self.assertEqual(sc.strip_preview_decision_leak('她往椅背上靠了一点。\n---'), '她往椅背上靠了一点。')

        # Zone 2 delta carries compact dual_stream_v2 output_format anchor.
        projection = {'text': '【L1】当前回合核心记忆', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        delta = json.loads(sc.build_user_delta(
            ROOT, self.state, projection, history=[], new_history_only=[],
            text='坐下', selected={'segment_id': 's1', 'option_id': 'A'},
            resolved_op=None, intent_evidence=None, preview_cost={'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '09:10'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, include_full_anchor=False, mode='dual_stream_v2',
        ))
        self.assertIn('---DECISION---', delta.get('output_format', ''))
        self.assertIn('[D:徐志北]', delta.get('output_format', ''))

    def test_dialogue_action_split_fish_tag_strip_and_trailing_move(self):
        stream = (
            '[A:徐志北] 你把温水放到书桌边，顺口问了句画展哪天开幕。\n'
            '[A:沈知韫] [soft sigh] 她揉了揉眉心。\n'
            '[D:沈知韫] 她端起来抿了一口，没抬眼：“[calm low voice] 几点了，还端着水往书房跑。”\n'
            '[D:徐念薇] “下周三开幕，评审刚换成周教授。”\n'
            '---DECISION---\n'
            'PROMPT: 书房灯光微暗，两人都看着你。\n'
            'A: 顺着画展评审的话题继续聊几句。\n'
            'B: 走近书桌替沈知韫把散乱的画册理好。\n'
            'C: 先告辞去公司核对展厅合同。[MOVE:公司]\n'
        )
        parsed = sc.parse_stream_story(
            stream,
            allowed_speakers=['沈知韫', '徐念薇'],
            partial=False,
            valid_destinations=['徐家主宅', '公司', '大学', '市中心顶层公寓', '工作室'],
            current_location='徐家主宅',
        )
        msgs = parsed['messages']
        self.assertEqual(len(msgs), 5)
        self.assertEqual(msgs[0], {'kind': 'action', 'speaker': '徐志北', 'text': '你把温水放到书桌边，顺口问了句画展哪天开幕。'})
        self.assertEqual(msgs[1], {'kind': 'action', 'speaker': '沈知韫', 'text': '她揉了揉眉心。'})
        self.assertEqual(msgs[2], {'kind': 'action', 'speaker': '沈知韫', 'text': '她端起来抿了一口，没抬眼。'})
        self.assertEqual(msgs[3], {'kind': 'dialogue', 'speaker': '沈知韫', 'text': '[calm low voice] 几点了，还端着水往书房跑。'})
        self.assertEqual(msgs[4], {'kind': 'dialogue', 'speaker': '徐念薇', 'text': '下周三开幕，评审刚换成周教授。'})
        self.assertEqual(parsed['decision']['options'][2]['text'], '先告辞去公司核对展厅合同。')
        self.assertEqual(parsed['decision']['options'][2]['operation'], {'code': 'move_player', 'destination': '公司'})

    def test_settlement_spec_tags_match_registry_and_keys_aligned(self):
        reg = json.loads((ROOT / 'txt文件/事件注册表.json').read_text(encoding='utf-8'))
        all_tags = {item['tag'] for items in reg['groups'].values() for item in items}
        projection = {'text': '【L1】测试', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        spec = sc.build_settlement_spec(
            ROOT, self.state, projection, text='坐下', selected={'segment_id': 's1', 'option_id': 'A'},
            resolved_op=None, intent_evidence=None, preview_cost={'kind': 'action', 'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '09:10'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, resolution_policy={'category_policy': 'fixed_option', 'required_category': 'A'},
            output_contract={'operation': '', 'handoff': '', 'checks': {}, 'resolution': {}}, operation_context={},
        )
        prompt = spec['system_prompt']
        self.assertNotIn('user_context.', prompt, 'All Stage 2 references must use context.* aligned with main.js')
        # Extract every tag(desc) entry inside the 多档标签判准速查 section and verify 100% match against 事件注册表.json
        import re
        m = re.search(r'多档标签判准速查（严禁自造白名单外标签）：([^\n]+)', prompt)
        self.assertIsNotNone(m)
        guide_line = m.group(1)
        cited_tags = re.findall(r'([\u4e00-\u9fffA-Za-z0-9_]+)\(', guide_line)
        self.assertGreaterEqual(len(cited_tags), 24, f'Expected >=24 multi-tier tags in guide, got {len(cited_tags)}')
        unknown = [t for t in cited_tags if t not in all_tags]
        self.assertEqual(unknown, [], f'Settlement guide cites tags absent from 事件注册表.json: {unknown}')

    def test_story_api_unhandled_exception_returns_json_500(self):
        from flask import Flask
        import story_service as ss
        app = Flask(__name__)
        app.config['PROPAGATE_EXCEPTIONS'] = False
        svc = ss.register_story_routes(app, ROOT)

        @app.get('/api/story/_test_boom')
        def _boom():
            raise RuntimeError('simulated boom')

        client = app.test_client()
        resp = client.get('/api/story/_test_boom')
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.mimetype, 'application/json')
        data = resp.get_json()
        self.assertIn('error', data)
        self.assertEqual(data.get('status'), 500)
        _ = svc

    def test_zone0_slimming_and_drama3_syntax_unified(self):
        z0 = sc.build_zone0_global(ROOT, mode='dual_stream_v2', protagonist_style='faithful')
        self.assertLess(len(z0), 11500, f'Zone 0 should stay lean (<11500 chars), got {len(z0)}')
        for required in ('一幕一位移', '[MOVE:', 'surprise_directive', '4000字', '<whisper>', '<slow>', 'Drama 3'):
            self.assertIn(required, z0)
        self.assertNotIn('合法Fish英文方括号声学标签', z0)
        self.assertNotIn('每幕五条硬基线', z0)

    def test_sensory_lens_organic_and_cliche_sliding_window(self):
        projection = {'text': '【L1】测试', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        repeated_history = [
            {'id': 'seg-1', 'messages': [
                {'kind': 'action', 'speaker': '沈知韫', 'text': '她放下茶杯，指尖微微一顿，垂下眼。'},
                {'kind': 'narration', 'speaker': '', 'text': '徐志北喉结滚了一下。'},
            ]},
            {'id': 'seg-2', 'messages': [
                {'kind': 'action', 'speaker': '沈知韫', 'text': '她再次合上文件，指尖微顿。'},
                {'kind': 'narration', 'speaker': '', 'text': '徐志北喉结微动。'},
            ]},
        ]
        delta_raw = sc.build_user_delta(
            ROOT, self.state, projection, history=repeated_history, new_history_only=[],
            text='坐下聊两句', selected={'segment_id': 'seg-2', 'option_id': 'A'},
            resolved_op=None, intent_evidence=None, preview_cost={'kind': 'action', 'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '09:30'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, include_full_anchor=False, mode='dual_stream_v2',
        )
        parsed = json.loads(delta_raw)
        self.assertNotIn('sensory_lens', parsed)
        self.assertIn('fresh_detail_hint', parsed)
        self.assertIn('喉结滚动', parsed['fresh_detail_hint'])

    def test_stream_normalizer_strips_stray_tags_from_player_and_narration(self):
        raw = (
            '[N] [低声旁白] 灯光暗了下来，<whisper>气氛微凉</whisper>。\n'
            '[A:沈知韫] [冷淡克制] <soft>她把账单推到桌角。</soft>\n'
            '[D:徐志北] [低声克制] 我只是<emphasis>顺口问一句</emphasis>。\n'
            '[D:沈知韫] [压着倦意，声音微冷] 账得<slow>先算清楚</slow>。[break] <whisper>别声张。</whisper>\n'
            '---DECISION---\n'
            'PROMPT: 桌上的账单还摊开着，你打算怎么接？\n'
            'A: 追问深圳分部回款周期\n'
            'B: 替她把文件边角压平\n'
            'C: 直接翻看压在最下面的签字页\n'
        )
        parsed = sc.parse_stream_story(raw, allowed_speakers=['沈知韫'], partial=False, allow_player_dialogue=True)
        msgs = parsed['messages']
        self.assertEqual(len(msgs), 4)
        self.assertNotIn('<whisper>', msgs[0]['text'])
        self.assertNotIn('[低声旁白]', msgs[0]['text'])
        self.assertNotIn('<soft>', msgs[1]['text'])
        self.assertNotIn('[冷淡克制]', msgs[1]['text'])
        self.assertEqual(msgs[2]['speaker'], '徐志北')
        self.assertEqual(msgs[2]['text'], '我只是顺口问一句。')
        self.assertEqual(msgs[3]['speaker'], '沈知韫')
        self.assertIn('[压着倦意，声音微冷]', msgs[3]['text'])
        self.assertIn('<slow>先算清楚</slow>', msgs[3]['text'])
        self.assertIn('<whisper>别声张。</whisper>', msgs[3]['text'])

    def test_zone0_zone1_whitelist_harmony_slimming_and_silent_rewrite(self):
        z0_f = sc.build_zone0_global(ROOT, mode='dual_stream_v2', protagonist_style='faithful')
        z0_s = sc.build_zone0_global(ROOT, mode='dual_stream_v2', protagonist_style='silent')
        self.assertLess(len(z0_f), 9200)
        self.assertIn('char.徐志北', z0_f)
        self.assertNotIn('※索引key※', z0_f)
        self.assertNotIn('系统推演：当前可选行动', z0_f)
        self.assertIn('[D:徐志北] 所以妈是不打算把南城那块地交给他？', z0_f)
        self.assertNotIn('[D:徐志北] 所以妈是不打算把南城那块地交给他？', z0_s)

        state3 = dict(self.state, cast=['沈知韫', '苏婉青', '徐念薇'])
        z1_f = sc.build_zone1_scene(ROOT, state3, state3['cast'], [], self.memory_text, mode='dual_stream_v2', protagonist_style='faithful')
        z1_s = sc.build_zone1_scene(ROOT, state3, state3['cast'], [], self.memory_text, mode='dual_stream_v2', protagonist_style='silent')
        self.assertLess(len(z1_f), 6800)
        self.assertNotIn('<<< char.徐志北', z1_f)
        self.assertNotIn('※索引key※', z1_f)
        self.assertIn('另允许 ≤3 句贴合玩家原意图的简短 [D:徐志北]', z1_f)
        self.assertIn('严禁 [D:徐志北]', z1_s)

        proj = {'text': '【L1】测试', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        spec = sc.build_settlement_spec(
            ROOT, state3, proj, text='聊聊', selected={'segment_id': 's1', 'option_id': 'A'},
            resolved_op=None, intent_evidence=None, preview_cost={'kind': 'action', 'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '09:10'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, resolution_policy={'category_policy': 'fixed_option', 'required_category': 'A'},
            output_contract={'operation': '', 'handoff': '', 'checks': {}, 'resolution': {}}, operation_context={},
        )
        self.assertLess(len(spec['system_prompt']), 12500)
        self.assertNotIn('SHAME_EVENTS', spec['system_prompt'])
        self.assertNotIn('运行时数据层', spec['system_prompt'])

    def test_c_streak_intel002_delivered_gifts_and_incremental_recalled_memories(self):
        rich_state = dict(
            self.state,
            location='徐家主宅',
            cast=['沈知韫', '苏婉青'],
            panels=[
                '[系统宿主] 体力 100 | 积分 50 | 经验值 0 | 魅力 70 | 商业嗅觉 30',
                '[沈知韫] 好感 95 | 羞耻 100 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
                '[苏婉青] 好感 50 | 羞耻 95 | 体力 100 | 欲望 0 | 堕落 0 | 怀孕 False',
            ],
            mechanics={
                'c_streak': {'沈知韫': {'count': 2, 'last_tag': 'C烈度_轻度'}},
                'secrets_unlocked': ['INTEL-002'],
            },
            delivered_items=[
                {'name': '手工红茶礼盒', 'recipient': '沈知韫'},
                {'name': '水彩颜料盒', 'recipient': '徐念薇'},
            ],
            items=[{'id': 'ITEM-001', 'name': '温热精油', 'quantity': 1, 'fields': {'描述': '精油'}}],
        )
        brief = sc.compile_state_qualitative_brief(rich_state, self.memory_text)
        self.assertIn('近轮连续高压接触(2轮', brief)
        self.assertIn('眼线身份已被宿主当面揭穿', brief)
        self.assertNotIn('主宅探访见闻事后会向丈夫徐承邺汇报', brief)

        proj = {
            'text': '【L1】当前回合',
            'current': None,
            'index': [],
            'transfers': {},
            'recalled_old_entries': [
                {'layer': 'L2', 'range': '3', 'body': '【3】沈知韫曾约定下周三复核深圳分部合同。'}
            ],
            'limits': {'round_chars': 600},
        }
        full_delta = json.loads(sc.build_user_delta(
            ROOT, rich_state, proj, history=[], new_history_only=[],
            text='提起红茶', selected=None, resolved_op=None, intent_evidence=None,
            preview_cost={'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '12:15'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, include_full_anchor=True, mode='dual_stream_v2',
        ))
        self.assertIn('items', full_delta)
        self.assertNotIn('held_items', full_delta)
        self.assertEqual(full_delta.get('delivered_gifts_to_cast'), [{'name': '手工红茶礼盒', 'recipient': '沈知韫'}])

        inc_delta = json.loads(sc.build_user_delta(
            ROOT, rich_state, proj, history=[], new_history_only=[],
            text='深圳分部合同怎么了', selected=None, resolved_op=None, intent_evidence=None,
            preview_cost={'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '12:20'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=self.memory_text, include_full_anchor=False, mode='dual_stream_v2',
        ))
        self.assertIn('recalled_memories', inc_delta)
        self.assertIn('深圳分部合同', inc_delta['recalled_memories'][0]['body'])

    def test_custom_system_rules_primary_and_settlement_isolated_and_unlimited(self):
        import tempfile
        import importlib.util
        import interaction_runtime as ir

        base_z0 = sc.build_zone0_global(ROOT, mode='dual_stream_v2')
        dummy_proj = {'text': '', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        dummy_contract = {'checks': {'intent': '', 'knowledge': '', 'action': '', 'pace': ''}, 'resolution': None}
        base_settle = sc.build_settlement_spec(
            ROOT, self.state, dummy_proj, '测试输入', None, None, None,
            {'kind': 'system'}, {'memory_round': 1, 'phase': 'ready'}, self.memory_text,
            {}, dummy_contract, None,
        )

        # Disabled rules must produce 100% byte-identical Zone 0 and Stage 2 system prompts.
        long_primary = ('主模型电影质感约束。' * 1500).strip()  # > 13,500 chars (no artificial cap!)
        long_settle = ('副模型额外审计偏好。' * 1500).strip()   # > 13,500 chars (no artificial cap!)
        off_prefs = {
            'custom_rules_enabled': False,
            'custom_rules_position': 'append',
            'custom_rules_text': long_primary,
            'settlement_custom_rules_enabled': False,
            'settlement_custom_rules_position': 'append',
            'settlement_custom_rules_text': long_settle,
        }
        self.assertEqual(sc.build_zone0_global(ROOT, mode='dual_stream_v2', custom_rules=off_prefs), base_z0)
        settle_off = sc.build_settlement_spec(
            ROOT, self.state, dummy_proj, '测试输入', None, None, None,
            {'kind': 'system'}, {'memory_round': 1, 'phase': 'ready'}, self.memory_text,
            {}, dummy_contract, None, settlement_custom_rules=off_prefs,
        )
        self.assertEqual(settle_off['system_prompt'], base_settle['system_prompt'])
        self.assertEqual(settle_off['system_sha256'], base_settle['system_sha256'])

        # Primary ON (append & prepend) affects ONLY Zone 0, never Stage 2!
        primary_append_prefs = {**off_prefs, 'custom_rules_enabled': True, 'custom_rules_position': 'append'}
        z0_app = sc.build_zone0_global(ROOT, mode='dual_stream_v2', custom_rules=primary_append_prefs)
        self.assertTrue(z0_app.startswith(base_z0))
        self.assertIn(long_primary, z0_app)
        self.assertNotIn(long_settle, z0_app)

        primary_prepend_prefs = {**off_prefs, 'custom_rules_enabled': True, 'custom_rules_position': 'prepend'}
        z0_pre = sc.build_zone0_global(ROOT, mode='dual_stream_v2', custom_rules=primary_prepend_prefs)
        self.assertTrue(z0_pre.startswith('【玩家自定义系统级规则'))
        self.assertTrue(z0_pre.endswith(base_z0))

        # Stage 2 remains untouched when only primary rule is enabled.
        settle_with_primary_only = sc.build_settlement_spec(
            ROOT, self.state, dummy_proj, '测试输入', None, None, None,
            {'kind': 'system'}, {'memory_round': 1, 'phase': 'ready'}, self.memory_text,
            {}, dummy_contract, None, settlement_custom_rules=primary_append_prefs,
        )
        self.assertEqual(settle_with_primary_only['system_prompt'], base_settle['system_prompt'])

        # Settlement ON (append & prepend) affects ONLY Stage 2 system_prompt, never Zone 0!
        settle_append_prefs = {**off_prefs, 'settlement_custom_rules_enabled': True, 'settlement_custom_rules_position': 'append'}
        settle_app = sc.build_settlement_spec(
            ROOT, self.state, dummy_proj, '测试输入', None, None, None,
            {'kind': 'system'}, {'memory_round': 1, 'phase': 'ready'}, self.memory_text,
            {}, dummy_contract, None, settlement_custom_rules=settle_append_prefs,
        )
        self.assertTrue(settle_app['system_prompt'].startswith(base_settle['system_prompt']))
        self.assertIn(long_settle, settle_app['system_prompt'])
        self.assertNotEqual(settle_app['system_sha256'], base_settle['system_sha256'])
        self.assertEqual(sc.build_zone0_global(ROOT, mode='dual_stream_v2', custom_rules=settle_append_prefs), base_z0)

        settle_prepend_prefs = {**off_prefs, 'settlement_custom_rules_enabled': True, 'settlement_custom_rules_position': 'prepend'}
        settle_pre = sc.build_settlement_spec(
            ROOT, self.state, dummy_proj, '测试输入', None, None, None,
            {'kind': 'system'}, {'memory_round': 1, 'phase': 'ready'}, self.memory_text,
            {}, dummy_contract, None, settlement_custom_rules=settle_prepend_prefs,
        )
        self.assertTrue(settle_pre['system_prompt'].startswith('【玩家自定义后台结算规则'))
        self.assertTrue(settle_pre['system_prompt'].endswith(base_settle['system_prompt']))

        # Persistence via save_story_prefs/load_story_prefs + preservation across 存档清理器.plan_reset().
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            saved = ir.save_story_prefs(td_path, {
                'custom_rules_enabled': True,
                'custom_rules_position': 'prepend',
                'custom_rules_text': long_primary + '\r\n第二行',
                'settlement_custom_rules_enabled': True,
                'settlement_custom_rules_position': 'append',
                'settlement_custom_rules_text': long_settle,
            })
            loaded = ir.load_story_prefs(td_path)
            self.assertEqual(loaded, saved)
            self.assertEqual(loaded['custom_rules_text'], long_primary + '\n第二行')
            self.assertEqual(loaded['settlement_custom_rules_text'], long_settle)

            (td_path / 'injection_core.py').write_text('# stub\n', encoding='utf-8')
            (td_path / 'round_runtime.py').write_text('# stub\n', encoding='utf-8')
            spec = importlib.util.spec_from_file_location('save_cleaner', ROOT / '存档清理器.py')
            cleaner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cleaner)
            plan = cleaner.plan_reset(td_path)
            planned_paths = {row['path'].replace('\\', '/') for row in plan}
            self.assertNotIn(ir.STORY_PREFS_PATH, planned_paths, '存档清理器 must preserve .round-runtime/story/prefs.json')

    def test_xu_chengye_no_depravity_and_tiered_vigilance_channel_gate(self):
        import tempfile
        import save_store
        import injection_core as ic
        import round_runtime as rr
        import interaction_runtime as ir

        # 1. Default state & legacy save migration must never emit [徐承邺] 堕落
        base_txt = save_store.render_memory_txt(save_store.default_state(), save_store.default_layers())
        self.assertNotIn('[徐承邺] 堕落', base_txt)
        legacy_txt = base_txt.replace('【人物所在】', '[徐承邺] 堕落 10\n\n【人物所在】')
        st_mig, ly_mig = save_store.migrate_from_legacy_texts(legacy_txt, '')
        self.assertNotIn('徐承邺', st_mig['panels'])
        self.assertNotIn('[徐承邺] 堕落', save_store.render_memory_txt(st_mig, ly_mig))

        # 2. _validate_event_fields rejects 徐承邺 in depravity_events
        with self.assertRaises(rr.RoundError):
            rr._validate_event_fields(ROOT, ic, {
                'shame_events': {}, 'depravity_events': {'徐承邺': ['死亡查岗_沉沦期']},
                'ds_events': {}, 'affection_events': {}, 'host_events': [], 'vigilance_events': {},
            })

        # 3. Perception gate, multipliers, traces, defection, spillover, per-char decay, 5-tier thresholds & blindspot
        with tempfile.TemporaryDirectory() as td:
            mp = Path(td) / 'mem.txt'
            st0 = save_store.default_state()
            mp.write_text(save_store.render_memory_txt(st0, save_store.default_layers()), encoding='utf-8')

            # 3a. Abroad + private room -> blocked (+0)
            ic.process_vigilance_system(
                {'苏婉青': ['异常行迹'], '沈知韫': ['目击确认']}, {}, str(mp),
                elapsed_hours=0, roll_home=False, active_cast=['苏婉青', '沈知韫'],
                event_evidences={'苏婉青': '卧室灯光昏暗，两人贴近低声交谈。', '沈知韫': '她轻声叹了口气。'},
                scene_privacy='private_room', enforce_channel_gate=True,
            )
            vig = ic._parse_vigilance_block(mp.read_text(encoding='utf-8'))
            self.assertEqual(vig['目标']['苏婉青']['警惕'], 0)
            self.assertEqual(vig['目标']['沈知韫']['警惕'], 0)

            # 3b. Real external channel -> 苏 14 / 沈 10 / 念薇 6 + 30% spillover to 徐志北 (9)
            ic.process_vigilance_system(
                {'苏婉青': ['异常行迹'], '沈知韫': ['异常行迹'], '徐念薇': ['异常行迹']}, {}, str(mp),
                elapsed_hours=0, roll_home=False, active_cast=['苏婉青', '沈知韫', '徐念薇'],
                event_evidences={
                    '苏婉青': '查岗电话里她停顿了两秒才开口敷衍过去。',
                    '沈知韫': '管家端茶推门时瞥见两人神色微变。',
                    '徐念薇': '物业保安顺口提了一句二少爷深夜离开画室。',
                },
                enforce_channel_gate=True,
            )
            vig = ic._parse_vigilance_block(mp.read_text(encoding='utf-8'))
            self.assertEqual(vig['目标']['苏婉青']['警惕'], 14)
            self.assertEqual(vig['目标']['沈知韫']['警惕'], 10)
            self.assertEqual(vig['目标']['徐念薇']['警惕'], 6)
            self.assertEqual(vig['目标']['徐志北']['警惕'], 9)
            self.assertIn('电话', vig['目标']['苏婉青']['动因'])
            self.assertIn('连带', vig['目标']['徐志北']['动因'])

            # 3c. Public vigilance hides 发现几率 / prob and exposes role_label + stage + reason
            pub = ir.parse_public_vigilance(mp.read_text(encoding='utf-8'), save_state=st0)
            pub_json = json.dumps(pub, ensure_ascii=False)
            self.assertNotIn('prob', pub_json)
            self.assertNotIn('发现几率', pub_json)
            su_pub = next(x for x in pub['targets'] if x['name'] == '苏婉青')
            self.assertEqual(su_pub['role_label'], '妻子 · 极敏')
            self.assertIn('电话', su_pub['reason'])

            # 3d. Per-character hourly decay (2h: 苏 -3 -> 11, 沈 -4 -> 6, 念薇 -6 -> 0 cleared, 志北 -4 -> 5)
            ic.process_vigilance_system({}, {}, str(mp), elapsed_hours=2, roll_home=False)
            vig = ic._parse_vigilance_block(mp.read_text(encoding='utf-8'))
            self.assertEqual(vig['目标']['苏婉青']['警惕'], 11)
            self.assertEqual(vig['目标']['沈知韫']['警惕'], 6)
            self.assertEqual(vig['目标']['徐念薇']['警惕'], 0)
            self.assertEqual(vig['目标']['徐念薇']['发现'], 0)
            self.assertEqual(vig['目标']['徐念薇']['动因'], '')
            self.assertEqual(vig['目标']['徐志北']['警惕'], 5)

            # 3e. Su Wanqing defected (x1.0) + traces bonus (+3) => 11 + 10 + 3 = 24
            ic.process_vigilance_system(
                {'苏婉青': ['异常行迹']}, {}, str(mp),
                elapsed_hours=0, roll_home=False, active_cast=['苏婉青'],
                event_evidences={'苏婉青': '公寓门禁记录显示访客深夜离开。'},
                traces={'苏婉青': [{'kind': 'mark', 'desc': '颈侧红痕', 'turns': 3}]},
                intel_state={'consumed': ['INTEL-002']},
                su_stats={'好感': 75, '羞耻': 45},
                enforce_channel_gate=True,
            )
            vig = ic._parse_vigilance_block(mp.read_text(encoding='utf-8'))
            self.assertEqual(vig['目标']['苏婉青']['警惕'], 24)

            # 3f. 5-tier return thresholds
            self.assertEqual(ic._vigilance_return_prob('苏婉青', 40), 0.15)
            self.assertEqual(ic._vigilance_return_prob('沈知韫', 40), 0.0)
            self.assertEqual(ic._vigilance_return_prob('沈知韫', 50), 0.10)
            self.assertEqual(ic._vigilance_return_prob('苏婉青', 65), 0.40)
            self.assertEqual(ic._vigilance_return_prob('沈知韫', 65), 0.30)
            self.assertEqual(ic._vigilance_return_prob('徐念薇', 85), 0.65)

            # 3g. Compiler blindspot note for 沈知韫 when 0 < vig < 45 & 动因 roundtrip via save_store
            st_brief = {'location': '徐家主宅', 'cast': ['沈知韫'], 'panels': [], 'presence': {}}
            brief = sc.compile_state_qualitative_brief(st_brief, mp.read_text(encoding='utf-8'))
            self.assertIn('伦理盲区', brief)
            self.assertIn('争家业', brief)
            st_rt, _ = save_store.migrate_from_legacy_texts(mp.read_text(encoding='utf-8'), '')
            self.assertIn('门禁', st_rt['vigilance']['目标']['苏婉青']['动因'])

    def test_attribute_rebalance_plan_b_invariants(self):
        """Plan B (P0+P1+P2) comprehensive invariants."""
        import tempfile
        import injection_core as ic
        import save_store
        import story_progression as sp

        # 1. Opening baselines & leverage_charges persistence roundtrip
        st0 = save_store.default_state()
        self.assertEqual(st0['panels']['沈知韫']['好感'], 82)
        self.assertEqual(st0['panels']['沈知韫']['羞耻'], 100)
        self.assertEqual(st0['panels']['徐念薇']['羞耻'], 96)
        self.assertEqual(st0['panels']['苏婉青']['羞耻'], 92)
        self.assertEqual(st0['intel']['leverage_charges'], 0)
        st0['intel']['leverage_charges'] = 2
        rendered0 = save_store.render_memory_txt(st0, save_store.default_layers())
        self.assertIn('商业杠杆护盾：剩余 2 次', rendered0)
        self.assertEqual(sp.parse_intel_block(rendered0)['leverage_charges'], 2)
        st_rt, _ = save_store.migrate_from_legacy_texts(rendered0, '')
        self.assertEqual(st_rt['intel']['leverage_charges'], 2)

        # 2. Passive EXP curve 20/50/110/220
        tiers = sp.passive_levels(ROOT)
        self.assertEqual([t['cost'] for t in tiers], [0, 20, 50, 110, 220])

        # 3. Charm <68 penalty tier + fluid lock creampie >=3 floor (62 vs 58)
        low_c = ic.charm_tier_info(64)
        self.assertEqual(low_c['name'], '气场受挫')
        self.assertEqual(low_c['release_vigor_cost'], 14)
        self.assertEqual(low_c['bt_floor'], 75)
        self.assertEqual(ic.charm_tier_info(70)['name'], '清俊克制')
        self.assertEqual(ic.fluid_lock_floor_for_turns(5, creampie_count=0), 58)
        self.assertEqual(ic.fluid_lock_floor_for_turns(5, creampie_count=3), 62)

        # 4. Orgasm multiplier soft cap 1.50, edging_streak >=3 (+0.15) & vigor <15 (-0.15)
        max_m, _ = ic._compute_orgasm_mult(
            100, 100, host_charm=100, body_dev={'沈知韫': {'foot': 90}}, char_name='沈知韫',
            body_acts={'沈知韫': ['foot']}, host_desire=95, edging_streak=4, host_vigor=100, creampie_count=5,
        )
        self.assertEqual(max_m, 1.50)
        m_base, _ = ic._compute_orgasm_mult(60, 20, host_charm=70, host_desire=50, edging_streak=0, host_vigor=60, creampie_count=0)
        m_edge3, _ = ic._compute_orgasm_mult(60, 20, host_charm=70, host_desire=90, edging_streak=3, host_vigor=60, creampie_count=0)
        m_tired, _ = ic._compute_orgasm_mult(60, 20, host_charm=70, host_desire=50, edging_streak=0, host_vigor=10, creampie_count=0)
        self.assertAlmostEqual(m_edge3 - m_base, 0.15, places=4)
        self.assertAlmostEqual(m_base - m_tired, 0.15, places=4)

        with tempfile.TemporaryDirectory() as td:
            mp = Path(td) / 'mem.txt'
            st = save_store.default_state()
            # 5. Lv.3 fatigue break (sta < 60 -> extra -1 shame), Lv.4 intact_defense exemption & 75% mitigation cap
            st['panels']['沈知韫'].update({'好感': 80, '羞耻': 90, '堕落': 0, '体力': 50, '被动': 3})
            mp.write_text(save_store.render_memory_txt(st, save_store.default_layers()), encoding='utf-8')
            sh_tired = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, str(mp))['沈知韫']
            st['panels']['沈知韫']['体力'] = 80
            mp.write_text(save_store.render_memory_txt(st, save_store.default_layers()), encoding='utf-8')
            sh_fresh = ic.process_shame_system({'沈知韫': ['C烈度_中度']}, str(mp))['沈知韫']
            self.assertEqual(sh_fresh - sh_tired, 1)

            # Intact defense stays active at Lv.2/3, exempt at Lv.4; stacked mitigations capped at 75% (floor -1)
            aff_lv3 = ic.process_affection_system({}, {'沈知韫': ['C烈度_重度']}, str(mp))['沈知韫']
            self.assertEqual(aff_lv3, 73)  # raw -15 (intact), Lv.2+ *0.5 -> -7
            aff_stacked = ic.process_affection_system(
                {}, {'沈知韫': ['C烈度_重度']}, str(mp),
                business_leverage=True, host_charm=95,
            )['沈知韫']
            self.assertEqual(aff_stacked, 76)  # 75% cap on -15 -> -4 (never 0)
            st['panels']['沈知韫']['被动'] = 4
            mp.write_text(save_store.render_memory_txt(st, save_store.default_layers()), encoding='utf-8')
            aff_lv4 = ic.process_affection_system({}, {'沈知韫': ['C烈度_重度']}, str(mp))['沈知韫']
            self.assertEqual(aff_lv4, 75)  # Lv.4 exempts intact_defense -> raw -10 * 0.5 -> -5

            # 6. Same-turn shame_cap clamp after depravity rise + clean A-tier gentle recovery (+5 cap 30) + nap +15
            prev_paths = (ic.BASE_DIR, ic.DATA_DIR, ic.MEMORY_FILE, ic.ITEM_FILE, ic.DATA_JSON_FILE)
            try:
                ic.BASE_DIR = td
                ic.DATA_DIR = str(Path(td) / '存档')
                ic.MEMORY_FILE = str(Path(td) / save_store.RENDERED_MEMORY_PATH)
                ic.ITEM_FILE = str(Path(td) / save_store.RENDERED_ITEMS_PATH)
                ic.DATA_JSON_FILE = str(Path(td) / 'data.json')
                st['panels']['沈知韫'].update({'羞耻': 98, '堕落': 0, '体力': 20, '被动': 0, '欲望': 10})
                save_store.save_bundle(td, st, save_store.default_layers())
                ic.apply_story_events(
                    {'shame_events': {'沈知韫': ['C烈度_轻度']}, 'depravity_events': {'沈知韫': ['内射_首次核爆']}},
                    None, 1, action_category='C', active_cast=['沈知韫'],
                )
                st_c_after, _, _ = save_store.load_bundle(td)
                # depravity becomes 15 -> shame_cap = 100 - int(15*0.6) = 91 -> clamped <= 91
                self.assertLessEqual(st_c_after['panels']['沈知韫']['羞耻'], 91)

                st['panels']['沈知韫'].update({'体力': 20, '欲望': 10})
                save_store.save_bundle(td, st, save_store.default_layers())
                ic.apply_story_events({}, None, 2, action_category='A', active_cast=['沈知韫'])
                st_a_after, _, _ = save_store.load_bundle(td)
                self.assertEqual(st_a_after['panels']['沈知韫']['体力'], 25)
            finally:
                ic.BASE_DIR, ic.DATA_DIR, ic.MEMORY_FILE, ic.ITEM_FILE, ic.DATA_JSON_FILE = prev_paths

            st['panels']['沈知韫'].update({'体力': 20, '欲望': 10})
            mp.write_text(save_store.render_memory_txt(st, save_store.default_layers()), encoding='utf-8')
            panels_nap = ic.process_desire_stamina_system({'沈知韫': ['恢复_小憩']}, str(mp))
            self.assertEqual(panels_nap['沈知韫']['体力'], 35)  # 20 + 15

            # 7. Independent biz settlement + biz >= 80 (+15% winning pts/exp & -15% non-witness vig) + leverage vig suppression
            st['panels']['系统宿主'].update({'积分': 0, '经验值': 0, '商业嗅觉': 80})
            mp.write_text(save_store.render_memory_txt(st, save_store.default_layers()), encoding='utf-8')
            host_res = ic.process_host_system(['侵蚀_防线坍塌', '商业_信息获取'], {}, str(mp))
            self.assertEqual(host_res['积分'], round(30 * 1.15))
            self.assertEqual(host_res['经验值'], round(20 * 1.15))
            self.assertEqual(host_res['商业嗅觉'], 84)  # +4 independent

            st_v = save_store.default_state()
            mp.write_text(save_store.render_memory_txt(st_v, save_store.default_layers()), encoding='utf-8')
            ic.process_vigilance_system(
                {'苏婉青': ['异常行迹']}, {}, str(mp),
                elapsed_hours=0, roll_home=False, active_cast=['苏婉青'],
                event_evidences={'苏婉青': '查岗电话里她声音微顿。'},
                enforce_channel_gate=True, host_biz=85, leverage_active=True,
            )
            vig = ic._parse_vigilance_block(mp.read_text(encoding='utf-8'))
            # Base 10 * 1.4 = 14 -> biz 80+ *0.85 = 12 -> leverage -10 => 2
            self.assertEqual(vig['目标']['苏婉青']['警惕'], 2)

        # 8. body_dev +4/+8, max 2 focus zones, edging_streak >= 3 vigor -2, single-turn Charm cap +1
        st_i = save_store.default_state()
        st_i['panels']['系统宿主']['魅力'] = 72
        st_i['intimate']['body_dev']['沈知韫']['foot'] = 44
        st_i['intimate']['host_phys'] = {'desire': 90, 'vigor': 50, 'release_count': 0, 'edging_streak': 2, 'fetishes': []}
        meta = ic.advance_intimate_state(
            st_i,
            {'shame_events': {'沈知韫': ['C烈度_深度']}},
            scene_state={'body_acts': {'沈知韫': ['mouth', 'chest', 'waist', 'foot', 'hand']}},
            active_cast=['沈知韫'],
            category='C',
            charm_gained_this_turn=True,
        )
        # Only 2 zones developed (signature 'foot' prioritized + 1 other)
        developed = [z for z, v in st_i['intimate']['body_dev']['沈知韫'].items() if (v > 0 and z != 'foot') or (z == 'foot' and v > 44)]
        self.assertEqual(len(developed), 2)
        self.assertEqual(st_i['intimate']['body_dev']['沈知韫']['foot'], 55)  # 44 + round(8*1.35)=11
        self.assertEqual(meta['charm_milestone_gain'], 0)  # capped because charm_gained_this_turn=True
        self.assertEqual(st_i['panels']['系统宿主']['魅力'], 72)
        self.assertEqual(st_i['intimate']['host_phys']['edging_streak'], 3)
        self.assertLessEqual(st_i['intimate']['host_phys']['vigor'], 43)  # extra -2 edging fatigue

        # 9. Shop unlock_req (SHOP-011..014) + Compiler Plan B briefings
        cat = {it['id']: it for it in sp.load_shop_catalog(ROOT)['items']}
        ok11_charm = sp.evaluate_unlock_req(cat['SHOP-011']['unlock_req'], 0, {'沈知韫': 82}, max_depravity=0, host_charm=75)
        ok11_low = sp.evaluate_unlock_req(cat['SHOP-011']['unlock_req'], 0, {'沈知韫': 82}, max_depravity=0, host_charm=70)
        self.assertTrue(ok11_charm['unlocked'])
        self.assertFalse(ok11_low['unlocked'])
        ok14_no_dep = sp.evaluate_unlock_req(cat['SHOP-014']['unlock_req'], 20, {'沈知韫': 90}, max_depravity=5, host_charm=70)
        ok14_ok = sp.evaluate_unlock_req(cat['SHOP-014']['unlock_req'], 20, {'沈知韫': 40}, max_depravity=10, host_charm=70)
        self.assertFalse(ok14_no_dep['unlocked'])
        self.assertTrue(ok14_ok['unlocked'])

        st_b = save_store.default_state()
        st_b['panels']['系统宿主']['商业嗅觉'] = 85
        st_b['panels']['沈知韫']['怀孕'] = True
        st_b['intel']['leverage_charges'] = 2
        st_b['intimate']['host_phys'].update({'desire': 90, 'edging_streak': 3, 'vigor': 12})
        mem_b = save_store.render_memory_txt(st_b, save_store.default_layers())
        brief_b = sc.compile_state_qualitative_brief(
            {
                'location': '徐家主宅',
                'cast': ['沈知韫'],
                'panels': [ln for ln in mem_b.splitlines() if ln.startswith('[') and ']' in ln],
                'presence': {},
                'intimate': st_b['intimate'],
            },
            mem_b,
        )
        self.assertIn('深局棋手', brief_b)
        self.assertIn('极限控场', brief_b)
        self.assertIn('动作略沉', brief_b)
        self.assertIn('商业牵制底气（余2次', brief_b)
        self.assertIn('孕期易倦', brief_b)

        # 10. Event registry table sync in 一键注入指南.txt & frontend parity checks
        reg = rr._event_registry(ROOT, ic)
        self.assertEqual(len(reg), 6)
        js_txt = (ROOT / 'story_client.js').read_text(encoding='utf-8')
        self.assertIn('levObj.remaining_charges', js_txt)
        self.assertIn('intel-tier-strip is-five', js_txt)
        self.assertIn('host_charm_tier: w.host_charm_tier', js_txt)
        self.assertIn('intimate: w.intimate', js_txt)

    def test_living_character_agency_plan_b_five_pillars(self):
        """Five-pillar living character agency (anti-puppetry) invariants."""
        import copy
        import save_store
        import story_progression as sp

        # 1. Pillar 1: De-numericized qualitative brief + role-specific tiers + micro-trend
        st = save_store.default_state()
        st['npc_mind']['沈知韫']['aff_delta_last'] = 4
        st['npc_mind']['徐念薇']['aff_delta_last'] = -3
        mem_txt = save_store.render_memory_txt(st, save_store.default_layers())
        state3 = {
            'location': '徐家主宅',
            'cast': ['沈知韫', '苏婉青', '徐念薇'],
            'panels': [ln for ln in mem_txt.splitlines() if ln.startswith('[') and ']' in ln],
            'presence': st['presence'],
            'intimate': st['intimate'],
            'mechanics': st['mechanics'],
            'npc_mind': st['npc_mind'],
        }
        brief = sc.compile_state_qualitative_brief(state3, mem_txt)
        self.assertIn('天然偏护信任', brief)
        self.assertIn('明显松动热络', brief)
        self.assertIn('态度明显收冷', brief)
        self.assertNotIn('好感82/羞耻100/堕落0', brief)
        self.assertNotIn('凡人体质', brief)
        self.assertNotIn('好感天花板85未解锁', brief)

        # 2. Pillar 2: npc_mind normalization, sanitizer whitelist, TTL decay & overnight cooling
        upgraded = save_store.normalize_state({})
        self.assertEqual(set(upgraded['npc_mind'].keys()), set(save_store.NPC_MIND_TARGETS))
        cat = sp.load_world_beats(ROOT, optional=True)
        dstate = sp.parse_director_block(mem_txt)
        san = sp._sanitize_director_echo(
            {
                'mind_updates': {
                    '徐念薇': {'mood': '被敷衍戳得有点堵', 'preoccupation': '改画展二稿', 'impression': '觉得志北今天话里有话'},
                    '路人甲': {'mood': '非法角色应被过滤'},
                    '沈知韫': {'mood': '无'},
                }
            },
            cat, dstate, is_action=True,
        )
        self.assertIn('mind_updates', san)
        self.assertIn('徐念薇', san['mind_updates'])
        self.assertNotIn('路人甲', san['mind_updates'])
        self.assertNotIn('沈知韫', san['mind_updates'])

        st_m = copy.deepcopy(st)
        sp.advance_npc_mind(st_m, san['mind_updates'], active_cast=['徐念薇'], aff_deltas={'徐念薇': 2})
        self.assertEqual(st_m['npc_mind']['徐念薇']['mood'], '被敷衍戳得有点堵')
        self.assertEqual(st_m['npc_mind']['徐念薇']['mood_ttl'], 2)
        self.assertEqual(st_m['npc_mind']['徐念薇']['aff_delta_last'], 2)
        self.assertEqual(len(st_m['npc_mind']['徐念薇']['impressions']), 1)
        # Next turn decays mood_ttl 2 -> 1 (still present)
        sp.advance_npc_mind(st_m, None, active_cast=['徐念薇'])
        self.assertEqual(st_m['npc_mind']['徐念薇']['mood_ttl'], 1)
        self.assertTrue(st_m['npc_mind']['徐念薇']['mood'])
        # Overnight clears mood immediately while keeping subjective impression & preoccupation
        sp.advance_npc_mind(st_m, None, active_cast=['徐念薇'], overnight=True)
        self.assertEqual(st_m['npc_mind']['徐念薇']['mood'], '')
        self.assertEqual(st_m['npc_mind']['徐念薇']['mood_ttl'], 0)
        self.assertEqual(st_m['npc_mind']['徐念薇']['preoccupation'], '改画展二稿')
        self.assertEqual(len(st_m['npc_mind']['徐念薇']['impressions']), 1)

        # 3 & 4. Pillar 3 & 4: Zone 0 anti-puppetry, Zone 2 cast_mind (cast-only), scene_entry_residue (turn 1 only), lateral hint
        z0 = sc.build_zone0_global(ROOT, mode='dual_stream_v2', protagonist_style='faithful')
        self.assertLess(len(z0), 9200)
        for token in ('活人演法与建设性摩擦', '斜向回应', '心智理论与合理误判', '多人同场横向空气'):
            self.assertIn(token, z0)

        z1 = sc.build_zone1_scene(ROOT, state3, state3['cast'], [], mem_txt, mode='dual_stream_v2')
        self.assertLess(len(z1), 6800)
        self.assertIn('活人骨相·主动/盲区/横向反应', z1)

        proj = {'text': '【L1】周日午宴', 'current': None, 'index': [], 'transfers': {}, 'limits': {'round_chars': 600}}
        d1 = json.loads(sc.build_user_delta(
            ROOT, state3, proj, history=[], new_history_only=[],
            text='坐下倒水', selected=None, resolved_op=None, intent_evidence=None,
            preview_cost={'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '12:15'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=mem_txt, include_full_anchor=True, mode='dual_stream_v2',
            director_roll={'scene_turns_in_place': 1},
        ))
        self.assertIn('cast_mind', d1)
        self.assertNotIn('徐承邺', d1['cast_mind']['people'])
        self.assertIn('scene_entry_residue', d1)
        self.assertIn('沈知韫', d1['scene_entry_residue']['moments'])
        self.assertIn('彼此直接接话', d1['output_format'])
        self.assertIn('演法锚点', d1['output_format'])

        # Turn 2 in same place omits scene_entry_residue
        d2 = json.loads(sc.build_user_delta(
            ROOT, state3, proj, history=[], new_history_only=[],
            text='继续聊', selected=None, resolved_op=None, intent_evidence=None,
            preview_cost={'before': 95, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '12:30'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=mem_txt, include_full_anchor=False, mode='dual_stream_v2',
            director_roll={'scene_turns_in_place': 2},
        ))
        self.assertNotIn('scene_entry_residue', d2)

        # 5. Pillar 5 + Stage 2 budget & mind_updates piggyback
        settle = sc.build_settlement_spec(
            ROOT, state3, proj, text='聊聊', selected={'segment_id': 's1', 'option_id': 'A'},
            resolved_op=None, intent_evidence=None, preview_cost={'kind': 'action', 'before': 100, 'reserved': 5},
            runtime={'clock': {'day': 1, 'time': '12:15'}, 'memory_round': 1, 'phase': 'ready'},
            memory_text=mem_txt, resolution_policy={'category_policy': 'fixed_option', 'required_category': 'A'},
            output_contract={'operation': '', 'handoff': '', 'checks': {}, 'resolution': {}}, operation_context={},
        )
        self.assertLess(len(settle['system_prompt']), 12500)
        self.assertIn('mind_updates', settle['system_prompt'])
        self.assertIn('cast_mind', settle['user_context'])


if __name__ == '__main__':
    unittest.main()




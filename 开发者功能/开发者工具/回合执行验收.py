"""Run directly to verify round submission against disposable synthetic projects."""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / 'round_runtime.py').is_file():
    ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'injection_core.py').is_file())
sys.path.insert(0, str(ROOT))
import round_runtime as rr

TMP_ROOT = ROOT / 'scene_chat_dev/tmp'


def memory(layers=None, prologue=False):
    values = layers or {'L1': [], 'L2': [], 'L3': [], 'L4': []}
    lines = ['【实时面板快照】', '▶ 当前最新数值',
             '[系统宿主] 积分 7 | 经验值 3 | 体力 100 | 魅力 70 | 商业嗅觉 0']
    for name in ('沈知韫', '徐念薇', '苏婉青'):
        lines.append('[' + name + '] 好感 50 | 堕落 0 | 欲望 0 | 羞耻 100 | 体力 100 | 高潮 0% | 内射 0次 | 怀孕 False | 被动 Lv.0')
    lines += ['[徐承邺] 堕落 0', '', '【人物所在】',
              '沈知韫：徐家主宅 | 事由：常住', '徐念薇：工作室 | 事由：工作',
              '苏婉青：市中心顶层公寓 | 事由：常住', '徐志北：徐家主宅 | 事由：常住', '', '【当前激活微状态】']
    for name in ('沈知韫', '徐念薇', '苏婉青'):
        lines += ['▶ ' + name, 'momentary_ease: false | residual_tension: false | confusion_debt: false']
    lines += ['', '==================================================', '▶ 上回合历史快照',
              '[系统宿主] 积分 7 | 经验值 3 | 体力 100 | 商业嗅觉 0', '',
              '==================================================', '【当前持久化状态与BUFF】',
              '▶ 沈知韫', '  - 无', '▶ 苏婉青', '  - 无', '▶ 徐念薇', '  - 无',
              '==================================================', '【回合计数器】', '连续守护回合: 0',
              '【监视状态】', '徐承邺位置：外地']
    for name in ('沈知韫', '徐念薇', '苏婉青', '徐志北'):
        lines.append('徐承邺_' + name + '：警惕 0 | 发现 0 | 发现几率 0')
    lines += ['', '【任务状态】', '当前任务：（无）', '最近完成：（空）', '待发道具：（无）',
              '', '【道具倒计时】', '（空）', '']
    for label, title in [('L1', '▲ 第一层：【即时运存区】'), ('L2', '▲ 第二层：【回想运存区】'),
                         ('L3', '▲ 第三层：【近期事实缓存区】'), ('L4', '▲ 第四层：【深渊纪元浓缩区】')]:
        entries = list(values[label])
        if prologue and label == 'L1':
            entries = ['【1】序幕事实。\n' + rr.PROLOGUE]
        lines += [title, '\n\n'.join(entries) or '（空）', '']
    return '\n'.join(lines)


def syslog(round_number):
    return f'''【SYSTEM_LOG】
ROUND: {round_number}
INTENT: 验收回合
SCENE: 客厅|徐志北,沈知韫
【应查】
must_keys: state.memory, contract.inject, gate.V1
【实查】
query_keys: state.memory, contract.inject, gate.V1
【豁免】
skip: 无
【V1验收】
V1-A: 通过 — 合成验收
V1-B: 通过 — 无括号
V1-C: 通过 — 合成验收
V1-D: 通过 — 合成验收
【事件打标】
HOST: 无
【记忆/所在】
L1: 已写
presence: {{}}
'''


class RoundTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='round-test-', dir=TMP_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '存档').mkdir()
        (self.root / 'txt文件').mkdir()
        for name in ('save_store.py', 'injection_core.py', 'round_runtime.py', 'txt文件/一键注入指南.txt', 'txt文件/事件注册表.json'):
            shutil.copyfile(ROOT / name, self.root / name)
        self.set_memory(memory())
        (self.root / rr.FILES[1]).write_text('▼ 活跃道具区 ▼\n\n（空）\n\n▼ 已过期/已消耗道具历史区 ▼\n\n（当前为空）\n', encoding='utf-8')
        (self.root / 'data.json').write_text('{"round":0,"storyNodes":[]}', encoding='utf-8')
        self.store = rr.RoundStore(self.root)

    def set_memory(self, value):
        (self.root / rr.FILES[0]).write_text(value, encoding='utf-8')

    def snapshot(self):
        return {name: (self.root / name).read_bytes() if (self.root / name).is_file() else None
                for name in (*rr.FILES, rr.META)}

    def request(self, name='request-1'):
        prepared = self.store.prepare()
        number = prepared['current_round']
        return {'schema_version': 1, 'request_id': name, 'base_revision': prepared['base_revision'],
                'current_round': number,
                'story_nodes': [{'type': 'header', 'text': '[居家] 7月22日, 周三, 徐家主宅客厅, 07:20'},
                                {'type': 'narration', 'text': '你把杯子放在桌上，指尖还留着杯壁的温度。'},
                                {'type': 'dialogue', 'speaker': '沈知韫', 'text': '谢谢。'}],
                'memory_deltas': {'l1_new_round': '周三七时二十分，徐家主宅客厅。徐志北放下杯子，沈知韫道谢。终点：二人仍在客厅。',
                                  'presence': {}, 'l1_to_l2_condensed': '', 'l2_to_l3_summary': '', 'l3_to_l4_summary': ''},
                'panel_changes': {}, 'system_log': syslog(number),
                'options_text': '[A. 日常互动]：继续交谈。\n[B. 社交接触]：去看朋友。\n[C. 主动行为]：提出计划。'}

    def assert_rejected(self, request, error=rr.RoundError):
        previous = self.snapshot()
        with self.assertRaises(error):
            self.store.submit(request)
        self.assertEqual(previous, self.snapshot())
        self.assertFalse((self.root / '.round-runtime/journal.json').exists())

    def test_commit_replay_and_no_input_mutation(self):
        request = self.request()
        request['host_events'] = ['日常_温和累进']
        original = copy.deepcopy(request)
        result = self.store.submit(request)
        self.assertEqual('committed', result['status'])
        self.assertTrue(result['optimistic_lock'])
        self.assertEqual(original, request)
        state = self.snapshot()
        replay = self.store.submit(request)
        self.assertTrue(replay['replayed'])
        self.assertEqual(state, self.snapshot())
        self.assertEqual(2, self.store.prepare()['current_round'])
        data = json.loads((self.root / 'data.json').read_text(encoding='utf-8'))
        self.assertEqual(1, data['state_version'])
        self.assertEqual('request-1', data['request_id'])
        reg = json.loads((self.root / 'txt文件/事件注册表.json').read_text(encoding='utf-8'))
        host08 = next(
            e['parameters']
            for g in reg['groups'].values()
            for e in (g['events'] if isinstance(g, dict) else g)
            if isinstance(e, dict) and e.get('id') == 'HOST_08'
        )
        expected_pts = 7 + int(host08['track2_pts_01'])
        expected_exp = 3 + int(host08.get('track2_exp_02', 0))
        self.assertIn(f'[系统宿主] 积分 {expected_pts} | 经验值 {expected_exp}', state[rr.FILES[0]].decode('utf-8'))
        self.assertEqual(1, len(list((self.root / '日志').glob('*.txt'))))

    def test_stale_revision_round_and_request_conflicts(self):
        request = self.request()
        stale = copy.deepcopy(request)
        stale['request_id'] = 'request-2'
        self.store.submit(request)
        self.assert_rejected(stale, rr.ConflictError)
        changed = copy.deepcopy(request)
        changed['story_nodes'][1]['text'] = '不同的内容。'
        self.assert_rejected(changed, rr.ConflictError)
        for value in (1, 3, 99, True, '2'):
            invalid = self.request('next')
            invalid['current_round'] = value
            self.assert_rejected(invalid)

    def test_invalid_nodes_events_options_and_system_log(self):
        base = self.request()
        cases = []
        bad = copy.deepcopy(base); bad['story_nodes'][1]['text'] = '字' * 4001; cases.append(bad)
        bad = copy.deepcopy(base); bad['story_nodes'][2]['speaker'] = '错字角色'; cases.append(bad)
        bad = copy.deepcopy(base); bad['story_nodes'][1]['speaker'] = '徐志北'; cases.append(bad)
        bad = copy.deepcopy(base); bad['host_events'] = ['拼错标签']; cases.append(bad)
        bad = copy.deepcopy(base); bad['host_events'] = ['日常_温和累进'] * 2; cases.append(bad)
        bad = copy.deepcopy(base); bad['memory_deltas']['typo'] = ''; cases.append(bad)
        bad = copy.deepcopy(base); bad['memory_deltas']['l1_new_round'] = ''; cases.append(bad)
        bad = copy.deepcopy(base); bad['micro_state_changes'] = {'沈知韫': {'momentary_ease': 'false'}}; cases.append(bad)
        bad = copy.deepcopy(base); bad['panel_changes'] = {'系统宿主': {'积分': 999}}; cases.append(bad)
        bad = copy.deepcopy(base); bad['options_text'] = '[A. 日常互动]|错误格式'; cases.append(bad)
        bad = copy.deepcopy(base); bad['system_log'] = bad['system_log'].replace('V1-A: 通过', 'V1-A: 失败'); cases.append(bad)
        bad = copy.deepcopy(base); bad['system_log'] += '\nV1-A: 通过 — 另一条\n'; cases.append(bad)
        bad = copy.deepcopy(base); bad['system_log'] = bad['system_log'].replace('ROUND: 1', 'ROUND: 8'); cases.append(bad)
        bad = copy.deepcopy(base); bad['story_nodes'][0]['text'] = '[居家] 日期, 周三, 客厅, 99:99'; cases.append(bad)
        bad = copy.deepcopy(base); bad['schema_version'] = True; cases.append(bad)
        bad = copy.deepcopy(base); bad['memory_deltas']['presence'] = {'沈知韫': {'location': '工作室'}}; cases.append(bad)
        bad = copy.deepcopy(base); bad['memory_deltas']['presence'] = []; cases.append(bad)
        for index, bad in enumerate(cases):
            with self.subTest(case=index):
                self.assert_rejected(bad)
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(rr.RoundError):
                rr.load_request(text)

    def test_check_has_no_commit_or_receipt(self):
        request = self.request()
        before = self.snapshot()
        self.assertEqual('validated', self.store.submit(request, dry_run=True)['status'])
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / '日志').exists())
        self.assertFalse(list((self.root / '.round-runtime').glob('work-*')))
        self.assertEqual('committed', self.store.submit(request)['status'])

    def test_capacity_summaries_and_multiple_layer_transition(self):
        layers = {'L4': [], 'L3': [f'【{n}】事实{n}' for n in range(1, 11)],
                  'L2': [f'【{n}】事实{n}' for n in range(11, 21)],
                  'L1': [f'【{n}】事实{n}' for n in range(21, 24)]}
        self.set_memory(memory(layers))
        request = self.request()
        self.assertEqual(24, request['current_round'])
        self.assert_rejected(request)
        request['memory_deltas']['l1_to_l2_condensed'] = '【21】事实21的因果摘要。'
        self.assert_rejected(request)
        request['memory_deltas']['l2_to_l3_summary'] = '【11-20】这一阶段的事实摘要。'
        self.assert_rejected(request)
        request['memory_deltas']['l3_to_l4_summary'] = '【1-10】早期关键事实。'
        self.store.submit(request)
        self.assertEqual({'L1': 3, 'L2': 1, 'L3': 1, 'L4': 1}, self.store.prepare()['memory_layers'])

    def test_prologue_uses_first_round(self):
        self.set_memory(memory(prologue=True))
        request = self.request()
        self.assertEqual(1, request['current_round'])
        self.store.submit(request)
        self.assertEqual(2, self.store.prepare()['current_round'])
        self.assertNotIn(rr.PROLOGUE, (self.root / rr.FILES[0]).read_text(encoding='utf-8'))

    def test_staged_engine_error_leaves_live_files_untouched(self):
        request = self.request()
        engine = self.root / 'injection_core.py'
        with engine.open('a', encoding='utf-8') as out:
            out.write('\ndef generate_data_json(*args, **kwargs):\n    raise OSError("staged failure")\n')
        self.assert_rejected(request, OSError)
        self.assertFalse((self.root / '日志').exists())

    def test_exception_during_publish_rolls_back(self):
        request = self.request()
        before = self.snapshot()
        original = self.store._publish
        def fail_once(values):
            self.store._publish = original
            rr._atomic(self.root / rr.FILES[0], values[rr.FILES[0]])
            raise OSError('simulated write failure')
        self.store._publish = fail_once
        with self.assertRaises(OSError):
            self.store.submit(request)
        self.assertEqual(before, self.snapshot())
        self.assertEqual('committed', self.store.submit(request)['status'])

    def test_process_death_recovery_before_and_after_commit_marker(self):
        for mode, expected_round in (('prepared', 1), ('committed', 2)):
            with self.subTest(mode=mode):
                if mode == 'committed':
                    shutil.rmtree(self.root / '.round-runtime')
                    self.set_memory(memory())
                    (self.root / 'data.json').write_text('{"round":0,"storyNodes":[]}', encoding='utf-8')
                request = self.request('crash-' + mode)
                request_file = self.root / 'request.json'
                request_file.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
                program = '''import json,os,pathlib,sys
import round_runtime as r
root=pathlib.Path(sys.argv[1]);mode=sys.argv[2]
store=r.RoundStore(root)
if mode=="prepared":
 def interrupt(values):
  r._atomic(root/r.FILES[0],values[r.FILES[0]])
  os._exit(77)
 store._publish=interrupt
else:
 original=r._atomic
 def interrupt(path,data):
  original(path,data)
  if path.name=="journal.json" and json.loads(data).get("phase")=="committed":os._exit(78)
 r._atomic=interrupt
store.submit(json.loads((root/"request.json").read_text()))
'''
                env = dict(os.environ, PYTHONPATH=str(self.root), PYTHONDONTWRITEBYTECODE='1')
                child = subprocess.run([sys.executable, '-B', '-c', program, str(self.root), mode],
                                       cwd=self.root, env=env, capture_output=True, timeout=20)
                self.assertEqual(77 if mode == 'prepared' else 78, child.returncode, child.stderr.decode())
                self.assertTrue((self.root / '.round-runtime/journal.json').exists())
                self.assertEqual(expected_round, self.store.prepare()['current_round'])
                if mode == 'committed':
                    self.assertTrue(self.store.submit(request)['replayed'])
                else:
                    self.assertEqual('committed', self.store.submit(request)['status'])
                self.assertFalse((self.root / '.round-runtime/journal.json').exists())

    def test_competing_requests_only_one_commit(self):
        first = self.request('first')
        second = copy.deepcopy(first); second['request_id'] = 'second'
        def submit(value):
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([sys.executable, '-B', str(self.root / 'round_runtime.py'),
                                     '--root', str(self.root), 'apply', '-'],
                                    input=json.dumps(value, ensure_ascii=False).encode('utf-8'),
                                    capture_output=True, env=env, timeout=20)
            answer = json.loads(result.stdout)
            if answer['ok']:
                return answer['result']['status']
            self.assertEqual('state_conflict', answer['code'], answer)
            return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (first, second)))
        self.assertCountEqual(['committed', 'conflict'], results)
        self.assertEqual(2, self.store.prepare()['current_round'])

    def test_legacy_entrypoint_and_replay_after_new_round(self):
        spec = importlib.util.spec_from_file_location('legacy_test', self.root / 'injection_core.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        request = self.request()
        args = {key: value for key, value in request.items() if key not in {'schema_version', 'request_id', 'base_revision'}}
        result = module.execute_injection(**args)
        self.assertFalse(result['optimistic_lock'])
        self.assertTrue(module.execute_injection(**args)['replayed'])
        self.store.submit(self.request('next-round'))
        replay = module.execute_injection(**args)
        self.assertTrue(replay['replayed'])
        self.assertFalse(replay['is_current'])
        self.assertEqual(3, self.store.prepare()['current_round'])

    def test_presence_npc_item_task_and_events(self):
        request = self.request()
        request['memory_deltas']['presence'] = {'沈知韫': {'location': '工作室', 'reason': '取文件'}}
        request['npc_entries'] = [{'name': '验收秘书', 'identity': '秘书', 'setting': '谨慎', 'faction': '公司'}]
        request['story_nodes'].append({'type': 'dialogue', 'speaker': '验收秘书', 'text': '文件在这里。'})
        request['item_entries'] = [{'name': '验收便签', 'type': '永久性', 'quantity': 1, 'desc': '记录时间'}]
        request['counter_updates'] = {'连续守护回合': 1}
        request['micro_state_changes'] = {'沈知韫': {'momentary_ease': True}}
        request['ds_events'] = {'沈知韫': ['消耗_日常劳作']}
        request['affection_events'] = {'沈知韫': ['社交微幅回馈']}
        request['host_events'] = ['日常_温和累进']
        request['task_issue'] = {'title': '交流', 'target': '沈知韫', 'attr': '好感', 'value': 60, 'tier': 'small', 'item_desc': '便签'}
        self.store.submit(request)
        data = json.loads((self.root / 'data.json').read_text(encoding='utf-8'))
        self.assertEqual('工作室', data['presence']['沈知韫']['location'])
        saved_state = json.loads((self.root / rr.FILES[2]).read_text(encoding='utf-8'))
        self.assertEqual(saved_state['presence']['沈知韫']['location'], '工作室')
        self.assertIn('验收便签', (self.root / rr.FILES[1]).read_text(encoding='utf-8'))
        self.assertIn('TASK-001', (self.root / rr.FILES[0]).read_text(encoding='utf-8'))

    def test_cli_json_result_and_error(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-B', str(self.root / 'round_runtime.py'), '--root', str(self.root)]
        result = subprocess.run(command + ['prepare'], capture_output=True, env=env, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertTrue(json.loads(result.stdout)['ok'])
        result = subprocess.run(command + ['check', '-'], input=b'{"x":1,"x":2}', capture_output=True, env=env, timeout=10)
        self.assertEqual(1, result.returncode)
        self.assertFalse(json.loads(result.stdout)['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

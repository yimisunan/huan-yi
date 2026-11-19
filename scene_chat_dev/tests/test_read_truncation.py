"""Regression checks for file-tool truncation and complete scene read coverage."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import story_reading as sr
from scene_chat import SceneService
import round_runtime as rr

MARKER = '... (file content truncated) ...'


def numbered(lines, begin=1):
    return '\n'.join(f'{i}| {line}' for i, line in enumerate(lines, begin))


class TruncationChecks(unittest.TestCase):
    def setUp(self):
        self.lines = ['{', '完整的角色资料', '较长的关系条目与后续字段', '}']
        self.raw = '\n'.join(self.lines).encode()

    def test_complete_numbered_and_raw_adapters(self):
        self.assertEqual(sr.verified_lines(self.raw, numbered(self.lines)), [1, 2, 3, 4])
        self.assertEqual(sr.verified_lines(self.raw, self.raw.decode()), [1, 2, 3, 4])
        self.assertEqual(sr.verified_lines(self.raw, numbered(self.lines[1:3], 2), 2, 3), [2, 3])

    def test_partial_last_line_requires_complete_reread(self):
        shown = numbered(self.lines[:2]) + '\n3| 较长的关系\n\n' + MARKER
        first = sr.verified_lines(self.raw, shown)
        self.assertEqual(first, [1, 2])
        second = sr.verified_lines(self.raw, numbered(self.lines[2:], 3), 3, 4)
        self.assertEqual(sorted(set(first + second)), [1, 2, 3, 4])
        self.assertFalse(set(range(1, 5)) <= set(first))

    def test_marked_truncation_after_complete_line(self):
        self.assertEqual(sr.verified_lines(self.raw, numbered(self.lines[:2]) + '\n\n' + MARKER), [1, 2])

    def test_unmarked_partial_line_still_rejected(self):
        with self.assertRaises(sr.ReadingError):
            sr.verified_lines(self.raw, numbered(self.lines[:2]) + '\n3| 较长的关系')

    def test_marker_does_not_hide_changed_content(self):
        for line in ('3| 改写的关系', '3| 较长的关系条目与后续字段加字'):
            with self.subTest(line=line), self.assertRaises(sr.ReadingError):
                sr.verified_lines(self.raw, numbered(self.lines[:2]) + '\n' + line + '\n\n' + MARKER)

    def test_only_last_payload_line_may_be_partial(self):
        for shown in ('1| {\n2| 完整\n3| 较长的关系\n\n' + MARKER,
                      '1| {\n2| 完整\n非编号额外内容\n\n' + MARKER):
            with self.subTest(shown=shown), self.assertRaises(sr.ReadingError):
                sr.verified_lines(self.raw, shown)

    def test_wrong_repeated_and_reordered_numbers_rejected(self):
        for shown in ('0| {', '5| }', '1| {\n1| {', '2| 完整的角色资料\n1| {'):
            with self.subTest(shown=shown), self.assertRaises(sr.ReadingError):
                sr.verified_lines(self.raw, shown + '\n\n' + MARKER)
        with self.assertRaises(sr.ReadingError):
            sr.verified_lines(self.raw, numbered(self.lines), 2, 4)

    def test_marker_must_be_terminal(self):
        with self.assertRaises(sr.ReadingError):
            sr.verified_lines(self.raw, '1| {\n2| 完整\n\n' + MARKER + '\nother text')

    def test_scene_requires_union_before_commit_and_keeps_audit(self):
        class Paths:
            def _audit_path(self, path, workspace):
                return path

        temporary = ROOT / 'scene_chat_dev/tmp'
        with tempfile.TemporaryDirectory(prefix='reading-regression-', dir=temporary) as folder:
            work = Path(folder)
            for name in ('txt文件/场景交流规范.md', 'txt文件/知识库/角色类.json',
                         'txt文件/关系称谓查询.jsonl', 'txt文件/关系称谓库.json'):
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            (work / '存档').mkdir()
            (work / '存档/base.txt').write_text('isolated read coverage regression')
            service = SceneService(work, Paths())
            sid = service.create({'cast': ['苏婉青'], 'location': '离线校验'})['scene']['id']
            key = 'scene-read-truncation-regression'
            service.submit({'request_id': key, 'scene_id': sid, 'base_scene_revision': 0,
                            'input': '今天在忙什么，我妈妈总是提到你'})
            task = service.claim()['task']
            packet = json.loads(task['turns'][0]['content'])['packet']
            lines = (work / packet['path']).read_text().splitlines()
            cut = 20
            fragment = lines[cut - 1][:len(lines[cut - 1]) // 2]
            first = {'name': 'read_file', 'parameters': {'path': packet['path']}, 'status': 'success',
                     'result_text': numbered(lines[:cut - 1]) + f'\n{cut}| ' + fragment + '\n\n' + MARKER}
            second = {'name': 'read_file_part', 'parameters': {'path': packet['path'], 'start_line': cut,
                      'end_line': len(lines)}, 'status': 'success', 'result_text': numbered(lines[cut - 1:], cut)}
            proof = {'api': 'Tools.Chat.sendMessageStreaming', 'chat_id': 'offline', 'participant_id': 'offline',
                     'workspace': str(work), 'outcome': {'type': 'committed', 'status': 'completed',
                     'assistant': {'messageTimestamp': 1}}, 'snapshot_message_timestamp': 1, 'tools': [first]}
            text = json.dumps({'messages': [{'kind': 'dialogue', 'speaker': '苏婉青', 'text': '离线校验。'}],
                               'facts_delta': [], 'needs': [], 'handoff': None}, ensure_ascii=False)
            body = {'lease': task['lease'], 'text': text, 'conversation_audit': proof}
            with self.assertRaisesRegex(rr.RoundError, '未完整读取'):
                service.worker(key, 'preflight', body)
            self.assertEqual(service.snapshot(sid)['scene']['revision'], 0)
            proof['tools'] = [first, second]
            self.assertTrue(service.worker(key, 'preflight', body)['ready'])
            service.worker(key, 'result', body)
            service.worker(key, 'result', body)
            restored = SceneService(work, Paths()).snapshot(sid)
            self.assertEqual(restored['scene']['revision'], 1)
            self.assertEqual(len(restored['scene']['history']), 1)
            with service.db() as db:
                saved = json.loads(db.execute('SELECT data FROM jobs WHERE id=?', (key,)).fetchone()[0])
                self.assertEqual(saved['accepted_audit']['tools'][0]['result_text'], first['result_text'])
                self.assertEqual(len(saved['accepted_audit']['tools']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)

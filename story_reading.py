"""Deterministic, task-scoped source projections with verified file-tool receipts."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

CACHE = 'txt文件/.story-reading'
GUIDE = 'txt文件/一键注入指南.txt'
PROMPT = 'txt文件/提示词.md'
KB = tuple('txt文件/知识库/' + name + '.json' for name in ('世界观类', '叙事判断', '角色类', '系统标签类'))
READ_TOOLS = {'read_file', 'read_file_full', 'read_file_part'}
EVENT_SOURCE = 'txt文件/事件注册表.json'
EVENT_FIELDS = ('shame_events', 'depravity_events', 'ds_events', 'affection_events', 'host_events', 'vigilance_events')
VERSION = 1


class ReadingError(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ReadingError('提取源含重复JSON键: ' + key)
        result[key] = value
    return result


def _load(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReadingError('提取源不是有效UTF-8 JSON') from exc


def _path(root, relative):
    root = Path(root).resolve()
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts or ':' in str(relative):
        raise ReadingError('提取路径越界')
    result = (root / value).resolve()
    if not result.is_relative_to(root):
        raise ReadingError('提取路径越出工作区')
    return result


def _anchor(lines, prefix):
    hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(hits) != 1:
        raise ReadingError('提取锚点缺失或重复: ' + prefix)
    return hits[0]


def _selected_spec(key, path, raw, ranges, dependencies=()):
    lines = raw.decode('utf-8').splitlines()
    if any(begin < 1 or end < begin or end > len(lines) for begin, end in ranges):
        raise ReadingError('提取原文范围无效')
    body = '\n'.join(line for begin, end in ranges for line in lines[begin-1:end])
    return {'key': key, 'body': body,
            'sources': [{'path': path, 'sha256': digest(raw), 'ranges': ranges}],
            'completeness': 'selected_source_ranges', 'dependencies': list(dependencies)}


def specifications(root):
    """All bodies are source content, never a second handwritten rule summary."""
    result = {}
    def add(spec):
        key = spec['key']
        if key in result or not isinstance(spec['body'], str) or not spec['body'].strip():
            raise ReadingError('提取key重复或正文为空: ' + key)
        result[key] = spec
    for relative in KB:
        raw = _path(root, relative).read_bytes()
        obj = _load(raw)
        entries = obj.get('data', {}).get('entries', []) or obj.get('entries', [])
        if not entries:
            raise ReadingError('知识库无条目: ' + relative)
        for index, entry in enumerate(entries):
            if entry.get('enabled', True) is not True:
                continue
            body = entry.get('content')
            matches = re.findall(r'※索引key※\s*((?:char|lore|narrative|sys)\.[\w]+)', body or '')
            fallback = entry.get('name', '').split('（', 1)[0]
            if not matches and re.fullmatch(r'(char|lore|narrative|sys)\.[\w]+', fallback):
                matches = [fallback]
            if len(matches) != 1:
                raise ReadingError('知识库条目缺唯一索引key: ' + relative)
            add({'key': matches[0], 'body': body,
                 'sources': [{'path': relative, 'sha256': digest(raw), 'entry': index,
                              'pointer': '#/data/entries/' + str(index) + '/content'}],
                 'completeness': 'complete_entry', 'always_required': bool(entry.get('constantActive', False))})
    raw = _path(root, GUIDE).read_bytes()
    lines = raw.decode('utf-8').splitlines()
    manual = _anchor(lines, '【手动Python入口开始】')
    maintenance = _anchor(lines, '【命令 · 仅手动维护端】')
    semantic = _anchor(lines, '【网页简化语义结果】')
    legacy = _anchor(lines, '【完整回合JSON · 固定执行器/CLI及旧桥接兼容】')
    nodes = _anchor(lines, '🛑 【STORY_NODES 结构死线') - 1
    blocks = []
    starts = [i for i, line in enumerate(lines) if line == '【注册表生成表开始】']
    ends = [i for i, line in enumerate(lines) if line == '【注册表生成表结束】']
    if len(starts) != len(EVENT_FIELDS) or len(ends) != len(EVENT_FIELDS):
        raise ReadingError('事件生成表数量不匹配')
    for field, begin, end in zip(EVENT_FIELDS, starts, ends):
        if begin >= end or field.upper() not in lines[begin+1]:
            raise ReadingError('事件生成表方向不匹配')
        spec = _selected_spec('contract.events.' + field, GUIDE, raw, [[begin+1, end+1]])
        source_raw = _path(root, EVENT_SOURCE).read_bytes()
        spec['sources'].append({'path': EVENT_SOURCE, 'sha256': digest(source_raw), 'pointer': '#/groups/' + field})
        add(spec)
        blocks.append((begin, end+1))
    omitted = [(maintenance, semantic), (legacy, nodes), *blocks]
    keep = [i for i in range(manual) if not any(begin <= i < end for begin, end in omitted)]
    ranges = []
    for i in keep:
        if ranges and i+1 == ranges[-1][1]+1:
            ranges[-1][1] = i+1
        else:
            ranges.append([i+1, i+1])
    add(_selected_spec('contract.inject', GUIDE, raw, ranges,
                       ['contract.events.' + f for f in EVENT_FIELDS]))
    raw = _path(root, PROMPT).read_bytes()
    lines = raw.decode('utf-8').splitlines()
    begin = _anchor(lines, '以下为成功回合的唯一模板')
    end = _anchor(lines, 'SYSTEM_LOG硬规则：')
    add(_selected_spec('rule.prompt', PROMPT, raw, [[1, begin], [end+1, len(lines)]]))
    return result


def _document(spec, task_id, nonce):
    header = {'reading_projection': VERSION, 'task_id': task_id, 'nonce': nonce,
              'key': spec['key'], 'sources': spec['sources'],
              'body_sha256': digest(spec['body'].encode('utf-8')), 'completeness': spec['completeness']}
    return (_json(header) + '\n' + spec['body'] + '\n').encode('utf-8')


def build_bundle(root, task_id):
    specs = specifications(root)
    nonce = uuid.uuid4().hex
    directory = CACHE + '/' + nonce
    mapping = {}
    for key, spec in specs.items():
        rel = directory + '/' + key + '.txt'
        raw = _document(spec, task_id, nonce)
        dest = _path(root, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        mapping[key] = {'path': rel, 'sha256': digest(raw), 'through_line': len(raw.decode('utf-8').splitlines()),
                        'sources': spec['sources'], 'completeness': spec['completeness'],
                        'always_required': spec.get('always_required', False)}
    return {'version': VERSION, 'task_id': task_id, 'nonce': nonce, 'entries': mapping}


def verify_bundle(root, bundle):
    if (not isinstance(bundle, dict) or bundle.get('version') != VERSION
            or not re.fullmatch(r'[0-9a-f]{32}', str(bundle.get('nonce', '')))):
        raise ReadingError('提取目录缺少本次任务身份')
    specs = specifications(root)
    entries = bundle.get('entries')
    if not isinstance(entries, dict) or set(entries) != set(specs):
        raise ReadingError('提取目录key缺失或漂移')
    for key, spec in specs.items():
        entry = entries[key]
        expected_path = CACHE + '/' + bundle['nonce'] + '/' + key + '.txt'
        raw = _document(spec, bundle['task_id'], bundle['nonce'])
        if (entry.get('path') != expected_path or entry.get('sources') != spec['sources']
                or entry.get('sha256') != digest(raw) or _path(root, expected_path).read_bytes() != raw):
            raise ReadingError('提取正文或来源已陈旧: ' + key)
    return specs


def verified_lines(raw, result_text, begin=1, end=None):
    """Authenticate displayed text; requested range or self-reported metadata is insufficient."""
    if not isinstance(result_text, str):
        raise ReadingError('读取回执没有文本')
    lines = raw.decode('utf-8').splitlines()
    end = min(end if end is not None else len(lines), len(lines))
    if begin < 1 or end < begin:
        raise ReadingError('读取回执范围无效')
    # Operit actual tools display `  1| text`; raw exact text is accepted for direct file adapters.
    # The file adapter can stop inside its final displayed line. A clipped
    # prefix is not a verified line; later reads must supply that whole line.
    clipped = re.search(r'\n\n\.\.\. \(file content truncated\) \.\.\.\s*\Z', result_text)
    payload = result_text[:clipped.start()].splitlines() if clipped else result_text.splitlines()
    numbered = []
    for position, line in enumerate(payload):
        match = re.match(r'^\s*(\d+)\| (.*)$', line)
        if match:
            numbered.append((position, int(match.group(1)), match.group(2)))
    if numbered:
        found = set()
        previous = begin - 1
        for position, number, text in numbered:
            if number < begin or number > end or number <= previous:
                raise ReadingError('读取回执正文或行号与当前文件不符')
            previous = number
            expected_line = lines[number-1]
            if text != expected_line:
                if (clipped and position == len(payload) - 1
                        and len(text) < len(expected_line) and expected_line.startswith(text)):
                    continue
                raise ReadingError('读取回执正文或行号与当前文件不符')
            found.add(number)
        return sorted(found)
    expected = '\n'.join(lines[begin-1:end])
    if result_text == expected or result_text == expected + '\n':
        return list(range(begin, end+1))
    raise ReadingError('读取回执没有可核验的实际正文')


def _covers(spans, begin, end):
    reached = begin-1
    for left, right in sorted(spans):
        if right < begin:
            continue
        if left > reached+1:
            return False
        reached = max(reached, right)
        if reached >= end:
            return True
    return False


def check_required(policy, records):
    reads = {}
    for record in records:
        if record.get('status') != 'success' or record.get('name') not in READ_TOOLS:
            continue
        reads.setdefault(record['path'], []).extend((n, n) for n in record.get('verified_lines', []))
    for required in policy['required_reads']:
        covered = _covers(reads.get(required['path'], []), 1, required['through_line'])
        alternative = required.get('source_alternative')
        if not covered and alternative:
            covered = all(_covers(reads.get(alternative['path'], []), a, b) for a, b in alternative['ranges'])
        if not covered:
            raise ReadingError('必读正文未完整取得: ' + required.get('key', required['path']))
    # The first three sources must complete before progressing, including interleaved partial reads.
    steps = policy['required_reads'][:3]
    cursor, seen = 0, {}
    for record in records:
        if record.get('status') != 'success' or record.get('name') not in READ_TOOLS:
            continue
        if cursor >= len(steps):
            break
        step = steps[cursor]
        alt = step.get('source_alternative')
        allowed = {step['path']} | ({alt['path']} if alt else set())
        if record['path'] not in allowed:
            raise ReadingError('前三份正文未按记忆库、指南、法典完成顺序读取')
        seen.setdefault(record['path'], []).extend((n,n) for n in record.get('verified_lines', []))
        done = _covers(seen.get(step['path'], []), 1, step['through_line'])
        if not done and alt:
            done = all(_covers(seen.get(alt['path'], []), a, b) for a, b in alt['ranges'])
        if done:
            cursor += 1
    if cursor != 3:
        raise ReadingError('前三份必读正文未完成')


def projection_facts(root, bundle, records):
    specs = verify_bundle(root, bundle)
    spans = {}
    for record in records:
        if record.get('status') == 'success' and record.get('name') in READ_TOOLS:
            spans.setdefault(record['path'], []).extend((n,n) for n in record.get('verified_lines', []))
    result = {}
    for key, entry in bundle['entries'].items():
        if _covers(spans.get(entry['path'], []), 1, entry['through_line']):
            source = specs[key]['sources'][0]
            result[key] = {'path': source['path'], 'sha256': source['sha256'], 'scope': entry['completeness'],
                           'projection_path': entry['path'], 'projection_sha256': entry['sha256'],
                           'body_sha256': digest(specs[key]['body'].encode('utf-8')), 'sources': entry['sources']}
    return result

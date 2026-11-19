"""Build P12 candidates against the locked P11 baseline."""
from pathlib import Path
import ast
import hashlib
import json

BASE = Path('开发者功能/修订日志/2026.11/回合执行基础')
MP = BASE/'src/安装清单_18.json'
M = json.loads(MP.read_bytes())
C = {c['path']:c for c in M['changes']}
READING_TEXT = '"""Deterministic, task-scoped source projections with verified file-tool receipts."""\nimport hashlib\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport uuid\n\nCACHE = \'txt文件/.story-reading\'\nGUIDE = \'txt文件/一键注入指南.txt\'\nPROMPT = \'txt文件/提示词.md\'\nKB = tuple(\'txt文件/知识库/\' + name + \'.json\' for name in (\'世界观类\', \'叙事判断\', \'角色类\', \'系统标签类\'))\nREAD_TOOLS = {\'read_file\', \'read_file_full\', \'read_file_part\'}\nEVENT_SOURCE = \'txt文件/事件注册表.json\'\nEVENT_FIELDS = (\'shame_events\', \'depravity_events\', \'ds_events\', \'affection_events\', \'host_events\', \'vigilance_events\')\nVERSION = 1\n\n\nclass ReadingError(ValueError):\n    pass\n\n\ndef digest(raw):\n    return hashlib.sha256(raw).hexdigest()\n\n\ndef _json(value):\n    return json.dumps(value, ensure_ascii=False, separators=(\',\', \':\'), allow_nan=False)\n\n\ndef _pairs(items):\n    result = {}\n    for key, value in items:\n        if key in result:\n            raise ReadingError(\'提取源含重复JSON键: \' + key)\n        result[key] = value\n    return result\n\n\ndef _load(raw):\n    try:\n        return json.loads(raw, object_pairs_hook=_pairs)\n    except (UnicodeError, json.JSONDecodeError) as exc:\n        raise ReadingError(\'提取源不是有效UTF-8 JSON\') from exc\n\n\ndef _path(root, relative):\n    root = Path(root).resolve()\n    value = Path(relative)\n    if value.is_absolute() or \'..\' in value.parts or \':\' in str(relative):\n        raise ReadingError(\'提取路径越界\')\n    result = (root / value).resolve()\n    if not result.is_relative_to(root):\n        raise ReadingError(\'提取路径越出工作区\')\n    return result\n\n\ndef _anchor(lines, prefix):\n    hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]\n    if len(hits) != 1:\n        raise ReadingError(\'提取锚点缺失或重复: \' + prefix)\n    return hits[0]\n\n\ndef _selected_spec(key, path, raw, ranges, dependencies=()):\n    lines = raw.decode(\'utf-8\').splitlines()\n    if any(begin < 1 or end < begin or end > len(lines) for begin, end in ranges):\n        raise ReadingError(\'提取原文范围无效\')\n    body = \'\\n\'.join(line for begin, end in ranges for line in lines[begin-1:end])\n    return {\'key\': key, \'body\': body,\n            \'sources\': [{\'path\': path, \'sha256\': digest(raw), \'ranges\': ranges}],\n            \'completeness\': \'selected_source_ranges\', \'dependencies\': list(dependencies)}\n\n\ndef specifications(root):\n    """All bodies are source content, never a second handwritten rule summary."""\n    result = {}\n    def add(spec):\n        key = spec[\'key\']\n        if key in result or not isinstance(spec[\'body\'], str) or not spec[\'body\'].strip():\n            raise ReadingError(\'提取key重复或正文为空: \' + key)\n        result[key] = spec\n    for relative in KB:\n        raw = _path(root, relative).read_bytes()\n        obj = _load(raw)\n        entries = obj.get(\'data\', {}).get(\'entries\', []) or obj.get(\'entries\', [])\n        if not entries:\n            raise ReadingError(\'知识库无条目: \' + relative)\n        for index, entry in enumerate(entries):\n            if entry.get(\'enabled\', True) is not True:\n                continue\n            body = entry.get(\'content\')\n            matches = re.findall(r\'※索引key※\\s*((?:char|lore|narrative|sys)\\.[\\w]+)\', body or \'\')\n            fallback = entry.get(\'name\', \'\').split(\'（\', 1)[0]\n            if not matches and re.fullmatch(r\'(char|lore|narrative|sys)\\.[\\w]+\', fallback):\n                matches = [fallback]\n            if len(matches) != 1:\n                raise ReadingError(\'知识库条目缺唯一索引key: \' + relative)\n            add({\'key\': matches[0], \'body\': body,\n                 \'sources\': [{\'path\': relative, \'sha256\': digest(raw), \'entry\': index,\n                              \'pointer\': \'#/data/entries/\' + str(index) + \'/content\'}],\n                 \'completeness\': \'complete_entry\', \'always_required\': bool(entry.get(\'constantActive\', False))})\n    raw = _path(root, GUIDE).read_bytes()\n    lines = raw.decode(\'utf-8\').splitlines()\n    manual = _anchor(lines, \'【手动Python入口开始】\')\n    maintenance = _anchor(lines, \'【命令 · 仅手动维护端】\')\n    semantic = _anchor(lines, \'【网页简化语义结果】\')\n    legacy = _anchor(lines, \'【完整回合JSON · 固定执行器/CLI及旧桥接兼容】\')\n    nodes = _anchor(lines, \'🛑 【STORY_NODES 结构死线\') - 1\n    blocks = []\n    starts = [i for i, line in enumerate(lines) if line == \'【注册表生成表开始】\']\n    ends = [i for i, line in enumerate(lines) if line == \'【注册表生成表结束】\']\n    if len(starts) != len(EVENT_FIELDS) or len(ends) != len(EVENT_FIELDS):\n        raise ReadingError(\'事件生成表数量不匹配\')\n    for field, begin, end in zip(EVENT_FIELDS, starts, ends):\n        if begin >= end or field.upper() not in lines[begin+1]:\n            raise ReadingError(\'事件生成表方向不匹配\')\n        spec = _selected_spec(\'contract.events.\' + field, GUIDE, raw, [[begin+1, end+1]])\n        source_raw = _path(root, EVENT_SOURCE).read_bytes()\n        spec[\'sources\'].append({\'path\': EVENT_SOURCE, \'sha256\': digest(source_raw), \'pointer\': \'#/groups/\' + field})\n        add(spec)\n        blocks.append((begin, end+1))\n    omitted = [(maintenance, semantic), (legacy, nodes), *blocks]\n    keep = [i for i in range(manual) if not any(begin <= i < end for begin, end in omitted)]\n    ranges = []\n    for i in keep:\n        if ranges and i+1 == ranges[-1][1]+1:\n            ranges[-1][1] = i+1\n        else:\n            ranges.append([i+1, i+1])\n    add(_selected_spec(\'contract.inject\', GUIDE, raw, ranges,\n                       [\'contract.events.\' + f for f in EVENT_FIELDS]))\n    raw = _path(root, PROMPT).read_bytes()\n    lines = raw.decode(\'utf-8\').splitlines()\n    begin = _anchor(lines, \'以下为成功回合的唯一模板\')\n    end = _anchor(lines, \'SYSTEM_LOG硬规则：\')\n    add(_selected_spec(\'rule.prompt\', PROMPT, raw, [[1, begin], [end+1, len(lines)]]))\n    return result\n\n\ndef _document(spec, task_id, nonce):\n    header = {\'reading_projection\': VERSION, \'task_id\': task_id, \'nonce\': nonce,\n              \'key\': spec[\'key\'], \'sources\': spec[\'sources\'],\n              \'body_sha256\': digest(spec[\'body\'].encode(\'utf-8\')), \'completeness\': spec[\'completeness\']}\n    return (_json(header) + \'\\n\' + spec[\'body\'] + \'\\n\').encode(\'utf-8\')\n\n\ndef build_bundle(root, task_id):\n    specs = specifications(root)\n    nonce = uuid.uuid4().hex\n    directory = CACHE + \'/\' + nonce\n    mapping = {}\n    for key, spec in specs.items():\n        rel = directory + \'/\' + key + \'.txt\'\n        raw = _document(spec, task_id, nonce)\n        dest = _path(root, rel)\n        dest.parent.mkdir(parents=True, exist_ok=True)\n        with dest.open(\'xb\') as output:\n            output.write(raw)\n            output.flush()\n            os.fsync(output.fileno())\n        mapping[key] = {\'path\': rel, \'sha256\': digest(raw), \'through_line\': len(raw.decode(\'utf-8\').splitlines()),\n                        \'sources\': spec[\'sources\'], \'completeness\': spec[\'completeness\'],\n                        \'always_required\': spec.get(\'always_required\', False)}\n    return {\'version\': VERSION, \'task_id\': task_id, \'nonce\': nonce, \'entries\': mapping}\n\n\ndef verify_bundle(root, bundle):\n    if (not isinstance(bundle, dict) or bundle.get(\'version\') != VERSION\n            or not re.fullmatch(r\'[0-9a-f]{32}\', str(bundle.get(\'nonce\', \'\')))):\n        raise ReadingError(\'提取目录缺少本次任务身份\')\n    specs = specifications(root)\n    entries = bundle.get(\'entries\')\n    if not isinstance(entries, dict) or set(entries) != set(specs):\n        raise ReadingError(\'提取目录key缺失或漂移\')\n    for key, spec in specs.items():\n        entry = entries[key]\n        expected_path = CACHE + \'/\' + bundle[\'nonce\'] + \'/\' + key + \'.txt\'\n        raw = _document(spec, bundle[\'task_id\'], bundle[\'nonce\'])\n        if (entry.get(\'path\') != expected_path or entry.get(\'sources\') != spec[\'sources\']\n                or entry.get(\'sha256\') != digest(raw) or _path(root, expected_path).read_bytes() != raw):\n            raise ReadingError(\'提取正文或来源已陈旧: \' + key)\n    return specs\n\n\ndef verified_lines(raw, result_text, begin=1, end=None):\n    """Authenticate displayed text; requested range or self-reported metadata is insufficient."""\n    if not isinstance(result_text, str):\n        raise ReadingError(\'读取回执没有文本\')\n    lines = raw.decode(\'utf-8\').splitlines()\n    end = min(end if end is not None else len(lines), len(lines))\n    if begin < 1 or end < begin:\n        raise ReadingError(\'读取回执范围无效\')\n    # Operit actual tools display `  1| text`; raw exact text is accepted for direct file adapters.\n    numbered = []\n    for line in result_text.splitlines():\n        match = re.match(r\'^\\s*(\\d+)\\| (.*)$\', line)\n        if match:\n            numbered.append((int(match.group(1)), match.group(2)))\n    if numbered:\n        found = set()\n        for number, text in numbered:\n            if (number < begin or number > end or number in found or text != lines[number-1]):\n                raise ReadingError(\'读取回执正文或行号与当前文件不符\')\n            found.add(number)\n        return sorted(found)\n    expected = \'\\n\'.join(lines[begin-1:end])\n    if result_text == expected or result_text == expected + \'\\n\':\n        return list(range(begin, end+1))\n    raise ReadingError(\'读取回执没有可核验的实际正文\')\n\n\ndef _covers(spans, begin, end):\n    reached = begin-1\n    for left, right in sorted(spans):\n        if right < begin:\n            continue\n        if left > reached+1:\n            return False\n        reached = max(reached, right)\n        if reached >= end:\n            return True\n    return False\n\n\ndef check_required(policy, records):\n    reads = {}\n    for record in records:\n        if record.get(\'status\') != \'success\' or record.get(\'name\') not in READ_TOOLS:\n            continue\n        reads.setdefault(record[\'path\'], []).extend((n, n) for n in record.get(\'verified_lines\', []))\n    for required in policy[\'required_reads\']:\n        covered = _covers(reads.get(required[\'path\'], []), 1, required[\'through_line\'])\n        alternative = required.get(\'source_alternative\')\n        if not covered and alternative:\n            covered = all(_covers(reads.get(alternative[\'path\'], []), a, b) for a, b in alternative[\'ranges\'])\n        if not covered:\n            raise ReadingError(\'必读正文未完整取得: \' + required.get(\'key\', required[\'path\']))\n    # The first three sources must complete before progressing, including interleaved partial reads.\n    steps = policy[\'required_reads\'][:3]\n    cursor, seen = 0, {}\n    for record in records:\n        if record.get(\'status\') != \'success\' or record.get(\'name\') not in READ_TOOLS:\n            continue\n        if cursor >= len(steps):\n            break\n        step = steps[cursor]\n        alt = step.get(\'source_alternative\')\n        allowed = {step[\'path\']} | ({alt[\'path\']} if alt else set())\n        if record[\'path\'] not in allowed:\n            raise ReadingError(\'前三份正文未按记忆库、指南、法典完成顺序读取\')\n        seen.setdefault(record[\'path\'], []).extend((n,n) for n in record.get(\'verified_lines\', []))\n        done = _covers(seen.get(step[\'path\'], []), 1, step[\'through_line\'])\n        if not done and alt:\n            done = all(_covers(seen.get(alt[\'path\'], []), a, b) for a, b in alt[\'ranges\'])\n        if done:\n            cursor += 1\n    if cursor != 3:\n        raise ReadingError(\'前三份必读正文未完成\')\n\n\ndef projection_facts(root, bundle, records):\n    specs = verify_bundle(root, bundle)\n    spans = {}\n    for record in records:\n        if record.get(\'status\') == \'success\' and record.get(\'name\') in READ_TOOLS:\n            spans.setdefault(record[\'path\'], []).extend((n,n) for n in record.get(\'verified_lines\', []))\n    result = {}\n    for key, entry in bundle[\'entries\'].items():\n        if _covers(spans.get(entry[\'path\'], []), 1, entry[\'through_line\']):\n            source = specs[key][\'sources\'][0]\n            result[key] = {\'path\': source[\'path\'], \'sha256\': source[\'sha256\'], \'scope\': entry[\'completeness\'],\n                           \'projection_path\': entry[\'path\'], \'projection_sha256\': entry[\'sha256\'],\n                           \'body_sha256\': digest(specs[key][\'body\'].encode(\'utf-8\')), \'sources\': entry[\'sources\']}\n    return result\n'
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def swap(text, old, new):
    if text.count(old) == 0 and '\n' not in old:
        matches = [line for line in text.splitlines() if line.lstrip() == old.lstrip()]
        if len(matches) == 1:
            old = matches[0]
    assert text.count(old) == 1, (old[:90], text.count(old))
    return text.replace(old, new)


def method(text, name, replacement):
    tree=ast.parse(text)
    parent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StoryService')
    node=next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(True)
    return ''.join(lines[:node.lineno-1])+replacement.rstrip()+'\n'+''.join(lines[node.end_lineno:])


def stage(rel, text):
    raw=text if isinstance(text,bytes) else text.encode('utf-8')
    Path(C[rel]['staged']).write_bytes(raw)
    C[rel]['after']={'sha256':sha(raw),'bytes':len(raw)}
    C[rel]['character_delta']=len(raw.decode())-len(Path(rel).read_text() if Path(rel).exists() else '')

stage('story_reading.py', READING_TEXT)
rel='.operit/sync.json';obj=json.loads(Path(rel).read_bytes())
if 'txt文件/.story-reading/' not in obj['exclude']:obj['exclude'].append('txt文件/.story-reading/')
stage(rel,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

rel='story_service.py';text=Path(rel).read_text()
text=swap(text,'import relationship_query as rq\n','import relationship_query as rq\nimport story_reading as sr\n')
text=swap(text,'         rq.SOURCE, rq.VIEW, rq.RESOLVER)','         rq.SOURCE, rq.VIEW, rq.RESOLVER, \'story_reading.py\')')
# Bundle identity is distinct on every explicit retry, even if request_id is reused.
a='''        required = []
        for name in REQUIRED_READS:
            text = self.store._path(name).read_text(encoding='utf-8')
            if name == RULES[0]:
                text = text.split('【手动Python入口开始】', 1)[0]
            required.append({'path': name, 'through_line': len(text.splitlines())})'''
z='''        try:
            bundle = sr.build_bundle(self.root, request_id)
        except (ValueError, OSError) as exc:
            raise rr.RoundError('正文提取失败: ' + str(exc)) from exc
        required = []
        for name in REQUIRED_READS:
            projected_key = 'contract.inject' if name == RULES[0] else 'rule.prompt' if name == RULES[2] else None
            if projected_key:
                entry = bundle['entries'][projected_key]
                required.append({'key': projected_key, 'path': entry['path'], 'through_line': entry['through_line'],
                                 'source_alternative': entry['sources'][0]})
            else:
                required.append({'path': name, 'through_line': len(self.store._path(name).read_text(encoding='utf-8').splitlines())})
        for entry in bundle['entries'].values():
            audit[entry['path']] = entry['sha256']'''
text=swap(text,a,z)
text=swap(text,"'rule': '按索引grep定位，再read_file_part读取第1行及所需方向/知情行；不自动读取全表。称谓可省略，知情按人物隔离；来源或视图失配须重试。'", "'rule': '按索引读取实际方向/知情行，不自动读取全表；不得互借秘密，称谓可省略。'")
text=swap(text,"                   'first_read_order': list(REQUIRED_READS[:3]),", "                   'version': sr.VERSION, 'required_keys': sorted(key for key, item in bundle['entries'].items() if item.get('always_required')), 'first_read_order': [item['path'] for item in required[:3]],")
text=swap(text,"'memory_layers': prepared['memory_layers'], 'summary_sources': prepared['summary_sources'],", "'summary_sources': prepared['summary_sources'],")
text=swap(text,"                    'source_baseline': audit, 'audit_origin': 'operit_tool_loop',", "                    'audit_origin': 'operit_tool_loop',\n                    'reading_directory': {'nonce': bundle['nonce'], 'entries': {key: {'path': value['path'], 'through_line': value['through_line']}\n                        for key, value in bundle['entries'].items()}},")
# Values with a single source remain in the internal audit; models do not need to copy them back.
text=swap(text,"        envelope = {'entry_mode':", "        for field in ('fixed_fields', 'optional_defaults', 'node_examples'):\n            output_contract.pop(field, None)\n        envelope = {'entry_mode':")
start=text.index("        system = ('你是网页故事回合生成器。")
end=text.index("        turns = ",start)
text=text[:start]+'''        system = ('你是网页故事回合生成器。entry_mode=story_bridge、retrieval_mode=operit_session。'
                  '按reading_policy依次完整读取记忆库、contract.inject提取文件、法典，再主提示提取文件、索引、data.json；'
                  '前三份完成前不读取其他正文，每轮浏览required_browse目录。'
                  'reading_directory按key指向本任务原文提取件：首行是来源证明，后续是正文，必须全部实际读取；'
                  'read_file截断时用read_file_part补完，失败或正文缺失则阻断，不从历史补回。'
                  '按索引、在场人物与触发项读取相关key并沿指针继续；7条常驻key仍须取得，主角色对白须读其char。'
                  '可读原源兼容，但提取只覆盖对应key/片段，不等于读完整原库。事件表、关系/知情按需读取，知情不互借。'
                  '只允许现有文件只读工具；禁止命令、写文件、外部服务、开发日志与非本任务缓存。'
                  '按output_contract交story_semantics_v1裸JSON：正文、记忆、选项、model_audit语义依据；'
                  '不输出system_log、读取次数、指纹或程序记忆统计；固定身份与空容器由程序补齐。'
                  'V1必须有真实依据，未满足先修正，仍失败则说明阻塞，不能伪造通过。')
'''+text[end:]
text=swap(text,"                'assembly_memory': assembly_memory}", "                'assembly_memory': assembly_memory, 'reading_bundle': bundle}")
# Precise, verifiable audit; no reliance on requested ranges or metadata-only claims.
text=method(text,'_verify_audit','''    def _verify_audit(self, key, proof):
        context = json.loads(self._blob(key, '.context.json').read_bytes())
        if context.get('protocol') != STORY_PROTOCOL or context.get('reading_policy', {}).get('version') != sr.VERSION:
            raise rr.RoundError('旧读取任务需显式重试以刷新正文提取契约')
        if not isinstance(proof, dict) or proof.get('api') != 'Tools.Chat.sendMessageStreaming':
            raise rr.RoundError('缺少Operit正式会话工具审计，未提交')
        outcome = proof.get('outcome', {})
        if not isinstance(outcome, dict):
            raise rr.RoundError('正式会话回执无效')
        assistant = outcome.get('assistant', {})
        if (outcome.get('type') != 'committed' or outcome.get('status') != 'completed'
                or not isinstance(assistant, dict) or type(assistant.get('messageTimestamp')) is not int
                or proof.get('snapshot_message_timestamp') != assistant.get('messageTimestamp')
                or not isinstance(proof.get('chat_id'), str) or not proof['chat_id']
                or not isinstance(proof.get('participant_id'), str) or not proof['participant_id']):
            raise rr.RoundError('正式会话未完成或消息快照不匹配')
        tools = proof.get('tools')
        if not isinstance(tools, list) or not 1 <= len(tools) <= 128:
            raise rr.RoundError('文件工具调用数须为1至128')
        bundle = context['reading_bundle']
        allowed_projections = {item['path'] for item in bundle['entries'].values()}
        records, browse = [], set()
        for call in tools:
            if not isinstance(call, dict) or call.get('name') not in READONLY_TOOLS:
                raise rr.RoundError('会话调用了白名单之外的工具')
            name, params = call['name'], call.get('parameters')
            if not isinstance(params, dict):
                raise rr.RoundError('工具审计参数无效')
            relative = self._audit_path(params.get('path'), proof.get('workspace'))
            if relative == sr.CACHE or relative.startswith(sr.CACHE + '/'):
                current_directory = sr.CACHE + '/' + bundle['nonce']
                if relative not in allowed_projections and not (name == 'list_files' and relative == current_directory):
                    raise rr.RoundError('读取了非本次任务提取件')
            text = call.get('result_text')
            if not isinstance(text, str) or len(text.encode('utf-8')) > 1024 * 1024:
                raise rr.RoundError('工具结果审计文本无效')
            record = {'name': name, 'path': relative, 'status': call.get('status'),
                      'part_id': call.get('part_id'), 'result_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
            if call.get('status') == 'success' and name in READ_TOOLS:
                source = self.store._path(relative)
                if not source.is_file():
                    raise rr.ConflictError('读取过的资料已删除，请重新生成: ' + relative)
                raw = source.read_bytes()
                begin, end = 1, len(raw.decode('utf-8').splitlines())
                if name == 'read_file_part':
                    try:
                        begin = int(params.get('start_line', 1))
                        end = int(params.get('end_line', begin + 99))
                    except (TypeError, ValueError):
                        raise rr.RoundError('分段读取行号无效')
                try:
                    line_numbers = sr.verified_lines(raw, text, begin, end)
                except (ValueError, OSError) as exc:
                    raise rr.RoundError('实际读取正文未核验: ' + str(exc)) from exc
                record.update(verified_lines=line_numbers, source_sha256_at_result=hashlib.sha256(raw).hexdigest())
            if call.get('status') == 'success' and name == 'list_files':
                browse.add(relative)
            records.append(record)
        try:
            sr.check_required(context['reading_policy'], records)
            sr.verify_bundle(self.root, bundle)
        except (ValueError, OSError) as exc:
            raise rr.RoundError('正文读取校验未通过: ' + str(exc)) from exc
        if not set(context['reading_policy']['required_browse']) <= browse:
            raise rr.RoundError('本轮未重新浏览规则、知识库及存档目录')
        self._source_check(context)
        return {**{k: proof.get(k) for k in ('api', 'chat_id', 'participant_id', 'workspace', 'outcome',
                                           'snapshot_message_timestamp', 'started_at', 'completed_at')},
                'verified_tools': records, 'tool_count': len(records), 'required_reads_verified': True}
''')
text=method(text,'_read_coverage','''    def _read_coverage(records):
        ranges = {}
        for record in records:
            if record['status'] == 'success' and record['name'] in READ_TOOLS:
                ranges.setdefault(record['path'], set()).update(record.get('verified_lines', []))
        result = {}
        for path, lines in ranges.items():
            reached = 0
            while reached + 1 in lines:
                reached += 1
            result[path] = reached
        return result
''')
# Preserve the staticmethod decorator already attached above the method.
a="""            spans.append((1, 10 ** 9) if record.get('complete_read') else
                         (record.get('start_line', 0), record.get('end_line', -1)))"""
z="""            spans.extend((line, line) for line in record.get('verified_lines', []))"""
text=swap(text,a,z)
text=swap(text,"        relationship_facts = self._relationship_facts(records)",'''        try:
            projected = sr.projection_facts(self.root, context['reading_bundle'], records)
        except (ValueError, OSError) as exc:
            raise rr.RoundError('提取来源不可核验: ' + str(exc)) from exc
        available.update(projected)
        for item in projected.values():
            for source in item['sources']:
                fingerprints[source['path']] = source['sha256']
        relationship_facts = self._relationship_facts(records)''')
text=swap(text,"        return {'required_reads_verified': True, 'available_keys': available,",'''        required_keys = sorted(key for key, item in context['reading_bundle']['entries'].items() if item.get('always_required'))
        if not set(required_keys) <= available.keys():
            raise rr.RoundError('本轮缺常驻必需正文: ' + ', '.join(sorted(set(required_keys) - available.keys())))
        return {'required_reads_verified': True, 'available_keys': available, 'enforced_keys': required_keys,''')
# Raw source ranges may satisfy bridge-specific required reads without claiming the whole guide was read.
a="        available.update(projected)"
z="""        available.update(projected)
        for required in context['reading_policy']['required_reads']:
            alternative = required.get('source_alternative')
            if alternative and required['key'] not in available:
                spans = [(n,n) for record in records if record['path'] == alternative['path']
                         for n in record.get('verified_lines', [])]
                if all(sr._covers(spans, a, b) for a, b in alternative['ranges']):
                    available[required['key']] = {'path': alternative['path'], 'sha256': alternative['sha256'],
                        'scope': 'selected_source_ranges', 'covered_ranges': alternative['ranges']}
                    fingerprints[alternative['path']] = alternative['sha256']"""
text=swap(text,a,z)
text=swap(text,"            if context.get('protocol') != STORY_PROTOCOL:", "            if context.get('protocol') != STORY_PROTOCOL or context.get('reading_policy', {}).get('version') != sr.VERSION:")
text=swap(text,"        context = json.loads(context_path.read_bytes())", '''        context = json.loads(context_path.read_bytes())
        if context.get('reading_policy', {}).get('version') != sr.VERSION:
            raise rr.RoundError('任务使用旧读取契约，请显式重试以刷新正文提取目录')''')
stage(rel,text)

rel='round_runtime.py';text=Path(rel).read_text()
text=swap(text,"    must = minimum | set(requested)",'''    enforced = facts.get('enforced_keys', [])
    if not isinstance(enforced, list) or any(not isinstance(key, str) for key in enforced):
        raise RoundError('程序必读key清单无效')
    speaker_keys = {'char.' + node['speaker'] for node in result.get('story_nodes', [])
                    if isinstance(node, dict) and node.get('type') == 'dialogue'
                    and isinstance(node.get('speaker'), str) and node.get('speaker') in {'徐志北', '沈知韫', '徐念薇', '苏婉青', '徐承邺'}}
    must = minimum | set(requested) | set(enforced) | speaker_keys''')
stage(rel,text)

rel='txt文件/提示词.md';text=Path(rel).read_text()
text=swap(text,'完整读取一个KB文件可覆盖其中多个key，部分读取不冒充完整条目。','完整读取一个KB文件可覆盖其中多个key；本任务提取件只覆盖其完整正文对应key，原文片段仅覆盖所列范围。部分回执、检索命中或元数据不冒充完整正文。')
text=swap(text,'先完整读取全局记忆库，再读取指南桥接分支与法典；指南可用read_file_part覆盖第1行至reading_policy指定行，不必读取手动Python模板。然后读取本主提示、故事检索索引和data.json。','先完整读取全局记忆库，再按reading_policy读取contract.inject桥接原文提取件与法典；然后读取rule.prompt提取件、故事检索索引和data.json。reading_directory按key给出本次路径及through_line，读取元数据首行和全部正文；截断须补读。原源完整读取或契约列出的等价原文范围仍兼容，不能用声明代替正文。')
text=swap(text,'桥接角色、sys、lore、narrative均从本轮本地文件取得，','桥接角色、sys、lore、narrative从本次key提取件或原始本地文件取得；提取正文与原content逐字一致，来源SHA、任务身份、实际回执和覆盖由程序复核。7条常驻key均须取得，主角色开口须取得其char；沿索引与跨条目指针补查其余触发key。')
text=swap(text,'以下物理读取顺序与审计要求同样适用于正式会话入口；手动入口保留原封装。','正式会话按上述新契约取得等价正文并核验；下列原始路径顺序用于手动入口，桥接前三份仍按记忆库、指南、法典完成顺序。手动封装保留。')
stage(rel,text)
rel='txt文件/故事检索索引.md';text=Path(rel).read_text()
text=swap(text,'所有“世界书”条目从对应本地JSON物理读取，沿指针补查。','所有“世界书”条目优先按reading_directory的key读取本次提取件，正文与原JSON content逐字一致；也可完整读取原库兼容。提取件首行与正文均须取得，程序核验来源、实际回执和完整覆盖；每件仅覆盖对应key，沿指针补查。')
text=swap(text,'- 关系/称谓：','- 桥接指南按contract.inject提供共同原文片段，未包含的事件表按contract.events.<小写事件字段>提取件按需读取；六表及手动/维护原文完整保留。reading_directory中的7条constantActive key仍必读，模型另按人物/事件判断所需key，不因省包装漏约束。\n- 关系/称谓：')
stage(rel,text)
rel='AGENTS.md';text=Path(rel).read_text()
text=swap(text,'网页桥接每轮按 `reading_policy` 与 `txt文件/故事检索索引.md` 物理读取本地知识库；','网页桥接每轮按 `reading_policy`、`reading_directory` 与 `txt文件/故事检索索引.md` 真实读取本次正文提取件或等价原源，核验来源与覆盖；')
text=swap(text,'网页桥接的知识库条目均按索引从本地 JSON 物理读取。','网页桥接的知识库条目按索引从本次key提取件或原始本地JSON取得；提取件由原源逐字生成，必须真实读取正文且经程序核验，缓存不能手工维护。')
stage(rel,text)
rel='开发者功能/开发者说明书/开发者说明书.md';text=Path(rel).read_text()
text=swap(text,'| `round_runtime.py` |','| `story_reading.py` / `txt文件/.story-reading/` | 逐字提取本任务相关权威正文与来源证明、验证实际工具回执；缓存排除同步且非维护源 | 手写摘要、修改角色/事件、模型命令权限 |\n| `round_runtime.py` |')
text=swap(text,'| 2026-11-17 | P11 关系事实与称谓查询 |','| 2026-11-17 | P12 按key正文提取与读取审计 | 保留原始规则，桥接按任务取得逐字正文/相关指南，核验实际回执、覆盖与原源指纹；原源完整读取兼容，模型语义责任保留。见回合执行基础/logs/step_18.md。 |\n| 2026-11-17 | P11 关系事实与称谓查询 |')
stage(rel,text)
M['status']='CANDIDATES_READY';MP.write_text(json.dumps(M,ensure_ascii=False,indent=2)+'\n')
print('CANDIDATES_READY existing=7 new=1')
for c in M['changes']:print('DELTA',c['path'],c['character_delta'],c['after']['bytes'])

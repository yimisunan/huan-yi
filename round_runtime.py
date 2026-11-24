"""Validated, recoverable round submission. Run with --help for the JSON CLI."""
import argparse
import ast
import base64
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
import types
import uuid
from contextlib import contextmanager
import save_store

FILES = (
    '存档/全局记忆库.txt', '存档/徐志北道具图鉴.txt',
    '存档/save_state.json', '存档/四层记忆.json',
    'data.json',
)
META = '.round-runtime/state.json'
RECENT_PLAYBACK = save_store.RECENT_PLAYBACK_PATH
PROLOGUE = '【系统隐藏标记：以上为新游戏序幕锚点，剧情从此刻正式开始计算】'
OPTIONAL = {
    'npc_entries': [], 'item_entries': [], 'system_log': '', 'options_text': '',
    'micro_state_changes': {}, 'shame_events': {}, 'depravity_events': {},
    'ds_events': {}, 'affection_events': {}, 'host_events': [],
    'presence_changes': {}, 'counter_updates': {}, 'vigilance_events': {},
    'task_issue': None,
}
REQUIRED = {'schema_version', 'request_id', 'base_revision', 'current_round',
            'story_nodes', 'memory_deltas', 'panel_changes'}
MEMORY_DELTA_FIELDS = {'l1_new_round', 'new_round_detail', 'l1_to_l2_condensed',
                       'l2_to_l3_summary', 'l3_to_l4_summary', 'new_buffs',
                       'presence', 'presence_changes', 'round_conditions'}
BRIDGE_NESTED_FIELDS = tuple(key for key in OPTIONAL
                            if key not in {'system_log', 'options_text', 'presence_changes'})
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


class RoundError(ValueError):
    code = 'invalid_request'


class ConflictError(RoundError):
    code = 'state_conflict'


class RecoveryError(RoundError):
    code = 'recovery_required'


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RoundError('JSON含重复键: ' + key)
        result[key] = value
    return result


def _bad_number(value):
    raise RoundError('JSON不接受非有限数字: ' + value)


def load_request(text):
    if len(text.encode('utf-8')) > 4 * 1024 * 1024:
        raise RoundError('回合JSON超过4MiB上限')
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_bad_number)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise RoundError('JSON无法解析: ' + str(exc)) from exc


def _json(value):
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           allow_nan=False, indent=2) + '\n').encode('utf-8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise RoundError('输入必须是有限、可序列化的JSON数据') from exc


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _revision(files):
    return _digest(_json({name: _digest(files[name]) if files[name] is not None else None
                          for name in FILES}))


def _text(value, label, limit=None):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise RoundError(label + '必须是非空文本')
    if limit is not None and len(re.sub(r'\s', '', value)) > limit:
        raise RoundError(label + '超出字符硬顶: ' + str(limit))
    return value


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise RoundError(label + '必须是大于等于' + str(minimum) + '的整数')


def _keys(value, allowed, label, required=()):
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise RoundError(label + '必须是对象')
    unknown = value.keys() - set(allowed)
    missing = set(required) - value.keys()
    if unknown or missing:
        raise RoundError(label + ': 未知键=' + str(sorted(unknown)) + '; 缺键=' + str(sorted(missing)))


_ENGINE_CODE_CACHE = {}
_ENGINE_CACHE_GUARD = threading.Lock()


def _engine(root, base):
    """Load trusted project code into an isolated namespace; never change live globals."""
    source_path = root / 'injection_core.py'
    reg_path = root / 'txt文件/事件注册表.json'
    source = source_path.read_bytes()
    try:
        reg_bytes = reg_path.read_bytes()
    except OSError as exc:
        raise RoundError('事件注册表不可用: ' + str(exc)) from exc
    cache_key = (hashlib.sha256(source).hexdigest(), hashlib.sha256(reg_bytes).hexdigest())
    with _ENGINE_CACHE_GUARD:
        code_obj = _ENGINE_CODE_CACHE.get(cache_key)
    module = types.ModuleType('_isolated_round_engine_' + uuid.uuid4().hex)
    module.__file__ = str(base / 'injection_core.py')
    module.__dict__['print'] = lambda *args, **kwargs: None
    module.__dict__['_EVENT_REGISTRY_SOURCE'] = str(reg_path)
    if code_obj is not None:
        exec(code_obj, module.__dict__)
        return module
    code_obj = compile(source, str(source_path), 'exec')
    exec(code_obj, module.__dict__)
    try:
        registry = module._load_event_registry()
        index = {entry['id']: entry for entries in registry['groups'].values() for entry in entries}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'_event_tag', '_event_param'}:
                if not node.args or not isinstance(node.args[0], ast.Constant):
                    raise ValueError('事件引用必须使用稳定内部ID')
                entry = index.get(node.args[0].value)
                if entry is None:
                    raise ValueError('事件注册表缺少引擎引用: ' + str(node.args[0].value))
                if node.func.id == '_event_param' and (len(node.args) != 2 or node.args[1].value not in entry['parameters']):
                    raise ValueError('事件注册表缺少结算参数')
    except (ValueError, OSError) as exc:
        raise RoundError('事件注册表不可用: ' + str(exc)) from exc
    with _ENGINE_CACHE_GUARD:
        if len(_ENGINE_CODE_CACHE) >= 16:
            _ENGINE_CODE_CACHE.clear()
        _ENGINE_CODE_CACHE[cache_key] = code_obj
    return module


def _engine_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise RoundError(str(exc)) from exc


def _memory_state(engine, files):
    if files.get(FILES[0]) is None and files.get(save_store.MEMORY_LAYERS_PATH) is None:
        raise RoundError('缺少全局记忆库；请先用项目开局工具初始化')
    state_obj, layers_obj, _ = save_store.load_bundle(Path(engine.BASE_DIR), files)
    content = (files[FILES[0]].decode('utf-8') if files.get(FILES[0]) is not None
               else save_store.render_memory_txt(state_obj, layers_obj))
    layers = _engine_call(engine._parse_memory_layer_items, content)
    last = 0
    for label in ('L4', 'L3', 'L2', 'L1'):
        for entry in layers[label]:
            start, end = _engine_call(engine._memory_item_range, entry)
            if start <= last:
                raise RoundError('记忆层回合范围重复或逆序: ' + label)
            last = end
    has_only_l1_one = (len(layers['L1']) == 1 and not any(layers[x] for x in ('L2', 'L3', 'L4'))
                       and layers['L1'][0].startswith('【1】'))
    prologue = has_only_l1_one and (bool(layers_obj.get('prologue_active')) or PROLOGUE in layers['L1'][0])
    return content, layers, 0 if prologue else last


def _event_registry(root, engine):
    guide = (root / 'txt文件/一键注入指南.txt').read_text(encoding='utf-8')
    result = {}
    for field, entries in engine._load_event_registry()['groups'].items():
        view = '【注册表生成表开始】\n' + engine._render_event_table(field) + '\n【注册表生成表结束】'
        if guide.count(view) != 1:
            raise RoundError('事件注册表生成视图未同步: ' + field)
        result[field] = {entry['tag'] for entry in entries}
    return result


def _validate_event_fields(root, engine, body):
    registry = _event_registry(root, engine)
    for field, allowed in registry.items():
        events = body[field]
        if field == 'vigilance_events':
            targets = set(engine.VIGILANCE_TARGETS)
        elif field == 'depravity_events':
            targets = (set(engine.DEFAULT_PRESENCE) - {'徐志北'}) | {'徐承邺'}
        else:
            targets = set(engine.DEFAULT_PRESENCE) - {'徐志北'}
        if field == 'host_events':
            tagged = [('系统宿主', events)]
        else:
            _keys(events, targets, field)
            tagged = events.items()
        for name, tags in tagged:
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise RoundError(field + '的标签必须是文本数组')
            if len(tags) != len(set(tags)):
                raise RoundError(field + '含重复标签')
            for tag in tags:
                if engine._event_is_template(field, tag):
                    raise RoundError('事件模板中的X须为实际正整数')
                if not engine._event_accepts(field, tag):
                    raise RoundError(field + '含未知标签: ' + tag)


def _audit_line(value, label, *, reason=False):
    _text(value, label, 2000)
    if '\n' in value or '\r' in value or (reason and value.strip() in {'同上', '见前文', '已读取', '通过', '无'}):
        raise RoundError(label + '须为单行具体依据')
    return value


def _normalize_bridge_fields(result):
    """Relocate known bridge fields without discarding conflicting nonempty values."""
    result = copy.deepcopy(result)
    deltas = result.get('memory_deltas')
    _keys(deltas, MEMORY_DELTA_FIELDS | set(BRIDGE_NESTED_FIELDS), 'memory_deltas')
    relocated = []
    for key in BRIDGE_NESTED_FIELDS:
        if key not in deltas:
            continue
        nested = deltas.pop(key)
        if key not in result:
            result[key] = nested
        elif _json(result[key]) == _json(nested) or _json(nested) == _json(OPTIONAL[key]):
            pass
        elif _json(result[key]) == _json(OPTIONAL[key]):
            result[key] = nested
        else:
            raise RoundError('桥接字段位置冲突: ' + key + '与memory_deltas.' + key)
        relocated.append(key)
    return result, relocated


def _assemble_bridge_result(root, result, identity, facts):
    """Internal bridge adapter. Public submit still requires a complete round request."""
    semantic_required = {'story_nodes', 'memory_deltas', 'options_text', 'model_audit'}
    allowed = (REQUIRED | OPTIONAL.keys() | {'model_audit'}) - {'system_log'}
    _keys(result, allowed, '桥接语义结果', semantic_required)
    result, relocated = _normalize_bridge_fields(result)
    for key, value in identity.items():
        if key in result and _json(result[key]) != _json(value):
            raise RoundError('模型结果的' + key + '与任务不符')
    if 'panel_changes' in result and result['panel_changes'] != {}:
        raise RoundError('普通回合panel_changes必须为空对象')
    audit = result['model_audit']
    audit_required = {'intent', 'scene', 'required_keys', 'evidence', 'v1', 'task', 'breakout'}
    _keys(audit, audit_required | {'notes'}, 'model_audit', audit_required)
    for field in ('intent', 'scene', 'task', 'breakout'):
        _audit_line(audit[field], 'model_audit.' + field, reason=True)
    requested = audit['required_keys']
    if (not isinstance(requested, list) or len(requested) > 64
            or not all(isinstance(key, str) for key in requested) or len(set(requested)) != len(requested)):
        raise RoundError('required_keys须为不重复的key数组')
    if (not isinstance(facts, dict) or facts.get('required_reads_verified') is not True
            or not isinstance(facts.get('available_keys'), dict)
            or type(facts.get('read_call_count')) is not int or facts['read_call_count'] < 3):
        raise RoundError('缺少程序核验的读取事实，不能组装桥接结果')
    available = facts['available_keys']
    minimum = {'state.memory', 'contract.inject', 'gate.V1'}
    enforced = facts.get('enforced_keys', [])
    if not isinstance(enforced, list) or any(not isinstance(key, str) for key in enforced):
        raise RoundError('程序必读key清单无效')
    speaker_keys = {'char.' + node['speaker'] for node in result.get('story_nodes', [])
                    if isinstance(node, dict) and node.get('type') == 'dialogue'
                    and isinstance(node.get('speaker'), str) and node.get('speaker') in {'徐志北', '沈知韫', '徐念薇', '苏婉青', '徐承邺'}}
    must = minimum | set(requested) | set(enforced) | speaker_keys
    if not must <= available.keys():
        raise RoundError('必需key未完整读取: ' + ', '.join(sorted(must - available.keys())))
    evidence = audit['evidence']
    _keys(evidence, available.keys(), 'model_audit.evidence', must)
    for key, value in evidence.items():
        _audit_line(value, 'evidence.' + key, reason=True)
    v1 = audit['v1']
    labels = ('V1-A', 'V1-B', 'V1-C', 'V1-D')
    _keys(v1, labels, 'model_audit.v1', labels)
    for label in labels:
        _keys(v1[label], {'status', 'reason'}, label, {'status', 'reason'})
        if v1[label]['status'] != '通过':
            raise RoundError(label + '未明确通过，程序不代填语义结论')
        _audit_line(v1[label]['reason'], label + '.reason', reason=True)
    notes = audit.get('notes', [])
    if not isinstance(notes, list) or len(notes) > 3:
        raise RoundError('model_audit.notes须为最多三行的数组')
    for note in notes:
        _audit_line(note, 'notes')
    body = {key: copy.deepcopy(result.get(key, value)) for key, value in OPTIONAL.items()
            if key not in {'system_log', 'options_text'}}
    body.update({key: copy.deepcopy(result[key]) for key in ('story_nodes', 'memory_deltas', 'options_text')})
    body.update(copy.deepcopy(identity), panel_changes={})
    _keys(body['memory_deltas'], MEMORY_DELTA_FIELDS, 'memory_deltas')
    l1 = body['memory_deltas'].get('l1_new_round') or body['memory_deltas'].get('new_round_detail')
    _text(l1, 'l1_new_round', 280)
    if 'round_conditions' not in body['memory_deltas']:
        raise RoundError('story_semantics_v1须提供memory_deltas.round_conditions语义条件')
    _validate_event_fields(root, _engine(root, root), body)
    _round_conditions(body['memory_deltas']['round_conditions'], body)
    compact = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    lines = ['【SYSTEM_LOG】', 'ROUND: ' + str(identity['current_round']),
             'INTENT: ' + audit['intent'], 'SCENE: ' + audit['scene'], '',
             '【应查】', 'must_keys: ' + ', '.join(sorted(must)), '',
             '【实查】', 'query_keys: ' + ', '.join(sorted(available)), '',
             '【读取审计】', 'entry_mode: story_bridge', '来源：Operit本轮文件工具（程序核验）',
             '本回内容读取工具调用次数：' + str(facts['read_call_count']),
             'source_sha256: ' + compact(facts['source_fingerprints']),
             '读取覆盖: ' + compact(available), '', '【阅据】',
             '程序记忆事实: ' + compact(facts['memory']),
             *[key + '（模型依据）: ' + evidence[key] for key in sorted(evidence)], '',
             '【豁免】', 'skip: 无', '', '【V1验收】',
             *[label + ': ' + v1[label]['status'] + ' — ' + v1[label]['reason'] for label in labels], '',
             '【事件打标】']
    for label, field in (('SHAME', 'shame_events'), ('DEPRAVITY', 'depravity_events'), ('DS', 'ds_events'),
                         ('AFFECTION', 'affection_events'), ('HOST', 'host_events'), ('VIGILANCE', 'vigilance_events')):
        lines.append(label + ': ' + (compact(body[field]) if body[field] else '无'))
    lines.extend(['TASK（模型提议）: ' + audit['task'], '破局（模型判断）: ' + audit['breakout'], '',
                  '【记忆/所在】', 'L1（拟提交）: ' + compact(l1),
                  'presence（拟提交）: ' + compact(body['memory_deltas'].get('presence') or
                      body['memory_deltas'].get('presence_changes') or body['presence_changes']),
                  'layer_note: ' + compact(facts['memory']), '', '【备注】',
                  '读取/身份/事件清单为程序事实；V1及人物因果依据为模型判断，不构成程序语义证明。', *notes])
    if relocated:
        lines.extend(['', '【字段归位】', 'memory_deltas中的合法可选字段已移至顶层: ' + compact(relocated)])
    body['system_log'] = '\n'.join(lines)
    return body



def _validate(root, request, files, allow_panel_override):
    _keys(request, REQUIRED | OPTIONAL.keys(), '回合', REQUIRED)
    if type(request['schema_version']) is not int or request['schema_version'] != 1:
        raise RoundError('schema_version必须为1')
    if not isinstance(request['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', request['request_id']):
        raise RoundError('request_id须为1至128位字母、数字或_.:-')
    if not isinstance(request['base_revision'], str) or not re.fullmatch(r'[0-9a-f]{64}', request['base_revision']):
        raise RoundError('base_revision必须使用prepare返回的SHA-256状态版本')
    _integer(request['current_round'], 'current_round', 1)
    engine = _engine(root, root)
    content, layers, previous = _memory_state(engine, files)
    if request['base_revision'] != _revision(files):
        raise ConflictError('状态版本已改变，请重新准备回合；旧结果未写入')
    if request['current_round'] != previous + 1:
        raise ConflictError('下一合法回合为' + str(previous + 1))
    body = {key: copy.deepcopy(request.get(key, value)) for key, value in OPTIONAL.items()}
    body.update({key: copy.deepcopy(request[key]) for key in ('current_round', 'story_nodes', 'memory_deltas', 'panel_changes')})
    _keys(body['panel_changes'], engine.TASK_WHITELIST.keys() | {'徐承邺'}, 'panel_changes')
    if body['panel_changes'] and not allow_panel_override:
        raise RoundError('普通回合panel_changes必须为空；人工覆写需在调用端显式授权')
    attributes = {'积分', '经验值', '体力', '魅力', '商业嗅觉', '好感', '堕落', '欲望', '羞耻', '高潮', '内射', '怀孕', '被动'}
    for name, changes in body['panel_changes'].items():
        _keys(changes, attributes, 'panel_changes.' + name)
        for attr, value in list(changes.items()):
            if attr == '怀孕':
                if type(value) is not bool:
                    raise RoundError('怀孕覆写须为布尔值')
            elif attr == '被动':
                if isinstance(value, str) and re.fullmatch(r'Lv\.?[0-4]', value.strip()):
                    changes[attr] = 'Lv.' + value.strip()[-1]
                elif type(value) is int and 0 <= value <= 4:
                    changes[attr] = 'Lv.' + str(value)
                else:
                    raise RoundError('被动覆写须为0-4整数或Lv.0~Lv.4')
            else:
                _integer(value, 'panel_changes.' + name + '.' + attr)
    known = set(engine.DEFAULT_PRESENCE) | {'徐承邺'}
    if not isinstance(body['npc_entries'], list):
        raise RoundError('npc_entries必须是数组')
    for npc in body['npc_entries']:
        _keys(npc, {'name', 'identity', 'setting', 'faction'}, 'npc_entries', {'name'})
        for key, value in npc.items():
            _text(value, 'npc_entries.' + key)
            if '\n' in value or '\r' in value:
                raise RoundError('NPC字段不接受换行')
        known.add(npc['name'])
    nodes = body['story_nodes']
    if not isinstance(nodes, list) or not nodes or len(nodes) > 1000:
        raise RoundError('story_nodes必须包含1至1000个节点')
    if not isinstance(nodes[0], dict) or nodes[0].get('type') != 'header':
        raise RoundError('首个节点必须是header')
    craft_count = 0
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise RoundError('节点必须是对象')
        kind = _text(node.get('type'), 'node.type')
        fields = {'type', 'text', 'speaker'} if kind == 'dialogue' else {'type', 'text'}
        if kind not in {'header', 'narration', 'dialogue', 'craft_note'}:
            raise RoundError('未知节点类型: ' + str(kind))
        _keys(node, fields, 'node[' + str(index) + ']', fields)
        text = _text(node['text'], 'node.text', 4000 if kind in {'narration', 'craft_note'} else None)
        if kind == 'header':
            stamp = re.sub(r'^\s*\[(居家|外出)\]\s*', '', text).strip()
            parts = [part.strip() for part in re.split('[,，]', stamp)]
            if (len(parts) != 4 or not re.fullmatch(r'\d{1,2}月\d{1,2}日', parts[0])
                    or not re.fullmatch(r'(周|星期)[一二三四五六日天]', parts[1])
                    or not parts[2] or not re.fullmatch(r'([01]?\d|2[0-3]):[0-5]\d', parts[3])):
                raise RoundError('header须为可选[居家]/[外出]加日期,周几,地点,HH:MM')
        elif kind == 'dialogue':
            _text(node['speaker'], 'node.speaker')
            if node['speaker'] not in known:
                raise RoundError('未登记说话人: ' + str(node['speaker']))
        elif kind == 'craft_note':
            craft_count += 1
    if craft_count > 3:
        raise RoundError('craft_note每回最多3条')
    deltas = body['memory_deltas']
    _keys(deltas, MEMORY_DELTA_FIELDS, 'memory_deltas')
    _text(deltas.get('l1_new_round') or deltas.get('new_round_detail'), 'l1_new_round', 280)
    if re.match(r'^\s*【\d', deltas.get('l1_new_round') or deltas.get('new_round_detail')):
        raise RoundError('L1正文禁止手写回合标记，由引擎自动盖戳')
    for key in ('l1_new_round', 'new_round_detail', 'l1_to_l2_condensed', 'l2_to_l3_summary', 'l3_to_l4_summary'):
        if key in deltas and not isinstance(deltas[key], str):
            raise RoundError(key + '必须是文本')
    for key in ('presence', 'presence_changes'):
        value = deltas.get(key, {})
        _keys(value, engine.DEFAULT_PRESENCE, 'memory_deltas.' + key)
        if value and body['presence_changes'] and value != body['presence_changes']:
            raise RoundError('人物所在的多个入口存在冲突')
        if value:
            body['presence_changes'] = value
    _keys(body['presence_changes'], engine.DEFAULT_PRESENCE, 'presence')
    for name, value in body['presence_changes'].items():
        if isinstance(value, str):
            parts = re.split('[|｜]', value)
            if len(parts) != 2:
                raise RoundError('人物移动须含地点与事由')
            value = dict(zip(('location', 'reason'), parts))
        _keys(value, {'location', 'reason'}, 'presence.' + name, {'location', 'reason'})
        for key, entry in value.items():
            _text(entry, 'presence.' + key)
            if any(c in entry for c in '\r\n|｜'):
                raise RoundError('人物所在字段不接受换行或分隔符')
    _keys(deltas.get('new_buffs', {}), ROUND_NPCS, 'new_buffs')
    for value in deltas.get('new_buffs', {}).values():
        _text(value, 'new_buffs')
    _keys(body['micro_state_changes'], ROUND_NPCS, 'micro_state_changes')
    for changes in body['micro_state_changes'].values():
        _keys(changes, {'momentary_ease', 'residual_tension', 'confusion_debt'}, 'micro_state')
        if any(type(v) is not bool for v in changes.values()):
            raise RoundError('微状态值须为布尔值')
    _keys(body['counter_updates'], body['counter_updates'].keys() if isinstance(body['counter_updates'], dict) else (), 'counter_updates')
    for key, value in body['counter_updates'].items():
        if not re.fullmatch(r'\w{1,64}', key):
            raise RoundError('计数器名称非法')
        _integer(value, 'counter_updates.' + key)
    _validate_event_fields(root, engine, body)
    if 'round_conditions' in deltas:
        _round_conditions(deltas['round_conditions'], body)
    if not isinstance(body['item_entries'], list):
        raise RoundError('item_entries必须是数组')
    for item in body['item_entries']:
        _keys(item, {'id', 'name', 'type', 'desc', 'quantity', 'obtain_round', 'status', 'location',
                     'target', 'duration', 'remaining', 'expire_rule', 'usage_record', 'remark',
                     'system_effect', 'giftable', 'action'}, 'item_entries', {'name'})
        _text(item['name'], 'item.name')
        if item.get('action', 'add') not in {'add', 'update', 'consume', 'archive'}:
            raise RoundError('道具action非法')
        if 'quantity' in item:
            _integer(item['quantity'], 'item.quantity', 1)
        for k, v in item.items():
            if k == 'giftable':
                if not isinstance(v, (bool, str)):
                    raise RoundError('道具giftable须为布尔或文本')
            elif not isinstance(v, (str, int)) or isinstance(v, bool):
                raise RoundError('道具字段须为文本或整数')
    task = body['task_issue']
    if task is not None:
        _keys(task, {'title', 'target', 'attr', 'value', 'tier', 'item_desc'}, 'task_issue',
              {'title', 'target', 'attr', 'value', 'tier', 'item_desc'})
        for key in ('title', 'target', 'attr', 'tier', 'item_desc'):
            _text(task[key], 'task_issue.' + key)
        _integer(task['value'], 'task.value', 1)
        if task['target'] not in engine.TASK_WHITELIST or task['attr'] not in engine.TASK_WHITELIST[task['target']] or task['tier'] not in engine.TASK_REWARDS:
            raise RoundError('任务目标、属性或奖励档位非法')
        task_state = engine._parse_task_block(content)
        if task_state is None:
            raise RoundError('记忆库缺少任务状态块')
        if task_state.get('current') and task_state['current'].get('status') == '进行中':
            raise RoundError('已有进行中任务，不接受新任务')
    if body['item_entries'] and files.get(FILES[1]) is None and files.get(save_store.SAVE_STATE_PATH) is None:
        raise RoundError('缺少待更新的存档文件: ' + FILES[1])
    _text(body['system_log'], 'system_log')
    _engine_call(engine.validate_system_log_scheme_a, body['system_log'])
    rounds = re.findall(r'^\s*ROUND\s*[:：]\s*(\d+)\s*$', body['system_log'], re.M)
    if rounds != [str(body['current_round'])]:
        raise RoundError('SYSTEM_LOG的ROUND须与提交回合一致且仅出现一次')
    options = _text(body['options_text'], 'options_text')
    letters = []
    for line in options.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line in {'【系统商城已开启】', '【系统推演：当前可选行动】', '系统推演：当前可选行动'}:
            continue
        match = re.fullmatch(r'\[([A-Z])\.\s*([^\]\r\n]+)\]\s*[:：]\s*(\S.*)', line)
        if not match:
            raise RoundError('每条选项须为[X. 名称]：内容，并独占一行')
        letters.append(match.group(1))
    if letters[:3] != ['A', 'B', 'C'] or letters != sorted(set(letters)):
        raise RoundError('选项须从A/B/C依次排列且不能重复')
    _engine_call(engine.validate_memory_transition_preflight, body['current_round'], deltas)
    return body


MICRO_STATES = ('momentary_ease', 'residual_tension', 'confusion_debt')
ROUND_NPCS = ('沈知韫', '苏婉青', '徐念薇')
CONDITION_NPCS = (*ROUND_NPCS, '徐承邺')
BREAKOUT_LIMITS = {'破局_日常冗余': 5, '破局_模式重复': 3, '破局_社交淤积': 3, '破局_张力淤积': 2}
LIFE_ANCHOR = '【回合生命周期】'
GUARD_EVENT_ID = 'HOST_07'
EXHAUST_EVENT_ID = 'DS_11'
ROUND_CONDITION_FIELDS = {'intensity', 'effective_progress', 'scene', 'npc', 'action_changed',
                          'stress_signals', 'breakout_triggered'}


INTIMATE_B_ALLOWED_SHAME_TAGS = frozenset({'C烈度_轻度', 'C烈度_中度'})


def _round_conditions(value, body, *, intimate_mode=False):
    _keys(value, ROUND_CONDITION_FIELDS, 'round_conditions', ROUND_CONDITION_FIELDS)
    if value['intensity'] not in ('A', 'B', 'C'):
        raise RoundError('round_conditions.intensity须为A/B/C，按已发生行为判断')
    for key in ('effective_progress', 'action_changed'):
        if type(value[key]) is not bool:
            raise RoundError('round_conditions.' + key + '须为布尔值')
    _audit_line(value['scene'], 'round_conditions.scene')
    if value['npc'] is not None and value['npc'] not in CONDITION_NPCS:
        raise RoundError('round_conditions.npc须为已登记主要角色名或null')
    _integer(value['stress_signals'], 'round_conditions.stress_signals')
    triggers = value['breakout_triggered']
    if (not isinstance(triggers, list) or not all(isinstance(k, str) and k in BREAKOUT_LIMITS for k in triggers)
            or len(triggers) != len(set(triggers))):
        raise RoundError('breakout_triggered须为不重复的四破局计数键数组')
    c_shame_tags = [tag for tags in body['shame_events'].values() for tag in tags if tag.startswith('C烈度_')]
    if c_shame_tags:
        if value['intensity'] == 'A':
            raise RoundError('A烈度条件与C烈度事件矛盾')
        if value['intensity'] == 'B':
            if not intimate_mode:
                raise RoundError('A/B烈度条件与C烈度事件矛盾')
            disallowed = [t for t in c_shame_tags if t not in INTIMATE_B_ALLOWED_SHAME_TAGS]
            if disallowed:
                raise RoundError('亲密进行态B档仅允许C烈度_轻度/中度，深度/重度须走C档：' + '、'.join(disallowed))
    if value['npc'] is None and value['stress_signals']:
        raise RoundError('应激信号须有明确NPC')
    return value


def _validate_scene_state(raw, active_cast, building_cast=None):
    """Validate optional resolution.scene_state dict (privacy/sub_location/present_actors/attire/traces/inter_heroine/intimate_active)."""
    if raw is None or raw == '':
        return None
    if not isinstance(raw, dict):
        raise RoundError('resolution.scene_state须为对象或空值')
    allowed_keys = {
        'intimate_active', 'privacy', 'sub_location', 'present_actors',
        'attire_updates', 'trace_adds', 'inter_heroine_deltas',
    }
    _keys(raw, allowed_keys, 'scene_state')
    out = {}
    if 'intimate_active' in raw and raw['intimate_active'] not in (None, ''):
        if type(raw['intimate_active']) is not bool:
            raise RoundError('scene_state.intimate_active须为布尔值')
        out['intimate_active'] = raw['intimate_active']
    if 'privacy' in raw and raw['privacy'] not in (None, ''):
        priv = str(raw['privacy']).strip()
        if priv not in save_store.PRIVACY_LEVELS:
            raise RoundError('scene_state.privacy须为合法隐私枚举：' + '/'.join(save_store.PRIVACY_LEVELS))
        out['privacy'] = priv
    if 'sub_location' in raw and raw['sub_location'] not in (None, ''):
        _text(raw['sub_location'], 'scene_state.sub_location', 48)
        out['sub_location'] = raw['sub_location'].strip()
    valid_pool = set(active_cast or ()) | set(building_cast or ())
    if 'present_actors' in raw and raw['present_actors'] not in (None, ''):
        pa = raw['present_actors']
        if not isinstance(pa, list) or not all(isinstance(x, str) for x in pa):
            raise RoundError('scene_state.present_actors须为角色名数组')
        cleaned = [x.strip() for x in pa if x.strip() in (valid_pool or set(CONDITION_NPCS))]
        out['present_actors'] = list(dict.fromkeys(cleaned))
    if 'attire_updates' in raw and raw['attire_updates'] not in (None, ''):
        au = raw['attire_updates']
        if not isinstance(au, dict):
            raise RoundError('scene_state.attire_updates须为对象')
        clean_au = {}
        for who, patch in au.items():
            if who not in ROUND_NPCS or not isinstance(patch, dict):
                continue
            item = {}
            if isinstance(patch.get('outfit'), str) and patch['outfit'].strip():
                item['outfit'] = patch['outfit'].strip()[:64]
            if patch.get('state') in save_store.ATTIRE_STATES:
                item['state'] = patch['state']
            if item:
                clean_au[who] = item
        if clean_au:
            out['attire_updates'] = clean_au
    if 'trace_adds' in raw and raw['trace_adds'] not in (None, ''):
        ta = raw['trace_adds']
        if not isinstance(ta, dict):
            raise RoundError('scene_state.trace_adds须为对象')
        clean_ta = {}
        for who, arr in ta.items():
            if who not in ROUND_NPCS or not isinstance(arr, list):
                continue
            kept = []
            for tr in arr[:2]:
                if not isinstance(tr, dict):
                    continue
                kind = str(tr.get('kind') or '').strip()[:24]
                if not kind:
                    continue
                desc = str(tr.get('desc') or kind).strip()[:80]
                turns = int(tr.get('turns') or 4) if isinstance(tr.get('turns'), int) else 4
                kept.append({'kind': kind, 'desc': desc, 'turns': max(1, min(12, turns)), 'visible': bool(tr.get('visible', True))})
            if kept:
                clean_ta[who] = kept
        if clean_ta:
            out['trace_adds'] = clean_ta
    if 'inter_heroine_deltas' in raw and raw['inter_heroine_deltas'] not in (None, ''):
        ih = raw['inter_heroine_deltas']
        if not isinstance(ih, dict):
            raise RoundError('scene_state.inter_heroine_deltas须为对象')
        clean_ih = {}
        for pair, delta in ih.items():
            if pair in save_store.INTER_HEROINE_PAIRS and isinstance(delta, int) and not isinstance(delta, bool):
                step = max(-1, min(1, delta))
                if step != 0:
                    clean_ih[pair] = step
        if clean_ih:
            out['inter_heroine_deltas'] = clean_ih
    return out or None


def _current_micro(content):
    current = content.split('▶ 上回合历史快照', 1)[0].split('▲ 第一层：', 1)[0]
    match = re.search(r'^【当前激活微状态】[ \t]*\n(.*?)(?=^={5,}|^【|\Z)', current, re.M | re.S)
    states = {}
    if match:
        for part in re.finditer(r'^▶[ \t]*([^\r\n]+)\n(.*?)(?=^▶|\Z)', match[1], re.M | re.S):
            name = part[1].strip()
            if name in states or name not in ROUND_NPCS:
                raise RoundError('微状态角色重复或未知: ' + name)
            found = re.findall(r'\b(' + '|'.join(MICRO_STATES) + r'):[ \t]*(true|false)\b', part[2])
            if len(found) != len(set(k for k, _ in found)):
                raise RoundError('微状态键重复: ' + name)
            states[name] = {key: value == 'true' for key, value in found}
    return {name: {key: states.get(name, {}).get(key, False) for key in MICRO_STATES} for name in ROUND_NPCS}


def _write_micro(content, states):
    marker = content.find('▶ 上回合历史快照')
    if marker == -1:
        marker = content.find('▲ 第一层：')
    current, tail = content[:marker], content[marker:]
    block = '【当前激活微状态】\n' + ''.join('▶ ' + name + '\n  ' + ' | '.join(
        key + ': ' + str(states[name][key]).lower() for key in MICRO_STATES) + '\n' for name in ROUND_NPCS) + '\n'
    pattern = r'^【当前激活微状态】[ \t]*\n.*?(?=^={5,}|^【|\Z)'
    if re.search(pattern, current, re.M | re.S):
        current = re.sub(pattern, lambda _: block, current, count=1, flags=re.M | re.S)
    else:
        current += '\n' + block
    return current + tail


def _counters(content):
    pre = content.split('▲ 第一层：', 1)[0]
    match = re.search(r'^【回合计数器】[ \t]*\n(.*?)(?=^【|^▲|^={5,}|\Z)', pre, re.M | re.S)
    if not match:
        return {}
    result = {}
    for line in match[1].splitlines():
        if not line.strip():
            continue
        m = re.fullmatch(r'\s*(\w{1,64}):[ \t]*(\d+)[ \t]*', line)
        if not m or m[1] in result:
            raise RoundError('回合计数器格式损坏或键重复')
        result[m[1]] = int(m[2])
    return result


def _write_counters(content, values):
    block = '【回合计数器】\n' + ''.join('  ' + key + ': ' + str(value) + '\n' for key, value in values.items()) + '\n'
    pattern = r'^【回合计数器】[ \t]*\n.*?(?=^【|^▲|^={5,}|\Z)'
    if re.search(pattern, content, re.M | re.S):
        return re.sub(pattern, lambda _: block, content, count=1, flags=re.M | re.S)
    index = content.find('▲ 第一层：')
    return content[:index] + block + content[index:]


def _lifecycle_meta(content, previous):
    pre = content.split('▲ 第一层：', 1)[0]
    matches = re.findall(r'^' + re.escape(LIFE_ANCHOR) + r'[ \t]*\n([^\n]*)', pre, re.M)
    if not matches:
        if LIFE_ANCHOR in pre:
            raise RoundError('回合生命周期元数据格式损坏')
        return {'version': 1, 'round': previous, 'micro': {}, 'ab_streak': 0, 'scopes': {}, 'legacy_counters': {}}
    if len(matches) != 1:
        raise RoundError('回合生命周期块重复')
    try:
        value = load_request(matches[0])
        fields = {'version', 'round', 'micro', 'ab_streak', 'scopes', 'legacy_counters'}
        _keys(value, fields, '生命周期', fields)
        if type(value['version']) is not int or value['version'] != 1 or type(value['round']) is not int or value['round'] != previous:
            raise RoundError('生命周期回合与存档不一致')
        _integer(value['ab_streak'], 'ab_streak')
        _keys(value['micro'], ROUND_NPCS, 'micro期限')
        for name, entries in value['micro'].items():
            _keys(entries, MICRO_STATES, 'micro期限.' + name)
            for item in entries.values():
                _keys(item, {'observed_round', 'origin'}, '期限', {'observed_round', 'origin'})
                _integer(item['observed_round'], 'observed_round', 1)
                if item['observed_round'] > previous or item['origin'] not in ('activated', 'legacy_observed'):
                    raise RoundError('微状态期限非法')
        _keys(value['scopes'], BREAKOUT_LIMITS, 'scopes')
        for scope in value['scopes'].values():
            if not isinstance(scope, str):
                raise RoundError('scope须为程序序列化文本')
        _keys(value['legacy_counters'], value['legacy_counters'].keys() if isinstance(value['legacy_counters'], dict) else (), 'legacy_counters')
        for item in value['legacy_counters'].values():
            _keys(item, {'value', 'observed_round'}, '旧计数观测', {'value', 'observed_round'})
            _integer(item['value'], '旧计数值'); _integer(item['observed_round'], '旧计数观测回合', 1)
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise RoundError('回合生命周期元数据损坏，禁止重置: ' + str(exc)) from exc


def _write_lifecycle(content, meta):
    block = LIFE_ANCHOR + '\n' + json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n\n'
    pattern = r'^' + re.escape(LIFE_ANCHOR) + r'[ \t]*\n[^\n]*\n(?:\n)?'
    if re.search(pattern, content, re.M):
        return re.sub(pattern, lambda _: block, content, count=1, flags=re.M)
    index = content.find('▲ 第一层：')
    return content[:index] + block + content[index:]


def _derive_lifecycle(engine, body, content, *, active_cast=None):
    """Derive once in the disposable settlement, before any journal publication."""
    guard_tag = engine._event_tag(GUARD_EVENT_ID)
    exhaust_tag = engine._event_tag(EXHAUST_EVENT_ID)
    result = copy.deepcopy(body)
    current = body['current_round']
    meta = _lifecycle_meta(content, current - 1)
    conditions = body['memory_deltas'].get('round_conditions')
    counts = _counters(content)
    updates = {}
    notes = []
    events = {'host': [], 'ds': {}}
    compact = lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if conditions:
        meta['ab_streak'] = meta['ab_streak'] + 1 if conditions['intensity'] in ('A', 'B') else 0
    else:
        meta['ab_streak'] = 0
        meta['scopes'] = {}
        notes.append('旧格式未提供round_conditions；未推断烈度或停滞，语义连续观测中断，旧绝对计数入口兼容。')
    states = _current_micro(content)
    transitions = {}
    cast_set = set(active_cast) if active_cast is not None else None
    for name in ROUND_NPCS:
        old_entries = meta['micro'].get(name, {})
        new_entries = {}
        requested = body['micro_state_changes'].get(name, {})
        old_states = dict(states[name])
        in_scene = (cast_set is None) or (name in cast_set)
        for key in MICRO_STATES:
            active = old_states[key]
            entry = old_entries.get(key)
            if active and entry is None:
                entry = {'observed_round': current, 'origin': 'legacy_observed'}
                notes.append('旧true首次观测保留: ' + name + '.' + key + '，从回合' + str(current) + '向后计时。')
            expires = bool(active and entry and current - entry['observed_round'] >= (2 if key == 'confusion_debt' else 1))
            if requested.get(key) is False or expires:
                active = False
            elif requested.get(key) is True and not active:
                active = True
                entry = {'observed_round': current, 'origin': 'activated'}
            if key == 'confusion_debt' and conditions and in_scene:
                if conditions['intensity'] == 'C':
                    active = False
                elif active and min(meta['ab_streak'], current - entry['observed_round']) >= 2:
                    active = False
            states[name][key] = active
            if active:
                new_entries[key] = entry
        if in_scene and conditions and conditions['intensity'] == 'C' and (old_states['confusion_debt'] or requested.get('confusion_debt') is True):
            states[name]['confusion_debt'] = False
            new_entries.pop('confusion_debt', None)
            states[name]['residual_tension'] = True
            new_entries['residual_tension'] = {'observed_round': current, 'origin': 'activated'}
        meta['micro'][name] = new_entries
        changed = {key: states[name][key] for key in MICRO_STATES if states[name][key] != old_states[key]}
        if changed:
            transitions[name] = changed
    guard_due = False
    breakout_evaluation = {}
    if conditions:
        c = conditions
        focused = c['npc'] is not None
        panel_line = re.search(r'^\[' + re.escape(c['npc'] or '') + r'\]([^\n]*)', content, re.M)
        shame = re.search(r'羞耻\s*(\d+)', panel_line[1]) if panel_line else None
        base = not c['effective_progress']
        rules = {
            '破局_日常冗余': (base and c['intensity'] == 'A', 'global'),
            '破局_模式重复': (base and focused and not c['action_changed'], compact([c['scene'], c['npc'], c['intensity']])),
            '破局_社交淤积': (base and focused and c['intensity'] in ('A', 'B') and shame is not None and int(shame[1]) > 80, compact(c['npc'])),
            '破局_张力淤积': (base and focused and c['intensity'] == 'B' and c['stress_signals'] > 0, compact(c['npc'])),
        }
        for key, (holds, scope) in rules.items():
            old = counts.get(key, 0)
            old_scope = meta['scopes'].get(key)
            if old and old_scope is None and key != '破局_日常冗余':
                meta['legacy_counters'].setdefault(key, {'value': old, 'observed_round': current})
                notes.append('旧计数缺scope，保留观测值并以本回条件重新起计: ' + key)
                old = 0
            if old_scope is not None and old_scope != scope:
                old = 0
            updates[key] = old + 1 if holds else 0
            breakout_evaluation[key] = {'candidate': updates[key], 'threshold': BREAKOUT_LIMITS[key],
                                        'threshold_reached': updates[key] >= BREAKOUT_LIMITS[key]}
            if key in c['breakout_triggered']:
                updates[key] = 0
            meta['scopes'][key] = scope
        # 冷却计数持久化与逐行动递减（修复原 冷却_破局全局 / 冷却_<key> 永不写入问题）
        if counts.get('冷却_破局全局', 0) > 0:
            updates['冷却_破局全局'] = max(0, counts.get('冷却_破局全局', 0) - 1)
        for key in BREAKOUT_LIMITS:
            ck = '冷却_' + key
            if counts.get(ck, 0) > 0:
                updates[ck] = max(0, counts.get(ck, 0) - 1)
        if c['breakout_triggered']:
            updates['冷却_破局全局'] = 2
            for key in c['breakout_triggered']:
                updates['冷却_' + key] = 8
        guard = counts.get('连续守护回合', 0) + 1 if c['intensity'] in ('A', 'B') else 0
        guard_due = guard >= 5
        updates['连续守护回合'] = 0 if guard_due else guard
    if guard_tag in result['host_events'] and conditions and not guard_due:
        raise RoundError('连续守护奖励提前，尚未满5个成功回合')
    if guard_due and guard_tag not in result['host_events']:
        result['host_events'].append(guard_tag)
    if guard_due:
        events['host'].append(guard_tag)
    if not conditions and guard_tag in result['host_events']:
        notes.append('旧格式守护标签沿用模型判断；未提供可核验的烈度连续观测。')
    if counts.get('空耗_连续未纾解', 0):
        meta['legacy_counters'].setdefault('空耗_连续未纾解', {'value': counts['空耗_连续未纾解'], 'observed_round': current})
        notes.append('旧空耗全局计数无角色归属，保留原值；不用于任何NPC扣分。')
    for name in ROUND_NPCS:
        key = '空耗_连续未纾解_' + name
        in_scene = (cast_set is None) or (name in cast_set)
        if not in_scene:
            updates[key] = counts.get(key, 0)
            if exhaust_tag in result['ds_events'].get(name, []):
                raise RoundError(name + '未在场，不得结算空耗惩罚')
            continue
        line = re.search(r'^\[' + re.escape(name) + r'\]([^\n]*)', content, re.M)
        desire = re.search(r'欲望\s*(\d+)', line[1]) if line else None
        if desire is None:
            continue
        original_tags = list(result['ds_events'].get(name, []))
        preview_tags = [tag for tag in original_tags if tag != exhaust_tag]
        projected = None
        if name in result['ds_events']:
            projected = _engine_call(engine.process_desire_stamina_system, {name: preview_tags}, engine.MEMORY_FILE).get(name)
        projected_desire = projected['欲望'] if projected else int(desire[1])
        # The existing engine's clearance produces 35 desire; explicit clearance or self-relief also ends a streak.
        relieved = (
            engine._event_tag('DS_17') in preview_tags
            or engine._event_tag('DS_18') in preview_tags
            or bool(projected and projected_desire <= 70)
        )
        value = counts.get(key, 0) + 1 if projected_desire > 70 and not relieved else 0
        due = value >= 2
        updates[key] = 0 if due else value
        if exhaust_tag in original_tags and not due:
            raise RoundError(name + '的空耗惩罚提前，尚未满两个成功回合')
        if due:
            if exhaust_tag not in original_tags:
                result['ds_events'].setdefault(name, []).append(exhaust_tag)
            events['ds'][name] = [exhaust_tag]
    for key, value in body['counter_updates'].items():
        if key in updates and value != updates[key]:
            raise RoundError('counter_updates与程序推导值不符: ' + key)
        if key == '空耗_连续未纾解' and value != counts.get(key, 0):
            raise RoundError('旧无归属空耗计数只读；使用程序分角色计数')
        updates.setdefault(key, value)
    meta['round'] = current
    result['memory_deltas'].pop('round_conditions', None)
    # Avoid the legacy unbounded role regex; write only the current block after engine settlement.
    result['micro_state_changes'] = {}
    result['counter_updates'] = {}
    counts.update(updates)
    audit = {'round_conditions': conditions, 'micro_transitions': transitions, 'counter_values': updates,
             'derived_events': events, 'breakout_evaluation': breakout_evaluation, 'compatibility_notes': notes}
    result['system_log'] += '\n\n【程序生命周期结算】\n' + compact(audit)
    return result, meta, states, counts




def _fsync_dir(directory):
    try:
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF, errno.EACCES}:
            raise


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.round-tmp-' + uuid.uuid4().hex)
    try:
        with tmp.open('xb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


_LOCK_DEPTH = threading.local()


class RoundStore:
    """One writer per project, using POSIX record locks and a durable rollback/redo journal."""
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).parent).resolve()
        if not (self.root / 'injection_core.py').is_file():
            raise RoundError('目标目录不是项目根目录')
        self.runtime = self._path('.round-runtime')
        with _LOCKS_GUARD:
            self.thread_lock = _LOCKS.setdefault(str(self.root), threading.RLock())

    def _path(self, relative):
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise RoundError('路径越出项目: ' + relative)
        return path

    @contextmanager
    def _locked(self):
        import fcntl
        if not self.thread_lock.acquire(timeout=10):
            raise ConflictError('已有回合正在提交，请稍后重试')
        depths = getattr(_LOCK_DEPTH, 'counts', None)
        if depths is None:
            depths = {}
            _LOCK_DEPTH.counts = depths
        key = str(self.root)
        depth = depths.get(key, 0)
        try:
            if depth > 0:
                depths[key] = depth + 1
                try:
                    yield
                finally:
                    depths[key] = depth
                return
            self.runtime.mkdir(parents=True, exist_ok=True)
            with self._path('.round-runtime/lock').open('a+b') as handle:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise ConflictError('已有其他进程正在提交')
                        time.sleep(0.05)
                depths[key] = 1
                try:
                    self._recover()
                    yield
                finally:
                    depths.pop(key, None)
                    fcntl.lockf(handle, fcntl.LOCK_UN)
        finally:
            self.thread_lock.release()

    def _files(self):
        return {name: self._path(name).read_bytes() if self._path(name).is_file() else None for name in FILES}

    def _ledger(self):
        path = self._path(META)
        if not path.exists():
            recovered_seq = 0
            try:
                ss_path = self._path(save_store.SAVE_STATE_PATH)
                if ss_path.is_file():
                    ss_obj = json.loads(ss_path.read_bytes())
                    rt_seq = (ss_obj.get('runtime') or {}).get('last_sequence')
                    if type(rt_seq) is int and rt_seq > recovered_seq:
                        recovered_seq = rt_seq
            except Exception:
                pass
            try:
                data_path = self._path('data.json')
                if data_path.is_file():
                    data_obj = json.loads(data_path.read_bytes())
                    for cand in (data_obj.get('state_version'), (data_obj.get('interaction') or {}).get('last_sequence')):
                        if type(cand) is int and cand > recovered_seq:
                            recovered_seq = cand
            except Exception:
                pass
            try:
                rp_path = self._path(RECENT_PLAYBACK)
                if rp_path.is_file():
                    rp_obj = json.loads(rp_path.read_bytes())
                    for seg in (rp_obj.get('segments') or []):
                        cand = seg.get('sequence') if isinstance(seg, dict) else None
                        if type(cand) is int and cand > recovered_seq:
                            recovered_seq = cand
            except Exception:
                pass
            inter_dir = self._path('.round-runtime/interaction')
            if inter_dir.is_dir():
                for item in inter_dir.glob('*.json'):
                    if re.fullmatch(r'\d{12}', item.stem):
                        cand = int(item.stem)
                        if cand > recovered_seq:
                            recovered_seq = cand
            return {'version': 1, 'sequence': recovered_seq, 'receipts': {}}
        try:
            value = json.loads(path.read_bytes(), object_pairs_hook=_pairs)
            if value['version'] != 1 or not isinstance(value['receipts'], dict) or type(value['sequence']) is not int:
                raise ValueError('invalid ledger')
            return value
        except (ValueError, KeyError, TypeError) as exc:
            raise RecoveryError('回合提交记录损坏，已停止写入') from exc

    def _publish(self, values):
        # Publish data.json last; consistent readers also hold this store's lock.
        names = [name for name in values if name != 'data.json']
        if 'data.json' in values:
            names.append('data.json')
        for name in names:
            path = self._path(name)
            if values[name] is None:
                if path.exists():
                    path.unlink()
                    _fsync_dir(path.parent)
            else:
                _atomic(path, values[name])

    def _recover(self):
        journal = self._path('.round-runtime/journal.json')
        if journal.exists():
            try:
                record = json.loads(journal.read_bytes(), object_pairs_hook=_pairs)
                if record['version'] != 1 or record['phase'] not in {'prepared', 'committed'}:
                    raise ValueError('journal phase')
                before, after = record['before'], record['after']
                playback_set = {'.round-runtime/interaction/playback.json', RECENT_PLAYBACK}
                if set(before) != set(after) or not ((set(FILES) | {META}) <= set(before) or set(before) == playback_set):
                    raise ValueError('journal file set')
                values = {}
                for name in before:
                    if name not in set(FILES) | {META} and not re.fullmatch(r'(?:日志/Round_\d+_[0-9a-f]{16}\.txt|\.round-runtime/interaction/(?:\d{12}|playback)\.json|\.round-runtime/story/tasks\.json|存档/近期演播\.json)', name):
                        raise ValueError('journal path')
                    for version in (before, after):
                        if version[name] is not None:
                            base64.b64decode(version[name], validate=True)
                    encoded = (after if record['phase'] == 'committed' else before)[name]
                    values[name] = None if encoded is None else base64.b64decode(encoded, validate=True)
                self._publish(values)
                journal.unlink()
                _fsync_dir(journal.parent)
            except Exception as exc:
                raise RecoveryError('未完成事务尚未恢复，记录已保留；请修复存储/权限后运行recover') from exc
        for relative in (*FILES, RECENT_PLAYBACK, META, '.round-runtime/journal.json'):
            target = self._path(relative)
            for leftover in target.parent.glob('.' + target.name + '.round-tmp-*'):
                if leftover.is_file() and not leftover.is_symlink():
                    leftover.unlink()
        log_dir = self._path('日志')
        if log_dir.is_dir():
            for leftover in log_dir.glob('.Round_*.txt.round-tmp-*'):
                if leftover.is_file() and not leftover.is_symlink():
                    leftover.unlink()
        interaction = self._path('.round-runtime/interaction')
        if interaction.is_dir():
            for leftover in interaction.glob('.*.json.round-tmp-*'):
                if leftover.is_file() and not leftover.is_symlink():
                    leftover.unlink()
        for folder in self.runtime.glob('work-*'):
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder)

    def recover(self):
        with self._locked():
            return {'status': 'ready', 'revision': _revision(self._files())}

    def prepare(self):
        with self._locked():
            files = self._files()
            content, layers, previous = _memory_state(_engine(self.root, self.root), files)
            return {
                'schema_version': 1, 'base_revision': _revision(files),
                'current_round': previous + 1,
                'memory_layers': {label: len(entries) for label, entries in layers.items()},
                'summary_sources': {
                    'l1_to_l2_condensed': layers['L1'][:1] if len(layers['L1']) == 3 else [],
                    'l2_to_l3_summary': layers['L2'] if len(layers['L2']) == 10 else [],
                    'l3_to_l4_summary': layers['L3'] if len(layers['L3']) == 10 else [],
                },
                'snapshot': {name: data.decode('utf-8') if data is not None else None for name, data in files.items()},
            }

    def _settle(self, body, files, sequence, request_id):
        stage = Path(tempfile.mkdtemp(prefix='work-', dir=self.runtime))
        try:
            for name, data in files.items():
                if data is not None:
                    _atomic(stage / name, data)
            engine = _engine(self.root, stage)
            settled, lifecycle, micro, counters = _derive_lifecycle(engine, body, files[FILES[0]].decode('utf-8'))
            _engine_call(engine._execute_injection_internal, **settled)
            memory_path = stage / FILES[0]
            memory = _write_micro(memory_path.read_text(encoding='utf-8'), micro)
            memory = _write_counters(memory, counters)
            _atomic(memory_path, _write_lifecycle(memory, lifecycle).encode('utf-8'))
            after = {name: (stage / name).read_bytes() if (stage / name).is_file() else None for name in FILES}
            if after['data.json'] is None:
                raise RoundError('结算没有生成运行时快照')
            data = json.loads(after['data.json'])
            if data.get('round') != body['current_round'] or not data.get('storyNodes'):
                raise RoundError('结算后的回合或正文快照无效')
            prior_data = json.loads(files['data.json'] or b'{}')
            for keep_key in ('interaction', 'story_runtime', 'prologue', 'last_settlement'):
                if keep_key in prior_data and keep_key not in data:
                    data[keep_key] = prior_data[keep_key]
            data['state_version'] = sequence
            data['request_id'] = request_id
            after['data.json'] = _json(data)
            # Sync P2 JSON single-source-of-truth with settled stage files & re-render views.
            st_obj, ly_obj, _ = save_store.load_bundle(stage, after)
            st_obj['micro_states'] = copy.deepcopy(micro)
            st_obj['counters'] = copy.deepcopy(counters)
            st_obj['lifecycle'] = copy.deepcopy(lifecycle)
            st_obj['runtime']['last_sequence'] = max(int(st_obj['runtime'].get('last_sequence') or 0), sequence)
            ly_obj['prologue_active'] = False
            rendered = save_store.render_bundle_bytes(st_obj, ly_obj, data_dict=data)
            after.update(rendered)
            _, _, end_round = _memory_state(engine, after)
            if end_round != body['current_round']:
                raise RoundError('结算后的记忆回合与正文不一致')
            log_files = list((stage / '日志').glob('*.txt'))
            if len(log_files) != 1:
                raise RoundError('结算后的推演日志缺失或重复')
            log_name = '日志/Round_' + str(body['current_round']) + '_' + _digest(request_id.encode('utf-8'))[:16] + '.txt'
            after[log_name] = log_files[0].read_bytes()
            return after
        finally:
            shutil.rmtree(stage)

    def _commit_files(self, after):
        before = {name: self._path(name).read_bytes() if self._path(name).is_file() else None for name in after}
        encode = lambda values: {name: None if raw is None else base64.b64encode(raw).decode('ascii') for name, raw in values.items()}
        record = {'version': 1, 'phase': 'prepared', 'before': encode(before), 'after': encode(after)}
        journal = self._path('.round-runtime/journal.json')
        committed = False
        try:
            _atomic(journal, _json(record))
            self._publish(after)
            record['phase'] = 'committed'
            _atomic(journal, _json(record))
            committed = True
            journal.unlink()
            _fsync_dir(journal.parent)
        except Exception:
            self._recover()
            if not committed:
                raise

    def _write_playback(self, value):
        # Caller holds this store lock. Reading never advances world state or sequence.
        # Only journal/publish the two playback files instead of rewriting all 6 unchanged world files.
        rp_path = self._path(RECENT_PLAYBACK)
        recent = save_store.default_recent()
        if rp_path.is_file():
            try:
                parsed = json.loads(rp_path.read_bytes())
                if isinstance(parsed, dict):
                    recent = parsed
            except ValueError:
                pass
        after = {
            '.round-runtime/interaction/playback.json': _json(value),
            RECENT_PLAYBACK: _json(save_store.update_recent_playback(recent, value)),
        }
        self._commit_files(after)

    def _check_source_baseline(self, baseline):
        if baseline is None:
            return
        for relative, expected in baseline.items():
            source = self._path(relative)
            if not source.is_file() or _digest(source.read_bytes()) != expected:
                raise ConflictError('提交来源已改变，请显式重试: ' + relative)

    def submit(self, request, *, dry_run=False, allow_panel_override=False, _legacy=False, _source_baseline=None):
        request = copy.deepcopy(request)
        # Serialize first so caller-owned containers cannot be changed by the engine.
        if len(_json(request)) > 4 * 1024 * 1024:
            raise RoundError('回合JSON超过4MiB上限')
        if not isinstance(request, dict):
            raise RoundError('回合必须是对象')
        excluded = {'request_id', 'base_revision'} if _legacy else {'request_id'}
        payload_hash = _digest(_json({k: v for k, v in request.items() if k not in excluded}))
        with self._locked():
            files = self._files()
            ledger = self._ledger()
            request_id = request.get('request_id')
            if not isinstance(request_id, str):
                raise RoundError('request_id必须是文本')
            previous = ledger['receipts'].get(request_id)
            if previous is not None:
                if previous['payload_hash'] != payload_hash:
                    raise ConflictError('request_id已用于不同内容，请勿复用')
                return dict(previous['receipt'], replayed=True, is_current=previous['receipt']['revision'] == _revision(files))
            if _legacy and request.get('base_revision') is None:
                request['base_revision'] = _revision(files)
            definition_baseline = {rel: _digest(self._path(rel).read_bytes()) for rel in
                                   ('injection_core.py', 'txt文件/事件注册表.json')}
            self._check_source_baseline(_source_baseline)
            continuous = request.get('entry_mode') == 'live_interaction'
            ir = None
            if continuous:
                import interaction_runtime as ir
                if request.get('schema_version') == 3:
                    import story_progression as sp
                    tasks = load_request(self._path(sp.TASKS).read_text())
                    task = tasks['jobs'].get(request_id)
                    if (not task or task['status'] != 'validating' or task.get('working_revision') != request.get('base_revision')
                            or task.get('reservation') != request.get('audit', {}).get('reservation')
                            or task['reservation']['status'] != 'held'):
                        raise ConflictError('预扣或任务已终止，拒绝迟到结果')
            body = ir.validate(self.root, request, files) if continuous else _validate(self.root, request, files, allow_panel_override)
            sequence = ledger['sequence'] + 1
            after = ir.settle(self, body, files, sequence, request_id) if continuous else self._settle(body, files, sequence, request_id)
            self._check_source_baseline(definition_baseline)
            self._check_source_baseline(_source_baseline)
            revision = _revision(after)
            receipt = {'request_id': request_id, 'round': json.loads(after['data.json']).get('round', 0), 'revision': revision,
                       'state_version': sequence, 'replayed': False,
                       'status': 'validated' if dry_run else 'committed',
                       'optimistic_lock': not _legacy}
            if dry_run:
                return receipt
            ledger['sequence'] = sequence
            ledger['receipts'][request_id] = {'payload_hash': payload_hash, 'receipt': receipt}
            after[META] = _json(ledger)
            if continuous and request['schema_version'] == 3:
                task.update(status='committed', error='', receipt=receipt, lease=None)
                task['reservation']['status'] = 'settled'
                task['settlement'] = json.loads(after['data.json'])['last_settlement']
                after[sp.TASKS] = _json(tasks)
            before = {name: self._path(name).read_bytes() if self._path(name).is_file() else None for name in after}
            # Detect non-cooperating edits that happened while the round was staged.
            if any(before[name] != files[name] for name in FILES):
                raise ConflictError('结算期间存档被其他工具更改，未提交本回合')
            self._commit_files(after)
            return receipt


def submit_legacy(root, body, *, request_id=None, base_revision=None, allow_panel_override=False):
    body = copy.deepcopy(body)
    request = dict(body, schema_version=1, request_id=request_id or 'legacy-' + _digest(_json(body)),
                   base_revision=base_revision)
    return RoundStore(root).submit(request, allow_panel_override=allow_panel_override,
                                   _legacy=base_revision is None)


def main(argv=None):
    parser = argparse.ArgumentParser(description='准备、校验、提交或恢复本地回合JSON；不调用模型或执行输入代码。')
    parser.add_argument('--root', default=str(Path(__file__).parent), help='项目根目录')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare', help='返回状态版本、下一回合、摘要来源和一致快照')
    commands.add_parser('recover', help='恢复未完成事务，然后返回状态版本')
    commands.add_parser('events', help='只读输出注册表生成视图，供维护时同步指南与知识库')
    for name in ('check', 'apply'):
        command = commands.add_parser(name)
        command.add_argument('request_file', help='UTF-8 JSON文件，-表示标准输入')
        command.add_argument('--allow-panel-override', action='store_true', help='仅人工明确要求强制改数值时使用')
    args = parser.parse_args(argv)
    try:
        store = RoundStore(args.root)
        if args.command == 'events':
            engine = _engine(store.root, store.root)
            result = {'path': 'txt文件/事件注册表.json',
                      'sha256': _digest(store._path('txt文件/事件注册表.json').read_bytes()),
                      'views': {field: engine._render_event_table(field) for field in engine._load_event_registry()['groups']}}
        elif args.command == 'prepare':
            result = store.prepare()
        elif args.command == 'recover':
            result = store.recover()
        else:
            import sys
            text = sys.stdin.read() if args.request_file == '-' else Path(args.request_file).read_text(encoding='utf-8-sig')
            result = store.submit(load_request(text), dry_run=args.command == 'check',
                                  allow_panel_override=args.allow_panel_override)
        print(_json({'ok': True, 'result': result}).decode('utf-8'), end='')
        return 0
    except (ValueError, OSError) as exc:
        print(_json({'ok': False, 'error': str(exc), 'code': getattr(exc, 'code', 'execution_error')}).decode('utf-8'), end='')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

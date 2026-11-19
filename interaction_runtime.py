"""Formal continuous interactions. Persistence is owned exclusively by RoundStore."""
import copy
import hashlib
import json
from pathlib import Path
import re
import time
import round_runtime as rr
import story_reading as sr
import story_progression as sp

MODE = 'live_interaction'
CONFIG = 'txt文件/互动运行配置.json'
ARCHIVE = '.round-runtime/interaction'
RULE = 'txt文件/场景交流规范.md'
PEOPLE = ('沈知韫', '苏婉青', '徐念薇')
PLAYBACK = ARCHIVE + '/playback.json'
OPTION_NAMES = {'A': '日常互动', 'B': '社交接触', 'C': '主动行为'}


def decision(value):
    rr._keys(value, {'prompt', 'options'}, 'decision', {'prompt', 'options'})
    rr._text(value['prompt'], 'decision.prompt', 300)
    options = value['options']
    if not isinstance(options, list) or len(options) != 3:
        raise rr.RoundError('decision.options须恰含A/B/C三个选项')
    for item, letter in zip(options, OPTION_NAMES):
        rr._keys(item, {'id', 'text'}, 'decision.option', {'id', 'text'})
        if item['id'] != letter:
            raise rr.RoundError('选项必须按A/B/C排列且不重复')
        rr._text(item['text'], 'decision.option.text', 500)
    if len({item['text'].strip() for item in options}) != 3:
        raise rr.RoundError('三个选项须为不同的可行动作')
    return copy.deepcopy(value)


def segment(root, files):
    data = json.loads(files.get('data.json') or b'{}')
    state = data.get('interaction', {})
    if not state.get('segment_id'):
        return None
    sequence = state.get('last_sequence')
    if type(sequence) is not int or sequence < 1:
        raise rr.RecoveryError('剧情段索引无效')
    row = rr.load_request((Path(root) / ARCHIVE / f'{sequence:012d}.json').read_text())
    if row.get('id') != state['segment_id'] or row.get('version') != 2:
        raise rr.RecoveryError('剧情段与当前存档不一致')
    return row


def playback(root, row):
    if row is None:
        return {'segment_id': '', 'revealed': 0, 'total': 0, 'completed': True, 'bootstrap': True}
    path = Path(root) / PLAYBACK
    value = rr.load_request(path.read_text()) if path.is_file() else {}
    total = len(row['messages'])
    if value.get('segment_id') != row['id']:
        raise rr.RecoveryError('剧情演播进度与当前段落不一致')
    if (value.get('version') != 1 or type(value.get('revealed')) is not int
            or not 0 <= value['revealed'] <= total or type(value.get('completed')) is not bool
            or (value['completed'] and value['revealed'] != total)):
        raise rr.RecoveryError('剧情演播进度无效')
    return {**value, 'total': total, 'bootstrap': False}


def selection(root, files, proposed, text, command=None):
    row = segment(root, files)
    state = playback(root, row)
    if proposed is None:
        if row is not None:
            raise rr.ConflictError('本段演播完成后须按当前抉择提交，旧输入不可绕过')
        return None  # Compatibility for pre-playback callers; the page uses BEGIN.
    rr._keys(proposed, {'segment_id', 'option_id'}, 'selection', {'segment_id', 'option_id'})
    if sp.enabled(root) and row is not None:
        runtime = sp.state(root, files)
        resting = runtime['phase'] == 'resting' or sp.stamina(root, files) < 5
        if resting:
            if (not state['completed'] or proposed != {'segment_id':row['id'], 'option_id':'REST'} or text != '继续休息' or command):
                raise rr.ConflictError('本段读完后须进入免费强制休息')
            return copy.deepcopy(proposed)
    if row is None:
        if proposed != {'segment_id': '', 'option_id': 'BEGIN'} or text != '继续当前剧情' or command:
            raise rr.ConflictError('当前没有可消费的抉择，请从继续剧情开始')
    else:
        if not state['completed']:
            raise rr.ConflictError('本段剧情尚未演播完成')
        if proposed['segment_id'] != row['id'] or proposed['option_id'] not in (*OPTION_NAMES, 'CUSTOM'):
            raise rr.ConflictError('抉择已过期，请恢复当前段落')
        if proposed['option_id'] != 'CUSTOM':
            item = next(item for item in row['decision']['options'] if item['id'] == proposed['option_id'])
            if item['text'] != text or command is not None:
                raise rr.ConflictError('选项内容与本段不一致，不允许替换原行动')
    return copy.deepcopy(proposed)


def update_playback(store, row, revealed, completed):
    state = playback(store.root, row)
    rr._integer(revealed, 'revealed')
    if type(completed) is not bool or row is None:
        raise rr.RoundError('演播完成标记或段落无效')
    if revealed > state['revealed'] + 1 or revealed > state['total']:
        raise rr.ConflictError('演播须逐节点推进，请先恢复当前进度')
    if completed and (revealed != state['total'] or state['revealed'] != state['total']):
        raise rr.ConflictError('最后节点尚未演播，不可提前完成')
    new = {'version': 1, 'segment_id': row['id'], 'revealed': max(revealed, state['revealed']),
           'completed': state['completed'] or completed}
    if any(new[key] != state.get(key) for key in new):
        store._write_playback(new)
    return playback(store.root, row)


def policy(root):
    value = rr.load_request((Path(root) / CONFIG).read_text(encoding='utf-8'))
    resource = value.get('resource', {})
    if resource.get('scheme') == 'fixed_tiers':
        return sp.config(root)
    if value.get('version') != 1 or resource.get('status') not in ('pending', 'active'):
        raise rr.RoundError('互动运行配置版本或资源政策无效')
    if not isinstance(value.get('locations'), list) or not all(isinstance(n, str) and n for n in value['locations']):
        raise rr.RoundError('登记地点配置无效')
    if resource['status'] == 'pending':
        if resource.get('base_cost') is not None or resource.get('action_costs') is not None:
            raise rr.RoundError('待定资源政策不得携带隐式默认成本')
    else:
        rr._keys(resource, {'status', 'version', 'attribute', 'base_cost', 'action_costs', 'recovery', 'limits'},
                 'resource', {'status', 'version', 'attribute', 'base_cost', 'action_costs'})
        rr._integer(resource['version'], 'resource.version', 1)
        if resource.get('recovery') is not None or resource.get('limits') is not None:
            raise rr.RoundError('恢复与上限规则尚未实现，不能静默启用')
        if resource['attribute'] not in ('体力', '积分'):
            raise rr.RoundError('资源属性仅支持宿主已登记的体力或积分')
        rr._integer(resource['base_cost'], 'base_cost', 1)
        rr._keys(resource['action_costs'], {'move_player', 'transfer_item'}, 'action_costs', {'move_player', 'transfer_item'})
        for name, cost in resource['action_costs'].items():
            rr._integer(cost, 'action_costs.' + name)
    return value


def quote(root, files, op):
    resource = policy(root)['resource']
    if resource['status'] == 'pending':
        return {'status': 'pending', 'total': None, 'policy_version': None}
    total = resource['base_cost'] + (resource['action_costs'][op['code']] if op else 0)
    engine = rr._engine(root, root)
    current = engine._read_attr_value(files[rr.FILES[0]].decode('utf-8'), '系统宿主', resource['attribute'])
    if current is None:
        raise rr.RoundError('正式存档缺少指定资源')
    if current < total:
        raise rr.RoundError('资源不足；本次交流和操作均未接受')
    return {'status': 'active', 'attribute': resource['attribute'], 'total': total,
            'before': current, 'after': current - total, 'policy_version': resource['version']}


def records(store):
    folder = store._path(ARCHIVE)
    return sorted(p for p in folder.glob('*.json') if re.fullmatch(r'\d{12}\.json', p.name))


def view(store, files=None):
    files = files or store._files()
    engine = rr._engine(store.root, store.root)
    memory = (files[rr.FILES[0]] or b'').decode('utf-8')
    presence = engine.parse_presence_from_memory(memory)
    location = presence['徐志北']['location']
    cast = [n for n in PEOPLE if presence[n]['location'] == location]
    catalog = (files[rr.FILES[1]] or b'').decode('utf-8')
    items = []
    for m in engine._ITEM_BLOCK_RE.finditer(engine._active_item_zone(catalog)):
        fields = engine._parse_item_block(m.group(0))
        if not re.fullmatch(r'ITEM-\d+', fields['道具ID']):
            continue
        items.append({'id': fields['道具ID'], 'name': m.group('name').strip(),
                      'quantity': engine._int_of(fields['数量'], 1), 'fields': fields})
    panel = memory.split('▶ 上回合历史快照', 1)[0]
    panels = [line for line in panel.splitlines() if line.startswith('[')]
    data = json.loads(files.get('data.json') or b'{}')
    progression = {'runtime': sp.state(store.root, files), 'stamina':sp.stamina(store.root, files),
                   'costs':sp.COSTS, 'item_budget':20-sp.state(store.root, files)['item_recovered']} if sp.enabled(store.root) else None
    return {'progression': progression, 'location': location, 'cast': cast, 'presence': presence, 'panels': panels,
            'items': items, 'tasks': engine._parse_task_block(memory),
            'interaction': data.get('interaction', {'count': 0, 'actions': 0}),
            'policy': policy(store.root)}


def operation(root, files, proposed, text='', explicit=False):
    """Only player travel and transfer of a complete held stack are currently supported."""
    if proposed is None:
        return None
    rr._keys(proposed, {'code', 'destination', 'item_id', 'recipient'}, 'operation', {'code'})
    if proposed['code'] == 'use_recovery_item' and sp.enabled(root):
        rr._keys(proposed, {'code','item_id'}, 'use_recovery_item', {'code','item_id'})
        match = sp.PURE_ITEM.fullmatch(text)
        if not match or match[1] != proposed['item_id']:
            raise rr.RoundError('道具操作必须是明确ID的纯使用恢复指令')
        sp.item_quote(root, files, proposed['item_id'])
        return copy.deepcopy(proposed)
    engine = rr._engine(root, root)
    presence = engine.parse_presence_from_memory(files[rr.FILES[0]].decode('utf-8'))
    player_place = presence['徐志北']['location']
    code = proposed['code']
    if code == 'move_player':
        rr._keys(proposed, {'code', 'destination'}, 'move_player', {'code', 'destination'})
        target = proposed['destination']
        if target not in policy(root)['locations'] or target == player_place:
            raise rr.RoundError('目的地未开放或已经位于该地点')
        if not explicit and (target not in text or not re.search(r'去|前往|回到|返回|走到|出发', text)):
            raise rr.RoundError('移动缺少玩家明确目的地与行动依据')
        return copy.deepcopy(proposed)
    if code == 'transfer_item':
        rr._keys(proposed, {'code', 'item_id', 'recipient'}, 'transfer_item', {'code', 'item_id', 'recipient'})
        who = proposed['recipient']
        if who not in PEOPLE or presence[who]['location'] != player_place:
            raise rr.RoundError('接收人必须实际在场')
        catalog = (files[rr.FILES[1]] or b'').decode('utf-8')
        if not isinstance(proposed['item_id'], str) or not re.fullmatch(r'ITEM-\d+', proposed['item_id']):
            raise rr.RoundError('道具编号无效')
        found = engine._find_item_block(catalog, item_id=proposed['item_id'])
        if not found:
            raise rr.RoundError('没有该活跃道具')
        fields = engine._parse_item_block(found['block'])
        if fields['当前状态'] != '仓库中' or fields['使用对象'] not in ('', '无', '未使用', '徐志北'):
            raise rr.RoundError('该道具不属于玩家可交付库存')
        if not explicit and (who not in text or not re.search(r'交给|送给|递给|赠给', text)
                             or re.search(r'【道具名称】：([^\n]+)', found['block']).group(1).strip() not in text
                             or not re.search(r'整组|全部|所有', text)):
            raise rr.RoundError('交付缺少玩家明确接收人依据')
        return copy.deepcopy(proposed)
    raise rr.RoundError('未登记的正式行动；请先明确可执行范围')


def validate(root, request, files):
    required = {'schema_version', 'entry_mode', 'request_id', 'base_revision', 'input', 'messages', 'operation', 'handoff', 'audit'}
    modern = request.get('schema_version') in (2, 3)
    charged = request.get('schema_version') == 3
    if sp.enabled(root) and not charged:
        raise rr.RoundError('现役收费入口须使用schema3及正式预扣')
    if charged:
        required.add('resolution')
    if modern:
        required |= {'decision', 'selection'}
    rr._keys(request, required, 'continuous_request', required)
    if type(request['schema_version']) is not int or request['schema_version'] not in (1, 2, 3) or request['entry_mode'] != MODE:
        raise rr.RoundError('正式互动协议无效')
    if not isinstance(request['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', request['request_id']):
        raise rr.RoundError('请求编号无效')
    if request['base_revision'] != rr._revision(files):
        raise rr.ConflictError('正式存档已改变，请恢复最新状态')
    rr._text(request['input'], 'input', 2000)
    checked_files = dict(files)
    if charged:
        import base64
        reservation = request.get('audit', {}).get('reservation', {})
        try: checked_files[rr.FILES[0]] = base64.b64decode(reservation['before_memory'], validate=True)
        except (ValueError, KeyError, TypeError) as exc: raise rr.RoundError('预扣原文缺失') from exc
    selection(root, checked_files, request.get('selection'), request['input'])
    if modern:
        decision(request['decision'])
    audit = request['audit']
    if not isinstance(audit, dict) or audit.get('required_reads_verified') is not True:
        raise rr.RoundError('缺少正式接受依据')
    proposed = operation(root, checked_files, request['operation'], request['input'], audit.get('origin') == 'player_action')
    presence = rr._engine(root, root).parse_presence_from_memory(files[rr.FILES[0]].decode('utf-8'))
    location = presence['徐志北']['location']
    allowed = {n for n in PEOPLE if presence[n]['location'] == location}
    if proposed and proposed['code'] == 'move_player':
        allowed = {n for n in PEOPLE if presence[n]['location'] == proposed['destination']}
    messages = request['messages']
    if not isinstance(messages, list) or not 1 <= len(messages) <= (1000 if modern else 12):
        raise rr.RoundError('剧情须为非空节点数组，传输最多1000节点；不作为正文篇幅预算')
    for m in messages:
        rr._keys(m, {'kind', 'speaker', 'text'}, 'message', {'kind', 'speaker', 'text'})
        rr._text(m['text'], 'message.text', 800)
        if m['kind'] not in ('dialogue', 'action', 'narration'):
            raise rr.RoundError('消息类型无效')
        if m['kind'] == 'narration':
            if m['speaker'] != '':
                raise rr.RoundError('旁白不带说话人')
        elif not isinstance(m['speaker'], str) or (m['speaker'] not in allowed and not (modern and m['kind'] == 'action' and m['speaker'] == '徐志北')):
            raise rr.RoundError('角色不在场或模型代写玩家台词')
    if not isinstance(request['handoff'], str) or len(request['handoff']) > 300:
        raise rr.RoundError('待处理说明无效')
    if proposed and request['handoff']:
        raise rr.RoundError('待处理行动不得同时宣称执行')
    if charged:
        sp.resolution(root, files, request)
    else:
        quote(root, files, proposed)
    return copy.deepcopy(request)


def settle(store, body, files, sequence, request_id):
    """No legacy round timers, random rolls, auto tasks, or L1 rotation per message."""
    import shutil
    import tempfile
    stage = Path(tempfile.mkdtemp(prefix='work-', dir=store.runtime))
    try:
        for name, raw in files.items():
            if raw is not None:
                rr._atomic(stage / name, raw)
        engine = rr._engine(store.root, stage)
        before_presence = engine.parse_presence_from_memory(files[rr.FILES[0]].decode('utf-8'))
        display_files = dict(files)
        if body['schema_version'] == 3:
            import base64
            display_files[rr.FILES[0]] = base64.b64decode(body['audit']['reservation']['before_memory'],validate=True)
        before_world = view(store, display_files)
        op = body['operation']
        charged = body['schema_version'] == 3
        settlement = None; runtime = None
        if charged:
            parsed = sp.resolution(store.root, files, body)
            cost = parsed['cost']
            runtime, settlement = sp.apply_staged(store, engine, stage, body, files, parsed)
        else: cost = quote(store.root, files, op)
        if not charged and cost['status'] == 'active':
            memory_path = stage / rr.FILES[0]
            memory = memory_path.read_text(encoding='utf-8')
            memory = engine._simulate_panel(memory, {'系统宿主': {cost['attribute']: cost['after']}})
            rr._atomic(memory_path, memory.encode('utf-8'))
        if op and not charged:
            rr._engine_call(engine.apply_interaction_operation, op)
        after = {name: (stage / name).read_bytes() if (stage / name).is_file() else None for name in rr.FILES}
        presence = engine.parse_presence_from_memory(after[rr.FILES[0]].decode('utf-8'))
        data = json.loads(after['data.json'] or b'{}')
        count = data.get('interaction', {}).get('count', 0) + 1
        actions = data.get('interaction', {}).get('actions', 0) + bool(op)
        data.update(presence=presence, state_version=sequence, request_id=request_id,
                    interaction={'count': count, 'actions': int(actions), 'last_sequence': sequence},
                    sceneTitle=presence['徐志北']['location'], options_text='')
        modern = body['schema_version'] in (2, 3)
        if charged:
            data.update(story_runtime=runtime, last_settlement=settlement, round=runtime['memory_round'])
        if modern:
            data['interaction']['segment_id'] = request_id
        data['storyNodes'] = [{'type': 'dialogue' if m['kind'] == 'dialogue' else 'narration',
                               **({'speaker': m['speaker']} if m['kind'] == 'dialogue' else {}), 'text': m['text']}
                              for m in body['messages']]
        after['data.json'] = rr._json(data)
        listeners = ['徐志北', *[n for n in PEOPLE if before_presence[n]['location'] == before_presence['徐志北']['location']]]
        reply_listeners = ['徐志北', *[n for n in PEOPLE if presence[n]['location'] == presence['徐志北']['location']]]
        if charged and cost['kind']=='item':
            listeners = reply_listeners = ['徐志北']
        accepted = {'version': 1, 'id': request_id, 'sequence': sequence, 'count': count,
                    'input': body['input'], 'input_kind': 'action' if op else 'dialogue',
                    'messages': body['messages'], 'handoff': body['handoff'], 'operation': op,
                    'known_by': sorted(set(listeners) & set(reply_listeners)),
                    'input_known_by': listeners, 'messages_known_by': reply_listeners,
                    'location': before_presence['徐志北']['location'],
                    'after_location': presence['徐志北']['location'],
                    'created_at': time.time(), 'cost': cost, 'audit': body['audit']}
        if modern:
            accepted.update(version=2, decision=body['decision'], selection=body['selection'], before_world=before_world)
            if charged:
                accepted.update(settlement=settlement, resolution=body['resolution'])
            after[PLAYBACK] = rr._json({'version': 1, 'segment_id': request_id, 'revealed': 0, 'completed': False})
        after[ARCHIVE + '/' + f'{sequence:012d}.json'] = rr._json(accepted)
        return after
    finally:
        shutil.rmtree(stage)


def _source_ref(memory, entry, offset, layer):
    begin = memory.index(entry,offset)
    return {'layer':layer, 'range':entry.split('】',1)[0]+'】', 'path':rr.FILES[0],
            'start_line':memory.count('\n',0,begin)+1,
            'end_line':memory.count('\n',0,begin+len(entry))+1, 'characters':len(entry)}


def _relevance(text, query):
    chunks = re.findall(r'[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}',query)
    terms = {term for chunk in chunks for term in ([chunk] if chunk.isascii() else [chunk[i:i+2] for i in range(len(chunk)-1)])}
    terms -= {'继续','今天','怎么','一下','这里','当前','剧情','自己','安排'}
    return sum(term in text for term in terms)


def memory_context(root, memory, query, runtime):
    """Select complete source entries; omitted entries remain addressable by exact ranges."""
    engine=rr._engine(Path(root),Path(root));layers=engine._parse_memory_layer_items(memory)
    limits=sp.memory_policy(root);budget=limits['context_chars']
    entries=[];cursor=memory.index('▲ 第一层：')
    for layer,items in layers.items():
        for item in items:
            ref=_source_ref(memory,item,cursor,layer)
            cursor=memory.index(item,cursor)+len(item)
            entries.append((item,ref))
    header=memory[:memory.index('▲ 第一层：')].strip()
    chosen=[];used=0
    # Current machine state is included once; a pathological legacy header is read explicitly.
    head=header if len(header)<=budget//2 else ''
    used=len(head)
    ranked=sorted(enumerate(entries),key=lambda pair:(pair[1][1]['layer']=='L1',_relevance(pair[1][0],query),pair[0]),reverse=True)
    for index,(item,ref) in ranked:
        if used+len(item)+1<=budget:
            chosen.append(index);used+=len(item)+1
    selected=set(chosen)
    projected='\n'.join(([head] if head else [])+[entries[i][0] for i in sorted(selected)])
    omitted=[ref for i,(_,ref) in enumerate(entries) if i not in selected]
    index_refs=[entries[i][1] for i,_ in ranked if i not in selected][:limits['index_entries']]
    number=runtime['last_closed'] if runtime['phase']=='resting' and runtime['last_closed'] else runtime['memory_round']
    current=next(((item,ref) for item,ref in entries if ref['layer']=='L1' and item.startswith('【'+str(number)+'】')),None)
    required=[];allowed=list(index_refs)
    def demand(ref):
        if ref not in allowed:allowed.append(ref)
        if ref not in required:required.append(ref)
    if not head and header:
        demand({'path':rr.FILES[0],'start_line':1,'end_line':memory[:memory.index('▲ 第一层：')].count('\n'),'characters':len(header),'layer':'state'})
    current_ref=None
    if current:
        item,current_ref=current
        if current_ref not in [entries[i][1] for i in selected]:demand(current_ref)
    transfer_sources={}
    if current is None and len(layers['L1'])==3:
        for key,layer,source in [('l1_to_l2_condensed','L1',layers['L1'][:1]),
                                  ('l2_to_l3_summary','L2',layers['L2'] if len(layers['L2'])==10 else []),
                                  ('l3_to_l4_summary','L3',layers['L3'] if len(layers['L2'])==10 and len(layers['L3'])==10 else [])]:
            if source:
                refs=[ref for item,ref in entries if ref['layer']==layer and item in source]
                transfer_sources[key]=refs
                for ref in refs:
                    if ref not in [entries[i][1] for i in selected]:demand(ref)
    return {'text':projected,'selected':[entries[i][1] for i in sorted(selected)],
            'all_entries':[{'source':ref,'preview':item[:80]} for item,ref in entries],
            'all_refs':[ref for _,ref in entries],
            'omitted_count':len(omitted),'index':index_refs,'allowed':allowed,'required':required,
            'current':current_ref,'transfers':transfer_sources,'limits':limits}


def bounded_history(candidates, limits):
    chosen=[];used=2
    for path,safe in reversed(candidates):
        size=len(json.dumps(safe,ensure_ascii=False,separators=(',',':')))+1
        if len(chosen)>=limits['history_turns'] or used+size>limits['history_chars']:
            break
        chosen.append((path,safe));used+=size
    return list(reversed(chosen))


def packet(story, prepared, key, text, command=None, previous_error='', selected=None, reservation=None):
    """Deterministic source extracts, scoped knowledge and original accepted messages."""
    from scene_chat import SceneService, encode_packet
    helper = SceneService(story.root, story)
    files = {n: v.encode('utf-8') if v is not None else None for n, v in prepared['snapshot'].items()}
    state = view(story.store, files)
    if command is None:
        for destination in state['policy']['locations']:
            if re.fullmatch(r'\s*(?:前往|去|回到|返回)\s*' + re.escape(destination) + r'[。！!]*\s*', text):
                command = {'code': 'move_player', 'destination': destination}
                break
    resolved = operation(story.root, files, command, text, explicit=True) if command else None
    charged = sp.enabled(story.root)
    preview_cost = reservation['quote'] if charged and reservation else quote(story.root, files, resolved)
    effective = copy.deepcopy(state)
    if resolved and resolved['code'] == 'move_player':
        effective['location'] = resolved['destination']
        effective['cast'] = [n for n in PEOPLE if state['presence'][n]['location'] == resolved['destination']]
    limits=sp.memory_policy(story.root)
    candidates = []
    archive = records(story.store)
    for path in archive[-limits['history_turns']:]:
        turn = rr.load_request(path.read_text(encoding='utf-8'))
        input_visible = all(n in turn.get('input_known_by', turn.get('known_by', [])) for n in effective['cast'])
        reply_visible = all(n in turn.get('messages_known_by', turn.get('known_by', [])) for n in effective['cast'])
        if input_visible or reply_visible:
            safe = {k: turn[k] for k in ('id', 'input', 'input_kind', 'messages', 'handoff', 'operation', 'location', 'known_by')}
            safe.update(input_known_by=turn.get('input_known_by',turn.get('known_by',[])),
                        messages_known_by=turn.get('messages_known_by',turn.get('known_by',[])))
            if not input_visible:
                safe['input'] = ''
            if not reply_visible:
                safe.update(messages=[], handoff='', operation=None)
            candidates.append((path,safe))
    recent=bounded_history(candidates,limits)
    history=[safe for _,safe in recent]
    included={path for path,_ in recent}
    omitted_archive=[str(p.relative_to(story.root)) for p in archive if p not in included]
    required_history=[str(candidates[-1][0].relative_to(story.root))] if candidates and candidates[-1][0] not in included else []
    refs = helper.references(text, history)
    if not any(r['name'] == '徐志北' for r in refs):
        refs.append({'name': '徐志北', 'matched_aliases': [], 'basis': 'host_sovereignty'})
    sources, characters, relationships = helper.sources(effective['cast'], refs)
    from relationship_query import RelationshipRegistry
    RelationshipRegistry(story.root).verify_view()
    names = [RULE, CONFIG, 'txt文件/提示词.md', 'txt文件/一键注入指南.txt', 'txt文件/全局执行法典.md',
             'txt文件/故事检索索引.md', 'txt文件/知识库/世界观类.json', 'txt文件/知识库/叙事判断.json',
             'txt文件/知识库/系统标签类.json', 'interaction_runtime.py', 'round_runtime.py', 'injection_core.py',
             'relationship_query.py', *(['story_progression.py','txt文件/事件注册表.json'] if sp.enabled(story.root) else []), *rr.FILES]
    sources.update({n: rr._digest(story.store._path(n).read_bytes()) for n in names})
    for p,_ in recent:
        sources[str(p.relative_to(story.root))] = rr._digest(p.read_bytes())
    relevant = []
    for filename in ('世界观类', '叙事判断', '系统标签类'):
        for entry in json.loads((story.root / ('txt文件/知识库/' + filename + '.json')).read_text())['data']['entries']:
            content = entry['content']
            if filename != '系统标签类' or any(k in content for k in ('※索引key※ sys.runtime_data', '※索引key※ sys.task', '※索引key※ sys.breakout')):
                relevant.append({'source': 'txt文件/知识库/' + filename + '.json', 'body': content})
    memory = prepared['snapshot'][rr.FILES[0]]
    runtime=sp.state(story.root,files) if charged else {'memory_round':1,'last_closed':0,'phase':'ready'}
    projection=memory_context(story.root,memory,text,runtime)
    cache=sr.CACHE+'/'+hashlib.sha256(key.encode()).hexdigest()[:32]
    archive_index=cache+'/history-index.json'
    rr._atomic(story.store._path(archive_index),rr._json({'paths':omitted_archive}))
    sources[archive_index]=rr._digest(story.store._path(archive_index).read_bytes())
    memory_index=cache+'/memory-index.json'
    rr._atomic(story.store._path(memory_index),rr._json({'entries':projection['all_entries']}))
    sources[memory_index]=rr._digest(story.store._path(memory_index).read_bytes())
    # Legacy memories lack machine-readable knowledge scopes; preserve as player-only continuity.
    data = {'entry_mode': MODE, 'request_id': key, 'source_manifest': sources,
            'rules': (story.root / RULE).read_text(),
            'sovereignty': (story.root / 'txt文件/全局执行法典.md').read_text(),
            'characters': characters, 'relationships': relationships, 'knowledge_rules': relevant,
            'scenario': {'location': effective['location'], 'cast': effective['cast'], 'presence': state['presence']},
            'operation_policy': {'locations': state['policy']['locations'],
                'templates': [{'code': 'move_player', 'destination': '登记地点'},
                              {'code': 'transfer_item', 'item_id': 'ITEM-编号', 'recipient': '在场人物'}]},
            'player_private_state': {'memory': projection['text'], 'items': state['items'], 'tasks': state['tasks'],
                'memory_context':{'selected':projection['selected'],'omitted_count':projection['omitted_count'],
                    'index':projection['index'],'full_index':memory_index,'required_reads':projection['required'],'limits':limits,
                    'rule':'仅含完整源条目的预算内视图，不代表其余事实消失；旧记忆为玩家私有，不能传播NPC未知秘密。需旧事实时据精确行号补读。'}},
            'accepted_history': history, 'input': text, 'selection': selected,
             'accounting': ({'reservation': {k:v for k,v in reservation.items() if k!='before_memory'},
                  'runtime':sp.state(story.root,files),'instruction':'面板体力已预扣，原体力见quote.before；不据暂扣判断力竭。按resolution交实际事件与时间；程序决定最终不足5及强制休息。',
                  'event_registry':rr._engine(story.root,story.root)._load_event_registry(),
                  'memory_transfer_sources':{}} if charged else None),
              'story_pacing': '依据当前人物、既有事务、矛盾及玩家意图推进连贯剧情，在真实抉择处交还；偶尔可短答，不固定一两句，不等整场结束，不按字数填充。',
            'operation': {'requested': resolved, 'rule': '玩家明确操作已预检；仅确认执行后的现场反应，不改参数。自由输入最多提议一个有原文依据的登记操作。'},
            'resource_policy': state['policy']['resource'], 'cost_preview': preview_cost,
            'history_archive': {'paths': omitted_archive[-limits['index_entries']:], 'omitted_count':len(omitted_archive),
                'index':archive_index,'required_reads':required_history,
                'rule': '需要旧记录时补读指定原文；更早路径从index取得。按input_known_by/messages_known_by分别核查，禁止扩散未知秘密。'},
            'previous_validation_error': previous_error}
    if charged:
        data['accounting']['memory_transfer_sources'] = {
            'current_round':runtime['last_closed'] if runtime['phase']=='resting' and runtime['last_closed'] else runtime['memory_round'],
            'current_entry':projection['current'],'transfers':projection['transfers'],
            'required_reads':projection['required'],
            'rule':'同回合只追加有长期价值的新fact，预计超600字符或旧条已超限时交完整compact；合并不是追加。旧事实在预算视图中只出现一次，未选入的必要原文按行号真实补读。L1/L2/L3容量3/10/10；转移单条上限见limits，不传播未知秘密。'}
        data['knowledge_rules'] = [{'source':'txt文件/知识库/'+name+'.json','body':e['content']}
            for name in ('世界观类','叙事判断','系统标签类')
            for e in json.loads((story.root/('txt文件/知识库/'+name+'.json')).read_text())['data']['entries']]
    raw = encode_packet(data)
    relative = sr.CACHE + '/' + hashlib.sha256(key.encode()).hexdigest()[:32] + '/live.txt'
    rr._atomic(story.store._path(relative), raw)
    contract = {'messages': [{'kind': 'dialogue|action|narration', 'speaker': '在场人物或旁白空串', 'text': '本段剧情'}],
                 'decision': {'prompt': '本段真实抉择', 'options': [{'id': k, 'text': '当前可行的下一步行为'} for k in OPTION_NAMES]},
                'operation': 'null或一个合法move_player/transfer_item对象；不填成本或任意状态patch',
                'handoff': '无待处理时空字符串',
                'checks': {'intent': '具体依据', 'knowledge': '本场信息边界', 'action': '操作与正文一致或无动作', 'pace': '本段推进及此处交还控制权的依据'}}
    if charged:
        contract['resolution'] = sp.contract(story.root)
    envelope = {'entry_mode': MODE, 'packet': {'path': relative, 'through_line': len(raw.decode().splitlines())},
                'output_contract': contract, 'instruction': '真实完整读取本次packet、memory_transfer_sources.required_reads和history_archive.required_reads指定原文；其余旧事实按本任务精确行号或归档索引补读。返回单个裸JSON，生成连贯剧情及decision中的A/B/C；无需演完一场戏，不写旧完整回合、L1或SYSTEM_LOG。'}
    if charged:
        envelope['instruction'] += ' 必须同时返回resolution：只分类和提供依据，不计算成本/最终面板；免费休息为SYSTEM且实际休息推进，睡眠有正文起止，不以短休冒充整夜。判档/事件/事实/时间只按当前资料；不能把人物系统数值或玩家私有记忆写成NPC知情。'
    return {'protocol': 3, 'interaction_protocol': 3 if charged else 2, 'entry_mode': MODE, 'audit': sources,
            'packet': {**envelope['packet'], 'sha256': rr._digest(raw)},
            'allowed_archive': [*omitted_archive,archive_index,memory_index],
            'allowed_memory_reads':projection['all_refs']+projection['allowed'], 'required_memory_reads':projection['required'],
            'required_history_reads':required_history,
            'command': resolved, 'cast': effective['cast'], 'selection': selected,
            'interaction_scope': rr._digest(rr._json([effective['location'], effective['cast']])),
            'cost_preview': preview_cost,
            'reading_policy': {'version': sr.VERSION},
            'turns': [{'kind': 'user', 'content': json.dumps(envelope, ensure_ascii=False)}]}


def verify(story, key, proof):
    context = json.loads(story._blob(key, '.context.json').read_bytes())
    story._source_check(context)
    if not isinstance(proof, dict) or proof.get('api') != 'Tools.Chat.sendMessageStreaming':
        raise rr.RoundError('缺少Operit正式只读会话审计')
    outcome = proof.get('outcome', {})
    if not isinstance(outcome, dict) or not isinstance(outcome.get('assistant'), dict):
        raise rr.RoundError('会话完成回执结构无效')
    stamp = outcome['assistant'].get('messageTimestamp')
    if (outcome.get('type') != 'committed' or outcome.get('status') != 'completed'
            or type(stamp) is not int or proof.get('snapshot_message_timestamp') != stamp
            or not proof.get('chat_id') or not proof.get('participant_id')):
        raise rr.RoundError('正式会话尚未完成或快照不符')
    tools = proof.get('tools')
    if not isinstance(tools, list) or not 1 <= len(tools) <= 128:
        raise rr.RoundError('读取工具审计无效')
    wanted = context['packet']; covered = set(); verified = []
    memory_refs=context.get('allowed_memory_reads',[])
    required_memory=context.get('required_memory_reads',[])
    memory_covered=set();history_covered={}
    allowed = {wanted['path'], *context.get('allowed_archive', []), *[ref['path'] for ref in memory_refs]}
    raw = story.store._path(wanted['path']).read_bytes()
    if rr._digest(raw) != wanted['sha256']:
        raise rr.ConflictError('本次资料包已经改变')
    for call in tools:
        if not isinstance(call, dict) or call.get('name') not in ('read_file', 'read_file_full', 'read_file_part', 'file_info'):
            raise rr.RoundError('正式互动仅允许读取指定资料')
        params = call.get('parameters', {})
        if not isinstance(params, dict) or not isinstance(params.get('path'), str):
            raise rr.RoundError('读取工具参数无效')
        path = params['path']
        for prefix in (proof.get('workspace'), str(story.root)):
            if isinstance(prefix, str) and prefix and path.startswith(prefix.rstrip('/') + '/'):
                path = path[len(prefix.rstrip('/')) + 1:]
                break
        if path not in allowed:
            raise rr.RoundError('读取了非本任务资料')
        if path==rr.FILES[0]:
            begin,end=params.get('start_line'),params.get('end_line')
            if (call['name']!='read_file_part' or type(begin) is not int or type(end) is not int
                    or not any(ref['start_line']<=begin<=end<=ref['end_line'] for ref in memory_refs)):
                raise rr.RoundError('记忆补读须使用本任务指定的精确行号，不得整库重读')
        entry = {'name': call['name'], 'path': path, 'status': call.get('status')}
        if call.get('status') == 'success' and call['name'] != 'file_info':
            source = story.store._path(path).read_bytes()
            begin, end = params.get('start_line', 1), params.get('end_line', len(source.decode().splitlines()))
            try:
                lines = sr.verified_lines(source, call.get('result_text', ''), int(begin), int(end))
            except (ValueError, TypeError) as exc:
                raise rr.RoundError('读取内容未核验: ' + str(exc)) from exc
            entry.update(verified_lines=lines, source_sha256_at_result=rr._digest(source))
            if path == wanted['path']:
                covered.update(lines)
            if path==rr.FILES[0]:memory_covered.update(lines)
            if path in context.get('required_history_reads',[]):history_covered.setdefault(path,set()).update(lines)
        verified.append(entry)
    if not set(range(1, wanted['through_line'] + 1)) <= covered:
        raise rr.RoundError('正式互动资料包未完整读取；截断须补完')
    if any(not set(range(ref['start_line'],ref['end_line']+1))<=memory_covered for ref in required_memory):
        raise rr.RoundError('必要记忆源未完整补读，不能用截断视图合并或转移')
    for path in context.get('required_history_reads',[]):
        if not set(range(1,len(story.store._path(path).read_text().splitlines())+1))<=history_covered.get(path,set()):
            raise rr.RoundError('最近剧情原文超过自动预算，须完整补读后再续写')
    return {'required_reads_verified': True, 'origin': 'operit_session', 'chat_id': proof['chat_id'],
            'verified_tools': verified, 'source_manifest': context['audit'],
            'snapshot_message_timestamp': stamp, 'packet_sha256': wanted['sha256']}


def assemble(story, key, job, result, context, audit):
    charged = sp.enabled(story.root)
    fields = {'messages','decision','operation','handoff','checks'} | ({'resolution'} if charged else set())
    rr._keys(result, fields, '互动结果', fields)
    decision(result['decision'])
    rr._keys(result['checks'], {'intent', 'knowledge', 'action', 'pace'}, 'checks', {'intent', 'knowledge', 'action', 'pace'})
    for name, value in result['checks'].items():
        rr._audit_line(value, 'checks.' + name, reason=True)
    if context['command'] and result['operation'] != context['command']:
        if result['operation'] is not None or not isinstance(result['handoff'], str) or not result['handoff'].strip():
            raise rr.RoundError('模型不能变更玩家明确操作；不能执行时须明确待处理且不提交操作')
    accepted_audit = {**audit, 'checks': result['checks']}
    if charged:
        if not job.get('reservation') or job['reservation']['status']!='held':raise rr.ConflictError('预扣已结束，拒绝旧结果')
        accepted_audit['reservation'] = copy.deepcopy(job['reservation'])
    if context['command']:
        accepted_audit['origin'] = 'player_action'
    return {'schema_version': 3 if charged else 2, 'entry_mode': MODE, 'request_id': key,
            **({'resolution':result['resolution']} if charged else {}),
            'base_revision': job.get('working_revision', job['base_revision']), 'input': job['action'],
            **{k: result[k] for k in ('messages', 'decision', 'operation', 'handoff')},
            'selection': job.get('selection'), 'audit': accepted_audit}

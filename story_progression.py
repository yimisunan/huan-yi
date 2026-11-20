"""Deterministic story accounting. Only RoundStore publishes its staged output."""
import base64
import copy
import json
from pathlib import Path
import re
import round_runtime as rr

COSTS = {'A': 5, 'B': 10, 'C': 15}
TASKS = '.round-runtime/story/tasks.json'
PURE_ITEM = re.compile(r'\s*使用恢复道具\s*[：:]?\s*(ITEM-\d+)\s*[。！!]?\s*')


MEMORY_DEFAULTS = {'fact_chars':160, 'round_chars':600, 'l2_chars':240, 'l3_chars':600,
                   'l4_chars':900, 'context_chars':6000, 'history_turns':6,
                   'history_chars':12000, 'index_entries':24}


def memory_policy(root):
    policy = rr.load_request((Path(root)/'txt文件/互动运行配置.json').read_text()).get('memory', MEMORY_DEFAULTS)
    if (not isinstance(policy, dict) or set(policy) != set(MEMORY_DEFAULTS)
            or any(type(v) is not int or v < 1 or v > 100000 for v in policy.values())):
        raise rr.RoundError('记忆预算配置无效')
    return policy


def memory_text(value, label, limit, empty=False):
    if (not isinstance(value, str) or len(value) > limit or any(c in value for c in ('\n','\r','\x00','▲','【回合生命周期】'))
            or re.match(r'^\s*【\d',value) and label != 'memory.transfer'):
        raise rr.RoundError(label+'须为预算内的单段文本，不得注入结构锚点')
    if not empty and not value.strip():
        raise rr.RoundError(label+'不得为空')
    return value.strip()


def memory_merge(root, layers, number, clock, value, system=False):
    """Model supplies semantic compaction; never silently truncate accepted facts."""
    prior = next((entry.split('】',1)[1] for entry in layers['L1'] if entry.startswith('【'+str(number)+'】')), '')
    if system:
        return None
    limit = memory_policy(root)['round_chars']
    fact = value['fact'].strip()
    compact = value.get('compact','').strip()
    if compact:
        if not prior:
            raise rr.RoundError('同回合合并摘要缺少原条目')
        return compact
    if fact and re.sub(r'\s','',fact) in re.sub(r'\s','',prior):
        fact = ''
    stamped = '第'+str(clock['day'])+'天 '+clock['time']+' '+fact if fact else ''
    merged = '\n'.join(s for s in (prior,stamped) if s).strip()
    if len(merged) > limit:
        raise rr.RoundError('本回合记忆超过预算，须据原文交memory.compact保留重要事实、待办和知情边界；未截断旧事实')
    return merged if merged and merged != prior else None


def enabled(root):
    return json.loads((Path(root)/'txt文件/互动运行配置.json').read_text())['resource'].get('scheme') == 'fixed_tiers'


def config(root):
    value = rr.load_request((Path(root)/'txt文件/互动运行配置.json').read_text())
    r = value['resource']
    if (value['version'] != 2 or r.get('status') != 'active' or r.get('scheme') != 'fixed_tiers'
            or r.get('costs') != COSTS or r.get('custom_reserve') != 15
            or r.get('attribute') != '体力' or r.get('maximum') != 100
            or r.get('item_recovery_percent') != 20 or r.get('minimum_action') != 5):
        raise rr.RoundError('固定三档配置非法，禁止隐式降级或重复旧基础费')
    return value


def stamina(root, files):
    engine = rr._engine(Path(root), Path(root))
    value = engine._read_attr_value(files[rr.FILES[0]].decode(), '系统宿主', '体力')
    if type(value) is not int or not 0 <= value <= config(root)['resource']['maximum']:
        raise rr.RoundError('正式宿主体力缺失或超出范围')
    return value


def state(root, files):
    data = json.loads(files.get('data.json') or b'{}')
    value = data.get('story_runtime')
    if value is None:
        engine = rr._engine(Path(root), Path(root))
        _, _, previous = rr._memory_state(engine, files)
        content = files[rr.FILES[0]].decode()
        old = re.search(r'^【回合生命周期】\s*\n([^\n]+)', content, re.M)
        action_index = json.loads(old[1]).get('round', 0) if old else 0
        return {'version': 1, 'clock': None, 'memory_round': previous+1,
                'last_closed': previous, 'phase': 'ready', 'item_recovered': 0,
                'action_index': action_index, 'closed_by': ''}
    required = {'version','clock','memory_round','last_closed','phase','item_recovered','action_index','closed_by'}
    rr._keys(value, required, 'story_runtime', required)
    if value['version'] != 1 or value['phase'] not in ('ready','resting'):
        raise rr.RecoveryError('互动时间状态无效')
    for key in ('memory_round','last_closed','item_recovered','action_index'):
        rr._integer(value[key], key, 1 if key == 'memory_round' else 0)
    if value['last_closed'] != value['memory_round']-1 or value['item_recovered'] > 20:
        raise rr.RecoveryError('互动回合或道具额度不一致')
    if value['clock'] is not None:
        minute(value['clock'])
    return copy.deepcopy(value)


def minute(clock):
    rr._keys(clock, {'day','time'}, 'clock', {'day','time'})
    rr._integer(clock['day'], 'clock.day', 1)
    if not isinstance(clock['time'], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock['time']):
        raise rr.RoundError('游戏时刻须为HH:MM')
    hour, part = map(int, clock['time'].split(':'))
    return (clock['day']-1)*1440+hour*60+part


def item_quote(root, files, item_id):
    if not isinstance(item_id,str) or not re.fullmatch(r'ITEM-\d+',item_id):
        raise rr.RoundError('恢复道具ID无效')
    engine=rr._engine(Path(root),Path(root))
    text=(files[rr.FILES[1]] or b'').decode()
    found=engine._find_item_block(text,item_id=item_id)
    if not found:
        raise rr.RoundError('没有该活跃库存，未消耗道具')
    fields=engine._parse_item_block(found['block'])
    if (fields['当前状态']!='仓库中' or fields['使用对象'] not in ('','无','未使用','徐志北')
            or not fields['数量'].isdigit() or int(fields['数量']) < 1
            or re.fullmatch(r'0\s*(?:回合|次|分钟)?',fields['剩余时效'])):
        raise rr.RoundError('该道具未持有或已过期，未消耗')
    effect=re.fullmatch(r'host_stamina:([1-9]\d{0,3})',fields.get('系统效果',''))
    if not effect:
        raise rr.RoundError('该道具未登记宿主体力恢复效果，不能猜测数值')
    if '临时性' in fields['类型'] and fields['时效'].isdigit() and int(fields['时效']) > 0:
        timer=re.search(r'^'+re.escape(item_id)+r'：(\d+)回合\s*\|',files[rr.FILES[0]].decode(),re.M)
        if not timer or int(timer[1]) < 1:
            raise rr.RoundError('道具有效时效未核实，未消耗')
    runtime=state(root,files)
    gain=min(int(effect[1]),20-runtime['item_recovered'],100-stamina(root,files))
    if gain <= 0:
        raise rr.RoundError('体力已满或两次整夜间恢复额度已用完，未消耗道具')
    return {'item_id':item_id,'name':re.search(r'【道具名称】：([^\n]+)',found['block'])[1].strip(),
            'effect':int(effect[1]),'recovery':gain,'quantity':1,'remaining_budget':20-runtime['item_recovered']-gain}


def quote(root, files, selected, text, command=None):
    config(root)
    if selected is None:
        raise rr.ConflictError('收费入口须绑定当前抉择，旧格式不可绕过')
    option=selected['option_id']
    runtime=state(root,files)
    current=stamina(root,files)
    match=PURE_ITEM.fullmatch(text) if option=='CUSTOM' else None
    item=command if command and command.get('code')=='use_recovery_item' else None
    if item:
        rr._keys(item,{'code','item_id'},'use_recovery_item',{'code','item_id'})
        if option!='CUSTOM' or not match or match[1]!=item['item_id']:
            raise rr.RoundError('免费道具只能提交纯使用命令，不可混入额外行动')
    if match:
        item={'code':'use_recovery_item','item_id':match[1]}
    if runtime['phase']=='resting' or current < 5:
        if option not in ('REST','BEGIN') or item:
            raise rr.RoundError('体力不足或正在强制休息，普通行动暂停')
        kind='rest'
    elif option=='REST':
        raise rr.ConflictError('当前没有待完成的强制休息')
    elif option=='BEGIN':kind='begin'
    elif item:kind='item'
    else:kind='action'
    amount=COSTS.get(option,15) if kind=='action' else 0
    if current < amount:
        raise rr.RoundError('体力不足以预扣本档费用，请选择可用档位或提前使用恢复道具')
    value={'status':'active','scheme':'fixed_tiers','kind':kind,'attribute':'体力','total':amount,
           'before':current,'after':current-amount,'policy_version':2,'option_id':option}
    if kind=='item':value['item']=item_quote(root,files,item['item_id'])
    return value


def change_stamina(root, files, value):
    result=dict(files)
    engine=rr._engine(Path(root),Path(root))
    result[rr.FILES[0]]=engine._simulate_panel(files[rr.FILES[0]].decode(),{'系统宿主':{'体力':value}}).encode()
    return result


def commit_tasks(store, files, tasks):
    after=dict(files)
    after[rr.META]=rr._json(store._ledger())
    after[TASKS]=rr._json(tasks)
    store._commit_files(after)


def reserve(service, tasks, job, files, cost):
    held=change_stamina(service.root,files,cost['after'])
    job['reservation']={'status':'held','quote':cost,'before_memory':base64.b64encode(files[rr.FILES[0]]).decode(),
                        'original_revision':rr._revision(files),'held_revision':rr._revision(held)}
    job['working_revision']=rr._revision(held)
    job['status']='preparing'
    tasks['jobs'][job['request_id']]=job;tasks['latest']=job['request_id']
    commit_tasks(service.store,held,tasks)
    return held


def refund(service,tasks,job,status,error):
    reservation=job.get('reservation')
    committed=service.store._ledger()['receipts'].get(job['request_id'])
    if committed:
        job.update(status='committed',error='',receipt=committed['receipt'],lease=None)
        if reservation:reservation['status']='settled'
        commit_tasks(service.store,service.store._files(),tasks)
        return
    if reservation and reservation['status']=='held':
        files=service.store._files()
        if rr._revision(files)!=reservation['held_revision']:
            job.update(status='refund_pending',lease=None,error='存档被外部改动，退款待恢复；未覆盖他方更改。')
            commit_tasks(service.store,files,tasks)
            raise rr.RecoveryError(job['error'])
        files[rr.FILES[0]]=base64.b64decode(reservation['before_memory'],validate=True)
        if rr._revision(files)!=reservation['original_revision']:
            raise rr.RecoveryError('预扣原始指纹不一致，拒绝猜测退款')
        reservation['status']='refunded'
        job['refund']={'amount':reservation['quote']['total'],'status':'refunded','reason':error}
        job.update(status=status,error=error,lease=None)
        commit_tasks(service.store,files,tasks)
    else:
        job.update(status=status,error=error,lease=None)
        commit_tasks(service.store,service.store._files(),tasks)


def resolution(root,files,body):
    value=body['resolution']
    required={'category','basis','clock','events','memory','conditions','sleep','task','items'}
    rr._keys(value,required,'resolution',required)
    selected=body['selection'];reservation=body['audit'].get('reservation')
    if not isinstance(reservation,dict) or reservation.get('status')!='held':
        raise rr.RoundError('缺少由正式任务写入器登记的预扣')
    cost=reservation['quote'];kind=cost['kind']
    if value['category'] not in (*COSTS,'SYSTEM'):
        raise rr.RoundError('分类只能为A/B/C或免费系统SYSTEM')
    if kind=='action':
        rr._audit_line(value['basis'],'resolution.basis',reason=True)
        if selected['option_id'] in COSTS and value['category']!=selected['option_id']:
            raise rr.RoundError('固定选项不允许模型重新定价')
        if value['category'] not in COSTS:
            raise rr.RoundError('普通自定义须判A/B/C，不得免费')
    elif value['category']!='SYSTEM':
        raise rr.RoundError('启动/道具/休息须为SYSTEM')
    rr._keys(value['clock'],{'day','time','basis'},'resolution.clock',{'day','time','basis'})
    clock={k:value['clock'][k] for k in ('day','time')};end=minute(clock)
    rr._audit_line(value['clock']['basis'],'clock.basis',reason=True)
    runtime=state(root,files);start=minute(runtime['clock']) if runtime['clock'] else None
    if start is None and clock['day']!=1 and cost['kind']!='rest':
        raise rr.RoundError('首次时钟从游戏第1天初始化，不能借初始化关闭空回合')
    if start is not None and (end<start or end-start>7*1440):
        raise rr.RoundError('游戏时间须连续向前，单次不得跳过七天')
    texts='\n'.join(m['text'] for m in body['messages'])
    sleep=value['sleep']
    rr._keys(sleep,{'kind','start','evidence'},'sleep',{'kind','start','evidence'})
    if sleep['kind'] not in ('none','interrupted','overnight','collapse'):
        raise rr.RoundError('睡眠状态非法')
    if sleep['kind']!='none':
        rr._text(sleep['evidence'],'sleep.evidence',500)
        if sleep['evidence'] not in texts:
            raise rr.RoundError('休息依据必须引用本段实际正文')
    elif sleep['start'] is not None or sleep['evidence']!='':
        raise rr.RoundError('无睡眠不应携带伪起点或依据')
    if sleep['kind']=='overnight':
        begun=minute(sleep['start'])
        if ((start is not None and begun<start) or begun>=end or end-begun<360
                or (begun//1440>=end//1440 and int(sleep['start']['time'][:2])>=6)
                or not 5<=int(clock['time'][:2])<=12):
            raise rr.RoundError('安稳一晚须有至少六小时、跨夜至清晨的连续起止时间；短休不满恢复')
    if kind=='rest' and (sleep['kind'] not in ('interrupted','overnight') or (start is not None and end<=start)):
        raise rr.RoundError('免费休息须实际推进休息过渡；中断保持休息')
    if kind=='begin' and sleep['kind']!='none':
        raise rr.RoundError('启动段不得凭空结算睡眠')
    limits=memory_policy(root)
    rr._keys(value['memory'],{'fact','transfers','compact'},'memory',{'fact','transfers'})
    memory_text(value['memory']['fact'],'memory.fact',limits['fact_chars'],empty=True)
    memory_text(value['memory'].get('compact',''),'memory.compact',limits['round_chars'],empty=True)
    rr._keys(value['memory']['transfers'],{'l1_to_l2_condensed','l2_to_l3_summary','l3_to_l4_summary'},'memory.transfers')
    for key,text in value['memory']['transfers'].items():
        memory_text(text,'memory.transfer',limits[{'l1_to_l2_condensed':'l2_chars','l2_to_l3_summary':'l3_chars','l3_to_l4_summary':'l4_chars'}[key]])
    grouped={key:[] if key=='host_events' else {} for key in rr._engine(Path(root),Path(root))._load_event_registry()['groups']}
    if not isinstance(value['events'],list) or len(value['events'])>40:
        raise rr.RoundError('事件须为最多40组的数组')
    for event in value['events']:
        rr._keys(event,{'group','target','tags','evidence'},'event',{'group','target','tags','evidence'})
        group=event['group'];target=event['target'];tags=event['tags']
        if not isinstance(tags,list) or not tags or not all(isinstance(t,str) for t in tags):raise rr.RoundError('事件标签须为非空文本数组')
        presence=rr._engine(Path(root),Path(root)).parse_presence_from_memory(files[rr.FILES[0]].decode())
        place=body['operation'].get('destination') if body.get('operation') and body['operation']['code']=='move_player' else presence['徐志北']['location']
        if target!='系统宿主' and (target not in presence or presence[target]['location']!=place):raise rr.RoundError('事件对象不在本段实际场内')
        if group not in grouped or (group=='host_events' and target!='系统宿主'):
            raise rr.RoundError('事件组或宿主目标无效')
        rr._text(event['evidence'],'event.evidence',800)
        if event['evidence'] not in texts:
            raise rr.RoundError('事件必须引用本段实际正文，不以选项或计划作已发生依据')
        if group=='host_events':grouped[group].extend(tags)
        else:grouped[group].setdefault(target,[]).extend(tags)
    engine=rr._engine(Path(root),Path(root))
    rr._validate_event_fields(Path(root),engine,grouped)
    if kind=='item' and (runtime['clock'] is None or clock!=runtime['clock'] or sleep['kind']!='none'):
        raise rr.RoundError('道具系统不推进游戏时间或睡眠')
    if kind!='action' and (value['events'] or value['task'] is not None or value['items']):
        raise rr.RoundError('免费系统操作不可附带额外数值事件、任务或物品奖励')
    if engine._event_tag('HOST_15') in grouped['host_events'] and sleep['kind']!='overnight':
        raise rr.RoundError('整夜恢复事件缺少实际整夜睡眠')
    forbidden={engine._event_tag('HOST_13'),engine._event_tag('HOST_14'),engine._event_tag('HOST_15'),engine._event_tag('HOST_07')}
    grouped['host_events']=[tag for tag in grouped['host_events'] if tag not in forbidden]
    if kind=='action':
        if not isinstance(value['conditions'],dict):
            raise rr.RoundError('普通付费行动的resolution.conditions必须是完整对象，即使只作澄清或未移动；字段为intensity/effective_progress/scene/npc/action_changed/stress_signals/breakout_triggered，无NPC仅npc为null')
        try:rr._round_conditions(value['conditions'],grouped)
        except rr.RoundError as exc:raise rr.RoundError('resolution.conditions字段不符：'+str(exc)) from exc
        if value['conditions']['intensity']!=value['category']:
            raise rr.RoundError('有效行动烈度须与本次实际判档一致')
    elif value['conditions'] is not None:
        raise rr.RoundError('免费操作不推进有效行动计数')
    if not isinstance(value['items'],list) or len(value['items'])>8:
        raise rr.RoundError('道具增量须为数组')
    if value['task'] is not None:
        task=value['task'];rr._keys(task,{'title','target','attr','value','tier','item_desc'},'task',{'title','target','attr','value','tier','item_desc'})
        rr._integer(task['value'],'task.value',1)
        for key in ('title','target','attr','tier','item_desc'):rr._text(task[key],'task.'+key,300)
    for item in value['items']:
        rr._keys(item,{'entry','evidence'},'item',{'entry','evidence'})
        rr._text(item['evidence'],'item.evidence',500)
        if item['evidence'] not in texts:raise rr.RoundError('道具变更缺正文依据')
        entry=item['entry'];rr._keys(entry,{'id','name','type','desc','quantity','status','location','target','duration','expire_rule','usage_record','remark','action','system_effect'},'item.entry',{'name','action'})
        for field,text in entry.items():
            if field=='quantity':rr._integer(text,'item.quantity',1)
            elif not isinstance(text,str) or '\n' in text or '\r' in text:raise rr.RoundError('道具字段须为单行文本')
        if entry['action'] not in ('add','consume','update','archive'):raise rr.RoundError('道具动作无效')
        if entry.get('system_effect') and not re.fullmatch(r'host_stamina:[1-9]\d{0,3}',entry['system_effect']):raise rr.RoundError('道具系统效果未登记')
    final_cost=COSTS[value['category']] if kind=='action' else 0
    return {'runtime':runtime,'cost':cost,'refund':cost['total']-final_cost,'net':final_cost,
            'events':grouped,'clock':clock,'elapsed':0 if start is None else end-start,'sleep':sleep}


def panel_values(engine,text):
    current=text.split('▶ 上回合历史快照',1)[0]
    result={}
    for name in ('系统宿主','沈知韫','徐念薇','苏婉青','徐承邺'):
        match=re.search(r'^\['+re.escape(name)+r'\]([^\n]+)',current,re.M)
        if not match:continue
        for pair in re.finditer(r'(积分|经验值|体力|魅力|商业嗅觉|好感|堕落|欲望|羞耻|高潮|内射)\s+(-?\d+)',match[1]):result[(name,pair[1])]=int(pair[2])
    return result


def apply_staged(store,engine,stage,body,files,parsed):
    runtime=copy.deepcopy(parsed['runtime']);value=body['resolution'];kind=parsed['cost']['kind']
    memory_path=stage/rr.FILES[0]
    before=base64.b64decode(body['audit']['reservation']['before_memory'],validate=True).decode()
    content=memory_path.read_text();current=engine._read_attr_value(content,'系统宿主','体力')
    rr._atomic(memory_path,engine._simulate_panel(content,{'系统宿主':{'体力':current+parsed['refund']}}).encode())
    events=parsed['events'];lifecycle=None;states=None;counts=None
    if kind=='action':
        # Lifecycle units are accepted paid actions, independently of memory rounds.
        action=runtime['action_index']+1
        lifecycle_body={'current_round':action,'memory_deltas':{'round_conditions':value['conditions']},
                        'micro_state_changes':{},'counter_updates':{},'system_log':'',**copy.deepcopy(events)}
        derived,lifecycle,states,counts=rr._derive_lifecycle(engine,lifecycle_body,memory_path.read_text())
        events={k:derived[k] for k in events};runtime['action_index']=action
        if any(t.startswith('兑换道具_') for t in events['host_events']):
            points=engine._read_attr_value(memory_path.read_text(),'系统宿主','积分')
            if sum(int(t.split('_')[1]) for t in events['host_events'] if t.startswith('兑换道具_'))>points:raise rr.RoundError('兑换积分不足，未接受道具或扣费')
        rr._engine_call(engine.apply_story_events,events,value['task'],runtime['memory_round'])
        rr._engine_call(engine.update_persistent_buffs,str(memory_path),events['shame_events'],{})
        rr._engine_call(engine.process_item_timers,str(memory_path),str(stage/rr.FILES[1]),action)
        memory=rr._write_lifecycle(rr._write_counters(rr._write_micro(memory_path.read_text(),states),counts),lifecycle)
        rr._atomic(memory_path,memory.encode())
        if value['items']:
            host=events['host_events'];task=engine._parse_task_block(memory)
            additions=sum(item['entry']['action']=='add' for item in value['items'])
            purchases=sum(t.startswith('兑换道具_') for t in host)
            if additions>purchases+bool(task and task.get('pending_item')):raise rr.RoundError('新增道具组数超过实际兑换或任务待发资格')
            for item in value['items']:
                entry=item['entry']
                if entry['action']=='add' and not any(t.startswith('兑换道具_') for t in host) and not (task and task.get('pending_item')):
                    raise rr.RoundError('新增道具缺已接受兑换或任务待发资格')
                if entry['action']=='add':
                    if entry.get('id'):raise rr.RoundError('新增道具ID由执行器生成，不能覆盖已有编号')
                    if engine._find_item_block((files[rr.FILES[1]] or b'').decode(),name=entry['name']):raise rr.RoundError('同名道具增发须保留已有登记字段，当前不自动改写')
                if entry['action']!='add':
                    original=engine._find_item_block((files[rr.FILES[1]] or b'').decode(),item_id=entry.get('id',''))
                    if original is None:raise rr.RoundError('道具增量未指向真实活跃ID')
                    original_fields=engine._parse_item_block(original['block'])
                    original_name=re.search(r'【道具名称】：([^\n]+)',original['block'])[1].strip()
                    if entry['name']!=original_name:raise rr.RoundError('道具名称与真实ID不一致')
                    if entry['action']=='update':raise rr.RoundError('当前正式入口不允许任意覆写已有道具字段')
                    if entry['action']=='consume' and entry.get('quantity',1)>engine._int_of(original_fields['数量'],0):raise rr.RoundError('道具消耗量超过库存')
                    if entry.get('system_effect') and entry['system_effect']!=engine._parse_item_block(original['block']).get('系统效果',''):raise rr.RoundError('不能为已有物品臆造恢复效果')
                rr._engine_call(engine.update_item_catalog,runtime['memory_round'],[entry])
            if task and task.get('pending_item') and any(i['entry']['action']=='add' for i in value['items']):
                task['pending_item']=None;rr._engine_call(engine._write_task_block,task)
    if body['operation'] and kind!='item':rr._engine_call(engine.apply_interaction_operation,body['operation'])
    item_receipt=None
    if kind=='item':
        item_receipt=parsed['cost']['item']
        rr._engine_call(engine.consume_story_recovery_item,item_receipt['item_id'],item_receipt['recovery'],runtime['memory_round'])
        runtime['item_recovered']+=item_receipt['recovery']
    if kind!='item':
        old_clock=runtime['clock'];new_clock=parsed['clock']
        hours=(minute(new_clock)//60-minute(old_clock)//60) if old_clock else 0
        if kind=='action' or hours:
            rr._engine_call(engine.process_vigilance_system,events['vigilance_events'],events['shame_events'],str(memory_path),elapsed_hours=hours,roll_home=kind=='action')
        runtime['clock']=new_clock
    if parsed['sleep']['kind']=='overnight':
        memory=memory_path.read_text()
        rr._atomic(memory_path,engine._simulate_panel(memory,{'系统宿主':{'体力':100}}).encode())
        runtime['item_recovered']=0
    final=engine._read_attr_value(memory_path.read_text(),'系统宿主','体力')
    low=final<5 or parsed['sleep']['kind']=='collapse'
    was_resting=runtime['phase']=='resting'
    crossed=parsed['runtime']['clock'] is not None and parsed['clock']['day']>parsed['runtime']['clock']['day']
    memory_round=runtime['last_closed'] if was_resting and runtime['last_closed'] else runtime['memory_round']
    memory_round=max(1,memory_round)
    old_layers=engine._parse_memory_layer_items(memory_path.read_text())
    merged=memory_merge(store.root,old_layers,memory_round,parsed['clock'],value['memory'],system=kind=='item')
    transfers={} if kind=='item' else copy.deepcopy(value['memory']['transfers'])
    deltas={**({'l1_new_round':merged} if merged else {}),**transfers}
    if deltas:
        rr._engine_call(engine.update_global_memory,memory_round,deltas,{})
    closed=False
    if not was_resting and (crossed or low):
        runtime['last_closed']=runtime['memory_round'];runtime['memory_round']+=1;runtime['closed_by']=body['request_id'];closed=True
    if kind=='rest' or low:
        if not closed and not was_resting and kind=='rest':
            runtime['last_closed']=runtime['memory_round'];runtime['memory_round']+=1;runtime['closed_by']=body['request_id'];closed=True
        runtime['phase']='ready' if parsed['sleep']['kind']=='overnight' and final>=5 else 'resting'
    else:runtime['phase']='ready'
    after_memory=memory_path.read_text();before_values=panel_values(engine,before);after_values=panel_values(engine,after_memory)
    changes=[{'target':name,'attribute':attr,'before':old,'after':after_values[key],'delta':after_values[key]-old}
             for key,old in before_values.items() for name,attr in (key,) if key in after_values and after_values[key]!=old]
    receipt={'request_id':body['request_id'],'kind':kind,'reserved':parsed['cost']['total'],'refunded':parsed['refund'],
             'items_changed':(files[rr.FILES[1]] or b'')!=(stage/rr.FILES[1]).read_bytes(),
             'task_after':engine._parse_task_block(memory_path.read_text()),
             'net_cost':parsed['net'],'stamina_before':parsed['cost']['before'],'stamina_after':final,'changes':changes,
             'events':events,'item':item_receipt,'clock':runtime['clock'],'memory_round':runtime['memory_round'],
             'closed_round':runtime['last_closed'] if closed else None,'phase':runtime['phase'],'item_budget':20-runtime['item_recovered'],
             'sleep_completed':parsed['sleep']['kind']=='overnight'}
    return runtime,receipt


def category_policy(kind, option_id=None):
    if kind != 'action':
        return {'mode':'system', 'required_category':'SYSTEM',
                'instruction':'本次为免费系统过渡，resolution.category只能为SYSTEM。'}
    if option_id in COSTS:
        return {'mode':'fixed_option', 'required_category':option_id,
                'instruction':f'本次玩家已选固定{option_id}选项，resolution.category必须原样返回{option_id}，不能按正文重新判档或降价。按已授权原行动生成，不因档位提高接触、情绪或剧情烈度，不保证成功。conditions.intensity按现有契约与category一致，不据此虚构事件。'}
    return {'mode':'custom', 'required_category':None,
            'instruction':'本次为自定义行动，resolution.category按实际成立行为判A/B/C并给出依据，不得使用SYSTEM；费用由程序计算。'}


def resolution_policy(kind, option_id=None):
    return {'kind':kind,'conditions_required':kind=='action',
            'category_policy':category_policy(kind, option_id),
            'conditions_fields':['intensity','effective_progress','scene','npc','action_changed','stress_signals','breakout_triggered'],
            'instruction':'普通付费行动必须提交七字段conditions对象；澄清/未移动也填，按事实用false，不改字段名；无NPC仅npc为空。免费SYSTEM的conditions为空。'}


def contract(root=None,kind='action',option_id=None):
    limits=memory_policy(root) if root is not None else MEMORY_DEFAULTS
    category = category_policy(kind, option_id)
    return {'category':category['required_category'] or 'A|B|C','basis':category['instruction'],
            'clock':{'day':1,'time':'HH:MM','basis':'实际经过的行为与时间依据，首次从剧情初始化'},
            'events':[{'group':'登记事件组','target':'本场对象或系统宿主','tags':['登记原标签'],'evidence':'本段原文子串'}],
            'memory':{'fact':f"无长期新增价值时空串；否则<={limits['fact_chars']}字符，仅记承诺/待办/关系或信息变化/不可逆事实，计划保留未执行状态",
                      'compact':f"可省略或空串；同回合摘要预计超过{limits['round_chars']}字符或旧条已超限时必交<={limits['round_chars']}字符的完整合并摘要，合并旧事实与本次fact，保留重要承诺、因果、待办及知情范围",
                      'transfers':{}},
            'conditions':{'intensity':'A|B|C','effective_progress':True,'scene':'现场地点','npc':None,'action_changed':True,'stress_signals':0,'breakout_triggered':[]} if kind=='action' else None,
            'sleep':{'kind':'none|collapse|interrupted|overnight','start':None,'evidence':''},'task':None,'items':[]}


def create(service,body,retry_key=None):
    service.start()
    rr._keys(body,{'request_id','base_revision','action','model_key','entry_mode','operation','save_epoch','selection'},'提交',{'request_id','base_revision','action','entry_mode','save_epoch','selection'})
    key=body['request_id'];action=body['action'];revision=body['base_revision']
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',key):raise rr.RoundError('请求编号无效')
    rr._text(action,'action',2000)
    model_key=service._model_key(body);selected=body['selection'];command=body.get('operation')
    import interaction_runtime as ir
    with service.store._locked():
        tasks=service._read();service._expire(tasks)
        existing=tasks['jobs'].get(key)
        if existing and retry_key is None:
            if any(existing.get(k)!=body.get(k) for k in ('base_revision','action','entry_mode','save_epoch','selection','operation','model_key')):
                raise rr.ConflictError('同编号不得改动原选择')
            return {'task':service._public(existing)}
        if any(j['status'] in {'preparing','queued','generating','validating','refund_pending'} for j in tasks['jobs'].values()):raise rr.ConflictError('已有行动正在处理或等待退款恢复')
        files=service.store._files()
        if service._save_epoch()!=body['save_epoch'] or rr._revision(files)!=revision:raise rr.ConflictError('存档或选择已更新，请恢复当前段落')
        ir.selection(service.root,files,selected,action,command)
        cost=quote(service.root,files,selected,action,command)
        if cost['kind']=='item':command={'code':'use_recovery_item','item_id':cost['item']['item_id']}
        if command:ir.operation(service.root,files,command,action,True)
        previous_error=(existing or {}).get('error','') if retry_key is not None else ''
        job={**(existing or {}),'request_id':key,'base_revision':revision,'action':action,'entry_mode':ir.MODE,
             'model_key':model_key,'operation':body.get('operation'),'save_epoch':body['save_epoch'],'selection':selected,
             'current_round':state(service.root,files)['memory_round'],'status':'preparing','attempt':(existing or {}).get('attempt',0),
             'created_at':__import__('time').time(),'error':'','lease':None,'cost_preview':cost}
        job.pop('refund',None);job.pop('receipt',None);job.pop('generation_model',None)
        service._blob(key,'.assembled.json').unlink(missing_ok=True)
        reserve(service,tasks,job,files,cost)
    try:
        prepared={'base_revision':job['working_revision'],'current_round':job['current_round'],
                  'snapshot':{n:data.decode() if data is not None else None for n,data in held_files(service,job).items()}}
        if cost['kind']=='item':
            context={'protocol':3,'interaction_protocol':3,'entry_mode':ir.MODE,'audit':{n:rr._digest(service.store._path(n).read_bytes()) for n in ('story_progression.py','injection_core.py','txt文件/互动运行配置.json','txt文件/事件注册表.json')},'system_item':True,'command':command,'selection':selected}
        else:
            context=ir.packet(service,prepared,key,action,command,previous_error=previous_error,selected=selected,reservation=job['reservation'])
        with service.store._locked():
            tasks=service._read();current=tasks['jobs'][key]
            if current['status']!='preparing' or current['reservation']!=job['reservation']:raise rr.ConflictError('任务已取消')
            rr._atomic(service._blob(key,'.context.json'),rr._json(context))
            if cost['kind']=='item':
                runtime=state(service.root,service.store._files())
                clock=runtime['clock'] or {'day':1,'time':'12:00'}
                text='使用'+cost['item']['name']+'后，体力恢复了'+str(cost['item']['recovery'])+'点。'
                row=ir.segment(service.root,service.store._files())
                decision=copy.deepcopy(row['decision'])
                result={'messages':[{'kind':'narration','speaker':'','text':text}],'decision':decision,'operation':command,'handoff':'',
                        'checks':{'intent':'玩家只使用已登记恢复道具。','knowledge':'恢复信息仅供玩家。','action':'使用明确ID的实际道具。','pace':'系统恢复结束，仍由玩家选择下一步。'},
                        'resolution':{'category':'SYSTEM','basis':'纯道具系统操作','clock':{**clock,'basis':'纯道具使用不推进剧情时间'},
                                      'events':[],'memory':{'fact':'','transfers':{}},'conditions':None,'sleep':{'kind':'none','start':None,'evidence':''},'task':None,'items':[]}}
                audit={'required_reads_verified':True,'origin':'player_action','reservation':current['reservation'],'checks':result['checks']}
                payload={'schema_version':3,'entry_mode':ir.MODE,'request_id':key,'base_revision':current['working_revision'],'input':action,
                         'selection':selected,'audit':audit,**{k:result[k] for k in ('messages','decision','operation','handoff','resolution')}}
                rr._atomic(service._blob(key,'.assembled.json'),rr._json(payload))
                current.update(status='validating')
            else:current.update(status='queued')
            commit_tasks(service.store,service.store._files(),tasks)
        return finish(service,key) if cost['kind']=='item' else {'task':service._public(current)}
    except (ValueError,OSError):
        with service.store._locked():
            tasks=service._read();current=tasks['jobs'][key]
            if current['status'] in ('preparing','queued','validating'):refund(service,tasks,current,'failed','准备或系统结算未完成，已返还预扣。')
        raise


def held_files(service,job):
    with service.store._locked():
        files=service.store._files()
        if rr._revision(files)!=job['working_revision']:raise rr.ConflictError('预扣后存档被外部修改')
        return files


def retry(service,key,body):
    with service.store._locked():
        tasks=service._read();service._expire(tasks);job=tasks['jobs'].get(key)
        if not job:raise rr.RoundError('任务不存在')
        if job['status'] in ('queued','generating','validating','committed','preparing'):return {'task':service._public(job)}
        if job.get('reservation',{}).get('status')=='held':refund(service,tasks,job,'failed','重试前返还原预扣')
        request={k:job.get(k) for k in ('request_id','base_revision','action','entry_mode','operation','save_epoch','selection','model_key')}
        request['model_key']=service._model_key(body)
    return create(service,request,retry_key=key)


def finish(service,key):
    with service.store._locked():
        job=copy.deepcopy(service._read()['jobs'][key])
    if job['status']!='validating':return {'task':service._public(job)}
    try:
        context=rr.load_request(service._blob(key,'.context.json').read_text())
        payload=rr.load_request(service._blob(key,'.assembled.json').read_text()) if context.get('system_item') else service._assemble_result(key,job)
        baseline=dict(context.get('audit',{}))
        if not context.get('system_item'):
            proof=rr.load_request(service._blob(key,'.read-audit.json').read_text())
            baseline.update({item['path']:item['source_sha256_at_result'] for item in proof['verified_tools'] if 'source_sha256_at_result' in item})
        receipt=service.store.submit(payload,_source_baseline=baseline)
        with service.store._locked():return {'task':service._public(service._read()['jobs'][key])}
    except rr.RoundError as error:
        with service.store._locked():
            tasks=service._read();current=tasks['jobs'][key]
            if current['status']=='validating':refund(service,tasks,current,'conflict' if isinstance(error,rr.ConflictError) else 'failed','结算未通过：'+str(error))
            return {'task':service._public(current)}


def cancel(service,key):
    service.start()
    with service.store._locked():
        tasks=service._read();job=tasks['jobs'].get(key)
        if not job:raise rr.RoundError('任务不存在')
        if job.get('reservation'):
            refund(service,tasks,job,'cancelled','已取消，预扣全额返还。')
        elif job['status']!='committed':
            job.update(status='cancelled',lease=None,error='已取消原请求。');service._write(tasks)
        return {'task':service._public(job)}

"""P12 focused, disposable source/audit/round acceptance; never runs models or live game writes."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import traceback
import types

sys.dont_write_bytecode = True
ROOT=Path.cwd().resolve()
BASE=ROOT/'开发者功能/修订日志/2026.11/回合执行基础'
MANIFEST=json.loads((BASE/'src/安装清单_18.json').read_bytes())
CHANGES={c['path']:c for c in MANIFEST['changes']}
INSTALLED='--installed' in sys.argv
RESULT=BASE/'src/P12隔离验收结果_18.json'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def source(rel):
    return (ROOT/CHANGES[rel]['staged']).read_bytes() if rel in CHANGES and not INSTALLED else (ROOT/rel).read_bytes()


def old_source(rel):
    return (ROOT/CHANGES[rel]['backup']).read_bytes() if rel in CHANGES and INSTALLED else (ROOT/rel).read_bytes()


def module(name, rel):
    mo=types.ModuleType(name);mo.__file__=str(ROOT/rel);sys.modules[name]=mo
    exec(compile(source(rel),mo.__file__,'exec'),mo.__dict__)
    return mo

sr=module('story_reading','story_reading.py')
rq=module('relationship_query','relationship_query.py')
rr=module('round_runtime','round_runtime.py')

def service_class(raw):
    tree=ast.parse(raw)
    tree=ast.Module(body=[n for n in tree.body if isinstance(n,(ast.Assign,ast.ClassDef))],type_ignores=[])
    env={'rr':rr,'rq':rq,'sr':sr,'Path':Path,'json':json,'re':re,'hashlib':hashlib,
         'threading':__import__('threading'),'time':__import__('time'),'secrets':__import__('secrets')}
    exec(compile(tree,'<actual service class>','exec'),env)
    return env['StoryService'],env

Service,ss=service_class(source('story_service.py'))
OldService,oldss=service_class(old_source('story_service.py'))
work=Path(tempfile.mkdtemp(prefix='tmp_p12_accept18_',dir=BASE/'tmp'))
project=work/'new';project.mkdir()
for rel in set(MANIFEST['protected'])|set(CHANGES)|set(ss['RULES'])|{'injection_core.py'}:
    p=project/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source(rel))
fx={'rr':rr}
tree=ast.parse((ROOT/'开发者功能/开发者工具/回合执行验收.py').read_bytes())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='memory'],type_ignores=[]),'<existing fixture>','exec'),fx)
for rel,text in [(rr.FILES[0],fx['memory']()),(rr.FILES[1],'▼ 已过期/已消耗道具历史区 ▼\n'),
                 (rr.FILES[2],'静态NPC名册\n'),('data.json','{"round":0,"storyNodes":[]}')]:
    (project/rel).write_text(text)
oldproject=work/'old';shutil.copytree(project,oldproject)
for rel in CHANGES:
    if CHANGES[rel]['before']:(oldproject/rel).write_bytes(old_source(rel))
service=Service(project)
prepared=service.store.prepare()
key='synthetic-p12';context=service._context(prepared,key,'你把材料递给沈知韫，询问下午安排。')
rr._atomic(service._blob(key,'.context.json'),rr._json(context))
bundle=context['reading_bundle'];specs=sr.specifications(project)
observations=[];measures={}
REVISION_ONLY='--revision-only' in sys.argv
REVISION_CASES={'actual_service_projection_audit_and_coverage','raw_source_complete_compatibility','execute_write_tools_still_rejected','foreign_task_projection_rejected','cache_root_search_rejected','current_task_directory_listing_allowed','old_context_result_rejected','old_queued_context_rejected_before_generation','same_case_chars_calls_fields_and_retry_measurement','protected_sources_and_live_facts_unchanged'}


def require(value,message='assertion failed'):
    if not value:raise AssertionError(message)


def reject(fn,exceptions=(ValueError,OSError)):
    try:fn()
    except exceptions:return
    raise AssertionError('expected rejection')


def case(name,fn):
    if REVISION_ONLY and name not in REVISION_CASES:return
    try:fn();observations.append({'name':name,'status':'PASS'})
    except Exception as exc:observations.append({'name':name,'status':'FAIL','error':str(exc),'traceback':traceback.format_exc()})
    print(observations[-1]['status'],name,flush=True)


def display(raw,begin=1,end=None):
    lines=raw.decode('utf-8').splitlines();end=min(len(lines),end if end is not None else len(lines))
    return f'Part 1 of 1 (Lines {begin}-{end} of {len(lines)})\n\n'+'\n'.join(f'{i}| {lines[i-1]}' for i in range(begin,end+1))


def read_call(path,begin=1,end=None,root=project):
    raw=(root/path).read_bytes();lines=raw.decode('utf-8').splitlines();end=len(lines) if end is None else end
    return {'name':'read_file_part','parameters':{'path':path,'start_line':begin,'end_line':end},
            'status':'success','result_text':display(raw,begin,end),'part_id':'synthetic-part-'+str(begin)}


def proof_for(ctx,root=project,raw_sources=False):
    tools=[]
    for required in ctx['reading_policy']['required_reads']:
        if raw_sources and required.get('source_alternative'):
            tools.append(read_call(required['source_alternative']['path'],root=root))
        else:tools.append(read_call(required['path'],root=root))
    for directory in ctx['reading_policy']['required_browse']:
        tools.append({'name':'list_files','parameters':{'path':directory},'status':'success','result_text':'synthetic directory list'})
    for k in ctx['reading_policy'].get('required_keys',[]):
        if raw_sources:
            rel=ctx['reading_bundle']['entries'][k]['sources'][0]['path']
            if any(c['parameters']['path']==rel for c in tools):continue
        else:rel=ctx['reading_bundle']['entries'][k]['path']
        tools.append(read_call(rel,root=root))
    rel=ctx['reading_bundle']['entries']['char.沈知韫']['path']
    if not raw_sources:tools.append(read_call(rel,root=root))
    return {'api':'Tools.Chat.sendMessageStreaming','chat_id':'synthetic-p12','participant_id':'synthetic-reader',
            'workspace':str(root),'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':18}},
            'snapshot_message_timestamp':18,'tools':tools}


def facts_for(proof=None,ctx=context,svc=service):
    proof=proof or proof_for(ctx)
    return svc._bridge_facts(ctx,svc._verify_audit(key,proof))


def semantic(facts):
    keys=sorted(set(facts['enforced_keys'])|{'state.memory','contract.inject','gate.V1','char.沈知韫'})
    story=[{'type':'header','text':'[居家] 7月21日, 周二, 徐家主宅, 19:48'},
           {'type':'narration','text':'你把材料递到桌边，纸页轻轻擦过指腹。'},
           {'type':'dialogue','speaker':'沈知韫','text':'放这里，我等会儿看。'}]
    memory=('你在徐家主宅把整理好的材料递给沈知韫，纸页从指腹擦过后落在桌边。她接过材料，说明稍后再看。'
            '两人仍在原处，你没有替她决定接下来的安排，也没有离开当前场景。桌面上的材料保持原样，'
            '没有新人物进入，没有道具变更，也未发生需要结算的数值事件。当前交流停在她接收材料后的短暂间隙，'
            '后续行动由你的下一条指令决定。')
    return {'story_nodes':story,'memory_deltas':{'l1_new_round':memory,'presence':{},
            'round_conditions':{'intensity':'A','effective_progress':True,'scene':'徐家主宅','npc':'沈知韫',
                                'action_changed':True,'stress_signals':0,'breakout_triggered':[]}},
            'options_text':'[A. 日常互动]：询问晚饭安排。\n[B. 社交接触]：把杯子递过去。\n[C. 主动行为]：主动提出帮忙整理材料。',
            'model_audit':{'intent':'递交材料并询问下午安排','scene':'徐家主宅|徐志北,沈知韫','required_keys':['char.沈知韫'],
            'evidence':{k:'材料交接按本轮原文规定保留意图、人物边界与当前所在。' for k in keys},
            'v1':{k:{'status':'通过','reason':'合成材料交接只保留原意，场景和可见动作与当前事实一致。'} for k in ['V1-A','V1-B','V1-C','V1-D']},
            'task':'当前任务为空，本轮不发布新任务。','breakout':'交接材料产生实际进展，无停滞或应激信号。'}}


def altered(name,rel,fn):
    dest=work/name;shutil.copytree(project,dest)
    path=dest/rel;path.write_bytes(fn(path.read_bytes()))
    return dest


def test_structure():
    for c in CHANGES.values():
        raw=source(c['path'])
        if c['path'].endswith('.py'):compile(raw,c['path'],'exec')
        if c['path'].endswith('.json'):json.loads(raw)
    require(len(bundle['entries'])==30)
    kb={k:v for k,v in specs.items() if v['completeness']=='complete_entry'}
    require(len(kb)==22)
    for k,v in kb.items():
        source_ref=v['sources'][0];e=json.loads((project/source_ref['path']).read_bytes())['data']['entries'][source_ref['entry']]
        require(v['body']==e['content'],k)
    measures['kb_entries_exact']=len(kb)
case('python_json_and_22_exact_entries',test_structure)


def test_guides():
    for key in ['contract.inject','rule.prompt']:
        spec=specs[key];raw=(project/spec['sources'][0]['path']).read_text().splitlines()
        expected='\n'.join(x for a,b in spec['sources'][0]['ranges'] for x in raw[a-1:b])
        require(spec['body']==expected)
    guide=specs['contract.inject']['body']
    for text in ["MEMORY","round_conditions","micro_state_changes",str(120),str(280),"presence","旁白声学标签契约"]:
        require(text in guide,text)
    require('【手动Python入口开始】' not in guide and '【注册表生成表开始】' not in guide)
    require('【SYSTEM_LOG】\nROUND:' not in specs['rule.prompt']['body'])
    require('SYSTEM_LOG硬规则' in specs['rule.prompt']['body'])
case('bridge_guide_prompt_exact_selected_ranges',test_guides)

case('event_tables_six_exact_source_views',lambda:require(all(specs['contract.events.'+f]['body'] in (project/sr.GUIDE).read_text() for f in sr.EVENT_FIELDS)))
case('bundle_nonce_and_source_verified',lambda:require(sr.verify_bundle(project,bundle)==specs))
case('all_seven_always_required_kept',lambda:require(len(context['reading_policy']['required_keys'])==7))
case('metadata_only_is_not_complete',lambda:require(sr.projection_facts(project,bundle,[{'name':'read_file_part','path':bundle['entries']['char.沈知韫']['path'],'status':'success','verified_lines':[1]}])=={}))


def test_missing_key():
    dest=altered('missing',sr.KB[0],lambda raw:json.dumps(dict(json.loads(raw),data={'entries':[]}),ensure_ascii=False).encode())
    reject(lambda:sr.specifications(dest))
case('missing_library_entries_rejected',test_missing_key)


def test_duplicate():
    def edit(raw):
        obj=json.loads(raw);obj['data']['entries'].append(copy.deepcopy(obj['data']['entries'][0]));return json.dumps(obj,ensure_ascii=False).encode()
    reject(lambda:sr.specifications(altered('duplicate',sr.KB[0],edit)))
case('duplicate_key_rejected',test_duplicate)


def test_empty():
    def edit(raw):
        obj=json.loads(raw);obj['data']['entries'][0]['content']='';return json.dumps(obj,ensure_ascii=False).encode()
    reject(lambda:sr.specifications(altered('empty',sr.KB[0],edit)))
case('empty_content_rejected',test_empty)

case('stale_source_rejected',lambda:reject(lambda:sr.verify_bundle(altered('stale',sr.KB[0],lambda raw:raw+b'\n'),bundle)))
case('cache_tamper_rejected',lambda:reject(lambda:sr.verify_bundle(altered('tamper',bundle['entries']['char.沈知韫']['path'],lambda raw:raw+b'bad'),bundle)))
case('missing_bundle_key_rejected',lambda:reject(lambda:sr.verify_bundle(project,dict(bundle,entries={k:v for k,v in bundle['entries'].items() if k!='char.沈知韫'}))))
case('bad_cache_path_rejected',lambda:reject(lambda:sr._path(project,'../outside')))


def test_result_lines():
    raw='甲\n乙\n丙\n'.encode();text=display(raw)
    require(sr.verified_lines(raw,text)==[1,2,3])
    reject(lambda:sr.verified_lines(raw,text.replace('乙','错')))
    require(sr.verified_lines(raw,display(raw,1,1)+chr(10)+"file content truncated",1,3)==[1])
    reject(lambda:sr.verified_lines(raw,'success source_sha256=claimed',1,3))
case('actual_numbered_receipts_and_truncation',test_result_lines)
case('raw_adapter_receipt_exact',lambda:require(sr.verified_lines('甲\n乙\n'.encode(),'甲\n乙\n')==[1,2]))


def test_valid_audit():
    facts=facts_for()
    require('char.沈知韫' in facts['available_keys'])
    require('char.苏婉青' not in facts['available_keys'])
    require(facts['available_keys']['char.沈知韫']['scope']=='complete_entry')
    measures['new_available_keys']=sorted(facts['available_keys'])
case('actual_service_projection_audit_and_coverage',test_valid_audit)
case('raw_source_complete_compatibility',lambda:require('char.沈知韫' in facts_for(proof_for(context,raw_sources=True))['available_keys']))


def test_short_read():
    obj=proof_for(context);obj['tools'][0]['result_text']=obj['tools'][0]['result_text'].splitlines()[0]+'\n\n1| '+(project/rr.FILES[0]).read_text().splitlines()[0]
    reject(lambda:service._verify_audit(key,obj))
case('claimed_full_range_but_missing_body_rejected',test_short_read)


def test_bad_text():
    obj=proof_for(context);obj['tools'][1]['result_text']=obj['tools'][1]['result_text'].replace('【使用说明','【假说明',1)
    reject(lambda:service._verify_audit(key,obj))
case('modified_body_receipt_rejected',test_bad_text)


def test_order():
    obj=proof_for(context);obj['tools'][0],obj['tools'][1]=obj['tools'][1],obj['tools'][0]
    reject(lambda:service._verify_audit(key,obj))
case('first_three_order_rejected',test_order)


def test_interleave():
    obj=proof_for(context);first=obj['tools'][0];obj['tools'][0]=read_call(rr.FILES[0],1,1)
    obj['tools'].insert(2,read_call(rr.FILES[0],2))
    reject(lambda:service._verify_audit(key,obj))
case('incomplete_memory_before_guide_rejected',test_interleave)


def test_browse():
    obj=proof_for(context);obj['tools']=[c for c in obj['tools'] if c['name']!='list_files']
    reject(lambda:service._verify_audit(key,obj))
case('required_directory_browse_still_enforced',test_browse)


def test_tool():
    obj=proof_for(context);obj['tools'].append({'name':'terminal','parameters':{'path':'.'},'status':'success','result_text':''})
    reject(lambda:service._verify_audit(key,obj))
case('execute_write_tools_still_rejected',test_tool)


def test_old_task():
    other=sr.build_bundle(project,'other-task')
    obj=proof_for(context);obj['tools'][-1]=read_call(other['entries']['char.沈知韫']['path'])
    reject(lambda:service._verify_audit(key,obj))
case('foreign_task_projection_rejected',test_old_task)


def test_cache_root():
    obj=proof_for(context);obj['tools'].append({'name':'grep_code','parameters':{'path':sr.CACHE},'status':'success','result_text':'cache content'})
    reject(lambda:service._verify_audit(key,obj))
case('cache_root_search_rejected',test_cache_root)


def test_current_directory():
    obj=proof_for(context);obj['tools'].append({'name':'list_files','parameters':{'path':sr.CACHE+'/'+bundle['nonce']},'status':'success','result_text':'current directory'})
    require(service._verify_audit(key,obj)['required_reads_verified'])
case('current_task_directory_listing_allowed',test_current_directory)


def test_old_result():
    dest=work/'old-result';shutil.copytree(project,dest);svc=Service(dest)
    oldctx=copy.deepcopy(context);oldctx['reading_policy'].pop('version')
    rr._atomic(svc._blob('old-result','.context.json'),rr._json(oldctx))
    rr._atomic(svc._blob('old-result','.result.txt'),rr._json({}))
    reject(lambda:svc._assemble_result('old-result',{'request_id':'old-result'}))
case('old_context_result_rejected',test_old_result)


def test_old_queued():
    dest=work/'old-queue';shutil.copytree(project,dest);svc=Service(dest)
    job=svc.create({'request_id':'old-queued','base_revision':prepared['base_revision'],'action':'递交材料'})['task']
    oldctx=json.loads(svc._blob('old-queued','.context.json').read_bytes());oldctx['reading_policy'].pop('version')
    rr._atomic(svc._blob('old-queued','.context.json'),rr._json(oldctx))
    require(svc.claim()['task'] is None)
    state=svc._read();require(state['jobs']['old-queued']['status']=='failed')
case('old_queued_context_rejected_before_generation',test_old_queued)



def test_required_character():
    obj=proof_for(context);path=bundle['entries']['sys.task']['path'];obj['tools']=[c for c in obj['tools'] if c['parameters']['path']!=path]
    reject(lambda:facts_for(obj))
case('missing_always_key_rejected',test_required_character)


def test_dialogue_character():
    obj=proof_for(context);path=bundle['entries']['char.沈知韫']['path'];obj['tools']=[c for c in obj['tools'] if c['parameters']['path']!=path]
    facts=facts_for(obj);value=semantic(facts)
    reject(lambda:rr._assemble_bridge_result(project,value,{'schema_version':1,'request_id':key,'base_revision':prepared['base_revision'],'current_round':prepared['current_round']},facts))
case('speaker_without_character_read_rejected',test_dialogue_character)


def test_context_size():
    envelope=json.loads(context['turns'][1]['content'])
    require('source_baseline' not in envelope and 'memory_layers' not in envelope)
    require('fixed_fields' not in envelope['output_contract'] and 'optional_defaults' not in envelope['output_contract'])
    require(ss['READONLY_TOOLS']==oldss['READONLY_TOOLS'])
case('context_duplicate_facts_removed_no_permission_expansion',test_context_size)


def test_projection_missing_header():
    obj=proof_for(context);path=bundle['entries']['char.沈知韫']['path'];obj['tools'][-1]=read_call(path,2)
    facts=facts_for(obj)
    require('char.沈知韫' not in facts['available_keys'])
case('body_without_source_header_not_counted',test_projection_missing_header)


def test_round():
    facts=facts_for();value=semantic(facts)
    identity={'schema_version':1,'request_id':key,'base_revision':prepared['base_revision'],'current_round':prepared['current_round']}
    request=rr._assemble_bridge_result(project,value,identity,facts)
    receipt=service.store.submit(request);require(receipt['status']=='committed')
    replay=service.store.submit(request);require(replay['replayed'] is True)
    measures['isolated_round']={'status':receipt['status'],'round':receipt['round'],'replay':replay['replayed']}
case('same_semantic_task_real_round_commit_and_idempotency',test_round)


def test_comparison():
    # The same retrieval needs: all seven active keys, Shen/host and a non-triggering ordinary exchange.
    oldservice=OldService(oldproject);oldprepared=oldservice.store.prepare()
    oldcontext=oldservice._context(oldprepared,'synthetic-baseline','你把材料递给沈知韫，询问下午安排。')
    old_paths=[r['path'] for r in oldcontext['reading_policy']['required_reads']]+list(sr.KB)
    old_bodies=[]
    for rel in old_paths:
        txt=(oldproject/rel).read_text()
        if rel==sr.GUIDE:txt=txt.split('【手动Python入口开始】',1)[0]
        old_bodies.append(txt)
    newproof=proof_for(context)
    newpaths=[c['parameters']['path'] for c in newproof['tools'] if c['name'] in ss['READ_TOOLS']]
    # Round test has advanced the isolated project; compare the generated task's original read bodies for data/memory.
    new_bodies=[]
    for rel in newpaths:
        if rel in rr.FILES:new_bodies.append((oldproject/rel).read_text())
        else:new_bodies.append((project/rel).read_text())
    oldchars=sum(len(t) for t in old_bodies);newchars=sum(len(t) for t in new_bodies)
    oldenv=sum(len(t['content']) for t in oldcontext['turns']);newenv=sum(len(t['content']) for t in context['turns'])
    require(newchars+newenv<oldchars+oldenv,'no net character saving')
    measures['comparison']={'unit':'Unicode characters, not tokens','same_case':'ordinary two-person material handoff',
        'before':{'read_body_chars':oldchars,'envelope_chars':oldenv,'total_chars':oldchars+oldenv,'content_read_calls':len(old_paths)},
        'after':{'read_body_chars':newchars,'envelope_chars':newenv,'total_chars':newchars+newenv,'content_read_calls':len(newpaths)},
        'model_required_top_fields_before':4,'model_required_top_fields_after':4,
        'synthetic_contract_validation_retries':0,'real_model_retry_rate':None,'creative_quality':None,
        'counting':'one complete-content call per file; directory listing calls=3 in both; tool display wrappers excluded; baseline reads four raw libraries to obtain the same required keys'}
case('same_case_chars_calls_fields_and_retry_measurement',test_comparison)


def test_live():
    for rel,info in MANIFEST['protected'].items():require(sha((ROOT/rel).read_bytes())==info['sha256'],rel)
    for c in CHANGES.values():
        info=c['after'] if INSTALLED else c['before']
        require(sha((ROOT/c['path']).read_bytes())==info['sha256'] if info else not (ROOT/c['path']).exists(),c['path'])
    require(not (ROOT/sr.CACHE).exists(),'live cache created during isolated acceptance')
case('protected_sources_and_live_facts_unchanged',test_live)

summary={'stage':'P12','cases':len(observations),'passed':sum(x['status']=='PASS' for x in observations),'failed':sum(x['status']=='FAIL' for x in observations),
         'tests':observations,'measurements':measures,'model_called':False,'flask_http_executed':False,
         'actual_service_class_executed':True,'live_game_facts_unchanged':observations[-1]['status']=='PASS'}
if REVISION_ONLY:
    initial=json.loads(RESULT.read_bytes())
    initial['initial_acceptance']={k:v for k,v in initial.items() if k!='tests'}
    initial['targeted_revision']=summary
    records={x['name']:x for x in initial['tests']};records.update({x['name']:x for x in observations})
    initial['tests']=list(records.values());initial['cases']=len(records)
    initial['passed']=sum(x['status']=='PASS' for x in records.values());initial['failed']=sum(x['status']=='FAIL' for x in records.values())
    initial['measurements'].update(measures);summary=initial
RESULT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print('P12_ISOLATION_'+('PASS' if not summary['failed'] else 'FAIL'),json.dumps({k:v for k,v in summary.items() if k!='tests'},ensure_ascii=False),flush=True)
shutil.rmtree(work)
raise SystemExit(1 if summary['failed'] else 0)

"""P11 focused acceptance on disposable projects; no Flask/model/network/live writes."""
from pathlib import Path
import ast
import copy
import hashlib
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
import types

sys.dont_write_bytecode = True
ROOT = Path.cwd().resolve()
BASE = ROOT/'开发者功能/修订日志/2026.11/回合执行基础'
MANIFEST = json.loads((BASE/'src/安装清单_17.json').read_bytes())
CHANGES = {c['path']:c for c in MANIFEST['changes']}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
INSTALLED = '--installed' in sys.argv

def source(rel):
    return (ROOT/CHANGES[rel]['staged']).read_bytes() if rel in CHANGES and not INSTALLED else (ROOT/rel).read_bytes()


def module(name, rel):
    result = types.ModuleType(name)
    result.__file__ = str(ROOT/rel)
    exec(compile(source(rel), result.__file__, 'exec'), result.__dict__)
    sys.modules[name] = result
    return result

rq = module('relationship_query', 'relationship_query.py')
rr = module('round_runtime', 'round_runtime.py')
# Exercise the actual service class/constants, omitting only unavailable Flask route imports.
tree = ast.parse(source('story_service.py'))
class_tree = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.Assign, ast.ClassDef))], type_ignores=[])
ss = {'rr':rr, 'rq':rq, 'Path':Path, 'hashlib':hashlib, 'json':json, 're':__import__('re'),
      'threading':__import__('threading'), 'time':__import__('time'), 'secrets':__import__('secrets')}
exec(compile(class_tree, '<actual story service class>', 'exec'), ss)
Service = ss['StoryService']
work = Path(tempfile.mkdtemp(prefix='tmp_p11_accept17_', dir=BASE/'tmp'))
project = work/'base';project.mkdir()
for rel in set(CHANGES) | set(rr.FILES) | set(ss['RULES']) | {'injection_core.py','round_runtime.py'}:
    if rel in rr.FILES:continue
    dest=project/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source(rel))
fixture_tree=ast.parse((ROOT/'开发者功能/开发者工具/回合执行验收.py').read_bytes())
fx={'rr':rr}
exec(compile(ast.Module(body=[n for n in fixture_tree.body if isinstance(n,ast.FunctionDef) and n.name=='memory'],type_ignores=[]),'<existing memory fixture>','exec'),fx)
for rel,text in [(rr.FILES[0],fx['memory']()),(rr.FILES[1],'▼ 已过期/已消耗道具历史区 ▼\n'),
                 (rr.FILES[2],'静态NPC名册\n'),('data.json','{"round":0,"storyNodes":[]}')]:
    dest=project/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
reg=rq.RelationshipRegistry(project)
rows=reg.verify_view()
service=Service(project)
observations=[]
counts={'direction_queries':0,'group_queries':0,'source_pointers':0}

def require(condition, message='assertion failed'):
    if not condition:raise AssertionError(message)


REVISION_CASES = {'syntax_json_and_fact_layers','source_authority_and_narrative_discipline','all_query_provenance_json_pointers','context_contract_fingerprints_without_table','real_service_audit_and_partial_fact_assembly','public_parent_identity_without_listener','sole_heir_knowledge_authorized','heir_secret_absent_from_other_perspectives','unknown_listener_neutral','stale_source_view_rejected','query_source_change_conflicts_with_task','all_live_sources_and_game_facts_untouched'}
REVISION_ONLY = '--revision-only' in sys.argv
def case(name, fn):
    if REVISION_ONLY and name not in REVISION_CASES:return
    try:
        fn();observations.append({'name':name,'status':'PASS'})
    except Exception as exc:
        observations.append({'name':name,'status':'FAIL','error':str(exc),'traceback':traceback.format_exc()})
    print(observations[-1]['status'], name)


def rejected(fn, error):
    try:fn()
    except error:return
    raise AssertionError('expected rejection '+error.__name__)


def terms(result):return {f['text'] for f in result['self_candidates']}

def addresses(result):return {f['text'] for f in result['targets'][0]['address_candidates']}

def isolated_change(key, mutate):
    dest=work/key;shutil.copytree(project,dest)
    p=dest/rq.SOURCE;obj=json.loads(p.read_bytes());mutate(obj);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    return dest


def record(line, name='read_file_part', status='success'):
    return {'name':name,'path':rq.VIEW,'status':status,'start_line':line,'end_line':line}


def row_line(key):return next(i for i,row in enumerate(rows,1) if row.get('key')==key)


def proof(context):
    calls=[]
    for req in context['reading_policy']['required_reads']:
        calls.append({'name':'read_file_part','parameters':{'path':req['path'],'start_line':1,'end_line':req['through_line']},
                      'status':'success','result_text':(project/req['path']).read_text(),'part_id':str(len(calls))})
    for directory in ss['REQUIRED_BROWSE']:
        calls.append({'name':'list_files','parameters':{'path':directory},'status':'success','result_text':'synthetic directory listing','part_id':str(len(calls))})
    return {'api':'Tools.Chat.sendMessageStreaming','outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':17}},
            'snapshot_message_timestamp':17,'chat_id':'synthetic-p11','participant_id':'synthetic-reader','workspace':str(project),'tools':calls}


def test_formats():
    for rel in CHANGES:
        raw=source(rel)
        if rel.endswith('.py'):compile(raw,rel,'exec')
        if rel.endswith('.json'):json.loads(raw)
        require(raw.decode('utf-8').startswith(('import','"""','#','{','[','=')) or rel.endswith('.txt'))
    require(reg.data['facts']['R01']['type']=='mother_son')
    require(reg.data['facts']['R04']['type']=='adoptive_mother_son')
    require(len(reg.data['facts'])==13 and len(rows)==42)
case('syntax_json_and_fact_layers',test_formats)


def test_metadata():
    total=[]
    for name in ['角色类','世界观类','叙事判断']:
        rel='txt文件/知识库/'+name+'.json';old=json.loads((ROOT/(CHANGES[rel]['backup'] if INSTALLED else rel)).read_bytes());new=json.loads(source(rel))
        a=copy.deepcopy(old);b=copy.deepcopy(new)
        for obj in [a,b]:
            for e in obj['data']['entries']:e.pop('content')
        require(a==b,rel+' metadata changed');total.extend(new['data']['entries'])
    export=json.loads(source('Operit世界书导出/operit_worldbook_深渊天平.json'))
    require(len(export)==22 and sum(e['always_active'] for e in export)==7)
    require(len({e['name'] for e in export})==22)
    all_entries=[]
    for name in ['世界观类','叙事判断','角色类','系统标签类']:
        all_entries+=json.loads(source('txt文件/知识库/'+name+'.json'))['data']['entries']
    for a,b in zip(all_entries,export):require(a['content']==b['content'] and a['keywords']==b['keywords'])
case('metadata_and_generated_export_22_7',test_metadata)


def test_authority():
    chars=json.loads(source('txt文件/知识库/角色类.json'))['data']['entries']
    require(all('【亲属关系·身份死线】见 lore.称谓' in e['content'] for e in chars))
    lore=json.loads(source('txt文件/知识库/世界观类.json'))['data']['entries'][0]['content']
    require('【家族谱系' not in lore and '【认知锁死' not in lore)
    require('唯一合法继承人为宿主' not in lore)
    require('「我是嫂子」' not in '\n'.join(e['content'] for e in chars))
    require('绝对禁止NPC主动「坦白」' in lore)
case('source_authority_and_narrative_discipline',test_authority)

case('daughter_in_law_to_mother_in_law',lambda:require({'儿媳','婉青','我',''}<=terms(reg.query('苏婉青',['沈知韫'],'formal')) and '嫂子' not in terms(reg.query('苏婉青',['沈知韫'],'formal'))))
case('daughter_in_law_relaxed_choice',lambda:require('儿媳' not in terms(reg.query('苏婉青',['沈知韫'],'relaxed')) and '婉青' in terms(reg.query('苏婉青',['沈知韫'],'relaxed'))))
case('sister_in_law_to_younger_brother',lambda:require('嫂子' in terms(reg.query('苏婉青',['徐志北'],'relaxed'))))
case('sister_in_law_to_younger_sister',lambda:require('嫂子' in terms(reg.query('苏婉青',['徐念薇'],'formal'))))
case('wife_to_husband_neutral',lambda:require(terms(reg.query('苏婉青',['徐承邺'],'relaxed'))=={'我','婉青',''}))
case('title_to_minor_npc',lambda:require('少奶奶' in terms(reg.query('苏婉青',['次要NPC'],'formal'))))
case('mother_caring_self_reference',lambda:require(all('妈妈' in terms(reg.query('沈知韫',[n],'relaxed')) for n in ['徐志北','徐承邺','徐念薇'])))
case('business_self_reference',lambda:require(terms(reg.query('沈知韫',['徐志北'],'business'))=={'我','知韫',''}))
case('mother_address_from_child',lambda:require({'妈','妈妈'}<=addresses(reg.query('徐志北',['沈知韫'],'relaxed'))))
case('group_mixed_generations_intersection',lambda:require(terms(reg.query('苏婉青',['沈知韫','徐志北'],'formal'))=={'我','婉青',''}))
case('group_same_role_intersection',lambda:require('嫂子' in terms(reg.query('苏婉青',['徐志北','徐念薇'],'relaxed'))))
case('unknown_listener_neutral',lambda:require(terms(reg.query('苏婉青',[],'relaxed'))=={'我','婉青',''}))


def test_directions():
    actors=['沈知韫','苏婉青','徐念薇','徐承邺','徐志北']
    for a,b in itertools.permutations(actors,2):
        for occasion in rq.OCCASIONS:
            x=reg.query(a,[b],occasion);y=reg.query(b,[a],occasion)
            require(x['targets'][0]['relations'][0]['speaker_role']==y['targets'][0]['relations'][0]['listener_role'])
            require({f['id'] for f in x['facts']}=={f['id'] for f in y['facts']})
            require('' in terms(x) and x['selection']['optional'] is True)
            require('K01' not in json.dumps(x,ensure_ascii=False))
            counts['direction_queries']+=1
    for a in actors:
        others=[b for b in actors if b!=a]
        for pair in itertools.combinations(others,2):
            actual=terms(reg.query(a,list(pair),'relaxed'))
            expected=set.intersection(*(terms(reg.query(a,[b],'relaxed')) for b in pair))
            require(actual==expected);counts['group_queries']+=1
case('all_60_directions_and_30_group_intersections',test_directions)

case('public_parent_identity_without_listener',lambda:require('R02' in {f['id'] for f in reg.query('徐志北',[],'formal')['facts']} and 'K01' not in json.dumps(reg.query('徐志北',[],'formal'),ensure_ascii=False)))
case('sole_heir_knowledge_authorized',lambda:require([f['id'] for f in reg.knowledge('沈知韫')['facts']]==['K01']))
case('heir_secret_absent_from_other_perspectives',lambda:require(all(not reg.knowledge(n)['facts'] and 'K01' not in json.dumps(reg.knowledge(n),ensure_ascii=False) and '唯一合法继承人' not in json.dumps(reg.knowledge(n),ensure_ascii=False) for n in ['徐志北','徐承邺','苏婉青','徐念薇'])))
case('belief_is_not_legal_fact',lambda:require(reg.knowledge('徐承邺')['beliefs'][0]['status']=='belief_not_fact' and reg.knowledge('徐承邺')['facts']==[]))
case('unknown_speaker_rejected',lambda:rejected(lambda:reg.query('未知',['沈知韫'],'formal'),rq.RelationshipError))
case('unknown_listener_rejected',lambda:rejected(lambda:reg.query('苏婉青',['未知'],'formal'),rq.RelationshipError))
case('unknown_perspective_rejected',lambda:rejected(lambda:reg.knowledge('未知'),rq.RelationshipError))
case('duplicate_listener_rejected',lambda:rejected(lambda:reg.query('苏婉青',['徐志北','徐志北'],'formal'),rq.RelationshipError))
case('invalid_occasion_rejected',lambda:rejected(lambda:reg.query('苏婉青',[],'fictional'),rq.RelationshipError))
case('deceased_speaker_rejected',lambda:rejected(lambda:reg.query('徐家亡父',[],'formal'),rq.RelationshipError))
case('self_listener_rejected',lambda:rejected(lambda:reg.query('苏婉青',['苏婉青'],'formal'),rq.RelationshipError))
case('caller_cannot_grant_unlocks',lambda:rejected(lambda:reg.query('苏婉青',[],'formal',known_by=['K01']),TypeError))


def test_pointers():
    def resolve(pointer):
        require(pointer.startswith('#/'))
        value=reg.data
        for token in pointer[2:].split('/'):
            value=value[int(token)] if isinstance(value,list) else value[token]
        counts['source_pointers']+=1
    for row in rows[1:]:
        values=row.get('occasions',{}).values() if 'occasions' in row else [row]
        for result in values:
            require(result['source']['sha256']==sha((project/rq.SOURCE).read_bytes()))
            for f in result.get('facts',[]):resolve(f['source'])
            for f in result.get('beliefs',[]):resolve(f['source'])
            forms=result.get('self_candidates',[])+[f for t in result.get('targets',[]) for f in t['address_candidates']]
            for f in forms:
                for pointer in f['sources']:resolve(pointer)
case('all_query_provenance_json_pointers',test_pointers)

case('duplicate_reverse_fact_rejected',lambda:rejected(lambda:rq.RelationshipRegistry(isolated_change('duplicate',lambda d:d['facts'].update({'R99':dict(d['facts']['R01'],subject='徐志北',object='沈知韫')}))),rq.RelationshipError))
case('invalid_known_by_rejected',lambda:rejected(lambda:rq.RelationshipRegistry(isolated_change('known',lambda d:d['facts']['K01'].update(known_by=['未知']))),rq.RelationshipError))
case('invalid_schema_rejected',lambda:rejected(lambda:rq.RelationshipRegistry(isolated_change('schema',lambda d:d.update(roles={'bad':{}}))),rq.RelationshipError))
case('stale_source_view_rejected',lambda:rejected(lambda:rq.RelationshipRegistry(isolated_change('stale',lambda d:d['entities']['沈知韫'].update(short='另名'))).verify_view(),rq.RelationshipError))


def test_view_tamper():
    dest=work/'view';shutil.copytree(project,dest);p=dest/rq.VIEW;p.write_bytes(p.read_bytes()+b'\n')
    rejected(lambda:rq.RelationshipRegistry(dest).verify_view(),rq.RelationshipError)
case('tampered_view_rejected',test_view_tamper)


def test_partial_rows():
    key='lore.称谓.苏婉青.沈知韫';line=row_line(key)
    result=service._relationship_facts([record(1),record(line)])
    require(set(result)=={key,'lore.称谓'})
    require(result[key]['covered_lines']==[1,line] and 'through_line' not in result[key])
    require(result['lore.称谓']['scope']=='query_rows')
case('bridge_directional_row_coverage',test_partial_rows)
case('bridge_missing_header_rejected',lambda:rejected(lambda:service._relationship_facts([record(2)]),rr.RoundError))
case('grep_does_not_count_as_read',lambda:require(service._relationship_facts([record(1,'grep_code'),record(2,'grep_code')])=={}))
case('failed_read_does_not_count',lambda:require(service._relationship_facts([record(1,status='error'),record(2,status='error')])=={}))
case('header_only_not_a_fact',lambda:require(service._relationship_facts([record(1)])=={}))

context=None
key='synthetic-p11'

def test_context():
    global context
    prepared=service.store.prepare();context=service._context(prepared,key,'询问是否留饭')
    contract=json.loads(context['turns'][1]['content'])['output_contract']['relationship_registry']
    require(contract['sha256']==reg.source['sha256'])
    require('facts' not in contract and 'entities' not in contract)
    require('唯一合法继承人' not in json.dumps(contract,ensure_ascii=False))
    require(context['reading_policy']['first_read_order']==list(ss['REQUIRED_READS'][:3]))
    require(ss['READONLY_TOOLS']=={'read_file','read_file_full','read_file_part','list_files','find_files','grep_code','file_info','file_exists'})
    rr._atomic(service._blob(key,'.context.json'),rr._json(context))
case('context_contract_fingerprints_without_table',test_context)


def test_audit_partial():
    obj=proof(context);line=row_line('lore.称谓.苏婉青.沈知韫')
    for n in [1,line]:obj['tools'].append({'name':'read_file_part','parameters':{'path':rq.VIEW,'start_line':n,'end_line':n},'status':'success','result_text':(project/rq.VIEW).read_text().splitlines()[n-1]})
    audited=service._verify_audit(key,obj)
    facts=service._bridge_facts(context,audited)
    require('lore.称谓.苏婉青.沈知韫' in facts['available_keys'])
    require('lore.称谓.徐承邺.徐志北' not in facts['available_keys'])
    require(facts['source_fingerprints'][rq.SOURCE]==reg.source['sha256'])
case('real_service_audit_and_partial_fact_assembly',test_audit_partial)


def test_audit_bad_tool():
    obj=proof(context);obj['tools'].append({'name':'terminal','parameters':{'path':'.'},'status':'success','result_text':''})
    rejected(lambda:service._verify_audit(key,obj),rr.RoundError)
case('audit_write_execute_tools_still_rejected',test_audit_bad_tool)


def test_audit_truncated():
    obj=proof(context);obj['tools'].append({'name':'read_file_part','parameters':{'path':rq.VIEW,'start_line':1,'end_line':2},'status':'success','result_text':'file content truncated'})
    rejected(lambda:service._verify_audit(key,obj),rr.RoundError)
case('truncated_query_read_rejected',test_audit_truncated)


def test_audit_missing_read():
    obj=proof(context);obj['tools'][0]['parameters']['end_line']=1
    rejected(lambda:service._verify_audit(key,obj),rr.RoundError)
case('original_required_full_coverage_unchanged',test_audit_missing_read)


def test_source_conflict():
    dest=work/'conflict';shutil.copytree(project,dest);path=dest/rq.SOURCE;path.write_bytes(path.read_bytes()+b'\n')
    rejected(lambda:Service(dest)._source_check(context),rr.ConflictError)
case('query_source_change_conflicts_with_task',test_source_conflict)


def test_cli():
    proc=subprocess.run([sys.executable,str(project/'relationship_query.py'),'--root',str(project),'query','--speaker','苏婉青','--listener','沈知韫','--occasion','formal'],capture_output=True,text=True)
    require(proc.returncode==0 and '嫂子' not in terms(json.loads(proc.stdout)['result']))
    proc=subprocess.run([sys.executable,str(project/'relationship_query.py'),'--root',str(project),'knowledge','--perspective','徐志北'],capture_output=True,text=True)
    require(proc.returncode==0 and json.loads(proc.stdout)['result']['facts']==[])
case('cli_real_query_and_knowledge',test_cli)


def test_live_protection():
    for rel,info in MANIFEST['protected'].items():require(sha((ROOT/rel).read_bytes())==info['sha256'],rel)
    for c in CHANGES.values():
        expected=c['after'] if INSTALLED else c['before']
        require(sha((ROOT/c['path']).read_bytes())==expected['sha256'] if expected else not (ROOT/c['path']).exists(),c['path'])
case('all_live_sources_and_game_facts_untouched',test_live_protection)

summary={'stage':'P11','cases':len(observations),'passed':sum(x['status']=='PASS' for x in observations),
         'failed':sum(x['status']=='FAIL' for x in observations),'counts':counts,'tests':observations,
         'flask_routes_executed':False,'actual_service_class_executed':True,'model_called':False,
         'live_game_facts_unchanged':observations[-1]['status']=='PASS'}
result_path=BASE/'src/P11隔离验收结果_17.json'
if REVISION_ONLY:
    initial=json.loads(result_path.read_bytes())
    initial['initial_acceptance']={k:v for k,v in initial.items() if k!='tests'}
    initial['targeted_revision']=summary
    index={x['name']:x for x in initial['tests']}
    index.update({x['name']:x for x in observations})
    initial['tests']=list(index.values());initial['cases']=len(index)
    initial['passed']=sum(x['status']=='PASS' for x in index.values());initial['failed']=sum(x['status']=='FAIL' for x in index.values())
    summary=initial
result_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print('P11_ISOLATION_'+('PASS' if not summary['failed'] else 'FAIL'),json.dumps({k:v for k,v in summary.items() if k!='tests'},ensure_ascii=False))
shutil.rmtree(work)
raise SystemExit(1 if summary['failed'] else 0)

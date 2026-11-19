"""Focused replay of a real missing-key failure. Disposable roots only; no model calls.
Run from project root with --installed after installation. Needs Python and Node, not Flask.
Actual service class and route registration execute with small HTTP adapters for routing tests.
"""
from pathlib import Path
import ast, copy, hashlib, hmac, json, re, secrets, shutil, subprocess, sys, tempfile, threading, time, traceback, types, zipfile
sys.dont_write_bytecode=True
ROOT=Path.cwd().resolve();BASE=ROOT/'开发者功能/修订日志/2026.11/回合执行基础'
MANIFEST=json.loads((BASE/'src/安装清单_24.json').read_bytes());CHANGES={c['path']:c for c in MANIFEST['changes']}
INSTALLED='--installed' in sys.argv
FROZEN=json.loads((BASE/'src/真实缺读失败样本_24.json').read_bytes())
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def source(rel,old=False):
 c=CHANGES.get(rel)
 if not c:return (ROOT/rel).read_bytes()
 return (ROOT/(c['backup'] if INSTALLED else rel) if old else ROOT/(rel if INSTALLED else c['staged'])).read_bytes()

sys.path.insert(0,str(ROOT))
import round_runtime as rr
import relationship_query as rq
import story_reading as sr

class HTTPError(Exception):
 def __init__(self,code):self.code=code

def abort(code):raise HTTPError(code)

def service_source(raw):
 tree=ast.parse(raw);tree.body=[n for n in tree.body if isinstance(n,(ast.Assign,ast.ClassDef,ast.FunctionDef))]
 env=dict(Path=Path,json=json,re=re,hashlib=hashlib,hmac=hmac,secrets=secrets,threading=threading,time=time,
          rr=rr,rq=rq,sr=sr,abort=abort,jsonify=lambda value=None,**kw:value if value is not None else kw,
          request=None,HTTPException=HTTPError,urlsplit=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit)
 exec(compile(tree,'<real story service>','exec'),env)
 return env['StoryService'],env

Service,ENV=service_source(source('story_service.py'));OldService,_=service_source(source('story_service.py',old=True))
work=Path(tempfile.mkdtemp(prefix='tmp_read24_tests_',dir=BASE/'tmp'));seed=work/'seed';seed.mkdir()
for rel in set(ENV['RULES'])|set(rr.FILES)|{'injection_core.py','data.json'}:
 dest=seed/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/rel).read_bytes())
for rel,text in FROZEN['facts'].items():(seed/rel).write_text(text,encoding='utf-8')
ctx=FROZEN['context'];specs=sr.specifications(seed)
for key,spec in specs.items():
 entry=ctx['reading_bundle']['entries'][key];raw=sr._document(spec,ctx['reading_bundle']['task_id'],ctx['reading_bundle']['nonce'])
 assert sha(raw)==entry['sha256'],key
 dest=seed/entry['path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
request_id=FROZEN['job']['request_id'];identity={'schema_version':1,**{k:FROZEN['job'][k] for k in ('request_id','base_revision','current_round')}}
real=rr.load_request(FROZEN['result_text']);results=[];details={}


def require(test,message='assertion failed'):
 if not test:raise AssertionError(message)

def rejects(fn,fragment,exception=Exception):
 try:fn()
 except exception as error:
  require(fragment in str(error),str(error));return str(error)
 raise AssertionError('expected rejection: '+fragment)

def case(name,fn):
 if '--failed-only' in sys.argv:
  previous=json.loads((BASE/'src/缺读补查验收首轮_24.json').read_bytes())
  saved=next((x for x in previous['cases'] if x['name']==name),None)
  if saved and saved['status']=='PASS':
   results.append(dict(saved,reused_from='缺读补查验收首轮_24.json'))
   if name=='real_plugin_session_and_repair_workflow_with_host_adapters':
    node=json.loads((BASE/'src/缺读补查Node结果_24.json').read_bytes());results.extend(dict(x,reused_from='缺读补查Node结果_24.json') for x in node['cases'])
   if name=='exact_real_failure_and_25_real_verified_records_replayed':details.update(previous['details'])
   return
 try:fn();results.append({'name':name,'status':'PASS'})
 except Exception as error:results.append({'name':name,'status':'FAIL','error':str(error),'traceback':traceback.format_exc()})
 print(results[-1]['status'],name,flush=True)

def project(name):
 p=work/name;shutil.copytree(seed,p);s=Service(p);s.start();job=copy.deepcopy(FROZEN['job'])
 job.update(status='generating',lease='isolated-lease24',lease_until=time.time()+10000,error='')
 state=s._read();state.update(latest=request_id,jobs={request_id:job});s._write(state)
 rr._atomic(s._blob(request_id,'.context.json'),rr._json(ctx));return p,s

p,svc=project('core')

def call_read(rel,begin=1,end=None,root=p):
 raw=(root/rel).read_bytes();lines=raw.decode().splitlines();end=min(len(lines),len(lines) if end is None else end)
 return {'name':'read_file_part','parameters':{'path':rel,'start_line':begin,'end_line':end},'status':'success',
         'part_id':'synthetic-read-'+str(begin),'result_text':'\n'.join(f'{i}| {lines[i-1]}' for i in range(begin,end+1))}

def initial_proof(root=p):
 tools=[]
 for record in FROZEN['audit']['verified_tools']:
  if record['name'] in sr.READ_TOOLS:
   nums=record['verified_lines'];tools.append(call_read(record['path'],min(nums),max(nums),root))
  else:tools.append({'name':record['name'],'parameters':{'path':record['path']},'status':record['status'],'part_id':'synthetic-dir','result_text':'synthetic directory receipt'})
 return {'api':'Tools.Chat.sendMessageStreaming','chat_id':'synthetic-isolated-read24','participant_id':'synthetic-reader24',
         'workspace':str(root),'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':24}},
         'snapshot_message_timestamp':24,'tools':tools,'started_at':100,'completed_at':200}

initial=initial_proof()

def stage_receipts(proof,count,final_timestamp=25):
 proof=copy.deepcopy(proof);outcome=copy.deepcopy(proof['outcome']);first_count=len(proof['tools'])-count
 proof['read_passes']=[{'outcome':outcome,'snapshot_message_timestamp':24,'tool_start':0,'tool_count':first_count},
  {'outcome':dict(outcome,assistant={'messageTimestamp':final_timestamp}),'snapshot_message_timestamp':final_timestamp,'tool_start':first_count,'tool_count':count}]
 proof['outcome']=proof['read_passes'][-1]['outcome'];proof['snapshot_message_timestamp']=final_timestamp;proof['repair_keys']=['sys.shame'];return proof

shame=ctx['reading_bundle']['entries']['sys.shame']
fixed=copy.deepcopy(initial);fixed['tools'].append(call_read(shame['path']));fixed=stage_receipts(fixed,1)

def body(proof=initial,value=real):return {'lease':'isolated-lease24','text':rr._json(value).decode('utf-8'),'conversation_audit':proof}


def syntax_routes():
 compile(source('story_service.py'),'story_service.py','exec')
 for rel in ['开发者功能/Operit故事桥接/main.js','开发者功能/Operit故事桥接/tools.js']:
  run=subprocess.run(['node','--check','-'],input=source(rel),capture_output=True);require(run.returncode==0,run.stderr.decode())
 with zipfile.ZipFile(ROOT/(CHANGES['开发者功能/Operit故事桥接/故事桥接.toolpkg']['path'] if INSTALLED else CHANGES['开发者功能/Operit故事桥接/故事桥接.toolpkg']['staged'])) as z:
  require(z.testzip() is None)
  for name in ['main.js','tools.js','manifest.json']:require(z.read(name)==source('开发者功能/Operit故事桥接/'+name))
  require(json.loads(z.read('manifest.json'))['version']=='1.3.0')
 # The new POST route is inside the unchanged same-origin/worker-token request boundary.
 before=ast.parse(source('story_service.py',old=True));after=ast.parse(source('story_service.py'))
 register=lambda tree:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register_story_routes')
 fn=lambda tree,name:next(n for n in register(tree).body if isinstance(n,ast.FunctionDef) and n.name==name)
 require(ast.dump(fn(before,'story_request_boundary'))==ast.dump(fn(after,'story_request_boundary')))
 require(ast.dump(fn(before,'result'))==ast.dump(fn(after,'result')))
 require("/api/story/worker/<key>/preflight" in ast.unparse(fn(after,'preflight')))
case('syntax_bundle_and_worker_boundary_preserved',syntax_routes)


def replay():
 old=OldService(p);facts=old._bridge_facts(ctx,FROZEN['audit']);require('sys.shame' not in facts['available_keys'])
 err=rejects(lambda:rr._assemble_bridge_result(p,real,identity,facts),'必需key未完整读取: sys.shame')
 details.update(real_failure=err,actual_tool_count=len(FROZEN['audit']['verified_tools']),missing_key='sys.shame',
                original_result_sha256=sha(FROZEN['result_text'].encode()),proofs_note='Stored verified audit is real; full tool receipts for new preflight tests are reconstructed and synthetic.')
case('exact_real_failure_and_25_real_verified_records_replayed',replay)


def no_writes():
 before=svc._path('tasks.json').read_bytes();facts=svc.store._files();names=sorted(x.name for x in svc.directory.iterdir())
 result=svc.preflight(request_id,body());require(result=={'ready':False,'missing_keys':['sys.shame'],'read_targets':[{'key':'sys.shame','reads':[{'path':shame['path'],'start_line':1,'end_line':44}]}]})
 require(before==svc._path('tasks.json').read_bytes());require(svc.store._files()==facts);require(names==sorted(x.name for x in svc.directory.iterdir()))
case('preflight_returns_exact_missing_key_location_without_writes',no_writes)


def partial_and_full():
 partial=copy.deepcopy(initial);partial['tools'].append(call_read(shame['path'],1,1));partial=stage_receipts(partial,1)
 require(svc.preflight(request_id,body(partial))['missing_keys']==['sys.shame'])
 partial['tools'][-1]['parameters']['end_line']=44
 require(svc.preflight(request_id,body(partial))['missing_keys']==['sys.shame'])
 require(svc.preflight(request_id,body(fixed))['ready'])
 fullaudit=svc._verify_audit(request_id,fixed);facts=svc._bridge_facts(ctx,fullaudit)
 value=rr._assemble_bridge_result(p,real,identity,facts);rr._validate(p,value,svc.store._files(),False)
 require(value['story_nodes']==real['story_nodes'] and value['memory_deltas']==real['memory_deltas'])
 details['nodes_preserved']=len(value['story_nodes'])
case('metadata_and_truncated_reads_rejected_full_read_passes',partial_and_full)


def split():
 value=copy.deepcopy(initial);value['tools'] += [call_read(shame['path'],1,20),call_read(shame['path'],21,44)];value=stage_receipts(value,2)
 require(svc.preflight(request_id,body(value))['ready'])
case('split_supplemental_ranges_combine_to_complete_read',split)


def no_hide():
 sample=copy.deepcopy(real);sample['model_audit']['required_keys'].remove('sys.shame');sample['model_audit']['evidence'].pop('sys.shame')
 missing=copy.deepcopy(initial);missing=stage_receipts(dict(missing,tools=missing['tools']+[call_read(shame['path'],1,1)]),1)
 require('sys.shame' in svc.preflight(request_id,body(missing,sample))['missing_keys'])
 audit=svc._verify_audit(request_id,missing)
 rejects(lambda:svc._bridge_facts(ctx,audit),'本轮缺必需正文: sys.shame')
case('repair_keys_cannot_be_removed_to_hide_missing_read',no_hide)


def relations():
 value=copy.deepcopy(initial);value['tools']=[x for x in value['tools'] if not (x['parameters']['path']==rq.VIEW and x['parameters'].get('start_line')==26)]
 report=svc.preflight(request_id,body(value));target=next(x for x in report['read_targets'] if x['key']=='lore.称谓.徐志北.沈知韫')
 require(target['reads']==[{'path':rq.VIEW,'start_line':1,'end_line':1},{'path':rq.VIEW,'start_line':26,'end_line':26}])
case('missing_relationship_uses_exact_header_and_direction_lines',relations)


def unknown():
 sample=copy.deepcopy(real);sample['model_audit']['required_keys'].append('sys.nonexistent')
 rejects(lambda:svc.preflight(request_id,body(initial,sample)),'未找到必需key的读取位置')
 malformed=copy.deepcopy(real);malformed['model_audit']['required_keys']=[{}]
 rejects(lambda:svc.preflight(request_id,body(initial,malformed)),'required_keys须为不重复')
case('unknown_key_and_malformed_required_keys_rejected',unknown)


def bad_passes():
 value=copy.deepcopy(fixed);value['read_passes'][0]['tool_count']-=1
 rejects(lambda:svc.preflight(request_id,body(value)),'正式会话补读回执或工具范围不符')
 value=copy.deepcopy(fixed);value['read_passes'][1]['outcome']['status']='cancelled'
 rejects(lambda:svc.preflight(request_id,body(value)),'正式会话未完成或消息快照不匹配')
 value=copy.deepcopy(fixed);value['read_passes'].append(value['read_passes'][1])
 rejects(lambda:svc.preflight(request_id,body(value)),'正式会话补读阶段须为1至2次')
case('invalid_cancelled_and_excess_read_pass_receipts_rejected',bad_passes)


def protected_audit():
 value=copy.deepcopy(initial);value['tools'].append({'name':'terminal','parameters':{'path':'.'},'status':'success','result_text':'anything'})
 rejects(lambda:svc.preflight(request_id,body(value)),'会话调用了白名单之外的工具')
 other=sr.build_bundle(p,'other-task');value=copy.deepcopy(initial);value['tools'].append(call_read(other['entries']['sys.shame']['path']))
 rejects(lambda:svc.preflight(request_id,body(value)),'读取了非本次任务提取件')
 value=copy.deepcopy(initial);value['tools'][0],value['tools'][1]=value['tools'][1],value['tools'][0]
 rejects(lambda:svc.preflight(request_id,body(value)),'前三份正文未按')
case('write_tools_foreign_projection_and_wrong_first_read_order_rejected',protected_audit)


def stale():
 target=p/shame['path'];before=target.read_bytes()
 try:
  target.write_bytes(before+b'tampered\n')
  rejects(lambda:svc.preflight(request_id,body()),'正文读取校验未通过')
 finally:target.write_bytes(before)
 target=p/'txt文件/知识库/系统标签类.json';before=target.read_bytes()
 try:
  target.write_bytes(before+b'\n')
  rejects(lambda:svc.preflight(request_id,body()),'正文读取校验未通过')
 finally:target.write_bytes(before)
case('tampered_projection_and_changed_original_source_still_rejected',stale)


def state_validation():
 value=body();value['lease']='wrong';rejects(lambda:svc.preflight(request_id,value),'结果属于已失效任务')
 value=body();value['extra']=True;rejects(lambda:svc.preflight(request_id,value),'读取预检: 未知键=')
 value=body();value['text']='not-json';rejects(lambda:svc.preflight(request_id,value),'JSON')
case('preflight_lease_body_and_json_strictly_validated',state_validation)


def missing_final_rejected():
 dest,s=project('missing-final');proof=initial_proof(dest)
 result=s.result(request_id,body(proof));require(result['task']['status']=='failed' and 'sys.shame' in result['task']['error'])
 require(json.loads((dest/'data.json').read_bytes())['round']==2)
case('direct_result_without_missing_read_still_rejected',missing_final_rejected)


def submit_once():
 dest,s=project('commit');proof=initial_proof(dest);proof['tools'].append(call_read(shame['path'],root=dest));proof=stage_receipts(proof,1)
 before=s.store._files();require(s.preflight(request_id,body(proof))['ready']);require(s.store._files()==before)
 result=s.result(request_id,body(proof));require(result['task']['status']=='committed',result['task'].get('error'))
 require(json.loads((dest/'data.json').read_bytes())['round']==3)
 after=s.store._files();again=s.result(request_id,body(proof));require(again['task']['status']=='committed' and after==s.store._files())
 rejects(lambda:s.preflight(request_id,body(proof)),'仅生成中的任务可预检')
 details['real_result_isolated_commit']={'round':3,'duplicate_commits':0,'changed_fields':False,'synthetic_added_read_receipt':True}
case('real_failed_result_complete_isolated_commit_and_idempotency',submit_once)


def http_route():
 dest,s=project('routing')
 class App:
  def __init__(self):self.extensions={};self.routes={}
  def post(self,path):return lambda fn:self.routes.setdefault(('POST',path),fn)
  def get(self,path):return lambda fn:self.routes.setdefault(('GET',path),fn)
  def before_request(self,fn):self.boundary=fn;return fn
  def after_request(self,fn):return fn
  def errorhandler(self,*args):return lambda fn:fn
 app=App();ENV['register_story_routes'](app,dest)
 path='/api/story/worker/'+request_id+'/preflight';token=app.extensions['story_service'].bridge_info()['token']
 def request(headers):
  ENV['request']=types.SimpleNamespace(path=path,host='127.0.0.1:5000',host_url='http://127.0.0.1:5000/',method='POST',headers=headers,is_json=True)
 request({})
 try:app.boundary();raise AssertionError('expected 403')
 except HTTPError as error:require(error.code==403)
 request({'X-Story-Bridge':token,'Origin':'https://foreign.test'})
 try:app.boundary();raise AssertionError('expected 403')
 except HTTPError as error:require(error.code==403)
 request({'X-Story-Bridge':token});app.boundary()
 proof=initial_proof(dest);ENV['request'].get_data=lambda **kwargs:rr._json(body(proof)).decode('utf-8')
 response=app.routes[('POST','/api/story/worker/<key>/preflight')](request_id)
 require(response['missing_keys']==['sys.shame'])
case('actual_route_registration_and_same_origin_worker_auth_adapters',http_route)


def claim_capability():
 dest,s=project('claim');state=s._read();state['jobs'][request_id].update(status='queued',lease=None);s._write(state)
 model=FROZEN['job']['generation_model'];response=s.claim({'model':model})
 require(response['task']['reading_preflight']==1 and response['task']['round_identity']==identity)
 require(s.status()['reading_preflight']==1)
case('status_and_claim_advertise_preflight_before_generation',claim_capability)


def node_tests():
 run=subprocess.run(['node',str(BASE/'src/缺读补查Node验收_24.js')]+(['--installed'] if INSTALLED else []),capture_output=True,text=True)
 print(run.stdout,flush=True);require(run.returncode==0,run.stderr+'\n'+run.stdout)
 data=json.loads((BASE/'src/缺读补查Node结果_24.json').read_bytes());results.extend(data['cases'])
case('real_plugin_session_and_repair_workflow_with_host_adapters',node_tests)


def unchanged():
 for rel,v in MANIFEST['dynamic_before'].items():require((sha((ROOT/rel).read_bytes()) if (ROOT/rel).exists() else None)==(v['sha256'] if v else None),rel)
 for rel,v in MANIFEST['protected'].items():require(sha((ROOT/rel).read_bytes())==v['sha256'],rel)
 state=json.loads((ROOT/'.round-runtime/story/tasks.json').read_bytes());require(state['jobs']==MANIFEST['jobs_before'] and state['latest']==MANIFEST['latest_before'])
case('live_saves_jobs_and_protected_sources_unchanged',unchanged)

out={'cases':results,'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results),'details':details,
     'real_service_class':True,'flask_http_tested':False,'route_request_adapters':True,'real_model_called':False,'live_submissions':False}
(BASE/'src/缺读补查验收结果_24.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
if not out['failed']:shutil.rmtree(work)
print('READ24_REGRESSION_'+('FAIL' if out['failed'] else 'PASS')+' cases='+str(len(results))+' passed='+str(out['passed'])+' failed='+str(out['failed'])+' live_submissions=false')
raise SystemExit(1 if out['failed'] else 0)
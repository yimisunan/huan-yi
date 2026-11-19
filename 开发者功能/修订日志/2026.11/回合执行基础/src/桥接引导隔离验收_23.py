"""Run focused HTTP/JS/packaging checks from the project root; all writes stay in tmp."""
from pathlib import Path
import ast, copy, hashlib, importlib.util, json, shutil, subprocess, sys, tempfile, time, traceback, types, zipfile
sys.dont_write_bytecode=True
ROOT=Path.cwd().resolve();BASE=ROOT/'开发者功能/修订日志/2026.11/回合执行基础'
MANIFEST=json.loads((BASE/'src/安装清单_23.json').read_bytes());CHANGES={c['path']:c for c in MANIFEST['changes']}
INSTALLED='--installed' in sys.argv
sys.path[:0]=[str(BASE/'tmp/tmp_deps23'),str(ROOT)]
from flask import Flask
import round_runtime as rr

def source(rel):return (ROOT/(rel if INSTALLED or rel not in CHANGES else CHANGES[rel]['staged'])).read_bytes()
ss=types.ModuleType('_bridge23_actual_service');ss.__file__=str(ROOT/'story_service.py')
exec(compile(source('story_service.py'),ss.__file__,'exec'),ss.__dict__)
work=Path(tempfile.mkdtemp(prefix='tmp_bridge23_tests_',dir=BASE/'tmp'));seed=work/'seed';seed.mkdir()
for rel in set(ss.RULES)|set(rr.FILES)|{'injection_core.py'}:
 p=seed/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source(rel))
results=[]

def case(name,fn):
 try:fn();results.append({'name':name,'status':'PASS'})
 except Exception as exc:results.append({'name':name,'status':'FAIL','error':str(exc),'traceback':traceback.format_exc()})
 print(results[-1]['status'],name,flush=True)

def require(test,message='assertion failed'):
 if not test:raise AssertionError(message)

def fixture(name):
 p=work/name;shutil.copytree(seed,p);app=Flask(name);app.testing=True;s=ss.register_story_routes(app,p);client=app.test_client()
 token=s.bridge_info()['token'];return p,s,client,{'X-Story-Bridge':token}

p,s,c,worker=fixture('control')
client_headers={'X-Story-Client':'1'}
model={'key':'["CHAT","test","test"]','function_type':'CHAT','provider_id':'test','model_id':'test','provider_name':'Test','pricing_configured':True}
runtime={'phase':'paused','running':False,'busy':False,'last_error':'','plugin_version':'1.2.0','model':model}

def http_security():
 require(c.post('/api/story/bridge/control',json={'action':'start'}).status_code==403)
 require(c.post('/api/story/worker/control',json={'runtime':runtime},headers={'X-Story-Bridge':'wrong'}).status_code==403)
 require(c.post('/api/story/bridge/control',json={'action':'start'},headers={**client_headers,'Origin':'https://evil.test'}).status_code==403)
 require(c.post('/api/story/worker/control',json={'runtime':runtime},headers={**worker,'Sec-Fetch-Site':'cross-site'}).status_code==403)
case('http_controls_require_same_origin_client_and_worker_token',http_security)

def typed_inputs():
 for body in [{'action':'delete'},{'action':'start','model':'x'},[]]:require(c.post('/api/story/bridge/control',json=body,headers=client_headers).status_code==400)
 bad=dict(runtime,running='true');require(c.post('/api/story/worker/control',json={'runtime':bad},headers=worker).status_code==400)
 require(c.post('/api/story/worker/control',json={'runtime':runtime,'ack_id':'invalid'},headers=worker).status_code==400)
case('control_and_worker_shapes_reject_invalid_or_extra_fields',typed_inputs)

def request_ack():
 before=s.store._files();r=c.post('/api/story/bridge/control',json={'action':'start'},headers=client_headers).get_json();cmd=r['bridge']['control']
 require(cmd['status']=='requested' and not r['bridge_connected'])
 repeated=c.post('/api/story/bridge/control',json={'action':'start'},headers=client_headers).get_json()['bridge']['control'];require(repeated['id']==cmd['id'])
 result=c.post('/api/story/worker/control',json={'runtime':runtime},headers=worker).get_json();require(result['command']['id']==cmd['id'])
 ready=dict(runtime,phase='ready',running=True)
 r=c.post('/api/story/worker/control',json={'runtime':ready,'ack_id':cmd['id'],'ack_error':''},headers=worker);require(r.status_code==200 and r.get_json()['command'] is None)
 status=c.get('/api/story/tasks').get_json();require(status['bridge_connected'] and status['bridge']['control']['status']=='applied')
 require(s.store._files()==before,'game facts changed')
case('start_intent_idempotency_worker_ack_and_real_status',request_ack)

def stop_error():
 r=c.post('/api/story/bridge/control',json={'action':'stop'},headers=client_headers).get_json();cmd=r['bridge']['control']
 c.post('/api/story/worker/control',json={'runtime':runtime,'ack_id':cmd['id']},headers=worker)
 status=c.get('/api/story/tasks').get_json();require(status['bridge']['present'] and not status['bridge_connected'] and status['bridge']['phase']=='paused')
 cmd=c.post('/api/story/bridge/control',json={'action':'start'},headers=client_headers).get_json()['bridge']['control']
 broken=dict(runtime,phase='error',last_error='Chat does not exist')
 c.post('/api/story/worker/control',json={'runtime':broken,'ack_id':cmd['id'],'ack_error':'Chat does not exist'},headers=worker)
 status=c.get('/api/story/tasks').get_json();require(not status['bridge_connected'] and status['bridge']['control']['status']=='failed' and status['bridge']['last_error']=='Chat does not exist')
case('paused_and_failed_runtime_are_not_reported_connected',stop_error)

def expiry():
 state=s._read();state['bridge_monitor']['received_at']=time.time()-16;state['bridge_control'].update(status='requested',issued_at=time.time()-121);s._write(state)
 status=c.get('/api/story/tasks').get_json();require(status['bridge']['phase']=='offline' and status['bridge']['control']['status']=='expired')
 require(c.post('/api/story/worker/control',json={'runtime':runtime},headers=worker).get_json()['command'] is None)
case('stale_heartbeat_and_control_expire_without_false_success',expiry)

def legacy():
 p2,s2,c2,w2=fixture('legacy');state=s2._read();state.update(bridge_seen=time.time(),bridge_model=model);s2._write(state)
 status=c2.get('/api/story/tasks').get_json();require(status['bridge_connected'] and status['bridge']['phase']=='legacy')
 state['bridge_seen']=0;s2._write(state);require(not c2.get('/api/story/tasks').get_json()['bridge_connected'])
case('legacy_worker_remains_compatible',legacy)

def archive():
 rel='开发者功能/Operit故事桥接/故事桥接.toolpkg'
 with zipfile.ZipFile(ROOT/(rel if INSTALLED else CHANGES[rel]['staged'])) as z:
  require(z.testzip() is None)
  for name in ['main.js','tools.js','manifest.json']:require(z.read(name)==source('开发者功能/Operit故事桥接/'+name))
  m=json.loads(z.read('manifest.json'));require(m['version']=='1.2.0' and m['api_version']=='2.0.0' and m['toolpkg_id']=='local.story.operit_bridge')
case('toolpkg_identity_version_and_exact_sources',archive)

def node_tests():
 r=subprocess.run(['node',str(BASE/'src/桥接引导Node验收_23.js')]+(['--installed'] if INSTALLED else []),capture_output=True,text=True)
 print(r.stdout,flush=True)
 require(r.returncode==0,r.stderr+'\n'+r.stdout)
case('node_plugin_and_frontend_focused_checks',node_tests)

def epoch_tests():
 r=subprocess.run(['node',str(BASE/'src/新档清理前端验收_21.js'),str(ROOT/('story_client.js' if INSTALLED else CHANGES['story_client.js']['staged']))],capture_output=True,text=True)
 require(r.returncode==0,r.stdout+r.stderr);parsed=json.loads(r.stdout.strip());require(parsed['passed']==5)
 results.extend(dict(item,name='existing_epoch_'+item['name']) for item in parsed['cases'])
case('existing_five_cross_save_checks',epoch_tests)

def syntax_and_live():
 compile(source('story_service.py'),'story_service.py','exec')
 for rel in ['story_client.js','开发者功能/Operit故事桥接/main.js','开发者功能/Operit故事桥接/tools.js']:
  r=subprocess.run(['node','--check',str(ROOT/(rel if INSTALLED else CHANGES[rel]['staged']))],capture_output=True,text=True);require(r.returncode==0,r.stderr)
 for rel,value in MANIFEST['dynamic_before'].items():
  if rel=='.round-runtime/story/tasks.json':continue
  p=ROOT/rel;require((hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)==(value['sha256'] if value else None),rel)
 state=json.loads((ROOT/'.round-runtime/story/tasks.json').read_bytes());require(state['jobs']==MANIFEST['jobs_before'] and state['latest']==MANIFEST['latest_before'])
 for rel,value in MANIFEST['protected'].items():require(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==value['sha256'],rel)
case('syntax_and_live_facts_protected_sources_unchanged',syntax_and_live)
node=json.loads((BASE/'src/桥接引导Node结果_23.json').read_bytes()) if (BASE/'src/桥接引导Node结果_23.json').exists() else {'cases':[]}
all_cases=results+node['cases'];out={'cases':all_cases,'passed':sum(v['status']=='PASS' for v in all_cases),'failed':sum(v['status']=='FAIL' for v in all_cases),
 'real_flask_test_client':True,'real_plugin_with_api_adapters':True,'real_model_called':False,'live_submissions':False,'real_browser':False}
(BASE/'src/桥接引导验收结果_23.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
if not out['failed']:shutil.rmtree(work)
print('BRIDGE23_ISOLATION_'+('FAIL' if out['failed'] else 'PASS')+' cases='+str(len(all_cases))+' passed='+str(out['passed'])+' failed='+str(out['failed'])+' live_submissions=false')
raise SystemExit(1 if out['failed'] else 0)
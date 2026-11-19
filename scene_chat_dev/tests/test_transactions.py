"""Offline transaction contract tests; no model/TTS requests."""
from pathlib import Path
import sys,json,shutil,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scene_chat import SceneService
from story_service import StoryService,register_story_routes
from flask import Flask
import round_runtime as rr
root=Path.cwd(); tmp=root/'scene_chat_dev/tmp';tmp.mkdir(exist_ok=True)
count=0
def reject(fn):
 global count
 try:fn()
 except (rr.RoundError,rr.ConflictError):count+=1;return
 raise AssertionError('accepted invalid request')
with tempfile.TemporaryDirectory(dir=tmp) as d:
 work=Path(d)
 for n in ('txt文件/场景交流规范.md','txt文件/知识库/角色类.json','txt文件/关系称谓查询.jsonl','txt文件/关系称谓库.json'):
  p=work/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,p)
 (work/'injection_core.py').write_text('# isolated project fixture')
 (work/'存档').mkdir();(work/'存档/base.txt').write_text('fixture')
 story=StoryService(work);s=SceneService(work,story)
 sid=s.create({'cast':['沈知韫'],'location':'客厅'})['scene']['id']
 req={'request_id':'scene-test','scene_id':sid,'base_scene_revision':0,'input':'今天忙吗？'}
 assert s.submit(req)==s.submit(req)
 reject(lambda:s.submit({**req,'input':'replacement'}))
 task=s.claim()['task'];assert task['entry_mode']=='scene_chat';assert s.claim()['task'] is None
 packet=json.loads(task['turns'][0]['content'])['packet'];raw=(work/packet['path']).read_bytes()
 payload=json.loads(raw);assert len(payload['characters'])==1
 assert all(r.get('speaker') in ('沈知韫','徐志北',None) and r.get('listener') in ('沈知韫','徐志北',None) for r in payload['relationships'])
 result={'messages':[{'kind':'dialogue','speaker':'沈知韫','text':'刚忙完，怎么了？'}],'facts_delta':[],'needs':[],'handoff':None}
 audit={'api':'Tools.Chat.sendMessageStreaming','chat_id':'offline','participant_id':'offline','workspace':str(work),'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':123}},'snapshot_message_timestamp':123,'tools':[{'name':'read_file','parameters':{'path':packet['path']},'status':'success','result_text':'\n'.join(f'{i}| {line}' for i,line in enumerate(raw.decode().splitlines(),1))}]}
 body={'lease':task['lease'],'text':json.dumps(result,ensure_ascii=False),'conversation_audit':audit}
 reject(lambda:s.worker(req['request_id'],'result',{**body,'lease':'wrong'}))
 reject(lambda:s.worker(req['request_id'],'result',{**body,'conversation_audit':{**audit,'tools':[]}}))
 bad=json.loads(json.dumps(audit));bad['tools'][0]['result_text']='1| partial'
 reject(lambda:s.worker(req['request_id'],'result',{**body,'conversation_audit':bad}))
 assert s.worker(req['request_id'],'preflight',body)['ready']
 assert s.snapshot(sid)['scene']['revision']==0
 s.worker(req['request_id'],'result',body);s.worker(req['request_id'],'result',body)
 assert s.snapshot(sid)['scene']['revision']==1
 assert SceneService(work,story).snapshot(sid)['scene']['history'][0]['messages']==result['messages']
 req2={**req,'request_id':'scene-test2','base_scene_revision':1,'input':'那就坐一会儿。'}
 s.submit(req2);t2=s.claim()['task']
 with s.db() as db: db.execute('UPDATE jobs SET expires=? WHERE id=?',(0,req2['request_id']))
 assert s.snapshot(sid)['task']['status']=='interrupted'
 s.retry(req2['request_id']);assert s.snapshot(sid)['task']['status']=='queued'
 t2=s.claim()['task'];s.worker(req2['request_id'],'result',{'lease':t2['lease'],'error':'offline failure'})
 (work/'txt文件/场景交流规范.md').write_text('changed')
 reject(lambda:s.retry(req2['request_id']))
 app=Flask('scene-offline');register_story_routes(app,work);client=app.test_client()
 assert client.get('/api/story/scene',base_url='http://localhost').status_code==200
 assert client.post('/api/story/scene',json=[],headers={'X-Story-Client':'1'},base_url='http://localhost').status_code==400
 assert client.post('/api/story/scene/worker/claim',json={},base_url='http://localhost').status_code==403
 print(json.dumps({'transactions':'PASS','idempotent_commit':'PASS','durable_restore':'PASS','expired_lease':'PASS','source_change':'PASS','packet_coverage':'PASS','route_boundary':'PASS','invalid_cases_rejected':count,'packet_bytes':len(raw)},ensure_ascii=False))

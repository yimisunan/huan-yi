"""Direct offline packet and transaction checks; no network/model calls."""
from pathlib import Path
import sys,json,tempfile,shutil,sqlite3
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scene_chat import SceneService,encode_packet
import story_reading as sr
import round_runtime as rr
root=Path.cwd(); comparisons=[]
# Compare the exact same existing payload, not new rules versus old rules.
dbpath=root/'.scene-chat/state.sqlite3'
if dbpath.exists():
 db=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True)
 for (data,) in db.execute('select data from jobs order by rowid desc limit 3'):
  p=root/json.loads(data)['path'];old=p.read_bytes();obj=json.loads(old);new=encode_packet(obj)
  assert json.loads(new)==obj
  assert len(new)<=len(old)
  comparisons.append({'old_bytes':len(old),'new_bytes':len(new),'old_lines':len(old.splitlines()),'new_lines':len(new.splitlines()),'max_line_bytes':max(map(len,new.splitlines()))})
 db.close()
class Paths:
 def _audit_path(self,path,workspace):
  value=Path(path)
  if value.is_absolute():value=value.relative_to(workspace)
  if '..' in value.parts:raise rr.RoundError('outside fixture')
  return value.as_posix()
with tempfile.TemporaryDirectory(dir=root/'scene_chat_dev/tmp') as folder:
 work=Path(folder)
 for name in ('txt文件/场景交流规范.md','txt文件/知识库/角色类.json','txt文件/关系称谓查询.jsonl','txt文件/关系称谓库.json'):
  target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
 (work/'存档').mkdir();(work/'存档/base.txt').write_text('fixture')
 service=SceneService(work,Paths());sid=service.create({'cast':['沈知韫'],'location':'客厅'})['scene']['id']
 request={'request_id':'scene-compact-check','scene_id':sid,'base_scene_revision':0,'input':'哥哥'}
 service.submit(request);task=service.claim()['task'];assert task['output_contract']['handoff']==''
 packet=json.loads(task['turns'][0]['content'])['packet'];raw=(work/packet['path']).read_bytes()
 obj=json.loads(raw);assert obj['input']==request['input'];assert obj['rules']==(root/'txt文件/场景交流规范.md').read_text()
 assert obj['scenario']['cast']==['沈知韫']
 assert any(c['key']=='char.徐承邺' for c in obj['characters'])
 assert not any(r.get('key')=='lore.知情.徐承邺' for r in obj['relationships'])
 assert service.references('继续说',[{'input':'哥哥'}])[0]['name']=='徐承邺'
 assert not service.references('亏损',[])
 assert not service.references('继续说',[{'input':'哥哥'},{'input':'一'},{'input':'二'}])
 result={'messages':[{'kind':'dialogue','speaker':'沈知韫','text':'刚忙完。'}],'facts_delta':[],'needs':[],'handoff':None}
 audit={'api':'Tools.Chat.sendMessageStreaming','chat_id':'offline','participant_id':'offline','workspace':str(work),'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':1}},'snapshot_message_timestamp':1,'tools':[{'name':'read_file','parameters':{'path':packet['path']},'status':'success','result_text':'\n'.join(f'{i}| {line}' for i,line in enumerate(raw.decode().splitlines(),1))}]}
 body={'lease':task['lease'],'text':json.dumps(result,ensure_ascii=False),'conversation_audit':audit}
 assert service.worker(task['request_id'],'preflight',body)['ready']
 bad=json.loads(json.dumps(body));bad['conversation_audit']['tools'][0]['result_text']='\n'.join(bad['conversation_audit']['tools'][0]['result_text'].splitlines()[:-1])
 try:service.worker(task['request_id'],'preflight',bad)
 except rr.RoundError:pass
 else:raise AssertionError('truncated packet accepted')
 service.worker(task['request_id'],'result',body);service.worker(task['request_id'],'result',body)
 assert service.snapshot(sid)['scene']['revision']==1
 with service.db() as db:
  saved=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(task['request_id'],)).fetchone()[0])
  assert saved['accepted_audit']['tools'][0]['result_text']==audit['tools'][0]['result_text']
  assert saved['accepted_audit']['references'][0]['name']=='徐承邺'
  assert 'lease' not in saved['accepted_audit']
 print('PASS referenced character routing, absent knowledge isolation, bounded carry, durable audit')
 print(json.dumps({'lossless_comparisons':comparisons,'coverage':'PASS','truncated_rejected':'PASS','idempotent_commit':'PASS','task_contract':'PASS'},ensure_ascii=False))

"""Typed scene messages and recovery API checks; isolated files, no model/TTS."""
from pathlib import Path
import json, shutil, sys, tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flask import Flask
from story_service import StoryService, register_story_routes
from scene_chat import SceneService
import round_runtime as rr

root = Path.cwd()
checks = 0

def reject(fn):
    global checks
    try:
        fn()
    except (rr.RoundError, rr.ConflictError):
        checks += 1
        return
    raise AssertionError('invalid response accepted')

with tempfile.TemporaryDirectory(dir=root/'scene_chat_dev/tmp') as folder:
    work = Path(folder)
    for name in ('txt文件/场景交流规范.md','txt文件/知识库/角色类.json','txt文件/关系称谓查询.jsonl','txt文件/关系称谓库.json'):
        p=work/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,p)
    (work/'存档').mkdir();(work/'存档/base.txt').write_text('isolated fixture')
    (work/'injection_core.py').write_text('# isolated fixture')
    live=work/'scene_chat_dev/src/scene_live';live.mkdir(parents=True)
    for p in (root/'scene_chat_dev/src/scene_live').iterdir():
        if p.is_file():shutil.copyfile(p,live/p.name)
    service=SceneService(work,StoryService(work))
    sid=service.create({'cast':['沈知韫','徐念薇'],'location':'客厅'})['scene']['id']
    request={'request_id':'scene-live-offline','scene_id':sid,'base_scene_revision':0,'input':'今天忙吗？'}
    assert service.request(request['request_id']) == {'task':None}
    first=service.submit(request);assert service.submit(request)==first
    reject(lambda:service.submit({**request,'input':'replacement'}))
    task=service.claim()['task'];assert {m['kind'] for m in task['output_contract']['messages']}=={'dialogue','action','narration'}
    packet=json.loads(task['turns'][0]['content'])['packet'];raw=(work/packet['path']).read_bytes()
    audit={'api':'Tools.Chat.sendMessageStreaming','chat_id':'offline','participant_id':'offline','workspace':str(work),
           'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':12}},
           'snapshot_message_timestamp':12,'tools':[{'name':'read_file','parameters':{'path':packet['path']},'status':'success',
           'result_text':'\n'.join(f'{i}| {line}' for i,line in enumerate(raw.decode().splitlines(),1))}]}
    messages=[{'kind':'narration','speaker':'','text':'窗外的雨停了。'},
              {'kind':'action','speaker':'沈知韫','text':'她合上文件，抬头看你。'},
              {'kind':'dialogue','speaker':'沈知韫','text':'刚忙完。你呢？'}]
    result={'messages':messages,'facts_delta':[],'needs':[],'handoff':None}
    body={'lease':task['lease'],'text':json.dumps(result,ensure_ascii=False),'conversation_audit':audit}
    for invalid in ({'kind':'action','speaker':'苏婉青','text':'她起身。'},
                    {'kind':'action','speaker':'','text':'她起身。'},
                    {'kind':'narration','speaker':'沈知韫','text':'雨停了。'},
                    {'kind':'move','speaker':'沈知韫','text':'她已经到公司。'},
                    {'kind':'dialogue','speaker':'徐志北','text':'我替玩家说话。'}):
        reject(lambda m=invalid:service.worker(request['request_id'],'preflight',{**body,'text':json.dumps({**result,'messages':[m]})}))
    truncated={**audit,'tools':[{**audit['tools'][0],'result_text':'1| partial'}]}
    reject(lambda:service.worker(request['request_id'],'preflight',{**body,'conversation_audit':truncated}))
    assert service.worker(request['request_id'],'preflight',body)['ready']
    service.worker(request['request_id'],'result',body);service.worker(request['request_id'],'result',body)
    restored=SceneService(work,StoryService(work));snapshot=restored.snapshot(sid)
    assert snapshot['scene']['revision']==1 and snapshot['scene']['history'][0]['messages']==messages
    assert len(snapshot['scene']['history'])==1
    public=restored.request(request['request_id'])['task']
    assert public['status']=='committed' and 'lease' not in public and 'data' not in public
    assert restored.scenes()['scenes'][0]['id']==sid
    reject(lambda:restored.submit({**request,'request_id':'scene-stale'}))
    app=Flask('scene-live-offline');story=register_story_routes(app,work);client=app.test_client()
    with client.get('/scene-live',base_url='http://localhost') as response:
        assert response.status_code==200
    for name in ('live.css','live.js'):
        with client.get('/scene-live/assets/'+name,base_url='http://localhost') as response:
            assert response.status_code==200
            assert response.data==(live/name).read_bytes()
    assert client.get('/scene-live/assets/README.md',base_url='http://localhost').status_code==404
    connection=client.get('/api/story/scene/connection',base_url='http://localhost').get_json()
    assert connection['scene_protocol']==3 and 'action' in connection['message_kinds']
    assert client.get('/api/story/scene/list',base_url='http://localhost').get_json()['scenes'][0]['id']==sid
    assert client.get('/api/story/scene/request/'+request['request_id'],base_url='http://localhost').get_json()['task']['status']=='committed'
    assert client.get('/api/story/scene/list',base_url='http://localhost',headers={'Origin':'https://outside.invalid'}).status_code==403
    assert client.post('/api/story/scene/messages',json=request,base_url='http://localhost').status_code==403
    print(json.dumps({'typed_messages':'PASS','invalid_speakers_and_kinds_rejected':checks,'read_coverage':'PASS','same_request_commit_once':'PASS','restart_restore':'PASS','request_lookup':'PASS','candidate_routes':'PASS','same_origin_boundary':'PASS'},ensure_ascii=False))

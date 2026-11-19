"""Formal entry acceptance/recovery checks; fixtures live under the existing task tmp."""
from pathlib import Path
import base64
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import round_runtime as rr
import interaction_runtime as ir
from story_service import StoryService, register_story_routes
from flask import Flask

spec = importlib.util.spec_from_file_location('save_cleaner', ROOT / '存档清理器.py')
cleaner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleaner)


def fixture(folder, *, progression=False):
    folder = Path(folder)
    names = ['injection_core.py', 'round_runtime.py', 'interaction_runtime.py', 'story_progression.py', 'story_reading.py', 'relationship_query.py',
             'txt文件/事件注册表.json', 'txt文件/互动运行配置.json', 'txt文件/场景交流规范.md',
             'txt文件/提示词.md', 'txt文件/全局执行法典.md', 'txt文件/一键注入指南.txt',
             'txt文件/故事检索索引.md', 'txt文件/关系称谓库.json', 'txt文件/关系称谓查询.jsonl',
             '存档清理器.py', '存档开局随机盲盒.py', *['txt文件/知识库/' + n + '.json' for n in ('角色类','世界观类','叙事判断','系统标签类')]]
    for name in names:
        if not (ROOT/name).is_file():
            continue
        target = folder/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    if not progression:
        (folder/'txt文件/互动运行配置.json').write_text(json.dumps({'version':1,'locations':['徐家主宅','市中心顶层公寓','大学','工作室'], 'operations':['move_player','transfer_item'], 'resource':{'status':'pending','base_cost':None,'action_costs':None,'recovery':None,'limits':None}}))
    for name, content in cleaner.TEMPLATES.items():
        target = folder/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
    (folder/'data.json').write_text(json.dumps({'round':0, 'storyNodes':[], 'presence':{}, 'sceneTitle':'徐家主宅'}))
    return folder


class InteractionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='official-test-', dir=ROOT/'scene_chat_dev/tmp')
        self.root = fixture(self.temp.name)
        self.store = rr.RoundStore(self.root)
        self.service = StoryService(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def request(self, ident='one', op=None, text='今天怎么样？'):
        return {'schema_version':1, 'entry_mode':ir.MODE, 'request_id':ident,
                'base_revision':self.store.prepare()['base_revision'], 'input':text,
                'messages':[{'kind':'narration','speaker':'','text':'门边传来脚步声。'}] if op else
                           [{'kind':'dialogue','speaker':'沈知韫','text':'先坐一会儿。'}],
                'operation':op, 'handoff':'',
                'audit':{'required_reads_verified':True,'origin':'player_action' if op else 'operit_session'}}

    def job(self, ident='job', command=None):
        self.service.create({'request_id':ident, 'base_revision':self.store.prepare()['base_revision'],
                             'entry_mode':ir.MODE, 'save_epoch':self.service._save_epoch(), 'action':'前往市中心顶层公寓' if command else '今天怎么样？',
                             **({'operation':command} if command else {})})
        task = self.service.claim()['task']
        context = json.loads(self.service._blob(ident,'.context.json').read_bytes())
        p = context['packet']; lines=(self.root/p['path']).read_text().splitlines()
        proof={'api':'Tools.Chat.sendMessageStreaming','chat_id':'offline-fixture','participant_id':'offline',
               'workspace':str(self.root),'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':1}},
               'snapshot_message_timestamp':1,'tools':[{'name':'read_file','parameters':{'path':p['path']},'status':'success',
                'result_text':'\n'.join(f'{i}| {line}' for i,line in enumerate(lines,1))}]}
        result={'messages':[{'kind':'narration','speaker':'','text':'话音落下，房间安静了片刻。'}],
                'decision':{'prompt':'如何回应？','options':[{'id':'A','text':'问起今天的安排'},{'id':'B','text':'礼貌地握手告别'},{'id':'C','text':'提出自己的具体建议'}]},
                'operation':command,'handoff':'','checks':{'intent':'只回应当前询问，没有替玩家决定。',
                'knowledge':'仅使用当前在场人物可知内容。','action':'与本次预检操作一致，未改动其他人物。','pace':'本次动作结果已经呈现，等待玩家的新决定。'}}
        return task,context,{'lease':task['lease'],'text':json.dumps(result,ensure_ascii=False),'conversation_audit':proof}

    def test_chat_saved_once_and_old_round_timers_unchanged(self):
        before=self.store._files();request=self.request()
        first=self.store.submit(request);again=self.store.submit(request)
        self.assertEqual(first['state_version'],1);self.assertTrue(again['replayed'])
        after=self.store._files()
        for name in rr.FILES[:3]:self.assertEqual(before[name],after[name])
        self.assertEqual(json.loads(after['data.json'])['round'],0)
        self.assertEqual(len(ir.records(self.store)),1)
        self.assertEqual(StoryService(self.root).interaction_snapshot()['history'][0]['input'],'今天怎么样？')

    def test_movement_updates_formal_presence_and_separates_witnesses(self):
        request=self.request(op={'code':'move_player','destination':'市中心顶层公寓'})
        self.store.submit(request)
        state=ir.view(self.store)
        self.assertEqual(state['location'],'市中心顶层公寓');self.assertEqual(state['cast'],['苏婉青'])
        row=json.loads(ir.records(self.store)[0].read_text())
        self.assertNotIn('沈知韫',row['messages_known_by']);self.assertNotIn('苏婉青',row['input_known_by'])
        self.assertEqual(json.loads(self.store._files()['data.json'])['interaction']['actions'],1)

    def test_same_id_changed_payload_and_stale_revision_rejected(self):
        req=self.request();old=copy.deepcopy(req);old['request_id']='stale'
        self.store.submit(req)
        bad=copy.deepcopy(req);bad['input']='changed'
        with self.assertRaises(rr.ConflictError):self.store.submit(bad)
        with self.assertRaises(rr.ConflictError):self.store.submit(old)
        self.assertEqual(len(ir.records(self.store)),1)

    def test_transfer_owned_stack_once_and_absent_recipient_denied(self):
        # Seed inventory through trusted engine in fixture, never by changing the live save.
        engine=rr._engine(self.root,self.root)
        engine.update_item_catalog(0,[{'name':'文具','type':'永久性','quantity':2,'target':'未使用','location':'徐志北'}])
        op={'code':'transfer_item','item_id':'ITEM-001','recipient':'沈知韫'}
        req=self.request(op=op);self.store.submit(req);self.assertTrue(self.store.submit(req)['replayed'])
        item=ir.view(self.store)['items'][0]
        self.assertEqual(item['quantity'],2);self.assertEqual(item['fields']['当前状态'],'已交付')
        with self.assertRaises(rr.RoundError):self.store.submit(self.request('twice',op))
        bad=dict(op,recipient='苏婉青')
        with self.assertRaises(rr.RoundError):self.store.submit(self.request('absent',bad))

    def test_invalid_speaker_patch_and_unregistered_operation(self):
        for key,value in [('messages',[{'kind':'dialogue','speaker':'苏婉青','text':'错误在场'}]),
                          ('operation',{'code':'disclose_secret'}),('panel_changes',{})]:
            req=self.request();req[key]=value
            with self.subTest(key=key),self.assertRaises(rr.RoundError):self.store.submit(req)
        self.assertFalse(ir.records(self.store))

    def test_read_audit_covers_all_packet_lines_and_real_result_commits(self):
        task,context,body=self.job()
        bad=copy.deepcopy(body);bad['conversation_audit']['tools'][0]['result_text']='1| {'
        with self.assertRaises(rr.RoundError):self.service.preflight('job',bad)
        self.assertTrue(self.service.preflight('job',body)['ready'])
        self.assertEqual(self.service.result('job',body)['task']['status'],'committed')
        self.assertEqual(self.service.result('job',body)['task']['status'],'committed')
        self.assertEqual(len(StoryService(self.root).interaction_snapshot()['history']),1)

    def test_storage_interruption_recovers_staged_transcript_and_original_reply(self):
        task,context,body=self.job()
        real=self.store._publish
        invoked=[]
        def fail_once(values):
            if not invoked:
                invoked.append(True)
                first=next(iter(values));rr._atomic(self.store._path(first),values[first])
                raise OSError('injected storage failure')
            return real(values)
        with patch.object(self.service.store,'_publish',side_effect=fail_once):
            with self.assertRaises(OSError):self.service.result('job',body)
        self.assertEqual(self.service._read()['jobs']['job']['status'],'validating')
        self.assertEqual(len(ir.records(self.store)),0)
        restored=StoryService(self.root).interaction_snapshot()
        self.assertEqual(restored['task']['status'],'committed');self.assertEqual(len(restored['history']),1)

    def test_committed_journal_redoes_message_and_state_together(self):
        req=self.request();files=self.store._files();after=ir.settle(self.store,ir.validate(self.root,req,files),files,1,'one')
        receipt={'request_id':'one','state_version':1,'revision':rr._revision(after)}
        after[rr.META]=rr._json({'version':1,'sequence':1,'receipts':{'one':{'payload_hash':'test','receipt':receipt}}})
        before={n:self.store._path(n).read_bytes() if self.store._path(n).exists() else None for n in after}
        enc=lambda v:{n:base64.b64encode(x).decode() if x is not None else None for n,x in v.items()}
        rr._atomic(self.store._path('.round-runtime/journal.json'),rr._json({'version':1,'phase':'committed','before':enc(before),'after':enc(after)}))
        restored=rr.RoundStore(self.root);restored.recover()
        self.assertEqual(len(ir.records(restored)),1);self.assertEqual(json.loads(restored._files()['data.json'])['interaction']['count'],1)

    def test_reset_removes_official_and_experimental_history_and_changes_epoch(self):
        self.store.submit(self.request())
        (self.root/'.scene-chat').mkdir();(self.root/'.scene-chat/fixture').write_text('test')
        with patch.object(cleaner,'server_running',return_value=False):
            result=cleaner.reset(self.root)
        self.assertEqual(result['status'],'reset')
        state=StoryService(self.root).interaction_snapshot()
        self.assertEqual(state['history'],[]);self.assertNotEqual(state['save_epoch'],'legacy')
        self.assertFalse((self.root/'.scene-chat').exists())
        self.assertEqual(state['world']['location'],'徐家主宅')

    def test_no_24_exchange_limit_and_history_pagination(self):
        for n in range(65):self.store.submit(self.request('msg-'+str(n)))
        first=self.service.interaction_snapshot();second=self.service.interaction_snapshot(first['history'][0]['sequence'])
        self.assertEqual(len(first['history']),60);self.assertEqual(len(second['history']),5)
        self.assertTrue(first['has_older']);self.assertFalse(second['has_older'])
        self.assertEqual(first['world']['interaction']['count'],65)

    def test_new_game_api_idempotent_and_rejects_inflight(self):
        self.store.submit(self.request())
        body={'request_id':'reset-fixture', 'save_epoch':'legacy', 'confirm':'new_game'}
        first=self.service.new_game(body)
        second=self.service.new_game(body)
        self.assertEqual(first['save_epoch'],second['save_epoch']);self.assertTrue(second['replayed'])
        self.assertEqual(self.service.interaction_snapshot()['history'],[])
        self.service.create({'request_id':'pending','base_revision':self.store.prepare()['base_revision'],
                             'entry_mode':ir.MODE,'save_epoch':self.service._save_epoch(),'action':'你好'})
        with self.assertRaises(rr.ConflictError):
            self.service.new_game(dict(body,request_id='reset-two',save_epoch=first['save_epoch']))

    def test_operation_packet_uses_destination_cast_and_host_boundaries(self):
        task,context,body=self.job(command={'code':'move_player','destination':'市中心顶层公寓'})
        payload=json.loads((self.root/context['packet']['path']).read_text())
        self.assertEqual(payload['scenario']['cast'],['苏婉青'])
        self.assertTrue(any(c['key']=='char.徐志北' for c in payload['characters']))
        self.assertIn('市中心顶层公寓',payload['operation_policy']['locations'])
        self.assertEqual(self.service.result('job',body)['task']['status'],'committed')
        state=self.service.interaction_snapshot()
        self.assertEqual(state['world']['cast'],['沈知韫'])
        self.service.playback_progress({'save_epoch':state['save_epoch'],'segment_id':'job','revealed':1,'completed':False})
        state=self.service.playback_progress({'save_epoch':state['save_epoch'],'segment_id':'job','revealed':1,'completed':True})
        self.assertEqual(state['world']['cast'],['苏婉青'])

    def test_active_cost_once_insufficient_and_no_implicit_pending_defaults(self):
        path=self.root/ir.CONFIG;config=json.loads(path.read_text())
        config['resource']={'status':'active','version':1,'attribute':'体力','base_cost':7,
                            'action_costs':{'move_player':11,'transfer_item':3},'recovery':None,'limits':None}
        path.write_text(json.dumps(config))
        req=self.request(op={'code':'move_player','destination':'市中心顶层公寓'})
        self.store.submit(req);self.store.submit(req)
        memory=self.store._files()[rr.FILES[0]].decode()
        self.assertEqual(rr._engine(self.root,self.root)._read_attr_value(memory,'系统宿主','体力'),82)
        row=json.loads(ir.records(self.store)[0].read_text());self.assertEqual(row['cost']['total'],18)
        config['resource']['base_cost']=100;path.write_text(json.dumps(config))
        before=self.store._files()
        unpaid=self.request('insufficient');unpaid['messages']=[{'kind':'dialogue','speaker':'苏婉青','text':'你好。'}]
        with self.assertRaisesRegex(rr.RoundError,'资源不足'):self.store.submit(unpaid)
        self.assertEqual(before,self.store._files())
        config['resource']={'status':'pending','base_cost':0,'action_costs':None}
        path.write_text(json.dumps(config))
        with self.assertRaises(rr.RoundError):ir.policy(self.root)

    def test_old_epoch_rejected_even_when_default_snapshot_matches(self):
        body={'request_id':'stale-tab','base_revision':self.store.prepare()['base_revision'],
              'entry_mode':ir.MODE,'save_epoch':'legacy','action':'你好'}
        self.service.new_game({'request_id':'reset-test','save_epoch':'legacy','confirm':'new_game'})
        body['base_revision']=self.store.prepare()['base_revision']
        with self.assertRaises(rr.ConflictError):self.service.create(body)

    def test_requested_action_can_be_declined_without_state_change(self):
        task,context,body=self.job(command={'code':'move_player','destination':'市中心顶层公寓'})
        value=json.loads(body['text']);value.update(operation=None,handoff='暂未确认能进入目的地，移动尚未执行。')
        value['messages']=[{'kind':'narration','speaker':'','text':'你还未出发。'}]
        body['text']=json.dumps(value)
        self.assertEqual(self.service.result('job',body)['task']['status'],'committed')
        state=self.service.interaction_snapshot()
        self.assertEqual(state['world']['location'],'徐家主宅')
        self.assertEqual(state['world']['interaction']['actions'],0)
        self.assertFalse(state['history'][0]['handoff'])
        for revealed in (1, 1):
            state=self.service.playback_progress({'save_epoch':state['save_epoch'],'segment_id':'job',
                'revealed':revealed,'completed':revealed==1 and state['playback']['revealed']==1})
        self.assertTrue(state['history'][0]['handoff'])

    def test_http_boundaries_and_live_snapshot_share_store(self):
        app=Flask('formal-check');register_story_routes(app,self.root);client=app.test_client()
        self.assertEqual(client.get('/api/story/live').status_code,200)
        self.assertEqual(client.post('/api/story/tasks',json={}).status_code,403)
        self.assertEqual(client.post('/api/story/worker/claim',json={},headers={'X-Story-Client':'1'}).status_code,403)
        self.assertEqual(client.get('/api/story/live',headers={'Origin':'https://foreign.example'}).status_code,403)


if __name__=='__main__':unittest.main(verbosity=2)
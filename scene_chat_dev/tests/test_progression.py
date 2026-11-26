"""Fixed accounting and memory-clock acceptance on disposable project roots."""
from pathlib import Path
import base64
import copy
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from test_interaction import fixture
from story_service import StoryService,register_story_routes
import round_runtime as rr
import interaction_runtime as ir
import story_progression as sp
from flask import Flask

DECISION={'prompt':'接下来如何回应？','options':[{'id':'A','text':'继续聊起今天的安排'},{'id':'B','text':'礼貌地握手告别'},{'id':'C','text':'主动提出自己的建议'}]}

class ProgressionChecks(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='tmp_step21_test-',dir=ROOT/'scene_chat_dev/tmp')
  self.root=fixture(self.temp.name,progression=True)
  self.service=StoryService(self.root);self.store=self.service.store;self.counter=0
 def tearDown(self):self.temp.cleanup()
 def energy(self):return sp.stamina(self.root,self.store._files())
 def edit_energy(self,value):
  files=sp.change_stamina(self.root,self.store._files(),value)
  (self.root/rr.FILES[0]).write_bytes(files[rr.FILES[0]])
 def play(self):
  snap=self.service.interaction_snapshot();p=snap['playback']
  if not p['segment_id']:return
  for step in range(p['revealed']+1,p['total']+1):self.service.playback_progress({'save_epoch':snap['save_epoch'],'segment_id':p['segment_id'],'revealed':step,'completed':False})
  self.service.playback_progress({'save_epoch':snap['save_epoch'],'segment_id':p['segment_id'],'revealed':p['total'],'completed':True})
 def request(self,option='BEGIN',text=None,key=None):
  snap=self.service.interaction_snapshot();row=ir.segment(self.root,self.store._files())
  if text is None:text='继续当前剧情' if option=='BEGIN' else '继续休息' if option=='REST' else next(x['text'] for x in row['decision']['options'] if x['id']==option)
  self.counter+=1
  return {'request_id':key or 'charge-'+str(self.counter),'base_revision':snap['revision'],'entry_mode':ir.MODE,'save_epoch':snap['save_epoch'],'action':text,'selection':{'segment_id':snap['playback']['segment_id'] if option!='BEGIN' else '','option_id':option}}
 def response(self,task,*,category='SYSTEM',day=1,time='22:00',text='房间里灯光安静，谈话暂时停了下来。',events=None,sleep=None,transfers=None):
  key=task['request_id'];context=json.loads(self.service._blob(key,'.context.json').read_text());packet=context['packet'];lines=(self.root/packet['path']).read_text().splitlines()
  proof={'api':'Tools.Chat.sendMessageStreaming','chat_id':'offline','participant_id':'fixture','workspace':str(self.root),'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':1}},'snapshot_message_timestamp':1,'tools':[{'name':'read_file','parameters':{'path':packet['path']},'status':'success','result_text':'\n'.join(str(i)+'| '+line for i,line in enumerate(lines,1))}]}
  result={'messages':[{'kind':'narration','speaker':'','text':text}],'decision':DECISION,'operation':None,'handoff':'','checks':{'intent':'仅承接本次玩家明确行为。','knowledge':'只使用本场已经成立的信息。','action':'没有附加未授权行动。','pace':'本次后果结束，交还新的决定。'},'resolution':{'category':category,'basis':'按本次原文实际日常或明确行为判档。','clock':{'day':day,'time':time,'basis':'对应本段谈话或休息实际经过时间。'},'events':events or [],'memory':{'fact':text,'transfers':transfers or {}},'conditions':None if category=='SYSTEM' else {'intensity':category,'effective_progress':True,'scene':'徐家主宅','npc':'沈知韫','action_changed':True,'stress_signals':0,'breakout_triggered':[]},'sleep':sleep or {'kind':'none','start':None,'evidence':''},'task':None,'items':[]}}
  return {'lease':task['lease'],'text':json.dumps(result,ensure_ascii=False),'conversation_audit':proof}
 def begin(self,time='22:00'):
  self.service.create(self.request());task=self.service.claim()['task'];result=self.service.result(task['request_id'],self.response(task,time=time));self.assertEqual(result['task']['status'],'committed',result);self.play()
 def accept(self,option='A',category='A',**kw):
  self.service.create(self.request(option));task=self.service.claim()['task'];result=self.service.result(task['request_id'],self.response(task,category=category,**kw));self.assertEqual(result['task']['status'],'committed',result);return result
 def item(self,quantity=3,effect=10):
  engine=rr._engine(self.root,self.root)
  engine.update_item_catalog(1,[{'name':'恢复剂','type':'临时性（消耗品）','quantity':quantity,'duration':'无','system_effect':'host_stamina:'+str(effect),'desc':'恢复宿主体力的系统道具。'}])
  return 'ITEM-001'
 def test_fixed_tiers_and_custom_refund_exactly_once(self):
  self.begin()
  for letter in ('A','B','C'):
   before=self.energy();request=self.request(letter);self.service.create(request);self.assertEqual(self.energy(),before-sp.COSTS[letter]);self.service.create(request);self.assertEqual(self.energy(),before-sp.COSTS[letter]);task=self.service.claim()['task'];body=self.response(task,category=letter,time='22:10');result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'committed',result);self.play()
  before=self.energy();self.service.create(self.request('CUSTOM','问问明天的天气'));self.assertEqual(self.energy(),before-15);task=self.service.claim()['task'];result=self.service.result(task['request_id'],self.response(task,category='A',time='22:15'));self.assertEqual(result['task']['status'],'committed',result);self.assertEqual(self.energy(),before-5);self.play();self.assertEqual(self.service.interaction_snapshot()['settlement']['refunded'],10)
 def test_model_switch_queue_retry_and_active_attempt(self):
  def model(name):
   return {'function_type':'CHAT','provider_id':'fixture','provider_name':'fixture','model_id':name,'key':json.dumps(['CHAT','fixture',name],separators=(',',':')),'pricing_configured':False}
  first,second,third=map(model,('first','second','third'))
  self.begin();request=self.request('A');request['model_key']=first['key']
  self.service.create(request);self.assertEqual(self.energy(),95)
  task=self.service.claim({'model':second})['task'];self.assertEqual(task['model_key'],second['key'])
  self.assertEqual(self.service._read()['jobs'][task['request_id']]['generation_model'],second)
  self.service.claim({'model':third})
  self.assertEqual(self.service._read()['jobs'][task['request_id']]['generation_model'],second)
  self.service.result(task['request_id'],{'lease':task['lease'],'error':'retry test'})
  self.assertEqual(self.energy(),100)
  self.service.retry(task['request_id']);self.assertEqual(self.energy(),95)
  self.assertNotIn('generation_model',self.service._read()['jobs'][task['request_id']])
  retried=self.service.claim({'model':third})['task'];self.assertEqual(retried['model_key'],third['key'])
  self.assertNotEqual(retried['lease'],task['lease'])
  with self.assertRaises(rr.ConflictError):self.service.result(task['request_id'],{'lease':task['lease'],'error':'stale'})
  sp.cancel(self.service,task['request_id']);self.assertEqual(self.energy(),100)
 def test_failure_cancel_retry_and_late_result(self):
  self.begin();request=self.request('CUSTOM','谈谈今天');self.service.create(request);task=self.service.claim()['task'];late=self.response(task,category='A');self.service.result(task['request_id'],{'lease':task['lease'],'error':'offline failure'});self.assertEqual(self.energy(),100);self.service.retry(task['request_id']);self.assertEqual(self.energy(),85)
  with self.assertRaises(rr.ConflictError):self.service.result(task['request_id'],late)
  result=sp.cancel(self.service,task['request_id']);self.assertEqual(result['task']['status'],'cancelled');self.assertEqual(self.energy(),100);sp.cancel(self.service,task['request_id']);self.assertEqual(self.energy(),100)
 def test_timeout_and_preparing_restart_refund(self):
  self.begin();self.service.create(self.request('A'));task=self.service.claim()['task']
  with self.store._locked():state=self.service._read();state['jobs'][task['request_id']]['lease_until']=0;self.service._write(state)
  self.service.interaction_snapshot();self.assertEqual(self.energy(),100)
  request=self.request('C');self.service.create(request)
  with self.store._locked():state=self.service._read();state['jobs'][request['request_id']]['status']='preparing';self.service._write(state)
  other=StoryService(self.root);other.start();self.assertEqual(sp.stamina(self.root,other.store._files()),100)
 def test_final_threshold_not_temporary_hold_and_forced_sleep(self):
  self.begin();self.edit_energy(15);self.service.create(self.request('CUSTOM','只聊一句'));self.assertEqual(self.energy(),0);task=self.service.claim()['task'];res=self.service.result(task['request_id'],self.response(task,category='A',time='22:10'));self.assertEqual(res['task']['status'],'committed',res);self.assertEqual(self.energy(),10);self.play()
  self.edit_energy(8);self.accept(time='23:00');self.assertEqual(self.energy(),3);self.play();runtime=sp.state(self.root,self.store._files());self.assertEqual(runtime['phase'],'resting');closed=runtime['last_closed']
  with self.assertRaises(rr.ConflictError):self.service.create(self.request('A'))
  text='他在夜里安稳睡下，次日七点醒来。';self.accept(option='REST',category='SYSTEM',day=2,time='07:00',text=text,sleep={'kind':'overnight','start':{'day':1,'time':'23:00'},'evidence':text});self.assertEqual(self.energy(),100);self.play();runtime=sp.state(self.root,self.store._files());self.assertEqual(runtime['last_closed'],closed);self.assertEqual(runtime['phase'],'ready')
 def test_midnight_and_memory_append_do_not_close_twice(self):
  self.begin(time='23:50');self.accept(day=1,time='23:55',text='第一件事实已经说清。');self.play();self.accept(day=2,time='00:00',text='第二件事实也已确认。');self.play();runtime=sp.state(self.root,self.store._files());self.assertEqual(runtime['last_closed'],1);self.accept(day=2,time='00:10',text='凌晨继续谈到第三件事实。');self.play();self.assertEqual(sp.state(self.root,self.store._files())['last_closed'],1);memory=(self.root/rr.FILES[0]).read_text();self.assertIn('第一件事实',memory);self.assertIn('第二件事实',memory);self.assertIn('第三件事实',memory)
 def test_item_uses_actual_inventory_budget_and_free_path(self):
  self.begin();self.edit_energy(10);self.item();request=self.request('CUSTOM','使用恢复道具 ITEM-001');result=self.service.create(request);self.assertEqual(result['task']['status'],'committed',result);self.assertEqual(self.energy(),20);self.service.create(request);self.assertEqual(self.energy(),20);self.play();result=self.service.create(self.request('CUSTOM','使用恢复道具 ITEM-001'));self.assertEqual(result['task']['status'],'committed',result);self.assertEqual(self.energy(),30);self.play()
  with self.assertRaises(rr.RoundError):self.service.create(self.request('CUSTOM','使用恢复道具 ITEM-001'))
  self.assertEqual(sp.state(self.root,self.store._files())['item_recovered'],20)
 def test_item_full_missing_unregistered_and_mixed_are_rejected(self):
  self.begin();self.item()
  with self.assertRaises(rr.RoundError):self.service.create(self.request('CUSTOM','使用恢复道具 ITEM-001'))
  self.edit_energy(10)
  with self.assertRaises(rr.RoundError):self.service.create(self.request('CUSTOM','使用恢复道具 ITEM-001 并和她聊聊'))
  with self.assertRaises(rr.RoundError):self.service.create(self.request('CUSTOM','使用恢复道具 ITEM-999'))
  self.assertEqual(self.energy(),10)
 def test_events_real_diff_and_old_base_cost_deduplicated(self):
  self.begin();text='他认真听完今天的安排，她点了点头。';event=[{'group':'host_events','target':'系统宿主','tags':['日常_信任建立','体力_日常消耗'],'evidence':text}];self.accept(time='22:10',text=text,events=event);self.assertEqual(self.energy(),95);self.assertIn('积分 2',(self.root/rr.FILES[0]).read_text());self.play();receipt=self.service.interaction_snapshot()['settlement'];self.assertEqual(receipt['net_cost'],5);self.assertTrue(any(x['attribute']=='积分' and x['delta']==2 for x in receipt['changes']))
 def test_bad_result_refunds_and_no_premature_receipt(self):
  self.begin();request=self.request('A');self.service.create(request);task=self.service.claim()['task'];body=self.response(task,category='A');value=json.loads(body['text']);value['resolution']['clock']['day']=0;body['text']=json.dumps(value);result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'failed');self.assertEqual(self.energy(),100)
  self.accept(time='22:10');snapshot=self.service.interaction_snapshot();self.assertIsNone(snapshot['settlement']);self.assertNotIn('settlement',snapshot['history'][-1]);self.play();self.assertEqual(self.service.interaction_snapshot()['settlement']['stamina_after'],95)
 def test_prepared_journal_rolls_back_held_balance_and_job(self):
  self.begin();before=self.store._files();request=self.request('C');original=self.store._publish;calls=0
  def fail_once(values):
   nonlocal calls;calls+=1
   if calls==1:
    key=rr.FILES[0];rr._atomic(self.root/key,values[key]);raise OSError('simulated interruption')
   return original(values)
  with patch.object(self.store,'_publish',side_effect=fail_once):
   with self.assertRaises(OSError):self.service.create(request)
  self.store.recover();self.assertEqual(self.store._files(),before);self.assertNotIn(request['request_id'],self.service._read()['jobs'])
 def test_http_cancel_boundary_and_system_effect_stays_in_catalog(self):
  self.begin();request=self.request('A');self.service.create(request);app=Flask('accounting-http');service=register_story_routes(app,self.root);client=app.test_client();url='/api/story/tasks/'+request['request_id']+'/cancel';self.assertEqual(client.post(url,json={}).status_code,403);self.assertEqual(client.post(url,json={},headers={'X-Story-Client':'1'}).status_code,200);self.assertEqual(self.energy(),100)
 def test_short_or_interrupted_rest_never_refills(self):
  self.begin();self.edit_energy(8);self.accept(time='23:00');self.play();text='短暂睡了一会儿，他被声响惊醒。';self.accept(option='REST',category='SYSTEM',time='23:20',text=text,sleep={'kind':'interrupted','start':{'day':1,'time':'23:00'},'evidence':text});self.assertEqual(self.energy(),3);self.play();self.assertEqual(sp.state(self.root,self.store._files())['phase'],'resting')

 def test_early_morning_sleep_and_task_rewards_remain_once(self):
  self.begin(time='01:00');self.edit_energy(8);self.accept(time='01:05');self.play()
  text='他凌晨一点睡下，早晨八点醒来。'
  self.accept(option='REST',category='SYSTEM',day=1,time='08:00',text=text,sleep={'kind':'overnight','start':{'day':1,'time':'01:05'},'evidence':text});self.play();self.assertEqual(self.energy(),100);self.assertEqual(sp.state(self.root,self.store._files())['last_closed'],1)
  engine=rr._engine(self.root,self.root)
  engine.process_task_system({'title':'练习目标','target':'系统宿主','attr':'积分','value':2,'tier':'small','item_desc':'普通纪念品'},2,str(self.root/rr.FILES[0]))
  text='他认真听完今天的安排。';events=[{'group':'host_events','target':'系统宿主','tags':['日常_信任建立'],'evidence':text}]
  self.accept(time='08:10',text=text,events=events);self.play();panel=engine._read_host_panel(str(self.root/rr.FILES[0]));self.assertEqual(panel['积分'],17);self.assertEqual(engine._parse_task_block((self.root/rr.FILES[0]).read_text())['current']['status'],'已完成')
  self.accept(time='08:15',text='他把事情再确认了一遍。');self.play();self.assertEqual(engine._read_host_panel(str(self.root/rr.FILES[0]))['积分'],17)
 def test_four_layer_transfer_preserves_source_and_action_timers(self):
  import save_store
  self.begin();engine=rr._engine(self.root,self.root)
  st,ms,rc=save_store.load_bundle(self.root)
  for idx in range(1,25):
   ms=save_store.record_memory_turn(ms,fact=f'第{idx}幕关键因果事实。',day=idx,time_str='20:00',location='徐家主宅',known_by=['徐志北','沈知韫'],overnight=True)
  save_store.save_bundle(self.root,st,ms,rc)
  self.assertTrue(save_store.needs_chronicle_archive(ms))
  text='新的第二十五幕事实，两人约定明日复查账目。';request=self.request('A');self.service.create(request);task=self.service.claim()['task']
  body=self.response(task,category='A',time='22:10',text=text)
  payload=json.loads(body['text'])
  payload['resolution']['memory']={'fact':text,'anchor_ops':[{'op':'add','kind':'promise','importance':4,'text':'约定明日复查账目','private_host':False}],'chronicle_digest':{'public':'前八幕完成了徐家主宅多轮试探与账目摸底。','views':{'沈知韫':'私下保留了对账单原件。'}}}
  body['text']=json.dumps(payload,ensure_ascii=False)
  result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'committed',result);self.play()
  _,ms_after,_=save_store.load_bundle(self.root)
  self.assertEqual(len(ms_after['chronicle']),1);self.assertEqual(len(ms_after['anchors']),1);self.assertLessEqual(len(ms_after['episodes']),save_store.MAX_HOT_EPISODES)
 def test_bad_event_target_and_invalid_sleep_return_prepaid_funds(self):
  self.begin();text='话题暂时告一段落。';request=self.request('A');self.service.create(request);task=self.service.claim()['task'];body=self.response(task,category='A',text=text,events=[{'group':'affection_events','target':'苏婉青','tags':['社交微幅回馈'],'evidence':text}]);result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'failed');self.assertEqual(self.energy(),100)
 def test_committed_journal_recovers_task_receipt_and_balance_together(self):
  self.begin();request=self.request('A');self.service.create(request);task=self.service.claim()['task'];body=self.response(task,category='A',time='22:10');self.service.result(task['request_id'],body)
  after=self.store._files();tasks=self.service._read();ledger=self.store._ledger();record={'version':1,'phase':'committed','before':{},'after':{}}
  values={**after,rr.META:rr._json(ledger),sp.TASKS:rr._json(tasks)}
  for name,value in values.items():record['before'][name]=None;record['after'][name]=base64.b64encode(value).decode() if value is not None else None
  rr._atomic(self.root/'.round-runtime/journal.json',rr._json(record));rr._atomic(self.root/sp.TASKS,rr._json({'version':1,'latest':None,'jobs':{},'bridge_seen':0}));self.store.recover();self.assertEqual(self.energy(),95);self.assertEqual(self.service._read()['jobs'][task['request_id']]['status'],'committed');self.service.result(task['request_id'],body) if False else None

if __name__=='__main__':unittest.main()

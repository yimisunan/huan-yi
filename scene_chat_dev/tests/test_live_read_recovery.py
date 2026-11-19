"""Read coverage/recovery, retry feedback and session controls on disposable roots."""
from pathlib import Path
from types import SimpleNamespace
import copy,json,secrets,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent));sys.dont_write_bytecode=True
import round_runtime as rr
import interaction_runtime as ir
import story_progression as sp
from story_service import StoryService,register_story_routes
from test_interaction import fixture
import test_progression as progression_checks
from flask import Flask

class LiveReadRecoveryChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='tmp_step27_audit-',dir=ROOT/'scene_chat_dev/tmp');self.root=Path(self.tmp.name)
  self.raw=b'{\n"a":1\n}\n\n';(self.root/'packet.txt').write_bytes(self.raw)
  self.context={'audit':{},'entry_mode':ir.MODE,'packet':{'path':'packet.txt','sha256':rr._digest(self.raw),'through_line':4},'allowed_archive':[],'allowed_memory_reads':[],'required_memory_reads':[]}
  self.cp=self.root/'context.json';self.cp.write_text(json.dumps(self.context))
  self.story=SimpleNamespace(root=self.root,_blob=lambda key,suffix:self.cp,_source_check=lambda context:None,store=SimpleNamespace(_path=lambda p:self.root/p))
  self.proof={'api':'Tools.Chat.sendMessageStreaming','outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':1}},'snapshot_message_timestamp':1,'chat_id':'fixture','participant_id':'fixture','tools':[]}
 def tearDown(self):self.tmp.cleanup()
 def call(self,begin,end):
  lines=self.raw.decode().splitlines()
  return {'name':'read_file_part','parameters':{'path':'packet.txt','start_line':str(begin),'end_line':str(end)},'status':'success','result_text':'\n'.join(str(i)+'| '+lines[i-1] for i in range(begin,end+1))}
 def test_trailing_blank_can_be_absent_but_final_nonblank_cannot(self):
  self.proof['tools']=[self.call(1,3)];self.assertTrue(ir.verify(self.story,'x',self.proof)['required_reads_verified'])
  self.proof['tools']=[self.call(1,2)]
  with self.assertRaisesRegex(rr.RoundError,'缺少行 3'):ir.verify(self.story,'x',self.proof)
  missing=ir.verify(self.story,'x',self.proof,allow_missing=True)
  self.assertEqual(missing['read_targets'],[{'key':'packet','reads':[{'path':'packet.txt','start_line':3,'end_line':3}]}])
 def test_preflight_returns_missing_without_running_story_assembly(self):
  self.proof['tools']=[self.call(1,2)]
  class Locked:
   def __enter__(self):pass
   def __exit__(self,*args):pass
  story=SimpleNamespace(**self.story.__dict__);story.start=lambda:None;story._read=lambda:{};story._leased=lambda *args:{'status':'generating'};story.store._locked=lambda:Locked()
  result=StoryService.preflight(story,'x',{'lease':'lease','text':'{}','conversation_audit':self.proof})
  self.assertFalse(result['ready']);self.assertEqual(result['read_targets'][0]['reads'][0]['start_line'],3)
 def test_one_same_task_repair_cumulative_receipt_and_wrong_identity_rejected(self):
  first=copy.deepcopy(self.proof['outcome']);second=copy.deepcopy(first);second['assistant']['messageTimestamp']=2
  self.proof.update(outcome=second,snapshot_message_timestamp=2,tools=[self.call(1,2),self.call(3,3)],read_passes=[{'outcome':first,'snapshot_message_timestamp':1,'tool_start':0,'tool_count':1},{'outcome':second,'snapshot_message_timestamp':2,'tool_start':1,'tool_count':1}])
  self.assertTrue(ir.verify(self.story,'x',self.proof)['required_reads_verified'])
  self.proof['read_passes'][1]['tool_start']=0
  with self.assertRaisesRegex(rr.RoundError,'工具范围'):ir.verify(self.story,'x',self.proof)
  self.proof['read_passes']*=2
  with self.assertRaisesRegex(rr.RoundError,'一次'):ir.verify(self.story,'x',self.proof)
 def test_missing_mode_cannot_hide_wrong_tool_or_forged_body(self):
  for call in [{'name':'write_file','parameters':{'path':'packet.txt'}},{**self.call(1,2),'result_text':'1| fabricated'}]:
   self.proof['tools']=[call]
   with self.assertRaises(rr.RoundError):ir.verify(self.story,'x',self.proof,allow_missing=True)

class RetryAndControlChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='tmp_step27_retry-',dir=ROOT/'scene_chat_dev/tmp');self.root=fixture(self.tmp.name,progression=True)
  self.service=StoryService(self.root);self.helper=progression_checks.ProgressionChecks();self.helper.root=self.root;self.helper.store=self.service.store;self.helper.service=self.service;self.helper.counter=0
 def tearDown(self):self.tmp.cleanup()
 def test_paid_retry_passes_error_memory_history_and_original_action_once(self):
  self.helper.begin();request=self.helper.request('A');self.service.create(request);task=self.service.claim()['task']
  self.service.result(task['request_id'],{'lease':task['lease'],'error':'实际缺少行：17'});balance=self.helper.energy()
  self.service.retry(task['request_id']);context=json.loads(self.service._blob(task['request_id'],'.context.json').read_text());envelope=json.loads(context['turns'][0]['content']);packet=json.loads((self.root/context['packet']['path']).read_text())
  self.assertIn('实际缺少行：17',envelope['previous_validation_error']);self.assertIn('实际缺少行：17',packet['previous_validation_error'])
  self.assertEqual(packet['input'],request['action']);self.assertTrue(packet['accepted_history']);self.assertTrue(packet['player_private_state']['memory'])
  self.assertEqual(self.helper.energy(),balance-5);self.service.retry(task['request_id']);self.assertEqual(self.helper.energy(),balance-5)
  claim=self.service.claim()['task'];self.assertIn('实际缺少行：17',claim['previous_validation_error']);self.assertEqual(claim['live_reading_revision'],2);self.assertTrue(claim['service_epoch'])
 def test_web_session_control_and_runtime_visibility_busy_rejection(self):
  app=Flask('session-controls');register_story_routes(app,self.root);client=app.test_client()
  response=client.post('/api/story/bridge/control',headers=dict([('X-Story-Client',str(1))]),json={'action':'session_policy','session_policy':'service_restart'});self.assertEqual(response.status_code,200,response.json)
  self.assertEqual(self.service._read()['bridge_control']['session_policy'],'service_restart')
  self.assertEqual(client.post('/api/story/bridge/control',headers=dict([('X-Story-Client',str(1))]),json={'action':'session_policy','session_policy':'bad'}).status_code,400)
  runtime={'phase':'ready','running':True,'busy':False,'last_error':'','plugin_version':'1.9.0','model':None,'session':{'policy':'service_restart','chat_id':'live-chat','generation':1,'reset_reason':'首次连接'}}
  self.service.worker_control({'runtime':runtime});self.assertEqual(self.service.status()['bridge']['session']['chat_id'],'live-chat')
  self.service.create(self.helper.request());self.assertEqual(client.post('/api/story/bridge/control',headers=dict([('X-Story-Client',str(1))]),json={'action':'reset_session'}).status_code,409)
 def test_service_identity_changes_only_on_python_service_instance(self):
  first=self.service.status()['service_epoch'];self.assertEqual(first,self.service.status()['service_epoch']);self.assertNotEqual(first,StoryService(self.root).status()['service_epoch'])

if __name__=='__main__':unittest.main()
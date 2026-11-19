"""Paid condition contracts and player travel verified through disposable RoundStore transactions."""
from pathlib import Path
import copy,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent));sys.dont_write_bytecode=True
import interaction_runtime as ir
import round_runtime as rr
import story_progression as sp
from story_service import StoryService
from test_interaction import fixture
import test_progression as progression

class ActionContractChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='tmp_step28_test-',dir=ROOT/'scene_chat_dev/tmp');self.root=fixture(self.tmp.name,progression=True)
  self.service=StoryService(self.root);self.store=self.service.store;self.helper=progression.ProgressionChecks();self.helper.root=self.root;self.helper.store=self.store;self.helper.service=self.service;self.helper.counter=0
 def tearDown(self):self.tmp.cleanup()
 def begin_apartment(self):
  self.helper.begin(time='09:35');rr._engine(self.root,self.root).apply_interaction_operation({'code':'move_player','destination':'市中心顶层公寓'})
 def task(self,text):
  request=self.helper.request('CUSTOM',text);self.service.create(request);return self.service.claim()['task']
 def reply(self,task,operation=None,conditions='valid',text='你回到徐家主宅，先在门口确认母亲是否在家。'):
  body=self.helper.response(task,category='A',time='09:45',text=text);result=json.loads(body['text']);result['operation']=operation;result['resolution']['memory']={'fact':'','compact':'','transfers':{}}
  result['resolution']['conditions']={'intensity':'A','effective_progress':False,'scene':'徐家主宅' if operation else '市中心顶层公寓','npc':None,'action_changed':bool(operation),'stress_signals':0,'breakout_triggered':[]} if conditions=='valid' else conditions
  body['text']=json.dumps(result,ensure_ascii=False);return body
 def test_direct_registered_aliases_and_noncommittal_phrases(self):
  for text,target in [('回到家里，看看妈妈在不在家','徐家主宅'),('回家','徐家主宅'),('我现在回家看看','徐家主宅'),('先回到家中','徐家主宅'),('返回主宅','徐家主宅'),('去公寓','市中心顶层公寓'),('前往徐家主宅，看看妈妈在不在家','徐家主宅'),('去大学','大学')]:
   with self.subTest(text=text):self.assertEqual(ir.travel_intent(self.root,text)['operation']['destination'],target)
  for text in ['不回家','先不回家','明天回家','等会回家','如果妈妈在家就回家','问她要不要回家','回家还是去大学','回家，随后去公司','回家？','回家里屋','回家，下午再去公司']:
   with self.subTest(text=text):self.assertIsNone(ir.travel_intent(self.root,text))
 def test_dynamic_system_and_paid_contracts(self):
  request=self.helper.request();self.service.create(request);context=json.loads(self.service._blob(request['request_id'],'.context.json').read_text());envelope=json.loads(context['turns'][0]['content'])
  self.assertFalse(envelope['resolution_policy']['conditions_required']);self.assertEqual(envelope['output_contract']['resolution']['category'],'SYSTEM');self.assertIsNone(envelope['output_contract']['resolution']['conditions'])
  self.assertTrue(sp.resolution_policy('action')['conditions_required']);self.assertEqual(set(sp.contract(self.root,'action')['conditions']),rr.ROUND_CONDITION_FIELDS)
  for kind in ['begin','rest','item']:self.assertIsNone(sp.contract(self.root,kind)['conditions'])
 def test_alias_packet_and_transaction_move_once_without_moving_npc(self):
  self.begin_apartment();before=self.helper.energy();task=self.task('回到家里，看看妈妈在不在家');context=json.loads(self.service._blob(task['request_id'],'.context.json').read_text());envelope=json.loads(context['turns'][0]['content']);packet=json.loads((self.root/context['packet']['path']).read_text());move={'code':'move_player','destination':'徐家主宅'}
  self.assertEqual(context['command'],move);self.assertEqual(envelope['operation_context']['requested'],move);self.assertEqual(envelope['operation_context']['input_evidence']['destination_text'],'家里');self.assertEqual(packet['scenario']['location'],'徐家主宅');self.assertEqual(packet['scenario']['cast'],['沈知韫']);self.assertTrue(envelope['resolution_policy']['conditions_required'])
  body=self.reply(task,operation=move);self.assertTrue(self.service.preflight(task['request_id'],body)['ready']);result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'committed',result)
  after=self.store._files();presence=rr._engine(self.root,self.root).parse_presence_from_memory(after[rr.FILES[0]].decode());self.assertEqual(presence['徐志北']['location'],'徐家主宅');self.assertEqual(presence['苏婉青']['location'],'市中心顶层公寓');self.assertEqual(self.helper.energy(),before-5)
  with self.assertRaises(rr.ConflictError):self.service.result(task['request_id'],body)
  self.assertEqual(self.store._files(),after);self.assertEqual(self.helper.energy(),before-5)
 def test_paid_missing_or_renamed_conditions_rejected_then_valid_object_passes(self):
  self.begin_apartment();task=self.task('问问今天的安排')
  for value in [None,'',[],{'intensity':'A','progress':False,'scene':'市中心顶层公寓','npc':None,'action_change':False,'stress_count':0,'breakout':[]}]:
   with self.subTest(value=value),self.assertRaisesRegex(rr.RoundError,'resolution.conditions'):self.service.preflight(task['request_id'],self.reply(task,conditions=value))
  body=self.reply(task,text='你停在原处，先确认刚才提到的安排。');self.assertTrue(self.service.preflight(task['request_id'],body)['ready']);result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'committed',result)
 def test_unauthorized_movement_does_not_gain_alias_permission(self):
  self.begin_apartment();files=self.store._files();move={'code':'move_player','destination':'徐家主宅'}
  for text in ['不回家','明天回家','问问妈妈在不在家','回家还是去大学']:
   with self.subTest(text=text),self.assertRaisesRegex(rr.RoundError,'移动缺少'):ir.operation(self.root,files,move,text)
  self.assertEqual(ir.operation(self.root,files,move,'回到家里，看看妈妈在不在家'),move)
  with self.assertRaisesRegex(rr.RoundError,'已经位于'):ir.operation(self.root,files,{'code':'move_player','destination':'市中心顶层公寓'},'回公寓')
 def test_missing_conditions_failure_refunds_once_and_retry_keeps_error(self):
  self.begin_apartment();before=self.helper.energy();task=self.task('先确认一下今天安排');body=self.reply(task,conditions=None)
  result=self.service.result(task['request_id'],body);self.assertEqual(result['task']['status'],'failed');self.assertIn('resolution.conditions',result['task']['error']);self.assertEqual(self.helper.energy(),before)
  self.service.retry(task['request_id']);retry=self.service.claim()['task'];self.assertIn('resolution.conditions',retry['previous_validation_error']);self.assertEqual(self.helper.energy(),before-15)
  with self.assertRaises(rr.ConflictError):self.service.result(task['request_id'],body)

if __name__=='__main__':unittest.main()
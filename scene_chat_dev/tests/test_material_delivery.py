"""Direct material delivery and lease audit on disposable roots; no Flask required."""
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
import ast, copy, json, sys, tempfile, time, unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.dont_write_bytecode = True
import interaction_runtime as ir
import round_runtime as rr
import story_progression as sp

# Execute the real service methods without importing the unavailable HTTP dependency.
tree = ast.parse((ROOT/'story_service.py').read_text())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'StoryService')
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('material', '_leased')]
import hmac
scope = dict(ir=ir, rr=rr, time=time, hmac=hmac)
exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='ServiceMethods', bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])), 'story_service.py', 'exec'), scope)

class MaterialDeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'scene_chat_dev/tmp')
        self.root = Path(self.tmp.name)
        self.raw = ir.encode_live_packet({'input':'当前行动', 'private':'仅玩家知情', 'previous_validation_error':'上次失败'})
        (self.root/'packet.txt').write_bytes(self.raw)
        self.memory = rr.FILES[0]
        p = self.root/self.memory; p.parent.mkdir(parents=True); p.write_text('第一行\n完整必要记忆\n第三行\n')
        (self.root/'history.json').write_text('{"messages_known_by":["甲"],"text":"已接受原文"}')
        self.ref = {'path':self.memory, 'start_line':2, 'end_line':2}
        self.context = {'entry_mode':ir.MODE, 'packet':{'path':'packet.txt', 'sha256':rr._digest(self.raw), 'through_line':len(self.raw.decode().splitlines())},
            'audit':{n:rr._digest((self.root/n).read_bytes()) for n in (self.memory, 'history.json')},
            'required_memory_reads':[self.ref], 'allowed_memory_reads':[self.ref], 'required_history_reads':['history.json'], 'allowed_archive':['history.json'],
            'turns':[{'kind':'user','content':json.dumps({'instruction':'逐段读取', 'output_contract':{'operation':None,'handoff':'','resolution':{'task':None,'sleep':{'start':None},'conditions':{'npc':None}}}})}]}
        self.cp = self.root/'x.context.json'; self.cp.write_text(json.dumps(self.context))
        self.job = {'status':'generating','entry_mode':ir.MODE,'lease':'current-lease','lease_until':time.time()+120}
        self.service = scope['ServiceMethods']()
        self.service.root = self.root
        self.service._blob = lambda key, suffix:self.root/(key+suffix)
        self.service.store = SimpleNamespace(_path=lambda p:self.root/p, _locked=nullcontext)
        self.service.start = lambda:None
        self.service._read = lambda:{'jobs':{'x':self.job}}
        self.service._write = lambda state:None
        self.service._source_check = self.source_check
        self.body = {'lease':self.job['lease'], 'chat_id':'chat', 'participant_id':'card'}
    def tearDown(self): self.tmp.cleanup()
    def source_check(self, context):
        for n, digest in context['audit'].items():
            if rr._digest((self.root/n).read_bytes()) != digest: raise rr.ConflictError('源已经改变')
    def issue(self): return self.service.material('x', self.body)
    def proof(self, delivery):
        outcome = {'type':'committed','status':'completed','userMessageTimestamp':10,'assistant':{'messageTimestamp':20}}
        return {'api':'Tools.Chat.sendMessageStreaming','chat_id':'chat','participant_id':'card','outcome':outcome,'snapshot_message_timestamp':20,'tools':[],
                'delivery':{**delivery['delivery'],'user_message_timestamp':10}, 'read_passes':[{'outcome':outcome,'snapshot_message_timestamp':20,'tool_start':0,'tool_count':0}]}
    def test_complete_delivery_without_model_file_reads(self):
        data=self.issue(); payload=json.loads(data['input_text']); self.assertEqual(payload['material'],json.loads(self.raw))
        self.assertEqual(payload['required_sources'][0]['body'],'完整必要记忆')
        self.assertIn('已接受原文',payload['required_sources'][1]['body'])
        self.assertEqual(rr._digest(data['input_text'].encode()),data['delivery']['input_sha256'])
        audit=ir.verify(self.service,'x',self.proof(data));self.assertTrue(audit['required_reads_verified']);self.assertEqual(audit['verified_tools'],[])
        self.assertEqual(audit['material_delivery']['kind'],'program_inline_v1')
    def test_same_lease_idempotent_and_session_rebind_rejected(self):
        first=self.issue();self.assertEqual(first,self.issue());self.body['chat_id']='other'
        with self.assertRaises(rr.ConflictError):self.issue()
    def test_retry_issues_new_delivery_and_rejects_old(self):
        first=self.issue();old=self.proof(first);self.job['lease']='retry';self.body['lease']='retry';second=self.issue()
        self.assertNotEqual(first['delivery']['id'],second['delivery']['id'])
        with self.assertRaises(rr.RoundError):ir.verify(self.service,'x',old)
        self.assertTrue(ir.verify(self.service,'x',self.proof(second))['required_reads_verified'])
    def test_changed_lease_expiration_or_completed_job_rejected(self):
        data=self.issue();proof=self.proof(data)
        for field,value in [('lease','other'),('lease_until',0),('status','failed')]:
            old=self.job[field];self.job[field]=value
            with self.assertRaises(rr.ConflictError):ir.verify(self.service,'x',proof)
            self.job[field]=old
    def test_tampered_receipt_and_identity_rejected(self):
        data=self.issue(); original=self.proof(data)
        for field,value in [('id','forged'),('input_sha256','0'*64),('user_message_timestamp',11)]:
            proof=copy.deepcopy(original);proof['delivery'][field]=value
            with self.assertRaises(rr.RoundError):ir.verify(self.service,'x',proof)
        for field in ('chat_id','participant_id'):
            proof=copy.deepcopy(original);proof[field]='other'
            with self.assertRaises(rr.RoundError):ir.verify(self.service,'x',proof)
        proof=copy.deepcopy(original);del proof['delivery']['user_message_timestamp']
        with self.assertRaises(rr.RoundError):ir.verify(self.service,'x',proof)
    def test_packet_mutation_after_delivery_rejected(self):
        data=self.issue();(self.root/'packet.txt').write_text('{}')
        with self.assertRaises(rr.ConflictError):ir.verify(self.service,'x',self.proof(data))
    def test_supplement_mutation_and_context_mutation_rejected(self):
        data=self.issue();(self.root/'history.json').write_text('{}')
        with self.assertRaises(rr.ConflictError):ir.verify(self.service,'x',self.proof(data))
        self.context['audit']['history.json']=rr._digest(b'{}');self.cp.write_text(json.dumps(self.context))
        with self.assertRaises(rr.ConflictError):ir.verify(self.service,'x',self.proof(data))
    def test_permitted_optional_read_and_second_receipt(self):
        data=self.issue();proof=self.proof(data)
        call={'name':'read_file_part','parameters':{'path':self.memory,'start_line':2,'end_line':2},'status':'success','result_text':'2| 完整必要记忆'}
        second={'type':'committed','status':'completed','userMessageTimestamp':30,'assistant':{'messageTimestamp':40}}
        proof['read_passes'].append({'outcome':second,'snapshot_message_timestamp':40,'tool_start':0,'tool_count':1})
        proof.update(outcome=second,snapshot_message_timestamp=40,tools=[call])
        self.assertTrue(ir.verify(self.service,'x',proof)['required_reads_verified'])
        proof['tools'][0]['parameters']['path']='outside.txt'
        with self.assertRaises(rr.RoundError):ir.verify(self.service,'x',proof)
    def test_invalid_lease_and_non_live_issuance_rejected(self):
        self.body['lease']='wrong'
        with self.assertRaises(rr.ConflictError):self.issue()
        self.body['lease']=self.job['lease'];self.job['entry_mode']='scene_chat'
        with self.assertRaises(rr.ConflictError):self.issue()
    def test_fixed_options_have_single_category_in_delivered_contract(self):
        for option in ('A','B','C'):
            (self.root/'x.delivery.json').unlink(missing_ok=True)
            envelope = json.loads(self.context['turns'][0]['content'])
            envelope['output_contract']['resolution'] = sp.contract(kind='action', option_id=option)
            envelope['resolution_policy'] = sp.resolution_policy('action', option)
            self.context['turns'][0]['content'] = json.dumps(envelope)
            self.cp.write_text(json.dumps(self.context))
            payload = json.loads(self.issue()['input_text'])
            self.assertEqual(payload['envelope']['output_contract']['resolution']['category'], option)
            policy = payload['envelope']['resolution_policy']['category_policy']
            self.assertEqual(policy['mode'], 'fixed_option')
            self.assertEqual(policy['required_category'], option)
            self.assertIn('禁止重新判档', payload['instruction'])
    def test_custom_and_system_categories_remain_distinct(self):
        self.assertEqual(sp.contract(kind='action', option_id='CUSTOM')['category'], 'A|B|C')
        self.assertEqual(sp.resolution_policy('action', 'CUSTOM')['category_policy']['mode'], 'custom')
        for kind in ('begin','rest','item'):
            self.assertEqual(sp.contract(kind=kind, option_id='C')['category'], 'SYSTEM')
            self.assertIsNone(sp.contract(kind=kind)['conditions'])
    def test_fixed_mismatch_still_rejected_by_production_validator(self):
        value=sp.contract(kind='action',option_id='C');value.update(category='A',basis='这是一次普通问候，不改变原行动。')
        body={'resolution':value,'selection':{'option_id':'C'},'audit':{'reservation':{'status':'held','quote':{'kind':'action'}}}}
        with self.assertRaisesRegex(rr.RoundError,'固定选项不允许模型重新定价'):
            sp.resolution(self.root,{},body)

    def test_format_repair_keeps_first_delivery_receipt(self):
        data=self.issue();proof=self.proof(data);first=proof['read_passes'][0]
        second={'outcome':{'type':'committed','status':'completed','userMessageTimestamp':30,'assistant':{'messageTimestamp':40}},
                'snapshot_message_timestamp':40,'tool_start':0,'tool_count':0}
        proof.update(outcome=second['outcome'],snapshot_message_timestamp=40,read_passes=[first,second],tools=[])
        self.assertTrue(ir.verify(self.service,'x',proof)['required_reads_verified'])
    def test_no_truncation_when_over_limit(self):
        self.raw=ir.encode_live_packet({'body':'文'*750000});(self.root/'packet.txt').write_bytes(self.raw)
        self.context['packet'].update(sha256=rr._digest(self.raw),through_line=len(self.raw.decode().splitlines()));self.cp.write_text(json.dumps(self.context))
        with self.assertRaisesRegex(rr.RoundError,'2MiB'):self.issue()
        self.assertFalse((self.root/'x.delivery.json').exists())

if __name__=='__main__': unittest.main()
"""Execute production reading verifier with isolated authenticated-text fixtures."""
from pathlib import Path
import ast,copy,hashlib,json,re,sys,tempfile,unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
import round_runtime as rr
import story_reading as sr
source=ast.parse((ROOT/'interaction_runtime.py').read_text())
wanted={'packet_read_ranges','required_source_lines','missing_read_target','verify'}
nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in wanted or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LIVE_READ_TOOLS' for t in n.targets)]
space={'json':json,'re':re,'rr':rr,'sr':sr};exec(compile(ast.Module(body=nodes,type_ignores=[]),'interaction_runtime.py','exec'),space)
verify=space['verify'];ranges=space['packet_read_ranges']

class ReadingAuditChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='tmp_step26_test-',dir=ROOT/'scene_chat_dev/tmp');self.root=Path(self.tmp.name)
  self.path='packet.txt';self.raw=('第一行\n第二行\n第三行\n').encode();(self.root/self.path).write_bytes(self.raw)
  self.context={'audit':{},'packet':{'path':self.path,'sha256':rr._digest(self.raw),'through_line':3},'allowed_archive':[],'allowed_memory_reads':[],'required_memory_reads':[]}
  self.cp=self.root/'context.json';self.save()
  self.story=SimpleNamespace(root=self.root,_blob=lambda key,suffix:self.cp,_source_check=lambda context:None,store=SimpleNamespace(_path=lambda p:self.root/p))
  self.proof={'api':'Tools.Chat.sendMessageStreaming','outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':1}},'snapshot_message_timestamp':1,'chat_id':'fixture','participant_id':'fixture','tools':[]}
 def tearDown(self):self.tmp.cleanup()
 def save(self):self.cp.write_text(json.dumps(self.context,ensure_ascii=False))
 def read(self,path=None,begin=1,end=3,strings=False):
  path=path or self.path;lines=(self.root/path).read_text().splitlines()
  return {'name':'read_file_part','parameters':{'path':path,'start_line':str(begin) if strings else begin,'end_line':str(end) if strings else end},'status':'success','result_text':'\n'.join(str(i)+'| '+lines[i-1] for i in range(begin,end+1))}
 def grep(self,path=None):return {'name':'grep_code','parameters':{'path':path or self.path,'pattern':'第二行'},'status':'success','result_text':'2| 第二行'}
 def test_allowed_grep_plus_complete_body_passes(self):
  self.proof['tools']=[self.grep(),self.read(strings=True)];result=verify(self.story,'x',self.proof)
  self.assertNotIn('verified_lines',result['verified_tools'][0]);self.assertEqual(result['verified_tools'][1]['verified_lines'],[1,2,3])
 def test_grep_only_or_missing_page_cannot_count_as_read(self):
  for calls in [[self.grep()],[self.grep(),self.read(end=2)]]:
   self.proof['tools']=calls
   with self.assertRaisesRegex(rr.RoundError,'未完整读取'):verify(self.story,'x',self.proof)
 def test_forbidden_tool_and_directory_search_rejected(self):
  for call in [{'name':'list_files','parameters':{'path':'.'}}, {'name':'write_file','parameters':{'path':self.path}},self.grep('.')]:
   self.proof['tools']=[call,self.read()]
   with self.assertRaises(rr.RoundError):verify(self.story,'x',self.proof)
 def test_non_task_file_and_false_body_rejected(self):
  self.proof['tools']=[self.grep('other.txt'),self.read()]
  with self.assertRaisesRegex(rr.RoundError,'非本任务'):verify(self.story,'x',self.proof)
  call=self.read();call['result_text']='1| forged';self.proof['tools']=[call]
  with self.assertRaisesRegex(rr.RoundError,'未核验'):verify(self.story,'x',self.proof)
 def test_memory_numeric_string_ranges_and_required_coverage(self):
  name=rr.FILES[0];(self.root/name).parent.mkdir(parents=True);(self.root/name).write_text('第一条\n待办约定\n第三条\n')
  ref={'path':name,'start_line':2,'end_line':2};self.context.update(allowed_memory_reads=[ref],required_memory_reads=[ref]);self.save()
  self.proof['tools']=[self.read(),self.read(name,2,2,strings=True)];self.assertTrue(verify(self.story,'x',self.proof)['required_reads_verified'])
  self.proof['tools'][1]=self.read(name,1,2)
  with self.assertRaisesRegex(rr.RoundError,'精确行号'):verify(self.story,'x',self.proof)
  self.proof['tools']=[self.read()]
  with self.assertRaisesRegex(rr.RoundError,'必要记忆源'):verify(self.story,'x',self.proof)
 def test_missing_required_history_rejected_then_full_read_passes(self):
  name='history.json';(self.root/name).write_text('{"record":"original"}')
  self.context.update(allowed_archive=[name],required_history_reads=[name]);self.save();self.proof['tools']=[self.read()]
  with self.assertRaisesRegex(rr.RoundError,'最近剧情原文'):verify(self.story,'x',self.proof)
  self.proof['tools'].append(self.read(name,1,1));self.assertTrue(verify(self.story,'x',self.proof)['required_reads_verified'])
 def test_source_mutation_rejected(self):
  (self.root/self.path).write_text('changed');self.proof['tools']=[self.grep()]
  with self.assertRaisesRegex(rr.ConflictError,'已经改变'):verify(self.story,'x',self.proof)
 def test_read_ranges_cover_long_packet_with_budget_and_tool_headroom(self):
  raw=('\n'.join('数据'+str(i)+'。'*20 for i in range(2400))+'\n').encode()
  planned=ranges(raw);self.assertLess(len(planned),30)
  numbers=[i for item in planned for i in range(item['start_line'],item['end_line']+1)];self.assertEqual(numbers,list(range(1,2401)))
  lines=raw.decode().splitlines()
  for item in planned:
   body='\n'.join(str(i)+'| '+lines[i-1] for i in range(item['start_line'],item['end_line']+1))
   self.assertLessEqual(len(body),9000);self.assertLessEqual(len(body.encode()),24000)
   self.assertEqual(sr.verified_lines(raw,body,item['start_line'],item['end_line']),list(range(item['start_line'],item['end_line']+1)))

if __name__=='__main__':unittest.main()
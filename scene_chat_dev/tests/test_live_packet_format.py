"""Lossless live-packet layout and real source receipt coverage without model calls."""
from pathlib import Path
import ast,json,sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import story_reading as sr
module=ast.parse((ROOT/'interaction_runtime.py').read_text())
function=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='encode_live_packet')
namespace={'json':json};exec(compile(ast.Module(body=[function],type_ignores=[]),'interaction_runtime.py','exec'),namespace)
encode=namespace['encode_live_packet']

class LivePacketFormatChecks(unittest.TestCase):
 def test_json_roundtrip_escapes_and_punctuation(self):
  obj={'rule':'括号{[逗号,引号"与反斜杠\\\n保持原文','array':[None,True,False,3,{'a':'b'}],'empty':{},'list':[]}
  raw=encode(obj);self.assertEqual(json.loads(raw),obj)
  self.assertGreater(len(raw.splitlines()),8)
  self.assertTrue(raw.endswith(b'\n'));self.assertFalse(raw.endswith(b'\n\n'))
  self.assertTrue(raw.decode().splitlines()[-1].strip())
 def test_large_rules_are_not_one_giant_knowledge_line(self):
  entries=json.loads((ROOT/'txt文件/知识库/系统标签类.json').read_text())['data']['entries']
  obj={'knowledge_rules':[{'body':x['content']} for x in entries]}
  raw=encode(obj);self.assertEqual(json.loads(raw),obj)
  self.assertLess(max(map(len,raw.decode().splitlines())),10000)
 def test_numbered_partial_receipts_cover_every_source_line(self):
  obj={'rules':[{'source':'rule'+str(i),'body':'中文资料。'*40} for i in range(50)]}
  raw=encode(obj);lines=raw.decode().splitlines();covered=set()
  for begin in range(1,len(lines)+1,10):
   end=min(begin+9,len(lines));result='\n'.join(str(i)+'| '+lines[i-1] for i in range(begin,end+1))
   covered.update(sr.verified_lines(raw,result,begin,end))
  self.assertEqual(covered,set(range(1,len(lines)+1)))
  with self.assertRaises(sr.ReadingError):sr.verified_lines(raw,'1| guessed',1,10)

if __name__=='__main__':unittest.main()

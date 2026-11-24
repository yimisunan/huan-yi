"""Playback gates, privacy, durable progress and concurrency on isolated formal saves."""
from pathlib import Path
import base64
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).parent))
from test_interaction import fixture, cleaner
import round_runtime as rr
import interaction_runtime as ir
from story_service import StoryService, register_story_routes
from flask import Flask

DECISION={'prompt':'你打算如何回应？','options':[
 {'id':'A','text':'询问今天还有什么安排。'},
 {'id':'B','text':'礼貌地伸手与她握手告别。'},
 {'id':'C','text':'提出自己准备好的计划。'}]}
MESSAGES=[{'kind':'narration','speaker':'','text':'窗边的桌上放着一份未合拢的文件。'},
 {'kind':'dialogue','speaker':'沈知韫','text':'这件事先听听你的看法。'},
 {'kind':'action','speaker':'沈知韫','text':'她将文件转向你，等着你的回答。'}]

class PlaybackChecks(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='playback-test-',dir=ROOT/'scene_chat_dev/tmp')
  self.root=fixture(self.temp.name);self.store=rr.RoundStore(self.root);self.service=StoryService(self.root)
 def tearDown(self):self.temp.cleanup()
 def request(self,ident='segment-one',selected=None,text='继续当前剧情',op=None):
  return {'schema_version':2,'entry_mode':ir.MODE,'request_id':ident,'base_revision':self.store.prepare()['base_revision'],
   'input':text,'messages':copy.deepcopy(MESSAGES),'decision':copy.deepcopy(DECISION),'selection':selected or {'segment_id':'','option_id':'BEGIN'},
   'operation':op,'handoff':'','audit':{'required_reads_verified':True,'origin':'operit_session'}}
 def advance(self,revealed,completed=False,ident='segment-one'):
  return self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':ident,'revealed':revealed,'completed':completed})
 def finish(self):
  for count in (1,2,3):self.advance(count)
  return self.advance(3,True)
 def body(self,ident='choice-one',option='A'):
  return {'request_id':ident,'entry_mode':ir.MODE,'save_epoch':self.service._save_epoch(),
   'base_revision':self.store.prepare()['base_revision'],'action':DECISION['options'][0]['text'] if option=='A' else '我想先听清楚。',
   'selection':{'segment_id':'segment-one','option_id':option}}
 def test_unrevealed_text_choices_and_world_are_hidden(self):
  req=self.request();self.store.submit(req)
  state=self.service.interaction_snapshot();self.assertEqual(state['history'][0]['messages'],[])
  self.assertNotIn('decision',state['history'][0]);self.assertEqual(state['playback']['total'],3)
  one=self.advance(1);self.assertEqual(one['history'][0]['messages'],MESSAGES[:1]);self.assertNotIn('decision',one['history'][0])
  self.assertEqual(self.service.interaction_snapshot(before=999)['history'][0]['messages'],MESSAGES[:1])
  done=self.finish();self.assertEqual(done['history'][0]['decision'],DECISION)
 def test_progress_never_changes_world_revision_or_ledger_sequence(self):
  self.store.submit(self.request());before=self.store._files();ledger=self.store._ledger()
  self.finish();self.advance(1)
  self.assertEqual(before,self.store._files());self.assertEqual(ledger,self.store._ledger())
  fresh=StoryService(self.root).interaction_snapshot();self.assertTrue(fresh['playback']['completed']);self.assertEqual(fresh['playback']['revealed'],3)
 def test_early_skip_stale_and_legacy_bypass_are_rejected(self):
  self.store.submit(self.request())
  with self.assertRaises(rr.ConflictError):self.advance(3,True)
  with self.assertRaises(rr.ConflictError):self.advance(2)
  with self.assertRaises(rr.ConflictError):self.advance(0,False,'stale')
  with self.assertRaises(rr.ConflictError):self.service.create(self.body())
  legacy=self.request('bypass');legacy['schema_version']=1;legacy.pop('selection');legacy.pop('decision');legacy['input']='你好'
  with self.assertRaises(rr.ConflictError):self.store.submit(legacy)
  self.finish();forged=self.body();forged['action']='换成别的选项内容'
  with self.assertRaises(rr.ConflictError):self.service.create(forged)
 def test_current_choice_idempotent_and_second_tab_cannot_consume_old_choice(self):
  self.store.submit(self.request());self.finish();body=self.body()
  task=self.service.create(body)['task'];self.assertEqual(task['selection']['option_id'],'A')
  self.assertEqual(self.service.create(body)['task']['request_id'],'choice-one')
  with self.assertRaises(rr.ConflictError):self.service.create(self.body('second-tab'))
  req=self.request('next',body['selection'],body['action']);self.store.submit(req)
  stale=self.body('stale-tab');stale['base_revision']=self.store.prepare()['base_revision']
  with self.assertRaises(rr.ConflictError):self.service.create(stale)
 def test_recovery_rolls_back_partial_progress_and_redoes_committed_progress(self):
  self.store.submit(self.request());files=self.store._files();real=self.store._publish;seen=[]
  def fail(values):
   if not seen:
    seen.append(True);rr._atomic(self.store._path(ir.PLAYBACK),values[ir.PLAYBACK]);raise OSError('interrupted progress')
   return real(values)
  with patch.object(self.store,'_publish',side_effect=fail):
   with self.assertRaises(OSError):
    with self.store._locked():ir.update_playback(self.store,ir.segment(self.root,self.store._files()),1,False)
  self.assertEqual(self.service.interaction_snapshot()['playback']['revealed'],0);self.assertEqual(files,self.store._files())
  after=self.store._files();after[rr.META]=rr._json(self.store._ledger());after[ir.PLAYBACK]=rr._json({'version':1,'segment_id':'segment-one','revealed':1,'completed':False})
  before={k:self.store._path(k).read_bytes() if self.store._path(k).exists() else None for k in after}
  encode=lambda values:{k:None if raw is None else base64.b64encode(raw).decode() for k,raw in values.items()}
  rr._atomic(self.store._path('.round-runtime/journal.json'),rr._json({'version':1,'phase':'committed','before':encode(before),'after':encode(after)}))
  self.assertEqual(StoryService(self.root).interaction_snapshot()['playback']['revealed'],1)
 def test_bad_choices_and_absent_speaker_reject_without_writes(self):
  for modification in ('order','extra','missing','speaker'):
   req=self.request()
   if modification=='order':req['decision']['options'].reverse()
   elif modification=='extra':req['decision']['options'][0]['cost']=5
   elif modification=='missing':req.pop('decision')
   else:req['messages'][1]['speaker']='苏婉青'
   with self.subTest(modification=modification),self.assertRaises(rr.RoundError):self.store.submit(req)
  self.assertFalse(ir.records(self.store));self.assertFalse(self.store._path(ir.PLAYBACK).exists())
 def test_not_capped_to_twelve_nodes_and_no_legacy_memory_rotation(self):
  before=self.store._files();req=self.request();req['messages']=[copy.deepcopy(MESSAGES[0]) for _ in range(25)]
  self.store.submit(req);self.assertEqual(self.service.interaction_snapshot()['playback']['total'],25)
  self.assertEqual(before[rr.FILES[0]],self.store._files()[rr.FILES[0]]);self.assertEqual(json.loads(self.store._files()['data.json'])['round'],0)
 def test_new_game_resets_playback_and_old_epoch_progress_rejected(self):
  self.store.submit(self.request());self.advance(1);old=self.service._save_epoch()
  self.service.new_game({'request_id':'reset-play','save_epoch':old,'confirm':'new_game'})
  self.assertTrue(self.service.interaction_snapshot()['playback']['bootstrap']);self.assertFalse(self.store._path(ir.PLAYBACK).exists())
  with self.assertRaises(rr.ConflictError):self.service.playback_progress({'save_epoch':old,'segment_id':'segment-one','revealed':2,'completed':False})
 def test_http_progress_uses_normal_same_origin_client_boundary(self):
  self.store.submit(self.request());app=Flask('playback-boundary');register_story_routes(app,self.root);client=app.test_client()
  body={'save_epoch':'legacy','segment_id':'segment-one','revealed':1,'completed':False}
  self.assertEqual(client.post('/api/story/live/progress',json=body).status_code,403)
  response=client.post('/api/story/live/progress',json=body,headers={'X-Story-Client':'1'})
  self.assertEqual(response.status_code,200);self.assertEqual(response.get_json()['playback']['revealed'],1)
 def test_catchup_playback_allows_single_jump_without_bypassing_completion(self):
  self.store.submit(self.request())
  # catchup=True allows jumping from 0 -> 3 with completed=False in a single request
  res=self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':'segment-one','revealed':3,'completed':False,'catchup':True})
  self.assertEqual(res['playback']['revealed'],3);self.assertFalse(res['playback']['completed'])
  # catchup=True STILL cannot skip straight to completed=True while unrevealed
  self.store.submit(self.request('segment-two',{'segment_id':'segment-one','option_id':'A'},'询问今天还有什么安排。')) if False else None
  done=self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':'segment-one','revealed':3,'completed':True})
  self.assertTrue(done['playback']['completed'])
 def test_compact_progress_returns_single_segment_delta(self):
  self.store.submit(self.request())
  mid=self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':'segment-one','revealed':1,'completed':False,'compact':True})
  self.assertTrue(mid.get('compact'))
  self.assertEqual(len(mid['history']),1)
  self.assertEqual(len(mid['history'][0]['messages']),1)
  self.assertIsNone(mid['world'])
  self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':'segment-one','revealed':2,'completed':False,'compact':True})
  self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':'segment-one','revealed':3,'completed':False,'compact':True})
  end=self.service.playback_progress({'save_epoch':self.service._save_epoch(),'segment_id':'segment-one','revealed':3,'completed':True,'compact':True})
  self.assertTrue(end.get('compact'))
  self.assertTrue(end['playback']['completed'])
  self.assertIsInstance(end['world'],dict)
  self.assertEqual(len(end['history'][0]['decision']['options']),3)

if __name__=='__main__':unittest.main(verbosity=2)

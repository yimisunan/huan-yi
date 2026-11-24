"""Registered opening and reset-journal acceptance on disposable saves."""
from pathlib import Path
import importlib.util,json,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from test_interaction import fixture,cleaner
from story_service import StoryService
import round_runtime as rr
import interaction_runtime as ir
import story_progression as sp
spec=importlib.util.spec_from_file_location('opening',ROOT/'存档开局随机盲盒.py');opening=importlib.util.module_from_spec(spec);spec.loader.exec_module(opening)

class PrologueChecks(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='tmp_step22_case-',dir=ROOT/'scene_chat_dev/tmp');self.root=fixture(self.temp.name,progression=True);self.service=StoryService(self.root);self.store=self.service.store
 def tearDown(self):self.temp.cleanup()
 def initialize(self,scenario=None):
  with self.store._locked():return opening.initialize_prologue(self.root,'new-save',scenario)
 def test_all_eight_scenarios_are_deterministic_valid_and_nonmutating(self):
  original=json.dumps(opening.SCENARIOS,ensure_ascii=False)
  self.assertEqual(len(opening.SCENARIOS),8)
  for scenario in opening.SCENARIOS:
   value=opening.choose_opening('same-id',scenario['id']);self.assertEqual(value,opening.choose_opening('same-id',scenario['id']));self.assertEqual(value['clock']['day'],1);self.assertEqual(len(value['messages']),3);self.assertNotIn('角色设定',value['messages'][0]['text']);self.assertNotIn('席间礼貌与暗流并存',value['messages'][0]['text']);self.assertTrue(any(tok in value['messages'][0]['text'] for tok in ('足背','脚踝','36D','腕骨','指节','锁骨','后颈')));ir.decision(value['decision']);self.assertIn(value['messages'][-1]['speaker'],value['presence']);self.assertIn(value['clock']['time'],opening.OPENING_TIMES[scenario['id']]);self.assertTrue(all(place in ir.policy(self.root)['locations'] for place,reason in value['presence'].values()))
  self.assertEqual(json.dumps(opening.SCENARIOS,ensure_ascii=False),original)
 def test_prologue_hidden_until_played_and_first_choice_costs_five(self):
  self.initialize('nianwei_saturday_studio');snap=self.service.interaction_snapshot();self.assertFalse(snap['playback']['completed']);self.assertEqual(snap['history'][-1]['messages'],[]);self.assertNotIn('decision',snap['history'][-1]);self.assertEqual(snap['world']['progression']['runtime']['last_closed'],0);self.assertEqual(snap['world']['progression']['runtime']['clock']['time'],'01:00')
  row=ir.segment(self.root,self.store._files());body={'request_id':'first-choice','entry_mode':ir.MODE,'save_epoch':snap['save_epoch'],'base_revision':snap['revision'],'action':row['decision']['options'][0]['text'],'selection':{'segment_id':row['id'],'option_id':'A'}}
  with self.assertRaises(rr.ConflictError):self.service.create(body)
  for i in range(1,4):self.service.playback_progress({'save_epoch':snap['save_epoch'],'segment_id':row['id'],'revealed':i,'completed':False})
  self.service.playback_progress({'save_epoch':snap['save_epoch'],'segment_id':row['id'],'revealed':3,'completed':True});self.service.create(body);self.assertEqual(sp.stamina(self.root,self.store._files()),95);self.assertEqual(sp.state(self.root,self.store._files())['last_closed'],0)
 def test_idempotent_prologue_never_overwrites_an_existing_game(self):
  self.initialize();before=self.store._files();progress=(self.root/ir.PLAYBACK).read_bytes();self.assertTrue(self.initialize()['replayed']);self.assertEqual(before,self.store._files());self.assertEqual(progress,(self.root/ir.PLAYBACK).read_bytes())
  with self.store._locked():
   with self.assertRaises(rr.ConflictError):opening.initialize_prologue(self.root,'different')
  self.assertEqual(before,self.store._files())
 def test_new_game_api_same_id_preserves_selected_prologue_and_epoch(self):
  self.initialize();body={'request_id':'reset-one','save_epoch':self.service._save_epoch(),'confirm':'new_game'};first=self.service.new_game(body);snapshot=self.store._files();again=self.service.new_game(body);self.assertFalse(first['replayed']);self.assertTrue(again['replayed']);self.assertEqual(first['save_epoch'],again['save_epoch']);self.assertEqual(snapshot,self.store._files());self.assertTrue(json.loads(snapshot['data.json'])['prologue']);self.assertFalse(self.service.interaction_snapshot()['playback']['completed'])
 def test_reset_failure_inside_prologue_restores_all_prior_sources(self):
  self.initialize();before=self.store._files();history=(self.root/ir.ARCHIVE/'000000000001.json').read_bytes()
  original=rr.RoundStore._commit_files
  def fail(store,values):
   if 'prologue' in json.loads(values.get('data.json') or b'{}'):raise OSError('injected opening failure')
   return original(store,values)
  with patch.object(rr.RoundStore,'_commit_files',fail):
   with self.assertRaises(OSError):self.service.new_game({'request_id':'reset-fail','save_epoch':self.service._save_epoch(),'confirm':'new_game'})
  self.assertEqual(before,self.store._files());self.assertEqual(history,(self.root/ir.ARCHIVE/'000000000001.json').read_bytes());self.assertFalse((self.root/cleaner.TX).exists())
 def test_opening_commit_journal_rolls_back_partial_published_files(self):
  before=self.store._files();publish=rr.RoundStore._publish;calls=0
  def fail_once(store,values):
   nonlocal calls;calls+=1
   if calls==1:
    rr._atomic(store.root/rr.FILES[0],values[rr.FILES[0]]);raise OSError('partial publish')
   return publish(store,values)
  with patch.object(rr.RoundStore,'_publish',fail_once):
   with self.assertRaises(OSError):self.initialize()
  self.store.recover();self.assertEqual(before,self.store._files());self.assertFalse(ir.records(self.store))

if __name__=='__main__':unittest.main()

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
 def test_all_ten_scenarios_are_deterministic_valid_hygienic_and_nonmutating(self):
  original=json.dumps(opening.SCENARIOS,ensure_ascii=False)
  self.assertEqual(len(opening.SCENARIOS),10)
  self.assertIn('nianwei_rain_studio',{s['id'] for s in opening.SCENARIOS})
  self.assertIn('zhiyun_late_office',{s['id'] for s in opening.SCENARIOS})
  banned_cliches=('喉结不受控','喉结滚','掌心发烫','嗓子发干','吞咽声')
  banned_opt_b=('按揉','脚踝','赤足','扶吊带','擦锁骨','吻','贴着她腰')
  for scenario in opening.SCENARIOS:
   value=opening.choose_opening('same-id',scenario['id'])
   self.assertEqual(value,opening.choose_opening('same-id',scenario['id']))
   self.assertEqual(value['clock']['day'],1)
   self.assertEqual(len(value['messages']),3)
   body=value['messages'][0]['text']
   self.assertNotIn('角色设定',body)
   self.assertNotIn('席间礼貌与暗流并存',body)
   for bad in banned_cliches:
    self.assertNotIn(bad,body,f"{scenario['id']} still contains banned cliché {bad}")
   self.assertTrue(any(tok in body for tok in ('足背','脚踝','36D','腕骨','指节','锁骨','后颈')))
   ir.decision(value['decision'])
   opt_b=value['decision']['options'][1]['text']
   for bad_b in banned_opt_b:
    self.assertNotIn(bad_b,opt_b,f"{scenario['id']} Option B violates daily etiquette: {bad_b}")
   self.assertIn(value['messages'][-1]['speaker'],value['presence'])
   self.assertIn(value['clock']['time'],opening.OPENING_TIMES[scenario['id']])
   self.assertTrue(all(place in ir.policy(self.root)['locations'] for place,reason in value['presence'].values()))
   self.assertTrue(value.get('present_actors'))
   self.assertTrue(set(value['present_actors']).issubset(set(value['presence'].keys())))
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
  self.initialize();body={'request_id':'reset-one','save_epoch':self.service._save_epoch(),'confirm':'new_game'};first=self.service.new_game(body);snapshot=self.store._files();again=self.service.new_game(body);self.assertFalse(first['replayed']);self.assertTrue(again['replayed']);self.assertEqual(first['save_epoch'],again['save_epoch']);self.assertEqual(snapshot,self.store._files());self.assertTrue(json.loads(snapshot['data.json'])['prologue']);self.assertTrue(again.get('prologue'));self.assertFalse(self.service.interaction_snapshot()['playback']['completed'])
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
 def test_room_known_by_isolation_and_scene_world_p2_parsing(self):
  import save_store,scene_world
  # zhiyun_friday_study is in 徐家主宅 (沈知韫 + 徐念薇 both in house) but only 沈知韫 is in the study
  self.initialize('zhiyun_friday_study')
  st,ly,rc=save_store.load_bundle(self.root)
  self.assertEqual(st['intimate']['present_actors'],['沈知韫'])
  self.assertEqual(ly['episodes'][0]['known_by'],['徐志北','沈知韫'])
  self.assertNotIn('徐念薇',ly['episodes'][0]['known_by'])
  seg=ir.segment(self.root,self.store._files())
  self.assertEqual(seg['known_by'],['徐志北','沈知韫'])
  import shutil
  vis_dst=self.root/'scene_chat_dev/src/legacy_visibility.json'
  vis_dst.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(ROOT/'scene_chat_dev/src/legacy_visibility.json',vis_dst)
  lw=scene_world.LegacyWorld(self.root)
  world=lw.parse(lw.sources())
  self.assertEqual(world['memories'][0]['known_by'],['徐志北','沈知韫'])
  self.assertEqual([x for x in world.get('issues',[]) if 'unresolved' in str(x) or 'memory_visibility' in str(x)],[])
 def test_cleaner_full_cleanup_slim_slots_roundtrip_and_reroll_only(self):
  import save_store
  self.initialize('zhiyun_sunday_noon')
  # Plant stale caches & temp files that cleaner MUST sweep
  story_dir=self.root/'.round-runtime/story';story_dir.mkdir(parents=True,exist_ok=True)
  stage1=story_dir/('a'*64+'.stage1.json');stage1.write_text('{}',encoding='utf-8')
  inquiries=story_dir/'shop_inquiries.json';inquiries.write_text('{}',encoding='utf-8')
  tmp_ss=self.root/'存档/.ss-tmp-stale';tmp_ss.write_text('tmp',encoding='utf-8')
  reading_dir=self.root/'.story-reading';reading_dir.mkdir(parents=True,exist_ok=True)
  (reading_dir/'big.txt').write_text('X'*50000,encoding='utf-8')
  ctx_blob=story_dir/('b'*64+'.context.json');ctx_blob.write_text('Y'*50000,encoding='utf-8')

  # Manual snapshot via StoryService must be slim (excludes .story-reading and .context.json)
  snap_res=self.service.snapshot_save({'save_epoch':self.service._save_epoch(),'label':'周日正午留档'})
  slot_id=snap_res['slot']['id']
  slot_files_root=self.root/cleaner.SAVE_SLOTS/slot_id/'files'
  self.assertFalse((slot_files_root/'.story-reading').exists())
  self.assertFalse(any(p.name.endswith('.context.json') for p in slot_files_root.rglob('*')))

  # Zero-action reroll_only creates NO new backup slot and switches to a different scenario
  before_slots=len(self.service.list_saves()['slots'])
  reroll_res=self.service.new_game({'request_id':'reroll-1','save_epoch':self.service._save_epoch(),'confirm':'new_game','reroll_only':True})
  self.assertTrue(reroll_res['reroll_only'])
  self.assertIsNone(reroll_res['slot'])
  self.assertEqual(len(self.service.list_saves()['slots']),before_slots)
  self.assertNotEqual(reroll_res['prologue']['scenario_id'],'zhiyun_sunday_noon')
  self.assertFalse(stage1.exists())
  self.assertFalse(inquiries.exists())
  self.assertFalse(tmp_ss.exists())

  # Switch explicitly to new scenario nianwei_rain_studio
  pick_res=self.service.new_game({'request_id':'pick-studio','save_epoch':self.service._save_epoch(),'confirm':'new_game','scenario_id':'nianwei_rain_studio'})
  self.assertEqual(pick_res['prologue']['scenario_id'],'nianwei_rain_studio')
  st_studio,_,_=save_store.load_bundle(self.root)
  self.assertEqual(st_studio['presence']['徐志北']['location'],'工作室')

  # Restore back to manual slot zhiyun_sunday_noon losslessly
  restore_res=self.service.restore_save({'save_epoch':self.service._save_epoch(),'slot_id':slot_id,'confirm':'restore_save','request_id':'rest-1'})
  self.assertEqual(restore_res['status'],'restored')
  self.assertEqual(restore_res['summary']['scenario_id'],'zhiyun_sunday_noon')
  st_back,_,_=save_store.load_bundle(self.root)
  self.assertEqual(st_back['presence']['徐志北']['location'],'徐家主宅')

  # Delete slot removes it cleanly
  del_res=self.service.delete_save(slot_id,{'save_epoch':self.service._save_epoch()})
  self.assertEqual(del_res['status'],'deleted')
  self.assertNotIn(slot_id,[s['id'] for s in del_res['slots']])

  # Once actions > 0, reroll_only must reject with ConflictError
  data_path=self.root/'data.json'
  d=json.loads(data_path.read_text(encoding='utf-8'))
  d.setdefault('interaction',{})['actions']=2
  data_path.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
  with self.assertRaises(rr.ConflictError):
   self.service.new_game({'request_id':'reroll-blocked','save_epoch':self.service._save_epoch(),'confirm':'new_game','reroll_only':True})

if __name__=='__main__':unittest.main()

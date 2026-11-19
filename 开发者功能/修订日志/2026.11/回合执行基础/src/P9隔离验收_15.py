"""P9 acceptance against disposable synthetic projects; no Flask/model/TTS required."""
from pathlib import Path
import argparse
import ast
import base64
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

parser = argparse.ArgumentParser()
parser.add_argument('--installed', action='store_true')
args = parser.parse_args()
sys.dont_write_bytecode = True
root = Path.cwd().resolve()
base = root / '开发者功能/修订日志/2026.11/回合执行基础'
manifest = json.loads((base / 'src/安装清单_15.json').read_bytes())
changes = {c['path']: c for c in manifest['changes']}
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def source(rel):
    c = changes.get(rel)
    return (root / c['staged']).read_bytes() if c and not args.installed else (root / rel).read_bytes()

rr = types.ModuleType('round_runtime')
rr.__file__ = str(root / 'round_runtime.py')
sys.modules['round_runtime'] = rr
exec(compile(source('round_runtime.py'), rr.__file__, 'exec'), rr.__dict__)
fixture_tree = ast.parse((root / '开发者功能/开发者工具/回合执行验收.py').read_bytes())
fixtures = {'rr': rr}
exec(compile(ast.Module(body=[n for n in fixture_tree.body if isinstance(n, ast.FunctionDef) and n.name in {'memory','syslog'}], type_ignores=[]), '<existing synthetic fixtures>', 'exec'), fixtures)
work = Path(tempfile.mkdtemp(prefix='tmp_p9_tests15_', dir=base/'tmp'))
live_files = {rel: (root/rel).read_bytes() for rel in rr.FILES}
tracked = dict(manifest['protected'])
tracked.update({c['path']: c['after' if args.installed else 'before'] for c in manifest['changes']})
for rel, info in tracked.items():
    assert sha((root/rel).read_bytes()) == info['sha256'], rel


def condition(**changes):
    value = {'intensity':'A', 'effective_progress':False, 'scene':'客厅', 'npc':'沈知韫',
             'action_changed':False, 'stress_signals':0, 'breakout_triggered':[]}
    value.update(changes)
    return value


class Cases(unittest.TestCase):
    count = 0
    def setUp(self):
        Cases.count += 1
        self.project = work / str(Cases.count)
        self.project.mkdir()
        for rel in ('injection_core.py','round_runtime.py','txt文件/一键注入指南.txt','story_service.py',
                    'txt文件/全局执行法典.md','txt文件/提示词.md','txt文件/故事检索索引.md',
                    'txt文件/知识库/世界观类.json','txt文件/知识库/角色类.json',
                    'txt文件/知识库/叙事判断.json','txt文件/知识库/系统标签类.json'):
            path = self.project/rel; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(source(rel))
        for rel,text in ((rr.FILES[0],fixtures['memory']()),(rr.FILES[1],'▼ 已过期/已消耗道具历史区 ▼\n'),
                         (rr.FILES[2],'静态NPC名册\n'),('data.json','{"round":0,"storyNodes":[]}')):
            path=self.project/rel; path.parent.mkdir(exist_ok=True,parents=True); path.write_text(text)
        self.store=rr.RoundStore(self.project)
        self.serial=0

    def memory(self): return (self.project/rr.FILES[0]).read_text()
    def write_memory(self, text): (self.project/rr.FILES[0]).write_text(text)
    def counts(self): return rr._counters(self.memory())
    def states(self): return rr._current_micro(self.memory())
    def meta(self): return rr._lifecycle_meta(self.memory(), self.store.prepare()['current_round']-1)
    def snapshot(self):
        return {p.relative_to(self.project).as_posix():p.read_bytes() for p in self.project.rglob('*')
                if p.is_file() and (p.relative_to(self.project).as_posix() in (*rr.FILES,rr.META) or p.parent.name=='日志')}
    def panel(self, name, attr):
        line=re.search(r'^\['+re.escape(name)+r'\]([^\n]*)',self.memory(),re.M)[1]
        return int(re.search(re.escape(attr)+r'\s*(-?\d+)',line)[1])
    def seed_panel(self, name, **values):
        text=self.memory(); pat=r'^\['+re.escape(name)+r'\][^\n]*'
        line=re.search(pat,text,re.M)[0]
        for key,value in values.items(): line=re.sub(r'('+re.escape(key)+r'\s*)-?\d+',lambda m:m[1]+str(value),line,count=1)
        self.write_memory(re.sub(pat,lambda _:line,text,count=1,flags=re.M))
    def seed_count(self, **values):
        counts=self.counts(); counts.update(values); self.write_memory(rr._write_counters(self.memory(),counts))
    def request(self, cond='default', **fields):
        prepared=self.store.prepare(); self.serial+=1; number=prepared['current_round']
        deltas={'l1_new_round':'中性验收场景中，徐志北整理客厅桌边材料，沈知韫要求先核对版本，后续附件尚待确认。'}
        for key,sources in prepared['summary_sources'].items():
            if sources:
                if key=='l1_to_l2_condensed':
                    label=re.match(r'【[^】]+】',sources[0])[0]
                else:
                    engine=rr._engine(self.project,self.project)
                    start=engine._memory_item_range(sources[0])[0]; end=engine._memory_item_range(sources[-1])[1]
                    label='【'+str(start)+'-'+str(end)+'】'
                deltas[key]=label+'材料核对仍待处理，保留顺序与疑点。'
        if cond is not None: deltas['round_conditions']=condition() if cond=='default' else cond
        req={'schema_version':1,'request_id':'case-'+str(Cases.count)+'-'+str(self.serial),
             'base_revision':prepared['base_revision'],'current_round':number,
             'story_nodes':[{'type':'header','text':'7月22日, 周三, 客厅, 08:10'},
                            {'type':'narration','text':'你把纸页放在桌上，指腹擦过页角，听见笔帽轻响。'},
                            {'type':'dialogue','speaker':'沈知韫','text':'先核版本，疑点留在页边。'}],
             'memory_deltas':deltas,'panel_changes':{},'system_log':fixtures['syslog'](number),
             'options_text':'[A. 日常]：继续核材料。\n[B. 社交]：询问附件位置。\n[C. 主动]：提出新顺序。'}
        req.update(fields); return req
    def commit(self, cond='default', **fields):
        req=self.request(cond,**fields); receipt=self.store.submit(req); return req,receipt
    def reject(self, req, exc=rr.RoundError):
        before=self.snapshot()
        with self.assertRaises(exc): self.store.submit(req)
        self.assertEqual(before,self.snapshot())
    def log(self): return sorted((self.project/'日志').glob('*.txt'),key=lambda p:p.stat().st_mtime_ns)[-1].read_text()

    def test_01_enter_and_omitted_expiry(self):
        self.commit(micro_state_changes={'沈知韫':{'momentary_ease':True,'residual_tension':True}})
        self.assertTrue(self.states()['沈知韫']['momentary_ease']); self.assertEqual(1,self.meta()['micro']['沈知韫']['momentary_ease']['observed_round'])
        self.commit(); self.assertFalse(self.states()['沈知韫']['momentary_ease']); self.assertFalse(self.states()['沈知韫']['residual_tension'])
    def test_02_repeated_true_does_not_extend(self):
        for expected in (True,False,True):
            self.commit(micro_state_changes={'沈知韫':{'momentary_ease':True}})
            self.assertEqual(expected,self.states()['沈知韫']['momentary_ease'])
    def test_03_confusion_two_snapshots(self):
        self.commit(micro_state_changes={'沈知韫':{'confusion_debt':True}})
        self.commit(micro_state_changes={'沈知韫':{'confusion_debt':True}})
        self.assertTrue(self.states()['沈知韫']['confusion_debt'])
        self.commit(micro_state_changes={'沈知韫':{'confusion_debt':True}})
        self.assertFalse(self.states()['沈知韫']['confusion_debt'])
    def test_04_confusion_c_transfer(self):
        self.commit(micro_state_changes={'沈知韫':{'confusion_debt':True}})
        self.commit(condition(intensity='C'))
        self.assertFalse(self.states()['沈知韫']['confusion_debt']); self.assertTrue(self.states()['沈知韫']['residual_tension'])
        self.commit(); self.assertFalse(self.states()['沈知韫']['residual_tension'])
    def test_05_explicit_exit(self):
        self.commit(micro_state_changes={'沈知韫':{'confusion_debt':True}})
        self.commit(micro_state_changes={'沈知韫':{'confusion_debt':False}})
        self.assertFalse(self.states()['沈知韫']['confusion_debt'])
    def test_06_character_blocks_do_not_leak(self):
        self.commit(micro_state_changes={'沈知韫':{'momentary_ease':True},'苏婉青':{'confusion_debt':True}})
        s=self.states(); self.assertFalse(s['徐念薇']['momentary_ease']); self.assertFalse(s['沈知韫']['confusion_debt']); self.assertTrue(s['苏婉青']['confusion_debt'])
    def test_07_legacy_true_observation(self):
        s=rr._current_micro(self.memory()); s['苏婉青']['momentary_ease']=True
        self.write_memory(rr._write_micro(self.memory(),s)); self.commit()
        self.assertTrue(self.states()['苏婉青']['momentary_ease']); self.assertEqual('legacy_observed',self.meta()['micro']['苏婉青']['momentary_ease']['origin'])
        self.assertIn('旧true首次观测保留',self.log()); self.commit(); self.assertFalse(self.states()['苏婉青']['momentary_ease'])
    def test_08_missing_micro_block(self):
        text=re.sub(r'【当前激活微状态】.*?(?=^={5,})','',self.memory(),flags=re.M|re.S)
        self.write_memory(text); self.commit(micro_state_changes={'徐念薇':{'momentary_ease':True}})
        self.assertTrue(self.states()['徐念薇']['momentary_ease'])
    def test_09_daily_scope_counter(self):
        for n in range(1,6):
            self.commit(); self.assertEqual(n,self.counts()['破局_日常冗余'])
        self.assertEqual(5,self.counts()['破局_日常冗余']); self.assertIn('counter_values',self.log())
    def test_10_progress_resets(self):
        self.commit(); self.commit(condition(effective_progress=True))
        self.assertTrue(all(self.counts()[k]==0 for k in rr.BREAKOUT_LIMITS))
    def test_11_scene_scope_switch(self):
        self.commit(); self.commit(); self.assertEqual(2,self.counts()['破局_模式重复'])
        self.commit(condition(scene='书房')); self.assertEqual(1,self.counts()['破局_模式重复']); self.assertEqual(3,self.counts()['破局_社交淤积'])
    def test_12_npc_scope_switch(self):
        self.commit(); self.commit(); self.commit(condition(npc='徐念薇'))
        self.assertEqual(1,self.counts()['破局_模式重复']); self.assertEqual(1,self.counts()['破局_社交淤积'])
    def test_13_intensity_and_action_switch(self):
        self.commit(); self.commit(condition(intensity='B')); self.assertEqual(0,self.counts()['破局_日常冗余']); self.assertEqual(1,self.counts()['破局_模式重复'])
        self.commit(condition(intensity='B',action_changed=True)); self.assertEqual(0,self.counts()['破局_模式重复'])
    def test_14_shame_boundary(self):
        self.seed_panel('沈知韫',羞耻=80); self.commit(); self.assertEqual(0,self.counts()['破局_社交淤积'])
        self.seed_panel('沈知韫',羞耻=81); self.commit(); self.assertEqual(1,self.counts()['破局_社交淤积'])
    def test_15_tension_streak(self):
        for expected in (1,2):
            self.commit(condition(intensity='B',stress_signals=1)); self.assertEqual(expected,self.counts()['破局_张力淤积'])
        self.commit(condition(intensity='A')); self.assertEqual(0,self.counts()['破局_张力淤积'])
    def test_16_actual_breakout_resets_only_named(self):
        self.commit(); self.commit(condition(breakout_triggered=['破局_模式重复']))
        self.assertEqual(0,self.counts()['破局_模式重复']); self.assertEqual(2,self.counts()['破局_日常冗余'])
    def test_17_guard_five_and_idempotence(self):
        for n in range(4): self.commit()
        self.assertEqual(7,self.panel('系统宿主','积分'))
        req,receipt=self.commit(host_events=[rr.GUARD_TAG]); self.assertEqual(12,self.panel('系统宿主','积分')); self.assertEqual(6,self.panel('系统宿主','经验值')); self.assertEqual(0,self.counts()['连续守护回合'])
        before=self.snapshot(); self.assertTrue(self.store.submit(req)['replayed']); self.assertEqual(before,self.snapshot())
    def test_18_guard_c_interrupts(self):
        self.commit(); self.commit(condition(intensity='C')); self.assertEqual(0,self.counts()['连续守护回合'])
    def test_19_guard_tracks_still_compete(self):
        for n in range(4): self.commit()
        self.commit(host_events=['商业_战略突破']); self.assertEqual(27,self.panel('系统宿主','积分')); self.assertEqual(23,self.panel('系统宿主','经验值')); self.assertEqual(0,self.counts()['连续守护回合'])
    def test_20_guard_early_rejected(self): self.reject(self.request(host_events=[rr.GUARD_TAG]))
    def test_21_exhaust_second_and_duplicate(self):
        self.seed_panel('沈知韫',欲望=75)
        self.commit(); self.assertEqual(1,self.counts()['空耗_连续未纾解_沈知韫']); self.assertEqual(100,self.panel('沈知韫','体力'))
        self.commit(ds_events={'沈知韫':[rr.EXHAUST_TAG]}); self.assertEqual(0,self.counts()['空耗_连续未纾解_沈知韫']); self.assertEqual(95,self.panel('沈知韫','体力'))
    def test_22_exhaust_independent_npcs(self):
        self.seed_panel('沈知韫',欲望=75); self.commit(); self.seed_panel('苏婉青',欲望=75); self.commit()
        self.assertEqual(95,self.panel('沈知韫','体力')); self.assertEqual(100,self.panel('苏婉青','体力')); self.assertEqual(1,self.counts()['空耗_连续未纾解_苏婉青'])
    def test_23_exhaust_end_condition(self):
        self.seed_panel('沈知韫',欲望=75); self.commit(); self.commit(ds_events={'沈知韫':['场景切换_欲望回落']})
        self.assertEqual(0,self.counts()['空耗_连续未纾解_沈知韫']); self.assertEqual(100,self.panel('沈知韫','体力'))
    def test_24_exhaust_clearance(self):
        self.seed_panel('沈知韫',欲望=75,高潮=90,体力=60); self.commit(); self.commit(ds_events={'沈知韫':['高潮_轻度累积']})
        self.assertEqual(0,self.counts()['空耗_连续未纾解_沈知韫']); self.assertEqual(75,self.panel('沈知韫','体力'))
    def test_25_exhaust_threshold_and_early(self):
        self.seed_panel('沈知韫',欲望=70); self.commit(); self.assertEqual(0,self.counts()['空耗_连续未纾解_沈知韫'])
        self.reject(self.request(ds_events={'沈知韫':[rr.EXHAUST_TAG]}))
    def test_26_legacy_global_not_assigned(self):
        self.seed_count(空耗_连续未纾解=1); self.seed_panel('沈知韫',欲望=75); self.commit()
        self.assertEqual(1,self.counts()['空耗_连续未纾解']); self.assertEqual(100,self.panel('沈知韫','体力')); self.assertIn('无角色归属',self.log())
    def test_27_counter_assertions_custom(self):
        self.reject(self.request(counter_updates={'连续守护回合':99}))
        self.commit(counter_updates={'连续守护回合':1,'自定义观测':4}); self.assertEqual(4,self.counts()['自定义观测'])
    def test_28_old_scope_explicit_observation(self):
        self.seed_count(破局_模式重复=9); self.commit(); self.assertEqual(1,self.counts()['破局_模式重复']); self.assertEqual(9,self.meta()['legacy_counters']['破局_模式重复']['value'])
    def test_29_legacy_full_json_compatibility(self):
        self.commit(None,counter_updates={'连续守护回合':2,'破局_日常冗余':4})
        self.assertEqual(2,self.counts()['连续守护回合']); self.assertIn('旧格式未提供round_conditions',self.log())
    def test_30_legacy_python_entry(self):
        engine=rr._engine(self.project,self.project); req=self.request(None); body={k:v for k,v in req.items() if k not in rr.REQUIRED-{'current_round','story_nodes','memory_deltas','panel_changes'}}
        receipt=engine.execute_injection(**body); self.assertEqual('committed',receipt['status']); self.assertTrue(engine.execute_injection(**body)['replayed'])
    def test_31_dry_run_not_counted(self):
        req=self.request(micro_state_changes={'沈知韫':{'momentary_ease':True}}); before=self.snapshot()
        self.assertEqual('validated',self.store.submit(req,dry_run=True)['status']); self.assertEqual(before,self.snapshot())
        self.store.submit(req); self.assertEqual(1,self.counts()['连续守护回合'])
    def test_32_invalid_failed_submit_not_counted(self):
        req=self.request(); req['story_nodes'][0]['text']='无效场景戳'; self.reject(req); self.commit(); self.assertEqual(1,self.counts()['连续守护回合'])
    def test_33_publish_failure_and_retry(self):
        req=self.request(); before=self.snapshot(); publish=self.store._publish
        def fail_once(values):
            self.store._publish=publish
            rr._atomic(self.project/rr.FILES[0],values[rr.FILES[0]])
            raise OSError('isolated publish failure')
        self.store._publish=fail_once
        with self.assertRaises(OSError): self.store.submit(req)
        self.assertEqual(before,self.snapshot()); self.store.submit(req); self.assertEqual(1,self.counts()['连续守护回合'])
    def test_34_process_death_recovery(self):
        req=self.request(); (self.project/'request.json').write_bytes(rr._json(req))
        program='''import json,os,sys
from pathlib import Path
import round_runtime as r
p=Path(sys.argv[1]);mode=sys.argv[2];s=r.RoundStore(p)
if mode=='prepared':
 def stop(values):
  r._atomic(p/r.FILES[0],values[r.FILES[0]]);os._exit(77)
 s._publish=stop
else:
 original=r._atomic
 def stop(path,raw):
  original(path,raw)
  if path.name=='journal.json' and json.loads(raw).get('phase')=='committed':os._exit(78)
 r._atomic=stop
s.submit(json.loads((p/'request.json').read_bytes()))
'''
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(self.project))
        child=subprocess.run([sys.executable,'-B','-c',program,str(self.project),'prepared'],cwd=self.project,env=env,capture_output=True,timeout=20)
        self.assertEqual(77,child.returncode,child.stderr.decode()); self.assertEqual(1,self.store.prepare()['current_round']); self.assertNotIn(rr.LIFE_ANCHOR,self.memory())
        child=subprocess.run([sys.executable,'-B','-c',program,str(self.project),'committed'],cwd=self.project,env=env,capture_output=True,timeout=20)
        self.assertEqual(78,child.returncode,child.stderr.decode()); self.assertEqual(2,self.store.prepare()['current_round']); self.assertEqual(1,self.counts()['连续守护回合']); self.assertTrue(self.store.submit(req)['replayed'])
    def test_35_stale_revision_and_source_rejected(self):
        old=self.request(); self.commit(); self.reject(old,rr.ConflictError)
        req=self.request(); before=self.snapshot(); original=self.store._settle
        guard=self.project/'txt文件/一键注入指南.txt'; expected=sha(guard.read_bytes())
        def change(*args):
            result=original(*args); guard.write_text(guard.read_text()+'\n'); return result
        self.store._settle=change
        with self.assertRaises(rr.ConflictError): self.store.submit(req,_source_baseline={'txt文件/一键注入指南.txt':expected})
        self.assertEqual(before,self.snapshot())
    def test_36_corrupt_metadata_rejected(self):
        self.commit(); self.write_memory(self.memory().replace('"version":1','"version":9'))
        self.reject(self.request())
    def test_37_condition_validation(self):
        for bad in (condition(intensity='D'),condition(stress_signals=True),condition(npc=None,stress_signals=1),condition(breakout_triggered=['未知']),condition(effective_progress=1)):
            self.reject(self.request(bad))
        self.reject(self.request(shame_events={'沈知韫':['C烈度_轻度']}))
    def test_38_bridge_adapter_and_context(self):
        prepared=self.store.prepare(); req=self.request(); keys=['state.memory','contract.inject','gate.V1']
        semantic={k:copy.deepcopy(req[k]) for k in ('story_nodes','memory_deltas','options_text')}
        semantic['model_audit']={'intent':'核对桌边材料，不代选后续行动','scene':'客厅|徐志北,沈知韫','required_keys':[],
            'evidence':{k:'本轮核对材料顺序与读入的字段边界：'+k for k in keys},
            'v1':{k:{'status':'通过','reason':'本轮具体事实仅为中性材料核查，保留宿主意图与感官。'} for k in ('V1-A','V1-B','V1-C','V1-D')},
            'task':'本回未提议新任务','breakout':'依据核查事实判断，无实际破局事件'}
        facts={'required_reads_verified':True,'available_keys':{k:{'path':'synthetic','complete':True} for k in keys},'read_call_count':3,'source_fingerprints':{},'memory':prepared['memory_layers']}
        identity={k:req[k] for k in ('schema_version','request_id','base_revision','current_round')}
        missing=copy.deepcopy(semantic); missing['memory_deltas'].pop('round_conditions')
        with self.assertRaises(rr.RoundError): rr._assemble_bridge_result(self.project,missing,identity,facts)
        body=rr._assemble_bridge_result(self.project,semantic,identity,facts); self.store.submit(body)
        tree=ast.parse(source('story_service.py')); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StoryService')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_context')
        ns={'rr':rr,'re':re,'json':json,'hashlib':hashlib,'STORY_PROTOCOL':3,
            'RULES':('txt文件/一键注入指南.txt','txt文件/全局执行法典.md','txt文件/提示词.md','txt文件/故事检索索引.md','txt文件/知识库/世界观类.json','txt文件/知识库/角色类.json','txt文件/知识库/叙事判断.json','txt文件/知识库/系统标签类.json')}
        ns['REQUIRED_READS']=(rr.FILES[0],*ns['RULES'][:4],'data.json'); ns['REQUIRED_BROWSE']=('txt文件','txt文件/知识库','存档')
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<real StoryService._context method>','exec'),ns)
        context=ns['_context'](types.SimpleNamespace(store=self.store,root=self.project),self.store.prepare(),'context','核材料')
        env=json.loads(context['turns'][1]['content']); contract=env['output_contract']
        self.assertEqual(4,len(contract['required_top_keys'])); self.assertEqual(sorted(rr.ROUND_CONDITION_FIELDS),contract['round_conditions']['required_fields']); self.assertEqual({},contract['optional_defaults']['micro_state_changes'])
    def test_39_event_registry_and_export_unchanged_shape(self):
        engine=rr._engine(self.project,self.project); registry=rr._event_registry(self.project,engine)
        self.assertEqual([18,6,17,9,15],[len(registry[k]) for k in ('shame_events','depravity_events','ds_events','affection_events','host_events')])
        convert=types.ModuleType('_test_converter'); convert.__file__=str(root/'Operit世界书导出/convert_to_operit.py')
        exec(compile((root/'Operit世界书导出/convert_to_operit.py').read_bytes(),convert.__file__,'exec'),convert.__dict__)
        out=[]
        for name in ('世界观类','叙事判断','角色类','系统标签类'):
            out.extend(convert.to_operit(e) for e in json.loads(source('txt文件/知识库/'+name+'.json'))['data']['entries'])
        exported=json.loads(source('Operit世界书导出/operit_worldbook_深渊天平.json'))
        self.assertEqual(out,exported); self.assertEqual(22,len(out)); self.assertEqual(7,sum(e['always_active'] for e in out))


    def test_40_empty_ds_passive_projection(self):
        self.seed_panel('沈知韫',欲望=69,羞耻=20,好感=80)
        self.commit(ds_events={'沈知韫':[]})
        self.assertEqual(72,self.panel('沈知韫','欲望'))
        self.assertEqual(1,self.counts()['空耗_连续未纾解_沈知韫'])
        self.commit()
        self.assertEqual(95,self.panel('沈知韫','体力'))
    def test_41_breakout_threshold_is_audited(self):
        for n in range(5): self.commit()
        audit=json.loads(self.log().split('【程序生命周期结算】',1)[1].strip())
        self.assertTrue(audit['breakout_evaluation']['破局_日常冗余']['threshold_reached'])
        self.assertEqual(5,audit['breakout_evaluation']['破局_日常冗余']['threshold'])
        self.assertEqual([],audit['round_conditions']['breakout_triggered'])


class Recording(unittest.TextTestResult):
    def addSuccess(self,test): super().addSuccess(test); results.append({'case':test._testMethodName,'status':'PASS'})
    def addFailure(self,test,err): super().addFailure(test,err); results.append({'case':test._testMethodName,'status':'FAIL'})
    def addError(self,test,err): super().addError(test,err); results.append({'case':test._testMethodName,'status':'ERROR'})

results=[]
try:
    import io
    capture=io.StringIO()
    result=unittest.TextTestRunner(stream=capture,verbosity=2,resultclass=Recording).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
    unchanged=all((root/rel).read_bytes()==raw for rel,raw in live_files.items())
    report={'cases':results,'metrics':{'real_store':True,'real_engine':True,'real_model_called':False,'tts_called':False,
             'http_tested':False,'bridge_context_method_tested':True,'installed':args.installed,'live_facts_unchanged':unchanged}}
    (base/'src/P9隔离验收结果_15.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    output=capture.getvalue()
    if result.wasSuccessful() and unchanged:
        line='P9_ISOLATION_PASS cases='+str(result.testsRun)+' real_store=true real_engine=true live_facts_unchanged=true'
        output+='\n'+line+'\n'; print(line)
    else:
        print(output)
    (base/'src/P9隔离验收输出_15.txt').write_text(output)
    assert unchanged and result.wasSuccessful()
finally:
    shutil.rmtree(work)

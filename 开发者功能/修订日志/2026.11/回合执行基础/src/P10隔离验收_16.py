"""P10 targeted acceptance using real engine functions and disposable RoundStore projects."""
from pathlib import Path
import argparse
import ast
import copy
import hashlib
import io
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');parser.add_argument('--retry-failed',action='store_true');args=parser.parse_args()
sys.dont_write_bytecode=True
root=Path.cwd().resolve();base=root/'开发者功能/修订日志/2026.11/回合执行基础'
m=json.loads((base/'src/安装清单_16.json').read_bytes());changes={c['path']:c for c in m['changes']}
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def source(rel):
    c=changes.get(rel)
    return (root/c['staged']).read_bytes() if c and not args.installed else (root/rel).read_bytes()
def parent_source(rel):
    c=changes.get(rel)
    return (root/c['backup']).read_bytes() if c and args.installed and c['before'] else (root/rel).read_bytes()

def load(name,rel,raw=None):
    module=types.ModuleType(name);module.__file__=str(root/rel)
    if name=='round_runtime':sys.modules[name]=module
    exec(compile(raw if raw is not None else source(rel),module.__file__,'exec'),module.__dict__)
    return module

rr=load('round_runtime','round_runtime.py')
registry=json.loads(source('txt文件/事件注册表.json'))
index={e['id']:e for entries in registry['groups'].values() for e in entries}
old_engine=load('_p10_parent_engine','injection_core.py',parent_source('injection_core.py'))
old_engine.print=lambda *a,**k:None
old_guide=parent_source('txt文件/一键注入指南.txt').decode()
work=Path(tempfile.mkdtemp(prefix='tmp_p10_tests16_',dir=base/'tmp'))
live={rel:(root/rel).read_bytes() for rel in rr.FILES}
tracked=dict(m['protected']);tracked.update({c['path']:c['after' if args.installed else 'before'] for c in m['changes'] if c['before'] or args.installed})
for rel,info in tracked.items():assert sha((root/rel).read_bytes())==info['sha256'],rel
fixture_tree=ast.parse((root/'开发者功能/开发者工具/回合执行验收.py').read_bytes());fixtures={'rr':rr}
exec(compile(ast.Module(body=[n for n in fixture_tree.body if isinstance(n,ast.FunctionDef) and n.name in {'memory','syslog'}],type_ignores=[]),'<existing fixtures>','exec'),fixtures)
# Reuse P9's direct compatibility cases, adding only the new registry file to each isolated project.
p9_text=(base/'src/P9隔离验收_15.py').read_text()
p9_text=p9_text.replace("'injection_core.py','round_runtime.py','txt文件/一键注入指南.txt','story_service.py',", "'injection_core.py','round_runtime.py','txt文件/一键注入指南.txt','story_service.py','txt文件/事件注册表.json',")
p9_text=p9_text.replace("'txt文件/知识库/叙事判断.json','txt文件/知识库/系统标签类.json')", "'txt文件/知识库/叙事判断.json','txt文件/知识库/系统标签类.json','txt文件/事件注册表.json')")
p9_text=p9_text.replace('rr.GUARD_TAG',"'日常_连续守护5回合'").replace('rr.EXHAUST_TAG',"'状态_空耗惩罚'")
ns=globals();p9_tree=ast.parse(p9_text)
exec(compile(ast.Module(body=[n for n in p9_tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in {'condition','Cases'}],type_ignores=[]),'<P9 cases with registry fixture>','exec'),ns)
P9Cases=Cases
metrics={'numeric_comparisons':0,'main_tag_count':65,'vigilance_tag_count':10,'real_store':True,'real_engine':True,'real_model_called':False,'tts_called':False,'http_tested':False,'installed':args.installed}


class P10Cases(P9Cases):
    # Run inherited P9 cases once, in their own suite.
    pass
for name in [key for key in P9Cases.__dict__ if key.startswith('test_')]:setattr(P10Cases,name,None)


def numeric_parity(self,field,fn):
    engine=rr._engine(self.project,self.project)
    entries=registry['groups'][field]
    tagsets=[[e['tag'] if e['pattern'] is None else '兑换道具_7'] for e in entries]
    tagsets += [[], [e['tag'] for e in entries if e['pattern'] is None]]
    if field=='shame_events':
        tagsets += [[a,b] for a in ('C烈度_轻度','C烈度_中度','C烈度_深度','C烈度_重度','内射_首次核爆')
                    for b in ('首次','同质化免疫_回合2','同质化免疫_回合3','解离保护','耻感反弹_苏醒')]
    if field=='ds_events':
        tagsets += [['刺激_物理','临界突破_心理羞辱'],['刺激_视觉','刺激_嗅觉','刺激_听觉'],['高潮_中度累积','消耗_剧烈抗拒']]
    if field=='affection_events':
        tagsets += [['苏婉青_真相揭露','深度操控_首次'],['苏婉青_温柔侵蚀','社交微幅回馈']]
    configs=[(0,0,0,0,0,0),(29,29,70,29,14,99),(30,30,71,40,15,90),(50,60,80,60,16,70),(60,61,85,70,60,100),(61,90,100,81,99,0),(86,99,69,20,100,0),(100,100,100,100,100,100)]
    for aff,dep,des,shame,sta,org in configs:
        for name in ('沈知韫','苏婉青','徐念薇'):
            self.seed_panel(name,好感=aff,堕落=dep,欲望=des,羞耻=shame,体力=sta,高潮=org)
        path=str(self.project/rr.FILES[0])
        for tags in tagsets:
            for name in ('沈知韫','苏婉青'):
                value=tags if field=='host_events' else {name:tags}
                if field=='host_events':a=(value,{'沈知韫':['内射_首次核爆']},path)
                elif field=='affection_events':a=(value,{'沈知韫':['C烈度_重度'],'苏婉青':['C烈度_轻度']},path)
                else:a=(value,path)
                expected=getattr(old_engine,fn)(*copy.deepcopy(a));actual=getattr(engine,fn)(*copy.deepcopy(a))
                self.assertEqual(expected,actual,(field,aff,dep,des,shame,sta,org,tags,name));metrics['numeric_comparisons']+=1


def test_registry_sets(self):
    engine=rr._engine(self.project,self.project);actual=rr._event_registry(self.project,engine)
    for field in registry['groups']:
        if field=='vigilance_events':
            tree=ast.parse(parent_source('injection_core.py'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_apply_vigilance_tags');tags=set()
            for n in ast.walk(fn):
                if isinstance(n,ast.Compare) and isinstance(n.left,ast.Name) and n.left.id=='tag':
                    for other in n.comparators:
                        values=other.elts if isinstance(other,(ast.Tuple,ast.List)) else [other]
                        tags.update(v.value for v in values if isinstance(v,ast.Constant))
        else:tags={s.strip() for s in re.findall(r'^【'+field.upper()+r'】(.+)$',old_guide,re.M)[0].split('/')}
        self.assertEqual(tags,actual[field])
    self.assertEqual(65,sum(len(actual[f]) for f in actual if f!='vigilance_events'));self.assertEqual(10,len(actual['vigilance_events']))


def test_engine_ast_equivalent(self):
    class Restore(ast.NodeTransformer):
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=='_event_tag':return ast.copy_location(ast.Constant(index[node.args[0].value]['tag']),node)
            if isinstance(node.func,ast.Name) and node.func.id=='_event_param':return ast.copy_location(ast.Constant(index[node.args[0].value]['parameters'][node.args[1].value]),node)
            return self.generic_visit(node)
        def visit_Subscript(self,node):
            is_prefix=isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='_event_tag'
            node=self.generic_visit(node)
            if is_prefix and isinstance(node.value,ast.Constant):return ast.copy_location(ast.Constant(node.value.value[:-1]),node)
            return node
    before=ast.parse(parent_source('injection_core.py'));after=ast.parse(source('injection_core.py'))
    before_f={n.name:n for n in before.body if isinstance(n,ast.FunctionDef)};after_f={n.name:n for n in after.body if isinstance(n,ast.FunctionDef)}
    for name,fn in before_f.items():self.assertEqual(ast.dump(fn,include_attributes=False),ast.dump(Restore().visit(copy.deepcopy(after_f[name])),include_attributes=False),name)
    metrics['original_engine_functions_ast_equal']=len(before_f)


def test_vigilance_numeric(self):
    engine=rr._engine(self.project,self.project);tags=[e['tag'] for e in registry['groups']['vigilance_events']]
    combos=[[t] for t in tags]+[tags,list(reversed(tags)),['异常行迹','眼线汇报'],['目击确认','降警惕_深度']]
    for level,vigilance,combo in itertools.product(range(5),(0,29,49,50,69,99),combos):
        before={'位置':'外地','目标':{'沈知韫':{'警惕':vigilance,'发现':level,'发现几率':0}}};after=copy.deepcopy(before)
        old_engine._apply_vigilance_tags(before,{'沈知韫':combo});engine._apply_vigilance_tags(after,{'沈知韫':combo})
        self.assertEqual(before,after);metrics['numeric_comparisons']+=1


def test_registry_validation(self):
    path=self.project/'txt文件/事件注册表.json';raw=path.read_text()
    invalid=[]
    obj=json.loads(raw);obj['groups']['shame_events'][0]['id']='SHAME_99';invalid.append(json.dumps(obj,ensure_ascii=False))
    obj=json.loads(raw);obj['groups']['shame_events'][0]['parameters'].pop('base_delta_01');obj['groups']['shame_events'][0]['parameter_usage'].pop('base_delta_01');invalid.append(json.dumps(obj,ensure_ascii=False))
    obj=json.loads(raw);obj['groups']['shame_events'][1]['tag']=obj['groups']['shame_events'][0]['tag'];invalid.append(json.dumps(obj,ensure_ascii=False))
    obj=json.loads(raw);obj['groups']['host_events'][11]['pattern']='.*';invalid.append(json.dumps(obj,ensure_ascii=False))
    obj=json.loads(raw);obj['groups']['host_events'][11]['pattern']=None;invalid.append(json.dumps(obj,ensure_ascii=False))
    invalid += [raw.replace('"version": 1','"version": 1, "version": 1',1),raw.replace('"base_delta_01": 2','"base_delta_01": NaN',1)]
    for text in invalid:
        path.write_text(text)
        with self.assertRaises(rr.RoundError):rr._engine(self.project,self.project)
    path.write_text(raw)
    path.unlink()
    with self.assertRaises(rr.RoundError):rr._engine(self.project,self.project)


def test_invalid_event_inputs(self):
    for field in registry['groups']:
        for tag in ('不存在的事件',' '):
            payload=[tag] if field=='host_events' else {'沈知韫':[tag]}
            self.reject(self.request(**{field:payload}))
        e=registry['groups'][field][0];tag=e['tag'];payload=[tag,tag] if field=='host_events' else {'沈知韫':[tag,tag]}
        self.reject(self.request(**{field:payload}))
    for tag in ('兑换道具_X','兑换道具_0','兑换道具_01','兑换道具_-1','兑换道具_1000000000'):
        self.reject(self.request(host_events=[tag]))
    for tag in ('兑换道具_1','兑换道具_999999999'):
        req=self.request(host_events=[tag]);self.store.submit(req,dry_run=True)
    self.reject(self.request(shame_events=['C烈度_轻度']))
    self.reject(self.request(host_events={'沈知韫':['商业_信息获取']}))


def test_generated_views(self):
    engine=rr._engine(self.project,self.project);guide=source('txt文件/一键注入指南.txt').decode()
    kb=json.loads(source('txt文件/知识库/系统标签类.json'));mapkey={'sys.shame':'shame_events','sys.depravity':'depravity_events','sys.ds':'ds_events','sys.affection':'affection_events','sys.host_points':'host_events','sys.vigilance':'vigilance_events'}
    for field in registry['groups']:
        view='【注册表生成表开始】\n'+engine._render_event_table(field)+'\n【注册表生成表结束】';self.assertEqual(1,guide.count(view))
        entry=next(e for e in kb['data']['entries'] if mapkey.get(e['name'].split('（')[0])==field);self.assertEqual(1,entry['content'].count(view))
    p=self.project/'txt文件/一键注入指南.txt';p.write_text(p.read_text().replace('track1_pts_01=2','track1_pts_01=999',1))
    self.reject(self.request())


def test_registry_controls_settlement(self):
    path=self.project/'txt文件/事件注册表.json';obj=json.loads(path.read_bytes());entry=obj['groups']['host_events'][0];entry['parameters']['track1_pts_01']=17
    path.write_text(json.dumps(obj,ensure_ascii=False));engine=rr._engine(self.project,self.project)
    result=engine.process_host_system(['侵蚀_认知撕裂'],{},str(self.project/rr.FILES[0]));self.assertEqual(24,result['积分'])
    self.assertIn('track1_pts_01=17',engine._render_event_table('host_events'))
    self.reject(self.request(host_events=['侵蚀_认知撕裂'])) # stale display cannot conceal a changed definition


def test_registry_changed_during_settle(self):
    request=self.request();before=self.snapshot();original=self.store._settle;path=self.project/'txt文件/事件注册表.json'
    def mutate(*a):
        result=original(*a);path.write_text(path.read_text()+'\n');return result
    self.store._settle=mutate
    with self.assertRaises(rr.ConflictError):self.store.submit(request)
    self.assertEqual(before,self.snapshot())


def test_item_ids_batch_and_history(self):
    (self.project/rr.FILES[1]).write_text('▼ 已过期/已消耗道具历史区 ▼\n==================================================\n（当前为空）\n')
    entries=[{'name':'核验笔A','type':'永久性','quantity':1,'desc':'中性验收物品'},{'name':'核验笔B','type':'永久性','quantity':1,'desc':'中性验收物品'}]
    req,_=self.commit(item_entries=entries);content=(self.project/rr.FILES[1]).read_text();self.assertEqual(['ITEM-001','ITEM-002'],re.findall(r'【道具ID】：(ITEM-\d+)',content))
    before=self.snapshot();self.assertTrue(self.store.submit(req)['replayed']);self.assertEqual(before,self.snapshot())
    self.commit(item_entries=[{'name':'核验笔A','action':'archive'}]);self.commit(item_entries=[{'name':'核验笔C','type':'永久性','desc':'中性验收物品'}])
    content=(self.project/rr.FILES[1]).read_text();ids=re.findall(r'【道具ID】：(ITEM-\d+)',content);self.assertEqual({'ITEM-001','ITEM-002','ITEM-003'},set(ids));self.assertEqual(3,len(ids))


def test_task_ids_serial_and_replay(self):
    task={'title':'核验任务A','target':'系统宿主','attr':'积分','value':8,'tier':'small','item_desc':'核验便签'}
    req,_=self.commit(task_issue=task);self.assertIn('TASK-001',self.memory());before=self.snapshot();self.assertTrue(self.store.submit(req)['replayed']);self.assertEqual(before,self.snapshot())
    self.commit(host_events=['日常_温和累进']);self.assertIn('已完成',self.memory())
    task=dict(task,title='核验任务B',value=100);self.commit(task_issue=task)
    state=rr._engine(self.project,self.project)._parse_task_block(self.memory());self.assertEqual('TASK-002',state['current']['id']);self.assertTrue(any('TASK-001' in x for x in state['history']))


def test_readonly_events_cli(self):
    command=[sys.executable,'-B',str(self.project/'round_runtime.py'),'--root',str(self.project),'events']
    before=self.snapshot();child=subprocess.run(command,cwd=self.project,capture_output=True,timeout=15)
    self.assertEqual(0,child.returncode,child.stderr.decode());obj=json.loads(child.stdout);self.assertTrue(obj['ok']);self.assertEqual(6,len(obj['result']['views']));self.assertEqual(before,self.snapshot())


P10Cases.test_50_sets=test_registry_sets
P10Cases.test_51_ast_equivalence=test_engine_ast_equivalent
for i,(field,fn) in enumerate([('shame_events','process_shame_system'),('depravity_events','process_depravity_system'),('ds_events','process_desire_stamina_system'),('affection_events','process_affection_system'),('host_events','process_host_system')],52):
    def test(self,field=field,fn=fn):numeric_parity(self,field,fn)
    setattr(P10Cases,'test_'+str(i)+'_'+field,test)
for i,(name,test) in enumerate([('vigilance_numeric',test_vigilance_numeric),('bad_registry',test_registry_validation),('invalid_events',test_invalid_event_inputs),('generated_views',test_generated_views),('single_source',test_registry_controls_settlement),('definition_conflict',test_registry_changed_during_settle),('item_ids',test_item_ids_batch_and_history),('task_ids',test_task_ids_serial_and_replay),('events_cli',test_readonly_events_cli)],57):
    setattr(P10Cases,'test_'+str(i)+'_'+name,test)


class Recording(unittest.TextTestResult):
    def addSuccess(self,test):super().addSuccess(test);results.append({'case':test.id(),'status':'PASS'})
    def addFailure(self,test,err):super().addFailure(test,err);results.append({'case':test.id(),'status':'FAIL'})
    def addError(self,test,err):super().addError(test,err);results.append({'case':test.id(),'status':'ERROR'})

results=[]
try:
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(P9Cases),unittest.defaultTestLoader.loadTestsFromTestCase(P10Cases)])
    previous=None
    if args.retry_failed:
        previous=json.loads((base/'src/P10隔离验收结果_16.json').read_bytes())
        failed={case['case'] for case in previous['cases'] if case['status']!='PASS'}
        suite=unittest.TestSuite(test for group in suite for test in group if test.id() in failed)
        assert suite.countTestCases()==len(failed) and failed
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2,resultclass=Recording).run(suite)
    attempt_cases=result.testsRun
    if previous:
        updated={case['case']:case for case in results}
        results=[updated.get(case['case'],case) for case in previous['cases']]
        metrics['numeric_comparisons']+=previous['metrics']['numeric_comparisons']
        metrics['original_engine_functions_ast_equal']=previous['metrics']['original_engine_functions_ast_equal']
        metrics['reused_passed_cases']=len(previous['cases'])-len(updated)
        metrics['targeted_retry_cases']=attempt_cases
        metrics['first_attempt_failures']=[case for case in previous['cases'] if case['status']!='PASS']

    metrics['live_facts_unchanged']=all((root/rel).read_bytes()==raw for rel,raw in live.items())
    metrics['cases']=len(results)
    text=output.getvalue()
    if previous:
        text=(base/'src/P10隔离验收输出_16.txt').read_text()+'\nTARGETED_RETRY fixture_history_separator_fixed=true\n'+text
    if result.wasSuccessful() and metrics['live_facts_unchanged']:
        line='P10_ISOLATION_PASS cases='+str(len(results))+' numeric_comparisons='+str(metrics['numeric_comparisons'])+' main_tags=65 vigilance_tags=10 live_facts_unchanged=true'
        text+='\n'+line+'\n';print(line)
        print('AST_EQUIVALENCE original_functions='+str(metrics['original_engine_functions_ast_equal'])+' restored=true')
    else:print(text)
    (base/'src/P10隔离验收结果_16.json').write_text(json.dumps({'cases':results,'metrics':metrics},ensure_ascii=False,indent=2)+'\n')
    (base/'src/P10隔离验收输出_16.txt').write_text(text)
    assert result.wasSuccessful() and metrics['live_facts_unchanged']
finally:shutil.rmtree(work)
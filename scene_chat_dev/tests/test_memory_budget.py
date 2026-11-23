"""Memory selection, compaction and authenticated retrieval on disposable saves."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from test_progression import ProgressionChecks
import interaction_runtime as ir
import story_progression as sp
import round_runtime as rr


class MemoryBudgetChecks(ProgressionChecks):
    # Reuse transaction helpers without re-running inherited test methods.
    def response(self,task,**kwargs):
        fact=kwargs.pop('fact',None);compact=kwargs.pop('compact',None)
        body=super().response(task,**kwargs)
        data=json.loads(body['text'])
        if fact is not None:data['resolution']['memory']['fact']=fact
        if compact is not None:data['resolution']['memory']['compact']=compact
        body['text']=json.dumps(data,ensure_ascii=False)
        return body

    def layers(self):
        return rr._engine(self.root,self.root)._parse_memory_layer_items((self.root/rr.FILES[0]).read_text())

    def packet(self,task):
        context=json.loads(self.service._blob(task['request_id'],'.context.json').read_text())
        return context,json.loads((self.root/context['packet']['path']).read_text())

    def read_ref(self,body,ref):
        lines=(self.root/ref['path']).read_text().splitlines()
        body['conversation_audit']['tools'].append({'name':'read_file_part',
            'parameters':{k:ref[k] for k in ('path','start_line','end_line')},'status':'success',
            'result_text':'\n'.join(str(i)+'| '+lines[i-1] for i in range(ref['start_line'],ref['end_line']+1))})

    def test_empty_routine_twenty_paid_actions_keep_archive_without_memory_growth(self):
        self.begin(time='09:00');before=self.layers()
        for i in range(20):
            self.accept(time='09:'+str(i+1).zfill(2),fact='',text='她把餐具放好，等他继续说。')
            self.play()
        self.assertEqual(self.layers(),before)
        self.assertEqual(len(ir.records(self.store)),21)
        self.assertEqual(self.energy(),0)
        self.assertEqual(sp.state(self.root,self.store._files())['last_closed'],1)

    def test_duplicate_facts_do_not_grow_and_plan_keeps_pending_status(self):
        self.begin(time='09:00')
        fact='苏婉青计划15:30去主宅探望，尚未执行；徐志北答应上午留下陪她。'
        self.accept(time='09:01',fact=fact);self.play();before=self.layers()
        for i in range(3):
            self.accept(time='09:0'+str(i+2),fact=fact);self.play()
        self.assertEqual(self.layers(),before)
        self.assertIn('尚未执行',self.layers()['L1'][0])

    def test_compact_replaces_long_daily_log_with_commitments_and_no_rewrite_elsewhere(self):
        self.begin(time='09:00')
        engine=rr._engine(self.root,self.root)
        original='徐志北答应上午留下；苏婉青计划15:30探望婆婆，尚未执行。'+'摆好餐具。'*150
        engine.update_global_memory(1,{'l1_new_round':original},{})
        compact='第1天09:05，公寓。徐志北答应上午留下陪苏婉青；她计划15:30到主宅探望婆婆、晚饭后返回，均未执行。她已说明晚饭需提前预约。'
        self.accept(time='09:05',fact='苏婉青说明晚饭需提前预约。',compact=compact);self.play()
        self.assertEqual(self.layers()['L1'],['【1】'+compact])
        self.assertLessEqual(len(self.layers()['L1'][0].split('】',1)[1]),600)
        self.assertEqual(len(ir.records(self.store)),2)

    def test_overflow_without_compact_refunds_and_preserves_prior_and_archive(self):
        self.begin(time='09:00');engine=rr._engine(self.root,self.root)
        engine.update_global_memory(1,{'l1_new_round':'重要旧约定。'*110},{})
        before=self.layers();energy=self.energy();count=len(ir.records(self.store))
        self.service.create(self.request('A'));task=self.service.claim()['task']
        result=self.service.result(task['request_id'],self.response(task,category='A',time='09:05',fact='新的重要信息。'))
        self.assertEqual(result['task']['status'],'failed',result)
        self.assertEqual(self.layers(),before);self.assertEqual(self.energy(),energy)
        self.assertEqual(len(ir.records(self.store)),count)

    def test_empty_fact_does_not_evict_or_require_transfer_at_full_l1(self):
        self.begin(time='09:00');engine=rr._engine(self.root,self.root)
        for i in (2,3):engine.update_global_memory(i,{'l1_new_round':'已有约定'+str(i)},{})
        data=json.loads((self.root/'data.json').read_text());data['story_runtime'].update(memory_round=4,last_closed=3)
        (self.root/'data.json').write_text(json.dumps(data,ensure_ascii=False));before=self.layers()
        self.accept(time='09:05',fact='');self.play()
        self.assertEqual(self.layers(),before)

    def test_budget_projection_1000_l4_entries_keeps_exact_sources_and_relevance(self):
        memory=(self.root/rr.FILES[0]).read_text()
        headers=['▲ 第一层：【即时运存区】','▲ 第二层：【回想运存区】','▲ 第三层：【近期事实缓存区】','▲ 第四层：【深渊纪元浓缩区】']
        l4=['【'+str(i)+'】'+('约定尚未完成。'*60) for i in range(1,1001)]
        l4[17]='【18】徐志北向沈知韫承诺周五归还蓝色借书卡，尚未归还。'
        content=memory[:memory.index('▲ 第一层：')]+headers[0]+'\n【1001】公寓当前场景。\n\n'+headers[1]+'\n（空）\n\n'+headers[2]+'\n（空）\n\n'+headers[3]+'\n'+'\n\n'.join(l4)+'\n'
        runtime={'memory_round':1001,'last_closed':1000,'phase':'ready'}
        view=ir.memory_context(self.root,content,'蓝色借书卡归还了吗',runtime)
        self.assertLessEqual(len(view['text']),6000)
        self.assertLessEqual(len(view['index']),24)
        self.assertIn('蓝色借书卡',view['text']);self.assertIn('公寓当前场景',view['text'])
        self.assertGreater(view['omitted_count'],900)
        source_lines=content.splitlines()
        all_entries=rr._engine(self.root,self.root)._parse_memory_layer_items(content)
        for ref in view['selected']:
            actual='\n'.join(source_lines[ref['start_line']-1:ref['end_line']])
            self.assertTrue(any(actual==item for items in all_entries.values() for item in items))

    def test_long_legacy_current_requires_complete_authenticated_read(self):
        self.begin(time='09:00');engine=rr._engine(self.root,self.root)
        engine.update_global_memory(1,{'l1_new_round':'保留明确未完成约定。'*900},{})
        self.service.create(self.request('A'));task=self.service.claim()['task'];context,packet=self.packet(task)
        self.assertTrue(context['required_memory_reads'])
        self.assertLessEqual(len(packet['player_private_state']['memory']),6000)
        body=self.response(task,category='A',time='09:05',fact='',compact='徐志北与沈知韫的明确约定尚未完成。')
        pre_mem=self.service.preflight(task['request_id'],body)
        self.assertFalse(pre_mem['ready']);self.assertTrue(pre_mem['missing_keys'])
        for ref in context['required_memory_reads']:self.read_ref(body,ref)
        self.assertTrue(self.service.preflight(task['request_id'],body)['ready'])
        invalid=copy.deepcopy(body);invalid['conversation_audit']['tools'][-1]['name']='read_file'
        with self.assertRaises(rr.RoundError):self.service.preflight(task['request_id'],invalid)
        self.assertEqual(self.service.result(task['request_id'],body)['task']['status'],'committed')
        self.assertEqual(self.layers()['L1'],['【1】徐志北与沈知韫的明确约定尚未完成。'])

    def test_history_window_has_character_budget_and_preserves_input_witnesses(self):
        self.begin(time='09:00')
        for i in range(8):self.accept(time='09:'+str(i+1).zfill(2),fact='',text='她看向门口。');self.play()
        self.service.create(self.request('A'));task=self.service.claim()['task'];context,packet=self.packet(task)
        self.assertEqual(len(packet['accepted_history']),6)
        self.assertLessEqual(len(json.dumps(packet['accepted_history'],ensure_ascii=False,separators=(',',':'))),12000)
        self.assertIn('input_known_by',packet['accepted_history'][0])
        self.assertIn('messages_known_by',packet['accepted_history'][0])
        self.assertNotIn('layers',packet['accounting']['memory_transfer_sources'])
        self.assertLessEqual(len(packet['history_archive']['paths']),24)
        for path in packet['history_archive']['paths']:self.assertTrue((self.root/path).is_file())
        huge=[(Path(str(i)),{'input':'长'*9000,'messages':[]}) for i in range(6)]
        bounded=ir.bounded_history(huge,sp.memory_policy(self.root));self.assertEqual(len(bounded),1)
        huge[-1][1]['input']='长'*13000
        self.assertEqual(ir.bounded_history(huge,sp.memory_policy(self.root)),[])

    def test_fact_transfer_and_compact_limits_reject_before_commit(self):
        self.begin(time='09:00')
        for field,value in [('fact','长'*161),('compact','长'*601),('fact','不应注入\n新行')]:
            self.service.create(self.request('A'));task=self.service.claim()['task']
            body=self.response(task,category='A',time='09:01')
            data=json.loads(body['text']);data['resolution']['memory'][field]=value
            body['text']=json.dumps(data,ensure_ascii=False)
            result=self.service.result(task['request_id'],body)
            self.assertEqual(result['task']['status'],'failed',result);self.assertEqual(self.energy(),100)

    def test_oversized_latest_history_requires_verified_source_and_keeps_transcript(self):
        self.begin(time='09:00');self.service.create(self.request('A'));task=self.service.claim()['task']
        body=self.response(task,category='A',time='09:01',fact='')
        data=json.loads(body['text']);data['messages']=[{'kind':'narration','speaker':'','text':str(i)+'。'+'日常对话的连续内容。'*45} for i in range(30)]
        body['text']=json.dumps(data,ensure_ascii=False)
        self.assertEqual(self.service.result(task['request_id'],body)['task']['status'],'committed');self.play()
        self.service.create(self.request('A'));task=self.service.claim()['task'];context,packet=self.packet(task)
        self.assertEqual(packet['accepted_history'],[])
        self.assertEqual(len(context['required_history_reads']),1)
        body=self.response(task,category='A',time='09:02',fact='')
        pre_hist=self.service.preflight(task['request_id'],body)
        self.assertFalse(pre_hist['ready']);self.assertTrue(pre_hist['missing_keys'])
        path=context['required_history_reads'][0];raw=(self.root/path).read_text()
        body['conversation_audit']['tools'].append({'name':'read_file','parameters':{'path':path},'status':'success','result_text':raw})
        self.assertTrue(self.service.preflight(task['request_id'],body)['ready'])
        self.assertEqual(self.service.result(task['request_id'],body)['task']['status'],'committed')
        self.assertEqual(len(json.loads((self.root/path).read_text())['messages']),30)

    def test_hundred_empty_facts_and_configured_contract_do_not_recreate_growth(self):
        layers={'L1':['【1】既有未履行约定。'],'L2':[],'L3':[],'L4':[]}
        for i in range(100):self.assertIsNone(sp.memory_merge(self.root,layers,1,{'day':1,'time':'09:00'},{'fact':'','transfers':{}}))
        self.assertEqual(layers['L1'],['【1】既有未履行约定。'])
        p=self.root/'txt文件/互动运行配置.json';value=json.loads(p.read_text());value['memory'].update(fact_chars=80,round_chars=400);p.write_text(json.dumps(value))
        contract=sp.contract(self.root)['memory'];self.assertIn('80',contract['fact']);self.assertIn('400',contract['compact'])

# Inherited compatibility tests are executed separately from test_progression.
for _name in list(ProgressionChecks.__dict__):
    if _name.startswith('test_') and _name not in MemoryBudgetChecks.__dict__:
        setattr(MemoryBudgetChecks,_name,None)

if __name__=='__main__':unittest.main()

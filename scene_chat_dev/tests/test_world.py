"""Legacy import, provenance, knowledge isolation and scene/API recovery; no model/TTS."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import round_runtime as rr
import save_store
from scene_world import LegacyWorld, ENTITIES, VISIBILITY
from scene_chat import SceneService
from story_service import StoryService, register_story_routes
from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_L1_BODY = '徐家主宅一楼餐厅，晚间 20:10，沈知韫问起今日安排，志北尚未回答。'
FIXTURE_L1 = '【1】' + FIXTURE_L1_BODY


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'scene_chat_dev/tmp')
        self.root = Path(self.temp.name)
        for name in (ENTITIES, 'txt文件/场景交流规范.md', 'txt文件/知识库/角色类.json', 'txt文件/关系称谓查询.jsonl'):
            p = self.root/name
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, p)
        state = save_store.default_state()
        layers = save_store.default_layers(FIXTURE_L1_BODY, prologue_active=False)
        data = {
            'round': 1,
            'sceneTitle': '徐家主宅一楼餐厅 · 20:10',
            'storyNodes': [],
            'presence': state['presence'],
        }
        save_store.save_bundle(self.root, state, layers, data_dict=data)
        (self.root / 'data.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        vis_digest = hashlib.sha256(FIXTURE_L1.encode('utf-8')).hexdigest()
        vis_path = self.root / VISIBILITY
        vis_path.parent.mkdir(parents=True, exist_ok=True)
        vis_path.write_text(json.dumps({
            'schema_version': 1,
            'entries': {
                vis_digest: {
                    'known_by': ['徐志北', '沈知韫'],
                    'basis': {'path': rr.FILES[0], 'start_line': 1, 'reason': '确定性单测夹具：餐厅共同在场。'},
                }
            },
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        (self.root/'injection_core.py').write_text('# isolated fixture, never executed')
        self.world = LegacyWorld(self.root)
        self.service = SceneService(self.root, StoryService(self.root))
        self.before = {name: (self.root/name).read_bytes() for name in rr.FILES}

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_source_mapping_and_provenance(self):
        value = self.world.import_latest()
        self.assertEqual(value['presence']['徐志北']['value']['location'], '徐家主宅')
        self.assertEqual(value['presence']['苏婉青']['value']['location'], '市中心顶层公寓')
        self.assertEqual(value['panels']['徐念薇']['value']['体力'], 65)
        self.assertEqual(value['panels']['沈知韫']['value']['高潮'], '0%')
        self.assertIs(value['panels']['沈知韫']['value']['怀孕'], False)
        self.assertEqual(value['items'], [])
        self.assertEqual(value['npcs'], [])
        self.assertIsNone(value['tasks']['current'])
        self.assertEqual(value['tasks']['history'], [])
        self.assertEqual(len(value['memories']), 1)
        self.assertEqual(value['unresolved_source'], [])
        self.assertTrue(value['legacy_snapshot']['options_expired'])
        self.assertFalse(value['legacy_snapshot']['story_nodes_imported_as_facts'])
        self.assertFalse(value['actions_enabled'])
        self.assertEqual(value['cost_policy'], 'unconfigured')
        for record in value['records']:
            src = record['origin']
            lines = (self.root/src['path']).read_text().splitlines()
            self.assertEqual('\n'.join(lines[src['start_line']-1:src['end_line']]), src['raw'])
        with self.world.db() as db:
            rows = db.execute('SELECT * FROM sources').fetchall()
            self.assertEqual(len(rows), len(self.world.sources()))
            for row in rows:
                self.assertEqual(row['body'], (self.root/row['path']).read_bytes())
                self.assertEqual(row['sha256'], hashlib.sha256(row['body']).hexdigest())
        self.assertEqual(self.before, {name: (self.root/name).read_bytes() for name in rr.FILES})

    def test_idempotent_import_and_fresh_process_restore(self):
        value = self.world.import_latest()
        self.assertEqual(value, self.world.import_latest())
        code = "import sys,json;from scene_world import LegacyWorld;w=LegacyWorld(sys.argv[1]).snapshot();print(json.dumps([w['world_id'],w['world_revision'],len(w['memories'])]))"
        raw = subprocess.check_output([sys.executable, '-c', code, str(self.root)], cwd=ROOT)
        self.assertEqual(json.loads(raw), [value['world_id'], 1, 1])
        with self.world.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM imports').fetchone()[0], 1)

    def test_visibility_is_exact_review_not_name_matching(self):
        first = self.world.import_latest()
        self.assertEqual(len(self.world.context(first, ['沈知韫'])['shared_memories']), 1)
        self.assertEqual(self.world.context(first, ['苏婉青'])['shared_memories'], [])
        p = self.root/rr.FILES[0]
        p.write_text(p.read_text().replace('▲ 第二层：', '【2】苏婉青独自看到一份文件。\n\n▲ 第二层：'))
        p = self.root/'data.json'; data = json.loads(p.read_text()); data['round'] = 2; p.write_text(json.dumps(data,ensure_ascii=False))
        world = self.world.import_latest()
        self.assertEqual(len(world['memories']), 2)
        self.assertIsNone(world['memories'][1]['known_by'])
        self.assertEqual(len(self.world.context(world, ['沈知韫'])['shared_memories']), 1)
        self.assertEqual(len(world['unresolved_source']), 1)
        self.assertNotIn('独自看到', json.dumps(self.world.context(world, ['苏婉青']), ensure_ascii=False))

    def test_source_change_and_mismatched_presence_do_not_overwrite(self):
        first = self.world.import_latest()
        p = self.root/'data.json'
        data = json.loads(p.read_text());data['presence']['徐志北']['location'] = '其他地点'
        p.write_text(json.dumps(data, ensure_ascii=False))
        self.assertFalse(self.world.status(first['world_id'])['source_current'])
        with self.assertRaises(rr.ConflictError): self.world.import_latest()
        self.assertEqual(self.world.snapshot()['world_id'], first['world_id'])
        p.write_bytes(self.before['data.json'])
        p = self.root/rr.FILES[0];p.write_text(p.read_text().replace('体力 65', '体力 64', 1))
        second = self.world.import_latest()
        self.assertNotEqual(first['world_id'], second['world_id'])
        self.assertEqual(second['world_revision'], 2)
        self.assertEqual(self.world.snapshot(first['world_id'])['panels']['徐念薇']['value']['体力'], 65)

    def test_pending_legacy_transaction_blocks_without_recovery(self):
        self.world.import_latest()
        journal = self.root/'.round-runtime/journal.json';journal.write_text('do not recover')
        with self.assertRaises(rr.RecoveryError): self.world.import_latest()
        self.assertEqual(journal.read_text(), 'do not recover')
        self.assertEqual(self.before, {name: (self.root/name).read_bytes() for name in rr.FILES})

    def test_corrupt_isolated_originals_rejected(self):
        world = self.world.import_latest()
        with self.world.db() as db:
            db.execute('UPDATE sources SET body=? WHERE world_id=? AND path=?', (b'altered', world['world_id'], rr.FILES[0]))
        with self.assertRaises(rr.RecoveryError): self.world.snapshot()

    def test_mismatched_round_does_not_publish(self):
        first = self.world.import_latest()
        p = self.root/'data.json'; data = json.loads(p.read_text());data['round'] = 9;p.write_text(json.dumps(data))
        with self.assertRaises(rr.ConflictError):self.world.import_latest()
        self.assertEqual(self.world.snapshot()['world_id'],first['world_id'])

    def test_items_tasks_and_real_npc_preserve_units_and_identity(self):
        p = self.root/rr.FILES[1]
        item = '【道具名称】：测试道具\n【道具ID】：ITEM-901\n【数量】：2\n【类型】：临时性\n【剩余时效】：11回合\n【使用对象】：未使用\n'
        p.write_text(p.read_text().replace('（新游戏初始仓库为空，兑换道具后由注入逻辑写入此区域）', item))
        p = self.root/rr.FILES[0]
        p.write_text(p.read_text().replace('当前任务：（无）', '当前任务：TASK-901 | 测试目标 | 徐志北·魅力·80 | A | 测试奖励 | active |发布回合1'))
        w = self.world.import_latest()
        self.assertEqual(w['items'][0]['fields']['剩余时效'], '11回合')
        self.assertEqual(w['items'][0]['quantity'], 2)
        self.assertEqual(w['tasks']['current']['id'], 'TASK-901')
        self.assertEqual(w['npcs'], [])
        self.assertEqual(w['unresolved_source'], [])

    def test_unknown_item_and_task_retained_without_fabrication(self):
        p = self.root/rr.FILES[1];p.write_text(p.read_text().replace('（新游戏初始仓库为空，兑换道具后由注入逻辑写入此区域）','一件未编号的物品'))
        p = self.root/rr.FILES[0];p.write_text(p.read_text().replace('当前任务：（无）','当前任务：尚未整理的旧任务'))
        w = self.world.import_latest()
        domains = {item['domain'] for item in w['unresolved_source']}
        self.assertTrue({'items','tasks'} <= domains)
        self.assertEqual(w['items'], [])
        self.assertIn('未编号', json.dumps(w['unresolved_source'], ensure_ascii=False))

    def body(self, task):
        packet = json.loads(task['turns'][0]['content'])['packet']
        raw = (self.root/packet['path']).read_text()
        audit = {'api':'Tools.Chat.sendMessageStreaming','chat_id':'offline','participant_id':'offline','workspace':str(self.root),
                 'outcome':{'type':'committed','status':'completed','assistant':{'messageTimestamp':21}}, 'snapshot_message_timestamp':21,
                 'tools':[{'name':'read_file','parameters':{'path':packet['path']},'status':'success',
                           'result_text':'\n'.join(f'{i}| {v}' for i,v in enumerate(raw.splitlines(),1))}]}
        result = {'messages':[{'kind':'dialogue','speaker':'沈知韫','text':'你刚才还没回答呢。'}],'facts_delta':[],'needs':[],'handoff':None}
        return {'lease':task['lease'],'text':json.dumps(result,ensure_ascii=False),'conversation_audit':audit}, json.loads(raw)

    def test_world_bound_scene_packet_and_commit_recovery(self):
        experiment = self.service.create({'cast':['苏婉青'],'location':'公寓大楼'})['scene']
        world = self.world.import_latest()
        with self.assertRaises(rr.RoundError): self.service.create({'world_id':world['world_id'],'cast':['苏婉青'],'location':'伪造地点'})
        scene = self.service.create({'world_id':world['world_id'],'cast':['沈知韫'],'location':'伪造地点'})['scene']
        self.assertEqual(scene['location'],'徐家主宅')
        request = {'request_id':'scene-world-offline','scene_id':scene['id'],'base_scene_revision':0,'input':'还没吃，你刚才问我什么？'}
        first = self.service.submit(request);self.assertEqual(self.service.submit(request), first)
        task = self.service.claim()['task'];body,packet = self.body(task)
        context = packet['world_state']
        self.assertEqual(context['world_id'],world['world_id'])
        self.assertEqual(set(context['presence']), {'徐志北','沈知韫'})
        self.assertEqual(set(context['private_state']), {'徐志北','沈知韫'})
        self.assertIn('志北尚未回答',context['shared_memories'][0]['value'])
        self.assertEqual(packet['accepted_history'], [])
        self.assertEqual(context['scene_snapshot']['title'],'徐家主宅一楼餐厅 · 20:10')
        self.assertTrue(self.service.worker(request['request_id'],'preflight',body)['ready'])
        self.service.worker(request['request_id'],'result',body);self.service.worker(request['request_id'],'result',body)
        restored = SceneService(self.root,StoryService(self.root)).snapshot(scene['id'])['scene']
        self.assertEqual(restored['revision'],1)
        self.assertEqual(restored['world_id'],world['world_id'])
        self.assertEqual(self.service.snapshot(experiment['id'])['scene'], experiment)
        self.assertEqual(self.world.snapshot(world['world_id']), world)
        self.assertEqual(self.before, {name: (self.root/name).read_bytes() for name in rr.FILES})

    def test_changed_data_rejects_queued_result_and_retry(self):
        world = self.world.import_latest()
        scene = self.service.create({'world_id':world['world_id'],'cast':['沈知韫']})['scene']
        request = {'request_id':'scene-changed','scene_id':scene['id'],'base_scene_revision':0,'input':'你好。'}
        self.service.submit(request);task = self.service.claim()['task'];body,_ = self.body(task)
        p = self.root/'data.json';p.write_text(p.read_text()+'\n')
        with self.assertRaises(rr.ConflictError):self.service.worker(request['request_id'],'result',body)
        self.assertEqual(self.service.snapshot(scene['id'])['scene']['revision'],0)
        self.service.worker(request['request_id'],'result',{'lease':task['lease'],'error':'offline failure'})
        with self.assertRaises(rr.ConflictError):self.service.retry(request['request_id'])
        with self.assertRaises(rr.ConflictError):self.service.submit({**request,'request_id':'scene-after-change'})

    def test_routes_import_is_explicit_and_same_origin(self):
        app = Flask('world-offline');register_story_routes(app,self.root);client = app.test_client()
        self.assertIsNone(client.get('/api/story/scene/world').get_json()['world'])
        self.assertEqual(client.post('/api/story/scene/world/import',json={}).status_code,403)
        response = client.post('/api/story/scene/world/import',json={},headers={'X-Story-Client':'1'})
        self.assertEqual(response.status_code,200)
        world = response.get_json()['world']
        self.assertEqual(client.get('/api/story/scene/world?id='+world['world_id']).get_json()['world'],world)
        self.assertEqual(client.get('/api/story/scene/world',headers={'Origin':'https://outside.invalid'}).status_code,403)
        response = client.post('/api/story/scene',json={'world_id':world['world_id'],'cast':['沈知韫']},headers={'X-Story-Client':'1'})
        self.assertEqual(response.status_code,200)
        scene = response.get_json()['scene']
        self.assertEqual(scene['world_id'],world['world_id'])
        self.assertEqual(client.get('/api/story/scene/connection').get_json()['world_state_protocol'],1)
        self.assertEqual(client.get('/api/story/scene/list').get_json()['scenes'][0]['world_id'],world['world_id'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

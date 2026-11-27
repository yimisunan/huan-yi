"""Isolated scene-chat transactions; never writes legacy game saves."""
import contextlib
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path

import round_runtime as rr
import story_reading as sr
from scene_world import LegacyWorld

RULE = 'txt文件/场景交流规范.md'
CAST = ('沈知韫', '苏婉青', '徐念薇')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode_packet(payload):
    """Lossless JSON; one top-level field/list item per line, no deep indentation."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    fields = []
    for key, value in payload.items():
        if isinstance(value, list) and value:
            encoded = '[\n' + ',\n'.join(compact(item) for item in value) + '\n]'
        else:
            encoded = compact(value)
        fields.append(compact(key) + ':' + encoded)
    return ('{\n' + ',\n'.join(fields) + '\n}').encode('utf-8')


_ALIAS_CACHE_LOCK = threading.RLock()
_ALIAS_CACHE = {}


def _build_reference_aliases(root):
    view_p = root / 'txt文件/关系称谓查询.jsonl'
    src_p = root / 'txt文件/关系称谓库.json'
    sig = None
    try:
        st_v, st_s = view_p.stat(), src_p.stat()
        sig = (str(view_p.resolve()), st_v.st_mtime_ns, st_v.st_size, str(src_p.resolve()), st_s.st_mtime_ns, st_s.st_size)
        with _ALIAS_CACHE_LOCK:
            cached = _ALIAS_CACHE.get(sig)
        if cached is not None:
            return cached
    except OSError:
        sig = None
    rows = [json.loads(line) for line in view_p.read_text(encoding='utf-8').splitlines()]
    entities = json.loads(src_p.read_text(encoding='utf-8'))['entities']
    aliases = {}
    for name, entity in entities.items():
        if entity.get('status') == 'active':
            for alias in (name, entity.get('short', '')):
                if len(alias) >= 2:
                    aliases.setdefault(alias, set()).add(name)
    for row in rows:
        if row.get('speaker') != '徐志北':
            continue
        for occasion in row.get('occasions', {}).values():
            for target in occasion.get('targets', []):
                for candidate in target.get('address_candidates', []):
                    alias = candidate['text']
                    if candidate.get('kind') == 'kinship' and len(alias) >= 2:
                        aliases.setdefault(alias, set()).add(target['listener'])
    frozen = tuple((alias, next(iter(names))) for alias, names in aliases.items() if len(names) == 1)
    if sig is not None:
        with _ALIAS_CACHE_LOCK:
            if len(_ALIAS_CACHE) >= 32:
                _ALIAS_CACHE.pop(next(iter(_ALIAS_CACHE)), None)
            _ALIAS_CACHE[sig] = frozen
    return frozen


class SceneService:
    def __init__(self, root, story):
        self.root = Path(root).resolve()
        self.story = story
        self.directory = self.root / '.scene-chat'
        self.lock = threading.RLock()
        self.world = LegacyWorld(self.root)

    @contextlib.contextmanager
    def db(self):
        self.directory.mkdir(exist_ok=True)
        db = sqlite3.connect(self.directory / 'state.sqlite3')
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS scenes(id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
          state TEXT NOT NULL, baseline TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, scene TEXT NOT NULL,
          base INTEGER NOT NULL, input TEXT NOT NULL, status TEXT NOT NULL,
          lease TEXT, expires REAL, data TEXT NOT NULL, result TEXT, error TEXT);
        ''')
        try:
            with db:
                yield db
        finally:
            db.close()

    def baseline(self):
        save_dir = self.root / '存档'
        files = sorted(list(save_dir.glob('*.txt')) + list(save_dir.glob('*.json')), key=lambda x: str(x))
        return digest(b''.join((str(p) + ':' + digest(p.read_bytes())).encode() for p in files))

    def references(self, text, history):
        unique_aliases = _build_reference_aliases(self.root)
        # Carry only the last two player turns; model wording cannot trigger new dependencies.
        inputs = [turn['input'] for turn in history[-2:]] + [text]
        found = {}
        for alias, name in unique_aliases:
            if any(alias in value for value in inputs):
                found.setdefault(name, []).append(alias)
        return [{'name': name, 'matched_aliases': sorted(set(hits)),
                 'basis': 'relationship_entities_and_player_address_candidates'} for name, hits in sorted(found.items())]

    def sources(self, cast, references=()):
        names = [RULE, 'txt文件/知识库/角色类.json', 'txt文件/关系称谓查询.jsonl']
        result = {name: digest((self.root / name).read_bytes()) for name in names}
        chars = json.loads((self.root / names[1]).read_text())['data']['entries']
        bodies = []
        for name in dict.fromkeys([*cast, *(r['name'] for r in references)]):
            found = [e['content'] for e in chars if '※索引key※ char.' + name in e.get('content', '')]
            if len(found) != 1:
                raise rr.RoundError('角色原文缺失或不唯一: ' + name)
            bodies.append({'key': 'char.' + name, 'body': found[0],
                'scope': 'present' if name in cast else 'referenced_background_not_shared_knowledge'})
        # Direction-scoped relationship rows; do not load all characters' secrets.
        rows = [json.loads(row) for row in (self.root / names[2]).read_text().splitlines()]
        relation_source = rows[0]['source']
        source_path = relation_source['path']
        source_hash = digest((self.root / source_path).read_bytes())
        if source_hash != relation_source['sha256']:
            raise rr.RoundError('称谓查询源指纹已过期，请先更新原查询源')
        result[source_path] = source_hash
        participants = set((*cast, '徐志北'))
        related = participants | {r['name'] for r in references}
        selected = [rows[0]]
        selected.extend(row for row in rows[1:] if
            (row.get('key', '').startswith('lore.知情.') and row.get('perspective') in participants) or
            (row.get('speaker') in participants and row.get('listener') in related))
        return result, bodies, selected

    def public(self, row):
        if not row:
            return None
        return {k: row[k] for k in ('id', 'scene', 'status', 'error', 'input', 'base')} | {
            'result': json.loads(row['result']) if row['result'] else None}

    def snapshot(self, scene_id=None):
        with self.lock, self.db() as db:
            self.expire(db)
            scene = db.execute('SELECT * FROM scenes WHERE id=?', (scene_id,)).fetchone() if scene_id else db.execute('SELECT * FROM scenes ORDER BY rowid DESC LIMIT 1').fetchone()
            if not scene:
                return {'scene': None, 'task': None}
            job = db.execute('SELECT * FROM jobs WHERE scene=? ORDER BY rowid DESC LIMIT 1', (scene['id'],)).fetchone()
            return {'scene': {'id': scene['id'], 'revision': scene['revision'], **json.loads(scene['state'])}, 'task': self.public(job), 'active': bool(db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','generating')").fetchone())}

    def scenes(self):
        with self.lock, self.db() as db:
            self.expire(db)
            rows = db.execute('SELECT * FROM scenes ORDER BY rowid DESC').fetchall()
            result = []
            for row in rows:
                state = json.loads(row['state'])
                task = db.execute('SELECT * FROM jobs WHERE scene=? ORDER BY rowid DESC LIMIT 1', (row['id'],)).fetchone()
                result.append({'id': row['id'], 'revision': row['revision'],
                    'cast': state['cast'], 'location': state['location'],
                    'experimental': True, 'world_id': state.get('world_id'),
                    'task_status': task['status'] if task else None})
            return {'scenes': result}

    def request(self, key):
        with self.lock, self.db() as db:
            self.expire(db)
            return {'task': self.public(db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())}

    def create(self, body):
        cast = body.get('cast')
        if not isinstance(cast, list) or not 1 <= len(cast) <= 2 or len(set(cast)) != len(cast) or any(n not in CAST for n in cast):
            raise rr.RoundError('请选择一至两位已登记角色')
        world_id = body.get('world_id')
        if world_id is not None and (not isinstance(world_id, str) or not world_id):
            raise rr.RoundError('隔离世界标记无效')
        world = self.world.snapshot(world_id) if world_id else None
        location = self.world.scene(world, cast) if world else body.get('location', '')
        if not isinstance(location, str) or not 1 <= len(location.strip()) <= 80:
            raise rr.RoundError('实验地点须为1至80字')
        with self.lock, self.db() as db:
            self.expire(db)
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','generating')").fetchone():
                raise rr.ConflictError('仍有交流请求未结束')
            key = secrets.token_hex(12)
            state = {'cast': cast, 'location': location.strip(), 'history': [], 'experimental': True}
            if world:
                state.update(world_id=world['world_id'], world_revision=world['world_revision'])
            db.execute('INSERT INTO scenes VALUES(?,?,?,?)', (key, 0, json.dumps(state, ensure_ascii=False), self.baseline()))
        return self.snapshot(key)

    def submit(self, body):
        key, text, sid = body.get('request_id'), body.get('input'), body.get('scene_id')
        if not isinstance(key, str) or not key.startswith('scene-') or len(key) > 100 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in key):
            raise rr.RoundError('无效请求ID')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise rr.RoundError('消息须为1至2000字')
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.expire(db)
            old = db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
            if old:
                if old['scene'] != sid or old['input'] != text or old['base'] != body.get('base_scene_revision'):
                    raise rr.ConflictError('相同请求ID不能替换输入或版本')
                return {'task': self.public(old)}
            scene = db.execute('SELECT * FROM scenes WHERE id=?', (sid,)).fetchone()
            if not scene or scene['revision'] != body.get('base_scene_revision'):
                raise rr.ConflictError('场景版本已改变，请恢复最新交流')
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','generating')").fetchone():
                raise rr.ConflictError('上一请求尚未结束')
            if scene['baseline'] != self.baseline():
                raise rr.ConflictError('原游戏事实已改变，请新建实验场景')
            state = json.loads(scene['state'])
            if len(state['history']) >= 24:
                raise rr.RoundError('首版24次交流边界已到；请保留记录后新建场景，不自动丢弃旧事实')
            references = self.references(text, state['history'])
            sources, characters, relationships = self.sources(state['cast'], references)
            world_context = None
            if state.get('world_id'):
                world = self.world.snapshot(state['world_id'])
                self.world.scene(world, state['cast'])
                sources.update(world['source_manifest'])
                world_context = self.world.context(world, state['cast'])
            payload = {'scene_id': sid, 'scene_revision': scene['revision'], 'source_manifest': sources,
                'scenario': {'location': state['location'], 'cast': state['cast'], 'experimental': True},
                'rules': (self.root / RULE).read_text(), 'characters': characters, 'referenced_entities': references,
                'relationships': relationships, 'accepted_history': state['history'], 'input': text}
            if world_context:
                payload['world_state'] = world_context
                payload['scenario'].update(world_id=state['world_id'], source='legacy_import')
            packet = self.directory / (key + '.txt')
            raw = encode_packet(payload)
            if len(raw) > 160000:
                raise rr.RoundError('会话包达到首版容量上限，不截断事实；请新建实验场景')
            packet.write_bytes(raw)
            data = {'path': packet.relative_to(self.root).as_posix(), 'hash': digest(raw),
                'sources': sources, 'through_line': len(raw.decode().splitlines())}
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                (key, sid, scene['revision'], text, 'queued', None, None, json.dumps(data), None, None))
            res = {'task': self.public(db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())}
        if getattr(self.story, 'hub', None):
            self.story.hub.publish('scene_task', {'id': key, 'status': 'queued'}, wake_worker=True)
        return res

    def expire(self, db):
        db.execute("UPDATE jobs SET status='interrupted',lease=NULL,error='连接中断；请显式重试原请求' WHERE status='generating' AND expires<?", (time.time(),))

    def retry(self, key):
        with self.lock, self.db() as db:
            self.expire(db)
            row = db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
            if not row or row['status'] not in ('failed', 'interrupted'):
                raise rr.RoundError('当前请求不可重试')
            scene = db.execute('SELECT * FROM scenes WHERE id=?', (row['scene'],)).fetchone()
            if scene['revision'] != row['base']:
                raise rr.ConflictError('版本已改变')
            data = json.loads(row['data'])
            self.check_sources(data)
            if scene['baseline'] != self.baseline():
                raise rr.ConflictError('原游戏事实已改变')
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','generating')").fetchone():
                raise rr.ConflictError('已有在途请求')
            db.execute("UPDATE jobs SET status='queued',lease=NULL,error=NULL WHERE id=?", (key,))
        if getattr(self.story, 'hub', None):
            self.story.hub.publish('scene_task', {'id': key, 'status': 'queued'}, wake_worker=True)
        return self.snapshot(row['scene'])

    def claim(self):
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.expire(db)
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return {'task': None}
            data = json.loads(row['data'])
            lease = secrets.token_urlsafe(24)
            db.execute("UPDATE jobs SET status='generating',lease=?,expires=? WHERE id=?", (lease, time.time()+660, row['id']))
            content = {'entry_mode': 'scene_chat', 'request_id': row['id'],
                'instruction': '这是隔离场景交流入口，不是完整回合。先完整真实读取packet及全部行，遵循其中场景交流规范，只返回messages/facts_delta/needs/handoff裸JSON；不得写文件或执行命令。当前packet是本任务权威上下文，不采用旧聊天的其他场景事实。',
                'packet': {'path': data['path'], 'through_line': data['through_line']},
                'output_contract': {'messages': [
                    {'kind': 'narration', 'speaker': '', 'text': '必要时交代现场环境'},
                    {'kind': 'action', 'speaker': '本场人物姓名', 'text': '必要时描述该人物场内动作'},
                    {'kind': 'dialogue', 'speaker': '本场人物姓名', 'text': '回应本次输入'}],
                    'facts_delta': [], 'needs': [], 'handoff': ''}}
            return {'task': {'entry_mode': 'scene_chat', 'request_id': row['id'], 'lease': lease,
                'scene_id': row['scene'], 'source_version': digest(json.dumps(data['sources'],sort_keys=True).encode()),
                'output_contract': content['output_contract'],
                'packet_bytes': (self.root/data['path']).stat().st_size, 'reading_preflight': 1, 'turns': [{'kind': 'user', 'content': json.dumps(content, ensure_ascii=False)}]}}

    def leased(self, db, key, lease):
        row = db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
        if not row or not isinstance(lease, str) or not row['lease'] or not secrets.compare_digest(lease, row['lease']):
            raise rr.ConflictError('请求租约失效')
        if row['status'] not in ('generating', 'committed'):
            raise rr.ConflictError('任务已结束')
        if row['status'] != 'committed' and row['expires'] < time.time():
            raise rr.ConflictError('请求租约过期')
        return row

    def check_sources(self, data):
        for name, expected in data['sources'].items():
            path = self.root/name
            if not path.is_file() or digest(path.read_bytes()) != expected:
                raise rr.ConflictError('源资料已改变，请建立新场景: ' + name)
        if digest((self.root/data['path']).read_bytes()) != data['hash']:
            raise rr.ConflictError('任务资料包已改变')
        packet = json.loads((self.root/data['path']).read_text())
        world_id = packet['scenario'].get('world_id')
        if world_id:
            self.world.assert_current(self.world.snapshot(world_id))

    def validate(self, row, body):
        data = json.loads(row['data'])
        self.check_sources(data)
        proof = body.get('conversation_audit', {})
        if not isinstance(proof, dict) or not isinstance(proof.get('outcome'), dict):
            raise rr.RoundError('会话审计结构无效')
        outcome = proof.get('outcome', {})
        if proof.get('api') != 'Tools.Chat.sendMessageStreaming' or outcome.get('type') != 'committed' or outcome.get('status') != 'completed' or not proof.get('chat_id') or not proof.get('participant_id'):
            raise rr.RoundError('缺少正式会话完成回执')
        if proof.get('snapshot_message_timestamp') != outcome.get('assistant', {}).get('messageTimestamp'):
            raise rr.RoundError('最终快照不匹配')
        covered = set()
        tools = proof.get('tools', [])
        if not isinstance(tools, list) or not 1 <= len(tools) <= 32:
            raise rr.RoundError('读取工具审计无效')
        raw = (self.root/data['path']).read_bytes()
        for call in tools:
            if call.get('name') not in ('read_file', 'read_file_full', 'read_file_part', 'file_info'):
                raise rr.RoundError('场景入口只允许读取指定资料包')
            params = call.get('parameters', {})
            if not isinstance(params, dict):
                raise rr.RoundError('工具参数结构无效')
            relative = self.story._audit_path(params.get('path'), proof.get('workspace'))
            if relative != data['path']:
                raise rr.RoundError('场景入口读取了非本任务包')
            if call.get('status') == 'success' and call['name'] != 'file_info':
                start = int(params.get('start_line', 1)); end = int(params.get('end_line', data['through_line']))
                try:
                    covered.update(sr.verified_lines(raw, call.get('result_text', ''), start, end))
                except sr.ReadingError as exc:
                    raise rr.RoundError(str(exc)) from exc
        if not set(range(1, data['through_line']+1)) <= covered:
            raise rr.RoundError('会话资料包正文未完整读取，截断须补读')
        result = rr.load_request(body.get('text', ''))
        if not isinstance(result, dict) or set(result) != {'messages', 'facts_delta', 'needs', 'handoff'}:
            raise rr.RoundError('场景响应字段无效')
        if result['facts_delta'] != [] or result['needs'] != []:
            raise rr.RoundError('首版事实增量/补读尚不支持；请只返回已有资料内交流或handoff')
        handoff = result['handoff']
        if handoff is not None and (not isinstance(handoff, str) or not 1 <= len(handoff) <= 300):
            raise rr.RoundError('转交说明无效')
        messages = result['messages']
        if not isinstance(messages, list) or not (0 if handoff else 1) <= len(messages) <= 8:
            raise rr.RoundError('消息数量无效')
        state = json.loads((self.root/data['path']).read_text())
        for m in messages:
            if not isinstance(m, dict) or set(m) != {'kind', 'speaker', 'text'} or not isinstance(m['text'], str) or not 1 <= len(m['text']) <= 800:
                raise rr.RoundError('消息结构或长度无效')
            if not ((m['kind'] == 'dialogue' and m['speaker'] in state['scenario']['cast'])
                    or (m['kind'] == 'action' and (m['speaker'] in state['scenario']['cast'] or m['speaker'] == '徐志北'))
                    or (m['kind'] == 'narration' and m['speaker'] == '')):
                raise rr.RoundError('未登记说话人或节点类型')
        return result

    def worker(self, key, action, body):
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.leased(db, key, body.get('lease'))
            if row['status'] == 'committed':
                return {'task': self.public(row), 'ready': True}
            if action == 'heartbeat':
                db.execute('UPDATE jobs SET expires=? WHERE id=?', (time.time()+660, key))
                return {'status': row['status']}
            if body.get('error'):
                db.execute("UPDATE jobs SET status='failed',error=?,lease=NULL WHERE id=?", (str(body['error'])[:500],key))
                return {'task': self.public(db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())}
            result = self.validate(row, body)
            scene = db.execute('SELECT * FROM scenes WHERE id=?',(row['scene'],)).fetchone()
            if scene['revision'] != row['base'] or scene['baseline'] != self.baseline():
                raise rr.ConflictError('场景或原游戏已改变')
            if action == 'preflight':
                return {'ready': True}
            if action != 'result':
                raise rr.RoundError('未知操作')
            data = json.loads(row['data'])
            packet = json.loads((self.root/data['path']).read_text())
            proof = body['conversation_audit']
            data['accepted_audit'] = {
                'api': proof['api'], 'chat_id': proof['chat_id'], 'participant_id': proof['participant_id'],
                'outcome': proof['outcome'], 'snapshot_message_timestamp': proof['snapshot_message_timestamp'],
                'packet_sha256': data['hash'], 'through_line': data['through_line'],
                'references': packet.get('referenced_entities', []),
                'tools': [{key: call.get(key) for key in ('name', 'parameters', 'status', 'result_text')}
                          for call in proof['tools']], 'verified_at': time.time()}
            db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data,ensure_ascii=False),key))
            state = json.loads(scene['state'])
            state['history'].append({'id':key, 'input':row['input'], **result})
            db.execute('UPDATE scenes SET revision=revision+1,state=? WHERE id=?', (json.dumps(state,ensure_ascii=False),row['scene']))
            db.execute("UPDATE jobs SET status='committed',result=?,error=NULL WHERE id=?",(json.dumps(result,ensure_ascii=False),key))
            return {'task':self.public(db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())}


def register_scene_routes(app, root, story):
    from flask import request, jsonify, send_from_directory
    service = SceneService(root, story)
    app.extensions['scene_chat'] = service

    def body():
        value = rr.load_request(request.get_data(as_text=True))
        if not isinstance(value, dict):
            raise rr.RoundError('请求必须是JSON对象')
        return value

    @app.get('/api/story/scene/audit/<key>')
    def scene_audit(key):
        with service.lock, service.db() as db:
            row = db.execute('SELECT data,status FROM jobs WHERE id=?', (key,)).fetchone()
            if not row:
                raise rr.RoundError('交流任务不存在')
            data = json.loads(row['data'])
            audit = data.get('accepted_audit')
            return jsonify({'request_id': key, 'status': row['status'], 'audit_available': audit is not None,
                'audit': audit, 'note': '覆盖校验仅证明资料已读，不证明模型充分运用了设定。'})

    @app.get('/api/story/scene/world')
    def scene_world():
        return jsonify(service.world.status(request.args.get('id')))

    @app.post('/api/story/scene/world/import')
    def scene_world_import():
        body()
        with service.lock, service.db() as db:
            service.expire(db)
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','generating')").fetchone():
                raise rr.ConflictError('交流请求未结束，请稍后导入')
            world = service.world.import_latest()
        return jsonify({'world': world, 'source_current': True, 'source_error': ''})

    @app.get('/api/story/scene/connection')
    def scene_connection():
        status = story.status()
        bridge = status.get('bridge', {})
        return jsonify({'origin': request.host_url.rstrip('/'), 'scene_protocol': 3, 'message_kinds': ['dialogue', 'action', 'narration'], 'live_page': '/scene-live',
            'world_state_protocol': 1, 'world_mode': 'isolated_read_only',
            'workspace_id': digest(str(service.root).encode())[:16],
            'bridge': {key: bridge.get(key) for key in
                ('present', 'running', 'phase', 'plugin_version', 'last_error')}})

    @app.post('/api/story/scene/worker/claim')
    def scene_claim():
        return jsonify(service.claim())

    @app.get('/api/story/scene/list')
    def scene_list():
        return jsonify(service.scenes())

    @app.get('/api/story/scene/request/<key>')
    def scene_request(key):
        return jsonify(service.request(key))

    @app.get('/scene-live')
    def scene_live_page():
        return send_from_directory(str(Path(root) / 'scene_chat_dev/src/scene_live'), 'index.html')

    @app.get('/scene-live/assets/<name>')
    def scene_live_asset(name):
        if name not in ('live.css', 'live.js'):
            from flask import abort
            abort(404)
        return send_from_directory(str(Path(root) / 'scene_chat_dev/src/scene_live'), name)

    @app.get('/scene-chat')
    def scene_page():
        return send_from_directory(str(root), 'scene_chat.html')

    @app.get('/api/story/scene')
    def scene_snapshot():
        return jsonify(service.snapshot(request.args.get('id')))

    @app.post('/api/story/scene')
    def scene_create():
        return jsonify(service.create(body()))

    @app.post('/api/story/scene/messages')
    def scene_submit():
        return jsonify(service.submit(body()))

    @app.post('/api/story/scene/retry/<key>')
    def scene_retry(key):
        return jsonify(service.retry(key))

    @app.post('/api/story/scene/worker/<key>/<action>')
    def scene_worker(key, action):
        return jsonify(service.worker(key, action, body()))

    return service

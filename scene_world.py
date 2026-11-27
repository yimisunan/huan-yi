"""Read-only legacy snapshots for scene chat. No legacy settlement or model calls."""
import contextlib
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

import round_runtime as rr
import save_store

ENTITIES = 'txt文件/关系称谓库.json'
VISIBILITY = 'scene_chat_dev/src/legacy_visibility.json'
EMPTY = {'', '（空）', '(空)', '（无）', '(无)', '无', '（当前为空）'}
LAYERS = ('▲ 第一层：', '▲ 第二层：', '▲ 第三层：', '▲ 第四层：')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class LegacyWorld:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._store = None
        self.directory = self.root / '.scene-chat/world'

    @property
    def store(self):
        if self._store is None:
            self._store = rr.RoundStore(self.root)
        return self._store

    @contextlib.contextmanager
    def read_lock(self):
        """Use RoundStore's exact FUSE-safe locks, but never call its recovery/publish hooks."""
        if not self.store.thread_lock.acquire(timeout=10):
            raise rr.ConflictError('旧回合正在提交，请稍后导入')
        try:
            self.store.runtime.mkdir(exist_ok=True)
            with rr.acquire_process_lock(self.root, timeout=10.0, conflict_message='旧回合正在提交，请稍后导入'):
                for name in ('journal.json', 'reset-journal.json'):
                    if (self.store.runtime/name).exists():
                        raise rr.RecoveryError('旧存档有未恢复事务；请先由原执行器恢复，再导入')
                yield
        finally:
            self.store.thread_lock.release()

    def sources(self):
        result = {}
        optional = {save_store.SAVE_STATE_PATH, save_store.MEMORY_LAYERS_PATH}
        for name in (*rr.FILES, ENTITIES, VISIBILITY):
            path = self.store._path(name)
            if not path.is_file():
                if name in optional:
                    continue
                raise rr.RoundError('缺少导入来源: ' + name)
            result[name] = path.read_bytes()
        return result

    @contextlib.contextmanager
    def db(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory/'state.sqlite3'
        if not path.resolve().is_relative_to(self.root):
            raise rr.RoundError('隔离账本路径越界')
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS imports(sequence INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
          created REAL NOT NULL, manifest TEXT NOT NULL, payload TEXT NOT NULL, payload_sha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(world_id TEXT NOT NULL, path TEXT NOT NULL,
          sha256 TEXT NOT NULL, body BLOB NOT NULL, PRIMARY KEY(world_id,path));
        ''')
        try:
            with db:
                yield db
        finally:
            db.close()

    def parse(self, sources):
        texts = {name: raw.decode('utf-8-sig') for name, raw in sources.items()}
        memory = texts[rr.FILES[0]]
        data = rr.load_request(texts['data.json'])
        registry = rr.load_request(texts[ENTITIES])['entities']
        visibility = rr.load_request(texts[VISIBILITY])
        manifest = {name: sha(raw) for name, raw in sources.items()}
        unresolved, records = [], []
        entities = {name for name, value in registry.items() if value.get('status') in ('active', 'deceased')}
        lines = memory.splitlines()

        def origin(path, start, end, raw):
            return {'path': path, 'sha256': manifest[path], 'start_line': start, 'end_line': end, 'raw': raw}

        def issue(domain, source, reason):
            unresolved.append({'kind': 'unresolved_source', 'domain': domain, 'reason': reason, 'origin': source})

        def span(anchor, stop=None):
            hits = [i for i, line in enumerate(lines) if line.strip() == anchor or (anchor in LAYERS and line.startswith(anchor))]
            if not hits:
                issue(anchor, origin(rr.FILES[0], 1, len(lines), ''), '缺少区块，不推断空值')
                return []
            start = hits[0] + 1
            end = len(lines)
            for i in range(start, len(lines)):
                line = lines[i]
                if (stop and line.startswith(stop)) or (not stop and (line.startswith('【') or line.startswith('▲ ') or re.fullmatch('={5,}', line))):
                    end = i
                    break
            return [(i+1, lines[i]) for i in range(start, end)]

        def record(kind, subject, predicate, value, source, known_by=None):
            result = {'record_id': sha(packed([kind, subject, predicate, source]).encode())[:24],
                      'kind': kind, 'subject': subject, 'predicate': predicate, 'value': value,
                      'origin': source, 'known_by': known_by, 'evidence_message_ids': []}
            records.append(result)
            return result

        presence, panels = {}, {}
        current = memory.split('▶ 上回合历史快照', 1)[0].split('▲ 第一层：', 1)[0]
        for number, line in enumerate(current.splitlines(), 1):
            source = origin(rr.FILES[0], number, number, line)
            m = re.fullmatch(r'([^：]+)：([^|]+) \| 事由：(.*)', line)
            if m and m[1] in entities:
                if m[1] in presence:
                    raise rr.RoundError('旧存档当前位置重复: ' + m[1])
                presence[m[1]] = record('fact', m[1], 'location', {'location': m[2].strip(), 'reason': m[3].strip()}, source)
            m = re.fullmatch(r'\[([^\]]+)\]\s*(.*)', line)
            if m:
                name = '徐志北' if m[1] == '系统宿主' else m[1]
                if name not in entities or name in panels:
                    issue('panel', source, '面板实体未登记或重复')
                    continue
                values = {}
                for field in m[2].split('|'):
                    pair = re.fullmatch(r'\s*(\S+)\s+(-?\d+%?|-?\d+次|True|False|Lv\.\d+)\s*', field)
                    if not pair:
                        issue('panel', source, '数值格式不明，保留原文')
                        continue
                    key, raw = pair.groups()
                    if key in values:
                        raise rr.RoundError('面板字段重复: ' + key)
                    value = int(raw) if re.fullmatch(r'-?\d+', raw) else {'True': True, 'False': False}.get(raw, raw)
                    values[key] = value
                panels[name] = record('fact', name, 'panel', values, source, [name])
        if '徐志北' not in presence:
            issue('presence', origin(rr.FILES[0], 1, len(lines), ''), '缺少玩家位置')
        if not isinstance(data, dict) or not isinstance(data.get('presence'), dict) or type(data.get('round')) is not int:
            raise rr.RoundError('旧展示快照缺少有效round/presence')
        expected_presence = {name: item['value'] for name, item in presence.items()}
        if data['presence'] != expected_presence:
            raise rr.ConflictError('data.json与记忆库人物所在不一致，保留旧源，请先核查')

        tasks = {'current': None, 'history': [], 'pending_item': None, 'pending_items': []}
        task_rows = span('【任务状态】')
        task_text = '\n'.join(value for _, value in task_rows)
        if task_rows:
            source = origin(rr.FILES[0], task_rows[0][0], task_rows[-1][0], task_text)
            match = re.search(r'^当前任务：(TASK-\d+) \| ([^|]+) \| ([^|·]+)·([^|·]+)·(\d+) \| (\w+) \| ([^|]+) \| (\S+) \|发布回合(\d+)(?: \|完成回合(\d+))?$', task_text, re.M)
            if match:
                tasks['current'] = dict(zip(('id','title','target','attr','value','tier','item_desc','status','issue_round','complete_round'), [v.strip() if v else v for v in match.groups()]))
            elif not re.search(r'^当前任务：[（(]无[）)]$', task_text, re.M):
                issue('tasks', source, '当前任务无法解析，不等同无任务')
            if not re.search(r'^最近完成：[（(]空[）)]$', task_text, re.M):
                hist_block = task_text.split('待发道具：', 1)[0]
                tasks['history'] = [v.strip() for v in hist_block.splitlines() if re.match(r'^\s+TASK-\d+', v)]
                if not tasks['history']:
                    issue('tasks', source, '最近完成无法解析')
            pending = re.search(r'^待发道具：(.*)$', task_text, re.M)
            if pending:
                inline = pending[1].strip()
                if inline and inline not in EMPTY:
                    tasks['pending_items'] = [inline]
                    tasks['pending_item'] = inline
                    if not re.fullmatch(r'TASK-\d+ \| [^|]+ \|完成回合\d+', inline):
                        issue('tasks', source, '待发道具无法解析')
                elif not inline:
                    after_pending = task_text[pending.end():]
                    items_p = [ln.strip() for ln in after_pending.splitlines() if re.match(r'^\s+TASK-\d+', ln)]
                    tasks['pending_items'] = items_p
                    tasks['pending_item'] = items_p[0] if items_p else None
                    for p_it in items_p:
                        if not re.fullmatch(r'TASK-\d+ \| [^|]+ \|完成回合\d+', p_it):
                            issue('tasks', source, '待发道具无法解析')
            else:
                issue('tasks', source, '缺少待发道具行')
            tasks['origin'] = source
        states = {}
        for anchor in ('【当前激活微状态】', '【当前持久化状态与BUFF】', '【回合计数器】', '【监视状态】', '【道具倒计时】', '【回合生命周期】'):
            rows = span(anchor)
            states[anchor] = origin(rr.FILES[0], rows[0][0], rows[-1][0], '\n'.join(v for _, v in rows)) if rows else None
        for opt_anchor in ('【商城与回响状态】', '【商业情报与杠杆状态】', '【情欲与空间态势】', '【世界导演状态】'):
            if any(line.strip() == opt_anchor for line in lines):
                rows = span(opt_anchor)
                states[opt_anchor] = origin(rr.FILES[0], rows[0][0], rows[-1][0], '\n'.join(v for _, v in rows)) if rows else None

        memories = []
        positions = []
        for anchor in LAYERS:
            found = [i for i, line in enumerate(lines) if line.startswith(anchor)]
            if len(found) != 1:
                raise rr.RoundError('记忆层锚点缺失或不唯一: ' + anchor)
            positions.append(found[0])
        if positions != sorted(positions):
            raise rr.RoundError('记忆层顺序无效')
        approved = visibility.get('entries', {})
        json_known_queues = {}
        prologue_from_json = False
        if save_store.MEMORY_LAYERS_PATH in texts:
            try:
                layers_meta = json.loads(texts[save_store.MEMORY_LAYERS_PATH])
                prologue_from_json = bool(layers_meta.get('prologue_active'))
                if isinstance(layers_meta.get('episodes'), list):
                    eps = layers_meta.get('episodes') or []
                    for idx_ep, ep in enumerate(eps):
                        if not isinstance(ep, dict):
                            continue
                        kb = ep.get('known_by')
                        if isinstance(kb, list) and kb and set(kb) <= entities:
                            day_i = max(1, int(ep.get('day') or 1))
                            lkey = 'L1' if idx_ep >= max(0, len(eps) - 3) else 'L2'
                            json_known_queues.setdefault((lkey, day_i, day_i), []).append(sorted(set(kb)))
                else:
                    layer_map = layers_meta.get('layers') if isinstance(layers_meta.get('layers'), dict) else layers_meta
                    for lkey in ('L1', 'L2', 'L3', 'L4'):
                        for j_entry in layer_map.get(lkey, []) if isinstance(layer_map.get(lkey), list) else []:
                            if not isinstance(j_entry, dict):
                                continue
                            kb = j_entry.get('known_by')
                            if isinstance(kb, list) and kb and set(kb) <= entities:
                                sr_i = int(j_entry.get('start_round') or j_entry.get('round') or 1)
                                er_i = int(j_entry.get('end_round') or sr_i)
                                json_known_queues.setdefault((lkey, sr_i, er_i), []).append(sorted(set(kb)))
            except (ValueError, TypeError):
                prologue_from_json = False
        for index, start in enumerate(positions):
            end = positions[index+1] if index < 3 else len(lines)
            body = '\n'.join(lines[start+1:end]).strip()
            if body in EMPTY:
                continue
            entries = list(re.finditer(r'(?m)^【(\d+)(?:-(\d+))?】[^\n]*(?:\n(?!【\d).*)*', body))
            residual = re.sub(r'(?m)^【(\d+)(?:-(\d+))?】[^\n]*(?:\n(?!【\d).*)*', '', body).strip()
            if residual or not entries:
                issue('memory', origin(rr.FILES[0], start+2, end, body), '记忆层有未识别正文')
            lkey = 'L' + str(index + 1)
            for entry in entries:
                raw = entry[0].strip()
                hit = next(i for i in range(start+1, end) if lines[i] == raw.splitlines()[0])
                source = origin(rr.FILES[0], hit+1, hit+len(raw.splitlines()), raw)
                fingerprint = sha(raw.encode())
                rule = approved.get(fingerprint)
                known = None
                vis_basis = None
                sr_i, er_i = int(entry[1]), int(entry[2] or entry[1])
                q_key = (lkey, sr_i, er_i)
                if isinstance(rule, dict) and rule.get('basis') and isinstance(rule.get('known_by'), list) and rule['known_by'] and set(rule['known_by']) <= entities:
                    known = sorted(set(rule['known_by']))
                    vis_basis = rule['basis']
                elif json_known_queues.get(q_key):
                    q = json_known_queues[q_key]
                    known = q.pop(0) if len(q) > 1 else q[0]
                    vis_basis = 'memory_layers_json'
                item = record('legacy_memory', '', 'memory', raw, source, known)
                item.update(layer=lkey, start_round=sr_i, end_round=er_i, text_sha256=fingerprint)
                if known is None:
                    issue('memory_visibility', source, '旧记忆没有可靠知情名单；保留供玩家核对，不发给人物')
                else:
                    item['visibility_basis'] = vis_basis
                memories.append(item)

        item_text = texts[rr.FILES[1]]
        active_marker = '▼ 活跃道具区 ▼'
        deployed_marker = '▼ 已部署装置区 ▼'
        delivered_marker = '▼ 已交付道具区 ▼'
        history_marker = '▼ 已过期/已消耗道具历史区 ▼'
        if item_text.count(active_marker) != 1 or item_text.count(history_marker) != 1:
            raise rr.RoundError('道具活跃/历史锚点缺失或不唯一')
        active_start = item_text.index('\n', item_text.index(active_marker)) + 1
        end_candidates = [item_text.index(history_marker)]
        if deployed_marker in item_text:
            end_candidates.append(item_text.index(deployed_marker))
        if delivered_marker in item_text:
            end_candidates.append(item_text.index(delivered_marker))
        active_end = min(end_candidates)
        if active_end <= active_start:
            raise rr.RoundError('道具区域顺序无效')
        zone = item_text[active_start:active_end]
        items = []
        matches = list(re.finditer(r'(?m)^【道具名称】：([^\n]+)\n[\s\S]*?(?=\n\n【道具名称】|\n=|\Z)', zone))
        ids = set()
        for match in matches:
            raw = match[0].strip()
            start = item_text[:active_start+match.start()].count('\n')+1
            source = origin(rr.FILES[1], start, start+len(raw.splitlines())-1, raw)
            fields = dict(re.findall(r'^【([^】]+)】：([^\n]*)$', raw, re.M))
            item_id, quantity = fields.get('道具ID'), fields.get('数量')
            if not item_id or not re.fullmatch(r'ITEM-\d+', item_id) or item_id in ids or not quantity or not quantity.isdigit():
                issue('items', source, '道具ID/数量缺失、重复或格式不明，不猜默认值')
                continue
            ids.add(item_id)
            items.append({'id': item_id, 'name': match[1], 'quantity': int(quantity), 'catalog_owner': '徐志北', 'fields': fields, 'origin': source})
        residual = zone
        for match in reversed(matches):
            residual = residual[:match.start()]+residual[match.end():]
        residual = re.sub(r'(?m)^=+\s*$', '', residual).strip()
        if residual and residual not in EMPTY and residual != '（新游戏初始仓库为空，兑换道具后由注入逻辑写入此区域）':
            start = item_text[:active_start].count('\n')+1
            issue('items', origin(rr.FILES[1], start, item_text[:active_end].count('\n'), zone), '活跃区有未识别正文')

        # 存档/次要NPC名册.txt has been retired; keep empty npcs list for schema compatibility.
        npcs = []

        tasks['import_status'] = 'unresolved' if any(v['domain'] in ('tasks', '【任务状态】') for v in unresolved) else 'parsed'
        last_round = max((entry['end_round'] for entry in memories), default=0)
        prologue = (len(memories) == 1 and (rr.PROLOGUE in memories[0]['value'] or prologue_from_json))
        valid_rounds = {0, 1} if prologue else {last_round, last_round + 1}
        if data['round'] not in valid_rounds:
            raise rr.ConflictError('旧记忆与展示快照的回合不一致，停止导入')

        # Display metadata is not an event or a set of executable options.
        snapshot = {key: data.get(key) for key in ('round', 'state_version', 'request_id', 'sceneTitle')}
        snapshot.update(options_expired=True, story_nodes_imported_as_facts=False)
        return {'schema_version': 1, 'mode': 'isolated_read_only', 'legacy_revision': rr._revision({name: sources.get(name) for name in rr.FILES}),
                'source_manifest': manifest, 'entities': sorted(entities), 'presence': presence, 'panels': panels,
                'tasks': tasks, 'items': items, 'npcs': npcs, 'memories': memories, 'records': records,
                'state_sections': states, 'legacy_snapshot': snapshot, 'unresolved_source': unresolved,
                'actions_enabled': False, 'cost_policy': 'unconfigured'}

    def import_latest(self):
        with self.read_lock():
            sources = self.sources()
            manifest = {name: sha(raw) for name, raw in sources.items()}
            key = sha(packed({'schema': 1, 'sources': manifest}).encode())
            payload = self.parse(sources)
            raw = packed(payload)
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT OR IGNORE INTO imports(id,created,manifest,payload,payload_sha) VALUES(?,?,?,?,?)',
                           (key, time.time(), packed(manifest), raw, sha(raw.encode())))
                for name, content in sources.items():
                    db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?)', (key, name, manifest[name], content))
            return self.snapshot(key)

    def snapshot(self, world_id=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM imports WHERE id=?', (world_id,)).fetchone() if world_id else db.execute('SELECT * FROM imports ORDER BY sequence DESC LIMIT 1').fetchone()
            if not row:
                if world_id:
                    raise rr.RoundError('隔离世界版本不存在')
                return None
            if sha(row['payload'].encode()) != row['payload_sha']:
                raise rr.RecoveryError('隔离世界内容指纹不符，停止使用')
            payload = json.loads(row['payload'])
            originals = db.execute('SELECT * FROM sources WHERE world_id=?', (row['id'],)).fetchall()
            manifest = {item['path']: item['sha256'] for item in originals}
            if (manifest != payload['source_manifest'] or json.loads(row['manifest']) != manifest
                    or any(sha(item['body']) != item['sha256'] for item in originals)):
                raise rr.RecoveryError('隔离来源原文或清单指纹不符，停止使用')
            return {'world_id': row['id'], 'world_revision': row['sequence'], 'imported_at': row['created'], **payload}

    def assert_current(self, world):
        with self.read_lock():
            current = {name: sha(raw) for name, raw in self.sources().items()}
        if current != world['source_manifest']:
            raise rr.ConflictError('旧存档或导入依据已改变，请重新导入并建立存档场景；原记录保留')

    def status(self, world_id=None):
        world = self.snapshot(world_id)
        if not world:
            return {'world': None, 'source_current': None, 'source_error': ''}
        error = ''
        try:
            self.assert_current(world)
        except (rr.RoundError, OSError) as exc:
            error = str(exc)
        return {'world': world, 'source_current': not error, 'source_error': error}

    def scene(self, world, cast):
        self.assert_current(world)
        player = world['presence'].get('徐志北')
        if not player:
            raise rr.RoundError('存档缺少玩家当前位置，请先核查待确认项')
        location = player['value']['location']
        for name in cast:
            value = world['presence'].get(name)
            if not value or value['value']['location'] != location:
                raise rr.RoundError('该人物未在玩家存档地点，暂不支持移动或远程交流: ' + name)
        return location

    def context(self, world, cast):
        participants = {'徐志北', *cast}
        memories = [entry for entry in world['memories'] if entry['known_by'] and participants <= set(entry['known_by'])]
        return {'world_id': world['world_id'], 'world_revision': world['world_revision'],
                'legacy_revision': world['legacy_revision'], 'mode': world['mode'],
                'presence': {name: world['presence'][name] for name in participants if name in world['presence']},
                'shared_memories': memories,
                'private_state': {name: world['panels'][name] for name in participants if name in world['panels']},
                'inventory': {'owner': '徐志北', 'items': world['items'], 'import_status': 'unresolved' if any(v['domain'] == 'items' for v in world['unresolved_source']) else 'parsed', 'visibility': 'player_private_not_shared_knowledge'},
                'tasks': {'value': world['tasks'], 'visibility': 'player_private_not_shared_knowledge'},
                'scene_snapshot': {'title': world['legacy_snapshot']['sceneTitle'], 'round': world['legacy_snapshot']['round'], 'scope': 'display_metadata_not_new_fact'},
                'knowledge_policy': 'shared_memories仅共同知情；private_state只约束对应人物，不是可说出口的信息。缺席人物、全局原文、未知知情记忆不注入。',
                'actions_enabled': False, 'cost_policy': 'unconfigured'}

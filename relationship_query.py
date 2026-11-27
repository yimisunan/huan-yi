"""Read-only, directional relationship queries; no round or dialogue writes."""
import argparse
import hashlib
import json
import threading
from pathlib import Path

SOURCE = 'txt文件/关系称谓库.json'
VIEW = 'txt文件/关系称谓查询.jsonl'
RESOLVER = 'relationship_query.py'
OCCASIONS = ('formal', 'relaxed', 'business', 'intimate')

_CACHE_LOCK = threading.RLock()
_REG_CACHE = {}
_VIEW_CACHE = {}
_MAX_CACHE_ENTRIES = 32


def _stat_sig(path):
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


ELDER_ROLES = frozenset({'mother', 'adoptive_mother', 'mother_in_law', 'father'})
SENIOR_ADDRESS_ROLES = ELDER_ROLES | frozenset({'elder_brother', 'elder_sister', 'sister_in_law'})


class RelationshipError(ValueError):
    pass


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise RelationshipError('关系资料有重复键: ' + key)
        result[key] = value
    return result


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class RelationshipRegistry:
    def __init__(self, root):
        self.root = Path(root).resolve()
        src_path = self._path(SOURCE)
        sig = None
        try:
            sig = _stat_sig(src_path)
            with _CACHE_LOCK:
                cached = _REG_CACHE.get(sig)
            if cached is not None:
                self.raw, self.data, self.source = cached
                return
        except OSError:
            sig = None
        self.raw = src_path.read_bytes()
        if len(self.raw) > 1024 * 1024:
            raise RelationshipError('关系资料超过1MiB')
        try:
            self.data = json.loads(self.raw, object_pairs_hook=_pairs,
                                   parse_constant=lambda value: self._fail('关系资料含非有限数字'))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RelationshipError('关系资料不是有效UTF-8 JSON') from exc
        try:
            self._validate()
        except (KeyError, TypeError) as exc:
            raise RelationshipError("关系资料字段类型无效") from exc
        self.source = {'path': SOURCE, 'version': 1, 'sha256': _sha(self.raw)}
        if sig is not None:
            with _CACHE_LOCK:
                if len(_REG_CACHE) >= _MAX_CACHE_ENTRIES:
                    _REG_CACHE.pop(next(iter(_REG_CACHE)), None)
                _REG_CACHE[sig] = (self.raw, self.data, self.source)

    @staticmethod
    def _fail(message):
        raise RelationshipError(message)

    def _path(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            self._fail('关系资料越出工作区')
        return path

    def _validate(self):
        d = self.data
        expected = {'version', 'entities', 'types', 'facts', 'roles', 'title_rules', 'beliefs', 'selection'}
        if not isinstance(d, dict) or set(d) != expected or type(d['version']) is not int or d['version'] != 1:
            self._fail('关系资料结构或版本无效')
        for key in ('entities', 'types', 'facts', 'roles', 'beliefs'):
            if not isinstance(d[key], dict) or not d[key]:
                self._fail('关系资料缺少对象: ' + key)
        entities, roles = d['entities'], d['roles']
        for name, item in entities.items():
            if (not isinstance(item, dict) or set(item) != {'short', 'status'}
                    or not name or not isinstance(item['short'], str) or not item['short']
                    or item['status'] not in {'active', 'deceased', 'category'}):
                self._fail('关系人物结构无效')
        for item in roles.values():
            if not isinstance(item, dict) or set(item) != {'label', 'self', 'address'} or not isinstance(item['label'], str):
                self._fail('关系角色词表无效')
            for mode in ('self', 'address'):
                forms = item[mode]
                if not isinstance(forms, dict) or set(forms) != set(OCCASIONS):
                    self._fail('称谓场合必须完整枚举')
                for terms in forms.values():
                    if (not isinstance(terms, list) or any(not isinstance(x, str) or not x for x in terms)
                            or len(set(terms)) != len(terms)):
                        self._fail('称谓候选须为不重复的非空字符串')
        for item in d['types'].values():
            if (not isinstance(item, dict) or set(item) != {'layer', 'roles'}
                    or item['layer'] not in {'blood', 'social', 'legal'}
                    or not isinstance(item['roles'], list) or len(item['roles']) not in {0, 2}
                    or any(r not in roles for r in item['roles'])):
                self._fail('关系类型无效')
        seen = set()
        for item in d['facts'].values():
            if not isinstance(item, dict) or set(item) != {'type', 'subject', 'object', 'known_by', 'text'}:
                self._fail('关系事实结构无效')
            if (item['type'] not in d['types'] or item['subject'] not in entities or item['object'] not in entities
                    or item['subject'] == item['object'] or not isinstance(item['text'], str) or not item['text']):
                self._fail('关系事实引用无效')
            known = item['known_by']
            if known != '*':
                if (not isinstance(known, list) or not known or len(set(known)) != len(known)
                        or any(x not in entities or entities[x]['status'] != 'active' for x in known)):
                    self._fail('知情资格须为明确人物名单')
            relation = d['types'][item['type']]
            signature = (relation['layer'], frozenset((item['subject'], item['object'])))
            if signature in seen:
                self._fail('同层关系事实重复或反向双写')
            seen.add(signature)
            if relation['roles'] and known == '*' and any(entities[x]['status'] == 'category' for x in (item['subject'], item['object'])):
                self._fail('人物类别不能充当亲属事实')
        if not isinstance(d['title_rules'], list):
            self._fail('身份称谓规则无效')
        for item in d['title_rules']:
            keys = set(item) if isinstance(item, dict) else set()
            target = item.get('target', 'self') if isinstance(item, dict) else None
            if (not isinstance(item, dict)
                    or not ({'speaker', 'listener', 'fact', 'forms'} <= keys <= {'speaker', 'listener', 'fact', 'forms', 'target'})
                    or target not in {'self', 'address'}
                    or item['speaker'] not in entities or item['listener'] not in entities or item['fact'] not in d['facts']
                    or not isinstance(item['forms'], dict) or set(item['forms']) != set(OCCASIONS)
                    or any(not isinstance(v, list) or any(not isinstance(s, str) or not s for s in v) for v in item['forms'].values())):
                self._fail('身份称谓引用无效')
        for item in d['beliefs'].values():
            if (not isinstance(item, dict) or set(item) != {'holder', 'text'} or item['holder'] not in entities
                    or not isinstance(item['text'], str) or not item['text']):
                self._fail('人物信念结构无效')
        if (not isinstance(d['selection'], dict) or set(d['selection']) != {'optional', 'rule'}
                or d['selection']['optional'] is not True or not isinstance(d['selection']['rule'], str)):
            self._fail('称谓必须保留选择及省略自由')

    def _entity(self, name, *, speaking=False):
        if not isinstance(name, str) or name not in self.data['entities']:
            self._fail('未知关系人物')
        item = self.data['entities'][name]
        if speaking and item['status'] == 'deceased':
            self._fail('已故人物不能作为当前说话者')
        return item

    @staticmethod
    def _visible(fact, people):
        return fact['known_by'] == '*' or set(people) <= set(fact['known_by'])

    def _fact(self, key, item):
        return {'id': key, 'type': item['type'], 'layer': self.data['types'][item['type']]['layer'],
                'subject': item['subject'], 'object': item['object'], 'text': item['text'],
                'source': '#/facts/' + key}

    @staticmethod
    def _form(text, kind, *sources):
        return {'text': text, 'kind': kind, 'sources': list(sources)}

    @staticmethod
    def _merge(forms):
        result = {}
        for form in forms:
            key = form['text']
            if key not in result:
                result[key] = dict(form, sources=list(form['sources']))
            else:
                result[key]['sources'] = sorted(set(result[key]['sources'] + form['sources']))
        return list(result.values())

    def _neutral(self, person, mode, include_short=True):
        entity = self.data['entities'][person]
        ref = '#/entities/' + person + '/short'
        allow_short = include_short and not (mode == 'self' and entity['status'] == 'category')
        if mode == 'self':
            items = [self._form('我', 'pronoun', '#/selection')]
            if allow_short:
                items.append(self._form(entity['short'], 'name', ref))
            items.append(self._form('', 'omit', '#/selection'))
            return items
        items = []
        if allow_short:
            items.append(self._form(entity['short'], 'name', ref))
        items.extend([self._form('你', 'pronoun', '#/selection'), self._form('', 'omit', '#/selection')])
        return items

    def query(self, speaker, listeners, occasion):
        self._entity(speaker, speaking=True)
        if not isinstance(occasion, str) or occasion not in OCCASIONS:
            self._fail('场合须为formal/relaxed/business/intimate')
        if listeners is None:
            listeners = []
        if (not isinstance(listeners, list) or len(listeners) > len(self.data['entities'])
                or any(not isinstance(x, str) for x in listeners) or len(set(listeners)) != len(listeners)):
            self._fail('听话者须为不重复的明确人物数组')
        for listener in listeners:
            self._entity(listener, speaking=True)
            if listener == speaker:
                self._fail('说话者与听话者不能相同')
        people = [speaker, *listeners]
        groups, targets, facts = [], [], {}
        for listener in listeners:
            matched_roles = []
            for key, item in self.data['facts'].items():
                if set((speaker, listener)) != {item['subject'], item['object']} or not self._visible(item, people):
                    continue
                roles = self.data['types'][item['type']]['roles']
                if not roles:
                    continue
                sr, lr = roles if speaker == item['subject'] else list(reversed(roles))
                matched_roles.append((key, item, sr, lr))
            speaker_is_category = self.data['entities'][speaker]['status'] == 'category'
            listener_is_elder = any(lr in ELDER_ROLES for _, _, _, lr in matched_roles)
            listener_is_senior = any(lr in SENIOR_ADDRESS_ROLES for _, _, _, lr in matched_roles)
            own = self._neutral(speaker, 'self', include_short=(listener_is_elder and not speaker_is_category))
            address = self._neutral(listener, 'address', include_short=(not listener_is_senior and not speaker_is_category))
            relations = []
            for key, item, sr, lr in matched_roles:
                facts[key] = self._fact(key, item)
                relations.append({'speaker_role': self.data['roles'][sr]['label'],
                                  'listener_role': self.data['roles'][lr]['label'], 'fact': '#/facts/' + key})
                for mode, role, forms in (('self', sr, own), ('address', lr, address)):
                    for term in self.data['roles'][role][mode][occasion]:
                        forms.append(self._form(term, 'kinship', '#/facts/' + key, '#/roles/' + role + '/' + mode + '/' + occasion))
            for i, rule in enumerate(self.data['title_rules']):
                if (rule['speaker'], rule['listener']) == (speaker, listener):
                    item = self.data['facts'][rule['fact']]
                    if self._visible(item, people):
                        facts[rule['fact']] = self._fact(rule['fact'], item)
                        bucket = address if rule.get('target', 'self') == 'address' else own
                        bucket.extend(self._form(term, 'title', '#/facts/' + rule['fact'], '#/title_rules/' + str(i))
                                      for term in rule['forms'][occasion])
            groups.append(self._merge(own))
            targets.append({'listener': listener, 'relations': relations, 'address_candidates': self._merge(address)})
        if groups:
            common = set.intersection(*({x['text'] for x in group} for group in groups))
            candidates = self._merge(x for group in groups for x in group if x['text'] in common)
        else:
            candidates = self._neutral(speaker, 'self', include_short=False)
            # Unknown audience permits public identity facts only, including deceased relatives.
            for key, item in self.data['facts'].items():
                if item['known_by'] == '*' and speaker in {item['subject'], item['object']}:
                    facts[key] = self._fact(key, item)
        return {'speaker': speaker, 'listeners': listeners, 'occasion': occasion,
                'self_candidates': candidates, 'targets': targets, 'facts': list(facts.values()),
                'source': self.source, 'selection': self.data['selection']}

    def knowledge(self, perspective):
        self._entity(perspective, speaking=True)
        return {'perspective': perspective,
                'facts': [self._fact(k, f) for k, f in self.data['facts'].items()
                          if f['known_by'] != '*' and self._visible(f, [perspective])],
                'beliefs': [{'text': f['text'], 'status': 'belief_not_fact', 'source': '#/beliefs/' + k}
                            for k, f in self.data['beliefs'].items() if f['holder'] == perspective],
                'rule': '仅供该人物视角推演；信念不等于事实，未返回的信息不得推定知情。知情不等于获准对外说出。',
                'source': self.source}

    def render_view(self):
        header = {'kind': 'relationship_queries', 'version': 1, 'source': self.source,
                  'resolver': {'path': RESOLVER, 'sha256': _sha(self._path(RESOLVER).read_bytes())},
                  'occasions': list(OCCASIONS), 'selection': self.data['selection'],
                  'group_rule': '多人自称只取各方向self_candidates的文字交集；不明确对象用该说话者的未明确行；按人物分别读取知情行，不能互借秘密。'}
        rows = [header]
        actors = [p for p, e in self.data['entities'].items() if e['status'] != 'deceased']
        for speaker in actors:
            for listener in [x for x in actors if x != speaker] + [None]:
                rows.append({'key': 'lore.称谓.' + speaker + '.' + (listener or '未明确'),
                             'speaker': speaker, 'listener': listener,
                             'occasions': {o: self.query(speaker, [listener] if listener else [], o) for o in OCCASIONS}})
        for person in actors:
            if self.data['entities'][person]['status'] == 'active':
                rows.append({'key': 'lore.知情.' + person, **self.knowledge(person)})
        return '\n'.join(_dump(row) for row in rows) + '\n'

    def verify_view(self):
        view_path = self._path(VIEW)
        res_path = self._path(RESOLVER)
        sig = None
        try:
            sig = (_stat_sig(view_path), self.source['sha256'], _stat_sig(res_path))
            with _CACHE_LOCK:
                cached = _VIEW_CACHE.get(sig)
            if cached is not None:
                return list(cached)
        except OSError:
            sig = None
        raw = view_path.read_bytes()
        if raw != self.render_view().encode('utf-8'):
            self._fail('关系称谓查询视图未同步，请从唯一原库重新生成')
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
        if sig is not None:
            with _CACHE_LOCK:
                if len(_VIEW_CACHE) >= _MAX_CACHE_ENTRIES:
                    _VIEW_CACHE.pop(next(iter(_VIEW_CACHE)), None)
                _VIEW_CACHE[sig] = rows
        return list(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='只读查询关系称谓；render仅输出可再生成视图到标准输出。')
    parser.add_argument('--root', default=str(Path(__file__).parent))
    commands = parser.add_subparsers(dest='command', required=True)
    query = commands.add_parser('query')
    query.add_argument('--speaker', required=True)
    query.add_argument('--listener', action='append', default=[])
    query.add_argument('--occasion', choices=OCCASIONS, required=True)
    knowledge = commands.add_parser('knowledge')
    knowledge.add_argument('--perspective', required=True)
    commands.add_parser('render')
    commands.add_parser('check')
    args = parser.parse_args(argv)
    try:
        registry = RelationshipRegistry(args.root)
        if args.command == 'render':
            print(registry.render_view(), end='')
            return 0
        if args.command == 'query':
            result = registry.query(args.speaker, args.listener, args.occasion)
        elif args.command == 'knowledge':
            result = registry.knowledge(args.perspective)
        else:
            rows = registry.verify_view()
            result = {'source': registry.source, 'rows': len(rows) - 1, 'view_matches': True}
        print(_dump({'ok': True, 'result': result}))
        return 0
    except (ValueError, OSError) as exc:
        print(_dump({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

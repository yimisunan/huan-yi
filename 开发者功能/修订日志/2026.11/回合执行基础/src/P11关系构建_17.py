"""Build P11 candidates; runtime source lives outside developer records."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import types

BASE = Path('开发者功能/修订日志/2026.11/回合执行基础')
RESOLVER_TEXT = '"""Read-only, directional relationship queries; no round or dialogue writes."""\nimport argparse\nimport hashlib\nimport json\nfrom pathlib import Path\n\nSOURCE = \'txt文件/关系称谓库.json\'\nVIEW = \'txt文件/关系称谓查询.jsonl\'\nRESOLVER = \'relationship_query.py\'\nOCCASIONS = (\'formal\', \'relaxed\', \'business\')\n\n\nclass RelationshipError(ValueError):\n    pass\n\n\ndef _pairs(items):\n    result = {}\n    for key, value in items:\n        if key in result:\n            raise RelationshipError(\'关系资料有重复键: \' + key)\n        result[key] = value\n    return result\n\n\ndef _dump(value):\n    return json.dumps(value, ensure_ascii=False, separators=(\',\', \':\'), allow_nan=False)\n\n\ndef _sha(raw):\n    return hashlib.sha256(raw).hexdigest()\n\n\nclass RelationshipRegistry:\n    def __init__(self, root):\n        self.root = Path(root).resolve()\n        self.raw = self._path(SOURCE).read_bytes()\n        if len(self.raw) > 1024 * 1024:\n            raise RelationshipError(\'关系资料超过1MiB\')\n        try:\n            self.data = json.loads(self.raw, object_pairs_hook=_pairs,\n                                   parse_constant=lambda value: self._fail(\'关系资料含非有限数字\'))\n        except (UnicodeError, json.JSONDecodeError) as exc:\n            raise RelationshipError(\'关系资料不是有效UTF-8 JSON\') from exc\n        try:\n            self._validate()\n        except (KeyError, TypeError) as exc:\n            raise RelationshipError("关系资料字段类型无效") from exc\n        self.source = {\'path\': SOURCE, \'version\': 1, \'sha256\': _sha(self.raw)}\n\n    @staticmethod\n    def _fail(message):\n        raise RelationshipError(message)\n\n    def _path(self, name):\n        path = (self.root / name).resolve()\n        if not path.is_relative_to(self.root):\n            self._fail(\'关系资料越出工作区\')\n        return path\n\n    def _validate(self):\n        d = self.data\n        expected = {\'version\', \'entities\', \'types\', \'facts\', \'roles\', \'title_rules\', \'beliefs\', \'selection\'}\n        if not isinstance(d, dict) or set(d) != expected or type(d[\'version\']) is not int or d[\'version\'] != 1:\n            self._fail(\'关系资料结构或版本无效\')\n        for key in (\'entities\', \'types\', \'facts\', \'roles\', \'beliefs\'):\n            if not isinstance(d[key], dict) or not d[key]:\n                self._fail(\'关系资料缺少对象: \' + key)\n        entities, roles = d[\'entities\'], d[\'roles\']\n        for name, item in entities.items():\n            if (not isinstance(item, dict) or set(item) != {\'short\', \'status\'}\n                    or not name or not isinstance(item[\'short\'], str) or not item[\'short\']\n                    or item[\'status\'] not in {\'active\', \'deceased\', \'category\'}):\n                self._fail(\'关系人物结构无效\')\n        for item in roles.values():\n            if not isinstance(item, dict) or set(item) != {\'label\', \'self\', \'address\'} or not isinstance(item[\'label\'], str):\n                self._fail(\'关系角色词表无效\')\n            for mode in (\'self\', \'address\'):\n                forms = item[mode]\n                if not isinstance(forms, dict) or set(forms) != set(OCCASIONS):\n                    self._fail(\'称谓场合必须完整枚举\')\n                for terms in forms.values():\n                    if (not isinstance(terms, list) or any(not isinstance(x, str) or not x for x in terms)\n                            or len(set(terms)) != len(terms)):\n                        self._fail(\'称谓候选须为不重复的非空字符串\')\n        for item in d[\'types\'].values():\n            if (not isinstance(item, dict) or set(item) != {\'layer\', \'roles\'}\n                    or item[\'layer\'] not in {\'blood\', \'social\', \'legal\'}\n                    or not isinstance(item[\'roles\'], list) or len(item[\'roles\']) not in {0, 2}\n                    or any(r not in roles for r in item[\'roles\'])):\n                self._fail(\'关系类型无效\')\n        seen = set()\n        for item in d[\'facts\'].values():\n            if not isinstance(item, dict) or set(item) != {\'type\', \'subject\', \'object\', \'known_by\', \'text\'}:\n                self._fail(\'关系事实结构无效\')\n            if (item[\'type\'] not in d[\'types\'] or item[\'subject\'] not in entities or item[\'object\'] not in entities\n                    or item[\'subject\'] == item[\'object\'] or not isinstance(item[\'text\'], str) or not item[\'text\']):\n                self._fail(\'关系事实引用无效\')\n            known = item[\'known_by\']\n            if known != \'*\':\n                if (not isinstance(known, list) or not known or len(set(known)) != len(known)\n                        or any(x not in entities or entities[x][\'status\'] != \'active\' for x in known)):\n                    self._fail(\'知情资格须为明确人物名单\')\n            relation = d[\'types\'][item[\'type\']]\n            signature = (relation[\'layer\'], frozenset((item[\'subject\'], item[\'object\'])))\n            if signature in seen:\n                self._fail(\'同层关系事实重复或反向双写\')\n            seen.add(signature)\n            if relation[\'roles\'] and known == \'*\' and any(entities[x][\'status\'] == \'category\' for x in (item[\'subject\'], item[\'object\'])):\n                self._fail(\'人物类别不能充当亲属事实\')\n        if not isinstance(d[\'title_rules\'], list):\n            self._fail(\'身份称谓规则无效\')\n        for item in d[\'title_rules\']:\n            if (not isinstance(item, dict) or set(item) != {\'speaker\', \'listener\', \'fact\', \'forms\'}\n                    or item[\'speaker\'] not in entities or item[\'listener\'] not in entities or item[\'fact\'] not in d[\'facts\']\n                    or not isinstance(item[\'forms\'], dict) or set(item[\'forms\']) != set(OCCASIONS)\n                    or any(not isinstance(v, list) or any(not isinstance(s, str) or not s for s in v) for v in item[\'forms\'].values())):\n                self._fail(\'身份称谓引用无效\')\n        for item in d[\'beliefs\'].values():\n            if (not isinstance(item, dict) or set(item) != {\'holder\', \'text\'} or item[\'holder\'] not in entities\n                    or not isinstance(item[\'text\'], str) or not item[\'text\']):\n                self._fail(\'人物信念结构无效\')\n        if (not isinstance(d[\'selection\'], dict) or set(d[\'selection\']) != {\'optional\', \'rule\'}\n                or d[\'selection\'][\'optional\'] is not True or not isinstance(d[\'selection\'][\'rule\'], str)):\n            self._fail(\'称谓必须保留选择及省略自由\')\n\n    def _entity(self, name, *, speaking=False):\n        if not isinstance(name, str) or name not in self.data[\'entities\']:\n            self._fail(\'未知关系人物\')\n        item = self.data[\'entities\'][name]\n        if speaking and item[\'status\'] == \'deceased\':\n            self._fail(\'已故人物不能作为当前说话者\')\n        return item\n\n    @staticmethod\n    def _visible(fact, people):\n        return fact[\'known_by\'] == \'*\' or set(people) <= set(fact[\'known_by\'])\n\n    def _fact(self, key, item):\n        return {\'id\': key, \'type\': item[\'type\'], \'layer\': self.data[\'types\'][item[\'type\']][\'layer\'],\n                \'subject\': item[\'subject\'], \'object\': item[\'object\'], \'text\': item[\'text\'],\n                \'source\': \'#/facts/\' + key}\n\n    @staticmethod\n    def _form(text, kind, *sources):\n        return {\'text\': text, \'kind\': kind, \'sources\': list(sources)}\n\n    @staticmethod\n    def _merge(forms):\n        result = {}\n        for form in forms:\n            key = form[\'text\']\n            if key not in result:\n                result[key] = dict(form, sources=list(form[\'sources\']))\n            else:\n                result[key][\'sources\'] = sorted(set(result[key][\'sources\'] + form[\'sources\']))\n        return list(result.values())\n\n    def _neutral(self, person, mode):\n        ref = \'#/entities/\' + person + \'/short\'\n        if mode == \'self\':\n            return [self._form(\'我\', \'pronoun\', \'#/selection\'),\n                    self._form(self.data[\'entities\'][person][\'short\'], \'name\', ref),\n                    self._form(\'\', \'omit\', \'#/selection\')]\n        return [self._form(self.data[\'entities\'][person][\'short\'], \'name\', ref),\n                self._form(\'你\', \'pronoun\', \'#/selection\'), self._form(\'\', \'omit\', \'#/selection\')]\n\n    def query(self, speaker, listeners, occasion):\n        self._entity(speaker, speaking=True)\n        if not isinstance(occasion, str) or occasion not in OCCASIONS:\n            self._fail(\'场合须为formal/relaxed/business\')\n        if listeners is None:\n            listeners = []\n        if (not isinstance(listeners, list) or len(listeners) > len(self.data[\'entities\'])\n                or any(not isinstance(x, str) for x in listeners) or len(set(listeners)) != len(listeners)):\n            self._fail(\'听话者须为不重复的明确人物数组\')\n        for listener in listeners:\n            self._entity(listener, speaking=True)\n            if listener == speaker:\n                self._fail(\'说话者与听话者不能相同\')\n        people = [speaker, *listeners]\n        groups, targets, facts = [], [], {}\n        for listener in listeners:\n            own, address, relations = self._neutral(speaker, \'self\'), self._neutral(listener, \'address\'), []\n            for key, item in self.data[\'facts\'].items():\n                if set((speaker, listener)) != {item[\'subject\'], item[\'object\']} or not self._visible(item, people):\n                    continue\n                roles = self.data[\'types\'][item[\'type\']][\'roles\']\n                if not roles:\n                    continue\n                sr, lr = roles if speaker == item[\'subject\'] else list(reversed(roles))\n                facts[key] = self._fact(key, item)\n                relations.append({\'speaker_role\': self.data[\'roles\'][sr][\'label\'],\n                                  \'listener_role\': self.data[\'roles\'][lr][\'label\'], \'fact\': \'#/facts/\' + key})\n                for mode, role, forms in ((\'self\', sr, own), (\'address\', lr, address)):\n                    for term in self.data[\'roles\'][role][mode][occasion]:\n                        forms.append(self._form(term, \'kinship\', \'#/facts/\' + key, \'#/roles/\' + role + \'/\' + mode + \'/\' + occasion))\n            for i, rule in enumerate(self.data[\'title_rules\']):\n                if (rule[\'speaker\'], rule[\'listener\']) == (speaker, listener):\n                    item = self.data[\'facts\'][rule[\'fact\']]\n                    if self._visible(item, people):\n                        facts[rule[\'fact\']] = self._fact(rule[\'fact\'], item)\n                        own.extend(self._form(term, \'title\', \'#/facts/\' + rule[\'fact\'], \'#/title_rules/\' + str(i))\n                                   for term in rule[\'forms\'][occasion])\n            groups.append(self._merge(own))\n            targets.append({\'listener\': listener, \'relations\': relations, \'address_candidates\': self._merge(address)})\n        if groups:\n            common = set.intersection(*({x[\'text\'] for x in group} for group in groups))\n            candidates = self._merge(x for group in groups for x in group if x[\'text\'] in common)\n        else:\n            candidates = self._neutral(speaker, \'self\')\n            # Unknown audience permits public identity facts only, including deceased relatives.\n            for key, item in self.data[\'facts\'].items():\n                if item[\'known_by\'] == \'*\' and speaker in {item[\'subject\'], item[\'object\']}:\n                    facts[key] = self._fact(key, item)\n        return {\'speaker\': speaker, \'listeners\': listeners, \'occasion\': occasion,\n                \'self_candidates\': candidates, \'targets\': targets, \'facts\': list(facts.values()),\n                \'source\': self.source, \'selection\': self.data[\'selection\']}\n\n    def knowledge(self, perspective):\n        self._entity(perspective, speaking=True)\n        return {\'perspective\': perspective,\n                \'facts\': [self._fact(k, f) for k, f in self.data[\'facts\'].items()\n                          if f[\'known_by\'] != \'*\' and self._visible(f, [perspective])],\n                \'beliefs\': [{\'text\': f[\'text\'], \'status\': \'belief_not_fact\', \'source\': \'#/beliefs/\' + k}\n                            for k, f in self.data[\'beliefs\'].items() if f[\'holder\'] == perspective],\n                \'rule\': \'仅供该人物视角推演；信念不等于事实，未返回的信息不得推定知情。知情不等于获准对外说出。\',\n                \'source\': self.source}\n\n    def render_view(self):\n        header = {\'kind\': \'relationship_queries\', \'version\': 1, \'source\': self.source,\n                  \'resolver\': {\'path\': RESOLVER, \'sha256\': _sha(self._path(RESOLVER).read_bytes())},\n                  \'occasions\': list(OCCASIONS), \'selection\': self.data[\'selection\'],\n                  \'group_rule\': \'多人自称只取各方向self_candidates的文字交集；不明确对象用该说话者的未明确行；按人物分别读取知情行，不能互借秘密。\'}\n        rows = [header]\n        actors = [p for p, e in self.data[\'entities\'].items() if e[\'status\'] != \'deceased\']\n        for speaker in actors:\n            for listener in [x for x in actors if x != speaker] + [None]:\n                rows.append({\'key\': \'lore.称谓.\' + speaker + \'.\' + (listener or \'未明确\'),\n                             \'speaker\': speaker, \'listener\': listener,\n                             \'occasions\': {o: self.query(speaker, [listener] if listener else [], o) for o in OCCASIONS}})\n        for person in actors:\n            if self.data[\'entities\'][person][\'status\'] == \'active\':\n                rows.append({\'key\': \'lore.知情.\' + person, **self.knowledge(person)})\n        return \'\\n\'.join(_dump(row) for row in rows) + \'\\n\'\n\n    def verify_view(self):\n        raw = self._path(VIEW).read_bytes()\n        if raw != self.render_view().encode(\'utf-8\'):\n            self._fail(\'关系称谓查询视图未同步，请从唯一原库重新生成\')\n        return [json.loads(line) for line in raw.decode(\'utf-8\').splitlines()]\n\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser(description=\'只读查询关系称谓；render仅输出可再生成视图到标准输出。\')\n    parser.add_argument(\'--root\', default=str(Path(__file__).parent))\n    commands = parser.add_subparsers(dest=\'command\', required=True)\n    query = commands.add_parser(\'query\')\n    query.add_argument(\'--speaker\', required=True)\n    query.add_argument(\'--listener\', action=\'append\', default=[])\n    query.add_argument(\'--occasion\', choices=OCCASIONS, required=True)\n    knowledge = commands.add_parser(\'knowledge\')\n    knowledge.add_argument(\'--perspective\', required=True)\n    commands.add_parser(\'render\')\n    commands.add_parser(\'check\')\n    args = parser.parse_args(argv)\n    try:\n        registry = RelationshipRegistry(args.root)\n        if args.command == \'render\':\n            print(registry.render_view(), end=\'\')\n            return 0\n        if args.command == \'query\':\n            result = registry.query(args.speaker, args.listener, args.occasion)\n        elif args.command == \'knowledge\':\n            result = registry.knowledge(args.perspective)\n        else:\n            rows = registry.verify_view()\n            result = {\'source\': registry.source, \'rows\': len(rows) - 1, \'view_matches\': True}\n        print(_dump({\'ok\': True, \'result\': result}))\n        return 0\n    except (ValueError, OSError) as exc:\n        print(_dump({\'ok\': False, \'error\': str(exc)}))\n        return 1\n\n\nif __name__ == \'__main__\':\n    raise SystemExit(main())\n'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
pack = lambda obj: (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
manifest_path = BASE/'src/安装清单_17.json'
manifest = json.loads(manifest_path.read_bytes())
changes = {c['path']:c for c in manifest['changes']}

def swap(text, old, new, count=1):
    assert text.count(old) == count, (old[:70], text.count(old), count)
    return text.replace(old, new)


def stage(name, raw):
    if isinstance(raw, str): raw=raw.encode('utf-8')
    Path(changes[name]['staged']).write_bytes(raw)
    changes[name]['after']={'sha256':sha(raw),'bytes':len(raw)}
    before=Path(name).read_bytes() if Path(name).exists() else b''
    changes[name]['character_delta']=len(raw.decode())-len(before.decode())


def forms(formal=(), relaxed=None, business=()):
    return {'formal':list(formal),'relaxed':list(formal if relaxed is None else relaxed),'business':list(business)}


def role(label, self_form=(), self_relaxed=None, addr=(), addr_relaxed=None):
    return {'label':label,'self':forms(self_form,self_relaxed),'address':forms(addr,addr_relaxed)}

roles={
 'mother':role('生母',(),('妈妈',),('母亲',),('妈','妈妈')),
 'son':role('亲生子',('儿子',),('儿子',),('儿子',)),
 'adoptive_mother':role('养母',(),('妈妈',),('母亲',),('妈','妈妈')),
 'adopted_son':role('养子',('儿子',),('儿子',),('儿子',)),
 'adopted_daughter':role('养女',('女儿',),('女儿',),('女儿',)),
 'father':role('生父',('父亲',),('爸爸',),('父亲',),('爸','爸爸')),
 'husband':role('丈夫',(),(),('丈夫',),('老公',)),
 'wife':role('妻子',(),(),('妻子',),('老婆',)),
 'mother_in_law':role('婆婆',(),(),('母亲',),('妈','妈妈')),
 'daughter_in_law':role('儿媳',('儿媳',),(),('儿媳',)),
 'elder_brother':role('养兄',('哥哥',),('哥','哥哥'),('大哥',),('哥','哥哥')),
 'younger_brother':role('养弟',('弟弟',),('弟弟',),('弟弟',)),
 'elder_sister':role('养姐',('姐姐',),('姐','姐姐'),('二姐',),('姐','姐姐')),
 'younger_sister':role('养妹',('妹妹',),('妹妹',),('妹妹',)),
 'sister_in_law':role('嫂子',('嫂子',),('嫂子',),('嫂子',),('嫂子','嫂嫂')),
 'husbands_younger_brother':role('小叔',(),(),('小叔',)),
 'husbands_younger_sister':role('小姑',(),(),('小姑',)),
}
# Names and kinship candidates are presentation; facts are stored once, oriented by endpoints.
types_map={
 'mother_son':{'layer':'blood','roles':['mother','son']},
 'father_son':{'layer':'blood','roles':['father','son']},
 'adoptive_mother_son':{'layer':'social','roles':['adoptive_mother','adopted_son']},
 'adoptive_mother_daughter':{'layer':'social','roles':['adoptive_mother','adopted_daughter']},
 'marriage':{'layer':'social','roles':['husband','wife']},
 'in_law_mother':{'layer':'social','roles':['mother_in_law','daughter_in_law']},
 'brothers':{'layer':'social','roles':['elder_brother','younger_brother']},
 'brother_sister':{'layer':'social','roles':['elder_brother','younger_sister']},
 'sister_brother':{'layer':'social','roles':['elder_sister','younger_brother']},
 'in_law_brother':{'layer':'social','roles':['sister_in_law','husbands_younger_brother']},
 'in_law_sister':{'layer':'social','roles':['sister_in_law','husbands_younger_sister']},
 'heir':{'layer':'legal','roles':[]},
}
facts={}
def fact(key,typ,subject,obj,text,known='*'):
    facts[key]={'type':typ,'subject':subject,'object':obj,'known_by':known,'text':text}
fact('R01','mother_son','沈知韫','徐志北','沈知韫为徐志北生母；徐志北是亲生子，不能写成养子。')
fact('R02','father_son','徐家亡父','徐志北','徐家亡父是徐志北生父，已故，为徐家创始人与遗嘱立者。')
fact('R03','marriage','徐家亡父','沈知韫','沈知韫为徐家亡父之妻；亡夫已故。')
fact('R04','adoptive_mother_son','沈知韫','徐承邺','沈知韫为徐承邺养母，徐承邺为徐家养子。')
fact('R05','adoptive_mother_daughter','沈知韫','徐念薇','沈知韫为徐念薇养母，徐念薇为徐家养女。')
fact('R06','marriage','徐承邺','苏婉青','徐承邺与苏婉青是夫妻；苏婉青在徐家为少奶奶。')
fact('R07','in_law_mother','沈知韫','苏婉青','沈知韫是苏婉青的婆婆，苏婉青为其儿媳。')
fact('R08','brothers','徐承邺','徐志北','徐承邺是徐志北的养兄、长兄；徐志北为其养弟。')
fact('R09','brother_sister','徐承邺','徐念薇','徐承邺是徐念薇的养兄；徐念薇为其养妹、家中二姐。')
fact('R10','sister_brother','徐念薇','徐志北','徐念薇是徐志北的养姐、二姐；徐志北为其养弟。')
fact('R11','in_law_brother','苏婉青','徐志北','苏婉青是徐志北的嫂子；徐志北为其小叔。')
fact('R12','in_law_sister','苏婉青','徐念薇','苏婉青是徐念薇的嫂子；徐念薇为其小姑。')
fact('K01','heir','徐家亡父','徐志北','亡夫遗嘱指定徐志北为千亿家产唯一合法继承人，而非徐承邺。',['沈知韫'])
entities={n:{'short':s,'status':'active'} for n,s in [('沈知韫','知韫'),('苏婉青','婉青'),('徐念薇','念薇'),('徐承邺','承邺'),('徐志北','志北')]}
entities['徐家亡父']={'short':'徐家亡父','status':'deceased'}
entities['次要NPC']={'short':'对方','status':'category'}
data={'version':1,'entities':entities,'types':types_map,'facts':facts,'roles':roles,
      'title_rules':[{'speaker':'苏婉青','listener':'次要NPC','fact':'R06','forms':forms(('少奶奶',),('少奶奶',))}],
      'beliefs':{'B01':{'holder':'徐承邺','text':'坚信自己能继承家业，试图获得母亲对继承权的认可。'},
                 'B02':{'holder':'徐念薇','text':'仅知自己是家族利益中的局外人。'},
                 'B03':{'holder':'沈知韫','text':'自认家业给亲生子、偏爱给养子是两全；为庇护养子自尊而死守遗嘱秘密至今，独自承受守密与偏爱不公的内疚。'}},
      'selection':{'optional':True,'rule':'称谓均为合法候选，不是必用台词。正式/放松/商务按实际话轮选择，可用我、姓名或省略；亲属自称只对明确听话者成立，不把叙述称呼复制为自称。'}}
stage('relationship_query.py',RESOLVER_TEXT)
stage('txt文件/关系称谓库.json',pack(data))
work=BASE/'tmp/tmp_relation17_project';work.mkdir(exist_ok=True)
for rel in ['relationship_query.py','txt文件/关系称谓库.json']:
    p=work/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(Path(changes[rel]['staged']).read_bytes())
module=types.ModuleType('relationship_query');module.__file__=str(work/'relationship_query.py')
exec(compile(RESOLVER_TEXT,module.__file__,'exec'),module.__dict__)
stage('txt文件/关系称谓查询.jsonl',module.RelationshipRegistry(work).render_view())

# Only content changes in knowledge libraries; all routing and activation metadata survive.
for file in ['角色类','世界观类','叙事判断']:
    rel='txt文件/知识库/'+file+'.json';obj=json.loads(Path(rel).read_bytes())
    for e in obj['data']['entries']:
        t=e['content']
        if file=='角色类':
            name=re.search(r'※索引key※\s*char\.(\S+)',t).group(1)
            t,n=re.subn(r'【亲属关系·身份死线】[^\n]+',f'【亲属关系·身份死线】见 lore.称谓（说话者={name}，听话者=当前实际对象）；关系事实以 txt文件/关系称谓库.json 为唯一维护源，按需读取生成查询行，不在本条复列。',t);assert n==1
            if name=='沈知韫':
                t=swap(t,'。遗嘱真相唯一知情人。','。知情资格见 lore.知情.沈知韫。')
                t=swap(t,'自认把家业给亲生子、把偏爱给养子是两全。','守密与偏爱相关的自身认知见 lore.知情.沈知韫。')
                t=swap(t,'对子女表达关怀时可自然用「妈妈」自称，承接上下文可省略主语，不必每句重复；对商务对象或其他听话者按关系用「我」或姓名。','自称与称呼按 lore.称谓 的实际听话者及场合候选选择，承接上下文可省略，不必每句重复。')
            elif name=='苏婉青':
                start=t.index('【语言指纹·亲属自称】');end=t.index('\n\n【Fish声学覆盖】',start)
                t=t[:start]+'【语言指纹·亲属自称】礼仪与紧张场合优先弱化或省略主语；称谓只在需要时出现，不每句重复。具体候选按 lore.称谓 的说话者→听话者→场合查询；不得把对某人的亲属自称套给其他对象。'+t[end:]
                t=swap(t,'【三重崩溃】1.退缩死守「我是嫂子」外壳','【三重崩溃】1.退缩死守亲属身份外壳（具体自称须匹配实际听话者，见lore.称谓）')
            elif name=='徐承邺':
                t=swap(t,'【信息差位置】不知情：不知遗嘱指定宿主为唯一合法继承人；坚信自己能继承家业。','【信息差位置】知情资格及自身信念见 lore.知情.徐承邺；信念不当作继承事实。')
            elif name=='徐志北':
                t=swap(t,'【信息差位置】本人完全不知情遗嘱指定其为唯一合法继承人（总表见 lore.信息差）。','【信息差位置】按 lore.知情.徐志北 读取自身已知信息；揭秘纪律见 lore.信息差。')
            elif name=='徐念薇':
                t=swap(t,'信息差中的她(仅知局外人，不知继承归属)见lore.信息差','自身知情与信念见lore.知情.徐念薇；揭秘纪律见lore.信息差')
        elif file=='世界观类' and '※索引key※ lore.信息差' in t:
            t,n=re.subn(r'【家族谱系[^\n]+', '【关系与知情查询】血缘/社会关系、继承事实与知情资格唯一维护源为 txt文件/关系称谓库.json；按索引 lore.称谓 / lore.知情 查询生成行。不要把全部关系表自动塞入每轮输入。',t);assert n==1
            t,n=re.subn(r'【继承权真相】[^\n]+','【继承权事实】按 lore.知情.<当前人物> 返回的事实与信念推演；未返回的信息不推定知情。剧情合法解锁须有玩家指令及已发生依据，并显式维护唯一源资格，查询不接受临时自报解锁。',t);assert n==1
            t,n=re.subn(r'\n\n【认知锁死[^\n]+','',t);assert n==1
        elif file=='叙事判断' and '亲属自称视角验证锁' in t:
            t=swap(t,'具体称谓和场合只见对应char语言指纹','具体候选按lore.称谓的说话者→听话者→场合查询；语气风格见对应char语言指纹')
        e['content']=t
    stage(rel,pack(obj))

rel='txt文件/故事检索索引.md';text=Path(rel).read_text()
text=swap(text,'- **禁止**：在本文件写长设定正文。','''- 关系/称谓：先grep_code定位 `txt文件/关系称谓查询.jsonl` 中的 `lore.称谓.<说话者>.<听话者>`（不明确用“未明确”）或 `lore.知情.<人物>`，再用read_file_part读取第1行元数据及所需行；grep只用于定位。正式formal、放松relaxed、商务business。多人自称取各明确方向的候选交集；知情行按人物隔离，不把别人秘密移入当前人物。无需每句重复称谓，也不自动通读完整查询表。原库仅维护/核对时读取，生成视图不能手改。
- **禁止**：在本文件写长设定正文。''')
text=swap(text,'| lore.信息差 | 世界书 | 涉家产/继承/遗嘱语气 | 世界书注入 |','''| lore.称谓 | workspace → txt文件/关系称谓查询.jsonl；原件→txt文件/关系称谓库.json | 需要核实亲属事实、自称或听话者方向 | 按需读取第1行及所需方向行；非每回合全表 |
| lore.知情 | workspace → txt文件/关系称谓查询.jsonl | 家产/继承/遗嘱及角色已知信息 | 只读当前人物知情行；信念不是事实 |
| lore.信息差 | 世界书 | 涉家产/继承/遗嘱语气；揭秘纪律 | 世界书注入 |''')
stage(rel,text)

rel='story_service.py';text=Path(rel).read_text()
text=swap(text,'import round_runtime as rr\n','import round_runtime as rr\nimport relationship_query as rq\n')
text=swap(text,"'txt文件/知识库/叙事判断.json', 'txt文件/知识库/系统标签类.json', 'txt文件/事件注册表.json')", "'txt文件/知识库/叙事判断.json', 'txt文件/知识库/系统标签类.json', 'txt文件/事件注册表.json',\n         rq.SOURCE, rq.VIEW, rq.RESOLVER)")
text=swap(text,'        required = []\n', '''        try:
            rq.RelationshipRegistry(self.root).verify_view()
        except (ValueError, OSError) as exc:
            raise rr.RoundError('关系查询资料不可用: ' + str(exc)) from exc
        required = []
''')
text=swap(text,"            'node_examples':",'''            'relationship_registry': {'path': rq.SOURCE, 'sha256': audit[rq.SOURCE],
                'view': {'path': rq.VIEW, 'sha256': audit[rq.VIEW]},
                'resolver': {'path': rq.RESOLVER, 'sha256': audit[rq.RESOLVER]},
                'occasions': list(rq.OCCASIONS), 'header_line': 1,
                'rule': '按索引grep定位，再read_file_part读取第1行及所需方向/知情行；不自动读取全表。称谓可省略，知情按人物隔离；来源或视图失配须重试。'},
            'node_examples':''')
text=swap(text,"'Operit世界书导出', '日志', '__pycache__', 'vosi', '语音仓库']}","'Operit世界书导出', '日志', '__pycache__', 'vosi', '语音仓库'],\n                  'relationship_queries': {'path': rq.VIEW, 'header_line': 1, 'coverage': '读取元数据及所需方向行，非全表'}}")
text=swap(text,"'允许文件工具调用，禁止写文件、命令执行、外部服务或自行注入。'", "                   '称谓及知情资料按索引读取生成查询行；不得把某人物的知情行当作他人已知，也不强制台词使用称谓。'\n                   '允许文件工具调用，禁止写文件、命令执行、外部服务或自行注入。'")
text=swap(text,'    def _bridge_facts(self, context, audit):', '''    def _relationship_facts(self, records):
        spans = []
        for record in records:
            if record['path'] != rq.VIEW or record['status'] != 'success' or record['name'] not in READ_TOOLS:
                continue
            spans.append((1, 10 ** 9) if record.get('complete_read') else
                         (record.get('start_line', 0), record.get('end_line', -1)))
        if not spans:
            return {}
        if not any(begin <= 1 <= end for begin, end in spans):
            raise rr.RoundError('关系查询缺少第1行元数据读取')
        try:
            registry = rq.RelationshipRegistry(self.root)
            rows = registry.verify_view()
        except (ValueError, OSError) as exc:
            raise rr.RoundError('关系查询来源或视图无效: ' + str(exc)) from exc
        digest = hashlib.sha256(self.store._path(rq.VIEW).read_bytes()).hexdigest()
        result = {}
        for line, row in enumerate(rows[1:], 2):
            if any(begin <= line <= end for begin, end in spans):
                result[row['key']] = {'path': rq.VIEW, 'sha256': digest, 'covered_lines': [1, line],
                                      'source': registry.source, 'scope': 'query_row'}
        for prefix in ('lore.称谓', 'lore.知情'):
            keys = [key for key in result if key.startswith(prefix + '.')]
            if keys:
                result[prefix] = {'path': rq.VIEW, 'sha256': digest, 'scope': 'query_rows',
                                  'keys': keys, 'covered_lines': sorted({1} | {result[k]['covered_lines'][1] for k in keys}),
                                  'source': registry.source}
        return result

    def _bridge_facts(self, context, audit):''')
text=swap(text,'        return {\'required_reads_verified\': True, \'available_keys\': available,', '''        relationship_facts = self._relationship_facts(records)
        available.update(relationship_facts)
        if relationship_facts:
            fingerprints[rq.VIEW] = hashlib.sha256(self.store._path(rq.VIEW).read_bytes()).hexdigest()
            fingerprints[rq.SOURCE] = hashlib.sha256(self.store._path(rq.SOURCE).read_bytes()).hexdigest()
        return {'required_reads_verified': True, 'available_keys': available,''')
text=swap(text,"            if successful and name in READ_TOOLS:\n", '''            if successful and name in READ_TOOLS:
                if relative == rq.VIEW and re.search(r'truncated|内容截断|内容已截断|file content truncated', text, re.I):
                    raise rr.RoundError('关系查询行读取被截断，请定向补读')
''')
text=text.replace("                                     '称谓及知情资料", "                  '称谓及知情资料").replace("                   '允许文件工具调用", "                  '允许文件工具调用")
stage(rel,text)

rel='开发者功能/开发者说明书/开发者说明书.md';text=Path(rel).read_text()
text=swap(text,'| `txt文件/知识库/世界观类.json` | 当前有效世界观、信息差、家谱唯一事实源、驻地作息、命名锁 |','| `txt文件/关系称谓库.json` | 血缘/社会关系、继承事实、知情资格和称谓候选的唯一维护源；relationship_query.py只读派生查询视图 | 台词替换、动态解锁自报、存档事实 |\n| `txt文件/知识库/世界观类.json` | 当前有效世界观、信息差叙事纪律、关系查询指针、驻地作息、命名锁 |')
text=swap(text,'| 2026-11-17 | P10 事件注册表与编号复用 |','| 2026-11-17 | P11 关系事实与称谓查询 | 关系/知情资格集中维护，称谓按方向与场合返回候选，桥接沿原文件只读权限按行读取并核验生成视图；不强制台词、不自动注入全表。见回合执行基础/logs/step_17.md。 |\n| 2026-11-17 | P10 事件注册表与编号复用 |')
stage(rel,text)
rel='开发者功能/开发者说明书/世界书关键字配置.txt';text=Path(rel).read_text()
text=swap(text,'关键词路由不变。','关键词路由不变。关系事实/具体自称与知情资格由txt文件/关系称谓库.json唯一维护，源条目按需指向关系称谓查询.jsonl，非世界书常驻表。')
text=swap(text,'    内容：世界观类.json → lore.信息差（常驻：否）','    内容：世界观类.json → lore.信息差（常驻：否；保留揭秘纪律，事实与知情按关系查询）')
stage(rel,text)

spec=importlib.util.spec_from_file_location('p11_converter','Operit世界书导出/convert_to_operit.py')
converter=importlib.util.module_from_spec(spec);spec.loader.exec_module(converter)
entries=[]
for _,file in converter.FILES:
    name=Path(file).resolve().relative_to(Path('.').resolve()).as_posix()
    raw=Path(changes[name]['staged']).read_bytes() if name in changes else Path(name).read_bytes()
    entries.extend(converter.to_operit(e) for e in json.loads(raw)['data']['entries'])
stage('Operit世界书导出/operit_worldbook_深渊天平.json',json.dumps(entries,ensure_ascii=False,indent=2).encode())
manifest['status']='CANDIDATES_READY'
manifest_path.write_bytes(pack(manifest))
print('CANDIDATES_READY',len(changes),'facts',len(facts),'view_rows',len(module.RelationshipRegistry(work).render_view().splitlines())-1)
for c in manifest['changes']:print('DELTA',c['path'],c['character_delta'],c['after']['bytes'])

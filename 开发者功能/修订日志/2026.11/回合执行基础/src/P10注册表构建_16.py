"""Build P10 candidates from the bound project's current sources. Run once before installation."""
from pathlib import Path
import ast
import datetime
import hashlib
import json
import re
import shlex
import types

ROOT = Path.cwd().resolve()
BASE = ROOT / '开发者功能/修订日志/2026.11/回合执行基础'
REGISTRY = 'txt文件/事件注册表.json'
SHA = lambda data: hashlib.sha256(data).hexdigest()

LOADER = r'''
EVENT_REGISTRY_PATH = globals().get('_EVENT_REGISTRY_SOURCE', os.path.join(BASE_DIR, 'txt文件', '事件注册表.json'))
_EVENT_REGISTRY_DATA = None
_EVENT_INDEX = None


def _event_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('事件注册表含重复键: ' + key)
        result[key] = value
    return result


def _load_event_registry():
    """Read one immutable registry snapshot per isolated engine instance."""
    global _EVENT_REGISTRY_DATA, _EVENT_INDEX
    if _EVENT_REGISTRY_DATA is not None:
        return _EVENT_REGISTRY_DATA
    with open(EVENT_REGISTRY_PATH, 'r', encoding='utf-8') as handle:
        raw = handle.read()
    def bad_number(value):
        raise ValueError('事件注册表不接受非有限数字: ' + value)
    data = json.loads(raw, object_pairs_hook=_event_pairs, parse_constant=bad_number)
    groups = ('shame_events', 'depravity_events', 'ds_events', 'affection_events', 'host_events', 'vigilance_events')
    if (not isinstance(data, dict) or set(data) != {'version', 'groups'}
            or type(data['version']) is not int or data['version'] != 1
            or not isinstance(data['groups'], dict) or set(data['groups']) != set(groups)):
        raise ValueError('事件注册表结构或版本非法')
    index = {}
    for group in groups:
        entries = data['groups'][group]
        if not isinstance(entries, list) or not entries:
            raise ValueError('事件组须为非空数组: ' + group)
        tags = set()
        for entry in entries:
            fields = {'id', 'tag', 'parameters', 'parameter_usage', 'description', 'pattern'}
            if not isinstance(entry, dict) or set(entry) != fields:
                raise ValueError('事件定义字段非法: ' + group)
            ident, tag = entry['id'], entry['tag']
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Z]+_[0-9]{2}', ident) or ident in index:
                raise ValueError('事件内部ID重复或非法')
            if not isinstance(tag, str) or not tag.strip() or any(c in tag for c in '\r\n') or tag in tags:
                raise ValueError('事件标签重复或非法: ' + group)
            params, usage = entry['parameters'], entry['parameter_usage']
            if not isinstance(params, dict) or not isinstance(usage, dict) or set(params) != set(usage):
                raise ValueError('事件参数与用途不对应: ' + ident)
            for key, value in params.items():
                if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or type(value) not in (int, float):
                    raise ValueError('事件参数须为具名数值: ' + ident)
                if isinstance(value, float) and (value != value or abs(value) == float('inf')):
                    raise ValueError('事件参数不可为非有限数字')
                if not isinstance(usage[key], str) or not usage[key].strip():
                    raise ValueError('事件参数缺少用途')
            if not isinstance(entry['description'], str) or not entry['description'].strip():
                raise ValueError('事件缺少说明: ' + ident)
            pattern = entry['pattern']
            if pattern is not None:
                if (group != 'host_events' or not tag.endswith('_X')
                        or pattern != re.escape(tag[:-1]) + r'[1-9]\d{0,8}'):
                    raise ValueError('事件模板模式非法: ' + ident)
                re.compile(pattern)
            tags.add(tag)
            index[ident] = entry
    _EVENT_REGISTRY_DATA, _EVENT_INDEX = data, index
    return data


def _event_tag(ident):
    _load_event_registry()
    return _EVENT_INDEX[ident]['tag']


def _event_param(ident, key):
    _load_event_registry()
    return _EVENT_INDEX[ident]['parameters'][key]


def _event_accepts(group, tag):
    for entry in _load_event_registry()['groups'][group]:
        if entry['pattern'] is not None:
            if re.fullmatch(entry['pattern'], tag):
                return True
        elif tag == entry['tag']:
            return True
    return False


def _event_is_template(group, tag):
    return any(e['pattern'] is not None and tag == e['tag'] for e in _load_event_registry()['groups'][group])


def _render_event_table(group, include_parameters=True):
    """Generate model-visible spelling and numeric display from the loaded registry."""
    entries = _load_event_registry()['groups'][group]
    lines = ['【' + group.upper() + '】' + ' / '.join(e['tag'] for e in entries)]
    if include_parameters:
        for entry in entries:
            items = [key + '=' + str(value) + '（' + entry['parameter_usage'][key] + '）'
                     for key, value in entry['parameters'].items()]
            details = '；'.join(items) if items else '条件/修饰标签；按既有通用规则处理'
            if entry['pattern']:
                details += '；实际提交模式=' + entry['pattern']
            lines.append('- ' + entry['tag'] + '：' + details)
    return '\n'.join(lines)
'''


def main():
    manifest_path = BASE / 'src/安装清单_16.json'
    assert not manifest_path.exists() and not (ROOT/REGISTRY).exists()
    parent = json.loads((BASE/'src/安装清单_15.json').read_bytes())
    baseline = dict(parent['protected']); baseline.update({c['path']:c['after'] for c in parent['changes']})
    for rel, info in baseline.items(): assert SHA((ROOT/rel).read_bytes()) == info['sha256'], rel
    engine_text = (ROOT/'injection_core.py').read_text()
    guide_text = (ROOT/'txt文件/一键注入指南.txt').read_text()
    groups = {}
    prefixes = ['SHAME','DEPRAVITY','DS','AFFECTION','HOST','VIGILANCE']
    fields = ['shame_events','depravity_events','ds_events','affection_events','host_events','vigilance_events']
    for field,prefix in zip(fields,prefixes):
        if field != 'vigilance_events':
            tags = [s.strip() for s in re.findall(r'^【'+field.upper()+r'】(.+)$',guide_text,re.M)[0].split('/')]
        else:
            fn = next(n for n in ast.parse(engine_text).body if isinstance(n,ast.FunctionDef) and n.name=='_apply_vigilance_tags')
            tags=[]
            for node in ast.walk(fn):
                if isinstance(node,ast.Compare) and isinstance(node.left,ast.Name) and node.left.id=='tag':
                    for other in node.comparators:
                        values = other.elts if isinstance(other,(ast.Tuple,ast.List)) else [other]
                        for v in values:
                            if isinstance(v,ast.Constant) and isinstance(v.value,str) and v.value not in tags: tags.append(v.value)
        groups[field]=[{'id':prefix+'_'+str(i+1).zfill(2),'tag':tag,'parameters':{},'parameter_usage':{},
                        'description':tag+'；触发条件见对应sys条目，数值不由模型计算。',
                        'pattern':r'兑换道具_[1-9]\d{0,8}' if tag=='兑换道具_X' else None} for i,tag in enumerate(tags)]
    assert [len(groups[f]) for f in fields] == [18,6,17,9,15,10]
    registry={'version':1,'groups':groups}
    index={e['id']:e for es in groups.values() for e in es}
    by_tag={}
    for field,entries in groups.items():
        for e in entries: by_tag.setdefault(e['tag'],{})[field]=e['id']
    defaults={'process_host_system':'host_events','process_shame_system':'shame_events',
              'process_depravity_system':'depravity_events','process_desire_stamina_system':'ds_events',
              'process_affection_system':'affection_events','process_pregnancy_rng':'shame_events',
              'update_persistent_buffs':'shame_events','_apply_vigilance_tags':'vigilance_events',
              'process_vigilance_system':'shame_events'}
    offsets=[]; pos=0
    for line in engine_text.splitlines(keepends=True): offsets.append(pos); pos+=len(line.encode('utf-8'))
    replacements={}
    def span(n): return offsets[n.lineno-1]+n.col_offset,offsets[n.end_lineno-1]+n.end_col_offset
    def event_id(value,field):
        if value in by_tag:
            opts=by_tag[value]
            return opts.get(field) or opts.get('shame_events') or next(iter(opts.values()))
        if value=='兑换道具_': return 'HOST_12'
        return None
    def put(n,value):
        key=span(n)
        if key in replacements: assert replacements[key]==value
        replacements[key]=value
    def walk(n, field, owner=None, label='value', parameterize=False):
        if isinstance(n,ast.JoinedStr):
            for v in n.values:
                if isinstance(v,ast.FormattedValue): walk(v.value,field,None,label,False)
            return
        if isinstance(n,ast.Constant) and isinstance(n.value,str):
            ident=event_id(n.value,field)
            if ident:
                expr='_event_tag('+repr(ident)+')'
                if n.value=='兑换道具_': expr+='[:-1]'
                put(n,expr)
            return
        if isinstance(n,ast.Constant) and type(n.value) in (int,float) and owner and parameterize:
            entry=index[owner]; cleaned=re.sub('[^a-z0-9_]+','_',label.lower()).strip('_') or 'value'
            if not cleaned[0].isalpha(): cleaned='value_'+cleaned
            key=cleaned+'_'+str(len(entry['parameters'])+1).zfill(2)
            entry['parameters'][key]=n.value; entry['parameter_usage'][key]=label
            put(n,'_event_param('+repr(owner)+', '+repr(key)+')'); return
        if isinstance(n,ast.If):
            candidates=[]
            for x in ast.walk(n.test):
                if isinstance(x,ast.Constant) and isinstance(x.value,str):
                    ident=event_id(x.value,field)
                    if ident and ident not in candidates: candidates.append(ident)
            branch=candidates[0] if candidates else owner
            walk(n.test,field,branch,label,branch is not None)
            for child in n.body: walk(child,field,branch,label,branch is not None)
            for child in n.orelse: walk(child,field,owner,label,owner is not None)
            return
        if isinstance(n,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
            target=n.targets[0] if isinstance(n,ast.Assign) else n.target
            action='增加' if isinstance(n,ast.AugAssign) and isinstance(n.op,ast.Add) else '扣减' if isinstance(n,ast.AugAssign) and isinstance(n.op,ast.Sub) else '赋值/条件值'
            label=ast.unparse(target)+' '+action
        elif isinstance(n,ast.Compare): label=ast.unparse(n.left)+' 比较阈值'
        if isinstance(n,ast.Subscript):
            walk(n.value,field,owner,label,parameterize); walk(n.slice,field,None,label,False); return
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {'group','split'}:
            for child in ast.iter_child_nodes(n): walk(child,field,None,label,False)
            return
        for child in ast.iter_child_nodes(n): walk(child,field,owner,label,parameterize)
    tree=ast.parse(engine_text)
    for fn in tree.body:
        if isinstance(fn,ast.FunctionDef):
            for child in fn.body: walk(child,defaults.get(fn.name,'shame_events'))
    raw=engine_text.encode('utf-8')
    token_edits=[]
    for (a,b),new in sorted(replacements.items(),reverse=True):
        token_edits.append({'old':raw[a:b].decode(),'new':new,'byte_start':a,'byte_end':b})
        raw=raw[:a]+new.encode()+raw[b:]
    engine_new=raw.decode()
    anchor='\n\ndef process_host_system('
    assert engine_new.count(anchor)==1
    engine_new=engine_new.replace(anchor,'\n'+LOADER+anchor,1)
    texts={'injection_core.py':engine_new,REGISTRY:json.dumps(registry,ensure_ascii=False,indent=2)+'\n'}
    changespec={'injection_core.py':{'token_edits':token_edits,'inserted_loader':LOADER}}
    def replace(rel,old,new):
        text=texts.setdefault(rel,(ROOT/rel).read_text())
        assert text.count(old)==1,(rel,old[:80],text.count(old))
        texts[rel]=text.replace(old,new,1)
        changespec.setdefault(rel,{}).setdefault('replacements',[]).append({'old':old,'new':new})
    rr='round_runtime.py'
    replace(rr,"    module.__dict__['print'] = lambda *args, **kwargs: None", "    module.__dict__['print'] = lambda *args, **kwargs: None\n    module.__dict__['_EVENT_REGISTRY_SOURCE'] = str(root / 'txt文件/事件注册表.json')")
    replace(rr,"    exec(compile(source, str(root / 'injection_core.py'), 'exec'), module.__dict__)\n    return module", "    exec(compile(source, str(root / 'injection_core.py'), 'exec'), module.__dict__)\n    try:\n        module._load_event_registry()\n    except (ValueError, OSError) as exc:\n        raise RoundError('事件注册表不可用: ' + str(exc)) from exc\n    return module")
    original=ast.get_source_segment((ROOT/rr).read_text(),next(n for n in ast.parse((ROOT/rr).read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='_event_registry'))
    replace(rr,original,"def _event_registry(root, engine):\n    return {field: {e['tag'] for e in entries}\n            for field, entries in engine._load_event_registry()['groups'].items()}")
    replace(rr,"if tag not in allowed and not (field == 'host_events' and re.fullmatch(r'兑换道具_[1-9]\\d{0,8}', tag)):","if not engine._event_accepts(field, tag):")
    replace(rr,"                if tag == '兑换道具_X':\n                    raise RoundError('兑换道具_X中的X须为实际正整数')", "                if engine._event_is_template(field, tag):\n                    raise RoundError('事件模板中的X须为实际正整数')")
    # Template-specific error stays separate from unknown-tag rejection.
    replace(rr,"                if not engine._event_accepts(field, tag):\n                    raise RoundError(field + '含未知标签: ' + tag)\n                if engine._event_is_template(field, tag):\n                    raise RoundError('事件模板中的X须为实际正整数')", "                if engine._event_is_template(field, tag):\n                    raise RoundError('事件模板中的X须为实际正整数')\n                if not engine._event_accepts(field, tag):\n                    raise RoundError(field + '含未知标签: ' + tag)")
    replace(rr,"GUARD_TAG = '日常_连续守护5回合'\nEXHAUST_TAG = '状态_空耗惩罚'", "GUARD_EVENT_ID = 'HOST_07'\nEXHAUST_EVENT_ID = 'DS_11'")
    old_fn=next(n for n in ast.parse(texts[rr]).body if isinstance(n,ast.FunctionDef) and n.name=='_derive_lifecycle')
    old=ast.get_source_segment(texts[rr],old_fn)
    new=old.replace('    result = copy.deepcopy(body)', "    guard_tag = engine._event_tag(GUARD_EVENT_ID)\n    exhaust_tag = engine._event_tag(EXHAUST_EVENT_ID)\n    result = copy.deepcopy(body)",1).replace('GUARD_TAG','guard_tag').replace('EXHAUST_TAG','exhaust_tag')
    # Clearance event spelling is also read from the same source.
    new=new.replace("'触发高潮_绝顶清算'", "engine._event_tag('DS_17')")
    replace(rr,old,new)
    replace(rr,"            self._check_source_baseline(_source_baseline)\n            body = _validate", "            definition_baseline = {rel: _digest(self._path(rel).read_bytes()) for rel in\n                                   ('injection_core.py', 'txt文件/事件注册表.json')}\n            self._check_source_baseline(_source_baseline)\n            body = _validate")
    replace(rr,"            after = self._settle(body, files, sequence, request_id)\n            self._check_source_baseline(_source_baseline)", "            after = self._settle(body, files, sequence, request_id)\n            self._check_source_baseline(definition_baseline)\n            self._check_source_baseline(_source_baseline)")
    ss='story_service.py'
    replace(ss,"'txt文件/知识库/叙事判断.json', 'txt文件/知识库/系统标签类.json')", "'txt文件/知识库/叙事判断.json', 'txt文件/知识库/系统标签类.json', 'txt文件/事件注册表.json')")
    replace(ss,"            'node_keys': node_keys, 'registered_speakers': sorted(known),", "            'node_keys': node_keys, 'registered_speakers': sorted(known),\n            'event_registry': {'path': 'txt文件/事件注册表.json', 'version': 1,\n                               'sha256': audit['txt文件/事件注册表.json'],\n                               'rule': '指南与sys条目的事件参数表由此源生成；仅按本回已发生事实选标签。'},")
    replace(ss,"RULES[1]: 'gate.V1', rr.FILES[1]: 'item.catalog', rr.FILES[2]: 'npc.minor'}", "RULES[1]: 'gate.V1', rr.FILES[1]: 'item.catalog', rr.FILES[2]: 'npc.minor',\n                  'txt文件/事件注册表.json': 'contract.events'}")
    # Generate views using exactly the engine renderer, without writing any live file.
    render=types.ModuleType('_p10_view');render.__file__=str(ROOT/'injection_core.py')
    exec(compile(engine_new,render.__file__,'exec'),render.__dict__)
    render._EVENT_REGISTRY_DATA=registry; render._EVENT_INDEX=index
    def table(field): return '【注册表生成表开始】\n'+render._render_event_table(field)+'\n【注册表生成表结束】'
    guide='txt文件/一键注入指南.txt'
    a=guide_text.index('🛑 【标签名总表'); b=guide_text.index('\n【叙事类·后端无结算】',a)
    generated='🛑 【事件标签与参数 · 注册表生成视图】\n==================================================\n唯一维护源为txt文件/事件注册表.json；本表与对应sys.*参数表由程序生成。未知、重复、错拼、错误容器或模板未实填均拒绝。通用乘数/边界/跨模块顺序仍由引擎执行；参数名及用途仅供核对，模型不手算。A/B不提交羞耻事件；事件须来自本回已发生事实。\n\n'+ '\n\n'.join(table(f) for f in fields)+'\n'
    replace(guide,guide_text[a:b],generated)
    replace(guide,'新增id可省，后端分配','新道具默认省略id，由已有_next_item_id分配；更新/消耗复用已有id或name')
    replace(guide,'同时最多一个进行中任务。奖励固定','任务id由已有_next_task_id分配，模型不提交id或猜序号。同时最多一个进行中任务。奖励固定')
    kbrel='txt文件/知识库/系统标签类.json'; kb=json.loads((ROOT/kbrel).read_bytes())
    for e in kb['data']['entries']:
        name=e['name'].split('（')[0]; text=e['content']; field=None
        if name=='sys.shame':
            field='shame_events'
            text=text.replace('内射标签在 sys.shame 常规计分(内射_常规-4、内射_首次核爆-10)','内射标签在 sys.shame 按下方生成表常规计分')
            start=text.index('【修饰/状态锁·完整标签名】');end=text.index('\n\n【AI操作清单】',start)
            text=text[:start]+'【修饰/状态锁】同质化免疫按登记折扣处理；首次影响C烈度扣分；耻感反弹使羞耻回升；无意识锁定/事件死寂锁定/解离保护停止本回下降；确诊怀孕清零。精确标签与事件参数见生成表。'+text[end:]
        elif name=='sys.depravity':
            field='depravity_events'
            text=text.replace('※每次破锁标签本身附带 +5 堕落分并把上限 cap 抬到对应档(30→60→90→100)。','※破锁标签本身附带登记增量并抬升对应上限，具体参数见生成表。')
            text=text.replace('标签名缺失「阶梯」二字后端直接静默丢弃。','标签名缺失「阶梯」二字会由固定执行器拒绝。')
        elif name=='sys.ds':
            field='ds_events'
            text=text.replace('高潮度累加至≥100%时，后端自动清空高潮、欲望回落约35、体力净值+15(结算=消耗-15+肾上腺素+30)。','高潮达到清算阈值时，后端按生成表清空高潮、回落欲望并结算体力。')
            start=text.index('【体力行为联动标签】');end=text.index('生理性断电监控：',start)
            text=text[:start]+'【体力行为联动标签】消耗/恢复按下方生成表。状态_空耗惩罚按NPC独立追踪本回DS投影欲望>70且未清算的连续成功回合，满两回合程序派生一次并归零，条件结束归零；AI不提前打标或手算累计。旧无归属全局计数不用于扣分。'+text[end:]
        elif name=='sys.affection':
            field='affection_events'
            text=text.replace('→ 解锁至 cap=95。','→ 解锁至生成表登记上限。')
        elif name=='sys.host_points':
            field='host_events'
            replacements={
              '→+2积分,+1经验。':'；奖励见生成表。','→+8积分,+5经验。':'；奖励见生成表。',
              '→+30积分,+20经验。':'；奖励见生成表。','→+50积分,+50经验。':'；奖励见生成表。',
              '→+4积分,+3经验。':'；奖励见生成表。','→+5积分,+3经验；':'；奖励见生成表；',
              '日常_温和累进→+1积分。':'日常_温和累进；奖励见生成表。',
              '→+4积分,+4经验,+4嗅觉。':'；奖励见生成表。','→+8积分,+8经验,+8嗅觉。':'；奖励见生成表。',
              '→+20积分,+20经验,+20嗅觉。':'；奖励见生成表。'}
            for a,b in replacements.items(): text=text.replace(a,b)
        elif name=='sys.vigilance':
            field='vigilance_events';start=text.index('【VIGILANCE_EVENTS标签协议');end=text.index('\n\n【死亡查岗衔接】',start)
            text=text[:start]+'【VIGILANCE_EVENTS协议】键=目标角色名，值=标签数组；精确标签和事件参数见生成表。眼线汇报不等于亲眼目击，锁定目标不受降低警惕标签影响；无异常可省略，逐回时间衰减由通用监视规则处理。'+text[end:]
        elif name=='sys.task':
            text=text.replace('经 TASK_ISSUE 提交（字段契约见《一键注入指南》任务契约节）。','经 TASK_ISSUE 提交（字段契约见《一键注入指南》任务契约节）；不提交任务id，由既有编号器分配。')
        if field: text+='\n\n【事件参数】唯一维护源：txt文件/事件注册表.json；下表为生成视图，通用计算与触发判断见上文。\n'+table(field)
        e['content']=text
    texts[kbrel]=json.dumps(kb,ensure_ascii=False,indent=2)+'\n'
    cfg='开发者功能/开发者说明书/世界书关键字配置.txt'
    replace(cfg,'内容源：txt文件/知识库/世界观类.json、叙事判断.json、系统标签类.json、角色类.json。','内容源：txt文件/知识库/世界观类.json、叙事判断.json、系统标签类.json、角色类.json；系统事件参数展示由txt文件/事件注册表.json生成，关键词路由不变。')
    idx='txt文件/故事检索索引.md'
    replace(idx,'| contract.inject | workspace → txt文件/一键注入指南.txt | 每回合 | 物理读取 |','| contract.inject | workspace → txt文件/一键注入指南.txt | 每回合 | 物理读取 |\n| contract.events | workspace → txt文件/事件注册表.json | 核对事件定义原件；指南/sys含生成视图 | 按需物理读取 |')
    doc='开发者功能/开发者说明书/开发者说明书.md'
    replace(doc,'| `txt文件/一键注入指南.txt` | 可执行脚本契约、节点字段、MEMORY、EVENTS、OPTIONS、标签名总表、计数器契约和调用格式 |','| `txt文件/事件注册表.json` | 事件标签、模板模式及事件分支参数的唯一维护源；生成指南/sys参数展示 | 剧情触发判断、可执行代码、存档事实 |\n| `txt文件/一键注入指南.txt` | 可执行脚本契约、节点字段、MEMORY、EVENTS、OPTIONS、生成事件视图、计数器契约和调用格式 |')
    replace(doc,'| 2026-11-17 | P9 微状态期限与连续回合计数 |','| 2026-11-17 | P10 事件注册表与编号复用 | 校验、结算分支参数与展示引用同源注册表；五表65标签及警惕10标签保持，任务/道具沿用既有编号器。见回合执行基础/logs/step_16.md。 |\n| 2026-11-17 | P9 微状态期限与连续回合计数 |')
    converter=types.ModuleType('_p10_converter');converter.__file__=str(ROOT/'Operit世界书导出/convert_to_operit.py')
    exec(compile((ROOT/'Operit世界书导出/convert_to_operit.py').read_bytes(),converter.__file__,'exec'),converter.__dict__)
    export=[]
    for name in ('世界观类','叙事判断','角色类','系统标签类'):
        rel='txt文件/知识库/'+name+'.json'; data=json.loads(texts.get(rel,(ROOT/rel).read_text()))
        export.extend(converter.to_operit(e) for e in data['data']['entries'])
    texts['Operit世界书导出/operit_worldbook_深渊天平.json']=json.dumps(export,ensure_ascii=False,indent=2)
    assert len(texts)==10
    suffix=datetime.datetime.now().strftime('%Y%m%d_%H%M%S'); changes=[]
    for i,(rel,text) in enumerate(texts.items()):
        path=ROOT/rel; assert path.resolve().is_relative_to(ROOT)
        raw=path.read_bytes() if path.exists() else None; after=text.encode()
        assert raw!=after
        if rel.endswith('.py'):ast.parse(after)
        if rel.endswith('.json'):json.loads(after)
        staged=BASE/'tmp'/('tmp_candidate16_'+str(i)+'.txt');staged.write_bytes(after)
        st=path.stat() if raw is not None else None
        changes.append({'path':rel,'realpath':str(path.resolve()),'before':None if raw is None else {'sha256':SHA(raw),'bytes':len(raw),'mtime_ns':st.st_mtime_ns,'mode':st.st_mode&0o777},
          'after':{'sha256':SHA(after),'bytes':len(after)},'staged':str(staged.relative_to(ROOT)),
          'backup':None if raw is None else rel+'.into-backup-'+suffix,'character_delta':len(text)-(len(raw.decode()) if raw else 0)})
    rollback='''from pathlib import Path
import hashlib,json,os
r=Path.cwd().resolve();m=json.loads((r/"开发者功能/修订日志/2026.11/回合执行基础/src/安装清单_16.json").read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for c in m["changes"]:
 p=r/c["path"]
 if c["before"]:
  assert sha(r/c["backup"])==c["before"]["sha256"]
  assert sha(p) in (c["before"]["sha256"],c["after"]["sha256"])
 else:assert not p.exists() or sha(p)==c["after"]["sha256"]
for c in m["changes"]:
 p=r/c["path"]
 if c["before"]:
  t=p.with_name("."+p.name+".round-tmp-rollback16")
  with t.open("xb") as f:f.write((r/c["backup"]).read_bytes());f.flush();os.fsync(f.fileno())
  os.chmod(t,c["before"]["mode"]);os.replace(t,p)
 elif p.exists():p.unlink()
print("ROLLBACK_PASS restored=9 removed_new=1")
'''
    manifest={'root':str(ROOT),'stage':'P10','risk':'L2/R1+R0','status':'PREPARED','changes':changes,
              'protected':{rel:info for rel,info in baseline.items() if rel not in texts},'root_names':sorted(p.name for p in ROOT.iterdir()),
              'file_edits':changespec,'upstream_sha256':SHA((BASE/'logs/step_15.md').read_bytes()),
              'plan_sha256':SHA((BASE/'plan/step_16.md').read_bytes()),'rollback_command':'python3 -c '+shlex.quote(rollback),
              'engine_reference_count':len(token_edits),'event_counts':{f:len(es) for f,es in groups.items()}}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('PREPARED existing=9 new=1 protected='+str(len(manifest['protected']))+' main_tags=65 vigilance_tags=10 references='+str(len(token_edits)))


if __name__=='__main__':main()

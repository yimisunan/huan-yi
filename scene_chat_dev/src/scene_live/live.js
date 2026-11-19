'use strict';
(() => {
 const $ = id => document.getElementById(id);
 const KEY = 'scene_live_b_ui_v1';
 const PEOPLE = ['沈知韫', '苏婉青', '徐念薇'];
 let cache = {sceneId:'', draft:'', pending:null};
 let snapshot = null, online = false, compatible = false, posting = false, polling = false;
 let storageOK = true, signature = '', castSignature = '', lastSpeaker = '', error = '', pendingMissing = false, pendingConflict = false;
 let portraitName = '', createUncertain = false, pendingFailure = '';
 let worldData = null, worldCapable = false, worldPosting = false, boundWorldCurrent = true;
 try {
  const value = JSON.parse(localStorage.getItem(KEY) || '{}');
  if (typeof value.sceneId === 'string') cache.sceneId = value.sceneId;
  if (typeof value.draft === 'string') cache.draft = value.draft;
  if (value.pending && typeof value.pending.request_id === 'string' && typeof value.pending.input === 'string' && typeof value.pending.scene_id === 'string' && Number.isInteger(value.pending.base_scene_revision)) cache.pending = value.pending;
 } catch (_) { storageOK = false; }
 function save() {
  try { localStorage.setItem(KEY, JSON.stringify(cache)); storageOK = true; }
  catch (_) { storageOK = false; }
  $('saveHint').textContent = storageOK ? '已接受回复由服务保存' : '本机存储不可用，发送已暂停；已接受记录仍可恢复';
  return storageOK;
 }
 function node(tag, className, text) {
  const n = document.createElement(tag); if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
 }
 async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
   const response = await fetch('/api/story/' + path, {cache:'no-store', signal:controller.signal,
    ...(body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Story-Client':'1'}, body:JSON.stringify(body)})});
   let value; try { value = await response.json(); } catch (_) { throw new Error('服务未返回有效数据，请确认已重启 Python 服务。'); }
   if (!response.ok) { const e = new Error(value.error || '服务请求失败'); e.status = response.status; throw e; }
   return value;
  } catch (e) { if (controller.signal.aborted) throw new Error('连接等待超时，原消息状态需要查询。'); throw e; }
  finally { clearTimeout(timer); }
 }
 function activeTask() { return !!snapshot?.active || ['queued','generating'].includes(snapshot?.task?.status); }
 function controls() {
  const active = activeTask(), scene = snapshot?.scene, p = cache.pending;
  $('send').disabled = posting || polling || !online || !compatible || !storageOK || !scene || active || !!p || worldPosting || !boundWorldCurrent || scene.revision >= 24;
  $('create').disabled = posting || polling || !online || !compatible || active || !!p || worldPosting || createUncertain;
  $('refresh').disabled = posting || polling || worldPosting;
  $('checkPending').hidden = !p;
  $('checkPending').disabled = posting || polling;
  $('resendPending').hidden = !p || !pendingMissing || pendingConflict;
  $('resendPending').disabled = posting || !online || active;
  $('editPending').hidden = !p || !pendingMissing || pendingConflict;
  $('editPending').disabled = posting || !online;
  $('retry').hidden = !['failed','interrupted'].includes(snapshot?.task?.status);
  $('retry').disabled = posting || !!p || active || !online || !compatible;
  $('history').disabled = !scene || !scene.history.length;
  const w = worldData?.world, playerPlace = w?.presence?.['徐志北']?.value?.location;
  const available = PEOPLE.filter(name=>playerPlace && w.presence[name]?.value?.location===playerPlace);
  $('importWorld').disabled = !worldCapable || worldPosting || posting || polling || active || !!p;
  $('startWorld').disabled = !worldCapable || worldPosting || posting || polling || active || !!p || !worldData?.source_current || !available.length || createUncertain;
  const task = snapshot?.task;
  const pendingText = p ? '待确认：' + p.input : task && ['queued','generating','failed','interrupted'].includes(task.status) ? '待处理：' + task.input : '';
  $('pending').textContent = pendingText; $('pending').hidden = !pendingText;
  if (error) { $('status').textContent = error; $('status').classList.add('error'); }
  else {
   $('status').classList.remove('error');
   $('status').textContent = !compatible ? '服务消息协议待更新，请重启 Python 服务。' : !online ? '服务连接已中断，记录与待发消息保留。' : p ? pendingConflict ? '原编号与服务记录不符，请保留现场并检查连接信息。' : pendingMissing ? pendingFailure || '服务尚未登记该编号，可按原编号发送或放回草稿。' : '正在查询原消息是否送达……' : active ? task?.status === 'generating' ? '正在回复，可继续编辑草稿。' : '已排队，等待 Operit 桥接。' : scene?.revision >= 24 ? '已到当前交流边界，请保留记录并新建场景。' : !boundWorldCurrent ? '绑定的旧存档已变化，请在存档状态中重新导入并开启新场景。' : task?.error || (scene ? '已就绪，可以继续接话。' : '选择已有场景，或建立一个新场景。');
  }
  if ($('sceneDialog').open) for (const b of $('sceneList').querySelectorAll('button')) b.disabled = posting || !!p;
 }
 function image(name, file = 'into.png') { return '/txt文件/image/' + encodeURIComponent(name) + '/' + file; }
 function showPortrait(name, file = 'fullbody.png') {
  if (!PEOPLE.includes(name)) return;
  portraitName = name; $('portraitName').textContent = name;
  $('portrait').src = image(name,file); $('portrait').alt = name + '立绘';
  document.querySelectorAll('[data-file]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.file === file)));
  if (!$('portraitDialog').open) $('portraitDialog').showModal();
 }
 function entry(kind, speaker, text, id) {
  const n = node('article', 'msg ' + kind + (speaker === '徐志北' ? ' player' : ''));
  n.dataset.messageId = id;
  n.setAttribute('aria-label', kind === 'narration' ? '旁白' : kind === 'handoff' ? '待处理事项' : speaker + (kind === 'action' ? '的动作' : '的对白'));
  if (kind === 'narration') n.append(node('div','narration-mark','旁白'));
  else {
   if (PEOPLE.includes(speaker)) { const im = node('img','avatar'); im.src = image(speaker); im.alt = ''; n.append(im); }
   const heading = node('div','message-heading'); heading.append(node('span','',speaker));
   if (kind === 'action') heading.append(node('span','kind-label','动作'));
   n.append(heading);
  }
  n.append(node('div','text',text));
  return n;
 }
 function timeline() {
  const result = [];
  for (const turn of snapshot?.scene?.history || []) {
   result.push(entry('dialogue','徐志北',turn.input,turn.id + ':input'));
   turn.messages.forEach((m,i) => result.push(entry(m.kind,m.speaker,m.text,turn.id + ':' + i)));
   if (turn.handoff) result.push(entry('handoff','待处理 · 尚未执行',turn.handoff,turn.id + ':handoff'));
  }
  return result;
 }
 function latest() { $('stream').scrollTo({top:$('stream').scrollHeight,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}); $('jump').hidden = true; }
 function render() {
  const s = snapshot?.scene;
  $('sceneTitle').textContent = s?.location || '一起坐坐';
  $('sceneMeta').textContent = s ? (s.world_id ? '存档交流 · ' : '实验交流 · ') + s.cast.join(' / ') : '先选择一个场景，再开始交流。';
  $('revision').textContent = s ? s.revision + ' 次已保存交流' : '尚未建立场景';
  const next = s ? s.id + ':' + s.revision : '';
  if (next !== signature) {
   const stream = $('stream'), switching = !signature || signature.split(':')[0] !== s?.id;
   const near = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 100;
   const oldTop = stream.scrollTop;
   $('messages').replaceChildren(...timeline());
   signature = next;
   $('messageCount').textContent = $('messages').children.length;
   const recent = s?.history.flatMap(t=>t.messages).filter(m=>m.speaker).at(-1);
   lastSpeaker = recent?.speaker || s?.cast[0] || '';
   if (switching || near) latest(); else { stream.scrollTop = oldTop; $('jump').hidden = false; }
   if ($('historyDialog').open) $('historyList').replaceChildren(...timeline());
  }
  $('empty').hidden = !!s?.history.length;
  $('emptyManage').textContent = s ? '更换场景' : '选择场景';
  const castNext = s?.id || '';
  if (castNext !== castSignature) {
   castSignature = castNext; $('cast').replaceChildren();
   for (const name of s?.cast || []) {
    const b = node('button','person-button'); b.type='button'; b.dataset.name=name; b.setAttribute('aria-label','查看'+name+'立绘');
    const im=node('img');im.src=image(name);im.alt='';b.append(im,node('span','',name));b.onclick=()=>showPortrait(name);$('cast').append(b);
   }
  }
  $('cast').querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',String(b.dataset.name===lastSpeaker)));
  controls(); sizing();
 }
 async function protocol() {
  const data = await api('scene/connection');
  compatible = data.scene_protocol >= 3 && data.message_kinds?.includes('action');
  worldCapable = data.world_state_protocol >= 1;
  if (!compatible) throw new Error('当前服务尚未加载三类消息协议，请重启语音运行.py 后刷新。');
  return data;
 }
 function sameRequest(task,p) { return task.id === p.request_id && task.scene === p.scene_id && task.input === p.input && task.base === p.base_scene_revision; }
 async function restore() {
  if (polling || posting || worldPosting) return;
  polling = true; controls();
  try {
   if (!compatible) await protocol();
   let resolved = null;
   if (cache.pending) {
    resolved = (await api('scene/request/' + encodeURIComponent(cache.pending.request_id))).task;
    pendingMissing = !resolved;
    pendingConflict = !!resolved && !sameRequest(resolved,cache.pending);
    if (resolved && !pendingConflict) cache.sceneId = resolved.scene;
   }
   snapshot = await api('scene' + (cache.sceneId ? '?id=' + encodeURIComponent(cache.sceneId) : ''));
   if (snapshot.scene?.world_id && worldCapable) {
    const current = await api('scene/world?id='+encodeURIComponent(snapshot.scene.world_id));
    boundWorldCurrent = current.source_current;
   } else boundWorldCurrent = !snapshot.scene?.world_id;
   online = true; error = '';
   if (resolved && !pendingConflict) { cache.pending = null; pendingMissing = false; }
   if (snapshot.scene) cache.sceneId = snapshot.scene.id;
   if (cache.sceneId && !snapshot.scene) error = '该场景在当前服务中不存在。请检查连接信息或从场景管理选择记录。';
   save(); render();
  } catch (e) { online = false; error = e.message; }
  finally { polling = false; controls(); }
 }
 async function dispatch() {
  if (posting || polling || !cache.pending) return;
  posting = true; error = ''; controls();
  const pending = cache.pending;
  try { await api('scene/messages',pending); pendingMissing = false; }
  catch (e) { pendingFailure = e.message; error = '发送状态待确认：' + e.message; }
  finally { posting = false; await restore(); controls(); }
 }
 async function manager() {
  if (!$('sceneDialog').open) $('sceneDialog').showModal();
  $('setupStatus').textContent = ''; $('sceneList').textContent = '正在读取……';
  try {
   const data = await api('scene/list');
   createUncertain = false;
   $('sceneList').replaceChildren();
   if (!data.scenes.length) $('sceneList').textContent = '还没有场景。';
   for (const s of data.scenes) {
    const b=node('button','scene-choice',s.location+' · '+s.cast.join(' / '));b.type='button';b.dataset.id=s.id;
    b.append(node('span','',s.revision+' 次交流 · '+(s.world_id?'存档交流 · ':'实验 · ')+(s.task_status||'尚未发送')));b.setAttribute('aria-current',String(s.id===snapshot?.scene?.id));
    b.onclick=async()=>{if(posting||polling||cache.pending)return;cache.sceneId=s.id;save();await restore();if(online)$('sceneDialog').close();};
    $('sceneList').append(b);
   }
  } catch(e) { $('sceneList').textContent = e.message; }
  controls();
 }
 $('form').onsubmit = async event => {
  event.preventDefault(); if ($('send').disabled || polling) return;
  const text=$('input').value;if(!text.trim())return;
  const id='scene-'+(crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
  cache.pending={request_id:id,scene_id:snapshot.scene.id,base_scene_revision:snapshot.scene.revision,input:text};
  cache.draft='';pendingMissing=false;pendingConflict=false;pendingFailure='';
  if(!save()){cache.pending=null;cache.draft=text;controls();return;}
  $('input').value='';$('input').style.height='auto';await dispatch();
 };
 $('input').addEventListener('input',()=>{cache.draft=$('input').value;save();$('input').style.height='auto';$('input').style.height=Math.min($('input').scrollHeight,96)+'px';sizing();controls();});
 $('input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('form').requestSubmit();}});
 $('refresh').onclick=restore; $('checkPending').onclick=restore; $('resendPending').onclick=dispatch;
 $('editPending').onclick=()=>{if(!cache.pending||!pendingMissing||pendingConflict||posting)return;cache.draft=[cache.pending.input,cache.draft].filter(Boolean).join('\n');cache.pending=null;pendingMissing=false;$('input').value=cache.draft;save();controls();sizing();};
 $('retry').onclick=async()=>{if($('retry').disabled||polling)return;posting=true;error='';controls();try{await api('scene/retry/'+encodeURIComponent(snapshot.task.id),{});}catch(e){error=e.message;}finally{posting=false;const failure=error;await restore();if(failure){error=failure;controls();}}};
 $('createForm').onsubmit=async event=>{
  event.preventDefault();if($('create').disabled||polling)return;
  const cast=[...$('createForm').querySelectorAll('input[name=cast]:checked')].map(n=>n.value),place=$('newLocation').value.trim();
  if(cast.length<1||cast.length>2||!place){$('setupStatus').textContent='请选择一至两位人物，并填写地点。';return;}
  posting=true;controls();
  try{snapshot=await api('scene',{cast,location:place});boundWorldCurrent=true;cache.sceneId=snapshot.scene.id;online=true;error='';signature='';save();render();$('sceneDialog').close();}
  catch(e){createUncertain=!e.status;$('setupStatus').textContent=createUncertain?'创建结果待确认，请重新打开场景管理查看已有记录。':e.message;}
  finally{posting=false;controls();}
 };
 $('manage').onclick=manager; $('emptyManage').onclick=manager;
 $('history').onclick=()=>{$('historyList').replaceChildren(...timeline());$('historyDialog').showModal();};
 $('connection').onclick=async()=>{if(!$('connectionDialog').open)$('connectionDialog').showModal();const view={origin:location.origin,path:location.pathname,scene_id:snapshot?.scene?.id||cache.sceneId,revision:snapshot?.scene?.revision,request_id:cache.pending?.request_id||snapshot?.task?.id};try{Object.assign(view,await api('scene/connection'));}catch(e){view.error=e.message;}$('connectionText').textContent=JSON.stringify(view,null,2);};
 $('manageConnection').onclick=()=>{$('sceneDialog').close();$('connection').click();};
  function sourceDetails(source) {
   const details=node('details','source-details'), label=node('summary','','查看来源');
   details.append(label,node('p','muted',source.path+' · '+source.start_line+'–'+source.end_line+' 行'),node('pre','',source.raw||''));
   return details;
  }
  function worldSection(title) {const n=node('section','world-section');n.append(node('h3','',title));$('worldContent').append(n);return n;}
  function renderWorld() {
   const box=$('worldContent');box.replaceChildren();
   const w=worldData?.world;
   if(!w){$('worldStatus').textContent=worldCapable?'读取后可查看人物所在、数值、库存、任务和已有记忆。':'请先重启 Python 服务，加载存档状态接口。';controls();return;}
   $('worldStatus').textContent=(worldData.source_current?'已读取旧回合 '+w.legacy_snapshot.round+' · ':'来源已变化 · ')+(w.legacy_snapshot.sceneTitle||'')+'。交流保存在隔离副本，旧存档保持原状。'+(worldData.source_error||'');
   $('importWorld').textContent='重新读取旧存档';
   let section=worldSection('人物所在');
   for(const [name,item] of Object.entries(w.presence)){
    const row=node('div','state-row');row.append(node('strong','',name),node('span','',item.value.location+' · '+item.value.reason),sourceDetails(item.origin));section.append(row);
   }
   section=worldSection('当前数值');
   for(const [name,item] of Object.entries(w.panels)){
    const card=node('details','state-card');card.append(node('summary','',name));
    const dl=node('dl');for(const [key,value] of Object.entries(item.value))dl.append(node('dt','',key),node('dd','',String(value)));card.append(dl,sourceDetails(item.origin));section.append(card);
   }
   section=worldSection('道具与任务');
   const itemUnclear=w.unresolved_source.some(v=>v.domain==='items'), taskUnclear=w.unresolved_source.some(v=>v.domain==='tasks'||v.domain==='【任务状态】');
   section.append(node('p','',itemUnclear?'库存有待确认内容，展开下方待确认项查看。':w.items.length?'活跃道具 '+w.items.length+' 种':'当前库存为空'));
   for(const item of w.items){const d=node('details');d.append(node('summary','',item.name+' × '+item.quantity),node('pre','',JSON.stringify(item.fields,null,2)),sourceDetails(item.origin));section.append(d);}
   section.append(node('p','',taskUnclear?'任务存在待确认内容。':w.tasks.current?'当前任务：'+w.tasks.current.title:'当前任务：无'));
   if(w.tasks.origin)section.append(sourceDetails(w.tasks.origin));
   section=worldSection('已有记忆');
   if(!w.memories.length)section.append(node('p','muted','旧存档没有有效记忆条目。'));
   for(const item of w.memories){const d=node('details','memory-card');d.append(node('summary','',item.layer+' · 回合 '+item.start_round+(item.end_round!==item.start_round?'–'+item.end_round:'')),node('p','muted',item.known_by?'已核查知情：'+item.known_by.join('、'):'知情范围待确认，暂不作为人物上下文'),node('p','memory-text',item.value),sourceDetails(item.origin));section.append(d);}
   section=worldSection('其他存档状态');
   for(const [label,source] of Object.entries(w.state_sections)){if(source){const d=node('details');d.append(node('summary','',label),sourceDetails(source));section.append(d);}}
   const pending=worldSection('待确认 · '+w.unresolved_source.length);
   if(!w.unresolved_source.length)pending.append(node('p','muted','本次来源没有未识别条目。'));
   for(const issue of w.unresolved_source){const d=node('details');d.append(node('summary','',issue.domain+' · '+issue.reason),sourceDetails(issue.origin));pending.append(d);}
   const provenance=worldSection('导入记录');
   provenance.append(node('p','muted','版本 '+w.world_revision+' · '+w.world_id.slice(0,12)+'。旧选项已过期；实验聊天保留独立记录。行动与资源结算尚未启用。'));
   const d=node('details');d.append(node('summary','','来源指纹'),node('pre','',JSON.stringify(w.source_manifest,null,2)));provenance.append(d);
   const playerPlace=w.presence['徐志北']?.value?.location, cast=PEOPLE.filter(name=>playerPlace&&w.presence[name]?.value.location===playerPlace);
   $('startWorld').textContent=cast.length?'在'+playerPlace+'与'+cast.slice(0,2).join('、')+'继续':'暂无同地可交流人物';
   controls();
  }
  $('world').onclick=async()=>{
   if(!$('worldDialog').open)$('worldDialog').showModal();
   $('worldStatus').textContent='正在读取……';
   try{if(!worldCapable)await protocol();if(worldCapable){worldData=await api('scene/world'+(snapshot?.scene?.world_id?'?id='+encodeURIComponent(snapshot.scene.world_id):''));}renderWorld();}
   catch(e){$('worldStatus').textContent=e.message;}
  };
  $('importWorld').onclick=async()=>{
   if($('importWorld').disabled)return;worldPosting=true;controls();$('worldStatus').textContent='正在读取旧存档……';
   try{worldData=await api('scene/world/import',{});renderWorld();}
   catch(e){$('worldStatus').textContent=e.message;}
   finally{worldPosting=false;controls();}
  };
  $('startWorld').onclick=async()=>{
   if($('startWorld').disabled)return;
   const w=worldData.world,place=w.presence['徐志北'].value.location,cast=PEOPLE.filter(name=>w.presence[name]?.value.location===place).slice(0,2);
   worldPosting=true;controls();
   try{snapshot=await api('scene',{world_id:w.world_id,cast});cache.sceneId=snapshot.scene.id;boundWorldCurrent=true;online=true;error='';signature='';save();render();$('worldDialog').close();}
   catch(e){createUncertain=!e.status;$('worldStatus').textContent=e.status?e.message:'创建结果待确认，请打开场景管理查看已有记录。';}
   finally{worldPosting=false;controls();}
  };

 document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
 document.querySelectorAll('[data-file]').forEach(b=>b.onclick=()=>showPortrait(portraitName,b.dataset.file));
 $('jump').onclick=latest;$('stream').addEventListener('scroll',()=>{if($('stream').scrollHeight-$('stream').scrollTop-$('stream').clientHeight<70)$('jump').hidden=true;});
 function sizing(){document.documentElement.style.setProperty('--bottom',Math.ceil($('composer').getBoundingClientRect().height)+'px');}
 if(window.ResizeObserver)new ResizeObserver(sizing).observe($('composer'));
 function viewport(){const v=window.visualViewport;document.documentElement.style.setProperty('--keyboard',Math.max(0,innerHeight-v.height-v.offsetTop)+'px');sizing();}
 if(window.visualViewport){visualViewport.addEventListener('resize',viewport);visualViewport.addEventListener('scroll',viewport);}
 window.addEventListener('resize',sizing);document.addEventListener('visibilitychange',()=>{if(!document.hidden)void restore();});
 $('input').value=cache.draft;save();render();void restore();setInterval(()=>{if(!document.hidden)void restore();},2500);
})();
'use strict';
(() => {
 const $=id=>document.getElementById(id), KEY='abyss_official_live_v1', PEOPLE=['沈知韫','苏婉青','徐念薇'];
 const LABELS={A:'日常互动',B:'社交接触',C:'主动行为'};
 let cache={epoch:'',draft:'',pending:null,voice:true},snapshot=null,online=false,posting=false,polling=false,progressing=false;
 let storageOK=true,error='',missing=false,mismatch=false,portraitName='',signature='',lastSpeaker='',history=[],hasOlder=false,olderCursor=null,resetRequest=null;
 let audioSerial=0,audioMessage=null,audioStatus='',gesture=false,configPromise=null,lastTap=0;
 const urls=new VoiceClient.AudioUrlStore(8,16*1024*1024),audioCache=new Map();
 try{const v=JSON.parse(localStorage.getItem(KEY)||'{}');
  if(typeof v.epoch==='string')cache.epoch=v.epoch;
  if(typeof v.draft==='string')cache.draft=v.draft;
  if(typeof v.voice==='boolean')cache.voice=v.voice;
  if(v.pending&&typeof v.pending.request_id==='string'&&typeof v.pending.action==='string'&&typeof v.pending.base_revision==='string')cache.pending=v.pending;
 }catch(_){storageOK=false;}
 function node(tag,cls,text){const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;}
 function save(){try{localStorage.setItem(KEY,JSON.stringify(cache));storageOK=true;}catch(_){storageOK=false;}
  $('saveHint').textContent=storageOK?(progression()?'剧情与阅读进度自动保存 · 点按不收费':'剧情与阅读进度自动保存 · 资源政策待启用'):'浏览器存储不可用，提交已暂停';return storageOK;}
 async function api(path,body){return VoiceClient.requestJson('/api/story/'+path,{cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Story-Client':'1'},body:JSON.stringify(body)})},12000);}
 const active=()=>['preparing','queued','generating','validating','refund_pending'].includes(snapshot?.task?.status);
 const baseBlocked=()=>posting||polling||progressing||!online||!storageOK||![2,3].includes(snapshot?.interaction_protocol)||!!cache.pending||active();
 const canDecide=()=>!!snapshot?.playback?.segment_id&&snapshot.playback.completed;
 const blocked=()=>baseBlocked()||!canDecide();
 const current=()=>history.find(t=>t.id===snapshot?.playback?.segment_id);
 const progression=()=>snapshot?.world?.progression;
 const resting=()=>!!progression()&&(progression().runtime.phase==='resting'||(snapshot?.task?.reservation?.status!=='held'&&progression().stamina<5));
 const pureRecovery=()=>/^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test($('input').value);
 const afford=n=>!progression()||progression().stamina>=n;
 const ordinaryBlocked=()=>blocked()||resting();
 function controls(){
  const p=snapshot?.playback,ready=canDecide(),base=baseBlocked(),hasSegment=!!p?.segment_id;
     const rest=resting();
   $('decisionPanel').hidden=!ready||rest;$('form').hidden=!ready||rest;
   $('rest').hidden=!ready||!rest;$('rest').disabled=base;
   $('cancelTask').hidden=!active()||!snapshot?.task?.reservation;$('cancelTask').disabled=posting||progressing;
   const pg=progression(),res=snapshot?.task?.reservation;
   $('resourceStatus').textContent=pg?(res?.status==='held'?'已暂扣 '+res.quote.total+' · 原体力 '+res.quote.before+' · 结算后判断疲惫':'体力 '+pg.stamina+' / 100 · 道具可恢复额度 '+pg.item_budget)+(pg.runtime.clock?' · 第'+pg.runtime.clock.day+'天 '+pg.runtime.clock.time:''):'';
   $('resourceStatus').hidden=!pg;
   $('useRecovery').disabled=ordinaryBlocked()||!$('recoveryItem').value||!pg||pg.item_budget<=0||pg.stamina>=100;
     $('send').disabled=ordinaryBlocked()||(!pureRecovery()&&!afford(15));$('input').disabled=!ready||posting||progressing||!online||!storageOK||!!cache.pending||active();
     $('actions').hidden=!ready||rest;$('actions').disabled=ordinaryBlocked()||!afford(15);
  $('move').disabled=ordinaryBlocked()||!afford(15)||!$('destination').value;$('give').disabled=ordinaryBlocked()||!afford(15)||!$('item').value||!$('recipient').value;
     $('choices').querySelectorAll('button').forEach(b=>b.disabled=ordinaryBlocked()||!afford({A:5,B:10,C:15}[b.dataset.option]));
  $('playbackBar').hidden=!hasSegment;
  $('advance').hidden=!hasSegment||p.completed;$('advance').disabled=base;
  $('advance').textContent=progressing?'正在保存进度…':!p?.revealed?'开始演播':p.revealed<p.total?'继续剧情':'读完本段 · 查看抉择';
  $('playbackCount').textContent=hasSegment?(p.completed?'本段已读完':p.revealed+' / '+p.total+' · 点击正文或继续按钮'):'准备当前剧情';
  $('voiceToggle').textContent=cache.voice?'语音已开启':'语音已静音';$('voiceToggle').setAttribute('aria-pressed',String(cache.voice));
  $('replayVoice').hidden=!audioMessage;$('replayVoice').textContent=audioStatus.includes('启用')?'启用语音':'重听当前';
  $('audioStatus').textContent=audioStatus;
  $('begin').hidden=hasSegment;$('begin').disabled=base;
   if(!hasSegment)$('begin').textContent=rest?'开始休息 · 免费':'继续当前剧情';
  $('refresh').disabled=posting||polling||progressing;$('retry').hidden=!['failed','interrupted','cancelled'].includes(snapshot?.task?.status);
  $('retry').disabled=base;$('older').disabled=posting||polling||progressing;$('confirmNewGame').disabled=base;
  $('checkPending').hidden=!cache.pending;$('checkPending').disabled=posting||polling||progressing;
  $('resendPending').hidden=!cache.pending||!missing||mismatch;$('resendPending').disabled=posting||polling||!online||active();
  $('editPending').hidden=!cache.pending||!missing||mismatch;$('editPending').disabled=posting||polling||!online;
  const task=snapshot?.task;
  $('pending').textContent=cache.pending?'待确认：'+cache.pending.action:task&&['queued','generating','validating','failed','interrupted'].includes(task.status)?'待处理：'+task.action:'';
  $('pending').hidden=!$('pending').textContent;
  $('status').classList.toggle('error',!!error||!!task?.error);
  $('status').textContent=error||(!online?'正在连接本地服务，原行动已保留。':![2,3].includes(snapshot?.interaction_protocol)?'请重启本地服务，加载剧情演播接口。':cache.pending?mismatch?'原编号与服务记录不符，请保留连接详情。':missing?'原编号尚未登记，可按原编号重发。':'正在查询原行动…':active()?task.status==='generating'?'正在依据当前存档推演剧情…':task.status==='validating'?'正在校验与保存…':'已排队，等待 Operit 桥接。':task?.error||(!hasSegment?'准备好后，继续当前剧情。':!p.completed?'点按观看，读完本段后选择下一步。':!snapshot.bridge_connected?'抉择已就绪，桥接待连接。':rest?'本段已收束，继续完成休息。':'此刻由你决定。'));
  $('bridgeInfo').textContent=(snapshot?.bridge_connected?'桥接已连接':'桥接未连接')+(snapshot?.bridge_model?' · '+snapshot.bridge_model.model_id:'')+(snapshot?.bridge?.last_error?' · '+snapshot.bridge.last_error:'');
 }
 function image(name,file='into.png'){return '/txt文件/image/'+encodeURIComponent(name)+'/'+file;}
 function showPortrait(name,file='fullbody.png'){portraitName=name;$('portraitName').textContent=name;$('portrait').src=image(name,file);$('portrait').alt=name+'立绘';document.querySelectorAll('[data-file]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.file===file)));if(!$('portraitDialog').open)$('portraitDialog').showModal();}
 function stopVoice(){audioSerial++;VoiceClient.cancel('live');$('audio').pause();$('audio').onended=null;audioStatus='';}
 function unlock(){if(gesture)return;gesture=true;
  // A silent, local sample primes the media element from this actual user gesture.
  $('audio').src='data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
  const result=$('audio').play();if(result?.catch)result.catch(()=>{});
 }
 async function speak(m,id){
  stopVoice();audioMessage={m,id};if(!cache.voice||!gesture){controls();return;}
  const serial=audioSerial;audioStatus='准备语音…';controls();
  try{
   let url=audioCache.get(id);
   if(!url||!urls.has(url)){
    configPromise=configPromise||VoiceClient.requestJson('/api/config',{cache:'no-store'}).catch(e=>{configPromise=null;throw e;});
    const config=await configPromise;if(serial!==audioSerial||document.hidden)return;
    const who=m.kind==='dialogue'?m.speaker:'旁白',cfg=config[who]||config['旁白']||{};
    const blob=await VoiceClient.requestAudio(VoiceClient.buildPayload(m.text,cfg,config.__settings__||{}),{channel:'live',maxBytes:16*1024*1024});
    if(serial!==audioSerial||document.hidden)return;
    url=urls.add(blob);audioCache.set(id,url);
    for(const [key,value]of audioCache)if(!urls.has(value))audioCache.delete(key);
   }
   if(serial!==audioSerial||!cache.voice||document.hidden)return;
   urls.pin(url);$('audio').src=url;await $('audio').play();if(serial!==audioSerial)return;
   audioStatus='正在朗读';$('audio').onended=()=>{if(serial===audioSerial){audioStatus='朗读完成 · 点按继续';controls();}};
  }catch(e){if(serial===audioSerial)audioStatus=e.name==='NotAllowedError'?'点“启用语音”后继续听读':'语音暂不可用，可继续阅读或点重听';}
  controls();
 }
 function entry(kind,speaker,text,id){
  const el=node('article','msg '+kind+(speaker==='徐志北'?' player':''));el.dataset.messageId=id;
  el.setAttribute('aria-label',kind==='narration'?'旁白':speaker+(kind==='action'?'的动作':'的对白'));
  if(kind==='narration')el.append(node('div','narration-mark','旁白'));
  else{if(PEOPLE.includes(speaker)){const im=node('img','avatar');im.src=image(speaker);im.alt='';el.append(im);}const h=node('div','message-heading');h.append(node('span','',speaker));if(kind==='action')h.append(node('span','kind-label','动作'));el.append(h);}
  el.append(node('div','text',speaker==='徐志北'?text:text.replace(/\[[^\]\r\n]+\]/g,'')));return el;
 }
 function timeline(){const out=[];for(const t of history){
  if(t.selection?.option_id!=='BEGIN')out.push(entry(t.input_kind==='action'?'action':'dialogue','徐志北',t.input,t.id+':input'));
  t.messages.forEach((m,i)=>out.push(entry(m.kind,m.speaker,m.text,t.id+':'+i)));
     if(t.handoff)out.push(entry('handoff','待处理',t.handoff,t.id+':handoff'));
   if(t.settlement&&t.id!==snapshot?.playback?.segment_id)out.push(settlementCard(t.settlement));
 }return out;}
 function icon(name){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');svg.classList.add('game-icon');
  const paths={energy:'M13 2 4 14h7l-1 8 10-13h-7l1-7Z',coin:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v10m3-8c-1-2-6-2-6 1 0 3 6 1 6 4 0 3-5 3-6 1',heart:'M12 20 3 11C-2 5 7-1 12 6 17-1 26 5 21 11L12 20Z',moon:'M20 15A8 8 0 0 1 9 4a9 9 0 1 0 11 11Z',check:'M4 12l5 5L20 6',bag:'M5 7h14l2 14H3L5 7Zm3 0V5a4 4 0 0 1 8 0v2',refund:'M8 4 3 9l5 5M3 9h11a6 6 0 0 1 0 12',clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v6l4 2'};
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[name]||paths.check);path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');path.setAttribute('stroke-width','1.6');path.setAttribute('stroke-linecap','round');path.setAttribute('stroke-linejoin','round');svg.append(path);return svg;
 }
 function settlementCard(s){
  const box=node('section','settlement-card game-settlement'+(s.phase==='resting'?' resting':s.sleep_completed?' rested':''));
  const header=node('div','settlement-head'),title=node('div','settlement-title'),mark=node('span','reward-mark');mark.append(icon(s.sleep_completed?'moon':s.phase==='resting'?'clock':'check'));title.append(mark,node('div','',s.sleep_completed?'安稳醒来':s.phase==='resting'?'本段收束':'行动已结算'));header.append(title,node('span','settlement-badge',s.kind==='item'?'道具恢复':s.kind==='rest'?'免费休息':s.net_cost+' 体力'));box.append(header);
  const balance=node('div','balance-line'),label=node('span','');label.append(icon('energy'),node('span','','体力'));balance.append(label,node('strong','',s.stamina_before+' → '+s.stamina_after),node('span','balance-cap','/ 100'));box.append(balance);
  const meter=node('div','stamina-meter');meter.setAttribute('role','meter');meter.setAttribute('aria-label','结算后体力');meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax','100');meter.setAttribute('aria-valuenow',String(s.stamina_after));const fill=node('span','stamina-fill');fill.style.setProperty('--balance',Math.max(0,Math.min(100,s.stamina_after))+'%');meter.append(fill);box.append(meter);
  const fees=node('div','fee-line');for(const [key,value]of [['暂扣',s.reserved],['返还',s.refunded],['实耗',s.net_cost]]){const part=node('span','');part.append(node('small','',key),node('b','',String(value)));fees.append(part);}box.append(fees);
  const changes=s.changes||[],rewards=changes.filter(c=>c.target!=='系统宿主'||c.attribute!=='体力');
  if(rewards.length){const badges=node('div','reward-list');for(const c of rewards.slice(0,3)){const tag=node('span','reward-pill');tag.append(icon(c.attribute==='好感'?'heart':'coin'),node('span','',c.target+' '+c.attribute+' '+(c.delta>0?'+':'')+c.delta));badges.append(tag);}box.append(badges);}
  if(s.item){const note=node('p','item-receipt');note.append(icon('bag'),node('span','',s.item.name+' × 1 · 恢复 '+s.item.recovery+' · 剩余额度 '+s.item_budget));box.append(note);}
  if(s.closed_round)box.append(node('p','round-receipt','记忆回合 '+s.closed_round+' 已结算'));
  if(s.phase==='resting')box.append(node('p','round-receipt','请完成休息后再行动'));
  if(s.sleep_completed)box.append(node('p','round-receipt','体力恢复至上限 · 道具额度重置'));
  const detail=node('details','settlement-details'),summary=node('summary','','查看本次明细');detail.append(summary);
  for(const c of changes)detail.append(node('p','',c.target+' · '+c.attribute+' '+c.before+' → '+c.after+'（'+(c.delta>0?'+':'')+c.delta+'）'));
  if(s.items_changed&&!s.item)detail.append(node('p','','库存已按实际增量更新，可在状态中查看'));
  if(s.task_after?.current)detail.append(node('p','','任务：'+s.task_after.current.title+' · '+s.task_after.current.status));
  if(s.clock)detail.append(node('p','','游戏第'+s.clock.day+'天 '+s.clock.time));
  if(s.events)for(const [group,value]of Object.entries(s.events)){const tags=Array.isArray(value)?value:Object.entries(value).flatMap(([who,values])=>values.map(tag=>who+' · '+tag));if(tags.length)detail.append(node('p','muted',tags.join(' / ')));}
  box.append(detail);return box;
 }
 function renderSettlement(){
  const box=$('settlement'),refund=snapshot?.task?.refund,s=refund?null:snapshot?.settlement;box.hidden=!s&&!refund;
  const key=s?.request_id||(refund?snapshot.task.request_id+':refund':'');
  if(box.dataset.id===key)return;box.dataset.id=key;box.replaceChildren();
  if(s)box.append(settlementCard(s));
  else if(refund){const card=node('section','settlement-card game-settlement returned'),title=node('div','settlement-title');title.append(icon('refund'),node('strong','','预扣已返还'));card.append(title,node('p','','返还 '+refund.amount+' 体力'),node('p','muted',refund.reason));box.append(card);}
 }

 function latest(){const el=$('stream');el.scrollTo({top:el.scrollHeight,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});$('jump').hidden=true;}
 function options(id,items){const old=$(id).value;$(id).replaceChildren(...items.map(([v,l])=>{const o=node('option','',l);o.value=v;return o;}));if(items.some(([v])=>v===old))$(id).value=old;}
 function renderWorld(){const w=snapshot?.world,box=$('worldContent');box.replaceChildren();if(!w)return;
  const section=title=>{const s=node('section','world-section');s.append(node('h3','',title));box.append(s);return s;};
  let s=section('人物所在');for(const [name,p]of Object.entries(w.presence))s.append(node('p','',name+' · '+p.location));
  s=section('当前状态');for(const p of w.panels)s.append(node('p','',p));
  s=section('库存与已交付物品');if(!w.items.length)s.append(node('p','muted','当前没有物品。'));for(const i of w.items)s.append(node('p','',i.name+' × '+i.quantity+' · '+i.fields['当前状态']+(i.fields['使用对象']?' · '+i.fields['使用对象']:'')));
  s=section('任务');s.append(node('p','',w.tasks?.current?JSON.stringify(w.tasks.current):'当前无任务'));if(w.tasks?.history?.length)w.tasks.history.forEach(t=>s.append(node('p','muted',t)));
     s=section('存档');s.append(node('p','',w.interaction.count+' 次已保存剧情 · '+w.interaction.actions+' 次登记行动'));
   if(w.progression){const p=w.progression;s.append(node('p','',p.runtime.memory_round+' · 当前记忆回合，跨零点或不足5收束'),node('p','muted','整夜休息恢复至100；道具累计额度剩余 '+p.item_budget));}
 }
 function render(){const w=snapshot?.world,p=snapshot?.playback;
     $('policyNote').textContent=progression()?'A 5 · B 10 · C 15体力 · 自定义暂扣15后退差额':'按设定与存档推进 · 本段读完后抉择';
  $('sceneTitle').textContent=w?.location||'正在回到现场';$('sceneMeta').textContent=w?(w.cast.length?w.cast.join(' / '):'此刻独处'):'读取本地存档…';
  $('revision').textContent=w?w.interaction.count+' 次已保存剧情':'';
  const sig=cache.epoch+':'+history.map(t=>t.id+':'+t.messages.length+':'+(t.handoff||'')+':'+!!t.settlement).join('|');
  if(sig!==signature){const stream=$('stream'),near=stream.scrollHeight-stream.scrollTop-stream.clientHeight<120,top=stream.scrollTop;signature=sig;
   $('messages').replaceChildren(...timeline());$('messageCount').textContent=$('messages').children.length;
   lastSpeaker=history.flatMap(t=>t.messages).filter(m=>m.speaker).at(-1)?.speaker||'';
   if(near)latest();else{stream.scrollTop=top;$('jump').hidden=false;}
   if($('historyDialog').open)$('historyList').replaceChildren(...timeline());
  }
  $('older').hidden=!hasOlder;$('empty').hidden=!!p?.segment_id;
  const names=w?.cast||[];if($('cast').dataset.names!==names.join('|')){$('cast').dataset.names=names.join('|');$('cast').replaceChildren(...names.map(name=>{const b=node('button','person-button');b.type='button';b.dataset.name=name;b.setAttribute('aria-label','查看'+name+'立绘');const im=node('img');im.src=image(name);im.alt='';b.append(im,node('span','',name));b.onclick=()=>showPortrait(name);return b;}));}
  $('cast').querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',String(b.dataset.name===lastSpeaker)));
  const turn=current(),decision=turn?.decision,decisionKey=p?.completed?turn?.id:'';
  if($('choices').dataset.key!==decisionKey){$('choices').dataset.key=decisionKey||'';$('choices').replaceChildren();
   if(decision){$('decisionPrompt').textContent=decision.prompt;for(const opt of decision.options){const b=node('button','story-option');b.type='button';b.dataset.option=opt.id;b.append(node('span','option-label',opt.id+' · '+LABELS[opt.id]+(progression()?' · '+({A:5,B:10,C:15}[opt.id])+'体力':'')),node('span','option-text',opt.text));b.onclick=()=>enqueue(opt.text,null,opt.id);$('choices').append(b);}}
  }
  if(w){options('destination',w.policy.locations.filter(place=>place!==w.location).map(place=>[place,place]));options('recipient',w.cast.map(name=>[name,name]));options('item',w.items.filter(i=>i.fields['当前状态']==='仓库中'&&['','无','未使用','徐志北'].includes(i.fields['使用对象'])).map(i=>[i.id,i.name+' × '+i.quantity]));}
     if(w)options('recoveryItem',[['','请选择实际恢复道具'],...w.items.filter(i=>i.fields['当前状态']==='仓库中'&&/^host_stamina:[1-9]\d*$/.test(i.fields['系统效果']||'')&&['','无','未使用','徐志北'].includes(i.fields['使用对象'])).map(i=>[i.id,i.name+' × '+i.quantity])]);
   renderSettlement();renderWorld();controls();sizing();
 }
 function canonical(value){if(!value)return null;return Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]]));}
 function same(task,p){return task.request_id===p.request_id&&task.action===p.action&&task.base_revision===p.base_revision&&JSON.stringify(canonical(task.operation))===JSON.stringify(canonical(p.operation))&&JSON.stringify(canonical(task.selection))===JSON.stringify(canonical(p.selection))&&task.entry_mode===p.entry_mode&&task.save_epoch===p.save_epoch;}
 function absorb(fresh){
  if(cache.epoch&&cache.epoch!==fresh.save_epoch){cache={epoch:fresh.save_epoch,draft:'',pending:null,voice:cache.voice};$('input').value='';history=[];signature='';olderCursor=null;missing=false;mismatch=false;error='已切换新档，旧行动与进度已隔离。';}
  if(snapshot?.playback?.segment_id!==fresh.playback?.segment_id){stopVoice();audioMessage=null;}
  cache.epoch=fresh.save_epoch;snapshot=fresh;const map=new Map(history.map(t=>[t.id,t]));fresh.history.forEach(t=>map.set(t.id,t));history=[...map.values()].sort((a,b)=>a.sequence-b.sequence);
  if(!audioMessage&&fresh.playback?.revealed){const turn=history.find(t=>t.id===fresh.playback.segment_id),i=fresh.playback.revealed-1;if(turn?.messages[i])audioMessage={m:turn.messages[i],id:turn.id+':'+i};}
  if(olderCursor===null)hasOlder=fresh.has_older;save();render();
 }
 async function restore(){if(posting||polling||progressing)return;polling=true;controls();try{
  const fresh=await api('live');online=true;error='';
  if(cache.pending){let task;try{task=(await api('tasks/'+encodeURIComponent(cache.pending.request_id))).task;}catch(e){if(e.status!==404)throw e;}
   missing=!task;mismatch=!!task&&!same(task,cache.pending);if(task&&!mismatch){cache.pending=null;missing=false;}}
  absorb(fresh);
 }catch(e){online=false;error=e.message;}finally{polling=false;controls();}}
 async function advance(){
  if(baseBlocked()||!snapshot?.playback?.segment_id||snapshot.playback.completed||Date.now()-lastTap<300)return;
  lastTap=Date.now();unlock();stopVoice();progressing=true;error='';controls();
  const p=snapshot.playback,revealed=Math.min(p.total,p.revealed+1),completed=p.revealed===p.total;
  try{const fresh=await api('live/progress',{save_epoch:cache.epoch,segment_id:p.segment_id,revealed,completed});absorb(fresh);latest();
   if(!completed){const turn=current(),m=turn?.messages[revealed-1];if(m)void speak(m,turn.id+':'+(revealed-1));}
  }catch(e){error='演播进度待确认：'+e.message;}finally{progressing=false;controls();}}
 async function dispatch(){if(posting||polling||progressing||!cache.pending)return;posting=true;stopVoice();error='';controls();try{await api('tasks',cache.pending);}catch(e){error='提交状态待确认：'+e.message;}finally{posting=false;await restore();controls();}}
 async function enqueue(text,op=null,optionId='CUSTOM'){
     if(baseBlocked()||!text.trim()||(optionId!=='BEGIN'&&!canDecide()))return;
   if(optionId!=='REST'&&optionId!=='BEGIN'&&(resting()||!afford(optionId==='CUSTOM'?(/^\s*使用恢复道具\s*[：:]?\s*ITEM-\d+\s*[。！!]?\s*$/.test(text)?0:15):({A:5,B:10,C:15}[optionId]))))return;
     const selected={segment_id:optionId==='BEGIN'?'':snapshot.playback.segment_id,option_id:optionId};
  cache.pending={request_id:'live-'+(crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)),base_revision:snapshot.revision,save_epoch:cache.epoch,entry_mode:'live_interaction',action:text,selection:selected,...(snapshot.bridge_model?{model_key:snapshot.bridge_model.key}:{}),...(op?{operation:op}:{})};
  if(optionId==='CUSTOM'&&!op)cache.draft='';missing=false;mismatch=false;
  if(!save()){cache.pending=null;cache.draft=text;controls();return;}
  if(optionId==='CUSTOM'&&!op){$('input').value='';$('input').style.height='auto';}await dispatch();
 }
   $('rest').onclick=()=>enqueue('继续休息',null,'REST');
  $('useRecovery').onclick=()=>{if($('useRecovery').disabled)return;void enqueue('使用恢复道具 '+$('recoveryItem').value,{code:'use_recovery_item',item_id:$('recoveryItem').value});};
  $('recoveryItem').onchange=controls;
  $('cancelTask').onclick=async()=>{if(posting||!snapshot?.task)return;posting=true;controls();try{await api('tasks/'+encodeURIComponent(snapshot.task.request_id)+'/cancel',{});}catch(e){error=e.message;}finally{posting=false;await restore();}};
  $('advance').onclick=advance;$('begin').onclick=()=>enqueue('继续当前剧情',null,'BEGIN');
 $('voiceToggle').onclick=()=>{unlock();cache.voice=!cache.voice;save();if(!cache.voice)stopVoice();else if(audioMessage)void speak(audioMessage.m,audioMessage.id);controls();};
 $('replayVoice').onclick=()=>{if(!audioMessage)return;unlock();cache.voice=true;save();void speak(audioMessage.m,audioMessage.id);};
 $('stream').addEventListener('click',e=>{if(e.target.closest('button,a,input,textarea,select')||getSelection()?.toString())return;void advance();});
 $('stream').addEventListener('keydown',e=>{if(e.target===$('stream')&&['Enter',' '].includes(e.key)){e.preventDefault();void advance();}});
 $('form').onsubmit=e=>{e.preventDefault();void enqueue($('input').value);};
 $('input').addEventListener('input',()=>{cache.draft=$('input').value;save();controls();$('input').style.height='auto';$('input').style.height=Math.min($('input').scrollHeight,96)+'px';sizing();});
 $('input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('form').requestSubmit();}});
 $('refresh').onclick=restore;$('checkPending').onclick=restore;$('resendPending').onclick=dispatch;
 $('editPending').onclick=()=>{if(!cache.pending||!missing||mismatch||posting||polling)return;cache.draft=[cache.pending.action,cache.draft].filter(Boolean).join('\n');cache.pending=null;$('input').value=cache.draft;save();controls();};
 $('retry').onclick=async()=>{if(baseBlocked())return;posting=true;controls();try{await api('tasks/'+encodeURIComponent(snapshot.task.request_id)+'/retry',snapshot.bridge_model?{model_key:snapshot.bridge_model.key}:{});}catch(e){error=e.message;}finally{posting=false;await restore();}};
 $('world').onclick=()=>{renderWorld();$('worldDialog').showModal();};
 $('actions').onclick=()=>{if(blocked())return;$('actionStatus').textContent='登记行动作为本次自定义选择提交。';render();$('actionDialog').showModal();};
 $('moveForm').onsubmit=async e=>{e.preventDefault();if($('move').disabled)return;const dest=$('destination').value;$('actionDialog').close();await enqueue('前往'+dest,{code:'move_player',destination:dest});};
 $('giveForm').onsubmit=async e=>{e.preventDefault();if($('give').disabled)return;const id=$('item').value,who=$('recipient').value,item=snapshot.world.items.find(i=>i.id===id);$('actionDialog').close();await enqueue('把'+item.name+'整组交给'+who,{code:'transfer_item',item_id:id,recipient:who});};
 $('destination').onchange=controls;$('item').onchange=controls;$('recipient').onchange=controls;
 $('newGame').onclick=()=>{$('worldDialog').close();$('newGameStatus').textContent='';resetRequest=null;$('newGameDialog').showModal();controls();};
 $('confirmNewGame').onclick=async()=>{if(baseBlocked())return;posting=true;controls();resetRequest=resetRequest||{request_id:'reset-'+(crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)),save_epoch:cache.epoch,confirm:'new_game'};
  try{await api('new-game',resetRequest);$('newGameDialog').close();}catch(e){$('newGameStatus').textContent=e.message+'；可按原编号再次确认。';}finally{posting=false;await restore();}};
 $('history').onclick=()=>{$('historyList').replaceChildren(...timeline());$('historyDialog').showModal();};
 $('older').onclick=async()=>{if(posting||polling||progressing||!history.length)return;polling=true;controls();try{const fresh=await api('live?before='+history[0].sequence);if(fresh.save_epoch!==cache.epoch){polling=false;await restore();return;}const map=new Map(history.map(t=>[t.id,t]));fresh.history.forEach(t=>map.set(t.id,t));history=[...map.values()].sort((a,b)=>a.sequence-b.sequence);hasOlder=fresh.has_older;olderCursor=history[0]?.sequence||0;render();}catch(e){error=e.message;}finally{polling=false;controls();}};
 $('connection').onclick=()=>{$('connectionText').textContent=JSON.stringify({origin:location.origin,revision:snapshot?.revision,save_epoch:snapshot?.save_epoch,playback:snapshot?.playback,task:snapshot?.task,bridge:snapshot?.bridge,model:snapshot?.bridge_model},null,2);controls();$('connectionDialog').showModal();};
 for(const [id,action]of [['bridgeStart','start'],['bridgeStop','stop']])$(id).onclick=async()=>{if(posting)return;posting=true;controls();try{await api('bridge/control',{action});}catch(e){error=e.message;}finally{posting=false;await restore();}};
 document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());document.querySelectorAll('[data-file]').forEach(b=>b.onclick=()=>showPortrait(portraitName,b.dataset.file));
 $('jump').onclick=latest;$('stream').addEventListener('scroll',()=>{if($('stream').scrollHeight-$('stream').scrollTop-$('stream').clientHeight<70)$('jump').hidden=true;});
 function sizing(){document.documentElement.style.setProperty('--bottom',Math.ceil($('composer').getBoundingClientRect().height)+'px');}
 if(window.ResizeObserver)new ResizeObserver(sizing).observe($('composer'));
 function viewport(){const v=window.visualViewport;document.documentElement.style.setProperty('--keyboard',Math.max(0,innerHeight-v.height-v.offsetTop)+'px');sizing();}
 if(window.visualViewport){visualViewport.addEventListener('resize',viewport);visualViewport.addEventListener('scroll',viewport);}
 window.addEventListener('resize',sizing);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stopVoice();else void restore();});
 window.addEventListener('pagehide',()=>{stopVoice();urls.clear();});
 $('input').value=cache.draft;save();render();void restore();setInterval(()=>{if(!document.hidden)void restore();},2500);
})();

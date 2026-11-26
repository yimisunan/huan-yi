'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../local.story.operit_bridge/main.js'),'utf8');
function createBox(){
 const config={workspacePath:'/fixture',endpoint:'http://127.0.0.1:5000',chatId:'legacy',participantId:'legacy-card',inFlight:null,outbox:null};
 const box={exports:{},console,setTimeout,clearTimeout,setInterval,clearInterval,config,ToolPkg:{ipc:{on(){}}},PluginConfig:{flush:async()=>{}}};
 vm.createContext(box);vm.runInContext(source,box);
 vm.runInContext(`let created=0;ensureSession=async(child,model,mode,persist)=>{if(!child.chatId)child.chatId='live-'+(++created);if(!child.participantId)child.participantId='card';await persist();return {chatId:child.chatId,participantId:child.participantId};};`,box);
 box.Tools={Chat:{agentStatus:async()=>({isIdle:true})}};box.model={key:'model-1'};
 box.task={request_id:'request-1',save_epoch:'save-1',interaction_scope:'scope-1',service_epoch:'boot-1',packet_bytes:200000};
 return box;
}
async function run(){
 const box=createBox(),call=()=>vm.runInContext('liveSession(config,model,task)',box);
 const first=await call();box.config.liveSession.observedChars=9000000;
 box.task={...box.task,request_id:'request-2',interaction_scope:'scope-2',service_epoch:'boot-2'};
 assert.equal((await call()).chatId,first.chatId,'continuous must ignore packet size, scene and restart');
 box.config.liveSessionPolicy='service_restart';box.task.service_epoch='boot-3';const restarted=await call();assert.notEqual(restarted.chatId,first.chatId);assert.equal((await call()).chatId,restarted.chatId);
 box.config.liveSessionPolicy='per_action';box.task.request_id='request-3';const perAction=await call();box.task.attempt=2;assert.equal((await call()).chatId,perAction.chatId,'retry keeps current chat');
 box.task.request_id='request-4';assert.notEqual((await call()).chatId,perAction.chatId);
 const beforeReset=box.config.liveSession.chatId;await vm.runInContext('resetLiveSession(config,"玩家手动重建")',box);assert.notEqual((await call()).chatId,beforeReset);
 const beforeModel=box.config.liveSession.chatId;box.model.key='model-2';assert.notEqual((await call()).chatId,beforeModel);
 const beforeSave=box.config.liveSession.chatId;box.task.save_epoch='save-2';assert.notEqual((await call()).chatId,beforeSave);
 box.config.inFlight={};await assert.rejects(vm.runInContext('resetLiveSession(config,"manual")',box),/结束/);box.config.inFlight=null;
 console.log('PASS continuous/restart/per-action/retry/manual/model/save session policies; no chat deletion');
 const flow=createBox();flow.task={...flow.task,entry_mode:'live_interaction',reading_preflight:1,live_reading_revision:2,action_contract_revision:1,material_delivery_revision:1,lease:'lease',previous_validation_error:'原错误',turns:[{kind:'user',content:JSON.stringify({entry_mode:'live_interaction',packet:{path:'packet',read_ranges:[{start_line:1,end_line:2}]},output_contract:{messages:[],decision:{},operation:'',handoff:'',checks:{},resolution:{sleep:{}}},instruction:'读取正文'})}]};
 flow.config.liveSession={observedChars:0,chatId:'same-chat'};flow.session={chatId:'same-chat',participantId:'card'};flow.calls=[];flow.httpBodies=[];flow.maxChecks=1;flow.savedText='';flow.inputText=JSON.stringify({envelope:JSON.parse(flow.task.turns[0].content),material:{previous_validation_error:'原错误'},material_delivery:'program_inline_v1'});
 vm.runInContext(`settings=async()=>config;currentChat=async()=>'return-chat';restoreChat=async()=>{};checkModel=async()=>{throw new Error("global model switched during attempt");};let checked=0;http=async(p,b)=>{if(p.endsWith('bridge-info'))return {token:'token'};if(p.endsWith('/material'))return {input_text:inputText,delivery:{id:'a'.repeat(48),input_sha256:'b'.repeat(64)}};httpBodies.push(b);return ++checked<=maxChecks ? {ready:false,missing_keys:['packet'],read_targets:[{key:'packet',reads:[{path:'packet',start_line:2,end_line:2}]}]} : {ready:true};};`,flow);
 flow.Tools.Chat.cancel=async()=>{};flow.Tools.Chat.getMessages=async()=>({chatId:'same-chat',messages:[{sender:'user',timestamp:10,content:flow.savedText}]});
 flow.Tools.Chat.sendMessageStreaming=async function*(request){flow.calls.push(request);if(flow.calls.length===1)flow.savedText=request.input.text;const stamp=flow.calls.length+10;yield {type:'part',chatId:'same-chat',messageTimestamp:stamp,revision:1,parts:[{kind:'tool_call',toolName:'read_file_part',partId:'call',attributes:{path:'packet',start_line:String(stamp),end_line:String(stamp)}},{kind:'tool_result',toolName:'read_file_part',attributes:{status:'success'},content:stamp+'| 正文'},{kind:'markdown',content:'{"messages":[],"operation":"","handoff":"","resolution":{"task":"","conditions":"","sleep":{"start":""}}}'}]};yield {type:'completed',result:{chatId:'same-chat',outcome:{type:'committed',status:'completed',userMessageTimestamp:10,assistant:{messageTimestamp:stamp}}}};};
 const body=await vm.runInContext('executeSession(config,task,model,session)',flow);
 assert.equal(flow.calls.length,2);assert(flow.calls.every(x=>x.chatId==='same-chat'));assert.equal(body.conversation_audit.tools.length,2);assert.equal(body.conversation_audit.read_passes.length,2);
 const repair=JSON.parse(flow.calls[1].input.text);assert.equal(repair.entry_mode,'live_interaction');assert(repair.task_envelope.output_contract.resolution);assert.equal(repair.request_id,'request-1');assert.equal(repair.read_repair.read_targets[0].reads[0].start_line,2);assert(flow.calls[0].input.text.includes('原错误'));
 flow.maxChecks=9;flow.calls.length=0;vm.runInContext('checked=0',flow);await assert.rejects(vm.runInContext('executeSession(config,task,model,session)',flow),/仍缺/);assert.equal(flow.calls.length,2);
 console.log('PASS same-chat one repair, cumulative proof, full contract, error handoff, second missing stops');

 // 2.1.2 Regression A: External chat deletion bypasses boundChatCache -> ensureSession recreates chatId -> liveSession forces isFresh=true and resets counters.
 {
  const extStore = new Map();
  const b2={exports:{},console,setTimeout,clearTimeout,setInterval,clearInterval,
   config:{workspacePath:'/fixture',endpoint:'http://127.0.0.1:5000',chatId:'',participantId:'model:chat',inFlight:null,outbox:null,dualStageEnabled:true,liveSessionPolicy:'continuous'},
   ToolPkg:{ipc:{on(){}},callDependency:async(pkg,fn)=>{ throw new Error('must not call dependency '+pkg+':'+fn); }},
   PluginConfig:{flush:async()=>{}},
   existingChats:new Set(['chat-1']),
   createdSeq:1,
  };
  b2.Tools={
   Chat:{
    listChats:async({chat_ids})=>({chats:(chat_ids||[]).filter(id=>b2.existingChats.has(id)).map(id=>({id}))}),
    agentStatus:async()=>({isIdle:true}),
    createNew:async()=>{const id='chat-'+(++b2.createdSeq);b2.existingChats.add(id);return {chatId:id};},
    updateTitle:async()=>{},
    cancel:async()=>{},
    writeExtension:async(target,val)=>{extStore.set(target.chatId,val);return {extension:val};},
    readExtension:async(target)=>({extension:extStore.get(target.chatId)||null}),
   },
   SoftwareSettings:{exec:async()=>({success:true})},
  };
  vm.createContext(b2);vm.runInContext(source,b2);
  b2.model={key:'p1:m1',provider_id:'p1',model_id:'m1'};
  b2.task={request_id:'r1',save_epoch:'s1',interaction_scope:'loc|cast',service_epoch:'ep1',material_delivery_v2:1};
  const s1=await vm.runInContext('liveSession(config,model,task)',b2);
  assert.equal(s1.chatId,'chat-2');assert.equal(s1.isFresh,true);
  // Populate boundChatCache + simulate 4 committed turns on chat-2
  b2.config.liveSession.turnCount=4;b2.config.liveSession.lastCommittedSeq=12;b2.config.liveSession.observedChars=8888;
  b2.task={...b2.task,request_id:'r2'};
  const s2=await vm.runInContext('liveSession(config,model,task)',b2);
  assert.equal(s2.chatId,'chat-2');assert.equal(s2.isFresh,false);
  // Externally delete chat-2 in Operit while boundChatCache still holds it!
  b2.existingChats.delete('chat-2');
  b2.task={...b2.task,request_id:'r3'};
  const s3=await vm.runInContext('liveSession(config,model,task)',b2);
  assert.equal(s3.chatId,'chat-3','must create fresh chat when bound chat was externally deleted');
  assert.equal(s3.isFresh,true,'external chat deletion must force isFresh=true');
  assert.equal(b2.config.liveSession.turnCount,0);
  assert.equal(b2.config.liveSession.lastCommittedSeq,0);
  assert.equal(b2.config.liveSession.observedChars,0);
  assert.equal(b2.config.liveSession.dirty,false);
  assert.equal(b2.config.liveSession.resetReason,'外部窗口已重建');

  // 2.1.2 Regression B: interruptedSession on v2 marks outbox.meta.isV2 and liveSession.dirty
  b2.config.inFlight={request_id:'r-crash',lease:'lease-9',model_key:'p1:m1',entry_mode:'live_interaction',chat_id:'chat-3',return_chat_id:'',is_v2:true};
  b2.config.outbox=null;
  await vm.runInContext('interruptedSession(config)',b2);
  assert.equal(b2.config.inFlight,null);
  assert.equal(b2.config.outbox.meta.isV2,true);
  assert.equal(b2.config.liveSession.dirty,true);

  // 2.1.2 Regression C: syncServiceEpoch resets workerSeq on service_epoch change
  vm.runInContext('workerSeq=42; syncServiceEpoch("ep-A"); syncServiceEpoch("ep-A");',b2);
  assert.equal(vm.runInContext('workerSeq',b2),42);
  vm.runInContext('syncServiceEpoch("ep-B");',b2);
  assert.equal(vm.runInContext('workerSeq',b2),0);
  console.log('PASS 2.1.2 external chat deletion -> fresh reset, v2 interruptedSession dirty/isV2, syncServiceEpoch workerSeq reset');
 }
}
run().catch(e=>{console.error(e);process.exitCode=1;});
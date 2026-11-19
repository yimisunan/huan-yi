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
 const flow=createBox();flow.task={...flow.task,entry_mode:'live_interaction',reading_preflight:1,live_reading_revision:2,action_contract_revision:1,lease:'lease',previous_validation_error:'原错误',turns:[{kind:'user',content:JSON.stringify({entry_mode:'live_interaction',packet:{path:'packet',read_ranges:[{start_line:1,end_line:2}]},output_contract:{messages:[],decision:{},operation:'',handoff:'',checks:{},resolution:{sleep:{}}},instruction:'读取正文'})}]};
 flow.config.liveSession={observedChars:0,chatId:'same-chat'};flow.session={chatId:'same-chat',participantId:'card'};flow.calls=[];flow.httpBodies=[];flow.maxChecks=1;
 vm.runInContext(`settings=async()=>config;currentChat=async()=>'return-chat';restoreChat=async()=>{};checkModel=async()=>{};let checked=0;http=async(p,b)=>{if(p.endsWith('bridge-info'))return {token:'token'};httpBodies.push(b);return ++checked<=maxChecks ? {ready:false,missing_keys:['packet'],read_targets:[{key:'packet',reads:[{path:'packet',start_line:2,end_line:2}]}]} : {ready:true};};`,flow);
 flow.Tools.Chat.cancel=async()=>{};
 flow.Tools.Chat.sendMessageStreaming=async function*(request){flow.calls.push(request);const stamp=flow.calls.length;yield {type:'part',chatId:'same-chat',messageTimestamp:stamp,revision:1,parts:[{kind:'tool_call',toolName:'read_file_part',partId:'call',attributes:{path:'packet',start_line:String(stamp),end_line:String(stamp)}},{kind:'tool_result',toolName:'read_file_part',attributes:{status:'success'},content:stamp+'| 正文'},{kind:'markdown',content:'{"messages":[],"operation":"","handoff":"","resolution":{"task":"","conditions":"","sleep":{"start":""}}}'}]};yield {type:'completed',result:{chatId:'same-chat',outcome:{type:'committed',status:'completed',assistant:{messageTimestamp:stamp}}}};};
 const body=await vm.runInContext('executeSession(config,task,model,session)',flow);
 assert.equal(flow.calls.length,2);assert(flow.calls.every(x=>x.chatId==='same-chat'));assert.equal(body.conversation_audit.tools.length,2);assert.equal(body.conversation_audit.read_passes.length,2);
 const repair=JSON.parse(flow.calls[1].input.text);assert.equal(repair.entry_mode,'live_interaction');assert(repair.task_envelope.output_contract.resolution);assert.equal(repair.request_id,'request-1');assert.equal(repair.read_repair.read_targets[0].reads[0].start_line,2);assert(flow.calls[0].input.text.includes('原错误'));
 flow.maxChecks=9;flow.calls.length=0;vm.runInContext('checked=0',flow);await assert.rejects(vm.runInContext('executeSession(config,task,model,session)',flow),/仍缺/);assert.equal(flow.calls.length,2);
 console.log('PASS same-chat one repair, cumulative proof, full contract, error handoff, second missing stops');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
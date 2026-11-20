'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../local.story.operit_bridge/main.js'),'utf8');
async function attempt(mutate=false,suffix=''){
 const config={workspacePath:'/fixture',liveSession:{observedChars:0,chatId:'chat'}};
 const payload=JSON.stringify({material_delivery:'program_inline_v1',envelope:{output_contract:{}},material:{input:'本轮行动',private:'仅玩家知情',previous_validation_error:'上次错误'}});
 const box={exports:{},ToolPkg:{ipc:{on(){}}},PluginConfig:{flush:async()=>{}},console,setTimeout,clearTimeout,setInterval,clearInterval,config,calls:[],checks:0,payload,
 task:{entry_mode:'live_interaction',request_id:'x',reading_preflight:1,live_reading_revision:2,action_contract_revision:1,material_delivery_revision:1,lease:'lease',previous_validation_error:'上次错误'},session:{chatId:'chat',participantId:'card'},model:{key:'m'}};
 vm.createContext(box);vm.runInContext(source,box);
 vm.runInContext(`currentChat=async()=>'';restoreChat=async()=>{};http=async(p,b)=>{if(p.endsWith('bridge-info'))return {token:'token'};if(p.endsWith('/material'))return {input_text:payload,delivery:{id:'a'.repeat(48),input_sha256:'b'.repeat(64)}};checks++;return {ready:true};};`,box);
 box.Tools={Chat:{cancel:async()=>{},getMessages:async()=>({chatId:'chat',messages:[{sender:'user',timestamp:10,content:mutate?payload.slice(0,-1):payload+suffix}]}),sendMessageStreaming:async function*(request){
  box.calls.push(request);
  yield {type:'part',chatId:'chat',messageTimestamp:20,revision:1,parts:[{kind:'markdown',content:'{"messages":[],"operation":"","handoff":""}'}]};
  yield {type:'completed',result:{chatId:'chat',outcome:{type:'committed',status:'completed',userMessageTimestamp:10,assistant:{messageTimestamp:20}}}};
 }}};
 const result=await vm.runInContext('executeSession(config,task,model,session)',box);
 assert.equal(box.calls.length,1);assert.equal(box.calls[0].input.text,payload);assert.equal(box.checks,1);
 assert.equal(result.conversation_audit.tools.length,0);assert.equal(result.conversation_audit.delivery.user_message_timestamp,10);assert.equal(result.timing.generation_passes,1);
}
(async()=>{await attempt();await attempt(false,'\n<workspace_attachment>workspace</workspace_attachment>');await assert.rejects(attempt(true),/资料不完整/);await assert.rejects(attempt(false,'forged'),/资料不完整/);console.log('BRIDGE_MATERIAL_OK one submit, zero tools, persisted body verified, tampering rejected');})().catch(e=>{console.error(e);process.exitCode=1;});
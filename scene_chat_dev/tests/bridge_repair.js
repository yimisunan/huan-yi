'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../local.story.operit_bridge/main.js'),'utf8');
async function run(invalidTwice=false){
 const payload=JSON.stringify({material_delivery:'program_inline_v1',envelope:{output_contract:{messages:[],operation:'',handoff:''}},material:{input:'本轮行动'}});
 const config={workspacePath:'/fixture',liveSession:{observedChars:0,chatId:'chat'},inFlight:null,outbox:null};
 const box={exports:{},console,setTimeout,clearTimeout,setInterval,clearInterval,config,payload,calls:0,
  PluginConfig:{flush:async()=>{}},ToolPkg:{ipc:{on(){}}},
  task:{entry_mode:'live_interaction',request_id:'repair-test',reading_preflight:1,live_reading_revision:2,action_contract_revision:1,material_delivery_revision:1,lease:'lease'},
  session:{chatId:'chat',participantId:'card'},model:{key:'m'}};
 vm.createContext(box);vm.runInContext(source,box);
 vm.runInContext(`currentChat=async()=>'';restoreChat=async()=>{};http=async(p,b)=>{if(p.endsWith('bridge-info'))return {token:'token'};if(p.endsWith('/material'))return {input_text:payload,delivery:{id:'a'.repeat(48),input_sha256:'b'.repeat(64)}};return {ready:true};};`,box);
 box.Tools={Chat:{cancel:async()=>{},
  getMessages:async()=>({chatId:'chat',messages:[{sender:'user',timestamp:10,content:payload}]}),
  sendMessageStreaming:async function*(){
   box.calls++;
   const first=box.calls===1;
   const text=first?'这不是JSON':JSON.stringify({messages:[{kind:'narration',speaker:'',text:'回应'}],operation:'',handoff:''});
   const stamp=first?20:40;
   yield {type:'part',chatId:'chat',messageTimestamp:stamp,revision:1,parts:[{kind:'markdown',content:invalidTwice&&!first?'也不是JSON':text}]};
   yield {type:'completed',result:{chatId:'chat',outcome:{type:'committed',status:'completed',userMessageTimestamp:first?10:30,assistant:{messageTimestamp:stamp}}}};
  }}};
 try{
  const body=await vm.runInContext('executeSession(config,task,model,session)',box);
  return {body,box};
 }catch(error){if(invalidTwice)return {error,box};throw error;}
}
(async()=>{
 const {body,box}=await run();
 assert.equal(box.calls,2,'exactly one format correction');
 assert.equal(body.conversation_audit.read_passes.length,2);
 assert.equal(body.conversation_audit.delivery.user_message_timestamp,10);
 assert.equal(body.conversation_audit.read_passes[0].tool_count,0);
 assert.equal(body.timing.generation_passes,2);
 const again=await run(true);
 assert(again.error);assert.equal(again.box.calls,2,'must not loop more than once');
 console.log('BRIDGE_FORMAT_REPAIR_OK one same-chat JSON correction, first delivery receipt kept, second failure stops');
})().catch(error=>{console.error(error);process.exitCode=1;});
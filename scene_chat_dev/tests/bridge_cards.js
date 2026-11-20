'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../local.story.operit_bridge/main.js'),'utf8');
const MARKS='local.story.operit_bridge:readonly';
function boxFor(mode){
 const config={workspacePath:'/fixture',chatId:'',participantId:''};
 const calls=[];
 const box={exports:{},console,setTimeout,clearTimeout,setInterval,clearInterval,config,calls,
  PluginConfig:{flush:async()=>{}},ToolPkg:{ipc:{on(){}},callDependency:async()=>{}}};
 vm.createContext(box);vm.runInContext(source,box);
 const model={provider_id:'provider',model_id:'model'};
 const expected=vm.runInContext('roleChanges(model,"live")',Object.assign(box,{model}));
 const card={...expected,id:'card-1',marks:MARKS};
 box.ToolPkg.callDependency=async(dep,method,args)=>{
  calls.push(method);
  if(method==='character.list') return [{id:'card-1',name:expected.name}];
  if(method==='character.get') return mode==='owned'?card:{...card,marks:'other'};
  if(method==='character.create') throw new Error('角色卡名称已存在：'+expected.name);
  if(method==='character.update') return {...card,...args.changes};
  if(method==='chat.configuration.binding.read') return {selection:'card:'+config.participantId};
  throw new Error('unexpected dependency '+method);
 };
 box.Tools={Chat:{listChats:async()=>({chats:[]}),createNew:async()=>({chatId:'chat-1'}),updateTitle:async()=>{},
  agentStatus:async()=>({isIdle:true})},SoftwareSettings:{exec:async()=>({success:true})}};
 box.model=model;
 return box;
}
(async()=>{
 const owned=boxFor('owned');
 const session=await vm.runInContext('ensureSession(config,model,"live")',owned);
 assert.equal(session.participantId,'card-1');assert.equal(owned.config.participantId,'card-1');
 assert(!owned.calls.includes('character.create'),'must adopt existing owned card, not create');
 assert(!owned.calls.includes('character.update'),'matching card must not be rewritten');
 const foreign=boxFor('foreign');
 await assert.rejects(vm.runInContext('ensureSession(config,model,"live")',foreign),/同名角色卡已存在但不是本插件/);
 assert.equal(foreign.config.participantId,'');
 console.log('BRIDGE_CARDS_OK adopts card by name+mark with get verification; foreign same-name card rejected without overwrite');
})().catch(error=>{console.error(error);process.exitCode=1;});
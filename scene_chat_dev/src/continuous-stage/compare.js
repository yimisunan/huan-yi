'use strict';
(()=>{
const $=s=>document.querySelector(s), people=['沈知韫','苏婉青','徐念薇'];
const fresh=()=>({messages:[{speaker:'沈知韫',text:'志北，过来坐。今天怎么样？'}],sent:0,draft:''});
const states={a:fresh(),b:fresh(),c:fresh()};let mode=['a','b','c'].includes(location.hash.slice(1))?location.hash.slice(1):'a',generation=0,busy=false,portraitName=people[0];
const descriptions={a:'人物在场，短句沿书页逐条留下。',b:'同席的每个人，都在同一条聊天流里。',c:'把注意力留给眼前的人、刚说出的这一句。'};
function node(tag,cls,text){const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;}
function store(){try{localStorage.setItem('three-chat-demo-'+mode,JSON.stringify(states[mode]));}catch{$('#hint').textContent='当前浏览器不能保存演示记录';}}
function sizing(){document.documentElement.style.setProperty('--footer',Math.ceil($('footer').getBoundingClientRect().height)+'px');}
function active(name){document.querySelectorAll('[data-person]').forEach(n=>n.classList.toggle('active',n.dataset.person===name));document.querySelectorAll('.person-button').forEach(n=>n.setAttribute('aria-current',String(n.dataset.name===name)));}
function showPortrait(name,file='fullbody.png'){portraitName=name;$('#portraitName').textContent=name;$('#portrait').src='/assets/'+encodeURIComponent(name)+'/'+file;$('#portrait').alt=name+'原立绘';document.querySelectorAll('[data-file]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.file===file)));if(!$('#portraitDialog').open)$('#portraitDialog').showModal();}
for(const name of people){const b=node('button','person-button');b.dataset.name=name;b.setAttribute('aria-label','查看'+name+'立绘');const im=node('img');im.src='/assets/'+encodeURIComponent(name)+'/into.png';im.alt='';b.append(im,node('span','',name));b.onclick=()=>showPortrait(name);$('#people').append(b);}
function message(m){
 const kind=m.kind||'dialogue';
 const n=node('article','msg '+kind+(m.speaker==='徐志北'?' player':'')+(m.demo?' demo':''));
 n.setAttribute('aria-label',kind==='narration'?'旁白':(m.speaker||'人物')+(kind==='action'?'的动作':'的对白'));
 if(kind==='narration'){
  n.append(node('div','narration-mark','旁白'),node('div','text',m.text));
  return n;
 }
 if(people.includes(m.speaker)){
  const im=node('img','avatar');im.src='/assets/'+encodeURIComponent(m.speaker)+'/into.png';im.alt='';n.append(im);
 }
 const heading=node('div','message-heading');
 heading.append(node('div','name',m.speaker||'现场'));
 if(kind==='action')heading.append(node('span','kind-label','动作'));
 n.append(heading,node('div','text',m.text));
 return n;
}
function controls(){
 $('#send').disabled=busy;
 document.querySelectorAll('[data-say]').forEach(b=>b.disabled=busy);
 $('#playMix').disabled=busy||mode!=='b'||!!states.b.demoPlayed;
 $('#playMix').textContent=states.b.demoPlayed?'混合示例已加入':'播放混合示例';
}
function focusView(){const s=states[mode],last=s.messages.at(-1),lastUser=s.messages.findLast(m=>m.speaker==='徐志北'),focus=last.speaker||s.messages.findLast(m=>m.speaker)?.speaker||people[0];$('#currentMessage').replaceChildren(message(last));$('#lastPlayer').textContent=lastUser?'你刚才说：'+lastUser.text:'她先向你打了招呼。';active(last.speaker==='徐志北'?people[0]:focus);}
function demoEntry(kind,speaker,text){const e={kind,speaker,text,demo:true};return e;}
const mixExample=[
 demoEntry('narration',null,'雨声停了。桌上的茶还冒着热气，文件被压在杯垫旁。'),
 demoEntry('action','苏婉青','她把茶杯往你这边推了推，指尖在杯沿停了一下。'),
 demoEntry('dialogue','沈知韫','志北，先喝口茶。你想问什么，慢慢说。'),
 demoEntry('action','徐念薇','她抬眼看了看母亲，又把窗帘拉开一线。'),
 demoEntry('narration',null,'杯底落在桌面上，发出很轻的一声。雨后的风从窗缝里透进来。')
];
function render(){const s=states[mode];document.body.dataset.mode=mode;document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));$('#modeDescription').textContent=descriptions[mode];$('#heading').textContent=mode==='b'?'会客厅 · 同席':'雨停之前';$('#stream').hidden=mode==='c';$('#focus').hidden=mode!=='c';$('#messages').replaceChildren(...s.messages.map(message));$('#input').value=s.draft;$('#input').style.height='auto';$('#count').textContent=s.messages.length;$('#progress').textContent=s.sent?'已发送 '+s.sent+' 句 · 可继续接话':s.demoPlayed?'混合示例 · 可继续接话':'初始状态 · 尚未发送';controls();focusView();sizing();}
function latest(){const n=$('#stream');n.scrollTo({top:n.scrollHeight,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});$('#jump').hidden=true;}
function replies(text,s){if(/你们|大家|都在/.test(text))return[{kind:'action',speaker:'沈知韫',text:'她把文件合上，抬眼看向另外两人。'},{kind:'dialogue',speaker:'沈知韫',text:'我刚看完文件，正好歇一会儿。'},{kind:'action',speaker:'苏婉青',text:'她在茶壶里添了些热水，回头朝你笑了笑。'},{kind:'dialogue',speaker:'苏婉青',text:'我在泡茶。也给你倒一杯？'},{kind:'narration',speaker:null,text:'徐念薇没有马上回答，窗外的水珠沿着玻璃慢慢滑下去。'},{kind:'dialogue',speaker:'徐念薇',text:'我没什么事，你说。'}];if(/休息|累|歇/.test(text))return[{kind:'action',speaker:'沈知韫',text:'她向旁边挪了挪，给你留出位置。'},{kind:'dialogue',speaker:'沈知韫',text:'好，听你的。陪我坐一会儿？'}];if(/忙|今天/.test(text))return[{kind:'action',speaker:'沈知韫',text:'她把手边的文件翻到最后一页，才抬起头。'},{kind:'dialogue',speaker:'沈知韫',text:'刚忙完。你呢，今天还顺利吗？'}];if(/茶|喝|一杯/.test(text))return[{kind:'action',speaker:'苏婉青',text:'她拿起另一只杯子，拇指轻轻擦过杯口。'},{kind:'dialogue',speaker:'苏婉青',text:'好，稍等。还是和以前一样？'}];if(/顺利|还好|不错/.test(text))return[{kind:'narration',speaker:null,text:'她的目光在你脸上停了一会儿，像是在确认你是不是真的没事。'},{kind:'dialogue',speaker:'沈知韫',text:'那就好。刚进门怎么不说话？'}];if(/继承|遗嘱/.test(text))return[{kind:'action',speaker:'沈知韫',text:'她的手指在文件边缘停住，随后把文件合了起来。'},{kind:'dialogue',speaker:'沈知韫',text:'怎么忽然问这个？你听到了什么？'}];if(/哥哥|公司|亏损/.test(text))return[{kind:'narration',speaker:null,text:'会客厅里安静了一瞬。没有人替你把“听说”说成“事实”。'},{kind:'dialogue',speaker:'沈知韫',text:'先说说你听到了什么，别急着下结论。'}];return[{kind:'action',speaker:s.messages.filter(m=>m.speaker&&m.speaker!=='徐志北').at(-1)?.speaker||people[0],text:'她没有打断你，只把注意力留在这句话上。'},{kind:'dialogue',speaker:s.messages.filter(m=>m.speaker&&m.speaker!=='徐志北').at(-1)?.speaker||people[0],text:s.sent%2?'嗯，我听着。然后呢？':'你慢慢说，不着急。'}];}
async function playMix(){if(busy||mode!=='b')return;const s=states.b;if(s.demoPlayed)return;const token=++generation,stream=$('#stream'),follow=s.messages.length===1||stream.scrollHeight-stream.scrollTop-stream.clientHeight<90;s.demoPlayed=true;busy=true;render();for(const m of mixExample){const label=m.kind==='narration'?'现场旁白':m.kind==='action'?m.speaker+'的动作':m.speaker+'正在说话';$('#arrival').textContent=label+'……';await new Promise(r=>setTimeout(r,650));if(token!==generation)return;s.messages.push(m);$('#messages').append(message(m));if(m.speaker)active(m.speaker);$('#count').textContent=s.messages.length;if(follow)latest();else $('#jump').hidden=false;}busy=false;$('#arrival').textContent='混合示例播放完毕 · 演示条目不计入发送句数';store();render();}
async function send(text){if(busy)return;text=String(text||'').trim();if(!text)return;const s=states[mode],token=++generation,stream=$('#stream'),follow=s.messages.length===1||stream.scrollHeight-stream.scrollTop-stream.clientHeight<90;s.draft='';s.messages.push({kind:'dialogue',speaker:'徐志北',text});s.sent++;const answer=replies(text,s);busy=true;render();store();if(follow)latest();for(const m of answer){const label=m.kind==='narration'?'现场旁白':m.kind==='action'?m.speaker+'的动作':m.speaker+'正在接话';$('#arrival').textContent=label+'……';await new Promise(r=>setTimeout(r,750));if(token!==generation)return;s.messages.push(m);if(mode==='c')focusView();else $('#messages').append(message(m));if(m.speaker)active(m.speaker);$('#count').textContent=s.messages.length;store();if(follow)latest();else $('#jump').hidden=false;}busy=false;$('#arrival').textContent='';controls();$('#progress').textContent='已发送 '+s.sent+' 句 · 可继续接话';}
function switchMode(next){generation++;busy=false;mode=next;history.replaceState(null,'','#'+mode);$('#arrival').textContent='';$('#jump').hidden=true;render();$('#stream').scrollTop=0;}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>switchMode(b.dataset.mode));$('#reset').onclick=()=>{generation++;busy=false;states[mode]=fresh();$('#arrival').textContent='';$('#jump').hidden=true;store();render();$('#stream').scrollTop=0;};$('#playMix').onclick=playMix;
$('#form').onsubmit=e=>{e.preventDefault();send($('#input').value);};document.querySelectorAll('[data-say]').forEach(b=>b.onclick=()=>send(b.dataset.say));
$('#input').oninput=()=>{states[mode].draft=$('#input').value;$('#input').style.height='auto';$('#input').style.height=Math.min($('#input').scrollHeight,96)+'px';store();sizing();};$('#input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('#input').value);}};
function historyView(){const n=$('#historyList');n.replaceChildren(...states[mode].messages.map(message));$('#historyDialog').showModal();n.lastElementChild?.scrollIntoView({block:'end'});}
$('#history').onclick=historyView;$('#replayLast').onclick=historyView;$('#jump').onclick=latest;
$('#restore').onclick=()=>{if(busy)return;try{const s=JSON.parse(localStorage.getItem('three-chat-demo-'+mode));if(s&&Array.isArray(s.messages)&&s.messages.length&&Number.isInteger(s.sent)){states[mode]=s;render();latest();}else $('#arrival').textContent='这一版还没有保存的聊天记录。';}catch{$('#arrival').textContent='没有可恢复的记录。';}};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());document.querySelectorAll('[data-file]').forEach(b=>b.onclick=()=>showPortrait(portraitName,b.dataset.file));
new ResizeObserver(sizing).observe($('footer'));window.addEventListener('resize',sizing);if(window.visualViewport)window.visualViewport.addEventListener('resize',()=>{document.documentElement.style.setProperty('--inset',Math.max(0,innerHeight-visualViewport.height-visualViewport.offsetTop)+'px');sizing();});
render();
})();
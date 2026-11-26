/* Persistent history; only a recent page is rendered on opening a chat. */
let chatId = newChatUUID();
let historyReady = false, historyBusy = false, olderAvailable = false, nextSeq = 1;
let listOffset = 0, listMore = false, listRequest = 0;
let chatRevision=null,viewRevision=null,listRevision=null,remotePending=false,liveVersion=null;
let syncStarted=false;
const chatList = document.querySelector('.chat-list');
function updateChatListFade(){
  chatList.toggleAttribute('data-fade-bottom',chatList.scrollHeight-chatList.clientHeight-chatList.scrollTop>2);
}
chatList.addEventListener('scroll',updateChatListFade,{passive:true});
new ResizeObserver(updateChatListFade).observe(chatList);
new MutationObserver(updateChatListFade).observe(chatList,{childList:true});

const moreChats = document.querySelector('.more-chats');
const newChatButton = document.querySelector('.new-chat');
const historyNote = document.querySelector('.history-note');
const olderButton = document.createElement('button');
olderButton.type = 'button';
olderButton.className = 'older-messages';
olderButton.textContent = 'Load earlier messages';

async function archiveRequest(path, data) {
  const r = await fetch('/api/chats'+path, data === undefined ? {cache:'no-store'} : {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)
  });
  if(!r.headers.get('content-type')?.includes('application/json')) throw Error('Chat history unavailable. Reconnecting…');
  const body=await r.json();
  if(!r.ok)throw Error(body.error||'Chat history unavailable');
  return body;
}
function canSwitch(){return historyReady&&!busy&&!historyBusy&&!document.body.classList.contains('voice-active');}
function historyControls(){
  newChatButton.disabled=!canSwitch();
  for(const b of chatList.querySelectorAll('button'))b.disabled=!canSwitch();
  olderButton.disabled=historyBusy||busy;
}
function markSelected(){
  for(const b of chatList.querySelectorAll('.chat-open'))b.classList.toggle('active',b.dataset.chat===chatId);
}
async function refreshChats(append=false){
  const request=++listRequest;
  if(!append)listOffset=0;
  try{
    const data=await archiveRequest('?offset='+listOffset);
    if(request!==listRequest)return;
    if(!append)chatList.replaceChildren();
    for(const chat of data.chats){
      const row=document.createElement('div');row.className='chat-entry';
      const open=document.createElement('button');open.type='button';open.className='chat-open';open.dataset.chat=chat.id;
      open.textContent=chat.title;open.title=chat.title;open.onclick=()=>openChat(chat.id);
      const options=document.createElement('button');options.type='button';options.className='chat-options';
      options.textContent='…';options.title='Chat options';options.setAttribute('aria-label','Options for '+chat.title);
      options.onclick=()=>showChatOptions(row,chat);
      row.append(open,options);chatList.append(row);
    }
    listOffset+=data.chats.length;listMore=data.more;moreChats.hidden=!listMore;
    markSelected();historyControls();historyNote.textContent='';
    return true;
  }catch(e){historyNote.textContent='Chat history unavailable. Reconnecting…';return false;}
}
function dismissChatMenus(){
  for(const menu of chatList.querySelectorAll('.chat-menu'))menu.remove();
}
document.addEventListener('pointerdown',e=>{
  if(!e.target.closest('.chat-menu,.chat-options'))dismissChatMenus();
},true);
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&chatList.querySelector('.chat-menu')){
    const toggle=chatList.querySelector('.chat-menu').closest('.chat-entry').querySelector('.chat-options');
    dismissChatMenus();
    toggle?.focus();
    e.preventDefault();
    e.stopPropagation();
  }
},true);
function confirmChatDeletion(){
  const dialog=document.querySelector('.delete-chat-dialog');
  if(dialog.open)return Promise.resolve(false);
  dialog.returnValue='cancel';
  return new Promise(resolve=>{
    dialog.addEventListener('close',()=>resolve(dialog.returnValue==='delete'),{once:true});
    dialog.showModal();
  });
}
function showChatOptions(row,chat){
  if(!canSwitch())return;
  const existing=row.querySelector('.chat-menu');
  for(const m of chatList.querySelectorAll('.chat-menu'))m.remove();
  if(existing)return;
  const menu=document.createElement('div');menu.className='chat-menu';
  const rename=document.createElement('button');rename.type='button';rename.textContent='Rename';
  const remove=document.createElement('button');remove.type='button';remove.textContent='Delete';
  rename.onclick=()=>{menu.remove();beginChatRename(row,chat);};
  remove.onclick=async()=>{menu.remove();if(!await confirmChatDeletion()||!canSwitch())return;try{await archiveRequest('/delete',{chat:chat.id});if(chat.id===chatId)resetChat();await refreshChats();}catch(e){historyNote.textContent=e.message;}};
  menu.append(rename,remove);row.append(menu);
}
function beginChatRename(row,chat){
  if(!canSwitch()||row.querySelector('.chat-rename'))return;
  for(const other of chatList.querySelectorAll('.chat-rename'))other.cancelRename?.();
  const open=row.querySelector('.chat-open'), options=row.querySelector('.chat-options');
  const editor=document.createElement('form');editor.className='chat-rename';
  const field=document.createElement('input');field.type='text';field.value=chat.title;field.maxLength=100;
  field.setAttribute('aria-label','Chat name');field.autocomplete='off';
  const save=document.createElement('button');save.type='submit';save.textContent='✓';save.title='Save name';save.setAttribute('aria-label','Save name');
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='×';cancel.title='Cancel';cancel.setAttribute('aria-label','Cancel rename');
  let saving=false;
  function close(){
    editor.remove();open.hidden=false;options.hidden=false;options.focus();
  }
  editor.cancelRename=()=>{if(!saving)close();};
  cancel.onclick=editor.cancelRename;
  field.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();editor.cancelRename();}});
  editor.onsubmit=async e=>{
    e.preventDefault();
    const title=field.value.trim();
    if(!title||saving||!canSwitch())return;
    if(title===chat.title){close();return;}
    saving=true;field.readOnly=true;save.disabled=true;cancel.disabled=true;
    try{
      await archiveRequest('/rename',{chat:chat.id,title});
      chat.title=title;open.textContent=title;open.title=title;
      options.setAttribute('aria-label','Options for '+title);
      historyNote.textContent='';close();
    }catch(error){
      historyNote.textContent=error.message;saving=false;field.readOnly=false;save.disabled=false;cancel.disabled=false;field.focus();
    }
  };
  editor.append(field,save,cancel);open.hidden=true;options.hidden=true;row.append(editor);
  field.focus();field.select();
}
function rememberChat(){try{localStorage.setItem('quantru.activeChat',chatId);}catch(_){}}
function resetChat(){
  cancelEdit();cancelFollow();turns.length=0;messages.replaceChildren();
  selectedFiles=[];input.value='';renderAttachments();form.classList.remove('expanded');
  chatId=newChatUUID();nextSeq=1;olderAvailable=false;followLatest=true;
  chatRevision=viewRevision=liveVersion=null;remotePending=false;
  try{localStorage.removeItem('quantru.activeChat');}catch(_){}
  historyNote.textContent='';markSelected();update();
}
function mediaURL(turn,index){return '/api/chats/media?chat='+encodeURIComponent(chatId)+'&seq='+turn.seq+'&index='+index;}
function showSavedImage(url,name){
  if(viewerURL)URL.revokeObjectURL(viewerURL);
  viewerURL=null;viewerImage.src=url;viewerImage.alt=name;if(!viewer.open)viewer.showModal();
}
function appendGeneratedImage(reply,chat,seq,before=null){
  const url='/api/chats/generated-image?chat='+encodeURIComponent(chat)+'&seq='+seq;
  const image=document.createElement('img');
  image.className='generated-image';image.src=url;image.loading='lazy';
  image.alt='Generated image';image.tabIndex=0;image.setAttribute('role','button');
  image.onclick=()=>showSavedImage(url,'Generated image');
  image.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();image.click();}};
  const download=document.createElement('a');download.className='generated-download';
  download.href=url;download.download='quantru-image.png';download.textContent='Download';
  const container=document.createElement('div');container.className='generated-result';
  container.append(image,download);reply.insertBefore(container,before);return container;
}
// Each inference round owns its own thought block.
function appendThoughtBlock(reply,before=null,active=false){
  const details=document.createElement('details');details.className='thinking';details.open=active;
  const summary=document.createElement('summary');summary.textContent=active?'Thinking…':'Thought process';
  const trace=document.createElement('div');trace.className='thinking-text';
  let text='',following=true,finished=!active;
  const nearBottom=()=>trace.scrollHeight-trace.clientHeight-trace.scrollTop<=24;
  trace.addEventListener('scroll',()=>{if(trace.clientHeight>0)following=nearBottom();},{passive:true});
  trace.addEventListener('wheel',e=>{if(e.deltaY<0&&trace.scrollHeight>trace.clientHeight)following=false;},{passive:true});
  function paint(final=false){
    if(!details.open)return;
    renderMarkdown(trace,text,final,()=>{if(following&&details.open)trace.scrollTop=trace.scrollHeight;scheduleFollow();});
  }
  details.addEventListener('toggle',()=>{if(details.open)paint(true);scheduleFollow();});
  details.append(summary,trace);reply.insertBefore(details,before);
  return {details,setText(value,final=false){if(value!==text||final){text=value;paint(final);}},
    finish(collapse=true){if(!finished){finished=true;summary.textContent='Thought process';paint(true);if(collapse)details.open=false;}}};
}
function splitThoughts(text,boundaries){
  const chars=Array.from(text||'');
  let offset=0,after=0;
  const parts=[];
  for(const boundary of boundaries||[]){
    if(!Number.isInteger(boundary.offset)||boundary.offset<offset||boundary.offset>chars.length||!Number.isInteger(boundary.after)||boundary.after<=after)continue;
    if(boundary.offset>offset)parts.push({after,text:chars.slice(offset,boundary.offset).join('')});
    offset=boundary.offset;after=boundary.after;
  }
  if(offset<chars.length)parts.push({after,text:chars.slice(offset).join('')});
  return parts;
}
function appendViewedImage(reply,record,before,seq){
  const box=document.createElement('section');box.className='shell-run viewed-image-run';
  const header=document.createElement('div');header.className='shell-run-header';
  const title=document.createElement('span');title.textContent='View image';
  const state=document.createElement('span');state.className='shell-run-status';
  header.append(title,state);
  const path=document.createElement('div');path.className='shell-run-cwd';path.textContent=record.command||'';
  const output=document.createElement('div');output.className='shell-run-output';output.textContent=record.output||'';output.hidden=!output.textContent;
  const image=document.createElement('img');image.className='viewed-image';image.hidden=true;image.loading='lazy';image.alt='Viewed image';image.tabIndex=0;image.setAttribute('role','button');
  const unavailable=document.createElement('div');unavailable.className='viewed-image-unavailable';unavailable.textContent='Original image unavailable or changed.';unavailable.hidden=true;
  const url='/api/chats/viewed-image?chat='+encodeURIComponent(chatId)+'&seq='+seq+'&idx='+record.idx;
  image.onload=()=>{if(box.dataset.status==='complete'){image.hidden=false;unavailable.hidden=true;scheduleFollow();}};
  image.onerror=()=>{image.hidden=true;if(box.dataset.status==='complete'){unavailable.hidden=false;scheduleFollow();}};
  image.onclick=()=>showSavedImage(url,record.command||'Viewed image');
  image.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();image.click();}};
  box.append(header,path,output,image,unavailable);reply.insertBefore(box,before);
  let requested=false;
  const block={box,output,running:true,appendOutput(text){output.textContent+=text;output.hidden=!output.textContent;},finish(status){
    block.running=status==='running';box.dataset.status=status;
    state.textContent=status==='running'?'Viewing…':status==='complete'?'Viewed':status==='stopped'?'Stopped':status==='interrupted'?'Interrupted':'Failed';
    if(status==='complete'){
      if(!requested){requested=true;image.hidden=false;image.src=url;}
    }else{image.hidden=true;unavailable.hidden=true;}
  }};
  block.finish(record.status||'running');return block;
}
function appendShellRun(reply,record,before=null,seq=null){
  if(record.kind==='view_image')return appendViewedImage(reply,record,before,seq);
  const box=document.createElement('section');box.className='shell-run';
  const header=document.createElement('div');header.className='shell-run-header';
  const title=document.createElement('span');title.textContent='Terminal';
  const state=document.createElement('span');state.className='shell-run-status';
  const copy=document.createElement('button');copy.type='button';copy.textContent='Copy';copy.title='Copy terminal command';
  copy.onclick=()=>copyToClipboard(command.textContent).catch(()=>{});
  header.append(title,state,copy);
  const cwd=document.createElement('div');cwd.className='shell-run-cwd';cwd.textContent=record.cwd||'';cwd.hidden=!record.cwd;
  const command=document.createElement('pre');command.className='shell-run-command';command.textContent=record.command;
  const output=document.createElement('pre');output.className='shell-run-output';output.textContent=record.output||'';output.hidden=!output.textContent;
  box.append(header,cwd,command,output);reply.insertBefore(box,before);
  const block={running:true,box,output,setCommand(text){command.textContent=text||'';},start(record){block.setCommand(record.command);cwd.textContent=record.cwd||'';cwd.hidden=!record.cwd;block.finish('running',null);},appendOutput(text){
    const follow=output.scrollHeight-output.clientHeight-output.scrollTop<=24;
    output.hidden=false;output.append(document.createTextNode(text));if(follow)output.scrollTop=output.scrollHeight;
  },finish(status,code){
    block.running=status==='running'||status==='writing';
    copy.disabled=status==='writing';
    box.dataset.status=status;
    state.textContent=status==='writing'?'Writing command…':status==='running'?'Running…':status==='complete'?'Exit '+(code??0):status==='stopped'?'Stopped':status==='interrupted'?'Interrupted':code==null?'Failed':'Exit '+code;
  }};
  block.finish(record.status||'running',record.exit_code);
  return block;
}
// Shared chronological renderer for the local stream, remote snapshots and archive.
function legacyTimeline(record){
  const result=[],runs=record.shell_runs||[];
  const parts=splitThoughts(record.thinking,record.thinking_boundaries);
  let id=0,offset=0,pi=0;
  function thought(part){
    const end=offset+Array.from(part.text).length;
    result.push({id:++id,kind:'thinking',start:offset,end});offset=end;
  }
  for(const run of runs){
    while(pi<parts.length&&parts[pi].after<run.idx)thought(parts[pi++]);
    result.push({id:++id,kind:'tool',idx:run.idx});
  }
  while(pi<parts.length)thought(parts[pi++]);
  let text=record.answer||'';
  if(record.generated_image){
    const marker=text.lastIndexOf('[Generated image: ');
    if(marker>=0)text=text.slice(0,marker).trimEnd();
  }
  if(text)result.push({id:++id,kind:'text',start:0,end:Array.from(text).length});
  if(record.generated_image)result.push({id:++id,kind:'generated_image'});
  return result;
}
function initResponseTimeline(turn){
  const anchor=document.createElement('div');anchor.hidden=true;
  turn.reply.replaceChildren(anchor);turn.responseAnchor=anchor;
  turn.responseBlocks=new Map();
}
function renderResponseTimeline(turn,record,pending=false){
  if(!turn.responseAnchor)initResponseTimeline(turn);
  const reply=turn.reply,anchor=turn.responseAnchor,blocks=turn.responseBlocks;
  const steps=[...(Array.isArray(record.timeline)?record.timeline:legacyTimeline(record))];
  if(pending)for(const id of Object.keys(record.shell_drafts||{}))steps.push({id:'draft:'+id,kind:'draft',draft_id:id});
  const answers=Array.from(record.answer||''),thoughts=Array.from(record.thinking||'');
  const runs=new Map((record.shell_runs||[]).map(r=>[r.idx,r]));
  const drafts=record.shell_drafts||{};
  const ordered=[],seen=new Set();
  const active=pending?steps.at(-1)?.id:null;
  function obtain(id,kind,create){
    let block=blocks.get(id);
    if(block&&block.kind!==kind){block.box.remove();blocks.delete(id);block=null;}
    if(!block){block=create();block.kind=kind;blocks.set(id,block);}
    seen.add(id);ordered.push(block.box);return block;
  }
  function note(id,kind,text){
    const block=obtain(id,kind,()=>{const box=document.createElement('div');box.className='generation-stopped';reply.insertBefore(box,anchor);return {box};});
    if(block.box.textContent!==text)block.box.textContent=text;
  }
  for(const item of steps){
    const id=item.id;
    if(item.kind==='thinking'||item.kind==='text'){
      const thinking=item.kind==='thinking';
      const value=(thinking?thoughts:answers).slice(item.start,item.end).join('');
      const running=active===id;
      const block=obtain(id,item.kind,()=>{
        if(thinking){const thought=appendThoughtBlock(reply,anchor,running);return {box:thought.details,thought};}
        const box=document.createElement('div');reply.insertBefore(box,anchor);return {box};
      });
      if(thinking){
        if(block.value!==value||block.running!==running)block.thought.setText(value,!running);
        if(block.running&&!running)block.thought.finish();
      }else if(block.value!==value||block.running!==running)renderMarkdown(block.box,value,!running,scheduleFollow);
      block.value=value;block.running=running;
    }else if(item.kind==='tool'||item.kind==='draft'||item.kind==='unfinished'){
      const r=item.kind==='tool'?runs.get(item.idx):item.kind==='draft'?drafts[item.draft_id]:item;
      if(!r)continue;
      const status=item.kind==='draft'?'writing':r.status;
      const block=obtain(id,item.kind,()=>appendShellRun(reply,{...r,status},anchor,turn.seq));
      if(item.kind!=='tool')block.setCommand?.(r.command);
      if(block.output.textContent!==(r.output||'')){
        const text=r.output||'';
        if(text.startsWith(block.output.textContent))block.appendOutput(text.slice(block.output.textContent.length));
        else{block.output.textContent=text;block.output.hidden=!text;}
      }
      block.finish(status,r.exit_code);
    }else if(item.kind==='generated_image'){
      obtain(id,item.kind,()=>({box:appendGeneratedImage(reply,chatId,turn.seq,anchor)}));
    }else if(item.kind==='error'){
      note(id,'error',item.message||'Generation failed');
    }
  }
  if(!pending&&record.status==='stopped')note('stopped','stopped','Generation stopped');
  if(!pending&&record.status==='error'&&!steps.some(s=>s.kind==='error'))note('error','error',record.error||'Generation failed');
  if(pending&&!ordered.length)note('pending','pending','…');
  for(const [id,block] of blocks)if(!seen.has(id)){block.box.remove();blocks.delete(id);}
  let before=anchor;
  for(let i=ordered.length-1;i>=0;i--){
    const box=ordered[i];if(box.nextSibling!==before)reply.insertBefore(box,before);before=box;
  }
  scheduleFollow();
}
// Client state follows server-authored timeline metadata. Text and tool payloads
// remain separate so the timeline never duplicates their contents.
function applyResponseChunk(record,chunk){
  const delta=chunk.choices?.[0]?.delta||{};
  record.thinking+=(delta.reasoning_content||'');
  if(chunk.answer_break)record.answer+='\n\n';
  record.answer+=(delta.content||'');
  if(chunk.image_generated){
    record.generated_image=true;
    record.answer+=(record.answer?'\n\n':'')+'[Generated image: '+(chunk.image_prompt||'')+']';
  }
  const e=chunk.shell_event;
  if(e){
    if(e.type==='writing')record.shell_drafts[e.draft_id]={draft_id:e.draft_id,command:e.command,status:'writing'};
    else if(e.type==='start'){
      delete record.shell_drafts[e.draft_id];
      record.shell_runs.push({...e,status:'running',output:'',exit_code:null});
    }else{
      const r=record.shell_runs.find(r=>r.idx===e.idx);
      if(r){if(e.type==='output')r.output+=e.text||'';else if(e.type==='end'){r.status=e.status;r.exit_code=e.exit_code;}}
    }
  }
  if(Array.isArray(chunk.timeline))record.timeline=chunk.timeline;
  if(chunk.generation_stats)record.generation_stats=chunk.generation_stats;
}
function finishResponseRecord(record,state,error){
  record.status=state;
  for(const r of record.shell_runs)if(r.status==='running')r.status=state==='stopped'?'stopped':'error';
  for(const draft of Object.values(record.shell_drafts||{})){
    const id=Math.max(0,...record.timeline.map(t=>Number(t.id)||0))+1;
    const errorIndex=record.timeline.findIndex(t=>t.kind==='error');
    record.timeline.splice(errorIndex<0?record.timeline.length:errorIndex,0,{id,kind:'unfinished',command:draft.command||'',status:state==='stopped'?'stopped':'error'});
  }
  record.shell_drafts={};
  if(error&&!record.timeline?.some(t=>t.kind==='error'))record.error=error;
}
function restoreTurn(record){
  const turn={...record,files:[],savedFiles:record.files,content:null,saved:true,recordKey:JSON.stringify(record)};
  const user=bubble('user','');turn.userBubble=user;
  const text=document.createElement('div');text.className='user-text';text.textContent=turn.text;turn.userText=text;user.append(text);
  for(const [i,f] of turn.savedFiles.entries()){
    if(f.type.startsWith('image/')){
      const img=document.createElement('img');const url=mediaURL(turn,i);
      img.className='message-image';img.src=url;img.loading='lazy';img.alt=f.name;img.tabIndex=0;img.setAttribute('role','button');
      img.onclick=()=>showSavedImage(url,f.name);
      img.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showSavedImage(url,f.name);}};
      user.append(img);
    }else{const label=document.createElement('div');label.className='message-file';label.textContent=f.name;user.append(label);}
  }
  turn.userActions=actionBar(turn,'user');
  const reply=bubble('assistant','');turn.reply=reply;
  initResponseTimeline(turn);
  renderResponseTimeline(turn,turn,turn.status==='pending');
  if(turn.status==='pending')reply.classList.add('streaming');
  turn.replyActions=actionBar(turn,'assistant');
  return turn;
}
function olderControl(){
  olderButton.remove();
  if(olderAvailable)messages.prepend(olderButton);
}
async function openChat(id,initial=false){
  if(!initial&&!canSwitch())return;
  if(!initial&&(input.value.trim()||selectedFiles.length)&&!confirm('Discard the current unsent draft?'))return;
  historyBusy=true;historyControls();update();
  try{
    const data=await archiveRequest('/page?chat='+encodeURIComponent(id));
    resetChat();chatId=id;rememberChat();followLatest=false;
    chatRevision=viewRevision=data.revision;remotePending=data.turns.some(t=>t.status==='pending');
    for(const record of data.turns)turns.push(restoreTurn(record));
    nextSeq=(turns.at(-1)?.seq||0)+1;olderAvailable=data.more;olderControl();
    historyNote.textContent='';markSelected();followLatest=true;scheduleFollow();
    if(!initial){
      const toggle=document.querySelector('.quantru-logo');
      if(toggle.getAttribute('aria-expanded')==='true')toggle.click();
    }
  }catch(e){
    if(initial&&e.message==='Chat not found')resetChat();
    else historyNote.textContent=e.message;
  }
  finally{historyBusy=false;historyControls();update();}
}
async function loadOlder(){
  if(!olderAvailable||!turns.length||busy||historyBusy)return;
  historyBusy=true;historyControls();followLatest=false;cancelFollow();
  const oldTop=chatScroll.scrollTop, first=turns[0].userBubble, oldPosition=first.getBoundingClientRect().top;
  try{
    const data=await archiveRequest('/page?chat='+encodeURIComponent(chatId)+'&before='+turns[0].seq);
    const restored=data.turns.map(restoreTurn);
    for(const t of restored)for(const node of [t.userBubble,t.userActions,t.reply,t.replyActions])messages.insertBefore(node,first);
    turns.unshift(...restored);olderAvailable=data.more;olderControl();
    chatScroll.scrollTop=oldTop+first.getBoundingClientRect().top-oldPosition;followLatest=false;
  }catch(e){historyNote.textContent=e.message;}
  finally{historyBusy=false;historyControls();update();}
}
olderButton.onclick=loadOlder;
messagesObserverPlaceholder();
function messagesObserverPlaceholder(){/* scroll listener installed after composer initializes */}
newChatButton.onclick=()=>{
  if(!canSwitch()||((input.value.trim()||selectedFiles.length)&&!confirm('Discard the current unsent draft?')))return;
  resetChat();
  const toggle=document.querySelector('.quantru-logo');
  if(toggle.getAttribute('aria-expanded')==='true')toggle.click();
  input.focus();
};
moreChats.onclick=()=>refreshChats(true);
async function initHistory(){
  window.addEventListener('scroll',()=>{if(chatScroll.scrollTop<80&&olderAvailable&&!historyBusy&&!busy)loadOlder();},{passive:true});
  while(!(await refreshChats())) await new Promise(resolve=>setTimeout(resolve,1500));
  let id=null;try{id=localStorage.getItem('quantru.activeChat');}catch(_){}
  if(id)await openChat(id,true);
  historyReady=true;update();
  if(!syncStarted){syncStarted=true;syncTick();}
}
async function saveStart(turn){
  const mode=turn.saved?'replace':'append';
  if(!turn.seq)turn.seq=nextSeq;
  turn.generationId=newChatUUID();
  const media=turn.savedFiles||turn.files.map(f=>({name:f.name,type:f.type}));
  const saved=await archiveRequest('/begin',{chat:chatId,seq:turn.seq,text:turn.text,content:turn.content,files:media,mode,expected_revision:chatRevision,generation_id:turn.generationId});
  chatRevision=saved.revision;
  turn.saved=true;turn.savedFiles=media;nextSeq=turn.seq+1;rememberChat();refreshChats();
}
async function saveFinish(turn,thinking,state,error){
  if(!turn.saved)return;
  const saved=await archiveRequest('/finish',{chat:chatId,seq:turn.seq,answer:turn.answer,thinking,status:state,error,generation_id:turn.generationId});
  chatRevision=saved.revision;
  if(saved.pending)remotePending=true;
  turn.thinking=thinking;turn.status=state;
  // File payloads now live in SQLite, not the active JS history.
  turn.content=null;turn.files=[];
  refreshChats();
}
async function restoredContent(turn){
  if(!turn.saved)return null;
  const data=await archiveRequest('/content?chat='+encodeURIComponent(chatId)+'&seq='+turn.seq);
  if(typeof data.content==='string')return turn.text;
  return [...(turn.text?[{type:'text',text:turn.text}]:[]),...data.content.filter(p=>p.type!=='text')];
}

// Synchronize persisted messages and stream snapshots without replacing drafts.
async function syncPage(id){
  const oldFirst=turns[0]?.seq;
  let data=await archiveRequest('/page?chat='+encodeURIComponent(id)), records=data.turns;
  let more=data.more;
  while(more&&records.length&&oldFirst&&records[0].seq>oldFirst){
    const page=await archiveRequest('/page?chat='+encodeURIComponent(id)+'&before='+records[0].seq);
    if(page.revision!==data.revision)return false;
    records=page.turns.concat(records);more=page.more;
  }
  if(id!==chatId||busy||editing)return false;
  const following=followLatest&&nearBottom();
  const oldTop=chatScroll.scrollTop;
  const anchor=turns.find(t=>t.userBubble.getBoundingClientRect().bottom>0);
  const anchorTop=anchor?.userBubble.getBoundingClientRect().top;
  cancelFollow();followLatest=false;
  const old=new Map(turns.map(t=>[t.seq,t]));
  const next=[];
  for(const record of records){
    let turn=old.get(record.seq);
    if(turn&&turn.recordKey!==JSON.stringify(record)){
      for(const n of [turn.userBubble,turn.userActions,turn.reply,turn.replyActions])n?.remove();
      old.delete(record.seq);turn=null;
    }
    if(!turn)turn=restoreTurn(record);
    old.delete(record.seq);next.push(turn);
  }
  for(const t of old.values())for(const n of [t.userBubble,t.userActions,t.reply,t.replyActions])n?.remove();
  for(const t of next)for(const n of [t.userBubble,t.userActions,t.reply,t.replyActions])messages.append(n);
  turns.splice(0,turns.length,...next);
  nextSeq=(turns.at(-1)?.seq||0)+1;olderAvailable=more;olderControl();
  chatRevision=viewRevision=data.revision;liveVersion=null;
  const sameAnchor=anchor&&turns.find(t=>t.seq===anchor.seq);
  followLatest=following;
  if(following)scheduleFollow();
  else if(sameAnchor)chatScroll.scrollTop=oldTop+sameAnchor.userBubble.getBoundingClientRect().top-anchorTop;
  else chatScroll.scrollTop=oldTop;
  return true;
}
function showRemoteLive(live){
  if(!live)return;
  const version=live.seq+':'+live.version;
  if(liveVersion===version)return;
  const turn=turns.find(t=>t.seq===live.seq);
  if(!turn||turn.status!=='pending')return;
  liveVersion=version;
  if(live.generation_stats){turn.generation_stats=live.generation_stats;updateTokenStats(turn);}
  if(!turn.hasLiveTimeline){initResponseTimeline(turn);turn.hasLiveTimeline=true;}
  turn.answer=live.answer;turn.thinking=live.thinking;
  const pending=!live.done&&!live.failed;
  if(pending)renderResponseTimeline(turn,live,true);
  else{const final={...live,timeline:[...(live.timeline||[])],shell_runs:(live.shell_runs||[]).map(r=>({...r}))};finishResponseRecord(final,live.failed?'error':'complete');renderResponseTimeline(turn,final,false);}

}
async function syncTick(){
  try{
    if(!historyReady||historyBusy||busy||editing)return;
    const id=chatId;
    const state=await archiveRequest('/sync?chat='+encodeURIComponent(id));
    if(id!==chatId||busy||historyBusy||editing)return;
    const pending=Boolean(state.pending||state.live);
    const changed=remotePending!==pending;
    remotePending=pending;
    if(changed)update();
    if(state.list_revision!==listRevision&&!chatList.querySelector('.chat-rename,.chat-menu')){
      const top=chatList.scrollTop;
      if(await refreshChats()){listRevision=state.list_revision;chatList.scrollTop=top;}
    }
    if(id!==chatId||busy||historyBusy||editing)return;
    if(state.revision!==viewRevision){
      if(state.revision===null){
        if(chatRevision!==null){
          const draft=input.value,attachments=selectedFiles.slice();
          resetChat();input.value=draft;selectedFiles=attachments;renderAttachments();update();
          historyNote.textContent='Conversation deleted on another device.';
        }
        return;
      }
      historyBusy=true;update();
      try{if(!await syncPage(id))return;}finally{historyBusy=false;update();}
    }
    if(id===chatId&&state.live)showRemoteLive(state.live);
  }catch(_){}
  finally{setTimeout(syncTick,850);}
}

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
function appendGeneratedImage(reply,chat,seq){
  if(reply.querySelector('.generated-image'))return;
  const url='/api/chats/generated-image?chat='+encodeURIComponent(chat)+'&seq='+seq;
  const image=document.createElement('img');
  image.className='generated-image';image.src=url;image.loading='lazy';
  image.alt='Generated image';image.tabIndex=0;image.setAttribute('role','button');
  image.onclick=()=>showSavedImage(url,'Generated image');
  image.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();image.click();}};
  const download=document.createElement('a');download.className='generated-download';
  download.href=url;download.download='quantru-image.png';download.textContent='Download';
  const container=document.createElement('div');container.className='generated-result';
  container.append(image,download);reply.append(container);
}
function appendShellRun(reply,record,before=null){
  const box=document.createElement('section');box.className='shell-run';
  const header=document.createElement('div');header.className='shell-run-header';
  const title=document.createElement('span');title.textContent='Terminal';
  const state=document.createElement('span');state.className='shell-run-status';
  const copy=document.createElement('button');copy.type='button';copy.textContent='Copy';copy.title='Copy terminal command';
  copy.onclick=()=>copyToClipboard(record.command).catch(()=>{});
  header.append(title,state,copy);
  const cwd=document.createElement('div');cwd.className='shell-run-cwd';cwd.textContent=record.cwd;
  const command=document.createElement('pre');command.className='shell-run-command';command.textContent=record.command;
  const output=document.createElement('pre');output.className='shell-run-output';output.textContent=record.output||'';output.hidden=!output.textContent;
  box.append(header,cwd,command,output);reply.insertBefore(box,before);
  const block={running:true,output,appendOutput(text){
    const follow=output.scrollHeight-output.clientHeight-output.scrollTop<=24;
    output.hidden=false;output.append(document.createTextNode(text));if(follow)output.scrollTop=output.scrollHeight;
  },finish(status,code){
    block.running=status==='running';
    box.dataset.status=status;
    state.textContent=status==='running'?'Running…':status==='complete'?'Exit '+(code??0):status==='stopped'?'Stopped':status==='interrupted'?'Interrupted':code==null?'Failed':'Exit '+code;
  }};
  block.finish(record.status||'running',record.exit_code);
  return block;
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
  if(turn.thinking||turn.status==='pending'){
    const details=document.createElement('details');details.className='thinking';
    const summary=document.createElement('summary');summary.textContent='Thought process';
    const trace=document.createElement('div');trace.className='thinking-text';
    details.append(summary,trace);reply.append(details);
    turn.remoteThoughts=details;turn.remoteTrace=trace;details.hidden=!turn.thinking;
    details.addEventListener('toggle',()=>{if(details.open)renderMarkdown(trace,turn.thinking,true);});
  }
  turn.remoteShells=new Map();
  for(const run of turn.shell_runs||[])turn.remoteShells.set(run.idx,appendShellRun(reply,run));
  if(turn.generated_image)appendGeneratedImage(reply,chatId,turn.seq);
  else if(turn.answer||turn.status==='pending'){
    const output=document.createElement('div');reply.append(output);turn.remoteOutput=output;
    if(turn.answer)renderMarkdown(output,turn.answer,true);else output.textContent='…';
  }
  if(turn.status==='pending')reply.classList.add('streaming');
  if(turn.status!=='complete'&&turn.status!=='pending'){const note=document.createElement('div');note.className='generation-stopped';note.textContent=turn.status==='error'?'Generation failed':'Generation stopped';reply.append(note);}
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
async function saveFinish(turn,thinking,state){
  if(!turn.saved)return;
  const saved=await archiveRequest('/finish',{chat:chatId,seq:turn.seq,answer:turn.answer,thinking,status:state,generation_id:turn.generationId});
  chatRevision=saved.revision;
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
  if(turn.remoteOutput){
    if(turn.answer!==live.answer){
      turn.answer=live.answer;
      renderMarkdown(turn.remoteOutput,live.generated_image?live.answer.replace(/\[Generated image: [^\]]*\]$/,''):live.answer,false,scheduleFollow);
    }else if(live.thinking&&!live.answer)turn.remoteOutput.textContent='';
  }
  if(turn.remoteThoughts&&turn.thinking!==live.thinking){
    turn.thinking=live.thinking;turn.remoteThoughts.hidden=!live.thinking;
    if(turn.remoteThoughts.open)renderMarkdown(turn.remoteTrace,live.thinking,false,scheduleFollow);
  }
  for(const run of live.shell_runs||[]){
    let block=turn.remoteShells.get(run.idx);
    if(!block){
      block=appendShellRun(turn.reply,run,turn.remoteOutput||null);turn.remoteShells.set(run.idx,block);
    }else if(block.output.textContent!==run.output){
      if(run.output.startsWith(block.output.textContent))block.appendOutput(run.output.slice(block.output.textContent.length));
      else{block.output.textContent=run.output;block.output.hidden=!run.output;}
    }
    block.finish(run.status,run.exit_code);
  }
  if(live.generated_image)appendGeneratedImage(turn.reply,chatId,turn.seq);
  scheduleFollow();
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

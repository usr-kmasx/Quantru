const form = document.querySelector('.composer');
const input = form.querySelector('textarea');
const send = form.querySelector('.send');
const sendIcon = send.innerHTML;
const stopIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"/></svg>';
let activeRequest = null;
let activeShellId = null;
function cancelShellRequest(){
  if(activeShellId)fetch('/api/shell/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:activeShellId}),keepalive:true}).catch(()=>{});
}
window.addEventListener('pagehide',cancelShellRequest);
function stopGeneration() {
  if (!activeRequest || activeRequest.signal.aborted) return;
  cancelShellRequest();
  activeRequest.abort();
  update();
}
const files = document.querySelector('#files');
const attachments = document.querySelector('.attachments');
let selectedFiles = [];
const viewer = document.querySelector('.image-viewer');
const viewerImage = viewer.querySelector('img');
let viewerURL = null;
function openPreview(file) {
  if (viewerURL) URL.revokeObjectURL(viewerURL);
  viewerURL = URL.createObjectURL(file);
  viewerImage.src = viewerURL;
  viewerImage.alt = file.name;
  if (!viewer.open) viewer.showModal();
}
viewer.querySelector('.viewer-close').onclick = () => viewer.close();
viewer.addEventListener('click', e => { if (e.target === viewer) viewer.close(); });
viewer.addEventListener('close', () => {
  viewerImage.removeAttribute('src');
  if (viewerURL) URL.revokeObjectURL(viewerURL);
  viewerURL = null;
});
function renderAttachments() {
  for (const img of attachments.querySelectorAll('img[data-preview-url]')) {
    URL.revokeObjectURL(img.dataset.previewUrl);
  }
  attachments.replaceChildren();
  selectedFiles.forEach((file, i) => {
    const item = document.createElement('div');
    item.className = 'attachment-preview' + (file.type.startsWith('image/') ? ' image-preview' : '');
    item.title = file.name;
    if (file.type.startsWith('image/')) {
      const img = document.createElement('img');
      const url = URL.createObjectURL(file);
      img.src = url;
      img.dataset.previewUrl = url;
      img.alt = file.name;
      img.tabIndex = 0;
      img.setAttribute('role','button');
      img.setAttribute('aria-label','View ' + file.name);
      img.onclick = () => openPreview(file);
      img.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPreview(file); } };
      item.append(img);
    } else {
      const name = document.createElement('span');
      name.textContent = file.name;
      item.append(name);
    }
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'attachment-remove';
    remove.textContent = '×';
    remove.title = 'Remove attachment';
    remove.setAttribute('aria-label', 'Remove ' + file.name);
    remove.onclick = () => { selectedFiles.splice(i, 1); renderAttachments(); update(); };
    item.append(remove);
    attachments.append(item);
  });
}
function readFile(file) {
  return new Promise((resolve,reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
const documentExt=/\.(pdf|docx|xlsx|txt|md|markdown|csv|tsv|json|xml|yaml|yml|toml|ini|cfg|conf|log|rst|py|js|ts|jsx|tsx|html|css|c|h|cpp|hpp|rs|go|java|kt|sh|bash|zsh|fish|sql|rb|php|lua|swift|cs|vue|svelte|cmake|dockerfile)$/i;
function isDocument(file){return documentExt.test(file.name)||/^(makefile|dockerfile|cmakelists\.txt|readme|license)$/i.test(file.name);}
async function mediaPart(file) {
  const url = await readFile(file);
  if (file.type.startsWith('image/')) return {type:'image_url',image_url:{url}};
  if(isDocument(file))return {type:'document',name:file.name,data:url.split(',')[1]};
  const format = ({'audio/mpeg':'mp3','audio/mp4':'m4a','audio/x-wav':'wav'})[file.type] || file.name.split('.').pop().toLowerCase();
  return {type:'input_audio',input_audio:{data:url.split(',')[1],format}};
}
const reasoningControl=form.querySelector('.reasoning-control');
const reasoningToggle=reasoningControl.querySelector('.reasoning-toggle');
const reasoningMenu=reasoningControl.querySelector('.reasoning-menu');
let reasoningCaps={native:[],supported:null,unlimited_default:true,model:null};
let reasoningLevel='default';
let reasoningModel=null;
try{reasoningLevel=sessionStorage.getItem('quantru.reasoning')||'default';reasoningModel=sessionStorage.getItem('quantru.reasoningModel');}catch(_){}
const reasoningLabels={off:'Off',minimal:'Minimal',low:'Low',medium:'Medium',high:'High',xhigh:'Extra High',max:'Max'};
const reasoningBudgets={low:'512 tokens',medium:'2,048 tokens',high:'8,192 tokens',max:'32,768 tokens'};
function reasoningOptions(){return ['default','off',...(reasoningCaps.native.length?reasoningCaps.native:['low','medium','high','max'])];}
function reasoningLabel(level){return level==='default'?(reasoningCaps.unlimited_default?'Unlimited':'Default'):reasoningLabels[level]||level;}
function closeReasoning(){reasoningMenu.hidden=true;reasoningToggle.setAttribute('aria-expanded','false');}
function setReasoning(level){
  reasoningLevel=reasoningOptions().includes(level)?level:'default';
  try{sessionStorage.setItem('quantru.reasoning',reasoningLevel);if(reasoningModel)sessionStorage.setItem('quantru.reasoningModel',reasoningModel);}catch(_){}
  updateReasoning();closeReasoning();
}
function updateReasoning(){
  reasoningControl.hidden=reasoningCaps.supported===false;
  reasoningToggle.disabled=busy;
  reasoningToggle.classList.toggle('active',reasoningLevel!=='off'&&reasoningLevel!=='default');
  reasoningToggle.title='Reasoning: '+reasoningLabel(reasoningLevel);
  reasoningToggle.setAttribute('aria-label',reasoningToggle.title);
  if(busy||reasoningControl.hidden)closeReasoning();
}
function renderReasoningMenu(){
  reasoningMenu.replaceChildren();
  for(const level of reasoningOptions()){
    const item=document.createElement('button');item.type='button';item.setAttribute('role','menuitemradio');
    item.setAttribute('aria-checked',String(level===reasoningLevel));
    const label=document.createElement('span');label.textContent=reasoningLabel(level);
    item.append(label);
    if(!reasoningCaps.native.length&&reasoningBudgets[level]){const hint=document.createElement('small');hint.textContent=reasoningBudgets[level];item.append(hint);}
    const check=document.createElement('span');check.className='reasoning-check';check.textContent='✓';check.setAttribute('aria-hidden','true');item.append(check);
    item.onclick=()=>{setReasoning(level);reasoningToggle.focus();};
    reasoningMenu.append(item);
  }
}
reasoningToggle.onclick=()=>{if(!reasoningMenu.hidden){closeReasoning();return;}renderReasoningMenu();reasoningMenu.hidden=false;reasoningToggle.setAttribute('aria-expanded','true');};
document.addEventListener('pointerdown',e=>{if(!reasoningControl.contains(e.target))closeReasoning();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!reasoningMenu.hidden){closeReasoning();reasoningToggle.focus();e.stopPropagation();}});
async function refreshReasoning(){
  try{
    const r=await fetch('/api/reasoning',{cache:'no-store'});if(!r.ok)return;
    const c=await r.json();
    const changed=JSON.stringify(c)!==JSON.stringify(reasoningCaps);
    if(reasoningModel&&reasoningModel!==c.model)reasoningLevel='default';
    reasoningModel=c.model;reasoningCaps=c;
    if(!reasoningOptions().includes(reasoningLevel))reasoningLevel='default';
    if(changed){try{sessionStorage.setItem('quantru.reasoning',reasoningLevel);sessionStorage.setItem('quantru.reasoningModel',reasoningModel);}catch(_){}if(!reasoningMenu.hidden)renderReasoningMenu();}
    updateReasoning();
  }catch(_){}
}
function update() {
  const expanded = form.classList.contains('expanded');
  // Measure in the compact layout, never in the multiline layout whose
  // minimum height would otherwise keep the composer permanently expanded.
  input.style.height = 'auto';
  if (!expanded) form.classList.remove('multiline');
  const style = getComputedStyle(input);
  const lineHeight = parseFloat(style.lineHeight) || 24;
  const padding = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
  const multi = expanded || input.scrollHeight > lineHeight + padding + 2;
  form.classList.toggle('multiline', multi);
  input.style.height = Math.min(input.scrollHeight, expanded ? window.innerHeight * .65 : 240) + 'px';
  const stopping = busy && activeRequest?.signal.aborted;
  const mode = busy ? 'stop' : 'send';
  if (send.dataset.mode !== mode) {
    send.dataset.mode = mode;
    send.innerHTML = busy ? stopIcon : sendIcon;
    send.title = busy ? 'Stop generating' : 'Send';
    send.setAttribute('aria-label', send.title);
  }
  send.disabled = busy ? !!stopping : ((!input.value.trim() && !selectedFiles.length) || !ready || !historyReady || historyBusy || remotePending || document.body.classList.contains('voice-active'));
  updateActions();
  historyControls();
  updateImageHint();
  updateShellHint();
  updateReasoning();
}
const imageHint=document.createElement('button');
imageHint.type='button';imageHint.className='image-tool-hint';imageHint.hidden=true;
imageHint.textContent='@image — Generate image';
form.before(imageHint);
const imageChip=document.createElement('span');
imageChip.className='image-tool-chip';imageChip.hidden=true;
const imageLabel=document.createElement('span');imageLabel.textContent='@image';
const imageRemove=document.createElement('button');imageRemove.type='button';
imageRemove.textContent='×';imageRemove.title='Disable image tool';
imageRemove.setAttribute('aria-label','Disable image tool');
imageChip.append(imageLabel,imageRemove);form.insertBefore(imageChip,input);
let imageToolAvailable=false,imageToolEnabled=false;
const imageTag=/(^|\s)@\s*image(?=\s|$)/ig;
const imagePartial=/(?:^|\s)@(?:\s*i(?:m(?:a(?:g(?:e)?)?)?)?)?$/i;
try{imageToolEnabled=sessionStorage.getItem('quantru.imageTool')==='1';}catch(_){}
function setImageTool(enabled){
  imageToolEnabled=!!enabled;
  if(enabled){shellEnabled=false;try{sessionStorage.setItem('quantru.shellTool','0');}catch(_){}}
  try{sessionStorage.setItem('quantru.imageTool',enabled?'1':'0');}catch(_){}
  updateImageHint();
}
function consumeImageTag(){
  if(!imageToolAvailable||busy)return;
  const text=input.value.replace(imageTag,'$1');
  if(text!==input.value){
    input.value=text.replace(/^ +/,'');
    setImageTool(true);
  }
}
function updateImageHint(){
  imageChip.hidden=!imageToolAvailable||!imageToolEnabled;
  imageRemove.disabled=busy;
  imageHint.hidden=!imageToolAvailable||busy||imageToolEnabled||!imagePartial.test(input.value);
}
imageRemove.onclick=()=>{setImageTool(false);input.focus();update();};
imageHint.onclick=()=>{
  input.value=input.value.replace(imagePartial,'').trimEnd();
  setImageTool(true);input.focus();update();
};
let imageStatusRequest=0;
async function refreshImageTool(){
  const request=++imageStatusRequest;
  try{
    const response=await fetch('/api/image/status',{cache:'no-store'});
    if(!response.ok)return;
    const data=await response.json();
    if(request!==imageStatusRequest)return;
    imageToolAvailable=!!data.available;
    if(imageToolAvailable)consumeImageTag();
    else if(!busy&&imageToolEnabled)setImageTool(false);
    update();
  }catch(_){}
}
refreshImageTool();
setInterval(refreshImageTool,5000);
// Shell permission is explicit and applies only to the next submitted request.
const shellHint=document.createElement('button');
shellHint.type='button';shellHint.className='image-tool-hint';shellHint.hidden=true;
shellHint.textContent='@shell — Local terminal access';
form.before(shellHint);
const shellChip=document.createElement('span');shellChip.className='image-tool-chip shell-tool-chip';shellChip.hidden=true;
const shellLabel=document.createElement('span');shellLabel.textContent='@shell';
const shellRemove=document.createElement('button');shellRemove.type='button';shellRemove.textContent='×';
shellRemove.title='Disable terminal access';shellRemove.setAttribute('aria-label',shellRemove.title);
shellChip.append(shellLabel,shellRemove);form.insertBefore(shellChip,input);
let shellEnabled=false;
try{shellEnabled=sessionStorage.getItem('quantru.shellTool')==='1';}catch(_){}
if(shellEnabled){imageToolEnabled=false;try{sessionStorage.setItem('quantru.imageTool','0');}catch(_){}}
const shellTag=/(^|\s)@\s*shell(?=\s|$)/ig;
const shellPartial=/(?:^|\s)@(?:\s*s(?:h(?:e(?:l(?:l)?)?)?)?)?$/i;
function setShellTool(enabled){
  shellEnabled=!!enabled;
  try{sessionStorage.setItem('quantru.shellTool',enabled?'1':'0');}catch(_){}
  if(enabled)setImageTool(false);
  updateShellHint();
}
function consumeShellTag(){
  if(busy)return;
  const text=input.value.replace(shellTag,'$1');
  if(text!==input.value){input.value=text.replace(/^ +/,'');setShellTool(true);}
}
function updateShellHint(){
  shellChip.hidden=!shellEnabled;
  shellRemove.disabled=busy;
  shellHint.hidden=busy||shellEnabled||!shellPartial.test(input.value);
}
shellRemove.onclick=()=>{setShellTool(false);input.focus();update();};
shellHint.onclick=()=>{
  input.value=input.value.replace(shellPartial,'').trimEnd();
  setShellTool(true);input.focus();update();
};
input.addEventListener('input',()=>{consumeImageTag();consumeShellTag();update();});
form.querySelector('.add').addEventListener('click', () => files.click());
files.addEventListener('change', () => {
  const accepted=Array.from(files.files).filter(f=>f.type.startsWith('image/')||f.type.startsWith('audio/')||/\.(wav|mp3|flac|ogg|m4a)$/i.test(f.name)||isDocument(f));
  for(const file of accepted){
    if(selectedFiles.length>=16|| (isDocument(file)&&file.size>20*1024*1024)||selectedFiles.reduce((n,f)=>n+f.size,0)+file.size>45*1024*1024){status.textContent='Attachment limit exceeded (20 MiB per document, 45 MiB total).';continue;}
    selectedFiles.push(file);
  }
  files.value = '';
  renderAttachments();
  update();
});
form.querySelector('.expand').addEventListener('click', () => {
  form.classList.toggle('expanded');
  update();
  input.focus();
});
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!busy && !send.disabled) form.requestSubmit();
  }
});
const messages = document.querySelector('.messages');
const chatScroll = document.scrollingElement;
let followLatest = true;
let followFrame = 0;
function nearBottom() {
  return chatScroll.scrollHeight - chatScroll.clientHeight - chatScroll.scrollTop <= 32;
}
function scheduleFollow() {
  if (!followLatest || followFrame) return;
  followFrame = requestAnimationFrame(() => {
    followFrame = 0;
    if (followLatest) chatScroll.scrollTop = chatScroll.scrollHeight;
  });
}
let lastChatTop=chatScroll.scrollTop;
function cancelFollow(){
  cancelAnimationFrame(followFrame);
  followFrame=0;
}
window.addEventListener('scroll', () => {
  const top=chatScroll.scrollTop;
  if(nearBottom())followLatest=true;
  else if(top<lastChatTop-1)followLatest=false;
  lastChatTop=top;
  if(!followLatest)cancelFollow();
}, {passive:true});
messages.addEventListener('pointerdown', () => {
  followLatest=false;
  cancelFollow();
}, {passive:true});
messages.addEventListener('wheel', e => {
  const inner = e.target.closest('.thinking-text, .code-block pre');
  if (inner && inner.scrollHeight > inner.clientHeight) return;
  if (e.deltaY < 0 && chatScroll.scrollHeight > chatScroll.clientHeight) {
    followLatest = false;
    cancelFollow();
  }
}, {passive:true});

const status = document.querySelector('.status');
const turns = [];
let editing = null;
const actionIcons = {
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  edit: '<path d="m14 6 4 4M4 20l4.5-1 11-11a2.8 2.8 0 0 0-4-4l-11 11z"/>',
  retry: '<path d="M20 11a8 8 0 1 0-2 6M20 4v7h-7"/>'
};
function actionButton(kind, title, callback) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'message-action action-' + kind;
  button.title = title;
  button.setAttribute('aria-label', title);
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">'+actionIcons[kind]+'</svg>';
  button.onclick = callback;
  return button;
}
async function copyMessage(button, value) {
  try {
    await copyToClipboard(value);
    button.classList.add('copied');
    button.title = 'Copied';
    setTimeout(() => {button.classList.remove('copied');button.title='Copy message';}, 1200);
  } catch (_) { button.title = 'Copy failed'; }
}
function updateTokenStats(turn){
  const label=turn.statsLabel;
  if(!label)return;
  const stats=turn.generation_stats;
  const running=turn.metricsRunning||turn.status==='pending';
  label.hidden=!stats;
  if(!stats){label.textContent='';label.title='';return;}
  // The first decode sample can have an unusually small elapsed time.
  // Wait for a useful sample without changing the measured cumulative rate.
  const now=performance.now();
  if(turn.firstMetricsAt==null)turn.firstMetricsAt=now;
  const enoughSamples=stats.tokens>=8&&Number(stats.decode_ms)>=3000&&now-turn.firstMetricsAt>=3000;
  const hasContext=Number.isInteger(stats.context_used)&&stats.context_used>=0&&Number.isInteger(stats.context_limit)&&stats.context_limit>0;
  const context=hasContext?' · '+Math.min(100,Math.floor(100*stats.context_used/stats.context_limit))+'% context':'';
  label.title=hasContext?stats.context_used.toLocaleString('en-US')+' / '+stats.context_limit.toLocaleString('en-US')+' context tokens':'';

  if(running&&!enoughSamples){
    label.textContent=stats.tokens.toLocaleString('en-US')+' tokens'+context;
    return;
  }
  if(running&&turn.lastMetricsPaint!=null&&now-turn.lastMetricsPaint<1000)return;
  turn.lastMetricsPaint=now;
  const average=Number(stats.average).toFixed(2);
  label.textContent=average+' tok/s · '+stats.tokens.toLocaleString('en-US')+' tokens'+context;
}
function actionBar(turn, role) {
  const bar = document.createElement('div');
  bar.className = 'message-actions ' + role + '-actions';
  const copy = actionButton('copy','Copy message', () => copyMessage(copy, role === 'user' ? turn.text : turn.answer));
  if (role === 'user') {
    bar.append(copy, actionButton('edit','Edit and resend', () => beginEdit(turn)));
  } else {
    copy.disabled = !turn.answer;
    bar.append(copy, actionButton('retry','Regenerate response', () => retryTurn(turn)));
    const stats=document.createElement('span');
    stats.className='generation-metrics';
    stats.title='Model decoding speed, including reasoning and tool tokens; excludes prompt processing.';
    stats.hidden=true;
    turn.statsLabel=stats;
    bar.append(stats);
    updateTokenStats(turn);
  }
  messages.append(bar);
  return bar;
}
function updateActions() {
  for (const button of messages.querySelectorAll('.action-edit,.action-retry')) button.disabled = busy || remotePending || !ready || historyBusy || !historyReady || document.body.classList.contains('voice-active');
}
function beginEdit(turn) {
  if (busy || remotePending || !ready || historyBusy || document.body.classList.contains('voice-active')) return;
  if (editing?.turn === turn) { editing.field.focus(); return; }
  cancelEdit();
  const bubble = turn.userBubble;
  const original = turn.userText;
  const editor = document.createElement('div');
  editor.className = 'inline-editor';
  const field = document.createElement('textarea');
  field.className = 'inline-edit-field';
  field.value = turn.text;
  field.rows = 1;
  field.setAttribute('aria-label','Edit message');
  const controls = document.createElement('div');
  controls.className = 'inline-edit-actions';
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.textContent = 'Cancel';
  const save = document.createElement('button');
  save.type = 'button';
  save.className = 'inline-edit-save';
  save.textContent = 'Send';
  function resize() {
    field.style.height = '0px';
    field.style.height = Math.max(32,Math.min(field.scrollHeight,240)) + 'px';
    save.disabled = !field.value.trim() && !(turn.files.length || turn.savedFiles?.length);
  }
  controls.append(cancel,save);
  editor.append(field,controls);
  original.hidden = true;
  bubble.classList.add('editing');
  bubble.prepend(editor);
  turn.userActions.hidden = true;
  editing = {turn,editor,field};
  cancel.onclick = () => cancelEdit();
  save.onclick = () => submitEdit();
  field.addEventListener('input',resize);
  field.addEventListener('keydown',e => {
    if(e.key === 'Escape') {e.preventDefault();cancelEdit();}
    if(e.key === 'Enter' && !e.shiftKey && !e.isComposing) {e.preventDefault();if(!save.disabled)submitEdit();}
  });
  resize();
  field.focus();
  field.setSelectionRange(field.value.length,field.value.length);
}
function cancelEdit() {
  if (!editing) return;
  const {turn,editor} = editing;
  editing = null;
  editor.remove();
  turn.userText.hidden = false;
  turn.userBubble.classList.remove('editing');
  turn.userActions.hidden = false;
}
async function submitEdit() {
  if (!editing || busy || remotePending || !ready || historyBusy) return;
  const {turn,field} = editing;
  const text = field.value.trim();
  if ((!text && !(turn.files.length || turn.savedFiles?.length)) || !confirmReplace(turn)) return;
  cancelEdit();
  truncateAfter(turn);
  turn.reply?.remove();
  turn.replyActions?.remove();
  turn.text = text;
  turn.userText.textContent = text;
  turn.content = null;
  turn.answer = '';
  await generate(turn,false);
}
function confirmReplace(turn) {
  const index = turns.indexOf(turn);
  return index >= 0 && (index === turns.length - 1 || window.confirm('This will replace the later messages in this conversation. Continue?'));
}
function truncateAfter(turn, include = false) {
  const index = turns.indexOf(turn);
  const removed = turns.splice(index + (include ? 0 : 1));
  for (const t of removed) {
    for (const node of [t.userBubble,t.userActions,t.reply,t.replyActions]) node?.remove();
  }
}
async function retryTurn(turn) {
  if (busy || remotePending || !ready || historyBusy || document.body.classList.contains('voice-active') || !confirmReplace(turn)) return;
  cancelEdit();
  truncateAfter(turn);
  turn.reply?.remove();
  turn.replyActions?.remove();
  turn.answer = '';
  await generate(turn, false);
}
let busy = false;
let ready = false;
let modelSleeping = false;
let modelUnconfigured = false;
let modelFilesMissing = false;
let serverInUse = false;
function bubble(role, value) {
  const node = document.createElement('div');
  node.className = 'message ' + role;
  node.textContent = value;
  messages.append(node);
  scheduleFollow();
  return node;
}
// Local voice status owns the notice while recording or transcribing.
let healthTimer=null, healthInFlight=false, healthRevision=0, healthRefreshPending=false;
function renderIdleStatus(){
  if(busy)return; // The active generation owns its own status.
  status.textContent=document.body.classList.contains('voice-active')||healthRefreshPending?''
    :remotePending?'Generation in progress…'
    :serverInUse?'Quantru is busy…'
    :modelUnconfigured?(modelFilesMissing?'Model files unavailable. Update their paths in llama.cpp settings.':'Choose a chat model in llama.cpp settings.')
    :ready?'':'Loading model…';
}
function refreshHealthAfterVoice(){
  healthRevision++;
  healthRefreshPending=true;
  clearTimeout(healthTimer);
  renderIdleStatus();
  if(!healthInFlight)health();
}
async function health() {
  if(healthInFlight)return;
  healthInFlight=true;
  const revision=healthRevision;
  let nextReady=false,nextSleeping=false,nextUnconfigured=false,nextMissing=false,nextInUse=false;
  try {
    const response = await fetch('/api/health', {cache:'no-store'});
    const healthData=await response.json().catch(()=>({}));
    nextUnconfigured = response.ok && healthData.configured === false;
    nextMissing = Array.isArray(healthData.missing_model_files)&&healthData.missing_model_files.length>0;
    nextReady = response.ok && !nextUnconfigured;
    nextSleeping = nextReady && healthData.status === 'sleeping';
    nextInUse=healthData.status==='busy';
    // Compatibility with an older server during a running image request.
    if(!nextReady&&!healthData.status&&!mobileClient){
      const imageState=await fetch('/api/image/settings',{cache:'no-store'}).then(r=>r.json()).catch(()=>({}));
      nextInUse=imageState.loading===true;
    }
  } catch (_) { nextReady=false;nextSleeping=false;nextUnconfigured=false;nextMissing=false;nextInUse=false; }
  finally {
    healthInFlight=false;
    if(revision!==healthRevision){
      // Discard a response started before local voice processing ended.
      healthTimer=setTimeout(health,0);
    }else{
      ready=nextReady;modelSleeping=nextSleeping;modelUnconfigured=nextUnconfigured;
      modelFilesMissing=nextMissing;serverInUse=nextInUse;healthRefreshPending=false;
      healthTimer=setTimeout(health,1500);
      renderIdleStatus();
      update();
      if(ready)refreshReasoning();
    }
  }
}
form.addEventListener('submit', async e => {
  e.preventDefault();
  if (busy) { if (e.submitter === send) stopGeneration(); return; }
  consumeImageTag();consumeShellTag();
  const text = input.value.trim();
  if ((!text && !selectedFiles.length) || !ready || !historyReady || historyBusy || remotePending || document.body.classList.contains('voice-active')) return;
  const turn = {text,files:selectedFiles.slice(),content:null,answer:''};
  cancelEdit();
  turns.push(turn);
  selectedFiles = [];
  input.value = '';
  renderAttachments();
  await generate(turn, true);
});
async function generate(turn, addUser) {
  followLatest = true;
  turn.generated_image=false;
  turn.generation_stats=null;
  turn.firstMetricsAt=null;
  turn.lastMetricsPaint=null;
  turn.metricsRunning=true;
  const allowShell=shellEnabled;
  const allowImageTool=!allowShell&&imageToolAvailable&&imageToolEnabled;
  busy = true;
  const request = new AbortController();
  activeRequest = request;
  activeShellId=allowShell?newChatUUID():null;
  status.textContent = modelSleeping ? 'Loading model…' : '';
  const text = turn.text;
  const pending = turn.files;
  if (addUser) {
  const userBubble = bubble('user','');
  turn.userBubble = userBubble;
  turn.userText = document.createElement('div');
  turn.userText.className = 'user-text';
  turn.userText.textContent = text;
  userBubble.append(turn.userText);
  for (const f of pending) {
    if (f.type.startsWith('image/')) {
      const img = document.createElement('img');
      const url = URL.createObjectURL(f);
      img.src = url;
      img.alt = f.name;
      img.className = 'message-image';
      img.tabIndex = 0;
      img.setAttribute('role','button');
      img.onclick = () => openPreview(f);
      img.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPreview(f); } };
      img.onload = () => URL.revokeObjectURL(url);
      img.onerror = () => URL.revokeObjectURL(url);
      userBubble.append(img);
    } else {
      const label = document.createElement('div');
      label.className = 'message-file';
      label.textContent = f.name;
      userBubble.append(label);
    }
  }
  turn.userActions = actionBar(turn,'user');
  }
  update();
  const reply = bubble('assistant','…');
  turn.reply = reply;
  reply.classList.add('streaming');
  let outcome='complete',persisted=false,sawDone=false;
  const record={answer:'',thinking:'',timeline:[],shell_runs:[],shell_drafts:{},status:'pending',generated_image:false};
  initResponseTimeline(turn);
  renderResponseTimeline(turn,record,true);
  turn.replyActions=actionBar(turn,'assistant');
  updateActions();
  try {
    if (turn.content === null) turn.content = turn.saved ? await restoredContent(turn) : pending.length ? [...(text ? [{type:'text',text}] : []), ...await Promise.all(pending.map(mediaPart))] : text;
    await saveStart(turn);
    persisted=true;
    request.signal.throwIfAborted();
    const r = await fetch('/v1/chat/completions',{
      method:'POST', signal:request.signal, headers:{'Content-Type':'application/json'},
      body:JSON.stringify({archive:{chat:chatId,seq:turn.seq},stream:true,generation_id:turn.generationId,image_tool:allowImageTool,shell_tool:allowShell,shell_request_id:activeShellId,reasoning_level:reasoningLevel})
    });
    if (!r.ok) throw new Error((await r.json()).error?.message || 'Request failed');
    status.textContent = '';
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value,{stream:true});
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]'){sawDone=true;continue;}
        const chunk=JSON.parse(data);
        applyResponseChunk(record,chunk);
        if(chunk.generation_stats){turn.generation_stats=chunk.generation_stats;updateTokenStats(turn);}
        if(chunk.shell_event){
          const event=chunk.shell_event;
          if(event.type==='writing')status.textContent='Writing command…';
          else if(event.type==='start')status.textContent=event.kind==='view_image'?'Viewing image…':event.kind==='view_all_images'?'Viewing images…':event.kind==='gallery_results'?'Reading gallery results…':'Running terminal command…';
          else if(event.type==='end')status.textContent='';
        }
        if(chunk.image_status)status.textContent=chunk.image_status;
        turn.generated_image=record.generated_image;
        renderResponseTimeline(turn,record,true);
        const error=chunk.shell_error||chunk.image_error||chunk.error;
        if(error)throw new Error(typeof error==='object'?(error.message||'Generation failed'):error);
      }
    }
    if(!sawDone)throw new Error('Model stream ended before completion.');
    finishResponseRecord(record,'complete');
    renderResponseTimeline(turn,record,false);
  }catch(error){
    outcome=request.signal.aborted?'stopped':'error';
    finishResponseRecord(record,outcome,error.message);
    renderResponseTimeline(turn,record,false);
  } finally {
    turn.answer=record.answer;turn.thinking=record.thinking;
    if(!persisted){
      if(addUser){input.value=[text,input.value].filter(Boolean).join('\n');selectedFiles=[...pending,...selectedFiles];renderAttachments();}
      viewRevision=null;
      for(const n of [turn.userBubble,turn.userActions,turn.reply,turn.replyActions])n?.remove();
      const index=turns.indexOf(turn);if(index>=0)turns.splice(index,1);
      historyNote.textContent='Message was not saved. Conversation will synchronize.';
    }
    if(persisted)try{await saveFinish(turn,record.thinking,outcome,record.error);}catch(e){historyNote.textContent='Could not save response: '+e.message;}
    const keepFollowing = followLatest && nearBottom();
    cancelFollow();
    status.textContent='';
    reply.classList.remove('streaming');
    turn.metricsRunning=false;
    if(persisted){turn.replyActions?.remove();turn.replyActions=actionBar(turn,'assistant');}
    activeRequest = null;
    activeShellId = null;
    busy = false;
    update();
    followLatest = keepFollowing;
    if(keepFollowing)scheduleFollow();
  }
}
health();
update();
initHistory();

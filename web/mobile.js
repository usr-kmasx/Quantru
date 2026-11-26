const mobileClient=!['localhost','127.0.0.1'].includes(location.hostname);
document.body.classList.toggle('mobile-client',mobileClient);
function newChatUUID(){
  if(crypto.randomUUID)return crypto.randomUUID();
  const b=crypto.getRandomValues(new Uint8Array(16));
  b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
  const h=Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');
  return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);
}
async function copyToClipboard(text){
  if(navigator.clipboard?.writeText)return navigator.clipboard.writeText(text);
  const t=document.createElement('textarea');t.value=text;t.style.cssText='position:fixed;left:-10000px;top:0';document.body.append(t);
  try{t.select();if(!document.execCommand('copy'))throw Error('Copy failed');}finally{t.remove();}
}
(()=>{
  if(mobileClient){
    const banner=document.createElement('div');
    banner.className='mobile-connection-note';banner.hidden=true;banner.setAttribute('role','status');
    document.body.append(banner);
    async function heartbeat(){
      try{
        const r=await fetch('/api/mobile/heartbeat',{cache:'no-store',signal:AbortSignal.timeout(3500)});
        banner.hidden=r.ok;
        if(!r.ok)banner.textContent=r.status===403?'Access revoked or expired. Scan a new QR code.':'Connection lost. Check the computer and Wi-Fi.';
      }catch(_){banner.hidden=false;banner.textContent='Connection lost. Check the computer and Wi-Fi.';}
      setTimeout(heartbeat,5000);
    }
    heartbeat();
    return;
  }
  const button=document.querySelector('#mobile-pair-open');
  const dialog=document.querySelector('.mobile-pair-dialog');
  const qr=dialog.querySelector('.mobile-pair-qr'), expiry=dialog.querySelector('.mobile-pair-expiry');
  const status=dialog.querySelector('.mobile-pair-status'),copy=dialog.querySelector('.mobile-pair-copy'),revoke=dialog.querySelector('.mobile-pair-revoke');
  const devices=dialog.querySelector('.mobile-devices');
  let url='',timer=null;
  async function refreshDevices(){
    try{
      const r=await fetch('/api/mobile/status',{cache:'no-store'});
      if(!r.ok)return;
      const data=await r.json();
      devices.replaceChildren();
      const heading=document.createElement('div');heading.className='mobile-devices-heading';heading.textContent='Paired devices';devices.append(heading);
      if(!data.devices.length){
        const empty=document.createElement('div');empty.className='mobile-device-empty';empty.textContent='No devices paired';devices.append(empty);
      }
      for(const d of data.devices){
        const row=document.createElement('div');row.className='mobile-device';
        const info=document.createElement('div');
        const name=document.createElement('strong');name.textContent=d.name;
        const ip=document.createElement('small');ip.textContent=d.ip;
        info.append(name,ip);
        const state=document.createElement('span');state.className='mobile-device-state';state.dataset.online=String(d.online);state.textContent=d.online?'Connected':'Offline';
        row.append(info,state);devices.append(row);
      }
      if(!data.active&&!qr.hidden){qr.hidden=true;copy.hidden=true;expiry.textContent='';revoke.disabled=true;status.textContent='Access expired or revoked. Reopen to generate a new QR code.';}
    }catch(_){}
  }
  async function api(path){
    const r=await fetch('/api/mobile/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await r.json();if(!r.ok)throw Error(data.error||'Pairing failed');return data;
  }
  button.onclick=async()=>{
    if(dialog.open)return;
    qr.hidden=true;copy.hidden=true;revoke.disabled=true;expiry.textContent='';status.textContent='Preparing QR code… Authorize local network access if prompted by your system.';dialog.showModal();
    refreshDevices();timer=setInterval(refreshDevices,2000);
    try{
      const data=await api('pair');url=data.url;qr.src=data.qr;qr.hidden=false;copy.hidden=false;revoke.disabled=false;
      expiry.textContent='Expires '+new Date(data.expires*1000).toLocaleString();status.textContent=data.firewall?.message||'';
    }catch(e){status.textContent=e.message;}
  };
  dialog.addEventListener('close',()=>{clearInterval(timer);timer=null;});
  dialog.querySelector('.llama-settings-close').onclick=()=>dialog.close();
  dialog.addEventListener('click',e=>{
    if(e.target!==dialog)return;
    const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();
  });
  copy.onclick=async()=>{try{await copyToClipboard(url);status.textContent='Link copied.';}catch(e){status.textContent=e.message;}};
  revoke.onclick=async()=>{
    revoke.disabled=true;
    try{await api('revoke');url='';qr.removeAttribute('src');qr.hidden=true;copy.hidden=true;expiry.textContent='';status.textContent='Access revoked. Reopen to create a new QR code.';refreshDevices();}catch(e){url='';qr.removeAttribute('src');qr.hidden=true;copy.hidden=true;expiry.textContent='';revoke.disabled=false;status.textContent=e.message;}
  };
})();

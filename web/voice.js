(() => {
  const mic=document.querySelector('.mic');
  const composer=document.querySelector('.composer');
  const input=composer.querySelector('textarea');
  const send=composer.querySelector('.send');
  const originalIcon=mic.innerHTML;
  const note=document.createElement('div');note.className='voice-status';note.hidden=true;note.setAttribute('role','status');composer.before(note);
  let supported=false, state='idle', id=null, context=null, stream=null, processor=null, queue=Promise.resolve(), timer=null, failure=null, stopping=false;
  const api=async(op,data={})=>{
    const r=await fetch('/api/voice/'+op,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const body=await r.json();
    if(!r.ok)throw Error(body.error||'Voice request failed');
    return body;
  };
  function setState(next,message=''){
    state=next;
    document.body.classList.toggle('voice-active',next!=='idle');
    if(typeof update==='function')update();
    mic.classList.toggle('recording',next==='recording');
    mic.innerHTML=next==='recording'?'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"/></svg>':originalIcon;
    mic.title=next==='recording'?'Stop recording':next==='idle'?'Dictate with microphone':'Processing voice…';
    mic.setAttribute('aria-label',mic.title);
    mic.disabled=!supported||next==='starting'||next==='processing';
    note.textContent=message;note.hidden=!message;
  }
  function release(){
    clearTimeout(timer);
    stream?.getTracks().forEach(t=>t.stop());
    if(context&&context.state!=='closed')context.close().catch(()=>{});
    stream=null;context=null;processor=null;
  }
  function encode(samples){
    const bytes=new Uint8Array(samples.buffer,samples.byteOffset,samples.byteLength);
    let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s);
  }
  async function abort(message){
    release();
    const token=id;id=null;
    if(token)try{await api('cancel',{id:token});}catch(_){}
    setState('idle',message);
  }
  async function start(){
    if(send.dataset.mode==='stop')return;
    setState('starting','Preparing microphone…');
    stopping=false;failure=null;queue=Promise.resolve();
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
      context=new AudioContext({sampleRate:48000});
      if(context.sampleRate!==48000)throw Error('48 kHz audio capture is unavailable.');
      await context.audioWorklet.addModule('/audio-worklet.js');
      await context.resume();
      const session=await api('start');id=session.id;
      processor=new AudioWorkletNode(context,'quantru-capture',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
      processor.port.onmessage=e=>{
        if(!e.data.pcm)return;
        const pcm=encode(e.data.pcm),token=id;
        queue=queue.then(async()=>{
          if(failure||!token)return;
          try{await api('push',{id:token,pcm});}
          catch(error){failure=error;if(!stopping)stop();}
        });
      };
      context.createMediaStreamSource(stream).connect(processor);
      processor.connect(context.destination);
      setState('recording','Recording…');
      timer=setTimeout(stop,59000);
    }catch(error){await abort(error.message);}
  }
  async function stop(){
    if(state!=='recording'||stopping)return;
    stopping=true;
    setState('processing','Isolating voice and transcribing…');
    try{
      if(processor){
        await new Promise(resolve=>{
          const original=processor.port.onmessage;
          const deadline=setTimeout(resolve,500);
          processor.port.onmessage=e=>{
            original(e);
            if(e.data.finished){clearTimeout(deadline);resolve();}
          };
          processor.port.postMessage('finish');
        });
      }
      release();
      await queue;
      if(failure)throw failure;
      const result=await api('finish',{id});
      id=null;
      if(result.text){
        input.value+=(input.value.trim()?' ':'')+result.text;
        input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
      }
      setState('idle',result.text?'':'No speech detected.');
    }catch(error){await abort(error.message);}
  }
  mic.onclick=()=>state==='recording'?stop():state==='idle'?start():null;
  window.addEventListener('pagehide',()=>{
    release();if(id)fetch('/api/voice/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id}),keepalive:true}).catch(()=>{});
  });
  fetch('/api/voice/status',{cache:'no-store'}).then(r=>r.json()).then(r=>{
    supported=r.available&&!!navigator.mediaDevices?.getUserMedia&&!!window.AudioWorkletNode;
    setState('idle');
  }).catch(()=>{});
})();

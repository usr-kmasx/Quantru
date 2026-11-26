(() => {
  const cache = ['f16','q8_0','q4_0','q4_1','q5_0','q5_1'];
  const llamaGroups = [
    ['General', [
      ['model','Model','text','Absolute path to a local GGUF model.'],
      ['mmproj','Multimodal projector','text','Optional GGUF projector. Leave empty for text only.'],
      ['context','Context length','number','Total context in tokens.',512,262144,1],
      ['thinking','Thinking','bool','Enable model reasoning when supported.'],
      ['max_tokens','Maximum output tokens','number','-1 = no explicit limit.',-1,262144,1],
      ['temperature','Temperature','number','Lower values make outputs more deterministic.',0,5,.05],
    ]],
    ['Speculative Decoding', [
      ['spec_method','Method','select','Accelerate generation using compatible predictions.',[
        ['none','Disabled'],['draft-mtp','MTP'],['draft-simple','Draft model'],['draft-eagle3','EAGLE-3'],
        ['draft-dflash','DFlash'],['draft-dflash2','DFlash2'],['draft-dspark','DSpark'],['draft-lilicorr','LiliCorr']]],
      ['draft_model','Draft model','text','Compatible auxiliary GGUF. Leave empty for integrated MTP.'],
      ['draft_tokens','Maximum draft tokens','number','Tokens predicted per drafting step.',1,128,1],
      ['draft_min','Minimum draft tokens','number','Minimum accepted draft length. 0 = no minimum.',0,128,1],
    ]],
    ['GPU & memory', [
      ['gpu_mode','GPU allocation','select','Prefer VRAM, with automatic RAM fallback.',[['vram-first','VRAM first'],['auto','Automatic fit']]],
      ['flash_attention','Flash Attention','select','Optimized attention implementation.',['on','auto','off']],
      ['cache_k','K cache type','select','Key cache precision.',cache],
      ['cache_v','V cache type','select','Value cache precision.',cache],
      ['gpu_margin','Free VRAM margin','number','MiB reserved when using automatic fit.',128,4096,64],
      ['mmproj_offload','Projector GPU offload','bool','Run the multimodal projector on the GPU.'],
      ['cache_prompt','Prompt cache','bool','Reuse matching prompt tokens.'],
    ]],
    ['Sampling', [
      ['top_k','Top K','number','Maximum candidate tokens. 0 = disabled.',0,262144,1],
      ['top_p','Top P','number','Cumulative probability threshold.',0,1,.01],
      ['min_p','Min P','number','Minimum relative token probability.',0,1,.01],
      ['repeat_penalty','Repetition penalty','number','1 = disabled.',.1,3,.05],
      ['presence_penalty','Presence penalty','number','Penalize previously used tokens.',-2,2,.05],
      ['frequency_penalty','Frequency penalty','number','Penalize frequent tokens.',-2,2,.05],
      ['seed','Seed','number','-1 = random seed.',-1,4294967295,1],
      ['reasoning_budget','Thinking budget','number','-1 = unrestricted. 0 = no thinking tokens.',-1,262144,1],
    ]],
    ['Performance', [
      ['batch','Batch size','number','Logical maximum prompt batch.',32,8192,32],
      ['ubatch','Micro batch size','number','Physical batch size.',32,8192,32],
      ['threads','CPU threads','number','Threads during generation.',1,64,1],
      ['threads_batch','Batch threads','number','Threads during prompt processing.',1,64,1],
    ]],
    ['Backend', [
      ['auto_update','Check for updates on startup','bool','Checks official llama.cpp releases in the background.'],
    ]]
  ];
  const imageGroups = [
    ['General', [
      ['diffusion','Diffusion model','text','Absolute path to the image generation model.'],
      ['encoder','Text encoder','text','Compatible language encoder model.'],
      ['llm_vision','LLM Vision (mmproj)','text','Optional projector for image editing. The installed Qwen Image 2.1 + Qwen3-VL pair uses its original mmproj automatically when empty.'],
      ['clip_vision','CLIP Vision','text','Optional compatible CLIP vision encoder for reference models that require it.'],
      ['vae','VAE','text','Compatible image encoder and decoder.'],
      ['resolution_presets','Resolution presets','presets','Quickly choose a common image size or restore the default.'],
      ['width','Width','number','Image width in pixels.',128,2048,16],
      ['height','Height','number','Image height in pixels.',128,2048,16],
    ]],
    ['LoRA', [
      ['loras','LoRA adapters','loras','Optional compatible LoRA files. Add an absolute path and set the strength.'],
      ['lora_apply_mode','Application mode','select','Auto selects the compatible mode for quantized weights.',[['auto','Auto'],['immediately','Immediately'],['at_runtime','At runtime']]],
    ]],
    ['Sampling', [
      ['steps','Steps','number','Number of denoising steps.',1,150,1],
      ['cfg','CFG scale','number','Classifier-free guidance scale.',0,30,.1],
      ['sampler','Sampler','select','Denoising sampling method.',['euler','euler_a','heun','dpm2','dpm++2s_a','dpm++2m','dpm++2mv2','ipndm','ipndm_v','lcm','ddim_trailing','tcd','res_multistep','res_2s','er_sde','euler_cfg_pp','euler_a_cfg_pp','euler_ge','dpm++2m_sde','dpm++2m_sde_bt','lms']],
      ['scheduler','Scheduler','select','Noise schedule.',['discrete','karras','exponential','ays','gits','sgm_uniform','simple','smoothstep','kl_optimal','lcm','bong_tangent','ltx2','logit_normal','flux2','flux','beta','llada_image']],
      ['seed','Seed','number','-1 = random seed.',-1,2147483647,1],
    ]],
    ['GPU & memory', [
      ['encoder_backend','Text encoder backend','select','Diffusion and VAE always use Vulkan.',[['cpu','CPU'],['vulkan0','Vulkan']]],
      ['weight_mode','Weight allocation','select','Keep weights in RAM or fit automatically.',[['offload','CPU offload'],['auto','Automatic fit']]],
      ['mmap','Memory mapping','bool','Map model weights from disk.'],
      ['vae_tiling','VAE tiling','bool','Decode image in tiles to reduce VRAM usage.'],
      ['vae_tile_size','VAE tile size','number','Tile width and height in pixels.',64,1024,16],
    ]],
    ['Performance', [
      ['threads','CPU threads','number','0 = automatic selection.',0,64,1],
      ['compatibility','Vulkan compatibility','bool','Limit and serialize submissions for older GPUs.'],
      ['auto_update','Check for updates on startup','bool','Downloads validated official Vulkan releases in the background.'],
    ]]
  ];
  function initialize(selector,formId,buttonId,endpoint,groups,isImage){
  const dialog=document.querySelector(selector);
  const form=dialog.querySelector(formId);
  const status=dialog.querySelector('.llama-settings-status');
  const apply=dialog.querySelector('.settings-apply');
  const reset=dialog.querySelector('.settings-reset');
  let info = null, controls = new Map(), applying = false;
  let loraList=null, loraAdd=null, resolutionPresetButtons=[];
  const resolutionPresets=[
    ['Default · 512×512',512,512],
    ['Square · 768×768',768,768],
    ['4:3 · 1024×768',1024,768],
    ['16:9 · 1024×576',1024,576],
    ['3:4 · 768×1024',768,1024],
    ['9:16 · 576×1024',576,1024],
  ];
  function syncResolutionPresets(){
    const width=controls.get('width')?.valueAsNumber;
    const height=controls.get('height')?.valueAsNumber;
    for(const item of resolutionPresetButtons){
      const active=width===item.width&&height===item.height;
      item.button.classList.toggle('active',active);
      item.button.setAttribute('aria-pressed',String(active));
    }
  }
  function pathControl(field,kind){
    const wrap=make('div','settings-path-control');
    const browse=make('button','settings-browse');
    browse.type='button';
    browse.dataset.kind=kind;
    browse.title='Browse model files';
    browse.setAttribute('aria-label','Browse model files');
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');
    svg.setAttribute('aria-hidden','true');
    const path=document.createElementNS(svg.namespaceURI,'path');
    path.setAttribute('d','M3 7V5a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z');
    svg.append(path);browse.append(svg);
    wrap.append(field,browse);return wrap;
  }
  function addLora(entry={path:'',strength:1,enabled:true}){
    const row=make('div','lora-entry');
    const line=make('div','lora-entry-actions');
    const path=make('input','settings-control lora-path');path.type='text';path.placeholder='/path/to/adapter.safetensors';path.value=entry.path;path.required=true;path.spellcheck=false;path.setAttribute('aria-label','LoRA path');
    const enabled=make('input','settings-switch');enabled.type='checkbox';enabled.checked=entry.enabled;enabled.setAttribute('aria-label','Enable LoRA');
    const strength=make('input','settings-control');strength.type='number';strength.min=-10;strength.max=10;strength.step='any';strength.required=true;strength.value=entry.strength;strength.setAttribute('aria-label','LoRA strength');
    const remove=make('button','lora-remove','Remove');remove.type='button';remove.onclick=()=>{row.remove();changed();};
    const power=make('label','lora-strength');power.append(make('span','','Strength'),strength);
    line.append(enabled,power,remove);row.append(pathControl(path,'lora'),line);loraList.append(row);
    row.readValue=()=>({path:path.value.trim(),strength:strength.valueAsNumber,enabled:enabled.checked});
  }
  function make(tag,cls,text) {
    const n=document.createElement(tag);
    if(cls)n.className=cls;
    if(text!==undefined)n.textContent=text;
    return n;
  }
  function build() {
    form.replaceChildren();
    controls.clear();loraList=null;loraAdd=null;resolutionPresetButtons=[];
    for(const [title,fields] of groups) {
      const section=make('section','settings-category');
      section.append(make('h3','',title));
      const list=make('div','settings-list');
      for(const [key,label,type,description,a,b,c] of fields) {
        if(type==='presets'){
          const row=make('div','settings-row resolution-presets');
          const text=make('div','settings-label');
          text.append(make('span','settings-name',label),make('small','settings-description',description));
          const buttons=make('div','resolution-preset-list');
          for(const [caption,width,height] of resolutionPresets){
            const button=make('button','resolution-preset',caption);
            button.type='button';button.disabled=true;button.setAttribute('aria-pressed','false');
            button.addEventListener('click',()=>{
              const widthField=controls.get('width'),heightField=controls.get('height');
              if(applying||!widthField||!heightField)return;
              widthField.value=width;heightField.value=height;
              syncResolutionPresets();changed();
            });
            resolutionPresetButtons.push({button,width,height});buttons.append(button);
          }
          row.append(text,buttons);list.append(row);continue;
        }
        if(type==='loras'){
          const row=make('div','settings-row settings-path lora-setting');
          const text=make('div','settings-label');
          text.append(make('span','settings-name',label),make('small','settings-description',description));
          loraList=make('div','lora-list');
          loraAdd=make('button','lora-add','+ Add LoRA');loraAdd.type='button';
          loraAdd.onclick=()=>{if(loraList.children.length<16){addLora();changed();}};
          row.append(text,loraList,loraAdd);list.append(row);continue;
        }
        const row=make(type==='text'?'div':'label','settings-row'+(type==='text'?' settings-path':''));
        const text=make('div','settings-label');
        text.append(make('span','settings-name',label),make('small','settings-description',description));
        const field=make(type==='select'?'select':'input','settings-control');
        field.name=key;
        if(type==='select'){
          for(const item of a){
            const [value,caption]=Array.isArray(item)?item:[item,item];
            const option=make('option','',caption);option.value=value;field.append(option);
          }
        } else if(type==='bool'){
          field.type='checkbox';field.classList.add('settings-switch');
        } else {
          field.type=type;
          if(type==='number'){field.min=a;field.max=b;field.step=c;}
          else {field.spellcheck=false;field.autocomplete='off';}
        }
        controls.set(key,field);
        if(type==='text'){
          field.setAttribute('aria-label',label);
          row.append(text,pathControl(field,isImage?'image':'gguf'));
        }else row.append(text,field);
        list.append(row);
      }
      section.append(list);form.append(section);
    }
  }
  function fill(config) {
    if(loraList){loraList.replaceChildren();for(const entry of config.loras||[])addLora(entry);}
    for(const [key,field] of controls) {
      if(field.type==='checkbox')field.checked=config[key];
      else field.value=config[key];
    }
    for(const item of resolutionPresetButtons)item.button.disabled=false;
    syncResolutionPresets();changed();
  }
  function values(){
    const out={};
    for(const [key,field] of controls){
      out[key]=field.type==='checkbox'?field.checked:field.type==='number'?field.valueAsNumber:field.value;
    }
    if(loraList)out.loras=Array.from(loraList.children,row=>row.readValue());
    return out;
  }
  function changed(){
    if(!info||applying){apply.disabled=true;return;}
    syncResolutionPresets();
    if(!isImage){
    const method=controls.get('spec_method').value;
    const active=method!=='none';
    for(const key of ['draft_model','draft_tokens','draft_min']){
      const field=controls.get(key);
      field.closest('.settings-row').hidden=!active;
      field.disabled=!active;
    }
    controls.get('draft_model').required=active&&method!=='draft-mtp';
    }else{
      const tile=controls.get('vae_tile_size');tile.disabled=!controls.get('vae_tiling').checked;tile.closest('.settings-row').hidden=tile.disabled;
    }
    if(loraAdd)loraAdd.disabled=loraList.children.length>=16;
    const current=values(), diff=Object.keys(current).filter(key=>JSON.stringify(current[key])!==JSON.stringify(info.config[key]));
    const reload=diff.some(key=>!info.runtime.includes(key));
    apply.disabled=!diff.length||!form.checkValidity()||info.loading;
    apply.textContent=reload?'Apply & reload':'Apply';
    status.textContent=diff.length?(reload?'Model will reload.':(isImage?'Applies to the next image.':'Applies to the next response.')):'';
  }
  async function load(){
    if(applying)return;
    status.textContent='Loading settings…'; apply.disabled=true; reset.disabled=true;
    try{
      const response=await fetch(endpoint,{cache:'no-store'});
      if(!response.ok)throw Error('Settings unavailable');
      info=await response.json();
      fill(info.config);reset.disabled=false;
    }catch(error){status.textContent=error.message;}
  }
  build();
  document.querySelector(buttonId).addEventListener('click',load);
  form.addEventListener('input',changed);
  reset.onclick=()=>{if(info&&!applying)fill(info.defaults);};
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(!info||applying||!form.checkValidity())return;
    applying=true;apply.disabled=true;reset.disabled=true;
    const candidate=values();
    status.textContent=apply.textContent.includes('reload')?'Reloading model…':'Applying…';
    for(const field of controls.values())field.disabled=true;
    for(const item of resolutionPresetButtons)item.button.disabled=true;
    if(loraList)for(const field of loraList.parentElement.querySelectorAll('input,button'))field.disabled=true;
    try{
      const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(candidate)});
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Unable to apply settings');
      info=data;fill(info.config);
      status.textContent='Settings saved.';
    }catch(error){status.textContent=error.message;}
    finally{
      applying=false;reset.disabled=false;
      for(const field of controls.values())field.disabled=false;
      for(const item of resolutionPresetButtons)item.button.disabled=false;
      if(loraList)for(const field of loraList.parentElement.querySelectorAll('input,button'))field.disabled=false;
      const message=status.textContent;changed();status.textContent=message;
    }
  });
  }
  initialize('.llama-settings:not(.image-settings)','#llama-settings-form','#llama-settings-open','/api/settings',llamaGroups,false);
  initialize('.image-settings','#image-settings-form','#image-settings-open','/api/image/settings',imageGroups,true);
})();

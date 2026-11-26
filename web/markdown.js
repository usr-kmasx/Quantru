(() => {
  const md = window.markdownit({
    html: false, linkify: true, breaks: false, typographer: false,
    highlight(code, lang) {
      try {
        if (lang && hljs.getLanguage(lang)) return hljs.highlight(code,{language:lang,ignoreIllegals:true}).value;
      } catch (_) {}
      return md.utils.escapeHtml(code);
    }
  });
  if (typeof texmath === 'function' && window.katex) {
    md.use(texmath,{engine:katex,delimiters:['dollars','brackets'],katexOptions:{throwOnError:false,trust:false}});
  }
  // Never fetch model-generated image URLs automatically.
  md.renderer.rules.image = (tokens, i) => md.utils.escapeHtml(tokens[i].content || 'Image');
  const fence = md.renderer.rules.fence;
  md.renderer.rules.fence = (tokens,i,options,env,self) => {
    const token=tokens[i];
    const lang=md.utils.escapeHtml(token.info.trim().split(/\s+/)[0] || 'text');
    const playable = /^(html|htm)$/i.test(lang);
    const play = playable ? '<button type="button" class="play-code" title="Preview HTML" aria-label="Preview HTML"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg></button>' : '';
    return '<div class="code-block"><div class="code-header"><span>'+lang+'</span><div class="code-actions">'+play+'<button type="button" class="copy-code">Copy</button></div></div>'+fence(tokens,i,options,env,self)+'</div>';
  };
  const linkOpen=md.renderer.rules.link_open || ((tokens,i,options,env,self)=>self.renderToken(tokens,i,options));
  md.renderer.rules.link_open=(tokens,i,options,env,self)=>{
    tokens[i].attrSet('target','_blank');
    tokens[i].attrSet('rel','noopener noreferrer');
    return linkOpen(tokens,i,options,env,self);
  };
  // Reconcile streamed Markdown without replacing existing controls.
  function patchChildren(parent, next) {
    const incoming = Array.from(next.childNodes);
    for (let i = 0; i < incoming.length; i++) {
      const fresh = incoming[i];
      const old = parent.childNodes[i];
      if (!old) { parent.append(fresh.cloneNode(true)); continue; }
      if (old.isEqualNode(fresh)) continue;
      if (old.nodeType !== fresh.nodeType || old.nodeName !== fresh.nodeName || old.namespaceURI !== fresh.namespaceURI) {
        old.replaceWith(fresh.cloneNode(true));
        continue;
      }
      if (old.nodeType === Node.TEXT_NODE || old.nodeType === Node.COMMENT_NODE) {
        old.nodeValue = fresh.nodeValue;
        continue;
      }
      if (old.nodeType !== Node.ELEMENT_NODE) continue;
      for (const attr of Array.from(old.attributes)) {
        if (!fresh.hasAttribute(attr.name)) old.removeAttribute(attr.name);
      }
      for (const attr of Array.from(fresh.attributes)) {
        if (old.getAttribute(attr.name) !== attr.value) old.setAttribute(attr.name, attr.value);
      }
      if (old.matches('.copy-code') && fresh.matches('.copy-code')) continue;
      if (old.matches('input[type=checkbox]')) old.checked = fresh.checked;
      if (old.matches('pre code')) {
        if (old.innerHTML !== fresh.innerHTML) old.replaceChildren(...Array.from(fresh.childNodes, n => n.cloneNode(true)));
        continue;
      }
      patchChildren(old, fresh);
    }
    while (parent.childNodes.length > incoming.length) parent.lastChild.remove();
  }
  // Each code block follows its own output until the reader scrolls up.
  const codeScroll = new WeakMap();
  function trackCode(pre) {
    let state = codeScroll.get(pre);
    if (state) return state;
    state = {follow:true};
    const nearBottom = () => pre.scrollHeight - pre.clientHeight - pre.scrollTop <= 24;
    pre.addEventListener('scroll', () => {
      if (pre.clientHeight > 0) state.follow = nearBottom();
    }, {passive:true});
    pre.addEventListener('wheel', e => {
      if (e.deltaY < 0 && pre.scrollHeight > pre.clientHeight) state.follow = false;
    }, {passive:true});
    codeScroll.set(pre,state);
    return state;
  }
  // Fade only recent visible text ranges. CSS highlights leave the Markdown
  // DOM, selection, code highlighting and copy buttons structurally intact.
  const fadeDuration=180, fadeLimit=200;
  const fadeStates=new WeakMap(), activeFades=new Map();
  const fadeNames=['quantru-fade-1','quantru-fade-2','quantru-fade-3','quantru-fade-4'];
  const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
  let fadeTimer=0;
  function visibleText(root){
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const parts=[];let text='',n;
    while((n=walker.nextNode())){
      if(!n.nodeValue||(/^\s+$/.test(n.nodeValue)&&n.nodeValue.includes('\n'))||n.parentElement?.closest('button,.code-header,.katex,[aria-hidden="true"]'))continue;
      const start=text.length;text+=n.nodeValue;
      parts.push({node:n,start,end:text.length});
    }
    return {text,parts};
  }
  function paintFades(){
    fadeTimer=0;
    if(!window.Highlight||!CSS.highlights)return;
    const groups=fadeNames.map(()=>new Highlight());
    const now=performance.now();
    for(const [root,state] of activeFades){
      if(!root.isConnected||reducedMotion.matches){activeFades.delete(root);continue;}
      state.batches=state.batches.filter(batch=>now-batch.time<fadeDuration);
      if(!state.batches.length){activeFades.delete(root);continue;}
      for(const batch of state.batches){
        const group=groups[Math.min(3,Math.floor((now-batch.time)/fadeDuration*4))];
        for(const part of state.parts){
          const start=Math.max(part.start,batch.start),end=Math.min(part.end,batch.end);
          if(start>=end||!part.node.isConnected)continue;
          const range=new Range();
          range.setStart(part.node,start-part.start);
          range.setEnd(part.node,end-part.start);
          group.add(range);
        }
      }
    }
    for(let i=0;i<groups.length;i++){
      if(groups[i].size)CSS.highlights.set(fadeNames[i],groups[i]);
      else CSS.highlights.delete(fadeNames[i]);
    }
    if(activeFades.size)fadeTimer=setTimeout(paintFades,35);
  }
  function updateFade(root,final){
    if(!window.Highlight||!CSS.highlights||reducedMotion.matches)return;
    let state=fadeStates.get(root);
    if(final&&!state)return; // Loading saved history must never animate.
    const {text,parts}=visibleText(root);
    const previous=state?.text||'';
    if(!state){state={text:'',parts:[],batches:[]};fadeStates.set(root,state);}
    if(!text.startsWith(previous))state.batches=[];
    const now=performance.now();
    const start=Math.max(previous.length,text.length-fadeLimit);
    if(text.length>start)state.batches.push({start,end:text.length,time:now});
    state.text=text;state.parts=parts;
    if(state.batches.length)activeFades.set(root,state);
    if(fadeTimer)clearTimeout(fadeTimer);
    paintFades();
    if(final)fadeStates.delete(root);
  }
  const pending=new WeakMap();
  window.renderMarkdown=(node,source,final=false,afterRender)=>{
    let job=pending.get(node);
    if(job){
      job.source=source;job.afterRender=afterRender;
      if(!final)return;
      clearTimeout(job.timer);
    }else job={source,afterRender,timer:0};
    const draw=()=>{
      pending.delete(node);
      if(!node.isConnected)return;
      const source=job.source,afterRender=job.afterRender;
      node.classList.add('markdown');
      const next=document.createElement("div");
      next.innerHTML=DOMPurify.sanitize(md.render(source),{ADD_TAGS:['eq','eqn','eqno'],ADD_ATTR:['target','rel','aria-hidden'],FORBID_TAGS:['img','iframe','object','embed','form'],FORBID_ATTR:['src','srcset']});
      // GFM task boxes, rendered as non-editable indicators.
      for(const li of next.querySelectorAll('li')){
        const first=li.firstChild?.nodeType===3?li.firstChild:li.querySelector('p')?.firstChild;
        if(first?.nodeType!==3) continue;
        const m=first.textContent.match(/^\[([ xX])\]\s+/);
        if(!m) continue;
        first.textContent=first.textContent.slice(m[0].length);
        const check=document.createElement('input'); check.type='checkbox'; check.checked=m[1]!==' '; check.disabled=true;
        first.parentNode.insertBefore(check,first); li.classList.add('task-item');
      }
      const before = new Map();
      for (const pre of node.querySelectorAll('pre')) {
        const state = trackCode(pre);
        before.set(pre,{text:pre.textContent,top:pre.scrollTop,left:pre.scrollLeft,follow:state.follow});
      }
      patchChildren(node, next);
      updateFade(node,final);
      for (const pre of node.querySelectorAll('pre')) {
        const state = trackCode(pre);
        const previous = before.get(pre);
        if (previous && previous.text === pre.textContent) continue;
        if (previous) {
          state.follow = previous.follow;
          pre.scrollLeft = previous.left;
        }
        if (state.follow) pre.scrollTop = pre.scrollHeight;
        else if (previous) pre.scrollTop = previous.top;
      }
      if (afterRender) afterRender();
    };
    if(final) draw();
    else {
      // Coalesce incoming chunks without postponing rendering indefinitely
      // during scrolling or continuous token delivery.
      pending.set(node,job);
      job.timer=setTimeout(draw,80);
    }
  };
  const preview = document.querySelector('.html-preview');
  const stage = preview.querySelector('.preview-stage');
  function openHTML(source) {
    stage.replaceChildren();
    const frame = document.createElement('iframe');
    frame.setAttribute('sandbox','allow-scripts');
    frame.setAttribute('referrerpolicy','no-referrer');
    frame.title = 'HTML preview';
    const policy = "default-src 'none'; script-src 'unsafe-inline' blob:; style-src 'unsafe-inline'; img-src data: blob:; font-src data: blob:; media-src data: blob:; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none';";
    frame.srcdoc = '<meta http-equiv="Content-Security-Policy" content="'+policy+'">'+source;
    stage.append(frame);
    if (!preview.open) preview.showModal();
  }
  preview.querySelector('.preview-close').onclick = () => preview.close();
  preview.addEventListener('close', () => stage.replaceChildren());
  document.addEventListener('click', e => {
    const play = e.target.closest('.play-code');
    if (!play) return;
    const code = play.closest('.code-block').querySelector('pre code');
    if (code) openHTML(code.textContent);
  });
  document.addEventListener('click',async e=>{
    const button=e.target.closest('.copy-code');
    if(!button) return;
    const code=button.closest('.code-block').querySelector('pre code').textContent;
    try{
      await navigator.clipboard.writeText(code);
      button.textContent='Copied';
      setTimeout(()=>button.textContent='Copy',1200);
    } catch(_) { button.textContent='Copy failed'; }
  });
})();

(() => {
  const toggle = document.querySelector('.quantru-logo');
  const panel = document.querySelector('.quantru-panel');
  function setOpen(open) {
    document.body.classList.toggle('panel-open', open);
    panel.inert = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close side panel' : 'Open side panel');
    toggle.title = open ? 'Close side panel' : 'Open side panel';
  }
  toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  // The full-height left edge, as wide as the logo inset, is a mouse shortcut.
  // Keep touch, keyboard, modal dialogs and the existing click toggle intact.
  document.addEventListener('pointermove', e => {
    if(e.pointerType!=='mouse'||e.buttons!==0||toggle.getAttribute('aria-expanded')==='true'||document.querySelector('dialog[open]'))return;
    const r=toggle.getBoundingClientRect();
    if(e.clientX>=0&&e.clientX<r.left)setOpen(true);
  },{passive:true});
  document.addEventListener('click', e => {
    if (toggle.getAttribute('aria-expanded') !== 'true' || document.querySelector('dialog[open]')) return;
    if (!panel.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !document.querySelector('dialog[open]') && toggle.getAttribute('aria-expanded') === 'true') {
      setOpen(false);
      toggle.focus();
    }
  });
  for(const [selector,button] of [['.llama-settings:not(.image-settings)','#llama-settings-open'],['.image-settings','#image-settings-open']]){
    const settings=document.querySelector(selector);
    document.querySelector(button).addEventListener('click',()=>{if(!settings.open)settings.showModal();});
    settings.querySelector('.llama-settings-close').addEventListener('click',()=>settings.close());
    settings.addEventListener('click',e=>{
      if(e.target!==settings)return;
      const r=settings.getBoundingClientRect();
      if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)settings.close();
    });
  }
})();

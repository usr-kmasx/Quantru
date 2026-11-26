// Keep keyboard traversal within the native Quantru window and active dialog.
(() => {
  if(location.origin!=='http://127.0.0.1:8765'||window.top!==window)return;
  const selector='a[href],button,input,select,textarea,summary,iframe,[tabindex],[contenteditable="true"]';
  function scope(){
    const dialogs=document.querySelectorAll('dialog[open]');
    return dialogs[dialogs.length-1]||document.body;
  }
  function candidates(root){
    return [...root.querySelectorAll(selector)].filter(el=>{
      if(el.tabIndex<0||el.matches(':disabled,[type="hidden"]')||el.closest('[hidden],[inert],[aria-hidden="true"]'))return false;
      if(!el.getClientRects().length||getComputedStyle(el).visibility!=='visible')return false;
      const details=el.closest('details:not([open])');
      if(details&&details.querySelector('summary')!==el)return false;
      return true;
    }).sort((a,b)=>(a.tabIndex||Infinity)-(b.tabIndex||Infinity));
  }
  let lastFocused=null;
  function moveFocus(reverse){
    const root=scope(),items=candidates(root);
    if(!items.length)return false;
    const active=document.activeElement,index=items.indexOf(active);
    const direction=reverse?-1:1;
    let next=index<0?(reverse?items.length-1:0):(index+direction+items.length)%items.length;
    for(let attempts=0;attempts<items.length;attempts++){
      const target=items[next];
      target.focus();
      if(document.activeElement===target){
        lastFocused?.removeAttribute('data-keyboard-focus');
        target.setAttribute('data-keyboard-focus','');
        lastFocused=target;
        return true;
      }
      next=(next+direction+items.length)%items.length;
    }
    return false;
  }
  window.quantruMoveFocus=moveFocus;
  document.addEventListener('focusout',e=>e.target.removeAttribute?.('data-keyboard-focus'),true);
  document.addEventListener('pointerdown',()=>lastFocused?.removeAttribute('data-keyboard-focus'),true);
  // The HTML preview is a sandboxed document with its own keyboard navigation.
  // Notify the GTK controller so it does not intercept keys while it is open.
  const preview=document.querySelector('.html-preview');
  const notifyPreview=()=>{
    window.webkit?.messageHandlers?.focusPreview?.postMessage(Boolean(preview?.open));
  };
  if(preview)new MutationObserver(notifyPreview).observe(preview,{attributes:true,attributeFilter:['open']});
  notifyPreview();
  document.addEventListener('keydown',e=>{
    if(!['Tab','ISO_Left_Tab'].includes(e.key)||e.altKey||e.ctrlKey||e.metaKey||e.defaultPrevented||preview?.open)return;
    if(moveFocus(e.shiftKey||e.key==='ISO_Left_Tab'))e.preventDefault();
  },true);
})();

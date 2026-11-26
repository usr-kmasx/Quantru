// Trusted local top frame only, in a separate WebKit script world.
(() => {
  if(location.origin!=='http://127.0.0.1:8765'||window.top!==window)return;
  const picker=window.webkit?.messageHandlers?.modelPicker;
  if(!picker)return;
  document.documentElement.dataset.nativeModelPicker='true';
  document.addEventListener('click',async event=>{
    if(!event.isTrusted||!(event.target instanceof Element))return;
    const button=event.target.closest('.settings-browse');
    if(!button||button.disabled)return;
    const field=button.parentElement.querySelector('input');
    if(!field||field.disabled)return;
    event.preventDefault();
    button.disabled=true;
    try{
      const path=await picker.postMessage({kind:button.dataset.kind,current:field.value});
      if(typeof path==='string'&&path&&field.isConnected&&!field.disabled&&field.closest('dialog')?.open){
        field.value=path;
        field.dispatchEvent(new Event('input',{bubbles:true}));
        field.dispatchEvent(new Event('change',{bubbles:true}));
      }
    }catch(error){console.warn('Model file selection:',String(error));}
    finally{button.disabled=false;}
  });
})();

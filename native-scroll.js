// Keep nested scrolling local even when WebKit propagates wheel gestures
// beyond the edge of an overflow container.
(() => {
  const regions='.quantru-panel,dialog,textarea,.thinking-text,.code-block pre,.markdown table,.katex-display,.markdown eqn,.shell-run-output,.chat-list,.llama-settings-body';
  document.addEventListener('wheel',event=>{
    if(event.defaultPrevented||event.ctrlKey||(!event.deltaY&&!event.deltaX))return;
    const target=event.target instanceof Element?event.target:null;
    if(!target)return;
    const region=target.closest(regions);
    const vertical=Math.abs(event.deltaY)>=Math.abs(event.deltaX);
    const axis=vertical?'Y':'X';
    let scroller=null;
    for(let el=target;el&&el!==document.body&&el!==document.documentElement;el=el.parentElement){
      const style=getComputedStyle(el);
      if(/^(auto|scroll|overlay)$/.test(style['overflow'+axis])){
        scroller=el;break;
      }
      if(el===region)break;
    }
    if(!scroller){
      if(region&&event.cancelable)event.preventDefault();
      return;
    }
    const pos=vertical?'scrollTop':'scrollLeft';
    const max=Math.max(0,vertical?scroller.scrollHeight-scroller.clientHeight:scroller.scrollWidth-scroller.clientWidth);
    const raw=vertical?event.deltaY:event.deltaX;
    const scale=event.deltaMode===1?16:event.deltaMode===2?(vertical?scroller.clientHeight:scroller.clientWidth):1;
    const next=scroller[pos]+raw*scale;
    if(event.cancelable&&(max<=1||next<=0||next>=max)){
      event.preventDefault();
      scroller[pos]=Math.max(0,Math.min(max,next));
    }
  },{capture:true,passive:false});
})();

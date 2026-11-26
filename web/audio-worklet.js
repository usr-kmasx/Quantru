class QuantruCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(9600);
    this.n = 0;
    this.done = false;
    this.port.onmessage = e => {
      if(e.data === 'finish') {
        this.done = true;
        this.flush();
        this.port.postMessage({finished:true});
      }
    };
  }
  flush() {
    if(!this.n)return;
    const pcm=this.buf.slice(0,this.n);
    this.port.postMessage({pcm},[pcm.buffer]);
    this.n=0;
  }
  process(inputs) {
    if(this.done)return false;
    const data=inputs[0]?.[0];
    if(data)for(const sample of data){
      this.buf[this.n++]=sample;
      if(this.n===this.buf.length)this.flush();
    }
    return true;
  }
}
registerProcessor('quantru-capture',QuantruCapture);

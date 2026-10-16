/* Trusted simulation ONLY. Never loaded during native API validation.
   Game clock control is private to the harness; model gets pixels/external clock. */
(() => {
  let seconds=0,paused=true;
  const offset=Number(globalThis.__MODEL_SIM_OFFSET_MS__||10000);
  let clock_ms=offset;
  const callbacks=new Map();let id=0;
  const media=HTMLMediaElement.prototype;
  Object.defineProperty(media,'currentTime',{get:()=>seconds,set:x=>{seconds=Number(x);clock_ms=offset+seconds*1000},configurable:true});
  Object.defineProperty(media,'paused',{get:()=>paused,configurable:true});
  media.play=async()=>{paused=false};media.pause=()=>{paused=true};
  Object.defineProperty(performance,'now',{value:()=>clock_ms,configurable:true});
  window.requestAnimationFrame=fn=>{callbacks.set(++id,fn);return id};
  window.cancelAnimationFrame=x=>callbacks.delete(x);
  function render(){const work=[...callbacks.values()];callbacks.clear();for(const fn of work)fn(performance.now())}
  globalThis.__modelSimulation={
    render,
    advance:target=>{
      if(!Number.isFinite(target)||target<seconds)throw Error('Nonmonotonic simulation clock');
      const target_ms=offset+target*1000;
      while(clock_ms<target_ms){
        const snapshot=window.__modelExecutor.snapshot();
        const next=snapshot.pending.filter(x=>x.at_ms>clock_ms).reduce((a,b)=>Math.min(a,b.at_ms),Infinity);
        clock_ms=Math.min(target_ms,clock_ms+1000/120,next);
        seconds=(clock_ms-offset)/1000;
        window.__modelExecutor.drain();render();
      }
      window.__modelExecutor.drain();render();
      if(seconds>=Number(globalThis.__MODEL_SIM_DURATION_S__||30.001) && document.body.dataset.state==='playing')document.getElementById('audio').dispatchEvent(new Event('ended'));
    }
  };
})();

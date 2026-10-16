/* Experiment instrumentation. Loaded with Playwright add_init_script, never by the public UI.
 * Policy workers receive screenshots and timestamps only, never this object or a Page.
 */
(() => {
  const virtual = globalThis.__RHYTHM_VIRTUAL__ === true;
  let time = 0, paused = true, nextId = 1;
  const callbacks = new Map();
  const nativeRAF=globalThis.requestAnimationFrame.bind(globalThis), nativeCancel=globalThis.cancelAnimationFrame.bind(globalThis);
  if (virtual) {
    const proto = HTMLMediaElement.prototype;
    Object.defineProperty(proto, 'currentTime', {get: () => time, set: t => { time = Number(t); }, configurable: true});
    Object.defineProperty(proto, 'paused', {get: () => paused, configurable: true});
    proto.play = async function () { paused = false; };
    proto.pause = function () { paused = true; };
    globalThis.requestAnimationFrame = fn => {const id=nextId++; callbacks.set(id,{fn,native:null}); return id;};
    globalThis.cancelAnimationFrame = id => {const item=callbacks.get(id);if(item && item.native!==null)nativeCancel(item.native); callbacks.delete(id);};
  }
  const fps=Number(globalThis.__RHYTHM_NATIVE_FPS__||0);
  if(!virtual && fps>0){
    let lastGameFrame=-Infinity;
    const pending=new Map();
    globalThis.requestAnimationFrame=fn=>{
      if(fn.name!=='frame')return nativeRAF(fn);
      const id=nextId++;
      const run=stamp=>{if(!pending.has(id))return;if(stamp-lastGameFrame>=1000/fps-.5){pending.delete(id);lastGameFrame=stamp;fn(stamp);}else pending.set(id,nativeRAF(run));};
      pending.set(id,nativeRAF(run));return id;
    };
    globalThis.cancelAnimationFrame=id=>{if(pending.has(id)){nativeCancel(pending.get(id));pending.delete(id);}else nativeCancel(id);};
  }
  const audio = () => document.getElementById('audio');
  let frameTime=0,framePerf=0;
  const clearRect=CanvasRenderingContext2D.prototype.clearRect;
  CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.id==='game' && audio()){frameTime=audio().currentTime;framePerf=performance.now();}return clearRect.apply(this,args);};
  const events = [], executed = [];
  let lateGrace=.055;
  const lastExecuted=lane=>{for(let i=executed.length-1;i>=0;i--)if(executed[i].lane===lane && executed[i].status==='executed')return executed[i];return null;};
  const keys = ['d','f','j','k'];
  function key(lane, down) {
    if (!Number.isInteger(lane) || lane < 0 || lane > 3) throw Error('Invalid DFJK lane');
    window.dispatchEvent(new KeyboardEvent(down ? 'keydown' : 'keyup', {key:keys[lane], code:'Key'+keys[lane].toUpperCase(), bubbles:true}));
  }
  function tap(lane) { key(lane,true); key(lane,false); }
  function render() {
    const batch = [...callbacks.values()]; callbacks.clear();
    for (const item of batch) {if(item.native!==null)nativeCancel(item.native);item.fn(performance.now());}
  }
  function processDue() {
    const now=audio().currentTime;
    while (events.length && events[0].time <= now + 1e-7) {
      const event=events.shift();
      // Expired plans never produce retrospective hits.
      if (now-event.time > lateGrace) {executed.push({...event,actual:now,status:'expired'});continue;}
      const previous=lastExecuted(event.lane);
      if(previous && now-previous.actual<.160){executed.push({...event,actual:now,status:'duplicate'});continue;}
      tap(event.lane); executed.push({...event,actual:now,status:'executed'});
    }
  }
  function advance(target) {
    if (!virtual) throw Error('Cannot control the real audio clock');
    if (!Number.isFinite(target) || target < time) throw Error('Clock must advance monotonically');
    while(time < target - 1e-9) {
      const nextEvent=events.length && events[0].time > time+1e-9 ? events[0].time : Infinity;
      time=Math.min(target,time+1/120,nextEvent);
      processDue(); render();
    }
    processDue(); render();
    // Native media ended does not fire with the simulated clock. Duration comes from the visible UI.
    const match=document.getElementById('time').textContent.match(/\/\s*(\d+):(\d+)/);
    if (match && time >= Number(match[1])*60+Number(match[2]) && document.body.dataset.state==='playing') audio().dispatchEvent(new Event('ended'));
  }
  function schedule(actions) {
    const now=audio().currentTime;
    for(const a of actions) {
      if(!Number.isFinite(a.time)||!Number.isInteger(a.lane)||a.lane<0||a.lane>3) throw Error('Invalid action');
    }
    const accepted=[];
    for(const a of actions) {
      if(a.time<now-lateGrace){executed.push({...a,actual:now,status:'expired'});continue;}
      // Exact repeated chunk entries are idempotent, distinct timing revisions remain explicit.
      if(!events.some(b=>b.lane===a.lane&&Math.abs(b.time-a.time)<.001)) {events.push({...a});accepted.push(a);}
    }
    events.sort((a,b)=>a.time-b.time || a.lane-b.lane);
    processDue(); return accepted;
  }
  if (!virtual) setInterval(()=>{if(audio() && document.body.dataset.state==='playing')processDue();},2);
  const clock=()=>({time_s:audio().currentTime,performance_ms:performance.now(),paused:audio().paused,state:document.body.dataset.state,ready_state:audio().readyState,network_state:audio().networkState,playback_rate:audio().playbackRate});
  globalThis.__rhythmAgent={virtual,advance,tap,schedule,render,
    snapshot:(after=0)=>({clock:clock(),actions:structuredClone(executed.slice(after)),cursor:executed.length}),
    configure:options=>{if(options.late_grace_ms!==undefined){if(!Number.isFinite(options.late_grace_ms)||options.late_grace_ms<0||options.late_grace_ms>110)throw Error('Invalid late grace');lateGrace=options.late_grace_ms/1000;}},
    replaceSchedule:input=>{
      const actions=Array.isArray(input)?input:input.actions;
      const guard=Array.isArray(input)?0:(input.commit_guard_ms||0)/1000;
      for(const a of actions)if(!Number.isFinite(a.time)||!Number.isInteger(a.lane)||a.lane<0||a.lane>3)throw Error('Invalid action');
      const now=audio().currentTime;
      const committed=events.filter(a=>a.time>=now && a.time-now<=guard);
      events.length=0;events.push(...committed);
      const filtered=actions.filter(a=>{
        const previous=lastExecuted(a.lane);
        if(previous && (Math.abs(previous.time-a.time)<1e-6 || (a.time-previous.actual>=-lateGrace && a.time-previous.actual<.160)))return false;
        if(committed.some(b=>b.lane===a.lane && Math.abs(b.time-a.time)<.160))return false;
        return true;
      });
      return schedule(filtered);
    },
    clear:()=>{events.length=0;executed.length=0;},
    captureTop200:()=>{const canvas=document.getElementById('game'),r=canvas.getBoundingClientRect(),b=document.querySelector('.board').getBoundingClientRect(),crop=document.createElement('canvas');crop.width=canvas.width;crop.height=200;crop.getContext('2d').drawImage(canvas,0,0,canvas.width,200,0,0,canvas.width,200);return {geometry:{width:canvas.width,height:200,canvas_top:r.y-b.y,canvas_height:r.height,hitline_y:r.height-88,top_lane_fraction:.63,travel_s:1.8,lane_keys:['D','F','J','K'],view:'rendered_canvas'},png:crop.toDataURL('image/png').split(',')[1],time_s:frameTime,performance_ms:framePerf,capture_s:audio().currentTime,state:document.body.dataset.state};},
    capture:()=>{const canvas=document.getElementById('game'),r=canvas.getBoundingClientRect(),b=document.querySelector('.board').getBoundingClientRect();return {geometry:{width:canvas.width,height:canvas.height,canvas_top:r.y-b.y,canvas_height:r.height,hitline_y:r.height-88,top_lane_fraction:.63,travel_s:1.8,lane_keys:['D','F','J','K'],view:'rendered_canvas'},png:canvas.toDataURL('image/png').split(',')[1],time_s:frameTime,performance_ms:framePerf,capture_s:audio().currentTime,state:document.body.dataset.state};},
    clock,
    actionLog:()=>structuredClone(executed),
    // Evaluator only; do not serialize raw rhythmDebug or its notes.
    evaluate:()=>{const s=window.rhythmDebug.getState(); return {state:s.state,time_s:s.time,score:s.score,combo:s.combo,max_combo:s.maxCombo,judged:s.judged,counts:{...s.counts},empty_presses:s.emptyPresses??null,total_notes:s.totalNotes??null};}
  };
})();

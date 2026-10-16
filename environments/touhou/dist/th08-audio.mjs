const ROOT = new URL('./assets/th08/audio/',import.meta.url);
export class OriginalAudio {
  constructor(context) {
    this.context=context;this.buffer=null;this.source=null;this.offset=0;this.startedAt=0;
    this.paused=true;this.error=null;this._volume=.45;this._muted=false;this.request=0;
    this.loop=true;this.currentSrc=new URL('kaguya-original.ogg',ROOT).href;
    this.ready=Promise.all([fetch(this.currentSrc).then(r=>{if(!r.ok)throw Error('BGM '+r.status);return r.arrayBuffer();}),fetch(new URL('kaguya-loop.json',ROOT)).then(r=>{if(!r.ok)throw Error('Loop '+r.status);return r.json();})]);
    this.ready.catch(e=>{this.error=String(e);});
  }
  get readyState(){return this.buffer?4:0;}
  get duration(){return this.buffer?.duration??0;}
  get volume(){return this._volume;}
  set volume(v){this._volume=Math.max(0,Math.min(1,Number(v)));this.updateGain();}
  get muted(){return this._muted;}
  set muted(v){this._muted=!!v;this.updateGain();}
  updateGain(){if(this.gain)this.gain.gain.value=this._muted?0:this._volume;}
  get currentTime(){
    let time=this.offset+(this.paused?0:this.context().currentTime-this.startedAt);
    if(this.points&&time>=this.points.loopEndSeconds)time=this.points.loopStartSeconds+(time-this.points.loopStartSeconds)%(this.points.loopEndSeconds-this.points.loopStartSeconds);
    return time;
  }
  set currentTime(v){const playing=!this.paused;this.pause();this.offset=Math.max(0,Math.min(Number(v),this.points?.loopEndSeconds??Number(v)));if(playing)this.play().catch(()=>{});}
  async load(){
    if(this.buffer)return;
    if(!this.decoding)this.decoding=(async()=>{
      const [bytes,points]=await this.ready,ctx=this.context();
      this.buffer=await ctx.decodeAudioData(bytes);this.points=points;
      if(!(points.loopStartSeconds>=0&&points.loopEndSeconds>points.loopStartSeconds&&points.loopEndSeconds<=this.buffer.duration+.02))throw Error('Invalid original loop points');
      this.gain=ctx.createGain();this.analyser=ctx.createAnalyser();this.gain.connect(this.analyser);this.analyser.connect(ctx.destination);this.updateGain();
    })();
    return this.decoding;
  }
  async play(){
    if(!this.paused)return;
    const request=++this.request;await this.load();const ctx=this.context();await ctx.resume();if(request!==this.request)return;
    const source=ctx.createBufferSource();source.buffer=this.buffer;source.loop=true;
    source.loopStart=this.points.loopStartSeconds;source.loopEnd=this.points.loopEndSeconds;
    source.connect(this.gain);source.start(0,this.offset);this.source=source;this.startedAt=ctx.currentTime;this.paused=false;
  }
  pause(){this.request++;this.offset=this.currentTime;this.paused=true;if(this.source){this.source.stop();this.source.disconnect();this.source=null;}}
  rms(){if(!this.analyser)return 0;const a=new Float32Array(this.analyser.fftSize);this.analyser.getFloatTimeDomainData(a);return Math.sqrt(a.reduce((s,x)=>s+x*x,0)/a.length);}
  state(){return {time:this.currentTime,paused:this.paused,ready:this.readyState,error:this.error,duration:this.duration,loopStart:this.points?.loopStartSeconds,loopEnd:this.points?.loopEndSeconds,rms:this.rms()};}
}
export class OriginalSfx {
  constructor(context){this.context=context;this.buffers=new Map();this.loading=null;this.muted=false;this.lastShot=-1;}
  async load(){
    const names=['se_pldead00.wav','se_plst00.wav','se_graze.wav','se_cat00.wav','se_enep00.wav','se_cancel00.wav','se_cardget.wav','se_pause.wav','se_damage00.wav','se_item00.wav'];
    if(!this.loading)this.loading=Promise.all(names.map(async name=>{const r=await fetch(new URL(name,ROOT));if(!r.ok)throw Error(name);this.buffers.set(name,await this.context().decodeAudioData(await r.arrayBuffer()));}));
    return this.loading;
  }
  play(kind,tick){
    if(this.muted)return;
    const map={hit:'se_pldead00.wav',shot:'se_plst00.wav',graze:'se_graze.wav',bomb:'se_cat00.wav',clear:'se_cardget.wav',spell:'se_enep00.wav',pause:'se_pause.wav',impact:'se_damage00.wav',cancel:'se_cancel00.wav'};
    const buffer=this.buffers.get(map[kind]);if(!buffer)return;
    if(kind==='shot'&&this.lastShot===tick)return;if(kind==='shot')this.lastShot=tick;
    const ctx=this.context(),source=ctx.createBufferSource(),gain=ctx.createGain();source.buffer=buffer;gain.gain.value=kind==='shot'?.16:kind==='graze'?.25:.55;source.connect(gain);gain.connect(ctx.destination);source.start();
  }
}

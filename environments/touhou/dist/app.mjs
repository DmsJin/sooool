import {Game, CHART, W, H} from './engine.mjs';
import {portrait, SPELLS} from './presentation.mjs';
import {originalAssets} from './th08-renderer.mjs';
import {OriginalAudio, OriginalSfx} from './th08-audio.mjs';

const $ = id => document.getElementById(id);
const canvas = $('game'), c = canvas.getContext('2d'), game = new Game(1);
const keys = new Set();
const researchEnabled = new URLSearchParams(location.search).get('research') === '1';
let researchMode='sim', researchSpeed=1, researchPlan=[], researchRemaining=0, researchHeld=[0,0,0,0];
let researchHuman=false, humanEdges=[], humanActions=[], humanLastAction=null;
let researchWallStart=0, researchMaxGap=0, researchBlurCount=0, researchIntroStart=0, researchActionStart=0;
const audioContext=()=>{audio??=new AudioContext();return audio;};
const bgm=new OriginalAudio(audioContext);
const originalSfx=new OriginalSfx(audioContext);
window.bgm=bgm;
bgm.volume=.45;
let bgmRequest=0;
async function playBgm(restart=false){
  if(restart)bgm.currentTime=0;
  bgm.muted=!sound;
  if(!started||paused||game.status!=='playing')return;
  const request=++bgmRequest;
  try{await bgm.play();if(request===bgmRequest){$('bgm-status').textContent='BGM · 竹取飛翔 ～ Lunatic Princess / ZUN';$('bgm-retry').hidden=true;}}
  catch{if(request===bgmRequest&&started&&!paused){$('bgm-status').textContent='BGM 未开始播放，请点击播放';$('bgm-retry').hidden=false;}}
}
function pauseBgm(){bgmRequest++;bgm.pause();}

$('bgm-retry').onclick=()=>playBgm();
$('bgm-volume').oninput=e=>{bgm.volume=Number(e.target.value)/100;};
let started = false, paused = false, last = 0, acc = 0, visualTick = 0;
let intro = 0, phaseIndex = 0, particles = [], audio = null, sound = true, lastNote = -1;
const hud=$('original-hud').getContext('2d');
let phaseHits = 0, phaseBombs = 3, history = [[0,0],[0,0],[0,0]], measuredFps = 60, fpsStart = 0, fpsFrames = 0;
try { const stored = JSON.parse(localStorage.getItem('kaguya-spell-history')); if (Array.isArray(stored) && stored.length===3 && stored.every(r=>Array.isArray(r)&&r.length===2&&r.every(Number.isFinite))) history=stored; } catch {}
function saveHistory() { try { localStorage.setItem('kaguya-spell-history',JSON.stringify(history)); } catch {} }
let lastUiKey = null;
let highScore = 0;
try { highScore = Number(localStorage.getItem('kaguya-high-score')) || 0; } catch {}

$('phases').innerHTML = CHART.map((p, i) => `<div class="phase" id="phase${i}"><span class="time">${p.start}–${p.end} SEC</span><h3>${p.title}</h3><p>${p.description}</p></div>`).join('');

function initAudio() {
  if (!sound) return;
  try { audio ??= new AudioContext(); audio.resume().catch(() => {}); } catch {}
}
function sfx(kind) { originalSfx.muted=!sound; originalSfx.play(kind,game.tick); }
function declareSpell(index, first = false) {
  phaseIndex = index;
  researchIntroStart=visualTick;
  intro = first ? 165 : 135;
  $('spell-name').textContent = SPELLS[index].name;
  history[index][1]++; saveHistory(); phaseHits=game.hits; phaseBombs=game.player.bombs;
  $('cutin').classList.remove('playing');
  $('cutin').style.animationPlayState = 'running';
  $('cutin').querySelector('img').style.animationPlayState = 'running';
  void $('cutin').offsetWidth;
  $('cutin').classList.add('playing');
  $('cutin').setAttribute('aria-hidden', 'false');
  sfx('spell');
}
function start() {
  initAudio(); game.reset(1); started = true; paused = false;
  keys.clear(); particles = []; acc = 0; visualTick = 0; lastNote = -1;
  $('overlay').style.display = 'none'; $('overlay').classList.remove('compact');
  $('pause').textContent = '暂停'; $('spell-result').classList.remove('show');
  playBgm(true);
  declareSpell(0, true);
}
function togglePause() {
  if (!started || game.status !== 'playing') return;
  paused = !paused; keys.clear(); acc = 0;
  $('pause').textContent = paused ? '继续' : '暂停';
  $('overlay').style.display = paused ? 'flex' : 'none';
  $('cutin').style.animationPlayState = paused ? 'paused' : 'running';
  $('cutin').querySelector('img').style.animationPlayState = paused ? 'paused' : 'running';
  sfx('pause');
  if(paused)pauseBgm();else playBgm();
  if (paused) {
    $('overlay').classList.add('compact'); $('title').textContent = '暂停';
    $('message').textContent = '永夜暂歇。按 Esc 或点击继续返回。';
    $('start').textContent = '继续练习 ↗';
  } else initAudio();
}
$('start').onclick = () => paused ? togglePause() : start();
$('restart').onclick = start; $('pause').onclick = togglePause;
$('sound').onclick = () => { sound = !sound; originalSfx.muted=!sound; bgm.muted=!sound; initAudio(); if(sound)playBgm(); $('sound').textContent = '声音：' + (sound ? '开' : '关'); };
$('fullscreen').onclick = async () => {
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.querySelector('main').requestFullscreen(); } catch { $('fullscreen').textContent = '请用浏览器全屏'; }
};
const allowed = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'KeyZ', 'KeyX', 'ShiftLeft', 'ShiftRight', 'Escape'];
window.addEventListener('keydown', e => {
  if (!allowed.includes(e.code) || (e.target instanceof HTMLElement && ['INPUT', 'TEXTAREA'].includes(e.target.tagName))) return;
  e.preventDefault();
  if (e.code === 'Escape') { if (!e.repeat) {togglePause();humanKeyEdge(e.code,true);} return; }
  if (e.code === 'KeyZ' && (!started || game.status !== 'playing')) { if (!researchHuman&&!e.repeat) start(); return; }
  const changed=!keys.has(e.code);keys.add(e.code);
  if(changed)humanKeyEdge(e.code,true);
});
window.addEventListener('keyup', e => {keys.delete(e.code);if(allowed.includes(e.code))humanKeyEdge(e.code,false);});
function blur() { if(researchEnabled){researchBlurCount++;if(researchHuman){for(const code of [...keys]){keys.delete(code);humanKeyEdge(code,false,'blur');}}return;} keys.clear(); if (started && !paused && game.status === 'playing') togglePause(); }
window.addEventListener('blur', blur);
document.addEventListener('visibilitychange', () => { if (document.hidden) blur(); });
for (const b of document.querySelectorAll('[data-key]')) {
  b.onpointerdown = e => { e.preventDefault(); b.setPointerCapture(e.pointerId); keys.add(b.dataset.key); };
  b.onpointerup = b.onpointercancel = () => keys.delete(b.dataset.key);
}
function action() {
  const x = Number(keys.has('ArrowRight')) - Number(keys.has('ArrowLeft'));
  const y = Number(keys.has('ArrowDown')) - Number(keys.has('ArrowUp'));
  const dir = [[0,0],[0,-1],[1,-1],[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1]].findIndex(d => d[0] === x && d[1] === y);
  return [dir, +keys.has('KeyZ'), +(keys.has('ShiftLeft') || keys.has('ShiftRight')), +keys.has('KeyX')];
}

function circle(x, y, r, color) {
  c.beginPath(); c.arc(x, y, r, 0, Math.PI*2); c.fillStyle = color; c.fill();
}
function polygon(points, color, stroke = null) {
  c.beginPath(); points.forEach(([x,y], i) => i ? c.lineTo(x,y) : c.moveTo(x,y)); c.closePath(); c.fillStyle = color; c.fill();
  if (stroke) { c.strokeStyle = stroke; c.lineWidth = 1; c.stroke(); }
}
function star(x, y, radius, color, angle = 0) {
  const points = Array.from({length:10}, (_, i) => { const a = i*Math.PI/5+angle; const r = i%2 ? radius*.45 : radius; return [x+Math.cos(a)*r,y+Math.sin(a)*r]; });
  polygon(points, color);
}
function burst(x, y, color, count = 12) {
  for (let i=0; i<count; i++) { const angle=i/count*Math.PI*2; particles.push({x,y,vx:Math.cos(angle)*(1+i%4),vy:Math.sin(angle)*(1+i%4),life:30+i%20,max:50,color,kind:'spark'}); }
}
function simulate() {
  if(researchEnabled && !researchHuman && intro===0)researchNextAction();
  visualTick++;
  for (const p of particles) { p.x+=p.vx; p.y+=p.vy; p.life--; if (p.kind==='item') { p.vx+=(game.player.x-p.x)*.001; p.vy+=(game.player.y-p.y)*.001; } }
  particles=particles.filter(p => p.life>0).slice(-400);
  if (intro>0) {
    intro--;
    if (intro===0) { $('cutin').classList.remove('playing'); $('cutin').setAttribute('aria-hidden','true'); }
    return;
  }
  const old = {score:game.score,graze:game.graze,hits:game.hits,bombs:game.player.bombs,dying:game.player.dying};
  const act=action();
  if(researchHuman){
    researchHeld=[...act];
    if(!humanLastAction||act.some((v,i)=>v!==humanLastAction[i])){
      humanActions.push({visual_frame:visualTick-1,logical_frame:game.tick,action:[...act],wall_ms:performance.now()-researchWallStart});
      humanLastAction=[...act];
    }
  }
  const cancelled=act[3]&&!game.lastBomb&&game.player.bombs>0?game.bullets.map(b=>({x:b.x,y:b.y,color:b.color})):[];
  game.step(act);
  if(researchEnabled&&!researchHuman&&researchRemaining>0){researchRemaining--;if(researchRemaining===0)researchNextAction();}
  if (act[1] && old.dying===0 && game.tick%10===0) sfx('shot');
  if (game.score>old.score && game.graze===old.graze) {burst(game.boss.x,game.boss.y,'#ffe3bc',3);if(game.tick%6===0)sfx('impact');}
  if (game.graze>old.graze) { burst(game.player.x,game.player.y,'#d7ebff',6); sfx('graze'); }
  if (game.hits>old.hits) sfx('hit');
  for(const event of game.events){
    if(event.type==='crash'){
      for(const color of ['#ff718f','#fff1eb','#eaa9e4'])burst(event.x,event.y,color,32);
      particles.push({x:event.x,y:event.y,vx:0,vy:0,life:45,max:45,color:'#fff0f3',kind:'crash-ring'});
      for(let i=0;i<16;i++)particles.push({x:event.x,y:event.y,vx:Math.cos(i*.8)*3,vy:Math.sin(i*.8)*3-1,life:48+i,max:64,color:i%2?'#ffe5ec':'#f16c90',kind:'paper'});
    }
    if(event.type==='respawn')burst(event.x,event.y,'#d9efff',18);
    if(event.type==='orb_hit'){burst(event.x,event.y,event.color,24);particles.push({x:event.x,y:event.y,vx:0,vy:0,life:22,max:22,color:event.color,kind:'impact'});}
    if(event.type==='cancel')particles.push({x:event.x,y:event.y,vx:0,vy:-1,life:30,max:30,color:'#fff3bb',kind:'item'});
  }
  if (game.player.bombs<old.bombs) {
    sfx('bomb');
    for (const b of cancelled) particles.push({x:b.x,y:b.y,vx:0,vy:-1,life:55,max:55,color:'#ffdc9b',kind:'item'});
    burst(game.player.x,game.player.y,'#ffe9c4',40);
  }
  if (game.status!=='playing') { finish(); return; }
  const next=Math.min(2,Math.floor(game.tick/1200));
  if (next!==phaseIndex) { if(game.hits===phaseHits && game.player.bombs===phaseBombs){ history[phaseIndex][0]++; saveHistory(); } declareSpell(next); }
}

function background(t) { originalAssets.background(c,t,phaseIndex,intro); }
function bossSprite(b,t) { originalAssets.boss(c,b,t,phaseIndex); }
function playerSprite(p,focus,t) { originalAssets.player(c,p,t,Number(keys.has('ArrowRight'))-Number(keys.has('ArrowLeft')),focus); }
function outlinedText(text,x,y,size,color='#fff3fa',align='left') {
  c.save();c.font=`${size}px Georgia,serif`;c.textAlign=align;c.lineJoin='round';c.lineWidth=3;c.strokeStyle='#2d192e';c.strokeText(text,x,y);c.fillStyle=color;c.fillText(text,x,y);c.restore();
}
function bullet(q) { originalAssets.bullet(c,q); }
function drawDreamSeal(t) {
  originalAssets.dreamSeal(c,game,t);
  if(game.bombTimer>0)outlinedText('霊符「夢想封印」',W/2,H-70,23,'#ffe8f6','center');
}
function draw() {
  const t=game.tick,p=game.player,b=game.boss,focus=keys.has('ShiftLeft')||keys.has('ShiftRight');
  c.setTransform(384/W,0,0,448/H,0,0);
  background(t);bossSprite(b,t);
  for(const shot of game.shots)originalAssets.shot(c,shot);
  for(const q of game.bullets)bullet(q);
  for(const effect of particles)originalAssets.particle(c,effect,t);
  if(p.dying===0)playerSprite(p,focus,t);
  drawDreamSeal(t);
  if(game.bombFlash){const f=game.bombFlash;c.fillStyle=`rgba(255,224,244,${f/90})`;c.fillRect(0,0,W,H);c.save();c.translate(p.x,p.y);c.rotate(t*.02);c.strokeStyle='#ffe6f4';c.lineWidth=2;for(const extra of [0,35]){c.beginPath();c.arc(0,0,(35-f)*23+extra,0,Math.PI*2);c.stroke();}c.restore();}
  // Reference-aligned boss strip, spell name, bonus and history.
  const remaining=Math.max(0,20-game.tick%1200/60);
  c.fillStyle='#1c1824';c.fillRect(2,3,W-4,5);
  const lifeWidth=(W-4)*b.hp/b.maxHp;
  const bar=c.createLinearGradient(0,0,W,0);bar.addColorStop(0,'#a5dcd9');bar.addColorStop(.2,'#c8e8c9');bar.addColorStop(.6,'#f0c4ca');bar.addColorStop(1,'#df8197');c.fillStyle=bar;c.fillRect(2,3,lifeWidth,5);
  for(let i=1;i<3-phaseIndex;i++){c.fillStyle='#fff5cc';c.fillRect(i*9,4,2,3);}
  originalAssets.entity(c,'front',24,3,17,128,16,{center:false});
  outlinedText(`+0(${String(Math.max(0,3-phaseIndex)).padStart(2,'0')})`,3,48,11,'#fff0a1');
  outlinedText(remaining.toFixed(2),W-5,23,22,'#d7e9ff','right');
  const bonus=(game.hits===phaseHits&&game.player.bombs===phaseBombs)?Math.floor(1000000*remaining/20):0;
  // Declaration briefly occupies the middle, then the same title settles at the top.
  const titleY=intro>0?H*.53:55;
  const spellDetail=`Bonus ${String(bonus).padStart(7,'0')}  History ${history[phaseIndex][0]} / ${history[phaseIndex][1]}`;
  if(intro===0){outlinedText(SPELLS[phaseIndex].name,W-9,titleY,15,'#fff0f7','right');outlinedText(spellDetail,W-9,titleY+22,11,'#eeebff','right');}
  $('cutin').querySelector('small').textContent=spellDetail;
  c.fillStyle='#e39dbb';polygon([[b.x-16,H-1],[b.x-12,H-8],[b.x+12,H-8],[b.x+16,H-1]],'#c183a0');c.fillStyle='#fff0f7';c.textAlign='center';c.font='7px monospace';c.fillText('Enemy',b.x,H-2);c.textAlign='left';
  outlinedText(String(Math.ceil(Math.max(0,60-game.tick/60))),W-6,H-9,16,'#fff5e9','right');
  const uiKey=[Math.floor(game.tick/6),p.lives,p.bombs,game.score,game.graze,phaseIndex,intro>0,paused,started,game.status,measuredFps].join('|');
  if(uiKey===lastUiKey)return;lastUiKey=uiKey;
  $('lives').textContent='★ '.repeat(Math.max(0,p.lives))||'—';$('bombs').textContent='★ '.repeat(p.bombs)||'—';
  $('score').textContent=String(game.score).padStart(10,'0');$('high-score').textContent=String(Math.max(highScore,game.score)).padStart(10,'0');$('graze').textContent=String(game.graze).padStart(4,'0');
  $('clock').textContent=`${String(Math.floor(game.tick/6)).padStart(4,'0')}/0`; $('point').textContent=String(Math.floor(game.score/10)).padStart(4,'0')+'/9999'; $('fps').textContent=measuredFps.toFixed(2)+'fps';$('progress').style.width=Math.min(100,game.tick/36)+'%';$('human-bar').style.left=(focus?78:23)+'%';
  $('state').textContent=paused?'PAUSED':!started?'READY / 准备就绪':intro>0?'SPELL CARD ATTACK':game.status==='playing'?(game.player.dying>0?'MISS / 坠机':game.bombTimer>0?'DREAM SEAL':'BOSS PRACTICE'):game.status==='lost'?'GAME OVER':'STAGE CLEAR';
  for(let i=0;i<3;i++)$('phase'+i).classList.toggle('active',i===phaseIndex);
  originalAssets.hud(hud,game,highScore,measuredFps);
}
function finish() {
  pauseBgm();
  if(researchEnabled){researchPlan=[];researchRemaining=0;researchSetKeys([0,0,0,0]);}
  keys.clear();highScore=Math.max(highScore,game.score);try{localStorage.setItem('kaguya-high-score',highScore)}catch{}
  $('overlay').style.display='flex';$('overlay').classList.add('compact');
  $('title').textContent=game.status==='lost'?'永夜再临':'月下通关';
  $('message').textContent=`得分 ${game.score} · 擦弹 ${game.graze} · 被弹 ${game.hits} 次。${game.status==='lost'?'试试 Shift 低速和 X 清屏。':'辉夜的月下试炼已经完成。'}`;
  $('start').textContent='再来一局 ↗';
  if(game.status!=='lost'){if(game.hits===phaseHits&&game.player.bombs===phaseBombs){history[phaseIndex][0]++;saveHistory();}sfx('clear');$('spell-result').textContent='SPELL CARD BONUS';$('spell-result').classList.add('show');}
}
function frame(now) {
  if(!researchEnabled){if(!fpsStart)fpsStart=now;fpsFrames++;if(now-fpsStart>=1000){measuredFps=Math.min(240,fpsFrames*1000/(now-fpsStart));fpsStart=now;fpsFrames=0;}}
  if(!last)last=now;
  const elapsed=Math.max(0,(now-last)/1000);
  if(researchEnabled)researchMaxGap=Math.max(researchMaxGap,elapsed);
  acc+=researchEnabled?(researchMode==='realtime'?elapsed*researchSpeed:0):Math.min(.1,elapsed);last=now;
  if(started&&!paused&&game.status==='playing'){
    while(acc>=1/60){simulate();acc-=1/60;if(game.status!=='playing'){acc=0;break}}
  }else{acc=0;if(!started&&!researchEnabled)visualTick++;}
  // Simulation is rendered by reset/apply/step/capture; waiting for a model
  // must not redraw identical atlases and DOM every animation frame.
  if(!researchEnabled||researchMode==='realtime'){
    if(researchEnabled)researchAnimations();
    draw();
  }
  requestAnimationFrame(frame);
}
$('start').disabled=true;$('start').textContent='原作素材加载中…';
Promise.all([originalAssets.ready,bgm.load(),originalSfx.load(),portrait.decode()]).then(()=>{
  $('start').disabled=false;$('start').innerHTML='开始练习 <span>START</span>';
  $('bgm-status').textContent='BGM · 竹取飛翔 ～ Lunatic Princess / ZUN · 原作循环';
}).catch(error=>{
  $('start').textContent='素材加载失败，请刷新';$('bgm-status').textContent='原作素材加载失败：'+String(error);
});
requestAnimationFrame(frame);
window.danmaku={getState:()=>game.snapshot(),getPresentation:()=>({intro,phaseIndex,paused,particles:particles.length,bgm:bgm.state(),assets:{ready:originalAssets.readyState,error:originalAssets.error,atlases:originalAssets.atlases.size},portraitLoaded:portrait.complete&&portrait.naturalWidth>0,spell:SPELLS[phaseIndex].name,history:history.map(r=>[...r])})};

// Experimental control is explicitly opt-in; normal site sessions keep their existing clock/input.
function researchSetKeys(a) {
  researchHeld=a.slice(0,4);keys.clear();
  const dirs=[[],['ArrowUp'],['ArrowUp','ArrowRight'],['ArrowRight'],['ArrowDown','ArrowRight'],['ArrowDown'],['ArrowDown','ArrowLeft'],['ArrowLeft'],['ArrowUp','ArrowLeft']];
  for(const key of dirs[a[0]])keys.add(key);
  if(a[1])keys.add('KeyZ');if(a[2])keys.add('ShiftLeft');if(a[3])keys.add('KeyX');
}
function researchNextAction() {
  if(researchRemaining>0)return;
  const next=researchPlan.shift();
  if(next){researchSetKeys(next);researchRemaining=next[4];researchActionStart=game.tick;}
  else researchSetKeys([0,researchHeld[1],researchHeld[2],0]);
}
function researchAnimations() {
  if(!researchEnabled)return;
  for(const animation of $('cutin').getAnimations({subtree:true})){
    animation.pause();animation.currentTime=(visualTick-researchIntroStart)*1000/60;
  }
}
function researchClock() {
  const wall=researchWallStart?performance.now()-researchWallStart:0;
  return {frame:game.tick,visual_frame:visualTick,intro,mode:researchMode,speed:researchSpeed,
    wall_ms:wall,max_raf_gap_ms:researchMaxGap*1000,actual_visual_speed:wall?visualTick/(wall*.06):0,
    blur_events:researchBlurCount,paused,status:game.status,held:[...researchHeld],remaining:researchRemaining,
    active_plan:researchRemaining?{action:[...researchHeld],start:researchActionStart,end:game.tick+researchRemaining}:null,
    pending_plan:researchPlan.map(a=>[...a])};
}
function humanKeyEdge(code,down,reason='keyboard') {
  if(!researchHuman)return;
  researchHeld=action();
  humanEdges.push({code,down,reason,visual_frame:visualTick,logical_frame:game.tick,wall_ms:performance.now()-researchWallStart,held:[...researchHeld],paused});
}
function researchCapture(asCanvas=false) {
  // Copy rendered native canvases synchronously: pixels and metadata refer to the same task.
  // Human realtime video copies the frame the game just rendered; avoid
  // rendering all atlases a second time for the recording canvas.
  if(!asCanvas||!researchHuman||researchMode!=='realtime'){draw();researchAnimations();}
  const image=document.createElement('canvas');image.width=640;image.height=480;
  const ctx=image.getContext('2d');ctx.imageSmoothingEnabled=false;ctx.fillStyle='#150d11';ctx.fillRect(0,0,640,480);
  const shell=document.querySelector('.game-shell'),box=shell.getBoundingClientRect();
  const scale=640/shell.clientWidth,originX=box.left+shell.clientLeft,originY=box.top+shell.clientTop;
  const rect=element=>{const r=element.getBoundingClientRect();return [(r.left-originX)*scale,(r.top-originY)*scale,r.width*scale,r.height*scale];};
  const arena=document.querySelector('.arena'),[ax,ay,aw,ah]=rect(arena);
  ctx.drawImage(canvas,...rect(canvas));
  // The cut-in is the original DOM portrait and CSS animation, sampled at its rendered pose.
  if(intro>0){
    ctx.save();ctx.beginPath();ctx.rect(ax,ay,aw,ah);ctx.clip();
    const cutin=$('cutin'),alpha=Number(getComputedStyle(cutin).opacity),img=cutin.querySelector('img');
    ctx.globalAlpha=alpha*Number(getComputedStyle(img).opacity);ctx.drawImage(img,...rect(img));
    ctx.globalAlpha=alpha;
    for(const element of cutin.querySelectorAll('.cutin-text > *')){
      const style=getComputedStyle(element);if(style.display==='none')continue;
      const [x,y,w,h]=rect(element);ctx.font=`${style.fontStyle} ${style.fontWeight} ${parseFloat(style.fontSize)*scale}px ${style.fontFamily}`;
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.lineJoin='round';ctx.lineWidth=parseFloat(style.webkitTextStrokeWidth||0)*scale;
      ctx.strokeStyle=style.webkitTextStrokeColor;ctx.fillStyle=style.color;
      if(ctx.lineWidth)ctx.strokeText(element.textContent,x+w/2,y+h/2);ctx.fillText(element.textContent,x+w/2,y+h/2);
    }
    ctx.restore();
  }
  ctx.drawImage($('original-hud'),0,0,640,480);
  // Human/youkai gauge is presentation-only DOM in the regular frontend.
  ctx.save();ctx.font='6px serif';ctx.fillStyle='#e2c2d3';ctx.fillText('人間',ax+4,ay+ah-5);ctx.fillText('妖怪',ax+83,ay+ah-5);
  ctx.strokeStyle='#a77b9b';ctx.strokeRect(ax+20,ay+ah-9,58,3);ctx.fillStyle='#e2c2d3';ctx.fillRect(ax+20+(researchHeld[2] ? .78:.23)*58,ay+ah-11,2,7);ctx.restore();
  const clock=researchClock();return {...(asCanvas?{canvas:image}:{png:image.toDataURL('image/png')}),frame:clock.frame,held:[...researchHeld],clock};
}
if(researchEnabled){
  const style=document.createElement('style');style.textContent='.game-shell{width:640px!important;height:480px!important;aspect-ratio:auto;font-size:12px!important;flex-shrink:0}';document.head.append(style);
  window.research={
    ready:()=>originalAssets.readyState&&!$('start').disabled,
    reset(seed=1,mode='sim',speed=1){
      if(!['sim','realtime'].includes(mode)||!(speed>0&&speed<=4))throw new Error('Invalid research clock');
      researchMode=mode;researchSpeed=speed;researchPlan=[];researchRemaining=0;researchHeld=[0,0,0,0];
      sound=false;originalSfx.muted=true;pauseBgm();start();game.reset(seed);researchSetKeys(researchHeld);
      history=[[0,1],[0,0],[0,0]];highScore=0;phaseHits=0;phaseBombs=game.player.bombs;lastUiKey=null;measuredFps=60;researchActionStart=0;
      researchWallStart=performance.now();researchMaxGap=0;researchBlurCount=0;last=performance.now();acc=0;
      researchAnimations();draw();return researchClock();
    },
    apply(plan){
      if(researchHuman)throw new Error('AI plans disabled while human controls are active');
      if(!Array.isArray(plan)||plan.length>16)throw new Error('Expected at most 16 action chunks');
      for(const a of plan)if(!Array.isArray(a)||a.length!==5||!a.every(Number.isInteger)||a[0]<0||a[0]>8||a.slice(1,4).some(v=>v!==0&&v!==1)||a[4]<1||a[4]>600)throw new Error('Invalid action chunk');
      researchPlan=plan.map(a=>[...a]);researchRemaining=0;researchNextAction();draw();return researchClock();
    },
    step(frames=1){
      if(researchMode!=='sim')throw new Error('Manual stepping is disabled in realtime mode');
      if(!Number.isInteger(frames)||frames<0||frames>10000)throw new Error('Invalid frame count');
      for(let i=0;i<frames&&game.status==='playing';i++)simulate();
      researchAnimations();draw();return researchClock();
    },
    setHuman(enabled){researchHuman=!!enabled;researchPlan=[];researchRemaining=0;researchSetKeys([0,0,0,0]);humanEdges=[];humanActions=[];humanLastAction=null;return researchClock();},
    setHumanAction(a){if(!researchHuman||!Array.isArray(a)||a.length!==4||!a.every(Number.isInteger)||a[0]<0||a[0]>8||a.slice(1).some(v=>v!==0&&v!==1))throw new Error('Invalid human replay action');researchSetKeys(a);return researchClock();},
    drainHumanEvents(){const result={keys:humanEdges,actions:humanActions};humanEdges=[];humanActions=[];return result;},
    captureCanvas:()=>researchCapture(true),getClock:researchClock,capture:researchCapture,
    diagnostics:()=>({clock:researchClock(),state:structuredClone(game.snapshot())})
  };
}

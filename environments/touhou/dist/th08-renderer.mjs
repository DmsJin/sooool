const BASE = new URL('./assets/th08/', import.meta.url);
const GROUPS = ['player00','stg7enm','stg7bg','face_st07sp','etama','front','ascii','enemy','eff01','eff02','eff03','eff07','eff09rm'];
export class TH08Renderer {
  constructor() {
    this.atlases=new Map();this.images=new Map();this.patterns=new Map();this.readyState=false;this.error=null;
    this.ready=this.load().then(()=>{this.readyState=true;return this;}).catch(error=>{this.error=String(error);throw error;});
  }
  async load() {
    await Promise.all(GROUPS.map(async group=>{
      const response=await fetch(new URL(`textures/${group}/frames.json`,BASE));
      if(!response.ok)throw Error(`Atlas ${group}: ${response.status}`);
      const frames=await response.json();this.atlases.set(group,new Map(frames.map(f=>[f.id,f])));
      await Promise.all([...new Set(frames.map(f=>f.image))].map(async file=>{
        const key=`${group}/${file}`;const image=new Image();
        image.src=new URL(`textures/${group}/${file}`,BASE).href;
        await image.decode();this.images.set(key,image);
      }));
    }));
  }
  frame(group,id) {return this.atlases.get(group)?.get(id);}
  image(group,id) {const f=this.frame(group,id);return f&&this.images.get(`${group}/${f.image}`);}
  draw(c,group,id,x,y,width,height,{center=true,angle=0,alpha=1,flip=false}={}) {
    const f=this.frame(group,id),im=this.image(group,id);if(!f||!im)return;
    width??=f.width;height??=f.height;
    c.save();c.imageSmoothingEnabled=false;c.translate(x,y);if(angle)c.rotate(angle);if(flip)c.scale(-1,1);c.globalAlpha*=alpha;
    c.drawImage(im,f.x,f.y,f.width,f.height,center?-width/2:0,center?-height/2:0,width,height);c.restore();
  }
  entity(c,group,id,x,y,width,height,options={}) {
    c.save();c.translate(x,y);c.scale(480/384,640/448);this.draw(c,group,id,0,0,width,height,options);c.restore();
  }
  text(c,text,x,y,{scale=1,spacing=12,align='left',alpha=1}={}) {
    text=String(text);if(align==='right')x-=text.length*spacing*scale;
    for(const char of text){const id=char.charCodeAt(0)-1;if(id>=31&&id<=126)this.draw(c,'ascii',id,x,y,16*scale,16*scale,{center:false,alpha});x+=spacing*scale;}
  }
  pattern(c,group,id,x,y,w,h,offsetX=0,offsetY=0,scale=1,alpha=1) {
    const source=this.image(group,id),frame=this.frame(group,id);if(!source||!frame)return;
    const key=group+'/'+id;
    if(!this.patterns.has(key)){const tile=document.createElement('canvas');tile.width=Math.min(frame.width,source.width-frame.x);tile.height=Math.min(frame.height,source.height-frame.y);tile.getContext('2d').drawImage(source,frame.x,frame.y,tile.width,tile.height,0,0,tile.width,tile.height);this.patterns.set(key,tile);}
    const image=this.patterns.get(key);
    c.save();c.beginPath();c.rect(x,y,w,h);c.clip();c.globalAlpha*=alpha;
    c.translate(x+offsetX,y+offsetY);c.scale(scale,scale);
    const pattern=c.createPattern(image,'repeat');c.fillStyle=pattern;
    c.fillRect((-Math.abs(offsetX)-w)/scale,(-Math.abs(offsetY)-h)/scale,(w*3+Math.abs(offsetX)*2)/scale,(h*3+Math.abs(offsetY)*2)/scale);c.restore();
  }
  // Original textures with a lightweight perspective camera; no gameplay coordinates change.
  background(c,t,phase,intro) {
    c.fillStyle='#080714';c.fillRect(0,0,480,640);
    this.draw(c,'stg7bg',7,0,0,480,640,{center:false});
    // Project the original cloud layers into rows receding to the horizon.
    const cloud=this.image('stg7bg',8),speed=t*.32;
    if(cloud&&intro>0){c.save();c.globalAlpha=.14;
      for(let y=180;y<640;y+=2){const depth=(y-150)/490,sy=((1/depth)*100-speed)%cloud.height;const sw=cloud.width*(.2+depth*.8);
        c.drawImage(cloud,(cloud.width-sw)/2,((sy%cloud.height)+cloud.height)%cloud.height,sw,1,0,y,480,2);
      }c.restore();}
    const effect=phase===1?'eff01':phase===2?'eff03':'eff02';
    this.pattern(c,effect,0,0,0,480,640,-(t*.48)%256,(t*.2)%256,1.9,.45);
    // Kaguya's original spell backdrop and rotating texture, from eff07 scripts.
    this.pattern(c,'eff07',3,0,0,480,640,(t*.09)%256,0,2.5,.46);
    c.save();c.translate(240,315);c.rotate(-t*.008);this.draw(c,'eff07',1,0,0,570,650,{alpha:.27});c.restore();
    this.draw(c,'face_st07sp',0,240,325,510*480/384,510*640/448,{alpha:intro>0?.12:.25});
    const shade=c.createLinearGradient(0,0,0,640);shade.addColorStop(0,'#07101a10');shade.addColorStop(1,'#0a071f55');c.fillStyle=shade;c.fillRect(0,0,480,640);
  }
  player(c,p,t,movement,focus) {
    if(p.dying)return;
    if(!this.motion||this.motion.direction!==movement)this.motion={direction:movement,since:t};
    let frame=Math.floor(t/6)%4;
    if(movement){const age=t-this.motion.since;frame=age<4?4+age:8+Math.floor((age-4)/6)%3;}
    this.entity(c,'player00',frame,p.x,p.y,30,46,{flip:movement>0,alpha:p.inv>0&&Math.floor(t/4)%2===0?.3:1});
    for(const sign of [-1,1])this.entity(c,'player00',32,p.x+sign*(focus?19:29),p.y-6,16,16,{angle:t*.04*sign,alpha:.8});
    if(focus){this.entity(c,'player00',44,p.x,p.y,21,21,{angle:t*.03,alpha:.7});c.beginPath();c.arc(p.x,p.y,3,0,Math.PI*2);c.fillStyle='white';c.fill();}
  }
  boss(c,b,t,phase) {
    const firing=t%[110,90,45][phase]<22;
    const id=firing?21+Math.floor(t/6)%4:13+Math.floor(t/5)%4;
    this.entity(c,'stg7enm',id,b.x,b.y+Math.sin(t*Math.PI/40)*5,80,80,{flip:Math.cos(t/150)<0});
  }
  shot(c,s) {this.entity(c,'player00',31,s.x,s.y,64,16,{angle:-Math.PI/2,alpha:.85});}
  bullet(c,q) {
    const id=q.color==='#b7a4ff'?19:q.color==='#ff9ab4'?35:255;
    this.entity(c,'etama',id,q.x,q.y,undefined,undefined,{angle:id===35?Math.atan2(q.vy,q.vx)+Math.PI/2:0});
  }
  particle(c,p,t) {
    const age=p.max-p.life,alpha=Math.min(1,p.life/15);
    if(p.kind==='item')this.entity(c,'etama',172,p.x,p.y,8,8,{alpha});
    else if(p.kind==='paper')this.entity(c,'player00',32,p.x,p.y,10,10,{angle:age*.12,alpha});
    else if(p.kind==='spark')this.entity(c,'ascii',11+Math.floor(age/2)%20,p.x,p.y,12,12,{alpha});
    else if(p.kind==='crash-ring')this.entity(c,'player00',44,p.x,p.y,24+age*5,24+age*5,{angle:age*.04,alpha:alpha*.75});
    else if(p.kind==='impact')this.entity(c,'etama',168,p.x,p.y,32+age*3,32+age*3,{alpha:alpha*.7});
  }
  dreamSeal(c,game,t) {
    if(game.bombTimer>0){
      const age=150-game.bombTimer,alpha=Math.min(1,age/15,game.bombTimer/30);
      this.pattern(c,'eff09rm',1,0,0,480,640,0,age*2,1.8,alpha*.13);
      c.save();c.translate(game.player.x,game.player.y);c.rotate(-age*.015707964);
      this.draw(c,'eff09rm',0,0,0,360,360,{alpha:alpha*.28});c.restore();
    }
    for(const orb of game.bombOrbs){
      for(let i=0;i<orb.trail.length;i++){const p=orb.trail[i];this.entity(c,'etama',168+orb.index%4,p.x,p.y,20,20,{alpha:i/orb.trail.length*.18});}
      c.save();c.globalCompositeOperation='lighter';this.entity(c,'etama',168+orb.index%4,orb.x,orb.y,55,55,{angle:t*.04});c.restore();
    }
  }
  hud(c,game,highScore,fps) {
    c.clearRect(0,0,640,480);const p=game.player;
    if(!this.hudStatic&&this.readyState){
      this.hudStatic=document.createElement('canvas');this.hudStatic.width=640;this.hudStatic.height=480;
      const layer=this.hudStatic.getContext('2d');
      for(const [x,y,w,h] of [[0,0,32,480],[32,0,384,16],[32,464,384,16],[416,0,224,480]])this.pattern(layer,'front',13,x,y,w,h);
      for(const [id,y] of [[2,40],[3,56],[4,88],[5,104],[6,136],[7,152],[8,168],[9,184]])this.draw(layer,'front',id,432,y,64,16,{center:false});
      this.draw(layer,'front',0,464,208,128,256,{center:false});this.draw(layer,'front',1,432,416,128,31,{center:false});
      this.draw(layer,'ascii',283,576,208,48,16,{center:false});
    }
    if(this.hudStatic)c.drawImage(this.hudStatic,0,0);
    this.text(c,String(Math.max(highScore,game.score)).padStart(10,'0'),620,40,{align:'right'});
    this.text(c,String(game.score).padStart(10,'0'),620,56,{align:'right'});
    for(let i=0;i<p.lives;i++)this.draw(c,'front',11,496+i*16,88,16,16,{center:false});
    for(let i=0;i<p.bombs;i++)this.draw(c,'front',12,496+i*16,104,16,16,{center:false});
    c.fillStyle='#c3bbd9';c.fillRect(496,138,128,12);this.text(c,'MAX',496,136,{spacing:12});
    this.text(c,String(game.graze),620,152,{align:'right'});
    this.text(c,Math.floor(game.score/10)+'/9999',620,168,{align:'right',spacing:10});
    this.text(c,Math.floor(game.tick/6)+'/0',620,184,{align:'right'});
    this.text(c,fps.toFixed(2)+'fps',620,464,{align:'right',spacing:10});
  }
}
export const originalAssets = new TH08Renderer();

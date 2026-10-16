import {test} from 'node:test';import assert from 'node:assert/strict';import {Game,CHART} from '../dist/engine.mjs';
test('same seed and actions reproduce full trajectory',()=>{const a=new Game(42),b=new Game(42);for(let t=0;t<1200;t++){const act=[Math.floor(t/60)%9,1,1,t===600?1:0];assert.deepEqual(a.step(act),b.step(act))}assert.deepEqual(a.snapshot(),b.snapshot())});
test('focus, bounds and bomb edge trigger',()=>{const g=new Game();g.step([3,0,1,0]);assert.equal(g.player.x,242);g.step([0,0,0,1]);for(let i=0;i<100;i++)g.step([3,0,0,1]);assert.equal(g.player.bombs,2);assert.equal(g.player.x,468)});
test('hit uses small core and invincibility',()=>{const g=new Game();g.player.inv=0;g.bullets=[{x:240,y:550,vx:0,vy:0,r:5},{x:240,y:550,vx:0,vy:0,r:5}];g.step();assert.equal(g.player.lives,2);assert.ok(g.player.inv>0)});
test('all phases spawn and timed survival truncates',()=>{const g=new Game();for(let t=0;t<3600;t++){g.player.inv=150;const r=g.step();if(t===1300)assert.equal(g.phase().pattern,'fan');if(t===2500)assert.equal(g.phase().pattern,'spiral');if(t===3599){assert.equal(r.truncated,true);assert.equal(r.terminated,false)}}assert.equal(g.status,'survived')});
test('shooting can defeat boss and defeat terminates',()=>{const g=new Game();g.boss.hp=1;g.shots=[{x:g.boss.x,y:g.boss.y+12}];assert.equal(g.step().terminated,true);assert.equal(g.status,'won');const h=new Game();h.player.lives=1;h.player.inv=0;h.bullets=[{x:240,y:550,vx:0,vy:0,r:5}];assert.equal(h.step().terminated,false);assert.equal(h.player.dying,45);for(let i=0;i<45;i++)h.step();assert.equal(h.status,'lost')});
test('browser and packaged Gym engines match',async()=>{const fs=await import('node:fs/promises');assert.equal(await fs.readFile('dist/engine.mjs','utf8'),await fs.readFile('python/touhou_gym/engine/engine.mjs','utf8'))});

test('crash hides control, then respawns at bottom with invulnerability',()=>{
 const g=new Game();g.player.x=100;g.player.y=300;g.player.inv=0;
 g.bullets=[{x:100,y:300,vx:0,vy:0,r:5}];g.step();
 assert.equal(g.player.lives,2);assert.equal(g.player.dying,45);assert.equal(g.events[0].type,'crash');
 for(let i=0;i<44;i++)g.step([3,1,0,1]);
 assert.equal(g.player.x,100);assert.equal(g.shots.length,0);assert.equal(g.player.bombs,3);
 g.step();assert.equal(g.player.dying,0);assert.equal(g.player.x,240);assert.equal(g.player.y,550);assert.equal(g.player.inv,150);assert.equal(g.events[0].type,'respawn');
});
test('Dream Seal expands, cancels bullets, homes and damages boss',()=>{
 const g=new Game();g.step([0,0,0,1]);assert.equal(g.bombOrbs.length,8);assert.equal(g.player.bombs,2);assert.equal(g.boss.hp,3200);
 const orb=g.bombOrbs[0];g.bullets=[{x:orb.x,y:orb.y,vx:0,vy:0,r:5}];g.step([0,0,0,1]);assert.equal(g.bullets.length,0);assert.ok(g.events.some(e=>e.type==='cancel'));
 let impacts=0;for(let i=0;i<145;i++){g.step([0,0,0,1]);impacts+=g.events.filter(e=>e.type==='orb_hit').length;}
 assert.equal(impacts,8);assert.equal(g.bombOrbs.length,0);assert.equal(g.boss.hp,2960);assert.equal(g.player.bombs,2);
});

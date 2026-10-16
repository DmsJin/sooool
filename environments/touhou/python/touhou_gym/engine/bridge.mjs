import readline from 'node:readline';
import {Game} from './engine.mjs';
const game=new Game();
for await (const line of readline.createInterface({input:process.stdin})){try{const req=JSON.parse(line);let result={reward:0,terminated:false,truncated:false};if(req.command==='reset')game.reset(req.seed??1);else if(req.command==='step')result=game.step(req.action);else throw Error('unknown command');console.log(JSON.stringify({...result,state:game.snapshot()}))}catch(e){console.log(JSON.stringify({error:e.message}))}}

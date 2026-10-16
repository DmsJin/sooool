// Display text only. Does not inspect notes, clocks, inputs, or judgments.
const english=new URLSearchParams(location.search).get('lang')==='en';
const strings={
'经典四键':'Classic 4 Keys','正在演奏':'Now Playing','演奏成绩':'Results',
'DFJK 击打 · 空格暂停':'DFJK to play · Space to pause','戴上耳机，准备开始':'Headphones on. Ready to play.',
'正在加载音乐…':'Loading music…','手指放在 D F J K 上':'Place your fingers on D F J K',
'演奏完成 · 再来一局？':'Finished. Play again?','已暂停':'Paused','音乐缓冲中…':'Buffering music…',
'音频加载失败，请重试或在设置中加载个人音频':'Audio failed to load. Retry or choose your own audio.',
'无法继续播放，请重试':'Could not resume. Please retry.',
'音频中断，请重试或切换个人音频':'Audio interrupted. Retry or choose another track.',
'经典四键 · RHYTHM LAB':'CLASSIC 4 KEYS · RHYTHM LAB','跟着音乐，让指尖记住节奏。':'Follow the music. Feel the rhythm.',
'自由模式':'FREE PLAY','Rick Astley · 官方 17 秒试听':'Rick Astley · Official 17-second preview',
'简单':'EASY','四分拍点 · 八分短连打 ·':'Quarter beats · Eighth-note runs ·',
'开始演奏':'START','音符到达光线时，按下对应按键':'Press the matching key when the note reaches the line.',
'演奏已暂停':'Paused','准备好后，继续你的节奏。':'Ready when you are.',
'继续演奏 ▶':'RESUME ▶','重新开始':'RESTART','返回选曲':'SONG SELECT','演奏完成 / RESULTS':'RESULTS',
'再来一次 ↻':'PLAY AGAIN ↻','用 D F J K 演奏':'Play with D F J K','空格暂停 / 继续':'Space to pause / resume',
'Gymnasium 环境 ↗':'Gymnasium environment ↗','音频与校准':'Audio & Calibration',
'判定偏移':'Timing offset','正值让判定提前。建议戴耳机，根据体感微调。':'Positive values advance timing. Adjust while wearing headphones.',
'个人音频':'Your audio','默认使用官方 17 秒试听段。个人音频按 113 BPM 生成练习谱。':'Official 17-second preview. Custom audio uses a 113 BPM practice chart.',
'恢复默认歌曲':'RESTORE DEFAULT TRACK','下载 Python Gym 环境 ↗':'Download Python Gym ↗',
'返回选曲':'Song select','设置':'Settings','暂停或继续':'Pause or resume','切换界面音效':'Toggle interface sounds',
'关闭设置':'Close settings','D 轨道':'D lane','F 轨道':'F lane','J 轨道':'J lane','K 轨道':'K lane',
'四轨节奏游戏。用 D F J K 或触摸底部四个按键击打。':'Four-lane rhythm game. Use D F J K or tap the bottom keys.',
'Never Gonna Give You Up 麦克风插画封面':'Never Gonna Give You Up microphone cover'
};
export function t(text){return english?(strings[text]??text):text}
export function translatePage(){
 if(!english)return;
 document.documentElement.lang='en';document.title='DFJK · Classic 4 Keys';
 const nodes=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 while(nodes.nextNode()){
  const n=nodes.currentNode;if(['SCRIPT','STYLE'].includes(n.parentElement?.tagName))continue;
  const trimmed=n.textContent.trim();if(strings[trimmed])n.textContent=n.textContent.replace(trimmed,strings[trimmed]);
 }
 for(const el of document.querySelectorAll('[aria-label],[alt]'))for(const attr of ['aria-label','alt'])if(el.hasAttribute(attr))el.setAttribute(attr,t(el.getAttribute(attr)));
}

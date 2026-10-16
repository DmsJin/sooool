"""Pixels and external timestamps for model-owned timing.

Only the private simulator and trusted evaluator access game internals.
The generic executor has no access to audio, chart, or judgement geometry.
Native capture uses raw CDP compositor frames and their frame-swap timestamps.
Epoch milliseconds minus public performance.timeOrigin expresses that timestamp
in the same clock domain as performance.now(); model action times are untouched.
"""
from pathlib import Path
import base64
import json
import asyncio
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[2]

class ModelVisualEnv:
    def __init__(self,url,*,virtual=False,browser_executable=None,audio_path=None,
                 chart_path=None,record_video_dir=None,clock_offset_ms=10000,sensor='screencast',record_sensor_dir=None):
        self.url,self.virtual=url,virtual
        self.browser_executable,self.audio_path=browser_executable,audio_path
        self.chart_path=Path(chart_path) if chart_path else None
        self.record_video_dir=Path(record_video_dir) if record_video_dir else None
        self.clock_offset_ms=clock_offset_ms
        self.record_sensor_dir=Path(record_sensor_dir) if record_sensor_dir else None
        self._recorded_sensor_frames=[]
        self.video_path=None
        self._pw=self._browser=self._page=None
        if sensor not in ('screencast','capture'):raise ValueError('Unknown pixel sensor')
        self.sensor='capture' if virtual else sensor
        self._latest_frame=None
        self._first_frame=asyncio.Event()
        self._sensor_tasks=set()
        self._sensor_closing=False
        self._frame_handler=None
        self.sensor_errors=[]
    async def __aenter__(self):return await self.open()
    async def __aexit__(self,*args):await self.close()
    async def open(self):
        self._pw=await async_playwright().start()
        options={'headless':True,'args':['--autoplay-policy=no-user-gesture-required','--disable-background-timer-throttling']}
        if self.browser_executable:options['executable_path']=str(self.browser_executable)
        self._browser=await self._pw.chromium.launch(**options)
        page_options={'viewport':{'width':390,'height':844},'device_scale_factor':1}
        if self.record_video_dir:
            self.record_video_dir.mkdir(parents=True,exist_ok=True)
            page_options.update(record_video_dir=str(self.record_video_dir),record_video_size={'width':390,'height':844})
        self._page=await self._browser.new_page(**page_options)
        if self.chart_path:
            payload=self.chart_path.read_bytes()
            await self._page.route('**/chart.json',lambda route:route.fulfill(body=payload,content_type='application/json'))
        if self.virtual:
            duration=json.loads(self.chart_path.read_text())['duration'] if self.chart_path else 30.001
            await self._page.add_init_script('globalThis.__MODEL_SIM_DURATION_S__='+str(duration))
            await self._page.route('**/AudioPreview*/**',lambda route:route.abort())
            await self._page.add_init_script('globalThis.__MODEL_SIM_OFFSET_MS__='+str(self.clock_offset_ms)+';\n'+(ROOT/'dist/model-sim-clock.js').read_text())
        await self._page.add_init_script((ROOT/'dist/model-executor.js').read_text())
        await self._page.goto(self.url,wait_until='domcontentloaded')
        # Load bundled CJK glyphs before any recording/model observation.
        await self._page.evaluate('document.fonts.ready.then(()=>true)')
        await self._page.wait_for_function('!!window.__modelExecutor && !!window.rhythmDebug',polling=20)
        if self.audio_path:
            value='data:audio/mp4;base64,'+base64.b64encode(Path(self.audio_path).read_bytes()).decode()
            await self._page.evaluate("src=>{document.getElementById('audio').src=src}",value)
        self._cdp=await self._page.context.new_cdp_session(self._page)
        if self.sensor=='screencast':
            self._time_origin_ms=await self._page.evaluate('performance.timeOrigin')
            self._frame_handler=self._receive_frame
            self._cdp.on('Page.screencastFrame',self._frame_handler)
            await self._cdp.send('Page.startScreencast',{'format':'png','maxWidth':390,'maxHeight':844,'everyNthFrame':1})
            await asyncio.wait_for(self._first_frame.wait(),10)
        return self
    def _receive_frame(self,event):
        if self._sensor_closing:return
        task=asyncio.create_task(self._ack_frame(event['sessionId']))
        self._sensor_tasks.add(task)
        task.add_done_callback(self._sensor_tasks.discard)
        timestamp=event['metadata'].get('timestamp')
        if timestamp is None:
            self.sensor_errors.append('Screencast frame has no raw frame-swap timestamp')
            return
        frame_ms=timestamp*1000-self._time_origin_ms
        self._latest_frame={'png':base64.b64decode(event['data']),
            'capture_start_ms':frame_ms,'capture_end_ms':frame_ms,
            'raw_frame_timestamp_epoch_s':timestamp,'time_origin_ms':self._time_origin_ms}
        if self.record_sensor_dir:self._recorded_sensor_frames.append(self._latest_frame)
        self._first_frame.set()
    async def _ack_frame(self,session_id):
        try:await self._cdp.send('Page.screencastFrameAck',{'sessionId':session_id})
        except Exception as error:
            if not self._sensor_closing:self.sensor_errors.append(type(error).__name__)
    async def close(self):
        self._sensor_closing=True
        if self._frame_handler:
            self._cdp.remove_listener('Page.screencastFrame',self._frame_handler)
            try:await self._cdp.send('Page.stopScreencast')
            except Exception:pass
        if self._sensor_tasks:await asyncio.gather(*tuple(self._sensor_tasks),return_exceptions=True)
        if self._page and self._page.video:
            video=self._page.video
            await self._page.context.close()
            self.video_path=str(await video.path())
        if self._browser:await self._browser.close()
        if self._pw:await self._pw.stop()
        if self.record_sensor_dir:
            await asyncio.to_thread(self._save_sensor_frames)
    def _save_sensor_frames(self):
        self.record_sensor_dir.mkdir(parents=True,exist_ok=True)
        metadata=[]
        for i,frame in enumerate(self._recorded_sensor_frames):
            name=f'frame-{i:05d}.png'
            (self.record_sensor_dir/name).write_bytes(frame['png'])
            metadata.append({**{k:v for k,v in frame.items() if k!='png'},'file':name})
        (self.record_sensor_dir/'frames.json').write_text(json.dumps(metadata))
        self._recorded_sensor_frames.clear()
    async def start(self):
        await self._page.locator('#start').click(force=True)
        await self._page.wait_for_function("document.body.dataset.state==='playing'",polling=20,timeout=30000)
        if self.virtual:await self._page.evaluate('window.__modelSimulation.render()')
    async def advance(self,seconds):
        if not self.virtual:raise RuntimeError('Native clocks must not be advanced or paused')
        await self._page.evaluate('t=>window.__modelSimulation.advance(t)',float(seconds))
    async def capture(self):
        if self.sensor=='screencast':
            if self._latest_frame is None:await asyncio.wait_for(self._first_frame.wait(),10)
            retrieved=await self._page.evaluate('performance.now()')
            # CDP events may update the frame while the public-clock RPC is
            # pending. Select the newest raw frame after that await instead of
            # unnecessarily holding an older image throughout the round trip.
            frame=dict(self._latest_frame)
            frame['capture_retrieved_ms']=retrieved
            frame['capture_staleness_ms']=retrieved-frame['capture_start_ms']
            return frame
        before=await self._page.evaluate('performance.now()')
        params={'format':'png','captureBeyondViewport':False,'fromSurface':True}
        if not self.virtual:params['optimizeForSpeed']=True
        data=await self._cdp.send('Page.captureScreenshot',params)
        after=await self._page.evaluate('performance.now()')
        return {'png':base64.b64decode(data['data']),'capture_start_ms':before,'capture_end_ms':after}
    async def snapshot(self):
        return await self._page.evaluate('window.__modelExecutor.snapshot()')
    async def apply(self,plan):
        return await self._page.evaluate('plan=>window.__modelExecutor.submit(plan)',plan)
    async def trusted_evaluator(self):
        # Never serialize this result into a policy observation.
        return await self._page.evaluate("""()=>{const s=window.rhythmDebug.getState();return {state:s.state,time_s:s.time,score:s.score,combo:s.combo,max_combo:s.maxCombo,judged:s.judged,counts:s.counts,empty_presses:s.emptyPresses,total_notes:s.totalNotes}}""")
    async def trusted_clock_diagnostic(self):
        # Native timing audit only; kept entirely outside observation construction.
        return await self._page.evaluate("""()=>{const a=document.getElementById('audio');return {external_ms:performance.now(),audio_s:a.currentTime,paused:a.paused,rate:a.playbackRate,state:document.body.dataset.state}}""")

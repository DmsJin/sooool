"""Executor-only improvements; imports original renderer/env without changing them."""
import asyncio, base64
from playwright.async_api import async_playwright
from .visual_env import Observation
from pathlib import Path
from . import visual_env as base

_OPEN_LOCK=asyncio.Lock()
BRIDGE_V2=Path(__file__).resolve().parents[2]/'dist/bridge-v2.js'

class VisualRhythmEnv(base.VisualRhythmEnv):
    def __init__(self,*args,late_grace_ms=55,mute_audio=None,native_fps=0,browser_executable=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.late_grace_ms=late_grace_ms
        self.mute_audio=mute_audio
        self.native_fps=native_fps
        self.browser_executable=browser_executable
        if not 0<=native_fps<=60:raise ValueError("Native FPS must be 0(auto) or <=60")

    async def open(self):
        self._pw=await async_playwright().start()
        launch={'headless':self.headless,'args':['--autoplay-policy=no-user-gesture-required','--disable-background-timer-throttling']}
        if self.browser_executable:launch['executable_path']=str(self.browser_executable)
        if self.mute_audio is False:launch['ignore_default_args']=['--mute-audio']
        elif self.mute_audio is True:launch['args'].append('--mute-audio')
        self._browser=await self._pw.chromium.launch(**launch)
        options={'viewport':{'width':self.viewport[0],'height':self.viewport[1]},'device_scale_factor':1}
        if self.record_video_dir:
            self.record_video_dir.mkdir(parents=True,exist_ok=True)
            options.update(record_video_dir=str(self.record_video_dir),record_video_size={'width':390,'height':844})
        self._page=await self._browser.new_page(**options)
        if self.virtual:await self._page.route('**/AudioPreview*/**',lambda route:route.abort())
        await self._page.add_init_script('globalThis.__RHYTHM_VIRTUAL__='+('true' if self.virtual else 'false')+';globalThis.__RHYTHM_NATIVE_FPS__='+str(self.native_fps)+';\n'+BRIDGE_V2.read_text())
        await self._page.goto(self.url,wait_until='domcontentloaded')
        await self._page.wait_for_function('!!window.rhythmDebug && !!window.__rhythmAgent',polling=20)
        if self.audio_path:
            encoded=base64.b64encode(Path(self.audio_path).read_bytes()).decode()
            await self._page.evaluate("s=>{document.getElementById('audio').src=s}",'data:audio/mp4;base64,'+encoded)
        self._cdp=await self._page.context.new_cdp_session(self._page)
        await self._page.evaluate('ms=>window.__rhythmAgent.configure({late_grace_ms:ms})',self.late_grace_ms)
        return self

    async def screenshot_cropped(self):
        capture=await self._page.evaluate('window.__rhythmAgent.captureTop200()')
        geometry=capture['geometry']
        geometry['frame_age_s']=max(0,capture['capture_s']-capture['time_s'])
        return Observation(base64.b64decode(capture['png']),capture['time_s'],capture['time_s'],capture['time_s'],geometry,capture['state'])

    async def snapshot(self,after_cursor=0):
        """Clock plus incremental execution acknowledgements in one browser task."""
        return await self._page.evaluate('cursor=>window.__rhythmAgent.snapshot(cursor)',after_cursor)

    async def replace_schedule(self,actions,commit_guard_ms=50):
        """Atomic idempotent replacement rechecks executed history at application."""
        return await self._page.evaluate('input=>window.__rhythmAgent.replaceSchedule(input)',
            {'actions':actions,'commit_guard_ms':commit_guard_ms})

"""Screenshot-only browser observation and DFJK execution.

Trusted orchestrator owns this object. An untrusted policy gets Observation.png
and .policy_metadata() ONLY, never Page, evaluator, dist files or chart. Virtual
mode controls the audio clock but uses the unmodified game renderer/judgement.
Real mode leaves the native audio clock and requestAnimationFrame untouched.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / 'dist' / 'agent-bridge.js'

@dataclass(frozen=True)
class Observation:
    png: bytes
    time_s: float
    capture_start_s: float
    capture_end_s: float
    geometry: dict[str, Any]
    state: str

    def policy_metadata(self):
        return {'time_s': self.time_s, 'capture_start_s': self.capture_start_s,
                'capture_end_s': self.capture_end_s, 'geometry': self.geometry,
                'state': self.state}

class VisualRhythmEnv:
    def __init__(self, url: str, *, virtual: bool = True, viewport=(390, 844),
                 headless=True, audio_path: str | None = None, record_video_dir: str | Path | None = None):
        self.url, self.virtual = url, virtual
        self.viewport, self.headless, self.audio_path = viewport, headless, audio_path
        self.record_video_dir = Path(record_video_dir) if record_video_dir else None
        self.video_path: str | None = None
        self._pw = self._browser = self._page = None

    async def open(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless,
            args=['--autoplay-policy=no-user-gesture-required','--disable-background-timer-throttling'])
        page_options = {'viewport':{'width':self.viewport[0], 'height':self.viewport[1]}, 'device_scale_factor':1}
        if self.record_video_dir:
            self.record_video_dir.mkdir(parents=True,exist_ok=True)
            page_options.update(record_video_dir=str(self.record_video_dir), record_video_size={'width':390,'height':844})
        self._page = await self._browser.new_page(**page_options)
        if self.virtual:
            await self._page.route('**/AudioPreview*/**', lambda route: route.abort())
        await self._page.add_init_script('globalThis.__RHYTHM_VIRTUAL__='+('true' if self.virtual else 'false')+';\n'+BRIDGE.read_text())
        await self._page.goto(self.url, wait_until='domcontentloaded')
        await self._page.wait_for_function('!!window.rhythmDebug && !!window.__rhythmAgent', polling=20)
        if self.audio_path:
            # The game's real media source is replaced with a local copy of the SAME preview.
            import base64
            encoded=base64.b64encode(Path(self.audio_path).read_bytes()).decode()
            await self._page.evaluate("s=>{document.getElementById('audio').src=s}", 'data:audio/mp4;base64,'+encoded)
        self._cdp = await self._page.context.new_cdp_session(self._page)
        return self

    async def __aenter__(self): return await self.open()
    async def __aexit__(self, *args): await self.close()

    async def close(self):
        if self._page and self._page.video:
            video=self._page.video
            await self._page.context.close()
            self.video_path=str(await video.path())
        if self._browser: await self._browser.close()
        if self._pw: await self._pw.stop()

    async def _start(self):
        await self._page.evaluate('window.__rhythmAgent.clear()')
        if await self._page.locator('body').get_attribute('data-state') == 'result':
            await self._page.locator('#again').click(force=True)
        else:
            await self._page.locator('#start').click(force=True)
        await self._page.wait_for_function("document.body.dataset.state === 'playing'",timeout=30000,polling=20)
        if self.virtual: await self._page.evaluate('window.__rhythmAgent.render()')
        return await self.screenshot()

    async def start_virtual(self):
        if not self.virtual: raise ValueError('Environment is real-time')
        return await self._start()

    async def start_realtime(self):
        if self.virtual: raise ValueError('Environment is virtual')
        return await self._start()

    async def advance(self, time_seconds: float):
        if not self.virtual: raise ValueError('Real audio may never be paused/advanced awaiting policy')
        await self._page.evaluate('t=>window.__rhythmAgent.advance(t)',float(time_seconds))
        return await self.clock()

    async def clock(self):
        return await self._page.evaluate('window.__rhythmAgent.clock()')

    async def tap(self, lane: int):
        await self._page.evaluate('lane=>window.__rhythmAgent.tap(lane)',lane)

    async def schedule(self, actions: list[dict]):
        """Absolute audio seconds, lanes D=0,F=1,J=2,K=3. Old >30ms discarded."""
        return await self._page.evaluate('a=>window.__rhythmAgent.schedule(a)',actions)

    async def replace_schedule(self, actions: list[dict]):
        """Atomically replace unexecuted actions; leave execution history intact."""
        return await self._page.evaluate('a=>window.__rhythmAgent.replaceSchedule(a)',actions)

    async def screenshot(self, *, full_page=False):
        import base64
        if full_page:
            before=await self.clock()
            png=await self._page.screenshot(full_page=True)
            after=await self.clock()
            return Observation(png,(before['time_s']+after['time_s'])/2,
                before['time_s'],after['time_s'],{},after['state'])
        # Canvas pixels, geometry and actual render-frame timestamp in ONE JS task.
        # Reading the frame clock, rather than RPC midpoint, prevents export/network
        # latency from shifting perceived note timing. Native music keeps playing.
        capture=await self._page.evaluate('window.__rhythmAgent.capture()')
        geometry=capture['geometry']
        geometry['frame_age_s']=max(0,capture['capture_s']-capture['time_s'])
        return Observation(base64.b64decode(capture['png']),capture['time_s'],
            capture['time_s'],capture['time_s'],geometry,capture['state'])

    async def evaluator(self):
        """TRUSTED evaluator channel only. Never include in a decision prompt."""
        return await self._page.evaluate('window.__rhythmAgent.evaluate()')

    async def action_log(self):
        return await self._page.evaluate('window.__rhythmAgent.actionLog()')

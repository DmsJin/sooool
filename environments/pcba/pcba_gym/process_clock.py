"""Process-isolated authoritative physics; renderer/model workers cannot own its GIL."""
import multiprocessing as mp
import threading
import time
import numpy as np
import mujoco
from .environment import PCBATestCell


def _serve(pipe,layout,seed,asset_dir):
    from .loop import PCBALoopCell
    from .environment import RealtimeSession
    env=(PCBALoopCell if layout=='loop' else PCBATestCell)(seed=seed,asset_dir=asset_dir)
    session=None;stopped=None
    def state():
        with env.lock:
            return {**{k:getattr(env.data,k).copy() for k in ('qpos','qvel','ctrl','eq_active')},
                    'geom_rgba':env.model.geom_rgba.copy(),'time':float(env.data.time)}
    pipe.send({'xml':env.xml,'state':state()})
    try:
        while True:
            op,args,kwargs=pipe.recv()
            try:
                if op=='close':pipe.send({'value':None});break
                if op=='start':
                    if session is not None:raise RuntimeError('Clock already started')
                    session=RealtimeSession(env).start();value=None
                elif op=='stop':
                    session.close();stopped=session.timing();value=stopped
                elif op=='timing':value=stopped or session.timing()
                elif op=='state':value=state()
                elif op=='observe':
                    with env.lock:value={'observation':env.observe(),'state':state()}
                elif op=='command':value=env.command(*args,**kwargs)
                elif op=='diagnostics':value=env.diagnostics()
                else:raise ValueError('Unknown physics RPC')
                # A blocked state transfer must not block authoritative physics.
                pipe.send({'value':value})
            except Exception as exc:pipe.send({'error':f'{type(exc).__name__}: {exc}'})
    except (EOFError,BrokenPipeError):pass
    finally:
        if session:session.close()
        env.close();pipe.close()


class ProcessCell:
    """The parent holds a rendering snapshot only; all commands go to physics."""
    def __init__(self,*,layout,seed,asset_dir):
        self.lock=threading.RLock();self._render_lock=threading.Lock();self._renderer=None
        ctx=mp.get_context('spawn');self._pipe,child=ctx.Pipe()
        self._process=ctx.Process(target=_serve,args=(child,layout,seed,asset_dir),name='pcba-physics-process')
        self._process.start();child.close()
        if not self._pipe.poll(30):raise RuntimeError('Physics process setup timed out')
        setup=self._pipe.recv();self.xml=setup['xml']
        self.model=mujoco.MjModel.from_xml_string(self.xml);self.data=mujoco.MjData(self.model)
        self._apply(setup['state'])

    def _rpc(self,op,*args,**kwargs):
        with self.lock:
            self._pipe.send((op,args,kwargs))
            if not self._pipe.poll(10):raise RuntimeError('Physics process RPC timed out')
            reply=self._pipe.recv()
            if 'error' in reply:raise RuntimeError(reply['error'])
            return reply['value']

    def _apply(self,snapshot):
        for k in ('qpos','qvel','ctrl','eq_active'):getattr(self.data,k)[:]=snapshot[k]
        self.data.time=snapshot['time'];self.model.geom_rgba[:]=snapshot['geom_rgba']
        mujoco.mj_forward(self.model,self.data)

    def sync_snapshot(self):
        with self.lock:self._apply(self._rpc('state'))

    def observe(self,cameras=(),width=640,height=480):
        with self.lock:
            packet=self._rpc('observe');obs=packet['observation'];snapshot=packet['state'];self._apply(snapshot)
        if cameras:
            with self._render_lock:
                if self._renderer is None or self._render_size!=(width,height):
                    if self._renderer:self._renderer.close()
                    self._render_model=mujoco.MjModel.from_xml_string(self.xml);self._render_data=mujoco.MjData(self._render_model)
                    self._renderer=mujoco.Renderer(self._render_model,height=height,width=width);self._render_size=(width,height)
                for k in ('qpos','qvel','ctrl','eq_active'):getattr(self._render_data,k)[:]=snapshot[k]
                self._render_data.time=snapshot['time'];self._render_model.geom_rgba[:]=snapshot['geom_rgba']
                mujoco.mj_forward(self._render_model,self._render_data);obs['images']={}
                for camera in cameras:
                    self._renderer.update_scene(self._render_data,camera=camera)
                    obs['images'][camera]=self._renderer.render().copy()
        return obs

    def command(self,*args,**kwargs):return self._rpc('command',*args,**kwargs)
    def diagnostics(self):return self._rpc('diagnostics')
    def close(self):
        if self._process.is_alive():self._rpc('close')
        self._process.join(timeout=5);self._pipe.close()
        if self._process.is_alive():self._process.terminate();self._process.join(timeout=5)
        if self._renderer:self._renderer.close();self._renderer=None


class ProcessSession:
    def __init__(self,env):self.env=env
    def start(self):self.env._rpc('start');return self
    def close(self):self.env._rpc('stop')
    def timing(self):return self.env._rpc('timing')


def main():
    import argparse,json
    from pathlib import Path
    from io import BytesIO
    from PIL import Image
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['clock-preflight'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=float,default=6.)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    env=ProcessCell(layout='loop',seed=0,asset_dir=a.output/'assets');session=None;captures=0
    try:
        env.observe(cameras=('overview','top','wrist'))
        session=ProcessSession(env).start();end=time.monotonic()+a.duration
        while time.monotonic()<end:
            obs=env.observe(cameras=('overview','top','wrist'))
            for pixels in obs['images'].values():Image.fromarray(pixels).save(BytesIO(),format='PNG')
            captures+=1;time.sleep(.1)
        session.close();timing=session.timing();session=None
        timing['wall_minus_sim_s']=timing['wall_elapsed_s']-timing['sim_elapsed_s']
        timing['timing_valid']=timing['max_tick_lag_s']<=.02 and abs(timing['wall_minus_sim_s'])<=max(.05,timing['wall_elapsed_s']*.01)
        diag=env.diagnostics()
        report={'kind':'process_clock_render_preflight','model_calls':0,'three_camera_captures':captures,'timing':timing,
                'finite_state':diag['finite_state'],'physics_warning_counts':diag['physics_warning_counts'],'dropped':diag['dropped']}
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    finally:
        if session:session.close()
        env.close()

"""Offline oracle validation of the loop, not a model-control evaluation."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from .loop import PCBALoopCell, LENGTH, SPEED, nearest_path
from .scene import FIXTURE, OUTPUTS, BOARD_COUNT
from .demo import move, travel, capture


def track_pick(env,i):
    """Oracle-only moving interception; exact poses never go to model actors."""
    move(env,[-.36,0,1.025])
    for _ in range(1000):
        p=env._board_position(i)
        if -.41<p[0]<-.30 and -.14<p[1]<.04:break
        env.advance(.05)
    else:raise RuntimeError('Board did not return to pick window')
    for _ in range(100):
        p=env._board_position(i);dof=env._dofs[i]
        predicted=p+np.r_[env.data.qvel[dof:dof+2]*.25,0.]
        predicted[:2]+=.5*(env.target[:2]-env.data.site_xpos[env.tcp][:2])
        goal=np.r_[predicted[:2],p[2]+.001,env._yaw(i)]
        delta=goal-env.target
        if np.linalg.norm(delta[:3])>.012:delta[:3]*=.012/np.linalg.norm(delta[:3])
        delta[3]=(delta[3]+np.pi)%(2*np.pi)-np.pi
        env.step({'delta_xyz_m':delta[:3].tolist(),'delta_yaw_rad':float(np.clip(delta[3],-.10,.10)),
                  'vacuum':bool(abs(delta[3])<.05)})
        if env.held is not None:
            if env.held!=i:raise RuntimeError('Unexpected board picked')
            return
    raise RuntimeError('Moving interception failed')


def align_fixture(env,i):
    """Oracle-only correction of the measured board/tool attachment offset."""
    move(env,[env.target[0],env.target[1],1.025],yaw=env.target[3])
    for _ in range(3):
        p=env._board_position(i);tcp=env.data.site_xpos[env.tcp].copy()
        yaw=env.observe()['robot']['tcp_yaw_rad']-env._yaw(i)
        xy=FIXTURE[:2]-(p-tcp)[:2]
        move(env,[*xy,1.025],yaw=yaw)
    p=env._board_position(i);tcp=env.data.site_xpos[env.tcp].copy()
    goal=FIXTURE+np.array([0,0,.001])-(p-tcp)
    move(env,goal,yaw=env.target[3])


def run(output,seed=0,unattended_seconds=0.):
    if not 0<=unattended_seconds<=60:raise ValueError('Invalid unattended duration')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    env=PCBALoopCell(seed=seed,asset_dir=out/'assets');states=[];times=[];next_sample=env.data.time
    original_tick=env._tick
    def tick():
        nonlocal next_sample
        original_tick()
        if env.data.time>=next_sample:
            states.append({k:getattr(env.data,k).copy() for k in ('qpos','qvel','ctrl','eq_active')})
            states[-1]['geom_rgba']=env.model.geom_rgba.copy();times.append(float(env.data.time));next_sample+=.5
    env._tick=tick
    try:
        (out/'scene.xml').write_text(env.xml)
        capture(env,out,'01-loop-overview',size=(1920,1440))
        capture(env,out,'02-loop-top','top',size=(1920,1440))
        # Deliberately let all boards make an unattended lap first: genuine
        # physical recirculation, never resetting/teleporting a missed board.
        env.advance(unattended_seconds)
        lap_check=env.diagnostics()
        if unattended_seconds>=45:assert min(lap_check['loop']['distance_m'])>LENGTH
        assert not lap_check['dropped']
        capture(env,out,'03-returned-boards','top',size=(1920,1440))
        for _ in range(BOARD_COUNT):
            move(env,[-.36,0,1.025])
            remaining=[i for i in range(BOARD_COUNT) if i not in env.sorted]
            def arrival(i):
                p=env._board_position(i);s,_,_=nearest_path(p[:2])
                return 0. if -.41<p[0]<-.30 and -.14<p[1]<.04 else (.04-s)%LENGTH
            i=min(remaining,key=arrival)
            track_pick(env,i)
            p=env._board_position(i);move(env,[p[0],p[1],1.025],yaw=env.target[3])
            # Correct the board's observed yaw while carrying it to the fixture.
            align_fixture(env,i)
            env.step({'vacuum':False});env.advance(.25)
            move(env,[*FIXTURE[:2],1.025])
            if not env.command({'fixture':'close'})['accepted']:raise RuntimeError('Fixture alignment failed')
            env.advance(.3)
            assert env.command({'fixture':'start_test'})['accepted']
            while env.tester=='running':env.advance(.05)
            result=env.observe()['fixture']['result']
            assert result['board_id']==f'PCBA-{i+1:03}'
            assert env.command({'fixture':'open'})['accepted'];env.advance(.3)
            board=env._board_position(i);move(env,[*board[:2],board[2]+.001])
            env.step({'vacuum':True});env.advance(.15)
            assert env.held==i
            status=result['status'];slot=env.observe()['outputs'][status]['occupied_slots'].index(False)
            goal=OUTPUTS[status][slot]
            if status=='ERROR':travel(env,[*goal[:2],goal[2]+.001])
            else:
                approach=[goal[0],.045,goal[2]+.006];travel(env,approach)
                move(env,[*goal[:2],goal[2]+.006])
            env.step({'vacuum':False});env.advance(.3)
            if status!='ERROR':move(env,approach)
            move(env,[env.target[0],env.target[1],1.025]);env.advance(.15)
            assert env.sorted[i]['correct']
            print(json.dumps({'board':i+1,'status':status,'sim_s':env.data.time,'expired':sorted(env._expired)}),flush=True)
        capture(env,out,'04-complete-overview',size=(1920,1440))
        capture(env,out,'05-loaded-containers','racks_closeup',size=(1920,1440))
        d=env.diagnostics()
        assert d['finite_state'] and not d['dropped'] and not any(d['physics_warning_counts'])
        report={'kind':'scripted_oracle_loop_validation','model_calls':0,'clock_mode':'offline fixed-step',
                'unattended_seconds':unattended_seconds,
                'not_vla_evidence':True,'lap_check':lap_check,'diagnostics':d,'nominal_lap_s':LENGTH/SPEED,
                'video_sample_interval_s':.5,'source':'native MuJoCo state replay; no image generation'}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    except BaseException as exc:
        (out/'failure.json').write_text(json.dumps({'error':str(exc),'diagnostics':env.diagnostics()},indent=2)+'\n')
        raise
    finally:
        if states:
            np.savez_compressed(out/'recorded-states.npz',**{k:np.stack([s[k] for s in states]) for k in states[0]})
            (out/'replay.json').write_text(json.dumps({'simulation_times_s':times,'sample_interval_s':.5},indent=2)+'\n')
        env.close()
    print(json.dumps({'output':str(out),'simulation_s':d['time_s'],'sorted':len(d['sorted']),
                      'all_on_time':d['loop']['all_on_time'],'model_calls':0}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['loop-demo'])
    p.add_argument('--output',type=Path,default=Path('runs')/f'pcba-loop-{time.strftime("%Y%m%dT%H%M%S")}')
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--unattended-seconds',type=float,default=0.)
    a=p.parse_args();run(a.output,a.seed,a.unattended_seconds)

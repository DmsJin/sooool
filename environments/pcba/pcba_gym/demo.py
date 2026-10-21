"""Scripted/oracle plumbing check. This is NOT model-controlled evidence."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from .environment import PCBATestCell, RealtimeSession
from .scene import FIXTURE, OUTPUTS, BOARD_COUNT


def move(env,position,yaw=0.):
    target=np.r_[position,yaw]
    for _ in range(400):
        delta=target-env.target
        if np.linalg.norm(delta[:3])<1e-6 and abs(delta[3])<1e-6:break
        displacement=delta[:3]
        length=np.linalg.norm(displacement)
        if length>.012:displacement=displacement*.012/length
        env.step({'delta_xyz_m':displacement.tolist(),'delta_yaw_rad':float(np.clip(delta[3],-.1,.1))})
    else:raise RuntimeError('Target motion exceeded bounded action count')
    for _ in range(100):
        actual=np.array(env.observe()['robot']['tcp_position_m'])
        if np.linalg.norm(actual-np.array(position))<.0015:return
        env.advance(.05)
    raise RuntimeError(f'Robot failed to converge: target {position}, measured {actual}')

def travel(env,position):
    current=np.array(env.observe()['robot']['tcp_position_m'])
    move(env,[current[0],current[1],1.025])
    move(env,[position[0],position[1],1.025])
    move(env,position)

def capture(env,out,name,camera='overview',size=(1440,960)):
    obs=env.observe(cameras=(camera,),width=size[0],height=size[1])
    path=out/(name+'.png');Image.fromarray(obs['images'][camera]).save(path)
    return {'path':str(path),'camera':camera,'capture_time_s':obs['capture_time_s']}

def scripted_demo(output,seed=0):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    env=PCBATestCell(seed=seed,asset_dir=out/'assets')
    shots=[];started=time.monotonic()
    try:
        (out/'scene.xml').write_text(env.xml)
        shots.append(capture(env,out,'01-overview'))
        shots.append(capture(env,out,'02-top-down','top'))
        for i in range(BOARD_COUNT):
            for _ in range(400):
                if env.observe()['conveyor']['pickup_ready']:break
                env.advance(.05)
            else:raise RuntimeError('Conveyor failed to present next board')
            if i==0:shots.append(capture(env,out,'03-conveyor-stopped','conveyor_closeup'))
            board=np.array(env.diagnostics()['board_positions_m'][i])
            travel(env,[board[0],board[1],board[2]+.001])
            env.step({'vacuum':True});env.advance(.15)
            if env.held!=i:raise RuntimeError(f'Vacuum failed to attach board {i}')
            move(env,[board[0],board[1],1.025])
            if i==0:shots.append(capture(env,out,'03-pickup'))
            travel(env,[FIXTURE[0],FIXTURE[1],FIXTURE[2]+.001])
            env.step({'vacuum':False});env.advance(.25)
            move(env,[FIXTURE[0],FIXTURE[1],1.025])
            receipt=env.command({'fixture':'close'})
            if not receipt['accepted']:raise RuntimeError(str(receipt))
            env.advance(.3)
            receipt=env.command({'fixture':'start_test'})
            if not receipt['accepted']:raise RuntimeError(str(receipt))
            if i==0:
                shots.append(capture(env,out,'04-fixture-testing','fixture_closeup'))
                shots.append(capture(env,out,'05-wrist-camera','wrist',(960,720)))
            while env.observe()['fixture']['tester_state']=='running':env.advance(.05)
            result=env.observe()['fixture']['result']
            assert result['board_id']==f'PCBA-{i+1:03}'
            receipt=env.command({'fixture':'open'});assert receipt['accepted']
            env.advance(.3)
            board=np.array(env.diagnostics()['board_positions_m'][i])
            move(env,[board[0],board[1],board[2]+.001])
            env.step({'vacuum':True});env.advance(.15)
            if env.held!=i:raise RuntimeError(f'Unload attachment failed for board {i}')
            status=result['status']
            occupied=env.observe()['outputs'][status]['occupied_slots']
            slot=occupied.index(False);goal=OUTPUTS[status][slot]
            if status=='ERROR':
                travel(env,[goal[0],goal[1],goal[2]+.001])
            else:
                approach=[goal[0],.045,goal[2]+.006]
                travel(env,approach)
                move(env,[goal[0],goal[1],goal[2]+.006])
                if slot==1:shots.append(capture(env,out,f'06-{status.lower()}-insertion','racks_closeup'))
            env.step({'vacuum':False});env.advance(.3)
            if status!='ERROR':move(env,approach)
            move(env,[env.target[0],env.target[1],1.025])
            env.advance(.15)
            if i not in env.sorted:raise RuntimeError(f'Board {i} did not settle in destination')
        move(env,[-.02,.05,1.025])
        shots.append(capture(env,out,'06-complete-overview'))
        shots.append(capture(env,out,'07-complete-top-down','top'))
        shots.append(capture(env,out,'08-loaded-magazines','racks_closeup'))
        report=env.diagnostics()
        report.update({'kind':'scripted_oracle_environment_smoke','model_calls':0,
                       'electrical_test':'mock device events, not electrical simulation',
                       'grasp_model':'ideal proximity-gated vacuum weld',
                       'conveyor_model':'contact-gated bounded motor forces; physical edge belts and end stop',
                       'clock_mode':'offline fixed-step development, not realtime policy evaluation',
                       'wall_elapsed_s':time.monotonic()-started,'images':shots})
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in env.events))
        assert len(env.sorted)==BOARD_COUNT and all(r['correct'] for r in env.sorted.values())
        assert not env.dropped and report['finite_state']
        assert not any(report['physics_warning_counts'])
        print(json.dumps({'output':str(out),'sorted':env.sorted,'simulation_seconds':env.data.time,'images':len(shots),'model_calls':0},indent=2))
    except BaseException as exc:
        (out/'failure.json').write_text(json.dumps({'kind':'scripted_oracle_environment_smoke',
            'error':type(exc).__name__,'message':str(exc),'diagnostics':env.diagnostics()},indent=2)+'\n')
        raise
    finally:env.close()

def realtime_smoke(output,duration=2.):
    env=PCBATestCell();out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    # Context/shader/asset initialization is setup, not an online observation.
    env.observe(cameras=('overview','wrist'),width=640,height=480)
    session=RealtimeSession(env).start()
    try:
        before=env.observe()['capture_time_s']
        # Simulate a blocked policy, deliberately without calling env.step().
        time.sleep(duration/2)
        image_obs=env.observe(cameras=('overview','wrist'),width=640,height=480)
        for name,pixels in image_obs['images'].items():Image.fromarray(pixels).save(out/(name+'.png'))
        time.sleep(duration/2)
        after=env.observe()['capture_time_s']
        receipt=env.command({'delta_xyz_m':[.001,0,0]},observed_at_s=before,ttl_s=.1)
        timing=session.timing()
        timing['wall_minus_sim_s']=timing['wall_elapsed_s']-timing['sim_elapsed_s']
        timing['timing_valid']=timing['max_tick_lag_s']<=.02 and abs(timing['wall_minus_sim_s'])<=.05
        report={'kind':'realtime_clock_smoke_zero_model_calls','before_s':before,'after_s':after,
                'time_advanced_without_policy':after-before,'stale_command_receipt':receipt,
                'rendered_cameras_while_physics_running':['overview','wrist'],**timing}
        assert after-before>duration*.8
        assert receipt['accepted'] is False
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:session.close();env.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['demo','realtime-smoke','view'])
    parser.add_argument('--output',type=Path,default=Path('runs')/f'pcba-{time.strftime("%Y%m%dT%H%M%S")}')
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args()
    if args.command=='demo':scripted_demo(args.output,args.seed)
    elif args.command=='realtime-smoke':realtime_smoke(args.output)
    else:
        import mujoco.viewer
        env=PCBATestCell(seed=args.seed)
        session=RealtimeSession(env).start()
        try:
            with mujoco.viewer.launch_passive(env.model,env.data) as viewer:
                viewer.cam.lookat[:]=[0,0,.8];viewer.cam.distance=2.;viewer.cam.azimuth=135;viewer.cam.elevation=-35
                while viewer.is_running():
                    with env.lock:viewer.sync()
                    time.sleep(.02)
        finally:session.close();env.close()

if __name__=='__main__':main()

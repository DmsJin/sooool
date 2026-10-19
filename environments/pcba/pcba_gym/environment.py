"""Physical prototype with an ideal vacuum latch and simulated test equipment.

The controller accepts bounded Cartesian deltas. No grasp/place macro is exposed
to a policy. Exact board poses and unobserved test outcomes are evaluator-only.
"""
from pathlib import Path
import tempfile
import threading
import time
import numpy as np
import mujoco
from .scene import build_scene, BASE, LINKS, TOOL_OFFSET, FIXTURE, INPUTS, OUTPUTS, BOARD_COUNT, CONVEYOR_STOP, CONVEYOR_SPEED


class PCBATestCell:
    control_dt = .05
    instruction = ('Pick each PCBA from the stopped conveyor and test it. Insert PASS boards into '
                   'an empty green magazine slot, FAIL boards into an empty red magazine slot, '
                   'and invalid-test ERROR boards into the amber tray. '
                   'Align before release; never unload a running or clamped fixture. '
                   'Cartesian actions use scene-world axes, metres and radians; +Z is up. '
                   'Each control interval is 0.05 seconds. Translation is limited to '
                   '0.025 metres and yaw to 0.2 radians per command.')

    def __init__(self, seed=0, asset_dir=None, scene_builder=build_scene):
        self.asset_dir=Path(asset_dir or Path(tempfile.gettempdir())/'sooool-pcba-assets-conveyor-v1')
        self.xml=scene_builder(self.asset_dir)
        self.model=mujoco.MjModel.from_xml_string(self.xml)
        self.data=mujoco.MjData(self.model)
        self.lock=threading.RLock()
        self._renderer=None
        self._render_lock=threading.Lock()
        self._render_model=None
        self._initial_eq=self.model.eq_data.copy()
        self.joints=[self.model.joint(n).id for n in ('shoulder_joint','elbow_joint','z_joint','yaw_joint')]
        self.qaddrs=[int(self.model.jnt_qposadr[j]) for j in self.joints]
        self.board_bodies=[self.model.body(f'board{i}').id for i in range(BOARD_COUNT)]
        self.board_qaddrs=[int(self.model.jnt_qposadr[self.model.joint(f'board_joint{i}').id]) for i in range(BOARD_COUNT)]
        self.tcp=self.model.site('tcp').id
        self.reset(seed)

    def inverse_kinematics(self, target):
        x,y,z,yaw=np.asarray(target,float)
        px,py=x-BASE[0],y-BASE[1]; a,b=LINKS
        c=(px*px+py*py-a*a-b*b)/(2*a*b)
        if not -1 <= c <= 1: raise ValueError('Cartesian target outside SCARA reach')
        elbow=np.arccos(c)
        shoulder=np.arctan2(py,px)-np.arctan2(b*np.sin(elbow),a+b*np.cos(elbow))
        reference=float(self.data.qpos[self.qaddrs[0]])
        candidates=[shoulder+k*2*np.pi for k in (-1,0,1)
                    if -6.28<=shoulder+k*2*np.pi<=6.28 and -6.28<=yaw-shoulder-k*2*np.pi-elbow<=6.28]
        if not candidates:raise ValueError('No continuous joint solution inside limits')
        shoulder=min(candidates,key=lambda v:abs(v-reference))
        slide=BASE[2]-.045-TOOL_OFFSET-z
        values=np.array([shoulder,elbow,slide,yaw-shoulder-elbow])
        for j,v in zip(self.joints,values):
            lo,hi=self.model.jnt_range[j]
            if not lo <= v <= hi: raise ValueError('Target exceeds joint limits')
        return values

    def reset(self, seed=0):
        with self.lock:
            if getattr(self,'_realtime_active',False):raise RuntimeError('Stop realtime session before resetting')
            mujoco.mj_resetData(self.model,self.data)
            self.model.eq_data[:]=self._initial_eq
            rng=np.random.default_rng(seed)
            self.seed=seed; self.held=None; self.vacuum=False
            self.clamp='open'; self.tester='idle'; self.result=None
            self._test_deadline=None; self._test_board=None; self._clamped_board=None
            # Private test fixture scenarios, unrelated to board appearance.
            self._outcomes={i:str(v) for i,v in enumerate(rng.permutation(('PASS','FAIL','PASS','FAIL','ERROR')))}
            self._test_duration=float(rng.uniform(1.2,1.8))
            self.test_receipts={};self.sorted={};self.events=[];self.last_receipt=None
            self.score=0.;self.dropped=set();self.rejected=0
            self.conveyor_running=True;self.pickup_ready=False
            self.target=np.array([-.02,.05,1.025,0.])
            q=self.inverse_kinematics(self.target)
            self.data.qpos[self.qaddrs]=q;self.data.ctrl[:4]=q
            for i,address in enumerate(self.board_qaddrs):
                self.data.qpos[address:address+3]=self._initial_board_position(i)+np.r_[rng.uniform(-.002,.002,2),0.]
                angle=float(rng.uniform(-.025,.025))
                self.data.qpos[address+3:address+7]=[np.cos(angle/2),0,0,np.sin(angle/2)]
            mujoco.mj_forward(self.model,self.data)
            for _ in range(100):self._tick()
            self.events=[]
            return self.observe()

    def _initial_board_position(self,i):
        return INPUTS[i]

    def _event(self,kind,**fields):
        self.events.append({'time_s':float(self.data.time),'kind':kind,**fields})

    def _board_position(self,i):
        return self.data.xpos[self.board_bodies[i]].copy()

    def _yaw(self,i):
        m=self.data.xmat[self.board_bodies[i]].reshape(3,3)
        return float(np.arctan2(m[1,0],m[0,0]))

    def _fixture_present(self):
        for i in range(BOARD_COUNT):
            p=self._board_position(i)
            if np.linalg.norm(p[:2]-FIXTURE[:2])<.004 and abs(p[2]-FIXTURE[2])<.004 and abs(self._yaw(i))<.10:
                return i
        return None

    def _weld(self,name,parent,child):
        eid=self.model.equality(name).id
        p1=self.data.xpos[parent];p2=self.data.xpos[child]
        r1=self.data.xmat[parent].reshape(3,3);r2=self.data.xmat[child].reshape(3,3)
        quat=np.empty(4);mujoco.mju_mat2Quat(quat,(r1.T@r2).ravel())
        self.model.eq_data[eid,3:6]=r1.T@(p2-p1)
        self.model.eq_data[eid,6:10]=quat
        self.data.eq_active[eid]=1

    def _conveyor_board(self):
        for i in range(BOARD_COUNT):
            if i==self.held or i in self.sorted:continue
            p=self._board_position(i)
            dof=int(self.model.jnt_dofadr[self.model.joint(f'board_joint{i}').id])
            if np.linalg.norm(p[:2]-CONVEYOR_STOP[:2])<.005 and abs(p[2]-CONVEYOR_STOP[2])<.003 and np.linalg.norm(self.data.qvel[dof:dof+3])<.012:
                return i
        return None

    def _slot_present(self,status,slot,exclude=None):
        # Declared full-depth presence switches; independent of score/test history.
        center=OUTPUTS[status][slot]
        return any(i!=exclude and i!=self.held and
                   np.linalg.norm(self._board_position(i)[:2]-center[:2])<.012 and
                   abs(self._board_position(i)[2]-center[2])<.004
                   for i in range(BOARD_COUNT))

    def _drive_conveyor(self):
        # Idealized motor coupling: force only while a PCB touches an edge belt.
        # Boards remain free bodies; the physical end stop arrests their motion.
        self.pickup_ready=self._conveyor_board() is not None
        self.conveyor_running=not self.pickup_ready
        belts={self.model.geom(f'conveyor_belt{s}').id for s in (-1,1)}
        for i,body in enumerate(self.board_bodies):
            self.data.xfrc_applied[body,:]=0
            if i==self.held or i==self._clamped_board:continue
            slab=self.model.geom(f'board_slab{i}').id
            contact=any((int(c.geom1)==slab and int(c.geom2) in belts) or
                        (int(c.geom2)==slab and int(c.geom1) in belts) for c in self.data.contact[:self.data.ncon])
            if contact:
                dof=int(self.model.jnt_dofadr[self.model.joint(f'board_joint{i}').id])
                velocity=self.data.qvel[dof+1]
                desired=-CONVEYOR_SPEED if self.conveyor_running else 0.
                self.data.xfrc_applied[body,1]=np.clip(2*(desired-velocity),-.16,.16)

    def _tick(self):
        self._drive_conveyor()
        mujoco.mj_step(self.model,self.data)
        self.pickup_ready=self._conveyor_board() is not None
        if self.vacuum and self.held is None:
            tcp=self.data.site_xpos[self.tcp]
            for i in range(BOARD_COUNT):
                if i==self._clamped_board or i in self.sorted:continue
                p=self._board_position(i)
                if np.linalg.norm(tcp[:2]-p[:2])<.006 and -.002<tcp[2]-p[2]-.0008<.005:
                    self._weld(f'grasp{i}',self.model.body('tool').id,self.board_bodies[i])
                    self.held=i;self._event('vacuum_attached',board=f'PCBA-{i+1:03}')
                    break
        clamps=[float(self.data.joint(f'clamp_joint{s}').qpos[0]) for s in (-1,1)]
        if self.clamp=='closing' and min(clamps)>.007:
            self.clamp='closed';self._event('clamp_closed')
        if self.clamp=='opening' and max(clamps)<.001:
            self.clamp='open';self._event('clamp_open')
        if self.tester=='running' and self.data.time>=self._test_deadline:
            i=self._test_board
            self.result={'board_id':f'PCBA-{i+1:03}','status':self._outcomes[i],
                         'test_id':f'T-{len(self.test_receipts)+1:04}',
                         'detail':{'PASS':'simulated checks passed','FAIL':'simulated voltage check failed',
                                   'ERROR':'simulated instrument timeout'}[self._outcomes[i]]}
            self.test_receipts[i]=dict(self.result);self.tester='complete'
            self._event('test_complete',**self.result)
        for i in range(BOARD_COUNT):
            if self._board_position(i)[2]<.60 and i not in self.dropped:
                self.dropped.add(i);self.score-=2;self._event('board_dropped',board=f'PCBA-{i+1:03}')
            if i in self.sorted or i==self.held or i not in self.test_receipts:continue
            p=self._board_position(i)
            for status,slots in OUTPUTS.items():
                for slot,center in enumerate(slots):
                    dof=int(self.model.jnt_dofadr[self.model.joint(f'board_joint{i}').id])
                    settled=np.linalg.norm(self.data.qvel[dof:dof+3])<.025
                    upright=self.data.xmat[self.board_bodies[i]].reshape(3,3)[2,2]>.98
                    slab=self.model.geom(f'board_slab{i}').id
                    if status=='ERROR':
                        supports={self.model.geom('error_base').id}
                    else:
                        supports={self.model.geom(f'{status.lower()}_slot{slot}_rail{s}').id for s in (-1,1)}
                    contacts={int(c.geom2) if int(c.geom1)==slab else int(c.geom1)
                              for c in self.data.contact[:self.data.ncon] if slab in (int(c.geom1),int(c.geom2))}
                    supported=supports.issubset(contacts)
                    occupied=self._slot_present(status,slot,exclude=i)
                    # Full depth, two supporting rails, released and settled are required.
                    if not occupied and np.linalg.norm(p[:2]-center[:2])<.012 and abs(p[2]-center[2])<.004 and settled and upright and supported:
                        correct=status==self.test_receipts[i]['status']
                        self.sorted[i]={'destination':status,'container_type':'tray' if status=='ERROR' else 'magazine','slot':slot,'correct':correct}
                        self.score+=1 if correct else -1
                        self._event('board_sorted',board=f'PCBA-{i+1:03}',**self.sorted[i])
                        break
                if i in self.sorted:break
        color={'idle':[.1,.6,.35,1],'running':[.95,.65,.12,1],'complete':[.1,.6,.35,1]}[self.tester]
        if self.result and self.tester=='complete':
            color={'PASS':[.1,.8,.35,1],'FAIL':[.9,.15,.2,1],'ERROR':[.95,.65,.12,1]}[self.result['status']]
        self.model.geom_rgba[self.model.geom('status_light').id]=color

    def command(self,action,observed_at_s=None,ttl_s=.5):
        with self.lock:
            if observed_at_s is not None:
                if not np.isfinite(observed_at_s) or not np.isfinite(ttl_s) or ttl_s<=0:raise ValueError('Invalid observation time/TTL')
                age=self.data.time-observed_at_s
                if age<-.005 or age>ttl_s:
                    self.rejected+=1;self.last_receipt={'accepted':False,'reason':'stale_or_future_observation','time_s':float(self.data.time)}
                    self._event('command_rejected',reason='stale_or_future_observation')
                    return dict(self.last_receipt)
            allowed={'delta_xyz_m','delta_yaw_rad','vacuum','fixture'}
            if not isinstance(action,dict) or set(action)-allowed:raise ValueError('Unknown action field')
            delta=np.asarray(action.get('delta_xyz_m',[0.,0.,0.]),float)
            yaw=float(action.get('delta_yaw_rad',0.))
            if delta.shape!=(3,) or not np.all(np.isfinite(delta)) or not np.isfinite(yaw):raise ValueError('Non-finite or malformed action')
            if np.linalg.norm(delta)>.025 or abs(yaw)>.2:raise ValueError('Action exceeds per-command motion limit')
            vacuum=action.get('vacuum',self.vacuum)
            if type(vacuum) not in (bool,int) or vacuum not in (0,1):raise ValueError('Vacuum must be boolean')
            fixture=action.get('fixture')
            if fixture not in (None,'close','open','start_test'):raise ValueError('Unknown fixture request')
            target=self.target+np.r_[delta,yaw]
            if not .755<=target[2]<=1.04:raise ValueError('TCP target outside vertical work envelope')
            q=self.inverse_kinematics(target)
            # Check device gates before applying any part of a combined command.
            board=self._fixture_present()
            reason=None
            if fixture=='close' and (self.clamp!='open' or board is None or self.held is not None):reason='board_not_seated_or_fixture_busy'
            if fixture=='start_test' and (self.clamp!='closed' or self.tester=='running' or self._clamped_board is None):reason='fixture_not_ready'
            if fixture=='open' and (self.tester=='running' or self.clamp not in ('closed','open')):reason='tester_busy_or_clamp_moving'
            if reason:
                self.rejected+=1;self.last_receipt={'accepted':False,'reason':reason,'time_s':float(self.data.time)}
                self._event('command_rejected',reason=reason);return dict(self.last_receipt)
            self.target=target;self.data.ctrl[:4]=q
            self.vacuum=bool(vacuum)
            if not self.vacuum and self.held is not None:
                i=self.held;self.data.eq_active[self.model.equality(f'grasp{i}').id]=0
                self.held=None;self._event('vacuum_released',board=f'PCBA-{i+1:03}')
            if fixture=='close':
                self._clamped_board=board
                self._weld(f'fixture_hold{board}',self.model.body('robot_base').id,self.board_bodies[board])
                self.data.ctrl[4:]=.008;self.clamp='closing';self._event('clamp_requested')
            elif fixture=='open':
                if self._clamped_board is not None:
                    self.data.eq_active[self.model.equality(f'fixture_hold{self._clamped_board}').id]=0
                self._clamped_board=None;self.data.ctrl[4:]=0
                if self.clamp!='open':self.clamp='opening'
            elif fixture=='start_test':
                self._test_board=self._clamped_board;self._test_deadline=self.data.time+self._test_duration
                self.tester='running';self.result=None
                self._event('test_started',board=f'PCBA-{self._test_board+1:03}')
            self.last_receipt={'accepted':True,'time_s':float(self.data.time)}
            return dict(self.last_receipt)

    def advance(self,seconds):
        if not np.isfinite(seconds) or seconds<0:raise ValueError('Invalid duration')
        with self.lock:
            if getattr(self,'_realtime_active',False):raise RuntimeError('Use command(), not advance()/step(), during realtime execution')
            for _ in range(round(seconds/self.model.opt.timestep)):self._tick()

    def step(self,action):
        if getattr(self,'_realtime_active',False):raise RuntimeError('Use command() during realtime execution')
        before=self.score;self.command(action);self.advance(self.control_dt)
        terminated=len(self.sorted)==BOARD_COUNT or bool(self.dropped)
        truncated=self.data.time>=240
        return self.observe(),self.score-before,terminated,truncated,{'receipt':self.last_receipt}

    def observe(self,cameras=(),width=640,height=480):
        with self.lock:
            captured=float(self.data.time)
            obs={'task':self.instruction,'capture_time_s':captured,
                 'robot':{'joint_position_rad_m':self.data.qpos[self.qaddrs].tolist(),
                          'tcp_position_m':self.data.site_xpos[self.tcp].tolist(),
                          'tcp_yaw_rad':float(np.arctan2(self.data.xmat[self.model.body('tool').id].reshape(3,3)[1,0],self.data.xmat[self.model.body('tool').id].reshape(3,3)[0,0])),
                          'commanded_tcp_pose_m_rad':self.target.tolist(),
                          'vacuum_on':self.vacuum,'vacuum_ok':self.held is not None,
                          'tool_force_N':self.data.sensor('tool_force').data.copy().tolist()},
                 'fixture':{'board_present':self._fixture_present() is not None,'clamp_state':self.clamp,
                            'tester_state':self.tester,'unload_allowed':self.clamp=='open' and self.tester!='running',
                            'result':dict(self.result) if self.result else None},
                 'conveyor':{'running':self.conveyor_running,'pickup_ready':self.pickup_ready,
                             'speed_m_s':CONVEYOR_SPEED if self.conveyor_running else 0.},
                 'outputs':{status:{'occupied_slots':[self._slot_present(status,slot)
                              for slot in range(len(slots))]} for status,slots in OUTPUTS.items()},
                 'last_action_receipt':dict(self.last_receipt) if self.last_receipt else None}
            if cameras:
                snapshot={k:getattr(self.data,k).copy() for k in ('qpos','qvel','ctrl','eq_active')}
                rgba=self.model.geom_rgba.copy()
        if cameras:
            with self._render_lock:
                if self._renderer is None or (width,height)!=self._render_size:
                    if self._renderer:self._renderer.close()
                    self._render_model=mujoco.MjModel.from_xml_string(self.xml)
                    self._render_data=mujoco.MjData(self._render_model)
                    self._renderer=mujoco.Renderer(self._render_model,height=height,width=width)
                    self._render_size=(width,height)
                for k,v in snapshot.items():getattr(self._render_data,k)[:]=v
                self._render_data.time=captured;self._render_model.geom_rgba[:]=rgba
                mujoco.mj_forward(self._render_model,self._render_data)
                obs['images']={}
                for camera in cameras:
                    self._renderer.update_scene(self._render_data,camera=camera)
                    obs['images'][camera]=self._renderer.render().copy()
        return obs

    def diagnostics(self):
        """Evaluator/oracle access; never pass this result to the policy actor."""
        with self.lock:
            return {'time_s':float(self.data.time),'score':self.score,
                    'board_positions_m':[self._board_position(i).tolist() for i in range(BOARD_COUNT)],
                    'board_yaw_rad':[self._yaw(i) for i in range(BOARD_COUNT)],'held_board':self.held,
                    'sorted':dict(self.sorted),'test_receipts':dict(self.test_receipts),
                    'dropped':sorted(self.dropped),'rejected_commands':self.rejected,
                    'events':list(self.events),
                    'physics_warning_counts':[int(w.number) for w in self.data.warning],
                    'finite_state':bool(all(np.all(np.isfinite(v)) for v in (self.data.qpos,self.data.qvel,self.data.qacc)))}

    def close(self):
        with self._render_lock:
            if self._renderer:self._renderer.close();self._renderer=None


class RealtimeSession:
    """Physics runs independently; rendering and policy waiting do not own its clock.

    Late physics ticks are recorded, not hidden by accelerated catch-up stepping.
    This is a soft realtime prototype, not a hard realtime robot driver.
    """
    def __init__(self,env):
        self.env=env;self._stop=threading.Event();self.thread=None
        self.max_lag_s=0.;self.late_ticks=0;self.wall_started=None;self.sim_started=None

    def start(self):
        if self.thread:raise RuntimeError('Session already started')
        with self.env.lock:
            if getattr(self.env,'_realtime_active',False):raise RuntimeError('Environment already has a realtime session')
            self.env._realtime_active=True
        self.wall_started=time.monotonic();self.sim_started=self.env.data.time
        self.thread=threading.Thread(target=self._run,name='pcba-physics',daemon=True);self.thread.start()
        return self

    def _run(self):
        deadline=time.monotonic();dt=float(self.env.model.opt.timestep)
        while not self._stop.is_set():
            lag=max(0.,time.monotonic()-deadline);self.max_lag_s=max(self.max_lag_s,lag)
            if lag>dt:self.late_ticks+=1
            with self.env.lock:self.env._tick()
            deadline=max(deadline+dt,time.monotonic())
            self._stop.wait(max(0.,deadline-time.monotonic()))

    def timing(self):
        return {'wall_elapsed_s':time.monotonic()-self.wall_started,
                'sim_elapsed_s':float(self.env.data.time-self.sim_started),
                'max_tick_lag_s':self.max_lag_s,'late_ticks':self.late_ticks}

    def close(self):
        self._stop.set()
        if self.thread:self.thread.join(timeout=5)
        with self.env.lock:self.env._realtime_active=False

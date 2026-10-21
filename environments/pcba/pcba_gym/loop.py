"""Recirculating belt variant. Free PCBs, contact-gated ideal belt traction.

The lateral traction term approximates a guided modular belt. It does not rotate
boards into alignment or expose object poses to the actor. Turns are not a
validated friction/contact model of an industrial conveyor.
"""
import xml.etree.ElementTree as ET
import tempfile
from pathlib import Path
import numpy as np
from .scene import build_scene, vec, BOARD_COUNT, font
from .environment import PCBATestCell

CX=-.54
HALF_STRAIGHT=.18
RADIUS=.18
WIDTH=.17
SPEED=.055
LENGTH=4*HALF_STRAIGHT+2*np.pi*RADIUS
DEADLINE=150.
MAX_LAPS=4
PITCH=.03  # belt segment pitch (rad), see build_loop_scene
RIDE_Z=.8008  # board centre height on the belt


def _yaw_pitch_quat(yaw,pitch):
    """Rotate by yaw about world z, then raise the local +x (travel) end by pitch."""
    qz=np.array([np.cos(yaw/2),0,0,np.sin(yaw/2)]);qy=np.array([np.cos(-pitch/2),0,np.sin(-pitch/2),0])
    w1,x1,y1,z1=qz;w2,x2,y2,z2=qy
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2,w1*x2+x1*w2+y1*z2-z1*y2,w1*y2-x1*z2+y1*w2+z1*x2,w1*z2+x1*y2-y1*x2+z1*w2])


def path_at(distance):
    """Counterclockwise racetrack: right straight, top turn, left, bottom turn."""
    s=distance % LENGTH
    if s<2*HALF_STRAIGHT:
        return np.array([CX+RADIUS,-HALF_STRAIGHT+s]),np.array([0.,1.])
    s-=2*HALF_STRAIGHT
    if s<np.pi*RADIUS:
        a=s/RADIUS
        return np.array([CX+RADIUS*np.cos(a),HALF_STRAIGHT+RADIUS*np.sin(a)]),np.array([-np.sin(a),np.cos(a)])
    s-=np.pi*RADIUS
    if s<2*HALF_STRAIGHT:
        return np.array([CX-RADIUS,HALF_STRAIGHT-s]),np.array([0.,-1.])
    a=np.pi+(s-2*HALF_STRAIGHT)/RADIUS
    return np.array([CX+RADIUS*np.cos(a),-HALF_STRAIGHT+RADIUS*np.sin(a)]),np.array([-np.sin(a),np.cos(a)])


def nearest_path(position):
    x,y=position
    if y>HALF_STRAIGHT:
        a=np.clip(np.arctan2(y-HALF_STRAIGHT,x-CX),0,np.pi)
        s=2*HALF_STRAIGHT+a*RADIUS
    elif y<-HALF_STRAIGHT:
        a=np.arctan2(y+HALF_STRAIGHT,x-CX) % (2*np.pi)
        a=np.clip(a,np.pi,2*np.pi)
        s=4*HALF_STRAIGHT+np.pi*RADIUS+(a-np.pi)*RADIUS
    elif x>=CX:s=y+HALF_STRAIGHT
    else:s=2*HALF_STRAIGHT+np.pi*RADIUS+HALF_STRAIGHT-y
    p,t=path_at(s)
    return s % LENGTH,p,t


def build_loop_scene(asset_dir):
    root=ET.fromstring(build_scene(asset_dir));root.set('model','PCBA recirculating test cell')
    # The curved belt has more collision surfaces than the stopped-line cell.
    # Use an explicit 100 Hz physics budget; robot command cadence stays 20 Hz.
    root.find('option').set('timestep','.01')
    from PIL import Image,ImageDraw
    label=Image.new('RGB',(1024,256),'#111d2c');draw=ImageDraw.Draw(label)
    draw.rectangle((0,0,20,255),fill='#38bdf8')
    draw.text((52,34),'01 / LOOP CONVEYOR',font=font(60,True),fill='#38bdf8')
    draw.text((55,142),'CONTINUOUS / TRACK / INTERCEPT',font=font(29),fill='#cad5e2')
    label.save(Path(asset_dir)/'input.png')
    root.find('visual/global').set('offwidth','1920')
    root.find('visual/global').set('offheight','1440')
    world=root.find('worldbody')
    for element in list(world):
        name=element.get('name','')
        if element.tag=='geom' and (name.startswith(('conveyor_','feed_arrow')) or name=='input_label'):world.remove(element)
    world.find("geom[@name='worktop']").set('pos','-.10 0 .72')
    world.find("geom[@name='worktop']").set('size','.86 .52 .03')
    def box(name,position,size,material='dark',yaw=0,physical=True):
        return ET.SubElement(world,'geom',name=name,type='box',pos=vec(position),size=vec(size),material=material,
            euler=vec([0,0,yaw]),contype='1' if physical else '0',conaffinity='1' if physical else '0',
            friction='.02 .001 .0001',priority='1')
    # Overlapping tangential surface segments approximate a modular curved belt.
    n=100
    for k in range(n):
        p,t=path_at((k+.5)*LENGTH/n);a=np.arctan2(t[1],t[0])
        # Sawtooth belt: each overlapping segment pitches up along travel so its entry edge sits
        # below the board while its exit edge carries it at the original 0.800 m top. Coplanar
        # segments let a slightly sunk slab catch the next segment's end face and stall.
        half=LENGTH/n*.56
        seg=box(f'loop_belt{k}',[*p,.797-half*np.sin(PITCH)],[half,WIDTH/2,.003],yaw=a)
        del seg.attrib['euler'];seg.set('quat',vec(_yaw_pitch_quat(a,PITCH)))
        normal=np.array([t[1],-t[0]])
        for side in (-1,1):
            q=p+normal*side*(WIDTH/2+.012)
            box(f'loop_edge{k}_{side}',[*q,.807],[LENGTH/n*.56,.006,.012],'blue',a)
        if k%5==0:
            box(f'loop_mark{k}',[*p,.8002],[.004,.026,.00015],'metal',a,False)
    box('input_label',[-.56,-.45,.752],[.19,.027,.001],'input_mat',physical=False)
    # Pick zone is marked, but there is no stopper or global pause command.
    for y in (-.14,.14):box(f'pick_boundary{y}',[-.36,y,.8004],[WIDTH/2,.002,.0002],'amber',physical=False)
    camera=world.find("camera[@name='conveyor_closeup']")
    camera.set('pos','-1.16 -.65 1.6')
    for i in range(BOARD_COUNT):
        p,_=path_at(i*LENGTH/BOARD_COUNT)
        world.find(f"body[@name='board{i}']").set('pos',vec([*p,.8008]))
    return ET.tostring(root,encoding='unicode')


class PCBALoopCell(PCBATestCell):
    instruction=('Pick skewed PCBs from the continuously circulating racetrack belt. '
        'Use the marked right straight pick zone, correct position and yaw, load the fixture, '
        'test and sort PASS/FAIL/ERROR into the matching containers. '
        'The belt never pauses for inference; a missed board returns on the next lap. '
        'Finish within 150 simulation seconds and before four full unpicked laps. '
        'No exact board poses are provided. Follow the same bounded Cartesian action interface.')

    def __init__(self,seed=0,asset_dir=None):
        self._belt_ids=None
        asset_dir=asset_dir or Path(tempfile.gettempdir())/'sooool-pcba-assets-loop-v1'
        super().__init__(seed,asset_dir,scene_builder=build_loop_scene)

    def _initial_board_position(self,i):
        p,_=path_at((i+.12)*LENGTH/BOARD_COUNT)
        return np.r_[p,.8008]

    def reset(self,seed=0):
        # Parent reset settles the old input arrangement; loop bookkeeping begins
        # only after reseeding boards on the new belt, before any actor sees them.
        self._loop_ready=False;self._belt_phase={}
        super().reset(seed)
        rng=np.random.default_rng(seed+710)
        self._belt_ids={self.model.geom(f'loop_belt{k}').id for k in range(100)}
        self._slab_ids={self.model.geom(f'board_slab{i}').id:i for i in range(BOARD_COUNT)}
        self._belt_mask=np.zeros(self.model.ngeom,dtype=bool)
        self._belt_mask[list(self._belt_ids)]=True
        self._slab_index=np.full(self.model.ngeom,-1,dtype=int)
        for slab,i in self._slab_ids.items():self._slab_index[slab]=i
        self._dofs=[int(self.model.jnt_dofadr[self.model.joint(f'board_joint{i}').id]) for i in range(BOARD_COUNT)]
        self._lane_offsets=rng.uniform(-.021,.021,BOARD_COUNT)
        self._distance=np.zeros(BOARD_COUNT);self._last_s=np.zeros(BOARD_COUNT)
        self._misses=np.zeros(BOARD_COUNT,dtype=int);self._expired=set();self._contact_boards=set()
        import mujoco
        for i,address in enumerate(self.board_qaddrs):
            s=(i+.12)*LENGTH/BOARD_COUNT;p,t=path_at(s)
            p+=np.array([t[1],-t[0]])*self._lane_offsets[i]
            yaw=float(rng.uniform(-.60,.60))
            self.data.qpos[address:address+3]=[*p,.8008]
            self.data.qpos[address+3:address+7]=[np.cos(yaw/2),0,0,np.sin(yaw/2)]
            self.data.qvel[self._dofs[i]:self._dofs[i]+6]=0
            self._last_s[i]=s
        self._loop_ready=True
        mujoco.mj_forward(self.model,self.data)
        self._loop_started=float(self.data.time)
        for _ in range(50):self._tick()
        self.events=[];self.dropped=set();self.score=0
        return self.observe()

    def _drive_conveyor(self):
        self.conveyor_running=True;self.pickup_ready=False
        self._contact_boards=set()
        for body in self.board_bodies:self.data.xfrc_applied[body,:]=0
        if not getattr(self,'_loop_ready',False):return
        # A board is on the belt when it lies within the belt footprint at belt height. This is
        # geometric rather than contact-based so a momentary hop does not drop it from the belt.
        for i in range(BOARD_COUNT):
            if i==self.held or i==self._clamped_board or i in self.sorted:continue
            p=self._board_position(i);_,center,t=nearest_path(p[:2])
            if abs(float((p[:2]-center)@np.array([t[1],-t[0]])))<WIDTH/2 and .790<p[2]<.815:self._contact_boards.add(i)
        phases=getattr(self,'_belt_phase',{});self._belt_phase={};dt=float(self.model.opt.timestep)
        for i in self._contact_boards:
            if i==self.held or i==self._clamped_board or i in self.sorted:continue
            p=self._board_position(i);s,center,t=nearest_path(p[:2]);n=np.array([t[1],-t[0]])
            # Conveyor model: a supported board takes the belt's surface velocity directly, as a
            # rigid modular belt would carry it. Force-driven thin slabs on segmented boxes could
            # snag on a seam or wedge between segments and stall indefinitely. Vertical support,
            # tilt and collisions remain physical. Each board keeps its own point on a virtual
            # belt, so spacing stays constant; a blocked board lags at most 10 mm.
            phase=phases.get(i,s);lag=float(np.clip((phase-s+LENGTH/2)%LENGTH-LENGTH/2,-.01,.01))
            self._belt_phase[i]=(s+lag+SPEED*dt)%LENGTH
            curve=abs(p[1])>HALF_STRAIGHT
            scale=np.linalg.norm(p[:2]-[CX,np.sign(p[1])*HALF_STRAIGHT])/RADIUS if curve else 1.
            # Weak radial correction keeps the random lane offset; no yaw servo.
            lateral=float((p[:2]-center)@n)-self._lane_offsets[i]
            dof=self._dofs[i];self.data.qvel[dof:dof+2]=(SPEED*scale+lag)*t-2*lateral*n
            # The belt is one flat surface: hold the board at ride height and level (no hopping or
            # pitching on segment seams). Yaw is never servoed; on the curves the board turns
            # with the belt (counter-clockwise), keeping its random skew.
            R=self.data.xmat[self.board_bodies[i]].reshape(3,3);level=np.cross(R[:,2],[0.,0.,1.])
            self.data.qvel[dof+2]=-20*(p[2]-RIDE_Z)
            w=np.array([20*level[0],20*level[1],SPEED/RADIUS if curve else 0.]);self.data.qvel[dof+3:dof+6]=R.T@w
            ds=(s-self._last_s[i]+LENGTH/2)%LENGTH-LENGTH/2
            if abs(ds)<.03:self._distance[i]+=max(0.,ds)
            self._last_s[i]=s
            if abs(p[0]-(CX+RADIUS))<WIDTH/2 and -.14<p[1]<.14:self.pickup_ready=True

    def _conveyor_board(self):
        # Parent uses this switch only; never return hidden poses as observation.
        if not getattr(self,'_loop_ready',False):return None
        for i in getattr(self,'_contact_boards',()):
            if i==self.held:continue
            p=self._board_position(i)
            if abs(p[0]-(CX+RADIUS))<WIDTH/2 and -.14<p[1]<.14:return i
        return None

    def _tick(self):
        super()._tick()
        if not getattr(self,'_loop_ready',False):return
        for i in range(BOARD_COUNT):
            laps=int(self._distance[i]/LENGTH)
            if laps>self._misses[i]:
                self._misses[i]=laps;self._event('unpicked_lap',board=f'PCBA-{i+1:03}',laps=laps)
            if i not in self.sorted and i not in self._expired and (laps>=MAX_LAPS or self.data.time-self._loop_started>=DEADLINE):
                self._expired.add(i);self._event('board_deadline_missed',board=f'PCBA-{i+1:03}')

    def observe(self,*args,**kwargs):
        obs=super().observe(*args,**kwargs)
        obs['conveyor']={'layout':'recirculating_racetrack','running':True,'pickup_ready':self.pickup_ready,
            'speed_m_s':SPEED,'nominal_lap_s':LENGTH/SPEED,'maximum_unpicked_laps':MAX_LAPS,
            'batch_deadline_s':DEADLINE,'batch_elapsed_s':max(0.,obs['capture_time_s']-getattr(self,'_loop_started',obs['capture_time_s'])),
            'pick_zone_reference_m':{'x':CX+RADIUS,'y_min':-.14,'y_max':.14,'substrate_z':.8008}}
        return obs

    def diagnostics(self):
        d=super().diagnostics()
        d['loop']={'distance_m':self._distance.tolist(),'unpicked_laps':self._misses.tolist(),
            'deadline_missed':sorted(self._expired),'all_on_time':len(self.sorted)==BOARD_COUNT and not self._expired and all(s['correct'] for s in self.sorted.values())}
        return d

    def step(self,action):
        obs,reward,terminated,truncated,info=super().step(action)
        return obs,reward,terminated,truncated or bool(self._expired),info

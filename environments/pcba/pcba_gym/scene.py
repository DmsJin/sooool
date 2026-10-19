"""Original procedural workcell assets, in metres; no third-party CAD required."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TABLE_Z = .75
LINKS = (.42, .36)
BASE = np.array([0., .35, 1.16])
TOOL_OFFSET = .15
FIXTURE = np.array([0., -.08, .7908])
CONVEYOR_STOP = np.array([-.50, -.2225, .8008])
CONVEYOR_SPEED = .05
INPUTS = [np.array([-.50, y, .8008]) for y in (-.15, -.015, .12, .255, .39)]
OUTPUTS = {"PASS": [np.array([.29, .21, z]) for z in (.8008, .8808, .9608)],
           "FAIL": [np.array([.57, .21, z]) for z in (.8008, .8808, .9608)],
           "ERROR": [np.array([x, -.26, .767]) for x in (.36, .48)]}
BOARD_COUNT = len(INPUTS)

def font(size, bold=False):
    try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf', size)
    except OSError:return ImageFont.load_default(size=size)

def make_assets(directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    for name, title, subtitle, color in [
        ('input', '01 / CONVEYOR', 'STOP / PICK / FEED', '#38bdf8'),
        ('pass', '03 / PASS', 'GOOD / MAGAZINE', '#4ade80'),
        ('fail', '04 / FAIL', 'REPAIR / MAGAZINE', '#fb7185'),
        ('error', '05 / HOLD', 'INVALID TEST / REVIEW', '#fbbf24'),
        ('fixture', '02 / TEST FIXTURE', 'ALIGN / CLAMP / TEST', '#a78bfa'),
        ('title', 'PCBA / TEST CELL', 'MUJOCO   |   ENVIRONMENT PROTOTYPE', '#93c5fd'),
        ('screen', 'AUTOMATED TEST', 'SIMULATED DEVICE / STATUS LIGHT', '#67e8f9')]:
        image = Image.new('RGB', (1024, 256), '#111d2c'); d=ImageDraw.Draw(image)
        d.rectangle((0,0,20,255),fill=color)
        d.text((52,34), title, font=font(62,True),fill=color)
        d.text((55,142), subtitle, font=font(29),fill='#cad5e2')
        image.save(directory/(name+'.png'))
    for i in range(BOARD_COUNT):
        image=Image.new('RGB',(880,600),'#075344'); d=ImageDraw.Draw(image)
        rng=np.random.default_rng(30+i)
        for _ in range(65):
            x,y=rng.integers([35,35],[845,565]); dx,dy=rng.integers(-100,100,size=2)
            d.line([(int(x),int(y)),(int(x+dx),int(y)),(int(x+dx),int(y+dy))],fill='#209879',width=3)
        for x,y in [(40,40),(840,40),(40,560),(840,560)]:
            d.ellipse((x-18,y-18,x+18,y+18),fill='#dfc67f')
            d.ellipse((x-9,y-9,x+9,y+9),fill='#102028')
        d.rounded_rectangle((180,400,700,510),radius=8,outline='#bddbd0',width=3)
        d.text((245,420),f'PCBA  /  {i+1:03}',font=font(42,True),fill='#e8f5ed')
        d.text((650,68),'USB',font=font(30),fill='white')
        image.save(directory/f'board{i}.png')

def vec(v):
    return ' '.join(f'{float(x):.7g}' for x in v)

def build_scene(asset_dir):
    make_assets(asset_dir)
    root=ET.Element('mujoco',model='PCBA test and sorting cell')
    ET.SubElement(root,'compiler',angle='radian',autolimits='true')
    ET.SubElement(root,'option',timestep='.005',integrator='implicitfast',gravity='0 0 -9.81',iterations='40')
    visual=ET.SubElement(root,'visual')
    ET.SubElement(visual,'global',offwidth='1600',offheight='1200',azimuth='135',elevation='-35')
    ET.SubElement(visual,'quality',shadowsize='2048',offsamples='4')
    ET.SubElement(visual,'headlight',ambient='.25 .25 .25',diffuse='.4 .4 .4',specular='.2 .2 .2')
    ET.SubElement(visual,'rgba',haze='.15 .19 .24 1')
    asset=ET.SubElement(root,'asset')
    ET.SubElement(asset,'texture',type='skybox',builtin='gradient',rgb1='.18 .24 .32',rgb2='.04 .07 .11',width='512',height='3072')
    ET.SubElement(asset,'texture',name='floor_tex',type='2d',builtin='checker',rgb1='.16 .19 .23',rgb2='.19 .22 .26',width='512',height='512')
    ET.SubElement(asset,'material',name='floor',texture='floor_tex',texrepeat='6 6',reflectance='.1')
    materials={'table':'.47 .54 .61 1','dark':'.07 .10 .14 1','robot':'.87 .90 .93 1',
               'joint':'.16 .24 .32 1','metal':'.65 .72 .79 1','gold':'.85 .65 .25 1',
               'blue':'.08 .43 .74 1','green':'.1 .62 .37 1','red':'.77 .18 .27 1','amber':'.9 .56 .12 1'}
    for name,rgba in materials.items():
        ET.SubElement(asset,'material',name=name,rgba=rgba,specular='.4',shininess='.35')
    for name in ['input','pass','fail','error','fixture','title','screen']+[f'board{i}' for i in range(BOARD_COUNT)]:
        ET.SubElement(asset,'texture',name=name+'_tex',type='2d',file=str(Path(asset_dir)/(name+'.png')))
        ET.SubElement(asset,'material',name=name+'_mat',texture=name+'_tex',texuniform='false',specular='.15',shininess='.1')
    world=ET.SubElement(root,'worldbody')
    def geom(parent,name,pos,size,material='dark',kind='box',physical=True,**kw):
        a=dict(name=name,type=kind,pos=vec(pos),size=vec(size),material=material,
               contype='1' if physical else '0',conaffinity='1' if physical else '0',friction='.8 .01 .001')
        a.update(kw); return ET.SubElement(parent,'geom',**a)
    geom(world,'floor',(0,0,0),(3,3,.1),'floor','plane')
    geom(world,'worktop',(0,0,.72),(.76,.52,.03),'table')
    geom(world,'front_rail',(0,-.515,.69),(.76,.018,.025),'joint')
    for x in (-.66,.66):
        for y in (-.43,.43): geom(world,f'leg_{x}_{y}',(x,y,.34),(.035,.035,.34),'metal')
    geom(world,'back_panel',(0,.515,.87),(.76,.012,.12),'joint')
    geom(world,'cell_title',(-.35,.494,.89),(.32,.08,.001),'title_mat',physical=False,euler='1.570796 0 0')
    for name,pos,target in [
        ('overview',(1.28,-1.55,1.90),(0,.02,.87)),
        ('top',(0,-.02,2.35),(0,-.02,.75)),
        ('fixture_closeup',(.30,-.55,1.20),(0,-.08,.80)),
        ('conveyor_closeup',(-1.0,-.65,1.45),(-.50,.01,.80)),
        ('racks_closeup',(.95,-.57,1.38),(.43,.21,.90))]:
        z=np.array(pos)-target;z/=np.linalg.norm(z)
        up=np.array([0.,1.,0.]) if name=='top' else np.array([0.,0.,1.])
        x=np.cross(up,z);x/=np.linalg.norm(x);y=np.cross(z,x)
        ET.SubElement(world,'camera',name=name,pos=vec(pos),xyaxes=vec(np.r_[x,y]),fovy='43')
    ET.SubElement(world,'light',name='key',pos='-.7 -.4 2.7',dir='.2 .1 -1',diffuse='.65 .65 .65',castshadow='true')
    ET.SubElement(world,'light',name='fill',pos='1 .5 2.1',dir='-.3 -.1 -1',diffuse='.25 .3 .4',castshadow='false')
    def tray(name,x,y,hx,hy,mat):
        geom(world,name+'_base',(x,y,.758),(hx,hy,.008),'dark')
        for side in (-1,1):
            geom(world,f'{name}_rim_x{side}',(x+side*hx,y,.776),(.006,hy,.018),mat)
            geom(world,f'{name}_rim_y{side}',(x,y+side*hy,.776),(hx,.006,.018),mat)
        geom(world,name+'_label',(x,y-hy-.026,.752),(hx,.022,.001),name+'_mat',physical=False)
    # Narrow edge belts support PCBs without touching their components.
    geom(world,'conveyor_chassis',(-.50,.10,.765),(.085,.40,.025),'joint')
    for side in (-1,1):
        geom(world,f'conveyor_belt{side}',(-.50+side*.049,.10,.797),(.005,.40,.003),'dark',friction='.03 .001 .0001',priority='1')
        geom(world,f'conveyor_rail{side}',(-.50+side*.064,.10,.814),(.005,.40,.014),'blue')
        for k,z in enumerate((.762,.78)):
            geom(world,f'conveyor_trim{side}_{k}',(-.50+side*.08,.10,z),(.003,.40,.004),'metal',physical=False)
    geom(world,'conveyor_stop',(-.50,-.270,.816),(.060,.010,.016),'metal')
    geom(world,'conveyor_sensor',(-.588,-.222,.817),(.014,.014,.014),'blue',physical=False)
    geom(world,'conveyor_sensor_lens',(-.572,-.222,.817),(.002,.006,.006),'amber',physical=False)
    geom(world,'input_label',(-.50,-.338,.752),(.13,.027,.001),'input_mat',physical=False)
    for k,y in enumerate((-.12,.02,.16,.30,.44)):
        geom(world,f'feed_arrow{k}',(-.50,y,.801),(.012,.016,.0002),'blue',physical=False,euler='0 0 .785398')
    # Three open-front horizontal slots; a pair of rails supports board edges.
    for status,mat in [('PASS','green'),('FAIL','red')]:
        name=status.lower();x=OUTPUTS[status][0][0];y=.21
        geom(world,name+'_rack_foot',(x,y,.765),(.084,.10,.015),'joint')
        geom(world,name+'_rack_back',(x,.307,.897),(.073,.006,.132),mat)
        for side in (-1,1):
            geom(world,f'{name}_rack_wall{side}',(x+side*.071,y,.897),(.005,.09,.132),mat)
            geom(world,f'{name}_rack_post{side}',(x+side*.071,.115,.897),(.006,.006,.132),'metal')
        for slot,center in enumerate(OUTPUTS[status]):
            for side in (-1,1):
                geom(world,f'{name}_slot{slot}_rail{side}',(x+side*.054,y,center[2]-.0038),(.008,.09,.003),'metal')
        geom(world,name+'_label',(x,.079,.752),(.10,.024,.001),name+'_mat',physical=False)
    tray('error',.43,-.26,.152,.072,'amber')
    geom(world,'error_divider',(.43,-.26,.769),(.003,.065,.003),'joint')
    geom(world,'fixture_base',(0,-.08,.765),(.105,.082,.015),'joint')
    geom(world,'fixture_bed',(0,-.08,.785),(.057,.042,.005),'dark')
    geom(world,'fixture_label',(0,-.205,.752),(.12,.024,.001),'fixture_mat',physical=False)
    for ix,x in enumerate((-.058,.058)):
        for iy,y in enumerate((-.122,-.038)):
            geom(world,f'guide_{ix}_{iy}',(x,y,.793),(.003,.003,.013),'metal','cylinder')
    for ix,x in enumerate(np.linspace(-.04,.04,8)):
        for iy,y in enumerate((-.105,-.06)):
            geom(world,f'probe_{ix}_{iy}',(x,y,.7905),(.0012,.0015),'gold','cylinder',physical=False)
    for side in (-1,1):
        b=ET.SubElement(world,'body',name=f'clamp{side}',pos=vec([side*.075,-.08,.796]))
        ET.SubElement(b,'joint',name=f'clamp_joint{side}',type='slide',axis=vec([-side,0,0]),range='0 .015',damping='6')
        geom(b,f'clamp_pad{side}',(0,0,0),(.012,.022,.006),'blue',mass='.1')
    geom(world,'tester_stand',(.47,.405,.96),(.012,.012,.21),'metal')
    geom(world,'tester_screen',(.47,.39,1.145),(.13,.012,.07),'dark')
    geom(world,'tester_display',(.47,.376,1.145),(.12,.055,.001),'screen_mat',physical=False,euler='1.570796 0 0')
    geom(world,'status_light',(.64,.39,1.15),(.018,.035),'green','cylinder',physical=False)
    base=ET.SubElement(world,'body',name='robot_base',pos=vec(BASE))
    geom(base,'robot_pedestal',(0,0,-.29),(.085,.085,.12),'joint')
    geom(base,'robot_column',(0,0,-.13),(.055,.13),'robot','cylinder')
    shoulder=ET.SubElement(base,'body',name='shoulder',gravcomp='1')
    ET.SubElement(shoulder,'joint',name='shoulder_joint',type='hinge',axis='0 0 1',range='-6.28 6.28',damping='5',armature='.1')
    geom(shoulder,'shoulder_cap',(0,0,.012),(.065,.037),'blue','cylinder',mass='1.5')
    geom(shoulder,'upper_arm',(.21,0,0),(.21,.046,.028),'robot',mass='2')
    elbow=ET.SubElement(shoulder,'body',name='elbow',pos='.42 0 0',gravcomp='1')
    ET.SubElement(elbow,'joint',name='elbow_joint',type='hinge',axis='0 0 1',range='-2.95 2.95',damping='4',armature='.1')
    geom(elbow,'elbow_cap',(0,0,-.012),(.052,.045),'joint','cylinder',mass='1')
    geom(elbow,'forearm',(.18,0,-.045),(.18,.035,.022),'robot',mass='1.2')
    slide=ET.SubElement(elbow,'body',name='slide',pos='.36 0 -.045',gravcomp='1')
    ET.SubElement(slide,'joint',name='z_joint',type='slide',axis='0 0 -1',range='-.08 .27',damping='12',armature='.05')
    geom(slide,'vertical_rail',(0,0,.06),(.018,.12),'metal','cylinder',mass='.4')
    tool=ET.SubElement(slide,'body',name='tool',gravcomp='1')
    ET.SubElement(tool,'joint',name='yaw_joint',type='hinge',axis='0 0 1',range='-6.28 6.28',damping='1',armature='.01')
    geom(tool,'vacuum_head',(0,0,-.07),(.035,.025,.035),'joint',mass='.15',physical=False)
    geom(tool,'vacuum_bar',(0,0,-.125),(.043,.018,.01),'blue',mass='.05',physical=False)
    for side in (-1,1):
        geom(tool,f'vacuum_cup{side}',(side*.033,0,-.144),(.008,.006),'dark','cylinder',mass='.005',physical=False)
    ET.SubElement(tool,'site',name='tcp',pos='0 0 -.15',size='.002',rgba='0 0 0 0')
    ET.SubElement(tool,'site',name='tool_sensor',pos='0 0 0',size='.002',rgba='0 0 0 0')
    ET.SubElement(tool,'camera',name='wrist',pos='0 -.09 -.02',xyaxes='1 0 0 0 1 0',fovy='65')
    for i,p in enumerate(INPUTS):
        body=ET.SubElement(world,'body',name=f'board{i}',pos=vec(p))
        ET.SubElement(body,'freejoint',name=f'board_joint{i}')
        geom(body,f'board_slab{i}',(0,0,0),(.055,.0375,.0008),f'board{i}_mat',mass='.045')
        for k,(x,y,sx,sy) in enumerate([(-.020,.012,.012,.012),(.017,.012,.007,.010),(.037,-.012,.006,.009)]):
            geom(body,f'chip{i}_{k}',(x,y,.003),(sx,sy,.0022),'dark',physical=False,mass='.002')
            for pin in (-1,1): geom(body,f'ic_pins{i}_{k}_{pin}',(x+pin*(sx+.001),y,.002),(.001,sy,.0005),'metal',physical=False)
        geom(body,f'usb{i}',(.047,.020,.004),(.010,.008,.004),'metal',physical=False,mass='.008')
        geom(body,f'usb_inset{i}',(.0571,.020,.004),(.0003,.006,.002),'dark',physical=False)
        for k in range(6):
            geom(body,f'resistor{i}_{k}',(-.035+k*.011,-.023,.0018),(.003,.0015,.001),'metal',physical=False)
        for k in range(4):
            geom(body,f'header{i}_{k}',(-.044,-.015+k*.009,.004),(.002,.002,.004),'gold','cylinder',physical=False)
    eq=ET.SubElement(root,'equality')
    for i in range(BOARD_COUNT):
        ET.SubElement(eq,'weld',name=f'grasp{i}',body1='tool',body2=f'board{i}',active='false',solref='.012 1')
        ET.SubElement(eq,'weld',name=f'fixture_hold{i}',body1='robot_base',body2=f'board{i}',active='false',solref='.012 1')
    actuators=ET.SubElement(root,'actuator')
    for joint,kp,kv,force in [('shoulder_joint',700,55,160),('elbow_joint',600,45,120),('z_joint',2400,110,180),('yaw_joint',90,10,30)]:
        ET.SubElement(actuators,'position',name=joint+'_servo',joint=joint,kp=str(kp),kv=str(kv),forcerange=f'-{force} {force}')
    for side in (-1,1): ET.SubElement(actuators,'position',name=f'clamp_servo{side}',joint=f'clamp_joint{side}',kp='1500',kv='30',ctrlrange='0 .015',forcerange='-40 40')
    sensors=ET.SubElement(root,'sensor')
    ET.SubElement(sensors,'force',name='tool_force',site='tool_sensor')
    ET.SubElement(sensors,'torque',name='tool_torque',site='tool_sensor')
    return ET.tostring(root,encoding='unicode')

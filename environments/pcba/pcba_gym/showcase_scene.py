"""Render-only dressing of a retained PCBA scene.xml for showcase exports.

Only materials, lights and static decorative geoms change. Every added geom
belongs to the world body, has no joint and no collision, so nq/nv, equality
constraints and recorded qpos replay exactly as captured.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from .scene import vec
from .showcase_art import make_showcase_art

# Table footprint of the loop cell (worktop centre x=-.10, half extents .86 x .52).
TX0, TX1, TY0, TY1 = -.96, .76, -.52, .52


def skin_scene(scene_xml, art_dir):
    art = Path(art_dir)
    if not (art / '.done').exists():
        make_showcase_art(art); (art / '.done').write_text('ok\n')
    root = ET.parse(scene_xml).getroot()
    vis = root.find('visual')
    vis.find('quality').set('shadowsize', '2048'); vis.find('quality').set('offsamples', '4')
    vis.find('headlight').attrib.update(ambient='.16 .17 .19', diffuse='.22 .22 .22', specular='.1 .1 .1')
    rgba = vis.find('rgba'); rgba.set('haze', '.10 .12 .15 1'); rgba.set('fog', '.07 .085 .10 1')
    ET.SubElement(vis, 'map', znear='.01')

    asset = root.find('asset')
    for t in asset.findall('texture'):
        if t.get('type') == 'skybox':
            t.attrib.update(rgb1='.10 .12 .15', rgb2='.03 .04 .06')
        name = t.get('name', '')
        if name.startswith('board') and name.endswith('_tex'):
            t.set('file', str(art / (name[:-4] + '.png')))
        if name == 'floor_tex':
            t.attrib.clear(); t.attrib.update(name='floor_tex', type='2d', file=str(art / 'floor.png'))
    for name, file in [('esd', 'esd.png'), ('steel', 'steel.png'), ('steel_dark', 'steel_dark.png'),
                       ('belt', 'belt.png'), ('wall', 'wall.png'), ('hazard', 'hazard.png'),
                       ('sign_cell', 'sign_cell.png'), ('sign_esd', 'sign_esd.png'), ('sign_robot', 'sign_robot.png')]:
        ET.SubElement(asset, 'texture', name=name + '_tex', type='2d', file=str(art / file))
    mats = {m.get('name'): m for m in asset.findall('material')}
    mats['floor'].attrib.update(texrepeat='2 2', reflectance='.22', specular='.3', shininess='.5')
    def material(name, **kw):
        kw.setdefault('specular', '.3'); kw.setdefault('shininess', '.4')
        ET.SubElement(asset, 'material', name=name, **kw)
    material('esd_mat', texture='esd_tex', texrepeat='3 2', specular='.15', shininess='.15')
    material('steel_mat', texture='steel_tex', texuniform='true', texrepeat='4 4', specular='.7', shininess='.7', reflectance='.08')
    material('steel_dark_mat', texture='steel_dark_tex', texuniform='true', texrepeat='4 4', specular='.5', shininess='.6')
    material('belt_mat', texture='belt_tex', texuniform='true', texrepeat='12 12', specular='.25', shininess='.3')
    material('wall_mat', texture='wall_tex', texrepeat='1 1', specular='.05', shininess='.05')
    material('hazard_mat', texture='hazard_tex', texrepeat='1 1', specular='.1', shininess='.1')
    for s in ('sign_cell', 'sign_esd', 'sign_robot'):
        material(s + '_mat', texture=s + '_tex', specular='.1', shininess='.1')
    material('yellow', rgba='.96 .77 .09 1', specular='.4')
    material('safety_orange', rgba='.95 .45 .10 1', specular='.4')
    material('mesh', rgba='.42 .48 .56 .28', specular='.2')
    material('lamp', rgba='1 .97 .9 1', emission='1')
    material('bin_blue', rgba='.12 .33 .62 1', specular='.3')
    material('reel', rgba='.55 .58 .62 1', specular='.5')
    material('reel_dark', rgba='.12 .13 .15 1', specular='.5')
    material('cabinet', rgba='.80 .82 .84 1', specular='.4', shininess='.4')
    material('screen_glow', rgba='.25 .65 .95 1', emission='.6')
    material('stack_red', rgba='.55 .08 .08 1', emission='.0')
    material('stack_amber', rgba='.55 .38 .05 1', emission='.0')
    material('stack_green', rgba='.08 .45 .18 1', emission='.0')
    # Existing research materials: crisper robot paint and graphite joints.
    mats['robot'].attrib.update(rgba='.93 .94 .95 1', specular='.7', shininess='.8', reflectance='.05')
    mats['joint'].attrib.update(rgba='.13 .15 .18 1', specular='.5', shininess='.6')
    mats['metal'].attrib.update(specular='.8', shininess='.8')
    mats['blue'].attrib.update(rgba='.10 .45 .85 1', specular='.6', shininess='.7')

    world = root.find('worldbody')
    for g in list(world):
        name = g.get('name', '')
        if g.tag == 'geom' and name.startswith('loop_mark'):
            world.remove(g)  # replaced by animated chevrons drawn at render time
        elif g.tag == 'geom' and name.startswith('loop_belt'):
            g.set('material', 'belt_mat')
        elif g.tag == 'geom' and name == 'worktop':
            g.set('material', 'esd_mat')
        elif g.tag == 'geom' and name.startswith('leg_'):
            g.set('material', 'steel_dark_mat')
        elif g.tag == 'geom' and name in ('front_rail', 'back_panel'):
            g.set('material', 'steel_dark_mat')
    for light in world.findall('light'):
        world.remove(light)
    ET.SubElement(world, 'light', name='key', pos='-.9 -1.1 3.0', dir='.25 .35 -1', diffuse='.75 .72 .66',
                  specular='.35 .35 .35', castshadow='true', cutoff='60', exponent='4')
    ET.SubElement(world, 'light', name='rim', pos='1.6 1.4 2.4', dir='-.6 -.5 -.7', diffuse='.25 .32 .45',
                  specular='.2 .2 .3', castshadow='false')
    ET.SubElement(world, 'light', name='bench', pos='-.1 0 2.0', dir='0 0 -1', diffuse='.35 .35 .35',
                  castshadow='false', cutoff='50', exponent='8')

    n = [0]
    def geom(pos, size, material, kind='box', **kw):
        n[0] += 1
        a = dict(name=f'show_{n[0]}', type=kind, pos=vec(pos), size=vec(size), material=material,
                 contype='0', conaffinity='0', group='1')
        a.update({k: (vec(v) if isinstance(v, (list, tuple, np.ndarray)) else str(v)) for k, v in kw.items()})
        return ET.SubElement(world, 'geom', **a)

    # Hazard tape frames the cell on the floor.
    m = .22
    x0, x1, y0, y1 = TX0 - m, TX1 + m, TY0 - m, TY1 + m
    geom(((x0 + x1) / 2, y0, .0012), ((x1 - x0) / 2, .03, .001), 'hazard_mat')
    geom(((x0 + x1) / 2, y1, .0012), ((x1 - x0) / 2, .03, .001), 'hazard_mat')
    geom((x0, (y0 + y1) / 2, .0012), ((y1 - y0) / 2, .03, .001), 'hazard_mat', euler=(0, 0, np.pi / 2))
    geom((x1, (y0 + y1) / 2, .0012), ((y1 - y0) / 2, .03, .001), 'hazard_mat', euler=(0, 0, np.pi / 2))
    # Walkway line beyond the tape.
    geom((0, -1.25, .0011), (2.6, .025, .001), 'yellow')
    geom((-1.55, .2, .0011), (.025, 1.45, .001), 'yellow')

    # Building shell: panel walls behind and left of the cell.
    geom((-.2, 2.05, 1.6), (2.8, .05, 1.6), 'wall_mat', euler=(np.pi / 2, 0, 0))
    geom((-2.35, 0, 1.6), (2.2, .05, 1.6), 'wall_mat', euler=(np.pi / 2, 0, np.pi / 2))
    for x in (-2.0, -.6, .8, 2.2):
        geom((x, 1.98, 1.6), (.09, .07, 1.6), 'steel_dark_mat')
    geom((-.85, 1.995, 1.55), (.42, .21, .002), 'sign_cell_mat', euler=(np.pi / 2, 0, 0))
    geom((.15, 1.995, 1.55), (.32, .16, .002), 'sign_esd_mat', euler=(np.pi / 2, 0, 0))
    geom((-2.295, -.25, 1.45), (.30, .15, .002), 'sign_robot_mat', euler=(np.pi / 2, 0, np.pi / 2))

    # Perimeter fence on the far sides only, so the broadcast view stays clear.
    fx0, fx1, fy = -1.5, 1.25, 1.05
    for x in np.linspace(fx0, fx1, 6):
        geom((x, fy, .9), (.025, .025, .9), 'yellow')
    for z in (.12, 1.0, 1.78):
        geom(((fx0 + fx1) / 2, fy, z), ((fx1 - fx0) / 2, .015, .015), 'yellow')
    geom(((fx0 + fx1) / 2, fy, .95), ((fx1 - fx0) / 2, .004, .8), 'mesh')
    for y in np.linspace(-.45, fy, 4):
        geom((fx0, y, .9), (.025, .025, .9), 'yellow')
    for z in (.12, 1.0, 1.78):
        geom((fx0, (fy - .45) / 2, z), (.015, (fy + .45) / 2, .015), 'yellow')
    geom((fx0, (fy - .45) / 2, .95), (.004, (fy + .45) / 2, .8), 'mesh')

    # Component storage rack behind the fence: ESD bins and SMT reels.
    sx, sy = -.55, 1.55
    for x in (sx - .7, sx + .7):
        for y in (sy - .2, sy + .2):
            geom((x, y, .9), (.02, .02, .9), 'steel_mat')
    for z in (.25, .75, 1.25, 1.7):
        geom((sx, sy, z), (.72, .22, .012), 'steel_dark_mat')
    rng = np.random.default_rng(3)
    for z in (.25, .75):
        for k in range(6):
            geom((sx - .6 + k * .24, sy - .02, z + .07), (.10, .17, .06), 'bin_blue')
    for z in (1.25, 1.7):
        for k in range(12):
            r = .09 + .03 * rng.random()
            geom((sx - .62 + k * .113, sy, z + .012 + r), (r, .012), 'reel' if k % 3 else 'reel_dark',
                 kind='cylinder', euler=(np.pi / 2, 0, 0))

    # Control cabinet with HMI and e-stop at the right rear.
    cx, cy = 1.55, 1.55
    geom((cx, cy, .9), (.32, .22, .9), 'cabinet')
    geom((cx, cy - .222, 1.25), (.20, .002, .13), 'screen_glow')
    geom((cx, cy - .224, 1.25), (.21, .001, .14), 'joint')
    geom((cx + .22, cy - .23, .95), (.035, .02), 'red', kind='cylinder', euler=(np.pi / 2, 0, 0))
    geom((cx + .22, cy - .225, .95), (.05, .05, .005), 'yellow', euler=(np.pi / 2, 0, 0))
    for k in range(3):
        geom((cx - .2 + k * .08, cy - .225, .95), (.018, .01), ('green', 'amber', 'joint')[k], kind='cylinder', euler=(np.pi / 2, 0, 0))

    # Stack light on the back panel next to the robot: red / amber / green.
    lx, ly = .70, .47
    geom((lx, ly, .86), (.008, .11), 'steel_mat', kind='cylinder')
    for k, mat in enumerate(('stack_green', 'stack_amber', 'stack_red')):
        geom((lx, ly, 1.0 + k * .052), (.024, .024), mat, kind='cylinder', name=f'stack_{mat[6:]}')
    geom((lx, ly, 1.16), (.026, .006), 'joint', kind='cylinder')

    # Rolling cart with a spare magazine on the left of the conveyor.
    kx, ky = -1.2, -.15
    geom((kx, ky, .55), (.18, .26, .012), 'steel_mat')
    geom((kx, ky, .18), (.18, .26, .012), 'steel_mat')
    for dx in (-.16, .16):
        for dy in (-.24, .24):
            geom((kx + dx, ky + dy, .36), (.012, .012, .19), 'steel_mat')
            geom((kx + dx, ky + dy, .04), (.035, .02), 'joint', kind='cylinder', euler=(np.pi / 2, 0, 0))
    geom((kx, ky + .05, .66), (.07, .1, .1), 'blue')
    geom((kx, ky - .14, .6), (.12, .06, .04), 'bin_blue')

    return ET.tostring(root, encoding='unicode')

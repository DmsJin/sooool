"""Model sees permitted observations only, with no reference-player actions."""
import json

BASE = '''You control a Franka Panda table-tennis robot in a continuous world.
Read the actual two-camera image and own-state/referee observation. Decide now.
Image: two rows, four chronological frames each; behind camera top, side bottom.
Only camera images reveal the ball. Do not assume coordinates absent from images.
World units: metres, seconds; origin at table centre on the playing surface.
Your half is y<0, opponent y>0; table ends y=+-1.37, width x=+-0.7625.
Gravity -9.81; drag acceleration about -0.13*|v|*v; table bounce normal 0.90,
tangential 0.87; blade restitution 0.80. Blade centre is 0.0275 m behind ball
centre along its unit normal toward opponent. See camera geometry in SPEC.
Return one compact JSON object and nothing else:
{"type":"wait"} to leave the existing stroke intact;
{"type":"move","base":[x,y]} to move rest position;
{"type":"toss","pos":[x,y,z],"height":h} for your legal serve;
{"type":"act","t":seconds_after_effect,"pos":[x,y,z],"normal":[x,y,z],"vel":[x,y,z],"base":[x,y]} to strike.
No need to include base for act. Arm motion is planned by the environment.
Base x within +-1.0, y in [-2.4,-1.5]. Contact t in (0,2.5], blade speed <=8.
Strike a falling serve after a >=0.16 m vertical toss behind y=-1.39, above z=.02.
Serve must bounce on your half then opponent half >=.2 m from net.
During rallies strike after one bounce on your half, aiming onto opponent half.
Do not repeatedly replace a good pending stroke or clear it while waiting.
Commands take effect after measured delay. Predict the ball at command effect
and choose a future reachable contact, accounting for own robot movement time.
You do not know future sampled delay or unfinished model responses.
'''

def prompt(view, spec, timing=None, variant='baseline'):
    cameras = spec.get('cameras', [])
    extra = ''
    if variant == 'anticipate':
        extra = '\nPlan across the latency P50-P95 range. Prepare base before ball arrives; avoid a late replacement of a committed swing.\n'
    if variant == 'serve_safe':
        extra = '''\nServing hypothesis from the robot geometry and a toss-touch failure:
Avoid tossing in front of the robot centre: a rising ball there can hit the arm
before your stroke. Prefer a toss to the left, e.g. x=-0.2, y=-1.42, z=0.27,
height=0.28, with the base moved left toward x=-0.6 and y=-1.75 first.
Wait for the stance to settle. Use the reported toss projection step to estimate
when the falling ball reaches a chosen strike height, and schedule the strike
early enough to give the arm time to accelerate. A legal stroke should send the
ball down onto your half, then over the net; copying the incoming ball's position
without predicting its falling contact time will miss. Keep the existing swing
once committed, unless the camera reveals that it will miss.\n'''
    return BASE + extra + '\nTIMING '+json.dumps(timing or {'profile':'not yet measured','slowdown':10}, separators=(',',':')) + '\nSPEC '+json.dumps({'cameras':cameras},separators=(',',':')) + '\nSTATE '+json.dumps(view['state'],separators=(',',':')) + '\nIMAGE_META '+json.dumps({k:v for k,v in view.get('observation',{}).items() if k not in ('image_png_b64','wall_mono')},separators=(',',':'))

def inputs(view, spec, timing=None, variant='baseline'):
    return [{'role':'user','content':[
        {'type':'input_text','text':prompt(view,spec,timing,variant)},
        {'type':'input_image','detail':'high','image_url':'data:image/png;base64,'+view['observation']['image_png_b64']}
    ]}]

def parse(text):
    value=json.loads(text)
    if not isinstance(value,dict) or value.get('type') not in ('wait','move','toss','act','none'):
        raise ValueError('Expected a supported JSON action')
    return value

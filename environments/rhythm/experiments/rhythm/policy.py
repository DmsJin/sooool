"""All target identity and pixel locations must come from GPT vision."""
import json,re

def prompt(observation,variant='pixels',history=None,delay_ms=None,lanes=None):
    g=observation.geometry;line=g['hitline_y'];top=g.get('canvas_top',0)
    text=f'''Play a four-lane rhythm game from the attached screenshot only. Left to right lanes D=0,F=1,J=2,K=3. Detect BLUE glowing horizontal rectangular note blocks above the hit line. Ignore lane lines, rings, blue keyboard buttons at bottom, white/yellow judgement text, combo digits, and hit particles. A note's lane is the column containing its center, even in the tapered top of the highway. Hitline y={line:.1f} pixels; top of moving-note area y={top:.1f}; image {g['width']}x{g['height']}. All image coordinates refer to this supplied screenshot. Notes move downward linearly; top to hit line takes 1800ms. Observation game time {observation.time_s*1000:.1f}ms. Every response is delayed; do not assume it has already arrived. Identify ALL visible blue note rectangles, including upcoming notes near the top. Do not invent offscreen notes or recall a stored song chart. Return only a compact JSON array, no prose. Empty array if none. '''
    if variant in ('pixels','pixels_history','pixels_compact','pixels_future'):
        text+='Each entry is [lane, vertical_pixel_center]. Example [[0,220],[3,90]]. Sort from bottommost (soonest) to topmost. Pixel centers must be accurate; do not output time values.'
    else:
        text+='Each entry is [lane, milliseconds_until_hit_from_observation]. Compute until_hit=(hitline_y-note_center_y)/(hitline_y-top_y)*1800. Example [[0,400],[3,930]].'
    if delay_ms is not None:text+=f' Measured API delay median={delay_ms[0]:.0f}ms, P95={delay_ms[1]:.0f}ms; actual request delay unknown.'
    if lanes is not None:text+=f' You control ONLY lanes {lanes}; exclude all other lanes.'
    if history:text+=' Previous already-applied actions: '+json.dumps(history[-8:],separators=(',',':'))
    if variant=='pixels_future':text+=' Prioritize rectangles that remain actionable after response arrival; return exact observed centers, not positions extrapolated during thinking.'
    if variant=='pixels_compact':text=f'4-lane rhythm image: D,F,J,K = 0,1,2,3 left-right. Find ALL BLUE horizontal NOTE rectangles, not keyboard/rings/text/particles. Image {g["width"]}x{g["height"]}; hitline y={line:.1f}. Output ONLY JSON [[lane,pixel_y_center],...] sorted bottom to top. Accurate centers. No offscreen predictions.'
    return text

def parse(answer,observation,variant='pixels',lanes=None):
    text=answer.strip()
    if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    data=json.loads(text)
    if not isinstance(data,list) or len(data)>16:raise ValueError('Expected <=16 visual targets')
    events=[];g=observation.geometry
    for row in data:
        if not isinstance(row,list) or len(row)!=2:raise ValueError('Invalid target')
        lane,value=row
        if type(lane) is not int or not 0<=lane<4 or type(value) not in (int,float):raise ValueError('Invalid lane/position')
        if lanes is not None and lane not in lanes:continue
        if variant.startswith('pixels'):
            if not g.get('canvas_top',0)<=value<=g['hitline_y']+4:continue
            delta=(g['hitline_y']-value)/(g['hitline_y']-g.get('canvas_top',0))*1800
        else:delta=float(value)
        if 0<=delta<=1810:events.append([lane,delta])
    return events

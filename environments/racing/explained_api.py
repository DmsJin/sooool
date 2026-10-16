"""Same model/settings and lane goals, with a public English summary in the same response."""
import sys,pathlib,json,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from run import API,write
from lane import parse_lane
OLD_FORMAT='Return ONLY one JSON row nested in an array: [[target_speed, lane_offset_left_m, lookahead_m]].'
NEW_FORMAT='''Return ONLY a JSON object with these keys IN THIS ORDER: {"decision_summary":"brief English observation and intended maneuver","action":[[target_speed,lane_offset_left_m,lookahead_m]]}.
Write one concise public decision summary in English, at most25 words, before the action. Describe the visible driving situation and intended maneuver, without step-by-step private reasoning. Preserve the original goal format and all driving rules below.'''
def parse_packet(answer):
 obj=json.loads(answer)
 if not isinstance(obj,dict) or list(obj)!=['decision_summary','action']:raise ValueError('summary/action object and order required')
 text=obj['decision_summary']
 if not isinstance(text,str) or not text.strip() or len(text)>240 or len(text.split())>40 or '\n' in text:raise ValueError('short English summary required')
 rows=obj['action']
 if not isinstance(rows,list) or any(not isinstance(r,list) or any(type(v) not in (int,float) for v in r) for r in rows):raise ValueError('numeric goals required')
 parse_lane(json.dumps(rows));return obj
class ExplainedAPI(API):
 def act(self,prompt,images,directory,on_ready=None,validator=None):
  assert OLD_FORMAT in prompt,'frozen original lane prompt required';actual_prompt=prompt.replace(OLD_FORMAT,NEW_FORMAT)
  def publish(packet,meta):
   if on_ready:on_ready(packet['action'],{**meta,'decision_summary':packet['decision_summary'],'published_monotonic':time.monotonic()})
  answer,meta=super().act(actual_prompt,images,directory,on_ready=publish if on_ready else None,validator=parse_packet)
  packet=parse_packet(answer);meta.update(decision_summary=packet['decision_summary'],summary_source='same actual API output as action',raw_packet=packet)
  write(pathlib.Path(directory)/'result.json',{'answer':answer,**meta})
  return json.dumps(packet['action']),meta

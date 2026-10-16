"""Offline SSE edge cases and reservation accounting; never calls an external API."""
import json,tempfile
from pathlib import Path
from paid import API,Budget,MODEL,TIER


def run():
    checked=[]
    valid={'input_tokens':100,'output_tokens':10,'input_tokens_details':{'cached_tokens':0}}
    def case(name,deltas,*,created=None,terminal_model=MODEL,terminal_tier=TIER,
             kind='response.completed',status='completed',usage=valid,terminal_text=None,
             expected_ready=1,expected_error=False,blocked=False,no_terminal=False,callback_error=False,action_parser=None):
        with tempfile.TemporaryDirectory(prefix='sooool-parser-') as tmp:
            budget=Budget(Path(tmp)/'fake-budget.json');notes=[];terminal_seen=False
            def notify(row):
                assert not terminal_seen,'Action first delivered at/after terminal'
                state=budget.update(lambda d:d.copy());assert len(state['pending'])==1 and state['used_usd']==0
                notes.append(row)
                if callback_error:raise RuntimeError('fixture callback error')
            class Response:
                status_code=200
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def iter_lines(self,chunk_size):
                    nonlocal terminal_seen
                    def line(e):return b'data: '+json.dumps(e).encode()
                    if created is not None:yield line({'type':'response.created','response':created})
                    prefix=''
                    for delta in deltas:
                        # Even a numeric prefix must never be guessed before JSON closes.
                        prefix+=delta
                        yield line({'type':'response.output_text.delta','delta':delta})
                        if not prefix.rstrip().endswith('}'):assert not notes or prefix.lstrip().startswith('{"choice":') and '}' in prefix
                    assert len(notes)==expected_ready,(name,notes)
                    if no_terminal:return
                    terminal_seen=True
                    text=''.join(deltas) if terminal_text is None else terminal_text
                    yield line({'type':kind,'response':{'model':terminal_model,'service_tier':terminal_tier,'status':status,
                        'output':[{'type':'message','content':[{'type':'output_text','text':text}]}],'usage':usage}})
            class HTTP:
                def post(self,*args,**kwargs):return Response()
                def close(self):pass
            api=API('offline-fixture-not-real',budget,'profiling',5);api.http.close();api.http=HTTP()
            row=api.call([],count=200,choice_count=12 if action_parser is None else None,on_ready=notify,action_parser=action_parser)
            state=budget.update(lambda d:d.copy())
            assert bool(row['error'])==expected_error,(name,row)
            assert state['blocked']==blocked and not state['pending'],(name,state)
            assert len(notes)==expected_ready
            assert state['used_usd']==row['cost_usd']>0
            if not expected_error:
                if action_parser is None:assert notes[0]['choice']==json.loads(''.join(deltas))['choice']
                else:assert notes[0]['action']==action_parser(''.join(deltas))
            checked.append(name)
    identity={'model':MODEL,'service_tier':TIER}
    case('split_multidigit',['{"choice":','1','0','}'],created=identity)
    case('trailing_whitespace',[' {"choice":1}',' \n'],created=identity)
    case('missing_identity_provisional',['{"choice":1}'])
    case('missing_tier_provisional',['{"choice":1}'],created={'model':MODEL})
    case('known_wrong_model_veto',['{"choice":1}'],created={'model':'wrong','service_tier':TIER},expected_ready=0,expected_error=True)
    case('known_wrong_tier_veto',['{"choice":1}'],created={'model':MODEL,'service_tier':'wrong'},expected_ready=0,expected_error=True)
    case('terminal_model_mismatch',['{"choice":1}'],terminal_model='wrong',expected_error=True)
    case('terminal_tier_mismatch',['{"choice":1}'],terminal_tier='wrong',expected_error=True)
    for name,text in [('duplicate_key','{"choice":1,"choice":1}'),('boolean','{"choice":true}'),
                      ('extra_field','{"choice":1,"other":0}'),('range','{"choice":12}'),('unfinished_number','{"choice":1')]:
        case(name,[text],created=identity,expected_ready=0,expected_error=True)
    case('late_junk',['{"choice":1}','oops'],created=identity,expected_error=True)
    case('terminal_changed_action',['{"choice":1}'],created=identity,terminal_text='{"choice":2}',expected_error=True)
    case('failed_terminal',['{"choice":1}'],created=identity,kind='response.failed',status='failed',expected_error=True)
    case('failed_event_with_completed_status',['{"choice":1}'],created=identity,kind='response.failed',expected_error=True)
    case('missing_usage',['{"choice":1}'],created=identity,usage=None,expected_error=True,blocked=True)
    case('invalid_nested_usage',['{"choice":1}'],created=identity,usage={**valid,'input_tokens_details':[1]},expected_error=True,blocked=True)
    case('missing_terminal',['{"choice":1}'],created=identity,no_terminal=True,expected_error=True,blocked=True)
    case('callback_failure_still_drains',['{"choice":1}'],created=identity,callback_error=True,expected_error=True)
    from direct_io import parse
    case('direct_split_move',['{"type":"move","base":[0,','-1.8]}'],created=identity,action_parser=parse)
    case('direct_split_act',['{"type":"act","t":0.4,"pos":[0,-1.2,0.2],',
                            '"normal":[0,1,0],"vel":[0,1,0]','}'],created=identity,action_parser=parse)
    case('direct_duplicate_key',['{"type":"wait","type":"none"}'],created=identity,action_parser=parse,expected_ready=0,expected_error=True)
    case('direct_terminal_changed_action',['{"type":"wait"}'],created=identity,action_parser=parse,terminal_text='{"type":"none"}',expected_error=True)
    report={'scope':'Offline SSE/ledger fixtures, not paid latency or game performance','cases':checked,
            'passed':len(checked),'callback_before_terminal_and_reservation_retained':True,'external_api_calls':0}
    print(json.dumps(report));return report

if __name__=='__main__':run()

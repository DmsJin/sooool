"""Candidate strokes from permitted pixels, robot state and public physics.

Nothing is executed here. GPT must choose online after seeing the real image.
This is an explicitly different input/control condition from direct JSON play.
"""
import base64
import numpy as np
from builtin_players import Cam,Player,decode,solve_out,paddle_for,serve_plan,SERVES
from robot_contact import receive_target

def scaled_return_velocity(velocity,normal,scale):
    """Keep requested normal velocity; scale only its tangential component.

    This changes native friction/spin interaction; the simplified outgoing-ball
    solution is not a prediction that native ball flight will remain unchanged.
    """
    velocity=np.asarray(velocity,float);normal=np.asarray(normal,float)
    normal=normal/np.linalg.norm(normal)
    vn=np.dot(velocity,normal)*normal
    return vn+scale*(velocity-vn)

class Candidates:
    def __init__(self,spec,mode='geometry_menu'):
        if '_fast_' in mode:
            from fast_geometry import install
            install()
        player_class=Player
        if '_rallylate_' in mode:
            from rally_late import RallyLatePlayer
            player_class=RallyLatePlayer
        if '_robotcontact_' in mode:
            from robot_contact import RobotContactPlayer
            player_class=RobotContactPlayer
        self.player=player_class([Cam(c) for c in spec['cameras']])
        self.mode=mode
        self.previous_q=None;self.previous_step=None;self.ready_q=None;self.stance_since=None;self.point=None
        self.armready_points=set()
        if '_recoverlift_' in mode:
            from recover_lift import Recovery
            self.recovery=Recovery()
        if mode.startswith('geometry_stable'):
            self.serves={f'central_depth_{y:.2f}':serve_plan('short_centre_top',recipe={**SERVES['short_centre_top'],'b2':(0.,y)}) for y in (.45,.4,.5)}
        else:self.serves={name:serve_plan(name) for name in ('short_centre_top','mid_wide_bh_top','mid_wide_fh_top')}
        if '_wideserve_' in mode:
            self.serves.update({f'wide_depth_0.45_x{x:+.2f}':serve_plan('short_centre_top',recipe={**SERVES['short_centre_top'],'b2':(x,.45)}) for x in (-.65,.65)})
        if '_marginserve_' in mode:
            self.serves['margin_depth_0.45_x+0.55']=serve_plan('short_centre_top',recipe={**SERVES['short_centre_top'],'b2':(.55,.45)})
    def build(self,view,timing):
        st=view['state'];ob=view['observation'];k=st['step'];sv=st.get('serve') or {}
        if '_armready_' in self.mode:
            self.armready_points.update(record['action']['_armready_point'] for record in st.get('recent_applied',[])
                                        if '_armready_point' in record.get('action',{}))
        stable_mode=self.mode.startswith('geometry_stable')
        settled=True
        if stable_mode or '_recoverlift_' in self.mode:
            q=np.asarray(st['q'],float)
            if self.ready_q is None:self.ready_q=q[2:].copy()
            if self.point!=st['point']:
                self.previous_q=None;self.stance_since=None;self.point=st['point']
            dt=0 if self.previous_step is None else (k-self.previous_step)*.01
            speed=None if self.previous_q is None or dt<=0 else float(np.max(np.abs(q-self.previous_q))/dt)
            near_ready=float(np.max(np.abs(q[2:]-self.ready_q)))<.003
            at_stance=float(np.max(np.abs(q[:2]-np.array([.2,-1.87]))))<.005
            rest=np.asarray(st.get('base_rest',q[:2]),float)
            if np.max(np.abs(rest-np.array([.2,-1.87])))<.001:
                if self.stance_since is None:self.stance_since=k
            else:self.stance_since=None
            elapsed=0 if self.stance_since is None else (k-self.stance_since)*.01
            settled=bool(speed is not None and speed<.04 and near_ready and at_stance and elapsed>=1.0)
            st['stance_check']={'max_joint_or_base_speed':speed,'near_ready':bool(near_ready),'at_stance':bool(at_stance),
                                'game_s_since_serve_stance_command':round(elapsed,3),'settled':settled}
            self.previous_q=q.copy();self.previous_step=k
        options=[{'id':0,'kind':'wait','description':'Keep current motion and any returned plan'}]
        if self.mode.endswith('_chunk'):
            options[0].update(wait_steps=20,description='Wait .20 game s, keeping the current stroke; then observe again')
            options.append({'id':1,'kind':'wait','wait_steps':5,'description':'Brief wait .05 game s for an urgent new ball estimate'})
        if '_watch_' in self.mode:
            waiting_opponent=st.get('you_receive_serve') and not st.get('ball_in_play')
            outgoing=st.get('ball_state')=='going to the opponent'
            forward=np.max(np.abs(np.asarray(st.get('base_rest',st['base_xy']))-np.array([0.,-1.55])))<.01
            if forward and (waiting_opponent or outgoing):
                options.append({'id':len(options),'kind':'wait','description':'Watch public referee until an incoming ball starts; wake to inspect actual camera; at most .80 game s',
                                'watch_for':{'ball_state':'coming to you','require_in_play':True,'max_steps':80}})
        if '_rallywatch_' in self.mode:
            target=receive_target(self.mode)
            rest=st.get('base_rest')
            at_receive=rest is not None and np.max(np.abs(np.asarray(rest)-target))<.01
            if at_receive and st.get('ball_state')=='going to the opponent':
                options.append({'id':len(options),'kind':'wait',
                                'description':'Watch public referee during outgoing rally flight; wake for an incoming ball image; at most .80 game s',
                                'watch_for':{'ball_state':'coming to you','require_in_play':True,'max_steps':80}})
        if '_recoverlift_' in self.mode:
            self.recovery.observe(st.get('recent_applied',[]))
            if self.recovery.blocked(st):return options
        if st.get('known_plan'):return options
        if st.get('you_serve') and st.get('ball_state')=='your serve':
            # Each candidate is an analytical public-physics serve, selected by GPT.
            for name,plan in self.serves.items():
                if plan is None:continue
                toss,stroke=plan;base=stroke['base'].tolist()
                needs_move=np.max(np.abs(np.array(st['base_xy'])-stroke['base']))>.01
                if stable_mode:needs_move=needs_move or np.max(np.abs(np.array(st.get('base_rest',st['base_xy']))-stroke['base']))>.001
                if needs_move:
                    if self.mode!='geometry_menu' and np.max(np.abs(np.array(st.get('base_rest',st['base_xy']))-stroke['base']))<.001:
                        continue
                    item={'kind':'move','action':{'type':'move','base':base},'description':'Prepare serve stance '+name}
                elif sv.get('phase')=='open':
                    if stable_mode and not settled:continue
                    action={key:np.asarray(stroke[key]).round(5).tolist() for key in ('pos','normal','vel','base')}
                    # tf starts at upward projection; native toss rests for10ticks.
                    # Keep both ends of the GPT-selected chunk on the same clock.
                    windup_steps=30 if '_windup30_' in self.mode else 10
                    action.update(type='act',t=round((windup_steps+10)*.01+stroke['t_from_projection'],4))
                    windup_label='.3' if windup_steps==30 else '.1'
                    item={'kind':'serve_bundle','description':name+f'; wind up now, toss after {windup_label} game s',
                          'actions':[{'after_steps':0,'action':action},{'after_steps':windup_steps,'action':{'type':'toss',**toss}}]}
                else:continue
                item['id']=len(options);options.append(item)
                if stable_mode:
                    if '_marginserve_' in self.mode and name.startswith('margin_'):
                        item['description']+='; experimental lateral margin: reduced faults in fixed calibration on six known seeds; not yet verified online'
                    elif '_wideserve_' in self.mode and name.startswith('wide_'):
                        item['description']+='; experimental edge target: fixed first-service tests scored directly on two known seeds; no guarantee of online success'
                    else:
                        item['description']+='; fixed-control calibration: depth .45 won 3/3 development serves, .50 won 2/3' + ('; compare with the experimental edge options' if '_wideserve_' in self.mode else '; prefer .45 for margin')
                elif self.mode!='geometry_menu' and name=='short_centre_top':
                    item['description']+='; preferred reliability candidate: this short central serve won the native fixed-choice smoke test'
        if self.mode!='geometry_menu' and not (st.get('you_serve') and st.get('ball_state')=='your serve'):
            # A move changes the rest slew after the committed swing, not the swing.
            # Later contacts are near the end line. Prepare their deeper stance
            # while the ball is outgoing, rather than asking for a late retreat.
            target=receive_target(self.mode)
            if st.get('ball_state')=='going to the opponent' or not st.get('ball_in_play'):
                if np.max(np.abs(np.array(st.get('base_rest',st['base_xy']))-target))>.01:
                    options.append({'id':len(options),'kind':'move','description':'Prepare forward receive stance before the incoming ball',
                                    'action':{'type':'move','base':target.tolist()}})
        if '_armready_' in self.mode and st.get('point') not in self.armready_points:
            from arm_ready import eligible,preparation
            if eligible(st,st.get('recent_applied',[])):
                option=preparation(st,bundle='_prepbase_' in self.mode);option['id']=len(options);options.append(option)
        if st.get('ball_state')=='coming to you' and st.get('ball_in_play'):
            obs=dict(st,view_steps=ob.get('view_steps'),view_times=ob.get('view_times'))
            self.player.update(obs,decode(base64.b64decode(ob['image_png_b64'])),k)
            pred=self.player.predict()
            if pred is not None:
                tc,p,v,phase,nfr=pred
                contact_step=self.player.leg['launch']+round(tc/.01)
                if contact_step>k+4:
                    for aim_x in (-.5,0,.5):
                        best=None
                        for pace in (4.6,4.2,3.8,3.4,3.0):
                            vo,ok=solve_out(p,[aim_x,.85],pace)
                            fallback_evidence=None
                            if not ok and '_robustout_' in self.mode:
                                from robust_out import solve_out_robust
                                vo,fallback_evidence=solve_out_robust(p,[aim_x,.85],pace)
                                ok=vo is not None
                            if not ok:continue
                            pos,normal,vel=paddle_for(p,v,vo)
                            speed=float(np.linalg.norm(vel))
                            if best is None or speed<best[0]:best=(speed,pos,normal,vel,pace,fallback_evidence)
                            if speed<=1.5:break
                        if best:
                            speed,pos,normal,vel,pace,fallback_evidence=best
                            # Choose pace with the original tangential=True speed
                            # and threshold first, then perform a paired ablation.
                            tangential_scale=.25 if '_quartertangent_' in self.mode else 0. if '_normalstroke_' in self.mode else 1.
                            original_speed=speed
                            if tangential_scale!=1.:
                                vel=scaled_return_velocity(vel,normal,tangential_scale)
                                speed=float(np.linalg.norm(vel))
                            options.append({'id':len(options),'kind':'act','description':'Return toward opponent x='+str(aim_x),
                                            'contact_step':int(contact_step),'lead_game_s':round((contact_step-k)*.01,3),
                                            'fit_phase':phase,'fit_frames':nfr,'estimated_blade_speed':round(speed,3),
                                            'action':{'type':'act','pos':pos.round(5).tolist(),'normal':normal.round(5).tolist(),'vel':vel.round(5).tolist()}})
                            if tangential_scale!=1.:
                                options[-1]['return_velocity_ablation']={
                                    'tangential_scale':tangential_scale,'original_blade_speed':round(original_speed,3),
                                    'adjusted_blade_speed':round(speed,3),'original_pace_vy':pace,
                                    'scope':'same selected contact, normal and pace; normal velocity preserved',
                                    'limitation':'native friction/spin can change outgoing ball flight; not verified'}
                            if fallback_evidence is not None:
                                options[-1]['outgoing_solver']={'method':'optional robust fallback after public solve_out rejection',
                                                               **fallback_evidence}
                            if '_rallylate_' in self.mode and self.player.leg['kind'] in ("opponent's return", 'return'):
                                options[-1]['contact_policy']='late rally contact from camera fit; nearer robot when the public late rule applies'
                            if '_robotcontact_' in self.mode and self.player.contact_metadata is not None:
                                options[-1]['contact_geometry']=self.player.contact_metadata
        if '_hold_' in self.mode:
            command=st.get('command')
            if isinstance(command,dict) and command.get('phase')=='approach':
                planned_step=k+round(float(command.get('contact_in_s',0))/.01)
                position=command.get('pos');normal=command.get('normal')
                for option in options:
                    if option['kind']!='act':continue
                    delta={'contact_shift_game_s':round((option['contact_step']-planned_step)*.01,3)}
                    if position is not None:delta['position_shift_m']=round(float(np.linalg.norm(np.asarray(option['action']['pos'])-np.asarray(position))),4)
                    if normal is not None:
                        a=np.asarray(option['action']['normal']);b=np.asarray(normal);cos=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
                        delta['normal_shift_deg']=round(float(np.degrees(np.arccos(np.clip(cos,-1,1)))),2)
                    option['change_from_committed_stroke']=delta
        if '_commitguard_' in self.mode:
            from commit_guard import filter_replacements
            options=filter_replacements(st,options,normal_limit=15 if '_guard15_' in self.mode else 2)
        if '_recoverlift_' in self.mode:
            from recover_lift import eligible,option
            if self.stance_since is not None and eligible(st,self.ready_q,self.stance_since,st['point'] in self.recovery.installed):
                recovery=option(st,self.ready_q,self.stance_since)
                if recovery is not None:recovery['id']=len(options);options.append(recovery)
        if '_abortstroke_' in self.mode:
            from abort_stroke import abort_option
            option=abort_option(st,len(options))
            if option is not None:options.append(option)
        return options

def menu_prompt(view,options,timing,mode='geometry_menu'):
    import json
    state=view['state']
    meta={k:v for k,v in view['observation'].items() if k not in ('image_png_b64','wall_mono')}
    evidence=''
    if mode.startswith('geometry_stable'):
        evidence='''\nDevelopment evidence: the old very short serve faulted below the .20 m minimum
depth. A deeper central serve aimed at .45 m won all three fixed-control development
tests; .50 m won two. Prefer central_depth_0.45. These small tests are calibration,
not a claim of guaranteed wins. Serving options are withheld until own joint/base
feedback shows a settled stance, with a one-game-second settling margin.
Choose the forward receive-stance move early; previous returns failed because
the base was .36 m too far back. A move changes the rest position after a swing.
Choose brief wait near an incoming ball; longer wait during safe preparation.
'''
    elif mode!='geometry_menu':
        evidence='''\nDevelopment evidence: short_centre_top won a legal fixed-choice serve test.
Wide forehand serve was returned in one online pilot and faulted in another.
Prefer the short central serve for reliability. After serving, or while waiting
for opponent service, select the forward receive-stance move early: a previous
return was missed because the base was .36 m too far back to move in time.
Keep that stance until your next serve requires the serve stance again.
Choose the brief wait when an incoming ball needs another flight estimate soon;
choose a longer wait during safe preparation or outgoing flight.\n'''
    if '_marginserve_' in mode and state.get('you_serve') and state.get('ball_state')=='your serve':
        evidence=evidence.replace('Prefer central_depth_0.45.', 'Experimental service policy: consider margin_depth_0.45_x+0.55 for more lateral margin than x=+.65. Fixed calibration on six known seeds reduced faults while often scoring directly; online success is unverified. Check the actual camera and choose; preserve settled stance and the wind-up/toss chunk.')
    elif '_wideserve_' in mode and state.get('you_serve') and state.get('ball_state')=='your serve':
        evidence=evidence.replace('Prefer central_depth_0.45.', 'Experimental service policy: prefer one of the new wide_depth_0.45_x options when it looks appropriate in the actual camera. Both x=-.65 and x=.65 scored directly in fixed first-service tests on two known research seeds. This is calibration, not GPT success or a guarantee. Choose the side farther from the red opponent paddle; preserve the original settled-stance gate and wind-up/toss chunk.')
    if '_latebase_' in mode:
        evidence+='''\nExperimental preparation policy for later rally contacts: use the offered\nreceive move to [0,-1.79] while the ball is outgoing or before opponent service.\nThis condition replaces the earlier forward-stance cue: recorded later contacts\nneeded about .24 m of retreat when prepared at -1.55. Preparing that retreat\nearly may preserve contact lead. It is an unverified hypothesis; low contacts\ncan still strike the table, and no candidate guarantees a successful return.\n'''
    if '_early_' in mode:
        evidence+='''\nReturn timing policy: do not wait for the bounce to begin a stroke. Previous\nmisses happened when an early estimate with .8-1.1 game seconds lead was ignored;\na later decision arrived with only .1-.24 seconds left and the arm could not\nreach the ball. When an early return candidate is available with several frames\nand at least .55 game seconds lead, commit now to a reachable low-speed return.\nThe prediction may be imperfect; beginning the base and arm motion now creates\nroom for a small later correction. Do not repeatedly wait for perfect estimates.\nOnce a return is commanded for the current incoming ball, preserve its direction\nand contact plan; replace only to correct a material contact error with enough\nremaining time. At less than .55 seconds observation-time lead, sending a first\nstroke is urgent and may already be too late after inference and motor motion.\n'''
    if '_feedback_' in mode:
        evidence+='''\nSTATE.recent_applied contains execution_feedback returned by your own native\nactions. Check blade_error_m and normal_error_deg for inaccurate plans; speed_scale\ngreater than one means the requested paddle velocity was reduced. Prefer an early\ncorrection while enough contact lead remains. Once a coherent accurate stroke is\ncommitted, avoid a late replacement merely because a small velocity reduction is\nreported. Candidate blade speed alone does not establish joint feasibility.\n'''
    recovery_context=(any(o.get('purpose')=='recoverlift' for o in options)
                      or any(r.get('_recoverlift_installed') is True
                             and r.get('action',{}).get('_recoverlift_point')==state.get('point')
                             for r in state.get('recent_applied',[])))
    if '_recoverlift_' in mode and recovery_context:
        evidence+='''\nIf a recovery lift is offered during your open service, consider it to free an\narm far from ready. It is a fixed zero-speed pose attempt, not a ball strike or\na guarantee of recovery. After choosing it, wait for natural ready return; do not\nreplace or toss during approach/follow-through. You still choose every action.\n'''
    if '_abortstroke_' in mode:
        evidence+='''\nConsider the offered abort_stroke before contact when matched public rehearsal\nfeedback predicts table contact or a severely inaccurate speed-limited plan.\nIt clears the current stroke and returns toward ready, and may concede this ball.\nThis warning predicts a plan problem; it does not prove an actual collision.\nYou choose whether to abort; cancellation is never automatic.\n'''
    if '_hold_' in mode:
        evidence+='''\nCommitted-stroke policy: a native branch diagnostic returned an opponent\nserve successfully when an early stroke was started with .75 seconds remaining\nand kept. Repeated late replacements in online pilots worsened the arm plan.\nInspect STATE.command and each candidate's change_from_committed_stroke.\nIf an incoming-ball stroke is already in approach and the current candidate differs\nby less than .03 m and .03 game seconds, normally choose wait to preserve it.\nA small joint-speed limitation alone does not justify replacing a coherent plan.\nCorrect a materially wrong contact early enough; avoid switching return direction\nlate. If the command reports not achievable, prefer an early feasible correction.\nThis is evidence from a fixed native diagnostic, not a guaranteed GPT result.\n'''
    if '_watch_' in mode:
        evidence+='''\nObservation scheduling: after the forward receive stance is commanded, prefer\nthe public-referee watch option while waiting for opponent service or outgoing\nflight. It keeps the commanded motion, sends no automatic strike, and wakes\nfor an actual new image as soon as an incoming ball starts (or after .80 seconds).\nThis saves repeated waiting decisions and reduces missed early flight frames.\nOn the incoming flight, use brief waits only when estimates are insufficient;\notherwise commit the early return. Every strike is still selected by you.\n'''
    if '_armready_' in mode:
        evidence+='''\nExperimental receive preparation policy: the base move prepares only the rail;
it does not prepare the arm. A recorded return had accurate position but severe
velocity loss; its arm travel alone required about .23 game seconds. Test whether
starting the fixed zero-speed ARM PREPARATION during outgoing flight improves the
next real return. When the menu offers it, your arm is ready, and the camera shows
the ball has cleared the preparation area, choose ARM PREPARATION before choosing
the outgoing watch. It is not a predicted ball strike. It includes the receive
base target, so a separate rail move is not required first. Once prepared, keep
that motion and use the watch; on the incoming ball, choose a new camera-derived
return. Do not prepare if the image shows a likely ball collision or when an
existing stroke must finish. Preparation later returns to ready automatically;
its benefit and timing are unverified. You still decide every action online.\n'''
        if '_prepbase_' in mode:
            evidence=evidence.replace('It includes the receive\nbase target, so a separate rail move is not required first.',
                                      'Its short chunk first prepares the arm, then sets receive base_rest\nwith a move that keeps the swing. This enables the outgoing watch and\naligns the later native return position.')
    if '_rallywatch_' in mode:
        evidence+='''\nExperimental rally observation scheduling: once the receive rest position is\ncommanded, consider the public-referee watch option during outgoing flight.\nIt preserves your stroke and wakes for a new image when an incoming ball starts\n(or after .80 game seconds). This option is absent while waiting for opponent\nservice; you still choose every gate and strike.\n'''
    return '''You are playing robot table tennis ONLINE. Look at the actual camera
image (two cameras x four chronological frames) and the referee/own robot state.
Choose ONE candidate action or short serve chunk. The menu is computed only from
these camera pixels, your own state, public physics and serve recipes. Estimates
can be wrong: use the actual image to decide, rather than blindly taking a menu item.
You alone choose whether, when and where to strike. Return ONLY {"choice":N}.
0 means wait, keeping an existing stroke or known chunk. Choose a move to the
serve stance while waiting to serve; once at stance, wait until the arm settles.
When your serve opens choose a serve bundle: wind-up then toss is one short plan.
Do not cancel or duplicate it. The bundle aims to hit the falling toss legally.
After tossing, keep the committed serve stroke; don't choose another serve.
On an incoming ball, choose a feasible return before the contact becomes too near.
Contact steps are absolute: the executor translates them after your actual delay.
Use estimated P50/P95 delay and the commanded stroke to avoid needless replacements.
Prefer placing the ball away from the red opponent paddle; choose a safer central
return if a wide option looks unreachable. Images and estimates describe the
observation time, not the unknown future. No hidden ball state is available.
'''+evidence+'\nTIMING '+json.dumps(timing,separators=(',',':'))+'\nSTATE '+json.dumps(state,separators=(',',':'))+'\nIMAGE_META '+json.dumps(meta,separators=(',',':'))+'\nCANDIDATES '+json.dumps(options,separators=(',',':'))

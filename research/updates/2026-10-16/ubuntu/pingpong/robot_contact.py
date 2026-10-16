"""Optional contact geometry from public camera fits and observed own base."""
import numpy as np
import builtin_players as public


def receive_target(mode):
    return np.array([0.,-1.67 if '_midbase_' in mode else -1.79 if '_latebase_' in mode else -1.55])


def comfortable_contact(fit,base,now,need_bounce,dt=.001,t_max=1.6):
    t0,p,v,accel=fit[:4]
    points,velocities,bounces=public.rollout(p,v,dt,int(t_max/dt),bounce=True,a_extra=accel)
    own=[i for i in bounces if points[i,1]<0]
    if need_bounce and not own:return None
    # Bounce numbering belongs to the fit phase, not the observation clock.
    # A pre-bounce fit must cross its first bounce even if the heard bounce
    # precedes that prediction; a post-bounce fit must never skip its next bounce.
    first=own[0] if need_bounce else 0
    next_bounce=next((i for i in own if i>first),len(points))
    for i in range(next_bounce-1,first,-1):
        point=points[i]
        if (t0+i*dt>=now+.04 and point[2]>=.20
                and abs(point[0]-base[0])<=.22 and abs(point[1]-(base[1]+.45))<=.10):
            return t0+i*dt,point.copy(),velocities[i].copy()
    return None


def audit_contact_boundary(fit,phase,contact_time,now,dt=.001,t_max=1.6):
    """Public-fit predicate for auditing old selected contacts; no game-state access.

    Call on the actual selected fit/phase and ball-clock contact time. Flags
    identify affected choices, not proof that a physical point would be lost.
    """
    t0,p,v,accel=fit[:4]
    points,_,bounces=public.rollout(p,v,dt,int(t_max/dt),bounce=True,a_extra=accel)
    own=[t0+i*dt for i in bounces if points[i,1]<0]
    if phase not in ('pre','post'):raise ValueError('Expected public fit phase pre/post')
    required=(own[0] if own else None) if phase=='pre' else t0
    deadline=(own[1] if len(own)>1 else None) if phase=='pre' else (own[0] if own else None)
    return {'fit_phase':phase,'required_bounce_game_s':required,'second_bounce_game_s':deadline,
            'before_required_bounce':required is None or contact_time<=required,
            'at_or_after_second_bounce':deadline is not None and contact_time>=deadline,
            'too_soon':contact_time<now+.04}


class RobotContactPlayer(public.Player):
    def update(self,obs,img,k_req):
        result=super().update(obs,img,k_req)
        self.observed_base=np.asarray(obs['base_xy'],float)
        self.observed_time=(k_req-self.leg['launch'])*public.DT
        return result

    def predict(self):
        self.contact_metadata=None
        if self.leg['kind'] not in ("opponent's return",'return'):return super().predict()
        frames=sorted(self.leg['frames'].items());own=self._bounce_t('own')
        before=[(t,x) for t,x in frames if t>0 and (own is None or t<own-.003)]
        fit=public.fit_flight(before,fit_accel=True) if len(before)>=3 else None
        phase='pre';count=len(before);need_bounce=True
        if own is not None:
            after=[(t,x) for t,x in frames if t>own+.003]
            if len(after)>=3:
                fit=public.fit_flight(after,a_fixed=None if fit is None else fit[3])
                phase='post';count=len(after);need_bounce=False
        contact=None if fit is None else comfortable_contact(fit,self.observed_base,self.observed_time,need_bounce)
        if contact is None:
            result=super().predict()
        else:result=contact+(phase,count)
        self.contact_metadata={'policy':'observed base comfort contact','fallback':contact is None,
                               'contact_height_m':None if result is None else round(float(result[1][2]),3),
                               'cone_center_xy':[round(float(self.observed_base[0]),3),round(float(self.observed_base[1]+.45),3)]}
        return result

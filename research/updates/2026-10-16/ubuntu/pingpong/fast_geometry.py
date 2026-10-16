"""Scalar implementation of public analytical flight integration.
Only candidate prediction uses this helper. Native game physics is untouched.
"""
import math
import numpy as np

def install():
 import builtin_players as public
 original=public.rollout
 gravity=tuple(float(x) for x in public.G)
 kd=float(public.KD);radius=float(public.BALL_R)
 table_x=float(public.TABLE_X);table_y=float(public.TABLE_Y)
 e_xy=float(public.E_BOUNCE_XY);e_z=float(public.E_BOUNCE_Z)
 def rollout(p,v,dt,n,bounce=True,a_extra=None):
  px,py,pz=map(float,p);vx,vy,vz=map(float,v)
  ex,ey,ez=(0.,0.,0.) if a_extra is None else map(float,a_extra)
  gx,gy,gz=gravity
  P=np.empty((n+1,3));V=np.empty((n+1,3))
  P[0]=(px,py,pz);V[0]=(vx,vy,vz);bounces=[]
  for i in range(1,n+1):
   speed=math.sqrt(vx*vx+vy*vy+vz*vz)
   vx=vx+(gx-kd*speed*vx+ex)*dt
   vy=vy+(gy-kd*speed*vy+ey)*dt
   vz=vz+(gz-kd*speed*vz+ez)*dt
   px=px+vx*dt;py=py+vy*dt;pz=pz+vz*dt
   if bounce and pz<radius and vz<0 and abs(px)<=table_x+.01 and abs(py)<=table_y+.01:
    vx=vx*e_xy;vy=vy*e_xy;vz=-vz*e_z;pz=2*radius-pz;bounces.append(i)
   P[i]=(px,py,pz);V[i]=(vx,vy,vz)
  return P,V,bounces
 public.rollout=rollout
 return original,rollout

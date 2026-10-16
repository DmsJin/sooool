"""Batched finite differences for the reference's unchanged drag/gravity flight fit."""
import math

import numpy as np
from numba import njit


@njit(cache=True)
def _rollout(position, velocity, dt, n, bounce, extra, gravity, drag, radius, ez, exy, table_x, table_y):
    p, v = position.copy(), velocity.copy()
    positions, velocities = np.empty((n + 1, 3)), np.empty((n + 1, 3))
    positions[0], velocities[0] = p, v
    bounces = []
    for step in range(1, n + 1):
        speed = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        acceleration = gravity - drag * speed * v + extra
        v = v + acceleration * dt
        p = p + v * dt
        if bounce and p[2] < radius and v[2] < 0 and abs(p[0]) <= table_x + .01 and abs(p[1]) <= table_y + .01:
            v = np.array([v[0] * exy, v[1] * exy, -v[2] * ez])
            p[2] = 2 * radius - p[2]
            bounces.append(step)
        positions[step], velocities[step] = p, v
    return positions, velocities, bounces


def rollout(p, v, dt, n, bounce=True, a_extra=None, *, gravity, drag, radius, ez, exy, table_x, table_y):
    return _rollout(np.asarray(p, float), np.asarray(v, float), dt, n, bounce,
                    np.zeros(3) if a_extra is None else np.asarray(a_extra, float),
                    gravity, drag, radius, ez, exy, table_x, table_y)


def solve_out(position, aim, vy=3.4, *, flight, radius, net_z):
    """Shoot to an interpolated target plane, avoiding discontinuous bounce indices."""
    p, aim = np.asarray(position, float), np.asarray(aim, float)
    vx = (aim[0]-p[0]) * vy / (aim[1]-p[1])

    def path(vz):
        velocity = np.array([vx, vy, vz])
        positions, _, _ = flight(p, velocity, .002, 1500, bounce=False)
        index = int(np.searchsorted(positions[:, 1], aim[1]))
        if index == len(positions):
            return None, positions, velocity
        fraction = (aim[1]-positions[index-1, 1]) / (positions[index, 1]-positions[index-1, 1])
        height = positions[index-1, 2] + fraction*(positions[index, 2]-positions[index-1, 2])
        return height-radius, positions[:index+1], velocity

    low, high = -3., 10.
    upper, _, _ = path(high)
    if upper is None or upper < 0:
        return np.array([vx, vy, high]), False
    for _ in range(22):
        middle = (low+high)/2
        error, _, _ = path(middle)
        if error is None or error < 0:
            low = middle
        else:
            high = middle
    _, positions, velocity = path((low+high)/2)
    net = int(np.searchsorted(positions[:, 1], 0.))
    if net == 0 or net == len(positions):
        return velocity, False
    fraction = -positions[net-1, 1] / (positions[net, 1]-positions[net-1, 1])
    height = positions[net-1, 2] + fraction*(positions[net, 2]-positions[net-1, 2])
    return velocity, bool(height > net_z+radius+.05)


@njit(cache=True)
def countershot(position, incoming, aim, gravity, drag, restitution=.8):
    """Jointly choose face and normal speed; screen the resulting ball flight."""
    heading = math.atan2((aim[0]-position[0])*3/max(.5,aim[1]-position[1])-incoming[0], 3-incoming[1])
    best = 1e9
    best_normal, best_velocity, best_out = np.zeros(3), np.zeros(3), np.zeros(3)
    for speed in (.45, .65, .85, 1.05, 1.25, 1.45):
        for pitch_deg in range(18, 59, 2):
            pitch = pitch_deg*math.pi/180
            for yaw_deg in (-8, -4, 0, 4, 8):
                yaw = heading+yaw_deg*math.pi/180
                normal = np.array([math.sin(yaw)*math.cos(pitch), math.cos(yaw)*math.cos(pitch), math.sin(pitch)])
                outgoing = incoming+(1+restitution)*(speed-np.dot(incoming,normal))*normal
                p, v = position.copy(), outgoing.copy()
                net_height = -10.
                for step in range(900):
                    previous = p.copy()
                    v = v+(gravity-drag*np.sqrt(np.dot(v,v))*v)*.002
                    p = p+v*.002
                    if previous[1]<0<=p[1]:
                        f=-previous[1]/(p[1]-previous[1])
                        net_height=previous[2]+f*(p[2]-previous[2])
                    if p[2]<=.02 and v[2]<0:
                        f=(previous[2]-.02)/(previous[2]-p[2])
                        landing=previous[:2]+f*(p[:2]-previous[:2])
                        error=np.sqrt(np.sum((landing-aim)**2))
                        if .12<landing[1]<1.25 and abs(landing[0])<.65 and net_height>.1525+.02+.10 and error<.28:
                            cost=2*error+.35*speed+.15*abs(pitch-.45)
                            if cost<best:
                                best=cost
                                best_normal, best_velocity, best_out=normal.copy(), speed*normal, outgoing.copy()
                        break
                    if p[1]>1.6 or p[1]<-2 or abs(p[0])>1:
                        break
    return best<1e9, best_normal, best_velocity, best_out


def _positions(theta, times, t0, gravity, drag, fixed, dt=.002):
    n = int(math.ceil((times.max() - t0) / dt)) + 1
    position, velocity = theta[:, :3].copy(), theta[:, 3:6].copy()
    extra = theta[:, 6:9] if theta.shape[1] == 9 else fixed
    path = np.empty((n + 1, len(theta), 3))
    path[0] = position
    for step in range(1, n + 1):
        speed = np.sqrt(np.sum(velocity * velocity, axis=1))[:, None]
        velocity += (gravity - drag * speed * velocity + extra) * dt
        position += velocity * dt
        path[step] = position
    index = (times - t0) / dt
    lower = np.clip(np.floor(index).astype(int), 0, n - 1)
    fraction = (index - lower)[:, None, None]
    return (path[lower] * (1 - fraction) + path[lower + 1] * fraction).transpose(1, 0, 2)


def fit_flight(obs, n_iter=6, fit_accel=False, a_fixed=None, *, gravity, drag):
    if len(obs) < 2:
        return None
    observations = sorted(obs, key=lambda item: item[0])
    times = np.array([item[0] for item in observations])
    measured = np.array([item[1] for item in observations])
    t0 = times[0]
    fixed = np.zeros(3) if a_fixed is None else np.asarray(a_fixed, float)
    if len(obs) == 2:
        velocity = (measured[1] - measured[0]) / (times[1] - times[0]) - .5 * gravity * (times[1] - times[0])
        return t0, measured[0], velocity, fixed, 0.0
    design = np.vstack([np.ones_like(times), times - t0, (times - t0) ** 2]).T
    coefficients = np.linalg.lstsq(design, measured, rcond=None)[0]
    npar = 9 if fit_accel and a_fixed is None and len(obs) >= 6 else 6
    theta = np.r_[coefficients[0], coefficients[1], np.zeros(3)][:npar]
    regularization = np.eye(npar) * 1e-6
    if npar == 9:
        regularization[6:, 6:] = np.eye(3) * 1e-2
    for _ in range(n_iter):
        batch = np.tile(theta, (npar + 1, 1))
        batch[1:] += np.eye(npar) * 1e-4
        predicted = _positions(batch, times, t0, gravity, drag, fixed)
        residual = measured.ravel() - predicted[0].ravel()
        jacobian = ((predicted[1:] - predicted[0]) / 1e-4).reshape(npar, -1).T
        delta = np.linalg.solve(jacobian.T @ jacobian + regularization, jacobian.T @ residual)
        theta += delta
        if np.linalg.norm(delta) < 1e-6:
            break
    predicted = _positions(theta[None, :], times, t0, gravity, drag, fixed)[0]
    error = float(np.sqrt(np.mean((measured - predicted) ** 2)))
    return t0, theta[:3], theta[3:6], theta[6:9] if npar == 9 else fixed, error

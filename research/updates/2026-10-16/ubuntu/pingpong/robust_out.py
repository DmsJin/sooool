"""Optional outgoing-ball solver; no native/world changes or automatic execution.

For the public gravity + isotropic drag model, vx/vy stays constant. Solve that
ratio directly, then bracket the vertical speed against a continuous interpolated
table-plane crossing. Always verify the result at finer resolution before exposing
it. This assumes no outgoing spin/Magnus and establishes no robot feasibility.
"""
import math
import numpy as np
import builtin_players as physics


def _flight(p, velocity, dt, duration):
    # Same semi-implicit Euler law as public rollout(bounce=False), stopping
    # once the first descending table-plane crossing is known. Scalar locals
    # avoid allocating a full position/velocity trajectory for each root probe.
    px, py, pz = map(float, p)
    vx, vy, vz = map(float, velocity)
    gx, gy, gz = map(float, physics.G)
    drag, radius = float(physics.KD), float(physics.BALL_R)
    net_height = None
    for _ in range(int(duration / dt)):
        ax, ay, az = px, py, pz
        speed = math.sqrt(vx*vx + vy*vy + vz*vz)
        vx += (gx - drag*speed*vx)*dt
        vy += (gy - drag*speed*vy)*dt
        vz += (gz - drag*speed*vz)*dt
        px += vx*dt; py += vy*dt; pz += vz*dt
        crossed = az >= radius > pz
        fraction = (az-radius)/(az-pz) if crossed else 1.
        if net_height is None and ay < 0 <= py:
            net_fraction = -ay/(py-ay)
            if net_fraction <= fraction:
                net_height = az + net_fraction*(pz-az)
        if crossed:
            return np.array([ax+fraction*(px-ax), ay+fraction*(py-ay), radius]), net_height
    return None


def solve_out_robust(p, aim, vy=4.2, *, net_margin_m=.03,
                     landing_tolerance_m=.01, dt=.002, duration_s=2.5):
    """Return (velocity or None, evidence); not integrated into any action menu.

    The allowed search vz interval is [-2, 8] m/s. Rejection never returns a bad
    velocity as a usable candidate. Evidence describes only public analytical
    trajectory checks, not native ball delivery or robot dynamics.
    """
    p, aim = np.asarray(p, float), np.asarray(aim, float)
    evidence = {'scope': 'public analytical outgoing flight; no execution', 'verified': False}
    if (p.shape != (3,) or aim.shape != (2,) or not np.all(np.isfinite(p))
            or not np.all(np.isfinite(aim)) or not np.isfinite(vy) or vy <= 0
            or p[2] <= physics.BALL_R or p[1] >= 0 or aim[1] <= 0
            or abs(aim[0]) > physics.TABLE_X or aim[1] > physics.TABLE_Y
            or not (0 < dt <= .004 and 0 < duration_s <= 5)
            or not (np.isfinite(net_margin_m) and net_margin_m >= 0)
            or not (0 < landing_tolerance_m <= .01)):
        evidence['reason'] = 'invalid or unsupported input'
        return None, evidence
    velocity = np.array([vy * (aim[0] - p[0]) / (aim[1] - p[1]), vy, 0.])

    def evaluate(vz, resolution):
        velocity[2] = vz
        return _flight(p, velocity, resolution, duration_s)

    lo, hi = -2., 8.
    left, right = evaluate(lo, dt), evaluate(hi, dt)
    if left is None or right is None or not left[0][1] <= aim[1] <= right[0][1]:
        evidence['reason'] = 'target not bracketed within bounded vertical-speed search'
        return None, evidence
    # Bisection avoids the quantized-first-bounce finite-difference Jacobian.
    for _ in range(24):
        mid = (lo + hi) / 2
        value = evaluate(mid, dt)
        if value is None:
            evidence['reason'] = 'flight horizon insufficient during search'
            return None, evidence
        if value[0][1] < aim[1]:
            lo = mid
        else:
            hi = mid
        if np.linalg.norm(value[0][:2] - aim) < landing_tolerance_m / 4:
            break
    fine = evaluate(mid, dt / 2)
    if fine is None:
        evidence['reason'] = 'fine-resolution validation has no landing'
        return None, evidence
    landing, height = fine
    error = float(np.linalg.norm(landing[:2] - aim))
    clearance = None if height is None else height - physics.NET_Z - physics.BALL_R
    verified = (error <= landing_tolerance_m and abs(landing[0]) <= physics.TABLE_X
                and 0 < landing[1] <= physics.TABLE_Y
                and clearance is not None and clearance >= net_margin_m)
    evidence.update(verified=bool(verified), reason='verified analytical trajectory' if verified else 'trajectory validation failed',
                    landing_xy=landing[:2].tolist(), landing_error_m=error,
                    net_center_height_m=height, net_clearance_m=clearance,
                    required_net_margin_m=net_margin_m, validation_dt_s=dt / 2,
                    validation_model='public gravity + isotropic drag; interpolated descending table-plane crossing')
    # Also require the unchanged public landing helper to accept the trajectory.
    # Its discretized output can reject an otherwise accurate interpolated root;
    # prefer withholding that candidate over relaxing its evidence checks.
    if verified:
        public_landing, public_clear = physics.landing(p, velocity)
        public_error = None if public_landing is None else float(np.linalg.norm(public_landing - aim))
        verified = bool(public_clear and public_error is not None and public_error <= landing_tolerance_m)
        evidence.update(verified=verified,
                        original_public_landing_xy=None if public_landing is None else public_landing.tolist(),
                        original_public_landing_error_m=public_error,
                        original_public_net_clear=bool(public_clear))
        if not verified:
            evidence['reason'] = 'unchanged public landing helper rejected trajectory'
    return (velocity.copy() if verified else None), evidence

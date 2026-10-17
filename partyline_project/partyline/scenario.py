"""Synthetic single-sector scenario generator.

Produces (independently of any coding scheme):
  * aircraft trajectories (piecewise constant velocity along a route),
  * versioned clearances (initial + speed/heading updates) issued by a "controller",
  * for every clearance, the set of OTHER aircraft for which it is relevant,
    with a per-pair deadline.

Relevance and deadlines use the controller's planned trajectories (NOT ADS-B as
side information). Relevance = predicted proximity (< R_rel NM) within horizon H,
or shared resource (same landing runway sequence) within H.
Deadline = predicted time separation drops below R_alert minus (processing +
crew response + manoeuvre margin); fallback = end of horizon (explicit modelling choice).
"""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Clearance:
    cid: int            # message id (unique per version)
    ac: int             # aircraft the clearance is addressed to
    version: int
    t_issue: float      # seconds
    demanders: dict = field(default_factory=dict)   # other aircraft -> deadline (absolute s)


@dataclass
class Params:
    area: float = 120.0          # NM, square sector side
    rate_per_min: float = 2.0    # aircraft arrival rate
    duration_min: float = 40.0   # arrival window
    speed_kt: float = 250.0
    update_rate_per_min: float = 0.25   # per-aircraft clearance update rate
    horizon_s: float = 300.0     # look-ahead H
    r_rel: float = 15.0          # NM relevance radius
    r_alert: float = 8.0         # NM proximity regarded as conflict
    margin_s: float = 90.0       # processing + crew response + manoeuvre
    n_routes: int = 4
    seed: int = 0


class Aircraft:
    def __init__(self, idx, t0, route, speed):
        self.idx, self.t0, self.route = idx, t0, route
        self.segs = [(t0, route[0], speed)]   # (t_start, start_pos, speed) piecewise; heading from route
        self.route = route
        self.speeds = [(t0, speed)]

    def set_speed(self, t, v):
        self.speeds.append((t, v))

    def pos(self, t, extra=None):
        """Position at time t following route with piecewise-constant speed."""
        speeds = sorted(self.speeds + ([extra] if extra else []))
        d, tt, v = 0.0, speeds[0][0], speeds[0][1]
        for ts, vs in speeds[1:]:
            if ts >= t:
                break
            d += v * (ts - tt) / 3600.0
            tt, v = ts, vs
        if t < self.t0:
            return None
        d += v * (t - tt) / 3600.0
        return self._along(d)

    def pos_arr(self, ts):
        """Vectorised positions for array ts; NaN where not active. Shape (len(ts),2)."""
        ts = np.asarray(ts, float)
        sp = sorted(self.speeds)
        tb = np.array([x[0] for x in sp]); vb = np.array([x[1] for x in sp])
        # cumulative distance at breakpoints
        cum = np.concatenate([[0.0], np.cumsum(vb[:-1] * np.diff(tb) / 3600.0)])
        k = np.clip(np.searchsorted(tb, ts, side="right") - 1, 0, len(tb) - 1)
        d = cum[k] + vb[k] * (ts - tb[k]) / 3600.0
        pts = np.array(self.route)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        cs = np.concatenate([[0.0], np.cumsum(seg)])
        x = np.interp(d, cs, pts[:, 0]); y = np.interp(d, cs, pts[:, 1])
        out = np.stack([x, y], 1)
        out[(ts < self.t0) | (d > cs[-1])] = np.nan
        return out

    def _along(self, d):
        pts = self.route
        for a, b in zip(pts[:-1], pts[1:]):
            L = np.linalg.norm(b - a)
            if d <= L:
                return a + (b - a) * (d / L)
            d -= L
        return None   # left the sector / landed

    def active(self, t, extra=None):
        return self.pos(t, extra) is not None


def make_routes(p, rng):
    c = np.array([p.area / 2, p.area / 2])
    routes = []
    for k in range(p.n_routes):
        ang = 2 * np.pi * k / p.n_routes + 0.3
        start = c + (p.area / 2) * np.array([np.cos(ang), np.sin(ang)])
        fix = c + 12 * np.array([np.cos(ang), np.sin(ang)])
        rwy = c + np.array([0.0, -3.0])
        routes.append([start, fix, c, rwy])
    return routes


def generate(p: Params):
    rng = np.random.default_rng(p.seed)
    routes = make_routes(p, rng)
    # Poisson arrivals
    n = rng.poisson(p.rate_per_min * p.duration_min)
    t_arr = np.sort(rng.uniform(0, p.duration_min * 60, n))
    ac = []
    for i, t0 in enumerate(t_arr):
        r = routes[rng.integers(p.n_routes)]
        ac.append(Aircraft(i, t0, r, p.speed_kt * rng.uniform(0.9, 1.1)))
    # clearance events: initial at t0, updates Poisson
    events = []  # (t, ac_idx, new_speed)
    for a in ac:
        events.append((a.t0, a.idx, a.speeds[0][1]))
        T = a.t0
        while True:
            T += rng.exponential(60.0 / p.update_rate_per_min)
            if T > a.t0 + 900:      # ~15 min in sector
                break
            events.append((T, a.idx, p.speed_kt * rng.uniform(0.7, 1.15)))
    events.sort()
    clearances, ver = [], {}
    for cid, (t, i, v) in enumerate(events):
        if not ac[i].active(t) and t > ac[i].t0:
            continue
        if t > ac[i].t0:
            ac[i].set_speed(t, v)
        ver[i] = ver.get(i, -1) + 1
        c = Clearance(len(clearances), i, ver[i], t)
        # relevance by controller's plan, evaluated over horizon at 5 s resolution
        ts = np.arange(t, t + p.horizon_s + 1, 5.0)
        PI = ac[i].pos_arr(ts)
        for j in ac:
            if j.idx == i or j.t0 > t or not j.active(t):
                continue
            dist = np.linalg.norm(PI - j.pos_arr(ts), axis=1)
            dist = np.where(np.isnan(dist), np.inf, dist)
            alert = np.nonzero(dist < p.r_alert)[0]
            first_alert = ts[alert[0]] if len(alert) else None
            close = bool((dist < p.r_rel).any())
            if first_alert is not None:
                c.demanders[j.idx] = max(t, first_alert - p.margin_s)
            elif close:
                c.demanders[j.idx] = t + p.horizon_s
        clearances.append(c)
    return ac, clearances

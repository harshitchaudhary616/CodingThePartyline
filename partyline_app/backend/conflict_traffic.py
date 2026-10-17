"""Conflict-driven clearance generation (replaces the random Poisson clearance times of partyline.engine).

A controller issues a clearance when a loss of separation is predicted. We therefore generate clearance events from the real
aircraft tracks: at every trajectory step, for every pair of airborne aircraft, look ahead H seconds along the planned path;
if the pair comes closer than r_alert horizontally while within vsep vertically, a conflict is predicted. The first step at which
a pair enters that state emits one clearance to one aircraft of the pair (the one that has not been cleared for the longest
time), subject to a cooldown per pair and per aircraft. Each aircraft also gets one clearance when it first appears in the
window (sector entry / initial contact), as in the random model. A routine background rate (upd_rate, per aircraft per minute) can
be added on top; 0 gives pure conflict-driven traffic. The critical receivers and deadlines of every clearance still come from
partyline.engine.build_clearances (the same geometry), so only WHEN and TO WHOM a clearance is issued changes.

  from conflict_traffic import from_tracks_conflict
  scn = from_tracks_conflict(rows, dict(upd_rate=0.0), seed)
"""
import numpy as np
from partyline import engine as E

COOLDOWN_PAIR = 300.0       # s before the same pair can trigger another clearance
COOLDOWN_AC = 60.0          # s between clearances to the same aircraft triggered by conflicts


def conflict_events(scn, p, rng):
    n, K, M = scn.n, scn.K, int(p["H"] // E.DT)
    last_pair, last_ac, state = {}, {}, {}
    ev = []
    for k in range(K):
        t = k * E.DT
        ks = np.arange(k, min(k + M + 1, K))
        act = [i for i in range(n) if E._active(scn, i, k)]
        for a in range(len(act)):
            i = act[a]
            for b in range(a + 1, len(act)):
                j = act[b]
                dx, dy = scn.X[i, ks] - scn.X[j, ks], scn.Y[i, ks] - scn.Y[j, ks]
                d = np.hypot(dx, dy)
                ok = ~np.isnan(d) & (np.abs(scn.Z[i, ks] - scn.Z[j, ks]) <= p["vsep"])
                now = bool(ok.any() and (np.where(ok, d, np.inf) < p["r_alert"]).any())
                was = state.get((i, j), False)
                state[(i, j)] = now
                if not now or was:
                    continue
                if t - last_pair.get((i, j), -1e9) < COOLDOWN_PAIR:
                    continue
                cands = sorted((i, j), key=lambda x: last_ac.get(x, -1e9))      # longest since last clearance first
                if rng.random() < 0.5 and last_ac.get(cands[0], -1e9) == last_ac.get(cands[1], -1e9):
                    cands = cands[::-1]
                for c in cands:
                    if t - last_ac.get(c, -1e9) >= COOLDOWN_AC:
                        ev.append((t, c)); last_ac[c] = t; last_pair[(i, j)] = t
                        break
    return ev


def from_tracks_conflict(rows, params, seed):
    p = E.clean(params, E.DEFAULTS)
    scn = E.from_tracks(rows, dict(params, upd_rate=0.0), seed)           # tracks only; routine clearances added below
    rng = np.random.default_rng(seed + 7)
    ev = [(a * E.DT, i) for i, (a, b) in enumerate(zip(scn.first, scn.last)) if a <= b]   # first contact
    ev += conflict_events(scn, p, rng)
    if p["upd_rate"] > 0:
        ev += [e for e in E._events_poisson(scn.first, scn.last, p["upd_rate"], rng)]
        ev = sorted(set(ev))
    ev.sort()
    scn.clearances = E.build_clearances(scn, ev, p)
    return scn
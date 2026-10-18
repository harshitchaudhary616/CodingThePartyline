"""Causal (online) relevance classes: what a ground system could compute at issue time, without the recorded future.

The main study derives the critical receivers and deadlines of a clearance from the recorded tracks over the next H seconds
(an oracle for the controller's planned trajectories), and admits an awareness receiver only if it is still airborne A s later.
Here both use only the past:
  * critical: every aircraft is projected at constant velocity (and constant vertical rate) from its last BACK seconds of track;
    the same alert/relevance rule as engine.build_clearances is applied to the projected paths.
  * awareness: every aircraft on the same sector frequency at issue time (no look-ahead to whether it is still airborne).
patch() installs both; overlap(scn_causal, scn_oracle) gives recall and precision of the causal critical set against the oracle one."""
import copy
import math
import numpy as np
from partyline import engine as E
from partyline.engine import Clearance, DT, _active
from awareness import A_DEFAULT, SECTOR_DEFAULT, R_AWARE_DEFAULT, _sector

BACK = 30.0          # seconds of past track used for the velocity estimate


def _state(scn, i, k0):
    """position and velocity per step of aircraft i at step k0 from its own past (velocity 0 if no past)."""
    kb = max(0, k0 - int(BACK // DT))
    while kb < k0 and not _active(scn, i, kb):
        kb += 1
    p = np.array([scn.X[i, k0], scn.Y[i, k0], scn.Z[i, k0]])
    if kb < k0:
        v = (p - np.array([scn.X[i, kb], scn.Y[i, kb], scn.Z[i, kb]])) / (k0 - kb)
    else:
        v = np.zeros(3)
    return p, v


def build_clearances_causal(scn, events, p):
    M = int(p["H"] // DT)
    out, ver = [], [-1] * scn.n
    steps = np.arange(0, M + 1)
    for t, i in events:
        k0 = int(t // DT)
        if not _active(scn, i, k0):
            if _active(scn, i, k0 + 1):
                k0 += 1
            else:
                continue
        ver[i] += 1
        c = Clearance(len(out), i, ver[i], t)
        pi, vi = _state(scn, i, k0)
        Pi = pi[None, :] + steps[:, None] * vi[None, :]
        for j in range(scn.n):
            if j == i or not _active(scn, j, k0):
                continue
            pj, vj = _state(scn, j, k0)
            Pj = pj[None, :] + steps[:, None] * vj[None, :]
            d = np.hypot(Pi[:, 0] - Pj[:, 0], Pi[:, 1] - Pj[:, 1])
            ok = np.abs(Pi[:, 2] - Pj[:, 2]) <= p["vsep"]
            if not ok.any():
                continue
            d = np.where(ok, d, np.inf)
            alert = np.nonzero(d < p["r_alert"])[0]
            if len(alert):
                c.dem[j] = max(t, (k0 + float(alert[0])) * DT - p["margin"])
            elif (d < p["r_rel"]).any():
                c.dem[j] = t + p["H"]
        out.append(c)
    return out


def with_awareness_causal(scn, A=A_DEFAULT, sector=SECTOR_DEFAULT, r_aware=R_AWARE_DEFAULT):
    s2 = copy.copy(scn)
    s2.clearances = []
    aware, critical = set(), set()
    x0, y0 = scn.bounds[0], scn.bounds[1]
    for c in scn.clearances:
        d = dict(c.dem)
        critical |= {(c.cid, r) for r in c.dem}
        k0 = int(c.t // DT)
        ki = k0 if _active(scn, c.ac, k0) else k0 + 1
        if _active(scn, c.ac, ki):
            xi, yi = scn.X[c.ac, ki], scn.Y[c.ac, ki]
            si = _sector(xi, yi, sector, x0, y0) if sector > 0 else None
            for j in range(scn.n):
                if j == c.ac or j in d or not _active(scn, j, ki):
                    continue
                xj, yj = scn.X[j, ki], scn.Y[j, ki]
                same = (_sector(xj, yj, sector, x0, y0) == si) if sector > 0 else (math.hypot(xj - xi, yj - yi) <= r_aware)
                if same:
                    d[j] = c.t + A
                    aware.add((c.cid, j))
        s2.clearances.append(Clearance(c.cid, c.ac, c.version, c.t, d))
    s2.aware, s2.critical = aware, critical
    return s2


_orig_build = E.build_clearances


def patch(EP=None):
    E.build_clearances = build_clearances_causal
    if EP is not None:
        EP.with_awareness = with_awareness_causal


def overlap(rows, params, seed):
    """recall and precision of the causal critical (clearance, aircraft) pairs against the oracle ones, same tracks and clearance times."""
    b, E.build_clearances = E.build_clearances, _orig_build
    try:
        so = E.from_tracks(rows, params, seed)
    finally:
        E.build_clearances = b
    p = E.clean(params, E.DEFAULTS)
    ev = [(c.t, c.ac) for c in so.clearances]
    cc = build_clearances_causal(so, ev, p)
    O = {(c.t, c.ac, r) for c in so.clearances for r in c.dem}
    C = {(c.t, c.ac, r) for c in cc for r in c.dem}
    inter = len(O & C)
    return dict(oracle=len(O), causal=len(C), recall=inter / len(O) if O else None, precision=inter / len(C) if C else None)

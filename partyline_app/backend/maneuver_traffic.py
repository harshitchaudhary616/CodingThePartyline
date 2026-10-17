"""Manoeuvre-derived clearances: clearance events taken from what the REAL aircraft did, not from a random process or a conflict rule.

A controller instruction is followed by a visible change in the flight path: a turn (heading), a climb or descent (vertical rate) or a
speed change. We detect those changes in the recorded ADS-B track and place a clearance LEAD seconds before the onset of each one (the
instruction has to be issued, read and executed before the manoeuvre starts). This is a PROXY: some manoeuvres are pilot- or FMS-initiated
(no controller instruction), and some instructions ("maintain", "report") change nothing; the paper must say so. What it removes is the
assumption that clearance times are random or follow our own conflict rule: they now follow the observed behaviour of real traffic.
The critical receivers and deadlines of every clearance still come from partyline.engine.build_clearances (planned-path geometry).

Detected manoeuvres (thresholds are parameters; tracks are the 5 s resampled positions, smoothed over SMOOTH samples):
    turn      heading deviates from the reference heading by >= HDG_MIN degrees (reference resets once the heading is steady again)
    vertical  vertical-rate state changes between level (|vr| < VR_LEVEL fpm), climb (> VR_ON) and descent (< -VR_ON)
    speed     ground speed deviates from the reference by >= SPD_MIN knots (reference resets once the speed is steady again)
Events of one aircraft closer than COOLDOWN seconds are merged; every aircraft also gets one clearance at first contact (as in the other modes).

  from maneuver_traffic import from_tracks_maneuver, detect
"""
import math
import numpy as np
from partyline import engine as E

LEAD = 30.0          # s between the clearance and the observed onset of the manoeuvre
HDG_MIN = 20.0       # deg
SPD_MIN = 25.0       # kt
VR_ON, VR_LEVEL = 500.0, 250.0     # ft/min
SMOOTH = 6           # samples (30 s)
COOLDOWN = 60.0      # s
MIN_SPEED = 80.0     # kt: below this the heading is meaningless
STEADY_DEG, STEADY_KT = 3.0, 6.0   # per 15 s: "steady again"


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def _smooth(v, w):
    out = np.full(v.shape, np.nan)
    if len(v) >= w:
        c = np.convolve(v, np.ones(w) / w, mode="valid")
        out[w // 2: w // 2 + len(c)] = c
    return out


def _segments(ok):
    """contiguous runs of True as (start, end) index pairs, end exclusive"""
    idx = np.flatnonzero(ok)
    if not len(idx):
        return []
    cut = np.flatnonzero(np.diff(idx) > 1)
    st = np.concatenate([[idx[0]], idx[cut + 1]])
    en = np.concatenate([idx[cut], [idx[-1]]]) + 1
    return list(zip(st, en))


def detect_one(X, Y, Z, kinds=("turn", "vertical", "speed")):
    """onset times (s) and kinds of the manoeuvres in one aircraft's track"""
    dt = E.DT
    ev = []
    for a, b in _segments(~np.isnan(X)):
        if b - a < 4 * SMOOTH:
            continue
        x, y, z = X[a:b], Y[a:b], Z[a:b]
        vx = _smooth(np.gradient(x) / dt * 3600.0, SMOOTH)
        vy = _smooth(np.gradient(y) / dt * 3600.0, SMOOTH)
        vr = _smooth(np.gradient(z) / dt * 60.0, SMOOTH)
        gs = np.hypot(vx, vy)
        hd = np.degrees(np.arctan2(vx, vy))
        n = len(x)
        s = int(15.0 // dt)
        if "turn" in kinds:
            ref, hold, onset = None, False, None
            for k in range(SMOOTH, n - SMOOTH):
                if np.isnan(hd[k]) or gs[k] < MIN_SPEED:
                    continue
                if ref is None:
                    ref = hd[k]
                dev = abs(_wrap(hd[k] - ref))
                if not hold:
                    if dev < STEADY_DEG:
                        onset = k
                    elif dev >= HDG_MIN:
                        ev.append(((a + (onset if onset is not None else k)) * dt, "turn")); hold = True
                else:
                    if k >= s and not np.isnan(hd[k - s]) and abs(_wrap(hd[k] - hd[k - s])) < STEADY_DEG:
                        ref, hold, onset = hd[k], False, k
        if "vertical" in kinds:
            state, onset = "level", None
            for k in range(SMOOTH, n - SMOOTH):
                if np.isnan(vr[k]):
                    continue
                new = "climb" if vr[k] > VR_ON else ("descend" if vr[k] < -VR_ON else ("level" if abs(vr[k]) < VR_LEVEL else state))
                if new != state:
                    if new != "level":
                        j = k
                        while j > 0 and not np.isnan(vr[j - 1]) and abs(vr[j - 1]) > VR_LEVEL and (vr[j - 1] > 0) == (vr[k] > 0):
                            j -= 1                      # walk back to where the rate started to build
                        ev.append(((a + j) * dt, "vertical"))
                    state = new
        if "speed" in kinds:
            ref, hold, onset = None, False, None
            for k in range(SMOOTH, n - SMOOTH):
                if np.isnan(gs[k]):
                    continue
                if ref is None:
                    ref = gs[k]
                dev = abs(gs[k] - ref)
                if not hold:
                    if dev < STEADY_KT:
                        onset = k
                    elif dev >= SPD_MIN:
                        ev.append(((a + (onset if onset is not None else k)) * dt, "speed")); hold = True
                else:
                    if k >= s and not np.isnan(gs[k - s]) and abs(gs[k] - gs[k - s]) < STEADY_KT:
                        ref, hold, onset = gs[k], False, k
    return sorted(ev)


def detect(scn, kinds=("turn", "vertical", "speed")):
    """[(onset_time, aircraft_index, kind)] for the whole scenario"""
    out = []
    for i in range(scn.n):
        for t, kd in detect_one(scn.X[i], scn.Y[i], scn.Z[i], kinds):
            out.append((t, i, kd))
    return sorted(out)


def from_tracks_maneuver(rows, params, seed, lead=None, kinds=("turn", "vertical", "speed")):
    p = E.clean(params, E.DEFAULTS)
    scn = E.from_tracks(rows, dict(params, upd_rate=0.0), seed)
    lead = LEAD if lead is None else lead
    ev = [(a * E.DT, i) for i, (a, b) in enumerate(zip(scn.first, scn.last)) if a <= b]          # first contact
    last, stats = {}, {"turn": 0, "vertical": 0, "speed": 0}
    for t, i, kd in detect(scn, kinds):
        tc = max(t - lead, scn.first[i] * E.DT)
        if tc - last.get(i, -1e9) < COOLDOWN:
            continue
        last[i] = tc
        ev.append((tc, i)); stats[kd] += 1
    if p["upd_rate"] > 0:
        rng = np.random.default_rng(seed + 7)
        ev += [e for e in E._events_poisson(scn.first, scn.last, p["upd_rate"], rng)]
    ev = sorted(set(ev))
    scn.clearances = E.build_clearances(scn, ev, p)
    scn.maneuver_stats = stats
    return scn

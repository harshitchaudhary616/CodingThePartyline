"""Scenario building (synthetic or recorded tracks) and channel simulation with full playback logs.

All results are SIMULATION. Recorded tracks supply aircraft paths only; clearances are simulated.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
from .coding import SCHEMES

DT = 5.0  # trajectory grid step, seconds

DEFAULTS = dict(area=120.0, rate=1.5, dur_min=30.0, speed=250.0, upd_rate=0.25, H=300.0, r_rel=15.0,
                r_alert=8.0, margin=90.0, n_routes=4, vsep=2000.0, max_aircraft=90)
CH_DEFAULTS = dict(airtime=0.4, access=0.8, bg=0.3, loss=0.05, overhear=0.0)

LIMITS = dict(rate=(0.1, 6.0), dur_min=(5, 60), upd_rate=(0.0, 2.0), H=(60, 900), r_rel=(2, 40), r_alert=(1, 30),
              margin=(0, 300), vsep=(0, 10000), max_aircraft=(2, 120), airtime=(0.01, 5), access=(0.0, 10),
              bg=(0.0, 0.9), loss=(0.0, 0.6), overhear=(0.0, 1.0))


def clean(params: dict, defaults: dict) -> dict:
    """Validate + clamp numeric parameters; unknown keys are rejected."""
    out = dict(defaults)
    for k, v in (params or {}).items():
        if k not in defaults:
            raise ValueError(f"unknown parameter: {k}")
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"parameter {k} must be a number")
        if not math.isfinite(v):
            raise ValueError(f"parameter {k} must be finite")
        lo, hi = LIMITS.get(k, (-1e9, 1e9))
        if not lo <= v <= hi:
            raise ValueError(f"parameter {k} must be between {lo} and {hi}")
        out[k] = v
    return out


@dataclass
class Clearance:
    cid: int
    ac: int
    version: int
    t: float
    dem: dict = field(default_factory=dict)   # receiver -> deadline (s)


@dataclass
class Scenario:
    ids: list
    X: np.ndarray            # (n, K) NM, NaN when inactive
    Y: np.ndarray
    Z: np.ndarray            # feet
    first: list
    last: list
    kind: str                # synthetic | recorded
    bounds: tuple
    centre: tuple
    params: dict
    routes: list = field(default_factory=list)
    clearances: list = field(default_factory=list)

    @property
    def n(self): return len(self.ids)

    @property
    def K(self): return self.X.shape[1]


# ------------------------------------------------------------------ clearances
def build_clearances(scn: Scenario, events, p) -> list:
    """events: list of (t, aircraft). Relevance and per-pair deadlines from the PLANNED paths."""
    M = int(p["H"] // DT)
    out, ver = [], [-1] * scn.n
    for t, i in events:
        k0 = int(t // DT)
        if not (_active(scn, i, k0) or _active(scn, i, k0 + 1)):
            continue
        ver[i] += 1
        c = Clearance(len(out), i, ver[i], t)
        ks = np.arange(k0, min(k0 + M + 1, scn.K))
        xi, yi, zi = scn.X[i, ks], scn.Y[i, ks], scn.Z[i, ks]
        for j in range(scn.n):
            if j == i or not _active(scn, j, k0):
                continue
            dx, dy = xi - scn.X[j, ks], yi - scn.Y[j, ks]
            d = np.hypot(dx, dy)
            ok = ~np.isnan(d) & (np.abs(zi - scn.Z[j, ks]) <= p["vsep"])
            if not ok.any():
                continue
            d = np.where(ok, d, np.inf)
            alert = np.nonzero(d < p["r_alert"])[0]
            if len(alert):
                c.dem[j] = max(t, float(ks[alert[0]]) * DT - p["margin"])
            elif (d < p["r_rel"]).any():
                c.dem[j] = t + p["H"]
        out.append(c)
    return out


def _active(scn, i, k):
    return 0 <= k < scn.K and not np.isnan(scn.X[i, k])


def _events_poisson(first, last, upd_rate, rng):
    ev = []
    for i, (a, b) in enumerate(zip(first, last)):
        if a > b:
            continue
        ts, te = a * DT, b * DT
        ev.append((ts, i))
        if upd_rate > 0:
            T = ts
            while True:
                T += rng.exponential(60.0 / upd_rate)
                if T > te or T > ts + 900:
                    break
                ev.append((T, i))
    ev.sort()
    return ev


# ------------------------------------------------------------------ synthetic
def make_synthetic(params: dict, seed: int) -> Scenario:
    p = clean(params, DEFAULTS)
    rng = np.random.default_rng(seed)
    c = p["area"] / 2
    routes = []
    for k in range(int(p["n_routes"])):
        ang = 2 * math.pi * k / p["n_routes"] + 0.3
        cs, sn = math.cos(ang), math.sin(ang)
        routes.append(np.array([[c + c * cs, c + c * sn], [c + 12 * cs, c + 12 * sn], [c, c], [c, c - 3]]))
    n = int(min(rng.poisson(p["rate"] * p["dur_min"]), p["max_aircraft"]))
    t0s = np.sort(rng.uniform(0, p["dur_min"] * 60, n))
    K = int((p["dur_min"] * 60 + 1500) // DT) + 1
    X = np.full((n, K), np.nan); Y = np.full((n, K), np.nan); Z = np.full((n, K), 3000.0)
    first, last, ids, ev_speed = [], [], [], []
    for i in range(n):
        route = routes[rng.integers(len(routes))]
        sched = [(t0s[i], p["speed"] * rng.uniform(0.9, 1.1))]
        T = t0s[i]
        while p["upd_rate"] > 0:
            T += rng.exponential(60.0 / p["upd_rate"])
            if T > t0s[i] + 900:
                break
            sched.append((T, p["speed"] * rng.uniform(0.7, 1.15)))
        seg = np.linalg.norm(np.diff(route, axis=0), axis=1)
        cs_ = np.concatenate([[0], np.cumsum(seg)])
        st = np.array([s[0] for s in sched]); sv = np.array([s[1] for s in sched])
        ts = np.arange(K) * DT
        idx = np.clip(np.searchsorted(st, ts, side="right") - 1, 0, len(st) - 1)
        step = np.where(ts >= st[0], sv[idx] * DT / 3600.0, 0.0)
        d = np.cumsum(step)
        k_start = int(math.ceil(st[0] / DT))
        if k_start < K:
            d = d - d[k_start]
        act = (ts >= st[0]) & (d <= cs_[-1])
        X[i] = np.where(act, np.interp(d, cs_, route[:, 0]), np.nan)
        Y[i] = np.where(act, np.interp(d, cs_, route[:, 1]), np.nan)
        w = np.nonzero(act)[0]
        first.append(int(w[0]) if len(w) else 0); last.append(int(w[-1]) if len(w) else -1)
        ids.append(f"AC{i:03d}")
    scn = Scenario(ids, X, Y, Z, first, last, "synthetic", (0, 0, p["area"], p["area"]), (c, c), p,
                   routes=[r.tolist() for r in routes])
    # clearance events: initial + speed updates (rate-matched, independent of trajectory solver)
    ev = _events_poisson(first, last, p["upd_rate"], rng)
    scn.clearances = build_clearances(scn, ev, p)
    return scn


# ------------------------------------------------------------------ recorded tracks
def from_tracks(rows, params: dict, seed: int) -> Scenario:
    """rows: iterable of (t, icao24, lat, lon, alt_m, onground). Returns scenario with SIMULATED clearances."""
    p = clean(params, DEFAULTS)
    by = {}
    for t, ic, lat, lon, alt, gnd in rows:
        if gnd or lat is None or lon is None:
            continue
        by.setdefault(ic, []).append((float(t), float(lat), float(lon), float(alt or 0.0)))
    tracks = [(ic, sorted(a)) for ic, a in by.items() if len(a) >= 8]
    if len(tracks) < 2:
        raise ValueError("need at least 2 aircraft with 8+ airborne position reports")
    tracks.sort(key=lambda x: -len(x[1]))
    tracks = tracks[: int(p["max_aircraft"])]
    tmin = min(a[0][0] for _, a in tracks); tmax = max(a[-1][0] for _, a in tracks)
    lat0 = float(np.mean([a[0][1] for _, a in tracks])); lon0 = float(np.mean([a[0][2] for _, a in tracks]))
    kx = 60.0 * math.cos(math.radians(lat0))
    K = int((tmax - tmin) // DT) + 1
    n = len(tracks)
    X = np.full((n, K), np.nan); Y = np.full((n, K), np.nan); Z = np.zeros((n, K))
    first, last, ids = [], [], []
    grid = tmin + np.arange(K) * DT
    for i, (ic, a) in enumerate(tracks):
        arr = np.array(a)
        t, la, lo, al = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        inside = (grid >= t[0]) & (grid <= t[-1])
        x = np.interp(grid, t, (lo - lon0) * kx); y = np.interp(grid, t, (la - lat0) * 60.0)
        z = np.interp(grid, t, al) * 3.28084
        # reject interpolation across reporting gaps > 120 s
        j = np.clip(np.searchsorted(t, grid, side="right"), 1, len(t) - 1)
        gap = (t[j] - t[j - 1]) > 120
        ok = inside & ~gap
        X[i] = np.where(ok, x, np.nan); Y[i] = np.where(ok, y, np.nan); Z[i] = np.where(ok, z, 0.0)
        w = np.nonzero(ok)[0]
        first.append(int(w[0]) if len(w) else 0); last.append(int(w[-1]) if len(w) else -1)
        ids.append(str(ic).upper())
    fin = ~np.isnan(X)
    pad = 8.0
    b = (float(np.nanmin(X)) - pad, float(np.nanmin(Y)) - pad, float(np.nanmax(X)) + pad, float(np.nanmax(Y)) + pad)
    scn = Scenario(ids, X, Y, Z, first, last, "recorded", b, (0.0, 0.0), p)
    rng = np.random.default_rng(seed)
    scn.clearances = build_clearances(scn, _events_poisson(first, last, p["upd_rate"], rng), p)
    scn.t0_epoch = tmin
    return scn


# ------------------------------------------------------------------ channel simulation
def simulate(scheme: str, scn: Scenario, ch: dict, seed: int) -> dict:
    ch = clean(ch, CH_DEFAULTS)
    rng = np.random.default_rng(seed)
    sched = SCHEMES[scheme]
    known = {i: set() for i in range(scn.n)}
    pending: dict = {}
    live: dict = {}
    cl = scn.clearances
    pairs: dict = {}      # (m, r) -> dict
    txs = []
    ci, t = 0, 0.0

    def end(m, r, state):
        q = pairs.get((m, r))
        if q and q["state"] == "open":
            q["state"], q["tEnd"] = state, t

    while ci < len(cl) or pending:
        while ci < len(cl) and cl[ci].t <= t:
            c = cl[ci]; ci += 1
            known[c.ac].add(c.cid)
            old = live.get(c.ac)
            if old is not None and old in pending:
                for r in list(pending[old]):
                    end(old, r, "superseded")
                del pending[old]
            live[c.ac] = c.cid
            if c.dem:
                pending[c.cid] = dict(c.dem)
                for r, d in c.dem.items():
                    pairs[(c.cid, r)] = dict(m=c.cid, r=r, tIssue=c.t, dl=d, tDone=None, tEnd=None, state="open")
        for m in list(pending):
            for r in list(pending[m]):
                if t > pending[m][r] + 120.0:
                    end(m, r, "expired"); del pending[m][r]
            if not pending[m]:
                del pending[m]
        if not pending:
            if ci < len(cl):
                t = max(t, cl[ci].t); continue
            break
        q = len(pending)
        T, got = sched(pending, known, t)
        if T is None:
            # Scheduler chose to WAIT (no transmission): `got` is the time at which it wants to decide again.
            # We wake at that time or at the next clearance, whichever is first.
            nxt = cl[ci].t if ci < len(cl) else got
            t = max(t + 0.05, min(got, nxt))
            continue
        service = (ch["airtime"] + rng.exponential(ch["access"])) / (1 - ch["bg"]) if ch["access"] > 0 else ch["airtime"] / (1 - ch["bg"])
        t0 = t; t += service
        res = []
        for m, r in sorted(got):
            if rng.random() < ch["loss"]:
                res.append([m, r, 0]); continue
            known[r].add(m)
            if m in pending and r in pending[m]:
                pr = pairs[(m, r)]
                if pr["state"] == "open":
                    pr["tDone"], pr["state"] = t, "done"
                del pending[m][r]
                if not pending[m]:
                    del pending[m]
            res.append([m, r, 1])
        if ch["overhear"] > 0:
            # Party-line overhearing: every other aircraft listening (prob. `overhear`) that receives the packet
            # (same loss) and can decode a message in it (rest of packet already known) stores it as side information.
            addressed = {r for _, r in got}
            for s_ in range(scn.n):
                if s_ in addressed or rng.random() >= ch["overhear"] or rng.random() < ch["loss"]:
                    continue
                for x in T:
                    if all((y in known[s_]) for y in T if y != x):
                        known[s_].add(x)
                        if x in pending and s_ in pending[x]:      # it was waiting for this message: now delivered
                            pr = pairs[(x, s_)]
                            if pr["state"] == "open":
                                pr["tDone"], pr["state"] = t, "done"
                            del pending[x][s_]
                            if not pending[x]:
                                del pending[x]
        txs.append(dict(t0=t0, t1=t, T=sorted(T), q=q, res=res))
    return _summ(scheme, list(pairs.values()), txs)


def _summ(scheme, pairs, txs):
    done = [p for p in pairs if p["tDone"] is not None]
    ok = [p for p in done if p["tDone"] <= p["dl"]]
    lat = [p["tDone"] - p["tIssue"] for p in done]
    return dict(scheme=scheme, n_tx=len(txs), n_pairs=len(pairs),
                miss=(1 - len(ok) / len(pairs)) if pairs else 0.0,
                mean_latency=float(np.mean(lat)) if lat else None,
                p95_latency=float(np.percentile(lat, 95)) if lat else None,
                txs=txs, pairs=pairs)


def run_all(scn: Scenario, ch: dict, seed: int) -> dict:
    return {s: simulate(s, scn, ch, seed) for s in ("unicast", "broadcast", "coded")}
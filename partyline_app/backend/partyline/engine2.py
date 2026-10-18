"""Party-line channel simulation with buffered (delayed) decoding, overhearing and per-aircraft loss.

Differences from engine.simulate (which is kept unchanged for the earlier results):
  * Every transmission is a linear combination of the messages in T with random non-zero GF(2^8)
    coefficients (an XOR packet is the special case all-ones; instant decodability is identical).
  * Receivers may STORE a packet they cannot decode yet (buffer=1) and decode later when more packets
    or side information arrive. Decoding uses the generic-rank rule: with random coefficients over a
    large field, the rank of a set of stored equations equals the size of a maximum matching between
    equations and unknown messages (true with probability >= 1 - k/255 per equation; the small
    rank-deficiency probability is ignored and stated as an assumption).
  * Party line: every active aircraft on the frequency hears an uplink. Aircraft that have a pending
    need always listen; others store what they hear with probability `overhear`.
  * Per-aircraft loss: loss_r = loss * (1 - het + 2*het*d_r/d_mean), d_r = distance of the aircraft
    from the ground station (scenario centre) at that time. het = 0 gives the earlier i.i.d. loss.
  * The ground station is assumed to know every receiver's state (perfect, free feedback), the same
    assumption as engine.simulate, for every scheme alike.

Scheduler interface:
  old style  sched(pending, known, now) -> (T, got)              (used for all earlier schemes)
  new style  sched.v2 = True; sched(view) -> dict(T=set, to=None|set) or (None, wake_time)
             view = dict(pending, known, rx, now, ploss, sent, first_tx, buffer, scn)
Feedback modes (ch["fbmode"]): 0 = ideal (default): the station sees every aircraft's true state for free.
  1 = reports: the station keeps its OWN copy of each aircraft's state, updated only when a state report arrives.
  After every uplink each aircraft the station believes still needs something sends a report; each report is lost
  with probability ch["fbloss"]. The station's belief is therefore always a subset of the truth: it may repeat
  clearances an aircraft already holds (waste) but never wrongly believes a clearance was delivered.
  2 = NACK-only reports (cheap feedback): an aircraft that decodes or already holds what it needs stays silent; only an
  aircraft that missed the packet sends a NACK, and a NACK is lost with probability ch["fbloss"]. The station treats
  silence as delivery, so a lost NACK makes it believe a clearance arrived when it did not: belief is NOT always a
  subset of the truth and such pairs are never repaired (they show up as deadline misses).
Collisions (ch["coll"], default 0): each uplink collides with a competing transmission with this probability and is lost
at every receiver, although it still costs its airtime (a first-order stand-in for slotted random access).
Contention (ch["nbg"] > 0, p-persistent CSMA in the style of VDL Mode 2): nbg is the mean number of competing stations with
a frame waiting, pp the persistence probability, slot the slot length in s. The ground station transmits in the first idle
slot it selects (a geometric number of slots with parameter pp, so a mean extra access delay of slot*(1-pp)/pp) and its
uplink collides when at least one competing station selects the same slot: with Poisson competitors this happens with
probability 1 - exp(-nbg*pp), combined with ch["coll"] as 1 - (1 - coll)*exp(-nbg*pp). With nbg = 0 (default) nothing changes.
Packet overhead (ch["hdr"], default 0 = earlier results): a packet combining k clearances needs an id and a coding
coefficient per clearance, so its airtime is airtime * (1 + hdr * (k - 1)); hdr is the extra airtime of one more
clearance as a fraction of one message (e.g. 3 header bytes per 100-byte message = 0.03).
Validation options (defaults reproduce every earlier result exactly):
  exact (0/1)      1 = receivers decode by exact Gaussian elimination over GF(2^8) with the packet's real random non-zero coefficients
                   (partyline.gf256.ExactRx) instead of the generic-rank matching rule; coefficients come from a separate random stream.
  fbair (s)        > 0 = every state report (or NACK) occupies the shared channel for fbair seconds after the uplink it answers, so
                   feedback delays the next uplink inside the simulation instead of being charged afterwards.
  supersede (0/1/2) 1 = a new clearance to an aircraft withdraws its previous one (earlier results); 0 = clearances are never withdrawn;
                   2 = typed: a clearance withdraws only the previous clearance of the same aircraft and the same kind (c.kind if the
                   scenario sets it, otherwise one of three kinds drawn per clearance from a fixed hash).
  track (0/1)      1 = the result also carries dec = {(clearance, aircraft): first time the aircraft decoded it} for EVERY listener (not only
                   pairs with a need) and wd = {clearance: time it was withdrawn by a newer clearance}; used by run_v10.py for metrics on a
                   common demand set and for end-to-end evaluation of causal classes. Scheduling is unchanged.
Each transmission record also counts how the receptions of aircraft with a (believed) need turned out:
rn = decoded something new, rs = stored a useful combination without decoding, rw = wasted (nothing new).
Each transmission record also counts the feedback a feedback-based scheme needs for it: fb = receivers with
a pending need (each reports its state), fb_nack = those of them that lost the packet; *_c = critical only.
"""
from __future__ import annotations
import math
import numpy as np
from .coding import SCHEMES
from .engine import clean, CH_DEFAULTS, LIMITS, DT, _summ, _active
from . import gf256

CH2_DEFAULTS = dict(CH_DEFAULTS, overhear=1.0, buffer=1.0, het=0.0, fbmode=0.0, fbloss=0.0, hdr=0.0, coll=0.0, nbg=0.0, pp=0.05, slot=0.01, fbpolicy=0.0, fbperiod=0.0, exact=0.0, fbair=0.0, supersede=1.0, track=0.0)
LIMITS.setdefault("buffer", (0.0, 1.0))
LIMITS.setdefault("het", (0.0, 1.0))
LIMITS["fbmode"] = (0.0, 2.0)
LIMITS.setdefault("fbloss", (0.0, 0.95))
LIMITS.setdefault("hdr", (0.0, 2.0))
LIMITS.setdefault("coll", (0.0, 0.9))
LIMITS.setdefault("nbg", (0.0, 50.0))
LIMITS.setdefault("pp", (0.001, 1.0))
LIMITS.setdefault("slot", (0.0, 1.0))
LIMITS.setdefault("fbpolicy", (0.0, 2.0))
LIMITS.setdefault("fbperiod", (0.0, 600.0))
LIMITS.setdefault("exact", (0.0, 1.0))
LIMITS.setdefault("fbair", (0.0, 5.0))
LIMITS.setdefault("supersede", (0.0, 2.0))
LIMITS.setdefault("track", (0.0, 1.0))


# ------------------------------------------------------------------ generic-rank decoding
def _matching(eqs):
    """Size of a maximum matching between equations (list of sets) and variables."""
    match = {}

    def aug(i, seen):
        for v in eqs[i]:
            if v in seen:
                continue
            seen.add(v)
            if v not in match or aug(match[v], seen):
                match[v] = i
                return True
        return False
    return sum(1 for i in range(len(eqs)) if aug(i, set()))


class Rx:
    """One receiver: known messages + stored, not yet decoded equations."""
    __slots__ = ("known", "eqs")

    def __init__(self):
        self.known = set()
        self.eqs = []

    def copy(self):
        r = Rx(); r.known = set(self.known); r.eqs = [set(e) for e in self.eqs]
        return r

    def add(self, T, buffer=True):
        """Receive a packet over messages T. Returns the set of newly decoded messages."""
        U = set(T) - self.known
        if not U:
            return set()
        if len(U) == 1:
            x = next(iter(U)); self.known.add(x)
            return {x} | self._closure()
        if not buffer:
            return set()
        if _matching(self.eqs + [U]) > _matching(self.eqs):   # innovative
            self.eqs.append(U)
            return self._closure()
        return set()

    def learn(self, x):
        if x in self.known:
            return set()
        self.known.add(x)
        return {x} | self._closure()

    def _closure(self):
        new = set()
        while True:
            self.eqs = [e - self.known for e in self.eqs]
            self.eqs = [e for e in self.eqs if e]
            if not self.eqs:
                return new
            got = {next(iter(e)) for e in self.eqs if len(e) == 1}
            if not got:
                V = set().union(*self.eqs)
                r0 = _matching(self.eqs)
                if r0 == len(V):
                    got = V
                else:
                    got = {x for x in V if _matching(self.eqs + [{x}]) == r0}
            if not got:
                return new
            self.known |= got
            new |= got

    def deficit(self):
        """(unknown variables in stored equations, extra equations needed to decode all of them)."""
        if not self.eqs:
            return set(), 0
        V = set().union(*self.eqs)
        return V, len(V) - _matching(self.eqs)


# ------------------------------------------------------------------ simulation
def simulate(scheme: str, scn, ch: dict, seed: int) -> dict:
    ch = clean(ch, CH2_DEFAULTS)
    rng = np.random.default_rng(seed)
    sched = SCHEMES[scheme]
    v2 = getattr(sched, "v2", False)
    crit = getattr(scn, "critical", None)          # set of critical (clearance, aircraft) pairs, if tagged
    buffer = ch["buffer"] >= 0.5
    exact = ch["exact"] >= 0.5
    RX = gf256.ExactRx if exact else Rx
    crng = np.random.default_rng(seed + 777)          # coefficient stream, separate so that the channel draws are unchanged
    sup = int(round(ch["supersede"]))
    kinds = ("turn", "vertical", "speed")
    track = ch["track"] >= 0.5
    dec: dict = {}                # (clearance, aircraft) -> first decode time (track = 1)
    wd: dict = {}                 # clearance -> time it was withdrawn by a newer clearance

    def kind_of(c):
        k = getattr(c, "kind", None)
        return k if k is not None else kinds[(c.cid * 2654435761) % 3]
    rx = [RX() for _ in range(scn.n)]
    known = [r.known for r in rx]          # live views (same set objects)
    rep = ch["fbmode"] >= 0.5
    brx = [RX() for _ in range(scn.n)] if rep else rx          # the station's belief about each aircraft
    bknown = [r.known for r in brx]
    pending: dict = {}
    bpending: dict = pending                                     # pairs the station believes are still open
    if rep:
        bpending = {}
    live: dict = {}
    sent: dict = {}
    first_tx: dict = {}
    cl = scn.clearances
    pairs: dict = {}
    txs = []
    dirty = [False] * scn.n          # fbpolicy >= 1: aircraft whose state changed since its last report
    last_rep = [-1e9] * scn.n
    gapstat = {}                  # (coded?, believed gaps j) -> [receptions by aircraft with a believed need, wasted ones]
    ci, t = 0, 0.0
    cx, cy = scn.centre if scn.kind == "synthetic" else (0.0, 0.0)
    D = np.hypot(scn.X - cx, scn.Y - cy)
    dmean = float(np.nanmean(D)) if np.isfinite(D).any() else 1.0

    def ploss(r):
        if ch["het"] <= 0:
            return ch["loss"]
        k = min(int(t // DT), scn.K - 1)
        d = D[r, k]
        if not np.isfinite(d):
            d = dmean
        return float(min(0.9, ch["loss"] * (1 - ch["het"] + 2 * ch["het"] * d / dmean)))

    def end(m, r, state):
        q = pairs.get((m, r))
        if q and q["state"] == "open":
            q["state"], q["tEnd"] = state, t

    def deliver(r, newly):
        for m in newly:
            if m in pending and r in pending[m]:
                pr = pairs[(m, r)]
                if pr["state"] == "open":
                    pr["tDone"], pr["state"] = t, "done"
                del pending[m][r]
                if not pending[m]:
                    del pending[m]

    while ci < len(cl) or bpending:
        while ci < len(cl) and cl[ci].t <= t:
            c = cl[ci]; ci += 1
            got0 = rx[c.ac].learn(c.cid)
            if track:
                for m in got0:
                    dec.setdefault((m, c.ac), t)
            deliver(c.ac, got0)
            if rep:
                brx[c.ac].learn(c.cid)
            key = c.ac if sup == 1 else (c.ac, kind_of(c))
            old = live.get(key) if sup >= 1 else None
            if old is not None:
                wd.setdefault(old, c.t)
            if rep and old is not None:
                bpending.pop(old, None)
            if old is not None and old in pending:
                for r in list(pending[old]):
                    end(old, r, "superseded")
                del pending[old]
            live[key] = c.cid
            if c.dem:
                dem = {r: d for r, d in c.dem.items() if c.cid not in known[r]}
                pending[c.cid] = dem
                for r, d in c.dem.items():
                    pairs[(c.cid, r)] = dict(m=c.cid, r=r, tIssue=c.t, dl=d, tDone=None, tEnd=None, state="open")
                for r in c.dem:
                    if c.cid in known[r]:
                        deliver(r, {c.cid})
                if not pending[c.cid]:
                    del pending[c.cid]
                if rep:
                    bd = {r: d for r, d in c.dem.items() if c.cid not in bknown[r]}
                    if bd:
                        bpending[c.cid] = bd
        if rep:
            for m in list(bpending):
                for r in list(bpending[m]):
                    if t > bpending[m][r] + 120.0:
                        del bpending[m][r]
                if not bpending[m]:
                    del bpending[m]
        for m in list(pending):
            for r in list(pending[m]):
                if t > pending[m][r] + 120.0:
                    end(m, r, "expired"); del pending[m][r]
            if not pending[m]:
                del pending[m]
        if not bpending:
            if ci < len(cl):
                t = max(t, cl[ci].t); continue
            break
        q = len(bpending)
        if v2:
            view = dict(pending=bpending, known=bknown, rx=brx, now=t, sent=sent, first_tx=first_tx,
                        ploss=lambda r: ploss(r), buffer=buffer, scn=scn)
            gf256.SCORING[0] = True
            try:
                out = sched(view)
            finally:
                gf256.SCORING[0] = False
            if isinstance(out, tuple):
                T, to = out[0], None
                if T is None:
                    nxt = cl[ci].t if ci < len(cl) else out[1]
                    t = max(t + 0.05, min(out[1], nxt)); continue
            else:
                T, to = out["T"], out.get("to")
        else:
            gf256.SCORING[0] = True
            try:
                T, got = sched(bpending, bknown, t)
            finally:
                gf256.SCORING[0] = False
            if T is None:
                nxt = cl[ci].t if ci < len(cl) else got
                t = max(t + 0.05, min(got, nxt)); continue
            to = {r for _, r in got} if scheme == "unicast" else None
        T = set(T)
        if exact:
            gf256.CUR = {m: int(crng.integers(1, 256)) for m in T}
        air = ch["airtime"] * (1.0 + ch["hdr"] * (len(T) - 1))        # coded packet: id + coefficient per extra clearance
        service = (air + rng.exponential(ch["access"])) / (1 - ch["bg"]) if ch["access"] > 0 else air / (1 - ch["bg"])
        if ch["nbg"] > 0:                                   # p-persistent CSMA: geometric number of busy slots before sending
            service += (rng.geometric(ch["pp"]) - 1) * ch["slot"]
        t0 = t; t += service
        pcoll = 1.0 - (1.0 - ch["coll"]) * math.exp(-ch["nbg"] * ch["pp"]) if ch["nbg"] > 0 else ch["coll"]
        collided = pcoll > 0 and rng.random() < pcoll
        for m in T:
            sent[m] = sent.get(m, 0) + 1
            first_tx.setdefault(m, t0)
        needy = {r for rs in bpending.values() for r in rs}
        cneedy = {r for m, rs in bpending.items() for r in rs if crit is not None and (m, r) in crit}
        res = []
        lost, lostc = 0, 0
        nsent = 0             # state reports actually sent for this uplink (all needy aircraft with fbpolicy 0)
        rn = rs = rw = 0      # receptions by aircraft with a (believed) need: decoded something / stored only / wasted
        k = min(int(t0 // DT), scn.K - 1)
        listeners = to if to is not None else range(scn.n)
        for r in listeners:
            if to is None and r not in needy:
                if not _active(scn, r, k) or rng.random() >= ch["overhear"]:
                    continue
            ok = (rng.random() >= ploss(r)) and not collided
            if ok:
                if r in needy:
                    jb = sum(1 for m in T if r in bpending.get(m, ()))          # clearances of T the station believes r still lacks
                    u0, ne = bool(set(T) - rx[r].known), len(rx[r].eqs)
                    newly = rx[r].add(T, buffer)
                    wasted = False
                    if newly:
                        rn += 1; dirty[r] = True
                    elif u0 and len(rx[r].eqs) > ne:
                        rs += 1; dirty[r] = True
                    else:
                        rw += 1; wasted = True; dirty[r] = True      # a redundant packet also triggers a report (the aircraft can see the station is stale)
                    gk = ("c" if len(T) > 1 else "u") + str(min(jb, 5))
                    g = gapstat.setdefault(gk, [0, 0]); g[0] += 1; g[1] += int(wasted)
                else:
                    newly = rx[r].add(T, buffer)
                if track:
                    for m in newly:
                        dec.setdefault((m, r), t)
                deliver(r, newly)
            if r in needy:
                res.append([sorted(T), r, int(ok)])
                lost += (not ok)
                lostc += (not ok) and (r in cneedy)
        if rep and ch["fbmode"] >= 1.5:           # NACK-only: silence = delivered; a lost NACK leaves the station wrongly optimistic
            ok_of = {rr[1]: rr[2] for rr in res}
            for r in needy:
                if to is not None and r not in to:
                    continue
                if ok_of.get(r, 1):
                    brx[r].add(T, buffer); bknown[r] = brx[r].known          # silent: station assumes the packet arrived
                elif ch["fbloss"] > 0 and rng.random() < ch["fbloss"]:
                    brx[r].add(T, buffer); bknown[r] = brx[r].known          # NACK lost: station wrongly assumes it arrived
                else:
                    brx[r] = rx[r].copy(); bknown[r] = brx[r].known          # NACK heard: station learns the true state
            for m in list(bpending):
                for r in list(bpending[m]):
                    if m in bknown[r]:
                        del bpending[m][r]
                if not bpending[m]:
                    del bpending[m]
        elif rep:                                 # state reports (each may be lost); belief only ever grows
            pol, per = int(ch["fbpolicy"]), ch["fbperiod"]
            for r in needy:
                if to is not None and r not in to:
                    continue
                if pol >= 1 and not (dirty[r] and (pol == 1 or t - last_rep[r] >= per)):
                    continue                    # change-triggered (1) / change-triggered and at most one report per `fbperiod` s (2, piggybacked)
                nsent += 1; dirty[r] = False; last_rep[r] = t
                if ch["fbloss"] <= 0 or rng.random() >= ch["fbloss"]:
                    brx[r] = rx[r].copy(); bknown[r] = brx[r].known
            for m in list(bpending):
                for r in list(bpending[m]):
                    if m in bknown[r]:
                        del bpending[m][r]
                if not bpending[m]:
                    del bpending[m]
        if ch["fbair"] > 0:                       # reports occupy the shared channel before the next uplink
            nrep = (nsent if ch["fbmode"] < 1.5 else lost) if rep else (1 if to is not None else len(needy))
            t += nrep * ch["fbair"]
        # feedback a scheme would need for this packet: every receiver with a pending need reports its state
        # (fb), or only those that lost it report (fb_nack); *_c = the same counted over critical receivers only
        txs.append(dict(t0=t0, t1=t, T=sorted(T), q=q, res=res, fb=len(needy), fb_c=len(cneedy),
                        fb_nack=lost, fb_nack_c=lostc, fbs=(nsent if rep and ch["fbmode"] < 1.5 else len(needy)), rn=rn, rs=rs, rw=rw))
    out = _summ(scheme, list(pairs.values()), txs)
    out["gapstat"] = gapstat
    if track:
        out["dec"], out["wd"] = dec, wd
    return out
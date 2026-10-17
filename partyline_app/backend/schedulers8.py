"""STGC-SH: STGC2 with a SUPERSESSION-AWARE hold.
A held repair of clearance m (addressed to aircraft a) is lost work when a newer clearance to a arrives before the repair is
sent: the pair is withdrawn and counts as a strict miss. Conflict-driven traffic arrives in bursts, so an aircraft that was
just given several clearances is likely to receive another. STGC-SH therefore holds each repair for a time that depends on how
likely its addressee is to be updated, estimated by the ground station from clearances it has itself issued (no extra information):
    lam_a   = (n_a(now) + lam0*T0) / (T0 + now/60)        clearances per minute to aircraft a  (T0 = 4 min prior)
    burst_a = exp(-(now - t_last_a)/tau)                   1 right after a clearance to a, decaying with time constant tau
    hold_m  = clip( hold * lam0 / (lam_a + beta*burst_a*lam0) , hold_min , hold )
so quiet aircraft keep the long hold (many uplinks saved) while aircraft that are being updated get their repairs earlier
(fewer withdrawn pairs). With beta = 0 and a common rate this reduces to the idea of STGC-AD, but per aircraft.
Use with engine2; schedulers8.register(hold=..., crit_w=...)."""
import math
from partyline import coding
import schedulers5 as S5


def make_sh(hold=30.0, crit_w=3.0, lam0=0.25, hold_min=6.0, tau=60.0, beta=2.0, T0=4.0):
    st = {"key": None, "by_ac": {}, "ac": {}}

    def index(scn):
        if st["key"] is not scn:
            by = {}
            for c in scn.clearances:
                by.setdefault(c.ac, []).append(c.t)
            st["key"], st["by_ac"] = scn, by
            st["ac"] = {c.cid: c.ac for c in scn.clearances}
        return st

    def hold_fn(view, m):
        scn, now = view["scn"], view["now"]
        S = index(scn)
        a = S["ac"].get(m)
        if a is None:
            return hold
        ts = [t for t in S["by_ac"].get(a, ()) if t <= now]          # only clearances already issued
        lam = (len(ts) + lam0 * T0) / (T0 + now / 60.0)
        burst = math.exp(-(now - ts[-1]) / tau) if ts else 0.0
        h = hold * lam0 / (lam + beta * burst * lam0)
        return max(hold_min, min(hold, h))
    return S5.make_stgc(hold=hold, crit_w=crit_w, idnc_seed=True, hold_fn=hold_fn)


def register(hold=30.0, crit_w=3.0):
    coding.SCHEMES["stgc_sh"] = make_sh(hold=hold, crit_w=crit_w)

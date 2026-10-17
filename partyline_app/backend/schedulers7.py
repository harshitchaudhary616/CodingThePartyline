"""STGC-AD: STGC2 whose repair hold time adapts to the clearance rate, so that one coder suits both quiet and busy skies.
A held repair can be withdrawn (superseded) before it is sent, and the chance of that grows with the clearance rate, so the
hold shrinks when traffic is busy and stays long when it is quiet (long holds save uplinks). The rate is estimated by the
ground station from the clearances it has issued (a one-minute prior at the default rate, then the running count).
  hold_eff = clip(hold * lam0 / lam_hat, hold_min, hold)
Use with engine2; register with schedulers7.register(hold=..., crit_w=...)."""
from partyline import coding
import schedulers5 as S5

LEVELS = (8.0, 12.0, 18.0, 30.0)


def make_adaptive(hold=30.0, crit_w=3.0, lam0=0.25, hold_min=8.0):
    top = max(hold, hold_min)
    levels = sorted(set([min(l, top) for l in LEVELS] + [top]))
    inst = {h: S5.make_stgc(hold=h, crit_w=crit_w, idnc_seed=True) for h in levels}
    st = {"seen": set(), "last": -1.0}

    def sched(view):
        now, scn = view["now"], view["scn"]
        if now < st["last"]:
            st["seen"] = set()                       # a new simulation started
        st["last"] = now
        st["seen"].update(view["pending"].keys())
        n = max(1, getattr(scn, "n", 10))
        lam = (len(st["seen"]) + n * lam0) / (n * (now + 60.0) / 60.0)      # clearances per aircraft per minute
        h = max(hold_min, min(top, hold * lam0 / max(lam, 1e-6)))
        h = min(levels, key=lambda x: abs(x - h))
        return inst[h](view)
    sched.v2 = True
    return sched


def register(hold=30.0, crit_w=3.0):
    coding.SCHEMES["stgc_ad"] = make_adaptive(hold=hold, crit_w=crit_w)
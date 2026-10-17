"""Critical-class guards for STGC2 on poor channels and in large sectors (the one place class-aware IDNC beats STGC2).
  stgc_g1   STGC2 with a wider urgent window (urgent_slack 30 s instead of 15 s) and repairs due when any pair has < 40 s left (instead of 20 s):
            critical repairs are sent earlier, at the price of holding fewer repairs.
  stgc_g2   the same with 45 s / 60 s.
  stgc_fb   fallback: STGC2 normally, class-aware IDNC (idnc_cls) while the station sees a poor channel (mean link loss of the aircraft with a
            believed need >= LOSS_THR) or a crowded frequency (>= N_THR aircraft with a believed need). Uses only quantities the station has:
            the link loss it estimates and its own list of pending needs.
Use with engine2; register with schedulers9.register(hold=..., crit_w=...) AFTER schedulers5.register."""
import numpy as np
from partyline import coding
import schedulers5 as S5

LOSS_THR = 0.35
N_THR = 30


def make_fb(stgc, idnc, loss_thr=LOSS_THR, n_thr=N_THR):
    def sched(view):
        needy = {r for rs in view["pending"].values() for r in rs}
        poor = bool(needy) and float(np.mean([view["ploss"](r) for r in needy])) >= loss_thr
        crowded = len(needy) >= n_thr
        return (idnc if (poor or crowded) else stgc)(view)
    sched.v2 = True
    return sched


def register(hold=30.0, crit_w=3.0):
    coding.SCHEMES["stgc_g1"] = S5.make_stgc(hold=hold, crit_w=crit_w, idnc_seed=True, urgent_slack=30.0, safe_slack=40.0)
    coding.SCHEMES["stgc_g2"] = S5.make_stgc(hold=hold, crit_w=crit_w, idnc_seed=True, urgent_slack=45.0, safe_slack=60.0)
    coding.SCHEMES["stgc_fb"] = make_fb(coding.SCHEMES["stgc2"], coding.SCHEMES["idnc_cls"])

"""Critical-priority STGC2 (stgc_cp): the hold/fallback decision revised after the withdrawal and in-band feedback checks.

  stgc_cp   while the station believes ANY critical pair is still open with a feasible deadline, the next uplink is chosen exactly as
            class-aware IDNC (idnc_cls) would choose it; only when no critical pair is open does STGC2 decide (new clearances at once,
            awareness repairs held and sent as random-linear combinations). Critical repairs are therefore never held, so the critical
            class is served as by class-aware IDNC, while awareness repairs keep the coding gain.
            Uses only what the station has: its own list of believed-open pairs and their deadlines and classes.
Register AFTER schedulers5.register (needs stgc2 and idnc_cls):  schedulers10.register()"""
from partyline import coding
import schedulers3 as S3


def make_cp(stgc, idnc):
    def sched(view):
        crit = getattr(view["scn"], "critical", None)
        now = view["now"]
        if crit is not None:
            for m, rs in view["pending"].items():
                for r, dl in rs.items():
                    if (m, r) in crit and dl - now >= S3.FEAS_MIN:
                        return idnc(view)
        return stgc(view)
    sched.v2 = True
    return sched


def register(**_):
    coding.SCHEMES["stgc_cp"] = make_cp(coding.SCHEMES["stgc2"], coding.SCHEMES["idnc_cls"])
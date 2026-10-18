"""Tests for the v10 metrics: tracking does not change scheduling, the common demand set is the same for every scheme,
critical-priority STGC2 hands over to class-aware IDNC while a critical pair is open, and causal runs are scored end to end."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import schedulers5, schedulers9, schedulers10
import experiments_party as EP
import awareness
from partyline import engine2, coding
from partyline import engine as E
from partyline.engine import make_synthetic
from awareness import with_awareness


def _setup():
    schedulers5.register(hold=30.0, crit_w=10.0); schedulers9.register(hold=30.0, crit_w=10.0); schedulers10.register()


def _scn(seed=3):
    return with_awareness(make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), seed))


def _ch(**kw):
    return dict(engine2.CH2_DEFAULTS, loss=0.3, fbmode=1.0, fbloss=0.6, **kw)


def test_tracking_does_not_change_scheduling():
    _setup()
    scn = _scn()
    a = engine2.simulate("stgc2", scn, _ch(), 5)
    b = engine2.simulate("stgc2", scn, _ch(track=1.0), 5)
    assert a["n_tx"] == b["n_tx"]
    assert [p["state"] for p in a["pairs"]] == [p["state"] for p in b["pairs"]]
    assert "dec" in b and "dec" not in a
    for p in b["pairs"]:                                    # a delivered pair was decoded no later than it was marked done
        if p["tDone"] is not None and p["tDone"] > p["tIssue"]:
            assert b["dec"][(p["m"], p["r"])] <= p["tDone"] + 1e-9


def test_common_set_is_the_same_for_every_scheme():
    _setup()
    import v10metrics as V
    scn = _scn(4)
    n = set()
    for s in ("idnc_cls", "stgc2", "stgc_cp"):
        ch = _ch(track=1.0)
        L = engine2.simulate(s, scn, ch, 7)
        V._cm = V._cm or EP.class_metrics
        out = V.class_metrics(L, scn, ch, s, 0.05)
        n.add((out["crit_n_cs"], out["aware_n_cs"], out["crit_n_cs_all"], out["crit_n_zero"]))
        assert out["crit_n_cs_all"] == out["crit_n_zero"] + out["crit_n_short"] + out["crit_n_cs"]
        assert out["busy_s"] > 0
    assert len(n) == 1


def test_critical_priority_uses_idnc_while_critical_open():
    _setup()
    cp, idnc = coding.SCHEMES["stgc_cp"], coding.SCHEMES["idnc_cls"]
    scn = _scn(5)
    seen = []

    def spy(view):
        crit_open = any((m, r) in scn.critical and dl - view["now"] >= 1.0 for m, rs in view["pending"].items() for r, dl in rs.items())
        out = cp(view)
        if crit_open:
            seen.append(set(out["T"]) == set(idnc(view)["T"]))
        return out
    spy.v2 = True
    coding.SCHEMES["_spy"] = spy
    try:
        engine2.simulate("_spy", scn, _ch(), 3)
    finally:
        del coding.SCHEMES["_spy"]
    assert seen and all(seen)


def test_causal_end_to_end_scoring():
    _setup()
    import v10metrics as V
    import causal_traffic as CT
    saved = (EP.from_tracks, EP.with_awareness, E.build_clearances, V._cm)
    try:
        V._install_causal()
        V._cm = saved[3] or EP.class_metrics
        s = make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), 3)
        rows = [(k * 5.0, f"a{i}", 45 + s.Y[i, k] / 60, 10 + s.X[i, k] / (60 * np.cos(np.radians(45))), s.Z[i, k] / 3.28084, False)
                for i in range(s.n) for k in range(s.K) if not np.isnan(s.X[i, k])]
        scn = EP.from_tracks(rows, dict(upd_rate=0.25), 7)
        scn = EP.with_awareness(scn, A=60.0, sector=60.0, r_aware=40.0)
        assert scn.oracle is not None and 0.5 < scn.overlap["recall"] <= 1.0
        ch = _ch(track=1.0)
        L = engine2.simulate("idnc_cls", scn, ch, 2)
        out = V.class_metrics(L, scn, ch, "idnc_cls", 0.05)
        assert out["crit_e2e_n"] > 0 and 0.0 <= out["crit_e2e_miss"] <= 1.0
        assert 0.0 < out["crit_e2e_pred"] <= 1.0
        assert out["aware_e2e_n"] > 0
    finally:
        EP.from_tracks, EP.with_awareness, E.build_clearances, V._cm = saved
"""Tests for the critical-class guards, the fallback and the K-nearest awareness filter."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schedulers5, schedulers9
from partyline import engine2, coding
from partyline.engine import make_synthetic
from awareness import with_awareness
from awareness_k import with_awareness_k


def _base(seed=3):
    return make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), seed)


def _run(scheme):
    schedulers5.register(hold=30.0, crit_w=10.0); schedulers9.register(hold=30.0, crit_w=10.0)
    ch = dict(engine2.CH2_DEFAULTS, loss=0.3, fbmode=1.0, fbloss=0.6)
    return engine2.simulate(scheme, with_awareness(_base()), ch, 5)


def test_guards_and_fallback_are_registered_and_run():
    for s in ("stgc_g1", "stgc_g2", "stgc_fb"):
        L = _run(s)
        assert L["n_tx"] > 0, s
    assert "stgc_fb" in coding.SCHEMES


def test_fallback_equals_idnc_cls_when_always_poor():
    schedulers5.register(hold=30.0, crit_w=10.0)
    fb = schedulers9.make_fb(coding.SCHEMES["stgc2"], coding.SCHEMES["idnc_cls"], loss_thr=0.0, n_thr=0)
    coding.SCHEMES["fb_always"] = fb
    a, b = _run("fb_always"), _run("idnc_cls")
    assert a["n_tx"] == b["n_tx"]


def test_k_filter_keeps_critical_set_and_shrinks_awareness():
    full = with_awareness(_base())
    k3 = with_awareness_k(_base(), K=3)
    assert k3.critical == full.critical
    assert len(k3.aware) <= len(full.aware)
    per = {}
    for c, r in k3.aware:
        per[c] = per.get(c, 0) + 1
    assert all(v <= 3 for v in per.values())


def test_k_zero_reproduces_unfiltered_awareness():
    assert with_awareness_k(_base(), K=0).aware == with_awareness(_base()).aware

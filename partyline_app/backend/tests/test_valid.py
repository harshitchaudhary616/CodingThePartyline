"""Tests for the reviewer checks: exact GF(2^8) decoding, in-band feedback, withdrawal rules, causal classes."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import schedulers5, schedulers9
from partyline import engine2, gf256
from partyline.engine import make_synthetic
from awareness import with_awareness
import causal_traffic as CT


def _scn(seed=3):
    return with_awareness(make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), seed))


def _run(scheme, **kw):
    schedulers5.register(hold=30.0, crit_w=10.0); schedulers9.register(hold=30.0, crit_w=10.0)
    ch = dict(engine2.CH2_DEFAULTS, loss=0.3, fbmode=1.0, fbloss=0.6, **kw)
    return engine2.simulate(scheme, _scn(), ch, 5)


def test_gf256_inverse_and_rank():
    assert all(gf256.mul(a, gf256.inv(a)) == 1 for a in range(1, 256))
    R = gf256.ExactRx()
    gf256.CUR = {0: 1, 1: 1}; R.add({0, 1})
    gf256.CUR = {0: 1, 1: 1}; assert R.add({0, 1}) == set()          # same row twice: not innovative
    gf256.CUR = {0: 1, 1: 2}; assert R.add({0, 1}) == {0, 1}         # independent row: both decoded


def test_exact_decoding_runs_and_rarely_disagrees():
    gf256.STATS[:] = [0, 0, 0]
    a, b = _run("stgc2"), _run("stgc2", exact=1.0)
    assert b["n_tx"] > 0
    assert gf256.STATS[1] + gf256.STATS[2] <= max(1, 0.05 * gf256.STATS[0])
    assert abs(a["n_tx"] - b["n_tx"]) <= 0.1 * a["n_tx"]


def test_inband_feedback_takes_channel_time():
    a, b = _run("idnc_cls"), _run("idnc_cls", fbair=0.05)
    assert b["txs"][-1]["t1"] > a["txs"][-1]["t1"]


def test_never_withdrawn_has_no_superseded_pairs():
    L = _run("stgc2", supersede=0.0)
    assert not any(p["state"] == "superseded" for p in L["pairs"])
    L1 = _run("stgc2")
    L2 = _run("stgc2", supersede=2.0)
    n = lambda L: sum(p["state"] == "superseded" for p in L["pairs"])
    assert n(L2) <= n(L1)


def test_causal_classes_overlap_oracle():
    s = make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), 3)
    rows = [(k * 5.0, f"a{i}", 45 + s.Y[i, k] / 60, 10 + s.X[i, k] / (60 * np.cos(np.radians(45))), s.Z[i, k] / 3.28084, False)
            for i in range(s.n) for k in range(s.K) if not np.isnan(s.X[i, k])]
    ov = CT.overlap(rows, dict(upd_rate=0.25), 7)
    assert 0.5 < ov["recall"] <= 1.0 and 0.5 < ov["precision"] <= 1.0

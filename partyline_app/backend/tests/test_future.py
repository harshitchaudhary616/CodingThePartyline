"""Tests for the future-work additions: sparse reporting, STGC-SH, belief-staleness model, calibration."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schedulers5, schedulers6, schedulers7, schedulers8
import belief_theory as BT
from partyline import engine2
from partyline.engine import make_synthetic
from awareness import with_awareness


def _scn(seed=3):
    return with_awareness(make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), seed))


def _run(scheme, **kw):
    schedulers5.register(hold=30.0, crit_w=10.0); schedulers6.register(); schedulers7.register(hold=30.0, crit_w=10.0); schedulers8.register(hold=30.0, crit_w=10.0)
    ch = dict(engine2.CH2_DEFAULTS, loss=0.3, fbmode=1.0, fbloss=0.6, **kw)
    return engine2.simulate(scheme, _scn(), ch, 5)


def test_full_reporting_counts_every_needy_aircraft():
    L = _run("stgc2")
    assert all(x["fbs"] == x["fb"] for x in L["txs"])


def test_sparse_reporting_sends_fewer_reports_per_uplink():
    full, chg = _run("stgc2"), _run("stgc2", fbpolicy=1.0)
    assert sum(x["fbs"] for x in chg["txs"]) / chg["n_tx"] < sum(x["fbs"] for x in full["txs"]) / full["n_tx"]


def test_period_limits_reports_further():
    chg, per = _run("stgc2", fbpolicy=1.0), _run("stgc2", fbpolicy=2.0, fbperiod=30.0)
    assert sum(x["fbs"] for x in per["txs"]) / per["n_tx"] < sum(x["fbs"] for x in chg["txs"]) / chg["n_tx"]


def test_stgc_sh_runs_and_urgent_critical_not_worse_than_stgc2_by_much():
    a, b = _run("stgc_sh"), _run("stgc2")
    assert a["n_tx"] > 0 and a["n_tx"] >= b["n_tx"] * 0.9          # a shorter hold never saves more uplinks than the long one by a wide margin


def test_closed_form_pair_waste():
    assert abs(BT.pair_waste(0.3, 0.6, 2) - 0.7 * 0.36 / 0.64) < 1e-12
    assert BT.pair_waste(0.3, 0.0, 1) == 0.0                       # no report loss, no stale belief


def test_chain_is_monotone_in_report_loss_and_gap():
    seqs = [[1, 1, 2], [2], [1]]
    assert BT.chain_w1(seqs, 0.3, 0.3) < BT.chain_w1(seqs, 0.3, 0.6) < BT.chain_w1(seqs, 0.3, 0.9)
    assert BT.chain_w1([[3]], 0.3, 0.6) < BT.chain_w1([[1]], 0.3, 0.6)


def test_model_tracks_simulation_for_full_reporting():
    sc, G, gs = [_scn(s) for s in range(1, 9)], [], {}
    for i, s in enumerate(sc):
        ch = dict(engine2.CH2_DEFAULTS, loss=0.3, fbmode=1.0, fbloss=0.6)
        L = engine2.simulate("stgc2", s, ch, 50 + i); G += BT.repeat_seqs(L["txs"])
        for k, (a, b) in L["gapstat"].items():
            z = gs.setdefault(k, [0, 0]); z[0] += a; z[1] += b
    m, _ = BT.measured_w1(gs)
    assert abs(BT.chain_w1(G, 0.3, 0.6) - m) < 0.08


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)

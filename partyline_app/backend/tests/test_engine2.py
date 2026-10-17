"""Tests for the party-line engine (engine2) and the tiered / DTC schedulers."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import schedulers2, schedulers3, schedulers4  # noqa: F401
from partyline import engine, engine2
from partyline.engine import Scenario, Clearance, make_synthetic
from partyline.engine2 import Rx, _matching


def test_matching_and_generic_decoding():
    assert _matching([{1, 2}, {2, 3}]) == 2
    r = Rx()
    assert r.add({1, 2}) == set() and len(r.eqs) == 1          # stored, not decodable
    assert r.add({2, 3}) == set()
    assert r.add({1}) == {1, 2, 3}                              # third equation resolves all
    r = Rx(); r.known = {5}
    assert r.add({5, 6}) == {6}                                 # instant decoding (IDNC rule)
    r = Rx()
    r.add({1, 2, 3}); r.add({1, 2, 3})
    assert r.deficit() == ({1, 2, 3}, 1)
    assert r.add({1, 2, 3}) == {1, 2, 3}                        # 3 independent combos of 3 messages


def test_non_innovative_packet_is_not_stored():
    r = Rx(); r.known = {1}
    r.add({2, 3}); r.add({2, 3}); assert r.known >= {2, 3}      # two generic combos of {2,3} decode both
    r = Rx(); r.add({1, 2}); r.add({1, 2}); n = len(r.eqs)
    assert r.add({1, 2}) == set() and len(r.eqs) == n           # nothing new


def test_no_buffer_discards_undecodable():
    r = Rx()
    assert r.add({1, 2}, buffer=False) == set() and r.eqs == []


def _xor_swap_scenario():
    cl = [Clearance(0, 0, 0, 0.0, {1: 100.0}), Clearance(1, 1, 0, 0.0, {0: 100.0})]
    z = np.zeros((2, 40))
    scn = Scenario(['A', 'B'], z, z, z, [0, 0], [39, 39], 'synthetic', (0, 0, 1, 1), (0, 0), {})
    scn.clearances = cl
    return scn


def test_engine2_matches_engine_on_lossless_swap():
    scn = _xor_swap_scenario()
    ch = dict(engine2.CH2_DEFAULTS, loss=0.0)
    for s in ('coded', 'coded_best', 'idnc_best', 'tiered', 'dtc'):
        L = engine2.simulate(s, scn, ch, 1)
        assert L['n_tx'] == 1 and L['miss'] == 0.0, s
    assert engine2.simulate('broadcast_best', scn, ch, 1)['n_tx'] == 2
    assert engine.simulate('coded', scn, {'loss': 0.0}, 1)['n_tx'] == 1


def test_every_pair_ends_in_a_final_state():
    scn = make_synthetic(dict(rate=2.0, dur_min=5), 7)
    ch = dict(engine2.CH2_DEFAULTS, loss=0.3, het=0.5)
    for s in ('broadcast_best', 'idnc_best', 'tiered', 'idnc_tiered', 'dtc'):
        L = engine2.simulate(s, scn, ch, 11)
        states = {p['state'] for p in L['pairs']}
        assert states <= {'done', 'superseded', 'expired'}, (s, states)
        for p in L['pairs']:
            if p['state'] == 'done':
                assert p['tDone'] >= p['tIssue']


def test_tiered_never_delays_urgent_pairs_more_than_immediate():
    """Pairs with < 15 s slack must be served as by the immediate scheduler: misses among still-valid
    clearances should not be worse than immediate coded_best by more than noise."""
    ch = dict(engine2.CH2_DEFAULTS, loss=0.2)
    import experiments_algo as A
    d = []
    for s in range(1, 5):
        scn = make_synthetic(dict(rate=3.0, dur_min=6), s)
        a = A.metrics(engine2.simulate('tiered', scn, ch, 100 + s), ch)['miss_excl']
        b = A.metrics(engine2.simulate('coded_best', scn, ch, 100 + s), ch)['miss_excl']
        d.append(a - b)
    assert np.mean(d) < 0.01


def test_same_seed_is_reproducible():
    scn = make_synthetic(dict(rate=2.0, dur_min=5), 3)
    ch = dict(engine2.CH2_DEFAULTS, loss=0.2)
    a = engine2.simulate('tiered', scn, ch, 5); b = engine2.simulate('tiered', scn, ch, 5)
    assert a['n_tx'] == b['n_tx'] and a['miss'] == b['miss']


# ---------------------------------------------------------------- party-line awareness (two relevance classes)
def test_awareness_keeps_critical_and_adds_same_sector_only():
    from awareness import with_awareness
    from partyline.engine import _active, DT
    import math
    scn = make_synthetic(dict(rate=3.0, dur_min=6), 4)
    s2 = with_awareness(scn, A=60.0, sector=60.0)
    assert s2 is not scn and len(s2.clearances) == len(scn.clearances)
    assert not (s2.aware & s2.critical)
    x0, y0 = scn.bounds[0], scn.bounds[1]
    for c, c2 in zip(scn.clearances, s2.clearances):
        for r, d in c.dem.items():
            assert c2.dem[r] == d                                  # critical deadline unchanged
        for r in c2.dem:
            if (c.cid, r) in s2.aware:
                assert c2.dem[r] == c.t + 60.0
                k = int(c.t // DT)
                k = k if _active(scn, c.ac, k) else k + 1
                sec = lambda i: (math.floor((scn.X[i, k] - x0) / 60.0), math.floor((scn.Y[i, k] - y0) / 60.0))
                assert sec(r) == sec(c.ac)
    assert s2.aware, "awareness pairs expected in a busy synthetic scenario"


def test_party_schemes_finish_and_tiered_saves_uplinks():
    from awareness import with_awareness
    import schedulers5  # noqa: F401
    ch = dict(engine2.CH2_DEFAULTS, loss=0.3)
    d = []
    for s in (1, 2, 3):
        scn = with_awareness(make_synthetic(dict(rate=3.0, dur_min=6), s))
        n = {}
        for name in ('broadcast_best', 'tiered', 'stgc'):
            L = engine2.simulate(name, scn, ch, 50 + s)
            assert {p['state'] for p in L['pairs']} <= {'done', 'superseded', 'expired'}
            n[name] = L['n_tx']
        d.append(n['tiered'] < n['broadcast_best'])
    assert all(d)


def test_stgc_lossless_swap_is_one_uplink():
    import schedulers5  # noqa: F401
    scn = _xor_swap_scenario()
    scn.critical = {(0, 1), (1, 0)}; scn.aware = set()
    L = engine2.simulate('stgc', scn, dict(engine2.CH2_DEFAULTS, loss=0.0), 1)
    assert L['n_tx'] == 1 and L['miss'] == 0.0


def test_feedback_counts_recorded():
    scn = make_synthetic(dict(rate=2.0, dur_min=5), 3)
    L = engine2.simulate('broadcast_best', scn, dict(engine2.CH2_DEFAULTS, loss=0.2), 5)
    assert all('fb' in x and 'fb_nack' in x and x['fb_nack'] <= x['fb'] for x in L['txs'])
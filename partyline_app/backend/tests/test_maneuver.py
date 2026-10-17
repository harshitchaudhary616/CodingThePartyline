"""Manoeuvre detection finds a known turn, climb and speed change within 15 s and raises no false event on a noisy straight, level track."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import maneuver_traffic as M
from partyline import engine as E


def _track():
    dt, K = E.DT, 240
    t = np.arange(K) * dt
    hdg = np.where(t < 300, 90.0, np.where(t < 330, 90 - 40 * (t - 300) / 30, 50.0))
    spd = np.where(t < 800, 250.0, np.where(t < 830, 250 + 40 * (t - 800) / 30, 290.0))
    X = np.cumsum(spd * np.sin(np.radians(hdg)) * dt / 3600); Y = np.cumsum(spd * np.cos(np.radians(hdg)) * dt / 3600)
    Z = 10000 + np.cumsum(np.where((t >= 600) & (t < 720), 1500.0, 0.0) * dt / 60)
    return X, Y, Z


def test_known_manoeuvres_are_found():
    X, Y, Z = _track()
    got = {k: t for t, k in M.detect_one(X, Y, Z)}
    for kind, truth in (("turn", 300), ("vertical", 600), ("speed", 800)):
        assert kind in got and abs(got[kind] - truth) <= 15, (kind, got)


def test_no_false_events_on_noisy_straight_level_flight():
    rng = np.random.default_rng(0)
    K = 240
    X = np.cumsum(np.full(K, 250 * E.DT / 3600)) + rng.normal(0, 0.02, K)
    Y = rng.normal(0, 0.02, K)
    Z = 10000 + np.round(rng.normal(0, 40, K) / 25) * 25
    assert M.detect_one(X, Y, Z) == []


if __name__ == "__main__":
    test_known_manoeuvres_are_found(); test_no_false_events_on_noisy_straight_level_flight(); print("PASS test_maneuver")

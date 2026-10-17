"""Predictive model of the ground station's stale belief (extends Proposition 1 from bounds to a prediction for single gaps).

Set-up. An aircraft r that the station believes still lacks clearance m is in one of two states when m is transmitted:
  L  it really lacks m                  (an uplink reaches it with probability 1-p)
  H  it already holds m, the station does not know (the report that would have told it was lost, probability q)
After every uplink each aircraft the station believes needs something sends a report; each report is lost with probability q.
g_k = number of uplinks between the k-th and (k+1)-th transmission of m (taken from the schedule the coder produced).
Per clearance, with x_k, y_k = probability that the k-th transmission of m finds the aircraft in L, H:
        x_1 = 1,  y_1 = 0,        x_(k+1) = p x_k,        y_(k+1) = s_k [ (1-p) x_k + y_k ],      s_k = (1 - c)^(g_k)
where c is the probability that one uplink corrects a stale belief: c = 1-q for full reporting; c = (1-p)(1-q) for change-triggered
reporting (a stale aircraft only reports after an uplink it actually received). The wasted fraction of single-gap receptions is
        W1 = sum_m sum_k y_k / sum_m sum_k (x_k + y_k).
For a pair whose repeats are g apart this gives the closed form  expected wasted receptions per pair = (1-p) s/(1-s), s = (1-c)^g.
The model takes (p, q, c) from the channel and the repeat schedule from the coder: it predicts how beliefs degrade over successive
transmissions, instead of only bounding them. Gaps with j >= 2 believed gaps remain bounded by Proposition 1: p_hat^j <= W(j) <= p_hat,
with p_hat = W1 (one report refreshes all gaps at once, which is why the measured values sit near the upper limit); no closed form is claimed.
"""
import numpy as np


def chain_w1(seqs, p, q, policy=0):
    """seqs: for each clearance, the list of gaps (in uplinks) between its successive transmissions. Returns predicted W1."""
    c = (1 - q) if policy == 0 else (1 - p) * (1 - q)
    X = Y = 0.0
    for gs in seqs:
        x, y = 1.0, 0.0
        sx, sy = x, y
        for g in gs:
            y = (1 - c) ** g * ((1 - p) * x + y)
            x = p * x
            sx += x; sy += y
        X += sx; Y += sy
    return Y / (X + Y) if X + Y else float("nan")


def pair_waste(p, q, g, policy=0):
    """closed form: expected wasted receptions per (clearance, aircraft) pair when repeats are g uplinks apart"""
    c = (1 - q) if policy == 0 else (1 - p) * (1 - q)
    s = (1 - c) ** g
    return (1 - p) * s / (1 - s)


def repeat_seqs(txs):
    """per clearance, the gaps (in uplinks) between consecutive transmissions, from a run's transmission list"""
    idx = {}
    for i, x in enumerate(txs):
        for m in x["T"]:
            idx.setdefault(m, []).append(i)
    return [[int(b - a) for a, b in zip(v, v[1:])] for v in idx.values()]


def measured_w1(gapstat):
    n = sum(gapstat.get(k, [0, 0])[0] for k in ("u1", "c1"))
    w = sum(gapstat.get(k, [0, 0])[1] for k in ("u1", "c1"))
    return (w / n if n else None), n

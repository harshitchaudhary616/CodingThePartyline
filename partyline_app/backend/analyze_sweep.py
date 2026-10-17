"""Summarise the robustness sweeps (run_sweep.sh) against the default study at critical weight 10.
For every configuration: STGC2 versus class-blind IDNC (idnc_best) and versus class-aware IDNC (idnc_cls), pooled over the
airspaces with the two-level block bootstrap of analyze_all.py.

  python3 analyze_sweep.py 4 5 8 9 11 12 13 14
Writes data/sweep_summary.txt
"""
import json, os, sys
import numpy as np
from analyze_all import load, boot, HERE

CONFIGS = [   # label, file suffix (after _A60)
    ("DEFAULT ideal feedback",            "_cw10"),
    ("DEFAULT 60% of reports lost",       "_rep0.6_cw10"),
    ("rate 0.1/min, ideal",               "_cw10_ur0.1"),
    ("rate 0.5/min, ideal",               "_cw10_ur0.5"),
    ("rate 1.0/min, ideal",               "_cw10_ur1"),
    ("rate 0.1/min, 60% lost",            "_rep0.6_cw10_ur0.1"),
    ("rate 0.5/min, 60% lost",            "_rep0.6_cw10_ur0.5"),
    ("rate 1.0/min, 60% lost",            "_rep0.6_cw10_ur1"),
    ("collisions 0.1, 60% lost",          "_rep0.6_cw10_coll0.1"),
    ("collisions 0.3, 60% lost",          "_rep0.6_cw10_coll0.3"),
    ("NACK-only, NACK loss 0.1",          "_nack0.1_cw10"),
    ("NACK-only, NACK loss 0.3",          "_nack0.3_cw10"),
    ("repair hold 10 s, 60% lost",        "_rep0.6_cw10_hold10"),
    ("repair hold 20 s, 60% lost",        "_rep0.6_cw10_hold20"),
]
METRICS = [("n_tx", "uplinks saved %", True), ("crit_miss", "strict crit miss pts", False),
           ("crit_miss_excl", "crit miss pts", False), ("aware_miss_excl", "aware miss pts", False)]


def cell(D, ids, x, y, key, rel, rng):
    d = {}
    for i in ids:
        if x in D[i] and y in D[i]:
            ax = np.array([np.nan if w[key] is None else w[key] for w in D[i][x]], float)
            ay = np.array([np.nan if w[key] is None else w[key] for w in D[i][y]], float)
            d[i] = (100 * (ay - ax) / np.where(ay == 0, np.nan, ay)) if rel else 100 * (ax - ay)
    if not d:
        return "n/a"
    e, lo, hi = boot(d, rng)
    good = (lo > 0) if rel else (hi < 0)
    bad = (hi < 0) if rel else (lo > 0)
    return f"{e:+6.1f} [{lo:+6.1f},{hi:+6.1f}]{'*' if good else ('-' if bad else ' ')}"


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_sweep.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("STGC2 versus IDNC, critical weight 10, loss 0.3, pooled over airspaces " + " ".join(ids))
    P("  uplinks: % saved (positive = STGC2 better); misses: percentage points (negative = STGC2 better)")
    P("  [low, high] = 95% two-level block bootstrap; * = significantly in favour of STGC2, - = in favour of IDNC\n")
    for base, name in (("idnc_best", "class-blind IDNC"), ("idnc_cls", "class-aware IDNC")):
        P(f"=== STGC2 vs {name}")
        P(f"{'configuration':30}" + "".join(f"{lab:>29}" for _, lab, _ in METRICS))
        for lab, sfx in CONFIGS:
            D = {}
            for i in ids:
                p = os.path.join(HERE, "data", f"party_dataset{i}_loss0.3_A60{sfx}.json")
                if os.path.exists(p):
                    D[i] = json.load(open(p))["per_window"]
            if not D:
                P(f"{lab:30}  (no files yet)")
                continue
            P(f"{lab:30}" + "".join(f"{cell(D, list(D), 'stgc2', base, k, rel, rng):>29}" for k, _, rel in METRICS) + f"   [{len(D)} airspaces]")
        P()
    p = os.path.join(HERE, "data", "sweep_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
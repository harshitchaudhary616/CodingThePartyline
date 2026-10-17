"""Summarise the sensitivity runs (run_sensitivity.sh): STGC2 versus class-blind and class-aware IDNC when the awareness
deadline A and the sector size change. Same pooled two-level block bootstrap as analyze_sweep.py.

  python3 analyze_sensitivity.py 4 5 8 9 11 12 13 14
Writes data/sensitivity_summary.txt
"""
import json, os, sys
import numpy as np
from analyze_sweep import cell, METRICS
from analyze_all import HERE

CONFIGS = [   # label, file suffix after "_loss0.3_"
    ("A = 30 s, ideal",             "A30_cw10"),
    ("A = 30 s, 60% lost",          "A30_rep0.6_cw10"),
    ("A = 120 s, ideal",            "A120_cw10"),
    ("A = 120 s, 60% lost",         "A120_rep0.6_cw10"),
    ("sector 40 NM, ideal",         "A60_cw10_sec40"),
    ("sector 40 NM, 60% lost",      "A60_rep0.6_cw10_sec40"),
    ("sector 90 NM, ideal",         "A60_cw10_sec90"),
    ("sector 90 NM, 60% lost",      "A60_rep0.6_cw10_sec90"),
]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_sensitivity.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("STGC2 versus IDNC under other definitions of the awareness class, critical weight 10, loss 0.3, airspaces " + " ".join(ids))
    P("  uplinks: % saved (positive = STGC2 better); misses: percentage points (negative = STGC2 better)")
    P("  [low, high] = 95% two-level block bootstrap; * = significantly in favour of STGC2, - = in favour of IDNC\n")
    for base, name in (("idnc_best", "class-blind IDNC"), ("idnc_cls", "class-aware IDNC")):
        P(f"=== STGC2 vs {name}")
        P(f"{'configuration':26}" + "".join(f"{lab:>29}" for _, lab, _ in METRICS))
        for lab, sfx in CONFIGS:
            D = {}
            for i in ids:
                p = os.path.join(HERE, "data", f"party_dataset{i}_loss0.3_{sfx}.json")
                if os.path.exists(p):
                    D[i] = json.load(open(p))["per_window"]
            if not D:
                P(f"{lab:26}  (no files yet)")
                continue
            P(f"{lab:26}" + "".join(f"{cell(D, list(D), 'stgc2', base, k, rel, rng):>29}" for k, _, rel in METRICS) + f"   [{len(D)} airspaces]")
        P()
    p = os.path.join(HERE, "data", "sensitivity_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
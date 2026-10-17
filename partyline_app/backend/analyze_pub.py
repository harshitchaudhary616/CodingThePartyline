"""STGC2 versus the published-style IDNC baseline (idnc_pub), pooled over airspaces with the two-level block bootstrap.
  python3 analyze_pub.py 4 5 8 9 11 12 13 14        (reads pubout/data, writes pubout/pub_summary.txt)"""
import os, sys, json
import numpy as np
from analyze_all import boot, HERE
from analyze_sweep import cell, METRICS

CONFIGS = [("ideal feedback", "_cw10"), ("60% of reports lost", "_rep0.6_cw10")]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_pub.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("STGC2 versus published-style IDNC (idnc_pub), critical weight 10, loss 0.3, airspaces " + " ".join(ids))
    P("  uplinks: % saved (positive = STGC2 better); misses: percentage points (negative = STGC2 better)\n")
    for base, name in (("idnc_pub", "published-style IDNC"), ("idnc_best", "our class-blind IDNC"), ("idnc_cls", "class-aware IDNC")):
        P(f"=== STGC2 vs {name}")
        P(f"{'configuration':24}" + "".join(f"{lab:>29}" for _, lab, _ in METRICS))
        for lab, sfx in CONFIGS:
            D = {}
            for i in ids:
                p = os.path.join(HERE, "pubout", "data", f"party_dataset{i}_loss0.3_A60{sfx}.json")
                if os.path.exists(p):
                    D[i] = json.load(open(p))["per_window"]
            if not D:
                P(f"{lab:24}  (no files yet)"); continue
            P(f"{lab:24}" + "".join(f"{cell(D, list(D), 'stgc2', base, k, rel, rng):>29}" for k, _, rel in METRICS) + f"   [{len(D)} airspaces]")
        P()
    p = os.path.join(HERE, "pubout", "pub_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
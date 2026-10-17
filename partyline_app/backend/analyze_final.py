"""Conflict-driven clearances (cfout) and p-persistent CSMA contention (csmaout2, csmaout6): STGC2 versus class-blind and class-aware IDNC,
pooled over airspaces with the two-level block bootstrap.
  python3 analyze_final.py 4 5 8 9 11 12 13 14        (writes final_summary.txt)"""
import os, sys, json
import numpy as np
from analyze_all import boot, HERE
from analyze_sweep import cell, METRICS

BLOCKS = [("CONFLICT-DRIVEN CLEARANCES (pure conflict traffic)", "cfout", [("ideal feedback", "_cw10_ur0"), ("60% of reports lost", "_rep0.6_cw10_ur0")]),
          ("CONTENTION, 2 competing stations, p=0.05, 60% lost", "csmaout2", [("60% of reports lost", "_rep0.6_cw10")]),
          ("CONTENTION, 6 competing stations, p=0.05, 60% lost", "csmaout6", [("60% of reports lost", "_rep0.6_cw10")])]
PAIRS = [("STGC2 vs class-blind IDNC", "stgc2", "idnc_best"), ("STGC2 vs class-aware IDNC", "stgc2", "idnc_cls")]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_final.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("Final extension results, critical weight 10, loss 0.3, airspaces " + " ".join(ids))
    P("  uplinks: % saved by STGC2; misses: points (negative = STGC2 better); * STGC2 better, - STGC2 worse (95% bootstrap)\n")
    for title, outdir, cfgs in BLOCKS:
        P("##### " + title)
        for lab, sfx in cfgs:
            D = {}
            for i in ids:
                p = os.path.join(HERE, outdir, "data", f"party_dataset{i}_loss0.3_A60{sfx}.json")
                if os.path.exists(p):
                    D[i] = json.load(open(p))["per_window"]
            P(f"=== {lab}   [{len(D)} airspaces]")
            P(f"{'comparison':32}" + "".join(f"{m[1]:>29}" for m in METRICS))
            for name, x, y in PAIRS:
                P(f"{name:32}" + ("  (no files)" if not D else "".join(f"{cell(D, list(D), x, y, k, rel, rng):>29}" for k, _, rel in METRICS)))
            P()
    p = os.path.join(HERE, "final_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
"""Where does each part of STGC2 pay? Builds the system up from class-aware IDNC one layer at a time, using the main-study
result files that already exist (no new runs). Pooled over airspaces with the two-level block bootstrap.
  python3 analyze_layers.py 4 5 8 9 11 12 13 14       (writes data/layers_summary.txt)
Pairs are (better-if-positive scheme, reference). Uplinks: % saved; misses: points (negative = first scheme better)."""
import os, sys, json
import numpy as np
from analyze_all import boot, HERE
from analyze_sweep import cell, METRICS

STEPS = [   # label, x, y
    ("tiered repair holding added to IDNC-cls", "idnc_tiered_cls", "idnc_cls"),
    ("stored random-linear repairs + clique seeds added (STGC2 vs tiered IDNC-cls)", "stgc2", "idnc_tiered_cls"),
    ("all layers: STGC2 vs IDNC-cls", "stgc2", "idnc_cls"),
    ("class weights inside STGC (STGC vs class-blind STGC)", "stgc", "stgc_noclass"),
    ("holding inside STGC (STGC vs repairs sent at once)", "stgc", "stgc_hold0"),
]
CONFIGS = [("ideal feedback", "_cw10"), ("60% of reports lost", "_rep0.6_cw10")]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_layers.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("Layer-by-layer value of STGC2, critical weight 10, loss 0.3, airspaces " + " ".join(ids))
    P("  uplinks: % saved by the first scheme; misses: points (negative = first scheme better); * first better, - first worse (95% bootstrap)\n")
    for lab, sfx in CONFIGS:
        D = {}
        for i in ids:
            p = os.path.join(HERE, "data", f"party_dataset{i}_loss0.3_A60{sfx}.json")
            if os.path.exists(p):
                D[i] = json.load(open(p))["per_window"]
        P(f"=== {lab}   [{len(D)} airspaces]")
        P(f"{'step':78}" + "".join(f"{m[1]:>29}" for m in METRICS))
        for name, x, y in STEPS:
            if not D:
                P(f"{name:78}  (no files)"); continue
            P(f"{name:78}" + "".join(f"{cell(D, list(D), x, y, k, rel, rng):>29}" for k, _, rel in METRICS))
        P()
    p = os.path.join(HERE, "data", "layers_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
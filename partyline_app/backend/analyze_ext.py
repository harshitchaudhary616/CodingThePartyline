"""Ablations and the rate-adaptive hold, pooled over airspaces with the two-level block bootstrap.
  python3 analyze_ext.py 4 5 8 9 11 12 13 14        (reads ablout/data and adout/data, writes ext_summary.txt)
Uplinks: % saved by the first scheme; misses: points (negative = first scheme better); * first better, - first worse."""
import os, sys, json
import numpy as np
from analyze_all import boot, HERE
from analyze_sweep import cell, METRICS

ABL = [("class weights inside STGC: stgc vs stgc_noclass", "stgc", "stgc_noclass"),
       ("holding inside STGC: stgc vs stgc_hold0", "stgc", "stgc_hold0"),
       ("STGC2 vs STGC (clique seeds)", "stgc2", "stgc"),
       ("STGC2 vs IDNC-cls (check)", "stgc2", "idnc_cls")]
AD = [("STGC-AD vs IDNC-cls", "stgc_ad", "idnc_cls"), ("STGC-AD vs STGC2", "stgc_ad", "stgc2"), ("STGC2 vs IDNC-cls", "stgc2", "idnc_cls")]
ABL_CFG = [("ideal feedback", "_cw10"), ("60% of reports lost", "_rep0.6_cw10")]
AD_CFG = [("rate 0.25, ideal", "_cw10"), ("rate 0.25, 60% lost", "_rep0.6_cw10"), ("rate 1.0, ideal", "_cw10_ur1"), ("rate 1.0, 60% lost", "_rep0.6_cw10_ur1")]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_ext.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("Extension results, critical weight 10, loss 0.3, airspaces " + " ".join(ids))
    P("  uplinks: % saved by the first scheme; misses: points (negative = first scheme better); * first better, - first worse (95% bootstrap)\n")
    for title, outdir, pairs, cfgs in (("ABLATIONS", "ablout", ABL, ABL_CFG), ("RATE-ADAPTIVE HOLD", "adout", AD, AD_CFG)):
        P("##### " + title)
        for lab, sfx in cfgs:
            D = {}
            for i in ids:
                p = os.path.join(HERE, outdir, "data", f"party_dataset{i}_loss0.3_A60{sfx}.json")
                if os.path.exists(p):
                    D[i] = json.load(open(p))["per_window"]
            P(f"=== {lab}   [{len(D)} airspaces]")
            P(f"{'comparison':46}" + "".join(f"{m[1]:>29}" for m in METRICS))
            for name, x, y in pairs:
                P(f"{name:46}" + ("  (no files)" if not D else "".join(f"{cell(D, list(D), x, y, k, rel, rng):>29}" for k, _, rel in METRICS)))
            P()
    p = os.path.join(HERE, "ext_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
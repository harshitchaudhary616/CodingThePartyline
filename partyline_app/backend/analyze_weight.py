"""Critical weight on harsh channels: STGC2 versus class-aware IDNC at weight 10 (futchcon / futchsev), 20 and 40 (wtcon*, wtsev*).
  python3 analyze_weight.py 4 5 8 9 11 12 13 14        (writes weightsummary.txt)"""
import os, sys, json
import numpy as np
from analyze_all import HERE
from analyze_sweep import cell, METRICS

CH = [("conservative channel (loss 0.4)", 0.4, [(10, "futchcon"), (20, "wtcon20"), (40, "wtcon40")]),
      ("severe channel (loss 0.5)", 0.5, [(10, "futchsev"), (20, "wtsev20"), (40, "wtsev40")])]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_weight.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("CRITICAL WEIGHT ON HARSH CHANNELS (60% of reports lost): STGC2 versus class-aware IDNC, both at the weight shown")
    P("  uplinks: % saved (positive = STGC2 better); misses: points (negative = STGC2 better); [95% two-level block bootstrap]; * STGC2 better, - worse\n")
    for lab, loss, cfg in CH:
        P(f"=== {lab}")
        P(f"{'weight':8}" + "".join(f"{m[1]:>29}" for m in METRICS) + "   critical miss % (excl.): IDNC-cls / STGC2   uplinks IDNC-cls / STGC2")
        for w, folder in cfg:
            D = {}
            for i in ids:
                p = os.path.join(HERE, folder, "data", f"party_dataset{i}_loss{loss:g}_A60_rep0.6_cw{w}.json")
                if os.path.exists(p):
                    D[i] = json.load(open(p))["per_window"]
            if not D:
                P(f"{w:<8} (no files yet)"); continue
            mu = lambda s, k: np.mean([x[k] for d in D.values() for x in d[s] if x.get(k) is not None])
            P(f"{w:<8}" + "".join(f"{cell(D, list(D), 'stgc2', 'idnc_cls', k, rel, rng):>29}" for k, _, rel in METRICS)
              + f"   {100 * mu('idnc_cls', 'crit_miss_excl'):.2f} / {100 * mu('stgc2', 'crit_miss_excl'):.2f}"
              + f"   {mu('idnc_cls', 'n_tx'):.0f} / {mu('stgc2', 'n_tx'):.0f}   [{len(D)} airspaces]")
        P()
    p = os.path.join(HERE, "weightsummary.txt")
    open(p, "w").write("\n".join(lines) + "\n"); print("saved", p)


if __name__ == "__main__":
    main()

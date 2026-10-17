"""Leave-one-airspace-out sensitivity of the headline comparisons (STGC2 versus class-aware IDNC), from the saved result files.
For each configuration and each metric: the pooled mean over all airspaces, the range of the pooled mean when one airspace is dropped
(and which airspace moves it most), and in how many airspaces STGC2 is better.
  python3 analyze_loo.py 4 5 8 9 11 12 13 14        (writes loosummary.txt)"""
import os, sys, json
import numpy as np
from analyze_all import HERE

CFG = [("main study, 60% lost", "futfb0", 0.3, "_rep0.6_cw10"), ("main study, ideal feedback", "data", 0.3, "_cw10"),
       ("conservative channel", "futchcon", 0.4, "_rep0.6_cw10"), ("severe channel", "futchsev", 0.5, "_rep0.6_cw10"),
       ("sector 240 NM", "futsec240", 0.3, "_rep0.6_cw10_sec240"), ("conflict-driven, 60% lost", "futcf", 0.3, "_rep0.6_cw10_ur0"),
       ("manoeuvre-derived, 60% lost", "manrep", 0.3, "_rep0.6_cw10_ur0")]
MET = [("n_tx", "uplinks saved %", True, +1), ("crit_miss_excl", "critical miss pts", False, -1), ("aware_miss_excl", "awareness miss pts", False, -1)]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_loo.py 4 5 8 9 11 12 13 14")
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("LEAVE-ONE-AIRSPACE-OUT: STGC2 versus class-aware IDNC (uplinks: % saved, positive = STGC2 better; misses: points, negative = STGC2 better)")
    P(f"{'configuration':30}{'metric':22}{'all':>8}{'LOO range':>18}{'most influential':>18}{'STGC2 better in':>17}")
    for lab, folder, loss, sfx in CFG:
        W = {}
        for i in ids:
            p = os.path.join(HERE, folder, "data", f"party_dataset{i}_loss{loss:g}_A60{sfx}.json")
            if os.path.exists(p):
                d = json.load(open(p))["per_window"]
                if "stgc2" in d and "idnc_cls" in d:
                    W[i] = d
        if len(W) < 3:
            P(f"{lab:30}(fewer than 3 airspaces with files)"); continue
        for key, mlab, rel, good in MET:
            per = {}
            for i, d in W.items():
                a = np.array([np.nan if w[key] is None else w[key] for w in d["stgc2"]], float)
                b = np.array([np.nan if w[key] is None else w[key] for w in d["idnc_cls"]], float)
                per[i] = (100 * (b - a) / np.where(b == 0, np.nan, b)) if rel else 100 * (a - b)
            pool = lambda ks: float(np.nanmean(np.concatenate([per[k] for k in ks])))
            allv = pool(list(per))
            loo = {i: pool([k for k in per if k != i]) for i in per}
            infl = max(loo, key=lambda i: abs(loo[i] - allv))
            better = sum(1 for i in per if (np.nanmean(per[i]) * good) > 0)
            P(f"{lab:30}{mlab:22}{allv:8.1f}{'[%6.1f,%6.1f]' % (min(loo.values()), max(loo.values())):>18}{('drop ' + str(infl)):>18}{('%d of %d' % (better, len(per))):>17}")
        P()
    p = os.path.join(HERE, "loosummary.txt")
    open(p, "w").write("\n".join(lines) + "\n"); print("saved", p)


if __name__ == "__main__":
    main()

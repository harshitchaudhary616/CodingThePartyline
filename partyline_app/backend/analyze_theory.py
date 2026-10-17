"""Does measured waste follow the propositions? Reads finalout/data (run_final.sh, 60% reports lost) and pools, over airspaces and windows,
the receptions by aircraft that the station believed needed something, grouped by packet kind (u = single clearance, c = coded packet)
and by j = number of clearances of the packet the station believed the aircraft still lacked.
  python3 analyze_theory.py 4 5 8 9 11 12 13 14       (writes finalout/theory_summary.txt)
p_hat = measured waste of coded packets with j = 1. Independent staleness predicts p_hat**j; fully correlated staleness predicts p_hat;
the general bound is p_hat**j <= waste(j) <= p_hat (a mix is wasted only if every believed gap is already held)."""
import os, sys, json
import numpy as np
from analyze_all import HERE

SCHEMES = ["stgc2", "idnc_cls", "stgc"]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_theory.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("Measured waste of receptions by aircraft with a believed need, 60% of reports lost, critical weight 10, airspaces " + " ".join(ids))
    P("  j = clearances in the packet that the station believed the aircraft lacked; waste = the reception brought no new degree of freedom\n")
    for s in SCHEMES:
        W = []                       # per window: dict key -> [n, w]
        for i in ids:
            p = os.path.join(HERE, "finalout", "data", f"party_dataset{i}_loss0.3_A60_rep0.6_cw10.json")
            if os.path.exists(p):
                D = json.load(open(p))["per_window"].get(s, [])
                W += [w["gap"] for w in D if w.get("gap")]
        if not W:
            P(f"{s}: (no files)"); continue
        keys = sorted({k for g in W for k in g})

        def pooled(sel):
            tot = {k: [0, 0] for k in keys}
            for g in sel:
                for k, (a, b) in g.items():
                    tot[k][0] += a; tot[k][1] += b
            return tot
        tot = pooled(W)
        boots = []
        for _ in range(1000):
            sel = [W[j] for j in rng.integers(0, len(W), len(W))]
            boots.append(pooled(sel))
        P(f"=== {s}   [{len(W)} windows]")
        P(f"{'kind,j':8}{'receptions':>12}{'wasted %':>10}{'95% CI':>18}")
        for k in keys:
            n, w = tot[k]
            if n == 0 or k.endswith("0"):
                continue
            r = [b[k][1] / b[k][0] for b in boots if b[k][0] > 0]
            P(f"{k:8}{n:12d}{100 * w / n:10.1f}{'[%5.1f,%5.1f]' % (100 * np.percentile(r, 2.5), 100 * np.percentile(r, 97.5)):>18}")
        c1 = tot.get("c1")
        if c1 and c1[0]:
            ph = c1[1] / c1[0]
            P(f"p_hat (coded, j=1) = {100 * ph:.1f}%")
            P(f"{'j':4}{'independent p^j':>18}{'fully correlated p':>20}{'measured':>12}")
            for j in (2, 3):
                n, w = tot.get(f"c{j}", [0, 0])
                if n:
                    P(f"{j:<4}{100 * ph ** j:17.1f}%{100 * ph:19.1f}%{100 * w / n:11.1f}%")
        P()
    p = os.path.join(HERE, "finalout", "theory_summary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()
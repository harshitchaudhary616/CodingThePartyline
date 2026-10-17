"""Final analysis over per-airspace result files (from run_all.sh): critical-weight choice by leave-one-airspace-out,
pooled comparison with a two-level block bootstrap (resample airspaces, then blocks of consecutive windows).

  python3 analyze_all.py 4 5 8 9 11 12 13 14            (ideal feedback)
  python3 analyze_all.py 4 5 8 9 11 12 13 14 --rep 0.6   (lossy state reports)
  python3 analyze_all.py 4 5 8 9 11 12 13 14 --cws 1 3 5 10 20 40   (wider weight grid)
Reads data/party_dataset<id>_loss<L>_A60[_rep<q>][_cw<w>].json, writes data/final_summary_<mode>.txt
"""
import argparse, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CWS = [1, 3, 5, 10]
CW_SCHEMES = ["stgc", "stgc2", "idnc_cls", "broadcast_cls", "coded_cls", "tiered_cls", "idnc_tiered_cls"]   # depend on the weight
BASE = ["unicast", "broadcast_best", "idnc_hd", "idnc_best", "coded_best", "tiered", "idnc_tiered", "rlnc_sys", "rlnc_group"]
METRICS = [("n_tx", "uplinks"), ("chan", "channel s"), ("crit_miss_excl", "hard miss"), ("aware_miss_excl", "aware miss")]


def load(ids, loss, rep, cw):
    D = {}
    for i in ids:
        sfx = (f"_rep{rep:g}" if rep else "") + (f"_cw{cw:g}" if cw != 3 else "")
        p = os.path.join(HERE, "data", f"party_dataset{i}_loss{loss:g}_A60{sfx}.json")
        if os.path.exists(p):
            D[i] = json.load(open(p))["per_window"]
        else:
            print("missing", p, file=sys.stderr)
    return D


def arr(D, scheme, key, ids):
    """per-airspace arrays of a metric (None -> nan)"""
    return {i: np.array([np.nan if w[key] is None else w[key] for w in D[i][scheme]], float) for i in ids if scheme in D[i]}


def boot(diffs, rng, B=2000, block=3):
    """diffs: {airspace: per-window paired differences}. Two-level block bootstrap of the pooled mean."""
    ks = [k for k in diffs if len(diffs[k])]
    est = np.nanmean(np.concatenate([diffs[k] for k in ks]))
    out = []
    for _ in range(B):
        sel = rng.choice(len(ks), len(ks))
        vals = []
        for j in sel:
            d = diffs[ks[j]]; n = len(d)
            b = min(block, n); nb = int(np.ceil(n / b))
            st = rng.integers(0, n - b + 1, nb)
            vals.append(np.concatenate([d[s:s + b] for s in st])[:n])
        out.append(np.nanmean(np.concatenate(vals)))
    return est, np.percentile(out, 2.5), np.percentile(out, 97.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--loss", type=float, default=0.3)
    ap.add_argument("--rep", type=float, default=0.0, help="state-report loss; 0 = ideal feedback")
    ap.add_argument("--cws", type=float, nargs="*", default=[1, 3, 5, 10], help="critical weights to choose from (3 must be included)")
    a = ap.parse_args()
    global CWS
    CWS = [int(c) if c == int(c) else c for c in a.cws]
    ids = a.ids
    rng = np.random.default_rng(1)
    DS = {cw: load(ids, a.loss, a.rep, cw) for cw in CWS}
    ids = [i for i in ids if all(i in DS[cw] for cw in CWS)]
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P(f"airspaces {ids}, loss {a.loss}, " + (f"lossy state reports (loss {a.rep})" if a.rep else "ideal feedback") + f", weight grid {CWS}")
    P("windows per airspace: " + ", ".join(f"{i}:{len(DS[3][i]['unicast'])}" for i in ids))

    # ---- leave-one-airspace-out choice of the critical weight (objective: hard misses, ties -> fewer awareness misses)
    P("\n== critical weight chosen on the other airspaces, evaluated on the held-out one (hard miss %, awareness miss %)")
    chosen = {s: {} for s in CW_SCHEMES}
    for s in CW_SCHEMES:
        for h in ids:
            rest = [i for i in ids if i != h]
            score = {}
            for cw in CWS:
                c = np.concatenate(list(arr(DS[cw], s, "crit_miss_excl", rest).values()))
                w = np.concatenate(list(arr(DS[cw], s, "aware_miss_excl", rest).values()))
                score[cw] = (np.nanmean(c), np.nanmean(w))
            chosen[s][h] = min(CWS, key=lambda cw: (round(score[cw][0], 4), score[cw][1]))
    P(f"{'scheme':16}" + "".join(f"{str(i):>12}" for i in ids) + "   (chosen weight when this airspace is held out)")
    for s in CW_SCHEMES:
        P(f"{s:16}" + "".join(f"{chosen[s][i]:>12}" for i in ids))

    # held-out table: every airspace scored at the weight chosen without it
    def held(s, key, i):
        if s in CW_SCHEMES:
            return arr(DS[chosen[s][i]], s, key, [i])[i]
        return arr(DS[3], s, key, [i])[i]
    P("\n== held-out results pooled over airspaces (mean over windows; weight-dependent schemes use their held-out weight)")
    P(f"{'scheme':16}" + "".join(f"{lab:>13}" for _, lab in METRICS))
    for s in BASE + CW_SCHEMES:
        row = []
        for k, _ in METRICS:
            v = np.concatenate([held(s, k, i) for i in ids if s in DS[3][i]])
            row.append(np.nanmean(v) * (100 if "miss" in k else 1))
        P(f"{s:16}" + "".join(f"{x:13.1f}" for x in row))

    # ---- paired differences, 95% bootstrap CI
    P("\n== paired differences, first scheme minus baseline, held-out weights; 95% CI from the two-level block bootstrap")
    P("   uplinks and channel in % saving (positive = first uses less); misses in percentage points (negative = first misses less)")
    pairs = [("stgc2", b) for b in BASE + ["broadcast_cls", "idnc_cls", "coded_cls", "tiered_cls", "idnc_tiered_cls", "stgc"]] + [("idnc_cls", "idnc_best"), ("stgc", "idnc_cls")]
    P(f"{'comparison':28}" + "".join(f"{lab:>26}" for _, lab in METRICS))
    for x, y in pairs:
        cells = []
        for k, _ in METRICS:
            d = {}
            for i in ids:
                if x in DS[3][i] and y in DS[3][i]:
                    ax, ay = held(x, k, i), held(y, k, i)
                    d[i] = (100 * (ay - ax) / np.where(ay == 0, np.nan, ay)) if k in ("n_tx", "chan") else 100 * (ax - ay)
            e, lo, hi = boot(d, rng)
            mark = "*" if (lo > 0 if k in ("n_tx", "chan") else hi < 0) else ("-" if (hi < 0 if k in ("n_tx", "chan") else lo > 0) else " ")
            cells.append(f"{e:+7.1f} [{lo:+6.1f},{hi:+6.1f}]{mark}")
        P(f"{x + ' vs ' + y:28}" + "".join(f"{c:>26}" for c in cells))
    P("  * = CI excludes 0 in favour of the first scheme, - = in favour of the baseline")

    # ---- per-airspace consistency
    P("\n== per airspace: stgc2 vs idnc_cls, hard-miss difference in points (negative = stgc2 better) and uplink saving %")
    for i in ids:
        dm = np.nanmean(held("stgc2", "crit_miss_excl", i) - held("idnc_cls", "crit_miss_excl", i)) * 100
        du = np.nanmean(100 * (held("idnc_cls", "n_tx", i) - held("stgc2", "n_tx", i)) / held("idnc_cls", "n_tx", i))
        P(f"  {i:>10}  hard miss {dm:+6.2f} pts   uplinks {du:+6.1f} %")
    p = os.path.join(HERE, "data", f"final_summary_{'rep' + format(a.rep, 'g') if a.rep else 'ideal'}{'_wide' if max(CWS) > 10 else ''}.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("\nsaved", p)


if __name__ == "__main__":
    main()
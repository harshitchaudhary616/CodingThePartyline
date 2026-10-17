"""Fair tuning and leave-one-dataset-out validation for the party-line study.

Every hold-based scheme (idnc_tiered, tiered, their class-aware versions, stgc) gets the SAME treatment: its repair
hold time is chosen from a grid on TRAINING airspaces only and then evaluated on the held-out airspace. Each airspace
is held out once (3 folds for datasets 4 5 8), and the held-out windows are pooled, so every window is evaluated with
a hold time chosen WITHOUT looking at it. Schemes without a hold parameter are run once.

Selection rule (the same for every scheme): among the holds whose training hard-deadline miss rate is within 1 point
and whose awareness miss rate is within 3 points of the best hold, take the one with the fewest uplinks.

  python3 experiments_tune.py --synthetic
  python3 experiments_tune.py --dataset 4 5 8 --loss 0.3
  python3 experiments_tune.py --dataset 4 5 8 --loss 0.3 --reports --fbloss 0.3
Writes data/party_tuned_dataset<ids>_loss<loss>_A<A>[...].json  (same layout as experiments_party.py, meta.tuned = true)
"""
import argparse, json, os, sys, time
import numpy as np
import schedulers2, schedulers3, schedulers4, schedulers5          # noqa: F401  (register schemes)
import experiments2 as E
from awareness import with_awareness
from experiments_algo import load_windows
from experiments_party import class_metrics
from partyline import engine2
from partyline.engine import from_tracks, make_synthetic

HERE = os.path.dirname(os.path.abspath(__file__))
HOLD_SCHEMES = ["idnc_tiered", "tiered", "idnc_tiered_cls", "tiered_cls", "stgc"]
FIXED = ["broadcast_best", "idnc_hd", "idnc_best", "coded_best", "rlnc_group", "broadcast_cls", "idnc_cls", "coded_cls"]


def build(a):
    groups = {}
    if a.synthetic:
        for g in range(3):
            groups[f"syn{g + 1}"] = [make_synthetic(dict(rate=a.rate, dur_min=8), 1 + g * a.n_syn + s) for s in range(a.n_syn)]
    else:
        k = 0
        for ds in a.dataset:
            d, wins = load_windows(ds, a.window, a.min_aircraft)
            L = []
            for w in wins:
                k += 1
                try:
                    L.append(from_tracks(w, {}, 1000 + k))
                except ValueError:
                    pass
            groups[str(ds)] = L
    out = {}
    for g, L in groups.items():
        S = [with_awareness(s, A=a.A, sector=a.sector, r_aware=a.r_aware) for s in L]
        out[g] = [s for s in S if any(c.dem for c in s.clearances)]
    return out


def mean(v):
    v = [x for x in v if x is not None]
    return float(np.mean(v)) if v else float("nan")


def choose(rows, holds):
    """rows[hold] = list of per-window metric dicts (training windows). Returns the selected hold."""
    m = {h: (mean(x["n_tx"] for x in rows[h]), mean(x["crit_miss_excl"] for x in rows[h]), mean(x["aware_miss_excl"] for x in rows[h])) for h in holds}
    bc = min(v[1] for v in m.values()); ba = min(v[2] for v in m.values())
    ok = [h for h in holds if m[h][1] <= bc + 0.01 and m[h][2] <= ba + 0.03]
    return min(ok, key=lambda h: m[h][0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int, nargs="*")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--rate", type=float, default=3.0)
    ap.add_argument("--n-syn", type=int, default=3, help="windows per synthetic pseudo-dataset")
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--min-aircraft", type=int, default=8)
    ap.add_argument("--loss", type=float, default=0.3)
    ap.add_argument("--het", type=float, default=0.0)
    ap.add_argument("--A", type=float, default=60.0)
    ap.add_argument("--sector", type=float, default=60.0)
    ap.add_argument("--r-aware", type=float, default=40.0)
    ap.add_argument("--reports", action="store_true")
    ap.add_argument("--fbloss", type=float, default=0.0)
    ap.add_argument("--holds", type=float, nargs="*", default=[5, 10, 20, 30, 45, 60])
    ap.add_argument("--f-report", type=float, default=0.05)
    a = ap.parse_args()
    if not a.synthetic and not a.dataset:
        sys.exit("give --dataset N M ... (at least 2) or --synthetic")
    groups = build(a)
    if len(groups) < 2:
        sys.exit("need at least 2 datasets for leave-one-dataset-out")
    ch = dict(engine2.CH2_DEFAULTS, loss=a.loss, het=a.het, fbmode=1.0 if a.reports else 0.0, fbloss=a.fbloss if a.reports else 0.0)
    T0 = time.time()
    R = {g: {} for g in groups}

    def run(g, scheme, key):
        R[g][key] = [class_metrics(engine2.simulate(scheme, scn, ch, 1000 + i), scn, ch, scheme, a.f_report) for i, scn in enumerate(groups[g])]
    for g in groups:
        for s in FIXED:
            run(g, s, (s, None))
        print(f"  {g}: fixed schemes done ({time.time() - T0:.0f} s)", file=sys.stderr)
    for h in a.holds:
        schedulers4.register(hold=h); schedulers5.register(hold=h)
        for g in groups:
            for s in HOLD_SCHEMES:
                run(g, s, (s, h))
        print(f"  hold {h:g} s done ({time.time() - T0:.0f} s)", file=sys.stderr)

    # sensitivity to the hold time (all windows pooled)
    print(f"\nHOLD-TIME SENSITIVITY (all windows pooled, loss {a.loss}" + (f", reports lost {a.fbloss}" if a.reports else ", ideal feedback") + ")")
    print(f"{'scheme':16}{'hold s':>8}{'uplinks':>9}{'hard miss %':>13}{'aware miss %':>14}")
    for s in HOLD_SCHEMES:
        for h in a.holds:
            rows = [x for g in groups for x in R[g][(s, h)]]
            print(f"{s:16}{h:8g}{mean(x['n_tx'] for x in rows):9.1f}{100 * mean(x['crit_miss_excl'] for x in rows):13.1f}{100 * mean(x['aware_miss_excl'] for x in rows):14.1f}")

    # leave-one-dataset-out
    names = FIXED + HOLD_SCHEMES
    pooled = {n: [] for n in names}
    chosen = {}
    print("\nLEAVE-ONE-DATASET-OUT: hold chosen on the other airspaces")
    for t in groups:
        train = [g for g in groups if g != t]
        line = []
        for s in HOLD_SCHEMES:
            h = choose({h: [x for g in train for x in R[g][(s, h)]] for h in a.holds}, a.holds)
            chosen[(t, s)] = h
            pooled[s] += R[t][(s, h)]
            line.append(f"{s} {h:g} s")
        for s in FIXED:
            pooled[s] += R[t][(s, None)]
        print(f"  test on {t}: " + ", ".join(line))
    n_w = len(pooled[FIXED[0]])
    meta = dict(ids=a.dataset or [], name=("synthetic self-test" if a.synthetic else f"datasets {a.dataset}") + " (leave-one-dataset-out, holds tuned on the other airspaces)",
                is_real=not a.synthetic, windows=n_w, window_min=a.window, study="party", A=a.A, sector=a.sector, r_aware=a.r_aware, hold=0,
                het=a.het, f_report=a.f_report, reports=a.reports, fbloss=a.fbloss, tuned=True, holds=a.holds,
                chosen={f"{t}|{s}": h for (t, s), h in chosen.items()}, engine="engine2 (party-line overhearing, buffered decoding)")
    out = {"meta": meta, "channel": ch, "n": n_w, "schemes": {}, "paired": {}}
    ci = lambda n, k: (lambda v: E.ci95(v) if v else (float("nan"), 0.0))([x[k] for x in pooled[n] if x[k] is not None])
    print(f"\nHELD-OUT RESULTS, {n_w} windows, every window evaluated with a hold chosen without it")
    print(f"{'scheme':16}{'uplinks':>9}{'hard miss %':>13}{'aware miss %':>14}{'decoded %':>11}{'wasted %':>10}")
    for n in names:
        mm = {k: ci(n, k) for k in ("n_tx", "fb", "fb_nack", "chan", "chan_nack", "crit_miss", "crit_miss_excl", "aware_miss", "aware_miss_excl",
                                    "crit_lat", "aware_lat", "use_now", "use_store", "use_waste")}
        out["schemes"][n] = mm
        print(f"{n:16}{mm['n_tx'][0]:9.1f}{100 * mm['crit_miss_excl'][0]:9.1f}±{100 * mm['crit_miss_excl'][1]:<3.1f}{100 * mm['aware_miss_excl'][0]:10.1f}±{100 * mm['aware_miss_excl'][1]:<3.1f}"
              f"{100 * mm['use_now'][0]:11.1f}{100 * mm['use_waste'][0]:10.1f}")

    def cmp(a_, b_):
        X, Y = pooled[a_], pooled[b_]
        pct = lambda k: E.ci95([100 * (y[k] - x[k]) / y[k] for x, y in zip(X, Y) if y[k]])

        def d(k):
            v = [100 * (y[k] - x[k]) for x, y in zip(X, Y) if x[k] is not None and y[k] is not None]
            return E.ci95(v) if v else (0.0, 0.0)
        tx, ct, cn, cm, am = pct("n_tx"), pct("chan"), pct("chan_nack"), d("crit_miss_excl"), d("aware_miss_excl")
        out["paired"][f"{a_}_vs_{b_}"] = dict(tx_saving_pct=tx, chan_saving_pct=ct, chan_nack_saving_pct=cn, crit_miss_excl_pts=cm, aware_miss_excl_pts=am)
        f = lambda v: f"{v[0]:+7.1f}±{v[1]:<5.1f}{'*' if v[0] - v[1] > 0 else ('-' if v[0] + v[1] < 0 else ' ')}"
        print(f"{a_ + ' vs ' + b_:26}{f(tx)} {f(ct)} {f(cn)} {f(cm)} {f(am)}")
    print("\npaired differences on held-out windows (positive = first scheme better; * significantly better, - significantly worse)")
    print(f"{'':26}{'uplinks %':>15} {'channel %':>14} {'chan NACK %':>14} {'crit miss pts':>14} {'aware miss pts':>15}")
    for b in ("broadcast_best", "idnc_hd", "idnc_best", "coded_best", "rlnc_group", "idnc_tiered", "tiered"):
        cmp("stgc", b)
    print("-- FAIR: baselines that know the classes too")
    for b in ("broadcast_cls", "idnc_cls", "coded_cls", "idnc_tiered_cls", "tiered_cls"):
        cmp("stgc", b)
    print("-- tuned XOR-only schemes")
    for b in ("idnc_best", "idnc_tiered"):
        cmp("tiered", b)
    sfx = (f"_het{a.het:g}" if a.het > 0 else "") + (f"_r{a.r_aware:g}" if a.sector <= 0 else "") + (f"_rep{a.fbloss:g}" if a.reports else "")
    tag = "synthetic" if a.synthetic else "_".join(str(x) for x in a.dataset)
    p = os.path.join(HERE, "data", f"party_tuned_dataset{tag}_loss{a.loss:g}_A{a.A:g}{sfx}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("\nsaved", p)


if __name__ == "__main__":
    main()
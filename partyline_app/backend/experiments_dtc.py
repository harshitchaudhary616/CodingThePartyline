"""Deadline-tiered repair study on the party-line channel (engine2).

Question: does deciding WHEN to repair (deadline-tiered batching) matter more than HOW to code?
All schemes run on the same windows with the same random seeds, the same receivers (party-line
overhearing + buffering) and the same channel.

  immediate repair (send whatever is most valuable now):
    broadcast_best, idnc_hd (published-style IDNC with the hard-deadline rule), idnc_best, coded_best
  deadline-tiered repair batching (urgent needs and first transmissions at once; repairs collected for
  at most --hold s, or until a repair pair has < 60 s left, or 8 clearances wait, or a coded repair
  packet is already available):
    bcast_tiered, idnc_tiered, tiered (= proposed: our coder + tiered batching),
    dtc (tiered batching + delay-tolerant random-linear repair packets that aircraft store)
  tiered_h<H>: the proposed scheme at other hold times (transmissions vs latency trade-off curve)
Windows with fewer than 2 aircraft having 8+ airborne reports are skipped.

  python3 experiments_dtc.py --dataset 4 5 --loss 0.1
  python3 experiments_dtc.py --dataset 4 5 --loss 0.3 --het 0.6      (distance-dependent loss)
  python3 experiments_dtc.py --synthetic                               (quick self-test)
Writes data/dtc_dataset<ids>_loss<loss>_het<het>.json  (same layout as the algo_*.json files)
"""
import argparse, json, os, sys, time
import numpy as np
import schedulers2, schedulers3, schedulers4          # noqa: F401  (register schemes)
import experiments2 as E
from experiments_algo import metrics, load_windows
from partyline import coding, engine2
from partyline.engine import from_tracks, make_synthetic

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = ["broadcast_best", "idnc_hd", "idnc_best", "coded_best", "bcast_tiered", "idnc_tiered", "tiered", "dtc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int, nargs="*")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--min-aircraft", type=int, default=8)
    ap.add_argument("--loss", type=float, default=0.1)
    ap.add_argument("--het", type=float, default=0.0, help="0 = same loss for all aircraft; 0.6 = loss grows with distance")
    ap.add_argument("--overhear", type=float, default=1.0)
    ap.add_argument("--buffer", type=float, default=1.0)
    ap.add_argument("--hold", type=float, default=30.0)
    ap.add_argument("--no-dtc", action="store_true", help="skip the slower dtc scheme")
    ap.add_argument("--pareto", type=float, nargs="*", default=[10.0, 20.0, 60.0],
                    help="extra hold times for the proposed scheme (transmissions vs latency trade-off curve)")
    a = ap.parse_args()
    schedulers4.register(hold=a.hold)
    if a.synthetic:
        scns = [make_synthetic(dict(rate=6.0, dur_min=8), s) for s in range(1, 9)]
        meta = dict(ids=[], name="synthetic self-test", is_real=False)
        tag = "synthetic"
    else:
        if not a.dataset:
            sys.exit("give --dataset N [M ...] or --synthetic")
        scns, names_, real, k = [], [], True, 0
        for dsid in a.dataset:
            d, wins = load_windows(dsid, a.window, a.min_aircraft)
            real = real and bool(d["is_real"])
            skipped, used = 0, 0
            for w in wins:
                k += 1
                try:
                    scns.append(from_tracks(w, {}, 1000 + k))
                    used += 1
                except ValueError:          # window too sparse (fewer than 2 aircraft with 8+ airborne reports)
                    skipped += 1
            names_.append(f"{d['name']} ({used} windows)")
            if skipped:
                print(f"dataset {dsid}: skipped {skipped} sparse window(s)", file=sys.stderr)
        meta = dict(ids=a.dataset, name=" + ".join(names_), is_real=real, windows=len(scns), window_min=a.window)
        tag = "_".join(str(x) for x in a.dataset)
    if len(scns) < 2:
        sys.exit("need at least 2 windows")
    meta.update(study="dtc", hold=a.hold, pareto=a.pareto, engine="engine2 (party-line overhearing, buffered decoding)")
    names = [n for n in NAMES if not (a.no_dtc and n == "dtc")]
    for h in a.pareto:
        nm = f"tiered_h{h:g}"
        coding.SCHEMES[nm] = schedulers4.make_batched(coding.SCHEMES["coded_best"], hold=h)
        names.append(nm)
    ch = dict(engine2.CH2_DEFAULTS, loss=a.loss, het=a.het, overhear=a.overhear, buffer=a.buffer)
    R = {n: [] for n in names}
    P95 = {n: [] for n in names}
    t0 = time.time()
    for i, scn in enumerate(scns):
        if not scn.clearances:
            continue
        for n in names:
            L = engine2.simulate(n, scn, ch, 1000 + i)
            R[n].append(metrics(L, ch))
            P95[n].append(L["p95_latency"])
        print(f"  window {i + 1}/{len(scns)} done ({time.time() - t0:.0f} s)", file=sys.stderr)
    n_w = len(R[names[0]])
    print(f"\n{meta['name']}  real={meta['is_real']}  {n_w} windows  loss={a.loss} het={a.het} "
          f"overhear={a.overhear} buffer={a.buffer} hold={a.hold}\n")
    print(f"{'scheme':16}{'tx':>9}{'miss strict %':>16}{'miss excl.withdrawn %':>24}{'mean lat s':>13}{'p95 lat s':>12}")
    out = {"meta": meta, "channel": ch, "n": n_w, "schemes": {}, "paired": {}}
    for n in names:
        r = R[n]
        mm = {k: E.ci95([x[k] for x in r if x[k] is not None]) for k in ("n_tx", "miss_sched", "miss_excl", "mean_lat")}
        mm["p95_lat"] = E.ci95([x for x in P95[n] if x is not None])
        out["schemes"][n] = mm
        print(f"{n:16}{mm['n_tx'][0]:9.1f}{100 * mm['miss_sched'][0]:11.1f}±{100 * mm['miss_sched'][1]:<4.1f}"
              f"{100 * mm['miss_excl'][0]:15.1f}±{100 * mm['miss_excl'][1]:<4.1f}{mm['mean_lat'][0]:13.1f}{mm['p95_lat'][0]:12.1f}")

    def cmp(a_, b_):
        if a_ not in R or b_ not in R:
            return
        tx = E.ci95([100 * (y["n_tx"] - x["n_tx"]) / y["n_tx"] for x, y in zip(R[a_], R[b_]) if y["n_tx"]])
        ms = E.ci95([100 * (y["miss_sched"] - x["miss_sched"]) for x, y in zip(R[a_], R[b_])])
        me = E.ci95([100 * (y["miss_excl"] - x["miss_excl"]) for x, y in zip(R[a_], R[b_])])
        la = E.ci95([y["mean_lat"] - x["mean_lat"] for x, y in zip(R[a_], R[b_]) if x["mean_lat"] is not None and y["mean_lat"] is not None])
        out["paired"][f"{a_}_vs_{b_}"] = dict(tx_saving_pct=tx, miss_strict_pts=ms, miss_excl_pts=me, latency_gain_s=la)
        f = lambda v: f"{v[0]:+6.2f}±{v[1]:<5.2f}{'*' if v[0] - v[1] > 0 else ('-' if v[0] + v[1] < 0 else ' ')}"
        print(f"{a_ + ' vs ' + b_:34}{f(tx)} {f(ms)} {f(me)} {f(la)}")
    print("\npaired differences (positive = first scheme better; * = significantly better, - = significantly worse)")
    print(f"{'':34}{'tx saving %':>14} {'miss strict pts':>15} {'miss excl pts':>14} {'latency gain s':>15}")
    print("-- HEADLINE: proposed (tiered) vs the baselines as they would normally be run")
    cmp("tiered", "broadcast_best"); cmp("tiered", "idnc_hd"); cmp("tiered", "idnc_best")
    print("-- does batching itself help? (same scheme, batched vs immediate)")
    cmp("bcast_tiered", "broadcast_best"); cmp("idnc_tiered", "idnc_best"); cmp("tiered", "coded_best")
    print("-- with batching, how much does coding add? and which coder?")
    cmp("tiered", "bcast_tiered"); cmp("idnc_tiered", "bcast_tiered"); cmp("tiered", "idnc_tiered")
    print("-- can delay-tolerant (stored) repair packets add more?")
    cmp("dtc", "tiered"); cmp("dtc", "idnc_tiered")
    print("-- trade-off: proposed scheme at other hold times vs immediate repair (coded_best)")
    for h in a.pareto:
        cmp(f"tiered_h{h:g}", "coded_best")
    cmp("tiered", "coded_best")
    p = os.path.join(HERE, "data", f"dtc_dataset{tag}_loss{a.loss:g}_het{a.het:g}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("\nsaved", p)


if __name__ == "__main__":
    main()
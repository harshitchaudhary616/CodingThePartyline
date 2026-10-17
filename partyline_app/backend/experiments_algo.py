"""Algorithm study: can a deadline-aware coder beat published-style IDNC?

Schemes (all paired on the same windows, same random seeds):
  broadcast / idnc / coded        the earlier versions (late pairs keep top priority)
  broadcast_hd / idnc_hd / coded_hd   same schemes with the hard-deadline rule: a pair that can no longer be on
                                  time gets a tiny weight and packets are seeded from the most urgent pair that
                                  is still feasible. The *_hd group is the FAIR comparison.
  broadcast_best / idnc_best / coded_best   max-weight versions (broadcast_best is the fair uncoded baseline); *_hd coders that build a packet around each of the 8 most urgent seeds and send the
                                  max-weight one (urgent-first whenever a feasible pair has < 15 s left)
  idnc_bestlazyH / coded_bestlazyH   the *_best coders + bounded holding of lone transmissions for up to H seconds
Metrics per window: transmissions, missed schedulable pairs (strict: pairs withdrawn by a newer clearance
count as missed), the same excluding withdrawn pairs, and mean delivery latency.
Several datasets can be pooled (windows from each are treated as independent samples).
Windows with fewer than 2 aircraft having 8+ airborne reports are skipped.

  python3 experiments_algo.py --dataset 4 5 --window 5 --holds 8 --loss 0.1
  python3 experiments_algo.py --synthetic            (quick self-test)
Writes data/algo_dataset<ids>_loss<loss>.json
"""
import argparse, json, os, sys
import numpy as np
import schedulers2, schedulers3          # noqa: F401
import experiments2 as E
from partyline import coding, engine
from partyline.engine import from_tracks, make_synthetic, CH_DEFAULTS

HERE = os.path.dirname(os.path.abspath(__file__))


def metrics(L, ch, min_slack=5.0):
    m = E.pair_metrics(L, ch, min_slack)
    floor = max(min_slack, 2 * ch["airtime"] / (1 - ch["bg"]))
    S = [p for p in L["pairs"] if p["dl"] - p["tIssue"] >= floor and p["state"] != "superseded"]
    met = lambda p: p["tDone"] is not None and p["tDone"] <= p["dl"]
    m["miss_excl"] = 1 - sum(map(met, S)) / len(S) if S else 0.0
    return m


def load_windows(dsid, window_min, min_aircraft):
    from db import DB
    db = DB(os.environ.get("PL_DB", os.path.join(HERE, "data", "partyline.db")))
    d = db.dataset(dsid)
    if not d:
        sys.exit(f"dataset {dsid} not found")
    rows = db.tracks(dsid)
    ts = np.array([r[0] for r in rows], float)
    t0, t1, W = ts.min(), ts.max(), window_min * 60.0
    wins, t = [], t0
    while t + W <= t1 + 1:
        sub = [r for r in rows if t <= r[0] < t + W]
        if len({r[1] for r in sub}) >= min_aircraft:
            wins.append(sub)
        t += W
    return d, wins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int, nargs="*")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--loss", type=float, default=0.1)
    ap.add_argument("--holds", type=float, nargs="*", default=[8.0, 30.0])
    ap.add_argument("--min-aircraft", type=int, default=8)
    a = ap.parse_args()
    if a.synthetic:
        scns = [make_synthetic(dict(rate=3.0, dur_min=8), s) for s in range(1, 7)]
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
    names = ["broadcast", "idnc", "coded", "broadcast_hd", "idnc_hd", "coded_hd", "broadcast_best", "idnc_best", "coded_best"]
    for h in a.holds:
        hs = f"{h:g}"
        coding.SCHEMES[f"idnc_bestlazy{hs}"] = schedulers3.make("idnc", lazy=True, best=True, hold=h)
        coding.SCHEMES[f"coded_bestlazy{hs}"] = schedulers3.make("coded", lazy=True, best=True, hold=h)
        names += [f"idnc_bestlazy{hs}", f"coded_bestlazy{hs}"]
    ch = dict(CH_DEFAULTS, loss=a.loss)
    R = {n: [] for n in names}
    for i, scn in enumerate(scns):
        if not scn.clearances:
            continue
        for n in names:
            R[n].append(metrics(engine.simulate(n, scn, ch, 1000 + i), ch))
    n_w = len(R["coded"])
    print(f"{meta['name']}  real={meta['is_real']}  {n_w} windows  loss={a.loss}\n")
    print(f"{'scheme':16}{'tx':>9}{'miss strict %':>16}{'miss excl.withdrawn %':>24}{'mean lat s':>13}")
    out = {"meta": meta, "channel": ch, "n": n_w, "schemes": {}, "paired": {}}
    for n in names:
        r = R[n]
        mm = {k: E.ci95([x[k] for x in r if x[k] is not None]) for k in ("n_tx", "miss_sched", "miss_excl", "mean_lat")}
        out["schemes"][n] = mm
        print(f"{n:16}{mm['n_tx'][0]:9.1f}{100 * mm['miss_sched'][0]:11.1f}±{100 * mm['miss_sched'][1]:<4.1f}"
              f"{100 * mm['miss_excl'][0]:15.1f}±{100 * mm['miss_excl'][1]:<4.1f}{mm['mean_lat'][0]:13.1f}")

    def cmp(a_, b_):
        tx = E.ci95([100 * (y["n_tx"] - x["n_tx"]) / y["n_tx"] for x, y in zip(R[a_], R[b_]) if y["n_tx"]])
        ms = E.ci95([100 * (y["miss_sched"] - x["miss_sched"]) for x, y in zip(R[a_], R[b_])])
        me = E.ci95([100 * (y["miss_excl"] - x["miss_excl"]) for x, y in zip(R[a_], R[b_])])
        la = E.ci95([y["mean_lat"] - x["mean_lat"] for x, y in zip(R[a_], R[b_]) if x["mean_lat"] is not None and y["mean_lat"] is not None])
        out["paired"][f"{a_}_vs_{b_}"] = dict(tx_saving_pct=tx, miss_strict_pts=ms, miss_excl_pts=me, latency_gain_s=la)
        f = lambda v: f"{v[0]:+6.2f}±{v[1]:<5.2f}{'*' if v[0] - v[1] > 0 else ' '}"
        print(f"{a_ + ' vs ' + b_:34}{f(tx)} {f(ms)} {f(me)} {f(la)}")
    print("\npaired differences (positive = first scheme better; * = interval excludes zero)")
    print(f"{'':34}{'tx saving %':>14} {'miss strict pts':>15} {'miss excl pts':>14} {'latency gain s':>15}")
    print("-- is the hard-deadline rule itself worth it? (earlier vs _hd of the same scheme)")
    cmp("broadcast_hd", "broadcast"); cmp("idnc_hd", "idnc"); cmp("coded_hd", "coded")
    print("-- FAIR comparisons (all _hd)")
    cmp("coded_hd", "idnc_hd"); cmp("coded_hd", "broadcast_hd"); cmp("idnc_hd", "broadcast_hd")
    print("-- multi-seed max-weight packets (same idea given to BOTH coders)")
    cmp("idnc_best", "idnc_hd"); cmp("coded_best", "coded_hd")
    print("-- FAIR comparisons (all _best): is our coder better than IDNC when both use the improvement?")
    cmp("coded_best", "idnc_best"); cmp("coded_best", "broadcast_best"); cmp("idnc_best", "broadcast_best")
    cmp("coded_best", "idnc_hd"); cmp("coded_best", "broadcast_hd")
    for h in a.holds:
        hs = f"{h:g}"
        print(f"-- bounded holding {hs} s on top of _best (latency/efficiency trade-off)")
        cmp(f"coded_bestlazy{hs}", f"idnc_bestlazy{hs}"); cmp(f"coded_bestlazy{hs}", "idnc_best"); cmp(f"coded_bestlazy{hs}", "coded_best")
    p = os.path.join(HERE, "data", f"algo_dataset{tag}_loss{a.loss:g}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("\nsaved", p)


if __name__ == "__main__":
    main()
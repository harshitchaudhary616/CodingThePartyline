"""Fair evaluation for Party Line Lab.

Compares unicast, broadcast, idnc (published-style) and coded (ours) over many seeds, reports
(a) all pairs and (b) only schedulable pairs, paired differences with 95% confidence intervals
(Student t, correct for small samples), and an optimality census (how often an exact linear code
would beat our greedy coder).

  python3 experiments2.py --synthetic
  python3 experiments2.py --dataset 3
  python3 experiments2.py --dataset 3 --loss 0.2 --seeds 20
Writes data/exp_<label>.json
"""
import argparse, json, math, os, sys, time
import numpy as np
import schedulers2  # noqa: F401  (registers 'idnc')
from partyline import coding, engine
from partyline.engine import make_synthetic, from_tracks, CH_DEFAULTS

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMES = ("unicast", "broadcast", "idnc", "coded")

# two-sided 95% Student t critical values by degrees of freedom
_T = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
      11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
      20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
      29: 2.045, 30: 2.042}


def tcrit(df):
    if df in _T:
        return _T[df]
    if df <= 40:
        return 2.021
    if df <= 60:
        return 2.000
    if df <= 120:
        return 1.980
    return 1.960


def ci95(a):
    a = np.asarray(a, float)
    if len(a) < 2:
        return float(a.mean()) if len(a) else 0.0, 0.0
    return float(a.mean()), float(tcrit(len(a) - 1) * a.std(ddof=1) / math.sqrt(len(a)))


def pair_metrics(L, ch, min_slack):
    floor = max(min_slack, 2 * ch["airtime"] / (1 - ch["bg"]))
    P = L["pairs"]
    sched = [p for p in P if p["dl"] - p["tIssue"] >= floor]

    def met(p):
        return p["tDone"] is not None and p["tDone"] <= p["dl"]
    return dict(n_tx=L["n_tx"], n_pairs=len(P), n_sched=len(sched),
                miss_all=1 - sum(map(met, P)) / len(P) if P else 0.0,
                miss_sched=1 - sum(map(met, sched)) / len(sched) if sched else 0.0,
                p95=L["p95_latency"], mean_lat=L["mean_latency"])


def census(scn, ch, seed, samples=150, nmax=4):
    """At sampled decision points, compare greedy coder to the exact optimum on the nmax most urgent messages."""
    base = coding.SCHEMES["coded"]
    snaps = []

    def wrapped(pending, known, now):
        if len(pending) >= 2 and len(snaps) < 4000:
            order = sorted(pending, key=lambda m: min(pending[m].values()))[:nmax]
            dem = [(m, r) for m in order for r in pending[m]]
            kn = {r: {x for x in known[r] if x in order} for _, r in dem}
            snaps.append((order, dem, kn))
        return base(pending, known, now)
    key = "__census"
    coding.SCHEMES[key] = wrapped
    try:
        engine.simulate(key, scn, ch, seed)
    finally:
        coding.SCHEMES.pop(key, None)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(snaps))[:samples]
    n = gt = opp = 0
    sav = []
    for i in idx:
        order, dem, kn = snaps[i]
        if len(dem) > 14:
            continue
        g = coding.greedy_static_length(order, dem, kn)
        e = coding.exact_gf2_length(order, dem, kn)
        n += 1
        if e < len(order):
            opp += 1
        if e < g:
            gt += 1
            sav.append((g - e) / g)
    return dict(snapshots=len(snaps), sampled=n, coding_possible=opp, greedy_suboptimal=gt,
                mean_saving_when_suboptimal=float(np.mean(sav)) if sav else 0.0)


def evaluate(make_scn, ch, seeds, min_slack=5.0, do_census=True):
    rows = {s: [] for s in SCHEMES}
    cens = []
    for sd in seeds:
        scn = make_scn(sd)
        if not scn.clearances:
            continue
        for s in SCHEMES:
            rows[s].append(pair_metrics(engine.simulate(s, scn, ch, 1000 + sd), ch, min_slack))
        if do_census:
            cens.append(census(scn, ch, 2000 + sd))
    n = len(rows["coded"])
    out = dict(n_seeds=n, channel=ch, min_slack=min_slack, schemes={}, paired={})
    for s in SCHEMES:
        r = rows[s]
        out["schemes"][s] = {k: ci95([x[k] for x in r if x[k] is not None]) for k in
                             ("n_tx", "miss_all", "miss_sched", "p95", "mean_lat", "n_pairs", "n_sched")}

    def saving(a, b):  # % fewer transmissions of a vs b
        return ci95([100 * (rb["n_tx"] - ra["n_tx"]) / rb["n_tx"] for ra, rb in zip(rows[a], rows[b]) if rb["n_tx"]])

    def dmiss(a, b):   # points: miss(b) - miss(a) on schedulable pairs, positive = a better
        return ci95([100 * (rb["miss_sched"] - ra["miss_sched"]) for ra, rb in zip(rows[a], rows[b])])
    for a, b in (("coded", "broadcast"), ("idnc", "broadcast"), ("coded", "idnc"), ("broadcast", "unicast")):
        out["paired"][f"{a}_vs_{b}"] = dict(tx_saving_pct=saving(a, b), miss_sched_improvement_pts=dmiss(a, b))
    if cens:
        tot = {k: sum(c[k] for c in cens) for k in ("snapshots", "sampled", "coding_possible", "greedy_suboptimal")}
        tot["mean_saving_when_suboptimal"] = float(np.mean([c["mean_saving_when_suboptimal"] for c in cens if c["greedy_suboptimal"]] or [0]))
        out["census"] = tot
    return out


def show(label, o):
    print(f"\n=== {label}  ({o['n_seeds']} seeds, loss={o['channel']['loss']}, bg={o['channel']['bg']}) ===")
    print(f"{'scheme':10s} {'tx':>14s} {'miss(all)':>16s} {'miss(schedulable)':>20s}")
    for s in SCHEMES:
        r = o["schemes"][s]
        print(f"{s:10s} {r['n_tx'][0]:8.0f}±{r['n_tx'][1]:<5.0f} {100*r['miss_all'][0]:7.1f}±{100*r['miss_all'][1]:<5.1f}% {100*r['miss_sched'][0]:9.1f}±{100*r['miss_sched'][1]:<5.1f}%")
    sch = o["schemes"]["coded"]
    print(f"pairs per run: {sch['n_pairs'][0]:.0f}, of which schedulable: {sch['n_sched'][0]:.0f}")
    for k, v in o["paired"].items():
        print(f"{k:22s} fewer tx: {v['tx_saving_pct'][0]:6.2f} ± {v['tx_saving_pct'][1]:.2f} %   schedulable-miss improvement: {v['miss_sched_improvement_pts'][0]:6.2f} ± {v['miss_sched_improvement_pts'][1]:.2f} pts")
    if "census" in o:
        c = o["census"]
        print(f"census: {c['sampled']} sampled decisions; coding possible in {c['coding_possible']}; greedy suboptimal in {c['greedy_suboptimal']} "
              f"(mean saving {100*c['mean_saving_when_suboptimal']:.0f}% when suboptimal)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--loss", type=float, nargs="*", default=[0.05, 0.2])
    ap.add_argument("--rate", type=float, nargs="*", default=[3.0])
    ap.add_argument("--no-census", action="store_true")
    a = ap.parse_args()
    seeds = list(range(1, a.seeds + 1))
    results = {}
    if a.dataset is not None:
        from db import DB
        db = DB(os.environ.get("PL_DB", os.path.join(HERE, "data", "partyline.db")))
        d = db.dataset(a.dataset)
        if not d:
            sys.exit("dataset not found")
        rows = db.tracks(a.dataset)
        label = f"dataset{a.dataset}"
        print(f"dataset {a.dataset}: {d['name']} real={bool(d['is_real'])} rows={len(rows)}")
        for loss in a.loss:
            ch = dict(CH_DEFAULTS, loss=loss)
            o = evaluate(lambda sd: from_tracks(rows, {}, sd), ch, seeds, do_census=not a.no_census)
            o["dataset"] = dict(id=d["id"], name=d["name"], is_real=bool(d["is_real"]), rows=len(rows))
            results[f"loss={loss}"] = o; show(f"{d['name']} loss={loss}", o)
    else:
        label = "synthetic"
        for rate in a.rate:
            for loss in a.loss:
                ch = dict(CH_DEFAULTS, loss=loss)
                o = evaluate(lambda sd: make_synthetic({"rate": rate, "dur_min": 20}, sd), ch, seeds, do_census=not a.no_census)
                o["synthetic"] = dict(rate=rate)
                results[f"rate={rate},loss={loss}"] = o; show(f"synthetic rate={rate} loss={loss}", o)
    out = os.path.join(HERE, "data", f"exp_{label}.json")
    json.dump(results, open(out, "w"), indent=1)
    print("\nsaved", out)


if __name__ == "__main__":
    main()
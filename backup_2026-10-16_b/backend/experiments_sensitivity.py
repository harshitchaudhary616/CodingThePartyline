"""Sensitivity of the real-data result to modelling choices (one factor at a time).

Baseline: loss 0.1, background load 0.3, schedulable slack 5 s, max aircraft 90,
conflict radius 8 NM, margin 90 s. Each row changes ONE factor and reports, over independent
time windows, coded vs broadcast and coded vs idnc (mean +- 95% t-interval).

  python3 experiments_sensitivity.py --dataset 4
  python3 experiments_sensitivity.py --dataset 4 --window 5
Writes data/sens_dataset<id>.json
"""
import argparse, json, os, sys, time
import numpy as np
import schedulers2  # noqa: F401
import experiments2 as E
from partyline import engine
from partyline.engine import from_tracks, CH_DEFAULTS
from db import DB

HERE = os.path.dirname(os.path.abspath(__file__))
S3 = ("broadcast", "idnc", "coded")

BASE = dict(loss=0.1, bg=0.3, slack=5.0, max_aircraft=90, r_alert=8.0, margin=90.0)
SWEEPS = [
    ("loss", [0.0, 0.05, 0.1, 0.2, 0.3]),
    ("bg", [0.1, 0.3, 0.5, 0.6]),
    ("slack", [2.0, 5.0, 10.0]),
    ("max_aircraft", [60, 90, 120]),
    ("r_alert", [5.0, 8.0, 12.0]),
    ("margin", [60.0, 90.0, 120.0]),
]


def windows(rows, minutes, min_ac):
    ts = [r[0] for r in rows]
    t0, t1, W = min(ts), max(ts), minutes * 60.0
    out, t = [], t0
    while t + W <= t1 + 1:
        sub = [r for r in rows if t <= r[0] < t + W]
        if len({r[1] for r in sub}) >= min_ac:
            out.append(sub)
        t += W
    return out


def run_cfg(wins, cfg):
    ch = dict(CH_DEFAULTS, loss=cfg["loss"], bg=cfg["bg"])
    params = dict(max_aircraft=int(cfg["max_aircraft"]), r_alert=cfg["r_alert"], margin=cfg["margin"])
    rows = {s: [] for s in S3}
    for i, w in enumerate(wins):
        try:
            scn = from_tracks(w, params, 1 + i)
        except ValueError:
            continue
        if not scn.clearances:
            continue
        for s in S3:
            rows[s].append(E.pair_metrics(engine.simulate(s, scn, ch, 1000 + i), ch, cfg["slack"]))
    n = len(rows["coded"])

    def sv(a, b):
        return E.ci95([100 * (y["n_tx"] - x["n_tx"]) / y["n_tx"] for x, y in zip(rows[a], rows[b]) if y["n_tx"]])

    def dm(a, b):
        return E.ci95([100 * (y["miss_sched"] - x["miss_sched"]) for x, y in zip(rows[a], rows[b])])
    return dict(n=n, pairs=float(np.mean([r["n_pairs"] for r in rows["coded"]])) if n else 0,
                sched=float(np.mean([r["n_sched"] for r in rows["coded"]])) if n else 0,
                broadcast_miss=E.ci95([100 * r["miss_sched"] for r in rows["broadcast"]]),
                coded_miss=E.ci95([100 * r["miss_sched"] for r in rows["coded"]]),
                tx_vs_broadcast=sv("coded", "broadcast"), miss_vs_broadcast=dm("coded", "broadcast"),
                tx_vs_idnc=sv("coded", "idnc"), miss_vs_idnc=dm("coded", "idnc"))


def flag(v):
    return "*" if v[0] - v[1] > 0 else " "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int, required=True)
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--min-aircraft", type=int, default=8)
    a = ap.parse_args()
    db = DB(os.environ.get("PL_DB", os.path.join(HERE, "data", "partyline.db")))
    d = db.dataset(a.dataset)
    if not d:
        sys.exit("dataset not found")
    rows = db.tracks(a.dataset)
    wins = windows(rows, a.window, a.min_aircraft)
    print(f"dataset {a.dataset}: {d['name']} real={bool(d['is_real'])}  {len(wins)} windows of {a.window:g} min")
    print("'*' = interval excludes zero (coded better).  Baseline:", BASE)
    results = {}
    hdr = f"{'factor':13s}{'value':>7s} {'n':>3s} {'bcast miss%':>12s} {'coded miss%':>12s} | {'tx vs bcast %':>16s} {'miss vs bcast pts':>19s} | {'tx vs idnc %':>15s} {'miss vs idnc pts':>18s}"
    print("\n" + hdr)
    t_start = time.time()
    for name, vals in SWEEPS:
        for v in vals:
            cfg = dict(BASE); cfg[name] = v
            r = run_cfg(wins, cfg)
            results[f"{name}={v}"] = dict(cfg=cfg, **r)
            tb, mb, ti, mi = r["tx_vs_broadcast"], r["miss_vs_broadcast"], r["tx_vs_idnc"], r["miss_vs_idnc"]
            print(f"{name:13s}{v:7g} {r['n']:3d} {r['broadcast_miss'][0]:7.1f}±{r['broadcast_miss'][1]:<4.1f} {r['coded_miss'][0]:7.1f}±{r['coded_miss'][1]:<4.1f} | "
                  f"{tb[0]:7.1f}±{tb[1]:<5.1f}{flag(tb)} {mb[0]:9.1f}±{mb[1]:<5.1f}{flag(mb)} | {ti[0]:6.1f}±{ti[1]:<5.1f}{flag(ti)} {mi[0]:8.1f}±{mi[1]:<5.1f}{flag(mi)}", flush=True)
    p = os.path.join(HERE, "data", f"sens_dataset{a.dataset}.json")
    json.dump(dict(base=BASE, window_min=a.window, results=results), open(p, "w"), indent=1)
    print(f"\nsaved {p}  ({time.time() - t_start:.0f}s)")


if __name__ == "__main__":
    main()
"""Richer side information: aircraft overhear each other's clearances on the shared channel.

overhear = probability that a non-addressed aircraft is listening to a given transmission (it still suffers the
same packet loss). A listener stores any message it can decode (rest of the packet already known).
overhear=0 reproduces the earlier results exactly.

  python3 experiments_overhear.py --dataset 4 --window 5
Writes data/oh_dataset<id>.json
"""
import argparse, json, os, sys
import numpy as np
import experiments2 as E
from partyline.engine import from_tracks, CH_DEFAULTS
from db import DB

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int, required=True)
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--loss", type=float, default=0.1)
    ap.add_argument("--levels", type=float, nargs="*", default=[0.0, 0.1, 0.25, 0.5, 0.75])
    ap.add_argument("--min-aircraft", type=int, default=8)
    a = ap.parse_args()
    db = DB(os.environ.get("PL_DB", os.path.join(HERE, "data", "partyline.db")))
    d = db.dataset(a.dataset)
    if not d:
        sys.exit("dataset not found")
    rows = db.tracks(a.dataset)
    ts = np.array([r[0] for r in rows], float)
    t0, t1, W = ts.min(), ts.max(), a.window * 60.0
    wins, t = [], t0
    while t + W <= t1 + 1:
        sub = [r for r in rows if t <= r[0] < t + W]
        if len({r[1] for r in sub}) >= a.min_aircraft:
            wins.append(sub)
        t += W
    print(f"{d['name']} real={bool(d['is_real'])}: {len(wins)} windows of {a.window:g} min, loss={a.loss}")
    if len(wins) < 2:
        sys.exit("need at least 2 usable windows")
    out = {}
    for lv in a.levels:
        ch = dict(CH_DEFAULTS, loss=a.loss, overhear=lv)
        o = E.evaluate(lambda i: from_tracks(wins[i], {}, 1 + i), ch, list(range(len(wins))), do_census=True)
        o["dataset"] = dict(id=d["id"], name=d["name"], is_real=bool(d["is_real"]), rows=len(rows),
                            windows=len(wins), window_min=a.window)
        out[f"overhear={lv}"] = o
        cb, ci = o["paired"]["coded_vs_broadcast"], o["paired"]["coded_vs_idnc"]
        c = o.get("census", {})
        f = lambda v: f"{v[0]:+.1f}±{v[1]:.1f}"
        print(f"overhear={lv:<5} coded vs broadcast: tx {f(cb['tx_saving_pct'])}%  miss {f(cb['miss_sched_improvement_pts'])} pts | "
              f"vs IDNC: tx {f(ci['tx_saving_pct'])}%  miss {f(ci['miss_sched_improvement_pts'])} pts | "
              f"coding possible {c.get('coding_possible', 0)}/{c.get('sampled', 0)}")
    p = os.path.join(HERE, "data", f"oh_dataset{a.dataset}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("saved", p)


if __name__ == "__main__":
    main()
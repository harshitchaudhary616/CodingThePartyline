"""Real-data evaluation over independent time windows of one recorded dataset.

Splits the recording into non-overlapping windows (default 10 minutes), treats each window as one
independent traffic sample (plus clearance-timing seeds inside it), and reports pooled results.

  python3 experiments_windows.py --dataset 3
  python3 experiments_windows.py --dataset 3 --window 10 --seeds-per-window 2 --loss 0.05 0.3
Writes data/expw_dataset<id>.json
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
    ap.add_argument("--window", type=float, default=10.0, help="minutes")
    ap.add_argument("--seeds-per-window", type=int, default=2)
    ap.add_argument("--loss", type=float, nargs="*", default=[0.05, 0.3])
    ap.add_argument("--min-aircraft", type=int, default=8)
    a = ap.parse_args()
    db = DB(os.environ.get("PL_DB", os.path.join(HERE, "data", "partyline.db")))
    d = db.dataset(a.dataset)
    if not d:
        sys.exit("dataset not found")
    rows = db.tracks(a.dataset)
    if not rows:
        sys.exit("dataset has no positions")
    ts = np.array([r[0] for r in rows], float)
    t0, t1 = ts.min(), ts.max()
    W = a.window * 60.0
    wins = []
    t = t0
    while t + W <= t1 + 1:
        sub = [r for r in rows if t <= r[0] < t + W]
        n_ac = len({r[1] for r in sub})
        if n_ac >= a.min_aircraft:
            wins.append((t, sub))
        t += W
    print(f"dataset {a.dataset}: {d['name']} real={bool(d['is_real'])} rows={len(rows)} "
          f"span={(t1 - t0) / 60:.1f} min -> {len(wins)} usable windows of {a.window:g} min (>= {a.min_aircraft} aircraft)")
    if len(wins) < 2:
        sys.exit("need at least 2 usable windows; record a longer or busier dataset")
    idx = list(range(len(wins) * a.seeds_per_window))

    def make(i):
        w = i // a.seeds_per_window
        return from_tracks(wins[w][1], {}, 1 + i)
    out = {}
    for loss in a.loss:
        ch = dict(CH_DEFAULTS, loss=loss)
        o = E.evaluate(make, ch, idx)
        o["dataset"] = dict(id=d["id"], name=d["name"], is_real=bool(d["is_real"]), rows=len(rows),
                            windows=len(wins), window_min=a.window, seeds_per_window=a.seeds_per_window)
        out[f"loss={loss}"] = o
        E.show(f"{d['name']} | {len(wins)} windows | loss={loss}", o)
    p = os.path.join(HERE, "data", f"expw_dataset{a.dataset}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("\nsaved", p)


if __name__ == "__main__":
    main()
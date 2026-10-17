"""Scheduler cost: time per simulated uplink decision for each coder on real windows.
  python3 timing.py 4            (dataset id; uses up to 4 windows, ideal feedback, critical weight 10)
  python3 timing.py --synthetic  (self-test without data)
Reports the mean wall-clock seconds per uplink decision (simulation included, so it is an upper bound on the scheduler cost)."""
import sys, time
import numpy as np
import schedulers2, schedulers3, schedulers4, schedulers5, schedulers6, schedulers7   # noqa: F401
from awareness import with_awareness
from experiments_algo import load_windows
from partyline import engine2
from partyline.engine import from_tracks, make_synthetic

SCH = ["unicast", "idnc_best", "idnc_cls", "stgc", "stgc2", "stgc_ad", "rlnc_sys"]


def main():
    schedulers4.register(hold=30.0)
    schedulers5.register(hold=30.0, crit_w=10.0)
    schedulers6.register()
    schedulers7.register(hold=30.0, crit_w=10.0)
    if "--synthetic" in sys.argv:
        base = [make_synthetic(dict(rate=3, dur_min=8, upd_rate=0.25), s) for s in range(1, 5)]
        name = "synthetic"
    else:
        ds = int(sys.argv[1])
        d, wins = load_windows(ds, 5.0, 8)
        base = []
        for k, w in enumerate(wins[:12]):
            try:
                base.append(from_tracks(w, dict(upd_rate=0.25), 1000 + k + 1))
            except ValueError:
                pass
        base = base[:4]
        name = d["name"]
    scns = [with_awareness(s, A=60.0, sector=60.0) for s in base]
    ch = dict(engine2.CH2_DEFAULTS, loss=0.3)
    print(f"{name}: {len(scns)} windows, {np.mean([len(s.clearances) for s in scns]):.0f} clearances and {np.mean([s.n for s in scns]):.0f} aircraft per window")
    print(f"{'scheme':12}{'uplinks/win':>13}{'ms per uplink':>15}")
    for sc in SCH:
        tt, nt = 0.0, 0
        for i, scn in enumerate(scns):
            t0 = time.time()
            L = engine2.simulate(sc, scn, ch, 1000 + i)
            tt += time.time() - t0; nt += L["n_tx"]
        print(f"{sc:12}{nt / len(scns):13.1f}{1000 * tt / max(1, nt):15.2f}")


if __name__ == "__main__":
    main()
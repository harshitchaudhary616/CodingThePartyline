"""run_future.py with clearances derived from real manoeuvres (maneuver_traffic.py) instead of the random/conflict generators.
  OUT=manout python3 run_maneuver.py --dataset 4 --loss 0.3 --crit-w 10 --reports --fbloss 0.6 --upd-rate 0 --schemes unicast idnc_cls stgc2
Extra flags (before the others): --lead S (default 30), --hdg DEG (20), --spd KT (25), --vr FPM (500).  --upd-rate 0 = manoeuvre-derived clearances only.
Each window record also stores cl_per_min (clearances per aircraft per minute) and man_stats (number of turn / vertical / speed clearances)."""
import os, sys, runpy
import experiments_party as EP
import maneuver_traffic as MT
from partyline.engine import DT

args = sys.argv[1:]
for flag, attr in (("--lead", "LEAD"), ("--hdg", "HDG_MIN"), ("--spd", "SPD_MIN"), ("--vr", "VR_ON")):
    if flag in args:
        i = args.index(flag); setattr(MT, attr, float(args[i + 1])); del args[i:i + 2]
sys.argv = [sys.argv[0]] + args
EP.from_tracks = MT.from_tracks_maneuver
_cm = EP.class_metrics


def class_metrics(L, scn, *a, **k):
    out = _cm(L, scn, *a, **k)
    mins = sum(max(0, scn.last[i] - scn.first[i] + 1) for i in range(scn.n)) * DT / 60.0
    out["cl_per_min"] = len(scn.clearances) / mins if mins > 0 else None
    out["man_stats"] = getattr(scn, "maneuver_stats", None)
    return out


EP.class_metrics = class_metrics
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_future.py"), run_name="__main__")

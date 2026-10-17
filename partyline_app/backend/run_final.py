"""Final extension runner: experiments_party.py plus
   --conflict        clearances generated from predicted conflicts on the real tracks (conflict_traffic.py)
   --nbg N --pp P --slot S    p-persistent CSMA contention (engine2): N competing stations, persistence P, slot S seconds
   idnc_pub (schedulers6) and stgc_ad (schedulers7) registered; believed-gap statistics saved as 'gap' in every window record.
Results go to the folder named by the environment variable OUT (default finalout)/data; existing results are never touched.
  OUT=cfout python3 run_final.py --dataset 4 --loss 0.3 --crit-w 10 --conflict --upd-rate 0 --schemes idnc_cls stgc2
"""
import os, sys
import schedulers6, schedulers7
import experiments_party as EP
from partyline import engine2

here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]


def pop_flag(name, has_value):
    if name not in args:
        return None
    i = args.index(name)
    v = float(args[i + 1]) if has_value else True
    del args[i:i + (2 if has_value else 1)]
    return v


conflict = pop_flag("--conflict", False)
nbg, pp, slot = pop_flag("--nbg", True), pop_flag("--pp", True), pop_flag("--slot", True)
sys.argv = [sys.argv[0]] + args
crit_w = float(args[args.index("--crit-w") + 1]) if "--crit-w" in args else 3.0
hold = float(args[args.index("--hold") + 1]) if "--hold" in args else 30.0

if conflict:
    import conflict_traffic
    EP.from_tracks = conflict_traffic.from_tracks_conflict
for k, v in (("nbg", nbg), ("pp", pp), ("slot", slot)):
    if v is not None:
        engine2.CH2_DEFAULTS[k] = v

_cm = EP.class_metrics


def class_metrics(L, *a, **k):
    out = _cm(L, *a, **k)
    out["gap"] = L.get("gapstat")
    return out


EP.class_metrics = class_metrics
schedulers6.register()
import schedulers5
_r5 = schedulers5.register


def r5b(**kw):
    _r5(**kw)
    schedulers7.register(hold=kw.get("hold", hold), crit_w=kw.get("crit_w", crit_w))


schedulers5.register = r5b
EP.schedulers5.register = r5b
EP.HERE = os.path.join(here, os.environ.get("OUT", "finalout"))
os.makedirs(os.path.join(EP.HERE, "data"), exist_ok=True)
EP.main()
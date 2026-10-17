"""Future-work runner: run_final.py plus
   --fbpolicy N --fbperiod S      sparse reporting (0 = every needy aircraft reports after every uplink; 1 = report only after a state change
                                  or a redundant packet; 2 = the same, at most one report per S seconds, i.e. piggybacked on a periodic downlink)
   --airtime A --access M --bg B  channel profile (airtime of one uplink, mean random access delay, background load)
   stgc_sh registered (schedulers8)
Every window record additionally stores: fbs (reports actually sent), chan_s (airtime + fbs * f_report), gseq (per clearance, the uplink gaps between
its successive transmissions: input of belief_theory.chain_w1), aware_per_min (awareness clearances displayed per aircraft-minute: a workload proxy).
Results go to the folder named by the environment variable OUT (default futout)/data.
  OUT=futfb1 python3 run_future.py --dataset 4 --loss 0.3 --crit-w 10 --reports --fbloss 0.6 --fbpolicy 1 --schemes unicast idnc_cls stgc2
  python3 run_future.py --synthetic --n-syn 6 --crit-w 10 --reports --fbloss 0.6 --schemes idnc_cls stgc2        (self-test, no data needed)"""
import os, sys
import schedulers6, schedulers7, schedulers8
import experiments_party as EP
from partyline import engine2
from partyline.engine import DT
import belief_theory as BT

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
extra = {k: pop_flag("--" + k, True) for k in ("nbg", "pp", "slot", "fbpolicy", "fbperiod", "airtime", "access", "bg")}
sys.argv = [sys.argv[0]] + args
crit_w = float(args[args.index("--crit-w") + 1]) if "--crit-w" in args else 3.0
hold = float(args[args.index("--hold") + 1]) if "--hold" in args else 30.0

if conflict:
    import conflict_traffic
    EP.from_tracks = conflict_traffic.from_tracks_conflict
for k, v in extra.items():
    if v is not None:
        engine2.CH2_DEFAULTS[k] = v

_cm = EP.class_metrics


def class_metrics(L, scn, ch, scheme, f_report, *a, **k):
    out = _cm(L, scn, ch, scheme, f_report, *a, **k)
    tx = L["txs"]
    out["gap"] = L.get("gapstat")
    out["fbs"] = sum(x.get("fbs", 0) for x in tx) if scheme != "unicast" else len(tx)       # unicast: one acknowledgement per uplink
    out["chan_s"] = out["air"] + out["fbs"] * f_report
    out["gseq"] = BT.repeat_seqs(tx)
    mins = sum(max(0, scn.last[i] - scn.first[i] + 1) for i in range(scn.n)) * DT / 60.0
    out["aware_per_min"] = len(scn.aware) / mins if mins > 0 else None
    return out


EP.class_metrics = class_metrics
schedulers6.register()
import schedulers5
_r5 = schedulers5.register


def r5b(**kw):
    _r5(**kw)
    schedulers7.register(hold=kw.get("hold", hold), crit_w=kw.get("crit_w", crit_w))
    schedulers8.register(hold=kw.get("hold", hold), crit_w=kw.get("crit_w", crit_w))


schedulers5.register = r5b
EP.schedulers5.register = r5b
EP.HERE = os.path.join(here, os.environ.get("OUT", "futout"))
os.makedirs(os.path.join(EP.HERE, "data"), exist_ok=True)
EP.main()

"""v10 runs: run_future.py with the guards (schedulers9) and critical-priority STGC2 (schedulers10), plus
  --exact          exact GF(2^8) decoding with the real coefficients (engine2 exact=1)
  --fbair S        every state report occupies the shared channel for S seconds before the next uplink (in-band feedback)
  --supersede N    1 = a new clearance withdraws the previous one to that aircraft (main study); 0 = never; 2 = only one of the same kind
  --causal         relevance classes from constant-velocity projection of the past track (causal_traffic.py); the scheduler uses ONLY these,
                   and every window is ALSO scored end to end against the recorded-future (oracle) classes of the same clearances
Every window record stores, in addition to the earlier metrics (engine2 track=1, scheduling unchanged):
  {crit,aware}_miss_cs        PRIMARY metric. Common demand set, the same for every scheme: all pairs whose slack at issue is at least
                              max(5 s, 2 airtime/(1-bg)) and whose clearance was NOT withdrawn before the pair's deadline. Whether a scheme
                              delivered a pair does not decide whether the pair is counted; a pair withdrawn after its deadline counts.
  {crit,aware}_miss_cs_<th>   the same with other slack thresholds: all (every pair, also slack 0), pos (slack > 0), 1, 2, 5, 10 s
  {crit,aware}_n_cs_<th>      size of those sets
  {crit,aware}_n_zero / _n_short / _miss_short   pairs with slack 0 at issue (the predicted alert minus the margin had already passed),
                              pairs with 0 < slack < threshold, and the miss rate of the latter
  busy_s                      channel time the station occupied: every uplink's service time (access, background) plus in-band reports
  fbs_n / chan_inband         reports sent; uplink airtime + reports x fbair
  causal only: causal_recall / causal_precision, and end to end against the oracle classes:
  {crit,aware}_e2e_miss       oracle pairs (common set, oracle deadlines) not decoded by the aircraft in time, whatever the reason
  crit_e2e_pred / _miss_pred / _miss_unpred / _miss_unpred_aw   share of oracle critical pairs the causal predictor flagged as critical, miss
                              rate among those (delivery failures), among the others (prediction omissions), and among the others that the
                              causal awareness class covered
Results go to the folder named by the environment variable OUT (default v10out)/data.
  OUT=v10base python3 run_v10.py --dataset 4 --crit-w 10 --reports --fbloss 0.6 --loss 0.3 --schemes idnc_cls stgc2 stgc_g2 stgc_cp
  OUT=/tmp/v10syn python3 run_v10.py --synthetic --n-syn 4 --crit-w 10 --reports --fbloss 0.6 --schemes idnc_cls stgc_cp   (self-test)"""
import os, sys, runpy
from partyline import engine2
import v10metrics

args = sys.argv[1:]


def pop(name, has_value):
    if name not in args:
        return None
    i = args.index(name)
    v = float(args[i + 1]) if has_value else True
    del args[i:i + (2 if has_value else 1)]
    return v


if pop("--exact", False):
    engine2.CH2_DEFAULTS["exact"] = 1.0
v = pop("--fbair", True)
if v is not None:
    engine2.CH2_DEFAULTS["fbair"] = v
v = pop("--supersede", True)
if v is not None:
    engine2.CH2_DEFAULTS["supersede"] = v
causal = pop("--causal", False)
sys.argv = [sys.argv[0]] + args
os.environ.setdefault("OUT", "v10out")
v10metrics.install(causal=bool(causal))
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_future.py"), run_name="__main__")
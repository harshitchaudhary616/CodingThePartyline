"""Validation runs for the reviewer checks (run_future.py with the critical-class guards of schedulers9, plus):
  --exact                exact GF(2^8) decoding with the real coefficients (engine2 exact=1) instead of the generic-rank rule
  --fbair S              every state report occupies the shared channel for S seconds before the next uplink (in-band feedback)
  --supersede N          1 = a new clearance withdraws the previous one to that aircraft (default, the paper); 0 = never; 2 = by kind
  --causal               relevance classes from constant-velocity projection of the past track and the current sector only
                         (causal_traffic.py); each window also records recall/precision of the causal critical set against the oracle one
Every window record additionally stores crit_miss_wd / aware_miss_wd: misses excluding only clearances withdrawn BEFORE their deadline
(a pair whose deadline passed before it was withdrawn counts as a miss), and gf_checks / gf_gen_only / gf_exact_only (exact mode:
multi-unknown receptions checked, and how often the generic-rank rule and exact elimination disagreed on innovation).
  OUT=valexact python3 run_valid.py --dataset 4 --crit-w 10 --reports --fbloss 0.6 --exact --schemes idnc_cls stgc2"""
import os, sys, runpy
import numpy as np
import experiments_party as EP
import schedulers5, schedulers9
from partyline import engine2, gf256

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

if causal:
    import causal_traffic as CT
    _ft = EP.from_tracks

    def from_tracks(rows, params, seed):
        ov = CT.overlap(rows, params, seed)
        CT.patch(EP)
        scn = _ft(rows, params, seed)
        scn.overlap = ov
        return scn
    EP.from_tracks = from_tracks
    CT.patch(EP)

_r5 = schedulers5.register


def register(**kw):
    _r5(**kw)
    schedulers9.register(hold=kw.get("hold", 30.0), crit_w=kw.get("crit_w", 3.0))


schedulers5.register = register
EP.schedulers5.register = register

_cm = EP.class_metrics
_last = [0, 0, 0]


def class_metrics(L, scn, ch, scheme, f_report, min_slack=5.0):
    out = _cm(L, scn, ch, scheme, f_report, min_slack)
    floor = max(min_slack, 2 * ch["airtime"] / (1 - ch["bg"]))
    met = lambda p: p["tDone"] is not None and p["tDone"] <= p["dl"]
    for name, S in (("crit", scn.critical), ("aware", scn.aware)):
        P = [p for p in L["pairs"] if (p["m"], p["r"]) in S and p["dl"] - p["tIssue"] >= floor]
        X = [p for p in P if not (p["state"] == "superseded" and p["tEnd"] is not None and p["tEnd"] <= p["dl"])]
        out[f"{name}_miss_wd"] = (1 - sum(map(met, X)) / len(X)) if X else None
        out[f"{name}_infeasible"] = sum(1 for p in L["pairs"] if (p["m"], p["r"]) in S and p["dl"] - p["tIssue"] < floor)
    st = list(gf256.STATS)
    out["gf_checks"], out["gf_gen_only"], out["gf_exact_only"] = (st[i] - _last[i] for i in range(3))
    _last[:] = st
    ov = getattr(scn, "overlap", None)
    if ov:
        out["causal_recall"], out["causal_precision"] = ov["recall"], ov["precision"]
    return out


EP.class_metrics = class_metrics
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_future.py"), run_name="__main__")

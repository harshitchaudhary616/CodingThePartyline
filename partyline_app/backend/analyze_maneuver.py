"""Manoeuvre-derived clearances: STGC2 versus IDNC, pooled over airspaces, plus how the derived clearances look.
  python3 analyze_maneuver.py 4 5 8 9 11 12 13 14        (writes mansummary.txt)"""
import os, sys, json
import numpy as np
from analyze_all import HERE
from analyze_sweep import cell, METRICS

CFG = [("manout", "_cw10_ur0", "default thresholds (lead 30 s, turn 20 deg, speed 25 kt, vertical 500 fpm), ideal feedback"),
       ("manrep", "_rep0.6_cw10_ur0", "default thresholds, 60% of reports lost"),
       ("manlead60", "_rep0.6_cw10_ur0", "lead 60 s, 60% of reports lost"),
       ("manhdg40", "_rep0.6_cw10_ur0", "stricter detection (turn 40 deg, speed 50 kt, vertical 1000 fpm), 60% of reports lost")]


def main():
    ids = sys.argv[1:]
    if not ids:
        sys.exit("usage: python3 analyze_maneuver.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("MANOEUVRE-DERIVED CLEARANCES (clearance times from the observed turns, climbs/descents and speed changes of the real tracks)")
    P("  uplinks: % saved (positive = STGC2 better); misses: points (negative = STGC2 better); [95% two-level block bootstrap]; * STGC2 better, - worse\n")
    for out, sfx, lab in CFG:
        D = {}
        for i in ids:
            p = os.path.join(HERE, out, "data", f"party_dataset{i}_loss0.3_A60{sfx}.json")
            if os.path.exists(p):
                D[i] = json.load(open(p))["per_window"]
        if not D:
            P(f"=== {lab}: (no files yet)"); continue
        W = [w for d in D.values() for w in d.get("stgc2", [])]
        rate = np.mean([w["cl_per_min"] for w in W if w.get("cl_per_min") is not None])
        ms = [w["man_stats"] for w in W if w.get("man_stats")]
        tot = {k: sum(m[k] for m in ms) for k in ("turn", "vertical", "speed")} if ms else {}
        P(f"=== {lab}   [{len(D)} airspaces, {len(W)} windows]")
        P(f"    derived clearances: {rate:.2f} per aircraft per minute (random default 0.25); manoeuvre clearances by type: {tot}")
        P(f"    {'comparison':28}" + "".join(f"{m[1]:>29}" for m in METRICS))
        for name, x, y in (("STGC2 vs class-blind IDNC", "stgc2", "idnc_best"), ("STGC2 vs class-aware IDNC", "stgc2", "idnc_cls")):
            if any(y in d for d in D.values()):
                P(f"    {name:28}" + "".join(f"{cell(D, list(D), x, y, k, rel, rng):>29}" for k, _, rel in METRICS))
        mu = lambda s, k: np.mean([w[k] for d in D.values() for w in d.get(s, []) if w.get(k) is not None]) if any(s in d for d in D.values()) else float("nan")
        P(f"    absolute uplinks per window: " + ", ".join(f"{s} {mu(s, 'n_tx'):.1f}" for s in ("unicast", "idnc_best", "idnc_cls", "stgc2")))
        P()
    P("Caveat: manoeuvres are a proxy for controller instructions (pilot/FMS-initiated changes are included, instructions that change nothing are missed).")
    p = os.path.join(HERE, "mansummary.txt")
    open(p, "w").write("\n".join(lines) + "\n"); print("saved", p)


if __name__ == "__main__":
    main()

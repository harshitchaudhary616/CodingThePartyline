"""Results of run_gap.sh: critical-class guards, relevance filter, VDL Mode 2 nominal profile.
  python3 analyze_gap.py 4 5 8 9 11 12 13 14        (writes gapsummary.txt)
VDL Mode 2 nominal profile (MITRE modelling report, https://mitre.org/sites/default/files/pdf/hung_modeling.pdf): 31.5 kb/s channel, ground-station
p-persistence 0.609 (aircraft 0.05078), inter-access delay TM1 4.5 ms; uplink messages 128 to 3325 bits on average; ~0.15 offered load at 80 aircraft.
Our profile: airtime 0.05 s (a 800-bit message plus 108-bit training sequence is 29 ms at 31.5 kb/s, rounded up for framing and the acknowledgement),
access 0.02 s, background load 0.15, slot 4.5 ms, persistence 0.609, 0.3 competing stations (collision probability 17%). These round-ups are OUR assumptions."""
import os, sys, json
import numpy as np
from analyze_all import HERE
from analyze_sweep import cell, METRICS

IDS = []


def load(folder, loss, sfx):
    D = {}
    for i in IDS:
        p = os.path.join(HERE, folder, "data", f"party_dataset{i}_loss{loss:g}_A60{sfx}.json")
        if os.path.exists(p):
            D[i] = json.load(open(p))["per_window"]
    return D


def mu(D, s, k):
    v = [w[k] for d in D.values() for w in d.get(s, []) if w.get(k) is not None]
    return float(np.mean(v)) if v else float("nan")


def main():
    global IDS
    IDS = sys.argv[1:]
    if not IDS:
        sys.exit("usage: python3 analyze_gap.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    P("1. CRITICAL-CLASS GUARDS (60% of reports lost, weight 10): each coder against class-aware IDNC")
    P("   uplinks: % saved (positive = better than IDNC-cls); misses: points (negative = fewer misses than IDNC-cls); [95% bootstrap]; * better, - worse\n")
    P(f"   {'setting / coder':28}" + "".join(f"{m[1]:>29}" for m in METRICS) + "   crit miss % (excl.)")
    for lab, f, loss, sfx in (("conservative channel", "gapcon", 0.4, "_rep0.6_cw10"), ("severe channel", "gapsev", 0.5, "_rep0.6_cw10"),
                              ("sector 120 NM", "gapsec120", 0.3, "_rep0.6_cw10_sec120"), ("sector 240 NM", "gapsec240", 0.3, "_rep0.6_cw10_sec240")):
        D = load(f, loss, sfx)
        if not D:
            P(f"   {lab}: (no files yet)"); continue
        P(f"   {lab}  [{len(D)} airspaces]   IDNC-cls: critical miss {100 * mu(D, 'idnc_cls', 'crit_miss_excl'):.2f}%, uplinks {mu(D, 'idnc_cls', 'n_tx'):.0f}")
        for s, nm in (("stgc2", "STGC2"), ("stgc_g1", "STGC2 guard 30/40 s"), ("stgc_g2", "STGC2 guard 45/60 s"), ("stgc_fb", "STGC2 with IDNC fallback")):
            if any(s in d for d in D.values()):
                P(f"     {nm:26}" + "".join(f"{cell(D, list(D), s, 'idnc_cls', k, rel, rng):>29}" for k, _, rel in METRICS) + f"   {100 * mu(D, s, 'crit_miss_excl'):.2f}")
    P("\n2. RELEVANCE FILTER: awareness limited to the K nearest aircraft (60% of reports lost, weight 10)")
    P(f"   {'setting':26}{'shown /aircraft/min':>20}" + "".join(f"{m[1]:>29}" for m in METRICS))
    for lab, f, sfx in (("sector 60 NM, K=3", "filtk3", "_rep0.6_cw10"), ("sector 60 NM, K=5", "filtk5", "_rep0.6_cw10"),
                        ("sector 240 NM, K=5", "filt240k5", "_rep0.6_cw10_sec240")):
        D = load(f, 0.3, sfx)
        if D:
            P(f"   {lab:26}{mu(D, 'stgc2', 'aware_per_min'):20.2f}" + "".join(f"{cell(D, list(D), 'stgc2', 'idnc_cls', k, rel, rng):>29}" for k, _, rel in METRICS))
        else:
            P(f"   {lab:26} (no files yet)")
    P("   (unfiltered: 1.09 / 3.73 / 10.26 / 28.75 shown per aircraft per minute for 30 / 60 / 120 / 240 NM sectors)")
    P("\n3. VDL MODE 2 NOMINAL PROFILE (airtime 0.05 s, access 0.02 s, background 0.15, slot 4.5 ms, persistence 0.609, 0.3 competitors; loss 0.3, 60% of reports lost)")
    D = load("vdl2", 0.3, "_rep0.6_cw10")
    if D:
        P(f"   {'comparison':28}" + "".join(f"{m[1]:>29}" for m in METRICS))
        for nm, x, y in (("STGC2 vs class-aware IDNC", "stgc2", "idnc_cls"), ("STGC2 vs unicast", "stgc2", "unicast")):
            P(f"   {nm:28}" + "".join(f"{cell(D, list(D), x, y, k, rel, rng):>29}" for k, _, rel in METRICS))
        P(f"   uplinks per window: unicast {mu(D, 'unicast', 'n_tx'):.0f}, IDNC-cls {mu(D, 'idnc_cls', 'n_tx'):.0f}, STGC2 {mu(D, 'stgc2', 'n_tx'):.0f};  channel time (s): "
          f"unicast {mu(D, 'unicast', 'air'):.1f}, IDNC-cls {mu(D, 'idnc_cls', 'air'):.1f}, STGC2 {mu(D, 'stgc2', 'air'):.1f} (airtime only)")
    else:
        P("   (no files yet)")
    p = os.path.join(HERE, "gapsummary.txt")
    open(p, "w").write("\n".join(lines) + "\n"); print("saved", p)


if __name__ == "__main__":
    main()

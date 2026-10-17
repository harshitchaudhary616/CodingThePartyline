"""Summaries for the future-work experiments (run_future.sh).
  python3 analyze_future.py 4 5 8 9 11 12 13 14        (writes futsummary.txt)
Sections: 1 feedback policies and the report cost at which coding pays; 2 repair-hold trade-off and STGC-SH; 3 belief-staleness model versus
measurement; 4 channel profiles, awareness deadlines, sector size and clearance rate; 5 awareness workload proxy."""
import os, sys, json
import numpy as np
from analyze_all import boot, HERE
from analyze_sweep import cell, METRICS
import belief_theory as BT

IDS = []


def load(folder, i, loss=0.3, A=60, sfx="_rep0.6_cw10"):
    p = os.path.join(HERE, folder, "data", f"party_dataset{i}_loss{loss:g}_A{A:g}{sfx}.json")
    return json.load(open(p))["per_window"] if os.path.exists(p) else None


def loadall(folder, **kw):
    D = {i: load(folder, i, **kw) for i in IDS}
    return {i: d for i, d in D.items() if d}


def mean(D, scheme, key):
    v = [w[key] for d in D.values() for w in d.get(scheme, []) if w.get(key) is not None]
    return float(np.mean(v)) if v else float("nan")


def per_as(D, scheme, key):
    return {i: np.mean([w[key] for w in d[scheme] if w.get(key) is not None]) for i, d in D.items() if scheme in d}


def breakeven(D, a, b):
    """per airspace: channel time of scheme a vs b as a function of the report cost f:  air_a + f fbs_a  vs  air_b + f fbs_b.
    returns (verdict, f*) with verdict 'always' (a cheaper at every f), 'below' (a cheaper when f < f*), 'above' (a cheaper when f > f*), 'never'"""
    Aa, Ab, Fa, Fb = (per_as(D, s, k) for s, k in ((a, "air"), (b, "air"), (a, "fbs"), (b, "fbs")))
    out = {}
    for i in Aa:
        if i in Ab:
            dair, df = Ab[i] - Aa[i], Fa[i] - Fb[i]
            if dair >= 0 and df <= 0:
                out[i] = ("always", float("nan"))
            elif dair > 0 and df > 0:
                out[i] = ("below", dair / df)
            elif dair < 0 and df < 0:
                out[i] = ("above", dair / df)
            else:
                out[i] = ("never", float("nan"))
    return out


def rng_str(d):
    if not d:
        return "n/a"
    kinds = {}
    for v, f in d.values():
        kinds.setdefault(v, []).append(f)
    parts = []
    for v, fs in kinds.items():
        fs = [x for x in fs if np.isfinite(x)]
        rg = f" f* = {np.median(fs) * 1000:.1f} ms (range {min(fs) * 1000:.1f} to {max(fs) * 1000:.1f})" if fs else ""
        parts.append({"always": "cheaper at any report cost", "below": "cheaper while a report costs less than", "above": "cheaper once a report costs more than",
                      "never": "never cheaper"}[v] + rg + f" [{len(kinds[v])} of {len(d)} airspaces]")
    return "; ".join(parts)


def main():
    global IDS
    IDS = sys.argv[1:]
    if not IDS:
        sys.exit("usage: python3 analyze_future.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    # ------------------------------------------------------------ 1 feedback
    P("1. FEEDBACK OVERHEAD (60% of reports lost, loss 0.3, critical weight 10)")
    P("   policy: full = every aircraft with a believed need reports after every uplink; change = only after a state change or a redundant packet;")
    P("           per15 / per30 = change-triggered and at most one report per 15 / 30 s (piggybacked on a periodic downlink)")
    P(f"   {'policy':8}{'scheme':10}{'uplinks':>9}{'reports':>9}{'air s':>8}{'aware miss %':>14}{'crit miss(excl) %':>19}   channel time at report cost 5 / 20 / 50 ms (s)")
    pol = [("full", "futfb0"), ("change", "futfb1"), ("per15", "futfb2"), ("per30", "futfb3")]
    for nm, f in pol:
        D = loadall(f)
        for s in ("unicast", "idnc_cls", "stgc2"):
            if D and any(s in d for d in D.values()):
                air, fb = mean(D, s, "air"), mean(D, s, "fbs")
                P(f"   {nm:8}{s:10}{mean(D, s, 'n_tx'):9.1f}{fb:9.0f}{air:8.0f}{100 * mean(D, s, 'aware_miss_excl'):14.1f}{100 * mean(D, s, 'crit_miss_excl'):19.1f}   "
                  + " / ".join(f"{air + fb * f_:6.0f}" for f_ in (0.005, 0.02, 0.05)))
    P("\n   report cost f* (per report) below which STGC2 uses less channel time than ... (median over airspaces):")
    for nm, f in pol:
        D = loadall(f)
        if D:
            P(f"   {nm:8} STGC2 vs unicast: {rng_str(breakeven(D, 'stgc2', 'unicast'))}\n   {'':8} STGC2 vs class-aware IDNC: {rng_str(breakeven(D, 'stgc2', 'idnc_cls'))}")
    D0, D1 = loadall("futfb0"), loadall("futfb1")
    if D0 and D1:
        M = {i: {"full": D0[i]["stgc2"], "chg": D1[i]["stgc2"]} for i in D0 if i in D1 and "stgc2" in D0[i] and "stgc2" in D1[i]}
        P("   STGC2 with FULL reporting versus change-triggered reporting: full reporting is " + rng_str(breakeven(M, "full", "chg")))
    P("   (aggregation: if k reports share one frame the cost per report falls to f/k; read the table at f/k.)\n")
    # ------------------------------------------------------------ 2 hold
    P("2. REPAIR HOLD AND THE STRICT MISS PENALTY (60% of reports lost)")
    P("   hold trade-off, STGC2 and STGC-SH, Poisson clearances at 0.25/aircraft/min: uplinks, strict critical miss %, critical miss excluding withdrawn pairs %, awareness miss %")
    P(f"   {'hold s':8}{'scheme':10}{'uplinks':>9}{'strict crit %':>15}{'excl crit %':>13}{'aware %':>9}")
    for h, f in ((10, "futh10"), (20, "futh20"), (30, "futfb0")):
        D = loadall(f, sfx="_rep0.6_cw10" + ("" if h == 30 else f"_hold{h}"))
        for s in ("idnc_cls", "stgc2", "stgc_sh"):
            if D and any(s in d for d in D.values()):
                P(f"   {h:<8}{s:10}{mean(D, s, 'n_tx'):9.1f}{100 * mean(D, s, 'crit_miss'):15.2f}{100 * mean(D, s, 'crit_miss_excl'):13.2f}{100 * mean(D, s, 'aware_miss_excl'):9.1f}")
    D = loadall("futcf", sfx="_rep0.6_cw10_ur0")
    if D:
        P("   conflict-driven clearances, hold 30 s:")
        for s in ("idnc_cls", "stgc2", "stgc_sh"):
            if any(s in d for d in D.values()):
                P(f"   {'cf':8}{s:10}{mean(D, s, 'n_tx'):9.1f}{100 * mean(D, s, 'crit_miss'):15.2f}{100 * mean(D, s, 'crit_miss_excl'):13.2f}{100 * mean(D, s, 'aware_miss_excl'):9.1f}")
    D0 = loadall("futfb0")
    if D0:
        P("   STGC-SH versus STGC2 (default hold, Poisson):  " + "".join(f"{lab}: {cell(D0, list(D0), 'stgc_sh', 'stgc2', k, rel, rng)}   " for k, lab, rel in METRICS))
    P("")
    # ------------------------------------------------------------ 3 theory
    P("3. BELIEF-STALENESS MODEL: predicted versus measured waste of single-gap receptions (W1)")
    P(f"   {'config':26}{'scheme':10}{'measured %':>11}{'predicted %':>12}{'abs error pts':>15}   per-airspace error (pts): min / median / max")
    for lab, f, sfx, q, pol_ in (("full reporting, q=0.6", "futfb0", "_rep0.6_cw10", 0.6, 0), ("full reporting, q=0.3", "futfbq3", "_rep0.3_cw10", 0.3, 0),
                                 ("change-triggered, q=0.6", "futfb1", "_rep0.6_cw10", 0.6, 1)):
        D = loadall(f, sfx=sfx)
        for s in ("idnc_cls", "stgc2"):
            if not D or not any(s in d for d in D.values()):
                continue
            errs, mt, pt = [], [], []
            for i, d in D.items():
                if s not in d:
                    continue
                gs, seqs = {}, []
                for w in d[s]:
                    for k, (a, b) in (w.get("gap") or {}).items():
                        z = gs.setdefault(k, [0, 0]); z[0] += a; z[1] += b
                    seqs += w.get("gseq") or []
                m, n = BT.measured_w1(gs)
                if m is None or not seqs:
                    continue
                pr = BT.chain_w1(seqs, 0.3, q, pol_)
                errs.append(100 * abs(pr - m)); mt.append(m); pt.append(pr)
            if errs:
                P(f"   {lab:26}{s:10}{100 * np.mean(mt):11.1f}{100 * np.mean(pt):12.1f}{np.mean(errs):15.1f}   {min(errs):.1f} / {np.median(errs):.1f} / {max(errs):.1f}")
    P("   closed form: expected wasted receptions per pair = (1-p) s/(1-s), s = (1-c)^g  (c = 1-q full reporting, (1-p)(1-q) change-triggered); see belief_theory.py\n")
    # ------------------------------------------------------------ 4 sweeps
    P("4. CHANNEL PROFILES, AWARENESS DEADLINE, SECTOR SIZE, CLEARANCE RATE (60% of reports lost): STGC2 versus class-aware IDNC, pooled over airspaces")
    P("   uplinks: % saved (positive = STGC2 better); misses: points (negative = STGC2 better); [95% two-level block bootstrap]; * STGC2 better, - worse\n")
    P(f"   {'configuration':34}" + "".join(f"{lab:>29}" for _, lab, _ in METRICS) + "   absolute: uplinks IDNC-cls / STGC2")
    cfgs = [("baseline (airtime 0.4 s, access 0.8 s, bg 0.3, loss 0.3)", "futfb0", dict()),
            ("optimistic (0.2 s, 0.4 s, bg 0.2, loss 0.1)", "futchopt", dict(loss=0.1)),
            ("conservative (0.8 s, 1.6 s, bg 0.5, loss 0.4)", "futchcon", dict(loss=0.4)),
            ("severe (1.0 s, 2.4 s, bg 0.6, loss 0.5)", "futchsev", dict(loss=0.5)),
            ("awareness deadline 30 s", "futA30", dict(A=30)), ("awareness deadline 120 s", "futA120", dict(A=120)),
            ("sector 30 NM (fewer per frequency)", "futsec30", dict(sfx="_rep0.6_cw10_sec30")), ("sector 120 NM", "futsec120", dict(sfx="_rep0.6_cw10_sec120")),
            ("sector 240 NM (consolidated)", "futsec240", dict(sfx="_rep0.6_cw10_sec240")),
            ("clearance rate 1.0 / aircraft / min", "futur1", dict(sfx="_rep0.6_cw10_ur1")), ("clearance rate 2.0 / aircraft / min", "futur2", dict(sfx="_rep0.6_cw10_ur2"))]
    for lab, f, kw in cfgs:
        D = loadall(f, **kw)
        if not D:
            P(f"   {lab:34}  (no files yet)")
            continue
        P(f"   {lab:34}" + "".join(f"{cell(D, list(D), 'stgc2', 'idnc_cls', k, rel, rng):>29}" for k, _, rel in METRICS)
          + f"   {mean(D, 'idnc_cls', 'n_tx'):.0f} / {mean(D, 'stgc2', 'n_tx'):.0f}  [{len(D)} airspaces]")
    P("")
    # ------------------------------------------------------------ 5 workload proxy
    P("5. AWARENESS WORKLOAD PROXY (what a pilot would see on the party-line display)")
    for f, sfx, lab in (("futfb0", "_rep0.6_cw10", "sector 60 NM"), ("futsec30", "_rep0.6_cw10_sec30", "sector 30 NM"), ("futsec120", "_rep0.6_cw10_sec120", "sector 120 NM"), ("futsec240", "_rep0.6_cw10_sec240", "sector 240 NM")):
        D = loadall(f, sfx=sfx)
        if D:
            s = "stgc2" if any("stgc2" in d for d in D.values()) else "idnc_cls"
            P(f"   {lab}: {mean(D, s, 'aware_per_min'):.2f} awareness clearances per aircraft per minute shown (default rate 0.25 clearances/aircraft/min), awareness latency {mean(D, s, 'aware_lat'):.1f} s")
    P("   This is a scenario statistic, not a human-factors result: whether pilots benefit from the display needs a user study (protocol in FUTURE_WORK.md).")
    p = os.path.join(HERE, "futsummary.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    print("saved", p)


if __name__ == "__main__":
    main()

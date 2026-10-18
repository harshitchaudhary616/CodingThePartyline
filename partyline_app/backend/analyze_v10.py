"""Results of run_v10.sh.   python3 analyze_v10.py 4 5 8 9 11 12 13 14      (writes v10summary.txt)
Primary metric: misses on the COMMON demand set (crit_miss_cs / aware_miss_cs): pairs with at least max(5 s, two service times) of slack whose
clearance was not withdrawn before the pair's deadline; the set is the same for every scheme. Uplinks: % saved (positive = first scheme better);
misses: points (negative = first scheme better); rates are means over windows. 95% two-level block-bootstrap intervals; * significantly better, - significantly worse.
Non-inferiority (exploratory): one-sided 95% upper bound of (scheme - class-aware IDNC) critical misses, against margins of 1.0 and 0.5 points."""
import os, sys, json
import numpy as np
from analyze_all import HERE
from analyze_sweep import cell

IDS = []
SCH = (("stgc2", "STGC2"), ("stgc_g2", "STGC2 guard 45/60 s"), ("stgc_cp", "STGC2 critical-priority"))
M = [("n_tx", "uplinks saved %", True), ("busy_s", "channel time saved %", True), ("crit_miss_cs", "crit miss pts", False),
     ("aware_miss_cs", "aware miss pts", False)]


def load(folder, loss=0.3, sfx="_rep0.6_cw10"):
    D = {}
    for i in IDS:
        p = os.path.join(HERE, folder, "data", f"party_dataset{i}_loss{loss:g}_A60{sfx}.json")
        if os.path.exists(p):
            D[i] = json.load(open(p))["per_window"]
    return D


def has(D, s):
    return any(s in d for d in D.values())


def mu(D, s, k):
    v = [w[k] for d in D.values() for w in d.get(s, []) if w.get(k) is not None]
    return float(np.mean(v)) if v else float("nan")


def tot(D, s, k):
    return sum(w.get(k) or 0 for d in D.values() for w in d.get(s, []))


def diffs(D, x, y, key):
    d = {}
    for i in D:
        if x in D[i] and y in D[i]:
            a = np.array([np.nan if w.get(key) is None else w[key] for w in D[i][x]], float)
            b = np.array([np.nan if w.get(key) is None else w[key] for w in D[i][y]], float)
            d[i] = 100 * (a - b)
    return d


def upper95(d, rng, B=2000, block=3):
    ks = [k for k in d if len(d[k]) and np.isfinite(d[k]).any()]
    if not ks:
        return float("nan"), float("nan")
    est = float(np.nanmean(np.concatenate([d[k] for k in ks])))
    out = []
    for _ in range(B):
        vals = []
        for j in rng.choice(len(ks), len(ks)):
            x = d[ks[j]]; n = len(x); b = min(block, n); nb = int(np.ceil(n / b))
            st = rng.integers(0, n - b + 1, nb)
            vals.append(np.concatenate([x[s:s + b] for s in st])[:n])
        out.append(np.nanmean(np.concatenate(vals)))
    return est, float(np.percentile(out, 95))


def safe_cell(D, x, y, k, rel, rng):
    ok = all(all(k in w for w in D[i][x] + D[i][y]) for i in D if x in D[i] and y in D[i])
    return cell(D, list(D), x, y, k, rel, rng) if ok else "n/a"


def main():
    global IDS
    IDS = sys.argv[1:]
    if not IDS:
        sys.exit("usage: python3 analyze_v10.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    hdr = lambda k=None: P(f"   {'comparison vs IDNC-cls':34}" + "".join(f"{m[1]:>29}" for m in (k or M)))

    def block(D, schemes=SCH, metrics=None):
        hdr(metrics)
        for s, nm in schemes:
            if has(D, s):
                P(f"   {nm:34}" + "".join(f"{safe_cell(D, s, 'idnc_cls', k, rel, rng):>29}" for k, _, rel in (metrics or M)))

    def rates(D, keys=("crit_miss_cs", "aware_miss_cs")):
        for s in ("unicast", "idnc_cls") + tuple(x for x, _ in SCH):
            if has(D, s):
                P(f"   {s:10} uplinks {mu(D, s, 'n_tx'):6.1f}  channel s {mu(D, s, 'busy_s'):7.1f}  reports {mu(D, s, 'fbs_n'):7.0f}  "
                  + "  ".join(f"{k} {100 * mu(D, s, k):6.2f}%" for k in keys))

    P("v10 RESULTS (60% of reports lost, w = 10). Primary metric: misses on the common demand set (same pairs for every scheme).\n")

    P("1. MAIN STUDY, PRIMARY METRIC")
    B = load("v10base")
    if B:
        P(f"   [{len(B)} airspaces]  critical pairs: {tot(B, 'idnc_cls', 'crit_n_cs_all')} in force at their deadline; {tot(B, 'idnc_cls', 'crit_n_zero')} with zero slack at issue, "
          f"{tot(B, 'idnc_cls', 'crit_n_short')} with 0 < slack < 5 s, {tot(B, 'idnc_cls', 'crit_n_cs')} eligible")
        rates(B)
        block(B)
        P("   earlier definition (undelivered withdrawn pairs dropped, scheme-dependent set) for reference:")
        block(B, metrics=[("crit_miss_excl", "crit miss pts (old)", False), ("aware_miss_excl", "aware miss pts (old)", False)])
    else:
        P("   (no files yet)")

    P("\n2. DEADLINE ELIGIBILITY: critical misses (common set) by minimum slack at issue")
    if B:
        P(f"   {'threshold':12}{'pairs':>9}" + "".join(f"{s:>12}" for s in ("idnc_cls", "stgc2", "stgc_g2", "stgc_cp")) + f"{'STGC2 - IDNC-cls, pts [95% CI]':>36}{'CP - IDNC-cls':>30}")
        for lab, nm in (("all", "every pair"), ("pos", "slack > 0"), ("1", ">= 1 s"), ("2", ">= 2 s"), ("5", ">= 5 s"), ("10", ">= 10 s")):
            k, kn = f"crit_miss_cs_{lab}", f"crit_n_cs_{lab}"
            P(f"   {nm:12}{tot(B, 'idnc_cls', kn):9d}" + "".join(f"{100 * mu(B, s, k):11.2f}%" for s in ("idnc_cls", "stgc2", "stgc_g2", "stgc_cp"))
              + f"{safe_cell(B, 'stgc2', 'idnc_cls', k, False, rng):>36}{safe_cell(B, 'stgc_cp', 'idnc_cls', k, False, rng):>30}")
        P("   short pairs (0 < slack < 5 s): miss rate " + "  ".join(f"{s} {100 * mu(B, s, 'crit_miss_short'):.1f}%" for s in ("idnc_cls", "stgc2", "stgc_g2", "stgc_cp")))
        P("   (zero-slack pairs: the predicted alert minus the 90 s margin had already passed at issue, so the deadline equals the issue time)")

    P("\n3. WITHDRAWAL RULE AND IN-BAND FEEDBACK (primary metric)")
    for lab, f in (("withdrawn by any newer (main)", "v10base"), ("withdrawn by same kind only", "v10sup2"), ("never withdrawn", "v10sup0"), ("reports in band, 20 ms", "v10fb20")):
        D = load(f)
        P(f"   -- {lab}  [{len(D)} airspaces]")
        if D:
            rates(D, ("crit_miss_cs",))
            block(D)

    P("\n4. CAUSAL CLASSES, SCORED END TO END against the recorded-future classes")
    D = load("v10causal")
    if D:
        P(f"   [{len(D)} airspaces]  causal critical set vs oracle: recall {100 * mu(D, 'idnc_cls', 'causal_recall'):.1f}%, precision {100 * mu(D, 'idnc_cls', 'causal_precision'):.1f}%")
        P("   (a) delivery within the predicted classes (what the scheduler was asked to do):")
        block(D)
        P("   (b) end to end: oracle critical / awareness pairs (oracle deadlines, common set) decoded in time, whatever the reason")
        P(f"   {'scheme':12}{'crit e2e miss':>15}{'of which: flagged critical':>28}{'not flagged':>13}{'not flagged, in awareness':>27}{'aware e2e miss':>16}")
        for s in ("idnc_cls", "stgc2", "stgc_g2", "stgc_cp"):
            if has(D, s):
                P(f"   {s:12}{100 * mu(D, s, 'crit_e2e_miss'):14.2f}%{100 * mu(D, s, 'crit_e2e_miss_pred'):27.2f}%{100 * mu(D, s, 'crit_e2e_miss_unpred'):12.2f}%"
                  f"{100 * mu(D, s, 'crit_e2e_miss_unpred_aw'):26.2f}%{100 * mu(D, s, 'aware_e2e_miss'):15.2f}%")
        P(f"   share of oracle critical pairs flagged critical by the predictor: {100 * mu(D, 'idnc_cls', 'crit_e2e_pred'):.1f}%; of the others, share in the causal awareness class: "
          f"{100 * mu(D, 'idnc_cls', 'crit_e2e_unpred_aw'):.1f}%")
        block(D, metrics=[("n_tx", "uplinks saved %", True), ("crit_e2e_miss", "crit e2e miss pts", False), ("aware_e2e_miss", "aware e2e miss pts", False)])
    else:
        P("   (no files yet)")

    P("\n5. COMBINED: exact decoding + in-band reports + same-kind withdrawal + causal classes, scored end to end")
    for lab, f in (("default channel, reports 20 ms", "v10comb"), ("VDL Mode 2 profile, reports 10 ms", "v10combv")):
        D = load(f)
        P(f"   -- {lab}  [{len(D)} airspaces]")
        if not D:
            P("   (no files yet)"); continue
        rates(D, ("crit_miss_cs", "crit_e2e_miss", "aware_e2e_miss"))
        block(D, metrics=[("n_tx", "uplinks saved %", True), ("busy_s", "channel time saved %", True), ("crit_e2e_miss", "crit e2e miss pts", False),
                          ("aware_e2e_miss", "aware e2e miss pts", False)])
        if has(D, "unicast"):
            P(f"   {'IDNC-cls vs unicast':34}" + "".join(f"{safe_cell(D, 'idnc_cls', 'unicast', k, rel, rng):>29}" for k, rel in
                                                    (("n_tx", True), ("busy_s", True), ("crit_e2e_miss", False), ("aware_e2e_miss", False))))
            P(f"   {'STGC2 critical-priority vs unicast':34}" + "".join(f"{safe_cell(D, 'stgc_cp', 'unicast', k, rel, rng):>29}" for k, rel in
                                                                   (("n_tx", True), ("busy_s", True), ("crit_e2e_miss", False), ("aware_e2e_miss", False))))

    P("\n6. HARSH CHANNELS AND LARGE SECTORS (primary metric)")
    for lab, f, loss, sfx in (("conservative channel", "v10con", 0.4, "_rep0.6_cw10"), ("severe channel", "v10sev", 0.5, "_rep0.6_cw10"),
                              ("sector 120 NM", "v10s120", 0.3, "_rep0.6_cw10_sec120"), ("sector 240 NM", "v10s240", 0.3, "_rep0.6_cw10_sec240")):
        D = load(f, loss, sfx)
        P(f"   -- {lab}  [{len(D)} airspaces]")
        if D:
            rates(D, ("crit_miss_cs",))
            block(D)

    P("\n7. NON-INFERIORITY (exploratory) on critical misses, common set: scheme minus class-aware IDNC, one-sided 95% upper bound")
    P(f"   {'configuration':34}{'scheme':10}{'IDNC-cls %':>11}{'diff pts':>10}{'upper':>8}{'<1.0':>6}{'<0.5':>6}")
    CFG = [("main study", "v10base", 0.3, "_rep0.6_cw10", "crit_miss_cs"), ("same-kind withdrawal", "v10sup2", 0.3, "_rep0.6_cw10", "crit_miss_cs"),
           ("never withdrawn", "v10sup0", 0.3, "_rep0.6_cw10", "crit_miss_cs"), ("reports in band 20 ms", "v10fb20", 0.3, "_rep0.6_cw10", "crit_miss_cs"),
           ("causal, end to end", "v10causal", 0.3, "_rep0.6_cw10", "crit_e2e_miss"), ("combined, default, e2e", "v10comb", 0.3, "_rep0.6_cw10", "crit_e2e_miss"),
           ("combined, VDL2, e2e", "v10combv", 0.3, "_rep0.6_cw10", "crit_e2e_miss"), ("conservative channel", "v10con", 0.4, "_rep0.6_cw10", "crit_miss_cs"),
           ("severe channel", "v10sev", 0.5, "_rep0.6_cw10", "crit_miss_cs"), ("sector 120 NM", "v10s120", 0.3, "_rep0.6_cw10_sec120", "crit_miss_cs"),
           ("sector 240 NM", "v10s240", 0.3, "_rep0.6_cw10_sec240", "crit_miss_cs")]
    for lab, f, loss, sfx, key in CFG:
        D = load(f, loss, sfx)
        if not D:
            P(f"   {lab:34}(no files)"); continue
        base = 100 * mu(D, "idnc_cls", key)
        for s, _ in SCH:
            if not has(D, s):
                continue
            e, u = upper95(diffs(D, s, "idnc_cls", key), rng)
            P(f"   {lab:34}{s:10}{base:11.2f}{e:+10.2f}{u:+8.2f}{'yes' if u < 1.0 else 'no':>6}{'yes' if u < 0.5 else 'no':>6}")
    P("\n8. WHERE THE UPLINKS ARE SAVED: uplinks sent before the last critical deadline of the window (later uplinks serve awareness pairs only)")
    for lab, f, loss, sfx in (("main study", "v10base", 0.3, "_rep0.6_cw10"), ("conservative channel", "v10con", 0.4, "_rep0.6_cw10"),
                              ("sector 240 NM", "v10s240", 0.3, "_rep0.6_cw10_sec240")):
        D = load(f, loss, sfx)
        if not D or not has(D, "idnc_cls") or any("n_tx_pre" not in w for d in D.values() for w in d["idnc_cls"]):
            P(f"   -- {lab}: (re-run needed: files from before the diagnostic)"); continue
        P(f"   -- {lab}  [{len(D)} airspaces]   mean last critical deadline {mu(D, 'idnc_cls', 'tcrit'):.0f} s")
        for s_, nm in (("idnc_cls", "IDNC-cls"),) + SCH:
            if has(D, s_):
                P(f"   {nm:26} uplinks total {mu(D, s_, 'n_tx'):6.1f}  before last critical deadline {mu(D, s_, 'n_tx_pre'):6.1f}  after {mu(D, s_, 'n_tx') - mu(D, s_, 'n_tx_pre'):6.1f}")
        P(f"   {'':26}" + "".join(f"{m:>29}" for m in ("uplinks saved % (all)", "uplinks saved % (before)")))
        for s_, nm in SCH:
            if has(D, s_):
                P(f"   {nm:26}" + f"{safe_cell(D, s_, 'idnc_cls', 'n_tx', True, rng):>29}{safe_cell(D, s_, 'idnc_cls', 'n_tx_pre', True, rng):>29}")
    p = os.path.join(HERE, "v10summary.txt")
    open(p, "w").write("\n".join(lines) + "\n"); print("saved", p)


if __name__ == "__main__":
    main()
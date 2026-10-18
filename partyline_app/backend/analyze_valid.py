"""Results of run_valid.sh plus a non-inferiority table over the existing result folders.
  python3 analyze_valid.py 4 5 8 9 11 12 13 14        (writes validsummary.txt)
Non-inferiority: margin DELTA = 1.0 percentage point of critical misses (withdrawn clearances excluded). For each configuration
we report the one-sided 95% upper bound (two-level block bootstrap, the 95th percentile) of STGC2 minus class-aware IDNC; STGC2 is
non-inferior under the model when the bound is below DELTA. This is a statement about simulated deadline delivery, not safety."""
import os, sys, json
import numpy as np
from analyze_all import HERE
from analyze_sweep import cell, METRICS

DELTA = 1.0
IDS = []


def load(folder, loss=0.3, sfx="_rep0.6_cw10"):
    D = {}
    for i in IDS:
        p = os.path.join(HERE, folder, "data", f"party_dataset{i}_loss{loss:g}_A60{sfx}.json")
        if os.path.exists(p):
            D[i] = json.load(open(p))["per_window"]
    return D


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
    ks = [k for k in d if len(d[k])]
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


def row(D, x, y, rng):
    return "".join(f"{cell(D, list(D), x, y, k, rel, rng):>29}" for k, _, rel in METRICS)


def main():
    global IDS
    IDS = sys.argv[1:]
    if not IDS:
        sys.exit("usage: python3 analyze_valid.py 4 5 8 9 11 12 13 14")
    rng = np.random.default_rng(1)
    lines = []
    P = lambda s="": (print(s), lines.append(s))
    hdr = f"   {'comparison':30}" + "".join(f"{m[1]:>29}" for m in METRICS)
    P("ALL: 60% of reports lost, weight 10, loss 0.3. Uplinks: % saved (positive = first scheme better); misses: points (negative = first better)\n")

    P("1. EXACT GF(2^8) DECODING versus the generic-rank rule")
    B, X = load("valbase"), load("valexact")
    if X:
        ck, g, e = (tot(X, s, k) for s in ("stgc2",) for k in ("gf_checks", "gf_gen_only", "gf_exact_only"))
        ck2, g2, e2 = (tot(X, "idnc_cls", k) for k in ("gf_checks", "gf_gen_only", "gf_exact_only"))
        P(f"   receptions checked (multi-unknown): STGC2 {ck}, IDNC-cls {ck2}; generic rule says innovative but exact does not: {g} / {g2}; reverse: {e} / {e2}")
        for s in ("idnc_cls", "stgc2"):
            P(f"   {s:9} uplinks generic {mu(B, s, 'n_tx'):.1f} exact {mu(X, s, 'n_tx'):.1f};  crit miss (excl.) % {100 * mu(B, s, 'crit_miss_excl'):.2f} / {100 * mu(X, s, 'crit_miss_excl'):.2f};"
              f"  aware miss % {100 * mu(B, s, 'aware_miss_excl'):.2f} / {100 * mu(X, s, 'aware_miss_excl'):.2f}")
        P(hdr); P(f"   {'STGC2 vs IDNC-cls, generic':30}" + row(B, "stgc2", "idnc_cls", rng)); P(f"   {'STGC2 vs IDNC-cls, exact':30}" + row(X, "stgc2", "idnc_cls", rng))
    else:
        P("   (no files yet)")

    P("\n2. IN-BAND FEEDBACK: each report occupies the channel before the next uplink")
    P(hdr)
    for lab, f in (("reports 5 ms", "valfb5"), ("reports 20 ms", "valfb20"), ("VDL2 profile, reports 10 ms", "valvdl2fb")):
        D = load(f)
        if not D:
            P(f"   {lab}: (no files yet)"); continue
        P(f"   {lab}  [{len(D)} airspaces]  uplinks unicast/IDNC-cls/STGC2 {mu(D, 'unicast', 'n_tx'):.0f}/{mu(D, 'idnc_cls', 'n_tx'):.0f}/{mu(D, 'stgc2', 'n_tx'):.0f}; reports sent "
          f"{mu(D, 'unicast', 'fbs'):.0f}/{mu(D, 'idnc_cls', 'fbs'):.0f}/{mu(D, 'stgc2', 'fbs'):.0f}; crit miss (excl.) % {100 * mu(D, 'unicast', 'crit_miss_excl'):.1f}/"
          f"{100 * mu(D, 'idnc_cls', 'crit_miss_excl'):.2f}/{100 * mu(D, 'stgc2', 'crit_miss_excl'):.2f}")
        P(f"     {'STGC2 vs IDNC-cls':28}" + row(D, "stgc2", "idnc_cls", rng))
        P(f"     {'STGC2 vs unicast':28}" + row(D, "stgc2", "unicast", rng))
        P(f"     {'IDNC-cls vs unicast':28}" + row(D, "idnc_cls", "unicast", rng))

    P("\n3. WITHDRAWAL RULE")
    P(hdr)
    for lab, f in (("withdrawn by any newer (paper)", "valbase"), ("never withdrawn", "valsup0"), ("withdrawn by same kind only", "valsup2")):
        D = load(f)
        if not D:
            P(f"   {lab}: (no files yet)"); continue
        P(f"   {lab}  [{len(D)} airspaces]")
        for s, nm in (("stgc2", "STGC2"), ("stgc_g2", "STGC2 guard 45/60 s")):
            P(f"     {nm + ' vs IDNC-cls':28}" + row(D, s, "idnc_cls", rng))
        b = upper95(diffs(D, "stgc2", "idnc_cls", "crit_miss_wd"), rng)
        P(f"     critical misses excluding only clearances withdrawn before their deadline: STGC2 - IDNC-cls = {b[0]:+.2f} pts (one-sided 95% upper bound {b[1]:+.2f});"
          f"  IDNC-cls {100 * mu(D, 'idnc_cls', 'crit_miss_wd'):.2f}%, STGC2 {100 * mu(D, 'stgc2', 'crit_miss_wd'):.2f}%")
    D = load("valbase")
    if D:
        P(f"   critical pairs excluded as infeasible at creation (slack below max(5 s, two service times)): {tot(D, 'stgc2', 'crit_infeasible')} "
          f"of {tot(D, 'stgc2', 'crit_infeasible') + tot(D, 'stgc2', 'crit_n')}")

    P("\n4. CAUSAL RELEVANCE CLASSES (constant-velocity projection of the past track; awareness without look-ahead)")
    D = load("valcausal")
    if D:
        P(f"   causal critical set against the oracle one: recall {100 * mu(D, 'stgc2', 'causal_recall'):.1f}%, precision {100 * mu(D, 'stgc2', 'causal_precision'):.1f}%  [{len(D)} airspaces]")
        P(hdr)
        for s, nm in (("stgc2", "STGC2"), ("stgc_g2", "STGC2 guard 45/60 s")):
            P(f"   {nm + ' vs IDNC-cls':30}" + row(D, s, "idnc_cls", rng))
        P(f"   crit miss (excl.) %: IDNC-cls {100 * mu(D, 'idnc_cls', 'crit_miss_excl'):.2f}, STGC2 {100 * mu(D, 'stgc2', 'crit_miss_excl'):.2f}, guard {100 * mu(D, 'stgc_g2', 'crit_miss_excl'):.2f}")
    else:
        P("   (no files yet)")

    P(f"\n5. NON-INFERIORITY on critical misses (withdrawn excluded), margin {DELTA:.1f} pt: STGC2 (or guard) minus class-aware IDNC")
    P(f"   {'configuration':40}{'coder':10}{'difference':>12}{'95% upper':>11}   verdict")
    CFG = [("main study", "futfb0", 0.3, "_rep0.6_cw10", "stgc2"), ("main study (rerun)", "valbase", 0.3, "_rep0.6_cw10", "stgc2"),
           ("main study, guard", "valbase", 0.3, "_rep0.6_cw10", "stgc_g2"), ("manoeuvre-derived", "manrep", 0.3, "_rep0.6_cw10_ur0", "stgc2"),
           ("conflict-driven", "futcf", 0.3, "_rep0.6_cw10_ur0", "stgc2"), ("sector 30 NM", "futsec30", 0.3, "_rep0.6_cw10_sec30", "stgc2"),
           ("sector 120 NM, guard", "gapsec120", 0.3, "_rep0.6_cw10_sec120", "stgc_g2"), ("sector 240 NM, guard", "gapsec240", 0.3, "_rep0.6_cw10_sec240", "stgc_g2"),
           ("conservative channel", "gapcon", 0.4, "_rep0.6_cw10", "stgc2"), ("severe channel", "gapsev", 0.5, "_rep0.6_cw10", "stgc2"),
           ("never withdrawn", "valsup0", 0.3, "_rep0.6_cw10", "stgc2"), ("causal classes", "valcausal", 0.3, "_rep0.6_cw10", "stgc2"),
           ("exact decoding", "valexact", 0.3, "_rep0.6_cw10", "stgc2")]
    for lab, f, loss, sfx, s in CFG:
        D = load(f, loss, sfx)
        if not D or not any(s in d for d in D.values()):
            P(f"   {lab:40}(no files)"); continue
        e, u = upper95(diffs(D, s, "idnc_cls", "crit_miss_excl"), rng)
        P(f"   {lab:40}{s:10}{e:+12.2f}{u:+11.2f}   {'non-inferior' if u < DELTA else 'not shown'}")
    p = os.path.join(HERE, "validsummary.txt")
    open(p, "w").write("\n".join(lines) + "\n"); print("saved", p)


if __name__ == "__main__":
    main()

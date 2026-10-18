"""Metrics and patches for the v10 runs (see run_v10.py). install(causal=...) patches experiments_party; class_metrics is the wrapper."""
import experiments_party as EP
import schedulers5, schedulers9, schedulers10
import awareness
from partyline import engine2, gf256
from partyline import engine as E


def _install_causal():
    import causal_traffic as CT
    _ft = EP.from_tracks
    _wa_oracle = awareness.with_awareness

    def from_tracks(rows, params, seed):
        b, E.build_clearances = E.build_clearances, CT._orig_build
        try:
            so = _ft(rows, params, seed)                       # recorded-future (oracle) classes, same tracks and clearance times
        finally:
            E.build_clearances = b
        E.build_clearances = CT.build_clearances_causal
        scn = _ft(rows, params, seed)                          # causal classes: what the scheduler sees
        O = {(c.t, c.ac, r) for c in so.clearances for r in c.dem}
        C = {(c.t, c.ac, r) for c in scn.clearances for r in c.dem}
        scn.overlap = dict(recall=len(O & C) / len(O) if O else None, precision=len(O & C) / len(C) if C else None)
        scn.oracle_base = so
        return scn

    def with_awareness(s, **kw):
        s2 = CT.with_awareness_causal(s, **kw)
        if getattr(s, "oracle_base", None) is not None:
            s2.oracle = _wa_oracle(s.oracle_base, **kw)
        return s2
    EP.from_tracks = from_tracks
    E.build_clearances = CT.build_clearances_causal
    EP.with_awareness = with_awareness


_r5 = None


def register(**kw):
    _r5(**kw)
    schedulers9.register(hold=kw.get("hold", 30.0), crit_w=kw.get("crit_w", 3.0))
    schedulers10.register()


_cm = None


def install(causal=False):
    """Patch experiments_party: guards and stgc_cp registered, v10 metrics, causal classes (with oracle scoring) if asked."""
    global _r5, _cm
    engine2.CH2_DEFAULTS["track"] = 1.0
    if causal:
        _install_causal()
    if _r5 is None:
        _r5 = schedulers5.register
        schedulers5.register = register
        EP.schedulers5.register = register
    if _cm is None:
        _cm = EP.class_metrics
        EP.class_metrics = class_metrics


_last = [0, 0, 0]
TH = (("all", None), ("pos", 0.0), ("1", 1.0), ("2", 2.0), ("5", 5.0), ("10", 10.0))


def _rate(P, met):
    return (1 - sum(map(met, P)) / len(P)) if P else None


def class_metrics(L, scn, ch, scheme, f_report, min_slack=5.0):
    out = _cm(L, scn, ch, scheme, f_report, min_slack)
    floor = max(min_slack, 2 * ch["airtime"] / (1 - ch["bg"]))
    wd, dec = L.get("wd", {}), L.get("dec", {})
    met = lambda p: p["tDone"] is not None and p["tDone"] <= p["dl"]
    inforce = lambda m, dl: not (m in wd and wd[m] <= dl)
    for name, S in (("crit", scn.critical), ("aware", scn.aware)):
        A = [p for p in L["pairs"] if (p["m"], p["r"]) in S and inforce(p["m"], p["dl"])]
        sl = lambda p: p["dl"] - p["tIssue"]
        for lab, th in TH:
            P = [p for p in A if th is None or (sl(p) > 0 if th == 0 else sl(p) >= th)]
            out[f"{name}_miss_cs_{lab}"], out[f"{name}_n_cs_{lab}"] = _rate(P, met), len(P)
        P = [p for p in A if sl(p) >= floor]
        out[f"{name}_miss_cs"], out[f"{name}_n_cs"] = _rate(P, met), len(P)
        Z = [p for p in A if sl(p) <= 0]
        Sh = [p for p in A if 0 < sl(p) < floor]
        out[f"{name}_n_zero"], out[f"{name}_n_short"], out[f"{name}_miss_short"] = len(Z), len(Sh), _rate(Sh, met)
    tx = L["txs"]
    out["busy_s"] = float(sum(x["t1"] - x["t0"] for x in tx))
    dls = [p["dl"] for p in L["pairs"] if (p["m"], p["r"]) in scn.critical]
    tc = max(dls) if dls else 0.0                       # last critical deadline of the window: later uplinks serve awareness pairs only
    out["tcrit"] = tc
    out["n_tx_pre"] = sum(1 for x in tx if x["t0"] < tc)
    out["busy_pre"] = float(sum(x["t1"] - x["t0"] for x in tx if x["t0"] < tc))
    out["fbs_n"] = sum(x.get("fbs", 0) for x in tx) if scheme != "unicast" else len(tx)
    out["chan_inband"] = out["air"] + out["fbs_n"] * ch.get("fbair", 0.0)
    st = list(gf256.STATS)
    out["gf_checks"], out["gf_gen_only"], out["gf_exact_only"] = (st[i] - _last[i] for i in range(3))
    _last[:] = st
    ov = getattr(scn, "overlap", None)
    if ov:
        out["causal_recall"], out["causal_precision"] = ov["recall"], ov["precision"]
    so = getattr(scn, "oracle", None)
    if so is not None:                       # end to end: causal scheduling, scored against the oracle classes
        cid = {(c.t, c.ac): c.cid for c in scn.clearances}
        for name, S in (("crit", so.critical), ("aware", so.aware)):
            rows = []
            for c in so.clearances:
                cc = cid.get((c.t, c.ac))
                if cc is None:
                    continue
                for r, dl in c.dem.items():
                    if (c.cid, r) not in S or dl - c.t < floor or not inforce(cc, dl):
                        continue
                    ok = dec.get((cc, r), float("inf")) <= dl
                    rows.append((ok, (cc, r) in scn.critical, (cc, r) in scn.aware))
            out[f"{name}_e2e_n"] = len(rows)
            out[f"{name}_e2e_miss"] = (1 - sum(x[0] for x in rows) / len(rows)) if rows else None
            if name == "crit":
                pr = [x for x in rows if x[1]]
                un = [x for x in rows if not x[1]]
                ua = [x for x in un if x[2]]
                out["crit_e2e_pred"] = len(pr) / len(rows) if rows else None
                out["crit_e2e_miss_pred"] = (1 - sum(x[0] for x in pr) / len(pr)) if pr else None
                out["crit_e2e_miss_unpred"] = (1 - sum(x[0] for x in un) / len(un)) if un else None
                out["crit_e2e_miss_unpred_aw"] = (1 - sum(x[0] for x in ua) / len(ua)) if ua else None
                out["crit_e2e_unpred_aw"] = len(ua) / len(un) if un else None
    return out
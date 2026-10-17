"""Mechanism tracing for Party Line Lab.

Nothing here changes the coding logic. It calls the SAME scheduler functions as the simulator
(partyline.coding.SCHEMES) and records, for every transmission, what was pending, what each
receiver already knew, what was sent, and who could decode and why (or why not).
"""
import threading
from partyline import coding, engine

SCHEMES = ("unicast", "broadcast", "coded")


def _entry(m, r, dl, ok, T, known_r):
    missing = sorted(set(T) - {m} - set(known_r))
    return dict(m=m, r=r, dl=dl, can=bool(ok), missing=missing,
                have=sorted(set(T) & set(known_r)))


def static_trace(scheme, demands, known, losses=(), service=1.0, t0=0.0, max_steps=40):
    """demands: list of (m, r, deadline). known: {r: [m,...]}. losses: [(step, r), ...] 0-based step."""
    sched = coding.SCHEMES[scheme]
    pending = {}
    for m, r, d in demands:
        pending.setdefault(int(m), {})[int(r)] = float(d)
    parts = sorted({int(r) for _, r, _ in demands} | {int(r) for r in known})
    kn = {r: set(int(x) for x in known.get(r, known.get(str(r), []))) for r in parts}
    lost = {(int(s), int(r)) for s, r in losses}
    done = {}
    t, steps = float(t0), []
    while pending and len(steps) < max_steps:
        T, got = sched(pending, kn, t)
        k = len(steps)
        snap = {r: sorted(kn[r]) for r in parts}
        pend_before = {m: dict(rs) for m, rs in pending.items()}
        t_end = t + service
        ents = []
        for m in sorted(T):
            for r, dl in sorted(pend_before.get(m, {}).items()):
                ok = (m, r) in got
                e = _entry(m, r, dl, ok, T, kn[r])
                e["status"] = "ignored" if (not ok and scheme == "unicast") else ("cannot" if not ok else "decoded")
                if ok and (k, r) in lost:
                    e["status"] = "lost"
                ents.append(e)
        for e in ents:
            if e["status"] == "decoded":
                kn[e["r"]].add(e["m"])
                pending[e["m"]].pop(e["r"], None)
                if not pending[e["m"]]:
                    del pending[e["m"]]
                done[(e["m"], e["r"])] = t_end
        steps.append(dict(step=k, t0=t, t1=t_end, T=sorted(T), known=snap,
                          pending={m: dict(rs) for m, rs in pend_before.items()}, entries=ents))
        t = t_end
        if not got:
            break
    met = sum(1 for m, r, d in demands if done.get((int(m), int(r)), 1e18) <= d)
    n = len(demands)
    return dict(scheme=scheme, steps=steps, n_tx=len(steps), n_pairs=n, met=met,
                miss=(1 - met / n) if n else 0.0,
                unfinished=sum(len(v) for v in pending.values()),
                done={f"{m}:{r}": v for (m, r), v in done.items()})


def all_static(demands, known, losses=(), service=1.0):
    out = {s: static_trace(s, demands, known, losses, service) for s in SCHEMES}
    msgs = sorted({int(m) for m, _, _ in demands})
    bound = None
    if len(msgs) <= 5:
        kk = {int(r): set(int(x) for x in known.get(r, known.get(str(r), []))) for r in
              {int(r) for _, r, _ in demands}}
        dm = [(int(m), int(r)) for m, r, _ in demands]
        try:
            bound = dict(exact_linear_gf2=coding.exact_gf2_length(msgs, dm, kk),
                         mais_lower=coding.lower_bound_mais(dm, kk))
        except Exception:
            bound = None
    out["bound"] = bound
    return out


_uid = 0
_lock = threading.Lock()


def run_trace(scn, ch, seed, limit=24):
    """Re-run the three schemes on a scenario and record the mechanism. Uses the same simulate()."""
    global _uid
    owner = {c.cid: c.ac for c in scn.clearances}
    version = {c.cid: c.version for c in scn.clearances}
    result = {}
    for s in SCHEMES:
        rec = []
        base = coding.SCHEMES[s]

        def wrapped(pending, known, now, _b=base, _rec=rec, _s=s):
            T, got = _b(pending, known, now)
            ents = []
            for m in sorted(T):
                for r, dl in pending.get(m, {}).items():
                    ok = (m, r) in got
                    e = _entry(m, r, dl, ok, T, known[r])
                    e["status"] = "ignored" if (not ok and _s == "unicast") else ("cannot" if not ok else "decoded")
                    ents.append(e)
            _rec.append(dict(t=now, T=sorted(T), q=len(pending), entries=ents))
            return T, got

        with _lock:
            _uid += 1
            key = f"__trace{_uid}"
            coding.SCHEMES[key] = wrapped
        try:
            L = engine.simulate(key, scn, ch, seed)
        finally:
            with _lock:
                coding.SCHEMES.pop(key, None)
        for i, (rc, tx) in enumerate(zip(rec, L["txs"])):
            ok = {(m, r): v for m, r, v in tx["res"]}
            for e in rc["entries"]:
                if e["status"] == "decoded" and ok.get((e["m"], e["r"]), 1) == 0:
                    e["status"] = "lost"
            rc["t1"] = tx["t1"]
        multi = [x for x in rec if len(x["T"]) >= 2]
        gain = [x for x in multi if sum(1 for e in x["entries"] if e["status"] in ("decoded", "lost")) >= 2]
        served = sum(1 for x in rec for e in x["entries"] if e["status"] == "decoded")
        result[s] = dict(n_tx=L["n_tx"], n_pairs=L["n_pairs"], miss=round(L["miss"], 4),
                         n_multi=len(multi), n_effective_coded=len(gain),
                         served_per_tx=round(served / max(1, len(rec)), 3),
                         mean_latency=L["mean_latency"], p95_latency=L["p95_latency"])
        if s == "coded":
            gain.sort(key=lambda x: -len(x["T"]))
            pick = sorted(gain[:limit], key=lambda x: x["t"])
            result["examples"] = [dict(t=x["t"], t1=x["t1"], T=x["T"], q=x["q"], entries=x["entries"]) for x in pick]
    used = {m for ex in result["examples"] for m in ex["T"]}
    result["owner"] = {str(k): owner[k] for k in used if k in owner}
    result["version"] = {str(k): version[k] for k in used if k in version}
    result["ids"] = list(scn.ids)
    return result
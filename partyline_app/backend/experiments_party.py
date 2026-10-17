"""Party-line study: deliver every clearance to its conflict neighbours (critical, hard deadline) AND to every
other aircraft on the same sector frequency (awareness, soft deadline A). engine2 channel (all aircraft in
range hear every uplink, store what they cannot decode yet).

Schemes (same windows, same seeds, same receivers, same channel, same perfect feedback):
    unicast          today's CPDLC: addressed delivery, one (clearance, aircraft) pair per uplink
    broadcast_best   uncoded broadcast with retransmission (max-weight, urgent-first)
    idnc_hd          published-style instantly decodable XOR coding (hard-deadline rule)
    idnc_best        the same with max-weight packets
    coded_best       our instantly decodable XOR coder, immediate repair
    tiered           our coder + deadline-tiered repair batching, XOR only (schedulers4)
    idnc_tiered      IDNC given the same tiered rule (is the gain in the coder or in the policy?)
    broadcast_cls, idnc_cls, coded_cls, tiered_cls, idnc_tiered_cls   the same baselines given stgc's class knowledge
                     (critical pairs x3, urgent-first only for critical pairs): is the gain the coding or the classes?
    stgc2            stgc + weighted-clique (idnc_best style) packet seeds
    stgc             PROPOSED: tiered + random linear (stored, delayed-decoding) repair packets (schedulers5)
Metrics per window: uplinks; state reports a feedback-based scheme needs (every aircraft with a pending
need reports after each uplink); for critical and awareness pairs separately: missed deadlines (strict, and
excluding clearances withdrawn by a newer version) and mean delivery latency.

  python3 experiments_party.py --synthetic
  python3 experiments_party.py --dataset 4 5 8 --loss 0.1
  python3 experiments_party.py --dataset 4 5 8 --loss 0.3
  python3 experiments_party.py --dataset 4 --reports --fbloss 0.6 --upd-rate 0.5 --coll 0.1     (robustness sweeps)
  python3 experiments_party.py --dataset 4 --reports --nack --fbloss 0.3                         (NACK-only feedback)
Writes data/party_dataset<ids>_loss<loss>_A<A>.json
"""
import argparse, json, os, sys, time
import numpy as np
import schedulers2, schedulers3, schedulers4, schedulers5          # noqa: F401  (register schemes)
import experiments2 as E
from awareness import with_awareness
from experiments_algo import load_windows
from partyline import engine2
from partyline.engine import from_tracks, make_synthetic

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = ["unicast", "broadcast_best", "idnc_hd", "idnc_best", "coded_best", "tiered", "idnc_tiered", "rlnc_sys", "rlnc_group",
           "broadcast_cls", "idnc_cls", "coded_cls", "tiered_cls", "idnc_tiered_cls", "stgc", "stgc2", "stgc_noclass", "stgc_hold0"]


def class_metrics(L, scn, ch, scheme, f_report, min_slack=5.0):
    floor = max(min_slack, 2 * ch["airtime"] / (1 - ch["bg"]))
    tx = L["txs"]
    if scheme == "unicast":                     # one acknowledgement per addressed uplink
        fb, fbn = len(tx), sum(1 for x in tx for _, _, ok in x["res"] if not ok)
    else:                                       # every aircraft with a pending need reports after each uplink
        fb, fbn = sum(x["fb"] for x in tx), sum(x["fb_nack"] for x in tx)
    air = sum(ch["airtime"] * (1.0 + ch.get("hdr", 0.0) * (len(x["T"]) - 1)) for x in tx)    # airtime incl. coding headers
    out = dict(n_tx=L["n_tx"], fb=fb, fb_nack=fbn, air=air, deg=float(np.mean([len(x["T"]) for x in tx])) if tx else 0.0,
               chan=air + fb * f_report, chan_nack=air + fbn * f_report)
    rn, rs, rw = (sum(x.get(k, 0) for x in tx) for k in ("rn", "rs", "rw"))
    tot = max(rn + rs + rw, 1)
    out.update(use_now=rn / tot, use_store=rs / tot, use_waste=rw / tot)     # what became of receptions by aircraft that needed something
    met = lambda p: p["tDone"] is not None and p["tDone"] <= p["dl"]
    for name, S in (("crit", scn.critical), ("aware", scn.aware)):
        P = [p for p in L["pairs"] if (p["m"], p["r"]) in S and p["dl"] - p["tIssue"] >= floor]
        X = [p for p in P if p["state"] != "superseded"]
        lat = [p["tDone"] - p["tIssue"] for p in P if p["tDone"] is not None]
        out[f"{name}_n"] = len(P)
        out[f"{name}_miss"] = (1 - sum(map(met, P)) / len(P)) if P else None
        out[f"{name}_miss_excl"] = (1 - sum(map(met, X)) / len(X)) if X else None
        out[f"{name}_lat"] = float(np.mean(lat)) if lat else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=int, nargs="*")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--rate", type=float, default=3.0, help="synthetic arrivals per minute")
    ap.add_argument("--n-syn", type=int, default=8)
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--min-aircraft", type=int, default=8)
    ap.add_argument("--loss", type=float, default=0.3)
    ap.add_argument("--het", type=float, default=0.0)
    ap.add_argument("--A", type=float, default=60.0, help="awareness deadline, s after issue")
    ap.add_argument("--sector", type=float, default=60.0, help="sector size NM (same sector = same frequency); 0 = radius")
    ap.add_argument("--r-aware", type=float, default=40.0, help="awareness radius NM (only with --sector 0)")
    ap.add_argument("--reports", action="store_true", help="realistic feedback: the station only knows what state reports told it")
    ap.add_argument("--fbloss", type=float, default=0.0, help="probability a state report is lost (with --reports)")
    ap.add_argument("--hold", type=float, default=30.0, help="repair hold time of the tiered schemes, s")
    ap.add_argument("--crit-w", type=float, default=3.0, help="weight multiplier of critical pairs (stgc, stgc2 and the *_cls baselines)")
    ap.add_argument("--hdr", type=float, default=0.0, help="coding-header overhead: extra airtime of each additional clearance in a packet, as a fraction of one message")
    ap.add_argument("--f-report", type=float, default=0.05, help="channel time of one feedback report, s")
    ap.add_argument("--max-windows", type=int, default=0, help="use at most this many windows per dataset (evenly spaced); 0 = all")
    ap.add_argument("--upd-rate", type=float, default=0.25, help="clearances per aircraft per minute in the simulated traffic (default 0.25 = earlier results)")
    ap.add_argument("--coll", type=float, default=0.0, help="probability that an uplink collides with a competing transmission and is lost at every receiver")
    ap.add_argument("--nack", action="store_true", help="NACK-only reports (with --reports): silence = delivered, --fbloss is then the NACK loss")
    ap.add_argument("--schemes", nargs="*", default=DEFAULT)
    a = ap.parse_args()
    schedulers4.register(hold=a.hold)
    schedulers5.register(hold=a.hold, crit_w=a.crit_w)
    if a.synthetic:
        base = [make_synthetic(dict(rate=a.rate, dur_min=8, upd_rate=a.upd_rate), s) for s in range(1, a.n_syn + 1)]
        meta = dict(ids=[], name=f"synthetic self-test (rate {a.rate}/min)", is_real=False)
        tag = f"synthetic{a.rate:g}"
    else:
        if not a.dataset:
            sys.exit("give --dataset N [M ...] or --synthetic")
        base, names_, real, k = [], [], True, 0
        for dsid in a.dataset:
            d, wins = load_windows(dsid, a.window, a.min_aircraft)
            real = real and bool(d["is_real"])
            used = 0
            if a.max_windows and len(wins) > a.max_windows:
                wins = [wins[int(i * len(wins) / a.max_windows)] for i in range(a.max_windows)]
            for w in wins:
                k += 1
                try:
                    base.append(from_tracks(w, dict(upd_rate=a.upd_rate), 1000 + k)); used += 1
                except ValueError:
                    pass
            names_.append(f"{d['name']} ({used} windows)")
        meta = dict(ids=a.dataset, name=" + ".join(names_), is_real=real, windows=len(base), window_min=a.window)
        tag = "_".join(str(x) for x in a.dataset)
    scns = [with_awareness(s, A=a.A, sector=a.sector, r_aware=a.r_aware) for s in base]
    scns = [s for s in scns if any(c.dem for c in s.clearances)]
    if len(scns) < 2:
        sys.exit("need at least 2 windows with demand")
    meta.update(study="party", A=a.A, sector=a.sector, r_aware=a.r_aware, hold=a.hold, crit_w=a.crit_w,
                f_report=a.f_report, reports=a.reports, fbloss=a.fbloss, upd_rate=a.upd_rate, coll=a.coll, nack=a.nack, engine="engine2 (party-line overhearing, buffered decoding)")
    ch = dict(engine2.CH2_DEFAULTS, loss=a.loss, het=a.het, hdr=a.hdr, coll=a.coll, fbmode=(2.0 if a.nack else 1.0) if a.reports else 0.0, fbloss=a.fbloss if a.reports else 0.0)
    names = list(a.schemes)
    R = {n: [] for n in names}
    T0 = time.time()
    tim = {n: 0.0 for n in names}
    npairs, nrecv, ncl = [], [], []
    for i, scn in enumerate(scns):
        dem = [len(c.dem) for c in scn.clearances if c.dem]
        npairs.append(sum(dem)); nrecv.append(float(np.mean(dem))); ncl.append(len(dem))
        for n in names:
            t1 = time.time()
            L = engine2.simulate(n, scn, ch, 1000 + i)
            tim[n] += time.time() - t1
            R[n].append(class_metrics(L, scn, ch, n, a.f_report))
        print(f"  window {i + 1}/{len(scns)} done ({time.time() - T0:.0f} s)", file=sys.stderr)
    n_w = len(scns)
    print(f"\n{meta['name']}  real={meta['is_real']}  {n_w} windows  loss={a.loss} het={a.het}  awareness deadline {a.A:g} s, "
          + (f"sector {a.sector:g} NM" if a.sector > 0 else f"radius {a.r_aware:g} NM")
          + f", repair hold {a.hold:g} s")
    if a.reports and a.nack:
        print(f"NACK-ONLY FEEDBACK: silence = delivered; a NACK is lost with prob {a.fbloss:g}; collisions {a.coll:g}; clearance rate {a.upd_rate:g}/aircraft/min")
    elif a.reports:
        print(f"REALISTIC FEEDBACK: the station keeps its own copy of each aircraft's state, updated only by reports; each report lost with prob {a.fbloss:g}")
    print(f"clearances per window {np.mean(ncl):.0f}, receivers per clearance {np.mean(nrecv):.1f}, pairs {np.mean(npairs):.0f}; "
          f"report airtime f={a.f_report:g} s\n")
    print(f"{'scheme':15}{'uplinks':>9}{'reports':>9}{'chan s':>8}{'crit miss %':>13}{'crit excl %':>13}{'aware miss %':>14}{'aware lat s':>12}{'sim s':>7}")
    out = {"meta": meta, "channel": ch, "n": n_w, "schemes": {}, "paired": {}, "per_window": R}

    def ci(n, k, scale=1.0):
        v = [x[k] * scale for x in R[n] if x[k] is not None]
        return E.ci95(v) if v else (float("nan"), 0.0)
    for n in names:
        mm = {k: ci(n, k) for k in ("n_tx", "fb", "fb_nack", "chan", "chan_nack", "crit_miss", "crit_miss_excl",
                                    "aware_miss", "aware_miss_excl", "crit_lat", "aware_lat", "use_now", "use_store", "use_waste", "air", "deg")}
        out["schemes"][n] = mm
        print(f"{n:15}{mm['n_tx'][0]:9.1f}{mm['fb'][0]:9.0f}{mm['chan'][0]:8.0f}"
              f"{100 * mm['crit_miss'][0]:9.1f}±{100 * mm['crit_miss'][1]:<3.1f}{100 * mm['crit_miss_excl'][0]:9.1f}±{100 * mm['crit_miss_excl'][1]:<3.1f}"
              f"{100 * mm['aware_miss_excl'][0]:10.1f}±{100 * mm['aware_miss_excl'][1]:<3.1f}{mm['aware_lat'][0]:12.1f}{tim[n]:7.0f}")

    print("\nwhat became of receptions by aircraft that needed something (higher 'decoded' and lower 'wasted' is better)")
    print(f"{'scheme':15}{'decoded %':>11}{'stored %':>10}{'wasted %':>10}{'clearances/pkt':>16}{'airtime s':>11}")
    for n in names:
        sc = out['schemes'][n]
        print(f"{n:15}{100 * sc['use_now'][0]:11.1f}{100 * sc['use_store'][0]:10.1f}{100 * sc['use_waste'][0]:10.1f}{sc['deg'][0]:16.2f}{sc['air'][0]:11.0f}")

    def cmp(a_, b_):
        if a_ not in R or b_ not in R:
            return
        X, Y = R[a_], R[b_]
        pct = lambda k: E.ci95([100 * (y[k] - x[k]) / y[k] for x, y in zip(X, Y) if y[k]])

        def d(k):
            v = [100 * (y[k] - x[k]) for x, y in zip(X, Y) if x[k] is not None and y[k] is not None]
            return E.ci95(v) if v else (0.0, 0.0)
        tx, ct, cn = pct("n_tx"), pct("chan"), pct("chan_nack")
        cm, am = d("crit_miss_excl"), d("aware_miss_excl")
        out["paired"][f"{a_}_vs_{b_}"] = dict(tx_saving_pct=tx, chan_saving_pct=ct, chan_nack_saving_pct=cn,
                                              crit_miss_excl_pts=cm, aware_miss_excl_pts=am)
        f = lambda v: f"{v[0]:+7.1f}±{v[1]:<5.1f}{'*' if v[0] - v[1] > 0 else ('-' if v[0] + v[1] < 0 else ' ')}"
        print(f"{a_ + ' vs ' + b_:26}{f(tx)} {f(ct)} {f(cn)} {f(cm)} {f(am)}")
    print("\npaired differences (positive = first scheme better; * = significantly better, - = significantly worse)")
    print(f"{'':26}{'uplinks %':>15} {'channel %':>14} {'chan NACK %':>14} {'crit miss pts':>14} {'aware miss pts':>15}")
    print("-- HEADLINE: stgc (tiered repair + random linear repair packets) vs today's CPDLC and the baselines")
    for b in ("unicast", "broadcast_best", "idnc_hd", "idnc_best", "coded_best", "tiered", "idnc_tiered", "rlnc_sys", "rlnc_group"):
        cmp("stgc", b)
    print("-- FAIR: baselines that know the classes too (critical x3, urgent-first only for critical)")
    for b in ("broadcast_cls", "idnc_cls", "coded_cls", "tiered_cls", "idnc_tiered_cls"):
        cmp("stgc", b)
    print("-- what knowing the classes is worth to XOR schemes (positive = class-aware is better)")
    for x, y in (("idnc_cls", "idnc_best"), ("coded_cls", "coded_best"), ("tiered_cls", "tiered")):
        cmp(x, y)
    print("-- stgc2 (weighted-clique seeds) vs the strongest class-aware baselines and stgc")
    for b in ("idnc_cls", "idnc_tiered_cls", "tiered_cls", "stgc", "rlnc_sys"):
        cmp("stgc2", b)
    print("-- ablation: remove one part of stgc (positive = the full scheme is better)")
    for b in ("stgc_noclass", "stgc_hold0"):
        cmp("stgc", b)
    print("-- ablation: tiered (XOR only) vs the baselines; is the gain in the coder or in the policy?")
    for b in ("broadcast_best", "idnc_hd", "idnc_best", "coded_best", "idnc_tiered"):
        cmp("tiered", b)
    sfx = (f"_het{a.het:g}" if a.het > 0 else "") + (f"_r{a.r_aware:g}" if a.sector <= 0 else "") + (f"_nack{a.fbloss:g}" if (a.reports and a.nack) else (f"_rep{a.fbloss:g}" if a.reports else "")) + (f"_cw{a.crit_w:g}" if a.crit_w != 3.0 else "") + (f"_hdr{a.hdr:g}" if a.hdr > 0 else "") + (f"_ur{a.upd_rate:g}" if a.upd_rate != 0.25 else "") + (f"_coll{a.coll:g}" if a.coll > 0 else "") + (f"_hold{a.hold:g}" if a.hold != 30.0 else "") + (f"_sec{a.sector:g}" if a.sector > 0 and a.sector != 60.0 else "")
    p = os.path.join(HERE, "data", f"party_dataset{tag}_loss{a.loss:g}_A{a.A:g}{sfx}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("\nsaved", p)


if __name__ == "__main__":
    main()
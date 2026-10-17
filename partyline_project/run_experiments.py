"""Usage: python3 run_experiments.py [quick]
Writes CSVs + figures to results/. All numbers are SIMULATION on synthetic geometries."""
import sys, csv, itertools
import numpy as np
from partyline.scenario import Params, generate as _gen
_cache={}
def generate(p):
    k=repr(p)
    if k not in _cache: _cache[k]=_gen(p)
    return _cache[k]
from partyline.sim import ChannelParams, run
from partyline.coding import greedy_static_length, exact_gf2_length, lower_bound_mais

quick = len(sys.argv) > 1 and sys.argv[1] == "quick"
SEEDS = range(4 if quick else 20)
SCH = ("unicast", "broadcast", "coded")

def ci(x):
    x = np.array(x, float); x = x[~np.isnan(x)]
    if len(x) < 2: return (float(x.mean()) if len(x) else float('nan'), 0.0)
    return float(x.mean()), float(1.96 * x.std(ddof=1) / np.sqrt(len(x)))

def sweep(name, grid, build):
    rows = []
    for val in grid:
        acc = {s: {k: [] for k in ("tx_per_pair", "n_tx", "miss", "mean_lat", "p95_lat", "n_pairs")} for s in SCH}
        for sd in SEEDS:
            scen, ch = build(val, sd)
            ac, cls = generate(scen)
            for s in SCH:
                r = run(s, ac, cls, ch, scen)
                for k in acc[s]: acc[s][k].append(r[k])
        for s in SCH:
            row = dict(sweep=name, value=val, scheme=s)
            for k, v in acc[s].items():
                m, h = ci(v); row[k] = round(m, 4); row[k + "_ci"] = round(h, 4)
            rows.append(row)
        print(name, val, {s: (round(acc[s]['n_tx'] and np.mean(acc[s]['n_tx']), 1), round(np.mean(acc[s]['miss']), 3)) for s in SCH}, flush=True)
    with open(f"results/{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return rows

def base(sd, **kw):
    return Params(seed=sd, **{k: v for k, v in kw.items() if k in Params.__dataclass_fields__}), \
           ChannelParams(seed=1000 + sd, **{k: v for k, v in kw.items() if k in ChannelParams.__dataclass_fields__})

# ---------------- checkpoint: static snapshots, greedy vs exact vs lower bound
def checkpoint():
    gaps, ratios, n = [], [], 0
    for sd in range(30 if not quick else 8):
        ac, cls = generate(Params(seed=sd, rate_per_min=1.5))
        known = {a.idx: set() for a in ac}
        for c in cls: known[c.ac].add(c.cid)
        for t0 in np.arange(200, 2000, 60):      # snapshot windows: msgs issued in [t0,t0+60)
            win = [c for c in cls if t0 <= c.t_issue < t0 + 60 and c.demanders]
            msgs = [c.cid for c in win]
            if not 2 <= len(msgs) <= 5: continue
            d = [(c.cid, r) for c in win for r in c.demanders]
            kn = {r: {m for m in msgs if m in known[r]} for r in {r for _, r in d}}
            d = [(m, r) for m, r in d if m not in kn[r]]
            if not d: continue
            g = greedy_static_length(msgs, d, kn); e = exact_gf2_length(msgs, d, kn)
            bcast = len({m for m, _ in d})
            gaps.append(g - e); ratios.append((bcast, g, e)); n += 1
    ratios = np.array(ratios)
    print(f"[checkpoint] {n} snapshots; greedy==exact in {np.mean(np.array(gaps)==0):.1%}; "
          f"mean broadcast={ratios[:,0].mean():.2f} greedy={ratios[:,1].mean():.2f} exact={ratios[:,2].mean():.2f}")
    with open("results/checkpoint.txt", "w") as f:
        f.write(f"snapshots={n}\ngreedy_equals_exact={np.mean(np.array(gaps)==0):.4f}\n"
                f"mean_uncoded_broadcast={ratios[:,0].mean():.3f}\nmean_greedy={ratios[:,1].mean():.3f}\nmean_exact_linear={ratios[:,2].mean():.3f}\n")
checkpoint()

sweep("load", [0.5, 1.0, 1.5, 2.0, 3.0], lambda v, sd: base(sd, rate_per_min=v))
sweep("loss", [0.0, 0.05, 0.1, 0.2, 0.3], lambda v, sd: base(sd, rate_per_min=1.5, p_loss=v))
sweep("horizon", [120, 300, 480, 600], lambda v, sd: base(sd, rate_per_min=1.5, horizon_s=v))
sweep("bgload", [0.0, 0.3, 0.5, 0.7], lambda v, sd: base(sd, rate_per_min=1.5, bg_load=v))
sweep("margin", [30, 90, 150], lambda v, sd: base(sd, rate_per_min=1.5, margin_s=v))

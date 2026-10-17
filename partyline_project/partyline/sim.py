"""Event-driven simulation of clearance dissemination over a shared serial VDL-Mode-2-like channel.

Channel model (explicit, parameterised, NOT a full CSMA/MAC simulation):
  service time per transmission = airtime + Exp(mean_access)  , inflated by 1/(1-bg_load)
  (bg_load = share of channel capacity used by other traffic, incl. the initial addressed
   clearance unicast, which is identical for all schemes and excluded from the 'extra' count).
Erasures: each receiver independently misses a transmission with prob p_loss.
Side info: own clearances (delivered by the initial unicast) + every message decoded so far.
"""
from dataclasses import dataclass
import numpy as np
from .scenario import generate, Params
from .coding import SCHEMES


@dataclass
class ChannelParams:
    airtime_s: float = 0.4
    mean_access_s: float = 0.8
    bg_load: float = 0.3
    p_loss: float = 0.05
    seed: int = 1


def run(scheme, ac, clearances, ch: ChannelParams, scen: Params):
    rng = np.random.default_rng(ch.seed)
    sched = SCHEMES[scheme]
    known = {a.idx: set() for a in ac}
    pending = {}                       # msg -> {receiver: deadline}
    stale_by_ac = {}                   # ac -> latest live msg id (newer version supersedes)
    cl = sorted(clearances, key=lambda c: c.t_issue)
    ci, t = 0, 0.0
    n_tx = 0
    pair_info = {}                     # (msg, r) -> (t_issue, deadline, t_done or None)
    msg_owner = {}
    while ci < len(cl) or pending:
        # admit all clearances issued by time t
        while ci < len(cl) and cl[ci].t_issue <= t:
            c = cl[ci]; ci += 1
            known[c.ac].add(c.cid)     # own clearance, via initial unicast
            msg_owner[c.cid] = c.ac
            # supersede older version of same aircraft: drop its pending pairs
            old = stale_by_ac.get(c.ac)
            if old is not None and old in pending:
                for r in pending[old]:
                    pair_info[(old, r)] = pair_info[(old, r)][:2] + ("superseded",)
                del pending[old]
            stale_by_ac[c.ac] = c.cid
            if c.demanders:
                pending[c.cid] = dict(c.demanders)
                for r, d in c.demanders.items():
                    pair_info[(c.cid, r)] = (c.t_issue, d, None)
        # drop receivers that already know the message (shouldn't happen) / expired far beyond deadline
        for m in list(pending):
            for r in list(pending[m]):
                if t > pending[m][r] + 120.0:       # give up 2 min after deadline
                    pair_info[(m, r)] = pair_info[(m, r)][:2] + ("expired",)
                    del pending[m][r]
            if not pending[m]:
                del pending[m]
        if not pending:
            if ci < len(cl):
                t = max(t, cl[ci].t_issue)
                continue
            break
        T, got = sched(pending, known, t)
        service = (ch.airtime_s + rng.exponential(ch.mean_access_s)) / (1 - ch.bg_load)
        t += service
        n_tx += 1
        for m, r in got:
            if rng.random() < ch.p_loss:
                continue
            known[r].add(m)
            if (m, r) in pair_info and pair_info[(m, r)][2] is None and m in pending and r in pending[m]:
                pair_info[(m, r)] = pair_info[(m, r)][:2] + (t,)
                del pending[m][r]
                if not pending[m]:
                    del pending[m]
    # metrics
    # pair universe = ALL (msg, receiver) pairs; superseded/expired/undelivered count as not met
    pairs = list(pair_info.items())
    done = [(k, v) for k, v in pairs if isinstance(v[2], float)]
    met = [v for k, v in done if v[2] <= v[1]]
    lat = [v[2] - v[0] for k, v in done]
    return dict(n_pairs=len(pairs), n_tx=n_tx,
                met=len(met) / max(len(pairs), 1),
                miss=1 - len(met) / max(len(pairs), 1),
                mean_lat=float(np.mean(lat)) if lat else float("nan"),
                p95_lat=float(np.percentile(lat, 95)) if lat else float("nan"),
                tx_per_pair=n_tx / max(len(pairs), 1))


def run_all(scen: Params, ch: ChannelParams, schemes=("unicast", "broadcast", "coded")):
    ac, cls = generate(scen)
    return {s: run(s, ac, cls, ch, scen) for s in schemes}, len(cls)

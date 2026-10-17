"""Deadline-tiered repair batching ("tiered") and delay-tolerant coded repair (DTC). Use with engine2.

Why. Each clearance is relevant to several aircraft, so one broadcast usually misses at least one of
them: at 30% loss more than half of all transmissions are repeats. A scheduler that repairs at once has
only 1-2 clearances to combine (the pending set is small), so instant coders (IDNC, our greedy XOR) find
few coding chances and perform alike. But most (clearance, aircraft) pairs have minutes of slack, and on
a party-line channel every aircraft hears every uplink, so aircraft that missed one clearance usually
hold the others. Letting repairs collect for a short, bounded time creates coding chances.

tiered (proposed), wrapped around any instant scheduler:
  tier 1  a still-feasible pair has < urgent_slack (15 s) left  -> urgent-first packet at once
  tier 2  first transmissions of new clearances                  -> sent at once (they serve everybody
                                                                    who receives them and give all
                                                                    listeners side information)
  tier 3  repairs (clearance already sent, some aircraft missed it) are collected and sent when DUE:
          the oldest waiting repair has waited `hold` s, or a repair pair has < safe_slack (60 s) left,
          or bmax (8) clearances wait for repair, or (early=True) the best packet already combines
          two or more clearances including a repair (waiting cannot improve on that).
          While nothing is due and nothing is new is waiting, the station stays silent (returns
          (None, wake_time)), which frees the channel for other datalink traffic.
  The rule only decides WHEN; the packet itself comes from the wrapped coder, so the same rule can be
  given to broadcast (bcast_tiered) and IDNC (idnc_tiered) for a fair comparison.

dtc: the same batching plus delay-tolerant repair packets: random linear combinations over GF(2^8) of the
  clearances some aircraft still lacks, which aircraft store and decode later (engine2 buffer=1).
  Candidates are scored by expected value over listening aircraft r (success prob 1 - loss_r):
  weights of pairs decoded now + lam * weights of wanted clearances tied up in stored equations / deficit.

Weights are the hard-deadline weights of schedulers3 (feasible pair: 1 + 30/slack, infeasible: 0.05).
Only information a ground station would have is used (pending needs, deadlines, reported receiver state).
"""
from partyline import coding
from partyline import engine2 as E2
import schedulers3 as S3

URGENT = 15.0
HOLD = 30.0


def _w(slack):
    return S3._w(slack)


def _value(rx, T, wants, now, lam, buffer=True):
    U = set(T) - rx.known
    if not U:
        return 0.0
    if len(U) > 1:
        if not buffer and not rx.eqs:
            return 0.0
        if E2._matching(rx.eqs + [U]) <= E2._matching(rx.eqs):
            return 0.0                    # not innovative
    r2 = rx.copy()
    newly = r2.add(T, buffer)
    v = sum(_w(d - now) for m, d in wants.items() if m in newly)
    if lam > 0 and buffer:
        V, deficit = r2.deficit()
        if deficit > 0:
            tied = [m for m in wants if m in V]
            if tied:
                v += lam * sum(_w(wants[m] - now) for m in tied) / deficit
    return v


def _wants(pending):
    W = {}
    for m, rs in pending.items():
        for r, d in rs.items():
            W.setdefault(r, {})[m] = d
    return W


def _repair_state(view, hold, safe_slack, bmax):
    """(fresh clearances, repair clearances, repair due?, wake time)."""
    pending, now, first = view["pending"], view["now"], view["first_tx"]
    fresh = [m for m in pending if m not in first]
    rep = [m for m in pending if m in first]
    if not rep:
        return fresh, rep, False, None
    oldest = min(first[m] for m in rep)
    slack = min(d - now for m in rep for d in pending[m].values())
    due = (now - oldest >= hold) or (S3.FEAS_MIN <= slack < safe_slack) or len(rep) >= bmax
    wake = oldest + hold
    if slack >= safe_slack:
        wake = min(wake, now + slack - safe_slack + 0.01)
    return fresh, rep, due, wake


def _urgent(pending, now, urgent_slack):
    feas = [d - now for m, rs in pending.items() for r, d in rs.items() if d - now >= S3.FEAS_MIN and S3._crit_pair(m, r)]
    return bool(feas) and min(feas) < urgent_slack


def make_batched(base, hold=HOLD, safe_slack=60.0, bmax=8, urgent_slack=URGENT, early=True):
    """Deadline-tiered repair batching around an instant scheduler base(pending, known, now)."""
    def sched(view):
        pending, now, known = view["pending"], view["now"], view["known"]
        if not _urgent(pending, now, urgent_slack):
            fresh, rep, due, wake = _repair_state(view, hold, safe_slack, bmax)
            if not due and early and rep:
                T, _ = base(pending, known, now)
                if len(T) >= 2 and set(T) & set(rep):
                    return dict(T=T)
            if not due:
                if not fresh:
                    return (None, wake)
                T, _ = base({m: pending[m] for m in fresh}, known, now)
                return dict(T=T)
        T, _ = base(pending, known, now)
        return dict(T=T)
    sched.v2 = True
    return sched


def make_dtc(lam=1.0, urgent_slack=URGENT, kmax=12, n_seeds=8, hold=HOLD, safe_slack=60.0, bmax=8, batch=True):
    def sched(view):
        pending, rx, now, ploss, known = view["pending"], view["rx"], view["now"], view["ploss"], view["known"]
        if _urgent(pending, now, urgent_slack):
            return dict(T=next(S3._candidates("coded", pending, known, now, 1)))
        fresh, rep, due, wake = _repair_state(view, hold, safe_slack, bmax)
        if batch and not due:
            if not fresh:
                return (None, wake)
            sub = {m: pending[m] for m in fresh}          # first transmissions only (may be coded together)
            cands = list(S3._candidates("coded", sub, known, now, n_seeds))
        else:
            cands = list(S3._candidates("coded", pending, known, now, n_seeds))
            order = sorted(rep, key=lambda m: S3._feasible_deadline(m, pending, now))
            for k in range(2, min(kmax, len(order)) + 1):
                cands.append(set(order[:k]))
        W = _wants(pending)
        best, bv, seen = None, -1.0, set()
        for T in cands:
            key = frozenset(T)
            if key in seen:
                continue
            seen.add(key)
            v = sum((1 - ploss(r)) * _value(rx[r], T, w, now, lam, view["buffer"])
                    for r, w in W.items() if set(T) - rx[r].known)
            if v > bv:
                best, bv = set(T), v
        return dict(T=best)
    sched.v2 = True
    return sched


def register(hold=HOLD):
    coding.SCHEMES["tiered"] = make_batched(coding.SCHEMES["coded_best"], hold=hold)        # proposed
    coding.SCHEMES["idnc_tiered"] = make_batched(coding.SCHEMES["idnc_best"], hold=hold)
    coding.SCHEMES["bcast_tiered"] = make_batched(coding.SCHEMES["broadcast_best"], hold=hold)
    coding.SCHEMES["dtc"] = make_dtc(hold=hold)


register()
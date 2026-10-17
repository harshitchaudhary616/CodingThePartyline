"""Deadline-feasibility and bounded-hold schedulers for Party Line Lab.

Functions (no registration on import except the default names below):
  make("idnc"|"coded", lazy=False|True, hold, safe_slack)  -> scheduler

  idnc_hd    : stronger published-style baseline. Same clique coder as 'idnc', but a pair whose deadline has
               already passed (hard deadline: it can no longer be on time) gets a tiny weight instead of the
               largest one, and the packet is seeded from the most urgent STILL-FEASIBLE pair.
  coded_hd   : our greedy XOR coder with the same feasibility rule.
  *_lazy     : the above plus bounded holding. A lone uncoded transmission is deferred for at most `hold`
               seconds (counted from when the message first waited), and only while every still-feasible pair
               has more than `safe_slack` seconds left, so a partner message can arrive and turn two
               transmissions into one. If a real coded packet (>= 2 messages) exists among the pending
               messages it is sent at once. The scheduler signals a deferral by returning (None, wake_time).
No scheme uses information a real ground station would not have (pending needs, deadlines, what each
aircraft is known to hold).
"""
from partyline import coding

LATE_W = 0.05
FEAS_MIN = 1.0   # a pair with < 1 s left cannot realistically be delivered on time (airtime ~ 1.7 s)


def _w(slack):
    return LATE_W if slack < FEAS_MIN else 1.0 + 30.0 / slack


def _feasible_deadline(m, pending, now):
    ds = [d for d in pending[m].values() if d - now >= FEAS_MIN]
    return (0, min(ds)) if ds else (1, min(pending[m].values()))


def _coded_from_seed(seed, order, pending, known, now, max_size=6):
    T = {seed}

    def score(T):
        return sum(_w(pending[m][r] - now) for m, r in coding.served(T, pending, known))
    cur = score(T)
    for m in order:
        if m == seed or len(T) >= max_size:
            continue
        T2 = T | {m}
        s2 = score(T2)
        need = [r for r in pending[seed] if (T - {seed}) <= known[r]]
        if s2 > cur and all(any(mm == seed and rr == r for mm, rr in coding.served(T2, pending, known)) for r in need):
            T, cur = T2, s2
    return T


def _idnc_from_seed(seed, V, w, known, max_size=6):
    def compat(a, b):
        (m1, r1), (m2, r2) = a, b
        return m1 == m2 or (m1 in known[r2] and m2 in known[r1])
    clique, msgs = [seed], {seed[0]}
    cand = [v for v in V if v != seed and compat(seed, v)]
    while cand:
        cand = [v for v in cand if v[0] in msgs or len(msgs) < max_size]
        if not cand:
            break
        best = max(cand, key=lambda v: w[v])
        clique.append(best); msgs.add(best[0])
        cand = [v for v in cand if v != best and compat(best, v)]
    return msgs


def _candidates(kind, pending, known, now, n_seeds):
    """Yield candidate packets (sets of message ids), the first being the 'urgent' one."""
    if kind == "coded":
        order = sorted(pending, key=lambda m: _feasible_deadline(m, pending, now))
        for s in order[:n_seeds]:
            yield _coded_from_seed(s, order, pending, known, now)
    else:
        V = [(m, r) for m, rs in pending.items() for r in rs]
        w = {(m, r): _w(pending[m][r] - now) for m, r in V}
        top = sorted(V, key=lambda v: -w[v])[:n_seeds]
        for s in top:
            yield _idnc_from_seed(s, V, w, known)


def make(kind, lazy=False, hold=8.0, safe_slack=60.0, n_seeds=8, best=False, urgent_slack=15.0):
    """lazy: defer a lone uncoded transmission for at most `hold` seconds (counted from when the message
    was first seen waiting), and only while every still-feasible pair has more than `safe_slack` seconds left.
    The bounded hold cannot build a backlog, so there is no deadline cliff."""
    st = {"seen": {}, "last": -1.0}

    def sched(pending, known, now):
        if now < st["last"]:
            st["seen"] = {}          # a new simulation started
        st["last"] = now
        seen = st["seen"]
        for m in pending:
            seen.setdefault(m, now)
        for m in [m for m in seen if m not in pending]:
            del seen[m]
        cands = list(_candidates(kind, pending, known, now, n_seeds if (lazy or best) else 1))
        first = cands[0]
        if best:
            # max-weight packet over several seeds, but whenever a feasible pair is close to its deadline
            # (< urgent_slack s) fall back to the urgent-first packet so urgent needs are never traded away
            feas0 = [d - now for rs in pending.values() for d in rs.values() if d - now >= FEAS_MIN]
            if not feas0 or min(feas0) >= urgent_slack:
                def gain(T):
                    return sum(_w(pending[m][r] - now) for m, r in coding.served(T, pending, known))
                first = max(cands, key=gain)
        if lazy:
            feas = [d - now for rs in pending.values() for d in rs.values() if d - now >= FEAS_MIN]
            oldest = max(now - seen[m] for m in pending)
            if feas and min(feas) > safe_slack and oldest < hold:
                multi = [T for T in cands if len(T) >= 2]
                if multi:
                    T = max(multi, key=lambda T: len(coding.served(T, pending, known)))
                    return T, set(coding.served(T, pending, known))
                return None, now + (hold - oldest)
        return first, set(coding.served(first, pending, known))
    return sched


def sched_broadcast_hd(pending, known, now):
    """Uncoded broadcast of the message with the earliest still-feasible deadline (fair baseline)."""
    m = min(pending, key=lambda x: _feasible_deadline(x, pending, now))
    T = {m}
    return T, set(coding.served(T, pending, known))


def sched_broadcast_best(pending, known, now, urgent_slack=15.0):
    """Uncoded broadcast of the single message that serves the most weighted pending needs (the same
    max-weight idea as *_best, so the uncoded baseline is not handicapped). Urgent-first when a feasible
    pair has < urgent_slack s left."""
    feas0 = [d - now for rs in pending.values() for d in rs.values() if d - now >= FEAS_MIN]
    if feas0 and min(feas0) < urgent_slack:
        return sched_broadcast_hd(pending, known, now)

    def gain(m):
        return sum(_w(d - now) for d in pending[m].values())
    m = max(pending, key=gain)
    T = {m}
    return T, set(coding.served(T, pending, known))


def register(hold=8.0):
    """Registers the final schemes in coding.SCHEMES (the *_best names are the recommended ones)."""
    coding.SCHEMES["broadcast_hd"] = sched_broadcast_hd
    coding.SCHEMES["broadcast_best"] = sched_broadcast_best
    coding.SCHEMES["idnc_hd"] = make("idnc")
    coding.SCHEMES["coded_hd"] = make("coded")
    coding.SCHEMES["idnc_best"] = make("idnc", best=True)
    coding.SCHEMES["coded_best"] = make("coded", best=True)
    coding.SCHEMES["coded_best_hold"] = make("coded", lazy=True, best=True, hold=hold)


register()
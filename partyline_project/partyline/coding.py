"""Coding schemes for one transmission decision, plus static (offline) bounds.

State passed to a scheduler at time t:
  pending : dict msg_id -> dict receiver -> deadline   (receivers still missing msg)
  known   : dict receiver -> set(msg_id)               (side info incl. own clearances)
A transmission is a set T of msg ids (XOR of equal-length padded messages).
Receiver r wanting m in T decodes iff T\\{m} is a subset of known[r].
No information beyond `known` (what receivers actually hold) is used -> no leakage.
"""
import itertools


def served(T, pending, known):
    """Set of (msg, receiver) pairs that decode if T is sent (error-free)."""
    out = []
    for m in T:
        for r in pending.get(m, {}):
            if (T - {m}) <= known[r]:
                out.append((m, r))
    return out


def urgency(m, pending):
    return min(pending[m].values())


def sched_unicast(pending, known, now):
    """Repeated unicast: one addressed message to one receiver (EDF over pairs)."""
    best = min(((d, m, r) for m, rs in pending.items() for r, d in rs.items()))
    _, m, r = best
    return {m}, {(m, r)}          # only the addressed receiver is credited


def sched_broadcast(pending, known, now):
    """Uncoded broadcast: send the most urgent single message to everyone."""
    m = min(pending, key=lambda x: urgency(x, pending))
    T = {m}
    return T, set(served(T, pending, known))


def sched_coded(pending, known, now, max_size=6, urgent_first=True):
    """Deadline-aware greedy XOR (clique-cover style) coding.

    Seed = most urgent message; greedily add messages that strictly increase the number of
    served (msg, receiver) pairs, preferring urgent ones. Weighted by 1/(slack) so near-deadline
    pairs dominate.
    """
    order = sorted(pending, key=lambda x: urgency(x, pending))
    seed = order[0]
    T = {seed}

    def score(T):
        s = 0.0
        for m, r in served(T, pending, known):
            slack = max(pending[m][r] - now, 1.0)
            s += 1.0 + 30.0 / slack
        return s

    cur = score(T)
    for m in order[1:]:
        if len(T) >= max_size:
            break
        T2 = T | {m}
        s2 = score(T2)
        # must keep the seed's receivers served
        if s2 > cur and all(any(mm == seed and rr == r for mm, rr in served(T2, pending, known))
                            for r in [r for r in pending[seed] if (T - {seed}) <= known[r]]):
            T, cur = T2, s2
    return T, set(served(T, pending, known))


SCHEMES = {"unicast": sched_unicast, "broadcast": sched_broadcast, "coded": sched_coded}


# ---------------------------------------------------------------- static / offline
def exact_gf2_length(msgs, demands, known):
    """Exact optimal SCALAR LINEAR GF(2) index code length for tiny instances (<=5 msgs).

    msgs: list of ids; demands: list of (msg, receiver); known: receiver -> set(msg).
    Returns minimal k such that k binary combinations let every receiver decode its message.
    """
    idx = {m: i for i, m in enumerate(msgs)}
    n = len(msgs)
    assert n <= 5, "exact solver limited to 5 messages"
    full = range(1, 1 << n)

    def span_has(rows, target):
        # does span(rows) contain target (ints over GF(2))?
        basis = []
        for v in rows:
            for b in basis:
                v = min(v, v ^ b)
            if v:
                basis.append(v)
        t = target
        for b in basis:
            t = min(t, t ^ b)
        return t == 0

    def ok(rows):
        for m, r in demands:
            kmask = sum(1 << idx[x] for x in known[r] if x in idx)
            # decodable iff exists combination c of rows with c = e_m + (stuff in known coordinates)
            # i.e. e_m in span(rows) + span(e_x : x in known)
            kvecs = [1 << idx[x] for x in known[r] if x in idx]
            if not span_has(list(rows) + kvecs, 1 << idx[m]):
                return False
            # and must not be trivially decodable w/o rows (m in known) -> demands exclude that
        return True

    for k in range(1, n + 1):
        for rows in itertools.combinations(full, k):
            if ok(rows):
                return k
    return n


def greedy_static_length(msgs, demands, known):
    """Greedy XOR cover of a static instance using the same coder (error-free, no deadlines)."""
    pending = {}
    for m, r in demands:
        pending.setdefault(m, {})[r] = 0.0
    known = {r: set(k) for r, k in known.items()}
    n_tx = 0
    while pending:
        T, got = sched_coded(pending, known, 0.0)
        for m, r in got:
            known[r].add(m)
            pending[m].pop(r, None)
            if not pending[m]:
                del pending[m]
        n_tx += 1
        assert got, "coder made no progress"
    return n_tx


def lower_bound_mais(demands, known, limit=18):
    """Lower bound: largest set of demand pairs, distinct messages, whose induced
    side-information digraph is acyclic (MAIS bound; valid for index coding length)."""
    pairs = list({(m, r) for m, r in demands})
    if len(pairs) > limit:
        return None
    best = 1 if pairs else 0

    def acyclic(S):
        # edge u->v if message of v is known by receiver of u
        nodes = list(S)
        indeg = {u: 0 for u in nodes}
        adj = {u: [] for u in nodes}
        for u in nodes:
            for v in nodes:
                if u != v and v[0] in known[u[1]]:
                    adj[u].append(v)
                    indeg[v] += 1
        q = [u for u in nodes if indeg[u] == 0]
        seen = 0
        while q:
            u = q.pop()
            seen += 1
            for v in adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        return seen == len(nodes)

    for k in range(len(pairs), 0, -1):
        for S in itertools.combinations(pairs, k):
            if len({m for m, _ in S}) == k and acyclic(S):
                return k
    return best

"""Extra schedulers for Party Line Lab. Importing this module registers them in coding.SCHEMES.

idnc : published-style instantly decodable network coding (clique on the receiver-message graph).
       Vertex = (message m, receiver r still needing m). Two vertices are compatible if they are the
       same message, or each receiver already holds the other's message. A clique is a set that can
       be XORed so every member decodes at once. Greedy maximum-weight clique, weights = urgency.
"""
from partyline import coding


def sched_idnc(pending, known, now, max_size=6):
    V = [(m, r) for m, rs in pending.items() for r in rs]
    w = {(m, r): 1.0 + 30.0 / max(pending[m][r] - now, 1.0) for m, r in V}

    def compat(a, b):
        (m1, r1), (m2, r2) = a, b
        return m1 == m2 or (m1 in known[r2] and m2 in known[r1])

    seed = max(V, key=lambda v: w[v])
    clique = [seed]
    msgs = {seed[0]}
    cand = [v for v in V if v != seed and compat(seed, v)]
    while cand:
        # a vertex with a message already in the packet adds no airtime; a new message counts against max_size
        cand = [v for v in cand if v[0] in msgs or len(msgs) < max_size]
        if not cand:
            break
        best = max(cand, key=lambda v: w[v])
        clique.append(best)
        msgs.add(best[0])
        cand = [v for v in cand if v != best and compat(best, v)]
    T = set(msgs)
    return T, set(coding.served(T, pending, known))


coding.SCHEMES["idnc"] = sched_idnc
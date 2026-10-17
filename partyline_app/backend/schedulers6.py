"""Published-style IDNC baseline (Sorour and Valaee, "On minimizing broadcast completion delay for instantly
decodable network coding", and their generalised IDNC): every pending (clearance, aircraft) need is a vertex of the
index-coding graph; two vertices are compatible if one transmission can serve both (same clearance, or each aircraft
already holds the other's clearance). Vertex weight = the number of clearances the aircraft still lacks, so aircraft
far from completion are served first. A packet is the greedy maximum-weight clique started from the heaviest vertex,
sent at once. It knows nothing about deadlines, critical neighbours or awareness classes, and does not store
undecodable combinations. Use with engine2; register with schedulers6.register()."""
from partyline import coding
import schedulers3 as S3


def sched_idnc_pub(pending, known, now):
    V = [(m, r) for m, rs in pending.items() for r in rs]
    demand = {}
    for m, r in V:
        demand[r] = demand.get(r, 0) + 1
    w = {(m, r): demand[r] for m, r in V}
    seed = max(V, key=lambda v: (w[v], -v[0]))          # heaviest vertex; ties go to the oldest clearance
    T = S3._idnc_from_seed(seed, V, w, known)
    return T, set(coding.served(T, pending, known))


def register():
    coding.SCHEMES["idnc_pub"] = sched_idnc_pub
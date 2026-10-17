"""Slack-tiered generation coding (STGC): tiered repair with RANDOM LINEAR (stored, delayed-decoding) repair
packets, for the party-line problem; plus RLNC baselines. Use with engine2. Tested as an extension of the
tiered scheme (schedulers4): on synthetic party-line traffic it ties with it (+3 +/- 3% uplinks, not
significant) because at a repair decision an aircraft lacks only ~1.2-1.4 clearances on average, so
instantly decodable packets are already nearly as good.

Problem. Each clearance must reach its critical receivers (conflict neighbours, hard deadline) and, for
party-line awareness, every other aircraft on the same sector frequency (soft deadline). With tens of
receivers per clearance and independent losses, almost every clearance is missed by someone. An uncoded
repeat or an instantly decodable XOR packet helps only receivers that miss exactly one clearance of the
packet; one random linear combination over a set S of missed clearances gives one new degree of freedom
(DoF) to EVERY receiver that still lacks something in S - but it is wasted on a receiver for which S also
contains clearances it lacks and does not want (it must decode those too).

STGC. At each decision the ground station:
  tier 1  critical pair with a feasible deadline < urgent_slack s away  ->  instantly decodable packet seeded
          from that pair (never waits for a combination to fill up)
  tier 2  clearances never transmitted  ->  sent at once, uncoded unless an XOR of new clearances serves
          more (an aircraft owning one clearance and wanting another); every listener that receives an
          uncoded copy decodes it immediately
  tier 3  repairs are collected into a GENERATION and sent when due: the oldest repair has waited `hold` s,
          or a still-feasible repair pair has < safe_slack s left, or bmax clearances wait for repair.
          The packet is a random linear combination over GF(2^8) of a set S chosen among
            - demand-aligned generations: for the aircraft with the largest weighted deficit, the repair
              clearances it wants and lacks (deadline order, at most kmax) - aircraft on the same sector
              frequency want the same clearances, so such an S is useful to all of them,
            - deadline-ordered prefixes of all repair clearances,
            - instantly decodable XOR packets, and the best packet of new clearances,
          maximising the expected weighted DoF progress   sum_r (1 - loss_r) * W_r(S) / d_r(S)
          W_r = weight of the clearances in S that r still wants, d_r = DoF r still needs to decode every
          clearance of S it lacks (counting combinations it has stored); d_r = 1 means r decodes now.
  While nothing is due and nothing is new, the station stays silent.
Weights: hard-deadline weight of schedulers3 (1 + 30/slack, 0.05 once infeasible), x crit_w for critical pairs.

Baselines (deadline-agnostic online systematic RLNC: new clearances uncoded in arrival order, then repeated
random combinations, no holding):
  rlnc_sys    combination of all repair clearances (oldest first, at most kmax) - the classic scheme
  rlnc_group  combination of the repair clearances wanted by the aircraft with the largest deficit
              (demand-aware generation, so the comparison isolates the deadline-tiered timing)
Ablations of stgc:
  stgc_noclass  no critical/awareness weighting
  stgc_hold0    repairs sent immediately (no holding)
  stgc2         stgc whose urgent and repair candidates also include weighted-clique (idnc_best style) packets:
                a critical pair seeds the packet, as in idnc_cls
Class-aware baselines (broadcast_cls, idnc_cls, coded_cls, tiered_cls, idnc_tiered_cls): the XOR/IDNC/broadcast
schemes given the same class knowledge as stgc (critical pairs x crit_w, urgent-first only for critical pairs).
They isolate whether stgc's gain comes from knowing the classes or from the random linear repair.

Only information a ground station has is used: pending needs and deadlines, each aircraft's reported state
(decoded clearances and stored combinations), and the class of each pair (critical / awareness).
"""
from partyline import coding
from partyline import engine2 as E2
import schedulers3 as S3

URGENT = 15.0


def _pair_w(scn, m, r, slack, crit_w):
    w = S3._w(slack)
    crit = getattr(scn, "critical", None)
    if crit_w != 1.0 and crit is not None and (m, r) in crit:
        w *= crit_w
    return w


def _dof_needed(rx, U):
    if not rx.eqs:
        return len(U)
    eq = [e for e in rx.eqs if e <= U]
    return len(U) - (E2._matching(eq) if eq else 0)


def _score(S, view, W_by_r):
    rx, ploss = view["rx"], view["ploss"]
    tot = 0.0
    for r, wants in W_by_r.items():
        U = S - rx[r].known
        if not U:
            continue
        Wr = sum(wants[m] for m in U if m in wants)
        if Wr <= 0:
            continue
        d = _dof_needed(rx[r], U)
        if d <= 0 or (d > 1 and not view["buffer"]):
            continue
        tot += (1 - ploss(r)) * Wr / d
    return tot


def _wants(view, crit_w):
    pending, now, scn = view["pending"], view["now"], view["scn"]
    W = {}
    for m, rs in pending.items():
        for r, dl in rs.items():
            W.setdefault(r, {})[m] = _pair_w(scn, m, r, dl - now, crit_w)
    return W


def _deficit_sets(W, rep, rx, top):
    """Top aircraft by weighted deficit over repair clearances -> their wanted, missing repair clearances."""
    rep = set(rep)
    D = []
    for r, wants in W.items():
        miss = [m for m in wants if m in rep and m not in rx[r].known]
        if miss:
            D.append((sum(wants[m] for m in miss), r, miss))
    D.sort(reverse=True)
    return D[:top]


def _idnc_cands(W, known, n):
    """Instantly decodable packets seeded from the n highest-weight (clearance, aircraft) pairs, weights W[r][m]
    (class-weighted): the same clique rule as idnc_best, so a critical pair seeds the packet."""
    V = [(m, r) for r, wants in W.items() for m in wants]
    w = {(m, r): W[r][m] for m, r in V}
    for seed in sorted(V, key=lambda v: -w[v])[:n]:
        yield S3._idnc_from_seed(seed, V, w, known)


def make_stgc(hold=20.0, safe_slack=20.0, bmax=24, urgent_slack=URGENT, crit_w=3.0, kmax=16, n_xor=4,
              n_groups=6, class_aware=True, idnc_seed=False):
    def sched(view):
        pending, now, known, first, scn = view["pending"], view["now"], view["known"], view["first_tx"], view["scn"]
        crit = getattr(scn, "critical", None) if class_aware else None
        order = sorted(pending, key=lambda x: S3._feasible_deadline(x, pending, now))
        # ---- tier 1: urgent critical pair -> instantly decodable packet seeded from it
        urg = [(dl, m) for m, rs in pending.items() for r, dl in rs.items()
               if S3.FEAS_MIN <= dl - now < urgent_slack and (crit is None or (m, r) in crit)]
        cw = crit_w if class_aware else 1.0
        W = _wants(view, cw)
        if urg and idnc_seed:
            # urgent critical pair -> weighted clique packet seeded from the most urgent critical pair
            dl0, m0 = min(urg)
            r0 = min((dl, r) for r, dl in pending[m0].items() if S3.FEAS_MIN <= dl - now < urgent_slack
                     and (crit is None or (m0, r) in crit))[1]
            V = [(m, r) for m, rs in pending.items() for r in rs]
            w = {(m, r): W[r][m] for m, r in V}
            return dict(T=S3._idnc_from_seed((m0, r0), V, w, known))
        if urg:
            return dict(T=S3._coded_from_seed(min(urg)[1], order, pending, known, now))
        fresh = [m for m in pending if m not in first]
        rep = [m for m in pending if m in first]
        due, wake = False, None
        if rep:
            oldest = min(first[m] for m in rep)
            feas = [d - now for m in rep for d in pending[m].values() if d - now >= S3.FEAS_MIN]
            slack = min(feas) if feas else float("inf")
            due = (now - oldest >= hold) or (slack < safe_slack) or len(rep) >= bmax
            wake = oldest + hold
            if slack < float("inf"):
                wake = min(wake, now + slack - safe_slack + 0.01)

        def fresh_best():
            # best instantly decodable packet over new clearances only: uncoded unless an XOR of new
            # clearances serves more (aircraft that own one clearance and want another)
            T, _ = coding.SCHEMES["coded_best"]({m: pending[m] for m in fresh}, known, now)
            return set(T)
        # ---- tier 2: new clearances at once while repairs are not due
        if fresh and not due:
            return dict(T=fresh_best())
        if not due:
            return (None, wake)
        # ---- tier 3: repair packet
        cands = []
        if fresh:
            cands.append(fresh_best())
        dl_key = lambda m: S3._feasible_deadline(m, pending, now)
        for _, r, miss in _deficit_sets(W, rep, view["rx"], n_groups):
            cands.append(set(sorted(miss, key=dl_key)[:kmax]))
        gen = [m for m in order if m in first][:kmax]
        for k in range(1, len(gen) + 1):
            cands.append(set(gen[:k]))
        for T in S3._candidates("coded", pending, known, now, n_xor):
            cands.append(set(T))
        if idnc_seed:
            for T in _idnc_cands(W, known, n_xor + 4):
                cands.append(set(T))
        best, bv, seen = None, -1.0, set()
        for S in cands:
            key = frozenset(S)
            if key in seen:
                continue
            seen.add(key)
            v = _score(S, view, W)
            if v > bv:
                best, bv = S, v
        return dict(T=best)
    sched.v2 = True
    return sched


def make_rlnc(kmax=16, group=False):
    """Online systematic RLNC without deadline awareness or holding (baselines)."""
    def sched(view):
        pending, first, rx = view["pending"], view["first_tx"], view["rx"]
        fresh = [m for m in pending if m not in first]
        if fresh:
            return dict(T={min(fresh)})                  # arrival order (clearance ids increase with time)
        if group:
            W = {}
            for m, rs in pending.items():
                for r in rs:
                    W.setdefault(r, {})[m] = 1.0
            D = _deficit_sets(W, list(pending), rx, 1)
            if D:
                return dict(T=set(sorted(D[0][2], key=lambda m: first[m])[:kmax]))
        return dict(T=set(sorted(pending, key=lambda m: first[m])[:kmax]))
    sched.v2 = True
    return sched


def classify(inner, v2=False, crit_w=3.0):
    """Give an existing scheduler the SAME class knowledge stgc has: critical pairs weigh crit_w times more
    and only critical pairs trigger the urgent-first rule (schedulers3.CTX). For XOR/IDNC/broadcast baselines."""
    def sched(view):
        S3.CTX["crit"] = getattr(view["scn"], "critical", None)
        S3.CTX["w"] = crit_w
        try:
            if v2:
                return inner(view)
            T, _ = inner(view["pending"], view["known"], view["now"])
            return dict(T=T)
        finally:
            S3.CTX["crit"] = None
            S3.CTX["w"] = 1.0
    sched.v2 = True
    return sched


def register(**kw):
    coding.SCHEMES["stgc"] = make_stgc(**kw)
    kw2 = {k: v for k, v in kw.items() if k != "class_aware"}
    coding.SCHEMES["stgc_noclass"] = make_stgc(class_aware=False, **kw2)
    kw0 = dict(kw); kw0["hold"] = 0.0
    coding.SCHEMES["stgc_hold0"] = make_stgc(**kw0)             # ablation: repairs sent immediately (no holding)
    kw3 = {k: v for k, v in kw.items() if k != "idnc_seed"}
    coding.SCHEMES["stgc2"] = make_stgc(idnc_seed=True, **kw3)  # stgc + weighted-clique (idnc_best style) seeds
    # class-aware versions of the XOR/IDNC/broadcast baselines (same critical weight and urgency rule as stgc)
    import schedulers4 as S4
    hold = kw.get("hold", 30.0)
    cw = kw.get("crit_w", 3.0)
    coding.SCHEMES["broadcast_cls"] = classify(coding.SCHEMES["broadcast_best"], crit_w=cw)
    coding.SCHEMES["idnc_cls"] = classify(coding.SCHEMES["idnc_best"], crit_w=cw)
    coding.SCHEMES["coded_cls"] = classify(coding.SCHEMES["coded_best"], crit_w=cw)
    coding.SCHEMES["tiered_cls"] = classify(S4.make_batched(coding.SCHEMES["coded_best"], hold=hold), v2=True, crit_w=cw)
    coding.SCHEMES["idnc_tiered_cls"] = classify(S4.make_batched(coding.SCHEMES["idnc_best"], hold=hold), v2=True, crit_w=cw)
    coding.SCHEMES["rlnc_sys"] = make_rlnc()
    coding.SCHEMES["rlnc_group"] = make_rlnc(group=True)


register()
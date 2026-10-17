"""Relevance-filtered awareness: of the aircraft on the same sector frequency, only the K nearest to the cleared aircraft (at issue time)
are awareness receivers. K = 0 or K >= sector population reproduces awareness.with_awareness. This is the filter a display would apply so
that a pilot sees a bounded number of awareness clearances per minute."""
import copy, math
from partyline.engine import Clearance, DT, _active
from awareness import A_DEFAULT, SECTOR_DEFAULT, _sector


def with_awareness_k(scn, A=A_DEFAULT, sector=SECTOR_DEFAULT, K=0):
    s2 = copy.copy(scn)
    s2.clearances = []
    aware, critical = set(), set()
    x0, y0 = scn.bounds[0], scn.bounds[1]
    for c in scn.clearances:
        d = dict(c.dem)
        critical |= {(c.cid, r) for r in c.dem}
        k0 = int(c.t // DT)
        ki = k0 if _active(scn, c.ac, k0) else k0 + 1
        kA = min(int((c.t + A) // DT), scn.K - 1)
        if _active(scn, c.ac, ki):
            xi, yi = scn.X[c.ac, ki], scn.Y[c.ac, ki]
            si = _sector(xi, yi, sector, x0, y0)
            cand = []
            for j in range(scn.n):
                if j == c.ac or j in d or not (_active(scn, j, ki) and _active(scn, j, kA)):
                    continue
                xj, yj = scn.X[j, ki], scn.Y[j, ki]
                if _sector(xj, yj, sector, x0, y0) == si:
                    cand.append((math.hypot(xj - xi, yj - yi), j))
            cand.sort()
            for _, j in (cand[:K] if K > 0 else cand):
                d[j] = c.t + A
                aware.add((c.cid, j))
        s2.clearances.append(Clearance(c.cid, c.ac, c.version, c.t, d))
    s2.aware, s2.critical = aware, critical
    return s2

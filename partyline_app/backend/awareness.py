"""Party-line awareness demand (two relevance classes).

On a voice frequency every pilot hears every clearance ("party-line information"; pilots rate it important,
especially traffic near airports - Pritchett & Hansman 1993). CPDLC unicast removes it. Restoring it over
datalink means each clearance is relevant not only to its conflict neighbours but to every aircraft on the
same ATC frequency (sector).

Two classes of (clearance, aircraft) pairs:
  critical   : the existing conflict-geometry pairs (deadline = predicted loss of separation - margin, or t+H)
  awareness  : every other aircraft j on the same frequency when the clearance is issued AND still airborne
               A seconds later. Deadline t + A (soft, default 60 s).
Frequency membership:
  sector = s   (default 60 NM): the airspace is split into s x s NM sectors; aircraft in the same sector at
               issue time share the frequency (homogeneous demand inside a sector)
  sector = 0 with r_aware = R: aircraft within R NM of the clearance's aircraft (overlapping neighbourhoods)
The VDL Mode 2 channel itself is shared by all sectors: every aircraft in range hears every uplink.
A pair that is already critical keeps its critical deadline.

with_awareness(scn) returns a NEW scenario (the original is not modified) with:
  scn2.clearances : same ids/times/versions, demand = critical U awareness
  scn2.critical   : set of (cid, r) critical pairs
  scn2.aware      : set of (cid, r) awareness pairs
"""
import copy
import math
from partyline.engine import Clearance, DT, _active

A_DEFAULT = 60.0
SECTOR_DEFAULT = 60.0
R_AWARE_DEFAULT = 40.0


def _sector(x, y, s, x0, y0):
    return (int(math.floor((x - x0) / s)), int(math.floor((y - y0) / s)))


def with_awareness(scn, A=A_DEFAULT, sector=SECTOR_DEFAULT, r_aware=R_AWARE_DEFAULT):
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
            si = _sector(xi, yi, sector, x0, y0) if sector > 0 else None
            for j in range(scn.n):
                if j == c.ac or j in d:
                    continue
                if not (_active(scn, j, ki) and _active(scn, j, kA)):
                    continue
                xj, yj = scn.X[j, ki], scn.Y[j, ki]
                same = (_sector(xj, yj, sector, x0, y0) == si) if sector > 0 else (math.hypot(xj - xi, yj - yi) <= r_aware)
                if same:
                    d[j] = c.t + A
                    aware.add((c.cid, j))
        s2.clearances.append(Clearance(c.cid, c.ac, c.version, c.t, d))
    s2.aware, s2.critical = aware, critical
    return s2


def critical_only(scn):
    """The original scenario tagged with classes (every pair critical)."""
    s2 = copy.copy(scn)
    s2.critical = {(c.cid, r) for c in scn.clearances for r in c.dem}
    s2.aware = set()
    return s2
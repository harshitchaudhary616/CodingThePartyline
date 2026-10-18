"""Exact GF(2^8) decoding, used to check the generic-rank (matching) rule of engine2.Rx.

ExactRx has the same interface as engine2.Rx (known, eqs, copy, add, learn, deficit) but keeps the real coefficient rows
of every stored packet and decides innovation and decoding by Gaussian elimination over GF(2^8) (polynomial 0x11d).
The coefficients of the packet being received are read from CUR (a dict message -> coefficient), which engine2.simulate
sets once per uplink, so that every receiver of one uplink sees the same coefficients. `eqs` is kept as the list of
supports (sets of still-unknown clearances) so that schedulers that read it work unchanged.
STATS counts, over every stored-or-rejected multi-unknown reception, how often the generic-rank rule and exact elimination
disagree on whether the packet is innovative: STATS = [checks, generic says innovative but exact does not, the reverse]."""
from __future__ import annotations

EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def mul(a, b):
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def inv(a):
    return EXP[255 - LOG[a]]


CUR: dict = {}
STATS = [0, 0, 0]
SCORING = [False]          # True while a scheduler evaluates candidate packets on copies: fresh coefficients, not counted
_rs = __import__("random").Random(12345)


def _matching(eqs):
    match = {}

    def aug(i, seen):
        for v in eqs[i]:
            if v in seen:
                continue
            seen.add(v)
            if v not in match or aug(match[v], seen):
                match[v] = i
                return True
        return False
    return sum(1 for i in range(len(eqs)) if aug(i, set()))


class ExactRx:
    __slots__ = ("known", "rows")          # rows: {pivot: {var: coef}} in reduced row-echelon form, pivot coefficient 1

    def __init__(self):
        self.known = set()
        self.rows = {}

    @property
    def eqs(self):
        return [set(r) for r in self.rows.values()]

    def copy(self):
        r = ExactRx(); r.known = set(self.known); r.rows = {p: dict(v) for p, v in self.rows.items()}
        return r

    def _reduce(self, row):
        for p, pr in self.rows.items():
            c = row.get(p, 0)
            if c:
                for v, a in pr.items():
                    nv = row.get(v, 0) ^ mul(c, a)
                    if nv:
                        row[v] = nv
                    else:
                        row.pop(v, None)
        return row

    def _insert(self, row):
        p = min(row)                           # pivot = smallest message id in the row
        ip = inv(row[p])
        row = {v: mul(ip, a) for v, a in row.items()}
        for q, qr in self.rows.items():        # eliminate p from the other rows (keep reduced form)
            c = qr.get(p, 0)
            if c:
                for v, a in row.items():
                    nv = qr.get(v, 0) ^ mul(c, a)
                    if nv:
                        qr[v] = nv
                    else:
                        qr.pop(v, None)
        self.rows[p] = row

    def add(self, T, buffer=True):
        U = set(T) - self.known
        if not U:
            return set()
        if len(U) == 1:
            x = next(iter(U)); self.known.add(x)
            return {x} | self._closure()
        if not buffer:
            return set()
        if SCORING[0]:
            row = self._reduce({m: _rs.randint(1, 255) for m in U})
            if not row:
                return set()
            self._insert(row)
            return self._closure()
        row = {m: CUR.get(m, 1) for m in U}
        g_innov = _matching(self.eqs + [U]) > _matching(self.eqs)
        row = self._reduce(row)
        e_innov = bool(row)
        STATS[0] += 1
        STATS[1] += int(g_innov and not e_innov)
        STATS[2] += int(e_innov and not g_innov)
        if not e_innov:
            return set()
        self._insert(row)
        return self._closure()

    def learn(self, x):
        if x in self.known:
            return set()
        self.known.add(x)
        return {x} | self._closure()

    def _closure(self):
        new = set()
        while True:
            changed = False
            for p in list(self.rows):           # known values are subtracted out of every row
                r = self.rows[p]
                for v in [v for v in r if v in self.known]:
                    del r[v]; changed = True
                if not r:
                    del self.rows[p]
            if changed:                         # rebuild reduced form after removing known variables
                old = list(self.rows.values()); self.rows = {}
                for r in old:
                    r = self._reduce(dict(r))
                    if r:
                        self._insert(r)
            got = {next(iter(r)) for r in self.rows.values() if len(r) == 1}
            got -= self.known
            if not got:
                return new
            self.known |= got
            new |= got

    def deficit(self):
        if not self.rows:
            return set(), 0
        V = set().union(*self.rows.values())
        return V, len(V) - len(self.rows)

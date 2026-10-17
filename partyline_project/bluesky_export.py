"""Export a generated scenario to a BlueSky .scn file so clearances/execution can be re-simulated
by an INDEPENDENT ATC simulator (step 3 of the plan). UNTESTED against BlueSky here: BlueSky was
not installable in the build sandbox. Check command syntax against your BlueSky version
(docs: https://github.com/TUDelft-CNS-ATM/bluesky). Coordinates are mapped NM -> lat/lon near 0,0.
Usage: python3 bluesky_export.py SEED out.scn
"""
import sys, numpy as np
from partyline.scenario import Params, generate
NM2DEG = 1 / 60.0
def hms(t): return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{t%60:05.2f}"
def main(seed, out):
    ac, cls = generate(Params(seed=seed))
    L = []
    for a in ac:
        x, y = a.route[0]; hdg = 0
        d = a.route[1] - a.route[0]; hdg = (np.degrees(np.arctan2(d[0], d[1])) + 360) % 360
        L.append(f"{hms(a.t0)}>CRE AC{a.idx:03d},B738,{y*NM2DEG:.5f},{x*NM2DEG:.5f},{hdg:.1f},FL100,{a.speeds[0][1]:.0f}")
        for wp in a.route[1:]:
            L.append(f"{hms(a.t0)}>ADDWPT AC{a.idx:03d},{wp[1]*NM2DEG:.5f},{wp[0]*NM2DEG:.5f}")
    for c in cls:
        if c.version > 0:
            v = [s for s in ac[c.ac].speeds if abs(s[0]-c.t_issue) < 1e-6]
            if v: L.append(f"{hms(c.t_issue)}>SPD AC{c.ac:03d},{v[0][1]:.0f}")
    prio = {"CRE": 0, "ADD": 1, "SPD": 2}
    L.sort(key=lambda l: (l.split(">")[0], prio.get(l.split(">")[1][:3], 3)))
    open(out, "w").write("\n".join(L) + "\n")
if __name__ == "__main__": main(int(sys.argv[1]), sys.argv[2])

"""Channel-time cost of feedback, from saved party-study JSON files (no simulation).

A coded broadcast scheme needs state reports from the aircraft. Channel time of a run is
    airtime of the uplinks  +  (number of reports) * f
where f is the channel time of ONE report. This script shows, for a range of f, the channel time of every scheme
relative to today's unicast CPDLC, and the break-even f at which a scheme stops saving channel time.
Two report policies: 'all' (every aircraft with a pending need reports after every uplink) and 'nack' (only
aircraft that missed the packet report).

  python3 report_cost.py data/party_dataset4_5_8_loss0.3_A60.json
  python3 report_cost.py data/party_dataset4_5_8_loss0.3_A60.json stgc2 idnc_cls idnc_best
"""
import json, sys

FS = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    d = json.load(open(sys.argv[1]))
    S = d["schemes"]
    names = sys.argv[2:] or [n for n in ("unicast", "broadcast_best", "idnc_best", "idnc_cls", "tiered_cls", "rlnc_sys", "stgc", "stgc2") if n in S]
    if "unicast" not in S:
        sys.exit("file has no unicast run")
    air = {n: (S[n]["air"][0] if "air" in S[n] else S[n]["n_tx"][0] * d["channel"]["airtime"]) for n in S}
    u_air, u_fb = air["unicast"], S["unicast"]["fb"][0]
    print(f"{d['meta']['name']}  loss {d['channel']['loss']}  hdr {d['channel'].get('hdr', 0)}")
    print("channel time relative to unicast (1.00 = same; below 1 = saves channel time)\n")
    for pol, key in (("all reports", "fb"), ("NACK-only reports", "fb_nack")):
        print(f"-- {pol}")
        print(f"{'scheme':16}" + "".join(f"{'f=' + format(f, 'g') + 's':>10}" for f in FS) + f"{'break-even f':>14}")
        for n in names:
            if n not in S or n == "unicast":
                continue
            row = []
            for f in FS:
                row.append((air[n] + f * S[n][key][0]) / (u_air + f * u_fb))
            den = S[n][key][0] - u_fb
            be = (u_air - air[n]) / den if den > 0 else float("inf")
            be_s = "always saves" if (be == float("inf") and air[n] < u_air) else (f"{be * 1000:.1f} ms" if be > 0 else "never saves")
            print(f"{n:16}" + "".join(f"{v:10.2f}" for v in row) + f"{be_s:>14}")
        print()
    print("uplinks and reports per window:")
    for n in names:
        if n in S:
            print(f"  {n:16} uplinks {S[n]['n_tx'][0]:7.1f}   reports(all) {S[n]['fb'][0]:8.0f}   reports(NACK-only) {S[n]['fb_nack'][0]:8.0f}")


if __name__ == "__main__":
    main()
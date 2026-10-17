"""Fit the channel model of the simulator to a recorded CPDLC / VDL Mode 2 uplink log.

Input CSV (header required), one row per uplink attempt:
    t_uplink      time the uplink was handed to the link (s)
    t_delivered   time the aircraft received it (s); empty or ignored if ok = 0
    ok            1 if delivered, 0 if lost / timed out
    busy          (optional) fraction of time the channel was busy around the attempt (0..1): used as the background load bg
    bytes         (optional) message size in bytes
Optional second CSV (--reports) with the aircraft state reports / acknowledgements:  columns sent, received (0/1)  -> report loss q.

Model: service time = (airtime + Exp(access)) / (1 - bg), loss = 1 - mean(ok).  Estimates:
    p  = 1 - mean(ok)
    bg = mean(busy)               (default 0.3 if the column is absent: say so in the paper)
    airtime = bytes * 8 / bitrate * overhead   if bytes is given (bitrate 31500 b/s for VDL Mode 2; overhead --overhead, default 2.0 for
              framing, acknowledgement and CSMA protocol overhead), else the 1st percentile of the service times times (1 - bg)
    access  = max(0, mean(service) * (1 - bg) - airtime)
The script also prints the observed and model-implied standard deviation of the service time as a goodness-of-fit check (an exponential
access delay implies std = access / (1 - bg)); a large mismatch means the exponential access assumption should be revisited.

  python3 calibrate.py cpdlc_log.csv [--reports acks.csv] [--bitrate 31500] [--overhead 2.0] [--out channel_profile.json]
Prints the matching run_future.py flags:   --loss P --airtime A --access M --bg B --fbloss Q
"""
import argparse, csv, json, sys
import numpy as np


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--reports")
    ap.add_argument("--bitrate", type=float, default=31500.0)
    ap.add_argument("--overhead", type=float, default=2.0)
    ap.add_argument("--out", default="channel_profile.json")
    a = ap.parse_args()
    R = read(a.log)
    ok = np.array([int(float(r["ok"])) for r in R])
    p = 1.0 - ok.mean()
    svc = np.array([float(r["t_delivered"]) - float(r["t_uplink"]) for r, o in zip(R, ok) if o and r.get("t_delivered") not in (None, "")])
    if len(svc) < 20:
        sys.exit("need at least 20 delivered uplinks")
    busy = [float(r["busy"]) for r in R if r.get("busy") not in (None, "")]
    bg = float(np.mean(busy)) if busy else 0.3
    by = [float(r["bytes"]) for r in R if r.get("bytes") not in (None, "")]
    air = float(np.mean(by)) * 8.0 / a.bitrate * a.overhead if by else float(np.percentile(svc, 1)) * (1 - bg)
    access = max(0.0, float(svc.mean()) * (1 - bg) - air)
    out = dict(loss=round(p, 4), airtime=round(air, 4), access=round(access, 4), bg=round(bg, 4), n_uplinks=len(R), n_delivered=int(ok.sum()),
               service_mean=round(float(svc.mean()), 3), service_std_observed=round(float(svc.std()), 3),
               service_std_model=round(access / (1 - bg), 3), bg_from_log=bool(busy), airtime_from_bytes=bool(by))
    if a.reports:
        Q = read(a.reports)
        sent = np.array([int(float(r["sent"])) for r in Q]); rec = np.array([int(float(r["received"])) for r in Q])
        out["fbloss"] = round(float(1.0 - rec[sent == 1].mean()), 4)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))
    print("\nrun_future.py flags:  --loss %.3f --airtime %.3f --access %.3f --bg %.3f%s" % (out["loss"], out["airtime"], out["access"], out["bg"],
          (" --reports --fbloss %.3f" % out["fbloss"]) if "fbloss" in out else ""))
    if not busy:
        print("note: no 'busy' column, bg defaulted to 0.3 (the simulator default)")


if __name__ == "__main__":
    main()

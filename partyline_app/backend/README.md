# Coding the Party Line: simulator and experiments

Code and scripts behind the paper "Coding the Party Line: Relevance-Aware, Deadline-Constrained Coded Broadcast of Air Traffic
Control Datalink Clearances" (Harshit Chaudhary, Gopika K S and Dr. Sivaranjini N). Everything here is simulation: aircraft paths are real OpenSky ADS-B
recordings, while the clearances, the awareness rule and the channel are modelled (see the paper, Sections III and V).

## Layout

| Path | What it is |
|---|---|
| `partyline/engine.py` | Scenario building from tracks, conflict geometry, the base channel simulator |
| `partyline/engine2.py` | Party-line channel: overhearing, stored (delayed) decoding, lossy reports, NACK-only, collisions, CSMA contention |
| `partyline/coding.py` | Scheme registry and XOR/IDNC primitives |
| `awareness.py` | Critical and awareness classes (sector frequency, 60 s default deadline) |
| `schedulers2.py` ... `schedulers5.py` | Unicast, broadcast, IDNC, tiered repair, RLNC baselines, STGC and STGC2 |
| `schedulers6.py` | Published-style IDNC baseline (Sorour and Valaee) |
| `schedulers7.py` | STGC-AD, STGC2 with a rate-adaptive hold time |
| `conflict_traffic.py` | Clearances generated from predicted conflicts on the real tracks |
| `experiments_party.py` | Main experiment runner (one airspace, many schemes) |
| `run_all.sh`, `run_sweep.sh`, `run_sensitivity.sh`, `run_pub.sh`, `run_ext.sh`, `run_final.sh` | Batch runs, three at a time, logs in `~/party_logs` |
| `analyze_*.py` | Pooled analysis with the two-level block bootstrap, writes a summary text file |
| `timing.py` | Scheduler decision time |
| `tests/run_tests.py` | Unit tests of the engine and schemes |

## Setup

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python3 tests/run_tests.py          # expects PASS lines; OpenSky network warnings are harmless

Airspace recordings are stored in `data/partyline.db` (dataset ids 4, 5, 8, 9, 11, 12, 13, 14 in the paper). Ingest your own with
`ingest.py`. The raw OpenSky data is not redistributed here; the result files in `data/` are.

## Reproducing the paper

    zsh reproduce.sh "4 5 8 9 11 12 13 14"

runs, in order: the main study (ideal and 60% lost reports, critical weight 1, 3, 5 and 10), the robustness sweeps, the sensitivity
sweeps, the published-style baseline, the ablations and rate-adaptive hold, and the final extensions (theory check, conflict-driven
clearances, CSMA contention), then each `analyze_*.py`. Every run skips result files that already exist. Results are deterministic:
seeds are fixed (`1000 + window index`).

Typical cost: the main study takes about an hour on a laptop with three parallel jobs. One scheduler decision takes well under a
millisecond (`python3 timing.py 4`).

## Notes

* `*_cls` schemes are class-aware versions of the baselines; `*_noclass` drop the class weights; `stgc_hold0` sends repairs at once.
* A pair withdrawn (superseded) before it is served counts as a miss in the "strict" rates and is excluded in the "excl" rates.
* Critical weight 10 is fixed in the sweeps; the main table chooses it leave-one-airspace-out.
* License: to be added by the authors before release.
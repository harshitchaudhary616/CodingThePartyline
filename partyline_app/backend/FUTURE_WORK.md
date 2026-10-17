# Future-work items of Paper 1: what is implemented, what the data must still say

| # | Item | Status |
|---|------|--------|
| 1 | Calibration with CPDLC / VDL Mode 2 | `calibrate.py` fits the channel model to a recorded log; conservative / severe channel profiles, deadline and clearance-rate sweeps are queued in `run_future.sh all`. No operational log was available, so the paper must still call the channel an abstraction. |
| 2 | Feedback overhead | `engine2` has two sparse-reporting policies (`--fbpolicy 1`: report after a state change or a redundant packet; `--fbpolicy 2 --fbperiod S`: at most one report per S seconds, i.e. piggybacked). `analyze_future.py` prints the report cost at which each policy and each coder pays off. |
| 3 | Strict miss penalty of the hold | `schedulers8.py` (STGC-SH, a per-aircraft supersession-aware hold) is implemented. On synthetic traffic it lies on the same uplinks-versus-strict-miss curve as a plain shorter hold, so it is reported as a neutral result unless the real airspaces show otherwise (section 2 of the summary). |
| 4 | Predictive staleness theory | `belief_theory.py`: a two-state chain per clearance (aircraft really lacks / holds-but-station-unaware) driven by loss p, report loss q and the repeat schedule. Closed form for one pair, schedule-conditioned prediction of the single-gap waste W1. Multi-gap waste (j >= 2) stays bounded by Proposition 1. |
| 5 | Multi-sector scaling, human factors | Sector-size (30/120/240 NM) and clearance-rate (1, 2 per aircraft per minute) sweeps and an awareness-workload proxy (`aware_per_min`). A pilot user study cannot be done in simulation; protocol below. |

## Run (real airspaces; about the same cost as the earlier run_final.sh per configuration)
    cd ~/CodingThePartyLine/partyline_app/backend
    python3 tests/run_tests.py                       # 7 new tests in tests/test_future.py
    zsh run_future.sh "4 5 8 9 11 12 13 14" core     # feedback policies, holds, conflict-driven, theory (8 configurations per airspace)
    zsh run_future.sh "4 5 8 9 11 12 13 14" all      # plus channel profiles, deadlines, sectors, clearance rates (adds 10)
    python3 analyze_future.py 4 5 8 9 11 12 13 14    # writes futsummary.txt; paste it back to update the paper

## Calibrating the channel model
CSV with t_uplink, t_delivered, ok (1/0), optional busy (0..1) and bytes; optionally a second CSV with sent, received for the aircraft reports.
    python3 calibrate.py cpdlc_log.csv --reports acks.csv --out channel_profile.json
It prints the `--loss --airtime --access --bg --fbloss` flags to give run_future.py, and a goodness-of-fit line for the exponential access-delay assumption.

## User-study protocol (not run)
Question: does a party-line awareness display help pilots without raising workload?
Design: within-subject, 12 or more airline pilots, simulated cockpit with a CPDLC display; three conditions: (A) today's addressed CPDLC, (B) party-line display with
all awareness clearances, (C) party-line display filtered to the pilot's own neighbourhood. Replay the recorded OpenSky windows with STGC2 delivery.
Measures: time to notice a conflicting aircraft's clearance, own-ship error rate, NASA-TLX workload, number of ignored messages, subjective usefulness.
Hypotheses: B and C reduce time-to-notice versus A; C does not raise TLX versus A. Needs ethics approval; the awareness-clearance rate per aircraft
(`aware_per_min` in the results) sets the message load the display must carry.

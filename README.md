# Coding the Party Line

Simulator, scripts and per-window result files for "Coding the Party Line: Relevance-Aware, Deadline-Constrained Coded Broadcast of Air Traffic Control Datalink Clearances" (H. Chaudhary, G. K S, N. Sivaranjini).

## Contents
- `partyline_app/backend/` simulator, coders (IDNC, IDNC-cls, STGC2, STGC-AD, STGC-SH, guard variants), experiment drivers and analysis scripts
- `partyline_app/backend/*/data/*.json` per-window result files behind every table
- `FUTURE_WORK.md` protocol for the pilot study and CPDLC calibration

## Data
ADS-B tracks come from the OpenSky Network (https://opensky-network.org) under its terms of use. Raw recordings are not redistributed; fetch them with the OpenSky API or historical database.

## Reproduce
cd partyline_app/backend
python3 tests/run_tests.py
zsh run_future.sh “4 5 8 9 11 12 13 14” all
zsh run_gap.sh “4 5 8 9 11 12 13 14”
python3 analyze_future.py 4 5 8 9 11 12 13 14
python3 analyze_gap.py 4 5 8 9 11 12 13 14
python3 analyze_loo.py 4 5 8 9 11 12 13 14
The clearances and the channel are simulated; see the paper's Limitations section.

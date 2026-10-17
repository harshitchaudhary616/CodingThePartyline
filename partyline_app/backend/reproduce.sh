#!/bin/zsh
# Reruns every experiment and analysis behind the paper. Each step skips result files that already exist.
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh reproduce.sh "4 5 8 9 11 12 13 14"
IDS=${1:-"4 5 8 9 11 12 13 14"}
set -e
zsh run_all.sh "$IDS"            # main study
python3 analyze_all.py ${=IDS}
python3 analyze_all.py ${=IDS} --rep 0.6
zsh run_sweep.sh "$IDS"          # robustness sweeps
python3 analyze_sweep.py ${=IDS}
zsh run_sensitivity.sh "$IDS"    # awareness deadline and sector size
python3 analyze_sensitivity.py ${=IDS}
zsh run_pub.sh "$IDS"            # published-style baseline
python3 analyze_pub.py ${=IDS}
zsh run_ext.sh "$IDS"            # ablations and rate-adaptive hold
python3 analyze_ext.py ${=IDS}
python3 analyze_layers.py ${=IDS}
zsh run_final.sh "$IDS"          # theory check, conflict-driven clearances, CSMA contention
python3 analyze_theory.py ${=IDS}
python3 analyze_final.py ${=IDS}
zsh run_future.sh "$IDS" all    # future-work experiments (sparse reporting, hold, staleness model, channel profiles, scaling)
python3 analyze_future.py ${=IDS}
python3 timing.py ${=IDS[1]}     # scheduler decision time on the first airspace
echo "ALL DONE"

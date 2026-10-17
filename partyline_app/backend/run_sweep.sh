#!/bin/zsh
# Robustness sweeps on the real airspaces (critical weight fixed at 10, loss 0.3):
#   rate  : clearance rate 0.1 / 0.5 / 1.0 per aircraft per minute (default study used 0.25), ideal and 60%-lost reports
#   coll  : uplink collision probability 0.1 / 0.3 (60%-lost reports)
#   nack  : NACK-only feedback, NACK loss 0.1 / 0.3 (silence = delivered)
#   hold  : repair hold time 10 / 20 s instead of 30 s (60%-lost reports)
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_sweep.sh "4 5 8 9 11 12 13 14"
# Logs in ~/party_logs/sweep_*.log. Re-running skips finished files.
SCH="unicast idnc_best idnc_cls stgc stgc2 rlnc_sys"
if [ "$1" = "--one" ]; then          # internal: run one job   --one <id> <tag> <extra experiments_party args...>
  id=$2; tag=$3; shift 3
  python3 experiments_party.py --dataset $id --loss 0.3 --crit-w 10 "$@" --schemes ${=SCH} > ~/party_logs/sweep_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id  file-suffix  extra-args  tag
  f="data/party_dataset$1_loss0.3_A60$2.json"
  [ -f "$f" ] && return
  echo "$1 $4 $3" >> $jobs_file
}
for id in ${=IDS}; do
  for ur in 0.1 0.5 1; do
    add $id "_cw10_ur$ur" "--upd-rate $ur" "ideal_ur$ur"
    add $id "_rep0.6_cw10_ur$ur" "--reports --fbloss 0.6 --upd-rate $ur" "rep_ur$ur"
  done
  for c in 0.1 0.3; do add $id "_rep0.6_cw10_coll$c" "--reports --fbloss 0.6 --coll $c" "coll$c"; done
  for q in 0.1 0.3; do add $id "_nack${q}_cw10" "--reports --nack --fbloss $q" "nack$q"; done
  for h in 10 20; do add $id "_rep0.6_cw10_hold$h" "--reports --fbloss 0.6 --hold $h" "hold$h"; done
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE
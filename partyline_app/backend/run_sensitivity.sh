#!/bin/zsh
# Sensitivity of the conclusions to our own definitions (critical weight 10, loss 0.3):
#   awareness deadline A = 30 s and 120 s   (main study 60 s)
#   sector size 40 NM and 90 NM             (main study 60 NM)
# each with ideal feedback and with 60%-lost reports.
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_sensitivity.sh "4 5 8 9 11 12 13 14"
# Logs in ~/party_logs/sens_*.log. Re-running skips finished files.
SCH="unicast idnc_best idnc_cls stgc stgc2 rlnc_sys"
if [ "$1" = "--one" ]; then          # internal: run one job   --one <id> <tag> <extra experiments_party args...>
  id=$2; tag=$3; shift 3
  python3 experiments_party.py --dataset $id --loss 0.3 --crit-w 10 "$@" --schemes ${=SCH} > ~/party_logs/sens_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id  file-suffix(after loss0.3_)  extra-args  tag
  f="data/party_dataset$1_loss0.3_$2.json"
  [ -f "$f" ] && return
  echo "$1 $4 $3" >> $jobs_file
}
for id in ${=IDS}; do
  for A in 30 120; do
    add $id "A${A}_cw10" "--A $A" "ideal_A$A"
    add $id "A${A}_rep0.6_cw10" "--A $A --reports --fbloss 0.6" "rep_A$A"
  done
  for sec in 40 90; do
    add $id "A60_cw10_sec$sec" "--sector $sec" "ideal_sec$sec"
    add $id "A60_rep0.6_cw10_sec$sec" "--sector $sec --reports --fbloss 0.6" "rep_sec$sec"
  done
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE
#!/bin/zsh
# Final study: every airspace separately, critical weight 1/3/5/10, ideal and lossy-report feedback.
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_all.sh "4 5 8 9 11 12 13 14"
# Runs 3 jobs at a time; logs in ~/party_logs/final_*.log. Re-running skips finished files.
FULL="unicast broadcast_best idnc_hd idnc_best coded_best tiered idnc_tiered rlnc_sys rlnc_group broadcast_cls idnc_cls coded_cls tiered_cls idnc_tiered_cls stgc stgc2 stgc_noclass stgc_hold0"
CWS="stgc stgc2 idnc_cls broadcast_cls coded_cls tiered_cls idnc_tiered_cls"

# one run:  zsh run_all.sh --one <id> <ideal|rep> <cw>
if [ "$1" = "--one" ]; then
  id=$2; mode=$3; cw=$4
  if [ $cw = 3 ]; then sch=$FULL; else sch=$CWS; fi
  extra=""
  [ $mode = rep ] && extra="--reports --fbloss 0.6"
  python3 experiments_party.py --dataset $id --loss 0.3 --crit-w $cw ${=extra} --schemes ${=sch} > ~/party_logs/final_${id}_${mode}_cw${cw}.log 2>&1
  exit
fi

IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
for id in ${=IDS}; do
  for mode in ideal rep; do
    for cw in 3 1 5 10; do
      sfx=""
      [ $mode = rep ] && sfx="_rep0.6"
      [ $cw != 3 ] && sfx="${sfx}_cw${cw}"
      f="data/party_dataset${id}_loss0.3_A60${sfx}.json"
      [ -f "$f" ] && continue
      echo "$id $mode $cw" >> $jobs_file
    done
  done
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh run_all.sh --one
echo ALL DONE
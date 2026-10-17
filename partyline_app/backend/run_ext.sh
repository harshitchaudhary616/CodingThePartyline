#!/bin/zsh
# Extension runs on the real airspaces (critical weight 10, loss 0.3). Existing results are never touched.
#   ablout : idnc_cls stgc2 stgc stgc_noclass stgc_hold0      (ideal and 60%-lost reports)   -> class weights / holding ablations
#   adout  : idnc_cls stgc2 stgc_ad  (rate 0.25 and 1.0, ideal and 60%-lost reports)         -> rate-adaptive hold
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_ext.sh "4 5 8 9 11 12 13 14"
# Logs in ~/party_logs/ext_*.log. Re-running skips finished files.
if [ "$1" = "--one" ]; then          # internal: --one <id> <tag> <outdir> <schemes,comma,separated> <extra args...>
  id=$2; tag=$3; out=$4; sch=${5//,/ }; shift 5
  OUT=$out python3 run_ext.py --dataset $id --loss 0.3 --crit-w 10 "$@" --schemes ${=sch} > ~/party_logs/ext_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs ablout/data adout/data
jobs_file=$(mktemp)
add() {   # id tag outdir schemes file-suffix extra
  [ -f "$3/data/party_dataset$1_loss0.3_A60$5.json" ] && return
  echo "$1 $2 $3 $4 $6" >> $jobs_file
}
ABL="idnc_cls,stgc2,stgc,stgc_noclass,stgc_hold0"
AD="idnc_cls,stgc2,stgc_ad"
for id in ${=IDS}; do
  add $id ideal ablout $ABL "_cw10" "--upd-rate 0.25"
  add $id rep ablout $ABL "_rep0.6_cw10" "--reports --fbloss 0.6"
  add $id ideal adout $AD "_cw10" "--upd-rate 0.25"
  add $id rep adout $AD "_rep0.6_cw10" "--reports --fbloss 0.6"
  add $id ideal_ur1 adout $AD "_cw10_ur1" "--upd-rate 1"
  add $id rep_ur1 adout $AD "_rep0.6_cw10_ur1" "--reports --fbloss 0.6 --upd-rate 1"
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE
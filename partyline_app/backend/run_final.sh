#!/bin/zsh
# Final extension runs on the real airspaces (critical weight 10, loss 0.3). Existing results are never touched.
#   finalout : idnc_cls stgc2 stgc          60% lost reports, default traffic   -> theory check (believed-gap statistics)
#   cfout    : unicast idnc_best idnc_cls stgc stgc2 rlnc_sys   conflict-driven clearances, ideal and 60% lost reports
#   csmaout2 / csmaout6 : idnc_best idnc_cls stgc2   p-persistent CSMA with 2 / 6 competing stations, 60% lost reports
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_final.sh "4 5 8 9 11 12 13 14"
# Logs in ~/party_logs/fin_*.log. Re-running skips finished files.
if [ "$1" = "--one" ]; then          # internal: --one <id> <tag> <outdir> <schemes,comma,separated> <extra args...>
  id=$2; tag=$3; out=$4; sch=${5//,/ }; shift 5
  OUT=$out python3 run_final.py --dataset $id --loss 0.3 --crit-w 10 "$@" --schemes ${=sch} > ~/party_logs/fin_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs finalout/data cfout/data csmaout2/data csmaout6/data
jobs_file=$(mktemp)
add() {   # id tag outdir schemes file-suffix extra
  [ -f "$3/data/party_dataset$1_loss0.3_A60$5.json" ] && return
  echo "$1 $2 $3 $4 $6" >> $jobs_file
}
for id in ${=IDS}; do
  add $id theory finalout "idnc_cls,stgc2,stgc" "_rep0.6_cw10" "--reports --fbloss 0.6"
  add $id cf_ideal cfout "unicast,idnc_best,idnc_cls,stgc,stgc2,rlnc_sys" "_cw10_ur0" "--conflict --upd-rate 0"
  add $id cf_rep cfout "unicast,idnc_best,idnc_cls,stgc,stgc2,rlnc_sys" "_rep0.6_cw10_ur0" "--conflict --upd-rate 0 --reports --fbloss 0.6"
  add $id csma2 csmaout2 "idnc_best,idnc_cls,stgc2" "_rep0.6_cw10" "--reports --fbloss 0.6 --nbg 2 --pp 0.05"
  add $id csma6 csmaout6 "idnc_best,idnc_cls,stgc2" "_rep0.6_cw10" "--reports --fbloss 0.6 --nbg 6 --pp 0.05"
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE
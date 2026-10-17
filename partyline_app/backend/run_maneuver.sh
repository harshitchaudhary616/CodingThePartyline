#!/bin/zsh
# Manoeuvre-derived clearances on the real airspaces (critical weight 10, loss 0.3). New folders only; nothing existing is touched.
#   manout    ideal feedback        manrep   60% of reports lost       manlead60  lead 60 s (60% lost)       manhdg40  stricter detection (60% lost)
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_maneuver.sh "4 5 8 9 11 12 13 14"
if [ "$1" = "--one" ]; then
  id=$2; tag=$3; out=$4; sch=${5//,/ }; shift 5
  OUT=$out python3 run_maneuver.py --dataset $id --loss 0.3 --crit-w 10 --upd-rate 0 "$@" --schemes ${=sch} > ~/party_logs/man_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id tag outdir schemes file-suffix extra...
  local id=$1 tag=$2 out=$3 sch=$4 sfx=$5; shift 5
  mkdir -p $out/data
  [ -f "$out/data/party_dataset${id}_loss0.3_A60${sfx}.json" ] && return
  local line="$id $tag $out $sch $*"
  echo "${line% }" >> $jobs_file          # no trailing blank: xargs -L would join the next line to this one
}
S="unicast,idnc_best,idnc_cls,stgc2"
for id in ${=IDS}; do
  add $id ideal  manout     $S "_cw10_ur0"
  add $id rep    manrep     $S "_rep0.6_cw10_ur0" --reports --fbloss 0.6
  add $id lead60 manlead60  "idnc_cls,stgc2" "_rep0.6_cw10_ur0" --reports --fbloss 0.6 --lead 60
  add $id turn   manhdg40   "idnc_cls,stgc2" "_rep0.6_cw10_ur0" --reports --fbloss 0.6 --hdg 40 --spd 50 --vr 1000
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE

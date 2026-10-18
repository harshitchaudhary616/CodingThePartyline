#!/bin/zsh
# Reviewer checks on the main configuration (60% of reports lost, weight 10). New folders only; nothing existing is touched.
#   valbase     same as the main study, adds the withdrawn-before-deadline miss count            (idnc_cls stgc2 stgc_g2)
#   valexact    exact GF(2^8) decoding instead of the generic-rank rule                          (idnc_cls stgc2)
#   valfb5 / valfb20   every state report occupies the channel for 5 / 20 ms before the next uplink   (unicast idnc_cls stgc2)
#   valvdl2fb   VDL Mode 2 nominal profile with in-band reports of 10 ms                         (unicast idnc_cls stgc2)
#   valsup0 / valsup2  clearances never withdrawn / withdrawn only by a clearance of the same kind   (idnc_cls stgc2 stgc_g2)
#   valcausal   relevance classes from the past track only (constant-velocity projection)        (idnc_cls stgc2 stgc_g2)
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_valid.sh "4 5 8 9 11 12 13 14"
if [ "$1" = "--one" ]; then          # --one <id> <tag> <outdir> <schemes,comma> <extra args...>
  id=$2; tag=$3; out=$4; sch=${5//,/ }; shift 5
  OUT=$out python3 run_valid.py --dataset $id --crit-w 10 --reports --fbloss 0.6 --loss 0.3 "$@" --schemes ${=sch} > ~/party_logs/val_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id tag outdir schemes extra...
  local id=$1 tag=$2 out=$3 sch=$4; shift 4
  mkdir -p $out/data
  [ -f "$out/data/party_dataset${id}_loss0.3_A60_rep0.6_cw10.json" ] && return
  local line="$id $tag $out $sch $*"
  echo "${line% }" >> $jobs_file
}
for id in ${=IDS}; do
  add $id base   valbase   "idnc_cls,stgc2,stgc_g2"
  add $id exact  valexact  "idnc_cls,stgc2" --exact
  add $id fb5    valfb5    "unicast,idnc_cls,stgc2" --fbair 0.005
  add $id fb20   valfb20   "unicast,idnc_cls,stgc2" --fbair 0.02
  add $id vdl2fb valvdl2fb "unicast,idnc_cls,stgc2" --airtime 0.05 --access 0.02 --bg 0.15 --slot 0.0045 --pp 0.609 --nbg 0.3 --fbair 0.01
  add $id sup0   valsup0   "idnc_cls,stgc2,stgc_g2" --supersede 0
  add $id sup2   valsup2   "idnc_cls,stgc2,stgc_g2" --supersede 2
  add $id causal valcausal "idnc_cls,stgc2,stgc_g2" --causal
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE

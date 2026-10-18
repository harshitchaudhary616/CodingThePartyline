#!/bin/zsh
# v10 runs: primary metric on a common demand set, deadline-eligibility sensitivity, end-to-end causal scoring, critical-priority
# STGC2 (stgc_cp) and the combined configuration. New folders only; nothing existing is touched. Main settings: 60% of reports lost, w = 10.
#   v10base    main study                                                                  idnc_cls stgc2 stgc_g2 stgc_cp
#   v10sup2    withdrawn only by a clearance of the same kind
#   v10sup0    never withdrawn
#   v10fb20    reports in band, 20 ms each
#   v10causal  causal classes, also scored against the recorded-future classes
#   v10comb    COMBINED: exact decoding + reports in band 20 ms + same-kind withdrawal + causal classes (default channel)
#   v10combv   COMBINED on the VDL Mode 2 profile with 10 ms reports                       (+ unicast)
#   v10con / v10sev      conservative / severe channel                                     idnc_cls stgc2 stgc_cp
#   v10s120 / v10s240    120 / 240 NM sectors                                              idnc_cls stgc2 stgc_g2 stgc_cp
# Jobs are queued configuration by configuration, so the first folders finish first.
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && caffeinate -i zsh run_v10.sh "4 5 8 9 11 12 13 14"
#         (P=4 zsh run_v10.sh ... runs 4 jobs at a time; default 3)
if [ "$1" = "--one" ]; then          # --one <id> <tag> <outdir> <schemes,comma> <extra args...>
  id=$2; tag=$3; out=$4; sch=${5//,/ }; shift 5
  OUT=$out python3 run_v10.py --dataset $id --crit-w 10 --reports --fbloss 0.6 "$@" --schemes ${=sch} > ~/party_logs/v10_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id tag outdir schemes loss file-suffix extra...
  local id=$1 tag=$2 out=$3 sch=$4 loss=$5 sfx=$6; shift 6
  mkdir -p $out/data
  [ -f "$out/data/party_dataset${id}_loss${loss}_A60${sfx}.json" ] && return
  local line="$id $tag $out $sch --loss $loss $*"
  echo "${line% }" >> $jobs_file          # no trailing blank: xargs -L 1 would join the line with the next one
}
S4="idnc_cls,stgc2,stgc_g2,stgc_cp"
S3="idnc_cls,stgc2,stgc_cp"
VDL="--airtime 0.05 --access 0.02 --bg 0.15 --slot 0.0045 --pp 0.609 --nbg 0.3"
for id in ${=IDS}; do add $id base   v10base   $S4 0.3 "_rep0.6_cw10"; done
for id in ${=IDS}; do add $id sup2   v10sup2   $S4 0.3 "_rep0.6_cw10" --supersede 2; done
for id in ${=IDS}; do add $id causal v10causal $S4 0.3 "_rep0.6_cw10" --causal; done
for id in ${=IDS}; do add $id comb   v10comb   $S4 0.3 "_rep0.6_cw10" --exact --fbair 0.02 --supersede 2 --causal; done
for id in ${=IDS}; do add $id combv  v10combv  "unicast,$S4" 0.3 "_rep0.6_cw10" ${=VDL} --exact --fbair 0.01 --supersede 2 --causal; done
for id in ${=IDS}; do add $id sup0   v10sup0   $S4 0.3 "_rep0.6_cw10" --supersede 0; done
for id in ${=IDS}; do add $id fb20   v10fb20   $S4 0.3 "_rep0.6_cw10" --fbair 0.02; done
for id in ${=IDS}; do add $id con    v10con    $S3 0.4 "_rep0.6_cw10" --airtime 0.8 --access 1.6 --bg 0.5; done
for id in ${=IDS}; do add $id sev    v10sev    $S3 0.5 "_rep0.6_cw10" --airtime 1.0 --access 2.4 --bg 0.6; done
for id in ${=IDS}; do add $id s120   v10s120   $S4 0.3 "_rep0.6_cw10_sec120" --sector 120; done
for id in ${=IDS}; do add $id s240   v10s240   $S4 0.3 "_rep0.6_cw10_sec240" --sector 240; done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P ${P:-3} -L 1 zsh "$0" --one
echo ALL DONE
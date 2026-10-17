#!/bin/zsh
# Closing the critical-class gap and the remaining reviewer points. New folders only; nothing existing is touched.
#   gapcon / gapsev / gapsec240 / gapsec120   idnc_cls stgc2 stgc_g1 stgc_g2 stgc_fb on the conservative channel, the severe channel and 240 / 120 NM sectors (weight 10)
#   filtk3 / filtk5 / filt240k5               awareness limited to the 3 / 5 nearest aircraft (sector 60, 60, 240 NM)
#   vdl2                                      VDL Mode 2 nominal profile from published figures (see analyze_gap.py)
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_gap.sh "4 5 8 9 11 12 13 14"
if [ "$1" = "--one" ]; then          # --one <id> <tag> <outdir> <script> <schemes,comma> <extra args...>
  id=$2; tag=$3; out=$4; script=$5; sch=${6//,/ }; shift 6
  OUT=$out python3 $script --dataset $id --crit-w 10 --reports --fbloss 0.6 "$@" --schemes ${=sch} > ~/party_logs/gap_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id tag outdir script schemes loss file-suffix extra...
  local id=$1 tag=$2 out=$3 script=$4 sch=$5 loss=$6 sfx=$7; shift 7
  mkdir -p $out/data
  [ -f "$out/data/party_dataset${id}_loss${loss}_A60${sfx}.json" ] && return
  echo "$id $tag $out $script $sch --loss $loss $*" >> $jobs_file
}
G="idnc_cls,stgc2,stgc_g1,stgc_g2,stgc_fb"
F="idnc_cls,stgc2"
for id in ${=IDS}; do
  add $id con    gapcon    run_gap.py    $G 0.4 "_rep0.6_cw10"        --airtime 0.8 --access 1.6 --bg 0.5
  add $id sev    gapsev    run_gap.py    $G 0.5 "_rep0.6_cw10"        --airtime 1.0 --access 2.4 --bg 0.6
  add $id sec240 gapsec240 run_gap.py    $G 0.3 "_rep0.6_cw10_sec240" --sector 240
  add $id sec120 gapsec120 run_gap.py    $G 0.3 "_rep0.6_cw10_sec120" --sector 120
  add $id k3     filtk3    run_filter.py $F 0.3 "_rep0.6_cw10"        --aware-k 3
  add $id k5     filtk5    run_filter.py $F 0.3 "_rep0.6_cw10"        --aware-k 5
  add $id k5s240 filt240k5 run_filter.py $F 0.3 "_rep0.6_cw10_sec240" --aware-k 5 --sector 240
  add $id vdl2   vdl2      run_future.py "unicast,idnc_cls,stgc2" 0.3 "_rep0.6_cw10" --airtime 0.05 --access 0.02 --bg 0.15 --slot 0.0045 --pp 0.609 --nbg 0.3
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE

#!/bin/zsh
# Does a larger critical weight remove STGC2's critical-class cost on harsh channels? New folders only; nothing existing is touched.
#   wtcon20 / wtcon40   conservative channel (airtime 0.8 s, access 1.6 s, background 0.5, loss 0.4), critical weight 20 / 40
#   wtsev20 / wtsev40   severe channel       (airtime 1.0 s, access 2.4 s, background 0.6, loss 0.5), critical weight 20 / 40
# The weight-10 results already exist in futchcon / futchsev.  Schemes idnc_cls and stgc2 both use the weight under test.
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_weight.sh "4 5 8 9 11 12 13 14"
if [ "$1" = "--one" ]; then
  id=$2; tag=$3; out=$4; shift 4
  OUT=$out python3 run_future.py --dataset $id --reports --fbloss 0.6 "$@" --schemes idnc_cls stgc2 > ~/party_logs/wt_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id tag outdir loss weight extra...
  local id=$1 tag=$2 out=$3 loss=$4 w=$5; shift 5
  mkdir -p $out/data
  [ -f "$out/data/party_dataset${id}_loss${loss}_A60_rep0.6_cw${w}.json" ] && return
  echo "$id $tag $out --loss $loss --crit-w $w $*" >> $jobs_file
}
for id in ${=IDS}; do
  add $id con20 wtcon20 0.4 20 --airtime 0.8 --access 1.6 --bg 0.5
  add $id con40 wtcon40 0.4 40 --airtime 0.8 --access 1.6 --bg 0.5
  add $id sev20 wtsev20 0.5 20 --airtime 1.0 --access 2.4 --bg 0.6
  add $id sev40 wtsev40 0.5 40 --airtime 1.0 --access 2.4 --bg 0.6
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE

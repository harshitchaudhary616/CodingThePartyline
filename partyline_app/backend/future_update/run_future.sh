#!/bin/zsh
# Future-work experiments on the real airspaces (critical weight 10). Existing results are never touched; each folder is new.
#   futfb0   full reporting, 60% of reports lost: unicast idnc_cls stgc2 stgc_ad stgc_sh      (theory check, STGC-SH, feedback baseline)
#   futfbq3  full reporting, 30% of reports lost                                              (theory check at a second report loss)
#   futfb1   change-triggered reporting                      futfb2 / futfb3: at most one report per 15 s / 30 s (piggybacked)
#   futh10, futh20   repair hold 10 s / 20 s  (strict-miss versus uplink trade-off)           futcf  conflict-driven clearances (STGC-SH check)
#   futchopt/futchcon/futchsev   channel profiles: optimistic / conservative / severe (airtime, access delay, background load, loss)
#   futA30, futA120  awareness deadline 30 s / 120 s       futsec30/120/240  sector (shared-frequency) size       futur1, futur2  clearance rate 1 and 2 per aircraft per minute
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_future.sh "4 5 8 9 11 12 13 14" [core|all]
# "core" (default) = feedback, hold, theory; "all" adds channel profiles, deadlines and scaling.   Logs in ~/party_logs/fut_*.log. Re-running skips finished files.
if [ "$1" = "--one" ]; then          # internal: --one <id> <tag> <outdir> <schemes,comma,separated> <extra args...>
  id=$2; tag=$3; out=$4; sch=${5//,/ }; shift 5
  OUT=$out python3 run_future.py --dataset $id --crit-w 10 "$@" --schemes ${=sch} > ~/party_logs/fut_${out}_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
TIER=${2:-core}
mkdir -p ~/party_logs
jobs_file=$(mktemp)
add() {   # id tag outdir schemes file-suffix(after loss/A) extra...      (loss and A are read from the extra args, defaults 0.3 / 60)
  local id=$1 tag=$2 out=$3 sch=$4 sfx=$5; shift 5
  local loss=0.3 A=60
  [[ "$*" == *"--loss 0.1"* ]] && loss=0.1
  [[ "$*" == *"--loss 0.4"* ]] && loss=0.4
  [[ "$*" == *"--loss 0.5"* ]] && loss=0.5
  [[ "$*" == *"--A 30"* ]] && A=30
  [[ "$*" == *"--A 120"* ]] && A=120
  mkdir -p $out/data
  [ -f "$out/data/party_dataset${id}_loss${loss}_A${A}${sfx}.json" ] && return
  echo "$id $tag $out $sch $*" >> $jobs_file
}
BASE="unicast,idnc_cls,stgc2"
R6="--reports --fbloss 0.6"
for id in ${=IDS}; do
  add $id fb0   futfb0  "unicast,idnc_cls,stgc2,stgc_ad,stgc_sh" "_rep0.6_cw10" $=R6
  add $id fbq3  futfbq3 "idnc_cls,stgc2"                         "_rep0.3_cw10" --reports --fbloss 0.3
  add $id fb1   futfb1  $BASE "_rep0.6_cw10" $=R6 --fbpolicy 1
  add $id fb2   futfb2  $BASE "_rep0.6_cw10" $=R6 --fbpolicy 2 --fbperiod 15
  add $id fb3   futfb3  $BASE "_rep0.6_cw10" $=R6 --fbpolicy 2 --fbperiod 30
  add $id h10   futh10  "idnc_cls,stgc2,stgc_sh" "_rep0.6_cw10_hold10" $=R6 --hold 10
  add $id h20   futh20  "idnc_cls,stgc2,stgc_sh" "_rep0.6_cw10_hold20" $=R6 --hold 20
  add $id cf    futcf   "idnc_cls,stgc2,stgc_sh" "_rep0.6_cw10_ur0" $=R6 --conflict --upd-rate 0
  if [ "$TIER" = "all" ]; then
    add $id chopt futchopt $BASE "_rep0.6_cw10" $=R6 --loss 0.1 --airtime 0.2 --access 0.4 --bg 0.2
    add $id chcon futchcon $BASE "_rep0.6_cw10" $=R6 --loss 0.4 --airtime 0.8 --access 1.6 --bg 0.5
    add $id chsev futchsev $BASE "_rep0.6_cw10" $=R6 --loss 0.5 --airtime 1.0 --access 2.4 --bg 0.6
    add $id A30   futA30   $BASE "_rep0.6_cw10" $=R6 --A 30
    add $id A120  futA120  $BASE "_rep0.6_cw10" $=R6 --A 120
    add $id sec30  futsec30  $BASE "_rep0.6_cw10_sec30"  $=R6 --sector 30
    add $id sec120 futsec120 $BASE "_rep0.6_cw10_sec120" $=R6 --sector 120
    add $id sec240 futsec240 $BASE "_rep0.6_cw10_sec240" $=R6 --sector 240
    add $id ur1 futur1 $BASE "_rep0.6_cw10_ur1" $=R6 --upd-rate 1
    add $id ur2 futur2 $BASE "_rep0.6_cw10_ur2" $=R6 --upd-rate 2
  fi
done
echo "$(wc -l < $jobs_file) runs queued ($TIER)"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE

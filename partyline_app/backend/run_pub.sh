#!/bin/zsh
# Published-style baseline runs: idnc_pub, idnc_best, idnc_cls, stgc2 on the real airspaces, ideal and 60%-lost reports.
# Usage:  cd ~/CodingThePartyLine/partyline_app/backend && zsh run_pub.sh "4 5 8 9 11 12 13 14"
# Results go to pubout/data (existing results are never touched). Logs in ~/party_logs/pub_*.log. Re-running skips finished files.
SCH="idnc_pub idnc_best idnc_cls stgc2"
if [ "$1" = "--one" ]; then          # internal: --one <id> <tag> <extra args...>
  id=$2; tag=$3; shift 3
  python3 run_pub.py --dataset $id --loss 0.3 --crit-w 10 "$@" --schemes ${=SCH} > ~/party_logs/pub_${id}_${tag}.log 2>&1
  exit 0
fi
IDS=${1:-"4 5 8 9 11 12 13 14"}
mkdir -p ~/party_logs pubout/data
jobs_file=$(mktemp)
for id in ${=IDS}; do
  [ -f "pubout/data/party_dataset${id}_loss0.3_A60_cw10.json" ] || echo "$id ideal --upd-rate 0.25" >> $jobs_file
  [ -f "pubout/data/party_dataset${id}_loss0.3_A60_rep0.6_cw10.json" ] || echo "$id rep --reports --fbloss 0.6" >> $jobs_file
done
echo "$(wc -l < $jobs_file) runs queued"
cat $jobs_file | xargs -P 3 -L 1 zsh "$0" --one
echo ALL DONE
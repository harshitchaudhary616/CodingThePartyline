"""run_future.py with the awareness class limited to the K nearest aircraft on the frequency (awareness_k.py).
  OUT=filt5 python3 run_filter.py --dataset 4 --aware-k 5 --sector 240 --crit-w 10 --reports --fbloss 0.6 --schemes idnc_cls stgc2
Each window record keeps aware_per_min (awareness clearances shown per aircraft per minute)."""
import os, sys, runpy
import experiments_party as EP
from awareness_k import with_awareness_k

args = sys.argv[1:]
K = 0
if "--aware-k" in args:
    i = args.index("--aware-k"); K = int(args[i + 1]); del args[i:i + 2]
sys.argv = [sys.argv[0]] + args
EP.with_awareness = lambda scn, A, sector, r_aware: with_awareness_k(scn, A=A, sector=sector, K=K)
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_future.py"), run_name="__main__")

"""Runs experiments_party.py with the published-style baseline idnc_pub added, writing to pubout/data so that no
existing result file is touched.  Same arguments as experiments_party.py, e.g.
  python3 run_pub.py --dataset 4 --loss 0.3 --crit-w 10 --reports --fbloss 0.6 --schemes idnc_pub idnc_best idnc_cls stgc2
"""
import os, sys
import schedulers6
schedulers6.register()
import experiments_party as EP
here = os.path.dirname(os.path.abspath(__file__))
EP.HERE = os.path.join(here, "pubout")
os.makedirs(os.path.join(EP.HERE, "data"), exist_ok=True)
EP.main()
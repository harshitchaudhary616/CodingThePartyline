"""run_future.py with the critical-class guards of schedulers9 registered (stgc_g1, stgc_g2, stgc_fb).
  OUT=gapcon python3 run_gap.py --dataset 4 --loss 0.4 --airtime 0.8 --access 1.6 --bg 0.5 --crit-w 10 --reports --fbloss 0.6 --schemes idnc_cls stgc2 stgc_g1 stgc_g2 stgc_fb"""
import os, sys, runpy
import schedulers5, schedulers9

_orig = schedulers5.register


def register(**kw):
    _orig(**kw)
    schedulers9.register(hold=kw.get("hold", 30.0), crit_w=kw.get("crit_w", 3.0))


schedulers5.register = register
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_future.py"), run_name="__main__")

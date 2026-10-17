"""Runs experiments_party.py with the extra schemes idnc_pub (schedulers6) and stgc_ad (schedulers7) registered, writing to the
folder named by the environment variable OUT (default extout)/data so that no existing result file is touched.  Same arguments
as experiments_party.py, e.g.
  OUT=adout python3 run_ext.py --dataset 4 --loss 0.3 --crit-w 10 --upd-rate 1 --schemes idnc_cls stgc2 stgc_ad
"""
import os, sys
import schedulers6, schedulers7
import experiments_party as EP
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
crit_w = float(args[args.index("--crit-w") + 1]) if "--crit-w" in args else 3.0
hold = float(args[args.index("--hold") + 1]) if "--hold" in args else 30.0
_orig_main = EP.main
schedulers6.register()


def main():
    # experiments_party.main() registers its own schemes first; register ours right after it does, via a thin hook
    import schedulers4, schedulers5
    r4, r5 = schedulers4.register, schedulers5.register
    def r5b(**kw):
        r5(**kw); schedulers7.register(hold=kw.get("hold", hold), crit_w=kw.get("crit_w", crit_w))
    schedulers5.register = r5b
    EP.schedulers5.register = r5b
    EP.HERE = os.path.join(here, os.environ.get("OUT", "extout"))
    os.makedirs(os.path.join(EP.HERE, "data"), exist_ok=True)
    _orig_main()


main()
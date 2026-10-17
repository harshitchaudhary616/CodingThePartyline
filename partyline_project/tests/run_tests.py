import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import test_core
fails = 0
for n in dir(test_core):
    if n.startswith('test_'):
        try: getattr(test_core, n)(); print('PASS', n)
        except Exception: fails += 1; print('FAIL', n); traceback.print_exc()
sys.exit(1 if fails else 0)

import sys, os, traceback, inspect
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..')); sys.path.insert(0, os.path.dirname(__file__))
import test_api, test_engine2, test_future, test_gap, test_valid
fails = 0
for mod in (test_api, test_engine2, test_future, test_gap, test_valid):
    for n, f in sorted(vars(mod).items()):
        if n.startswith('test_') and callable(f):
            try: f(); print('PASS', mod.__name__, n)
            except Exception: fails += 1; print('FAIL', mod.__name__, n); traceback.print_exc()
sys.exit(1 if fails else 0)

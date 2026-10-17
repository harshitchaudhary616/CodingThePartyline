import sys, os, traceback, inspect
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..')); sys.path.insert(0, os.path.dirname(__file__))
import test_api
fails = 0
for n, f in sorted(vars(test_api).items()):
    if n.startswith('test_') and callable(f):
        try: f(); print('PASS', n)
        except Exception: fails += 1; print('FAIL', n); traceback.print_exc()
sys.exit(1 if fails else 0)

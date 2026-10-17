import random
from partyline.coding import *
from partyline.scenario import generate, Params

def test_xor_swap():
    # a at A, b at B; A wants b, B wants a -> 1 coded tx vs 2
    known={'A':{'a'},'B':{'b'}}
    d=[('b','A'),('a','B')]
    assert exact_gf2_length(['a','b'],d,known)==1
    assert greedy_static_length(['a','b'],d,known)==1
    assert lower_bound_mais(d,known)==1

def test_no_side_info_needs_all():
    known={'A':set(),'B':set()}
    d=[('a','A'),('b','B')]
    assert exact_gf2_length(['a','b'],d,known)==2

def test_decode_rule():
    pending={'a':{'B':0.0},'b':{'A':0.0}}
    known={'A':{'a'},'B':{'b'}}
    got=served({'a','b'},pending,known)
    assert set(got)=={('a','B'),('b','A')}
    assert served({'a'},pending,known)==[('a','B')]

def test_greedy_between_bounds_random():
    random.seed(0)
    for _ in range(150):
        n=random.randint(2,5); msgs=[f'm{i}' for i in range(n)]
        recs=[f'r{i}' for i in range(random.randint(2,5))]
        known={r:{m for m in msgs if random.random()<0.4} for r in recs}
        d=[(m,r) for r in recs for m in msgs if m not in known[r] and random.random()<0.6]
        if not d: continue
        g=greedy_static_length(msgs,d,known); e=exact_gf2_length(msgs,d,known)
        lb=lower_bound_mais(d,known)
        assert lb<=e<=g, (lb,e,g)
        assert g<=len({m for m,_ in d})   # never worse than uncoded broadcast

def test_scenario_deterministic():
    a1,c1=generate(Params(seed=3)); a2,c2=generate(Params(seed=3))
    assert [ (c.ac,c.t_issue,sorted(c.demanders)) for c in c1]==[(c.ac,c.t_issue,sorted(c.demanders)) for c in c2]

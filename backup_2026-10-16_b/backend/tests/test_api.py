import json, os, sys, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from app import create_app
from opensky import OpenSkyError, snapshot_rows
from partyline.engine import make_synthetic, from_tracks, run_all, simulate, Scenario, Clearance, clean
from ingest import parse_tracks, synthetic_demo_rows

def client(**kw):
    app = create_app(":memory:" if False else os.path.join('/tmp', f'pl_test_{time.time_ns()}.db'), **kw)
    return app, app.test_client()

def test_health_and_404_405():
    app, c = client()
    assert c.get('/api/health').json['status'] == 'ok'
    assert c.get('/api/nope').status_code == 404
    assert c.post('/api/health').status_code == 405

def test_engine_xor_swap_through_simulator():
    # a at A, b at B; each demands the other's message, both pending at once -> 1 coded tx vs 2 broadcast
    cl = [Clearance(0, 0, 0, 0.0, {1: 100.0}), Clearance(1, 1, 0, 0.0, {0: 100.0})]
    z = np.zeros((2, 4))
    scn = Scenario(['A', 'B'], z, z, z, [0, 0], [3, 3], 'synthetic', (0, 0, 1, 1), (0, 0), {})
    scn.clearances = cl
    r = run_all(scn, {'loss': 0.0}, 1)
    assert r['coded']['n_tx'] == 1 and r['broadcast']['n_tx'] == 2 and r['unicast']['n_tx'] == 2
    assert r['coded']['miss'] == 0.0

def test_validation_rejects_bad_params():
    app, c = client()
    assert c.post('/api/simulate', json={'params': {'rate': 'x'}}).status_code == 400
    assert c.post('/api/simulate', json={'params': {'rate': 99}}).status_code == 400
    assert c.post('/api/simulate', json={'params': {'bogus': 1}}).status_code == 400
    assert c.post('/api/simulate', json={'channel': {'loss': 0.99}}).status_code == 400
    assert c.post('/api/simulate', json={'dataset_id': 999}).status_code == 404

def test_simulate_synthetic_and_replay_stored_run():
    app, c = client()
    r = c.post('/api/simulate', json={'params': {'rate': 1.0, 'dur_min': 15}, 'seed': 2})
    assert r.status_code == 200, r.json
    j = r.json; s = j['summary']['schemes']
    assert s['unicast']['n_tx'] > s['broadcast']['n_tx'] >= s['coded']['n_tx'] > 0
    assert j['playback']['meta']['is_real'] is False
    g = c.get(f"/api/runs/{j['run_id']}").json
    assert g['playback']['schemes']['coded']['n_tx'] == s['coded']['n_tx']
    assert len(c.get('/api/runs').json) == 1

def test_demo_dataset_is_never_labelled_real_and_replays():
    app, c = client()
    d = c.post('/api/datasets/demo').json
    assert d['is_real'] is False and d['source'] == 'synthetic' and d['n_rows'] > 100
    r = c.post('/api/simulate', json={'dataset_id': d['id'], 'seed': 1})
    assert r.status_code == 200, r.json
    assert r.json['playback']['meta']['is_real'] is False and r.json['playback']['kind'] == 'recorded'
    assert 'clearances are simulated' in r.json['playback']['meta']['note']

def test_upload_csv_and_json_and_bad_files():
    app, c = client()
    csv = "time,icao24,callsign,lat,lon,velocity,heading,baroaltitude,onground\n" + "".join(
        f"{1700000000 + 10*k},abc{i},T{i},{13 + 0.01*k + i*0.002},{80 + 0.01*k},200,90,3000,false\n" for i in range(3) for k in range(20))
    r = c.post('/api/datasets/upload?name=t', data=csv, content_type='text/csv')
    assert r.status_code == 201 and r.json['n_rows'] == 60 and r.json['is_real'] is True
    assert c.post('/api/datasets/upload', data='time,foo\n1,2', content_type='text/csv').status_code == 400
    assert c.post('/api/datasets/upload', data='', content_type='text/csv').status_code == 400
    js = json.dumps({'time': 1700000000, 'states': [['abc', 'X', 'C', 1, 1, 80.1, 13.1, 3000, False, 200, 90, 0]]})
    assert c.post('/api/datasets/upload', data=js, content_type='application/json').status_code == 201

def test_snapshot_rows_skips_missing_positions():
    js = {'time': 5, 'states': [['a', 'X ', 'c', 1, 1, None, None, 0, False], ['b', 'Y', 'c', 1, 1, 80.0, 13.0, 3000.0, False]]}
    rows = snapshot_rows(js)
    assert len(rows) == 1 and rows[0][1] == 'b'

def _fake_fetch_factory(fail_first=0):
    state = {'n': 0}
    def fetch(bbox):
        state['n'] += 1
        if state['n'] <= fail_first:
            raise OpenSkyError('HTTP 429 retry-after 5s')
        t = 1_700_000_000 + 10 * state['n']
        return {'time': t, 'states': [[f'ac{i}', f'C{i}', 'X', t, t, 80.0 + 0.01 * state['n'] + 0.002 * i, 13.0 + 0.01 * state['n'], 3000.0, False, 200, 90, 0] for i in range(4)]}
    return fetch

def test_opensky_recording_job_with_retry(monkeypatch=None):
    sleeps = []
    app, c = client(fetch=_fake_fetch_factory(fail_first=2), sleep=lambda s: (sleeps.append(s), time.sleep(0.0)))
    # speed up: minutes tiny; poll loop ends by wall clock so run ~ a second
    import opensky
    r = c.post('/api/datasets/opensky', json={'bbox': [12, 79, 14, 81], 'minutes': 1, 'every': 5})
    assert r.status_code == 202, r.json
    jid, did = r.json['job_id'], r.json['dataset_id']
    # job runs for ~60 s wall clock in the thread; check intermediate progress then stop early
    time.sleep(1.5)
    j = c.get(f'/api/jobs/{jid}').json
    assert j['failures'] == 2 and j['polls'] >= 1 and j['rows'] >= 4
    d = [x for x in c.get('/api/datasets').json if x['id'] == did][0]
    assert d['status'] == 'recording' and d['is_real'] is True
    assert c.post('/api/simulate', json={'dataset_id': did}).status_code == 409   # refuses while recording
    assert max(sleeps) >= 10          # exponential backoff happened

def test_opensky_bbox_validation():
    app, c = client()
    assert c.post('/api/datasets/opensky', json={'bbox': [1, 2]}).status_code == 400
    assert c.post('/api/datasets/opensky', json={'bbox': [14, 79, 12, 81]}).status_code == 400
    assert c.post('/api/datasets/opensky', json={'bbox': [0, 0, 20, 20]}).status_code == 400

def test_opensky_total_failure_marks_failed():
    app, c = client(fetch=_fake_fetch_factory(fail_first=10**6), sleep=lambda s: None)
    r = c.post('/api/datasets/opensky', json={'bbox': [12, 79, 14, 81], 'minutes': 1, 'every': 5})
    time.sleep(1.0)
    j = c.get(f"/api/jobs/{r.json['job_id']}").json
    assert j['state'] == 'failed' and '5 consecutive failures' in j['message']
    d = [x for x in c.get('/api/datasets').json if x['id'] == r.json['dataset_id']][0]
    assert d['status'] == 'failed'

def test_api_key_enforced(monkeypatch=None):
    os.environ['PL_API_KEY'] = 'secret'
    try:
        app, c = client()
        assert c.get('/api/health').status_code == 200
        assert c.get('/api/datasets').status_code == 401
        assert c.get('/api/datasets', headers={'X-API-Key': 'secret'}).status_code == 200
    finally:
        del os.environ['PL_API_KEY']

def test_delete_dataset_cascades():
    app, c = client()
    d = c.post('/api/datasets/demo').json
    assert c.delete(f"/api/datasets/{d['id']}").status_code == 200
    assert c.get('/api/datasets').json == []
    assert c.delete(f"/api/datasets/{d['id']}").status_code == 404

def test_results_bundle():
    app, c = client()
    j = c.get('/api/results').json
    assert 'paired' in j and 'checkpoint' in j

def test_deterministic_runs():
    a = run_all(make_synthetic({'rate': 1.0, 'dur_min': 15}, 5), {}, 9)
    b = run_all(make_synthetic({'rate': 1.0, 'dur_min': 15}, 5), {}, 9)
    assert [a[s]['n_tx'] for s in a] == [b[s]['n_tx'] for s in b]

def test_playback_contract_matches_flutter_models():
    """Keys/types here mirror app/lib/models.dart. Change both together."""
    app, c = client()
    for body in ({'params': {'rate': 1.0, 'dur_min': 15}}, {'dataset_id': c.post('/api/datasets/demo').json['id']}):
        pb = c.post('/api/simulate', json=body).json['playback']
        for k, t in (('dt', (int, float)), ('K', int), ('kind', str), ('bounds', list), ('centre', list), ('r_alert', (int, float)),
                     ('vsep', (int, float)), ('routes', list), ('aircraft', list), ('clearances', list), ('schemes', dict), ('meta', dict)):
            assert isinstance(pb[k], t), k
        assert len(pb['bounds']) == 4 and len(pb['centre']) == 2
        a = pb['aircraft'][0]
        assert set(a) == {'id', 'first', 'x', 'y', 'z'} and len(a['x']) == len(a['y']) == len(a['z'])
        assert all(set(x) == {'id', 'ac', 'v', 't'} for x in pb['clearances'])
        assert set(pb['schemes']) == {'unicast', 'broadcast', 'coded'}
        for L in pb['schemes'].values():
            assert {'n_tx', 'n_pairs', 'miss', 'mean_latency', 'p95_latency', 'txs', 'pairs'} <= set(L)
            for t0, t1, T, q, res in L['txs'][:20]:
                assert t1 > t0 and isinstance(T, list) and isinstance(q, int) and all(len(r) == 3 for r in res)
            for p in L['pairs'][:20]:
                assert len(p) == 6 and p[4] is None or isinstance(p[4], (int, float))
        assert {'source', 'label', 'is_real'} <= set(pb['meta'])
        # message ids used in transmissions must exist in the clearance list
        n = len(pb['clearances'])
        for L in pb['schemes'].values():
            for _, _, T, _, res in L['txs']:
                assert all(0 <= m < n for m in T)

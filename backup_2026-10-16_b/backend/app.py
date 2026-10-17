"""Party Line Lab REST API (Flask).

Run:   python app.py            (dev)      |   gunicorn -w 2 -b 0.0.0.0:8000 'app:create_app()'   (prod)
Env:   PL_DB (sqlite path), PL_API_KEY (if set, required as X-API-Key), PL_CORS (allowed origin, default *)
"""
import json, logging, os, time, threading
import numpy as np
from flask import Flask, jsonify, request, g

import opensky
from db import DB
from ingest import parse_tracks, synthetic_demo_rows
from partyline import engine
from partyline.engine import DT, make_synthetic, from_tracks, run_all, DEFAULTS, CH_DEFAULTS

logging.basicConfig(level=os.environ.get("PL_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("partyline.api")
HERE = os.path.dirname(os.path.abspath(__file__))


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg); self.msg, self.code = msg, code


def _num(v, name, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be a number")
    if not (lo <= v <= hi):
        raise ApiError(f"{name} must be between {lo} and {hi}")
    return v


def build_payload(scn, logs, ch, seed):
    """Everything a client needs to animate the run. Positions rounded; NaN -> null."""
    def arr(a, lo, hi, nd):
        return [None if np.isnan(v) else round(float(v), nd) for v in a[lo:hi + 1]]
    ac = []
    for i in range(scn.n):
        lo, hi = scn.first[i], scn.last[i]
        if hi < lo:
            ac.append(dict(id=scn.ids[i], first=0, x=[], y=[], z=[])); continue
        ac.append(dict(id=scn.ids[i], first=lo, x=arr(scn.X[i], lo, hi, 2), y=arr(scn.Y[i], lo, hi, 2), z=arr(scn.Z[i], lo, hi, 0)))
    schemes = {}
    for s, L in logs.items():
        schemes[s] = dict(
            n_tx=L["n_tx"], n_pairs=L["n_pairs"], miss=round(L["miss"], 5),
            mean_latency=L["mean_latency"], p95_latency=L["p95_latency"],
            txs=[[round(x["t0"], 2), round(x["t1"], 2), x["T"], x["q"], x["res"]] for x in L["txs"]],
            pairs=[[p["m"], p["r"], round(p["tIssue"], 2), round(p["dl"], 2),
                    None if p["tDone"] is None else round(p["tDone"], 2),
                    None if p["tEnd"] is None else round(p["tEnd"], 2)] for p in L["pairs"]])
    return dict(
        dt=DT, K=int(scn.K), kind=scn.kind, bounds=[round(b, 2) for b in scn.bounds], centre=list(scn.centre),
        r_alert=scn.params["r_alert"], vsep=scn.params["vsep"], routes=scn.routes, aircraft=ac,
        clearances=[dict(id=c.cid, ac=c.ac, v=c.version, t=round(c.t, 2)) for c in scn.clearances],
        schemes=schemes, channel=ch, seed=seed)


def create_app(db_path=None, fetch=None, sleep=time.sleep):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    db = DB(db_path or os.environ.get("PL_DB", os.path.join(HERE, "data", "partyline.db")))
    db.mark_stale_jobs()
    app.db = db
    api_key = os.environ.get("PL_API_KEY")
    cors = os.environ.get("PL_CORS", "*")
    sim_lock = threading.Semaphore(int(os.environ.get("PL_MAX_SIMS", "2")))  # bound CPU use

    @app.before_request
    def _auth():
        g.t0 = time.time()
        if request.method == "OPTIONS" or request.path == "/api/health":
            return None
        if api_key and request.headers.get("X-API-Key") != api_key:
            return jsonify(error="invalid or missing X-API-Key"), 401

    @app.after_request
    def _hdr(r):
        r.headers["Access-Control-Allow-Origin"] = cors
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        if (not r.direct_passthrough and r.status_code == 200 and "gzip" in request.headers.get("Accept-Encoding", "")
                and r.mimetype == "application/json" and (r.content_length or 0) > 8192):
            import gzip
            r.set_data(gzip.compress(r.get_data(), 5)); r.headers["Content-Encoding"] = "gzip"; r.headers["Vary"] = "Accept-Encoding"
        return r

    @app.errorhandler(ApiError)
    def _api_err(e): return jsonify(error=e.msg), e.code

    @app.errorhandler(ValueError)
    def _val_err(e): return jsonify(error=str(e)), 400

    @app.errorhandler(404)
    def _nf(e): return jsonify(error="not found"), 404

    @app.errorhandler(413)
    def _big(e): return jsonify(error="file too large (50 MB max)"), 413

    @app.errorhandler(Exception)
    def _boom(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify(error=e.name), e.code
        log.exception("unhandled error")
        return jsonify(error="internal error"), 500

    @app.get("/api/health")
    def health():
        with db.conn() as c:
            c.execute("SELECT 1")
        return jsonify(status="ok", version="1.0", time=time.time(), auth=bool(api_key),
                       opensky_auth=bool(os.environ.get("OPENSKY_CLIENT_ID")))

    # ---------------- datasets
    def _ds(d):
        d = dict(d)
        d["bbox"] = json.loads(d["bbox"]) if d.get("bbox") else None
        d["is_real"] = bool(d["is_real"])
        return d

    @app.get("/api/datasets")
    def datasets(): return jsonify([_ds(d) for d in db.datasets()])

    @app.delete("/api/datasets/<int:did>")
    def del_dataset(did):
        if not db.dataset(did):
            raise ApiError("dataset not found", 404)
        db.delete_dataset(did)
        return jsonify(ok=True)

    @app.post("/api/datasets/demo")
    def demo_dataset():
        did = db.create_dataset("Synthetic demo (not real traffic)", "synthetic", False, note="generated by the simulator")
        db.add_positions(did, synthetic_demo_rows())
        return jsonify(_ds(db.dataset(did))), 201

    @app.post("/api/datasets/upload")
    def upload():
        name = request.args.get("name") or "Uploaded tracks"
        if request.files:
            text = next(iter(request.files.values())).read().decode("utf-8", "replace")
        else:
            text = request.get_data(as_text=True)
        rows = parse_tracks(text)
        is_real = request.args.get("real", "1") != "0"
        did = db.create_dataset(name[:80], "upload", is_real, note="user-supplied file; provenance not verified")
        db.add_positions(did, rows)
        return jsonify(_ds(db.dataset(did))), 201

    @app.post("/api/datasets/opensky")
    def record():
        b = request.get_json(silent=True) or {}
        bb = b.get("bbox")
        if not (isinstance(bb, list) and len(bb) == 4):
            raise ApiError("bbox must be [lamin, lomin, lamax, lomax]")
        lamin, lomin, lamax, lomax = (_num(bb[0], "lamin", -90, 90), _num(bb[1], "lomin", -180, 180), _num(bb[2], "lamax", -90, 90), _num(bb[3], "lomax", -180, 180))
        if lamax <= lamin or lomax <= lomin:
            raise ApiError("bbox max must exceed min")
        if (lamax - lamin) * (lomax - lomin) > 25:
            raise ApiError("bbox too large (max 25 square degrees)")
        minutes = _num(b.get("minutes", 30), "minutes", 1, 180)
        every = _num(b.get("every", 10), "every", 5, 120)
        name = str(b.get("name") or f"OpenSky {time.strftime('%Y-%m-%d %H:%M')}")[:80]
        did, jid, _ = opensky.start_recording(db, name, [lamin, lomin, lamax, lomax], minutes, every, fetch, sleep)
        return jsonify(dataset_id=did, job_id=jid), 202

    @app.get("/api/jobs/<int:jid>")
    def job(jid):
        j = db.job(jid)
        if not j:
            raise ApiError("job not found", 404)
        return jsonify(j)

    # ---------------- simulation
    @app.post("/api/simulate")
    def simulate():
        b = request.get_json(silent=True) or {}
        seed = int(_num(b.get("seed", 3), "seed", 0, 10**6))
        params = engine.clean(b.get("params"), DEFAULTS)
        ch = engine.clean(b.get("channel"), CH_DEFAULTS)
        did = b.get("dataset_id")
        if not sim_lock.acquire(timeout=1):
            raise ApiError("server busy, try again shortly", 503)
        try:
            if did is None:
                scn = make_synthetic(b.get("params"), seed)
                meta = dict(source="synthetic", is_real=False, label="Synthetic traffic")
            else:
                d = db.dataset(int(did))
                if not d:
                    raise ApiError("dataset not found", 404)
                if d["status"] == "recording":
                    raise ApiError("dataset is still recording", 409)
                rows = db.tracks(d["id"], b.get("t_from"), b.get("t_to"))
                if not rows:
                    raise ApiError("dataset has no positions", 409)
                scn = from_tracks(rows, b.get("params"), seed)
                meta = dict(source=d["source"], is_real=bool(d["is_real"]), label=d["name"], dataset_id=d["id"],
                            note="aircraft paths from the dataset; clearances are simulated")
            t0 = time.time()
            logs = run_all(scn, ch, 1000 + seed)
            payload = build_payload(scn, logs, ch, seed)
            payload["meta"] = meta
            summary = dict(meta=meta, n_aircraft=scn.n, n_clearances=len(scn.clearances), compute_s=round(time.time() - t0, 2),
                           schemes={s: dict(n_tx=L["n_tx"], n_pairs=L["n_pairs"], miss=round(L["miss"], 4),
                                            mean_latency=L["mean_latency"], p95_latency=L["p95_latency"]) for s, L in logs.items()})
            bc, cd = summary["schemes"]["broadcast"]["n_tx"], summary["schemes"]["coded"]["n_tx"]
            summary["coded_saving_vs_broadcast_pct"] = round(100 * (bc - cd) / bc, 2) if bc else 0.0
            rid = db.save_run(did, dict(params=params, channel=ch, seed=seed), summary, payload)
        finally:
            sim_lock.release()
        return jsonify(run_id=rid, summary=summary, playback=payload)

    @app.get("/api/runs")
    def runs(): return jsonify(db.runs())

    @app.get("/api/runs/<int:rid>")
    def run_get(rid):
        r = db.run(rid)
        if not r:
            raise ApiError("run not found", 404)
        return jsonify(run_id=rid, summary=r["summary"], playback=r["payload"], params=r["params"])

    @app.get("/api/results")
    def results():
        p = os.path.join(HERE, "data", "results.json")
        if not os.path.exists(p):
            raise ApiError("results not bundled", 404)
        return app.response_class(open(p).read(), mimetype="application/json")

    return app


if __name__ == "__main__":
    create_app().run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")), threaded=True)

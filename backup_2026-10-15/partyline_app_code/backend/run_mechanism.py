"""Start the Party Line Lab API with the mechanism endpoints.

    python3 run_mechanism.py            (same port 8000 as app.py)
"""
import os, threading
from flask import Blueprint, jsonify, request, current_app
from app import create_app, ApiError, _num
import tracer
from partyline import engine
from partyline.engine import make_synthetic, from_tracks, DEFAULTS, CH_DEFAULTS

bp = Blueprint("mechanism", __name__)
_lock = threading.Semaphore(2)


def _ints(v, name):
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be an integer")


@bp.post("/api/mechanism/scenario")
def scenario():
    """Hand-built scenario: {demands:[[m,r,deadline],..], known:{"r":[m,..]}, losses:[[step,r],..], service}"""
    b = request.get_json(silent=True) or {}
    dm = b.get("demands")
    if not isinstance(dm, list) or not (1 <= len(dm) <= 40):
        raise ApiError("demands must be a list of 1..40 [msg, receiver, deadline]")
    demands = []
    for d in dm:
        if not (isinstance(d, list) and len(d) == 3):
            raise ApiError("each demand is [msg, receiver, deadline]")
        demands.append((_ints(d[0], "msg"), _ints(d[1], "receiver"), _num(d[2], "deadline", 0, 1e6)))
    known = {}
    for r, ms in (b.get("known") or {}).items():
        if not isinstance(ms, list) or len(ms) > 40:
            raise ApiError("known sets must be lists")
        known[_ints(r, "receiver")] = [_ints(x, "msg") for x in ms]
    losses = []
    for l in b.get("losses") or []:
        if not (isinstance(l, list) and len(l) == 2):
            raise ApiError("each loss is [step, receiver]")
        losses.append((_ints(l[0], "step"), _ints(l[1], "receiver")))
    service = _num(b.get("service", 1.0), "service", 0.05, 100)
    return jsonify(tracer.all_static(demands, known, losses, service))


@bp.post("/api/mechanism/run")
def run():
    """Trace a full simulation: {dataset_id?, params, channel, seed, limit}"""
    b = request.get_json(silent=True) or {}
    seed = int(_num(b.get("seed", 3), "seed", 0, 10**6))
    ch = engine.clean(b.get("channel"), CH_DEFAULTS)
    limit = int(_num(b.get("limit", 24), "limit", 1, 60))
    did = b.get("dataset_id")
    if not _lock.acquire(timeout=1):
        raise ApiError("server busy, try again shortly", 503)
    try:
        if did is None:
            scn = make_synthetic(b.get("params"), seed)
            meta = dict(source="synthetic", is_real=False, label="Synthetic traffic")
        else:
            d = current_app.db.dataset(int(did))
            if not d:
                raise ApiError("dataset not found", 404)
            if d["status"] == "recording":
                raise ApiError("dataset is still recording", 409)
            rows = current_app.db.tracks(d["id"], b.get("t_from"), b.get("t_to"))
            if not rows:
                raise ApiError("dataset has no positions", 409)
            scn = from_tracks(rows, b.get("params"), seed)
            meta = dict(source=d["source"], is_real=bool(d["is_real"]), label=d["name"], dataset_id=d["id"],
                        note="aircraft paths from the dataset; clearances are simulated")
        out = tracer.run_trace(scn, ch, 1000 + seed, limit)
    finally:
        _lock.release()
    out["meta"] = meta
    out["channel"] = ch
    out["n_aircraft"] = scn.n
    out["n_clearances"] = len(scn.clearances)
    return jsonify(out)


def build():
    app = create_app()
    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    build().run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")), threaded=True)
"""OpenSky Network live ingestion (REST /states/all over a bounding box) with retry/backoff.

Uses only the standard library. Auth is optional: set OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET for OAuth2
client credentials. Always check the current OpenSky terms and API docs; historical (Trino) access is separate.
"""
import json, os, threading, time, urllib.error, urllib.parse, urllib.request, logging

log = logging.getLogger("partyline.opensky")
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API = "https://opensky-network.org/api/states/all"


class OpenSkyError(Exception):
    pass


class Client:
    def __init__(self, timeout=30):
        self.timeout, self._tok, self._exp = timeout, None, 0.0

    def _token(self):
        cid, sec = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
        if not (cid and sec):
            return None
        if self._tok and time.time() < self._exp - 30:
            return self._tok
        data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}).encode()
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=self.timeout) as r:
            js = json.load(r)
        self._tok, self._exp = js["access_token"], time.time() + float(js.get("expires_in", 300))
        return self._tok

    def states(self, bbox):
        q = urllib.parse.urlencode(dict(zip(("lamin", "lomin", "lamax", "lomax"), bbox)))
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "party-line-lab/1.0"})
        tok = self._token()
        if tok:
            req.add_header("Authorization", f"Bearer {tok}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            retry = e.headers.get("X-Rate-Limit-Retry-After-Seconds") if e.headers else None
            raise OpenSkyError(f"HTTP {e.code}" + (f" retry-after {retry}s" if retry else "")) from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise OpenSkyError(str(e)) from e


def snapshot_rows(js):
    """Convert an OpenSky /states/all response to DB rows (ts, icao24, callsign, lat, lon, alt_m, onground)."""
    t = js.get("time")
    out = []
    for s in js.get("states") or []:
        if len(s) < 9 or s[5] is None or s[6] is None:
            continue
        alt = s[7] if s[7] is not None else s[13] if len(s) > 13 else None
        out.append((float(t), s[0], (s[1] or "").strip(), float(s[6]), float(s[5]), alt, int(bool(s[8]))))
    return out


def record(db, dataset_id, job_id, bbox, minutes, every, fetch=None, sleep=time.sleep, stop=None):
    """Poll until `minutes` elapsed. Backs off on errors. Fails the job if no poll ever succeeds."""
    fetch = fetch or Client().states
    end = time.time() + minutes * 60
    polls = fails = rows = consecutive = 0
    backoff = every
    msg = None
    try:
        while time.time() < end and not (stop and stop.is_set()):
            t0 = time.time()
            try:
                js = fetch(bbox)
                n = db.add_positions(dataset_id, snapshot_rows(js))
                rows += n; polls += 1; consecutive = 0; backoff = every
            except OpenSkyError as e:
                fails += 1; consecutive += 1; msg = str(e)
                backoff = min(300.0, max(every, backoff * 2))
                log.warning("poll failed (%s); backing off %.0fs", e, backoff)
            db.update_job(job_id, polls=polls, failures=fails, rows=rows, message=msg)
            if polls == 0 and consecutive >= 5:
                raise OpenSkyError(f"5 consecutive failures before any data: {msg}")
            sleep(max(0.0, (backoff if consecutive else every) - (time.time() - t0)))
        state = "done" if rows else "failed"
        db.update_job(job_id, state=state, finished=time.time(), message=msg if not rows else "completed")
        db.set_dataset_status(dataset_id, "ready" if rows else "failed", None if rows else (msg or "no data received"))
    except Exception as e:  # noqa: BLE001  (job boundary: report, never crash the server)
        log.exception("recording job failed")
        db.update_job(job_id, state="failed", finished=time.time(), message=str(e))
        db.set_dataset_status(dataset_id, "failed" if not rows else "partial", str(e))


def start_recording(db, name, bbox, minutes, every, fetch=None, sleep=time.sleep):
    did = db.create_dataset(name, "opensky", True, bbox, status="recording")
    jid = db.create_job("opensky", did)
    th = threading.Thread(target=record, args=(db, did, jid, bbox, minutes, every, fetch, sleep), daemon=True)
    th.start()
    return did, jid, th

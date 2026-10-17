"""Parsing of uploaded track files (OpenSky CSV / Impala export / /states JSON) and a clearly-labelled
synthetic demo dataset generator."""
import csv, io, json
import numpy as np
from partyline.engine import make_synthetic, DT


def parse_tracks(text: str):
    """-> list of (ts, icao24, callsign, lat, lon, alt_m, onground). Raises ValueError with a helpful message."""
    text = text.strip()
    if not text:
        raise ValueError("empty file")
    rows = []
    if text[0] in "{[":
        try:
            js = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON could not be parsed: {e}")
        for snap in (js if isinstance(js, list) else [js]):
            for s in snap.get("states") or []:
                if len(s) >= 9 and s[5] is not None and s[6] is not None:
                    rows.append((float(snap["time"]), s[0], (s[1] or "").strip(), float(s[6]), float(s[5]),
                                 s[7] if s[7] is not None else (s[13] if len(s) > 13 else None), int(bool(s[8]))))
    else:
        rd = csv.reader(io.StringIO(text))
        head = [h.strip().lower() for h in next(rd)]

        def ix(*names):
            for n in names:
                if n in head:
                    return head.index(n)
            return -1
        it, ii, ia, io_ = ix("time", "timestamp", "lastcontact"), ix("icao24", "icao"), ix("lat", "latitude"), ix("lon", "lng", "longitude")
        if min(it, ii, ia, io_) < 0:
            raise ValueError("CSV needs columns: time, icao24, lat, lon (optional: callsign, baroaltitude, onground)")
        ic, iz, ig = ix("callsign"), ix("baroaltitude", "baro_altitude", "geoaltitude", "altitude"), ix("onground")
        for f in rd:
            try:
                alt = float(f[iz]) if iz >= 0 and f[iz] not in ("", "None", "null") else None
                gnd = int(f[ig].strip().lower() in ("1", "true")) if ig >= 0 else 0
                rows.append((float(f[it]), f[ii].strip(), f[ic].strip() if ic >= 0 else "", float(f[ia]), float(f[io_]), alt, gnd))
            except (ValueError, IndexError):
                continue
    if not rows:
        raise ValueError("no valid position rows found")
    return rows


def synthetic_demo_rows(seed=7, lat0=13.0, lon0=80.2):
    """SYNTHETIC tracks in OpenSky row format. Stored with is_real=0 and source='synthetic' and never presented as real."""
    scn = make_synthetic({"rate": 1.2, "dur_min": 20}, seed)
    kx = 60.0 * np.cos(np.radians(lat0))
    base = 1_760_000_000.0
    rows = []
    for i in range(scn.n):
        for k in range(scn.first[i], scn.last[i] + 1, 2):
            if np.isnan(scn.X[i, k]):
                continue
            rows.append((base + k * DT, f"syn{i:04x}", f"SYN{i}", lat0 + (scn.Y[i, k] - 60) / 60.0,
                         lon0 + (scn.X[i, k] - 60) / kx, 914.4, 0))
    return rows

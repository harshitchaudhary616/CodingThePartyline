# Party Line Lab: backend + Flutter app

Simulates and animates how CPDLC clearances reach the aircraft that need them under three schemes
(addressed, plain broadcast, deadline-aware XOR coding). All results are SIMULATION. Real ADS-B tracks
(OpenSky) supply aircraft paths only; clearances are always simulated, because no public dataset contains them.

```
backend/   Flask REST API + SQLite + OpenSky recorder + simulation engine + tests   (tested: 15 tests pass)
app/       Flutter app (Simulator, Data, Results, Method)                              (NOT compiled or run by the author, see below)
docker-compose.yml, backend/Dockerfile
web_demo_party_line_lab.html   earlier self-contained browser demo
```

## 1. Run the backend
```bash
cd backend
pip install -r requirements.txt
python tests/run_tests.py          # 15 tests
python app.py                      # http://localhost:8000
# or: docker compose up --build    (from this folder)
```
Environment: `PL_DB` (sqlite path), `PL_API_KEY` (require `X-API-Key`), `OPENSKY_CLIENT_ID/SECRET` (optional OAuth2),
`PL_MAX_SIMS` (concurrent simulations, default 2), `PL_CORS` (allowed origin, default `*`; set it in production).

### API
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET/POST/DELETE | `/api/datasets`, `/api/datasets/demo`, `/api/datasets/upload?name=`, `/api/datasets/opensky`, `/api/datasets/<id>` | list, synthetic demo file, import CSV/JSON, record from OpenSky (background job), delete |
| GET | `/api/jobs/<id>` | recording progress (polls, failures, rows) |
| POST | `/api/simulate` | `{dataset_id?, params, channel, seed}` returns summary + full playback |
| GET | `/api/runs`, `/api/runs/<id>` | stored runs |
| GET | `/api/results` | bundled 20-seed results |

Reliability built in: input validation with hard limits, JSON errors everywhere, bounded concurrent simulations (503 when busy),
50 MB upload limit, SQLite WAL, OpenSky retry with exponential backoff and a job that fails cleanly after 5 straight failures,
interrupted recordings marked `partial` after a restart, gzip responses, optional API key, health check.

## 2. Get REAL data
1. Create an OpenSky account (academic terms apply; read their current terms).
2. Start the backend on a machine with internet access.
3. In the app: Data tab, enter a bounding box (default around Chennai) and minutes, Start recording. Or:
```bash
curl -X POST localhost:8000/api/datasets/opensky -H 'content-type: application/json' \
  -d '{"bbox":[12.0,79.3,14.0,81.0],"minutes":45,"name":"Chennai 45 min"}'
```
4. When the dataset is `ready`, select it and press Simulate. The radar then shows recorded paths with simulated clearances.
Datasets are labelled REAL only when recorded from OpenSky (or imported with `real=1`); the synthetic demo file is always labelled SYNTHETIC.

## 3. Run the Flutter app
Requires the Flutter SDK (3.22 or newer).
```bash
cd app
flutter create .            # generates android/ios/web/desktop folders; keeps lib/ and pubspec.yaml
flutter pub get
flutter test                # model parsing tests
flutter run
```
Server address: Android emulator `http://10.0.2.2:8000`, iOS simulator/desktop `http://localhost:8000`, a phone `http://<your-LAN-IP>:8000`.
Plain `http://` needs `android:usesCleartextTraffic="true"` in `AndroidManifest.xml` and an App Transport Security exception on iOS for development;
use HTTPS behind a reverse proxy for anything real.

## Honest status
* Backend: fully exercised here (unit, API and contract tests, plus a live HTTP smoke test).
* OpenSky ingestion: tested with a simulated OpenSky client including 429 failures. A live OpenSky call could not be made from the build sandbox (network blocked), so first real use is the first real test.
* Flutter app: written against the tested API contract but the author's environment had no Flutter or Dart toolchain, so it has NOT been compiled. Expect to fix a few compile errors on first build; send them back and they get fixed quickly.
* Science: coded transmission saves 0.3% to 3.4% of transmissions versus plain broadcast in the 20-seed runs, and the gain grows with load and loss. It is not a large effect, and nothing here is operational evidence.

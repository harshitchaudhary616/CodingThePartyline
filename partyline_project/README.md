# Coding the Party Line — implementation package

Simulation code for the locked proposal (deadline-constrained index coding for CPDLC clearance
dissemination). Everything here is **simulation on synthetic geometries**; nothing is operational evidence.

## Layout
| File | Role |
|---|---|
| `partyline/scenario.py` | Sector, aircraft, versioned clearances, relevance (proximity/shared resource within horizon H), per-pair deadlines |
| `partyline/coding.py` | Decode rule, schedulers (`unicast`, `broadcast`, `coded` deadline-aware greedy XOR), exact GF(2) linear solver (<=5 msgs), MAIS lower bound |
| `partyline/sim.py` | Event-driven serial channel (airtime + exponential access delay, background load, erasures), metrics |
| `run_experiments.py` | Checkpoint + sweeps (load, loss, horizon, background load, margin) -> `results/*.csv` |
| `bluesky_export.py` | Exports scenario to BlueSky `.scn` for independent re-simulation (**untested**, see file header) |
| `tests/run_tests.py` | Unit tests (XOR swap example, decode rule, greedy between bounds on 150 random instances, determinism) |

Run: `python3 tests/run_tests.py` then `python3 run_experiments.py quick` (or without `quick` for 20 seeds).

## Leakage / fairness rules enforced in code
* Receivers only know their own clearance (initial unicast, identical for all schemes, not counted) plus messages they actually decoded.
* Relevance/deadlines come from the controller's plan, never used as side information.
* All schemes see the same scenario, same channel parameters, same pair universe; superseded, expired and undelivered pairs all count as not met.

## Plan (maps to proposal Section 4)
1. **Done here:** model + baselines + exact/greedy/lower-bound + checkpoint.
2. **Checkpoint (done, see Findings):** do existing methods already solve the case?
3. Independent clearance generation: run `bluesky_export.py` output in BlueSky, log clearances and executed trajectories, replace `scenario.generate`. Needs BlueSky installed locally.
4. Real traffic geometry: request OpenSky research access (VIT email), load a sector's recorded tracks as aircraft paths; keep clearances simulated.
5. Statistics: 20+ seeds, 95% CIs (already in CSVs), sensitivity sweeps, ablation of deadline weighting.
6. Only if a gain exists: derive bound/construction for the regime where it exists; compare with cycle codes / single-uniprior codes.
7. Write-up with the limitations in the proposal (simulation only, no pilot-awareness claim).

## Findings so far (must be read before writing any paper)
See `results/` and the delivery message. In the current model **greedy XOR coding gives essentially no gain over plain uncoded broadcast** (checkpoint: 3.57 vs 3.64 transmissions per snapshot; sweeps within ~0-3%). Plain broadcast already restores the party line, and coding needs several messages pending at once with matching side information, which the thin side information (own clearance only) and underloaded queue rarely provide.

### Full run (20 seeds, `results/*.csv`)
* Checkpoint, 406 static snapshots: uncoded broadcast 3.70 tx, greedy XOR 3.66, **exact optimal scalar linear code 3.65** (greedy = exact in 99.3%). So even optimal coding saves ~1.4% here.
* Sweeps: coded vs uncoded broadcast saves -0.3% to 2.0% transmissions (largest at heaviest load / 30% loss); miss rates equal within 0.1 pt.
* Repeated unicast (what CPDLC does today, extended to all relevant aircraft) needs 4-5x more transmissions and collapses under load, but that is the comparison against *addressing*, not against *coding*.
* ~32-38% "misses" for every scheme are mostly infeasible deadlines (conflict already inside the margin at issue time) - a modelling artefact to separate out before reporting.

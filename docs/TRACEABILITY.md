# Article methods and executable evidence

The paper describes a synthetic computational experiment. The code does not control a physical data diode or diagnose a measured pump. The pump is an illustrative application scenario.

| Article claim or component | Implementation | Independent evidence |
| --- | --- | --- |
| Coherent / mixed / ambiguous / out of model verdicts | `study/model/run_model.py:monitor`, `study/simulation/run_simulation.py:monitor` | Enumerated origin explanations; `tests/test_model_contract.py` |
| Repeated equal values can conceal mixing | Values-only monitor and repeated diagonal source catalogue | Finite model enumeration and constant-source regression test |
| Whole-object R1 preserves one capture | `simulate` installs `ox` and `oy` together | Exact sorted-arrival reconstruction for every read; zero-delay, loss and reset controls |
| 12 conditions, 40 seed indices, 960 mode runs | `conditions`, `main`, keyed RNG streams | Run identities, counters and independent source reconstruction |
| Loss, delayed arrival, reset/ready/read ordering | `simulate` event heap | `audit_evidence.py` reconstructs sorted arrivals and checks all 3,840,000 read tuples directly |
| Mixing and coverage in Tables 6 and 7 | `run_metrics.csv` | Exact integer-count ratios checked against 48 Word table cells |
| Bootstrap summaries and paired contrasts | `aggregate`, `aggregate_lags` | Existing independent audit checks 372 means, 132 selected intervals and 60 paired intervals |
| Figures 1 through 6 | Embedded PNG artwork in the Word manuscript | Exact byte equality with `manuscript/figures/`; numeric rendering is outside the runner |
| Full numerical reproduction | `reproduce.py --full` | 29 prior numeric files removed before regeneration; new CSV/JSON and decompressed log compared with frozen reference |

`reproduce.py --verify-only` checks supplied evidence and reconstructs events, but does not regenerate the simulator's outputs. `--full` also regenerates numerical results. Both modes require Python 3.10 or later and only its standard library. The clean-environment audit records the actual interpreter used; other Python/platform combinations are not asserted to have been tested.

Figure provenance: the original computational distribution contained an earlier layout of Figures 3 and 6. Those originals remain under `study/figures/` to preserve source hashes. The current article's improved artwork is exported exactly under `manuscript/figures/`. These exports do not claim that the runner redraws the graphs from CSV.

The original `study/` programs and raw reference results are retained unchanged. The deeper audit strengthens the reproduction runner and connects its evidence to the manuscript; it does not introduce new industrial measurements or alter the experiment's reported counts.

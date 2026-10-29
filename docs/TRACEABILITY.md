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
| Figures 1 through 6 | `plot_figures.py` reads analytical formulas and frozen simulation CSVs | `audit_plots.py` independently checks plotted values; exact PNG equality with Word is also checked |
| Full numerical reproduction | `reproduce.py --full` | 29 prior numeric files removed before regeneration; new CSV/JSON and decompressed log compared with frozen reference |

`reproduce.py --verify-only` checks supplied evidence and reconstructs events, but does not regenerate the simulator's outputs. `--full` also regenerates numerical results. Both modes require Python 3.10 or later and only its standard library. The clean-environment audit records the actual interpreter used; other Python/platform combinations are not asserted to have been tested.

Figure provenance: original computational-package images remain unchanged under `study/figures/`. The submission figures have been redrawn in a similar style at 600 dpi using `plot_figures.py`. The current Word images and plotting values are under `manuscript/figures/`. Figure 1 is a contract schematic; Figure 2 uses analytical expressions; Figures 3–6 use the same simulation summaries and selected trace. The separate plot audit verifies those inputs and recorded values. Raster bytes may depend on font/library versions, so cross-platform reproduction requires matching scientific values rather than identical PNG bytes.

The original `study/` programs and raw reference results are retained unchanged. The deeper audit strengthens the reproduction runner and connects its evidence to the manuscript; it does not introduce new industrial measurements or alter the experiment's reported counts.

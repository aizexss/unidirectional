# Snapshot coherence in unidirectional industrial telemetry

Companion code and synthetic data for **Verifying State Snapshot Coherence in Unidirectional Industrial Telemetry**, by Aibar Ibragimov, Leila Rzayeva and Laura Aldasheva.

This public repository contains the source code, synthetic data and manuscript. The publication version is tagged `article1-submission-20261030-r2`. No account or access request is needed to download the materials.

## Run the study

The verified environment is Python 3.12.14 on Windows. Use that interpreter to reproduce the frozen numerical files. The runner supports Python 3.10 syntax, but other interpreter versions have not been validated for identical floating-point output. The computations and runner need only the standard library; no device, API key, online service or extra package is required.

```sh
python reproduce.py --verify-only
```

This verifies file hashes, reruns finite and theory checks, independently reconstructs all 3,840,000 saved reads, and checks the principal results against the manuscript. It does **not** rerun the simulator.

```sh
python reproduce.py --full
```

This additionally removes all 29 copied numeric output files from a temporary study copy, regenerates the simulation and bootstrap analysis, then compares newly created outputs and decompressed readings with the reference. A generator that fails to create an expected file causes FAIL. Saved evidence under `study/` is never overwritten. The last completed run replaces the reports.

## Understand the output

The terminal prints each numbered stage, its PASS/FAIL status, the main percentages, and the report location. Exit status is 0 for success and 1 for failed verification; invalid CLI arguments return 2.

- `reports/RESULTS.md` is the readable result report, with denominators and scope.
- `reports/RESULTS_RU.md` is the Russian result report.
- `reports/verification_summary.json` contains the same result and check status in structured form.
- `reports/*.log` contains the detailed output of each stage after a local run.
- `MANIFEST.json` and `SHA256SUMS.txt` fix the distributed evidence files.
- `study/SOURCE_MANIFEST.json` preserves the original computational distribution's file identities.

Key expected results: 12 conditions; 40 independent replicate indices per condition; 960 mode runs; 4,000 scheduled reads per mode run; 3,840,000 reads total. In C05 (5% independent message loss, no receiver restart, alpha 0.50), separate publication R0 mixes origins in 62.144375% of reads despite 100% complete-state availability. Whole-object R1 has zero mixed reads under the stated atomicity and origin-binding contract.

All timings, losses and source values are synthetic. Shared random inputs couple conditions, so the 480 condition-specific pairs are not mutually independent. The 3.84 million reads are temporally dependent observations, not independent replications. The model does not measure physical-device performance or normalize the modes to equal bytes.

## Files

| Location | Content |
| --- | --- |
| `manuscript/` | Research article and its six figure images |
| `study/model/` | Exact finite model, schedule enumeration and negative controls |
| `study/theory/` | Independent finite-count, partition and Markov checks |
| `study/graph_checks.py`, `study/graph_validation/` | Equality-evidence graph enumeration |
| `study/simulation/run_simulation.py` | Synthetic event simulator and bootstrap analysis |
| `study/simulation/source_histories.csv` | Offline reference source sequences, hidden from the tested monitors |
| `study/simulation/readings.csv.gz` | Full compressed scheduled-read log |
| `study/simulation/run_metrics.csv` | One record per condition, seed and mode |
| `study/simulation/aggregate_metrics.csv` | Means and pointwise whole-run bootstrap intervals |
| `study/simulation/paired_contrasts.csv` | Paired R0 minus R1 contrasts |
| `study/simulation/validate_reading_log.py` | Independent streamed reconstruction |
| `study/audit_study/audit_independent.py` | Independent sorted-arrival reconstruction and interval checks |
| `study/figures/` | Original computational-package figure exports retained unchanged |
| `manuscript/figures/` | Exact six figure images embedded in the current Word article |
| `audit_evidence.py` | Independent comparison of every logged read with the scheduled event timeline, 48 numeric table cells and exact manuscript artwork |

The runner verifies the supplied figure files. A separate plotting command redraws all six figures; the Word layout is checked separately. The industrial pump scenario is an illustrative application example, not an additional physical experiment or simulation dataset.

## Redraw and check the figures

The optional plotting environment was tested with Python 3.12 on Windows. Install its packages in a separate virtual environment:

```sh
python -m pip install -r requirements-figures.txt
python plot_figures.py
python audit_plots.py reports/figures
```

The plotting command writes six 600 dpi PNGs, six JPGs and `plot_evidence.json` under `reports/figures/`. It reads analytical expressions and frozen CSV files; it does not rerun the simulator or alter the source data. The independent plot audit checks 402 analytical curve points, run-count shares, lag and age summaries, and all 480 selected restart readings. Missing ages remain gaps. The reference plotting values and images are under `manuscript/figures/`.

The article uses Times New Roman. If that font is unavailable, explicitly select an installed font, for example `python plot_figures.py --font "DejaVu Serif"`. Numerical values are unchanged; font metrics and raster appearance can differ between environments. Fonts and plotting libraries are not redistributed in this repository. The numerical reproduction commands above still need only Python's standard library.

Run the runner's regression tests with `python -m unittest discover -s tests -v`.

The deeper audit checks every `(condition, seed, mode, read time, online status, x origin, y origin)` tuple against independently sorted arrivals. It rejects missing/extra reads, timestamp duplicates and wrong origins even if aggregate percentages would coincide. It also checks the 250–280-word abstract, 20 references in first-citation order and the three author identities and ORCID checksums. `docs/TRACEABILITY.md` maps article claims to the code and evidence. `reports/verification_summary.json` records the latest verification run.

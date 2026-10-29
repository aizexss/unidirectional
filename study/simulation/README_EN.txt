EXECUTED SYNTHETIC TELEMETRY SIMULATION

This package reports a discrete-event model, not a hardware experiment. All
times, delay and loss parameters are declared synthetic assumptions. None is
calibrated to AIMI DataDiode or to a physical industrial installation.

REPRODUCTION
Use Python 3.10 or later; no packages outside the standard library are needed.

    python run_simulation.py

The script regenerates CSV, JSON and the gzip reading log beside itself. Source
and analysis use deterministic SHA-256-keyed random streams. Gzip metadata can
contain its creation time; compare decompressed readings for exact reproduction.
CSV and JSON numerical outputs are deterministic. SHA256SUMS.txt records the
current artifact, rather than asserting equality of gzip metadata across runs.

DESIGN AND UNITS
There are 40 independent paired seeds in each of 12 prespecified conditions:
  C01/C02/C03: alpha=.05 and no loss / iid5% / correlated burst loss.
  C04/C05/C06: alpha=.50 and the same three loss settings.
  C07/C08/C09: alpha=.95 and the same three loss settings.
  C10: alpha=.50, iid5%, receiver restart with cleared state.
  C11: alpha=.50, iid5%, receiver restart with preserved state.
  C12: alpha=.50, burst loss, receiver restart with cleared state.

The same 40 seed indices and common random inputs are reused across condition
cells. Thus 480 condition-specific paired executions are not 480 mutually
independent pairs. The inferential repetition count is 40 within a condition.
Cross-condition comparisons must retain the common-seed blocking.

Each seed generates a stationary symmetric binary Markov source. Its initial
value is a fair bit and each next generation flips with probability alpha.
Alpha=.5 is an iid fair binary source. Both fields of a source snapshot have
that generation's value. Source identities1..1200 are unique within one run;
epoch changes at the source are not simulated.

One synthetic millisecond is the event-clock unit. A snapshot is generated
every20ms from0 through23980ms. The total horizon is24s. The first4s are warmup;
the20s evaluation uses4000 atomic reads at a5ms interval. A seeded phase in
0..4ms offsets the read grid and is shared by the paired modes.

R0 sends two field records per generation and replaces each received field
together with its bound origin. R1 sends one whole object and publishes both
fields with one origin atomically. Each message has an independent integer
uniform delay in0..40ms. These are distinct representations with different
message counts; the study is not a bandwidth-normalized transport comparison.

Each main paired run shares its source history and burst environment. Delays
and iid loss use separate keyed mode/component streams. Per-message draws are
assigned even when a condition discards a message, preserving common random
numbers across channel-factor conditions. None of these random streams or the
selection of delivered origins depends on the source values.

The iid channel independently drops each message with probability.05. The
burst channel uses a stationary two-state chain indexed by source generation:
  P(bad -> good)=.1; P(good -> bad)=.05*.1/.95.
The stationary bad probability is.05; the mean bad run is10 generations or
200ms. A bad generation drops both R0 fields and the R1 object. Thus the burst
environment is shared across the pair. Realized loss need not equal5% in any
finite run. Each message's attempted/lost/delivered/receiver-dropped/pending
counts are recorded separately; late pending messages are not called losses.
Loss fractions use attempted emissions over the full 24 s run, including
warmup. State shares instead use the 20 s evaluation interval. These are
different observational units and denominators.

RESTART AND EVENT ORDER
The receiver is down on[12000,12200)ms. Its source and independent observer
continue. Clear removes both stored fields at reset. Preserve retains their
value-origin pairs; it does not promise freshness or common provenance in R0.
Pending arrivals keep their scheduled times. Arrivals during downtime are
discarded, while arrivals at or after ready are accepted. A read during downtime
is unavailable even if memory was preserved.

At one timestamp, reset/ready is processed first, every arrival second, and
the atomic read last. R0 x/y writes at one timestamp therefore complete before
that read. The zero-delay control tests this boundary and produces no artificial
between-event mixing. Main runs have no duplicated transmissions; separate
finite-model work covers duplicates. No queue service rate or receiver CPU is
modeled.

TRUTH, OBSERVERS AND METRICS
The reference classifies an online complete read as coherent iff both retained
origins are equal, otherwise mixed. An offline or incomplete read is unavailable.
The monitor does not access the source history. It receives only its allowed
projection and the public catalogue{(0,0),(1,1)}:
  V: values and presence; equal values ambiguous, unequal values mixed.
  I: values and truthful identifiers bound to each field.
  G: trusted same-origin grouping for R1; no grouping evidence for R0.
G is a conditional interpretation profile, not an independent detector of
incorrect grouping. I/G binding truth is an assumption. Zero conclusive errors
checks the implementation under that assumption and is not a security estimate.

All slot shares use all4000 planned evaluation reads as denominator. These
include actual mixed/coherent/unavailable shares, conclusive coverage, hidden
mixed states and the availability of a fresh coherent state. Complete share is
coherent plus mixed. Conditional detector success uses actual mixed reads as
its denominator. Undefined fractions are left empty, including R1 V's fraction
of conclusive errors when it makes no conclusive decisions.

A naive catalogue-membership rule falsely calls an equal-valued mixed state
coherent. Its false-coherent count equals hidden mixing for this catalogue;
the program verifies that equality without treating it as a universal result.

State age is calculated ONLY for available coherent state as read time minus
the generation time of its single origin. Mixed and unavailable observations
have no state-age value. Fresh coherent availability counts coherent reads with
age<=100ms, divided by all reads;100ms is a declared synthetic threshold, not a
plant safety requirement. A coherent old object is not relabeled fresh merely
because a new copy is received. Per-run mean/p95 age are conditional on coherent
availability and must be reported with the all-slot availability metric.

ANALYTICAL VALIDATION
For distinct selected source generations separated by lag k, the stationary
symmetric Markov source predicts detection probability

    d_alpha(k)=[1-(1-2*alpha)**k]/2.

Origin selection is value-independent by construction, so this predicts the
conditional chance that a mixed pair has different values. lag_validation.csv
compares it with actual mixed observations. A second transition recurrence
independently verifies the formula. Formula d=.5 is specific to alpha=.5; short
lags in a slowly changing process can conceal far more actual mixing.

INDEPENDENCE AND UNCERTAINTY
The independent repetition unit is a complete seeded pair, not a read, message
or repeated state. aggregate_metrics.csv gives the mean of per-run metrics and
a2000-replicate whole-run percentile bootstrap interval. paired_contrasts.csv
resamples complete paired differences R0 minus R1. lag_validation.csv resamples
whole runs and recomputes the pooled detection ratio at each lag. Each interval
is pointwise and descriptive; no multiplicity correction or confirmatory
hypothesis test is claimed. All run-level results are available for inspection.
Condition-specific resampling streams can give slightly different interval
endpoints for identical point data across source-value factors. This is Monte
Carlo variation in the interval computation, not a source-value effect.

The primary model contrast is the paired all-slot actual mixed share, interpreted
with completeness and fresh coherent availability. Zero mixing from dropping
all data is not improvement; the all-loss control demonstrates zero coverage.
Main R1 zero mixing follows from its construction and is not empirical evidence
that an untested physical implementation satisfies the same contract.

FILES
run_simulation.py        self-contained generator, simulator, metrics and checks
results.json            complete settings, condition list and verification totals
source_histories.csv     every seeded source history used in main runs
readings.csv.gz          all evaluation reads with origins and online status
run_metrics.csv          raw counts and derived metrics for all960 mode runs
aggregate_metrics.csv    means and whole-run bootstrap intervals
paired_contrasts.csv     paired R0 minus R1 effects and bootstrap intervals
lag_counts_per_run.csv   per-run lag counts and detection counts
lag_validation.csv       pooled lag validation and cluster-bootstrap intervals
sample_traces.csv        full slot traces for seed0 in C03,C05,C06,C10, both modes
restart_diagnostic.csv   deterministic cleared vs preserved memory counterexample
verification_controls.csv deterministic zero-delay and all-loss checks
SHA256SUMS.txt           hashes for the current artifact

readings.csv.gz can be independently reanalyzed using source_histories.csv:
online=0 means unavailable; online=1 with either origin0 means incomplete;
otherwise equal origins mean coherent and unequal origins mean mixed. Values
come from that origin's indexed source history. This reference reconstruction
does not grant the restricted monitor access to the private source history.

The deterministic restart diagnostic uses a1s generation period and zero delay.
At12200ms, clear is unavailable, whereas preserve exposes a coherent object
generated at11000ms with age1200ms. This illustrates why completeness and age
must be evaluated separately; it is not a timing estimate for an actual receiver.

LIMITATIONS
Synthetic timings and losses; binary diagonal source; one receiver reset;
no source-epoch restart, adversary, cryptography, finite-capacity queue, packet
fragmentation, byte-normalized cost, wall-clock synchronization error, hardware
calibration or physical isolation test. The model proves or demonstrates only
the stated contracts and their conditional observational consequences.

# MYA — Dense team-possession inference

Ali ABOUHACHIM-ALAMI · Youssef BENADDI · Maxime BENDAVID
More Than a Hack 2027, Phase 1 — frozen delivery, 29 October 2026

## Approach and output

Our submission assigns H (Barcelona), A (Athletic), D (dead ball) or X
(outside the evaluated timeline, or abstention) to each of the 199,319 frames
of the supplied tactical video. This is offline tracking-based inference,
not a video computer-vision model. The final CSV is `submissions/final/MYA.csv`.

We use three regularized logistic observation heads followed by exact Viterbi
decoding independently within each half. A lightweight CPU pipeline was chosen
because the supplied tracking already provides ball/player coordinates, while
missing observations and fragmented identities make temporal consistency and
careful validation more useful than immediately adding a visual network.

The final model is the candidate selected in milestone 6: the complete feature
family, static temporal costs, H/A switching multiplier 1 and dead-ball switching
multiplier 2. The latter scales changes into and out of D, not its self-transition.
No parameters are adjusted after the final external test.

## Assets used and discarded

Final inference requires only `tactical/BAR-ATH_tactical_atd.txt` and its ATD XML.
The XML supplies slot-to-team mapping, timing and units. Normalized x/y are
converted to metres using the competition pitch dimensions, 105.3 × 68 m.
ATD frame IDs are converted to zero-based video frames with the validated
frame-ID-minus-one convention. The delivered scalar speed is not used: its XML
unit differs from the prose documentation. Velocities are derived from x/y within
valid fragments, without bridging gaps, period boundaries or implausible links.

The tactical video is not decoded. Smart Tagging and homography were inspected
and remain available in the exploratory notebook, but neither enters the final
logistic design or static decoder. TV tracking/video, manual corrections,
interpolated ball positions, visual detectors, pitch-control models and deep
sequence models are not used in the final submission. Anonymous slots are not
assumed to be stable player identities or jersey numbers. Nearby duplicate tracks
receive symmetric weights instead of being counted as independent players.

The official five-minute public annotations were used only for earlier fixed
pipeline diagnostics, never for training, calibration, hyperparameter tuning or
candidate selection. Milestones 6 and 7 do not open those annotations.

## Training data and supervision

All supervised learning uses the openly available DFL / IDSSE Bundesliga tracking
dataset, Bassek et al. (2025), Figshare article 28196177 version 1,
[DOI 10.6084/m9.figshare.28196177.v1](https://doi.org/10.6084/m9.figshare.28196177.v1),
CC BY 4.0. We acknowledge the authors, DFL and Sportec Solutions. Exact public
file identifiers, sizes, MD5s and label provenance are recorded in
`configs/dfl_manifest.json` and `docs/sources.json`.

Provider BallStatus and BallPossession fields supply the labels; we did not
annotate the competition match. Provider tracking/events undergo operator quality
control, but these labels are not assumed to match the competition's possession
convention perfectly. Status 0 maps to D; status 1 with owner 1/2 maps to H/A;
missing or unexpected values remain X. Dead status overrides ownership.
Status, ownership, height, events, player names, jersey numbers and stable IDs
are excluded from the observation interface.

| Role | Complete matches | Tracking frames |
|---|---|---:|
| Training | J03WMX, J03WN1, J03WOH, J03WOY | 567,278 |
| Development confirmation | J03WPY, J03WQQ | 288,556 |
| Final external test, opened after freeze | J03WR9 | 146,810 |

Training uses clean, long-ball-gap and combined degradation conditions with fixed
seed 20261026. At most 12,000 evenly spaced eligible rows per match/condition are
sampled. These are augmented views of the same four matches, not additional
independent labelled matches.

| Head | Inputs | Training rows after masks |
|---|---:|---:|
| Dead ball versus alive | 21 | 144,000 |
| Home versus away with usable ball geometry | 22 | 56,023 |
| Home versus away from collective observations | 11 | 76,581 |

The model uses L2=0.01, training-only scaling/imputation, clipping at 8 standardized
units and deterministic Newton optimization. State features also expose missing
indicators. Odd H-minus-A team features use zero-centred RMS scaling and no
intercept, preserving team-exchange symmetry. A two-mode activity descriptor is
fitted on training observations only; it is not a calibrated dead-ball probability.
The fitted parameters are included in `release/model.json`; no external training
data needs to be downloaded to reproduce the submission.

## Observations and possession conventions

The shared feature builder computes 116 descriptors, with NaN and validity masks.
The heads use explicit subsets: metric distances/control kernels, relative
kinematics, anonymous collective geometry and movement, physical ball motion,
boundary/exit cues and period-bounded past/future context.

The state head excludes team-control and player-to-ball proximity features.
Standing beside a stationary ball is therefore not itself evidence that the ball
is alive. A separate visible-ball head estimates the controlling team when both
teams have usable geometric candidates. Otherwise the collective head supplies
conditional team evidence. Missing ball alone does not force D or continued
possession by the last team.

We factor observations as P(D), P(H)=(1−P(D))P(H|alive), and
P(A)=(1−P(D))(1−P(H|alive)). These are uncalibrated estimates. The final global
path can trade off H/A/D evidence jointly; separation of observation heads does
not make the complete decoded path conditionally independent.

Viterbi maximizes summed log observation scores minus soft transition costs.
The prior is estimated from adjacent known labels in the four training matches,
with H/A pooling, pseudocount 0.5 and uniform initial state. Modified costs are
score potentials, not a newly normalized Markov probability matrix. Probabilities
are quantized to float32 before logarithms to reproduce the archived J4/J6
numerical contract. Exact ties prefer fewer changes, then stable state order.

A pass or brief deflection does not automatically create a new possession.
Sustained contrary evidence can create a change; no minimum duration is imposed
and no short segment is removed after decoding. This can still suppress real
brief recoveries when their evidence is weak. Restarts are inferred from learned
physical context rather than a manually identified whistle or a fixed nearest
player. The published FAQ dead interval [110808,113742) is imposed inside the
decoder. X is emitted outside [11185,90652) and [110808,190198). No other manual
frame-specific correction is used. Completely uninformative periods may abstain;
partial gaps can use the global temporal context without imputing coordinates.

## Validation and limitations

We use the official pinned scorer: spellF1 averages greedy one-to-one possession
matching at IoU 0.3, 0.4, 0.5, 0.6 and 0.7; macroF1 is secondary. Short-possession
recall uses its one-to-one matching at IoU 0.5. Periods are separated explicitly.

Milestone 6 registered a bounded search before running it. Four match-level
internal folds refit preprocessing, context, classifiers and priors on three
training matches and evaluate the fourth. Four feature families and nine temporal
settings yield 156 comparisons. Selection considers a neighbourhood of settings
and short-possession recall. Nine fixed methods then yield 342 comparisons on
the two confirmation matches across 19 pre-existing scenario/seed pairs.
Those confirmation matches had already been inspected earlier: they were not a
new blind test. Independent final-test results are archived separately and do not
feed another selection or fallback.

| Mean spellF1 over 19 conditions | J03WPY | J03WQQ |
|---|---:|---:|
| Baseline, nearest player and ±50 majority | 0.2401 | 0.2752 |
| Original static Viterbi | 0.4052 | 0.4222 |
| Frozen final candidate | 0.4205 | 0.4355 |

Removing the collective fallback or replacing the learned state head with physical
rules reduces spellF1 on this benchmark. Dynamic transition cues did not improve
on the static reference. Rule-based hold improved macroF1 without improving
spellF1 and was not stacked onto the final model.

Short possessions remain the main known weakness: mean recall below two seconds
is only 0.0480 / 0.0526 on the confirmation matches and slightly lower than the
original static decoder. Neither a higher overall score nor absence of a hard
minimum duration resolves this failure. Other limits are provider-label mismatch,
cleaner DFL tracking, limited match diversity and synthetic degradations that are
stress tests rather than a validated simulator of the supplied ATD. Match splits
are not guaranteed to be team- or season-disjoint. External scores cannot be
converted into an expected private competition score. We do not target a league
possession count or a dead-ball percentage, or claim a ranking from these results.

## Exact reproduction

Use Python 3.12.6 and `requirements-inference.txt`. From the team repository:

```powershell
py -3.12 -m venv .venv-inference
.venv-inference\Scripts\python.exe -m pip install -r requirements-inference.txt
.venv-inference\Scripts\python.exe mya.py --verify
.venv-inference\Scripts\python.exe mya.py --data-dir "C:\path\to\provided-bundle" --fresh
```

No official checkout, Git metadata, external targets, training caches, notebook
or network is needed during inference. The supplied bundle may contain other
files; the final command only reads the two tactical ATD files. A CPU path was
verified on Windows, Intel i7-1355U with about 16 GiB RAM; no GPU is required.
Fresh and warm tracking-cache runs are checked in an isolated source copy and a
new virtual environment. This is a clean environment on the same computer, not
proof of bitwise identity on every architecture.

The exporter validates every row and checks the following exact SHA256 before
replacing an output file. A mismatch stops execution and preserves an existing
output. Source/model integrity and pinned versions are checked first.

```text
8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7
```

`docs/DELIVERY.md` details the options and the separate official format check.
`analysis/JALON_7_VALIDATION.md` records the actual reproduction checks and the
single final external evaluation. No private data or framewise predictions are
included in the public repository. The earlier baseline remains at
`submissions/MYA.csv`; the file to upload is **`submissions/final/MYA.csv`**.

## Final external test after the freeze

J03WR9 was opened only after the delivery code, weights, conditions and exact
competition CSV checksum were fixed. Only the final candidate and the predefined
baseline were evaluated. Results over the 19 conditions were:

| Method | Mean spellF1 | Mean macroF1 | Short-possession recall |
|---|---:|---:|---:|
| baseline | 0.2399 | 0.4209 | 0.0146 |
| candidate | 0.4064 | 0.8288 | 0.0823 |

These are aggregate measurements on one external match, not 19 independent
matches and not a competition score. The final package remains unchanged after
this measurement; it cannot support another selection on J03WR9. Detailed
results and immutable prediction fingerprints are in
`analysis/JALON_7_FINAL_TEST.json` and `.csv`.

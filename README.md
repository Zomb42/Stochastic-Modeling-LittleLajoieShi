# MLB In-Game Win Probability vs. Kalshi

Stochastic-modeling project for Little, Lajoie, and Shi. We are pursuing **baseball**: construct an absorbing Markov-chain model of MLB game states, then compare its in-game win probabilities with historical Kalshi market prices.

The main questions concern **forecast accuracy, calibration, and differences across game situations**. Latency arbitrage is an optional exploratory finding, not the primary objective. A profitable trading strategy is not required. Read [PROJECT_DIRECTION.md](PROJECT_DIRECTION.md) for the research question, modeling choices, analysis plan, and proposal-ready wording.

## Start here

1. [Project direction](PROJECT_DIRECTION.md): current MLB scope and methods.
2. [Data access and teammate setup](DATA_ACCESS.md): sources, public API access, and credential guidance.
3. [NFL/MLB comparison](SPORT_COMPARISON.md): why we chose baseball, lookback dates, and coverage checks.
4. [Complete-game alignment audit](alignment_audit/ALIGNMENT_AUDIT.md): six game timelines, reconstructed states, scoring-event checks, and conservative timing filters.

## Setup

Use Python 3.11 or newer. Clone the shared repository and open its root directory:

```bash
cd Stochastic-Modeling-LittleLajoieShi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate` instead. The downloads, reconstruction, and tests use the standard library. Matplotlib is needed only to regenerate timeline images.

**No API key, account login, Coinbase credentials, or private PEM file is needed for the current workflow.** The data was obtained through public Kalshi and MLB GET requests. Teammates can use the included snapshot or download their own copy. See [DATA_ACCESS.md](DATA_ACCESS.md) before adding any authenticated integration.

## Reproduce the saved analysis offline

The repository includes the public-data snapshot used for the checks, approximately 80 MiB including raw responses, derived tables, and audit outputs. Ensure those data folders are included when sharing the repo; sharing just the Python scripts will not supply the offline inputs.

```bash
python -m unittest -v test_mlb_alignment.py
python validate_mlb_alignment.py --plots
```

The audit reads `sport_comparison/` and regenerates `alignment_audit/`, including six PNG timelines and CSV tables. It makes no network calls. To preserve the supplied audit, write a separate local output folder:

```bash
python validate_mlb_alignment.py --out alignment_audit_local --plots
```

Current validated sample:

- Six complete games, 441 plate appearances, and 39 run-producing episodes.
- Scores, outs, and occupied bases match the saved MLB feed after every plate appearance.
- 241 eligible comparisons under the initial same-state timing, quote-age, and spread rules; 124 and 120 with fixed 30- and 60-second safety lags.
- This validates the sampled historical alignment. Exact live feed synchronization, the full catalog, and exceptional games still need further checks.

## Download a fresh public-data snapshot

Run this from the repository root with an internet connection:

```bash
python sport_data_probe.py --out sport_comparison_fresh
python validate_mlb_alignment.py --inputs sport_comparison_fresh --out alignment_audit_fresh --plots
```

`sport_data_probe.py` downloads and paginates the MLB/NFL market catalogs, downloads MLB schedules and team metadata, and retrieves play feeds and minute-price histories for six fixed sample dates. It caches responses. **Use a new output directory for a fresh snapshot**; rerunning in an existing directory reuses cached files. Fresh local snapshots are ignored by Git by default so they do not accidentally replace the reference dataset.

API archive cutoffs move over time. Catalog counts may change, and the scripts use fixed games to make checks reproducible. These probes establish feasibility; they are not yet a full-season ingestion pipeline or a fitted win-probability model.

## Files

| Path | Purpose |
| --- | --- |
| `sport_data_probe.py` | Main public-data discovery and MLB sample downloader |
| `validate_mlb_alignment.py` | Game-state reconstruction and market-alignment audit |
| `test_mlb_alignment.py` | Runner-movement and timing/leakage regression tests |
| `sport_comparison/` | Shared catalogs, MLB feeds, schedules, sample prices, matching results, and volume checks |
| `alignment_audit/` | Shared audit report, state/price tables, scoring windows, and timeline images |
| `PROJECT_DIRECTION.md` | Current baseball research scope |
| `DATA_ACCESS.md` | Reproducible data access and credential policy |
| `kalshi_data_probe.py` | Shared API utilities and the original NFL feasibility probe |
| `data_feasibility/`, `DATA_FEASIBILITY.md` | Earlier NFL investigation, retained as background |
| `NFL In-Game Win Probability vs Kalshi Project To-Do.pdf` | Original planning document; the current direction supersedes its NFL-specific scope |

## Remaining project work

Expand the alignment audit to extra innings, walk-offs, suspended games, and doubleheaders. Freeze an analysis sample and fit the transition model on earlier games. Evaluate calibration and forecast accuracy on later games, with uncertainty estimated by game. Any fee-aware paper-trading and bankroll analysis is secondary. Follow the course's AI-disclosure requirement and ensure every team member can explain the model and code.

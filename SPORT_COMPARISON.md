# Choosing NFL or MLB for the stochastic-modeling project

Checked October 27, 2026. Raw public API responses, normalized price CSVs, and measured results are saved in `sport_comparison/`. All operations were read-only.

**Decision: proceed with MLB for the historical absorbing-Markov-chain study.** Its Kalshi catalog is about 9.6 times larger, the game-state structure is a good fit, and the sampled MLB play feeds supply UTC timestamps. The NFL investigation is retained as comparison evidence. Collaborators can reproduce the public-data workflow without account keys; see [DATA_ACCESS.md](DATA_ACCESS.md).

The current [project direction](PROJECT_DIRECTION.md) emphasizes forecast accuracy, calibration, and model-market differences. Latency arbitrage is a possible exploratory extension, not the main goal or a required result. The follow-up [complete-game alignment audit](alignment_audit/ALIGNMENT_AUDIT.md) reconstructs six games and filters comparisons to observations representing the same recorded game state.

## How far the Kalshi data goes

| Measure | NFL (`KXNFLGAME`) | MLB (`KXMLBGAME`) |
| --- | --- | --- |
| Earliest game date found | **July 31, 2025** | **April 16, 2025** |
| Latest settled game date found | October 26, 2026 | October 26, 2026 |
| Earliest market opening | May 20, 2025; pregame prices for a September game | April 16, 2025 |
| Unique settled game-event identifiers | **489** | **4,693** |
| Unique team contracts | 978 | 9,386 |
| Events dated in calendar 2025 | 305 | 2,214 |
| Events dated in calendar 2026 | 184 | 2,479 |
| Recent / archived contract records | 278 / 732 | 1,104 / 8,462 |
| Duplicate contracts appearing in both tiers | 32 | 180 |

These are fully paginated game-winner-series catalogs, deduplicated by contract ticker. Each event normally contains two team contracts, so contract count is not game count. The NFL count includes preseason, and the MLB count includes some special/placeholder events and nonstandard settlements. They are candidate samples, not counts of fully cleaned price histories.

The legacy names `NFLGAME` and `MLBGAME` both returned zero records from recent and archived market listings. A Sports-series search also identified `KXNFLGAME` and `KXMLBGAME` as the main professional game-winner series. No pre-2025 history was found in these tested series. This is a scoped API finding, not proof that no older isolated sports contract or third-party archive exists. Season-winner futures should not be combined with game-winner data.

The oldest **prices**, not just metadata, were tested:

- NFL: `KXNFLGAME-25JUL31LACDET-LAC` returned 245 minute candles in the requested July 31 23:00 to August 1 05:00 UTC window, with 26 gaps between returned candles longer than a minute. It also returned all 911 trades in that window; no next cursor remained.
- NFL pregame lookback: `KXNFLGAME-25SEP08MINCHI-MIN` returned 68 quote candles between May 20 13:00 and May 21 15:00 UTC. The first was May 20 at 14:01 UTC. No trades were returned in that early window. This establishes earlier pregame quote data, not May football games.
- MLB: `KXMLBGAME-25APR16ATLTOR-ATL` returned 132 candles and all 65 trades in the April 16 15:00 to 22:00 UTC window. Its first candle was 15:01 UTC. The oldest baseball history is therefore retrievable, but sparse.

Kalshi's [historical-data guide](https://docs.kalshi.com/getting_started/historical_data) explains the moving archive boundaries. The August 28, 2026 cutoff observed here is the routing boundary between recent and archived data, **not the start of available history**. Older markets/candles and trades require their historical endpoints. Current versus archived candle schemas also differ; the scripts normalize both.

## Is baseball actually usable?

Yes, based on six directly tested games. The earliest MLB market matches MLB's own game `778297`, Atlanta at Toronto on April 16, 2025. Its historical feed returned 68 plate appearances and 316 pitches, all with UTC start timestamps. The separate win-probability endpoint returned 68 baseline observations.

Five later sample games were selected by the median combined contract volume among exact date/team matches on each chosen date. The dates are a small purposive sample; this is not a random full-catalog quality audit.

| Game date | Sample matchup | In-game minute candles / possible minute endpoints | Median quoted spread | Plate appearances with timestamps |
| --- | --- | --- | --- | --- |
| April 16, 2025 | Atlanta–Toronto | **107 / 163 (65.6%)** | **5 cents** | 68 / 68 |
| June 15, 2025 | Athletics–Kansas City | **169 / 169** | **1 cent** | 73 / 73 |
| September 15, 2025 | San Francisco–Arizona | **147 / 147** | **1 cent** | 69 / 69 |
| April 15, 2026 | San Francisco–Cincinnati | **144 / 144** | **1 cent** | 75 / 75 |
| September 15, 2026 | San Diego–Colorado | **151 / 151** | **1 cent** | 80 / 80 |
| October 26, 2026 | Milwaukee–Tampa Bay | **180 / 180** | **1 cent** | 76 / 76 |

Across all six, 441 plate appearances and 1,767 pitch events had start timestamps. In-game candle windows run from first-pitch start through last-pitch end, excluding the pregame period and most postgame artifacts. All five later games have consecutive one-minute endpoints in that interval. Candle presence does not establish quote freshness, executable size, or a fill at the midpoint. Some individual spreads were much wider than the median.

This suggests a pilot using June 2025 onward, followed by a larger quality audit before setting the final cutoff. It does not establish that every game after June has complete coverage.

## How many baseball games can be linked?

Matching the two-year catalog against MLB schedules using official date and the two contract team codes produced:

- 4,571 event identifiers with exactly one final-game candidate on that date and matchup.
- 4,564 distinct MLB game IDs among those candidates; some event identifiers refer to the same actual game.
- **4,562 distinct games** after also requiring binary yes/no settlements and agreement with the MLB final winner: **2,149 from 2025 and 2,413 from 2026**.
- 62 event identifiers with multiple possible games on the same date/matchup, usually doubleheaders. These require explicit game-number or scheduled-time matching.
- 60 event identifiers with no exact final-game candidate, including special labels, All-Star teams, postponements, and other exceptions. They were not forced into a match.

The catalog contains 11 events with at least one scalar settlement. In the single-candidate subset, one event had a nonbinary settlement and one had an outcome mismatch (`KXMLBGAME-25AUG18MILCHCG2`); both were excluded from the 4,562 count. Remaining duplicate event mappings must be reduced to one event per actual game for evaluation.

**This is schedule/outcome validation, not play-feed or price-history validation for all 4,562 games.** Play feeds and in-game candle quality were tested for six games. The prior NFL probe established 281 exact 2025-season matches with play timestamps; it did not audit every game's market history either.

## Baseball sources and API examples

Primary MLB data routes that responded without credentials:

```text
GET https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2025
GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2025-01-01&endDate=2025-12-31
GET https://statsapi.mlb.com/api/v1.1/game/778297/feed/live
GET https://statsapi.mlb.com/api/v1/game/778297/winProbability
```

The feed supplies `gamePk`, inning/half-inning, plate-appearance and pitch timestamps, outcomes, runner movements, count, and scores. The clock fields tested are full UTC strings such as `2025-04-16T17:08:27.463Z`. Kalshi's oldest corresponding archive request is:

```text
GET https://external-api.kalshi.com/trade-api/v2/historical/markets/KXMLBGAME-25APR16ATLTOR-ATL/candlesticks
    ?start_ts=1744815600&end_ts=1744840800&period_interval=1
```

The MLB web documentation redirects to an interactive portal, so these field-access findings were checked directly against saved MLB responses. The official [Baseball Savant CSV documentation](https://baseballsavant.mlb.com/csv-docs) independently documents pre-pitch balls/strikes, occupied bases, outs, inning, pre- and post-pitch scores, `game_pk`, and win-expectancy fields. Its deprecated time fields should not be assumed to provide reliable market-alignment clocks; the tested Stats API feed supplies those clocks.

For model training before the Kalshi overlap, [Retrosheet provides historical play-by-play downloads](https://www.retrosheet.org/downloads/csvdownloads.html), including [all 2025 regular-season and postseason event files](https://www.retrosheet.org/fall2025release.html). Older sports play data can train a transition model, but cannot create missing historical Kalshi prices.

## Which sport fits the stochastic model better?

| Consideration | MLB | NFL |
| --- | --- | --- |
| Candidate Kalshi sample | Much larger; portions of two seasons | One complete season plus part of another; includes preseason |
| Natural model structure | Base/out transitions with runs scored; inning and score determine game outcome | Possession, score, time, field position, down/distance and timeouts |
| State-space design | A useful starting component is 24 base/out states: 8 base configurations × 3 out counts | More continuous variables require bucketing and stronger smoothing |
| Sports-clock alignment | UTC plate-appearance and pitch timestamps verified in six games | UTC play timestamps verified across 281 matched games in prior probe |
| Price resolution | Minute bid/ask candles plus trade timestamps | Same API resolutions |
| New live data during November | Limited: only the remaining World Series schedule | Ongoing NFL games |
| Main complications | Doubleheaders, postponed/suspended games, pitching changes, extras and differing postseason rules | Sparse states, changing clock rules, overtime/ties, feed timing and clustered plays |

The 24-state base/out component alone is **not** a full-game win-probability model. Add inning, half-inning, and score differential; treat the inning-ending out as a boundary and home/away wins as absorbing outcomes. A practical first version learns plate-appearance transitions and the distribution of runs on each transition, pooling across innings to reduce sparsity. Player strength and starting pitchers can be extensions, rather than exploding the initial state space.

Handle regular-season and postseason extra innings separately: MLB's [automatic-runner rule applies only in the regular season](https://www.mlb.com/glossary/rules/designated-runner). Use the appropriate base state at the start of extras. Sampled Kalshi baseball rules also allow 50/50 settlement for certain unplayed/canceled/tied games; exclude those exceptional outcomes from a simple binary winner study or model their contractual payoff explicitly.

Start with plate-appearance or inning-level comparisons. A one-minute candle can span several pitches, so it is too coarse for a claim that the market reacted to a particular pitch at a particular instant. Use only information available before the prediction: MLB play `result` scores and final `count` fields describe the completed event, not automatically the starting state. Reconstruct pre-event state or use the documented Savant pre-pitch fields. MLB win-probability values in the tested endpoint are on a 0–100 scale, unlike Kalshi's 0–1 dollar prices; verify timing and normalize before comparison.

**Suggested scope:** fit a coarse MLB model on earlier seasons, validate its probabilities on held-out baseball games, then compare it with quality-filtered Kalshi prices from 2025–2026. Split by time, bootstrap by game, and keep midpoint calibration separate from any ask-price/fee-based paper trading simulation. The many historical games reduce dependence on collecting new data before the project deadline.

## Files and reproduction

From this project directory:

```bash
python3 sport_data_probe.py --out sport_comparison_fresh
```

The script uses Python's standard library and public GET requests. It caches responses, so a new output directory is required for a fresh catalog snapshot. The current saved run reused some raw responses fetched earlier in this same investigation; provenance is recorded in `sport_comparison/request_log.json`.

Key outputs:

- `sport_comparison/summary.json`: dates, deduplicated counts, oldest-price checks, MLB overlap, and six-game coverage.
- `sport_comparison/mlb_outcome_checked_matches.json`: successful schedule/outcome matches and rejected exceptions.
- `sport_comparison/mlb_schedule_matches.json`: original candidate matches and unresolved events.
- `sport_comparison/*_candles.csv`: normalized dollar-valued bid/ask paths.
- `sport_comparison/mlb_2025_04_16_plays.csv`: timestamped sample events, explicitly labeled post-event scores/outs, and the reported MLB baseline.
- `sport_comparison/raw/`: catalogs, MLB schedules, six historical play feeds, and API price responses.

Verification: both full catalogs were exhausted, contracts and game IDs were deduplicated, archived quotes were retrieved at the earliest boundaries, MLB outcomes were checked against schedule results, and all six sampled feeds and price paths were inspected programmatically. The follow-up alignment audit checks every plate appearance and scoring event in those six games; a full-season audit and fitted stochastic model remain subsequent work.

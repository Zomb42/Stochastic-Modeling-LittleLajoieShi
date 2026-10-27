# NFL win probability vs. Kalshi: data feasibility

Historical NFL feasibility notes. The current working scope has moved toward MLB; see [PROJECT_DIRECTION.md](PROJECT_DIRECTION.md) for the calibration-focused research question and the secondary role of possible latency/trading findings, and [the MLB alignment audit](alignment_audit/ALIGNMENT_AUDIT.md) for the completed six-game timing checks.

Checked October 27, 2026, approximately 4:34 PM Eastern, using public, unauthenticated GET requests. Evidence and normalized CSVs are in `data_feasibility/`. These are access and coverage checks, not a completed calibration study or a profitability result.

**Assessment: proceed with the project.** Historical NFL prices and timestamped play-by-play are available. A conservative starting sample is 281 exactly matched games from the 2025 NFL season, including January 2026 playoffs. Historical full-depth order books are not needed for the core calibration question. Precise executable-price and latency analysis needs additional work.

## What was verified

| Check | Observed result |
| --- | --- |
| Recent settled `KXNFLGAME` catalog | 278 contracts / 139 game events |
| Archived `KXNFLGAME` catalog | 732 contracts / 366 game events |
| Overlap between catalogs | 32 contracts / 16 events |
| Deduplicated catalog | **978 contracts / 489 game events** |
| Calendar year in event identifier | 305 events in 2025; 184 in 2026 |
| Earliest market close | August 1, 2025, 03:54 UTC; the July 31 Chargers–Lions game |
| Latest market close | October 27, 2026, 03:20 UTC; the October 26 Dallas–Philadelphia game |
| Strict date-and-team matches to nflverse schedules | 388 events |
| Matches belonging to the 2025 NFL season | **281 games: 270 regular season, 6 wild card, 4 divisional, 1 conference championship** |
| Matched 2025-season games with play timestamps | **281 / 281** |
| Rows across those games | 48,114; 46,689 with nonempty `time_of_day` (97.0%) |
| Additional schedule matches from the 2026 season | 107 regular-season games; 2026 play-by-play was not downloaded in this check |

Both catalogs were paginated until the cursor was empty. Do not add their counts without deduplicating on contract ticker, and count games using `event_ticker`, not contract count. The 489 events include preseason; they are not 489 confirmed analysis-ready regular-season games. Calendar year and NFL season are different: January 2026 playoffs belong to the 2025 season.

Of the 101 events without an exact schedule match, 98 are July/August preseason events absent from the downloaded schedule table. Three January identifiers need manual date/matchup review: `KXNFLGAME-26JAN04CARTB`, `KXNFLGAME-26JAN04SEASF`, and `KXNFLGAME-26JAN18SFSEA`. Do not silently assign these to the nearest date. The 2025 play-by-play release contains 285 games; this strict match establishes 281, rather than complete coverage of all 285.

This verifies market metadata availability for the catalog and price availability for two sample games. It does **not** establish usable price histories for all 281 matched games; that requires a batch candle download and quality audit.

## The sample URL

The URL identifies event `KXNFLGAME-26OCT29CARGB`, with two binary contracts:

- `KXNFLGAME-26OCT29CARGB-GB`: Green Bay wins.
- `KXNFLGAME-26OCT29CARGB-CAR`: Carolina wins.

The game is October 29, after this October 27 check. Its available prices are pregame prices. Use completed games to test in-game history.

The event response supplies titles, team labels, contract rules, and settlement source. Resolve an event to its contracts through `/events/{event_ticker}`; the website slug itself is not a contract ticker. `open_time` is the start of market trading, and `close_time`/`expected_expiration_time` are not reliable kickoff times. Use an NFL schedule plus observed play timestamps.

**Model adjustment:** the sampled rules specify a $0.50 settlement for each team in a tied game. For regular-season games, add a tie absorbing state and compare price to `P(win) + 0.5 P(tie)`, or restrict the analysis to an explicitly justified subset. A two-state win/loss model ignores this contractual outcome. Postponed/canceled games also require rule-based filtering.

## Price-history tests

| Contract | Requested UTC window | One-minute candles returned | Trade sample |
| --- | --- | --- | --- |
| `KXNFLGAME-25SEP04DALPHI-PHI` | Sep 4, 23:30 to Sep 5, 05:30, 2025 | 301, consecutive through 04:30 | 1,000 rows; more pages available |
| `KXNFLGAME-26OCT26DALPHI-DAL` | Oct 26, 23:30 to Oct 27, 04:30, 2026 | 232, consecutive through 03:21 | 1,000 rows; more pages available |

These counts include pregame and some postgame minutes. For the 2025 sample, restricting candle endpoints to the first through last timestamped play gives **234 consecutive one-minute candles**, all with bid and ask closes. Median quoted spread was **$0.01**, with a maximum of **$0.24** during that interval. A full-window post-close candle has a $1.00 spread, illustrating why postgame/suspended/empty-book states need filtering.

Candles contain YES bid and ask OHLC, trade-price OHLC/mean/previous, volume, and open interest. The tested minimum aggregation is **one minute**; documented alternatives are 60 and 1,440 minutes. Public trades provide finer event timestamps, price, quantity, and aggressor-side information, but do not reconstruct historical quotes or displayed depth. A last trade can be stale or occur on either side of the spread.

The 1,000 trades saved per game are bounded samples, not full game histories. Their cursors indicate additional data. For a full download, paginate `/markets/trades` and `/historical/trades` separately, deduplicate by `trade_id`, and respect their independent trade-time cutoff. Candle density in two games does not establish exchange uptime, quote freshness, or fillability across the entire sample.

### Important schema difference

The actual API responses match the current docs:

| Meaning | Recent candle response | Archived candle response |
| --- | --- | --- |
| Bid close | `yes_bid.close_dollars` | `yes_bid.close` |
| Ask close | `yes_ask.close_dollars` | `yes_ask.close` |
| Trade close | `price.close_dollars` | `price.close` |
| Volume | `volume_fp` | `volume` |
| Open interest | `open_interest_fp` | `open_interest` |

Both tested price representations are dollar strings such as `"0.7900"`; do not divide archived prices by 100. The probe normalizes both schemas to dollar probabilities and exports a common CSV schema.

## API routes and documentation

The current [public market-data guide](https://docs.kalshi.com/getting_started/quick_start_market_data) documents base URL `https://external-api.kalshi.com/trade-api/v2`. The older `https://api.elections.kalshi.com/trade-api/v2` from the HFT project also responded successfully in this check. The saved reproducible run uses the currently documented hostname. No local API secrets were needed.

| Purpose | GET route, relative to base URL |
| --- | --- |
| Archive boundary | `/historical/cutoff` |
| Resolve the example event | `/events/KXNFLGAME-26OCT29CARGB` |
| Recent settled NFL contracts | `/markets?series_ticker=KXNFLGAME&status=settled&limit=1000` |
| Archived NFL contracts | `/historical/markets?series_ticker=KXNFLGAME&limit=1000` |
| Recent-market candles | `/series/KXNFLGAME/markets/{ticker}/candlesticks` |
| Archived-market candles | `/historical/markets/{ticker}/candlesticks` |
| Recent public trades | `/markets/trades?ticker={ticker}&limit=1000` |
| Archived public trades | `/historical/trades?ticker={ticker}&limit=1000` |
| Current book only | `/markets/{ticker}/orderbook` |

Candles require `start_ts`, `end_ts` (Unix seconds), and `period_interval=1`. Trades accept `min_ts`, `max_ts`, and cursor pagination.

Observed cutoffs were `market_settled_ts = 2026-08-28T00:00:00Z` and `trades_created_ts = 2026-08-28T00:00:00Z`; order-update cutoff was October 13. These boundaries move. Candle routing depends on **market settlement time**; trade routing depends on **each trade's creation time**, so an open/recent market can have older trades in the archive. Current overlap also makes deduplication necessary.

Primary references:

- [Historical data and cutoff semantics](https://docs.kalshi.com/getting_started/historical_data)
- [Historical market catalog](https://docs.kalshi.com/api-reference/historical/get-historical-markets)
- [Recent candlesticks](https://docs.kalshi.com/api-reference/market/get-market-candlesticks)
- [Historical candlesticks](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks)
- [Historical public trades](https://docs.kalshi.com/api-reference/historical/get-historical-trades)
- [Current order book](https://docs.kalshi.com/api-reference/market/get-market-orderbook)
- [Authenticated WebSocket book updates](https://docs.kalshi.com/websockets/orderbook-updates)

Kalshi documents current books and real-time snapshot/delta streams, but no historical full-depth order-book route was found in the documented archive endpoints. This is a limit of the documented API, not a claim that no third-party archive exists. REST market-data checks here were keyless; the order-book WebSocket channel requires authentication.

## NFL data and timestamp validation

The maintained Python loader is [`nflreadpy`](https://nflreadpy.nflverse.com/). Its [load functions](https://nflreadpy.nflverse.com/api/load_functions/) support `nfl.load_pbp(2025)` and `nfl.load_schedules()`. It returns Polars frames; `.to_pandas()` is available. The probe instead downloads the same public CSV sources directly using the Python standard library, avoiding a package installation.

The downloaded `2025_01_DAL_PHI` game has 163 rows, of which 156 have `time_of_day`. All requested state/baseline columns are present in the saved sample CSV: score, possession, time remaining, field position, down/distance, `wp`, and `vegas_wp`.

Actual data:

- First kickoff timestamp: `2025-09-05T00:23:01.813Z`.
- `start_time`: `9/4/25, 20:23:01`, consistent with Eastern daylight time.
- Last timestamped play: `2025-09-05T04:17:46.890Z`.

This sample's `time_of_day` is already a full UTC ISO timestamp. Parse it directly; adding the Eastern game date or applying an extra four-hour shift would corrupt the join. Do not assume every season uses the same representation. The current [nflfastR field reference](https://nflfastr.com/reference/fast_scraper.html) describes UTC `time_of_day` and Eastern `start_time`, although its stated `HH:MM:SS` format is less specific than the actual 2025 values.

Two leakage issues matter:

1. The official field reference defines `total_home_score` and `total_away_score` as scores **at the end of the play**. Use `posteam_score`, `defteam_score`, and `score_differential` for a pre-play state. Match pre-play `home_wp`/`vegas_home_wp` to the home-team contract; raw `wp`/`vegas_wp` are possession-team probabilities.
2. A candle's `end_period_ts` marks the interval endpoint. Joining a snap to the candle containing that snap can include the market's response to the play. The example `sample_preplay_alignment.csv` uses only the last completed candle strictly before the play, with a maximum 60-second gap. It matches all 156 timestamped, non-deleted sample rows. This demonstrates a feasible temporal join, not a verified market-feed latency model.

Before drawing conclusions, inspect scoring plays, timestamp ordering, suspensions, and game-specific delays. Compare conservative backward joins and wider lag windows. Any estimated offset must be fixed without tuning on held-out outcomes. Bootstrap by game and split chronologically; thousands of plays are not independent game outcomes.

## Reuse from Kalshi-Orderbook-Predictor

Relevant existing files:

- `kalshi_live/market_discovery.py`: reusable keyless GET, JSON parsing, and cursor-pagination patterns. Its default series and current-market selection are specific to `KXBTC15M`, so the NFL probe uses explicit event/contract discovery.
- `kalshi_live/kalshi_auth.py`: reusable RSA-PSS signing if a future authenticated WebSocket recorder is needed.
- `kalshi_live/orderbook.py`: reusable snapshot/delta book reconstruction; it already handles fixed-point dollar fields.
- `kalshi_live/run_live.py`: provides WebSocket connection/subscription structure, but its BTC model, Coinbase dependency, filters, and paper simulator are not an NFL data pipeline.
- `collector/include/kalshi_worker.hpp`: useful stream-recording reference.
- `collector/include/kalshi_rest.hpp`: implements order placement/cancellation. It is not needed for historical data research.

The prior HFT collector also contains live order-management integration. It was inspected as source code and was not launched. No trading operations were performed. Do not transfer the BTC model's fee assumptions or trained signals to NFL markets.

## Recommended project scope

1. Train the absorbing game-state model on earlier NFL play-by-play seasons, then evaluate on a chronologically separated Kalshi sample. Include timeouts and a pregame strength bucket only if there is enough support; use coarse buckets/smoothing or a drive-level fallback.
2. Begin with the 281 exact 2025-season matches. Download minute candles for each, restrict to actual game activity, and audit quote gaps, spreads, nulls, missing histories, and event outcomes. Expand to 2026 after its play-by-play overlap is checked.
3. Build calibration/Brier-score comparisons using a consistent team perspective, payoff definition, and pre-play timing. Keep the last pregame price outside the in-game evaluation rows.
4. Treat execution as a separate, conservative paper simulation: buy at the ask, account for the applicable NFL fees and liquidity, and do not treat midpoint as an executable price. Verify current series fee rules before that phase. Candle closes alone do not establish available size or fill probability.
5. If finer timing/depth is needed, build a dedicated read-only recorder for selected upcoming games. Keyless REST polling every 30–60 seconds is a simple backup; authenticated WebSockets can capture richer quotes. Neither was left running by this investigation.

## Reproduce and inspect

From the `Stochastic-Modeling-LittleLajoieShi` repository root:

```bash
python3 kalshi_data_probe.py --nfl
```

Python 3.9+ and an internet connection are sufficient. Default output is `data_feasibility/`; rerunning replaces files with a fresh snapshot. `--trade-pages 3` increases the bounded trade sample; it still must not be described as complete unless `trades_incomplete` becomes false. `--out /path/to/new-folder` preserves the current evidence. The two sample game IDs are deliberately fixed so future runs exercise both archival routing and schema normalization.

Useful saved outputs:

- `summary.json`, `request_log.json`, `cutoff.json`: measured counts and API provenance.
- `live_markets.json`, `historical_markets.json`: raw paginated catalogs.
- `historical_candles.csv`, `live_candles.csv`: normalized one-minute price paths.
- `historical_trades.json`, `live_trades.json`: explicitly incomplete trade samples.
- `nfl_overlap.json`, `nfl_schedules.csv`: exact schedule matching and timestamp coverage.
- `nfl_2025_01_DAL_PHI.csv`: selected state/timing/baseline fields for one game.
- `sample_preplay_alignment.csv`: 156 backward candle-to-play matches.

Validation completed: the probe ran successfully against the documented public host, both candle schemas normalized into [0, 1] prices with bid <= ask, and all saved demonstration joins used earlier candle endpoints within 60 seconds. Full-history download, detailed alignment validation, calibration estimates, current fee verification, and bankroll simulation remain subsequent project work.

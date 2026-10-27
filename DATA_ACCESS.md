# Data access and teammate setup

The current baseball project is reproducible **without sharing anyone's API secrets**. Public datasets and code can be shared through the repository; account credentials are unnecessary for this workflow.

## What teammates need

- Python 3.11+ and the repository.
- Matplotlib from `requirements.txt` to regenerate the plots.
- Internet access only when downloading a new snapshot. The included snapshot supports offline reconstruction and tests.

There is no `.env` setup and no credentials file to request from another teammate. Coinbase is unrelated to this MLB project; do not copy credentials or private keys from the older HFT project.

## Public Kalshi market data

The [official market-data quick start](https://docs.kalshi.com/getting_started/quick_start_market_data) documents unauthenticated market-data access. All historical/recent market catalog, candle, and public-trade requests used in our investigation succeeded without keys.

Base URL:

```text
https://external-api.kalshi.com/trade-api/v2
```

Example catalog requests:

```text
GET /markets?series_ticker=KXMLBGAME&status=settled&limit=1000
GET /historical/markets?series_ticker=KXMLBGAME&limit=1000
GET /historical/cutoff
```

Example price/trade routes:

```text
GET /series/KXMLBGAME/markets/{ticker}/candlesticks
GET /historical/markets/{ticker}/candlesticks
GET /markets/trades?ticker={ticker}&limit=1000
GET /historical/trades?ticker={ticker}&limit=1000
```

Candles require Unix-second `start_ts`, `end_ts`, and `period_interval=1`. Paginate catalog and trade cursors. The [historical-data documentation](https://docs.kalshi.com/getting_started/historical_data) explains the moving routing cutoffs: candles follow market settlement time, while trades follow their individual creation times. Use backoff for rate-limit/server errors; do not evade rate limits by circulating account keys.

Run `python sport_data_probe.py --out sport_comparison_fresh` to perform the implemented requests, rather than constructing every URL by hand. The raw responses and source URLs are saved with the snapshot. Prices and volumes are observations, not evidence of guaranteed executable size or profit.

## Public MLB game data

These MLB endpoints were tested without credentials:

```text
https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2025
https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2025-01-01&endDate=2025-12-31
https://statsapi.mlb.com/api/v1.1/game/778297/feed/live
https://statsapi.mlb.com/api/v1/game/778297/winProbability
```

Schedules and teams establish game IDs. The game feed supplies timestamped events and runner movements. The baseline win-probability response is useful for comparison, but its event timing and 0–100 scale must be normalized before analysis. The official [Baseball Savant CSV reference](https://baseballsavant.mlb.com/csv-docs) documents complementary pre-pitch state variables. [Retrosheet](https://www.retrosheet.org/downloads/csvdownloads.html) supplies historical play-by-play for model training.

## Shared snapshot and reproducibility

Share these folders with the code:

- `sport_comparison/`: public raw responses and derived matching/price tables needed by the MLB audit.
- `alignment_audit/`: the reference report, timelines, and CSV outputs.
- `data_feasibility/`: the earlier NFL comparison evidence.

The saved snapshot was collected October 27, 2026. It contains public sports/market data; it does not contain personal portfolio or account responses. Regenerate local snapshots under separate names such as `sport_comparison_fresh` to preserve the common reference sample. Record source URLs and retrieval dates in future downloads, and keep provider attribution when using the data.

## If authenticated data is added later

Kalshi's [order-book WebSocket channel requires authentication](https://docs.kalshi.com/websockets/orderbook-updates). Authentication is not needed for the current REST-based project.

If that extension becomes useful, each teammate should create their own account/API key and keep the private key locally. Select the narrowest permissions available for the task. Another option is to run one collector under its owner's account and share its permitted public-data outputs, rather than distributing the owner's account credentials.

**Do not send teammates your personal Kalshi or Coinbase secret files, even just to avoid putting them in a public repository.** A private repository, email attachment, or direct message still gives recipients copies of those account credentials. The [Kalshi key guide](https://docs.kalshi.com/getting_started/api_keys) describes the public/private key design; the private signing key stays private.

The repository's `.gitignore` excludes secret directories, PEM/private-key files, environment files, and common credential JSON filenames. Ignore rules do not remove files already committed. If a real secret has previously been exposed, revoke/rotate it with the provider and address any repository history containing it. This migration does not inspect or modify the older HFT account credentials.

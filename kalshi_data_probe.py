#!/usr/bin/env python3
"""Read-only NFL data feasibility probe. Python 3.9+, standard library only.

Fetches public market data without credentials. Trades are a bounded sample;
catalogs are fully paginated. --nfl also downloads public 2025 play-by-play.
"""

import argparse
from bisect import bisect_left
import csv
import gzip
import io
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://external-api.kalshi.com/trade-api/v2"
SCHEDULES = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
PBP = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv.gz"
SAMPLE_COLUMNS = [
    "game_id", "play_id", "game_date", "season", "season_type", "home_team",
    "away_team", "posteam", "start_time", "time_of_day", "qtr", "time",
    "game_seconds_remaining", "total_home_score", "total_away_score",
    "posteam_score", "defteam_score", "score_differential", "yardline_100",
    "down", "ydstogo", "wp", "home_wp", "vegas_wp", "vegas_home_wp",
    "play_deleted", "play_type", "desc",
]


def download(url):
    for attempt in range(5):
        try:
            request = Request(url, headers={"User-Agent": "NFL-academic-data-probe/1.0"})
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            time.sleep(min(float(error.headers.get("Retry-After", 2 ** attempt)), 30))


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def iso_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def utc_iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def write_csv(path, rows, columns):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def candle_price(candle, group, field="close"):
    values = candle.get(group) or {}
    # Both representations are dollar probabilities, not integer cents.
    value = values.get(field + "_dollars", values.get(field))
    return float(value) if value is not None else None


def normalize_candles(candles):
    rows = []
    for candle in sorted(candles, key=lambda c: c["end_period_ts"]):
        bid, ask = candle_price(candle, "yes_bid"), candle_price(candle, "yes_ask")
        rows.append({
            "end_period_ts": candle["end_period_ts"],
            "end_period_utc": utc_iso(candle["end_period_ts"]),
            "yes_bid": bid, "yes_ask": ask,
            "midpoint": (bid + ask) / 2 if bid is not None and ask is not None else None,
            "spread": ask - bid if bid is not None and ask is not None else None,
            "trade_close": candle_price(candle, "price"),
            "volume": candle.get("volume_fp", candle.get("volume")),
            "open_interest": candle.get("open_interest_fp", candle.get("open_interest")),
        })
    return rows


def candle_summary(rows):
    spreads = [r["spread"] for r in rows if r["spread"] is not None]
    return {
        "rows": len(rows),
        "first_end_utc": rows[0]["end_period_utc"] if rows else None,
        "last_end_utc": rows[-1]["end_period_utc"] if rows else None,
        "gaps_over_60_seconds": sum(b["end_period_ts"] - a["end_period_ts"] > 60
                                    for a, b in zip(rows, rows[1:])),
        "rows_with_quotes": len(spreads),
        "median_spread": statistics.median(spreads) if spreads else None,
        "min_spread": min(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
    }


def canonical_team(team):
    return {"JAC": "JAX", "LAR": "LA", "WSH": "WAS"}.get(team, team)


def game_key(date, teams):
    return date, tuple(sorted(canonical_team(t) for t in teams))


def event_key(ticker, markets):
    # The date token is explicit. Teams come from each individual contract suffix;
    # do not try to split the concatenated matchup portion (variable-length teams).
    match = re.match(r"KXNFLGAME-(\d{2})([A-Z]{3})(\d{2})", ticker)
    if not match:
        raise ValueError(f"Unexpected NFL event ticker: {ticker}")
    year, month, day = match.groups()
    months = {name: i + 1 for i, name in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
    date = f"20{year}-{months[month]:02d}-{day}"
    return game_key(date, {m["ticker"].rsplit("-", 1)[1] for m in markets})


def nfl_probe(out, catalog, archived_candles):
    schedule_bytes = download(SCHEDULES)
    (out / "nfl_schedules.csv").write_bytes(schedule_bytes)
    schedules = {game_key(r["gameday"], [r["home_team"], r["away_team"]]): r
                 for r in csv.DictReader(io.StringIO(schedule_bytes.decode()))}
    events = defaultdict(list)
    for market in catalog:
        events[market["event_ticker"]].append(market)
    matched, unmatched = [], []
    for ticker, markets in events.items():
        schedule = schedules.get(event_key(ticker, markets))
        if schedule:
            matched.append((ticker, schedule))
        else:
            unmatched.append(ticker)

    print("Downloading compressed 2025 nflverse play-by-play...", flush=True)
    compressed = download(PBP)
    games, sample = {}, []
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as binary:
        for row in csv.DictReader(io.TextIOWrapper(binary)):
            game = games.setdefault(row["game_id"], {"rows": 0, "timestamp_rows": 0,
                                                    "iso_utc_rows": 0})
            game["rows"] += 1
            game["timestamp_rows"] += bool(row.get("time_of_day"))
            game["iso_utc_rows"] += row.get("time_of_day", "").endswith("Z")
            if row["game_id"] == "2025_01_DAL_PHI":
                sample.append({key: row.get(key, "") for key in SAMPLE_COLUMNS})
    write_csv(out / "nfl_2025_01_DAL_PHI.csv", sample, SAMPLE_COLUMNS)
    pbp_matches = [{"event_ticker": event, "game_id": schedule["game_id"],
                    "season": schedule["season"], "game_type": schedule["game_type"],
                    **games[schedule["game_id"]]}
                   for event, schedule in matched if schedule["game_id"] in games]
    timestamps = [iso_ts(r["time_of_day"]) for r in sample if r.get("time_of_day")]
    in_play = [r for r in archived_candles
               if timestamps and min(timestamps) <= r["end_period_ts"] <= max(timestamps)]
    # Demonstrate a backward join; a containing-minute candle would see the future.
    candle_ends = [r["end_period_ts"] for r in archived_candles]
    aligned = []
    for play in sample:
        if not play.get("time_of_day") or play.get("play_deleted") == "1":
            continue
        play_ts = iso_ts(play["time_of_day"])
        index = bisect_left(candle_ends, play_ts) - 1
        if index < 0 or play_ts - candle_ends[index] > 60:
            continue
        candle = archived_candles[index]
        aligned.append({
            "game_id": play["game_id"], "play_id": play["play_id"],
            "play_time_utc": play["time_of_day"], "posteam": play["posteam"],
            "posteam_score_before": play["posteam_score"],
            "defteam_score_before": play["defteam_score"],
            "home_wp_before": play["home_wp"], "vegas_home_wp_before": play["vegas_home_wp"],
            "candle_end_utc": candle["end_period_utc"],
            "candle_age_seconds": play_ts - candle["end_period_ts"],
            "phi_bid": candle["yes_bid"], "phi_ask": candle["yes_ask"],
            "phi_midpoint": candle["midpoint"], "spread": candle["spread"],
        })
    if aligned:
        write_csv(out / "sample_preplay_alignment.csv", aligned, list(aligned[0]))
    summary = {
        "schedule_source": SCHEDULES, "pbp_source": PBP,
        "schedule_matches": len(matched), "unmatched_events": sorted(unmatched),
        "schedule_matches_by_season_and_type": dict(Counter(
            s["season"] + "_" + s["game_type"] for _, s in matched)),
        "pbp_2025_games": len(games), "matched_pbp_games": len(pbp_matches),
        "matched_games_with_timestamps": sum(g["timestamp_rows"] > 0 for g in pbp_matches),
        "matched_pbp_rows": sum(g["rows"] for g in pbp_matches),
        "matched_timestamp_rows": sum(g["timestamp_rows"] for g in pbp_matches),
        "sample_rows": len(sample), "sample_timestamp_rows": len(timestamps),
        "sample_first_timestamp": utc_iso(min(timestamps)) if timestamps else None,
        "sample_last_timestamp": utc_iso(max(timestamps)) if timestamps else None,
        "sample_preplay_aligned_rows": len(aligned),
        "sample_in_play_candles": candle_summary(in_play), "matches": pbp_matches,
    }
    save_json(out / "nfl_overlap.json", summary)
    return {k: v for k, v in summary.items() if k not in ("matches", "unmatched_events")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data_feasibility")
    parser.add_argument("--nfl", action="store_true", help="Also verify overlap with 2025 NFL play-by-play")
    parser.add_argument("--trade-pages", type=int, default=1, help="Maximum 1000-row pages per sample game")
    args = parser.parse_args()
    if args.trade_pages < 1:
        parser.error("--trade-pages must be positive")
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    requests = []

    def get(path, params=None):
        url = args.base_url.rstrip("/") + path
        if params:
            url += "?" + urlencode(params)
        data = json.loads(download(url))
        requests.append({"url": url, "received_at_utc": datetime.now(timezone.utc).isoformat()})
        time.sleep(0.15)
        return data

    cutoff = get("/historical/cutoff")
    save_json(out / "cutoff.json", cutoff)
    event = get("/events/KXNFLGAME-26OCT29CARGB")
    save_json(out / "sample_event.json", event)
    catalog_by_tier = {}
    for tier, endpoint in [("live", "/markets"), ("historical", "/historical/markets")]:
        params = {"series_ticker": "KXNFLGAME", "limit": 1000}
        if tier == "live":
            params["status"] = "settled"
        markets, seen_cursors = [], set()
        while True:
            page = get(endpoint, params)
            markets.extend(page["markets"])
            cursor = page.get("cursor")
            if not cursor:
                break
            if cursor in seen_cursors:
                raise RuntimeError("API repeated a catalog cursor")
            seen_cursors.add(cursor)
            params["cursor"] = cursor
        catalog_by_tier[tier] = markets
        save_json(out / f"{tier}_markets.json", markets)
        print(f"{tier}: {len(markets)} markets, {len({m['event_ticker'] for m in markets})} events", flush=True)

    live = {m["ticker"]: m for m in catalog_by_tier["live"]}
    historical = {m["ticker"]: m for m in catalog_by_tier["historical"]}
    # Prefer live metadata when a market is temporarily present in both tiers.
    unique = {**historical, **live}
    catalog = list(unique.values())
    events = {m["event_ticker"] for m in catalog}
    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url,
        "cutoffs": cutoff, "unique_markets": len(catalog), "unique_events": len(events),
        "overlapping_markets": len(live.keys() & historical.keys()),
        "events_by_calendar_year": dict(Counter("20" + e.split("-")[1][:2] for e in events)),
        "earliest_market_close": min(m["close_time"] for m in catalog),
        "latest_market_close": max(m["close_time"] for m in catalog), "samples": {},
    }
    historical_rows = []
    for label, ticker, start, end in [
        ("live", "KXNFLGAME-26OCT26DALPHI-DAL", "2026-10-26T23:30:00Z", "2026-10-27T04:30:00Z"),
        ("historical", "KXNFLGAME-25SEP04DALPHI-PHI", "2025-09-04T23:30:00Z", "2025-09-05T05:30:00Z"),
    ]:
        # Route candles by market settlement; route trades independently by trade time.
        market = unique[ticker]
        tier = "historical" if iso_ts(market["settlement_ts"]) < iso_ts(cutoff["market_settled_ts"]) else "live"
        path = (f"/historical/markets/{ticker}/candlesticks" if tier == "historical"
                else f"/series/KXNFLGAME/markets/{ticker}/candlesticks")
        candles = get(path, {"start_ts": int(iso_ts(start)), "end_ts": int(iso_ts(end)), "period_interval": 1})
        save_json(out / f"{label}_candles.json", candles)
        rows = normalize_candles(candles["candlesticks"])
        columns = ["end_period_ts", "end_period_utc", "yes_bid", "yes_ask", "midpoint",
                   "spread", "trade_close", "volume", "open_interest"]
        write_csv(out / f"{label}_candles.csv", rows, columns)
        if label == "historical":
            historical_rows = rows
        trades, incomplete, pages = [], False, 0
        trade_cutoff = int(iso_ts(cutoff["trades_created_ts"]))
        windows = [("/historical/trades", int(iso_ts(start)), min(int(iso_ts(end)), trade_cutoff - 1)),
                   ("/markets/trades", max(int(iso_ts(start)), trade_cutoff), int(iso_ts(end)))]
        for endpoint, lower, upper in windows:
            if lower > upper:
                continue
            params = {"ticker": ticker, "min_ts": lower, "max_ts": upper, "limit": 1000}
            if pages >= args.trade_pages:
                incomplete = True
                continue
            while pages < args.trade_pages:
                page = get(endpoint, params)
                pages += 1
                trades.extend(page["trades"])
                if not page.get("cursor"):
                    break
                params["cursor"] = page["cursor"]
            else:
                incomplete = True
        save_json(out / f"{label}_trades.json", {"trades": trades, "incomplete": incomplete, "pages": pages})
        summary["samples"][label] = {"ticker": ticker, "candle_tier": tier, **candle_summary(rows),
                                      "trade_sample_rows": len(trades), "trades_incomplete": incomplete}

    if args.nfl:
        summary["nfl"] = nfl_probe(out, catalog, historical_rows)
    save_json(out / "request_log.json", requests)
    save_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

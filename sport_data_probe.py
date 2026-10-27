#!/usr/bin/env python3
"""Compare public Kalshi NFL/MLB catalogs and MLB timestamp/price samples.

Python standard library only; all network operations are public GET requests.
Responses are cached. Use a new --out directory to take a fresh snapshot.
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from kalshi_data_probe import (
    BASE, candle_summary, download, iso_ts, normalize_candles, save_json, write_csv,
)


def canonical_team(code):
    return {"ARI": "AZ", "WSN": "WSH", "OAK": "ATH"}.get(code, code)


def matchup_key(date, teams):
    return date, tuple(sorted(canonical_team(t) for t in teams))


def event_date(event):
    token = event.split("-")[1][:7]
    months = dict(zip(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        range(1, 13),
    ))
    return f"20{token[:2]}-{months[token[2:5]]:02d}-{token[5:7]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "sport_comparison")
    parser.add_argument("--seed-cache", type=Path, help="Optional directory of previously fetched responses")
    args = parser.parse_args()
    out = args.out
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    log = []

    def cached(label, url):
        path = raw / f"{label}.json"
        seed = args.seed_cache / path.name if args.seed_cache else None
        if path.exists():
            data = json.loads(path.read_text())
            origin = "existing cache"
        elif seed and seed.exists():
            data = json.loads(seed.read_text())
            save_json(path, data)
            origin = "seed cache from earlier requests in this investigation"
        else:
            data = json.loads(download(url))
            save_json(path, data)
            origin = "public GET"
        log.append({"label": label, "url": url, "source": origin,
                    "accessed_at_utc": datetime.now(timezone.utc).isoformat()})
        return data

    catalogs, counts = {}, {}
    for series in ["KXNFLGAME", "NFLGAME", "KXMLBGAME", "MLBGAME"]:
        tiers = {}
        for tier, endpoint in [("live", "/markets"), ("historical", "/historical/markets")]:
            label = f"{series}_{tier}"
            path = raw / (label + ".json")
            seed = args.seed_cache / path.name if args.seed_cache else None
            params = {"series_ticker": series, "limit": 1000}
            if tier == "live":
                params["status"] = "settled"
            url = BASE + endpoint + "?" + urlencode(params)
            if path.exists() or (seed and seed.exists()):
                markets = cached(label, url)
            else:
                markets, seen = [], set()
                while True:
                    page = json.loads(download(BASE + endpoint + "?" + urlencode(params)))
                    markets.extend(page["markets"])
                    cursor = page.get("cursor")
                    if not cursor:
                        break
                    if cursor in seen:
                        raise RuntimeError("Repeated catalog cursor")
                    seen.add(cursor)
                    params["cursor"] = cursor
                save_json(path, markets)
                log.append({"label": label, "url": url, "source": "fully paginated public GET"})
            tiers[tier] = {m["ticker"]: m for m in markets}
        unique = {**tiers["historical"], **tiers["live"]}
        catalogs[series] = unique
        events = {m["event_ticker"] for m in unique.values()}
        counts[series] = {
            "live_contracts": len(tiers["live"]), "historical_contracts": len(tiers["historical"]),
            "overlapping_contracts": len(tiers["live"].keys() & tiers["historical"].keys()),
            "unique_contracts": len(unique), "unique_events": len(events),
            "events_by_calendar_year": dict(Counter("20" + e.split("-")[1][:2] for e in events)),
            "earliest_event_date": min(map(event_date, events)) if events else None,
            "latest_event_date": max(map(event_date, events)) if events else None,
            "earliest_market_open": min((m["open_time"] for m in unique.values()), default=None),
        }
        print(series, json.dumps(counts[series]), flush=True)

    cutoff = cached("cutoff", BASE + "/historical/cutoff")
    earliest_samples = []
    for label, ticker, start, end in [
        ("nfl_oldest_game", "KXNFLGAME-25JUL31LACDET-LAC", "2025-07-31T23:00:00Z", "2025-08-01T05:00:00Z"),
        ("nfl_earliest_pregame", "KXNFLGAME-25SEP08MINCHI-MIN", "2025-05-20T13:00:00Z", "2025-05-21T15:00:00Z"),
        ("mlb_oldest_game", "KXMLBGAME-25APR16ATLTOR-ATL", "2025-04-16T15:00:00Z", "2025-04-16T22:00:00Z"),
    ]:
        query = urlencode({"start_ts": int(iso_ts(start)), "end_ts": int(iso_ts(end)), "period_interval": 1})
        data = cached(label + "_candles", BASE + f"/historical/markets/{ticker}/candlesticks?" + query)
        rows = normalize_candles(data["candlesticks"])
        if rows:
            write_csv(out / (label + "_candles.csv"), rows, list(rows[0]))
        query = urlencode({"ticker": ticker, "min_ts": int(iso_ts(start)), "max_ts": int(iso_ts(end)), "limit": 1000})
        trades = cached(label + "_trades", BASE + "/historical/trades?" + query)
        earliest_samples.append({"label": label, "ticker": ticker, **candle_summary(rows),
                                 "trade_rows": len(trades["trades"]),
                                 "trades_incomplete": bool(trades.get("cursor"))})

    schedules = []
    teams = {}
    for year in [2025, 2026]:
        data = cached(f"mlb_teams_{year}", f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={year}")
        teams.update({t["id"]: t["abbreviation"] for t in data["teams"]})
        schedules.append(cached(f"mlb_schedule_{year}",
            f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={year}-01-01&endDate={year}-12-31"))
    by_pair = defaultdict(dict)
    for schedule in schedules:
        for date in schedule["dates"]:
            for game in date["games"]:
                if game["status"]["abstractGameState"] != "Final":
                    continue
                pair = [teams.get(game["teams"][side]["team"]["id"], "UNKNOWN") for side in ["home", "away"]]
                by_pair[matchup_key(game["officialDate"], pair)][game["gamePk"]] = game
    by_event = defaultdict(list)
    for market in catalogs["KXMLBGAME"].values():
        by_event[market["event_ticker"]].append(market)
    matched, ambiguous, unmatched = [], [], []
    for event, markets in by_event.items():
        candidates = list(by_pair[matchup_key(event_date(event),
            {m["ticker"].rsplit("-", 1)[1] for m in markets})].values())
        if len(candidates) == 1:
            matched.append({"event_ticker": event, "game": candidates[0]})
        elif len(candidates) > 1:
            ambiguous.append({"event_ticker": event, "games": candidates})
        else:
            unmatched.append(event)
    save_json(out / "mlb_schedule_matches.json", {"matched": matched, "ambiguous": ambiguous, "unmatched": unmatched})
    consistent, rejected = [], []
    for row in matched:
        game = row["game"]
        markets = by_event[row["event_ticker"]]
        if any(m.get("result") not in ("yes", "no") for m in markets):
            rejected.append({"event_ticker": row["event_ticker"], "reason": "nonbinary settlement"})
            continue
        home_score, away_score = (game["teams"][side].get("score") for side in ["home", "away"])
        if home_score is None or away_score is None or home_score == away_score:
            rejected.append({"event_ticker": row["event_ticker"], "reason": "no distinct final winner"})
            continue
        winner = teams[game["teams"]["home" if home_score > away_score else "away"]["team"]["id"]]
        if all((m["result"] == "yes") ==
               (canonical_team(m["ticker"].rsplit("-", 1)[1]) == winner) for m in markets):
            consistent.append(row)
        else:
            rejected.append({"event_ticker": row["event_ticker"], "reason": "market/schedule outcome mismatch"})
    save_json(out / "mlb_outcome_checked_matches.json", {"matched": consistent, "rejected": rejected})
    overlap = {
        "events_with_one_final_date_team_candidate": len(matched),
        "unique_mlb_game_ids_among_those_candidates": len({r["game"]["gamePk"] for r in matched}),
        "candidate_events_by_year": dict(Counter(r["game"]["season"] for r in matched)),
        "ambiguous_doubleheader_events": len(ambiguous), "unmatched_events": len(unmatched),
        "scalar_settlement_events": sum(any(m.get("result") == "scalar" for m in ms) for ms in by_event.values()),
        "binary_outcome_consistent_events": len(consistent),
        "binary_outcome_consistent_unique_games": len({r["game"]["gamePk"] for r in consistent}),
        "binary_outcome_consistent_unique_games_by_year": dict(Counter(year for year, game_id in {
            (r["game"]["season"], r["game"]["gamePk"]) for r in consistent})),
    }

    samples = []
    for date in ["2025-04-16", "2025-06-15", "2025-09-15", "2026-04-15", "2026-09-15", "2026-10-26"]:
        candidates = [r for r in matched if r["game"]["officialDate"] == date
            and all(m.get("result") in ["yes", "no"] for m in by_event[r["event_ticker"]])]
        if not candidates:
            continue
        if date == "2025-04-16":
            selection = next(r for r in candidates if r["game"]["gamePk"] == 778297)
        else:
            candidates.sort(key=lambda r: sum(float(m["volume_fp"]) for m in by_event[r["event_ticker"]]))
            selection = candidates[len(candidates) // 2]
        game = selection["game"]
        market = sorted(by_event[selection["event_ticker"]], key=lambda m: m["ticker"])[0]
        ticker = market["ticker"]
        print("Sampling", date, ticker, "MLB game", game["gamePk"], flush=True)
        prefix = date.replace("-", "")
        feed = cached(prefix + "_feed", f"https://statsapi.mlb.com/api/v1.1/game/{game['gamePk']}/feed/live")
        plays = feed["liveData"]["plays"]["allPlays"]
        pitches = [e for play in plays for e in play.get("playEvents", []) if e.get("isPitch")]
        starts = [iso_ts(e["startTime"]) for e in pitches if e.get("startTime")]
        ends = [iso_ts(e["endTime"]) for e in pitches if e.get("endTime")]
        first, last = min(starts), max(ends)
        archived = iso_ts(market["settlement_ts"]) < iso_ts(cutoff["market_settled_ts"])
        route = (f"/historical/markets/{ticker}/candlesticks" if archived
                 else f"/series/KXMLBGAME/markets/{ticker}/candlesticks")
        query = urlencode({"start_ts": int(first) - 1800, "end_ts": int(last) + 120, "period_interval": 1})
        data = cached(prefix + "_candles", BASE + route + "?" + query)
        rows = normalize_candles(data["candlesticks"])
        if rows:
            write_csv(out / (prefix + "_candles.csv"), rows, list(rows[0]))
        active = [c for c in rows if first <= c["end_period_ts"] <= last]
        expected = int(last // 60 - first // 60)
        sample = {
            "date": date, "event_ticker": selection["event_ticker"], "ticker": ticker,
            "gamePk": game["gamePk"], "game_type": game["gameType"],
            "selection": "earliest game" if date == "2025-04-16" else "median combined market volume on date",
            "first_pitch_utc": datetime.fromtimestamp(first, timezone.utc).isoformat(),
            "last_pitch_utc": datetime.fromtimestamp(last, timezone.utc).isoformat(),
            "plate_appearances": len(plays),
            "plate_appearances_with_start": sum(bool(p.get("about", {}).get("startTime")) for p in plays),
            "pitch_events": len(pitches), "pitch_events_with_start": len(starts),
            "expected_minute_endpoints": expected,
            "minute_coverage_fraction": len(active) / expected if expected else None,
            "in_game_candles": candle_summary(active),
        }
        samples.append(sample)
        print(json.dumps(sample), flush=True)
    wp = cached("mlb_oldest_wp", "https://statsapi.mlb.com/api/v1/game/778297/winProbability")
    overlap["oldest_sample_wp_rows"] = len(wp)
    overlap["oldest_sample_wp_rows_with_baseline"] = sum(p.get("homeTeamWinProbability") is not None for p in wp)
    play_rows = [{
        "at_bat_index": p.get("atBatIndex", p.get("about", {}).get("atBatIndex")),
        "inning": p["about"]["inning"], "half_inning": p["about"]["halfInning"],
        "start_time_utc": p["about"].get("startTime"),
        "end_time_utc": p["about"].get("endTime"), "result": p["result"]["event"],
        "home_score_after": p["result"]["homeScore"],
        "away_score_after": p["result"]["awayScore"], "outs_after": p["count"]["outs"],
        "home_wp_reported": p.get("homeTeamWinProbability"),
    } for p in wp]
    if play_rows:
        write_csv(out / "mlb_2025_04_16_plays.csv", play_rows, list(play_rows[0]))
    summary = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "catalogs": counts,
               "earliest_price_samples": earliest_samples, "mlb_schedule_overlap": overlap,
               "mlb_price_samples": samples}
    save_json(out / "summary.json", summary)
    save_json(out / "request_log.json", log)
    print("Saved", out / "summary.json", flush=True)


if __name__ == "__main__":
    main()

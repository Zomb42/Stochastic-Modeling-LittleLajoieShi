#!/usr/bin/env python3
"""Reconstruct cached MLB games and audit conservative joins to Kalshi candles.

No network calls. Standard library for the audit; --plots requires matplotlib.
Game-event times are historical event timestamps, not feed receive timestamps.
"""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from kalshi_data_probe import iso_ts, normalize_candles, save_json, write_csv
from sport_data_probe import canonical_team

BASES = ("1B", "2B", "3B")


def stamp(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def apply_movements(state, movements, batting_side):
    """Apply simultaneous movements, collapsing intermediate stops per runner.

    One runner can have 2B->3B and 3B->score records at the same play index.
    Remove all departing runners before placing any arriving runners.
    """
    runners = defaultdict(list)
    for movement in movements:
        runners[movement["details"]["runner"]["id"]].append(movement)
    for runner_id, moves in runners.items():
        occupied = [base for base, player in state["bases"].items() if player == runner_id]
        for base in occupied:
            del state["bases"][base]
        # A pinch runner can replace the recorded identity at the starting base.
        if not occupied:
            state["bases"].pop(moves[0]["movement"]["start"], None)
    for runner_id, moves in runners.items():
        movement = moves[-1]["movement"]
        destination = movement["end"]
        if movement["isOut"]:
            state["outs"] += 1
        elif destination in BASES:
            if destination in state["bases"]:
                raise ValueError(f"Two runners occupy {destination}")
            state["bases"][destination] = runner_id
        if any(m["details"]["isScoringEvent"] and not m["movement"]["isOut"] for m in moves):
            state[batting_side] += 1
    if state["outs"] >= 3:
        state["bases"].clear()


def snapshot(state):
    return {"home_score": state["home"], "away_score": state["away"], "outs": state["outs"],
            "bases": "|".join(base for base in BASES if base in state["bases"])}


def reconstruct(feed):
    plays = feed["liveData"]["plays"]["allPlays"]
    state = {"home": 0, "away": 0, "outs": 0, "bases": {}}
    half, previous_end = None, None
    pa_rows, event_rows, scoring, problems = [], [], [], []
    for play in plays:
        about = play["about"]
        pa_index = about["atBatIndex"]
        current_half = (about["inning"], about["halfInning"])
        side = "away" if current_half[1] == "top" else "home"
        if half != current_half:
            half = current_half
            state["outs"], state["bases"] = 0, {}
        movements = defaultdict(list)
        for runner in play["runners"]:
            movements[runner["details"]["playIndex"]].append(runner)
        events = sorted(play["playEvents"], key=lambda e: e["index"])
        if set(movements) - {e["index"] for e in events}:
            raise ValueError(f"Runner movement has no event in PA {pa_index}")
        anchor, pre_state, ready = None, None, previous_end
        for event in events:
            start = iso_ts(event["startTime"]) if event.get("startTime") else None
            end = iso_ts(event["endTime"]) if event.get("endTime") else start
            before = snapshot(state)
            if event.get("isPitch") and anchor is None:
                if start is None:
                    raise ValueError("First pitch lacks timestamp")
                anchor, pre_state = start, before.copy()
                if ready is not None and ready > anchor:
                    problems.append({"pa_index": pa_index, "kind": "state_ready_after_first_pitch",
                                     "seconds": ready - anchor})
            apply_movements(state, movements[event["index"]], side)
            after = snapshot(state)
            changed = before != after
            if changed and end is None:
                raise ValueError("State-changing event lacks a timestamp")
            if changed and anchor is None:
                ready = max(ready or end, end)
            event_rows.append({"pa_index": pa_index, "event_index": event["index"],
                "inning": half[0], "half": half[1], "is_pitch": bool(event.get("isPitch")),
                "start_ts": start, "end_ts": end, "state_changed": changed,
                **{"before_" + k: v for k, v in before.items()},
                **{"after_" + k: v for k, v in after.items()}})
            runs = after[side + "_score"] - before[side + "_score"]
            if runs:
                scoring.append({"pa_index": pa_index, "event_index": event["index"],
                    "inning": half[0], "half": half[1], "scoring_side": side, "runs": runs,
                    "event": "; ".join(dict.fromkeys(r["details"]["event"] for r in movements[event["index"]]
                                                       if r["details"]["isScoringEvent"])),
                    "start_ts": start, "end_ts": end, "event_start_utc": stamp(start),
                    "event_end_utc": stamp(end), "home_score_after": state["home"],
                    "away_score_after": state["away"],
                    "pa_scoring_flag": about.get("isScoringPlay", False)})

        expected_bases = {base for key, base in [("postOnFirst", "1B"), ("postOnSecond", "2B"),
                                                ("postOnThird", "3B")] if key in play["matchup"]}
        if set(state["bases"]) != expected_bases:
            raise ValueError(f"Base reconstruction differs from MLB in PA {pa_index}")
        if state["outs"] != play["count"]["outs"]:
            raise ValueError(f"Out reconstruction differs from MLB in PA {pa_index}")
        if (state["home"], state["away"]) != (play["result"]["homeScore"], play["result"]["awayScore"]):
            raise ValueError(f"Score reconstruction differs from MLB in PA {pa_index}")
        end = iso_ts(about["endTime"])
        if anchor is None:
            problems.append({"pa_index": pa_index, "kind": "no_pitch_anchor"})
        if anchor is not None and end < anchor:
            raise ValueError("PA ends before its first pitch")
        if previous_end is not None and anchor is not None and anchor < previous_end:
            problems.append({"pa_index": pa_index, "kind": "overlapping_pa_timestamps",
                             "seconds": previous_end - anchor})
        pa_rows.append({"pa_index": pa_index, "inning": half[0], "half": half[1],
            "anchor_ts": anchor, "first_pitch_utc": stamp(anchor) if anchor else None,
            "pa_end_ts": end, "pa_end_utc": stamp(end), "state_ready_ts": ready,
            "previous_pa_end_ts": previous_end,
            **{"before_" + k: v for k, v in (pre_state or {}).items()},
            **{"after_" + k: v for k, v in snapshot(state).items()},
            "result_after": play["result"]["event"], "description_after": play["result"].get("description")})
        previous_end = end
    final = feed["liveData"]["linescore"]["teams"]
    if (state["home"], state["away"]) != (final["home"]["runs"], final["away"]["runs"]):
        raise ValueError("Reconstruction differs from final linescore")
    return pa_rows, event_rows, scoring, problems


def prior_quote(candles, ends, cutoff):
    index = bisect_left(ends, cutoff) - 1
    return candles[index] if index >= 0 else None


def quote_fields(quote):
    if quote is None:
        return {k: None for k in ["quote_end_utc", "quote_end_ts", "home_bid", "home_ask", "home_mid", "spread"]}
    return {"quote_end_utc": quote["end_period_utc"], "quote_end_ts": quote["end_period_ts"],
            "home_bid": quote["home_bid"], "home_ask": quote["home_ask"],
            "home_mid": quote["home_mid"], "spread": quote["spread"]}


def align_pa(pa_rows, candles, lag=0, max_spread=0.05):
    ends = [c["end_period_ts"] for c in candles]
    rows = []
    for pa in pa_rows:
        if pa["anchor_ts"] is None:
            continue
        quote = prior_quote(candles, ends, pa["anchor_ts"] - lag)
        age = pa["anchor_ts"] - quote["end_period_ts"] if quote else None
        fresh = age is not None and lag < age <= lag + 60
        same = quote is not None and (pa["state_ready_ts"] is None or quote["end_period_ts"] >= pa["state_ready_ts"])
        good_spread = quote is not None and quote["spread"] is not None and 0 < quote["spread"] <= max_spread + 1e-9
        row = {**pa, "lag_seconds": lag, **quote_fields(quote), "quote_age_seconds": age,
               "age_ok": fresh, "same_recorded_state": same, "spread_ok": good_spread,
               "eligible": fresh and same and good_spread}
        rows.append(row)
    return rows


def score_windows(scoring, events, candles):
    rows = []
    ends = [c["end_period_ts"] for c in candles]
    for number, episode in enumerate(scoring, 1):
        before = prior_quote(candles, ends, episode["start_ts"])
        for wait in [0, 60, 120]:
            index = bisect_left(ends, episode["end_ts"] + wait)
            after = candles[index] if index < len(candles) else None
            other_changes = sum(e["state_changed"] and e["end_ts"] is not None and
                episode["end_ts"] < e["end_ts"] <= after["end_period_ts"] for e in events) if after else None
            other_scores = sum(episode["end_ts"] < e["end_ts"] <= after["end_period_ts"] for e in scoring) if after else None
            move = after["home_mid"] - before["home_mid"] if before and after else None
            pre_age = episode["start_ts"] - before["end_period_ts"] if before else None
            post_age = after["end_period_ts"] - episode["end_ts"] if after else None
            quote_quality = (before is not None and after is not None and pre_age <= 60
                and post_age <= wait + 60 and 0 < before["spread"] <= .05 + 1e-9
                and 0 < after["spread"] <= .05 + 1e-9)
            rows.append({"episode_number": number, **episode, "post_wait_seconds": wait,
                "pre_quote_utc": before["end_period_utc"] if before else None,
                "post_quote_utc": after["end_period_utc"] if after else None,
                "pre_home_mid": before["home_mid"] if before else None,
                "post_home_mid": after["home_mid"] if after else None,
                "pre_spread": before["spread"] if before else None,
                "post_spread": after["spread"] if after else None,
                "quote_quality_ok": quote_quality,
                "home_mid_change": move, "other_state_changes_before_post_quote": other_changes,
                "other_scoring_episodes_before_post_quote": other_scores,
                "pre_quote_age_to_event_start": pre_age,
                "post_quote_delay_from_event_end": post_age})
    return rows


def plot_game(out, feed, sample, candles, scoring, pa_aligned):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import MaxNLocator
    home = feed["gameData"]["teams"]["home"]["abbreviation"]
    away = feed["gameData"]["teams"]["away"]["abbreviation"]
    first, last = iso_ts(sample["first_pitch_utc"]), iso_ts(sample["last_pitch_utc"])
    active = [c for c in candles if first - 600 <= c["end_period_ts"] <= last + 60]
    times = [datetime.fromtimestamp(c["end_period_ts"], timezone.utc) for c in active]
    def broken_values(field):
        # Do not bridge absent minutes with a continuous price line.
        xs, ys = [], []
        for i, c in enumerate(active):
            if i and c["end_period_ts"] - active[i-1]["end_period_ts"] > 60:
                xs.append(datetime.fromtimestamp(active[i-1]["end_period_ts"] + 1, timezone.utc));ys.append(float("nan"))
            xs.append(datetime.fromtimestamp(c["end_period_ts"], timezone.utc));ys.append(c[field])
        return xs, ys
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 1, figsize=(12, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.3, 1.1]}, layout="constrained")
    for field, color, label, width in [("home_bid", "#94a3b8", "Home bid/ask proxy", .8),
                                      ("home_ask", "#94a3b8", None, .8),
                                      ("home_mid", "#1d4ed8", "Home midpoint proxy", 1.6)]:
        xs, ys = broken_values(field);axes[0].plot(xs, ys, color=color, lw=width, label=label)
    eligible = [r for r in pa_aligned if r["lag_seconds"] == 0 and r["eligible"]]
    axes[0].scatter([datetime.fromtimestamp(r["anchor_ts"], timezone.utc) for r in eligible],
                    [r["home_mid"] for r in eligible], s=12, color="#111827", alpha=.65,
                    label="Eligible pre-PA join (price sampled earlier)")
    for i, episode in enumerate(scoring):
        dt = datetime.fromtimestamp(episode["end_ts"], timezone.utc)
        color = "#15803d" if episode["scoring_side"] == "home" else "#b91c1c"
        for ax in axes:
            ax.axvline(dt, color=color, alpha=.3, lw=.8)
        axes[0].text(dt, .96 - .09 * (i % 3), f"{i+1}", color=color, fontsize=8,
                     transform=axes[0].get_xaxis_transform(), ha="center")
    axes[0].set_ylim(-.03, 1.06);axes[0].set_ylabel(f"{home} win-price proxy")
    axes[0].legend(loc="lower left", fontsize=8, ncol=2)
    axes[0].set_title(f"{sample['date']}  {away} at {home} | cached event-time audit", loc="left", fontweight="bold")
    st = [datetime.fromtimestamp(first - 600, timezone.utc)] + [datetime.fromtimestamp(e["end_ts"], timezone.utc) for e in scoring] + [datetime.fromtimestamp(last, timezone.utc)]
    for side, color, team in [("home", "#1d4ed8", home), ("away", "#d97706", away)]:
        values = [0] + [e[side + "_score_after"] for e in scoring] + [feed["liveData"]["linescore"]["teams"][side]["runs"]]
        axes[1].step(st, values, where="post", color=color, label=team)
    axes[1].set_ylabel("Runs");axes[1].yaxis.set_major_locator(MaxNLocator(integer=True));axes[1].legend(loc="upper left", ncol=2, fontsize=8)
    axes[2].plot(times, [100*c["spread"] for c in active], color="#475569", lw=1)
    axes[2].axhline(5, color="#b45309", ls="--", lw=.8, label="5-cent audit threshold")
    axes[2].set_ylabel("Spread (cents)");axes[2].legend(loc="upper left", fontsize=8)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=timezone.utc))
    axes[2].set_xlabel("UTC time | numbered lines: scoring event end; green=home, red=away; no clock offsets fitted")
    for ax in axes:
        ax.grid(alpha=.15)
        ax.set_xlim(datetime.fromtimestamp(first - 600, timezone.utc), datetime.fromtimestamp(last + 60, timezone.utc))
    fig.savefig(out / (sample["date"] + "_timeline.png"), dpi=160)
    plt.close(fig)


def report(out, results, totals):
    lines = ["# MLB game-state and market alignment audit", "",
        "Six complete games reconstructed from the saved October 27, 2026 API snapshot. "
        "This validates historical event-time alignment, not real-time feed delivery or latency arbitrage.", "",
        "## Reconstruction and conservative joins", "",
        "Runner movements were processed in event-index order. Multiple movements of one runner within "
        "an event were collapsed to the final destination. Scores, outs, and occupied bases were checked "
        "against MLB after every plate appearance; final scores were checked against linescores.", "",
        "The decision anchor is the first pitch of each plate appearance (PA). A quote must end strictly "
        "before that anchor. An eligible join also requires that the candle endpoint is after the preceding "
        "PA finished and after any further recorded state change before the first pitch, with quote age "
        "at most 60 seconds and a positive spread no wider than 5 cents. Candle existence alone does not "
        "establish quote freshness. This rule is deliberately stricter than a generic backward join.", "",
        "| Game date | Away at home | PAs checked | Score/base/out mismatches | Backward joins within 60s | Same recorded state within 60s | Eligible at <=5c spread | Scoring episodes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in results:
        z = r["lags"]["0"]
        lines.append(f"| {r['date']} | {r['away']} at {r['home']} | {r['plate_appearances']} | 0 | {z['age_ok']} | {z['same_state_and_age_ok']} | {z['eligible']} | {r['scoring_episodes']} |")
    lines += ["", f"Across all games: **{totals['plate_appearances']} plate appearances**, "
              f"**{totals['scoring_episodes']} scoring episodes**, and **zero** score/base/out reconstruction mismatches. "
              "Timestamp-order warnings, if any, are reported separately in `summary.json`.", "",
        "### Lag sensitivity", "",
        "The same backward-join rules were repeated with fixed 30- and 60-second safety lags. "
        "The state at the decision time is still required to have existed at the earlier quote endpoint. "
        "This tests sample loss under conservative timing, not the optimal latency offset.", "",
        "| Safety lag | Age-qualified candidates | Same-state candidates | Eligible with spread filter |",
        "| --- | ---: | ---: | ---: |"]
    for lag, count in totals["lags"].items():
        lines.append(f"| {lag}s | {count['age_ok']} | {count['same_state_and_age_ok']} | {count['eligible']} |")
    lines += ["", "## Scoring-event inspection", "",
        "Every run-producing event was identified from reconstructed score changes, including mid-PA "
        "runs that MLB's PA-level `isScoringPlay` flag can omit. Each episode has diagnostic windows: "
        "the last candle strictly before the event starts, and the first candle ending at least 0, 60, "
        "or 120 seconds after the event ends. Intervening state changes and other scoring episodes are "
        "counted in the CSV. These windows can combine several pieces of baseball news; they are not "
        "causal price-impact estimates or evidence of exploitable market delay.", "",
        "Home prices use the sampled contract's YES quotes when it is the home team; otherwise "
        "`home_bid = 1 - away_ask` and `home_ask = 1 - away_bid`. This is the NO side of that contract, "
        "not an independently observed second team's order book.", ""]
    for r in results:
        lines += [f"### {r['date']}: {r['away']} at {r['home']}", "",
            f"![Complete game timeline]({r['date']}_timeline.png)", "",
            "Times below are UTC event-end timestamps. Scores are away-home. Price changes compare "
            "the last pre-event candle with the first candle ending at least 60 seconds after event end.", "",
            "| Episode | UTC end | Inning | Event | Score | Home midpoint before -> after | Quote quality | Other state changes |",
            "| --- | --- | --- | --- | --- | --- | --- | ---: |"]
        for w in r["scoring_windows"]:
            if w["post_wait_seconds"] != 60:
                continue
            fmt = lambda v: f"{v:.3f}" if v is not None else "missing"
            quality = "passes" if w["quote_quality_ok"] else "wide / stale / missing"
            lines.append(f"| {w['episode_number']} | {w['event_end_utc'][11:19]} | {w['half']} {w['inning']} | {w['event']} | {w['away_score_after']}-{w['home_score_after']} | {fmt(w['pre_home_mid'])} -> {fmt(w['post_home_mid'])} | {quality} | {w['other_state_changes_before_post_quote']} |")
    lines += ["", "## Interpretation and remaining limits", "",
        "The audit establishes a reproducible same-state subset for minute-resolution calibration. "
        "A plain nearest-prior quote is insufficient when the previous play ended after that quote. "
        "Such rows remain in the diagnostic CSV but are excluded from the eligible subset. "
        "This selection favors longer breaks and can change the state distribution; report selection "
        "rates by inning/state and repeat the analysis with alternative evaluation designs.", "",
        "Final historical feeds can contain revisions. Neither source supplies the receive-time records "
        "needed to prove when a particular observer learned an event. Events also occupy time intervals, "
        "and minute candles cannot resolve individual pitches. No empirical clock shift was fitted. "
        "The six audited games do not cover extra innings, walk-offs, suspended games, or ambiguous "
        "doubleheaders; those cases require separate checks before expanding the sample.", "",
        "Use the calibration/forecast comparison as the primary study. Price response around events is "
        "a secondary descriptive analysis. Profitable latency arbitrage would need higher-resolution "
        "quotes, contemporaneous receive timestamps, executable size, and fee/latency modeling, and "
        "is not a required outcome.", "",
        "## Reproduce", "", "```bash", "python3 validate_mlb_alignment.py --plots", "```", "",
        "The audit uses cached inputs in `sport_comparison/`; it makes no network calls. "
        "CSV/JSON generation uses the standard library; plots require matplotlib. "
        "`pa_market_alignment.csv` includes diagnostic outcome columns with `_after` suffixes; "
        "they must never be used as prediction inputs. `game_events.csv` contains event-by-event "
        "reconstructed states, and `scoring_event_windows.csv` contains all inspection windows."]
    (out / "ALIGNMENT_AUDIT.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path(__file__).resolve().parent / "sport_comparison")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "alignment_audit")
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    samples = json.loads((args.inputs / "summary.json").read_text())["mlb_price_samples"]
    results, all_pa, all_events, all_windows = [], [], [], []
    for sample in samples:
        prefix = sample["date"].replace("-", "")
        feed = json.loads((args.inputs / "raw" / (prefix + "_feed.json")).read_text())
        pa_rows, events, scoring, problems = reconstruct(feed)
        home = feed["gameData"]["teams"]["home"]["abbreviation"]
        away = feed["gameData"]["teams"]["away"]["abbreviation"]
        contract_team = canonical_team(sample["ticker"].rsplit("-", 1)[1])
        if contract_team not in (home, away):
            raise ValueError("Contract and MLB feed teams disagree")
        candles = normalize_candles(json.loads((args.inputs / "raw" / (prefix + "_candles.json")).read_text())["candlesticks"])
        for candle in candles:
            if candle["yes_bid"] is None or candle["yes_ask"] is None:
                raise ValueError("Sample has null quotes; add explicit filtering")
            if contract_team == home:
                candle["home_bid"], candle["home_ask"] = candle["yes_bid"], candle["yes_ask"]
            else:
                candle["home_bid"], candle["home_ask"] = 1 - candle["yes_ask"], 1 - candle["yes_bid"]
            candle["home_mid"] = (candle["home_bid"] + candle["home_ask"]) / 2
        aligned = [row for lag in [0, 30, 60] for row in align_pa(pa_rows, candles, lag)]
        for row in aligned:
            if row["quote_end_ts"] is not None and not row["quote_end_ts"] < row["anchor_ts"] - row["lag_seconds"]:
                raise ValueError("Join used a future candle")
            if row["eligible"] and row["state_ready_ts"] is not None and row["quote_end_ts"] < row["state_ready_ts"]:
                raise ValueError("Eligible join uses an outdated state")
        windows = score_windows(scoring, events, candles)
        ids = {"date": sample["date"], "game_pk": sample["gamePk"], "ticker": sample["ticker"],
               "home_team": home, "away_team": away}
        all_pa += [{**ids, **row} for row in aligned]
        all_events += [{**ids, **row} for row in events]
        all_windows += [{**ids, **row} for row in windows]
        lags = {}
        for lag in [0, 30, 60]:
            rows = [r for r in aligned if r["lag_seconds"] == lag]
            lags[str(lag)] = {"candidates": len(rows), "age_ok": sum(r["age_ok"] for r in rows),
                "same_state_and_age_ok": sum(r["age_ok"] and r["same_recorded_state"] for r in rows),
                "eligible": sum(r["eligible"] for r in rows)}
        result = {**ids, "home": home, "away": away, "plate_appearances": len(pa_rows),
            "events": len(events), "reconstruction_mismatches": 0, "scoring_episodes": len(scoring),
            "scoring_episodes_without_pa_flag": sum(not s["pa_scoring_flag"] for s in scoring),
            "timestamp_warnings": problems, "lags": lags, "scoring_windows": windows}
        results.append(result)
        if args.plots:
            plot_game(args.out, feed, sample, candles, scoring, aligned)
        print(sample["date"], "PAs", len(pa_rows), "scoring", len(scoring), "lags", lags, "warnings", problems)
    totals = {"games": len(results), "plate_appearances": sum(r["plate_appearances"] for r in results),
              "scoring_episodes": sum(r["scoring_episodes"] for r in results),
              "scoring_episodes_without_pa_flag": sum(r["scoring_episodes_without_pa_flag"] for r in results),
              "timestamp_warning_count": sum(len(r["timestamp_warnings"]) for r in results),
              "lags": {str(lag): {key: sum(r["lags"][str(lag)][key] for r in results)
                         for key in ["candidates", "age_ok", "same_state_and_age_ok", "eligible"]} for lag in [0, 30, 60]}}
    for name, rows in [("pa_market_alignment.csv", all_pa), ("game_events.csv", all_events),
                        ("scoring_event_windows.csv", all_windows)]:
        if rows:
            write_csv(args.out / name, rows, list(rows[0]))
    save_json(args.out / "summary.json", {"totals": totals, "games": results})
    report(args.out, results, totals)
    print("TOTAL", json.dumps(totals))


if __name__ == "__main__":
    main()

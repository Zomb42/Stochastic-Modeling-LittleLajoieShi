# MLB in-game win probability and Kalshi: project direction

Updated October 27, 2026. **Baseball is the chosen direction** for the Little, Lajoie, and Shi stochastic-modeling project. The original NFL project outline remains useful background; the sport and research emphasis below supersede that earlier draft. Start with [README.md](README.md) and [DATA_ACCESS.md](DATA_ACCESS.md) for collaborator setup. The current public-data workflow requires no API keys.

## Central question

**How well does an absorbing Markov-chain model of baseball game states estimate in-game win probabilities, and how do its forecasts compare with Kalshi market prices across different game situations?**

The primary goals are to build and explain the stochastic model, evaluate out-of-sample forecast accuracy and calibration, and understand systematic differences between model probabilities and observed market prices. The study remains valuable if the market outperforms the model, if forecasts are similarly accurate, or if no profitable strategy is found.

## Role of latency and trading

**We are not primarily seeking latency arbitrage.** We do not need to observe an event before other traders or exploit a faster data feed for this project to succeed. Our main comparison uses game states and market observations that reflect the same recorded information, with conservative timing and sensitivity checks.

Price adjustment after runs, outs, and other events can be a secondary descriptive analysis. Delayed market adjustment or a possible latency opportunity could emerge as an exploratory finding, but it is not assumed, promised, or required. A lag between recorded timestamps is not by itself evidence of a tradable edge: source timestamps, feed delivery, quote aggregation, revisions, liquidity, and other intervening plays can all matter.

If the secondary betting analysis is retained, test whether persistent discrepancies survive spreads, applicable fees, and conservative execution assumptions. Use paper simulations and a bankroll/risk-of-ruin model to connect with the random-walk material. A profitable result is not a success criterion, and midpoint prices are not assumed executable. An actual latency-arbitrage study would require additional high-resolution quotes and contemporaneous receive-time records beyond the current historical candles.

## Why baseball

Baseball is event-driven and has discrete state variables. Begin at the plate-appearance level with

```text
state = (inning, top/bottom, outs, occupied bases, score difference)
```

There are 24 base/out combinations within a half-inning: eight base configurations times three out counts. This is a component of the full-game model, not the whole state space. Learn transitions and runs scored from earlier play-by-play, carry score and inning forward, and make home and away wins absorbing outcomes. Handle inning boundaries, walk-offs, and regular-season versus postseason extra innings explicitly.

Most variables do not need arbitrary bins. A finite implementation may still need a documented score-range truncation or extra-inning approximation. Start with pooled transitions and an explainable baseline; player/pitcher strength or pregame team strength are extensions. If pregame Kalshi prices are used as model inputs, disclose that dependence and report an ablation without those prices so the model-market comparison remains interpretable.

## What the data investigation establishes

- The public game-winner catalogs contain 4,693 distinct settled MLB event identifiers, compared with 489 NFL events, as of the saved October 27 snapshot. These totals precede cleaning of special events and exceptions.
- MLB game-market history reaches April 16, 2025. The earliest sample is sparse; five later games tested from June 2025 through October 2026 have complete in-game minute endpoints and 1-cent median quoted spreads.
- 4,562 distinct MLB games pass date/team/final-winner matching. Six complete games have now been reconstructed and checked against the saved MLB feed at every plate appearance. That does not establish full cleaned coverage of all 4,562 games.
- The six-game alignment audit checks 441 plate appearances and 39 run-producing episodes with zero score, out, or base-occupancy reconstruction mismatches and zero timestamp-order warnings. It retains 241 pre-plate-appearance observations under the initial same-state, quote-age, and 5-cent spread rules. Fixed 30- and 60-second safety lags retain 124 and 120, respectively.

The full audit, timelines, scoring-event tables, and exclusions are in [ALIGNMENT_AUDIT.md](alignment_audit/ALIGNMENT_AUDIT.md). Source and catalog details are in [SPORT_COMPARISON.md](SPORT_COMPARISON.md).

## Matching and information timing

Match actual games by date, teams, and game number/time when necessary. Deduplicate multiple market identifiers referring to the same game. Normalize all event timestamps to UTC and all prices to a consistent home-team perspective.

Reconstruct the state sequentially from completed events. Pre-play prediction inputs must not include the outcome, final count, post-play scores, later runner movements, or revised information that would only be known after the decision point. Historical corrected feeds do not establish real-time availability.

For the initial minute-candle design, anchor an observation immediately before a plate appearance's first pitch. Use a strictly earlier completed candle, and keep it only if the preceding plate appearance and any subsequent recorded state changes were already complete at the candle endpoint. This avoids comparing a new game state to a price from before that state existed. The initial quote-age limit is 60 seconds and the maximum spread is 5 cents; these are provisional quality rules, not tuned performance thresholds. Repeat with fixed safety lags and report how selection changes the sample.

Scoring-event plots are diagnostic. Their windows can contain other plays and should not be interpreted as isolated causal responses or latency-arbitrage signals. No clock offset has been optimized to make price jumps align with game events.

## Analysis plan

1. **Validate and freeze the sample.** Expand the six-game audit, explicitly test extra innings, walk-offs, doubleheaders, and suspended/rescheduled games, and audit per-state selection rates. Restrict exceptional settlements or model their contractual payoff separately.
2. **Estimate transitions.** Train on earlier seasons and document pooling, smoothing, truncation, and absorbing outcomes. Check that the model reaches absorption and that its probabilities are sensible in obvious endgame states.
3. **Evaluate forecasts.** Use later held-out games and compare model and Kalshi forecasts with Brier scores, log loss, and calibration plots. Normalize the timing and perspective of any third-party win-probability baseline before including it. Bootstrap by game and avoid treating correlated plate appearances as independent outcomes.
4. **Explain differences.** Break results down by inning, score, base/out state, quote quality, and pregame strength. Model-market disagreement alone does not prove market mispricing; omitted player information and model approximation can explain it.
5. **Secondary economic/risk analysis.** If feasible, simulate conservative paper decisions and bankroll paths after spread/fees. Keep exploratory event-response or latency findings separate from the primary calibration conclusions.

## Proposal wording

> We will develop an absorbing Markov-chain model of MLB game states and evaluate its in-game win probabilities against historical Kalshi prices. The main objective is to study forecast calibration, accuracy, and systematic differences across game situations using conservatively aligned observations. We are not primarily pursuing latency arbitrage: possible delayed market adjustment may be explored as a secondary finding, but neither a latency advantage nor a profitable trading strategy is required for the project. Any paper-trading and bankroll analysis will account for spreads, applicable fees, and uncertainty about execution.

Disclose AI assistance as required by the course, and ensure the team can explain the code, state definitions, timing rules, and conclusions. No predictive model or calibration result has been fitted yet; the completed work establishes data feasibility and a validated initial alignment pipeline.

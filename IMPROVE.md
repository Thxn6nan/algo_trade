# Real Edge Strategy Improvement Plan

Last updated: 2026-05-05

## Purpose

เอกสารนี้คือแผนพัฒนาระบบและ strategy ให้เข้าใกล้ "real edge" อย่างรัดกุม โดยไม่ตั้งเป้าว่าแค่ทำให้ `verdict: PASS` ให้ได้ แต่ตั้งเป้าว่า edge ต้องรอดจากต้นทุนจริง, out-of-sample, stress, robustness, และการตรวจซ้ำแบบไม่เปิดช่องให้ overfit.

หลักสำคัญ:

- Truthful `FAIL` ดีกว่า gamed `PASS`.
- Strategy ที่ผ่านเฉพาะ in-sample ยังเป็นแค่ candidate.
- ทุกการปรับ strategy ต้องมี thesis ก่อน ไม่ใช่วนสุ่ม parameter จนเขียว.
- ห้ามลด gate เพื่อให้ผลผ่าน เว้นแต่มีเหตุผลด้าน realism และต้องบันทึกเหตุผลไว้ใน report.
- Gemini หรือ agent ตัวอื่นใช้ช่วย research/patch ได้ แต่ห้ามให้แก้ threshold, cost model, หรือ holdout rules เพื่อทำให้ตัวเอง PASS.

## Latest Evidence Baseline

Latest real-data evidence run:

- Command: `python run.py --mode backtest --symbol XAUUSDm --timeframe M15`
- Run id: `bt-e7f61e2dcb35`
- Walk-forward run id: `wf-7f1a589b6eec`
- Report artifacts:
  - `runs/bt-e7f61e2dcb35/edge_report.json`
  - `runs/bt-e7f61e2dcb35/edge_report.md`
  - `runs/wf-7f1a589b6eec/walk_forward_summary.json`
- Edge verdict: `FAIL`
- Failure class: `no_edge`
- Failure reasons:
  - `profit_factor`
  - `stress_expectancy_positive`
  - `walk_forward_present`
  - `walk_forward_positive`
  - `robustness_positive`

Primary backtest metrics:

- Real-data rows: 20,000 M15 bars.
- Data range: 2025-06-30 01:00 to 2026-05-05 08:00.
- Duplicate timestamps: 0.
- Invalid candles: 0.
- Missing bars: 271, currently accepted by warning policy.
- Median spread: 160.
- P95 spread: 280.
- Strategy: `pullback_trend_continuation`.
- Trades: 1,066.
- Profit factor: 1.1067, below the 1.15 gate.
- Expectancy: 1.641.
- Total return: 17.49%.
- Max drawdown: 7.15%.
- Win rate: 42.78%.
- Median R: -0.525.

Stress evidence:

- `bad` stress remains positive:
  - Profit factor: 1.0945.
  - Expectancy: 1.448.
  - Total return: 15.44%.
- `stress` stress fails:
  - Profit factor: 0.9916.
  - Expectancy: -0.131.
  - Total return: -1.10%.

Walk-forward evidence:

- Current walk-forward summary has zero splits and zero rounds.
- Cause: current data covers about 10 months, while the default promotion split needs 12 months train + 3 months validation + 3 months test.
- Therefore no out-of-sample promotion evidence exists yet.

Current interpretation:

- The system is now more honest than the earlier suspicious PASS.
- Corrected cost handling made the strategy weaker.
- The strategy is a research candidate, not proven real edge.
- The next goal is not to force PASS, but to find a thesis that survives stress and locked out-of-sample validation.

## Current Credibility Risks

### 1. Data coverage is too short for promotion

The latest local file has about 10 months of M15 data. That is enough for research diagnostics but not enough for the default promotion walk-forward scheme.

Risk:

- Any strategy tuned on this span can overfit recent XAUUSD behavior.
- No proper locked test window exists under the default split.

Required response:

- Backfill at least 18 months for a minimal promotion run.
- Prefer 24-36 months for more stable regime coverage.
- Keep shorter split configs explicitly labeled as `research_dev`, never promotion.

### 2. Profit factor is close to threshold

The latest PF is 1.1067 after improved costs, below the 1.15 gate.

Risk:

- Small cost, spread, slippage, or fill-policy changes can flip the result.
- A near-threshold edge is not robust enough for live exposure.

Required response:

- Treat PF below 1.15 as no edge.
- Treat PF 1.15-1.25 as weak candidate only.
- Require PF stability across walk-forward and cost stress before promotion.

### 3. Stress failure is decisive

The strategy loses positive expectancy under the heavier stress model.

Risk:

- The edge depends on optimistic execution assumptions.
- Live spreads/slippage can erase the apparent advantage.

Required response:

- Strategy changes must improve stressed expectancy, not just base expectancy.
- Any thesis that only works under base cost is rejected.

### 4. Walk-forward gate is still not producing usable evidence

The latest edge check correctly failed `walk_forward_present`, but the report still has no meaningful walk-forward rounds.

Risk:

- PASS can remain blocked, but the system cannot yet tell which strategy generalizes.

Required response:

- Expand data or add a clearly marked short research split.
- Promotion must require non-empty locked test rounds.

### 5. Robustness is partially implemented

Cost stress and trade dependency checks now exist, but parameter sweeps are still empty.

Risk:

- A strategy can be fragile to ATR, RR, stop, session, or spread thresholds while still passing current robustness.

Required response:

- Add rerun-based parameter sweeps, not only trade-PnL adjustment.
- Block PASS when a tiny parameter change destroys expectancy.

### 6. Baselines need stronger fairness checks

Current baseline comparison shows the candidate beats existing baselines, but `random_entry` can produce zero trades due to confidence/filter interactions.

Risk:

- A zero-trade random baseline is too easy to beat.
- Baselines may not match candidate trade frequency, session exposure, or cost exposure.

Required response:

- Add frequency-matched random baselines.
- Add session-matched random baselines.
- Add direction-shuffled and entry-time-shuffled baselines.

## Non-Negotiable Promotion Gates

A strategy can only receive promotion-level `PASS` when all gates below pass.

### Data Gates

- Real broker data only.
- Sample data disabled.
- Broker metadata snapshot present.
- Broker metadata critical fields match config:
  - `point`
  - `digits`
  - `spread`
  - `tick_size`
  - `tick_value`
  - `contract_size`
  - `trade_tick_size`
  - `trade_tick_value`
  - `volume_min`
  - `volume_max`
  - `volume_step`
- No duplicate timestamps.
- No invalid candles.
- Missing-bar policy must not hide material gaps.
- Promotion dataset must cover enough history for non-empty walk-forward splits.

### Execution Realism Gates

- No lookahead.
- Signal execution remains `next_open`.
- Same-bar policy remains conservative.
- Spread cost uses MT5 point/tick semantics correctly.
- Slippage stress must materially affect results.
- Commission must be configurable and included.
- R-multiple must use the same value-per-price-unit logic as PnL and sizing.

### Strategy Viability Gates

- Minimum raw signals: at least 100.
- Minimum approved trades: at least 30 for research, higher for promotion when data expands.
- Rejection rate below configured ceiling.
- Side distribution reviewed; both-side requirement can be relaxed only when the thesis is explicitly directional.
- No excessive reliance on one narrow hour/session unless that is the thesis and it survives holdout.

### Edge Gates

- Positive expectancy after realistic costs.
- Profit factor above threshold.
- Beats relevant baselines.
- Stress expectancy remains positive.
- Max drawdown controlled.
- Walk-forward locked tests present and positive.
- Robustness does not depend on top 1-3 trades.
- Parameter sweeps show a stable neighborhood.

### Human Review Gates

- Every `PASS` must include a written thesis.
- Every threshold/config change must be explained.
- Any change that makes passing easier is suspicious until justified.
- Any agent-generated strategy must be reviewed against leakage, unit mismatch, and overfit.

## Strategy Development Principles

The strategy should be developed thesis-first.

Good thesis examples:

- XAUUSD M15 has continuation after trend pullbacks during London/NewYork when spread is below its session median and volatility is expanding.
- XAUUSD has false breakouts during late NewYork/rollover; excluding that window should improve stress expectancy.
- Compression followed by London volatility expansion has positive expectancy only when ATR percentile is rising and spread percentile is controlled.

Bad thesis examples:

- Increase PF by changing thresholds.
- Try strategies until one passes.
- Shorten the walk-forward split until rounds appear.
- Disable a baseline because it is hard to beat.

Every candidate strategy must specify:

- Market behavior it exploits.
- Sessions where it should work.
- Sessions where it should not trade.
- Volatility/regime condition.
- Spread/cost assumption.
- Entry rule.
- Stop rule.
- Take-profit or exit rule.
- Invalidation condition.

## Development Roadmap

### Phase 1: Evidence Integrity Lockdown

Goal:

Make it impossible to confuse research candidate results with promotion-quality edge.

Tasks:

1. Keep latest cost-model correction.
   - PnL and risk sizing should use `tick_value / tick_size`.
   - Spread cost should use spread points times tick value times volume.
   - Slippage should use the same unit model.

2. Add explicit cost-model tests.
   - Given XAUUSDm spread of 200 points and 0.01 lot, spread cost must be in realistic broker units.
   - Increasing spread or slippage must reduce net PnL materially.
   - Stress backtest must not be nearly identical to base backtest.

3. Keep broker metadata as a hard gate.
   - Do not trust config-only metadata for promotion.
   - Persist every MT5 snapshot into run artifacts.
   - Report mismatched fields clearly.

4. Separate gate levels.
   - `research_candidate`: can pass without full promotion data, but must say it is not proven.
   - `promotion_candidate`: requires walk-forward and full robustness.
   - `live_candidate`: requires paper/shadow evidence after promotion candidate.

Success criteria:

- Full test suite passes.
- A run with missing walk-forward cannot produce promotion PASS.
- Report language distinguishes research candidate from proven edge.

Failure handling:

- If cost correction breaks historical PASS, keep the FAIL.
- If broker metadata changes intraday spread beyond config max, fail with data/execution realism reason.

### Phase 2: Data Expansion And Split Policy

Goal:

Create enough historical coverage to evaluate out-of-sample behavior.

Tasks:

1. Backfill XAUUSDm M15 history.
   - Minimum: 18 months.
   - Preferred: 24-36 months.
   - Keep source as broker/MT5, not mixed unknown sources.

2. Add data coverage report.
   - Start/end timestamps.
   - Number of bars.
   - Missing bars by month.
   - Spread percentiles by month/session.
   - Regime coverage by month.

3. Define split presets.
   - `research_dev`: shorter split for quick iteration, never eligible for promotion.
   - `promotion_default`: 12/3/3 or stricter.
   - `long_history`: longer train/test windows when enough data exists.

4. Write split eligibility rules.
   - If promotion split has zero rounds, verdict must fail `walk_forward_present`.
   - If only research split exists, report must say `candidate_only`.

Success criteria:

- Walk-forward produces non-empty locked test rounds.
- Latest report includes walk-forward summary at top level and inside edge evidence.

Failure handling:

- If MT5 backfill fails, do not lower promotion requirements.
- If data has large gaps, classify result as data-quality limited.

### Phase 3: Diagnostics Before Strategy Tuning

Goal:

Find where expectancy comes from before changing rules.

Tasks:

1. Build diagnostic breakdowns:
   - Session.
   - Hour of day.
   - Day of week.
   - ATR percentile.
   - Realized volatility percentile.
   - Spread percentile.
   - Trend regime.
   - Range regime.
   - Long vs short.
   - Holding time.

2. Add candidate bucket scoring.
   - Trades.
   - Expectancy.
   - PF.
   - Max drawdown.
   - Stress expectancy.
   - Share of total PnL.
   - Stability across months.

3. Flag suspicious buckets.
   - Fewer than 30 trades.
   - Most PnL from top 1-3 trades.
   - Positive only in one month.
   - Dies under spread/slippage stress.

Success criteria:

- Strategy changes are justified by diagnostic evidence.
- No new strategy is accepted only because in-sample PF rose.

Failure handling:

- If no stable positive bucket exists, stop tuning and classify as no edge.

### Phase 4: Thesis-First Strategy Iteration

Goal:

Develop strategy variants from market theses, then test them against fixed gates.

Candidate theses to explore:

1. Pullback trend continuation refinement.
   - Current candidate has many trades and positive base expectancy but fails stress.
   - Improve by reducing cost-sensitive entries:
     - Avoid high spread percentile.
     - Require stronger trend regime.
     - Require ATR percentile above a minimum.
     - Avoid entries too close to rollover.
     - Add tighter invalidation for weak pullbacks.

2. London/NewYork volatility expansion.
   - Trade only when volatility expands after compression.
   - Require session in London or NewYork.
   - Require spread percentile below threshold.
   - Compare directly against session breakout baseline.

3. Mean reversion only in confirmed range regimes.
   - Trade range mean reversion only when ATR percentile is low and range regime persists.
   - Avoid trend regimes.
   - Validate separately from trend continuation.

4. Directional asymmetry test.
   - Test long-only and short-only variants only if diagnostics show persistent asymmetry.
   - Require separate baseline for directional exposure.

Iteration protocol:

1. Write thesis in plain language.
2. Define rule change.
3. Run in-sample research.
4. Run stress.
5. Run walk-forward.
6. Run baselines.
7. Record result.
8. Decide:
   - Keep.
   - Modify.
   - Reject.

Prohibited iteration behavior:

- Changing gate thresholds to pass.
- Switching strategy after looking at final holdout without resetting the holdout.
- Using test-window performance to tune parameters.
- Deleting bad runs from evidence.

Success criteria:

- A candidate improves stressed expectancy and walk-forward behavior, not only base PF.

Failure handling:

- If a rule improves base but hurts stress, reject or mark as cost-sensitive.
- If a rule improves in-sample but fails walk-forward, reject or keep only as research note.

### Phase 5: Robustness And Stress Expansion

Goal:

Make fragile strategies fail loudly.

Required robustness reruns:

- Spread multiplier: 1.25x, 1.5x, 2x, 3x.
- Slippage multiplier: 1.5x, 2x, 3x.
- Commission: 2, 5, 10 per lot or broker-relevant values.
- ATR threshold sweep.
- RR/TP sweep.
- Time stop sweep.
- Session filter sweep.
- Spread percentile threshold sweep.

Required dependency tests:

- Remove best 1 trade.
- Remove best 3 trades.
- Double worst 1 trade.
- Double worst 3 trades.
- Monte Carlo trade order shuffle.
- Monthly PnL concentration.

Pass criteria:

- Expectancy remains positive under configured stress.
- PF remains above minimum under reasonable stress.
- Removing top trades does not erase the edge.
- Neighboring parameter settings remain viable.

Failure handling:

- If only one exact parameter setting works, mark as overfit.
- If top 1-3 trades explain most returns, mark as trade-dependent.
- If stress flips negative, do not promote.

### Phase 6: Baseline Upgrade

Goal:

Make "beats baseline" meaningful.

Baselines to add:

- No trade.
- ATR breakout.
- Session breakout.
- MA crossover.
- Frequency-matched random entry.
- Session-matched random entry.
- Direction-matched random entry.
- Entry-time shuffle with same exits.
- Side-flip variant of the same strategy.

Comparison rules:

- Candidate must beat baselines on total return and expectancy.
- Candidate must beat at least one active-trading baseline under stress.
- Zero-trade baselines count only for sanity, not as sufficient evidence.

Failure handling:

- If a baseline beats the candidate, classify as no edge or weak edge.
- If random baselines have zero trades due to filters, fix the baseline design.

### Phase 7: Agent/Gemini Controlled Optimization Protocol

Goal:

Allow Gemini to help without turning it into a gate-gaming optimizer.

Gemini may:

- Read diagnostics.
- Propose market theses.
- Propose rule changes.
- Add tests.
- Improve reporting.
- Run research windows.
- Summarize failed runs.

Gemini may not:

- Lower promotion thresholds.
- Disable stress, baselines, walk-forward, or broker metadata checks.
- Change holdout windows after seeing results.
- Mark metadata confirmed without live snapshot comparison.
- Delete or hide losing runs.
- Change test expectations only to bless weaker behavior.

Loop protocol:

1. Human or orchestrator locks config gates.
2. Gemini proposes one thesis at a time.
3. Gemini implements the smallest rule change.
4. Run tests.
5. Run research backtest.
6. Run stress.
7. Run walk-forward.
8. Save evidence.
9. Gemini writes a candid conclusion.
10. Human reviews whether to continue, reject, or promote to paper testing.

Stop conditions:

- Three consecutive thesis variants fail stress.
- Walk-forward is empty.
- Tests fail.
- Any gate is weakened.
- Improvement exists only in in-sample data.

Success condition:

- Candidate passes locked gates without changing them.

### Phase 8: Promotion To Paper/Shadow

Goal:

Only promote after backtest evidence survives all gates.

Pre-paper requirements:

- Broker metadata confirmed.
- Full tests pass.
- Promotion walk-forward has non-empty rounds.
- Base PF and expectancy pass.
- Stress PF and expectancy pass.
- Robustness pass.
- Baselines beaten.
- Report states why the edge should exist.

Paper/shadow requirements:

- No real orders in shadow.
- Record every decision, rejection, and hypothetical fill.
- Compare live spread/slippage against backtest assumptions.
- Monitor missed bars and feed quality.
- Track drift between backtest expected behavior and shadow behavior.

Failure handling:

- If live spreads are worse than assumptions, return to cost model.
- If trade frequency differs materially, inspect filters and session assumptions.
- If slippage exceeds stress model, fail promotion.

## Scenario Playbook

### Scenario A: Base result PASS, stress FAIL

Interpretation:

- Edge is execution-cost sensitive.

Action:

- Do not promote.
- Reduce low-quality entries.
- Improve spread/session filters.
- Recheck cost model.

### Scenario B: Base PASS, stress PASS, walk-forward empty

Interpretation:

- Candidate only, not proven.

Action:

- Backfill more data.
- Do not lower promotion split.
- Optionally run research split labeled as non-promotion.

### Scenario C: Base PASS, walk-forward FAIL

Interpretation:

- Likely overfit or regime-specific.

Action:

- Diagnose which rounds fail.
- Check regime differences.
- Avoid tuning on test rounds.
- If thesis no longer holds, reject.

### Scenario D: Base FAIL, diagnostics show positive bucket

Interpretation:

- Possible narrow thesis.

Action:

- Convert bucket into explicit rule.
- Require enough trades.
- Test under stress and walk-forward.

### Scenario E: Strategy beats weak baselines only

Interpretation:

- Baseline test is not strong enough.

Action:

- Add frequency/session/direction matched random baselines.
- Do not claim edge until active baselines are beaten.

### Scenario F: Robustness fails after removing top trades

Interpretation:

- PnL depends on a few outliers.

Action:

- Reject promotion.
- Analyze if outliers correspond to repeatable thesis.
- Require more data.

### Scenario G: Full tests fail after config or strategy change

Interpretation:

- System integrity is broken.

Action:

- Stop strategy evaluation.
- Fix tests or revert bad change.
- Do not interpret backtest results until tests pass.

### Scenario H: Gemini finds a PASS by changing config

Interpretation:

- The gate may have been gamed.

Action:

- Diff config against locked baseline.
- Revert threshold reductions.
- Rerun with locked promotion config.
- Treat the run as invalid unless every easier change is justified by broker realism.

## Reporting Requirements

Every evidence report should include:

- Run id.
- Config hash.
- Git commit hash.
- Data range.
- Data quality.
- Broker metadata comparison.
- Strategy thesis.
- Strategy configuration.
- Primary metrics.
- Baseline metrics.
- Stress metrics.
- Walk-forward summary.
- Robustness summary.
- Promotion gate status.
- Failure reasons.
- Human-readable conclusion:
  - `proven_edge`
  - `candidate_edge`
  - `no_edge`
  - `invalid_evidence`

## Immediate Next Tasks

1. Keep the latest cost model correction and verify it with explicit unit tests.
2. Fix report wiring so `walk_forward_summary` is populated when walk-forward runs.
3. Backfill enough M15 data for non-empty promotion walk-forward splits.
4. Add a `research_dev` split mode that cannot produce promotion PASS.
5. Add frequency/session-matched random baselines.
6. Add rerun-based parameter sweeps.
7. Run the latest `pullback_trend_continuation` candidate through:
   - Base backtest.
   - Bad stress.
   - Stress stress.
   - Walk-forward.
   - Robustness.
   - Active baselines.
8. If it still fails stress, diagnose which trade classes collapse under cost.
9. Build the next strategy variant only from that diagnostic evidence.

## Definition Of Real Edge

A strategy is considered real edge only when:

- It is based on a plausible market thesis.
- It survives realistic broker costs.
- It passes locked out-of-sample walk-forward tests.
- It beats meaningful active baselines.
- It remains positive under stress.
- It is not dependent on a few lucky trades.
- It remains viable under nearby parameter settings.
- It is observable in paper/shadow trading before live exposure.

Until then, the correct label is `candidate_edge` or `no_edge`, not proven edge.

# Real Edge Development Plan

Project: `algo_trade`  
Scope: rule-based algorithmic trading only  
Out of scope: ML training, ML inference, online learning, model research

## Positioning

This project should not try to look sophisticated by adding model complexity. Its job is to prove or reject rule-based trading edges with discipline.

A strategy is not considered to have edge because it produces a positive backtest once. A strategy has candidate edge only when it survives realistic data, costs, baselines, walk-forward testing, and robustness checks.

Current system status:

- The platform can run a stateful backtest.
- Real-data backfill and sample-data rejection exist.
- The latest real-data run produced `edge_evidence.verdict = FAIL`.
- That failure is useful: the system is now rejecting unsupported edge claims instead of producing cosmetic results.

## Non-Negotiable Rule

No strategy may advance toward live trading unless:

- Real broker historical data is used.
- Sample fixtures are not used as evidence.
- The strategy produces enough trades to evaluate.
- It beats simple baselines after costs.
- It passes slippage/spread stress.
- It passes walk-forward out-of-sample testing.
- It has a clear market thesis that can be falsified.

## Priority 1: Data And Metadata Audit

Before improving strategy logic, verify that data units and symbol metadata are correct.

### Required Checks

- Confirm MT5 `spread` unit for `XAUUSDm`.
- Confirm `pip_size`, `tick_size`, `pip_value`, and `contract_size`.
- Confirm `average_spread` and `max_spread_points` from real broker data.
- Compute spread distribution by session.
- Confirm weekend/session gaps are classified correctly.
- Confirm timestamp semantics are candle-open time.

### Acceptance Criteria

- Backtest does not reject most signals because of a unit mismatch.
- Spread filter uses real distribution, not a guessed constant.
- Data quality report includes missing bars, spread percentiles, and source path.

## Priority 2: Strategy Viability Gate

The system should fail fast when a strategy/config is not evaluable.

### Add Gate

```text
strategy_viability:
  min_raw_signals: 100
  min_approved_trades: 30
  max_rejection_rate: 0.95
  require_both_sides: false
```

### Failure Examples

- `0` trades over 20,000 bars.
- Almost every raw signal rejected by spread filter.
- Only one trade drives the entire result.
- Strategy trades only during obviously bad spread windows.

### Acceptance Criteria

- Edge report explicitly distinguishes:
  - no edge
  - insufficient evidence
  - invalid configuration
  - data quality failure

## Priority 3: Session And Regime Features

Rule-based edge usually lives in specific market conditions, not all candles.

### Add Features

- session label: Asia, London, New York, rollover
- hour of day
- day of week
- ATR percentile
- realized volatility percentile
- trend regime using EMA slope or ADX
- range regime using Bollinger width or ATR compression
- spread percentile by session

### Acceptance Criteria

- Reports break down performance by session and regime.
- Strategies can filter by session and regime from config.
- Rollover and extreme-spread windows can be excluded.

## Priority 4: Build Rule-Based Strategy Thesis Library

Each strategy must have a clear thesis before implementation.

### Candidate 1: London/NY Volatility Breakout

Thesis:

XAUUSD may trend after liquidity expands during London/New York overlap, especially when prior range compression is followed by breakout.

Rules:

- Trade only London/New York sessions.
- Require ATR percentile above threshold or volatility expansion.
- Enter breakout above prior rolling high or below prior rolling low.
- Avoid rollover and high-spread windows.
- Stop = ATR multiple.
- Take profit = fixed R multiple or trailing ATR.
- Time stop if breakout stalls.

Evidence Needed:

- Positive expectancy after spread/slippage.
- Beats ATR breakout baseline.
- Stable across walk-forward periods.

### Candidate 2: Pullback Trend Continuation

Thesis:

In trending regimes, pullbacks toward EMA/ATR bands may offer better R:R than chasing breakouts.

Rules:

- Require trend regime.
- Long only when fast EMA > slow EMA and slope positive.
- Wait for pullback toward EMA or ATR band.
- Enter after candle closes back in trend direction.
- Stop beyond pullback low/high.
- TP by R multiple or structure.

Evidence Needed:

- Better expectancy than MA crossover.
- Lower drawdown than breakout strategy.
- Works in trend regime, fails or is disabled in range regime.

### Candidate 3: Range Mean Reversion

Thesis:

During low-volatility range regimes, extreme moves away from mean may revert before session expansion.

Rules:

- Require range regime and low ATR percentile.
- Avoid London/NY breakout windows unless explicitly tested.
- Long near lower band with RSI oversold.
- Short near upper band with RSI overbought.
- Stop beyond band/structure.
- Conservative TP near midline.

Evidence Needed:

- Positive expectancy only in range regime.
- Disabled during trend/high-vol regime.
- Survives slippage and spread stress.

## Priority 5: Baseline Framework

Baselines should be hard enough to embarrass weak strategies.

### Required Baselines

- no trade
- random entry with same exits
- moving average crossover
- ATR breakout
- session breakout
- simple buy-and-hold where applicable

### Acceptance Criteria

- Primary strategy must beat relevant baselines on:
  - total return
  - expectancy
  - max drawdown
  - profit factor
  - cost-adjusted R multiple

## Priority 6: Walk-Forward Testing

Backtest evidence is incomplete without out-of-sample validation.

### Default Split

```text
train: 12 months
validation: 3 months
test: 3 months
step: 3 months
```

### Rules

- Tune thresholds only on train/validation.
- Lock test results.
- Aggregate all rounds.
- Report worst round, not just average.

### Acceptance Criteria

- Strategy must remain positive or controlled in most test rounds.
- No single lucky period should dominate the result.
- Parameter choices should not drift wildly across rounds.

## Priority 7: Robustness Tests

A strategy should not depend on one perfect setting.

### Required Tests

- slippage stress
- spread stress
- commission sensitivity
- ATR multiplier sweep
- TP:R sweep
- session filter sweep
- remove best N trades
- double worst N losses
- Monte Carlo trade shuffle

### Acceptance Criteria

- Edge does not disappear under normal cost stress.
- Result is not dependent on top 1-3 trades.
- Neighboring parameters remain viable.

## Priority 8: Reporting

The system should explain why a strategy passed or failed.

### Required Report Sections

- data source and date range
- data quality summary
- strategy configuration
- edge verdict
- strategy viability
- baseline comparison
- cost analysis
- session/regime breakdown
- trade distribution
- R-multiple distribution
- drawdown curve
- rejection reason summary
- walk-forward summary
- robustness summary

## Promotion Gates

### Gate 1: Research Candidate

- real data loaded
- data quality passes
- strategy viability passes
- at least 30 trades
- decision logs complete

### Gate 2: Backtest Candidate

- edge evidence passes on in-sample data
- beats baselines
- costs included
- no-lookahead tested
- TP/SL/time-stop tested

### Gate 3: Walk-Forward Candidate

- walk-forward complete
- OOS results positive or controlled
- worst round acceptable
- no single period dominates

### Gate 4: Paper Candidate

- paper mode works
- reconciliation works
- order logs match expected lifecycle
- no live order bypass possible

### Gate 5: Micro-Live Candidate

- small risk only
- manual review process ready
- emergency stop tested
- account/server checks pass
- no unresolved reconciliation warnings

## Immediate Implementation Order

1. Audit spread units and symbol metadata.
2. Add strategy viability gate.
3. Add session/regime features.
4. Add session breakout baseline.
5. Implement London/NY volatility breakout strategy.
6. Add walk-forward runner.
7. Add robustness suite.
8. Generate edge report artifact per run.

## Final Principle

The system should be allowed to say:

```text
No edge proven.
```

That is not failure. That is the platform doing its job.

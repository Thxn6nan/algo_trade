# Real Edge Improvement Context

Last updated: 2026-05-05

## Current Evidence State

The latest real-data backtest can evaluate the strategy, but it still correctly refuses to promote the result as edge.

Recent evidence run:

- Command: `python run.py --mode backtest --symbol XAUUSDm --timeframe M15`
- Run id: `bt-3e96a9e29438`
- Report artifacts:
  - `runs/bt-3e96a9e29438/edge_report.json`
  - `runs/bt-3e96a9e29438/edge_report.md`
- Edge verdict: `FAIL`
- Failure class: `data_quality_failure`
- Primary blocker: `broker_metadata_unconfirmed`

This does not mean the OHLCV CSV is unusable. The real data file passes core validation:

- Real broker CSV is loaded from `data/XAUUSDm_M15.csv`.
- 20,000 bars are available.
- Duplicate timestamps: 0.
- Invalid candles: 0.
- Median spread: 160.
- P95 spread: 280.
- Timestamp semantics: candle open time.

The failure means the run is not eligible for promotion because broker symbol metadata has not been confirmed from MT5.

## Why Promotion Is Blocked

The system must verify broker metadata before trusting costs, sizing, and R-multiples. For `XAUUSDm`, the following fields need a live MT5 snapshot and comparison against config:

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

Without this confirmation, a profitable backtest could be caused by a unit mismatch rather than real edge.

## Current Strategy Result

The current strategy is evaluable but does not prove edge.

- Raw signals: 4,560.
- Approved trades: 289.
- Rejection rate: 92.82%, below the 95% ceiling.
- Strategy viability: passed.
- Profit factor: 0.972, below the 1.15 requirement.
- Expectancy: negative.
- It does not beat relevant baselines.
- Slippage stress still has negative expectancy.

If broker metadata is confirmed and these performance metrics remain unchanged, the likely failure class should move from `data_quality_failure` to `no_edge`.

## Recommended Development Order

1. Add MT5 symbol metadata snapshot ingestion.
   - Add a read-only MT5 method that calls `symbol_info("XAUUSDm")`.
   - Persist the snapshot into the run directory.
   - Compare broker metadata with `config/default.yaml`.
   - Clear `broker_metadata_unconfirmed` only when critical fields match.

2. Expand data coverage for walk-forward testing.
   - Current default split is 12 months train, 3 months validation, 3 months test, 3 months step.
   - Current local data is too short for a non-empty default walk-forward run.
   - Either backfill at least 18+ months or use a shorter research-only dev split.

3. Deepen session and regime diagnostics.
   - Break performance down by session, hour, day of week, ATR percentile, spread percentile, trend regime, and range regime.
   - Look for narrow conditions where expectancy is positive after costs.
   - Treat isolated positive buckets as candidate theses, not proven edge.

4. Develop thesis-first rule strategies.
   - Start with London/New York volatility breakout.
   - Require volatility expansion or ATR percentile strength.
   - Avoid rollover and high-spread windows.
   - Compare directly against ATR breakout and session breakout baselines.

5. Expand robustness into rerun-based stress tests.
   - Current robustness summarizes trade dependency and Monte Carlo shuffle.
   - Next version should rerun the backtest under spread, slippage, commission, ATR, TP:R, and session-filter sweeps.

6. Promote only after evidence survives all gates.
   - Broker metadata confirmed.
   - Strategy viability passed.
   - Positive expectancy after costs.
   - Profit factor above threshold.
   - Beats relevant baselines.
   - Walk-forward out-of-sample results are controlled.
   - Robustness does not depend on the top 1-3 trades.

## Principle

The goal is not to make the backtest green. The goal is to make unsupported edge claims fail loudly and make real candidate edge hard to fake.

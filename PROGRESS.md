# Progress

Last updated: 2026-05-05

## Current Status

The project has a runnable Python modular trading core for the first architecture phase: **Backtest + Shadow + Paper + guarded Micro-Live/Live mode** for **MT5 CFD/FX-style instruments**.

Implemented:

- Python package skeleton under `algo_trade/`
- CLI entrypoint via `run.py`
- YAML config loading and validation with deterministic `config_hash`
- Symbol registry for CFD/FX metadata such as pip size, pip value, lot step, max lot, average spread, and magic number
- Historical CSV market data loader that prefers real broker data and refuses sample fixtures unless explicitly enabled
- MT5 backfill path for missing or incomplete historical data, persisted as local real CSV outside git
- OHLCV validator with fail-fast checks for missing columns, invalid prices, duplicated/unsorted timestamps, negative volume, and negative spread
- Technical feature pipeline with schema lock and per-symbol/timeframe rolling calculations
- Baseline strategies: buy-and-hold, no-trade, random entry, moving average crossover, RSI mean reversion, and ATR breakout
- Model-probability strategy adapter for upstream model outputs
- Signal filtering for confidence, spread, risk/reward, and volatility availability
- Risk engine with position sizing, max drawdown guard, daily loss guard, max position checks, and kill-switch snapshot
- Decision engine that converts raw signals into approved/rejected/held/halted decisions with reason codes
- Stateful backtest engine with next-open execution, no-lookahead default behavior, TP/SL checks, conservative same-bar TP/SL policy, time stop, and trading costs
- JSONL logs and SQLite state store per run with common structured log fields
- Required storage tables for runs, signals, decisions, orders, fills, positions, trades, risk events, reconciliation events, model/config versions, and symbol snapshots
- Performance report with return, win rate, profit factor, expectancy, drawdown, R multiples, costs, and rejected-signal summary
- Edge evidence gate with minimum bars/trades, real-data requirement, baseline comparison, slippage stress checks, strategy viability, and failure taxonomy
- Symbol/data audit layer with source path, broker metadata status, spread percentiles, session spread distribution, timestamp semantics, and promotion blockers
- Strategy viability gate with raw signal count, approved trades, rejection rate, side counts, rejection reason summary, and explicit insufficient-evidence/invalid-configuration classification
- `technical_v2` feature schema with session, hour/day, ATR percentile, realized volatility percentile, trend/range regime, rollover flag, and spread percentile by session
- Config-driven session, regime, and spread-percentile filters
- Rule-based strategy library entries for session breakout, London/New York volatility breakout, pullback trend continuation, and range mean reversion
- Walk-forward runner with locked test-window split metadata
- Robustness summary for trade-dependency and Monte Carlo shuffle checks
- Per-run `edge_report.json` and `edge_report.md` artifacts
- Shadow runner safety shell where order submission is disabled by construction
- Paper/live one-cycle runner with MT5 data interface, paper order recording, live confirmation/account/server/env guards, emergency-stop guard, and startup reconciliation halt
- Unit tests for validation, feature schema, decisions, risk, backtest behavior, same-bar policy, and shadow execution guard

## Verification

Verified commands:

```bash
python -m unittest discover -s tests -v
python run.py --mode backtest --symbol XAUUSDm --timeframe M15
python run.py --mode walk_forward --symbol XAUUSDm --timeframe M15
python run.py --mode shadow --symbol XAUUSDm --timeframe M15
```

The test suite currently passes with 36 tests.

## Important Safety State

- Supported modes are `research`, `backtest`, `walk_forward`, `shadow`, `paper`, `micro_live`, and `live`.
- `shadow.send_orders` must remain `false`.
- `MT5ExecutionAdapter.submit_order()` raises unless order sending is explicitly enabled.
- `paper` must keep `execution.send_orders=false`.
- `micro_live` and `live` require explicit order sending config, live confirmation phrase, matching `.env` account/server values, non-research risk profile, and no emergency stop file.
- Backtest execution is fixed to `next_open` to prevent lookahead mistakes.
- Same-bar TP/SL policy is fixed to `conservative`.
- Default backtest requires real data, at least 5,000 bars, and attempts MT5 backfill up to 20,000 bars when local data is missing or incomplete.
- Broker metadata absence does not block a backtest run, but it blocks promotion through the edge/promotion gates as `data_quality_failure`.
- `model_probability` remains in code for compatibility but is disabled by default when `strategy_library.rule_based_only=true`.
- A backtest can finish with `edge_evidence.verdict = FAIL`; that is the intended result when the evidence does not support an edge.

## Generated Artifacts

Backtest and shadow smoke runs write output under `runs/`.

Each run may include:

- `signals.jsonl`
- `decisions.jsonl`
- `orders.jsonl`
- `fills.jsonl`
- `positions.jsonl`
- `trades.jsonl`
- `reconciliation.jsonl`
- `system_events.jsonl`
- `edge_report.json`
- `edge_report.md`
- `state.sqlite`

These are useful for inspection, but future cleanup may choose to ignore or archive generated run folders.

## Next Recommended Work

1. Add broker symbol metadata snapshot ingestion from MT5 so `broker_metadata_confirmed` can pass without manual config edits.
2. Add enough historical coverage for non-empty default walk-forward windows.
3. Expand robustness from trade-dependency checks into full backtest reruns for spread, commission, and parameter sweeps.
4. Add strategy research work that can actually pass the edge evidence gate on out-of-sample data.
5. Add shadow-mode live signal generation over MT5 data, still with order submission disabled.
6. Add richer reconciliation against persisted local positions and broker magic numbers.
7. Add documentation for risk settings, symbol registry fields, and backtest assumptions.
8. Add packaging/dev workflow decisions such as dependency lockfile and CI.

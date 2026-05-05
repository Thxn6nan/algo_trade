# Progress

Last updated: 2026-05-05

## Current Status

The project has a runnable Python modular trading core for the first architecture phase: **Backtest + Shadow mode** for **MT5 CFD/FX-style instruments**.

Implemented:

- Python package skeleton under `algo_trade/`
- CLI entrypoint via `run.py`
- YAML config loading and validation with deterministic `config_hash`
- Symbol registry for CFD/FX metadata such as pip size, pip value, lot step, max lot, average spread, and magic number
- Historical CSV market data loader
- OHLCV validator with fail-fast checks for missing columns, invalid prices, duplicated/unsorted timestamps, negative volume, and negative spread
- Technical feature pipeline with schema lock
- Baseline strategies: buy-and-hold, random entry, moving average crossover, RSI mean reversion, and ATR breakout
- Signal filtering for confidence, spread, risk/reward, and volatility availability
- Risk engine with position sizing, max drawdown guard, daily loss guard, max position checks, and kill-switch snapshot
- Decision engine that converts raw signals into approved/rejected/held/halted decisions with reason codes
- Stateful backtest engine with next-open execution, no-lookahead default behavior, TP/SL checks, conservative same-bar TP/SL policy, time stop, and trading costs
- JSONL logs and SQLite state store per run
- Performance report with return, win rate, profit factor, expectancy, drawdown, R multiples, costs, and rejected-signal summary
- Shadow runner safety shell where order submission is disabled by construction
- Unit tests for validation, feature schema, decisions, risk, backtest behavior, same-bar policy, and shadow execution guard

## Verification

Verified commands:

```bash
python -m unittest discover -s tests -v
python run.py --mode backtest --symbol XAUUSDm --timeframe M15
python run.py --mode shadow --symbol XAUUSDm --timeframe M15
```

The test suite currently passes with 13 tests.

## Important Safety State

- `research`, `backtest`, `walk_forward`, and `shadow` are the only supported modes.
- `paper` and `live` are intentionally unavailable.
- `shadow.send_orders` must remain `false`.
- `MT5ExecutionAdapter.submit_order()` raises unless order sending is explicitly enabled, and live submission is still not implemented.
- Backtest execution is fixed to `next_open` to prevent lookahead mistakes.
- Same-bar TP/SL policy is fixed to `conservative`.

## Generated Artifacts

Backtest and shadow smoke runs write output under `runs/`.

Each run may include:

- `signals.jsonl`
- `decisions.jsonl`
- `orders.jsonl`
- `trades.jsonl`
- `system_events.jsonl`
- `state.sqlite`

These are useful for inspection, but future cleanup may choose to ignore or archive generated run folders.

## Next Recommended Work

1. Add real historical data ingestion paths beyond the sample CSV.
2. Add walk-forward orchestration rather than treating it as a backtest alias.
3. Add richer data quality reporting for missing sessions and broker timezone metadata.
4. Add baseline comparison runner across all baseline strategies.
5. Add robustness tests: cost stress, slippage stress, parameter sensitivity, Monte Carlo trade shuffle.
6. Add a real MT5 market-data adapter for shadow mode, still with order submission disabled.
7. Add documentation for risk settings, symbol registry fields, and backtest assumptions.
8. Add packaging/dev workflow decisions such as dependency lockfile and CI.

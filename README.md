# algo_trade

Algorithmic trading core for a solo-developer quant platform.

The project currently implements a **Python modular CLI** for **Backtest, Shadow, Paper, and guarded Live mode** targeting **MT5 CFD/FX-style instruments**. The goal is not to chase a beautiful backtest. The goal is to build a trading system that validates data, prevents lookahead mistakes, forces risk checks, logs every decision, and can grow toward broker execution safely.

## Scope

In scope now:

- Historical OHLCV data loading from CSV
- Real MT5 bar reads for paper/live runs
- Market data validation
- Technical feature pipeline
- Feature schema lock
- Baseline strategies
- Signal generation
- Signal filters
- Risk-controlled trade decisions
- Stateful backtesting with TP/SL/time stop
- Realistic cost hooks for spread, slippage, and commission
- JSONL and SQLite logs
- Performance reporting
- Shadow-mode safety shell with order submission disabled
- Paper-mode decision/order logging without broker submission
- Live-mode MT5 order submission behind explicit config and `.env` guards

Out of scope for the current phase:

- Online learning
- High-frequency trading infrastructure
- Exchange co-location
- Deep ML training internals
- External macro or sentiment API integrations

## Safety Defaults

The current implementation intentionally supports only:

```text
research
backtest
walk_forward
shadow
paper
live
```

Backtest safety defaults:

- Signals generated on candle `t` execute at the next candle open.
- Same-bar TP/SL ambiguity uses the conservative policy: stop loss first.
- Every approved entry decision must have a stop loss.
- Every signal produces a logged decision: approved, rejected, held, or halted.

Shadow safety defaults:

- `shadow.send_orders` must be `false`.
- The execution adapter raises if order submission is attempted.

Paper/live safety defaults:

- `paper` uses MT5 market data and records paper orders only.
- `live` requires `execution.send_orders: true`, `execution.live_enabled: true`, `execution.confirm_live: I_UNDERSTAND_LIVE_TRADING_RISK`, and `SYSTEM_MODE=live` in `.env`.

## Project Layout

```text
algo_trade/          Source package
config/default.yaml  Default runnable config
data/                Sample historical data
runs/                Generated run logs and SQLite state
tests/               Unit tests
run.py               CLI entrypoint
SPEC.md             System specification
BASICCONCEPT.md     Trading concept notes
ABOUT.md            Agent-facing project context
PROGRESS.md         Current implementation progress
```

## Quick Start

Install dependencies in your preferred Python 3.12 environment:

```bash
pip install pandas numpy pyyaml
```

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Run a sample backtest:

```bash
python run.py --mode backtest --symbol XAUUSDm --timeframe M15
```

Run shadow safety mode:

```bash
python run.py --mode shadow --symbol XAUUSDm --timeframe M15
```

Run one paper cycle against MT5 data:

```bash
python run.py --mode paper --symbol XAUUSDm --timeframe M15
```

Live mode uses the same command shape, but only after the live guards in `config/default.yaml` and `.env` are deliberately enabled.

Outputs are written under `runs/<run_id>/`.

## Configuration

Start with:

```text
config/default.yaml
```

Important groups:

- `mode`: selected operating mode
- `paths`: data and output directories
- `symbols`: enabled symbols and symbol metadata
- `risk`: risk caps, max lot, kill-switch behavior
- `signal`: strategy and thresholds
- `filters`: spread and volatility filters
- `backtest`: initial equity, execution policy, cost model
- `shadow`: broker target and order-sending safety flag
- `real_data`: MT5 bar count and real-data validation tolerance
- `real_data.allow_session_gaps`: allows normal broker weekend/session gaps and short daily maintenance gaps while still rejecting unexpected weekday gaps above tolerance
- `execution`: paper/live broker settings and live-trading guards

## Contributing Guidelines

- Keep the system modular: signal generation must not send orders, and risk must not be bypassed.
- Add tests for any change touching validation, features, signals, decisions, risk, backtest execution, or shadow safety.
- Preserve explicit reason codes for rejected or approved decisions.
- Do not add live trading behavior without a dedicated phase plan and safety review.
- Keep generated run outputs out of source changes unless they are intentionally used as fixtures.

## Current Status

See `PROGRESS.md` for the latest implementation status and recommended next work.

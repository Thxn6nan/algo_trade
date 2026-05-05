# About This Project For Agents

This repository is an algorithmic trading core for a solo-developer quant platform. The current target is **MT5 CFD/FX**, starting with **Backtest + Shadow mode** only.

The central rule: build a trading system that is harder to fool than a prediction script. Every signal must be auditable, risk-controlled, and logged before it can become any trade decision.

## Current Architecture

Main flow:

```text
Config
  -> Symbol Registry
  -> Market Data Provider
  -> Data Validator
  -> Feature Pipeline
  -> Strategy / Signal Generator
  -> Signal Filters
  -> Risk Engine
  -> Trade Decision
  -> Backtest Engine or Shadow Runner
  -> State Store + Logs
  -> Performance Report
```

Core directories and files:

- `algo_trade/`: source package
- `config/default.yaml`: runnable default config and safety defaults
- `data/sample_XAUUSDm_M15.csv`: sample historical OHLCV data
- `tests/`: stdlib `unittest` suite
- `run.py`: CLI entrypoint
- `SPEC.md`: high-level trading-system specification
- `BASICCONCEPT.md`: educational concept notes
- `PROGRESS.md`: current implementation status and next work
- `README.md`: contributor-facing overview

## Agent Rules

- Follow the repo instruction in `AGENTS.md`: shell commands should be prefixed with `rtk` where possible.
- Preserve safety defaults unless explicitly asked to change the project phase.
- Do not add live order submission as a drive-by improvement.
- Do not allow `paper` or `live` modes to bypass the current safety gate.
- Keep signal, decision, risk, execution, and logging boundaries separate.
- Prefer deterministic behavior and explicit reason codes over clever opaque logic.
- Use focused tests for any behavior change touching validation, risk, decisions, backtest execution, or shadow safety.

## Current Safety Defaults

- Supported modes: `research`, `backtest`, `walk_forward`, `shadow`
- Disabled modes: `paper`, `live`
- Shadow mode: `send_orders=false`
- Backtest execution: signal on candle `t`, simulated entry at next candle open
- Same-bar TP/SL: conservative, SL first
- Live execution adapter: present only as a guarded interface/stub

## Implementation Notes

- The project currently uses Python 3.12.
- Dependencies used by the implementation are `pandas`, `numpy`, and `pyyaml`.
- Tests use the standard library `unittest`, not pytest.
- Runtime outputs are stored under `runs/<run_id>/`.
- SQLite stores table payloads as JSON text for simple auditability.
- JSONL logs mirror important streams for easy inspection.

## Definition Of Done For Near-Term Changes

A change is not complete until:

- Relevant tests pass with `python -m unittest discover -s tests -v`.
- CLI smoke tests still work for backtest and shadow when the change touches core flow.
- Safety assumptions remain documented if changed.
- New trading decisions include reason codes.
- Any new data, feature, or model behavior has validation before use.

from __future__ import annotations

import argparse
import json
from pathlib import Path

from algo_trade.backtest import BacktestEngine
from algo_trade.config import load_config
from algo_trade.data import HistoricalDataProvider
from algo_trade.shadow import ShadowRunner
from algo_trade.strategies import get_strategy
from algo_trade.symbols import SymbolRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Algorithmic trading core CLI")
    parser.add_argument("--config", default="config/default.yaml", help="Path to YAML config")
    parser.add_argument("--mode", choices=["research", "backtest", "walk_forward", "shadow"], help="Override config mode")
    parser.add_argument("--symbol", help="Symbol to run")
    parser.add_argument("--timeframe", default="M15", help="Primary timeframe")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.mode:
        config.raw["mode"]["name"] = args.mode
    registry = SymbolRegistry.from_config(config.raw["symbols"])
    symbol = args.symbol or config.enabled_symbols[0]

    if config.mode in {"backtest", "walk_forward", "research"}:
        provider = HistoricalDataProvider(config.data_dir)
        frame = provider.load(symbol, args.timeframe)
        strategy = get_strategy(config.raw["signal"].get("strategy", "atr_breakout"))
        result = BacktestEngine(config, registry, strategy).run(frame, symbol)
        print(json.dumps({"run_id": result.run_id, "run_dir": str(result.run_dir), "report": result.report.to_record()}, indent=2, default=str))
        return 0

    if config.mode == "shadow":
        run_id = ShadowRunner(config).run_once()
        print(json.dumps({"run_id": run_id, "mode": "shadow", "send_orders": False}, indent=2))
        return 0

    raise ValueError(f"Unsupported mode {config.mode!r}")

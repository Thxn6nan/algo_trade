from __future__ import annotations

import argparse
import json
from pathlib import Path

from algo_trade.backtest import BacktestEngine
from algo_trade.config import load_config, with_mode
from algo_trade.data import load_backtest_data
from algo_trade.edge import build_edge_evidence
from algo_trade.mt5_gateway import MT5Gateway
from algo_trade.realtime import RealtimeRunner
from algo_trade.shadow import ShadowRunner
from algo_trade.strategies import get_strategy
from algo_trade.symbols import SymbolRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Algorithmic trading core CLI")
    parser.add_argument("--config", default="config/default.yaml", help="Path to YAML config")
    parser.add_argument("--mode", choices=["research", "backtest", "walk_forward", "shadow", "paper", "micro_live", "live"], help="Override config mode")
    parser.add_argument("--symbol", help="Symbol to run")
    parser.add_argument("--timeframe", default="M15", help="Primary timeframe")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.mode:
        config = with_mode(config, args.mode)
    registry = SymbolRegistry.from_config(config.raw["symbols"])
    symbol = args.symbol or config.enabled_symbols[0]
    strategy = get_strategy(config.raw["signal"].get("strategy", "atr_breakout"))

    if config.mode in {"backtest", "walk_forward", "research"}:
        frame = load_backtest_data(config, symbol, args.timeframe)
        result = BacktestEngine(config, registry, strategy).run(frame, symbol)
        edge_evidence = build_edge_evidence(config, registry, frame, symbol, strategy, result)
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "run_dir": str(result.run_dir),
                    "report": result.report.to_record(),
                    "edge_evidence": edge_evidence.to_record(),
                },
                indent=2,
                default=str,
            )
        )
        return 0

    if config.mode == "shadow":
        run_id = ShadowRunner(config).run_once()
        print(json.dumps({"run_id": run_id, "mode": "shadow", "send_orders": False}, indent=2))
        return 0

    if config.mode in {"paper", "micro_live", "live"}:
        gateway = MT5Gateway(env_path=config.raw["execution"].get("env_path", ".env"))
        result = RealtimeRunner(config, registry, strategy, gateway).run_once(symbol, args.timeframe)
        print(json.dumps(result.__dict__, indent=2, default=str))
        return 0

    raise ValueError(f"Unsupported mode {config.mode!r}")

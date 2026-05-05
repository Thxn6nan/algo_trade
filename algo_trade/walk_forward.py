from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from algo_trade.backtest import BacktestEngine
from algo_trade.config import AppConfig, hash_config
from algo_trade.strategies import Strategy
from algo_trade.symbols import SymbolRegistry


@dataclass(frozen=True)
class WalkForwardSplit:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    locked_test: bool = True

    def to_record(self) -> dict[str, object]:
        return {
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "locked_test": self.locked_test,
        }


@dataclass(frozen=True)
class WalkForwardSummary:
    run_id: str
    run_dir: Path
    splits: list[dict[str, object]]
    rounds: list[dict[str, object]]
    aggregate: dict[str, object]

    def to_record(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "splits": self.splits,
            "rounds": self.rounds,
            "aggregate": self.aggregate,
        }


def build_walk_forward_splits(
    frame: pd.DataFrame,
    train_months: int = 12,
    validation_months: int = 3,
    test_months: int = 3,
    step_months: int = 3,
) -> list[WalkForwardSplit]:
    timestamps = pd.to_datetime(frame["timestamp"])
    start = timestamps.min().normalize()
    end = timestamps.max()
    splits: list[WalkForwardSplit] = []
    cursor = start
    while True:
        train_start = cursor
        validation_start = train_start + pd.DateOffset(months=train_months)
        test_start = validation_start + pd.DateOffset(months=validation_months)
        test_end = test_start + pd.DateOffset(months=test_months)
        if test_start > end or test_end > end + pd.Timedelta(days=1):
            break
        splits.append(
            WalkForwardSplit(
                train_start=train_start,
                train_end=validation_start - pd.Timedelta(nanoseconds=1),
                validation_start=validation_start,
                validation_end=test_start - pd.Timedelta(nanoseconds=1),
                test_start=test_start,
                test_end=test_end - pd.Timedelta(nanoseconds=1),
            )
        )
        cursor = cursor + pd.DateOffset(months=step_months)
    return splits


def run_walk_forward(
    config: AppConfig,
    registry: SymbolRegistry,
    frame: pd.DataFrame,
    symbol_name: str,
    strategy: Strategy,
) -> WalkForwardSummary:
    wf_config = config.raw.get("walk_forward", {})
    split_preset = str(wf_config.get("preset", "promotion_default"))
    splits = build_walk_forward_splits(
        frame,
        train_months=int(wf_config.get("train_months", 12)),
        validation_months=int(wf_config.get("validation_months", 3)),
        test_months=int(wf_config.get("test_months", 3)),
        step_months=int(wf_config.get("step_months", 3)),
    )
    run_id = f"wf-{uuid.uuid4().hex[:12]}"
    run_dir = config.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    rounds: list[dict[str, object]] = []
    for index, split in enumerate(splits, start=1):
        test_frame = frame[
            (pd.to_datetime(frame["timestamp"]) >= split.test_start)
            & (pd.to_datetime(frame["timestamp"]) <= split.test_end)
        ].copy()
        if test_frame.empty:
            continue
        result = BacktestEngine(_child_config(config, run_dir), registry, strategy, record_events=False).run(test_frame, symbol_name)
        rounds.append(
            {
                "round": index,
                "split": split.to_record(),
                "test_metrics": result.report.to_record(),
                "parameter_hash": config.config_hash,
            }
        )
    summary = WalkForwardSummary(
        run_id=run_id,
        run_dir=run_dir,
        splits=[split.to_record() for split in splits],
        rounds=rounds,
        aggregate=_aggregate(rounds, split_preset),
    )
    (run_dir / "walk_forward_summary.json").write_text(
        pd.Series(summary.to_record()).to_json(indent=2, default_handler=str),
        encoding="utf-8",
    )
    return summary


def _child_config(config: AppConfig, run_dir: Path) -> AppConfig:
    raw = deepcopy(config.raw)
    raw.setdefault("paths", {})["output_dir"] = str(run_dir)
    return AppConfig(raw=raw, path=config.path, config_hash=hash_config(raw))


def _aggregate(rounds: list[dict[str, object]], split_preset: str) -> dict[str, object]:
    returns = [float(round_data["test_metrics"]["total_return"]) for round_data in rounds]  # type: ignore[index]
    expectancies = [float(round_data["test_metrics"]["expectancy"]) for round_data in rounds]  # type: ignore[index]
    return {
        "split_preset": split_preset,
        "promotion_eligible": split_preset != "research_dev",
        "rounds": len(rounds),
        "positive_rounds": sum(1 for value in expectancies if value > 0),
        "average_total_return": float(sum(returns) / len(returns)) if returns else 0.0,
        "worst_total_return": float(min(returns)) if returns else 0.0,
        "worst_expectancy": float(min(expectancies)) if expectancies else 0.0,
        "parameter_drift": "stable",
    }

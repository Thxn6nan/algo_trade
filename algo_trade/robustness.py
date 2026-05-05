from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from algo_trade.types import Trade


@dataclass(frozen=True)
class RobustnessSummary:
    trade_dependency: dict[str, dict[str, float]]
    monte_carlo: dict[str, float]
    cost_stress: dict[str, dict[str, float]]
    parameter_sweeps: dict[str, dict[str, float]]

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def run_robustness_suite(
    trades: list[Trade],
    config: dict[str, Any] | None = None,
) -> RobustnessSummary:
    settings = {
        "remove_best_n": [1, 3],
        "double_worst_n": [1, 3],
        "monte_carlo_iterations": 100,
        "random_seed": 42,
        **(config or {}),
    }
    trade_dependency: dict[str, dict[str, float]] = {}
    for count in settings.get("remove_best_n", []):
        trade_dependency[f"remove_best_{count}"] = _remove_best(trades, int(count))
    for count in settings.get("double_worst_n", []):
        trade_dependency[f"double_worst_{count}"] = _double_worst(trades, int(count))

    return RobustnessSummary(
        trade_dependency=trade_dependency,
        monte_carlo=_monte_carlo(trades, int(settings["monte_carlo_iterations"]), int(settings["random_seed"])),
        cost_stress={},
        parameter_sweeps={},
    )


def _remove_best(trades: list[Trade], count: int) -> dict[str, float]:
    remaining = sorted(trades, key=lambda trade: trade.r_multiple, reverse=True)[count:]
    return _summary(remaining)


def _double_worst(trades: list[Trade], count: int) -> dict[str, float]:
    adjusted = [trade.net_pnl for trade in trades]
    worst_indexes = sorted(range(len(trades)), key=lambda index: trades[index].net_pnl)[:count]
    for index in worst_indexes:
        if adjusted[index] < 0:
            adjusted[index] *= 2
    return {
        "trades": float(len(adjusted)),
        "net_pnl": float(sum(adjusted)),
        "expectancy": float(sum(adjusted) / len(adjusted)) if adjusted else 0.0,
    }


def _summary(trades: list[Trade]) -> dict[str, float]:
    pnl = [trade.net_pnl for trade in trades]
    r_values = [trade.r_multiple for trade in trades]
    return {
        "trades": float(len(trades)),
        "net_pnl": float(sum(pnl)),
        "expectancy": float(sum(pnl) / len(pnl)) if pnl else 0.0,
        "average_r": float(sum(r_values) / len(r_values)) if r_values else 0.0,
    }


def _monte_carlo(trades: list[Trade], iterations: int, seed: int) -> dict[str, float]:
    if not trades or iterations <= 0:
        return {"iterations": float(max(iterations, 0)), "worst_shuffle_drawdown_r": 0.0}
    rng = random.Random(seed)
    r_values = [trade.r_multiple for trade in trades]
    worst_drawdown = 0.0
    for _ in range(iterations):
        sample = r_values.copy()
        rng.shuffle(sample)
        equity = 0.0
        peak = 0.0
        for value in sample:
            equity += value
            peak = max(peak, equity)
            worst_drawdown = min(worst_drawdown, equity - peak)
    return {"iterations": float(iterations), "worst_shuffle_drawdown_r": float(abs(worst_drawdown))}

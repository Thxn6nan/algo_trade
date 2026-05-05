from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pandas as pd

from algo_trade.config import AppConfig, hash_config
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
    parameter_sweeps: dict[str, dict[str, float]] | None = None,
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

    cost_stress: dict[str, dict[str, float]] = {}
    for mult in [1.5, 2.0, 3.0]:
        cost_stress[f"spread_x{mult}"] = _simulate_cost_increase(trades, spread_mult=mult)
    for comm in [2.0, 5.0, 10.0]:
        cost_stress[f"commission_{comm}"] = _simulate_cost_increase(trades, commission=comm)
    for slip in [1.5, 2.0, 3.0]:
        cost_stress[f"slippage_x{slip}"] = _simulate_cost_increase(trades, slippage_mult=slip)

    return RobustnessSummary(
        trade_dependency=trade_dependency,
        monte_carlo=_monte_carlo(trades, int(settings["monte_carlo_iterations"]), int(settings["random_seed"])),
        cost_stress=cost_stress,
        parameter_sweeps=parameter_sweeps or {},
    )


def run_parameter_sweeps(
    config: AppConfig,
    registry: Any,
    frame: pd.DataFrame,
    symbol_name: str,
    strategy: Any,
) -> dict[str, dict[str, float]]:
    sweep_config = config.raw.get("robustness", {}).get("parameter_sweeps")
    if sweep_config is None:
        sweep_config = {
            "filters.max_spread_percentile": [0.90, 0.95],
            "signal.min_rr": [1.25, 1.5, 1.75],
            "backtest.time_stop_bars": [12, 24, 36],
        }
    results: dict[str, dict[str, float]] = {}
    for dotted_path, values in sweep_config.items():
        for value in values:
            label = f"{dotted_path}={value}"
            sweep_raw = deepcopy(config.raw)
            _set_dotted(sweep_raw, str(dotted_path), value)
            sweep_config_obj = AppConfig(raw=sweep_raw, path=config.path, config_hash=hash_config(sweep_raw))
            from algo_trade.backtest import BacktestEngine
            from algo_trade.strategies import get_strategy

            try:
                sweep_strategy = get_strategy(strategy.name)
            except ValueError:
                sweep_strategy = deepcopy(strategy)
            result = BacktestEngine(
                sweep_config_obj,
                registry,
                sweep_strategy,
                record_events=False,
            ).run(frame.copy(), symbol_name)
            results[label] = {
                "trades": float(result.report.number_of_trades),
                "total_return": float(result.report.total_return),
                "profit_factor": float(result.report.profit_factor),
                "expectancy": float(result.report.expectancy),
                "max_drawdown": float(result.report.max_drawdown),
            }
    return results


def _set_dotted(raw: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    current = raw
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _simulate_cost_increase(trades: list[Trade], spread_mult: float = 1.0, commission: float = 0.0, slippage_mult: float = 1.0) -> dict[str, float]:
    adjusted = []
    for trade in trades:
        extra_spread = trade.spread_cost * (spread_mult - 1.0) if spread_mult > 1.0 else 0.0
        extra_slippage = trade.slippage * (slippage_mult - 1.0) if slippage_mult > 1.0 else 0.0
        extra_comm = (commission * trade.position_size) - trade.commission if commission > 0.0 else 0.0
        adjusted.append(trade.net_pnl - extra_spread - extra_slippage - extra_comm)
    return {
        "trades": float(len(adjusted)),
        "net_pnl": float(sum(adjusted)),
        "expectancy": float(sum(adjusted) / len(adjusted)) if adjusted else 0.0,
    }


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

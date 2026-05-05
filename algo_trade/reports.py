from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from algo_trade.types import Trade


@dataclass(frozen=True)
class PerformanceReport:
    total_return: float
    win_rate: float
    average_win: float
    average_loss: float
    profit_factor: float
    expectancy: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    average_r: float
    median_r: float
    number_of_trades: int
    cost_as_percent_gross_profit: float
    rejected_signals: dict[str, int]

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def build_performance_report(
    trades: list[Trade],
    equity_curve: pd.Series,
    rejected_reasons: list[str],
    initial_equity: float,
) -> PerformanceReport:
    pnl = np.array([trade.net_pnl for trade in trades], dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(abs(losses.sum())) if losses.size else 0.0
    returns = equity_curve.pct_change().dropna()
    downside = returns[returns < 0]
    running_peak = equity_curve.cummax()
    drawdown = (equity_curve - running_peak) / running_peak.replace(0, np.nan)
    costs = sum(trade.commission + trade.spread_cost + trade.slippage for trade in trades)
    rejected_summary: dict[str, int] = {}
    for reason in rejected_reasons:
        rejected_summary[reason] = rejected_summary.get(reason, 0) + 1
    return PerformanceReport(
        total_return=float((equity_curve.iloc[-1] - initial_equity) / initial_equity) if len(equity_curve) else 0.0,
        win_rate=float(len(wins) / len(pnl)) if len(pnl) else 0.0,
        average_win=float(wins.mean()) if wins.size else 0.0,
        average_loss=float(losses.mean()) if losses.size else 0.0,
        profit_factor=float(gross_profit / gross_loss) if gross_loss else (float("inf") if gross_profit else 0.0),
        expectancy=float(pnl.mean()) if len(pnl) else 0.0,
        sharpe_ratio=float((returns.mean() / returns.std()) * np.sqrt(252)) if len(returns) > 1 and returns.std() else 0.0,
        sortino_ratio=float((returns.mean() / downside.std()) * np.sqrt(252)) if len(downside) > 1 and downside.std() else 0.0,
        max_drawdown=float(abs(drawdown.min())) if len(drawdown) else 0.0,
        average_r=float(np.mean([trade.r_multiple for trade in trades])) if trades else 0.0,
        median_r=float(np.median([trade.r_multiple for trade in trades])) if trades else 0.0,
        number_of_trades=len(trades),
        cost_as_percent_gross_profit=float(costs / gross_profit) if gross_profit else 0.0,
        rejected_signals=rejected_summary,
    )


def compare_baselines(reports: dict[str, PerformanceReport]) -> dict[str, dict[str, object]]:
    return {name: report.to_record() for name, report in reports.items()}

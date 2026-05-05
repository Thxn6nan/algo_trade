from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from algo_trade.backtest import BacktestEngine, BacktestResult
from algo_trade.config import AppConfig, hash_config
from algo_trade.reports import PerformanceReport
from algo_trade.storage import RunRecorder
from algo_trade.strategies import Strategy, get_strategy
from algo_trade.symbols import SymbolRegistry


@dataclass(frozen=True)
class EdgeEvidence:
    verdict: str
    checks: dict[str, bool]
    reasons: list[str]
    primary_metrics: dict[str, object]
    baseline_metrics: dict[str, dict[str, object]]
    stress_metrics: dict[str, dict[str, object]]

    def to_record(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "checks": self.checks,
            "reasons": self.reasons,
            "primary_metrics": self.primary_metrics,
            "baseline_metrics": self.baseline_metrics,
            "stress_metrics": self.stress_metrics,
        }


def build_edge_evidence(
    config: AppConfig,
    registry: SymbolRegistry,
    frame: pd.DataFrame,
    symbol_name: str,
    strategy: Strategy,
    primary_result: BacktestResult,
) -> EdgeEvidence:
    edge_config = config.raw.get("edge", {})
    if edge_config.get("enabled", True) is False:
        evidence = _assess(config, frame, primary_result.report, {}, {})
        _record_edge(config, primary_result.run_id, primary_result.run_dir, evidence)
        return evidence

    baseline_reports: dict[str, PerformanceReport] = {}
    for baseline_name in edge_config.get("baselines", []):
        if baseline_name == strategy.name:
            continue
        baseline_result = BacktestEngine(config, registry, get_strategy(baseline_name), record_events=False).run(frame.copy(), symbol_name)
        baseline_reports[baseline_name] = baseline_result.report

    stress_reports: dict[str, PerformanceReport] = {}
    for slippage_model in edge_config.get("stress_slippage_models", []):
        stress_config = _with_backtest_override(config, {"slippage_model": slippage_model})
        stress_strategy = get_strategy(strategy.name)
        stress_result = BacktestEngine(stress_config, registry, stress_strategy, record_events=False).run(frame.copy(), symbol_name)
        stress_reports[str(slippage_model)] = stress_result.report

    evidence = _assess(config, frame, primary_result.report, baseline_reports, stress_reports)
    _record_edge(config, primary_result.run_id, primary_result.run_dir, evidence)
    return evidence


def _assess(
    config: AppConfig,
    frame: pd.DataFrame,
    primary_report: PerformanceReport,
    baseline_reports: dict[str, PerformanceReport],
    stress_reports: dict[str, PerformanceReport],
) -> EdgeEvidence:
    edge_config = config.raw.get("edge", {})
    min_bars = int(edge_config.get("min_bars", config.raw.get("data", {}).get("min_bars", 0)))
    min_trades = int(edge_config.get("min_trades", 0))
    min_profit_factor = float(edge_config.get("min_profit_factor", 1.0))
    min_expectancy = float(edge_config.get("min_expectancy", 0.0))
    max_drawdown = float(edge_config.get("max_drawdown", 1.0))
    require_real_data = bool(edge_config.get("require_real_data", True))
    require_beats_baselines = bool(edge_config.get("require_beats_baselines", True))
    require_stress_expectancy_positive = bool(edge_config.get("require_stress_expectancy_positive", True))

    checks: dict[str, bool] = {
        "real_data": (not require_real_data) or (not bool(frame.attrs.get("is_sample_data", False))),
        "minimum_bars": len(frame) >= min_bars,
        "minimum_trades": primary_report.number_of_trades >= min_trades,
        "profit_factor": primary_report.profit_factor >= min_profit_factor,
        "positive_expectancy": primary_report.expectancy > min_expectancy,
        "drawdown_controlled": primary_report.max_drawdown <= max_drawdown,
    }

    if require_beats_baselines:
        checks["baselines_present"] = bool(baseline_reports)
        checks["beats_baselines"] = bool(baseline_reports) and all(
            primary_report.total_return > baseline.total_return for baseline in baseline_reports.values()
        )

    if require_stress_expectancy_positive:
        checks["stress_present"] = bool(stress_reports)
        checks["stress_expectancy_positive"] = bool(stress_reports) and all(
            report.expectancy > min_expectancy for report in stress_reports.values()
        )

    reasons = [name for name, passed in checks.items() if not passed]
    verdict = "PASS" if not reasons else "FAIL"
    return EdgeEvidence(
        verdict=verdict,
        checks=checks,
        reasons=reasons,
        primary_metrics=primary_report.to_record(),
        baseline_metrics={name: report.to_record() for name, report in baseline_reports.items()},
        stress_metrics={name: report.to_record() for name, report in stress_reports.items()},
    )


def _with_backtest_override(config: AppConfig, backtest_overrides: dict[str, Any]) -> AppConfig:
    raw = deepcopy(config.raw)
    raw.setdefault("backtest", {}).update(backtest_overrides)
    return AppConfig(raw=raw, path=config.path, config_hash=hash_config(raw))


def _record_edge(config: AppConfig, run_id: str, run_dir: Path, evidence: EdgeEvidence) -> None:
    recorder = RunRecorder(run_id, run_dir, mode=config.mode, config_hash=config.config_hash)
    try:
        recorder.record("edge_evidence", "system_events", {"event": "edge_evidence", **evidence.to_record()})
    finally:
        recorder.close()

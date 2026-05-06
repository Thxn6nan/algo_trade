from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from algo_trade.backtest import BacktestEngine, BacktestResult
from algo_trade.config import AppConfig, hash_config
from algo_trade.edge_report import write_edge_report
from algo_trade.reports import PerformanceReport
from algo_trade.robustness import run_parameter_sweeps, run_robustness_suite
from algo_trade.storage import RunRecorder
from algo_trade.strategies import Strategy, get_strategy
from algo_trade.symbols import SymbolRegistry


@dataclass(frozen=True)
class EdgeEvidence:
    verdict: str
    failure_class: str
    checks: dict[str, bool]
    reasons: list[str]
    primary_metrics: dict[str, object]
    baseline_metrics: dict[str, dict[str, object]]
    stress_metrics: dict[str, dict[str, object]]
    strategy_viability: dict[str, object]
    symbol_audit: dict[str, object]
    walk_forward: dict[str, object] | None = None
    robustness: dict[str, object] | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "failure_class": self.failure_class,
            "checks": self.checks,
            "reasons": self.reasons,
            "primary_metrics": self.primary_metrics,
            "baseline_metrics": self.baseline_metrics,
            "stress_metrics": self.stress_metrics,
            "strategy_viability": self.strategy_viability,
            "symbol_audit": self.symbol_audit,
            "walk_forward": self.walk_forward,
            "robustness": self.robustness,
        }


def build_edge_evidence(
    config: AppConfig,
    registry: SymbolRegistry,
    frame: pd.DataFrame,
    symbol_name: str,
    strategy: Strategy,
    primary_result: BacktestResult,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    progress_step_percent: int = 5,
) -> EdgeEvidence:
    edge_config = config.raw.get("edge", {})
    if edge_config.get("enabled", True) is False:
        evidence = _assess(config, frame, primary_result, {}, {}, None, None)
        _record_edge(config, primary_result.run_id, primary_result.run_dir, evidence)
        return evidence

    baseline_reports: dict[str, PerformanceReport] = {}
    for baseline_name in edge_config.get("baselines", []):
        if baseline_name == strategy.name:
            continue
        baseline_result = BacktestEngine(
            config,
            registry,
            get_strategy(baseline_name),
            record_events=False,
            progress_callback=progress_callback,
            progress_step_percent=progress_step_percent,
            progress_label=f"baseline {baseline_name}",
        ).run(frame.copy(), symbol_name)
        baseline_reports[baseline_name] = baseline_result.report

    stress_reports: dict[str, PerformanceReport] = {}
    for slippage_model in edge_config.get("stress_slippage_models", []):
        stress_config = _with_backtest_override(config, {"slippage_model": slippage_model})
        stress_strategy = get_strategy(strategy.name)
        stress_result = BacktestEngine(
            stress_config,
            registry,
            stress_strategy,
            record_events=False,
            progress_callback=progress_callback,
            progress_step_percent=progress_step_percent,
            progress_label=f"stress {slippage_model}",
        ).run(frame.copy(), symbol_name)
        stress_reports[str(slippage_model)] = stress_result.report

    wf_summary = None
    if edge_config.get("require_walk_forward_positive", True):
        from algo_trade.walk_forward import run_walk_forward
        wf_summary = run_walk_forward(config, registry, frame, symbol_name, strategy)

    parameter_sweeps = run_parameter_sweeps(config, registry, frame, symbol_name, strategy)
    robustness = run_robustness_suite(primary_result.trades, config.raw.get("robustness", {}), parameter_sweeps)

    evidence = _assess(config, frame, primary_result, baseline_reports, stress_reports, wf_summary, robustness)
    _record_edge(config, primary_result.run_id, primary_result.run_dir, evidence)
    _record_report(config, frame, primary_result, evidence, robustness)
    return evidence


def _assess(
    config: AppConfig,
    frame: pd.DataFrame,
    primary_result: BacktestResult,
    baseline_reports: dict[str, PerformanceReport],
    stress_reports: dict[str, PerformanceReport],
    wf_summary: Any | None,
    robustness: Any | None,
) -> EdgeEvidence:
    edge_config = config.raw.get("edge", {})
    primary_report = primary_result.report
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
    symbol_audit_record = primary_result.symbol_audit.to_record() if primary_result.symbol_audit else {}
    viability_record = primary_result.strategy_viability.to_record() if primary_result.strategy_viability else {}
    checks["symbol_audit"] = not bool(symbol_audit_record.get("promotion_blockers"))
    checks["strategy_viability"] = bool(viability_record.get("passed", True))

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

    require_walk_forward_positive = bool(edge_config.get("require_walk_forward_positive", True))
    if require_walk_forward_positive:
        checks["walk_forward_present"] = bool(wf_summary and wf_summary.rounds)
        checks["walk_forward_promotion_eligible"] = bool(
            wf_summary and wf_summary.aggregate.get("promotion_eligible", True)
        )
        checks["walk_forward_positive"] = bool(
            wf_summary
            and wf_summary.aggregate.get("promotion_eligible", True)
            and wf_summary.aggregate.get("positive_rounds", 0) > 0
        )

    require_robustness_positive = bool(edge_config.get("require_robustness_positive", True))
    if require_robustness_positive:
        checks["robustness_present"] = bool(robustness)
        if robustness:
            dependency_passed = all(
                result.get("expectancy", 0.0) > min_expectancy
                for result in robustness.trade_dependency.values()
            )
            cost_passed = all(
                result.get("expectancy", 0.0) > min_expectancy
                for result in robustness.cost_stress.values()
            )
            parameter_passed = bool(robustness.parameter_sweeps) and all(
                result.get("expectancy", 0.0) > min_expectancy
                for result in robustness.parameter_sweeps.values()
            )
            checks["robustness_positive"] = dependency_passed and cost_passed and parameter_passed
        else:
            checks["robustness_positive"] = False

    reasons = [name for name, passed in checks.items() if not passed]
    verdict = "PASS" if not reasons else "FAIL"
    failure_class = _failure_class(checks, primary_report, viability_record, symbol_audit_record)
    return EdgeEvidence(
        verdict=verdict,
        failure_class=failure_class,
        checks=checks,
        reasons=reasons,
        primary_metrics=primary_report.to_record(),
        baseline_metrics={name: report.to_record() for name, report in baseline_reports.items()},
        stress_metrics={name: report.to_record() for name, report in stress_reports.items()},
        strategy_viability=viability_record,
        symbol_audit=symbol_audit_record,
        walk_forward=wf_summary.to_record() if wf_summary else None,
        robustness=robustness.to_record() if robustness else None,
    )


def _failure_class(
    checks: dict[str, bool],
    primary_report: PerformanceReport,
    viability_record: dict[str, object],
    symbol_audit_record: dict[str, object],
) -> str:
    if all(checks.values()):
        return "passed"
    if not checks.get("real_data", True) or not checks.get("minimum_bars", True) or symbol_audit_record.get("promotion_blockers"):
        return "data_quality_failure"
    viability_failure = viability_record.get("failure_class")
    if viability_failure:
        return str(viability_failure)
    if primary_report.number_of_trades == 0 or not checks.get("minimum_trades", True):
        return "insufficient_evidence"
    return "no_edge"


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


def _record_report(config: AppConfig, frame: pd.DataFrame, result: BacktestResult, evidence: EdgeEvidence, robustness_summary: Any) -> None:
    if config.raw.get("reports", {}).get("edge_report", True) is False:
        return
    data_quality = result.data_quality.to_record() if result.data_quality and hasattr(result.data_quality, "to_record") else {}
    robustness = robustness_summary.to_record() if robustness_summary else {}
    promotion_gate = _research_candidate_gate(config, result, evidence)
    write_edge_report(
        result.run_dir,
        {
            "run_id": result.run_id,
            "data_quality": data_quality,
            "symbol_audit": evidence.symbol_audit,
            "strategy_configuration": config.raw.get("signal", {}),
            "strategy_viability": evidence.strategy_viability,
            "edge_evidence": evidence.to_record(),
            "execution_diagnostics": build_execution_diagnostics(
                frame,
                result.trades,
                result.report.to_record(),
                config.raw.get("risk", {}),
            ),
            "baseline_comparison": evidence.baseline_metrics,
            "performance": result.report.to_record(),
            "trades": [trade.to_record() for trade in result.trades],
            "trade_distribution": _trade_distribution(result.trades),
            "r_multiple_distribution": _r_distribution(result.trades),
            "drawdown_curve": _drawdown_curve(result.equity_curve),
            "walk_forward_summary": evidence.walk_forward or {},
            "robustness_summary": robustness,
            "promotion_gate": promotion_gate,
        },
    )


def _research_candidate_gate(config: AppConfig, result: BacktestResult, evidence: EdgeEvidence) -> dict[str, object]:
    min_trades = int(config.raw.get("promotion_gates", {}).get("research_candidate", {}).get("min_trades", 30))
    checks = {
        "real_data": evidence.checks.get("real_data", False),
        "data_quality": evidence.checks.get("symbol_audit", False),
        "strategy_viability": evidence.checks.get("strategy_viability", False),
        "minimum_trades": result.report.number_of_trades >= min_trades,
    }
    return {"gate": "research_candidate", "passed": all(checks.values()), "checks": checks}


def build_execution_diagnostics(
    frame: pd.DataFrame,
    trades: list[object],
    primary_metrics: dict[str, object],
    risk_config: dict[str, object],
) -> dict[str, object]:
    timestamps = pd.to_datetime(frame["timestamp"]) if "timestamp" in frame and len(frame) else pd.Series(dtype="datetime64[ns]")
    data_start = timestamps.min() if len(timestamps) else pd.NaT
    data_end = timestamps.max() if len(timestamps) else pd.NaT
    data_seconds = float((data_end - data_start).total_seconds()) if pd.notna(data_start) and pd.notna(data_end) else 0.0

    first_entry = min((pd.Timestamp(getattr(trade, "entry_time")) for trade in trades), default=pd.NaT)
    last_exit = max((pd.Timestamp(getattr(trade, "exit_time")) for trade in trades), default=pd.NaT)
    trade_seconds = float((last_exit - first_entry).total_seconds()) if pd.notna(first_entry) and pd.notna(last_exit) else 0.0
    remaining_seconds = float((data_end - last_exit).total_seconds()) if pd.notna(data_end) and pd.notna(last_exit) else 0.0

    max_drawdown = float(primary_metrics.get("max_drawdown", 0.0) or 0.0)
    drawdown_cap = float(risk_config.get("max_drawdown", 1.0) or 1.0)
    risk_cap_reached = drawdown_cap < 1.0 and max_drawdown >= drawdown_cap * 0.99
    data_remaining_after_last_trade_ratio = remaining_seconds / data_seconds if data_seconds > 0 else 0.0
    trade_period_coverage_ratio = trade_seconds / data_seconds if data_seconds > 0 else 0.0

    flags = []
    if not trades:
        flags.append("no_trades")
    if trades and risk_cap_reached and data_remaining_after_last_trade_ratio > 0.5:
        flags.append("trade_activity_truncated")

    return {
        "data_start": data_start.isoformat() if pd.notna(data_start) else None,
        "data_end": data_end.isoformat() if pd.notna(data_end) else None,
        "first_trade_entry": first_entry.isoformat() if pd.notna(first_entry) else None,
        "last_trade_exit": last_exit.isoformat() if pd.notna(last_exit) else None,
        "trade_period_coverage_ratio": trade_period_coverage_ratio,
        "data_remaining_after_last_trade_ratio": data_remaining_after_last_trade_ratio,
        "max_drawdown": max_drawdown,
        "risk_max_drawdown": drawdown_cap,
        "risk_cap_reached": risk_cap_reached,
        "flags": flags,
    }


def _trade_distribution(trades: list[object]) -> dict[str, object]:
    return {"trades": len(trades)}


def _r_distribution(trades: list[object]) -> dict[str, object]:
    values = [float(getattr(trade, "r_multiple", 0.0)) for trade in trades]
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(values),
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
    }


def _drawdown_curve(equity_curve: pd.Series) -> dict[str, object]:
    if equity_curve.empty:
        return {"points": []}
    running_peak = equity_curve.cummax()
    drawdown = (equity_curve - running_peak) / running_peak.replace(0, pd.NA)
    return {"points": [{"timestamp": index.isoformat(), "drawdown": float(value)} for index, value in drawdown.dropna().items()]}

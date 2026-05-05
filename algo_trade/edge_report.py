from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_edge_report(run_dir: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    report = dict(payload)
    trades = list(report.get("trades", []))
    report.setdefault("session_regime_breakdown", build_session_regime_breakdown(trades))

    (path / "edge_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (path / "edge_report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def build_session_regime_breakdown(trades: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "by_session": _group(trades, "entry_session"),
        "by_trend_regime": _group(trades, "entry_trend_regime"),
        "by_range_regime": _group(trades, "entry_range_regime"),
    }


def _group(trades: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        value = str(trade.get(key) or "unknown")
        grouped.setdefault(value, []).append(trade)
    return {name: _trade_summary(items) for name, items in grouped.items()}


def _trade_summary(trades: list[dict[str, Any]]) -> dict[str, float]:
    pnl = [float(trade.get("net_pnl", 0.0)) for trade in trades]
    r_values = [float(trade.get("R_multiple", trade.get("r_multiple", 0.0))) for trade in trades]
    return {
        "trades": len(trades),
        "net_pnl": float(sum(pnl)),
        "average_r": float(sum(r_values) / len(r_values)) if r_values else 0.0,
    }


def _markdown(report: dict[str, Any]) -> str:
    evidence = report.get("edge_evidence", {})
    viability = report.get("strategy_viability", {})
    promotion = report.get("promotion_gate", {})
    lines = [
        f"# Edge Report {report.get('run_id', '')}".strip(),
        "",
        "## Data Source And Quality",
        _json_block(report.get("data_quality", {})),
        "",
        "## Symbol Audit",
        _json_block(report.get("symbol_audit", {})),
        "",
        "## Strategy Configuration",
        _json_block(report.get("strategy_configuration", {})),
        "",
        "## Edge Verdict",
        f"- Verdict: {evidence.get('verdict', 'unknown')}",
        f"- Failure class: {evidence.get('failure_class', 'unknown')}",
        "",
        "## Strategy Viability",
        f"- Passed: {viability.get('passed', False)}",
        f"- Raw signals: {viability.get('raw_signals', 0)}",
        f"- Approved trades: {viability.get('approved_trades', 0)}",
        "",
        "## Baseline Comparison",
        _json_block(report.get("baseline_comparison", {})),
        "",
        "## Cost Analysis",
        _json_block(report.get("performance", {})),
        "",
        "## Session And Regime Breakdown",
        _json_block(report.get("session_regime_breakdown", {})),
        "",
        "## Trade Distribution",
        _json_block(report.get("trade_distribution", {})),
        "",
        "## R-Multiple Distribution",
        _json_block(report.get("r_multiple_distribution", {})),
        "",
        "## Drawdown Curve",
        _json_block(report.get("drawdown_curve", {})),
        "",
        "## Rejection Reason Summary",
        _json_block(viability.get("rejection_reasons", {})),
        "",
        "## Walk-Forward Summary",
        _json_block(report.get("walk_forward_summary", {})),
        "",
        "## Robustness Summary",
        _json_block(report.get("robustness_summary", {})),
        "",
        "## Promotion Gate",
        f"- Gate: {promotion.get('gate', 'research_candidate')}",
        f"- Passed: {promotion.get('passed', False)}",
    ]
    return "\n".join(lines) + "\n"


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True, default=str) + "\n```"

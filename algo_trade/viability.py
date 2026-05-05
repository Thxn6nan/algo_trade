from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from algo_trade.types import DecisionStatus, Signal, SignalSide, TradeDecision


@dataclass(frozen=True)
class StrategyViabilityReport:
    passed: bool
    raw_signals: int
    approved_trades: int
    rejected_signals: int
    rejection_rate: float
    side_counts: dict[str, int]
    rejection_reasons: dict[str, int]
    thresholds: dict[str, object]
    reasons: list[str]
    failure_class: str | None

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def build_strategy_viability(
    signals: list[Signal],
    decisions: list[TradeDecision | dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> StrategyViabilityReport:
    thresholds = {
        "min_raw_signals": 100,
        "min_approved_trades": 30,
        "max_rejection_rate": 0.95,
        "require_both_sides": False,
        **(config or {}),
    }
    raw = [signal for signal in signals if signal.side != SignalSide.HOLD]
    side_counts = {
        SignalSide.BUY.value: sum(1 for signal in raw if signal.side == SignalSide.BUY),
        SignalSide.SELL.value: sum(1 for signal in raw if signal.side == SignalSide.SELL),
    }

    approved = 0
    rejected = 0
    rejection_reasons: dict[str, int] = {}
    for decision in decisions:
        record = _decision_record(decision)
        status = record.get("status")
        if status == DecisionStatus.APPROVED.value:
            approved += 1
        elif status == DecisionStatus.REJECTED.value:
            rejected += 1
            for reason in record.get("reasons", []) or []:
                rejection_reasons[str(reason)] = rejection_reasons.get(str(reason), 0) + 1

    denominator = approved + rejected
    rejection_rate = float(rejected / denominator) if denominator else 0.0
    reasons: list[str] = []
    if len(raw) < int(thresholds["min_raw_signals"]):
        reasons.append("minimum_raw_signals")
    if approved < int(thresholds["min_approved_trades"]):
        reasons.append("minimum_approved_trades")
    if rejection_rate > float(thresholds["max_rejection_rate"]):
        reasons.append("rejection_rate_too_high")
    if bool(thresholds["require_both_sides"]) and (side_counts[SignalSide.BUY.value] == 0 or side_counts[SignalSide.SELL.value] == 0):
        reasons.append("both_sides_required")

    failure_class = None
    if reasons:
        failure_class = "invalid_configuration" if "rejection_rate_too_high" in reasons else "insufficient_evidence"

    return StrategyViabilityReport(
        passed=not reasons,
        raw_signals=len(raw),
        approved_trades=approved,
        rejected_signals=rejected,
        rejection_rate=rejection_rate,
        side_counts=side_counts,
        rejection_reasons=rejection_reasons,
        thresholds=thresholds,
        reasons=reasons,
        failure_class=failure_class,
    )


def _decision_record(decision: TradeDecision | dict[str, Any]) -> dict[str, Any]:
    if isinstance(decision, TradeDecision):
        record = decision.to_record()
        record["reasons"] = decision.reasons
        return record
    return decision

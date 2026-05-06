from __future__ import annotations

from algo_trade.filters import SignalFilter
from algo_trade.risk import RiskEngine
from algo_trade.symbols import SymbolSpec
from algo_trade.types import DecisionStatus, DecisionType, Signal, SignalSide, TradeDecision


class DecisionEngine:
    def __init__(self, filters: SignalFilter, risk: RiskEngine, backtest_config: dict):
        self.filters = filters
        self.risk = risk
        self.backtest_config = backtest_config

    def decide(
        self,
        signal: Signal,
        symbol: SymbolSpec,
        equity: float,
        entry_price: float,
        open_positions: int,
    ) -> TradeDecision:
        snapshot = self.risk.snapshot(equity, timestamp=signal.timestamp)
        if snapshot.kill_switch_active:
            return _decision(signal, DecisionType.HALT, DecisionStatus.HALTED, None, None, None, 0.0, 0.0, ["kill_switch_active", snapshot.kill_switch_reason or "unknown"])

        if signal.side == SignalSide.HOLD:
            return _decision(signal, DecisionType.HOLD, DecisionStatus.HELD, None, None, None, 0.0, 0.0, ["hold_signal"])

        if open_positions >= int(self.risk.config.get("max_open_positions", 1)):
            return _decision(signal, DecisionType.REJECT, DecisionStatus.REJECTED, None, None, None, 0.0, 0.0, ["max_open_positions"])

        atr = signal.metadata.get("atr")
        if atr is None or atr <= 0:
            return _decision(signal, DecisionType.REJECT, DecisionStatus.REJECTED, None, None, None, 0.0, 0.0, ["atr_unavailable"])

        stop_loss, take_profit = _stops(signal.side, entry_price, atr)
        rr = abs(take_profit - entry_price) / abs(entry_price - stop_loss)
        filter_result = self.filters.evaluate(signal, symbol, rr)
        if not filter_result.passed:
            return _decision(
                signal,
                DecisionType.REJECT,
                DecisionStatus.REJECTED,
                entry_price,
                stop_loss,
                take_profit,
                0.0,
                rr,
                filter_result.failed_reasons,
                filters_passed=filter_result.passed_reasons,
                filters_failed=filter_result.failed_reasons,
            )

        size = self.risk.size_position(equity, symbol, entry_price, stop_loss)
        if size.lots <= 0:
            return _decision(
                signal,
                DecisionType.REJECT,
                DecisionStatus.REJECTED,
                entry_price,
                stop_loss,
                take_profit,
                0.0,
                rr,
                [size.reason],
                filters_passed=filter_result.passed_reasons,
                filters_failed=filter_result.failed_reasons,
                risk_amount=size.risk_amount,
            )

        decision_type = DecisionType.ENTER_LONG if signal.side == SignalSide.BUY else DecisionType.ENTER_SHORT
        reasons = filter_result.passed_reasons + [size.reason, "stop_loss_required"]
        return _decision(
            signal,
            decision_type,
            DecisionStatus.APPROVED,
            entry_price,
            stop_loss,
            take_profit,
            size.risk_pct,
            rr,
            reasons,
            size.lots,
            filters_passed=filter_result.passed_reasons,
            filters_failed=filter_result.failed_reasons,
            risk_amount=size.risk_amount,
        )


def _stops(side: SignalSide, entry_price: float, atr: float) -> tuple[float, float]:
    stop_distance = 2.0 * atr
    reward_distance = 4.0 * atr
    if side == SignalSide.BUY:
        return entry_price - stop_distance, entry_price + reward_distance
    return entry_price + stop_distance, entry_price - reward_distance


def _decision(
    signal: Signal,
    decision: DecisionType,
    status: DecisionStatus,
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    risk_pct: float,
    rr: float,
    reasons: list[str],
    position_size: float = 0.0,
    filters_passed: list[str] | None = None,
    filters_failed: list[str] | None = None,
    risk_amount: float = 0.0,
) -> TradeDecision:
    return TradeDecision(
        timestamp=signal.timestamp,
        symbol=signal.symbol,
        decision=decision,
        side=signal.side,
        entry_type="MARKET" if entry_price is not None else None,
        entry_price_estimate=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_pct=risk_pct,
        position_size=position_size,
        rr=rr,
        status=status,
        reasons=reasons,
        signal_id=signal.signal_id,
        metadata={
            "source": signal.source,
            "confidence": signal.confidence,
            "expected_return": signal.expected_return,
            "filters_passed": filters_passed or [],
            "filters_failed": filters_failed or [],
            "risk_amount": risk_amount,
            **signal.metadata,
        },
    )

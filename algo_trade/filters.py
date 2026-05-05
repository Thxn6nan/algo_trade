from __future__ import annotations

from dataclasses import dataclass

from algo_trade.symbols import SymbolSpec
from algo_trade.types import Signal, SignalSide


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    passed_reasons: list[str]
    failed_reasons: list[str]


class SignalFilter:
    def __init__(
        self,
        signal_config: dict,
        filter_config: dict,
        session_config: dict | None = None,
        regime_config: dict | None = None,
    ):
        self.signal_config = signal_config
        self.filter_config = filter_config
        self.session_config = session_config or {}
        self.regime_config = regime_config or {}

    def evaluate(self, signal: Signal, symbol: SymbolSpec, rr: float) -> FilterResult:
        passed: list[str] = []
        failed: list[str] = []
        if signal.side == SignalSide.HOLD:
            return FilterResult(False, [], ["hold_signal"])

        threshold_key = "buy_threshold" if signal.side == SignalSide.BUY else "sell_threshold"
        threshold = float(self.signal_config.get(threshold_key, 0.0))
        if signal.confidence >= threshold:
            passed.append("confidence_ok")
        else:
            failed.append("confidence_below_threshold")

        current_spread = signal.metadata.get("spread")
        max_spread = symbol.average_spread * float(self.filter_config.get("max_spread_multiplier", 2.5))
        if symbol.max_spread_points is not None:
            max_spread = min(max_spread, symbol.max_spread_points)
        if current_spread is not None and current_spread <= max_spread:
            passed.append("spread_ok")
        else:
            failed.append("spread_too_high")

        spread_percentile = signal.metadata.get("spread_percentile_session")
        max_spread_percentile = self.filter_config.get("max_spread_percentile")
        if max_spread_percentile is not None and spread_percentile is not None:
            if float(spread_percentile) <= float(max_spread_percentile):
                passed.append("spread_percentile_ok")
            else:
                failed.append("spread_percentile_too_high")

        session = signal.metadata.get("session_label")
        allowed_sessions = self.session_config.get("allowed_sessions") or []
        if session is not None:
            if bool(self.session_config.get("exclude_rollover", False)) and session == "rollover":
                failed.append("rollover_excluded")
            if allowed_sessions and session not in allowed_sessions:
                failed.append("session_not_allowed")

        trend_regime = signal.metadata.get("trend_regime")
        allowed_trend_regimes = self.regime_config.get("allowed_trend_regimes") or []
        if trend_regime is not None and allowed_trend_regimes and trend_regime not in allowed_trend_regimes:
            failed.append("trend_regime_not_allowed")

        range_regime = signal.metadata.get("range_regime")
        allowed_range_regimes = self.regime_config.get("allowed_range_regimes") or []
        if range_regime is not None and allowed_range_regimes and range_regime not in allowed_range_regimes:
            failed.append("range_regime_not_allowed")

        min_rr = float(self.signal_config.get("min_rr", 1.5))
        if rr >= min_rr:
            passed.append("rr_ok")
        else:
            failed.append("rr_below_minimum")

        atr = signal.metadata.get("atr")
        min_atr = float(self.filter_config.get("min_atr", 0.0))
        if atr is not None and atr > min_atr:
            passed.append("volatility_ok")
        else:
            failed.append("volatility_unavailable")

        return FilterResult(not failed, passed, failed)

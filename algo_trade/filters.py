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
    def __init__(self, signal_config: dict, filter_config: dict):
        self.signal_config = signal_config
        self.filter_config = filter_config

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
        if current_spread is not None and current_spread <= max_spread:
            passed.append("spread_ok")
        else:
            failed.append("spread_too_high")

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

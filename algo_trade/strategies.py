from __future__ import annotations

import random
from abc import ABC, abstractmethod

import pandas as pd

from algo_trade.types import Signal, SignalSide


class Strategy(ABC):
    name: str

    @abstractmethod
    def generate(self, row: pd.Series) -> Signal:
        raise NotImplementedError


class HoldStrategy(Strategy):
    name = "buy_and_hold"

    def generate(self, row: pd.Series) -> Signal:
        return _signal(row, SignalSide.BUY, self.name, confidence=1.0)


class RandomEntryStrategy(Strategy):
    name = "random_entry"

    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)

    def generate(self, row: pd.Series) -> Signal:
        side = self.random.choice([SignalSide.BUY, SignalSide.SELL, SignalSide.HOLD])
        return _signal(row, side, self.name, confidence=0.5)


class MovingAverageCrossoverStrategy(Strategy):
    name = "ma_crossover"

    def generate(self, row: pd.Series) -> Signal:
        if pd.isna(row.get("ema_fast")) or pd.isna(row.get("ema_slow")):
            return _signal(row, SignalSide.HOLD, self.name, confidence=0.0)
        if row["ema_fast"] > row["ema_slow"]:
            return _signal(row, SignalSide.BUY, self.name, confidence=0.7)
        if row["ema_fast"] < row["ema_slow"]:
            return _signal(row, SignalSide.SELL, self.name, confidence=0.7)
        return _signal(row, SignalSide.HOLD, self.name, confidence=0.0)


class RSIMeanReversionStrategy(Strategy):
    name = "rsi_mean_reversion"

    def generate(self, row: pd.Series) -> Signal:
        if pd.isna(row.get("rsi")):
            return _signal(row, SignalSide.HOLD, self.name, confidence=0.0)
        if row["rsi"] < 30:
            return _signal(row, SignalSide.BUY, self.name, confidence=0.65)
        if row["rsi"] > 70:
            return _signal(row, SignalSide.SELL, self.name, confidence=0.65)
        return _signal(row, SignalSide.HOLD, self.name, confidence=0.0)


class ATRBreakoutStrategy(Strategy):
    name = "atr_breakout"

    def generate(self, row: pd.Series) -> Signal:
        rolling_high = row.get("rolling_high")
        rolling_low = row.get("rolling_low")
        if pd.isna(rolling_high) or pd.isna(rolling_low):
            return _signal(row, SignalSide.HOLD, self.name, confidence=0.0)
        if row["close"] > rolling_high:
            return _signal(row, SignalSide.BUY, self.name, confidence=0.72)
        if row["close"] < rolling_low:
            return _signal(row, SignalSide.SELL, self.name, confidence=0.72)
        return _signal(row, SignalSide.HOLD, self.name, confidence=0.0)


def get_strategy(name: str) -> Strategy:
    strategies: dict[str, Strategy] = {
        "buy_and_hold": HoldStrategy(),
        "random_entry": RandomEntryStrategy(),
        "ma_crossover": MovingAverageCrossoverStrategy(),
        "rsi_mean_reversion": RSIMeanReversionStrategy(),
        "atr_breakout": ATRBreakoutStrategy(),
    }
    try:
        return strategies[name]
    except KeyError as exc:
        raise ValueError(f"Unknown strategy {name!r}") from exc


def _signal(row: pd.Series, side: SignalSide, source: str, confidence: float) -> Signal:
    expected_return = float(row.get("return") or 0.0)
    metadata = {
        "close": float(row["close"]),
        "atr": _safe_float(row.get("atr")),
        "spread": _safe_float(row.get("spread")),
        "rolling_high": _safe_float(row.get("rolling_high")),
        "rolling_low": _safe_float(row.get("rolling_low")),
    }
    return Signal(
        timestamp=row["timestamp"].to_pydatetime() if hasattr(row["timestamp"], "to_pydatetime") else row["timestamp"],
        symbol=str(row["symbol"]),
        side=side,
        confidence=confidence,
        expected_return=expected_return,
        source=source,
        timeframe=str(row["timeframe"]),
        metadata=metadata,
    )


def _safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)

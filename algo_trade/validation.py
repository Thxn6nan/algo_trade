from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from algo_trade.data import REQUIRED_COLUMNS


@dataclass(frozen=True)
class DataQualityReport:
    symbol: str
    timeframe: str
    rows: int
    start: str
    end: str
    duplicate_timestamps: int
    missing_bars: int
    invalid_candles: int
    nan_count: int
    infinite_count: int
    median_spread: float
    p95_spread: float
    timezone: str
    source: str = "unknown"
    source_path: str | None = None
    timestamp_semantics: str = "candle_open_time"
    validation_status: str = "passed"

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def validate_ohlcv(
    frame: pd.DataFrame,
    missing_threshold: int = 0,
    allow_session_gaps: bool = False,
    max_session_gap_minutes: int = 180,
    source: str = "unknown",
    source_path: str | None = None,
    timestamp_semantics: str = "candle_open_time",
) -> DataQualityReport:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing OHLCV columns: {missing_columns}")
    if frame.empty:
        raise ValueError("OHLCV data is empty")

    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("Timestamps must be parseable")
    duplicate_count = int(frame.assign(timestamp=timestamps).duplicated(subset=["symbol", "timeframe", "timestamp"]).sum())
    if duplicate_count:
        raise ValueError(f"Duplicate timestamps per symbol/timeframe found: {duplicate_count}")
    for (_, _), group in frame.assign(timestamp=timestamps).groupby(["symbol", "timeframe"], sort=False):
        if not group["timestamp"].is_monotonic_increasing:
            raise ValueError("Timestamps must be sorted ascending per symbol/timeframe")

    numeric_columns = ["open", "high", "low", "close", "volume", "spread"]
    numeric = frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    nan_count = int(numeric.isna().sum().sum())
    infinite_count = int(np.isinf(numeric.to_numpy(dtype=float)).sum()) if not numeric.isna().any().any() else 0
    if nan_count:
        raise ValueError("OHLCV numeric columns contain NaN or non-numeric values")
    if infinite_count:
        raise ValueError("OHLCV numeric columns contain infinite values")

    invalid_mask = (
        (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1))
        | (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1))
        | (numeric[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (numeric["volume"] < 0)
        | (numeric["spread"] < 0)
    )
    invalid_count = int(invalid_mask.sum())
    if invalid_count:
        raise ValueError(f"Invalid candles found: {invalid_count}")

    missing_bars = 0
    validated = frame.assign(timestamp=timestamps)
    for (_, _), group in validated.groupby(["symbol", "timeframe"], sort=False):
        missing_bars += _count_missing_bars(
            group["timestamp"].reset_index(drop=True),
            allow_session_gaps=allow_session_gaps,
            max_session_gap=pd.Timedelta(minutes=max_session_gap_minutes),
        )
    if missing_bars > missing_threshold:
        raise ValueError(f"Missing bars {missing_bars} exceeds threshold {missing_threshold}")

    symbol = _summarize_unique(frame["symbol"])
    timeframe = _summarize_unique(frame["timeframe"])
    timezone = str(getattr(timestamps.dt, "tz", None) or "naive/broker-time")
    return DataQualityReport(
        symbol=symbol,
        timeframe=timeframe,
        rows=len(frame),
        start=timestamps.iloc[0].isoformat(),
        end=timestamps.iloc[-1].isoformat(),
        duplicate_timestamps=duplicate_count,
        missing_bars=missing_bars,
        invalid_candles=invalid_count,
        nan_count=nan_count,
        infinite_count=infinite_count,
        median_spread=float(numeric["spread"].median()),
        p95_spread=float(numeric["spread"].quantile(0.95)),
        timezone=timezone,
        source=source,
        source_path=source_path,
        timestamp_semantics=timestamp_semantics,
    )


def _count_missing_bars(
    timestamps: pd.Series,
    allow_session_gaps: bool = False,
    max_session_gap: pd.Timedelta = pd.Timedelta(hours=3),
) -> int:
    if len(timestamps) < 3:
        return 0
    deltas = timestamps.diff().dropna()
    expected = deltas.mode().iloc[0]
    if expected <= pd.Timedelta(0):
        return 0
    missing = ((deltas / expected).round().astype(int) - 1).clip(lower=0)
    if allow_session_gaps:
        for position, delta in enumerate(deltas, start=1):
            if delta <= expected:
                continue
            previous_timestamp = timestamps.iloc[position - 1]
            current_timestamp = timestamps.iloc[position]
            if _is_market_session_gap(previous_timestamp, current_timestamp, max_session_gap):
                missing.iloc[position - 1] = 0
    return int(missing.sum())


def _is_market_session_gap(previous_timestamp: pd.Timestamp, current_timestamp: pd.Timestamp, max_session_gap: pd.Timedelta) -> bool:
    if current_timestamp <= previous_timestamp:
        return False
    if current_timestamp - previous_timestamp <= max_session_gap:
        return True
    dates = pd.date_range(previous_timestamp.normalize(), current_timestamp.normalize(), freq="D")
    return any(day.weekday() >= 5 for day in dates)


def _summarize_unique(values: pd.Series) -> str:
    unique = [str(value) for value in values.dropna().unique()]
    if len(unique) <= 3:
        return ",".join(unique)
    return f"{len(unique)} values"

from __future__ import annotations

import numpy as np
import pandas as pd

from algo_trade.types import FeatureFrame

FEATURE_SCHEMA_VERSION = "technical_v2"
FEATURE_SCHEMA = [
    "return",
    "log_return",
    "atr",
    "rsi",
    "ema_fast",
    "ema_slow",
    "macd",
    "adx",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "rolling_high",
    "rolling_low",
    "spread",
    "session_label",
    "hour_of_day",
    "day_of_week",
    "atr_percentile",
    "realized_volatility",
    "realized_volatility_percentile",
    "ema_slope",
    "trend_regime",
    "bb_width",
    "range_regime",
    "is_rollover",
    "spread_percentile_session",
]


def build_features(frame: pd.DataFrame) -> FeatureFrame:
    if {"symbol", "timeframe"}.issubset(frame.columns):
        pieces = []
        for _, group in frame.groupby(["symbol", "timeframe"], sort=False):
            pieces.append(_build_features_single(group.copy()))
        data = pd.concat(pieces).sort_index()
    else:
        data = _build_features_single(frame.copy())
    data[FEATURE_SCHEMA] = data[FEATURE_SCHEMA].replace([np.inf, -np.inf], np.nan)
    return FeatureFrame(data=data, feature_schema_version=FEATURE_SCHEMA_VERSION, schema=FEATURE_SCHEMA.copy())


def _build_features_single(data: pd.DataFrame) -> pd.DataFrame:
    data["return"] = data["close"].pct_change()
    data["log_return"] = np.log(data["close"] / data["close"].shift(1))
    data["atr"] = atr(data)
    data["rsi"] = rsi(data["close"])
    data["ema_fast"] = data["close"].ewm(span=5, adjust=False).mean()
    data["ema_slow"] = data["close"].ewm(span=10, adjust=False).mean()
    data["macd"] = data["close"].ewm(span=12, adjust=False).mean() - data["close"].ewm(span=26, adjust=False).mean()
    data["adx"] = adx(data)
    rolling_mean = data["close"].rolling(10, min_periods=3).mean()
    rolling_std = data["close"].rolling(10, min_periods=3).std()
    data["bb_mid"] = rolling_mean
    data["bb_upper"] = rolling_mean + 2 * rolling_std
    data["bb_lower"] = rolling_mean - 2 * rolling_std
    data["rolling_high"] = data["high"].rolling(5, min_periods=2).max().shift(1)
    data["rolling_low"] = data["low"].rolling(5, min_periods=2).min().shift(1)
    timestamps = pd.to_datetime(data["timestamp"])
    data["session_label"] = timestamps.map(session_label_for_timestamp)
    data["hour_of_day"] = timestamps.dt.hour
    data["day_of_week"] = timestamps.dt.dayofweek
    data["atr_percentile"] = rolling_percentile(data["atr"])
    data["realized_volatility"] = data["log_return"].rolling(20, min_periods=5).std()
    data["realized_volatility_percentile"] = rolling_percentile(data["realized_volatility"])
    data["ema_slope"] = data["ema_slow"].diff(3)
    data["trend_regime"] = trend_regime(data)
    data["bb_width"] = (data["bb_upper"] - data["bb_lower"]) / data["bb_mid"].replace(0, np.nan)
    data["range_regime"] = range_regime(data["bb_width"])
    data["is_rollover"] = data["session_label"].eq("rollover")
    data["spread_percentile_session"] = spread_percentile_by_session(data)
    return data


def validate_feature_schema(feature_frame: FeatureFrame, expected_schema: list[str] | None = None) -> None:
    expected = expected_schema or FEATURE_SCHEMA
    actual = [column for column in feature_frame.schema]
    if actual != expected:
        raise ValueError(f"Feature schema mismatch: expected {expected}, got {actual}")
    values = feature_frame.data[expected]
    finite_region = values.dropna()
    if finite_region.empty:
        raise ValueError("Feature frame has no fully formed rows")
    numeric = finite_region.select_dtypes(include=[np.number])
    if not numeric.empty and np.isinf(numeric.to_numpy()).any():
        raise ValueError("Feature frame contains infinite values")


def atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = data["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=2).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=2).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=2).mean()
    rs = gain / loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    value = value.mask((loss == 0) & (gain > 0), 100.0)
    value = value.mask((gain == 0) & (loss > 0), 0.0)
    value = value.mask((gain == 0) & (loss == 0), 50.0)
    return value


def adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
    up_move = data["high"].diff()
    down_move = -data["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = atr(data, period=period)
    plus_di = 100 * pd.Series(plus_dm, index=data.index).rolling(period, min_periods=2).sum() / tr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=data.index).rolling(period, min_periods=2).sum() / tr.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(period, min_periods=2).mean()


def session_label_for_timestamp(timestamp: object) -> str:
    hour = pd.Timestamp(timestamp).hour
    if hour in {21, 22, 23, 0}:
        return "rollover"
    if 1 <= hour < 8:
        return "Asia"
    if 8 <= hour < 13:
        return "London"
    return "NewYork"


def rolling_percentile(series: pd.Series, window: int = 200) -> pd.Series:
    return series.rolling(window, min_periods=5).rank(pct=True)


def trend_regime(data: pd.DataFrame) -> pd.Series:
    strong = data["adx"].fillna(0) >= 20
    up = (data["ema_fast"] > data["ema_slow"]) & (data["ema_slope"] > 0) & strong
    down = (data["ema_fast"] < data["ema_slow"]) & (data["ema_slope"] < 0) & strong
    return pd.Series(np.select([up, down], ["trend_up", "trend_down"], default="range"), index=data.index)


def range_regime(bb_width: pd.Series) -> pd.Series:
    width_percentile = rolling_percentile(bb_width)
    compressed = width_percentile <= 0.35
    expanding = width_percentile >= 0.65
    return pd.Series(np.select([compressed, expanding], ["compressed", "expanding"], default="range"), index=bb_width.index)


def spread_percentile_by_session(data: pd.DataFrame) -> pd.Series:
    return data.groupby("session_label")["spread"].rank(pct=True)

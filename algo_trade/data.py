from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from algo_trade.mt5_gateway import MT5Gateway

REQUIRED_COLUMNS = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "spread"]


class HistoricalDataProvider:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def path_for(self, symbol: str, timeframe: str) -> Path:
        return self.data_dir / f"{symbol}_{timeframe}.csv"

    def sample_path_for(self, symbol: str, timeframe: str) -> Path:
        return self.data_dir / f"sample_{symbol}_{timeframe}.csv"

    def load(self, symbol: str, timeframe: str, allow_sample_data: bool = False) -> pd.DataFrame:
        real_path = self.path_for(symbol, timeframe)
        sample_path = self.sample_path_for(symbol, timeframe)
        if real_path.exists():
            csv_path = real_path
            is_sample = False
        elif allow_sample_data and sample_path.exists():
            csv_path = sample_path
            is_sample = True
        elif sample_path.exists():
            raise FileNotFoundError(
                f"No real historical data found for {symbol} {timeframe} in {self.data_dir}. "
                f"A sample fixture exists at {sample_path}, but data.allow_sample_data=false."
            )
        else:
            raise FileNotFoundError(f"No historical data found for {symbol} {timeframe} in {self.data_dir}")
        frame = pd.read_csv(csv_path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
        frame.attrs["source_path"] = str(csv_path)
        frame.attrs["is_sample_data"] = is_sample
        return frame

    def save_real(self, symbol: str, timeframe: str, frame: pd.DataFrame) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.path_for(symbol, timeframe)
        frame.to_csv(csv_path, index=False)
        return csv_path


class MT5MarketDataProvider:
    """Market data reads backed by MT5.

    Order submission stays behind the execution adapter so signal/risk code cannot
    accidentally send broker orders while fetching market data.
    """

    def __init__(self, gateway: Any | None = None, env_path: str = ".env"):
        self.gateway = gateway or MT5Gateway(env_path=env_path)

    def latest_bars(self, symbol: str, timeframe: str, count: int = 250, include_current: bool = False) -> pd.DataFrame:
        return self.gateway.latest_bars(symbol, timeframe, count=count, include_current=include_current)

    def close(self) -> None:
        shutdown = getattr(self.gateway, "shutdown", None)
        if callable(shutdown):
            shutdown()


def load_backtest_data(config: Any, symbol: str, timeframe: str, gateway: Any | None = None) -> pd.DataFrame:
    data_config = config.raw.get("data", {})
    provider = HistoricalDataProvider(config.data_dir)
    allow_sample_data = bool(data_config.get("allow_sample_data", False))
    require_real_data = bool(data_config.get("require_real_data", True))
    auto_fetch_latest = bool(data_config.get("auto_fetch_latest", False))
    min_bars = int(data_config.get("min_bars", 0))
    backfill_bars = max(int(data_config.get("backfill_bars", min_bars or 0)), min_bars)

    try:
        frame = provider.load(symbol, timeframe, allow_sample_data=allow_sample_data)
    except FileNotFoundError:
        if not auto_fetch_latest:
            raise
        frame = _fetch_and_persist(provider, config, symbol, timeframe, backfill_bars, gateway)

    if len(frame) < min_bars and auto_fetch_latest:
        frame = _fetch_and_persist(provider, config, symbol, timeframe, backfill_bars, gateway)

    if len(frame) < min_bars:
        raise ValueError(
            f"Historical data incomplete for {symbol} {timeframe}: {len(frame)} bars found, "
            f"minimum required is {min_bars}. Enable data.auto_fetch_latest or provide a real CSV."
        )
    if require_real_data and bool(frame.attrs.get("is_sample_data", False)):
        raise ValueError("Sample data cannot be used for evidence backtests when data.require_real_data=true")
    return frame


def _fetch_and_persist(
    provider: HistoricalDataProvider,
    config: Any,
    symbol: str,
    timeframe: str,
    bars: int,
    gateway: Any | None,
) -> pd.DataFrame:
    if bars <= 0:
        raise ValueError("data.backfill_bars must be positive when data.auto_fetch_latest=true")
    market_data = MT5MarketDataProvider(gateway=gateway, env_path=config.raw.get("execution", {}).get("env_path", ".env"))
    try:
        frame = market_data.latest_bars(symbol, timeframe, count=bars, include_current=False)
    except Exception as exc:
        raise RuntimeError(
            f"Real historical data is missing/incomplete and MT5 backfill failed for {symbol} {timeframe}. "
            "Install/configure MetaTrader5 credentials in .env, or provide data/<symbol>_<timeframe>.csv."
        ) from exc
    finally:
        market_data.close()
    csv_path = provider.save_real(symbol, timeframe, frame)
    frame.attrs["source_path"] = str(csv_path)
    frame.attrs["is_sample_data"] = False
    frame.attrs["fetched_from"] = "mt5"
    return frame

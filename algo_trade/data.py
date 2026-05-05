from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from algo_trade.mt5_gateway import MT5Gateway

REQUIRED_COLUMNS = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "spread"]


class HistoricalDataProvider:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def load(self, symbol: str, timeframe: str) -> pd.DataFrame:
        csv_path = self.data_dir / f"sample_{symbol}_{timeframe}.csv"
        if not csv_path.exists():
            csv_path = self.data_dir / f"{symbol}_{timeframe}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"No historical data found for {symbol} {timeframe} in {self.data_dir}")
        frame = pd.read_csv(csv_path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
        return frame


class MT5MarketDataProvider:
    """Market data reads backed by MT5.

    Order submission stays behind the execution adapter so signal/risk code cannot
    accidentally send broker orders while fetching market data.
    """

    def __init__(self, gateway: Any | None = None, env_path: str = ".env"):
        self.gateway = gateway or MT5Gateway(env_path=env_path)

    def latest_bars(self, symbol: str, timeframe: str, count: int = 250, include_current: bool = False) -> pd.DataFrame:
        return self.gateway.latest_bars(symbol, timeframe, count=count, include_current=include_current)

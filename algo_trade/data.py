from __future__ import annotations

from pathlib import Path

import pandas as pd

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
    """Shadow-only adapter placeholder.

    This object deliberately exposes market data reads only. Order submission lives
    behind the execution adapter and is guarded out of this phase.
    """

    def latest_bars(self, symbol: str, timeframe: str, count: int = 250) -> pd.DataFrame:
        raise NotImplementedError("MT5 data reads are not wired in this skeleton yet")

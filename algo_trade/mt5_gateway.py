from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from algo_trade.env import load_dotenv
from algo_trade.types import OrderRequest, SignalSide


TIMEFRAME_NAMES: dict[str, str] = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


@dataclass(frozen=True)
class MT5Credentials:
    login: str
    password: str
    server: str

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "MT5Credentials":
        load_dotenv(env_path)
        login = os.getenv("ACCOUNT_ID") or os.getenv("MT5_LOGIN")
        password = os.getenv("ACCOUNT_PASSWORD") or os.getenv("MT5_PASSWORD")
        server = os.getenv("SERVER_NAME") or os.getenv("MT5_SERVER")
        missing = [
            name
            for name, value in {
                "ACCOUNT_ID/MT5_LOGIN": login,
                "ACCOUNT_PASSWORD/MT5_PASSWORD": password,
                "SERVER_NAME/MT5_SERVER": server,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing MT5 environment values: {missing}")
        return cls(login=str(login), password=str(password), server=str(server))


class MT5Gateway:
    def __init__(self, credentials: MT5Credentials | None = None, env_path: str = ".env"):
        self.credentials = credentials or MT5Credentials.from_env(env_path)
        self.mt5 = _import_mt5()
        self.connected = False

    def initialize(self) -> None:
        if self.connected:
            return
        ok = self.mt5.initialize(
            login=int(self.credentials.login),
            password=self.credentials.password,
            server=self.credentials.server,
        )
        if not ok:
            raise RuntimeError(f"MT5 initialize/login failed: {self.mt5.last_error()}")
        self.connected = True

    def shutdown(self) -> None:
        if self.connected:
            self.mt5.shutdown()
            self.connected = False

    def latest_bars(self, symbol: str, timeframe: str, count: int = 250, include_current: bool = False) -> pd.DataFrame:
        self.initialize()
        self._ensure_symbol(symbol)
        mt5_timeframe = self._timeframe(timeframe)
        request_count = count + (0 if include_current else 1)
        rates = self.mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, request_count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5 returned no bars for {symbol} {timeframe}: {self.mt5.last_error()}")

        frame = pd.DataFrame(rates)
        frame["timestamp"] = pd.to_datetime(frame["time"], unit="s")
        frame["symbol"] = symbol
        frame["timeframe"] = timeframe
        if "tick_volume" in frame.columns:
            frame["volume"] = frame["tick_volume"]
        elif "real_volume" in frame.columns:
            frame["volume"] = frame["real_volume"]
        else:
            frame["volume"] = 0
        if "spread" not in frame.columns:
            frame["spread"] = 0

        frame = frame[["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "spread"]]
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        if not include_current and len(frame) > count:
            frame = frame.iloc[:-1].reset_index(drop=True)
        return frame.tail(count).reset_index(drop=True)

    def current_price(self, symbol: str, side: SignalSide) -> float:
        self.initialize()
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5 returned no tick for {symbol}: {self.mt5.last_error()}")
        return float(tick.ask if side == SignalSide.BUY else tick.bid)

    def account_equity(self) -> float:
        self.initialize()
        account = self.mt5.account_info()
        if account is None:
            raise RuntimeError(f"MT5 returned no account info: {self.mt5.last_error()}")
        return float(account.equity)

    def open_positions_count(self, symbol: str) -> int:
        self.initialize()
        positions = self.mt5.positions_get(symbol=symbol)
        if positions is None:
            return 0
        return len(positions)

    def is_market_open(self, symbol: str, max_tick_age_seconds: int = 1800) -> bool:
        self.initialize()
        info = self.mt5.symbol_info(symbol)
        tick = self.mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return False
        if info.trade_mode == self.mt5.SYMBOL_TRADE_MODE_DISABLED:
            return False
        last_tick_time = datetime.fromtimestamp(tick.time)
        return (datetime.now() - last_tick_time).total_seconds() <= max_tick_age_seconds

    def submit_order(self, order: OrderRequest, deviation: int = 20) -> dict[str, Any]:
        self.initialize()
        self._ensure_symbol(order.symbol)
        order_type = self.mt5.ORDER_TYPE_BUY if order.side == SignalSide.BUY else self.mt5.ORDER_TYPE_SELL
        price = self.current_price(order.symbol, order.side)
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": float(order.volume),
            "type": order_type,
            "price": price,
            "sl": float(order.stop_loss),
            "tp": float(order.take_profit),
            "deviation": deviation,
            "magic": int(order.magic),
            "comment": order.comment,
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        result = self.mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"MT5 order_send returned None: {self.mt5.last_error()}")
        record = result._asdict() if hasattr(result, "_asdict") else dict(result)
        record["request"] = request
        return record

    def _ensure_symbol(self, symbol: str) -> None:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"MT5 symbol not found: {symbol}")
        if not info.visible and not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f"MT5 could not select symbol: {symbol}")

    def _timeframe(self, timeframe: str) -> int:
        attr = TIMEFRAME_NAMES.get(timeframe.upper())
        if attr is None or not hasattr(self.mt5, attr):
            raise ValueError(f"Unsupported MT5 timeframe {timeframe!r}")
        return int(getattr(self.mt5, attr))


def _import_mt5() -> Any:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required for real MT5 data/execution") from exc
    return mt5

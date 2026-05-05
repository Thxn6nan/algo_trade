from __future__ import annotations

from algo_trade.mt5_gateway import MT5Gateway

_gateway: MT5Gateway | None = None


def initialize_mt5() -> bool:
    global _gateway
    try:
        _gateway = MT5Gateway()
        _gateway.initialize()
        return True
    except Exception:
        _gateway = None
        return False


def is_market_open(symbol: str) -> bool:
    if _gateway is None:
        return False
    return _gateway.is_market_open(symbol)


def shutdown_mt5() -> None:
    global _gateway
    if _gateway is not None:
        _gateway.shutdown()
    _gateway = None


if __name__ == "__main__":
    raise SystemExit(0 if initialize_mt5() else 1)

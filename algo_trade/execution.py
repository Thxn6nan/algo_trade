from __future__ import annotations

from typing import Any

from algo_trade.types import OrderRequest


class MT5ExecutionAdapter:
    """Guarded execution interface."""

    def __init__(self, gateway: Any | None = None, send_orders: bool = False):
        self.gateway = gateway
        self.send_orders = send_orders

    def submit_order(self, order: OrderRequest) -> dict[str, Any]:
        if not self.send_orders:
            raise RuntimeError("Order submission disabled: shadow/backtest/paper phase is log-only")
        if self.gateway is None:
            raise RuntimeError("Order submission requires an MT5 gateway")
        return self.gateway.submit_order(order)

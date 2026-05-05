from __future__ import annotations

from algo_trade.types import OrderRequest


class MT5ExecutionAdapter:
    """Guarded execution interface.

    Paper/live order submission is intentionally unavailable until the backtest,
    robustness, shadow, and risk controls have been proven.
    """

    def __init__(self, send_orders: bool = False):
        self.send_orders = send_orders

    def submit_order(self, order: OrderRequest) -> None:
        if not self.send_orders:
            raise RuntimeError("Order submission disabled: shadow/backtest phase is log-only")
        raise NotImplementedError("Live order submission is out of scope for this phase")

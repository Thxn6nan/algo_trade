from __future__ import annotations

import uuid

from algo_trade.config import AppConfig
from algo_trade.data import MT5MarketDataProvider
from algo_trade.execution import MT5ExecutionAdapter
from algo_trade.storage import RunRecorder


class ShadowRunner:
    def __init__(self, config: AppConfig):
        self.config = config
        self.market_data = MT5MarketDataProvider()
        self.execution = MT5ExecutionAdapter(send_orders=False)

    def run_once(self) -> str:
        if self.config.raw["shadow"].get("send_orders") is not False:
            raise RuntimeError("Shadow mode requires send_orders=false")
        run_id = f"shadow-{uuid.uuid4().hex[:12]}"
        recorder = RunRecorder(run_id, self.config.output_dir / run_id)
        try:
            recorder.record(
                "system_events",
                "system_events",
                {
                    "event": "shadow_safety_ready",
                    "send_orders": False,
                    "message": "MT5 data adapter is placeholder; order adapter is disabled",
                },
            )
        finally:
            recorder.close()
        return run_id

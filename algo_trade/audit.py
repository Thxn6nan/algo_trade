from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from algo_trade.features import session_label_for_timestamp
from algo_trade.symbols import SymbolSpec


@dataclass(frozen=True)
class SymbolAuditReport:
    symbol: str
    source_path: str | None
    timestamp_semantics: str
    broker_metadata_confirmed: bool
    metadata_source: str
    configured_average_spread: float
    configured_max_spread_points: float | None
    spread_percentiles: dict[str, float]
    spread_by_session: dict[str, dict[str, float]]
    promotion_blockers: list[str]
    checks: dict[str, bool]

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def build_symbol_audit(
    frame: pd.DataFrame,
    symbol: SymbolSpec,
    timestamp_semantics: str,
    broker_metadata: dict[str, Any] | None = None,
    max_spread_median_to_config_ratio: float = 3.0,
    require_broker_metadata: bool = True,
) -> SymbolAuditReport:
    spread = pd.to_numeric(frame["spread"], errors="coerce").dropna()
    spread_percentiles = _spread_percentiles(spread)
    by_session = _spread_by_session(frame)
    broker_confirmed = bool(broker_metadata) or symbol.metadata_confirmed
    metadata_source = "broker_snapshot" if broker_metadata else symbol.metadata_source

    configured_average = float(symbol.average_spread)
    median_spread = spread_percentiles.get("p50", 0.0)
    spread_config_ok = configured_average > 0 and (
        median_spread / configured_average <= max_spread_median_to_config_ratio
    )
    max_spread_ok = symbol.max_spread_points is None or symbol.max_spread_points >= spread_percentiles.get("p50", 0.0)

    checks = {
        "broker_metadata_confirmed": (not require_broker_metadata) or broker_confirmed,
        "spread_config_matches_data": spread_config_ok,
        "max_spread_covers_median": max_spread_ok,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    blockers = [
        "broker_metadata_unconfirmed" if reason == "broker_metadata_confirmed" else reason
        for reason in blockers
    ]
    blockers = [
        "spread_config_mismatch" if reason == "spread_config_matches_data" else reason
        for reason in blockers
    ]

    return SymbolAuditReport(
        symbol=symbol.name,
        source_path=str(frame.attrs.get("source_path")) if frame.attrs.get("source_path") else None,
        timestamp_semantics=timestamp_semantics,
        broker_metadata_confirmed=broker_confirmed,
        metadata_source=metadata_source,
        configured_average_spread=configured_average,
        configured_max_spread_points=symbol.max_spread_points,
        spread_percentiles=spread_percentiles,
        spread_by_session=by_session,
        promotion_blockers=blockers,
        checks=checks,
    )


def _spread_percentiles(spread: pd.Series) -> dict[str, float]:
    if spread.empty:
        return {key: 0.0 for key in ["min", "p50", "p75", "p90", "p95", "p99", "max"]}
    return {
        "min": float(spread.min()),
        "p50": float(spread.quantile(0.50)),
        "p75": float(spread.quantile(0.75)),
        "p90": float(spread.quantile(0.90)),
        "p95": float(spread.quantile(0.95)),
        "p99": float(spread.quantile(0.99)),
        "max": float(spread.max()),
    }


def _spread_by_session(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    data = frame.copy()
    data["session_label"] = pd.to_datetime(data["timestamp"]).map(session_label_for_timestamp)
    summaries: dict[str, dict[str, float]] = {}
    for session, group in data.groupby("session_label", sort=False):
        summaries[str(session)] = _spread_percentiles(pd.to_numeric(group["spread"], errors="coerce").dropna())
    return summaries

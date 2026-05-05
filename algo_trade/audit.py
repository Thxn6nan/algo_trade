from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from algo_trade.features import session_label_for_timestamp
from algo_trade.symbols import SymbolSpec


CRITICAL_BROKER_FIELDS = [
    "point",
    "digits",
    "spread",
    "tick_size",
    "tick_value",
    "contract_size",
    "trade_tick_size",
    "trade_tick_value",
    "volume_min",
    "volume_max",
    "volume_step",
]


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
    broker_metadata_comparison: dict[str, Any]
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
    broker_comparison = compare_broker_metadata(symbol, broker_metadata, max_spread_median_to_config_ratio)
    broker_confirmed = broker_comparison["passed"] if require_broker_metadata else bool(
        broker_comparison["passed"] or symbol.metadata_confirmed
    )
    metadata_source = "broker_snapshot" if broker_comparison["snapshot_present"] else symbol.metadata_source

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
    blockers = [_broker_metadata_blocker(broker_comparison) if reason == "broker_metadata_confirmed" else reason for reason in blockers]
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
        broker_metadata_comparison=broker_comparison,
        promotion_blockers=blockers,
        checks=checks,
    )


def compare_broker_metadata(
    symbol: SymbolSpec,
    broker_metadata: dict[str, Any] | None,
    max_spread_to_config_ratio: float = 3.0,
) -> dict[str, Any]:
    if not broker_metadata:
        return {
            "snapshot_present": False,
            "passed": False,
            "required_fields": CRITICAL_BROKER_FIELDS,
            "missing_fields": CRITICAL_BROKER_FIELDS.copy(),
            "mismatches": {},
            "checks": {},
        }

    checks = {
        "point": _field_check(broker_metadata, "point", symbol.pip_size),
        "digits": _field_check(broker_metadata, "digits", _decimal_digits(symbol.pip_size)),
        "spread": _spread_check(broker_metadata, symbol, max_spread_to_config_ratio),
        "tick_size": _field_check(broker_metadata, "tick_size", symbol.tick_size),
        "tick_value": _field_check(broker_metadata, "tick_value", symbol.tick_value),
        "contract_size": _field_check(broker_metadata, "contract_size", symbol.contract_size),
        "trade_tick_size": _field_check(broker_metadata, "trade_tick_size", symbol.tick_size),
        "trade_tick_value": _field_check(broker_metadata, "trade_tick_value", symbol.tick_value),
        "volume_min": _field_check(broker_metadata, "volume_min", symbol.min_lot),
        "volume_max": _field_check(broker_metadata, "volume_max", symbol.max_lot),
        "volume_step": _field_check(broker_metadata, "volume_step", symbol.lot_step),
    }
    missing = [name for name, check in checks.items() if check.get("missing")]
    mismatches = {name: check for name, check in checks.items() if not check.get("missing") and not check["passed"]}
    return {
        "snapshot_present": True,
        "passed": not missing and not mismatches,
        "required_fields": CRITICAL_BROKER_FIELDS,
        "missing_fields": missing,
        "mismatches": mismatches,
        "checks": checks,
    }


def _field_check(broker_metadata: dict[str, Any], key: str, expected: float | int | None) -> dict[str, Any]:
    if key not in broker_metadata or broker_metadata.get(key) is None:
        return {"expected": expected, "actual": None, "passed": False, "missing": True}
    actual = broker_metadata.get(key)
    passed = _numeric_equal(actual, expected)
    return {"expected": expected, "actual": actual, "passed": passed, "missing": False}


def _spread_check(
    broker_metadata: dict[str, Any],
    symbol: SymbolSpec,
    max_spread_to_config_ratio: float,
) -> dict[str, Any]:
    key = "spread"
    if key not in broker_metadata or broker_metadata.get(key) is None:
        return {
            "expected": {"average_spread": symbol.average_spread, "max_spread_points": symbol.max_spread_points},
            "actual": None,
            "passed": False,
            "missing": True,
        }
    actual = float(broker_metadata[key])
    max_spread = symbol.max_spread_points
    configured_average = float(symbol.average_spread)
    within_max = max_spread is None or actual <= float(max_spread)
    within_ratio = configured_average > 0 and actual / configured_average <= max_spread_to_config_ratio
    return {
        "expected": {"average_spread": symbol.average_spread, "max_spread_points": symbol.max_spread_points},
        "actual": actual,
        "passed": actual > 0 and within_max and within_ratio,
        "missing": False,
    }


def _broker_metadata_blocker(comparison: dict[str, Any]) -> str:
    if not comparison.get("snapshot_present"):
        return "broker_metadata_unconfirmed"
    if comparison.get("missing_fields"):
        return "broker_metadata_incomplete"
    return "broker_metadata_mismatch"


def _numeric_equal(actual: Any, expected: float | int | None) -> bool:
    if expected is None:
        return actual is None
    return abs(float(actual) - float(expected)) <= 1e-9


def _decimal_digits(value: float) -> int:
    decimal = Decimal(str(value)).normalize()
    return max(0, -decimal.as_tuple().exponent)


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

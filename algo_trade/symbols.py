from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True)
class SymbolSpec:
    name: str
    asset_class: str
    magic: int
    pip_size: float
    pip_value: float
    contract_size: float
    min_lot: float
    max_lot: float
    lot_step: float
    average_spread: float
    trading_session: str
    broker_suffix: str | None = None
    canonical_symbol: str | None = None
    broker_symbol: str | None = None
    base_currency: str | None = None
    quote_currency: str | None = None
    profit_currency: str | None = None
    margin_currency: str | None = None
    tick_size: float | None = None
    tick_value: float | None = None
    stop_level_points: int = 0
    freeze_level_points: int = 0
    max_spread_points: float | None = None
    enabled: bool = True

    @classmethod
    def from_config(cls, name: str, raw: dict[str, Any]) -> "SymbolSpec":
        pip_size = float(raw.get("pip_size", raw.get("tick_size")))
        pip_value = float(raw.get("pip_value", raw.get("tick_value")))
        return cls(
            name=name,
            asset_class=raw["asset_class"],
            magic=int(raw["magic"]),
            pip_size=pip_size,
            pip_value=pip_value,
            contract_size=float(raw["contract_size"]),
            min_lot=float(raw["min_lot"]),
            max_lot=float(raw["max_lot"]),
            lot_step=float(raw["lot_step"]),
            average_spread=float(raw.get("average_spread", raw.get("average_spread_points", 0))),
            trading_session=str(raw.get("trading_session", raw.get("trading_sessions", {}).get("timezone", "broker"))),
            broker_suffix=raw.get("broker_suffix"),
            canonical_symbol=raw.get("canonical_symbol"),
            broker_symbol=raw.get("broker_symbol", name),
            base_currency=raw.get("base_currency"),
            quote_currency=raw.get("quote_currency"),
            profit_currency=raw.get("profit_currency"),
            margin_currency=raw.get("margin_currency"),
            tick_size=float(raw.get("tick_size", pip_size)),
            tick_value=float(raw.get("tick_value", pip_value)),
            stop_level_points=int(raw.get("stop_level_points", 0)),
            freeze_level_points=int(raw.get("freeze_level_points", 0)),
            max_spread_points=float(raw["max_spread_points"]) if raw.get("max_spread_points") is not None else None,
            enabled=bool(raw.get("enabled", True)),
        )

    def round_lot(self, lots: float, max_lot_override: float | None = None) -> float:
        capped = min(max(lots, self.min_lot), max_lot_override or self.max_lot, self.max_lot)
        step = Decimal(str(self.lot_step))
        rounded_steps = (Decimal(str(capped)) / step).to_integral_value(rounding=ROUND_HALF_UP)
        rounded = rounded_steps * step
        return float(max(Decimal(str(self.min_lot)), min(rounded, Decimal(str(self.max_lot)))))


class SymbolRegistry:
    def __init__(self, specs: dict[str, SymbolSpec]):
        self._specs = specs

    @classmethod
    def from_config(cls, raw_symbols: dict[str, Any]) -> "SymbolRegistry":
        registry = raw_symbols.get("registry") or {}
        specs = {name: SymbolSpec.from_config(name, value) for name, value in registry.items()}
        return cls(specs)

    def get(self, symbol: str) -> SymbolSpec:
        try:
            spec = self._specs[symbol]
        except KeyError as exc:
            raise KeyError(f"Missing symbol metadata for {symbol}") from exc
        if not spec.enabled:
            raise KeyError(f"Symbol metadata disabled for {symbol}")
        return spec

    def enabled(self, names: list[str]) -> list[SymbolSpec]:
        return [self.get(name) for name in names]

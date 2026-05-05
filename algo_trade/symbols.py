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

    @classmethod
    def from_config(cls, name: str, raw: dict[str, Any]) -> "SymbolSpec":
        return cls(
            name=name,
            asset_class=raw["asset_class"],
            magic=int(raw["magic"]),
            pip_size=float(raw["pip_size"]),
            pip_value=float(raw["pip_value"]),
            contract_size=float(raw["contract_size"]),
            min_lot=float(raw["min_lot"]),
            max_lot=float(raw["max_lot"]),
            lot_step=float(raw["lot_step"]),
            average_spread=float(raw["average_spread"]),
            trading_session=str(raw["trading_session"]),
            broker_suffix=raw.get("broker_suffix"),
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
            return self._specs[symbol]
        except KeyError as exc:
            raise KeyError(f"Missing symbol metadata for {symbol}") from exc

    def enabled(self, names: list[str]) -> list[SymbolSpec]:
        return [self.get(name) for name in names]

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_MODES = {"research", "backtest", "walk_forward", "shadow", "paper", "live"}


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]
    path: Path
    config_hash: str

    @property
    def mode(self) -> str:
        return self.raw["mode"]["name"]

    @property
    def enabled_symbols(self) -> list[str]:
        return list(self.raw["symbols"]["enabled"])

    @property
    def output_dir(self) -> Path:
        return Path(self.raw.get("paths", {}).get("output_dir", "runs"))

    @property
    def data_dir(self) -> Path:
        return Path(self.raw.get("paths", {}).get("data_dir", "data"))


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    validate_config(raw)
    return AppConfig(raw=raw, path=config_path, config_hash=hash_config(raw))


def with_mode(config: AppConfig, mode: str) -> AppConfig:
    raw = deepcopy(config.raw)
    raw.setdefault("mode", {})["name"] = mode
    validate_config(raw)
    return AppConfig(raw=raw, path=config.path, config_hash=hash_config(raw))


def validate_config(raw: dict[str, Any]) -> None:
    required_groups = ["mode", "symbols", "risk", "signal", "backtest", "shadow", "execution", "real_data"]
    missing = [group for group in required_groups if group not in raw]
    if missing:
        raise ValueError(f"Missing config groups: {missing}")

    mode = raw["mode"].get("name")
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported mode {mode!r}")

    if raw["shadow"].get("send_orders") is not False:
        raise ValueError("shadow.send_orders must be false")

    execution = raw["execution"]
    if mode == "paper" and execution.get("send_orders") is not False:
        raise ValueError("paper mode requires execution.send_orders=false")
    if mode == "live" and execution.get("send_orders") is not True:
        raise ValueError("live mode requires execution.send_orders=true")

    enabled = raw["symbols"].get("enabled") or []
    registry = raw["symbols"].get("registry") or {}
    unknown = [symbol for symbol in enabled if symbol not in registry]
    if unknown:
        raise ValueError(f"Enabled symbols missing from registry: {unknown}")

    risk = raw["risk"]
    for key in ["risk_per_trade", "daily_loss_limit", "max_open_positions", "max_lot"]:
        if key not in risk:
            raise ValueError(f"Missing risk.{key}")
    if not 0 <= float(risk["risk_per_trade"]) <= 0.01:
        raise ValueError("risk.risk_per_trade must be between 0 and 1%")

    if raw["backtest"].get("execute_signal_at") != "next_open":
        raise ValueError("Only next_open execution is supported to prevent lookahead")
    if raw["backtest"].get("same_bar_policy") != "conservative":
        raise ValueError("Only conservative same-bar policy is supported initially")


def hash_config(raw: dict[str, Any]) -> str:
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

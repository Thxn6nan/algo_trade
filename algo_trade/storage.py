from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlLogger:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, record: dict[str, Any]) -> None:
        path = self.run_dir / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, sort_keys=True) + "\n")


class SQLiteStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.ensure_schema()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()

    def ensure_schema(self) -> None:
        tables = [
            "runs",
            "signals",
            "decisions",
            "orders",
            "fills",
            "positions",
            "trades",
            "risk_events",
            "system_events",
            "reconciliation_events",
            "model_versions",
            "config_versions",
            "symbol_registry_snapshots",
        ]
        for table in tables:
            self.connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    timestamp TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
        self.connection.commit()

    def insert(self, table: str, run_id: str, payload: dict[str, Any], timestamp: str | None = None) -> None:
        self.connection.execute(
            f"INSERT INTO {table} (run_id, timestamp, payload) VALUES (?, ?, ?)",
            (run_id, timestamp, json.dumps(payload, default=str, sort_keys=True)),
        )


class RunRecorder:
    def __init__(
        self,
        run_id: str,
        run_dir: str | Path,
        mode: str = "unknown",
        config_hash: str = "unknown",
        schema_version: str = "core_v1",
    ):
        self.run_id = run_id
        self.run_dir = Path(run_dir)
        self.mode = mode
        self.config_hash = config_hash
        self.schema_version = schema_version
        self.jsonl = JsonlLogger(self.run_dir)
        self.sqlite = SQLiteStore(self.run_dir / "state.sqlite")

    def close(self) -> None:
        self.sqlite.close()

    def record(self, stream: str, table: str, payload: dict[str, Any], timestamp: str | None = None) -> None:
        record = self._envelope(stream, payload, timestamp)
        self.jsonl.write(stream, record)
        self.sqlite.insert(table, self.run_id, record, record["timestamp"])

    def _envelope(self, stream: str, payload: dict[str, Any], timestamp: str | None = None) -> dict[str, Any]:
        event_timestamp = timestamp or payload.get("timestamp") or datetime.now(UTC).isoformat()
        record = {
            "timestamp": event_timestamp,
            "run_id": self.run_id,
            "mode": self.mode,
            "config_hash": self.config_hash,
            "schema_version": self.schema_version,
            "event_type": payload.get("event_type") or payload.get("event") or stream,
            "severity": payload.get("severity", "INFO"),
            **payload,
        }
        record["run_id"] = self.run_id
        return record

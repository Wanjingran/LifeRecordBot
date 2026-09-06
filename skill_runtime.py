from __future__ import annotations

import contextlib
import csv
import importlib
import io
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


ITEM_ACTIONS = {"expense", "income", "date", "note", "mood", "reminder", "todo", "budget"}
NO_ITEM_ACTIONS = {"delete", "weather", "chart", "summary", "view", "study_plan", "mood_trend", "answer"}
REPEAT_VALUES = {"none", "daily", "weekly", "monthly", "yearly"}


class ActionContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ActionContract":
        if self.type in ITEM_ACTIONS and not isinstance(self.items, list):
            raise ValueError("items must be a list")
        if self.type == "answer" and not isinstance(self.answer, str):
            raise ValueError("answer action requires text")
        if self.type == "weather" and not isinstance(self.text, str):
            raise ValueError("weather action requires source text")
        for item in self.items:
            if not isinstance(item, dict):
                raise ValueError("every action item must be an object")
            if self.type in {"expense", "income", "budget"}:
                amount = float(item.get("amount", 0))
                if not math.isfinite(amount) or amount <= 0:
                    raise ValueError("amount must be a positive finite number")
            if self.type in {"expense", "income", "date", "note", "mood"} and item.get("date"):
                date.fromisoformat(str(item["date"]))
            if self.type == "reminder":
                datetime.strptime(str(item.get("remind_at") or ""), "%Y-%m-%d %H:%M:%S")
                if str(item.get("repeat") or "none").lower() not in REPEAT_VALUES:
                    raise ValueError("invalid reminder repeat value")
            if self.type == "mood" and item.get("score") is not None:
                score = int(item["score"])
                if score < -2 or score > 2:
                    raise ValueError("mood score must be between -2 and 2")
        return self


def validate_action_contract(action: dict[str, Any], valid_types: set[str]) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    if action.get("type") not in valid_types:
        raise ValueError("unknown action type")
    ActionContract.model_validate(action)
    return action


@dataclass(frozen=True)
class EntitySpan:
    text: str
    start: int
    end: int
    value: str = ""
    kind: str = ""


class EntityMatch:
    """Small re.Match-compatible wrapper for entities parsed by JioNLP."""

    def __init__(self, entity: EntitySpan):
        self.entity = entity

    def start(self) -> int:
        return self.entity.start

    def end(self) -> int:
        return self.entity.end

    def span(self) -> tuple[int, int]:
        return self.entity.start, self.entity.end

    def group(self, index: int = 0) -> str:
        return self.entity.text if index == 0 else self.entity.value


@dataclass(frozen=True)
class SemanticSnapshot:
    text: str
    sentences: tuple[str, ...]
    money: tuple[EntitySpan, ...]
    times: tuple[EntitySpan, ...]
    location: str
    provider: str


_JIO: Any | None = None
_JIO_FAILED = False
_RAPID_ENGINE: Any | None = None
_RAPID_FAILED = False


def _jio() -> Any | None:
    global _JIO, _JIO_FAILED
    if _JIO is not None:
        return _JIO
    if _JIO_FAILED:
        return None
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            _JIO = importlib.import_module("jionlp")
        return _JIO
    except Exception:
        _JIO_FAILED = True
        return None


def _fallback_sentences(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r"[，,。；;！？!?\n]+", text) if part.strip()) or (text.strip(),)


def analyze_semantics(text: str, now: datetime | None = None) -> SemanticSnapshot:
    text = str(text or "").strip()
    jio = _jio()
    if not text or jio is None:
        return SemanticSnapshot(text, _fallback_sentences(text), (), (), "", "fallback")
    try:
        sentences = tuple(part.strip() for part in jio.split_sentence(text, criterion="fine") if part.strip())
    except Exception:
        sentences = _fallback_sentences(text)
    money: list[EntitySpan] = []
    try:
        for item in jio.ner.extract_money(text, with_parsing=True, ret_all=False):
            offset = item.get("offset") or [0, 0]
            detail = item.get("detail") or {}
            value = detail.get("num")
            if isinstance(value, list):
                continue
            money.append(EntitySpan(str(item.get("text") or ""), int(offset[0]), int(offset[1]), str(value or ""), "money"))
    except Exception:
        money = []
    times: list[EntitySpan] = []
    try:
        base = (now or datetime.now()).timestamp()
        for item in jio.ner.extract_time(text, time_base=base, with_parsing=True, ret_all=False, ret_future=True):
            offset = item.get("offset") or [0, 0]
            detail = item.get("detail") or {}
            value = detail.get("time") or ""
            times.append(EntitySpan(str(item.get("text") or ""), int(offset[0]), int(offset[1]), json.dumps(value, ensure_ascii=False), str(item.get("type") or "time")))
    except Exception:
        times = []
    location = ""
    try:
        parsed = jio.parse_location(text)
        if any(parsed.get(key) for key in ("province", "city", "county")):
            location = "".join(str(parsed.get(key) or "") for key in ("city", "county")) or str(parsed.get("full_location") or "")
    except Exception:
        location = ""
    return SemanticSnapshot(text, sentences or _fallback_sentences(text), tuple(money), tuple(times), location, "jionlp")


def first_money_match(text: str) -> EntityMatch | None:
    snapshot = analyze_semantics(text)
    for entity in snapshot.money:
        try:
            value = float(entity.value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            normalized = EntitySpan(entity.text, entity.start, entity.end, f"{value:g}", entity.kind)
            return EntityMatch(normalized)
    return None


def semantic_sentences(text: str) -> list[str]:
    return list(analyze_semantics(text).sentences)


def semantic_location(text: str) -> str:
    return analyze_semantics(text).location


def rapid_ocr_text(image_path: Path | str) -> str:
    global _RAPID_ENGINE, _RAPID_FAILED
    if _RAPID_FAILED:
        return ""
    try:
        if _RAPID_ENGINE is None:
            rapidocr = importlib.import_module("rapidocr")
            _RAPID_ENGINE = rapidocr.RapidOCR()
        result = _RAPID_ENGINE(str(image_path))
        texts = getattr(result, "txts", None)
        if texts is None and isinstance(result, (tuple, list)) and result:
            rows = result[0] or []
            texts = [row[1] for row in rows if isinstance(row, (tuple, list)) and len(row) > 1]
        return " ".join(str(value).strip() for value in (texts or []) if str(value).strip())
    except Exception:
        _RAPID_FAILED = True
        return ""


def _initialize_database(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS record_snapshots (
            kind TEXT NOT NULL,
            row_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (kind, row_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_metadata (
            kind TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            synced_at TEXT NOT NULL
        )
        """
    )


def sync_csv_snapshot(database_path: Path | str, kind: str, csv_path: Path | str) -> int:
    database_path = Path(database_path)
    csv_path = Path(csv_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        return 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with contextlib.closing(sqlite3.connect(database_path, timeout=15)) as connection:
        _initialize_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM record_snapshots WHERE kind = ?", (kind,))
        for index, row in enumerate(rows):
            row_id = str(row.get("id") or f"legacy-{index}")
            connection.execute(
                "INSERT INTO record_snapshots(kind, row_id, payload, synced_at) VALUES (?, ?, ?, ?)",
                (kind, row_id, json.dumps(row, ensure_ascii=False, sort_keys=True), synced_at),
            )
        connection.execute(
            "INSERT INTO sync_metadata(kind, source_path, row_count, synced_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET source_path=excluded.source_path, row_count=excluded.row_count, synced_at=excluded.synced_at",
            (kind, str(csv_path), len(rows), synced_at),
        )
        connection.commit()
    return len(rows)


def sync_all_snapshots(database_path: Path | str, sources: dict[str, Path]) -> dict[str, int]:
    return {kind: sync_csv_snapshot(database_path, kind, path) for kind, path in sources.items()}


def verify_snapshots(database_path: Path | str, sources: dict[str, Path]) -> dict[str, tuple[int, int]]:
    database_path = Path(database_path)
    if not database_path.exists():
        return {kind: (0, -1) for kind in sources}
    result: dict[str, tuple[int, int]] = {}
    with contextlib.closing(sqlite3.connect(database_path, timeout=15)) as connection:
        _initialize_database(connection)
        connection.commit()
        for kind, path in sources.items():
            with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
                csv_count = sum(1 for _ in csv.DictReader(handle))
            row = connection.execute("SELECT COUNT(*) FROM record_snapshots WHERE kind = ?", (kind,)).fetchone()
            result[kind] = (csv_count, int(row[0] if row else 0))
    return result
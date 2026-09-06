from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

import skill_runtime as runtime

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("liferecordbot_integration", ROOT / "bot.py")
bot = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bot)


def retarget(tmp_path: Path) -> None:
    bot.DATA_DIR = tmp_path / "records"
    bot.CHARTS_DIR = tmp_path / "charts"
    bot.PHOTO_DIR = tmp_path / "photos"
    bot.EXPENSES_CSV = bot.DATA_DIR / "expenses.csv"
    bot.INCOME_CSV = bot.DATA_DIR / "income.csv"
    bot.DATES_CSV = bot.DATA_DIR / "dates.csv"
    bot.NOTES_CSV = bot.DATA_DIR / "notes.csv"
    bot.MOODS_CSV = bot.DATA_DIR / "moods.csv"
    bot.REMINDERS_CSV = bot.DATA_DIR / "reminders.csv"
    bot.BUDGETS_CSV = bot.DATA_DIR / "budgets.csv"
    bot.TODOS_CSV = bot.DATA_DIR / "todos.csv"
    bot.GOALS_CSV = bot.DATA_DIR / "goals.csv"
    bot.GOAL_LOGS_CSV = bot.DATA_DIR / "goal_logs.csv"
    bot.RAW_JSONL = bot.DATA_DIR / "raw_messages.jsonl"
    bot.STATE_PATH = tmp_path / "state.json"


def test_action_contract_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        runtime.validate_action_contract(
            {"type": "expense", "items": [{"amount": 0}]}, {"expense"}
        )
    with pytest.raises(ValueError):
        runtime.validate_action_contract(
            {
                "type": "reminder",
                "items": [{"remind_at": "tomorrow", "repeat": "sometimes"}],
            },
            {"reminder"},
        )


def test_chinese_money_and_district_location() -> None:
    money = bot.expense_amount_match("\u65e9\u9910\u5341\u5757\u94b1")
    assert money is not None
    assert float(money.group(1)) == 10
    city = bot.extract_city(
        {"default_city": "\u6df1\u5733"},
        "\u6df1\u5733\u5357\u5c71\u533a\u660e\u5929\u5929\u6c14\u5982\u4f55",
    )
    assert "\u6df1\u5733" in city and "\u5357\u5c71" in city


def test_long_same_skill_message_records_every_item_on_shared_date(tmp_path: Path) -> None:
    retarget(tmp_path)
    bot.ensure_files()
    text = (
        "\u4e5d\u6708\u4e09\u53f7\u5496\u55619.9\uff0c12.5\u65e9\u9910\uff0c"
        "25\u4e2d\u5348\u996d\uff0c4.9\u4e70\u6c34\uff0c20\u5757\u6e38\u6cf3\uff0c32.9\u665a\u9910"
    )
    actions = bot.complete_local_record_actions(text)
    assert len(actions) == 1
    assert actions[0]["type"] == "expense"
    items = actions[0]["items"]
    assert len(items) == 6
    assert {item["date"] for item in items} == {"2026-09-03"}
    assert sum(float(item["amount"]) for item in items) == pytest.approx(105.2)
    assert sum(item["category"] == "\u9910\u996e" for item in items) == 5
    assert sum(item["category"] == "\u5a31\u4e50" for item in items) == 1

    reply = bot.handle_text(
        {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"},
        text,
        chat_id=1001,
    )
    rows = bot.read_csv_rows(bot.EXPENSES_CSV)
    assert "\u5df2\u8bb0\u5f55\u6d88\u8d39" in str(reply)
    assert len(rows) == 6
    assert {row["date"] for row in rows} == {"2026-09-03"}


def test_mixed_skill_message_is_not_swallowed_by_batch_parser() -> None:
    text = "\u65e9\u991012\uff0c\u4eca\u5929\u5fc3\u60c5\u4e0d\u9519"
    assert bot.complete_local_record_actions(text) == []
    assert bot.has_expense_hint(text)
    assert bot.is_mood_statement(text)


def test_sqlite_snapshot_matches_csv_and_closes_files(tmp_path: Path) -> None:
    csv_path = tmp_path / "expenses.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "date", "item", "amount"])
        writer.writeheader()
        writer.writerow(
            {"id": "one", "date": "2026-09-03", "item": "\u65e9\u9910", "amount": "12.5"}
        )
    database = tmp_path / "life_record.db"
    assert runtime.sync_csv_snapshot(database, "expenses", csv_path) == 1
    assert runtime.verify_snapshots(database, {"expenses": csv_path}) == {"expenses": (1, 1)}
    database.unlink()
    csv_path.unlink()


def test_ptb_job_queue_is_available_without_network() -> None:
    from telegram.ext import Application

    application = Application.builder().token("123456:TEST_TOKEN").build()
    assert application.job_queue is not None


@given(st.integers(min_value=1, max_value=999))
def test_duration_and_quantity_are_never_money(value: int) -> None:
    assert bot.expense_amount_match(f"\u5065\u8eab{value}\u5206\u949f") is None
    assert bot.expense_amount_match(f"\u8dd1\u6b65{value}\u6b21") is None
    explicit = bot.expense_amount_match(f"\u5065\u8eab{value}\u5757")
    assert explicit is not None
    assert float(explicit.group(1)) == value


@given(st.integers(min_value=1, max_value=28))
def test_calendar_date_is_never_money(day: int) -> None:
    assert bot.expense_amount_match(f"2026-09-{day:02d}\u5065\u8eab") is None
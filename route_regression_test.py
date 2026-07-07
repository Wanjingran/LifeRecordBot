from __future__ import annotations

import csv
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOT_PATH = ROOT / "bot.py"

spec = importlib.util.spec_from_file_location("liferecordbot", BOT_PATH)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def U(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


def active_flags(text: str) -> set[str]:
    flags = set()
    if bot.is_explicit_note_request(text):
        flags.add("note")
    if bot.has_expense_hint(text):
        flags.add("expense")
    if bot.has_income_hint(text):
        flags.add("income")
    if bot.is_mood_statement(text):
        flags.add("mood")
    if bot.has_chat_hint(text):
        flags.add("chat")
    if bot.has_weather_hint(text):
        flags.add("weather")
    if bot.has_event_hint(text):
        flags.add("event")
    if bot.has_study_plan_hint(text):
        flags.add("study_plan")
    if bot.chart_period_from_text(text):
        flags.add("chart")
    if bot.summary_period_from_text(text):
        flags.add("summary")
    view = bot.view_action_from_text(text)
    if view:
        flags.add("view:" + view.get("name", ""))
    if bot.daily_report_kind_from_text(text):
        flags.add("report")
    if bot.mood_trend_period_from_text(text):
        flags.add("mood_trend")
    return flags


CASES = [
    ("expense", U(r"\u65e9\u991025"), {"expense"}, False),
    ("expense umbrella", U(r"\u4e70\u96e8\u4f1e20"), {"expense"}, False),
    ("income", U(r"\u5de5\u8d44\u5230\u8d263000"), {"income"}, False),
    ("part time income", U(r"\u4eca\u5929\u517c\u804c\u6536\u5165200"), {"income"}, False),
    ("mood positive", U(r"\u4eca\u5929\u5fc3\u60c5\u4e0d\u9519"), {"mood"}, False),
    ("mood tired", U(r"\u6211\u6709\u70b9\u7d2f\u60f3\u4f11\u606f"), {"mood"}, False),
    ("chat feedback", U(r"\u8fd9\u4e2a\u529f\u80fd\u4e0d\u9519"), {"chat"}, False),
    ("chat encourage", U(r"\u9f13\u52b1\u6211\u4e00\u4e0b"), {"chat"}, False),
    ("weather tomorrow", U(r"\u660e\u5929\u5929\u6c14\u5982\u4f55"), {"weather"}, False),
    ("weather umbrella", U(r"\u4eca\u665a\u8981\u5e26\u4f1e\u5417"), {"weather"}, False),
    ("weather nice", U(r"\u4eca\u5929\u5929\u6c14\u4e0d\u9519"), {"weather"}, False),
    ("chart", U(r"\u672c\u6708\u6d88\u8d39\u5360\u6bd4\u56fe"), {"chart"}, False),
    ("summary", U(r"\u603b\u7ed3\u4e0b\u4eca\u5929"), {"summary"}, False),
    ("view budget", U(r"\u9884\u7b97\u8fd8\u5269\u591a\u5c11"), {"view:budget"}, False),
    ("view reminders", U(r"\u770b\u770b\u63d0\u9192"), {"view:reminders"}, False),
    ("study plan", U(r"\u5e2e\u6211\u628a\u4e03\u5929\u7b97\u6cd5\u590d\u4e60\u62c6\u6210\u8ba1\u5212"), {"study_plan"}, False),
    ("explicit note", U(r"\u8bb0\u4e00\u4e0b\u4eca\u5929\u53bb\u4e86\u56fe\u4e66\u9986"), {"note"}, False),
    ("expense chart", U(r"\u65e9\u991025\uff0c\u987a\u4fbf\u770b\u672c\u6708\u6d88\u8d39\u5360\u6bd4\u56fe"), {"expense", "chart"}, True),
    ("income expense", U(r"\u5de5\u8d44\u5230\u8d263000\uff0c\u665a\u4e0a\u6253\u8f66\u82b130"), {"income", "expense"}, True),
    ("event mood", U(r"\u660e\u5929\u4e0b\u5348\u4e09\u70b9\u8003\u8bd5\uff0c\u6211\u5f88\u7d27\u5f20"), {"event", "mood"}, True),
    ("study view", U(r"\u4e03\u5929\u7b97\u6cd5\u590d\u4e60\u5e2e\u6211\u62c6\u6210\u8ba1\u5212\uff0c\u7136\u540e\u770b\u770b\u5f85\u529e"), {"study_plan", "view:todo"}, True),
    ("weather reminder", U(r"\u660e\u5929\u665a\u4e0a\u4f1a\u4e0b\u96e8\u5417\uff0c\u5982\u679c\u4f1a\u4e0b\u96e8\u5c31\u516b\u70b9\u63d0\u9192\u6211\u5e26\u4f1e"), {"weather", "event"}, True),
    ("mood chat", U(r"\u4eca\u5929\u6709\u70b9\u7d2f\uff0c\u9f13\u52b1\u6211\u4e00\u4e0b"), {"mood", "chat"}, True),
    ("expense mood summary", U(r"\u5348\u996d28\uff0c\u4eca\u5929\u72b6\u6001\u4e0d\u9519\uff0c\u987a\u4fbf\u603b\u7ed3\u4e0b\u4eca\u5929"), {"expense", "mood", "summary"}, True),
    ("note summary", U(r"\u8bb0\u4e00\u4e0b\u4eca\u5929\u53bb\u4e86\u56fe\u4e66\u9986\uff0c\u987a\u4fbf\u603b\u7ed3\u4e0b\u4eca\u5929"), {"note", "summary"}, True),
]


CITY_CASES = [
    (U(r"\u660e\u5929\u5929\u6c14\u5982\u4f55"), "DEFAULT"),
    (U(r"\u6df1\u5733\u672a\u6765\u4e00\u5468\u5929\u6c14\u600e\u4e48\u6837"), U(r"\u6df1\u5733")),
    (U(r"\u4eca\u665a\u4f1a\u4e0b\u96e8\u5417"), "DEFAULT"),
]


AUGMENT_CASES = [
    (
        "augment event mood",
        U(r"\u660e\u5929\u4e0b\u5348\u4e09\u70b9\u8003\u8bd5\uff0c\u6211\u5f88\u7d27\u5f20"),
        {"type": "mood", "items": [{"date": "2026-01-01", "mood": "\u7d27\u5f20", "score": -1, "reason": "", "note": ""}]},
        {"mood", "date"},
    ),
    (
        "augment income expense",
        U(r"\u5de5\u8d44\u5230\u8d263000\uff0c\u665a\u4e0a\u6253\u8f66\u82b130"),
        {"type": "answer", "answer": "ok"},
        {"answer", "income", "expense"},
    ),
    (
        "augment weather reminder",
        U(r"\u660e\u5929\u665a\u4e0a\u4f1a\u4e0b\u96e8\u5417\uff0c\u5982\u679c\u4f1a\u4e0b\u96e8\u5c31\u516b\u70b9\u63d0\u9192\u6211\u5e26\u4f1e"),
        {"type": "answer", "answer": "ok"},
        {"answer", "weather", "reminder"},
    ),
    (
        "augment expense mood summary",
        U(r"\u5348\u996d28\uff0c\u4eca\u5929\u72b6\u6001\u4e0d\u9519\uff0c\u987a\u4fbf\u603b\u7ed3\u4e0b\u4eca\u5929"),
        {"type": "answer", "answer": "ok"},
        {"answer", "expense", "mood", "summary"},
    ),
    (
        "augment study view",
        U(r"\u4e03\u5929\u7b97\u6cd5\u590d\u4e60\u5e2e\u6211\u62c6\u6210\u8ba1\u5212\uff0c\u7136\u540e\u770b\u770b\u5f85\u529e"),
        {"type": "answer", "answer": "ok"},
        {"answer", "study_plan", "view"},
    ),
]

MULTI_HANDLE_CASES = [
    (
        "multi income expense",
        U(r"\u5de5\u8d44\u5230\u8d263000\uff0c\u665a\u4e0a\u6253\u8f66\u82b130"),
        {"income": 1, "expense": 1},
    ),
    (
        "multi expense mood summary",
        U(r"\u5348\u996d28\uff0c\u4eca\u5929\u72b6\u6001\u4e0d\u9519\uff0c\u987a\u4fbf\u603b\u7ed3\u4e0b\u4eca\u5929"),
        {"expense": 1, "mood": 1},
    ),
    (
        "multi event mood",
        U(r"\u660e\u5929\u4e0b\u5348\u4e09\u70b9\u8003\u8bd5\uff0c\u6211\u5f88\u7d27\u5f20"),
        {"reminder": 1, "mood": 1},
    ),
    (
        "multi distinct event reminder",
        U(r"\u6211\u660e\u5929\u4e5d\u70b9\u8003\u8bd5\uff0c\u6709\u70b9\u7d27\u5f20\uff0c\u63d0\u9192\u6211\u590d\u4e60\u51c6\u8003\u8bc1"),
        {"reminder": 2, "mood": 1},
    ),
    (
        "multi weather reminder",
        U(r"\u660e\u5929\u665a\u4e0a\u4f1a\u4e0b\u96e8\u5417\uff0c\u5982\u679c\u4f1a\u4e0b\u96e8\u5c31\u516b\u70b9\u63d0\u9192\u6211\u5e26\u4f1e"),
        {"reminder": 1},
    ),
    (
        "multi note summary",
        U(r"\u8bb0\u4e00\u4e0b\u4eca\u5929\u53bb\u4e86\u56fe\u4e66\u9986\uff0c\u987a\u4fbf\u603b\u7ed3\u4e0b\u4eca\u5929"),
        {"note": 1},
    ),
]

LOCAL_HANDLE_CASES = [
    ("local expense breakfast", U(r"\u65e9\u991025"), "\u5df2\u8bb0\u5f55\u6d88\u8d39", "expense"),
    ("local expense umbrella", U(r"\u4e70\u96e8\u4f1e20"), "\u5df2\u8bb0\u5f55\u6d88\u8d39", "expense"),
    ("local income salary", U(r"\u5de5\u8d44\u5230\u8d263000"), "\u5df2\u8bb0\u5f55\u6536\u5165", "income"),
    ("local mood", U(r"\u4eca\u5929\u5fc3\u60c5\u4e0d\u9519"), "\u5df2\u8bb0\u5f55\u5fc3\u60c5", "mood"),
    ("local explicit note", U(r"\u8bb0\u4e00\u4e0b\u4eca\u5929\u53bb\u4e86\u56fe\u4e66\u9986"), "\u5df2\u8bb0\u5f55\u751f\u6d3b\u4e8b\u9879", "note"),
]


def assert_route_cases(failures: list[str]) -> None:
    for name, text, expected_flags, expected_multi in CASES:
        flags = active_flags(text)
        missing = expected_flags - flags
        if missing:
            failures.append(f"{name}: missing {sorted(missing)} from {sorted(flags)}")
        multi = bot.has_multi_intent_hint(text)
        if multi != expected_multi:
            failures.append(f"{name}: multi expected {expected_multi}, got {multi}, flags={sorted(flags)}")
        if not expected_multi and bot.intent_hint_count(text) != 1:
            failures.append(f"{name}: single hint expected 1, got {bot.intent_hint_count(text)}, flags={sorted(flags)}")
    for text, expected_city in CITY_CASES:
        city = bot.extract_city({"default_city": "DEFAULT"}, text)
        if city != expected_city:
            failures.append(f"city: {text!r} expected {expected_city!r}, got {city!r}")


def parsed_action_types(parsed: dict) -> set[str]:
    actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else [parsed]
    return {action.get("type", "") for action in actions}


def assert_augment_cases(failures: list[str]) -> None:
    for name, text, parsed, expected_types in AUGMENT_CASES:
        augmented = bot.augment_parsed_actions(parsed, text)
        types = parsed_action_types(augmented)
        missing = expected_types - types
        if missing:
            failures.append(f"{name}: missing augmented types {sorted(missing)} from {sorted(types)}")

def retarget_data_paths(tmp_root: Path) -> None:
    bot.DATA_DIR = tmp_root / "records"
    bot.CHARTS_DIR = tmp_root / "charts"
    bot.PHOTO_DIR = tmp_root / "photos"
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
    bot.STATE_PATH = tmp_root / "state.json"


def data_csv(kind: str) -> Path:
    return {
        "expense": bot.EXPENSES_CSV,
        "income": bot.INCOME_CSV,
        "mood": bot.MOODS_CSV,
        "reminder": bot.REMINDERS_CSV,
        "note": bot.NOTES_CSV,
        "goal": bot.GOALS_CSV,
        "goal_log": bot.GOAL_LOGS_CSV,
    }[kind]


def row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def assert_multi_handle_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek
        original_weather_answer = bot.weather_answer

        def weak_model_response(*_args, **_kwargs):
            return {"type": "answer", "answer": "ok"}

        bot.call_deepseek = weak_model_response
        bot.weather_answer = lambda _config, _text: "weather ok"
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            for name, text, expected_deltas in MULTI_HANDLE_CASES:
                before = {kind: row_count(data_csv(kind)) for kind in expected_deltas}
                before_reminders = row_count(bot.REMINDERS_CSV) if "reminder" in expected_deltas else None
                try:
                    reply = bot.handle_text(config, text, chat_id=12345)
                except Exception as exc:
                    failures.append(f"{name}: raised {exc!r}")
                    continue
                if not reply:
                    failures.append(f"{name}: empty reply")
                for kind, expected_delta in expected_deltas.items():
                    if kind == "reminder":
                        after = row_count(bot.REMINDERS_CSV)
                        actual_delta = after - (before_reminders or 0)
                    else:
                        after = row_count(data_csv(kind))
                        actual_delta = after - before[kind]
                    if actual_delta != expected_delta:
                        failures.append(f"{name}: expected {expected_delta} new {kind} rows, got {actual_delta}")
        finally:
            bot.call_deepseek = original_call_deepseek
            bot.weather_answer = original_weather_answer

def assert_note_confirmation_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("note confirmation case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            notes_before = row_count(bot.NOTES_CSV)
            reply = bot.handle_text(config, U(r"\u4eca\u5929\u53bb\u4e86\u6d77\u8fb9"), chat_id=100)
            if not isinstance(reply, str) or "\u8bb0\u4e0b" not in reply or "\n\n\u8fd9\u53e5\u50cf\u751f\u6d3b\u8bb0\u5f55" not in reply or reply.startswith("\u8fd9\u53e5\u50cf\u751f\u6d3b\u8bb0\u5f55"):
                failures.append(f"pending note prompt: unexpected reply {reply!r}")
            if row_count(bot.NOTES_CSV) != notes_before:
                failures.append("pending note prompt: note was saved before confirmation")
            reply = bot.handle_text(config, U(r"\u8bb0\u4e0b"), chat_id=100)
            if not isinstance(reply, str) or not reply.startswith("\u5df2\u8bb0\u5f55\u751f\u6d3b\u4e8b\u9879"):
                failures.append(f"pending note confirm: unexpected reply {reply!r}")
            if row_count(bot.NOTES_CSV) != notes_before + 1:
                failures.append("pending note confirm: expected one saved note")

            notes_before = row_count(bot.NOTES_CSV)
            reply = bot.handle_text(config, U(r"\u4eca\u5929\u5f00\u59cb\u5b66\u4e60 python \u4e86\uff0c\u867d\u7136\u5f88\u5c11\u4f46\u80dc\u5728\u5f00\u59cb"), chat_id=103)
            if not isinstance(reply, str) or "\u5f00\u59cb\u672c\u8eab\u5c31\u5df2\u7ecf\u5728\u52a8\u4e86" not in reply or "\n\n\u8fd9\u53e5\u50cf\u751f\u6d3b\u8bb0\u5f55" not in reply:
                failures.append(f"pending note study prompt: unexpected reply {reply!r}")
            if row_count(bot.NOTES_CSV) != notes_before:
                failures.append("pending note study prompt: note was saved before confirmation")
            reply = bot.handle_text(config, U(r"\u4e0d\u7528"), chat_id=103)
            if reply != "\u597d\uff0c\u8fd9\u6761\u4e0d\u8bb0\u3002":
                failures.append(f"pending note study cancel: unexpected reply {reply!r}")

            notes_before = row_count(bot.NOTES_CSV)
            reply = bot.handle_text(config, U(r"\u6628\u5929\u53bb\u4e86\u56fe\u4e66\u9986"), chat_id=101)
            if not isinstance(reply, str) or "\u8bb0\u4e0b" not in reply or "\n\n\u8fd9\u53e5\u50cf\u751f\u6d3b\u8bb0\u5f55" not in reply or reply.startswith("\u8fd9\u53e5\u50cf\u751f\u6d3b\u8bb0\u5f55"):
                failures.append(f"pending note cancel prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, U(r"\u4e0d\u7528"), chat_id=101)
            if reply != "\u597d\uff0c\u8fd9\u6761\u4e0d\u8bb0\u3002":
                failures.append(f"pending note cancel: unexpected reply {reply!r}")
            if row_count(bot.NOTES_CSV) != notes_before:
                failures.append("pending note cancel: note should not be saved")

            if not bot.should_confirm_life_note(U(r"\u4eca\u5929\u51b3\u5b9a\u91cd\u65b0\u5f00\u59cb\u5b66\u82f1\u8bed"), chat_id=104):
                failures.append("pending note value score: high-value life event should ask confirmation")
            if bot.should_confirm_life_note(U(r"\u4f60\u89c9\u5f97\u6211\u4eca\u5929\u5f00\u59cb\u5b66python\u600e\u4e48\u6837"), chat_id=104):
                failures.append("pending note chat exclusion: question-like chat should not ask confirmation")
            state = bot.read_state()
            state.setdefault("note_confirmation_stats", {})["104"] = {"accepted": 0, "cancelled": 3}
            bot.write_state(state)
            if bot.should_confirm_life_note(U(r"\u4eca\u5929\u53bb\u4e86\u6d77\u8fb9"), chat_id=104):
                failures.append("pending note preference: quiet users should get fewer low-value confirmations")
        finally:
            bot.call_deepseek = original_call_deepseek


def assert_note_guard_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def mistaken_note(*_args, **_kwargs):
            return {"type": "note", "items": [{"date": "2026-01-01", "content": "should not save"}]}

        bot.call_deepseek = mistaken_note
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            before = row_count(bot.NOTES_CSV)
            reply = bot.handle_text(config, U(r"\u751f\u6d3b\u771f\u5947\u5999"), chat_id=102)
            if isinstance(reply, str) and reply.startswith("\u5df2\u8bb0\u5f55\u751f\u6d3b\u4e8b\u9879"):
                failures.append("note guard: unrequested note was saved")
            if row_count(bot.NOTES_CSV) != before:
                failures.append("note guard: notes.csv changed for casual chat")
            before = row_count(bot.NOTES_CSV)
            reply = bot.handle_text(config, U(r"\u8fd9\u4e2a\u529f\u80fd\u4e0d\u9519"), chat_id=102)
            if not isinstance(reply, str) or "\u751f\u6d3b\u8bb0\u5f55" in reply:
                failures.append(f"note guard: obvious chat should not prompt note confirmation {reply!r}")
            if row_count(bot.NOTES_CSV) != before:
                failures.append("note guard: obvious chat changed notes.csv")
        finally:
            bot.call_deepseek = original_call_deepseek

def assert_goal_tone_history_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("goal/history case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            before_goals = row_count(bot.GOALS_CSV)
            reply = bot.handle_text(config, U(r"\u6bcf\u5929\u5b66\u4e60python 15min"), chat_id=200)
            if not isinstance(reply, str) or "\u5df2\u8bbe\u7f6e\u76ee\u6807" not in reply:
                failures.append(f"goal set: unexpected reply {reply!r}")
            if row_count(bot.GOALS_CSV) != before_goals + 1:
                failures.append("goal set: expected one goal row")

            def weak_goal_mood(*_args, **_kwargs):
                return {"type": "mood", "items": [{"date": "2026-07-05", "mood": "\u4e0d\u9519", "score": 1, "reason": "", "note": ""}]}

            bot.call_deepseek = weak_goal_mood
            before_goals_multi = row_count(bot.GOALS_CSV)
            before_moods_multi = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, U(r"\u6bcf\u5929\u5b66\u4e60\u7b97\u6cd53\u9898\uff0c\u4eca\u5929\u5fc3\u60c5\u4e0d\u9519"), chat_id=200)
            if not isinstance(reply, str) or "\u5df2\u8bbe\u7f6e\u76ee\u6807" not in reply or "\u5df2\u8bb0\u5f55\u5fc3\u60c5" not in reply:
                failures.append(f"goal mood multi: unexpected reply {reply!r}")
            if row_count(bot.GOALS_CSV) != before_goals_multi + 1 or row_count(bot.MOODS_CSV) != before_moods_multi + 1:
                failures.append("goal mood multi: expected one goal and one mood row")
            bot.call_deepseek = fail_call_deepseek

            before_logs = row_count(bot.GOAL_LOGS_CSV)
            reply = bot.handle_text(config, U(r"\u6211\u5b66\u4e60python\u5b66\u4e8610min"), chat_id=200)
            if not isinstance(reply, str) or "10/15" not in reply:
                failures.append(f"goal progress: unexpected reply {reply!r}")
            if row_count(bot.GOAL_LOGS_CSV) != before_logs + 1:
                failures.append("goal progress: expected one goal log row")

            reply = bot.handle_text(config, U(r"\u4eca\u65e5\u76ee\u6807"), chat_id=200)
            if not isinstance(reply, str) or "10/15" not in reply:
                failures.append(f"goal status: unexpected reply {reply!r}")

            bot.append_csv(bot.EXPENSES_CSV, ["2026-07-05", "\u65e9\u9910", 20, "\u9910\u996e", "", "2026-07-05 08:00:00"])
            bot.append_csv(bot.EXPENSES_CSV, ["2026-07-05", "\u6e38\u620f", 30, "\u5a31\u4e50", "", "2026-07-05 09:00:00"])
            reply = bot.handle_text(config, U(r"\u6211\u6700\u8fd1\u94b1\u82b1\u54ea\u4e86"), chat_id=200)
            if not isinstance(reply, str) or "\u9910\u996e" not in reply or "\u5a31\u4e50" not in reply:
                failures.append(f"history spend: unexpected reply {reply!r}")

            reply = bot.handle_text(config, U(r"\u5207\u6362\u4e25\u683c\u6a21\u5f0f"), chat_id=200)
            if not isinstance(reply, str) or "\u4e25\u683c" not in reply:
                failures.append(f"tone set: unexpected reply {reply!r}")
            reply = bot.handle_text(config, U(r"\u9f13\u52b1\u6211\u4e00\u4e0b"), chat_id=200)
            if not isinstance(reply, str) or "\u4e0b\u4e00\u6b65" not in reply:
                failures.append(f"tone chat: unexpected reply {reply!r}")

            state = {"last_interaction_dates": {"200": "2026-06-01"}}
            reply = bot.append_failure_protection_notice(state, 200, "ok")
            if not isinstance(reply, str) or "\u6ca1\u8bb0\u5f55\u4e5f\u6ca1\u5173\u7cfb" not in reply:
                failures.append(f"failure protection: unexpected reply {reply!r}")
        finally:
            bot.call_deepseek = original_call_deepseek

def assert_important_item_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("important item case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "深圳"}
            before_dates = row_count(bot.DATES_CSV)
            before_reminders = row_count(bot.REMINDERS_CSV)
            reply = bot.handle_text(config, "7月12日妈妈生日，提前三天提醒我", chat_id=500)
            if not isinstance(reply, str) or "已记录重要事项" not in reply or "关联提醒" not in reply:
                failures.append(f"important birthday: unexpected reply {reply!r}")
            if row_count(bot.DATES_CSV) != before_dates + 1 or row_count(bot.REMINDERS_CSV) != before_reminders + 1:
                failures.append("important birthday: expected one date and one reminder row")
            reminders = bot.read_csv_rows(bot.REMINDERS_CSV)
            if not reminders or reminders[-1].get("repeat") != "yearly" or reminders[-1].get("text") != "妈妈生日":
                failures.append(f"important birthday: unexpected reminder row {reminders[-1] if reminders else None!r}")

            reply = bot.handle_text(config, "删除重要事项妈妈生日", chat_id=500)
            if not isinstance(reply, str) or "同时删除关联提醒" not in reply:
                failures.append(f"important delete linked reminder: unexpected reply {reply!r}")
            if row_count(bot.DATES_CSV) != before_dates or row_count(bot.REMINDERS_CSV) != before_reminders:
                failures.append("important delete linked reminder: date/reminder rows were not removed together")

            def weak_mood(*_args, **_kwargs):
                return {"type": "mood", "items": [{"date": "2026-07-05", "mood": "紧张", "score": -1, "reason": "考试", "note": ""}]}

            bot.call_deepseek = weak_mood
            before_dates = row_count(bot.DATES_CSV)
            before_reminders = row_count(bot.REMINDERS_CSV)
            before_moods = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, "明天下午三点考试，我很紧张", chat_id=501)
            if not isinstance(reply, str) or "已记录重要事项" not in reply or "关联提醒" not in reply or "已记录心情" not in reply:
                failures.append(f"important exam mood multi: unexpected reply {reply!r}")
            if row_count(bot.DATES_CSV) != before_dates + 1 or row_count(bot.REMINDERS_CSV) != before_reminders + 1 or row_count(bot.MOODS_CSV) != before_moods + 1:
                failures.append("important exam mood multi: expected date, reminder and mood rows")
            reminders = bot.read_csv_rows(bot.REMINDERS_CSV)
            if not reminders or reminders[-1].get("repeat") != "none" or "15:00:00" not in reminders[-1].get("remind_at", ""):
                failures.append(f"important exam mood multi: unexpected reminder row {reminders[-1] if reminders else None!r}")
        finally:
            bot.call_deepseek = original_call_deepseek

def assert_routine_confirmation_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("routine confirmation case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "深圳"}
            if bot.is_ambiguous_routine_intent("每天学习python 15min"):
                failures.append("routine explicit goal: quantity target should not ask confirmation")
            if bot.is_ambiguous_routine_intent("每天早上9点提醒我起床"):
                failures.append("routine explicit reminder: clock reminder should not ask confirmation")

            before_goals = row_count(bot.GOALS_CSV)
            before_reminders = row_count(bot.REMINDERS_CSV)
            reply = bot.handle_text(config, "提醒我每天学习python", chat_id=400)
            if not isinstance(reply, str) or "按两种方式处理" not in reply or "设为今日任务" not in reply or "设为重复提醒" not in reply:
                failures.append(f"routine ambiguous prompt: unexpected reply {reply!r}")
            if row_count(bot.GOALS_CSV) != before_goals or row_count(bot.REMINDERS_CSV) != before_reminders:
                failures.append("routine ambiguous prompt: should not save before user chooses")
            reply = bot.handle_text(config, "1", chat_id=400)
            if not isinstance(reply, str) or "已设为今日任务" not in reply:
                failures.append(f"routine choose task: unexpected reply {reply!r}")
            if row_count(bot.GOALS_CSV) != before_goals + 1:
                failures.append("routine choose task: expected one goal row")

            before_reminders = row_count(bot.REMINDERS_CSV)
            reply = bot.handle_text(config, "我每天学习英语", chat_id=401)
            if not isinstance(reply, str) or "按两种方式处理" not in reply:
                failures.append(f"routine second ambiguous prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, "提醒", chat_id=401)
            if not isinstance(reply, str) or "提醒已设好" not in reply:
                failures.append(f"routine choose reminder: unexpected reply {reply!r}")
            if row_count(bot.REMINDERS_CSV) != before_reminders + 1:
                failures.append("routine choose reminder: expected one reminder row")
            rows = bot.read_csv_rows(bot.REMINDERS_CSV)
            if not rows or rows[-1].get("repeat") != "daily" or "学习英语" not in rows[-1].get("text", ""):
                failures.append(f"routine choose reminder: unexpected reminder row {rows[-1] if rows else None!r}")

            reply = bot.handle_text(config, "每天阅读20min", chat_id=402)
            if not isinstance(reply, str) or "已设置目标" not in reply:
                failures.append(f"routine explicit quantity goal: unexpected reply {reply!r}")

            before_moods = row_count(bot.MOODS_CSV)
            before_goals = row_count(bot.GOALS_CSV)
            before_reminders = row_count(bot.REMINDERS_CSV)
            reply = bot.handle_text(config, "提醒我每天学习算法，今天心情不错", chat_id=403)
            if not isinstance(reply, str) or "按两种方式处理" not in reply or "已记录心情" not in reply:
                failures.append(f"routine ambiguous mood multi: unexpected reply {reply!r}")
            if row_count(bot.MOODS_CSV) != before_moods + 1:
                failures.append("routine ambiguous mood multi: expected one mood row")
            if row_count(bot.GOALS_CSV) != before_goals or row_count(bot.REMINDERS_CSV) != before_reminders:
                failures.append("routine ambiguous mood multi: should wait before saving task/reminder")
        finally:
            bot.call_deepseek = original_call_deepseek

def assert_unified_task_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek
        original_weather_answer = bot.weather_answer

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("unified task case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        bot.weather_answer = lambda _config, _text: "深圳现在：晴"
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": ""}
            created = bot.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bot.append_csv(bot.TODOS_CSV, ["todo-unified-1", "交作业", "pending", "", created, ""])
            reply = bot.handle_text(config, "每天学习python 15min", chat_id=300)
            if not isinstance(reply, str) or "已设置目标" not in reply:
                failures.append(f"unified task goal set: unexpected reply {reply!r}")

            morning = bot.daily_report_reply(config, "morning")
            if "今日任务：" not in morning or "待办：" in morning or "今日目标：" in morning:
                failures.append(f"unified morning report: duplicate sections still present {morning!r}")
            if "交作业" not in morning or "python" not in morning:
                failures.append(f"unified morning report: missing task rows {morning!r}")

            reply = bot.handle_text(config, "今日任务", chat_id=300)
            if not isinstance(reply, str) or "今日任务" not in reply or "交作业" not in reply or "python" not in reply:
                failures.append(f"unified task view: unexpected reply {reply!r}")
            if not isinstance(reply, str) or "1." not in reply or "2." not in reply:
                failures.append(f"unified task view: expected numbered task list {reply!r}")

            reply = bot.handle_text(config, "完成了", chat_id=300)
            if not isinstance(reply, str) or "你想标记哪一项完成" not in reply:
                failures.append(f"unified task ambiguous completion: unexpected reply {reply!r}")
            reply = bot.handle_text(config, "1", chat_id=300)
            if not isinstance(reply, str) or "已完成待办" not in reply:
                failures.append(f"unified task numbered completion: unexpected reply {reply!r}")

            before_logs = row_count(bot.GOAL_LOGS_CSV)
            reply = bot.handle_text(config, "完成python", chat_id=300)
            if not isinstance(reply, str) or "今日目标完成" not in reply:
                failures.append(f"unified task goal completion: unexpected reply {reply!r}")
            if row_count(bot.GOAL_LOGS_CSV) != before_logs + 1:
                failures.append("unified task goal completion: expected one goal log row")

            def weak_mood(*_args, **_kwargs):
                return {"type": "mood", "items": [{"date": "2026-07-05", "mood": "不错", "score": 1, "reason": "", "note": ""}]}

            bot.call_deepseek = weak_mood
            reply = bot.handle_text(config, "每天练算法3题", chat_id=300)
            if not isinstance(reply, str) or "已设置目标" not in reply:
                failures.append(f"unified task second goal set: unexpected reply {reply!r}")
            before_logs = row_count(bot.GOAL_LOGS_CSV)
            before_moods = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, "完成算法，今天心情不错", chat_id=300)
            if not isinstance(reply, str) or "今日目标完成" not in reply or "已记录心情" not in reply:
                failures.append(f"unified task completion mood multi: unexpected reply {reply!r}")
            if row_count(bot.GOAL_LOGS_CSV) != before_logs + 1 or row_count(bot.MOODS_CSV) != before_moods + 1:
                failures.append("unified task completion mood multi: expected goal log and mood rows")

            reply = bot.handle_text(config, "每天阅读20min", chat_id=300)
            if not isinstance(reply, str) or "已设置目标" not in reply:
                failures.append(f"unified task progress goal set: unexpected reply {reply!r}")
            before_logs = row_count(bot.GOAL_LOGS_CSV)
            before_moods = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, "我阅读学了5min，今天心情不错", chat_id=300)
            if not isinstance(reply, str) or "今日进度" not in reply or "已记录心情" not in reply:
                failures.append(f"unified task progress mood multi: unexpected reply {reply!r}")
            if row_count(bot.GOAL_LOGS_CSV) != before_logs + 1 or row_count(bot.MOODS_CSV) != before_moods + 1:
                failures.append("unified task progress mood multi: expected goal log and mood rows")
        finally:
            bot.call_deepseek = original_call_deepseek
            bot.weather_answer = original_weather_answer




def assert_bulk_task_completion_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("bulk task completion case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": ""}
            created = bot.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bot.append_csv(bot.TODOS_CSV, ["todo-bulk-1", U(r"\u4ea4\u4f5c\u4e1a"), "pending", "", created, ""])
            bot.append_csv(bot.TODOS_CSV, ["todo-bulk-2", U(r"\u80cc\u5355\u8bcd"), "pending", "", created, ""])

            reply = bot.handle_text(config, U(r"\u5b8c\u6210\u7b2c\u4e8c\u4e2a\u4ee3\u529e"), chat_id=930)
            rows = bot.read_csv_rows(bot.TODOS_CSV)
            second = next((row for row in rows if row.get("id") == "todo-bulk-2"), {})
            first = next((row for row in rows if row.get("id") == "todo-bulk-1"), {})
            if not isinstance(reply, str) or "\u5df2\u5b8c\u6210\u5f85\u529e" not in reply or second.get("status") != "done" or first.get("status") != "pending":
                failures.append(f"bulk task complete second todo: reply={reply!r}, rows={rows!r}")

            reply = bot.handle_text(config, U(r"\u628a\u7b2c\u4e00\u4e2a\u4efb\u52a1\u5b8c\u6210"), chat_id=930)
            rows = bot.read_csv_rows(bot.TODOS_CSV)
            first = next((row for row in rows if row.get("id") == "todo-bulk-1"), {})
            if not isinstance(reply, str) or "\u5df2\u5b8c\u6210\u5f85\u529e" not in reply or first.get("status") != "done":
                failures.append(f"bulk task complete first visible task: reply={reply!r}, rows={rows!r}")

            bot.append_csv(bot.TODOS_CSV, ["todo-bulk-3", U(r"\u6574\u7406\u684c\u9762"), "pending", "", created, ""])
            bot.append_csv(bot.TODOS_CSV, ["todo-bulk-4", U(r"\u590d\u4e60\u6570\u5b66"), "pending", "", created, ""])
            reply = bot.handle_text(config, U(r"\u5b8c\u6210\u5168\u90e8\u4ee3\u529e"), chat_id=930)
            rows = bot.read_csv_rows(bot.TODOS_CSV)
            pending = [row for row in rows if row.get("status") == "pending"]
            if not isinstance(reply, str) or "\u5df2\u5b8c\u6210\u5168\u90e8\u4eca\u65e5\u4efb\u52a1" not in reply or pending:
                failures.append(f"bulk task complete all: reply={reply!r}, pending={pending!r}")

            bot.append_csv(bot.TODOS_CSV, ["todo-bulk-5", U(r"\u6d17\u8863\u670d"), "pending", "", created, ""])
            bot.append_csv(bot.TODOS_CSV, ["todo-bulk-6", U(r"\u6253\u626b\u623f\u95f4"), "pending", "", created, ""])
            reply = bot.handle_text(config, U(r"\u90fd\u5b8c\u6210\u4e86"), chat_id=930)
            rows = bot.read_csv_rows(bot.TODOS_CSV)
            pending = [row for row in rows if row.get("status") == "pending"]
            if not isinstance(reply, str) or "\u5df2\u5b8c\u6210\u5168\u90e8\u4eca\u65e5\u4efb\u52a1" not in reply or pending:
                failures.append(f"bulk task complete all shorthand: reply={reply!r}, pending={pending!r}")
        finally:
            bot.call_deepseek = original_call_deepseek

def assert_support_layer_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek
        original_weather_answer = bot.weather_answer

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("support layer single case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        bot.weather_answer = lambda _config, _text: "weather ok"
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "深圳"}
            reply = bot.handle_text(config, "今晚会下雨吗，我怕下雨", chat_id=700)
            if not isinstance(reply, str) or "weather ok" not in reply or "天气这块先按保守方案准备" not in reply:
                failures.append(f"support layer weather concern: unexpected reply {reply!r}")

            def multi_weather_mood(*_args, **_kwargs):
                return {
                    "actions": [
                        {"type": "weather", "text": "明天天气如何"},
                        {"type": "mood", "items": [{"date": "2026-07-05", "mood": "烦", "score": -1, "reason": "明天天气如何，有点烦", "note": ""}]},
                    ]
                }

            bot.call_deepseek = multi_weather_mood
            before_moods = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, "明天天气如何，有点烦", chat_id=701)
            if not isinstance(reply, str) or "weather ok" not in reply or "已记录心情" not in reply:
                failures.append(f"support layer weather mood multi: unexpected reply {reply!r}")
            if "天气这块先按保守方案准备" in str(reply):
                failures.append("support layer weather mood multi: duplicated support layer after mood action")
            if row_count(bot.MOODS_CSV) != before_moods + 1:
                failures.append("support layer weather mood multi: expected one mood row")
        finally:
            bot.call_deepseek = original_call_deepseek
            bot.weather_answer = original_weather_answer

def assert_record_management_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("record management case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "深圳"}
            reply = bot.handle_text(config, "早餐25", chat_id=800)
            if not isinstance(reply, str) or "已记录消费" not in reply:
                failures.append(f"record mgmt create expense: unexpected reply {reply!r}")
            rows = bot.read_csv_rows(bot.EXPENSES_CSV)
            if not rows or not rows[-1].get("id"):
                failures.append("record mgmt create expense: expected generated id")

            reply = bot.handle_text(config, "/recent", chat_id=800)
            if not isinstance(reply, str) or "1. [消费]" not in reply or "删第2条" not in reply:
                failures.append(f"record mgmt recent numbering: unexpected reply {reply!r}")

            reply = bot.handle_text(config, "把第1条改成15元", chat_id=800)
            rows = bot.read_csv_rows(bot.EXPENSES_CSV)
            if not isinstance(reply, str) or "已修改" not in reply or not rows or rows[-1].get("amount") != "15":
                failures.append(f"record mgmt update numbered expense: reply={reply!r}, rows={rows!r}")

            reply = bot.handle_text(config, "删第1条", chat_id=800)
            if not isinstance(reply, str) or "已删除" not in reply or bot.read_csv_rows(bot.EXPENSES_CSV):
                failures.append(f"record mgmt delete numbered expense: reply={reply!r}, rows={bot.read_csv_rows(bot.EXPENSES_CSV)!r}")

            reply = bot.handle_text(config, "7月12日妈妈生日，提前三天提醒我", chat_id=801)
            if not isinstance(reply, str) or "已记录重要事项" not in reply or "关联提醒" not in reply:
                failures.append(f"record mgmt important setup: unexpected reply {reply!r}")
            reply = bot.handle_text(config, "把妈妈生日改成7月13日", chat_id=801)
            dates = bot.read_csv_rows(bot.DATES_CSV)
            reminders = bot.read_csv_rows(bot.REMINDERS_CSV)
            if not isinstance(reply, str) or "已修改" not in reply or "同步修改关联提醒" not in reply:
                failures.append(f"record mgmt update important date: unexpected reply {reply!r}")
            if not dates or not dates[-1].get("date", "").endswith("-07-13"):
                failures.append(f"record mgmt update important date: date not updated {dates!r}")
            if not reminders or not reminders[-1].get("remind_at", "").endswith("09:00:00") or "-07-10 " not in reminders[-1].get("remind_at", ""):
                failures.append(f"record mgmt update important date: linked reminder not updated {reminders!r}")

            bot.save_reminder({"type": "reminder", "items": [{"remind_at": "2099-01-01 09:00:00", "text": "起床", "repeat": "none"}]}, 802)
            reply = bot.handle_text(config, "/recent", chat_id=802)
            reminder_index = None
            if isinstance(reply, str):
                for line in reply.splitlines():
                    if "[提醒]" in line and "起床" in line:
                        reminder_index = line.split(".", 1)[0].strip()
                        break
            if not reminder_index:
                failures.append(f"record mgmt reminder recent: unexpected reply {reply!r}")
                reminder_index = "1"
            reply = bot.handle_text(config, f"把第{reminder_index}条改到明天十点", chat_id=802)
            reminders = bot.read_csv_rows(bot.REMINDERS_CSV)
            wake_row = next((row for row in reminders if row.get("text") == "起床"), {})
            if not isinstance(reply, str) or "已修改" not in reply or not wake_row.get("remind_at", "").endswith("10:00:00"):
                failures.append(f"record mgmt update numbered reminder: reply={reply!r}, reminders={reminders!r}")
        finally:
            bot.call_deepseek = original_call_deepseek


def assert_confirmation_center_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("confirmation center case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}

            before_notes = row_count(bot.NOTES_CSV)
            reply = bot.handle_text(config, U(r"\u4eca\u5929\u53bb\u4e86\u6d77\u8fb9"), chat_id=900)
            if not isinstance(reply, str) or "\u8fd9\u53e5\u50cf\u751f\u6d3b\u8bb0\u5f55" not in reply:
                failures.append(f"confirmation center note prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, "1", chat_id=900)
            if not isinstance(reply, str) or not reply.startswith("\u5df2\u8bb0\u5f55\u751f\u6d3b\u4e8b\u9879"):
                failures.append(f"confirmation center note numeric confirm: unexpected reply {reply!r}")
            if row_count(bot.NOTES_CSV) != before_notes + 1:
                failures.append("confirmation center note numeric confirm: expected one saved note")

            before_goals = row_count(bot.GOALS_CSV)
            reply = bot.handle_text(config, U(r"\u63d0\u9192\u6211\u6bcf\u5929\u5b66\u4e60\u82f1\u8bed"), chat_id=901)
            if not isinstance(reply, str) or "\u6309\u4e24\u79cd\u65b9\u5f0f\u5904\u7406" not in reply:
                failures.append(f"confirmation center routine prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, U(r"\u7b2c\u4e00\u4e2a"), chat_id=901)
            if not isinstance(reply, str) or "\u5df2\u8bbe\u4e3a\u4eca\u65e5\u4efb\u52a1" not in reply:
                failures.append(f"confirmation center routine chinese ordinal: unexpected reply {reply!r}")
            if row_count(bot.GOALS_CSV) != before_goals + 1:
                failures.append("confirmation center routine chinese ordinal: expected one goal row")

            before_reminders = row_count(bot.REMINDERS_CSV)
            reply = bot.handle_text(config, U(r"\u6211\u6bcf\u5929\u590d\u4e60\u6570\u636e\u7ed3\u6784"), chat_id=902)
            if not isinstance(reply, str) or "\u6309\u4e24\u79cd\u65b9\u5f0f\u5904\u7406" not in reply:
                failures.append(f"confirmation center routine second prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, U(r"\u7b2c\u4e8c\u4e2a"), chat_id=902)
            if not isinstance(reply, str) or "\u63d0\u9192\u5df2\u8bbe\u597d" not in reply:
                failures.append(f"confirmation center routine second ordinal: unexpected reply {reply!r}")
            if row_count(bot.REMINDERS_CSV) != before_reminders + 1:
                failures.append("confirmation center routine second ordinal: expected one reminder row")

            created = bot.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bot.append_csv(bot.TODOS_CSV, ["todo-center-1", U(r"\u4ea4\u4f5c\u4e1a"), "pending", "", created, ""])
            bot.append_csv(bot.TODOS_CSV, ["todo-center-2", U(r"\u80cc\u5355\u8bcd"), "pending", "", created, ""])
            reply = bot.handle_text(config, U(r"\u5b8c\u6210\u4e86"), chat_id=903)
            if not isinstance(reply, str) or "\u4f60\u60f3\u6807\u8bb0\u54ea\u4e00\u9879\u5b8c\u6210" not in reply:
                failures.append(f"confirmation center task prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, U(r"\u7b2c\u4e8c\u4e2a"), chat_id=903)
            todos = bot.read_csv_rows(bot.TODOS_CSV)
            second = next((row for row in todos if row.get("id") == "todo-center-2"), {})
            if not isinstance(reply, str) or "\u5df2\u5b8c\u6210\u5f85\u529e" not in reply or second.get("status") != "done":
                failures.append(f"confirmation center task second ordinal: reply={reply!r}, todos={todos!r}")

            created = "2026-07-05 08:00:00"
            bot.append_csv(bot.EXPENSES_CSV, ["2026-07-01", U(r"\u65e9\u9910"), "10", U(r"\u9910\u996e"), "", created, "expense-center-a"])
            bot.append_csv(bot.EXPENSES_CSV, ["2026-07-02", U(r"\u65e9\u9910"), "20", U(r"\u9910\u996e"), "", created, "expense-center-b"])
            reply = bot.handle_text(config, U(r"\u5220\u9664\u65e9\u9910"), chat_id=904)
            if not isinstance(reply, str) or "\u6211\u627e\u5230\u51e0\u6761\u53ef\u80fd\u8981\u5220\u9664\u7684\u8bb0\u5f55" not in reply:
                failures.append(f"confirmation center ambiguous delete prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, U(r"\u7b2c\u4e8c\u4e2a"), chat_id=904)
            rows = bot.read_csv_rows(bot.EXPENSES_CSV)
            if not isinstance(reply, str) or "\u5df2\u5220\u9664" not in reply or any(row.get("id") == "expense-center-b" for row in rows):
                failures.append(f"confirmation center ambiguous delete choice: reply={reply!r}, rows={rows!r}")

            bot.append_csv(bot.EXPENSES_CSV, ["2026-07-03", U(r"\u5348\u996d"), "12", U(r"\u9910\u996e"), "", created, "expense-center-c"])
            bot.append_csv(bot.EXPENSES_CSV, ["2026-07-04", U(r"\u5348\u996d"), "18", U(r"\u9910\u996e"), "", created, "expense-center-d"])
            reply = bot.handle_text(config, U(r"\u628a\u5348\u996d\u6539\u621015\u5143"), chat_id=905)
            if not isinstance(reply, str) or "\u6211\u627e\u5230\u51e0\u6761\u53ef\u80fd\u8981\u4fee\u6539\u7684\u8bb0\u5f55" not in reply:
                failures.append(f"confirmation center ambiguous update prompt: unexpected reply {reply!r}")
            reply = bot.handle_text(config, "1", chat_id=905)
            rows = bot.read_csv_rows(bot.EXPENSES_CSV)
            changed = next((row for row in rows if row.get("id") == "expense-center-c"), {})
            if not isinstance(reply, str) or "\u5df2\u4fee\u6539" not in reply or changed.get("amount") != "15":
                failures.append(f"confirmation center ambiguous update choice: reply={reply!r}, rows={rows!r}")
        finally:
            bot.call_deepseek = original_call_deepseek






def assert_weather_mood_boundary_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek
        original_weather_answer = bot.weather_answer

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("weather mood boundary case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        bot.weather_answer = lambda _config, _text: "weather ok"
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            before_moods = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, U(r"\u4eca\u5929\u5929\u6c14\u4e0d\u9519"), chat_id=920)
            if not isinstance(reply, str) or "weather ok" not in reply:
                failures.append(f"weather mood boundary: expected weather reply {reply!r}")
            if "\u5df2\u8bb0\u5f55\u5fc3\u60c5" in str(reply) or row_count(bot.MOODS_CSV) != before_moods:
                failures.append(f"weather mood boundary: weather description should not create mood reply={reply!r}")

            before_moods = row_count(bot.MOODS_CSV)
            reply = bot.handle_text(config, U(r"\u4eca\u5929\u5929\u6c14\u4e0d\u9519\uff0c\u6211\u5fc3\u60c5\u4e5f\u4e0d\u9519"), chat_id=921)
            if not isinstance(reply, str) or "weather ok" not in reply or "\u5df2\u8bb0\u5f55\u5fc3\u60c5" not in reply:
                failures.append(f"weather mood boundary: explicit self mood should still be recorded {reply!r}")
            if row_count(bot.MOODS_CSV) != before_moods + 1:
                failures.append("weather mood boundary: expected one mood row for explicit self mood")
        finally:
            bot.call_deepseek = original_call_deepseek
            bot.weather_answer = original_weather_answer

def assert_answer_filter_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek
        original_weather_answer = bot.weather_answer

        def generic_answer(*_args, **_kwargs):
            return {"type": "answer", "answer": "model ok"}

        bot.call_deepseek = generic_answer
        bot.weather_answer = lambda _config, _text: "weather ok"
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            reply = bot.handle_text(config, U(r"\u4eca\u5929\u65e9\u991025\uff0c\u5fc3\u60c5\u4e0d\u9519\uff0c\u5e2e\u6211\u603b\u7ed3\u4e0b\u4eca\u5929"), chat_id=910)
            if "model ok" in str(reply):
                failures.append(f"answer filter: low-value answer leaked into multi-action reply {reply!r}")
            if not isinstance(reply, str) or "\u5df2\u8bb0\u5f55\u6d88\u8d39" not in reply or "\u5df2\u8bb0\u5f55\u5fc3\u60c5" not in reply or "\u4eca\u65e5\u603b\u7ed3" not in reply:
                failures.append(f"answer filter: expected expense, mood and summary reply {reply!r}")
        finally:
            bot.call_deepseek = original_call_deepseek
            bot.weather_answer = original_weather_answer

def assert_local_handle_cases(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        retarget_data_paths(Path(tmp))
        bot.ensure_files()
        original_call_deepseek = bot.call_deepseek

        def fail_call_deepseek(*_args, **_kwargs):
            raise AssertionError("local case unexpectedly called DeepSeek")

        bot.call_deepseek = fail_call_deepseek
        try:
            config = {"deepseek_api_key": "", "deepseek_model": "", "default_city": "\u6df1\u5733"}
            for name, text, expected_prefix, csv_kind in LOCAL_HANDLE_CASES:
                csv_path = data_csv(csv_kind)
                before = row_count(csv_path)
                try:
                    reply = bot.handle_text(config, text, chat_id=12345)
                except Exception as exc:
                    failures.append(f"{name}: raised {exc!r}")
                    continue
                if not isinstance(reply, str) or not reply.startswith(expected_prefix):
                    failures.append(f"{name}: unexpected reply {reply!r}")
                after = row_count(csv_path)
                if after != before + 1:
                    failures.append(f"{name}: expected one new row in {csv_path.name}, got {after - before}")
        finally:
            bot.call_deepseek = original_call_deepseek


def main() -> None:
    failures: list[str] = []
    assert_route_cases(failures)
    assert_augment_cases(failures)
    assert_local_handle_cases(failures)
    assert_note_confirmation_cases(failures)
    assert_note_guard_cases(failures)
    assert_goal_tone_history_cases(failures)
    assert_important_item_cases(failures)
    assert_routine_confirmation_cases(failures)
    assert_unified_task_cases(failures)
    assert_bulk_task_completion_cases(failures)
    assert_support_layer_cases(failures)
    assert_record_management_cases(failures)
    assert_confirmation_center_cases(failures)
    assert_weather_mood_boundary_cases(failures)
    assert_answer_filter_cases(failures)
    assert_multi_handle_cases(failures)
    if failures:
        print("FAILED")
        for failure in failures:
            print("- " + failure)
        raise SystemExit(1)
    print(f"OK: {len(CASES)} route cases, {len(CITY_CASES)} city cases, {len(AUGMENT_CASES)} augment cases, {len(LOCAL_HANDLE_CASES)} local handle cases, note confirmation, note guard, goal/tone/history, important items, routine confirmation, unified tasks, bulk task completion, support layer, record management, confirmation center, weather/mood boundary, answer filter, {len(MULTI_HANDLE_CASES)} multi handle cases")


if __name__ == "__main__":
    main()

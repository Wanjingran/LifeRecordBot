from __future__ import annotations

import csv
import ctypes
import json
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error, request
from urllib.parse import quote, urlencode


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "records"
CHARTS_DIR = ROOT / "charts"
PHOTO_DIR = ROOT / "photos"
EXPENSES_CSV = DATA_DIR / "expenses.csv"
INCOME_CSV = DATA_DIR / "income.csv"
DATES_CSV = DATA_DIR / "dates.csv"
NOTES_CSV = DATA_DIR / "notes.csv"
MOODS_CSV = DATA_DIR / "moods.csv"
REMINDERS_CSV = DATA_DIR / "reminders.csv"
BUDGETS_CSV = DATA_DIR / "budgets.csv"
TODOS_CSV = DATA_DIR / "todos.csv"
GOALS_CSV = DATA_DIR / "goals.csv"
GOAL_LOGS_CSV = DATA_DIR / "goal_logs.csv"
RAW_JSONL = DATA_DIR / "raw_messages.jsonl"
STATE_PATH = ROOT / "state.json"
DELETE_WORDS = ("\u5220", "\u5220\u9664", "\u64a4\u9500", "\u53d6\u6d88", "\u53bb\u6389", "\u79fb\u9664")
MUTEX_NAME = "Global\\LifeRecordBotSingleInstance"
WEATHER_WORDS = (
    "天气", "下雨", "有雨", "暴雨", "小雨", "中雨", "大雨", "阵雨", "温度", "气温", "几度", "降水", "刮风", "大风",
    "带伞", "要不要带伞", "冷不冷", "热不热", "冷吗", "热吗", "穿什么", "空气质量", "湿度",
)
MOOD_WORDS = (
    "心情", "情绪", "状态", "感觉", "难受", "焦虑", "压力", "烦", "烦躁", "郁闷",
    "累", "疲惫", "困", "开心", "高兴", "快乐", "满足", "舒服", "轻松", "还行", "不错",
    "崩溃", "沮丧", "失落", "孤独", "不好", "委屈", "emo", "破防", "摆烂", "无聊",
    "紧张", "担心", "害怕", "慌", "心慌", "不安", "迷茫", "没动力", "有动力",
)
NEGATIVE_MOOD_WORDS = (
    "难受", "焦虑", "压力", "烦", "烦躁", "郁闷", "累", "疲惫", "困", "崩溃",
    "沮丧", "失落", "孤独", "不好", "委屈", "emo", "破防", "摆烂", "无聊",
    "紧张", "担心", "害怕", "慌", "心慌", "不安", "迷茫", "没动力",
)
POSITIVE_MOOD_WORDS = ("开心", "高兴", "快乐", "轻松", "舒服", "不错", "还行", "满足", "有动力", "顺利", "好多了")
CHAT_WORDS = (
    "你好", "在吗", "早安", "晚安", "陪我", "聊聊", "说句话", "鼓励", "支持", "夸夸", "安慰",
    "给我打气", "我该怎么办", "怎么办", "给点建议", "建议一下", "没事干", "不知道干嘛",
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("Missing config.json. Copy config.example.json to config.json, then fill in your keys.")
        sys.exit(1)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    required = ("telegram_bot_token", "deepseek_api_key")
    for key in required:
        value = str(config.get(key, "")).strip()
        if not value or value.startswith("PASTE_"):
            print(f"Please fill {key} in config.json.")
            sys.exit(1)
        config[key] = value
    config["deepseek_model"] = str(config.get("deepseek_model") or "deepseek-v4-flash").strip()
    config["default_city"] = str(config.get("default_city") or "").strip()
    config["allowed_user_ids"] = config.get("allowed_user_ids") or []
    config["daily_reports_enabled"] = bool(config.get("daily_reports_enabled", True))
    config["daily_report_chat_ids"] = config.get("daily_report_chat_ids") or []
    config["morning_report_time"] = str(config.get("morning_report_time") or "08:00").strip()
    config["evening_report_time"] = str(config.get("evening_report_time") or "22:30").strip()
    config["tesseract_cmd"] = str(config.get("tesseract_cmd") or "").strip()
    config["ocr_lang"] = str(config.get("ocr_lang") or "chi_sim+eng").strip()
    return config


def ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    ensure_csv(EXPENSES_CSV, ["date", "item", "amount", "category", "note", "created_at", "id"])
    ensure_csv(INCOME_CSV, ["date", "source", "amount", "category", "note", "created_at", "id"])
    ensure_csv(DATES_CSV, ["date", "title", "remind_days", "note", "created_at", "id"])
    ensure_csv(NOTES_CSV, ["date", "content", "created_at", "id"])
    ensure_csv(MOODS_CSV, ["date", "mood", "score", "reason", "note", "created_at", "id"])
    ensure_csv(REMINDERS_CSV, ["id", "chat_id", "remind_at", "text", "status", "created_at", "sent_at", "repeat"])
    ensure_csv(BUDGETS_CSV, ["period", "category", "amount", "created_at", "id"])
    ensure_csv(TODOS_CSV, ["id", "text", "status", "due_date", "created_at", "done_at"])
    ensure_csv(GOALS_CSV, ["id", "chat_id", "title", "subject", "target_amount", "unit", "period", "reminder_time", "status", "created_at"])
    ensure_csv(GOAL_LOGS_CSV, ["goal_id", "date", "amount", "unit", "note", "created_at"])
    for path, header in managed_record_headers().items():
        ensure_csv_columns(path, header)
        ensure_row_ids(path, header)
    ensure_csv_columns(GOAL_LOGS_CSV, ["goal_id", "date", "amount", "unit", "note", "created_at"])
    if not STATE_PATH.exists():
        STATE_PATH.write_text(json.dumps({"offset": 0}, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_csv(path: Path, header: list[str]) -> None:
    if not path.exists():
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(header)


def ensure_csv_columns(path: Path, header: list[str]) -> None:
    if not path.exists():
        ensure_csv(path, header)
        return
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        old_header = reader.fieldnames or []
        rows = list(reader)
    missing = [name for name in header if name not in old_header]
    if not missing:
        return
    merged_header = old_header + missing
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=merged_header)
        writer.writeheader()
        for row in rows:
            for name in missing:
                row.setdefault(name, "")
            writer.writerow(row)


def managed_record_headers() -> dict[Path, list[str]]:
    return {
        EXPENSES_CSV: ["date", "item", "amount", "category", "note", "created_at", "id"],
        INCOME_CSV: ["date", "source", "amount", "category", "note", "created_at", "id"],
        DATES_CSV: ["date", "title", "remind_days", "note", "created_at", "id"],
        NOTES_CSV: ["date", "content", "created_at", "id"],
        MOODS_CSV: ["date", "mood", "score", "reason", "note", "created_at", "id"],
        REMINDERS_CSV: ["id", "chat_id", "remind_at", "text", "status", "created_at", "sent_at", "repeat"],
        BUDGETS_CSV: ["period", "category", "amount", "created_at", "id"],
        TODOS_CSV: ["id", "text", "status", "due_date", "created_at", "done_at"],
        GOALS_CSV: ["id", "chat_id", "title", "subject", "target_amount", "unit", "period", "reminder_time", "status", "created_at"],
    }


def ensure_row_ids(path: Path, fallback_header: list[str]) -> None:
    if not path.exists():
        ensure_csv(path, fallback_header)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or fallback_header)
        rows = list(reader)
    if "id" not in fieldnames:
        fieldnames.append("id")
    changed = False
    for row in rows:
        if not row.get("id"):
            row["id"] = uuid.uuid4().hex
            changed = True
    if changed:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

def append_csv(path: Path, row: list) -> None:
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerow(row)


def http_json(url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 60) -> dict:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url, data=body, headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tg_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def send_message(token: str, chat_id: int, text: str) -> None:
    http_json(tg_url(token, "sendMessage"), {"chat_id": chat_id, "text": text[:3900]})


def http_multipart(url: str, fields: dict, files: dict, timeout: int = 60) -> dict:
    boundary = "----LifeRecordBot" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for name, path in files.items():
        path = Path(path)
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: image/png\r\n\r\n")
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = request.Request(url, data=bytes(body), headers=headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_photo(token: str, chat_id: int, photo_path: Path | str, caption: str = "") -> None:
    http_multipart(
        tg_url(token, "sendPhoto"),
        {"chat_id": chat_id, "caption": caption[:1000]},
        {"photo": Path(photo_path)},
    )


def telegram_file_url(token: str, file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


def download_telegram_file(token: str, file_id: str, prefix: str = "photo") -> Path:
    info = http_json(tg_url(token, "getFile"), {"file_id": file_id}, timeout=30)
    file_path = info.get("result", {}).get("file_path", "")
    if not file_path:
        raise ValueError("Telegram 没有返回文件路径。")
    suffix = Path(file_path).suffix or ".jpg"
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    target = PHOTO_DIR / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
    req = request.Request(telegram_file_url(token, file_path))
    with request.urlopen(req, timeout=60) as resp:
        target.write_bytes(resp.read())
    return target


def image_file_id_from_message(message: dict) -> str:
    photos = message.get("photo") or []
    if photos:
        best = sorted(photos, key=lambda item: item.get("file_size", 0))[-1]
        return best.get("file_id", "")
    document = message.get("document") or {}
    mime = str(document.get("mime_type") or "")
    if mime.startswith("image/"):
        return document.get("file_id", "")
    return ""


def tesseract_executable(config: dict) -> str:
    configured = str(config.get("tesseract_cmd") or "").strip()
    if configured:
        return configured
    return shutil.which("tesseract") or ""


def ocr_image_text(config: dict, image_path: Path) -> str:
    exe = tesseract_executable(config)
    if not exe:
        return ""
    try:
        result = subprocess.run(
            [exe, str(image_path), "stdout", "-l", config.get("ocr_lang") or "chi_sim+eng"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=40,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return re.sub(r"\s+", " ", result.stdout).strip()


def handle_photo_message(config: dict, token: str, message: dict, chat_id: int) -> str | dict:
    file_id = image_file_id_from_message(message)
    caption = str(message.get("caption") or "").strip()
    if not file_id:
        return "我收到消息了，但里面没有可识别的图片。"
    try:
        image_path = download_telegram_file(token, file_id)
    except Exception as exc:
        return f"图片下载失败：{exc}"
    ocr_text = ocr_image_text(config, image_path)
    if not ocr_text:
        if caption:
            return handle_text(config, caption, "", chat_id)
        return "图片收到了，但这台电脑还没装 OCR，所以暂时读不出小票文字。安装 Tesseract 后，在 config.json 里设置 tesseract_cmd，就可以继续用拍照记账。"
    prompt = "这是一张账单、小票或支付截图的 OCR 文本。请优先识别实际消费或收入；如果金额不确定，直接回答需要我确认，不要硬记。"
    if caption:
        prompt += f"\n用户说明：{caption}"
    prompt += f"\nOCR内容：{ocr_text}"
    return handle_text(config, prompt, "", chat_id)


def call_deepseek(config: dict, text: str) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system = f"""
You are an intent router and parser for a warm, practical personal life assistant bot.
Current local time: {now}.
Return only valid JSON. No markdown. No explanation.

Classify the user's Chinese message into one or more actions. Prefer the actions array when the message contains multiple intents. For backward compatibility, a single action may also be returned as one of these shapes:

Expense:
{{"type":"expense","items":[{{"date":"YYYY-MM-DD","name":"item","amount":12.3,"category":"餐饮|交通|购物|居住|娱乐|医疗|学习|其他","note":""}}]}}

Income:
{{"type":"income","items":[{{"date":"YYYY-MM-DD","source":"income source","amount":12.3,"category":"兼职|工资|红包|报销|其他","note":""}}]}}

Important date:
{{"type":"date","items":[{{"date":"YYYY-MM-DD","title":"event title","remind_days":0,"note":""}}]}}

Life note:
{{"type":"note","items":[{{"date":"YYYY-MM-DD","content":"note content"}}]}}

Mood:
{{"type":"mood","items":[{{"date":"YYYY-MM-DD","mood":"short mood label","score":-2 to 2,"reason":"main reason or empty","note":"original feeling summary"}}]}}

Reminder:
{{"type":"reminder","items":[{{"remind_at":"YYYY-MM-DD HH:MM:SS","text":"thing to remind the user","repeat":"none|daily|weekly|monthly"}}]}}

Todo:
{{"type":"todo","items":[{{"text":"task text","due_date":"YYYY-MM-DD or empty"}}]}}

Budget:
{{"type":"budget","items":[{{"period":"month|week","category":"总额|餐饮|交通|购物|居住|娱乐|医疗|学习|其他","amount":800}}]}}

Study plan:
{{"type":"study_plan","goal":"learning goal","deadline":"YYYY-MM-DD or empty","days":7}}

Weather:
{{"type":"weather","text":"original weather question"}}

Chart:
{{"type":"chart","period":"month|year"}}

Summary:
{{"type":"summary","period":"today|week|month|year"}}

Mood trend:
{{"type":"mood_trend","period":"week|month|year"}}

View/list/status:
{{"type":"view","name":"recent|reminders|todo|budget|dates","period":"today|week|month|year"}}

General answer:
{{"type":"answer","answer":"direct answer in Chinese"}}

Delete existing record:
{{"type":"delete","target":"expense|income|date|note|mood|reminder|todo|budget|any","date":"YYYY-MM-DD or empty","query":"keywords from the record to delete","amount":12.3 or null}}

Multiple actions:
{{"actions":[{{"type":"reminder","items":[{{"remind_at":"YYYY-MM-DD HH:MM:SS","text":"thing to remind the user","repeat":"none|daily|weekly|monthly"}}]}},{{"type":"mood","items":[{{"date":"YYYY-MM-DD","mood":"short mood label","score":-2,"reason":"main reason","note":"original feeling summary"}}]}}]}}

Rules:
- If one message contains multiple intents, return {{"actions":[...]}} and include every useful action.
- Example: "我今天下午三点要考试，我很紧张" should create both a reminder/action for the exam time and a mood action for anxiety.
- Example: "今天兼职赚了200，晚上打车花了30" should create both income and expense actions.
- Example: "7月12日妈妈生日，提前三天提醒我买礼物" should create both an important date action and a reminder action.
- Example: "早餐25，工资到账3000，下午三点考试，我很紧张，顺便看本月收支图" should create expense, income, reminder, mood, and chart actions.
- A single user message may contain 3 or more useful actions. Never stop after the first one or two actions.
- Split multiple expenses in one message into multiple items.
- If the user records received money, salary, part-time pay, transfer income, red packet, reimbursement, or allowance, use type income.
- Convert relative dates such as 今天, 昨天, 明天 using current local time.
- If no date is provided for an expense or note, use today's date.
- Do not invent an amount. If there is no numeric cost, use note instead of expense.
- If the user describes their emotional state, stress, tiredness, anxiety, happiness, motivation, boredom, or mental condition, use type mood.
- If the user asks you to remind, call, wake, notify, or alert them at a future time, use type reminder.
- If the user mentions a future scheduled event with a concrete time, such as an exam/interview/meeting/class, create a reminder even if the word 提醒 is omitted.
- If the user adds a todo, task, checklist item, or says 添加待办/待办, use type todo.
- If the user sets a budget or limit such as 预算/限额, use type budget.
- If the user asks about weather together with other intents, include a weather action with the weather question text.
- If the user asks for 收支图, 开销图, 消费图, 账单图, income/expense chart, or a visual chart, include a chart action. Use period year for 今年/年度/全年, otherwise month.
- If the user asks for 今日/本周/本月/今年总结 together with other intents, include a summary action.
- If the user asks for 心情趋势, 情绪趋势, 心理趋势, 状态趋势, or mood trend, include a mood_trend action.
- If the user asks to make, split, arrange, or 拆解 a 学习计划/复习计划/备考计划, include a study_plan action. Parse 三天/七天/一周 into days when possible.
- If the user asks to view 最近记录, 提醒列表, 待办列表, 预算情况, or 重要日期 together with other intents, include a view action.
- If the user asks for encouragement, comfort, casual chat, praise, advice, or says 陪我聊聊/鼓励我/夸夸我/安慰我, include an answer action, even when another record action is also present.
- For 查看/看看/有哪些/列表/清单/还剩多少/进度 questions, prefer view/summary/chart instead of answer.
- Only use note when the user explicitly asks to record/log a life note, such as 记一下/记录一下/生活日志/把这件事记下来. Do not use note for ordinary chat, feedback, questions, or casual statements.
- For recurring reminders like 每天, 每周, 每月, set repeat to daily, weekly, or monthly. Otherwise set repeat to none.
- For reminder, convert relative time such as 明天早上八点, 今晚九点, 下午三点, 半小时后 using current local time. Chinese numerals like 三点 mean 3:00; 下午三点 means 15:00.
- Mood score: -2 very negative, -1 negative, 0 neutral/mixed, 1 positive, 2 very positive.
- Important item reminder like 提前三天提醒 means remind_days is 3. The app automatically creates a reminder for date actions, so do not create a duplicate reminder for the same birthday/exam/deadline. Only create a separate reminder if the user asks for an extra distinct action, such as buying a gift.
- Use category 其他 when unsure.
- If the user asks a question, asks for advice, gives feedback, asks what something means, or asks you to perform reasoning, use type answer instead of note.
- If the message is merely a casual statement and the user did not explicitly ask to record it, use type answer instead of note.
- If the user wants to delete, remove, cancel, or undo an existing log, use type delete.
- For type delete, target should be expense, income, date, note, mood, reminder, todo, budget, or any when unclear.
- For type delete, query should contain the item/event/note keywords to match. If the user says 删除刚才那条/撤销上一条, leave query empty.
- For type answer, answer like a concise daily companion: practical, warm, specific, and not preachy. Use 1-3 short sentences.
- When the user sounds tired, anxious, or low, first acknowledge the feeling briefly, then suggest one small next action.
- When the user shares a positive mood, celebrate it lightly and help them notice what made it work.
- Do not pretend to be a doctor, lawyer, or financial advisor. For high-risk issues, suggest seeking professional help.
""".strip()
    payload = {
        "model": config["deepseek_model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    result = http_json(
        "https://api.deepseek.com/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {config['deepseek_api_key']}"},
        timeout=90,
    )
    content = result["choices"][0]["message"]["content"]
    return parse_json_content(content)


VALID_ACTION_TYPES = {"expense", "income", "date", "note", "mood", "reminder", "todo", "budget", "study_plan", "mood_trend", "weather", "chart", "summary", "view", "answer", "delete"}


def validate_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise ValueError("DeepSeek returned an invalid action.")
    if action.get("type") not in VALID_ACTION_TYPES:
        raise ValueError("DeepSeek returned an unknown type.")
    if action.get("type") == "answer":
        if not isinstance(action.get("answer"), str):
            raise ValueError("DeepSeek returned an invalid answer.")
        return action
    if action.get("type") == "delete":
        return action
    if action.get("type") == "weather":
        if not isinstance(action.get("text"), str):
            raise ValueError("DeepSeek returned an invalid weather action.")
        return action
    if action.get("type") in {"chart", "summary", "view", "study_plan", "mood_trend"}:
        return action
    if not isinstance(action.get("items"), list):
        raise ValueError("DeepSeek returned invalid items.")
    return action


def parse_json_content(content: str) -> dict:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if fenced:
        content = fenced.group(1).strip()
    parsed = json.loads(content)
    if isinstance(parsed.get("actions"), list):
        actions = [validate_action(action) for action in parsed["actions"]]
        if not actions:
            raise ValueError("DeepSeek returned empty actions.")
        return {"actions": actions}
    return validate_action(parsed)




def normalize_expense_category(name: str, category: str) -> str:
    category = (category or "其他").strip()
    aliases = {
        "娛樂": "娱乐", "娛楽": "娱乐", "餐飲": "餐饮", "交通費": "交通",
        "購物": "购物", "醫療": "医疗", "學習": "学习", "饮食": "餐饮",
        "吃饭": "餐饮", "吃飯": "餐饮", "食品": "餐饮", "饭钱": "餐饮",
    }
    category = aliases.get(category, category)
    valid = {"餐饮", "交通", "购物", "居住", "娱乐", "医疗", "学习", "其他"}
    text = name or ""
    compact = re.sub(r"\s+", "", text)
    rules = [
        ("餐饮", ("早餐", "早饭", "早点", "午饭", "午餐", "中饭", "晚饭", "晚餐", "夜宵", "宵夜", "外卖", "奶茶", "咖啡", "冰淇淋", "冰淇凌", "冰激凌", "雪糕", "甜品", "喝水", "买水", "水", "饮品", "饮料", "可乐", "矿泉水", "纯净水", "瓶装水", "汉堡", "炸鸡", "烧烤", "火锅", "麻辣烫", "包子", "饺子", "水果", "食堂", "餐厅", "饭店", "饭", "餐", "面", "粉", "粥")),
        ("交通", ("打车", "出租", "网约车", "滴滴", "坐地铁", "地铁", "坐公交", "公交", "公交车", "巴士", "大巴", "高铁", "火车", "机票", "车票", "停车", "过路费", "油费", "共享单车", "骑行")),
        ("娱乐", ("qq音乐", "QQ音乐", "音乐", "网吧", "网咖", "游戏", "会员", "电影", "续费", "演唱会", "剧本杀", "KTV", "ktv")),
        ("购物", ("淘宝", "京东", "拼多多", "超市", "买", "衣服", "鞋", "雨伞", "伞", "日用品", "快递", "礼物")),
        ("居住", ("房租", "水电", "物业", "宽带", "燃气", "电费", "水费")),
        ("医疗", ("医院", "药", "挂号", "体检", "牙", "诊所")),
        ("学习", ("书", "课程", "培训", "考试", "教材", "资料", "学费")),
    ]
    inferred = "其他"
    for normalized, keywords in rules:
        for keyword in keywords:
            if keyword == "水":
                if compact == "水":
                    inferred = normalized
                    break
            elif keyword in text:
                inferred = normalized
                break
        if inferred != "其他":
            break
    if category in valid and category != "其他":
        return category
    if inferred != "其他":
        return inferred
    if category in valid:
        return category
    return "其他"

def normalize_income_category(source: str, category: str) -> str:
    category = (category or "其他").strip()
    aliases = {"兼職": "兼职", "工資": "工资", "紅包": "红包", "報銷": "报销"}
    category = aliases.get(category, category)
    valid = {"兼职", "工资", "红包", "报销", "其他"}
    if category in valid:
        return category
    text = source or ""
    if "兼职" in text:
        return "兼职"
    if "工资" in text:
        return "工资"
    if "红包" in text:
        return "红包"
    if "报销" in text:
        return "报销"
    return "其他"

def save_parsed(parsed: dict) -> str:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kind = parsed["type"]
    if kind == "answer":
        return parsed["answer"]
    if kind == "delete":
        return delete_record(parsed)

    items = parsed["items"]
    if kind == "expense":
        lines = []
        total = 0.0
        history_rows = read_csv_rows(EXPENSES_CSV)
        anomaly_lines = []
        for item in items:
            amount = safe_amount(item.get("amount"))
            total += amount
            name = item.get("name", "")
            category = normalize_expense_category(name, item.get("category", "其他"))
            anomaly_lines.extend(expense_anomaly_for_item(item.get("date", ""), name, amount, category, history_rows))
            append_csv(EXPENSES_CSV, [
                item.get("date", ""), name, amount,
                category, item.get("note", ""), created_at, uuid.uuid4().hex,
            ])
            history_rows.append({"date": item.get("date", ""), "item": name, "amount": str(amount), "category": category, "note": item.get("note", ""), "created_at": created_at})
            lines.append(f"- {item.get('date', '')} {name} {amount:g} 元 [{category}]")
        anomaly = expense_anomaly_notice(anomaly_lines)
        return "已记录消费：\n" + "\n".join(lines) + f"\n本次合计：{total:g} 元\n{encouragement('expense')}" + anomaly + budget_warning_for_expense()

    if kind == "income":
        lines = []
        total = 0.0
        for item in items:
            amount = safe_amount(item.get("amount"))
            total += amount
            source = item.get("source", "")
            category = normalize_income_category(source, item.get("category", "其他"))
            append_csv(INCOME_CSV, [
                item.get("date", ""), source, amount,
                category, item.get("note", ""), created_at, uuid.uuid4().hex,
            ])
            lines.append(f"- {item.get('date', '')} {source} {amount:g} 元 [{category}]")
        return "已记录收入：\n" + "\n".join(lines) + f"\n本次合计：{total:g} 元\n{encouragement('income')}"

    if kind == "date":
        return save_date_action(parsed, None)

    if kind == "mood":
        lines = []
        for item in items:
            score = int(item.get("score") or 0)
            append_csv(MOODS_CSV, [
                item.get("date", ""), item.get("mood", ""), score,
                item.get("reason", ""), item.get("note", ""), created_at, uuid.uuid4().hex,
            ])
            reason = f"，原因：{item.get('reason', '')}" if item.get("reason") else ""
            lines.append(f"- {item.get('date', '')} {item.get('mood', '')}（{score:+d}）{reason}")
        return "已记录心情：\n" + "\n".join(lines) + f"\n{mood_support_reply(items)}"

    lines = []
    for item in items:
        append_csv(NOTES_CSV, [item.get("date", ""), item.get("content", ""), created_at, uuid.uuid4().hex])
        lines.append(f"- {item.get('date', '')} {item.get('content', '')}")
    return "已记录生活事项：\n" + "\n".join(lines) + f"\n{encouragement('note')}"



def normalize_repeat(repeat: str) -> str:
    repeat = str(repeat or "none").strip().lower()
    return repeat if repeat in {"none", "daily", "weekly", "monthly", "yearly"} else "none"


def repeat_suffix(repeat: str) -> str:
    return {"daily": "（每天）", "weekly": "（每周）", "monthly": "（每月）", "yearly": "（每年）"}.get(normalize_repeat(repeat), "")


def reminder_exists(chat_id: int, remind_at: str, text: str, repeat: str) -> bool:
    if not REMINDERS_CSV.exists():
        return False
    for row in read_csv_rows(REMINDERS_CSV):
        if row.get("status") != "pending":
            continue
        if str(row.get("chat_id")) == str(chat_id) and row.get("remind_at") == remind_at and row.get("text") == text and normalize_repeat(row.get("repeat")) == normalize_repeat(repeat):
            return True
    return False


def append_reminder_row(chat_id: int, remind_at: str, text: str, repeat: str, created_at: str) -> bool:
    repeat = normalize_repeat(repeat)
    if reminder_exists(chat_id, remind_at, text, repeat):
        return False
    append_csv(REMINDERS_CSV, [uuid.uuid4().hex, chat_id, remind_at, text, "pending", created_at, "", repeat])
    return True


def is_annual_important_item(title: str) -> bool:
    return any(word in title for word in ("生日", "纪念日", "周年", "忌日"))


def parse_remind_days(text: str) -> int:
    match = re.search(r"提前\s*(\d+|[一二两三四五六七八九十]{1,3})\s*天", text)
    if not match:
        return 0
    value = chinese_number_to_int(match.group(1))
    return max(0, value or 0)


def parse_item_date(text: str) -> datetime.date | None:
    today = datetime.now().date()
    match = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date()
        except ValueError:
            return None
    match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|号)?", text)
    if match:
        try:
            day = datetime(today.year, int(match.group(1)), int(match.group(2))).date()
        except ValueError:
            return None
        if day < today:
            try:
                day = day.replace(year=today.year + 1)
            except ValueError:
                day = day.replace(year=today.year + 1, month=2, day=28)
        return day
    if "后天" in text:
        return today + timedelta(days=2)
    if "明天" in text:
        return today + timedelta(days=1)
    if "今天" in text or "今晚" in text:
        return today
    return None


def parse_clock_from_text(text: str) -> str:
    match = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    match = re.search(r"(凌晨|早上|上午|中午|下午|晚上|今晚)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*点\s*(半|\d{1,2}分?|[一二三四五六七八九十]{1,3}分?)?", text)
    if not match:
        return ""
    hour = chinese_number_to_int(match.group(2))
    if hour is None or hour > 24:
        return ""
    minute_text = match.group(3) or ""
    minute = 0
    if minute_text == "半":
        minute = 30
    elif minute_text:
        parsed = chinese_number_to_int(minute_text.replace("分", ""))
        if parsed is not None:
            minute = parsed
    period = match.group(1) or ""
    if period in {"下午", "晚上", "今晚"} and 1 <= hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    if hour == 24:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def important_item_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,。；;]", text.strip()) if part.strip()]
    event_words = ("生日", "纪念日", "周年", "考试", "面试", "开学", "截止", "ddl", "DDL", "报名", "体检", "答辩", "比赛", "会议", "开会", "上课", "聚餐", "交作业")
    for part in parts:
        if parse_item_date(part) and any(word in part for word in event_words):
            return part
    for part in parts:
        if any(word in part for word in event_words):
            return part
    return text.strip()


def clean_important_title(text: str) -> str:
    clause = important_item_clause(text)
    title = clause
    title = re.sub(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?", "", title)
    title = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*(?:日|号)?", "", title)
    title = re.sub(r"(今天|明天|后天|今晚|上午|中午|下午|晚上|早上|凌晨)", "", title)
    title = re.sub(r"(凌晨|早上|上午|中午|下午|晚上|今晚)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*点(?:半|\d{1,2}分?)?", "", title)
    title = re.sub(r"\d{1,2}[:：]\d{2}", "", title)
    title = re.sub(r"提前\s*(\d+|[一二两三四五六七八九十]{1,3})\s*天\s*(提醒我?|通知我?|叫我?)?.*$", "", title)
    title = re.sub(r"(提醒我|通知我|叫我|提醒|记一下|记录一下|帮我记|帮我记录)", "", title)
    title = title.strip(" ：:，,。 的了")
    if title:
        return title
    for word in ("生日", "纪念日", "考试", "面试", "开学", "截止", "报名", "体检", "答辩", "比赛", "会议", "上课", "聚餐", "交作业"):
        if word in clause:
            return word
    return "重要事项"


def local_important_item_action(text: str) -> dict | None:
    if has_expense_hint(text) or has_income_hint(text) or has_weather_hint(text) or has_study_plan_hint(text):
        return None
    date_value = parse_item_date(text)
    if not date_value:
        return None
    title = clean_important_title(text)
    event_words = ("生日", "纪念日", "周年", "考试", "面试", "开学", "截止", "ddl", "DDL", "报名", "体检", "答辩", "比赛", "会议", "开会", "上课", "聚餐", "交作业")
    if not any(word in title or word in text for word in event_words):
        return None
    return {"type": "date", "items": [{"date": date_value.isoformat(), "title": title, "remind_days": parse_remind_days(text), "note": "", "time": parse_clock_from_text(text)}]}


def important_item_reminder_at(item: dict, repeat: str) -> datetime | None:
    try:
        day = datetime.strptime(str(item.get("date") or ""), "%Y-%m-%d").date()
    except ValueError:
        return None
    remind_days = safe_int(item.get("remind_days"))
    clock = str(item.get("time") or item.get("remind_time") or "09:00").strip() or "09:00"
    try:
        hour, minute = [int(part) for part in clock.split(":", 1)]
    except (ValueError, AttributeError):
        hour, minute = 9, 0
    target_day = day - timedelta(days=remind_days)
    now = datetime.now()
    if repeat == "yearly":
        event_this_year = day.replace(year=now.year)
        target_day = event_this_year - timedelta(days=remind_days)
    try:
        remind_at = datetime.combine(target_day, datetime.min.time()).replace(hour=hour, minute=minute)
    except ValueError:
        return None
    if repeat == "yearly":
        while remind_at <= now:
            remind_at = add_year(remind_at)
    elif remind_at <= now:
        return None
    return remind_at


def save_date_action(parsed: dict, chat_id: int | None) -> str:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    reminder_lines = []
    for item in parsed.get("items", []):
        date_text = str(item.get("date") or "").strip()
        title = str(item.get("title") or "重要事项").strip() or "重要事项"
        remind_days = safe_int(item.get("remind_days"))
        append_csv(DATES_CSV, [date_text, title, remind_days, item.get("note", ""), created_at, uuid.uuid4().hex])
        remind_text = f"，提前 {remind_days} 天提醒" if remind_days else ""
        lines.append(f"- {date_text} {title}{remind_text}")
        if chat_id is None:
            continue
        repeat = "yearly" if is_annual_important_item(title) else "none"
        remind_at = important_item_reminder_at(item, repeat)
        if remind_at is None:
            continue
        created = append_reminder_row(chat_id, remind_at.strftime("%Y-%m-%d %H:%M:%S"), title, repeat, created_at)
        duplicate = "（已存在）" if not created else ""
        reminder_lines.append(f"- {remind_at.strftime('%Y-%m-%d %H:%M:%S')} {title}{repeat_suffix(repeat)}{duplicate}")
    if not lines:
        return "没有识别到可保存的重要事项。"
    reply = "已记录重要事项：\n" + "\n".join(lines)
    if reminder_lines:
        reply += "\n关联提醒：\n" + "\n".join(reminder_lines)
    return reply + f"\n{encouragement('date')}"

def save_reminder(parsed: dict, chat_id: int) -> str:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    for item in parsed.get("items", []):
        remind_at = str(item.get("remind_at", "")).strip()
        text = str(item.get("text", "")).strip() or "提醒"
        try:
            datetime.strptime(remind_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return "提醒时间解析失败。你可以这样说：明天早上8点提醒我起床"
        repeat = normalize_repeat(item.get("repeat") or "none")
        created = append_reminder_row(chat_id, remind_at, text, repeat, created_at)
        duplicate = "（已存在）" if not created else ""
        lines.append(f"- {remind_at} {text}{repeat_suffix(repeat)}{duplicate}")
    if not lines:
        return "没有识别到可保存的提醒。"
    return "提醒已设好：\n" + "\n".join(lines)


def list_reminders() -> str:
    if not REMINDERS_CSV.exists():
        return "暂无提醒。"
    rows = []
    with REMINDERS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "pending":
                rows.append(row)
    rows.sort(key=lambda row: row.get("remind_at", ""))
    if not rows:
        return "暂无待提醒事项。"
    lines = ["待提醒："]
    for row in rows[:20]:
        repeat = row.get("repeat") or "none"
        lines.append(f"- {row.get('remind_at', '')} {row.get('text', '')}{repeat_suffix(repeat)}")
    return "\n".join(lines)


def add_month(dt: datetime) -> datetime:
    month = dt.month + 1
    year = dt.year + month // 13
    month = 1 if month == 13 else month
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(dt.day, days_in_month[month - 1])
    return dt.replace(year=year, month=month, day=day)


def add_year(dt: datetime) -> datetime:
    try:
        return dt.replace(year=dt.year + 1)
    except ValueError:
        return dt.replace(year=dt.year + 1, month=2, day=28)


def next_repeat_time(remind_at: datetime, repeat: str, now: datetime) -> datetime:
    next_time = remind_at
    while next_time <= now:
        if repeat == "daily":
            next_time += timedelta(days=1)
        elif repeat == "weekly":
            next_time += timedelta(days=7)
        elif repeat == "monthly":
            next_time = add_month(next_time)
        elif repeat == "yearly":
            next_time = add_year(next_time)
        else:
            return next_time
    return next_time


def dispatch_due_reminders(token: str) -> None:
    if not REMINDERS_CSV.exists():
        return
    now = datetime.now()
    changed = False
    with REMINDERS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or ["id", "chat_id", "remind_at", "text", "status", "created_at", "sent_at", "repeat"]
    if "repeat" not in fieldnames:
        fieldnames.append("repeat")
    for row in rows:
        if row.get("status") != "pending":
            continue
        try:
            remind_at = datetime.strptime(row.get("remind_at", ""), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if remind_at <= now:
            chat_id = row.get("chat_id")
            text = row.get("text") or "提醒"
            try:
                send_message(token, int(chat_id), f"提醒：{text}")
            except (TypeError, ValueError):
                row["status"] = "invalid"
                changed = True
                continue
            repeat = (row.get("repeat") or "none").lower()
            if repeat in {"daily", "weekly", "monthly", "yearly"}:
                row["remind_at"] = next_repeat_time(remind_at, repeat, now).strftime("%Y-%m-%d %H:%M:%S")
                row["sent_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                row["status"] = "pending"
            else:
                row["status"] = "sent"
                row["sent_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
            changed = True
    if changed:
        with REMINDERS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def delete_linked_reminders_for_date(date_row: dict) -> int:
    title = str(date_row.get("title") or "").strip()
    if not title or not REMINDERS_CSV.exists():
        return 0
    with REMINDERS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    kept = []
    removed = 0
    for row in rows:
        text = str(row.get("text") or "").strip()
        if row.get("status") == "pending" and (text == title or title in text or text in title):
            removed += 1
            continue
        kept.append(row)
    if removed:
        with REMINDERS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept)
    return removed

def delete_record(request_data: dict) -> str:
    info = find_target_record(request_data)
    if not info:
        return "没找到可删除的匹配记录。\n请说得更具体一点，比如：删除今天奶茶 15，或先发 /recent 后说“删第2条”。"
    rows = info["rows"]
    index = info["index"]
    kind = info["kind"]
    removed = rows.pop(index)
    write_csv_rows(info["path"], info["fieldnames"], rows)
    extra = ""
    if kind == "date":
        linked = delete_linked_reminders_for_date(removed)
        if linked:
            extra = f"\n同时删除关联提醒 {linked} 条。"
    if kind == "goal":
        logs = remove_goal_logs(removed.get("id", ""))
        if logs:
            extra = f"\n同时删除目标进度 {logs} 条。"
    return "已删除：\n" + describe_deleted(kind, removed) + extra

def delete_from_reply_context(reply_context: str) -> str | None:
    if not reply_context:
        return None
    lines = [line.strip() for line in reply_context.splitlines() if line.strip()]
    candidates = [line.lstrip("- ").strip() for line in lines if line.lstrip().startswith("- ")]
    if not candidates:
        candidates = lines
    for line in candidates:
        parsed = parse_record_line_for_delete(line)
        if parsed:
            parsed["_quoted"] = True
            result = delete_record(parsed)
            if not result.startswith("没找到"):
                return result
    return "????????????????????????"




def infer_delete_date_from_text(text: str) -> str:
    today = datetime.now().date()
    if "今天" in text or "今日" in text:
        return today.isoformat()
    if "昨天" in text:
        return (today - timedelta(days=1)).isoformat()
    if "明天" in text:
        return (today + timedelta(days=1)).isoformat()
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def infer_amount_from_text(text: str) -> float | None:
    currency_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)", text)
    if currency_match:
        return float(currency_match.group(1))
    if not any(word in text for word in ("早餐", "午饭", "晚饭", "奶茶", "打车", "花", "买", "充值", "续费", "消费", "收入", "赚", "报销", "预算")):
        return None
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    # Avoid treating dates like 7?12? as money. For money-like text, the last number is usually the amount.
    return float(numbers[-1])


def infer_delete_target_from_text(text: str, amount) -> str:
    if any(word in text for word in ("提醒", "闹钟", "叫我", "通知")):
        return "reminder"
    if any(word in text for word in ("重要事项", "重要日期", "日期", "生日", "纪念日", "考试", "面试", "开学", "截止")):
        return "date"
    if "待办" in text:
        return "todo"
    if "预算" in text:
        return "budget"
    if any(word in text for word in ("收入", "赚", "赚了", "工资", "兼职", "红包", "报销")):
        return "income"
    if any(word in text for word in MOOD_WORDS):
        return "mood"
    if amount is not None:
        return "any"
    return "any"


def clean_original_message_for_delete(text: str) -> str:
    text = re.sub(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2})", " ", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:元|块)?", " ", text)
    text = re.sub(r"(我|今天|今日|昨天|明天|后天|本月|这个月|这月|本周|这周|这个星期|要|了|的|把|这个|那个|这条|那条|设置|添加|新增|加入|记录|吃了)", " ", text)
    return clean_delete_query(text)

def parse_record_line_for_delete(line: str) -> dict | None:
    date = infer_delete_date_from_text(line)
    time_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", line)
    amount = infer_amount_from_text(line)
    query = clean_original_message_for_delete(line)
    target = infer_delete_target_from_text(line, amount)
    if time_match and target == "any":
        target = "reminder"
    if not query and amount is None and not date:
        return None
    return {"type": "delete", "target": target, "date": date, "query": query, "amount": amount}

def clean_delete_query(query: str) -> str:
    query = re.sub(r"(重\s*事项|重\s*日期)", "", query)
    query = re.sub(r"(删除|删掉|去掉|撤销|取消|移除|关掉|关闭|取消掉|这条|该事项|这个事项|刚才那条|上一条|记录|提醒|闹钟|待办|预算|重要事项|重要日期|日期|已设好|已加入)", "", query)
    query = re.sub(r"\s+", " ", query).strip(" ：:，,。-")
    return query

def delete_match_score(kind: str, row: dict, main_field: str, date: str, query: str, amount) -> int:
    if date:
        row_date = row.get("date") or row.get("due_date") or row.get("remind_at", "")[:10] or row.get("created_at", "")[:10]
        if row_date != date:
            return -1
    if amount not in (None, ""):
        if kind in {"expense", "income", "budget"}:
            amount_field = "amount"
        else:
            return -1
        try:
            if abs(float(row.get(amount_field) or 0) - float(amount)) > 0.001:
                return -1
        except (TypeError, ValueError):
            return -1

    haystack = " ".join(str(value) for value in row.values())
    score = 0
    if date:
        score += 4
    if amount not in (None, ""):
        score += 4
    if query:
        if query in haystack:
            score += 8
        else:
            tokens = [part for part in re.split(r"[\s,，。:：\[\]-]+", query) if part]
            hits = sum(1 for token in tokens if token in haystack)
            if hits == 0:
                return -1
            score += hits
    if not query and not date and amount in (None, ""):
        score += 1
    if row.get(main_field):
        score += 1
    if kind == "reminder" and row.get("status") == "pending":
        score += 2
    if kind == "todo" and row.get("status") == "pending":
        score += 2
    return score

def describe_deleted(kind: str, row: dict) -> str:
    if kind == "expense":
        return f"- {row.get('date', '')} {row.get('item', '')} {row.get('amount', '')} 元 [{row.get('category', '')}]"
    if kind == "income":
        return f"- {row.get('date', '')} {row.get('source', '')} {row.get('amount', '')} 元 [{row.get('category', '')}]"
    if kind == "date":
        return f"- [重要事项] {row.get('date', '')} {row.get('title', '')}"
    if kind == "mood":
        return f"- {row.get('date', '')} {row.get('mood', '')} {row.get('score', '')} {row.get('reason', '')}"
    if kind == "reminder":
        repeat = row.get("repeat") or "none"
        return f"- {row.get('remind_at', '')} {row.get('text', '')}{repeat_suffix(repeat)}"
    if kind == "todo":
        due = f"（{row.get('due_date')}）" if row.get("due_date") else ""
        return f"- {row.get('text', '')}{due}"
    if kind == "budget":
        title = "本周" if row.get("period") == "week" else "本月"
        return f"- {title}{row.get('category', '')}预算 {row.get('amount', '')} 元"
    return f"- {row.get('date', '')} {row.get('content', '')}"

def record_kind_specs() -> dict[str, dict]:
    headers = managed_record_headers()
    return {
        "expense": {"path": EXPENSES_CSV, "fieldnames": headers[EXPENSES_CSV], "main_field": "item", "label": "消费"},
        "income": {"path": INCOME_CSV, "fieldnames": headers[INCOME_CSV], "main_field": "source", "label": "收入"},
        "date": {"path": DATES_CSV, "fieldnames": headers[DATES_CSV], "main_field": "title", "label": "重要事项"},
        "note": {"path": NOTES_CSV, "fieldnames": headers[NOTES_CSV], "main_field": "content", "label": "事项"},
        "mood": {"path": MOODS_CSV, "fieldnames": headers[MOODS_CSV], "main_field": "mood", "label": "心情"},
        "reminder": {"path": REMINDERS_CSV, "fieldnames": headers[REMINDERS_CSV], "main_field": "text", "label": "提醒"},
        "todo": {"path": TODOS_CSV, "fieldnames": headers[TODOS_CSV], "main_field": "text", "label": "待办"},
        "budget": {"path": BUDGETS_CSV, "fieldnames": headers[BUDGETS_CSV], "main_field": "category", "label": "预算"},
        "goal": {"path": GOALS_CSV, "fieldnames": headers[GOALS_CSV], "main_field": "title", "label": "目标"},
    }


def record_kinds_for_target(target: str) -> list[str]:
    specs = record_kind_specs()
    target = str(target or "any").lower()
    aliases = {"alarm": "reminder", "task": "todo", "important": "date", "important_date": "date", "dates": "date", "goals": "goal"}
    target = aliases.get(target, target)
    if target in specs:
        return [target]
    return ["expense", "income", "date", "note", "mood", "reminder", "todo", "budget", "goal"]


def record_rows_info(kind: str) -> dict | None:
    spec = record_kind_specs().get(kind)
    if not spec:
        return None
    path = spec["path"]
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or spec["fieldnames"])
        rows = list(reader)
    for name in spec["fieldnames"]:
        if name not in fieldnames:
            fieldnames.append(name)
    return {"kind": kind, "path": path, "fieldnames": fieldnames, "rows": rows, "spec": spec}


def find_record_by_id(kind: str, record_id: str) -> dict | None:
    if not record_id:
        return None
    for candidate_kind in record_kinds_for_target(kind):
        info = record_rows_info(candidate_kind)
        if not info:
            continue
        for index, row in enumerate(info["rows"]):
            if row.get("id") == record_id:
                info.update({"index": index, "row": row})
                return info
    return None


def find_target_record(request_data: dict) -> dict | None:
    record_id = str(request_data.get("id") or "").strip()
    target = str(request_data.get("target") or request_data.get("kind") or "any").lower()
    if record_id:
        return find_record_by_id(target, record_id)
    date = str(request_data.get("date") or "").strip()
    query = clean_delete_query(str(request_data.get("query") or ""))
    amount = request_data.get("amount")
    quoted = bool(request_data.get("_quoted"))
    recent_floor = (datetime.now().date() - timedelta(days=1)).isoformat() if quoted and not date else ""
    best = None
    for kind in record_kinds_for_target(target):
        info = record_rows_info(kind)
        if not info:
            continue
        main_field = info["spec"]["main_field"]
        for index, row in enumerate(info["rows"]):
            if recent_floor:
                row_created = (row.get("created_at", "") or row.get("date", "") or row.get("remind_at", ""))[:10]
                if row_created and row_created < recent_floor:
                    continue
            score = delete_match_score(kind, row, main_field, date, query, amount)
            if score < 0 and quoted and amount not in (None, "") and query:
                score = delete_match_score(kind, row, main_field, date, "", amount)
            if score < 0:
                continue
            created_at = row.get("created_at", "")
            if kind == "reminder" and row.get("status") == "pending":
                score += 2
            if kind == "todo" and row.get("status") == "pending":
                score += 2
            candidate = (score, created_at, index, kind, info, row)
            if best is None or candidate[:4] > best[:4]:
                best = candidate
    if best is None:
        return None
    _, _, index, kind, info, row = best
    info = dict(info)
    info.update({"index": index, "kind": kind, "row": row})
    return info


def pending_record_action_store(state: dict) -> dict:
    return state.setdefault("pending_record_actions", {})


def record_action_candidates(request_data: dict, limit: int = 6) -> list[dict]:
    if str(request_data.get("id") or "").strip():
        info = find_record_by_id(str(request_data.get("target") or request_data.get("kind") or "any"), str(request_data.get("id") or ""))
        if not info:
            return []
        row = info["row"]
        return [{"kind": info["kind"], "id": row.get("id", ""), "label": record_kind_specs()[info["kind"]]["label"], "text": format_record_text(info["kind"], row), "score": 999}]
    target = str(request_data.get("target") or request_data.get("kind") or "any").lower()
    date = str(request_data.get("date") or "").strip()
    query = clean_delete_query(str(request_data.get("query") or ""))
    amount = request_data.get("amount")
    candidates = []
    for kind in record_kinds_for_target(target):
        info = record_rows_info(kind)
        if not info:
            continue
        main_field = info["spec"]["main_field"]
        for row in info["rows"]:
            score = delete_match_score(kind, row, main_field, date, query, amount)
            if score < 0:
                continue
            if kind == "reminder" and row.get("status") == "pending":
                score += 2
            if kind == "todo" and row.get("status") == "pending":
                score += 2
            candidates.append({
                "kind": kind,
                "id": row.get("id", ""),
                "label": info["spec"]["label"],
                "text": format_record_text(kind, row),
                "score": score,
                "created_at": row.get("created_at", ""),
            })
    candidates.sort(key=lambda item: (item.get("score", 0), item.get("created_at", "")), reverse=True)
    return candidates[:limit]


def should_confirm_record_action(request_data: dict, candidates: list[dict]) -> bool:
    if str(request_data.get("id") or "").strip() or len(candidates) < 2:
        return False
    top = safe_int(candidates[0].get("score"))
    second = safe_int(candidates[1].get("score"))
    query = clean_delete_query(str(request_data.get("query") or ""))
    return top == second or (len(query) <= 2 and second >= top - 1)


def queue_record_action_confirmation(action: str, request_data: dict, candidates: list[dict], chat_id: int | None) -> str:
    action_label = "删除" if action == "delete" else "修改"
    lines = [f"我找到几条可能要{action_label}的记录，你选哪一条？"]
    for index, item in enumerate(candidates[:6], 1):
        lines.append(f"{index}. [{item.get('label', '')}] {item.get('text', '')}")
    lines.append("回复编号即可，或回复“取消”。")
    if chat_id is not None:
        state = read_state()
        pending_record_action_store(state)[str(chat_id)] = {
            "action": action,
            "raw_text": request_data.get("raw_text") or request_data.get("text") or "",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": [{"kind": item.get("kind", ""), "id": item.get("id", ""), "label": item.get("label", ""), "text": item.get("text", "")} for item in candidates[:6]],
        }
        set_pending_center(state, chat_id, "record_action")
        write_state(state)
    return "\n".join(lines)


def resolve_or_queue_record_action(action: str, request_data: dict, chat_id: int | None) -> str:
    candidates = record_action_candidates(request_data)
    if chat_id is not None and should_confirm_record_action(request_data, candidates):
        return queue_record_action_confirmation(action, request_data, candidates, chat_id)
    if action == "delete":
        return delete_record(request_data)
    return update_record(request_data, chat_id)


def handle_pending_record_action(text: str, chat_id: int | None, intent: dict | None = None) -> str | None:
    if chat_id is None:
        return None
    intent = intent or confirmation_intent(text)
    state = read_state()
    pending = pending_record_action_store(state)
    item = pending.get(str(chat_id))
    if not item:
        return None
    try:
        created_at = datetime.strptime(item.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        created_at = datetime.now()
    if datetime.now() - created_at > timedelta(minutes=30):
        pending.pop(str(chat_id), None)
        clear_pending_center(state, chat_id, "record_action")
        write_state(state)
        return None
    if intent.get("cancel"):
        pending.pop(str(chat_id), None)
        clear_pending_center(state, chat_id, "record_action")
        write_state(state)
        return "好，这次不处理这些记录。"
    index = intent.get("index")
    items = item.get("items") or []
    if intent.get("confirm") and len(items) == 1:
        index = 1
    if not index:
        return None
    index = int(index) - 1
    if not (0 <= index < len(items)):
        return "编号没对上，你可以重新发一个列表里的数字。"
    selected = items[index]
    pending.pop(str(chat_id), None)
    clear_pending_center(state, chat_id, "record_action")
    write_state(state)
    action = item.get("action") or "delete"
    if action == "delete":
        return delete_record({"type": "delete", "target": selected.get("kind", "any"), "id": selected.get("id", "")})
    return update_record({"type": "update", "target": selected.get("kind", "any"), "id": selected.get("id", ""), "raw_text": item.get("raw_text", "")}, chat_id)
def remove_goal_logs(goal_id: str) -> int:
    if not goal_id or not GOAL_LOGS_CSV.exists():
        return 0
    with GOAL_LOGS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or ["goal_id", "date", "amount", "unit", "note", "created_at"]
        rows = list(reader)
    kept = [row for row in rows if row.get("goal_id") != goal_id]
    removed = len(rows) - len(kept)
    if removed:
        write_csv_rows(GOAL_LOGS_CSV, list(fieldnames), kept)
    return removed


def format_record_text(kind: str, row: dict) -> str:
    if kind == "expense":
        return f"{row.get('date', '')} {row.get('item', '')} {row.get('amount', '')} 元 [{row.get('category', '')}]"
    if kind == "income":
        return f"{row.get('date', '')} {row.get('source', '')} {row.get('amount', '')} 元 [{row.get('category', '')}]"
    if kind == "date":
        remind = safe_int(row.get("remind_days"))
        suffix = f"，提前 {remind} 天提醒" if remind else ""
        return f"{row.get('date', '')} {row.get('title', '')}{suffix}"
    if kind == "note":
        return f"{row.get('date', '')} {row.get('content', '')}"
    if kind == "mood":
        extra = row.get("reason") or row.get("note") or ""
        return f"{row.get('date', '')} {row.get('mood', '')} {row.get('score', '')} {extra}".strip()
    if kind == "reminder":
        repeat = row.get("repeat") or "none"
        return f"{row.get('remind_at', '')} {row.get('text', '')}{repeat_suffix(repeat)}"
    if kind == "todo":
        due = f"（{row.get('due_date')}）" if row.get("due_date") else ""
        status = "已完成" if row.get("status") == "done" else "待办"
        return f"{row.get('text', '')}{due} [{status}]"
    if kind == "budget":
        title = "本周" if row.get("period") == "week" else "本月"
        return f"{title}{row.get('category', '')}预算 {row.get('amount', '')} 元"
    if kind == "goal":
        period = {"daily": "每天", "weekly": "每周", "monthly": "每月"}.get(row.get("period"), "目标")
        return f"{period}{row.get('title', '')} {row.get('target_amount', '')} {goal_unit_label(row.get('unit', ''))} [{row.get('status', '')}]"
    return " ".join(str(value) for value in row.values() if value)


def recent_entries(limit: int = 8) -> list[dict]:
    entries = []
    for kind, spec in record_kind_specs().items():
        info = record_rows_info(kind)
        if not info:
            continue
        if kind == "mood":
            mood_by_date = {}
            for row in info["rows"]:
                date = row.get("date", "")
                if not date:
                    continue
                if date not in mood_by_date or row.get("created_at", "") > mood_by_date[date].get("created_at", ""):
                    mood_by_date[date] = row
            rows = list(mood_by_date.values())
        else:
            rows = info["rows"]
        for row in rows:
            if kind == "reminder" and row.get("status") not in {"pending", "sent", ""}:
                continue
            if kind == "goal" and row.get("status") not in {"active", ""}:
                continue
            entries.append({
                "kind": kind,
                "id": row.get("id", ""),
                "created_at": row.get("created_at", ""),
                "label": spec["label"],
                "text": format_record_text(kind, row),
            })
    entries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return entries[:limit]


def remember_recent_entries(chat_id: int | None, entries: list[dict]) -> None:
    if chat_id is None:
        return
    state = read_state()
    store = state.setdefault("recent_index", {})
    store[str(chat_id)] = [
        {"n": index, "kind": entry.get("kind", ""), "id": entry.get("id", ""), "created_at": entry.get("created_at", ""), "text": entry.get("text", "")}
        for index, entry in enumerate(entries, 1)
    ]
    write_state(state)


def extract_record_index(text: str) -> int | None:
    for pattern in (r"第\s*(\d{1,2})\s*(?:条|项|个|号)", r"(?:删|删除|改|修改|把)\s*(\d{1,2})\s*(?:条|项|个|号)"):
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def resolve_recent_reference(index: int, chat_id: int | None) -> dict | None:
    if index <= 0:
        return None
    if chat_id is not None:
        try:
            refs = read_state().get("recent_index", {}).get(str(chat_id), [])
        except Exception:
            refs = []
        for ref in refs:
            if safe_int(ref.get("n")) == index and find_record_by_id(ref.get("kind", ""), ref.get("id", "")):
                return ref
    current = recent_entries(max(index, 20))
    if index <= len(current):
        entry = current[index - 1]
        return {"n": index, "kind": entry.get("kind", ""), "id": entry.get("id", ""), "text": entry.get("text", "")}
    return None


def local_delete_action(text: str, chat_id: int | None) -> dict | None:
    if not is_delete_request(text):
        return None
    index = extract_record_index(text)
    if index:
        ref = resolve_recent_reference(index, chat_id)
        if not ref:
            return {"type": "answer", "answer": f"没找到最近记录第 {index} 条。你可以先发 /recent 再删。"}
        return {"type": "delete", "target": ref.get("kind", "any"), "id": ref.get("id", "")}
    return parse_record_line_for_delete(text)


def is_update_request(text: str) -> bool:
    return any(word in text for word in ("改成", "改为", "修改成", "修改为", "换成", "调到", "改到", "应该是", "不是"))


def update_query_prefix(text: str) -> str:
    prefix = re.split(r"改成|改为|修改成|修改为|换成|调到|改到|应该是|不是", text, maxsplit=1)[0]
    prefix = re.sub(r"^(把|将|帮我|请)", "", prefix).strip(" ：:，,。")
    return prefix or text


def infer_update_target_from_text(text: str, fallback: str) -> str:
    if fallback and fallback != "any":
        return fallback
    if any(word in text for word in ("提醒", "闹钟", "叫我", "通知")):
        return "reminder"
    if any(word in text for word in ("重要事项", "重要日期", "生日", "纪念日", "考试", "面试", "截止")):
        return "date"
    if any(word in text for word in ("待办", "任务")):
        return "todo"
    if any(word in text for word in ("目标", "每天", "每日")):
        return "goal"
    if "预算" in text:
        return "budget"
    if any(word in text for word in ("收入", "工资", "兼职", "红包", "报销")):
        return "income"
    return fallback or "any"


def local_update_action(text: str, chat_id: int | None) -> dict | None:
    if not is_update_request(text):
        return None
    index = extract_record_index(text)
    if index:
        ref = resolve_recent_reference(index, chat_id)
        if not ref:
            return {"type": "answer", "answer": f"没找到最近记录第 {index} 条。你可以先发 /recent 再改。"}
        return {"type": "update", "target": ref.get("kind", "any"), "id": ref.get("id", ""), "raw_text": text}
    prefix = update_query_prefix(text)
    parsed = parse_record_line_for_delete(prefix)
    if not parsed:
        parsed = {"type": "update", "target": infer_update_target_from_text(text, "any"), "query": clean_original_message_for_delete(prefix), "date": infer_delete_date_from_text(prefix), "amount": None}
    parsed["type"] = "update"
    parsed["raw_text"] = text
    parsed["target"] = infer_update_target_from_text(text, parsed.get("target", "any"))
    return parsed


def parse_update_amount(text: str, kind: str = "") -> float | None:
    money_match = re.search(r"(?:改成|改为|修改成|修改为|换成|应该是|是)\s*(\d+(?:\.\d+)?)\s*(?:元|块)", text)
    if money_match:
        return float(money_match.group(1))
    amount_kinds = {"expense", "income", "budget", "goal"}
    money_cue = kind in amount_kinds or any(word in text for word in ("元", "块", "预算", "消费", "收入", "花", "买", "早餐", "午饭", "晚饭", "奶茶", "打车"))
    if money_cue or "不是" in text:
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        if numbers:
            return float(numbers[-1])
    return None


def extract_update_tail(text: str) -> str:
    parts = re.split(r"改成|改为|修改成|修改为|换成|调到|改到|应该是|不是|是", text)
    tail = parts[-1] if parts else ""
    return tail.strip(" ：:，,。")


def tail_is_only_value(tail: str, kind: str) -> bool:
    if not tail:
        return True
    if parse_update_amount(tail, kind) is not None and re.fullmatch(r"\d+(?:\.\d+)?\s*(?:元|块|分钟|min|小时|h|题|次|页|公里|km)?", tail, re.I):
        return True
    if parse_clock_from_text(tail):
        return True
    if parse_item_date(tail):
        return True
    return False


def infer_record_updates(kind: str, text: str, row: dict) -> dict:
    updates = {}
    amount = parse_update_amount(text, kind)
    if amount is not None:
        if kind in {"expense", "income", "budget"}:
            updates["amount"] = f"{amount:g}"
        elif kind == "goal":
            updates["target_amount"] = f"{amount:g}"
    date_value = parse_item_date(text)
    clock = parse_clock_from_text(text)
    tail = extract_update_tail(text)
    if kind == "reminder":
        old_dt = None
        try:
            old_dt = datetime.strptime(row.get("remind_at", ""), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        if old_dt and (date_value or clock):
            day = date_value or old_dt.date()
            if clock:
                hour, minute = [int(part) for part in clock.split(":", 1)]
            else:
                hour, minute = old_dt.hour, old_dt.minute
            updates["remind_at"] = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute).strftime("%Y-%m-%d %H:%M:%S")
        if tail and not tail_is_only_value(tail, kind):
            updates["text"] = tail
    elif kind == "date":
        if date_value:
            updates["date"] = date_value.isoformat()
        if "提前" in text:
            updates["remind_days"] = str(parse_remind_days(text))
        if tail and not tail_is_only_value(tail, kind):
            updates["title"] = tail
    elif kind == "expense":
        if tail and not tail_is_only_value(tail, kind):
            updates["item"] = tail
        for category in ("餐饮", "交通", "购物", "居住", "娱乐", "医疗", "学习", "其他"):
            if category in text:
                updates["category"] = category
                break
    elif kind == "income":
        if tail and not tail_is_only_value(tail, kind):
            updates["source"] = tail
        for category in ("兼职", "工资", "红包", "报销", "其他"):
            if category in text:
                updates["category"] = category
                break
    elif kind == "note":
        if tail:
            updates["content"] = tail
        if date_value:
            updates["date"] = date_value.isoformat()
    elif kind == "mood":
        if tail and not tail_is_only_value(tail, kind):
            updates["note"] = tail
        parsed = local_mood_parse(text)
        if is_mood_statement(text):
            item = parsed.get("items", [{}])[0]
            updates.update({"mood": item.get("mood", row.get("mood", "")), "score": str(item.get("score", row.get("score", ""))), "reason": item.get("reason", row.get("reason", ""))})
    elif kind == "todo":
        if tail and not tail_is_only_value(tail, kind):
            updates["text"] = tail
        if date_value:
            updates["due_date"] = date_value.isoformat()
    elif kind == "budget":
        for category in ("总额", "餐饮", "交通", "购物", "居住", "娱乐", "医疗", "学习", "其他"):
            if category in text:
                updates["category"] = category
                break
    elif kind == "goal":
        if tail and not tail_is_only_value(tail, kind):
            updates["title"] = tail
            updates["subject"] = tail.lower().replace(" ", "")
        if clock:
            updates["reminder_time"] = clock
    return {key: value for key, value in updates.items() if value not in (None, "")}


def sync_linked_reminders_after_date_update(old_row: dict, new_row: dict) -> int:
    old_title = str(old_row.get("title") or "").strip()
    new_title = str(new_row.get("title") or old_title).strip()
    if not old_title or not REMINDERS_CSV.exists():
        return 0
    info = record_rows_info("reminder")
    if not info:
        return 0
    changed = 0
    for row in info["rows"]:
        text = str(row.get("text") or "").strip()
        if row.get("status") != "pending" or not (text == old_title or old_title in text or text in old_title):
            continue
        if new_title and text != new_title:
            row["text"] = new_title
        try:
            old_remind = datetime.strptime(row.get("remind_at", ""), "%Y-%m-%d %H:%M:%S")
            event_day = datetime.strptime(str(new_row.get("date") or ""), "%Y-%m-%d").date()
            target_day = event_day - timedelta(days=safe_int(new_row.get("remind_days")))
            new_remind = datetime.combine(target_day, datetime.min.time()).replace(hour=old_remind.hour, minute=old_remind.minute)
            if normalize_repeat(row.get("repeat")) == "yearly":
                while new_remind <= datetime.now():
                    new_remind = add_year(new_remind)
            row["remind_at"] = new_remind.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        changed += 1
    if changed:
        write_csv_rows(info["path"], info["fieldnames"], info["rows"])
    return changed


def update_record(request_data: dict, chat_id: int | None = None) -> str:
    info = find_target_record(request_data)
    if not info:
        return "没找到可修改的匹配记录。你可以先发 /recent，再说：把第2条改成15元。"
    kind = info["kind"]
    row = info["row"]
    old_row = dict(row)
    updates = infer_record_updates(kind, str(request_data.get("raw_text") or ""), row)
    if not updates:
        return "我找到记录了，但没看清要改成什么。比如：把第2条改成15元，或把第3条改到明天十点。"
    row.update(updates)
    write_csv_rows(info["path"], info["fieldnames"], info["rows"])
    extra = ""
    if kind == "date":
        linked = sync_linked_reminders_after_date_update(old_row, row)
        if linked:
            extra = f"\n同步修改关联提醒 {linked} 条。"
    return "已修改：\n" + describe_deleted(kind, row) + extra
def encouragement(kind: str) -> str:
    pools = {
        "expense": [
            "记好了，这笔也归档了",
            "收下了，账慢慢清楚起来",
            "嗯，已经放进账本里",
            "这笔我记住了，月底回看会很直观",
            "记上了，花出去的钱有了去处",
        ],
        "income": [
            "到账记录也收好了",
            "这笔收入记下了，现金流更完整",
            "收到，收入这边也补上了",
            "记好了，之后总结会算进净额里",
        ],
        "date": [
            "已收好，到时候不会靠脑子硬记",
            "这件事放进清单了",
            "记下了，重要日子先替你存着",
            "安排上了，之后查起来方便",
        ],
        "note": [
            "收到，这条生活记录留住了",
            "记下来了，日后回看会有线索",
            "这一条我收好了",
            "嗯，先放进你的生活档案里",
        ],
        "mood": [
            "我记下了，状态被看见就已经轻一点",
            "收到，今天的情绪也算数",
            "记住了，不用急着解释清楚，先留个痕迹",
            "我放进心情记录里了，之后总结会一起看",
        ],
    }
    return style_reply(random.choice(pools.get(kind, ["已处理"])), "feedback")


def read_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_raw(update: dict) -> None:
    with RAW_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(update, ensure_ascii=False) + "\n")


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


TONE_ALIASES = {
    "warm": "温柔陪伴",
    "brief": "简洁工具人",
    "strict": "严格督促",
    "senior": "学长式督促",
}


def current_tone_mode() -> str:
    try:
        state = read_state()
        mode = str(state.get("tone_mode") or "warm")
    except Exception:
        mode = "warm"
    return mode if mode in TONE_ALIASES else "warm"


def tone_mode_from_text(text: str) -> str | None:
    if not any(word in text for word in ("语气", "模式", "切换", "改成", "换成", "用")):
        return None
    if any(word in text for word in ("简洁", "工具人", "短一点", "少废话")):
        return "brief"
    if any(word in text for word in ("严格", "督促", "狠一点", "别惯着")):
        return "strict"
    if any(word in text for word in ("学长", "学姐", "前辈")):
        return "senior"
    if any(word in text for word in ("温柔", "陪伴", "正常", "默认")):
        return "warm"
    return None


def set_tone_mode_reply(text: str) -> str | None:
    mode = tone_mode_from_text(text)
    if not mode:
        return None
    state = read_state()
    state["tone_mode"] = mode
    write_state(state)
    return f"语气已切换：{TONE_ALIASES[mode]}。你可以随时说：切换简洁模式 / 切换严格模式 / 切换温柔模式。"


def style_reply(text: str, kind: str = "chat") -> str:
    mode = current_tone_mode()
    if mode == "brief":
        return text.split("\n", 1)[0][:120]
    if mode == "strict" and kind in {"chat", "feedback"}:
        if "下一步" in text or re.match(r"^已(记录|设置|更新|加入|完成|删除|保存)", text):
            return text
        return text + "\n下一步：别等状态，先做一个最小动作。"
    if mode == "senior" and kind in {"chat", "feedback"}:
        if "学长提醒" in text:
            return text
        return text + "\n学长提醒：别追求一下子做满，先把今天这一格推进。"
    return text


def normalize_goal_unit(unit: str) -> str:
    unit = (unit or "").lower().strip()
    if unit in {"min", "mins", "minute", "minutes", "分钟"}:
        return "min"
    if unit in {"h", "hour", "hours", "小时"}:
        return "min"
    if unit in {"km", "公里"}:
        return "公里"
    return unit or "次"


def convert_goal_amount(amount: float, unit: str) -> tuple[float, str]:
    raw_unit = (unit or "").lower().strip()
    normalized = normalize_goal_unit(unit)
    if raw_unit in {"h", "hour", "hours", "小时"}:
        return amount * 60, "min"
    return amount, normalized


def goal_unit_label(unit: str) -> str:
    return {"min": "分钟", "公里": "公里", "个": "个", "页": "页", "次": "次", "题": "题"}.get(unit, unit or "次")


def clean_goal_subject(text: str) -> str:
    text = re.sub(r"(我想|我要|我希望|希望|请|帮我|给我|每天|每日|每周|每月|坚持|完成|提醒我|提醒|打卡|目标|计划|一下|吧)", "", text, flags=re.I)
    text = re.sub(r"(学了|学习了|做了|练了|背了|读了|跑了|运动了|完成了|打卡了)$", "", text, flags=re.I)
    return text.strip(" ：:，,。 的了") or "目标"


def parse_goal_target(text: str) -> dict | None:
    if not any(word in text for word in ("每天", "每日", "每周", "每月", "目标", "坚持")):
        return None
    if has_expense_hint(text) or has_income_hint(text):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(min|mins|分钟|小时|h|个|页|次|题|公里|km)", text, re.I)
    if not match:
        return None
    amount, unit = convert_goal_amount(float(match.group(1)), match.group(2))
    period = "daily"
    if "每周" in text:
        period = "weekly"
    elif "每月" in text:
        period = "monthly"
    before = text[:match.start()]
    after = text[match.end():]
    subject = clean_goal_subject(before) or clean_goal_subject(after)
    title = subject
    reminder_time = ""
    time_match = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if time_match:
        reminder_time = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
    else:
        hour_match = re.search(r"(早上|上午|中午|下午|晚上|今晚)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*点", text)
        if hour_match:
            hour = chinese_number_to_int(hour_match.group(2))
            period_word = hour_match.group(1) or ""
            if hour is not None:
                if period_word in {"下午", "晚上", "今晚"} and 1 <= hour < 12:
                    hour += 12
                elif period_word == "中午" and hour < 11:
                    hour += 12
                reminder_time = f"{hour:02d}:00"
    return {"title": title, "subject": subject, "target_amount": amount, "unit": unit, "period": period, "reminder_time": reminder_time}


def active_goals() -> list[dict]:
    return [row for row in read_csv_rows(GOALS_CSV) if (row.get("status") or "active") == "active"]


def upsert_goal(parsed: dict, chat_id: int | None) -> tuple[dict, bool]:
    rows = read_csv_rows(GOALS_CSV)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = parsed["subject"]
    period = parsed["period"]
    existing = None
    for row in rows:
        if (row.get("status") or "active") == "active" and row.get("subject", "").lower() == subject.lower() and row.get("period") == period:
            existing = row
            break
    if existing:
        existing.update({
            "chat_id": str(chat_id or existing.get("chat_id") or ""),
            "title": parsed["title"],
            "subject": subject,
            "target_amount": f"{parsed['target_amount']:g}",
            "unit": parsed["unit"],
            "period": period,
            "reminder_time": parsed.get("reminder_time", ""),
            "status": "active",
        })
        write_csv_rows(GOALS_CSV, ["id", "chat_id", "title", "subject", "target_amount", "unit", "period", "reminder_time", "status", "created_at"], rows)
        return existing, False
    row = {
        "id": uuid.uuid4().hex,
        "chat_id": str(chat_id or ""),
        "title": parsed["title"],
        "subject": subject,
        "target_amount": f"{parsed['target_amount']:g}",
        "unit": parsed["unit"],
        "period": period,
        "reminder_time": parsed.get("reminder_time", ""),
        "status": "active",
        "created_at": created_at,
    }
    append_csv(GOALS_CSV, [row[name] for name in ["id", "chat_id", "title", "subject", "target_amount", "unit", "period", "reminder_time", "status", "created_at"]])
    return row, True


def save_goal_from_text(text: str, chat_id: int | None) -> str | None:
    parsed = parse_goal_target(text)
    if not parsed:
        return None
    goal, created = upsert_goal(parsed, chat_id)
    period_label = {"daily": "每天", "weekly": "每周", "monthly": "每月"}.get(goal.get("period"), "每天")
    target = f"{safe_amount(goal.get('target_amount')):g} {goal_unit_label(goal.get('unit', ''))}"
    verb = "已设置目标" if created else "已更新目标"
    lines = [f"{verb}: {period_label}{goal.get('title', '')} {target}"]
    if goal.get("reminder_time"):
        lines.append(f"提醒联动: {goal.get('reminder_time')} 会出现在你的目标提醒里。")
    lines.append("完成后直接说: 我学习python学了10min。")
    return "\n".join(lines)


def goal_log_total(goal_id: str, day: str) -> float:
    return sum(safe_amount(row.get("amount")) for row in read_csv_rows(GOAL_LOGS_CSV) if row.get("goal_id") == goal_id and row.get("date") == day)


def goal_subject_matches(goal: dict, text: str) -> bool:
    subject = (goal.get("subject") or goal.get("title") or "").lower().replace(" ", "")
    compact = text.lower().replace(" ", "")
    if subject and (subject in compact or compact in subject):
        return True
    english = re.findall(r"[a-zA-Z]+", subject)
    if english and any(word.lower() in compact for word in english):
        return True
    chinese = [word for word in re.findall(r"[\u4e00-\u9fa5]{2,}", subject) if word not in {"学习", "运动", "阅读"}]
    return bool(chinese and any(word in compact for word in chinese))


def parse_goal_progress(text: str) -> dict | None:
    if any(word in text for word in ("每天", "每日", "每周", "每月", "目标")) and parse_goal_target(text):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(min|mins|分钟|小时|h|个|页|次|题|公里|km)", text, re.I)
    if not match:
        return None
    if not any(word in text for word in ("学了", "学习", "做了", "练了", "背了", "读了", "跑了", "运动", "完成", "打卡")):
        return None
    amount, unit = convert_goal_amount(float(match.group(1)), match.group(2))
    goals = active_goals()
    matched = next((goal for goal in goals if goal_subject_matches(goal, text)), None)
    if not matched:
        return {"unmatched": True, "amount": amount, "unit": unit}
    return {"goal": matched, "amount": amount, "unit": unit, "note": text}


def save_goal_progress_from_text(text: str) -> str | None:
    parsed = parse_goal_progress(text)
    if not parsed:
        return None
    if parsed.get("unmatched"):
        return "我看到你完成了一点进度，但没匹配到目标。你可以先说: 每天学习python 15min。"
    goal = parsed["goal"]
    today = datetime.now().date().isoformat()
    amount = parsed["amount"]
    unit = goal.get("unit") or parsed.get("unit") or "次"
    if unit == "min" and parsed.get("unit") not in {"min", ""}:
        amount, _ = convert_goal_amount(amount, parsed.get("unit"))
    append_csv(GOAL_LOGS_CSV, [goal.get("id"), today, f"{amount:g}", unit, parsed.get("note", ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    total = goal_log_total(goal.get("id", ""), today)
    target = safe_amount(goal.get("target_amount"))
    label = goal_unit_label(unit)
    if total >= target > 0:
        return style_reply(f"今日目标完成: {goal.get('title', '')} {total:g}/{target:g} {label}。已经够了，剩下算奖励。", "feedback")
    left = max(0, target - total)
    return style_reply(f"今日进度: {goal.get('title', '')} {total:g}/{target:g} {label}，还差 {left:g} {label}。已经开始了，后面补一点就能收口。", "feedback")


def goal_status_lines(period: str = "today") -> list[str]:
    today = datetime.now().date().isoformat()
    lines = []
    for goal in active_goals()[:8]:
        if goal.get("period") != "daily":
            continue
        target = safe_amount(goal.get("target_amount"))
        total = goal_log_total(goal.get("id", ""), today)
        unit = goal_unit_label(goal.get("unit", ""))
        status = "完成" if target > 0 and total >= target else f"还差 {max(0, target - total):g} {unit}"
        lines.append(f"- {goal.get('title', '')}: {total:g}/{target:g} {unit}（{status}）")
    return lines


def due_todo_rows() -> list[dict]:
    today = datetime.now().date().isoformat()
    rows = []
    for row in read_csv_rows(TODOS_CSV):
        if row.get("status") != "pending":
            continue
        due = row.get("due_date", "")
        if not due or due <= today:
            rows.append(row)
    rows.sort(key=lambda row: (row.get("due_date", "9999-99-99"), row.get("created_at", "")))
    return rows


def unified_task_rows() -> list[dict]:
    tasks = []
    for row in due_todo_rows():
        label = f"[待办] {row.get('text', '')}"
        if row.get("due_date"):
            label += f"（{row.get('due_date')}）"
        tasks.append({"kind": "todo", "id": row.get("id", ""), "text": row.get("text", ""), "label": label})
    today = datetime.now().date().isoformat()
    for goal in active_goals():
        if goal.get("period") != "daily":
            continue
        target = safe_amount(goal.get("target_amount"))
        total = goal_log_total(goal.get("id", ""), today)
        unit = goal_unit_label(goal.get("unit", ""))
        status = "完成" if target > 0 and total >= target else f"还差 {max(0, target - total):g} {unit}"
        label = f"[目标] {goal.get('title', '')}: {total:g}/{target:g} {unit}（{status}）"
        tasks.append({"kind": "goal", "id": goal.get("id", ""), "text": goal.get("title") or goal.get("subject", ""), "goal": goal, "label": label})
    return tasks


def unified_task_lines(limit: int = 8) -> list[str]:
    return [f"{index}. {item['label']}" for index, item in enumerate(unified_task_rows()[:limit], 1)]


def task_completion_words(text: str) -> bool:
    if any(word in text for word in ("完成情况", "目标进度", "打卡情况", "还差多少", "完成了吗", "完成了多少")):
        return False
    return any(word in text for word in ("完成", "做完", "搞定", "办完", "打卡", "已做", "做了", "学完", "弄完", "交了", "提交了"))


def task_completion_query(text: str) -> str:
    query = re.sub(r"(我|已经|今天|刚刚|刚才|任务|待办|目标|每日|日常|完成了|完成|做完了|做完|搞定了|搞定|办完了|办完|打卡了|打卡|已做|做了|学完了|学完|弄完了|弄完|交了|提交了|第|个)", "", text)
    query = re.sub(r"\d+(?:\.\d+)?\s*(min|mins|分钟|小时|h|个|页|次|题|公里|km)", "", query, flags=re.I)
    return query.strip(" ：:，,。")


def task_match_score(item: dict, query: str) -> int:
    if not query:
        return 0
    text = (item.get("text") or "").lower().replace(" ", "")
    query_norm = query.lower().replace(" ", "")
    if not text or not query_norm:
        return 0
    if query_norm == text:
        return 100
    if query_norm in text or text in query_norm:
        return 80
    score = 0
    words = re.findall(r"[a-zA-Z]+", query_norm)
    score += sum(20 for word in words if word and word in text)
    for block in re.findall(r"[\u4e00-\u9fa5]{2,}", query_norm):
        seen = set()
        matched_block = False
        max_size = min(5, len(block))
        for size in range(max_size, 1, -1):
            for start in range(0, len(block) - size + 1):
                piece = block[start:start + size]
                if piece in seen:
                    continue
                seen.add(piece)
                if piece in text:
                    score += 20 + size
                    matched_block = True
                    break
            if matched_block:
                break
    return score


def pending_task_store(state: dict) -> dict:
    return state.setdefault("pending_task_completion", {})


def complete_todo_by_id(todo_id: str) -> str | None:
    rows = read_csv_rows(TODOS_CSV)
    target = next((row for row in rows if row.get("id") == todo_id and row.get("status") == "pending"), None)
    if not target:
        return None
    target["status"] = "done"
    target["done_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_csv_rows(TODOS_CSV, ["id", "text", "status", "due_date", "created_at", "done_at"], rows)
    return f"已完成待办: {target.get('text', '')}"


def complete_goal_by_id(goal_id: str, note: str = "") -> str | None:
    goal = next((row for row in active_goals() if row.get("id") == goal_id), None)
    if not goal:
        return None
    today = datetime.now().date().isoformat()
    target = safe_amount(goal.get("target_amount"))
    total = goal_log_total(goal_id, today)
    remaining = max(0, target - total)
    unit = goal.get("unit") or "次"
    if remaining > 0:
        append_csv(GOAL_LOGS_CSV, [goal_id, today, f"{remaining:g}", unit, note or "完成目标", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        total += remaining
    label = goal_unit_label(unit)
    return style_reply(f"今日目标完成: {goal.get('title', '')} {total:g}/{target:g} {label}。", "feedback")


def complete_unified_task(item: dict, note: str = "") -> str:
    if item.get("kind") == "todo":
        return complete_todo_by_id(item.get("id", "")) or "这条待办已经不在待办列表里了。"
    if item.get("kind") == "goal":
        return complete_goal_by_id(item.get("id", ""), note) or "这个目标暂时没找到。"
    return "这个任务暂时没法完成。"


def queue_task_completion_confirmation(chat_id: int | None, candidates: list[dict]) -> str:
    lines = ["你想标记哪一项完成？"]
    for index, item in enumerate(candidates[:6], 1):
        lines.append(f"{index}. {item.get('label', '')}")
    lines.append("回复编号即可，或回复“取消”。")
    if chat_id is not None:
        state = read_state()
        pending_task_store(state)[str(chat_id)] = {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": [{"kind": item.get("kind"), "id": item.get("id"), "label": item.get("label", "")} for item in candidates[:6]],
        }
        set_pending_center(state, chat_id, "task_completion")
        write_state(state)
    return "\n".join(lines)


def handle_pending_task_completion(text: str, chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    state = read_state()
    pending = pending_task_store(state)
    item = pending.get(str(chat_id))
    if not item:
        return None
    if text.strip() in {"取消", "算了", "不用"}:
        pending.pop(str(chat_id), None)
        write_state(state)
        return "好，这次不标记完成。"
    if not text.strip().isdigit():
        return None
    index = int(text.strip()) - 1
    items = item.get("items") or []
    if not (0 <= index < len(items)):
        return "编号没对上，你可以重新发一个列表里的数字。"
    selected = items[index]
    pending.pop(str(chat_id), None)
    write_state(state)
    return complete_unified_task(selected)




def task_completion_index_from_text(text: str) -> int | None:
    if not task_completion_words(text):
        return None
    stripped = text.strip()
    patterns = (
        r"(?:\u5b8c\u6210|\u505a\u5b8c|\u641e\u5b9a|\u6253\u5361|\u4ea4\u4e86|\u63d0\u4ea4\u4e86)?\s*\u7b2c\s*(\d{1,2}|[\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341])\s*(?:\u4e2a|\u6761|\u9879)?\s*(?:\u4ee3\u529e|\u5f85\u529e|\u4efb\u52a1|\u76ee\u6807)?",
        r"(?:\u4ee3\u529e|\u5f85\u529e|\u4efb\u52a1|\u76ee\u6807)\s*(\d{1,2}|[\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341])\s*(?:\u5b8c\u6210|\u505a\u5b8c|\u641e\u5b9a|\u6253\u5361)?",
    )
    for pattern in patterns:
        match = re.search(pattern, stripped)
        if not match:
            continue
        value = match.group(1)
        if value.isdigit():
            return int(value)
        return chinese_number_to_int(value)
    return None


def is_complete_all_tasks_request(text: str) -> bool:
    if not task_completion_words(text):
        return False
    all_words = ("\u5168\u90e8", "\u5168\u90fd", "\u6240\u6709", "\u90fd", "\u5168\u6e05", "\u6e05\u7a7a", "\u4e00\u952e")
    task_words = ("\u4ee3\u529e", "\u5f85\u529e", "\u4efb\u52a1", "\u76ee\u6807", "\u4eca\u65e5\u4efb\u52a1")
    if not any(word in text for word in all_words):
        return False
    if any(word in text for word in task_words):
        return True
    blockers = (has_expense_hint(text), has_income_hint(text), has_weather_hint(text), is_delete_request(text), is_explicit_note_request(text))
    return not any(blockers) and bool(unified_task_rows())


def complete_task_by_visible_index(index: int, note: str = "") -> str:
    tasks = unified_task_rows()
    if not tasks:
        return "\u73b0\u5728\u6ca1\u6709\u5f85\u5b8c\u6210\u7684\u4eca\u65e5\u4efb\u52a1\u3002"
    if not (1 <= index <= len(tasks)):
        return f"\u7b2c {index} \u4e2a\u4eca\u65e5\u4efb\u52a1\u6ca1\u627e\u5230\u3002\u4f60\u53ef\u4ee5\u53d1\u201c\u4eca\u65e5\u4efb\u52a1\u201d\u5148\u770b\u5217\u8868\u3002"
    return complete_unified_task(tasks[index - 1], note)


def complete_all_unified_tasks(text: str = "") -> str:
    tasks = unified_task_rows()
    if not tasks:
        return "\u73b0\u5728\u6ca1\u6709\u5f85\u5b8c\u6210\u7684\u4eca\u65e5\u4efb\u52a1\u3002"
    replies = []
    for item in tasks:
        reply = complete_unified_task(item, text)
        if reply:
            replies.append(reply)
    if not replies:
        return "\u6ca1\u6709\u627e\u5230\u53ef\u5b8c\u6210\u7684\u4eca\u65e5\u4efb\u52a1\u3002"
    return "\u5df2\u5b8c\u6210\u5168\u90e8\u4eca\u65e5\u4efb\u52a1\uff1a\n" + "\n".join(f"- {reply}" for reply in replies)


def natural_todo_due_date(text: str) -> str:
    today = datetime.now().date()
    if "\u540e\u5929" in text:
        return (today + timedelta(days=2)).isoformat()
    if "\u660e\u5929" in text:
        return (today + timedelta(days=1)).isoformat()
    if "\u4eca\u5929" in text or "\u4eca\u665a" in text:
        return today.isoformat()
    return ""


def natural_todo_items_from_text(text: str) -> list[str]:
    if any(word in text for word in ("\u5f85\u529e", "\u4efb\u52a1\u5217\u8868", "\u4eca\u65e5\u4efb\u52a1", "\u7b2c\u4e00\u4e2a", "\u7b2c\u4e8c\u4e2a", "\u7b2c\u4e09\u4e2a", "\u7b2c1", "\u7b2c2", "\u7b2c3")):
        return []
    if not any(word in text for word in ("\u4eca\u5929", "\u660e\u5929", "\u540e\u5929", "\u4eca\u665a")):
        return []
    if not any(word in text for word in ("\u8981", "\u9700\u8981", "\u5f97", "\u5fc5\u987b", "\u8ba1\u5212", "\u5b89\u6392")):
        return []
    if not any(word in text for word in ("\u5b8c\u6210", "\u505a\u5b8c", "\u641e\u5b9a", "\u5f04\u5b8c", "\u5904\u7406\u5b8c", "\u5199\u5b8c", "\u6d4b\u8bd5\u5b8c")):
        return []
    if has_expense_hint(text) or has_income_hint(text) or has_weather_hint(text):
        return []

    parts = re.split(r"[\uFF0C,\u3002\uFF1B;\u3001]+", text)
    items: list[str] = []
    for part in parts:
        if not part.strip():
            continue
        if not any(word in part for word in ("\u5b8c\u6210", "\u505a\u5b8c", "\u641e\u5b9a", "\u5f04\u5b8c", "\u5904\u7406\u5b8c", "\u5199\u5b8c", "\u6d4b\u8bd5\u5b8c")):
            continue
        cleaned = part
        cleaned = re.sub(r"(\u4eca\u5929|\u660e\u5929|\u540e\u5929|\u4eca\u665a|\u6211|\u81ea\u5df1|\u5148|\u7136\u540e|\u987a\u4fbf)", "", cleaned)
        cleaned = re.sub(r"(\u9700\u8981|\u5fc5\u987b|\u8ba1\u5212|\u5b89\u6392|\u8981\u628a|\u8981\u5c06|\u628a|\u5c06|\u4e5f\u8981|\u90fd\u8981|\u8981|\u5f97)", "", cleaned)
        cleaned = re.sub(r"(\u5b8c\u6210|\u505a\u5b8c|\u641e\u5b9a|\u5f04\u5b8c|\u5904\u7406\u5b8c|\u5199\u5b8c|\u6d4b\u8bd5\u5b8c)+$", "", cleaned)
        cleaned = cleaned.strip(" \uFF1A:\uFF0C,\u3002\uFF1B;\u3001")
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def natural_todo_creation_reply(text: str) -> str | None:
    items = natural_todo_items_from_text(text)
    if not items:
        return None
    due_date = natural_todo_due_date(text)
    return save_todo_action({"type": "todo", "items": [{"text": item, "due_date": due_date} for item in items]})


def complete_task_from_text(text: str, chat_id: int | None) -> str | None:
    if natural_todo_items_from_text(text):
        return None
    if not task_completion_words(text):
        return None
    if is_complete_all_tasks_request(text):
        return complete_all_unified_tasks(text)
    visible_index = task_completion_index_from_text(text)
    if visible_index:
        return complete_task_by_visible_index(visible_index, text)
    if has_quantity_target(text):
        return None
    query = task_completion_query(text)
    tasks = unified_task_rows()
    if not tasks:
        return "\u73b0\u5728\u6ca1\u6709\u5f85\u5b8c\u6210\u7684\u4eca\u65e5\u4efb\u52a1\u3002\u4f60\u60f3\u65b0\u589e\u5f85\u529e\u7684\u8bdd\uff0c\u53ef\u4ee5\u8bf4\uff1a\u4eca\u5929\u8981\u628a\u524d\u540e\u7aef\u6d4b\u8bd5\u5b8c\u6210\u3002"
    scored = [(task_match_score(item, query), item) for item in tasks]
    matches = [item for score, item in scored if score > 0]
    if len(matches) == 1:
        return complete_unified_task(matches[0], text)
    if len(matches) > 1:
        top_score = max(score for score, _ in scored)
        top = [item for score, item in scored if score == top_score and score > 0]
        if len(top) == 1 and top_score >= 60:
            return complete_unified_task(top[0], text)
        return queue_task_completion_confirmation(chat_id, matches)
    if query:
        return "\u6ca1\u627e\u5230\u5339\u914d\u7684\u4eca\u65e5\u4efb\u52a1\u3002\u4f60\u53ef\u4ee5\u53d1\u201c\u4eca\u65e5\u4efb\u52a1\u201d\u5148\u770b\u5217\u8868\uff0c\u6216\u8bf4\u201c\u6dfb\u52a0\u5f85\u529e ...\u201d\u3002"
    return queue_task_completion_confirmation(chat_id, tasks)

def repeat_period_from_text(text: str) -> str | None:
    if any(word in text for word in ("每月", "每个月", "每个月的")):
        return "monthly"
    if any(word in text for word in ("每周", "每星期", "每个星期")):
        return "weekly"
    if any(word in text for word in ("每天", "每日", "每晚", "每早", "天天")):
        return "daily"
    return None


def has_quantity_target(text: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?\s*(min|mins|分钟|小时|h|个|页|次|题|公里|km)", text, re.I))


def has_clock_time(text: str) -> bool:
    return bool(re.search(r"(凌晨|早上|上午|中午|下午|晚上|今晚)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*点|\d{1,2}[:：]\d{2}", text))


def routine_activity_words(text: str) -> bool:
    words = (
        "学习", "学", "复习", "练", "练习", "背", "阅读", "读书", "读", "写代码", "代码", "算法",
        "python", "Python", "英语", "单词", "课程", "运动", "跑步", "健身", "起床", "睡觉", "早睡",
        "整理", "打扫", "收拾", "记账", "写日记", "打卡",
    )
    return any(word in text for word in words)


def clean_routine_subject(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,。；;]", text.strip()) if part.strip()]
    subject = next((part for part in parts if repeat_period_from_text(part) or routine_activity_words(part)), text.strip())
    subject = re.sub(r"(提醒我|叫我|通知我|提醒|我想|我要|我希望|希望|请|帮我|给我|坚持|打卡|任务|目标|计划|一下|吧)", "", subject, flags=re.I)
    subject = re.sub(r"(每天|每日|每晚|每早|天天|每周|每星期|每个星期|每月|每个月)", "", subject)
    subject = re.sub(r"(凌晨|早上|上午|中午|下午|晚上|今晚)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*点(?:半|\d{1,2}分?)?", "", subject)
    subject = re.sub(r"\d{1,2}[:：]\d{2}", "", subject)
    return subject.strip(" ：:，,。 的了") or "这件事"


def is_ambiguous_routine_intent(text: str) -> bool:
    stripped = text.strip()
    if is_question_like(stripped) or is_delete_request(stripped) or is_explicit_note_request(stripped):
        return False
    if has_expense_hint(stripped) or has_income_hint(stripped) or has_weather_hint(stripped) or has_study_plan_hint(stripped):
        return False
    if parse_goal_target(stripped) or has_quantity_target(stripped):
        return False
    period = repeat_period_from_text(stripped)
    if not period:
        return False
    if not routine_activity_words(stripped):
        return False
    if has_clock_time(stripped) and any(word in stripped for word in ("提醒", "叫我", "通知", "闹钟")):
        return False
    return True


def pending_routine_store(state: dict) -> dict:
    return state.setdefault("pending_routine_confirmations", {})


def routine_confirmation_prompt(text: str, chat_id: int | None) -> str | None:
    if not is_ambiguous_routine_intent(text):
        return None
    period = repeat_period_from_text(text) or "daily"
    title = clean_routine_subject(text)
    if chat_id is not None:
        state = read_state()
        pending_routine_store(state)[str(chat_id)] = {
            "text": text,
            "title": title,
            "period": period,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        set_pending_center(state, chat_id, "routine")
        write_state(state)
    period_label = {"daily": "每天", "weekly": "每周", "monthly": "每月"}.get(period, "每天")
    return (
        f"这个我能按两种方式处理：\n"
        f"1. 设为今日任务：{period_label}{title}，之后可以打卡完成\n"
        f"2. 设为重复提醒：{period_label}提醒你{title}\n"
        "回复 1/任务，或 2/提醒。回复“不用”取消。"
    )


def default_repeat_remind_at(period: str) -> datetime:
    now = datetime.now()
    remind_at = datetime.combine(now.date(), datetime.min.time()).replace(hour=9, minute=0)
    if remind_at <= now:
        if period == "weekly":
            remind_at += timedelta(days=7)
        elif period == "monthly":
            remind_at = add_month(remind_at)
        else:
            remind_at += timedelta(days=1)
    return remind_at


def routine_reminder_action(text: str, title: str, period: str) -> dict:
    remind_at = parse_time_expression(text) or default_repeat_remind_at(period)
    repeat = period if period in {"daily", "weekly", "monthly"} else "daily"
    return {"type": "reminder", "items": [{"remind_at": remind_at.strftime("%Y-%m-%d %H:%M:%S"), "text": title, "repeat": repeat}]}


def save_routine_task(text: str, title: str, period: str, chat_id: int | None) -> str:
    goal, created = upsert_goal({
        "title": title,
        "subject": title,
        "target_amount": 1,
        "unit": "次",
        "period": period,
        "reminder_time": "",
    }, chat_id)
    period_label = {"daily": "每天", "weekly": "每周", "monthly": "每月"}.get(goal.get("period"), "每天")
    verb = "已设为今日任务" if created else "已更新今日任务"
    return f"{verb}: {period_label}{goal.get('title', '')}。完成后可以说：完成{goal.get('title', '')}。"


def handle_pending_routine_confirmation(config: dict, text: str, chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    state = read_state()
    pending = pending_routine_store(state)
    item = pending.get(str(chat_id))
    if not item:
        return None
    try:
        created_at = datetime.strptime(item.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        created_at = datetime.now()
    if datetime.now() - created_at > timedelta(minutes=30):
        pending.pop(str(chat_id), None)
        write_state(state)
        return None
    stripped = text.strip()
    if stripped in {"取消", "不用", "算了", "不设", "先不"}:
        pending.pop(str(chat_id), None)
        write_state(state)
        return "好，这次不设置。"
    title = item.get("title") or clean_routine_subject(item.get("text", ""))
    period = item.get("period") or repeat_period_from_text(item.get("text", "")) or "daily"
    if stripped in {"1", "任务", "设为任务", "今日任务", "每日任务", "打卡", "目标"}:
        pending.pop(str(chat_id), None)
        write_state(state)
        return save_routine_task(item.get("text", ""), title, period, chat_id)
    if stripped in {"2", "提醒", "设为提醒", "重复提醒", "闹钟"}:
        pending.pop(str(chat_id), None)
        write_state(state)
        return save_reminder(routine_reminder_action(item.get("text", ""), title, period), chat_id)
    return None

def goal_status_reply() -> str:
    lines = unified_task_lines()
    if not lines:
        return "现在还没有今日任务。你可以说: 每天学习python 15min，或 添加待办 明天交作业。"
    return "今日任务:\n" + "\n".join(lines)


def goal_query_reply(text: str) -> str | None:
    if any(word in text for word in ("目标情况", "今日目标", "今日任务", "任务情况", "任务进度", "目标进度", "目标列表", "打卡情况", "完成情况")):
        return goal_status_reply()
    return None


def history_keyword(text: str) -> str:
    english = re.findall(r"[a-zA-Z]+", text)
    if english:
        return english[-1]
    match = re.search(r"(?:学|学习|开始|说|提到)([\u4e00-\u9fa5A-Za-z0-9]{2,12})", text)
    if match:
        return match.group(1)
    words = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
    stop = {"最近", "什么时候", "开始", "上次", "因为", "什么", "完成", "情况", "历史", "记录"}
    for word in reversed(words):
        if word not in stop:
            return word
    return ""


def history_search_reply(text: str) -> str | None:
    if any(word in text for word in ("目标情况", "今日目标", "今日任务", "任务情况", "任务进度", "目标进度", "目标列表", "打卡情况", "完成情况")):
        return goal_status_reply()
    if any(word in text for word in ("花哪", "花到哪", "花哪里", "钱花", "都花")):
        start, end, title = period_range("week" if any(word in text for word in ("本周", "这周")) else "month")
        rows = rows_between(EXPENSES_CSV, start, end)
        if not rows:
            return f"{title}还没有消费记录。"
        totals = total_by(rows, "category")
        lines = [f"{title}钱主要花在:"]
        for category, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:5]:
            lines.append(f"- {category}: {amount:g} 元")
        return "\n".join(lines)
    if "心情最差" in text or "情绪最差" in text:
        start, end, title = period_range("week" if any(word in text for word in ("本周", "这周")) else "month")
        rows = rows_between(MOODS_CSV, start, end)
        if not rows:
            return f"{title}没有心情记录。"
        worst = min(rows, key=lambda row: safe_int(row.get("score")))
        return f"{title}心情最低的一次: {worst.get('date', '')} {worst.get('mood', '')}（{safe_int(worst.get('score')):+d}），原因: {worst.get('reason') or worst.get('note') or '未记录'}"
    if "上次" in text:
        keyword = history_keyword(text)
        rows = list(reversed(read_csv_rows(MOODS_CSV) + read_csv_rows(NOTES_CSV)))
        for row in rows:
            blob = " ".join(str(value) for value in row.values())
            if keyword and keyword in blob:
                return f"上次相关记录: {row.get('date', '')} {row.get('mood') or row.get('content') or row.get('reason') or blob}"
        return "没找到上次相关记录。"
    if "什么时候开始" in text or "哪天开始" in text:
        keyword = history_keyword(text)
        candidates = []
        for path, fields in ((GOALS_CSV, ("created_at", "title", "subject")), (GOAL_LOGS_CSV, ("date", "note")), (NOTES_CSV, ("date", "content")), (TODOS_CSV, ("created_at", "text"))):
            for row in read_csv_rows(path):
                blob = " ".join(str(row.get(field, "")) for field in fields)
                if keyword and keyword.lower() in blob.lower():
                    date_text = row.get("date") or str(row.get("created_at", ""))[:10]
                    candidates.append((date_text, blob))
        candidates = [item for item in candidates if item[0]]
        if not candidates:
            return "没翻到明确的开始记录。之后你设成目标或打卡，我就能追踪得更准。"
        candidates.sort(key=lambda item: item[0])
        return f"我翻到最早大概是 {candidates[0][0]}: {candidates[0][1]}"
    return None

def expense_anomaly_for_item(date: str, name: str, amount: float, category: str, history_rows: list[dict]) -> list[str]:
    if amount <= 0:
        return []
    same_category = [safe_amount(row.get("amount")) for row in history_rows if row.get("category") == category and safe_amount(row.get("amount")) > 0]
    lines = []
    if len(same_category) >= 4:
        avg = sum(same_category) / len(same_category)
        previous_max = max(same_category)
        if amount >= max(50, avg * 2.4) and amount >= previous_max * 1.15:
            lines.append(f"这笔{name or category}比你平时的{category}高不少：{amount:g} 元，历史均值约 {avg:g} 元。")
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        day = datetime.now().date()
    today_total = amount + sum(
        safe_amount(row.get("amount"))
        for row in history_rows
        if row.get("category") == category and row.get("date") == day.isoformat()
    )
    daily_totals = {}
    for row in history_rows:
        if row.get("category") != category or row.get("date") == day.isoformat():
            continue
        try:
            row_day = datetime.strptime(row.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if day - timedelta(days=21) <= row_day < day:
            daily_totals[row_day.isoformat()] = daily_totals.get(row_day.isoformat(), 0.0) + safe_amount(row.get("amount"))
    if len(daily_totals) >= 5:
        avg_day = sum(daily_totals.values()) / len(daily_totals)
        if today_total >= max(80, avg_day * 2.5):
            lines.append(f"今天{category}已经到 {today_total:g} 元，明显高于近期开销节奏。")
    return lines[:2]


def expense_anomaly_notice(lines: list[str]) -> str:
    unique = []
    for line in lines:
        if line and line not in unique:
            unique.append(line)
    if not unique:
        return ""
    return "\n消费提醒：\n" + "\n".join(f"- {line}" for line in unique[:3])


def period_summary(config: dict, period: str) -> str:
    start, end, title = period_range(period)
    expense_rows = rows_between(EXPENSES_CSV, start, end)
    income_rows = rows_between(INCOME_CSV, start, end)
    note_rows = rows_between(NOTES_CSV, start, end)
    mood_rows = rows_between(MOODS_CSV, start, end)
    expense_total = sum(safe_amount(row.get("amount")) for row in expense_rows)
    income_total = sum(safe_amount(row.get("amount")) for row in income_rows)

    lines = [f"{title}总结（{start.isoformat()} 至 {end.isoformat()}）"]
    lines.append(f"开销：{expense_total:g} 元")
    lines.append(f"收入：{income_total:g} 元")
    lines.append(f"净额：{income_total - expense_total:g} 元")

    expense_by_category = total_by(expense_rows, "category")
    if expense_by_category:
        lines.append("开销分类：")
        for category, amount in sorted(expense_by_category.items(), key=lambda item: item[1], reverse=True)[:6]:
            lines.append(f"- {category or '其他'}: {amount:g} 元")
    else:
        lines.append("开销分类：暂无记录")

    income_by_category = total_by(income_rows, "category")
    if income_by_category:
        lines.append("收入来源：")
        for category, amount in sorted(income_by_category.items(), key=lambda item: item[1], reverse=True)[:6]:
            lines.append(f"- {category or '其他'}: {amount:g} 元")

    if mood_rows:
        scores = [safe_int(row.get("score")) for row in mood_rows]
        avg_score = sum(scores) / len(scores)
        mood_words = "、".join(row.get("mood", "") for row in mood_rows[-3:] if row.get("mood"))
        reasons = "、".join(row.get("reason", "") for row in mood_rows[-3:] if row.get("reason"))
        lines.append(f"心理状况：平均 {avg_score:.1f}，最近关键词：{mood_words or '未提取'}")
        if reasons:
            lines.append(f"可能影响因素：{reasons}")
    elif period == "today":
        lines.append("心理状况：今天还没有记录心情。你现在状态怎么样？可以直接回我一句。")
    else:
        lines.append("心理状况：这段时间没有心情记录。")

    if note_rows:
        lines.append("生活事项：")
        for row in note_rows[-5:]:
            lines.append(f"- {row.get('date', '')} {row.get('content', '')}")

    if period == "today" and config.get("default_city"):
        lines.append("天气参考：")
        lines.append(weather_answer(config, "今天的天气怎么样"))
    return "\n".join(lines)


def daily_report_kind_from_text(text: str) -> str | None:
    raw = text.strip().lower()
    if raw in {"/morning", "晨报", "早报", "每日晨报", "今日晨报"} or "晨报" in text or "早报" in text:
        return "morning"
    if raw in {"/evening", "晚报", "每日晚报", "今晚复盘"} or "晚报" in text or "晚间总结" in text:
        return "evening"
    return None


def mood_trend_period_from_text(text: str) -> str | None:
    if not any(word in text for word in ("心情趋势", "情绪趋势", "心理趋势", "状态趋势", "mood trend")):
        return None
    if any(word in text for word in ("今年", "年度", "全年", "一年")):
        return "year"
    if any(word in text for word in ("本周", "这周", "一周", "最近七天")):
        return "week"
    return "month"


def mood_keywords(rows: list[dict], limit: int = 5) -> list[str]:
    text = " ".join((row.get("reason", "") + " " + row.get("note", "")) for row in rows)
    words = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
    stop = {"今天", "昨天", "感觉", "因为", "但是", "有点", "还是", "没有", "已经", "自己", "一下", "心情", "情绪", "记录"}
    counts = {}
    for word in words:
        if word in stop or len(word) > 8:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def mood_trend_reply(period: str = "month") -> str:
    period = normalize_period(period, "month")
    start, end, title = period_range(period)
    rows = rows_between(MOODS_CSV, start, end)
    if not rows:
        return f"{title}还没有心情记录。你可以直接发一句：今天有点累，但还撑得住。"
    rows.sort(key=lambda row: (row.get("date", ""), row.get("created_at", "")))
    scores = [safe_int(row.get("score")) for row in rows]
    avg_score = sum(scores) / len(scores)
    first_half = scores[:max(1, len(scores) // 2)]
    second_half = scores[max(1, len(scores) // 2):] or scores
    delta = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))
    if delta > 0.4:
        trend = "在回升"
    elif delta < -0.4:
        trend = "有点下滑"
    else:
        trend = "整体比较平稳"
    labels = {-2: "低", -1: "偏低", 0: "平", 1: "好", 2: "很好"}
    recent = " -> ".join(labels.get(max(-2, min(2, score)), "平") for score in scores[-7:])
    keywords = mood_keywords(rows)
    negative_days = [row.get("date", "") for row in rows if safe_int(row.get("score")) < 0]
    expense_rows = rows_between(EXPENSES_CSV, start, end)
    expense_by_date = {}
    for row in expense_rows:
        expense_by_date[row.get("date", "")] = expense_by_date.get(row.get("date", ""), 0.0) + safe_amount(row.get("amount"))
    negative_spend = [expense_by_date.get(day, 0.0) for day in negative_days if expense_by_date.get(day, 0.0) > 0]
    lines = [f"{title}心情趋势："]
    lines.append(f"- 平均分：{avg_score:.1f}（-2 到 +2），趋势：{trend}")
    lines.append(f"- 最近轨迹：{recent}")
    lines.append(f"- 高频线索：{'、'.join(keywords) if keywords else '还不明显'}")
    if negative_spend:
        lines.append(f"- 低落日也有消费记录，平均约 {sum(negative_spend) / len(negative_spend):g} 元，可以留意压力消费。")
    if rows[-1].get("reason") or rows[-1].get("note"):
        lines.append(f"- 最近一次：{rows[-1].get('mood', '')}，{rows[-1].get('reason') or rows[-1].get('note', '')}")
    return "\n".join(lines)


def today_pending_reminders() -> list[str]:
    today = datetime.now().date().isoformat()
    rows = []
    for row in read_csv_rows(REMINDERS_CSV):
        if row.get("status") != "pending":
            continue
        remind_at = row.get("remind_at", "")
        if remind_at.startswith(today):
            rows.append(row)
    rows.sort(key=lambda row: row.get("remind_at", ""))
    return [f"- {row.get('remind_at', '')[11:16]} {row.get('text', '')}" for row in rows[:6]]


def due_todo_lines() -> list[str]:
    return [f"- {row.get('text', '')}{'（' + row.get('due_date') + '）' if row.get('due_date') else ''}" for row in due_todo_rows()[:6]]


def budget_snapshot_lines(period: str = "month") -> list[str]:
    budgets = [row for row in read_csv_rows(BUDGETS_CSV) if row.get("period") == period]
    if not budgets:
        return []
    start, end, _ = period_range(period)
    expenses = rows_between(EXPENSES_CSV, start, end)
    lines = []
    for row in budgets[:4]:
        category = row.get("category") or "总额"
        limit = safe_amount(row.get("amount"))
        if limit <= 0:
            continue
        if category == "总额":
            used = sum(safe_amount(item.get("amount")) for item in expenses)
        else:
            used = sum(safe_amount(item.get("amount")) for item in expenses if item.get("category") == category)
        lines.append(f"- {category}: {used:g}/{limit:g} 元（{used / limit:.0%}）")
    return lines


def weather_brief(config: dict) -> str:
    if not config.get("default_city"):
        return ""
    try:
        return weather_answer(config, "今天的天气怎么样").split("\n", 1)[0]
    except Exception:
        return "天气暂时没取到，晚点再问我也行。"


def daily_report_reply(config: dict, kind: str) -> str:
    kind = "evening" if kind == "evening" else "morning"
    if kind == "morning":
        lines = ["早上好，今天先看这几件事："]
        weather = weather_brief(config)
        if weather:
            lines.append(f"天气：{weather}")
        date_notice = important_date_notice_today()
        if date_notice:
            lines.append(date_notice)
        reminders = today_pending_reminders()
        lines.append("今日提醒：")
        lines.extend(reminders or ["- 暂无固定提醒"])
        task_lines = unified_task_lines()
        lines.append("今日任务：")
        lines.extend(task_lines or ["- 暂无到期待办或每日目标"])
        budget_lines = budget_snapshot_lines("month")
        if budget_lines:
            lines.append("本月预算：")
            lines.extend(budget_lines)
        lines.append("今天先抓住一件最重要的小事就够了。")
        return "\n".join(lines)
    lines = ["晚报来了，给今天收个尾：", period_summary(config, "today")]
    task_lines = unified_task_lines()
    if task_lines:
        lines.append("还没收尾的今日任务：")
        lines.extend(task_lines[:8])
        if any("还差" in line for line in task_lines):
            lines.append("没完成也不是失败，明天继续从最小一格接上。")
    if not rows_between(MOODS_CSV, datetime.now().date(), datetime.now().date()):
        lines.append("今天还没记录心情。可以回我一句：今天状态怎么样。")
    return "\n".join(lines)


def parse_report_time(value: str, default: str) -> tuple[int, int]:
    match = re.match(r"^(\d{1,2}):(\d{2})$", str(value or ""))
    if not match:
        value = default
        match = re.match(r"^(\d{1,2}):(\d{2})$", value)
    hour = max(0, min(23, int(match.group(1))))
    minute = max(0, min(59, int(match.group(2))))
    return hour, minute


def report_time_in_window(now: datetime, value: str, default: str, window_minutes: int = 90) -> bool:
    hour, minute = parse_report_time(value, default)
    target = hour * 60 + minute
    current = now.hour * 60 + now.minute
    return 0 <= current - target <= window_minutes


def remember_chat(state: dict, chat_id: int) -> bool:
    chats = state.setdefault("known_chat_ids", [])
    key = str(chat_id)
    if key in [str(item) for item in chats]:
        return False
    chats.append(key)
    return True


def daily_report_targets(state: dict, config: dict) -> list[int]:
    raw_ids = list(state.get("known_chat_ids") or []) + list(config.get("daily_report_chat_ids") or [])
    targets = []
    for value in raw_ids:
        try:
            chat_id = int(value)
        except (TypeError, ValueError):
            continue
        if chat_id not in targets:
            targets.append(chat_id)
    return targets


def dispatch_goal_reminders(token: str, config: dict) -> None:
    state = read_state()
    now = datetime.now()
    today = now.date().isoformat()
    sent = state.setdefault("goal_reminders_sent", {})
    changed = False
    fallback_targets = daily_report_targets(state, config)
    for goal in active_goals():
        if goal.get("period") != "daily" or not goal.get("reminder_time"):
            continue
        if not report_time_in_window(now, goal.get("reminder_time", ""), goal.get("reminder_time", ""), 90):
            continue
        goal_id = goal.get("id", "")
        if sent.get(goal_id) == today:
            continue
        target = safe_amount(goal.get("target_amount"))
        total = goal_log_total(goal_id, today)
        if target > 0 and total >= target:
            sent[goal_id] = today
            changed = True
            continue
        targets = []
        try:
            if goal.get("chat_id"):
                targets.append(int(goal.get("chat_id")))
        except (TypeError, ValueError):
            pass
        targets.extend(chat_id for chat_id in fallback_targets if chat_id not in targets)
        if not targets:
            continue
        unit = goal_unit_label(goal.get("unit", ""))
        message = f"目标提醒：今天{goal.get('title', '')} {total:g}/{target:g} {unit}。完成后直接回：我{goal.get('title', '')}学了10min。"
        for chat_id in targets:
            send_message(token, chat_id, message)
        sent[goal_id] = today
        changed = True
    if changed:
        write_state(state)

def dispatch_daily_reports(token: str, config: dict) -> None:
    if not config.get("daily_reports_enabled", True):
        return
    state = read_state()
    targets = daily_report_targets(state, config)
    if not targets:
        return
    now = datetime.now()
    today = now.date().isoformat()
    sent = state.setdefault("daily_reports_sent", {})
    changed = False
    jobs = [
        ("morning", "morning_report_time", "08:00", 120),
        ("evening", "evening_report_time", "22:30", 150),
    ]
    for kind, key, default, window in jobs:
        if not report_time_in_window(now, config.get(key), default, window):
            continue
        for chat_id in targets:
            chat_key = str(chat_id)
            chat_sent = sent.setdefault(chat_key, {})
            if chat_sent.get(kind) == today:
                continue
            send_message(token, chat_id, daily_report_reply(config, kind))
            chat_sent[kind] = today
            changed = True
    if changed:
        write_state(state)


def period_range(period: str):
    today = datetime.now().date()
    if period == "today":
        return today, today, "今日"
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, today, "本周"
    if period == "year":
        start = today.replace(month=1, day=1)
        return start, today, "今年"
    start = today.replace(day=1)
    return start, today, "本月"


def rows_between(path: Path, start, end) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                row_date = datetime.strptime(row.get("date", ""), "%Y-%m-%d").date()
            except ValueError:
                continue
            if start <= row_date <= end:
                rows.append(row)
    return rows


def total_by(rows: list[dict], field: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        key = row.get(field) or "其他"
        totals[key] = totals.get(key, 0.0) + safe_amount(row.get("amount"))
    return totals


def safe_amount(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def finance_totals(rows: list[dict], kind: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        if kind == "expense":
            key = normalize_expense_category(row.get("item", ""), row.get("category", "其他"))
        else:
            key = normalize_income_category(row.get("source", ""), row.get("category", "其他"))
        amount = safe_amount(row.get("amount"))
        if amount <= 0:
            continue
        totals[key] = totals.get(key, 0.0) + amount
    return totals


def compact_totals(totals: dict[str, float], limit: int = 6) -> list[tuple[str, float]]:
    items = [(name or "其他", amount) for name, amount in totals.items() if amount > 0]
    items.sort(key=lambda item: item[1], reverse=True)
    if len(items) <= limit:
        return items
    head = items[: limit - 1]
    other_total = sum(amount for _, amount in items[limit - 1:])
    head.append(("其他合计", other_total))
    return head


def chart_period_from_text(text: str) -> str | None:
    raw = text.strip()
    lowered = raw.lower()
    finance_words = ("收入", "支出", "收支", "开销", "花销", "消费", "账单", "总开销", "总花销", "花钱", "花费")
    chart_words = ("图", "图表", "饼图", "pie", "占比", "比例", "可视化", "统计图")
    year_words = ("今年", "年度", "全年", "每年", "年")
    month_words = ("本月", "这个月", "这月", "月度", "每月", "月")
    if lowered in {"/chart", "/charts", "/chart_month", "/month_chart"}:
        return "month"
    if lowered in {"/chart year", "/chart_year", "/year_chart"}:
        return "year"
    if any(word in raw for word in ("今年收支图", "年度收支图", "全年收支图", "年收支图", "今年收入图", "今年支出图", "今年开销图", "年度开销图", "全年开销图", "今年消费图", "年度消费占比", "全年花钱占比")):
        return "year"
    if any(word in raw for word in chart_words) and any(word in raw for word in year_words) and any(word in raw for word in finance_words):
        return "year"
    if any(word in raw for word in ("本月收支图", "月度收支图", "这个月收支图", "月收支图", "本月收入图", "本月支出图", "本月开销图", "这个月开销图", "月度开销图", "本月消费图", "这个月消费图", "总开销图", "开销图", "消费图", "账单图", "收支图", "消费占比", "支出占比", "花钱占比")):
        return "month"
    if any(word in raw for word in chart_words) and any(word in raw for word in month_words) and any(word in raw for word in finance_words):
        return "month"
    return None


def chart_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = []
    if bold:
        candidates.extend(["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"])
    candidates.extend(["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/arial.ttf"])
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_width(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def draw_centered(draw, xy: tuple[int, int], text: str, font, fill: str) -> None:
    x, y = xy
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)


def draw_finance_panel(draw, bounds: tuple[int, int, int, int], title: str, totals: list[tuple[str, float]], total: float, colors: list[str], fonts: dict) -> None:
    x1, y1, x2, y2 = bounds
    draw.rounded_rectangle(bounds, radius=24, fill="#FFFFFF", outline="#E2E6EF", width=2)
    draw.text((x1 + 32, y1 + 26), title, font=fonts["panel_title"], fill="#20242A")
    draw.text((x1 + 32, y1 + 68), f"合计 {total:g} 元", font=fonts["small"], fill="#667085")

    pie_box = (x1 + 56, y1 + 128, x1 + 356, y1 + 428)
    if total <= 0 or not totals:
        draw.ellipse(pie_box, fill="#EEF1F6", outline="#D9DEE8", width=2)
        draw_centered(draw, ((pie_box[0] + pie_box[2]) // 2, pie_box[1] + 126), "暂无记录", fonts["small"], "#667085")
        return

    start_angle = -90
    for index, (_, amount) in enumerate(totals):
        extent = 360 * amount / total
        end_angle = start_angle + extent
        draw.pieslice(pie_box, start=start_angle, end=end_angle, fill=colors[index % len(colors)], outline="#FFFFFF", width=3)
        start_angle = end_angle
    draw.ellipse(pie_box, outline="#FFFFFF", width=3)

    legend_x = x1 + 405
    legend_y = y1 + 126
    for index, (name, amount) in enumerate(totals):
        color = colors[index % len(colors)]
        y = legend_y + index * 52
        percent = amount / total * 100 if total else 0
        draw.rounded_rectangle((legend_x, y + 6, legend_x + 24, y + 30), radius=5, fill=color)
        line = f"{name} {amount:g} 元"
        draw.text((legend_x + 38, y), line, font=fonts["legend"], fill="#20242A")
        draw.text((legend_x + 38, y + 25), f"{percent:.1f}%", font=fonts["small"], fill="#667085")


def create_finance_chart_image(period: str) -> tuple[Path, str]:
    from PIL import Image, ImageDraw

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    start, end, title = period_range(period)
    expense_rows = rows_between(EXPENSES_CSV, start, end)
    income_rows = rows_between(INCOME_CSV, start, end)
    expense_total = sum(safe_amount(row.get("amount")) for row in expense_rows)
    income_total = sum(safe_amount(row.get("amount")) for row in income_rows)
    expense_totals = compact_totals(finance_totals(expense_rows, "expense"))
    income_totals = compact_totals(finance_totals(income_rows, "income"))

    image = Image.new("RGB", (1400, 900), "#F6F8FB")
    draw = ImageDraw.Draw(image)
    fonts = {
        "title": chart_font(46, True),
        "subtitle": chart_font(24),
        "panel_title": chart_font(30, True),
        "legend": chart_font(22),
        "small": chart_font(19),
        "summary": chart_font(25, True),
    }
    colors = ["#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1", "#9C755F"]

    heading = f"{title}收支占比图"
    draw_centered(draw, (700, 48), heading, fonts["title"], "#111827")
    draw_centered(draw, (700, 108), f"{start.isoformat()} 至 {end.isoformat()}", fonts["subtitle"], "#667085")

    net = income_total - expense_total
    summary_items = [("支出", expense_total, "#E15759"), ("收入", income_total, "#59A14F"), ("净额", net, "#4E79A7" if net >= 0 else "#E15759")]
    x = 210
    for label, value, color in summary_items:
        draw.rounded_rectangle((x, 162, x + 300, 232), radius=18, fill="#FFFFFF", outline="#E2E6EF", width=2)
        draw.text((x + 28, 184), label, font=fonts["subtitle"], fill="#667085")
        money = f"{value:g} 元"
        draw.text((x + 105, 180), money, font=fonts["summary"], fill=color)
        x += 345

    draw_finance_panel(draw, (70, 285, 680, 805), "支出分类", expense_totals, expense_total, colors, fonts)
    draw_finance_panel(draw, (720, 285, 1330, 805), "收入来源", income_totals, income_total, list(reversed(colors)), fonts)

    path = CHARTS_DIR / f"finance_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    image.save(path, format="PNG")
    for old_path in sorted(CHARTS_DIR.glob("finance_*.png"), key=lambda item: item.stat().st_mtime, reverse=True)[20:]:
        try:
            old_path.unlink()
        except OSError:
            pass
    caption = f"{title}收支图：支出 {expense_total:g} 元，收入 {income_total:g} 元，净额 {net:g} 元。"
    return path, caption


def finance_chart_reply(period: str) -> dict:
    path, caption = create_finance_chart_image(period)
    return {"type": "photo", "photo": str(path), "caption": caption}


def normalize_period(value: str | None, default: str = "month") -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "today": "today", "day": "today", "今日": "today", "今天": "today",
        "week": "week", "本周": "week", "这周": "week", "weekly": "week",
        "month": "month", "本月": "month", "这个月": "month", "monthly": "month",
        "year": "year", "今年": "year", "年度": "year", "全年": "year", "yearly": "year",
    }
    return aliases.get(text, default)


def view_action_from_text(text: str) -> dict | None:
    if is_delete_request(text):
        return None
    if any(word in text for word in ("最近记录", "最近记了", "最近", "recent", "历史记录", "记录列表", "看看记录")):
        return {"type": "view", "name": "recent"}
    if any(word in text for word in ("提醒列表", "待提醒", "reminders", "查看提醒", "看看提醒", "有哪些提醒", "我的提醒", "提醒清单")):
        return {"type": "view", "name": "reminders"}
    if any(word in text for word in ("待办列表", "待办清单", "todo", "查看待办", "看看待办", "有哪些待办", "我的待办", "今日任务", "今天任务", "任务列表", "任务清单", "今天要做什么", "今天要干啥")):
        return {"type": "view", "name": "todo"}
    if any(word in text for word in ("预算情况", "预算状态", "budget", "预算还剩", "还剩多少预算", "预算用了多少", "预算进度")):
        return {"type": "view", "name": "budget", "period": parse_period(text)}
    if any(word in text for word in ("重要事项", "重要日期", "日期列表", "dates", "纪念日列表", "生日列表", "看看日期", "有哪些重要日子")):
        return {"type": "view", "name": "dates"}
    return None


def first_action_item(action: dict) -> dict:
    items = action.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def action_value(action: dict, *names: str, default=""):
    item = first_action_item(action)
    for name in names:
        value = action.get(name)
        if value not in (None, ""):
            return value
        value = item.get(name)
        if value not in (None, ""):
            return value
    return default


def view_reply(action: dict, chat_id: int | None = None) -> str:
    name = str(action_value(action, "name", "view", default="")).strip().lower()
    period = normalize_period(action_value(action, "period", default="month"), "month")
    aliases = {
        "records": "recent", "record": "recent", "recent_records": "recent",
        "reminder": "reminders", "reminder_list": "reminders",
        "todos": "todo", "todo_list": "todo", "task": "todo", "tasks": "todo",
        "budget_status": "budget", "budgets": "budget",
        "date": "dates", "important_dates": "dates",
    }
    name = aliases.get(name, name)
    if name == "recent":
        return recent_records(chat_id=chat_id)
    if name == "reminders":
        return list_reminders()
    if name == "todo":
        return goal_status_reply()
    if name == "budget":
        return budget_status(period)
    if name == "dates":
        return list_dates()
    return "这个查看项我还没识别清楚。你可以说：最近记录、提醒列表、今日任务、预算情况、重要事项。"


def combine_reply_parts(parts: list) -> str | dict:
    messages = []
    photos = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, dict):
            if part.get("type") == "photo":
                photos.append(part)
            elif part.get("type") == "multi":
                messages.extend(part.get("messages") or [])
                photos.extend(part.get("photos") or [])
        else:
            messages.append(str(part).strip())
    messages = [message for message in messages if message]
    if photos and messages:
        return {"type": "multi", "messages": messages, "photos": photos}
    if len(photos) == 1:
        return photos[0]
    if len(photos) > 1:
        return {"type": "multi", "messages": messages, "photos": photos}
    return "\n\n".join(messages) if messages else "没有识别到需要执行的内容。"


def send_reply(token: str, chat_id: int, reply) -> None:
    if isinstance(reply, dict) and reply.get("type") == "photo":
        send_photo(token, chat_id, reply["photo"], reply.get("caption", ""))
        return
    if isinstance(reply, dict) and reply.get("type") == "multi":
        for message in reply.get("messages") or []:
            send_message(token, chat_id, message)
        for photo in reply.get("photos") or []:
            send_photo(token, chat_id, photo["photo"], photo.get("caption", ""))
        return
    send_message(token, chat_id, str(reply))


def summary_period_from_text(text: str) -> str | None:
    summary_words = ("总结", "复盘", "回顾", "小结", "汇总", "报告")
    if text in {"/today", "今日总结", "今天总结", "今日复盘", "今天复盘", "今日回顾", "今天回顾"} or (any(word in text for word in summary_words) and any(word in text for word in ("今日", "今天", "本日"))):
        return "today"
    if text in {"/week", "本周总结", "这周总结", "本周复盘", "这周复盘"} or (any(word in text for word in summary_words) and any(word in text for word in ("本周", "这周", "本星期", "这个星期", "一周", "周报"))):
        return "week"
    if text in {"/month", "/summary", "本月总结", "月总结", "本月复盘", "月报"} or (any(word in text for word in summary_words) and any(word in text for word in ("本月", "这个月", "这月", "月度", "一月", "月报"))):
        return "month"
    if text in {"/year", "今年总结", "年度总结", "全年总结", "年报"} or (any(word in text for word in summary_words) and any(word in text for word in ("今年", "年度", "全年", "一年", "年报"))):
        return "year"
    return None



def list_dates() -> str:
    if not DATES_CSV.exists():
        return "暂无重要事项记录。"
    with DATES_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda row: row.get("date", ""))
    if not rows:
        return "暂无重要事项记录。"
    lines = ["重要事项："]
    for row in rows[-20:]:
        remind = safe_int(row.get("remind_days"))
        suffix = f"，提前 {remind} 天提醒" if remind else ""
        lines.append(f"- {row.get('date', '')} {row.get('title', '')}{suffix}")
    return "\n".join(lines)


def recent_records(limit: int = 8, chat_id: int | None = None) -> str:
    entries = recent_entries(limit)
    remember_recent_entries(chat_id, entries)
    if not entries:
        return "暂无记录。"
    lines = ["最近记录："]
    for index, entry in enumerate(entries, 1):
        lines.append(f"{index}. [{entry.get('label', '')}] {entry.get('text', '')}")
    lines.append("可直接说：删第2条，或：把第1条改成15元。")
    return "\n".join(lines)

def is_question_like(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith(("?", "？")):
        return True
    return any(word in stripped for word in ("吗", "么", "如何", "怎么", "怎么办", "为什么", "啥意思", "什么意思", "你觉得", "有没有", "可不可以", "能不能", "要不要"))


def is_note_confirmation(text: str) -> bool:
    stripped = text.strip()
    return stripped in {"记下", "记录", "记", "保存", "存一下", "记下来", "帮我记下", "对", "是", "可以", "嗯", "好"}


def is_note_cancel(text: str) -> bool:
    stripped = text.strip()
    return stripped in {"不用", "不用了", "不记", "别记", "算了", "取消", "取消记录", "先不记", "不要记"}


def is_explicit_note_request(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    explicit_words = (
        "记一下", "记录一下", "帮我记", "帮我记录", "记下来", "记下这个", "把这件事记下来",
        "把这个记下来", "留个记录", "存一下", "写下来", "生活日志", "生活事项", "日记", "日志：", "日志:",
        "/note", "note:", "note：",
    )
    return any(word in lowered or word in stripped for word in explicit_words)


def strip_note_request(text: str) -> str:
    content = text.strip()
    content = re.sub(r"^/(note|log)\s*", "", content, flags=re.I)
    content = re.sub(r"^(生活日志|生活事项|日记|日志|note)\s*[：:]\s*", "", content, flags=re.I)
    content = re.sub(r"^(帮我)?(记一下|记录一下|记下|记录|帮我记|帮我记录|留个记录|存一下|写下来)\s*", "", content)
    content = re.sub(r"^(把)?(这件事|这个|这句话)\s*(记下来|记录下来)\s*", "", content)
    return content.strip(" ：:，,。")


def local_note_action(text: str) -> dict | None:
    content = strip_note_request(text)
    if not content or is_question_like(content):
        return None
    return {"type": "note", "items": [{"date": local_record_date(text), "content": content}]}


def has_non_note_intent(text: str) -> bool:
    return any((
        has_expense_hint(text),
        has_income_hint(text),
        is_mood_statement(text),
        has_weather_hint(text),
        has_event_hint(text),
        has_study_plan_hint(text),
        chart_period_from_text(text) is not None,
        summary_period_from_text(text) is not None,
        view_action_from_text(text) is not None,
        daily_report_kind_from_text(text) is not None,
        mood_trend_period_from_text(text) is not None,
    ))


def is_obvious_chat_only(text: str) -> bool:
    stripped = text.strip()
    if is_question_like(stripped) or has_chat_hint(stripped):
        return True
    casual_words = ("你真好", "谢谢", "哈哈", "笑死", "随便聊", "陪我", "吐槽一下", "我该怎么办", "怎么办")
    if any(word in stripped for word in casual_words):
        return True
    feedback_objects = ("功能", "模块", "机器人", "助手", "bot", "Bot", "回复", "代码")
    feedback_words = ("不错", "好用", "不好用", "喜欢", "问题", "bug", "优化", "改进", "不行", "太生硬")
    return any(word in stripped for word in feedback_objects) and any(word in stripped for word in feedback_words)


def life_note_value_score(text: str) -> int:
    stripped = text.strip()
    score = 0
    time_words = ("今天", "昨天", "前天", "刚刚", "刚才", "上午", "中午", "下午", "晚上", "今晚", "周末", "这周", "最近")
    milestone_words = ("开始", "决定", "第一次", "重新", "终于", "坚持", "改变", "完成", "做完", "结束", "报名", "入门")
    action_words = ("去了", "去", "见了", "见到", "遇到", "碰到", "参加", "看了", "读了", "写了", "聊了", "学了", "学习", "练了", "跑了", "回家", "出门", "路过")
    scene_words = ("图书馆", "学校", "海边", "公园", "医院", "公司", "家里", "宿舍", "朋友", "同学", "老师", "考试", "面试", "实习", "旅行")
    reflection_words = ("虽然", "但是", "胜在", "还好", "不容易", "值得", "算是", "以后", "从今天起")
    if any(word in stripped for word in time_words):
        score += 1
    if any(word in stripped for word in milestone_words):
        score += 2
    if any(word in stripped for word in action_words):
        score += 1
    if any(word in stripped for word in scene_words):
        score += 1
    if any(word in stripped for word in reflection_words):
        score += 1
    return score


def note_confirmation_preference(chat_id: int | None) -> str:
    if chat_id is None:
        return "normal"
    try:
        stats = read_state().get("note_confirmation_stats", {}).get(str(chat_id), {})
    except Exception:
        return "normal"
    accepted = safe_int(stats.get("accepted"))
    cancelled = safe_int(stats.get("cancelled"))
    if cancelled >= accepted + 3:
        return "quiet"
    if accepted >= cancelled + 2:
        return "eager"
    return "normal"


def should_confirm_life_note(text: str, chat_id: int | None = None) -> bool:
    stripped = text.strip()
    if not (4 <= len(stripped) <= 100):
        return False
    if is_delete_request(stripped) or is_explicit_note_request(stripped):
        return False
    if has_non_note_intent(stripped) or is_obvious_chat_only(stripped):
        return False
    score = life_note_value_score(stripped)
    preference = note_confirmation_preference(chat_id)
    threshold = 5 if preference == "quiet" else 2 if preference == "eager" else 3
    return score >= threshold


def is_life_note_candidate(text: str) -> bool:
    return should_confirm_life_note(text, None)


def note_pending_store(state: dict) -> dict:
    return state.setdefault("pending_note_confirmations", {})


def update_note_confirmation_stats(state: dict, chat_id: int | None, accepted: bool) -> None:
    if chat_id is None:
        return
    stats = state.setdefault("note_confirmation_stats", {}).setdefault(str(chat_id), {"accepted": 0, "cancelled": 0})
    key = "accepted" if accepted else "cancelled"
    stats[key] = safe_int(stats.get(key)) + 1


def life_note_chat_reply(text: str) -> str:
    if any(word in text for word in ("学习", "开始", "入门", "python", "Python")):
        return "这挺值得肯定的，少一点也没关系，开始本身就已经在动了。"
    if any(word in text for word in ("海边", "公园", "散步", "出门", "路过")):
        return "听起来今天有一点不一样，能把这段小经历说出来也挺好。"
    if any(word in text for word in ("见了", "见到", "聊了", "朋友", "同学")):
        return "这种和人有关的小片段，之后回看常常会很有温度。"
    return local_chat_reply(text)


def queue_pending_note_confirmation(text: str, chat_id: int | None) -> str:
    content = strip_note_request(text) if is_explicit_note_request(text) else text.strip(" ：:，,。")
    if chat_id is not None:
        state = read_state()
        note_pending_store(state)[str(chat_id)] = {
            "date": local_record_date(text),
            "content": content,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        set_pending_center(state, chat_id, "note")
        write_state(state)
    confirm = f"这句像生活记录。要帮你记进生活日志吗？\n内容：{content}\n回复“记下”保存，回复“不用”取消。"
    return life_note_chat_reply(text) + "\n\n" + confirm


def chat_then_queue_pending_note_confirmation(text: str, chat_id: int | None) -> str:
    return queue_pending_note_confirmation(text, chat_id)


def handle_pending_note_confirmation(text: str, chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    state = read_state()
    pending = note_pending_store(state)
    item = pending.get(str(chat_id))
    if not item:
        if is_note_confirmation(text):
            return "现在没有等待确认的生活事项。你可以说：记一下今天去了图书馆。"
        return None
    try:
        created_at = datetime.strptime(item.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        created_at = datetime.now()
    if datetime.now() - created_at > timedelta(minutes=30):
        pending.pop(str(chat_id), None)
        write_state(state)
        return None
    if is_note_cancel(text):
        pending.pop(str(chat_id), None)
        update_note_confirmation_stats(state, chat_id, accepted=False)
        write_state(state)
        return "好，这条不记。"
    if is_note_confirmation(text):
        pending.pop(str(chat_id), None)
        update_note_confirmation_stats(state, chat_id, accepted=True)
        write_state(state)
        return save_parsed({"type": "note", "items": [{"date": item.get("date") or datetime.now().date().isoformat(), "content": item.get("content", "")} ]})
    return None

def has_amount(text: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?", text))


def has_time_expression(text: str) -> bool:
    if re.search(r"\d{1,2}\s*[点:]|[一二两三四五六七八九十半]\s*点", text):
        return True
    if re.search(r"\d+\s*(分钟|小时|天|周|个月)后", text):
        return True
    if re.search(r"\d{1,2}\s*(月|/|-)\s*\d{1,2}\s*(日|号)?", text):
        return True
    return any(word in text for word in ("今天", "明天", "后天", "今晚", "早上", "上午", "中午", "下午", "晚上", "凌晨", "周一", "周二", "周三", "周四", "周五", "周六", "周日", "周天", "每天", "每周", "每月"))


def has_event_hint(text: str) -> bool:
    event_words = ("考试", "面试", "报名", "上课", "开会", "会议", "体检", "答辩", "比赛", "约", "聚餐", "交作业", "截止", "ddl", "DDL", "生日", "纪念日")
    reminder_words = ("提醒", "闹钟", "叫我", "通知")
    return has_time_expression(text) and (
        any(word in text for word in event_words) or any(word in text for word in reminder_words)
    )


def has_expense_hint(text: str) -> bool:
    expense_words = (
        "早餐", "午饭", "午餐", "晚饭", "晚餐", "夜宵", "奶茶", "咖啡", "打车", "地铁", "公交",
        "充值", "续费", "买", "花", "消费", "开销", "支出", "支付", "付款", "扣费", "花了", "花掉", "元", "块",
        "外卖", "电影", "游戏", "网吧", "网咖", "房租", "水电", "话费",
    )
    income_words = ("收入", "工资", "兼职", "赚", "到账", "入账", "红包", "报销", "收款", "生活费", "奖学金", "补贴")
    if not has_amount(text) or not any(word in text for word in expense_words):
        return False
    return not (any(word in text for word in income_words) and not any(word in text for word in ("花", "买", "消费", "支出", "打车", "早餐", "午饭", "晚饭", "充值", "续费")))


def has_income_hint(text: str) -> bool:
    income_words = ("兼职", "收入", "赚", "工资", "报销", "红包", "到账", "入账", "收款", "收到", "生活费", "奖学金", "补贴", "转账给我")
    return has_amount(text) and any(word in text for word in income_words)


def has_study_plan_hint(text: str) -> bool:
    if any(word in text for word in ("学习计划", "复习计划", "备考计划", "学习安排", "复习安排", "拆计划")):
        return True
    if any(word in text for word in ("拆解", "拆成", "安排一下", "规划一下", "制定计划")) and any(word in text for word in ("学习", "复习", "备考", "算法", "课程", "考试")):
        return True
    return False


def has_weather_hint(text: str) -> bool:
    if any(word in text for word in WEATHER_WORDS):
        return True
    return any(word in text for word in ("会不会下", "要不要带伞", "适合出门", "会不会很冷", "会不会很热"))


def is_weather_question(text: str) -> bool:
    return has_weather_hint(text)


def has_chat_hint(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in {"hi", "hello", "hey"}:
        return True
    if any(word in text for word in CHAT_WORDS):
        return True
    if any(word in text for word in ("功能", "模块", "机器人", "助手", "bot", "Bot", "回复")) and any(word in text for word in ("不错", "好", "喜欢", "问题", "bug", "优化", "改进", "不行", "太生硬")):
        return True
    return False


def local_chat_reply(text: str) -> str:
    if any(word in text for word in ("你好", "在吗", "早安")):
        reply = random.choice(["我在。今天想先处理哪一件小事？", "在的，慢慢说，我跟着你一起理。", "来了。今天我们从最容易推进的一步开始。"])
    elif "晚安" in text:
        reply = random.choice(["晚安。今天就先到这里，能收住也是一种完成。", "晚安，明天再继续。今天剩下的交给睡眠。"])
    elif any(word in text for word in ("鼓励", "夸夸", "给我打气")):
        reply = random.choice(["你已经在把生活一点点接回自己手里了，这件事不小。", "能想到让自己被支持一下，说明你没有放弃往前走。", "今天先别要求满分，能动一小步就很硬气。"])
    elif any(word in text for word in ("无聊", "没事干", "不知道干嘛")):
        reply = random.choice(["那就挑一个低门槛动作：洗把脸、收拾桌面一角，或者走五分钟。别急着找意义，先让身体动一下。", "无聊的时候别硬逼自己燃起来，先做一件小到不会抗拒的事。", "可以把接下来 20 分钟当成试运行：做一点点，够了就停。"])
    elif any(word in text for word in ("怎么办", "建议")):
        reply = "先把问题缩小到下一步：现在最影响你的那一件事是什么？说出来我帮你拆。"
    else:
        reply = random.choice(["收到。我在这儿，你可以继续说。", "嗯，我听到了。这个状态先不用急着定义。", "可以，先把这句话放下来，我们再慢慢处理后面的。"])
    return style_reply(reply, "chat")


def safe_companion_reply(config: dict, text: str) -> str:
    try:
        if config.get("deepseek_api_key"):
            return companion_answer(config, text)
    except Exception:
        pass
    return local_chat_reply(text)


def mood_support_reply(items: list[dict]) -> str:
    if not items:
        return encouragement("mood")
    scores = [safe_int(item.get("score")) for item in items]
    avg_score = sum(scores) / len(scores)
    text = " ".join(str(item.get("note") or item.get("reason") or item.get("mood") or "") for item in items)
    if avg_score >= 1:
        return random.choice([
            "挺好，把这种轻一点的状态也留下来。等以后回看，你会知道自己不是一直卡住的。",
            "不错，今天这点亮色值得被记住。可以顺手想想：是什么让状态变好了？",
            "收到，这种顺一点的日子也很重要。趁状态好，做一件小事就很赚。",
        ])
    if avg_score <= -1:
        if any(word in text for word in ("紧张", "考试", "面试")):
            return "紧张被看见了就没那么乱。先把下一步缩小：准备一个最确定能做的动作。"
        if any(word in text for word in ("累", "疲惫", "困")):
            return "累的时候先别逼自己解释太多，补一点水、坐直缓一下，能恢复一点是一点。"
        if any(word in text for word in ("无聊", "摆烂", "没动力")):
            return "这种没动力的时刻也会过去。先别追求自律，做一个两分钟能完成的小动作就行。"
        return random.choice([
            "我记下来了。今天先别把自己逼太紧，挑一件最小的事做完就够。",
            "这个状态不舒服，但它不是你的全部。先让自己缓一口气。",
            "收到。你不用马上变好，先把当下撑过去就已经算数。",
        ])
    return random.choice([
        "记下来了。平稳也很好，生活不是每天都要有大波动。",
        "收到，先把状态留个痕迹，之后总结时我们一起看规律。",
        "嗯，这样的状态也值得记录。今天按自己的节奏走就行。",
    ])


def support_layer_hint(text: str) -> bool:
    support_words = (
        "焦虑", "紧张", "担心", "害怕", "怕", "慌", "烦", "难受", "崩溃", "委屈", "失落", "不安",
        "累", "疲惫", "困", "没动力", "摆烂", "迷茫", "压力", "心态",
        "开心", "高兴", "不错", "顺利", "舒服", "轻松", "有希望",
    )
    return has_chat_hint(text) or is_mood_statement(text) or any(word in text for word in support_words)


def support_layer_reply(text: str) -> str:
    if not support_layer_hint(text):
        return ""
    if any(word in text for word in ("功能", "模块", "机器人", "助手", "bot", "Bot", "回复", "代码")):
        reply = "收到，这类体验反馈我会留意；主任务也已经处理了。"
    elif any(word in text for word in ("考试", "面试")) and any(word in text for word in ("紧张", "慌", "担心", "怕", "焦虑")):
        reply = "考试前紧张很正常，先把能确定的一小步做掉，心会稳一点。"
    elif has_weather_hint(text) and any(word in text for word in ("下雨", "降雨", "冷", "热", "台风", "怕", "担心")):
        reply = "天气这块先按保守方案准备，带伞或外套这种小动作很划算。"
    elif any(word in text for word in ("累", "疲惫", "困")):
        reply = "累的时候先别硬顶，补点水、缓两分钟，再决定下一步。"
    elif any(word in text for word in ("开心", "高兴", "不错", "顺利", "舒服", "轻松", "有希望")):
        reply = "这个状态挺好，顺手留住一点点就已经很赚。"
    elif any(word in text for word in ("焦虑", "紧张", "担心", "害怕", "怕", "慌", "烦", "难受", "崩溃", "委屈", "失落", "不安", "没动力", "摆烂", "迷茫", "压力")):
        reply = "先别急着把自己拉满，挑一个最小动作做完就够了。"
    else:
        reply = "我听到了，先把主线处理好，情绪这部分也不用急着压下去。"
    return style_reply(reply, "chat")


def reply_text_for_support(reply) -> str:
    if isinstance(reply, dict):
        texts = []
        if reply.get("caption"):
            texts.append(str(reply.get("caption") or ""))
        if reply.get("messages"):
            texts.extend(str(message) for message in reply.get("messages") or [])
        if reply.get("photos"):
            for photo in reply.get("photos") or []:
                if isinstance(photo, dict) and photo.get("caption"):
                    texts.append(str(photo.get("caption") or ""))
        return "\n".join(texts)
    return str(reply or "")


def with_support_layer(reply, source_text: str, action_types: set[str] | None = None):
    action_types = action_types or set()
    if not source_text or "mood" in action_types or "answer" in action_types:
        return reply
    if "weather" in action_types and is_weather_only_mood_context(source_text):
        return reply
    support = support_layer_reply(source_text)
    if not support:
        return reply
    existing_text = reply_text_for_support(reply)
    if any(marker in existing_text for marker in ("已记录心情", "我记下来了", "紧张被看见", "我在这儿", "下一步", "状态")):
        return reply
    if isinstance(reply, dict) and reply.get("type") == "multi":
        messages = list(reply.get("messages") or [])
        photos = list(reply.get("photos") or [])
        messages.append(support)
        return {"type": "multi", "messages": messages, "photos": photos}
    if isinstance(reply, dict) and reply.get("type") == "photo":
        return {"type": "multi", "messages": [support], "photos": [reply]}
    reply_text = str(reply or "").strip()
    return (reply_text + "\n\n" + support).strip() if reply_text else support

def is_delete_request(text: str) -> bool:
    return any(word in text for word in DELETE_WORDS)




def is_weather_only_mood_context(text: str) -> bool:
    if not has_weather_hint(text):
        return False
    self_markers = ("\u5fc3\u60c5", "\u60c5\u7eea", "\u72b6\u6001", "\u6211\u6709\u70b9", "\u6211\u6709\u4e9b", "\u6211\u5f88", "\u6211\u633a", "\u611f\u89c9\u6211")
    self_mood_phrase = re.search(r"(\u6211)?(\u6709\u70b9|\u6709\u4e9b|\u5f88|\u633a|\u6709\u70b9\u513f)(\u70e6|\u7d2f|\u7d27\u5f20|\u7126\u8651|\u5bb3\u6015|\u62c5\u5fc3|\u96be\u53d7|\u5f00\u5fc3|\u9ad8\u5174|\u4e0d\u5b89|\u5d29\u6e83|\u4e27)", text)
    if any(marker in text for marker in self_markers) or self_mood_phrase:
        return False
    weather_subjects = ("\u5929\u6c14", "\u6c14\u6e29", "\u6e29\u5ea6", "\u96e8", "\u4e0b\u96e8", "\u592a\u9633", "\u6674", "\u9634", "\u70ed", "\u51b7", "\u98ce", "\u53f0\u98ce")
    mood_like_adjectives = ("\u4e0d\u9519", "\u633a\u597d", "\u5f88\u597d", "\u8fd8\u884c", "\u8212\u670d", "\u7cdf", "\u5dee", "\u723d", "\u95f7", "\u70e6")
    return any(subject in text for subject in weather_subjects) and any(word in text for word in mood_like_adjectives)

def is_mood_statement(text: str) -> bool:
    if mood_trend_period_from_text(text):
        return False
    if is_weather_only_mood_context(text):
        return False
    question_words = ("怎么办", "怎么", "如何", "建议")
    self_mood_markers = ("我", "今天", "有点", "有些", "很", "太", "挺", "感觉", "心情", "状态")
    if any(word in text for word in question_words) and not any(word in text for word in self_mood_markers):
        return False
    object_feedback_words = ("功能", "模块", "机器人", "助手", "bot", "Bot", "回复", "代码", "天气模块")
    if any(word in text for word in object_feedback_words) and any(word in text for word in ("不错", "好", "喜欢", "问题", "bug", "优化", "改进", "不行", "太生硬")) and not any(word in text for word in ("心情", "情绪", "状态", "开心", "难受", "焦虑", "累", "紧张", "烦")):
        return False
    strong_words = tuple(word for word in MOOD_WORDS if word not in {"感觉", "状态"})
    if any(word in text for word in strong_words):
        return True
    if any(word in text for word in ("感觉", "状态")) and any(word in text for word in NEGATIVE_MOOD_WORDS + POSITIVE_MOOD_WORDS + ("一般", "平稳", "还可以", "糟", "颓")):
        return True
    return False


def local_mood_parse(text: str) -> dict:
    today = datetime.now().date()
    if "昨天" in text:
        today = today - timedelta(days=1)
    score = 0
    if any(word in text for word in NEGATIVE_MOOD_WORDS):
        score = -1
    if any(word in text for word in ("崩溃", "很难受", "特别焦虑")):
        score = -2
    if any(word in text for word in POSITIVE_MOOD_WORDS):
        score = max(score, 1)
    if any(word in text for word in ("非常开心", "很高兴")):
        score = 2
    label = "情绪平稳"
    if score < 0:
        label = "状态偏低"
    elif score > 0:
        label = "状态不错"
    reason = ""
    reason_match = re.search(r"(?:因为|主要是|感觉)(.+)", text)
    if reason_match:
        reason = reason_match.group(1).strip(" ，,。")
    return {
        "type": "mood",
        "items": [{
            "date": today.isoformat(),
            "mood": label,
            "score": score,
            "reason": reason,
            "note": text,
        }],
    }


def extract_city(config: dict, text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5]{2,16})(?:天气|会下雨|下雨|会不会下雨|降雨|气温|温度)", text)
    if match:
        candidate = clean_city_name(match.group(1))
        if candidate:
            return candidate
    return config.get("default_city", "")


def clean_city_name(candidate: str) -> str:
    candidate = candidate.strip()
    candidate = re.sub(
        r"(今天|明天|后天|今晚|晚上|早上|中午|下午|现在|当前|此刻|我这里|这边|那边|未来一周|未来七天|未来7天|未来三天|未来3天|未来几天|一周|七天|7天|三天|3天|本周|这周|周内)",
        "",
        candidate,
    )
    candidate = re.sub(r"(会|还会|要|要不要|能不能|有没有|适合)+$", "", candidate)
    candidate = candidate.strip(" ，,。？?：:")
    stop_words = {"会", "还会", "要", "要不要", "能不能", "有没有", "适合", "天气", "下雨", "有雨"}
    if len(candidate) < 2 or candidate in stop_words:
        return ""
    return candidate



def weather_query_mode(text: str) -> str:
    if any(word in text for word in ("一周", "未来7天", "未来七天", "七天", "7天", "未来三天", "未来3天", "三天", "3天", "未来几天", "这周", "本周", "周内")):
        return "week"
    if "后天" in text:
        return "day_after_tomorrow"
    if "明天" in text:
        return "tomorrow"
    return "today"


def weather_target_date(mode: str) -> datetime.date:
    today = datetime.now().date()
    if mode == "tomorrow":
        return today + timedelta(days=1)
    if mode == "day_after_tomorrow":
        return today + timedelta(days=2)
    return today


def weather_day_label(mode: str, date_text: str = "") -> str:
    labels = {"today": "今天", "tomorrow": "明天", "day_after_tomorrow": "后天"}
    return labels.get(mode, date_text or "当天")


def daily_value(daily: dict, key: str, index: int, default="?"):
    values = daily.get(key) or []
    if 0 <= index < len(values):
        value = values[index]
        return default if value is None else value
    return default


def weather_day_index(daily: dict, target_date) -> int | None:
    target = target_date.isoformat()
    for index, value in enumerate(daily.get("time") or []):
        if value == target:
            return index
    return None


def weather_daily_line(daily: dict, index: int, label: str) -> str:
    code = daily_value(daily, "weather_code", index, None)
    t_min = daily_value(daily, "temperature_2m_min", index)
    t_max = daily_value(daily, "temperature_2m_max", index)
    rain_prob = daily_value(daily, "precipitation_probability_max", index, 0)
    rain_sum = daily_value(daily, "precipitation_sum", index, 0)
    return f"{label}：{weather_code_text(code)}，{t_min}~{t_max}°C，最高降雨概率约 {rain_prob}%，预计降水 {rain_sum} mm。"


def hourly_window_summary(hourly: dict, target_date, start_hour: int, end_hour: int, label: str) -> str:
    times = hourly.get("time") or []
    rain_probs = hourly.get("precipitation_probability") or []
    weather_codes = hourly.get("weather_code") or []
    temps = hourly.get("temperature_2m") or []
    indexes = []
    for index, value in enumerate(times):
        try:
            day_text, time_text = value.split("T", 1)
            hour = int(time_text.split(":", 1)[0])
            day = datetime.strptime(day_text, "%Y-%m-%d").date()
        except (ValueError, IndexError):
            continue
        if day == target_date and start_hour <= hour <= end_hour:
            indexes.append(index)
    if not indexes:
        return f"{label}分时段预报暂时没取到。"
    valid_probs = [int(rain_probs[i] or 0) for i in indexes if i < len(rain_probs)]
    valid_temps = [float(temps[i]) for i in indexes if i < len(temps) and temps[i] is not None]
    codes = [weather_codes[i] for i in indexes if i < len(weather_codes)]
    max_rain = max(valid_probs) if valid_probs else 0
    temp_text = ""
    if valid_temps:
        temp_text = f"，气温约 {min(valid_temps):g}~{max(valid_temps):g}°C"
    desc = weather_code_text(codes[0] if codes else None)
    return f"{label}：{desc}{temp_text}，最高降雨概率约 {max_rain}%。"


def weather_advice(rain_prob, rain_sum, t_min, t_max) -> str:
    try:
        rain_prob = int(rain_prob or 0)
    except (TypeError, ValueError):
        rain_prob = 0
    try:
        rain_sum = float(rain_sum or 0)
    except (TypeError, ValueError):
        rain_sum = 0
    try:
        t_min = float(t_min)
        t_max = float(t_max)
    except (TypeError, ValueError):
        t_min = t_max = None
    tips = []
    if rain_prob >= 60 or rain_sum >= 3:
        tips.append("出门建议带伞，鞋子也别选太怕湿的。")
    elif rain_prob >= 35:
        tips.append("有一定降雨可能，包里放把伞比较稳。")
    if t_max is not None and t_max >= 32:
        tips.append("温度偏高，记得补水。")
    if t_min is not None and t_min <= 12:
        tips.append("早晚偏冷，可以多带一层。")
    return " ".join(tips) if tips else "整体看问题不大，按正常安排走就行。"


def weather_week_reply(display_city: str, daily: dict) -> str:
    times = daily.get("time") or []
    if not times:
        return f"{display_city}未来一周预报暂时没取到。"
    lines = [f"{display_city}未来一周天气概况："]
    wet_days = []
    for index, date_text in enumerate(times[:7]):
        label = date_text[5:]
        line = weather_daily_line(daily, index, label)
        lines.append("- " + line)
        rain_prob = daily_value(daily, "precipitation_probability_max", index, 0)
        rain_sum = daily_value(daily, "precipitation_sum", index, 0)
        try:
            if int(rain_prob or 0) >= 50 or float(rain_sum or 0) >= 2:
                wet_days.append(label)
        except (TypeError, ValueError):
            pass
    if wet_days:
        lines.append(f"重点留意：{', '.join(wet_days[:4])} 降雨概率偏高，出门前再确认一下。")
    else:
        lines.append("这一周暂时没有特别突出的降雨信号。")
    return "\n".join(lines)


def weather_answer(config: dict, text: str) -> str:
    city = extract_city(config, text)
    if not city:
        return "你还没设置默认城市。请在 config.json 里加一行，例如：\n\"default_city\": \"杭州\"\n然后重启机器人。也可以直接问：杭州今晚会下雨吗"
    geo_params = urlencode({"name": city, "count": 1, "language": "zh", "format": "json"})
    try:
        geo = http_json(f"https://geocoding-api.open-meteo.com/v1/search?{geo_params}", timeout=20)
    except Exception as exc:
        return f"天气位置查询暂时失败：{exc}\n你可以稍后再试，或直接指定城市，例如：深圳明天天气如何"
    results = geo.get("results") or []
    if not results:
        return f"没查到“{city}”的天气位置。你可以换个更明确的城市名，例如：深圳明天天气如何"
    place = results[0]
    latitude = place["latitude"]
    longitude = place["longitude"]
    display_city = city if any(unit in city for unit in ("区", "县", "旗")) else (place.get("name") or city)
    forecast_params = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,precipitation,weather_code",
        "hourly": "precipitation_probability,weather_code,temperature_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
        "forecast_days": 7,
        "timezone": "auto",
    })
    try:
        data = http_json(f"https://api.open-meteo.com/v1/forecast?{forecast_params}", timeout=20)
    except Exception as exc:
        return f"{display_city}天气查询暂时失败：{exc}\n可能是天气服务短暂不可用，稍后再问我一次。"

    mode = weather_query_mode(text)
    daily = data.get("daily") or {}
    hourly = data.get("hourly") or {}
    if mode == "week":
        return weather_week_reply(display_city, daily)

    target_date = weather_target_date(mode)
    index = weather_day_index(daily, target_date)
    label = weather_day_label(mode, target_date.isoformat()[5:])
    lines = []
    if mode == "today":
        current = data.get("current") or {}
        current_temp = current.get("temperature_2m", "?")
        current_rain = current.get("precipitation", 0)
        current_desc = weather_code_text(current.get("weather_code"))
        lines.append(f"{display_city}现在：{current_desc}，{current_temp}°C，当前降水 {current_rain} mm。")
    if index is not None:
        daily_label = f"{display_city}{label}" if mode != "today" else label
        lines.append(weather_daily_line(daily, index, daily_label))
        if any(word in text for word in ("今晚", "晚上", "夜里", "还会下")):
            lines.append(hourly_window_summary(hourly, target_date, 18, 23, f"{label}晚上"))
        rain_prob = daily_value(daily, "precipitation_probability_max", index, 0)
        rain_sum = daily_value(daily, "precipitation_sum", index, 0)
        t_min = daily_value(daily, "temperature_2m_min", index)
        t_max = daily_value(daily, "temperature_2m_max", index)
        lines.append(weather_advice(rain_prob, rain_sum, t_min, t_max))
    else:
        lines.append(f"{display_city}{label}的日预报暂时没取到。")
    return "\n".join(lines)

def weather_code_text(code) -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "天气未知"
    mapping = {
        0: "晴", 1: "大部晴朗", 2: "局部多云", 3: "阴",
        45: "雾", 48: "雾凇",
        51: "小毛毛雨", 53: "中等毛毛雨", 55: "较强毛毛雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪",
        80: "短时小阵雨", 81: "短时中阵雨", 82: "强阵雨",
        95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴强冰雹",
    }
    return mapping.get(code, "天气未知")



def companion_answer(config: dict, text: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tone = TONE_ALIASES.get(current_tone_mode(), "温柔陪伴")
    system = f"""
你是一个日常生活助手。当前时间：{now}。当前语气模式：{tone}。
用中文回答，语气温和、具体、简洁；若当前语气是严格督促，可以更直接但不要羞辱用户。
目标是帮用户处理日常生活、学习、情绪、计划、选择和小问题。
如果用户只是情绪倾诉，先接住情绪，再给一个很小、可以马上做的动作。
不要长篇说教，不要空泛鸡汤，不要冒充专业医生/律师/理财顾问。
遇到危险、自伤、严重疾病等高风险内容，建议立即联系现实中的可信任的人或专业机构。
""".strip()
    payload = {
        "model": config["deepseek_model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "temperature": 0.7,
        "stream": False,
    }
    result = http_json(
        "https://api.deepseek.com/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {config['deepseek_api_key']}"},
        timeout=90,
    )
    return result["choices"][0]["message"]["content"].strip()


def json_from_model_content(content: str) -> dict:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if fenced:
        content = fenced.group(1).strip()
    return json.loads(content)


def fallback_study_tasks(goal: str, days: int, start: datetime.date) -> list[dict]:
    goal = goal or "学习目标"
    templates = [
        f"明确{goal}的范围，列出资料和薄弱点",
        f"完成{goal}的基础知识梳理",
        f"做一轮{goal}练习，并记录错题",
        f"复盘错题，补上不会的知识点",
        f"做一次限时练习或模拟检查",
        f"整理{goal}复习清单，保留最后要看的重点",
        f"轻量复盘，确认明天第一步",
    ]
    tasks = []
    for index in range(max(1, min(days, 14))):
        text = templates[index] if index < len(templates) else f"推进{goal}第 {index + 1} 步并复盘"
        tasks.append({"text": text, "due_date": (start + timedelta(days=index)).isoformat()})
    return tasks


def create_study_plan(config: dict, action: dict) -> str:
    goal = str(action_value(action, "goal", "text", "content", default="")).strip() or "学习计划"
    deadline = str(action_value(action, "deadline", "due_date", default="")).strip()
    days = safe_int(action_value(action, "days", default="7"), 7)
    days = max(1, min(days, 14))
    start_day = datetime.now().date()
    if deadline:
        try:
            deadline_day = datetime.strptime(deadline, "%Y-%m-%d").date()
            days = max(1, min((deadline_day - start_day).days + 1, 14))
        except ValueError:
            deadline = ""
    tasks = []
    if config.get("deepseek_api_key"):
        system = "你是学习计划拆解器。只返回 JSON：{\"tasks\":[{\"text\":\"任务\",\"due_date\":\"YYYY-MM-DD\"}],\"note\":\"一句鼓励\"}。任务要具体、可执行、适合学生，不要超过 10 条。"
        user = f"当前日期：{start_day.isoformat()}\n学习目标：{goal}\n截止日期：{deadline or '未指定'}\n计划天数：{days}"
        payload = {
            "model": config["deepseek_model"],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.4,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        try:
            result = http_json(
                "https://api.deepseek.com/chat/completions",
                payload,
                headers={"Authorization": f"Bearer {config['deepseek_api_key']}"},
                timeout=90,
            )
            data = json_from_model_content(result["choices"][0]["message"]["content"])
            tasks = [task for task in data.get("tasks", []) if isinstance(task, dict)]
        except Exception:
            tasks = []
    if not tasks:
        tasks = fallback_study_tasks(goal, days, start_day)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    for task in tasks[:10]:
        text = str(task.get("text") or "").strip()
        if not text:
            continue
        due_date = str(task.get("due_date") or "").strip()
        if due_date:
            try:
                datetime.strptime(due_date, "%Y-%m-%d")
            except ValueError:
                due_date = ""
        append_csv(TODOS_CSV, [uuid.uuid4().hex, text, "pending", due_date, created_at, ""])
        lines.append(f"- {text}{'（' + due_date + '）' if due_date else ''}")
    if not lines:
        return "学习计划没有拆出来。你可以说得更具体一点，比如：帮我把 7 天算法复习拆成计划。"
    return "学习计划已拆成待办：\n" + "\n".join(lines) + "\n先照着第一条做，别一口气把自己压满。"


def local_record_date(text: str) -> str:
    day = datetime.now().date()
    if "前天" in text:
        day = day - timedelta(days=2)
    elif "昨天" in text:
        day = day - timedelta(days=1)
    elif "明天" in text:
        day = day + timedelta(days=1)
    return day.isoformat()


def strip_record_noise(text: str) -> str:
    text = re.sub(r"(今天|今日|昨天|前天|明天|刚刚|刚才|早上|上午|中午|下午|晚上|今晚|凌晨)", "", text)
    text = re.sub(r"(我|花了|花掉|花|买了|买|消费|支出|支付|付款|开销|用了|用掉|吃了|吃|喝了|喝|充值了|充值|开销)", "", text)
    return text.strip(" ：:，,。？?的了")


def strip_income_noise(text: str) -> str:
    text = re.sub(r"(今天|今日|昨天|前天|明天|刚刚|刚才|早上|上午|中午|下午|晚上|今晚|我|收到|收到了|到账|到帐|入账|入帐|收入|赚了|赚|得了|给我|转账给我)", "", text)
    return text.strip(" ：:，,。？?的了")


def local_simple_expense_parse(text: str) -> dict | None:
    if has_multi_intent_hint(text) or not has_expense_hint(text):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)?", text)
    if not match:
        return None
    amount = safe_amount(match.group(1))
    if amount <= 0:
        return None
    before = text[:match.start()]
    after = text[match.end():]
    name = strip_record_noise(before) or strip_record_noise(after) or "消费"
    if len(name) > 30:
        name = name[-30:]
    category = normalize_expense_category(name, "其他")
    return {"type": "expense", "items": [{"date": local_record_date(text), "name": name, "amount": amount, "category": category, "note": ""}]}


def local_simple_income_parse(text: str) -> dict | None:
    if has_multi_intent_hint(text) or not has_income_hint(text):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)?", text)
    if not match:
        return None
    amount = safe_amount(match.group(1))
    if amount <= 0:
        return None
    before = text[:match.start()]
    after = text[match.end():]
    source = strip_income_noise(before) or strip_income_noise(after) or "收入"
    if len(source) > 30:
        source = source[-30:]
    category = normalize_income_category(source, "其他")
    return {"type": "income", "items": [{"date": local_record_date(text), "source": source, "amount": amount, "category": category, "note": ""}]}

def split_intent_segments(text: str) -> list[str]:
    parts = re.split(r"[，,。；;\n]+|(?:然后|顺便|另外|还有|并且|同时)", text)
    return [part.strip() for part in parts if part and part.strip()]


def local_expense_item_from_segment(segment: str) -> dict | None:
    if not has_expense_hint(segment):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)?", segment)
    if not match:
        return None
    amount = safe_amount(match.group(1))
    if amount <= 0:
        return None
    before = segment[:match.start()]
    after = segment[match.end():]
    name = strip_record_noise(before) or strip_record_noise(after) or "消费"
    if len(name) > 30:
        name = name[-30:]
    return {"date": local_record_date(segment), "name": name, "amount": amount, "category": normalize_expense_category(name, "其他"), "note": ""}


def local_income_item_from_segment(segment: str) -> dict | None:
    if not has_income_hint(segment):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)?", segment)
    if not match:
        return None
    amount = safe_amount(match.group(1))
    if amount <= 0:
        return None
    before = segment[:match.start()]
    after = segment[match.end():]
    source = strip_income_noise(before) or strip_income_noise(after) or "收入"
    if len(source) > 30:
        source = source[-30:]
    return {"date": local_record_date(segment), "source": source, "amount": amount, "category": normalize_income_category(source, "其他"), "note": ""}


def local_record_actions_from_text(text: str) -> list[dict]:
    expense_items = []
    income_items = []
    for segment in split_intent_segments(text):
        income_item = local_income_item_from_segment(segment)
        if income_item:
            income_items.append(income_item)
        expense_item = local_expense_item_from_segment(segment)
        if expense_item:
            expense_items.append(expense_item)
    actions = []
    if expense_items:
        actions.append({"type": "expense", "items": expense_items})
    if income_items:
        actions.append({"type": "income", "items": income_items})
    return actions


def local_study_plan_action(text: str) -> dict:
    days = 7
    if any(word in text for word in ("三天", "3天")):
        days = 3
    elif any(word in text for word in ("五天", "5天")):
        days = 5
    elif any(word in text for word in ("两周", "二周", "14天")):
        days = 14
    elif any(word in text for word in ("一周", "七天", "7天")):
        days = 7
    goal = re.sub(r"(帮我|给我|把|做一个|制定|安排|拆成|拆解|学习计划|复习计划|备考计划|计划|一下|吧|，|,|。)", "", text).strip()
    goal = goal or "学习计划"
    return {"type": "study_plan", "goal": goal, "deadline": "", "days": days}


def record_item_key(kind: str, item: dict) -> tuple:
    if kind == "expense":
        return (item.get("date", ""), item.get("name", ""), safe_amount(item.get("amount")))
    if kind == "income":
        return (item.get("date", ""), item.get("source", ""), safe_amount(item.get("amount")))
    return tuple(sorted(item.items()))


def merge_record_action(actions: list[dict], new_action: dict) -> bool:
    kind = new_action.get("type")
    new_items = [item for item in new_action.get("items", []) if isinstance(item, dict)]
    if kind not in {"expense", "income"} or not new_items:
        return False
    for action in actions:
        if action.get("type") != kind:
            continue
        items = action.setdefault("items", [])
        keys = {record_item_key(kind, item) for item in items if isinstance(item, dict)}
        changed = False
        for item in new_items:
            key = record_item_key(kind, item)
            if key not in keys:
                items.append(item)
                keys.add(key)
                changed = True
        return changed
    actions.append(new_action)
    return True


def has_action_type(actions: list[dict], kind: str) -> bool:
    return any(action.get("type") == kind for action in actions)




def low_value_answer_text(text: str) -> bool:
    normalized = re.sub(r"[\s\u3002\uff0c\uff01\uff1f\uff1a\uff1b,!.?:;~\-]+", "", str(text or "").lower())
    generic = {
        "ok", "okay", "modelok",
        "\u597d", "\u597d\u7684", "\u6536\u5230", "\u660e\u767d", "\u53ef\u4ee5", "\u6ca1\u95ee\u9898",
        "\u597d\u7684\u6211\u6765", "\u597d\u7684\u6211\u6765\u5904\u7406", "\u6211\u6765\u5904\u7406",
        "\u597d\u7684\u6211\u6765\u4e3a\u4f60\u5904\u7406", "\u597d\u7684\u6211\u6765\u5e2e\u4f60\u5904\u7406",
    }
    if normalized in generic:
        return True
    patterns = (
        r"^(\u597d\u7684|\u6536\u5230|\u660e\u767d)(\u6211\u6765|\u5df2\u7ecf)?(\u5e2e\u4f60|\u4e3a\u4f60)?(\u5904\u7406|\u8bb0\u5f55|\u67e5\u770b|\u5b89\u6392)?$",
        r"^(\u597d|\u884c|\u53ef\u4ee5)(\u7684)?$",
    )
    return any(re.fullmatch(pattern, normalized) for pattern in patterns)


def should_skip_answer_action(action: dict, actions: list[dict]) -> bool:
    if action.get("type") != "answer":
        return False
    has_other_action = any(isinstance(item, dict) and item.get("type") not in {"answer", ""} for item in actions)
    if not has_other_action:
        return False
    return low_value_answer_text(action.get("answer") or action.get("text") or "")


def local_extra_reminder_action(text: str) -> dict | None:
    if not has_event_hint(text):
        return None
    remind_at = parse_time_expression(text)
    if remind_at is None:
        return None
    match = re.search(r"(?:\u63d0\u9192\u6211|\u53eb\u6211|\u901a\u77e5\u6211)(.+)$", text)
    if not match:
        return None
    title = match.group(1)
    title = re.sub(
        r"(\u4eca\u5929|\u660e\u5929|\u540e\u5929|\u4eca\u665a|\u65e9\u4e0a|\u4e0a\u5348|\u4e2d\u5348|\u4e0b\u5348|\u665a\u4e0a|\u51cc\u6668|\u6bcf\u5929|\u6bcf\u5468|\u6bcf\u6708|\d{1,2}\s*[\u70b9:]\d{0,2}|\d{1,2}\s*\u70b9(?:\u534a|\d{1,2}\u5206?)?|[\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*\u70b9(?:\u534a|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\u5206?)?|\u5982\u679c|\u5c31|\u7684\u8bdd|\u5e2e\u6211|\u4e00\u4e0b)",
        " ",
        title,
    )
    title = re.sub(r"[\s\u3002\uff0c\uff1b\uff1a,.;:]+", " ", title).strip()
    event_only = {"\u8003\u8bd5", "\u9762\u8bd5", "\u5f00\u4f1a", "\u4f1a\u8bae", "\u4e0a\u8bfe", "\u751f\u65e5", "\u7eaa\u5ff5\u65e5", "\u622a\u6b62", "ddl", "DDL"}
    if len(title) < 2 or title in event_only:
        return None
    return {"type": "reminder", "items": [{"remind_at": remind_at.strftime("%Y-%m-%d %H:%M:%S"), "text": title, "repeat": "none"}]}

def parse_amount(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    return float(match.group(1))


def parse_period(text: str) -> str:
    if any(word in text for word in ("本周", "这周", "每周", "周")):
        return "week"
    return "month"



def finance_plan_from_text(text: str) -> str | None:
    if not any(word in text for word in ("收入", "工资", "生活费")):
        return None
    if not any(word in text for word in ("省", "存", "结余", "留下")):
        return None
    nums = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(nums) < 2:
        return None
    income, saving = nums[0], nums[1]
    if income <= 0 or saving < 0 or saving >= income:
        return "财政规划金额不太对。可以这样说：本月收入3000，计划省1000。"
    spend_limit = income - saving
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    if BUDGETS_CSV.exists():
        with BUDGETS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    rows = [row for row in rows if not (row.get("period") == "month" and row.get("category") == "总额")]
    rows.append({"period": "month", "category": "总额", "amount": f"{spend_limit:g}", "created_at": created_at, "id": uuid.uuid4().hex})
    with BUDGETS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["period", "category", "amount", "created_at", "id"])
        writer.writeheader()
        writer.writerows(rows)
    return f"已做好本月财政规划：收入 {income:g} 元，计划省 {saving:g} 元，本月可支出预算 {spend_limit:g} 元。之后每笔消费都会按总预算提醒。"


def set_budget(text: str) -> str | None:
    plan_reply = finance_plan_from_text(text)
    if plan_reply:
        return plan_reply
    if not any(word in text for word in ("预算", "限额")):
        return None
    amount = parse_amount(text)
    if amount is None:
        return "预算金额没有看清楚。你可以这样说：设置本月餐饮预算800"
    period = parse_period(text)
    category = "总额"
    for name in ("餐饮", "交通", "购物", "居住", "娱乐", "医疗", "学习", "其他"):
        if name in text:
            category = name
            break
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    if BUDGETS_CSV.exists():
        with BUDGETS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    rows = [row for row in rows if not (row.get("period") == period and row.get("category") == category)]
    rows.append({"period": period, "category": category, "amount": f"{amount:g}", "created_at": created_at, "id": uuid.uuid4().hex})
    with BUDGETS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["period", "category", "amount", "created_at", "id"])
        writer.writeheader()
        writer.writerows(rows)
    title = "本周" if period == "week" else "本月"
    return f"已设置{title}{category}预算：{amount:g} 元"


def budget_status(period: str | None = None) -> str:
    if period is None:
        period = "month"
    if not BUDGETS_CSV.exists():
        return "还没有设置预算。你可以说：设置本月餐饮预算800"
    with BUDGETS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        budgets = [row for row in csv.DictReader(f) if row.get("period") == period]
    if not budgets:
        return "这个周期还没有设置预算。"
    start, end, title = period_range(period)
    expenses = rows_between(EXPENSES_CSV, start, end)
    lines = [f"{title}预算："]
    for row in budgets:
        category = row.get("category") or "总额"
        limit = safe_amount(row.get("amount"))
        if category == "总额":
            used = sum(safe_amount(item.get("amount")) for item in expenses)
        else:
            used = sum(safe_amount(item.get("amount")) for item in expenses if item.get("category") == category)
        if limit <= 0:
            lines.append(f"- {category}: 预算金额异常，请重新设置")
            continue
        ratio = used / limit
        lines.append(f"- {category}: {used:g}/{limit:g} 元（{ratio:.0%}）")
    return "\n".join(lines)


def budget_warning_for_expense() -> str:
    if not BUDGETS_CSV.exists():
        return ""
    with BUDGETS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        budgets = list(csv.DictReader(f))
    warnings = []
    for period in ("week", "month"):
        start, end, title = period_range(period)
        expenses = rows_between(EXPENSES_CSV, start, end)
        for row in budgets:
            if row.get("period") != period:
                continue
            category = row.get("category") or "总额"
            limit = safe_amount(row.get("amount"))
            if limit <= 0:
                continue
            if category == "总额":
                used = sum(safe_amount(item.get("amount")) for item in expenses)
            else:
                used = sum(safe_amount(item.get("amount")) for item in expenses if item.get("category") == category)
            ratio = used / limit
            if ratio >= 1:
                warnings.append(f"{title}{category}预算已超出：{used:g}/{limit:g} 元")
            elif ratio >= 0.9:
                warnings.append(f"{title}{category}预算已经到 {ratio:.0%}：{used:g}/{limit:g} 元")
    return "\n" + "\n".join(warnings[:3]) if warnings else ""


def add_todo(text: str) -> str | None:
    if text.startswith(("添加待办", "新增待办", "待办")) or "加入待办" in text:
        content = re.sub(r"^(添加待办|新增待办|待办)[:：]?", "", text).replace("加入待办", "").strip(" ：:，,。")
        if not content:
            return "待办内容没有看清楚。你可以说：添加待办 明天交作业"
        due_date = ""
        today = datetime.now().date()
        if "今天" in content:
            due_date = today.isoformat()
        elif "明天" in content:
            due_date = (today + timedelta(days=1)).isoformat()
        append_csv(TODOS_CSV, [uuid.uuid4().hex, content, "pending", due_date, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""])
        return f"已加入待办：{content}"
    return None


def list_todos() -> str:
    if not TODOS_CSV.exists():
        return "暂无待办。"
    with TODOS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [row for row in csv.DictReader(f) if row.get("status") == "pending"]
    if not rows:
        return "暂无待办。"
    lines = ["待办："]
    for index, row in enumerate(rows[:20], 1):
        due = f"（{row.get('due_date')}）" if row.get("due_date") else ""
        lines.append(f"{index}. {row.get('text', '')}{due}")
    return "\n".join(lines)


def complete_todo(text: str) -> str | None:
    if not any(word in text for word in ("完成待办", "待办完成", "完成了", "做完了")):
        return None
    query = re.sub(r"(完成待办|待办完成|完成了|做完了|第|个)", "", text).strip(" ：:，,。")
    if not TODOS_CSV.exists():
        return "暂无待办。"
    with TODOS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ["id", "text", "status", "due_date", "created_at", "done_at"]
    pending = [row for row in rows if row.get("status") == "pending"]
    target = None
    if query.isdigit() and 1 <= int(query) <= len(pending):
        target = pending[int(query) - 1]
    else:
        for row in pending:
            if query and query in row.get("text", ""):
                target = row
                break
    if target is None:
        return "没找到要完成的待办。你可以发：待办列表，然后说：完成待办1"
    target["status"] = "done"
    target["done_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with TODOS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return f"已完成：{target.get('text', '')}"


def expense_query(text: str) -> str | None:
    if not any(word in text for word in ("花了多少", "多少钱", "消费多少", "开销多少", "支出多少", "查账")):
        return None
    if "今天" in text or "今日" in text:
        period = "today"
    elif "本周" in text or "这周" in text:
        period = "week"
    else:
        period = "month"
    start, end, title = period_range(period)
    rows = rows_between(EXPENSES_CSV, start, end)
    category = ""
    for name in ("餐饮", "交通", "购物", "居住", "娱乐", "医疗", "学习", "其他"):
        if name in text:
            category = name
            break
    keyword = ""
    match = re.search(r"(.+?)(?:花了多少|多少钱|消费多少|开销多少|支出多少)", text)
    if match:
        keyword = match.group(1).replace("我", "").replace("这周", "").replace("本周", "").replace("这个月", "").replace("本月", "").replace("今天", "").strip()
    filtered = rows
    if category:
        filtered = [row for row in filtered if row.get("category") == category]
    elif keyword:
        filtered = [row for row in filtered if keyword in row.get("item", "") or keyword in row.get("category", "")]
    total = sum(safe_amount(row.get("amount")) for row in filtered)
    lines = [f"{title}{category or keyword or '总'}消费：{total:g} 元"]
    for row in filtered[-8:]:
        lines.append(f"- {row.get('date', '')} {row.get('item', '')} {safe_amount(row.get('amount')):g} 元 [{row.get('category', '')}]")
    return "\n".join(lines)


def important_date_notice_today() -> str:
    if not DATES_CSV.exists():
        return ""
    today = datetime.now().date()
    lines = []
    with DATES_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                day = datetime.strptime(row.get("date", ""), "%Y-%m-%d").date()
            except ValueError:
                continue
            remind_days = safe_int(row.get("remind_days"))
            annual_day = day.replace(year=today.year)
            if annual_day == today:
                lines.append(f"- 今天：{row.get('title', '')}")
            elif remind_days and today <= annual_day <= today + timedelta(days=remind_days):
                left = (annual_day - today).days
                lines.append(f"- {left} 天后：{row.get('title', '')}（{annual_day.isoformat()}）")
    if not lines:
        return ""
    return "今天的重要事项提醒：\n" + "\n".join(lines[:8])


def append_failure_protection_notice(state: dict, chat_id: int, reply) -> str | dict:
    today = datetime.now().date()
    key = str(chat_id)
    last_seen = state.setdefault("last_interaction_dates", {})
    sent = state.setdefault("failure_protection_sent", {})
    notice = ""
    last_text = last_seen.get(key, "")
    if last_text:
        try:
            last_day = datetime.strptime(last_text, "%Y-%m-%d").date()
            if (today - last_day).days >= 3 and sent.get(key) != today.isoformat():
                notice = "好几天没记录也没关系，从今天继续接上就行。"
                sent[key] = today.isoformat()
        except ValueError:
            pass
    last_seen[key] = today.isoformat()
    if not notice:
        return reply
    if isinstance(reply, dict) and reply.get("type") == "multi":
        reply.setdefault("messages", []).insert(0, notice)
        return reply
    if isinstance(reply, dict):
        return {"type": "multi", "messages": [notice], "photos": [reply] if reply.get("type") == "photo" else []}
    return notice + "\n\n" + str(reply)

def append_first_daily_notice(state: dict, chat_id: int, reply: str) -> str:
    today = datetime.now().date().isoformat()
    key = str(chat_id)
    notices = state.setdefault("date_notice_sent", {})
    if notices.get(key) == today:
        return reply
    notice = important_date_notice_today()
    notices[key] = today
    if not notice:
        return reply
    return reply + "\n\n" + notice


def intent_hint_count(text: str) -> int:
    trend_hint = mood_trend_period_from_text(text) is not None
    view_action = view_action_from_text(text)
    view_name = (view_action or {}).get("name", "")
    budget_hint = any(word in text for word in ("预算", "限额")) and view_name != "budget"
    todo_hint = (any(word in text for word in ("待办", "任务", "清单", "交作业")) or ("复习" in text and not has_study_plan_hint(text))) and view_name != "todo"
    goal_hint = parse_goal_target(text) is not None
    progress_hint = parse_goal_progress(text) is not None
    completion_hint = task_completion_words(text) and not progress_hint
    reminder_hint = (any(word in text for word in ("提醒", "叫我", "通知", "闹钟", "每天", "每周", "每月")) or has_event_hint(text)) and view_name != "reminders" and not goal_hint
    note_hint = is_explicit_note_request(text)
    hints = [
        goal_hint,
        progress_hint,
        completion_hint,
        note_hint,
        budget_hint,
        todo_hint,
        reminder_hint,
        has_weather_hint(text),
        chart_period_from_text(text) is not None,
        summary_period_from_text(text) is not None,
        view_action is not None,
        daily_report_kind_from_text(text) is not None,
        trend_hint,
        has_study_plan_hint(text),
        has_chat_hint(text),
        is_mood_statement(text) and not trend_hint,
        has_expense_hint(text),
        has_income_hint(text),
    ]
    return sum(1 for hit in hints if hit)


def has_multi_intent_hint(text: str) -> bool:
    return intent_hint_count(text) >= 2


def save_todo_action(parsed: dict) -> str:
    lines = []
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in parsed.get("items", []):
        content = str(item.get("text") or item.get("content") or "").strip()
        if not content:
            continue
        due_date = str(item.get("due_date") or "").strip()
        append_csv(TODOS_CSV, [uuid.uuid4().hex, content, "pending", due_date, created_at, ""])
        due = f"（{due_date}）" if due_date else ""
        lines.append(f"- {content}{due}")
    if not lines:
        return "没有识别到可保存的待办。"
    return "已加入待办：\n" + "\n".join(lines)


def save_budget_action(parsed: dict) -> str:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    if BUDGETS_CSV.exists():
        with BUDGETS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    lines = []
    valid_categories = {"总额", "餐饮", "交通", "购物", "居住", "娱乐", "医疗", "学习", "其他"}
    for item in parsed.get("items", []):
        period = str(item.get("period") or "month").strip().lower()
        if period not in {"month", "week"}:
            period = "month"
        category = str(item.get("category") or "总额").strip()
        if category not in valid_categories:
            category = "总额"
        try:
            amount = safe_amount(item.get("amount"))
        except (TypeError, ValueError):
            continue
        rows = [row for row in rows if not (row.get("period") == period and row.get("category") == category)]
        rows.append({"period": period, "category": category, "amount": f"{amount:g}", "created_at": created_at, "id": uuid.uuid4().hex})
        title = "本周" if period == "week" else "本月"
        lines.append(f"- {title}{category}预算 {amount:g} 元")
    with BUDGETS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["period", "category", "amount", "created_at", "id"])
        writer.writeheader()
        writer.writerows(rows)
    if not lines:
        return "没有识别到可保存的预算。"
    return "已设置预算：\n" + "\n".join(lines)


def chinese_number_to_int(text: str) -> int | None:
    text = str(text or "").strip()
    if text.isdigit():
        return int(text)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text in digits:
        return digits[text]
    if text == "十":
        return 10
    if text.startswith("十") and len(text) == 2:
        return 10 + digits.get(text[1], 0)
    if text.endswith("十") and len(text) == 2:
        return digits.get(text[0], 0) * 10
    if "十" in text:
        left, right = text.split("十", 1)
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    return None


def parse_time_expression(text: str) -> datetime | None:
    now = datetime.now()
    day = now.date()
    explicit_today = False
    if "后天" in text:
        day = day + timedelta(days=2)
    elif "明天" in text:
        day = day + timedelta(days=1)
    elif "今天" in text or "今晚" in text:
        explicit_today = True
    match = re.search(r"(凌晨|早上|上午|中午|下午|晚上|今晚)?\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*点\s*(半|\d{1,2}分?|[一二三四五六七八九十]{1,3}分?)?", text)
    if not match:
        return None
    period = match.group(1) or ""
    if not period and ("今晚" in text or "晚上" in text or "夜里" in text):
        period = "晚上"
    hour = chinese_number_to_int(match.group(2))
    if hour is None or hour > 24:
        return None
    minute_text = match.group(3) or ""
    minute = 0
    if minute_text == "半":
        minute = 30
    elif minute_text:
        minute_text = minute_text.replace("分", "")
        parsed_minute = chinese_number_to_int(minute_text)
        if parsed_minute is not None:
            minute = parsed_minute
    if period in {"下午", "晚上", "今晚"} and 1 <= hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    if hour == 24:
        hour = 0
        day = day + timedelta(days=1)
    try:
        remind_at = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    except ValueError:
        return None
    if remind_at <= now and not explicit_today and "明天" not in text and "后天" not in text:
        remind_at = remind_at + timedelta(days=1)
    if remind_at <= now:
        return None
    return remind_at


def local_event_reminder_action(text: str) -> dict | None:
    if not has_event_hint(text):
        return None
    remind_at = parse_time_expression(text)
    if remind_at is None:
        return None
    event_words = ("考试", "面试", "开会", "会议", "上课", "报名", "体检", "答辩", "比赛", "聚餐", "交作业", "纪念日", "生日")
    title = next((word for word in event_words if word in text), "")
    if not title:
        match = re.search(r"(?:提醒我|叫我|通知我|提醒|闹钟)(.+)$", text)
        if match:
            raw_title = match.group(1)
            raw_title = re.sub(r"(今天|明天|后天|今晚|早上|上午|中午|下午|晚上|凌晨|每天|每周|每月|\d{1,2}\s*[点:]\d{0,2}|\d{1,2}\s*点(?:半|\d{1,2}分?)?|[一二两三四五六七八九十半]+\s*点(?:半|[一二三四五六七八九十]+分?)?|如果|就|的话|，|,|。)", " ", raw_title)
            title = raw_title.strip(" ：:，,。 ")
    title = title or "事项"
    return {"type": "reminder", "items": [{"remind_at": remind_at.strftime("%Y-%m-%d %H:%M:%S"), "text": title, "repeat": "none"}]}


def action_list(parsed: dict) -> list[dict]:
    if isinstance(parsed.get("actions"), list):
        return list(parsed.get("actions") or [])
    return [parsed]


def augment_parsed_actions(parsed: dict, text: str) -> dict:
    actions = action_list(parsed)
    changed = False

    note_action = local_note_action(text) if is_explicit_note_request(text) else None
    note_blocked_by_record = any((has_expense_hint(text), has_income_hint(text), is_mood_statement(text), has_weather_hint(text), has_event_hint(text), has_study_plan_hint(text)))
    if note_action and not note_blocked_by_record and not has_action_type(actions, "note"):
        actions.append(note_action)
        changed = True

    for record_action in local_record_actions_from_text(text):
        changed = merge_record_action(actions, record_action) or changed

    important_action = local_important_item_action(text)
    if important_action and not has_action_type(actions, "date"):
        actions.append(important_action)
        changed = True

    if is_mood_statement(text) and not has_action_type(actions, "mood"):
        actions.append(local_mood_parse(text))
        changed = True

    if has_weather_hint(text) and not has_action_type(actions, "weather"):
        actions.append({"type": "weather", "text": text})
        changed = True

    chart_period = chart_period_from_text(text)
    if chart_period and not has_action_type(actions, "chart"):
        actions.append({"type": "chart", "period": chart_period})
        changed = True

    summary_period = summary_period_from_text(text)
    if summary_period and not has_action_type(actions, "summary"):
        actions.append({"type": "summary", "period": summary_period})
        changed = True

    view_action = view_action_from_text(text)
    if view_action and not has_action_type(actions, "view"):
        actions.append(view_action)
        changed = True

    trend_period = mood_trend_period_from_text(text)
    if trend_period and not has_action_type(actions, "mood_trend"):
        actions.append({"type": "mood_trend", "period": trend_period})
        changed = True

    if has_study_plan_hint(text) and not has_action_type(actions, "study_plan"):
        actions.append(local_study_plan_action(text))
        changed = True

    extra_reminder = local_extra_reminder_action(text)
    if extra_reminder and not has_action_type(actions, "reminder"):
        actions.append(extra_reminder)
        changed = True

    if has_chat_hint(text) and not has_action_type(actions, "answer"):
        actions.append({"type": "answer", "answer": local_chat_reply(text)})
        changed = True

    if not has_action_type(actions, "reminder") and not has_action_type(actions, "date"):
        reminder = local_event_reminder_action(text)
        if reminder:
            actions.append(reminder)
            changed = True

    if not changed:
        return parsed
    if len(actions) == 1:
        return actions[0]
    return {"actions": actions}


def action_contains_note(action: dict) -> bool:
    return isinstance(action, dict) and action.get("type") == "note"


def without_unrequested_notes(parsed: dict, text: str, chat_id: int | None) -> dict:
    if is_explicit_note_request(text):
        return parsed
    actions = action_list(parsed)
    if not any(action_contains_note(action) for action in actions):
        return parsed
    kept = [action for action in actions if not action_contains_note(action)]
    if kept:
        return kept[0] if len(kept) == 1 else {"actions": kept}
    if is_life_note_candidate(text):
        return {"type": "answer", "answer": chat_then_queue_pending_note_confirmation(text, chat_id)}
    return {"type": "answer", "answer": local_chat_reply(text)}

def execute_action(action: dict, chat_id: int | None, config: dict | None = None) -> str | dict:
    kind = action.get("type")
    if kind == "date":
        return save_date_action(action, chat_id)
    if kind == "reminder":
        if chat_id is None:
            return "提醒需要在 Telegram 对话里设置。"
        return save_reminder(action, chat_id)
    if kind == "todo":
        return save_todo_action(action)
    if kind == "budget":
        return save_budget_action(action)
    if kind == "study_plan":
        return create_study_plan(config or {}, action)
    if kind == "mood_trend":
        return mood_trend_reply(normalize_period(action_value(action, "period", default="month"), "month"))
    if kind == "weather":
        return weather_answer(config or {}, action.get("text") or "")
    if kind == "chart":
        return finance_chart_reply(normalize_period(action_value(action, "period", default="month"), "month"))
    if kind == "summary":
        return period_summary(config or {}, normalize_period(action_value(action, "period", default="today"), "today"))
    if kind == "view":
        return view_reply(action, chat_id)
    if kind == "update":
        return update_record(action, chat_id)
    return save_parsed(action)

def execute_parsed_result(parsed: dict, chat_id: int | None, config: dict | None = None, source_text: str = "") -> str | dict:
    if "actions" not in parsed:
        action_types = {str(parsed.get("type") or "")}
        reply = execute_action(parsed, chat_id, config)
        return with_support_layer(reply, source_text, action_types)
    replies = []
    seen = set()
    action_types = set()
    actions = [action for action in parsed.get("actions", []) if isinstance(action, dict)]
    for action in actions:
        if should_skip_answer_action(action, actions):
            continue
        action_types.add(str(action.get("type") or ""))
        key = json.dumps(action, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        reply = execute_action(action, chat_id, config)
        if isinstance(reply, str):
            reply = reply.strip()
        if reply:
            replies.append(reply)
    combined = combine_reply_parts(replies)
    return with_support_layer(combined, source_text, action_types)


def pending_center_store(state: dict) -> dict:
    return state.setdefault("pending_confirmations", {})


def set_pending_center(state: dict, chat_id: int | None, kind: str) -> None:
    if chat_id is None:
        return
    pending_center_store(state)[str(chat_id)] = {"kind": kind, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def clear_pending_center(state: dict, chat_id: int | None, kind: str | None = None) -> None:
    if chat_id is None:
        return
    store = pending_center_store(state)
    item = store.get(str(chat_id))
    if item and (kind is None or item.get("kind") == kind):
        store.pop(str(chat_id), None)


def chinese_index_to_int(text: str) -> int | None:
    text = str(text or "").strip()
    aliases = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "第一个": 1, "第一个吧": 1, "第一个就行": 1, "第二个": 2, "第三个": 3}
    if text in aliases:
        return aliases[text]
    value = chinese_number_to_int(text)
    return value if value and value > 0 else None


def confirmation_intent(text: str) -> dict:
    stripped = text.strip()
    lowered = stripped.lower()
    cancel_words = {"取消", "不用", "不用了", "算了", "先不", "不设", "不记", "别记", "不要", "不用处理"}
    confirm_words = {"确认", "确定", "可以", "对", "是", "好", "嗯", "行", "就这个", "这个", "没错", "记下", "保存", "设定", "设置"}
    if stripped in cancel_words:
        return {"cancel": True}
    if stripped in {"任务", "设为任务", "今日任务", "每日任务", "打卡", "目标"}:
        return {"index": 1, "choice": "task"}
    if stripped in {"提醒", "设为提醒", "重复提醒", "闹钟", "通知"}:
        return {"index": 2, "choice": "reminder"}
    if lowered.isdigit():
        return {"index": int(lowered)}
    match = re.search(r"第?\s*(\d{1,2}|[一二两三四五六七八九十])\s*(?:个|条|项|号)?", stripped)
    if match:
        value = match.group(1)
        return {"index": int(value) if value.isdigit() else chinese_index_to_int(value)}
    index = chinese_index_to_int(stripped)
    if index:
        return {"index": index}
    if stripped in confirm_words:
        return {"confirm": True}
    return {}


def active_pending_confirmation_kind(state: dict, chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    key = str(chat_id)
    center = pending_center_store(state).get(key)
    if center:
        kind = center.get("kind")
        if kind == "note" and note_pending_store(state).get(key):
            return kind
        if kind == "task_completion" and pending_task_store(state).get(key):
            return kind
        if kind == "routine" and pending_routine_store(state).get(key):
            return kind
        if kind == "record_action" and pending_record_action_store(state).get(key):
            return kind
    if note_pending_store(state).get(key):
        return "note"
    if pending_task_store(state).get(key):
        return "task_completion"
    if pending_routine_store(state).get(key):
        return "routine"
    if pending_record_action_store(state).get(key):
        return "record_action"
    return None


def handle_pending_confirmation_center(config: dict, text: str, chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    state = read_state()
    kind = active_pending_confirmation_kind(state, chat_id)
    intent = confirmation_intent(text)
    if not kind:
        if is_note_confirmation(text):
            return "现在没有等待确认的生活事项。你可以说：记一下今天去了图书馆。"
        return None
    if kind == "note":
        if intent.get("cancel"):
            return handle_pending_note_confirmation("不用", chat_id)
        if intent.get("confirm") or intent.get("index") == 1 or is_note_confirmation(text):
            return handle_pending_note_confirmation("记下", chat_id)
        return None
    if kind == "task_completion":
        if intent.get("cancel"):
            return handle_pending_task_completion("取消", chat_id)
        if intent.get("index"):
            return handle_pending_task_completion(str(intent.get("index")), chat_id)
        items = pending_task_store(state).get(str(chat_id), {}).get("items") or []
        if intent.get("confirm") and len(items) == 1:
            return handle_pending_task_completion("1", chat_id)
        return None
    if kind == "routine":
        if intent.get("cancel"):
            return handle_pending_routine_confirmation(config, "取消", chat_id)
        if intent.get("choice") == "task" or intent.get("index") == 1:
            return handle_pending_routine_confirmation(config, "1", chat_id)
        if intent.get("choice") == "reminder" or intent.get("index") == 2:
            return handle_pending_routine_confirmation(config, "2", chat_id)
        if intent.get("confirm"):
            return "这个需要选一种：回复 1/任务，或 2/提醒。"
        return None
    if kind == "record_action":
        return handle_pending_record_action(text, chat_id, intent)
    return None

def handle_text(config: dict, text: str, reply_context: str = "", chat_id: int | None = None) -> str | dict:
    text = text.strip()
    if text in {"/start", "/help", "帮助"}:
        return "直接发记录或问题都可以：\n午饭 23，奶茶 15\n兼职收入 200\n每天学习python 15min\n我学习python学了10min\n7月12日妈妈生日，提前3天提醒\n明天早上8点提醒我起床\n添加待办 明天交作业\n记一下今天去了图书馆\n设置本月餐饮预算800\n帮我把一周算法复习拆成计划\n本周娱乐花了多少\n我最近钱花哪了\n切换严格模式\n\n命令：\n/today 今日总结\n/week 本周总结\n/month 本月总结\n/year 今年总结\n/chart 本月收支图\n/chart year 今年收支图\n/morning 晨报\n/evening 晚报\n心情趋势\n/dates 查看重要事项\n/recent 查看最近记录\n/reminders 提醒列表\n/todo 今日任务\n/budget 预算情况\n/mood 倾诉/鼓励模式\n\n普通聊天不会自动记入生活事项；想记生活日志可以说：记一下……\n也可以直接发小票/支付截图；若电脑装了 OCR，会尝试自动记账。"

    tone_reply = set_tone_mode_reply(text)
    if tone_reply:
        return tone_reply

    pending_result = handle_pending_confirmation_center(config, text, chat_id)
    if pending_result:
        return pending_result
    update_action = local_update_action(text, chat_id)
    if update_action:
        if update_action.get("type") == "answer":
            return update_action.get("answer", "")
        return resolve_or_queue_record_action("update", update_action, chat_id)

    if is_delete_request(text):
        if reply_context:
            result = delete_from_reply_context(reply_context)
            if result:
                return result
        parsed_delete = local_delete_action(text, chat_id)
        if parsed_delete:
            if parsed_delete.get("type") == "answer":
                return parsed_delete.get("answer", "")
            return resolve_or_queue_record_action("delete", parsed_delete, chat_id)

    routine_prompt = routine_confirmation_prompt(text, chat_id)
    if routine_prompt:
        parts = [routine_prompt]
        if is_mood_statement(text):
            parts.append(save_parsed(local_mood_parse(text)))
        return combine_reply_parts(parts)

    important_action = local_important_item_action(text)
    if important_action and not has_multi_intent_hint(text):
        return with_support_layer(execute_action(important_action, chat_id, config), text, {"date"})

    if is_explicit_note_request(text) and not has_multi_intent_hint(text):
        note_action = local_note_action(text)
        if note_action:
            return save_parsed(note_action)
        return "要记的内容我没看清。你可以这样说：记一下今天去了图书馆。"

    natural_todo_reply = natural_todo_creation_reply(text)
    if natural_todo_reply:
        return with_support_layer(natural_todo_reply, text, {"todo"})

    goal_reply = save_goal_from_text(text, chat_id)
    if goal_reply:
        if not has_multi_intent_hint(text):
            return with_support_layer(goal_reply, text, {"goal"})
        prompt_text = text
        if reply_context:
            prompt_text = f"用户引用的上一条机器人消息：\n{reply_context}\n\n用户新消息：{text}"
        parsed = call_deepseek(config, prompt_text)
        parsed = augment_parsed_actions(parsed, text)
        parsed = without_unrequested_notes(parsed, text, chat_id)
        return combine_reply_parts([goal_reply, execute_parsed_result(parsed, chat_id, config, text)])

    progress_reply = save_goal_progress_from_text(text)
    if progress_reply:
        if not has_multi_intent_hint(text):
            return with_support_layer(progress_reply, text, {"progress"})
        prompt_text = text
        if reply_context:
            prompt_text = f"用户引用的上一条机器人消息：\n{reply_context}\n\n用户新消息：{text}"
        parsed = call_deepseek(config, prompt_text)
        parsed = augment_parsed_actions(parsed, text)
        parsed = without_unrequested_notes(parsed, text, chat_id)
        return combine_reply_parts([progress_reply, execute_parsed_result(parsed, chat_id, config, text)])

    task_complete_reply = complete_task_from_text(text, chat_id)
    if task_complete_reply:
        if is_complete_all_tasks_request(text) or task_completion_index_from_text(text) or not has_multi_intent_hint(text):
            return with_support_layer(task_complete_reply, text, {"todo"})
        prompt_text = text
        if reply_context:
            prompt_text = f"用户引用的上一条机器人消息：\n{reply_context}\n\n用户新消息：{text}"
        parsed = call_deepseek(config, prompt_text)
        parsed = augment_parsed_actions(parsed, text)
        parsed = without_unrequested_notes(parsed, text, chat_id)
        return combine_reply_parts([task_complete_reply, execute_parsed_result(parsed, chat_id, config, text)])

    history_reply = history_search_reply(text)
    if history_reply:
        return history_reply

    report_kind = daily_report_kind_from_text(text)
    if report_kind and not has_multi_intent_hint(text):
        return daily_report_reply(config, report_kind)

    trend_period = mood_trend_period_from_text(text)
    if trend_period and not has_multi_intent_hint(text):
        return mood_trend_reply(trend_period)

    chart_period = chart_period_from_text(text)
    if chart_period and not has_multi_intent_hint(text):
        return finance_chart_reply(chart_period)

    period = summary_period_from_text(text)
    if period and not has_multi_intent_hint(text):
        return period_summary(config, period)

    view_action = view_action_from_text(text)
    if view_action and not has_multi_intent_hint(text):
        return view_reply(view_action, chat_id)

    if text in {"统计", "本月统计"}:
        return period_summary(config, "month")
    if text in {"/dates", "重要日期"}:
        return list_dates()
    if text in {"/recent", "最近记录", "最近"}:
        return recent_records(chat_id=chat_id)
    if text in {"/reminders", "提醒列表", "待提醒"}:
        return list_reminders()
    if text in {"/todo", "待办", "待办列表", "今日任务", "任务列表", "今天任务"}:
        return goal_status_reply()
    if text in {"/budget", "预算", "预算情况"}:
        return budget_status("month")
    local_result = None
    if not has_multi_intent_hint(text):
        local_result = set_budget(text) or add_todo(text) or complete_todo(text) or expense_query(text)
    if local_result:
        return local_result
    if not has_multi_intent_hint(text):
        local_record = local_simple_income_parse(text) or local_simple_expense_parse(text)
        if local_record:
            return save_parsed(local_record)
    if text.startswith("/mood"):
        content = text.replace("/mood", "", 1).strip()
        if not content:
            return "你可以这样发：\n/mood 今天有点烦，事情很多但不想动"
        saved = save_parsed(local_mood_parse(content))
        return saved + "\n\n" + companion_answer(config, content)

    if is_weather_question(text) and not has_multi_intent_hint(text):
        return with_support_layer(weather_answer(config, text), text, {"weather"})
    if has_weather_hint(text) and is_mood_statement(text):
        parsed = {"actions": [{"type": "weather", "text": text}, local_mood_parse(text)]}
        return execute_parsed_result(parsed, chat_id, config, text)
    if has_chat_hint(text) and not has_multi_intent_hint(text):
        return safe_companion_reply(config, text)
    if should_confirm_life_note(text, chat_id) and not has_multi_intent_hint(text):
        return chat_then_queue_pending_note_confirmation(text, chat_id)

    if is_mood_statement(text) and not has_multi_intent_hint(text):
        return save_parsed(local_mood_parse(text))

    prompt_text = text
    if reply_context:
        prompt_text = f"用户引用的上一条机器人消息：\n{reply_context}\n\n用户新消息：{text}"
    parsed = call_deepseek(config, prompt_text)
    parsed = augment_parsed_actions(parsed, text)
    parsed = without_unrequested_notes(parsed, text, chat_id)
    return execute_parsed_result(parsed, chat_id, config, text)

def acquire_single_instance_lock():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        return None
    return mutex

def main() -> None:
    mutex = acquire_single_instance_lock()
    if mutex is None:
        print("LifeRecordBot is already running. This duplicate instance will exit.")
        return
    config = load_config()
    ensure_files()
    token = config["telegram_bot_token"]
    allowed_user_ids = set(config["allowed_user_ids"])
    print("LifeRecordBot started. Keep this window open. Press Ctrl+C to stop.")
    while True:
        try:
            dispatch_due_reminders(token)
            dispatch_daily_reports(token, config)
            dispatch_goal_reminders(token, config)
            state = read_state()
            updates = http_json(
                tg_url(token, "getUpdates"),
                {"offset": int(state.get("offset", 0)), "timeout": 45, "allowed_updates": ["message"]},
                timeout=60,
            )
            for update in updates.get("result", []):
                state["offset"] = update["update_id"] + 1
                write_state(state)
                append_raw(update)
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                user = message.get("from") or {}
                chat_id = chat.get("id")
                user_id = user.get("id")
                text = message.get("text") or ""
                reply_message = message.get("reply_to_message") or {}
                quote = message.get("quote") or {}
                reply_context = quote.get("text") or reply_message.get("text") or ""
                if not chat_id:
                    continue
                if allowed_user_ids and user_id not in allowed_user_ids:
                    send_message(token, chat_id, "未授权用户。")
                    continue
                try:
                    if text:
                        reply = handle_text(config, text, reply_context, chat_id)
                    elif image_file_id_from_message(message):
                        reply = handle_photo_message(config, token, message, chat_id)
                    else:
                        continue
                    latest_state = read_state()
                    remember_chat(latest_state, chat_id)
                    reply = append_failure_protection_notice(latest_state, chat_id, reply)
                    if isinstance(reply, dict):
                        notice = append_first_daily_notice(latest_state, chat_id, "").strip()
                        if notice:
                            send_message(token, chat_id, notice)
                    else:
                        reply = append_first_daily_notice(latest_state, chat_id, reply)
                    write_state(latest_state)
                except Exception as exc:
                    reply = f"处理失败：{exc}"
                try:
                    send_reply(token, chat_id, reply)
                except Exception as exc:
                    send_message(token, chat_id, f"回复发送失败：{exc}")
        except KeyboardInterrupt:
            print("Stopped.")
            break
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP error: {exc.code} {detail}")
            time.sleep(5)
        except error.URLError as exc:
            print(f"Network error: {exc}")
            time.sleep(5)
        except Exception as exc:
            print(f"Runtime error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()


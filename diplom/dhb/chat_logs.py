import asyncio
import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


DHB_DIR = Path(os.getenv("DHB_DIR", "dhb/data"))
CHAT_LOG_PATH = Path(os.getenv("CHAT_LOG_PATH", str(DHB_DIR / "chat_logs.jsonl")))
GOOGLE_SHEETS_LOG_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_LOG_WEBHOOK_URL", "")
GOOGLE_SHEETS_LOG_READ_URL = os.getenv("GOOGLE_SHEETS_LOG_READ_URL", GOOGLE_SHEETS_LOG_WEBHOOK_URL)


FIELD_ALIASES = {
    "time": ("time", "timestamp", "date", "datetime", "created_at", "created"),
    "email": ("email", "user", "mail", "почта"),
    "question": ("question", "prompt", "message", "query", "вопрос"),
    "answer": ("answer", "response", "reply", "ответ"),
}


def _append_local(payload):
    CHAT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHAT_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


async def _append_google_sheet(payload):
    if not GOOGLE_SHEETS_LOG_WEBHOOK_URL:
        return {"sheet_logged": False, "reason": "GOOGLE_SHEETS_LOG_WEBHOOK_URL is not configured"}

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(GOOGLE_SHEETS_LOG_WEBHOOK_URL, json=payload)
        response.raise_for_status()

    return {"sheet_logged": True}


def _value(row, names):
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_row(row):
    if not isinstance(row, dict):
        return None

    return {
        "time": _value(row, FIELD_ALIASES["time"]),
        "email": _value(row, FIELD_ALIASES["email"]).lower(),
        "question": _value(row, FIELD_ALIASES["question"]),
        "answer": _value(row, FIELD_ALIASES["answer"]),
    }


def _filter_rows(rows, email, limit):
    email = email.strip().lower()
    limit = max(1, min(int(limit or 200), 500))
    result = []
    for row in rows:
        item = _normalize_row(row)
        if not item or item["email"] != email:
            continue
        if item["question"] or item["answer"]:
            result.append(item)
    return result[-limit:]


def _load_local(email, limit):
    if not CHAT_LOG_PATH.exists():
        return []

    rows = []
    with CHAT_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return _filter_rows(rows, email, limit)


def _rows_from_json(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "records", "rows", "data", "history"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _rows_from_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


async def _load_google_sheet(email, limit):
    if not GOOGLE_SHEETS_LOG_READ_URL:
        return {"items": [], "source": "google_sheet", "error": "GOOGLE_SHEETS_LOG_READ_URL is not configured"}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(GOOGLE_SHEETS_LOG_READ_URL, params={"email": email, "limit": limit})
        response.raise_for_status()

    text = response.text.strip()
    if not text:
        return {"items": [], "source": "google_sheet", "error": "empty response"}

    try:
        rows = _rows_from_json(response.json())
    except Exception:
        rows = _rows_from_csv(text)

    return {"items": _filter_rows(rows, email, limit), "source": "google_sheet"}


async def load_chat_history(email, limit=200):
    local_items = await asyncio.to_thread(_load_local, email, limit)

    try:
        sheet_result = await _load_google_sheet(email, limit)
    except Exception as exc:
        return {
            "source": "local_jsonl",
            "items": local_items,
            "sheet_error": repr(exc),
        }

    sheet_items = sheet_result.get("items", [])
    if sheet_items:
        return {
            "source": "google_sheet",
            "items": sheet_items,
            "local_items": len(local_items),
        }

    return {
        "source": "local_jsonl",
        "items": local_items,
        "sheet_error": sheet_result.get("error"),
    }


async def save_chat_log(email, question, answer):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email": email,
        "question": question,
        "answer": answer,
    }

    await asyncio.to_thread(_append_local, payload)

    try:
        sheet_result = await _append_google_sheet(payload)
    except Exception as exc:
        sheet_result = {"sheet_logged": False, "error": repr(exc)}

    return {
        "status": "logged",
        "local_path": str(CHAT_LOG_PATH),
        **sheet_result,
    }
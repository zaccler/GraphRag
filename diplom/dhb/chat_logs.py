import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


DHB_DIR = Path(os.getenv("DHB_DIR", "dhb/data"))
CHAT_LOG_PATH = Path(os.getenv("CHAT_LOG_PATH", str(DHB_DIR / "chat_logs.jsonl")))
GOOGLE_SHEETS_LOG_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_LOG_WEBHOOK_URL", "")


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

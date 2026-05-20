import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx


TEXT_DB_SHEET_LOG_PATH = Path(os.getenv("TEXT_DB_SHEET_LOG_PATH", "dhb/data/text_db_rows.jsonl"))
TEXT_DB_SHEET_MAX_TEXT_CHARS = int(os.getenv("TEXT_DB_SHEET_MAX_TEXT_CHARS", "45000"))
GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL", "")


def _clean_cell(value, limit=None):
    text = (value or "").replace("\x00", "").strip()
    if limit and len(text) > limit:
        return f"{text[:limit]}\n\n[truncated: {len(text) - limit} chars]"
    return text


def _meta(text, *keys):
    keys = {key.upper() for key in keys}
    for line in text.splitlines():
        match = re.match(r"\s*([A-Z_]+):\s*(.*)\s*$", line)
        if match and match.group(1).upper() in keys:
            return match.group(2).strip()
    return ""


def _short_path(path):
    try:
        value = str(path.relative_to(Path.cwd()))
    except ValueError:
        value = str(path)
    return value.replace("\\", "/")


def _record_from_file(file_path, source_kind):
    path = Path(file_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    file_name = _short_path(path)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_key": file_name,
        "source_kind": source_kind,
        "title": _clean_cell(_meta(text, "TITLE") or path.stem),
        "url": _clean_cell(_meta(text, "SOURCE_URL", "URL")),
        "source_type": _clean_cell(_meta(text, "SOURCE_TYPE")),
        "package_manager": _clean_cell(_meta(text, "PACKAGE_MANAGER")),
        "package_id": _clean_cell(_meta(text, "PACKAGE_ID", "PACKAGE", "REPOSITORY")),
        "version": _clean_cell(_meta(text, "VERSION", "TAG")),
        "download_url": _clean_cell(_meta(text, "DOWNLOAD_URL", "HTML_URL")),
        "file_path": file_name,
        "text": _clean_cell(text, TEXT_DB_SHEET_MAX_TEXT_CHARS),
    }
    return record


def _save_local(records):
    TEXT_DB_SHEET_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TEXT_DB_SHEET_LOG_PATH.open("a", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _send_to_google_sheet(records):
    if not records:
        return {"sheet_logged": False, "reason": "no records"}
    if not GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL:
        return {"sheet_logged": False, "reason": "GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL is not configured"}

    with httpx.Client(timeout=30) as client:
        response = client.post(GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL, json={"records": records})
        response.raise_for_status()

    return {"sheet_logged": True, "records": len(records)}


def mirror_text_db_files(file_paths, source_kind, max_files=None):
    files = list(file_paths)
    if max_files and max_files > 0:
        files = files[:max_files]

    records = []
    errors = []
    for file_path in files:
        try:
            records.append(_record_from_file(file_path, source_kind))
        except Exception as exc:
            errors.append({"file": str(file_path), "error": repr(exc)})

    if records:
        _save_local(records)

    try:
        result = _send_to_google_sheet(records)
    except Exception as exc:
        result = {"sheet_logged": False, "error": repr(exc)}

    result["records"] = len(records)
    result["errors"] = errors
    result["local_log"] = str(TEXT_DB_SHEET_LOG_PATH)
    return result

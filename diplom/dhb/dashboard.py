from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from xdt.pul import request_get
from xdt.scp.parser import google_sheet_csv_url, package_source_from_line, sanitize_filename


PACKAGE_KINDS = {
    "github",
    "nuget",
    "pypi",
    "python",
    "npm",
    "maven",
    "gradle",
    "crates",
    "cargo",
    "rust",
    "docker",
    "dockerhub",
    "go",
    "gomod",
}


def _value(row: dict[str, Any], *names: str):
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _enabled(row: dict[str, Any]):
    value = _value(row, "enabled", "ena", "active", "on")
    if not value:
        return True
    return value.lower() not in {"0", "false", "no", "off", "disabled"}


def _read_sheet_rows(sheet: dict[str, Any]):
    csv_url = google_sheet_csv_url(sheet)
    response = request_get(csv_url)
    response.raise_for_status()
    if not response.text.strip():
        raise ValueError(f"Dashboard Google Sheet returned empty CSV: {csv_url}")

    rows = list(csv.DictReader(io.StringIO(response.text)))
    return csv_url, rows


def _package_line(kind: str, value: str):
    source = package_source_from_line(f"{kind} {value}")
    if not source:
        raise ValueError(f"Unsupported package row: {kind} {value}")
    return f"{kind} {value}"


def _doc_source(row: dict[str, Any], source_type: str, value: str):
    code = _value(row, "cod", "code") or sanitize_filename(value or source_type)
    title = _value(row, "title", "name")
    max_rows = _value(row, "max_rows", "rows")

    if source_type == "python_docs":
        return {
            "code": code,
            "type": "python_docs",
            "root_url": value,
            "max_pages": int(_value(row, "max_pages", "pages") or "300"),
            "delay_sec": float(_value(row, "delay_sec", "delay") or "0.15"),
            "enabled": True,
        }

    if source_type == "google_sheet":
        source = {
            "code": code,
            "type": "google_sheet",
            "url": value,
            "gid": _value(row, "gid", "sheet_gid") or "0",
            "title": title or code,
            "enabled": True,
        }
        if max_rows:
            source["max_rows"] = int(max_rows)
        return source

    return {
        "code": code,
        "type": "doc_page",
        "url": value,
        "enabled": True,
    }


def sync_google_sheet_dashboard(sheet: dict[str, Any], output_dir: str = "dhb/data"):
    csv_url, rows = _read_sheet_rows(sheet)
    package_lines = []
    docs_sources = []
    skipped = []

    for index, row in enumerate(rows, start=2):
        if not _enabled(row):
            skipped.append({"row": index, "reason": "disabled"})
            continue

        kind = _value(row, "typ", "type", "kind").lower()
        value = _value(row, "url", "value", "package", "repo", "module", "image", "name")
        if not kind or not value:
            skipped.append({"row": index, "reason": "missing kind or value"})
            continue

        if kind in PACKAGE_KINDS:
            package_lines.append(_package_line(kind, value))
            continue

        if kind in {"doc", "docs", "doc_page", "page"}:
            docs_sources.append(_doc_source(row, "doc_page", value))
            continue

        if kind in {"python_docs", "python-docs"}:
            docs_sources.append(_doc_source(row, "python_docs", value))
            continue

        if kind in {"google_sheet", "sheet", "google-sheet"}:
            docs_sources.append(_doc_source(row, "google_sheet", value))
            continue

        skipped.append({"row": index, "reason": f"unsupported kind: {kind}"})

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    packages_path = out_dir / "packages.from_sheet.txt"
    docs_path = out_dir / "docs_registry.from_sheet.json"
    status_path = out_dir / "last_sync.json"

    packages_path.write_text(
        "# Generated from Google Sheet dashboard. Do not edit manually.\n" + "\n".join(package_lines) + "\n",
        encoding="utf-8",
    )
    docs_path.write_text(
        json.dumps({"sources": docs_sources}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = {
        "csv_url": csv_url,
        "rows": len(rows),
        "package_sources": len(package_lines),
        "docs_sources": len(docs_sources),
        "skipped": skipped,
        "packages_path": str(packages_path),
        "docs_registry_path": str(docs_path),
    }
    status_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

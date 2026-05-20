from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
USERS_PATH = DATA_DIR / "users.json"
JOBS_PATH = DATA_DIR / "jobs.json"
RAG_API_URL = os.getenv("RAG_API_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_CODE = os.getenv("MGR_ADMIN_CODE", "admin")

app = FastAPI(title="GraphRAG Manager Web", version="0.1.0")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

sessions: dict[str, dict[str, Any]] = {}


class AuthRequest(BaseModel):
    username: str
    password: str
    admin_code: str | None = None


class ChatRequest(BaseModel):
    question: str
    debug: bool = False


class GoogleSheetRequest(BaseModel):
    url: str | None = None
    csv_url: str | None = None
    sheet_id: str | None = None
    gid: str | None = None
    code: str | None = None
    title: str | None = None
    max_rows: int | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_PATH.exists():
        USERS_PATH.write_text("[]", encoding="utf-8")
    if not JOBS_PATH.exists():
        JOBS_PATH.write_text("[]", encoding="utf-8")


def load_users() -> list[dict[str, Any]]:
    ensure_data_dir()
    return json.loads(USERS_PATH.read_text(encoding="utf-8"))


def save_users(users: list[dict[str, Any]]) -> None:
    ensure_data_dir()
    USERS_PATH.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jobs() -> list[dict[str, Any]]:
    ensure_data_dir()
    return json.loads(JOBS_PATH.read_text(encoding="utf-8"))


def add_job(action: str, user: dict[str, Any], result: Any) -> dict[str, Any]:
    jobs = load_jobs()
    job = {
        "id": secrets.token_hex(8),
        "action": action,
        "username": user["username"],
        "created_at": now_iso(),
        "result": result,
    }
    jobs.append(job)
    JOBS_PATH.write_text(json.dumps(jobs[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return salt, digest.hex()


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, password_hash)


def clean_username(username: str) -> str:
    value = username.strip().lower()
    if len(value) < 3:
        raise HTTPException(status_code=400, detail="Логин должен быть не короче 3 символов")
    return value


def get_user_from_token(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Нужен вход")
    token = authorization.replace("Bearer ", "", 1).strip()
    user = sessions.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Сессия не найдена")
    return user


def require_admin(user: dict[str, Any] = Depends(get_user_from_token)) -> dict[str, Any]:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Нужны права админа")
    return user


async def call_rag(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{RAG_API_URL}{path}"
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.request(method, url, json=payload)
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    if not response.text:
        return {}
    return response.json()


@app.get("/")
async def index():
    return FileResponse(APP_DIR / "static" / "index.html")


@app.post("/auth/register")
async def register(request: AuthRequest):
    username = clean_username(request.username)
    if len(request.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 4 символов")

    users = load_users()
    if any(user["username"] == username for user in users):
        raise HTTPException(status_code=409, detail="Пользователь уже есть")

    is_first_user = len(users) == 0
    is_admin = is_first_user or request.admin_code == ADMIN_CODE
    salt, password_hash = hash_password(request.password)
    users.append(
        {
            "username": username,
            "salt": salt,
            "password_hash": password_hash,
            "is_admin": is_admin,
            "created_at": now_iso(),
        }
    )
    save_users(users)
    return {"status": "ok", "username": username, "is_admin": is_admin}


@app.post("/auth/login")
async def login(request: AuthRequest):
    username = clean_username(request.username)
    users = load_users()
    user = next((item for item in users if item["username"] == username), None)
    if not user or not verify_password(request.password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = secrets.token_urlsafe(32)
    session_user = {"username": user["username"], "is_admin": bool(user.get("is_admin"))}
    sessions[token] = session_user
    return {"token": token, "user": session_user}


@app.get("/me")
async def me(user: dict[str, Any] = Depends(get_user_from_token)):
    return user


@app.post("/chat")
async def chat(request: ChatRequest, user: dict[str, Any] = Depends(get_user_from_token)):
    path = "/ask_debug" if request.debug else "/ask"
    result = await call_rag("POST", path, {"question": request.question})
    return {"user": user["username"], "result": result}


@app.get("/mgr/status")
async def mgr_status(user: dict[str, Any] = Depends(require_admin)):
    return await call_rag("GET", "/status")


@app.get("/mgr/jobs")
async def mgr_jobs(user: dict[str, Any] = Depends(require_admin)):
    return {"jobs": list(reversed(load_jobs()))}


@app.post("/mgr/run-packages")
async def mgr_run_packages(user: dict[str, Any] = Depends(require_admin)):
    result = await call_rag("POST", "/parse/packages", {})
    return add_job("run-packages", user, result)


@app.post("/mgr/run-docs")
async def mgr_run_docs(user: dict[str, Any] = Depends(require_admin)):
    result = await call_rag("POST", "/parse/docs-registry", {})
    return add_job("run-docs", user, result)


@app.post("/mgr/run-google-sheet")
async def mgr_run_google_sheet(
    request: GoogleSheetRequest,
    user: dict[str, Any] = Depends(require_admin),
):
    result = await call_rag("POST", "/dhb/sync-google-sheet", request.model_dump(exclude_none=True))
    return add_job("sync-google-sheet-dashboard", user, result)


@app.post("/mgr/rebuild")
async def mgr_rebuild(user: dict[str, Any] = Depends(require_admin)):
    result = await call_rag("POST", "/rebuild", {})
    return add_job("rebuild", user, result)

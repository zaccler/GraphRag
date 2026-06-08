import os
import re
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage

from fastapi import HTTPException


AUTH_CODE_TTL_SEC = int(os.getenv("AUTH_CODE_TTL_SEC", "600"))
AUTH_CODE_LENGTH = int(os.getenv("AUTH_CODE_LENGTH", "6"))
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no", "off"}
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AUTH_CODE_ALPHABET = "0123456789"
AUTH_CODES = {}
AUTH_CODES_LOCK = threading.Lock()


def normalize_email(email):
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email")
    return email


def generate_auth_code():
    return "".join(secrets.choice(AUTH_CODE_ALPHABET) for _ in range(AUTH_CODE_LENGTH))


def smtp_configured():
    return bool(SMTP_HOST and SMTP_FROM)


def send_auth_code_email(email, code):
    if not smtp_configured():
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "GraphRAG login code"
    message["From"] = SMTP_FROM
    message["To"] = email
    message.set_content(
        "\n".join(
            [
                "Your GraphRAG login code:",
                "",
                code,
                "",
                f"Code lifetime: {AUTH_CODE_TTL_SEC // 60} min.",
                "Ignore this email if you did not request login.",
            ]
        )
    )

    smtp_cls = smtplib.SMTP_SSL if SMTP_USE_SSL else smtplib.SMTP
    try:
        with smtp_cls(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS and not SMTP_USE_SSL:
                server.starttls()
            if SMTP_USER or SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "Gmail отклонил SMTP логин. Для Gmail нужен пароль приложения: "
            "включи 2FA, создай App Password и укажи его в SMTP_PASSWORD без пробелов."
        ) from exc


def store_auth_code(email, code):
    with AUTH_CODES_LOCK:
        AUTH_CODES[email] = {
            "code": code,
            "expires_at": time.time() + AUTH_CODE_TTL_SEC,
        }


def verify_auth_code(email, code):
    code = (code or "").strip()
    with AUTH_CODES_LOCK:
        record = AUTH_CODES.get(email)
        if not record:
            return False

        if float(record["expires_at"]) < time.time():
            AUTH_CODES.pop(email, None)
            return False

        if not secrets.compare_digest(str(record["code"]), code):
            return False

        AUTH_CODES.pop(email, None)
        return True

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_CONFIG_PATH = Path(os.getenv("XDT_RESOURCE_POOL_PATH", "xdt/pul/resources.json"))


@dataclass(frozen=True)
class ResourceRule:
    name: str
    hosts: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    timeout_sec: float | None = None
    retries: int | None = None
    backoff_sec: tuple[float, ...] = ()
    proxy_env: str | None = None
    token_env: str | None = None
    token_header: str = "Authorization"
    token_prefix: str = "Bearer"


@dataclass(frozen=True)
class ResourcePool:
    headers: dict[str, str]
    timeout_sec: float
    retries: int
    backoff_sec: tuple[float, ...]
    rules: tuple[ResourceRule, ...]

    def rule_for_url(self, url: str) -> ResourceRule | None:
        host = urlparse(url).netloc.lower()
        for rule in self.rules:
            if any(host == item or host.endswith(f".{item}") for item in rule.hosts):
                return rule
        return None


def _as_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _as_float_tuple(value: Any) -> tuple[float, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(float(item) for item in value)


def _load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_resource_pool(path: Path = DEFAULT_CONFIG_PATH) -> ResourcePool:
    data = _load_config(path)
    defaults = data.get("defaults", {})
    rules = []

    for item in data.get("resources", []):
        rules.append(
            ResourceRule(
                name=str(item.get("name", "resource")),
                hosts=tuple(str(host).lower() for host in item.get("hosts", [])),
                headers=_as_str_dict(item.get("headers")),
                timeout_sec=float(item["timeout_sec"]) if item.get("timeout_sec") is not None else None,
                retries=int(item["retries"]) if item.get("retries") is not None else None,
                backoff_sec=_as_float_tuple(item.get("backoff_sec")),
                proxy_env=str(item["proxy_env"]) if item.get("proxy_env") else None,
                token_env=str(item["token_env"]) if item.get("token_env") else None,
                token_header=str(item.get("token_header", "Authorization")),
                token_prefix=str(item.get("token_prefix", "Bearer")),
            )
        )

    return ResourcePool(
        headers={"User-Agent": "Mozilla/5.0", **_as_str_dict(defaults.get("headers"))},
        timeout_sec=float(defaults.get("timeout_sec", os.getenv("XDT_HTTP_TIMEOUT_SEC", "30"))),
        retries=int(defaults.get("retries", os.getenv("XDT_HTTP_RETRIES", "2"))),
        backoff_sec=_as_float_tuple(defaults.get("backoff_sec")) or (1.0, 3.0, 7.0),
        rules=tuple(rules),
    )


def _headers_for(rule: ResourceRule | None, extra_headers: dict[str, str] | None) -> dict[str, str]:
    pool = load_resource_pool()
    headers = dict(pool.headers)
    if rule is not None:
        headers.update(rule.headers)
        if rule.token_env:
            token = os.getenv(rule.token_env, "").strip()
            if token:
                value = token if not rule.token_prefix else f"{rule.token_prefix} {token}"
                headers[rule.token_header] = value
    if extra_headers:
        headers.update(extra_headers)
    return headers


def get_auth_headers(resource_name: str) -> dict[str, str]:
    pool = load_resource_pool()
    for rule in pool.rules:
        if rule.name == resource_name and rule.token_env:
            token = os.getenv(rule.token_env, "").strip()
            if token:
                value = token if not rule.token_prefix else f"{rule.token_prefix} {token}"
                return {rule.token_header: value}
    return {}


def request_get(url: str, timeout: float | None = None, headers: dict[str, str] | None = None) -> requests.Response:
    pool = load_resource_pool()
    rule = pool.rule_for_url(url)
    request_headers = _headers_for(rule, headers)
    request_timeout = timeout or (rule.timeout_sec if rule and rule.timeout_sec else pool.timeout_sec)
    retries = rule.retries if rule and rule.retries is not None else pool.retries
    backoff = rule.backoff_sec if rule and rule.backoff_sec else pool.backoff_sec
    proxies = None

    if rule and rule.proxy_env:
        proxy = os.getenv(rule.proxy_env, "").strip()
        if proxy:
            proxies = {"http": proxy, "https": proxy}

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(
                url,
                timeout=request_timeout,
                headers=request_headers,
                proxies=proxies,
            )
            if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(backoff[min(attempt, len(backoff) - 1)])

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"GET request failed without response: {url}")

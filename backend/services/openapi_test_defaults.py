"""Local defaults for the KB OpenAPI sample page."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from backend.settings import RuntimeSettings, get_runtime_settings, normalize_runtime_mode


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _load_key_txt_defaults() -> dict[str, str]:
    raw = _read_text(_repo_root() / "key.txt")
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip()

    def first(*keys: str) -> str:
        for key in keys:
            value = values.get(key.lower())
            if value:
                return value
        return ""

    return {
        "b2cClientId": first("b2cClientId", "b2c_client_id", "clientId", "appkey", "app_key"),
        "b2cClientSecret": first(
            "b2cClientSecret",
            "b2c_client_secret",
            "clientSecret",
            "secretkey",
            "secret_key",
            "b2cSecretKey",
            "b2c_secret_key",
        ),
        "b2cGrantType": first("b2cGrantType", "b2c_grant_type", "grantType", "grant_type"),
    }


def _walk_postman_items(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("request"), dict):
            result.append(item)
            continue
        nested = item.get("item")
        if isinstance(nested, list):
            result.extend(_walk_postman_items(nested))
    return result


def _request_body(item: dict[str, Any]) -> dict[str, Any]:
    request = item.get("request")
    if not isinstance(request, dict):
        return {}
    body = request.get("body")
    if not isinstance(body, dict):
        return {}
    raw = body.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _kb_b2c_apps_base_url(settings: RuntimeSettings) -> str:
    return settings.active_environment.kb_b2c_base_url


def _kb_b2c_token_base_url(settings: RuntimeSettings) -> str:
    return settings.active_environment.kb_b2c_token_base_url


def _load_b2c_postman_defaults(settings: RuntimeSettings) -> dict[str, Any]:
    collection_path = (
        _repo_root().parent
        / "_dev_"
        / "KB_BaaS 2.0 Dev (B2C).postman_collection"
        / "2.BaaS 2.0 Dev (B2C).postman_collection.json"
    )
    collection = _load_json(collection_path)
    key_txt = _load_key_txt_defaults() if settings.expose_local_defaults else {}
    items = _walk_postman_items(collection.get("item", []))
    app_registration: dict[str, Any] = {}
    token_issue: dict[str, Any] = {}

    for item in items:
        request = item.get("request", {})
        url = request.get("url", {}) if isinstance(request, dict) else {}
        raw_url = url.get("raw", "") if isinstance(url, dict) else ""
        if "/service/apps" in raw_url:
            app_registration = _request_body(item)
        if "/oauth2/token" in raw_url:
            token_issue = _request_body(item)

    b2c_client_id = key_txt.get("b2cClientId", "")
    b2c_client_secret = key_txt.get("b2cClientSecret", "")
    b2c_grant_type = key_txt.get("b2cGrantType", "") or "client_credentials"
    if b2c_client_id or b2c_client_secret:
        token_issue = {
            "dataBody": {
                "clientId": b2c_client_id,
                "clientSecret": b2c_client_secret,
                "grantType": b2c_grant_type,
            },
        }

    return {
        "appsBaseUrl": _kb_b2c_apps_base_url(settings),
        "tokenBaseUrl": _kb_b2c_token_base_url(settings),
        "appRegistration": app_registration,
        "tokenIssue": token_issue,
    }


def openapi_test_defaults(mode: str | None = None) -> dict[str, Any]:
    settings = get_runtime_settings()
    if mode:
        selected_mode = normalize_runtime_mode(mode)
        settings = replace(
            settings,
            mode=selected_mode,
            expose_local_defaults=settings.expose_local_defaults and selected_mode == "development",
        )

    b2c_defaults = (
        _load_b2c_postman_defaults(settings)
        if settings.expose_local_defaults
        else {
            "appsBaseUrl": _kb_b2c_apps_base_url(settings),
            "tokenBaseUrl": _kb_b2c_token_base_url(settings),
            "appRegistration": {},
            "tokenIssue": {},
        }
    )

    return {
        "runtimeMode": settings.mode,
        "kb": {
            "b2c": b2c_defaults,
        },
    }

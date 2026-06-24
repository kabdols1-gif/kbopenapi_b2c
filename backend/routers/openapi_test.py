"""OpenAPI test utility endpoints."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Optional
from urllib.parse import urlparse

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.settings import get_runtime_settings


router = APIRouter()
settings = get_runtime_settings()
ROOT_DIR = Path(__file__).resolve().parents[2]
SHARED_METADATA_PATH = ROOT_DIR / "config" / "openapi-test" / "shared-metadata.json"
_shared_metadata_lock = Lock()


class OpenApiProxyRequest(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: str = Field(max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    accessToken: Optional[str] = None
    clientSecret: Optional[str] = None
    encryptBody: bool = False


class SharedFieldSpecOverride(BaseModel):
    required: Optional[Literal["Y", "N"]] = None
    description: Optional[str] = Field(default=None, max_length=20000)


class SharedSampleSpecOverrides(BaseModel):
    inputSpec: Optional[dict[str, SharedFieldSpecOverride]] = None
    outputSpec: Optional[dict[str, SharedFieldSpecOverride]] = None


class SharedSampleMetadataPatch(BaseModel):
    specOverrides: Optional[SharedSampleSpecOverrides] = None
    note: Optional[str] = Field(default=None, max_length=20000)
    verified: Optional[bool] = None


SHARED_METADATA_LOCAL_STATE_KEYS = {
    "executed",
    "lastExecutedAt",
    "lastStatus",
    "lastOk",
}


def _is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    schemes = {"https"}
    if settings.allow_http_targets:
        schemes.add("http")
    return parsed.scheme in schemes and any(
        host == suffix or host.endswith(f".{suffix}") for suffix in settings.allowed_host_suffixes
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty_shared_metadata() -> dict[str, Any]:
    return {"version": 1, "updatedAt": "", "samples": {}}


def _load_shared_metadata() -> dict[str, Any]:
    if not SHARED_METADATA_PATH.exists():
        return _empty_shared_metadata()
    try:
        metadata = json.loads(SHARED_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_shared_metadata()
    if not isinstance(metadata, dict):
        return _empty_shared_metadata()
    samples = metadata.get("samples")
    if not isinstance(samples, dict):
        metadata["samples"] = {}
    else:
        for sample in samples.values():
            if isinstance(sample, dict):
                for key in SHARED_METADATA_LOCAL_STATE_KEYS:
                    sample.pop(key, None)
    metadata["version"] = 1
    metadata.setdefault("updatedAt", "")
    return metadata


def _write_shared_metadata(metadata: dict[str, Any]) -> None:
    SHARED_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHARED_METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _merge_spec_overrides(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    next_overrides = dict(current)
    for section in ("inputSpec", "outputSpec"):
        section_patch = patch.get(section)
        if not isinstance(section_patch, dict):
            continue
        current_section = dict(next_overrides.get(section) or {})
        for field_key, field_patch in section_patch.items():
            if not isinstance(field_key, str) or not isinstance(field_patch, dict):
                continue
            current_field = dict(current_section.get(field_key) or {})
            current_field.update(field_patch)
            current_section[field_key] = current_field
        next_overrides[section] = current_section
    return next_overrides


def _compact_body(body: Any) -> str:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _encrypt_ecb_pkcs7(client_secret: str, plain_body: str) -> str:
    key = client_secret.encode("utf-8")
    if len(key) not in {16, 24, 32}:
        raise HTTPException(status_code=400, detail="clientSecret must be 16, 24, or 32 bytes for AES encryption.")
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(plain_body.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt_ecb_pkcs7(client_secret: str, encrypted_body: str) -> str:
    key = client_secret.encode("utf-8")
    if len(key) not in {16, 24, 32}:
        raise HTTPException(status_code=400, detail="clientSecret must be 16, 24, or 32 bytes for AES decryption.")
    try:
        encrypted = base64.b64decode(encrypted_body)
        cipher = AES.new(key, AES.MODE_ECB)
        decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
        return decrypted.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Failed to decrypt encrypted OpenAPI response.") from exc


def _make_hs_key(access_token: str, plain_body: str) -> str:
    digest_hex = hmac.new(access_token.encode("utf-8"), plain_body.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.b64encode(digest_hex.encode("utf-8")).decode("ascii")


def _decrypt_response_if_needed(response_text: str, client_secret: Optional[str]) -> tuple[str, bool]:
    if not client_secret:
        return response_text, False
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text, False
    if not isinstance(payload, dict):
        return response_text, False
    encrypted_body = payload.get("encrypt")
    if not isinstance(encrypted_body, str) or not encrypted_body.strip():
        return response_text, False
    return _decrypt_ecb_pkcs7(client_secret, encrypted_body), True


@router.post("/proxy")
async def proxy_openapi_request(request: OpenApiProxyRequest) -> dict[str, Any]:
    if not _is_allowed_url(request.url):
        raise HTTPException(status_code=400, detail="Unsupported OpenAPI target URL.")

    headers = {key: value for key, value in request.headers.items() if key.lower() not in {"host", "content-length"}}
    request_body = request.body
    if request.encryptBody and request.method in {"POST", "PUT", "PATCH"}:
        if not request.accessToken:
            raise HTTPException(status_code=400, detail="accessToken is required for encrypted OpenAPI requests.")
        if not request.clientSecret:
            raise HTTPException(status_code=400, detail="clientSecret is required for encrypted OpenAPI requests.")
        plain_body = _compact_body(request.body)
        headers["hsKey"] = _make_hs_key(request.accessToken, plain_body)
        request_body = {"encrypt": _encrypt_ecb_pkcs7(request.clientSecret, plain_body)}
    sent_headers = dict(headers)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                request.method,
                request.url,
                headers=headers,
                json=request_body if request.method in {"POST", "PUT", "PATCH"} else None,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response_body, decrypted = _decrypt_response_if_needed(response.text, request.clientSecret)
    response_headers = dict(response.headers)
    if decrypted:
        response_headers["x-openapi-test-decrypted"] = "true"

    return {
        "status": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "headers": response_headers,
        "body": response_body,
        "decrypted": decrypted,
        "requestHeaders": sent_headers,
    }


@router.get("/shared-metadata")
async def get_shared_metadata() -> dict[str, Any]:
    with _shared_metadata_lock:
        return _load_shared_metadata()


@router.put("/shared-metadata/samples/{sample_id}")
async def update_shared_sample_metadata(sample_id: str, patch: SharedSampleMetadataPatch) -> dict[str, Any]:
    sample_key = sample_id.strip()
    if not sample_key:
        raise HTTPException(status_code=400, detail="sample_id is required.")

    patch_data = patch.model_dump(exclude_unset=True)
    with _shared_metadata_lock:
        metadata = _load_shared_metadata()
        samples = metadata.setdefault("samples", {})
        if not isinstance(samples, dict):
            samples = {}
            metadata["samples"] = samples

        spec_patch = patch_data.pop("specOverrides", None)
        has_note_patch = "note" in patch_data
        has_verified_patch = "verified" in patch_data
        if not spec_patch and not has_note_patch and not has_verified_patch:
            return metadata

        current_sample = dict(samples.get(sample_key) or {})
        for key in SHARED_METADATA_LOCAL_STATE_KEYS:
            current_sample.pop(key, None)
        if isinstance(spec_patch, dict):
            current_sample["specOverrides"] = _merge_spec_overrides(
                dict(current_sample.get("specOverrides") or {}),
                spec_patch,
            )
        if has_note_patch:
            current_sample["note"] = str(patch_data.get("note") or "")
        if has_verified_patch:
            current_sample["verified"] = patch_data.get("verified") is True
        current_sample["updatedAt"] = _now_iso()
        samples[sample_key] = current_sample
        metadata["updatedAt"] = current_sample["updatedAt"]
        _write_shared_metadata(metadata)
        return metadata

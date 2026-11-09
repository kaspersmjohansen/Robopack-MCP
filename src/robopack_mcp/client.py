"""Thin async client for the Robopack v1 REST API.

Authentication is the X-API-Key header. The key is never included in error
messages or logs.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx

BASE_URLS = {
    "test": "https://api-test.robopack.com/v1/",
    "prod": "https://api.robopack.com/v1/",
}

RETRY_STATUSES = {429, 500, 502, 503, 504}
# API paths are made of words and UUIDs. Anything else, such as '..', is refused.
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9-]+")


class RobopackError(Exception):
    """Raised when the Robopack API returns an error response."""

    def __init__(self, status: int, method: str, path: str, message: str):
        self.status = status
        self.method = method
        self.path = path
        self.message = message
        super().__init__(f"Robopack API {status} on {method} {path}: {message}")


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:500] or resp.reason_phrase
    if isinstance(body, dict):
        for key in ("message", "title", "error", "detail"):
            if body.get(key):
                return str(body[key])[:500]
    return str(body)[:500]


def _retry_delay(resp: httpx.Response, attempt: int, base: float) -> float:
    retry_after = resp.headers.get("Retry-After", "")
    if retry_after.isdigit():
        return min(float(retry_after), 60.0)
    return min(base * (2**attempt), 20.0)


class RobopackClient:
    def __init__(
        self,
        api_key: str,
        env: str = "test",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ):
        if not api_key:
            raise ValueError("A Robopack API key is required (set ROBOPACK_API_KEY).")
        if env not in BASE_URLS:
            raise ValueError(f"ROBOPACK_ENV must be one of {sorted(BASE_URLS)}, got {env!r}.")
        self._http = httpx.AsyncClient(
            base_url=BASE_URLS[env],
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    @classmethod
    def from_env(cls) -> RobopackClient:
        return cls(
            os.environ.get("ROBOPACK_API_KEY", ""),
            os.environ.get("ROBOPACK_ENV", "test"),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send a request. Retries 429 for any method and 5xx only for GET.

        POST is not retried on 5xx because a repeat could start a second import.
        """
        for segment in path.strip("/").split("/"):
            if not _SAFE_SEGMENT.fullmatch(segment):
                raise ValueError(f"Invalid API path segment {segment!r}: IDs may only contain letters, digits and hyphens")
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        resp: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            resp = await self._http.request(
                method,
                path.lstrip("/"),
                params=clean_params or None,
                json=json,
                content=content,
                headers=headers,
            )
            retryable = resp.status_code == 429 or (
                resp.status_code in RETRY_STATUSES and method.upper() == "GET"
            )
            if not retryable or attempt == self._max_retries:
                break
            await asyncio.sleep(_retry_delay(resp, attempt, self._backoff_base))

        if resp is None:  # unreachable: the loop always runs at least once
            raise RuntimeError("No response received")
        if resp.status_code >= 400:
            raise RobopackError(resp.status_code, method, path, _error_message(resp))
        return resp

    async def get_json(self, path: str, **kwargs: Any) -> Any:
        return (await self.request("GET", path, **kwargs)).json()

    async def post_json(self, path: str, body: Any = None, **kwargs: Any) -> Any:
        resp = await self.request("POST", path, json=body, **kwargs)
        return resp.json() if resp.content else None

import asyncio
import json

import httpx
import pytest

from robopack_mcp.client import RobopackClient, RobopackError

KEY = "test-key-123"


def make_client(handler, **kwargs):
    kwargs.setdefault("backoff_base", 0)
    return RobopackClient(KEY, "test", transport=httpx.MockTransport(handler), **kwargs)


def run(coro):
    return asyncio.run(coro)


def test_sends_api_key_header_and_uses_test_base_url():
    seen = {}

    def handler(request):
        seen["key"] = request.headers.get("X-API-Key")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    client = make_client(handler)
    run(client.get_json("app/verified", params={"Page": 0, "ItemsPerPage": 5, "Missing": None}))
    assert seen["key"] == KEY
    assert seen["url"] == "https://api-test.robopack.com/v1/app/verified?Page=0&ItemsPerPage=5"


def test_retries_rate_limit_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "slow down"})
        return httpx.Response(200, json={"ok": True})

    result = run(make_client(handler).get_json("package"))
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_post_is_not_retried_on_server_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, json={"message": "boom"})

    with pytest.raises(RobopackError):
        run(make_client(handler).post_json("app/import/abc", {"scope": "machine"}))
    assert calls["n"] == 1


def test_error_message_is_surfaced_and_key_is_not_leaked():
    def handler(request):
        return httpx.Response(404, json={"message": "Package not found"})

    with pytest.raises(RobopackError) as exc:
        run(make_client(handler).get_json("package/does-not-exist"))
    assert exc.value.status == 404
    assert "Package not found" in str(exc.value)
    assert KEY not in str(exc.value)


def test_rejects_unknown_environment_and_missing_key():
    with pytest.raises(ValueError):
        RobopackClient(KEY, "staging")
    with pytest.raises(ValueError):
        RobopackClient("", "test")


def test_post_json_handles_empty_body():
    def handler(request):
        return httpx.Response(204)

    assert run(make_client(handler).post_json("package/content/x/finalize", {"files": []})) is None

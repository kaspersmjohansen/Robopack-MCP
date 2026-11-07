import asyncio

import pytest

from robopack_mcp import server


def run(coro):
    return asyncio.run(coro)


def test_safe_path_blocks_escape(tmp_path):
    with pytest.raises(ValueError):
        server._safe_path("../outside.txt", tmp_path)
    with pytest.raises(ValueError):
        server._safe_path("/etc/passwd", tmp_path)
    assert server._safe_path("ok.msi", tmp_path) == (tmp_path / "ok.msi").resolve()


def test_destructive_tools_do_not_run_without_confirm(monkeypatch):
    def boom():
        raise AssertionError("client must not be called without confirm=True")

    monkeypatch.setattr(server, "client", boom)

    result = run(server.robopack_import_app("app-1"))
    assert result["status"] == "not_executed"
    assert result["action"] == "import_app"

    result = run(server.robopack_upload_to_tenant("t-1", "p-1"))
    assert result["status"] == "not_executed"

    result = run(server.robopack_create_package("My App", "msi"))
    assert result["status"] == "not_executed"


def test_paging_is_one_based():
    assert server._paging(0, 5) == {"Page": 1, "ItemsPerPage": 5}
    assert server._paging(None, None) == {"Page": None, "ItemsPerPage": None}
    assert server._paging(2, 5) == {"Page": 2, "ItemsPerPage": 5}


def test_tenant_upload_sends_package_id_as_query_param(monkeypatch):
    seen = {}

    class FakeClient:
        async def post_json(self, path, body=None, **kwargs):
            seen["path"], seen["body"], seen["params"] = path, body, kwargs.get("params")
            return {"id": "u-1", "state": "Pending"}

    monkeypatch.setattr(server, "client", lambda: FakeClient())
    run(server.robopack_upload_to_tenant("t-1", "p-1", confirm=True))
    assert seen["path"] == "tenant/t-1/upload"
    assert seen["params"] == {"packageId": "p-1"}
    assert "packageId" not in seen["body"]


def test_import_sends_scope_and_version_as_query_params(monkeypatch):
    seen = {}

    class FakeClient:
        async def post_json(self, path, body=None, **kwargs):
            seen["path"], seen["body"], seen["params"] = path, body, kwargs.get("params")
            return "pkg-1"

    monkeypatch.setattr(server, "client", lambda: FakeClient())
    run(server.robopack_import_app("app-1", scope="user", version_id="v-1", confirm=True))
    assert seen["path"] == "app/import/app-1"
    assert seen["params"] == {"scope": "user", "versionId": "v-1"}
    assert seen["body"] is None


def test_search_apps_sends_search_key(monkeypatch):
    seen = {}

    class FakeClient:
        async def get_json(self, path, params=None):
            seen["path"], seen["params"] = path, params
            return []

    monkeypatch.setattr(server, "client", lambda: FakeClient())
    run(server.robopack_search_apps(search="7-Zip", verified=True, page=1, items_per_page=3))
    assert seen["path"] == "app"
    assert seen["params"] == {"search": "7-Zip", "verified": True, "Page": 1, "ItemsPerPage": 3}


def test_download_defaults_to_psadt(tmp_path, monkeypatch):
    import inspect

    default = inspect.signature(server.robopack_download_package).parameters["format"].default
    assert default == "PSADT"


def test_upload_reads_only_from_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOPACK_UPLOAD_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        run(server.robopack_upload_package_file("p-1", "../secret.txt"))

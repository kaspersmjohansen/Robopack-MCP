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
    assert seen["params"] == {"packageId": "p-1", "wait": False, "uploadMsixAsWin32": True}
    assert seen["body"] is None


def test_tenant_upload_false_flag_is_sent_as_query_param(monkeypatch):
    seen = {}

    class FakeClient:
        async def post_json(self, path, body=None, **kwargs):
            seen["params"] = kwargs.get("params")
            return {"id": "u-1", "state": "Pending"}

    monkeypatch.setattr(server, "client", lambda: FakeClient())
    run(server.robopack_upload_to_tenant("t-1", "p-1", upload_msix_as_win32=False, confirm=True))
    assert seen["params"]["uploadMsixAsWin32"] is False


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


def test_chunked_upload_sends_offset_and_chunk_numbers(monkeypatch, tmp_path):
    base = tmp_path / "uploads"
    base.mkdir()
    (base / "big.msix").write_bytes(b"0123456789" * 5)  # 50 bytes
    monkeypatch.setenv("ROBOPACK_UPLOAD_DIR", str(base))

    calls = []

    class FakeClient:
        async def post_json(self, path, body=None, **kwargs):
            calls.append((path, kwargs["params"], kwargs["content"]))
            return None

    monkeypatch.setattr(server, "client", lambda: FakeClient())
    result = run(server.robopack_upload_package_file("p-1", "big.msix", chunk_bytes=20, confirm=True))

    assert result == {"file": "big.msix", "bytes": 50, "chunks_uploaded": 3}
    assert [c[1] for c in calls] == [
        {"index": 0, "size": 20, "offset": 0, "chunk": 0},
        {"index": 0, "size": 20, "offset": 20, "chunk": 1},
        {"index": 0, "size": 10, "offset": 40, "chunk": 2},
    ]
    assert b"".join(c[2] for c in calls) == (base / "big.msix").read_bytes()


def _upload_dir(monkeypatch, tmp_path, name, data):
    base = tmp_path / "uploads"
    base.mkdir(exist_ok=True)
    (base / name).write_bytes(data)
    monkeypatch.setenv("ROBOPACK_UPLOAD_DIR", str(base))
    return base


def test_custom_package_preview_makes_no_calls(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path, "app.msi", b"x" * 30)

    def boom():
        raise AssertionError("client must not be called without confirm=True")

    monkeypatch.setattr(server, "client", boom)
    result = run(server.robopack_create_custom_package("app.msi", "App", "msi"))
    assert result["status"] == "not_executed"
    assert result["details"]["chunks"] == 1


def test_custom_package_rejects_extension_mismatch(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path, "app.exe", b"x")
    with pytest.raises(ValueError):
        run(server.robopack_create_custom_package("app.exe", "App", "msi", confirm=True))


def test_custom_package_runs_create_upload_finalize_then_waits(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path, "app.exe", b"0123456789" * 3)  # 30 bytes
    calls = []

    class FakeClient:
        async def post_json(self, path, body=None, **kwargs):
            calls.append(("post", path, body, kwargs.get("params")))
            if path == "package/create":
                return {"id": "pkg-9"}
            return None

        async def get_json(self, path):
            calls.append(("get", path))
            return {"state": "Completed", "issues": []}

    monkeypatch.setattr(server, "client", lambda: FakeClient())
    result = run(server.robopack_create_custom_package(
        "app.exe", "My App", "exe", publisher="Contoso", version="1.2.3",
        install_command="setup.exe /S", uninstall_command="uninstall.exe /S",
        chunk_bytes=10, confirm=True,
    ))

    assert result == {"package_id": "pkg-9", "state": "Completed", "issues": [],
                      "bytes": 30, "chunks_uploaded": 3}
    assert calls[0][:3] == ("post", "package/create", {
        "name": "My App", "sourceType": "exe", "publisher": "Contoso", "version": "1.2.3",
        "installCommand": "setup.exe /S", "uninstallCommand": "uninstall.exe /S",
    })
    assert [c[3]["offset"] for c in calls if c[0] == "post" and c[1] == "package/content/pkg-9"] == [0, 10, 20]
    assert calls[-2][:2] == ("post", "package/content/pkg-9/finalize")
    assert calls[-1] == ("get", "package/pkg-9")


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def post_json(self, path, body=None, **kwargs):
        self.calls.append(("post", path, body))
        return {"ok": True}

    async def get_json(self, path, **kwargs):
        self.calls.append(("get", path))
        return {}


def test_flow_writes_do_not_run_without_confirm(monkeypatch):
    def boom():
        raise AssertionError("client must not be called without confirm=True")

    monkeypatch.setattr(server, "client", boom)
    assert run(server.robopack_create_flow(package_id="p-1"))["status"] == "not_executed"
    assert run(server.robopack_add_deployment("f-1", "p-1"))["status"] == "not_executed"
    assert run(server.robopack_start_deployment("d-1"))["status"] == "not_executed"
    assert run(server.robopack_stop_deployment("d-1"))["status"] == "not_executed"
    assert run(server.robopack_update_deployment_content("d-1"))["status"] == "not_executed"


def test_create_flow_needs_exactly_one_source(monkeypatch):
    monkeypatch.setattr(server, "client", lambda: _RecordingClient())
    with pytest.raises(ValueError):
        run(server.robopack_create_flow(confirm=True))
    with pytest.raises(ValueError):
        run(server.robopack_create_flow(package_id="p-1", app_id="a-1", confirm=True))


def test_create_flow_maps_scope_and_sends_body(monkeypatch):
    fake = _RecordingClient()
    monkeypatch.setattr(server, "client", lambda: fake)
    run(server.robopack_create_flow(
        package_id="p-1", scope="User", flags=1, patch_group_id="g-1",
        supersedence_history_count=2, confirm=True,
    ))
    assert fake.calls == [("post", "flow/create", {
        "packageId": "p-1", "scope": 2, "flags": 1, "patchGroupId": "g-1",
        "supersedenceHistoryCount": 2,
    })]


def test_create_flow_rejects_out_of_range_supersedence(monkeypatch):
    monkeypatch.setattr(server, "client", lambda: _RecordingClient())
    with pytest.raises(ValueError):
        run(server.robopack_create_flow(package_id="p-1", supersedence_history_count=9, confirm=True))


def test_add_deployment_and_actions_use_expected_paths(monkeypatch):
    fake = _RecordingClient()
    monkeypatch.setattr(server, "client", lambda: fake)
    run(server.robopack_add_deployment("f-1", "p-1", version="2.0", start_now=True, confirm=True))
    run(server.robopack_start_deployment("d-1", confirm=True))
    run(server.robopack_stop_deployment("d-1", confirm=True))
    run(server.robopack_update_deployment_content("d-1", confirm=True))
    assert fake.calls == [
        ("post", "flow/f-1/add-deployment", {"packageId": "p-1", "startNow": True, "version": "2.0"}),
        ("post", "flow/deployment/d-1/start", None),
        ("post", "flow/deployment/d-1/stop", None),
        ("post", "flow/deployment/d-1/update-content", None),
    ]


def test_wave_tools_are_read_only_and_use_expected_paths(monkeypatch):
    fake = _RecordingClient()
    monkeypatch.setattr(server, "client", lambda: fake)
    run(server.robopack_get_wave("w-1"))
    run(server.robopack_get_wave_live("w-1"))
    assert fake.calls == [("get", "flow/wave/w-1"), ("get", "flow/wave/w-1/live")]

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


def test_upload_reads_only_from_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOPACK_UPLOAD_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        run(server.robopack_upload_package_file("p-1", "../secret.txt"))

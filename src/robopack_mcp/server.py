"""MCP server exposing the Robopack v1 API as tools.

Tools that change data in Robopack or Intune (import, create, upload, tenant
upload) do nothing unless called with confirm=True. Without it they return a
preview of the action.

Local file access is limited to ROBOPACK_UPLOAD_DIR (reads) and
ROBOPACK_DOWNLOAD_DIR (writes).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .client import RobopackClient

mcp = FastMCP("robopack")
_client: RobopackClient | None = None


def client() -> RobopackClient:
    global _client
    if _client is None:
        _client = RobopackClient.from_env()
    return _client


def _sandbox(env_var: str, default: str) -> Path:
    return Path(os.environ.get(env_var, default)).expanduser().resolve()


def _safe_path(raw: str, base: Path, must_exist: bool = False) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(base):
        raise ValueError(f"Path must be inside {base}")
    if must_exist and not candidate.is_file():
        raise ValueError(f"No such file: {candidate.name}")
    return candidate


def _paging(page: int | None, items_per_page: int | None) -> dict[str, Any]:
    # The live API is 1-based. The v1 article says 0-indexed, but Page=0 returns HTTP 500.
    return {"Page": max(page, 1) if page is not None else None, "ItemsPerPage": items_per_page}


def _preview(action: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "not_executed",
        "action": action,
        "details": details,
        "message": "This changes data in Robopack or Intune. Call again with confirm=true to run it.",
    }


# ---------------------------------------------------------------- apps

@mcp.tool()
async def robopack_search_apps(
    search: str | None = None,
    verified: bool | None = None,
    page: int | None = None,
    items_per_page: int | None = None,
) -> Any:
    """Search repository apps that can be imported into the organization.

    `search` matches app names (verified against the live API: `search=7-Zip`
    returns 7-Zip first; other keys such as `name` or `query` are ignored).
    `verified=True` limits results to verified apps.
    """
    params = {"search": search, "verified": verified, **_paging(page, items_per_page)}
    return await client().get_json("app", params=params)


@mcp.tool()
async def robopack_list_verified_apps(page: int | None = None, items_per_page: int | None = None) -> Any:
    """List apps Robopack has tested and marked as verified (expected to work)."""
    return await client().get_json("app/verified", params=_paging(page, items_per_page))


@mcp.tool()
async def robopack_list_showcased_apps(page: int | None = None, items_per_page: int | None = None) -> Any:
    """List showcased apps, the most-used ones."""
    return await client().get_json("app/showcase", params=_paging(page, items_per_page))


@mcp.tool()
async def robopack_get_app(app_id: str) -> Any:
    """Get one repository app, including its available versions."""
    return await client().get_json(f"app/{app_id}")


@mcp.tool()
async def robopack_import_app(
    app_id: str,
    scope: Literal["user", "machine"] = "machine",
    version_id: str | None = None,
    confirm: bool = False,
) -> Any:
    """Import a repository app into the organization. Returns the new package ID.

    Check the app's userScope/machineScope before choosing `scope`.
    Omit `version_id` to import the newest version.
    """
    details = {"app_id": app_id, "scope": scope, "version_id": version_id}
    if not confirm:
        return _preview("import_app", details)
    # The live API reads scope and versionId from the query string. In the JSON body
    # they are silently ignored, so a user-scope import falls back to machine scope.
    params = {"scope": scope, "versionId": version_id}
    return await client().post_json(f"app/import/{app_id}", None, params=params)


# ---------------------------------------------------------------- packages

@mcp.tool()
async def robopack_list_packages(page: int | None = None, items_per_page: int | None = None) -> Any:
    """List all packages in the account. importInfo is not populated in this list."""
    return await client().get_json("package", params=_paging(page, items_per_page))


@mcp.tool()
async def robopack_get_package(package_id: str) -> Any:
    """Get package details, state (Pending/Running/Completed/Error), issues and importInfo."""
    return await client().get_json(f"package/{package_id}")


@mcp.tool()
async def robopack_download_package(
    package_id: str,
    output_name: str,
    format: Literal["PSADT", "IntuneWin", "SourceFiles", "AppV", "MSIX", "CIM", "VHD", "VHDX"] = "PSADT",
    no_script_wrap: bool = False,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Download a package to ROBOPACK_DOWNLOAD_DIR. Returns the saved path and size.

    Defaults to PSADT. Any other format must be requested explicitly.
    MSIX-only formats apply to MSIX packages. `no_script_wrap` and `template_id` apply to IntuneWin.
    """
    base = _sandbox("ROBOPACK_DOWNLOAD_DIR", "robopack-downloads")
    base.mkdir(parents=True, exist_ok=True)
    target = _safe_path(output_name, base)
    params = {
        "format": format,
        "noScriptWrap": str(no_script_wrap).lower() if no_script_wrap else None,
        "templateId": template_id,
    }
    resp = await client().request("GET", f"package/{package_id}/download", params=params)
    target.write_bytes(resp.content)
    return {"saved_to": str(target), "bytes": len(resp.content)}


@mcp.tool()
async def robopack_create_package(
    name: str,
    source_type: Literal["msi", "zip", "exe"],
    publisher: str | None = None,
    version: str | None = None,
    install_command: str | None = None,
    uninstall_command: str | None = None,
    user_context: str | None = None,
    detection_rules: list[dict[str, Any]] | None = None,
    logo_base64_png: str | None = None,
    confirm: bool = False,
) -> Any:
    """Create a blank package to upload content into. Returns the package ID.

    Install and uninstall commands and detection rules are needed before Intune
    import or script wrapping works. MSI packages get these after content upload.
    """
    body = {
        "name": name,
        "sourceType": source_type,
        "publisher": publisher,
        "version": version,
        "installCommand": install_command,
        "uninstallCommand": uninstall_command,
        "userContext": user_context,
        "detectionRules": detection_rules,
        "logoData": logo_base64_png,
    }
    body = {k: v for k, v in body.items() if v is not None}
    if not confirm:
        return _preview("create_package", body)
    return await client().post_json("package/create", body)


@mcp.tool()
async def robopack_upload_package_file(
    package_id: str,
    file_name: str,
    index: int = 0,
    chunk_bytes: int | None = None,
    confirm: bool = False,
) -> Any:
    """Upload a file from ROBOPACK_UPLOAD_DIR into a package in WaitingForContent state.

    Without chunk_bytes the whole file goes in one request. With chunk_bytes the file is
    sent in pieces of that size: `size` is the piece size, `offset` is the byte position
    in the file, and `chunk` is the piece number. Call robopack_finalize_package afterwards
    with the same file names, sizes and order.
    """
    base = _sandbox("ROBOPACK_UPLOAD_DIR", "robopack-uploads")
    path = _safe_path(file_name, base, must_exist=True)
    size = path.stat().st_size
    piece = chunk_bytes or size
    if piece <= 0:
        raise ValueError("chunk_bytes must be positive")
    chunks = max(1, -(-size // piece))
    details = {"package_id": package_id, "file": path.name, "bytes": size,
               "index": index, "chunk_bytes": piece, "chunks": chunks}
    if not confirm:
        return _preview("upload_package_file", details)
    with path.open("rb") as f:
        for n in range(chunks):
            offset = n * piece
            data = f.read(piece)
            await client().post_json(
                f"package/content/{package_id}",
                content=data,
                params={"index": index, "size": len(data), "offset": offset, "chunk": n},
                headers={"Content-Type": "application/octet-stream"},
            )
    return {"file": path.name, "bytes": size, "chunks_uploaded": chunks}


@mcp.tool()
async def robopack_finalize_package(
    package_id: str,
    files: list[dict[str, Any]],
    confirm: bool = False,
) -> Any:
    """Finalize uploaded content. `files` is a list of {"fileName": str, "fileSize": int}.

    The entries must match the uploaded files exactly and follow the order of their index values.
    """
    body = {"files": files}
    if not confirm:
        return _preview("finalize_package", {"package_id": package_id, **body})
    return await client().post_json(f"package/content/{package_id}/finalize", body)


@mcp.tool()
async def robopack_create_custom_package(
    file_name: str,
    name: str,
    source_type: Literal["msi", "exe"],
    publisher: str | None = None,
    version: str | None = None,
    install_command: str | None = None,
    uninstall_command: str | None = None,
    user_context: str | None = None,
    detection_rules: list[dict[str, Any]] | None = None,
    chunk_bytes: int | None = None,
    max_wait_seconds: int = 600,
    confirm: bool = False,
) -> Any:
    """Create a custom MSI or EXE package from a file in ROBOPACK_UPLOAD_DIR in one step.

    Runs create, upload, finalize, then waits until the package is Completed or Error.
    The file name must end in the source type (.msi or .exe). MSIX is not supported yet.
    """
    if Path(file_name).suffix.lower() != f".{source_type}":
        raise ValueError(f"file_name must end in .{source_type} for source_type {source_type}")
    base = _sandbox("ROBOPACK_UPLOAD_DIR", "robopack-uploads")
    path = _safe_path(file_name, base, must_exist=True)
    size = path.stat().st_size
    piece = chunk_bytes or size
    if piece <= 0:
        raise ValueError("chunk_bytes must be positive")
    chunks = max(1, -(-size // piece))
    details = {
        "name": name, "source_type": source_type, "file": path.name, "bytes": size,
        "chunks": chunks, "publisher": publisher, "version": version,
        "install_command": install_command, "uninstall_command": uninstall_command,
        "user_context": user_context, "detection_rules": detection_rules,
    }
    if not confirm:
        return _preview("create_custom_package", details)

    created = await robopack_create_package(
        name, source_type, publisher=publisher, version=version,
        install_command=install_command, uninstall_command=uninstall_command,
        user_context=user_context, detection_rules=detection_rules, confirm=True,
    )
    package_id = created["id"]
    try:
        await robopack_upload_package_file(
            package_id, path.name, index=0,
            chunk_bytes=chunk_bytes, confirm=True,
        )
        await robopack_finalize_package(
            package_id, [{"fileName": path.name, "fileSize": size}], confirm=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Package {package_id} was created but the upload failed: {exc}. "
            "Delete it in Robopack, since the API cannot delete packages."
        ) from exc

    state, package = None, {}
    deadline = max_wait_seconds
    while True:
        package = await client().get_json(f"package/{package_id}")
        state = package.get("state")
        if state in ("Completed", "Error") or deadline <= 0:
            break
        await asyncio.sleep(10)
        deadline -= 10
    return {
        "package_id": package_id,
        "state": state,
        "issues": package.get("issues"),
        "bytes": size,
        "chunks_uploaded": chunks,
    }


# ---------------------------------------------------------------- flows and deployments

_SCOPE_VALUES = {"Machine": 1, "User": 2, "Any": 4}
# Values allowed by the POST /v1/flow/create schema. Combined bitmasks are not listed there.
_FLOW_FLAG_VALUES = {0} | {1 << n for n in range(16)}  # 0, 1, 2, ..., 32768


@mcp.tool()
async def robopack_list_flows(page: int | None = None, items_per_page: int | None = None) -> Any:
    """List deployment flows (patch flows and manual flows)."""
    return await client().get_json("flow", params=_paging(page, items_per_page))


@mcp.tool()
async def robopack_get_flow(flow_id: str) -> Any:
    """Get a deployment flow with its deployments."""
    return await client().get_json(f"flow/{flow_id}")


@mcp.tool()
async def robopack_create_flow(
    package_id: str | None = None,
    app_id: str | None = None,
    name: str | None = None,
    scope: Literal["Machine", "User", "Any"] | None = None,
    flags: int | None = None,
    patch_group_id: str | None = None,
    template_id: str | None = None,
    supersedence_history_count: int | None = None,
    confirm: bool = False,
) -> Any:
    """Create a deployment flow from a package or an Instant app. Give exactly one of package_id or app_id.

    `flags` is the AppRegistrationFlags bitmask. For example, 1 = Automatic (patch flow),
    128 = UploadMsixAsWin32. `patch_group_id` adds the flow to an existing patch group.
    """
    if bool(package_id) == bool(app_id):
        raise ValueError("Give exactly one of package_id or app_id")
    if supersedence_history_count is not None and not 0 <= supersedence_history_count <= 8:
        raise ValueError("supersedence_history_count must be between 0 and 8")
    if flags is not None and flags not in _FLOW_FLAG_VALUES:
        raise ValueError(f"flags must be one of the schema values: {sorted(_FLOW_FLAG_VALUES)}")
    body = {
        "packageId": package_id,
        "appId": app_id,
        "name": name,
        "scope": _SCOPE_VALUES[scope] if scope else None,
        "flags": flags,
        "patchGroupId": patch_group_id,
        "templateId": template_id,
        "supersedenceHistoryCount": supersedence_history_count,
    }
    body = {k: v for k, v in body.items() if v is not None}
    if not confirm:
        return _preview("create_flow", body)
    return await client().post_json("flow/create", body)


@mcp.tool()
async def robopack_add_deployment(
    flow_id: str,
    package_id: str,
    version: str | None = None,
    start_now: bool = False,
    confirm: bool = False,
) -> Any:
    """Add a deployment (a package version) to an existing flow. `version` overrides the package version."""
    body: dict[str, Any] = {"packageId": package_id, "startNow": start_now}
    if version:
        body["version"] = version
    if not confirm:
        return _preview("add_deployment", {"flow_id": flow_id, **body})
    return await client().post_json(f"flow/{flow_id}/add-deployment", body)


@mcp.tool()
async def robopack_get_deployment(deployment_id: str) -> Any:
    """Get a deployment's details and status."""
    return await client().get_json(f"flow/deployment/{deployment_id}")


@mcp.tool()
async def robopack_get_wave(wave_id: str) -> Any:
    """Get a deployment wave, including its group targets (read-only)."""
    return await client().get_json(f"flow/wave/{wave_id}")


@mcp.tool()
async def robopack_get_wave_live(wave_id: str) -> Any:
    """Get live deployment data for a wave, such as targeted devices and results (read-only)."""
    return await client().get_json(f"flow/wave/{wave_id}/live")


@mcp.tool()
async def robopack_start_deployment(deployment_id: str, confirm: bool = False) -> Any:
    """Start a deployment, which pushes its app to the tenant's assigned groups."""
    if not confirm:
        return _preview("start_deployment", {"deployment_id": deployment_id})
    return await client().post_json(f"flow/deployment/{deployment_id}/start")


@mcp.tool()
async def robopack_stop_deployment(deployment_id: str, confirm: bool = False) -> Any:
    """Stop a running deployment."""
    if not confirm:
        return _preview("stop_deployment", {"deployment_id": deployment_id})
    return await client().post_json(f"flow/deployment/{deployment_id}/stop")


@mcp.tool()
async def robopack_update_deployment_content(deployment_id: str, confirm: bool = False) -> Any:
    """Update a deployment's app content from its package."""
    if not confirm:
        return _preview("update_deployment_content", {"deployment_id": deployment_id})
    return await client().post_json(f"flow/deployment/{deployment_id}/update-content")


# ---------------------------------------------------------------- tenants

@mcp.tool()
async def robopack_list_tenants() -> Any:
    """List the Intune tenants connected to the organization."""
    return await client().get_json("tenant")


@mcp.tool()
async def robopack_get_tenant(tenant_id: str) -> Any:
    """Get tenant details and admin-consent status."""
    return await client().get_json(f"tenant/{tenant_id}")


@mcp.tool()
async def robopack_upload_to_tenant(
    tenant_id: str,
    package_id: str,
    wait: bool = False,
    upload_msix_as_win32: bool = True,
    confirm: bool = False,
) -> Any:
    """Start uploading a completed package to an Intune tenant. Returns an upload ID.

    With wait=True a failed upload returns HTTP 400. Poll
    robopack_get_tenant_upload_status until the state is Completed, Error or Canceled.
    """
    # The live API reads packageId, wait and uploadMsixAsWin32 from the query string.
    # In the JSON body they are ignored: packageId is rejected as missing, and
    # uploadMsixAsWin32=False silently falls back to True.
    params = {"packageId": package_id, "wait": wait, "uploadMsixAsWin32": upload_msix_as_win32}
    if not confirm:
        return _preview("upload_to_tenant", {"tenant_id": tenant_id, **params})
    return await client().post_json(f"tenant/{tenant_id}/upload", None, params=params)


@mcp.tool()
async def robopack_get_tenant_upload_status(upload_id: str) -> Any:
    """Check a tenant upload. States: Pending, Running, Completed, Error, Canceled."""
    return await client().get_json(f"tenant/upload/{upload_id}")


# ---------------------------------------------------------------- templates

@mcp.tool()
async def robopack_list_templates(page: int | None = None, items_per_page: int | None = None) -> Any:
    """List shared and private configuration templates."""
    return await client().get_json("template", params=_paging(page, items_per_page))


@mcp.tool()
async def robopack_get_template(template_id: str) -> Any:
    """Get template details and script settings."""
    return await client().get_json(f"template/{template_id}")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

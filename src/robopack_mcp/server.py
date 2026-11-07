"""MCP server exposing the Robopack v1 API as tools.

Tools that change data in Robopack or Intune (import, create, upload, tenant
upload) do nothing unless called with confirm=True. Without it they return a
preview of the action.

Local file access is limited to ROBOPACK_UPLOAD_DIR (reads) and
ROBOPACK_DOWNLOAD_DIR (writes).
"""

from __future__ import annotations

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
    confirm: bool = False,
) -> Any:
    """Upload a file from ROBOPACK_UPLOAD_DIR into a package in WaitingForContent state.

    Uploads the whole file in one request. Chunked upload is not implemented yet.
    Call robopack_finalize_package afterwards with the same file names, sizes and order.
    """
    base = _sandbox("ROBOPACK_UPLOAD_DIR", "robopack-uploads")
    path = _safe_path(file_name, base, must_exist=True)
    size = path.stat().st_size
    details = {"package_id": package_id, "file": path.name, "bytes": size, "index": index}
    if not confirm:
        return _preview("upload_package_file", details)
    data = path.read_bytes()
    return await client().post_json(
        f"package/content/{package_id}",
        content=data,
        params={"index": index, "size": size},
        headers={"Content-Type": "application/octet-stream"},
    )


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
    # The live API rejects packageId in the JSON body ("packageId field is required")
    # and accepts it as a query parameter, so it is sent that way.
    body = {"wait": wait, "uploadMsixAsWin32": upload_msix_as_win32}
    if not confirm:
        return _preview("upload_to_tenant", {"tenant_id": tenant_id, "packageId": package_id, **body})
    return await client().post_json(
        f"tenant/{tenant_id}/upload", body, params={"packageId": package_id}
    )


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

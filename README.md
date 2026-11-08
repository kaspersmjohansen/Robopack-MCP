# robopack-mcp

An MCP server that exposes the Robopack v1 API (Intune app packaging) as tools.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env   # then add your key
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `ROBOPACK_API_KEY` | (required) | Key from Settings → API Integration. Shown once. |
| `ROBOPACK_ENV` | `test` | `test` → api-test.robopack.com, `prod` → api.robopack.com |
| `ROBOPACK_UPLOAD_DIR` | `./robopack-uploads` | Only directory the server reads package content from |
| `ROBOPACK_DOWNLOAD_DIR` | `./robopack-downloads` | Only directory downloads are written to |

Start with `ROBOPACK_ENV=test`. Switch to `prod` only after the flow works end to end.

## Run tests

```bash
pytest
```

The tests use a mock HTTP transport, so they do not need a key or network access.

## Use with an MCP client

Example Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "robopack": {
      "command": "/absolute/path/to/.venv/bin/robopack-mcp",
      "env": {
        "ROBOPACK_API_KEY": "your-key",
        "ROBOPACK_ENV": "test"
      }
    }
  }
}
```

## Tools

| Tool | Changes data | Purpose |
|---|---|---|
| `robopack_search_apps` | no | Search importable repository apps |
| `robopack_list_verified_apps` / `robopack_list_showcased_apps` | no | Verified and most-used apps |
| `robopack_get_app` | no | App details and versions |
| `robopack_import_app` | **yes** | Import an app, returns package ID |
| `robopack_list_packages` / `robopack_get_package` | no | Package list, state, issues |
| `robopack_download_package` | no (local write) | Save package to the download dir. Format defaults to PSADT; request others explicitly. |
| `robopack_create_package` | **yes** | Create a blank package |
| `robopack_upload_package_file` | **yes** | Upload a file into a package |
| `robopack_finalize_package` | **yes** | Finalize uploaded content |
| `robopack_create_custom_package` | **yes** | Create an MSI or EXE package from a file in the upload dir in one step (create, upload, finalize, wait for Completed or Error). MSIX not supported yet. |
| `robopack_list_flows` / `robopack_get_flow` / `robopack_get_deployment` / `robopack_get_wave` / `robopack_get_wave_live` | no | Deployment flows, deployments, waves and their status |
| `robopack_create_flow` | **yes** | Create a flow (patch flow with `flags=1`) from a package or Instant app, optionally into a patch group |
| `robopack_add_deployment` | **yes** | Add a package version to a flow, optionally start it |
| `robopack_start_deployment` / `robopack_stop_deployment` / `robopack_update_deployment_content` | **yes** | Control a deployment |
| `robopack_list_tenants` / `robopack_get_tenant` | no | Tenants and admin-consent status |
| `robopack_upload_to_tenant` | **yes** | Push a package to Intune |
| `robopack_get_tenant_upload_status` | no | Poll a tenant upload |
| `robopack_list_templates` / `robopack_get_template` | no | Configuration templates |

Tools marked **yes** return a preview unless called with `confirm=true`.

## Assumptions to verify before production use

These come from the public v1 article, not from the in-app docs:

- **App search filter names.** `robopack_search_apps` forwards `filters` as-is. The article does not list the keys.
- **Upload parameters.** The client sends the whole file as the request body with `index` and `size` query parameters, where `size` is the file size in bytes. A 296 MB MSIX (`Claude.msix`) uploaded this way and completed with no issues on 2026-11-08 (package `1640d031-4c27-4b9a-fb2b-08df3d5b6c2e`). Chunked upload is also implemented: pass `chunk_bytes` to `robopack_upload_package_file`. The OpenAPI spec defines `index` (file index), `size` (piece size), `offset` (byte position in the file) and `chunk` (piece number). The same 296 MB file in 16 MB pieces (18 pieces) completed with no issues on 2026-11-08 (package `d18fcda0-3d8d-4a87-8914-08df3d876502`, size matches the source).
- **Download formats.** The tool passes the format through, so check which values each package type accepts.
- **Rate limits and error codes.** The article does not document them. The client retries 429 and GET 5xx with backoff, and never retries POST on 5xx. On 2026-11-08, 1,000 concurrent read-only GET requests to `tenant` all returned 200 in about 15 seconds, with no 429 and no `Retry-After` header. The 429 retry path is still untested against the live API.
- **Paging.** Paging is 1-based on the live API, even though the article says 0-indexed. `Page=0` returns HTTP 500, so the server clamps it to 1. Paging info comes back in the `X-Pagination` header. Tools return only the body, so add header passthrough if you need page counts.

## Open issues

- **Tenant upload flags were sent in the wrong place (fixed, uncommitted, verified live).** `uploadMsixAsWin32` and `wait` are query parameters on `POST /v1/tenant/{id}/upload`. The server had sent them in the JSON body, where the API ignores them, so every earlier `upload_msix_as_win32=False` test actually ran with `True`. After the fix, `uploadMsixAsWin32=False` on the repository package `Claude 1.5354.0` (`aa470342-a46b-4259-b08f-08dea9e68ed7`) creates an MSIX app in Intune (verified in the Intune portal, 2026-11-07). The same package with `True` creates a Win32 app.
- **Custom MSIX uploads fail with `IntuneUploadFailed` with both `True` and `False`.** Custom MSIX packages (`Hygrosoft 1.0.5.26100`, `1b906906-a0c2-417b-16a9-08df3c5fad3f`, and `Claude 4.23118.0.0`, `7e9b7967-0d8f-4e8f-16ac-08df3c5fad3f`) failed with `True`. A new Hygrosoft package created through the API (`3fd4819b-53b7-482f-16b0-08df3c5fad3f`, source 4, `isCustom` true) also failed with `False` on 2026-11-07. Those packages have no detection rules. The web app's "Import to Intune" works for the same MSIX files. Ask Robopack support whether the API should set the MSIX detection rule itself.
- **Follow-up: custom MSIX with `uploadMsixAsWin32=False` also fails.** Claude 4.23118.0.0, package `1640d031-4c27-4b9a-fb2b-08df3d5b6c2e`, upload `b5891e5f-546b-4584-a8ea-08df3d51b180` (2026-11-08) returned `IntuneUploadFailed`. Hygrosoft failed the same way. Include in the Robopack support request.
- **`wait=True` failure path.** With `wait=True`, a failed Intune upload returns HTTP 400. The body is the upload object with `state: Error`. Tested 2026-11-08 with a new Claude 4.23118.0.0 package (`8e644caa-fcd7-4b47-fb49-08df3d5b6c2e`, upload `66b83912-4dc8-47a1-a934-08df3d51b180`), which failed with `IntuneUploadFailed`.
- **Follow-up: AppV download format.** Not tested because no App-V packages are available. AppV returns `400 Download failed` on every package tried (Claude MSIX, Notepad++, Wallpaper, Hygrosoft). Test it once an App-V package is available.
- **Follow-up: group assignment is not writable through the v1 API.** The docs describe assignments in the web UI only: "Create Deployment Assignments" at import, which creates Entra ID groups (Required, Available, Uninstall), and deployment waves with group targets for patch flows. The v1 spec has no import option for assignments (`POST /v1/app/import/{appId}` takes only scope, script template and version), and no endpoint to create or edit waves or wave targets. Read-only data exists: `GET /v1/flow/wave/{id}` and `GET /v1/flow/wave/{id}/live` return targets with `groupObjectId`, `assignmentType` and flags. Patch groups can be referenced through `patchGroupId` when creating a flow, but there is no endpoint to create or assign them. Per the web UI docs for `POST /v1/flow/create`, a flow created with a `patchGroupId` inherits that group's waves and settings. Without one, the flow is empty. So the workable path is to create the patch group and its waves in the web UI, then create flows through the API with that `patchGroupId`. The web UI example sends `appId` and `packageId` together and uses `scope: 0`. The schema says `appId` and `packageId` are mutually exclusive and `scope` must be 1, 2 or 4 (Machine, User, Any), so the example is wrong on both counts. The tool follows the schema. Ask Robopack support for write endpoints for waves, targets and patch groups.
- **Follow-up: Brave 153 and 155 version imports fail with access denied** (`InstallFailed`, exit code `-2147024891`). Ask Robopack support.
- **Tenant upload has no wrapping option.** Probing `noScriptWrap` and `templateId` on the upload endpoint returned no validation error, so the API does not accept them there. IntuneWin downloads do accept `noScriptWrap` and `templateId`.

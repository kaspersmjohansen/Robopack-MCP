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
| `robopack_download_package` | no (local write) | Save package to the download dir |
| `robopack_create_package` | **yes** | Create a blank package |
| `robopack_upload_package_file` | **yes** | Upload a file into a package |
| `robopack_finalize_package` | **yes** | Finalize uploaded content |
| `robopack_list_tenants` / `robopack_get_tenant` | no | Tenants and admin-consent status |
| `robopack_upload_to_tenant` | **yes** | Push a package to Intune |
| `robopack_get_tenant_upload_status` | no | Poll a tenant upload |
| `robopack_list_templates` / `robopack_get_template` | no | Configuration templates |

Tools marked **yes** return a preview unless called with `confirm=true`.

## Assumptions to verify before production use

These come from the public v1 article, not from the in-app docs:

- **App search filter names.** `robopack_search_apps` forwards `filters` as-is. The article does not list the keys.
- **Upload parameters.** The client sends the whole file as the request body with `index` and `size` query parameters, where `size` is the file size in bytes. Confirm this, and add chunked upload if files are large.
- **Download formats.** The tool passes the format through, so check which values each package type accepts.
- **Rate limits and error codes.** The article does not document them. The client retries 429 and GET 5xx with backoff, and never retries POST on 5xx.
- **Paging.** Paging is 1-based on the live API, even though the article says 0-indexed. `Page=0` returns HTTP 500, so the server clamps it to 1. Paging info comes back in the `X-Pagination` header. Tools return only the body, so add header passthrough if you need page counts.

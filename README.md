# robopack-mcp

An unofficial MCP server that exposes the Robopack v1 API (Intune app packaging) as tools. It uses only the native Robopack API.

This is an independent project. It is not affiliated with, endorsed by or supported by Robopack.

## Quick start with uvx (no clone)

[`uvx`](https://docs.astral.sh/uv/) is part of `uv`. It downloads, builds and runs the server on demand, in its own environment, the same way `npx` runs Node packages. You do not clone the repository or create a virtual environment.

**1. Install uv.** On Windows: `winget install -e --id astral-sh.uv`. On macOS: `brew install uv`. On any system with Python: `pipx install uv`. Open a new terminal afterwards, and restart Claude Desktop later so it sees `uvx` on the PATH. Check it with `uvx --version`.

**2. Create the folders the server may use** and add the server to your MCP client. On Windows the config file is `%APPDATA%\Claude\claude_desktop_config.json`. Use absolute folder paths and double the backslashes in JSON:

```json
{
  "mcpServers": {
    "robopack": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/kaspersmjohansen/Robopack-MCP", "robopack-mcp"],
      "env": {
        "ROBOPACK_API_KEY": "your-key",
        "ROBOPACK_ENV": "prod",
        "ROBOPACK_UPLOAD_DIR": "C:\\Robopack\\uploads",
        "ROBOPACK_DOWNLOAD_DIR": "C:\\Robopack\\downloads"
      }
    }
  }
}
```

**3. Restart Claude Desktop** and ask it to list your Robopack tenants.

Notes:

- The first start downloads and builds the package, so it takes longer than later starts.
- Git has to be able to read the repository. If it is private, Git must be signed in to a GitHub account with access, and that is unreliable when Claude Desktop starts the server. Use the clone-and-install steps below instead.
- `uvx` caches the build. To get a newer version, run `uv cache clean robopack-mcp` and restart Claude Desktop.
- To stay on one version, add a tag or commit to the URL, for example `git+https://github.com/kaspersmjohansen/Robopack-MCP@<tag-or-commit>`.

## Install on Windows

You need Python 3.10 or newer and Git. The steps use PowerShell and do not need administrator rights.

**1. Install Python.** Either use winget:

```powershell
winget install -e --id Python.Python.3.12
```

or download the installer from [python.org/downloads](https://www.python.org/downloads/) and tick **Add python.exe to PATH** on the first screen. Then open a **new** PowerShell window and check it:

```powershell
py -3 --version
```

This should print `Python 3.10` or newer. If `python` opens the Microsoft Store instead, use `py -3` as in the steps below, or turn off the `python.exe` entries under Settings → Apps → Advanced app settings → App execution aliases.

**2. Install Git** if you do not have it: `winget install -e --id Git.Git`. Open a new PowerShell window afterwards.

**3. Get the code.** If the repository is private, Git asks you to sign in to GitHub the first time.

```powershell
cd $HOME
git clone https://github.com/kaspersmjohansen/Robopack-MCP.git
cd Robopack-MCP
```

**4. Create the environment and install.** You do not need to activate the environment, which also avoids PowerShell's script execution policy.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

This creates `.venv\Scripts\robopack-mcp.exe`, which is the program your MCP client starts.

**5. Create the folders the server may use.** It only reads package files from the upload folder and only writes downloads to the download folder. Use absolute paths, because relative paths resolve against whatever folder the MCP client starts the server in.

```powershell
New-Item -ItemType Directory -Force C:\Robopack\uploads, C:\Robopack\downloads
```

**6. Add the server to Claude Desktop.** Open `%APPDATA%\Claude\claude_desktop_config.json` (or Settings → Developer → Edit Config) and add the server. Replace `YOUR-USER` and the key. Backslashes must be doubled in JSON.

```json
{
  "mcpServers": {
    "robopack": {
      "command": "C:\\Users\\YOUR-USER\\Robopack-MCP\\.venv\\Scripts\\robopack-mcp.exe",
      "env": {
        "ROBOPACK_API_KEY": "your-key",
        "ROBOPACK_ENV": "prod",
        "ROBOPACK_UPLOAD_DIR": "C:\\Robopack\\uploads",
        "ROBOPACK_DOWNLOAD_DIR": "C:\\Robopack\\downloads"
      }
    }
  }
}
```

The key sits in this file in plain text, so do not share or sync the file. Create the key in Robopack under Settings → API Integration. It is shown once.

**7. Restart Claude Desktop** by quitting it from the system tray, not just closing the window, and start it again. Then ask Claude to list your Robopack tenants. If the call returns your tenant, the server works.

**Update later:**

```powershell
cd $HOME\Robopack-MCP
git pull
.\.venv\Scripts\python.exe -m pip install -e .
```

### Troubleshooting on Windows

| Symptom | Likely cause |
|---|---|
| The server does not appear in Claude Desktop | A typo in the JSON, or single backslashes in a path. Check the file is valid JSON and restart from the tray. |
| The server shows as failed | The `command` path is wrong. Check that `robopack-mcp.exe` exists at that path. The logs are in `%APPDATA%\Claude\logs`. |
| HTTP 401 from every call | Wrong key, or `ROBOPACK_ENV` does not match the key. A key made in production does not work with `test`. |
| `No such file` or `Path must be inside` | The file is not inside `ROBOPACK_UPLOAD_DIR`, or the folder variable is a relative path. |
| `pip` or `py` is not found | Python is not on your PATH. Reinstall it with **Add python.exe to PATH** ticked and open a new PowerShell window. |

## Install on macOS or Linux

You need Python 3.10 or newer and Git.

```bash
git clone https://github.com/kaspersmjohansen/Robopack-MCP.git
cd Robopack-MCP
python3 -m venv .venv
.venv/bin/python -m pip install -e .
mkdir -p ~/robopack/uploads ~/robopack/downloads
```

Then add the server to your MCP client the same way as in step 6 above, with `command` set to the absolute path of `.venv/bin/robopack-mcp` and the folders set to absolute paths. On macOS the Claude Desktop config is `~/Library/Application Support/Claude/claude_desktop_config.json`.

The server needs `mcp` 1.x (`mcp>=1.2.0,<2`), because version 2 renamed `FastMCP`. The install picks the right version for you.

## Configuration

The server reads these environment variables. It does not read a `.env` file, so set them in the `env` block of your MCP client config, as in the examples above, or in the shell that starts it. `.env.example` lists the names.

| Variable | Default | Purpose |
|---|---|---|
| `ROBOPACK_API_KEY` | (required) | Key from Settings → API Integration. Shown once. |
| `ROBOPACK_ENV` | `test` | `test` → api-test.robopack.com, `prod` → api.robopack.com |
| `ROBOPACK_UPLOAD_DIR` | `./robopack-uploads` | Only directory the server reads package content from |
| `ROBOPACK_DOWNLOAD_DIR` | `./robopack-downloads` | Only directory downloads are written to |

All live testing so far was done against `prod`. The test host rejected the key that was used (401), so check that your key works against `test` before relying on it.

## Run tests

Install the test dependencies and run pytest:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

On macOS or Linux use `.venv/bin/python` instead. The tests use a mock HTTP transport, so they do not need a key or network access.

## Tools

Tools marked **yes** return a preview unless called with `confirm=true`.

| Tool | Changes data | Purpose |
|---|---|---|
| `robopack_search_apps` | no | Search importable repository apps (`search`, `verified`) |
| `robopack_list_verified_apps` / `robopack_list_showcased_apps` | no | Verified and most-used apps |
| `robopack_get_app` | no | App details and versions |
| `robopack_import_app` | **yes** | Import an app (scope, optional version), returns the package ID |
| `robopack_list_packages` / `robopack_get_package` | no | Package list, state, issues |
| `robopack_download_package` | no (local write) | Save a package to the download dir. Format defaults to PSADT; request others explicitly. |
| `robopack_create_package` | **yes** | Create a blank package |
| `robopack_upload_package_file` | **yes** | Upload a file into a package, whole or in chunks (`chunk_bytes`) |
| `robopack_finalize_package` | **yes** | Finalize uploaded content |
| `robopack_detect_installer` | no | Detect an EXE's installer type and suggest silent switches |
| `robopack_create_custom_package` | **yes** | Create an MSI or EXE package from files in the upload dir in one step. See below. |
| `robopack_list_flows` / `robopack_get_flow` / `robopack_get_deployment` / `robopack_get_wave` / `robopack_get_wave_live` | no | Flows, deployments, waves and their status |
| `robopack_create_flow` | **yes** | Create a flow (patch flow with `flags=1`) from a package or Instant app, optionally into a patch group |
| `robopack_add_deployment` | **yes** | Add a package version to a flow, optionally start it |
| `robopack_start_deployment` / `robopack_stop_deployment` / `robopack_update_deployment_content` | **yes** | Control a deployment |
| `robopack_list_tenants` / `robopack_get_tenant` | no | Tenants and admin-consent status |
| `robopack_upload_to_tenant` | **yes** | Push a package to Intune (`wait`, `upload_msix_as_win32`) |
| `robopack_get_tenant_upload_status` | no | Poll a tenant upload |
| `robopack_list_templates` / `robopack_get_template` | no | Configuration templates |

### Custom packages

`robopack_create_custom_package` runs create, upload, finalize and then waits until the package is Completed or Error.

- **Files.** `file_name` is the main installer (`.msi` or `.exe`, matching `source_type`). `additional_files` are uploaded after it, in the order given, and finalize lists every file in that order.
- **EXE install command.** Robopack's analyzer runs only in the web UI, not for API-created packages, so the tool works out the silent switches itself. Without `install_command` it detects the installer type and uses its usual switches. If the type is unknown, or the switches depend on how the installer was built, it stops before creating anything and asks for `install_command`. A given `install_command` always wins. Uninstall is optional.

  | Installer type | Silent switches |
  |---|---|
  | Inno Setup | `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-` |
  | NSIS | `/S` |
  | WiX Burn bundle | `/quiet /norestart` |
  | Advanced Installer | `/exenoui /qn /norestart` |
  | InstallShield, with an MSI in the package | `/S /v/qn` |

- **EXE metadata.** Publisher and version are read from the file's version resource (`CompanyName`, `ProductVersion`) unless given explicitly. MSI files need no help, because Robopack reads them itself.
- **Not supported.** MSIX packages (see Follow-ups).

## Verified behaviour

All of this was checked against the live production API.

- **Parameter placement.** `scope` and `versionId` (import), `packageId`, `wait` and `uploadMsixAsWin32` (tenant upload), `noScriptWrap` and `templateId` (IntuneWin download), and `search` are read from the query string. The same values in the JSON body are silently ignored. Package create and finalize take a JSON body.
- **Paging.** Paging is 1-based, even though the article says 0-indexed. `Page=0` returns HTTP 500, so the server clamps it to 1. Paging info comes back in the `X-Pagination` header, and the tools return only the body.
- **Search.** The search text must be sent as `search`. The keys `name` and `query` are ignored.
- **Uploads.** Whole-file upload works (296 MB MSIX, 159 MB EXE). Chunked upload works too: 296 MB in 16 MB pieces. The spec defines `index` (file index), `size` (piece size), `offset` (byte position) and `chunk` (piece number).
- **Package states.** Deleted packages stay readable by ID but drop out of the package list. A tenant upload of a package in Error state is rejected with HTTP 400 before anything reaches Intune.
- **`wait=True` failure path.** A failed Intune upload returns HTTP 400, and the body is the upload object with `state: Error`.
- **`uploadMsixAsWin32`.** For a repository MSIX package (Claude 1.5354.0), `False` creates an MSIX app in Intune and `True` creates a Win32 app. The earlier `False` results were wrong because the flag was sent in the body.
- **Download formats.** PSADT, IntuneWin and SourceFiles work for repository and custom packages. MSIX, CIM, VHD and VHDX work for an MSIX-origin repository package. For other packages they return `400 Download failed`, which matches the web UI. AppV has not worked on any package tried.
- **Tenant upload has no wrapping option.** `noScriptWrap` and `templateId` are not accepted on the upload endpoint. Whether a package is wrapped is decided on the Robopack side.
- **Rate limits.** 1,000 concurrent read-only GET requests to `tenant` all returned 200 in about 15 seconds, with no 429 and no `Retry-After` header. The client retries 429 and GET 5xx with backoff and never retries POST on 5xx. The 429 path is covered only by a mock test.
- **Custom packages.** MSI, single-file EXE and an 11-file InstallShield setup (51 MB) all completed, and the multi-file source download held every file with matching sizes. The detected install commands and the metadata were checked in the web UI.
- **Path safety.** The client refuses any API path segment that is not letters, digits and hyphens, so a malformed or hostile ID such as `../tenant` cannot redirect a call to another endpoint. File access is limited to the upload and download folders, and symlinks that point outside them are refused.
- **No delete.** The API has no delete endpoint. Packages and Intune apps have to be removed by hand.

## Not tested live

- **Flows, deployments and waves.** `robopack_create_flow`, `robopack_add_deployment`, the start, stop and update-content tools, and the wave tools are covered by unit tests only. Flow creation needs a patch group ID from the web UI.
- **Installer detection for Inno Setup, NSIS, Advanced Installer.** Covered by unit tests only. WiX Burn and InstallShield were checked on real installers.

## Follow-ups for Robopack support

- **Custom MSIX uploads to Intune fail with `IntuneUploadFailed`, with both `uploadMsixAsWin32` values.** Packages tested: Hygrosoft 1.0.5.26100 and Claude 4.23118.0.0, both created through the API (source type `zip`, since `sourceType` accepts only `msi`, `zip` and `exe`). They have a PSADT install command and no detection rules. The web app's "Import to Intune" works for the same MSIX files. Ask whether the API should set the MSIX detection rule, and how MSIX packages are meant to be created through the API.
- **Brave 153 and 155 version imports fail** with `InstallFailed` and exit code `-2147024891` (access denied). The imported packages had no detection rules.
- **Group assignment is not writable through the v1 API.** The docs describe assignments in the web UI only: "Create Deployment Assignments" at import (Entra ID groups for Required, Available and Uninstall) and deployment waves with group targets for patch flows. `POST /v1/app/import/{appId}` takes only scope, script template and version, and no endpoint creates or edits waves, wave targets or patch groups. Waves are readable (`GET /v1/flow/wave/{id}` and `/live` return targets with `groupObjectId` and `assignmentType`). A flow created with a `patchGroupId` inherits that group's waves and settings, so the workable path is to build the patch group in the web UI and create flows through the API. Ask for write endpoints for waves, targets and patch groups.
- **The `POST /v1/flow/create` example in the web docs conflicts with its schema.** The example sends `appId` and `packageId` together and uses `scope: 0`. The schema says they are mutually exclusive and `scope` must be 1, 2 or 4 (Machine, User, Any). The tool follows the schema. Combined `flags` bitmasks are rejected, because the schema lists only 0 and single bits up to 32768. Ask whether combinations are allowed.
- **Analyzer for API-created packages.** An API-created package has no Analyze and Test option in the web UI. Ask whether there is an endpoint for it.
- **AppV download.** Not tested because no App-V package is available. Test it once one exists.

## License

MIT. See [LICENSE](LICENSE).

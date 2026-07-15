# Using a Pre-Built Index: Complete Setup Guide

**English** | [繁體中文](setup-prebuilt-index.zh-TW.md)

> Scenario: a teammate gave you a ready-made `index.db` (~500 MB) and you
> want Claude Code / Codex / Cursor on your machine to query the NXOpen
> API — **without** spending hours building the index yourself.
>
> ⚠️ Licensing: the index contains Siemens API documentation text. Use it
> only within an organization whose seats are licensed for NX; do not
> redistribute it publicly.

---

## 0. What you need

| Item | Notes |
|------|-------|
| Windows PC | macOS/Linux also work — adjust paths |
| Python 3.11+ | Check with `python --version`; install from https://www.python.org/downloads/ and **tick "Add python.exe to PATH"** |
| ~3 GB of disk | 0.5 GB index + 2 GB BGE-M3 model (auto-downloaded on first semantic query) |
| The `index.db` file | ~500 MB, from your teammate |
| Claude Code (or Codex / Cursor) | any MCP-capable AI coding tool |

---

## 1. Install nxopen-mcp

Open a terminal:

```bash
pip install "nxopen-mcp[embed]"
```

- You do **not** need `[reflect]` when using a pre-built index
  (inheritance chains are already baked in).
- `[embed]` is required for semantic search; it pulls in PyTorch, so the
  download takes a while.

Verify:

```bash
nxopen-mcp --help
```

Seeing the `index` / `serve` commands means success. If you get
"command not found", Python's Scripts directory isn't on PATH — find it:

```bash
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

then use `<that path>\nxopen-mcp.exe` wherever `nxopen-mcp` appears below.

---

## 2. Place the index file

Copy the `index.db` you received to the default location:

```
C:\Users\<you>\.nxopen-mcp\index.db
```

Create the `.nxopen-mcp` folder if it doesn't exist. One PowerShell line:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.nxopen-mcp" | Out-Null
Copy-Item "D:\Downloads\index.db" "$env:USERPROFILE\.nxopen-mcp\index.db"
```

> Prefer a different location? Keep it anywhere and add
> `--db "D:\your\path\index.db"` when registering below.

---

## 3. Register with Claude Code

### Option A: one CLI command (recommended)

```bash
claude mcp add -s user nxopen -- nxopen-mcp serve
```

- `-s user`: available in every project, not just one folder.
- Non-default index location:
  `claude mcp add -s user nxopen -- nxopen-mcp serve --db "D:\path\index.db"`
- Tip: add `--preload` after `serve` to warm the model at startup so the
  first semantic query doesn't wait for the model load.

### Option B: edit the config file directly

If the `claude` command isn't available, open
`C:\Users\<you>\.claude.json` and add (or merge into) a top-level
`mcpServers` block:

```json
{
  "mcpServers": {
    "nxopen": {
      "type": "stdio",
      "command": "nxopen-mcp",
      "args": ["serve"]
    }
  }
}
```

If `nxopen-mcp` isn't on PATH, set `command` to the full executable path,
e.g. `C:\\Python312\\Scripts\\nxopen-mcp.exe` (double backslashes in JSON).

---

## 4. Verify

1. **Open a brand-new Claude Code session** (MCP servers connect at
   startup only — old windows won't pick it up).
2. Type `/mcp` → you should see `nxopen ✓ connected`.
3. Test an **exact lookup** first (no model needed — instant):

   > Use nxopen to list the members of CavityMillingBuilder

4. Then a **semantic query**:

   > Use nxopen to search "how to set the spindle speed"

   ⏳ **The first semantic query pauses for 1–3 minutes**: it downloads
   the BGE-M3 model (~2 GB, once ever) and loads it into memory. After
   that, semantic queries within the same session take seconds.
   **It is not frozen — don't interrupt it.**

All green? You're done. From now on just work normally, e.g.:

> Write NXOpen C# that creates a drilling operation and sets the feed rate

Claude will call the nxopen tools automatically before writing code.

---

## 5. Codex / Cursor (optional)

**Codex CLI** — edit `~/.codex/config.toml`:

```toml
[mcp_servers.nxopen]
command = "nxopen-mcp"
args = ["serve"]
```

**Cursor** — add the same JSON block as Option B above to the project's
`.cursor/mcp.json` (or global Settings → MCP).

---

## 6. Troubleshooting

| Symptom | Cause & fix |
|---------|-------------|
| `/mcp` says not connected | Old sessions don't auto-connect → open a new session / restart the tool |
| `error: index not found at ...` | Index isn't at the default path → re-check step 2, or add `--db` when registering |
| `error: index ... schema version` | The index was built by an incompatible nxopen-mcp version → get a matching index or rebuild |
| First search "hangs" for minutes | Normal: one-time model download + load — let it finish |
| Model download fails (corporate network) | Needs access to huggingface.co; set `HTTPS_PROXY` if you're behind a proxy |
| `nxopen-mcp` is not recognized | Scripts dir not on PATH → see step 1, use the full path |
| Exact lookups fast, semantic slow after restart | Normal: the model stays loaded only while the server lives; after a restart the first semantic query reloads it (~1 min, no re-download). Use `--preload` to hide this |
| Want to inspect the index | It's a SQLite file; a full NX 12 doc set has ~98k rows in the `members` table |

---

## 7. Maintenance

- **Upgrade the software**: `pip install -U "nxopen-mcp[embed]"` (the
  index is unaffected).
- **Switch to another NX version's index**: overwrite the file at the
  same path — no re-registration needed.
- **Build your own index** (if you have an NX installation): see the
  main [README](../README.md) Quick start.

Questions? Ask whoever gave you the index file, or open an issue at
https://github.com/mingfeng6684/nxopen-mcp/issues.

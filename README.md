# nxopen-mcp

MCP server that gives AI coding agents (Claude Code, Codex, Cursor)
accurate knowledge of the Siemens NXOpen .NET API — eliminating
hallucinated API calls via hybrid retrieval over your own NX installation's
official documentation.

## Why

LLMs hallucinate NXOpen APIs: it's a niche domain (Siemens NX CAM/CAD
automation) with sparse public training data, so models confidently invent
classes, methods, and parameters that don't exist. This server grounds
agents in the real docs instead of guesses:

- **Semantic search** (BGE-M3 dense + sparse embeddings) so natural-language
  queries in English or 中文 find the right API even without exact names.
- **Exact-name lookup** so a literal class/member name (e.g. `CavityMillingBuilder`)
  is matched precisely, not just approximately.
- **Exact-name channel**: literal CamelCase tokens in your query are
  looked up directly and pinned to the top (types first).
- **RRF fusion** available to combine channels — though evaluation made
  dense + exact the default (see [Evaluation](#evaluation)).

Everything runs locally and offline against an index built from your own
licensed NX installation — no Siemens files are ever bundled with this
repo or sent anywhere.

## Quick start

```bash
# 1. Build the index from YOUR NX installation (one-time, several minutes)
pip install "nxopen-mcp[embed]"
nxopen-mcp index --nx-path "D:\Siemens\NX12.0"

# 2. Register with Claude Code
claude mcp add nxopen -- nxopen-mcp serve

# 3. Ask Claude Code to write NXOpen code — it now queries real APIs.
```

`index` looks for `NXOpen*.xml` doc files under `<nx-path>\UGII\managed`
(falling back to `<nx-path>` itself), and for `NXOpen*.dll` assemblies in
the same folder. The `[embed]` extra pulls in `FlagEmbedding`, which
downloads the BGE-M3 model (~2GB) on first run. Without it, `index` and
`serve` cannot produce or query real embeddings.

By default the index is written to `~/.nxopen-mcp/index.db`; override with
`--db <path>` on both `index` and `serve`.

### `.mcp.json` (Claude Code / other MCP-aware clients)

```json
{
  "mcpServers": {
    "nxopen": {
      "command": "nxopen-mcp",
      "args": ["serve"]
    }
  }
}
```

If you built the index at a non-default path, pass it explicitly:

```json
{
  "mcpServers": {
    "nxopen": {
      "command": "nxopen-mcp",
      "args": ["serve", "--db", "D:\\path\\to\\index.db"]
    }
  }
}
```

### Codex / Cursor

Both tools support stdio MCP servers via a similar config block (Codex's
`~/.codex/config.toml` `[mcp_servers.nxopen]` table, or Cursor's
`mcp.json`). Point `command` at `nxopen-mcp` and `args` at `["serve"]`
(plus `--db` if needed) the same way as above — consult your tool's MCP
docs for the exact config file location and syntax.

## Tools

| tool | purpose |
|---|---|
| `search_api` | Hybrid semantic search over the API (dense + exact-name by default, sparse optional). Accepts English or 中文 queries; use when you don't know the exact class/member name. |
| `get_class` | Full member list for a class, including members inherited from its ancestor chain. Use when you know the class name. |
| `get_member` | Exact signature, parameters, return value, NX version, and license requirement for one member. |
| `find_builder` | Given a CAM operation name (e.g. "cavity milling", "hole drilling"), finds the matching `*Builder` class, its creator method, and a Builder → Commit → Destroy code skeleton. |

## Architecture

```
NXOpen*.xml / *.dll  (your NX install)
        │
        ▼
  indexer/parser.py        one XML doc-comment member -> one MemberRecord
  indexer/inheritance.py   optional: reflect DLLs (pythonnet) for base-class chains
        │
        ▼
  indexer/embedder.py      BGE-M3 dense vector + sparse token weights per record
        │
        ▼
  indexer/build.py         writes members, dense_vec (sqlite-vec), sparse_postings
        │                  into a single SQLite file (index.db)
        ▼
  retrieval/store.py       exact-name lookup, class/member/inheritance queries
  retrieval/hybrid.py      dense ANN + exact CamelCase match (default),
                           optional sparse channel, RRF fusion
        │
        ▼
  server.py                4 MCP tools (FastMCP, stdio transport)
  cli.py                   `nxopen-mcp index` / `nxopen-mcp serve`
```

Design decisions:

- **BYO-Docs licensing.** This repository contains no Siemens XML/DLL
  files. Users point `nxopen-mcp index` at their own licensed NX
  installation; the resulting index is a local SQLite file that never
  leaves the machine and is never committed (see `.gitignore`).
- **One-member-one-chunk.** Each indexed unit is a single API member
  (type, property, method, field, or event) rather than an arbitrary text
  window, so retrieval results map 1:1 onto something an agent can act on
  (a class, a method signature) instead of a fragment of a doc page.
- **RRF fusion, not score blending.** Dense and sparse rankings are
  combined with Reciprocal Rank Fusion, which is scale-free and doesn't
  require calibrating dense-vs-sparse score magnitudes against each other.
  Exact CamelCase name matches are promoted ahead of the fused list
  outright, since a literal name in the query is a much stronger signal
  than similarity.
- **Inheritance via reflection, with graceful degradation.** Ancestor
  chains (needed by `get_class` to show inherited members) are extracted
  by reflecting the NXOpen DLLs with `pythonnet` (`[reflect]` extra) at
  index time. If the extra isn't installed or DLLs aren't found alongside
  the XML docs, indexing still succeeds — `get_class` simply has no
  inherited members to show.

## Evaluation

Measured on a real index built from an NX 12 installation (97,913 API
members) against a 33-query golden set (`eval/golden.jsonl`, mixed
English / Traditional Chinese, four query styles: semantic description,
exact class name, member lookup, builder idiom):

```bash
python eval/run_eval.py --db ~/.nxopen-mcp/index.db
```

| config | Recall@5 | Recall@10 | MRR |
|---|---|---|---|
| dense-only | 69.70% | 78.79% | 0.551 |
| sparse-only | 39.39% | 45.45% | 0.252 |
| **dense+exact (default)** | **69.70%** | **78.79%** | **0.551** |
| dense+sparse+exact | 54.55% | 60.61% | 0.468 |

**Evaluation-driven default.** The original design fused dense, sparse
and exact-name channels with uniform RRF. Measurement showed BGE-M3's
sparse channel *hurt* on this corpus: fusing it dragged Recall@5 from
69.7% down to 54.5%, and a weight sweep (w_sparse ∈ {0.5, 0.3, 0.15})
never recovered the dense-only baseline. The exact-name channel — after
reordering its matches (types first, shortest name first, capped at 3)
— matched the dense baseline while guaranteeing literal-name hits. The
default is therefore **dense + exact**; the sparse channel remains
available via the `channels` parameter of `search()`.

## Demo

> **Placeholder.** A demo GIF showing an agent using `search_api` /
> `find_builder` to write correct NXOpen code will go here.

## License & IP

Code: MIT (see [LICENSE](LICENSE)). This repository contains **no**
Siemens files — no NXOpen XML docs, no DLLs. The index is built locally
from your own licensed NX installation's documentation via
`nxopen-mcp index` and never leaves your machine.

"""MCP server: 4 tools over the hybrid retrieval layer."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from nxopen_mcp.retrieval.hybrid import HybridSearcher
from nxopen_mcp.retrieval.store import Store

_KIND_LABEL = {"T": "class", "P": "property", "M": "method",
               "F": "field", "E": "event"}

_BUILDER_SKELETON = """\
Standard NXOpen builder workflow:
```csharp
var builder = collection.{creator}(camObject);
try {{
    // ... set builder properties ...
    var result = builder.Commit();
}} finally {{
    builder.Destroy();
}}
```"""


def format_member(m: dict) -> str:
    lines = [f"### {m['full_name']}",
             f"- kind: {_KIND_LABEL.get(m['kind'], m['kind'])}"]
    if m.get("summary"):
        lines.append(f"- summary: {m['summary']}")
    if m.get("signature"):
        lines.append(f"- parameters: ({m['signature']})")
    for pname, pdesc in m.get("params", []):
        lines.append(f"  - {pname}: {pdesc}")
    if m.get("returns"):
        lines.append(f"- returns: {m['returns']}")
    if m.get("version"):
        lines.append(f"- since: {m['version']}")
    if m.get("license"):
        lines.append(f"- license: {m['license']}")
    return "\n".join(lines)


def _member_line(m: dict) -> str:
    sig = f"({m['signature']})" if m.get("signature") else ""
    return f"- [{_KIND_LABEL.get(m['kind'], m['kind'])}] {m['name']}{sig} — {m['summary']}"


def create_server(store: Store, searcher: HybridSearcher) -> FastMCP:
    mcp = FastMCP("nxopen")

    @mcp.tool()
    def search_api(query: str, namespace: str | None = None,
                   top_k: int = 10) -> str:
        """Semantic search over the real NXOpen .NET API. Use when you don't
        know the exact class or member name. Query may be English or Chinese."""
        results = searcher.search(query, top_k=top_k, namespace=namespace)
        if not results:
            return "No matching API members found."
        return "\n\n".join(format_member(m) for m in results)

    @mcp.tool()
    def get_class(class_name: str) -> str:
        """List all members of an NXOpen class, including inherited members
        from its ancestor chain. Use when you know the class name."""
        c = store.get_class(class_name)
        if not c:
            return f"Class '{class_name}' not found. Try search_api instead."
        out = [format_member(c["type"]), "", "## Members"]
        out += [_member_line(m) for m in c["members"]] or ["(none)"]
        if c["ancestors"]:
            out.append(f"\n## Inherited (from {' -> '.join(c['ancestors'])})")
            out += [_member_line(m) for m in c["inherited_members"]]
        return "\n".join(out)

    @mcp.tool()
    def get_member(member_name: str) -> str:
        """Get exact signature, parameters, return value, NX version and
        license requirement of a single NXOpen member."""
        m = store.get_member(member_name)
        if not m:
            return f"Member '{member_name}' not found. Try search_api instead."
        return format_member(m)

    @mcp.tool()
    def find_builder(operation: str) -> str:
        """Find the NXOpen Builder class for a CAM operation (e.g. 'cavity
        milling', 'hole drilling') and how to create/commit it."""
        results = searcher.search(f"{operation} builder", top_k=20)
        builders = [m for m in results
                    if m["kind"] == "T" and m["name"].endswith("Builder")]
        if not builders:
            return f"No builder found for '{operation}'. Try search_api."
        out = []
        for b in builders[:3]:
            out.append(format_member(b))
            if b.get("creator_cref"):
                creator = b["creator_cref"].split("(")[0].rsplit(".", 1)[1]
                out.append(f"\nCreate via: `{b['creator_cref']}`")
                out.append(_BUILDER_SKELETON.format(creator=creator))
            out.append("")
        return "\n".join(out)

    return mcp

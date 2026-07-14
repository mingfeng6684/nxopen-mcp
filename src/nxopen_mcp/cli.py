"""CLI entry points: nxopen-mcp index / serve."""
from __future__ import annotations

import os
from pathlib import Path

import typer

app = typer.Typer(help="NXOpen MCP server — accurate NXOpen API for AI agents")

DEFAULT_DB = Path.home() / ".nxopen-mcp" / "index.db"


def _make_embedder():
    if os.environ.get("NXOPEN_MCP_FAKE_EMBEDDER"):
        try:
            from tests.fakes import FakeEmbedder  # test hook only
            return FakeEmbedder()
        except ImportError:
            typer.echo("error: NXOPEN_MCP_FAKE_EMBEDDER is a dev-only hook; "
                       "it requires the tests/ module. Unset the variable or "
                       "use the installed source distribution.")
            raise typer.Exit(1)
    from nxopen_mcp.indexer.embedder import BGEM3Embedder
    typer.echo("loading BGE-M3 model (first run downloads ~2GB) ...")
    return BGEM3Embedder()


@app.command()
def index(
    nx_path: Path = typer.Option(..., help="NX install dir, e.g. D:\\Siemens\\NX12.0"),
    db: Path = typer.Option(DEFAULT_DB, help="Index output path"),
    workers: int = typer.Option(
        1, min=1,
        help="Parallel embedding worker processes. Each worker loads its own "
             "model copy; on an 8-core CPU, 3 workers give ~3x throughput. "
             "Interrupted parallel builds resume where they left off."),
):
    """Build the local index from your own NX installation's doc XMLs."""
    from nxopen_mcp.indexer.build import build_index, find_doc_xmls

    xmls = find_doc_xmls(nx_path)
    if not xmls:
        typer.echo(f"error: no NXOpen*.xml found under {nx_path} "
                   f"(looked in UGII\\managed and the dir itself)")
        raise typer.Exit(1)
    typer.echo(f"found: {', '.join(p.name for p in xmls)}")
    dlls = sorted(xmls[0].parent.glob("NXOpen*.dll")) or None
    if workers > 1:
        # Workers each build their own embedder from the (picklable)
        # module-level factory, so the parent never loads the model.
        n = build_index(xmls, db, dll_paths=dlls, on_progress=typer.echo,
                        workers=workers, embedder_factory=_make_embedder)
    else:
        n = build_index(xmls, db, _make_embedder(), dll_paths=dlls,
                        on_progress=typer.echo)
    typer.echo(f"done: indexed {n} members -> {db}")


@app.command()
def serve(db: Path = typer.Option(DEFAULT_DB, help="Index path")):
    """Start the MCP server (stdio). Requires a built index."""
    if not db.exists():
        typer.echo(f"error: index not found at {db}\n"
                   f"Build it first:\n"
                   f'  nxopen-mcp index --nx-path "D:\\Siemens\\NX12.0"')
        raise typer.Exit(1)
    from nxopen_mcp.indexer.build import load_vec_extension
    from nxopen_mcp.retrieval.hybrid import HybridSearcher
    from nxopen_mcp.retrieval.store import Store
    from nxopen_mcp.server import create_server

    store = Store(db)
    load_vec_extension(store.conn)
    server = create_server(store, HybridSearcher(store, _make_embedder()))
    server.run()  # stdio transport


if __name__ == "__main__":
    app()

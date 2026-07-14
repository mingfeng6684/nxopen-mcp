"""Offline index build pipeline: parse XML -> store -> embed -> vectors."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Callable

from nxopen_mcp.indexer.embedder import Embedder, record_to_text
from nxopen_mcp.indexer.inheritance import build_chains, extract_bases
from nxopen_mcp.indexer.parser import parse_doc_xml
from nxopen_mcp.retrieval.store import Store, load_vec_extension  # noqa: F401  (re-exported for callers)

_BATCH = 64


def serialize_f32(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def find_doc_xmls(nx_path: Path) -> list[Path]:
    """Locate NXOpen*.xml under an NX install dir (or a direct folder)."""
    for cand in (nx_path / "UGII" / "managed", nx_path):
        found = sorted(cand.glob("NXOpen*.xml"))
        if found:
            return found
    return []


def build_index(
    xml_paths: list[Path],
    db_path: Path,
    embedder: Embedder,
    dll_paths: list[Path] | None = None,
    on_progress: Callable[[str], None] = print,
) -> int:
    store = Store(db_path)
    store.create_schema()
    store.conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS dense_vec USING vec0("
        f"member_id INTEGER PRIMARY KEY, embedding float[{embedder.dim}])")

    records = []
    for xml in xml_paths:
        on_progress(f"parsing {xml.name} ...")
        records.extend(parse_doc_xml(xml))
    on_progress(f"parsed {len(records)} members")
    store.insert_members(records)

    if dll_paths:
        on_progress("extracting inheritance from DLLs ...")
        # Inheritance is fully derived from the DLLs on every build, so clear
        # stale rows first -- otherwise re-indexing duplicates every
        # (type, ancestor, depth) row and get_class returns N copies of each
        # ancestor/inherited member after N builds.
        store.conn.execute("DELETE FROM inheritance")
        store.insert_inheritance(build_chains(extract_bases(dll_paths)))

    id_rows = store.conn.execute("SELECT id, full_name FROM members").fetchall()
    id_by_name = {r["full_name"]: r["id"] for r in id_rows}

    for i in range(0, len(records), _BATCH):
        batch = records[i:i + _BATCH]
        dense, sparse = embedder.encode([record_to_text(r) for r in batch])
        for r, dvec, swts in zip(batch, dense, sparse):
            mid = id_by_name[r.full_name]
            store.conn.execute("DELETE FROM dense_vec WHERE member_id = ?", [mid])
            store.conn.execute(
                "INSERT INTO dense_vec(member_id, embedding) VALUES(?,?)",
                [mid, serialize_f32(dvec)])
            store.conn.execute(
                "DELETE FROM sparse_postings WHERE member_id = ?", [mid])
            store.conn.executemany(
                "INSERT INTO sparse_postings(token, member_id, weight) VALUES(?,?,?)",
                [(tok, mid, w) for tok, w in swts.items()])
        on_progress(f"embedded {min(i + _BATCH, len(records))}/{len(records)}")
    store.conn.commit()
    return len(records)

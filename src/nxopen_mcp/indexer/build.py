"""Offline index build pipeline: parse XML -> store -> embed -> vectors."""
from __future__ import annotations

import json
import multiprocessing
import sqlite3
import struct
import traceback
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


def shard_path(db_path: Path, worker_id: int) -> Path:
    return db_path.parent / f"{db_path.name}.shard{worker_id}"


def _create_dense_table(conn: sqlite3.Connection, dim: int) -> None:
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS dense_vec USING vec0("
        f"member_id INTEGER PRIMARY KEY, embedding float[{dim}])")


def _embed_worker(shard: Path, items: list[tuple[int, str]],
                  embedder_factory: Callable[[], Embedder],
                  queue, worker_id: int) -> None:
    """Child process: embed `items` into a private shard sqlite.

    Commits per batch so a killed run leaves usable partial results; on
    restart, member_ids already present in the shard are skipped.
    """
    try:
        conn = sqlite3.connect(str(shard))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings("
            "member_id INTEGER PRIMARY KEY, dense BLOB, sparse_json TEXT)")
        done = {r[0] for r in conn.execute("SELECT member_id FROM embeddings")}
        todo = [(mid, text) for mid, text in items if mid not in done]
        if len(items) - len(todo):
            queue.put(("progress", worker_id, len(items) - len(todo)))
        embedder = embedder_factory() if todo else None
        for i in range(0, len(todo), _BATCH):
            batch = todo[i:i + _BATCH]
            dense, sparse = embedder.encode([t for _, t in batch])
            conn.executemany(
                "INSERT OR REPLACE INTO embeddings VALUES(?,?,?)",
                [(mid, serialize_f32(d), json.dumps(s))
                 for (mid, _), d, s in zip(batch, dense, sparse)])
            conn.commit()
            queue.put(("progress", worker_id, len(batch)))
        conn.close()
        queue.put(("done", worker_id, None))
    except Exception:
        queue.put(("error", worker_id, traceback.format_exc()))


def _merge_shard(store: Store, shard: Path, on_progress) -> None:
    conn = sqlite3.connect(str(shard))
    rows = conn.execute(
        "SELECT member_id, dense, sparse_json FROM embeddings").fetchall()
    conn.close()
    if rows:
        _create_dense_table(store.conn, len(rows[0][1]) // 4)
    for mid, blob, sparse_json in rows:
        store.conn.execute("DELETE FROM dense_vec WHERE member_id = ?", [mid])
        store.conn.execute(
            "INSERT INTO dense_vec(member_id, embedding) VALUES(?,?)",
            [mid, blob])
        store.conn.execute(
            "DELETE FROM sparse_postings WHERE member_id = ?", [mid])
        store.conn.executemany(
            "INSERT INTO sparse_postings(token, member_id, weight) VALUES(?,?,?)",
            [(tok, mid, w) for tok, w in json.loads(sparse_json).items()])
    store.conn.commit()
    shard.unlink()
    on_progress(f"merged {shard.name} ({len(rows)} members)")


def _embed_parallel(store: Store, db_path: Path, items: list[tuple[int, str]],
                    workers: int, embedder_factory: Callable[[], Embedder],
                    on_progress: Callable[[str], None]) -> None:
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    procs = []
    for k in range(workers):
        p = ctx.Process(
            target=_embed_worker,
            args=(shard_path(db_path, k),
                  [it for it in items if it[0] % workers == k],
                  embedder_factory, queue, k))
        p.start()
        procs.append(p)
    total, embedded, running = len(items), 0, workers
    while running:
        try:
            kind, worker_id, payload = queue.get(timeout=5)
        except Exception:  # queue.Empty — check for silently dead workers
            if not any(p.is_alive() for p in procs) and queue.empty():
                raise RuntimeError(
                    "embedding workers exited without reporting completion")
            continue
        if kind == "progress":
            embedded += payload
            on_progress(f"embedded {embedded}/{total}")
        elif kind == "done":
            running -= 1
        else:
            for p in procs:
                p.terminate()
            raise RuntimeError(f"embedding worker {worker_id} failed:\n{payload}")
    for p in procs:
        p.join()
    for k in range(workers):
        if shard_path(db_path, k).exists():
            _merge_shard(store, shard_path(db_path, k), on_progress)


def build_index(
    xml_paths: list[Path],
    db_path: Path,
    embedder: Embedder | None = None,
    dll_paths: list[Path] | None = None,
    on_progress: Callable[[str], None] = print,
    workers: int = 1,
    embedder_factory: Callable[[], Embedder] | None = None,
) -> int:
    """Build the index. With workers == 1, `embedder` (or one created from
    `embedder_factory`) runs in-process. With workers > 1, `embedder_factory`
    must be a picklable zero-arg callable: each spawned worker builds its own
    embedder, so the parent never loads a model. Parallel builds resume —
    members that already have a dense vector are skipped.
    """
    if workers > 1 and embedder_factory is None:
        raise ValueError("workers > 1 requires embedder_factory "
                         "(a picklable zero-arg callable)")
    if workers == 1 and embedder is None:
        if embedder_factory is None:
            raise ValueError("either embedder or embedder_factory is required")
        embedder = embedder_factory()

    store = Store(db_path)
    store.create_schema()
    if workers == 1:
        _create_dense_table(store.conn, embedder.dim)

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

    if workers > 1:
        has_dense = store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'dense_vec'").fetchone()
        already = {r[0] for r in store.conn.execute(
            "SELECT member_id FROM dense_vec")} if has_dense else set()
        items = [(id_by_name[r.full_name], record_to_text(r))
                 for r in records if id_by_name[r.full_name] not in already]
        on_progress(f"embedding {len(items)} members "
                    f"({len(already)} already done) with {workers} workers ...")
        _embed_parallel(store, db_path, items, workers, embedder_factory,
                        on_progress)
        return len(records)

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

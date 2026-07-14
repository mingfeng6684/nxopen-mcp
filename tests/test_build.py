import json
import sqlite3
import struct

from pathlib import Path

import pytest

from nxopen_mcp.indexer.build import build_index, find_doc_xmls, shard_path
from nxopen_mcp.retrieval.store import Store
from tests.fakes import FakeEmbedder

FIXTURE = Path(__file__).parent / "fixtures" / "sample_doc.xml"


def test_find_doc_xmls_in_ugii_managed(tmp_path):
    managed = tmp_path / "UGII" / "managed"
    managed.mkdir(parents=True)
    (managed / "NXOpen.xml").write_text("<doc/>")
    (managed / "NXOpenUI.xml").write_text("<doc/>")
    found = find_doc_xmls(tmp_path)
    assert {p.name for p in found} == {"NXOpen.xml", "NXOpenUI.xml"}


def test_build_index_populates_all_tables(tmp_path):
    db = tmp_path / "index.db"
    n = build_index([FIXTURE], db, FakeEmbedder(), on_progress=lambda _: None)
    assert n == 3
    store = Store(db)
    assert store.get_member("BlankGeometry") is not None
    cnt = store.conn.execute("SELECT count(*) c FROM dense_vec").fetchone()["c"]
    assert cnt == 3
    sp = store.conn.execute("SELECT count(*) c FROM sparse_postings").fetchone()["c"]
    assert sp > 0


def test_rebuild_does_not_duplicate_postings(tmp_path):
    db = tmp_path / "index.db"
    build_index([FIXTURE], db, FakeEmbedder(), on_progress=lambda _: None)
    store = Store(db)
    first = store.conn.execute("SELECT count(*) c FROM sparse_postings").fetchone()["c"]
    store.conn.close()
    build_index([FIXTURE], db, FakeEmbedder(), on_progress=lambda _: None)
    store = Store(db)
    second = store.conn.execute("SELECT count(*) c FROM sparse_postings").fetchone()["c"]
    assert second == first


# --- parallel embedding (workers > 1) ---

def _dense_rows(db: Path) -> dict[int, bytes]:
    store = Store(db)
    rows = store.conn.execute(
        "SELECT member_id, embedding FROM dense_vec").fetchall()
    out = {r["member_id"]: bytes(r["embedding"]) for r in rows}
    store.conn.close()
    return out


def _junk_vec() -> bytes:
    return struct.pack("8f", *([9.0] * 8))


def test_parallel_build_matches_single_worker(tmp_path):
    db1 = tmp_path / "single.db"
    db2 = tmp_path / "parallel.db"
    build_index([FIXTURE], db1, FakeEmbedder(), on_progress=lambda _: None)
    n = build_index([FIXTURE], db2, workers=2, embedder_factory=FakeEmbedder,
                    on_progress=lambda _: None)
    assert n == 3
    assert _dense_rows(db2) == _dense_rows(db1)
    store = Store(db2)
    sp = store.conn.execute("SELECT count(*) c FROM sparse_postings").fetchone()["c"]
    assert sp > 0
    # 合併完成後 shard 檔要清掉
    assert not list(tmp_path.glob("parallel.db.shard*"))


def test_parallel_build_requires_embedder_factory(tmp_path):
    with pytest.raises(ValueError, match="embedder_factory"):
        build_index([FIXTURE], tmp_path / "index.db", FakeEmbedder(),
                    workers=2, on_progress=lambda _: None)


def test_parallel_build_skips_already_embedded_members(tmp_path):
    db = tmp_path / "index.db"
    build_index([FIXTURE], db, FakeEmbedder(), on_progress=lambda _: None)
    store = Store(db)
    mid = store.conn.execute(
        "SELECT id FROM members WHERE name = 'BlankGeometry'").fetchone()["id"]
    store.conn.execute("DELETE FROM dense_vec WHERE member_id = ?", [mid])
    store.conn.execute(
        "INSERT INTO dense_vec(member_id, embedding) VALUES(?,?)",
        [mid, _junk_vec()])
    store.conn.commit()
    store.conn.close()
    build_index([FIXTURE], db, workers=2, embedder_factory=FakeEmbedder,
                on_progress=lambda _: None)
    # 已有向量的 member 不重算(resume 語意)
    assert _dense_rows(db)[mid] == _junk_vec()


def test_parallel_build_resumes_from_leftover_shard(tmp_path):
    db = tmp_path / "index.db"
    # 先建一次拿到穩定的 member id,再清空向量模擬「embedding 中途掛掉」
    build_index([FIXTURE], db, FakeEmbedder(), on_progress=lambda _: None)
    store = Store(db)
    mid = store.conn.execute(
        "SELECT id FROM members WHERE name = 'BlankGeometry'").fetchone()["id"]
    store.conn.execute("DELETE FROM dense_vec")
    store.conn.execute("DELETE FROM sparse_postings")
    store.conn.commit()
    store.conn.close()
    # 模擬上次 run 留下的 shard:該 member 已嵌入(垃圾向量以便辨識)
    shard = shard_path(db, mid % 2)
    conn = sqlite3.connect(str(shard))
    conn.execute("CREATE TABLE embeddings("
                 "member_id INTEGER PRIMARY KEY, dense BLOB, sparse_json TEXT)")
    conn.execute("INSERT INTO embeddings VALUES(?,?,?)",
                 [mid, _junk_vec(), json.dumps({"junktoken": 1.0})])
    conn.commit()
    conn.close()
    build_index([FIXTURE], db, workers=2, embedder_factory=FakeEmbedder,
                on_progress=lambda _: None)
    dense = _dense_rows(db)
    assert len(dense) == 3
    assert dense[mid] == _junk_vec()  # shard 裡的結果被沿用,沒有重算
    assert not shard.exists()


def test_parallel_build_reports_progress(tmp_path):
    messages = []
    build_index([FIXTURE], tmp_path / "index.db", workers=2,
                embedder_factory=FakeEmbedder, on_progress=messages.append)
    embedded = [m for m in messages if m.startswith("embedded ")]
    assert embedded
    assert embedded[-1].startswith("embedded 3/3")


def test_rebuild_does_not_duplicate_inheritance(tmp_path, monkeypatch):
    import nxopen_mcp.indexer.build as build_mod
    monkeypatch.setattr(build_mod, "extract_bases",
                        lambda dlls: {"NXOpen.CAM.CavityMillingBuilder": "NXOpen.Builder"})
    db = tmp_path / "index.db"
    for _ in range(2):
        build_index([FIXTURE], db, FakeEmbedder(),
                     dll_paths=[Path("dummy.dll")], on_progress=lambda _: None)
    store = Store(db)
    rows = store.conn.execute(
        "SELECT count(*) c FROM inheritance WHERE type_name = ?",
        ["NXOpen.CAM.CavityMillingBuilder"]).fetchone()["c"]
    assert rows == 1

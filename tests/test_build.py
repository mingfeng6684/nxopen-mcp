from pathlib import Path
from nxopen_mcp.indexer.build import build_index, find_doc_xmls
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

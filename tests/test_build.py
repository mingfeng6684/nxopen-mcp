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

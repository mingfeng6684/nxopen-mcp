import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

from run_eval import evaluate  # noqa: E402
from nxopen_mcp.indexer.build import build_index, load_vec_extension  # noqa: E402
from nxopen_mcp.retrieval.hybrid import HybridSearcher  # noqa: E402
from nxopen_mcp.retrieval.store import Store  # noqa: E402
from tests.fakes import FakeEmbedder  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_doc.xml"


def test_evaluate_computes_metrics(tmp_path):
    db = tmp_path / "index.db"
    emb = FakeEmbedder()
    build_index([FIXTURE], db, emb, on_progress=lambda _: None)
    store = Store(db)
    load_vec_extension(store.conn)
    searcher = HybridSearcher(store, emb)
    golden = [{"query": "CavityMillingBuilder",
               "expected": "NXOpen.CAM.CavityMillingBuilder"}]
    m = evaluate(searcher, golden, channels={"dense", "sparse", "exact"})
    assert m["recall@5"] == 1.0
    assert m["mrr"] > 0

from pathlib import Path
import pytest
from nxopen_mcp.indexer.build import build_index, load_vec_extension
from nxopen_mcp.retrieval.hybrid import HybridSearcher
from nxopen_mcp.retrieval.store import Store
from nxopen_mcp.server import create_server
from tests.fakes import FakeEmbedder

FIXTURE = Path(__file__).parent / "fixtures" / "sample_doc.xml"


@pytest.fixture
def tools(tmp_path):
    db = tmp_path / "index.db"
    emb = FakeEmbedder()
    build_index([FIXTURE], db, emb, on_progress=lambda _: None)
    store = Store(db)
    load_vec_extension(store.conn)
    server = create_server(store, HybridSearcher(store, emb))
    # FastMCP 的工具函數可經 _tool_manager 取得並直接呼叫
    return {t.name: t.fn for t in server._tool_manager.list_tools()}


def test_registers_exactly_four_tools(tools):
    assert set(tools) == {"search_api", "get_class", "get_member", "find_builder"}


def test_search_api_returns_markdown(tools):
    out = tools["search_api"](query="CavityMillingBuilder")
    assert "NXOpen.CAM.CavityMillingBuilder" in out


def test_get_class_includes_members_and_inheritance_note(tools):
    out = tools["get_class"](class_name="CavityMillingBuilder")
    assert "BlankGeometry" in out


def test_get_member_shows_license(tools):
    out = tools["get_member"](
        member_name="OperationCollection.CreateCavityMillingBuilder")
    assert 'cam_base ("CAM BASE")' in out


def test_find_builder_shows_creator_and_skeleton(tools):
    out = tools["find_builder"](operation="cavity milling")
    assert "CreateCavityMillingBuilder" in out
    assert "Commit" in out  # Builder→Commit→Destroy 骨架


def test_get_class_not_found_is_friendly(tools):
    out = tools["get_class"](class_name="NoSuchClass")
    assert "not found" in out.lower()

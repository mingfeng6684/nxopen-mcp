from pathlib import Path
import pytest
from nxopen_mcp.indexer.parser import parse_doc_xml
from nxopen_mcp.retrieval.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "sample_doc.xml"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "index.db")
    s.create_schema()
    s.insert_members(parse_doc_xml(FIXTURE))
    return s


def test_get_member_exact(store):
    m = store.get_member("NXOpen.CAM.CavityMillingBuilder.BlankGeometry")
    assert m["kind"] == "P"
    assert m["version"] == "NX8.0.0"


def test_get_member_partial_name(store):
    m = store.get_member("BlankGeometry")
    assert m["full_name"] == "NXOpen.CAM.CavityMillingBuilder.BlankGeometry"


def test_get_class_lists_members(store):
    c = store.get_class("CavityMillingBuilder")
    assert c["type"]["full_name"] == "NXOpen.CAM.CavityMillingBuilder"
    names = [m["name"] for m in c["members"]]
    assert "BlankGeometry" in names


def test_inheritance_chain(store):
    store.insert_inheritance([
        ("NXOpen.CAM.CavityMillingBuilder", "NXOpen.CAM.OperationBuilder", 1),
    ])
    # 父類的成員也要能列為 inherited_members
    from nxopen_mcp.indexer.parser import MemberRecord
    store.insert_members([MemberRecord(
        full_name="NXOpen.CAM.OperationBuilder.Description", kind="P",
        namespace="NXOpen.CAM", parent_type="NXOpen.CAM.OperationBuilder",
        name="Description", summary="operation description")])
    c = store.get_class("CavityMillingBuilder")
    assert c["ancestors"] == ["NXOpen.CAM.OperationBuilder"]
    assert any(m["name"] == "Description" for m in c["inherited_members"])


def test_exact_name_matches(store):
    ids = store.exact_name_matches("CavityMillingBuilder")
    assert len(ids) >= 1


def test_reinsert_preserves_member_id(store):
    before = store.conn.execute(
        "SELECT id FROM members WHERE full_name = ?",
        ["NXOpen.CAM.CavityMillingBuilder"]).fetchone()["id"]
    store.insert_members(parse_doc_xml(FIXTURE))  # re-index same docs
    after = store.conn.execute(
        "SELECT id FROM members WHERE full_name = ?",
        ["NXOpen.CAM.CavityMillingBuilder"]).fetchone()["id"]
    assert after == before


def test_exact_name_matches_prefers_type_and_short_names(store):
    from nxopen_mcp.indexer.parser import MemberRecord
    store.insert_members([
        MemberRecord(
            full_name="NXOpen.CAM.DrillMethodBuilder.FeedsBuilder", kind="P",
            namespace="NXOpen.CAM", parent_type="NXOpen.CAM.DrillMethodBuilder",
            name="FeedsBuilder", summary="feeds builder property"),
        MemberRecord(
            full_name="NXOpen.CAM.FeedsBuilder", kind="T",
            namespace="NXOpen.CAM", parent_type=None,
            name="FeedsBuilder", summary="feeds builder class"),
    ])
    ids = store.exact_name_matches("FeedsBuilder")
    first = store.get_members_by_ids(ids[:1])[0]
    assert first["kind"] == "T"  # the class outranks same-named properties
    assert len(ids) <= 3


def test_find_one_partial_match_is_deterministic(store):
    from nxopen_mcp.indexer.parser import MemberRecord
    store.insert_members([
        MemberRecord(
            full_name="NXOpen.CAM.ZLevelBuilder.CutLevel", kind="P",
            namespace="NXOpen.CAM", parent_type="NXOpen.CAM.ZLevelBuilder",
            name="CutLevel", summary="z-level cut level"),
        MemberRecord(
            full_name="NXOpen.CAM.CutLevel", kind="T",
            namespace="NXOpen.CAM", parent_type=None,
            name="CutLevel", summary="cut level class"),
    ])
    for _ in range(3):  # same answer every time: shortest full_name wins
        assert store.get_member("CutLevel")["full_name"] == "NXOpen.CAM.CutLevel"

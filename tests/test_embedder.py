from nxopen_mcp.indexer.embedder import record_to_text
from nxopen_mcp.indexer.parser import MemberRecord


def test_record_to_text_contains_key_fields():
    r = MemberRecord(
        full_name="NXOpen.CAM.CavityMillingBuilder", kind="T",
        namespace="NXOpen.CAM", parent_type=None, name="CavityMillingBuilder",
        summary="Represents a CavityMilling Builder",
        params=[("param", "operation to be edited")])
    text = record_to_text(r)
    assert "NXOpen.CAM.CavityMillingBuilder" in text
    assert "class" in text          # kind 轉可讀標籤
    assert "CavityMilling Builder" in text
    assert "operation to be edited" in text

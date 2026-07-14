from pathlib import Path
from nxopen_mcp.indexer.parser import parse_doc_xml

FIXTURE = Path(__file__).parent / "fixtures" / "sample_doc.xml"


def _records():
    return {r.full_name: r for r in parse_doc_xml(FIXTURE)}


def test_parses_type_entry():
    r = _records()["NXOpen.CAM.CavityMillingBuilder"]
    assert r.kind == "T"
    assert r.namespace == "NXOpen.CAM"
    assert r.parent_type is None
    assert r.name == "CavityMillingBuilder"
    assert "CavityMilling Builder" in r.summary
    assert r.version == "NX5.0.0"
    assert r.creator_cref == "NXOpen.CAM.OperationCollection.CreateCavityMillingBuilder(NXOpen.CAM.CAMObject)"


def test_parses_property_entry():
    r = _records()["NXOpen.CAM.CavityMillingBuilder.BlankGeometry"]
    assert r.kind == "P"
    assert r.parent_type == "NXOpen.CAM.CavityMillingBuilder"
    assert r.namespace == "NXOpen.CAM"
    assert r.license == "None"
    assert r.version == "NX8.0.0"


def test_parses_method_with_params_and_signature():
    r = _records()["NXOpen.CAM.OperationCollection.CreateCavityMillingBuilder"]
    assert r.kind == "M"
    assert r.signature == "NXOpen.CAM.CAMObject"
    assert r.params == [("param", "operation to be edited")]
    assert "operation builder created" in r.returns
    assert r.license == 'cam_base ("CAM BASE")'


def test_skips_malformed_member_names(tmp_path):
    xml = tmp_path / "bad.xml"
    xml.write_text(
        "<doc><members>"
        '<member name="T:Dotless"><summary>bad</summary></member>'
        '<member name="T:NXOpen.Session"><summary>ok</summary></member>'
        "</members></doc>")
    records = list(parse_doc_xml(xml))
    assert [r.full_name for r in records] == ["NXOpen.Session"]

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


def test_lazy_embedder_defers_factory_until_encode():
    from nxopen_mcp.indexer.embedder import LazyEmbedder
    calls = []

    class Fake:
        dim = 8

        def encode(self, texts):
            return "dense", "sparse"

    def factory():
        calls.append(1)
        return Fake()

    lazy = LazyEmbedder(factory)
    assert calls == []            # nothing loaded at construction
    assert lazy.encode(["x"]) == ("dense", "sparse")
    lazy.encode(["y"])
    assert calls == [1]           # factory called exactly once


def test_lazy_embedder_preload_loads_in_background():
    import time
    from nxopen_mcp.indexer.embedder import LazyEmbedder
    calls = []

    class Fake:
        dim = 8

        def encode(self, texts):
            return "d", "s"

    def factory():
        calls.append(1)
        return Fake()

    lazy = LazyEmbedder(factory)
    lazy.start_preload()
    for _ in range(50):  # wait for the background thread
        if calls:
            break
        time.sleep(0.05)
    assert calls == [1]
    assert lazy.encode(["x"]) == ("d", "s")
    assert calls == [1]  # not loaded twice

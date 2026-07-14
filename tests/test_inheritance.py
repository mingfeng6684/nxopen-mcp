from nxopen_mcp.indexer.inheritance import build_chains


def test_expands_multi_level_chain():
    bases = {
        "NXOpen.CAM.HoleDrillingBuilder": "NXOpen.CAM.HoleMachiningBuilder",
        "NXOpen.CAM.HoleMachiningBuilder": "NXOpen.CAM.OperationBuilder",
        "NXOpen.CAM.OperationBuilder": "NXOpen.Builder",
    }
    chains = build_chains(bases)
    hole = [(a, d) for t, a, d in chains if t == "NXOpen.CAM.HoleDrillingBuilder"]
    assert hole == [
        ("NXOpen.CAM.HoleMachiningBuilder", 1),
        ("NXOpen.CAM.OperationBuilder", 2),
        ("NXOpen.Builder", 3),
    ]


def test_handles_cycle_without_hanging():
    bases = {"A": "B", "B": "A"}
    chains = build_chains(bases)
    assert ("A", "B", 1) in chains  # 展開一次即停,不無窮迴圈

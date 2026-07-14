"""Retrieval evaluation: Recall@k / MRR across channel configs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CONFIGS = {
    "dense-only": {"dense"},
    "sparse-only": {"sparse"},
    "dense+exact (default)": {"dense", "exact"},
    "dense+sparse+exact": {"dense", "sparse", "exact"},
}


def evaluate(searcher, golden: list[dict], channels: set[str]) -> dict:
    hits5 = hits10 = 0
    rr_sum = 0.0
    for item in golden:
        results = searcher.search(item["query"], top_k=10, channels=channels)
        names = [r["full_name"] for r in results]
        if item["expected"] in names[:5]:
            hits5 += 1
        if item["expected"] in names[:10]:
            hits10 += 1
        if item["expected"] in names:
            rr_sum += 1.0 / (names.index(item["expected"]) + 1)
    n = len(golden)
    return {"recall@5": hits5 / n, "recall@10": hits10 / n, "mrr": rr_sum / n}


def main() -> None:
    from nxopen_mcp.cli import DEFAULT_DB, _make_embedder
    from nxopen_mcp.indexer.build import load_vec_extension
    from nxopen_mcp.retrieval.hybrid import HybridSearcher
    from nxopen_mcp.retrieval.store import Store

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()

    golden = [json.loads(line) for line in
              (Path(__file__).parent / "golden.jsonl").read_text(
                  encoding="utf-8").splitlines() if line.strip()]
    store = Store(args.db)
    load_vec_extension(store.conn)
    searcher = HybridSearcher(store, _make_embedder())

    print(f"{'config':<24}{'Recall@5':>10}{'Recall@10':>11}{'MRR':>8}")
    for name, chans in CONFIGS.items():
        m = evaluate(searcher, golden, chans)
        print(f"{name:<24}{m['recall@5']:>10.2%}{m['recall@10']:>11.2%}"
              f"{m['mrr']:>8.3f}")


if __name__ == "__main__":
    main()

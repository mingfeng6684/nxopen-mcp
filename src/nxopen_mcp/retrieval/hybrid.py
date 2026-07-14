"""Hybrid retrieval: dense + sparse + exact-name channels fused with RRF."""
from __future__ import annotations

import re
from collections import defaultdict

from nxopen_mcp.indexer.embedder import Embedder
from nxopen_mcp.retrieval.store import Store

_CAMEL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")
_CANDIDATES = 50


def extract_camel_tokens(query: str) -> list[str]:
    return _CAMEL_RE.findall(query)


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> list[int]:
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, mid in enumerate(ranking):
            scores[mid] += 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.__getitem__, reverse=True)


class HybridSearcher:
    def __init__(self, store: Store, embedder: Embedder):
        self.store = store
        self.embedder = embedder

    def _dense(self, qvec) -> list[int]:
        from nxopen_mcp.indexer.build import serialize_f32
        rows = self.store.conn.execute(
            "SELECT member_id FROM dense_vec WHERE embedding MATCH ? "
            "ORDER BY distance LIMIT ?",
            [serialize_f32(qvec), _CANDIDATES]).fetchall()
        return [r["member_id"] for r in rows]

    def _sparse(self, qweights: dict[str, float]) -> list[int]:
        scores: dict[int, float] = defaultdict(float)
        for tok, qw in qweights.items():
            for r in self.store.conn.execute(
                    "SELECT member_id, weight FROM sparse_postings WHERE token = ?",
                    [tok]):
                scores[r["member_id"]] += qw * r["weight"]
        ranked = sorted(scores, key=scores.__getitem__, reverse=True)
        return ranked[:_CANDIDATES]

    def _exact(self, query: str) -> list[int]:
        ids: list[int] = []
        for tok in extract_camel_tokens(query):
            ids.extend(self.store.exact_name_matches(tok))
        return ids

    # Default channels chosen by evaluation on a 33-query golden set:
    # BGE-M3's sparse channel *lowered* Recall@5 from 69.7% to 54.5% when
    # RRF-fused with dense on this corpus (at any fusion weight), so the
    # default is dense + exact; sparse remains available via `channels`.
    DEFAULT_CHANNELS = frozenset({"dense", "exact"})

    def search(self, query: str, top_k: int = 10,
               namespace: str | None = None,
               channels: set[str] = DEFAULT_CHANNELS,
               ) -> list[dict]:
        exact = self._exact(query) if "exact" in channels else []
        rankings: list[list[int]] = []
        if channels & {"dense", "sparse"}:
            dense_q, sparse_q = self.embedder.encode([query])
            if "dense" in channels:
                rankings.append(self._dense(dense_q[0]))
            if "sparse" in channels:
                rankings.append(self._sparse(sparse_q[0]))
        fused_rest = rrf_fuse(rankings)
        # Exact-name matches are precise (user typed a literal class/member
        # name), so they're surfaced ahead of similarity-only channels
        # rather than merely contributing one vote to the RRF sum.
        seen: set[int] = set()
        fused: list[int] = []
        for mid in [*exact, *fused_rest]:
            if mid not in seen:
                seen.add(mid)
                fused.append(mid)
        results = self.store.get_members_by_ids(fused)
        if namespace:
            results = [r for r in results if r["namespace"].startswith(namespace)]
        return results[:top_k]

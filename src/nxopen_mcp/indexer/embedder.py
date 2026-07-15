"""Embedding: chunk text composition + BGE-M3 (dense + sparse) wrapper."""
from __future__ import annotations

from typing import Protocol

import numpy as np

from nxopen_mcp.indexer.parser import MemberRecord

_KIND_LABEL = {"T": "class", "P": "property", "M": "method",
               "F": "field", "E": "event"}


def record_to_text(r: MemberRecord) -> str:
    """One member = one chunk. API docs are naturally structured."""
    parts = [r.full_name, _KIND_LABEL.get(r.kind, r.kind), r.summary]
    for pname, pdesc in r.params:
        parts.append(f"{pname}: {pdesc}")
    if r.returns:
        parts.append(f"returns: {r.returns}")
    return " | ".join(p for p in parts if p)


class Embedder(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> tuple[np.ndarray, list[dict[str, float]]]:
        """Return (L2-normalized dense matrix (n, dim), per-text sparse weights)."""
        ...


class LazyEmbedder:
    """Defers constructing the real embedder until the first encode().

    `serve` must answer the MCP initialize handshake within the client's
    startup timeout (~30s); loading BGE-M3 takes minutes on CPU. Exact
    lookups (get_class / get_member) never touch the model at all.
    """

    dim = 1024

    def __init__(self, factory) -> None:
        self._factory = factory
        self._real: Embedder | None = None

    def encode(self, texts: list[str]) -> tuple[np.ndarray, list[dict[str, float]]]:
        if self._real is None:
            self._real = self._factory()
        return self._real.encode(texts)


class BGEM3Embedder:
    """Real embedder. Heavy import is deferred so CI never touches it."""

    dim = 1024

    def __init__(self) -> None:
        from FlagEmbedding import BGEM3FlagModel  # lazy: pulls torch
        import torch  # noqa: PLC0415 — decide fp16 by device
        # fp16 is a big win on CUDA but *slower* than fp32 on CPU
        # (no hardware fp16 path), so enable it only when a GPU is used.
        self._model = BGEM3FlagModel(
            "BAAI/bge-m3", use_fp16=torch.cuda.is_available())

    def encode(self, texts: list[str]) -> tuple[np.ndarray, list[dict[str, float]]]:
        # max_length=1024 (default 8192): API-doc chunks rarely carry useful
        # signal past 1k tokens, and CPU attention cost grows quadratically —
        # a few giant NXOpen.UF entries would otherwise stall a whole batch.
        out = self._model.encode(
            texts, return_dense=True, return_sparse=True,
            batch_size=32, max_length=1024)
        dense = np.asarray(out["dense_vecs"], dtype=np.float32)
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        dense = dense / np.where(norms == 0, 1.0, norms)
        sparse = [
            {tok: float(w) for tok, w in d.items()}
            for d in out["lexical_weights"]
        ]
        return dense, sparse

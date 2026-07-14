"""Deterministic fake embedder for tests — no model download, dim=8."""
import hashlib
import numpy as np


class FakeEmbedder:
    dim = 8

    def encode(self, texts):
        dense = np.zeros((len(texts), self.dim), dtype=np.float32)
        sparse = []
        for i, t in enumerate(texts):
            h = hashlib.md5(t.encode()).digest()
            v = np.frombuffer(h[:self.dim * 2], dtype=np.uint16).astype(np.float32)
            dense[i] = v / (np.linalg.norm(v) or 1.0)
            sparse.append({tok.lower(): 1.0 for tok in t.split()[:8]})
        return dense, sparse

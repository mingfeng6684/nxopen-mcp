"""Extract inheritance chains from .NET DLLs (optional, degrades gracefully)."""
from __future__ import annotations

import sys
from pathlib import Path


def build_chains(bases: dict[str, str]) -> list[tuple[str, str, int]]:
    """Expand {type: base} into (type, ancestor, depth) rows. Cycle-safe."""
    out: list[tuple[str, str, int]] = []
    for t in bases:
        seen = {t}
        cur, depth = bases.get(t), 1
        while cur and cur not in seen:
            out.append((t, cur, depth))
            seen.add(cur)
            cur = bases.get(cur)
            depth += 1
    return out


def extract_bases(dll_paths: list[Path]) -> dict[str, str]:
    """Reflect over DLLs with pythonnet. Returns {} on any failure —
    the index still builds, just without inheritance chains."""
    try:
        import clr  # type: ignore
        from System.Reflection import Assembly  # type: ignore
    except Exception:
        print("warning: pythonnet unavailable; skipping inheritance extraction",
              file=sys.stderr)
        return {}
    bases: dict[str, str] = {}
    for dll in dll_paths:
        try:
            asm = Assembly.LoadFile(str(dll))
            for t in asm.GetExportedTypes():
                if t.BaseType is not None and t.FullName and t.BaseType.FullName:
                    if t.BaseType.FullName != "System.Object":
                        bases[t.FullName] = t.BaseType.FullName
        except Exception as e:  # noqa: BLE001 — degrade, never crash indexing
            print(f"warning: could not reflect {dll.name}: {e}", file=sys.stderr)
    return bases

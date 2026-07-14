"""Parse .NET documentation XML (NXOpen.xml et al.) into structured records."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

_VERSION_RE = re.compile(r"Created in (NX[\d.]+)")
_LICENSE_RE = re.compile(r"License requirements:\s*(.+?)\s*\.?\s*$", re.DOTALL)


@dataclass
class MemberRecord:
    full_name: str            # "NXOpen.CAM.CavityMillingBuilder.BlankGeometry"
    kind: str                 # T / P / M / F / E
    namespace: str            # "NXOpen.CAM"
    parent_type: str | None   # None for kind == "T"
    name: str                 # short name, last segment
    summary: str
    params: list[tuple[str, str]] = field(default_factory=list)
    returns: str | None = None
    version: str | None = None
    license: str | None = None
    creator_cref: str | None = None  # only for T: builder entries
    signature: str | None = None     # method param types "A,B" (raw)


def _text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return " ".join("".join(elem.itertext()).split())


def parse_doc_xml(path: Path) -> Iterator[MemberRecord]:
    for _, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag != "member":
            continue
        raw = elem.get("name", "")
        if len(raw) < 3 or raw[1] != ":":
            elem.clear()
            continue
        kind = raw[0]
        body = raw[2:]
        signature = None
        if "(" in body:
            body, sig = body.split("(", 1)
            signature = sig.rstrip(")")
        if kind == "T":
            namespace, name = body.rsplit(".", 1)
            parent_type = None
        else:
            parent_type, name = body.rsplit(".", 1)
            namespace = parent_type.rsplit(".", 1)[0]

        summary = _text(elem.find("summary"))
        remarks = _text(elem.find("remarks"))
        version = m.group(1) if (m := _VERSION_RE.search(remarks)) else None
        lic = m.group(1).rstrip(". ") if (m := _LICENSE_RE.search(remarks)) else None

        creator_cref = None
        if kind == "T":
            rem = elem.find("remarks")
            if rem is not None:
                for see in rem.iter("see"):
                    cref = see.get("cref", "")
                    if cref.startswith("M:") and ".Create" in cref:
                        creator_cref = cref[2:]
                        break

        params = [
            (p.get("name", ""), _text(p))
            for p in elem.findall("param")
        ]
        returns = _text(elem.find("returns")) or None

        yield MemberRecord(
            full_name=body, kind=kind, namespace=namespace,
            parent_type=parent_type, name=name, summary=summary,
            params=params, returns=returns, version=version,
            license=lic, creator_cref=creator_cref, signature=signature,
        )
        elem.clear()

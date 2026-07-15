"""SQLite storage: structured member data, inheritance chains, exact lookup."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

from nxopen_mcp.indexer.parser import MemberRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS members(
    id INTEGER PRIMARY KEY,
    full_name TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    namespace TEXT NOT NULL,
    parent_type TEXT,
    name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '[]',
    returns TEXT,
    version TEXT,
    license TEXT,
    creator_cref TEXT,
    signature TEXT
);
CREATE INDEX IF NOT EXISTS idx_members_parent ON members(parent_type);
CREATE INDEX IF NOT EXISTS idx_members_name ON members(name);
CREATE TABLE IF NOT EXISTS inheritance(
    type_name TEXT NOT NULL,
    ancestor TEXT NOT NULL,
    depth INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inherit_type ON inheritance(type_name);
CREATE TABLE IF NOT EXISTS sparse_postings(
    token TEXT NOT NULL,
    member_id INTEGER NOT NULL,
    weight REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sparse_token ON sparse_postings(token);
"""

_COLS = ("full_name kind namespace parent_type name summary params_json "
         "returns version license creator_cref signature").split()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["params"] = json.loads(d.pop("params_json", "[]"))
    return d


def load_vec_extension(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension so dense_vec (a vec0 virtual table) is
    queryable from any connection. Extensions must be loaded per-connection,
    so this runs on every Store() construction. Degrades gracefully if
    sqlite-vec isn't installed or extension loading isn't supported by this
    Python build; on failure, prints a one-line warning to stderr.
    """
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as e:
        print(f"warning: could not load sqlite-vec extension: {e}",
              file=sys.stderr)


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        load_vec_extension(self.conn)

    def create_schema(self) -> None:
        self.conn.executescript(_SCHEMA)

    def insert_members(self, records: Iterable[MemberRecord]) -> None:
        rows = [
            (r.full_name, r.kind, r.namespace, r.parent_type, r.name,
             r.summary, json.dumps(r.params), r.returns, r.version,
             r.license, r.creator_cref, r.signature)
            for r in records
        ]
        # Use ON CONFLICT DO UPDATE to preserve existing member IDs
        # This prevents orphaning sparse_postings and dense vector references
        placeholders = ','.join('?' * len(_COLS))
        conflict_updates = ','.join(f"{col}=excluded.{col}" for col in _COLS[1:])
        upsert_sql = (
            f"INSERT INTO members({','.join(_COLS)}) VALUES({placeholders}) "
            f"ON CONFLICT(full_name) DO UPDATE SET {conflict_updates}"
        )
        self.conn.executemany(upsert_sql, rows)
        self.conn.commit()

    def insert_inheritance(self, chains: Iterable[tuple[str, str, int]]) -> None:
        self.conn.executemany(
            "INSERT INTO inheritance(type_name, ancestor, depth) VALUES(?,?,?)",
            list(chains))
        self.conn.commit()

    def _find_one(self, name: str, kind: str | None = None) -> sqlite3.Row | None:
        kind_sql = " AND kind = ?" if kind else ""
        kp = [kind] if kind else []
        # Deterministic tie-breaks: shortest full_name first, then
        # alphabetical — a partial-name lookup always returns the same row.
        order = " ORDER BY length(full_name), full_name LIMIT 1"
        for sql, p in [
            (f"SELECT * FROM members WHERE full_name = ?{kind_sql}", [name, *kp]),
            (f"SELECT * FROM members WHERE name = ?{kind_sql}{order}", [name, *kp]),
            (f"SELECT * FROM members WHERE full_name LIKE ?{kind_sql}{order}",
             [f"%{name}%", *kp]),
        ]:
            if row := self.conn.execute(sql, p).fetchone():
                return row
        return None

    def get_member(self, full_name: str) -> dict | None:
        row = self._find_one(full_name)
        return _row_to_dict(row) if row else None

    def get_class(self, class_name: str) -> dict | None:
        row = self._find_one(class_name, kind="T")
        if not row:
            return None
        type_d = _row_to_dict(row)
        members = [
            _row_to_dict(r) for r in self.conn.execute(
                "SELECT * FROM members WHERE parent_type = ? ORDER BY kind, name",
                [type_d["full_name"]])
        ]
        ancestors = [
            r["ancestor"] for r in self.conn.execute(
                "SELECT ancestor FROM inheritance WHERE type_name = ? ORDER BY depth",
                [type_d["full_name"]])
        ]
        inherited = []
        for anc in ancestors:
            inherited += [
                _row_to_dict(r) for r in self.conn.execute(
                    "SELECT * FROM members WHERE parent_type = ? ORDER BY kind, name",
                    [anc])
            ]
        return {"type": type_d, "members": members,
                "ancestors": ancestors, "inherited_members": inherited}

    def get_members_by_ids(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM members WHERE id IN ({q})", ids).fetchall()
        by_id = {r["id"]: _row_to_dict(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def exact_name_matches(self, token: str) -> list[int]:
        # Name equality first, types before members, shortest name first —
        # evaluation showed the old broad LIKE flood (20 unordered rows)
        # buried the intended match under its own class members.
        rows = self.conn.execute(
            "SELECT id FROM members WHERE name = ? "
            "ORDER BY (kind = 'T') DESC, length(full_name) LIMIT 3",
            [token]).fetchall()
        if not rows:  # partial token, e.g. "CavityMilling" for the builder
            rows = self.conn.execute(
                "SELECT id FROM members WHERE full_name LIKE ? "
                "ORDER BY length(full_name) LIMIT 3",
                [f"%.{token}%"]).fetchall()
        return [r["id"] for r in rows]

"""PostgreSQL read/write helpers for the RDS classifier pipeline.

Identifier safety
-----------------
The ``table`` and ``pk`` arguments are SQL identifiers and CANNOT be
parameterised with %s. They are always wrapped in
``psycopg2.sql.Identifier`` before composition. Callers MUST NOT
build statements outside this module.

Write policy
------------
``update_row`` builds the SET clause from only the columns present in
the ``writes`` dict. A column whose value is None or empty string is
omitted upstream by the pipeline -- if it reaches this layer, it WILL
be written. This is intentional: this module trusts its caller and
does not second-guess the value type. The NULL-vs-empty policy lives
in ``classify_rds``.
"""
from __future__ import annotations

from typing import Iterator

from psycopg2 import sql


def iter_unclassified(conn, table: str, pk: str, fetch_size: int
                      ) -> Iterator[tuple]:
    """Yield ``(pk_value, doc_type, type, discipline_id, title)`` for
    every row where any classification target is NULL or empty.

    Uses a named (server-side) cursor so the result set streams instead
    of loading entirely into client memory. ``itersize`` controls the
    per-round-trip fetch volume.

    The generator must be fully consumed (or its `.close()` called)
    before another statement is issued on the same connection. Callers
    typically iterate it inline.
    """
    select_q = sql.SQL(
        "SELECT {pk}, doc_type, type, discipline_id, title "
        "FROM {tbl} "
        "WHERE doc_type IS NULL OR doc_type = '' "
        "   OR type     IS NULL OR type     = '' "
        "   OR discipline_id IS NULL"
    ).format(
        pk=sql.Identifier(pk),
        tbl=sql.Identifier(table),
    )
    # Unique cursor name so re-entry on the same connection (e.g. a
    # caller running classify_from_rds twice without closing conn)
    # cannot collide with a still-open server-side cursor.
    cur = conn.cursor(name=f"classify_cur_{id(conn)}")
    try:
        cur.itersize = fetch_size
        cur.execute(select_q)
        for row in cur:
            yield row
    finally:
        cur.close()


def update_row(cur, table: str, pk: str, pk_value, writes: dict) -> bool:
    """Issue an UPDATE for the listed columns. Returns True if a
    statement was sent (i.e. ``writes`` was non-empty), False otherwise.

    The cursor is the caller's regular (non-server-side) cursor.
    """
    if not writes:
        return False
    cols = list(writes.keys())
    set_clause = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in cols
    )
    stmt = sql.SQL("UPDATE {tbl} SET {sets} WHERE {pk} = %s").format(
        tbl=sql.Identifier(table),
        sets=set_clause,
        pk=sql.Identifier(pk),
    )
    cur.execute(stmt, [*writes.values(), pk_value])
    return True


from classifier.core.record import Record, ClassificationResult  # noqa: E402


class RdsReader:
    """Streams unclassified rows as Records. Does NOT own the connection
    (caller's lifecycle); the server-side cursor is closed inside
    iter_unclassified.
    """
    def __init__(self, conn, *, table: str = "documents",
                 pk: str = "document_id", fetch_size: int = 1000):
        self.conn = conn
        self.table = table
        self.pk = pk
        self.fetch_size = fetch_size

    def __iter__(self):
        for pk_value, dt, ty, disc, title in iter_unclassified(
            self.conn, table=self.table, pk=self.pk, fetch_size=self.fetch_size
        ):
            yield Record(
                title="" if title is None else str(title),
                doc_type="" if dt is None else str(dt),
                type="" if ty is None else str(ty),
                discipline_id="" if disc is None else str(disc),
                handle=pk_value,
            )

    def close(self) -> None:
        pass


class RdsWriter:
    """Per-row UPDATE sink. Owns commit cadence (every commit_every processed
    rows + a final commit on close) and its own non-server-side cursor. Does
    NOT own the connection.
    """
    def __init__(self, conn, *, table: str = "documents",
                 pk: str = "document_id", commit_every: int = 500):
        self.conn = conn
        self.table = table
        self.pk = pk
        self.commit_every = commit_every
        self.cur = conn.cursor()
        self.processed = 0

    def write(self, rec: Record, result: ClassificationResult, writes) -> None:
        w = dict(writes)
        if "discipline_id" in w:
            w["discipline_id"] = int(w["discipline_id"])   # SQL needs int FK
        update_row(self.cur, table=self.table, pk=self.pk,
                   pk_value=rec.handle, writes=w)
        self.processed += 1
        if self.processed % self.commit_every == 0:
            self.conn.commit()

    def close(self) -> None:
        self.cur.close()

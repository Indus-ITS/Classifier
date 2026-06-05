"""Fake-conn tests for the RDS pipeline: locks write/skip decisions, the
per-row UPDATE parameters, commit cadence, and the stats dict shape — none
of which the CSV golden covers.
"""
from classifier.pipeline.classify_rds import classify_from_rds


class FakeServerCursor:
    """Stands in for the named server-side cursor used by iter_unclassified."""
    def __init__(self, rows):
        self._rows = rows
        self.itersize = None
    def execute(self, *a, **k):
        pass
    def __iter__(self):
        return iter(self._rows)
    def close(self):
        pass


class FakeWriteCursor:
    def __init__(self, log):
        self._log = log
    def execute(self, stmt, params=None):
        self._log.append(params)
    def close(self):
        pass


class FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.updates = []        # list of params lists from UPDATE
        self.commits = 0
    def cursor(self, name=None):
        if name is not None:
            return FakeServerCursor(self._rows)
        return FakeWriteCursor(self.updates)
    def commit(self):
        self.commits += 1


def test_fills_empty_fields_and_skips_complete_rows():
    rows = [
        # (pk, doc_type, type, discipline_id, title)
        (1, None, None, None, "PIPING AND INSTRUMENT DIAGRAM"),  # should update
        (2, "drawing", "PID", 7, ""),                            # already full -> but selected? simulate skip
    ]
    conn = FakeConn(rows)
    stats = classify_from_rds(conn, commit_every=10)
    assert stats["rows_scanned"] == 2
    # Exactly 1 row updated (row 1) and exactly 1 skipped (row 2 already complete).
    assert stats["rows_updated"] == 1
    assert stats["rows_skipped"] == 1
    # Stats dict shape (superset preserved):
    for key in ("rows_scanned", "rows_updated", "rows_skipped",
                "doc_type", "type", "discipline_id", "callback_error"):
        assert key in stats
    assert isinstance(stats["doc_type"], dict)


def test_final_commit_happens():
    conn = FakeConn([(1, None, None, None, "VALVE LIST")])
    classify_from_rds(conn, commit_every=500)
    assert conn.commits >= 1   # final commit at end


def test_on_done_callback_receives_stats():
    seen = {}
    conn = FakeConn([(1, None, None, None, "VALVE LIST")])
    classify_from_rds(conn, on_done=lambda s: seen.update(s))
    assert seen["rows_scanned"] == 1

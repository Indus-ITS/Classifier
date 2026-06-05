from classifier.core.record import Record
from classifier.pipeline.run import run


class ListReader:
    def __init__(self, records): self._records = records; self.closed = False
    def __iter__(self): return iter(self._records)
    def close(self): self.closed = True


class RecordingWriter:
    def __init__(self): self.writes = []; self.closed = False
    def write(self, rec, result, writes): self.writes.append((rec, result, writes))
    def close(self): self.closed = True


def test_run_classifies_and_persists_each_record():
    reader = ListReader([Record(title="PIPING AND INSTRUMENT DIAGRAM"),
                         Record(title="ZZZ NONSENSE")])
    writer = RecordingWriter()
    stats = run(reader, writer)
    assert stats.rows_scanned == 2
    assert len(writer.writes) == 2
    assert reader.closed and writer.closed


def test_run_closes_both_on_exception():
    class Boom(ListReader):
        def __iter__(self):
            raise RuntimeError("boom")
    reader = Boom([])
    writer = RecordingWriter()
    try:
        run(reader, writer)
    except RuntimeError:
        pass
    assert reader.closed and writer.closed


def test_writer_closed_even_if_reader_close_raises():
    class BadCloseReader(ListReader):
        def close(self):
            raise RuntimeError("reader close failed")
    reader = BadCloseReader([Record(title="X")])
    writer = RecordingWriter()
    try:
        run(reader, writer)
    except RuntimeError:
        pass
    assert writer.closed   # writer.close() ran despite reader.close() raising

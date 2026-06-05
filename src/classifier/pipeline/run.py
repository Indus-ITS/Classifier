"""The single orchestration loop: read -> classify -> persist.

Generic over any RecordReader (input source) and ResultWriter (output sink).
Core decides what to write (plan_writes); the writer only persists. run()
owns the lifecycle of both reader and writer and closes them even on error.
Per-record errors propagate (fail-fast), matching historical behavior.
"""
from __future__ import annotations

from typing import Callable, Optional

from classifier.core.classify import classify_record, plan_writes
from classifier.pipeline.stats import Stats


def run(reader, writer, *,
        on_progress: Optional[Callable[[Stats], None]] = None) -> Stats:
    stats = Stats()
    try:
        for rec in reader:
            result = classify_record(rec)
            writes = plan_writes(rec, result)
            writer.write(rec, result, writes)
            stats.observe(rec, result, writes)
            if on_progress is not None:
                on_progress(stats)
    finally:
        # Close both even if the first raises; reader's exception still propagates.
        try:
            reader.close()
        finally:
            writer.close()
    return stats

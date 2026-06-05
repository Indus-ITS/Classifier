"""Hand-maintained."""
from __future__ import annotations

# Each entry: type -> (dest_discipline_id, share, support_count)
# share and support_count are informational; only dest_id is used at classify time.
TYPE_TO_DISCIPLINE: dict[str, int] = {
    'DBD': 4,  # 100% of 5 rows
    'DGA': 13,  # 93% of 27 rows
    'DSL': 4,  # 100% of 7 rows
}

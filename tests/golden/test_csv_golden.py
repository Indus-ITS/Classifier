"""Golden test: `classify` must reproduce tests/golden/classified.csv byte-for-byte.

Runs the real classifier against the real input but redirects OUTPUT_PATH to a
temp file so the tracked output/ file is never touched by the test.
"""
from pathlib import Path

from classifier.cli import classify


def test_classify_reproduces_golden(tmp_path, monkeypatch):
    out = tmp_path / "classified.csv"
    monkeypatch.setattr(classify, "OUTPUT_PATH", out)

    classify.main()

    golden = Path("tests/golden/classified.csv").read_bytes()
    produced = out.read_bytes()
    assert produced == golden, "classify output drifted from golden"

from pathlib import Path
from classifier.pipeline.staleness import stale_configs


def test_flags_config_older_than_training(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    cfg = tmp_path / "rules.py"
    cfg.write_text("x = 1")
    # make a training CSV newer than the config
    newer = csv_dir / "a.csv"
    newer.write_text("h\n")
    import os, time
    old = cfg.stat().st_mtime - 100
    os.utime(cfg, (old, old))

    stale = stale_configs([(cfg, "learn-x")], csv_dir)
    assert stale == [(cfg, "learn-x")]


def test_empty_when_no_training_dir(tmp_path):
    cfg = tmp_path / "rules.py"; cfg.write_text("x=1")
    assert stale_configs([(cfg, "learn-x")], tmp_path / "missing") == []

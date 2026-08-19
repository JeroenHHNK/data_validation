"""Tests for stable key normalization, migration, and folder matching."""
import json
import shutil
from pathlib import Path

import pytest

from dataval._utils import (
    normalize_wiertsema_key,
    parse_stable_key,
    match_origin_folder,
    stable_key_from_csvs,
)
from dataval.migrate_wiertsema import run_migration, _collect_plans, _detect_conflicts


# ---------------------------------------------------------------------------
# Key normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("84507_1", "84507-1"),
    ("84507-1", "84507-1"),
    ("Schellingwoude _84507_1", "84507-1"),
    ("Beemster_86349_1_deel_1", "86349-1"),
    ("Beemster_oud_83034_1", "83034-1"),
    ("Schermer_88111_1_deel_2", "88111-1"),
    ("Schellingwoude_84507_2", "84507-2"),
])
def test_normalize_wiertsema_key(raw, expected):
    assert normalize_wiertsema_key(raw) == expected


@pytest.mark.parametrize("raw", [
    "peilbuisdata_alle_sensoren_07042026",
    "some_random_folder",
])
def test_normalize_returns_none_for_unresolvable(raw):
    assert normalize_wiertsema_key(raw) is None


@pytest.mark.parametrize("filename,expected", [
    ("Beemster_86349_1_deel_1.xlsx", "86349-1"),
    ("Beemster_86349_1_deel_2.xlsx", "86349-1"),
    ("Schellingwoude _84507_1.xlsx", "84507-1"),
    ("Schellingwoude_84507_2.xlsx", "84507-2"),
    ("Beemster_oud_83034_1.xlsx", "83034-1"),
    ("peilbuisdata_alle_sensoren_07042026.xlsx", "peilbuisdata_alle_sensoren_07042026"),
])
def test_parse_stable_key_wiertsema(filename, expected):
    assert parse_stable_key(filename, "wiertsema") == expected


def test_parse_stable_key_fugro_unchanged():
    f = "4424-260484_HHW_normaal_01-01-2024 00_00_00_26-07-2026 00_00_00_Uur_20260729090847.csv"
    assert parse_stable_key(f, "fugro") == "4424-260484_HHW_normaal_Uur"


# ---------------------------------------------------------------------------
# Folder matching
# ---------------------------------------------------------------------------

def test_match_origin_folder(tmp_path):
    wiertsema = tmp_path / "wiertsema"
    (wiertsema / "Beemster_86349_1_deel_1" / "only_csv").mkdir(parents=True)
    (wiertsema / "Beemster_86349_1_deel_1" / "only_csv" / "86349-1 HB029PB01.csv").write_text("a")

    assert match_origin_folder("86349-1", "wiertsema", tmp_path) == "Beemster_86349_1_deel_1"


def test_match_origin_folder_csv_fallback(tmp_path):
    wiertsema = tmp_path / "wiertsema"
    (wiertsema / "peilbuisdata_07042026" / "only_csv").mkdir(parents=True)
    (wiertsema / "peilbuisdata_07042026" / "only_csv" / "86349-1 HB002PB01.csv").write_text("a")

    assert match_origin_folder("86349-1", "wiertsema", tmp_path) == "peilbuisdata_07042026"


def test_match_origin_folder_already_migrated(tmp_path):
    wiertsema = tmp_path / "wiertsema"
    (wiertsema / "86349-1" / "only_csv").mkdir(parents=True)
    (wiertsema / "86349-1" / "only_csv" / "86349-1 HB029PB01.csv").write_text("a")

    assert match_origin_folder("86349-1", "wiertsema", tmp_path) == "86349-1"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

@pytest.fixture
def migration_tree(tmp_path):
    """Create a mock output_data/wiertsema tree for migration testing."""
    w = tmp_path / "wiertsema"

    # Folder A: will be renamed
    (w / "Belmermeer_87097_1" / "only_csv").mkdir(parents=True)
    (w / "Belmermeer_87097_1" / "only_csv" / "87097-1 HB178PB01.csv").write_text("data_a")
    (w / "Belmermeer_87097_1" / "figures").mkdir()
    (w / "Belmermeer_87097_1" / "figures" / "87097-1 HB178PB01.html").write_text("fig_a")

    # Folders B1 and B2: will be merged into 88111-1
    (w / "Schermer_88111_1_deel_1" / "only_csv").mkdir(parents=True)
    (w / "Schermer_88111_1_deel_1" / "only_csv" / "88111-1 HB029PB01.csv").write_text("deel1")
    (w / "Schermer_88111_1_deel_2" / "only_csv").mkdir(parents=True)
    (w / "Schermer_88111_1_deel_2" / "only_csv" / "88111-1 HB001PB01.csv").write_text("deel2")

    # Unresolvable folder
    (w / "random_data" / "only_csv").mkdir(parents=True)
    (w / "random_data" / "only_csv" / "something.csv").write_text("x")

    return w


def test_migration_dry_run(migration_tree):
    report = run_migration(migration_tree, apply=False)
    assert "DRY-RUN" in report
    assert "87097-1" in report
    assert "88111-1" in report
    # Nothing moved
    assert (migration_tree / "Belmermeer_87097_1").is_dir()
    assert (migration_tree / "Schermer_88111_1_deel_1").is_dir()


def test_migration_apply_rename(migration_tree):
    run_migration(migration_tree, apply=True)

    # Belmermeer renamed to 87097-1
    assert (migration_tree / "87097-1" / "only_csv" / "87097-1 HB178PB01.csv").exists()
    assert not (migration_tree / "Belmermeer_87097_1").exists()
    # Figures carried across
    assert (migration_tree / "87097-1" / "figures" / "87097-1 HB178PB01.html").exists()


def test_migration_apply_merge(migration_tree):
    run_migration(migration_tree, apply=True)

    target = migration_tree / "88111-1" / "only_csv"
    assert target.is_dir()
    assert (target / "88111-1 HB029PB01.csv").exists()
    assert (target / "88111-1 HB001PB01.csv").exists()
    assert not (migration_tree / "Schermer_88111_1_deel_1").exists()
    assert not (migration_tree / "Schermer_88111_1_deel_2").exists()


def test_migration_merge_collision(tmp_path):
    """Two folders have the same file — newer wins, older gets _old suffix."""
    w = tmp_path / "wiertsema"
    (w / "Loc_99999_1_deel_1" / "only_csv").mkdir(parents=True)
    f1 = w / "Loc_99999_1_deel_1" / "only_csv" / "99999-1 sensor.csv"
    f1.write_text("old_data")

    (w / "Loc_99999_1_deel_2" / "only_csv").mkdir(parents=True)
    f2 = w / "Loc_99999_1_deel_2" / "only_csv" / "99999-1 sensor.csv"
    f2.write_text("new_data")

    import time
    import os
    # Make f2 newer
    old_time = f1.stat().st_mtime - 100
    os.utime(f1, (old_time, old_time))

    run_migration(w, apply=True)

    target_csv = w / "99999-1" / "only_csv"
    assert (target_csv / "99999-1 sensor.csv").read_text() == "new_data"
    assert (target_csv / "99999-1 sensor_old.csv").read_text() == "old_data"


def test_migration_unresolvable(migration_tree):
    report = run_migration(migration_tree, apply=False)
    assert "random_data" in report
    assert "Could not derive" in report


def test_migration_idempotent(migration_tree):
    run_migration(migration_tree, apply=True)
    # Second run: no plans (only unresolvable remains, which is left untouched)
    plans, unresolvable = _collect_plans(migration_tree)
    assert plans == []


def test_migration_log_written(migration_tree):
    run_migration(migration_tree, apply=True)
    log_path = migration_tree / "migration_log.json"
    assert log_path.exists()
    log = json.loads(log_path.read_text())
    assert "entries" in log
    assert len(log["entries"]) > 0

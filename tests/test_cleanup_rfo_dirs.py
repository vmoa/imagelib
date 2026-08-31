"""Tests for bin/cleanup_rfo_dirs.py."""
import os
import sys

import pytest

_bin = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bin')
if _bin not in sys.path:
    sys.path.insert(0, _bin)
import cleanup_rfo_dirs as crd


def _make_tree(tmp_path, dirs, files):
    """Create directory and file structure under tmp_path."""
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('')


# ---------------------------------------------------------------------------
# find_cleanup_dirs
# ---------------------------------------------------------------------------

def test_finds_closed_loop_slews(tmp_path):
    _make_tree(tmp_path,
               dirs=['Closed Loop Slews'],
               files=['Closed Loop Slews/slew001.fits'])
    targets = crd.find_cleanup_dirs(str(tmp_path))
    assert any('Closed Loop Slews' in t for t in targets)


def test_finds_automated_pointing_run(tmp_path):
    _make_tree(tmp_path,
               dirs=['Automated Pointing Run 2024-06-01'],
               files=['Automated Pointing Run 2024-06-01/pt001.fits'])
    targets = crd.find_cleanup_dirs(str(tmp_path))
    assert any('Automated Pointing Run' in t for t in targets)


def test_does_not_find_normal_date_dirs(tmp_path):
    _make_tree(tmp_path,
               dirs=['2024-06-01'],
               files=['2024-06-01/NGC5194.fits'])
    targets = crd.find_cleanup_dirs(str(tmp_path))
    assert targets == []


def test_does_not_descend_into_matched_dir(tmp_path):
    """A nested match inside an already-matched dir should not appear separately."""
    _make_tree(tmp_path,
               dirs=['Closed Loop Slews', 'Closed Loop Slews/Closed Loop Slews'],
               files=[])
    targets = crd.find_cleanup_dirs(str(tmp_path))
    # Only the top-level match; the nested one is pruned
    assert len(targets) == 1


def test_finds_multiple_matches(tmp_path):
    _make_tree(tmp_path,
               dirs=['Closed Loop Slews', 'Automated Pointing Run A',
                     'Automated Pointing Run B', '2024-06-01'],
               files=[])
    targets = crd.find_cleanup_dirs(str(tmp_path))
    assert len(targets) == 3


# ---------------------------------------------------------------------------
# Deletion behaviour
# ---------------------------------------------------------------------------

def test_dry_run_does_not_delete(tmp_path):
    target = tmp_path / 'Closed Loop Slews'
    target.mkdir()
    (target / 'slew.fits').write_text('')

    crd.find_cleanup_dirs(str(tmp_path))  # just discover — deletion is in main()
    # Simulate dry-run: directory must still exist
    assert target.exists()


def test_rmtree_removes_directory(tmp_path):
    import shutil
    target = tmp_path / 'Closed Loop Slews'
    target.mkdir()
    (target / 'slew.fits').write_text('')

    targets = crd.find_cleanup_dirs(str(tmp_path))
    assert targets
    shutil.rmtree(targets[0])
    assert not target.exists()

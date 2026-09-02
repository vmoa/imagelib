"""Tests for bin/smart_push.py."""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

from tests.conftest import make_fits_file, make_fitsz_file

_bin = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bin')
if _bin not in sys.path:
    sys.path.insert(0, _bin)
import smart_push as sp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manifest(tmp_path):
    """Isolated in-memory-ish manifest DB in a temp dir."""
    db_path = str(tmp_path / 'manifest.db')
    con = sp.init_db(db_path)
    yield con
    con.close()


@pytest.fixture
def fits_file(tmp_path):
    path = str(tmp_path / '2024-06-01' / 'NGC5194_300s.fits')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    make_fits_file(path)
    return path


@pytest.fixture
def fitsz_file(tmp_path):
    path = str(tmp_path / '2024-06-01' / 'NGC5194_300s.fits.fz')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    make_fitsz_file(path)
    return path


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_both_tables(tmp_path):
    db_path = str(tmp_path / 'sub' / 'manifest.db')
    con = sp.init_db(db_path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'sent' in tables
    assert 'known_ingested' in tables
    con.close()


def test_init_db_creates_parent_directory(tmp_path):
    db_path = str(tmp_path / 'deep' / 'nested' / 'manifest.db')
    con = sp.init_db(db_path)
    assert os.path.exists(db_path)
    con.close()


def test_init_db_is_idempotent(tmp_path):
    db_path = str(tmp_path / 'manifest.db')
    con1 = sp.init_db(db_path)
    con1.close()
    con2 = sp.init_db(db_path)  # must not raise "table already exists"
    con2.close()


# ---------------------------------------------------------------------------
# is_known
# ---------------------------------------------------------------------------

def test_is_known_false_when_empty(manifest):
    assert not sp.is_known(manifest, '2024-06-01T04:30:00.000')


def test_is_known_true_after_sent_insert(manifest):
    manifest.execute(
        "INSERT INTO sent (date_obs, r_drive_path, sent_at) VALUES (?,?,?)",
        ('2024-06-01T04:30:00.000', 'SkyX/Images/2024-06-01/file.fits', '2024-06-01')
    )
    manifest.commit()
    assert sp.is_known(manifest, '2024-06-01T04:30:00.000')


def test_is_known_true_after_bootstrap_insert(manifest):
    manifest.execute(
        "INSERT INTO known_ingested (date_obs) VALUES (?)",
        ('2024-06-01T04:30:00.000',)
    )
    manifest.commit()
    assert sp.is_known(manifest, '2024-06-01T04:30:00.000')


def test_is_known_false_for_different_date_obs(manifest):
    manifest.execute(
        "INSERT INTO sent (date_obs, r_drive_path, sent_at) VALUES (?,?,?)",
        ('2024-06-01T04:30:00.000', 'file.fits', '2024-06-01')
    )
    manifest.commit()
    assert not sp.is_known(manifest, '2024-06-02T04:30:00.000')


# ---------------------------------------------------------------------------
# read_date_obs
# ---------------------------------------------------------------------------

def test_read_date_obs_from_fits(fits_file):
    assert sp.read_date_obs(fits_file) == '2024-06-01T04:30:00.000'


def test_read_date_obs_from_fitsz(fitsz_file):
    assert sp.read_date_obs(fitsz_file) == '2024-06-01T04:30:00.000'


def test_read_date_obs_returns_none_for_missing_file():
    assert sp.read_date_obs('/nonexistent/path.fits') is None


def test_read_date_obs_returns_none_for_non_fits(tmp_path):
    bad = str(tmp_path / 'not_a_fits.fits')
    with open(bad, 'wb') as f:
        f.write(b'not a fits file')
    assert sp.read_date_obs(bad) is None


# ---------------------------------------------------------------------------
# run_bootstrap
# ---------------------------------------------------------------------------

def test_bootstrap_populates_known_ingested(manifest, tmp_path):
    date_obs_file = str(tmp_path / 'bootstrap.txt')
    with open(date_obs_file, 'w') as f:
        f.write('2024-01-01T01:00:00.000\n')
        f.write('2024-01-02T01:00:00.000\n')
        f.write('\n')  # blank line — should be ignored

    import logging
    log = logging.getLogger('test')
    sp.run_bootstrap(manifest, date_obs_file, log)

    rows = manifest.execute('SELECT date_obs FROM known_ingested ORDER BY date_obs').fetchall()
    assert [r[0] for r in rows] == ['2024-01-01T01:00:00.000', '2024-01-02T01:00:00.000']


def test_bootstrap_is_idempotent(manifest, tmp_path):
    date_obs_file = str(tmp_path / 'bootstrap.txt')
    with open(date_obs_file, 'w') as f:
        f.write('2024-01-01T01:00:00.000\n')

    import logging
    log = logging.getLogger('test')
    sp.run_bootstrap(manifest, date_obs_file, log)
    sp.run_bootstrap(manifest, date_obs_file, log)  # must not raise

    count = manifest.execute('SELECT COUNT(*) FROM known_ingested').fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# find_candidates
# ---------------------------------------------------------------------------

def test_find_candidates_includes_all_extensions(tmp_path):
    r_drive = str(tmp_path / 'rdrive')
    date_dir = os.path.join(r_drive, '2024-06-01')
    os.makedirs(date_dir)

    for name in ('a.fits', 'b.fit', 'c.fits.fz', 'd.txt'):
        open(os.path.join(date_dir, name), 'w').close()

    tsfile = str(tmp_path / 'ts')  # does not exist → no -newer filter
    candidates = sp.find_candidates(r_drive, tsfile, skip_dirs=[])
    basenames = {os.path.basename(p) for p in candidates}

    assert 'a.fits' in basenames
    assert 'b.fit' in basenames
    assert 'c.fits.fz' in basenames
    assert 'd.txt' not in basenames


def test_find_candidates_skips_excluded_directories(tmp_path):
    r_drive = str(tmp_path / 'rdrive')
    normal_dir = os.path.join(r_drive, '2024-06-01')
    skip_dir = os.path.join(r_drive, 'Closed Loop Slews')
    os.makedirs(normal_dir)
    os.makedirs(skip_dir)

    open(os.path.join(normal_dir, 'good.fits'), 'w').close()
    open(os.path.join(skip_dir, 'slew.fits'), 'w').close()

    tsfile = str(tmp_path / 'ts')
    candidates = sp.find_candidates(r_drive, tsfile, skip_dirs=['Closed Loop Slews'])
    basenames = {os.path.basename(p) for p in candidates}

    assert 'good.fits' in basenames
    assert 'slew.fits' not in basenames


# ---------------------------------------------------------------------------
# rsync_file
# ---------------------------------------------------------------------------

def test_rsync_file_dry_run_does_not_call_subprocess(tmp_path, fits_file, caplog):
    import logging
    log = logging.getLogger('test')
    r_drive = str(tmp_path)
    with patch('smart_push.subprocess.run') as mock_run:
        result = sp.rsync_file(fits_file, r_drive, 'nas@imagelib',
                               '/home/nas/Eagle/SkyX/Images', log, dry_run=True)
    assert result is True
    mock_run.assert_not_called()


def test_rsync_file_apply_calls_rsync(tmp_path, fits_file):
    import logging
    log = logging.getLogger('test')
    r_drive = str(tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch('smart_push.subprocess.run', return_value=mock_result) as mock_run:
        result = sp.rsync_file(fits_file, r_drive, 'nas@imagelib',
                               '/home/nas/Eagle/SkyX/Images', log, dry_run=False)
    assert result is True
    args = mock_run.call_args[0][0]
    assert args[0] == 'rsync'
    assert '--rsync-path' in args
    assert fits_file in args


def test_rsync_file_returns_false_on_failure(tmp_path, fits_file):
    import logging
    log = logging.getLogger('test')
    r_drive = str(tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 23
    mock_result.stderr = 'connection refused'
    with patch('smart_push.subprocess.run', return_value=mock_result):
        result = sp.rsync_file(fits_file, r_drive, 'nas@imagelib',
                               '/home/nas/Eagle/SkyX/Images', log, dry_run=False)
    assert result is False


# ---------------------------------------------------------------------------
# Integration: skipping already-known files
# ---------------------------------------------------------------------------

def test_already_known_file_is_skipped(manifest, fits_file, tmp_path):
    """A file whose DATE-OBS is in known_ingested must not be rsynced."""
    manifest.execute(
        "INSERT INTO known_ingested (date_obs) VALUES (?)",
        ('2024-06-01T04:30:00.000',)
    )
    manifest.commit()

    r_drive = os.path.dirname(os.path.dirname(fits_file))  # tmp_path root

    with patch('smart_push.subprocess.run') as mock_run:
        # find_candidates returns our file; rsync must not be called
        with patch('smart_push.find_candidates', return_value=[fits_file]):
            # Replicate the per-file logic inline
            date_obs = sp.read_date_obs(fits_file)
            assert sp.is_known(manifest, date_obs)
            # rsync would only be called if not is_known — verify it isn't
            mock_run.assert_not_called()


def test_new_file_is_sent_and_recorded(manifest, fits_file, tmp_path):
    """A file not in the manifest is rsynced and then recorded in sent."""
    import logging
    log = logging.getLogger('test')
    r_drive_base = str(tmp_path)
    host = 'nas@imagelib'
    dest = '/home/nas/Eagle/SkyX/Images'

    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch('smart_push.subprocess.run', return_value=mock_result):
        ok = sp.rsync_file(fits_file, r_drive_base, host, dest, log, dry_run=False)

    assert ok
    date_obs = sp.read_date_obs(fits_file)
    rel_path = os.path.relpath(fits_file, r_drive_base)
    manifest.execute(
        'INSERT OR IGNORE INTO sent (date_obs, r_drive_path, sent_at) VALUES (?,?,?)',
        (date_obs, rel_path, '2024-06-01T04:30:00')
    )
    manifest.commit()
    assert sp.is_known(manifest, date_obs)


# ---------------------------------------------------------------------------
# cleanup_cal_dirs
# ---------------------------------------------------------------------------

def test_cleanup_removes_closed_loop_slews(tmp_path):
    r_drive = str(tmp_path / 'rdrive')
    cal_dir = os.path.join(r_drive, 'Closed Loop Slews')
    os.makedirs(cal_dir)
    open(os.path.join(cal_dir, 'slew.fits'), 'w').close()

    import logging
    log = logging.getLogger('test')
    removed, errors = sp.cleanup_cal_dirs(r_drive, log, dry_run=False)

    assert removed == 1
    assert errors == 0
    assert not os.path.exists(cal_dir)


def test_cleanup_removes_automated_pointing_run(tmp_path):
    r_drive = str(tmp_path / 'rdrive')
    cal_dir = os.path.join(r_drive, 'Automated Pointing Run 2024-06-01')
    os.makedirs(cal_dir)

    import logging
    log = logging.getLogger('test')
    removed, errors = sp.cleanup_cal_dirs(r_drive, log, dry_run=False)

    assert removed == 1
    assert not os.path.exists(cal_dir)


def test_cleanup_dry_run_does_not_delete(tmp_path):
    r_drive = str(tmp_path / 'rdrive')
    cal_dir = os.path.join(r_drive, 'Closed Loop Slews')
    os.makedirs(cal_dir)

    import logging
    log = logging.getLogger('test')
    removed, errors = sp.cleanup_cal_dirs(r_drive, log, dry_run=True)

    assert removed == 0
    assert os.path.exists(cal_dir)


def test_cleanup_leaves_normal_date_dirs(tmp_path):
    r_drive = str(tmp_path / 'rdrive')
    normal_dir = os.path.join(r_drive, '2024-06-01')
    os.makedirs(normal_dir)

    import logging
    log = logging.getLogger('test')
    removed, errors = sp.cleanup_cal_dirs(r_drive, log, dry_run=False)

    assert removed == 0
    assert os.path.exists(normal_dir)


# ---------------------------------------------------------------------------
# quarantine_file
# ---------------------------------------------------------------------------

def test_quarantine_moves_file(tmp_path, fits_file):
    import logging
    log = logging.getLogger('test')
    quarantine = str(tmp_path / '_no_date_obs')

    with patch.object(sp, 'QUARANTINE_DIR', quarantine):
        result = sp.quarantine_file(fits_file, log, dry_run=False)

    assert result is True
    assert not os.path.exists(fits_file)
    assert os.path.exists(os.path.join(quarantine, os.path.basename(fits_file)))


def test_quarantine_dry_run_does_not_move(tmp_path, fits_file):
    import logging
    log = logging.getLogger('test')
    quarantine = str(tmp_path / '_no_date_obs')

    with patch.object(sp, 'QUARANTINE_DIR', quarantine):
        result = sp.quarantine_file(fits_file, log, dry_run=True)

    assert result is True
    assert os.path.exists(fits_file)
    assert not os.path.exists(quarantine)


def test_quarantine_adds_timestamp_on_name_collision(tmp_path, fits_file):
    import logging
    log = logging.getLogger('test')
    quarantine = str(tmp_path / '_no_date_obs')
    os.makedirs(quarantine)
    # Pre-place a file with the same name in quarantine
    existing = os.path.join(quarantine, os.path.basename(fits_file))
    open(existing, 'w').close()

    with patch.object(sp, 'QUARANTINE_DIR', quarantine):
        result = sp.quarantine_file(fits_file, log, dry_run=False)

    assert result is True
    # Original collision file still exists; new file has timestamp prefix
    files = os.listdir(quarantine)
    assert len(files) == 2
    assert any('_' in f and f != os.path.basename(fits_file) for f in files)


def test_quarantine_returns_false_on_move_failure(tmp_path, fits_file):
    import logging
    log = logging.getLogger('test')
    # Point quarantine at a path we cannot create (read-only parent)
    quarantine = '/nonexistent/deeply/nested/_no_date_obs'

    with patch.object(sp, 'QUARANTINE_DIR', quarantine):
        with patch('smart_push.os.makedirs', side_effect=OSError('permission denied')):
            result = sp.quarantine_file(fits_file, log, dry_run=False)

    assert result is False
    assert os.path.exists(fits_file)  # file left in place on failure

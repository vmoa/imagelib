"""Tests for date_subpath (fitsfiles), compress_migrate, and nina_migrate (bin/)."""
import logging
import os
import sqlite3
import sys
from unittest.mock import patch

import numpy as np
import pytest
from astropy.io import fits

from tests.conftest import make_fits_file
from fitsfiles import date_subpath

# Import compress_migrate from bin/
_bin = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bin')
if _bin not in sys.path:
    sys.path.insert(0, _bin)
import compress_migrate as cm
import nina_migrate as nm

_log = logging.getLogger('test_migrate')


# ---------------------------------------------------------------------------
# date_subpath
# ---------------------------------------------------------------------------

def test_date_subpath_builds_correct_path(tmp_path):
    result = date_subpath('2021-01-15', str(tmp_path))
    assert result == str(tmp_path / '2021' / '01' / '15')


def test_date_subpath_creates_directory(tmp_path):
    date_subpath('2021-03-07', str(tmp_path))
    assert (tmp_path / '2021' / '03' / '07').is_dir()


# ---------------------------------------------------------------------------
# compress_to_temp
# ---------------------------------------------------------------------------

@pytest.fixture
def fits_path(tmp_path):
    p = str(tmp_path / 'light.fits')
    make_fits_file(p)
    return p


def test_compress_fits_produces_valid_fitsz(fits_path):
    with fits.open(fits_path, memmap=False, do_not_scale_image_data=True) as hdul:
        original_data = hdul[0].data.copy()

    tmp_fz = cm.compress_to_temp(fits_path)
    try:
        with fits.open(tmp_fz, memmap=False, do_not_scale_image_data=True) as verify:
            comp_hdu = next(h for h in verify if isinstance(h, fits.CompImageHDU))
            assert np.array_equal(original_data, comp_hdu.data)
    finally:
        if os.path.exists(tmp_fz):
            os.unlink(tmp_fz)


def test_compress_data_verification_rejects_mismatch(fits_path):
    with patch('compress_migrate.np.array_equal', return_value=False):
        with pytest.raises(RuntimeError, match='verification failed'):
            cm.compress_to_temp(fits_path)
    # Temp file must be cleaned up on error
    leftovers = [f for f in os.listdir(os.path.dirname(fits_path))
                 if f.endswith('.fits.fz')]
    assert not leftovers


# ---------------------------------------------------------------------------
# migrate_row helpers
# ---------------------------------------------------------------------------

def _make_test_db(tmp_path, src_path, preview=None, thumbnail=None):
    """Minimal sqlite3 DB with one fits row."""
    db_path = str(tmp_path / 'test.db')
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute('''
        CREATE TABLE fits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT, object TEXT, date TEXT, timestamp TEXT,
            filter TEXT, binning TEXT, exposure REAL,
            x INTEGER, y INTEGER,
            path TEXT, preview TEXT, thumbnail TEXT, imagetype TEXT,
            organization TEXT, project TEXT, observatory TEXT, observer TEXT
        )
    ''')
    con.execute(
        "INSERT INTO fits (target, object, date, timestamp, path, preview, thumbnail, imagetype)"
        " VALUES ('M 51','NGC 5194','2021-01-15','2021-01-15T04:00:00.000',?,?,?,'tgt')",
        (src_path, preview, thumbnail)
    )
    con.commit()
    return con


def _fetch_row(con, src_path):
    r = con.execute(
        "SELECT id, path, date, preview, thumbnail FROM fits WHERE path = ?", (src_path,)
    ).fetchone()
    return dict(r)


# ---------------------------------------------------------------------------
# migrate_row — dry-run
# ---------------------------------------------------------------------------

def test_dry_run_makes_no_disk_changes(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_test_db(tmp_path, src)
    dest_base = str(tmp_path / 'dest')

    result = cm.migrate_row(_fetch_row(con, src), dest_base, con, dry_run=True, log=_log)

    assert result == 'processed'
    assert os.path.exists(src)
    dest = tmp_path / 'dest'
    assert not any(dest.rglob('*.fits.fz')) if dest.exists() else True


def test_dry_run_makes_no_db_changes(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_test_db(tmp_path, src)

    cm.migrate_row(_fetch_row(con, src), str(tmp_path / 'dest'), con, dry_run=True, log=_log)

    db_path = con.execute("SELECT path FROM fits").fetchone()[0]
    assert db_path == src


# ---------------------------------------------------------------------------
# migrate_row — missing file
# ---------------------------------------------------------------------------

def test_skips_missing_file_without_crash(tmp_path):
    src = str(tmp_path / 'missing.fits')
    # intentionally not created
    con = _make_test_db(tmp_path, src)

    result = cm.migrate_row(_fetch_row(con, src), str(tmp_path / 'dest'), con,
                            dry_run=False, log=_log)
    assert result == 'skipped'


# ---------------------------------------------------------------------------
# migrate_row — apply: file moves, DB, deletion
# ---------------------------------------------------------------------------

def test_moves_preview_and_thumb_alongside_fitsz(tmp_path):
    src     = str(tmp_path / 'img.fits')
    preview = str(tmp_path / 'img.png')
    thumb   = str(tmp_path / 'img-thumb.png')
    make_fits_file(src)
    open(preview, 'wb').close()
    open(thumb,   'wb').close()

    con = _make_test_db(tmp_path, src, preview=preview, thumbnail=thumb)
    cm.migrate_row(_fetch_row(con, src), str(tmp_path / 'dest'), con,
                   dry_run=False, log=_log)

    dest_dir = tmp_path / 'dest' / '2021' / '01' / '15'
    assert (dest_dir / 'img.fits.fz').exists()
    assert (dest_dir / 'img.png').exists()
    assert (dest_dir / 'img-thumb.png').exists()


def test_original_deleted_after_apply(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_test_db(tmp_path, src)

    cm.migrate_row(_fetch_row(con, src), str(tmp_path / 'dest'), con,
                   dry_run=False, log=_log)

    assert not os.path.exists(src)


def test_db_path_updated_to_fitsz(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_test_db(tmp_path, src)
    row_id = _fetch_row(con, src)['id']

    cm.migrate_row(_fetch_row(con, src), str(tmp_path / 'dest'), con,
                   dry_run=False, log=_log)

    new_path = con.execute("SELECT path FROM fits WHERE id=?", (row_id,)).fetchone()[0]
    assert new_path.endswith('.fits.fz')
    assert os.path.exists(new_path)


def test_db_updated_before_original_deleted(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_test_db(tmp_path, src)
    row = _fetch_row(con, src)

    db_path_at_delete = []
    real_unlink = os.unlink

    def spy_unlink(path):
        r = con.execute("SELECT path FROM fits WHERE id=?", (row['id'],)).fetchone()
        db_path_at_delete.append(r[0])
        real_unlink(path)

    with patch('compress_migrate.os.unlink', side_effect=spy_unlink):
        cm.migrate_row(row, str(tmp_path / 'dest'), con, dry_run=False, log=_log)

    assert db_path_at_delete, 'os.unlink was never called'
    assert db_path_at_delete[0] != src, 'DB path should be updated before original is deleted'
    assert db_path_at_delete[0].endswith('.fits.fz')


# ---------------------------------------------------------------------------
# main() — maintenance flag guard
# ---------------------------------------------------------------------------

def test_refuses_apply_without_maintenance_flag(tmp_path, monkeypatch):
    flag = str(tmp_path / 'MAINTENANCE')  # does not exist
    monkeypatch.setenv('IMAGELIB_MAINTENANCE', flag)
    monkeypatch.setenv('FITSDB_FILE', str(tmp_path / 'dummy.db'))
    monkeypatch.setattr(sys, 'argv', ['compress_migrate', '--apply'])

    with pytest.raises(SystemExit) as exc:
        cm.main()
    assert exc.value.code != 0


def test_dry_run_does_not_require_maintenance_flag(tmp_path, monkeypatch):
    flag = str(tmp_path / 'MAINTENANCE')  # does not exist
    monkeypatch.setenv('IMAGELIB_MAINTENANCE', flag)

    # Create a minimal DB so main() has something to query
    db_path = str(tmp_path / 'test.db')
    con = sqlite3.connect(db_path)
    con.execute('''CREATE TABLE fits (id INTEGER PRIMARY KEY, target TEXT,
        object TEXT, date TEXT, timestamp TEXT, filter TEXT, binning TEXT,
        exposure REAL, x INTEGER, y INTEGER, path TEXT, preview TEXT,
        thumbnail TEXT, imagetype TEXT, organization TEXT, project TEXT,
        observatory TEXT, observer TEXT)''')
    con.commit()
    con.close()

    monkeypatch.setenv('FITSDB_FILE', db_path)
    monkeypatch.setattr(sys, 'argv', ['compress_migrate'])  # no --apply

    cm.main()  # must not raise


# ---------------------------------------------------------------------------
# main() — --year filter
# ---------------------------------------------------------------------------

def test_year_filter_restricts_candidate_rows(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test.db')
    con = sqlite3.connect(db_path)
    con.execute('''CREATE TABLE fits (id INTEGER PRIMARY KEY, target TEXT,
        object TEXT, date TEXT, timestamp TEXT, filter TEXT, binning TEXT,
        exposure REAL, x INTEGER, y INTEGER, path TEXT UNIQUE, preview TEXT,
        thumbnail TEXT, imagetype TEXT, organization TEXT, project TEXT,
        observatory TEXT, observer TEXT)''')
    for year in ('2021', '2022'):
        con.execute(
            "INSERT INTO fits (target, object, date, timestamp, path, imagetype)"
            " VALUES ('M 51','NGC 5194',?,?,'%s','tgt')" % f'/home/nas/Eagle/SkyX/img_{year}.fits',
            (f'{year}-01-15', f'{year}-01-15T04:00:00.000')
        )
    con.commit()
    con.close()

    monkeypatch.setenv('FITSDB_FILE', db_path)
    monkeypatch.setattr(sys, 'argv', ['compress_migrate', '--year', '2021'])

    processed_paths = []

    def fake_migrate(row, *a, **kw):
        processed_paths.append(row['path'])
        return 'skipped'  # don't actually touch disk

    with patch('compress_migrate.migrate_row', side_effect=fake_migrate):
        cm.main()

    assert all('2021' in p for p in processed_paths)
    assert not any('2022' in p for p in processed_paths)


# ===========================================================================
# 4e — nina_migrate
# ===========================================================================

_NINA_PREFIX = '/home/nas/Eagle/NINA/Astro-Images'


def _make_nina_db(tmp_path, src_path, preview=None, thumbnail=None):
    """Minimal DB with one NINA row (path under NINA/Astro-Images prefix)."""
    db_path = str(tmp_path / 'nina_test.db')
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute('''
        CREATE TABLE fits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT, object TEXT, date TEXT, timestamp TEXT,
            filter TEXT, binning TEXT, exposure REAL,
            x INTEGER, y INTEGER,
            path TEXT, preview TEXT, thumbnail TEXT, imagetype TEXT,
            organization TEXT, project TEXT, observatory TEXT, observer TEXT
        )
    ''')
    con.execute(
        "INSERT INTO fits (target, object, date, timestamp, path, preview, thumbnail, imagetype)"
        " VALUES ('M 42','NGC 1976','2025-12-18','2025-12-18T04:00:00.000',?,?,?,'tgt')",
        (src_path, preview, thumbnail)
    )
    con.commit()
    return con


def _nina_row(con, src_path):
    r = con.execute(
        "SELECT id, path, date, preview, thumbnail FROM fits WHERE path = ?", (src_path,)
    ).fetchone()
    return dict(r)


# ---------------------------------------------------------------------------
# move_row — dry-run
# ---------------------------------------------------------------------------

def test_nina_dry_run_makes_no_disk_changes(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_nina_db(tmp_path, src)
    dest_base = str(tmp_path / 'dest')

    result = nm.move_row(_nina_row(con, src), dest_base, con, dry_run=True, log=_log)

    assert result == 'processed'
    assert os.path.exists(src)
    assert not (tmp_path / 'dest').exists() or not any((tmp_path / 'dest').rglob('*.fits'))


def test_nina_dry_run_makes_no_db_changes(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_nina_db(tmp_path, src)

    nm.move_row(_nina_row(con, src), str(tmp_path / 'dest'), con, dry_run=True, log=_log)

    db_path = con.execute("SELECT path FROM fits").fetchone()[0]
    assert db_path == src


# ---------------------------------------------------------------------------
# move_row — missing file
# ---------------------------------------------------------------------------

def test_nina_skips_missing_file(tmp_path):
    src = str(tmp_path / 'missing.fits')
    con = _make_nina_db(tmp_path, src)

    result = nm.move_row(_nina_row(con, src), str(tmp_path / 'dest'), con,
                         dry_run=False, log=_log)
    assert result == 'skipped'


# ---------------------------------------------------------------------------
# move_row — apply: destination in SkyX/Images tree
# ---------------------------------------------------------------------------

def test_nina_files_move_to_skyx_images(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_nina_db(tmp_path, src)
    dest_base = str(tmp_path / 'SkyX' / 'Images')

    nm.move_row(_nina_row(con, src), dest_base, con, dry_run=False, log=_log)

    # File should be under SkyX/Images/YYYY/MM/DD/
    dest_dir = tmp_path / 'SkyX' / 'Images' / '2025' / '12' / '18'
    assert (dest_dir / 'img.fits').exists()
    assert not os.path.exists(src)


def test_nina_moves_preview_and_thumb(tmp_path):
    src     = str(tmp_path / 'img.fits')
    preview = str(tmp_path / 'img.png')
    thumb   = str(tmp_path / 'img-thumb.png')
    make_fits_file(src)
    open(preview, 'wb').close()
    open(thumb,   'wb').close()

    con = _make_nina_db(tmp_path, src, preview=preview, thumbnail=thumb)
    dest_base = str(tmp_path / 'dest')

    nm.move_row(_nina_row(con, src), dest_base, con, dry_run=False, log=_log)

    dest_dir = tmp_path / 'dest' / '2025' / '12' / '18'
    assert (dest_dir / 'img.fits').exists()
    assert (dest_dir / 'img.png').exists()
    assert (dest_dir / 'img-thumb.png').exists()
    assert not os.path.exists(preview)
    assert not os.path.exists(thumb)


def test_nina_db_updated_to_dest_path(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_nina_db(tmp_path, src)
    row_id = _nina_row(con, src)['id']
    dest_base = str(tmp_path / 'dest')

    nm.move_row(_nina_row(con, src), dest_base, con, dry_run=False, log=_log)

    new_path = con.execute("SELECT path FROM fits WHERE id=?", (row_id,)).fetchone()[0]
    assert 'NINA' not in new_path
    assert os.path.exists(new_path)


def test_nina_original_deleted_after_db_commit(tmp_path):
    src = str(tmp_path / 'img.fits')
    make_fits_file(src)
    con = _make_nina_db(tmp_path, src)

    nm.move_row(_nina_row(con, src), str(tmp_path / 'dest'), con,
                dry_run=False, log=_log)

    assert not os.path.exists(src)


# ---------------------------------------------------------------------------
# main() — maintenance flag and --pilot-date
# ---------------------------------------------------------------------------

def test_nina_refuses_apply_without_maintenance_flag(tmp_path, monkeypatch):
    flag = str(tmp_path / 'MAINTENANCE')
    monkeypatch.setenv('IMAGELIB_MAINTENANCE', flag)
    monkeypatch.setenv('FITSDB_FILE', str(tmp_path / 'dummy.db'))
    monkeypatch.setattr(sys, 'argv', ['nina_migrate', '--apply'])

    with pytest.raises(SystemExit) as exc:
        nm.main()
    assert exc.value.code != 0


def test_nina_pilot_date_filter(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test.db')
    con = sqlite3.connect(db_path)
    con.execute('''CREATE TABLE fits (id INTEGER PRIMARY KEY, target TEXT,
        object TEXT, date TEXT, timestamp TEXT, filter TEXT, binning TEXT,
        exposure REAL, x INTEGER, y INTEGER, path TEXT UNIQUE, preview TEXT,
        thumbnail TEXT, imagetype TEXT, organization TEXT, project TEXT,
        observatory TEXT, observer TEXT)''')
    for date in ('2025-12-18', '2025-12-19'):
        con.execute(
            "INSERT INTO fits (target, object, date, timestamp, path, imagetype)"
            " VALUES ('M 42','NGC 1976',?,?,?,'tgt')",
            (date, date + 'T04:00:00.000',
             '/home/nas/Eagle/NINA/Astro-Images/img_{}.fits'.format(date))
        )
    con.commit()
    con.close()

    monkeypatch.setenv('FITSDB_FILE', db_path)
    monkeypatch.setattr(sys, 'argv', ['nina_migrate', '--pilot-date', '2025-12-18'])

    processed_paths = []

    def fake_move(row, *a, **kw):
        processed_paths.append(row['date'])
        return 'skipped'

    with patch('nina_migrate.move_row', side_effect=fake_move):
        nm.main()

    assert processed_paths == ['2025-12-18']

"""
Shared pytest fixtures for imagelib tests.

Module-level code here runs before any test collection or imports,
which lets us patch Fitsdb.dbfile and set env vars before the Flask
app (and its module-level markup.Markup() call) is ever imported.
"""
import os
import sys
import tempfile

import numpy as np
import pytest
from astropy.io import fits

# ---------------------------------------------------------------------------
# Module-level bootstrap (runs before any test file is collected)
# ---------------------------------------------------------------------------

# 1. Secret key — must be set before __init__.py is imported.
os.environ.setdefault('IMAGELIB_SECRET_KEY', 'test-secret-key')

# 2. Ensure the repo root is on sys.path.
_repo_root = os.path.dirname(os.path.dirname(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# 3. Redirect Fitsdb to a session temp dir before any import can open the
#    real production DB.  This must happen before importing catalog or markup.
import fitsdb as _fitsdb

_session_dir = tempfile.mkdtemp(prefix='imagelib_test_')
_session_db_path = os.path.join(_session_dir, 'session.db')
_fitsdb.Fitsdb.dbfile = _session_db_path
_fitsdb.Fitsdb.tsfile = os.path.join(_session_dir, 'session.last_run')

# 4. Reset catalog's lazy class-level DB so it picks up the patched dbfile.
import catalog as _catalog
_catalog.Catalog.db = None

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _create_fits_schema(db):
    cur = db.con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS fits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT, object TEXT, date TEXT, timestamp TEXT,
            filter TEXT, binning TEXT, exposure REAL,
            x INTEGER, y INTEGER,
            path TEXT, preview TEXT, thumbnail TEXT, imagetype TEXT,
            organization TEXT, project TEXT, observatory TEXT, observer TEXT
        )
    ''')
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS fits_path_index ON fits (path)"
    )
    db.con.commit()


def _create_catalog_schema(db):
    cur = db.con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object TEXT, other TEXT, type TEXT, con TEXT
        )
    ''')
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS catalog_object_index ON catalog (object)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS catalog_by_target "
        "(target TEXT, id INTEGER, cname TEXT)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS catalog_by_target_idx "
        "ON catalog_by_target (target)"
    )
    db.con.commit()


def _insert_fits_record(db, **overrides):
    """Insert a test fits record; returns the row id."""
    rec = dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00.000', filter='Clear',
        binning='2x2', exposure=300.0, x=200, y=100,
        path='/nonexistent/img.fits',
        preview='/nonexistent/img.png',
        thumbnail='/nonexistent/img-thumb.png',
        imagetype='tgt',
    )
    rec.update(overrides)
    db.insert(rec)
    cur = db.con.cursor()
    return cur.execute(
        "SELECT id FROM fits WHERE path = ?", [rec['path']]
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# FITS file factories (used by multiple test modules)
# ---------------------------------------------------------------------------

def make_fits_file(path, object_name='M 51'):
    """Write a minimal standard .fits file."""
    data = np.zeros((100, 200), dtype=np.int16)
    hdu = fits.PrimaryHDU(data)
    hdu.header['OBJECT']   = object_name
    hdu.header['DATE-OBS'] = '2024-06-01T04:30:00.000'
    hdu.header['EXPTIME']  = 300.0
    hdu.header['IMAGETYP'] = 'Light Frame'
    hdu.header['XBINNING'] = 2
    hdu.header['YBINNING'] = 2
    hdu.header['FILTER']   = 'Clear'
    fits.HDUList([hdu]).writeto(path, overwrite=True)


def make_fitsz_file(path, object_name='M 51'):
    """Write a minimal Rice-compressed .fits.fz file."""
    data = np.zeros((100, 200), dtype=np.int32)
    primary    = fits.PrimaryHDU()
    compressed = fits.CompImageHDU(data, compression_type='RICE_1')
    compressed.header['OBJECT']   = object_name
    compressed.header['DATE-OBS'] = '2024-06-01T04:30:00.000'
    compressed.header['EXPTIME']  = 300.0
    compressed.header['IMAGETYP'] = 'Light Frame'
    compressed.header['XBINNING'] = 2
    compressed.header['YBINNING'] = 2
    compressed.header['FILTER']   = 'Clear'
    fits.HDUList([primary, compressed]).writeto(path, overwrite=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Isolated fitsdb instance on a per-test temp file, fits schema created."""
    db_path = str(tmp_path / 'test.db')
    monkeypatch.setattr(_fitsdb.Fitsdb, 'dbfile', db_path)
    db = _fitsdb.Fitsdb()
    _create_fits_schema(db)
    return db


@pytest.fixture
def fresh_catalog_db(tmp_path, monkeypatch):
    """Isolated fitsdb with both fits and catalog schemas; resets Catalog.db."""
    db_path = str(tmp_path / 'test.db')
    monkeypatch.setattr(_fitsdb.Fitsdb, 'dbfile', db_path)
    monkeypatch.setattr(_catalog.Catalog, 'db', None)
    db = _fitsdb.Fitsdb()
    _create_fits_schema(db)
    _create_catalog_schema(db)
    return db


@pytest.fixture(scope='session')
def _session_db():
    """Session-scoped DB used by the Flask integration tests."""
    db = _fitsdb.Fitsdb()
    _create_fits_schema(db)
    _create_catalog_schema(db)
    return db


@pytest.fixture(scope='session')
def app(_session_db):
    """Flask test app backed by the shared session DB."""
    import __init__ as _app_module
    _app_module.app.config['TESTING'] = True
    return _app_module.app


@pytest.fixture
def client(app):
    return app.test_client()

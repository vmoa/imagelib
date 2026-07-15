"""Unit tests for markup.py"""
import os
import zipfile
from unittest.mock import patch

import pytest

import markup as markup_module
from tests.conftest import make_fits_file, make_fitsz_file


@pytest.fixture
def m(fresh_db):
    """Markup instance connected to the per-test fresh_db."""
    instance = markup_module.Markup()
    instance.reset()
    return instance


# ---------------------------------------------------------------------------
# buildWhere_imgfilter
# ---------------------------------------------------------------------------

def test_imgfilter_cal(m):
    m.buildWhere_imgfilter('cal')
    assert m.get_where() == 'imagetype = ?'
    assert m.get_params() == ['cal']


def test_imgfilter_tgt(m):
    m.buildWhere_imgfilter('tgt')
    assert m.get_where() == 'imagetype = ?'
    assert m.get_params() == ['tgt']


def test_imgfilter_both_adds_nothing(m):
    m.buildWhere_imgfilter('both')
    assert m.get_where() == ''
    assert m.get_params() == []


# ---------------------------------------------------------------------------
# buildWhere_target — exact match, fuzzy match, and injection safety
# ---------------------------------------------------------------------------

def test_target_exact_match(m, fresh_db):
    fresh_db.insert(dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00', filter='Clear', binning='2x2',
        exposure=300.0, x=200, y=100, path='/t/a.fits',
        preview='/t/a.png', thumbnail='/t/a-thumb.png', imagetype='tgt',
    ))
    m.buildWhere_target('M 51')
    assert 'target = ?' in m.get_where()
    assert 'M 51' in m.get_params()


def test_target_fuzzy_match_uses_parameter(m):
    """SQL injection fix: fuzzy LIKE must use a bound parameter, not interpolation."""
    m.buildWhere_target("M'; DROP TABLE fits; --")
    where = m.get_where()
    params = m.get_params()
    assert 'like ?' in where.lower()
    # The dangerous string must appear only in params, never in the SQL clause
    assert "DROP TABLE" not in where
    assert any("DROP TABLE" in str(p) for p in params)


def test_target_fuzzy_like_value(m):
    """Fuzzy match must wrap the term in % wildcards via the parameter."""
    m.buildWhere_target('nebula')
    params = m.get_params()
    assert any('%nebula%' in str(p) for p in params)


def test_multiple_wheres_joined_with_and(m):
    m.buildWhere_imgfilter('tgt')
    m.add_where('date = ?', ['2024-06-01'])
    assert m.get_where() == 'imagetype = ? AND date = ?'
    assert m.get_params() == ['tgt', '2024-06-01']


# ---------------------------------------------------------------------------
# findStartDate
# ---------------------------------------------------------------------------

def test_find_start_date_exact(m):
    dates = ['2024-06-03', '2024-06-02', '2024-06-01']
    assert m.findStartDate(dates, '2024-06-02') == 1


def test_find_start_date_none_returns_zero(m):
    dates = ['2024-06-03', '2024-06-02', '2024-06-01']
    assert m.findStartDate(dates, None) == 0


def test_find_start_date_beyond_end_wraps_to_zero(m):
    dates = ['2024-06-03', '2024-06-02', '2024-06-01']
    assert m.findStartDate(dates, '2023-01-01') == 0


# ---------------------------------------------------------------------------
# zipit
# ---------------------------------------------------------------------------

def test_zipit_returns_valid_zip(fresh_db, tmp_path):
    """zipit() should produce a readable ZIP containing the requested file."""
    fits_file = str(tmp_path / 'target.fits')
    make_fits_file(fits_file)

    fresh_db.insert(dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00', filter='Clear', binning='2x2',
        exposure=300.0, x=200, y=100,
        path=fits_file, preview=fits_file.replace('.fits', '.png'),
        thumbnail=fits_file.replace('.fits', '-thumb.png'), imagetype='tgt',
    ))
    cur = fresh_db.con.cursor()
    recid = cur.execute("SELECT id FROM fits WHERE path = ?", [fits_file]).fetchone()[0]

    m = markup_module.Markup()
    zip_path = m.zipit(str(recid))

    assert os.path.exists(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert 'target.fits' in names


def test_zipit_filename_is_basename(fresh_db, tmp_path):
    """Files in the ZIP should use just the basename, not the full path."""
    fits_file = str(tmp_path / 'deep' / 'nested' / 'image.fits')
    os.makedirs(os.path.dirname(fits_file))
    make_fits_file(fits_file)

    fresh_db.insert(dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00', filter='Clear', binning='2x2',
        exposure=300.0, x=200, y=100,
        path=fits_file, preview='/t/p.png', thumbnail='/t/t.png',
        imagetype='tgt',
    ))
    cur = fresh_db.con.cursor()
    recid = cur.execute("SELECT id FROM fits WHERE path = ?", [fits_file]).fetchone()[0]

    m = markup_module.Markup()
    zip_path = m.zipit(str(recid))

    with zipfile.ZipFile(zip_path) as zf:
        assert 'image.fits' in zf.namelist()


def test_zipit_fitsz_served_as_fz(fresh_db, tmp_path):
    """fmt='fz' passes .fits.fz through to the ZIP unchanged."""
    fitsz_file = str(tmp_path / 'image.fits.fz')
    make_fitsz_file(fitsz_file)

    fresh_db.insert(dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00', filter='Clear', binning='2x2',
        exposure=300.0, x=200, y=100,
        path=fitsz_file, preview='/t/p.png', thumbnail='/t/t.png',
        imagetype='tgt',
    ))
    cur = fresh_db.con.cursor()
    recid = cur.execute("SELECT id FROM fits WHERE path = ?", [fitsz_file]).fetchone()[0]

    m = markup_module.Markup()
    zip_path = m.zipit(str(recid), fmt='fz')

    with zipfile.ZipFile(zip_path) as zf:
        assert 'image.fits.fz' in zf.namelist()


# ---------------------------------------------------------------------------
# buildWhere_orgproject / buildWhere_observatory / buildWhere_observer (3e)
# ---------------------------------------------------------------------------

def test_buildwhere_orgproject_valid(m):
    m.buildWhere_orgproject('AstOrg|Deep Sky Survey')
    assert 'organization = ?' in m.get_where()
    assert 'project = ?' in m.get_where()
    assert 'AstOrg' in m.get_params()
    assert 'Deep Sky Survey' in m.get_params()


def test_buildwhere_orgproject_empty_ignored(m):
    m.buildWhere_orgproject('')
    assert m.get_where() == ''
    assert m.get_params() == []


def test_buildwhere_observatory(m):
    m.buildWhere_observatory('RFO-RC20')
    assert 'observatory = ?' in m.get_where()
    assert 'RFO-RC20' in m.get_params()


def test_buildwhere_observer(m):
    m.buildWhere_observer('J. Smith')
    assert 'observer = ?' in m.get_where()
    assert 'J. Smith' in m.get_params()


def test_zipit_fitsz_decompressed_to_fits(fresh_db, tmp_path):
    """fmt='fits' decompresses .fits.fz in memory and writes .fits into the ZIP."""
    import io
    from astropy.io import fits as astrofits

    fitsz_file = str(tmp_path / 'image.fits.fz')
    make_fitsz_file(fitsz_file)

    fresh_db.insert(dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00', filter='Clear', binning='2x2',
        exposure=300.0, x=200, y=100,
        path=fitsz_file, preview='/t/p.png', thumbnail='/t/t.png',
        imagetype='tgt',
    ))
    cur = fresh_db.con.cursor()
    recid = cur.execute("SELECT id FROM fits WHERE path = ?", [fitsz_file]).fetchone()[0]

    m = markup_module.Markup()
    zip_path = m.zipit(str(recid), fmt='fits')

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert 'image.fits.fz' not in names
        assert 'image.fits' in names
        with astrofits.open(io.BytesIO(zf.read('image.fits'))) as hdul:
            assert len(hdul) > 0

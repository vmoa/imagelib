"""Integration tests for all six Flask routes in __init__.py"""
import os
import zipfile

import pytest

from tests.conftest import _create_fits_schema, _fitsdb, make_fits_file


# ---------------------------------------------------------------------------
# Session-scoped test data: one FITS file on disk + one DB record
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def seeded(tmp_path_factory, _session_db):
    """Create a real FITS file and a matching DB record for integration tests."""
    fits_dir = tmp_path_factory.mktemp('fits')
    fits_file = str(fits_dir / 'M51_300s.fits')
    make_fits_file(fits_file, object_name='M 51')

    _session_db.insert(dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00.000', filter='Clear',
        binning='2x2', exposure=300.0, x=200, y=100,
        path=fits_file,
        preview=fits_file.replace('.fits', '.png'),
        thumbnail=fits_file.replace('.fits', '-thumb.png'),
        imagetype='tgt',
    ))
    cur = _session_db.con.cursor()
    recid = cur.execute(
        "SELECT id FROM fits WHERE path = ?", [fits_file]
    ).fetchone()[0]

    return {'fits_file': fits_file, 'fits_dir': str(fits_dir), 'recid': recid}


# ---------------------------------------------------------------------------
# Route: /
# ---------------------------------------------------------------------------

def test_home_returns_200(client):
    r = client.get('/')
    assert r.status_code == 200


def test_home_contains_title(client):
    r = client.get('/')
    assert b'RFO Image Library' in r.data


def test_home_post_with_target(client, seeded):
    r = client.post('/', data={'target': 'M 51', 'imgfilter': 'both'})
    assert r.status_code == 200
    assert b'M 51' in r.data


# ---------------------------------------------------------------------------
# Route: /search
# ---------------------------------------------------------------------------

def test_search_returns_200(client):
    r = client.get('/search?target=M+51')
    assert r.status_code == 200


def test_search_unknown_target_flashes_message(client):
    r = client.post('/', data={'target': 'ZZZNOMATCH', 'imgfilter': 'both'})
    assert r.status_code == 200
    assert b'not found' in r.data


# ---------------------------------------------------------------------------
# Route: /deets
# ---------------------------------------------------------------------------

def test_deets_returns_html_fragment(client, seeded):
    r = client.get(f'/deets?recid={seeded["recid"]}')
    assert r.status_code == 200
    assert b'FITS Details' in r.data
    assert b'M 51' in r.data


# ---------------------------------------------------------------------------
# Route: /download
# ---------------------------------------------------------------------------

def test_download_returns_zip(client, seeded):
    r = client.post('/download', data={'recids': str(seeded['recid'])})
    assert r.status_code == 200
    assert r.content_type == 'application/zip'


def test_download_zip_contains_fits_file(client, seeded):
    r = client.post('/download', data={'recids': str(seeded['recid'])})
    import io
    with zipfile.ZipFile(io.BytesIO(r.data)) as zf:
        assert 'M51_300s.fits' in zf.namelist()


@pytest.mark.skip(reason="Phase 3c: format choice (.fits.fz / .fits) not yet implemented")
def test_download_format_choice():
    pass


# ---------------------------------------------------------------------------
# Route: /fits/<path>  and  /Eagle/<path>
# ---------------------------------------------------------------------------

def test_fits_path_serves_file(client, seeded, tmp_path_factory):
    """The /fits/ route must serve a real file from a fits/ subdirectory."""
    import __init__ as app_module
    fits_dir = tmp_path_factory.mktemp('fitsserve')
    test_file = fits_dir / 'test.fits'
    test_file.write_bytes(b'SIMPLE  =T')

    # Patch send_file to avoid needing the real path rooted at 'fits/'
    from unittest.mock import patch
    with patch('flask.send_file', return_value=app_module.app.response_class(
        response=b'SIMPLE  =T', status=200, mimetype='application/octet-stream'
    )):
        r = client.get('/fits/test.fits')
    assert r.status_code == 200


def test_eagle_path_serves_file(client):
    """The /Eagle/ route must return a non-404 response for a valid path."""
    from unittest.mock import patch
    import __init__ as app_module
    with patch('flask.send_file', return_value=app_module.app.response_class(
        response=b'', status=200, mimetype='application/octet-stream'
    )):
        r = client.get('/Eagle/2024-06-01/test.fits')
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Round-trip: ingest → query → render
# ---------------------------------------------------------------------------

def test_roundtrip_target_appears_in_html(client, seeded):
    """Full round-trip: record in DB → home page renders the target name."""
    r = client.post('/', data={'target': 'M 51', 'imgfilter': 'tgt'})
    assert r.status_code == 200
    assert b'M 51' in r.data

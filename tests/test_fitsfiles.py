"""Unit tests for fitsfiles.py"""
import os
from unittest.mock import patch

import pytest

import fitsfiles
from tests.conftest import make_fits_file, make_fitsz_file


@pytest.fixture
def ff():
    return fitsfiles.FitsFiles()


@pytest.fixture
def fits_path(tmp_path):
    p = str(tmp_path / 'light.fits')
    make_fits_file(p)
    return p


@pytest.fixture
def fitsz_path(tmp_path):
    p = str(tmp_path / 'light.fits.fz')
    make_fitsz_file(p)
    return p


# ---------------------------------------------------------------------------
# parseFitsHeader
# ---------------------------------------------------------------------------

def test_parse_header_standard_fits(ff, fits_path):
    headers = ff.parseFitsHeader(fits_path)
    assert headers is not None
    assert headers['OBJECT'] == 'M 51'
    assert headers['NAXIS1'] == 200
    assert headers['NAXIS2'] == 100
    assert headers['EXPTIME'] == 300.0
    assert headers['FILTER'] == 'Clear'


def test_parse_header_fitsz(ff, fitsz_path):
    """parseFitsHeader() must handle Rice-compressed .fits.fz without changes."""
    headers = ff.parseFitsHeader(fitsz_path)
    assert headers is not None
    assert headers['OBJECT'] == 'M 51'
    assert headers['NAXIS1'] == 200
    assert headers['NAXIS2'] == 100


def test_parse_header_missing_date_obs_returns_none(ff, tmp_path):
    from astropy.io import fits
    import numpy as np
    p = str(tmp_path / 'no_date.fits')
    hdu = fits.PrimaryHDU(np.zeros((10, 10), dtype=np.int16))
    hdu.header['OBJECT'] = 'Test'
    fits.HDUList([hdu]).writeto(p)
    assert ff.parseFitsHeader(p) is None


# ---------------------------------------------------------------------------
# buildDatabaseRecord
# ---------------------------------------------------------------------------

def test_build_record_target_image(ff, fits_path):
    headers = ff.parseFitsHeader(fits_path)
    with patch('catalog.Catalog.cname', return_value='M 51'):
        record = ff.buildDatabaseRecord(fits_path, headers)
    assert record['imagetype'] == 'tgt'
    assert record['target'] == 'M 51'
    assert record['date'] == '2024-06-01'
    assert record['binning'] == '2x2'
    assert record['x'] == 200
    assert record['y'] == 100


def test_build_record_calibration_dark(ff):
    headers = {
        'OBJECT': 'Dark', 'DATE-OBS': '2024-06-01T04:30:00.000',
        'EXPTIME': 120.0, 'IMAGETYP': 'Dark Frame',
        'XBINNING': 2, 'YBINNING': 2, 'FILTER': 'Clear',
        'NAXIS1': 200, 'NAXIS2': 100,
    }
    record = ff.buildDatabaseRecord('/tmp/dark.fits', headers)
    assert record['imagetype'] == 'cal'
    assert record['target'] == 'Dark Frame 120s'


def test_build_record_calibration_flat(ff):
    headers = {
        'OBJECT': 'Flat', 'DATE-OBS': '2024-06-01T04:30:00.000',
        'EXPTIME': 5.0, 'IMAGETYP': 'Flat Frame',
        'XBINNING': 1, 'YBINNING': 1, 'FILTER': 'Red',
        'NAXIS1': 4498, 'NAXIS2': 3598,
    }
    record = ff.buildDatabaseRecord('/tmp/flat.fits', headers)
    assert record['imagetype'] == 'cal'
    assert record['target'] == 'Flat Frame 5s'


# ---------------------------------------------------------------------------
# fits2png  (subprocess mocked so fitspng binary is not required)
# ---------------------------------------------------------------------------

def _fake_fitspng(cmd, **kwargs):
    """Side-effect for mocked subprocess.run: creates the expected output file."""
    if '-o' in cmd:
        out_path = cmd[cmd.index('-o') + 1]
        open(out_path, 'wb').close()


def test_fits2png_preview_and_thumb_created(ff, fits_path):
    expected_preview = fits_path.replace('.fits', '.png')
    expected_thumb   = fits_path.replace('.fits', '-thumb.png')

    with patch('subprocess.run', side_effect=_fake_fitspng):
        record = ff.fits2png({'path': fits_path, 'x': 200, 'y': 100})

    assert os.path.exists(expected_preview)
    assert os.path.exists(expected_thumb)
    assert record['preview'] == expected_preview
    assert record['thumbnail'] == expected_thumb


def test_fits2png_original_file_restored(ff, fits_path):
    """The temp-rename workaround must always restore the original filename."""
    with patch('subprocess.run', side_effect=_fake_fitspng):
        ff.fits2png({'path': fits_path, 'x': 200, 'y': 100})

    assert os.path.exists(fits_path)


def test_fits2png_skips_existing_preview(ff, fits_path):
    """When preview already exists and forcepng is False, fitspng is not called."""
    preview = fits_path.replace('.fits', '.png')
    thumb   = fits_path.replace('.fits', '-thumb.png')
    open(preview, 'wb').close()
    open(thumb,   'wb').close()

    with patch('subprocess.run') as mock_run:
        ff.fits2png({'path': fits_path, 'x': 200, 'y': 100})

    mock_run.assert_not_called()


def test_fits2png_fitsz_preview_and_thumb_created(ff, fitsz_path):
    """.fits.fz: preview and thumb paths must strip the full 8-char extension."""
    expected_preview = fitsz_path[:-8] + '.png'
    expected_thumb   = fitsz_path[:-8] + '-thumb.png'

    with patch('subprocess.run', side_effect=_fake_fitspng):
        record = ff.fits2png({'path': fitsz_path, 'x': 200, 'y': 100})

    assert os.path.exists(expected_preview)
    assert os.path.exists(expected_thumb)
    assert record['preview'] == expected_preview
    assert record['thumbnail'] == expected_thumb


def test_fits2png_fitsz_original_file_restored(ff, fitsz_path):
    """.fits.fz: the temp-rename workaround must restore the original filename."""
    with patch('subprocess.run', side_effect=_fake_fitspng):
        ff.fits2png({'path': fitsz_path, 'x': 200, 'y': 100})

    assert os.path.exists(fitsz_path)

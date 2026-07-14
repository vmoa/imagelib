#!/usr/bin/env python3
"""
verify_fitspng_fz.py -- Verify fitspng compatibility with fits.fz (Rice-compressed FITS).

Answers the open question in doc/plan.md section 3b:
  - Does parseFitsHeader() correctly find the image HDU in a fits.fz file?
  - Does fitspng accept a .fits.fz file directly?
  - Does fitspng accept a .fits.fz file renamed to .fits (the existing temp-rename workaround)?
  - Does astropy decompress to plain .fits before fitspng work as a fallback?
  - Is the fits_path_abs[:-5] extension stripping in fits2png() safe for .fits.fz paths?

Run from the imagelib directory with the virtualenv active:
    python3 verify_fitspng_fz.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from astropy.io import fits

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_results = []


def report(label, status, detail=""):
    _results.append((label, status, detail))
    marker = "+" if status == PASS else ("-" if status == SKIP else "!")
    suffix = f": {detail}" if detail else ""
    print(f"  [{marker}] {label}{suffix}")


# ---------------------------------------------------------------------------
# Synthetic fits.fz creation
# ---------------------------------------------------------------------------

def create_test_fitsz(path):
    """Write a minimal Rice-compressed FITS file with all headers parseFitsHeader() needs."""
    data = np.zeros((200, 250), dtype=np.int32)
    data[50:150, 60:190] = 32768

    primary = fits.PrimaryHDU()
    compressed = fits.CompImageHDU(data, compression_type='RICE_1')
    compressed.header['OBJECT']   = 'Test Galaxy'
    compressed.header['DATE-OBS'] = '2024-06-01T04:30:00.000'
    compressed.header['EXPTIME']  = 300.0
    compressed.header['IMAGETYP'] = 'Light Frame'
    compressed.header['XBINNING'] = 2
    compressed.header['YBINNING'] = 2
    compressed.header['FILTER']   = 'Clear'
    compressed.header['OBJCTRA']  = '12 30 00'
    compressed.header['OBJCTDEC'] = '+41 00 00'

    fits.HDUList([primary, compressed]).writeto(path, overwrite=True)


# ---------------------------------------------------------------------------
# Test 1: parseFitsHeader() HDU discovery and header extraction
# ---------------------------------------------------------------------------

def test_parse_header(fitsz_path):
    print("\nTest 1: parseFitsHeader() on .fits.fz")

    # Exercise the exact same logic as fitsfiles.FitsFiles.parseFitsHeader()
    with fits.open(fitsz_path) as fitsfile:
        found_hdu = None
        for hdu in fitsfile:
            if hdu.header['NAXIS'] == 2:
                found_hdu = hdu
                break

    if found_hdu is None:
        report("HDU with NAXIS==2 found", FAIL, "no HDU matched")
        return

    hdu_type = type(found_hdu).__name__
    report("HDU with NAXIS==2 found", PASS, f"type={hdu_type}")

    expected = {
        'NAXIS1': 250,
        'NAXIS2': 200,
        'OBJECT': 'Test Galaxy',
        'DATE-OBS': '2024-06-01T04:30:00.000',
        'EXPTIME': 300.0,
        'IMAGETYP': 'Light Frame',
        'XBINNING': 2,
        'YBINNING': 2,
        'FILTER': 'Clear',
    }
    for key, expected_val in expected.items():
        if key in found_hdu.header:
            actual = found_hdu.header[key]
            if actual == expected_val:
                report(f"  header[{key}]", PASS, repr(actual))
            else:
                report(f"  header[{key}]", FAIL, f"got {actual!r}, expected {expected_val!r}")
        else:
            report(f"  header[{key}] present", FAIL, "key missing from header")


# ---------------------------------------------------------------------------
# Test 2: fitspng directly on .fits.fz
# ---------------------------------------------------------------------------

def test_fitspng_direct(fitsz_path, tmpdir):
    print("\nTest 2: fitspng called directly on .fits.fz")
    out_png = os.path.join(tmpdir, "direct.png")
    cmd = ['fitspng', '-o', out_png, fitsz_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(out_png) and os.path.getsize(out_png) > 0:
            report("fitspng direct on .fits.fz", PASS, f"{os.path.getsize(out_png)} bytes")
        else:
            report("fitspng direct on .fits.fz", FAIL,
                   f"rc={r.returncode} stderr={r.stderr.strip()!r}")
    except FileNotFoundError:
        report("fitspng direct on .fits.fz", SKIP, "fitspng not found in PATH")


# ---------------------------------------------------------------------------
# Test 3: fitspng via temp rename workaround (copy .fits.fz -> temp_safe_image.fits)
#         This mirrors what fits2png() does today.
# ---------------------------------------------------------------------------

def test_fitspng_rename_workaround(fitsz_path, tmpdir):
    print("\nTest 3: fitspng via rename workaround (.fits.fz copied to temp_safe_image.fits)")
    work_dir = tmpdir
    temp_fits = os.path.join(work_dir, "temp_safe_image.fits")
    temp_png  = os.path.join(work_dir, "temp_safe_image.png")
    out_png   = os.path.join(tmpdir, "rename_workaround.png")

    shutil.copy2(fitsz_path, temp_fits)
    cmd = ['fitspng', '-o', temp_png, temp_fits]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(temp_png) and os.path.getsize(temp_png) > 0:
            shutil.move(temp_png, out_png)
            report("fitspng on compressed data renamed to .fits", PASS,
                   f"{os.path.getsize(out_png)} bytes")
        else:
            report("fitspng on compressed data renamed to .fits", FAIL,
                   f"rc={r.returncode} stderr={r.stderr.strip()!r}")
    except FileNotFoundError:
        report("fitspng on compressed data renamed to .fits", SKIP, "fitspng not found in PATH")
    finally:
        for f in (temp_fits, temp_png):
            if os.path.exists(f):
                os.unlink(f)


# ---------------------------------------------------------------------------
# Test 4: astropy decompress to plain .fits, then fitspng (fallback approach)
# ---------------------------------------------------------------------------

def test_fitspng_after_decompress(fitsz_path, tmpdir):
    print("\nTest 4: astropy decompress to plain .fits, then fitspng")
    plain_fits = os.path.join(tmpdir, "decompressed.fits")
    out_png    = os.path.join(tmpdir, "decompress_then_fitspng.png")

    try:
        with fits.open(fitsz_path) as hdus:
            new_primary = fits.PrimaryHDU()
            image_hdus = []
            for hdu in hdus:
                if isinstance(hdu, fits.CompImageHDU):
                    image_hdus.append(fits.ImageHDU(data=hdu.data, header=hdu.header.copy()))
            fits.HDUList([new_primary] + image_hdus).writeto(plain_fits, overwrite=True)
        report("astropy decompress to plain .fits", PASS,
               f"{os.path.getsize(plain_fits)} bytes")
    except Exception as e:
        report("astropy decompress to plain .fits", FAIL, str(e))
        return

    cmd = ['fitspng', '-o', out_png, plain_fits]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(out_png) and os.path.getsize(out_png) > 0:
            report("fitspng on decompressed .fits", PASS, f"{os.path.getsize(out_png)} bytes")
        else:
            report("fitspng on decompressed .fits", FAIL,
                   f"rc={r.returncode} stderr={r.stderr.strip()!r}")
    except FileNotFoundError:
        report("fitspng on decompressed .fits", SKIP, "fitspng not found in PATH")


# ---------------------------------------------------------------------------
# Test 5: Extension stripping safety check
#         fits_path_abs[:-5] is the current code; show what it produces for .fits.fz
# ---------------------------------------------------------------------------

def test_extension_stripping():
    print("\nTest 5: Extension stripping for .fits.fz paths")

    cases = [
        "image.fits",
        "image.fit",
        "image.fits.fz",
        "/home/nas/Eagle/2024-06-01/NGC1234_300s.fits.fz",
    ]

    for path in cases:
        sliced     = path[:-5]
        stem, _ext = os.path.splitext(path)
        # For .fits.fz, splitext gives stem=image.fits; strip again for the base name
        if path.endswith('.fits.fz'):
            base = os.path.splitext(stem)[0]
        else:
            base = stem

        if path.endswith('.fits.fz'):
            ok = sliced != base  # sliced will be wrong
            report(f"  [:-5] on '{os.path.basename(path)}'", FAIL if ok else PASS,
                   f"[:-5] gives '{os.path.basename(sliced)}.png'  "
                   f"correct base is '{os.path.basename(base)}.png'")
        else:
            ok = sliced == base
            report(f"  [:-5] on '{os.path.basename(path)}'", PASS if ok else FAIL,
                   f"gives '{os.path.basename(sliced)}.png' (correct)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("fitspng + fits.fz compatibility verification")
    print("=" * 60)

    with tempfile.TemporaryDirectory(prefix="imglib_fz_verify_") as tmpdir:

        fitsz_path = os.path.join(tmpdir, "test_image.fits.fz")
        print(f"\nCreating synthetic fits.fz at {fitsz_path}")
        try:
            create_test_fitsz(fitsz_path)
            print("  Created OK")
        except Exception as e:
            print(f"  FATAL: could not create test file: {e}")
            sys.exit(1)

        test_parse_header(fitsz_path)
        test_fitspng_direct(fitsz_path, tmpdir)
        test_fitspng_rename_workaround(fitsz_path, tmpdir)
        test_fitspng_after_decompress(fitsz_path, tmpdir)

    test_extension_stripping()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    passes = sum(1 for _, s, _ in _results if s == PASS)
    fails  = sum(1 for _, s, _ in _results if s == FAIL)
    skips  = sum(1 for _, s, _ in _results if s == SKIP)
    for label, status, detail in _results:
        marker = "+" if status == PASS else ("-" if status == SKIP else "!")
        suffix = f": {detail}" if detail else ""
        print(f"  [{marker}] {label}{suffix}")
    print(f"\n  {passes} passed  {fails} failed  {skips} skipped")

    if skips > 0:
        print("\n  Note: SKIP means fitspng is not in PATH on this machine.")
        print("  Re-run on a machine with fitspng installed to get full results.")

    sys.exit(0 if fails == 0 else 1)


if __name__ == '__main__':
    main()

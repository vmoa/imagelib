#!/usr/bin/env python3
"""
RICE-compress SkyX .fits/.fit files and reorganize into YYYY/MM/DD subfolders.

Driven by DB rows (not a filesystem walk) so every file touched has a
corresponding DB record. Defaults to --dry-run; pass --apply to commit changes.
Requires the maintenance flag file to be present before --apply will run.

Usage:
  sudo -u nas python3 bin/compress_migrate.py [--year YYYY] [--apply]
"""

import argparse
import datetime
import logging
import os
import shutil
import sqlite3
import sys
import tempfile

import numpy as np
from astropy.io import fits

# Allow import when run from repo root or from bin/
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from fitsfiles import date_subpath

PROD_DB   = '/home/nas/data/fits.db'
DEST_BASE = '/home/nas/Eagle/SkyX/Images'
DEFAULT_MAINTENANCE_FLAG = '/home/nas/data/MAINTENANCE'

_SOURCE_SQL = """
    SELECT id, path, date, preview, thumbnail
    FROM fits
    WHERE (path LIKE '/home/nas/Eagle/SkyX/%.fits'
           OR  path LIKE '/home/nas/Eagle/SkyX/%.fit')
"""


def compress_to_temp(src_path):
    """RICE-compress src_path into a temp .fits.fz in the same directory.

    Verifies pixel data round-trips exactly via np.array_equal before returning.
    Cleans up the temp file on any error. Raises on verification failure.
    Returns the temp file path on success.
    """
    src_dir = os.path.dirname(src_path)

    with fits.open(src_path, memmap=False, do_not_scale_image_data=True) as hdul:
        img_hdu = next((h for h in hdul if h.header.get('NAXIS', 0) == 2), None)
        if img_hdu is None:
            raise ValueError('No 2D image HDU in {}'.format(src_path))
        original_data = img_hdu.data.copy()
        img_header = img_hdu.header.copy()

    fd, tmp_path = tempfile.mkstemp(suffix='.fits.fz', dir=src_dir)
    os.close(fd)
    try:
        comp = fits.CompImageHDU(data=original_data, header=img_header,
                                 compression_type='RICE_1')
        fits.HDUList([fits.PrimaryHDU(), comp]).writeto(
            tmp_path, output_verify='silentfix', overwrite=True
        )
        with fits.open(tmp_path, memmap=False, do_not_scale_image_data=True) as verify:
            comp_hdu = next((h for h in verify if isinstance(h, fits.CompImageHDU)), None)
            if comp_hdu is None:
                raise RuntimeError('No CompImageHDU in compressed output for {}'.format(src_path))
            if not np.array_equal(original_data, comp_hdu.data):
                raise RuntimeError('Data verification failed: pixel mismatch in {}'.format(src_path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return tmp_path


def migrate_row(row, dest_base, con, dry_run, log):
    """Process one DB row: compress, move, update DB, delete original.

    row: dict with keys id, path, date, preview, thumbnail
    Returns: 'processed', 'skipped', or 'error'
    """
    src_path  = row['path']
    date_str  = row['date']
    preview   = row['preview']
    thumbnail = row['thumbnail']
    row_id    = row['id']

    if not os.path.exists(src_path):
        log.warning('SKIP (missing on disk): %s', src_path)
        return 'skipped'

    if src_path.endswith('.fits'):
        stem = os.path.basename(src_path)[:-5]
    else:  # .fit
        stem = os.path.basename(src_path)[:-4]

    dest_dir   = date_subpath(date_str, dest_base)
    dest_fz    = os.path.join(dest_dir, stem + '.fits.fz')
    dest_png   = os.path.join(dest_dir, stem + '.png')
    dest_thumb = os.path.join(dest_dir, stem + '-thumb.png')

    log.info('%sid=%s  %s\n%s→ %s',
             '[DRY-RUN] ' if dry_run else '',
             row_id, src_path, ' ' * 11, dest_fz)

    if dry_run:
        return 'processed'

    tmp_fz = None
    try:
        tmp_fz = compress_to_temp(src_path)

        shutil.move(tmp_fz, dest_fz)
        tmp_fz = None  # ownership transferred to dest_fz

        if preview and os.path.exists(preview):
            shutil.move(preview, dest_png)
        if thumbnail and os.path.exists(thumbnail):
            shutil.move(thumbnail, dest_thumb)

        con.execute(
            'UPDATE fits SET path=?, preview=?, thumbnail=? WHERE id=?',
            (dest_fz, dest_png, dest_thumb, row_id)
        )
        con.commit()

        os.unlink(src_path)
        log.info('  deleted original: %s', src_path)

        return 'processed'

    except Exception as exc:
        log.error('ERROR id=%s  %s: %s', row_id, src_path, exc)
        if tmp_fz and os.path.exists(tmp_fz):
            os.unlink(tmp_fz)
        return 'error'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--year', metavar='YYYY',
                   help='restrict to rows where date starts with YYYY (e.g. 2021 for pilot)')
    p.add_argument('--apply', action='store_true',
                   help='apply changes to disk and DB (default is dry-run, no changes made)')
    args = p.parse_args()
    dry_run = not args.apply

    maintenance_flag = os.environ.get('IMAGELIB_MAINTENANCE', DEFAULT_MAINTENANCE_FLAG)
    if args.apply and not os.path.exists(maintenance_flag):
        sys.exit('ERROR: maintenance flag file not found: {}\n'
                 'Create it before running --apply.'.format(maintenance_flag))

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = '/tmp/compress_migrate_{}.log'.format(ts)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout),
        ]
    )
    log = logging.getLogger(__name__)
    log.info('compress_migrate start  dry_run=%s  year=%s', dry_run, args.year)
    if not dry_run:
        log.info('Log: %s', log_path)

    db_path = os.environ.get('FITSDB_FILE', PROD_DB)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    sql = _SOURCE_SQL
    params = []
    if args.year:
        sql += " AND date LIKE ?"
        params.append(args.year + '-%')
    sql += " ORDER BY date, path"

    rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    log.info('Candidate rows: %d', len(rows))

    counts = {'processed': 0, 'skipped': 0, 'error': 0}
    for row in rows:
        status = migrate_row(row, DEST_BASE, con, dry_run, log)
        counts[status] += 1

    log.info('Done.  processed=%d  skipped=%d  error=%d',
             counts['processed'], counts['skipped'], counts['error'])
    con.close()
    if counts['error']:
        sys.exit(1)


if __name__ == '__main__':
    main()

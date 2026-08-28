#!/usr/bin/env python3
"""
Move NINA/Astro-Images .fits files (and their PNG previews) into the
SkyX/Images/YYYY/MM/DD folder tree, then update the DB paths.

No compression is performed here — NINA files are moved as-is; a subsequent
compress_migrate run on SkyX will pick them up and compress them.

Usage:
  sudo -u nas python3 bin/nina_migrate.py [--pilot-date YYYY-MM-DD] [--apply]

Defaults to --dry-run. Requires the maintenance flag file before --apply.
"""

import argparse
import datetime
import logging
import os
import shutil
import sqlite3
import sys

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
    WHERE path LIKE '/home/nas/Eagle/NINA/Astro-Images/%'
"""


def move_row(row, dest_base, con, dry_run, log):
    """Move one DB row's files from NINA/Astro-Images to SkyX/Images/YYYY/MM/DD/.

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

    basename = os.path.basename(src_path)
    if src_path.endswith('.fits'):
        stem = basename[:-5]
    elif src_path.endswith('.fit'):
        stem = basename[:-4]
    else:
        stem = basename

    dest_dir   = date_subpath(date_str, dest_base)
    dest_fits  = os.path.join(dest_dir, basename)
    dest_png   = os.path.join(dest_dir, stem + '.png')
    dest_thumb = os.path.join(dest_dir, stem + '-thumb.png')

    log.info('%sid=%s  %s\n%s→ %s',
             '[DRY-RUN] ' if dry_run else '',
             row_id, src_path, ' ' * 11, dest_fits)

    if dry_run:
        return 'processed'

    try:
        # Copy files to destination (copy before DB update for safe recovery)
        shutil.copy2(src_path, dest_fits)
        if preview and os.path.exists(preview):
            shutil.copy2(preview, dest_png)
        if thumbnail and os.path.exists(thumbnail):
            shutil.copy2(thumbnail, dest_thumb)

        # Update DB to point at new locations, then commit
        con.execute(
            'UPDATE fits SET path=?, preview=?, thumbnail=? WHERE id=?',
            (dest_fits, dest_png, dest_thumb, row_id)
        )
        con.commit()

        # Delete originals only after DB is committed
        os.unlink(src_path)
        if preview and os.path.exists(preview):
            os.unlink(preview)
        if thumbnail and os.path.exists(thumbnail):
            os.unlink(thumbnail)

        log.info('  deleted originals for id=%s', row_id)
        return 'processed'

    except Exception as exc:
        log.error('ERROR id=%s  %s: %s', row_id, src_path, exc)
        return 'error'


def main():
    os.umask(0o022)  # ensure created files are group/world-readable (rw-r--r--)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot-date', metavar='YYYY-MM-DD',
                   help='restrict to rows where date = YYYY-MM-DD (single-date trial run)')
    p.add_argument('--apply', action='store_true',
                   help='apply changes to disk and DB (default is dry-run, no changes made)')
    args = p.parse_args()
    dry_run = not args.apply

    maintenance_flag = os.environ.get('IMAGELIB_MAINTENANCE', DEFAULT_MAINTENANCE_FLAG)
    if args.apply and not os.path.exists(maintenance_flag):
        sys.exit('ERROR: maintenance flag file not found: {}\n'
                 'Create it before running --apply.'.format(maintenance_flag))

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = '/tmp/nina_migrate_{}.log'.format(ts)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout),
        ]
    )
    log = logging.getLogger(__name__)
    log.info('nina_migrate start  dry_run=%s  pilot_date=%s', dry_run, args.pilot_date)
    if not dry_run:
        log.info('Log: %s', log_path)

    db_path = os.environ.get('FITSDB_FILE', PROD_DB)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    sql = _SOURCE_SQL
    params = []
    if args.pilot_date:
        sql += " AND date = ?"
        params.append(args.pilot_date)
    sql += " ORDER BY date, path"

    rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    log.info('Candidate rows: %d', len(rows))

    counts = {'processed': 0, 'skipped': 0, 'error': 0}
    for row in rows:
        status = move_row(row, DEST_BASE, con, dry_run, log)
        counts[status] += 1

    log.info('Done.  processed=%d  skipped=%d  error=%d',
             counts['processed'], counts['skipped'], counts['error'])
    con.close()
    if counts['error']:
        sys.exit(1)


if __name__ == '__main__':
    main()

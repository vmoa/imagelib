#!/usr/bin/env python3
"""
Remove duplicate .fits rows (and their sidecar PNGs) that were inserted by
fitsfiles.py for orphan files that had already been compressed by compress_migrate.

These rows exist because compress_migrate compressed the file, updated the DB path
to .fits.fz, then failed to unlink the original .fits.  fitsfiles.py later
re-ingested those originals, creating a second DB row per image.

Targets rows with paths matching: SkyX/Images/YYYY-MM-DD/file.fits

Usage:
  sudo -u nas python3 bin/cleanup_orphan_fits.py [--year YYYY] [--apply]

Defaults to --dry-run.
"""

import argparse
import os
import sqlite3
import sys

PROD_DB = '/home/nas/data/fits.db'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--year', metavar='YYYY',
                   help='restrict to rows where the date folder starts with YYYY')
    p.add_argument('--apply', action='store_true',
                   help='delete files and DB rows (default is dry-run)')
    args = p.parse_args()
    dry_run = not args.apply

    if args.year and (len(args.year) != 4 or not args.year.isdigit()):
        sys.exit('ERROR: --year must be a 4-digit year')

    db_path = os.environ.get('FITSDB_FILE', PROD_DB)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # GLOB matches SkyX/Images/YYYY-MM-DD/file.fits (date-directory style, not YYYY/MM/DD)
    glob = '/home/nas/Eagle/SkyX/Images/????-*/*.fits'
    if args.year:
        glob = '/home/nas/Eagle/SkyX/Images/{}-*/*.fits'.format(args.year)

    rows = [dict(r) for r in con.execute(
        "SELECT id, path, preview, thumbnail FROM fits WHERE path GLOB ?", (glob,)
    ).fetchall()]

    print('{} duplicate .fits rows found{}'.format(
        len(rows), ' (dry-run, pass --apply to delete)' if dry_run else ''))

    deleted_files = 0
    deleted_rows = 0
    errors = 0

    for row in rows:
        row_id  = row['id']
        path    = row['path']
        preview = row['preview']
        thumb   = row['thumbnail']

        print('  id={:6d}  {}'.format(row_id, path))

        if dry_run:
            continue

        try:
            for f in (path, preview, thumb):
                if f and os.path.exists(f):
                    os.unlink(f)
                    deleted_files += 1

            con.execute('DELETE FROM fits WHERE id = ?', (row_id,))
            con.commit()
            deleted_rows += 1
        except Exception as exc:
            print('    ERROR id={}: {}'.format(row_id, exc))
            errors += 1

    if not dry_run:
        print('Deleted {} files, {} DB rows, {} errors'.format(
            deleted_files, deleted_rows, errors))
    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Remove duplicate .fits rows (and their sidecar PNGs) that were inserted by
fitsfiles.py for orphan files that had already been compressed by compress_migrate.

A row is a duplicate only if a corresponding .fits.fz row already exists in the
DB at the new YYYY/MM/DD path.  Legitimate un-migrated rows (no .fits.fz
counterpart in DB) are left untouched.

Usage:
  sudo -u nas python3 bin/cleanup_orphan_fits.py [--year YYYY] [--apply]

Defaults to --dry-run.
"""

import argparse
import os
import re
import sqlite3
import sys

PROD_DB   = '/home/nas/data/fits.db'
SKYX_BASE = '/home/nas/Eagle/SkyX/Images'

# Matches SkyX/Images/YYYY-MM-DD/stem.fits  (date-directory style)
_DATE_DIR_RE = re.compile(
    r'^(.+/SkyX/Images/)(\d{4})-(\d{2})-(\d{2})/(.+?)\.fits?$'
)


def expected_fz_path(src_path):
    """Return the expected .fits.fz path in the new YYYY/MM/DD structure, or None."""
    m = _DATE_DIR_RE.match(src_path)
    if not m:
        return None
    base, year, month, day, stem = m.groups()
    return '{}{}/{}/{}/{}.fits.fz'.format(base, year, month, day, stem)


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

    glob = '{}/????-*/*.fits'.format(SKYX_BASE)
    if args.year:
        glob = '{}/{}-%/*.fits'.format(SKYX_BASE, args.year)

    candidates = [dict(r) for r in con.execute(
        "SELECT id, path, preview, thumbnail FROM fits WHERE path GLOB ?", (glob,)
    ).fetchall()]

    # Keep only rows whose .fits.fz counterpart already exists in the DB
    duplicates = []
    for row in candidates:
        fz_path = expected_fz_path(row['path'])
        if fz_path is None:
            continue
        exists = con.execute(
            "SELECT 1 FROM fits WHERE path = ?", (fz_path,)
        ).fetchone()
        if exists:
            row['fz_path'] = fz_path
            duplicates.append(row)

    print('{} candidate rows, {} confirmed duplicates{}'.format(
        len(candidates), len(duplicates),
        ' (dry-run, pass --apply to delete)' if dry_run else ''))

    deleted_files = 0
    deleted_rows = 0
    errors = 0

    for row in duplicates:
        row_id  = row['id']
        path    = row['path']
        preview = row['preview']
        thumb   = row['thumbnail']

        print('  id={:6d}  {}\n{:>11}  → {}'.format(
            row_id, path, '', row['fz_path']))

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

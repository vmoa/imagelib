#!/usr/bin/env python3
"""
Find .fits files on disk (in SkyX/Images/YYYY-MM-DD directories) that have no
matching path row in the fits DB. Prints one path per line, suitable for piping
to fitsfiles.py via xargs -d '\n'.

Usage:
  python3 bin/find_orphans.py --year YYYY
  python3 bin/find_orphans.py --year YYYY | xargs -d '\n' sudo -u nas python3 fitsfiles.py
"""

import argparse
import os
import sqlite3
import subprocess
import sys

PROD_DB   = '/home/nas/data/fits.db'
SKYX_BASE = '/home/nas/Eagle/SkyX/Images'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--year', metavar='YYYY', required=True,
                   help='year to scan (e.g. 2022)')
    args = p.parse_args()

    if len(args.year) != 4 or not args.year.isdigit():
        sys.exit('ERROR: --year must be a 4-digit year')

    db_path = os.environ.get('FITSDB_FILE', PROD_DB)
    con = sqlite3.connect(db_path)

    # Load all DB paths for date-directory files in this year into a set
    # SQLite LIKE uses % not * as wildcard
    pattern = '{}/{}-%/%'.format(SKYX_BASE, args.year)
    known = set(
        row[0] for row in con.execute(
            "SELECT path FROM fits WHERE path LIKE ?", (pattern,)
        )
    )
    con.close()

    # Walk the filesystem for .fits files in YYYY-* date directories
    result = subprocess.run(
        ['find', SKYX_BASE, '-maxdepth', '2', '-name', '*.fits',
         '-path', '*/{}-*/*'.format(args.year)],
        capture_output=True, text=True
    )

    orphans = []
    for path in result.stdout.splitlines():
        path = path.strip()
        if path and path not in known:
            orphans.append(path)

    sys.stderr.write('{} orphan .fits files not in DB\n'.format(len(orphans)))
    for path in sorted(orphans):
        print(path)


if __name__ == '__main__':
    main()

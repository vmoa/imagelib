#!/usr/bin/env python3
"""
migrate_targets.py -- normalize target names in the fits and fits_by_target tables.

Dry-run by default: prints the proposed renames without touching the DB.
Pass --apply to execute the changes inside a single transaction.

Review the dry-run diff carefully (and get PR approval) before running --apply.

Usage:
  python3 bin/migrate_targets.py [--db PATH] [--apply]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitsdb
from normalize import normalize_target


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', default=None,
                   help='Path to fits.db (default: fitsdb auto-detect)')
    p.add_argument('--apply', action='store_true',
                   help='Apply changes (default: dry-run, prints diff only)')
    args = p.parse_args()

    db = fitsdb.Fitsdb() if args.db is None else fitsdb.Fitsdb.__new__(fitsdb.Fitsdb)
    if args.db:
        import sqlite3
        db.con = sqlite3.connect(args.db, check_same_thread=False)

    cur = db.con.cursor()

    rows = cur.execute(
        "SELECT target, COUNT(*) FROM fits GROUP BY target ORDER BY target"
    ).fetchall()

    changes = [(t, normalize_target(t), n) for t, n in rows if normalize_target(t) != t]

    if not changes:
        print("No changes needed.")
        return

    total_rows = sum(n for _, _, n in changes)
    label = 'DRY RUN — proposed' if not args.apply else 'Applying'
    print(f"{label} {len(changes)} renames affecting {total_rows} rows:\n")
    for old, new, count in changes:
        print(f"  {count:5d}  {old!r:45s} -> {new!r}")

    if not args.apply:
        print("\nRe-run with --apply to execute.")
        return

    print()
    cur.execute("BEGIN")
    for old, new, _ in changes:
        cur.execute("UPDATE fits SET target = ? WHERE target = ?", (new, old))
        cur.execute("UPDATE fits_by_target SET target = ? WHERE target = ?", (new, old))
    db.con.commit()
    print(f"Done. {total_rows} rows updated across fits and fits_by_target.")


if __name__ == '__main__':
    main()

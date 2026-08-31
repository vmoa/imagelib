#!/usr/bin/env python3
"""
cleanup_rfo_dirs.py -- remove SkyX calibration artifact directories from R_Drive.

Runs on rfovpn. Finds and deletes 'Closed Loop Slews' and 'Automated Pointing
Run*' directories that SkyX creates during telescope calibration. These are
never wanted in the imagelib archive.

The old sync_to_aws script deleted these from R_Drive before every rsync.
This script replaces that step and is intended to run as a separate daily cron.

Configuration (set via environment variables):
  CLEANUP_RFO_BASE  Base directory to search  [/nas/R_Drive/Eagle]

Usage:
  python3 cleanup_rfo_dirs.py [--apply]

Defaults to --dry-run.
"""

import argparse
import logging
import os
import shutil
import sys

BASE_DIR = os.environ.get('CLEANUP_RFO_BASE', '/nas/R_Drive/Eagle')

# Directory names (exact match or prefix) to remove
REMOVE_PATTERNS = [
    'Closed Loop Slews',
    'Automated Pointing Run',
]


def find_cleanup_dirs(base_dir):
    """Walk base_dir and return paths of directories matching REMOVE_PATTERNS.

    Does not descend into matched directories (they are removed wholesale).
    """
    targets = []
    for root, dirs, _files in os.walk(base_dir, topdown=True):
        matched = []
        for d in dirs:
            if any(d == pat or d.startswith(pat) for pat in REMOVE_PATTERNS):
                targets.append(os.path.join(root, d))
                matched.append(d)
        for d in matched:
            dirs.remove(d)  # prune so os.walk does not descend into them
    return targets


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--apply', action='store_true',
                   help='delete matched directories (default: dry-run)')
    args = p.parse_args()
    dry_run = not args.apply

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    log = logging.getLogger(__name__)

    targets = find_cleanup_dirs(BASE_DIR)
    log.info('Found %d calibration artifact directories under %s', len(targets), BASE_DIR)

    removed = errors = 0
    for path in targets:
        if dry_run:
            log.info('[DRY-RUN] would remove: %s', path)
        else:
            log.info('Removing: %s', path)
            try:
                shutil.rmtree(path)
                removed += 1
            except Exception as exc:
                log.error('Failed to remove %s: %s', path, exc)
                errors += 1

    if dry_run:
        log.info('Dry-run complete. Pass --apply to delete.')
    else:
        log.info('Done. removed=%d errors=%d', removed, errors)

    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()

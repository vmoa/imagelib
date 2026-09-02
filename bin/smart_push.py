#!/usr/bin/env python3
"""
smart_push.py -- sync new SkyX FITS files from R_Drive to imagelib.

Runs on rfovpn. Uses find -newer to locate files added to R_Drive since the
last run, reads DATE-OBS via astropy to uniquely identify each exposure, skips
files already sent or known to be ingested on imagelib, and rsyncs new files
to imagelib's SkyX/Images directory.

Handles .fits, .fit, and .fits.fz files identically. When SkyX or NINA is
reconfigured to write .fits.fz directly, no changes to this script are needed.

Configuration (set via environment variables):
  SMART_PUSH_R_DRIVE    R_Drive SkyX/Images mount path    [/nas/R_Drive/Eagle/SkyX/Images]
  SMART_PUSH_HOST       rsync destination host/user        [required -- e.g. nas@54.148.172.109]
  SMART_PUSH_DEST       SkyX/Images path on imagelib       [/home/nas/Eagle/SkyX/Images]
  SMART_PUSH_DB         manifest SQLite DB path            [/home/nas/var/smart_push/manifest.db]
  SMART_PUSH_TS         timestamp file path                [/home/nas/var/smart_push/last_run.ts]
  SMART_PUSH_QUARANTINE quarantine dir for files with no DATE-OBS header
                        [sibling of SkyX/Images: .../SkyX/_no_date_obs]

Directories excluded from sync (SkyX telescope calibration artifacts):
  "Closed Loop Slews", "Automated Pointing Run*"
These are purged from R_Drive at the start of each run (before find -newer),
mirroring sync_to_aws step 1. The find call also excludes them as a safety net.

Files with no DATE-OBS header are moved to QUARANTINE_DIR rather than left in
place. This prevents them from causing repeated errors on every subsequent run
(since a file left on R_Drive would be returned by find -newer tsfile each time
the tsfile fails to advance due to errors).

Usage:
  python3 smart_push.py [--apply]
  python3 smart_push.py --bootstrap FILE

To run a catch-up sync starting from a specific date (e.g. after an outage):
  touch -t YYMMDDhhmm /tmp/tsfile
  SMART_PUSH_TS=/tmp/tsfile python3 smart_push.py --apply
  (The 'sent' table in the manifest prevents re-sending files already pushed.)

Bootstrap FILE is one DATE-OBS value per line, exported from imagelib:
  sqlite3 /home/nas/data/fits.db \\
    "SELECT timestamp FROM fits WHERE path LIKE '%%SkyX%%'" > bootstrap.txt

Requirements: rsync (any recent version), astropy
"""

import argparse
import datetime
import logging
import os
import shutil
import sqlite3
import subprocess
import sys

from astropy.io import fits

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

R_DRIVE_BASE = os.environ.get('SMART_PUSH_R_DRIVE', '/nas/R_Drive/Eagle/SkyX/Images')
IMAGELIB_HOST = os.environ.get('SMART_PUSH_HOST',   '')
IMAGELIB_DEST = os.environ.get('SMART_PUSH_DEST',   '/home/nas/Eagle/SkyX/Images')
MANIFEST_DB   = os.environ.get('SMART_PUSH_DB',     '/home/nas/var/smart_push/manifest.db')
TSFILE        = os.environ.get('SMART_PUSH_TS',     '/home/nas/var/smart_push/last_run.ts')

# Sibling of R_DRIVE_BASE so it is never picked up by find_candidates.
# e.g. /nas/R_Drive/Eagle/SkyX/_no_date_obs
QUARANTINE_DIR = os.environ.get(
    'SMART_PUSH_QUARANTINE',
    os.path.join(os.path.dirname(R_DRIVE_BASE), '_no_date_obs'),
)

FILE_PATTERNS = ['*.fits', '*.fit', '*.fits.fz']

# SkyX telescope calibration directories that should never be synced.
# The old sync_to_aws deleted these from R_Drive; smart_push skips them instead.
SKIP_DIR_PATTERNS = ['Closed Loop Slews', 'Automated Pointing Run']

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path):
    """Open (or create) the manifest SQLite database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS sent (
            date_obs     TEXT PRIMARY KEY,
            r_drive_path TEXT NOT NULL,
            sent_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS known_ingested (
            date_obs TEXT PRIMARY KEY
        );
    """)
    con.commit()
    return con


def is_known(con, date_obs):
    """Return True if date_obs appears in sent or known_ingested."""
    return bool(
        con.execute('SELECT 1 FROM sent WHERE date_obs = ?', (date_obs,)).fetchone() or
        con.execute('SELECT 1 FROM known_ingested WHERE date_obs = ?', (date_obs,)).fetchone()
    )

# ---------------------------------------------------------------------------
# FITS header
# ---------------------------------------------------------------------------

def read_date_obs(path):
    """Return DATE-OBS from a FITS file, or None on failure.

    Handles .fits, .fit, and .fits.fz transparently. DATE-OBS may be in the
    primary HDU header or a CompImageHDU extension header.
    """
    try:
        with fits.open(path, memmap=False) as hdul:
            for hdu in hdul:
                if 'DATE-OBS' in hdu.header:
                    return hdu.header['DATE-OBS']
    except Exception as exc:
        logging.warning('Could not read DATE-OBS from %s: %s', path, exc)
    return None

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_candidates(r_drive_base, tsfile, skip_dirs=None):
    """Return paths of FITS files under r_drive_base newer than tsfile.

    If tsfile does not exist, returns all FITS files (first run or recovery).
    Directories whose names start with any entry in skip_dirs are pruned.
    """
    if skip_dirs is None:
        skip_dirs = SKIP_DIR_PATTERNS
    cmd = ['find', r_drive_base]
    # Prune excluded directories before descending into them
    for pattern in skip_dirs:
        cmd += ['-name', pattern, '-prune', '-o']
    cmd += ['-type', 'f']
    if os.path.exists(tsfile):
        cmd += ['-newer', tsfile]
    name_args = []
    for pattern in FILE_PATTERNS:
        if name_args:
            name_args.append('-o')
        name_args += ['-name', pattern]
    cmd += ['('] + name_args + [')']
    cmd += ['-print']
    result = subprocess.run(cmd, capture_output=True, text=True)
    return [p.strip() for p in result.stdout.splitlines() if p.strip()]

# ---------------------------------------------------------------------------
# Calibration directory cleanup
# ---------------------------------------------------------------------------

def cleanup_cal_dirs(r_drive_base, log, dry_run):
    """Remove SkyX calibration artifact directories from r_drive_base.

    Walks r_drive_base and removes any directory whose name matches
    SKIP_DIR_PATTERNS (exact match or prefix). Must be called before
    find_candidates so these files are never picked up as sync candidates.

    Returns (removed, errors) counts.
    """
    targets = []
    for root, dirs, _files in os.walk(r_drive_base, topdown=True):
        matched = []
        for d in dirs:
            if any(d == pat or d.startswith(pat) for pat in SKIP_DIR_PATTERNS):
                targets.append(os.path.join(root, d))
                matched.append(d)
        for d in matched:
            dirs.remove(d)

    removed = errors = 0
    for path in targets:
        if dry_run:
            log.info('[DRY-RUN] would remove cal dir: %s', path)
        else:
            log.info('Removing cal dir: %s', path)
            try:
                shutil.rmtree(path)
                removed += 1
            except Exception as exc:
                log.error('Failed to remove %s: %s', path, exc)
                errors += 1

    if targets:
        log.info('Cal dir cleanup: found=%d removed=%d errors=%d', len(targets), removed, errors)
    return removed, errors

# ---------------------------------------------------------------------------
# Quarantine (no DATE-OBS)
# ---------------------------------------------------------------------------

def quarantine_file(path, log, dry_run):
    """Move a FITS file that has no DATE-OBS header to QUARANTINE_DIR.

    Returns True if the file was quarantined (or dry_run), False if the move
    failed and the file was left in place.

    Placing the file outside R_DRIVE_BASE ensures it is never returned by
    find_candidates on subsequent runs. If a file with the same name already
    exists in the quarantine dir, a timestamp prefix is added to avoid
    overwriting.
    """
    basename = os.path.basename(path)
    dest = os.path.join(QUARANTINE_DIR, basename)
    if os.path.exists(dest):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(QUARANTINE_DIR, '{}_{}'.format(ts, basename))

    if dry_run:
        log.warning('[DRY-RUN] No DATE-OBS — would quarantine: %s -> %s', path, dest)
        return True

    try:
        os.makedirs(QUARANTINE_DIR, exist_ok=True)
        shutil.move(path, dest)
        log.warning('No DATE-OBS — quarantined: %s -> %s', path, dest)
        return True
    except Exception as exc:
        log.error('No DATE-OBS and quarantine failed for %s: %s', path, exc)
        return False

# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------

def rsync_file(src_path, r_drive_base, imagelib_host, imagelib_dest, log, dry_run):
    """rsync one file to imagelib, preserving its relative directory structure.

    Uses --rsync-path to mkdir -p the destination directory before transferring,
    which works with any rsync version (avoids the --mkpath requirement of 3.2.3).
    """
    rel_path = os.path.relpath(src_path, r_drive_base)
    dest_dir = '{}/{}'.format(imagelib_dest, os.path.dirname(rel_path))
    dest = '{}:{}/{}'.format(imagelib_host, imagelib_dest, rel_path)
    rsync_path = "mkdir -p '{}' && rsync".format(dest_dir)
    cmd = ['rsync', '-az', '-s', '--rsync-path', rsync_path, src_path, dest]
    if dry_run:
        log.info('[DRY-RUN] would rsync: %s -> %s', rel_path, dest)
        return True
    log.info('Sending %s -> %s', rel_path, dest)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error('rsync failed for %s: %s', rel_path, result.stderr.strip())
        return False
    return True

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def run_bootstrap(con, date_obs_file, log):
    """Pre-populate known_ingested from a file of DATE-OBS values (one per line)."""
    inserted = skipped = 0
    with open(date_obs_file) as f:
        for line in f:
            date_obs = line.strip()
            if not date_obs:
                continue
            cur = con.execute(
                'INSERT OR IGNORE INTO known_ingested (date_obs) VALUES (?)', (date_obs,))
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
    con.commit()
    log.info('Bootstrap: %d inserted, %d already present in known_ingested', inserted, skipped)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--apply', action='store_true',
                   help='rsync files and update manifest (default: dry-run)')
    p.add_argument('--bootstrap', metavar='FILE',
                   help='one-time: pre-populate known_ingested from FILE of DATE-OBS values')
    args = p.parse_args()
    dry_run = not args.apply

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = '/tmp/smart_push_{}.log'.format(ts)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger(__name__)

    if not args.bootstrap and not IMAGELIB_HOST:
        log.error('SMART_PUSH_HOST environment variable is required')
        sys.exit(1)

    con = init_db(MANIFEST_DB)

    if args.bootstrap:
        run_bootstrap(con, args.bootstrap, log)
        con.close()
        return

    start_time = datetime.datetime.now()
    log.info('smart_push start  dry_run=%s  r_drive=%s', dry_run, R_DRIVE_BASE)
    if not dry_run:
        log.info('Log: %s', log_path)

    sent = skipped = errors = 0

    # Step 1: purge calibration dirs before scanning — mirrors sync_to_aws step 1,
    # ensuring cal dir files are never returned as candidates by find_candidates.
    _removed, _errs = cleanup_cal_dirs(R_DRIVE_BASE, log, dry_run)
    errors += _errs

    candidates = find_candidates(R_DRIVE_BASE, TSFILE)
    log.info('Candidates (newer than tsfile): %d', len(candidates))
    for path in candidates:
        date_obs = read_date_obs(path)
        if date_obs is None:
            if not quarantine_file(path, log, dry_run):
                errors += 1  # move failed; file stays and will be retried
            continue

        if is_known(con, date_obs):
            log.debug('Already known (%s), skipping: %s', date_obs, path)
            skipped += 1
            continue

        rel_path = os.path.relpath(path, R_DRIVE_BASE)
        if rsync_file(path, R_DRIVE_BASE, IMAGELIB_HOST, IMAGELIB_DEST, log, dry_run):
            if not dry_run:
                con.execute(
                    'INSERT OR IGNORE INTO sent (date_obs, r_drive_path, sent_at) VALUES (?,?,?)',
                    (date_obs, rel_path, start_time.isoformat()),
                )
                con.commit()
            sent += 1
        else:
            errors += 1

    log.info('Done. sent=%d  skipped=%d  errors=%d', sent, skipped, errors)

    # Only update tsfile on a fully clean run so a partial run retries all candidates next time
    if not dry_run and errors == 0:
        timestamp = start_time.strftime('%Y%m%d%H%M.%S')
        subprocess.run(['touch', '-t', timestamp, TSFILE])
        log.info('Updated tsfile: %s', TSFILE)
    elif not dry_run and errors:
        log.warning('Errors occurred -- tsfile NOT updated; all candidates re-examined next run')

    con.close()
    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()

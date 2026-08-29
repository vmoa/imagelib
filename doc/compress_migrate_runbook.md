# compress_migrate Maintenance Window Runbook

Migration of SkyX `.fits` files to RICE-compressed `.fits.fz` in a reorganized
`YYYY/MM/DD` folder structure. Process one year at a time.

## Overview

Files move from `SkyX/Images/YYYY-MM-DD/file.fits` to
`SkyX/Images/YYYY/MM/DD/file.fits.fz`. The DB is updated atomically before
originals are deleted. The web server must be in maintenance mode during
`--apply` so no downloads hit files mid-move.

Scripts involved:

| Script | Purpose |
|---|---|
| `bin/find_orphans.py` | Find `.fits` files on disk not yet in the DB |
| `fitsfiles.py` | Ingest orphan files (parse headers, generate PNGs, insert DB rows) |
| `bin/compress_migrate.py` | Compress and reorganize one year's files |
| `bin/cleanup_orphan_fits.py` | Remove duplicate DB rows left by failed unlinks |

---

## Step 1 — Find and ingest orphans (no maintenance window needed)

Some `.fits` files on disk were never ingested into the DB. These must be added
before compress_migrate runs so they are included in the migration.

```bash
# Check count — stderr shows total, stdout has paths
python3 bin/find_orphans.py --year YYYY

# Ingest (xargs -d '\n' handles spaces in filenames)
python3 bin/find_orphans.py --year YYYY \
  | xargs -d '\n' sudo -u nas python3 fitsfiles.py
```

This can run while the site is live. It only adds rows and generates PNGs.

**If ingest fails with "UNIQUE constraint failed: fits.path":** the files are
already in the DB (find_orphans was not filtering correctly). No action needed —
proceed to step 2.

---

## Step 2 — Open maintenance window

```bash
# Create the flag file — the web server returns 503 immediately
sudo touch /home/nas/data/MAINTENANCE

# Verify maintenance mode is active
curl -s -o /dev/null -w "%{http_code}" https://imagelib.rfo.org/
# Expected: 503
```

---

## Step 3 — Dry run

```bash
sudo -u nas python3 bin/compress_migrate.py --year YYYY
```

Review the candidate row count and a sample of paths before applying.

---

## Step 4 — Apply

```bash
sudo -u nas python3 bin/compress_migrate.py --year YYYY --apply
```

A log is written to `/tmp/compress_migrate_<timestamp>.log`. The script exits
non-zero if any row errored. Review the log if that happens before proceeding.

---

## Step 5 — Close maintenance window

```bash
sudo rm /home/nas/data/MAINTENANCE

# Verify site is back
curl -s -o /dev/null -w "%{http_code}" https://imagelib.rfo.org/
# Expected: 200
```

---

## Step 6 — Verify downloads

Open the UI, navigate to the migrated year, and download at least one image.
Downloads failing with Internal Server Error after a successful compress_migrate
run usually means the new `.fits.fz` files have mode `600` (unreadable by
Apache). Fix with:

```bash
find /home/nas/Eagle/SkyX/Images/YYYY -name "*.fits.fz" -exec chmod 644 {} \;
find /home/nas/Eagle/SkyX/Images/YYYY -type d -exec chmod 755 {} \;
```

The `umask 022` line in `compress_migrate.py` prevents this going forward, but
apply the fix manually to any files created before that fix was deployed.

---

## Step 7 — Check for and remove duplicate DB rows

If compress_migrate successfully compressed a file but failed to delete the
original `.fits`, and fitsfiles.py was subsequently run on that file, the DB
will have two rows for the same image. `cleanup_orphan_fits.py` detects this
by checking whether a `.fits.fz` counterpart already exists in the DB for each
`.fits` row in a date-directory path.

```bash
# Dry run — should be 0 if compress_migrate deleted originals cleanly
sudo -u nas python3 bin/cleanup_orphan_fits.py --year YYYY

# If count > 0, apply the cleanup
sudo -u nas python3 bin/cleanup_orphan_fits.py --year YYYY --apply
```

This does not require a maintenance window.

---

## Step 8 — Remove empty old-format date directories

Once all years have been migrated and cleaned up, the `YYYY-MM-DD` directories
should be empty. Confirm and remove:

```bash
# Confirm no .fits files remain in old-format directories
find /home/nas/Eagle/SkyX/Images -name "*.fits" -path "*/????-*/*" | wc -l
# Expected: 0

# Remove empty directories
find /home/nas/Eagle/SkyX/Images -maxdepth 1 -type d -name "????-*" -empty -delete
```

---

## Known issues and fixes

**Files not in DB before migration**
Some files were captured but never ingested (cron missed them, ingest error,
etc.). `find_orphans.py` identifies these. Always run step 1 before step 3.

**Duplicate DB rows after migration**
If `os.unlink` fails after a successful compress and DB update, the original
`.fits` remains on disk. A subsequent `fitsfiles.py` run re-ingests it, creating
a duplicate row. `cleanup_orphan_fits.py` identifies duplicates by checking for
a `.fits.fz` counterpart in the DB and removes the stale `.fits` rows and files.

**Downloads return 500 after migration**
Caused by new `.fits.fz` files being mode `600` (readable only by the `nas`
user, not by Apache). Fixed by the `umask 022` call in `compress_migrate.py`
main(). For files created before that fix, use the `chmod` commands in step 6.

**Production server not picking up code changes**
After merging a PR, run on the server:
```bash
cd /home/nas/flask/imagelib
git pull
sudo systemctl reload apache2
```

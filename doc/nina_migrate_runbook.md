# NINA Migration Runbook

Moves all `NINA/Astro-Images` FITS files into `SkyX/Images/YYYY/MM/DD/`, merging them
into the SkyX tree and decommissioning NINA as a delivery folder. DB paths are updated
in place. No compression — `_maybe_compress_skyx` picks them up on the next fitsfiles.py
run.

**Prerequisites:** Phase 4d (SkyX compression, PR #43) complete and verified. ✓

---

## Before the maintenance window

**1. Confirm how many rows will be moved:**
```bash
sudo -u nas sqlite3 /home/nas/data/fits.db \
  "SELECT COUNT(*) FROM fits WHERE path LIKE '/home/nas/Eagle/NINA/Astro-Images/%'"
```

**2. Verify disk space on imagelib** — NINA files move within the same filesystem
(NINA → SkyX/Images), so no net space change, but confirm before starting:
```bash
df -h /home/nas
```

**3. Verify the script is current:**
```bash
cd /home/nas/flask/imagelib && git pull && git log --oneline -3
```

---

## Pilot run — single date

Pick a date with a small number of files to verify the move and DB update end-to-end
before touching everything.

**Find a good pilot date (small file count):**
```bash
sudo -u nas sqlite3 /home/nas/data/fits.db \
  "SELECT date, COUNT(*) as n FROM fits
   WHERE path LIKE '/home/nas/Eagle/NINA/Astro-Images/%'
   GROUP BY date ORDER BY n ASC LIMIT 10"
```

**Dry-run the pilot date:**
```bash
sudo -u nas python3 /home/nas/flask/imagelib/bin/nina_migrate.py \
  --pilot-date YYYY-MM-DD
```

Review the log output — each line shows `id=N  source → destination`.

**Apply the pilot date:**
```bash
sudo touch /home/nas/data/MAINTENANCE
sudo -u nas python3 /home/nas/flask/imagelib/bin/nina_migrate.py \
  --pilot-date YYYY-MM-DD --apply
```

**Verify the pilot:**
```bash
# DB row points at new path
sudo -u nas sqlite3 /home/nas/data/fits.db \
  "SELECT path FROM fits WHERE date = 'YYYY-MM-DD'
   AND path LIKE '/home/nas/Eagle/NINA/%' LIMIT 5"
# should return 0 rows

sudo -u nas sqlite3 /home/nas/data/fits.db \
  "SELECT path FROM fits WHERE date = 'YYYY-MM-DD'
   AND path LIKE '/home/nas/Eagle/SkyX/%' LIMIT 5"
# should return the moved files

# Files exist on disk at new location
ls /home/nas/Eagle/SkyX/Images/YYYY/MM/DD/

# Originals are gone
ls /home/nas/Eagle/NINA/Astro-Images/YYYY-MM-DD/ 2>/dev/null || echo "directory gone or empty"
```

**Check imagelib UI** — open a record from the pilot date and confirm image loads correctly.

---

## Full migration

Only proceed after the pilot is verified.

**Dry-run the full set:**
```bash
sudo -u nas python3 /home/nas/flask/imagelib/bin/nina_migrate.py \
  2>&1 | tee /tmp/nina_migrate_dryrun.log
tail -5 /tmp/nina_migrate_dryrun.log
```

Expect `processed=N  skipped=0  error=0` where N matches the COUNT from step 1.

**Apply:**

The MAINTENANCE flag should already be in place from the pilot. If not:
```bash
sudo touch /home/nas/data/MAINTENANCE
```

```bash
sudo -u nas python3 /home/nas/flask/imagelib/bin/nina_migrate.py --apply \
  2>&1 | tee /tmp/nina_migrate_apply.log
tail -5 /tmp/nina_migrate_apply.log
```

A timestamped log is also written to `/tmp/nina_migrate_YYYYMMDD_HHMMSS.log`.

---

## After the migration

**1. Verify counts:**
```bash
# Should be 0
sudo -u nas sqlite3 /home/nas/data/fits.db \
  "SELECT COUNT(*) FROM fits WHERE path LIKE '/home/nas/Eagle/NINA/Astro-Images/%'"

# Should match original count
sudo -u nas sqlite3 /home/nas/data/fits.db \
  "SELECT COUNT(*) FROM fits WHERE path LIKE '/home/nas/Eagle/SkyX/Images/%'
   AND date IN (SELECT DISTINCT date FROM fits
                WHERE path LIKE '/home/nas/Eagle/NINA/%')"
```

**2. Check for orphaned files** (files on disk with no DB row):
```bash
sudo -u nas find /home/nas/Eagle/NINA/Astro-Images -type f | head -20
```
Any `.fits` files remaining here were not in the DB — log them and decide whether to
add them manually or discard.

**3. Wait for fitsfiles.py to compress** — the moved `.fits` files will be found by
`_maybe_compress_skyx` on the next cron run (within 5 minutes) and compressed to
`.fits.fz` in place. Monitor `/tmp/fitsfiles.out` for progress.

**4. Remove the maintenance flag:**
```bash
sudo rm /home/nas/data/MAINTENANCE
```

**5. Confirm the imagelib UI looks correct** — spot-check a few NINA-era records to
confirm images load and previews render.

---

## Rollback

The script copies before updating the DB and deletes originals only after commit. If
the script is interrupted mid-run:

- Any row whose DB path already points to `SkyX/Images/` has been fully committed.
  The original in `NINA/Astro-Images/` has been deleted.
- Any row whose DB path still points to `NINA/Astro-Images/` has not been touched
  (or failed). Re-run `--apply` — the script re-queries from the DB, so it naturally
  resumes from the remaining rows.

There is no manual rollback path for rows already committed — the new `.fits` path in
`SkyX/Images/YYYY/MM/DD/` is the canonical location going forward.

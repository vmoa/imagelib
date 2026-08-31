# imagelib Data Flow

End-to-end documentation of how FITS images travel from the telescope to the imagelib
web application, including the current ingest architecture and the proposed smart sync
replacing the legacy rsync.

---

## System Components

| Component | Location | Role |
|---|---|---|
| Eagle PC | Observatory (Windows) | Telescope control; SkyX captures exposures |
| R_Drive | Observatory (NAS, RAID1 3TB) | Primary archive of all raw FITS files |
| rfovpn | Observatory server (Linux) | Mounts R_Drive; gateway to AWS over VPN |
| imagelib | AWS EC2 (Linux, `/home/nas/Eagle/`) | Database, web server, compressed image store |

---

## File Formats in Play

| Extension | Description | Where it lives |
|---|---|---|
| `.fits` / `.fit` | Raw uncompressed FITS | R_Drive (always); imagelib (transiently during ingest) |
| `.fits.fz` | RICE-compressed FITS (astropy `CompImageHDU`) | imagelib permanent store; future R_Drive output when SkyX/NINA is reconfigured |

---

## Directory Structures

**R_Drive (observatory, source of truth):**
```
/nas/R_Drive/SkyX/Images/
    YYYY-MM-DD/          ← SkyX assigns date from local clock
        filename.fits
```

**imagelib (AWS, permanent store):**
```
/home/nas/Eagle/SkyX/Images/
    YYYY/MM/DD/          ← date from DATE-OBS header (UTC)
        filename.fits.fz
    Asterism/rfo/
        YYYY/MM/DD/
            filename.fits.fz
```

---

## Current Flow (post PRs #41–44)

### 1. Capture (observatory)

```
Telescope → SkyX → R_Drive/SkyX/Images/YYYY-MM-DD/filename.fits
```

SkyX names the date directory from the local observatory clock (Pacific time).

### 2. Sync to imagelib — CURRENTLY DISABLED

The legacy `sync_to_aws` rsync on rfovpn has been commented out because it
re-pushed the entire historical archive after the YYYY/MM/DD reorganization.
No automated sync is running. Files only reach imagelib if pushed manually.

### 3. Ingest on imagelib (`fitsfiles.py`, hourly cron)

When a `.fits`, `.fit`, or `.fits.fz` file appears under
`/home/nas/Eagle/`, `fitsfiles.py` picks it up on the next cron run via
`find -newer tsfile`.

**Per-file processing in `addFitsFile()`:**

```
parseFitsHeader()
    └─ astropy opens file (handles .fits, .fit, .fits.fz transparently)
    └─ extracts DATE-OBS, OBJECT, IMAGETYP, EXPTIME, FILTER, NAXIS1/2, etc.

_maybe_organize()           [Asterism files only]
    └─ if file is in ASTERISM_DROP flat folder:
         copy to ASTERISM_DROP/YYYY/MM/DD/, verify size, delete original

_maybe_compress_skyx()      [SkyX files only]
    └─ if file is under SkyX/Images/ but NOT in YYYY/MM/DD structure:
         ┌─ dest_fz already exists on disk?
         │    └─ delete incoming duplicate, return existing path (re-sync guard)
         ├─ file is .fits.fz?
         │    └─ copy to SkyX/Images/YYYY/MM/DD/, delete original
         └─ file is .fits/.fit?
              compress to temp .fits.fz (RICE_1) in source directory
              verify pixels with np.array_equal
              move .fits.fz to SkyX/Images/YYYY/MM/DD/
              delete original .fits/.fit
         └─ attempt os.rmdir on source YYYY-MM-DD directory (no-op if non-empty)
         └─ on any failure: log error, return original path unchanged

buildDatabaseRecord()
    └─ derives target, imagetype, date (from DATE-OBS UTC), filter, binning, etc.
    └─ record['path'] = final .fits.fz path in YYYY/MM/DD

fits2png()
    └─ calls fitspng CLI (via safe temp-rename workaround for complex filenames)
    └─ generates full-res preview .png and thumbnail -thumb.png alongside .fits.fz

db.insert()
    └─ inserts into fits table; UNIQUE constraint on path silently skips duplicates
```

**YYYY-MM-DD directory cleanup:** after each file is deleted from its source
directory, `os.rmdir` is attempted on that directory. It succeeds only if the
directory is now empty and fails silently otherwise. smart_push (or rsync)
recreates the directory on the next push if needed.

---

## Proposed Flow — smart_push.py (replaces rsync)

### Why rsync was wrong

rsync mirrors directory structure. The source (R_Drive) has `YYYY-MM-DD`;
the destination (imagelib) now uses `YYYY/MM/DD` with RICE compression. rsync
has no awareness of what imagelib has already ingested, so it re-pushes the
entire ~50,000-file historical archive after any reorganization.

### Design principles

- **DATE-OBS is the unique identifier.** It is stored in every FITS header and
  in the imagelib DB `timestamp` column. It is unique per exposure, format-
  independent, and survives renaming, compression, and directory restructuring.
- **`find -newer tsfile` limits candidates.** Only files added to R_Drive since
  the last run are examined — typically 50–200 files per night, not 50,000.
- **astropy reads headers.** Handles `.fits`, `.fit`, and `.fits.fz` identically
  without special casing. No fragility across FITS versions.
- **Manifest DB on rfovpn is the sync state.** imagelib's DB is never queried
  at runtime; it is used only during the one-time bootstrap.

### Manifest database (on rfovpn)

```sql
-- Files rfovpn has successfully pushed to imagelib
CREATE TABLE sent (
    date_obs     TEXT PRIMARY KEY,   -- FITS DATE-OBS (authoritative unique key)
    r_drive_path TEXT NOT NULL,      -- R_Drive relative path (audit/debug only)
    sent_at      TEXT NOT NULL       -- ISO timestamp of push
);

-- DATE-OBS values already ingested on imagelib before smart_push existed (bootstrap)
CREATE TABLE known_ingested (
    date_obs TEXT PRIMARY KEY
);
```

### Bootstrap (one-time)

Pre-populate `known_ingested` from imagelib's DB so historical files are never
pushed:

```bash
# On imagelib:
sqlite3 /home/nas/data/fits.db \
  "SELECT timestamp FROM fits WHERE path LIKE '%SkyX%'" > bootstrap.txt

# Transfer bootstrap.txt to rfovpn, then:
python3 smart_push.py --bootstrap bootstrap.txt
```

No R_Drive walk required. Bootstrap inserts are idempotent (PRIMARY KEY conflict
is silently ignored).

### Per-run algorithm

```
record start_time

candidates = find(R_DRIVE, newer_than=tsfile, names=['*.fits','*.fit','*.fits.fz'])

for each candidate:
    date_obs = astropy.fits.open(candidate) → DATE-OBS header
    if date_obs is None:
        log warning, skip
        continue
    if date_obs in sent OR date_obs in known_ingested:
        skip (already on imagelib or already ingested pre-bootstrap)
    rsync candidate → imagelib:/home/nas/Eagle/SkyX/Images/YYYY-MM-DD/filename
    if rsync exit 0:
        INSERT INTO sent (date_obs, r_drive_path, sent_at)

touch tsfile with start_time
```

### imagelib side — no changes required

Files arrive at imagelib in `SkyX/Images/YYYY-MM-DD/` format.
`_maybe_compress_skyx` handles compression, reorganization, and cleanup exactly
as it does today. smart_push is transparent to imagelib's ingest pipeline.

### .fits.fz support (future SkyX/NINA reconfiguration)

smart_push.py already includes `*.fits.fz` in its `find` patterns. When
SkyX or NINA is reconfigured to write `.fits.fz` directly to R_Drive,
**no change to smart_push.py is required**. astropy reads DATE-OBS from
`.fits.fz` headers identically to uncompressed files, and `_maybe_compress_skyx`
already handles incoming `.fits.fz` files (moves them to `YYYY/MM/DD/` without
re-compressing, with the re-sync duplicate guard).

### Failure modes and recovery

| Failure | Effect | Recovery |
|---|---|---|
| rsync fails for one file | Not inserted into `sent`; retried next cron run | Automatic |
| rfovpn crashes mid-run | Partial `sent` entries for completed files only | Automatic (next run retries missing files) |
| tsfile lost | Next run walks all of R_Drive once; `sent` table prevents re-pushing | Automatic (slow one-time run) |
| Manifest DB lost | Next run finds all 50k files; `known_ingested` must be re-bootstrapped | Re-run bootstrap; then `find -newer` resumes normal cadence |
| imagelib DB has duplicate path | `db.insert` UNIQUE constraint silently ignores it | Automatic |

---

## Key Design Decisions

**DATE-OBS as the universal key, not file path.**
The directory structure on R_Drive (YYYY-MM-DD, local time) and on imagelib
(YYYY/MM/DD, UTC from DATE-OBS) can differ by one day for late-night
observations. Only the FITS header value itself is reliable across both systems.

**R_Drive is never modified.**
All compression and reorganization happens on imagelib. R_Drive remains the
unmodified 3TB archive of raw FITS files indefinitely.

**`_maybe_compress_skyx` is idempotent.**
If a file already exists at the destination (re-synced or retried), the incoming
duplicate is deleted and the existing compressed file is returned. This makes
the entire ingest pipeline safe to re-run without side effects.

**Compression location is source-agnostic.**
Files may arrive compressed (`.fits.fz`, when SkyX/NINA is reconfigured) or
uncompressed (`.fits`/`.fit`, current default). `_maybe_compress_skyx` handles
both: it compresses incoming uncompressed files on imagelib, and moves already-
compressed files without re-compressing. No code change is required when the
source switches format. Network bandwidth decreases naturally once the source
writes `.fits.fz` directly; no design decision forces it either way.
